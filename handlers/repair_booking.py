from typing import Optional

from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from config import get_photo_path, REMINDER_TIME_MINUTES, ADMIN_ID
from database import Session, User, Auto, Booking, BookingStatus
from keyboards.main_kb import Keyboards
from datetime import datetime
from utils import setup_logger
from .service_utils import (
    get_progress_bar, send_message, handle_error,
    check_user_and_autos, notify_master, schedule_reminder, schedule_user_reminder,
    master_only, get_booking_context, send_booking_notification
)
from .states import RepairBookingStates, REPAIR_PROGRESS_STEPS
from .reminder_manager import reminder_manager
import asyncio
import re

logger = setup_logger(__name__)

repair_booking_router = Router()

async def send_state_message(
    bot: Bot,
    chat_id: str,
    state: FSMContext,
    next_state: RepairBookingStates,
    message: str,
    photo_key: Optional[str] = None,
    reply_markup: Optional[InlineKeyboardMarkup] = None
) -> bool:
    """Отправляет сообщение и обновляет состояние."""
    sent_message = await send_message(
        bot, chat_id, "photo" if photo_key else "text",
        (await get_progress_bar(next_state, REPAIR_PROGRESS_STEPS, style="emoji")).format(message=message),
        photo_path=get_photo_path(photo_key) if photo_key else None,
        reply_markup=reply_markup
    )
    if sent_message:
        await state.update_data(last_message_id=sent_message.message_id)
        await state.set_state(next_state)
        logger.debug(f"Состояние установлено: {next_state}")
        return True
    return False

@repair_booking_router.message(F.text == "Запись на ремонт")
async def start_repair_booking(message: Message, state: FSMContext, bot: Bot):
    """Начинает процесс записи на ремонт."""
    logger.info(f"Пользователь {message.from_user.id} начал запись на ремонт")
    try:
        with Session() as session:
            user, autos = await check_user_and_autos(session, str(message.from_user.id), bot, message, state, "booking_repair")
            if user:
                if autos:
                    await send_state_message(
                        bot, str(message.chat.id), state,
                        RepairBookingStates.AwaitingAuto,
                        "Выберите автомобиль для ремонта: 🚗",
                        "booking_repair",
                        Keyboards.auto_selection_kb(autos)
                    )
                else:
                    sent_message = await send_message(
                        bot, str(message.chat.id), "text",
                        "У вас нет зарегистрированных автомобилей. Добавьте автомобиль в личном кабинете. 🚗",
                        reply_markup=Keyboards.main_menu_kb()
                    )
                    if sent_message:
                        await state.update_data(last_message_id=sent_message.message_id)
                    await state.clear()
    except Exception as e:
        await handle_error(message, state, bot, "Ошибка. Попробуйте снова. 😔", "Ошибка начала записи на ремонт", e)

@repair_booking_router.callback_query(RepairBookingStates.AwaitingAuto, F.data.startswith("auto_"))
async def process_auto_selection(callback: CallbackQuery, state: FSMContext, bot: Bot):
    """Обрабатывает выбор автомобиля."""
    auto_id = int(callback.data.replace("auto_", ""))
    try:
        with Session() as session:
            auto = session.query(Auto).get(auto_id)
            if not auto:
                await handle_error(
                    callback, state, bot,
                    "Автомобиль не найден. Попробуйте снова. 🚗",
                    f"Автомобиль не найден для auto_id={auto_id}",
                    Exception("Автомобиль не найден")
                )
                await callback.answer()
                return
        await state.update_data(auto_id=auto_id)
        success = await send_state_message(
            bot, str(callback.message.chat.id), state,
            RepairBookingStates.AwaitingDescription,
            "Опишите проблему с автомобилем (например, <b>стук в двигателе</b>): 📝",
            "booking_repair_sel",
            reply_markup=Keyboards.cancel_kb()
        )
        if success:
            await callback.answer()
    except Exception as e:
        await handle_error(callback, state, bot, "Ошибка. Попробуйте снова. 😔", "Ошибка выбора автомобиля", e)
        await callback.answer()

@repair_booking_router.message(RepairBookingStates.AwaitingDescription, F.text)
async def process_description(message: Message, state: FSMContext, bot: Bot):
    """Обрабатывает описание проблемы."""
    description = message.text.strip()
    if len(description) < 5:
        await send_state_message(
            bot, str(message.chat.id), state,
            RepairBookingStates.AwaitingDescription,
            "Описание слишком короткое (мин. 5 символов). Введите снова: 📝",
            "booking_repair_sel",
            reply_markup=Keyboards.cancel_kb()
        )
        return
    await state.update_data(description=description, photos=[])
    success = await send_state_message(
        bot, str(message.chat.id), state,
        RepairBookingStates.AwaitingPhotos,
        "Отправьте <b>фото</b> проблемы (или нажмите 'Продолжить без фото'): 📸",
        reply_markup=Keyboards.continue_without_photos_kb()
    )

@repair_booking_router.message(RepairBookingStates.AwaitingPhotos, F.photo)
async def process_photos(message: Message, state: FSMContext, bot: Bot):
    """Обрабатывает отправку фотографий."""
    data = await state.get_data()
    photos = data.get("photos", [])
    photos.append(message.photo[-1].file_id)
    await state.update_data(photos=photos)
    success = await send_state_message(
        bot, str(message.chat.id), state,
        RepairBookingStates.AwaitingPhotos,
        f"Фото добавлено ({len(photos)}). Отправьте ещё или нажмите 'Продолжить': 📸",
        reply_markup=Keyboards.continue_without_photos_kb()
    )

@repair_booking_router.callback_query(RepairBookingStates.AwaitingPhotos, F.data == "continue_without_photos")
async def continue_without_photos(callback: CallbackQuery, state: FSMContext, bot: Bot):
    """Продолжает без добавления фотографий."""
    await state.update_data(week_offset=0)
    success = await send_state_message(
        bot, str(callback.message.chat.id), state,
        RepairBookingStates.AwaitingDate,
        "Выберите <b>дату</b> для записи: 📅",
        reply_markup=Keyboards.calendar_kb()
    )
    if success:
        await callback.answer()

@repair_booking_router.callback_query(RepairBookingStates.AwaitingDate, F.data.startswith("prev_week_"))
async def prev_week_selection(callback: CallbackQuery, state: FSMContext):
    """Обрабатывает переход на предыдущую неделю."""
    week_offset = int(callback.data.replace("prev_week_", ""))
    data = await state.get_data()
    selected_date = data.get("selected_date")
    await state.update_data(week_offset=week_offset)
    await callback.message.edit_reply_markup(
        reply_markup=Keyboards.calendar_kb(selected_date, week_offset)
    )
    await callback.answer()

@repair_booking_router.callback_query(RepairBookingStates.AwaitingDate, F.data.startswith("next_week_"))
async def next_week_selection(callback: CallbackQuery, state: FSMContext):
    """Обрабатывает переход на следующую неделю."""
    week_offset = int(callback.data.replace("next_week_", ""))
    data = await state.get_data()
    selected_date = data.get("selected_date")
    await state.update_data(week_offset=week_offset)
    await callback.message.edit_reply_markup(
        reply_markup=Keyboards.calendar_kb(selected_date, week_offset)
    )
    await callback.answer()

@repair_booking_router.callback_query(RepairBookingStates.AwaitingDate, F.data == "today")
async def today_selection(callback: CallbackQuery, state: FSMContext):
    """Обрабатывает выбор текущего дня."""
    await state.update_data(week_offset=0)
    data = await state.get_data()
    selected_date = data.get("selected_date")
    await callback.message.edit_reply_markup(
        reply_markup=Keyboards.calendar_kb(selected_date, 0)
    )
    await callback.answer()

@repair_booking_router.callback_query(RepairBookingStates.AwaitingDate, F.data.startswith("date_"))
async def process_date_selection(callback: CallbackQuery, state: FSMContext, bot: Bot):
    """Обрабатывает выбор даты."""
    date_str = callback.data.replace("date_", "")
    try:
        selected_date = datetime.strptime(date_str, "%Y-%m-%d")
        data = await state.get_data()
        week_offset = data.get("week_offset", 0)
        with Session() as session:
            time_slots = Keyboards.time_slots_kb(selected_date, 60, session)
            if not time_slots.inline_keyboard:
                await send_state_message(
                    bot, str(callback.message.chat.id), state,
                    RepairBookingStates.AwaitingDate,
                    "Нет доступных слотов на эту дату. Выберите другую дату: 📅",
                    reply_markup=Keyboards.calendar_kb(selected_date, week_offset)
                )
                await callback.answer()
                return
            await state.update_data(selected_date=selected_date, time_offset=0)
            await send_state_message(
                bot, str(callback.message.chat.id), state,
                RepairBookingStates.AwaitingTime,
                "Выберите <b>время</b> для записи: ⏰",
                reply_markup=time_slots
            )
            await callback.answer()
    except ValueError:
        data = await state.get_data()
        week_offset = data.get("week_offset", 0)
        await send_state_message(
            bot, str(callback.message.chat.id), state,
            RepairBookingStates.AwaitingDate,
            "Некорректная дата. Выберите снова: 📅",
            reply_markup=Keyboards.calendar_kb(week_offset=week_offset)
        )
        await callback.answer()

@repair_booking_router.callback_query(RepairBookingStates.AwaitingTime, F.data.startswith("prev_slots_"))
async def prev_slots_selection(callback: CallbackQuery, state: FSMContext):
    """Обрабатывает переход к предыдущим временным слотам."""
    time_offset = int(callback.data.replace("prev_slots_", ""))
    data = await state.get_data()
    selected_date = data.get("selected_date")
    await state.update_data(time_offset=time_offset)
    with Session() as session:
        await callback.message.edit_reply_markup(
            reply_markup=Keyboards.time_slots_kb(selected_date, 60, session, time_offset)
        )
    await callback.answer()

@repair_booking_router.callback_query(RepairBookingStates.AwaitingTime, F.data.startswith("next_slots_"))
async def next_slots_selection(callback: CallbackQuery, state: FSMContext):
    """Обрабатывает переход к следующим временным слотам."""
    time_offset = int(callback.data.replace("next_slots_", ""))
    data = await state.get_data()
    selected_date = data.get("selected_date")
    await state.update_data(time_offset=time_offset)
    with Session() as session:
        await callback.message.edit_reply_markup(
            reply_markup=Keyboards.time_slots_kb(selected_date, 60, session, time_offset)
        )
    await callback.answer()

@repair_booking_router.callback_query(RepairBookingStates.AwaitingTime, F.data.startswith("time_"))
async def process_time_selection(callback: CallbackQuery, state: FSMContext, bot: Bot):
    """Обрабатывает выбор времени."""
    time_str = callback.data.replace("time_", "")
    try:
        selected_time = datetime.strptime(time_str, "%H:%M").time()
        data = await state.get_data()
        with Session() as session:
            user = session.query(User).filter_by(telegram_id=str(callback.from_user.id)).first()
            auto = session.query(Auto).get(data["auto_id"])
            if not auto:
                await handle_error(
                    callback, state, bot,
                    "Автомобиль не найден. Начните заново. 🚗",
                    f"Автомобиль не найден для auto_id={data['auto_id']}",
                    Exception("Автомобиль не найден")
                )
                await callback.answer()
                return
            booking = Booking(
                user_id=user.id,
                auto_id=data["auto_id"],
                service_name="Ремонт: " + data["description"],
                date=data["selected_date"].date(),
                time=selected_time,
                status=BookingStatus.PENDING,
                price=0,  # Цена будет определена мастером
                created_at=datetime.utcnow()
            )
            session.add(booking)
            session.commit()
            logger.info(f"Запись на ремонт создана: {booking.id} для пользователя {callback.from_user.id}")
            # Отправка фотографий мастеру
            photos = data.get("photos", [])
            if photos:
                for photo_id in photos:
                    await bot.send_photo(
                        chat_id=ADMIN_ID,
                        photo=photo_id,
                        caption=f"Фото для записи #{booking.id}"
                    )
            success = await notify_master(bot, booking, user, auto)
            if not success:
                logger.warning(f"Не удалось уведомить мастера о записи booking_id={booking.id}")
            asyncio.create_task(schedule_reminder(bot, booking, user, auto))
            asyncio.create_task(schedule_user_reminder(bot, booking, user, auto))
            keyboard = InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="Отменить запись ❌", callback_data=f"cancel_booking_{booking.id}")
            ]])
            sent_message = await send_message(
                bot, str(callback.message.chat.id), "text",
                f"Ваша заявка на ремонт отправлена мастеру. Ожидайте подтверждения. ⏳\n"
                f"<b>Описание:</b> {data['description']} 🔧",
                reply_markup=keyboard
            )
            if sent_message:
                await state.update_data(last_message_id=sent_message.message_id)
            await state.clear()
            await callback.answer()
    except Exception as e:
        await handle_error(callback, state, bot, "Ошибка записи. Попробуйте снова. 😔", "Ошибка создания записи на ремонт", e)
        await callback.answer()

@repair_booking_router.callback_query(F.data == "cancel")
async def cancel_action(callback: CallbackQuery, state: FSMContext, bot: Bot):
    """Отменяет процесс бронирования."""
    sent_message = await send_message(
        bot, str(callback.message.chat.id), "text",
        "Действие отменено. ❌",
        reply_markup=Keyboards.main_menu_kb()
    )
    if sent_message:
        await state.update_data(last_message_id=sent_message.message_id)
    await state.clear()
    await callback.answer()

@repair_booking_router.callback_query(F.data.startswith("confirm_booking_"))
@master_only
async def confirm_booking(callback: CallbackQuery, state: FSMContext, bot: Bot):
    """Мастер подтверждает запись."""
    booking_id = int(callback.data.replace("confirm_booking_", ""))
    try:
        with Session() as session:
            booking, user, auto = await get_booking_context(session, booking_id, bot, callback, state)
            if not booking:
                await callback.answer()
                return
            booking.status = BookingStatus.CONFIRMED
            session.commit()
            success = await send_booking_notification(
                bot, user.telegram_id, booking, user, auto,
                "Ваша запись на ремонт подтверждена! ✅"
            )
            if not success:
                logger.warning(f"Не удалось уведомить пользователя user_id={user.telegram_id} о подтверждении записи booking_id={booking_id}")
            await callback.message.edit_text(
                callback.message.text + "\n<b>Статус:</b> Подтверждено ✅",
                parse_mode="HTML"
            )
            await callback.answer("Запись подтверждена. ✅")
    except Exception as e:
        await handle_error(callback, state, bot, "Ошибка. Попробуйте снова. 😔", f"Ошибка подтверждения записи booking_id={booking_id}", e)
        await callback.answer()

@repair_booking_router.callback_query(F.data.startswith("reschedule_booking_"))
@master_only
async def reschedule_booking(callback: CallbackQuery, state: FSMContext, bot: Bot):
    """Мастер предлагает другое время."""
    booking_id = int(callback.data.replace("reschedule_booking_", ""))
    try:
        with Session() as session:
            booking, _, _ = await get_booking_context(session, booking_id, bot, callback, state)
            if not booking:
                await callback.answer()
                return
        await state.update_data(booking_id=booking_id, master_action="reschedule")
        sent_message = await send_message(
            bot, str(callback.message.chat.id), "text",
            "Введите новое <b>время</b> (например, <b>14:30</b>): ⏰"
        )
        if sent_message:
            await state.update_data(last_message_id=sent_message.message_id)
            await state.set_state(RepairBookingStates.AwaitingMasterTime)
            logger.info(f"Мастер запросил новое время для записи booking_id={booking_id}")
        await callback.answer()
    except Exception as e:
        await handle_error(callback, state, bot, "Ошибка. Попробуйте снова. 😔", f"Ошибка переноса записи booking_id={booking_id}", e)
        await callback.answer()

@repair_booking_router.message(RepairBookingStates.AwaitingMasterTime, F.text)
@master_only
async def process_master_time(message: Message, state: FSMContext, bot: Bot):
    """Обрабатывает ввод нового времени мастером."""
    data = await state.get_data()
    if "booking_id" not in data or "master_action" not in data or data["master_action"] != "reschedule":
        await handle_error(
            message, state, bot,
            "Ошибка: данные состояния отсутствуют. Попробуйте снова. 😔",
            "Некорректные данные состояния FSM",
            Exception("Некорректные данные состояния")
        )
        return
    booking_id = data.get("booking_id")
    time_str = message.text.strip()
    if not re.match(r"^(?:[01]\d|2[0-3]):[0-5]\d$", time_str):
        logger.warning(f"Некорректный формат времени '{time_str}' для записи booking_id={booking_id}")
        sent_message = await send_message(
            bot, str(message.chat.id), "text",
            "Некорректный формат времени. Введите снова (например, <b>14:30</b>): ⏰"
        )
        if sent_message:
            await state.update_data(last_message_id=sent_message.message_id)
        return
    try:
        with Session() as session:
            booking, user, auto = await get_booking_context(session, booking_id, bot, message, state)
            if not booking:
                return
            new_time = datetime.strptime(time_str, "%H:%M").time()
            # Проверка доступности времени
            time_slots = Keyboards.time_slots_kb(booking.date, 60, session)
            available_times = [btn.callback_data.replace("time_", "") for row in time_slots.inline_keyboard for btn in row if btn.callback_data.startswith("time_")]
            if time_str not in available_times:
                sent_message = await send_message(
                    bot, str(message.chat.id), "text",
                    "Это время занято. Введите другое время (например, <b>14:30</b>): ⏰"
                )
                if sent_message:
                    await state.update_data(last_message_id=sent_message.message_id)
                return
            booking.proposed_time = new_time
            booking.status = BookingStatus.PENDING
            session.commit()
            success = await send_booking_notification(
                bot, user.telegram_id, booking, user, auto,
                f"Мастер предложил новое время для записи:\n<b>Новое время:</b> {new_time.strftime('%H:%M')} ⏰",
                Keyboards.confirm_reschedule_kb(booking_id)
            )
            if success:
                sent_message = await send_message(
                    bot, str(message.chat.id), "text",
                    "Новое время отправлено пользователю. Ожидается подтверждение. ⏳"
                )
                if sent_message:
                    await state.update_data(last_message_id=sent_message.message_id)
            await state.clear()
    except Exception as e:
        await handle_error(
            message, state, bot,
            "Критическая ошибка. Попробуйте снова. 😔",
            f"Ошибка обработки нового времени для записи booking_id={booking_id}",
            e
        )

@repair_booking_router.callback_query(F.data.startswith("reject_booking_"))
@master_only
async def reject_booking(callback: CallbackQuery, state: FSMContext, bot: Bot):
    """Мастер отклоняет запись."""
    booking_id = int(callback.data.replace("reject_booking_", ""))
    try:
        with Session() as session:
            booking, _, _ = await get_booking_context(session, booking_id, bot, callback, state)
            if not booking:
                await callback.answer()
                return
        await state.update_data(booking_id=booking_id, master_action="reject")
        sent_message = await send_message(
            bot, str(callback.message.chat.id), "text",
            "Введите <b>причину</b> отказа: 📝"
        )
        if sent_message:
            await state.update_data(last_message_id=sent_message.message_id)
            await state.set_state(RepairBookingStates.AwaitingMasterResponse)
            logger.info(f"Мастер запросил причину отказа для записи booking_id={booking_id}")
        await callback.answer()
    except Exception as e:
        await handle_error(callback, state, bot, "Ошибка. Попробуйте снова. 😔", f"Ошибка отклонения записи booking_id={booking_id}", e)
        await callback.answer()

@repair_booking_router.message(RepairBookingStates.AwaitingMasterResponse, F.text)
@master_only
async def process_master_rejection(message: Message, state: FSMContext, bot: Bot):
    """Обрабатывает причину отказа мастера."""
    data = await state.get_data()
    if "booking_id" not in data or "master_action" not in data or data["master_action"] != "reject":
        await handle_error(
            message, state, bot,
            "Ошибка: данные состояния отсутствуют. Попробуйте снова. 😔",
            "Некорректные данные состояния FSM",
            Exception("Некорректные данные состояния")
        )
        return
    booking_id = data.get("booking_id")
    try:
        with Session() as session:
            booking, user, auto = await get_booking_context(session, booking_id, bot, message, state)
            if not booking:
                return
            booking.status = BookingStatus.REJECTED
            booking.rejection_reason = message.text
            session.commit()
            success = await send_booking_notification(
                bot, user.telegram_id, booking, user, auto,
                f"Ваша запись на ремонт отклонена. ❌\n<b>Причина:</b> {message.text} 📝"
            )
            if success:
                sent_message = await send_message(
                    bot, str(message.chat.id), "text",
                    "Отказ отправлен пользователю. ✅"
                )
                if sent_message:
                    await state.update_data(last_message_id=sent_message.message_id)
            await state.clear()
    except Exception as e:
        await handle_error(
            message, state, bot,
            "Критическая ошибка. Попробуйте снова. 😔",
            f"Ошибка обработки отказа для записи booking_id={booking_id}",
            e
        )

@repair_booking_router.callback_query(F.data.startswith("confirm_reschedule_"))
async def process_user_confirmation(callback: CallbackQuery, state: FSMContext, bot: Bot):
    """Обрабатывает подтверждение пользователем нового времени."""
    booking_id = int(callback.data.replace("confirm_reschedule_", ""))
    try:
        with Session() as session:
            booking, user, auto = await get_booking_context(session, booking_id, bot, callback, state)
            if not booking:
                await callback.answer()
                return
            if str(callback.from_user.id) != str(booking.user.telegram_id):
                logger.warning(f"Несанкционированный доступ: user_id={callback.from_user.id} != telegram_id={booking.user.telegram_id}")
                await callback.answer("Доступ только для владельца записи. 🔒")
                return
            if not booking.proposed_time:
                await handle_error(
                    callback, state, bot,
                    "Ошибка: предложенное время не найдено. ⏰",
                    f"Предложенное время не найдено для booking_id={booking_id}",
                    Exception("Предложенное время не найдено")
                )
                await callback.answer()
                return
            booking.time = booking.proposed_time
            booking.proposed_time = None
            booking.status = BookingStatus.CONFIRMED
            session.commit()
            success = await send_booking_notification(
                bot, ADMIN_ID, booking, user, auto,
                f"Пользователь {user.first_name} {user.last_name} подтвердил запись на ремонт: ✅"
            )
            if not success:
                logger.warning(f"Не удалось уведомить мастера о подтверждении записи booking_id={booking_id}")
            sent_message = await send_message(
                bot, str(callback.message.chat.id), "text",
                f"Вы подтвердили запись на ремонт: ✅\n"
                f"<b>Описание:</b> {booking.service_name.replace('Ремонт: ', '')} 🔧\n"
                f"<b>Дата:</b> {booking.date.strftime('%d.%m.%Y')} 📅\n"
                f"<b>Время:</b> {booking.time.strftime('%H:%M')} ⏰\n"
                f"<b>Авто:</b> {auto.brand}, {auto.year}, {auto.license_plate} 🚗",
                reply_markup=Keyboards.main_menu_kb()
            )
            if sent_message:
                await state.update_data(last_message_id=sent_message.message_id)
            await callback.answer("Запись подтверждена. ✅")
            await state.clear()
    except Exception as e:
        await handle_error(
            callback, state, bot,
            "Ошибка. Попробуйте снова. 😔",
            f"Ошибка подтверждения переноса для записи booking_id={booking_id}",
            e
        )
        await callback.answer()

@repair_booking_router.callback_query(F.data.startswith("reject_reschedule_"))
async def process_user_rejection(callback: CallbackQuery, state: FSMContext, bot: Bot):
    """Обрабатывает отклонение пользователем нового времени."""
    booking_id = int(callback.data.replace("reject_reschedule_", ""))
    try:
        with Session() as session:
            booking, user, auto = await get_booking_context(session, booking_id, bot, callback, state)
            if not booking:
                await callback.answer()
                return
            if str(callback.from_user.id) != str(booking.user.telegram_id):
                logger.warning(f"Несанкционированный доступ: user_id={callback.from_user.id} != telegram_id={booking.user.telegram_id}")
                await callback.answer("Доступ только для владельца записи. 🔒")
                return
            booking.status = BookingStatus.REJECTED
            booking.rejection_reason = "Пользователь отклонил предложенное время"
            booking.proposed_time = None
            session.commit()
            success = await send_booking_notification(
                bot, ADMIN_ID, booking, user, auto,
                f"Пользователь {user.first_name} {user.last_name} отклонил запись на ремонт:\n<b>Причина:</b> Пользователь отклонил предложенное время 📝"
            )
            if not success:
                logger.warning(f"Не удалось уведомить мастера об отклонении записи booking_id={booking_id}")
            sent_message = await send_message(
                bot, str(callback.message.chat.id), "text",
                f"Вы отклонили предложенное время для записи: ❌\n"
                f"<b>Описание:</b> {booking.service_name.replace('Ремонт: ', '')} 🔧\n"
                f"<b>Дата:</b> {booking.date.strftime('%d.%m.%Y')} 📅\n"
                f"<b>Авто:</b> {auto.brand}, {auto.year}, {auto.license_plate} 🚗",
                reply_markup=Keyboards.main_menu_kb()
            )
            if sent_message:
                await state.update_data(last_message_id=sent_message.message_id)
            await callback.answer("Запись отклонена. ❌")
            await state.clear()
    except Exception as e:
        await handle_error(
            callback, state, bot,
            "Ошибка. Попробуйте снова. 😔",
            f"Ошибка отклонения переноса для записи booking_id={booking_id}",
            e
        )
        await callback.answer()

@repair_booking_router.callback_query(F.data.startswith("cancel_booking_"))
async def process_booking_cancellation(callback: CallbackQuery, state: FSMContext, bot: Bot):
    """Обрабатывает отмену записи пользователем."""
    booking_id = int(callback.data.replace("cancel_booking_", ""))
    try:
        with Session() as session:
            booking, user, auto = await get_booking_context(session, booking_id, bot, callback, state)
            if not booking:
                await callback.answer()
                return
            if str(callback.from_user.id) != str(booking.user.telegram_id):
                logger.warning(f"Несанкционированный доступ: user_id={callback.from_user.id} != telegram_id={booking.user.telegram_id}")
                await callback.answer("Доступ только для владельца записи. 🔒")
                return
            booking.status = BookingStatus.CANCELLED
            booking.rejection_reason = "Отменено пользователем"
            session.commit()
            reminder_manager.cancel(booking_id)
            success = await send_booking_notification(
                bot, ADMIN_ID, booking, user, auto,
                f"Пользователь {user.first_name} {user.last_name} отменил запись на ремонт: ❌"
            )
            if not success:
                logger.warning(f"Не удалось уведомить мастера об отмене записи booking_id={booking_id}")
            sent_message = await send_message(
                bot, str(callback.message.chat.id), "text",
                f"Вы отменили запись на ремонт: ❌\n"
                f"<b>Описание:</b> {booking.service_name.replace('Ремонт: ', '')} 🔧\n"
                f"<b>Дата:</b> {booking.date.strftime('%d.%m.%Y')} 📅\n"
                f"<b>Время:</b> {booking.time.strftime('%H:%M')} ⏰",
                reply_markup=Keyboards.main_menu_kb()
            )
            if sent_message:
                await state.update_data(last_message_id=sent_message.message_id)
            await callback.answer("Запись отменена. ❌")
            await state.clear()
    except Exception as e:
        await handle_error(
            callback, state, bot,
            "Ошибка. Попробуйте снова. 😔",
            f"Ошибка отмены записи booking_id={booking_id}",
            e
        )
        await callback.answer()
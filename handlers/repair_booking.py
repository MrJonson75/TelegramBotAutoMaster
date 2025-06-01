from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from config import get_photo_path, ADMIN_ID
from keyboards.main_kb import Keyboards
from database import User, Auto, Booking, BookingStatus, Session
from datetime import datetime
import asyncio
import re
from .states import RepairBookingStates, REPAIR_PROGRESS_STEPS
from utils import (
    get_progress_bar, send_message, handle_error, check_user_and_autos,
    master_only, get_booking_context, send_booking_notification, set_user_state,
    notify_master, schedule_reminder, schedule_user_reminder, setup_logger, process_user_input
)

repair_booking_router = Router()
logger = setup_logger(__name__)

@repair_booking_router.message(F.text == "Запись на ремонт")
async def start_repair_booking(message: Message, state: FSMContext, bot: Bot):
    """Запускает процесс записи на ремонт."""
    logger.info(f"Пользователь {message.from_user.id} начал запись на ремонт")
    try:
        with Session() as session:
            user, autos = await check_user_and_autos(session, str(message.from_user.id), bot, message, state, "booking_repair")
            if not user:
                logger.debug(f"Пользователь {message.from_user.id} не зарегистрирован, обработка завершена")
                return
            if autos:
                response = (await get_progress_bar(RepairBookingStates.AwaitingAuto, REPAIR_PROGRESS_STEPS, style="emoji")).format(
                    message="Выберите автомобиль для записи на ремонт: 🚗"
                )
                try:
                    sent_message = await send_message(
                        bot, str(message.chat.id), "photo",
                        response,
                        photo=get_photo_path("booking"),
                        reply_markup=Keyboards.auto_selection_kb(autos)
                    )
                except FileNotFoundError as e:
                    logger.error(f"Фото booking не найдено: {str(e)}. Отправлено текстовое сообщение.")
                    sent_message = await send_message(
                        bot, str(message.chat.id), "text",
                        response,
                        reply_markup=Keyboards.auto_selection_kb(autos)
                    )
                if sent_message:
                    await state.update_data(last_message_id=sent_message.message_id)
                    await state.set_state(RepairBookingStates.AwaitingAuto)
            else:
                sent_message = await send_message(
                    bot, str(message.chat.id), "text",
                    "У вас нет зарегистрированных автомобилей. Добавьте автомобиль в личном кабинете. 🚗",
                    reply_markup=Keyboards.profile_menu_kb()
                )
                if sent_message:
                    await state.update_data(last_message_id=sent_message.message_id)
                await state.clear()
    except Exception as e:
        logger.error(f"Неизвестная ошибка в start_repair_booking для user_id={message.from_user.id}: {str(e)}")
        await handle_error(message, state, bot,
                           "Ошибка. Попробуйте снова. 😔",
                           "Ошибка в start_repair_booking", e)

@repair_booking_router.callback_query(RepairBookingStates.AwaitingAuto, F.data.startswith("auto_"))
async def process_auto_selection(callback: CallbackQuery, state: FSMContext, bot: Bot):
    """Обрабатывает выбор автомобиля."""
    auto_id = int(callback.data.replace("auto_", ""))
    try:
        with Session() as session:
            auto = session.query(Auto).get(auto_id)
            if not auto:
                await handle_error(callback, state, bot,
                                   "Автомобиль не найден. Попробуйте снова. 🚗",
                                   f"Автомобиль не найден для auto_id={auto_id}",
                                   Exception("Автомобиль не найден"))
                await callback.answer()
                return
            await state.update_data(auto_id=auto_id, photos=[])
            response = (await get_progress_bar(RepairBookingStates.AwaitingProblemDescription, REPAIR_PROGRESS_STEPS, style="emoji")).format(
                message="Опишите проблему с автомобилем (например, 'стук в подвеске'): 🔧"
            )
            try:
                sent_message = await send_message(
                    bot, str(callback.message.chat.id), "photo",
                    response,
                    photo=get_photo_path("repair_description")
                )
            except FileNotFoundError as e:
                logger.error(f"Фото repair_description не найдено: {str(e)}. Отправлено текстовое сообщение.")
                sent_message = await send_message(
                    bot, str(callback.message.chat.id), "text",
                    response
                )
            if sent_message:
                await state.update_data(last_message_id=sent_message.message_id)
                await state.set_state(RepairBookingStates.AwaitingProblemDescription)
            await callback.answer()
    except Exception as e:
        await handle_error(callback, state, bot,
                           "Ошибка. Попробуйте снова. 😔",
                           "Ошибка выбора автомобиля", e)
        await callback.answer()

@repair_booking_router.message(RepairBookingStates.AwaitingProblemDescription, F.text)
async def process_problem_description(message: Message, state: FSMContext, bot: Bot):
    """Обрабатывает описание проблемы."""
    def validate_description(text: str) -> str:
        text = text.strip()
        if len(text) < 5:
            raise ValueError("Описание слишком короткое")
        if len(text) > 500:
            raise ValueError("Описание слишком длинное")
        return text

    await process_user_input(
        message, state, bot,
        validate_description, "problem_description",
        "Описание принято! Теперь вы можете загрузить до 3 фотографий для диагностики 📸 или пропустить этот шаг.",
        "Описание должно быть от 5 до 500 символов. Попробуйте снова: 🔧",
        RepairBookingStates.AwaitingPhotos,
        REPAIR_PROGRESS_STEPS,
        reply_markup=Keyboards.photo_upload_kb()
    )

@repair_booking_router.message(RepairBookingStates.AwaitingPhotos, F.photo)
async def process_photo_upload(message: Message, state: FSMContext, bot: Bot):
    """Обрабатывает загрузку фотографий."""
    data = await state.get_data()
    photos = data.get("photos", [])
    if len(photos) >= 3:
        sent_message = await send_message(
            bot, str(message.chat.id), "text",
            (await get_progress_bar(RepairBookingStates.AwaitingPhotos, REPAIR_PROGRESS_STEPS, style="emoji")).format(
                message="Максимум 3 фотографии. Нажмите 'Готово' или 'Пропустить'. 📸"
            ),
            reply_markup=Keyboards.photo_upload_kb()
        )
        if sent_message:
            await state.update_data(last_message_id=sent_message.message_id)
        return
    photos.append(message.photo[-1].file_id)
    await state.update_data(photos=photos)
    remaining = 3 - len(photos)
    sent_message = await send_message(
        bot, str(message.chat.id), "text",
        (await get_progress_bar(RepairBookingStates.AwaitingPhotos, REPAIR_PROGRESS_STEPS, style="emoji")).format(
            message=f"Фотография загружена! Осталось {remaining} фото. Загрузите ещё или нажмите 'Готово'/'Пропустить'. 📸"
        ),
        reply_markup=Keyboards.photo_upload_kb()
    )
    if sent_message:
        await state.update_data(last_message_id=sent_message.message_id)

@repair_booking_router.callback_query(RepairBookingStates.AwaitingPhotos, F.data == "photos_ready")
async def photos_ready(callback: CallbackQuery, state: FSMContext, bot: Bot):
    """Обрабатывает завершение загрузки фотографий."""
    await state.update_data(service_name="Ремонт", service_duration=60, week_offset=0)
    response = (await get_progress_bar(RepairBookingStates.AwaitingDate, REPAIR_PROGRESS_STEPS, style="emoji")).format(
        message="Выберите <b>дату</b> для записи на ремонт: 📅"
    )
    sent_message = await send_message(
        bot, str(callback.message.chat.id), "text",
        response,
        reply_markup=Keyboards.calendar_kb()
    )
    if sent_message:
        await state.update_data(last_message_id=sent_message.message_id)
        await state.set_state(RepairBookingStates.AwaitingDate)
    await callback.answer()

@repair_booking_router.callback_query(RepairBookingStates.AwaitingPhotos, F.data == "skip_photos")
async def skip_photos(callback: CallbackQuery, state: FSMContext, bot: Bot):
    """Обрабатывает пропуск загрузки фотографий."""
    await state.update_data(photos=[], service_name="Ремонт", service_duration=60, week_offset=0)
    response = (await get_progress_bar(RepairBookingStates.AwaitingDate, REPAIR_PROGRESS_STEPS, style="emoji")).format(
        message="Выберите <b>дату</b> для записи на ремонт: 📅"
    )
    sent_message = await send_message(
        bot, str(callback.message.chat.id), "text",
        response,
        reply_markup=Keyboards.calendar_kb()
    )
    if sent_message:
        await state.update_data(last_message_id=sent_message.message_id)
        await state.set_state(RepairBookingStates.AwaitingDate)
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
            time_slots = Keyboards.time_slots_kb(selected_date, data["service_duration"], session)
            if not time_slots.inline_keyboard:
                sent_message = await send_message(
                    bot, str(callback.message.chat.id), "text",
                    (await get_progress_bar(RepairBookingStates.AwaitingDate, REPAIR_PROGRESS_STEPS, style="emoji")).format(
                        message="Нет доступных слотов на эту дату. Выберите другую дату: 📅"
                    ),
                    reply_markup=Keyboards.calendar_kb(selected_date, week_offset)
                )
                if sent_message:
                    await state.update_data(last_message_id=sent_message.message_id)
                await callback.answer()
                return
            await state.update_data(selected_date=selected_date, time_offset=0)
            sent_message = await send_message(
                bot, str(callback.message.chat.id), "text",
                (await get_progress_bar(RepairBookingStates.AwaitingTime, REPAIR_PROGRESS_STEPS, style="emoji")).format(
                    message="Выберите <b>время</b> для записи: ⏰"
                ),
                reply_markup=time_slots
            )
            if sent_message:
                await state.update_data(last_message_id=sent_message.message_id)
                await state.set_state(RepairBookingStates.AwaitingTime)
            await callback.answer()
    except ValueError:
        data = await state.get_data()
        week_offset = data.get("week_offset", 0)
        sent_message = await send_message(
            bot, str(callback.message.chat.id), "text",
            (await get_progress_bar(RepairBookingStates.AwaitingDate, REPAIR_PROGRESS_STEPS, style="emoji")).format(
                message="Некорректная дата. Выберите снова: 📅"
            ),
            reply_markup=Keyboards.calendar_kb(week_offset=week_offset)
        )
        if sent_message:
            await state.update_data(last_message_id=sent_message.message_id)
        await callback.answer()

@repair_booking_router.callback_query(RepairBookingStates.AwaitingTime, F.data.startswith("prev_slots_"))
async def prev_slots_selection(callback: CallbackQuery, state: FSMContext):
    """Обрабатывает переход к предыдущим временным слотам."""
    time_offset = int(callback.data.replace("prev_slots_", ""))
    data = await state.get_data()
    selected_date = data.get("selected_date")
    service_duration = data.get("service_duration")
    await state.update_data(time_offset=time_offset)
    with Session() as session:
        await callback.message.edit_reply_markup(
            reply_markup=Keyboards.time_slots_kb(selected_date, service_duration, session, time_offset)
        )
    await callback.answer()

@repair_booking_router.callback_query(RepairBookingStates.AwaitingTime, F.data.startswith("next_slots_"))
async def next_slots_selection(callback: CallbackQuery, state: FSMContext):
    """Обрабатывает переход к следующим временным слотам."""
    time_offset = int(callback.data.replace("next_slots_", ""))
    data = await state.get_data()
    selected_date = data.get("selected_date")
    service_duration = data.get("service_duration")
    await state.update_data(time_offset=time_offset)
    with Session() as session:
        await callback.message.edit_reply_markup(
            reply_markup=Keyboards.time_slots_kb(selected_date, service_duration, session, time_offset)
        )
    await callback.answer()

@repair_booking_router.callback_query(RepairBookingStates.AwaitingTime, F.data.startswith("time_"))
async def process_time_selection(callback: CallbackQuery, state: FSMContext, bot: Bot):
    """Обрабатывает выбор времени и создает запись."""
    time_str = callback.data.replace("time_", "")
    try:
        selected_time = datetime.strptime(time_str, "%H:%M").time()
        data = await state.get_data()
        photos = data.get("photos", [])
        with Session() as session:
            user = session.query(User).filter_by(telegram_id=str(callback.from_user.id)).first()
            auto = session.query(Auto).get(data["auto_id"])
            if not auto:
                await handle_error(callback, state, bot,
                                   "Автомобиль не найден. Начните заново. 🚗",
                                   f"Автомобиль не найден для auto_id={data['auto_id']}",
                                   Exception("Автомобиль не найден"))
                await callback.answer()
                return
            booking = Booking(
                user_id=user.id,
                auto_id=data["auto_id"],
                service_name="Ремонт",
                problem_description=data.get("problem_description", ""),
                photo1=photos[0] if photos else None,
                photo2=photos[1] if len(photos) > 1 else None,
                photo3=photos[2] if len(photos) > 2 else None,
                date=data["selected_date"].date(),
                time=selected_time,
                status=BookingStatus.PENDING
            )
            session.add(booking)
            session.commit()
            logger.info(f"Запись на ремонт создана: booking_id={booking.id}, user_id={callback.from_user.id}")
            notification_text = (
                f"Новая запись на ремонт #{booking.id} ожидает оценки: 📝\n"
                f"<b>Описание проблемы:</b> {data.get('problem_description', 'Не указано')}\n"
                f"<b>Авто:</b> {auto.brand}, {auto.year}, {auto.license_plate}\n"
                f"<b>Дата:</b> {booking.date.strftime('%d.%m.%Y')}\n"
                f"<b>Время:</b> {booking.time.strftime('%H:%M')}"
            )
            keyboard = InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="Оценить ремонт 🔧", callback_data=f"evaluate_booking_{booking.id}"),
                InlineKeyboardButton(text="Отказаться ❌", callback_data=f"reject_booking_{booking.id}")
            ]])
            success = await send_message(
                bot, ADMIN_ID, "text",
                notification_text,
                reply_markup=keyboard
            )
            if not success:
                logger.error(f"Не удалось уведомить мастера о записи booking_id={booking.id}, user_id={callback.from_user.id}")
            if photos:
                for i, photo_id in enumerate(photos, 1):
                    await bot.send_photo(
                        chat_id=ADMIN_ID,
                        photo=photo_id,
                        caption=f"Фото {i} для записи #{booking.id}"
                    )
            sent_message = await send_message(
                bot, str(callback.message.chat.id), "text",
                f"Ваша заявка на ремонт отправлена мастеру. Ожидайте оценки стоимости и времени. ⏳\n"
                f"<b>Проблема:</b> {data.get('problem_description', 'Не указано')} 🔧",
                reply_markup=Keyboards.main_menu_kb()
            )
            if sent_message:
                await state.update_data(last_message_id=sent_message.message_id)
            await state.clear()
            await callback.answer()
    except Exception as e:
        await handle_error(callback, state, bot,
                           "Ошибка записи. Попробуйте снова. 😔",
                           f"Ошибка создания записи на ремонт booking_id={booking.id if 'booking' in locals() else 'unknown'}", e)
        await callback.answer()

@repair_booking_router.callback_query(F.data.startswith("evaluate_booking_"))
@master_only
async def evaluate_booking(callback: CallbackQuery, state: FSMContext, bot: Bot):
    """Мастер оценивает стоимость и время ремонта."""
    booking_id = int(callback.data.replace("evaluate_booking_", ""))
    try:
        with Session() as session:
            booking, _, _ = await get_booking_context(session, booking_id, bot, callback, state)
            if not booking:
                await callback.answer()
                return
        await state.update_data(booking_id=booking_id, master_action="evaluate")
        sent_message = await send_message(
            bot, str(callback.message.chat.id), "text",
            "Введите <b>стоимость</b> ремонта (в рублях, например, 5000) и <b>длительность</b> (в часах, например, 2): ⏰\n"
            "Формат: <b>5000 2</b>"
        )
        if sent_message:
            await state.update_data(last_message_id=sent_message.message_id)
            await state.set_state(RepairBookingStates.AwaitingMasterEvaluation)
        await callback.answer()
    except Exception as e:
        await handle_error(callback, state, bot,
                           "Ошибка. Попробуйте снова. 😔",
                           f"Ошибка оценки записи booking_id={booking_id}", e)
        await callback.answer()

@repair_booking_router.message(RepairBookingStates.AwaitingMasterEvaluation, F.text)
@master_only
async def process_master_evaluation(message: Message, state: FSMContext, bot: Bot):
    """Обрабатывает ввод стоимости и длительности мастером."""
    data = await state.get_data()
    booking_id = data.get("booking_id")
    if not booking_id or data.get("master_action") != "evaluate":
        await handle_error(message, state, bot,
                           "Ошибка: данные состояния отсутствуют. Попробуйте снова. 😔",
                           "Некорректные данные состояния FSM", Exception("Некорректные данные состояния"))
        return
    try:
        cost, hours = map(float, message.text.strip().split())
        if cost < 0 or hours <= 0:
            raise ValueError("Стоимость и длительность должны быть положительными")
        duration = int(hours * 60)  # Конвертация часов в минуты
        with Session() as session:
            booking, _, _ = await get_booking_context(session, booking_id, bot, message, state)
            if not booking:
                return
            await state.update_data(cost=cost, duration=duration)
            sent_message = await send_message(
                bot, str(message.chat.id), "text",
                f"Текущее время записи: {booking.time.strftime('%H:%M')}. Хотите изменить время? ⏰",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="Оставить текущее время ✅", callback_data=f"keep_time_{booking_id}")],
                    [InlineKeyboardButton(text="Выбрать новое время ⏰", callback_data=f"change_time_{booking_id}")]
                ])
            )
            if sent_message:
                await state.update_data(last_message_id=sent_message.message_id)
            await state.set_state(RepairBookingStates.AwaitingMasterTimeSelection)
    except ValueError as e:
        logger.warning(f"Некорректный формат ввода для booking_id={booking_id}: {str(e)}")
        sent_message = await send_message(
            bot, str(message.chat.id), "text",
            "Ошибка: формат 'стоимость длительность' (например, '5000 2'). Повторите ввод: ⏰"
        )
        if sent_message:
            await state.update_data(last_message_id=sent_message.message_id)
    except Exception as e:
        await handle_error(message, state, bot,
                           "Критическая ошибка. Попробуйте снова. 😔",
                           f"Ошибка обработки оценки для booking_id={booking_id}", e)

@repair_booking_router.callback_query(RepairBookingStates.AwaitingMasterTimeSelection, F.data.startswith("keep_time_"))
@master_only
async def keep_time(callback: CallbackQuery, state: FSMContext, bot: Bot):
    """Мастер оставляет текущее время."""
    booking_id = int(callback.data.replace("keep_time_", ""))
    try:
        data = await state.get_data()
        cost = data.get("cost")
        duration = data.get("duration")
        with Session() as session:
            booking, user, auto = await get_booking_context(session, booking_id, bot, callback, state)
            if not booking:
                await callback.answer()
                return
            booking.cost = cost
            booking.service_duration = duration
            session.commit()
            notification_text = (
                f"Мастер оценил ремонт #{booking_id}:\n"
                f"<b>Стоимость:</b> {cost:.2f} руб.\n"
                f"<b>Длительность:</b> {duration // 60} ч.\n"
                f"<b>Дата:</b> {booking.date.strftime('%d.%m.%Y')}\n"
                f"<b>Время:</b> {booking.time.strftime('%H:%M')}\n"
                f"<b>Проблема:</b> {booking.problem_description or 'Не указано'}"
            )
            keyboard = InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="Подтвердить ✅", callback_data=f"confirm_booking_{booking_id}"),
                InlineKeyboardButton(text="Отказаться ❌", callback_data=f"reject_booking_{booking_id}")
            ]])
            success = await send_booking_notification(
                bot, user.telegram_id, booking, user, auto,
                notification_text,
                keyboard
            )
            if not success:
                logger.error(f"Не удалось уведомить пользователя о оценке booking_id={booking_id}, user_id={user.telegram_id}")
            sent_message = await send_message(
                bot, str(callback.message.chat.id), "text",
                f"Оценка отправлена пользователю: {cost:.2f} руб., {duration // 60} ч. Ожидается подтверждение. ⏳"
            )
            if sent_message:
                await state.update_data(last_message_id=sent_message.message_id)
            await state.clear()
        await callback.answer()
    except Exception as e:
        await handle_error(callback, state, bot,
                           "Ошибка. Попробуйте снова. 😔",
                           f"Ошибка сохранения времени для booking_id={booking_id}", e)
        await callback.answer()

@repair_booking_router.callback_query(RepairBookingStates.AwaitingMasterTimeSelection, F.data.startswith("change_time_"))
@master_only
async def change_time(callback: CallbackQuery, state: FSMContext, bot: Bot):
    """Мастер выбирает новое время."""
    booking_id = int(callback.data.replace("change_time_", ""))
    try:
        sent_message = await send_message(
            bot, str(callback.message.chat.id), "text",
            "Введите новое <b>время</b> (например, <b>14:30</b>): ⏰"
        )
        if sent_message:
            await state.update_data(last_message_id=sent_message.message_id)
            await state.set_state(RepairBookingStates.AwaitingMasterTime)
        await callback.answer()
    except Exception as e:
        await handle_error(callback, state, bot,
                           "Ошибка. Попробуйте снова. 😔",
                           f"Ошибка запроса нового времени для booking_id={booking_id}", e)
        await callback.answer()

@repair_booking_router.message(RepairBookingStates.AwaitingMasterTime, F.text)
@master_only
async def process_master_time(message: Message, state: FSMContext, bot: Bot):
    """Обрабатывает ввод нового времени мастером."""
    data = await state.get_data()
    booking_id = data.get("booking_id")
    cost = data.get("cost")
    duration = data.get("duration")
    if not booking_id or data.get("master_action") != "evaluate":
        await handle_error(message, state, bot,
                           "Ошибка: данные состояния отсутствуют. Попробуйте снова. 😔",
                           "Некорректные данные состояния FSM", Exception("Некорректные данные состояния"))
        return
    time_str = message.text.strip()
    if not re.match(r"^(?:[01]\d|2[0-3]):[0-5]\d$", time_str):
        logger.warning(f"Некорректный формат времени '{time_str}' для booking_id={booking_id}")
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
            booking.time = new_time
            booking.cost = cost
            booking.service_duration = duration
            session.commit()
            notification_text = (
                f"Мастер оценил ремонт #{booking_id}:\n"
                f"<b>Стоимость:</b> {cost:.2f} руб.\n"
                f"<b>Длительность:</b> {duration // 60} ч.\n"
                f"<b>Дата:</b> {booking.date.strftime('%d.%m.%Y')}\n"
                f"<b>Время:</b> {booking.time.strftime('%H:%M')}\n"
                f"<b>Проблема:</b> {booking.problem_description or 'Не указано'}"
            )
            keyboard = InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="Подтвердить ✅", callback_data=f"confirm_booking_{booking_id}"),
                InlineKeyboardButton(text="Отказаться ❌", callback_data=f"reject_booking_{booking_id}")
            ]])
            success = await send_booking_notification(
                bot, user.telegram_id, booking, user, auto,
                notification_text,
                keyboard
            )
            if not success:
                logger.error(f"Не удалось уведомить пользователя о новом времени booking_id={booking_id}, user_id={user.telegram_id}")
            sent_message = await send_message(
                bot, str(message.chat.id), "text",
                f"Оценка отправлена пользователю: {cost:.2f} руб., {duration // 60} ч., время {new_time.strftime('%H:%M')}. Ожидается подтверждение. ⏳"
            )
            if sent_message:
                await state.update_data(last_message_id=sent_message.message_id)
            await state.clear()
    except Exception as e:
        await handle_error(message, state, bot,
                           "Критическая ошибка. Попробуйте снова. 😔",
                           f"Ошибка обработки нового времени для booking_id={booking_id}", e)

@repair_booking_router.callback_query(F.data.startswith("reject_booking_"))
@master_only
async def reject_booking(callback: CallbackQuery, state: FSMContext, bot: Bot):
    """Мастер отказывается от ремонта."""
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
            "Укажите <b>причину</b> отказа от ремонта: 📝"
        )
        if sent_message:
            await state.update_data(last_message_id=sent_message.message_id)
            await state.set_state(RepairBookingStates.AwaitingMasterRejectionReason)
        await callback.answer()
    except Exception as e:
        await handle_error(callback, state, bot,
                           "Ошибка. Попробуйте снова. 😔",
                           f"Ошибка отказа от записи booking_id={booking_id}", e)
        await callback.answer()

@repair_booking_router.message(RepairBookingStates.AwaitingMasterRejectionReason, F.text)
@master_only
async def process_master_rejection(message: Message, state: FSMContext, bot: Bot):
    """Обрабатывает причину отказа мастера."""
    data = await state.get_data()
    booking_id = data.get("booking_id")
    if not booking_id or data.get("master_action") != "reject":
        await handle_error(message, state, bot,
                           "Ошибка: данные состояния отсутствуют. Попробуйте снова. 😔",
                           "Некорректные данные состояния FSM", Exception("Некорректные данные состояния"))
        return
    rejection_reason = message.text.strip()
    if len(rejection_reason) < 5:
        sent_message = await send_message(
            bot, str(message.chat.id), "text",
            "Причина отказа слишком короткая. Укажите подробнее: 📝"
        )
        if sent_message:
            await state.update_data(last_message_id=sent_message.message_id)
        return
    try:
        with Session() as session:
            booking, user, auto = await get_booking_context(session, booking_id, bot, message, state)
            if not booking:
                return
            booking.status = BookingStatus.REJECTED
            booking.rejection_reason = rejection_reason
            session.commit()
            success = await send_booking_notification(
                bot, user.telegram_id, booking, user, auto,
                f"Мастер отказался от ремонта:\n<b>Причина:</b> {rejection_reason} ❌"
            )
            if not success:
                logger.error(f"Не удалось уведомить пользователя об отказе booking_id={booking_id}, user_id={user.telegram_id}")
            sent_message = await send_message(
                bot, str(message.chat.id), "text",
                f"Отказ отправлен пользователю: {rejection_reason}. ❌"
            )
            if sent_message:
                await state.update_data(last_message_id=sent_message.message_id)
            await state.clear()
    except Exception as e:
        await handle_error(message, state, bot,
                           "Критическая ошибка. Попробуйте снова. 😔",
                           f"Ошибка обработки отказа для booking_id={booking_id}", e)

@repair_booking_router.callback_query(F.data.startswith("confirm_booking_"))
async def confirm_booking(callback: CallbackQuery, state: FSMContext, bot: Bot):
    """Пользователь подтверждает запись."""
    booking_id = int(callback.data.replace("confirm_booking_", ""))
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
            booking.status = BookingStatus.CONFIRMED
            session.commit()
            cost = booking.cost or 0
            duration = booking.service_duration or 60
            notification_text = (
                f"Пользователь {user.first_name} {user.last_name} подтвердил запись на ремонт #{booking_id}: ✅\n"
                f"<b>Стоимость:</b> {cost:.2f} руб.\n"
                f"<b>Длительность:</b> {duration // 60} ч."
            )
            success = await send_booking_notification(
                bot, ADMIN_ID, booking, user, auto,
                notification_text
            )
            if not success:
                logger.error(f"Не удалось уведомить мастера о подтверждении booking_id={booking_id}, user_id={user.telegram_id}")
            sent_message = await send_message(
                bot, str(callback.message.chat.id), "text",
                f"Вы подтвердили запись на ремонт: ✅\n"
                f"<b>Услуга:</b> Ремонт 🔧\n"
                f"<b>Стоимость:</b> {cost:.2f} руб.\n"
                f"<b>Длительность:</b> {duration // 60} ч.\n"
                f"<b>Дата:</b> {booking.date.strftime('%d.%m.%Y')} 📅\n"
                f"<b>Время:</b> {booking.time.strftime('%H:%M')} ⏰\n"
                f"<b>Авто:</b> {auto.brand}, {auto.year}, {auto.license_plate} 🚗",
                reply_markup=Keyboards.main_menu_kb()
            )
            if sent_message:
                await state.update_data(last_message_id=sent_message.message_id)
            asyncio.create_task(schedule_reminder(bot, booking, user, auto))
            asyncio.create_task(schedule_user_reminder(bot, booking, user, auto))
            await callback.answer("Запись подтверждена. ✅")
            await state.clear()
    except Exception as e:
        await handle_error(callback, state, bot,
                           "Ошибка. Попробуйте снова. 😔",
                           f"Ошибка подтверждения записи для booking_id={booking_id}", e)
        await callback.answer()

@repair_booking_router.callback_query(F.data.startswith("reject_booking_"))
async def reject_booking_user(callback: CallbackQuery, state: FSMContext, bot: Bot):
    """Пользователь отклоняет запись."""
    booking_id = int(callback.data.replace("reject_booking_", ""))
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
            booking.rejection_reason = "Пользователь отклонил запись"
            session.commit()
            cost = booking.cost or 0
            duration = booking.service_duration or 60
            success = await send_booking_notification(
                bot, ADMIN_ID, booking, user, auto,
                f"Пользователь {user.first_name} {user.last_name} отклонил запись на ремонт #{booking_id}:\n"
                f"<b>Причина:</b> Пользователь отклонил запись ❌\n"
                f"<b>Стоимость:</b> {cost:.2f} руб.\n"
                f"<b>Длительность:</b> {duration} мин."
            )
            if not success:
                logger.error(f"Не удалось уведомить мастера об отклонении booking_id={booking_id}, user_id={user.telegram_id}")
            sent_message = await send_message(
                bot, str(callback.message.chat.id), "text",
                f"Вы отклонили запись на ремонт: ❌\n"
                f"<b>Услуга:</b> Ремонт 🔧\n"
                f"<b>Дата:</b> {booking.date.strftime('%d.%m.%Y')} 📅\n"
                f"<b>Время:</b> {booking.time.strftime('%H:%M')} ⏰\n"
                f"<b>Авто:</b> {auto.brand}, {auto.year}, {auto.license_plate} 🚗",
                reply_markup=Keyboards.main_menu_kb()
            )
            if sent_message:
                await state.update_data(last_message_id=sent_message.message_id)
            await callback.answer("Запись отклонена. ❌")
            await state.clear()
    except Exception as e:
        await handle_error(callback, state, bot,
            "Ошибка. Попробуйте снова. 😔",
            f"Ошибка отклонения записи booking_id={booking_id}", e)
        await callback.answer()
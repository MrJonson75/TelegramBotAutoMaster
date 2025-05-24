from typing import Optional

from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from config import get_photo_path, REMINDER_TIME_MINUTES
from database import Session, User, Auto, Booking, BookingStatus
from keyboards.main_kb import Keyboards
from datetime import datetime
from utils import setup_logger, AutoInput
from .service_utils import (
    get_progress_bar, process_user_input, send_message, handle_error,
    check_user_and_autos, notify_master, schedule_reminder, schedule_user_reminder
)
from .states import RepairBookingStates, REPAIR_PROGRESS_STEPS
from pydantic import ValidationError
import asyncio

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
        logger.debug(f"State set to {next_state}, current FSM state: {await state.get_state()}")
        return True
    return False

@repair_booking_router.message(F.text == "Запись на ремонт")
async def start_repair_booking(message: Message, state: FSMContext, bot: Bot):
    """Начинает процесс записи на ремонт."""
    logger.info(f"User {message.from_user.id} started repair booking")
    try:
        with Session() as session:
            user, autos = await check_user_and_autos(session, str(message.from_user.id), bot, message, state, "booking_repair")
            if user and autos:
                await send_state_message(
                    bot, str(message.chat.id), state,
                    RepairBookingStates.AwaitingAuto,
                    "Выберите автомобиль для ремонта: 🚗",
                    "booking_repair",
                    Keyboards.auto_selection_kb(autos)
                )
    except Exception as e:
        await handle_error(message, state, bot, "Ошибка. Попробуйте снова. 😔", "Error starting repair booking", e)

@repair_booking_router.callback_query(RepairBookingStates.AwaitingAuto, F.data == "add_new_auto")
async def add_new_auto(callback: CallbackQuery, state: FSMContext, bot: Bot):
    """Обрабатывает выбор добавления нового автомобиля."""
    logger.info(f"User {callback.from_user.id} requested to add a new auto")
    success = await send_state_message(
        bot, str(callback.message.chat.id), state,
        RepairBookingStates.AwaitingAutoBrand,
        "Введите <b>марку</b> автомобиля (например, <b>Toyota</b>): 🚗"
    )
    if success:
        await callback.answer()

@repair_booking_router.message(RepairBookingStates.AwaitingAutoBrand, F.text)
async def process_auto_brand(message: Message, state: FSMContext, bot: Bot):
    """Обрабатывает ввод марки автомобиля."""
    await process_user_input(
        message, state, bot,
        AutoInput.validate_brand, "brand",
        "Введите <b>год выпуска</b> автомобиля (например, <b>2020</b>): 📅",
        "Марка слишком короткая или длинная (2–50 символов). Введите снова: 😔",
        RepairBookingStates.AwaitingAutoYear,
        REPAIR_PROGRESS_STEPS,
        reply_markup=Keyboards.cancel_kb()
    )

@repair_booking_router.message(RepairBookingStates.AwaitingAutoYear, F.text)
async def process_auto_year(message: Message, state: FSMContext, bot: Bot):
    """Обрабатывает ввод года выпуска автомобиля."""
    try:
        year = int(message.text.strip())
        AutoInput.validate_year(year)
        await state.update_data(year=year)
        success = await send_state_message(
            bot, str(message.chat.id), state,
            RepairBookingStates.AwaitingAutoVin,
            "Введите <b>VIN-номер</b> автомобиля (17 букв/цифр, например, <b>JTDBT923771012345</b>): 🔢",
            reply_markup=Keyboards.cancel_kb()
        )
    except (ValidationError, ValueError) as e:
        logger.warning(f"Validation error for year: {e}, input: {message.text}")
        await send_state_message(
            bot, str(message.chat.id), state,
            RepairBookingStates.AwaitingAutoYear,
            f"Некорректный год (1900–{datetime.today().year}). Введите снова: 📅",
            reply_markup=Keyboards.cancel_kb()
        )

@repair_booking_router.message(RepairBookingStates.AwaitingAutoVin, F.text)
async def process_auto_vin(message: Message, state: FSMContext, bot: Bot):
    """Обрабатывает ввод VIN-номера автомобиля."""
    await process_user_input(
        message, state, bot,
        AutoInput.validate_vin, "vin",
        "Введите <b>государственный номер</b> автомобиля (например, <b>А123БВ45</b>): 🚘",
        "Некорректный VIN (17 букв/цифр). Введите снова: 😔",
        RepairBookingStates.AwaitingAutoLicensePlate,
        REPAIR_PROGRESS_STEPS,
        reply_markup=Keyboards.cancel_kb()
    )

@repair_booking_router.message(RepairBookingStates.AwaitingAutoLicensePlate, F.text)
async def process_auto_license_plate(message: Message, state: FSMContext, bot: Bot):
    """Обрабатывает ввод госномера автомобиля."""
    if not message.text:
        await send_state_message(
            bot, str(message.chat.id), state,
            RepairBookingStates.AwaitingAutoLicensePlate,
            "Госномер не введён. Введите снова (например, <b>А123БВ45</b>): 🚘",
            reply_markup=Keyboards.cancel_kb()
        )
        return
    try:
        license_plate = message.text.strip()
        data = await state.get_data()
        auto_input = AutoInput(
            brand=data["brand"],
            year=data["year"],
            vin=data["vin"],
            license_plate=license_plate
        )
        with Session() as session:
            user = session.query(User).filter_by(telegram_id=str(message.from_user.id)).first()
            if not user:
                await handle_error(
                    message, state, bot,
                    "Вы не зарегистрированы. Начните с записи на ТО. 👤",
                    "User not found", Exception("User not found")
                )
                return
            auto = Auto(
                user_id=user.id,
                brand=auto_input.brand,
                year=auto_input.year,
                vin=auto_input.vin,
                license_plate=auto_input.license_plate
            )
            session.add(auto)
            session.commit()
            logger.info(f"Auto added for user {message.from_user.id}")
            autos = session.query(Auto).filter_by(user_id=user.id).all()
            success = await send_state_message(
                bot, str(message.chat.id), state,
                RepairBookingStates.AwaitingAddAnotherAuto,
                "Автомобиль добавлен! 🎉 Хотите добавить ещё один автомобиль или продолжить?",
                reply_markup=Keyboards.add_another_auto_kb()
            )
            if success:
                await state.update_data(auto_id=auto.id)
    except ValidationError as e:
        logger.warning(f"Validation error for license plate: {e}, input: {license_plate}")
        await send_state_message(
            bot, str(message.chat.id), state,
            RepairBookingStates.AwaitingAutoLicensePlate,
            "Госномер слишком короткий или длинный (5–20 символов, например, <b>А123БВ45</b>). Введите снова: 🚘",
            reply_markup=Keyboards.cancel_kb()
        )
    except Exception as e:
        await handle_error(
            message, state, bot,
            "Ошибка добавления автомобиля. Попробуйте снова. 😔",
            "Error adding auto", e
        )

@repair_booking_router.callback_query(RepairBookingStates.AwaitingAddAnotherAuto, F.data == "add_another_auto")
async def add_another_auto(callback: CallbackQuery, state: FSMContext, bot: Bot):
    """Обрабатывает выбор добавления ещё одного автомобиля."""
    logger.info(f"User {callback.from_user.id} chose to add another auto")
    success = await send_state_message(
        bot, str(callback.message.chat.id), state,
        RepairBookingStates.AwaitingAutoBrand,
        "Введите <b>марку</b> автомобиля (например, <b>Toyota</b>): 🚗"
    )
    if success:
        await callback.answer()

@repair_booking_router.callback_query(RepairBookingStates.AwaitingAddAnotherAuto, F.data == "continue_booking")
async def continue_booking(callback: CallbackQuery, state: FSMContext, bot: Bot):
    """Продолжает процесс бронирования."""
    logger.info(f"User {callback.from_user.id} chose to continue booking")
    try:
        data = await state.get_data()
        with Session() as session:
            user, autos = await check_user_and_autos(session, str(callback.from_user.id), bot, callback, state, "booking_repair")
            if not user:
                return
            if autos and "auto_id" not in data:
                await send_state_message(
                    bot, str(callback.message.chat.id), state,
                    RepairBookingStates.AwaitingAuto,
                    "Выберите автомобиль для ремонта: 🚗",
                    "booking_repair",
                    Keyboards.auto_selection_kb(autos)
                )
            else:
                await send_state_message(
                    bot, str(callback.message.chat.id), state,
                    RepairBookingStates.AwaitingDescription,
                    "Опишите проблему с автомобилем (например, <b>стук в двигателе</b>): 📝",
                    "booking_repair_sel"
                )
        await callback.answer()
    except Exception as e:
        await handle_error(
            callback, state, bot,
            "Ошибка. Попробуйте снова. 😔",
            "Error continuing booking", e
        )
        await callback.answer()

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
                    f"Auto not found for auto_id={auto_id}",
                    Exception("Auto not found")
                )
                await callback.answer()
                return
        await state.update_data(auto_id=auto_id)
        success = await send_state_message(
            bot, str(callback.message.chat.id), state,
            RepairBookingStates.AwaitingDescription,
            "Опишите проблему с автомобилем (например, <b>стук в двигателе</b>): 📝",
            "booking_repair_sel"
        )
        if success:
            await callback.answer()
    except Exception as e:
        await handle_error(
            callback, state, bot,
            "Ошибка. Попробуйте снова. 😔",
            "Error selecting auto", e
        )
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
            "booking_repair_sel"
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
    data = await state.get_data()
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
    with Session() as session:
        await callback.message.edit_reply_markup(
            reply_markup=Keyboards.time_slots_kb(selected_date, 60, session, time_offset)
        )
    await callback.answer()

@repair_booking_router.callback_query(RepairBookingStates.AwaitingTime, F.data.startswith("time_"))
async def process_time_selection(callback: CallbackQuery, state: FSMContext, bot: Bot):
    """Обрабатывает выбор времени и создаёт запись."""
    time_str = callback.data.replace("time_", "")
    try:
        selected_time = datetime.strptime(time_str, "%H:%M").time()
        data = await state.get_data()
        with Session() as session:
            user = session.query(User).filter_by(telegram_id=str(callback.from_user.id)).first()
            auto = session.query(Auto).get(data.get("auto_id"))
            if not auto:
                await handle_error(
                    callback, state, bot,
                    "Автомобиль не найден. Начните заново. 🚗",
                    f"Auto not found for auto_id={data.get('auto_id')}",
                    Exception("Auto not found")
                )
                await callback.answer()
                return
            # Проверка доступности времени
            time_slots = Keyboards.time_slots_kb(data["selected_date"], 60, session)
            available_times = [btn[0].callback_data.replace("time_", "") for btn in time_slots.inline_keyboard if btn[0].callback_data.startswith("time_")]
            if time_str not in available_times:
                await send_state_message(
                    bot, str(callback.message.chat.id), state,
                    RepairBookingStates.AwaitingTime,
                    "Выбранное время недоступно. Выберите другое время: ⏰",
                    reply_markup=Keyboards.time_slots_kb(data["selected_date"], 60, session)
                )
                await callback.answer()
                return
            booking = Booking(
                user_id=user.id,
                auto_id=data["auto_id"],
                service_name="Ремонт",
                description=data["description"],
                date=data["selected_date"].date(),
                time=selected_time,
                status=BookingStatus.PENDING,
                price=None
            )
            session.add(booking)
            session.commit()
            logger.info(f"Repair booking created: {booking.id} for user {callback.from_user.id}")
            photos = data.get("photos", [])
            success = await notify_master(bot, booking, user, auto, photos)
            if not success:
                logger.warning(f"Failed to notify master for booking_id={booking.id}: Notification sending failed")
            # Планируем напоминание только за REMINDER_TIME_MINUTES
            asyncio.create_task(schedule_reminder(bot, booking, user, auto, delay_minutes=REMINDER_TIME_MINUTES))
            asyncio.create_task(schedule_user_reminder(bot, booking, user, auto, delay_minutes=REMINDER_TIME_MINUTES))
            keyboard = InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="Отменить запись ❌", callback_data=f"cancel_booking_{booking.id}")
            ]])
            response = (
                f"Ваша заявка на ремонт отправлена мастеру. Ожидайте подтверждения. ⏳\n"
                f"<b>Проблема:</b> {data['description']} 📝"
            )
            sent_message = await send_message(
                bot, str(callback.message.chat.id), "text",
                response,
                reply_markup=keyboard
            )
            if sent_message:
                await state.update_data(last_message_id=sent_message.message_id)
            await state.clear()
            await callback.answer()
    except Exception as e:
        await handle_error(
            callback, state, bot,
            "Ошибка записи. Попробуйте снова. 😔",
            "Error creating repair booking", e
        )
        await callback.answer()

@repair_booking_router.callback_query(F.data == "cancel")
async def cancel_action(callback: CallbackQuery, state: FSMContext, bot: Bot):
    """Отменяет действие."""
    sent_message = await send_message(
        bot, str(callback.message.chat.id), "text",
        "Действие отменено. ❌",
        reply_markup=Keyboards.main_menu_kb()
    )
    if sent_message:
        await state.update_data(last_message_id=sent_message.message_id)
    await state.clear()
    await callback.answer()
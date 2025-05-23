from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, FSInputFile, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.base import StorageKey
from aiogram.exceptions import TelegramForbiddenError, TelegramBadRequest
from config import get_photo_path, ADMIN_ID, MESSAGES, REMINDER_TIME_MINUTES, SERVICES
from keyboards.main_kb import Keyboards
from utils import setup_logger, UserInput, AutoInput, delete_previous_message
from pydantic import ValidationError
from database import User, Auto, Booking, BookingStatus
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
import re
import asyncio

service_booking_router = Router()
logger = setup_logger(__name__)
from database import Session

# Состояния FSM
class BookingStates(StatesGroup):
    AwaitingAutoSelection = State()
    AwaitingService = State()
    AwaitingFirstName = State()
    AwaitingLastName = State()
    AwaitingPhone = State()
    AwaitingAutoBrand = State()
    AwaitingAutoYear = State()
    AwaitingAutoVin = State()
    AwaitingAutoLicensePlate = State()
    AwaitingAddAnotherAuto = State()
    AwaitingDate = State()
    AwaitingTime = State()
    AwaitingMasterResponse = State()
    AwaitingMasterTime = State()
    AwaitingUserConfirmation = State()

async def notify_master(bot, booking: Booking, user: User, auto: Auto):
    """Отправляет уведомление мастеру о новой записи."""
    try:
        message = (
            f"Новая заявка на ТО:\n"
            f"Пользователь: {user.first_name} {user.last_name}\n"
            f"Телефон: {user.phone}\n"
            f"Авто: {auto.brand}, {auto.year}, {auto.license_plate}\n"
            f"Услуга: {booking.service_name}\n"
            f"Дата: {booking.date.strftime('%d.%m.%Y')}\n"
            f"Время: {booking.time.strftime('%H:%M')}\n"
            f"Подтвердить или отклонить?"
        )
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Подтвердить", callback_data=f"confirm_booking_{booking.id}")],
            [InlineKeyboardButton(text="Предложить другое время", callback_data=f"reschedule_booking_{booking.id}")],
            [InlineKeyboardButton(text="Отклонить", callback_data=f"reject_booking_{booking.id}")]
        ])
        await bot.send_message(ADMIN_ID, message, reply_markup=keyboard)
        logger.info(f"Уведомление мастеру отправлено для booking_id={booking.id}")
    except Exception as e:
        logger.error(f"Ошибка отправки уведомления мастеру для booking_id={booking.id}: {str(e)}")

async def schedule_reminder(bot, booking: Booking, user: User, auto: Auto):
    """Запланировать напоминание мастеру."""
    try:
        booking_datetime = datetime.combine(booking.date, booking.time)
        reminder_time = booking_datetime - timedelta(minutes=REMINDER_TIME_MINUTES)
        now = datetime.now()
        if reminder_time > now:
            delay = (reminder_time - now).total_seconds()
            await asyncio.sleep(delay)
            await bot.send_message(
                ADMIN_ID,
                f"Напоминание: Через {REMINDER_TIME_MINUTES} минут запись:\n"
                f"Пользователь: {user.first_name} {user.last_name}\n"
                f"Авто: {auto.brand}, {auto.year}\n"
                f"Услуга: {booking.service_name}\n"
                f"Дата: {booking.date.strftime('%d.%m.%Y')}\n"
                f"Время: {booking.time.strftime('%H:%M')}"
            )
            logger.info(f"Напоминание мастеру отправлено для booking_id={booking.id}")
    except Exception as e:
        logger.error(f"Ошибка отправки напоминания мастеру для booking_id={booking.id}: {str(e)}")

@service_booking_router.message(F.text == "Запись на ТО")
async def start_booking(message: Message, state: FSMContext, bot):
    """Запускает процесс записи на ТО."""
    logger.info(f"User {message.from_user.id} started booking")
    try:
        with Session() as session:
            user = session.query(User).filter_by(telegram_id=str(message.from_user.id)).first()
            if user:
                autos = session.query(Auto).filter_by(user_id=user.id).all()
                if autos:
                    try:
                        photo_path = get_photo_path("booking")
                        sent_message = await message.answer_photo(
                            photo=FSInputFile(photo_path),
                            caption="Выберите автомобиль для записи на ТО:",
                            reply_markup=Keyboards.auto_selection_kb(autos)
                        )
                        await state.update_data(last_message_id=sent_message.message_id)
                    except (FileNotFoundError, ValueError) as e:
                        logger.error(f"Ошибка загрузки фото для бронирования: {str(e)}")
                        sent_message = await message.answer(
                            "Выберите автомобиль для записи на ТО:",
                            reply_markup=Keyboards.auto_selection_kb(autos)
                        )
                        await state.update_data(last_message_id=sent_message.message_id)
                    await state.set_state(BookingStates.AwaitingAutoSelection)
                else:
                    sent_message = await message.answer(
                        "У вас нет зарегистрированных автомобилей. Введите марку автомобиля:"
                    )
                    await state.update_data(last_message_id=sent_message.message_id)
                    await state.set_state(BookingStates.AwaitingAutoBrand)
            else:
                sent_message = await message.answer(
                    "Для записи на ТО необходимо зарегистрироваться.\nВведите ваше имя:"
                )
                await state.update_data(last_message_id=sent_message.message_id)
                await state.set_state(BookingStates.AwaitingFirstName)
    except Exception as e:
        logger.error(f"Ошибка проверки пользователя: {str(e)}")
        sent_message = await message.answer("Ошибка. Попробуйте снова.", reply_markup=Keyboards.main_menu_kb())
        await state.update_data(last_message_id=sent_message.message_id)
        await state.clear()

@service_booking_router.callback_query(BookingStates.AwaitingAutoSelection, F.data.startswith("auto_"))
async def process_auto_selection(callback: CallbackQuery, state: FSMContext, bot):
    """Обрабатывает выбор автомобиля."""
    auto_id = int(callback.data.replace("auto_", ""))
    try:
        with Session() as session:
            auto = session.query(Auto).get(auto_id)
            if not auto:
                await delete_previous_message(bot, callback.message.chat.id, (await state.get_data()).get("last_message_id"))
                sent_message = await callback.message.answer("Автомобиль не найден. Попробуйте снова:",
                                              reply_markup=Keyboards.main_menu_kb())
                await state.update_data(last_message_id=sent_message.message_id)
                await state.clear()
                await callback.answer()
                return
            await state.update_data(auto_id=auto_id)
            await delete_previous_message(bot, callback.message.chat.id, (await state.get_data()).get("last_message_id"))
            try:
                photo_path = get_photo_path("booking_menu")
                sent_message = await callback.message.answer_photo(
                    photo=FSInputFile(photo_path),
                    caption=MESSAGES["booking"],
                    reply_markup=Keyboards.services_kb()
                )
                await state.update_data(last_message_id=sent_message.message_id)
            except (FileNotFoundError, ValueError) as e:
                logger.error(f"Ошибка загрузки фото для бронирования: {str(e)}")
                sent_message = await callback.message.answer(
                    MESSAGES["booking"],
                    reply_markup=Keyboards.services_kb()
                )
                await state.update_data(last_message_id=sent_message.message_id)
            await state.set_state(BookingStates.AwaitingService)
            await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка выбора автомобиля: {str(e)}")
        await delete_previous_message(bot, callback.message.chat.id, (await state.get_data()).get("last_message_id"))
        sent_message = await callback.message.answer("Ошибка. Попробуйте снова.", reply_markup=Keyboards.main_menu_kb())
        await state.update_data(last_message_id=sent_message.message_id)
        await state.clear()
        await callback.answer()

@service_booking_router.callback_query(BookingStates.AwaitingAutoSelection, F.data == "add_new_auto")
async def add_new_auto(callback: CallbackQuery, state: FSMContext, bot):
    """Обрабатывает выбор добавления нового автомобиля."""
    await delete_previous_message(bot, callback.message.chat.id, (await state.get_data()).get("last_message_id"))
    sent_message = await callback.message.answer("Введите марку автомобиля:")
    await state.update_data(last_message_id=sent_message.message_id)
    await state.set_state(BookingStates.AwaitingAutoBrand)
    await callback.answer()

@service_booking_router.message(BookingStates.AwaitingFirstName, F.text)
async def process_first_name(message: Message, state: FSMContext, bot):
    try:
        first_name = message.text.strip()
        UserInput.validate_first_name(first_name)
        await state.update_data(first_name=first_name)
        await delete_previous_message(bot, message.chat.id, (await state.get_data()).get("last_message_id"))
        sent_message = await message.answer("Введите вашу фамилию:")
        await state.update_data(last_message_id=sent_message.message_id)
        await state.set_state(BookingStates.AwaitingLastName)
    except ValidationError as e:
        logger.warning(f"Validation error for first_name: {e}, input: {first_name}")
        await delete_previous_message(bot, message.chat.id, (await state.get_data()).get("last_message_id"))
        sent_message = await message.answer("Имя слишком короткое или длинное (2–50 символов). Введите снова:")
        await state.update_data(last_message_id=sent_message.message_id)

@service_booking_router.message(BookingStates.AwaitingLastName, F.text)
async def process_last_name(message: Message, state: FSMContext, bot):
    try:
        last_name = message.text.strip()
        UserInput.validate_last_name(last_name)
        await state.update_data(last_name=last_name)
        await delete_previous_message(bot, message.chat.id, (await state.get_data()).get("last_message_id"))
        sent_message = await message.answer("Введите ваш номер телефона (например, +79991234567):")
        await state.update_data(last_message_id=sent_message.message_id)
        await state.set_state(BookingStates.AwaitingPhone)
    except ValidationError as e:
        logger.warning(f"Validation error for last_name: {e}, input: {last_name}")
        await delete_previous_message(bot, message.chat.id, (await state.get_data()).get("last_message_id"))
        sent_message = await message.answer("Фамилия слишком короткая или длинная (2–50 символов). Введите снова:")
        await state.update_data(last_message_id=sent_message.message_id)

@service_booking_router.message(BookingStates.AwaitingPhone, F.text)
async def process_phone(message: Message, state: FSMContext, bot):
    try:
        phone = message.text.strip()
        data = await state.get_data()
        user_input = UserInput(
            first_name=data["first_name"],
            last_name=data["last_name"],
            phone=phone
        )
        try:
            with Session() as session:
                user = User(
                    first_name=user_input.first_name,
                    last_name=user_input.last_name,
                    phone=user_input.phone,
                    telegram_id=str(message.from_user.id)
                )
                session.add(user)
                session.commit()
                logger.info(f"User {message.from_user.id} registered")
            await delete_previous_message(bot, message.chat.id, (await state.get_data()).get("last_message_id"))
            sent_message = await message.answer("Введите марку автомобиля:")
            await state.update_data(last_message_id=sent_message.message_id)
            await state.set_state(BookingStates.AwaitingAutoBrand)
        except Exception as e:
            logger.error(f"Ошибка регистрации пользователя: {str(e)}")
            await delete_previous_message(bot, message.chat.id, (await state.get_data()).get("last_message_id"))
            sent_message = await message.answer("Ошибка регистрации. Попробуйте снова.", reply_markup=Keyboards.main_menu_kb())
            await state.update_data(last_message_id=sent_message.message_id)
            await state.clear()
    except ValidationError as e:
        logger.warning(f"Validation error for phone: {e}, input: {phone}")
        await delete_previous_message(bot, message.chat.id, (await state.get_data()).get("last_message_id"))
        sent_message = await message.answer("Некорректный номер телефона (10–15 цифр, например, +79991234567). Введите снова:")
        await state.update_data(last_message_id=sent_message.message_id)

@service_booking_router.message(BookingStates.AwaitingAutoBrand, F.text)
async def process_auto_brand(message: Message, state: FSMContext, bot):
    try:
        brand = message.text.strip()
        AutoInput.validate_brand(brand)
        await state.update_data(brand=brand)
        await delete_previous_message(bot, message.chat.id, (await state.get_data()).get("last_message_id"))
        sent_message = await message.answer("Введите год выпуска автомобиля (например, 2020):")
        await state.update_data(last_message_id=sent_message.message_id)
        await state.set_state(BookingStates.AwaitingAutoYear)
    except ValidationError as e:
        logger.warning(f"Validation error for brand: {e}, input: {brand}")
        await delete_previous_message(bot, message.chat.id, (await state.get_data()).get("last_message_id"))
        sent_message = await message.answer("Марка слишком короткая или длинная (2–50 символов). Введите снова:")
        await state.update_data(last_message_id=sent_message.message_id)

@service_booking_router.message(BookingStates.AwaitingAutoYear, F.text)
async def process_auto_year(message: Message, state: FSMContext, bot):
    try:
        year = int(message.text.strip())
        AutoInput.validate_year(year)
        await state.update_data(year=year)
        await delete_previous_message(bot, message.chat.id, (await state.get_data()).get("last_message_id"))
        sent_message = await message.answer("Введите VIN-номер автомобиля (17 символов):")
        await state.update_data(last_message_id=sent_message.message_id)
        await state.set_state(BookingStates.AwaitingAutoVin)
    except (ValidationError, ValueError) as e:
        logger.warning(f"Validation error for year: {e}, input: {message.text}")
        await delete_previous_message(bot, message.chat.id, (await state.get_data()).get("last_message_id"))
        sent_message = await message.answer(f"Некорректный год (1900–{datetime.today().year}). Введите снова:")
        await state.update_data(last_message_id=sent_message.message_id)

@service_booking_router.message(BookingStates.AwaitingAutoVin, F.text)
async def process_auto_vin(message: Message, state: FSMContext, bot):
    try:
        vin = message.text.strip()
        AutoInput.validate_vin(vin)
        await state.update_data(vin=vin)
        await delete_previous_message(bot, message.chat.id, (await state.get_data()).get("last_message_id"))
        sent_message = await message.answer("Введите государственный номер автомобиля:")
        await state.update_data(last_message_id=sent_message.message_id)
        await state.set_state(BookingStates.AwaitingAutoLicensePlate)
    except ValidationError as e:
        logger.warning(f"Validation error for vin: {e}, input: {vin}")
        await delete_previous_message(bot, message.chat.id, (await state.get_data()).get("last_message_id"))
        sent_message = await message.answer("Некорректный VIN (17 букв/цифр). Введите снова:")
        await state.update_data(last_message_id=sent_message.message_id)

@service_booking_router.message(BookingStates.AwaitingAutoLicensePlate, F.text)
async def process_auto_license_plate(message: Message, state: FSMContext, bot):
    try:
        license_plate = message.text.strip()
        data = await state.get_data()
        auto_input = AutoInput(
            brand=data["brand"],
            year=data["year"],
            vin=data["vin"],
            license_plate=license_plate
        )
        try:
            with Session() as session:
                user = session.query(User).filter_by(telegram_id=str(message.from_user.id)).first()
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
                await state.update_data(auto_id=auto.id)
            await delete_previous_message(bot, message.chat.id, (await state.get_data()).get("last_message_id"))
            sent_message = await message.answer(
                "Автомобиль добавлен. Хотите добавить ещё один автомобиль или продолжить?",
                reply_markup=Keyboards.add_another_auto_kb()
            )
            await state.update_data(last_message_id=sent_message.message_id)
            await state.set_state(BookingStates.AwaitingAddAnotherAuto)
        except Exception as e:
            logger.error(f"Ошибка добавления автомобиля: {str(e)}")
            await delete_previous_message(bot, message.chat.id, (await state.get_data()).get("last_message_id"))
            sent_message = await message.answer("Ошибка добавления автомобиля. Попробуйте снова.", reply_markup=Keyboards.main_menu_kb())
            await state.update_data(last_message_id=sent_message.message_id)
            await state.clear()
    except ValidationError as e:
        logger.warning(f"Validation error for license_plate: {e}, input: {license_plate}")
        await delete_previous_message(bot, message.chat.id, (await state.get_data()).get("last_message_id"))
        sent_message = await message.answer("Госномер слишком короткий или длинный (5–20 символов). Введите снова:")
        await state.update_data(last_message_id=sent_message.message_id)

# Остальной код остаётся без изменений
@service_booking_router.callback_query(BookingStates.AwaitingAddAnotherAuto, F.data == "add_another_auto")
async def add_another_auto(callback: CallbackQuery, state: FSMContext, bot):
    """Обрабатывает выбор добавления ещё одного автомобиля."""
    await delete_previous_message(bot, callback.message.chat.id, (await state.get_data()).get("last_message_id"))
    sent_message = await callback.message.answer("Введите марку автомобиля:")
    await state.update_data(last_message_id=sent_message.message_id)
    await state.set_state(BookingStates.AwaitingAutoBrand)
    await callback.answer()

@service_booking_router.callback_query(BookingStates.AwaitingAddAnotherAuto, F.data == "continue_booking")
async def continue_booking(callback: CallbackQuery, state: FSMContext, bot):
    """Продолжает процесс бронирования."""
    try:
        await delete_previous_message(bot, callback.message.chat.id, (await state.get_data()).get("last_message_id"))
        photo_path = get_photo_path("booking_final")
        sent_message = await callback.message.answer_photo(
            photo=FSInputFile(photo_path),
            caption=MESSAGES["booking"],
            reply_markup=Keyboards.services_kb()
        )
        await state.update_data(last_message_id=sent_message.message_id)
        await state.set_state(BookingStates.AwaitingService)
        await callback.answer()
    except (FileNotFoundError, ValueError) as e:
        logger.error(f"Ошибка загрузки фото для бронирования: {str(e)}")
        await delete_previous_message(bot, callback.message.chat.id, (await state.get_data()).get("last_message_id"))
        sent_message = await callback.message.answer(
            MESSAGES["booking"],
            reply_markup=Keyboards.services_kb()
        )
        await state.update_data(last_message_id=sent_message.message_id)
        await state.set_state(BookingStates.AwaitingService)
        await callback.answer()

@service_booking_router.callback_query(BookingStates.AwaitingService, F.data.startswith("service_"))
async def process_service_selection(callback: CallbackQuery, state: FSMContext, bot):
    """Обрабатывает выбор услуги."""
    service_name = callback.data.replace("service_", "")
    if service_name not in [s["name"] for s in SERVICES]:
        await delete_previous_message(bot, callback.message.chat.id, (await state.get_data()).get("last_message_id"))
        sent_message = await callback.message.answer("Некорректная услуга. Выберите снова:", reply_markup=Keyboards.services_kb())
        await state.update_data(last_message_id=sent_message.message_id)
        await callback.answer()
        return
    service_duration = next(s["duration_minutes"] for s in SERVICES if s["name"] == service_name)
    await state.update_data(service_name=service_name, service_duration=service_duration, week_offset=0)
    await delete_previous_message(bot, callback.message.chat.id, (await state.get_data()).get("last_message_id"))
    sent_message = await callback.message.answer(
        "Выберите дату для записи:",
        reply_markup=Keyboards.calendar_kb()
    )
    await state.update_data(last_message_id=sent_message.message_id)
    await state.set_state(BookingStates.AwaitingDate)
    await callback.answer()

@service_booking_router.callback_query(BookingStates.AwaitingDate, F.data.startswith("prev_week_"))
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

@service_booking_router.callback_query(BookingStates.AwaitingDate, F.data.startswith("next_week_"))
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

@service_booking_router.callback_query(BookingStates.AwaitingDate, F.data == "today")
async def today_selection(callback: CallbackQuery, state: FSMContext):
    """Обрабатывает выбор текущего дня."""
    await state.update_data(week_offset=0)
    data = await state.get_data()
    selected_date = data.get("selected_date")
    await callback.message.edit_reply_markup(
        reply_markup=Keyboards.calendar_kb(selected_date, 0)
    )
    await callback.answer()

@service_booking_router.callback_query(BookingStates.AwaitingDate, F.data.startswith("date_"))
async def process_date_selection(callback: CallbackQuery, state: FSMContext, bot):
    """Обрабатывает выбор даты."""
    date_str = callback.data.replace("date_", "")
    try:
        selected_date = datetime.strptime(date_str, "%Y-%m-%d")
        data = await state.get_data()
        week_offset = data.get("week_offset", 0)
        with Session() as session:
            time_slots = Keyboards.time_slots_kb(selected_date, data["service_duration"], session)
            if not time_slots.inline_keyboard:
                await delete_previous_message(bot, callback.message.chat.id, (await state.get_data()).get("last_message_id"))
                sent_message = await callback.message.answer(
                    "Нет доступных слотов на эту дату. Выберите другую дату:",
                    reply_markup=Keyboards.calendar_kb(selected_date, week_offset)
                )
                await state.update_data(last_message_id=sent_message.message_id)
                await callback.answer()
                return
            await state.update_data(selected_date=selected_date, time_offset=0)
            await delete_previous_message(bot, callback.message.chat.id, (await state.get_data()).get("last_message_id"))
            sent_message = await callback.message.answer(
                "Выберите время для записи:",
                reply_markup=time_slots
            )
            await state.update_data(last_message_id=sent_message.message_id)
            await state.set_state(BookingStates.AwaitingTime)
            await callback.answer()
    except ValueError:
        data = await state.get_data()
        week_offset = data.get("week_offset", 0)
        await delete_previous_message(bot, callback.message.chat.id, (await state.get_data()).get("last_message_id"))
        sent_message = await callback.message.answer(
            "Некорректная дата. Выберите снова:",
            reply_markup=Keyboards.calendar_kb(week_offset=week_offset)
        )
        await state.update_data(last_message_id=sent_message.message_id)
        await callback.answer()

@service_booking_router.callback_query(BookingStates.AwaitingTime, F.data.startswith("prev_slots_"))
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

@service_booking_router.callback_query(BookingStates.AwaitingTime, F.data.startswith("next_slots_"))
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

async def schedule_user_reminder(bot, booking: Booking, user: User, auto: Auto):
    """Запланировать напоминание пользователю."""
    try:
        booking_datetime = datetime.combine(booking.date, booking.time)
        reminder_time = booking_datetime - timedelta(minutes=REMINDER_TIME_MINUTES)
        now = datetime.now()
        if reminder_time > now:
            delay = (reminder_time - now).total_seconds()
            await asyncio.sleep(delay)
            await bot.send_message(
                user.telegram_id,
                f"Напоминание: Через {REMINDER_TIME_MINUTES} минут ваша запись:\n"
                f"Услуга: {booking.service_name} ({booking.price} ₽)\n"
                f"Авто: {auto.brand}, {auto.year}\n"
                f"Дата: {booking.date.strftime('%d.%m.%Y')}\n"
                f"Время: {booking.time.strftime('%H:%M')}"
            )
            logger.info(f"Напоминание отправлено пользователю {user.telegram_id} для booking_id={booking.id}")
    except Exception as e:
        logger.error(f"Ошибка отправки напоминания пользователю для booking_id={booking.id}: {str(e)}")

@service_booking_router.callback_query(BookingStates.AwaitingTime, F.data.startswith("time_"))
async def process_time_selection(callback: CallbackQuery, state: FSMContext, bot):
    time_str = callback.data.replace("time_", "")
    try:
        selected_time = datetime.strptime(time_str, "%H:%M").time()
        data = await state.get_data()
        with Session() as session:
            user = session.query(User).filter_by(telegram_id=str(callback.from_user.id)).first()
            auto = session.query(Auto).get(data["auto_id"])
            if not auto:
                await delete_previous_message(bot, callback.message.chat.id, (await state.get_data()).get("last_message_id"))
                sent_message = await callback.message.answer("Автомобиль не найден. Начните заново.",
                                              reply_markup=Keyboards.main_menu_kb())
                await state.update_data(last_message_id=sent_message.message_id)
                await state.clear()
                await callback.answer()
                return
            service_price = next(s["price"] for s in SERVICES if s["name"] == data["service_name"])
            booking = Booking(
                user_id=user.id,
                auto_id=data["auto_id"],
                service_name=data["service_name"],
                date=data["selected_date"].date(),
                time=selected_time,
                status=BookingStatus.PENDING,
                price=service_price
            )
            session.add(booking)
            session.commit()
            logger.info(f"Booking created: {booking.id} for user {callback.from_user.id}")
            await notify_master(bot, booking, user, auto)
            asyncio.create_task(schedule_reminder(bot, booking, user, auto))
            asyncio.create_task(schedule_user_reminder(bot, booking, user, auto))
            await delete_previous_message(bot, callback.message.chat.id, (await state.get_data()).get("last_message_id"))
            sent_message = await callback.message.answer(
                f"Ваша заявка отправлена мастеру. Ожидайте подтверждения.\n"
                f"Услуга: {booking.service_name} ({service_price} ₽)",
                reply_markup=Keyboards.main_menu_kb()
            )
            await state.update_data(last_message_id=sent_message.message_id)
            await state.clear()
            await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка создания записи: {str(e)}")
        await delete_previous_message(bot, callback.message.chat.id, (await state.get_data()).get("last_message_id"))
        sent_message = await callback.message.answer("Ошибка записи. Попробуйте снова.", reply_markup=Keyboards.main_menu_kb())
        await state.update_data(last_message_id=sent_message.message_id)
        await state.clear()
        await callback.answer()

@service_booking_router.callback_query(F.data.startswith("confirm_booking_"))
async def confirm_booking(callback: CallbackQuery, state: FSMContext, bot):
    """Мастер подтверждает запись."""
    if str(callback.from_user.id) != ADMIN_ID:
        await callback.answer("Доступ только для мастера.")
        return
    booking_id = int(callback.data.replace("confirm_booking_", ""))
    try:
        with Session() as session:
            booking = session.query(Booking).get(booking_id)
            if not booking:
                await callback.answer("Запись не найдена.")
                return
            booking.status = BookingStatus.CONFIRMED
            session.commit()
            user = session.query(User).get(booking.user_id)
            auto = session.query(Auto).get(booking.auto_id)
            try:
                await bot.send_message(
                    user.telegram_id,
                    f"Ваша запись подтверждена!\n"
                    f"Услуга: {booking.service_name}\n"
                    f"Дата: {booking.date.strftime('%d.%m.%Y')}\n"
                    f"Время: {booking.time.strftime('%H:%M')}\n"
                    f"Авто: {auto.brand}, {auto.year}, {auto.license_plate}"
                )
                logger.info(f"Уведомление о подтверждении отправлено пользователю {user.telegram_id} для booking_id={booking_id}")
            except TelegramForbiddenError:
                logger.error(f"Не удалось отправить уведомление пользователю {user.telegram_id}: пользователь заблокировал бота")
            except Exception as e:
                logger.error(f"Ошибка отправки уведомления пользователю {user.telegram_id}: {str(e)}")
            await callback.message.edit_text(
                callback.message.text + "\nСтатус: Подтверждено"
            )
            await callback.answer("Запись подтверждена.")
    except Exception as e:
        logger.error(f"Ошибка подтверждения записи booking_id={booking_id}: {str(e)}")
        await callback.answer("Ошибка. Попробуйте снова.")

@service_booking_router.callback_query(F.data.startswith("reschedule_booking_"))
async def reschedule_booking(callback: CallbackQuery, state: FSMContext, bot):
    """Мастер предлагает другое время."""
    if str(callback.from_user.id) != ADMIN_ID:
        await callback.answer("Доступ только для мастера.")
        return
    booking_id = int(callback.data.replace("reschedule_booking_", ""))
    try:
        with Session() as session:
            booking = session.query(Booking).get(booking_id)
            if not booking:
                await callback.answer("Запись не найдена.")
                return
        await state.update_data(booking_id=booking_id, master_action="reschedule")
        await callback.message.answer("Введите новое время (например, 14:30):")
        await state.set_state(BookingStates.AwaitingMasterTime)
        logger.info(f"Мастер запросил новое время для booking_id={booking_id}")
        await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка при запросе нового времени для booking_id={booking_id}: {str(e)}")
        await callback.answer("Ошибка. Попробуйте снова.")

@service_booking_router.callback_query(F.data.startswith("reject_booking_"))
async def reject_booking(callback: CallbackQuery, state: FSMContext, bot):
    """Мастер отклоняет запись."""
    if str(callback.from_user.id) != ADMIN_ID:
        await callback.answer("Доступ только для мастера.")
        return
    booking_id = int(callback.data.replace("reject_booking_", ""))
    await state.update_data(booking_id=booking_id, master_action="reject")
    await callback.message.answer("Укажите причину отказа:")
    await state.set_state(BookingStates.AwaitingMasterResponse)
    logger.info(f"Мастер запросил причину отказа для booking_id={booking_id}")
    await callback.answer()

@service_booking_router.message(BookingStates.AwaitingMasterTime, F.text)
async def process_master_time(message: Message, state: FSMContext, bot):
    """Обрабатывает ввод нового времени мастером."""
    if str(message.from_user.id) != ADMIN_ID:
        logger.debug(f"Неавторизованный доступ к process_master_time от user_id={message.from_user.id}")
        return
    data = await state.get_data()
    logger.debug(f"FSM state in process_master_time: {data}")
    if "booking_id" not in data or "master_action" not in data or data["master_action"] != "reschedule":
        logger.error(f"Некорректные данные состояния FSM: {data}")
        await message.answer("Ошибка: данные состояния отсутствуют. Попробуйте снова.")
        await state.clear()
        return
    booking_id = data.get("booking_id")
    logger.info(f"Обработка нового времени для booking_id={booking_id}")

    try:
        with Session() as session:
            booking = session.query(Booking).get(booking_id)
            if not booking:
                logger.error(f"Запись booking_id={booking_id} не найдена")
                await message.answer("Запись не найдена.")
                await state.clear()
                return
            user = session.query(User).get(booking.user_id)
            if not user:
                logger.error(f"Пользователь user_id={booking.user_id} не найден для booking_id={booking_id}")
                await message.answer("Пользователь не найден.")
                await state.clear()
                return
            auto = session.query(Auto).get(booking.auto_id)
            if not auto:
                logger.error(f"Автомобиль auto_id={booking.auto_id} не найден для booking_id={booking_id}")
                await message.answer("Автомобиль не найден.")
                await state.clear()
                return
            logger.debug(f"Данные для booking_id={booking_id}: user_id={user.id}, telegram_id={user.telegram_id}, auto_id={auto.id}")

            try:
                new_time = datetime.strptime(message.text, "%H:%M").time()
                logger.info(f"Новое время {new_time} для booking_id={booking_id}")
                booking.proposed_time = new_time
                booking.status = BookingStatus.PENDING
                session.commit()
                logger.info(f"Запись booking_id={booking_id} обновлена: proposed_time={new_time}, status=PENDING")
                try:
                    # Создаём новый FSMContext для пользователя
                    user_state = FSMContext(
                        storage=state.storage,
                        key=StorageKey(
                            bot_id=state.key.bot_id,
                            chat_id=int(user.telegram_id),
                            user_id=int(user.telegram_id)
                        )
                    )
                    await user_state.update_data(booking_id=booking_id)
                    await user_state.set_state(BookingStates.AwaitingUserConfirmation)
                    logger.debug(f"Установлено состояние AwaitingUserConfirmation для user_id={user.telegram_id}, booking_id={booking_id}")
                    await bot.send_message(
                        user.telegram_id,
                        f"Мастер предложил новое время для записи:\n"
                        f"Услуга: {booking.service_name}\n"
                        f"Дата: {booking.date.strftime('%d.%m.%Y')}\n"
                        f"Новое время: {new_time.strftime('%H:%M')}\n"
                        f"Авто: {auto.brand}, {auto.year}, {auto.license_plate}\n"
                        f"Подтвердите или отклоните:",
                        reply_markup=Keyboards.confirm_reschedule_kb(booking_id)
                    )
                    logger.info(f"Уведомление о новом времени отправлено пользователю {user.telegram_id} для booking_id={booking_id}")
                    await message.answer("Новое время отправлено пользователю. Ожидается подтверждение.")
                except TelegramForbiddenError:
                    logger.error(f"Не удалось отправить уведомление пользователю {user.telegram_id}: пользователь заблокировал бота")
                    await message.answer("Ошибка: пользователь заблокировал бота.")
                except TelegramBadRequest as e:
                    logger.error(f"Ошибка Telegram API при отправке уведомления пользователю {user.telegram_id}: {str(e)}")
                    await message.answer("Ошибка Telegram API при отправке сообщения.")
                except Exception as e:
                    logger.error(f"Ошибка отправки уведомления пользователю {user.telegram_id} для booking_id={booking_id}: {str(e)}")
                    await message.answer("Ошибка отправки уведомления пользователю.")
            except ValueError:
                logger.warning(f"Некорректный формат времени '{message.text}' для booking_id={booking_id}")
                await message.answer("Некорректный формат времени. Введите снова (например, 14:30):")
                return
        await state.clear()
        logger.debug(f"Состояние FSM мастера очищено для booking_id={booking_id}")
    except Exception as e:
        logger.error(f"Критическая ошибка обработки нового времени для booking_id={booking_id}: {str(e)}")
        await message.answer("Критическая ошибка. Попробуйте снова.")
        await state.clear()

@service_booking_router.message(BookingStates.AwaitingMasterResponse, F.text)
async def process_master_rejection(message: Message, state: FSMContext, bot):
    """Обрабатывает причину отказа мастера."""
    if str(message.from_user.id) != ADMIN_ID:
        logger.debug(f"Неавторизованный доступ к process_master_rejection от user_id={message.from_user.id}")
        return
    data = await state.get_data()
    logger.debug(f"FSM state in process_master_rejection: {data}")
    if "booking_id" not in data or "master_action" not in data or data["master_action"] != "reject":
        logger.error(f"Некорректные данные состояния FSM: {data}")
        await message.answer("Ошибка: данные состояния отсутствуют. Попробуйте снова.")
        await state.clear()
        return
    booking_id = data.get("booking_id")
    logger.info(f"Обработка причины отказа для booking_id={booking_id}")

    try:
        with Session() as session:
            booking = session.query(Booking).get(booking_id)
            if not booking:
                logger.error(f"Запись booking_id={booking_id} не найдена")
                await message.answer("Запись не найдена.")
                await state.clear()
                return
            user = session.query(User).get(booking.user_id)
            if not user:
                logger.error(f"Пользователь user_id={booking.user_id} не найден для booking_id={booking_id}")
                await message.answer("Пользователь не найден.")
                await state.clear()
                return
            auto = session.query(Auto).get(booking.auto_id)
            if not auto:
                logger.error(f"Автомобиль auto_id={booking.auto_id} не найден для booking_id={booking_id}")
                await message.answer("Автомобиль не найден.")
                await state.clear()
                return
            booking.status = BookingStatus.REJECTED
            booking.rejection_reason = message.text
            session.commit()
            logger.info(f"Запись booking_id={booking_id} отклонена: reason={message.text}")
            try:
                await bot.send_message(
                    user.telegram_id,
                    f"Ваша запись отклонена.\n"
                    f"Причина: {message.text}\n"
                    f"Услуга: {booking.service_name}\n"
                    f"Дата: {booking.date.strftime('%d.%m.%Y')}\n"
                    f"Время: {booking.time.strftime('%H:%M')}"
                )
                logger.info(f"Уведомление об отказе отправлено пользователю {user.telegram_id} для booking_id={booking_id}")
                await message.answer("Отказ отправлен пользователю.")
            except TelegramForbiddenError:
                logger.error(f"Не удалось отправить уведомление об отказе пользователю {user.telegram_id}: пользователь заблокировал бота")
                await message.answer("Ошибка: пользователь заблокировал бота.")
            except Exception as e:
                logger.error(f"Ошибка отправки уведомления об отказе пользователю {user.telegram_id}: {str(e)}")
                await message.answer("Ошибка отправки уведомления пользователю.")
        await state.clear()
        logger.debug(f"Состояние FSM очищено для booking_id={booking_id}")
    except Exception as e:
        logger.error(f"Критическая ошибка обработки причины отказа для booking_id={booking_id}: {str(e)}")
        await message.answer("Критическая ошибка. Попробуйте снова.")
        await state.clear()

@service_booking_router.callback_query(F.data.startswith("confirm_reschedule_"))
async def process_user_confirmation(callback: CallbackQuery, state: FSMContext, bot):
    """Обрабатывает подтверждение пользователем нового времени."""
    logger.debug(f"Попытка подтверждения пользователем user_id={callback.from_user.id} для callback_data={callback.data}")
    booking_id = int(callback.data.replace("confirm_reschedule_", ""))
    try:
        with Session() as session:
            booking = session.query(Booking).get(booking_id)
            if not booking:
                logger.error(f"Запись booking_id={booking_id} не найдена")
                await delete_previous_message(bot, callback.message.chat.id, (await state.get_data()).get("last_message_id"))
                sent_message = await callback.message.answer("Запись не найдена.", reply_markup=Keyboards.main_menu_kb())
                await state.update_data(last_message_id=sent_message.message_id)
                await state.clear()
                await callback.answer()
                return
            if str(callback.from_user.id) != str(booking.user.telegram_id):
                logger.warning(f"Несанкционированный доступ: user_id={callback.from_user.id} не соответствует telegram_id={booking.user.telegram_id}")
                await callback.answer("Доступ только для владельца записи.")
                return
            user = session.query(User).get(booking.user_id)
            auto = session.query(Auto).get(booking.auto_id)
            if not booking.proposed_time:
                logger.error(f"Предложенное время отсутствует для booking_id={booking_id}")
                await delete_previous_message(bot, callback.message.chat.id, (await state.get_data()).get("last_message_id"))
                sent_message = await callback.message.answer("Ошибка: предложенное время не найдено.", reply_markup=Keyboards.main_menu_kb())
                await state.update_data(last_message_id=sent_message.message_id)
                await state.clear()
                await callback.answer()
                return
            booking.time = booking.proposed_time
            booking.proposed_time = None
            booking.status = BookingStatus.CONFIRMED
            session.commit()
            logger.info(f"Запись booking_id={booking_id} подтверждена пользователем: time={booking.time}, status=CONFIRMED")
            try:
                await bot.send_message(
                    ADMIN_ID,
                    f"Пользователь {user.first_name} {user.last_name} подтвердил запись:\n"
                    f"Услуга: {booking.service_name}\n"
                    f"Дата: {booking.date.strftime('%d.%m.%Y')}\n"
                    f"Время: {booking.time.strftime('%H:%M')}\n"
                    f"Авто: {auto.brand}, {auto.year}, {auto.license_plate}"
                )
                logger.info(f"Уведомление о подтверждении отправлено мастеру для booking_id={booking_id}")
            except Exception as e:
                logger.error(f"Ошибка отправки уведомления мастеру для booking_id={booking_id}: {str(e)}")
            await delete_previous_message(bot, callback.message.chat.id, (await state.get_data()).get("last_message_id"))
            sent_message = await callback.message.answer(
                f"Вы подтвердили запись:\n"
                f"Услуга: {booking.service_name}\n"
                f"Дата: {booking.date.strftime('%d.%m.%Y')}\n"
                f"Время: {booking.time.strftime('%H:%M')}\n"
                f"Авто: {auto.brand}, {auto.year}, {auto.license_plate}",
                reply_markup=Keyboards.main_menu_kb()
            )
            await state.update_data(last_message_id=sent_message.message_id)
            await callback.answer("Запись подтверждена.")
            await state.clear()
            logger.debug(f"Состояние FSM очищено для booking_id={booking_id}")
    except Exception as e:
        logger.error(f"Ошибка подтверждения записи пользователем для booking_id={booking_id}: {str(e)}")
        await delete_previous_message(bot, callback.message.chat.id, (await state.get_data()).get("last_message_id"))
        sent_message = await callback.message.answer("Ошибка. Попробуйте снова.", reply_markup=Keyboards.main_menu_kb())
        await state.update_data(last_message_id=sent_message.message_id)
        await state.clear()
        await callback.answer()

@service_booking_router.callback_query(F.data.startswith("reject_reschedule_"))
async def process_user_rejection(callback: CallbackQuery, state: FSMContext, bot):
    """Обрабатывает отклонение пользователем нового времени."""
    logger.debug(f"Попытка отклонения пользователем user_id={callback.from_user.id} для callback_data={callback.data}")
    booking_id = int(callback.data.replace("reject_reschedule_", ""))
    try:
        with Session() as session:
            booking = session.query(Booking).get(booking_id)
            if not booking:
                logger.error(f"Запись booking_id={booking_id} не найдена")
                await delete_previous_message(bot, callback.message.chat.id, (await state.get_data()).get("last_message_id"))
                sent_message = await callback.message.answer("Запись не найдена.", reply_markup=Keyboards.main_menu_kb())
                await state.update_data(last_message_id=sent_message.message_id)
                await state.clear()
                await callback.answer()
                return
            if str(callback.from_user.id) != str(booking.user.telegram_id):
                logger.warning(f"Несанкционированный доступ: user_id={callback.from_user.id} не соответствует telegram_id={booking.user.telegram_id}")
                await callback.answer("Доступ только для владельца записи.")
                return
            user = session.query(User).get(booking.user_id)
            auto = session.query(Auto).get(booking.auto_id)
            booking.status = BookingStatus.REJECTED
            booking.rejection_reason = "Пользователь отклонил предложенное время"
            booking.proposed_time = None
            session.commit()
            logger.info(f"Запись booking_id={booking_id} отклонена пользователем: reason={booking.rejection_reason}")
            try:
                await bot.send_message(
                    ADMIN_ID,
                    f"Пользователь {user.first_name} {user.last_name} отклонил запись:\n"
                    f"Услуга: {booking.service_name}\n"
                    f"Дата: {booking.date.strftime('%d.%m.%Y')}\n"
                    f"Предложенное время: {booking.time.strftime('%H:%M')}\n"
                    f"Авто: {auto.brand}, {auto.year}, {auto.license_plate}\n"
                    f"Причина: Пользователь отклонил предложенное время"
                )
                logger.info(f"Уведомление об отказе отправлено мастеру для booking_id={booking_id}")
            except Exception as e:
                logger.error(f"Ошибка отправки уведомления мастеру для booking_id={booking_id}: {str(e)}")
            await delete_previous_message(bot, callback.message.chat.id, (await state.get_data()).get("last_message_id"))
            sent_message = await callback.message.answer(
                f"Вы отклонили предложенное время для записи:\n"
                f"Услуга: {booking.service_name}\n"
                f"Дата: {booking.date.strftime('%d.%m.%Y')}\n"
                f"Авто: {auto.brand}, {auto.year}, {auto.license_plate}",
                reply_markup=Keyboards.main_menu_kb()
            )
            await state.update_data(last_message_id=sent_message.message_id)
            await callback.answer("Запись отклонена.")
            await state.clear()
            logger.debug(f"Состояние FSM очищено для booking_id={booking_id}")
    except Exception as e:
        logger.error(f"Ошибка отклонения записи пользователем для booking_id={booking_id}: {str(e)}")
        await delete_previous_message(bot, callback.message.chat.id, (await state.get_data()).get("last_message_id"))
        sent_message = await callback.message.answer("Ошибка. Попробуйте снова.", reply_markup=Keyboards.main_menu_kb())
        await state.update_data(last_message_id=sent_message.message_id)
        await state.clear()
        await callback.answer()

@service_booking_router.callback_query(F.data == "cancel_booking")
async def cancel_booking(callback: CallbackQuery, state: FSMContext, bot):
    await delete_previous_message(bot, callback.message.chat.id, (await state.get_data()).get("last_message_id"))
    sent_message = await callback.message.answer("Действие отменено.", reply_markup=Keyboards.main_menu_kb())
    await state.update_data(last_message_id=sent_message.message_id)
    await state.clear()
    await callback.answer()
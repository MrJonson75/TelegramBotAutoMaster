from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, FSInputFile
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from config import Config
from keyboards.main_kb import Keyboards
from utils import setup_logger
from database import init_db, User, Auto, Booking, BookingStatus
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
import re
import asyncio

service_booking_router = Router()
logger = setup_logger(__name__)
Session = init_db()

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

def validate_phone(phone: str) -> bool:
    """Проверяет формат номера телефона."""
    pattern = r"^\+?\d{10,15}$"
    return bool(re.match(pattern, phone))

def validate_vin(vin: str) -> bool:
    """Проверяет формат VIN (17 символов)."""
    return len(vin) == 17 and vin.isalnum()

def validate_year(year: str) -> bool:
    """Проверяет год выпуска автомобиля."""
    try:
        year_int = int(year)
        return 1900 <= year_int <= datetime.today().year
    except ValueError:
        return False

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
        await bot.send_message(Config.ADMIN_ID, message, reply_markup=Keyboards.bookings_kb([booking]))
    except Exception as e:
        logger.error(f"Ошибка отправки уведомления мастеру: {str(e)}")

async def schedule_reminder(bot, booking: Booking, user: User, auto: Auto):
    """Запланировать напоминание мастеру."""
    booking_datetime = datetime.combine(booking.date, booking.time)
    reminder_time = booking_datetime - timedelta(minutes=Config.REMINDER_TIME_MINUTES)
    now = datetime.now()
    if reminder_time > now:
        delay = (reminder_time - now).total_seconds()
        await asyncio.sleep(delay)
        try:
            await bot.send_message(
                Config.ADMIN_ID,
                f"Напоминание: Через {Config.REMINDER_TIME_MINUTES} минут запись:\n"
                f"Пользователь: {user.first_name} {user.last_name}\n"
                f"Авто: {auto.brand}, {auto.year}\n"
                f"Услуга: {booking.service_name}\n"
                f"Дата: {booking.date.strftime('%d.%m.%Y')}\n"
                f"Время: {booking.time.strftime('%H:%M')}"
            )
        except Exception as e:
            logger.error(f"Ошибка отправки напоминания мастеру: {str(e)}")

@service_booking_router.message(F.text == "Запись на ТО")
async def start_booking(message: Message, state: FSMContext):
    """Запускает процесс записи на ТО."""
    logger.info(f"User {message.from_user.id} started booking")
    try:
        with Session() as session:
            user = session.query(User).filter_by(telegram_id=str(message.from_user.id)).first()
            if user:
                autos = session.query(Auto).filter_by(user_id=user.id).all()
                if autos:
                    try:
                        photo_path = Config.get_photo_path("booking")
                        await message.answer_photo(
                            photo=FSInputFile(photo_path),
                            caption="Выберите автомобиль для записи на ТО:",
                            reply_markup=Keyboards.auto_selection_kb(autos)
                        )
                    except (FileNotFoundError, ValueError) as e:
                        logger.error(f"Ошибка загрузки фото для бронирования: {str(e)}")
                        await message.answer(
                            "Выберите автомобиль для записи на ТО:",
                            reply_markup=Keyboards.auto_selection_kb(autos)
                        )
                    await state.set_state(BookingStates.AwaitingAutoSelection)
                else:
                    await message.answer(
                        "У вас нет зарегистрированных автомобилей. Введите марку автомобиля:"
                    )
                    await state.set_state(BookingStates.AwaitingAutoBrand)
            else:
                await message.answer(
                    "Для записи на ТО необходимо зарегистрироваться.\nВведите ваше имя:"
                )
                await state.set_state(BookingStates.AwaitingFirstName)
    except Exception as e:
        logger.error(f"Ошибка проверки пользователя: {str(e)}")
        await message.answer("Ошибка. Попробуйте снова.", reply_markup=Keyboards.main_menu_kb())
        await state.clear()

@service_booking_router.callback_query(BookingStates.AwaitingAutoSelection, F.data.startswith("auto_"))
async def process_auto_selection(callback: CallbackQuery, state: FSMContext):
    """Обрабатывает выбор автомобиля."""
    auto_id = int(callback.data.replace("auto_", ""))
    try:
        with Session() as session:
            auto = session.query(Auto).get(auto_id)
            if not auto:
                await callback.message.answer("Автомобиль не найден. Попробуйте снова:",
                                              reply_markup=Keyboards.main_menu_kb())
                await state.clear()
                await callback.answer()
                return
            await state.update_data(auto_id=auto_id)
            try:
                photo_path = Config.get_photo_path("booking_menu")
                await callback.message.answer_photo(
                    photo=FSInputFile(photo_path),
                    caption=Config.MESSAGES["booking"],
                    reply_markup=Keyboards.services_kb()
                )
            except (FileNotFoundError, ValueError) as e:
                logger.error(f"Ошибка загрузки фото для бронирования: {str(e)}")
                await callback.message.answer(
                    Config.MESSAGES["booking"],
                    reply_markup=Keyboards.services_kb()
                )
            await state.set_state(BookingStates.AwaitingService)
            await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка выбора автомобиля: {str(e)}")
        await callback.message.answer("Ошибка. Попробуйте снова.", reply_markup=Keyboards.main_menu_kb())
        await state.clear()
        await callback.answer()

@service_booking_router.callback_query(BookingStates.AwaitingAutoSelection, F.data == "add_new_auto")
async def add_new_auto(callback: CallbackQuery, state: FSMContext):
    """Обрабатывает выбор добавления нового автомобиля."""
    await callback.message.answer("Введите марку автомобиля:")
    await state.set_state(BookingStates.AwaitingAutoBrand)
    await callback.answer()

@service_booking_router.message(BookingStates.AwaitingFirstName, F.text)
async def process_first_name(message: Message, state: FSMContext):
    """Обрабатывает имя пользователя."""
    first_name = message.text.strip()
    if len(first_name) < 2:
        await message.answer("Имя слишком короткое. Введите снова:")
        return
    await state.update_data(first_name=first_name)
    await message.answer("Введите вашу фамилию:")
    await state.set_state(BookingStates.AwaitingLastName)

@service_booking_router.message(BookingStates.AwaitingLastName, F.text)
async def process_last_name(message: Message, state: FSMContext):
    """Обрабатывает фамилию пользователя."""
    last_name = message.text.strip()
    if len(last_name) < 2:
        await message.answer("Фамилия слишком короткая. Введите снова:")
        return
    await state.update_data(last_name=last_name)
    await message.answer("Введите ваш номер телефона (например, +79991234567):")
    await state.set_state(BookingStates.AwaitingPhone)

@service_booking_router.message(BookingStates.AwaitingPhone, F.text)
async def process_phone(message: Message, state: FSMContext):
    """Обрабатывает номер телефона."""
    phone = message.text.strip()
    if not validate_phone(phone):
        await message.answer("Некорректный номер телефона. Введите снова (например, +79991234567):")
        return
    data = await state.get_data()
    try:
        with Session() as session:
            user = User(
                first_name=data["first_name"],
                last_name=data["last_name"],
                phone=phone,
                telegram_id=str(message.from_user.id)
            )
            session.add(user)
            session.commit()
            logger.info(f"User {message.from_user.id} registered")
        await message.answer("Введите марку автомобиля:")
        await state.set_state(BookingStates.AwaitingAutoBrand)
    except Exception as e:
        logger.error(f"Ошибка регистрации пользователя: {str(e)}")
        await message.answer("Ошибка регистрации. Попробуйте снова.", reply_markup=Keyboards.main_menu_kb())
        await state.clear()

@service_booking_router.message(BookingStates.AwaitingAutoBrand, F.text)
async def process_auto_brand(message: Message, state: FSMContext):
    """Обрабатывает марку автомобиля."""
    brand = message.text.strip()
    if len(brand) < 2:
        await message.answer("Марка слишком короткая. Введите снова:")
        return
    await state.update_data(brand=brand)
    await message.answer("Введите год выпуска автомобиля (например, 2020):")
    await state.set_state(BookingStates.AwaitingAutoYear)

@service_booking_router.message(BookingStates.AwaitingAutoYear, F.text)
async def process_auto_year(message: Message, state: FSMContext):
    """Обрабатывает год выпуска автомобиля."""
    year = message.text.strip()
    if not validate_year(year):
        await message.answer(f"Некорректный год. Введите снова (1900–{datetime.today().year}):")
        return
    await state.update_data(year=int(year))
    await message.answer("Введите VIN-номер автомобиля (17 символов):")
    await state.set_state(BookingStates.AwaitingAutoVin)

@service_booking_router.message(BookingStates.AwaitingAutoVin, F.text)
async def process_auto_vin(message: Message, state: FSMContext):
    """Обрабатывает VIN-номер."""
    vin = message.text.strip().upper()
    if not validate_vin(vin):
        await message.answer("Некорректный VIN (должен быть 17 символов, буквы и цифры). Введите снова:")
        return
    await state.update_data(vin=vin)
    await message.answer("Введите государственный номер автомобиля:")
    await state.set_state(BookingStates.AwaitingAutoLicensePlate)

@service_booking_router.message(BookingStates.AwaitingAutoLicensePlate, F.text)
async def process_auto_license_plate(message: Message, state: FSMContext):
    """Обрабатывает госномер автомобиля."""
    license_plate = message.text.strip()
    if len(license_plate) < 5:
        await message.answer("Госномер слишком короткий. Введите снова:")
        return
    data = await state.get_data()
    try:
        with Session() as session:
            user = session.query(User).filter_by(telegram_id=str(message.from_user.id)).first()
            auto = Auto(
                user_id=user.id,
                brand=data["brand"],
                year=data["year"],
                vin=data["vin"],
                license_plate=license_plate
            )
            session.add(auto)
            session.commit()
            logger.info(f"Auto added for user {message.from_user.id}")
            await state.update_data(auto_id=auto.id)
        await message.answer(
            "Автомобиль добавлен. Хотите добавить ещё один автомобиль или продолжить?",
            reply_markup=Keyboards.add_another_auto_kb()
        )
        await state.set_state(BookingStates.AwaitingAddAnotherAuto)
    except Exception as e:
        logger.error(f"Ошибка добавления автомобиля: {str(e)}")
        await message.answer("Ошибка добавления автомобиля. Попробуйте снова.", reply_markup=Keyboards.main_menu_kb())
        await state.clear()

@service_booking_router.callback_query(BookingStates.AwaitingAddAnotherAuto, F.data == "add_another_auto")
async def add_another_auto(callback: CallbackQuery, state: FSMContext):
    """Обрабатывает выбор добавления ещё одного автомобиля."""
    await callback.message.answer("Введите марку автомобиля:")
    await state.set_state(BookingStates.AwaitingAutoBrand)
    await callback.answer()

@service_booking_router.callback_query(BookingStates.AwaitingAddAnotherAuto, F.data == "continue_booking")
async def continue_booking(callback: CallbackQuery, state: FSMContext):
    """Продолжает процесс бронирования."""
    try:
        photo_path = Config.get_photo_path("booking_final")
        await callback.message.answer_photo(
            photo=FSInputFile(photo_path),
            caption=Config.MESSAGES["booking"],
            reply_markup=Keyboards.services_kb()
        )
        await state.set_state(BookingStates.AwaitingService)
        await callback.answer()
    except (FileNotFoundError, ValueError) as e:
        logger.error(f"Ошибка загрузки фото для бронирования: {str(e)}")
        await callback.message.answer(
            Config.MESSAGES["booking"],
            reply_markup=Keyboards.services_kb()
        )
        await state.set_state(BookingStates.AwaitingService)
        await callback.answer()

@service_booking_router.callback_query(BookingStates.AwaitingService, F.data.startswith("service_"))
async def process_service_selection(callback: CallbackQuery, state: FSMContext):
    """Обрабатывает выбор услуги."""
    service_name = callback.data.replace("service_", "")
    if service_name not in [s["name"] for s in Config.SERVICES]:
        await callback.message.answer("Некорректная услуга. Выберите снова:", reply_markup=Keyboards.services_kb())
        await callback.answer()
        return
    service_duration = next(s["duration_minutes"] for s in Config.SERVICES if s["name"] == service_name)
    await state.update_data(service_name=service_name, service_duration=service_duration)
    await callback.message.answer(
        "Выберите дату для записи:",
        reply_markup=Keyboards.calendar_kb()
    )
    await state.set_state(BookingStates.AwaitingDate)
    await callback.answer()

@service_booking_router.callback_query(BookingStates.AwaitingDate, F.data.startswith("date_"))
async def process_date_selection(callback: CallbackQuery, state: FSMContext):
    """Обрабатывает выбор даты."""
    date_str = callback.data.replace("date_", "")
    try:
        selected_date = datetime.strptime(date_str, "%Y-%m-%d")
        data = await state.get_data()
        with Session() as session:
            time_slots = Keyboards.time_slots_kb(selected_date, data["service_duration"], session)
            if not time_slots.inline_keyboard:
                await callback.message.answer(
                    "Нет доступных слотов на эту дату. Выберите другую дату:",
                    reply_markup=Keyboards.calendar_kb(selected_date)
                )
                await callback.answer()
                return
            await state.update_data(selected_date=selected_date)
            await callback.message.answer(
                "Выберите время для записи:",
                reply_markup=time_slots
            )
            await state.set_state(BookingStates.AwaitingTime)
            await callback.answer()
    except ValueError:
        await callback.message.answer("Некорректная дата. Выберите снова:", reply_markup=Keyboards.calendar_kb())
        await callback.answer()

@service_booking_router.callback_query(BookingStates.AwaitingTime, F.data.startswith("time_"))
async def process_time_selection(callback: CallbackQuery, state: FSMContext, bot):
    """Обрабатывает выбор времени и создаёт запись."""
    time_str = callback.data.replace("time_", "")
    try:
        selected_time = datetime.strptime(time_str, "%H:%M").time()
        data = await state.get_data()
        with Session() as session:
            user = session.query(User).filter_by(telegram_id=str(callback.from_user.id)).first()
            auto = session.query(Auto).get(data["auto_id"])
            if not auto:
                await callback.message.answer("Автомобиль не найден. Начните заново.",
                                              reply_markup=Keyboards.main_menu_kb())
                await state.clear()
                await callback.answer()
                return
            booking = Booking(
                user_id=user.id,
                auto_id=data["auto_id"],
                service_name=data["service_name"],
                date=data["selected_date"].date(),
                time=selected_time,
                status=BookingStatus.PENDING
            )
            session.add(booking)
            session.commit()
            logger.info(f"Booking created: {booking.id} for user {callback.from_user.id}")
            await notify_master(bot, booking, user, auto)
            asyncio.create_task(schedule_reminder(bot, booking, user, auto))
            await callback.message.answer(
                "Ваша заявка отправлена мастеру. Ожидайте подтверждения.",
                reply_markup=Keyboards.main_menu_kb()
            )
            await state.set_state(BookingStates.AwaitingMasterResponse)
            await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка создания записи: {str(e)}")
        await callback.message.answer("Ошибка записи. Попробуйте снова.", reply_markup=Keyboards.main_menu_kb())
        await state.clear()
        await callback.answer()

@service_booking_router.callback_query(F.data.startswith("confirm_booking_"))
async def confirm_booking(callback: CallbackQuery, state: FSMContext, bot):
    """Мастер подтверждает запись."""
    if str(callback.from_user.id) != Config.ADMIN_ID:
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
            await bot.send_message(
                user.telegram_id,
                f"Ваша запись подтверждена!\n"
                f"Услуга: {booking.service_name}\n"
                f"Дата: {booking.date.strftime('%d.%m.%Y')}\n"
                f"Время: {booking.time.strftime('%H:%M')}\n"
                f"Авто: {auto.brand}, {auto.year}, {auto.license_plate}"
            )
            await callback.message.edit_text(
                callback.message.text + "\nСтатус: Подтверждено"
            )
            await callback.answer("Запись подтверждена.")
    except Exception as e:
        logger.error(f"Ошибка подтверждения записи: {str(e)}")
        await callback.answer("Ошибка. Попробуйте снова.")

@service_booking_router.callback_query(F.data.startswith("reschedule_booking_"))
async def reschedule_booking(callback: CallbackQuery, state: FSMContext, bot):
    """Мастер предлагает другое время."""
    if str(callback.from_user.id) != Config.ADMIN_ID:
        await callback.answer("Доступ только для мастера.")
        return
    booking_id = int(callback.data.replace("reschedule_booking_", ""))
    await callback.message.answer("Введите новое время (например, 14:30):")
    await state.update_data(booking_id=booking_id, master_action="reschedule")
    await callback.answer()

@service_booking_router.callback_query(F.data.startswith("reject_booking_"))
async def reject_booking(callback: CallbackQuery, state: FSMContext, bot):
    """Мастер отклоняет запись."""
    if str(callback.from_user.id) != Config.ADMIN_ID:
        await callback.answer("Доступ только для мастера.")
        return
    booking_id = int(callback.data.replace("reject_booking_", ""))
    await callback.message.answer("Укажите причину отказа:")
    await state.update_data(booking_id=booking_id, master_action="reject")
    await callback.answer()

@service_booking_router.message(F.text, F.state.in_([None, BookingStates.AwaitingMasterResponse]))
async def process_master_response(message: Message, state: FSMContext, bot):
    """Обрабатывает ответ мастера (новое время или причина отказа)."""
    if str(message.from_user.id) != Config.ADMIN_ID:
        return
    data = await state.get_data()
    if "master_action" not in data:
        return
    booking_id = data.get("booking_id")
    try:
        with Session() as session:
            booking = session.query(Booking).get(booking_id)
            if not booking:
                await message.answer("Запись не найдена.")
                return
            user = session.query(User).get(booking.user_id)
            auto = session.query(Auto).get(booking.auto_id)
            if data["master_action"] == "reschedule":
                try:
                    new_time = datetime.strptime(message.text, "%H:%M").time()
                    booking.time = new_time
                    booking.status = BookingStatus.CONFIRMED
                    session.commit()
                    await bot.send_message(
                        user.telegram_id,
                        f"Мастер предложил новое время для записи:\n"
                        f"Услуга: {booking.service_name}\n"
                        f"Дата: {booking.date.strftime('%d.%m.%Y')}\n"
                        f"Новое время: {booking.time.strftime('%H:%M')}\n"
                        f"Авто: {auto.brand}, {auto.year}, {auto.license_plate}"
                    )
                    await message.answer("Новое время отправлено пользователю.")
                except ValueError:
                    await message.answer("Некорректный формат времени. Введите снова (например, 14:30):")
                    return
            elif data["master_action"] == "reject":
                booking.status = BookingStatus.REJECTED
                booking.rejection_reason = message.text
                session.commit()
                await bot.send_message(
                    user.telegram_id,
                    f"Ваша запись отклонена.\n"
                    f"Причина: {message.text}\n"
                    f"Услуга: {booking.service_name}\n"
                    f"Дата: {booking.date.strftime('%d.%m.%Y')}\n"
                    f"Время: {booking.time.strftime('%H:%M')}"
                )
                await message.answer("Отказ отправлен пользователю.")
        await state.clear()
    except Exception as e:
        logger.error(f"Ошибка обработки ответа мастера: {str(e)}")
        await message.answer("Ошибка. Попробуйте снова.")
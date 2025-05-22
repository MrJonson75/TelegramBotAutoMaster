from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, FSInputFile, InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from config import Config
from keyboards.main_kb import Keyboards
from utils import setup_logger
from database import init_db, User, Auto, Booking, BookingStatus
from sqlalchemy.orm import Session
from datetime import datetime
import re

my_bookings_router = Router()
logger = setup_logger(__name__)
Session = init_db()

# Состояния FSM для регистрации
class RegistrationStates(StatesGroup):
    AwaitingFirstName = State()
    AwaitingLastName = State()
    AwaitingPhone = State()
    AwaitingAutoBrand = State()
    AwaitingAutoYear = State()
    AwaitingAutoVin = State()
    AwaitingAutoLicensePlate = State()
    AwaitingAddAnotherAuto = State()

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

async def notify_master_of_cancellation(bot, booking: Booking, user: User, auto: Auto):
    """Уведомляет мастера об отмене записи."""
    try:
        await bot.send_message(
            Config.ADMIN_ID,
            f"Пользователь отменил запись:\n"
            f"Пользователь: {user.first_name} {user.last_name}\n"
            f"Телефон: {user.phone}\n"
            f"Авто: {auto.brand}, {auto.year}, {auto.license_plate}\n"
            f"Услуга: {booking.service_name}\n"
            f"Дата: {booking.date.strftime('%d.%m.%Y')}\n"
            f"Время: {booking.time.strftime('%H:%M')}"
        )
    except Exception as e:
        logger.error(f"Ошибка уведомления мастера об отмене: {str(e)}")

@my_bookings_router.message(F.text == "Мои записи")
async def show_my_bookings(message: Message, state: FSMContext):
    """Отображает список записей пользователя."""
    logger.info(f"User {message.from_user.id} requested bookings")
    try:
        with Session() as session:
            user = session.query(User).filter_by(telegram_id=str(message.from_user.id)).first()
            if not user:
                await message.answer(
                    "Для просмотра записей необходимо зарегистрироваться.\nВведите ваше имя:"
                )
                await state.set_state(RegistrationStates.AwaitingFirstName)
                return
            bookings = session.query(Booking).filter_by(user_id=user.id).order_by(Booking.created_at.desc()).all()
            if not bookings:
                await message.answer(
                    "У вас нет записей в RemDiesel.",
                    reply_markup=Keyboards.main_menu_kb()
                )
                await state.clear()
                return
            try:
                photo_path = Config.get_photo_path("bookings")
                await message.answer_photo(
                    photo=FSInputFile(photo_path),
                    caption=Config.MESSAGES["my_bookings"],
                    reply_markup=Keyboards.bookings_kb(bookings)
                )
            except (FileNotFoundError, ValueError) as e:
                logger.error(f"Ошибка загрузки фото для записей: {str(e)}")
                await message.answer(
                    Config.MESSAGES["my_bookings"],
                    reply_markup=Keyboards.bookings_kb(bookings)
                )
    except Exception as e:
        logger.error(f"Ошибка получения записей: {str(e)}")
        await message.answer("Ошибка. Попробуйте снова.", reply_markup=Keyboards.main_menu_kb())
        await state.clear()

@my_bookings_router.message(RegistrationStates.AwaitingFirstName, F.text)
async def process_first_name(message: Message, state: FSMContext):
    """Обрабатывает имя пользователя."""
    first_name = message.text.strip()
    if len(first_name) < 2:
        await message.answer("Имя слишком короткое. Введите снова:")
        return
    await state.update_data(first_name=first_name)
    await message.answer("Введите вашу фамилию:")
    await state.set_state(RegistrationStates.AwaitingLastName)

@my_bookings_router.message(RegistrationStates.AwaitingLastName, F.text)
async def process_last_name(message: Message, state: FSMContext):
    """Обрабатывает фамилию пользователя."""
    last_name = message.text.strip()
    if len(last_name) < 2:
        await message.answer("Фамилия слишком короткая. Введите снова:")
        return
    await state.update_data(last_name=last_name)
    await message.answer("Введите ваш номер телефона (например, +79991234567):")
    await state.set_state(RegistrationStates.AwaitingPhone)

@my_bookings_router.message(RegistrationStates.AwaitingPhone, F.text)
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
        await state.set_state(RegistrationStates.AwaitingAutoBrand)
    except Exception as e:
        logger.error(f"Ошибка регистрации пользователя: {str(e)}")
        await message.answer("Ошибка регистрации. Попробуйте снова.", reply_markup=Keyboards.main_menu_kb())
        await state.clear()

@my_bookings_router.message(RegistrationStates.AwaitingAutoBrand, F.text)
async def process_auto_brand(message: Message, state: FSMContext):
    """Обрабатывает марку автомобиля."""
    brand = message.text.strip()
    if len(brand) < 2:
        await message.answer("Марка слишком короткая. Введите снова:")
        return
    await state.update_data(brand=brand)
    await message.answer("Введите год выпуска автомобиля (например, 2020):")
    await state.set_state(RegistrationStates.AwaitingAutoYear)

@my_bookings_router.message(RegistrationStates.AwaitingAutoYear, F.text)
async def process_auto_year(message: Message, state: FSMContext):
    """Обрабатывает год выпуска автомобиля."""
    year = message.text.strip()
    if not validate_year(year):
        await message.answer(f"Некорректный год. Введите снова (1900–{datetime.today().year}):")
        return
    await state.update_data(year=int(year))
    await message.answer("Введите VIN-номер автомобиля (17 символов):")
    await state.set_state(RegistrationStates.AwaitingAutoVin)

@my_bookings_router.message(RegistrationStates.AwaitingAutoVin, F.text)
async def process_auto_vin(message: Message, state: FSMContext):
    """Обрабатывает VIN-номер."""
    vin = message.text.strip().upper()
    if not validate_vin(vin):
        await message.answer("Некорректный VIN (должен быть 17 символов, буквы и цифры). Введите снова:")
        return
    await state.update_data(vin=vin)
    await message.answer("Введите государственный номер автомобиля:")
    await state.set_state(RegistrationStates.AwaitingAutoLicensePlate)

@my_bookings_router.message(RegistrationStates.AwaitingAutoLicensePlate, F.text)
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
        await message.answer(
            "Автомобиль добавлен. Хотите добавить ещё один автомобиль или продолжить?",
            reply_markup=Keyboards.add_another_auto_kb()
        )
        await state.set_state(RegistrationStates.AwaitingAddAnotherAuto)
    except Exception as e:
        logger.error(f"Ошибка добавления автомобиля: {str(e)}")
        await message.answer("Ошибка добавления автомобиля. Попробуйте снова.", reply_markup=Keyboards.main_menu_kb())
        await state.clear()

@my_bookings_router.callback_query(RegistrationStates.AwaitingAddAnotherAuto, F.data == "add_another_auto")
async def add_another_auto(callback: CallbackQuery, state: FSMContext):
    """Обрабатывает выбор добавления ещё одного автомобиля."""
    await callback.message.answer("Введите марку автомобиля:")
    await state.set_state(RegistrationStates.AwaitingAutoBrand)
    await callback.answer()

@my_bookings_router.callback_query(RegistrationStates.AwaitingAddAnotherAuto, F.data == "continue_my_bookings")
async def continue_my_bookings(callback: CallbackQuery, state: FSMContext):
    """Продолжает просмотр записей после регистрации."""
    try:
        with Session() as session:
            user = session.query(User).filter_by(telegram_id=str(callback.from_user.id)).first()
            bookings = session.query(Booking).filter_by(user_id=user.id).order_by(Booking.created_at.desc()).all()
            if not bookings:
                await callback.message.answer(
                    "У вас нет записей в RemDiesel.",
                    reply_markup=Keyboards.main_menu_kb()
                )
                await state.clear()
                await callback.answer()
                return
            try:
                photo_path = Config.get_photo_path("bookings")
                await callback.message.answer_photo(
                    photo=FSInputFile(photo_path),
                    caption=Config.MESSAGES["my_bookings"],
                    reply_markup=Keyboards.bookings_kb(bookings)
                )
            except (FileNotFoundError, ValueError) as e:
                logger.error(f"Ошибка загрузки фото для записей: {str(e)}")
                await callback.message.answer(
                    Config.MESSAGES["my_bookings"],
                    reply_markup=Keyboards.bookings_kb(bookings)
                )
        await state.clear()
        await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка получения записей: {str(e)}")
        await callback.message.answer("Ошибка. Попробуйте снова.", reply_markup=Keyboards.main_menu_kb())
        await state.clear()
        await callback.answer()

@my_bookings_router.callback_query(F.data.startswith("view_booking_"))
async def view_booking_details(callback: CallbackQuery):
    """Отображает детали записи."""
    booking_id = int(callback.data.replace("view_booking_", ""))
    try:
        with Session() as session:
            booking = session.query(Booking).get(booking_id)
            if not booking:
                await callback.answer("Запись не найдена.")
                return
            auto = booking.auto
            user = booking.user
            if str(user.telegram_id) != str(callback.from_user.id):
                await callback.answer("Доступ только к вашим записям.")
                return
            status = {
                BookingStatus.PENDING: "⏳ Ожидает подтверждения",
                BookingStatus.CONFIRMED: "✅ Подтверждено",
                BookingStatus.REJECTED: "❌ Отклонено"
            }[booking.status]
            message = (
                f"📋 Детали записи:\n"
                f"Услуга: {booking.service_name}\n"
                f"Дата: {booking.date.strftime('%d.%m.%Y')}\n"
                f"Время: {booking.time.strftime('%H:%M')}\n"
                f"Авто: {auto.brand}, {auto.year}, {auto.license_plate}\n"
                f"Статус: {status}\n"
            )
            if booking.status == BookingStatus.REJECTED and booking.rejection_reason:
                message += f"Причина отказа: {booking.rejection_reason}\n"
            keyboard = []
            if booking.status in [BookingStatus.PENDING, BookingStatus.CONFIRMED]:
                keyboard.append([InlineKeyboardButton(text="Отменить запись", callback_data=f"cancel_booking_{booking.id}")])
            await callback.message.answer(
                message,
                reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard) if keyboard else None
            )
            await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка просмотра записи: {str(e)}")
        await callback.answer("Ошибка. Попробуйте снова.")

@my_bookings_router.callback_query(F.data.startswith("cancel_booking_"))
async def cancel_booking(callback: CallbackQuery, state: FSMContext, bot):
    """Обрабатывает отмену записи."""
    booking_id = int(callback.data.replace("cancel_booking_", ""))
    try:
        with Session() as session:
            booking = session.query(Booking).get(booking_id)
            if not booking:
                await callback.answer("Запись не найдена.")
                return
            user = booking.user
            if str(user.telegram_id) != str(callback.from_user.id):
                await callback.answer("Доступ только к вашим записям.")
                return
            if booking.status == BookingStatus.REJECTED:
                await callback.answer("Запись уже отменена.")
                return
            booking.status = BookingStatus.REJECTED
            booking.rejection_reason = "Отменено пользователем"
            session.commit()
            auto = booking.auto
            await notify_master_of_cancellation(bot, booking, user, auto)
            await callback.message.answer(
                f"Запись на {booking.service_name} ({booking.date.strftime('%d.%m.%Y')} {booking.time.strftime('%H:%M')}) отменена.",
                reply_markup=Keyboards.main_menu_kb()
            )
            await callback.answer("Запись отменена.")
    except Exception as e:
        logger.error(f"Ошибка отмены записи: {str(e)}")
        await callback.answer("Ошибка. Попробуйте снова.")
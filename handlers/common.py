from datetime import datetime

import pytz
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, FSInputFile
from sqlalchemy.orm import Session

from keyboards.main_kb import Keyboards  # Обновлённый импорт
from config import Config
from utils import setup_logger

from database import Booking, BookingStatus, User, Auto, Session

logger = setup_logger(__name__)

common_router = Router()

# Обработчик команды /start
@common_router.message(Command("start"))
async def cmd_start(message: Message):
    try:
        photo_path = Config.get_photo_path("welcome")
        await message.answer_photo(
            photo=FSInputFile(photo_path),
            caption=Config.MESSAGES["welcome"],
            reply_markup=Keyboards.main_menu_kb()  # Обновлено
        )
    except (FileNotFoundError, ValueError) as e:
        logger.error(f"Ошибка загрузки фото для /start: {str(e)}")
        await message.answer(
            Config.MESSAGES["welcome"],
            reply_markup=Keyboards.main_menu_kb()  # Обновлено
        )

# Обработчик текстового сообщения "📞 Контакты/как проехать"
@common_router.message(F.text == "📞 Контакты/как проехать")
async def show_contacts(message: Message):
    try:
        photo_path = Config.get_photo_path("contacts")
        await message.answer_photo(
            photo=FSInputFile(photo_path),
            caption=Config.MESSAGES["contacts"],
            reply_markup=Keyboards.main_menu_kb()  # Обновлено
        )
    except (FileNotFoundError, ValueError) as e:
        logger.error(f"Ошибка загрузки фото для контактов: {str(e)}")
        await message.answer(
            Config.MESSAGES["contacts"],
            reply_markup=Keyboards.main_menu_kb()  # Обновлено
        )

# Обработчик текстового сообщения "О мастере"
@common_router.message(F.text == "О мастере")
async def show_about_master(message: Message):
    try:
        photo_path = Config.get_photo_path("about_master")
        await message.answer_photo(
            photo=FSInputFile(photo_path),
            caption=Config.MESSAGES["about_master"],
            reply_markup=Keyboards.main_menu_kb()  # Обновлено
        )
    except (FileNotFoundError, ValueError) as e:
        logger.error(f"Ошибка загрузки фото для 'О мастере': {str(e)}")
        await message.answer(
            Config.MESSAGES["about_master"],
            reply_markup=Keyboards.main_menu_kb()  # Обновлено
        )

@common_router.message(Command("admin"))
async def cmd_admin(message: Message):
    if str(message.from_user.id) != Config.ADMIN_ID:
        await message.answer("Доступ только для мастера.")
        return
    try:
        with Session() as session:  # Контекстный менеджер для сессии
            tz = pytz.timezone('Asia/Dubai')
            now = datetime.now(tz)
            bookings = session.query(Booking).filter(
                Booking.status.in_([BookingStatus.PENDING, BookingStatus.CONFIRMED]),
                (Booking.date > now.date()) | (
                    (Booking.date == now.date()) & (Booking.time >= now.time())
                )
            ).order_by(Booking.date, Booking.time).all()
            if not bookings:
                await message.answer("Нет активных записей.", reply_markup=Keyboards.main_menu_kb())
                return
            response = "Активные записи:\n\n"
            for booking in bookings:
                user = session.query(User).get(booking.user_id)
                auto = session.query(Auto).get(booking.auto_id)
                status = {
                    BookingStatus.PENDING: "Ожидает",
                    BookingStatus.CONFIRMED: "Подтверждено"
                }[booking.status]
                response += (
                    f"Заявка #{booking.id}: {booking.service_name} ({booking.price} ₽), "
                    f"{user.first_name} {user.last_name}, {auto.brand} {auto.license_plate}, "
                    f"{booking.date.strftime('%d.%m.%Y')} {booking.time.strftime('%H:%M')}, {status}\n"
                )
            if len(response) > 1024:
                await message.answer(response, reply_markup=Keyboards.main_menu_kb())
                return
            try:
                photo_path = Config.get_photo_path("booking")
                await message.answer_photo(
                    photo=FSInputFile(photo_path),
                    caption=response,
                    reply_markup=Keyboards.main_menu_kb()
                )
            except (FileNotFoundError, ValueError) as e:
                logger.error(f"Ошибка загрузки фото для админ-панели: {str(e)}")
                await message.answer(response, reply_markup=Keyboards.main_menu_kb())
    except Exception as e:
        logger.error(f"Ошибка админ-панели: {str(e)}")
        await message.answer("Ошибка. Попробуйте снова.", reply_markup=Keyboards.main_menu_kb())
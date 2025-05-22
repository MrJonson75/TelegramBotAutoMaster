from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, FSInputFile
from aiogram.exceptions import TelegramForbiddenError, TelegramBadRequest
from sqlalchemy.orm import Session
from config import Config
from keyboards.main_kb import Keyboards
from utils import setup_logger
from database import init_db, User, Auto, Booking, BookingStatus
from datetime import datetime
import pytz

my_bookings_router = Router()
logger = setup_logger(__name__)
Session = init_db()

@my_bookings_router.message(F.text == "Мои записи")
async def list_bookings(message: Message):
    """Показывает список активных записей пользователя (PENDING или CONFIRMED, время не прошло) в одном сообщении с фото и клавиатурой для отмены."""
    logger.info(f"User {message.from_user.id} requested bookings")
    try:
        with Session() as session:
            user = session.query(User).filter_by(telegram_id=str(message.from_user.id)).first()
            if not user:
                await message.answer("Вы не зарегистрированы. Начните с записи на ТО.",
                                     reply_markup=Keyboards.main_menu_kb())
                return
            # Текущее время в часовом поясе +04:00
            tz = pytz.timezone('Asia/Dubai')  # +04:00
            now = datetime.now(tz)
            logger.debug(f"Current time: {now}")
            # Получаем все записи пользователя для отладки
            all_bookings = session.query(Booking).filter(
                Booking.user_id == user.id
            ).order_by(Booking.created_at.desc()).all()
            logger.debug(f"All bookings for user {message.from_user.id}: {[(b.id, b.service_name, b.date, b.time, b.status) for b in all_bookings]}")
            # Фильтруем активные записи (PENDING или CONFIRMED, время не прошло)
            bookings = session.query(Booking).filter(
                Booking.user_id == user.id,
                Booking.status.in_([BookingStatus.PENDING, BookingStatus.CONFIRMED]),
                (Booking.date > now.date()) | (
                    (Booking.date == now.date()) & (Booking.time >= now.time())
                )
            ).order_by(Booking.created_at.desc()).all()
            logger.debug(f"Filtered {len(bookings)} active bookings for user {message.from_user.id}: {[(b.id, b.service_name, b.date, b.time, b.status) for b in bookings]}")
            if not bookings:
                await message.answer("У вас нет активных записей.", reply_markup=Keyboards.main_menu_kb())
                return
            # Формируем текст для всех записей
            response = "Ваши активные записи:\n\n"
            keyboard = []
            for booking in bookings:
                auto = session.query(Auto).get(booking.auto_id)
                status = {
                    BookingStatus.PENDING: "Ожидает",
                    BookingStatus.CONFIRMED: "Подтверждено",
                    BookingStatus.REJECTED: "Отклонено"  # Для отладки, не должно использоваться
                }[booking.status]
                response += (
                    f"Заявка #{booking.id}: {booking.service_name}, "
                    f"{auto.brand} {auto.license_plate}, "
                    f"{booking.date.strftime('%d.%m.%Y')} {booking.time.strftime('%H:%M')}, "
                    f"{status}\n"
                )
                # Добавляем кнопку отмены только для PENDING или CONFIRMED
                if booking.status in [BookingStatus.PENDING, BookingStatus.CONFIRMED]:
                    keyboard.append([InlineKeyboardButton(text=f"Отменить #{booking.id}", callback_data=f"cancel_booking_{booking.id}")])
            # Проверяем длину подписи (лимит Telegram для caption — 1024 символа)
            if len(response) > 1024:
                logger.warning(f"Подпись слишком длинная ({len(response)} символов), отправляем без фото")
                await message.answer(
                    response,
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard) if keyboard else Keyboards.main_menu_kb()
                )
                return
            # Отправляем сообщение с фото
            try:
                photo_path = Config.get_photo_path("booking")
                await message.answer_photo(
                    photo=FSInputFile(photo_path),
                    caption=response,
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard) if keyboard else Keyboards.main_menu_kb()
                )
            except (FileNotFoundError, ValueError) as e:
                logger.error(f"Ошибка загрузки фото для бронирования: {str(e)}")
                await message.answer(
                    response,
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard) if keyboard else Keyboards.main_menu_kb()
                )
            except TelegramBadRequest as e:
                logger.error(f"Ошибка Telegram API: {str(e)}")
                await message.answer(
                    response,
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard) if keyboard else Keyboards.main_menu_kb()
                )
    except Exception as e:
        logger.error(f"Ошибка получения записей: {str(e)}")
        await message.answer("Ошибка при получении записей. Попробуйте снова.",
                             reply_markup=Keyboards.main_menu_kb())

@my_bookings_router.callback_query(F.data.startswith("cancel_booking_"))
async def cancel_booking(callback: CallbackQuery, bot):
    """Обрабатывает отмену записи пользователем."""
    logger.debug(f"Попытка отмены пользователем user_id={callback.from_user.id} для callback_data={callback.data}")
    booking_id = int(callback.data.replace("cancel_booking_", ""))
    try:
        with Session() as session:
            booking = session.query(Booking).get(booking_id)
            if not booking:
                logger.error(f"Запись booking_id={booking_id} не найдена")
                await callback.message.answer("Запись не найдена.", reply_markup=Keyboards.main_menu_kb())
                await callback.answer()
                return
            if str(callback.from_user.id) != str(booking.user.telegram_id):
                logger.warning(f"Несанкционированный доступ: user_id={callback.from_user.id} не соответствует telegram_id={booking.user.telegram_id}")
                await callback.answer("Доступ только для владельца записи.")
                return
            user = session.query(User).get(booking.user_id)
            auto = session.query(Auto).get(booking.auto_id)
            booking.status = BookingStatus.REJECTED
            booking.rejection_reason = "Отменено пользователем"
            booking.proposed_time = None
            session.commit()
            logger.info(f"Запись booking_id={booking_id} отменена пользователем: reason={booking.rejection_reason}")
            try:
                await bot.send_message(
                    Config.ADMIN_ID,
                    f"Пользователь {user.first_name} {user.last_name} отменил запись:\n"
                    f"Услуга: {booking.service_name}\n"
                    f"Дата: {booking.date.strftime('%d.%m.%Y')}\n"
                    f"Время: {booking.time.strftime('%H:%M')}\n"
                    f"Авто: {auto.brand}, {auto.year}, {auto.license_plate}\n"
                    f"Причина: Отменено пользователем"
                )
                logger.info(f"Уведомление об отмене отправлено мастеру для booking_id={booking_id}")
            except TelegramForbiddenError:
                logger.error(f"Не удалось отправить уведомление мастеру: мастер заблокировал бота")
            except Exception as e:
                logger.error(f"Ошибка отправки уведомления мастеру для booking_id={booking_id}: {str(e)}")
            await callback.message.edit_caption(
                caption=(
                    f"Вы отменили запись:\n"
                    f"Услуга: {booking.service_name}\n"
                    f"Дата: {booking.date.strftime('%d.%m.%Y')}\n"
                    f"Время: {booking.time.strftime('%H:%M')}\n"
                    f"Авто: {auto.brand}, {auto.year}, {auto.license_plate}"
                ),
                reply_markup=None
            )
            await callback.answer("Запись отменена.")
    except Exception as e:
        logger.error(f"Ошибка отмены записи пользователем для booking_id={booking_id}: {str(e)}")
        await callback.message.answer("Ошибка. Попробуйте снова.", reply_markup=Keyboards.main_menu_kb())
        await callback.answer()
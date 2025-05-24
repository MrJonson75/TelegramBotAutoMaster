from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, FSInputFile, InlineKeyboardButton, InlineKeyboardMarkup
from config import get_photo_path, ADMIN_ID
from database import Session, User, Auto, Booking, BookingStatus
from keyboards.main_kb import Keyboards
from datetime import datetime
import pytz
from utils import setup_logger

logger = setup_logger(__name__)

my_bookings_router = Router()

@my_bookings_router.message(F.text == "Мои записи")
async def list_bookings(message: Message):
    logger.info(f"User {message.from_user.id} requested bookings")
    try:
        with Session() as session:
            user = session.query(User).filter_by(telegram_id=str(message.from_user.id)).first()
            if not user:
                await message.answer("Вы не зарегистрированы. Начните с записи на ТО.",
                                     reply_markup=Keyboards.main_menu_kb())
                return
            tz = pytz.timezone('Asia/Dubai')
            now = datetime.now(tz)
            bookings = session.query(Booking).filter(
                Booking.user_id == user.id,
                Booking.status.in_([BookingStatus.PENDING, BookingStatus.CONFIRMED]),
                (Booking.date > now.date()) | (
                    (Booking.date == now.date()) & (Booking.time >= now.time())
                )
            ).order_by(Booking.created_at.desc()).all()
            if not bookings:
                await message.answer("У вас нет активных записей.", reply_markup=Keyboards.main_menu_kb())
                return
            response = "📋 Ваши активные записи:\n\n"
            keyboard = []
            for booking in bookings:
                auto = session.query(Auto).get(booking.auto_id)
                status = {
                    BookingStatus.PENDING: "Ожидает",
                    BookingStatus.CONFIRMED: "Подтверждено",
                    BookingStatus.REJECTED: "Отклонено"
                }[booking.status]
                description = f"\nОписание: {booking.description}" if booking.description else ""
                response += (
                    f"Заявка #{booking.id}: {booking.service_name} ({booking.price or 'не указана'} ₽), "
                    f"{auto.brand} {auto.license_plate}, "
                    f"{booking.date.strftime('%d.%m.%Y')} {booking.time.strftime('%H:%M')}, "
                    f"{status}{description}\n"
                )
                if booking.status in [BookingStatus.PENDING, BookingStatus.CONFIRMED]:
                    keyboard.append([InlineKeyboardButton(text=f"Отменить #{booking.id}", callback_data=f"cancel_booking_{booking.id}")])
            if len(response) > 1024:
                logger.warning(f"Подпись слишком длинная ({len(response)} символов), отправляем без фото")
                await message.answer(
                    response,
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard) if keyboard else Keyboards.main_menu_kb()
                )
                return
            try:
                photo_path = get_photo_path("bookings")
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
    except Exception as e:
        logger.error(f"Ошибка получения записей: {str(e)}")
        await message.answer("Ошибка при получении записей. Попробуйте снова.",
                             reply_markup=Keyboards.main_menu_kb())

@my_bookings_router.callback_query(F.data.startswith("cancel_booking_"))
async def cancel_booking(callback: CallbackQuery, bot):
    """Обрабатывает отмену существующей записи."""
    logger.info(f"User {callback.from_user.id} requested to cancel booking")
    try:
        booking_id = int(callback.data.replace("cancel_booking_", ""))
        with Session() as session:
            booking = session.query(Booking).get(booking_id)
            if not booking:
                await callback.message.answer("Запись не найдена.", reply_markup=Keyboards.main_menu_kb())
                await callback.answer()
                return
            user = session.query(User).filter_by(telegram_id=str(callback.from_user.id)).first()
            if booking.user_id != user.id:
                await callback.message.answer("Вы не можете отменить чужую запись.", reply_markup=Keyboards.main_menu_kb())
                await callback.answer()
                return
            if booking.status not in [BookingStatus.PENDING, BookingStatus.CONFIRMED]:
                await callback.message.answer("Эта запись уже отменена или завершена.", reply_markup=Keyboards.main_menu_kb())
                await callback.answer()
                return
            booking.status = BookingStatus.REJECTED
            booking.rejection_reason = "Отменено пользователем"
            session.commit()
            logger.info(f"Booking {booking_id} cancelled by user {callback.from_user.id}")

            # Уведомление пользователю
            auto = session.query(Auto).get(booking.auto_id)
            await callback.message.answer(
                f"Заявка #{booking.id} ({booking.service_name}, {auto.brand} {auto.license_plate}) успешно отменена.",
                reply_markup=Keyboards.main_menu_kb()
            )

            # Уведомление мастеру
            message_text = (
                f"❌ Заявка #{booking.id} отменена пользователем\n"
                f"Клиент: {user.first_name} {user.last_name}\n"
                f"Авто: {auto.brand} {auto.license_plate}\n"
                f"Услуга: {booking.service_name}\n"
                f"Дата: {booking.date.strftime('%d.%m.%Y')}\n"
                f"Время: {booking.time.strftime('%H:%M')}"
            )
            await bot.send_message(ADMIN_ID, message_text)

            await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка отмены записи {booking_id}: {str(e)}")
        await callback.message.answer("Ошибка при отмене записи. Попробуйте снова.", reply_markup=Keyboards.main_menu_kb())
        await callback.answer()

@my_bookings_router.message(F.text == "История записей")
async def list_history(message: Message):
    """Отображает завершённые или отклонённые записи."""
    logger.info(f"User {message.from_user.id} requested booking history")
    try:
        with Session() as session:
            user = session.query(User).filter_by(telegram_id=str(message.from_user.id)).first()
            if not user:
                await message.answer("Вы не зарегистрированы. Начните с записи на ТО.",
                                     reply_markup=Keyboards.main_menu_kb())
                return
            bookings = session.query(Booking).filter(
                Booking.user_id == user.id,
                Booking.status == BookingStatus.REJECTED
            ).order_by(Booking.created_at.desc()).all()
            if not bookings:
                await message.answer("У вас нет завершённых или отклонённых записей.",
                                     reply_markup=Keyboards.main_menu_kb())
                return
            response = "📜 История ваших записей:\n\n"
            for booking in bookings:
                auto = session.query(Auto).get(booking.auto_id)
                status = "❌ Отклонено"
                description = f"\nОписание: {booking.description}" if booking.description else ""
                reason = f"\nПричина отклонения: {booking.rejection_reason}" if booking.rejection_reason else ""
                response += (
                    f"Заявка #{booking.id}: {booking.service_name} ({booking.price or 'не указана'} ₽), "
                    f"{auto.brand} {auto.license_plate}, "
                    f"{booking.date.strftime('%d.%m.%Y')} {booking.time.strftime('%H:%M')}, "
                    f"{status}{description}{reason}\n"
                )
            if len(response) > 1024:
                await message.answer(response, reply_markup=Keyboards.main_menu_kb())
                return
            try:
                photo_path = get_photo_path("bookings_list")
                await message.answer_photo(
                    photo=FSInputFile(photo_path),
                    caption=response,
                    reply_markup=Keyboards.main_menu_kb()
                )
            except (FileNotFoundError, ValueError) as e:
                logger.error(f"Ошибка загрузки фото для истории записей: {str(e)}")
                await message.answer(response, reply_markup=Keyboards.main_menu_kb())
    except Exception as e:
        logger.error(f"Ошибка получения истории записей: {str(e)}")
        await message.answer("Ошибка при получении истории. Попробуйте снова.",
                             reply_markup=Keyboards.main_menu_kb())
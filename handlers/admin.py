from datetime import datetime
import pytz
from aiogram import Router, F, Bot
from aiogram.filters import Command
from aiogram.types import Message, InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from config import ADMIN_ID
from database import Session, User, Auto, Booking, BookingStatus
from keyboards.main_kb import Keyboards
from utils import setup_logger
from handlers.service_utils import send_booking_notification

logger = setup_logger(__name__)
admin_router = Router()

class AdminStates(StatesGroup):
    AwaitingRejectionReason = State()
    AwaitingNewTimeDate = State()
    AwaitingNewTimeSlot = State()

@admin_router.message(Command("admin"))
@admin_router.callback_query(F.data.startswith("admin_page_"))
async def cmd_admin(message_or_callback: Message | CallbackQuery, bot: Bot = None):
    """Отображает активные заявки с пагинацией."""
    is_callback = isinstance(message_or_callback, CallbackQuery)
    message = message_or_callback.message if is_callback else message_or_callback
    logger.debug(f"Admin access attempt by user {message_or_callback.from_user.id}, expected ADMIN_ID: {ADMIN_ID}")
    if str(message_or_callback.from_user.id) != ADMIN_ID:
        await message.answer("Доступ только для мастера.")
        if is_callback:
            await message_or_callback.answer()
        return
    page = 0
    if is_callback and message_or_callback.data.startswith("admin_page_"):
        page = int(message_or_callback.data.replace("admin_page_", ""))
        if page < 0:
            page = 0
    try:
        with Session() as session:
            tz = pytz.timezone('Asia/Dubai')
            now = datetime.now(tz)
            bookings_query = session.query(Booking).filter(
                Booking.status.in_([BookingStatus.PENDING, BookingStatus.CONFIRMED]),
                (Booking.date > now.date()) | (
                    (Booking.date == now.date()) & (Booking.time >= now.time())
                )
            ).order_by(Booking.date, Booking.time)
            total_bookings = bookings_query.count()
            bookings = bookings_query.limit(5).offset(page * 5).all()
            logger.debug(f"Rendering admin page {page} with {len(bookings)} bookings")
            if not bookings:
                await message.answer("Нет активных записей.", reply_markup=Keyboards.main_menu_kb())
                if is_callback:
                    await message_or_callback.answer()
                return
            if page == 0 and not is_callback:
                await message.answer(f"📋 Активные записи (страница {page + 1}):", reply_markup=Keyboards.main_menu_kb())
            for booking in bookings:
                user = session.query(User).get(booking.user_id)
                auto = session.query(Auto).get(booking.auto_id)
                status = {
                    BookingStatus.PENDING: "⏳ Ожидает",
                    BookingStatus.CONFIRMED: "✅ Подтверждено"
                }[booking.status]
                description = f"\nОписание: {booking.description}" if booking.description else ""
                response = (
                    f"Заявка #{booking.id}: {booking.service_name} ({booking.price or 'не указана'} ₽)\n"
                    f"Клиент: {user.first_name} {user.last_name}\n"
                    f"Авто: {auto.brand} {auto.license_plate}\n"
                    f"Дата: {booking.date.strftime('%d.%m.%Y')}\n"
                    f"Время: {booking.time.strftime('%H:%M')}\n"
                    f"Статус: {status}{description}"
                )
                keyboard_rows = []
                if booking.status == BookingStatus.PENDING:
                    keyboard_rows.append([
                        InlineKeyboardButton(text="Подтвердить", callback_data=f"confirm_booking_{booking.id}"),
                        InlineKeyboardButton(text="Отклонить", callback_data=f"reject_booking_{booking.id}"),
                        InlineKeyboardButton(text="Изменить время", callback_data=f"reschedule_booking_{booking.id}")
                    ])
                keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_rows)
                if len(response) > 1024:
                    logger.warning(f"Подпись слишком длинная ({len(response)} символов)")
                    await message.answer(response, reply_markup=keyboard)
                    continue
                logger.debug(f"Rendering booking {booking.id} on page {page}")
                await message.answer(response, reply_markup=keyboard)
            # Клавиатура пагинации
            navigation_keyboard = Keyboards.admin_pagination_kb(page, total_bookings)
            if navigation_keyboard:
                await message.answer(f"Страница {page + 1} из {((total_bookings - 1) // 5) + 1}", reply_markup=navigation_keyboard)
            if is_callback:
                await message_or_callback.answer()
    except Exception as e:
        logger.error(f"Ошибка админ-панели: {str(e)}")
        await message.answer("Ошибка. Попробуйте снова.", reply_markup=Keyboards.main_menu_kb())
        if is_callback:
            await message_or_callback.answer()

@admin_router.callback_query(F.data.startswith("confirm_booking_"))
async def confirm_booking(callback: CallbackQuery, bot: Bot):
    """Подтверждает заявку и уведомляет пользователя."""
    if str(callback.from_user.id) != ADMIN_ID:
        await callback.message.answer("Доступ только для мастера.")
        await callback.answer()
        return
    try:
        booking_id = int(callback.data.replace("confirm_booking_", ""))
        with Session() as session:
            booking = session.query(Booking).get(booking_id)
            if not booking:
                await callback.message.answer("Заявка не найдена.", reply_markup=Keyboards.main_menu_kb())
                await callback.answer()
                return
            if booking.status != BookingStatus.PENDING:
                await callback.message.answer("Заявка уже обработана.", reply_markup=Keyboards.main_menu_kb())
                await callback.answer()
                return
            booking.status = BookingStatus.CONFIRMED
            session.commit()
            logger.info(f"Booking {booking_id} confirmed by admin {callback.from_user.id}")

            # Уведомление пользователю
            user = session.query(User).get(booking.user_id)
            auto = session.query(Auto).get(booking.auto_id)
            message_text = (
                f"✅ Ваша заявка #{booking.id} подтверждена!\n"
                f"Услуга: {booking.service_name}\n"
                f"Авто: {auto.brand} {auto.license_plate}\n"
                f"Дата: {booking.date.strftime('%d.%m.%Y')}\n"
                f"Время: {booking.time.strftime('%H:%M')}"
            )
            logger.debug(f"Sending confirmation to user {user.telegram_id} for booking {booking_id}")
            await bot.send_message(user.telegram_id, message_text)
            await callback.message.answer(f"Заявка #{booking_id} подтверждена.", reply_markup=Keyboards.main_menu_kb())
            await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка подтверждения заявки {booking_id}: {str(e)}")
        await callback.message.answer("Ошибка при подтверждении. Попробуйте снова.", reply_markup=Keyboards.main_menu_kb())
        await callback.answer()

@admin_router.callback_query(F.data.startswith("reject_booking_"))
async def reject_booking(callback: CallbackQuery, state: FSMContext):
    """Запрашивает причину отклонения заявки."""
    if str(callback.from_user.id) != ADMIN_ID:
        await callback.message.answer("Доступ только для мастера.")
        await callback.answer()
        return
    try:
        booking_id = int(callback.data.replace("reject_booking_", ""))
        with Session() as session:
            booking = session.query(Booking).get(booking_id)
            if not booking:
                await callback.message.answer("Заявка не найдена.", reply_markup=Keyboards.main_menu_kb())
                await callback.answer()
                return
            if booking.status != BookingStatus.PENDING:
                await callback.message.answer("Заявка уже обработана.", reply_markup=Keyboards.main_menu_kb())
                await callback.answer()
                return
            await state.update_data(booking_id=booking_id)
            await callback.message.answer("Введите причину отклонения заявки:")
            await state.set_state(AdminStates.AwaitingRejectionReason)
            logger.debug(f"Starting rejection for booking {booking_id}")
            await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка начала отклонения заявки: {str(e)}")
        await callback.message.answer("Ошибка. Попробуйте снова.", reply_markup=Keyboards.main_menu_kb())
        await callback.answer()

@admin_router.message(AdminStates.AwaitingRejectionReason, F.text)
async def process_rejection_reason(message: Message, state: FSMContext, bot: Bot):
    """Обрабатывает причину отклонения и уведомляет пользователя."""
    reason = message.text.strip()
    if len(reason) > 500:
        await message.answer("Причина слишком длинная. Максимум 500 символов. Попробуйте снова.")
        return
    try:
        data = await state.get_data()
        booking_id = data.get("booking_id")
        with Session() as session:
            booking = session.query(Booking).get(booking_id)
            if not booking:
                await message.answer("Заявка не найдена.", reply_markup=Keyboards.main_menu_kb())
                await state.clear()
                return
            booking.status = BookingStatus.REJECTED
            booking.rejection_reason = reason
            session.commit()
            logger.info(f"Booking {booking_id} rejected by admin {message.from_user.id} with reason: {reason}")

            # Уведомление пользователю
            user = session.query(User).get(booking.user_id)
            auto = session.query(Auto).get(booking.auto_id)
            success = await send_booking_notification(
                bot, user.telegram_id, booking, user, auto,
                f"Ваша запись отклонена. ❌\n<b>Причина:</b> {reason} 📝"
            )
            if not success:
                logger.warning(f"Не удалось уведомить пользователя user_id={user.telegram_id} об отклонении записи booking_id={booking_id}")
            await message.answer(f"Заявка #{booking_id} отклонена.", reply_markup=Keyboards.main_menu_kb())
            await state.clear()
    except Exception as e:
        logger.error(f"Ошибка отклонения заявки {booking_id}: {str(e)}")
        await message.answer("Ошибка при отклонении. Попробуйте снова.", reply_markup=Keyboards.main_menu_kb())
        await state.clear()

@admin_router.callback_query(F.data.startswith("reschedule_booking_"))
async def reschedule_booking(callback: CallbackQuery, state: FSMContext):
    """Запрашивает новую дату для заявки."""
    if str(callback.from_user.id) != ADMIN_ID:
        await callback.message.answer("Доступ только для мастера.")
        await callback.answer()
        return
    try:
        booking_id = int(callback.data.replace("reschedule_booking_", ""))
        with Session() as session:
            booking = session.query(Booking).get(booking_id)
            if not booking:
                await callback.message.answer("Заявка не найдена.", reply_markup=Keyboards.main_menu_kb())
                await callback.answer()
                return
            if booking.status != BookingStatus.PENDING:
                await callback.message.answer("Заявка уже обработана.", reply_markup=Keyboards.main_menu_kb())
                await callback.answer()
                return
            await state.update_data(booking_id=booking_id)
            await callback.message.answer("Выберите новую дату для заявки:", reply_markup=Keyboards.calendar_kb())
            await state.set_state(AdminStates.AwaitingNewTimeDate)
            logger.debug(f"Starting reschedule for booking {booking_id}")
            await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка начала изменения времени заявки {booking_id}: {str(e)}")
        await callback.message.answer("Ошибка. Попробуйте снова.", reply_markup=Keyboards.main_menu_kb())
        await callback.answer()

@admin_router.callback_query(AdminStates.AwaitingNewTimeDate, F.data.startswith("date_"))
async def process_new_date_selection(callback: CallbackQuery, state: FSMContext):
    """Обрабатывает выбор новой даты."""
    date_str = callback.data.replace("date_", "")
    try:
        selected_date = datetime.strptime(date_str, "%Y-%m-%d")
        await state.update_data(selected_date=selected_date)
        with Session() as session:
            await callback.message.answer(
                "Выберите новое время для заявки:",
                reply_markup=Keyboards.time_slots_kb(selected_date, 60, session)
            )
            await state.set_state(AdminStates.AwaitingNewTimeSlot)
            await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка выбора новой даты: {str(e)}")
        await callback.message.answer("Ошибка. Попробуйте снова.", reply_markup=Keyboards.main_menu_kb())
        await state.clear()
        await callback.answer()

@admin_router.callback_query(AdminStates.AwaitingNewTimeSlot, F.data.startswith("time_"))
async def process_new_time_selection(callback: CallbackQuery, state: FSMContext, bot: Bot):
    """Обрабатывает выбор нового времени и уведомляет пользователя."""
    time_str = callback.data.replace("time_", "")
    try:
        selected_time = datetime.strptime(time_str, "%H:%M").time()
        data = await state.get_data()
        booking_id = data.get("booking_id")
        selected_date = data.get("selected_date")
        with Session() as session:
            booking = session.query(Booking).get(booking_id)
            if not booking:
                await callback.message.answer("Заявка не найдена.", reply_markup=Keyboards.main_menu_kb())
                await state.clear()
                await callback.answer()
                return
            # Проверка, что время не в прошлом
            now = datetime.now(pytz.timezone('Asia/Dubai'))
            if selected_date.date() < now.date() or (selected_date.date() == now.date() and selected_time < now.time()):
                await callback.message.answer("Нельзя выбрать прошедшее время.", reply_markup=Keyboards.main_menu_kb())
                await state.clear()
                await callback.answer()
                return
            booking.date = selected_date.date()
            booking.time = selected_time
            booking.status = BookingStatus.PENDING
            session.commit()
            logger.info(f"Booking {booking_id} rescheduled by admin {callback.from_user.id} to {selected_date.date()} {selected_time}")

            # Уведомление пользователю
            user = session.query(User).get(booking.user_id)
            auto = session.query(Auto).get(booking.auto_id)
            success = await send_booking_notification(
                bot, user.telegram_id, booking, user, auto,
                f"📅 Время вашей заявки #{booking.id} изменено.\n"
                f"Новая дата: {booking.date.strftime('%d.%m.%Y')}\n"
                f"Новое время: {booking.time.strftime('%H:%M')}\n"
                f"Пожалуйста, подтвердите или отклоните новое время.",
                reply_markup=Keyboards.confirm_reschedule_kb(booking_id)
            )
            if not success:
                logger.warning(f"Не удалось уведомить пользователя user_id={user.telegram_id} об изменении времени записи booking_id={booking_id}")
            await callback.message.answer(
                f"Время заявки #{booking_id} изменено на {booking.date.strftime('%d.%m.%Y')} {booking.time.strftime('%H:%M')}.",
                reply_markup=Keyboards.main_menu_kb()
            )
            await state.clear()
            await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка изменения времени заявки {booking_id}: {str(e)}")
        await callback.message.answer("Ошибка при изменении времени. Попробуйте снова.", reply_markup=Keyboards.main_menu_kb())
        await state.clear()
        await callback.answer()
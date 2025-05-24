from typing import Tuple, Optional, List
from aiogram import Bot
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, FSInputFile
from aiogram.fsm.context import FSMContext
from sqlalchemy.orm import Session
from database import User, Auto, Booking, BookingStatus
from config import ADMIN_ID, MESSAGES, REMINDER_TIME_MINUTES
from keyboards.main_kb import Keyboards
from utils import setup_logger
from datetime import datetime, time, timedelta
import asyncio
import hashlib
import json
import os

logger = setup_logger(__name__)

async def send_message(bot: Bot, chat_id: str, message_type: str, message: str = None, **kwargs) -> Optional[Message]:
    """Отправляет сообщение пользователю."""
    try:
        if message_type == "text":
            return await bot.send_message(chat_id=chat_id, text=message, parse_mode="HTML", **kwargs)
        elif message_type == "photo":
            photo = kwargs.pop("photo", None)
            if not photo:
                logger.error("Параметр 'photo' не предоставлен для отправки фото")
                return None
            # Если photo — строка и это путь к файлу, преобразуем в FSInputFile
            if isinstance(photo, str) and os.path.isfile(photo):
                photo = FSInputFile(path=photo)
            return await bot.send_photo(chat_id=chat_id, photo=photo, caption=message, parse_mode="HTML", **kwargs)
        logger.warning(f"Неизвестный тип сообщения: {message_type}")
        return None
    except Exception as e:
        logger.error(f"Ошибка отправки сообщения в чат {chat_id}: {str(e)}")
        return None

async def handle_error(
    source: Message | CallbackQuery,
    state: FSMContext,
    bot: Bot,
    user_message: str,
    log_message: str,
    exception: Exception
) -> None:
    """Обрабатывает ошибки и отправляет сообщение пользователю."""
    logger.error(f"{log_message}: {str(exception)}")
    chat_id = str(source.chat.id) if isinstance(source, Message) else str(source.message.chat.id)
    sent_message = await send_message(bot, chat_id, "text", user_message, reply_markup=Keyboards.main_menu_kb())
    if sent_message:
        await state.update_data(last_message_id=sent_message.message_id)
    await state.clear()

async def get_progress_bar(
    current_state: str,
    progress_steps: dict,
    style: str = "emoji"
) -> str:
    """Создаёт прогресс-бар."""
    try:
        current_step = progress_steps.get(str(current_state), 1)
        total_steps = max(progress_steps.values())
        if style == "emoji":
            filled = "🟢" * current_step
            empty = "⚪" * (total_steps - current_step)
            return f"{filled}{empty} {{message}}"
        return "{message}"
    except Exception as e:
        logger.error(f"Ошибка создания прогресс-бара: {str(e)}")
        return "{message}"

async def check_user_and_autos(
    session: Session,
    user_id: str,
    bot: Bot,
    source: Message | CallbackQuery,
    state: FSMContext,
    context: str = "booking"
) -> Tuple[Optional[User], List[Auto]]:
    """Проверяет, зарегистрирован ли пользователь и есть ли у него автомобили."""
    try:
        user = session.query(User).filter_by(telegram_id=user_id).first()
        if not user:
            logger.info(f"Пользователь {user_id} не зарегистрирован в контексте {context}")
            chat_id = str(source.chat.id) if isinstance(source, Message) else str(source.message.chat.id)
            sent_message = await send_message(
                bot, chat_id, "text",
                "Вы не зарегистрированы. Перейдите в <b>Личный кабинет</b> для регистрации. 👤",
                reply_markup=Keyboards.main_menu_kb()
            )
            if sent_message:
                await state.update_data(last_message_id=sent_message.message_id)
            await state.clear()
            return None, []
        autos = session.query(Auto).filter_by(user_id=user.id).all()
        return user, autos
    except Exception as e:
        logger.error(f"Ошибка проверки пользователя {user_id} в контексте {context}: {str(e)}")
        await handle_error(source, state, bot, "Ошибка. Попробуйте снова. 😔", f"Ошибка проверки пользователя {context}", e)
        return None, []

async def check_user_registered(
    session: Session,
    user_id: str,
    bot: Bot,
    source: Message | CallbackQuery,
    state: FSMContext,
    context: str = "action"
) -> Optional[User]:
    """Проверяет, зарегистрирован ли пользователь."""
    try:
        user = session.query(User).filter_by(telegram_id=user_id).first()
        if not user:
            logger.info(f"Пользователь {user_id} не зарегистрирован в контексте {context}")
            chat_id = str(source.chat.id) if isinstance(source, Message) else str(source.message.chat.id)
            sent_message = await send_message(
                bot, chat_id, "text",
                "Вы не зарегистрированы. Перейдите в <b>Личный кабинет</b> для регистрации. 👤",
                reply_markup=Keyboards.main_menu_kb()
            )
            if sent_message:
                await state.update_data(last_message_id=sent_message.message_id)
            await state.clear()
            return None
        return user
    except Exception as e:
        logger.error(f"Ошибка проверки пользователя {user_id} в контексте {context}: {str(e)}")
        await handle_error(source, state, bot, "Ошибка. Попробуйте снова. 😔", f"Ошибка проверки пользователя {context}", e)
        return None

def master_only(func):
    """Декоратор: доступ только для мастера."""
    async def wrapper(callback: CallbackQuery, state: FSMContext, bot: Bot):
        if str(callback.from_user.id) != ADMIN_ID:
            logger.warning(f"Несанкционированный доступ: user_id={callback.from_user.id}")
            await callback.answer("Доступ только для мастера. 🔒")
            return
        return await func(callback, state, bot)
    return wrapper

async def get_booking_context(
    session: Session,
    booking_id: int,
    bot: Bot,
    source: Message | CallbackQuery,
    state: FSMContext
) -> Tuple[Optional[Booking], Optional[User], Optional[Auto]]:
    """Получает контекст бронирования."""
    try:
        booking = session.query(Booking).get(booking_id)
        if not booking:
            logger.warning(f"Запись booking_id={booking_id} не найдена")
            await handle_error(
                source, state, bot,
                "Запись не найдена. 📝", f"Запись не найдена для booking_id={booking_id}", Exception("Запись не найдена")
            )
            return None, None, None
        user = session.query(User).get(booking.user_id)
        auto = session.query(Auto).get(booking.auto_id)
        return booking, user, auto
    except Exception as e:
        logger.error(f"Ошибка получения контекста записи booking_id={booking_id}: {str(e)}")
        await handle_error(source, state, bot, "Ошибка. Попробуйте снова. 😔", f"Ошибка контекста записи booking_id={booking_id}", e)
        return None, None, None

async def send_booking_notification(
    bot: Bot,
    chat_id: str,
    booking: Booking,
    user: User,
    auto: Auto,
    message: str,
    reply_markup: InlineKeyboardMarkup = None
) -> bool:
    """Отправляет уведомление о бронировании."""
    try:
        if booking.status == BookingStatus.REJECTED:
            text = (
                f"❌ Ваша заявка #{booking.id} отклонена.\n"
                f"<b>Услуга:</b> {booking.service_name}\n"
                f"<b>Авто:</b> {auto.brand} {auto.license_plate}\n"
                f"<b>Дата:</b> {booking.date.strftime('%d.%m.%Y')}\n"
                f"<b>Время:</b> {booking.time.strftime('%H:%M')}\n"
                f"<b>Причина:</b> {booking.rejection_reason}"
            )
        else:
            text = (
                f"{message}\n"
                f"<b>Пользователь:</b> {user.first_name} {user.last_name or ''} 📋\n"
                f"<b>Телефон:</b> {user.phone or 'Не указано'} 📞\n"
                f"<b>Авто:</b> {auto.brand}, {auto.year}, {auto.license_plate} 🚗\n"
                f"<b>Услуга:</b> {booking.service_name} 🔧\n"
                f"<b>Дата:</b> {booking.date.strftime('%d.%m.%Y')} 📅\n"
                f"<b>Время:</b> {booking.time.strftime('%H:%M')} ⏰"
            )
        logger.debug(f"Отправка уведомления для booking_id={booking.id}, status={booking.status}, text: {text}")
        sent_message = await send_message(
            bot, chat_id, "text",
            text,
            reply_markup=reply_markup
        )
        return bool(sent_message)
    except Exception as e:
        logger.error(f"Ошибка отправки уведомления в чат {chat_id} для booking_id={booking.id}: {str(e)}")
        return False

async def set_user_state(
    bot_id: int,
    user_id: str,
    storage,
    state: str,
    data: dict
) -> bool:
    """Устанавливает состояние FSM для пользователя."""
    try:
        from aiogram.fsm.storage.memory import MemoryStorage
        if isinstance(storage, MemoryStorage):
            storage_key = f"{bot_id}:{user_id}"
            storage.storage[storage_key] = {"state": state, "data": data}
            return True
        logger.warning(f"Неподдерживаемый тип хранилища: {type(storage)}")
        return False
    except Exception as e:
        logger.error(f"Ошибка установки состояния для user_id={user_id}: {str(e)}")
        return False

async def notify_master(bot: Bot, booking: Booking, user: User, auto: Auto) -> bool:
    """Уведомляет мастера о новой записи."""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Подтвердить ✅", callback_data=f"confirm_booking_{booking.id}")],
        [InlineKeyboardButton(text="Перенести ⏰", callback_data=f"reschedule_booking_{booking.id}")],
        [InlineKeyboardButton(text="Отклонить ❌", callback_data=f"reject_booking_{booking.id}")]
    ])
    return await send_booking_notification(
        bot, ADMIN_ID, booking, user, auto,
        f"Новая запись #{booking.id} ожидает подтверждения: 📝",
        reply_markup=keyboard
    )

async def schedule_reminder(bot: Bot, booking: Booking, user: User, auto: Auto):
    """Планирует напоминание мастеру."""
    try:
        from .reminder_manager import reminder_manager
        if booking.status != BookingStatus.PENDING:
            return
        reminder_time = datetime.combine(booking.date, booking.time) - timedelta(minutes=REMINDER_TIME_MINUTES)
        if reminder_time <= datetime.now():
            return
        await reminder_manager.schedule(
            bot, booking.id, reminder_time,
            ADMIN_ID,
            f"Напоминание: запись #{booking.id} через {REMINDER_TIME_MINUTES} минут! ⏰\n"
            f"<b>Пользователь:</b> {user.first_name} {user.last_name or ''}\n"
            f"<b>Авто:</b> {auto.brand}, {auto.year}, {auto.license_plate}\n"
            f"<b>Услуга:</b> {booking.service_name}\n"
            f"<b>Время:</b> {booking.date.strftime('%d.%m.%Y')} {booking.time.strftime('%H:%M')}"
        )
    except Exception as e:
        logger.error(f"Ошибка планирования напоминания для booking_id={booking.id}: {str(e)}")

async def schedule_user_reminder(bot: Bot, booking: Booking, user: User, auto: Auto):
    """Планирует напоминание пользователю."""
    try:
        from .reminder_manager import reminder_manager
        if booking.status != BookingStatus.CONFIRMED:
            return
        reminder_time = datetime.combine(booking.date, booking.time) - timedelta(minutes=REMINDER_TIME_MINUTES)
        if reminder_time <= datetime.now():
            return
        await reminder_manager.schedule(
            bot, booking.id, reminder_time,
            user.telegram_id,
            f"Напоминание: ваша запись #{booking.id} через {REMINDER_TIME_MINUTES} минут! ⏰\n"
            f"<b>Авто:</b> {auto.brand}, {auto.year}, {auto.license_plate}\n"
            f"<b>Услуга:</b> {booking.service_name}\n"
            f"<b>Время:</b> {booking.date.strftime('%d.%m.%Y')} {booking.time.strftime('%H:%M')}"
        )
    except Exception as e:
        logger.error(f"Ошибка планирования напоминания пользователю для booking_id={booking.id}: {str(e)}")

async def process_user_input(
    message: Message,
    state: FSMContext,
    bot: Bot,
    validate_func,
    field_name: str,
    success_message: str,
    error_message: str,
    next_state,
    progress_steps: dict,
    reply_markup: Optional[InlineKeyboardMarkup] = None
) -> None:
    """Обрабатывает ввод пользователя с валидацией."""
    from pydantic import ValidationError
    try:
        value = message.text.strip()
        validated_value = validate_func(value)
        await state.update_data(**{field_name: validated_value})
        sent_message = await send_message(
            bot, str(message.chat.id), "text",
            (await get_progress_bar(next_state, progress_steps, style="emoji")).format(message=success_message),
            reply_markup=reply_markup
        )
        if sent_message:
            await state.update_data(last_message_id=sent_message.message_id)
            await state.set_state(next_state)
    except ValidationError as e:
        logger.error(f"Ошибка валидации {field_name} для user_id={message.from_user.id}: {str(e)}")
        sent_message = await send_message(
            bot, str(message.chat.id), "text",
            (await get_progress_bar(await state.get_state(), progress_steps, style="emoji")).format(message=error_message),
            reply_markup=reply_markup
        )
        if sent_message:
            await state.update_data(last_message_id=sent_message.message_id)
    except Exception as e:
        logger.error(f"Неожиданная ошибка при обработке {field_name} для user_id={message.from_user.id}: {str(e)}")
        await handle_error(
            message, state, bot,
            "Ошибка. Попробуйте снова. 😔",
            f"Неожиданная ошибка при обработке {field_name}",
            e
        )
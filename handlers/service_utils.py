from aiogram import Bot
from aiogram.types import Message, CallbackQuery, FSInputFile, InlineKeyboardMarkup, ReplyKeyboardMarkup, InputMediaPhoto
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State
from aiogram.fsm.storage.base import StorageKey
from aiogram.exceptions import TelegramForbiddenError
from config import ADMIN_ID, REMINDER_TIME_MINUTES, get_photo_path
from keyboards.main_kb import Keyboards
from utils import delete_previous_message, setup_logger
from database import User, Auto, Booking
from datetime import datetime, timedelta, timezone
from sqlalchemy.orm import Session as SQLSession
from typing import Union, Callable, Optional, Dict, Tuple
from functools import wraps
import asyncio
import os
from .states import RepairBookingStates, REPAIR_PROGRESS_STEPS

logger = setup_logger(__name__)

async def get_progress_bar(
    current_state: State,
    steps_map: Dict[str, int],
    style: str = "emoji"
) -> str:
    """Генерирует текстовый прогресс-бар для отображения этапа процесса."""
    state_str = str(current_state)
    current_step = steps_map.get(state_str, 1)
    total_steps = max(steps_map.values())  # Динамически вычисляем общее количество шагов
    logger.debug(f"Generating progress bar: state={state_str}, step={current_step}, total_steps={total_steps}")
    if style == "emoji":
        filled = "⬛" * current_step
        empty = "⬜" * (total_steps - current_step)
        return f"Шаг {current_step} из {total_steps}: {{message}} {filled}{empty}"
    elif style == "percent":
        percent = (current_step / total_steps) * 100
        return f"Прогресс: {percent:.0f}% {{message}}"
    else:
        return f"Шаг {current_step}/{total_steps}: {{message}}"

async def process_user_input(
    message: Message,
    state: FSMContext,
    bot: Bot,
    validate_fn: Callable,
    field_key: str,
    success_message: str,
    error_message: str,
    next_state: State,
    steps_map: Dict[str, int],
    reply_markup: Optional[Union[InlineKeyboardMarkup, ReplyKeyboardMarkup]] = None
) -> bool:
    """Обрабатывает пользовательский ввод с валидацией и обновлением состояния."""
    from pydantic import ValidationError
    if not message.text:
        logger.warning(f"No text provided for {field_key}")
        await delete_previous_message(bot, message.chat.id, (await state.get_data()).get("last_message_id"))
        current_state = await state.get_state() or next_state
        sent_message = await send_message(
            bot, str(message.chat.id), "text",
            (await get_progress_bar(current_state, steps_map, style="emoji")).format(message=error_message),
            reply_markup=reply_markup
        )
        if sent_message:
            await state.update_data(last_message_id=sent_message.message_id)
        return False
    try:
        value = message.text.strip()
        validate_fn(value)
        await state.update_data(**{field_key: value})
        await delete_previous_message(bot, message.chat.id, (await state.get_data()).get("last_message_id"))
        sent_message = await send_message(
            bot, str(message.chat.id), "text",
            (await get_progress_bar(next_state, steps_map, style="emoji")).format(message=success_message),
            reply_markup=reply_markup
        )
        if not sent_message:
            logger.error(f"Не удалось отправить сообщение для chat_id={message.chat.id}")
            return False
        await state.update_data(last_message_id=sent_message.message_id)
        await state.set_state(next_state)
        logger.debug(f"State set to {next_state}")
        return True
    except ValidationError as e:
        logger.warning(f"Ошибка валидации для {field_key}: {e}, ввод: {value}")
        await delete_previous_message(bot, message.chat.id, (await state.get_data()).get("last_message_id"))
        current_state = await state.get_state() or next_state
        sent_message = await send_message(
            bot, str(message.chat.id), "text",
            (await get_progress_bar(current_state, steps_map, style="emoji")).format(message=error_message),
            reply_markup=reply_markup
        )
        if sent_message:
            await state.update_data(last_message_id=sent_message.message_id)
        return False

async def send_message(
    bot: Bot,
    chat_id: str,
    message_type: str,
    content: str,
    photo_path: Optional[str] = None,
    reply_markup: Optional[Union[InlineKeyboardMarkup, ReplyKeyboardMarkup]] = None
) -> Optional[Message]:
    """Универсальная функция для отправки сообщений."""
    try:
        if message_type == "photo" and photo_path and os.path.exists(photo_path):
            sent_message = await bot.send_photo(
                chat_id=chat_id,
                photo=FSInputFile(photo_path),
                caption=content,
                reply_markup=reply_markup,
                parse_mode="HTML"
            )
        else:
            sent_message = await bot.send_message(
                chat_id=chat_id,
                text=content,
                reply_markup=reply_markup,
                parse_mode="HTML"
            )
        logger.info(f"Сообщение отправлено в чат chat_id={chat_id}")
        return sent_message
    except TelegramForbiddenError:
        logger.error(f"Не удалось отправить сообщение в чат chat_id={chat_id}: пользователь заблокировал бота")
        return None
    except Exception as e:
        logger.error(f"Ошибка отправки сообщения в чат chat_id={chat_id}: {str(e)}")
        return None

async def delete_previous_message(bot: Bot, chat_id: int, message_id: Optional[int]) -> None:
    """Удаляет предыдущее сообщение, если оно существует."""
    if message_id:
        try:
            await bot.delete_message(chat_id=chat_id, message_id=message_id)
            logger.debug(f"Сообщение message_id={message_id} удалено из чата chat_id={chat_id}")
        except Exception as e:
            logger.warning(f"Не удалось удалить сообщение message_id={message_id} в чате chat_id={chat_id}: {str(e)}")

async def handle_error(
    message_or_callback: Union[Message, CallbackQuery],
    state: FSMContext,
    bot: Bot,
    error_message: str,
    log_message: str,
    exception: Exception
) -> bool:
    """Обрабатывает ошибки, отправляя сообщение и очищая состояние."""
    logger.error(f"{log_message}: {str(exception)}")
    chat_id = message_or_callback.chat.id if isinstance(message_or_callback, Message) else message_or_callback.message.chat.id
    await delete_previous_message(bot, chat_id, (await state.get_data()).get("last_message_id"))
    sent_message = await send_message(
        bot, str(chat_id), "text", error_message, reply_markup=Keyboards.main_menu_kb()
    )
    if sent_message:
        await state.update_data(last_message_id=sent_message.message_id)
    await state.clear()
    return bool(sent_message)

def master_only(handler: Callable) -> Callable:
    """Декоратор для проверки, что пользователь — мастер."""
    @wraps(handler)
    async def wrapper(callback_or_message: Union[CallbackQuery, Message], *args, **kwargs):
        user_id = callback_or_message.from_user.id
        if str(user_id) != ADMIN_ID:
            logger.debug(f"Несанкционированный доступ пользователем user_id={user_id}")
            if isinstance(callback_or_message, CallbackQuery):
                await callback_or_message.answer("Доступ только для мастера. 🔒")
            return
        return await handler(callback_or_message, *args, **kwargs)
    return wrapper

async def get_booking_context(
    session: SQLSession,
    booking_id: int,
    bot: Bot,
    message_or_callback: Union[Message, CallbackQuery],
    state: FSMContext
) -> Tuple[Optional[Booking], Optional[User], Optional[Auto]]:
    """Получает данные о записи, пользователе и автомобиле по booking_id."""
    booking = session.query(Booking).get(booking_id)
    if not booking:
        await handle_error(
            message_or_callback, state, bot,
            "Запись не найдена. 📝", f"Запись не найдена для booking_id={booking_id}", Exception("Запись не найдена")
        )
        return None, None, None
    user = session.query(User).get(booking.user_id)
    if not user:
        await handle_error(
            message_or_callback, state, bot,
            "Пользователь не найден. 👤", f"Пользователь не найден для booking_id={booking_id}", Exception("Пользователь не найден")
        )
        return None, None, None
    auto = session.query(Auto).get(booking.auto_id)
    if not auto:
        await handle_error(
            message_or_callback, state, bot,
            "Автомобиль не найден. 🚗", f"Автомобиль не найден для booking_id={booking_id}", Exception("Автомобиль не найден")
        )
        return None, None, None
    return booking, user, auto

async def send_booking_notification(
    bot: Bot,
    chat_id: str,
    booking: Booking,
    user: User,
    auto: Auto,
    message_text: str,
    reply_markup: Optional[Union[InlineKeyboardMarkup, ReplyKeyboardMarkup]] = None,
    photos: Optional[list] = None
) -> bool:
    """Отправляет уведомление о записи, включая фотографии, если они есть."""
    message = (
        f"{message_text}\n"
        f"<b>Услуга:</b> {booking.service_name} 🔧\n"
        f"<b>Дата:</b> {booking.date.strftime('%d.%m.%Y')} 📅\n"
        f"<b>Время:</b> {booking.time.strftime('%H:%M')} ⏰\n"
        f"<b>Авто:</b> {auto.brand}, {auto.year}, {auto.license_plate} 🚗"
    )
    if booking.description:
        message += f"\n<b>Описание:</b> {booking.description} 📝"
    try:
        if photos:
            media = [InputMediaPhoto(media=photo_id) for photo_id in photos]
            await bot.send_media_group(chat_id=chat_id, media=media)
        sent_message = await send_message(bot, chat_id, "text", message, reply_markup=reply_markup)
        return bool(sent_message)
    except Exception as e:
        logger.error(f"Ошибка отправки уведомления в чат chat_id={chat_id}: {str(e)}")
        return False

async def set_user_state(
    bot_id: int,
    user_telegram_id: str,
    storage,
    state: State,
    data: dict
) -> bool:
    """Устанавливает состояние FSM для пользователя."""
    try:
        user_state = FSMContext(
            storage=storage,
            key=StorageKey(
                bot_id=bot_id,
                chat_id=int(user_telegram_id),
                user_id=int(user_telegram_id)
            )
        )
        await user_state.update_data(**data)
        await user_state.set_state(state)
        logger.debug(f"Установлено состояние {state} для пользователя user_id={user_telegram_id}")
        return True
    except Exception as e:
        logger.error(f"Ошибка установки состояния для user_id={user_telegram_id}: {str(e)}")
        return False

async def notify_master(bot: Bot, booking: Booking, user: User, auto: Auto, photos: Optional[list] = None) -> bool:
    """Отправляет уведомление мастеру о новой записи."""
    from aiogram.types import InlineKeyboardButton
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Подтвердить ✅", callback_data=f"confirm_booking_{booking.id}")],
        [InlineKeyboardButton(text="Предложить другое время ⏰", callback_data=f"reschedule_booking_{booking.id}")],
        [InlineKeyboardButton(text="Отклонить ❌", callback_data=f"reject_booking_{booking.id}")]
    ])
    try:
        success = await send_booking_notification(
            bot, ADMIN_ID, booking, user, auto,
            f"Новая заявка на ремонт:\n<b>Пользователь:</b> {user.first_name} {user.last_name} 👤\n<b>Телефон:</b> {user.phone} 📞",
            reply_markup=keyboard,
            photos=photos
        )
        if not success:
            logger.warning(f"Failed to notify master for booking_id={booking.id}: Notification sending failed")
        return success
    except Exception as e:
        logger.error(f"Failed to notify master for booking_id={booking.id}: {str(e)}")
        return False

async def check_user_and_autos(
    session: SQLSession,
    user_id: str,
    bot: Bot,
    message_or_callback: Union[Message, CallbackQuery],
    state: FSMContext,
    photo_key: str = None
) -> Tuple[Optional[User], list[Auto]]:
    """Проверяет существование пользователя и его автомобилей."""
    user = session.query(User).filter_by(telegram_id=user_id).first()
    chat_id = message_or_callback.chat.id if isinstance(message_or_callback, Message) else message_or_callback.message.chat.id
    if not user:
        await delete_previous_message(bot, chat_id, (await state.get_data()).get("last_message_id"))
        sent_message = await send_message(
            bot, str(chat_id), "text",
            "Вы не зарегистрированы. Начните с записи на ТО. 👤",
            reply_markup=Keyboards.main_menu_kb()
        )
        if sent_message:
            await state.update_data(last_message_id=sent_message.message_id)
        await state.clear()
        return None, []
    autos = session.query(Auto).filter_by(user_id=user.id).all()
    if not autos:
        response = "У вас нет зарегистрированных автомобилей. Введите <b>марку</b> автомобиля (например, <b>Toyota</b>): 🚗"
        await delete_previous_message(bot, chat_id, (await state.get_data()).get("last_message_id"))
        sent_message = await send_message(
            bot, str(chat_id), "photo" if photo_key else "text",
            (await get_progress_bar(RepairBookingStates.AwaitingAutoBrand, REPAIR_PROGRESS_STEPS, style="emoji")).format(message=response),
            photo_path=get_photo_path(photo_key) if photo_key else None,
            reply_markup=Keyboards.cancel_kb()
        )
        if sent_message:
            await state.update_data(last_message_id=sent_message.message_id)
        await state.set_state(RepairBookingStates.AwaitingAutoBrand)
        return user, []
    return user, autos

class ReminderManager:
    def __init__(self):
        self.tasks: Dict[int, asyncio.Task] = {}

    async def schedule_reminder(self, bot: Bot, booking: Booking, user: User, auto: Auto, is_user: bool = False, delay_minutes: int = REMINDER_TIME_MINUTES) -> None:
        """Запланировать напоминание."""
        try:
            booking_datetime = datetime.combine(booking.date, booking.time, tzinfo=timezone.utc)
            reminder_time = booking_datetime - timedelta(minutes=delay_minutes)
            now = datetime.now(timezone.utc)
            if reminder_time > now:
                delay = (reminder_time - now).total_seconds()
                await asyncio.sleep(delay)
                target_id = user.telegram_id if is_user else ADMIN_ID
                message = (
                    f"Напоминание: Через {delay_minutes} минут ваша запись:\n<b>Услуга:</b> {booking.service_name} 🔧"
                    if is_user else
                    f"Напоминание: Через {delay_minutes} минут запись:\n<b>Пользователь:</b> {user.first_name} {user.last_name} 👤"
                )
                success = await send_booking_notification(bot, target_id, booking, user, auto, message)
                if success:
                    logger.info(f"Напоминание отправлено для записи booking_id={booking.id} в чат {target_id}")
        except Exception as e:
            logger.error(f"Ошибка напоминания для записи booking_id={booking.id}: {str(e)}")
        finally:
            self.tasks.pop(booking.id, None)

    def schedule(self, bot: Bot, booking: Booking, user: User, auto: Auto, is_user: bool = False, delay_minutes: int = REMINDER_TIME_MINUTES) -> None:
        """Создаёт задачу для напоминания."""
        task = asyncio.create_task(self.schedule_reminder(bot, booking, user, auto, is_user, delay_minutes))
        self.tasks[booking.id] = task

    def cancel(self, booking_id: int) -> None:
        """Отменяет напоминание."""
        task = self.tasks.pop(booking_id, None)
        if task:
            task.cancel()
            logger.info(f"Напоминание для записи booking_id={booking_id} отменено")

reminder_manager = ReminderManager()

async def schedule_reminder(bot: Bot, booking: Booking, user: User, auto: Auto, delay_minutes: int = REMINDER_TIME_MINUTES) -> None:
    """Запланировать напоминание мастеру."""
    reminder_manager.schedule(bot, booking, user, auto, is_user=False, delay_minutes=delay_minutes)

async def schedule_user_reminder(bot: Bot, booking: Booking, user: User, auto: Auto, delay_minutes: int = REMINDER_TIME_MINUTES) -> None:
    """Запланировать напоминание пользователю."""
    reminder_manager.schedule(bot, booking, user, auto, is_user=True, delay_minutes=delay_minutes)
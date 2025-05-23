from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, FSInputFile, InlineKeyboardMarkup, InlineKeyboardButton, KeyboardButton, ReplyKeyboardMarkup
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.base import StorageKey
from aiogram.exceptions import TelegramForbiddenError, TelegramBadRequest
from config import get_photo_path, ADMIN_ID, MESSAGES, REMINDER_TIME_MINUTES, SERVICES
from keyboards.main_kb import Keyboards
from utils import setup_logger, UserInput, AutoInput, delete_previous_message
from pydantic import ValidationError
from database import User, Auto, Booking, BookingStatus, Session, init_db
from datetime import datetime, timedelta
from sqlalchemy.orm import Session as SQLSession
import asyncio
from typing import Union, Callable, Optional
from functools import wraps
import os

# Инициализируем базу данных
init_db()

service_booking_router = Router()
logger = setup_logger(__name__)

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

# Прогресс-бар
PROGRESS_STEPS = {
    BookingStates.AwaitingFirstName: 1,
    BookingStates.AwaitingLastName: 2,
    BookingStates.AwaitingPhone: 3,
    BookingStates.AwaitingAutoBrand: 4,
    BookingStates.AwaitingAutoYear: 5,
    BookingStates.AwaitingAutoVin: 6,
    BookingStates.AwaitingAutoLicensePlate: 7,
    BookingStates.AwaitingAddAnotherAuto: 8,
    BookingStates.AwaitingAutoSelection: 9,
    BookingStates.AwaitingService: 10,
    BookingStates.AwaitingDate: 11,
    BookingStates.AwaitingTime: 12
}

def get_progress_bar(current_state: State, total_steps: int = 12) -> str:
    """Генерирует текстовый прогресс-бар."""
    current_step = PROGRESS_STEPS.get(current_state, 1)
    filled = "⬛" * current_step
    empty = "⬜" * (total_steps - current_step)
    return f"Шаг {current_step} из {total_steps}: {{message}} {filled}{empty}"



# Вспомогательные функции
async def process_user_input(
    message: Message,
    state: FSMContext,
    bot: Bot,
    validate_fn: Callable,
    field_key: str,
    success_message: str,
    error_message: str,
    next_state: State
):
    """Обрабатывает пользовательский ввод с валидацией."""
    try:
        value = message.text.strip()
        validate_fn(value)
        await state.update_data(**{field_key: value})
        await delete_previous_message(bot, message.chat.id, (await state.get_data()).get("last_message_id"))
        sent_message = await message.answer(
            get_progress_bar(next_state).format(message=success_message),
            parse_mode="HTML"
        )
        await state.update_data(last_message_id=sent_message.message_id)
        await state.set_state(next_state)
    except ValidationError as e:
        logger.warning(f"Ошибка валидации для {field_key}: {e}, ввод: {value}")
        await delete_previous_message(bot, message.chat.id, (await state.get_data()).get("last_message_id"))
        current_state = await state.get_state()
        sent_message = await message.answer(
            get_progress_bar(current_state).format(message=error_message),
            parse_mode="HTML"
        )
        await state.update_data(last_message_id=sent_message.message_id)

async def send_message_with_photo_fallback(
    message_or_callback: Union[Message, CallbackQuery],
    state: FSMContext,
    bot: Bot,
    photo_key: str,
    caption: str,
    reply_markup
):
    """Отправляет сообщение с фото, с возвратом к тексту при ошибке."""
    logger.debug(f"Отправка сообщения с фото, тип: {type(message_or_callback).__name__}")
    try:
        photo_path = get_photo_path(photo_key)
        logger.debug(f"Попытка загрузки фото по пути: {photo_path}, существует: {os.path.exists(photo_path)}")
        if not os.path.exists(photo_path):
            raise FileNotFoundError(f"Файл фото не найден по пути {photo_path}")
        if isinstance(message_or_callback, Message):
            sent_message = await message_or_callback.answer_photo(
                photo=FSInputFile(photo_path),
                caption=caption,
                reply_markup=reply_markup,
                parse_mode="HTML"
            )
        else:  # CallbackQuery
            sent_message = await message_or_callback.message.answer_photo(
                photo=FSInputFile(photo_path),
                caption=caption,
                reply_markup=reply_markup,
                parse_mode="HTML"
            )
    except (FileNotFoundError, ValueError) as e:
        logger.error(f"Ошибка загрузки фото для {photo_key}: {str(e)}")
        if isinstance(message_or_callback, Message):
            sent_message = await message_or_callback.answer(caption, reply_markup=reply_markup, parse_mode="HTML")
        else:  # CallbackQuery
            sent_message = await message_or_callback.message.answer(caption, reply_markup=reply_markup, parse_mode="HTML")
    await state.update_data(last_message_id=sent_message.message_id)
    return sent_message

async def handle_error(
    message_or_callback: Union[Message, CallbackQuery],
    state: FSMContext,
    bot: Bot,
    error_message: str,
    log_message: str,
    exception: Exception
):
    """Обрабатывает ошибки, отправляя сообщение и очищая состояние."""
    logger.error(f"{log_message}: {str(exception)}")
    chat_id = message_or_callback.chat.id if isinstance(message_or_callback, Message) else message_or_callback.message.chat.id
    await delete_previous_message(bot, chat_id, (await state.get_data()).get("last_message_id"))
    sent_message = await (message_or_callback if isinstance(message_or_callback, Message) else message_or_callback.message).answer(
        error_message, reply_markup=Keyboards.main_menu_kb(), parse_mode="HTML"
    )
    await state.update_data(last_message_id=sent_message.message_id)
    await state.clear()

def master_only(handler):
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
) -> tuple[Optional[Booking], Optional[User], Optional[Auto]]:
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
    reply_markup=None
):
    """Отправляет уведомление о записи."""
    try:
        message = (
            f"{message_text}\n"
            f"<b>Услуга:</b> {booking.service_name} 🔧\n"
            f"<b>Дата:</b> {booking.date.strftime('%d.%m.%Y')} 📅\n"
            f"<b>Время:</b> {booking.time.strftime('%H:%M')} ⏰\n"
            f"<b>Авто:</b> {auto.brand}, {auto.year}, {auto.license_plate} 🚗"
        )
        if booking.description:
            message += f"\n<b>Описание:</b> {booking.description} 📝"
        await bot.send_message(chat_id, message, reply_markup=reply_markup, parse_mode="HTML")
        logger.info(f"Уведомление отправлено в чат chat_id={chat_id} для записи booking_id={booking.id}")
    except TelegramForbiddenError:
        logger.error(f"Не удалось отправить уведомление в чат chat_id={chat_id}: пользователь заблокировал бота")
        raise
    except Exception as e:
        logger.error(f"Ошибка отправки уведомления в чат chat_id={chat_id} для записи booking_id={booking.id}: {str(e)}")
        raise

async def set_user_state(
    bot_id: int,
    user_telegram_id: str,
    storage,
    state: State,
    data: dict
):
    """Устанавливает состояние FSM для пользователя."""
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

async def notify_master(bot: Bot, booking: Booking, user: User, auto: Auto):
    """Отправляет уведомление мастеру о новой записи."""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Подтвердить ✅", callback_data=f"confirm_booking_{booking.id}")],
        [InlineKeyboardButton(text="Предложить другое время ⏰", callback_data=f"reschedule_booking_{booking.id}")],
        [InlineKeyboardButton(text="Отклонить ❌", callback_data=f"reject_booking_{booking.id}")]
    ])
    await send_booking_notification(
        bot, ADMIN_ID, booking, user, auto,
        f"Новая заявка на ТО:\n<b>Пользователь:</b> {user.first_name} {user.last_name} 👤\n<b>Телефон:</b> {user.phone} 📞",
        reply_markup=keyboard
    )

async def schedule_reminder(bot: Bot, booking: Booking, user: User, auto: Auto):
    """Запланировать напоминание мастеру."""
    try:
        booking_datetime = datetime.combine(booking.date, booking.time)
        reminder_time = booking_datetime - timedelta(minutes=REMINDER_TIME_MINUTES)
        now = datetime.utcnow()
        if reminder_time > now:
            delay = (reminder_time - now).total_seconds()
            await asyncio.sleep(delay)
            await send_booking_notification(
                bot, ADMIN_ID, booking, user, auto,
                f"Напоминание: Через {REMINDER_TIME_MINUTES} минут запись:\n<b>Пользователь:</b> {user.first_name} {user.last_name} 👤"
            )
    except Exception as e:
        logger.error(f"Ошибка отправки напоминания мастеру для записи booking_id={booking.id}: {str(e)}")

async def schedule_user_reminder(bot: Bot, booking: Booking, user: User, auto: Auto):
    """Запланировать напоминание пользователю."""
    try:
        booking_datetime = datetime.combine(booking.date, booking.time)
        reminder_time = booking_datetime - timedelta(minutes=REMINDER_TIME_MINUTES)
        now = datetime.utcnow()
        if reminder_time > now:
            delay = (reminder_time - now).total_seconds()
            await asyncio.sleep(delay)
            await send_booking_notification(
                bot, user.telegram_id, booking, user, auto,
                f"Напоминание: Через {REMINDER_TIME_MINUTES} минут ваша запись:\n<b>Цена:</b> {booking.price} ₽ 💸"
            )
    except Exception as e:
        logger.error(f"Ошибка отправки напоминания пользователю для записи booking_id={booking.id}: {str(e)}")

@service_booking_router.message(F.text == "Запись на ТО")
async def start_booking(message: Message, state: FSMContext, bot: Bot):
    """Запускает процесс записи на ТО."""
    logger.info(f"Пользователь {message.from_user.id} начал запись")
    try:
        logger.debug(f"Класс Session: {Session}, движок: {Session.kw['bind']}")
        with Session() as session:
            user = session.query(User).filter_by(telegram_id=str(message.from_user.id)).first()
            if user:
                autos = session.query(Auto).filter_by(user_id=user.id).all()
                if autos:
                    await send_message_with_photo_fallback(
                        message, state, bot, "booking",
                        get_progress_bar(BookingStates.AwaitingAutoSelection).format(
                            message="Выберите автомобиль для записи на ТО: 🚗"
                        ),
                        Keyboards.auto_selection_kb(autos)
                    )
                    await state.set_state(BookingStates.AwaitingAutoSelection)
                else:
                    await delete_previous_message(bot, message.chat.id, (await state.get_data()).get("last_message_id"))
                    sent_message = await message.answer(
                        get_progress_bar(BookingStates.AwaitingAutoBrand).format(
                            message="У вас нет зарегистрированных автомобилей. Введите <b>марку</b> автомобиля (например, <b>Toyota</b>): 🚗"
                        ),
                        parse_mode="HTML"
                    )
                    await state.update_data(last_message_id=sent_message.message_id)
                    await state.set_state(BookingStates.AwaitingAutoBrand)
            else:
                await delete_previous_message(bot, message.chat.id, (await state.get_data()).get("last_message_id"))
                sent_message = await message.answer(
                    get_progress_bar(BookingStates.AwaitingFirstName).format(
                        message="Давайте познакомимся! 👤 Введите ваше <b>имя</b>:"
                    ),
                    parse_mode="HTML"
                )
                await state.update_data(last_message_id=sent_message.message_id)
                await state.set_state(BookingStates.AwaitingFirstName)
    except Exception as e:
        await handle_error(message, state, bot, "Ошибка. Попробуйте снова. 😔", "Ошибка проверки пользователя", e)

@service_booking_router.callback_query(BookingStates.AwaitingAutoSelection, F.data.startswith("auto_"))
async def process_auto_selection(callback: CallbackQuery, state: FSMContext, bot: Bot):
    """Обрабатывает выбор автомобиля."""
    auto_id = int(callback.data.replace("auto_", ""))
    try:
        with Session() as session:
            auto = session.query(Auto).get(auto_id)
            if not auto:
                await handle_error(
                    callback, state, bot,
                    "Автомобиль не найден. Попробуйте снова. 🚗", f"Автомобиль не найден для auto_id={auto_id}", Exception("Автомобиль не найден")
                )
                await callback.answer()
                return
            await state.update_data(auto_id=auto_id)
            await send_message_with_photo_fallback(
                callback, state, bot, "booking_menu",
                get_progress_bar(BookingStates.AwaitingService).format(
                    message=MESSAGES.get("booking", "Выберите <b>услугу</b> для записи на ТО: 🔧")
                ),
                Keyboards.services_kb()
            )
            await state.set_state(BookingStates.AwaitingService)
            await callback.answer()
    except Exception as e:
        await handle_error(callback, state, bot, "Ошибка. Попробуйте снова. 😔", "Ошибка выбора автомобиля", e)
        await callback.answer()

@service_booking_router.callback_query(BookingStates.AwaitingAutoSelection, F.data == "add_new_auto")
async def add_new_auto(callback: CallbackQuery, state: FSMContext, bot: Bot):
    """Обрабатывает выбор добавления нового автомобиля."""
    await delete_previous_message(bot, callback.message.chat.id, (await state.get_data()).get("last_message_id"))
    sent_message = await callback.message.answer(
        get_progress_bar(BookingStates.AwaitingAutoBrand).format(
            message="Введите <b>марку</b> автомобиля (например, <b>Toyota</b>): 🚗"
        ),
        parse_mode="HTML"
    )
    await state.update_data(last_message_id=sent_message.message_id)
    await state.set_state(BookingStates.AwaitingAutoBrand)
    await callback.answer()

@service_booking_router.message(BookingStates.AwaitingFirstName, F.text)
async def process_first_name(message: Message, state: FSMContext, bot: Bot):
    await process_user_input(
        message, state, bot,
        UserInput.validate_first_name, "first_name",
        "Введите вашу <b>фамилию</b>: 👤",
        "Имя слишком короткое или длинное (2–50 символов). Введите снова: 😔",
        BookingStates.AwaitingLastName
    )

@service_booking_router.message(BookingStates.AwaitingLastName, F.text)
async def process_last_name(message: Message, state: FSMContext, bot: Bot):
    await process_user_input(
        message, state, bot,
        UserInput.validate_last_name, "last_name",
        "Введите ваш номер телефона, начиная с <b>+7</b> (например, <b>+79991234567</b>, 10–15 цифр): 📞",
        "Фамилия слишком короткая или длинная (2–50 символов). Введите снова: 😔",
        BookingStates.AwaitingPhone
    )

@service_booking_router.message(BookingStates.AwaitingPhone, F.text)
async def process_phone(message: Message, state: FSMContext, bot: Bot):
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
                logger.info(f"Пользователь {message.from_user.id} зарегистрирован")
            await delete_previous_message(bot, message.chat.id, (await state.get_data()).get("last_message_id"))
            sent_message = await message.answer(
                get_progress_bar(BookingStates.AwaitingAutoBrand).format(
                    message="Введите <b>марку</b> автомобиля (например, <b>Toyota</b>): 🚗"
                ),
                parse_mode="HTML"
            )
            await state.update_data(last_message_id=sent_message.message_id)
            await state.set_state(BookingStates.AwaitingAutoBrand)
        except Exception as e:
            await handle_error(message, state, bot, "Ошибка регистрации. Попробуйте снова. 😔", "Ошибка регистрации пользователя", e)
    except ValidationError as e:
        logger.warning(f"Ошибка валидации номера телефона: {e}, ввод: {phone}")
        await delete_previous_message(bot, message.chat.id, (await state.get_data()).get("last_message_id"))
        sent_message = await message.answer(
            get_progress_bar(BookingStates.AwaitingPhone).format(
                message="Некорректный номер телефона (10–15 цифр, например, <b>+79991234567</b>). Введите снова: 📞"
            ),
            parse_mode="HTML"
        )
        await state.update_data(last_message_id=sent_message.message_id)

@service_booking_router.message(BookingStates.AwaitingAutoBrand, F.text)
async def process_auto_brand(message: Message, state: FSMContext, bot: Bot):
    await process_user_input(
        message, state, bot,
        AutoInput.validate_brand, "brand",
        "Введите <b>год выпуска</b> автомобиля (например, <b>2020</b>): 📅",
        "Марка слишком короткая или длинная (2–50 символов). Введите снова: 😔",
        BookingStates.AwaitingAutoYear
    )

@service_booking_router.message(BookingStates.AwaitingAutoYear, F.text)
async def process_auto_year(message: Message, state: FSMContext, bot: Bot):
    try:
        year = int(message.text.strip())
        AutoInput.validate_year(year)
        await state.update_data(year=year)
        await delete_previous_message(bot, message.chat.id, (await state.get_data()).get("last_message_id"))
        sent_message = await message.answer(
            get_progress_bar(BookingStates.AwaitingAutoVin).format(
                message="Введите <b>VIN-номер</b> автомобиля (ровно 17 букв/цифр, например, <b>JTDBT923771012345</b>): 🔢"
            ),
            parse_mode="HTML"
        )
        await state.update_data(last_message_id=sent_message.message_id)
        await state.set_state(BookingStates.AwaitingAutoVin)
    except (ValidationError, ValueError) as e:
        logger.warning(f"Ошибка валидации года выпуска: {e}, ввод: {message.text}")
        await delete_previous_message(bot, message.chat.id, (await state.get_data()).get("last_message_id"))
        sent_message = await message.answer(
            get_progress_bar(BookingStates.AwaitingAutoYear).format(
                message=f"Некорректный год (1900–{datetime.today().year}). Введите снова: 📅"
            ),
            parse_mode="HTML"
        )
        await state.update_data(last_message_id=sent_message.message_id)

@service_booking_router.message(BookingStates.AwaitingAutoVin, F.text)
async def process_auto_vin(message: Message, state: FSMContext, bot: Bot):
    await process_user_input(
        message, state, bot,
        AutoInput.validate_vin, "vin",
        "Введите <b>государственный номер</b> автомобиля (например, <b>А123БВ45</b>): 🚘",
        "Некорректный VIN (17 букв/цифр). Введите снова: 😔",
        BookingStates.AwaitingAutoLicensePlate
    )

@service_booking_router.message(BookingStates.AwaitingAutoLicensePlate, F.text)
async def process_auto_license_plate(message: Message, state: FSMContext, bot: Bot):
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
                logger.info(f"Автомобиль добавлен для пользователя {message.from_user.id}")
                await state.update_data(auto_id=auto.id)
            await delete_previous_message(bot, message.chat.id, (await state.get_data()).get("last_message_id"))
            sent_message = await message.answer(
                get_progress_bar(BookingStates.AwaitingAddAnotherAuto).format(
                    message="Автомобиль добавлен! 🎉 Хотите добавить ещё один автомобиль или продолжить?"
                ),
                reply_markup=Keyboards.add_another_auto_kb(),
                parse_mode="HTML"
            )
            await state.update_data(last_message_id=sent_message.message_id)
            await state.set_state(BookingStates.AwaitingAddAnotherAuto)
        except Exception as e:
            await handle_error(message, state, bot, "Ошибка добавления автомобиля. Попробуйте снова. 😔", "Ошибка добавления автомобиля", e)
    except ValidationError as e:
        logger.warning(f"Ошибка валидации госномера: {e}, ввод: {license_plate}")
        await delete_previous_message(bot, message.chat.id, (await state.get_data()).get("last_message_id"))
        sent_message = await message.answer(
            get_progress_bar(BookingStates.AwaitingAutoLicensePlate).format(
                message="Госномер слишком короткий или длинный (5–20 символов, например, <b>А123БВ45</b>). Введите снова: 🚘"
            ),
            parse_mode="HTML"
        )
        await state.update_data(last_message_id=sent_message.message_id)

@service_booking_router.callback_query(BookingStates.AwaitingAddAnotherAuto, F.data == "add_another_auto")
async def add_another_auto(callback: CallbackQuery, state: FSMContext, bot: Bot):
    """Обрабатывает выбор добавления ещё одного автомобиля."""
    await delete_previous_message(bot, callback.message.chat.id, (await state.get_data()).get("last_message_id"))
    sent_message = await callback.message.answer(
        get_progress_bar(BookingStates.AwaitingAutoBrand).format(
            message="Введите <b>марку</b> автомобиля (например, <b>Toyota</b>): 🚗"
        ),
        parse_mode="HTML"
    )
    await state.update_data(last_message_id=sent_message.message_id)
    await state.set_state(BookingStates.AwaitingAutoBrand)
    await callback.answer()

@service_booking_router.callback_query(BookingStates.AwaitingAddAnotherAuto, F.data == "continue_booking")
async def continue_booking(callback: CallbackQuery, state: FSMContext, bot: Bot):
    """Продолжает процесс бронирования."""
    try:
        await send_message_with_photo_fallback(
            callback, state, bot, "booking_final",
            get_progress_bar(BookingStates.AwaitingService).format(
                message=MESSAGES.get("booking", "Выберите <b>услугу</b> для записи на ТО: 🔧")
            ),
            Keyboards.services_kb()
        )
        await state.set_state(BookingStates.AwaitingService)
        await callback.answer()
    except Exception as e:
        await handle_error(callback, state, bot, "Ошибка. Попробуйте снова. 😔", "Ошибка продолжения записи", e)
        await callback.answer()

@service_booking_router.callback_query(BookingStates.AwaitingService, F.data.startswith("service_"))
async def process_service_selection(callback: CallbackQuery, state: FSMContext, bot: Bot):
    """Обрабатывает выбор услуги."""
    service_name = callback.data.replace("service_", "")
    if service_name not in [s["name"] for s in SERVICES]:
        await delete_previous_message(bot, callback.message.chat.id, (await state.get_data()).get("last_message_id"))
        sent_message = await callback.message.answer(
            get_progress_bar(BookingStates.AwaitingService).format(
                message="Некорректная услуга. Выберите снова: 🔧"
            ),
            reply_markup=Keyboards.services_kb(),
            parse_mode="HTML"
        )
        await state.update_data(last_message_id=sent_message.message_id)
        await callback.answer()
        return
    service_duration = next(s["duration_minutes"] for s in SERVICES if s["name"] == service_name)
    await state.update_data(service_name=service_name, service_duration=service_duration, week_offset=0)
    await delete_previous_message(bot, callback.message.chat.id, (await state.get_data()).get("last_message_id"))
    sent_message = await callback.message.answer(
        get_progress_bar(BookingStates.AwaitingDate).format(
            message="Выберите <b>дату</b> для записи: 📅"
        ),
        reply_markup=Keyboards.calendar_kb(),
        parse_mode="HTML"
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
async def process_date_selection(callback: CallbackQuery, state: FSMContext, bot: Bot):
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
                    get_progress_bar(BookingStates.AwaitingDate).format(
                        message="Нет доступных слотов на эту дату. Выберите другую дату: 📅"
                    ),
                    reply_markup=Keyboards.calendar_kb(selected_date, week_offset),
                    parse_mode="HTML"
                )
                await state.update_data(last_message_id=sent_message.message_id)
                await callback.answer()
                return
            await state.update_data(selected_date=selected_date, time_offset=0)
            await delete_previous_message(bot, callback.message.chat.id, (await state.get_data()).get("last_message_id"))
            sent_message = await callback.message.answer(
                get_progress_bar(BookingStates.AwaitingTime).format(
                    message="Выберите <b>время</b> для записи: ⏰"
                ),
                reply_markup=time_slots,
                parse_mode="HTML"
            )
            await state.update_data(last_message_id=sent_message.message_id)
            await state.set_state(BookingStates.AwaitingTime)
            await callback.answer()
    except ValueError:
        data = await state.get_data()
        week_offset = data.get("week_offset", 0)
        await delete_previous_message(bot, callback.message.chat.id, (await state.get_data()).get("last_message_id"))
        sent_message = await callback.message.answer(
            get_progress_bar(BookingStates.AwaitingDate).format(
                message="Некорректная дата. Выберите снова: 📅"
            ),
            reply_markup=Keyboards.calendar_kb(week_offset=week_offset),
            parse_mode="HTML"
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

@service_booking_router.callback_query(BookingStates.AwaitingTime, F.data.startswith("time_"))
async def process_time_selection(callback: CallbackQuery, state: FSMContext, bot: Bot):
    """Обрабатывает выбор времени."""
    time_str = callback.data.replace("time_", "")
    try:
        selected_time = datetime.strptime(time_str, "%H:%M").time()
        data = await state.get_data()
        with Session() as session:
            user = session.query(User).filter_by(telegram_id=str(callback.from_user.id)).first()
            auto = session.query(Auto).get(data["auto_id"])
            if not auto:
                await handle_error(
                    callback, state, bot,
                    "Автомобиль не найден. Начните заново. 🚗", f"Автомобиль не найден для auto_id={data['auto_id']}", Exception("Автомобиль не найден")
                )
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
                price=service_price,
                created_at=datetime.utcnow()
            )
            session.add(booking)
            session.commit()
            logger.info(f"Запись создана: {booking.id} для пользователя {callback.from_user.id}")
            await notify_master(bot, booking, user, auto)
            asyncio.create_task(schedule_reminder(bot, booking, user, auto))
            asyncio.create_task(schedule_user_reminder(bot, booking, user, auto))
            await delete_previous_message(bot, callback.message.chat.id, (await state.get_data()).get("last_message_id"))
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="Отменить запись ❌", callback_data=f"cancel_booking_{booking.id}")]
            ])
            sent_message = await callback.message.answer(
                f"Ваша заявка отправлена мастеру. Ожидайте подтверждения. ⏳\n"
                f"<b>Услуга:</b> {booking.service_name} ({service_price} ₽) 🔧",
                reply_markup=keyboard,
                parse_mode="HTML"
            )
            await state.update_data(last_message_id=sent_message.message_id)
            await state.clear()
            await callback.answer()
    except Exception as e:
        await handle_error(callback, state, bot, "Ошибка записи. Попробуйте снова. 😔", "Ошибка создания записи", e)
        await callback.answer()

@service_booking_router.callback_query(F.data.startswith("confirm_booking_"))
@master_only
async def confirm_booking(callback: CallbackQuery, state: FSMContext, bot: Bot):
    """Мастер подтверждает запись."""
    booking_id = int(callback.data.replace("confirm_booking_", ""))
    try:
        with Session() as session:
            booking, user, auto = await get_booking_context(session, booking_id, bot, callback, state)
            if not booking:
                await callback.answer()
                return
            booking.status = BookingStatus.CONFIRMED
            session.commit()
            await send_booking_notification(
                bot, user.telegram_id, booking, user, auto,
                "Ваша запись подтверждена! ✅"
            )
            await callback.message.edit_text(
                callback.message.text + "\n<b>Статус:</b> Подтверждено ✅",
                parse_mode="HTML"
            )
            await callback.answer("Запись подтверждена. ✅")
    except TelegramForbiddenError:
        logger.error(f"Не удалось отправить подтверждение пользователю для записи booking_id={booking_id}: пользователь заблокировал бота")
        await callback.answer("Ошибка: пользователь заблокировал бота. 🚫")
    except Exception as e:
        await handle_error(callback, state, bot, "Ошибка. Попробуйте снова. 😔", f"Ошибка подтверждения записи booking_id={booking_id}", e)
        await callback.answer()

@service_booking_router.callback_query(F.data.startswith("reschedule_booking_"))
@master_only
async def reschedule_booking(callback: CallbackQuery, state: FSMContext, bot: Bot):
    """Мастер предлагает другое время."""
    booking_id = int(callback.data.replace("reschedule_booking_", ""))
    try:
        with Session() as session:
            booking, _, _ = await get_booking_context(session, booking_id, bot, callback, state)
            if not booking:
                await callback.answer()
                return
        await state.update_data(booking_id=booking_id, master_action="reschedule")
        await callback.message.answer("Введите новое <b>время</b> (например, <b>14:30</b>): ⏰", parse_mode="HTML")
        await state.set_state(BookingStates.AwaitingMasterTime)
        logger.info(f"Мастер запросил новое время для записи booking_id={booking_id}")
        await callback.answer()
    except Exception as e:
        await handle_error(callback, state, bot, "Ошибка. Попробуйте снова. 😔", f"Ошибка переноса записи booking_id={booking_id}", e)
        await callback.answer()

@service_booking_router.callback_query(F.data.startswith("reject_booking_"))
@master_only
async def reject_booking(callback: CallbackQuery, state: FSMContext, bot: Bot):
    """Мастер отклоняет запись."""
    booking_id = int(callback.data.replace("reject_booking_", ""))
    await state.update_data(booking_id=booking_id, master_action="reject")
    await callback.message.answer("Укажите <b>причину</b> отказа: 📝", parse_mode="HTML")
    await state.set_state(BookingStates.AwaitingMasterResponse)
    logger.info(f"Мастер запросил причину отказа для записи booking_id={booking_id}")
    await callback.answer()

@service_booking_router.message(BookingStates.AwaitingMasterTime, F.text)
@master_only
async def process_master_time(message: Message, state: FSMContext, bot: Bot):
    """Обрабатывает ввод нового времени мастером."""
    data = await state.get_data()
    if "booking_id" not in data or "master_action" not in data or data["master_action"] != "reschedule":
        await handle_error(
            message, state, bot,
            "Ошибка: данные состояния отсутствуют. Попробуйте снова. 😔",
            "Некорректные данные состояния FSM", Exception("Некорректные данные состояния")
        )
        return
    booking_id = data.get("booking_id")
    try:
        with Session() as session:
            booking, user, auto = await get_booking_context(session, booking_id, bot, message, state)
            if not booking:
                return
            new_time = datetime.strptime(message.text, "%H:%M").time()
            booking.proposed_time = new_time
            booking.status = BookingStatus.PENDING
            session.commit()
            await set_user_state(
                state.key.bot_id, user.telegram_id, state.storage,
                BookingStates.AwaitingUserConfirmation, {"booking_id": booking_id}
            )
            await send_booking_notification(
                bot, user.telegram_id, booking, user, auto,
                f"Мастер предложил новое время для записи:\n<b>Новое время:</b> {new_time.strftime('%H:%M')} ⏰",
                Keyboards.confirm_reschedule_kb(booking_id)
            )
            await message.answer("Новое время отправлено пользователю. Ожидается подтверждение. ⏳", parse_mode="HTML")
            await state.clear()
    except ValueError:
        logger.warning(f"Некорректный формат времени '{message.text}' для записи booking_id={booking_id}")
        await message.answer("Некорректный формат времени. Введите снова (например, <b>14:30</b>): ⏰", parse_mode="HTML")
    except TelegramForbiddenError:
        await message.answer("Ошибка: пользователь заблокировал бота. 🚫", parse_mode="HTML")
    except TelegramBadRequest as e:
        await message.answer("Ошибка Telegram API при отправке сообщения. 😔", parse_mode="HTML")
    except Exception as e:
        await handle_error(
            message, state, bot,
            "Критическая ошибка. Попробуйте снова. 😔", f"Ошибка обработки нового времени для записи booking_id={booking_id}", e
        )

@service_booking_router.message(BookingStates.AwaitingMasterResponse, F.text)
@master_only
async def process_master_rejection(message: Message, state: FSMContext, bot: Bot):
    """Обрабатывает причину отказа мастера."""
    data = await state.get_data()
    if "booking_id" not in data or "master_action" not in data or data["master_action"] != "reject":
        await handle_error(
            message, state, bot,
            "Ошибка: данные состояния отсутствуют. Попробуйте снова. 😔",
            "Некорректные данные состояния FSM", Exception("Некорректные данные состояния")
        )
        return
    booking_id = data.get("booking_id")
    try:
        with Session() as session:
            booking, user, auto = await get_booking_context(session, booking_id, bot, message, state)
            if not booking:
                return
            booking.status = BookingStatus.REJECTED
            booking.rejection_reason = message.text
            session.commit()
            await send_booking_notification(
                bot, user.telegram_id, booking, user, auto,
                f"Ваша запись отклонена. ❌\n<b>Причина:</b> {message.text} 📝"
            )
            await message.answer("Отказ отправлен пользователю. ✅", parse_mode="HTML")
            await state.clear()
    except TelegramForbiddenError:
        await message.answer("Ошибка: пользователь заблокировал бота. 🚫", parse_mode="HTML")
    except Exception as e:
        await handle_error(
            message, state, bot,
            "Критическая ошибка. Попробуйте снова. 😔", f"Ошибка обработки отказа для записи booking_id={booking_id}", e
        )

@service_booking_router.callback_query(F.data.startswith("confirm_reschedule_"))
async def process_user_confirmation(callback: CallbackQuery, state: FSMContext, bot: Bot):
    """Обрабатывает подтверждение пользователем нового времени."""
    booking_id = int(callback.data.replace("confirm_reschedule_", ""))
    try:
        with Session() as session:
            booking, user, auto = await get_booking_context(session, booking_id, bot, callback, state)
            if not booking:
                await callback.answer()
                return
            if str(callback.from_user.id) != str(booking.user.telegram_id):
                logger.warning(f"Несанкционированный доступ: user_id={callback.from_user.id} != telegram_id={booking.user.telegram_id}")
                await callback.answer("Доступ только для владельца записи. 🔒")
                return
            if not booking.proposed_time:
                await handle_error(
                    callback, state, bot,
                    "Ошибка: предложенное время не найдено. ⏰", f"Предложенное время не найдено для booking_id={booking_id}",
                    Exception("Предложенное время не найдено")
                )
                await callback.answer()
                return
            booking.time = booking.proposed_time
            booking.proposed_time = None
            booking.status = BookingStatus.CONFIRMED
            session.commit()
            await send_booking_notification(
                bot, ADMIN_ID, booking, user, auto,
                f"Пользователь {user.first_name} {user.last_name} подтвердил запись: ✅"
            )
            await delete_previous_message(bot, callback.message.chat.id, (await state.get_data()).get("last_message_id"))
            sent_message = await callback.message.answer(
                f"Вы подтвердили запись: ✅\n"
                f"<b>Услуга:</b> {booking.service_name} 🔧\n"
                f"<b>Дата:</b> {booking.date.strftime('%d.%m.%Y')} 📅\n"
                f"<b>Время:</b> {booking.time.strftime('%H:%M')} ⏰\n"
                f"<b>Авто:</b> {auto.brand}, {auto.year}, {auto.license_plate} 🚗",
                reply_markup=Keyboards.main_menu_kb(),
                parse_mode="HTML"
            )
            await state.update_data(last_message_id=sent_message.message_id)
            await callback.answer("Запись подтверждена. ✅")
            await state.clear()
    except Exception as e:
        await handle_error(
            callback, state, bot,
            "Ошибка. Попробуйте снова. 😔", f"Ошибка подтверждения переноса для записи booking_id={booking_id}", e
        )
        await callback.answer()

@service_booking_router.callback_query(F.data.startswith("reject_reschedule_"))
async def process_user_rejection(callback: CallbackQuery, state: FSMContext, bot: Bot):
    """Обрабатывает отклонение пользователем нового времени."""
    booking_id = int(callback.data.replace("reject_reschedule_", ""))
    try:
        with Session() as session:
            booking, user, auto = await get_booking_context(session, booking_id, bot, callback, state)
            if not booking:
                await callback.answer()
                return
            if str(callback.from_user.id) != str(booking.user.telegram_id):
                logger.warning(f"Несанкционированный доступ: user_id={callback.from_user.id} != telegram_id={booking.user.telegram_id}")
                await callback.answer("Доступ только для владельца записи. 🔒")
                return
            booking.status = BookingStatus.REJECTED
            booking.rejection_reason = "Пользователь отклонил предложенное время"
            booking.proposed_time = None
            session.commit()
            await send_booking_notification(
                bot, ADMIN_ID, booking, user, auto,
                f"Пользователь {user.first_name} {user.last_name} отклонил запись:\n<b>Причина:</b> Пользователь отклонил предложенное время 📝"
            )
            await delete_previous_message(bot, callback.message.chat.id, (await state.get_data()).get("last_message_id"))
            sent_message = await callback.message.answer(
                f"Вы отклонили предложенное время для записи: ❌\n"
                f"<b>Услуга:</b> {booking.service_name} 🔧\n"
                f"<b>Дата:</b> {booking.date.strftime('%d.%m.%Y')} 📅\n"
                f"<b>Авто:</b> {auto.brand}, {auto.year}, {auto.license_plate} 🚗",
                reply_markup=Keyboards.main_menu_kb(),
                parse_mode="HTML"
            )
            await state.update_data(last_message_id=sent_message.message_id)
            await callback.answer("Запись отклонена. ❌")
            await state.clear()
    except Exception as e:
        await handle_error(
            callback, state, bot,
            "Ошибка. Попробуйте снова. 😔", f"Ошибка отклонения переноса для записи booking_id={booking_id}", e
        )
        await callback.answer()

@service_booking_router.callback_query(F.data.startswith("cancel_booking_"))
async def process_booking_cancellation(callback: CallbackQuery, state: FSMContext, bot: Bot):
    """Обрабатывает отмену записи пользователем."""
    booking_id = int(callback.data.replace("cancel_booking_", ""))
    try:
        with Session() as session:
            booking, user, auto = await get_booking_context(session, booking_id, bot, callback, state)
            if not booking:
                await callback.answer()
                return
            if str(callback.from_user.id) != str(booking.user.telegram_id):
                logger.warning(f"Несанкционированный доступ: user_id={callback.from_user.id} != telegram_id={booking.user.telegram_id}")
                await callback.answer("Доступ только для владельца записи. 🔒")
                return
            booking.status = BookingStatus.CANCELLED
            booking.rejection_reason = "Отменено пользователем"
            session.commit()
            await send_booking_notification(
                bot, ADMIN_ID, booking, user, auto,
                f"Пользователь {user.first_name} {user.last_name} отменил запись: ❌",
                parse_mode="HTML"
            )
            await delete_previous_message(bot, callback.message.chat.id, (await state.get_data()).get("last_message_id"))
            sent_message = await callback.message.answer(
                f"Вы отменили запись: ❌\n"
                f"<b>Услуга:</b> {booking.service_name} 🔧\n"
                f"<b>Дата:</b> {booking.date.strftime('%d.%m.%Y')} 📅\n"
                f"<b>Время:</b> {booking.time.strftime('%H:%M')} ⏰",
                reply_markup=Keyboards.main_menu_kb(),
                parse_mode="HTML"
            )
            await state.update_data(last_message_id=sent_message.message_id)
            await callback.answer("Запись отменена. ❌")
            await state.clear()
    except Exception as e:
        await handle_error(
            callback, state, bot,
            "Ошибка. Попробуйте снова. 😔", f"Ошибка отмены записи booking_id={booking_id}", e
        )
        await callback.answer()

@service_booking_router.message(F.text == "Мои записи 📜")
async def show_bookings(message: Message, state: FSMContext, bot: Bot):
    """Показывает список записей пользователя."""
    try:
        with Session() as session:
            user = session.query(User).filter_by(telegram_id=str(message.from_user.id)).first()
            if not user:
                await handle_error(
                    message, state, bot,
                    "Вы не зарегистрированы. Начните с команды 'Запись на ТО'. 😔",
                    "Пользователь не найден", Exception("Пользователь не найден")
                )
                return
            bookings = session.query(Booking).filter_by(user_id=user.id).all()
            if not bookings:
                await delete_previous_message(bot, message.chat.id, (await state.get_data()).get("last_message_id"))
                sent_message = await message.answer(
                    "У вас нет записей. Создайте новую с помощью 'Запись на ТО'. 📝",
                    reply_markup=Keyboards.main_menu_kb(),
                    parse_mode="HTML"
                )
                await state.update_data(last_message_id=sent_message.message_id)
                return
            response = "<b>Ваши записи:</b> 📜\n\n"
            for booking in bookings:
                auto = session.query(Auto).get(booking.auto_id)
                status_map = {
                    BookingStatus.PENDING: "Ожидает подтверждения ⏳",
                    BookingStatus.CONFIRMED: "Подтверждено ✅",
                    BookingStatus.REJECTED: "Отклонено ❌",
                    BookingStatus.CANCELLED: "Отменено 🚫"
                }
                response += (
                    f"<b>Запись #{booking.id}</b>\n"
                    f"<b>Услуга:</b> {booking.service_name} 🔧\n"
                    f"<b>Дата:</b> {booking.date.strftime('%d.%m.%Y')} 📅\n"
                    f"<b>Время:</b> {booking.time.strftime('%H:%M')} ⏰\n"
                    f"<b>Авто:</b> {auto.brand}, {auto.year}, {auto.license_plate} 🚗\n"
                    f"<b>Статус:</b> {status_map[booking.status]}"
                )
                if booking.rejection_reason:
                    response += f"\n<b>Причина отказа:</b> {booking.rejection_reason} 📝"
                response += "\n\n"
            await delete_previous_message(bot, message.chat.id, (await state.get_data()).get("last_message_id"))
            sent_message = await message.answer(
                response,
                reply_markup=Keyboards.main_menu_kb(),
                parse_mode="HTML"
            )
            await state.update_data(last_message_id=sent_message.message_id)
    except Exception as e:
        await handle_error(
            message, state, bot,
            "Ошибка. Попробуйте снова. 😔", "Ошибка получения записей", e
        )

@service_booking_router.callback_query(F.data == "cancel_booking")
async def cancel_booking(callback: CallbackQuery, state: FSMContext, bot: Bot):
    """Отменяет процесс бронирования."""
    await delete_previous_message(bot, callback.message.chat.id, (await state.get_data()).get("last_message_id"))
    sent_message = await callback.message.answer(
        "Действие отменено. ❌",
        reply_markup=Keyboards.main_menu_kb(),
        parse_mode="HTML"
    )
    await state.update_data(last_message_id=sent_message.message_id)
    await state.clear()
    await callback.answer()
from datetime import datetime

from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from pydantic import ValidationError

from config import MESSAGES
from keyboards.main_kb import Keyboards
from utils import setup_logger, UserInput, AutoInput
from database import User, Auto, Booking, BookingStatus, Session
from .service_utils import send_message, handle_error, get_progress_bar

profile_router = Router()
logger = setup_logger(__name__)


# Состояния для личного кабинета
class ProfileStates(StatesGroup):
    MainMenu = State()
    EditingProfile = State()
    AwaitingFirstName = State()
    AwaitingLastName = State()
    AwaitingPhone = State()
    ManagingAutos = State()
    AwaitingAutoBrand = State()
    AwaitingAutoYear = State()
    AwaitingAutoVin = State()
    AwaitingAutoLicensePlate = State()
    RegisterFirstName = State()  # Новое состояние для регистрации
    RegisterLastName = State()
    RegisterPhone = State()


PROFILE_PROGRESS_STEPS = {
    str(ProfileStates.AwaitingFirstName): 1,
    str(ProfileStates.AwaitingLastName): 2,
    str(ProfileStates.AwaitingPhone): 3,
    str(ProfileStates.AwaitingAutoBrand): 1,
    str(ProfileStates.AwaitingAutoYear): 2,
    str(ProfileStates.AwaitingAutoVin): 3,
    str(ProfileStates.AwaitingAutoLicensePlate): 4,
    str(ProfileStates.RegisterFirstName): 1,
    str(ProfileStates.RegisterLastName): 2,
    str(ProfileStates.RegisterPhone): 3
}


@profile_router.message(F.text == "Личный кабинет 👤")
async def enter_profile(message: Message, state: FSMContext, bot: Bot):
    """Вход в личный кабинет или начало регистрации."""
    logger.info(f"Пользователь {message.from_user.id} вошёл в личный кабинет")
    try:
        with Session() as session:
            user = session.query(User).filter_by(telegram_id=str(message.from_user.id)).first()
            if not user:
                logger.info(f"Пользователь {message.from_user.id} не зарегистрирован, начало регистрации")
                sent_message = await send_message(
                    bot, str(message.chat.id), "text",
                    (await get_progress_bar(ProfileStates.RegisterFirstName, PROFILE_PROGRESS_STEPS,
                                            style="emoji")).format(
                        message="Давайте познакомимся! 👤 Введите ваше <b>имя</b>:"
                    )
                )
                if sent_message:
                    await state.update_data(last_message_id=sent_message.message_id)
                    await state.set_state(ProfileStates.RegisterFirstName)
                return
            response = (
                f"<b>Личный кабинет</b> 👤\n"
                f"Имя: {user.first_name}\n"
                f"Фамилия: {user.last_name}\n"
                f"Телефон: {user.phone}\n"
            )
            sent_message = await send_message(
                bot, str(message.chat.id), "text",
                response,
                reply_markup=Keyboards.profile_menu_kb()
            )
            if sent_message:
                logger.debug(f"Сообщение личного кабинета отправлено для {message.from_user.id}")
                await state.update_data(last_message_id=sent_message.message_id)
                await state.set_state(ProfileStates.MainMenu)
    except Exception as e:
        logger.error(f"Ошибка входа в личный кабинет для {message.from_user.id}: {str(e)}")
        await handle_error(message, state, bot, "Ошибка. Попробуйте снова. 😔", "Ошибка входа в личный кабинет", e)


@profile_router.message(ProfileStates.RegisterFirstName, F.text)
async def process_register_first_name(message: Message, state: FSMContext, bot: Bot):
    """Обработка имени при регистрации."""
    from .service_utils import process_user_input
    await process_user_input(
        message, state, bot,
        UserInput.validate_first_name, "first_name",
        "Введите вашу <b>фамилию</b>: 👤",
        "Имя слишком короткое или длинное (2–50 символов). Введите снова: 😔",
        ProfileStates.RegisterLastName,
        PROFILE_PROGRESS_STEPS
    )


@profile_router.message(ProfileStates.RegisterLastName, F.text)
async def process_register_last_name(message: Message, state: FSMContext, bot: Bot):
    """Обработка фамилии при регистрации."""
    from .service_utils import process_user_input
    await process_user_input(
        message, state, bot,
        UserInput.validate_last_name, "last_name",
        "Введите ваш номер телефона, начиная с <b>+7</b> (например, <b>+79991234567</b>): 📞",
        "Фамилия слишком короткая или длинная (2–50 символов). Введите снова: 😔",
        ProfileStates.RegisterPhone,
        PROFILE_PROGRESS_STEPS
    )


@profile_router.message(ProfileStates.RegisterPhone, F.text)
async def process_register_phone(message: Message, state: FSMContext, bot: Bot):
    """Обработка телефона и регистрация пользователя."""
    logger.info(f"Пользователь {message.from_user.id} ввёл телефон для регистрации")
    try:
        phone = message.text.strip()
        # Проверяем телефон через validate_phone
        UserInput.validate_phone(phone)
        data = await state.get_data()
        user_input = UserInput(
            first_name=data["first_name"],
            last_name=data["last_name"],
            phone=phone
        )
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
            response = (
                f"<b>Регистрация завершена</b> ✅\n"
                f"Имя: {user.first_name}\n"
                f"Фамилия: {user.last_name}\n"
                f"Телефон: {user.phone}\n"
            )
            sent_message = await send_message(
                bot, str(message.chat.id), "text",
                response,
                reply_markup=Keyboards.profile_menu_kb()
            )
            if sent_message:
                await state.update_data(last_message_id=sent_message.message_id)
                await state.set_state(ProfileStates.MainMenu)
    except ValidationError as e:
        logger.error(f"Ошибка валидации телефона для {message.from_user.id}: {str(e)}")
        sent_message = await send_message(
            bot, str(message.chat.id), "text",
            (await get_progress_bar(ProfileStates.RegisterPhone, PROFILE_PROGRESS_STEPS, style="emoji")).format(
                message="Некорректный номер телефона. Введите номер, начиная с +7 (например, +79991234567): 📞"
            )
        )
        if sent_message:
            await state.update_data(last_message_id=sent_message.message_id)
    except Exception as e:
        logger.error(f"Ошибка регистрации для {message.from_user.id}: {str(e)}")
        await handle_error(message, state, bot, "Ошибка регистрации. Попробуйте снова. 😔", "Ошибка регистрации", e)


@profile_router.callback_query(ProfileStates.MainMenu, F.data == "edit_profile")
async def edit_profile(callback: CallbackQuery, state: FSMContext, bot: Bot):
    """Редактирование личных данных."""
    logger.info(f"Пользователь {callback.from_user.id} начал редактирование профиля")
    sent_message = await send_message(
        bot, str(callback.message.chat.id), "text",
        (await get_progress_bar(ProfileStates.AwaitingFirstName, PROFILE_PROGRESS_STEPS, style="emoji")).format(
            message="Введите ваше <b>имя</b>: 👤"
        )
    )
    if sent_message:
        await state.update_data(last_message_id=sent_message.message_id)
        await state.set_state(ProfileStates.AwaitingFirstName)
    await callback.answer()


@profile_router.message(ProfileStates.AwaitingFirstName, F.text)
async def process_first_name(message: Message, state: FSMContext, bot: Bot):
    """Обработка имени."""
    from .service_utils import process_user_input
    await process_user_input(
        message, state, bot,
        UserInput.validate_first_name, "first_name",
        "Введите вашу <b>фамилию</b>: 👤",
        "Имя слишком короткое или длинное (2–50 символов). Введите снова: 😔",
        ProfileStates.AwaitingLastName,
        PROFILE_PROGRESS_STEPS
    )


@profile_router.message(ProfileStates.AwaitingLastName, F.text)
async def process_last_name(message: Message, state: FSMContext, bot: Bot):
    """Обработка фамилии."""
    from .service_utils import process_user_input
    await process_user_input(
        message, state, bot,
        UserInput.validate_last_name, "last_name",
        "Введите ваш номер телефона, начиная с <b>+7</b> (например, <b>+79991234567</b>): 📞",
        "Фамилия слишком короткая или длинная (2–50 символов). Введите снова: 😔",
        ProfileStates.AwaitingPhone,
        PROFILE_PROGRESS_STEPS
    )


@profile_router.message(ProfileStates.AwaitingPhone, F.text)
async def process_phone(message: Message, state: FSMContext, bot: Bot):
    """Обработка телефона и сохранение данных."""
    logger.info(f"Пользователь {message.from_user.id} ввёл телефон")
    try:
        phone = message.text.strip()
        # Проверяем телефон через validate_phone
        UserInput.validate_phone(phone)
        data = await state.get_data()
        user_input = UserInput(
            first_name=data["first_name"],
            last_name=data["last_name"],
            phone=phone
        )
        with Session() as session:
            user = session.query(User).filter_by(telegram_id=str(message.from_user.id)).first()
            user.first_name = user_input.first_name
            user.last_name = user_input.last_name
            user.phone = user_input.phone
            session.commit()
            logger.info(f"Пользователь {message.from_user.id} обновил данные")
            response = (
                f"<b>Данные обновлены</b> ✅\n"
                f"Имя: {user.first_name}\n"
                f"Фамилия: {user.last_name}\n"
                f"Телефон: {user.phone}\n"
            )
            sent_message = await send_message(
                bot, str(message.chat.id), "text",
                response,
                reply_markup=Keyboards.profile_menu_kb()
            )
            if sent_message:
                await state.update_data(last_message_id=sent_message.message_id)
                await state.set_state(ProfileStates.MainMenu)
    except ValidationError as e:
        logger.error(f"Ошибка валидации телефона для {message.from_user.id}: {str(e)}")
        sent_message = await send_message(
            bot, str(message.chat.id), "text",
            (await get_progress_bar(ProfileStates.AwaitingPhone, PROFILE_PROGRESS_STEPS, style="emoji")).format(
                message="Некорректный номер телефона. Введите номер, начиная с +7 (например, +79991234567): 📞"
            )
        )
        if sent_message:
            await state.update_data(last_message_id=sent_message.message_id)
    except Exception as e:
        logger.error(f"Ошибка обновления данных для {message.from_user.id}: {str(e)}")
        await handle_error(message, state, bot, "Ошибка. Попробуйте снова. 😔", "Ошибка обновления данных", e)


@profile_router.callback_query(ProfileStates.MainMenu, F.data == "manage_autos")
async def manage_autos(callback: CallbackQuery, state: FSMContext, bot: Bot):
    """Управление автомобилями."""
    logger.info(f"Пользователь {callback.from_user.id} запросил управление автомобилями")
    try:
        with Session() as session:
            user = session.query(User).filter_by(telegram_id=str(callback.from_user.id)).first()
            autos = session.query(Auto).filter_by(user_id=user.id).all()
            if not autos:
                sent_message = await send_message(
                    bot, str(callback.message.chat.id), "text",
                    "У вас нет автомобилей. Введите <b>марку</b> автомобиля (например, <b>Toyota</b>): 🚗",
                    reply_markup=Keyboards.cancel_kb()
                )
                if sent_message:
                    await state.update_data(last_message_id=sent_message.message_id)
                    await state.set_state(ProfileStates.AwaitingAutoBrand)
                await callback.answer()
                return
            response = "<b>Ваши автомобили</b> 🚗\n\n"
            for auto in autos:
                response += (
                    f"ID: {auto.id}\n"
                    f"Марка: {auto.brand}\n"
                    f"Год: {auto.year}\n"
                    f"Госномер: {auto.license_plate}\n\n"
                )
            sent_message = await send_message(
                bot, str(callback.message.chat.id), "text",
                response,
                reply_markup=Keyboards.auto_management_kb(autos)
            )
            if sent_message:
                await state.update_data(last_message_id=sent_message.message_id)
                await state.set_state(ProfileStates.ManagingAutos)
            await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка управления автомобилями для {callback.from_user.id}: {str(e)}")
        await handle_error(callback, state, bot, "Ошибка. Попробуйте снова. 😔", "Ошибка управления автомобилями", e)
        await callback.answer()


@profile_router.callback_query(ProfileStates.ManagingAutos, F.data == "add_auto")
async def add_auto(callback: CallbackQuery, state: FSMContext, bot: Bot):
    """Добавление нового автомобиля."""
    logger.info(f"Пользователь {callback.from_user.id} начал добавление автомобиля")
    sent_message = await send_message(
        bot, str(callback.message.chat.id), "text",
        (await get_progress_bar(ProfileStates.AwaitingAutoBrand, PROFILE_PROGRESS_STEPS, style="emoji")).format(
            message="Введите <b>марку</b> автомобиля (например, <b>Toyota</b>): 🚗"
        ),
        reply_markup=Keyboards.cancel_kb()
    )
    if sent_message:
        await state.update_data(last_message_id=sent_message.message_id)
        await state.set_state(ProfileStates.AwaitingAutoBrand)
    await callback.answer()


@profile_router.message(ProfileStates.AwaitingAutoBrand, F.text)
async def process_auto_brand(message: Message, state: FSMContext, bot: Bot):
    """Обработка марки автомобиля."""
    from .service_utils import process_user_input
    await process_user_input(
        message, state, bot,
        AutoInput.validate_brand, "brand",
        "Введите <b>год выпуска</b> автомобиля (например, <b>2020</b>): 📅",
        "Марка слишком короткая или длинная (2–50 символов). Введите снова: 😔",
        ProfileStates.AwaitingAutoYear,
        PROFILE_PROGRESS_STEPS,
        reply_markup=Keyboards.cancel_kb()
    )


@profile_router.message(ProfileStates.AwaitingAutoYear, F.text)
async def process_auto_year(message: Message, state: FSMContext, bot: Bot):
    """Обработка года выпуска."""
    logger.info(f"Пользователь {message.from_user.id} ввёл год автомобиля")
    try:
        year = int(message.text.strip())
        AutoInput.validate_year(year)
        await state.update_data(year=year)
        sent_message = await send_message(
            bot, str(message.chat.id), "text",
            (await get_progress_bar(ProfileStates.AwaitingAutoVin, PROFILE_PROGRESS_STEPS, style="emoji")).format(
                message="Введите <b>VIN-номер</b> автомобиля (17 букв/цифр, например, <b>JTDBT923771012345</b>): 🔢"
            ),
            reply_markup=Keyboards.cancel_kb()
        )
        if sent_message:
            await state.update_data(last_message_id=sent_message.message_id)
            await state.set_state(ProfileStates.AwaitingAutoVin)
    except Exception as e:
        logger.error(f"Ошибка обработки года автомобиля для {message.from_user.id}: {str(e)}")
        sent_message = await send_message(
            bot, str(message.chat.id), "text",
            (await get_progress_bar(ProfileStates.AwaitingAutoYear, PROFILE_PROGRESS_STEPS, style="emoji")).format(
                message=f"Некорректный год (1900–{datetime.today().year}). Введите снова: 📅"
            ),
            reply_markup=Keyboards.cancel_kb()
        )
        if sent_message:
            await state.update_data(last_message_id=sent_message.message_id)


@profile_router.message(ProfileStates.AwaitingAutoVin, F.text)
async def process_auto_vin(message: Message, state: FSMContext, bot: Bot):
    """Обработка VIN-номера."""
    from .service_utils import process_user_input
    await process_user_input(
        message, state, bot,
        AutoInput.validate_vin, "vin",
        "Введите <b>государственный номер</b> автомобиля (например, <b>А123БВ45</b>): 🚘",
        "Некорректный VIN (17 букв/цифр). Введите снова: 😔",
        ProfileStates.AwaitingAutoLicensePlate,
        PROFILE_PROGRESS_STEPS,
        reply_markup=Keyboards.cancel_kb()
    )


@profile_router.message(ProfileStates.AwaitingAutoLicensePlate, F.text)
async def process_auto_license_plate(message: Message, state: FSMContext, bot: Bot):
    """Обработка госномера и сохранение автомобиля."""
    logger.info(f"Пользователь {message.from_user.id} ввёл госномер автомобиля")
    try:
        license_plate = message.text.strip()
        data = await state.get_data()
        auto_input = AutoInput(
            brand=data["brand"],
            year=data["year"],
            vin=data["vin"],
            license_plate=license_plate
        )
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
            autos = session.query(Auto).filter_by(user_id=user.id).all()
            response = "<b>Автомобиль добавлен</b> 🎉\n\n"
            for auto in autos:
                response += (
                    f"ID: {auto.id}\n"
                    f"Марка: {auto.brand}\n"
                    f"Год: {auto.year}\n"
                    f"Госномер: {auto.license_plate}\n\n"
                )
            sent_message = await send_message(
                bot, str(message.chat.id), "text",
                response,
                reply_markup=Keyboards.auto_management_kb(autos)
            )
            if sent_message:
                await state.update_data(last_message_id=sent_message.message_id)
                await state.set_state(ProfileStates.ManagingAutos)
    except Exception as e:
        logger.error(f"Ошибка добавления автомобиля для {message.from_user.id}: {str(e)}")
        sent_message = await send_message(
            bot, str(message.chat.id), "text",
            (await get_progress_bar(ProfileStates.AwaitingAutoLicensePlate, PROFILE_PROGRESS_STEPS,
                                    style="emoji")).format(
                message="Госномер слишком короткий или длинный (5–20 символов). Введите снова: 🚘"
            ),
            reply_markup=Keyboards.cancel_kb()
        )
        if sent_message:
            await state.update_data(last_message_id=sent_message.message_id)


@profile_router.callback_query(ProfileStates.ManagingAutos, F.data.startswith("delete_auto_"))
async def delete_auto(callback: CallbackQuery, state: FSMContext, bot: Bot):
    """Удаление автомобиля."""
    logger.info(f"Пользователь {callback.from_user.id} запросил удаление автомобиля")
    auto_id = int(callback.data.replace("delete_auto_", ""))
    try:
        with Session() as session:
            auto = session.query(Auto).get(auto_id)
            if not auto:
                logger.warning(f"Автомобиль {auto_id} не найден для пользователя {callback.from_user.id}")
                await handle_error(callback, state, bot, "Автомобиль не найден. 😔", "Автомобиль не найден",
                                   Exception("Auto not found"))
                await callback.answer()
                return

            # Проверяем наличие активных записей
            active_bookings = session.query(Booking).filter(
                Booking.auto_id == auto_id,
                Booking.status.in_([BookingStatus.PENDING, BookingStatus.CONFIRMED])
            ).all()
            if active_bookings:
                logger.warning(f"Невозможно удалить автомобиль {auto_id}: есть активные записи")
                sent_message = await send_message(
                    bot, str(callback.message.chat.id), "text",
                    "Невозможно удалить автомобиль: есть активные записи. Отмените их в 'Мои записи'. 📝",
                    reply_markup=Keyboards.auto_management_kb(
                        session.query(Auto).filter_by(user_id=auto.user_id).all()
                    )
                )
                if sent_message:
                    await state.update_data(last_message_id=sent_message.message_id)
                await callback.answer()
                return

            # Удаляем неактивные записи (REJECTED, CANCELLED)
            session.query(Booking).filter(
                Booking.auto_id == auto_id,
                Booking.status.in_([BookingStatus.REJECTED, BookingStatus.CANCELLED])
            ).delete()

            # Удаляем автомобиль
            session.delete(auto)
            session.commit()
            logger.info(f"Автомобиль {auto_id} удалён для пользователя {callback.from_user.id}")

            autos = session.query(Auto).filter_by(user_id=auto.user_id).all()
            if not autos:
                sent_message = await send_message(
                    bot, str(callback.message.chat.id), "text",
                    "У вас больше нет автомобилей. Добавьте новый: 🚗",
                    reply_markup=Keyboards.auto_management_kb(autos)
                )
                if sent_message:
                    await state.update_data(last_message_id=sent_message.message_id)
                    await state.set_state(ProfileStates.ManagingAutos)
                await callback.answer()
                return

            response = "<b>Автомобиль удалён</b> 🗑\n\n"
            for auto in autos:
                response += (
                    f"ID: {auto.id}\n"
                    f"Марка: {auto.brand}\n"
                    f"Год: {auto.year}\n"
                    f"Госномер: {auto.license_plate}\n\n"
                )
            sent_message = await send_message(
                bot, str(callback.message.chat.id), "text",
                response,
                reply_markup=Keyboards.auto_management_kb(autos)
            )
            if sent_message:
                await state.update_data(last_message_id=sent_message.message_id)
                await state.set_state(ProfileStates.ManagingAutos)
            await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка удаления автомобиля для {callback.from_user.id}: {str(e)}")
        await handle_error(callback, state, bot, "Ошибка. Попробуйте снова. 😔", "Ошибка удаления автомобиля", e)
        await callback.answer()


@profile_router.callback_query(ProfileStates.MainMenu, F.data == "my_bookings")
async def show_bookings(callback: CallbackQuery, state: FSMContext, bot: Bot):
    """Показ активных записей."""
    logger.info(f"Пользователь {callback.from_user.id} запросил активные записи")
    try:
        with Session() as session:
            user = session.query(User).filter_by(telegram_id=str(callback.from_user.id)).first()
            bookings = session.query(Booking).filter(
                Booking.user_id == user.id,
                Booking.status.in_([BookingStatus.PENDING, BookingStatus.CONFIRMED])
            ).all()
            if not bookings:
                sent_message = await send_message(
                    bot, str(callback.message.chat.id), "text",
                    "У вас нет активных записей. 📝",
                    reply_markup=Keyboards.profile_menu_kb()
                )
                if sent_message:
                    await state.update_data(last_message_id=sent_message.message_id)
                await state.set_state(ProfileStates.MainMenu)
                await callback.answer()
                return
            response = "<b>Ваши активные записи</b> 📜\n\n"
            for booking in bookings:
                auto = session.query(Auto).get(booking.auto_id)
                status_map = {
                    BookingStatus.PENDING: "Ожидает подтверждения ⏳",
                    BookingStatus.CONFIRMED: "Подтверждено ✅"
                }
                response += (
                    f"<b>Запись #{booking.id}</b>\n"
                    f"<b>Услуга:</b> {booking.service_name} 🔧\n"
                    f"<b>Дата:</b> {booking.date.strftime('%d.%m.%Y')} 📅\n"
                    f"<b>Время:</b> {booking.time.strftime('%H:%M')} ⏰\n"
                    f"<b>Авто:</b> {auto.brand}, {auto.year}, {auto.license_plate} 🚗\n"
                    f"<b>Статус:</b> {status_map[booking.status]}\n\n"
                )
            sent_message = await send_message(
                bot, str(callback.message.chat.id), "text",
                response,
                reply_markup=Keyboards.profile_menu_kb()
            )
            if sent_message:
                await state.update_data(last_message_id=sent_message.message_id)
                await state.set_state(ProfileStates.MainMenu)
            await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка получения записей для {callback.from_user.id}: {str(e)}")
        await handle_error(callback, state, bot, "Ошибка. Попробуйте снова. 😔", "Ошибка получения записей", e)
        await callback.answer()


@profile_router.callback_query(ProfileStates.MainMenu, F.data == "booking_history")
async def show_booking_history(callback: CallbackQuery, state: FSMContext, bot: Bot):
    """Показ истории записей."""
    logger.info(f"Пользователь {callback.from_user.id} запросил историю записей")
    try:
        with Session() as session:
            user = session.query(User).filter_by(telegram_id=str(callback.from_user.id)).first()
            bookings = session.query(Booking).filter(
                Booking.user_id == user.id,
                Booking.status.in_([BookingStatus.REJECTED, BookingStatus.CANCELLED])
            ).all()
            if not bookings:
                sent_message = await send_message(
                    bot, str(callback.message.chat.id), "text",
                    "У вас нет завершённых или отменённых записей. 📝",
                    reply_markup=Keyboards.profile_menu_kb()
                )
                if sent_message:
                    await state.update_data(last_message_id=sent_message.message_id)
                await state.set_state(ProfileStates.MainMenu)
                await callback.answer()
                return
            response = "<b>История записей</b> 📜\n\n"
            for booking in bookings:
                auto = session.query(Auto).get(booking.auto_id)
                status_map = {
                    BookingStatus.PENDING: "Ожидает подтверждения ⏳",
                    BookingStatus.CONFIRMED: "Подтверждено ✅",
                    BookingStatus.REJECTED: "Отклонено ❌",
                    BookingStatus.CANCELLED: "Отменено 🚫"  # Добавляем отображение
                }
                response += (
                    f"<b>Запись #{booking.id}</b>\n"
                    f"<b>Услуга:</b> {booking.service_name} 🔧\n"
                    f"<b>Дата:</b> {booking.date.strftime('%d.%m.%Y')} 📅\n"
                    f"<b>Время:</b> {booking.time.strftime('%H:%M')} ⏰\n"
                    f"<b>Авто:</b> {auto.brand}, {auto.year}, {auto.license_plate} 🚗\n"
                    f"<b>Статус:</b> {status_map[booking.status]}\n"
                )
                if booking.rejection_reason:
                    response += f"<b>Причина:</b> {booking.rejection_reason}\n"
                response += "\n"
            sent_message = await send_message(
                bot, str(callback.message.chat.id), "text",
                response,
                reply_markup=Keyboards.profile_menu_kb()
            )
            if sent_message:
                await state.update_data(last_message_id=sent_message.message_id)
                await state.set_state(ProfileStates.MainMenu)
            await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка получения истории записей для {callback.from_user.id}: {str(e)}")
        await handle_error(callback, state, bot, "Ошибка. Попробуйте снова. 😔", "Ошибка получения истории записей", e)
        await callback.answer()


@profile_router.callback_query(F.data == "back_to_main")
async def back_to_main(callback: CallbackQuery, state: FSMContext, bot: Bot):
    """Возврат в главное меню."""
    logger.info(f"Пользователь {callback.from_user.id} вернулся в главное меню")
    sent_message = await send_message(
        bot, str(callback.message.chat.id), "text",
        "Главное меню",
        reply_markup=Keyboards.main_menu_kb()
    )
    if sent_message:
        await state.update_data(last_message_id=sent_message.message_id)
    await state.clear()
    await callback.answer()
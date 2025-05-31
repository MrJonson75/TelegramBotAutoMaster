import os
from datetime import datetime
from aiogram import Router, F, Bot
from aiogram.types import (Message, CallbackQuery, InlineKeyboardMarkup,
                           InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton)
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from pydantic import ValidationError
from keyboards.main_kb import Keyboards
from database import User, Auto, Booking, BookingStatus, Session, Review
from utils import (send_message, handle_error, get_progress_bar,
                   send_booking_notification, setup_logger, UserInput, AutoInput)
from config import get_photo_path, ADMIN_ID, UPLOAD_USER_DIR

profile_router = Router()
logger = setup_logger(__name__)

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
    RegisterAwaitingPhone = State()
    RegisterConfirm = State()
    ViewingBooking = State()
    AwaitingReviewRating = State()  # Для выбора рейтинга
    AwaitingReviewText = State()  # Для ввода текста отзыва
    AwaitingReviewPhotos = State()  # Для загрузки фотографий
    AwaitingReviewVideo = State()  # Для загрузки видео
    ConfirmReview = State()  # Для подтверждения отзыва

PROFILE_PROGRESS_STEPS = {
    str(ProfileStates.AwaitingFirstName): 1,
    str(ProfileStates.AwaitingLastName): 2,
    str(ProfileStates.AwaitingPhone): 3,
    str(ProfileStates.AwaitingAutoBrand): 1,
    str(ProfileStates.AwaitingAutoYear): 2,
    str(ProfileStates.AwaitingAutoVin): 3,
    str(ProfileStates.AwaitingAutoLicensePlate): 4,
    str(ProfileStates.RegisterAwaitingPhone): 1,
    str(ProfileStates.RegisterConfirm): 2,
    str(ProfileStates.AwaitingReviewText): 1,
    str(ProfileStates.AwaitingReviewPhotos): 2,
    str(ProfileStates.ConfirmReview): 3
}

@profile_router.message(F.text == "Личный кабинет 👤")
async def enter_profile(message: Message, state: FSMContext, bot: Bot):
    """Вход в личный кабинет или начало регистрации."""
    logger.info(f"Пользователь {message.from_user.id} вошёл в личный кабинет")
    try:
        with Session() as session:
            user = session.query(User).filter_by(telegram_id=str(message.from_user.id)).first()
            if user:
                response = (
                    f"<b>Личный кабинет</b> 👤\n"
                    f"Имя: {user.first_name}\n"
                    f"Фамилия: {user.last_name or 'Не указано'}\n"
                    f"Телефон: {user.phone or 'Не указано'}\n"
                    f"Имя пользователя: {user.username or 'Не указано'}\n"
                    f"Дата рождения: {user.birth_date or 'Не указано'}\n"
                )
                try:
                    photo_path = get_photo_path("profile")
                    sent_message = await send_message(
                        bot, str(message.chat.id), "photo",
                        response,
                        photo=photo_path,
                        reply_markup=Keyboards.profile_menu_kb()
                    )
                except FileNotFoundError as e:
                    logger.warning(f"Не удалось отправить фото профиля для {message.from_user.id}: {str(e)}")
                    sent_message = await send_message(
                        bot, str(message.chat.id), "text",
                        response,
                        reply_markup=Keyboards.profile_menu_kb()
                    )
                if sent_message:
                    logger.debug(f"Сообщение личного кабинета отправлено для {message.from_user.id}")
                    await state.update_data(last_message_id=sent_message.message_id)
                    await state.set_state(ProfileStates.MainMenu)
                return

            user_data = {
                "telegram_id": str(message.from_user.id),
                "first_name": message.from_user.first_name,
                "last_name": message.from_user.last_name,
                "username": message.from_user.username,
                "phone": None,
                "birth_date": None
            }
            await state.update_data(user_data=user_data)

            keyboard = ReplyKeyboardMarkup(
                keyboard=[[KeyboardButton(text="Отправить контакт", request_contact=True)]],
                resize_keyboard=True,
                one_time_keyboard=True
            )
            sent_message = await send_message(
                bot, str(message.chat.id), "text",
                "Пожалуйста, отправьте ваш номер телефона, нажав на кнопку ниже: 📞",
                reply_markup=keyboard
            )
            if sent_message:
                await state.update_data(last_message_id=sent_message.message_id)
                await state.set_state(ProfileStates.RegisterAwaitingPhone)
    except Exception as e:
        logger.error(f"Ошибка входа в личный кабинет для {message.from_user.id}: {str(e)}")
        await handle_error(message, state, bot, "Ошибка. Попробуйте снова. 😔", "Ошибка входа в личный кабинет", e)

@profile_router.message(ProfileStates.RegisterAwaitingPhone, F.content_type == 'contact')
async def process_register_phone(message: Message, state: FSMContext, bot: Bot):
    """Обработка номера телефона из контакта."""
    logger.info(f"Пользователь {message.from_user.id} отправил контакт")
    try:
        phone = message.contact.phone_number
        if not phone.startswith("+"):
            phone = f"+{phone}"
        UserInput.validate_phone(phone)
        data = await state.get_data()
        user_data = data["user_data"]
        user_data["phone"] = phone
        await state.update_data(user_data=user_data)
        await show_user_data(message, state, bot)
    except ValidationError as e:
        logger.error(f"Ошибка валидации телефона для {message.from_user.id}: {str(e)}")
        keyboard = ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="Отправить контакт", request_contact=True)]],
            resize_keyboard=True,
            one_time_keyboard=True
        )
        sent_message = await send_message(
            bot, str(message.chat.id), "text",
            "Некорректный номер телефона. Введите номер, начиная с +7 (например, +79991234567): 📞",
            reply_markup=keyboard
        )
        if sent_message:
            await state.update_data(last_message_id=sent_message.message_id)
    except Exception as e:
        logger.error(f"Ошибка обработки телефона для {message.from_user.id}: {str(e)}")
        await handle_error(message, state, bot, "Ошибка. Попробуйте снова. 😔", "Ошибка обработки телефона", e)

async def show_user_data(message: Message, state: FSMContext, bot: Bot):
    """Показывает собранные данные и запрашивает подтверждение."""
    data = await state.get_data()
    user_data = data["user_data"]
    response = (
        "<b>Ваши данные:</b> 👤\n"
        f"Имя: {user_data['first_name']}\n"
        f"Фамилия: {user_data['last_name'] or 'Не указано'}\n"
        f"Телефон: {user_data['phone'] or 'Не указано'}\n"
        f"Имя пользователя: {user_data['username'] or 'Не указано'}\n"
        f"Дата рождения: {user_data['birth_date'] or 'Не указано'}\n"
        "\nДобавить эти данные в базу?"
    )
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Добавить ✅", callback_data="confirm_register")],
        [InlineKeyboardButton(text="Отмена 🚫", callback_data="cancel_register")]
    ])
    sent_message = await send_message(
        bot, str(message.chat.id), "text",
        response,
        reply_markup=keyboard
    )
    if sent_message:
        await state.update_data(last_message_id=sent_message.message_id)
        await state.set_state(ProfileStates.RegisterConfirm)

@profile_router.callback_query(ProfileStates.RegisterConfirm, F.data == "confirm_register")
async def confirm_register(callback: CallbackQuery, state: FSMContext, bot: Bot):
    """Подтверждение регистрации и сохранение данных."""
    logger.info(f"Пользователь {callback.from_user.id} подтвердил регистрацию")
    try:
        data = await state.get_data()
        user_data = data["user_data"]
        user_input = UserInput(
            first_name=user_data["first_name"],
            last_name=user_data["last_name"],
            phone=user_data["phone"]
        )
        with Session() as session:
            user = User(
                telegram_id=user_data["telegram_id"],
                first_name=user_input.first_name,
                last_name=user_input.last_name,
                phone=user_input.phone,
                username=user_data["username"],
                birth_date=user_data["birth_date"]
            )
            session.add(user)
            session.commit()
            logger.info(f"Пользователь {callback.from_user.id} зарегистрирован")
            response = (
                f"<b>Регистрация завершена</b> ✅\n"
                f"Имя: {user.first_name}\n"
                f"Фамилия: {user.last_name or 'Не указано'}\n"
                f"Телефон: {user.phone or 'Не указано'}\n"
                f"Имя пользователя: {user.username or 'Не указано'}\n"
                f"Дата рождения: {user.birth_date or 'Не указано'}\n"
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
        logger.error(f"Ошибка регистрации для {callback.from_user.id}: {str(e)}")
        await handle_error(callback, state, bot, "Ошибка регистрации. Попробуйте снова. 😔", "Ошибка регистрации", e)
        await callback.answer()

@profile_router.callback_query(ProfileStates.RegisterConfirm, F.data == "cancel_register")
async def cancel_register(callback: CallbackQuery, state: FSMContext, bot: Bot):
    """Отмена регистрации."""
    logger.info(f"Пользователь {callback.from_user.id} отменил регистрацию")
    sent_message = await send_message(
        bot, str(callback.message.chat.id), "text",
        "Регистрация отменена. Вернитесь в 'Личный кабинет' для повторной попытки. 👤",
        reply_markup=Keyboards.main_menu_kb()
    )
    if sent_message:
        await state.update_data(last_message_id=sent_message.message_id)
    await state.clear()
    await callback.answer()

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
    from utils.service_utils import process_user_input
    await process_user_input(
        message, state, bot,
        UserInput.validate_first_name, "first_name",
        "Введите вашу <b>фамилию</b> (или оставьте пустым, нажав Enter): 👤",
        "Имя слишком короткое или длинное (2–50 символов). Введите снова: 😔",
        ProfileStates.AwaitingLastName,
        PROFILE_PROGRESS_STEPS
    )

@profile_router.message(ProfileStates.AwaitingLastName, F.text)
async def process_last_name(message: Message, state: FSMContext, bot: Bot):
    """Обработка фамилии."""
    from utils.service_utils import process_user_input
    def validate_last_name_or_none(value: str):
        if value.strip() == "":
            return None
        return UserInput.validate_last_name(value)
    await process_user_input(
        message, state, bot,
        validate_last_name_or_none, "last_name",
        "Введите ваш номер телефона, начиная с <b>+7</b> (например, <b>+79991234567</b>), или оставьте пустым: 📞",
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
        validated_phone = None
        if phone:
            validated_phone = UserInput.validate_phone(phone)
        data = await state.get_data()
        user_input = UserInput(
            first_name=data.get("first_name", ""),
            last_name=data.get("last_name"),
            phone=validated_phone
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
                f"Фамилия: {user.last_name or 'Не указано'}\n"
                f"Телефон: {user.phone or 'Не указано'}\n"
                f"Имя пользователя: {user.username or 'Не указано'}\n"
                f"Дата рождения: {user.birth_date or 'Не указано'}\n"
            )
            try:
                photo_path = get_photo_path("profile_edit")
                sent_message = await send_message(
                    bot, str(message.chat.id), "photo",
                    response,
                    photo=photo_path,
                    reply_markup=Keyboards.profile_menu_kb()
                )
            except FileNotFoundError as e:
                logger.warning(f"Не удалось отправить фото profile_edit для {message.from_user.id}: {str(e)}")
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
                message="Некорректный номер телефона. Введите номер, начиная с +7 (например, +79991234567), или оставьте пустым: 📞"
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
            try:
                photo_path = get_photo_path("profile_list_auto")
                sent_message = await send_message(
                    bot, str(callback.message.chat.id), "photo",
                    response,
                    photo=photo_path,
                    reply_markup=Keyboards.auto_management_kb(autos)
                )
            except FileNotFoundError as e:
                logger.warning(f"Не удалось отправить фото profile_list_auto для {callback.from_user.id}: {str(e)}")
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
    from utils.service_utils import process_user_input
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
    from utils.service_utils import process_user_input
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

            session.query(Booking).filter(
                Booking.auto_id == auto_id,
                Booking.status.in_([BookingStatus.REJECTED, BookingStatus.CANCELLED])
            ).delete()

            session.delete(auto)
            session.commit()
            logger.info(f"Автомобиль {auto_id} удалён для пользователя {callback.from_user.id}")

            autos = session.query(Auto).filter_by(user_id=auto.user_id).all()
            if not autos:
                response = "У вас больше нет автомобилей. Добавьте новый: 🚗"
                sent_message = await send_message(
                    bot, str(callback.message.chat.id), "text",
                    response,
                    reply_markup=Keyboards.profile_menu_kb()
                )
                if sent_message:
                    await state.update_data(last_message_id=sent_message.message_id)
                    await state.set_state(ProfileStates.MainMenu)
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

@profile_router.callback_query(ProfileStates.ManagingAutos, F.data == "back_to_profile")
async def back_to_profile(callback: CallbackQuery, state: FSMContext, bot: Bot):
    """Возврат в меню личного кабинета из управления автомобилями."""
    logger.info(f"Пользователь {callback.from_user.id} вернулся в меню личного кабинета")
    try:
        with Session() as session:
            user = session.query(User).filter_by(telegram_id=str(callback.from_user.id)).first()
            response = (
                f"<b>Личный кабинет</b> 👤\n"
                f"Имя: {user.first_name}\n"
                f"Фамилия: {user.last_name or 'Не указано'}\n"
                f"Телефон: {user.phone or 'Не указано'}\n"
                f"Имя пользователя: {user.username or 'Не указано'}\n"
                f"Дата рождения: {user.birth_date or 'Не указано'}\n"
            )
            try:
                photo_path = get_photo_path("profile")
                sent_message = await send_message(
                    bot, str(callback.message.chat.id), "photo",
                    response,
                    photo=photo_path,
                    reply_markup=Keyboards.profile_menu_kb()
                )
            except FileNotFoundError as e:
                logger.warning(f"Не удалось отправить фото профиля для {callback.from_user.id}: {str(e)}")
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
        logger.error(f"Ошибка возврата в личный кабинет для {callback.from_user.id}: {str(e)}")
        await handle_error(callback, state, bot, "Ошибка. Попробуйте снова. 😔", "Ошибка возврата в личный кабинет", e)
        await callback.answer()

@profile_router.callback_query(ProfileStates.MainMenu, F.data == "back_to_profile")
async def back_to_profile_main_menu(callback: CallbackQuery, state: FSMContext, bot: Bot):
    """Возврат в меню личного кабинета из списка записей."""
    logger.info(f"Пользователь {callback.from_user.id} вернулся в меню личного кабинета из списка записей")
    try:
        with Session() as session:
            user = session.query(User).filter_by(telegram_id=str(callback.from_user.id)).first()
            response = (
                f"<b>Личный кабинет</b> 👤\n"
                f"Имя: {user.first_name}\n"
                f"Фамилия: {user.last_name or 'Не указано'}\n"
                f"Телефон: {user.phone or 'Не указано'}\n"
                f"Имя пользователя: {user.username or 'Не указано'}\n"
                f"Дата рождения: {user.birth_date or 'Не указано'}\n"
            )
            try:
                photo_path = get_photo_path("profile")
                sent_message = await send_message(
                    bot, str(callback.message.chat.id), "photo",
                    response,
                    photo=photo_path,
                    reply_markup=Keyboards.profile_menu_kb()
                )
            except FileNotFoundError as e:
                logger.warning(f"Не удалось отправить фото профиля для {callback.from_user.id}: {str(e)}")
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
        logger.error(f"Ошибка возврата в личный кабинет для {callback.from_user.id}: {str(e)}")
        await handle_error(callback, state, bot, "Ошибка. Попробуйте снова. 😔", "Ошибка возврата в личный кабинет", e)
        await callback.answer()

@profile_router.callback_query(ProfileStates.MainMenu, F.data == "my_bookings")
async def show_bookings(callback: CallbackQuery, state: FSMContext, bot: Bot):
    """Показ активных записей с возможностью просмотра и отмены."""
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
            response = "<b>Ваши активные записи</b> 📜\nВыберите запись для просмотра или отмены:"
            try:
                photo_path = get_photo_path("bookings")
                sent_message = await send_message(
                    bot, str(callback.message.chat.id), "photo",
                    response,
                    photo=photo_path,
                    reply_markup=Keyboards.bookings_kb(bookings)
                )
            except FileNotFoundError as e:
                logger.warning(f"Не удалось отправить фото bookings для {callback.from_user.id}: {str(e)}")
                sent_message = await send_message(
                    bot, str(callback.message.chat.id), "text",
                    response,
                    reply_markup=Keyboards.bookings_kb(bookings)
                )
            if sent_message:
                await state.update_data(last_message_id=sent_message.message_id)
                await state.set_state(ProfileStates.MainMenu)
            await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка получения записей для {callback.from_user.id}: {str(e)}")
        await handle_error(callback, state, bot, "Ошибка. Попробуйте снова. 😔", "Ошибка получения записей", e)
        await callback.answer()

@profile_router.callback_query(ProfileStates.ViewingBooking, F.data == "my_bookings")
async def back_to_bookings(callback: CallbackQuery, state: FSMContext, bot: Bot):
    """Возврат к списку активных записей из просмотра записи."""
    logger.info(f"Пользователь {callback.from_user.id} возвращается к списку записей")
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
            response = "<b>Ваши активные записи</b> 📜\nВыберите запись для просмотра или отмены:"
            try:
                photo_path = get_photo_path("bookings")
                sent_message = await send_message(
                    bot, str(callback.message.chat.id), "photo",
                    response,
                    photo=photo_path,
                    reply_markup=Keyboards.bookings_kb(bookings)
                )
            except FileNotFoundError as e:
                logger.warning(f"Не удалось отправить фото bookings для {callback.from_user.id}: {str(e)}")
                sent_message = await send_message(
                    bot, str(callback.message.chat.id), "text",
                    response,
                    reply_markup=Keyboards.bookings_kb(bookings)
                )
            if sent_message:
                await state.update_data(last_message_id=sent_message.message_id)
                await state.set_state(ProfileStates.MainMenu)
            await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка возврата к списку записей для {callback.from_user.id}: {str(e)}")
        await handle_error(callback, state, bot, "Ошибка. Попробуйте снова. 😔", "Ошибка возврата к списку записей", e)
        await callback.answer()

@profile_router.callback_query(F.data.startswith("view_booking_"))
async def view_booking(callback: CallbackQuery, state: FSMContext, bot: Bot):
    """Показывает детали выбранной записи."""
    logger.info(f"Пользователь {callback.from_user.id} просматривает запись")
    booking_id = int(callback.data.replace("view_booking_", ""))
    try:
        with Session() as session:
            booking = session.query(Booking).get(booking_id)
            if not booking:
                sent_message = await send_message(
                    bot, str(callback.message.chat.id), "text",
                    "Запись не найдена. 📝",
                    reply_markup=Keyboards.profile_menu_kb()
                )
                if sent_message:
                    await state.update_data(last_message_id=sent_message.message_id)
                await state.set_state(ProfileStates.MainMenu)
                await callback.answer()
                return
            if str(callback.from_user.id) != str(booking.user.telegram_id):
                logger.warning(f"Несанкционированный доступ: user_id={callback.from_user.id} != telegram_id={booking.user.telegram_id}")
                await callback.answer("Доступ только для владельца записи. 🔒")
                return
            auto = session.query(Auto).get(booking.auto_id)
            status_map = {
                BookingStatus.PENDING: "Ожидает подтверждения ⏳",
                BookingStatus.CONFIRMED: "Подтверждено ✅",
                BookingStatus.REJECTED: "Отклонено ❌",
                BookingStatus.CANCELLED: "Отменено 🚫"
            }
            response = (
                f"<b>Запись #{booking.id}</b> 📋\n"
                f"<b>Услуга:</b> {booking.service_name} 🔧\n"
                f"<b>Дата:</b> {booking.date.strftime('%d.%m.%Y')} 📅\n"
                f"<b>Время:</b> {booking.time.strftime('%H:%M')} ⏰\n"
                f"<b>Авто:</b> {auto.brand}, {auto.year}, {auto.license_plate} 🚗\n"
                f"<b>Статус:</b> {status_map[booking.status]}\n"
            )
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="Назад ⬅", callback_data="my_bookings")]
            ])
            if booking.status in [BookingStatus.PENDING, BookingStatus.CONFIRMED]:
                keyboard.inline_keyboard.insert(0, [InlineKeyboardButton(text="Отменить ❌", callback_data=f"cancel_booking_{booking.id}")])
            try:
                photo_path = get_photo_path("booking_details")
                sent_message = await send_message(
                    bot, str(callback.message.chat.id), "photo",
                    response,
                    photo=photo_path,
                    reply_markup=keyboard
                )
            except FileNotFoundError as e:
                logger.warning(f"Не удалось отправить фото booking_details для {callback.from_user.id}: {str(e)}")
                sent_message = await send_message(
                    bot, str(callback.message.chat.id), "text",
                    response,
                    reply_markup=keyboard
                )
            if sent_message:
                await state.update_data(last_message_id=sent_message.message_id)
                await state.set_state(ProfileStates.ViewingBooking)
            await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка просмотра записи {booking_id} для {callback.from_user.id}: {str(e)}")
        await handle_error(callback,
                           state,
                           bot,
                           "Ошибка. Попробуйте снова. 😔",
                           "Ошибка просмотра записи", e
                           )
        await callback.answer()

@profile_router.callback_query(ProfileStates.MainMenu, F.data == "booking_history")
async def show_booking_history(callback: CallbackQuery, state: FSMContext, bot: Bot):
    """Показ истории записей с пагинацией."""
    logger.info(f"Пользователь {callback.from_user.id} запросил историю записей")
    try:
        with Session() as session:
            user = session.query(User).filter_by(telegram_id=str(callback.from_user.id)).first()
            bookings = session.query(Booking).filter(
                Booking.user_id == user.id,
                Booking.status.in_([BookingStatus.REJECTED, BookingStatus.CANCELLED, BookingStatus.COMPLETED])
            ).order_by(Booking.date.desc()).all()
            if not bookings:
                sent_message = await send_message(
                    bot, str(callback.message.chat.id), "photo",
                    "📜 У вас нет завершённых, отменённых или выполненных записей.",
                    photo=get_photo_path("no_history"),
                    reply_markup=Keyboards.profile_menu_kb()
                )
                if sent_message:
                    await state.update_data(last_message_id=sent_message.message_id)
                await state.set_state(ProfileStates.MainMenu)
                await callback.answer()
                return
            response = "📜 <b>История ваших записей</b>\nВыберите запись для просмотра:"
            try:
                sent_message = await send_message(
                    bot, str(callback.message.chat.id), "photo",
                    response,
                    photo=get_photo_path("booking_history"),
                    reply_markup=Keyboards.bookings_history_kb(bookings, page=0)
                )
            except FileNotFoundError as e:
                logger.warning(f"Не удалось отправить фото booking_history: {str(e)}")
                sent_message = await send_message(
                    bot, str(callback.message.chat.id), "text",
                    response,
                    reply_markup=Keyboards.bookings_history_kb(bookings, page=0)
                )
            if sent_message:
                await state.update_data(last_message_id=sent_message.message_id)
                await state.set_state(ProfileStates.MainMenu)
            await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка получения истории записей для {callback.from_user.id}: {str(e)}")
        await handle_error(callback,
                           state,
                           bot,
                           "Ошибка. Попробуйте снова. 😔",
                           "Ошибка получения истории записей", e
                           )
        await callback.answer()


@profile_router.callback_query(F.data.startswith("history_page_"))
async def show_booking_history_page(callback: CallbackQuery, state: FSMContext, bot: Bot):
    """Показ истории записей для выбранной страницы."""
    page = int(callback.data.replace("history_page_", ""))
    logger.info(f"Пользователь {callback.from_user.id} запросил страницу {page} истории записей")
    try:
        with Session() as session:
            user = session.query(User).filter_by(telegram_id=str(callback.from_user.id)).first()
            bookings = session.query(Booking).filter(
                Booking.user_id == user.id,
                Booking.status.in_([BookingStatus.REJECTED, BookingStatus.CANCELLED, BookingStatus.COMPLETED])
            ).order_by(Booking.date.desc()).all()
            response = "📜 <b>История ваших записей</b>\nВыберите запись для просмотра:"
            try:
                sent_message = await send_message(
                    bot, str(callback.message.chat.id), "photo",
                    response,
                    photo=get_photo_path("booking_history"),
                    reply_markup=Keyboards.bookings_history_kb(bookings, page=page)
                )
            except FileNotFoundError as e:
                logger.warning(f"Не удалось отправить фото booking_history: {str(e)}")
                sent_message = await send_message(
                    bot, str(callback.message.chat.id), "text",
                    response,
                    reply_markup=Keyboards.bookings_history_kb(bookings, page=page)
                )
            if sent_message:
                await state.update_data(last_message_id=sent_message.message_id)
                await state.set_state(ProfileStates.MainMenu)
            await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка получения страницы {page} истории записей для {callback.from_user.id}: {str(e)}")
        await handle_error(callback, state, bot, "Ошибка. Попробуйте снова. 😔", "Ошибка получения страницы истории", e)
        await callback.answer()


@profile_router.callback_query(F.data.startswith("delete_booking_"))
async def delete_booking(callback: CallbackQuery, state: FSMContext, bot: Bot):
    """Удаление записи из истории."""
    booking_id = int(callback.data.replace("delete_booking_", ""))
    logger.info(f"Пользователь {callback.from_user.id} запросил удаление записи #{booking_id}")
    try:
        with Session() as session:
            booking = session.query(Booking).get(booking_id)
            if not booking:
                await handle_error(
                    callback, state, bot,
                    "Запись не найдена. 📝", f"Запись #{booking_id} не найдена", Exception("Booking not found")
                )
                await callback.answer()
                return
            if str(callback.from_user.id) != str(booking.user.telegram_id):
                logger.warning(
                    f"Несанкционированный доступ: user_id={callback.from_user.id} != telegram_id={booking.user.telegram_id}")
                await callback.answer("Доступ только для владельца записи. 🔒")
                return
            if booking.status not in [BookingStatus.REJECTED, BookingStatus.CANCELLED]:
                await callback.answer("Удалить можно только отменённые или отклонённые записи.")
                return
            session.delete(booking)
            session.commit()
            logger.info(f"Запись #{booking_id} удалена пользователем {callback.from_user.id}")

            # Показать обновлённую историю
            bookings = session.query(Booking).filter(
                Booking.user_id == booking.user_id,
                Booking.status.in_([BookingStatus.REJECTED, BookingStatus.CANCELLED, BookingStatus.COMPLETED])
            ).order_by(Booking.date.desc()).all()
            response = "📜 <b>История ваших записей</b>\nВыберите запись для просмотра:"
            try:
                sent_message = await send_message(
                    bot, str(callback.message.chat.id), "photo",
                    response,
                    photo=get_photo_path("booking_history"),
                    reply_markup=Keyboards.bookings_history_kb(bookings, page=0)
                )
            except FileNotFoundError as e:
                logger.warning(f"Не удалось отправить фото booking_history: {str(e)}")
                sent_message = await send_message(
                    bot, str(callback.message.chat.id), "text",
                    response,
                    reply_markup=Keyboards.bookings_history_kb(bookings, page=0)
                )
            if sent_message:
                await state.update_data(last_message_id=sent_message.message_id)
                await state.set_state(ProfileStates.MainMenu)
            await callback.answer("Запись удалена 🗑")
    except Exception as e:
        logger.error(f"Ошибка удаления записи #{booking_id} для {callback.from_user.id}: {str(e)}")
        await handle_error(callback, state, bot, "Ошибка. Попробуйте снова. 😔", f"Ошибка удаления записи #{booking_id}",
                           e)
        await callback.answer()


@profile_router.callback_query(F.data.startswith("leave_review_"))
async def start_leave_review(callback: CallbackQuery, state: FSMContext, bot: Bot):
    booking_id = int(callback.data.replace("leave_review_", ""))
    logger.info(f"Пользователь {callback.from_user.id} начал оставление отзыва для записи #{booking_id}")
    try:
        with Session() as session:
            booking = session.query(Booking).get(booking_id)
            if not booking:
                await handle_error(
                    callback, state, bot,
                    "Запись не найдена. 📝", f"Запись #{booking_id} не найдена", Exception("Booking not found")
                )
                await callback.answer()
                return
            if str(callback.from_user.id) != str(booking.user.telegram_id):
                logger.warning(
                    f"Несанкционированный доступ: user_id={callback.from_user.id} != telegram_id={booking.user.telegram_id}")
                await callback.answer("Доступ только для владельца записи. 🔒")
                return
            if booking.status != BookingStatus.COMPLETED or booking.review:
                await callback.answer("Отзыв можно оставить только для выполненных записей без отзыва.")
                return
            await state.update_data(booking_id=booking_id, review_photos=[], review_video=None)
            sent_message = await send_message(
                bot, str(callback.message.chat.id), "photo",
                (await get_progress_bar(ProfileStates.AwaitingReviewRating, PROFILE_PROGRESS_STEPS, style="emoji")).format(
                    message="⭐ Выберите рейтинг (1–5):"
                ),
                photo=get_photo_path("leave_review"),
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text=str(i), callback_data=f"rating_{i}") for i in range(1, 6)],
                    [InlineKeyboardButton(text="Отмена 🚫", callback_data="cancel_review")]
                ])
            )
            if sent_message:
                await state.update_data(last_message_id=sent_message.message_id)
            await state.set_state(ProfileStates.AwaitingReviewRating)
            await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка начала отзыва для записи #{booking_id}: {str(e)}")
        await handle_error(callback, state, bot, "Ошибка. Попробуйте снова. 😔", f"Ошибка начала отзыва #{booking_id}", e)
        await callback.answer()

@profile_router.callback_query(ProfileStates.AwaitingReviewRating, F.data.startswith("rating_"))
async def process_review_rating(callback: CallbackQuery, state: FSMContext, bot: Bot):
    rating = int(callback.data.replace("rating_", ""))
    logger.info(f"Пользователь {callback.from_user.id} выбрал рейтинг {rating}")
    try:
        if not 1 <= rating <= 5:
            await callback.answer("Некорректный рейтинг.")
            return
        await state.update_data(review_rating=rating)
        sent_message = await send_message(
            bot, str(callback.message.chat.id), "photo",
            (await get_progress_bar(ProfileStates.AwaitingReviewText, PROFILE_PROGRESS_STEPS, style="emoji")).format(
                message="⭐ Напишите ваш отзыв о выполненной услуге:"
            ),
            photo=get_photo_path("leave_review"),
            reply_markup=Keyboards.cancel_kb()
        )
        if sent_message:
            await state.update_data(last_message_id=sent_message.message_id)
        await state.set_state(ProfileStates.AwaitingReviewText)
        await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка обработки рейтинга для {callback.from_user.id}: {str(e)}")
        await handle_error(callback, state, bot, "Ошибка. Попробуйте снова. 😔", "Ошибка обработки рейтинга", e)
        await callback.answer()

@profile_router.message(ProfileStates.AwaitingReviewText, F.text)
async def process_review_text(message: Message, state: FSMContext, bot: Bot):
    logger.info(f"Пользователь {message.from_user.id} ввёл текст отзыва")
    try:
        text = message.text.strip()
        if len(text) < 10 or len(text) > 500:
            sent_message = await send_message(
                bot, str(message.chat.id), "photo",
                (await get_progress_bar(ProfileStates.AwaitingReviewText, PROFILE_PROGRESS_STEPS, style="emoji")).format(
                    message="Отзыв должен быть от 10 до 500 символов. Введите снова: ⭐"
                ),
                photo=get_photo_path("leave_review"),
                reply_markup=Keyboards.cancel_kb()
            )
            if sent_message:
                await state.update_data(last_message_id=sent_message.message_id)
            return
        await state.update_data(review_text=text)
        sent_message = await send_message(
            bot, str(message.chat.id), "photo",
            (await get_progress_bar(ProfileStates.AwaitingReviewPhotos, PROFILE_PROGRESS_STEPS, style="emoji")).format(
                message="📷 Загрузите до 3 фотографий (по одной, до 10 МБ) или нажмите 'Далее':"
            ),
            photo=get_photo_path("upload_photos"),
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="➡ Далее", callback_data="review_photos_done")]
            ])
        )
        if sent_message:
            await state.update_data(last_message_id=sent_message.message_id)
            await state.set_state(ProfileStates.AwaitingReviewPhotos)
    except Exception as e:
        logger.error(f"Ошибка обработки текста отзыва для {message.from_user.id}: {str(e)}")
        await handle_error(message, state, bot, "Ошибка. Попробуйте снова. 😔", "Ошибка обработки текста отзыва", e)

@profile_router.message(ProfileStates.AwaitingReviewPhotos, F.photo)
async def process_review_photo(message: Message, state: FSMContext, bot: Bot):
    logger.info(f"Пользователь {message.from_user.id} загрузил фото для отзыва")
    try:
        data = await state.get_data()
        photos = data.get("review_photos", [])
        if len(photos) >= 3:
            await message.answer("Максимум 3 фотографии. Нажмите 'Далее'.",
                                 reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                                     [InlineKeyboardButton(text="➡ Далее", callback_data="review_photos_done")]
                                 ]))
            return
        photo = message.photo[-1]
        if photo.file_size > 10 * 1024 * 1024:  # 10 МБ
            await message.answer("Фото слишком большое (макс. 10 МБ). Загрузите другое или нажмите 'Далее'.",
                                 reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                                     [InlineKeyboardButton(text="➡ Далее", callback_data="review_photos_done")]
                                 ]))
            return
        file_info = await bot.get_file(photo.file_id)
        file_path = f"{UPLOAD_USER_DIR}/review_{message.from_user.id}_{len(photos) + 1}_{photo.file_id}.jpg"
        await bot.download_file(file_info.file_path, file_path)
        photos.append(file_path)
        await state.update_data(review_photos=photos)
        remaining = 3 - len(photos)
        sent_message = await send_message(
            bot, str(message.chat.id), "photo",
            (await get_progress_bar(ProfileStates.AwaitingReviewPhotos, PROFILE_PROGRESS_STEPS, style="emoji")).format(
                message=f"📷 Фото загружено! Осталось загрузить до {remaining} фото или нажмите 'Далее':"
            ),
            photo=get_photo_path("upload_photos"),
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="➡ Далее", callback_data="review_photos_done")]
            ])
        )
        if sent_message:
            await state.update_data(last_message_id=sent_message.message_id)
    except Exception as e:
        logger.error(f"Ошибка загрузки фото отзыва для {message.from_user.id}: {str(e)}")
        await handle_error(message, state, bot, "Ошибка загрузки фото. Попробуйте снова. 😔",
                           "Ошибка загрузки фото отзыва", e)

@profile_router.callback_query(ProfileStates.AwaitingReviewPhotos, F.data == "review_photos_done")
async def proceed_to_video(callback: CallbackQuery, state: FSMContext, bot: Bot):
    logger.info(f"Пользователь {callback.from_user.id} завершил загрузку фото для отзыва")
    try:
        sent_message = await send_message(
            bot, str(callback.message.chat.id), "photo",
            (await get_progress_bar(ProfileStates.AwaitingReviewVideo, PROFILE_PROGRESS_STEPS, style="emoji")).format(
                message="🎥 Загрузите видео (до 50 МБ) или нажмите 'Готово':"
            ),
            photo=get_photo_path("upload_video"),
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="✅ Готово", callback_data="review_video_done")]
            ])
        )
        if sent_message:
            await state.update_data(last_message_id=sent_message.message_id)
            await state.set_state(ProfileStates.AwaitingReviewVideo)
        await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка перехода к загрузке видео для {callback.from_user.id}: {str(e)}")
        await handle_error(callback, state, bot, "Ошибка. Попробуйте снова. 😔", "Ошибка перехода к видео", e)
        await callback.answer()

@profile_router.message(ProfileStates.AwaitingReviewVideo, F.video)
async def process_review_video(message: Message, state: FSMContext, bot: Bot):
    logger.info(f"Пользователь {message.from_user.id} загрузил видео для отзыва")
    try:
        data = await state.get_data()
        if data.get("review_video"):
            await message.answer("Можно загрузить только одно видео. Нажмите 'Готово'.",
                                 reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                                     [InlineKeyboardButton(text="✅ Готово", callback_data="review_video_done")]
                                 ]))
            return
        video = message.video
        if video.file_size > 50 * 1024 * 1024:  # 50 МБ
            await message.answer("Видео слишком большое (макс. 50 МБ). Загрузите другое или нажмите 'Готово'.",
                                 reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                                     [InlineKeyboardButton(text="✅ Готово", callback_data="review_video_done")]
                                 ]))
            return
        file_info = await bot.get_file(video.file_id)
        file_path = f"{UPLOAD_USER_DIR}/review_{message.from_user.id}_video_{video.file_id}.mp4"
        await bot.download_file(file_info.file_path, file_path)
        await state.update_data(review_video=file_path)
        sent_message = await send_message(
            bot, str(message.chat.id), "photo",
            (await get_progress_bar(ProfileStates.AwaitingReviewVideo, PROFILE_PROGRESS_STEPS, style="emoji")).format(
                message="🎥 Видео загружено! Нажмите 'Готово':"
            ),
            photo=get_photo_path("upload_video"),
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="✅ Готово", callback_data="review_video_done")]
            ])
        )
        if sent_message:
            await state.update_data(last_message_id=sent_message.message_id)
    except Exception as e:
        logger.error(f"Ошибка загрузки видео отзыва для {message.from_user.id}: {str(e)}")
        await handle_error(message, state, bot, "Ошибка загрузки видео. Попробуйте снова. 😔",
                           "Ошибка загрузки видео отзыва", e)

@profile_router.callback_query(ProfileStates.AwaitingReviewVideo, F.data == "review_video_done")
async def confirm_review(callback: CallbackQuery, state: FSMContext, bot: Bot):
    logger.info(f"Пользователь {callback.from_user.id} завершил загрузку медиа для отзыва")
    try:
        data = await state.get_data()
        review_text = data.get("review_text")
        review_rating = data.get("review_rating")
        review_photos = data.get("review_photos", [])
        review_video = data.get("review_video")
        booking_id = data.get("booking_id")
        response = (
            f"⭐ <b>Ваш отзыв:</b>\n"
            f"Рейтинг: {'⭐' * review_rating}\n"
            f"Текст: {review_text}\n\n"
            f"📷 Загружено фотографий: {len(review_photos)}\n"
            f"🎥 Загружено видео: {'1' if review_video else '0'}\n"
            "Сохранить отзыв?"
        )
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Сохранить", callback_data="save_review")],
            [InlineKeyboardButton(text="📸 Предпросмотр медиа", callback_data="preview_media")],
            [InlineKeyboardButton(text="🚫 Отмена", callback_data="cancel_review")]
        ])
        sent_message = await send_message(
            bot, str(callback.message.chat.id), "photo",
            response,
            photo=get_photo_path("confirm_review"),
            reply_markup=keyboard
        )
        if sent_message:
            await state.update_data(last_message_id=sent_message.message_id)
            await state.set_state(ProfileStates.ConfirmReview)
        await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка подтверждения отзыва для {callback.from_user.id}: {str(e)}")
        await handle_error(callback, state, bot, "Ошибка. Попробуйте снова. 😔", "Ошибка подтверждения отзыва", e)
        await callback.answer()

@profile_router.callback_query(ProfileStates.ConfirmReview, F.data == "preview_media")
async def preview_review_media(callback: CallbackQuery, state: FSMContext, bot: Bot):
    logger.info(f"Пользователь {callback.from_user.id} запросил предпросмотр медиа")
    try:
        data = await state.get_data()
        review_photos = data.get("review_photos", [])
        review_video = data.get("review_video")
        if not review_photos and not review_video:
            await callback.answer("Нет медиа для предпросмотра.")
            return
        for photo in review_photos:
            await send_message(bot, str(callback.message.chat.id), "photo", photo=photo)
        if review_video:
            await send_message(bot, str(callback.message.chat.id), "video", video=review_video)
        await callback.answer("Медиа отправлены для предпросмотра.")
    except Exception as e:
        logger.error(f"Ошибка предпросмотра медиа для {callback.from_user.id}: {str(e)}")
        await handle_error(callback, state, bot, "Ошибка предпросмотра. 😔", "Ошибка предпросмотра медиа", e)
        await callback.answer()

@profile_router.callback_query(ProfileStates.ConfirmReview, F.data == "save_review")
async def save_review(callback: CallbackQuery, state: FSMContext, bot: Bot):
    logger.info(f"Пользователь {callback.from_user.id} сохраняет отзыв")
    try:
        data = await state.get_data()
        review_text = data.get("review_text")
        review_rating = data.get("review_rating")
        review_photos = data.get("review_photos", [])
        review_video = data.get("review_video")
        booking_id = data.get("booking_id")
        with Session() as session:
            review = Review(
                user_id=session.query(User).filter_by(telegram_id=str(callback.from_user.id)).first().id,
                booking_id=booking_id,
                text=review_text,
                rating=review_rating,
                photo1=review_photos[0] if len(review_photos) > 0 else None,
                photo2=review_photos[1] if len(review_photos) > 1 else None,
                photo3=review_photos[2] if len(review_photos) > 2 else None,
                video=review_video
            )
            session.add(review)
            session.commit()
            logger.info(f"Отзыв сохранён для записи #{booking_id}")
            response = "⭐ Ваш отзыв успешно сохранён! Спасибо за обратную связь."
            try:
                sent_message = await send_message(
                    bot, str(callback.message.chat.id), "photo",
                    response,
                    photo=get_photo_path("review_saved"),
                    reply_markup=Keyboards.profile_menu_kb()
                )
            except FileNotFoundError as e:
                logger.warning(f"Не удалось отправить фото review_saved: {str(e)}")
                sent_message = await send_message(
                    bot, str(callback.message.chat.id), "text",
                    response,
                    reply_markup=Keyboards.profile_menu_kb()
                )
            if sent_message:
                await state.update_data(last_message_id=sent_message.message_id)
                await state.set_state(ProfileStates.MainMenu)
            await callback.answer()

            booking = session.query(Booking).get(booking_id)
            user = session.query(User).get(booking.user_id)
            auto = session.query(Auto).get(booking.auto_id)
            await send_booking_notification(
                bot, ADMIN_ID, booking, user, auto,
                f"Новый отзыв для записи #{booking_id}:\n"
                f"Рейтинг: {'⭐' * review_rating}\n"
                f"{review_text}\n"
                f"Фотографий: {len(review_photos)}\n"
                f"Видео: {'1' if review_video else '0'}"
            )
    except Exception as e:
        logger.error(f"Ошибка сохранения отзыва для {callback.from_user.id}: {str(e)}")
        await handle_error(callback, state, bot, "Ошибка. Попробуйте снова. 😔", "Ошибка сохранения отзыва", e)
        await callback.answer()

@profile_router.callback_query(ProfileStates.ConfirmReview, F.data == "cancel_review")
async def cancel_review(callback: CallbackQuery, state: FSMContext, bot: Bot):
    logger.info(f"Пользователь {callback.from_user.id} отменил отзыв")
    try:
        data = await state.get_data()
        review_photos = data.get("review_photos", [])
        review_video = data.get("review_video")
        for photo in review_photos:
            if os.path.exists(photo):
                os.remove(photo)
        if review_video and os.path.exists(review_video):
            os.remove(review_video)
        response = "📜 <b>История ваших записей</b>\nВыберите запись для просмотра:"
        with Session() as session:
            user = session.query(User).filter_by(telegram_id=str(callback.from_user.id)).first()
            bookings = session.query(Booking).filter(
                Booking.user_id == user.id,
                Booking.status.in_([BookingStatus.REJECTED, BookingStatus.CANCELLED, BookingStatus.COMPLETED])
            ).order_by(Booking.date.desc()).all()
            try:
                sent_message = await send_message(
                    bot, str(callback.message.chat.id), "photo",
                    response,
                    photo=get_photo_path("booking_history"),
                    reply_markup=Keyboards.bookings_history_kb(bookings, page=0)
                )
            except FileNotFoundError as e:
                logger.warning(f"Не удалось отправить фото booking_history: {str(e)}")
                sent_message = await send_message(
                    bot, str(callback.message.chat.id), "text",
                    response,
                    reply_markup=Keyboards.bookings_history_kb(bookings, page=0)
                )
            if sent_message:
                await state.update_data(last_message_id=sent_message.message_id)
                await state.set_state(ProfileStates.MainMenu)
            await callback.answer("Отзыв отменён.")
    except Exception as e:
        logger.error(f"Ошибка отмены отзыва для {callback.from_user.id}: {str(e)}")
        await handle_error(callback, state, bot, "Ошибка. Попробуйте снова. 😔", "Ошибка отмены отзыва", e)
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
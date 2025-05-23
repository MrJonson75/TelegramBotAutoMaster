from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery, FSInputFile
from config import get_photo_path, ADMIN_ID
from database import Session, User, Auto, Booking, BookingStatus
from keyboards.main_kb import Keyboards
from datetime import datetime
from utils import setup_logger, delete_previous_message, AutoInput
from pydantic import ValidationError

logger = setup_logger(__name__)

repair_booking_router = Router()

class RepairBookingStates(StatesGroup):
    AwaitingAuto = State()
    AwaitingDescription = State()
    AwaitingPhotos = State()
    AwaitingDate = State()
    AwaitingTime = State()
    AwaitingAutoBrand = State()
    AwaitingAutoYear = State()
    AwaitingAutoVin = State()
    AwaitingAutoLicensePlate = State()
    AwaitingAddAnotherAuto = State()

@repair_booking_router.message(F.text == "Запись на ремонт")
async def start_repair_booking(message: Message, state: FSMContext, bot):
    """Начинает процесс записи на ремонт."""
    logger.info(f"User {message.from_user.id} started repair booking")
    try:
        with Session() as session:
            user = session.query(User).filter_by(telegram_id=str(message.from_user.id)).first()
            if not user:
                await delete_previous_message(bot, message.chat.id, (await state.get_data()).get("last_message_id"))
                sent_message = await message.answer("Вы не зарегистрированы. Пожалуйста, начните с записи на ТО.",
                                     reply_markup=Keyboards.main_menu_kb())
                await state.update_data(last_message_id=sent_message.message_id)
                return
            autos = session.query(Auto).filter_by(user_id=user.id).all()
            if not autos:
                response = "У вас нет зарегистрированных автомобилей. Добавьте авто."
                if len(response) > 1024:
                    logger.warning(f"Подпись слишком длинная ({len(response)} символов), отправляем без фото")
                    await delete_previous_message(bot, message.chat.id, (await state.get_data()).get("last_message_id"))
                    sent_message = await message.answer(response, reply_markup=Keyboards.auto_selection_kb(autos))
                    await state.update_data(last_message_id=sent_message.message_id)
                    await state.set_state(RepairBookingStates.AwaitingAuto)
                    return
                try:
                    photo_path = get_photo_path("booking_repair")
                    await delete_previous_message(bot, message.chat.id, (await state.get_data()).get("last_message_id"))
                    sent_message = await message.answer_photo(
                        photo=FSInputFile(photo_path),
                        caption=response,
                        reply_markup=Keyboards.auto_selection_kb(autos)
                    )
                    await state.update_data(last_message_id=sent_message.message_id)
                except (FileNotFoundError, ValueError) as e:
                    logger.error(f"Ошибка загрузки фото для начала записи на ремонт: {str(e)}")
                    await delete_previous_message(bot, message.chat.id, (await state.get_data()).get("last_message_id"))
                    sent_message = await message.answer(response, reply_markup=Keyboards.auto_selection_kb(autos))
                    await state.update_data(last_message_id=sent_message.message_id)
                await state.set_state(RepairBookingStates.AwaitingAuto)
                return
            response = "Выберите автомобиль для ремонта:"
            if len(response) > 1024:
                logger.warning(f"Подпись слишком длинная ({len(response)} символов), отправляем без фото")
                await delete_previous_message(bot, message.chat.id, (await state.get_data()).get("last_message_id"))
                sent_message = await message.answer(response, reply_markup=Keyboards.auto_selection_kb(autos))
                await state.update_data(last_message_id=sent_message.message_id)
                await state.set_state(RepairBookingStates.AwaitingAuto)
                return
            try:
                photo_path = get_photo_path("booking_repair")
                await delete_previous_message(bot, message.chat.id, (await state.get_data()).get("last_message_id"))
                sent_message = await message.answer_photo(
                    photo=FSInputFile(photo_path),
                    caption=response,
                    reply_markup=Keyboards.auto_selection_kb(autos)
                )
                await state.update_data(last_message_id=sent_message.message_id)
            except (FileNotFoundError, ValueError) as e:
                logger.error(f"Ошибка загрузки фото для начала записи на ремонт: {str(e)}")
                await delete_previous_message(bot, message.chat.id, (await state.get_data()).get("last_message_id"))
                sent_message = await message.answer(response, reply_markup=Keyboards.auto_selection_kb(autos))
                await state.update_data(last_message_id=sent_message.message_id)
            await state.set_state(RepairBookingStates.AwaitingAuto)
    except Exception as e:
        logger.error(f"Ошибка начала записи на ремонт: {str(e)}")
        await delete_previous_message(bot, message.chat.id, (await state.get_data()).get("last_message_id"))
        sent_message = await message.answer("Ошибка. Попробуйте снова.", reply_markup=Keyboards.main_menu_kb())
        await state.update_data(last_message_id=sent_message.message_id)
        await state.clear()

@repair_booking_router.callback_query(RepairBookingStates.AwaitingAuto, F.data == "add_new_auto")
async def add_new_auto(callback: CallbackQuery, state: FSMContext, bot):
    """Обрабатывает выбор добавления нового автомобиля."""
    logger.info(f"User {callback.from_user.id} requested to add a new auto")
    try:
        await delete_previous_message(bot, callback.message.chat.id, (await state.get_data()).get("last_message_id"))
        sent_message = await callback.message.answer("Введите марку автомобиля:")
        await state.update_data(last_message_id=sent_message.message_id)
        await state.set_state(RepairBookingStates.AwaitingAutoBrand)
        await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка обработки запроса на добавление автомобиля: {str(e)}")
        await delete_previous_message(bot, callback.message.chat.id, (await state.get_data()).get("last_message_id"))
        sent_message = await callback.message.answer("Ошибка. Попробуйте снова.", reply_markup=Keyboards.main_menu_kb())
        await state.update_data(last_message_id=sent_message.message_id)
        await state.clear()
        await callback.answer()

@repair_booking_router.message(RepairBookingStates.AwaitingAutoBrand, F.text)
async def process_auto_brand(message: Message, state: FSMContext, bot):
    """Обрабатывает ввод марки автомобиля."""
    try:
        brand = message.text.strip()
        AutoInput.validate_brand(brand)
        await state.update_data(brand=brand)
        await delete_previous_message(bot, message.chat.id, (await state.get_data()).get("last_message_id"))
        sent_message = await message.answer("Введите год выпуска автомобиля (например, 2020):")
        await state.update_data(last_message_id=sent_message.message_id)
        await state.set_state(RepairBookingStates.AwaitingAutoYear)
    except ValidationError as e:
        logger.warning(f"Validation error for brand: {e}, input: {brand}")
        await delete_previous_message(bot, message.chat.id, (await state.get_data()).get("last_message_id"))
        sent_message = await message.answer("Марка слишком короткая или длинная (2–50 символов). Введите снова:")
        await state.update_data(last_message_id=sent_message.message_id)

@repair_booking_router.message(RepairBookingStates.AwaitingAutoYear, F.text)
async def process_auto_year(message: Message, state: FSMContext, bot):
    """Обрабатывает ввод года выпуска автомобиля."""
    try:
        year = int(message.text.strip())
        AutoInput.validate_year(year)
        await state.update_data(year=year)
        await delete_previous_message(bot, message.chat.id, (await state.get_data()).get("last_message_id"))
        sent_message = await message.answer("Введите VIN-номер автомобиля (17 символов):")
        await state.update_data(last_message_id=sent_message.message_id)
        await state.set_state(RepairBookingStates.AwaitingAutoVin)
    except (ValidationError, ValueError) as e:
        logger.warning(f"Validation error for year: {e}, input: {message.text}")
        await delete_previous_message(bot, message.chat.id, (await state.get_data()).get("last_message_id"))
        sent_message = await message.answer(f"Некорректный год (1900–{datetime.today().year}). Введите снова:")
        await state.update_data(last_message_id=sent_message.message_id)

@repair_booking_router.message(RepairBookingStates.AwaitingAutoVin, F.text)
async def process_auto_vin(message: Message, state: FSMContext, bot):
    """Обрабатывает ввод VIN-номера автомобиля."""
    try:
        vin = message.text.strip()
        AutoInput.validate_vin(vin)
        await state.update_data(vin=vin)
        await delete_previous_message(bot, message.chat.id, (await state.get_data()).get("last_message_id"))
        sent_message = await message.answer("Введите государственный номер автомобиля:")
        await state.update_data(last_message_id=sent_message.message_id)
        await state.set_state(RepairBookingStates.AwaitingAutoLicensePlate)
    except ValidationError as e:
        logger.warning(f"Validation error for vin: {e}, input: {vin}")
        await delete_previous_message(bot, message.chat.id, (await state.get_data()).get("last_message_id"))
        sent_message = await message.answer("Некорректный VIN (17 букв/цифр). Введите снова:")
        await state.update_data(last_message_id=sent_message.message_id)

@repair_booking_router.message(RepairBookingStates.AwaitingAutoLicensePlate, F.text)
async def process_auto_license_plate(message: Message, state: FSMContext, bot):
    """Обрабатывает ввод госномера автомобиля."""
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
                if not user:
                    await delete_previous_message(bot, message.chat.id, (await state.get_data()).get("last_message_id"))
                    sent_message = await message.answer(
                        "Вы не зарегистрированы. Начните с записи на ТО.",
                        reply_markup=Keyboards.main_menu_kb()
                    )
                    await state.update_data(last_message_id=sent_message.message_id)
                    await state.clear()
                    return
                auto = Auto(
                    user_id=user.id,
                    brand=auto_input.brand,
                    year=auto_input.year,
                    vin=auto_input.vin,
                    license_plate=auto_input.license_plate
                )
                session.add(auto)
                session.commit()
                logger.info(f"Auto added: {auto_input.brand} {auto_input.license_plate} for user {message.from_user.id}")
                await state.update_data(auto_id=auto.id)
            await delete_previous_message(bot, message.chat.id, (await state.get_data()).get("last_message_id"))
            sent_message = await message.answer(
                "Автомобиль добавлен. Хотите добавить ещё один автомобиль или продолжить?",
                reply_markup=Keyboards.add_another_auto_kb()
            )
            await state.update_data(last_message_id=sent_message.message_id)
            await state.set_state(RepairBookingStates.AwaitingAddAnotherAuto)
        except Exception as e:
            logger.error(f"Ошибка добавления автомобиля: {str(e)}")
            await delete_previous_message(bot, message.chat.id, (await state.get_data()).get("last_message_id"))
            sent_message = await message.answer("Ошибка добавления автомобиля. Попробуйте снова.", reply_markup=Keyboards.main_menu_kb())
            await state.update_data(last_message_id=sent_message.message_id)
            await state.clear()
    except ValidationError as e:
        logger.warning(f"Validation error for license_plate: {e}, input: {license_plate}")
        await delete_previous_message(bot, message.chat.id, (await state.get_data()).get("last_message_id"))
        sent_message = await message.answer("Госномер слишком короткий или длинный (5–20 символов). Введите снова:")
        await state.update_data(last_message_id=sent_message.message_id)

@repair_booking_router.callback_query(RepairBookingStates.AwaitingAddAnotherAuto, F.data == "add_another_auto")
async def add_another_auto(callback: CallbackQuery, state: FSMContext, bot):
    """Обрабатывает выбор добавления ещё одного автомобиля."""
    logger.info(f"User {callback.from_user.id} requested to add another auto")
    try:
        await delete_previous_message(bot, callback.message.chat.id, (await state.get_data()).get("last_message_id"))
        sent_message = await callback.message.answer("Введите марку автомобиля:")
        await state.update_data(last_message_id=sent_message.message_id)
        await state.set_state(RepairBookingStates.AwaitingAutoBrand)
        await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка обработки запроса на добавление ещё одного автомобиля: {str(e)}")
        await delete_previous_message(bot, callback.message.chat.id, (await state.get_data()).get("last_message_id"))
        sent_message = await callback.message.answer("Ошибка. Попробуйте снова.", reply_markup=Keyboards.main_menu_kb())
        await state.update_data(last_message_id=sent_message.message_id)
        await state.clear()
        await callback.answer()

@repair_booking_router.callback_query(RepairBookingStates.AwaitingAddAnotherAuto, F.data == "continue_booking")
async def continue_booking(callback: CallbackQuery, state: FSMContext, bot):
    """Продолжает процесс бронирования."""
    logger.info(f"User {callback.from_user.id} chose to continue booking")
    try:
        with Session() as session:
            user = session.query(User).filter_by(telegram_id=str(callback.from_user.id)).first()
            if not user:
                await delete_previous_message(bot, callback.message.chat.id, (await state.get_data()).get("last_message_id"))
                sent_message = await callback.message.answer(
                    "Вы не зарегистрированы. Начните с записи на ТО.",
                    reply_markup=Keyboards.main_menu_kb()
                )
                await state.update_data(last_message_id=sent_message.message_id)
                await state.clear()
                await callback.answer()
                return
            autos = session.query(Auto).filter_by(user_id=user.id).all()
            if not autos:
                await delete_previous_message(bot, callback.message.chat.id, (await state.get_data()).get("last_message_id"))
                sent_message = await callback.message.answer(
                    "У вас нет зарегистрированных автомобилей. Добавьте авто.",
                    reply_markup=Keyboards.auto_selection_kb(autos)
                )
                await state.update_data(last_message_id=sent_message.message_id)
                await state.set_state(RepairBookingStates.AwaitingAuto)
                await callback.answer()
                return
            response = "Выберите автомобиль для ремонта:"
            try:
                await delete_previous_message(bot, callback.message.chat.id, (await state.get_data()).get("last_message_id"))
                photo_path = get_photo_path("booking_repair")
                sent_message = await callback.message.answer_photo(
                    photo=FSInputFile(photo_path),
                    caption=response,
                    reply_markup=Keyboards.auto_selection_kb(autos)
                )
                await state.update_data(last_message_id=sent_message.message_id)
            except (FileNotFoundError, ValueError) as e:
                logger.error(f"Ошибка загрузки фото для выбора автомобиля: {str(e)}")
                await delete_previous_message(bot, callback.message.chat.id, (await state.get_data()).get("last_message_id"))
                sent_message = await callback.message.answer(response, reply_markup=Keyboards.auto_selection_kb(autos))
                await state.update_data(last_message_id=sent_message.message_id)
            await state.set_state(RepairBookingStates.AwaitingAuto)
            await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка продолжения бронирования: {str(e)}")
        await delete_previous_message(bot, callback.message.chat.id, (await state.get_data()).get("last_message_id"))
        sent_message = await callback.message.answer("Ошибка. Попробуйте снова.", reply_markup=Keyboards.main_menu_kb())
        await state.update_data(last_message_id=sent_message.message_id)
        await state.clear()
        await callback.answer()

@repair_booking_router.callback_query(RepairBookingStates.AwaitingAuto, F.data.startswith("auto_"))
async def process_auto_selection(callback: CallbackQuery, state: FSMContext, bot):
    """Обрабатывает выбор автомобиля."""
    auto_id = int(callback.data.replace("auto_", ""))
    try:
        with Session() as session:
            auto = session.query(Auto).get(auto_id)
            if not auto:
                await delete_previous_message(bot, callback.message.chat.id, (await state.get_data()).get("last_message_id"))
                sent_message = await callback.message.answer("Автомобиль не найден. Попробуйте снова.",
                                             reply_markup=Keyboards.main_menu_kb())
                await state.update_data(last_message_id=sent_message.message_id)
                await state.clear()
                await callback.answer()
                return
            await state.update_data(auto_id=auto_id)
            response = f"Выбран автомобиль: {auto.brand} {auto.license_plate}\nОпишите проблему с автомобилем (например, 'стук в двигателе'):"
            if len(response) > 1024:
                logger.warning(f"Подпись слишком длинная ({len(response)} символов), отправляем без фото")
                await delete_previous_message(bot, callback.message.chat.id, (await state.get_data()).get("last_message_id"))
                sent_message = await callback.message.answer(response)
                await state.update_data(last_message_id=sent_message.message_id)
                await state.set_state(RepairBookingStates.AwaitingDescription)
                await callback.answer()
                return
            try:
                await delete_previous_message(bot, callback.message.chat.id, (await state.get_data()).get("last_message_id"))
                photo_path = get_photo_path("booking_repair_sel")
                sent_message = await callback.message.answer_photo(
                    photo=FSInputFile(photo_path),
                    caption=response
                )
                await state.update_data(last_message_id=sent_message.message_id)
            except (FileNotFoundError, ValueError) as e:
                logger.error(f"Ошибка загрузки фото для выбора автомобиля: {str(e)}")
                await delete_previous_message(bot, callback.message.chat.id, (await state.get_data()).get("last_message_id"))
                sent_message = await callback.message.answer(response)
                await state.update_data(last_message_id=sent_message.message_id)
            await state.set_state(RepairBookingStates.AwaitingDescription)
            await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка выбора автомобиля: {str(e)}")
        await delete_previous_message(bot, callback.message.chat.id, (await state.get_data()).get("last_message_id"))
        sent_message = await callback.message.answer("Ошибка. Попробуйте снова.", reply_markup=Keyboards.main_menu_kb())
        await state.update_data(last_message_id=sent_message.message_id)
        await state.clear()
        await callback.answer()

@repair_booking_router.message(RepairBookingStates.AwaitingDescription, F.text)
async def process_description(message: Message, state: FSMContext, bot):
    """Обрабатывает описание проблемы."""
    description = message.text.strip()
    if len(description) > 500:
        await delete_previous_message(bot, message.chat.id, (await state.get_data()).get("last_message_id"))
        sent_message = await message.answer("Описание слишком длинное. Максимум 500 символов. Попробуйте снова.")
        await state.update_data(last_message_id=sent_message.message_id)
        return
    await state.update_data(description=description)
    await delete_previous_message(bot, message.chat.id, (await state.get_data()).get("last_message_id"))
    sent_message = await message.answer(
        "Загрузите до 3 фотографий проблемы (если есть). Нажмите 'Готово' или 'Пропустить'.",
        reply_markup=Keyboards.photo_upload_kb()
    )
    await state.update_data(last_message_id=sent_message.message_id)
    await state.set_state(RepairBookingStates.AwaitingPhotos)
    await state.update_data(photos=[])

@repair_booking_router.message(RepairBookingStates.AwaitingPhotos, F.photo)
async def process_photo(message: Message, state: FSMContext, bot):
    """Обрабатывает загрузку фото."""
    data = await state.get_data()
    photos = data.get("photos", [])
    if len(photos) >= 3:
        await delete_previous_message(bot, message.chat.id, (await state.get_data()).get("last_message_id"))
        sent_message = await message.answer("Максимум 3 фото. Нажмите 'Готово' или 'Пропустить'.",
                            reply_markup=Keyboards.photo_upload_kb())
        await state.update_data(last_message_id=sent_message.message_id)
        return
    photo_id = message.photo[-1].file_id
    photos.append(photo_id)
    await state.update_data(photos=photos)
    await delete_previous_message(bot, message.chat.id, (await state.get_data()).get("last_message_id"))
    sent_message = await message.answer(f"Фото {len(photos)}/3 загружено. Добавьте ещё или нажмите 'Готово'.",
                        reply_markup=Keyboards.photo_upload_kb())
    await state.update_data(last_message_id=sent_message.message_id)

@repair_booking_router.callback_query(RepairBookingStates.AwaitingPhotos, F.data == "photos_ready")
async def process_photos_ready(callback: CallbackQuery, state: FSMContext, bot):
    """Обрабатывает завершение загрузки фото."""
    await delete_previous_message(bot, callback.message.chat.id, (await state.get_data()).get("last_message_id"))
    sent_message = await callback.message.answer("Выберите дату для ремонта:", reply_markup=Keyboards.calendar_kb())
    await state.update_data(last_message_id=sent_message.message_id)
    await state.set_state(RepairBookingStates.AwaitingDate)
    await callback.answer()

@repair_booking_router.callback_query(RepairBookingStates.AwaitingPhotos, F.data == "skip_photos")
async def skip_photos(callback: CallbackQuery, state: FSMContext, bot):
    """Обрабатывает пропуск загрузки фото."""
    await delete_previous_message(bot, callback.message.chat.id, (await state.get_data()).get("last_message_id"))
    sent_message = await callback.message.answer("Выберите дату для ремонта:", reply_markup=Keyboards.calendar_kb())
    await state.update_data(last_message_id=sent_message.message_id)
    await state.set_state(RepairBookingStates.AwaitingDate)
    await callback.answer()

@repair_booking_router.callback_query(RepairBookingStates.AwaitingDate, F.data.startswith("date_"))
async def process_date_selection(callback: CallbackQuery, state: FSMContext, bot):
    """Обрабатывает выбор даты."""
    date_str = callback.data.replace("date_", "")
    selected_date = datetime.strptime(date_str, "%Y-%m-%d")
    await state.update_data(selected_date=selected_date)
    with Session() as session:
        await delete_previous_message(bot, callback.message.chat.id, (await state.get_data()).get("last_message_id"))
        sent_message = await callback.message.answer(
            "Выберите время для ремонта:",
            reply_markup=Keyboards.time_slots_kb(selected_date, 60, session)
        )
        await state.update_data(last_message_id=sent_message.message_id)
        await state.set_state(RepairBookingStates.AwaitingTime)
        await callback.answer()

@repair_booking_router.callback_query(RepairBookingStates.AwaitingTime, F.data.startswith("time_"))
async def process_time_selection(callback: CallbackQuery, state: FSMContext, bot):
    """Обрабатывает выбор времени и создаёт запись."""
    time_str = callback.data.replace("time_", "")
    try:
        selected_time = datetime.strptime(time_str, "%H:%M").time()
        data = await state.get_data()
        with Session() as session:
            user = session.query(User).filter_by(telegram_id=str(callback.from_user.id)).first()
            auto = session.query(Auto).get(data["auto_id"])
            if not auto:
                await delete_previous_message(bot, callback.message.chat.id, (await state.get_data()).get("last_message_id"))
                sent_message = await callback.message.answer("Автомобиль не найден. Начните заново.",
                                             reply_markup=Keyboards.main_menu_kb())
                await state.update_data(last_message_id=sent_message.message_id)
                await state.clear()
                await callback.answer()
                return
            booking = Booking(
                user_id=user.id,
                auto_id=data["auto_id"],
                service_name="Ремонт",
                description=data["description"],
                date=data["selected_date"].date(),
                time=selected_time,
                status=BookingStatus.PENDING,
                price=None
            )
            session.add(booking)
            session.commit()
            logger.info(f"Repair booking created: {booking.id} for user {callback.from_user.id}")

            # Уведомление мастеру
            photos = data.get("photos", [])
            message_text = (
                f"📌 Новая заявка на ремонт #{booking.id}\n"
                f"Клиент: {user.first_name} {user.last_name}\n"
                f"Авто: {auto.brand} {auto.license_plate}\n"
                f"Проблема: {data['description']}\n"
                f"Дата: {booking.date.strftime('%d.%m.%Y')}\n"
                f"Время: {booking.time.strftime('%H:%M')}"
            )
            if photos:
                await bot.send_media_group(
                    chat_id=ADMIN_ID,
                    media=[{"type": "photo", "media": photo_id} for photo_id in photos]
                )
            await bot.send_message(ADMIN_ID, message_text)

            # Уведомление пользователю
            await delete_previous_message(bot, callback.message.chat.id, (await state.get_data()).get("last_message_id"))
            sent_message = await callback.message.answer(
                f"Ваша заявка на ремонт отправлена мастеру. Ожидайте подтверждения.\n"
                f"Проблема: {data['description']}",
                reply_markup=Keyboards.main_menu_kb()
            )
            await state.update_data(last_message_id=sent_message.message_id)
            await state.clear()
            await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка создания записи на ремонт: {str(e)}")
        await delete_previous_message(bot, callback.message.chat.id, (await state.get_data()).get("last_message_id"))
        sent_message = await callback.message.answer("Ошибка записи. Попробуйте снова.", reply_markup=Keyboards.main_menu_kb())
        await state.update_data(last_message_id=sent_message.message_id)
        await state.clear()
        await callback.answer()

@repair_booking_router.callback_query(F.data == "cancel_booking")
async def cancel_booking(callback: CallbackQuery, state: FSMContext, bot):
    """Обрабатывает отмену записи."""
    await delete_previous_message(bot, callback.message.chat.id, (await state.get_data()).get("last_message_id"))
    sent_message = await callback.message.answer("Запись на ремонт отменена.", reply_markup=Keyboards.main_menu_kb())
    await state.update_data(last_message_id=sent_message.message_id)
    await state.clear()
    await callback.answer()
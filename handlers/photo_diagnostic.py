from aiogram import Router, F, Bot
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, FSInputFile
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
import hashlib
import os
from PIL import Image
from io import BytesIO
from config import get_photo_path
from utils import setup_logger, analyze_text_description, analyze_images, delete_previous_message
from keyboards.main_kb import Keyboards

photo_diagnostic_router = Router()
logger = setup_logger(__name__)

# Папка для сохранения фото
MEDIA_DIR = "media/diagnostics"
os.makedirs(MEDIA_DIR, exist_ok=True)

# Состояния FSM
class DiagnosticStates(StatesGroup):
    AwaitingChoice = State()
    AwaitingTextDescription = State()
    AwaitingPhoto = State()
    AwaitingPhotoDescription = State()

# Прогресс-бар для загрузки фото
def get_progress_bar(current: int, total: int = 3) -> str:
    filled = "█" * current
    empty = " " * (total - current)
    return f"[{filled}{empty}] {current}/{total}"

def validate_photo_size(photo) -> bool:
    """Проверяет минимальное разрешение фото (640x480)."""
    return photo.width >= 640 and photo.height >= 480

def validate_photo_format(image_data: bytes) -> bool:
    """Проверяет формат изображения (JPEG/PNG)."""
    try:
        img = Image.open(BytesIO(image_data))
        return img.format in ["JPEG", "PNG"]
    except:
        return False

def get_image_hash(image_data: bytes) -> str:
    """Вычисляет MD5-хеш изображения."""
    return hashlib.md5(image_data).hexdigest()

async def get_cached_result(image_hash: str) -> str:
    """Проверяет кэш в файле."""
    cache_file = os.path.join(MEDIA_DIR, "cache.txt")
    try:
        with open(cache_file, "r", encoding="utf-8") as f:
            for line in f:
                if line.startswith(image_hash):
                    return line.split(":", 1)[1].strip()
    except:
        return None
    return None

async def cache_result(image_hash: str, result: str):
    """Сохраняет результат в кэш."""
    cache_file = os.path.join(MEDIA_DIR, "cache.txt")
    try:
        with open(cache_file, "a", encoding="utf-8") as f:
            f.write(f"{image_hash}:{result}\n")
    except Exception as e:
        logger.error(f"Ошибка кэширования: {str(e)}")

@photo_diagnostic_router.message(F.text == "Быстрый ответ - Диагностика по фото")
async def start_diagnostic(message: Message, state: FSMContext):
    """Запускает процесс диагностики, предлагая выбор варианта."""
    logger.info(f"Starting photo diagnostic for user {message.from_user.id}")
    try:
        photo_path = get_photo_path("photo_diagnostic")
        await message.answer_photo(
            photo=FSInputFile(photo_path),
            caption="Выберите способ диагностики:",
            reply_markup=Keyboards.diagnostic_choice_kb()
        )
    except (FileNotFoundError, ValueError) as e:
        logger.error(f"Ошибка загрузки фото для диагностики: {str(e)}")
        await message.answer(
            "Выберите способ диагностики:",
            reply_markup=Keyboards.diagnostic_choice_kb()
        )
    await state.set_state(DiagnosticStates.AwaitingChoice)
    logger.debug(f"Set state to AwaitingChoice for user {message.from_user.id}")


@photo_diagnostic_router.callback_query(F.data.in_(["text_diagnostic", "start_photo_diagnostic"]))
async def handle_diagnostic_choice(callback: CallbackQuery, state: FSMContext, bot: Bot):
    logger.debug(f"Received callback data: {callback.data} for user {callback.from_user.id}")
    try:
        # Сохраняем ID сообщения для удаления
        await state.update_data(last_message_id=callback.message.message_id)

        if callback.data == "text_diagnostic":
            await delete_previous_message(bot, callback.message.chat.id, callback.message.message_id)
            message = await callback.message.answer(
                "Опишите проблему с автомобилем текстом (например, 'стучит подвеска').",
                reply_markup=Keyboards.main_menu_kb()
            )
            await state.update_data(last_message_id=message.message_id)
            await state.set_state(DiagnosticStates.AwaitingTextDescription)
        elif callback.data == "start_photo_diagnostic":
            await delete_previous_message(bot, callback.message.chat.id, callback.message.message_id)
            message = await callback.message.answer(
                "📸 Нажмите на скрепку 📎 или перетащите 1–3 фото для диагностики...",
                reply_markup=Keyboards.photo_upload_kb()
            )
            await state.update_data(last_message_id=message.message_id)
            await state.set_state(DiagnosticStates.AwaitingPhoto)
            await state.update_data(photos=[])
        await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка обработки callback {callback.data}: {str(e)}")
        await callback.message.answer("Ошибка. Начните диагностику заново.", reply_markup=Keyboards.main_menu_kb())
        await state.clear()
        await callback.answer()

@photo_diagnostic_router.message(DiagnosticStates.AwaitingTextDescription, F.text)
async def handle_text_description(message: Message, state: FSMContext):
    """Обрабатывает текстовое описание проблемы."""
    try:
        description = message.text.strip()
        if len(description) < 5:
            await message.answer("Описание слишком короткое. Пожалуйста, опишите подробнее.", reply_markup=Keyboards.main_menu_kb())
            return
        logger.info(f"Processing text description: {description[:50]}... for user {message.from_user.id}")
        analysis = await analyze_text_description(description)
        try:
            photo_path = get_photo_path("photo_result_diagnostic")
            await message.answer_photo(
                photo=FSInputFile(photo_path),
                caption=f"🔧 Диагностика:\n"
                        f"Анализ:\n{analysis}\n"
                        f"Описание проблемы: {description}\n\n"
                        "📋 Рекомендуется очный осмотр для подтверждения.",
                reply_markup=Keyboards.main_menu_kb()
            )
        except (FileNotFoundError, ValueError) as e:
            logger.error(f"Ошибка отправки фото результата: {str(e)}")
            await message.answer(
                f"🔧 Диагностика:\n"
                f"Анализ:\n{analysis}\n"
                f"Описание проблемы: {description}\n\n"
                "📋 Рекомендуется очный осмотр для подтверждения.",
                reply_markup=Keyboards.main_menu_kb()
            )
        await state.clear()
        logger.debug(f"Cleared state for user {message.from_user.id}")
    except Exception as e:
        logger.error(f"Ошибка обработки текстового описания: {str(e)}")
        await message.answer("Ошибка. Начните диагностику заново.", reply_markup=Keyboards.main_menu_kb())
        await state.clear()

@photo_diagnostic_router.message(DiagnosticStates.AwaitingPhoto, F.photo)
async def handle_photo(message: Message, state: FSMContext):
    """Обрабатывает загруженные фото."""
    try:
        photo = message.photo[-1]
        if not validate_photo_size(photo):
            await message.answer("Ошибка: фото слишком маленькое (мин. 640x480).", reply_markup=Keyboards.main_menu_kb())
            return
        if photo.file_size > 5 * 1024 * 1024:
            await message.answer("Ошибка: файл слишком большой (макс. 5MB).", reply_markup=Keyboards.main_menu_kb())
            return

        file = await message.bot.get_file(photo.file_id)
        photo_bytes = await message.bot.download_file(file.file_path)
        image_data = photo_bytes.read()

        if not validate_photo_format(image_data):
            await message.answer("Ошибка: поддерживаются только JPEG и PNG.", reply_markup=Keyboards.main_menu_kb())
            return

        data = await state.get_data()
        photos = data.get("photos", [])
        photos.append(image_data)
        await state.update_data(photos=photos)

        logger.debug(f"Photo uploaded, total: {len(photos)} for user {message.from_user.id}")
        if len(photos) < 3:
            await message.answer(
                f"Фото загружено.\n"
                f"{get_progress_bar(len(photos))}\n"
                f"Нажмите на скрепку 📎 для следующего фото или выберите \"Готово\".",
                reply_markup=Keyboards.photo_upload_kb()
            )
        else:
            await message.answer(
                f"Фото загружено.\n"
                f"{get_progress_bar(len(photos))}\n"
                f"Нажмите \"Готово\" для анализа.",
                reply_markup=Keyboards.photo_upload_kb()
            )
    except Exception as e:
        logger.error(f"Ошибка обработки фото: {str(e)}")
        await message.answer(
            "Ошибка загрузки фото. Попробуйте снова.",
            reply_markup=Keyboards.photo_upload_kb()
        )
        await state.clear()

@photo_diagnostic_router.callback_query(DiagnosticStates.AwaitingPhoto, F.data == "photos_ready")
async def process_photos(callback: CallbackQuery, state: FSMContext):
    """Обрабатывает все загруженные фото и запрашивает описание."""
    data = await state.get_data()
    photos = data.get("photos", [])
    if not photos:
        await callback.message.answer("Фото не загружены. Отправьте фото снова.", reply_markup=Keyboards.main_menu_kb())
        await state.clear()
        await callback.answer()
        return

    try:
        image_hashes = [get_image_hash(photo) for photo in photos]
        cached_results = []
        for image_hash in image_hashes:
            cached = await get_cached_result(image_hash)
            if cached:
                cached_results.append(cached)
        if len(cached_results) == len(photos):
            analysis = "\n".join(cached_results)
            await state.update_data(analysis=analysis)
        else:
            await state.update_data(photos=photos)

        await callback.message.answer(
            "Опишите проблему с автомобилем текстом (например, 'горит чек, код P0420').",
            reply_markup=Keyboards.main_menu_kb()
        )
        await state.set_state(DiagnosticStates.AwaitingPhotoDescription)
        logger.debug(f"Set state to AwaitingPhotoDescription for user {callback.from_user.id}")
        await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка анализа: {str(e)}")
        await callback.message.answer("Ошибка анализа. Отправьте фото снова.", reply_markup=Keyboards.main_menu_kb())
        await state.clear()
        await callback.answer()
    finally:
        for i in range(len(photos)):
            file_path = os.path.join(MEDIA_DIR, f"{callback.from_user.id}_{i}.jpg")
            if os.path.exists(file_path):
                os.remove(file_path)

@photo_diagnostic_router.message(DiagnosticStates.AwaitingPhotoDescription, F.text)
async def handle_photo_description(message: Message, state: FSMContext):
    """Обрабатывает текстовое описание после загрузки фото."""
    try:
        description = message.text.strip()
        if len(description) < 5:
            await message.answer("Описание слишком короткое. Пожалуйста, опишите подробнее.", reply_markup=Keyboards.main_menu_kb())
            return
        data = await state.get_data()
        photos = data.get("photos", [])
        if photos:
            logger.info(f"Processing {len(photos)} photos with description: {description[:50]}... for user {message.from_user.id}")
            analysis = await analyze_images(photos, description)
            image_hashes = [get_image_hash(photo) for photo in photos]
            for image_hash in image_hashes:
                await cache_result(image_hash, analysis)
        else:
            logger.info(f"Processing description without photos: {description[:50]}... for user {message.from_user.id}")
            analysis = await analyze_text_description(description)
        try:
            photo_path = get_photo_path("photo_result_diagnostic")
            await message.answer_photo(
                photo=FSInputFile(photo_path),
                caption=f"🔧 Диагностика:\n"
                        f"Анализ:\n{analysis}\n"
                        f"Описание проблемы: {description}\n\n"
                        "📋 Рекомендуется очный осмотр для подтверждения.",
                reply_markup=Keyboards.main_menu_kb()
            )
        except (FileNotFoundError, ValueError) as e:
            logger.error(f"Ошибка отправки фото результата: {str(e)}")
            await message.answer(
                f"🔧 Диагностика:\n"
                f"Анализ:\n{analysis}\n"
                f"Описание проблемы: {description}\n\n"
                "📋 Рекомендуется очный осмотр для подтверждения.",
                reply_markup=Keyboards.main_menu_kb()
            )
        await state.clear()
        logger.debug(f"Cleared state for user {message.from_user.id}")
    except Exception as e:
        logger.error(f"Ошибка обработки описания: {str(e)}")
        await message.answer("Ошибка. Начните диагностику заново.", reply_markup=Keyboards.main_menu_kb())
        await state.clear()

@photo_diagnostic_router.message(DiagnosticStates.AwaitingPhoto)
async def invalid_photo_input(message: Message, state: FSMContext):
    """Обрабатывает некорректный ввод в состоянии ожидания фото."""
    data = await state.get_data()
    photos = data.get("photos", [])
    await message.answer(
        f"📸 Пожалуйста, нажмите на скрепку 📎 или перетащите фото.\n"
        f"{get_progress_bar(len(photos))}",
        reply_markup=Keyboards.photo_upload_kb()
    )

@photo_diagnostic_router.message(DiagnosticStates.AwaitingChoice)
async def invalid_choice_input(message: Message, state: FSMContext):
    """Обрабатывает некорректный ввод в состоянии выбора."""
    await message.answer(
        "Пожалуйста, выберите вариант диагностики, используя кнопки.",
        reply_markup=Keyboards.diagnostic_choice_kb()
    )

@photo_diagnostic_router.message(DiagnosticStates.AwaitingTextDescription)
async def invalid_text_description_input(message: Message, state: FSMContext):
    """Обрабатывает некорректный ввод в состоянии ожидания текстового описания."""
    await message.answer(
        "Пожалуйста, отправьте текстовое описание проблемы.",
        reply_markup=Keyboards.main_menu_kb()
    )

@photo_diagnostic_router.message(DiagnosticStates.AwaitingPhotoDescription)
async def invalid_photo_description_input(message: Message, state: FSMContext):
    """Обрабатывает некорректный ввод в состоянии ожидания описания после фото."""
    await message.answer(
        "Пожалуйста, отправьте текстовое описание проблемы.",
        reply_markup=Keyboards.main_menu_kb()
    )
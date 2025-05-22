from aiogram import Router, F
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, FSInputFile
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
import hashlib
import os
from PIL import Image
from io import BytesIO
from config import Config  # Обновлённый импорт
from utils import setup_logger, analyze_text_description, analyze_images  # Обновлённый импорт
from keyboards.main_kb import main_menu_kb

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

# Инлайн-кнопки для выбора варианта
def diagnostic_choice_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Описать текстом", callback_data="text_diagnostic")],
        [InlineKeyboardButton(text="Загрузить фото", callback_data="start_photo_diagnostic")]
    ])

# Инлайн-кнопка для "Готово"
def photo_upload_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Готово", callback_data="photos_ready")]
    ])

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
    """Проверяет кэш в файле (замените на redis, если нужно)."""
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

@photo_diagnostic_router.message(F.text.lower().contains("быстрый ответ - диагностика по фото"))
async def start_diagnostic(message: Message, state: FSMContext):
    """Запускает процесс диагностики, предлагая выбор варианта."""
    logger.info("Starting photo diagnostic")
    try:
        photo_path = Config.get_photo_path("photo_diagnostic")
        await message.answer_photo(
            photo=FSInputFile(photo_path),
            caption="Выберите способ диагностики:",
            reply_markup=diagnostic_choice_kb()
        )
    except (FileNotFoundError, ValueError) as e:
        logger.error(f"Ошибка загрузки фото для диагностики: {str(e)}")
        await message.answer(
            "Выберите способ диагностики:",
            reply_markup=diagnostic_choice_kb()
        )
    await state.set_state(DiagnosticStates.AwaitingChoice)

@photo_diagnostic_router.callback_query(DiagnosticStates.AwaitingChoice, F.data == "text_diagnostic")
async def choose_text_diagnostic(callback: CallbackQuery, state: FSMContext):
    """Обрабатывает выбор текстового описания."""
    await callback.message.answer(
        "Опишите проблему с автомобилем текстом (например, 'стучит подвеска').",
        reply_markup=main_menu_kb()
    )
    await state.set_state(DiagnosticStates.AwaitingTextDescription)
    await callback.answer()

@photo_diagnostic_router.callback_query(DiagnosticStates.AwaitingChoice, F.data == "start_photo_diagnostic")
async def choose_photo_diagnostic(callback: CallbackQuery, state: FSMContext):
    """Обрабатывает выбор загрузки фото."""
    await callback.message.answer(
        "📸 Нажмите на скрепку 📎 или перетащите 1–3 фото для диагностики (например, приборная панель, кузов, детали). "
        "Данные обрабатываются внешним сервисом.",
        reply_markup=photo_upload_kb()
    )
    await state.set_state(DiagnosticStates.AwaitingPhoto)
    await state.update_data(photos=[])
    await callback.answer()

@photo_diagnostic_router.message(DiagnosticStates.AwaitingTextDescription, F.text)
async def handle_text_description(message: Message, state: FSMContext):
    """Обрабатывает текстовое описание проблемы."""
    try:
        description = message.text.strip()
        if len(description) < 5:
            await message.answer("Описание слишком короткое. Пожалуйста, опишите подробнее.", reply_markup=main_menu_kb())
            return
        logger.info(f"Processing text description: {description[:50]}...")
        # Анализ текста через Yandex GPT
        analysis = await analyze_text_description(description)
        try:
            photo_path = Config.get_photo_path("photo_diagnostic")
            await message.answer_photo(
                photo=FSInputFile(photo_path),
                caption=f"🔧 Диагностика:\n"
                        f"Анализ:\n{analysis}\n"
                        f"Описание проблемы: {description}\n\n"
                        "📋 Рекомендуется очный осмотр для подтверждения.",
                reply_markup=main_menu_kb()
            )
        except (FileNotFoundError, ValueError) as e:
            logger.error(f"Ошибка отправки фото результата: {str(e)}")
            await message.answer(
                f"🔧 Диагностика:\n"
                f"Анализ:\n{analysis}\n"
                f"Описание проблемы: {description}\n\n"
                "📋 Рекомендуется очный осмотр для подтверждения.",
                reply_markup=main_menu_kb()
            )
        await state.clear()
    except Exception as e:
        logger.error(f"Ошибка обработки текстового описания: {str(e)}")
        await message.answer("Ошибка. Начните диагностику заново.", reply_markup=main_menu_kb())
        await state.clear()

@photo_diagnostic_router.message(DiagnosticStates.AwaitingPhoto, F.photo)
async def handle_photo(message: Message, state: FSMContext):
    """Обрабатывает загруженные фото."""
    try:
        photo = message.photo[-1]
        if not validate_photo_size(photo):
            await message.answer("Ошибка: фото слишком маленькое (мин. 640x480).", reply_markup=main_menu_kb())
            return
        if photo.file_size > 5 * 1024 * 1024:
            await message.answer("Ошибка: файл слишком большой (макс. 5MB).", reply_markup=main_menu_kb())
            return

        file = await message.bot.get_file(photo.file_id)
        photo_bytes = await message.bot.download_file(file.file_path)
        image_data = photo_bytes.read()

        if not validate_photo_format(image_data):
            await message.answer("Ошибка: поддерживаются только JPEG и PNG.", reply_markup=main_menu_kb())
            return

        data = await state.get_data()
        photos = data.get("photos", [])
        photos.append(image_data)
        await state.update_data(photos=photos)

        if len(photos) < 3:
            await message.answer(
                f"Фото загружено.\n"
                f"{get_progress_bar(len(photos))}\n"
                f"Нажмите на скрепку 📎 для следующего фото или выберите \"Готово\".",
                reply_markup=photo_upload_kb()
            )
        else:
            await message.answer(
                f"Фото загружено.\n"
                f"{get_progress_bar(len(photos))}\n"
                f"Нажмите \"Готово\" для анализа.",
                reply_markup=photo_upload_kb()
            )
    except Exception as e:
        logger.error(f"Ошибка обработки фото: {str(e)}")
        await message.answer(
            "Ошибка загрузки фото. Попробуйте снова.",
            reply_markup=photo_upload_kb()
        )
        await state.clear()

@photo_diagnostic_router.callback_query(DiagnosticStates.AwaitingPhoto, F.data == "photos_ready")
async def process_photos(callback: CallbackQuery, state: FSMContext):
    """Обрабатывает все загруженные фото и запрашивает описание."""
    data = await state.get_data()
    photos = data.get("photos", [])
    if not photos:
        await callback.message.answer("Фото не загружены. Отправьте фото снова.", reply_markup=main_menu_kb())
        await state.clear()
        await callback.answer()
        return

    try:
        # Проверяем кэш
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
            # Сохраняем фото для анализа после получения комментария
            await state.update_data(photos=photos)

        await callback.message.answer(
            "Опишите проблему с автомобилем текстом (например, 'горит чек, код P0420').",
            reply_markup=main_menu_kb()
        )
        await state.set_state(DiagnosticStates.AwaitingPhotoDescription)
        await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка анализа: {str(e)}")
        await callback.message.answer("Ошибка анализа. Отправьте фото снова.", reply_markup=main_menu_kb())
        await state.clear()
        await callback.answer()
    finally:
        # Очистка временных файлов
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
            await message.answer("Описание слишком короткое. Пожалуйста, опишите подробнее.", reply_markup=main_menu_kb())
            return
        data = await state.get_data()
        photos = data.get("photos", [])
        if photos:
            logger.info(f"Processing {len(photos)} photos with description: {description[:50]}...")
            # Анализ фото и комментария через Yandex Vision + GPT
            analysis = await analyze_images(photos, description)
            # Кэширование результатов
            image_hashes = [get_image_hash(photo) for photo in photos]
            for image_hash in image_hashes:
                await cache_result(image_hash, analysis)
        else:
            # Анализ только текста через Yandex GPT
            logger.info(f"Processing description without photos: {description[:50]}...")
            analysis = await analyze_text_description(description)
        try:
            photo_path = Config.get_photo_path("photo_result_diagnostic")  # Восстановлено
            await message.answer_photo(
                photo=FSInputFile(photo_path),
                caption=f"🔧 Диагностика:\n"
                        f"Анализ:\n{analysis}\n"
                        f"Описание проблемы: {description}\n\n"
                        "📋 Рекомендуется очный осмотр для подтверждения.",
                reply_markup=main_menu_kb()
            )
        except (FileNotFoundError, ValueError) as e:
            logger.error(f"Ошибка отправки фото результата: {str(e)}")
            await message.answer(
                f"🔧 Диагностика:\n"
                f"Анализ:\n{analysis}\n"
                f"Описание проблемы: {description}\n\n"
                "📋 Рекомендуется очный осмотр для подтверждения.",
                reply_markup=main_menu_kb()
            )
        await state.clear()
    except Exception as e:
        logger.error(f"Ошибка обработки описания: {str(e)}")
        await message.answer("Ошибка. Начните диагностику заново.", reply_markup=main_menu_kb())
        await state.clear()

@photo_diagnostic_router.message(DiagnosticStates.AwaitingPhoto)
async def invalid_photo_input(message: Message, state: FSMContext):
    """Обрабатывает некорректный ввод в состоянии ожидания фото."""
    data = await state.get_data()
    photos = data.get("photos", [])
    await message.answer(
        f"📸 Пожалуйста, нажмите на скрепку 📎 или перетащите фото.\n"
        f"{get_progress_bar(len(photos))}",
        reply_markup=photo_upload_kb()
    )

@photo_diagnostic_router.message(DiagnosticStates.AwaitingChoice)
async def invalid_choice_input(message: Message, state: FSMContext):
    """Обрабатывает некорректный ввод в состоянии выбора."""
    await message.answer(
        "Пожалуйста, выберите вариант диагностики, используя кнопки.",
        reply_markup=diagnostic_choice_kb()
    )

@photo_diagnostic_router.message(DiagnosticStates.AwaitingTextDescription)
async def invalid_text_description_input(message: Message, state: FSMContext):
    """Обрабатывает некорректный ввод в состоянии ожидания текстового описания."""
    await message.answer(
        "Пожалуйста, отправьте текстовое описание проблемы.",
        reply_markup=main_menu_kb()
    )

@photo_diagnostic_router.message(DiagnosticStates.AwaitingPhotoDescription)
async def invalid_photo_description_input(message: Message, state: FSMContext):
    """Обрабатывает некорректный ввод в состоянии ожидания описания после фото."""
    await message.answer(
        "Пожалуйста, отправьте текстовое описание проблемы.",
        reply_markup=main_menu_kb()
    )
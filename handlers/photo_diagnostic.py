from aiogram import Router, F
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
import logging
import hashlib
import os
from PIL import Image
from io import BytesIO
from utils.gpt_helper import analyze_text_description
from utils.vision_api import analyze_images
from keyboards.main_kb import main_menu_kb

photo_diagnostic_router = Router()
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
console_handler = logging.StreamHandler()
console_handler.setFormatter(formatter)
console_handler.setLevel(logging.INFO)
console_handler.stream.reconfigure(encoding='utf-8')
file_handler = logging.FileHandler("bot.log", encoding="utf-8")
file_handler.setFormatter(formatter)
file_handler.setLevel(logging.INFO)
logger.handlers = [console_handler, file_handler]

# Папка для сохранения фото
MEDIA_DIR = "media/diagnostics"
os.makedirs(MEDIA_DIR, exist_ok=True)

# Состояния FSM
class DiagnosticStates(StatesGroup):
    AwaitingChoice = State()
    AwaitingTextDescription = State()
    AwaitingPhoto = State()
    AwaitingPhotoDescription = State()
    AwaitingMileage = State()

# Инлайн-кнопки для выбора варианта
def diagnostic_choice_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Описать текстом", callback_data="text_diagnostic")],
        [InlineKeyboardButton(text="Загрузить фото", callback_data="photo_diagnostic")]
    ])

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

@photo_diagnostic_router.callback_query(DiagnosticStates.AwaitingChoice, F.data == "photo_diagnostic")
async def choose_photo_diagnostic(callback: CallbackQuery, state: FSMContext):
    """Обрабатывает выбор загрузки фото."""
    await callback.message.answer(
        "📸 Отправьте 1–3 фото для диагностики (например, приборная панель, кузов, детали). "
        "Данные обрабатываются внешним сервисом.",
        reply_markup=main_menu_kb()
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
            await message.answer("Описание слишком короткое. Пожалуйста, опишите подробнее.")
            return
        # Анализ текста через Yandex GPT
        analysis = await analyze_text_description(description)
        await state.update_data(description=description, analysis=analysis)
        await message.answer(
            "Сколько км пробега у автомобиля?",
            reply_markup=main_menu_kb()
        )
        await state.set_state(DiagnosticStates.AwaitingMileage)
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
            await message.answer("Ошибка: фото слишком маленькое (мин. 640x480).")
            return
        if photo.file_size > 5 * 1024 * 1024:
            await message.answer("Ошибка: файл слишком большой (макс. 5MB).")
            return

        file = await message.bot.get_file(photo.file_id)
        photo_bytes = await message.bot.download_file(file.file_path)
        image_data = photo_bytes.read()

        if not validate_photo_format(image_data):
            await message.answer("Ошибка: поддерживаются только JPEG и PNG.")
            return

        data = await state.get_data()
        photos = data.get("photos", [])
        photos.append(image_data)
        await state.update_data(photos=photos)

        if len(photos) < 3:
            await message.answer(f"Загружено {len(photos)} фото. Отправьте ещё или напишите 'Готово'.")
        else:
            await message.answer("Загружено 3 фото. Напишите 'Готово' для анализа.")
    except Exception as e:
        logger.error(f"Ошибка обработки фото: {str(e)}")
        await message.answer("Ошибка загрузки фото. Попробуйте снова.", reply_markup=main_menu_kb())
        await state.clear()

@photo_diagnostic_router.message(DiagnosticStates.AwaitingPhoto, F.text.lower() == "готово")
async def process_photos(message: Message, state: FSMContext):
    """Обрабатывает все загруженные фото и запрашивает описание."""
    data = await state.get_data()
    photos = data.get("photos", [])
    if not photos:
        await message.answer("Фото не загружены. Отправьте фото снова.", reply_markup=main_menu_kb())
        await state.clear()
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

        await message.answer(
            "Опишите проблему с автомобилем текстом (например, 'горит чек, код P0420').",
            reply_markup=main_menu_kb()
        )
        await state.set_state(DiagnosticStates.AwaitingPhotoDescription)
    except Exception as e:
        logger.error(f"Ошибка анализа: {str(e)}")
        await message.answer("Ошибка анализа. Отправьте фото снова.", reply_markup=main_menu_kb())
        await state.clear()
    finally:
        # Очистка временных файлов
        for i in range(len(photos)):
            file_path = os.path.join(MEDIA_DIR, f"{message.from_user.id}_{i}.jpg")
            if os.path.exists(file_path):
                os.remove(file_path)

@photo_diagnostic_router.message(DiagnosticStates.AwaitingPhotoDescription, F.text)
async def handle_photo_description(message: Message, state: FSMContext):
    """Обрабатывает текстовое описание после загрузки фото."""
    try:
        description = message.text.strip()
        if len(description) < 5:
            await message.answer("Описание слишком короткое. Пожалуйста, опишите подробнее.")
            return
        data = await state.get_data()
        photos = data.get("photos", [])
        if photos:
            # Анализ фото и комментария через Yandex Vision + GPT
            analysis = await analyze_images(photos, description)
        else:
            # Анализ только текста через Yandex GPT
            analysis = await analyze_text_description(description)
        await state.update_data(description=description, analysis=analysis)
        await message.answer(
            "Сколько км пробега у автомобиля?",
            reply_markup=main_menu_kb()
        )
        await state.set_state(DiagnosticStates.AwaitingMileage)
    except Exception as e:
        logger.error(f"Ошибка обработки описания: {str(e)}")
        await message.answer("Ошибка. Начните диагностику заново.", reply_markup=main_menu_kb())
        await state.clear()

@photo_diagnostic_router.message(DiagnosticStates.AwaitingMileage, F.text)
async def process_mileage(message: Message, state: FSMContext):
    """Обрабатывает пробег и завершает диагностику."""
    try:
        mileage = message.text.strip()
        if not mileage.isdigit():
            await message.answer("Пожалуйста, введите пробег в километрах (число).")
            return
        data = await state.get_data()
        analysis = data.get("analysis", "Нет данных")
        description = data.get("description", "Описание не предоставлено")
        await message.answer(
            f"🔧 Диагностика (пробег: {mileage} км):\n"
            f"Анализ:\n{analysis}\n"
            f"Описание проблемы: {description}\n\n"
            "📋 Рекомендуется очный осмотр для подтверждения.",
            reply_markup=main_menu_kb()
        )
        await state.clear()
    except Exception as e:
        logger.error(f"Ошибка обработки пробега: {str(e)}")
        await message.answer("Ошибка. Начните диагностику заново.", reply_markup=main_menu_kb())
        await state.clear()

@photo_diagnostic_router.message(DiagnosticStates.AwaitingPhoto)
async def invalid_photo_input(message: Message, state: FSMContext):
    """Обрабатывает некорректный ввод в состоянии ожидания фото."""
    await message.answer(
        "Пожалуйста, отправьте фото или напишите 'Готово' для анализа.",
        reply_markup=main_menu_kb()
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
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, FSInputFile
from config import get_photo_path, MESSAGES
from keyboards.main_kb import Keyboards
from utils import setup_logger

logger = setup_logger(__name__)
common_router = Router()

@common_router.message(Command("start"))
async def cmd_start(message: Message):
    """Обработчик команды /start."""
    try:
        photo_path = get_photo_path("welcome")
        await message.answer_photo(
            photo=FSInputFile(photo_path),
            caption=MESSAGES["welcome"],
            reply_markup=Keyboards.main_menu_kb()
        )
    except (FileNotFoundError, ValueError) as e:
        logger.error(f"Ошибка загрузки фото для /start: {str(e)}")
        await message.answer(
            MESSAGES["welcome"],
            reply_markup=Keyboards.main_menu_kb()
        )

@common_router.message(F.text == "📞 Контакты/как проехать")
async def show_contacts(message: Message):
    """Обработчик текстового сообщения '📞 Контакты/как проехать'."""
    try:
        photo_path = get_photo_path("contacts")
        await message.answer_photo(
            photo=FSInputFile(photo_path),
            caption=MESSAGES["contacts"],
            reply_markup=Keyboards.main_menu_kb()
        )
    except (FileNotFoundError, ValueError) as e:
        logger.error(f"Ошибка загрузки фото для контактов: {str(e)}")
        await message.answer(
            MESSAGES["contacts"],
            reply_markup=Keyboards.main_menu_kb()
        )

@common_router.message(F.text == "О мастере")
async def cmd_about_master(message: Message):
    """Обработчик текстового сообщения 'О мастере'."""
    try:
        photo_path = get_photo_path("about_master")
        await message.answer_photo(photo=FSInputFile(photo_path))
        await message.answer(MESSAGES["about_master"], reply_markup=Keyboards.main_menu_kb())
    except Exception as e:
        logger.error(f"Ошибка отправки информации о мастере: {str(e)}")
        await message.answer("Ошибка. Попробуйте снова.", reply_markup=Keyboards.main_menu_kb())

@common_router.message(F.text == "Быстрый ответ - Диагностика по фото")
async def cmd_diagnostic(message: Message):
    """Обработчик текстового сообщения 'Быстрый ответ - Диагностика по фото'."""
    await message.answer(
        "Выберите способ диагностики:",
        reply_markup=Keyboards.diagnostic_choice_kb()
    )
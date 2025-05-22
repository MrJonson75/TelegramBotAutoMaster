from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, FSInputFile
from keyboards.main_kb import Keyboards  # Обновлённый импорт
from config import Config
from utils import setup_logger

logger = setup_logger(__name__)

common_router = Router()

# Обработчик команды /start
@common_router.message(Command("start"))
async def cmd_start(message: Message):
    try:
        photo_path = Config.get_photo_path("welcome")
        await message.answer_photo(
            photo=FSInputFile(photo_path),
            caption=Config.MESSAGES["welcome"],
            reply_markup=Keyboards.main_menu_kb()  # Обновлено
        )
    except (FileNotFoundError, ValueError) as e:
        logger.error(f"Ошибка загрузки фото для /start: {str(e)}")
        await message.answer(
            Config.MESSAGES["welcome"],
            reply_markup=Keyboards.main_menu_kb()  # Обновлено
        )

# Обработчик текстового сообщения "📞 Контакты/как проехать"
@common_router.message(F.text == "📞 Контакты/как проехать")
async def show_contacts(message: Message):
    try:
        photo_path = Config.get_photo_path("contacts")
        await message.answer_photo(
            photo=FSInputFile(photo_path),
            caption=Config.MESSAGES["contacts"],
            reply_markup=Keyboards.main_menu_kb()  # Обновлено
        )
    except (FileNotFoundError, ValueError) as e:
        logger.error(f"Ошибка загрузки фото для контактов: {str(e)}")
        await message.answer(
            Config.MESSAGES["contacts"],
            reply_markup=Keyboards.main_menu_kb()  # Обновлено
        )

# Обработчик текстового сообщения "О мастере"
@common_router.message(F.text == "О мастере")
async def show_about_master(message: Message):
    try:
        photo_path = Config.get_photo_path("about_master")
        await message.answer_photo(
            photo=FSInputFile(photo_path),
            caption=Config.MESSAGES["about_master"],
            reply_markup=Keyboards.main_menu_kb()  # Обновлено
        )
    except (FileNotFoundError, ValueError) as e:
        logger.error(f"Ошибка загрузки фото для 'О мастере': {str(e)}")
        await message.answer(
            Config.MESSAGES["about_master"],
            reply_markup=Keyboards.main_menu_kb()  # Обновлено
        )
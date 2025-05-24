from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, FSInputFile, InlineKeyboardMarkup, InlineKeyboardButton
from config import get_photo_path, MESSAGES
from keyboards.main_kb import Keyboards
from utils import setup_logger, delete_previous_message
from typing import Optional

logger = setup_logger(__name__)
common_router = Router()


async def send_message_with_cleanup(
        message: Message,
        text: str,
        photo_path: Optional[str] = None,
        reply_markup: Optional[InlineKeyboardMarkup] = None
) -> bool:
    """Отправляет сообщение с удалением предыдущего и логированием."""
    try:
        # Удаляем предыдущее сообщение бота
        await delete_previous_message(message)

        if photo_path:
            sent_message = await message.answer_photo(
                photo=FSInputFile(photo_path),
                caption=text,
                parse_mode="HTML",
                reply_markup=reply_markup
            )
        else:
            sent_message = await message.answer(
                text,
                parse_mode="HTML",
                reply_markup=reply_markup
            )
        logger.debug(f"Сообщение отправлено: {text[:50]}...")
        return True
    except Exception as e:
        logger.error(f"Ошибка отправки сообщения: {str(e)}")
        await message.answer(
            "😔 Произошла ошибка. Попробуйте снова.",
            parse_mode="HTML",
            reply_markup=Keyboards.main_menu_kb()
        )
        return False


@common_router.message(Command("start"))
async def cmd_start(message: Message):
    """Обработчик команды /start."""
    logger.info(f"Пользователь {message.from_user.id} выполнил команду /start")
    back_button = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="Назад в меню ⬅", callback_data="back_to_main")
    ]])
    await send_message_with_cleanup(
        message,
        f"<b>Добро пожаловать!</b>\n{MESSAGES['welcome']} 🚗",
        photo_path=get_photo_path("welcome"),
        reply_markup=back_button
    )


@common_router.message(F.text == "📞 Контакты/как проехать")
async def show_contacts(message: Message):
    """Обработчик текстового сообщения '📞 Контакты/как проехать'."""
    logger.info(f"Пользователь {message.from_user.id} запросил контакты")
    back_button = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="Назад в меню ⬅", callback_data="back_to_main")
    ]])
    await send_message_with_cleanup(
        message,
        f"<b>Контакты и проезд</b>\n{MESSAGES['contacts']} 📍",
        photo_path=get_photo_path("contacts"),
        reply_markup=back_button
    )


@common_router.message(F.text == "О мастере")
async def cmd_about_master(message: Message):
    """Обработчик текстового сообщения 'О мастере'."""
    logger.info(f"Пользователь {message.from_user.id} запросил информацию о мастере")
    back_button = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="Назад в меню ⬅", callback_data="back_to_main")
    ]])
    # Сначала отправляем фото
    if await send_message_with_cleanup(
            message,
            None,  # Без текста, только фото
            photo_path=get_photo_path("about_master")
    ):
        # Затем отправляем текст с информацией
        await send_message_with_cleanup(
            message,
            f"<b>О мастере</b>\n{MESSAGES['about_master']} 🔧",
            reply_markup=back_button
        )
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, FSInputFile
from config import get_photo_path, MESSAGES
from keyboards.main_kb import Keyboards
from utils.service_utils import send_message, setup_logger
from utils import delete_previous_message
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
        await delete_previous_message(message)
        if photo_path:
            sent_message = await send_message(
                message.bot, str(message.chat.id), "photo",
                text, photo=photo_path, reply_markup=reply_markup
            )
            return bool(sent_message)
        sent_message = await send_message(
            message.bot, str(message.chat.id), "text",
            text, reply_markup=reply_markup
        )
        logger.debug(f"Сообщение отправлено: {text[:50]}...")
        return bool(sent_message)
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
    await send_message_with_cleanup(
        message,
        f"<b>Добро пожаловать!</b>\n{MESSAGES['welcome']} 🚗",
        photo_path=get_photo_path("welcome"),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Начать в меню ⬅", callback_data="back_to_main")]
        ])
    )

@common_router.message(F.text == "📞 Контакты/как проехать")
async def show_contacts(message: Message):
    """Обработчик текстового сообщения '📞 Контакты/как проехать'."""
    logger.info(f"Пользователь {message.from_user.id} запросил контакты")
    await send_message_with_cleanup(
        message,
        f"<b>Контакты и проезд</b>\n{MESSAGES['contacts']} 📍",
        photo_path=get_photo_path("contacts"),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Назад в меню ⬅", callback_data="back_to_main")]
        ])
    )

@common_router.message(F.text == "О мастере")
async def cmd_about_master(message: Message):
    """Обработчик текстового сообщения 'О мастере'."""
    logger.info(f"Пользователь {message.from_user.id} запросил информацию о мастере")
    response = (
        f"<b>О мастере 🚗</b>\n"
        f"Узнайте больше о нашем мастере и его работе!\n"
        f"Выберите раздел:"
    )

    await send_message_with_cleanup(
        message,
        response,
        photo_path=get_photo_path("about_master"),
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(text="📜 Немного о себе", callback_data="master_about"),
                    InlineKeyboardButton(text="⭐ Лента отзывов", callback_data="master_reviews"),
                ],
                [InlineKeyboardButton(text="🟢 Примеры работ", callback_data="master_works")],
                [InlineKeyboardButton(text="⬅ Назад в меню", callback_data="back_to_main")]
            ]
        )
    )
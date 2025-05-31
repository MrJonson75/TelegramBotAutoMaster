from aiogram import Router, F, Bot
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from database import Session, Review
from config import get_photo_path, MESSAGES
from utils.service_utils import send_message, get_progress_bar
from keyboards.main_kb import Keyboards
from utils import setup_logger

logger = setup_logger(__name__)
master_info_router = Router()

# Прогресс-бар для UX
MASTER_PROGRESS_STEPS = {
    "about": 1,
    "reviews": 2,
    "works": 3
}

def get_master_menu_kb() -> InlineKeyboardMarkup:
    """Возвращает инлайн-клавиатуру для меню 'О мастере'."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📜 Немного о себе", callback_data="master_about"),
            InlineKeyboardButton(text="⭐ Лента отзывов", callback_data="master_reviews"),
        ],
        [
            InlineKeyboardButton(text="🛠️ Примеры работ", callback_data="master_works"),
        ],
        [
            InlineKeyboardButton(text="⬅ Назад в меню", callback_data="back_to_main"),
        ]
    ])

@master_info_router.callback_query(F.data == "master_menu")
async def show_master_menu(callback: CallbackQuery, state: FSMContext, bot: Bot):
    """Показывает меню 'О мастере' с инлайн-клавиатурой."""
    try:
        response = (
            f"<b>О мастере 🚗</b>\n"
            f"Узнайте больше о мастере и его работе!\n"
            f"Выберите раздел:"
        )
        sent_message = await send_message(
            bot, str(callback.message.chat.id), "photo",
            response,
            photo=get_photo_path("about_master"),
            reply_markup=get_master_menu_kb()
        )
        if sent_message:
            await state.update_data(last_message_id=sent_message.message_id)
        await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка при показе меню мастера: {str(e)}")
        await callback.answer("😔 Произошла ошибка.")

@master_info_router.callback_query(F.data == "master_about")
async def show_master_about(callback: CallbackQuery, state: FSMContext, bot: Bot):
    """Показывает информацию 'Немного о себе'."""
    try:
        response = (
            f"{await get_progress_bar('about', MASTER_PROGRESS_STEPS, style='emoji')}\n"
            f"<b>📜 Немного о себе</b>\n"
            f"{MESSAGES['about_master']}\n"
            f"😎 Качество и забота о вашем авто!"
        )
        sent_message = await send_message(
            bot, str(callback.message.chat.id), "photo",
            response,
            photo=get_photo_path("about_master"),
            reply_markup=get_master_menu_kb()
        )
        if sent_message:
            await state.update_data(last_message_id=sent_message.message_id)
        await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка при показе 'Немного о себе': {str(e)}")
        await callback.answer("😔 Произошла ошибка.")

@master_info_router.callback_query(F.data == "master_reviews")
async def show_master_reviews(callback: CallbackQuery, state: FSMContext, bot: Bot):
    """Показывает ленту отзывов (последние 5)."""
    try:
        with Session() as session:
            reviews = session.query(Review).order_by(Review.created_at.desc()).limit(5).all()
            response = (
                f"{await get_progress_bar('reviews', MASTER_PROGRESS_STEPS, style='emoji')}\n"
                f"<b>⭐ Лента отзывов</b>\n"
            )
            if not reviews:
                response += "😢 Пока нет отзывов. Будьте первым!"
            else:
                for review in reviews:
                    rating = review.rating if hasattr(review, 'rating') and review.rating else "Без рейтинга"
                    response += (
                        f"📅 {review.created_at.strftime('%d.%m.%Y')}\n"
                        f"⭐ {rating}\n"
                        f"{review.text[:50]}{'?' if len(review.text) > 50 else ''}\n"
                        f"{'📸 С фото' if review.photo1 else ''}\n\n"
                    )

        sent_message = await send_message(
            bot, str(callback.message.chat.id), "photo",
            response,
            photo=get_photo_path("reviews"),
            reply_markup=get_master_menu_kb()
        )
        if sent_message:
            await state.update_data(last_message_id=sent_message.message_id)
        await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка при показе отзывов: {str(e)}")
        await callback.answer("😔 Произошла ошибка.")

@master_info_router.callback_query(F.data == "master_works")
async def show_master_works(callback: CallbackQuery, state: FSMContext, bot: Bot):
    """Показывает примеры работ."""
    try:
        response = (
            f"{await get_progress_bar('works', MASTER_PROGRESS_STEPS, style='emoji')}\n"
            f"<b>🛠️ Примеры работ</b>\n"
            f"Что мы умеем:\n"
            f"🔧 Диагностика и ремонт двигателей\n"
            f"🚗 Полное ТО и замена масла\n"
            f"⚙️ Ремонт ходовой и электроники\n"
            f"📸 Посмотрите фото наших работ!"
        )
        sent_message = await send_message(
            bot, str(callback.message.chat.id), "photo",
            response,
            photo=get_photo_path("works"),
            reply_markup=get_master_menu_kb()
        )
        if sent_message:
            await state.update_data(last_message_id=sent_message.message_id)
        await callback.answer()
    except Exception as e:
        logger.error(f"Error showing master works: {str(e)}")
        await callback.answer("😔 Произошла ошибка.")
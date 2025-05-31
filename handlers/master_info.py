from aiogram import Router, F, Bot
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from database import Session, Review
from config import get_photo_path, MESSAGES
from utils.service_utils import send_message, get_progress_bar
from utils import setup_logger
from datetime import datetime
import pytz

logger = setup_logger(__name__)
master_info_router = Router()

MASTER_PROGRESS_STEPS = {
    "about": 1,
    "reviews": 2,
    "works": 3
}

def get_master_menu_kb() -> InlineKeyboardMarkup:
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
    await show_reviews_page(callback, state, bot, page=0)

@master_info_router.callback_query(F.data.startswith("reviews_page_"))
async def show_reviews_page(callback: CallbackQuery, state: FSMContext, bot: Bot, page: int = 0):
    try:
        with Session() as session:
            reviews = session.query(Review).order_by(Review.created_at.desc()).all()
            reviews_per_page = 5
            start_idx = page * reviews_per_page
            end_idx = min(start_idx + reviews_per_page, len(reviews))
            msk = pytz.timezone("Europe/Moscow")
            response = (
                f"{await get_progress_bar('reviews', MASTER_PROGRESS_STEPS, style='emoji')}\n"
                f"<b>⭐ Лента отзывов</b>\n"
            )
            if not reviews:
                response += "😢 Пока нет отзывов. Будьте первым!"
            else:
                for review in reviews[start_idx:end_idx]:
                    rating = f"{'⭐' * review.rating}" if review.rating else "Без рейтинга"
                    has_media = review.photo1 or review.video
                    response += (
                        f"📅 {review.created_at.astimezone(msk).strftime('%d.%m.%Y')}\n"
                        f"⭐ {rating}\n"
                        f"{review.text[:50]}{'...' if len(review.text) > 50 else ''}\n"
                        f"{'📸 С медиа' if has_media else ''}\n\n"
                    )

            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                *[[InlineKeyboardButton(text=f"Отзыв #{r.id}", callback_data=f"view_review_{r.id}")]
                  for r in reviews[start_idx:end_idx]],
                *([[
                    InlineKeyboardButton(text="⬅ Назад", callback_data=f"reviews_page_{page-1}") if page > 0 else None,
                    InlineKeyboardButton(text="Вперёд ➡", callback_data=f"reviews_page_{page+1}")
                    if end_idx < len(reviews) else None
                ]] if reviews else []),
                [InlineKeyboardButton(text="⬅ Назад в меню", callback_data="master_menu")]
            ])
            keyboard.inline_keyboard = [[btn for btn in row if btn] for row in keyboard.inline_keyboard if any(row)]

            sent_message = await send_message(
                bot, str(callback.message.chat.id), "photo",
                response,
                photo=get_photo_path("reviews"),
                reply_markup=keyboard
            )
            if sent_message:
                await state.update_data(last_message_id=sent_message.message_id)
            await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка при показе страницы отзывов #{page}: {str(e)}")
        await callback.answer("😔 Произошла ошибка.")

@master_info_router.callback_query(F.data.startswith("view_review_"))
async def view_review_media(callback: CallbackQuery, state: FSMContext, bot: Bot):
    review_id = int(callback.data.replace("view_review_", ""))
    try:
        with Session() as session:
            review = session.query(Review).get(review_id)
            if not review:
                await callback.answer("Отзыв не найден.")
                return
            msk = pytz.timezone("Europe/Moscow")
            rating = f"{'⭐' * review.rating}" if review.rating else "Без рейтинга"
            response = (
                f"<b>Отзыв #{review.id}</b>\n"
                f"📅 {review.created_at.astimezone(msk).strftime('%d.%m.%Y')}\n"
                f"⭐ {rating}\n"
                f"{review.text}\n"
            )
            photos = [p for p in [review.photo1, review.photo2, review.photo3] if p]
            video = review.video
            if photos or video:
                if photos:
                    for i, photo in enumerate(photos, 1):
                        await send_message(
                            bot, str(callback.message.chat.id), "photo",
                            response if i == 1 else None,
                            photo=photo
                        )
                if video:
                    await send_message(
                        bot, str(callback.message.chat.id), "video",
                        response if not photos else None,
                        video=video
                    )
            else:
                await send_message(
                    bot, str(callback.message.chat.id), "text",
                    response,
                    reply_markup=get_master_menu_kb()
                )
            await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка при показе медиа отзыва #{review_id}: {str(e)}")
        await callback.answer("😔 Произошла ошибка.")

@master_info_router.callback_query(F.data == "master_works")
async def show_master_works(callback: CallbackQuery, state: FSMContext, bot: Bot):
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
        logger.error(f"Ошибка при показе примеров работ: {str(e)}")
        await callback.answer("😔 Произошла ошибка.")
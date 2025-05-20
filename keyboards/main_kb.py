from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from aiogram.utils.keyboard import ReplyKeyboardBuilder



def main_menu_kb() -> ReplyKeyboardMarkup:
    """
    Создает главное меню бота с кнопками:
    - О мастере
    - Услуги и цены
    - Диагностика по фото
    - Записаться на прием
    - Мои записи
    - Контакты
    - Быстрый вопрос
    """
    builder = ReplyKeyboardBuilder()

    # Добавляем кнопки в 2 колонки
    builder.row(
        KeyboardButton(text="📋 О мастере"),
        KeyboardButton(text="🔧 Услуги без записи")
    )
    builder.row(
        KeyboardButton(text="🖼 Диагностика по фото"),
        KeyboardButton(text="🗓 Записаться на прием")
    )
    builder.row(
        KeyboardButton(text="✏ Мои записи"),
        KeyboardButton(text="📞 Контакты/как проехать")
    )
    builder.row(
        KeyboardButton(text="❓ Быстрый вопрос")
    )

    return builder.as_markup(
        resize_keyboard=True,
        one_time_keyboard=True,  # Меню скроется после выбора
        input_field_placeholder="Выберите действие..."
    )
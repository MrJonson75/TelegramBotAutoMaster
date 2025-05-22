from aiogram.utils.keyboard import ReplyKeyboardBuilder
from aiogram.types import ReplyKeyboardMarkup

def main_menu_kb() -> ReplyKeyboardMarkup:
    # Создание главного меню
    builder = ReplyKeyboardBuilder()
    builder.button(text="📞 Контакты/как проехать")
    builder.button(text="Запись на ТО")
    builder.button(text="Запись на ремонт")
    builder.button(text="Быстрый ответ - Диагностика по фото")
    builder.button(text="Мои записи")
    builder.button(text="О мастере")
    builder.adjust(2)
    return builder.as_markup(resize_keyboard=True)
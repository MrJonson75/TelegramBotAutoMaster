from aiogram.utils.keyboard import ReplyKeyboardBuilder
from aiogram.types import ReplyKeyboardMarkup, InlineKeyboardMarkup, InlineKeyboardButton


class Keyboards:
    """Класс для управления клавиатурами бота."""

    @staticmethod
    def main_menu_kb() -> ReplyKeyboardMarkup:
        """Создаёт главное меню."""
        builder = ReplyKeyboardBuilder()
        builder.button(text="📞 Контакты/как проехать")
        builder.button(text="Запись на ТО")
        builder.button(text="Запись на ремонт")
        builder.button(text="Быстрый ответ - Диагностика по фото")
        builder.button(text="Мои записи")
        builder.button(text="О мастере")
        builder.adjust(2)
        return builder.as_markup(resize_keyboard=True)

    @staticmethod
    def diagnostic_choice_kb() -> InlineKeyboardMarkup:
        """Создаёт инлайн-клавиатуру для выбора варианта диагностики."""
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Описать текстом", callback_data="text_diagnostic")],
            [InlineKeyboardButton(text="Загрузить фото", callback_data="start_photo_diagnostic")]
        ])

    @staticmethod
    def photo_upload_kb() -> InlineKeyboardMarkup:
        """Создаёт инлайн-клавиатуру для завершения загрузки фото."""
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Готово", callback_data="photos_ready")]
        ])
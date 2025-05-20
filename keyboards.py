from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import ReplyKeyboardBuilder, InlineKeyboardBuilder


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


def services_menu_kb(services: list[str]) -> InlineKeyboardMarkup:
    """
    Инлайн-клавиатура с перечнем услуг
    :param services: список услуг из БД/конфига
    :return: InlineKeyboardMarkup
    """
    builder = InlineKeyboardBuilder()

    # Добавляем кнопки услуг с callback-данными
    for service in services:
        builder.add(InlineKeyboardButton(
            text=service,
            callback_data=f"service_{service}"  # или используйте ID услуги
        ))

    # Добавляем кнопку "Назад"
    builder.row(InlineKeyboardButton(
        text="⬅️ Назад",
        callback_data="back_to_main"
    ))

    # Настройка расположения кнопок (по 2 в ряду)
    builder.adjust(2)

    return builder.as_markup()


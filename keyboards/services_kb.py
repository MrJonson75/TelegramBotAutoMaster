from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
import config



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


def services_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for service_name in config.SERVICES.keys():
        builder.button(
            text=service_name,
            callback_data=f"service_detail:{service_name}"
        )
    builder.button(text="⬅️ Назад", callback_data="back_to_main")
    builder.adjust(1)
    return builder.as_markup()

def service_actions_kb(service_name: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(
        text="📅 Записаться",
        callback_data=f"service_book:{service_name}"
    )
    builder.button(
        text="ℹ️ Подробнее",
        callback_data=f"service_info:{service_name}"
    )
    builder.button(
        text="⬅️ Назад к услугам",
        callback_data="back_to_services"
    )
    builder.adjust(1)
    return builder.as_markup()


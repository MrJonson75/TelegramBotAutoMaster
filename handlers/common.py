from typing import Union

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, FSInputFile, CallbackQuery

from keyboards import services_menu_kb, main_menu_kb
import config


comm_router = Router()


@comm_router.message(Command("start"))
async def cmd_start(message: Message):
    """Обработчик команды /start с приветствием и главным меню"""
    welcome_text = (
        "🚗 <b>Добро пожаловать в автомастерскую!</b>\n\n"
        "Я ваш помощник в организации ремонта автомобиля.\n"
        "С моей помощью вы можете:\n"
        "• Узнать о мастере и его опыте\n"
        "• Посмотреть услуги и цены\n"
        "• Записаться на удобное время\n"
        "• Предварительно оценить проблему по фото\n"
        "• Получить быстрый ответ на вопрос\n\n"
        "Выберите действие в меню ниже 👇"
    )

    await message.answer_photo(
        photo=FSInputFile("media/image/welcome.jpg"),  # Замените на реальное фото
        caption=welcome_text,
        reply_markup=main_menu_kb(),
        parse_mode="html",
    )

    # Отправляем дополнительное сообщение с важной информацией
    await message.answer(
        f"ℹ️ <b>Часы работы:</b>\n"
        f"Пн-Пт: {config.WORK_HOURS["Пн-Пт"]}\n"
        f"Сб: {config.WORK_HOURS["Сб"]}\n"
        f"Вс: {config.WORK_HOURS["Вс"]}\n\n"
        f"📍 <b>Адрес:</b> {config.ADRES}",
        parse_mode="HTML"
    )



@comm_router.message(F.text == "🔧 Услуги без записи")
async def show_services(message: Message):
    services = config.SERVICES.keys()  # Получаем из БД
    await message.answer(
        "Выберите услугу:",
        reply_markup=services_menu_kb(services)
    )


@comm_router.message(F.text == "↩️ Назад")
@comm_router.callback_query(F.data == "back_to_main")
async def back_to_main(update: Union[Message, CallbackQuery]):
    if isinstance(update, CallbackQuery):
        message = update.message
        await update.answer()
    else:
        message = update

    await message.answer(
        "Главное меню:",
        reply_markup=main_menu_kb()
    )
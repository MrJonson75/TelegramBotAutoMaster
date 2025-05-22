from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, FSInputFile
from keyboards.main_kb import main_menu_kb
from config.config import PHOTO_PATHS

common_router = Router()

# Обработчик команды /start
@common_router.message(Command("start"))
async def cmd_start(message: Message):
    welcome_text = (
        "Добро пожаловать в RemDiesel 🚚!\n"
        "Я помогу вам:\n"
        "- Записаться на техническое обслуживание или ремонт\n"
        "- Провести диагностику по фото\n"
        "- Просмотреть ваши записи\n"
        "- Узнать о мастере и контактах\n"
        "Выберите действие:"
    )
    await message.answer_photo(
        photo=FSInputFile(PHOTO_PATHS["welcome"]),
        caption=welcome_text,
        reply_markup=main_menu_kb()
    )

# Обработчик текстового сообщения "📞 Контакты/как проехать"
@common_router.message(F.text == "📞 Контакты/как проехать")
async def show_contacts(message: Message):
    contacts_text = (
        "📞 Свяжитесь с нами:\n"
        "Телефон: +7 (999) 123-45-67\n"
        "Email: support@remdiesel.ru\n"
        "Адрес: г. Москва, ул. Автозаводская, д. 10\n"
        "Как проехать: м. Автозаводская, 5 мин пешком"
    )
    await message.answer_photo(
        photo=FSInputFile(PHOTO_PATHS["contacts"]),
        caption=contacts_text,
        reply_markup=main_menu_kb()
    )

# Обработчик текстового сообщения "О мастере"
@common_router.message(F.text == "О мастере")
async def show_about_master(message: Message):
    about_text = (
        "🛠 Мастер Иван - эксперт по дизельным автомобилям с 15-летним опытом.\n"
        "Специализация: диагностика, ремонт двигателей, ТО.\n"
        "Посмотрите фото и видео наших работ!"
    )
    await message.answer_photo(
        photo=FSInputFile(PHOTO_PATHS["about_master"]),
        caption=about_text,
        reply_markup=main_menu_kb()
    )
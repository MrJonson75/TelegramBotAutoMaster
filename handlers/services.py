from aiogram import Router, F
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import Message, CallbackQuery, FSInputFile
from config import SERVICES, SERVICES_PHOTO, DEFAULT_PHOTO
from keyboards import services_kb, service_actions_kb
from utils.logger import logger

serv_router = Router()



@serv_router.message(F.text == "🔧 Услуги без записи")
async def show_services(message: Message):
    """Показывает список доступных услуг с изображением"""
    try:
        await message.answer_photo(
            photo=SERVICES_PHOTO,
            caption="<b>Доступные услуги:</b>",
            reply_markup=services_kb(),
            parse_mode="HTML"
        )
    except FileNotFoundError:
        logger.error("Services image not found, using default")
        await message.answer_photo(
            photo=DEFAULT_PHOTO,
            caption="<b>Доступные услуги:</b>",
            reply_markup=services_kb(),
            parse_mode="HTML"
        )


@serv_router.callback_query(F.data.startswith("service_detail:"))
async def service_detail(callback: CallbackQuery):
    """Показывает детали конкретной услуги"""
    try:
        service_name = callback.data.split(":")[1]
        service = SERVICES[service_name]

        text = (
            f"<b>{service_name}</b>\n\n"
            f"💰 Стоимость от: {service['price']} руб.\n"
            f"⏱ Время выполнения от: {service['duration']}\n"
        )

        try:
            await callback.message.edit_text(
                text,
                reply_markup=service_actions_kb(service_name),
                parse_mode="HTML"
            )
        except TelegramBadRequest:
            await callback.message.answer(
                text,
                reply_markup=service_actions_kb(service_name),
                parse_mode="HTML"
            )
    except KeyError as e:
        logger.error(f"Service not found: {e}")
        await callback.answer("Услуга временно недоступна", show_alert=True)
    finally:
        await callback.answer()


@serv_router.callback_query(F.data.startswith("service_info:"))
async def service_info(callback: CallbackQuery):
    """Показывает подробное описание услуги"""
    try:
        service_name = callback.data.split(":")[1]
        description = SERVICES[service_name]["description"]
        await callback.answer(
            f"{service_name}\n\n{description}",
            show_alert=True
        )
    except KeyError:
        await callback.answer("Описание недоступно", show_alert=True)


@serv_router.callback_query(F.data == "back_to_services")
async def back_to_services(callback: CallbackQuery):
    """Возврат к списку услуг"""
    try:
        await callback.message.answer_photo(
            photo=SERVICES_PHOTO,
            caption="<b>Доступные услуги:</b>",
            reply_markup=services_kb(),
            parse_mode="HTML"
        )
    except Exception as e:
        logger.error(f"Error showing services: {e}")
        await callback.message.answer(
            "<b>Доступные услуги:</b>",
            reply_markup=services_kb(),
            parse_mode="HTML"
        )
    finally:
        await callback.answer()


@serv_router.callback_query(F.data.startswith("service_book:"))
async def book_service(callback: CallbackQuery):
    """Обработка выбора услуги для записи"""
    service_name = callback.data.split(":")[1]

    # Логирование выбора услуги
    logger.info(f"User {callback.from_user.id} selected service: {service_name}")

    try:
        await callback.answer(
            f"Вы выбрали: {service_name}. Перенаправляем к записи...",
            show_alert=True
        )
        # Здесь будет переход к модулю записи
        # Например: await start_booking_process(callback, service_name)
    except Exception as e:
        logger.error(f"Booking error: {e}")
        await callback.answer(
            "Ошибка при обработке записи. Попробуйте позже.",
            show_alert=True
        )
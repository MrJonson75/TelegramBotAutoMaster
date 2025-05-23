from datetime import datetime
from utils import logger
from aiogram import Bot

async def on_start(bot: Bot):
    """
    Асинхронная функция, вызываемая при запуске бота.

    Логирует запуск бота и отправляет уведомление администратору (если задан).
    """
    now = datetime.now().strftime('%H:%M:%S %d/%m/%Y')
    logger.info(f"Бот запущен, ID: {bot.id}, время: {now}")

    # Опционально: отправка уведомления администратору
    from config import config
    if hasattr(config, 'ADMIN_ID'):
        try:
            await bot.send_message(config.ADMIN_ID, f"Бот запущен в {now}")
            logger.info(f"Уведомление о запуске отправлено администратору (ID: {config.ADMIN_ID})")
        except Exception as e:
            logger.error(f"Ошибка отправки уведомления администратору: {str(e)}")

async def on_shutdown(bot: Bot):
    """
    Асинхронная функция, вызываемая при остановке бота.

    Логирует остановку бота и отправляет уведомление администратору (если задан).
    """
    now = datetime.now().strftime('%H:%M:%S %d/%m/%Y')
    logger.info(f"Бот остановлен, время: {now}")

    # Опционально: отправка уведомления администратору
    from config import config
    if hasattr(config, 'ADMIN_ID'):
        try:
            await bot.send_message(config.ADMIN_ID, f"Бот остановлен в {now}")
            logger.info(f"Уведомление об остановке отправлено администратору (ID: {config.ADMIN_ID})")
        except Exception as e:
            logger.error(f"Ошибка отправки уведомления администратору: {str(e)}")
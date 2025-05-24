from aiogram import Bot
from utils import setup_logger

logger = setup_logger(__name__)

async def on_start(bot: Bot):
    """Функция, выполняемая при старте бота."""
    logger.info(f"Бот {bot.id} успешно запущен")
    # Здесь можно добавить другие действия при старте, например, отправку уведомления админу

async def on_shutdown(bot: Bot):
    """Функция, выполняемая при остановке бота."""
    logger.info(f"Бот {bot.id} останавливается")
    # Здесь можно добавить другие действия при остановке
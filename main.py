import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from config import Config
from database import init_db
from handlers import all_handlers
from utils import setup_logger

logger = setup_logger(__name__)

async def main():
    """Точка входа бота."""
    logging.basicConfig(level=logging.INFO)
    bot = Bot(token=Config.BOT_TOKEN)
    dp = Dispatcher(storage=MemoryStorage())
    dp["bot"] = bot
    Session = init_db()

    # Регистрация всех обработчиков
    dp.include_router(all_handlers)

    try:
        logger.info("Starting bot")
        await dp.start_polling(bot, session=Session)
    except Exception as e:
        logger.error(f"Bot error: {str(e)}")
    finally:
        await bot.session.close()

if __name__ == "__main__":
    asyncio.run(main())
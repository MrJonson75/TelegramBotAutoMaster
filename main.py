from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from config import Config
from handlers import all_handlers
from utils import setup_logger
from database import init_db

logger = setup_logger(__name__)

async def main():
    logger.info("Starting bot")
    bot = Bot(token=Config.BOT_TOKEN)
    dp = Dispatcher(storage=MemoryStorage())

    # Инициализация базы данных
    init_db()

    # Передаём bot в маршрутизатор
    dp["bot"] = bot

    # Подключение всех маршрутизаторов
    dp.include_router(all_handlers)

    try:
        await dp.start_polling(bot)
    except Exception as e:
        logger.error(f"Bot polling error: {str(e)}")
    finally:
        await bot.session.close()
        logger.info("Bot stopped")

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
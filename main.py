import asyncio
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from config import BOT_TOKEN
from database import init_db
from handlers import all_handlers
from utils import setup_logger, on_start, on_shutdown, start_status_updater


logger = setup_logger(__name__)

async def main():
    """Точка входа бота."""
    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher(storage=MemoryStorage())
    dp["bot"] = bot

    # Инициализация базы данных
    try:
        Session = init_db()
        dp["session"] = Session
        logger.info("База данных успешно инициализирована")
    except Exception as e:
        logger.error(f"Ошибка инициализации базы данных: {str(e)}")
        return

    # Регистрация всех обработчиков
    dp.include_router(all_handlers)
    start_status_updater()

    # Регистрация функций startup и shutdown
    dp.startup.register(on_start)
    dp.shutdown.register(on_shutdown)

    try:
        logger.info("Запуск бота")
        await dp.start_polling(bot)
    except Exception as e:
        logger.error(f"Ошибка работы бота: {str(e)}")
    finally:
        await bot.session.close()

if __name__ == "__main__":
    asyncio.run(main())
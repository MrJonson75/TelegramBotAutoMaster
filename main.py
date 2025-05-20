import asyncio
from aiogram import Bot, Dispatcher
from utils import misc
from handlers import all_handlers
import config
from utils.logger import logger, setup_logging


async def main():
    logger.info("Запуск бота")

    # Проверка конфигурации
    if not config.BOT_TOKEN:
        logger.error("TELEGRAM_TOKEN не задан в конфигурации")
        raise ValueError("TELEGRAM_TOKEN не задан")

    try:
        # Инициализация бота
        bot = Bot(token=config.BOT_TOKEN)
        logger.info("Бот инициализирован")

        # Инициализация диспетчера
        dp = Dispatcher()
        logger.info("Диспетчер инициализирован")

        # Регистрация роутеров
        dp.include_router(all_handlers)

        logger.info("Роутеры зарегистрированы")

        # Регистрация функций startup и shutdown
        dp.startup.register(misc.on_start)
        dp.shutdown.register(misc.on_shutdown)
        logger.info("Обработчики startup/shutdown зарегистрированы")

        # Удаление вебхука и пропуск апдейтов
        await bot.delete_webhook(drop_pending_updates=True)
        logger.info("Вебхук удален, апдейты пропущены")

        # Запуск polling
        logger.info("Запуск polling")
        await dp.start_polling(bot)

    except Exception as e:
        logger.error(f"Ошибка при запуске бота: {str(e)}")
        raise

if __name__ == '__main__':
    # Настройка логирования
    setup_logging()

    try:
        # Запуск основной функции
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Бот остановлен пользователем (KeyboardInterrupt)")
    except Exception as e:
        logger.error(f"Критическая ошибка: {str(e)}")
    finally:
        logger.info("Завершение работы бота")
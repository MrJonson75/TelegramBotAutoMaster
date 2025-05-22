import asyncio
from aiogram import Bot, Dispatcher
from config.config import BOT_TOKEN
from handlers.common import common_router
from handlers.photo_diagnostic import photo_diagnostic_router



async def main():
    # Инициализация бота и диспетчера
    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher()

    # Подключение роутеров
    dp.include_routers(common_router, photo_diagnostic_router)

    # Сброс существующих webhook'ов или getUpdates
    try:
        await bot.delete_webhook(drop_pending_updates=True)
        print("Webhook deleted, starting polling")
    except Exception as e:
        print(f"Failed to delete webhook: {e}")

    # Запуск polling
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
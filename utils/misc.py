from datetime import datetime
from utils.logger import logger

def on_start(bot):
    """
    Функция, вызываемая при запуске бота.

    Выводит в консоль текущие дату и время начала работы бота.
    Используется как обработчик события startup в aiogram.
    """
    logger.info(f"Бот запущен, ID: {bot.id}")
    # Получаем текущее время и форматируем его в строку
    now = datetime.now().strftime('%H:%M:%S %d/%m/%Y')
    # Выводим сообщение о запуске бота
    print(f'Bot started at {now}')


def on_shutdown():
    """
    Функция, вызываемая при остановке бота.

    Выводит в консоль текущие дату и время остановки бота.
    Используется как обработчик события shutdown в aiogram.
    """
    # Получаем текущее время и форматируем его в строку
    now = datetime.now().strftime('%H:%M:%S %d/%m/%Y')
    # Выводим сообщение об остановке бота
    print(f'Bot is down at {now}')
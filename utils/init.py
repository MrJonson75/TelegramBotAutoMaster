from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest

async def delete_previous_message(bot: Bot, chat_id: int, message_id: int):
    """
    Удаляет сообщение по его ID, игнорируя ошибки (например, если сообщение уже удалено).
    """
    try:
        await bot.delete_message(chat_id=chat_id, message_id=message_id)
    except TelegramBadRequest:
        pass  # Игнорируем, если сообщение не найдено
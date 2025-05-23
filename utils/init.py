from aiogram import Bot
import logging

logger = logging.getLogger(__name__)

async def delete_previous_message(bot: Bot, chat_id: int, message_id: int):
    """Безопасно удаляет предыдущее сообщение, если message_id действителен."""
    if message_id is None:
        logger.debug(f"Удаление сообщений пропуску: message_id не для CHAT_ID={chat_id}")
        return
    try:
        await bot.delete_message(chat_id=chat_id, message_id=message_id)
        logger.debug(f"Удаленное сообщение {message_id} в чате {chat_id}")
    except Exception as e:
        logger.warning(f"Не удалось удалить сообщение {message_id} в чате {chat_id}: {str(e)}")


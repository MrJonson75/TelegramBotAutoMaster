from aiogram.types import Message
from utils import setup_logger

logger = setup_logger(__name__)

async def delete_previous_message(message: Message) -> bool:
    """Удаляет предыдущее сообщение бота в чате."""
    try:
        # Пытаемся удалить сообщение с ID на единицу меньше текущего
        await message.bot.delete_message(
            chat_id=message.chat.id,
            message_id=message.message_id - 1
        )
        logger.debug(f"Удалено предыдущее сообщение в чате {message.chat.id}")
        return True
    except Exception as e:
        logger.debug(f"Не удалось удалить предыдущее сообщение: {str(e)}")
        return False
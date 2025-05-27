import asyncio
from aiogram import Bot
from datetime import datetime
import pytz
from utils import setup_logger

logger = setup_logger(__name__)

MSK = pytz.timezone('Europe/Moscow')

def to_msk(dt: datetime) -> datetime:
    """Конвертирует datetime в MSK, добавляя часовой пояс, если его нет."""
    if dt.tzinfo is None:
        return MSK.localize(dt)
    return dt.astimezone(MSK)

class ReminderManager:
    def __init__(self):
        self.reminders = {}

    async def schedule(self, bot: Bot, booking_id: int, reminder_time: datetime, chat_id: str, message: str):
        """Планирует напоминание о бронировании."""
        try:
            now = self.get_msk_time()
            reminder_time = to_msk(reminder_time)
            delay = (reminder_time - now).total_seconds()
            if delay <= 0:
                logger.info(f"Напоминание о booking_id={booking_id} в прошлом, пропустить")
                return
            self.reminders[booking_id] = asyncio.create_task(
                self._send_reminder(bot, booking_id, delay, chat_id, message)
            )
            logger.info(f"Запланированное напоминание для booking_id={booking_id} at {reminder_time}")
        except Exception as e:
            logger.error(f"Напоминание о планировании ошибок для booking_id={booking_id}: {str(e)}")

    async def _send_reminder(self, bot: Bot, booking_id: int, delay: float, chat_id: str, message: str):
        """Отправляет напоминание после указанной задержки."""
        try:
            await asyncio.sleep(delay)
            from database import Session, Booking, BookingStatus
            with Session() as session:
                booking = session.query(Booking).get(booking_id)
                if booking and booking.status == BookingStatus.CONFIRMED:
                    await bot.send_message(chat_id=chat_id, text=message, parse_mode="HTML")
                    logger.info(f"Послал напоминание для booking_id={booking_id} до chat_id={chat_id}")
                else:
                    logger.info(f"Напоминание о booking_id={booking_id} Пропущен: бронирование не подтверждено")
            del self.reminders[booking_id]
        except Exception as e:
            logger.error(f"Ошибка отправки напоминания для booking_id={booking_id}: {str(e)}")

    def cancel(self, booking_id: int):
        """Отменяет напоминание о бронировании."""
        try:
            task = self.reminders.get(booking_id)
            if task:
                task.cancel()
                del self.reminders[booking_id]
                logger.info(f"Отменено напоминание для booking_id={booking_id}")
        except Exception as e:
            logger.error(f"Ошибка отмены напоминания для booking_id={booking_id}: {str(e)}")

    def get_msk_time(self):
        """Возвращает текущее время в MSK."""
        return datetime.now(MSK)

reminder_manager = ReminderManager()
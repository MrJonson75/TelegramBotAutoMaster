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
        """Schedules a reminder for a booking."""
        try:
            now = self.get_msk_time()
            reminder_time = to_msk(reminder_time)
            delay = (reminder_time - now).total_seconds()
            if delay <= 0:
                logger.info(f"Reminder for booking_id={booking_id} is in the past, skipping")
                return
            self.reminders[booking_id] = asyncio.create_task(
                self._send_reminder(bot, booking_id, delay, chat_id, message)
            )
            logger.info(f"Scheduled reminder for booking_id={booking_id} at {reminder_time}")
        except Exception as e:
            logger.error(f"Error scheduling reminder for booking_id={booking_id}: {str(e)}")

    async def _send_reminder(self, bot: Bot, booking_id: int, delay: float, chat_id: str, message: str):
        """Sends a reminder after the specified delay."""
        try:
            await asyncio.sleep(delay)
            from database import Session, Booking, BookingStatus
            with Session() as session:
                booking = session.query(Booking).get(booking_id)
                if booking and booking.status == BookingStatus.CONFIRMED:
                    await bot.send_message(chat_id=chat_id, text=message, parse_mode="HTML")
                    logger.info(f"Sent reminder for booking_id={booking_id} to chat_id={chat_id}")
                else:
                    logger.info(f"Reminder for booking_id={booking_id} skipped: booking not confirmed")
            del self.reminders[booking_id]
        except Exception as e:
            logger.error(f"Error sending reminder for booking_id={booking_id}: {str(e)}")

    def cancel(self, booking_id: int):
        """Cancels a reminder for a booking."""
        try:
            task = self.reminders.get(booking_id)
            if task:
                task.cancel()
                del self.reminders[booking_id]
                logger.info(f"Cancelled reminder for booking_id={booking_id}")
        except Exception as e:
            logger.error(f"Error cancelling reminder for booking_id={booking_id}: {str(e)}")

    def get_msk_time(self):
        """Возвращает текущее время в MSK."""
        return datetime.now(MSK)

reminder_manager = ReminderManager()
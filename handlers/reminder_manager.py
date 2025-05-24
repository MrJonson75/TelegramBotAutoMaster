import asyncio
from aiogram import Bot
from datetime import datetime
from utils import setup_logger

logger = setup_logger(__name__)

class ReminderManager:
    def __init__(self):
        self.reminders = {}

    async def schedule(self, bot: Bot, booking_id: int, reminder_time: datetime, chat_id: str, message: str):
        """Schedules a reminder for a booking."""
        try:
            now = datetime.utcnow()
            delay = (reminder_time - now).total_seconds()
            if delay <= 0:
                logger.info(f"Reminder for booking_id={booking_id} is in the past, skipping")
                return
            self.reminders[booking_id] = asyncio.create_task(self._send_reminder(bot, booking_id, delay, chat_id, message))
            logger.info(f"Scheduled reminder for booking_id={booking_id} at {reminder_time}")
        except Exception as e:
            logger.error(f"Error scheduling reminder for booking_id={booking_id}: {str(e)}")

    async def _send_reminder(self, bot: Bot, booking_id: int, delay: float, chat_id: str, message: str):
        """Sends a reminder after the specified delay."""
        try:
            await asyncio.sleep(delay)
            await bot.send_message(chat_id=chat_id, text=message, parse_mode="HTML")
            logger.info(f"Sent reminder for booking_id={booking_id} to chat_id={chat_id}")
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

reminder_manager = ReminderManager()
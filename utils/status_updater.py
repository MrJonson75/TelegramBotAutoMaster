import asyncio
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from database import Booking, BookingStatus, Session as DBSession
from config import SERVICES
from utils import setup_logger

logger = setup_logger(__name__)

async def update_booking_statuses():
    """Фоновая задача для обновления статуса записей на COMPLETED."""
    while True:
        try:
            with DBSession() as session:
                bookings = session.query(Booking).filter(
                    Booking.status == BookingStatus.CONFIRMED
                ).all()
                current_time = datetime.now()
                for booking in bookings:
                    booking_datetime = datetime.combine(booking.date, booking.time)
                    service = next((s for s in SERVICES if s["name"] == booking.service_name), None)
                    duration = service["duration_minutes"] if service else 60  # По умолчанию 60 минут для "Ремонт"
                    end_time = booking_datetime + timedelta(minutes=duration)
                    if current_time >= end_time:
                        booking.status = BookingStatus.COMPLETED
                        logger.info(f"Запись #{booking.id} обновлена до статуса COMPLETED")
                session.commit()
        except Exception as e:
            logger.error(f"Ошибка обновления статусов записей: {str(e)}")
        await asyncio.sleep(300)  # Проверка каждые 5 минут

def start_status_updater():
    """Запускает фоновую задачу обновления статусов."""
    asyncio.create_task(update_booking_statuses())
import os
from sqlalchemy import create_engine, Column, Integer, String, ForeignKey, Enum, Date, Time, Text, DateTime, inspect
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from sqlalchemy.sql import text
import enum
from datetime import datetime
from utils import setup_logger

logger = setup_logger(__name__)

Base = declarative_base()

class BookingStatus(enum.Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    REJECTED = "rejected"
    CANCELLED = "cancelled"  # Добавляем новый статус

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    first_name = Column(String, nullable=False)
    last_name = Column(String, nullable=False)
    phone = Column(String, nullable=False)
    telegram_id = Column(String, unique=True, nullable=False)
    autos = relationship("Auto", back_populates="user")
    bookings = relationship("Booking", back_populates="user")

class Auto(Base):
    __tablename__ = "auto"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    brand = Column(String, nullable=False)
    year = Column(Integer, nullable=False)
    vin = Column(String, nullable=False)
    license_plate = Column(String, nullable=False)
    user = relationship("User", back_populates="autos")
    bookings = relationship("Booking", back_populates="auto")

class Booking(Base):
    __tablename__ = 'bookings'
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    auto_id = Column(Integer, ForeignKey('auto.id'), nullable=False)
    service_name = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    date = Column(Date, nullable=False)
    time = Column(Time, nullable=False)
    proposed_time = Column(Time, nullable=True)
    status = Column(Enum(BookingStatus), default=BookingStatus.PENDING, nullable=False)
    rejection_reason = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    price = Column(Integer, nullable=True)
    user = relationship("User", back_populates="bookings")
    auto = relationship("Auto", back_populates="bookings")

engine = create_engine("sqlite:///RemDiesel.db", echo=False)
Session = sessionmaker(bind=engine)

def init_db():
    """Инициализирует базу данных, создавая таблицы и применяя миграции."""
    Base.metadata.create_all(engine)
    inspector = inspect(engine)
    columns = [col['name'] for col in inspector.get_columns('bookings')]
    with engine.connect() as conn:
        if 'description' not in columns:
            try:
                conn.execute(text("ALTER TABLE bookings ADD COLUMN description TEXT;"))
                conn.commit()
                logger.info("Added description column to bookings table")
            except Exception as e:
                logger.error(f"Ошибка добавления столбца description: {str(e)}")
        if 'rejection_reason' not in columns:
            try:
                conn.execute(text("ALTER TABLE bookings ADD COLUMN rejection_reason TEXT;"))
                conn.commit()
                logger.info("Added rejection_reason column to bookings table")
            except Exception as e:
                logger.error(f"Ошибка добавления столбца rejection_reason: {str(e)}")
    return Session
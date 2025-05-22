from sqlalchemy import create_engine, Column, Integer, String, ForeignKey, Date, Time, Enum, DateTime
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
import enum
import os
from datetime import datetime

Base = declarative_base()

class BookingStatus(enum.Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    REJECTED = "rejected"

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
    __tablename__ = "bookings"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    auto_id = Column(Integer, ForeignKey("auto.id"), nullable=False)
    service_name = Column(String, nullable=False)
    date = Column(Date, nullable=False)
    time = Column(Time, nullable=False)
    status = Column(Enum(BookingStatus), default=BookingStatus.PENDING, nullable=False)
    rejection_reason = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)
    user = relationship("User", back_populates="bookings")
    auto = relationship("Auto", back_populates="bookings")

def init_db():
    """Инициализирует базу данных, создавая таблицы, если они не существуют."""
    db_path = "sqlite:///autoshop.db"
    if not os.path.exists("autoshop.db"):
        engine = create_engine(db_path, echo=False)
        Base.metadata.create_all(engine)
    else:
        engine = create_engine(db_path, echo=False)
    Session = sessionmaker(bind=engine)
    return Session
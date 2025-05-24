from sqlalchemy import Column, Integer, String, ForeignKey, Date, Time, Enum, create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
import enum


Base = declarative_base()

class BookingStatus(enum.Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    REJECTED = "rejected"
    CANCELLED = "cancelled"

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    telegram_id = Column(String, unique=True, nullable=False)
    first_name = Column(String, nullable=False)
    last_name = Column(String, nullable=True)  # Опционально
    phone = Column(String, nullable=True)  # Опционально
    username = Column(String, nullable=True)  # Опционально
    birth_date = Column(Date, nullable=True)  # Опционально
    autos = relationship("Auto", back_populates="user")
    bookings = relationship("Booking", back_populates="user")

class Auto(Base):
    __tablename__ = "autos"
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
    auto_id = Column(Integer, ForeignKey("autos.id"), nullable=False)
    service_name = Column(String, nullable=False)
    date = Column(Date, nullable=False)
    time = Column(Time, nullable=False)
    status = Column(Enum(BookingStatus), default=BookingStatus.PENDING, nullable=False)
    rejection_reason = Column(String, nullable=True)
    user = relationship("User", back_populates="bookings")
    auto = relationship("Auto", back_populates="bookings")

engine = create_engine("sqlite:///RemDiesel.db")
Base.metadata.create_all(engine)
Session = sessionmaker(bind=engine)

def init_db():
    Base.metadata.create_all(engine)
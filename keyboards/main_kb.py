from aiogram.utils.keyboard import ReplyKeyboardBuilder
from aiogram.types import ReplyKeyboardMarkup, InlineKeyboardMarkup, InlineKeyboardButton
from config import Config
from database import Booking, BookingStatus
from datetime import datetime, timedelta, time
from sqlalchemy.orm import Session


class Keyboards:
    """Класс для управления клавиатурами бота."""

    @staticmethod
    def main_menu_kb() -> ReplyKeyboardMarkup:
        """Создаёт главное меню."""
        builder = ReplyKeyboardBuilder()
        builder.button(text="📞 Контакты/как проехать")
        builder.button(text="Запись на ТО")
        builder.button(text="Запись на ремонт")
        builder.button(text="Быстрый ответ - Диагностика по фото")
        builder.button(text="Мои записи")
        builder.button(text="О мастере")
        builder.adjust(2)
        return builder.as_markup(resize_keyboard=True)

    @staticmethod
    def diagnostic_choice_kb() -> InlineKeyboardMarkup:
        """Создаёт инлайн-клавиатуру для выбора варианта диагностики."""
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Описать текстом", callback_data="text_diagnostic")],
            [InlineKeyboardButton(text="Загрузить фото", callback_data="start_photo_diagnostic")]
        ])

    @staticmethod
    def photo_upload_kb() -> InlineKeyboardMarkup:
        """Создаёт инлайн-клавиатуру для завершения загрузки фото."""
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Готово", callback_data="photos_ready")]
        ])

    @staticmethod
    def auto_selection_kb(autos: list) -> InlineKeyboardMarkup:
        """Создаёт инлайн-клавиатуру для выбора автомобиля."""
        keyboard = []
        for auto in autos:
            text = f"{auto.brand} {auto.year} {auto.license_plate}"
            keyboard.append([InlineKeyboardButton(text=text, callback_data=f"auto_{auto.id}")])
        keyboard.append([InlineKeyboardButton(text="Добавить новый автомобиль", callback_data="add_new_auto")])
        return InlineKeyboardMarkup(inline_keyboard=keyboard)

    @staticmethod
    def services_kb() -> InlineKeyboardMarkup:
        """Создаёт инлайн-клавиатуру с перечнем услуг."""
        keyboard = []
        for service in Config.SERVICES:
            keyboard.append([InlineKeyboardButton(text=service["name"], callback_data=f"service_{service['name']}")])
        return InlineKeyboardMarkup(inline_keyboard=keyboard)

    @staticmethod
    def add_another_auto_kb() -> InlineKeyboardMarkup:
        """Создаёт инлайн-клавиатуру для добавления ещё одного автомобиля."""
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Добавить ещё авто", callback_data="add_another_auto")],
            [InlineKeyboardButton(text="Продолжить", callback_data="continue_booking")]
        ])

    @staticmethod
    def calendar_kb(selected_date: datetime = None) -> InlineKeyboardMarkup:
        """Создаёт инлайн-клавиатуру с доступными датами (30 дней вперёд)."""
        today = datetime.today()
        keyboard = []
        for i in range(30):
            date = today + timedelta(days=i)
            if date.strftime("%A") in Config.WORKING_HOURS["weekends"]:
                continue
            callback_data = f"date_{date.strftime('%Y-%m-%d')}"
            text = date.strftime("%d.%m.%Y (%A)")
            if selected_date and selected_date.date() == date.date():
                text = f"✅ {text}"
            keyboard.append([InlineKeyboardButton(text=text, callback_data=callback_data)])
        return InlineKeyboardMarkup(inline_keyboard=keyboard)

    @staticmethod
    def time_slots_kb(date: datetime, service_duration: int, session: Session) -> InlineKeyboardMarkup:
        """Создаёт инлайн-клавиатуру с доступными временными слотами."""
        start_hour = int(Config.WORKING_HOURS["start"].split(":")[0])
        end_hour = int(Config.WORKING_HOURS["end"].split(":")[0])
        keyboard = []

        # Получаем существующие записи на выбранную дату
        existing_bookings = session.query(Booking).filter(
            Booking.date == date.date(),
            Booking.status != BookingStatus.REJECTED
        ).all()
        booked_times = [(b.time.hour, b.time.hour + (
                    b.time.minute + Config.SERVICES[[s["name"] for s in Config.SERVICES].index(b.service_name)][
                "duration_minutes"]) // 60) for b in existing_bookings]

        current_time = time(hour=start_hour)
        while current_time.hour < end_hour:
            slot_end_hour = current_time.hour + (service_duration // 60)
            slot_end_minutes = current_time.minute + (service_duration % 60)
            if slot_end_minutes >= 60:
                slot_end_hour += 1
                slot_end_minutes -= 60
            if slot_end_hour > end_hour or (slot_end_hour == end_hour and slot_end_minutes > 0):
                break
            is_booked = False
            for start, end in booked_times:
                if current_time.hour >= start and current_time.hour < end:
                    is_booked = True
                    break
            if not is_booked:
                callback_data = f"time_{current_time.strftime('%H:%M')}"
                keyboard.append([InlineKeyboardButton(text=current_time.strftime('%H:%M'), callback_data=callback_data)])
            current_time = (datetime.combine(datetime.today(), current_time) + timedelta(minutes=30)).time()

        return InlineKeyboardMarkup(inline_keyboard=keyboard)

    @staticmethod
    def bookings_kb(bookings: list) -> InlineKeyboardMarkup:
        """Создаёт инлайн-клавиатуру со списком записей."""
        keyboard = []
        for booking in bookings:
            auto = booking.auto
            status = {
                BookingStatus.PENDING: "⏳ Ожидает",
                BookingStatus.CONFIRMED: "✅ Подтверждено",
                BookingStatus.REJECTED: "❌ Отклонено"
            }[booking.status]
            text = (
                f"{booking.service_name} | {booking.date.strftime('%d.%m.%Y')} {booking.time.strftime('%H:%M')} | "
                f"{auto.brand} {auto.license_plate} | {status}"
            )
            buttons = []
            if booking.status in [BookingStatus.PENDING, BookingStatus.CONFIRMED]:
                buttons.append(InlineKeyboardButton(text="Отменить", callback_data=f"cancel_booking_{booking.id}"))
            keyboard.append([InlineKeyboardButton(text=text, callback_data=f"view_booking_{booking.id}")])
            if buttons:
                keyboard.append(buttons)
        return InlineKeyboardMarkup(inline_keyboard=keyboard)
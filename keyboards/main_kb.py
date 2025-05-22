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
    def calendar_kb(selected_date: datetime = None, week_offset: int = 0) -> InlineKeyboardMarkup:
        """Создаёт инлайн-клавиатуру с доступными датами (7 дней)."""
        today = datetime.today()
        start_date = today + timedelta(days=week_offset * 7)
        keyboard = []
        valid_dates = []

        # Собираем 7 рабочих дней
        current_date = start_date
        while len(valid_dates) < 7:
            if current_date.strftime("%A") not in Config.WORKING_HOURS["weekends"]:
                valid_dates.append(current_date)
            current_date += timedelta(days=1)
            if (current_date - start_date).days > 30:  # Ограничение на 30 дней вперёд
                break

        for date in valid_dates:
            callback_data = f"date_{date.strftime('%Y-%m-%d')}"
            text = date.strftime("%d.%m (%a)")
            if selected_date and selected_date.date() == date.date():
                text = f"✅ {text}"
            keyboard.append([InlineKeyboardButton(text=text, callback_data=callback_data)])

        # Кнопки навигации
        nav_buttons = []
        if week_offset > 0:
            nav_buttons.append(InlineKeyboardButton(text="⬅ Назад", callback_data=f"prev_week_{week_offset - 1}"))
        if today <= valid_dates[-1] < today + timedelta(days=30):
            nav_buttons.append(InlineKeyboardButton(text="Вперёд ➡", callback_data=f"next_week_{week_offset + 1}"))
        if start_date.date() != today.date():
            nav_buttons.append(InlineKeyboardButton(text="Сегодня", callback_data="today"))
        if nav_buttons:
            keyboard.append(nav_buttons)

        return InlineKeyboardMarkup(inline_keyboard=keyboard)

    @staticmethod
    def time_slots_kb(date: datetime, service_duration: int, session: Session,
                      time_offset: int = 0) -> InlineKeyboardMarkup:
        """Создаёт инлайн-клавиатуру с доступными временными слотами (шаг 1 час, до 6 слотов)."""
        start_hour = int(Config.WORKING_HOURS["start"].split(":")[0])
        end_hour = int(Config.WORKING_HOURS["end"].split(":")[0])
        keyboard = []
        valid_slots = []

        # Получаем существующие записи на выбранную дату
        existing_bookings = session.query(Booking).filter(
            Booking.date == date.date(),
            Booking.status != BookingStatus.REJECTED
        ).all()
        booked_times = [(b.time.hour, b.time.hour + (
                b.time.minute + Config.SERVICES[[s["name"] for s in Config.SERVICES].index(b.service_name)][
            "duration_minutes"]) // 60) for b in existing_bookings]

        # Собираем доступные слоты с шагом 1 час
        current_hour = start_hour
        while current_hour < end_hour:
            slot_end_hour = current_hour + (service_duration // 60)
            slot_end_minutes = (service_duration % 60)
            if slot_end_minutes >= 60:
                slot_end_hour += 1
                slot_end_minutes -= 60
            if slot_end_hour > end_hour or (slot_end_hour == end_hour and slot_end_minutes > 0):
                break
            is_booked = False
            for start, end in booked_times:
                if current_hour >= start and current_hour < end:
                    is_booked = True
                    break
            if not is_booked:
                valid_slots.append(time(hour=current_hour))
            current_hour += 1

        # Ограничиваем до 6 слотов за раз
        start_index = time_offset * 6
        display_slots = valid_slots[start_index:start_index + 6]

        for slot in display_slots:
            callback_data = f"time_{slot.strftime('%H:%M')}"
            keyboard.append([InlineKeyboardButton(text=slot.strftime("%H:%M"), callback_data=callback_data)])

        # Кнопки навигации
        nav_buttons = []
        if start_index > 0:
            nav_buttons.append(InlineKeyboardButton(text="⬅ Ранее", callback_data=f"prev_slots_{time_offset - 1}"))
        if start_index + 6 < len(valid_slots):
            nav_buttons.append(InlineKeyboardButton(text="Позже ➡", callback_data=f"next_slots_{time_offset + 1}"))
        if nav_buttons:
            keyboard.append(nav_buttons)

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

    @staticmethod
    def confirm_reschedule_kb(booking_id: int) -> InlineKeyboardMarkup:
        """Клавиатура для подтверждения/отклонения нового времени пользователем."""
        keyboard = [
            [InlineKeyboardButton(text="Подтвердить", callback_data=f"confirm_reschedule_{booking_id}")],
            [InlineKeyboardButton(text="Отклонить", callback_data=f"reject_reschedule_{booking_id}")]
        ]
        return InlineKeyboardMarkup(inline_keyboard=keyboard)
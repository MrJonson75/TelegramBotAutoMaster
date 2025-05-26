from aiogram.utils.keyboard import ReplyKeyboardBuilder
from aiogram.types import ReplyKeyboardMarkup, InlineKeyboardMarkup, InlineKeyboardButton
from config import SERVICES, WORKING_HOURS
from database import Booking, BookingStatus
from datetime import datetime, timedelta, time
from sqlalchemy.orm import Session
from utils import setup_logger

logger = setup_logger(__name__)

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
        builder.button(text="Личный кабинет 👤")
        builder.button(text="О мастере")
        builder.adjust(2)
        return builder.as_markup(resize_keyboard=True)

    @staticmethod
    def profile_menu_kb() -> InlineKeyboardMarkup:
        """Создаёт меню личного кабинета."""
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Редактировать данные 👤", callback_data="edit_profile")],
            [InlineKeyboardButton(text="Мои автомобили 🚗", callback_data="manage_autos")],
            [InlineKeyboardButton(text="Мои записи 📜", callback_data="my_bookings")],
            [InlineKeyboardButton(text="История записей 📜", callback_data="booking_history")],
            [InlineKeyboardButton(text="Назад ⬅", callback_data="back_to_main")]
        ])

    @staticmethod
    def diagnostic_choice_kb() -> InlineKeyboardMarkup:
        """Создаёт инлайн-клавиатуру для выбора варианта диагностики."""
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Описать текстом", callback_data="text_diagnostic")],
            [InlineKeyboardButton(text="Загрузить фото", callback_data="start_photo_diagnostic")]
        ])

    @staticmethod
    def photo_upload_kb() -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Готово", callback_data="photos_ready")],
            [InlineKeyboardButton(text="⏭ Пропустить", callback_data="skip_photos")]
        ])

    @staticmethod
    def auto_selection_kb(autos: list) -> InlineKeyboardMarkup:
        """Создаёт инлайн-клавиатуру для выбора автомобиля."""
        keyboard = []
        for auto in autos:
            text = f"{auto.brand} {auto.year} {auto.license_plate}"
            keyboard.append([InlineKeyboardButton(text=text, callback_data=f"auto_{auto.id}")])
        keyboard.append([InlineKeyboardButton(text="Назад ⬅", callback_data="back_to_main")])
        return InlineKeyboardMarkup(inline_keyboard=keyboard)

    @staticmethod
    def auto_management_kb(autos: list) -> InlineKeyboardMarkup:
        """Создаёт инлайн-клавиатуру для управления автомобилями."""
        keyboard = []
        for auto in autos:
            text = f"{auto.brand} {auto.year} {auto.license_plate}"
            keyboard.append([InlineKeyboardButton(text=text, callback_data=f"view_auto_{auto.id}")])
            keyboard.append([InlineKeyboardButton(text=f"Удалить {auto.brand}", callback_data=f"delete_auto_{auto.id}")])
        keyboard.append([InlineKeyboardButton(text="Добавить автомобиль 🚗", callback_data="add_auto")])
        keyboard.append([InlineKeyboardButton(text="Назад ⬅", callback_data="back_to_profile")])
        return InlineKeyboardMarkup(inline_keyboard=keyboard)

    @staticmethod
    def services_kb() -> InlineKeyboardMarkup:
        """Создаёт инлайн-клавиатуру с перечнем услуг."""
        keyboard = []
        for service in SERVICES:
            text = f"{service['name']} ({service['price']} ₽)"
            keyboard.append([InlineKeyboardButton(text=text, callback_data=f"service_{service['name']}")])
        return InlineKeyboardMarkup(inline_keyboard=keyboard)

    @staticmethod
    def continue_without_photos_kb() -> InlineKeyboardMarkup:
        """Создаёт клавиатуру для продолжения без фотографий."""
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Продолжить без фото 📷", callback_data="continue_without_photos")],
            [InlineKeyboardButton(text="Отменить ❌", callback_data="cancel")]
        ])

    @staticmethod
    def calendar_kb(selected_date: datetime = None, week_offset: int = 0) -> InlineKeyboardMarkup:
        """Создаёт инлайн-клавиатуру с доступными датами (7 рабочих дней, на русском)."""
        today = datetime.today()
        start_date = today + timedelta(days=week_offset * 7)
        keyboard = []
        valid_dates = []

        day_names = {
            "Monday": "Понедельник",
            "Tuesday": "Вторник",
            "Wednesday": "Среда",
            "Thursday": "Четверг",
            "Friday": "Пятница",
            "Saturday": "Суббота",
            "Sunday": "Воскресенье"
        }
        day_emojis = {
            "Monday": "🟦",
            "Tuesday": "🟩",
            "Wednesday": "🟨",
            "Thursday": "🟧",
            "Friday": "🟪",
            "Saturday": "🔴",
            "Sunday": "⚪"
        }

        current_date = start_date
        while len(valid_dates) < 7:
            if current_date.strftime("%A") not in WORKING_HOURS["weekends"]:
                valid_dates.append(current_date)
            current_date += timedelta(days=1)
            if (current_date - start_date).days > 30:
                break

        for i in range(0, len(valid_dates), 2):
            row = []
            for date in valid_dates[i:i+2]:
                day_name = day_names[date.strftime("%A")]
                emoji = day_emojis[date.strftime("%A")]
                callback_data = f"date_{date.strftime('%Y-%m-%d')}"
                text = f"{emoji} {date.strftime('%d.%m')} {day_name}"
                if selected_date and selected_date.date() == date.date():
                    text = f"✅ {text}"
                row.append(InlineKeyboardButton(text=text, callback_data=callback_data))
            keyboard.append(row)

        nav_buttons = []
        if week_offset > 0:
            nav_buttons.append(InlineKeyboardButton(text="⬅ Назад", callback_data=f"prev_week_{week_offset - 1}"))
        if today <= valid_dates[-1] < today + timedelta(days=30):
            nav_buttons.append(InlineKeyboardButton(text="Вперёд ➡", callback_data=f"next_week_{week_offset + 1}"))
        if start_date.date() != today.date():
            nav_buttons.append(InlineKeyboardButton(text="📅 Сегодня", callback_data="today"))
        nav_buttons.append(InlineKeyboardButton(text="🚫 Отмена", callback_data="cancel"))
        keyboard.append(nav_buttons)

        return InlineKeyboardMarkup(inline_keyboard=keyboard)

    @staticmethod
    def time_slots_kb(date: datetime, service_duration: int, session: Session,
                      time_offset: int = 0) -> InlineKeyboardMarkup:
        """Создаёт инлайн-клавиатуру с доступными временными слотами."""
        start_hour = int(WORKING_HOURS["start"].split(":")[0])
        start_minute = int(WORKING_HOURS["start"].split(":")[1])
        end_hour = int(WORKING_HOURS["end"].split(":")[0])
        end_minute = int(WORKING_HOURS["end"].split(":")[1])
        keyboard = []
        valid_slots = []

        existing_bookings = session.query(Booking).filter(
            Booking.date == date.date(),
            Booking.status != BookingStatus.REJECTED
        ).all()
        booked_slots = []
        for b in existing_bookings:
            start_time = b.time
            duration = SERVICES[[s["name"] for s in SERVICES].index(b.service_name)]["duration_minutes"] if b.service_name != "Ремонт" else 60
            end_time = (datetime.combine(date.today(), start_time) + timedelta(minutes=duration)).time()
            booked_slots.append((start_time, end_time))

        current_time = datetime.combine(date.today(), time(hour=start_hour, minute=start_minute))
        end_time = datetime.combine(date.today(), time(hour=end_hour, minute=end_minute))
        while current_time < end_time:
            slot_end = current_time + timedelta(minutes=service_duration)
            if slot_end > end_time:
                break
            is_booked = False
            for booked_start, booked_end in booked_slots:
                booked_start_dt = datetime.combine(date.today(), booked_start)
                booked_end_dt = datetime.combine(date.today(), booked_end)
                if (current_time < booked_end_dt and slot_end > booked_start_dt):
                    is_booked = True
                    break
            if not is_booked:
                valid_slots.append(current_time.time())
            current_time += timedelta(minutes=30)

        start_index = time_offset * 6
        display_slots = valid_slots[start_index:start_index + 6]

        for i in range(0, len(display_slots), 2):
            row = []
            for slot in display_slots[i:i+2]:
                callback_data = f"time_{slot.strftime('%H:%M')}"
                text = f"🕒 {slot.strftime('%H:%M')} ({service_duration} мин)"
                row.append(InlineKeyboardButton(text=text, callback_data=callback_data))
            keyboard.append(row)

        nav_buttons = []
        if start_index > 0:
            nav_buttons.append(InlineKeyboardButton(text="⏪ Ранее", callback_data=f"prev_slots_{time_offset - 1}"))
        if start_index + 6 < len(valid_slots):
            nav_buttons.append(InlineKeyboardButton(text="Позже ⏩", callback_data=f"next_slots_{time_offset + 1}"))
        nav_buttons.append(InlineKeyboardButton(text="🚫 Отмена", callback_data="cancel"))
        if nav_buttons:
            keyboard.append(nav_buttons)

        return InlineKeyboardMarkup(inline_keyboard=keyboard)

    @staticmethod
    def bookings_kb(bookings: list) -> InlineKeyboardMarkup:
        """Создаёт инлайн-клавиатуру со списком записей."""
        keyboard = []
        for booking in bookings:
            auto = booking.auto
            status_map = {
                BookingStatus.PENDING: "⏳ Ожидает",
                BookingStatus.CONFIRMED: "✅ Подтверждено",
                BookingStatus.REJECTED: "❌ Отклонено"
            }
            status = status_map.get(booking.status, "Неизвестно")
            text = (
                f"#{booking.id} {booking.service_name} | {booking.date.strftime('%d.%m.%Y')} "
                f"{booking.time.strftime('%H:%M')} | {auto.brand} {auto.license_plate} | {status}"
            )
            buttons = []
            if booking.status in [BookingStatus.PENDING, BookingStatus.CONFIRMED]:
                buttons.append(InlineKeyboardButton(text="Отменить ❌", callback_data=f"cancel_booking_{booking.id}"))
            keyboard.append([InlineKeyboardButton(text=text, callback_data=f"view_booking_{booking.id}")])
            if buttons:
                keyboard.append(buttons)
        keyboard.append([InlineKeyboardButton(text="Назад ⬅", callback_data="back_to_profile")])
        return InlineKeyboardMarkup(inline_keyboard=keyboard)

    @staticmethod
    def confirm_reschedule_kb(booking_id: int) -> InlineKeyboardMarkup:
        """Клавиатура для подтверждения/отклонения нового времени."""
        keyboard = [
            [InlineKeyboardButton(text="Подтвердить", callback_data=f"confirm_reschedule_{booking_id}")],
            [InlineKeyboardButton(text="Отклонить", callback_data=f"reject_reschedule_{booking_id}")]
        ]
        return InlineKeyboardMarkup(inline_keyboard=keyboard)

    @staticmethod
    def admin_pagination_kb(page: int, total_bookings: int) -> InlineKeyboardMarkup:
        """Создаёт инлайн-клавиатуру для пагинации админ-панели."""
        navigation_rows = []
        if page > 0:
            navigation_rows.append(InlineKeyboardButton(text="⬅ Предыдущая", callback_data=f"admin_page_{page-1}"))
        if total_bookings > (page + 1) * 5:
            navigation_rows.append(InlineKeyboardButton(text="Следующая ➡", callback_data=f"admin_page_{page+1}"))
        if navigation_rows:
            return InlineKeyboardMarkup(inline_keyboard=[navigation_rows])
        return None

    @staticmethod
    def cancel_kb():
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Отменить ❌", callback_data="cancel")]
        ])

    @staticmethod
    def bookings_history_kb(bookings: list, page: int = 0, bookings_per_page: int = 5) -> InlineKeyboardMarkup:
        """Создаёт инлайн-клавиатуру для истории записей с пагинацией."""
        keyboard = []
        start_idx = page * bookings_per_page
        end_idx = min(start_idx + bookings_per_page, len(bookings))
        for booking in bookings[start_idx:end_idx]:
            auto = booking.auto
            status_map = {
                BookingStatus.PENDING: "⏳ Ожидает",
                BookingStatus.CONFIRMED: "✅ Подтверждено",
                BookingStatus.REJECTED: "❌ Отклонено",
                BookingStatus.CANCELLED: "🚫 Отменено",
                BookingStatus.COMPLETED: "✅ Выполнено"
            }
            status = status_map.get(booking.status, "Неизвестно")
            text = (
                f"#{booking.id} {booking.service_name} | {booking.date.strftime('%d.%m.%Y')} "
                f"{booking.time.strftime('%H:%M')} | {auto.brand} {auto.license_plate} | {status}"
            )
            keyboard.append([InlineKeyboardButton(text=text, callback_data=f"view_booking_{booking.id}")])
            buttons = []
            if booking.status == BookingStatus.COMPLETED and not booking.review:
                buttons.append(
                    InlineKeyboardButton(text="Оставить отзыв ⭐", callback_data=f"leave_review_{booking.id}"))
            if booking.status in [BookingStatus.REJECTED, BookingStatus.CANCELLED]:
                buttons.append(InlineKeyboardButton(text="Удалить 🗑", callback_data=f"delete_booking_{booking.id}"))
            if buttons:
                keyboard.append(buttons)

        # Кнопки пагинации
        nav_buttons = []
        if page > 0:
            nav_buttons.append(InlineKeyboardButton(text="⬅ Назад", callback_data=f"history_page_{page - 1}"))
        if end_idx < len(bookings):
            nav_buttons.append(InlineKeyboardButton(text="Вперёд ➡", callback_data=f"history_page_{page + 1}"))
        nav_buttons.append(InlineKeyboardButton(text="Назад в профиль ⬅", callback_data="back_to_profile"))
        if nav_buttons:
            keyboard.append(nav_buttons)

        return InlineKeyboardMarkup(inline_keyboard=keyboard)
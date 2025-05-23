from aiogram.utils.keyboard import ReplyKeyboardBuilder
from aiogram.types import ReplyKeyboardMarkup, InlineKeyboardMarkup, InlineKeyboardButton
from config import Config
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
        builder.button(text="Мои записи")
        builder.button(text="История записей")
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
        keyboard.append([InlineKeyboardButton(text="Добавить новый автомобиль", callback_data="add_new_auto")])
        return InlineKeyboardMarkup(inline_keyboard=keyboard)

    @staticmethod
    def services_kb() -> InlineKeyboardMarkup:
        """Создаёт инлайн-клавиатуру с перечнем услуг."""
        keyboard = []
        for service in Config.SERVICES:
            text = f"{service['name']} ({service['price']} ₽)"
            keyboard.append([InlineKeyboardButton(text=text, callback_data=f"service_{service['name']}")])
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
        """Создаёт инлайн-клавиатуру с доступными датами (7 рабочих дней, на русском)."""
        today = datetime.today()
        start_date = today + timedelta(days=week_offset * 7)
        keyboard = []
        valid_dates = []

        # Словарь для локализации дней недели
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

        # Собираем 7 рабочих дней
        current_date = start_date
        while len(valid_dates) < 7:
            if current_date.strftime("%A") not in Config.WORKING_HOURS["weekends"]:
                valid_dates.append(current_date)
            current_date += timedelta(days=1)
            if (current_date - start_date).days > 30:
                break

        # Группируем по 2–3 даты в строке
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

        # Кнопки навигации
        nav_buttons = []
        if week_offset > 0:
            nav_buttons.append(InlineKeyboardButton(text="⬅ Назад", callback_data=f"prev_week_{week_offset - 1}"))
        if today <= valid_dates[-1] < today + timedelta(days=30):
            nav_buttons.append(InlineKeyboardButton(text="Вперёд ➡", callback_data=f"next_week_{week_offset + 1}"))
        if start_date.date() != today.date():
            nav_buttons.append(InlineKeyboardButton(text="📅 Сегодня", callback_data="today"))
        nav_buttons.append(InlineKeyboardButton(text="🚫 Отмена", callback_data="cancel_booking"))
        keyboard.append(nav_buttons)

        return InlineKeyboardMarkup(inline_keyboard=keyboard)

    @staticmethod
    def time_slots_kb(date: datetime, service_duration: int, session: Session,
                      time_offset: int = 0) -> InlineKeyboardMarkup:
        """Создаёт инлайн-клавиатуру с доступными временными слотами (шаг 30 минут, до 6 слотов)."""
        start_hour = int(Config.WORKING_HOURS["start"].split(":")[0])
        start_minute = int(Config.WORKING_HOURS["start"].split(":")[1])
        end_hour = int(Config.WORKING_HOURS["end"].split(":")[0])
        end_minute = int(Config.WORKING_HOURS["end"].split(":")[1])
        keyboard = []
        valid_slots = []

        # Получаем существующие записи на выбранную дату
        existing_bookings = session.query(Booking).filter(
            Booking.date == date.date(),
            Booking.status != BookingStatus.REJECTED
        ).all()
        booked_slots = []
        for b in existing_bookings:
            start_time = b.time
            duration = Config.SERVICES[[s["name"] for s in Config.SERVICES].index(b.service_name)]["duration_minutes"] if b.service_name != "Ремонт" else 60
            end_time = (datetime.combine(date.today(), start_time) + timedelta(minutes=duration)).time()
            booked_slots.append((start_time, end_time))

        # Собираем доступные слоты с шагом 30 минут
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

        # Ограничиваем до 6 слотов за раз
        start_index = time_offset * 6
        display_slots = valid_slots[start_index:start_index + 6]

        # Группируем по 2 слота в строке
        for i in range(0, len(display_slots), 2):
            row = []
            for slot in display_slots[i:i+2]:
                callback_data = f"time_{slot.strftime('%H:%M')}"
                text = f"🕒 {slot.strftime('%H:%M')} ({service_duration} мин)"
                row.append(InlineKeyboardButton(text=text, callback_data=callback_data))
            keyboard.append(row)

        # Кнопки навигации
        nav_buttons = []
        if start_index > 0:
            nav_buttons.append(InlineKeyboardButton(text="⏪ Ранее", callback_data=f"prev_slots_{time_offset - 1}"))
        if start_index + 6 < len(valid_slots):
            nav_buttons.append(InlineKeyboardButton(text="Позже ⏩", callback_data=f"next_slots_{time_offset + 1}"))
        nav_buttons.append(InlineKeyboardButton(text="🚫 Отмена", callback_data="cancel_booking"))
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
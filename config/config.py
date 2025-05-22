import os

from dotenv import load_dotenv
load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = os.getenv("ADMIN")
YANDEX_API_KEY = os.getenv("YANDEX_IAM_TOKEN")
YANDEX_FOLDER_ID = os.getenv("YANDEX_FOLDER_ID")

HUGGINGFACE_API_KEY = os.getenv("HUGGINGFACE_API_KEY")

# Пути к фото для сопровождения сообщений
PHOTO_PATHS = {
    "welcome": "photos/welcome.jpg",
    "contacts": "photos/contacts.jpg",
    "services": "photos/services.jpg",
    "booking": "photos/booking.jpg",
    "photo_diagnostic": "photos/diagnostic.jpg",
    "my_bookings": "photos/bookings.jpg",
    "about_master": "photos/master.jpg"
}

# Промпт для ИИ в диагностике по фото
AI_PROMPT = """
Вы - эксперт по диагностике автомобилей. Пользователь загрузил до 3 фотографий автомобиля или его деталей. 
Проанализируйте изображения и предоставьте возможную диагностику проблемы, указав:
- Вероятную неисправность.
- Возможные причины.
- Рекомендации по ремонту.
Если информации недостаточно или проблема не ясна, укажите, что требуется консультация мастера.
Ответ должен быть кратким и понятным, не более 200 символов.
"""
AI_PROMPT_STR = """
Ты автомеханик. Проанализируй описание проблемы автомобиля и дай предварительный диагноз.
- Вероятную неисправность.
- Возможные причины.
- Рекомендации по ремонту.
Если информации недостаточно или проблема не ясна, укажите, что требуется консультация мастера.
Ответ должен быть кратким и понятным, не более 200 символов.
"""
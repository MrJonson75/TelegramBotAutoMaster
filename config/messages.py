MESSAGES = {
    "welcome": "Добро пожаловать в RemDiesel 🚚! \n"
               "Я помогу вам:\n"
               "- Записаться на техническое обслуживание или ремонт\n"
               "- Провести диагностику по фото\n"
               "- Просмотреть ваши записи\n"
               "- Узнать о мастере и контактах\n"
               "Выберите действие:",
    "contacts": "📍 Адрес: Мытищи, ул. Стрелковая, 16\n"
                "📞 Телефон: +7 (915) 395-96-95\n "
                "Телеграмм: https://t.me/MrJonson_Dmitriy",
    "about_master": "Мастер Дмитрий - эксперт по дизельным автомобилям с 16-летним опытом.\n"
                    "Специализация: диагностика, ремонт двигателей, ТО.\n"
                    "Посмотрите фото и видео наших работ!",
    "booking": "Выберите услугу для записи на ТО:",
    "my_bookings": "📋 Ваши записи в RemDiesel:",
    "repair": "Опишите проблему и выберите время для ремонта! 🔧",
}

AI_PROMPT_STR = """
Ты автомеханик. Проанализируй описание проблемы автомобиля и дай предварительный диагноз.
- Вероятную неисправность.
- Возможные причины.
- Рекомендации по ремонту.
Если информации недостаточно или проблема не ясна, укажите, что требуется консультация мастера.
Ответ должен быть кратким и понятным, не более 200 символов.
"""

AI_PROMPT = """
Вы - эксперт по диагностике автомобилей. Пользователь загрузил до 3 фотографий автомобиля или его деталей. 
Проанализируйте изображения и предоставьте возможную диагностику проблемы, указав:
- Вероятную неисправность.
- Возможные причины.
- Рекомендации по ремонту.
Если информации недостаточно или проблема не ясна, укажите, что требуется консультация мастера.
Ответ должен быть кратким и понятным, не более 200 символов.
"""
import os
from dotenv import load_dotenv


class Config:
    """Класс для хранения всех констант и настроек бота."""

    # Загрузка переменных окружения
    load_dotenv()

    # Токены и идентификаторы
    BOT_TOKEN = os.getenv("BOT_TOKEN")
    ADMIN_ID = os.getenv("ADMIN")
    YANDEX_API_KEY = os.getenv("YANDEX_IAM_TOKEN")
    YANDEX_FOLDER_ID = os.getenv("YANDEX_FOLDER_ID")
    HUGGINGFACE_API_KEY = os.getenv("HUGGINGFACE_API_KEY")

    # Базовая папка для фотографий
    PHOTO_DIR = "photos"

    # Промпты для ИИ
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

    # Тексты для сообщений пользователю
    MESSAGES = {
        "welcome": (
            "Добро пожаловать в RemDiesel 🚚!\n"
            "Я помогу вам:\n"
            "- Записаться на техническое обслуживание или ремонт\n"
            "- Провести диагностику по фото\n"
            "- Просмотреть ваши записи\n"
            "- Узнать о мастере и контактах\n"
            "Выберите действие:"
        ),
        "contacts": (
            "📞 Свяжитесь с нами:\n"
            "Телефон: +7 (999) 123-45-67\n"
            "Email: support@remdiesel.ru\n"
            "Адрес: г. Москва, ул. Автозаводская, д. 10\n"
            "Как проехать: м. Автозаводская, 5 мин пешком"
        ),
        "about_master": (
            "🛠 Мастер Иван - эксперт по дизельным автомобилям с 15-летним опытом.\n"
            "Специализация: диагностика, ремонт двигателей, ТО.\n"
            "Посмотрите фото и видео наших работ!"
        )
    }

    # Список услуг
    SERVICES = [
        {"name": "Диагностика электроники", "duration_minutes": 60},
        {"name": "Замена масла в двигателе", "duration_minutes": 30},
        {"name": "Диагностика ходовой", "duration_minutes": 45},
        {"name": "Замена масла в АКПП", "duration_minutes": 90},
        {"name": "Замена колодок", "duration_minutes": 90},
        {"name": "Подача дизельного топлива", "duration_minutes": 20}
    ]

    @staticmethod
    def get_photo_path(file_name: str) -> str:
        """
        Возвращает путь к файлу в каталоге с фотографиями.

        Args:
            file_name (str): Имя файла без расширения (например, 'welcome').

        Returns:
            str: Полный путь к файлу (например, 'photos/welcome.jpg').

        Raises:
            FileNotFoundError: Если файл или папка не существуют.
            ValueError: Если имя файла пустое или содержит недопустимые символы.
        """
        if not file_name or not isinstance(file_name, str):
            raise ValueError("Имя файла должно быть непустой строкой")

        # Формируем имя файла с расширением .jpg
        file_name = file_name.strip()
        if not file_name:
            raise ValueError("Имя файла не может быть пустым")

        # Проверяем на недопустимые символы
        invalid_chars = '<>:"/\\|?*'
        if any(char in file_name for char in invalid_chars):
            raise ValueError(f"Имя файла содержит недопустимые символы: {invalid_chars}")

        # Формируем путь
        file_path = os.path.join(Config.PHOTO_DIR, f"{file_name}.jpg")

        # Проверяем существование папки
        if not os.path.exists(Config.PHOTO_DIR):
            raise FileNotFoundError(f"Папка с фотографиями не найдена: {Config.PHOTO_DIR}")

        # Проверяем существование файла
        if not os.path.isfile(file_path):
            raise FileNotFoundError(f"Файл не найден: {file_path}")

        return file_path
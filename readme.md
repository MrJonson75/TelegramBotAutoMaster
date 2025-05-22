TelegramBotAutoMaster/
├── config/
│   ├── __init__.py          # Новый файл: from .config import Config, __all__ = ['Config']
│   └── config.py            # Содержит класс Config с методом get_photo_path
├── utils/
│   ├── vision_api.py        # Интеграция с Yandex Vision API
│   ├── gpt_helper.py        # Интеграция с Yandex GPT
│   └── logger.py            # Настройка логирования
├── handlers/
│   ├── __init__.py          # Пустой или импортирует обработчики
│   ├── common.py            # Общие обработчики
│   └── photo_diagnostic.py  # Обработчик диагностики
├── keyboards/
│   └── main_kb.py           # Основная клавиатура main_menu_kb
├── photos/
│   ├── welcome.jpg
│   ├── contacts.jpg
│   ├── diagnostic.jpg
│   ├── bookings.jpg
│   ├── master.jpg
│   ├── services.jpg
│   └── booking.jpg
├── media/
│   └── diagnostics/
│       └── cache.txt        # Кэш результатов анализа
├── .env                     # Переменные окружения
├── bot.log                  # Логи бота
├── requirements.txt         # Зависимости
└── main.py                  # Главный файл бота
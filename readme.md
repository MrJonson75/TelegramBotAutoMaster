 TelegramBotAutoMaster/
├── config/                         # Конфигурация
│   ├── __init__.py                # Пустой файл для пакета
│   └── config.py                  # Настройки (BOT_TOKEN, ADMIN_ID, get_photo_path, SERVICES, ...)
├── utils/                          # Утилиты
│   ├── __init__.py                # Пустой файл для пакета
│   ├── vision_api.py              # (Вероятно) Интеграция с API для анализа изображений
│   ├── gpt_helper.py              # (Вероятно) Интеграция с GPT для обработки текста
│   └── logger.py                  # Настройка логирования (setup_logger, пишет в bot.log)
├── handlers/                       # Обработчики команд и callback'ов
│   ├── __init__.py                # Пустой файл для пакета
│   ├── common.py                  # Общие обработчики (например, /start, /help)
│   ├── photo_diagnostic.py         # Логика диагностики по фото
│   ├── service_booking.py          # Создание записей (FSM, регистрация, выбор авто/услуги)
│   └── my_bookings.py             # Просмотр и отмена записей
├── keyboards/                      # Клавиатуры
│   └── main_kb.py                 # Основное меню, клавиатуры для выбора авто, услуг, дат
├── photos/                         # Изображения для сообщений
│   ├── welcome.jpg                # Для команды /start или приветствия
│   ├── contacts.jpg               # Для контактов мастера
│   ├── photo_diagnostic.jpg       # Для диагностики по фото
│   ├── bookings.jpg               # Для списка записей (my_bookings.py)
│   ├── about_master.jpg           # Для раздела "О мастере"
│   ├── services.jpg               # Для списка услуг
│   ├── booking.jpg                # Для процесса бронирования
│   ├── booking_final.jpg          # Финальный шаг бронирования
│   ├── booking_menu.jpg           # Меню выбора услуги
│   └── photo_result_diagnostic.jpg # Результат диагностики по фото
├── media/                          # Медиафайлы (диагностика)
│   └── diagnostics/               # Папка для кэша диагностики
│       └── cache.txt              # Кэш результатов диагностики
├── .env                           # Переменные окружения (BOT_TOKEN, API ключи, ...)
├── bot.log                        # Лог-файл (DEBUG, INFO, ERROR)
├── database.py                    # Инициализация и модели базы данных (SQLite)
├── requirements.txt               # Зависимости (aiogram, sqlalchemy, pytz, ...)
└── main.py                        # Точка входа бота   
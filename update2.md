# **Проект Telegram-бота для частной автомастерской**  


---

## **📁 Структура проекта**  

### **📄 1. Основные файлы**  
```
├── main.py                # Главный скрипт бота  
├── config.py              # Настройки (токен, данные мастера)  
├── database.py            # Работа с SQLite  
├── keyboards.py           # Клавиатуры и кнопки  
├── handlers/              # Обработчики сообщений  
│   ├── __init__.py  
│   ├── common.py          # Основные команды (старт, помощь)  
│   ├── booking.py         # Запись на прием  
│   ├── photo_diagnostic.py # Диагностика по фото  
│   └── admin.py           # Команды для мастера  
└── utils/  
    ├── logger.py          # Логирование  
    ├── notifications.py   # Уведомления  
    └── storage.py         # Хранение фото и файлов  
```

---

## **📋 Описание файлов**  

### **2. `config.py`**  
```python
BOT_TOKEN = "ВАШ_TELEGRAM_BOT_TOKEN"  
MASTER_CHAT_ID = 123456789  # Ваш ID в Telegram  

# Часы работы  
WORK_HOURS = {  
    "Пн-Пт": "9:00 - 18:00",  
    "Сб": "10:00 - 15:00",  
    "Вс": "выходной"  
}  

# Основные услуги  
SERVICES = {  
    "Диагностика": 1500,  
    "Замена масла": 3000,  
    "Ремонт тормозов": 5000  
}  
```  

---

### **3. `database.py`**  
```python
import sqlite3  

def init_db():  
    conn = sqlite3.connect("autoshop.db")  
    cursor = conn.cursor()  

    # Таблица клиентов  
    cursor.execute("""  
    CREATE TABLE IF NOT EXISTS clients (  
        id INTEGER PRIMARY KEY,  
        user_id INTEGER,  
        name TEXT,  
        phone TEXT  
    )""")  

    # Таблица записей  
    cursor.execute("""  
    CREATE TABLE IF NOT EXISTS bookings (  
        id INTEGER PRIMARY KEY,  
        client_id INTEGER,  
        service TEXT,  
        date TEXT,  
        time TEXT,  
        status TEXT DEFAULT 'ожидает'  
    )""")  

    # Таблица диагностики по фото  
    cursor.execute("""  
    CREATE TABLE IF NOT EXISTS photo_diagnostics (  
        id INTEGER PRIMARY KEY,  
        client_id INTEGER,  
        photo_path TEXT,  
        description TEXT,  
        response TEXT DEFAULT NULL  
    )""")  

    conn.commit()  
    conn.close()  
```  

---

### **4. `keyboards.py`**  
```python
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton  

def main_menu():  
    return ReplyKeyboardMarkup(resize_keyboard=True).add(  
        KeyboardButton("🗓 Записаться"),  
        KeyboardButton("🖼 Диагностика по фото"),  
        KeyboardButton("📞 Контакты")  
    )  

def services_menu():  
    return ReplyKeyboardMarkup(resize_keyboard=True).add(  
        *[KeyboardButton(service) for service in SERVICES.keys()]  
    )  
```  

---

### **5. `handlers/photo_diagnostic.py`**  
```python
from aiogram import types  
from database import save_photo_diagnostic  

async def handle_photo(message: types.Message):  
    photo = message.photo[-1]  
    await message.answer("Фото принято. Опишите проблему:")  

    # Сохраняем в БД  
    save_photo_diagnostic(  
        user_id=message.from_user.id,  
        photo_id=photo.file_id,  
        description=""  # Пока пусто  
    )  

async def handle_description(message: types.Message):  
    # Обновляем описание в БД  
    update_description(message.from_user.id, message.text)  
    await message.answer("Мастер ответит в течение 2 часов!")  
```  

### **⚙️ Возможности бота:**  
✅ Запись на прием  
✅ Диагностика по фото  
✅ Управление графиком  
✅ Уведомления клиентов  


import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
YANDEX_API_KEY = os.getenv("YANDEX_API_KEY")
YANDEX_FOLDER_ID = os.getenv("YANDEX_FOLDER_ID")
ADMIN_ID = os.getenv("ADMIN_ID")
PHOTO_DIR = "photos"
UPLOAD_USER_DIR = "media/user_images"

# Создаем директорию, если она не существует
if not os.path.exists(PHOTO_DIR):
    os.makedirs(PHOTO_DIR)

# Создаем директорию, если она не существует
if not os.path.exists(UPLOAD_USER_DIR):
    os.makedirs(UPLOAD_USER_DIR)

def get_photo_path(file_name: str) -> str:
    """
    Возвращает путь к файлу в каталоге с фотографиями.
    """
    if not file_name or not isinstance(file_name, str):
        raise ValueError("Имя файла должно быть непустой строкой")
    file_name = file_name.strip()
    if not file_name:
        raise ValueError("Имя файла не может быть пустым")
    invalid_chars = '<>:"/\\|?*'
    if any(char in file_name for char in invalid_chars):
        raise ValueError(f"Имя файла содержит недопустимые символы: {invalid_chars}")
    file_path = os.path.join(PHOTO_DIR, f"{file_name}.jpg")
    if not os.path.exists(PHOTO_DIR):
        raise FileNotFoundError(f"Папка с фотографиями не найдена: {PHOTO_DIR}")
    if not os.path.isfile(file_path):
        raise FileNotFoundError(f"Файл не найден: {file_path}")
    return file_path
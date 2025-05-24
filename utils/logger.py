import logging
from logging import StreamHandler, FileHandler
import sys

def setup_logger(name: str) -> logging.Logger:
    """Настраивает и возвращает логгер с заданным именем."""
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)

    # Проверяем, нет ли уже обработчиков, чтобы избежать дублирования
    if not logger.handlers:
        # Формат логов
        formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(name)s - %(message)s")

        # Консольный обработчик
        console_handler = StreamHandler(sys.stdout)
        console_handler.setFormatter(formatter)
        console_handler.setLevel(logging.INFO)
        console_handler.stream.reconfigure(encoding='utf-8')

        # Файловый обработчик
        file_handler = FileHandler("bot.log", encoding="utf-8")
        file_handler.setFormatter(formatter)
        file_handler.setLevel(logging.INFO)

        # Добавляем обработчики
        logger.addHandler(console_handler)
        logger.addHandler(file_handler)

    return logger
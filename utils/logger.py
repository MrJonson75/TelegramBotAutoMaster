import logging
from logging import StreamHandler, FileHandler


def setup_logger(name: str) -> logging.Logger:
    """Настраивает и возвращает логгер с заданным именем."""
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)

    # Формат логов
    formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")

    # Консольный обработчик
    console_handler = StreamHandler()
    console_handler.setFormatter(formatter)
    console_handler.setLevel(logging.INFO)
    console_handler.stream.reconfigure(encoding='utf-8')

    # Файловый обработчик
    file_handler = FileHandler("bot.log", encoding="utf-8")
    file_handler.setFormatter(formatter)
    file_handler.setLevel(logging.INFO)

    # Очистка существующих обработчиков и добавление новых
    logger.handlers = [console_handler, file_handler]

    return logger
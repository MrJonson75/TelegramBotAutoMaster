import logging

logger = logging.getLogger(__name__)

def setup_logging():
    logging.basicConfig(
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        level=logging.INFO,
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler('bot_log.log', encoding='utf-8')
        ]
    )
    logger.info("Логирование настроено: консоль и файл bot_log.log")
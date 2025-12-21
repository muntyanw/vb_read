import logging
from datetime import datetime

FMT = '%(asctime)s - %(levelname)s - %(message)s'

logging.basicConfig(
    level=logging.INFO,           # корневой логгер: только INFO и выше
    format=FMT,
    handlers=[
        logging.FileHandler("log.log", mode='w', encoding='utf-8'),  # файл
        logging.StreamHandler(),                                      # консоль
    ],
    force=True  # ВАЖНО: сбрасывает ВСЕ ранее добавленные хендлеры/настройки
)

def log_and_print(message: str, level: str = 'debug'):
    level = level.lower()
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    if level in ('info', 'warning', 'error', 'critical'): #, 'debug'
        print(f"[{now}] {message}")

    if level == 'info':
        logging.info(message)
    elif level == 'warning':
        logging.warning(message)
    elif level == 'error':
        logging.error(message)
    elif level == 'critical':
        logging.critical(message)
    elif level == 'debug':
        logging.debug(message)

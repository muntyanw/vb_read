import logging
from datetime import datetime

# Настройка логирования
logging.basicConfig(
    filename='log.log',
    filemode='w',
    format='%(asctime)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    encoding='utf-8'
)

def log_and_print(message, level='info'):
    current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    print(f"[{current_time}] {message}")
    if level == 'info':
        logging.info(message)
    elif level == 'warning':
        log_and_print(message)
    elif level == 'error':
        log_and_print(message)
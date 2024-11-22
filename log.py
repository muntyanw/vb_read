import log

# Настройка логирования
logging.basicConfig(
    filename='facebook_automation.log',
    filemode='w',
    format='%(asctime)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    encoding='utf-8'
)

def log_and_print(message, level='info'):
    print(message)
    if level == 'info':
        logging.info(message)
    elif level == 'warning':
        log_and_print(message)
    elif level == 'error':
        log_and_print(message)
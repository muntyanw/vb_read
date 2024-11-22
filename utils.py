import json
from log import log_and_print

def clear_file(file_path):
    """Clears the contents of the specified file."""
    try:
        with open(file_path, 'w') as file:
            pass  # Opening in 'w' mode clears the file
        print(f"File '{file_path}' has been cleared.")
    except Exception as e:
        print(f"Error clearing file '{file_path}': {e}")


def read_setting(field_path):
    """
    Reads a specific field's value from a JSON settings file.

    :param field_path: Dot-separated path to the field (e.g., "capture_and_recognize.lang").
    :return: Value of the specified field, or None if the field does not exist.
    """
    file_path = "settings.json"
    try:
        # Open and load the JSON file
        with open(file_path, 'r') as file:
            settings = json.load(file)

        # Navigate to the desired field
        keys = field_path.split('.')
        value = settings
        for key in keys:
            value = value[key]

        return value
    except (FileNotFoundError, KeyError, json.JSONDecodeError) as e:
        print(f"Error reading field '{field_path}' from '{file_path}': {e}")
        return None

def load_json(file_path):
    log_and_print(f"Загрузка данных из JSON файла {file_path}.", 'info')
    try:
        with open(file_path, 'r', encoding='utf-8') as file:
            data = json.load(file)
        log_and_print(f"Данные успешно загружены из {file_path}.", 'info')
        return data
    except FileNotFoundError:
        log_and_print(f"Файл {file_path} не найден.", 'error')
        return None
    except json.JSONDecodeError:
        log_and_print(f"Ошибка декодирования JSON в файле {file_path}.", 'error')
        return None

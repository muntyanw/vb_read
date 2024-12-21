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

def convert_to_utf8(old_file, new_file):
    try:
        with open(old_file, 'r', encoding='windows-1251') as f:
            content = f.read()

        with open(new_file, 'w', encoding='utf-8') as f:
            f.write(content)

        print("Файл успешно преобразован и сохранён как", new_file)
    except Exception as e:
        print(f"Ошибка: {e}")

def read_setting(field_path):

    file_path = "settings.json"
    try:
        # Open and load the JSON file
        with open(file_path, 'r', encoding='windows-1251') as file:
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

def write_setting(field_path, new_value):
    """
    Writes a new value to a specific field in a JSON settings file.

    :param field_path: Dot-separated path to the field (e.g., "capture_and_recognize.lang").
    :param new_value: The new value to set for the specified field.
    """
    file_path = "settings.json"

    try:
        # Open and load the JSON file
        with open(file_path, 'r', encoding='windows-1251') as file:
            settings = json.load(file)

        # Navigate to the desired field and set the new value
        keys = field_path.split('.')
        value = settings
        for key in keys[:-1]:  # Traverse to the second-to-last key
            value = value[key]

        value[keys[-1]] = new_value  # Set the new value at the final key

        # Write the modified settings back to the file
        with open(file_path, 'w', encoding='windows-1251') as file:
            json.dump(settings, file, indent=4)
        log_and_print(f"[write_setting] Field '{field_path}' updated successfully. new_value = {new_value}")

    except (FileNotFoundError, KeyError, json.JSONDecodeError) as e:
        log_and_print(f"[write_setting] Error writing field '{field_path}' to '{file_path}': {e}")

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

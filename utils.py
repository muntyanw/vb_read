import json
from log import log_and_print
import os
import cv2

def read_setting(field_path):

    file_path = "settings.json"
    try:
        # Open and load the JSON file
        with open(file_path, 'r', encoding='utf-8') as file:
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
        with open(file_path, 'r', encoding='utf-8') as file:
            settings = json.load(file)

        # Navigate to the desired field and set the new value
        keys = field_path.split('.')
        value = settings
        for key in keys[:-1]:  # Traverse to the second-to-last key
            value = value[key]

        value[keys[-1]] = new_value  # Set the new value at the final key

        # Write the modified settings back to the file
        with open(file_path, 'w', encoding='utf-8') as file:
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

def get_latest_file(download_folder):
    try:
        files = os.listdir(download_folder)
        paths = [os.path.join(download_folder, fname) for fname in files]
        latest_file = max(paths, key=os.path.getctime)
        return latest_file
    except Exception as e:
        print(f"Ошибка при получении последнего файла: {e}")
        return None


def is_video_file(file_path):
    """
    Определяет, является ли файл видео по его расширению.

    :param file_path: Путь к файлу.
    :return: True, если файл является видео, иначе False.
    """
    # Список расширений видеофайлов
    video_extensions = {".mp4", ".mkv", ".avi", ".mov", ".wmv", ".flv", ".webm", ".m4v"}

    # Получаем расширение файла
    file_extension = file_path.lower().split('.')[-1]

    # Проверяем, есть ли расширение в списке видео
    return f".{file_extension}" in video_extensions

def get_video_dimensions_cv2(file_path):
    cap = cv2.VideoCapture(file_path)
    if not cap.isOpened():
        return None, None, None, None
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = cap.get(cv2.CAP_PROP_FPS)
    duration = cap.get(cv2.CAP_PROP_FRAME_COUNT) / fps if fps else None
    cap.release()
    return width, height, duration, fps

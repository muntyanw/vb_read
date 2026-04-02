import os
from log import log_and_print
import re
from utils import read_setting
from project_config import external_or_resource_path, writable_app_path

def load_previous_text(file_name='previous_text.txt'):
    file_path = external_or_resource_path(file_name)
    log_and_print(f"Загрузка предыдущего текста из файла {file_name}")
    if os.path.exists(file_path):
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                text = f.read()
            log_and_print("[load_previous_text] Предыдущий текст успешно загружен")
            return text
        except Exception as e:
            log_and_print(f"[load_previous_text] Ошибка при чтении файла {file_name}: {e}")
            return ""
    else:
        log_and_print(f"[load_previous_text] Файл {file_name} не найден. Будет создан новый файл.")
        return ""

def remove_service_symbols_and_spaces(text):
    # This will remove all non-alphanumeric characters and spaces
    cleaned_text = re.sub(r'[^A-Za-z0-9]', '', text)
    return cleaned_text

def save_current_text(text, file_name='previous_text.txt', max_chars=read_setting("max_chars_member")):
    file_path = writable_app_path(file_name)
    log_and_print(f"Saving current text to history file {file_name} (max {max_chars} chars)")

    try:
        current = str(text or "").strip()
        if not current:
            return

        try:
            max_chars = int(max_chars)
        except Exception:
            max_chars = 20000

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                existing_content = f.read().strip()
        except FileNotFoundError:
            existing_content = ""

        sep = "\n\n===MSG===\n\n"
        combined_text = f"{existing_content}{sep}{current}" if existing_content else current

        if max_chars > 0 and len(combined_text) > max_chars:
            combined_text = combined_text[-max_chars:]

        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(combined_text)
    except Exception as e:
        log_and_print(f"Error saving text to file {file_name}: {e}", "error")

import os
from log import log_and_print
import re
from utils import read_setting

def load_previous_text(file_name='previous_text.txt'):
    log_and_print(f"Загрузка предыдущего текста из файла {file_name}")
    if os.path.exists(file_name):
        try:
            with open(file_name, 'r', encoding='utf-8') as f:
                text = f.read()
            log_and_print(f"Предыдущий текст успешно загружен text = {text}")
            return text
        except Exception as e:
            log_and_print(f"Ошибка при чтении файла {file_name}: {e}")
            return ""
    else:
        log_and_print(f"Файл {file_name} не найден. Будет создан новый файл.")
        return ""

def remove_service_symbols_and_spaces(text):
    # This will remove all non-alphanumeric characters and spaces
    cleaned_text = re.sub(r'[^A-Za-z0-9]', '', text)
    return cleaned_text

def save_current_text(text, file_name='previous_text.txt', max_chars=read_setting("max_chars_member")):
    log_and_print(f"Adding current text to file {file_name} with a limit of {max_chars} characters.")

    try:
        # Read existing content if the file exists
        try:
            with open(file_name, 'r', encoding='utf-8') as f:
                existing_content = f.read().strip()
        except FileNotFoundError:
            existing_content = ""

        # Clean the new text
        cleaned_text = remove_service_symbols_and_spaces(text)

        # Combine the existing and new cleaned text
        combined_text = existing_content + cleaned_text

        # If the combined text exceeds the max_chars limit, truncate it to the last max_chars
        if len(combined_text) > max_chars:
            combined_text = combined_text[-max_chars:]

        # Write the single-line text back to the file
        with open(file_name, 'w', encoding='utf-8') as f:
            f.write(combined_text)
    except Exception as e:
        log_and_print(f"Error saving text to file: {e}")

        log_and_print(f"Текст успешно добавлен. Последние {max_lines} строк сохранены. Добавлено: {text}")
    except Exception as e:
        log_and_print(f"Ошибка при сохранении текста в файл {file_name}: {e}")

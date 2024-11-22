import os
import logging

def load_previous_text(file_name='previous_text.txt'):
    logging.debug(f"Загрузка предыдущего текста из файла {file_name}")
    if os.path.exists(file_name):
        try:
            with open(file_name, 'r', encoding='utf-8') as f:
                text = f.read()
            logging.debug("Предыдущий текст успешно загружен")
            return text
        except Exception as e:
            logging.error(f"Ошибка при чтении файла {file_name}: {e}")
            return ""
    else:
        logging.warning(f"Файл {file_name} не найден. Будет создан новый файл.")
        return ""

def save_current_text(text, file_name='previous_text.txt'):
    logging.debug(f"Сохранение текущего текста в файл {file_name}")
    try:
        with open(file_name, 'w', encoding='utf-8') as f:
            f.write(text)
        logging.debug("Текущий текст успешно сохранён")
    except Exception as e:
        logging.error(f"Ошибка при сохранении текста в файл {file_name}: {e}")

def find_addition(old_text, new_text, match_ratio=0.8):
    """
    Ищет новый добавленный текст в новом тексте относительно старого текста.
    :param old_text: Старый текст.
    :param new_text: Новый текст.
    :param match_ratio: Процент совпадения для частичного совпадения (по умолчанию 80%).
    :return: Новый добавленный текст.
    """
    # Приводим оба текста к нижнему регистру
    old_text = old_text.lower()
    logging.debug(f"[find_addition] old_text: {old_text}")
    new_text_origin = new_text
    new_text = new_text.lower()
    logging.debug(f"[find_addition] new_text: {new_text}")

    # Вычисляем длину части для сравнения (30% длины старого текста, минимум 3 символа)
    min_length = 3
    part_length = max(int(len(old_text) * 0.3), min_length)

    if len(old_text) < part_length:
        logging.warning("Старый текст слишком короткий длина участка будет его длина.")
        part_length = len(old_text) -1

    # Берём часть старого текста для поиска
    old_part = old_text[-part_length:]

    logging.debug(f"Часть старого текста для поиска: {old_part}")

    # Перебираем новый текст с конца, сдвигаясь влево
    for shift in range(len(new_text) - part_length, -1, -1):
        # Извлекаем часть нового текста для сравнения
        new_part = new_text[shift:shift + part_length]

        # Считаем количество совпавших символов
        matches = sum(1 for o, n in zip(old_part, new_part) if o == n)

        # Если совпадение удовлетворяет условию (80% совпадения), фиксируем начало нового текста
        if matches / part_length >= match_ratio:
            # Возвращаем новый добавленный текст, начиная с найденной позиции
            addition = new_text_origin[shift + part_length:]
            logging.debug(f"Найдено совпадение с {matches} совпавшими символами из {part_length} (порог {match_ratio * 100}%).")
            logging.debug(f"Добавленный текст: {addition}")
            return addition

    # Если совпадение не найдено
    logging.warning("Совпадение не найдено.")
    return None


    # Извлекаем часть нового текста, которая идёт после найденной подстроки
    addition_start = pos + len(last_part)
    addition = new_text[addition_start:].strip()

    return addition

import os
from log import log_and_print

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

def save_current_text(text, file_name='previous_text.txt'):
    log_and_print(f"Сохранение текущего текста в файл {file_name}")
    try:
        with open(file_name, 'w', encoding='utf-8') as f:
            f.write(text)
        log_and_print(f"Текущий текст успешно сохранён text = {text}")
    except Exception as e:
        log_and_print(f"Ошибка при сохранении текста в файл {file_name}: {e}")

def are_texts_different(text1, text2, threshold=0.2):
    # Приводим тексты к одному регистру и удаляем лишние пробелы
    text1 = text1.strip().lower()
    text2 = text2.strip().lower()

    # Находим длину более длинного текста
    max_length = max(len(text1), len(text2))

    # Если оба текста пусты, считаем их одинаковыми
    if max_length == 0:
        return False

    # Подсчитываем количество отличий
    differences = sum(1 for a, b in zip(text1, text2) if a != b)
    differences += abs(len(text1) - len(text2))  # Учитываем разницу в длине

    # Вычисляем долю различий
    difference_ratio = differences / max_length

    # Возвращаем результат на основе порога
    return difference_ratio > threshold

def find_addition(old_text, new_text, match_ratio=0.6):
    """
    Ищет новый добавленный текст в новом тексте относительно старого текста.
    :param old_text: Старый текст.
    :param new_text: Новый текст.
    :param match_ratio: Процент совпадения для частичного совпадения (по умолчанию 80%).
    :return: Новый добавленный текст.
    """
    # Приводим оба текста к нижнему регистру
    old_text = old_text.lower()
    log_and_print(f"[find_addition] old_text: {old_text}")
    new_text_origin = new_text
    new_text = new_text.lower()
    log_and_print(f"[find_addition] new_text: {new_text}")

    # Вычисляем длину части для сравнения (30% длины старого текста, минимум 3 символа)
    min_length = 3
    part_length = max(int(len(old_text) * 0.3), min_length)

    if len(old_text) < part_length:
        log_and_print("Старый текст слишком короткий длина участка будет его длина.")
        part_length = len(old_text) -1

    # Берём часть старого текста для поиска
    old_part = old_text[-part_length:]

    log_and_print(f"Часть старого текста для поиска: {old_part}")

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
            log_and_print(f"Найдено совпадение с {matches} совпавшими символами из {part_length} (порог {match_ratio * 100}%).")
            log_and_print(f"Добавленный текст: {addition}")
            return addition

    # Если совпадение не найдено
    log_and_print("Совпадение не найдено. Значит єто полностью новий текст.")
    return new_text


    # Извлекаем часть нового текста, которая идёт после найденной подстроки
    addition_start = pos + len(last_part)
    addition = new_text[addition_start:].strip()

    return addition.strip()

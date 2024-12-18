import os
from log import log_and_print
from difflib import SequenceMatcher

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

def save_current_text(text, file_name='previous_text.txt', max_lines=400):
    log_and_print(f"Добавление текущего текста в файл {file_name} с ограничением в {max_lines} строк.")

    try:
        # Читаем существующие строки (если файл существует)
        try:
            with open(file_name, 'r', encoding='utf-8') as f:
                existing_lines = f.readlines()
        except FileNotFoundError:
            existing_lines = []

        # Превращаем новый текст в список строк
        new_lines = text.split('\n')

        # Добавляем новые строки к существующим
        all_lines = existing_lines + [line + '\n' for line in new_lines if line.strip() != '']

        # Если общее число строк больше max_lines, оставляем только последние max_lines
        if len(all_lines) > max_lines:
            all_lines = all_lines[-max_lines:]

        # Записываем обратно в файл
        with open(file_name, 'w', encoding='utf-8') as f:
            f.writelines(all_lines)

        log_and_print(f"Текст успешно добавлен. Последние {max_lines} строк сохранены. Добавлено: {text}")
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

def find_addition(old_text, new_text, match_ratio=0.7):
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


def is_subtext_similar(full_text, subtext, threshold=80):
    """
    Определяет, похож ли subtext на некоторый фрагмент full_text
    с процентом схожести не ниже threshold.

    Параметры:
    - full_text (str): исходный полный текст
    - subtext (str): искомый текст (шаблон)
    - threshold (int): минимальный процент схожести (0-100)

    Возвращает:
    - bool: True, если найдена похожесть не ниже порога, иначе False
    """
    # Удаляем лишние пробелы
    full_text = full_text.strip()
    subtext = subtext.strip()

    if not subtext or not full_text:
        return False

    # Если subtext короче или равен full_text, можно сразу проверить схожесть
    if len(subtext) <= len(full_text):
        # Скользящее окно по full_text, чтобы найти максимально похожий фрагмент
        for start in range(0, len(full_text) - len(subtext) + 1):
            fragment = full_text[start:start + len(subtext)]
            ratio = SequenceMatcher(None, subtext, fragment).ratio() * 100
            if ratio >= threshold:
                return True
    else:
        # Если subtext длиннее full_text, просто сравниваем их целиком
        ratio = SequenceMatcher(None, subtext, full_text).ratio() * 100
        return ratio >= threshold

    return False

def sequence_matcher_ratio(text1, text2):
    matcher = SequenceMatcher(None, text1, text2)
    return matcher.ratio() * 100

def is_subtext_present_at_threshold(full_text, subtext, threshold=70):
    """
    Проверяет, встречается ли в full_text подстрока, которая покрывает не менее threshold% subtext.

    Например, если threshold=70 и subtext="привет",
    то мы считаем True, если в full_text есть как минимум "приве" (то есть 5/6≈83% символов подряд).
    """
    ratio = sequence_matcher_ratio(subtext, full_text)
    log_and_print(f"[is_subtext_present_at_threshold] ratio = {ratio}")
    return ratio >= threshold

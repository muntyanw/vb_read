from log import log_and_print
import pyautogui
import pytesseract
from pytesseract import Output
from utils import read_setting
import numpy as np
from find_message import remove_service_symbols_and_spaces

pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'

import cv2

def preprocess_image(image_np):
    """
    Преобразует изображение для улучшения качества OCR.

    :param image_np: Изображение в формате NumPy массива (RGB)
    :return: Обработанное изображение в оттенках серого
    """
    # Проверяем размерность массива
    if len(image_np.shape) != 3 or image_np.shape[2] != 3:
        raise ValueError("Изображение должно быть цветным (3 канала).")

    # Конвертируем из RGB в BGR
    image_bgr = cv2.cvtColor(image_np, cv2.COLOR_RGB2BGR)

    # Конвертируем в оттенки серого
    gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)

    # Улучшаем контрастность с помощью CLAHE
    clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))  # Увеличен clipLimit для большего усиления контраста
    enhanced = clahe.apply(gray)

    # Адаптивная бинаризация с измененными параметрами
    thresh = cv2.adaptiveThreshold(enhanced, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                   cv2.THRESH_BINARY_INV, 15, 10)  # Используем инверсию и меньший блок

    # Морфологическое закрытие для заполнения пробелов внутри букв
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (2, 2))
    closed = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel, iterations=1)

    # Удаление небольших шумов с помощью морфологического открытия
    opened = cv2.morphologyEx(closed, cv2.MORPH_OPEN, kernel, iterations=1)

    # Опционально: применение билинейного фильтра для сглаживания краев
    # opened = cv2.bilateralFilter(opened, 9, 75, 75)

    return opened

def filter_recognized_text(text):
    """
    Filters out lines that are shorter than 6 characters and contain colons.
    """
    lines = text.split('\n')  # Разбиваем текст на строки
    filtered_lines = []
    for line in lines:
        stripped_line = line.strip()  # Убираем пробелы в начале и конце строки
        if len(stripped_line) < 6 and ':' in stripped_line:
            continue  # Пропускаем строки, если их длина < 6 и они содержат двоеточие
        filtered_lines.append(line)  # Добавляем остальные строки
    return '\n'.join(filtered_lines)  # Собираем текст обратно

def showImage(processed_image, ms):
    # Отображение обработанного изображения
    processed_array = np.array(processed_image)
    window_name = "Processed Image"
    cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)
    cv2.moveWindow(window_name, 10, 10)
    cv2.imshow(window_name, processed_array)
    cv2.waitKey(1)
    cv2.waitKey(ms)
    cv2.destroyAllWindows()

def capture_and_recognize(region):
    log_and_print(f"[capture_and_recognize] region: {region}")
    """Capture and recognize text only when the image changes."""
    try:
        # Take a screenshot
        #screenshot = pyautogui.screenshot(region=region)
        screenshot = take_screenshot(region)
        #showImage(screenshot, region)
        # Preprocess the image (if needed)
        processed_image = preprocess_image(screenshot) #

        visualize = read_setting("visualize")
        if visualize:
            showImage(processed_image, 1000)
        #cv2.waitKey(3000)
        # Perform OCR
        custom_config = read_setting("capture_and_recognize.custom_config")
        lang = read_setting("capture_and_recognize.lang")
        text = pytesseract.image_to_string(processed_image, lang=lang, config=custom_config)

        log_and_print(f"Recognized text (before filtering):\n{text}")

        # Filter the recognized text
        filtered_text = filter_recognized_text(text)

        log_and_print(f"Recognized text (after filtering):\n{filtered_text}")

        return filtered_text

    except Exception as e:
        log_and_print(f"Error during capture and recognition: {e}")
        return None

def capture_and_find_multiple_text_coordinates(region, search_phrases, visualize = False):
    log_and_print(f"[capture_and_find_multiple_text_coordinates] region: {region}, search_phrases: {search_phrases}")
    try:
        cv2.destroyAllWindows()

        # Захват скриншота
        screenshot_np = take_screenshot(region)
        log_and_print(f"[capture_and_find_text_coordinates] Скриншот захвачен успешно.")

        # Предварительная обработка изображения
        processed_image = preprocess_image(screenshot_np)
        log_and_print(f"[capture_and_find_text_coordinates] Изображение обработано успешно.")

        # Выполнение OCR с получением позиций
        data = perform_ocr_with_positions(processed_image)

        # Визуализация результатов OCR (опционально)
        if visualize:
            visualize_ocr_results(processed_image, data)

        log_and_print(f"Результат распознания меню data = {data}")
        # Подготовим словарь результатов
        # Изначально для всех ключей значение None
        result_dict = {key: None for key in search_phrases}

        # Перебираем каждый ключ-фразу из словаря поиска
        for key, phrase in search_phrases.items():
            log_and_print(f"phrase = {phrase}")
            search_word_lower = phrase.lower()
            # Проходим по всем распознанным словам
            for recognized in data:
                log_and_print(f"word = {recognized["text"]}")
                if recognized["text"]:
                    word_lower = recognized["text"].lower()
                    if search_word_lower == word_lower:
                        # Если нашли совпадение, сохраняем координаты и выходим из цикла
                        x = recognized["left"]
                        y = recognized["top"]
                        w = recognized["width"]
                        h = recognized["height"]
                        result_dict[key] = (x, y, w, h)
                        break

        # Логируем результаты
        for k, coords in result_dict.items():
            if coords is not None:
                log_and_print(f"Coordinates for phrase '{search_phrases[k]}' (key: {k}): {coords}")
            else:
                log_and_print(f"Phrase '{search_phrases[k]}' (key: {k}) not found.")

        return result_dict

    except Exception as e:
        log_and_print(f"Error during capture and coordinate recognition: {e}")
        return {key: None for key in search_phrases}

def take_screenshot(region):
    screenshot = pyautogui.screenshot(region=region)
    image_np = np.array(screenshot)
    return image_np

def preprocess_image(image_np):
    # Проверяем размерность массива
    if len(image_np.shape) != 3 or image_np.shape[2] != 3:
        raise ValueError("Изображение должно быть цветным (3 канала).")

    # Конвертируем из RGB в BGR
    image_bgr = cv2.cvtColor(image_np, cv2.COLOR_RGB2BGR)

    # Конвертируем в оттенки серого
    gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)

    # Улучшаем контрастность с помощью CLAHE (Contrast Limited Adaptive Histogram Equalization)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    enhanced = clahe.apply(gray)

    # Адаптивная бинаризация
    thresh = cv2.adaptiveThreshold(enhanced, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                   cv2.THRESH_BINARY, 31, 2)

    # Удаление небольших шумов с помощью морфологических операций
    kernel = np.ones((1, 1), np.uint8)
    cleaned = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, kernel)

    return cleaned

def perform_ocr_with_positions(image):
    custom_config = read_setting("capture_and_recognize.custom_config")
    lang = read_setting("capture_and_recognize.lang")

    data = pytesseract.image_to_data(image, lang=lang, config=custom_config, output_type=Output.DICT)

    n_boxes = len(data['level'])
    words_with_positions = []

    for i in range(n_boxes):
        if int(data['conf'][i]) > 60 and data['text'][i].strip() != "":
            word_info = {
                'text': data['text'][i],
                'left': data['left'][i],
                'top': data['top'][i],
                'width': data['width'][i],
                'height': data['height'][i],
                'conf': data['conf'][i]
            }
            words_with_positions.append(word_info)

    return words_with_positions

def visualize_ocr_results(image, ocr_data):
    """
    Отображает распознанные слова с их позициями на изображении.

    :param image: Обработанное изображение (оттенки серого)
    :param ocr_data: Список слов с их позициями
    """
    # Конвертируем обратно в BGR для отображения цветных рамок
    image_bgr = cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)

    for word in ocr_data:
        # Рисуем прямоугольник вокруг слова
        cv2.rectangle(image_bgr,
                      (word['left'], word['top']),
                      (word['left'] + word['width'], word['top'] + word['height']),
                      (0, 255, 0), 2)
        # Наносим текст слова
        cv2.putText(image_bgr, word['text'],
                    (word['left'], word['top'] - 10),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.5, (0, 0, 255), 2, cv2.LINE_AA)

    # Отображаем изображение
    cv2.imshow("OCR Results", image_bgr)
    cv2.waitKey(1)
    input("Press key from continue")
    cv2.destroyAllWindows()

def capture_and_find_text_coordinates(region, search_words, preprocess=True, case_sensitive=False, visualize = False):
    try:
        # Захват скриншота
        screenshot_np = take_screenshot(region)
        log_and_print(f"[capture_and_find_text_coordinates] Скриншот захвачен успешно.")

        if preprocess :
            # Предварительная обработка изображения
            processed_image = preprocess_image(screenshot_np)
            log_and_print(f"[capture_and_find_text_coordinates] Изображение обработано успешно.")
        else:
            processed_image = screenshot_np

        # Выполнение OCR с получением позиций
        ocr_results = perform_ocr_with_positions(processed_image)

        # Визуализация результатов OCR (опционально)
        if visualize:
            visualize_ocr_results(processed_image, ocr_results)

        # Подготавливаем список для хранения координат
        coordinates = []

        # Проходим по всем распознанным словам
        for word in ocr_results:
            if not word['text']:
                continue  # Пропускаем пустые строки

            # Обрабатываем регистр в зависимости от флага
            for search_word in search_words:
                if not case_sensitive:
                    word_lower = word['text'].lower()
                    search_word_lower = search_word.lower()
                else:
                    word_lower = word['text']
                    search_word_lower = search_word

                log_and_print(f"word_lower = {word_lower} search_word_lower: {search_word_lower}")

                if search_word_lower in word_lower:
                    x = word['left']
                    y = word['top']
                    w = word['width']
                    h = word['height']
                    coordinates.append((x, y, w, h))

        return coordinates

    except Exception as e:
        print(f"Ошибка в capture_and_find_text_coordinates: {e}")
        return []

def find_text_upward_with_highlight(start_x, start_y, y_max, height, template_height, template_width, search_words):

    step = int(template_height / 2)  # Шаг поиска

    current_y = start_y
    min_y = y_max - height

    log_and_print(f"height = {height}, min_y = {min_y}")

    while current_y >= min_y:
        log_and_print(f"start_x = {start_x}, current_y = {current_y}, min_y = {min_y}")

        # Снимаем скриншот текущей области
        region = (start_x, current_y, template_width, template_height)

        text = capture_and_recognize(region).lower()
        word = (text.replace(">", "")
                .replace("›", "")
                .replace(" ", "")
                .replace("»", "")
                .replace("\n", "")
                .replace("\r", "")
                .replace("\t", "")
                )
        search_words_lower = [word.lower() for word in search_words]

        log_and_print(f"word = {word} search_words_lower = {search_words_lower}")

        if word:
            # Если шаблон найден
            if word in search_words_lower:
                log_and_print(f"text знайдений")
                found_y = current_y
                return found_y

        # Шаг вверх
        current_y -= step
        # time.sleep(3)

    return None



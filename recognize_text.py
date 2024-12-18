from log import log_and_print
import pyautogui
import pytesseract
from pytesseract import Output
from utils import read_setting
import cv2
import numpy as np
from PIL import Image

pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'

def preprocess_image(pil_image):
    """
    Preprocess the image to make messages visible while hiding timestamps and checkmarks.
    """
    # Convert PIL Image to OpenCV format
    image = np.array(pil_image)

    # Convert to grayscale for easier processing
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

    # Apply CLAHE (Contrast Limited Adaptive Histogram Equalization)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    enhanced_image = clahe.apply(gray)  # Apply CLAHE to enhance contrast

    # Detect areas with timestamps and checkmarks (using brightness threshold)
    _, binary = cv2.threshold(enhanced_image, 200, 255, cv2.THRESH_BINARY)

    # Define a mask to remove timestamps and checkmarks
    mask = np.zeros_like(binary)

    # Apply the mask to hide timestamps and checkmarks
    processed = cv2.bitwise_and(enhanced_image, enhanced_image, mask=~mask)

    # Convert back to PIL Image format
    return Image.fromarray(processed)

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

def showImage(processed_image, region):
    # Отображение обработанного изображения
    processed_array = np.array(processed_image)
    window_name = "Processed Image"
    cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)
    cv2.moveWindow(window_name, region[0], region[1])
    cv2.imshow(window_name, processed_array)
    cv2.waitKey(1)
    cv2.waitKey(30000)
    cv2.destroyAllWindows()

def capture_and_recognize(region):
    log_and_print(f"[capture_and_recognize] region: {region}")
    """Capture and recognize text only when the image changes."""
    try:
        cv2.destroyAllWindows()
        # Take a screenshot
        screenshot = pyautogui.screenshot(region=region)
        #showImage(screenshot, region)
        # Preprocess the image (if needed)
        processed_image = preprocess_image(screenshot) #
        #showImage(processed_image, region)
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


def capture_and_find_multiple_text_coordinates(region, search_phrases):
    """
    Выполняет скриншот заданного региона экрана, распознаёт текст,
    и для каждого ключа (фразы) возвращает координаты (x, y, w, h),
    если фраза найдена. Если не найдена – возвращает None.

    Параметры:
    - region: кортеж (left, top, width, height) для pyautogui.screenshot
    - search_phrases: словарь {ключ: искомая_фраза}, где:
        ключ - название/идентификатор фразы
        искомая_фраза - строка, которую нужно найти на изображении

    Возвращает:
    - result_dict: словарь {ключ: (x, y, w, h) или None},
      для каждого искомого текста.
    """
    log_and_print(f"[capture_and_find_multiple_text_coordinates] region: {region}, search_phrases: {search_phrases}")
    try:
        cv2.destroyAllWindows()
        # Делаем скриншот заданного региона
        screenshot = pyautogui.screenshot(region=region)

        # Предобработка изображения
        processed_image = preprocess_image(screenshot)

        # Считываем настройки для Tesseract
        custom_config = read_setting("capture_and_recognize.custom_config")
        lang = read_setting("capture_and_recognize.lang")

        # Получаем данные с координатами и текстом
        data = pytesseract.image_to_data(processed_image, lang=lang, config=custom_config, output_type=pytesseract.Output.DICT)
        log_and_print(f"Результат распознания меню data = {data}")
        # Подготовим словарь результатов
        # Изначально для всех ключей значение None
        result_dict = {key: None for key in search_phrases}

        # Перебираем каждый ключ-фразу из словаря поиска
        for key, phrase in search_phrases.items():
            # Проходим по всем распознанным словам
            for i, recognized_text in enumerate(data["text"]):
                if recognized_text and phrase in recognized_text:
                    # Если нашли совпадение, сохраняем координаты и выходим из цикла
                    x = data["left"][i]
                    y = data["top"][i]
                    w = data["width"][i]
                    h = data["height"][i]
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


def preprocess_image_for_purple_text(image):
    """
    Предобрабатывает изображение для выделения фиолетового текста.

    Параметры:
    - image: изображение в формате PIL.Image

    Возвращает:
    - mask: бинарная маска фиолетового текста
    """
    # Конвертируем изображение из PIL в OpenCV формат (BGR)
    image_np = np.array(image)
    image_bgr = cv2.cvtColor(image_np, cv2.COLOR_RGB2BGR)

    # Конвертируем в HSV цветовое пространство
    hsv = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2HSV)

    # Определяем диапазон фиолетового цвета в HSV
    # Эти значения могут потребовать корректировки в зависимости от вашего изображения
    lower_purple = np.array([130, 50, 50])
    upper_purple = np.array([160, 255, 255])

    # Создаем маску для фиолетового цвета
    mask = cv2.inRange(hsv, lower_purple, upper_purple)

    # Применяем морфологические операции для очистки маски
    kernel = np.ones((3, 3), np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=2)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel, iterations=1)

    return mask

def capture_and_find_text_coordinates(region, search_word, preprocess=True, case_sensitive=False):
    """
    Выполняет скриншот заданного региона экрана, распознаёт текст,
    и возвращает координаты всех вхождений заданного слова.

    Параметры:
    - region: кортеж (left, top, width, height) для pyautogui.screenshot
    - search_word: слово (строка), которое нужно найти на изображении
    - preprocess: булевый флаг, указывающий, нужно ли предобрабатывать изображение
    - case_sensitive: булевый флаг для учета регистра при поиске

    Возвращает:
    - coordinates: список кортежей (x, y, w, h), где каждое кортеж представляет координаты найденного слова
    """
    try:
        # Делает скриншот заданного региона
        screenshot = pyautogui.screenshot(region=region)

        # Предобработка изображения (по желанию)
        if preprocess:
            processed_image = preprocess_image(screenshot)
        else:
            # Конвертируем изображение из PIL в OpenCV формат без предобработки
            processed_image = cv2.cvtColor(cv2.cvtColor(np.array(screenshot), cv2.COLOR_RGB2BGR), cv2.COLOR_BGR2GRAY)

        #showImage(processed_image, region)

        # Настройки для Tesseract
        custom_config = r'--oem 3 --psm 6'  # OEM 3: Default, based on what is available. PSM 6: Assume a single uniform block of text.
        lang = 'rus'  # Укажите нужные языки, например, английский и украинский

        # Выполняем распознавание текста с данными о позициях
        data = pytesseract.image_to_data(processed_image, lang=lang, config=custom_config, output_type=Output.DICT)

        # Подготавливаем список для хранения координат
        coordinates = []

        # Проходим по всем распознанным словам
        for i, word in enumerate(data['text']):
            log_and_print(f"word: {word}")
            if not word:
                continue  # Пропускаем пустые строки

            # Обрабатываем регистр в зависимости от флага
            if not case_sensitive:
                word_lower = word.lower()
                search_word_lower = search_word.lower()
            else:
                word_lower = word
                search_word_lower = search_word

            if search_word_lower in word_lower:
                x = data['left'][i]
                y = data['top'][i]
                w = data['width'][i]
                h = data['height'][i]
                coordinates.append((x, y, w, h))

        return coordinates

    except Exception as e:
        print(f"Ошибка в capture_and_find_text_coordinates: {e}")
        return []


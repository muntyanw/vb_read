import cv2
import numpy as np
import logging
from PIL import Image
import pyautogui
import pytesseract
import re

import cv2
import numpy as np
from PIL import Image

def preprocess_image(pil_image):
    """
    Preprocess the image to make messages visible while hiding timestamps and checkmarks.
    """
    # Convert PIL Image to OpenCV format
    image = np.array(pil_image)

    # Convert to grayscale for easier processing
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

    # Detect areas with timestamps and checkmarks (using brightness threshold)
    # You can tune the threshold value based on your image
    _, binary = cv2.threshold(gray, 200, 255, cv2.THRESH_BINARY)

    # Define a mask to remove timestamps and checkmarks
    mask = np.zeros_like(binary)

    # Assuming timestamps and checkmarks are usually on the right side, mask that area
    height, width = binary.shape
    for y in range(height):
        for x in range(int(width * 0.8), width):  # Focus on the rightmost 20% of the image
            if binary[y, x] == 255:  # If a bright pixel is detected
                cv2.rectangle(mask, (x - 50, y - 10), (x + 50, y + 10), 255, -1)  # Adjust rectangle size

    # Apply the mask to hide timestamps and checkmarks
    processed = cv2.bitwise_and(gray, gray, mask=~mask)

    # Convert back to PIL Image format
    return Image.fromarray(processed)



def filter_recognized_text(text):
    """Фильтрует текст, оставляя только корректные строки."""
    # Список символов, которые нужно удалить
    symbols_to_remove = [',', '.']  # Можно добавить другие символы при необходимости

    filtered_lines = []
    for line in text.splitlines():
        # Удаляем символы из строки
        for symbol in symbols_to_remove:
            line = line.replace(symbol, '')

        # Пропускаем пустые строки после удаления символов
        if not line.strip():
            continue

        # Фильтруем строки, которые содержат только буквы, цифры и пробелы
        if re.match(r'^[а-яА-ЯёЁa-zA-Z0-9\s]+$', line):
            filtered_lines.append(line.strip())

    # Возвращаем строки, объединённые в одну строку через пробел
    return " ".join(filtered_lines)


def capture_and_recognize(region):
    """Capture and recognize text only when the image changes."""
    try:
        # Take a screenshot
        screenshot = pyautogui.screenshot(region=region)
        # Preprocess the image (if needed)
        processed_image = preprocess_image(screenshot)

        # Perform OCR
        custom_config = r'--oem 3 --psm 6'
        text = pytesseract.image_to_string(processed_image, lang='rus', config=custom_config)

        logging.debug(f"Recognized text (before filtering):\n{text}")

        # Filter the recognized text
        #filtered_text = filter_recognized_text(text)

        logging.debug(f"Recognized text (after filtering):\n{text}")

        return text

    except Exception as e:
        logging.error(f"Error during capture and recognition: {e}")
        return None

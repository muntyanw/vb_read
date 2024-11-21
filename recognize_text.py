import cv2
import numpy as np
import logging
from PIL import Image
import pyautogui
import pytesseract
import re

def preprocess_image(pil_image):
    """Преобразование изображения для улучшения OCR."""
    # Convert PIL Image to OpenCV format
    image = np.array(pil_image)

    # Convert to grayscale
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

    # Apply adaptive thresholding to handle uneven lighting
    binary = cv2.adaptiveThreshold(
        gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 2
    )

    # Optionally apply Gaussian blur to reduce noise
    blurred = cv2.GaussianBlur(binary, (3, 3), 0)

    # Convert back to PIL Image format
    return Image.fromarray(blurred)


def filter_recognized_text(text):
    """Фильтрует текст, оставляя только корректные строки."""
    # Убираем лишние символы, такие как > и некорректные символы
    filtered_lines = []
    for line in text.splitlines():
        # Пропускаем пустые строки
        if not line.strip():
            continue
        # Фильтруем строки, которые содержат только буквы, цифры и пробелы
        if re.match(r'^[а-яА-ЯёЁa-zA-Z0-9\s]+$', line):
            filtered_lines.append(line.strip())
    return " ".join(filtered_lines)

def capture_and_recognize(region):
    """Capture and recognize text only when the image changes."""
    try:
        # Take a screenshot
        screenshot = pyautogui.screenshot(region=region)
        # Preprocess the image (if needed)
        #processed_image = preprocess_image(screenshot)

        # Perform OCR
        custom_config = r'--oem 3 --psm 6'
        text = pytesseract.image_to_string(screenshot, lang='rus', config=custom_config)

        logging.debug(f"Recognized text (before filtering):\n{text}")

        # Filter the recognized text
        filtered_text = filter_recognized_text(text)

        logging.debug(f"Recognized text (after filtering):\n{filtered_text}")

        return filtered_text

    except Exception as e:
        logging.error(f"Error during capture and recognition: {e}")
        return None

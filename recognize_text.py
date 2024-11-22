import log
import pyautogui
import pytesseract
import re
from utils import read_setting
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

    return text


def capture_and_recognize(region):
    """Capture and recognize text only when the image changes."""
    try:
        # Take a screenshot
        screenshot = pyautogui.screenshot(region=region)
        # Preprocess the image (if needed)
        processed_image = preprocess_image(screenshot)

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

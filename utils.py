import json
from log import log_and_print
import os
import cv2
import numpy as np
import pyautogui
from typing import Union

ImageLike = Union[str, np.ndarray]

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


def read_setting(field_path):

    file_path = "settings.json"
    try:
        # Open and load the JSON file
        with open(file_path, 'r', encoding='utf-8') as file:
            settings = json.load(file)

        # Navigate to the desired field
        keys = field_path.split('.')
        value = settings
        for key in keys:
            value = value[key]

        return value
    except (FileNotFoundError, KeyError, json.JSONDecodeError) as e:
        print(f"Error reading field '{field_path}' from '{file_path}': {e}")
        return None

def write_setting(field_path, new_value):
    """
    Writes a new value to a specific field in a JSON settings file.

    :param field_path: Dot-separated path to the field (e.g., "capture_and_recognize.lang").
    :param new_value: The new value to set for the specified field.
    """
    file_path = "settings.json"

    try:
        # Open and load the JSON file
        with open(file_path, 'r', encoding='utf-8') as file:
            settings = json.load(file)

        # Navigate to the desired field and set the new value
        keys = field_path.split('.')
        value = settings
        for key in keys[:-1]:  # Traverse to the second-to-last key
            value = value[key]

        value[keys[-1]] = new_value  # Set the new value at the final key

        # Write the modified settings back to the file
        with open(file_path, 'w', encoding='utf-8') as file:
            json.dump(settings, file, indent=4)
        log_and_print(f"[write_setting] Field '{field_path}' updated successfully. new_value = {new_value}")

    except (FileNotFoundError, KeyError, json.JSONDecodeError) as e:
        log_and_print(f"[write_setting] Error writing field '{field_path}' to '{file_path}': {e}")

def load_json(file_path):
    log_and_print(f"Загрузка данных из JSON файла {file_path}.", 'info')
    try:
        with open(file_path, 'r', encoding='utf-8') as file:
            data = json.load(file)
        log_and_print(f"Данные успешно загружены из {file_path}.", 'info')
        return data
    except FileNotFoundError:
        log_and_print(f"Файл {file_path} не найден.", 'error')
        return None
    except json.JSONDecodeError:
        log_and_print(f"Ошибка декодирования JSON в файле {file_path}.", 'error')
        return None

def get_latest_file(download_folder):
    try:
        files = os.listdir(download_folder)
        paths = [os.path.join(download_folder, fname) for fname in files]
        latest_file = max(paths, key=os.path.getctime)
        return latest_file
    except Exception as e:
        print(f"Ошибка при получении последнего файла: {e}")
        return None

def is_video_file(file_path):
    """
    Определяет, является ли файл видео по его расширению.

    :param file_path: Путь к файлу.
    :return: True, если файл является видео, иначе False.
    """
    # Список расширений видеофайлов
    video_extensions = {".mp4", ".mkv", ".avi", ".mov", ".wmv", ".flv", ".webm", ".m4v"}

    # Получаем расширение файла
    file_extension = file_path.lower().split('.')[-1]

    # Проверяем, есть ли расширение в списке видео
    return f".{file_extension}" in video_extensions

def get_video_dimensions_cv2(file_path):
    cap = cv2.VideoCapture(file_path)
    if not cap.isOpened():
        return None, None, None, None
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = cap.get(cv2.CAP_PROP_FPS)
    duration = cap.get(cv2.CAP_PROP_FRAME_COUNT) / fps if fps else None
    cap.release()
    return width, height, duration, fps

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

def draw_match_overlay(
    img, x, y, w, h, *,
    idx=None, score=None, y_boundary=None,
    show_zoom=True, zoom_scale=2, zoom_size_min=120
):

    H, W = img.shape[:2]
    bgr = img if img.ndim == 3 else cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)

    # 1) Bounding box (high contrast + anti-aliased)
    cv2.rectangle(bgr, (x, y), (x+w, y+h), (0, 255, 0), 2, lineType=cv2.LINE_AA)

    # 2) Top-left crosshair
    cv2.drawMarker(bgr, (x, y), (0, 0, 255), markerType=cv2.MARKER_TILTED_CROSS, markerSize=16, thickness=2)

    # 3) Global boundary line
    if y_boundary is not None:
        cv2.line(bgr, (0, y_boundary), (W, y_boundary), (255, 0, 0), 1, lineType=cv2.LINE_AA)

    # 4) Semi-transparent highlight in the box
    overlay = bgr.copy()
    cv2.rectangle(overlay, (x, y), (x+w, y+h), (0, 255, 0), -1)
    bgr = cv2.addWeighted(overlay, 0.15, bgr, 0.85, 0)

    # 5) Label box (index, coords, score)
    label = []
    if idx is not None: label.append(f"#{idx}")
    label.append(f"x={x} y={y} w={w} h={h}")
    if score is not None: label.append(f"s={score:.3f}")
    text = "  ".join(label)
    (tw, th), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 0.55, 1)
    pad = 6
    bx, by = x, max(0, y - th - 2*pad - 2)
    cv2.rectangle(bgr, (bx, by), (bx+tw+2*pad, by+th+2*pad), (0, 0, 0), -1)
    cv2.putText(bgr, text, (bx+pad, by+th+pad), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255,255,255), 1, cv2.LINE_AA)

    # 6) Zoom inset (optional)
    if show_zoom:
        cx, cy = x + w//2, y + h//2
        crop = bgr[max(0,y):min(H,y+h), max(0,x):min(W,x+w)].copy()
        if crop.size > 0:
            zh = max(zoom_size_min, crop.shape[0]*zoom_scale)
            zw = max(zoom_size_min, crop.shape[1]*zoom_scale)
            zoom = cv2.resize(crop, (zw, zh), interpolation=cv2.INTER_NEAREST)
            # place inset at top-right with border
            inset_x = max(0, W - zw - 10); inset_y = 10
            bgr[inset_y:inset_y+zh, inset_x:inset_x+zw] = zoom
            cv2.rectangle(bgr, (inset_x, inset_y), (inset_x+zw, inset_y+zh), (50,50,50), 1)

    return bgr

def take_screenshot(region):
    screenshot = pyautogui.screenshot(region=region)
    image_np = np.array(screenshot)
    return image_np

import cv2
import numpy as np

def _safe_show(img_bgr, delay_ms: int = 1000, win_name: str = "Screen with region"):
    """Use your showImage if available; otherwise fallback to cv2.imshow."""
    try:
        showImage(img_bgr, delay_ms)  # your helper
    except Exception:
        cv2.imshow(win_name, img_bgr)
        cv2.waitKey(delay_ms)
        try:
            cv2.destroyWindow(win_name)
        except Exception:
            pass

def show_screen_with_region(
    region,                      # (x, y, w, h) in screen coordinates
    delay_ms: int = 1000,
    border_color = (0, 255, 0),  # BGR
    thickness: int = 3,
    dim_background: bool = True  # darken non-selected area
):
    """
    Capture full screen, draw a rectangle around `region`, and display.
    Region is highlighted on the *full-screen* image so you see where it is.
    """
    try:
        # 1) Capture full screen (replace with your own if you have one)
        # If you already have a full-screen capture helper, use it here:
        # full_bgr = take_full_screenshot()
        # Fallback using pyautogui (returns PIL.Image in RGB):
        import pyautogui
        pil_img = pyautogui.screenshot()  # full screen
        full_bgr = cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)

        # 2) Draw overlay
        x, y, w, h = region
        H, W = full_bgr.shape[:2]
        dbg = full_bgr.copy()

        if dim_background:
            # Slightly darken everything except the region
            overlay = dbg.copy()
            overlay[:] = (0, 0, 0)
            alpha = 0.45
            dbg = cv2.addWeighted(overlay, alpha, dbg, 1 - alpha, 0)
            # Paste original region back to keep it bright
            x2, y2 = max(0, x), max(0, y)
            x3, y3 = min(W, x + w), min(H, y + h)
            if x2 < x3 and y2 < y3:
                dbg[y2:y3, x2:x3] = full_bgr[y2:y3, x2:x3]

        # 3) Draw border and corner crosshair
        cv2.rectangle(dbg, (x, y), (x + w, y + h), border_color, thickness, lineType=cv2.LINE_AA)
        cv2.drawMarker(dbg, (x, y), (0, 0, 255), markerType=cv2.MARKER_TILTED_CROSS, markerSize=18, thickness=2)

        # 4) Add a small label with coords
        label = f"region x={x} y={y} w={w} h={h}"
        (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 1)
        bx, by = max(4, x), max(0, y - th - 10)
        cv2.rectangle(dbg, (bx, by), (bx + tw + 10, by + th + 10), (0, 0, 0), -1)
        cv2.putText(dbg, label, (bx + 5, by + th + 5), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255,255,255), 1, cv2.LINE_AA)

        # 5) Show
        _safe_show(dbg, delay_ms)

    except Exception as e:
        print(f"Error in show_screen_with_region: {e}")



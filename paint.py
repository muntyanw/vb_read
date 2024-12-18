import ctypes
import time
import cv2
import numpy as np
from PIL import ImageGrab
from log import log_and_print
from recognize_text import capture_and_recognize
from PIL import Image

# Константы для окна
SW_SHOW = 5
WS_POPUP = 0x80000000
WS_VISIBLE = 0x10000000
WS_EX_TOPMOST = 0x00000008
WS_EX_LAYERED = 0x00080000
LWA_COLORKEY = 0x00000001

class RECT(ctypes.Structure):
    _fields_ = [("left", ctypes.c_long),
                ("top", ctypes.c_long),
                ("right", ctypes.c_long),
                ("bottom", ctypes.c_long)]

def create_colorref(red, green, blue):
    """
    Преобразует RGB в COLORREF.
    """
    return (blue << 16) | (green << 8) | red

def highlight_circle(x, y, duration=2, size=50, color="red", remove=False):
    """
    Визуально подсвечивает точку на экране временным кругом.

    :param x: Координата X центра круга.
    :param y: Координата Y центра круга.
    :param duration: Длительность подсветки в секундах.
    :param size: Диаметр круга.
    :param color: Цвет круга (например, "red", "green", "blue").
    """
    # Карта цветов
    color_map = {
        "red": (255, 0, 0),
        "green": (0, 255, 0),
        "blue": (0, 0, 255),
        "yellow": (255, 255, 0),
        "white": (255, 255, 255),
        "black": (0, 0, 0),
    }

    # Получаем RGB для заданного цвета
    rgb = color_map.get(color.lower(), (255, 0, 0))
    colorref = create_colorref(*rgb)

    # Создаём окно
    hwnd = ctypes.windll.user32.CreateWindowExW(
        0,
        "STATIC",
        None,
        WS_POPUP | WS_VISIBLE,
        x - size // 2,
        y - size // 2,
        size,
        size,
        None,
        None,
        None,
        None,
    )

    # Получаем контекст устройства (DC) для окна
    hdc = ctypes.windll.user32.GetDC(hwnd)

    # Создаём кисть и рисуем круг
    brush = ctypes.windll.gdi32.CreateSolidBrush(colorref)
    pen = ctypes.windll.gdi32.CreatePen(0, 1, colorref)  # Перо для границы

    old_brush = ctypes.windll.gdi32.SelectObject(hdc, brush)
    old_pen = ctypes.windll.gdi32.SelectObject(hdc, pen)

    # Рисуем круг (как эллипс с равной шириной и высотой)
    ctypes.windll.gdi32.Ellipse(hdc, 0, 0, size, size)

    # Возвращаем старые объекты и удаляем ресурсы
    ctypes.windll.gdi32.SelectObject(hdc, old_brush)
    ctypes.windll.gdi32.SelectObject(hdc, old_pen)
    ctypes.windll.gdi32.DeleteObject(brush)
    ctypes.windll.gdi32.DeleteObject(pen)

    # Показываем окно
    ctypes.windll.user32.ShowWindow(hwnd, SW_SHOW)

    # Ждём указанное время
    time.sleep(duration)

    if remove:
        # Удаляем окно
        ctypes.windll.user32.DestroyWindow(hwnd)

    return hwnd

def highlight_point(x, y, duration=2, size=50, color="red"):
    """
    Визуально подсвечивает точку на экране временной фигурой.

    :param x: Координата X.
    :param y: Координата Y.
    :param duration: Длительность подсветки в секундах.
    :param size: Размер подсветки (диаметр круга или размер квадрата).
    :param color: Цвет подсветки (например, "red", "green", "blue").
    """
    # Карта цветов
    color_map = {
        "red": (255, 0, 0),
        "green": (0, 255, 0),
        "blue": (0, 0, 255),
        "yellow": (255, 255, 0),
        "white": (255, 255, 255),
        "black": (0, 0, 0),
    }

    # Получаем RGB для заданного цвета
    rgb = color_map.get(color.lower(), (255, 0, 0))
    colorref = create_colorref(*rgb)

    # Создаём окно
    hwnd = ctypes.windll.user32.CreateWindowExW(
        0,
        "STATIC",
        None,
        WS_POPUP | WS_VISIBLE,
        x - size // 2,
        y - size // 2,
        size,
        size,
        None,
        None,
        None,
        None,
    )

    # Получаем контекст устройства (DC) для окна
    hdc = ctypes.windll.user32.GetDC(hwnd)

    # Создаём кисть и рисуем квадрат
    brush = ctypes.windll.gdi32.CreateSolidBrush(colorref)
    pen = ctypes.windll.gdi32.CreatePen(0, 1, colorref)  # Перо для границы

    old_brush = ctypes.windll.gdi32.SelectObject(hdc, brush)
    old_pen = ctypes.windll.gdi32.SelectObject(hdc, pen)

    ctypes.windll.gdi32.Rectangle(hdc, 0, 0, size, size)

    # Возвращаем старые объекты и удаляем ресурсы
    ctypes.windll.gdi32.SelectObject(hdc, old_brush)
    ctypes.windll.gdi32.SelectObject(hdc, old_pen)
    ctypes.windll.gdi32.DeleteObject(brush)
    ctypes.windll.gdi32.DeleteObject(pen)

    # Показываем окно
    ctypes.windll.user32.ShowWindow(hwnd, SW_SHOW)

    # Ждём указанное время
    time.sleep(duration)

    # Удаляем окно
    ctypes.windll.user32.DestroyWindow(hwnd)

def create_highlight_window(x, y, width, height, color=(255, 0, 0)):
    """
    Создаёт временное окно для визуального выделения области.

    :param x: Координата X верхнего левого угла.
    :param y: Координата Y верхнего левого угла.
    :param width: Ширина области.
    :param height: Высота области.
    :param color: Цвет выделения (по умолчанию красный).
    :return: Хендлер окна.
    """
    hwnd = ctypes.windll.user32.CreateWindowExW(
        WS_EX_TOPMOST | WS_EX_LAYERED,
        "STATIC",
        None,
        WS_POPUP | WS_VISIBLE,
        x,
        y,
        width,
        height,
        None,
        None,
        None,
        None,
    )

    # Получаем контекст устройства (DC) для окна
    hdc = ctypes.windll.user32.GetDC(hwnd)

    # Создаём кисть
    brush = ctypes.windll.gdi32.CreateSolidBrush((color[2] << 16) | (color[1] << 8) | color[0])

    # Рисуем прямоугольник с использованием функции Rectangle
    pen = ctypes.windll.gdi32.CreatePen(0, 1, (color[2] << 16) | (color[1] << 8) | color[0])
    old_brush = ctypes.windll.gdi32.SelectObject(hdc, brush)
    old_pen = ctypes.windll.gdi32.SelectObject(hdc, pen)

    ctypes.windll.gdi32.Rectangle(hdc, 0, 0, width, height)

    # Возвращаем старые объекты и удаляем ресурсы
    ctypes.windll.gdi32.SelectObject(hdc, old_brush)
    ctypes.windll.gdi32.SelectObject(hdc, old_pen)
    ctypes.windll.gdi32.DeleteObject(brush)
    ctypes.windll.gdi32.DeleteObject(pen)

    # Устанавливаем окно как прозрачное
    ctypes.windll.user32.SetLayeredWindowAttributes(hwnd, 0x000000, 128, LWA_COLORKEY)

    ctypes.windll.user32.ShowWindow(hwnd, SW_SHOW)
    return hwnd

def destroy_highlight_window(hwnd):
    """
    Удаляет окно выделения.
    """
    ctypes.windll.user32.DestroyWindow(hwnd)

def find_image_upward_with_highlight(start_x, start_y, y_max, height, template_path):
    """
    Ищет образ на экране начиная с заданных координат в направлении вверх,
    с визуальным выделением области.

    :param start_x: Координата X нижнего левого угла области поиска.
    :param start_y: Координата Y нижнего левого угла области поиска.
    :param y_max: Верхняя граница поиска.
    :param height: Высота области поиска.
    :param template_path: Путь к файлу изображения-образа (шаблона).
    :return: Координата Y верхнего угла найденного образа или None, если образ не найден.
    """
    # Загружаем шаблон
    template = cv2.imread(template_path, cv2.IMREAD_GRAYSCALE)

    if template is None:
        raise FileNotFoundError(f"Template image not found: {template_path}")

    # Отображаем шаблон для проверки
    cv2.imshow("Template (Gray)", template)
    cv2.waitKey(1)  # Ждем 1 мс для отображения окна

    template_height, template_width = template.shape
    width = template_width  # Ширина области поиска равна ширине шаблона
    step = 2  # Шаг поиска

    current_y = start_y
    min_y = y_max - height

    log_and_print(f"height = {height}, min_y = {min_y}")

    while current_y >= min_y:
        log_and_print(f"start_x = {start_x}, current_y = {current_y}, min_y = {min_y}")

        # Снимаем скриншот текущей области
        bbox = (start_x, current_y - template_height, start_x + template_width, current_y)
        screenshot = ImageGrab.grab(bbox)

        # Преобразуем скриншот в оттенки серого
        screen_gray = cv2.cvtColor(np.array(screenshot), cv2.COLOR_BGR2GRAY)

        # Отображаем текущую область для проверки
        cv2.imshow("Current Screenshot (Gray)", screen_gray)
        cv2.waitKey(1)  # Обновляем окно OpenCV
        #time.sleep(2)  # Ждем 2 секунды для визуализации

        # Сравниваем шаблон с текущим изображением
        res = cv2.matchTemplate(screen_gray, template, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, max_loc = cv2.minMaxLoc(res)

        log_and_print(f"current_y = {current_y}, max_val = {max_val}")

        # Если шаблон найден
        if max_val > 0.3:  # Порог совпадения
            found_y = current_y - template_height + max_loc[1]
            cv2.destroyAllWindows()  # Закрываем окна после завершения
            return found_y

        # Шаг вверх
        current_y -= step

    cv2.destroyAllWindows()  # Закрываем окна после завершения
    return None

def find_text_upward_with_highlight(start_x, start_y, y_max, height, template_height, template_width, template_text):
    """
    Ищет образ на экране начиная с заданных координат в направлении вверх,
    с визуальным выделением области.

    :param start_x: Координата X нижнего левого угла области поиска.
    :param start_y: Координата Y нижнего левого угла области поиска.
    :param y_max: Верхняя граница поиска.
    :param height: Высота области поиска.
    :param template_path: Путь к файлу изображения-образа (шаблона).
    :return: Координата Y верхнего угла найденного образа или None, если образ не найден.
    """
    step = int(template_height / 2)  # Шаг поиска

    current_y = start_y
    min_y = y_max - height

    log_and_print(f"height = {height}, min_y = {min_y}")

    while current_y >= min_y:
        log_and_print(f"start_x = {start_x}, current_y = {current_y}, min_y = {min_y}")

        # Снимаем скриншот текущей области
        region = (start_x, current_y, template_width, template_height)

        text = capture_and_recognize(region)

        log_and_print(f"text = {text}")

        # Если шаблон найден
        if text and template_text in text:
            log_and_print(f"text знайдений")
            found_y = current_y
            cv2.destroyAllWindows()  # Закрываем окна после завершения
            return found_y

        # Шаг вверх
        current_y -= step
        # time.sleep(3)

    cv2.destroyAllWindows()  # Закрываем окна после завершения
    return None

def get_image_height(file_path):
    """
    Determines the height of an image file.

    Args:
        file_path (str): Path to the image file.

    Returns:
        int: Height of the image in pixels.
    """
    try:
        # Open the image file
        with Image.open(file_path) as img:
            # Get the height of the image
            height = img.height
            return height
    except Exception as e:
        # Handle exceptions (e.g., file not found or unsupported format)
        print(f"Error: {e}")
        return None

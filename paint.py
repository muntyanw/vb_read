import ctypes
import time
import cv2
import numpy as np
from PIL import ImageGrab
from log import log_and_print
from recognize_text import capture_and_recognize
from PIL import Image
import tkinter as tk

# Константы для окна
SW_SHOW = 5
WS_POPUP = 0x80000000
WS_VISIBLE = 0x10000000
WS_EX_TOPMOST = 0x00000008
WS_EX_LAYERED = 0x00080000
LWA_COLORKEY = 0x00000001

HWND_TOPMOST = -1
SWP_NOSIZE = 0x0001
SWP_NOMOVE = 0x0002
SWP_NOACTIVATE = 0x0010

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

def show_position(x, y, duration=2, size=50, color="red"):
    """
    Показывает положение на экране с использованием Tkinter.

    :param x: Координата X для позиционирования окна.
    :param y: Координата Y для позиционирования окна.
    :param duration: Длительность показа окна в секундах.
    :param size: Размер окна (ширина и высота).
    :param color: Цвет фона окна.
    """
    root = tk.Tk()
    root.title("Position Indicator")

    # Устанавливаем размер окна и позицию
    root.geometry(f"{size}x{size}+{x}+{y}")

    # Устанавливаем прозрачность окна
    root.attributes('-alpha', 0.5)  # Полупрозрачное окно

    # Устанавливаем цвет фона
    root.configure(bg=color)

    # Функция для автоматического закрытия окна
    root.after(int(duration * 1000), root.destroy)

    root.mainloop()

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

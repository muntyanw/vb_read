import tkinter as tk
from log import log_and_print
import pyautogui

class ScreenRegionSelector:
    def __init__(self):
        self.root = tk.Tk()

        # Полноэкранное окно и полупрозрачность
        self.root.attributes("-fullscreen", True)  # Окно на весь экран
        self.root.attributes("-alpha", 0.5)  # Полупрозрачность
        self.root.config(cursor="crosshair")  # Курсор в виде крестика

        # Окно всегда поверх других окон
        self.root.attributes("-topmost", True)

        self.canvas = tk.Canvas(self.root, cursor="crosshair")
        self.canvas.pack(fill=tk.BOTH, expand=True)

        # Переменные для хранения координат
        self.start_x = None
        self.start_y = None
        self.rect = None

        # Привязка событий
        self.canvas.bind("<ButtonPress-1>", self.on_mouse_press)
        self.canvas.bind("<B1-Motion>", self.on_mouse_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_mouse_release)

        self.selected_region = None  # для хранения координат выделенной области

    def on_mouse_press(self, event):
        """Запоминаем начальную точку выделения"""
        self.start_x = event.x
        self.start_y = event.y

        # Создаем прямоугольник на холсте
        if self.rect:
            self.canvas.delete(self.rect)
        self.rect = self.canvas.create_rectangle(self.start_x, self.start_y, self.start_x, self.start_y, outline='black')

    def on_mouse_drag(self, event):
        """Обновляем прямоугольник, когда мышь перетаскивается"""
        if self.rect:
            self.canvas.coords(self.rect, self.start_x, self.start_y, event.x, event.y)

    def on_mouse_release(self, event):
        """Когда выделение завершено, возвращаем координаты"""
        end_x, end_y = event.x, event.y
        self.selected_region = (self.start_x, self.start_y, end_x, end_y)
        log_and_print(f"Выделенная область: от ({self.start_x}, {self.start_y}) до ({end_x}, {end_y})")

        # Закрытие окна после завершения выделения
        self.root.destroy()  # Закрываем окно после завершения выделения

    def get_selected_region(self):
        """Метод для получения выбранной области"""
        return self.selected_region

    def run(self):
        """Запуск основного цикла Tkinter"""
        self.root.mainloop()

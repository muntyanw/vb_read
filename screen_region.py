from log import log_and_print
import json
import sys
import tkinter as tk

def read_region_from_json(json_file='region.json'):
    log_and_print(f"Чтение области экрана из файла {json_file}")
    try:
        with open(json_file, 'r') as f:
            data = json.load(f)
        left = data['left']
        top = data['top']
        width = data['width']
        height = data['height']
        log_and_print(f"Считанная область из JSON: left={left}, top={top}, width={width}, height={height}")
        return left, top, width, height
    except Exception as e:
        log_and_print(f"Ошибка при чтении файла {json_file}: {e}")
        sys.exit(1)

def save_region_to_json(left, top, width, height, json_file='region.json'):
    log_and_print(f"Сохранение области экрана в файл {json_file}")
    try:
        data = {'left': left, 'top': top, 'width': width, 'height': height}
        with open(json_file, 'w') as f:
            json.dump(data, f)
        log_and_print(f"Новая область сохранена в файл {json_file}")
    except Exception as e:
        log_and_print(f"Ошибка при сохранении области экрана в файл {json_file}: {e}")

def draw_rectangle_on_screen(left, top, width, height):
    log_and_print("Рисование прямоугольника на экране")
    try:
        root = tk.Tk()
        root.overrideredirect(True)
        root.geometry(f"{width}x{height}+{left}+{top}")
        root.lift()
        root.wm_attributes("-topmost", True)

        # Попытка установить прозрачность окна
        try:
            root.wm_attributes("-alpha", 0.3)  # Прозрачность окна
            log_and_print("Установлена прозрачность окна")
        except Exception as e:
            log_and_print(f"Прозрачность окна не поддерживается: {e}")

        # Рисуем рамку
        canvas = tk.Canvas(root, width=width, height=height, bg='white')
        canvas.pack()
        canvas.create_rectangle(0, 0, width, height, outline='red', width=3)

        # Возвращаем объект окна для дальнейшего управления
        return root
    except Exception as e:
        log_and_print(f"Ошибка при рисовании прямоугольника: {e}")
        sys.exit(1)

def select_region():
    # Функция для выбора области экрана с помощью мыши
    log_and_print("Пожалуйста, выберите новую область экрана")

    root = tk.Tk()
    root.attributes("-topmost", True)
    root.attributes("-fullscreen", True)
    root.attributes("-alpha", 0.2)
    root.configure(background='black')

    canvas = tk.Canvas(root, cursor="crosshair", bg='black')
    canvas.pack(fill=tk.BOTH, expand=True)

    rect = None
    start_x = None
    start_y = None
    abs_start_x = None
    abs_start_y = None
    abs_end_x = None
    abs_end_y = None

    def on_mouse_down(event):
        nonlocal start_x, start_y, abs_start_x, abs_start_y
        start_x = event.x
        start_y = event.y
        abs_start_x = event.x_root
        abs_start_y = event.y_root

    def on_mouse_move(event):
        nonlocal rect
        if rect:
            canvas.delete(rect)
        rect = canvas.create_rectangle(
            start_x, start_y, event.x, event.y, outline='red', width=2
        )

    def on_mouse_up(event):
        nonlocal abs_end_x, abs_end_y
        abs_end_x = event.x_root
        abs_end_y = event.y_root
        root.quit()  # Выходим из mainloop

    canvas.bind("<ButtonPress-1>", on_mouse_down)
    canvas.bind("<B1-Motion>", on_mouse_move)
    canvas.bind("<ButtonRelease-1>", on_mouse_up)

    root.mainloop()
    root.destroy()  # Закрываем окно после выхода из mainloop

    # Вычисляем координаты после завершения mainloop
    x1 = min(abs_start_x, abs_end_x)
    y1 = min(abs_start_y, abs_end_y)
    x2 = max(abs_start_x, abs_end_x)
    y2 = max(abs_start_y, abs_end_y)
    width = x2 - x1
    height = y2 - y1
    log_and_print(f"Новая область выбрана: left={x1}, top={y1}, width={width}, height={height}")
    return x1, y1, width, height

import logging
import json
import sys
import tkinter as tk
import platform

def read_region_from_json(json_file='region.json'):
    logging.debug(f"Чтение области экрана из файла {json_file}")
    try:
        with open(json_file, 'r') as f:
            data = json.load(f)
        left = data['left']
        top = data['top']
        width = data['width']
        height = data['height']
        logging.info(f"Считанная область из JSON: left={left}, top={top}, width={width}, height={height}")
        return left, top, width, height
    except Exception as e:
        logging.error(f"Ошибка при чтении файла {json_file}: {e}")
        sys.exit(1)

def save_region_to_json(left, top, width, height, json_file='region.json'):
    logging.debug(f"Сохранение области экрана в файл {json_file}")
    try:
        data = {'left': left, 'top': top, 'width': width, 'height': height}
        with open(json_file, 'w') as f:
            json.dump(data, f)
        logging.info(f"Новая область сохранена в файл {json_file}")
    except Exception as e:
        logging.error(f"Ошибка при сохранении области экрана в файл {json_file}: {e}")

def draw_rectangle_on_screen(left, top, width, height):
    logging.debug("Рисование прямоугольника на экране")
    try:
        root = tk.Tk()
        root.overrideredirect(True)
        root.geometry(f"{width}x{height}+{left}+{top}")
        root.lift()
        root.wm_attributes("-topmost", True)

        # Попытка установить прозрачность окна
        try:
            root.wm_attributes("-alpha", 0.3)  # Прозрачность окна
            logging.debug("Установлена прозрачность окна")
        except Exception as e:
            logging.warning(f"Прозрачность окна не поддерживается: {e}")

        # Рисуем рамку
        canvas = tk.Canvas(root, width=width, height=height, bg='white')
        canvas.pack()
        canvas.create_rectangle(0, 0, width, height, outline='red', width=3)

        # Возвращаем объект окна для дальнейшего управления
        return root
    except Exception as e:
        logging.error(f"Ошибка при рисовании прямоугольника: {e}")
        sys.exit(1)

def select_region():
    # Функция для выбора области экрана с помощью мыши
    logging.info("Пожалуйста, выберите новую область экрана")

    root = tk.Tk()
    root.attributes("-topmost", True)
    root.attributes("-fullscreen", True)

    system = platform.system()

    if system == 'Windows':
        # Решение для Windows
        root.attributes("-transparentcolor", 'grey')
        root.config(bg='grey')
        canvas = tk.Canvas(root, cursor="crosshair", bg='grey')
    else:
        # Решение для других систем
        root.attributes("-alpha", 0.2)
        canvas = tk.Canvas(root, cursor="crosshair", bg='black')

    canvas.pack(fill=tk.BOTH, expand=True)

    selection = {'x1': None, 'y1': None, 'x2': None, 'y2': None}
    rect = None

    def on_mouse_down(event):
        selection['x1'] = event.x_root
        selection['y1'] = event.y_root

    def on_mouse_move(event):
        nonlocal rect
        if rect:
            canvas.delete(rect)
        selection['x2'] = event.x_root
        selection['y2'] = event.y_root
        rect = canvas.create_rectangle(
            selection['x1'], selection['y1'], selection['x2'], selection['y2'], outline='red', width=2
        )

    def on_mouse_up(event):
        selection['x2'] = event.x_root
        selection['y2'] = event.y_root
        root.destroy()

    canvas.bind("<ButtonPress-1>", on_mouse_down)
    canvas.bind("<B1-Motion>", on_mouse_move)
    canvas.bind("<ButtonRelease-1>", on_mouse_up)

    root.mainloop()

    x1 = min(selection['x1'], selection['x2'])
    y1 = min(selection['y1'], selection['y2'])
    x2 = max(selection['x1'], selection['x2'])
    y2 = max(selection['y1'], selection['y2'])
    width = x2 - x1
    height = y2 - y1
    logging.info(f"Новая область выбрана: left={x1}, top={y1}, width={width}, height={height}")
    return x1, y1, width, height
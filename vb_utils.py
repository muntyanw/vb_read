import pywinauto
from pywinauto import Application, mouse
from log import log_and_print
import cv2
import numpy as np
from typing import Optional, Tuple, Union, Dict


ImageLike = Union[str, np.ndarray] 

def scroll_with_mouse(window, count_scroll, direction="down"):
    window.set_focus()

    # Находим панель с сообщениями
    chat_pane = window.child_window(control_type="Pane", found_index=0)

    # Получаем координаты панели
    rect = chat_pane.rectangle()
    center_x = (rect.left + rect.right) // 2
    center_y = (rect.top + rect.bottom) // 2

    # Прокручиваем вниз
    for _ in range(count_scroll):  # Повторяем несколько раз
        if direction == "down":
            mouse.scroll(coords=(center_x, center_y), wheel_dist=-1)  # Отрицательное значение для скроллинга вниз
            print("Scrolled down with mouse wheel")
        else:
            mouse.scroll(coords=(center_x, center_y), wheel_dist=1)
            print("Scrolled up with mouse wheel")

def right_click_on_panel(x_offset=0, y_offset=0):
    """
    Кликает правой кнопкой мыши на панели с сообщениями Viber.

    :param x_offset: Смещение по X относительно центра панели.
    :param y_offset: Смещение по Y относительно центра панели.
    """
    # Подключаемся к Viber
    app = Application(backend="uia").connect(title_re=".*Viber.*")
    window = app.window(title_re=".*Viber.*")
    window.set_focus()

    # Находим панель с сообщениями
    chat_pane = window.child_window(control_type="Pane", found_index=0)

    # Получаем координаты панели
    rect = chat_pane.rectangle()
    center_x = (rect.left + rect.right) // 2 + x_offset
    center_y = (rect.top + rect.bottom) // 2 + y_offset

    # Выполняем клик правой кнопкой мыши
    mouse.click(button="right", coords=(center_x, center_y))
    log_and_print(f"Right-clicked at ({center_x}, {center_y}) on the chat panel")
    return center_x, center_y

def right_click(app, window_title, x=0, y=0):
    """
    Устанавливает фокус на окно, а затем кликает правой кнопкой мыши по указанным координатам.

    Args:
        app: экземпляр pywinauto.Application
        window_title: название окна
        x: координата X для клика
        y: координата Y для клика
    """
    try:
        # Подключаемся к окну приложения
        window = app.window(title=window_title)

        # Устанавливаем фокус на окно
        window.set_focus()

        # Выполняем клик правой кнопкой мыши
        mouse.click(button="right", coords=(x, y))

        print(f"Right-clicked at ({x}, {y}) on the window '{window_title}'")
    except pywinauto.findwindows.ElementNotFoundError:
        print(f"Window with title '{window_title}' not found!")
    except Exception as e:
        print(f"Error during right-click: {e}")

def left_click(window, x=0, y=0):
    """
    Кликает левой кнопкой мыши
    """

    # Выполняем клик левой кнопкой мыши
    mouse.click(button="left", coords=(x, y))
    log_and_print(f"Left-clicked at ({x}, {y}) on the chat panel")

def _load_bgr(img: ImageLike) -> np.ndarray:
    """Завантажує зображення з файлу або прийнятого масиву у BGR."""
    if isinstance(img, str):
        im = cv2.imread(img, cv2.IMREAD_COLOR)
        if im is None:
            raise FileNotFoundError(f"Cannot read image: {img}")
        return im
    if isinstance(img, np.ndarray):
        if img.ndim == 2:
            return cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
        if img.ndim == 3:
            return img
    raise TypeError("img must be filepath or np.ndarray (H,W[,3])")

def find_message_bottom_by_image(
    screenshot: ImageLike,
    search_image: ImageLike,                        # <-- вместо search_words
    search_roi: Optional[Tuple[int, int, int, int]] = None,  # (x,y,w,h) як і раніше
    threshold: float = 0.83,                        # мін. кореляція для прийняття збігу
    scales: Tuple[float, ...] = tuple(np.linspace(0.85, 1.15, 9)),  # мульти-скейл
    return_debug: bool = False,
) -> Dict[str, Union[int, float, Tuple[int,int,int,int], np.ndarray]]:
    """
    Знаходить нижню межу повідомлення у Viber за шаблоном (search_image).

    Параметри (аналогічні попередньому методу):
      screenshot   : шлях або np.ndarray BGR повного скріну/ROI.
      search_image : шлях або np.ndarray BGR шаблону стику "бабл ↔ фон".
      search_roi   : (x,y,w,h) — обмеження області пошуку (опційно).
      threshold    : поріг прийняття збігу для TM_CCOEFF_NORMED.
      scales       : коефіцієнти масштабування шаблону (на випадок різних DPI/зуму).
      return_debug : якщо True — поверне скрін із розміткою.

    Повертає:
      {
        'x','y','w','h' : координати top-left та розмір збігу у всьому скріні,
        'rect'          : (x,y,w,h),
        'score'         : найкраще значення метрики,
        'y_boundary'    : y-координата лінії межі (центр шаблону по вертикалі),
        'debug_bgr'     : зображення з розміткою (якщо return_debug=True)
      }
    """
    img_bgr = _load_bgr(screenshot)
    tpl_bgr = _load_bgr(search_image)

    # Обмежуємо область пошуку, якщо задано
    if search_roi:
        rx, ry, rw, rh = search_roi
        roi_bgr = img_bgr[ry:ry+rh, rx:rx+rw]
    else:
        rx, ry, rw, rh = 0, 0, img_bgr.shape[1], img_bgr.shape[0]
        roi_bgr = img_bgr

    # Переходимо в відтінки сірого + легке згладжування
    roi_gray = cv2.cvtColor(roi_bgr, cv2.COLOR_BGR2GRAY)
    roi_gray = cv2.GaussianBlur(roi_gray, (3, 3), 0)

    tpl_gray_orig = cv2.cvtColor(tpl_bgr, cv2.COLOR_BGR2GRAY)
    tpl_gray_orig = cv2.GaussianBlur(tpl_gray_orig, (3, 3), 0)

    best = {"score": -1.0, "x": 0, "y": 0, "w": 0, "h": 0, "rect": (0,0,0,0)}

    # Мульти-скейл матчинг
    for s in scales:
        th = int(round(tpl_gray_orig.shape[0] * s))
        tw = int(round(tpl_gray_orig.shape[1] * s))
        if th < 3 or tw < 10:
            continue

        tpl_gray = cv2.resize(tpl_gray_orig, (tw, th), interpolation=cv2.INTER_AREA)
        res = cv2.matchTemplate(roi_gray, tpl_gray, cv2.TM_CCOEFF_NORMED)
        minVal, maxVal, minLoc, maxLoc = cv2.minMaxLoc(res)

        if maxVal > best["score"]:
            bx, by = maxLoc
            best.update({
                "score": float(maxVal),
                "x": int(rx + bx),
                "y": int(ry + by),
                "w": int(tw),
                "h": int(th),
                "rect": (int(rx + bx), int(ry + by), int(tw), int(th)),
            })

    if best["score"] < threshold:
        raise ValueError(
            f"No match above threshold {threshold:.2f}. Best score={best['score']:.3f}. "
            f"Try adjusting threshold/scales or refining search_roi."
        )

    # Лінія межі — середина шаблону по вертикалі
    y_boundary = best["y"] + best["h"] // 2
    best["y_boundary"] = int(y_boundary)

    if return_debug:
        dbg = img_bgr.copy()
        x, y, w, h = best["rect"]
        cv2.rectangle(dbg, (x, y), (x + w, y + h), (0, 255, 0), 2)
        cv2.line(dbg, (0, y_boundary), (dbg.shape[1], y_boundary), (255, 0, 0), 1)
        best["debug_bgr"] = dbg

    return best


from pywinauto import Application, mouse
from log import log_and_print
import asyncio
from tg import send_message_to_tg_channel
import re
from dispatcher.dispatch_client import send_for_analysis
import hashlib
import cv2
import numpy as np
from typing import Optional, Tuple, Union, Dict, List
from utils import take_screenshot, preprocess_image, show_screen_with_region
import cv2
import numpy as np
from typing import List, Tuple, Union

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

def right_click(window, x=0, y=0):
    """
    Кликает правой кнопкой мыши
    """
    window.set_focus()
    # Выполняем клик правой кнопкой мыши
    mouse.click(button="right", coords=(x, y))
    log_and_print(f"Right-clicked at ({x}, {y}) on the chat panel")

def left_click(window, x=0, y=0):
    """
    Кликает левой кнопкой мыши
    """

    # Выполняем клик левой кнопкой мыши
    mouse.click(button="left", coords=(x, y))
    log_and_print(f"Left-clicked at ({x}, {y}) on the chat panel")

# Глобальный флаг для предотвращения двойной реакции
processed_messages = set()
# Семафор для последовательной обработки сообщений
processing_semaphore = asyncio.Semaphore(1)

async def process_one_message_telegramm(message_text, bot_client, channel_name, name_viber, file_path):

    log_and_print(f"bot_client: {bot_client}", 'info')
    log_and_print(f"service_channel_name: {channel_name}", 'info')
    log_and_print(f"name_viber: {name_viber}", 'info')

    if message_text:
        # Добавляем ID сообщения в список обработанных
        processed_messages.add(message_text)
    elif file_path:
        processed_messages.add(file_path)


    # Обрабатываем сообщение последовательно с использованием семафора
    async with processing_semaphore:
        try:
            log_and_print(f'Обработка сообщения: {message_text}', 'info')

            await send_message_to_tg_channel(bot_client, channel_name, message_text, file_path)

        except Exception as e:
            log_and_print(f"Oшибка при обработке одного сообщения: {e}", 'error')
            await asyncio.sleep(10)  # Задержка

def reformat_telegram_text(input_text):
    """
    Takes a text, finds all text enclosed in single asterisks (*),
    and replaces them with double asterisks (**) for Telegram formatting.

    Args:
        input_text (str): The input text.

    Returns:
        str: The modified text with updated formatting.
    """
    # Regular expression to find text enclosed in single asterisks
    pattern = r'\*(.*?)\*'

    # Replace single asterisks with double asterisks
    formatted_text = re.sub(pattern, r'**\1**', input_text)

    return formatted_text

async def process_one_message_dispatcher(message_text, name_viber, file_path):

    log_and_print(f"name_viber: {name_viber}", 'info')

    if message_text:
        # Добавляем ID сообщения в список обработанных
        processed_messages.add(message_text)
    elif file_path:
        processed_messages.add(file_path)


    # Обрабатываем сообщение последовательно с использованием семафора
    async with processing_semaphore:
        try:
            log_and_print(f'Обработка сообщения: {message_text}', 'info')
            md5_hash = hashlib.md5(message_text.encode()).hexdigest()

            await send_for_analysis(
                message_id = md5_hash,
                text = message_text,
                chat_id = "UkrBusTravel",
                sender = None,
                attachments = None,
                locale = "uk",
                timeout_s = 8.0,
                retries = 2
            )

        except Exception as e:
            log_and_print(f"Oшибка при обработке одного сообщения: {e}", 'error')
            await asyncio.sleep(10)  # Задержка


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


def capture_and_find_image_boundary_coordinates(
    region,
    search_image: ImageLike,
    preprocess: bool = True,
    visualize: bool = False,
    threshold: float = 0.83
) -> List[Tuple[int, int, int, int]]:
    """
    Capture screenshot of `region`, find all matches of `search_image` (template),
    and return rectangles [(x, y, w, h)] in screenshot-local coordinates.
    If `visualize` is True, draw overlays and call showImage() right here.
    """

    try:
        
        # 7) Inline visualization (if requested)
        if visualize:
            show_screen_with_region(region, 3000)
        
        # 1) Capture screenshot of the region
        screenshot_np = take_screenshot(region)
        log_and_print("[capture_and_find_image_boundary_coordinates] Screenshot captured.")

        # 2) Optional preprocessing
        if preprocess:
            processed_image = preprocess_image(screenshot_np)
            log_and_print("[capture_and_find_image_boundary_coordinates] Image preprocessed.")
        else:
            processed_image = screenshot_np

        # 3) Load/prepare template
        if isinstance(search_image, str):
            tpl_bgr = cv2.imread(search_image, cv2.IMREAD_COLOR)
            if tpl_bgr is None:
                raise FileNotFoundError(f"Cannot read template: {search_image}")
        else:
            tpl_bgr = search_image
            if tpl_bgr.ndim == 2:
                tpl_bgr = cv2.cvtColor(tpl_bgr, cv2.COLOR_GRAY2BGR)

        # 4) Grayscale + light blur for robustness
        img_gray = cv2.cvtColor(processed_image, cv2.COLOR_BGR2GRAY) if processed_image.ndim == 3 else processed_image
        tpl_gray = cv2.cvtColor(tpl_bgr, cv2.COLOR_BGR2GRAY) if tpl_bgr.ndim == 3 else tpl_bgr
        img_gray = cv2.GaussianBlur(img_gray, (3, 3), 0)
        tpl_gray = cv2.GaussianBlur(tpl_gray, (3, 3), 0)

        th, tw = tpl_gray.shape[:2]

        # 5) Template matching (single-shot; OpenCV computes full response map)
        res = cv2.matchTemplate(img_gray, tpl_gray, cv2.TM_CCOEFF_NORMED)

        # 6) Collect all peaks above threshold
        ys, xs = np.where(res >= threshold)
        scores = res[ys, xs] if (len(ys) > 0) else np.array([])

        candidates = [(int(x0), int(y0), int(tw), int(th), float(sc))
                      for x0, y0, sc in zip(xs.tolist(), ys.tolist(), scores.tolist())]

        # Optional: simple NMS to avoid duplicate overlapping boxes
        def nms(boxes, iou_thresh=0.3):
            if not boxes:
                return []
            boxes = sorted(boxes, key=lambda b: b[4], reverse=True)
            picked = []

            def iou(a, b):
                ax1, ay1, aw, ah = a[0], a[1], a[2], a[3]
                bx1, by1, bw, bh = b[0], b[1], b[2], b[3]
                ax2, ay2 = ax1 + aw, ay1 + ah
                bx2, by2 = bx1 + bw, by1 + bh
                inter_x1 = max(ax1, bx1)
                inter_y1 = max(ay1, by1)
                inter_x2 = min(ax2, bx2)
                inter_y2 = min(ay2, by2)
                inter_w = max(0, inter_x2 - inter_x1)
                inter_h = max(0, inter_y2 - inter_y1)
                inter = inter_w * inter_h
                area_a = aw * ah
                area_b = bw * bh
                union = area_a + area_b - inter + 1e-9
                return inter / union

            while boxes:
                best = boxes.pop(0)
                picked.append(best)
                boxes = [b for b in boxes if iou(best, b) < iou_thresh]
            return picked

        picked = nms(candidates, iou_thresh=0.3)
        coordinates = [(x, y, w, h) for (x, y, w, h, _) in picked]

        log_and_print(f"[capture_and_find_image_boundary_coordinates] Matches: {len(coordinates)} (threshold={threshold}).")

        return coordinates

    except Exception as e:
        print(f"Ошибка в capture_and_find_image_boundary_coordinates: {e}")
        return []

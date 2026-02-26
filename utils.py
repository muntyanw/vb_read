import json
import string
from log import log_and_print
import os
import cv2
import numpy as np
import pyautogui
from typing import Union
import ctypes

os.environ["QT_LOGGING_RULES"] = "qt.qpa.windows.debug=false"

from typing import Tuple, Optional
import time
import win32api, win32con, win32gui

ImageLike = Union[str, np.ndarray]

def preprocess_image(image_np):
    """
    РџСЂРµРѕР±СЂР°Р·СѓРµС‚ РёР·РѕР±СЂР°Р¶РµРЅРёРµ РґР»СЏ СѓР»СѓС‡С€РµРЅРёСЏ РєР°С‡РµСЃС‚РІР° OCR.

    :param image_np: РР·РѕР±СЂР°Р¶РµРЅРёРµ РІ С„РѕСЂРјР°С‚Рµ NumPy РјР°СЃСЃРёРІР° (RGB)
    :return: РћР±СЂР°Р±РѕС‚Р°РЅРЅРѕРµ РёР·РѕР±СЂР°Р¶РµРЅРёРµ РІ РѕС‚С‚РµРЅРєР°С… СЃРµСЂРѕРіРѕ
    """
    # РџСЂРѕРІРµСЂСЏРµРј СЂР°Р·РјРµСЂРЅРѕСЃС‚СЊ РјР°СЃСЃРёРІР°
    if len(image_np.shape) != 3 or image_np.shape[2] != 3:
        raise ValueError("РР·РѕР±СЂР°Р¶РµРЅРёРµ РґРѕР»Р¶РЅРѕ Р±С‹С‚СЊ С†РІРµС‚РЅС‹Рј (3 РєР°РЅР°Р»Р°).")

    # РљРѕРЅРІРµСЂС‚РёСЂСѓРµРј РёР· RGB РІ BGR
    image_bgr = cv2.cvtColor(image_np, cv2.COLOR_RGB2BGR)

    # РљРѕРЅРІРµСЂС‚РёСЂСѓРµРј РІ РѕС‚С‚РµРЅРєРё СЃРµСЂРѕРіРѕ
    gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)

    # РЈР»СѓС‡С€Р°РµРј РєРѕРЅС‚СЂР°СЃС‚РЅРѕСЃС‚СЊ СЃ РїРѕРјРѕС‰СЊСЋ CLAHE
    clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))  # РЈРІРµР»РёС‡РµРЅ clipLimit РґР»СЏ Р±РѕР»СЊС€РµРіРѕ СѓСЃРёР»РµРЅРёСЏ РєРѕРЅС‚СЂР°СЃС‚Р°
    enhanced = clahe.apply(gray)

    # РђРґР°РїС‚РёРІРЅР°СЏ Р±РёРЅР°СЂРёР·Р°С†РёСЏ СЃ РёР·РјРµРЅРµРЅРЅС‹РјРё РїР°СЂР°РјРµС‚СЂР°РјРё
    thresh = cv2.adaptiveThreshold(enhanced, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                   cv2.THRESH_BINARY_INV, 15, 10)  # РСЃРїРѕР»СЊР·СѓРµРј РёРЅРІРµСЂСЃРёСЋ Рё РјРµРЅСЊС€РёР№ Р±Р»РѕРє

    # РњРѕСЂС„РѕР»РѕРіРёС‡РµСЃРєРѕРµ Р·Р°РєСЂС‹С‚РёРµ РґР»СЏ Р·Р°РїРѕР»РЅРµРЅРёСЏ РїСЂРѕР±РµР»РѕРІ РІРЅСѓС‚СЂРё Р±СѓРєРІ
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (2, 2))
    closed = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel, iterations=1)

    # РЈРґР°Р»РµРЅРёРµ РЅРµР±РѕР»СЊС€РёС… С€СѓРјРѕРІ СЃ РїРѕРјРѕС‰СЊСЋ РјРѕСЂС„РѕР»РѕРіРёС‡РµСЃРєРѕРіРѕ РѕС‚РєСЂС‹С‚РёСЏ
    opened = cv2.morphologyEx(closed, cv2.MORPH_OPEN, kernel, iterations=1)

    # РћРїС†РёРѕРЅР°Р»СЊРЅРѕ: РїСЂРёРјРµРЅРµРЅРёРµ Р±РёР»РёРЅРµР№РЅРѕРіРѕ С„РёР»СЊС‚СЂР° РґР»СЏ СЃРіР»Р°Р¶РёРІР°РЅРёСЏ РєСЂР°РµРІ
    # opened = cv2.bilateralFilter(opened, 9, 75, 75)

    return opened


def read_setting(field_path) -> str | int | float | bool | list[str] | dict | None:

    file_path = "settings.json"
    try:
        # Open and load the JSON file
        with open(file_path, 'r', encoding='utf-8-sig') as file:
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
        with open(file_path, 'r', encoding='utf-8-sig') as file:
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
    log_and_print(f"Р—Р°РіСЂСѓР·РєР° РґР°РЅРЅС‹С… РёР· JSON С„Р°Р№Р»Р° {file_path}.", 'info')
    try:
        with open(file_path, 'r', encoding='utf-8-sig') as file:
            data = json.load(file)
        log_and_print(f"Р”Р°РЅРЅС‹Рµ СѓСЃРїРµС€РЅРѕ Р·Р°РіСЂСѓР¶РµРЅС‹ РёР· {file_path}.", 'info')
        return data
    except FileNotFoundError:
        log_and_print(f"Р¤Р°Р№Р» {file_path} РЅРµ РЅР°Р№РґРµРЅ.", 'error')
        return None
    except json.JSONDecodeError:
        log_and_print(f"РћС€РёР±РєР° РґРµРєРѕРґРёСЂРѕРІР°РЅРёСЏ JSON РІ С„Р°Р№Р»Рµ {file_path}.", 'error')
        return None

def get_latest_file(download_folder):
    try:
        files = os.listdir(download_folder)
        paths = [os.path.join(download_folder, fname) for fname in files]
        latest_file = max(paths, key=os.path.getctime)
        return latest_file
    except Exception as e:
        print(f"РћС€РёР±РєР° РїСЂРё РїРѕР»СѓС‡РµРЅРёРё РїРѕСЃР»РµРґРЅРµРіРѕ С„Р°Р№Р»Р°: {e}")
        return None

def is_video_file(file_path):
    """
    РћРїСЂРµРґРµР»СЏРµС‚, СЏРІР»СЏРµС‚СЃСЏ Р»Рё С„Р°Р№Р» РІРёРґРµРѕ РїРѕ РµРіРѕ СЂР°СЃС€РёСЂРµРЅРёСЋ.

    :param file_path: РџСѓС‚СЊ Рє С„Р°Р№Р»Сѓ.
    :return: True, РµСЃР»Рё С„Р°Р№Р» СЏРІР»СЏРµС‚СЃСЏ РІРёРґРµРѕ, РёРЅР°С‡Рµ False.
    """
    # РЎРїРёСЃРѕРє СЂР°СЃС€РёСЂРµРЅРёР№ РІРёРґРµРѕС„Р°Р№Р»РѕРІ
    video_extensions = {".mp4", ".mkv", ".avi", ".mov", ".wmv", ".flv", ".webm", ".m4v"}

    # РџРѕР»СѓС‡Р°РµРј СЂР°СЃС€РёСЂРµРЅРёРµ С„Р°Р№Р»Р°
    file_extension = file_path.lower().split('.')[-1]

    # РџСЂРѕРІРµСЂСЏРµРј, РµСЃС‚СЊ Р»Рё СЂР°СЃС€РёСЂРµРЅРёРµ РІ СЃРїРёСЃРєРµ РІРёРґРµРѕ
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

def showImage(processed_image, ms, title=None):
    # РћС‚РѕР±СЂР°Р¶РµРЅРёРµ РѕР±СЂР°Р±РѕС‚Р°РЅРЅРѕРіРѕ РёР·РѕР±СЂР°Р¶РµРЅРёСЏ
    processed_array = np.array(processed_image)
    window_name = str(title) if title else "Processed Image"
    cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)
    screen_w = win32api.GetSystemMetrics(0)
    screen_h = win32api.GetSystemMetrics(1)
    window_w = max(420, min(900, int(screen_w * 0.35)))
    window_h = max(320, min(900, int(screen_h * 0.45)))
    cv2.resizeWindow(window_name, window_w, window_h)
    cv2.moveWindow(window_name, max(0, screen_w - window_w - 20), 20)
    cv2.imshow(window_name, processed_array)
    cv2.waitKey(1)
    if ms is not None and ms > 0:
        cv2.waitKey(ms)
        cv2.destroyAllWindows()
        return

    # Hold window until user closes it manually.
    while True:
        visible = cv2.getWindowProperty(window_name, cv2.WND_PROP_VISIBLE)
        if visible < 1:
            break
        cv2.waitKey(100)

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

def show_overlay_win32_hole(
    region,                  # (x, y, w, h) - СЌРєСЂР°РЅРЅС‹Рµ РєРѕРѕСЂРґРёРЅР°С‚С‹
    delay_ms=1500,
    *,
    alpha=120,               # 0..255 вЂ” Р·Р°С‚РµРјРЅРµРЅРёРµ С„РѕРЅР°
    border_color=(0, 255, 0),# BGR
    border_width=3,
    click_through=False,     # True -> РєР»РёРєРё РїСЂРѕС…РѕРґСЏС‚ СЃРєРІРѕР·СЊ РѕРІРµСЂР»РµР№
    caption=None,            # РїРѕРґРїРёСЃСЊ (РѕРїС†РёРѕРЅР°Р»СЊРЅРѕ)
):
    """
    РџРѕР»СѓРїСЂРѕР·СЂР°С‡РЅС‹Р№ TOPMOST-РѕРІРµСЂР»РµР№ РЅР° РІРµСЃСЊ СЌРєСЂР°РЅ СЃ В«РґС‹СЂРєРѕР№В» РїРѕРґ region Рё СЂР°РјРєРѕР№.
    Р‘РµР· Qt/COM. Р—Р°РєСЂС‹С‚РёРµ РїРѕ С‚Р°Р№РјРµСЂСѓ, ESC РёР»Рё РєР»РёРєРѕРј (РµСЃР»Рё click_through=False).
    """
    # Р›РѕРєР°Р»СЊРЅС‹Рµ РёРјРїРѕСЂС‚С‹
    import time
    import ctypes
    import win32api, win32con, win32gui

    x, y, w, h = map(int, region)

    # --- Р Р°Р·РјРµСЂ СЌРєСЂР°РЅР°
    sw = win32api.GetSystemMetrics(0)
    sh = win32api.GetSystemMetrics(1)

    # --- Р РµРіРёСЃС‚СЂР°С†РёСЏ РєР»Р°СЃСЃР° РѕРєРЅР° Рё WndProc
    wc = win32gui.WNDCLASS()
    hInstance = wc.hInstance = win32api.GetModuleHandle(None)
    wc.lpszClassName = "OverlayWin32HoleClass_Ctypes"

    def _on_destroy(hWnd, msg, wParam, lParam):
        win32gui.PostQuitMessage(0)
        return 0

    def _on_keydown(hWnd, msg, wParam, lParam):
        if not click_through and wParam == win32con.VK_ESCAPE:
            win32gui.PostMessage(hWnd, win32con.WM_CLOSE, 0, 0)
        return 0

    def _on_lbutton(hWnd, msg, wParam, lParam):
        if not click_through:
            win32gui.PostMessage(hWnd, win32con.WM_CLOSE, 0, 0)
        return 0

    def _on_paint(hWnd, msg, wParam, lParam):
        # РљРѕСЂСЂРµРєС‚РЅС‹Р№ РїР°С‚С‚РµСЂРЅ BeginPaint/EndPaint Р±РµР· win32gui.PAINTSTRUCT()
        hdc, paintStruct = win32gui.BeginPaint(hWnd)
        try:
            # РџРµСЂРѕ (WinAPI -> RGB, РєРѕРЅРІРµСЂС‚РёСЂСѓРµРј BGR->RGB)
            rgb = win32api.RGB(border_color[2], border_color[1], border_color[0])
            pen = win32gui.CreatePen(win32con.PS_SOLID, int(border_width), rgb)
            old_pen = win32gui.SelectObject(hdc, pen)

            # Р Р°РјРєР° РІРѕРєСЂСѓРі В«РґС‹СЂРєРёВ»
            win32gui.MoveToEx(hdc, x, y);             win32gui.LineTo(hdc, x + w, y)
            win32gui.MoveToEx(hdc, x, y + h - 1);     win32gui.LineTo(hdc, x + w, y + h - 1)
            win32gui.MoveToEx(hdc, x, y);             win32gui.LineTo(hdc, x, y + h)
            win32gui.MoveToEx(hdc, x + w - 1, y);     win32gui.LineTo(hdc, x + w - 1, y + h)

            win32gui.SelectObject(hdc, old_pen)
            win32gui.DeleteObject(pen)

            # РџРѕРґРїРёСЃСЊ (РµСЃР»Рё РЅСѓР¶РЅР°)
            if caption:
                # Р§С‘СЂРЅР°СЏ РїРѕРґР»РѕР¶РєР°
                bg_brush = win32gui.CreateSolidBrush(win32api.RGB(0, 0, 0))
                pad_x, pad_y = 6, 4
                top = max(0, y - 24)
                rect = (x, top, x + 320, top + 20)
                win32gui.FillRect(hdc, rect, bg_brush)
                win32gui.DeleteObject(bg_brush)
                # Р‘РµР»С‹Р№ С‚РµРєСЃС‚
                win32gui.SetTextColor(hdc, win32api.RGB(255, 255, 255))
                win32gui.SetBkMode(hdc, win32con.TRANSPARENT)
                win32gui.TextOut(hdc, rect[0] + pad_x, rect[1] + pad_y, str(caption))
        finally:
            win32gui.EndPaint(hWnd, paintStruct)
        return 0

    wc.lpfnWndProc = {
        win32con.WM_DESTROY:      _on_destroy,
        win32con.WM_KEYDOWN:      _on_keydown,
        win32con.WM_LBUTTONDOWN:  _on_lbutton,
        win32con.WM_PAINT:        _on_paint,
    }

    atom = win32gui.RegisterClass(wc)

    # --- РЎРѕР·РґР°С‘Рј TOPMOST + LAYERED РѕРєРЅРѕ
    style = win32con.WS_POPUP
    exstyle = win32con.WS_EX_TOPMOST | win32con.WS_EX_LAYERED | win32con.WS_EX_TOOLWINDOW
    if click_through:
        exstyle |= win32con.WS_EX_TRANSPARENT  # РїСЂРѕРїСѓСЃРє РєР»РёРєРѕРІ

    hwnd = win32gui.CreateWindowEx(
        exstyle, atom, "overlay", style,
        0, 0, sw, sh, 0, 0, hInstance, None
    )

    # --- РџРѕР»СѓРїСЂРѕР·СЂР°С‡РЅРѕСЃС‚СЊ С„РѕРЅР°
    win32gui.SetLayeredWindowAttributes(hwnd, 0, int(alpha), win32con.LWA_ALPHA)

    # --- Р РµРіРёРѕРЅ РѕРєРЅР° СЃ В«РґС‹СЂРєРѕР№В» (С‡РµСЂРµР· GDI32 / ctypes)
    gdi32 = ctypes.windll.gdi32
    CreateRectRgn = gdi32.CreateRectRgn
    CombineRgn    = gdi32.CombineRgn
    DeleteObject  = gdi32.DeleteObject
    RGN_DIFF      = 4  # win32con.RGN_DIFF

    r_full  = CreateRectRgn(0, 0, sw, sh)
    r_hole  = CreateRectRgn(x, y, x + w, y + h)
    r_final = CreateRectRgn(0, 0, 0, 0)
    CombineRgn(r_final, r_full, r_hole, RGN_DIFF)  # r_final = r_full - r_hole

    win32gui.SetWindowRgn(hwnd, r_final, True)  # r_final С‚РµРїРµСЂСЊ РїСЂРёРЅР°РґР»РµР¶РёС‚ РѕРєРЅСѓ
    DeleteObject(r_full)
    DeleteObject(r_hole)

    # --- РџРѕРєР°Р·
    win32gui.ShowWindow(hwnd, win32con.SW_SHOW)
    win32gui.UpdateWindow(hwnd)

    # --- Р›С‘РіРєРёР№ message loop РґРѕ С‚Р°Р№РјР°СѓС‚Р°
    t_end = time.time() + (delay_ms / 1000.0)
    while time.time() < t_end:
        win32gui.PumpWaitingMessages()
        time.sleep(0.01)

    # --- Р—Р°РєСЂС‹С‚СЊ Рё РѕС‡РёСЃС‚РёС‚СЊ
    if win32gui.IsWindow(hwnd):
        win32gui.DestroyWindow(hwnd)
    try:
        win32gui.UnregisterClass(atom, hInstance)
    except Exception:
        pass


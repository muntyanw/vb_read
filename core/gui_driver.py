"""
core/gui_driver.py
~~~~~~~~~~~~~~~~~~

Low-level wrapper around PyAutoGUI + OpenCV (Рё РѕРїС†РёРѕРЅР°Р»СЊРЅРѕ OCR), 
Р°РґР°РїС‚РёСЂРѕРІР°РЅ РґР»СЏ СЂР°Р±РѕС‚С‹ РЅР° РѕРґРЅРѕРј РјРѕРЅРёС‚РѕСЂРµ 1920Г—1080 РІ РјСѓР»СЊС‚Рё-РјРѕРЅРёС‚РѕСЂРЅРѕР№ РєРѕРЅС„РёРіСѓСЂР°С†РёРё.

* РћРїСЂРµРґРµР»СЏРµС‚ С†РµР»РµРІРѕР№ РјРѕРЅРёС‚РѕСЂ РїРѕ СЂР°Р·СЂРµС€РµРЅРёСЋ TARGET_RES.
* Р’СЃРµ СЃРєСЂРёРЅС€РѕС‚С‹ Р±РµСЂСѓС‚СЃСЏ С‚РѕР»СЊРєРѕ РёР· СЌС‚РѕРіРѕ РјРѕРЅРёС‚РѕСЂР° (СЃ region).
* РљРѕРѕСЂРґРёРЅР°С‚С‹ РєР»РёРєРѕРІ Рё РїРѕРёСЃРєР° СЃРјРµС‰Р°СЋС‚СЃСЏ РѕР±СЂР°С‚РЅРѕ РІ РіР»РѕР±Р°Р»СЊРЅС‹Рµ (СЃ СѓС‡С‘С‚РѕРј x, y С†РµР»РµРІРѕРіРѕ РјРѕРЅРёС‚РѕСЂР°).
"""

from __future__ import annotations

import os
import random
import time
from pathlib import Path
import datetime as _dt
from datetime import date
import re

import cv2
import numpy as np
import pyautogui as pag  
import pytesseract
import matplotlib.pyplot as plt
import mss
import ctypes
from typing import Final, Iterable, Optional, Tuple, List, Union
from difflib import SequenceMatcher
import platform

from project_config import (TEMPLATE_DIR,
                            MONITOR_WIDTH, MONITOR_HEIGHT,
                            MONITOR_INDEX,
                            TESSDATA_PREFIX, MON_X)

from pytesseract import Output

import win32gui
import win32con
import win32api
import win32process
import logging, sys

from utils import preprocess_image, show_overlay_win32_hole, showImage, take_screenshot
ImageLike = Union[str, np.ndarray]

MON_Y = 0

pag.FAILSAFE = False
pag.PAUSE = 0.2

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('log.log', mode='w', encoding='utf-8'),
        logging.StreamHandler(sys.stdout),  # console
    ],
    force=True,  # important if something configured logging before
)
LOGGER = logging.getLogger(__name__)

pag.FAILSAFE = True  # РѕСЃС‚Р°РІРёС‚СЊ РІРѕР·РјРѕР¶РЅРѕСЃС‚СЊ В«РґРІРёР¶РµРЅРёСЏ РјС‹С€Рё РІ СѓРіРѕР» РґР»СЏ СЌРєСЃС‚СЂРµРЅРЅРѕР№ РѕСЃС‚Р°РЅРѕРІРєРёВ»

# ---------------------------------------------------------------------------
# Constants: РёС‰РµРј РјРѕРЅРёС‚РѕСЂ СЃ СЂР°Р·СЂРµС€РµРЅРёРµРј РЅРµРѕР±С…РѕРґРёРјС‹Рј РґР»СЏ СЂР°Р±РѕС‚С‹
# ---------------------------------------------------------------------------
TARGET_RES: Final[Tuple[int, int]] = (MONITOR_WIDTH, MONITOR_HEIGHT)



# with mss.mss() as sct:
#     monitors = sct.monitors  # СЃРїРёСЃРѕРє СЃР»РѕРІР°СЂРµР№; monitors[0] вЂ” РІРµСЃСЊ РІРёСЂС‚СѓР°Р»СЊРЅС‹Р№ СЌРєСЂР°РЅ
#     # monitors[1] вЂ” РїРµСЂРІС‹Р№ С„РёР·РёС‡РµСЃРєРёР№ СЌРєСЂР°РЅ; monitors[2] вЂ” РІС‚РѕСЂРѕР№ Рё С‚.Рґ.
#     # РњС‹ РѕР¶РёРґР°РµРј MONITOR_INDEX 1-based
#     print(f"MONITOR_INDEX = {MONITOR_INDEX}")
#     if 1 <= MONITOR_INDEX < len(monitors):
#         mon = monitors[MONITOR_INDEX]
#         print(mon)
#         MON_X, MON_Y, MON_W, MON_H = mon["left"], mon["top"], mon["width"], mon["height"]
#         #MON_X, MON_Y, MON_W, MON_H = mon["width"], mon["top"],mon["width"], mon["height"]
#         LOGGER.debug("Using MSS monitor #%d: offset (%d,%d), size %dx%d",
#                     MONITOR_INDEX, MON_X, MON_Y, MON_W, MON_H)
#     else:
#         # fallback: РµСЃР»Рё СѓРєР°Р·Р°РЅРЅС‹Р№ РёРЅРґРµРєСЃ РІРЅРµ РґРёР°РїР°Р·РѕРЅР° вЂ” Р±РµСЂРµРј РїРµСЂРІС‹Р№ РјРѕРЅРёС‚РѕСЂ
#         mon = monitors[1]
#         MON_X, MON_Y, MON_W, MON_H = mon["left"], mon["top"], mon["width"], mon["height"]
#         LOGGER.warning("monitor_index=%d is invalid, using primary monitor #%d", MONITOR_INDEX, 1)

def _safe_norm_text(x) -> str:
    """Convert OCR cell to normalized lowercase string; None -> ''."""
    if x is None:
        return ""
    # Сѓ pytesseract РјРѕР¶РµС‚ РїСЂРѕСЃРєРѕС‡РёС‚СЊ РЅРµСЃС‚СЂРѕРєРѕРІС‹Р№ С‚РёРї
    try:
        s = str(x)
    except Exception:
        return ""
    return s.strip().lower()


def pause(amount):
    LOGGER.debug(f"pause {amount} second")
    time.sleep(amount)
    
def _get_monitor_region(scope) -> dict:
    left, bottom, right, top = scope
    print(f"MON_X = {MON_X}")
    monitor_region = {
        "top": bottom,
        "left": MON_X + left,
        "width" :right - left,
        "height": top - bottom
    }

    return monitor_region
# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------

def arrays_fuzzy_equal(window: List[str], query_words: List[str], threshold: float = 0.7) -> bool:
    """
    РЎС‡РёС‚Р°РµС‚ РґРІР° РјР°СЃСЃРёРІР° В«СЂР°РІРЅС‹РјРёВ», РµСЃР»Рё РѕРЅРё РѕРґРёРЅР°РєРѕРІРѕР№ РґР»РёРЅС‹, Рё РґР»СЏ РєР°Р¶РґРѕР№ РїРѕР·РёС†РёРё i:
      РѕС‚РЅРѕС€РµРЅРёРµ РїРѕС…РѕР¶РµСЃС‚Рё (SequenceMatcher) РЅР° СЃС‚СЂРѕРєР°С… w[i] Рё q[i] в‰Ґ threshold.
    РџСѓСЃС‚С‹Рµ СЃС‚СЂРѕРєРё СЃС‡РёС‚Р°СЋС‚СЃСЏ РЅРµРїРѕС…РѕР¶РёРјРё РЅР° РЅРµРїСѓСЃС‚С‹Рµ (С‚РѕР»СЊРєРѕ РѕР±Рµ РїСѓСЃС‚С‹Рµ в†’ РїРѕС…РѕР¶РµСЃС‚СЊ = 1.0).

    :param window:      РїРµСЂРІС‹Р№ СЃРїРёСЃРѕРє СЃС‚СЂРѕРє
    :param query_words: РІС‚РѕСЂРѕР№ СЃРїРёСЃРѕРє СЃС‚СЂРѕРє
    :param threshold:   РјРёРЅРёРјР°Р»СЊРЅС‹Р№ РїРѕСЂРѕРі РїРѕС…РѕР¶РµСЃС‚Рё (РїРѕ СѓРјРѕР»С‡Р°РЅРёСЋ 0.7)
    :return: True, РµСЃР»Рё РІСЃРµ РїР°СЂРЅС‹Рµ СЃС‚СЂРѕРєРѕРІС‹Рµ СЌР»РµРјРµРЅС‚С‹ РїРѕС…РѕР¶Рё в‰Ґ threshold
    """
    if len(window) != len(query_words):
        return False

    count_equal = 0
    
    for w, q in zip(window, query_words):
        # Р•СЃР»Рё РѕР±Рµ СЃС‚СЂРѕРєРё РїСѓСЃС‚С‹Рµ, СЃС‡РёС‚Р°РµРј РёС… РёРґРµРЅС‚РёС‡РЅС‹РјРё
        if not w and not q:
            count_equal += 1
            continue

        # Р•СЃР»Рё РѕРґРЅР° РїСѓСЃС‚Р°СЏ, Р° РІС‚РѕСЂР°СЏ РЅРµС‚ в†’ РїРѕС…РѕР¶РµСЃС‚СЊ 0
        if not w or not q:
            continue

        ratio = SequenceMatcher(None, w, q).ratio()
        if ratio >= threshold:
            count_equal += 1

    return count_equal/len(window) >= threshold

def arrays_fuzzy_equal_as_one_str(window: List[str], query_words: List[str], threshold: float = 0.7) -> bool:
    """
    РџСЂРµРѕР±СЂР°Р·СѓРµС‚ РґРІР° РјР°СЃСЃРёРІР° РІ СЃС‚СЂРѕРєРё Рё СЃСЂР°РІРЅРёРІР°РµС‚ РёС…
    
    :param window:      РїРµСЂРІС‹Р№ СЃРїРёСЃРѕРє СЃС‚СЂРѕРє
    :param query_words: РІС‚РѕСЂРѕР№ СЃРїРёСЃРѕРє СЃС‚СЂРѕРє
    :param threshold:   РјРёРЅРёРјР°Р»СЊРЅС‹Р№ РїРѕСЂРѕРі РїРѕС…РѕР¶РµСЃС‚Рё (РїРѕ СѓРјРѕР»С‡Р°РЅРёСЋ 0.7)
    :return: True, РµСЃР»Рё РІСЃРµ РїР°СЂРЅС‹Рµ СЃС‚СЂРѕРєРѕРІС‹Рµ СЌР»РµРјРµРЅС‚С‹ РїРѕС…РѕР¶Рё в‰Ґ threshold
    """
    if len(window) != len(query_words):
        return False

    str_window = "".join(window)
    str_query_words = "".join(query_words)

    ratio = SequenceMatcher(None, str_window, str_query_words).ratio()
    
    return ratio >= threshold


def detect_checkbox_type_from_frame(scope: tuple[int, int, int, int] = None,
                is_debug: bool = False) -> str:
    """
        frame_bgr: РєР°РґСЂ СЌРєСЂР°РЅР° (numpy.ndarray РІ С„РѕСЂРјР°С‚Рµ BGR)
        empty_template_path: РїСѓС‚СЊ РґРѕ С€Р°Р±Р»РѕРЅР° РїСѓСЃС‚РѕРіРѕ РєРІР°РґСЂР°С‚РёРєР°
        checked_template_path: РїСѓС‚СЊ РґРѕ С€Р°Р±Р»РѕРЅР° РєРІР°РґСЂР°С‚РёРєР° СЃ РіР°Р»РѕС‡РєРѕР№
        threshold: РјРёРЅРёРјР°Р»СЊРЅРѕРµ Р·РЅР°С‡РµРЅРёРµ СЃРѕРІРїР°РґРµРЅРёСЏ (0.0вЂ“1.0)
        
        Р’РµСЂРЅС‘С‚:
        - "empty", РµСЃР»Рё РЅР° СЌРєСЂР°РЅРµ РЅР°Р№РґРµРЅ РїСѓСЃС‚РѕР№ РєРІР°РґСЂР°С‚РёРє
        - "checked", РµСЃР»Рё РЅР°Р№РґРµРЅ РєРІР°РґСЂР°С‚РёРє СЃ РіР°Р»РѕС‡РєРѕР№
        - "none", РµСЃР»Рё РЅРё РѕРґРёРЅ РёР· С€Р°Р±Р»РѕРЅРѕРІ РЅРµ РЅР°С€С‘Р»СЃСЏ (РјР°ximР°Р»СЊРЅС‹Р№ РєРѕСЌС„С„РёС†РёРµРЅС‚ < threshold)
    """
    frame_bgr = screen(scope)
    
    if is_debug:
        show_image(frame_bgr)
        time.sleep(0.5)
    

    # Р—Р°РіСЂСѓР¶Р°РµРј РѕР±Р° С€Р°Р±Р»РѕРЅР° СЃСЂР°Р·Сѓ РІ РіСЂР°РґР°С†РёСЏС… СЃРµСЂРѕРіРѕ
    templ_empty = cv2.imread(str(TEMPLATE_DIR / CHECK_EMPTY_TEMPLATE_PATH))
    
    templ_checked = cv2.imread(str(TEMPLATE_DIR / CHECK_CHECKED_TEMPLATE_PATH))
    
    if templ_empty is None:
        raise FileNotFoundError(f"РќРµ РЅР°Р№РґРµРЅ С€Р°Р±Р»РѕРЅ В«РїСѓСЃС‚РѕР№В» РїРѕ РїСѓС‚Рё {TEMPLATE_DIR / CHECK_EMPTY_TEMPLATE_PATH}")
    if templ_checked is None:
        raise FileNotFoundError(f"РќРµ РЅР°Р№РґРµРЅ С€Р°Р±Р»РѕРЅ В«СЃ РіР°Р»РѕС‡РєРѕР№В» РїРѕ РїСѓС‚Рё {TEMPLATE_DIR / CHECK_CHECKED_TEMPLATE_PATH}")

    if is_debug:
        show_image(templ_empty)
        time.sleep(0.5)
        show_image(templ_checked)
        time.sleep(0.5)
    
    # 1) РџРѕРёСЃРє РїСѓСЃС‚РѕРіРѕ РєРІР°РґСЂР°С‚РёРєР°
    res_empty = cv2.matchTemplate(frame_bgr, templ_empty, cv2.TM_CCOEFF_NORMED)
    _, max_val_empty, _, _ = cv2.minMaxLoc(res_empty)

    # 2) РџРѕРёСЃРє РєРІР°РґСЂР°С‚РёРєР° СЃ РіР°Р»РѕС‡РєРѕР№
    res_checked = cv2.matchTemplate(frame_bgr, templ_checked, cv2.TM_CCOEFF_NORMED)
    _, max_val_checked, _, _ = cv2.minMaxLoc(res_checked)

    # Р•СЃР»Рё РЅРё РѕРґРёРЅ РёР· С€Р°Р±Р»РѕРЅРѕРІ РЅРµ РїСЂРµРІС‹СЃРёР» threshold в†’ В«РЅРёС‡РµРіРѕ РЅРµ РЅР°Р№РґРµРЅРѕВ»
    LOGGER.debug(f"max_val_empty: {max_val_empty}, max_val_checked: {max_val_checked}")

    # Р•СЃР»Рё РѕР±Р° РІС‹С€Рµ РїРѕСЂРѕРіР°, СЃРјРѕС‚СЂРёРј, Сѓ РєРѕРіРѕ РєРѕСЌС„С„РёС†РёРµРЅС‚ Р±РѕР»СЊС€РёР№
    if max_val_checked >= max_val_empty:
        return "checked"
    else:
        return "empty"

def detect_image_from_frame(image_names: list[str], scope: tuple[int, int, int, int] = None,
                is_debug: bool = False,
                threshold: float = 0.8) -> str:
   
    frame_bgr = screen(scope)
    
    # РљРѕРЅРІРµСЂС‚РёСЂСѓРµРј СЃРєСЂРёРЅ РІ РѕС‚С‚РµРЅРєРё СЃРµСЂРѕРіРѕ
    gray_frame = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)

    max_weight = -10000
    check_image = ""
    
    for image_name in image_names:
        templ = cv2.imread(TEMPLATE_DIR / image_name, cv2.IMREAD_GRAYSCALE)
        if templ is None:
            raise FileNotFoundError(f"РќРµ РЅР°Р№РґРµРЅ С€Р°Р±Р»РѕРЅ В«РїСѓСЃС‚РѕР№В» РїРѕ РїСѓС‚Рё {TEMPLATE_DIR / image_name}")
        res = cv2.matchTemplate(gray_frame, templ, cv2.TM_CCOEFF_NORMED)
        _, weight, _, _ = cv2.minMaxLoc(res)
        
        if weight > max_weight:
            check_image = image_name

        return check_image

def find_image(name: str, timeout: float = 8.0, 
                confidence: float = 0.7,
                scope: tuple[int, int, int, int] = None,
                is_debug: bool = False, 
                multiscale: bool = False) -> (tuple[int, int] | None):
    """
    РќР°Р№С‚Рё PNG-С€Р°Р±Р»РѕРЅ РЅР° СЌРєСЂР°РЅРµ.
    """
    path = TEMPLATE_DIR / name
    if not path.exists():
        raise FileNotFoundError(path)

    deadline = time.perf_counter() + timeout
    
    LOGGER.debug(f"Start locate image {name}")
    
    while time.perf_counter() < deadline:
        
        if not multiscale:
            pos = _locate(path, confidence, scope=scope, is_debug=is_debug)
        else:
            pos = _locate_multiscale(path, confidence, scope=scope, is_debug=is_debug)
            
        if pos:
            LOGGER.debug(f"return image: {name} pos: {pos}")
            abs_x = pos[0]
            abs_y = pos[1]
            return (abs_x, abs_y) 

    LOGGER.debug(f"image {name} not found")
    return False

def click_image(name: str, timeout: float = 8.0, confidence: float = 0.7,
                scope: tuple[int, int, int, int] = None,
                plus_y: int = 0,
                plus_x: int = 0,
                is_debug: bool = False,
                multiscale: bool = False,
                count_click: int = 1) -> bool:
    """
    РќР°Р№С‚Рё PNG-С€Р°Р±Р»РѕРЅ РЅР° СЌРєСЂР°РЅРµ (РІ РїСЂРµРґРµР»Р°С… С†РµР»РµРІРѕРіРѕ РјРѕРЅРёС‚РѕСЂР°) Рё РєР»РёРєРЅСѓС‚СЊ РµРіРѕ С†РµРЅС‚СЂ.
    Р’РѕР·РІСЂР°С‰Р°РµС‚ True, РµСЃР»Рё РєР»РёРєРЅСѓР»Рё, False РµСЃР»Рё РЅРµ РЅР°Р№РґРµРЅРѕ Р·Р° timeout СЃРµРєСѓРЅРґ.
    """
    LOGGER.debug(f"Start find image {name}")
    start = time.perf_counter()
    result_find = find_image(name, timeout, confidence, scope, is_debug, multiscale)
    end = time.perf_counter()
    tm = end - start
    #print(f"time find image {name} (multiscale={multiscale}) = {tm}")
    LOGGER.debug(f"result_find {name} = {result_find}")
    if result_find:
        
        LOGGER.debug(f"Foud image {name}")
        #print(f"Foud image {name}")
        #print(f"result_find {result_find}")
        abs_x, abs_y = result_find
        if abs_x is not None and abs_y is not None:
            draw_click_circle(abs_x + plus_x, abs_y + plus_y)
            human_move_and_click(abs_x + plus_x, abs_y + plus_y, count_click=count_click)
            return True
        

    return False

def type_text(text: str, interval: Tuple[float, float] = (0.05, 0.12)) -> None:
    """
    РџРµС‡Р°С‚Р°С‚СЊ СЃС‚СЂРѕРєСѓ СЃ РЅРµР±РѕР»СЊС€РёРј СЃР»СѓС‡Р°Р№РЅС‹Рј РёРЅС‚РµСЂРІР°Р»РѕРј РјРµР¶РґСѓ СЃРёРјРІРѕР»Р°РјРё.
    """
    for ch in text:
        pag.typewrite(ch)
        time.sleep(random.uniform(*interval))

def show_image(img) -> None:
    # Show debug image on the right side of the screen when backend allows.
    plt.figure(figsize=(8, 5))
    plt.imshow(img)
    plt.axis("off")
    plt.title("Tesseract Input: Full-Screen Screenshot")

    try:
        screen_w, screen_h = pag.size()
        win_w = int(screen_w * 0.45)
        win_h = int(screen_h * 0.55)
        pos_x = max(0, screen_w - win_w - 20)
        pos_y = 20

        manager = plt.get_current_fig_manager()
        if hasattr(manager, "resize"):
            manager.resize(win_w, win_h)

        if hasattr(manager, "window") and hasattr(manager.window, "wm_geometry"):
            manager.window.wm_geometry(f"{win_w}x{win_h}+{pos_x}+{pos_y}")
        elif hasattr(manager, "window") and hasattr(manager.window, "setGeometry"):
            manager.window.setGeometry(pos_x, pos_y, win_w, win_h)
    except Exception:
        pass

    plt.show()
# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------
def _detect_chrome() -> Path:
    """
    Best-effort РїРѕРёСЃРє chrome.exe / google-chrome РІ common locations.
    """
    candidates = [
        Path(r"C:/Program Files/Google/Chrome/Application/chrome.exe"),
        Path(r"C:/Program Files (x86)/Google/Chrome/Application/chrome.exe"),
        Path("/usr/bin/google-chrome-stable"),
        Path("/usr/bin/google-chrome"),
    ]
    for p in candidates:
        if p.exists():
            return p
    raise RuntimeError("Chrome executable not found; add custom logic in _detect_chrome()")

def scroll(amount: int = 100) -> None:
        pag.scroll(amount) 
        time.sleep(0.01) 


# Optional DirectX backend for crisp, DPI-accurate capture on Windows
try:
    import dxcam  # pip install dxcam
except Exception:
    dxcam = None

_DPI_AWARE_SET = False
_DXCAM_HANDLE = None


def _ensure_dpi_awareness_once() -> None:
    """Make the process DPI-aware (Windows). No-op elsewhere."""
    global _DPI_AWARE_SET
    if _DPI_AWARE_SET:
        return
    if platform.system() == "Windows":
        import ctypes
        try:
            # Per-monitor v2 (Windows 10+)
            ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
        except Exception:
            try:
                # Per-monitor (Windows 8.1+)
                ctypes.windll.shcore.SetProcessDpiAwareness(2)
            except Exception:
                try:
                    # System-aware (fallback)
                    ctypes.windll.user32.SetProcessDPIAware()
                except Exception:
                    pass
    _DPI_AWARE_SET = True


def _grab_with_dxcam(scope: Optional[Tuple[int, int, int, int]]) -> Optional[np.ndarray]:
    """Grab BGR frame via dxcam (Windows/DirectX). Returns None if not available."""
    global _DXCAM_HANDLE
    if dxcam is None or platform.system() != "Windows":
        return None
    if _DXCAM_HANDLE is None:
        _DXCAM_HANDLE = dxcam.create(output_idx=0)
    # dxcam expects (left, top, right, bottom)
    if scope:
        l, t, w, h = scope
        l = l + MON_X
        print(f"MON_X = {MON_X}")
        frame = _DXCAM_HANDLE.grab(region=(l, t, l + w, t + h))
    else:
        frame = _DXCAM_HANDLE.grab()
    if frame is None:
        return None
    return cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)


def _grab_with_mss(scope: Optional[Tuple[int, int, int, int]]) -> np.ndarray:
    """Grab BGR frame via MSS."""
    with mss.mss() as sct:
        mon = _get_monitor_region(scope)  # your existing helper: returns dict {left, top, width, height}
        img = sct.grab(mon)
        scr_np = np.array(img)  # BGRA
        return cv2.cvtColor(scr_np, cv2.COLOR_BGRA2BGR)


def screen(
    scope: Optional[Tuple[int, int, int, int]] = None,
    is_debug: bool = False,
    process_for_read: bool = True,
):
    """
    Capture a screen region with the highest practical fidelity for OCR when process_for_read=True.
    - When process_for_read=True:
        * Make process DPI-aware (Windows) and prefer DirectX capture (dxcam) for crisp pixels.
        * Fall back to MSS if dxcam is unavailable.
        * Do NOT artificially upscale here to keep coordinates consistent.
        * Then run `preprocess_for_ocr` on the native-resolution frame.
    - When process_for_read=False:
        * Use MSS with standard settings (no preprocessing).
    Returns a BGR image.
    """
    if process_for_read:
        _ensure_dpi_awareness_once()  # get native-resolution capture on Windows
        scr_bgr = _grab_with_dxcam(scope)
        if scr_bgr is None:
            scr_bgr = _grab_with_mss(scope)
        scr_bgr = preprocess_for_ocr(scr_bgr)  # your existing OCR pipeline
    else:
        scr_bgr = _grab_with_mss(scope)

    if is_debug:
        show_image(scr_bgr)
        time.sleep(0.5)

    return scr_bgr


def _read_template_with_optional_mask(template_path: Path):
    """
    Read template preserving alpha if present.
    Returns (tpl_bgr, mask_or_None).
    """
    tpl = cv2.imread(str(template_path), cv2.IMREAD_UNCHANGED)
    if tpl is None:
        raise RuntimeError(f"Cannot read template: {template_path}")

    mask = None
    if tpl.ndim == 3 and tpl.shape[2] == 4:
        # Has alpha channel: build binary mask from alpha
        bgr = cv2.cvtColor(tpl, cv2.COLOR_BGRA2BGR)
        alpha = tpl[:, :, 3]
        _, mask = cv2.threshold(alpha, 0, 255, cv2.THRESH_BINARY)
        tpl_bgr = bgr
    elif tpl.ndim == 3:
        tpl_bgr = tpl
        # Auto-mask for templates without alpha:
        # if corner background is almost uniform, ignore it in matching.
        h, w = tpl_bgr.shape[:2]
        if h >= 3 and w >= 3:
            corners = np.array(
                [
                    tpl_bgr[0, 0],
                    tpl_bgr[0, w - 1],
                    tpl_bgr[h - 1, 0],
                    tpl_bgr[h - 1, w - 1],
                ],
                dtype=np.int16,
            )
            bg = np.median(corners, axis=0).astype(np.int16)
            corner_spread = int(np.max(np.abs(corners - bg)))
            if corner_spread <= 12:
                diff = np.max(np.abs(tpl_bgr.astype(np.int16) - bg), axis=2)
                auto_mask = (diff > 20).astype(np.uint8) * 255
                nz = int(np.count_nonzero(auto_mask))
                total = int(auto_mask.size)
                # Keep only meaningful masks (avoid all-0 or all-1 masks).
                if int(0.03 * total) <= nz <= int(0.97 * total):
                    mask = auto_mask
    else:
        # Single channel template -> convert to BGR for uniformity
        tpl_bgr = cv2.cvtColor(tpl, cv2.COLOR_GRAY2BGR)
    return tpl_bgr, mask


def _locate(
    template_path: Path,
    confidence: float,
    scope: Tuple[int, int, int, int] = None,
    is_debug: bool = False
) -> Optional[Tuple[int, int]]:
    """
    Single-scale template matching.
    Returns absolute (x_center, y_center) or None.
    """
    # Always capture raw image for matching (no OCR preprocessing)
    scr_bgr = screen(scope, process_for_read=False, is_debug=False)

    tpl_bgr, mask = _read_template_with_optional_mask(template_path)

    img_h, img_w = scr_bgr.shape[:2]
    th, tw = tpl_bgr.shape[:2]

    # Guard: template must fit inside image at this single scale
    if th > img_h or tw > img_w or th < 1 or tw < 1:
        if is_debug:
            print(f"[DEBUG] Template size ({tw}x{th}) doesn't fit image ({img_w}x{img_h}).")
        return None

    # Choose method: with mask -> CCORR_NORMED in color; without mask -> CCOEFF_NORMED in gray
    if mask is not None:
        res = cv2.matchTemplate(scr_bgr, tpl_bgr, cv2.TM_CCORR_NORMED, mask=mask)
        min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(res)
        score, (x, y), w, h = float(max_val), max_loc, tw, th
    else:
        img_gray = cv2.cvtColor(scr_bgr, cv2.COLOR_BGR2GRAY)
        img_gray = cv2.GaussianBlur(img_gray, (3, 3), 0)
        tpl_gray = cv2.cvtColor(tpl_bgr, cv2.COLOR_BGR2GRAY)
        tpl_gray = cv2.GaussianBlur(tpl_gray, (3, 3), 0)
        res = cv2.matchTemplate(img_gray, tpl_gray, cv2.TM_CCOEFF_NORMED)
        min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(res)
        score, (x, y), w, h = float(max_val), max_loc, tw, th

    if score < confidence:
        if is_debug:
            print(f"[DEBUG] Best score {score:.3f} < confidence {confidence:.3f}")
        return None

    # Convert to absolute center coordinates
    left = scope[0] if scope else 0
    top  = scope[1] if scope else 0
    cx_abs = left + x + w // 2
    cy_abs = top  + y + h // 2

    if is_debug:
        dbg = scr_bgr.copy()
        cv2.rectangle(dbg, (x, y), (x + w, y + h), (0, 255, 0), 2)
        show_image(dbg)

    return (cx_abs, cy_abs)


def _locate_multiscale(
    template_path: Path,
    confidence: float,
    scope: Tuple[int, int, int, int] = None,
    is_debug: bool = False,
    w_l: float = 0.55,          # РІРµСЃ СЏСЂРєРѕСЃС‚Рё (L*)
    w_c: float = 0.45,          # СЃРѕРІРѕРєСѓРїРЅС‹Р№ РІРµСЃ С†РІРµС‚Р° (a*+b*)
    hist_bins_h: int = 30,
    hist_bins_s: int = 32,
    color_reweight: float = 0.25,  # СЃРёР»Р° РґРѕРЅР°СЃС‚СЂРѕР№РєРё РїРѕ С†РІРµС‚Сѓ (0..1)
) -> Optional[Tuple[int, int]]:
    """
    Multi-scale template matching with color-aware scoring.
    Р’РѕР·РІСЂР°С‰Р°РµС‚ Р°Р±СЃРѕР»СЋС‚РЅС‹Рµ (cx, cy) РёР»Рё None.
    """

    def _deltaEab_mean(bgrA, bgrB) -> float:
        A = cv2.cvtColor(bgrA, cv2.COLOR_BGR2LAB).astype("float32")
        B = cv2.cvtColor(bgrB, cv2.COLOR_BGR2LAB).astype("float32")
        diff = A - B
        # РџСЂРѕСЃС‚РѕР№ О”E*ab (CIE76) вЂ” РЅРѕСЂРј РґР»СЏ СЂР°РЅР¶РёСЂРѕРІР°РЅРёСЏ
        de = np.sqrt(np.sum(diff ** 2, axis=2))
        return float(de.mean())

    def _hsv_hist_corr(bgrA, bgrB) -> float:
        hsvA = cv2.cvtColor(bgrA, cv2.COLOR_BGR2HSV)
        hsvB = cv2.cvtColor(bgrB, cv2.COLOR_BGR2HSV)
        histA = cv2.calcHist([hsvA], [0, 1], None, [hist_bins_h, hist_bins_s], [0, 180, 0, 256])
        histB = cv2.calcHist([hsvB], [0, 1], None, [hist_bins_h, hist_bins_s], [0, 180, 0, 256])
        cv2.normalize(histA, histA)
        cv2.normalize(histB, histB)
        # CORREL в€€ [-1..1] -> РїСЂРёРІРµРґС‘Рј Рє [0..1]
        corr = cv2.compareHist(histA, histB, cv2.HISTCMP_CORREL)
        return float(max(0.0, min(1.0, 0.5 * (corr + 1.0))))

    # 1) РЎРЅРёРјРѕРє СЌРєСЂР°РЅР°
    scr_bgr = screen(scope, process_for_read=False, is_debug=is_debug)
    img_h, img_w = scr_bgr.shape[:2]

    # 2) РЁР°Р±Р»РѕРЅ (+РјР°СЃРєР° РїСЂРё РЅР°Р»РёС‡РёРё)
    tpl_bgr, mask = _read_template_with_optional_mask(template_path)
    tw0, th0 = tpl_bgr.shape[1], tpl_bgr.shape[0]

    # 3) Р”РёР°РїР°Р·РѕРЅ РјР°СЃС€С‚Р°Р±РѕРІ
    scales = np.linspace(0.75, 1.25, 21)

    best = None  # Р±СѓРґРµС‚ С…СЂР°РЅРёС‚СЊ (final_score, raw_tm, x, y, w, h, scale)

    # РџСЂРµРґСЂР°СЃС‡С‘С‚ СЏСЂРєРѕСЃС‚РЅРѕРіРѕ Рё С†РІРµС‚РѕРІС‹С… РєР°РЅР°Р»РѕРІ РґР»СЏ СЌРєСЂР°РЅР°
    scr_lab = cv2.cvtColor(scr_bgr, cv2.COLOR_BGR2LAB)
    scr_L, scr_a, scr_b = cv2.split(scr_lab)

    for s in scales:
        new_w = max(1, int(round(tw0 * s)))
        new_h = max(1, int(round(th0 * s)))
        if new_w > img_w or new_h > img_h or new_w < 1 or new_h < 1:
            continue

        interp = cv2.INTER_AREA if s < 1.0 else cv2.INTER_LINEAR
        tpl_s = cv2.resize(tpl_bgr, (new_w, new_h), interpolation=interp)
        mask_s = None
        if mask is not None:
            mask_s = cv2.resize(mask, (new_w, new_h), interpolation=cv2.INTER_NEAREST)

        if mask_s is not None:
            # РњР°СЃРєРёСЂРѕРІР°РЅРЅРѕРµ СЃРѕРїРѕСЃС‚Р°РІР»РµРЅРёРµ РїРѕ С†РІРµС‚Сѓ (РЅРѕСЂРјРёСЂРѕРІР°РЅРЅР°СЏ РєРѕСЂСЂРµР»СЏС†РёСЏ)
            res = cv2.matchTemplate(scr_bgr, tpl_s, cv2.TM_CCORR_NORMED, mask=mask_s)
            _, raw_tm, _, max_loc = cv2.minMaxLoc(res)
            x, y = max_loc
        else:
            # Р¦РІРµС‚Рѕ-С‡СѓРІСЃС‚РІРёС‚РµР»СЊРЅС‹Р№ СЃРєРѕСЂРёРЅРі: L*, a*, b* РѕС‚РґРµР»СЊРЅРѕ вЂ” Р·Р°С‚РµРј СЃРјРµС€РёРІР°РµРј
            tpl_lab = cv2.cvtColor(tpl_s, cv2.COLOR_BGR2LAB)
            tpl_L, tpl_a, tpl_b = cv2.split(tpl_lab)

            # РќРµР±РѕР»СЊС€РѕРµ СЃРіР»Р°Р¶РёРІР°РЅРёРµ С‚РѕР»СЊРєРѕ РЅР° L* (С‚РµРєСЃС‚СѓСЂРЅС‹Р№ С€СѓРј)
            scr_L_blur = cv2.GaussianBlur(scr_L, (3, 3), 0)
            tpl_L_blur = cv2.GaussianBlur(tpl_L, (3, 3), 0)

            # РљР°СЂС‚С‹ СЃРѕРІРїР°РґРµРЅРёСЏ ([-1..1] РґР»СЏ CCOEFF_NORMED)
            res_L = cv2.matchTemplate(scr_L_blur, tpl_L_blur, cv2.TM_CCOEFF_NORMED)
            res_a = cv2.matchTemplate(scr_a, tpl_a, cv2.TM_CCOEFF_NORMED)
            res_b = cv2.matchTemplate(scr_b, tpl_b, cv2.TM_CCOEFF_NORMED)

            # РЎРјРµС€РёРІР°РЅРёРµ СЃ РІРµСЃР°РјРё
            res = w_l * res_L + (w_c * 0.5) * (res_a + res_b)

            _, raw_tm, _, max_loc = cv2.minMaxLoc(res)
            x, y = max_loc

        # 4) Re-rank РїРѕ С†РІРµС‚Сѓ РЅР° РЅР°Р№РґРµРЅРЅРѕРј РїРёРєРµ: О”E*ab Рё HSV-РіРёСЃС‚ РєРѕСЂСЂРµР»СЏС†РёСЏ
        roi = scr_bgr[y:y+new_h, x:x+new_w]
        if roi.shape[0] == new_h and roi.shape[1] == new_w:
            # О”E ~ [0..~100] -> РїСЂРµРѕР±СЂР°Р·СѓРµРј РІ [0..1] С‡РµСЂРµР· СЌРєСЃРїРѕРЅРµРЅС‚Сѓ
            dE = _deltaEab_mean(roi, tpl_s)  # РјРµРЅСЊС€Рµ вЂ” Р»СѓС‡С€Рµ
            dE_term = np.exp(-dE / 12.0)     # в‰€0.44 РїСЂРё dE=10; в‰€0.19 РїСЂРё dE=20

            # РљРѕСЂСЂРµР». РіРёСЃС‚РѕРіСЂР°РјРј HSV в€€ [0..1]
            hcorr = _hsv_hist_corr(roi, tpl_s)

            # Р¦РІРµС‚РѕРІРѕР№ Р±РѕРЅСѓСЃ [0..1]
            color_bonus = 0.6 * dE_term + 0.4 * hcorr

            # РС‚РѕРіРѕРІС‹Р№ СЃРєРѕСЂ (РїРѕРґРїСЂР°РІР»СЏРµРј СЃС‹СЂРѕР№ TM РІ СЃС‚РѕСЂРѕРЅСѓ С†РІРµС‚РѕРІРѕРіРѕ СЃРѕРІРїР°РґРµРЅРёСЏ)
            final_score = (1.0 - color_reweight) * float(raw_tm) + color_reweight * float(color_bonus)
        else:
            final_score = float(raw_tm)

        if best is None or final_score > best[0]:
            best = (final_score, float(raw_tm), x, y, new_w, new_h, float(s))

        if is_debug:
            print(f"[DEBUG] scale={s:.3f}, raw_tm={float(raw_tm):.3f}, final={final_score:.3f}, x={x}, y={y}, wh=({new_w},{new_h})")

    if not best or best[0] < confidence:
        if is_debug:
            bv = best[0] if best else -1.0
            bs = best[6] if best else float('nan')
            print(f"[DEBUG] No match >= {confidence:.3f}. best={bv:.3f} @ scale={bs}")
        return None

    final_score, raw_tm, x, y, w, h, s = best

    left = scope[0] if scope else 0
    top  = scope[1] if scope else 0
    cx_abs = left + x + w // 2
    cy_abs = top  + y + h // 2

    if is_debug:
        dbg = scr_bgr.copy()
        cv2.rectangle(dbg, (x, y), (x + w, y + h), (0, 255, 0), 2)
        show_image(dbg)
        print(f"[DEBUG] chosen scale={s:.3f}, final={final_score:.3f}, raw_tm={raw_tm:.3f}, center=({cx_abs},{cy_abs})")

    return (cx_abs, cy_abs)


def _human_move(x: int, y: int, 
                duration: Tuple[float, float] = (0.1, 0.2)) -> None:
    """
    РџРµСЂРµРґР°С‚СЊ Р°Р±СЃРѕР»СЋС‚РЅС‹Рµ РіР»РѕР±Р°Р»СЊРЅС‹Рµ РєРѕРѕСЂРґРёРЅР°С‚С‹ (x, y) Рё РІС‹РїРѕР»РЅРёС‚СЊ РїР»Р°РІРЅРѕРµ РґРІРёР¶РµРЅРёРµ
    вЂњРїРѕ-С‡РµР»РѕРІРµС‡РµСЃРєРёвЂќ. РСЃРїРѕР»СЊР·СѓРµС‚СЃСЏ Bezier-РєСЂРёРІР°СЏ + РЅРµР±РѕР»СЊС€РёРµ СЃР»СѓС‡Р°Р№РЅС‹Рµ РїР°СѓР·С‹.
    """
    LOGGER.debug(f"Start human move to x: {x}, y: {y}")
    
    x = x + MON_X
    
    #cx, cy = pag.position()  # С‚РµРєСѓС‰Р°СЏ Р°Р±СЃРѕР»СЋС‚РЅР°СЏ РїРѕР·РёС†РёСЏ РјС‹С€Рё

    # РўРѕС‡РєРё РґР»СЏ РєСЂРёРІРѕР№ Р‘РµР·СЊРµ: СЃС‚Р°СЂС‚ в†’ 2 СЃР»СѓС‡Р°Р№РЅС‹Рµ РѕРїРѕСЂС‹ в†’ С†РµР»СЊ
    # anchors = [
    #     (cx, cy),
    #     _rand_near(cx, cy, 100),
    #     _rand_near(x, y, 100),
    #     (x, y),
    # ]
    # steps = 3
    # for t in np.linspace(0, 1, steps):
    #     bx, by = _bezier_point(anchors, t)
    #     pag.moveTo(bx, by, duration=0)
    #     time.sleep(0.0001)

    pag.moveTo(x, y)#, duration=random.uniform(*duration)

def draw_click_circle(x, y, radius=20, duration=0.2):
    class_name = "ClickCircleClass"
    
    x= x + MON_X

    def wnd_proc(hwnd, msg, wparam, lparam):
        if msg == win32con.WM_PAINT:
            hdc, ps = win32gui.BeginPaint(hwnd)
            brush = win32gui.CreateSolidBrush(win32api.RGB(0, 0, 255))
            win32gui.SelectObject(hdc, brush)
            win32gui.Ellipse(hdc, 0, 0, radius * 2, radius * 2)
            win32gui.EndPaint(hwnd, ps)
            return 0
        return win32gui.DefWindowProc(hwnd, msg, wparam, lparam)

    hInstance = win32api.GetModuleHandle(None)
    wnd_class = win32gui.WNDCLASS()
    wnd_class.lpfnWndProc = wnd_proc
    wnd_class.lpszClassName = class_name
    wnd_class.hInstance = hInstance
    wnd_class.hCursor = win32gui.LoadCursor(None, win32con.IDC_ARROW)
    wnd_class.hbrBackground = win32con.COLOR_WINDOW + 1
    wnd_class.style = win32con.CS_HREDRAW | win32con.CS_VREDRAW

    try:
        win32gui.RegisterClass(wnd_class)
    except win32gui.error:
        pass  # РљР»Р°СЃСЃ СѓР¶Рµ Р·Р°СЂРµРіРёСЃС‚СЂРёСЂРѕРІР°РЅ

    hwnd = win32gui.CreateWindowEx(
        win32con.WS_EX_LAYERED | win32con.WS_EX_TOPMOST | win32con.WS_EX_TOOLWINDOW,
        class_name,
        None,
        win32con.WS_POPUP,
        x - radius, y - radius,
        radius * 2, radius * 2,
        None, None, hInstance, None
    )

    win32gui.SetLayeredWindowAttributes(hwnd, 0, 180, win32con.LWA_ALPHA)
    win32gui.ShowWindow(hwnd, win32con.SW_SHOW)
    win32gui.UpdateWindow(hwnd)

    # Р–РґС‘Рј duration СЃРµРєСѓРЅРґ, РїРѕС‚РѕРј Р·Р°РєСЂС‹РІР°РµРј РѕРєРЅРѕ
    time.sleep(duration)
    win32gui.DestroyWindow(hwnd)
    
def human_move_and_click(x: int, y: int, 
                         duration: Tuple[float, float] = (0.2, 0.3),
                         count_click: int = 1) -> None:
    """
    РџРµСЂРµРґР°С‚СЊ Р°Р±СЃРѕР»СЋС‚РЅС‹Рµ РіР»РѕР±Р°Р»СЊРЅС‹Рµ РєРѕРѕСЂРґРёРЅР°С‚С‹ (x, y) Рё РІС‹РїРѕР»РЅРёС‚СЊ РїР»Р°РІРЅРѕРµ РґРІРёР¶РµРЅРёРµ
    вЂњРїРѕ-С‡РµР»РѕРІРµС‡РµСЃРєРёвЂќ + РєР»РёРє. РСЃРїРѕР»СЊР·СѓРµС‚СЃСЏ Bezier-РєСЂРёРІР°СЏ + РЅРµР±РѕР»СЊС€РёРµ СЃР»СѓС‡Р°Р№РЅС‹Рµ РїР°СѓР·С‹.
    """
    _human_move(x, y, duration)
    
    for i in range(0, count_click, 1):
        LOGGER.debug(f"click x: {x} y: {y}")
        draw_click_circle(x,y)
        pag.click()
        
def human_move_and_right_click(x: int, y: int, duration: Tuple[float, float] = (0.4, 0.9),
                         count_click: int = 1) -> None:
    """
    РџРµСЂРµРґР°С‚СЊ Р°Р±СЃРѕР»СЋС‚РЅС‹Рµ РіР»РѕР±Р°Р»СЊРЅС‹Рµ РєРѕРѕСЂРґРёРЅР°С‚С‹ (x, y) Рё РІС‹РїРѕР»РЅРёС‚СЊ РїР»Р°РІРЅРѕРµ РґРІРёР¶РµРЅРёРµ
    вЂњРїРѕ-С‡РµР»РѕРІРµС‡РµСЃРєРёвЂќ + РєР»РёРє. РСЃРїРѕР»СЊР·СѓРµС‚СЃСЏ Bezier-РєСЂРёРІР°СЏ + РЅРµР±РѕР»СЊС€РёРµ СЃР»СѓС‡Р°Р№РЅС‹Рµ РїР°СѓР·С‹.
    """
    _human_move(x, y, duration)
    
    for i in range(0, count_click, 1):
        LOGGER.debug(f"click x: {x} y: {y}")
        draw_click_circle(x,y,duration=0.4)
        pag.rightClick()
        
def human_move_and_click_diff(x: int, y: int, duration: Tuple[float, float] = (0.4, 0.9),
                         count_click: int = 1) -> None:
    """
    РџРµСЂРµРґР°С‚СЊ Р°Р±СЃРѕР»СЋС‚РЅС‹Рµ РіР»РѕР±Р°Р»СЊРЅС‹Рµ РєРѕРѕСЂРґРёРЅР°С‚С‹ (x, y) Рё РІС‹РїРѕР»РЅРёС‚СЊ РїР»Р°РІРЅРѕРµ РґРІРёР¶РµРЅРёРµ
    вЂњРїРѕ-С‡РµР»РѕРІРµС‡РµСЃРєРёвЂќ + РєР»РёРє. РСЃРїРѕР»СЊР·СѓРµС‚СЃСЏ Bezier-РєСЂРёРІР°СЏ + РЅРµР±РѕР»СЊС€РёРµ СЃР»СѓС‡Р°Р№РЅС‹Рµ РїР°СѓР·С‹.
    """
    x, y = human_move_diff(x, y, duration)
    
    for i in range(0, count_click, 1):
        LOGGER.debug(f"click x: {x} y: {y}")
        draw_click_circle(x,y)
        pag.click()

def human_move(x: int, y: int, duration: Tuple[float, float] = (0.4, 0.9)):
    x = MON_X + x
    _human_move(x, y, duration)
    
def human_move_diff(diff_x: int, diff_y: int, duration: Tuple[float, float] = (0.4, 0.9)):
    x, y = pag.position()
    x = x + diff_x
    y = y + diff_y
    _human_move(x, y, duration)
    return x, y
    
def click(x: int = None, y: int = None, duration: Tuple[float, float] = (0.4, 0.9)):
    if x == None:
        x, y = pag.position()
        
    human_move_and_click(x, y) 
    
def right_click(x: int, y: int, duration: Tuple[float, float] = (0.4, 0.9)):
    human_move_and_right_click(x, y) 
    
def double_click(x: int = None, y: int = None, duration: Tuple[float, float] = (0.4, 0.9)):
    if x == None:
        x, y = pag.position()
    human_move_and_click(x, y, count_click=2)
    
def click_diff(x: int, y: int, duration: Tuple[float, float] = (0.4, 0.9)):
    human_move_and_click_diff(x, y)
    
def _bezier_point(pts: list[Tuple[int, int]], t: float) -> Tuple[int, int]:
    """
    Quadratic/ cubic bezier evaluation (De Casteljau) вЂ“ generic n-degree.
    Р’С…РѕРґ: pts вЂ” СЃРїРёСЃРѕРє С‚РѕС‡РµРє (x, y), t РѕС‚ 0.0 РґРѕ 1.0.
    Р’С‹С…РѕРґ: РєРѕРѕСЂРґРёРЅР°С‚С‹ С‚РѕС‡РєРё РЅР° РєСЂРёРІРѕР№ Р‘РµР·СЊРµ.
    """
    pts_arr = np.array(pts, dtype=float)
    while len(pts_arr) > 1:
        pts_arr = (1 - t) * pts_arr[:-1] + t * pts_arr[1:]
    return int(pts_arr[0][0]), int(pts_arr[0][1])

def _rand_near(x: int, y: int, radius: int = 80) -> Tuple[int, int]:
    """
    Р’РµСЂРЅС‘С‚ С‚РѕС‡РєСѓ РІ СЃР»СѓС‡Р°Р№РЅРѕРј РЅР°РїСЂР°РІР»РµРЅРёРё РЅР° СЂР°СЃСЃС‚РѕСЏРЅРёРё [radius*0.3 .. radius]
    РѕС‚ (x, y). РСЃРїРѕР»СЊР·СѓРµС‚СЃСЏ РґР»СЏ Р±РѕР»РµРµ В«С‡РµР»РѕРІРµС‡РµСЃРєРѕРіРѕВ» РґРІРёР¶РµРЅРёСЏ РјС‹С€Рё.
    """
    ang = random.uniform(0, 2 * np.pi)
    r = random.uniform(radius * 0.3, radius)
    return int(x + r * np.cos(ang)), int(y + r * np.sin(ang))

def draw_monitor_region_on_screen(color: tuple[int,int,int] = (0, 0, 255), thickness: int = 4) -> None:
    """
    РќР°СЂРёСЃРѕРІР°С‚СЊ РЅР° СЂР°Р±РѕС‡РµРј СЃС‚РѕР»Рµ (РЅР° СЃР°РјРѕР№ РїРѕРІРµСЂС…РЅРѕСЃС‚Рё СЌРєСЂР°РЅР°) РїРѕР»СѓРїСЂРѕР·СЂР°С‡РЅС‹Р№ (С‡РµСЂРµР· XOR)
    РёР»Рё СЃРїР»РѕС€РЅРѕР№ (С‡РµСЂРµР· GDI Rectangle) РєРѕРЅС‚СѓСЂ РѕР±Р»Р°СЃС‚Рё MON_X, MON_Y, MON_W, MON_H.

    РџР°СЂР°РјРµС‚СЂС‹:
    ---------
    color : BGR-С†РІРµС‚ СЂР°РјРєРё, РЅР°РїСЂРёРјРµСЂ (0, 0, 255) РґР»СЏ РєСЂР°СЃРЅРѕРіРѕ (РєР°Рє OpenCV).
    thickness : С‚РѕР»С‰РёРЅР° Р»РёРЅРёРё СЂР°РјРєРё РІ РїРёРєСЃРµР»СЏС….

    РџСЂРё Р·Р°РїСѓСЃРєРµ СЌС‚РѕР№ С„СѓРЅРєС†РёРё РІС‹ СѓРІРёРґРёС‚Рµ С‡С‘С‚РєСѓСЋ СЂР°РјРєСѓ РЅР° СЌРєСЂР°РЅРµ. РћРЅР° РѕС‚СЂРёСЃСѓРµС‚СЃСЏ РїРѕРІРµСЂС… РІСЃРµРіРѕ,
    РЅРѕ РёСЃС‡РµР·РЅРµС‚ РїСЂРё СЃР»РµРґСѓСЋС‰РµРј РѕР±РЅРѕРІР»РµРЅРёРё РѕРєРЅР° РёР»Рё РїСЂРё СЃР»РµРґСѓСЋС‰РµРј РІС‹Р·РѕРІРµ (РІ Р·Р°РІРёСЃРёРјРѕСЃС‚Рё РѕС‚ СЂРµР¶РёРјР°).
    """
    # 1) РЎРЅР°С‡Р°Р»Р° РІС‹С‡РёСЃР»РёРј РєРѕРѕСЂРґРёРЅР°С‚С‹ РЅСѓР¶РЅРѕРіРѕ РјРѕРЅРёС‚РѕСЂР° С‡РµСЂРµР· MSS:
    with mss.mss() as sct:
        monitors = sct.monitors
        if 1 <= MONITOR_INDEX < len(monitors):
            mon = monitors[MONITOR_INDEX]
        else:
            mon = monitors[1]  # РµСЃР»Рё СѓРєР°Р·Р°РЅ РЅРµРІРµСЂРЅС‹Р№ РёРЅРґРµРєСЃ, РІР·СЏС‚СЊ РїРµСЂРІС‹Р№
        MON_X, MON_Y, MON_W, MON_H = mon["left"], mon["top"], mon["width"], mon["height"]

    # 2) РџРѕР»СѓС‡Р°РµРј РєРѕРЅС‚РµРєСЃС‚ СѓСЃС‚СЂРѕР№СЃС‚РІР° (DC) РґР»СЏ РІСЃРµРіРѕ СЌРєСЂР°РЅР° (hwnd=0 в†’ РІРµСЃСЊ СЌРєСЂР°РЅ)
    hdc = ctypes.windll.user32.GetDC(0)

    # 3) РЎРѕР·РґР°С‘Рј РїРµСЂРѕ РЅСѓР¶РЅРѕРіРѕ С†РІРµС‚Р° Рё С‚РѕР»С‰РёРЅС‹
    #    Р’ GDI С†РІРµС‚ Р·Р°РґР°С‘С‚СЃСЏ РІ С„РѕСЂРјР°С‚Рµ 0x00BBGGRR, РїРѕСЌС‚РѕРјСѓ РїРµСЂРµРєР»Р°РґС‹РІР°РµРј:
    b, g, r = color
    gdi_color = (r << 16) | (g << 8) | b

    PS_SOLID = 0          # СЃРїР»РѕС€РЅР°СЏ Р»РёРЅРёСЏ
    pen = ctypes.windll.gdi32.CreatePen(PS_SOLID, thickness, gdi_color)
    old_pen = ctypes.windll.gdi32.SelectObject(hdc, pen)

    # 4) РџРѕР»СѓС‡Р°РµРј В«РїСѓСЃС‚СѓСЋ РєРёСЃС‚СЊВ» (NULL_BRUSH), С‡С‚РѕР±С‹ РІРЅСѓС‚СЂРё РЅРµ Р·Р°Р»РёРІР°С‚СЊ
    NULL_BRUSH = 5  # РёРЅРґРµРєСЃ РІ GDI РґР»СЏ В«null brushВ»
    brush = ctypes.windll.gdi32.GetStockObject(NULL_BRUSH)
    old_brush = ctypes.windll.gdi32.SelectObject(hdc, brush)

    # 5) Р РёСЃСѓРµРј РїСЂСЏРјРѕСѓРіРѕР»СЊРЅРёРє. РџР°СЂР°РјРµС‚СЂС‹: hdc, left, top, right, bottom
    left   = MON_X
    top    = MON_Y
    right  = MON_X + MON_W
    bottom = MON_Y + MON_H

    # Rectangle СЂРёСЃСѓРµС‚ СЂР°РјРєСѓ РјРµР¶РґСѓ (left, top) Рё (right, bottom)
    ctypes.windll.gdi32.Rectangle(hdc, left, top, right, bottom)

    # 6) Р’РѕР·РІСЂР°С‰Р°РµРј РїСЂРµРґС‹РґСѓС‰РµРµ РїРµСЂРѕ/РєРёСЃС‚СЊ Рё СѓРґР°Р»СЏРµРј СЃРѕР·РґР°РЅРЅС‹Рµ РѕР±СЉРµРєС‚С‹
    ctypes.windll.gdi32.SelectObject(hdc, old_pen)
    ctypes.windll.gdi32.SelectObject(hdc, old_brush)
    ctypes.windll.gdi32.DeleteObject(pen)

    # 7) РћСЃРІРѕР±РѕР¶РґР°РµРј DC
    ctypes.windll.user32.ReleaseDC(0, hdc)


def replace_similar_chars(word: str) -> str:
    char_map = {
        'e': 'Рµ',  # Р°РЅРіР» e в†’ СѓРєСЂ Рµ
        'E': 'Р•',  # Р°РЅРіР» E в†’ СѓРєСЂ Р•
        'i': 'С–',  # Р°РЅРіР» i в†’ СѓРєСЂ С– (РїРѕ РЅРµРѕР±С…РѕРґРёРјРѕСЃС‚Рё)
        'I': 'Р†',  # Р°РЅРіР» I в†’ СѓРєСЂ Р†
        'a': 'Р°',  # Р°РЅРіР» a в†’ СѓРєСЂ Р°
        'A': 'Рђ',  # Р°РЅРіР» A в†’ СѓРєСЂ Рђ
        'o': 'Рѕ',  # Р°РЅРіР» o в†’ СѓРєСЂ Рѕ
        'O': 'Рћ',  # Р°РЅРіР» O в†’ СѓРєСЂ Рћ
        'c': 'СЃ',  # Р°РЅРіР» c в†’ СѓРєСЂ СЃ
        'C': 'РЎ',  # Р°РЅРіР» C в†’ СѓРєСЂ РЎ
        'p': 'СЂ',  # Р°РЅРіР» p в†’ СѓРєСЂ СЂ
        'P': 'Р ',  # Р°РЅРіР» P в†’ СѓРєСЂ Р 
        'x': 'С…',  # Р°РЅРіР» x в†’ СѓРєСЂ С…
        'X': 'РҐ',  # Р°РЅРіР» X в†’ СѓРєСЂ РҐ
    }
    return ''.join(char_map.get(c, c) for c in word)

def read_text(
    lang: str,
    scope: tuple[int, int, int, int] = None,
    is_debug: bool = False
) -> [str]:
    """
    OCR-based read text
    
    """
    
    scr_bgr = screen(scope, is_debug = is_debug)
    
    os.environ['TESSDATA_PREFIX'] = os.path.normpath(TESSDATA_PREFIX)
    pytesseract.pytesseract.tesseract_cmd = r"C:/Program Files/Tesseract-OCR/tesseract.exe"

    data = pytesseract.image_to_data(
        scr_bgr, lang=lang, output_type=pytesseract.Output.DICT
    )

    raw_texts = data.get("text", []) or []
    texts = [_safe_norm_text(t) for t in raw_texts]
    LOGGER.debug(f"read texts: {texts}")
    return texts

def get_first_date(text_list) -> date:
    date_pattern = r'\b\d{2}\.\d{2}\.\d{4}\b'
    for text in text_list:
        match = re.search(date_pattern, text)
        if match:
            date_str = match.group()
            return _dt.strptime(date_str, '%d.%m.%Y').date()
    return None

def read_first_date(
    lang: str,
    scope: tuple[int, int, int, int] = None,
    is_debug: bool = False
) -> date:
    """
    OCR-based read text
    
    """

    texts = read_text(lang, scope, is_debug)
    dt = get_first_date(texts)
    
    return dt

def click_text(
    query: str|Iterable[str],
    lang: str,
    count_attempt_find: int = 1,
    pause_attempt: int = 2,
    scope: tuple[int, int, int, int] | None = None,
    plus_y: int = 0,
    plus_x: int = 0,
    count_click: int = 1,
    is_debug: bool = False,
    threshold: float = 0.7,
    occurrence: int = 1,
    duration: Tuple[float, float] = (0.2, 0.3),
) -> bool | Tuple[List[Tuple[int, int]], Tuple[int, int] | None]:
    """
    OCR-based search: РЅР°Р№С‚Рё С‚РµРєСЃС‚ `query` РЅР° СЌРєСЂР°РЅРµ (РІ РїСЂРµРґРµР»Р°С… MON_X..MON_W, MON_Y..MON_H)
    Рё РєР»РёРєРЅСѓС‚СЊ РµРіРѕ С†РµРЅС‚СЂ.
    Р’РѕР·РІСЂР°С‰Р°РµС‚ True, РµСЃР»Рё СѓРґР°Р»РѕСЃСЊ РЅР°Р№С‚Рё Рё РєР»РёРєРЅСѓС‚СЊ, РёРЅР°С‡Рµ False РїРѕ РёСЃС‚РµС‡РµРЅРёРё timeout.

    РџР°СЂР°РјРµС‚СЂС‹:
    -----------
    query : str
        РџРѕРґСЃС‚СЂРѕРєР° (Р±РµР· СѓС‡С‘С‚Р° СЂРµРіРёСЃС‚СЂР°), РєРѕС‚РѕСЂСѓСЋ РёС‰РµРј СЃСЂРµРґРё СЂР°СЃРїРѕР·РЅР°РЅРЅС‹С… СЃР»РѕРІ.
    timeout : float
        РњР°РєСЃРёРјР°Р»СЊРЅРѕРµ РІСЂРµРјСЏ (РІ СЃРµРєСѓРЅРґР°С…) РЅР° РїРѕРїС‹С‚РєРё РїРѕРёСЃРєР°.
    lang : str
        РЇР·С‹Рє Tesseract (РЅР°РїСЂРёРјРµСЂ, "eng", "rus", "ukr").
    conf_threshold : float
        РњРёРЅРёРјР°Р»СЊРЅС‹Р№ РїРѕСЂРѕРі РґРѕРІРµСЂРёСЏ (0.0вЂ“1.0) РґР»СЏ СЂР°СЃРїРѕР·РЅР°РЅРЅС‹С… СЃР»РѕРІ.
    padding : tuple[int, int, int, int], optional
        РЎРјРµС‰РµРЅРёРµ (left, bottom, right, top) РґР»СЏ СЃСѓР¶РµРЅРёСЏ РѕР±Р»Р°СЃС‚Рё СЃРєСЂРёРЅС€РѕС‚Р°.
    """
    LOGGER.debug(f"find and click {query},scope: {scope}")
    
    pos = None
    
    if isinstance(query, str):
        pos = find_text(query=query, lang=lang, 
                        count=count_attempt_find, 
                        pause_attempt = pause_attempt, 
                        scope=scope, plus_y = plus_y,
                        is_debug=is_debug, occurrence = occurrence)
        
    elif isinstance(query, Iterable):
        start = time.perf_counter()
        pos = find_text_any(queries=query, lang=lang, 
                            count=count_attempt_find, 
                            pause_attempt_sec = pause_attempt, 
                            scope=scope, 
                            threshold = threshold,
                            is_debug=is_debug, 
                            occurrence = occurrence)
        end = time.perf_counter()
        tm = end - start
        
    else:
        print("click_text error value query")
    
    if pos:
        print(f"time find_text_any queries= {query}  : {tm}")
        abs_x, abs_y = pos
        human_move_and_click(abs_x + plus_x, abs_y + plus_y, duration, count_click=count_click)
        return pos
    else:
        print(f"Not find time find_text_any queries= {query}  : {tm}")

    time.sleep(0.2)

    return False

def find_text(
    query: str,
    lang: str,
    count: int = 1,
    pause_attempt: int = 2,
    scope: tuple[int, int, int, int] | None = None,
    plus_y: int = 0,
    is_debug: bool = False,
    occurrence: int = 1,  # РЅРѕРјРµСЂ СЃРѕРІРїР°РґРµРЅРёСЏ
) -> tuple[int, int] | None:
    """
    OCR-based search: РЅР°Р№С‚Рё С‚РµРєСЃС‚ `query` РЅР° СЌРєСЂР°РЅРµ (РІ РїСЂРµРґРµР»Р°С… MON_X..MON_W, MON_Y..MON_H).

    Р’РѕР·РІСЂР°С‰Р°РµС‚ x, y С†РµРЅС‚СЂР° N-РіРѕ СЃРѕРІРїР°РґРµРЅРёСЏ, РёРЅР°С‡Рµ None РїРѕ РёСЃС‚РµС‡РµРЅРёРё count РїРѕРїС‹С‚РѕРє.

    РџР°СЂР°РјРµС‚СЂС‹:
    -----------
    query : str
        РџРѕРґСЃС‚СЂРѕРєР° (Р±РµР· СѓС‡С‘С‚Р° СЂРµРіРёСЃС‚СЂР°), РєРѕС‚РѕСЂСѓСЋ РёС‰РµРј СЃСЂРµРґРё СЂР°СЃРїРѕР·РЅР°РЅРЅС‹С… СЃР»РѕРІ.
    lang : str
        РЇР·С‹Рє Tesseract (РЅР°РїСЂРёРјРµСЂ, "eng", "rus", "ukr").
    count : int
        РљРѕР»-РІРѕ РїРѕРїС‹С‚РѕРє РїРѕРёСЃРєР° СЃ РїР°СѓР·РѕР№ РјРµР¶РґСѓ РЅРёРјРё.
    pause_attempt : int
        РџР°СѓР·Р° (СЃРµРє) РјРµР¶РґСѓ РїРѕРїС‹С‚РєР°РјРё.
    scope : (x, y, w, h)
        РћР±Р»Р°СЃС‚СЊ СЌРєСЂР°РЅР° РґР»СЏ OCR. Р•СЃР»Рё None вЂ” РІРµСЃСЊ СЌРєСЂР°РЅ.
    plus_y : int
        Р”РѕРї. СЃРјРµС‰РµРЅРёРµ РІРЅРёР· РїРѕ Y.
    is_debug : bool
        Р’РєР»СЋС‡РёС‚СЊ РѕС‚Р»Р°РґРєСѓ.
    occurrence : int
        РќРѕРјРµСЂ СЃРѕРІРїР°РґРµРЅРёСЏ (1 = РїРµСЂРІРѕРµ, 2 = РІС‚РѕСЂРѕРµ Рё С‚.Рґ.)
    """

    if occurrence < 1:
        occurrence = 1

    LOGGER.debug(f"start find text: {query}")
    query_words = query.lower().split()
    query_words = [replace_similar_chars(w) for w in query_words]
    n_words = len(query_words)

    attempts = 0
    while attempts < count:
        attempts += 1

        scr_bgr = screen(scope, is_debug=is_debug)

        os.environ['TESSDATA_PREFIX'] = os.path.normpath(TESSDATA_PREFIX)
        pytesseract.pytesseract.tesseract_cmd = r"C:/Program Files/Tesseract-OCR/tesseract.exe"

        data = pytesseract.image_to_data(
            scr_bgr, lang=lang, output_type=pytesseract.Output.DICT
        )

        raw_texts = data.get("text", []) or []
        texts = [_safe_norm_text(t) for t in raw_texts]
        ocr_texts = [w for w in texts if w]  # РѕС‚Р±СЂР°СЃС‹РІР°РµРј РїСѓСЃС‚С‹Рµ
        LOGGER.debug(f"OCR texts: {ocr_texts}")

        if len(ocr_texts) == 0 and attempts == count:
            return None

        n_boxes = min(
            len(data.get("text", [])),
            len(data.get("left", [])),
            len(data.get("top", [])),
            len(data.get("width", [])),
            len(data.get("height", [])),
        )
        found_count = 0  # СЃС‡С‘С‚С‡РёРє СЃРѕРІРїР°РґРµРЅРёР№

        for i in range(n_boxes - n_words + 1):
            window = texts[i:i + n_words]
            window = [replace_similar_chars(w) for w in window]

            if arrays_fuzzy_equal_as_one_str(window, query_words):
                found_count += 1

                if found_count == occurrence:
                    x_left = min(int(data["left"][j]) for j in range(i, i + n_words) if j < n_boxes)
                    y_top = min(int(data["top"][j]) for j in range(i, i + n_words) if j < n_boxes)
                    x_right = max(int(data["left"][j]) + int(data["width"][j]) for j in range(i, i + n_words) if j < n_boxes)
                    y_bottom = max(int(data["top"][j]) + int(data["height"][j]) for j in range(i, i + n_words) if j < n_boxes)


                    center_x_rel = (x_left + x_right) // 2
                    center_y_rel = (y_top + y_bottom) // 2

                    scope_left, scope_top = (scope[0], scope[1]) if scope else (0, 0)
                    abs_x = MON_X + center_x_rel + scope_left
                    abs_y = MON_Y + center_y_rel + scope_top

                    LOGGER.debug(
                        f"Found #{found_count} phrase '{query}' "
                        f"at local ({center_x_rel},{center_y_rel}), "
                        f"global ({abs_x},{abs_y})"
                    )
                    return abs_x, abs_y + plus_y

        pause(pause_attempt)

    LOGGER.debug(f"Text '{query}' with occurrence={occurrence} not found after {attempts} attempts")
    return None

def init_tesseract(tess_root=r"C:\Program Files\Tesseract-OCR", lang_check=("eng","rus")):
    tess_root = os.path.normpath(tess_root)
    tess_exe  = os.path.join(tess_root, "tesseract.exe")
    tessdata  = os.path.join(tess_root, "tessdata")

    # 1) Р±Р°Р·РѕРІС‹Рµ РїСЂРѕРІРµСЂРєРё
    if not os.path.isfile(tess_exe):
        raise FileNotFoundError(f"tesseract.exe not found: {tess_exe}")
    if not os.path.isdir(tessdata):
        raise FileNotFoundError(f"tessdata folder not found: {tessdata}")

    # 2) СЃР±СЂРѕСЃРёС‚СЊ РєСЂРёРІСѓСЋ РЅР°СЃС‚СЂРѕР№РєСѓ, РµСЃР»Рё Р±С‹Р»Р°
    os.environ.pop("TESSDATA_PREFIX", None)
    # Р’РђР–РќРћ: СѓРєР°Р·С‹РІР°С‚СЊ РРњР•РќРќРћ РєРѕСЂРµРЅСЊ, РќР• tessdata
    os.environ["TESSDATA_PREFIX"] = tess_root

    # 3) РїСѓС‚СЊ Рє Р±РёРЅР°СЂРЅРёРєСѓ
    pytesseract.pytesseract.tesseract_cmd = tess_exe

    # 4) РїСЂРѕРІРµСЂРёС‚СЊ РЅР°Р»РёС‡РёРµ СЏР·С‹РєРѕРІ
    missing = [lng for lng in lang_check
               if not os.path.isfile(os.path.join(tessdata, f"{lng}.traineddata"))]
    if missing:
        raise FileNotFoundError(f"Missing traineddata: {', '.join(missing)} in {tessdata}")

    # 5) Р±С‹СЃС‚СЂР°СЏ СЃР°РјРѕРїСЂРѕРІРµСЂРєР° (РїРѕ Р¶РµР»Р°РЅРёСЋ)
    try:
        _ = pytesseract.get_tesseract_version()
    except Exception as e:
        raise RuntimeError(f"Tesseract not initialized: {e}")

def find_text_any(
    queries: Iterable[str],
    lang: str,
    count: int = 1,
    pause_attempt_sec: int = 1,
    scope: tuple[int, int, int, int] | None = None,
    is_debug: bool = False,
    occurrence: int = 1,
    threshold: float = 0.7,
    font_scale: float = 0.7,
    font_thickness: int = 2,
) -> Tuple[List[Tuple[int, int]], Optional[Tuple[int, int]]] | None:
    """
    РС‰РµС‚ Р»СЋР±РѕР№ РёР· С‚РµРєСЃС‚РѕРІ `queries` РЅР° СЌРєСЂР°РЅРµ, РІРёР·СѓР°Р»РёР·РёСЂСѓРµС‚ РІСЃРµ РЅР°С…РѕР¶РґРµРЅРёСЏ
    Рё РІРѕР·РІСЂР°С‰Р°РµС‚:
      - СЃРїРёСЃРѕРє Р°Р±СЃРѕР»СЋС‚РЅС‹С… РєРѕРѕСЂРґРёРЅР°С‚ С†РµРЅС‚СЂРѕРІ РІСЃРµС… СЃРѕРІРїР°РґРµРЅРёР№ [(abs_x, abs_y), ...]
      - РєРѕРѕСЂРґРёРЅР°С‚С‹ N-РіРѕ РїРѕ РїРѕСЂСЏРґРєСѓ СЃРѕРІРїР°РґРµРЅРёСЏ (occurrence) РёР»Рё None

    РџСЂР°РІРёР»Р°:
      - РџРѕСЂСЏРґРѕРє РЅСѓРјРµСЂР°С†РёРё СЃРѕРѕС‚РІРµС‚СЃС‚РІСѓРµС‚ РїРѕСЂСЏРґРєСѓ РѕР±РЅР°СЂСѓР¶РµРЅРёСЏ (СЃРєР°РЅРёСЂРѕРІР°РЅРёРµ СЃР»РµРІР° РЅР°РїСЂР°РІРѕ РїРѕ OCR-РѕРєРЅР°Рј).
      - РќР° РєР°СЂС‚РёРЅРєРµ: РІСЃРµ СЃРѕРІРїР°РґРµРЅРёСЏ Р¶С‘Р»С‚С‹Рµ СЃ РЅРѕРјРµСЂРѕРј; occurrence вЂ” РєСЂР°СЃРЅР°СЏ СЂР°РјРєР°.
      - Р•СЃР»Рё РЅР° РїРѕСЃР»РµРґРЅРµР№ РїРѕРїС‹С‚РєРµ OCR РЅРµ РґР°Р» РЅРё РѕРґРЅРѕРіРѕ СЃР»РѕРІР° вЂ” РІРѕР·РІСЂР°С‰Р°РµС‚СЃСЏ ([], None).

    Р’Р°Р¶РЅРѕ: РёСЃРїРѕР»СЊР·СѓРµС‚СЃСЏ screen(process_for_read=True) РґР»СЏ OCR.
    """
    
    if occurrence < 1:
        occurrence = 1
        
    queries = [q for q in queries if isinstance(q, str) and q.strip()]

    queries_words = [q.lower().split() for q in queries]
    attempts = 0

    while attempts < count:
        attempts += 1

        # 1) РЎРєСЂРёРЅ РѕР±Р»Р°СЃС‚Рё (OCR-РїСЂРµРґРѕР±СЂР°Р±РѕС‚РєР° РІРєР»СЋС‡РµРЅР°)
        scr_bgr = screen(scope=scope, process_for_read=True, is_debug=is_debug)
        vis_bgr = scr_bgr.copy()

        # 2) OCR
        data = pytesseract.image_to_data(scr_bgr, lang=lang, output_type=Output.DICT)

        texts: List[str] = []
        n_boxes = min(
            len(data.get("text", [])),
            len(data.get("left", [])),
            len(data.get("top", [])),
            len(data.get("width", [])),
            len(data.get("height", [])),
        )

        for i in range(n_boxes):
            txt = _safe_norm_text(data["text"][i] if i < len(data["text"]) else "")
            texts.append(txt)

        ocr_texts = [w for w in texts if w]
        if not ocr_texts and attempts == count:
            return None


        # 4) РџРѕРёСЃРє СЃРѕРІРїР°РґРµРЅРёР№
        matches: List[Tuple[int, int]] = []  # Р°Р±СЃРѕР»СЋС‚РЅС‹Рµ С†РµРЅС‚СЂС‹ РІСЃРµС… СЃРѕРІРїР°РґРµРЅРёР№
        boxes: List[Tuple[int, int, int, int]] = []  # x1,y1,x2,y2 РґР»СЏ РІРёР·СѓР°Р»РёР·Р°С†РёРё
        labels: List[str] = []  # РёСЃС…РѕРґРЅС‹Р№ С‚РµРєСЃС‚ РѕРєРЅР° РґР»СЏ РїРѕРґРїРёСЃРё
        nth_abs: Optional[Tuple[int, int]] = None
        nth_idx: Optional[int] = None  # РёРЅРґРµРєСЃ СЃРѕРІРїР°РґРµРЅРёСЏ (1-based) РґР»СЏ РїРѕРґСЃРІРµС‚РєРё

        scope_left, scope_top = (scope[0], scope[1]) if scope is not None else (0, 0)

        found_count = 0
        for query_words in queries_words:
            normalized_query = [replace_similar_chars(w) for w in query_words]
            n_words = len(normalized_query)
            if n_words == 0:
                continue

            for i in range(0, n_boxes - n_words + 1):
                window = texts[i: i + n_words]
                if any(w == "" for w in window):
                    continue

                normalized_window = [replace_similar_chars(w) for w in window]

                if arrays_fuzzy_equal_as_one_str(normalized_window, normalized_query, threshold):
                    # РЎРѕР±РёСЂР°РµРј РѕР±С‰РёР№ bbox РїРѕ СЃР»РѕРІР°Рј i..i+n_words-1
                    x_left = min(int(data["left"][j]) for j in range(i, i + n_words))
                    y_top = min(int(data["top"][j]) for j in range(i, i + n_words))
                    x_right = max(int(data["left"][j]) + int(data["width"][j]) for j in range(i, i + n_words))
                    y_bottom = max(int(data["top"][j]) + int(data["height"][j]) for j in range(i, i + n_words))

                    center_x_rel = (x_left + x_right) // 2
                    center_y_rel = (y_top + y_bottom) // 2

                    abs_x = scope_left + center_x_rel
                    abs_y = scope_top + center_y_rel

                    found_count += 1
                    matches.append((abs_x, abs_y))
                    boxes.append((x_left, y_top, x_right, y_bottom))
                    labels.append(" ".join(window).strip())

                    if found_count == occurrence:
                        nth_abs = (abs_x, abs_y)
                        nth_idx = found_count  # 1-based

        # 5) Р’РёР·СѓР°Р»РёР·Р°С†РёСЏ вЂ” РЅСѓРјРµСЂР°С†РёСЏ РІСЃРµС… СЃРѕРІРїР°РґРµРЅРёР№ + РІС‹РґРµР»РµРЅРёРµ occurrence
        if is_debug and boxes:
            for idx, ((x1, y1, x2, y2), label) in enumerate(zip(boxes, labels), start=1):
                # Р’СЃРµ СЃРѕРІРїР°РґРµРЅРёСЏ вЂ” Р¶С‘Р»С‚С‹Рµ
                cv2.rectangle(vis_bgr, (x1, y1), (x2, y2), (0, 255, 255), 2)
                cv2.putText(
                    vis_bgr,
                    f"{idx}",
                    (x1, max(0, y1 - 6)),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    font_scale,
                    (0, 255, 255),
                    font_thickness,
                    cv2.LINE_AA,
                )
                # РњРѕР¶РЅРѕ РґРѕРїРёСЃР°С‚СЊ С‚РµРєСЃС‚ СЂСЏРґРѕРј РїСЂРё РЅРµРѕР±С…РѕРґРёРјРѕСЃС‚Рё:
                # cv2.putText(vis_bgr, label, (x1 + 18, max(0, y1 - 6)), cv2.FONT_HERSHEY_SIMPLEX,
                #             font_scale, (0, 255, 255), max(1, font_thickness - 1), cv2.LINE_AA)

            # РџРѕРґСЃРІРµС‚РєР° occurrence вЂ” РєСЂР°СЃРЅС‹Рј Рё С‚РѕР»С‰Рµ
            if nth_idx is not None:
                x1, y1, x2, y2 = boxes[nth_idx - 1]
                cv2.rectangle(vis_bgr, (x1, y1), (x2, y2), (0, 0, 255), max(3, font_thickness + 1))
                cv2.putText(
                    vis_bgr,
                    f"[{nth_idx}]",
                    (x1, max(0, y1 - 8 - int(12 * font_scale))),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    font_scale,
                    (0, 0, 255),
                    max(2, font_thickness),
                    cv2.LINE_AA,
                )

            show_image(vis_bgr)

        # 6) Р’РѕР·РІСЂР°С‰Р°РµРј РјР°СЃСЃРёРІ Рё N-Р№ СЌР»РµРјРµРЅС‚ (РµСЃР»Рё РµСЃС‚СЊ) вЂ” СЃСЂР°Р·Сѓ РїРѕСЃР»Рµ РїРµСЂРІРѕР№ СЂРµР·СѓР»СЊС‚Р°С‚РёРІРЅРѕР№ РїРѕРїС‹С‚РєРё
        if matches or attempts == count:
            # Р•СЃР»Рё РЅРёС‡РµРіРѕ РЅРµ РЅР°Р№РґРµРЅРѕ, РІРµСЂРЅС‘Рј РїСѓСЃС‚РѕР№ РјР°СЃСЃРёРІ Рё None
            return nth_abs

        # РРЅР°С‡Рµ Р¶РґС‘Рј Рё РїРѕРІС‚РѕСЂСЏРµРј
        pause(pause_attempt_sec)

def cursor_move_to(
    x: int = 500,
    y: int = 500
) -> None:
   
    x = MON_X + x
    LOGGER.debug("Cursor moved to global (%d,%d)", x, y)                    
    human_move_and_click(x, y)

def contrlScroll(amount:int):
    time.sleep(1)
    
    pag.keyDown('ctrl')
    time.sleep(0.1)

    pag.scroll(amount)

    time.sleep(1)
    # РћС‚РїСѓСЃРєР°РµРј Ctrl
    pag.keyUp('ctrl')
    
    time.sleep(1) 
    
def remove_green_background(src_bgr: np.ndarray) -> np.ndarray:
    """
    РџСЂРµРІСЂР°С‰Р°РµС‚ Р·РµР»С‘РЅС‹Рµ Р±Р»РѕРєРё РІ С‡РёСЃС‚Рѕ-Р±РµР»С‹Р№ С„РѕРЅ, РѕСЃС‚Р°РІР»СЏСЏ С‚РµРєСЃС‚ (Рё РІСЃС‘ РѕСЃС‚Р°Р»СЊРЅРѕРµ) РЅРµС‚СЂРѕРЅСѓС‚С‹Рј.
    Р’РѕР·РІСЂР°С‰Р°РµС‚ BGR-РёР·РѕР±СЂР°Р¶РµРЅРёРµ, РіРґРµ В«Р·РµР»С‘РЅРѕРµВ» СЃС‚Р°Р»Рѕ (255,255,255).
    """
    # 1. РџРµСЂРµРІРѕРґРёРј РІ РїСЂРѕСЃС‚СЂР°РЅСЃС‚РІРѕ HSV, С‡С‚РѕР±С‹ Р»РµРіРєРѕ РѕС‚С„РёР»СЊС‚СЂРѕРІР°С‚СЊ Р·РµР»С‘РЅС‹Р№
    hsv = cv2.cvtColor(src_bgr, cv2.COLOR_BGR2HSV)

    # 2. Р—Р°РґР°С‘Рј РґРёР°РїР°Р·РѕРЅ В«Р·РµР»С‘РЅРѕРіРѕВ»
    #    РќРёР¶РЅРёР№ Рё РІРµСЂС…РЅРёР№ РїРѕСЂРѕРі РіСЂР°РЅРёС† H, S, V вЂ” РјРѕР¶РЅРѕ РїРѕРґРєРѕСЂСЂРµРєС‚РёСЂРѕРІР°С‚СЊ РїРѕРґ РІР°С€ РѕС‚С‚РµРЅРѕРє
    lower_green = np.array([40,  40,  40])   # РЅР°РїСЂРёРјРµСЂ: Hв‰€60В°, РЅРѕ OpenCV: H РѕС‚ 0 РґРѕ 179
    upper_green = np.array([80, 255, 255])

    # 3. Р”РµР»Р°РµРј РјР°СЃРєСѓ: РіРґРµ РїРёРєСЃРµР»Рё В«Р·РµР»РµРЅС‹РµВ» в†’ 255, РѕСЃС‚Р°Р»СЊРЅРѕРµ в†’ 0
    mask_green = cv2.inRange(hsv, lower_green, upper_green)

    # 4. Invert mask: РіРґРµ РќР• Р·РµР»С‘РЅРѕРµ (С‚РµРєСЃС‚, РѕСЃС‚Р°Р»СЊРЅС‹Рµ СЌР»РµРјРµРЅС‚С‹) в†’ 255, РіРґРµ Р·РµР»С‘РЅРѕРµ в†’ 0
    mask_not_green = cv2.bitwise_not(mask_green)

    # 5. РЎРѕР·РґР°С‘Рј В«С„РѕРЅВ» РїРѕР»РЅРѕСЃС‚СЊСЋ Р±РµР»РѕРіРѕ С†РІРµС‚Р° С‚РѕРіРѕ Р¶Рµ СЂР°Р·РјРµСЂР°
    white_bg = np.full_like(src_bgr, fill_value=255)

    # 6. РќР°РєР»Р°РґС‹РІР°РµРј: РЅР° РёСЃС…РѕРґРЅРѕРј РёР·РѕР±СЂР°Р¶РµРЅРёРё РІСЃС‘, С‡С‚Рѕ РќР• Р·РµР»С‘РЅРѕРµ, РѕСЃС‚Р°РІР»СЏРµРј (AND СЃ mask_not_green),
    #    Р° РІ РјРµСЃС‚Р°С… В«Р·РµР»С‘РЅРѕРіРѕВ» Р±СѓРґРµРј Р±СЂР°С‚СЊ Р±РµР»С‹Р№ С„РѕРЅ (AND СЃ mask_green Рё Р±РµР»С‹Р№)
    fg = cv2.bitwise_and(src_bgr, src_bgr, mask=mask_not_green)
    bg = cv2.bitwise_and(white_bg, white_bg, mask=mask_green)

    # 7. РЎРєР»РµРёРІР°РµРј: РїРѕР»СѓС‡Р°РµС‚СЃСЏ РєР°СЂС‚РёРЅРєР°, РіРґРµ В«Р·РµР»С‘РЅРѕРµВ» Р·Р°РјРµРЅРµРЅРѕ РЅР° Р±РµР»РѕРµ
    result = cv2.add(fg, bg)
    return result

def sharpen_filter(src_bgr: np.ndarray) -> np.ndarray:
    """
    РџСЂРёРјРµРЅСЏРµС‚ Рє BGR-РёР·РѕР±СЂР°Р¶РµРЅРёСЋ РїСЂРѕСЃС‚РѕР№ С„РёР»СЊС‚СЂ СЂРµР·РєРѕСЃС‚Рё.
    Р’РѕР·РІСЂР°С‰Р°РµС‚ В«СЂРµР·С‡РµВ» BGR-РёР·РѕР±СЂР°Р¶РµРЅРёРµ.
    """
    # РћРїСЂРµРґРµР»СЏРµРј kernel
    kernel = np.array([
        [ 0, -1,  0],
        [-1,  5, -1],
        [ 0, -1,  0]
    ], dtype=np.float32)

    # РџСЂРёРјРµРЅСЏРµРј С„РёР»СЊС‚СЂ СЃРІС‘СЂС‚РєРё
    sharpened = cv2.filter2D(src_bgr, ddepth=-1, kernel=kernel)
    return sharpened

def unsharp_mask(src_bgr: np.ndarray, 
                 blur_ksize: tuple[int, int] = (9, 9), 
                 sigma: float = 10.0, 
                 amount: float = 1.5, 
                 threshold: int = 0) -> np.ndarray:
    """
    РџР°СЂР°РјРµС‚СЂС‹:
    - blur_ksize: СЂР°Р·РјРµСЂ СЏРґСЂР° РґР»СЏ GaussianBlur (РґРѕР»Р¶РµРЅ Р±С‹С‚СЊ РЅРµС‡С‘С‚РЅС‹Рј, РЅР°РїСЂ. (9,9)).
    - sigma: РѕС‚РєР»РѕРЅРµРЅРёРµ РїРѕ Р“Р°СѓСЃСЃСѓ (С‡РµРј Р±РѕР»СЊС€Рµ, С‚РµРј СЃРёР»СЊРЅРµРµ СЃРіР»Р°Р¶РёРІР°РЅРёРµ).
    - amount: РІРѕ СЃРєРѕР»СЊРєРѕ СЂР°Р· СѓСЃРёР»РёРІР°РµС‚СЃСЏ В«РјР°СЃРєР° СЂРµР·РєРѕСЃС‚РёВ».
    - threshold: РјРёРЅРёРјР°Р»СЊРЅР°СЏ СЂР°Р·РЅРёС†Р° СЏСЂРєРѕСЃС‚Рё, РїСЂРё РєРѕС‚РѕСЂРѕР№ РїСЂРѕРёСЃС…РѕРґРёС‚ СѓСЃРёР»РµРЅРёРµ; 0 вЂ” Р±РµР· РїРѕСЂРѕРіР°.
    """
    # 1) РЎРіР»Р°Р¶РёРІР°РµРј
    blurred = cv2.GaussianBlur(src_bgr, blur_ksize, sigma)

    # 2) Р’С‹С‡РёСЃР»СЏРµРј В«РјР°СЃРєСѓВ»: РѕСЂРёРіРёРЅР°Р» в€’ СЂР°Р·РјС‹С‚РёРµ
    mask = cv2.subtract(src_bgr, blurred)

    # 3) РЈСЃРёР»РёРІР°РµРј РјР°СЃРєСѓ Рё СЃРєР»Р°РґС‹РІР°РµРј СЃ РѕСЂРёРіРёРЅР°Р»РѕРј
    sharpened = cv2.addWeighted(src_bgr, 1.0, mask, amount, 0)

    if threshold > 0:
        # Р”РѕРїРѕР»РЅРёС‚РµР»СЊРЅРѕ: РїРѕСЂРѕРіРѕРІРѕРµ СѓСЃРёР»РµРЅРёРµ (Optional)
        # Р Р°Р·РЅРёС†Р° РјРµР¶РґСѓ РѕСЂРёРіРёРЅР°Р»РѕРј Рё СЂР°Р·РјС‹С‚С‹Рј (РїРѕ РєР°РЅР°Р»Р°Рј)
        low_contrast_mask = np.absolute(src_bgr - blurred) < threshold
        # Р’ С‚РµС… РјРµСЃС‚Р°С…, РіРґРµ РєРѕРЅС‚СЂР°СЃС‚ РЅРёР·РєРёР№, РѕСЃС‚Р°РІР»СЏРµРј РѕСЂРёРіРёРЅР°Р»
        np.copyto(sharpened, src_bgr, where=low_contrast_mask)

    return sharpened

def preprocess_for_ocr(src_bgr: np.ndarray) -> np.ndarray:
    """
    1) РЈРґР°Р»СЏРµС‚ Р·РµР»С‘РЅС‹Р№ С„РѕРЅ (РІС‹Р·С‹РІР°СЏ remove_green_background)
    2) РљРѕРЅРІРµСЂС‚РёСЂСѓРµС‚ РІ СЃРµСЂС‹Р№ + CLAHE (Р»РѕРєР°Р»СЊРЅРѕРµ РІС‹СЂР°РІРЅРёРІР°РЅРёРµ РіРёСЃС‚РѕРіСЂР°РјРјС‹)
    3) РђРґР°РїС‚РёРІРЅСѓСЋ Р±РёРЅР°СЂРёР·Р°С†РёСЋ (С‡С‘СЂРЅРѕ-Р±РµР»РѕРµ)
    """
    # 1) РЈР±РёСЂР°РµРј Р·РµР»С‘РЅС‹Р№ С„РѕРЅ
    no_green = unsharp_mask(remove_green_background(src_bgr))

    # 2) Р’ РѕС‚С‚РµРЅРєРё СЃРµСЂРѕРіРѕ
    gray = cv2.cvtColor(no_green, cv2.COLOR_BGR2GRAY)

    # 3) CLAHE РґР»СЏ РїРѕРІС‹С€РµРЅРёСЏ РєРѕРЅС‚СЂР°СЃС‚Р°
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    equalized = clahe.apply(gray)

    # 4) РђРґР°РїС‚РёРІРЅР°СЏ Р±РёРЅР°СЂРёР·Р°С†РёСЏ (Р»РѕРєР°Р»СЊРЅР°СЏ) вЂ” С‡Р°С‰Рµ РІСЃРµРіРѕ Р»СѓС‡С€Рµ, С‡РµРј РїСЂРѕСЃС‚Рѕ Otsu
    bw = cv2.adaptiveThreshold(
        equalized,
        255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY,
        blockSize=11,  # РЅРµС‡С‘С‚РЅС‹Р№ СЂР°Р·РјРµСЂ; РјРѕР¶РЅРѕ РІР°СЂСЊРёСЂРѕРІР°С‚СЊ (11, 15, 21)
        C=2             # РєРѕРЅСЃС‚Р°РЅС‚Р°, РІС‹С‡РёС‚Р°РµРјР°СЏ РёР· СЃСЂРµРґРЅРµРіРѕ
    )
    return bw

def find_first_free_slot_in_day_week(scope: tuple[int,int,int,int],
                                     is_debug: bool = False
                                    ) -> tuple[int,int] | None:

    # 1) Р—Р°С…РІР°С‚ СЌРєСЂР°РЅР° + РєРѕРЅРІРµСЂСЃРёСЏ BGRAв†’BGRв†’HSV
    with mss.mss() as sct:
        mon = _get_monitor_region(scope)
        img = sct.grab(mon)
        bgr = np.array(img)[..., :3]
        hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)

    if is_debug:
        show_image(bgr)
        show_image(hsv)
        time.sleep(0.5)

    # 2) РњР°СЃРєР° РґР»СЏ РіРѕР»СѓР±РѕРіРѕ (РіСЂР°РЅРёС†С‹ Р±РµСЂРёС‚Рµ РёР· РѕС‚Р»Р°РґРєРё HSV)
    lower_blue = np.array([ 90,  30, 150])
    upper_blue = np.array([120, 255, 255])
    mask_blue = cv2.inRange(hsv, lower_blue, upper_blue)
    mask_blue = cv2.GaussianBlur(mask_blue, (5,5), 0)

    # 3) РњРѕСЂС„РѕР»РѕРіРёСЏ РґР»СЏ РѕС‡РёСЃС‚РєРё
    kernel     = cv2.getStructuringElement(cv2.MORPH_RECT, (5,5))
    mask_clean = cv2.morphologyEx(mask_blue, cv2.MORPH_CLOSE, kernel, iterations=2)
    mask_clean = cv2.morphologyEx(mask_clean, cv2.MORPH_OPEN,  kernel, iterations=1)

    if is_debug:
        show_image(mask_blue)
        show_image(mask_clean)
        time.sleep(0.5)

    # 4) РС‰РµРј РІСЃРµ РєРѕРЅС‚СѓСЂС‹ Рё СЃСЂР°Р·Сѓ Р¶Рµ С„РёР»СЊС‚СЂСѓРµРј РїРѕ РїР»РѕС‰Р°РґРё Рё В«РЅР°СЃРєРѕР»СЊРєРѕ РіРѕР»СѓР±РѕР№В» РѕРЅРё РІРЅСѓС‚СЂРё
    cnts, _ = cv2.findContours(mask_clean, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    blue_rects = []
    for cnt in cnts:
        x, y, w, h = cv2.boundingRect(cnt)
        if w < 30 or h < 15:
            continue

        # РїРѕСЃС‡РёС‚Р°РµРј РґРѕР»СЋ Р±РµР»С‹С… РїРёРєСЃРµР»РµР№ РІ РїРµСЂРІРёС‡РЅРѕР№ mask_blue РІРЅСѓС‚СЂРё СЌС‚РѕРіРѕ РїСЂСЏРјРѕСѓРіРѕР»СЊРЅРёРєР°
        patch_mask = mask_blue[y:y+h, x:x+w]
        blue_ratio = patch_mask.sum() / 255 / (w*h)

        # РґРѕРїРѕР»РЅРёС‚РµР»СЊРЅРѕ РїСЂРѕРІРµСЂРёРј, С‡С‚Рѕ РІРЅСѓС‚СЂРё РґРµР№СЃС‚РІРёС‚РµР»СЊРЅРѕ С†РІРµС‚ РЅР°СЃС‹С‰РµРЅ (С‡С‚РѕР±С‹ РЅРµ СЃС…РІР°С‚РёС‚СЊ
        # СЃРІРµС‚Р»Рѕ-СЃРµСЂС‹Р№ Р°СЂС‚РµС„Р°РєС‚)
        patch_hsv = hsv[y:y+h, x:x+w]
        mean_s = float(patch_hsv[...,1].mean())

        # Р±РµСЂРµРј С‚РѕР»СЊРєРѕ С‚Рµ, РіРґРµ С…РѕС‚СЏ Р±С‹ 30% РїРёРєСЃРµР»РµР№ РїРѕРїР°Р»Рѕ РІ РјР°СЃРєСѓ Р СЃСЂРµРґРЅСЏСЏ РЅР°СЃС‹С‰РµРЅРЅРѕСЃС‚СЊ > 20
        if blue_ratio > 0.3 and mean_s > 20:
            blue_rects.append((x, y, w, h))

    if not blue_rects:
        return None

    # 5) РЎРѕСЂС‚РёСЂСѓРµРј В«СЃРІРµСЂС…СѓвЂ“РІР»РµРІРѕВ» Рё РІРѕР·РІСЂР°С‰Р°РµРј РїРµСЂРІСѓСЋ РіРѕР»СѓР±СѓСЋ
    blue_rects.sort(key=lambda r: (r[1], r[0]))
    x0, y0, _, _ = blue_rects[0]
    return (x0 + scope[0], y0 + scope[1])

def reload_page():
    LOGGER.debug("reload page")
    click(92,50)
    pause(2)
    human_move_diff(0, 70)


def get_current_layout() -> int:
    """
    РџРѕР»СѓС‡Р°РµС‚ С‚РµРєСѓС‰РёР№ СЏР·С‹Рє РІРІРѕРґР° Р°РєС‚РёРІРЅРѕРіРѕ РѕРєРЅР°.
    Р’РѕР·РІСЂР°С‰Р°РµС‚ low word layout code (РЅР°РїСЂРёРјРµСЂ, 0x409 РґР»СЏ EN-US).
    """
    hwnd = win32gui.GetForegroundWindow()
    thread_id, _ = win32process.GetWindowThreadProcessId(hwnd)
    layout = win32api.GetKeyboardLayout(thread_id)
    return layout & 0xFFFF


def ensure_layout(target: str = "en", max_attempts: int = 5) -> bool:
    """
    Р“Р°СЂР°РЅС‚РёСЂСѓРµС‚, С‡С‚Рѕ СЂР°СЃРєР»Р°РґРєР° РєР»Р°РІРёР°С‚СѓСЂС‹ СѓСЃС‚Р°РЅРѕРІР»РµРЅР° РІ РЅСѓР¶РЅС‹Р№ СЏР·С‹Рє.
    РџРѕРґРґРµСЂР¶РёРІР°РµС‚ 'en' (Р°РЅРіР»РёР№СЃРєРёР№) Рё 'ru' (СЂСѓСЃСЃРєРёР№).
    Р’РѕР·РІСЂР°С‰Р°РµС‚ True, РµСЃР»Рё СѓРґР°Р»РѕСЃСЊ СѓСЃС‚Р°РЅРѕРІРёС‚СЊ СЂР°СЃРєР»Р°РґРєСѓ, РёРЅР°С‡Рµ False.
    """
    lang_codes = {
        "en": 0x0409,  # English (US)
        "ru": 0x0419,  # Russian
        # РјРѕР¶РЅРѕ РґРѕР±Р°РІРёС‚СЊ РґСЂСѓРіРёРµ
    }

    desired_code = lang_codes.get(target.lower())
    if not desired_code:
        raise ValueError(f"Unsupported language code: {target}")

    for attempt in range(max_attempts):
        current = get_current_layout()
        if current == desired_code:
            return True

        # РџРµСЂРµРєР»СЋС‡Р°РµРј Alt+Shift
        pag.keyDown('altleft')
        pag.press('shift')
        pag.keyUp('altleft')
        time.sleep(0.3)

    return get_current_layout() == desired_code

def grab_monitor(region=None, as_rgb=False):
    """
    region:
      - tuple/list: (x, y, w, h) Р°Р±СЃРѕР»СЋС‚РЅС‹Рµ РєРѕРѕСЂРґРёРЅР°С‚С‹ РІРёСЂС‚СѓР°Р»СЊРЅРѕРіРѕ СЂР°Р±РѕС‡РµРіРѕ СЃС‚РѕР»Р°
      - dict: {"left":x, "top":y, "width":w, "height":h}
      - None: РІРµСЃСЊ РІРёСЂС‚СѓР°Р»СЊРЅС‹Р№ СЌРєСЂР°РЅ (sct.monitors[1])
    as_rgb: True -> RGB (РєР°Рє Сѓ pyautogui), False -> BGR (РґР»СЏ OpenCV)
    returns: np.ndarray (H, W, 3), uint8
    """
    with mss.mss() as sct:
        # Build bbox
        if region is None:
            mon = sct.monitors[1]  # full virtual desktop
            bbox = {"left": mon["left"], "top": mon["top"],
                    "width": mon["width"], "height": mon["height"]}
        elif isinstance(region, (tuple, list)):
            x, y, w, h = map(int, region)
            if w <= 0 or h <= 0:
                raise ValueError("width/height must be > 0")
            bbox = {"left": x, "top": y, "width": w, "height": h}
        elif isinstance(region, dict):
            bbox = {"left": int(region["left"]), "top": int(region["top"]),
                    "width": int(region["width"]), "height": int(region["height"])}
            if bbox["width"] <= 0 or bbox["height"] <= 0:
                raise ValueError("width/height must be > 0")
        else:
            raise ValueError("region must be None, (x,y,w,h), or dict with left/top/width/height")

        # Grab
        shot = sct.grab(bbox)              # BGRA
        img = np.array(shot, dtype=np.uint8)[:, :, :3]  # BGR
        if as_rgb:
            img = img[:, :, ::-1].copy()   # BGR->RGB to match pyautogui
        return img

def capture_and_find_image_boundary_coordinates(
    region,
    search_images: List[ImageLike],
    preprocess: bool = False,
    visualize: bool = False,
    threshold: float = 0.88
) -> List[Tuple[int, int, int, int]]:
    """
    Capture screenshot of `region`, find all matches for ANY template from `search_images`,
    and return rectangles [(x, y, w, h)] in screenshot-local coordinates.
    If `visualize` is True, draw overlays and call showImage() right here.
    """
    x, y, w, h = map(int, region)
    x = x + MON_X
    region = (x, y, w, h)
    try:
        # 0) Р’РёР·СѓР°Р»РёР·Р°С†РёСЏ РѕР±Р»Р°СЃС‚Рё Р·Р°С…РІР°С‚Р° (РѕРїС†РёРѕРЅР°Р»СЊРЅРѕ)
        if visualize:
            show_overlay_win32_hole(
                region=region,
                delay_ms=2000,
                alpha=120,
                border_color=(0, 255, 0),
                border_width=3,
                click_through=False
            )

        # 1) РЎРєСЂРёРЅС€РѕС‚ РѕР±Р»Р°СЃС‚Рё
        screenshot_np = grab_monitor(region)
        if visualize:
            showImage(screenshot_np, 6000)
        LOGGER.debug("[capture_and_find_image_boundary_coordinates] Screenshot captured.")

        # 2) РџСЂРµРґРѕР±СЂР°Р±РѕС‚РєР° (РµСЃР»Рё РЅСѓР¶РЅРѕ)
        processed_image = preprocess_image(screenshot_np) if preprocess else screenshot_np
        if visualize:
            showImage(processed_image, 6000)

        # 3) Р“РѕС‚РѕРІРёРј РёР·РѕР±СЂР°Р¶РµРЅРёРµ Рё С€Р°Р±Р»РѕРЅС‹ (СЃРµСЂС‹Р№ + Р»С‘РіРєРѕРµ СЂР°Р·РјС‹С‚РёРµ)
        img_gray = cv2.cvtColor(processed_image, cv2.COLOR_BGR2GRAY) if processed_image.ndim == 3 else processed_image
        img_gray = cv2.GaussianBlur(img_gray, (3, 3), 0)

        img_h, img_w = img_gray.shape[:2]
        if img_h == 0 or img_w == 0:
            LOGGER.debug("[capture_and_find_image_boundary_coordinates] Empty screenshot dimensions.")
            return []

        # РќРѕСЂРјР°Р»РёР·СѓРµРј СЃРїРёСЃРѕРє С€Р°Р±Р»РѕРЅРѕРІ
        if not isinstance(search_images, (list, tuple)) or len(search_images) == 0:
            raise ValueError("`search_images` must be a non-empty list/tuple of images or paths.")

        candidates = []  # (x, y, w, h, score)

        for tpl in search_images:
            # 4) Р—Р°РіСЂСѓР·РєР°/РЅРѕСЂРјР°Р»РёР·Р°С†РёСЏ С€Р°Р±Р»РѕРЅР°
            if isinstance(tpl, str):
                tpl_bgr = cv2.imread(tpl, cv2.IMREAD_COLOR)
                if tpl_bgr is None:
                    LOGGER.debug(f"[capture_and_find_image_boundary_coordinates] Cannot read template: {tpl}")
                    continue
            else:
                tpl_bgr = tpl

            if tpl_bgr.ndim == 2:
                tpl_bgr = cv2.cvtColor(tpl_bgr, cv2.COLOR_GRAY2BGR)

            tpl_gray = cv2.cvtColor(tpl_bgr, cv2.COLOR_BGR2GRAY) if tpl_bgr.ndim == 3 else tpl_bgr
            tpl_gray = cv2.GaussianBlur(tpl_gray, (3, 3), 0)

            th, tw = tpl_gray.shape[:2]
            if th == 0 or tw == 0:
                continue

            # 4.1) Р•СЃР»Рё С€Р°Р±Р»РѕРЅ Р±РѕР»СЊС€Рµ РєР°СЂС‚РёРЅРєРё вЂ” СѓРјРµРЅСЊС€Р°РµРј
            if th > img_h or tw > img_w:
                scale = min(img_w / tw, img_h / th) * 0.98  # РЅРµРјРЅРѕРіРѕ РјРµРЅСЊС€Рµ, С‡С‚РѕР±С‹ РіР°СЂР°РЅС‚РёСЂРѕРІР°РЅРЅРѕ РїРѕРјРµСЃС‚РёР»СЃСЏ
                new_w = max(1, int(tw * scale))
                new_h = max(1, int(th * scale))
                if new_w < 1 or new_h < 1:
                    LOGGER.debug("[capture_and_find_image_boundary_coordinates] Template too large; skipped after scaling.")
                    continue
                tpl_gray = cv2.resize(tpl_gray, (new_w, new_h), interpolation=cv2.INTER_AREA)
                th, tw = tpl_gray.shape[:2]

            # 5) РЎРѕРїРѕСЃС‚Р°РІР»РµРЅРёРµ С€Р°Р±Р»РѕРЅР°
            res = cv2.matchTemplate(img_gray, tpl_gray, cv2.TM_CCOEFF_NORMED)

            # 6) РџРёРєРё РІС‹С€Рµ РїРѕСЂРѕРіР°
            ys, xs = np.where(res >= threshold)
            if len(ys) == 0:
                continue
            scores = res[ys, xs]

            for x0, y0, sc in zip(xs.tolist(), ys.tolist(), scores.tolist()):
                candidates.append((int(x0), int(y0), int(tw), int(th), float(sc)))

        # 7) РџСЂРѕСЃС‚Р°СЏ NMS, С‡С‚РѕР±С‹ СѓР±СЂР°С‚СЊ РїРµСЂРµСЃРµС‡РµРЅРёСЏ
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
        unique_coords = []
        used_y = []

        for (x, y, w, h) in coordinates:
            # РїСЂРѕРІРµСЂСЏРµРј, РЅРµС‚ Р»Рё СѓР¶Рµ РєРѕРѕСЂРґРёРЅР°С‚С‹ СЃ Р±Р»РёР·РєРёРј y
            if not any(abs(y - uy) <= 100 for uy in used_y):
                unique_coords.append((x, y, w, h))
                used_y.append(y)

        coordinates = unique_coords
        #sort from y
        coordinates_sorted = sorted(coordinates, key=lambda c: c[1], reverse=True)

        LOGGER.debug(f"[capture_and_find_image_boundary_coordinates] Matches: {len(coordinates)} (threshold={threshold}).")
        return coordinates_sorted

    except Exception as e:
        print(f"РћС€РёР±РєР° РІ capture_and_find_image_boundary_coordinates: {e}")
        return []

def main():
    init_tesseract()
    
if __name__ == "__main__":
    main()

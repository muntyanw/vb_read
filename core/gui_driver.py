"""
core/gui_driver.py
~~~~~~~~~~~~~~~~~~

Low-level wrapper around PyAutoGUI + OpenCV (и опционально OCR), 
адаптирован для работы на одном мониторе 1920×1080 в мульти-мониторной конфигурации.

* Определяет целевой монитор по разрешению TARGET_RES.
* Все скриншоты берутся только из этого монитора (с region).
* Координаты кликов и поиска смещаются обратно в глобальные (с учётом x, y целевого монитора).
"""

from __future__ import annotations

import os
import random
import subprocess
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
import mss.tools
import ctypes
from typing import Final, Iterable, Optional, Tuple, List
from difflib import SequenceMatcher
import platform

from project_config import (TEMPLATE_DIR,
                            MONITOR_WIDTH, MONITOR_HEIGHT,
                            MONITOR_INDEX,
                            TESSDATA_PREFIX)

from pytesseract import Output

import win32gui
import win32con
import win32api
import win32process
import logging

import time
from contextlib import contextmanager

pag.FAILSAFE = False
pag.PAUSE = 0.2

logging.basicConfig(
    filename= "log.log" ,
    filemode='w',
    format='%(asctime)s - %(levelname)s - %(message)s',
    level=logging.DEBUG,
    encoding='utf-8'
)

LOGGER = logging.getLogger(__name__) 

pag.FAILSAFE = True  # оставить возможность «движения мыши в угол для экстренной остановки»

# ---------------------------------------------------------------------------
# Constants: ищем монитор с разрешением необходимым для работы
# ---------------------------------------------------------------------------
TARGET_RES: Final[Tuple[int, int]] = (MONITOR_WIDTH, MONITOR_HEIGHT)


with mss.mss() as sct:
    monitors = sct.monitors  # список словарей; monitors[0] — весь виртуальный экран
    # monitors[1] — первый физический экран; monitors[2] — второй и т.д.
    # Мы ожидаем MONITOR_INDEX 1-based
    if 1 <= MONITOR_INDEX < len(monitors):
        mon = monitors[MONITOR_INDEX]
        MON_X, MON_Y, MON_W, MON_H = mon["left"], mon["top"], mon["width"], mon["height"]
        LOGGER.debug("Using MSS monitor #%d: offset (%d,%d), size %dx%d",
                    MONITOR_INDEX, MON_X, MON_Y, MON_W, MON_H)
    else:
        # fallback: если указанный индекс вне диапазона — берем первый монитор
        mon = monitors[1]
        MON_X, MON_Y, MON_W, MON_H = mon["left"], mon["top"], mon["width"], mon["height"]
        LOGGER.warning("monitor_index=%d is invalid, using primary monitor #%d", MONITOR_INDEX, 1)

def pause(amount):
    LOGGER.debug(f"pause {amount} second")
    time.sleep(amount)
    
def _get_monitor_region(scope) -> dict:
    if scope != None:
        left, bottom, right, top = scope
        monitor_region = {
            "top": bottom,
            "left": MON_X + left,
            "width" :right - left,
            "height": top - bottom
        }
    else:
        monitor_region = {
            "top": MON_Y,
            "left": MON_X,
            "width": MON_W,
            "height": MON_H
        }
    return monitor_region
# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------

def arrays_fuzzy_equal(window: List[str], query_words: List[str], threshold: float = 0.7) -> bool:
    """
    Считает два массива «равными», если они одинаковой длины, и для каждой позиции i:
      отношение похожести (SequenceMatcher) на строках w[i] и q[i] ≥ threshold.
    Пустые строки считаются непохожими на непустые (только обе пустые → похожесть = 1.0).

    :param window:      первый список строк
    :param query_words: второй список строк
    :param threshold:   минимальный порог похожести (по умолчанию 0.7)
    :return: True, если все парные строковые элементы похожи ≥ threshold
    """
    if len(window) != len(query_words):
        return False

    count_equal = 0
    
    for w, q in zip(window, query_words):
        # Если обе строки пустые, считаем их идентичными
        if not w and not q:
            count_equal += 1
            continue

        # Если одна пустая, а вторая нет → похожесть 0
        if not w or not q:
            continue

        ratio = SequenceMatcher(None, w, q).ratio()
        if ratio >= threshold:
            count_equal += 1

    return count_equal/len(window) >= threshold

def arrays_fuzzy_equal_as_one_str(window: List[str], query_words: List[str], threshold: float = 0.7) -> bool:
    """
    Преобразует два массива в строки и сравнивает их
    
    :param window:      первый список строк
    :param query_words: второй список строк
    :param threshold:   минимальный порог похожести (по умолчанию 0.7)
    :return: True, если все парные строковые элементы похожи ≥ threshold
    """
    if len(window) != len(query_words):
        return False

    str_window = "".join(window)
    str_query_words = "".join(query_words)

    ratio = SequenceMatcher(None, str_window, str_query_words).ratio()
    
    return ratio >= threshold

def launch_chrome(profile_dir: Path, url: str = "https://e-consul.gov.ua/messages") -> subprocess.Popen:
    """
    The function `launch_chrome` launches Chrome with specified profile directory, window size, and
    position on the screen.
    
    :param profile_dir: The `profile_dir` parameter in the `launch_chrome` function is expected to be a
    `Path` object representing the directory where Chrome will store user profile data. This directory
    will be used as the user data directory for the Chrome instance being launched
    :type profile_dir: Path
    :param url: The `url` parameter in the `launch_chrome` function is a string that represents the URL
    of the website you want to open in the Chrome browser. In the provided code snippet, the default URL
    is set to "https://e-consul.gov.ua/", but you can pass a different URL, defaults to
    https://e-consul.gov.ua/
    :type url: str (optional)
    :return: The function `launch_chrome` returns a `subprocess.Popen` object, which represents a
    process that has been launched to run the Chrome browser with specific parameters such as window
    size, position, and URL.
    """
    """
    Launch Chrome at 1920×1080 on the monitor matching TARGET_RES (или primary).
    """
    chrome_path = _detect_chrome()

    width, height = MON_W, MON_H
    offset_x, offset_y = MON_X, MON_Y

    cmd = [
        str(chrome_path),
        f"--user-data-dir={profile_dir}",
        "--new-window",
        "--start-maximized",
        #f"--window-size={width},{height}",
        #f"--window-position={offset_x},{offset_y}",
        #f"--force-page-scale-factor=1",
        url,
    ]
    LOGGER.debug("Run Chrome at %dx%d+%d+%d: %s", width, height, offset_x, offset_y, cmd)
    return subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

def detect_checkbox_type_from_frame(scope: tuple[int, int, int, int] = None,
                is_debug: bool = False) -> str:
    """
        frame_bgr: кадр экрана (numpy.ndarray в формате BGR)
        empty_template_path: путь до шаблона пустого квадратика
        checked_template_path: путь до шаблона квадратика с галочкой
        threshold: минимальное значение совпадения (0.0–1.0)
        
        Вернёт:
        - "empty", если на экране найден пустой квадратик
        - "checked", если найден квадратик с галочкой
        - "none", если ни один из шаблонов не нашёлся (маximальный коэффициент < threshold)
    """
    frame_bgr = screen(scope)
    
    if is_debug:
        show_image(frame_bgr)
        time.sleep(0.5)
    

    # Загружаем оба шаблона сразу в градациях серого
    templ_empty = cv2.imread(str(TEMPLATE_DIR / CHECK_EMPTY_TEMPLATE_PATH))
    
    templ_checked = cv2.imread(str(TEMPLATE_DIR / CHECK_CHECKED_TEMPLATE_PATH))
    
    if templ_empty is None:
        raise FileNotFoundError(f"Не найден шаблон «пустой» по пути {TEMPLATE_DIR / CHECK_EMPTY_TEMPLATE_PATH}")
    if templ_checked is None:
        raise FileNotFoundError(f"Не найден шаблон «с галочкой» по пути {TEMPLATE_DIR / CHECK_CHECKED_TEMPLATE_PATH}")

    if is_debug:
        show_image(templ_empty)
        time.sleep(0.5)
        show_image(templ_checked)
        time.sleep(0.5)
    
    # 1) Поиск пустого квадратика
    res_empty = cv2.matchTemplate(frame_bgr, templ_empty, cv2.TM_CCOEFF_NORMED)
    _, max_val_empty, _, _ = cv2.minMaxLoc(res_empty)

    # 2) Поиск квадратика с галочкой
    res_checked = cv2.matchTemplate(frame_bgr, templ_checked, cv2.TM_CCOEFF_NORMED)
    _, max_val_checked, _, _ = cv2.minMaxLoc(res_checked)

    # Если ни один из шаблонов не превысил threshold → «ничего не найдено»
    LOGGER.debug(f"max_val_empty: {max_val_empty}, max_val_checked: {max_val_checked}")

    # Если оба выше порога, смотрим, у кого коэффициент больший
    if max_val_checked >= max_val_empty:
        return "checked"
    else:
        return "empty"

def detect_image_from_frame(image_names: list[str], scope: tuple[int, int, int, int] = None,
                is_debug: bool = False,
                threshold: float = 0.8) -> str:
   
    frame_bgr = screen(scope)
    
    # Конвертируем скрин в оттенки серого
    gray_frame = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)

    max_weight = -10000
    check_image = ""
    
    for image_name in image_names:
        templ = cv2.imread(TEMPLATE_DIR / image_name, cv2.IMREAD_GRAYSCALE)
        if templ is None:
            raise FileNotFoundError(f"Не найден шаблон «пустой» по пути {TEMPLATE_DIR / image_name}")
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
    Найти PNG-шаблон на экране.
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
            abs_x = MON_X + pos[0]
            abs_y = MON_Y + pos[1]
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
    Найти PNG-шаблон на экране (в пределах целевого монитора) и кликнуть его центр.
    Возвращает True, если кликнули, False если не найдено за timeout секунд.
    """
    LOGGER.debug(f"Start find image {name}")
    start = time.perf_counter()
    result_find = find_image(name, timeout, confidence, scope, is_debug, multiscale)
    end = time.perf_counter()
    tm = end - start
    print(f"time find image (multiscale={multiscale}) = {tm}")

    if result_find:
        LOGGER.debug(f"Foud image {name}")
        abs_x, abs_y = result_find
        if abs_x is not None and abs_y is not None:
            human_move_and_click(abs_x + plus_x, abs_y + plus_y, count_click=count_click)
            return True
        

    return False

def type_text(text: str, interval: Tuple[float, float] = (0.05, 0.12)) -> None:
    """
    Печатать строку с небольшим случайным интервалом между символами.
    """
    for ch in text:
        pag.typewrite(ch)
        time.sleep(random.uniform(*interval))

def take_screenshot() -> Path:
    """
    Сделать PNG скрин целевого MONITOR_INDEX с помощью MSS и вернуть Path.
    """
    import tempfile, datetime as dt

    ts = dt.datetime.utcnow().isoformat().replace(":", "-")
    output_path = Path(tempfile.gettempdir()) / f"scr_{ts}.png"

    with mss.mss() as sct:
        # Снимаем именно ту область, что описывает монитора:
        monitor_region = {"top": MON_Y, "left": MON_X, "width": MON_W, "height": MON_H}
        img_data = sct.grab(monitor_region)
        # Записываем в PNG (MSS возвращает raw-битмап):
        mss.tools.to_png(img_data.rgb, img_data.size, output=str(output_path))

    return output_path

def show_image(img) -> None:
    # Показать изображение через matplotlib
    plt.figure(figsize=(8, 5))
    plt.imshow(img)
    plt.axis('off')
    plt.title("Tesseract Input: Full-Screen Screenshot")
    plt.show()
# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------
def _detect_chrome() -> Path:
    """
    Best-effort поиск chrome.exe / google-chrome в common locations.
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
    w_l: float = 0.55,          # вес яркости (L*)
    w_c: float = 0.45,          # совокупный вес цвета (a*+b*)
    hist_bins_h: int = 30,
    hist_bins_s: int = 32,
    color_reweight: float = 0.25,  # сила донастройки по цвету (0..1)
) -> Optional[Tuple[int, int]]:
    """
    Multi-scale template matching with color-aware scoring.
    Возвращает абсолютные (cx, cy) или None.
    """

    def _deltaEab_mean(bgrA, bgrB) -> float:
        A = cv2.cvtColor(bgrA, cv2.COLOR_BGR2LAB).astype("float32")
        B = cv2.cvtColor(bgrB, cv2.COLOR_BGR2LAB).astype("float32")
        diff = A - B
        # Простой ΔE*ab (CIE76) — норм для ранжирования
        de = np.sqrt(np.sum(diff ** 2, axis=2))
        return float(de.mean())

    def _hsv_hist_corr(bgrA, bgrB) -> float:
        hsvA = cv2.cvtColor(bgrA, cv2.COLOR_BGR2HSV)
        hsvB = cv2.cvtColor(bgrB, cv2.COLOR_BGR2HSV)
        histA = cv2.calcHist([hsvA], [0, 1], None, [hist_bins_h, hist_bins_s], [0, 180, 0, 256])
        histB = cv2.calcHist([hsvB], [0, 1], None, [hist_bins_h, hist_bins_s], [0, 180, 0, 256])
        cv2.normalize(histA, histA)
        cv2.normalize(histB, histB)
        # CORREL ∈ [-1..1] -> приведём к [0..1]
        corr = cv2.compareHist(histA, histB, cv2.HISTCMP_CORREL)
        return float(max(0.0, min(1.0, 0.5 * (corr + 1.0))))

    # 1) Снимок экрана
    scr_bgr = screen(scope, process_for_read=False, is_debug=is_debug)
    img_h, img_w = scr_bgr.shape[:2]

    # 2) Шаблон (+маска при наличии)
    tpl_bgr, mask = _read_template_with_optional_mask(template_path)
    tw0, th0 = tpl_bgr.shape[1], tpl_bgr.shape[0]

    # 3) Диапазон масштабов
    scales = np.linspace(0.75, 1.25, 21)

    best = None  # будет хранить (final_score, raw_tm, x, y, w, h, scale)

    # Предрасчёт яркостного и цветовых каналов для экрана
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
            # Маскированное сопоставление по цвету (нормированная корреляция)
            res = cv2.matchTemplate(scr_bgr, tpl_s, cv2.TM_CCORR_NORMED, mask=mask_s)
            _, raw_tm, _, max_loc = cv2.minMaxLoc(res)
            x, y = max_loc
        else:
            # Цвето-чувствительный скоринг: L*, a*, b* отдельно — затем смешиваем
            tpl_lab = cv2.cvtColor(tpl_s, cv2.COLOR_BGR2LAB)
            tpl_L, tpl_a, tpl_b = cv2.split(tpl_lab)

            # Небольшое сглаживание только на L* (текстурный шум)
            scr_L_blur = cv2.GaussianBlur(scr_L, (3, 3), 0)
            tpl_L_blur = cv2.GaussianBlur(tpl_L, (3, 3), 0)

            # Карты совпадения ([-1..1] для CCOEFF_NORMED)
            res_L = cv2.matchTemplate(scr_L_blur, tpl_L_blur, cv2.TM_CCOEFF_NORMED)
            res_a = cv2.matchTemplate(scr_a, tpl_a, cv2.TM_CCOEFF_NORMED)
            res_b = cv2.matchTemplate(scr_b, tpl_b, cv2.TM_CCOEFF_NORMED)

            # Смешивание с весами
            res = w_l * res_L + (w_c * 0.5) * (res_a + res_b)

            _, raw_tm, _, max_loc = cv2.minMaxLoc(res)
            x, y = max_loc

        # 4) Re-rank по цвету на найденном пике: ΔE*ab и HSV-гист корреляция
        roi = scr_bgr[y:y+new_h, x:x+new_w]
        if roi.shape[0] == new_h and roi.shape[1] == new_w:
            # ΔE ~ [0..~100] -> преобразуем в [0..1] через экспоненту
            dE = _deltaEab_mean(roi, tpl_s)  # меньше — лучше
            dE_term = np.exp(-dE / 12.0)     # ≈0.44 при dE=10; ≈0.19 при dE=20

            # Коррел. гистограмм HSV ∈ [0..1]
            hcorr = _hsv_hist_corr(roi, tpl_s)

            # Цветовой бонус [0..1]
            color_bonus = 0.6 * dE_term + 0.4 * hcorr

            # Итоговый скор (подправляем сырой TM в сторону цветового совпадения)
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
    Передать абсолютные глобальные координаты (x, y) и выполнить плавное движение
    “по-человечески”. Используется Bezier-кривая + небольшие случайные паузы.
    """
    LOGGER.debug(f"Start human move to x: {x}, y: {y}")
    
    x = x + MON_X
    
    cx, cy = pag.position()  # текущая абсолютная позиция мыши

    # Точки для кривой Безье: старт → 2 случайные опоры → цель
    anchors = [
        (cx, cy),
        _rand_near(cx, cy, 100),
        _rand_near(x, y, 100),
        (x, y),
    ]
    steps = 3
    for t in np.linspace(0, 1, steps):
        bx, by = _bezier_point(anchors, t)
        pag.moveTo(bx, by, duration=0)
        time.sleep(0.0001)

    pag.moveTo(x, y, duration=random.uniform(*duration))

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
        pass  # Класс уже зарегистрирован

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

    # Ждём duration секунд, потом закрываем окно
    time.sleep(duration)
    win32gui.DestroyWindow(hwnd)
    
def human_move_and_click(x: int, y: int, 
                         duration: Tuple[float, float] = (0.2, 0.3),
                         count_click: int = 1) -> None:
    """
    Передать абсолютные глобальные координаты (x, y) и выполнить плавное движение
    “по-человечески” + клик. Используется Bezier-кривая + небольшие случайные паузы.
    """
    _human_move(x, y, duration)
    
    for i in range(0, count_click, 1):
        LOGGER.debug(f"click x: {x} y: {y}")
        draw_click_circle(x,y)
        pag.click()
        
def human_move_and_right_click(x: int, y: int, duration: Tuple[float, float] = (0.4, 0.9),
                         count_click: int = 1) -> None:
    """
    Передать абсолютные глобальные координаты (x, y) и выполнить плавное движение
    “по-человечески” + клик. Используется Bezier-кривая + небольшие случайные паузы.
    """
    _human_move(x, y, duration)
    
    for i in range(0, count_click, 1):
        LOGGER.debug(f"click x: {x} y: {y}")
        draw_click_circle(x,y,duration=0.4)
        pag.rightClick()
        
def human_move_and_click_diff(x: int, y: int, duration: Tuple[float, float] = (0.4, 0.9),
                         count_click: int = 1) -> None:
    """
    Передать абсолютные глобальные координаты (x, y) и выполнить плавное движение
    “по-человечески” + клик. Используется Bezier-кривая + небольшие случайные паузы.
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
    else:
        x = MON_X + x
        
    human_move_and_click(x, y) 
    
def right_click(x: int, y: int, duration: Tuple[float, float] = (0.4, 0.9)):
    x = MON_X + x
    human_move_and_right_click(x, y) 
    
def click_diff(x: int, y: int, duration: Tuple[float, float] = (0.4, 0.9)):
    x = MON_X + x
    human_move_and_click_diff(x, y)
    
def _bezier_point(pts: list[Tuple[int, int]], t: float) -> Tuple[int, int]:
    """
    Quadratic/ cubic bezier evaluation (De Casteljau) – generic n-degree.
    Вход: pts — список точек (x, y), t от 0.0 до 1.0.
    Выход: координаты точки на кривой Безье.
    """
    pts_arr = np.array(pts, dtype=float)
    while len(pts_arr) > 1:
        pts_arr = (1 - t) * pts_arr[:-1] + t * pts_arr[1:]
    return int(pts_arr[0][0]), int(pts_arr[0][1])

def _rand_near(x: int, y: int, radius: int = 80) -> Tuple[int, int]:
    """
    Вернёт точку в случайном направлении на расстоянии [radius*0.3 .. radius]
    от (x, y). Используется для более «человеческого» движения мыши.
    """
    ang = random.uniform(0, 2 * np.pi)
    r = random.uniform(radius * 0.3, radius)
    return int(x + r * np.cos(ang)), int(y + r * np.sin(ang))

def draw_monitor_region_on_screen(color: tuple[int,int,int] = (0, 0, 255), thickness: int = 4) -> None:
    """
    Нарисовать на рабочем столе (на самой поверхности экрана) полупрозрачный (через XOR)
    или сплошной (через GDI Rectangle) контур области MON_X, MON_Y, MON_W, MON_H.

    Параметры:
    ---------
    color : BGR-цвет рамки, например (0, 0, 255) для красного (как OpenCV).
    thickness : толщина линии рамки в пикселях.

    При запуске этой функции вы увидите чёткую рамку на экране. Она отрисуется поверх всего,
    но исчезнет при следующем обновлении окна или при следующем вызове (в зависимости от режима).
    """
    # 1) Сначала вычислим координаты нужного монитора через MSS:
    with mss.mss() as sct:
        monitors = sct.monitors
        if 1 <= MONITOR_INDEX < len(monitors):
            mon = monitors[MONITOR_INDEX]
        else:
            mon = monitors[1]  # если указан неверный индекс, взять первый
        MON_X, MON_Y, MON_W, MON_H = mon["left"], mon["top"], mon["width"], mon["height"]

    # 2) Получаем контекст устройства (DC) для всего экрана (hwnd=0 → весь экран)
    hdc = ctypes.windll.user32.GetDC(0)

    # 3) Создаём перо нужного цвета и толщины
    #    В GDI цвет задаётся в формате 0x00BBGGRR, поэтому перекладываем:
    b, g, r = color
    gdi_color = (r << 16) | (g << 8) | b

    PS_SOLID = 0          # сплошная линия
    pen = ctypes.windll.gdi32.CreatePen(PS_SOLID, thickness, gdi_color)
    old_pen = ctypes.windll.gdi32.SelectObject(hdc, pen)

    # 4) Получаем «пустую кисть» (NULL_BRUSH), чтобы внутри не заливать
    NULL_BRUSH = 5  # индекс в GDI для «null brush»
    brush = ctypes.windll.gdi32.GetStockObject(NULL_BRUSH)
    old_brush = ctypes.windll.gdi32.SelectObject(hdc, brush)

    # 5) Рисуем прямоугольник. Параметры: hdc, left, top, right, bottom
    left   = MON_X
    top    = MON_Y
    right  = MON_X + MON_W
    bottom = MON_Y + MON_H

    # Rectangle рисует рамку между (left, top) и (right, bottom)
    ctypes.windll.gdi32.Rectangle(hdc, left, top, right, bottom)

    # 6) Возвращаем предыдущее перо/кисть и удаляем созданные объекты
    ctypes.windll.gdi32.SelectObject(hdc, old_pen)
    ctypes.windll.gdi32.SelectObject(hdc, old_brush)
    ctypes.windll.gdi32.DeleteObject(pen)

    # 7) Освобождаем DC
    ctypes.windll.user32.ReleaseDC(0, hdc)


def replace_similar_chars(word: str) -> str:
    char_map = {
        'e': 'е',  # англ e → укр е
        'E': 'Е',  # англ E → укр Е
        'i': 'і',  # англ i → укр і (по необходимости)
        'I': 'І',  # англ I → укр І
        'a': 'а',  # англ a → укр а
        'A': 'А',  # англ A → укр А
        'o': 'о',  # англ o → укр о
        'O': 'О',  # англ O → укр О
        'c': 'с',  # англ c → укр с
        'C': 'С',  # англ C → укр С
        'p': 'р',  # англ p → укр р
        'P': 'Р',  # англ P → укр Р
        'x': 'х',  # англ x → укр х
        'X': 'Х',  # англ X → укр Х
    }
    return ''.join(char_map.get(c, c) for c in word)

def read_text(
    lang: str,
    scope: tuple[int, int, int, int] = None,
    is_debug: bool = False
) -> bool:
    """
    OCR-based read text
    
    """
    
    scr_bgr = screen(scope, is_debug = is_debug)
    
    os.environ['TESSDATA_PREFIX'] = os.path.normpath(TESSDATA_PREFIX)
    pytesseract.pytesseract.tesseract_cmd = r"C:/Program Files/Tesseract-OCR/tesseract.exe"

    data = pytesseract.image_to_data(
        scr_bgr, lang=lang, output_type=pytesseract.Output.DICT
    )

    texts = [t.strip().lower() for t in data["text"]]
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
    scope: tuple[int, int, int, int] = None,
    plus_y: int = 0,
    is_debug: bool = False,
    threshold: float = 0.7,
    occurrence: int = 1,
    duration: Tuple[float, float] = (0.2, 0.3),
) -> bool:
    """
    OCR-based search: найти текст `query` на экране (в пределах MON_X..MON_W, MON_Y..MON_H)
    и кликнуть его центр.
    Возвращает True, если удалось найти и кликнуть, иначе False по истечении timeout.

    Параметры:
    -----------
    query : str
        Подстрока (без учёта регистра), которую ищем среди распознанных слов.
    timeout : float
        Максимальное время (в секундах) на попытки поиска.
    lang : str
        Язык Tesseract (например, "eng", "rus", "ukr").
    conf_threshold : float
        Минимальный порог доверия (0.0–1.0) для распознанных слов.
    padding : tuple[int, int, int, int], optional
        Смещение (left, bottom, right, top) для сужения области скриншота.
    """
    LOGGER.debug(f"find and click {query},scope: {scope}")
    
    pos = None
    
    if isinstance(query, str):
        pos = find_text(query=query, lang=lang, 
                        count=count_attempt_find, 
                        pause_attempt = pause_attempt, 
                        scope=scope, plus_y = plus_y,
                        threshold = threshold, 
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
        print(f"time find_text_any = {tm}")
    else:
        print("click_text error value query")
    
    if pos:
        abs_x, abs_y = pos
        human_move_and_click(abs_x, abs_y + plus_y, duration)
        return pos

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
    occurrence: int = 1,  # номер совпадения
) -> tuple[int, int] | None:
    """
    OCR-based search: найти текст `query` на экране (в пределах MON_X..MON_W, MON_Y..MON_H).

    Возвращает x, y центра N-го совпадения, иначе None по истечении count попыток.

    Параметры:
    -----------
    query : str
        Подстрока (без учёта регистра), которую ищем среди распознанных слов.
    lang : str
        Язык Tesseract (например, "eng", "rus", "ukr").
    count : int
        Кол-во попыток поиска с паузой между ними.
    pause_attempt : int
        Пауза (сек) между попытками.
    scope : (x, y, w, h)
        Область экрана для OCR. Если None — весь экран.
    plus_y : int
        Доп. смещение вниз по Y.
    is_debug : bool
        Включить отладку.
    occurrence : int
        Номер совпадения (1 = первое, 2 = второе и т.д.)
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

        texts = [t.strip().lower() for t in data["text"]]
        ocr_texts = [w for w in texts if w != ""]
        LOGGER.debug(f"OCR texts: {ocr_texts}")

        if len(ocr_texts) == 0 and attempts == count:
            return None

        n_boxes = len(texts)
        found_count = 0  # счётчик совпадений

        for i in range(n_boxes - n_words + 1):
            window = texts[i:i + n_words]
            window = [replace_similar_chars(w) for w in window]

            if arrays_fuzzy_equal_as_one_str(window, query_words):
                found_count += 1

                if found_count == occurrence:
                    x_left = min(int(data["left"][j]) for j in range(i, i + n_words))
                    y_top = min(int(data["top"][j]) for j in range(i, i + n_words))
                    x_right = max(int(data["left"][j]) + int(data["width"][j]) for j in range(i, i + n_words))
                    y_bottom = max(int(data["top"][j]) + int(data["height"][j]) for j in range(i, i + n_words))

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

    # 1) базовые проверки
    if not os.path.isfile(tess_exe):
        raise FileNotFoundError(f"tesseract.exe not found: {tess_exe}")
    if not os.path.isdir(tessdata):
        raise FileNotFoundError(f"tessdata folder not found: {tessdata}")

    # 2) сбросить кривую настройку, если была
    os.environ.pop("TESSDATA_PREFIX", None)
    # ВАЖНО: указывать ИМЕННО корень, НЕ tessdata
    os.environ["TESSDATA_PREFIX"] = tess_root

    # 3) путь к бинарнику
    pytesseract.pytesseract.tesseract_cmd = tess_exe

    # 4) проверить наличие языков
    missing = [lng for lng in lang_check
               if not os.path.isfile(os.path.join(tessdata, f"{lng}.traineddata"))]
    if missing:
        raise FileNotFoundError(f"Missing traineddata: {', '.join(missing)} in {tessdata}")

    # 5) быстрая самопроверка (по желанию)
    try:
        _ = pytesseract.get_tesseract_version()
    except Exception as e:
        raise RuntimeError(f"Tesseract not initialized: {e}")

def find_text_any(
    queries: Iterable[str],
    lang: str,
    count: int = 1,
    pause_attempt_sec: int = 0.5,
    scope: tuple[int, int, int, int] | None = None,
    is_debug: bool = False,
    occurrence: int = 1,
    threshold: float = 0.7,
    font_scale: float = 0.7,
    font_thickness: int = 2,
) -> Tuple[List[Tuple[int, int]], Optional[Tuple[int, int]]]:
    """
    Ищет любой из текстов `queries` на экране, визуализирует все нахождения
    и возвращает:
      - список абсолютных координат центров всех совпадений [(abs_x, abs_y), ...]
      - координаты N-го по порядку совпадения (occurrence) или None

    Правила:
      - Порядок нумерации соответствует порядку обнаружения (сканирование слева направо по OCR-окнам).
      - На картинке: все совпадения жёлтые с номером; occurrence — красная рамка.
      - Если на последней попытке OCR не дал ни одного слова — возвращается ([], None).

    Важно: используется screen(process_for_read=True) для OCR.
    """
    
    if occurrence < 1:
        occurrence = 1

    queries_words = [q.lower().split() for q in queries]
    attempts = 0

    while attempts < count:
        attempts += 1

        # 1) Скрин области (OCR-предобработка включена)
        scr_bgr = screen(scope=scope, process_for_read=True, is_debug=is_debug)
        vis_bgr = scr_bgr.copy()

        # 2) OCR
        data = pytesseract.image_to_data(scr_bgr, lang=lang, output_type=Output.DICT)

        # 3) Сбор слов
        texts: List[str] = []
        n_boxes = len(data["text"])
        for i in range(n_boxes):
            txt = data["text"][i].strip().lower()
            texts.append(txt)

        ocr_texts = [w for w in texts if w != ""]
        if len(ocr_texts) == 0 and attempts == count:
            # На последней попытке OCR пуст — возвращаем пустой список
            return None

        # 4) Поиск совпадений
        matches: List[Tuple[int, int]] = []  # абсолютные центры всех совпадений
        boxes: List[Tuple[int, int, int, int]] = []  # x1,y1,x2,y2 для визуализации
        labels: List[str] = []  # исходный текст окна для подписи
        nth_abs: Optional[Tuple[int, int]] = None
        nth_idx: Optional[int] = None  # индекс совпадения (1-based) для подсветки

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
                    # Собираем общий bbox по словам i..i+n_words-1
                    x_left = min(int(data["left"][j]) for j in range(i, i + n_words))
                    y_top = min(int(data["top"][j]) for j in range(i, i + n_words))
                    x_right = max(int(data["left"][j]) + int(data["width"][j]) for j in range(i, i + n_words))
                    y_bottom = max(int(data["top"][j]) + int(data["height"][j]) for j in range(i, i + n_words))

                    center_x_rel = (x_left + x_right) // 2
                    center_y_rel = (y_top + y_bottom) // 2

                    abs_x = MON_X + scope_left + center_x_rel
                    abs_y = MON_Y + scope_top + center_y_rel

                    found_count += 1
                    matches.append((abs_x, abs_y))
                    boxes.append((x_left, y_top, x_right, y_bottom))
                    labels.append(" ".join(window).strip())

                    if found_count == occurrence:
                        nth_abs = (abs_x, abs_y)
                        nth_idx = found_count  # 1-based

        # 5) Визуализация — нумерация всех совпадений + выделение occurrence
        if is_debug and boxes:
            for idx, ((x1, y1, x2, y2), label) in enumerate(zip(boxes, labels), start=1):
                # Все совпадения — жёлтые
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
                # Можно дописать текст рядом при необходимости:
                # cv2.putText(vis_bgr, label, (x1 + 18, max(0, y1 - 6)), cv2.FONT_HERSHEY_SIMPLEX,
                #             font_scale, (0, 255, 255), max(1, font_thickness - 1), cv2.LINE_AA)

            # Подсветка occurrence — красным и толще
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

        # 6) Возвращаем массив и N-й элемент (если есть) — сразу после первой результативной попытки
        if matches or attempts == count:
            # Если ничего не найдено, вернём пустой массив и None
            return nth_abs

        # Иначе ждём и повторяем
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
    # Отпускаем Ctrl
    pag.keyUp('ctrl')
    
    time.sleep(1) 
    
def remove_green_background(src_bgr: np.ndarray) -> np.ndarray:
    """
    Превращает зелёные блоки в чисто-белый фон, оставляя текст (и всё остальное) нетронутым.
    Возвращает BGR-изображение, где «зелёное» стало (255,255,255).
    """
    # 1. Переводим в пространство HSV, чтобы легко отфильтровать зелёный
    hsv = cv2.cvtColor(src_bgr, cv2.COLOR_BGR2HSV)

    # 2. Задаём диапазон «зелёного»
    #    Нижний и верхний порог границ H, S, V — можно подкорректировать под ваш оттенок
    lower_green = np.array([40,  40,  40])   # например: H≈60°, но OpenCV: H от 0 до 179
    upper_green = np.array([80, 255, 255])

    # 3. Делаем маску: где пиксели «зеленые» → 255, остальное → 0
    mask_green = cv2.inRange(hsv, lower_green, upper_green)

    # 4. Invert mask: где НЕ зелёное (текст, остальные элементы) → 255, где зелёное → 0
    mask_not_green = cv2.bitwise_not(mask_green)

    # 5. Создаём «фон» полностью белого цвета того же размера
    white_bg = np.full_like(src_bgr, fill_value=255)

    # 6. Накладываем: на исходном изображении всё, что НЕ зелёное, оставляем (AND с mask_not_green),
    #    а в местах «зелёного» будем брать белый фон (AND с mask_green и белый)
    fg = cv2.bitwise_and(src_bgr, src_bgr, mask=mask_not_green)
    bg = cv2.bitwise_and(white_bg, white_bg, mask=mask_green)

    # 7. Склеиваем: получается картинка, где «зелёное» заменено на белое
    result = cv2.add(fg, bg)
    return result

def sharpen_filter(src_bgr: np.ndarray) -> np.ndarray:
    """
    Применяет к BGR-изображению простой фильтр резкости.
    Возвращает «резче» BGR-изображение.
    """
    # Определяем kernel
    kernel = np.array([
        [ 0, -1,  0],
        [-1,  5, -1],
        [ 0, -1,  0]
    ], dtype=np.float32)

    # Применяем фильтр свёртки
    sharpened = cv2.filter2D(src_bgr, ddepth=-1, kernel=kernel)
    return sharpened

def unsharp_mask(src_bgr: np.ndarray, 
                 blur_ksize: tuple[int, int] = (9, 9), 
                 sigma: float = 10.0, 
                 amount: float = 1.5, 
                 threshold: int = 0) -> np.ndarray:
    """
    Параметры:
    - blur_ksize: размер ядра для GaussianBlur (должен быть нечётным, напр. (9,9)).
    - sigma: отклонение по Гауссу (чем больше, тем сильнее сглаживание).
    - amount: во сколько раз усиливается «маска резкости».
    - threshold: минимальная разница яркости, при которой происходит усиление; 0 — без порога.
    """
    # 1) Сглаживаем
    blurred = cv2.GaussianBlur(src_bgr, blur_ksize, sigma)

    # 2) Вычисляем «маску»: оригинал − размытие
    mask = cv2.subtract(src_bgr, blurred)

    # 3) Усиливаем маску и складываем с оригиналом
    sharpened = cv2.addWeighted(src_bgr, 1.0, mask, amount, 0)

    if threshold > 0:
        # Дополнительно: пороговое усиление (Optional)
        # Разница между оригиналом и размытым (по каналам)
        low_contrast_mask = np.absolute(src_bgr - blurred) < threshold
        # В тех местах, где контраст низкий, оставляем оригинал
        np.copyto(sharpened, src_bgr, where=low_contrast_mask)

    return sharpened

def preprocess_for_ocr(src_bgr: np.ndarray) -> np.ndarray:
    """
    1) Удаляет зелёный фон (вызывая remove_green_background)
    2) Конвертирует в серый + CLAHE (локальное выравнивание гистограммы)
    3) Адаптивную бинаризацию (чёрно-белое)
    """
    # 1) Убираем зелёный фон
    no_green = unsharp_mask(remove_green_background(src_bgr))

    # 2) В оттенки серого
    gray = cv2.cvtColor(no_green, cv2.COLOR_BGR2GRAY)

    # 3) CLAHE для повышения контраста
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    equalized = clahe.apply(gray)

    # 4) Адаптивная бинаризация (локальная) — чаще всего лучше, чем просто Otsu
    bw = cv2.adaptiveThreshold(
        equalized,
        255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY,
        blockSize=11,  # нечётный размер; можно варьировать (11, 15, 21)
        C=2             # константа, вычитаемая из среднего
    )
    return bw

def find_first_free_slot_in_day_week(scope: tuple[int,int,int,int],
                                     is_debug: bool = False
                                    ) -> tuple[int,int] | None:

    # 1) Захват экрана + конверсия BGRA→BGR→HSV
    with mss.mss() as sct:
        mon = _get_monitor_region(scope)
        img = sct.grab(mon)
        bgr = np.array(img)[..., :3]
        hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)

    if is_debug:
        show_image(bgr)
        show_image(hsv)
        time.sleep(0.5)

    # 2) Маска для голубого (границы берите из отладки HSV)
    lower_blue = np.array([ 90,  30, 150])
    upper_blue = np.array([120, 255, 255])
    mask_blue = cv2.inRange(hsv, lower_blue, upper_blue)
    mask_blue = cv2.GaussianBlur(mask_blue, (5,5), 0)

    # 3) Морфология для очистки
    kernel     = cv2.getStructuringElement(cv2.MORPH_RECT, (5,5))
    mask_clean = cv2.morphologyEx(mask_blue, cv2.MORPH_CLOSE, kernel, iterations=2)
    mask_clean = cv2.morphologyEx(mask_clean, cv2.MORPH_OPEN,  kernel, iterations=1)

    if is_debug:
        show_image(mask_blue)
        show_image(mask_clean)
        time.sleep(0.5)

    # 4) Ищем все контуры и сразу же фильтруем по площади и «насколько голубой» они внутри
    cnts, _ = cv2.findContours(mask_clean, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    blue_rects = []
    for cnt in cnts:
        x, y, w, h = cv2.boundingRect(cnt)
        if w < 30 or h < 15:
            continue

        # посчитаем долю белых пикселей в первичной mask_blue внутри этого прямоугольника
        patch_mask = mask_blue[y:y+h, x:x+w]
        blue_ratio = patch_mask.sum() / 255 / (w*h)

        # дополнительно проверим, что внутри действительно цвет насыщен (чтобы не схватить
        # светло-серый артефакт)
        patch_hsv = hsv[y:y+h, x:x+w]
        mean_s = float(patch_hsv[...,1].mean())

        # берем только те, где хотя бы 30% пикселей попало в маску И средняя насыщенность > 20
        if blue_ratio > 0.3 and mean_s > 20:
            blue_rects.append((x, y, w, h))

    if not blue_rects:
        return None

    # 5) Сортируем «сверху–влево» и возвращаем первую голубую
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
    Получает текущий язык ввода активного окна.
    Возвращает low word layout code (например, 0x409 для EN-US).
    """
    hwnd = win32gui.GetForegroundWindow()
    thread_id, _ = win32process.GetWindowThreadProcessId(hwnd)
    layout = win32api.GetKeyboardLayout(thread_id)
    return layout & 0xFFFF


def ensure_layout(target: str = "en", max_attempts: int = 5) -> bool:
    """
    Гарантирует, что раскладка клавиатуры установлена в нужный язык.
    Поддерживает 'en' (английский) и 'ru' (русский).
    Возвращает True, если удалось установить раскладку, иначе False.
    """
    lang_codes = {
        "en": 0x0409,  # English (US)
        "ru": 0x0419,  # Russian
        # можно добавить другие
    }

    desired_code = lang_codes.get(target.lower())
    if not desired_code:
        raise ValueError(f"Unsupported language code: {target}")

    for attempt in range(max_attempts):
        current = get_current_layout()
        if current == desired_code:
            return True

        # Переключаем Alt+Shift
        pag.keyDown('altleft')
        pag.press('shift')
        pag.keyUp('altleft')
        time.sleep(0.3)

    return get_current_layout() == desired_code

def main():
    init_tesseract()
    
if __name__ == "__main__":
    main()

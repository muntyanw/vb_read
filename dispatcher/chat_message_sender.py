from datetime import datetime
from pathlib import Path

import cv2
import pyautogui as pag
import pyperclip
from pywinauto import keyboard as win_keyboard

from core import gui_driver as gd
from log import log_and_print
from utils import take_screenshot, read_setting


def _normalize_input_text(text: str | None) -> str:
    value = str(text or '')
    value = value.replace('\r\n', '\n').replace('\r', '\n')
    return value.strip()


def _read_input_text() -> str:
    old_clip = None
    try:
        old_clip = pyperclip.paste()
    except Exception:
        old_clip = None

    marker = '__chat_input_probe__'
    try:
        pyperclip.copy(marker)
        pag.hotkey('ctrl', 'a')
        gd.pause(0.08)
        pag.hotkey('ctrl', 'c')
        gd.pause(0.12)
        current = pyperclip.paste() or ''
        if current == marker:
            return ''
        return str(current)
    except Exception:
        return ''
    finally:
        if old_clip is not None:
            try:
                pyperclip.copy(old_clip)
            except Exception:
                pass


def _focus_input(window, input_xy: tuple[int, int]) -> None:
    input_x, input_y = int(input_xy[0]), int(input_xy[1])
    window.set_focus()
    gd.click(input_x, input_y)
    gd.pause(0.12)
    gd.click(input_x, input_y)
    gd.pause(0.12)


def _input_debug_region(input_xy: tuple[int, int]) -> tuple[int, int, int, int]:
    input_x, input_y = int(input_xy[0]), int(input_xy[1])
    left = max(0, input_x - 260)
    top = max(0, input_y - 130)
    width = 620
    height = 220
    return (left, top, width, height)


def _save_input_snapshot(input_xy: tuple[int, int], tag: str) -> str | None:
    if not bool(read_setting("debug_methods_mode")):
        return None
    try:
        region = _input_debug_region(input_xy)
        snap_rgb = take_screenshot(region)
        out_dir = Path(__file__).resolve().parents[1] / 'temp_log'
        out_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime('%Y%m%d_%H%M%S_%f')
        path = out_dir / f'{tag}_{ts}.png'
        cv2.imwrite(str(path), cv2.cvtColor(snap_rgb, cv2.COLOR_RGB2BGR))
        return str(path)
    except Exception as exc:
        log_and_print(f'[chat_send] input snapshot failed tag={tag}: {exc}', 'error')
        return None


def _clear_input_manually() -> bool:
    current = _normalize_input_text(_read_input_text())
    if not current:
        return True
    try:
        pag.press('end')
        gd.pause(0.04)
    except Exception:
        pass
    backspaces = max(len(current) + 12, 32)
    for _ in range(backspaces):
        pag.press('backspace')
    gd.pause(0.12)
    remaining = _normalize_input_text(_read_input_text())
    return remaining == ''


def _type_with_pywinauto(text: str) -> bool:
    if not text:
        return False
    source_text = str(text)
    if '\n' in source_text or '\r' in source_text:
        return False

    escaped = []
    for ch in source_text:
        if ch in {'+', '^', '%', '~', '(', ')', '{', '}'}:
            escaped.append('{' + ch + '}')
        else:
            escaped.append(ch)
    send_text = ''.join(escaped)

    for vk_packet in (True, False):
        try:
            win_keyboard.send_keys(
                send_text,
                pause=0.02,
                with_spaces=True,
                with_newlines=True,
                vk_packet=vk_packet,
            )
            log_and_print(f'[chat_send] type method=pywinauto vk_packet={vk_packet}', 'debug')
            return True
        except Exception as exc:
            log_and_print(f'[chat_send] type method=pywinauto vk_packet={vk_packet} failed: {exc}', 'debug')
            continue
    return False


def _press_shift_enter() -> None:
    pag.keyDown('shift')
    gd.pause(0.03)
    pag.press('enter')
    gd.pause(0.03)
    pag.keyUp('shift')
    gd.pause(0.05)


def _type_multiline_unicode(text: str) -> bool:
    normalized = str(text or '').replace('\r\n', '\n').replace('\r', '\n')
    parts = normalized.split('\n')
    try:
        for idx, part in enumerate(parts):
            if part:
                ok = gd.type_text_unicode(part, interval_s=0.005)
                log_and_print(f'[chat_send] type multiline line={idx+1}/{len(parts)} chars={len(part)} ok={ok}', 'debug')
                if not ok:
                    return False
            if idx < len(parts) - 1:
                _press_shift_enter()
        return True
    except Exception as exc:
        log_and_print(f'[chat_send] type multiline failed: {exc}', 'debug')
        return False


def _type_text_manually(text: str, type_text_fn=None) -> tuple[bool, str]:
    source_text = str(text or '')
    if type_text_fn is not None:
        try:
            ok = bool(type_text_fn(source_text))
            log_and_print(f'[chat_send] type method=external ok={ok}', 'debug')
            if ok:
                return True, 'external'
        except Exception as exc:
            log_and_print(f'[chat_send] type method=external failed: {exc}', 'debug')
    if '\n' in source_text or '\r' in source_text:
        ok = _type_multiline_unicode(source_text)
        return ok, 'multiline_unicode'
    try:
        if _type_with_pywinauto(source_text):
            return True, 'pywinauto'
    except Exception as exc:
        log_and_print(f'[chat_send] type method=pywinauto wrapper failed: {exc}', 'debug')
    try:
        ok = gd.type_text_unicode(source_text, interval_s=0.005)
        log_and_print(f'[chat_send] type method=unicode_singleline ok={ok}', 'debug')
        if ok:
            return True, 'unicode_singleline'
    except Exception as exc:
        log_and_print(f'[chat_send] type method=unicode_singleline failed: {exc}', 'debug')
    return False, 'none'


def prepare_text_in_active_chat(window, input_xy: tuple[int, int], text: str, type_text_fn=None) -> bool:
    expected = _normalize_input_text(text)
    if not expected:
        log_and_print('[chat_send] empty text', 'error')
        return False

    for attempt in range(1, 4):
        _focus_input(window, input_xy)
        if not _clear_input_manually():
            log_and_print(f'[chat_send] manual clear failed attempt={attempt}/3', 'info')
            _save_input_snapshot(input_xy, f'chat_send_clear_failed_attempt{attempt}')
            continue

        _save_input_snapshot(input_xy, f'chat_send_before_type_attempt{attempt}')
        typed_ok, method_name = _type_text_manually(expected, type_text_fn=type_text_fn)
        _save_input_snapshot(input_xy, f'chat_send_after_type_attempt{attempt}_{method_name}')
        log_and_print(
            f'[chat_send] type attempt={attempt}/3 method={method_name} typed_ok={typed_ok} expected_len={len(expected)}',
            'info',
        )
        if not typed_ok:
            gd.pause(0.2)
            continue

        gd.pause(0.2)
        current_before_send = _normalize_input_text(_read_input_text())
        contains_before_send = bool(current_before_send) and (
            expected in current_before_send or current_before_send in expected
        )
        log_and_print(
            f'[chat_send] pre-send verify attempt={attempt}/3 method={method_name} '
            f'contains_before_send={contains_before_send} input_len={len(current_before_send)}',
            'info',
        )
        if contains_before_send:
            return True
        _save_input_snapshot(input_xy, f'chat_send_verify_failed_attempt{attempt}_{method_name}')
        gd.pause(0.2)

    log_and_print('[chat_send] manual typing failed after 3 attempts', 'info')
    return False


def send_text_to_active_chat(window, input_xy: tuple[int, int], text: str, type_text_fn=None) -> bool:
    expected = _normalize_input_text(text)
    if not prepare_text_in_active_chat(window, input_xy, expected, type_text_fn=type_text_fn):
        return False

    pag.press('enter')
    gd.pause(0.6)

    current_after_send = _normalize_input_text(_read_input_text())
    still_contains_after_send = bool(current_after_send) and (
        expected in current_after_send or current_after_send in expected
    )
    log_and_print(
        f'[chat_send] post-send verify still_contains_after_send={still_contains_after_send} input_len={len(current_after_send)}',
        'info',
    )
    if still_contains_after_send:
        _save_input_snapshot(input_xy, 'chat_send_post_send_still_contains')
    return not still_contains_after_send

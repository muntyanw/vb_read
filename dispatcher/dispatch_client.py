# viber_worker/dispatch_client.py
import os
from typing import Optional, Dict, Any, List, Union
import asyncio
import httpx
from pydantic import BaseModel, Field, field_validator, ValidationError, ConfigDict
from datetime import datetime, timezone
from pathlib import Path
from find_message import load_previous_text, save_current_text
from log import log_and_print
from core import gui_driver as gd
import pyperclip
import pyautogui as pag
from utils import read_setting, take_screenshot
import hashlib
import ctypes
from vb_utils import scroll_with_mouse
from recognize_text import text_includes_fast
import time
import random
import win32gui
import cv2
import numpy as np
import win32con
from pywinauto import keyboard
pag.FAILSAFE = False
ip_numbber = 0
def _ui_debug() -> bool:
    return bool(read_setting("debug_methods_mode"))
def _save_last_mess_debug(scope: tuple[int, int, int, int], channel_name: str, reason: str) -> str | None:
    try:
        left, top, right, bottom = [int(v) for v in scope]
        width = max(1, right - left)
        height = max(1, bottom - top)
        snap = take_screenshot((left, top, width, height))
        out_dir = Path(__file__).resolve().parents[1] / "temp_log"
        out_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        safe_channel = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in str(channel_name or "unknown"))
        safe_reason = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in str(reason or "unknown"))
        path = out_dir / f"last_mess_{safe_channel}_{safe_reason}_{ts}.png"
        cv2.imwrite(str(path), cv2.cvtColor(snap, cv2.COLOR_RGB2BGR))
        return str(path)
    except Exception as exc:
        log_and_print(f"[last_mess] debug screenshot save failed: {exc}", "error")
        return None
def _save_last_mess_annotated(
    scope: tuple[int, int, int, int],
    channel_name: str,
    recognized_rect: tuple[int, int, int, int],
    click_pos: tuple[int, int],
    tm_score: float,
    color_score: float,
    template_name: str,
) -> str | None:
    try:
        left, top, right, bottom = [int(v) for v in scope]
        width = max(1, right - left)
        height = max(1, bottom - top)
        snap = take_screenshot((left, top, width, height))
        bgr = cv2.cvtColor(snap, cv2.COLOR_RGB2BGR)
        rx, ry, rw, rh = [int(v) for v in recognized_rect]
        x1 = max(0, min(width - 1, rx))
        y1 = max(0, min(height - 1, ry))
        x2 = max(x1 + 1, min(width - 1, rx + rw))
        y2 = max(y1 + 1, min(height - 1, ry + rh))
        cv2.rectangle(bgr, (x1, y1), (x2, y2), (0, 255, 0), 2)
        cx, cy = int(click_pos[0]), int(click_pos[1])
        local_x = max(0, min(width - 1, cx - left))
        local_y = max(0, min(height - 1, cy - top))
        cv2.circle(bgr, (local_x, local_y), 4, (0, 0, 255), -1)
        label = f"tm={tm_score:.3f} color={color_score:.3f} tpl={template_name}"
        cv2.putText(bgr, label[:110], (6, 18), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 255, 255), 1, cv2.LINE_AA)
        out_dir = Path(__file__).resolve().parents[1] / "temp_log"
        out_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        safe_channel = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in str(channel_name or "unknown"))
        path = out_dir / f"last_mess_{safe_channel}_after_{ts}.png"
        cv2.imwrite(str(path), bgr)
        return str(path)
    except Exception as exc:
        log_and_print(f"[last_mess] annotated screenshot save failed: {exc}", "error")
        return None
def _last_mess_template_paths(channel_name: str) -> list[Path]:
    images_dir = Path(__file__).resolve().parents[1] / "images"
    candidates: list[Path] = []
    channel_dir = images_dir / str(channel_name)
    if channel_dir.exists():
        candidates.extend(sorted(channel_dir.glob("last_mess*.png")))
    candidates.extend(sorted(images_dir.glob("last_mess*.png")))
    seen = set()
    uniq = []
    for p in candidates:
        key = str(p.resolve())
        if key in seen:
            continue
        seen.add(key)
        uniq.append(p)
    return uniq
def _match_template_score(scr_bgr: np.ndarray, tpl_path: Path, scale: float) -> tuple[float, tuple[int, int], int, int] | None:
    tpl = cv2.imread(str(tpl_path), cv2.IMREAD_UNCHANGED)
    if tpl is None:
        return None
    if tpl.ndim == 3 and tpl.shape[2] == 4:
        tpl_bgr = cv2.cvtColor(tpl, cv2.COLOR_BGRA2BGR)
        alpha = tpl[:, :, 3]
        _, mask = cv2.threshold(alpha, 0, 255, cv2.THRESH_BINARY)
    elif tpl.ndim == 3:
        tpl_bgr = tpl
        mask = None
    else:
        tpl_bgr = cv2.cvtColor(tpl, cv2.COLOR_GRAY2BGR)
        mask = None
    th0, tw0 = tpl_bgr.shape[:2]
    tw = max(1, int(round(tw0 * float(scale))))
    th = max(1, int(round(th0 * float(scale))))
    if tw > scr_bgr.shape[1] or th > scr_bgr.shape[0]:
        return None
    interp = cv2.INTER_AREA if scale < 1.0 else cv2.INTER_LINEAR
    tpl_s = cv2.resize(tpl_bgr, (tw, th), interpolation=interp)
    mask_s = None
    if mask is not None:
        mask_s = cv2.resize(mask, (tw, th), interpolation=cv2.INTER_NEAREST)
    try:
        if mask_s is not None:
            res = cv2.matchTemplate(scr_bgr, tpl_s, cv2.TM_CCORR_NORMED, mask=mask_s)
        else:
            img_gray = cv2.cvtColor(scr_bgr, cv2.COLOR_BGR2GRAY)
            tpl_gray = cv2.cvtColor(tpl_s, cv2.COLOR_BGR2GRAY)
            img_gray = cv2.GaussianBlur(img_gray, (3, 3), 0)
            tpl_gray = cv2.GaussianBlur(tpl_gray, (3, 3), 0)
            res = cv2.matchTemplate(img_gray, tpl_gray, cv2.TM_CCOEFF_NORMED)
    except Exception:
        return None
    if res is None or res.size == 0:
        return None
    if not np.isfinite(res).any():
        return None
    _, max_val, _, max_loc = cv2.minMaxLoc(res)
    if not np.isfinite(max_val):
        return None
    return float(max_val), max_loc, tw, th
def _last_mess_color_score(roi_bgr: np.ndarray) -> tuple[float, bool]:
    if roi_bgr is None or roi_bgr.size == 0:
        return 0.0, False
    hsv = cv2.cvtColor(roi_bgr, cv2.COLOR_BGR2HSV)
    purple = cv2.inRange(hsv, (112, 35, 40), (168, 255, 255))
    light = cv2.inRange(hsv, (0, 0, 170), (179, 85, 255))
    total = float(max(1, roi_bgr.shape[0] * roi_bgr.shape[1]))
    purple_ratio = float(cv2.countNonZero(purple)) / total
    light_ratio = float(cv2.countNonZero(light)) / total
    purple_term = min(1.0, purple_ratio / 0.08)
    light_term = min(1.0, light_ratio / 0.02)
    score = 0.65 * purple_term + 0.35 * light_term
    is_valid = purple_ratio >= 0.04 and light_ratio >= 0.008
    return float(score), bool(is_valid)
def _find_last_mess_match(scope: tuple[int, int, int, int], channel_name: str):
    left, top, right, bottom = [int(v) for v in scope]
    width = max(1, right - left)
    height = max(1, bottom - top)
    snap = take_screenshot((left, top, width, height))
    scr_bgr = cv2.cvtColor(snap, cv2.COLOR_RGB2BGR)

    gray = cv2.cvtColor(scr_bgr, cv2.COLOR_BGR2GRAY)
    gray = cv2.GaussianBlur(gray, (5, 5), 1.2)

    min_r = max(12, int(min(width, height) * 0.10))
    max_r = max(min_r + 2, int(min(width, height) * 0.45))

    circles = cv2.HoughCircles(
        gray,
        cv2.HOUGH_GRADIENT,
        dp=1.2,
        minDist=18,
        param1=120,
        param2=24,
        minRadius=min_r,
        maxRadius=max_r,
    )
    if circles is None:
        return None

    hsv = cv2.cvtColor(scr_bgr, cv2.COLOR_BGR2HSV)
    cands = []

    for c in np.round(circles[0]).astype(int):
        cx, cy, r = int(c[0]), int(c[1]), int(c[2])
        x1, y1 = cx - r, cy - r
        x2, y2 = cx + r, cy + r
        if x1 < 0 or y1 < 0 or x2 >= width or y2 >= height:
            continue

        roi_hsv = hsv[y1:y2 + 1, x1:x2 + 1]
        rh, rw = roi_hsv.shape[:2]
        yy, xx = np.ogrid[:rh, :rw]
        circle_mask = ((xx - r) ** 2 + (yy - r) ** 2) <= (r * r)
        if int(circle_mask.sum()) < 40:
            continue

        # White circular button body.
        light_mask = (
            (roi_hsv[:, :, 1] <= 70)
            & (roi_hsv[:, :, 2] >= 145)
            & circle_mask
        )
        light_ratio = float(np.count_nonzero(light_mask)) / float(max(1, np.count_nonzero(circle_mask)))

        # Purple arrow glyph.
        purple_mask = (
            (roi_hsv[:, :, 0] >= 108)
            & (roi_hsv[:, :, 0] <= 172)
            & (roi_hsv[:, :, 1] >= 40)
            & (roi_hsv[:, :, 2] >= 45)
            & circle_mask
        )
        purple_count = int(np.count_nonzero(purple_mask))
        purple_ratio = float(purple_count) / float(max(1, np.count_nonzero(circle_mask)))

        if light_ratio < 0.42 or purple_ratio < 0.004:
            continue


        shape_score = 0.55 * min(1.0, light_ratio / 0.75) + 0.45 * min(1.0, purple_ratio / 0.06)
        color_score = min(1.0, purple_ratio / 0.06)
        final_score = 0.70 * float(shape_score) + 0.30 * float(color_score)

        cands.append(
            {
                "tm_score": float(shape_score),
                "color_score": float(color_score),
                "final_score": float(final_score),
                "color_ok": True,
                "clickable": True,
                "reason": "ok",
                "x": int(x1),
                "y": int(y1),
                "w": int(2 * r),
                "h": int(2 * r),
                "template": "circle_arrow",
                "scale": 1.0,
                "scan_attempts_total": int(len(circles[0])),
                "scan_attempts_tm_ok": int(len(cands) + 1),
                "abs_center": (int(left + cx), int(top + cy)),
            }
        )

    if not cands:
        return None

    cands.sort(key=lambda z: z["final_score"], reverse=True)
    return cands[0]
def _norm_resend_value(value: str) -> str:
    return "".join(ch for ch in str(value or "").lower() if ch.isalnum())
def _read_focused_field_text() -> str:
    try:
        pag.keyDown("ctrl")
        gd.pause(0.05)
        pag.press("a")
        gd.pause(0.05)
        pag.press("c")
        gd.pause(0.05)
        pag.keyUp("ctrl")
        gd.pause(0.08)
        return str(pyperclip.paste() or "")
    except Exception:
        return ""
def _resend_value_matches(actual: str, expected: str) -> bool:
    # For resend search we only need confirmation that something was inserted.
    # Input can contain one or two phones and may be transformed by the UI.
    a = _norm_resend_value(actual)
    return len(a) >= 2
def _save_resend_field_state(
    phase: str,
    attempt: int,
    actual: str,
    has_content: bool,
    scope: tuple[int, int, int, int] = (320, 300, 980, 470),
) -> str | None:
    try:
        left, top, right, bottom = [int(v) for v in scope]
        width = max(1, right - left)
        height = max(1, bottom - top)
        snap = take_screenshot((left, top, width, height))
        bgr = cv2.cvtColor(snap, cv2.COLOR_RGB2BGR)
        preview = str(actual or "").replace("\n", " ").replace("\r", " ")
        preview = " ".join(preview.split())
        if len(preview) > 80:
            preview = preview[:80] + "..."
        label = f"phase={phase} attempt={attempt} has_content={has_content} len={len(str(actual or ''))}"
        cv2.putText(bgr, label[:120], (8, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 1, cv2.LINE_AA)
        cv2.putText(bgr, f"actual='{preview}'"[:120], (8, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (180, 255, 180), 1, cv2.LINE_AA)
        out_dir = Path(__file__).resolve().parents[1] / "temp_log"
        out_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        safe_phase = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in str(phase or "unknown"))
        path = out_dir / f"resend_field_{safe_phase}_attempt{int(attempt)}_{ts}.png"
        cv2.imwrite(str(path), bgr)
        log_and_print(f"[resend] field snapshot: {path}", "DEBUG")
        return str(path)
    except Exception as exc:
        log_and_print(f"[resend] field snapshot save failed: {exc}", "ERROR")
        return None
def _set_and_verify_resend_search_value(value: str, clear_before_input: bool = True) -> bool:
    value = str(value or "").strip()
    if not value:
        return False

    def _clear_field() -> None:
        pag.keyDown("ctrl")
        gd.pause(0.05)
        pag.press("a")
        gd.pause(0.05)
        pag.keyUp("ctrl")
        gd.pause(0.05)
        pag.press("backspace")
        gd.pause(0.12)

    for attempt in range(1, 4):
        # 1) Keyboard typing first (most stable for this field)
        if clear_before_input:
            _clear_field()
        typed = False
        try:
            typed = bool(gd.type_text_unicode(value, interval_s=0.004))
        except Exception:
            typed = False

        if not typed:
            for ch in value:
                pag.typewrite(ch)
                gd.pause(0.01)

        gd.pause(0.30)
        actual = _read_focused_field_text()
        has_content = _resend_value_matches(actual, value)
        _save_resend_field_state("after_typing", attempt, actual, has_content)
        if has_content:
            log_and_print(f"[resend] search value accepted via typing attempt={attempt}", "DEBUG")
            return True

        # 2) Clipboard paste via Ctrl+V
        if clear_before_input:
            _clear_field()
        pyperclip.copy(value)
        gd.pause(0.08)
        pag.keyDown("ctrl")
        gd.pause(0.04)
        pag.press("v")
        gd.pause(0.04)
        pag.keyUp("ctrl")
        gd.pause(0.30)

        actual = _read_focused_field_text()
        has_content = _resend_value_matches(actual, value)
        _save_resend_field_state("after_paste_ctrl_v", attempt, actual, has_content)
        if has_content:
            log_and_print(f"[resend] search value accepted via Ctrl+V attempt={attempt}", "DEBUG")
            return True

        # 3) Clipboard paste via Shift+Insert
        if clear_before_input:
            _clear_field()
        pyperclip.copy(value)
        gd.pause(0.08)
        pag.keyDown("shift")
        gd.pause(0.04)
        pag.press("insert")
        gd.pause(0.04)
        pag.keyUp("shift")
        gd.pause(0.30)

        actual = _read_focused_field_text()
        has_content = _resend_value_matches(actual, value)
        _save_resend_field_state("after_paste_shift_insert", attempt, actual, has_content)
        if has_content:
            log_and_print(f"[resend] search value accepted via Shift+Insert attempt={attempt}", "DEBUG")
            return True

        log_and_print(
            f"[resend] all fill methods failed attempt={attempt}",
            "WARNING",
        )

    log_and_print("[resend] cannot verify non-empty value in search field", "ERROR")
    return False

def _get_ips() -> list[str]:
    ips = read_setting("IPS") or []
    if not isinstance(ips, list):
        return []
    return [str(ip).strip() for ip in ips if str(ip).strip()]
def get_dispatch_url():
    ips = _get_ips()
    if not ips:
        return "http://127.0.0.1:8888/api/v1/dispatch/analyze"
    global ip_numbber
    ip_numbber = ip_numbber % len(ips)
    return f"http://{ips[ip_numbber]}:8888/api/v1/dispatch/analyze"
DISPATCH_API_KEY = os.getenv(
    "DISPATCH_API_KEY",
    "3e7e07d4f2a64f99a95cf8b18a1381f635ea2cde93cce94e4dcbfdd4c3af5d87",
)
# Global flag to prevent duplicate message handling.
processed_messages = set()
# Semaphore for sequential message processing.
processing_semaphore = asyncio.Semaphore(1)
count_y_mess_empty = 0
copied_message_counter = 0
last_message_copy_monotonic = time.monotonic()
class DispatchError(Exception):
    pass
def mark_message_copied() -> None:
    global copied_message_counter, last_message_copy_monotonic
    copied_message_counter += 1
    last_message_copy_monotonic = time.monotonic()
    log_and_print(f"[copy_watchdog] copied_message_counter={copied_message_counter}", "info")
def reset_copy_watchdog() -> None:
    global copied_message_counter, last_message_copy_monotonic
    copied_message_counter = 0
    last_message_copy_monotonic = time.monotonic()
    log_and_print("[copy_watchdog] reset on worker start", "info")
# ---- Client-side models for server response ----
class Action(BaseModel):
    type: str
    payload: Optional[Dict[str, Any]] = None
class Decision(BaseModel):
    matches: Optional[bool] = None
    confidence: Optional[float] = None
    reason: Optional[str] = None
class MatchedContact(BaseModel):
    order_id: int
    carrier_id: int
    viber_contact_name: Optional[str] = None
class DispatchResult(BaseModel):
    # Ignore unexpected fields from backend.
    model_config = ConfigDict(extra='ignore')
    message_id: str
    # Convert null -> {} and keep a safe default via default_factory.
    extracted: Dict[str, Any] = Field(default_factory=dict)
    # Convert null -> [] for list fields.
    actions: List[Action] = Field(default_factory=list)
    decision: Optional[Decision] = None
    matched_contacts: List[MatchedContact] = Field(default_factory=list)
    @field_validator("extracted", mode="before")
    @classmethod
    def _coerce_extracted(cls, v):
        return v or {}
    @field_validator("actions", mode="before")
    @classmethod
    def _coerce_actions(cls, v):
        return v or []
    @field_validator("matched_contacts", mode="before")
    @classmethod
    def _coerce_matched_contacts(cls, v):
        return v or []
def _dispatch_base_url() -> str:
    # From ".../dispatch/analyze" to ".../dispatch".
    base = get_dispatch_url().rstrip("/")
    return base.rsplit("/", 1)[0]

def _dispatch_job_url(job_id: str) -> str:
    return _dispatch_base_url() + f"/jobs/{job_id}"


async def _poll_dispatch_job_result(
    client: httpx.AsyncClient,
    job_id: str,
    headers: Dict[str, str],
    timeout_s: float,
) -> Dict[str, Any]:
    poll_interval_s = float(read_setting("dispatch_job_poll_interval_s") or 1.5)
    max_wait_s = float(read_setting("dispatch_job_max_wait_s") or max(30.0, timeout_s * 4.0))
    deadline = time.monotonic() + max_wait_s
    url = _dispatch_job_url(job_id)

    while time.monotonic() < deadline:
        resp = await client.get(url, headers=headers)
        if resp.status_code == 401:
            raise DispatchError("Unauthorized: check X-API-Key")
        resp.raise_for_status()

        job_data = resp.json() or {}
        status = str(job_data.get("status") or "").strip().lower()
        log_and_print(f"[dispatch] job {job_id} status={status}", "debug")

        if status in {"done", "completed", "success", "succeeded"}:
            result_payload = job_data.get("result_payload")
            if not isinstance(result_payload, dict):
                raise DispatchError(f"Dispatch job done but result_payload is missing/invalid for job_id={job_id}")
            return result_payload

        if status in {"failed", "error", "cancelled", "canceled"}:
            err_text = str(job_data.get("error") or job_data.get("message") or "Unknown job error")
            raise DispatchError(f"Dispatch job failed job_id={job_id}: {err_text}")

        await asyncio.sleep(max(0.5, poll_interval_s))

    raise DispatchError(f"Dispatch job timeout job_id={job_id} wait_s={max_wait_s}")

async def has_active_orders(
    window_days: int = 2,
    include_count: bool = False,
    timeout_s: float = 5.0,
    retries: int = 1,
) -> tuple[bool, Optional[int]]:
    """
    Returns (has_active, count|None).
    - has_active: True/False for active orders in [today..today+window_days]
    - count: when include_count=True, returns count (subject to server limit), else None
    """
    url = _dispatch_base_url() + "/has-active-orders"
    params = {
        "window_days": window_days,
        "include_count": "true" if include_count else "false",
    }
    headers = {
        "X-API-Key": DISPATCH_API_KEY,
        "X-Client": "viber-worker",
    }
    for attempt in range(retries + 1):
        try:
            async with httpx.AsyncClient(
                timeout=timeout_s, follow_redirects=True
            ) as client:
                resp = await client.get(url, params=params, headers=headers)
                log_and_print(
                    f"[has_active_orders] GET {url} status={resp.status_code}"
                )
                if resp.status_code == 401:
                    raise DispatchError("Unauthorized: check X-API-Key")
                resp.raise_for_status()
                data = resp.json() or {}
                return bool(data.get("has_active")), data.get("count")
        except Exception as e:
            log_and_print(
                f"[has_active_orders] attempt {attempt+1}/{retries+1} failed: {e}",
                "error",
            )
            if attempt < retries:
                await asyncio.sleep(0.5 * (attempt + 1))
    log_and_print("[has_active_orders] giving up, returning (False, None)", "error")
    return False, None
def _fallback_result(message_id: str) -> DispatchResult:
    """Fallback response to avoid returning None to callers."""
    return DispatchResult(
        message_id=message_id,
        extracted={},
        actions=[Action(type="ignore", payload=None)],
        decision=Decision(matches=False, confidence=0.0, reason="Fallback"),
    )
def _safe_action_type(a: Union[Action, Dict[str, Any], None]) -> Optional[str]:
    if a is None:
        return None
    if isinstance(a, dict):
        return a.get("type")
    try:
        return a.type  # pydantic model
    except Exception:
        return None
async def process_one_message_dispatcher(
    message_text: Optional[str], 
    file_path: Optional[str],
    name_viber_channel: str,
    s
):
    log_and_print("!!! process_one_message_dispatcher !!!")
    uid_source = message_text or file_path or f"msg-{time.time()}"
    if uid_source:
        processed_messages.add(uid_source)
    # Process messages sequentially using semaphore.
    async with processing_semaphore:
        try:
            log_and_print(f"Обработка сообщения: {message_text}", "info")
            md5_hash = hashlib.md5(uid_source.encode()).hexdigest()
            return await send_for_analysis(
                message_id=md5_hash,
                text=message_text or "",
                chat_id=name_viber_channel,
                sender="",  # sender name if available
                attachments=None,
                locale="uk",
                timeout_s=float(read_setting("dispatch_timeout_s") or 15.0),
                retries=int(read_setting("dispatch_retries") or 2),
            )
        except Exception as e:
            log_and_print(f"Ошибка при обработке одного сообщения: {e}", "error")
            await asyncio.sleep(2)  # short pause before next attempt
            # IMPORTANT: always return non-None so upper flow does not crash.
            return _fallback_result(message_id=md5_hash)
async def send_for_analysis(
    *,
    message_id: str,
    text: str,
    chat_id: Optional[str] = None,
    sender: Optional[str] = None,
    attachments: Optional[list] = None,
    locale: str = "uk",
    timeout_s: float = 15.0,
    retries: int = 2,
) -> DispatchResult:

    global ip_numbber

    payload = {
        "message_id": message_id,
        "chat_id": chat_id,
        "sender": sender,
        "text": text,
        "attachments": attachments or [],
        "received_at": datetime.now(timezone.utc).isoformat(),
        "locale": locale,
    }
    headers = {
        "X-API-Key": DISPATCH_API_KEY,
        "Content-Type": "application/json",
        "X-Client": "viber-worker",
    }
    log_and_print(f"[dispatch] POST {get_dispatch_url()}")
    log_and_print(
        "[dispatch] headers: {{'X-API-Key': '***', 'Content-Type': 'application/json', 'X-Client': 'viber-worker'}}"
    )
    log_and_print(f"[dispatch] payload: {payload}")

    last_exc: Optional[Exception] = None
    for attempt in range(retries + 1):
        try:
            async with httpx.AsyncClient(timeout=timeout_s, follow_redirects=True) as client:
                log_and_print(f"[dispatch] post to {get_dispatch_url()}", "debug")
                resp = await client.post(get_dispatch_url(), json=payload, headers=headers)
                log_and_print(f"[dispatch] status={resp.status_code}", "debug")

                body_preview = (
                    resp.text
                    if len(resp.text) < 2000
                    else (resp.text[:2000] + "...<truncated>")
                )
                log_and_print(f"[dispatch] body: {body_preview}")

                if resp.status_code == 401:
                    raise DispatchError("Unauthorized: check X-API-Key")

                resp.raise_for_status()
                data = resp.json() or {}

                # New async flow: analyze enqueues a job and returns 202 + job_id.
                if resp.status_code == 202:
                    job_id = str(data.get("job_id") or "").strip()
                    job_status = str(data.get("status") or "").strip().lower()
                    if not job_id:
                        raise DispatchError("Dispatch enqueue response missing job_id")
                    log_and_print(f"[dispatch] processing job_id={job_id} status={job_status}", "info")
                    data = await _poll_dispatch_job_result(client, job_id, headers, timeout_s)

                try:
                    result = DispatchResult(**data)
                except ValidationError as ve:
                    log_and_print(f"[dispatch] ValidationError: {ve}", "error")
                    actions_raw = data.get("actions") or []
                    actions: List[Action] = []
                    for a in actions_raw:
                        if isinstance(a, dict):
                            actions.append(
                                Action(
                                    type=a.get("type", "ignore"),
                                    payload=a.get("payload"),
                                )
                            )
                    result = DispatchResult(
                        message_id=data.get("message_id", message_id),
                        extracted=data.get("extracted") or {},
                        actions=actions,
                        decision=data.get("decision"),
                    )
                return result
        except Exception as e:
            last_exc = e
            ips = _get_ips()
            current_ip = ips[ip_numbber % len(ips)] if ips else "no-ip-configured"
            log_and_print(
                f"[dispatch] attempt {attempt+1}/{retries+1} failed from {current_ip}: {e}", "error"
            )
            if ips:
                ip_numbber = (ip_numbber + 1) % len(ips)
                log_and_print(f"[dispatch] change ip to {ips[ip_numbber]}", "INFO")
            else:
                log_and_print("[dispatch] IPS is empty in settings.json", "ERROR")

            if attempt < retries:
                await asyncio.sleep(0.7 * (attempt + 1))
            else:
                log_and_print("[dispatch] returning fallback result", "error")
                return _fallback_result(message_id=message_id)

    raise DispatchError(f"Dispatch failed: {last_exc}")

def is_foto_message(scope):
    pos = gd.find_text_any(queries=["Копировать фото",],
                            lang="rus", 
                            count=2, 
                            pause_attempt_sec =1, 
                            scope=scope, 
                            threshold = 0.8,
                            is_debug=_ui_debug(), 
                            occurrence = 1)
    if pos:
        return True
    
    return False
def is_link(scope):
    pos = gd.find_text_any(queries=["Копировать ссылку",],
                            lang="rus", 
                            count=2, 
                            pause_attempt_sec =1, 
                            scope=scope, 
                            threshold = 0.8,
                            is_debug=_ui_debug(), 
                            occurrence = 1)
    if pos:
        return True
    
    return False
def is_center_ok():
    
    if not gd.click_image(
        "center_ok.png",
        scope=(350, 450, 800, 800),
        confidence=0.88,
        count_click=2,
        multiscale=True,
        is_debug=_ui_debug(),
        ):
        log_and_print("[is_center_ok] Not find center OK")
        return False
    
    log_and_print("[is_center_ok] Find center OK")
    
    return True
def is_center_continue():
    
    if not gd.click_image(
        "continue.png",
        scope=(300, 550, 600, 700),
        confidence=0.88,
        count_click=2,
        multiscale=True,
        is_debug=_ui_debug(),
        ):
        log_and_print("[is_center_continue] Not find center Continue")
        return False
    
    log_and_print("[is_center_continue] Find center Continue")
    return True
def press_esq(window):
    window.set_focus()
    
    # Escape closes context menus; pyautogui uses "esc" as key name.
    pag.keyDown("esc")
    gd.pause(0.4)
    pag.keyUp("esc")
    gd.pause(0.4)
    log_and_print("[press_esq] press esq", "INFO")
    # gd.right_click(
    #     s.search_board_mess_x_start + s.x_offset_out_mess,
    #     s.search_board_mess_y_start + 10,
    # )
def click_copy_text(tp, window, s, x, y, is_debug=None):
    #global count_y_mess_empty
    if is_debug is None:
        is_debug = _ui_debug()
    
    scope=(
            int(x - s.width_menu),
            y - int(s.height_menu),
            x + int(s.width_menu),
            y + int(s.height_menu),
    )
    
    gd.pause(1)
    pos = False
    if tp == "image":
        pos = not gd.click_image(
            "copy.png",
            scope=scope,
            confidence=0.88,
            count_click=1,
            multiscale=True,
            is_debug=is_debug,
        )
    else:
        pos = gd.click_text(
            ["Копировать текст", "Скопировать сообщение"],
            count_attempt_find=2,
            pause_attempt=2,
            lang="rus",
            scope=scope,
            is_debug=is_debug,
            threshold=0.8,
            occurrence=1,
        )
    
    log_and_print(f"pos = {pos}", "INFO")
    if not pos:
        
        if tp == "image":
        
            pos = gd.click_text(
                ["Копировать текст", "Скопировать сообщение"],
                count_attempt_find=2,
                pause_attempt=2,
                lang="rus",
                scope=scope,
                is_debug=is_debug,
                threshold=0.8,
                occurrence=1,
            )
        else:
            pos = gd.click_image(
                "copy.png",
                scope=scope,
                confidence=0.88,
                count_click=1,
                multiscale=True,
                is_debug=is_debug,
            )
            
    if not pos:
        
        log_and_print("[send_messages_from_y_mess] Not find Скопировать сообщение", "INFO")
        
        press_esq(window)    
        #if is_foto_message(scope) or is_link(scope) or is_center_continue():
    
        #count_y_mess_empty = count_y_mess_empty + 1
        
        #log_and_print("[send_messages_from_y_mess] right click empty place", "INFO")
        return "is_foto"
        
        #else:
        #    press_esq(window)
        #    return None
    log_and_print("[send_messages_from_y_mess] Повідомлення скопійовано в буфер обміну", "INFO")
    mark_message_copied()
    return pyperclip.paste()
count_old_mess = 0
async def send_messages_from_y_mess(window, viber_channel, s):
    window.set_focus()
    sending = 0
    was_new_mess = False
    global count_old_mess
    for x, y in s.y_mess:
        if y:
            log_and_print(f"[send_messages_from_y_mess] Меседж y = {y}")
            window.set_focus()
            x = x + s.search_board_mess_x_start + 180
            y = y + s.search_board_mess_y_start
            xRight = x - 140
            yRight = y - 10
            gd.right_click(xRight, yRight)
            log_and_print(
                f"[send_messages_from_y_mess] right_click xRight = {xRight}, yRight = {yRight}"
            )
            text = click_copy_text("text", window, s, x, y, is_debug=_ui_debug())
            
            if len(text) == 1:
                continue
    
            if text == "is_foto":
                log_and_print("[send_messages_from_y_mess] Фото повідомлення", "INFO")
                continue
            
            if text is None:
                log_and_print(
                    "[send_messages_from_y_mess] Не вдалося скопіювати меседж, буфер обміну пустий", "INFO"
                )
                
                if is_center_ok():
                    continue
                else:
                    return "repeat"
                
            if not text_includes_fast(text, s.old_text, 0.7):
                was_new_mess = True
                count_old_mess = 0
                log_and_print(
                    "[send_messages_from_y_mess] Відправка та збереження нового сповіщення для аналізу", "INFO"
                )
                resp = await process_one_message_dispatcher(
                    text, None,
                    viber_channel["name_viber_channel"],
                    s
                )
                log_and_print(
                    f"[send_messages_from_y_mess] response from server: {resp.model_dump() if isinstance(resp, DispatchResult) else resp}"
                )
                # Extract type of first action (if present).
                action_type = None
                viber_names = []
                
                if isinstance(resp, DispatchResult) and resp.actions:
                    first_action = resp.actions[0]
                    action_type = _safe_action_type(first_action)
                    
                    # 2) Extract carrier names if backend returned matched_contacts.
                    if hasattr(resp, "matched_contacts") and getattr(resp, "matched_contacts", None):
                        # resp.matched_contacts may contain objects or dicts.
                        for mc in resp.matched_contacts or []:
                            # dict case
                            if isinstance(mc, dict):
                                name = mc.get("viber_contact_name")
                            else:
                                # Pydantic MatchedContact case
                                name = getattr(mc, "viber_contact_name", None)
                            if name and name not in viber_names:
                                viber_names.append(name)
                fallback_response = (
                    isinstance(resp, DispatchResult)
                    and resp.decision is not None
                    and str(resp.decision.reason or "").strip().lower() == "fallback"
                )
                log_and_print(
                    f"[send_messages_from_y_mess] action_type={action_type} matched_contacts={len(viber_names)} fallback={fallback_response}",
                    "DEBUG",
                )
                if fallback_response:
                    log_and_print("[send_messages_from_y_mess] dispatch fallback: keep message for retry", "WARNING")
                    continue

                result = True
                if action_type and action_type != "ignore":
                    log_and_print("++++++++++++++++++++++++++++++++++++++++++++++", "INFO")
                    result = sendViberMessDispatherToCarrier(
                        viber_names, window, xRight, yRight, viber_channel, text, s
                    )
                    if not result:
                        press_esq(window)
                        gd.right_click(
                            s.search_board_mess_x_start + s.x_offset_out_mess,
                            s.search_board_mess_y_start + 10,
                        )
                        result = sendViberMessDispatherToCarrier(
                        viber_names, window, xRight, yRight, viber_channel, text, s
                    )
                else:
                    log_and_print("xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx", "INFO")
                if result:
                    save_current_text(text)
                    s.old_text = load_previous_text()
            else:
                count_old_mess += 1
                if count_old_mess >= 3:
                    was_new_mess = False
                    count_old_mess = 0
                    return was_new_mess
                sending += 1
                log_and_print(
                    "[send_messages_from_y_mess] ------------------------------------- Сповіщення вже було відправлено", "INFO"
                )
                if sending >= 2:
                    # break
                    pass
    return was_new_mess
def clickLastMess(window, name_viber_channel):
    window.set_focus()
    base_scope = (740, 910, 1120, 1000)
    if _ui_debug():
        debug_before_path = _save_last_mess_debug(base_scope, name_viber_channel, "search_scope")
        if debug_before_path:
            log_and_print(f"[last_mess] search snapshot: {debug_before_path}", "DEBUG")
    match = _find_last_mess_match(base_scope, name_viber_channel)
    if not match:
        log_and_print("Not find icon LastMessage", "INFO")
        if _ui_debug():
            debug_after_path = _save_last_mess_debug(base_scope, name_viber_channel, "search_no_candidate")
            if debug_after_path:
                log_and_print(f"[last_mess] no-candidate snapshot: {debug_after_path}", "DEBUG")
        return False
    click_pos = match["abs_center"]
    if _ui_debug():
        debug_after_path = _save_last_mess_annotated(
            base_scope,
            name_viber_channel,
            (int(match["x"]), int(match["y"]), int(match["w"]), int(match["h"])),
            (int(click_pos[0]), int(click_pos[1])),
            float(match["tm_score"]),
            float(match["color_score"]),
            str(match["template"]),
        )
        if debug_after_path:
            log_and_print(f"[last_mess] after snapshot: {debug_after_path}", "DEBUG")
    log_and_print(
        f"[last_mess] match final={match['final_score']:.3f} tm={match['tm_score']:.3f} "
        f"color={match['color_score']:.3f} tpl={match['template']} "
        f"scale={match.get('scale', 0.0):.3f} "
        f"tm_ok={match.get('scan_attempts_tm_ok', 0)}/{match.get('scan_attempts_total', 0)} "
        f"reason={match.get('reason', 'n/a')} pos={click_pos}",
        "DEBUG",
    )
    if not bool(match.get("clickable", True)):
        log_and_print("Not find icon LastMessage (best candidate below tm threshold)", "INFO")
        return False
    gd.click(int(click_pos[0]), int(click_pos[1]))
    log_and_print("Click down to last messages", "INFO")
    return True
def moveToContactsAndScrollUp():
    log_and_print("[moveToContactsAndScrollUp] scroll up contacts")
    
    gd.human_move(140, 400)
    gd.scroll(3000)
def click_viber_channel_image(name_viber_channel ):
    
    return gd.click_image(
            name_viber_channel + ".png",
            scope=(0, 200, 120, 700),
            confidence=0.88,
            count_click=1,
            multiscale=True,
            is_debug=_ui_debug(),
    )
    
def click_viber_channel_text(viber_channel):
    
    return gd.click_text(
            [viber_channel["name_viber_contact"],],
            count_attempt_find=2,
            pause_attempt=4,
            lang=viber_channel["name_viber_contact_lang"],
            scope=(0, 200, 320, 700),
            threshold=0.5,
            plus_x = -16,
            is_debug=_ui_debug(),
            count_click=2
    )
def klickViberChannel(tp, window, clickLastMessBool, viber_channel):
    log_and_print(f"start click {viber_channel["name_viber_channel"]}", "DEBUG")
    press_esq(window)
    
    if tp == "image":
        pos = click_viber_channel_image(viber_channel["name_viber_channel"])
        
        if not pos:       
            log_and_print(f"Not find image chat {viber_channel["name_viber_channel"]}", "INFO")
                
            pos = click_viber_channel_text(viber_channel)
            
            if not pos:  
                log_and_print(f"Not find text name chat {viber_channel["name_viber_channel"]}", "INFO")
            
        
    else:
        pos = click_viber_channel_text(viber_channel)
        
        if not pos:       
            log_and_print(f"Not find text name chat {viber_channel["name_viber_channel"]}", "INFO")
                
            pos = click_viber_channel_image(viber_channel["name_viber_channel"])
            
            if not pos:  
                log_and_print(f"Not find image chat {viber_channel["name_viber_channel"]}", "INFO")
            
    log_and_print(f"Click name chat {viber_channel["name_viber_channel"]}")
    if clickLastMessBool:
        clickLastMess(window, viber_channel["name_viber_channel"])
        
    moveToContactsAndScrollUp()
    
    return True
def findMessage(window, x, y, viber_channel, text, s):
    log_and_print(f"[findMessage] text = {text}")
    gd.right_click(x, y)
    gd.pause(0.5)
    current_text = click_copy_text("text", window, s, x+60, y, is_debug=_ui_debug())
    
    log_and_print(f"[findMessage] current_text = {current_text}")
    if current_text and text_includes_fast(text, current_text, 0.7):
        log_and_print("[findMessage] succ message find")
        return x, y
    else:
        log_and_print("[findMessage] succ message not find")
        count_attempt_find = 0
        count_attempt_find_max = 3
        while True:
            window.set_focus()
            fill_y_mess(window, viber_channel, s)
            if len(s.y_mess) > 0:
                for x, y in s.y_mess:
                    if y:
                        log_and_print(f"[findMessage] Меседж y = {y}")
                        window.set_focus()
                        x = x + s.search_board_mess_x_start + 180
                        y = y + s.search_board_mess_y_start
                        xRight = x - 160
                        yRight = y
                        gd.right_click(xRight, yRight)
                        log_and_print(
                            f"[findMessage] right_click xRight = {xRight}, yRight = {yRight}"
                        )
                        current_text = click_copy_text("text", window, s, x, y)
                        if current_text == "":
                            press_esq(window)
                            continue
                        if text_includes_fast(text, str(current_text), 0.7):
                            log_and_print("succ message find")
                            return x, y
                        else:
                            log_and_print("[findMessage] this not right text")
                count_attempt_find += 1
                if count_attempt_find > count_attempt_find_max:
                    return False
                count_scroll_up = read_setting("count_scroll_up")
                scroll_with_mouse(window, count_scroll=count_scroll_up, direction="up")
            else:
                klickViberChannel("image", window, True, viber_channel)
                pag.keyDown("esq")
                gd.pause(0.2)
                pag.keyUp("esq")
                gd.pause(0.2)
                gd.right_click(
                    s.search_board_mess_x_start + s.x_offset_out_mess,
                    s.search_board_mess_y_start + 10,
                )
def sendViberMessDispatherToCarrier(viber_names, window, x, y, viber_channel, text, s):
    is_debug = _ui_debug()
    resultFind = findMessage(window, x, y, viber_channel, text, s)
    if resultFind:
        x, y = resultFind
    else:
        return False
    xRight = x - 70
    yRight = y + 20
    gd.right_click(xRight, yRight)
    if not gd.click_text(
        ["Переслать"],
        count_attempt_find=2,
        pause_attempt=4,
        lang="rus",
        scope=(x - 200, y - 50, x + 200, y + 400),
        threshold=0.86,
        plus_x = -16,
        is_debug=_ui_debug(),
    ):
        log_and_print("Not find menu item Переслать")
        return False
    log_and_print("Click Переслать")
    for idx, viber_name in enumerate(viber_names):
        log_and_print(f"viber_name = {viber_name}")
        
        first_name = viber_name.split()[0]
   
        pos = gd.find_image(
            "find.png", scope=(320, 320, 380, 380), multiscale=True, is_debug=is_debug
        )
        if not pos:
            log_and_print("Not find field find in resend")
            return False
    
        gd.click(pos[0] + 100, pos[1] - 10)
        log_and_print("Click field find")
        clear_before_input = (idx == 0)
        if not _set_and_verify_resend_search_value(viber_name, clear_before_input=clear_before_input):
            log_and_print(f"[resend] search field fill failed for {viber_name}", "ERROR")
            return "repeat"
        gd.pause(0.4)
        if not gd.click_image(
            "select.png",
            scope=(580, 400, 940, 620),
            confidence=0.97,
            count_click=1,
            multiscale=False,
            is_debug=_ui_debug(),
        ): 
        #if not gd.click_text(
        #    [first_name],
        #    count_attempt_find=2,
        #    pause_attempt=4,
        #    lang="ukr",
        #    scope=(pos[0], pos[0] + 40, pos[0] + 300, pos[0] + 200),
        #    is_debug=_ui_debug(),
        #    threshold=0.5,
        #    occurrence=1,
        #):
            log_and_print(f"Not find NameViberCarrier  {viber_name}")
            return "repeat"
        log_and_print(f"click name chat {viber_name}")
        gd.pause(1)
    if not gd.click_image(
        "resend.png",
        scope=(460, 730, 640, 810),
        confidence=0.5,
        count_click=1,
        is_debug=_ui_debug(),
    ):
        log_and_print("Not find button resend")
        return "repeat"
    log_and_print("click button resend success")
    save_current_text(text)
    s.old_text = load_previous_text()
    klickViberChannel("image", window, True, viber_channel)
    return True
def fill_y_mess(window, viber_channel, s):
    s.y_mess = []
    window.set_focus()
    log_and_print("Старт fill_y_mess")
    height = s.search_board_mess_y_end - s.search_board_mess_y_start
    width = s.search_board_mess_x_end - s.search_board_mess_x_start
    x, y = s.search_board_mess_x_start + 120, s.search_board_mess_y_start
    log_and_print(f"x = {x} y = {y} height = {height}, width = {width}")
    heart_templates = []
    channel_name = viber_channel["name_viber_channel"]
    for idx in range(1, 8):
        file_name = "heart.png" if idx == 1 else f"heart{idx}.png"
        file_path = f"images\\{channel_name}\\{file_name}"
        if not os.path.exists(file_path):
            log_and_print(f"[fill_y_mess] template not found, stop heart scan list: {file_path}", "debug")
            break
        heart_templates.append(file_path)
    if not heart_templates:
        log_and_print(f"[fill_y_mess] no heart templates found for channel={channel_name}", "error")
        return
    coordinates = gd.capture_and_find_image_boundary_coordinates(
        (x, y, 800, height),
        heart_templates,
        visualize=False,
        threshold=0.88,
    )
    window.set_focus()
    s.y_mess = [(coord[0], coord[1]) for coord in coordinates]
    log_and_print(f"s.y_mess = {s.y_mess}")
def click_close_hitlite():
    log_and_print("Find hitlite", "INFO")
    if not gd.click_image(
        "close.png",
        scope=(750, 945, 800, 990),
        confidence=0.8,
        count_click=1,
        multiscale=True,
        plus_x=10,
        plus_y=6,
        is_debug=_ui_debug(),
    ):
        log_and_print("Not find icon close", "INFO")
        return False
    log_and_print("Find success hitlite and click close", "INFO")
    return True
def click_folder():
    log_and_print("Find button folder", "INFO")
    if not gd.click_image(
        "folder.png",
        scope=(66, 154, 175, 207),
        confidence=0.8,
        count_click=1,
        multiscale=True,
        is_debug=_ui_debug(),
    ):
        log_and_print("Not find button folder", "INFO")
        return False
    log_and_print("Find success button folder and click", "INFO")
    return True
def click_close_image():
    log_and_print("Find hitlite", "INFO")
    if not gd.click_image(
        "close_image.png",
        scope=(930, 40, 1080, 100),
        confidence=0.8,
        count_click=1,
        multiscale=True,
        plus_x=10,
        plus_y=6,
        is_debug=_ui_debug(),
    ):
        log_and_print("Not find icon close image", "INFO")
        return False
    
    log_and_print("Find success image close and click close", "INFO")
    return True
def click_exist_mess(window, viber_channel):
    log_and_print("Find exist mrssages", "INFO")
    
    for number in range(5):
        if not gd.click_image(
            f"exist_mess{number}.png",
            scope=(245, 220, 300, 700),
            confidence=0.9,
            count_click=1,
            multiscale=True,
            plus_x=0,
            plus_y=0,
            is_debug=_ui_debug(),
        ):
            log_and_print(f"Not find exist mrssages{number}", "INFO")
            
        else:
            log_and_print("Success find and click images exist messages", "INFO")
            
            clickLastMess(window, viber_channel["name_viber_channel"])
            return True
        
    log_and_print("Not find images exist messages", "INFO")
    return False
def click_close_info():
    log_and_print("Find info", "INFO")
    if not gd.click_image(
        "info.png",
        scope=(720, 70, 800, 120),
        confidence=0.9,
        plus_y=0,
        plus_x=0,
        count_click=1,
        multiscale=True,
        is_debug=_ui_debug(),
    ):
        log_and_print("Not find icon close info, attempt 2", "INFO")
        
    log_and_print("Find success image close info and click", "INFO")
    return True
def click_open_info():
    log_and_print("Find info", "INFO")
    if not gd.click_image(
        "info.png",
        scope=(1050, 70, 1100, 120),
        confidence=0.8,
        count_click=1,
        multiscale=True,
        is_debug=_ui_debug(),
    ):
        log_and_print("Not find icon open info, attempt 2", "INFO")
        if not gd.click_image(
        "info.png",
        scope=(910, 70, 950, 120),
        confidence=0.8,
        count_click=1,
        multiscale=True,
        is_debug=_ui_debug(),
        ):
            
            log_and_print("Not find icon open info atte,pt2", "INFO")
            return False
        
    log_and_print("Find success image open info and click", "INFO")
    return True
def click_cancel_window_save_as():
    log_and_print("Find window_save_as", "INFO")
    if not gd.click_image(
        "cancel.png",
        scope=(800, 500, 1060, 580),
        confidence=0.9,
        count_click=1,
        multiscale=True,
        is_debug=_ui_debug(),
    ):
        log_and_print("Not find window_save_as - attempt 2", "INFO")
        if not gd.click_image(
            "cancel2.png",
            scope=(800, 500, 1060, 580),
            confidence=0.9,
            count_click=1,
            multiscale=True,
            is_debug=_ui_debug(),
        ):
            log_and_print("Not find window_save_as - attempt 3", "INFO")
            if not gd.click_image(
                "cancel_close.png",
                scope=(800, 20, 970, 100),
                confidence=0.8,
                count_click=1,
                multiscale=True,
                is_debug=_ui_debug(),
                ):
                    
                    log_and_print("Not find window_save_as attempt2", "INFO")
                    return False
        
    log_and_print("Find success window_save_as and click", "INFO")
    return True
async def processViberMess(
    window, s, count_scroll_up, count_scroll_down, pause_cycle_read
):
    global count_y_mess_empty
    empty_send_count = 0
    numberViberChannel = 0
    viber_channel = s.viber_channels[numberViberChannel]
    window_top_focus(window)
    
    is_center_continue()
    click_folder()
    click_close_info()
    click_cancel_window_save_as()
    if not klickViberChannel("image",window, True, viber_channel):
                log_and_print(f"Not find chat {viber_channel["name_viber_channel"]}", "INFO")
                return None
            
    log_and_print(f"click chat {viber_channel["name_viber_channel"]}", "INFO")
    gd.right_click(
        s.search_board_mess_x_start + s.x_offset_out_mess,
        s.search_board_mess_y_start + 10,
    )
    count_repeat = int(read_setting("count_repeat"))
    break_flag = False
    for i in range(count_repeat):
        while True:
            copy_stall_restart_seconds = int(read_setting("copy_stall_restart_seconds") or 3600)
            if copy_stall_restart_seconds > 0:
                idle_seconds = time.monotonic() - last_message_copy_monotonic
                if idle_seconds >= copy_stall_restart_seconds:
                    raise RuntimeError(
                        f"[copy_watchdog] no message copies for {int(idle_seconds)}s "
                        f"(limit {copy_stall_restart_seconds}s)"
                    )
            # Keep group list pane in expected state at the beginning of each reader loop.
            click_folder()
            log_and_print(f"empty_send_count: {empty_send_count}", "INFO")
            if empty_send_count > 4:
                window_top_focus(window)
                window_left(window)
                is_center_continue()
                click_folder()
                click_close_info()
                click_close_hitlite()
                click_close_image()
                scroll_with_mouse(
                                window, count_scroll=random.randint(1, 3), direction="up"
                            )
            if empty_send_count > 3:
                click_cancel_window_save_as()
                scroll_with_mouse(
                                window, count_scroll=random.randint(1, 3), direction="up"
                            )
                
            if empty_send_count > 2:
                
                if not click_exist_mess(window, viber_channel):
                    
                    if numberViberChannel + 1 >= len(s.viber_channels):
                        numberViberChannel = 0
                    else:
                        numberViberChannel = numberViberChannel + 1
                    
                    log_and_print(f"empty_send_count > 10 change channel to : {s.viber_channels[numberViberChannel]}", "INFO")
                    viber_channel = s.viber_channels[numberViberChannel]
                
                    if klickViberChannel("image", window, True, viber_channel):
                        log_and_print(f"Not find chat {viber_channel["name_viber_channel"]}", "INFO")
                        
                        empty_send_count = 0
                
                else:
                    empty_send_count = 0
                    
                
            fill_y_mess(window, viber_channel, s)
            if len(s.y_mess) > 0:
                was_send = await send_messages_from_y_mess(window, viber_channel, s)
                log_and_print(f"was_send: {was_send}", "INFO")
                if was_send != "repeat":
                    if was_send:
                        empty_send_count = 0
                        
                        scroll_with_mouse(
                            window, count_scroll=count_scroll_up, direction="up"
                        )
                    else:
                        empty_send_count += 1
                        press_esq(window)
                        clickLastMess(window, viber_channel["name_viber_channel"])
                        
            else:
                empty_send_count += 1
                window_top_focus(window)
                press_esq(window)
                is_center_ok()
                is_center_continue()
                break_flag = True
                break
            window_top_focus(window)
            
            #if not klickViberChannel("image", window, False, viber_channel):
            #    log_and_print(f"Not find chat {viber_channel["name_viber_channel"]}", "INFO")
            
            
        if break_flag:
            break
        ctypes.windll.user32.LockWindowUpdate(0)
        log_and_print(f"count_y_mess_empty = {count_y_mess_empty}")
    window_top_focus(window)
    press_esq(window)
    log_and_print(f"pause = {read_setting('pause_read_messages_second')}")
    
def window_top_focus(window):
    
    hwnd = window.handle
    # Set "always on top" flag.
    win32gui.SetWindowPos(
        hwnd,
        win32con.HWND_TOPMOST,  # above all windows
        0, 0, 0, 0,
        win32con.SWP_NOMOVE | win32con.SWP_NOSIZE
    )
    window.set_focus()
    
def window_left(window):
    hwnd = window.handle
    win32gui.ShowWindow(hwnd, win32con.SW_MAXIMIZE)
    keyboard.send_keys('{LWIN down}{LEFT}{LWIN up}')











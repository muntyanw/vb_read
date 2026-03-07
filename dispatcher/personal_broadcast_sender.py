import random
import json
import time
import math
import re
import unicodedata
from datetime import datetime
from collections import defaultdict
from difflib import SequenceMatcher
from pathlib import Path

import cv2
import pyautogui as pag
import pyperclip
from pywinauto import keyboard as win_keyboard

from core import gui_driver as gd
from dispatcher.dispatch_client import klickViberChannel, window_top_focus, click_folder
from dispatcher.message_send_logger import log_sent_message
from dispatcher.personal_broadcast_config import PersonalBroadcastConfig
from dispatcher.personal_broadcast_registry import PersonalBroadcastRegistry
from log import log_and_print
from recognize_text import perform_ocr_with_positions, preprocess_image
from utils import take_screenshot, read_setting, showImage
from vb_utils import scroll_with_mouse

def _ui_debug() -> bool:
    return bool(read_setting("debug_methods_mode"))


class PersonalBroadcastSender:
    _NON_MEMBER_WORDS = {
        "\u0443\u0447\u0430\u0441\u0442\u043d\u0438\u043a\u0438",  # участники
        "\u0443\u0447\u0430\u0441\u043d\u0438\u043a\u0438",      # учасники
        "\u0443\u0447\u0430\u043a\u043d\u0438\u043a\u0438",
        "participants",
        "\u0432\u044b",  # вы
        "you",
        "\u0437\u0430\u043f\u0440\u043e\u0441\u0438\u0442\u0438",
        "\u0437\u0430\u043f\u0440\u043e\u0441",
        "\u0437\u0430\u043f\u0430",
        "\u043d\u0435\u0438\u0437\u0432\u0435\u0441\u0442\u043d\u043e",
        "--",
    }
    _RIGHT_TEXT_MIN_GAP_PX = 110
    _BUILTIN_ROLE_KEYWORDS = {
        "admin",
        "administrator",
        "superadmin",
        "\u0430\u0434\u043c\u0438\u043d",          # админ
        "\u0430\u0434\u043c\u0438\u043d\u0438\u0441\u0442\u0440\u0430\u0442\u043e\u0440",  # администратор
        "\u0430\u0434\u043c\u0456\u043d\u0456\u0441\u0442\u0440\u0430\u0442\u043e\u0440",  # адміністратор
        "\u0441\u0443\u043f\u0435\u0440\u0430\u0434\u043c\u0438\u043d",  # суперадмин
        "\u0441\u0443\u043f\u0435\u0440\u0430\u0434\u043c\u0456\u043d",  # суперадмін
    }
    _ROLE_MARKERS = (
        "admin",
        "administrator",
        "\u0430\u0434\u043c\u0438\u043d",
        "\u0430\u0434\u043c\u0438\u043d\u0438\u0441\u0442\u0440\u0430\u0442\u043e\u0440",
        "\u0430\u0434\u043c\u0456\u043d\u0456\u0441\u0442\u0440\u0430\u0442\u043e\u0440",
        "\u0441\u0443\u043f\u0435\u0440\u0430\u0434\u043c\u0438\u043d",
        "\u0441\u0443\u043f\u0435\u0440\u0430\u0434\u043c\u0456\u043d",
    )

    _INFO_STATE_EPS = 0.015
    _INFO_CLICK_MIN_SCORE = 0.99
    _NAME_MAX_X_RATIO = 0.62
    _LAYOUT_CODE_TO_NAME = {
        0x0409: "en",
        0x0419: "ru",
        0x0422: "uk",
    }

    def __init__(self, config: PersonalBroadcastConfig):
        self._config = config
        self._registry = PersonalBroadcastRegistry(config.sent_names_file)
        self._channel_index = 0
        self._exceptions_cache: set[str] = set()
        self._exceptions_cache_mtime: float | None = None
        self._exceptions_cache_file: str | None = None
        log_and_print("[personal_broadcast] initialized", "info")

    def update_config(self, config: PersonalBroadcastConfig) -> None:
        sent_file_changed = self._config.sent_names_file != config.sent_names_file
        exceptions_file_changed = self._config.exceptions_file != config.exceptions_file
        self._config = config
        log_and_print("[personal_broadcast] config updated", "debug")
        if sent_file_changed:
            self._registry = PersonalBroadcastRegistry(config.sent_names_file)
            log_and_print(f"[personal_broadcast] registry file changed: {config.sent_names_file}", "debug")
        if exceptions_file_changed:
            self._exceptions_cache.clear()
            self._exceptions_cache_mtime = None
            self._exceptions_cache_file = None
            log_and_print(f"[personal_broadcast] exceptions file changed: {config.exceptions_file}", "debug")

    def run_once(self, window, s) -> None:
        if not self._config.enabled:
            log_and_print("[personal_broadcast] skipped: disabled by config", "debug")
            return

        self._set_startup_layout()
        click_folder()
        channel_pool = self._channel_pool(s)
        if not channel_pool:
            log_and_print("[personal_broadcast] no channels available", "error")
            return

        for _ in range(len(channel_pool)):
            channel = channel_pool[self._channel_index % len(channel_pool)]
            log_and_print(f"[personal_broadcast] start channel={channel.get('name_viber_channel')}", "debug")
            window_top_focus(window)
            if not klickViberChannel("image", window, False, channel):
                log_and_print(
                    f"[personal_broadcast] channel open failed: {channel.get('name_viber_channel')}",
                    "error",
                )
                self._channel_index = (self._channel_index + 1) % len(channel_pool)
                continue

            had_candidates = self._run_channel(window, s, channel.get("name_viber_channel", "unknown"))
            if had_candidates:
                return

            self._channel_index = (self._channel_index + 1) % len(channel_pool)
            next_channel = channel_pool[self._channel_index % len(channel_pool)]
            log_and_print(
                f"[personal_broadcast] empty users list in channel={channel.get('name_viber_channel')}, "
                f"switch to next={next_channel.get('name_viber_channel')}",
                "warning",
            )

    def _channel_pool(self, s) -> list[dict]:
        pool = []
        seen = set()
        # prefer explicit personal_broadcast channel first
        target = self._config.target_channel if isinstance(self._config.target_channel, dict) else None
        if target:
            ch_name = str(target.get("name_viber_channel") or "").strip().lower()
            if ch_name:
                pool.append(target)
                seen.add(ch_name)
        channels = getattr(s, "viber_channels", None)
        if isinstance(channels, list):
            for ch in channels:
                if not isinstance(ch, dict):
                    continue
                ch_name = str(ch.get("name_viber_channel") or "").strip().lower()
                if not ch_name or ch_name in seen:
                    continue
                pool.append(ch)
                seen.add(ch_name)
        return pool

    def _target_input_layout(self) -> str:
        raw = str(read_setting("personal_broadcast_input_layout") or "en").strip().lower()
        if raw in {"en", "ru", "uk"}:
            return raw
        return "en"

    def _load_exceptions(self) -> set[str]:
        file_path = str(self._config.exceptions_file or "").strip()
        if not file_path:
            return set()

        p = Path(file_path)
        try:
            mtime = p.stat().st_mtime
        except Exception:
            self._exceptions_cache = set()
            self._exceptions_cache_mtime = None
            self._exceptions_cache_file = file_path
            return self._exceptions_cache

        if (
            self._exceptions_cache_file == file_path
            and self._exceptions_cache_mtime == mtime
        ):
            return self._exceptions_cache

        try:
            raw = p.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            raw = ""

        tokens: list[str] = []
        for part in raw.replace("\n", ",").replace(";", ",").split(","):
            n = part.strip().lower()
            if n:
                tokens.append(n)

        self._exceptions_cache = set(tokens)
        self._exceptions_cache_mtime = mtime
        self._exceptions_cache_file = file_path
        return self._exceptions_cache

    def _is_in_exceptions(self, name: str) -> bool:
        n_raw = str(name or "").strip()
        if not n_raw:
            return False

        n_norm = self._normalize_name(n_raw).lower()
        if not n_norm:
            return False

        n_key = self._exception_norm_key(n_raw)
        n_tokens = self._exception_tokens(n_raw)

        best_ratio = 0.0
        best_exc = ""
        for exc in self._load_exceptions():
            exc_raw = str(exc or "").strip()
            if not exc_raw:
                continue

            e_norm = self._normalize_name(exc_raw).lower()
            if not e_norm:
                continue

            if n_norm == e_norm:
                return True

            e_key = self._exception_norm_key(exc_raw)
            if n_key and e_key and n_key == e_key:
                return True

            ratio = SequenceMatcher(None, n_key or n_norm, e_key or e_norm).ratio()
            if ratio > best_ratio:
                best_ratio = ratio
                best_exc = e_key or e_norm
            if ratio >= 0.78:
                return True

            e_tokens = self._exception_tokens(exc_raw)
            if self._exception_tokens_match(n_tokens, e_tokens):
                return True

        if best_ratio >= 0.62:
            log_and_print(
                f"[personal_broadcast] exceptions near-match name='{n_key or n_norm}' best='{best_exc}' ratio={best_ratio:.2f}",
                "debug",
            )
        return False

    def _set_startup_layout(self) -> None:
        target = self._target_input_layout()
        try:
            ok = gd.ensure_layout(target)
            log_and_print(f"[personal_broadcast] startup keyboard layout={target} ok={ok}", "debug")
        except Exception as exc:
            log_and_print(f"[personal_broadcast] cannot set startup layout={target}: {exc}", "error")

    def _run_channel(self, window, s, channel_name: str) -> bool:
        had_candidates_total = False
        if not self._open_participants(window):
            return False

        step = 0
        while step < self._config.max_scroll_steps:
            log_and_print(f"[personal_broadcast] scan step={step+1}/{self._config.max_scroll_steps}", "debug")
            self._dismiss_no_personal_messages_popup(scan_id=f"pre_scan_step{step+1}", context="pre_scan")
            if not self._ensure_participants_list(window):
                return
            candidates, scan_id = self._read_candidates_from_scope(channel_name=channel_name, step=step + 1)
            if candidates and step == 0:
                first_candidate = min(candidates, key=lambda c: (c["y"], c["x"]))
                top_y = int(first_candidate["y"])
                # Skip the whole first visible row only on the first scroll page.
                top_row_window = 14
                filtered = [c for c in candidates if abs(int(c["y"]) - top_y) > top_row_window]
                skipped_top = len(candidates) - len(filtered)
                candidates = filtered
                if skipped_top > 0:
                    log_and_print(
                        f"[personal_broadcast] skip top row around y={top_y}, "
                        f"skipped={skipped_top}",
                        "debug",
                    )
            if step == 0:
                before = len(candidates)
                candidates = self._dedupe_candidates_by_position(candidates)
                removed = before - len(candidates)
                if removed > 0:
                    log_and_print(
                        f"[personal_broadcast] dedupe by position removed={removed} scan_id={scan_id}",
                        "debug",
                    )
            log_and_print(f"[personal_broadcast] candidates found={len(candidates)} scan_id={scan_id}", "debug")
            sent_any = False
            raw_count = len(candidates)
            if raw_count > 0:
                had_candidates_total = True
            skip_registry = 0
            skip_gender = 0
            send_attempted = 0
            force_scroll_rescan = False
            force_rescan_same_step = False

            for candidate in candidates:
                name = candidate["name"]
                if self._registry.has(name):
                    skip_registry += 1
                    log_and_print(f"[personal_broadcast] skip already sent: {name} scan_id={scan_id}", "debug")
                    continue
                if step > 0:
                    similar = self._registry.find_similar(name, min_ratio=0.86, max_len_diff=4)
                    if similar:
                        skip_registry += 1
                        log_and_print(
                            f"[personal_broadcast] skip similar sent: {name} ~ {similar[0]} ({similar[1]:.2f}) scan_id={scan_id}",
                            "debug",
                        )
                        continue
                if not self._gender_matches(name):
                    skip_gender += 1
                    log_and_print(f"[personal_broadcast] skip gender filter: {name} scan_id={scan_id}", "debug")
                    continue

                if self._is_participants_label(name):
                    skip_registry += 1
                    log_and_print(
                        f"[personal_broadcast] skip participants label: {name} scan_id={scan_id}",
                        "debug",
                    )
                    continue

                send_attempted += 1
                send_result = self._send_to_member(window, s, candidate, channel_name, scan_id=scan_id)
                if send_result == "sent":
                    sent_any = True
                    pause = random.uniform(0, max(self._config.max_pause_seconds, 0.0))
                    time.sleep(pause)
                    if not self._back_to_group(window):
                        return had_candidates_total
                    if not self._open_participants(window):
                        return had_candidates_total
                    # After return from dialog, members list can shift/reset. Restore scroll position.
                    self._restore_scroll_position(window, step)
                    # Re-scan immediately instead of using stale candidates from old screenshot.
                    break
                elif send_result == "recover":
                    log_and_print(
                        f"[personal_broadcast] recover participants list after '{name}' scan_id={scan_id}",
                        "warning",
                    )
                    if not self._open_participants(window):
                        log_and_print(
                            "[personal_broadcast] participants reopen failed; scroll and rescan without return-to-group",
                            "warning",
                        )
                        force_scroll_rescan = True
                        break
                    # Participants list may visually shift after recover; old candidate coordinates become stale.
                    force_rescan_same_step = True
                    break
                else:
                    log_and_print(
                        f"[personal_broadcast] skip candidate without recovery: '{name}' scan_id={scan_id}",
                        "debug",
                    )

            after_registry = raw_count - skip_registry
            after_gender = after_registry - skip_gender
            log_and_print(
                f"[personal_broadcast] candidate pipeline raw={raw_count} "
                f"after_registry={after_registry} after_gender={after_gender} "
                f"send_attempted={send_attempted} scan_id={scan_id}",
                "debug",
            )

            if sent_any:
                log_and_print("[personal_broadcast] message sent, refresh members screenshot", "debug")
                continue
            if force_rescan_same_step:
                log_and_print("[personal_broadcast] recover completed; rescan current step with fresh coordinates", "debug")
                continue
            if force_scroll_rescan:
                log_and_print("[personal_broadcast] force scroll after participants reopen failure", "debug")
            else:
                log_and_print("[personal_broadcast] no candidate sent, scroll down", "debug")
            self._handle_same_one_before_scroll(window)
            self._scroll_members_down(window)
            gd.pause(1.5)
            step += 1

        log_and_print(f"[personal_broadcast] no more candidates in {channel_name}", "info")
        self._back_to_group(window)
        return had_candidates_total


    def _handle_same_one_before_scroll(self, window) -> None:
        """If same_one banner exists, click it and wait until it disappears."""
        try:
            scope = self._config.members_scope
            left = int(scope[0])
            right = int(scope[0] + scope[2])

            # Exclude top header area (where "??????????" causes false positives).
            top = int(scope[1] + min(220, max(120, int(scope[3] * 0.28))))
            bottom = int(scope[1] + max(top - int(scope[1]) + 40, int(scope[3] * 0.72)))
            same_scope = (left, top, right, bottom)
        except Exception:
            same_scope = None

        while True:
            try:
                found = gd.find_image(
                    "same_one.png",
                    timeout=0.4,
                    confidence=0.8,
                    scope=same_scope,
                    multiscale=True,
                    is_debug=_ui_debug(),
                )
            except Exception:
                found = None

            if not found:
                return

            # Guard against false positives on right-side purple action buttons.
            try:
                fx, fy = int(found[0]), int(found[1])
            except Exception:
                return

            if same_scope is not None:
                sl, st, sr, sb = [int(v) for v in same_scope]
                sw = max(1, sr - sl)
                # "same_one" pill is usually in the central area; rightmost area is often send/chat button.
                allowed_left = int(sl + sw * 0.20)
                allowed_right = int(sl + sw * 0.72)
                if fx < allowed_left or fx > allowed_right:
                    log_and_print(
                        f"[personal_broadcast] ignore same_one false-positive at x={fx}, y={fy}; "
                        f"allowed_x=[{allowed_left},{allowed_right}] scope={same_scope}",
                        "debug",
                    )
                    return

            log_and_print(
                f"[personal_broadcast] same_one detected before scroll, click and wait 60s scope={same_scope}",
                "warning",
            )
            try:
                window.set_focus()
            except Exception:
                pass
            try:
                gd.click(fx, fy)
            except Exception:
                pass
            gd.pause(60.0)

    def _restore_scroll_position(self, window, steps: int) -> None:
        if steps <= 0:
            return
        self._handle_same_one_before_scroll(window)
        log_and_print(f"[personal_broadcast] restore scroll position steps={steps}", "debug")
        for i in range(int(steps)):
            # Heavy UIA wheel fallback is needed only for the first jump.
            self._scroll_members_down(window, use_mouse_fallback=(i == 0))

    def _scroll_members_down(self, window, use_mouse_fallback: bool = True) -> None:
        """
        Strong scroll in members list (similar power to dispatch_client scrolling).
        """
        scope = self._config.members_scope
        # scope is (x, y, w, h)
        cx = int(scope[0] + scope[2] // 2)
        cy = int(scope[1] + scope[3] // 2)
        window.set_focus()
        log_and_print(f"[personal_broadcast] scroll members at x={cx}, y={cy}", "debug")
        gd.human_move(cx, cy)
        gd.pause(0.05)
        # Large wheel distance. UIA mouse-scroll fallback is expensive; use only when requested.
        gd.scroll(-2600)
        gd.pause(0.08)
        gd.scroll(-2600)
        gd.pause(0.08)
        if use_mouse_fallback:
            scroll_with_mouse(window, count_scroll=6, direction="down")

    def _open_participants(self, window) -> bool:
        for attempt in range(1, 4):
            window.set_focus()
            state, score_unselect, score_info = self._detect_info_icon_state()
            log_and_print(
                f"[personal_broadcast] info state attempt={attempt}/3 "
                f"state={state} score_unselect={score_unselect:.3f} score_info={score_info:.3f}",
                "debug",
            )
            self._save_info_search_snapshot(state, score_unselect, score_info, attempt)

            should_click_info = state == "closed" and score_unselect >= self._INFO_CLICK_MIN_SCORE
            if should_click_info:
                log_and_print(
                    f"[personal_broadcast] click info image={self._config.open_info_image}, "
                    f"scope={self._config.open_info_scope} attempt={attempt}/3",
                    "debug",
                )
                info_scope = self._config.open_info_scope
                clicked_info = self._click_image_with_optional_color_hint(
                    self._config.open_info_image,
                    scope=info_scope,
                    confidence=0.80,
                    use_purple_hint=True,
                    scan_id=f"info_attempt{attempt}",
                    fallback_plain=False,
                    fallback_confidence=0.72,
                )
                if not clicked_info:
                    log_and_print("[personal_broadcast] info image not found for click", "warning")
                    self._save_info_search_snapshot(state, score_unselect, score_info, attempt)
                gd.pause(0.6)
            else:
                log_and_print(
                    "[personal_broadcast] skip info click (not confidently closed or score too low)",
                    "debug",
                )

            if self._click_participants_text():
                gd.pause(2.0)
                return True

            log_and_print(
                f"[personal_broadcast] participants text not found, retry open info attempt={attempt}/3",
                "warning",
            )
            gd.pause(0.8)

        log_and_print("[personal_broadcast] cannot click participants", "error")
        return False

    def _click_participants_text(self) -> bool:
        log_and_print(
            f"[personal_broadcast] click participants text in scope={self._config.participants_click_scope}",
            "debug",
        )
        gd.pause(1.0)
        return bool(
            gd.click_text(
                self._config.participants_texts,
                count_attempt_find=2,
                pause_attempt=1,
                lang="ukr",
                scope=self._config.participants_click_scope,
                threshold=0.6,
                is_debug=_ui_debug(),
                count_click=1,
            )
        )

    def _save_info_search_snapshot(
        self,
        state: str,
        score_unselect: float,
        score_info: float,
        attempt: int,
        click_xy: tuple[int, int] | None = None,
    ) -> str | None:
        if not _ui_debug():
            return None
        scope = self._config.open_info_scope
        if scope is None:
            return None
        try:
            left, top, right, bottom = [int(v) for v in scope]
            width = max(1, right - left)
            height = max(1, bottom - top)
            snap_rgb = take_screenshot((left, top, width, height))
            bgr = cv2.cvtColor(snap_rgb, cv2.COLOR_RGB2BGR)

            label = (
                f"state={state} unselect={score_unselect:.3f} "
                f"info={score_info:.3f} attempt={attempt}"
            )
            cv2.putText(
                bgr,
                label[:120],
                (6, 18),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.45,
                (0, 255, 255),
                1,
                cv2.LINE_AA,
            )
            if click_xy is not None:
                cx, cy = int(click_xy[0]), int(click_xy[1])
                lx = max(0, min(width - 1, cx - left))
                ly = max(0, min(height - 1, cy - top))
                cv2.circle(bgr, (lx, ly), 6, (0, 0, 255), -1)
                cv2.putText(
                    bgr,
                    f"click=({cx},{cy})",
                    (6, 36),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.45,
                    (0, 180, 255),
                    1,
                    cv2.LINE_AA,
                )

            out_dir = Path(__file__).resolve().parents[1] / "temp_log"
            out_dir.mkdir(parents=True, exist_ok=True)
            ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
            path = out_dir / f"pb_info_state_attempt{int(attempt)}_{ts}.png"
            cv2.imwrite(str(path), bgr)
            log_and_print(f"[personal_broadcast] info snapshot: {path}", "debug")
            return str(path)
        except Exception as exc:
            log_and_print(f"[personal_broadcast] info snapshot save failed: {exc}", "warning")
            return None

    def _detect_info_icon_state(self) -> tuple[str, float, float]:
        """
        Returns (state, score_unselect, score_info):
        - state=open: info.png is more similar (info panel likely already opened)
        - state=closed: info_unselect.png is more similar
        - state=unknown: similarity is too close or templates not available
        """
        scope = self._config.open_info_scope
        if scope is None:
            return "unknown", -1.0, -1.0

        score_unselect = self._template_score_in_scope(self._config.open_info_image, scope)
        score_info = self._template_score_in_scope("info.png", scope)

        if score_unselect < 0 and score_info < 0:
            return "unknown", score_unselect, score_info
        if score_info > score_unselect + self._INFO_STATE_EPS:
            return "open", score_unselect, score_info
        if score_unselect > score_info + self._INFO_STATE_EPS:
            return "closed", score_unselect, score_info
        return "unknown", score_unselect, score_info

    def _template_score_in_scope(self, image_name: str, scope: tuple[int, int, int, int]) -> float:
        path = self._resolve_template_path(image_name)
        if path is None:
            return -1.0

        left, bottom, right, top = [int(v) for v in scope]
        width = max(1, right - left)
        height = max(1, top - bottom)
        snap_rgb = take_screenshot((left, bottom, width, height))
        snap_bgr = cv2.cvtColor(snap_rgb, cv2.COLOR_RGB2BGR)

        tpl = cv2.imread(str(path), cv2.IMREAD_UNCHANGED)
        if tpl is None:
            return -1.0

        mask = None
        if tpl.ndim == 3 and tpl.shape[2] == 4:
            alpha = tpl[:, :, 3]
            _, mask = cv2.threshold(alpha, 0, 255, cv2.THRESH_BINARY)
            tpl_bgr = cv2.cvtColor(tpl, cv2.COLOR_BGRA2BGR)
            # For info icons we must keep white background in matching; 
            # alpha-only mask causes false positives on right black sidebar.
            if "info" in str(image_name).lower():
                mask = None
        elif tpl.ndim == 3:
            tpl_bgr = tpl
        else:
            tpl_bgr = cv2.cvtColor(tpl, cv2.COLOR_GRAY2BGR)

        ih, iw = snap_bgr.shape[:2]
        th, tw = tpl_bgr.shape[:2]
        if th < 1 or tw < 1 or th > ih or tw > iw:
            return -1.0

        if mask is not None:
            res = cv2.matchTemplate(snap_bgr, tpl_bgr, cv2.TM_CCORR_NORMED, mask=mask)
            _, max_val, _, _ = cv2.minMaxLoc(res)
            max_val = float(max_val)
            if math.isfinite(max_val):
                return max_val
            log_and_print(
                f"[personal_broadcast] non-finite template score for {image_name} with alpha mask; fallback to gray matching",
                "warning",
            )

        img_gray = cv2.cvtColor(snap_bgr, cv2.COLOR_BGR2GRAY)
        tpl_gray = cv2.cvtColor(tpl_bgr, cv2.COLOR_BGR2GRAY)
        res = cv2.matchTemplate(img_gray, tpl_gray, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, _ = cv2.minMaxLoc(res)
        max_val = float(max_val)
        if not math.isfinite(max_val):
            return -1.0
        return max_val


    @staticmethod
    def _purple_icon_color_score(roi_bgr) -> tuple[float, bool]:
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

    def _find_template_match_in_scope(
        self,
        image_name: str,
        scope: tuple[int, int, int, int],
        *,
        use_purple_hint: bool = False,
        min_tm_score: float = 0.72,
    ) -> dict | None:
        path = self._resolve_template_path(image_name)
        if path is None:
            return None

        left, top, right, bottom = [int(v) for v in scope]
        width = max(1, right - left)
        height = max(1, bottom - top)
        snap_rgb = take_screenshot((left, top, width, height))
        snap_bgr = cv2.cvtColor(snap_rgb, cv2.COLOR_RGB2BGR)

        tpl = cv2.imread(str(path), cv2.IMREAD_UNCHANGED)
        if tpl is None:
            return None

        if tpl.ndim == 3 and tpl.shape[2] == 4:
            alpha = tpl[:, :, 3]
            _, mask = cv2.threshold(alpha, 0, 255, cv2.THRESH_BINARY)
            tpl_bgr = cv2.cvtColor(tpl, cv2.COLOR_BGRA2BGR)
            # For info icons we must match with full patch (incl. white background).
            if "info" in str(image_name).lower():
                mask = None
        elif tpl.ndim == 3:
            tpl_bgr = tpl
            mask = None
        else:
            tpl_bgr = cv2.cvtColor(tpl, cv2.COLOR_GRAY2BGR)
            mask = None

        ih, iw = snap_bgr.shape[:2]
        th0, tw0 = tpl_bgr.shape[:2]
        if th0 < 1 or tw0 < 1 or th0 > ih or tw0 > iw:
            return None

        best = None
        scales = [0.92, 0.96, 1.00, 1.04, 1.08]
        for sc in scales:
            tw = max(1, int(round(tw0 * sc)))
            th = max(1, int(round(th0 * sc)))
            if tw > iw or th > ih:
                continue
            interp = cv2.INTER_AREA if sc < 1.0 else cv2.INTER_LINEAR
            tpl_s = cv2.resize(tpl_bgr, (tw, th), interpolation=interp)
            mask_s = None
            if mask is not None:
                mask_s = cv2.resize(mask, (tw, th), interpolation=cv2.INTER_NEAREST)

            if mask_s is not None:
                res = cv2.matchTemplate(snap_bgr, tpl_s, cv2.TM_CCORR_NORMED, mask=mask_s)
            else:
                img_gray = cv2.cvtColor(snap_bgr, cv2.COLOR_BGR2GRAY)
                tpl_gray = cv2.cvtColor(tpl_s, cv2.COLOR_BGR2GRAY)
                img_gray = cv2.GaussianBlur(img_gray, (3, 3), 0)
                tpl_gray = cv2.GaussianBlur(tpl_gray, (3, 3), 0)
                res = cv2.matchTemplate(img_gray, tpl_gray, cv2.TM_CCOEFF_NORMED)

            _, max_val, _, max_loc = cv2.minMaxLoc(res)
            tm_score = float(max_val)
            if not math.isfinite(tm_score):
                log_and_print(
                    f"[personal_broadcast] non-finite tm score image={image_name} scale={sc:.2f}",
                    "warning",
                )
                continue
            if tm_score < float(min_tm_score):
                continue

            x, y = int(max_loc[0]), int(max_loc[1])
            roi = snap_bgr[y:y + th, x:x + tw]
            color_score, color_ok = self._purple_icon_color_score(roi)
            final_score = tm_score
            if use_purple_hint:
                final_score = (0.78 * tm_score) + (0.22 * float(color_score))
            if not math.isfinite(float(final_score)):
                continue

            cand = {
                "x": x,
                "y": y,
                "w": int(tw),
                "h": int(th),
                "tm_score": tm_score,
                "color_score": float(color_score),
                "color_ok": bool(color_ok),
                "final_score": float(final_score),
                "abs_center": (int(left + x + (tw // 2)), int(top + y + (th // 2))),
            }
            if best is None or cand["final_score"] > best["final_score"]:
                best = cand

        return best

    def _save_scope_click_snapshot(self, scope: tuple[int, int, int, int], click_xy: tuple[int, int], tag: str) -> str | None:
        try:
            left, top, right, bottom = [int(v) for v in scope]
            width = max(1, right - left)
            height = max(1, bottom - top)
            snap_rgb = take_screenshot((left, top, width, height))
            bgr = cv2.cvtColor(snap_rgb, cv2.COLOR_RGB2BGR)
            cx, cy = int(click_xy[0]), int(click_xy[1])
            lx = max(0, min(width - 1, cx - left))
            ly = max(0, min(height - 1, cy - top))
            cv2.circle(bgr, (lx, ly), 6, (0, 0, 255), -1)
            cv2.putText(bgr, f"click=({cx},{cy})", (6, 18), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 180, 255), 1, cv2.LINE_AA)
            out_dir = Path(__file__).resolve().parents[1] / "temp_log"
            out_dir.mkdir(parents=True, exist_ok=True)
            ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
            safe_tag = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in str(tag or "scope_click"))
            path = out_dir / f"{safe_tag}_{ts}.png"
            cv2.imwrite(str(path), bgr)
            log_and_print(f"[personal_broadcast] click snapshot: {path}", "debug")
            return str(path)
        except Exception as exc:
            log_and_print(f"[personal_broadcast] click snapshot save failed: {exc}", "warning")
            return None

    def _click_image_with_optional_color_hint(
        self,
        image_name: str,
        scope: tuple[int, int, int, int],
        *,
        confidence: float,
        use_purple_hint: bool = False,
        scan_id: str = "na",
        fallback_plain: bool = True,
        fallback_confidence: float = 0.75,
    ) -> bool:
        # Default path: existing click_image behavior.
        if not use_purple_hint:
            return bool(
                gd.click_image(
                    image_name,
                    scope=scope,
                    confidence=confidence,
                    count_click=1,
                    multiscale=False,
                    is_debug=_ui_debug(),
                )
            )

        # Enhanced path: template + purple color-weighted scoring (like last_mess logic).
        m = self._find_template_match_in_scope(
            image_name,
            scope,
            use_purple_hint=True,
            min_tm_score=max(0.66, float(confidence) - 0.16),
        )
        if not m:
            if fallback_plain:
                pos = gd.find_image(
                    image_name,
                    timeout=8.0,
                    confidence=float(fallback_confidence),
                    scope=scope,
                    is_debug=_ui_debug(),
                    multiscale=True,
                )
                if pos:
                    click_xy = (int(pos[0]), int(pos[1]))
                    gd.click(click_xy[0], click_xy[1])
                    if _ui_debug() and str(scan_id).startswith("info_attempt"):
                        self._save_scope_click_snapshot(scope, click_xy, tag=f"pb_info_click_{scan_id}_fallback")
                    return True
                return False
            return False

        if float(m["final_score"]) < float(confidence):
            log_and_print(
                f"[personal_broadcast] color-hint match below confidence image={image_name} "
                f"final={m['final_score']:.3f} tm={m['tm_score']:.3f} color={m['color_score']:.3f} "
                f"scope={scope} scan_id={scan_id}",
                "debug",
            )
            if fallback_plain:
                pos = gd.find_image(
                    image_name,
                    timeout=8.0,
                    confidence=float(fallback_confidence),
                    scope=scope,
                    is_debug=_ui_debug(),
                    multiscale=True,
                )
                if pos:
                    click_xy = (int(pos[0]), int(pos[1]))
                    gd.click(click_xy[0], click_xy[1])
                    if _ui_debug() and str(scan_id).startswith("info_attempt"):
                        self._save_scope_click_snapshot(scope, click_xy, tag=f"pb_info_click_{scan_id}_fallback")
                    return True
                return False
            return False

        click_xy = (int(m["abs_center"][0]), int(m["abs_center"][1]))
        gd.click(click_xy[0], click_xy[1])
        log_and_print(
            f"[personal_broadcast] color-hint click image={image_name} "
            f"final={m['final_score']:.3f} tm={m['tm_score']:.3f} color={m['color_score']:.3f} "
            f"scope={scope} scan_id={scan_id}",
            "debug",
        )
        if _ui_debug() and str(scan_id).startswith("info_attempt"):
            self._save_scope_click_snapshot(scope, click_xy, tag=f"pb_info_click_{scan_id}")
        return True

    def _template_score_in_scope_edges(self, image_name: str, scope: tuple[int, int, int, int]) -> float:
        path = self._resolve_template_path(image_name)
        if path is None:
            return -1.0

        left, top, right, bottom = [int(v) for v in scope]
        width = max(1, right - left)
        height = max(1, bottom - top)
        snap_rgb = take_screenshot((left, top, width, height))
        snap_bgr = cv2.cvtColor(snap_rgb, cv2.COLOR_RGB2BGR)

        tpl = cv2.imread(str(path), cv2.IMREAD_UNCHANGED)
        if tpl is None:
            return -1.0
        if tpl.ndim == 3 and tpl.shape[2] == 4:
            tpl_bgr = cv2.cvtColor(tpl, cv2.COLOR_BGRA2BGR)
        elif tpl.ndim == 3:
            tpl_bgr = tpl
        else:
            tpl_bgr = cv2.cvtColor(tpl, cv2.COLOR_GRAY2BGR)

        ih, iw = snap_bgr.shape[:2]
        th, tw = tpl_bgr.shape[:2]
        if th < 1 or tw < 1 or th > ih or tw > iw:
            return -1.0

        snap_gray = cv2.cvtColor(snap_bgr, cv2.COLOR_BGR2GRAY)
        tpl_gray = cv2.cvtColor(tpl_bgr, cv2.COLOR_BGR2GRAY)
        snap_edges = cv2.Canny(snap_gray, 50, 140)
        tpl_edges = cv2.Canny(tpl_gray, 50, 140)
        if int(cv2.countNonZero(tpl_edges)) < 20:
            return -1.0

        res = cv2.matchTemplate(snap_edges, tpl_edges, cv2.TM_CCORR_NORMED)
        _, max_val, _, _ = cv2.minMaxLoc(res)
        return float(max_val)

    def _template_score_in_scope_glyph(self, image_name: str, scope: tuple[int, int, int, int]) -> float:
        """
        Template score using only bright low-saturation pixels (white glyph),
        which separates send arrow from microphone better than full-icon matching.
        """
        path = self._resolve_template_path(image_name)
        if path is None:
            return -1.0

        left, top, right, bottom = [int(v) for v in scope]
        width = max(1, right - left)
        height = max(1, bottom - top)
        snap_rgb = take_screenshot((left, top, width, height))
        snap_bgr = cv2.cvtColor(snap_rgb, cv2.COLOR_RGB2BGR)

        tpl = cv2.imread(str(path), cv2.IMREAD_UNCHANGED)
        if tpl is None:
            return -1.0
        if tpl.ndim == 3 and tpl.shape[2] == 4:
            tpl_bgr = cv2.cvtColor(tpl, cv2.COLOR_BGRA2BGR)
        elif tpl.ndim == 3:
            tpl_bgr = tpl
        else:
            tpl_bgr = cv2.cvtColor(tpl, cv2.COLOR_GRAY2BGR)

        ih, iw = snap_bgr.shape[:2]
        th, tw = tpl_bgr.shape[:2]
        if th < 1 or tw < 1 or th > ih or tw > iw:
            return -1.0

        hsv = cv2.cvtColor(tpl_bgr, cv2.COLOR_BGR2HSV)
        glyph_mask = cv2.inRange(hsv, (0, 0, 170), (179, 70, 255))
        if int(cv2.countNonZero(glyph_mask)) < 20:
            g = cv2.cvtColor(tpl_bgr, cv2.COLOR_BGR2GRAY)
            edges = cv2.Canny(g, 60, 140)
            glyph_mask = cv2.threshold(edges, 0, 255, cv2.THRESH_BINARY)[1]
            if int(cv2.countNonZero(glyph_mask)) < 20:
                return -1.0

        img_gray = cv2.cvtColor(snap_bgr, cv2.COLOR_BGR2GRAY)
        tpl_gray = cv2.cvtColor(tpl_bgr, cv2.COLOR_BGR2GRAY)
        res = cv2.matchTemplate(img_gray, tpl_gray, cv2.TM_CCORR_NORMED, mask=glyph_mask)
        _, max_val, _, _ = cv2.minMaxLoc(res)
        return float(max_val)

    @staticmethod
    def _resolve_template_path(image_name: str) -> Path | None:
        p = Path(str(image_name))
        candidates = [
            p,
            Path.cwd() / p,
            Path.cwd() / "images" / p.name,
            Path(__file__).resolve().parents[1] / "images" / p.name,
        ]
        for c in candidates:
            if c.exists():
                return c
        return None

    def _ensure_participants_list(self, window) -> bool:
        window.set_focus()
        clicked = gd.click_text(
            self._config.participants_texts,
            count_attempt_find=1,
            pause_attempt=0.2,
            lang="ukr",
            scope=self._config.participants_click_scope,
            threshold=0.6,
            is_debug=_ui_debug(),
            count_click=1,
        )
        if clicked:
            log_and_print("[personal_broadcast] participants label visible; open participants list", "debug")
            gd.pause(0.6)
        return True

    def _scan_meta_path(self, scan_id: str) -> Path:
        out_dir = Path(__file__).resolve().parents[1] / "temp_log"
        return out_dir / f"{scan_id}.json"

    def _update_scan_metadata(self, scan_id: str, **fields) -> None:
        try:
            meta_path = self._scan_meta_path(scan_id)
            if meta_path.exists():
                data = json.loads(meta_path.read_text(encoding="utf-8"))
            else:
                data = {"scan_id": scan_id}
            for k, v in fields.items():
                data[k] = v
            meta_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as e:
            log_and_print(f"[personal_broadcast] metadata update failed scan_id={scan_id}: {e}", "error")

    def _save_scan_snapshot(self, image_np, channel_name: str, step: int, scope: tuple[int, int, int, int]) -> tuple[str, str | None]:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        safe_channel = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in str(channel_name or "unknown"))
        scan_id = f"pb_{safe_channel}_step{int(step):03d}_{ts}"
        try:
            out_dir = Path(__file__).resolve().parents[1] / "temp_log"
            out_dir.mkdir(parents=True, exist_ok=True)
            image_path = out_dir / f"{scan_id}.png"
            meta_path = out_dir / f"{scan_id}.json"

            # take_screenshot returns RGB; cv2.imwrite expects BGR
            image_bgr = cv2.cvtColor(image_np, cv2.COLOR_RGB2BGR)
            cv2.imwrite(str(image_path), image_bgr)

            meta = {
                "scan_id": scan_id,
                "channel": str(channel_name or "unknown"),
                "step": int(step),
                "scope": [int(scope[0]), int(scope[1]), int(scope[2]), int(scope[3])],
                "saved_at": datetime.now().isoformat(timespec="seconds"),
                "image": str(image_path.resolve()),
                "cwd": str(Path.cwd()),
            }
            meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

            log_and_print(f"[personal_broadcast] snapshot saved scan_id={scan_id} image={image_path}", "debug")
            return scan_id, str(image_path)
        except Exception as e:
            log_and_print(f"[personal_broadcast] snapshot save failed scan_id={scan_id}: {e}", "error")
            return scan_id, None


    def _save_dialog_action_snapshot(
        self,
        scope: tuple[int, int, int, int],
        reason: str,
        state: str | None = None,
        send_score: float | None = None,
        mic_score: float | None = None,
        scan_id: str | None = None,
        member_name: str | None = None,
    ) -> None:
        try:
            left, top, right, bottom = [int(v) for v in scope]
            width = max(1, right - left)
            height = max(1, bottom - top)
            snap = take_screenshot((left, top, width, height))

            ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
            safe_reason = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in str(reason or "unknown"))
            safe_name = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in str(member_name or "unknown"))
            if len(safe_name) > 40:
                safe_name = safe_name[:40]
            sid = str(scan_id or "na")

            out_dir = Path(__file__).resolve().parents[1] / "temp_log"
            out_dir.mkdir(parents=True, exist_ok=True)
            image_path = out_dir / f"pb_dialog_{safe_reason}_{safe_name}_{sid}_{ts}.png"
            meta_path = out_dir / f"pb_dialog_{safe_reason}_{safe_name}_{sid}_{ts}.json"

            snap_bgr = cv2.cvtColor(snap, cv2.COLOR_RGB2BGR)
            cv2.imwrite(str(image_path), snap_bgr)

            meta = {
                "reason": str(reason or "unknown"),
                "state": str(state or ""),
                "send_score": None if send_score is None else float(send_score),
                "mic_score": None if mic_score is None else float(mic_score),
                "member_name": str(member_name or ""),
                "scan_id": sid,
                "scope": [int(left), int(top), int(right), int(bottom)],
                "saved_at": datetime.now().isoformat(timespec="seconds"),
                "image": str(image_path.resolve()),
                "cwd": str(Path.cwd()),
            }
            meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
            log_and_print(
                f"[personal_broadcast] dialog snapshot saved reason={reason} image={image_path} scan_id={sid}",
                "debug",
            )
        except Exception as e:
            log_and_print(f"[personal_broadcast] dialog snapshot save failed reason={reason}: {e}", "error")


    def _dedupe_candidates_by_position(self, candidates: list[dict], max_dx: int = 70, max_dy: int = 16) -> list[dict]:
        if not candidates:
            return []

        def _quality(name: str) -> float:
            text = str(name or "")
            cyr = sum(1 for ch in text if (0x0400 <= ord(ch.lower()) <= 0x04FF) or (ch.lower() in {"?", "?", "?", "?"}))
            lat = sum(1 for ch in text if "a" <= ch.lower() <= "z")
            q = min(len(text), 24) * 1.2
            q += min(cyr, 12) * 1.8
            if lat > 0 and cyr == 0:
                q -= 3.0
            return q

        kept = []
        for c in sorted(candidates, key=lambda x: (int(x.get("y", 0)), int(x.get("x", 0)))):
            cx = int(c.get("x", 0))
            cy = int(c.get("y", 0))
            found_index = None
            for i, k in enumerate(kept):
                kx = int(k.get("x", 0))
                ky = int(k.get("y", 0))
                if abs(cy - ky) <= max_dy and abs(cx - kx) <= max_dx:
                    found_index = i
                    break
            if found_index is None:
                kept.append(c)
                continue

            cur_q = _quality(c.get("name", ""))
            prev_q = _quality(kept[found_index].get("name", ""))
            if cur_q > prev_q:
                kept[found_index] = c
        return kept


    def _is_participants_label(self, name: str) -> bool:
        raw = "".join(ch for ch in str(name or "").strip().lower() if ch.isalnum())
        if not raw:
            return False
        labels = [str(x).strip().lower() for x in (self._config.participants_texts or []) if str(x).strip()]
        labels += ["????????", "?????????", "participants"]
        for label in labels:
            norm = "".join(ch for ch in label if ch.isalnum())
            if not norm:
                continue
            if raw == norm or raw in norm or norm in raw:
                return True
        if raw.startswith("??") and ("?????" in raw or "????" in raw):
            return True
        if raw.startswith("?????") or raw.startswith("????") or raw.startswith("participant"):
            return True
        return False

    def _read_candidates_from_scope(self, channel_name: str, step: int) -> tuple[list[dict], str]:
        skip_stats = {"role_line": 0, "role_label": 0, "no_avatar": 0, "bad_token": 0, "short_name": 0}
        scope = self._config.members_scope
        log_and_print(f"[personal_broadcast] OCR scope={scope}", "debug")
        gd.pause(1.0)
        img = take_screenshot(scope)
        scan_id, _snapshot_path = self._save_scan_snapshot(img, channel_name=channel_name, step=step, scope=scope)
        processed = preprocess_image(img)
        img_up = cv2.resize(img, None, fx=2.0, fy=2.0, interpolation=cv2.INTER_CUBIC)
        processed_up = preprocess_image(img_up)
        circles = self._detect_avatar_circles(img)
        log_and_print(f"[personal_broadcast] avatar circles={len(circles)}", "debug")
        if _ui_debug():
            # quick preview for debug mode without stopping the loop
            showImage(img, 0, title=f"[personal_broadcast] OCR raw scope={scope}")
            showImage(processed, 0, title=f"[personal_broadcast] OCR processed scope={scope}")
        langs = self._ocr_lang_variants()
        seq_processed = []
        seq_raw = []
        seq_up_processed = []
        seq_up_raw = []

        for lang in langs:
            seq_processed.append(perform_ocr_with_positions(processed, min_conf=35, lang=lang))
            seq_raw.append(perform_ocr_with_positions(img, min_conf=35, lang=lang))
            seq_up_processed.append(self._ocr_words_with_scale(processed_up, scale=2.0, min_conf=38, lang=lang))
            seq_up_raw.append(self._ocr_words_with_scale(img_up, scale=2.0, min_conf=38, lang=lang))

        words = []
        seen = set()

        def _merge_words(seq):
            added_local = 0
            for w in seq:
                key = (str(w.get("text", "")), int(w.get("left", 0)), int(w.get("top", 0)))
                if key in seen:
                    continue
                seen.add(key)
                words.append(w)
                added_local += 1
            return added_local

        added_total = 0
        for pack in (seq_processed, seq_raw, seq_up_processed, seq_up_raw):
            for seq in pack:
                added_total += _merge_words(seq)

        if added_total > 0:
            total_raw = sum(len(x) for x in seq_raw)
            total_up = sum(len(x) for x in seq_up_processed) + sum(len(x) for x in seq_up_raw)
            total_proc = sum(len(x) for x in seq_processed)
            log_and_print(
                f"[personal_broadcast] OCR merged 3lang raw+processed+upscaled: "
                f"proc={total_proc} raw={total_raw} up={total_up} "
                f"unique={len(words)} scan_id={scan_id}",
                "debug",
            )
        if not words:
            self._update_scan_metadata(
                scan_id,
                ocr_words_count=0,
                avatar_circles_count=len(circles),
                skip_stats=skip_stats,
                candidates_count=0,
                candidates=[],
            )
            log_and_print(f"[personal_broadcast] OCR returned 0 words scan_id={scan_id}", "debug")
            return [], scan_id

        lines = defaultdict(list)
        for w in words:
            key = int(w["top"] / max(self._config.line_top_tolerance, 1))
            lines[key].append(w)

        candidates = []
        for _, line_words in lines.items():
            line_words.sort(key=lambda x: x["left"])
            line_text = " ".join(str(w["text"]).strip() for w in line_words if str(w["text"]).strip())
            if not line_text:
                continue
            low = line_text.lower()
            role_keywords = set(self._config.role_keywords) | self._BUILTIN_ROLE_KEYWORDS
            if any(role in low for role in role_keywords):
                skip_stats["role_line"] += 1
                log_and_print(f"[personal_broadcast] role detected, skip line='{line_text}' scan_id={scan_id}", "debug")
                continue

            token_candidates = []
            for w in line_words:
                token_raw = str(w.get("text", "")).strip()
                if not token_raw:
                    continue
                token_norm = self._normalize_name(token_raw)
                if not self._is_member_name_token(token_norm):
                    continue
                token_candidates.append(
                    {
                        "raw": token_raw,
                        "norm": token_norm,
                        "left": int(w.get("left", 0)),
                        "top": int(w.get("top", 0)),
                        "width": int(w.get("width", 0)),
                        "height": int(w.get("height", 0)),
                        "conf": float(w.get("conf", 0.0)),
                        "word": w,
                    }
                )

            if not token_candidates:
                skip_stats["bad_token"] += 1
                continue

            # Group tokens by close X positions and pick one best token per visual slot.
            bins = []
            for t in sorted(token_candidates, key=lambda x: (x["left"], -x["conf"])):
                placed = False
                for b in bins:
                    if abs(int(t["left"]) - int(b["x"])) <= 18:
                        b["items"].append(t)
                        # keep running center close to observed values
                        b["x"] = int(round((float(b["x"]) + float(t["left"])) / 2.0))
                        placed = True
                        break
                if not placed:
                    bins.append({"x": int(t["left"]), "items": [t]})

            selected = []
            for b in bins:
                best = None
                best_score = -1e9
                for t in b["items"]:
                    norm = str(t["norm"])
                    has_cyr = any((0x0400 <= ord(ch.lower()) <= 0x04FF) or (ch.lower() in {"?", "?", "?", "?"}) for ch in norm)
                    has_lat = any("a" <= ch.lower() <= "z" for ch in norm)
                    score = float(t["conf"])
                    score += min(len(norm), 14) * 1.4
                    if has_cyr:
                        score += 10.0
                    if has_lat and not has_cyr:
                        score -= 3.0
                    raw = str(t["raw"])
                    if raw and raw[0].isupper():
                        score += 2.0
                    if score > best_score:
                        best_score = score
                        best = t
                if best is not None:
                    selected.append(best)

            if not selected:
                skip_stats["bad_token"] += 1
                continue

            selected.sort(key=lambda x: x["left"])

            # Drop repeated/near-duplicate neighbor tokens caused by OCR variants.
            compact = []
            for t in selected:
                n = str(t["norm"]).lower()
                if not compact:
                    compact.append(t)
                    continue
                prev = compact[-1]
                pn = str(prev["norm"]).lower()
                if n == pn:
                    if float(t["conf"]) > float(prev["conf"]):
                        compact[-1] = t
                    continue
                if n in pn or pn in n:
                    short = min(len(n), len(pn))
                    long = max(len(n), len(pn))
                    if short >= 3 and (short / float(long)) >= 0.65:
                        if float(t["conf"]) > float(prev["conf"]):
                            compact[-1] = t
                        continue
                compact.append(t)

            # Most people have 1-2 tokens in display name; cap to avoid long glued garbage.
            compact = compact[:3]
            token_boxes = [t["word"] for t in compact]
            raw_name = " ".join(str(t["raw"]).strip() for t in compact).strip()
            name = self._normalize_name(raw_name)
            if len(name) < 2:
                skip_stats["short_name"] += 1
                continue

            lefts = [int(b["left"]) for b in token_boxes]
            tops = [int(b["top"]) for b in token_boxes]
            rights = [int(b["left"]) + int(b["width"]) for b in token_boxes]
            bottoms = [int(b["top"]) + int(b["height"]) for b in token_boxes]
            chosen_left = min(lefts)
            chosen_top = min(tops)
            chosen_right = max(rights)
            chosen_bottom = max(bottoms)
            chosen_w = max(1, chosen_right - chosen_left)
            chosen_h = max(1, chosen_bottom - chosen_top)

            if self._row_has_role_label(words, chosen_left, chosen_top, chosen_w, chosen_h):
                skip_stats["role_label"] += 1
                log_and_print(
                    f"[personal_broadcast] skip role label on row for name='{name}' line='{line_text}' scan_id={scan_id}",
                    "debug",
                )
                continue
            # Right-side OCR noise is common; keep candidate if role checks passed.

            local_center_x = int(chosen_left) + int(chosen_w) // 2
            local_center_y = int(chosen_top) + int(chosen_h) // 2
            if local_center_x > int(scope[2] * self._NAME_MAX_X_RATIO):
                skip_stats["bad_token"] += 1
                log_and_print(
                    f"[personal_broadcast] skip right-column token name='{name}' x={local_center_x} "
                    f"scope_w={scope[2]} scan_id={scan_id}",
                    "debug",
                )
                continue
            if not self._has_avatar_left(local_center_x, local_center_y, circles):
                skip_stats["no_avatar"] += 1
                log_and_print(f"[personal_broadcast] skip no avatar near name='{name}' line='{line_text}' scan_id={scan_id}", "debug")
                continue

            center_x = scope[0] + local_center_x
            center_y = scope[1] + local_center_y
            candidates.append({"name": name, "x": center_x, "y": center_y})

        candidates = self._dedupe_candidates_by_position(candidates)

        unique = {}
        for c in candidates:
            key = PersonalBroadcastRegistry._norm_key(c["name"]) or c["name"].lower()
            if key not in unique:
                unique[key] = c
        result = list(unique.values())
        self._update_scan_metadata(
            scan_id,
            ocr_words_count=len(words),
            avatar_circles_count=len(circles),
            skip_stats=skip_stats,
            candidates_count=len(result),
            candidates=[{"name": c["name"], "x": int(c["x"]), "y": int(c["y"])} for c in result[:80]],
        )
        if result:
            preview = ", ".join(f"{c['name']}@({c['x']},{c['y']})" for c in result[:15])
            log_and_print(f"[personal_broadcast] candidates: {preview} scan_id={scan_id}", "debug")
        else:
            ocr_preview = [str(w.get("text", "")).strip() for w in words if str(w.get("text", "")).strip()]
            if ocr_preview:
                log_and_print(
                    f"[personal_broadcast] no candidates from OCR words: {', '.join(ocr_preview[:25])} scan_id={scan_id}",
                    "debug",
                )
            else:
                log_and_print(f"[personal_broadcast] no candidates: OCR words are empty after filtering scan_id={scan_id}", "debug")
        return result, scan_id

    @staticmethod
    def _ocr_lang_variants() -> list[str]:
        # Experiment mode: keep OCR language stable to reduce per-scan variance.
        variants = [
            "ukr+eng+rus",
            # "ukr+rus+eng",
            # "rus+ukr+eng",
        ]
        seen = set()
        out = []
        for v in variants:
            if v in seen:
                continue
            seen.add(v)
            out.append(v)
        return out

    @staticmethod
    def _ocr_words_with_scale(image, scale: float, min_conf: int, lang: str) -> list[dict]:
        words = perform_ocr_with_positions(image, min_conf=min_conf, lang=lang)
        if not words or scale <= 0:
            return words
        out = []
        inv = 1.0 / float(scale)
        for w in words:
            out.append(
                {
                    "text": w["text"],
                    "left": int(round(float(w["left"]) * inv)),
                    "top": int(round(float(w["top"]) * inv)),
                    "width": max(1, int(round(float(w["width"]) * inv))),
                    "height": max(1, int(round(float(w["height"]) * inv))),
                    "conf": float(w.get("conf", 0.0)),
                }
            )
        return out

    @classmethod
    def _select_best_name_word(cls, line_words: list[dict]) -> dict | None:
        best = None
        best_score = -1e9
        for w in line_words:
            token = str(w.get("text", "")).strip()
            normalized = cls._normalize_name(token)
            if not cls._is_member_name_token(normalized):
                continue
            conf = float(w.get("conf", 0.0))
            has_cyr = any("а" <= ch.lower() <= "я" or ch.lower() in {"і", "ї", "є", "ґ"} for ch in normalized)
            has_lat = any("a" <= ch.lower() <= "z" for ch in normalized)
            score = conf
            score += min(len(normalized), 14) * 1.5
            if has_cyr:
                score += 12.0
            if has_lat and not has_cyr:
                score -= 3.0
            if token and token[0].isupper():
                score += 2.0
            if score > best_score:
                best_score = score
                best = w
        return best

    @classmethod
    def _is_member_name_token(cls, token: str) -> bool:
        if len(token) < 3:
            return False
        low = token.lower()
        if cls._looks_like_role_word(low):
            return False
        if cls._looks_like_non_person_name(low):
            return False
        if low.startswith(
            (
                "\u0443\u0447\u0430\u0441\u043d",  # учасн
                "\u0443\u0447\u0430\u0441\u0442\u043d",  # участн
                "\u0443\u0447\u0430\u043a\u043d",
                "\u0437\u0430\u043f\u0440\u043e\u0441",  # запрос
                "\u0437\u0430\u043f\u0430",
            )
        ):
            return False
        if low in cls._NON_MEMBER_WORDS:
            return False
        if not any(ch.isalpha() for ch in token):
            return False
        return True

    @staticmethod
    def _looks_like_non_person_name(low: str) -> bool:
        low = (low or "").lower()
        if not low:
            return False
        non_person_parts = (
            "перевез",
            "переїзд",
            "поїзд",
            "европ",
            "євр",
            "bus",
            "travel",
            "group",
            "канал",
            "чат",
            "вы",
            "you",
        )
        return any(p in low for p in non_person_parts)

    @staticmethod
    def _looks_like_role_word(low: str) -> bool:
        low = (low or "").lower()
        if not low:
            return False
        role_parts = (
            "admin",
            "dmin",
            "superadmin",
            "админ",
            "дмин",
            "министратор",
            "дминистратор",
            "суперадмин",
        )
        return any(p in low for p in role_parts)
    @classmethod
    def _contains_role_marker(cls, text: str) -> bool:
        low = str(text or "").strip().lower()
        if not low:
            return False
        if any(marker in low for marker in cls._ROLE_MARKERS):
            return True
        tokens = [t for t in low.replace("|", " ").replace(",", " ").split() if t]
        return any(cls._looks_like_role_word(t) for t in tokens)

    def _row_has_role_label(
        self,
        words: list[dict],
        chosen_left: int,
        chosen_top: int,
        chosen_w: int,
        chosen_h: int,
    ) -> bool:
        chosen_right = chosen_left + chosen_w
        chosen_bottom = chosen_top + chosen_h
        for w in words:
            text = str(w.get("text", "")).strip()
            if not text:
                continue
            if not self._contains_role_marker(text):
                continue
            w_left = int(w["left"])
            if w_left < chosen_right + 40:
                continue
            w_top = int(w["top"])
            w_bottom = w_top + int(w["height"])
            overlap = max(0, min(chosen_bottom, w_bottom) - max(chosen_top, w_top))
            if overlap >= max(4, min(chosen_h, int(w["height"])) // 3):
                return True
        return False

    @staticmethod
    def _detect_avatar_circles(image_np) -> list[tuple[int, int, int]]:
        gray = cv2.cvtColor(image_np, cv2.COLOR_RGB2GRAY)
        blur = cv2.GaussianBlur(gray, (5, 5), 0)
        circles = cv2.HoughCircles(
            blur,
            cv2.HOUGH_GRADIENT,
            dp=1.2,
            minDist=26,
            param1=80,
            param2=16,
            minRadius=9,
            maxRadius=34,
        )
        if circles is None:
            return []
        return [(int(c[0]), int(c[1]), int(c[2])) for c in circles[0]]

    @staticmethod
    def _has_avatar_left(name_x: int, name_y: int, circles: list[tuple[int, int, int]]) -> bool:
        for cx, cy, _ in circles:
            if cx >= name_x:
                continue
            dx = name_x - cx
            dy = abs(name_y - cy)
            if 10 <= dx <= 180 and dy <= 45:
                return True
        return False

    def _send_to_member(self, window, s, candidate: dict, channel_name: str, scan_id: str | None = None) -> str:
        name = candidate["name"]
        x = candidate["x"]
        y = candidate["y"]
        sid = scan_id or "na"

        if self._is_in_exceptions(name):
            log_and_print(f"[personal_broadcast] skip by exceptions file: {name} scan_id={sid}", "debug")
            return "skip"

        if self._has_role_in_member_row(y, scan_id=sid):
            log_and_print(f"[personal_broadcast] skip role account before send: {name} scan_id={sid}", "debug")
            return "skip"

        log_and_print(f"[personal_broadcast] sending to {name} scan_id={sid}", "info")
        log_and_print(f"[personal_broadcast] click member name='{name}' at x={x}, y={y} scan_id={sid}", "debug")

        window.set_focus()
        gd.click(x, y)
        gd.pause(0.2)

        member_scope = self._config.members_scope
        # In position mode include extra two rows below configured scope,
        # because members list is taller than base config on some layouts.
        extra_bottom = 0
        if str(getattr(self._config, "processing_mode", "")).lower() == "by_positions":
            try:
                extra_bottom = max(0, int(self._config.position_row_height) * 2)
            except Exception:
                extra_bottom = 100

        panel_left = int(member_scope[0])
        panel_top = int(member_scope[1])
        panel_right = int(member_scope[0] + member_scope[2])
        panel_bottom = int(member_scope[1] + member_scope[3] + extra_bottom)

        # Search send icon in a small scope relative to selected row coordinates.
        sx1 = max(panel_left, x + 70)
        sx2 = min(panel_right, x + 290)
        sy1 = max(panel_top, y - 34)
        sy2 = min(panel_bottom, y + 34)

        # Fallback safety: keep non-empty rectangle.
        if sx2 <= sx1:
            sx1 = max(panel_left, panel_right - 150)
            sx2 = panel_right
        if sy2 <= sy1:
            sy1 = max(panel_top, y - 40)
            sy2 = min(panel_bottom, y + 40)

        send_scope = (sx1, sy1, sx2, sy2)

        if not self._click_image_with_optional_color_hint(
            self._config.row_send_image,
            scope=send_scope,
            confidence=0.95,
            use_purple_hint=True,
            scan_id=sid,
        ):
            log_and_print(f"[personal_broadcast] row send icon not found for {name} scan_id={sid}", "error")
            return "recover"
        log_and_print(f"[personal_broadcast] row send clicked, scope={send_scope} scan_id={sid}", "debug")

        # Required order: check popup before any message input.
        if self._dismiss_no_personal_messages_popup(scan_id=sid, context="before_input"):
            log_and_print(
                f"[personal_broadcast] skip input/send because popup visible: {name} scan_id={sid}",
                "warning",
            )
            return "recover"

        if not self._is_private_chat_context():
            log_and_print(
                f"[personal_broadcast] private-chat check failed (likely group), skip before input scan_id={sid}",
                "error",
            )
            return "recover"

        if self._already_sent_recl1():
            self._registry.add(name)
            log_and_print(
                f"[personal_broadcast] already-sent indicator detected (recl1.png), mark processed and exit dialog scan_id={sid}",
                "info",
            )
            try:
                self._back_to_group(window)
            except Exception:
                pass
            return "recover"

        window.set_focus()
        if not self._insert_message_text(window):
            log_and_print(f"[personal_broadcast] cannot insert message text for {name} scan_id={sid}", "error")
            return "recover"

        dialog_send_scope = self._config.dialog_send_scope
        action_state, send_score, mic_score = self._detect_dialog_action_state_with_pause(dialog_send_scope, pause_s=1.0)
        log_and_print(
            f"[personal_broadcast] dialog action state={action_state} "
            f"send_score={send_score:.3f} mic_score={mic_score:.3f} scan_id={sid}",
            "debug",
        )
        if action_state == "microphone":
            log_and_print(
                f"[personal_broadcast] microphone dominates by similarity; "
                f"text likely not inserted, skip send scan_id={sid}",
                "error",
            )
            self._save_dialog_action_snapshot(
                dialog_send_scope,
                reason="dialog_action_microphone",
                state=action_state,
                send_score=send_score,
                mic_score=mic_score,
                scan_id=sid,
                member_name=name,
            )
            return "recover"
        if action_state == "unknown":
            log_and_print(
                f"[personal_broadcast] cannot confidently determine send icon, "
                f"skip click to avoid microphone misclick scan_id={sid}",
                "error",
            )
            self._save_dialog_action_snapshot(
                dialog_send_scope,
                reason="dialog_action_unknown",
                state=action_state,
                send_score=send_score,
                mic_score=mic_score,
                scan_id=sid,
                member_name=name,
            )
            return "recover"

        # If error popup is already visible, do not click send again.
        if self._dismiss_no_personal_messages_popup(scan_id=sid, context="before_send_click"):
            log_and_print(
                f"[personal_broadcast] skip send click because popup already visible: {name} scan_id={sid}",
                "warning",
            )
            return "recover"

        if not gd.click_image(
            self._config.dialog_send_image,
            scope=dialog_send_scope,
            confidence=0.75,
            count_click=1,
            multiscale=True,
            is_debug=_ui_debug(),
        ):
            log_and_print(f"[personal_broadcast] dialog send icon not found for {name} scan_id={sid}", "error")
            self._save_dialog_action_snapshot(
                dialog_send_scope,
                reason="dialog_send_not_found",
                state=action_state,
                send_score=send_score,
                mic_score=mic_score,
                scan_id=sid,
                member_name=name,
            )
            return "recover"
        log_and_print(f"[personal_broadcast] dialog send clicked, scope={dialog_send_scope} scan_id={sid}", "debug")

        # After clicking send, some contacts can show "cannot receive personal messages".
        if self._dismiss_no_personal_messages_popup(scan_id=sid, context="after_send_click"):
            log_and_print(
                f"[personal_broadcast] no-personal-messages popup after send: {name} scan_id={sid}",
                "warning",
            )
            return "recover"

        self._registry.add(name)
        log_sent_message(channel_name=channel_name, text=self._config.message_text, source=f"personal:{name}")
        return "sent"

    def _dismiss_no_personal_messages_popup(self, scan_id: str | None = None, context: str = "") -> bool:
        handled = self._handle_no_personal_messages_popup(scan_id=scan_id)
        if handled and context:
            sid = scan_id or "na"
            log_and_print(
                f"[personal_broadcast] dismissed no-personal-messages popup context={context} scan_id={sid}",
                "debug",
            )
        return handled

    def _handle_no_personal_messages_popup(self, scan_id: str | None = None) -> bool:
        sid = scan_id or "na"
        popup_scope = (460, 540, 660, 640)
        popup_score = self._template_score_in_scope("no_mess_person_ok.png", popup_scope)
        log_and_print(
            f"[personal_broadcast] no-popup score={popup_score:.3f} scope={popup_scope} scan_id={sid}",
            "debug",
        )
        # Use purple-only mask matching to avoid false positives on white chat background.
        found = self._find_no_messages_ok_button(popup_scope)
        if not found:
            return False
        gd.pause(0.08)
        found_confirm = self._find_no_messages_ok_button(popup_scope)
        if not found_confirm:
            log_and_print(
                f"[personal_broadcast] popup candidate not confirmed scan_id={sid}",
                "debug",
            )
            return False
        if not self._popup_text_confirms_no_messages(found_confirm[0], found_confirm[1], scan_id=sid):
            log_and_print(
                f"[personal_broadcast] popup image found but text not confirmed; treat as false positive scan_id={sid}",
                "debug",
            )
            return False

        log_and_print(
            f"[personal_broadcast] popup 'cannot receive personal messages' detected scan_id={sid}",
            "warning",
        )
        try:
            gd.click(found_confirm[0], found_confirm[1])
        except Exception:
            pass
        return True

    def _find_no_messages_ok_button(self, scope: tuple[int, int, int, int]) -> tuple[int, int] | None:
        """
        Detect no_mess_person_ok.png by matching only saturated (purple) template pixels.
        This prevents matching on generic white backgrounds.
        """
        path = self._resolve_template_path("no_mess_person_ok.png")
        if path is None:
            return None
        tpl = cv2.imread(str(path), cv2.IMREAD_UNCHANGED)
        if tpl is None:
            return None
        if tpl.ndim == 3 and tpl.shape[2] == 4:
            tpl_bgr = cv2.cvtColor(tpl, cv2.COLOR_BGRA2BGR)
        elif tpl.ndim == 3:
            tpl_bgr = tpl
        else:
            tpl_bgr = cv2.cvtColor(tpl, cv2.COLOR_GRAY2BGR)

        # Keep only colored pixels (purple button); ignore white/gray background.
        tpl_hsv = cv2.cvtColor(tpl_bgr, cv2.COLOR_BGR2HSV)
        sat_mask = cv2.inRange(tpl_hsv, (0, 45, 40), (179, 255, 255))
        if int(cv2.countNonZero(sat_mask)) < 40:
            return None

        left, top, right, bottom = [int(v) for v in scope]
        width = max(1, right - left)
        height = max(1, bottom - top)
        snap_rgb = take_screenshot((left, top, width, height))
        snap_bgr = cv2.cvtColor(snap_rgb, cv2.COLOR_RGB2BGR)

        ih, iw = snap_bgr.shape[:2]
        th, tw = tpl_bgr.shape[:2]
        if th < 1 or tw < 1 or th > ih or tw > iw:
            return None

        res = cv2.matchTemplate(snap_bgr, tpl_bgr, cv2.TM_CCORR_NORMED, mask=sat_mask)
        _, max_val, _, max_loc = cv2.minMaxLoc(res)
        log_and_print(
            f"[personal_broadcast] no-popup purple-only score={max_val:.3f} scope={scope}",
            "debug",
        )
        if float(max_val) < 0.94:
            return None

        x, y = max_loc
        return (left + x + tw // 2, top + y + th // 2)

    def _popup_text_confirms_no_messages(self, ok_x: int, ok_y: int, scan_id: str | None = None) -> bool:
        sid = scan_id or "na"
        # Approximate modal text area above OK button.
        left = max(0, int(ok_x) - 260)
        top = max(0, int(ok_y) - 150)
        right = max(left + 40, int(ok_x) + 260)
        bottom = max(top + 30, int(ok_y) - 20)
        scope = (left, top, right, bottom)
        width = max(1, right - left)
        height = max(1, bottom - top)

        snap = take_screenshot((left, top, width, height))
        processed = preprocess_image(snap)
        words = perform_ocr_with_positions(processed, min_conf=20, lang="ukr+rus+eng")
        if not words:
            words = perform_ocr_with_positions(snap, min_conf=20, lang="ukr+rus+eng")

        line = " ".join(str(w.get("text", "")).strip().lower() for w in words if str(w.get("text", "")).strip())
        norm = "".join(ch if ch.isalnum() or ch.isspace() else " " for ch in line)
        norm = " ".join(norm.split())

        markers = [
            "ошибка",
            "учасник",
            "участник",
            "личн",
            "повідомл",
            "сообщен",
            "не може",
            "не может",
        ]
        hits = 0
        for m in markers:
            if m in norm:
                hits += 1
        log_and_print(
            f"[personal_broadcast] popup text OCR hits={hits} scope={scope} text='{norm[:160]}' scan_id={sid}",
            "debug",
        )
        return hits >= 2

    def _scroll_info_panel_up_for_private_check(self) -> None:
        """Before private/group detection, force list panel to top for stable UI signals."""
        try:
            scope = self._config.members_scope
            cx = int(scope[0] + scope[2] // 2)
            cy = int(scope[1] + scope[3] // 2)
            log_and_print(
                f"[personal_broadcast] private-chat precheck scroll up at x={cx}, y={cy}",
                "debug",
            )
            gd.human_move(cx, cy)
            gd.pause(0.05)
            gd.scroll(2600)
            gd.pause(0.08)
            gd.scroll(2600)
            gd.pause(0.08)
            gd.scroll(2600)
            gd.pause(0.08)
            gd.scroll(2600)
            gd.pause(0.25)
        except Exception as exc:
            log_and_print(f"[personal_broadcast] precheck scroll up failed: {exc}", "debug")

    def _is_private_chat_context(self) -> bool:
        has_info_icon = False
        try:
            has_info_icon = bool(
                gd.find_image(
                    "info.png",
                    timeout=1.2,
                    confidence=0.78,
                    scope=self._config.open_info_scope,
                    multiscale=True,
                    is_debug=_ui_debug(),
                )
            )
        except Exception:
            has_info_icon = False

        has_participants_word = self._scope_has_participants_label(
            self._config.participants_click_scope,
            strict=False,
            min_conf=30,
        )
        # Extra guard: if "????????/?????????" is visible near top header area,
        # this is a group chat with opened participants list.
        has_participants_header = self._scope_has_participants_label(
            (850, 55, 1070, 110),
            strict=True,
            min_conf=62,
        )

        action_visible, action_state, send_score, mic_score = self._dialog_action_icon_visible()

        log_and_print(
            f"[personal_broadcast] private-chat check: has_info_icon={has_info_icon}, "
            f"has_participants_word={has_participants_word}, "
            f"has_participants_header={has_participants_header}, "
            f"action_visible={action_visible}, action_state={action_state} "
            f"send_score={send_score:.3f} mic_score={mic_score:.3f}",
            "debug",
        )

        if has_participants_header:
            return False

        if action_visible:
            return True

        return has_info_icon and (not has_participants_word)


    def _dialog_action_icon_visible(self) -> tuple[bool, str, float, float]:
        try:
            state, send_score, mic_score = self._detect_dialog_action_state_with_pause(
                self._config.dialog_send_scope,
                pause_s=0.0,
            )
        except Exception:
            return False, "unknown", -1.0, -1.0
        best = max(send_score, mic_score)
        visible = best >= 0.90
        return visible, state, send_score, mic_score

    def _scope_has_participants_label(
        self,
        scope: tuple[int, int, int, int],
        strict: bool = False,
        min_conf: int = 30,
    ) -> bool:
        left, top, right, bottom = [int(v) for v in scope]
        width = max(1, right - left)
        height = max(1, bottom - top)
        snap = take_screenshot((left, top, width, height))
        processed = preprocess_image(snap)

        words = perform_ocr_with_positions(processed, min_conf=min_conf, lang="ukr+rus+eng")
        raw_words = perform_ocr_with_positions(snap, min_conf=min_conf, lang="ukr+rus+eng")
        all_words = words + raw_words

        labels = [str(x).strip().lower() for x in (self._config.participants_texts or []) if str(x).strip()]
        labels += ["учасники", "участники", "participants"]
        labels_norm = ["".join(ch for ch in label if ch.isalnum()) for label in labels if label]

        for w in all_words:
            token = str(w.get("text", "")).strip().lower()
            if not token:
                continue
            token = "".join(ch for ch in token if ch.isalnum())
            if not token:
                continue
            if strict:
                # Header scope is noisy; require near-exact OCR match.
                for norm_label in labels_norm:
                    if not norm_label:
                        continue
                    if SequenceMatcher(None, token, norm_label).ratio() >= 0.90:
                        return True
            else:
                if token.startswith("учас") or token.startswith("участ") or token.startswith("participant"):
                    return True
                for norm_label in labels_norm:
                    if norm_label and (norm_label in token or token in norm_label):
                        return True
        return False

    def _detect_dialog_action_state(self, scope: tuple[int, int, int, int]) -> tuple[str, float, float]:
        send_raw = self._template_score_in_scope(self._config.dialog_send_image, scope)
        mic_raw = self._template_score_in_scope("microfon.png", scope)
        send_glyph = self._template_score_in_scope_glyph(self._config.dialog_send_image, scope)
        mic_glyph = self._template_score_in_scope_glyph("microfon.png", scope)
        send_edge = self._template_score_in_scope_edges(self._config.dialog_send_image, scope)
        mic_edge = self._template_score_in_scope_edges("microfon.png", scope)
        send_score = (0.35 * send_raw) + (0.65 * send_glyph)
        mic_score = (0.35 * mic_raw) + (0.65 * mic_glyph)
        eps = 0.008
        edge_eps = 0.01

        log_and_print(
            f"[personal_broadcast] dialog score details raw(send={send_raw:.3f}, mic={mic_raw:.3f}) "
            f"glyph(send={send_glyph:.3f}, mic={mic_glyph:.3f}) "
            f"edge(send={send_edge:.3f}, mic={mic_edge:.3f}) "
            f"final(send={send_score:.3f}, mic={mic_score:.3f})",
            "debug",
        )

        if send_score < 0 and mic_score < 0:
            return "unknown", send_score, mic_score
        if send_score >= 0 and send_score > mic_score + eps:
            return "send", send_score, mic_score
        if mic_score >= 0 and mic_score > send_score + eps:
            return "microphone", send_score, mic_score

        # Tie-breaker using edge match when scores are too close.
        if send_edge >= 0 and mic_edge >= 0:
            if send_edge > mic_edge + edge_eps:
                return "send", send_score, mic_score
            if mic_edge > send_edge + edge_eps:
                return "microphone", send_score, mic_score

        return "unknown", send_score, mic_score

    def _detect_dialog_action_state_with_pause(
        self,
        scope: tuple[int, int, int, int],
        pause_s: float = 1.0,
    ) -> tuple[str, float, float]:
        if pause_s and pause_s > 0:
            gd.pause(float(pause_s))
        return self._detect_dialog_action_state(scope)

    def _has_role_in_member_row(self, member_center_y: int, scan_id: str | None = None) -> bool:
        scope = self._config.members_scope
        left = scope[0] + int(scope[2] * 0.55)
        top = max(scope[1], int(member_center_y) - 28)
        right = scope[0] + scope[2]
        bottom = min(scope[1] + scope[3], int(member_center_y) + 28)
        if right - left < 20 or bottom - top < 10:
            return False

        # take_screenshot expects (x, y, width, height)
        row_scope = (left, top, right - left, bottom - top)
        img = take_screenshot(row_scope)
        processed = preprocess_image(img)
        words = perform_ocr_with_positions(processed, min_conf=20, lang="ukr+eng+rus")
        if not words:
            words = perform_ocr_with_positions(img, min_conf=20, lang="ukr+eng+rus")
        if not words:
            return False
        row_text = " ".join(str(w.get("text", "")).strip() for w in words if str(w.get("text", "")).strip())
        if self._contains_role_marker(row_text):
            sid = scan_id or "na"
            log_and_print(f"[personal_broadcast] role marker in right column: '{row_text}' scan_id={sid}", "debug")
            return True
        return False


    def _already_sent_recl1(self) -> bool:
        try:
            found = gd.find_image(
                "recl1.png",
                timeout=0.6,
                confidence=0.9,
                scope=(410, 200, 780, 700),
                multiscale=True,
                is_debug=_ui_debug(),
            )
            return bool(found)
        except Exception:
            return False


    def _insert_message_text(self, window) -> bool:
        text = self._config.message_text
        if not text:
            log_and_print("[personal_broadcast] message text is empty", "error")
            return False

        x, y = self._config.message_input_xy
        target_layout = self._target_input_layout()
        previous_layout_name = None
        try:
            current_code = gd.get_current_layout()
            previous_layout_name = self._LAYOUT_CODE_TO_NAME.get(int(current_code))
        except Exception:
            previous_layout_name = None

        try:
            gd.ensure_layout(target_layout)
        except Exception as exc:
            log_and_print(f"[personal_broadcast] cannot set input layout={target_layout}: {exc}", "error")

        last_error = None
        try:
            dialog_send_scope = self._config.dialog_send_scope
            for attempt in range(1, 4):
                try:
                    window.set_focus()
                    gd.click(x, y)
                    gd.pause(0.08)
                    gd.click(x, y)
                    log_and_print(
                        f"[personal_broadcast] double-click message input at {(x, y)} attempt={attempt}/3",
                        "debug",
                    )
                    gd.pause(0.25)

                    # Try to focus and clear current text before paste.
                    pag.hotkey("ctrl", "a")
                    gd.pause(0.05)
                    pag.press("backspace")
                    gd.pause(0.05)

                    # Strategy 1: keyboard typing first (requested) via pywinauto.
                    typed = self._type_with_pywinauto(text)
                    gd.pause(0.2)
                    state, send_score, mic_score = self._detect_dialog_action_state_with_pause(dialog_send_scope, pause_s=1.0)
                    log_and_print(
                        f"[personal_broadcast] post-keyboard-type state={state} typed={typed} "
                        f"send_score={send_score:.3f} mic_score={mic_score:.3f} attempt={attempt}/3",
                        "debug",
                    )
                    if state == "send":
                        log_and_print(
                            f"[personal_broadcast] message accepted via keyboard typing attempt={attempt}/3",
                            "debug",
                        )
                        return True

                    # Strategy 2: Ctrl+V
                    pyperclip.copy(text)
                    self._paste_ctrl_v()
                    gd.pause(0.25)
                    state, send_score, mic_score = self._detect_dialog_action_state_with_pause(dialog_send_scope, pause_s=1.0)
                    log_and_print(
                        f"[personal_broadcast] post-paste(ctrl+v) state={state} "
                        f"send_score={send_score:.3f} mic_score={mic_score:.3f} attempt={attempt}/3",
                        "debug",
                    )
                    if state == "send":
                        log_and_print(
                            f"[personal_broadcast] message paste accepted via ctrl+v attempt={attempt}/3",
                            "debug",
                        )
                        return True

                    # Strategy 3: Shift+Insert
                    pyperclip.copy(text)
                    self._paste_shift_insert()
                    gd.pause(0.25)
                    state, send_score, mic_score = self._detect_dialog_action_state_with_pause(dialog_send_scope, pause_s=1.0)
                    log_and_print(
                        f"[personal_broadcast] post-paste(shift+insert) state={state} "
                        f"send_score={send_score:.3f} mic_score={mic_score:.3f} attempt={attempt}/3",
                        "debug",
                    )
                    if state == "send":
                        log_and_print(
                            f"[personal_broadcast] message paste accepted via shift+insert attempt={attempt}/3",
                            "debug",
                        )
                        return True
                    # If two paste attempts failed, use manual typing fallback.
                    if attempt >= 2:
                        if self._type_message_fallback(window, text, x, y):
                            log_and_print(
                                f"[personal_broadcast] message manual-typing fallback success attempt={attempt}/3",
                                "debug",
                            )
                            return True


                    state, send_score, mic_score = self._detect_dialog_action_state_with_pause(dialog_send_scope, pause_s=1.0)
                    log_and_print(
                        f"[personal_broadcast] paste verification failed attempt={attempt}/3 "
                        f"(state={state}, send_score={send_score:.3f}, mic_score={mic_score:.3f})",
                        "warning",
                    )
                    self._save_dialog_action_snapshot(
                        dialog_send_scope,
                        reason=f"input_verify_failed_attempt{attempt}",
                        state=state,
                        send_score=send_score,
                        mic_score=mic_score,
                        scan_id=None,
                        member_name=None,
                    )
                    continue

                except Exception as exc:
                    last_error = exc
                    log_and_print(f"[personal_broadcast] paste attempt={attempt}/3 failed: {exc}", "error")
                    gd.pause(0.2)

            if last_error:
                log_and_print(f"[personal_broadcast] paste failed after retries: {last_error}", "error")
            return False
        finally:
            if previous_layout_name and previous_layout_name != target_layout:
                try:
                    gd.ensure_layout(previous_layout_name)
                    log_and_print(
                        f"[personal_broadcast] keyboard layout restored to {previous_layout_name}",
                        "debug",
                    )
                except Exception as exc:
                    log_and_print(
                        f"[personal_broadcast] cannot restore keyboard layout to {previous_layout_name}: {exc}",
                        "error",
                    )

    def _type_message_fallback(self, window, text: str, x: int, y: int) -> bool:
        try:
            # Manual typing fallback (requested): force focus into input first.
            window.set_focus()
            gd.click(x, y)
            gd.pause(0.08)
            gd.click(x, y)
            gd.pause(0.12)
            pag.hotkey("ctrl", "a")
            gd.pause(0.04)
            pag.press("backspace")
            gd.pause(0.05)
            # Prevent sticky modifier keys from corrupting typed text.
            for key in ("ctrl", "shift", "alt", "win"):
                try:
                    pag.keyUp(key)
                except Exception:
                    pass

            # If message has Cyrillic and config layout is en, auto-switch for typing fallback.
            layout_for_typing = self._target_input_layout()
            if layout_for_typing == "en" and any("\u0400" <= ch <= "\u04FF" for ch in text):
                layout_for_typing = "uk"
            try:
                gd.ensure_layout(layout_for_typing)
                log_and_print(
                    f"[personal_broadcast] manual typing layout={layout_for_typing}",
                    "debug",
                )
            except Exception as exc:
                log_and_print(
                    f"[personal_broadcast] cannot set manual typing layout={layout_for_typing}: {exc}",
                    "error",
                )
            # Primary: pywinauto keyboard typing (Unicode on Windows).
            if self._type_with_pywinauto(text):
                log_and_print("[personal_broadcast] manual typing method=pywinauto.send_keys", "debug")
            elif gd.type_text_unicode(text, interval_s=0.005):
                log_and_print("[personal_broadcast] manual typing method=unicode_sendinput", "debug")
            else:
                # Fallback: paste full text, then Shift+Insert as backup.
                log_and_print("[personal_broadcast] unicode_sendinput failed, use clipboard full-paste fallback", "warning")
                old_clip = None
                try:
                    old_clip = pyperclip.paste()
                except Exception:
                    old_clip = None
                try:
                    pyperclip.copy(text)
                    self._paste_ctrl_v()
                    gd.pause(0.12)
                    pyperclip.copy(text)
                    self._paste_shift_insert()
                    gd.pause(0.12)
                finally:
                    if old_clip is not None:
                        try:
                            pyperclip.copy(old_clip)
                        except Exception:
                            pass
            gd.pause(0.2)
            state, send_score, mic_score = self._detect_dialog_action_state_with_pause(self._config.dialog_send_scope, pause_s=1.0)
            log_and_print(
                f"[personal_broadcast] manual-typing fallback state={state} "
                f"send_score={send_score:.3f} mic_score={mic_score:.3f}",
                "debug",
            )
            if state == "send":
                return True
            if state == "microphone":
                return False
            return False
        except Exception as exc:
            log_and_print(f"[personal_broadcast] manual typing fallback failed: {exc}", "error")
            return False

    @staticmethod
    def _type_with_pywinauto(text: str) -> bool:
        if not text:
            return False
        # Escape send_keys reserved symbols so text is typed literally.
        escaped = []
        for ch in str(text):
            if ch in {"+", "^", "%", "~", "(", ")", "{", "}"}:
                escaped.append("{" + ch + "}")
            else:
                escaped.append(ch)
        send_text = "".join(escaped)
        # Try both VK_PACKET modes: some apps don't handle VK_PACKET reliably.
        for vk_packet in (True, False):
            try:
                win_keyboard.send_keys(
                    send_text,
                    pause=0.02,
                    with_spaces=True,
                    with_newlines=True,
                    vk_packet=vk_packet,
                )
                return True
            except Exception:
                continue
        return False

    def _verify_input_text(self, window, x: int, y: int, text: str) -> bool:
        try:
            window.set_focus()
            gd.click(x, y)
            gd.pause(0.06)
        except Exception:
            pass
        ok = self._input_contains_text(text)
        return ok

    @staticmethod
    def _paste_ctrl_v() -> None:
        # Match forwarding flow style: keyDown/press/keyUp with small pauses.
        pag.keyDown("ctrl")
        gd.pause(0.2)
        pag.press("v")
        gd.pause(0.2)
        pag.keyUp("ctrl")
        gd.pause(0.2)

    @staticmethod
    def _paste_shift_insert() -> None:
        pag.keyDown("shift")
        gd.pause(0.2)
        pag.press("insert")
        gd.pause(0.2)
        pag.keyUp("shift")
        gd.pause(0.2)

    @staticmethod
    def _input_contains_text(expected: str) -> bool:
        if not expected:
            return False
        try:
            old_clip = pyperclip.paste()
        except Exception:
            old_clip = None

        try:
            marker = "__pb_clip_marker__"
            pyperclip.copy(marker)
            pag.hotkey("ctrl", "a")
            gd.pause(0.04)
            pag.hotkey("ctrl", "c")
            gd.pause(0.08)
            current = (pyperclip.paste() or "").strip().lower()
            target = expected.strip().lower()
            # If marker remains in clipboard, copy-from-input did not happen.
            if not current or current == marker:
                return False
            return target in current or current in target
        except Exception:
            return False
        finally:
            if old_clip is not None:
                try:
                    pyperclip.copy(old_clip)
                except Exception:
                    pass

    def _back_to_group(self, window) -> bool:
        window.set_focus()
        log_and_print(
            f"[personal_broadcast] click return image={self._config.return_image}, scope={self._config.return_scope}",
            "debug",
        )
        if not gd.click_image(
            self._config.return_image,
            scope=self._config.return_scope,
            confidence=0.7,
            count_click=1,
            multiscale=True,
            is_debug=_ui_debug(),
        ):
            log_and_print("[personal_broadcast] cannot return to group", "error")
            return False
        gd.pause(0.3)
        return True

    def _gender_matches(self, name: str) -> bool:
        filter_value = self._config.gender_filter
        if filter_value == "all":
            return True
        is_female = self._is_female_name(name)
        if filter_value == "female":
            return is_female
        if filter_value == "male":
            return not is_female
        return True

    @staticmethod
    def _is_female_name(name: str) -> bool:
        n = name.strip().lower()
        if not n:
            return False
        # Heuristic for ukr/rus/eng OCR names:
        # female names often end with: а/я (cyrillic) or a (latin).
        return n[-1] in {"\u0430", "\u044f", "a"}  # а, я, a

    @staticmethod
    def _exception_norm_key(value: str) -> str:
        t = unicodedata.normalize("NFKC", str(value or "").lower())
        # Cyrillic/Latin confusables for OCR text
        table = str.maketrans({
            "?": "a", "?": "e", "?": "o", "?": "p", "?": "c", "?": "y", "?": "x",
            "?": "k", "?": "m", "?": "t", "?": "b", "?": "i", "?": "i", "?": "i", "?": "e",
            "?": "", "?": "",
        })
        t = t.translate(table)
        t = "".join(ch for ch in t if ch.isalpha())
        # collapse repeated chars and repeated whole-string chunks
        t = re.sub(r"(.)\1{2,}", r"\1\1", t)
        for k in range(1, max(1, len(t) // 2 + 1)):
            if len(t) % k == 0:
                unit = t[:k]
                if unit * (len(t) // k) == t:
                    t = unit
                    break
        return t

    @classmethod
    def _exception_tokens(cls, value: str) -> list[str]:
        text = str(value or "")
        if not text:
            return []

        # split by separators + lower->UPPER transitions + script transitions
        out = []
        cur = []

        def script(ch: str) -> str:
            o = ord(ch)
            if (0x0400 <= o <= 0x04FF) or ch in "??????????":
                return "cyr"
            if "a" <= ch.lower() <= "z":
                return "lat"
            return "other"

        prev = ""
        for ch in text:
            if not ch.isalpha():
                if cur:
                    out.append("".join(cur))
                    cur = []
                prev = ""
                continue
            if cur:
                if prev.islower() and ch.isupper():
                    out.append("".join(cur))
                    cur = []
                elif script(prev) != script(ch):
                    out.append("".join(cur))
                    cur = []
            cur.append(ch)
            prev = ch
        if cur:
            out.append("".join(cur))

        norm_tokens = []
        for tok in out:
            k = cls._exception_norm_key(tok)
            if len(k) >= 3:
                norm_tokens.append(k)

        # drop consecutive duplicates
        dedup = []
        for tok in norm_tokens:
            if dedup and dedup[-1] == tok:
                continue
            dedup.append(tok)
        return dedup

    @staticmethod
    def _exception_tokens_match(candidate_tokens: list[str], exception_tokens: list[str]) -> bool:
        if not candidate_tokens or not exception_tokens:
            return False

        def token_ok(c: str, e: str) -> bool:
            if c == e:
                return True
            if c in e or e in c:
                short = min(len(c), len(e))
                long = max(len(c), len(e))
                return short >= 3 and (short / float(long)) >= 0.55
            return SequenceMatcher(None, c, e).ratio() >= 0.72

        for e in exception_tokens:
            if not any(token_ok(c, e) for c in candidate_tokens):
                return False
        return True

    @staticmethod
    def _normalize_name(name: str) -> str:
        allowed = []
        for ch in name:
            if ch.isalpha() or ch in {"-", "'"}:
                allowed.append(ch)
        return "".join(allowed).strip()







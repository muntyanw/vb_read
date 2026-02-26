import random
import time
from collections import defaultdict

import cv2
import pyautogui as pag
import pyperclip

from core import gui_driver as gd
from dispatcher.dispatch_client import klickViberChannel, window_top_focus
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
        "участники",
        "учасники",
        "participants",
        "вы",
        "you",
        "неизвестно",
        "--",
    }
    _RIGHT_TEXT_MIN_GAP_PX = 110
    _BUILTIN_ROLE_KEYWORDS = {
        "admin",
        "administrator",
        "superadmin",
        "админ",
        "администратор",
        "суперадмин",
    }

    def __init__(self, config: PersonalBroadcastConfig):
        self._config = config
        self._registry = PersonalBroadcastRegistry(config.sent_names_file)
        log_and_print("[personal_broadcast] initialized", "info")

    def update_config(self, config: PersonalBroadcastConfig) -> None:
        sent_file_changed = self._config.sent_names_file != config.sent_names_file
        self._config = config
        log_and_print("[personal_broadcast] config updated", "debug")
        if sent_file_changed:
            self._registry = PersonalBroadcastRegistry(config.sent_names_file)
            log_and_print(f"[personal_broadcast] registry file changed: {config.sent_names_file}", "debug")

    def run_once(self, window, s) -> None:
        if not self._config.enabled:
            log_and_print("[personal_broadcast] skipped: disabled by config", "debug")
            return

        channel = self._config.target_channel
        log_and_print(f"[personal_broadcast] start channel={channel.get('name_viber_channel')}", "debug")
        window_top_focus(window)
        if not klickViberChannel("image", window, False, channel):
            log_and_print(
                f"[personal_broadcast] channel open failed: {channel.get('name_viber_channel')}",
                "error",
            )
            return
        self._run_channel(window, s, channel.get("name_viber_channel", "unknown"))

    def _run_channel(self, window, s, channel_name: str) -> None:
        if not self._open_participants(window):
            return

        for step in range(self._config.max_scroll_steps):
            log_and_print(f"[personal_broadcast] scan step={step+1}/{self._config.max_scroll_steps}", "debug")
            candidates = self._read_candidates_from_scope()
            if step == 0 and candidates:
                first_candidate = min(candidates, key=lambda c: (c["y"], c["x"]))
                candidates = [c for c in candidates if c is not first_candidate]
                log_and_print(
                    f"[personal_broadcast] first pass skip top candidate '{first_candidate['name']}' "
                    f"at ({first_candidate['x']},{first_candidate['y']})",
                    "debug",
                )
            log_and_print(f"[personal_broadcast] candidates found={len(candidates)}", "debug")
            sent_any = False

            for candidate in candidates:
                name = candidate["name"]
                if self._registry.has(name):
                    log_and_print(f"[personal_broadcast] skip already sent: {name}", "debug")
                    continue
                if not self._gender_matches(name):
                    log_and_print(f"[personal_broadcast] skip gender filter: {name}", "debug")
                    continue

                if self._send_to_member(window, s, candidate, channel_name):
                    self._registry.add(name)
                    sent_any = True
                    pause = random.uniform(0, max(self._config.max_pause_seconds, 0.0))
                    time.sleep(pause)
                    if not self._back_to_group(window):
                        return
                    if not self._open_participants(window):
                        return
                    break

            if sent_any:
                continue

            log_and_print("[personal_broadcast] no candidate sent, scroll down", "debug")
            scroll_with_mouse(window, count_scroll=2, direction="down")
            gd.pause(0.3)

        log_and_print(f"[personal_broadcast] no more candidates in {channel_name}", "info")
        self._back_to_group(window)

    def _open_participants(self, window) -> bool:
        window.set_focus()
        log_and_print(
            f"[personal_broadcast] click info image={self._config.open_info_image}, scope={self._config.open_info_scope}",
            "debug",
        )
        if not gd.click_image(
            self._config.open_info_image,
            scope=self._config.open_info_scope,
            confidence=0.8,
            count_click=1,
            multiscale=True,
            is_debug=_ui_debug(),
        ):
            log_and_print("[personal_broadcast] cannot open info panel", "error")
            return False

        log_and_print(
            f"[personal_broadcast] click participants text in scope={self._config.participants_click_scope}",
            "debug",
        )
        gd.pause(1.0)
        if not gd.click_text(
            self._config.participants_texts,
            count_attempt_find=2,
            pause_attempt=1,
            lang="ukr",
            scope=self._config.participants_click_scope,
            threshold=0.6,
            is_debug=_ui_debug(),
            count_click=1,
        ):
            log_and_print("[personal_broadcast] cannot click participants", "error")
            return False
        return True

    def _read_candidates_from_scope(self) -> list[dict]:
        scope = self._config.members_scope
        log_and_print(f"[personal_broadcast] OCR scope={scope}", "debug")
        gd.pause(1.0)
        img = take_screenshot(scope)
        processed = preprocess_image(img)
        circles = self._detect_avatar_circles(img)
        log_and_print(f"[personal_broadcast] avatar circles={len(circles)}", "debug")
        if _ui_debug():
            # quick preview for debug mode without stopping the loop
            showImage(img, 0, title=f"[personal_broadcast] OCR raw scope={scope}")
            showImage(processed, 0, title=f"[personal_broadcast] OCR processed scope={scope}")
        words = perform_ocr_with_positions(processed)
        if not words:
            log_and_print("[personal_broadcast] OCR returned 0 words", "debug")
            return []

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
                log_and_print(f"[personal_broadcast] role detected, skip line='{line_text}'", "debug")
                continue

            chosen = None
            for w in line_words:
                token = str(w["text"]).strip()
                normalized = self._normalize_name(token)
                if self._is_member_name_token(normalized):
                    chosen = w
                    break
            if not chosen:
                continue

            raw_name = str(chosen["text"]).strip()
            name = self._normalize_name(raw_name)
            if len(name) < 2:
                continue

            chosen_left = int(chosen["left"])
            chosen_top = int(chosen["top"])
            chosen_w = int(chosen["width"])
            chosen_h = int(chosen["height"])
            chosen_right = chosen_left + chosen_w
            chosen_bottom = chosen_top + chosen_h
            has_right_text = False
            for w in words:
                text = str(w.get("text", "")).strip()
                if not text:
                    continue
                w_left = int(w["left"])
                if w_left < chosen_right + self._RIGHT_TEXT_MIN_GAP_PX:
                    continue
                w_top = int(w["top"])
                w_bottom = w_top + int(w["height"])
                # Same row by vertical overlap (robust to OCR line split).
                overlap = max(0, min(chosen_bottom, w_bottom) - max(chosen_top, w_top))
                if overlap >= max(4, min(chosen_h, int(w["height"])) // 3):
                    has_right_text = True
                    break
            if has_right_text:
                log_and_print(
                    f"[personal_broadcast] skip right-side text for name='{name}' line='{line_text}'",
                    "debug",
                )
                continue

            local_center_x = int(chosen["left"]) + int(chosen["width"]) // 2
            local_center_y = int(chosen["top"]) + int(chosen["height"]) // 2
            if not self._has_avatar_left(local_center_x, local_center_y, circles):
                log_and_print(f"[personal_broadcast] skip no avatar near name='{name}' line='{line_text}'", "debug")
                continue

            center_x = scope[0] + local_center_x
            center_y = scope[1] + local_center_y
            candidates.append({"name": name, "x": center_x, "y": center_y})

        unique = {}
        for c in candidates:
            key = c["name"].lower()
            if key not in unique:
                unique[key] = c
        result = list(unique.values())
        if result:
            preview = ", ".join(f"{c['name']}@({c['x']},{c['y']})" for c in result[:15])
            log_and_print(f"[personal_broadcast] candidates: {preview}", "debug")
        else:
            ocr_preview = [str(w.get("text", "")).strip() for w in words if str(w.get("text", "")).strip()]
            if ocr_preview:
                log_and_print(
                    f"[personal_broadcast] no candidates from OCR words: {', '.join(ocr_preview[:25])}",
                    "debug",
                )
            else:
                log_and_print("[personal_broadcast] no candidates: OCR words are empty after filtering", "debug")
        return result

    @classmethod
    def _is_member_name_token(cls, token: str) -> bool:
        if len(token) < 2:
            return False
        low = token.lower()
        if low in cls._NON_MEMBER_WORDS:
            return False
        if not any(ch.isalpha() for ch in token):
            return False
        return True

    @staticmethod
    def _detect_avatar_circles(image_np) -> list[tuple[int, int, int]]:
        gray = cv2.cvtColor(image_np, cv2.COLOR_RGB2GRAY)
        blur = cv2.GaussianBlur(gray, (5, 5), 0)
        circles = cv2.HoughCircles(
            blur,
            cv2.HOUGH_GRADIENT,
            dp=1.2,
            minDist=26,
            param1=90,
            param2=20,
            minRadius=10,
            maxRadius=28,
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
            if 15 <= dx <= 140 and dy <= 30:
                return True
        return False

    def _send_to_member(self, window, s, candidate: dict, channel_name: str) -> bool:
        name = candidate["name"]
        x = candidate["x"]
        y = candidate["y"]
        log_and_print(f"[personal_broadcast] sending to {name}", "info")
        log_and_print(f"[personal_broadcast] click member name='{name}' at x={x}, y={y}", "debug")

        window.set_focus()
        gd.click(x, y)
        gd.pause(0.2)

        member_scope = self._config.members_scope
        send_scope = (
            member_scope[0] + member_scope[2] - 130,
            max(member_scope[1], y - 30),
            member_scope[0] + member_scope[2],
            min(member_scope[1] + member_scope[3], y + 30),
        )

        if not gd.click_image(
            self._config.row_send_image,
            scope=send_scope,
            confidence=0.95,
            count_click=1,
            multiscale=False,
            is_debug=_ui_debug(),
        ):
            log_and_print(f"[personal_broadcast] row send icon not found for {name}", "error")
            return False
        log_and_print(f"[personal_broadcast] row send clicked, scope={send_scope}", "debug")

        window.set_focus()
        if not self._insert_message_text(window):
            log_and_print(f"[personal_broadcast] cannot insert message text for {name}", "error")
            return False

        dialog_send_scope = self._config.dialog_send_scope

        if not gd.click_image(
            self._config.dialog_send_image,
            scope=dialog_send_scope,
            confidence=0.7,
            count_click=1,
            multiscale=True,
            is_debug=_ui_debug(),
        ):
            log_and_print(f"[personal_broadcast] dialog send icon not found for {name}", "error")
            return False
        log_and_print(f"[personal_broadcast] dialog send clicked, scope={dialog_send_scope}", "debug")

        log_sent_message(channel_name=channel_name, text=self._config.message_text, source=f"personal:{name}")
        return True

    def _insert_message_text(self, window) -> bool:
        text = self._config.message_text
        if not text:
            log_and_print("[personal_broadcast] message text is empty", "error")
            return False

        x, y = self._config.message_input_xy
        last_error = None
        for attempt in range(1, 4):
            try:
                window.set_focus()
                gd.click(x, y)
                log_and_print(
                    f"[personal_broadcast] click message input at {(x, y)} attempt={attempt}/3",
                    "debug",
                )
                gd.pause(0.2)

                # Try to focus and clear current text before paste.
                pag.hotkey("ctrl", "a")
                gd.pause(0.05)
                pag.press("backspace")
                gd.pause(0.05)

                pyperclip.copy(text)
                pag.hotkey("ctrl", "v")
                gd.pause(0.2)

                # Fallback insert for apps/windows where Ctrl+V is intercepted.
                if pyperclip.paste() != text:
                    pyperclip.copy(text)
                pag.hotkey("shift", "insert")
                gd.pause(0.15)

                log_and_print(f"[personal_broadcast] message paste done attempt={attempt}/3", "debug")
                return True
            except Exception as exc:
                last_error = exc
                log_and_print(f"[personal_broadcast] paste attempt={attempt}/3 failed: {exc}", "error")
                gd.pause(0.2)

        if last_error:
            log_and_print(f"[personal_broadcast] paste failed after retries: {last_error}", "error")
        return False

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
        return n[-1] in {"а", "я", "a"}

    @staticmethod
    def _normalize_name(name: str) -> str:
        allowed = []
        for ch in name:
            if ch.isalpha() or ch in {"-", "'"}:
                allowed.append(ch)
        return "".join(allowed).strip()

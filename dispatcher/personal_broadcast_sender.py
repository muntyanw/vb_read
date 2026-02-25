import random
import time
from collections import defaultdict

import pyautogui as pag
import pyperclip

from core import gui_driver as gd
from dispatcher.dispatch_client import klickViberChannel, window_top_focus
from dispatcher.message_send_logger import log_sent_message
from dispatcher.personal_broadcast_config import PersonalBroadcastConfig
from dispatcher.personal_broadcast_registry import PersonalBroadcastRegistry
from log import log_and_print
from recognize_text import perform_ocr_with_positions, preprocess_image
from utils import take_screenshot
from vb_utils import scroll_with_mouse


class PersonalBroadcastSender:
    def __init__(self, config: PersonalBroadcastConfig):
        self._config = config
        self._registry = PersonalBroadcastRegistry(config.sent_names_file)
        log_and_print("[personal_broadcast] initialized", "info")

    def update_config(self, config: PersonalBroadcastConfig) -> None:
        sent_file_changed = self._config.sent_names_file != config.sent_names_file
        self._config = config
        if sent_file_changed:
            self._registry = PersonalBroadcastRegistry(config.sent_names_file)

    def run_once(self, window, s) -> None:
        if not self._config.enabled:
            return

        channel = self._config.target_channel
        window_top_focus(window)
        if not klickViberChannel("image", window, True, channel):
            log_and_print(
                f"[personal_broadcast] channel open failed: {channel.get('name_viber_channel')}",
                "error",
            )
            return
        self._run_channel(window, s, channel.get("name_viber_channel", "unknown"))

    def _run_channel(self, window, s, channel_name: str) -> None:
        if not self._open_participants(window):
            return

        for _ in range(self._config.max_scroll_steps):
            candidates = self._read_candidates_from_scope()
            sent_any = False

            for candidate in candidates:
                name = candidate["name"]
                if self._registry.has(name):
                    continue
                if not self._gender_matches(name):
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

            scroll_with_mouse(window, count_scroll=2, direction="down")
            gd.pause(0.3)

        log_and_print(f"[personal_broadcast] no more candidates in {channel_name}", "info")
        self._back_to_group(window)

    def _open_participants(self, window) -> bool:
        window.set_focus()
        if not gd.click_image(
            self._config.open_info_image,
            scope=None,
            confidence=0.8,
            count_click=1,
            multiscale=True,
            is_debug=False,
        ):
            log_and_print("[personal_broadcast] cannot open info panel", "error")
            return False

        if not gd.click_text(
            self._config.participants_texts,
            count_attempt_find=2,
            pause_attempt=1,
            lang="ukr",
            scope=self._config.participants_click_scope,
            threshold=0.6,
            is_debug=False,
            count_click=1,
        ):
            log_and_print("[personal_broadcast] cannot click participants", "error")
            return False
        return True

    def _read_candidates_from_scope(self) -> list[dict]:
        scope = self._config.members_scope
        img = take_screenshot(scope)
        processed = preprocess_image(img)
        words = perform_ocr_with_positions(processed)
        if not words:
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
            if any(role in low for role in self._config.role_keywords):
                continue

            first = line_words[0]
            raw_name = str(first["text"]).strip()
            name = self._normalize_name(raw_name)
            if len(name) < 2:
                continue

            center_x = scope[0] + int(first["left"]) + int(first["width"]) // 2
            center_y = scope[1] + int(first["top"]) + int(first["height"]) // 2
            candidates.append({"name": name, "x": center_x, "y": center_y})

        unique = {}
        for c in candidates:
            key = c["name"].lower()
            if key not in unique:
                unique[key] = c
        return list(unique.values())

    def _send_to_member(self, window, s, candidate: dict, channel_name: str) -> bool:
        name = candidate["name"]
        x = candidate["x"]
        y = candidate["y"]
        log_and_print(f"[personal_broadcast] sending to {name}", "info")

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
            confidence=0.7,
            count_click=1,
            multiscale=True,
            is_debug=False,
        ):
            log_and_print(f"[personal_broadcast] row send icon not found for {name}", "error")
            return False

        window.set_focus()
        gd.click(self._config.message_input_xy[0], self._config.message_input_xy[1])
        gd.pause(0.2)
        pyperclip.copy(self._config.message_text)
        pag.hotkey("ctrl", "v")
        gd.pause(0.2)

        if not gd.click_image(
            self._config.dialog_send_image,
            scope=None,
            confidence=0.7,
            count_click=1,
            multiscale=True,
            is_debug=False,
        ):
            log_and_print(f"[personal_broadcast] dialog send icon not found for {name}", "error")
            return False

        log_sent_message(channel_name=channel_name, text=self._config.message_text, source=f"personal:{name}")
        return True

    def _back_to_group(self, window) -> bool:
        window.set_focus()
        if not gd.click_image(
            self._config.back_to_group_image,
            scope=None,
            confidence=0.7,
            count_click=1,
            multiscale=True,
            is_debug=False,
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
        return n[-1] in {"а", "я"}

    @staticmethod
    def _normalize_name(name: str) -> str:
        allowed = []
        for ch in name:
            if ch.isalpha() or ch in {"-", "'"}:
                allowed.append(ch)
        return "".join(allowed).strip()

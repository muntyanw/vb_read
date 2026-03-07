import time
import requests
from typing import List, Dict, Any

import pyautogui as pag
import pyperclip

from core import gui_driver as gd
from log import log_and_print
from dispatcher.dispatch_client import klickViberChannel, window_top_focus
from dispatcher.message_send_logger import log_sent_message
from dispatcher.dispatch_client import _get_ips
from dispatcher.server_dispatcher_config import ServerDispatcherConfig


class ServerDispatcherSender:
    def __init__(self, config: ServerDispatcherConfig):
        self._config = config
        self._last_wait_log_at = 0.0
        self._next_poll_at = float("inf")
        self._backoff_delay = 5.0  # start with 5s
        self._last_sent_ids = set()  # to avoid duplicates in one cycle
        self.update_config(config, is_startup=True)

    def update_config(self, config: ServerDispatcherConfig, is_startup: bool = False) -> None:
        if config == self._config and self._next_poll_at != float("inf"):
            return

        self._config = config
        if config.enabled:
            ips = _get_ips()
            ip = ips[0] if ips else "no-ip"
            self._next_poll_at = time.monotonic()
            log_and_print(
                f"[server_dispatcher] enabled: poll every {config.poll_interval_seconds} s from {ip}:8888",
                "info",
            )
        else:
            self._next_poll_at = float("inf")
            log_and_print("[server_dispatcher] disabled", "info")

    def send_if_due(self, window, s) -> None:
        if not self._config.enabled:
            return

        now = time.monotonic()
        if now < self._next_poll_at:
            if now - self._last_wait_log_at >= 60:
                secs_left = self._next_poll_at - now
                log_and_print(
                    f"[server_dispatcher] waiting, next poll in {secs_left:.1f} s",
                    "info",
                )
                self._last_wait_log_at = now
            return

        log_and_print("[server_dispatcher] start poll cycle", "info")
        self._poll_and_send(window, s)
        self._next_poll_at = now + self._config.poll_interval_seconds
        log_and_print("[server_dispatcher] poll cycle complete", "info")

    def _poll_and_send(self, window, s) -> None:
        ips = _get_ips()
        if not ips:
            log_and_print("[server_dispatcher] no IPS configured", "error")
            return
        ip = ips[0]  # use first IP
        url = f"http://{ip}:8888/api/dispatcher/notifications/poll"
        params = {"limit": self._config.poll_limit}
        if self._config.user_id:
            params["user_id"] = self._config.user_id

        try:
            response = requests.get(url, params=params, timeout=30)
            response.raise_for_status()
            data = response.json()
        except requests.RequestException as e:
            log_and_print(f"[server_dispatcher] HTTP error: {e}", "error")
            self._handle_backoff()
            return
        except Exception as e:
            log_and_print(f"[server_dispatcher] JSON parse error: {e}", "error")
            self._handle_backoff()
            return

        # Reset backoff on success
        self._backoff_delay = 5.0

        server_time = data.get("server_time")
        has_messages = data.get("has_messages", False)
        messages = data.get("messages", [])

        log_and_print(f"[server_dispatcher] polled: server_time={server_time}, has_messages={has_messages}, count={len(messages)}", "info")

        if not has_messages or not messages:
            return

        sent_ids = []
        errors = []

        self._last_sent_ids.clear()

        for msg in messages:
            msg_id = msg.get("id")
            if msg_id in self._last_sent_ids:
                continue
            message_text = msg.get("message_text", "").strip()
            if not message_text:
                continue

            try:
                self._send_to_all_channels(window, s, message_text)
                sent_ids.append(msg_id)
                self._last_sent_ids.add(msg_id)
                log_sent_message(channel_name="all_channels", text=message_text, source="server_dispatcher")
            except Exception as e:
                errors.append({"id": msg_id, "error": str(e)})
                log_and_print(f"[server_dispatcher] send error for id={msg_id}: {e}", "error")

        log_and_print(f"[server_dispatcher] sent_ids={sent_ids}, errors={errors}", "info")

    def _handle_backoff(self) -> None:
        self._backoff_delay = min(self._backoff_delay * 2, 60.0)
        self._next_poll_at = time.monotonic() + self._backoff_delay
        log_and_print(f"[server_dispatcher] backoff: next poll in {self._backoff_delay} s", "warning")

    def _send_to_all_channels(self, window, s, text: str) -> None:
        for channel in s.viber_channels:
            window_top_focus(window)
            if not klickViberChannel("image", window, True, channel):
                log_and_print(
                    f"[server_dispatcher] skip channel: {channel.get('name_viber_channel')}",
                    "error",
                )
                continue

            self._send_text_to_active_chat(window, s, text, channel.get("name_viber_channel"))

    def _send_text_to_active_chat(self, window, s, text: str, channel_name: str | None) -> None:
        # Click message input area near the bottom of the chat panel.
        input_x = s.search_board_mess_x_start + 240
        input_y = s.search_board_mess_y_end + 12

        window.set_focus()
        gd.click(input_x, input_y)
        gd.pause(0.2)

        pyperclip.copy(text)
        pag.hotkey("ctrl", "v")
        gd.pause(0.2)
        pag.press("enter")
        gd.pause(0.5)

        text_preview = text if len(text) <= 80 else text[:80] + "..."
        log_and_print(
            f"[server_dispatcher] message sent to '{channel_name}': {text_preview}",
            "info",
        )
import time

import pyautogui as pag
import pyperclip

from core import gui_driver as gd
from log import log_and_print
from dispatcher.dispatch_client import klickViberChannel, window_top_focus
from dispatcher.periodic_broadcast_config import PeriodicBroadcastConfig


class PeriodicBroadcastSender:
    def __init__(self, config: PeriodicBroadcastConfig):
        self._config = config
        self._next_send_at = (
            time.monotonic() + (config.interval_minutes * 60.0)
            if config.enabled
            else float("inf")
        )

    def send_if_due(self, window, s) -> None:
        if not self._config.enabled:
            return

        now = time.monotonic()
        if now < self._next_send_at:
            return

        self._send_to_all_channels(window, s, self._config.message_text)
        self._next_send_at = now + (self._config.interval_minutes * 60.0)

    def _send_to_all_channels(self, window, s, text: str) -> None:
        for channel in s.viber_channels:
            window_top_focus(window)
            if not klickViberChannel("image", window, True, channel):
                log_and_print(
                    f"[periodic_broadcast] skip channel: {channel.get('name_viber_channel')}",
                    "error",
                )
                continue

            self._send_text_to_active_chat(window, s, text)

    def _send_text_to_active_chat(self, window, s, text: str) -> None:
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

        log_and_print("[periodic_broadcast] message sent", "info")

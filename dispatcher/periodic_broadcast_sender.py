import time


from log import log_and_print
from dispatcher.dispatch_client import klickViberChannel, window_top_focus
from dispatcher.message_send_logger import log_sent_message
from dispatcher.periodic_broadcast_config import PeriodicBroadcastConfig
from dispatcher.chat_message_sender import send_text_to_active_chat


class PeriodicBroadcastSender:
    def __init__(self, config: PeriodicBroadcastConfig):
        self._config = config
        self._last_wait_log_at = 0.0
        self._next_send_at = float("inf")
        self.update_config(config, is_startup=True)

    def update_config(self, config: PeriodicBroadcastConfig, is_startup: bool = False) -> None:
        if config == self._config and self._next_send_at != float("inf"):
            return

        self._config = config
        if config.enabled:
            if is_startup and config.send_on_startup:
                self._next_send_at = time.monotonic()
                log_and_print(
                    f"[periodic_broadcast] enabled: send on startup, then every {config.interval_minutes} min",
                    "info",
                )
            else:
                self._next_send_at = time.monotonic() + (config.interval_minutes * 60.0)
                log_and_print(
                    f"[periodic_broadcast] enabled: every {config.interval_minutes} min",
                    "info",
                )
        else:
            self._next_send_at = float("inf")
            log_and_print("[periodic_broadcast] disabled", "info")

    def send_if_due(self, window, s) -> None:
        if not self._config.enabled:
            return

        now = time.monotonic()
        if now < self._next_send_at:
            if now - self._last_wait_log_at >= 60:
                mins_left = (self._next_send_at - now) / 60.0
                log_and_print(
                    f"[periodic_broadcast] waiting, next send in {mins_left:.1f} min",
                    "info",
                )
                self._last_wait_log_at = now
            return

        log_and_print("[periodic_broadcast] start broadcast cycle", "info")
        self._send_to_all_channels(window, s, self._config.message_text)
        self._next_send_at = now + (self._config.interval_minutes * 60.0)
        log_and_print("[periodic_broadcast] broadcast cycle complete", "info")

    def _send_to_all_channels(self, window, s, text: str) -> None:
        for channel in s.viber_channels:
            window_top_focus(window)
            if not klickViberChannel("image", window, True, channel):
                log_and_print(
                    f"[periodic_broadcast] skip channel: {channel.get('name_viber_channel')}",
                    "error",
                )
                continue

            self._send_text_to_active_chat(window, s, text, channel.get("name_viber_channel"))

    def _send_text_to_active_chat(self, window, s, text: str, channel_name: str | None) -> None:
        # Click message input area near the bottom of the chat panel.
        input_x = s.search_board_mess_x_start + 240
        input_y = s.search_board_mess_y_end + 12

        send_text_to_active_chat(window, (input_x, input_y), text)

        text_preview = text if len(text) <= 80 else text[:80] + "..."
        log_and_print(
            f"[periodic_broadcast] message sent to '{channel_name}': {text_preview}",
            "info",
        )
        log_sent_message(channel_name=channel_name, text=text, source="periodic")




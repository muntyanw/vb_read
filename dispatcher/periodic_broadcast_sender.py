import time


from log import log_and_print
from dispatcher.dispatch_client import klickViberChannel, window_top_focus
from dispatcher.message_send_logger import log_sent_message
from dispatcher.periodic_broadcast_config import PeriodicBroadcastConfig
from dispatcher.chat_message_sender import _normalize_input_text
from dispatcher.personal_message_input import insert_message_text
from dispatcher.chat_input_position import resolve_chat_input_xy
from dispatcher.outgoing_text import prepare_outgoing_text_for_ui


class PeriodicBroadcastSender:
    def __init__(self, config: PeriodicBroadcastConfig, personal_sender=None):
        self._config = config
        self._personal_sender = personal_sender
        self._last_wait_log_at = 0.0
        self._next_send_at = float("inf")
        self.update_config(config, is_startup=True)

    def set_personal_sender(self, personal_sender) -> None:
        self._personal_sender = personal_sender
        mode = getattr(getattr(personal_sender, "_config", None), "processing_mode", "unknown")
        log_and_print(f"[periodic_broadcast] personal sender attached mode={mode}", "debug")

    def update_config(self, config: PeriodicBroadcastConfig, is_startup: bool = False) -> None:
        if config == self._config and self._next_send_at != float("inf"):
            return

        self._config = config
        if config.enabled:
            if is_startup and config.send_on_startup:
                self._next_send_at = time.monotonic()
                log_and_print(
                    f"[periodic_broadcast] enabled: send on startup, then every {config.interval_minutes} min",
                    "debug",
                )
            else:
                self._next_send_at = time.monotonic() + (config.interval_minutes * 60.0)
                log_and_print(
                    f"[periodic_broadcast] enabled: every {config.interval_minutes} min",
                    "debug",
                )
        else:
            self._next_send_at = float("inf")
            log_and_print("[periodic_broadcast] disabled", "debug")

    def send_if_due(self, window, s) -> None:
        if not self._config.enabled:
            return

        now = time.monotonic()
        if now < self._next_send_at:
            if now - self._last_wait_log_at >= 60:
                mins_left = (self._next_send_at - now) / 60.0
                log_and_print(
                    f"[periodic_broadcast] waiting, next send in {mins_left:.1f} min",
                    "debug",
                )
                self._last_wait_log_at = now
            return

        log_and_print("[periodic_broadcast] start broadcast cycle", "debug")
        self._send_to_all_channels(window, s, prepare_outgoing_text_for_ui(self._config.message_text))
        self._next_send_at = now + (self._config.interval_minutes * 60.0)
        log_and_print("[periodic_broadcast] broadcast cycle complete", "debug")

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
        if self._personal_sender is None:
            raise RuntimeError('personal sender is not configured for shared input flow')

        sender = self._personal_sender
        original_xy = tuple(sender._config.message_input_xy)
        expected = _normalize_input_text(text)
        input_x, input_y = resolve_chat_input_xy(s)

        try:
            sender._config.message_input_xy = (input_x, input_y)
            ok = insert_message_text(sender, window, text=text)
            if not ok:
                raise RuntimeError(f"chat input not confirmed for channel={channel_name}")

            import pyautogui as pag
            from core import gui_driver as gd
            pag.press('enter')
            gd.pause(0.6)

            text_still_present = False
            try:
                text_still_present = bool(sender._input_contains_text(expected))
            except Exception as exc:
                log_and_print(f"[periodic_broadcast] post-send input verification failed channel={channel_name}: {exc}", "warning")

            log_and_print(
                f"[periodic_broadcast] post-send verify channel={channel_name} text_still_present={text_still_present}",
                'info',
            )
            if text_still_present:
                raise RuntimeError(f"chat send not confirmed for channel={channel_name}")
        finally:
            sender._config.message_input_xy = original_xy

        text_preview = text if len(text) <= 80 else text[:80] + "..."
        log_and_print(
            f"[periodic_broadcast] message sent to '{channel_name}': {text_preview}",
            "info",
        )
        log_sent_message(channel_name=channel_name, text=text, source="periodic")




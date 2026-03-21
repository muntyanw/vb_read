import time
import requests
from typing import List, Dict, Any

from log import log_and_print
from dispatcher.dispatch_client import klickViberChannel, window_top_focus
from dispatcher.message_send_logger import log_sent_message
from dispatcher.dispatch_client import _get_ips
from dispatcher.server_dispatcher_config import ServerDispatcherConfig
from dispatcher.chat_message_sender import send_text_to_active_chat
from dispatcher.personal_direct_message_sender import PersonalDirectMessageSender


class ServerDispatcherSender:
    def __init__(self, config: ServerDispatcherConfig, personal_sender=None):
        self._config = config
        self._last_wait_log_at = 0.0
        self._next_poll_at = float("inf")
        self._backoff_delay = 5.0  # start with 5s
        self._last_sent_ids = set()  # to avoid duplicates in one cycle
        self._personal_sender = personal_sender
        self.update_config(config, is_startup=True)

    def set_personal_sender(self, personal_sender) -> None:
        self._personal_sender = personal_sender
        mode = getattr(getattr(personal_sender, "_config", None), "processing_mode", "unknown")
        log_and_print(f"[server_dispatcher] personal sender attached mode={mode}", "debug")

    def _personal_direct_sender(self) -> PersonalDirectMessageSender:
        if self._personal_sender is None:
            raise RuntimeError("personal sender is not configured")
        return PersonalDirectMessageSender(self._personal_sender)

    @staticmethod
    def _parse_recipient_phones(raw_value) -> list[str]:
        if raw_value is None:
            return []
        phones = []
        for part in str(raw_value).split(","):
            phone = part.strip()
            if phone:
                phones.append(phone)
        return phones

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
        ip = ips[0]
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

        self._backoff_delay = 5.0

        server_time = data.get("server_time")
        has_messages = data.get("has_messages", False)
        messages = data.get("messages", [])

        log_and_print(
            f"[server_dispatcher] polled: server_time={server_time}, has_messages={has_messages}, count={len(messages)}",
            "info",
        )

        if not has_messages or not messages:
            return

        sent_ids = []
        errors = []

        self._last_sent_ids.clear()

        for msg in messages:
            msg_id = msg.get("id")
            if msg_id in self._last_sent_ids:
                log_and_print(f"[server_dispatcher] skip duplicate id={msg_id} in current cycle", "debug")
                continue
            message_text = msg.get("message_text", "").strip()
            if not message_text:
                log_and_print(f"[server_dispatcher] skip empty message_text id={msg_id}", "warning")
                continue

            raw_recipient_phones = msg.get("recipient_phones")
            recipient_phones = self._parse_recipient_phones(raw_recipient_phones)
            text_preview = message_text if len(message_text) <= 80 else message_text[:80] + "..."
            log_and_print(
                f"[server_dispatcher] message id={msg_id} raw_recipient_phones={raw_recipient_phones!r} "
                f"parsed_phones={recipient_phones} text_preview={text_preview}",
                "info",
            )

            try:
                if recipient_phones:
                    log_and_print(
                        f"[server_dispatcher] route=personal_direct id={msg_id} phones_count={len(recipient_phones)}",
                        "info",
                    )
                    self._send_personal_messages(window, recipient_phones, message_text, msg_id=msg_id)
                    log_sent_message(
                        channel_name="personal_direct",
                        text=message_text,
                        source=f"server_dispatcher:{','.join(recipient_phones)}",
                    )
                else:
                    log_and_print(f"[server_dispatcher] route=all_channels id={msg_id}", "info")
                    self._send_to_all_channels(window, s, message_text)
                    log_sent_message(channel_name="all_channels", text=message_text, source="server_dispatcher")
                sent_ids.append(msg_id)
                self._last_sent_ids.add(msg_id)
                log_and_print(f"[server_dispatcher] message id={msg_id} completed", "info")
            except Exception as e:
                errors.append({"id": msg_id, "error": str(e)})
                log_and_print(f"[server_dispatcher] send error for id={msg_id}: {e}", "error")

        log_and_print(f"[server_dispatcher] sent_ids={sent_ids}, errors={errors}", "info")

    def _send_personal_messages(self, window, recipient_phones: list[str], message_text: str, msg_id=None) -> None:
        direct_sender = self._personal_direct_sender()
        for idx, phone in enumerate(recipient_phones, start=1):
            window_top_focus(window)
            log_and_print(
                f"[server_dispatcher] personal send start id={msg_id} phone_index={idx}/{len(recipient_phones)} phone={phone}",
                "info",
            )
            direct_sender.send_to_phone(window, phone, message_text=message_text)
            log_and_print(
                f"[server_dispatcher] personal send ok id={msg_id} phone_index={idx}/{len(recipient_phones)} phone={phone}",
                "info",
            )

    def _handle_backoff(self) -> None:
        self._backoff_delay = min(self._backoff_delay * 2, 60.0)
        self._next_poll_at = time.monotonic() + self._backoff_delay
        log_and_print(f"[server_dispatcher] backoff: next poll in {self._backoff_delay} s", "warning")

    def _send_to_all_channels(self, window, s, text: str) -> None:
        for channel in s.viber_channels:
            window_top_focus(window)
            channel_name = channel.get("name_viber_channel")
            log_and_print(f"[server_dispatcher] channel send start channel={channel_name}", "debug")
            if not klickViberChannel("image", window, True, channel):
                log_and_print(
                    f"[server_dispatcher] skip channel: {channel_name}",
                    "error",
                )
                continue

            self._send_text_to_active_chat(window, s, text, channel_name)

    def _send_text_to_active_chat(self, window, s, text: str, channel_name: str | None) -> None:
        input_x = s.search_board_mess_x_start + 240
        input_y = s.search_board_mess_y_end + 12

        send_text_to_active_chat(window, (input_x, input_y), text)

        text_preview = text if len(text) <= 80 else text[:80] + "..."
        log_and_print(
            f"[server_dispatcher] message sent to '{channel_name}': {text_preview}",
            "info",
        )

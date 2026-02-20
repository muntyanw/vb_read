from dataclasses import dataclass

from utils import read_setting, write_setting


@dataclass
class PeriodicBroadcastConfig:
    message_text: str
    interval_minutes: float
    send_on_startup: bool

    @property
    def enabled(self) -> bool:
        return bool(self.message_text.strip()) and self.interval_minutes > 0


def load_periodic_broadcast_config() -> PeriodicBroadcastConfig:
    raw_text = read_setting("periodic_broadcast_text") or ""
    raw_interval = read_setting("periodic_broadcast_interval_minutes")
    raw_send_on_startup = read_setting("periodic_broadcast_send_on_startup")
    if raw_send_on_startup is None:
        write_setting("periodic_broadcast_send_on_startup", False)
        raw_send_on_startup = False

    try:
        interval_minutes = float(raw_interval)
    except Exception:
        interval_minutes = 0.0

    send_on_startup = bool(raw_send_on_startup)

    return PeriodicBroadcastConfig(
        message_text=str(raw_text),
        interval_minutes=interval_minutes,
        send_on_startup=send_on_startup,
    )

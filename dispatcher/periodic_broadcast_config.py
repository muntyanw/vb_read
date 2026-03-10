from dataclasses import dataclass

from utils import read_setting, write_setting


@dataclass
class PeriodicBroadcastConfig:
    enabled_flag: bool
    message_text: str
    interval_minutes: float
    send_on_startup: bool

    @property
    def enabled(self) -> bool:
        return self.enabled_flag and bool(self.message_text.strip()) and self.interval_minutes > 0


def load_periodic_broadcast_config() -> PeriodicBroadcastConfig:
    raw_enabled = read_setting("periodic_broadcast_enabled")
    if raw_enabled is None:
        write_setting("periodic_broadcast_enabled", False)
        raw_enabled = False

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

    enabled_flag = bool(raw_enabled)
    send_on_startup = bool(raw_send_on_startup)

    return PeriodicBroadcastConfig(
        enabled_flag=enabled_flag,
        message_text=str(raw_text),
        interval_minutes=interval_minutes,
        send_on_startup=send_on_startup,
    )

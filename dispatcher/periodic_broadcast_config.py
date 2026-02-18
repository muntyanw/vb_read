from dataclasses import dataclass

from utils import read_setting


@dataclass
class PeriodicBroadcastConfig:
    message_text: str
    interval_minutes: float

    @property
    def enabled(self) -> bool:
        return bool(self.message_text.strip()) and self.interval_minutes > 0


def load_periodic_broadcast_config() -> PeriodicBroadcastConfig:
    raw_text = read_setting("periodic_broadcast_text") or ""
    raw_interval = read_setting("periodic_broadcast_interval_minutes")

    try:
        interval_minutes = float(raw_interval)
    except Exception:
        interval_minutes = 0.0

    return PeriodicBroadcastConfig(
        message_text=str(raw_text),
        interval_minutes=interval_minutes,
    )


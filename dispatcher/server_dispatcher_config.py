from dataclasses import dataclass

from utils import read_setting
from dispatcher.dispatch_client import _get_ips


@dataclass
class ServerDispatcherConfig:
    send_enabled: bool
    poll_interval_seconds: float
    user_id: str | None
    poll_limit: int

    @property
    def enabled(self) -> bool:
        return self.send_enabled and bool(_get_ips()) and self.poll_interval_seconds > 0


def load_server_dispatcher_config() -> ServerDispatcherConfig:
    raw_send_enabled = read_setting("dispatcher_send_enabled")
    if isinstance(raw_send_enabled, bool):
        send_enabled = raw_send_enabled
    elif isinstance(raw_send_enabled, str):
        send_enabled = raw_send_enabled.strip().lower() in {"1", "true", "yes", "on"}
    else:
        send_enabled = False

    try:
        poll_interval_seconds = float(read_setting("dispatcher_poll_interval_seconds") or 60.0)
    except Exception:
        poll_interval_seconds = 60.0
    user_id = read_setting("dispatcher_user_id")
    if user_id is not None:
        user_id = str(user_id).strip()
        if not user_id:
            user_id = None
    try:
        poll_limit = int(read_setting("dispatcher_poll_limit") or 10)
    except Exception:
        poll_limit = 10
    poll_limit = max(1, min(poll_limit, 100))

    return ServerDispatcherConfig(
        send_enabled=send_enabled,
        poll_interval_seconds=poll_interval_seconds,
        user_id=user_id,
        poll_limit=poll_limit,
    )

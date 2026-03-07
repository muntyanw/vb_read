from dataclasses import dataclass

from utils import read_setting
from dispatcher.dispatch_client import _get_ips


@dataclass
class ServerDispatcherConfig:
    poll_interval_seconds: float
    user_id: str | None
    poll_limit: int

    @property
    def enabled(self) -> bool:
        return bool(_get_ips()) and self.poll_interval_seconds > 0


def load_server_dispatcher_config() -> ServerDispatcherConfig:
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
        poll_interval_seconds=poll_interval_seconds,
        user_id=user_id,
        poll_limit=poll_limit,
    )
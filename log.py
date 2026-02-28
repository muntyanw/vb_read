import logging
from datetime import datetime

FMT = "%(asctime)s - %(levelname)s - %(message)s"
DEBUG_MODE = False
RUN_ID = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
_SESSION_LOGGED = False


def _configure_third_party_loggers() -> None:
    # Silence verbose library debug logs (font matching, image internals, etc.)
    logging.getLogger("matplotlib").setLevel(logging.WARNING)
    logging.getLogger("matplotlib.font_manager").setLevel(logging.WARNING)
    logging.getLogger("PIL").setLevel(logging.WARNING)

logging.basicConfig(
    level=logging.INFO,
    format=FMT,
    handlers=[
        logging.FileHandler("log.log", mode="a", encoding="utf-8"),
        logging.StreamHandler(),
    ],
    force=True,
)


def set_debug_mode(enabled: bool) -> None:
    global DEBUG_MODE, _SESSION_LOGGED
    DEBUG_MODE = bool(enabled)
    logging.getLogger().setLevel(logging.DEBUG if DEBUG_MODE else logging.INFO)
    _configure_third_party_loggers()
    if not _SESSION_LOGGED:
        logging.info(f"[log] session_start run_id={RUN_ID}")
        _SESSION_LOGGED = True
    logging.info(f"[log] run_id={RUN_ID} debug_logs_mode={'on' if DEBUG_MODE else 'off'}")


def log_and_print(message: str, level: str = "debug"):
    level = level.lower()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    if level in ("info", "warning", "error", "critical") or (level == "debug" and DEBUG_MODE):
        print(f"[{now}] {message}")

    if level == "info":
        logging.info(message)
    elif level == "warning":
        logging.warning(message)
    elif level == "error":
        logging.error(message)
    elif level == "critical":
        logging.critical(message)
    elif level == "debug":
        logging.debug(message)

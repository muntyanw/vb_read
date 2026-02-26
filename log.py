import logging
from datetime import datetime

FMT = "%(asctime)s - %(levelname)s - %(message)s"
DEBUG_MODE = False

logging.basicConfig(
    level=logging.INFO,
    format=FMT,
    handlers=[
        logging.FileHandler("log.log", mode="w", encoding="utf-8"),
        logging.StreamHandler(),
    ],
    force=True,
)


def set_debug_mode(enabled: bool) -> None:
    global DEBUG_MODE
    DEBUG_MODE = bool(enabled)
    logging.getLogger().setLevel(logging.DEBUG if DEBUG_MODE else logging.INFO)
    logging.info(f"[log] debug_logs_mode={'on' if DEBUG_MODE else 'off'}")


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

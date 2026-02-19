from datetime import datetime
from pathlib import Path


SEND_LOG_FILE = Path("sent_messages.log")


def log_sent_message(channel_name: str | None, text: str, source: str = "periodic") -> None:
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    channel = channel_name or "unknown"
    payload = text.replace("\r", " ").replace("\n", " ")
    line = f"[{ts}] source={source}; channel={channel}; text={payload}\n"
    with SEND_LOG_FILE.open("a", encoding="utf-8") as fh:
        fh.write(line)


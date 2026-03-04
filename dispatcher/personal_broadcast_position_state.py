from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path


_ROW_RE = re.compile(r"scroll=(?P<scroll>\d+)\s*\|\s*position=(?P<position>\d+)", re.IGNORECASE)


class PersonalBroadcastPositionRegistry:
    def __init__(self, filename: str):
        self.path = Path(filename)
        self._seen: set[tuple[int, int]] = set()
        self._last_processed: tuple[int, int] = (1, 0)
        self._load()

    def _load(self) -> None:
        self._seen.clear()
        self._last_processed = (1, 0)
        if not self.path.exists():
            return
        for line in self.path.read_text(encoding="utf-8-sig").splitlines():
            parsed = self._parse_line(line)
            if parsed is None:
                continue
            self._seen.add(parsed)
            # Keep exact last marker from file order (not max tuple),
            # so resume continues from where previous run actually ended.
            self._last_processed = parsed

    @staticmethod
    def _parse_line(line: str) -> tuple[int, int] | None:
        raw = str(line or "").strip()
        if not raw:
            return None
        m = _ROW_RE.search(raw)
        if not m:
            return None
        return int(m.group("scroll")), int(m.group("position"))

    def has(self, scroll_no: int, position_no: int) -> bool:
        return (int(scroll_no), int(position_no)) in self._seen

    def add(self, scroll_no: int, position_no: int, viber_name: str) -> None:
        key = (int(scroll_no), int(position_no))
        if key in self._seen:
            return
        self._seen.add(key)

        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        name = str(viber_name or "").replace("\n", " ").strip()
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(f"{ts} | scroll={key[0]} | position={key[1]} | viber={name}\n")

    def load_last_processed(self) -> tuple[int, int]:
        return int(self._last_processed[0]), int(self._last_processed[1])

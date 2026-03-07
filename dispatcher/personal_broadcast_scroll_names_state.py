from __future__ import annotations

from pathlib import Path


class PersonalBroadcastScrollNamesState:
    """Keeps current scroll number for by_scroll_names mode."""

    def __init__(self, filename: str):
        self.path = Path(filename)

    def load_scroll_no(self) -> int:
        if not self.path.exists():
            return 1
        try:
            raw = self.path.read_text(encoding="utf-8-sig").strip()
            value = int(raw)
            return max(1, value)
        except Exception:
            return 1

    def save_scroll_no(self, scroll_no: int) -> None:
        value = max(1, int(scroll_no))
        self.path.write_text(f"{value}\n", encoding="utf-8")

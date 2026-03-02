from pathlib import Path
from difflib import SequenceMatcher
import unicodedata


class PersonalBroadcastRegistry:
    def __init__(self, filename: str):
        self.path = Path(filename)
        self._names = set()
        self._keys = set()
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            self._names = set()
            self._keys = set()
            return
        data = self.path.read_text(encoding="utf-8-sig").splitlines()
        self._names = {x.strip().lower() for x in data if x.strip()}
        self._keys = {self._norm_key(x) for x in self._names if self._norm_key(x)}

    @staticmethod
    def _norm_key(name: str) -> str:
        s = unicodedata.normalize("NFKC", str(name or "")).strip().lower()
        s = s.replace("’", "").replace("'", "").replace("`", "")
        s = "".join(ch for ch in s if ch.isalnum())
        if not s:
            return ""
        # conservative normalization only
        return (
            s.replace("ё", "е")
             .replace("й", "и")
             .replace("і", "и")
             .replace("ї", "и")
        )

    def has(self, name: str) -> bool:
        raw = name.strip().lower()
        if raw in self._names:
            return True

        key = self._norm_key(raw)
        if not key:
            return False
        if key in self._keys:
            return True

        for existing in self._keys:
            if abs(len(existing) - len(key)) > 2:
                continue
            if SequenceMatcher(None, key, existing).ratio() >= 0.92:
                return True
        return False

    def add(self, name: str) -> None:
        raw = name.strip().lower()
        if not raw:
            return
        norm = self._norm_key(raw)
        # prevent duplicates in file for OCR variants
        if raw in self._names or (norm and norm in self._keys):
            return
        self._names.add(raw)
        if norm:
            self._keys.add(norm)
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(name.strip() + "\n")

from pathlib import Path
from difflib import SequenceMatcher
import unicodedata
import re
from datetime import datetime


class PersonalBroadcastRegistry:
    _TOKEN_RE = re.compile(r"[a-z\u0400-\u04FF0-9]+")
    _KEEP_RE = re.compile(r"[^a-z0-9\u0400-\u04FF]")

    # Visual skeleton map (Cyrillic/Latin confusables -> canonical latin-like forms)
    _SKELETON_MAP = str.maketrans({
        "\u0430": "a", "\u0410": "a",  # ? ?
        "\u0435": "e", "\u0415": "e",  # ? ?
        "\u043E": "o", "\u041E": "o",  # ? ?
        "\u0440": "p", "\u0420": "p",  # ? ?
        "\u0441": "c", "\u0421": "c",  # ? ?
        "\u0443": "y", "\u0423": "y",  # ? ?
        "\u0445": "x", "\u0425": "x",  # ? ?
        "\u043A": "k", "\u041A": "k",  # ? ?
        "\u043C": "m", "\u041C": "m",  # ? ?
        "\u0442": "t", "\u0422": "t",  # ? ?
        "\u0432": "b", "\u0412": "b",  # ? ?
        "\u0456": "i", "\u0406": "i",  # ? ?
        "\u0457": "i", "\u0407": "i",  # ? ?
        "\u0439": "i", "\u0419": "i",  # ? ?
        "\u0451": "e", "\u0401": "e",  # ? ?
        "\u044C": "", "\u042C": "",    # ? ?
        "\u044A": "", "\u042A": "",    # ? ?
    })

    def __init__(self, filename: str):
        self.path = Path(filename)
        self._names = set()
        self._keys = set()
        self._token_sets = []
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            self._names = set()
            self._keys = set()
            self._token_sets = []
            return
        data = self.path.read_text(encoding="utf-8-sig").splitlines()
        names = [self._extract_name(x) for x in data]
        self._names = {x.strip().lower() for x in names if str(x).strip()}
        self._keys = {self._norm_key(x) for x in self._names if self._norm_key(x)}
        self._token_sets = [set(self._norm_tokens(x)) for x in self._names if self._norm_tokens(x)]

    @staticmethod
    def _extract_name(line: str) -> str:
        raw = str(line or "").strip()
        if not raw:
            return ""
        if "|" in raw:
            parts = raw.split("|", 1)
            if len(parts) == 2:
                return parts[1].strip()
        return raw

    @staticmethod
    def _reduce_repeats(s: str) -> str:
        if not s:
            return s

        # Collapse full-string repeats: abcabcabc -> abc
        for k in range(1, len(s) // 2 + 1):
            if len(s) % k != 0:
                continue
            unit = s[:k]
            if unit * (len(s) // k) == s:
                return unit

        # Collapse immediate duplicated prefixes/suffixes: tishiktishik -> tishik
        changed = True
        while changed and len(s) >= 4:
            changed = False
            for k in range(2, len(s) // 2 + 1):
                if s.endswith(s[-k:] * 2):
                    s = s[:-k]
                    changed = True
                    break
                if s.startswith(s[:k] * 2):
                    s = s[k:]
                    changed = True
                    break
        return s

    @classmethod
    def _skeleton(cls, s: str) -> str:
        s = unicodedata.normalize("NFKC", str(s or ""))
        s = s.translate(cls._SKELETON_MAP).lower()
        s = s.replace("'", "").replace("`", "").replace("\u2019", "")
        s = cls._KEEP_RE.sub("", s)
        return s

    @classmethod
    def _norm_tokens(cls, name: str) -> list[str]:
        s = cls._skeleton(name)
        if not s:
            return []

        raw_tokens = cls._TOKEN_RE.findall(s)
        tokens = []
        for tok in raw_tokens:
            tok = cls._reduce_repeats(tok)
            if len(tok) >= 3:
                tokens.append(tok)

        seen = set()
        out = []
        for t in tokens:
            if t in seen:
                continue
            seen.add(t)
            out.append(t)
        return out

    @classmethod
    def _norm_key(cls, name: str) -> str:
        tokens = cls._norm_tokens(name)
        if tokens:
            return "".join(sorted(tokens))
        return cls._skeleton(name)

    @staticmethod
    def _containment_ratio(a: str, b: str) -> float:
        if not a or not b:
            return 0.0
        shorter = min(len(a), len(b))
        longer = max(len(a), len(b))
        return float(shorter) / float(longer) if longer else 0.0

    @staticmethod
    def _loose_token_match(tokens: set[str], existing_tokens: set[str]) -> bool:
        if not tokens or not existing_tokens:
            return False

        overlap = tokens.intersection(existing_tokens)
        if len(overlap) >= 2:
            return True
        for t in overlap:
            if len(t) >= 4:
                return True

        # OCR concatenation: short token may be inside long token.
        for a in tokens:
            if len(a) < 4:
                continue
            for b in existing_tokens:
                if len(b) < 4:
                    continue
                short = a if len(a) <= len(b) else b
                long = b if len(a) <= len(b) else a
                if short in long and (len(short) / len(long)) >= 0.30:
                    return True
        return False

    def has(self, name: str) -> bool:
        raw = str(name or "").strip().lower()
        if not raw:
            return False
        if raw in self._names:
            return True

        key = self._norm_key(raw)
        if not key:
            return False
        if key in self._keys:
            return True

        tokens = set(self._norm_tokens(raw))
        for existing_tokens in self._token_sets:
            if self._loose_token_match(tokens, existing_tokens):
                return True

        for existing in self._keys:
            if not existing:
                continue
            if key in existing or existing in key:
                if self._containment_ratio(key, existing) >= 0.30:
                    return True
            # OCR can inject noise into long glued keys; accept if a solid prefix matches.
            if len(key) >= 4 and existing.startswith(key):
                return True
            if len(existing) >= 4 and key.startswith(existing):
                return True

        for existing in self._keys:
            if abs(len(existing) - len(key)) > 10:
                continue
            if SequenceMatcher(None, key, existing).ratio() >= 0.70:
                return True
        return False

    def find_similar(self, name: str, min_ratio: float = 0.86, max_len_diff: int = 4):
        raw = str(name or "").strip().lower()
        key = self._norm_key(raw)
        if not key:
            return None

        tokens = set(self._norm_tokens(raw))
        for existing_tokens in self._token_sets:
            if self._loose_token_match(tokens, existing_tokens):
                return "token_match", 0.99

        best_ratio = 0.0
        best_key = None
        for existing in self._keys:
            if abs(len(existing) - len(key)) > max_len_diff:
                continue
            ratio = SequenceMatcher(None, key, existing).ratio()
            if ratio > best_ratio:
                best_ratio = ratio
                best_key = existing
        if best_key is not None and best_ratio >= min_ratio:
            return best_key, best_ratio

        for existing in self._keys:
            if key in existing or existing in key:
                ratio = self._containment_ratio(key, existing)
                if ratio >= 0.30:
                    return "containment", ratio
            if len(key) >= 4 and existing.startswith(key):
                return "prefix", 0.95
            if len(existing) >= 4 and key.startswith(existing):
                return "prefix", 0.95
        return None

    def add(self, name: str) -> None:
        raw = str(name or "").strip().lower()
        if not raw:
            return

        norm = self._norm_key(raw)
        if raw in self._names:
            return
        if norm and norm in self._keys:
            return

        self._names.add(raw)
        if norm:
            self._keys.add(norm)

        tokens = self._norm_tokens(raw)
        if tokens:
            self._token_sets.append(set(tokens))

        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(f"{ts} | {str(name).strip()}\n")

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
        # Cyrillic -> latin-like skeleton (OCR-friendly)
        "\u0430": "a", "\u0410": "a", "\u0431": "b", "\u0411": "b", "\u0432": "v", "\u0412": "v",
        "\u0433": "g", "\u0413": "g", "\u0491": "g", "\u0490": "g", "\u0434": "d", "\u0414": "d",
        "\u0435": "e", "\u0415": "e", "\u0451": "e", "\u0401": "e", "\u0454": "e", "\u0404": "e",
        "\u0436": "zh", "\u0416": "zh", "\u0437": "z", "\u0417": "z", "\u0438": "i", "\u0418": "i",
        "\u0456": "i", "\u0406": "i", "\u0457": "i", "\u0407": "i", "\u0439": "i", "\u0419": "i",
        "\u043a": "k", "\u041a": "k", "\u043b": "l", "\u041b": "l", "\u043c": "m", "\u041c": "m",
        "\u043d": "n", "\u041d": "n", "\u043e": "o", "\u041e": "o", "\u043f": "p", "\u041f": "p",
        "\u0440": "r", "\u0420": "r", "\u0441": "s", "\u0421": "s", "\u0442": "t", "\u0422": "t",
        "\u0443": "u", "\u0423": "u", "\u0444": "f", "\u0424": "f", "\u0445": "h", "\u0425": "h",
        "\u0446": "c", "\u0426": "c", "\u0447": "ch", "\u0427": "ch", "\u0448": "sh", "\u0428": "sh",
        "\u0449": "sh", "\u0429": "sh", "\u044b": "y", "\u042b": "y", "\u044d": "e", "\u042d": "e",
        "\u044e": "yu", "\u042e": "yu", "\u044f": "ya", "\u042f": "ya", "\u044c": "", "\u042c": "", "\u044a": "", "\u042a": "",
    })

    def __init__(self, filename: str):
        self.path = Path(filename)
        self._names = set()
        self._keys = set()
        self._token_sets = []
        self._norm_values = set()
        self._raw_names = set()
        self._case_token_sets = []
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            self._names = set()
            self._keys = set()
            self._token_sets = []
            self._norm_values = set()
            self._raw_names = set()
            self._case_token_sets = []
            return
        data = self.path.read_text(encoding="utf-8-sig").splitlines()
        names = [self._extract_name(x) for x in data]
        raw_names = [str(x).strip() for x in names if str(x).strip()]
        self._raw_names = set(raw_names)
        self._names = {x.lower() for x in raw_names}
        self._keys = {self._norm_key(x) for x in self._names if self._norm_key(x)}
        self._token_sets = [set(self._norm_tokens(x)) for x in self._names if self._norm_tokens(x)]
        self._norm_values = {self._norm_value(x) for x in self._names if self._norm_value(x)}
        self._case_token_sets = [set(self._case_split_tokens(x)) for x in self._raw_names if self._case_split_tokens(x)]

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
    def _containment_threshold(a: str, b: str) -> float:
        # For short names (e.g. Yuriy), OCR often glues extra noise around the core token.
        shorter = min(len(a or ""), len(b or ""))
        if shorter <= 6:
            return 0.20
        if shorter <= 8:
            return 0.25
        return 0.30

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

    @staticmethod
    def _squash_repeated_chars(s: str) -> str:
        if not s:
            return s
        out = []
        prev = None
        run = 0
        for ch in s:
            if ch == prev:
                run += 1
            else:
                prev = ch
                run = 1
            if run <= 2:
                out.append(ch)
        return "".join(out)

    @classmethod
    def _norm_value(cls, name: str) -> str:
        v = cls._skeleton(name)
        v = cls._reduce_repeats(v)
        v = cls._squash_repeated_chars(v)
        return v

    @staticmethod
    def _jaro_winkler(a: str, b: str) -> float:
        if not a or not b:
            return 0.0
        if a == b:
            return 1.0
        la, lb = len(a), len(b)
        match_dist = max(0, max(la, lb) // 2 - 1)
        a_match = [False] * la
        b_match = [False] * lb

        matches = 0
        for i, ca in enumerate(a):
            start = max(0, i - match_dist)
            end = min(i + match_dist + 1, lb)
            for j in range(start, end):
                if b_match[j] or b[j] != ca:
                    continue
                a_match[i] = True
                b_match[j] = True
                matches += 1
                break

        if matches == 0:
            return 0.0

        t = 0
        j = 0
        for i in range(la):
            if not a_match[i]:
                continue
            while not b_match[j]:
                j += 1
            if a[i] != b[j]:
                t += 1
            j += 1
        transpositions = t / 2.0

        m = float(matches)
        jaro = (m / la + m / lb + (m - transpositions) / m) / 3.0

        prefix = 0
        for ca, cb in zip(a, b):
            if ca == cb:
                prefix += 1
                if prefix == 4:
                    break
            else:
                break
        return jaro + (prefix * 0.1 * (1.0 - jaro))

    @staticmethod
    def _dice_ngrams(a: str, b: str, n: int = 3) -> float:
        if not a or not b:
            return 0.0
        if a == b:
            return 1.0
        if len(a) < n or len(b) < n:
            return SequenceMatcher(None, a, b).ratio()
        sa = {a[i:i+n] for i in range(len(a) - n + 1)}
        sb = {b[i:i+n] for i in range(len(b) - n + 1)}
        if not sa or not sb:
            return 0.0
        inter = len(sa.intersection(sb))
        return (2.0 * inter) / float(len(sa) + len(sb))

    @staticmethod
    def _levenshtein_ratio(a: str, b: str) -> float:
        if not a or not b:
            return 0.0
        if a == b:
            return 1.0

        la, lb = len(a), len(b)
        prev = list(range(lb + 1))
        for i in range(1, la + 1):
            cur = [i] + [0] * lb
            ca = a[i - 1]
            for j in range(1, lb + 1):
                cb = b[j - 1]
                cost = 0 if ca == cb else 1
                cur[j] = min(
                    prev[j] + 1,      # deletion
                    cur[j - 1] + 1,   # insertion
                    prev[j - 1] + cost,  # substitution
                )
            prev = cur

        dist = prev[lb]
        denom = max(la, lb)
        if denom <= 0:
            return 0.0
        return 1.0 - (float(dist) / float(denom))

    @classmethod
    def _is_probably_same(cls, a: str, b: str) -> bool:
        a = cls._norm_value(a)
        b = cls._norm_value(b)
        if not a or not b:
            return False
        if a == b:
            return True

        shorter = a if len(a) <= len(b) else b
        longer = b if len(a) <= len(b) else a

        if shorter in longer:
            if len(shorter) >= 5:
                return True
            if len(shorter) >= 4 and (len(shorter) / float(len(longer))) >= 0.60:
                return True

        seq = SequenceMatcher(None, a, b).ratio()
        jw = cls._jaro_winkler(a, b)
        dice = cls._dice_ngrams(a, b, n=3)
        lev = cls._levenshtein_ratio(a, b)

        if len(shorter) <= 6 and (jw >= 0.90 or seq >= 0.85 or dice >= 0.65 or lev >= 0.83):
            return True

        # Aggressive OCR fallback for short names (e.g. Georg ~ Ceogd, Adeipa ~ Nadezhda).
        if len(longer) <= 10:
            if (seq >= 0.60 and lev >= 0.40) or (seq >= 0.57 and lev >= 0.50):
                return True

        score = (
            0.40 * (1.0 if shorter in longer and len(shorter) >= 4 else 0.0)
            + 0.22 * jw
            + 0.16 * dice
            + 0.22 * lev
        )
        return score >= 0.72

    @classmethod
    def _case_split_tokens(cls, value: str) -> list[str]:
        text = str(value or "")
        if not text:
            return []

        tokens = []
        cur = []

        def _script(ch: str) -> str:
            o = ord(ch)
            if (0x0400 <= o <= 0x04FF) or ch in "??????????":
                return "cyr"
            if "a" <= ch.lower() <= "z":
                return "lat"
            return "other"

        prev = ""
        for ch in text:
            if not ch.isalpha():
                if cur:
                    tokens.append("".join(cur))
                    cur = []
                prev = ""
                continue
            if cur:
                if prev and prev.islower() and ch.isupper():
                    tokens.append("".join(cur))
                    cur = []
                elif prev and _script(prev) != _script(ch):
                    tokens.append("".join(cur))
                    cur = []
            cur.append(ch)
            prev = ch
        if cur:
            tokens.append("".join(cur))

        out = []
        seen = set()
        for t in tokens:
            n = cls._norm_value(t)
            if len(n) < 3:
                continue
            if n in seen:
                continue
            seen.add(n)
            out.append(n)
        return out

    @classmethod
    def _max_token_lev_ratio(cls, left_tokens: set[str], right_tokens: set[str]) -> float:
        if not left_tokens or not right_tokens:
            return 0.0
        best = 0.0
        for a in left_tokens:
            if len(a) < 3:
                continue
            for b in right_tokens:
                if len(b) < 3:
                    continue
                r = cls._levenshtein_ratio(a, b)
                if r > best:
                    best = r
        return best

    def has(self, name: str) -> bool:
        raw = str(name or "").strip().lower()
        if not raw:
            return False
        if raw in self._names:
            return True

        key = self._norm_key(raw)
        norm_val = self._norm_value(raw)
        if not key:
            return False
        if key in self._keys:
            return True
        if norm_val in self._norm_values:
            return True

        tokens = set(self._norm_tokens(raw))
        for existing_tokens in self._token_sets:
            if self._loose_token_match(tokens, existing_tokens):
                return True

        case_tokens = set(self._case_split_tokens(name))
        if case_tokens:
            for existing_case_tokens in self._case_token_sets:
                lev_ratio = self._max_token_lev_ratio(case_tokens, existing_case_tokens)
                if lev_ratio >= 0.84:
                    return True

        for existing in self._keys:
            if not existing:
                continue
            if key in existing or existing in key:
                if self._containment_ratio(key, existing) >= self._containment_threshold(key, existing):
                    return True
            # OCR can inject noise into long glued keys; accept if a solid prefix matches.
            if len(key) >= 4 and existing.startswith(key):
                return True
            if len(existing) >= 4 and key.startswith(existing):
                return True

        for existing in self._norm_values:
            if self._is_probably_same(norm_val, existing):
                return True

        for existing in self._keys:
            if abs(len(existing) - len(key)) > 10:
                continue
            seq_ratio = SequenceMatcher(None, key, existing).ratio()
            lev_ratio = self._levenshtein_ratio(key, existing)
            if seq_ratio >= 0.70 or lev_ratio >= 0.72:
                return True
        return False

    def find_similar(self, name: str, min_ratio: float = 0.86, max_len_diff: int = 4):
        raw = str(name or "").strip().lower()
        key = self._norm_key(raw)
        norm_val = self._norm_value(raw)
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

        best_lev = 0.0
        best_lev_key = None
        for existing in self._keys:
            if abs(len(existing) - len(key)) > max_len_diff + 6:
                continue
            ratio = self._levenshtein_ratio(key, existing)
            if ratio > best_lev:
                best_lev = ratio
                best_lev_key = existing
        if best_lev_key is not None and best_lev >= max(0.78, min_ratio - 0.08):
            return best_lev_key, best_lev

        for existing in self._norm_values:
            if self._is_probably_same(norm_val, existing):
                return "fuzzy", 0.95

        for existing in self._keys:
            if key in existing or existing in key:
                ratio = self._containment_ratio(key, existing)
                if ratio >= self._containment_threshold(key, existing):
                    return "containment", ratio
            if len(key) >= 4 and existing.startswith(key):
                return "prefix", 0.95
            if len(existing) >= 4 and key.startswith(existing):
                return "prefix", 0.95

        case_tokens = set(self._case_split_tokens(name))
        if case_tokens:
            best_case = 0.0
            for existing_case_tokens in self._case_token_sets:
                r = self._max_token_lev_ratio(case_tokens, existing_case_tokens)
                if r > best_case:
                    best_case = r
            if best_case >= 0.84:
                return "case_lev", best_case
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
        self._raw_names.add(str(name).strip())
        if norm:
            self._keys.add(norm)
        norm_val = self._norm_value(raw)
        if norm_val:
            self._norm_values.add(norm_val)

        tokens = self._norm_tokens(raw)
        if tokens:
            self._token_sets.append(set(tokens))
        case_tokens = self._case_split_tokens(str(name))
        if case_tokens:
            self._case_token_sets.append(set(case_tokens))

        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(f"{ts} | {str(name).strip()}\n")

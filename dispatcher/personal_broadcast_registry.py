from pathlib import Path


class PersonalBroadcastRegistry:
    def __init__(self, filename: str):
        self.path = Path(filename)
        self._names = set()
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            self._names = set()
            return
        data = self.path.read_text(encoding="utf-8").splitlines()
        self._names = {x.strip().lower() for x in data if x.strip()}

    def has(self, name: str) -> bool:
        return name.strip().lower() in self._names

    def add(self, name: str) -> None:
        key = name.strip().lower()
        if not key or key in self._names:
            return
        self._names.add(key)
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(name.strip() + "\n")


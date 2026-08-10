import json
from pathlib import Path


class BaseStore:
    def __init__(self, file_path: str):
        self.file_path = Path(file_path)
        self.data = self._load()

    def _load(self):
        with open(self.file_path, "r", encoding="utf-8") as file:
            return json.load(file)

    def save(self):
        with open(self.file_path, "w", encoding="utf-8") as file:
            json.dump(
                self.data,
                file,
                ensure_ascii=False,
                indent=2
            )
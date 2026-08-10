import json
from pathlib import Path

from .memory_models import MemoryDocument


class BaseStore:
    def __init__(self, file_path: str):
        self.file_path = Path(file_path)
        self.data = self._load()

    def _load(self):
        with open(self.file_path, "r", encoding="utf-8") as file:
            raw_data = json.load(file)

        document = MemoryDocument.model_validate(raw_data)
        return document.model_dump(mode="json")

    def save(self):
        document = MemoryDocument.model_validate(self.data)
        self.data = document.model_dump(mode="json")

        with open(self.file_path, "w", encoding="utf-8") as file:
            json.dump(
                self.data,
                file,
                ensure_ascii=False,
                indent=2,
            )
            file.write("\n")

import json
from pathlib import Path

from memory_models import Fact


class MemoryStore:
    def __init__(self, file_path: str):
        self.file_path = Path(file_path)
        self.data = self._load()

    def _load(self):
        with open(self.file_path, "r", encoding="utf-8") as file:
            return json.load(file)

    def get_fact(self, fact_id: str):
        for fact_data in self.data["facts"]:
            if fact_data["id"] == fact_id:
                return Fact(**fact_data)

        return None
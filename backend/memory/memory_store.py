import json
from pathlib import Path

from .memory_models import Fact


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

    def add_fact(self, fact: Fact):
        self.data["facts"].append({
            "id": fact.id,
            "subject": fact.subject,
            "key": fact.key,
            "value": fact.value,
            "status": fact.status,
            "importance": fact.importance,
            "confidence": fact.confidence,
            "source": fact.source,
            "owner": fact.owner,
            "known_by": fact.known_by,
            "superseded_by": fact.superseded_by,
            "created_at": fact.created_at,
            "updated_at": fact.updated_at
        })
        return None
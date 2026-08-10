import json
from pathlib import Path

from .memory_models import Fact, Project


class MemoryStore:
    def __init__(self, file_path: str):
        self.file_path = Path(file_path)
        self.data = self._load()

    def _load(self):
        with open(self.file_path, "r", encoding="utf-8") as file:
            return json.load(file)

    def get_project(self, project_id: str):
        project_data = self.data.get("project")

        if project_data is None:
            return None

        if project_data["id"] != project_id:
            return None

        return Project(**project_data)

    def get_fact(self, fact_id: str):
        for fact_data in self.data["facts"]:
            if fact_data["id"] == fact_id:
                return Fact(**fact_data)

        return None

    def get_facts_by_project(self, project_id: str):
        result = []

        for fact_data in self.data["facts"]:
            project_ids = fact_data.get("project_ids", [])

            if project_id in project_ids:
                result.append(Fact(**fact_data))

        return result

    def _fact_to_dict(self, fact: Fact):
        return {
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
            "project_ids": fact.project_ids,
            "superseded_by": fact.superseded_by,
            "created_at": fact.created_at,
            "updated_at": fact.updated_at
        }

    def add_fact(self, fact: Fact):
        if self.get_fact(fact.id) is not None:
            return False

        self.data["facts"].append(
            self._fact_to_dict(fact)
        )

        return True

    def update_fact(self, fact: Fact):
        for index, fact_data in enumerate(self.data["facts"]):
            if fact_data["id"] == fact.id:
                self.data["facts"][index] = self._fact_to_dict(fact)
                return True

        return False

    def save(self):
        with open(self.file_path, "w", encoding="utf-8") as file:
            json.dump(
                self.data,
                file,
                ensure_ascii=False,
                indent=2
            )
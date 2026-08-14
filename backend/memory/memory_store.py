from .base_store import BaseStore
from .memory_models import Fact, MemoryDocument, Project


class MemoryStore(BaseStore):

    def read_document(self) -> MemoryDocument:
        """Expose the active JSON document through the shared storage boundary."""
        return MemoryDocument.model_validate(self.data)

    def replace_document(
        self,
        document: MemoryDocument,
        *,
        action: str = "replace_document",
        audit_payload: dict | None = None,
        audit_entity_type: str = "memory_document",
        audit_entity_id: str | None = None,
        additional_audit_events: tuple[dict, ...] = (),
    ) -> None:
        """Persist only a fully validated document to the active JSON store."""
        validated = MemoryDocument.model_validate(document)
        self.data = validated.model_dump(mode="json")
        self.save()

    def get_project(self, project_id: str):
        for project_data in self.data.get("projects", []):
            if project_data["id"] == project_id:
                return Project(**project_data)

        return None

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
        return fact.model_dump(mode="json")

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

    def forget_fact(self, fact_id: str) -> bool:
        return self.forget("fact", fact_id)

    def restore_fact(self, fact_id: str) -> bool:
        return self.restore("fact", fact_id)

    def _find_collection(self, memory_type: str):
        collections = {
            "fact": "facts",
            "decision": "decisions",
            "commitment": "commitments",
            "episode": "episodes",
        }

        return collections.get(memory_type)

    def _set_memory_visibility(
            self,
            memory_type: str,
            memory_id: str,
            visibility: str,
    ) -> bool:

        collection_name = self._find_collection(memory_type)

        if collection_name is None:
            return False

        for item in self.data.get(collection_name, []):
            if item.get("id") == memory_id:
                if item.get("visibility") == visibility:
                    return False

                item["visibility"] = visibility
                return True

        return False

    def forget(
            self,
            memory_type: str,
            memory_id: str,
    ) -> bool:

        return self._set_memory_visibility(
            memory_type,
            memory_id,
            "hidden",
        )

    def restore(
            self,
            memory_type: str,
            memory_id: str,
    ) -> bool:

        return self._set_memory_visibility(
            memory_type,
            memory_id,
            "visible",
        )

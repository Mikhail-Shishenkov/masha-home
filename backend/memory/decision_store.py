from .base_store import BaseStore
from .memory_models import Decision


class DecisionStore(BaseStore):

    def get_decision(self, decision_id: str):
        for decision_data in self.data.get("decisions", []):
            if decision_data["id"] == decision_id:
                return Decision(**decision_data)

        return None

    def get_decisions_by_project(self, project_id: str):
        result = []

        for decision_data in self.data.get("decisions", []):
            if project_id in decision_data.get("project_ids", []):
                result.append(Decision(**decision_data))

        return result
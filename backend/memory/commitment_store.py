from .base_store import BaseStore
from .memory_models import Commitment


class CommitmentStore(BaseStore):

    def get_commitment(self, commitment_id: str):
        for commitment_data in self.data.get("commitments", []):
            if commitment_data["id"] == commitment_id:
                return Commitment(**commitment_data)

        return None

    def get_commitments_by_project(self, project_id: str):
        result = []

        for commitment_data in self.data.get("commitments", []):
            if project_id in commitment_data.get("project_ids", []):
                result.append(Commitment(**commitment_data))

        return result

    def get_open_commitments(self):
        result = []

        for commitment_data in self.data.get("commitments", []):
            if commitment_data.get("status") == "open":
                result.append(Commitment(**commitment_data))

        return result
from .base_store import BaseStore
from .memory_models import Episode


class EpisodeStore(BaseStore):

    def get_episode(self, episode_id: str):
        for episode_data in self.data.get("episodes", []):
            if episode_data["id"] == episode_id:
                return Episode(**episode_data)

        return None

    def get_episodes_by_project(self, project_id: str):
        result = []

        for episode_data in self.data.get("episodes", []):
            projects = episode_data.get("project_ids", [])

            if project_id in projects:
                result.append(Episode(**episode_data))

        return result

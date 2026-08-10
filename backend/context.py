from dataclasses import dataclass

from backend.memory.memory_store import MemoryStore
from backend.memory.decision_store import DecisionStore
from backend.memory.commitment_store import CommitmentStore
from backend.memory.episode_store import EpisodeStore
from backend.persona.persona_store import PersonaStore


@dataclass
class MashaContext:
    persona: object
    project: object
    facts: list
    decisions: list
    commitments: list
    episodes: list


class ContextBuilder:
    def __init__(
        self,
        memory_path: str,
        persona_path: str
    ):
        self.memory_store = MemoryStore(memory_path)
        self.decision_store = DecisionStore(memory_path)
        self.commitment_store = CommitmentStore(memory_path)
        self.episode_store = EpisodeStore(memory_path)
        self.persona_store = PersonaStore(persona_path)

    def build(
        self,
        persona_id: str,
        project_id: str
    ):
        persona = self.persona_store.get_persona(persona_id)
        project = self.memory_store.get_project(project_id)
        facts = self.memory_store.get_facts_by_project(project_id)
        decisions = self.decision_store.get_decisions_by_project(project_id)
        commitments = self.commitment_store.get_commitments_by_project(project_id)
        episodes = self.episode_store.get_episodes_by_project(project_id)

        return MashaContext(
            persona=persona,
            project=project,
            facts=facts,
            decisions=decisions,
            commitments=commitments,
            episodes=episodes
        )
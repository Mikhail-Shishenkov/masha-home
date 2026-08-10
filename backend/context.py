from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from backend.memory.memory_store import MemoryStore
from backend.memory.memory_retriever import MemoryRetriever
from backend.memory.decision_store import DecisionStore
from backend.memory.commitment_store import CommitmentStore
from backend.memory.episode_store import EpisodeStore
from backend.memory.working_memory import WorkingMemory
from backend.memory.memory_manager import MemoryManager
from backend.persona.persona_store import PersonaStore


@dataclass
class MashaContext:
    persona: object
    project: object

    facts: list = field(default_factory=list)
    decisions: list = field(default_factory=list)
    commitments: list = field(default_factory=list)
    episodes: list = field(default_factory=list)

    working_memory: list = field(default_factory=list)
    current_time: str = ""


class ContextBuilder:
    def __init__(
        self,
        memory_path: str,
        persona_path: str,
    ):
        self.memory_store = MemoryStore(memory_path)
        self.memory_retriever = MemoryRetriever(self.memory_store)

        self.decision_store = DecisionStore(memory_path)
        self.commitment_store = CommitmentStore(memory_path)
        self.episode_store = EpisodeStore(memory_path)

        self.persona_store = PersonaStore(persona_path)

        self.working_memory = WorkingMemory(max_items=10)

        self.memory_manager = MemoryManager(
            store=self.memory_store,
            retriever=self.memory_retriever,
            working_memory=self.working_memory,
        )

    def build(
        self,
        persona_id: str,
        project_id: str,
    ):
        persona = self.persona_store.get_persona(persona_id)

        project = self.memory_store.get_project(project_id)

        facts = self.memory_store.get_facts_by_project(
            project_id
        )

        decisions = self.decision_store.get_decisions_by_project(
            project_id
        )

        commitments = (
            self.commitment_store.get_commitments_by_project(
                project_id
            )
        )

        episodes = self.episode_store.get_episodes_by_project(
            project_id
        )

        working_memory = self.memory_manager.load_working_memory(
            project_id=project_id,
            limit=10,
        )

        current_time = (
            datetime.now()
            .astimezone()
            .isoformat()
        )

        return MashaContext(
            persona=persona,
            project=project,
            facts=facts,
            decisions=decisions,
            commitments=commitments,
            episodes=episodes,
            working_memory=working_memory,
            current_time=current_time,
        )
from dataclasses import dataclass
from typing import Optional


@dataclass
class Project:
    id: str
    name: str
    description: str
    status: str


@dataclass
class Fact:
    id: str
    subject: str
    key: str
    value: str
    status: str
    importance: float
    confidence: float
    source: str
    owner: str
    known_by: list[str]
    project_ids: list[str]
    superseded_by: Optional[str] = None
    created_at: str = ""
    updated_at: str = ""


@dataclass
class Decision:
    id: str
    title: str
    decision: str
    reason: str
    status: str
    project_ids: list[str]
    source_episode: Optional[str] = None
    superseded_by: Optional[str] = None
    created_at: str = ""
    updated_at: str = ""


@dataclass
class Commitment:
    id: str
    text: str
    owner: str
    status: str
    project_ids: list[str]
    due_at: Optional[str] = None
    completed_at: Optional[str] = None
    importance: float = 0.5
    source_episode: Optional[str] = None
    created_at: str = ""
    updated_at: str = ""


@dataclass
class Episode:
    id: str
    title: str
    summary: str
    occurred_at: str
    source: str
    importance: float
    context: dict
    produced: dict
    updated: dict
    superseded: dict
    created_at: str
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
    superseded_by: Optional[str] = None
    created_at: str = ""
    updated_at: str = ""

"""Typed transient references for application-rendered human entity lists."""

from __future__ import annotations

from enum import Enum

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field


class HumanEntityKind(str, Enum):
    MEMORY = "memory"
    CONTINUITY = "continuity"


class HumanEntityAction(str, Enum):
    FORGET = "forget"
    RESOLVE_CONTINUITY = "resolve_continuity"


class HumanEntityRef(BaseModel):
    """Application-owned reference to one real, currently removable entity."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    entity_kind: HumanEntityKind
    entity_id: str = Field(min_length=1)
    human_label: str = Field(min_length=1)
    allowed_actions: tuple[HumanEntityAction, ...] = Field(min_length=1)


class PresentedEntityRef(HumanEntityRef):
    """One entity in the exact order rendered by the application."""

    ordinal: int = Field(ge=1)


class PresentedEntitySet(BaseModel):
    """Conversation-scoped selection truth; intentionally never persisted."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    conversation_id: str = Field(min_length=1)
    source_kind: str = Field(min_length=1)
    created_at: AwareDatetime
    items: tuple[PresentedEntityRef, ...] = Field(min_length=1)


class HumanEntityClarification(BaseModel):
    """Bounded typed candidates for one ambiguous cross-entity request."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    conversation_id: str = Field(min_length=1)
    candidates: tuple[HumanEntityRef, ...] = Field(min_length=2, max_length=5)
    original_query: str = Field(min_length=1)

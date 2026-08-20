"""Neutral, bounded local context for resolving an explicit public query."""

from __future__ import annotations

from enum import Enum
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ExternalContextHintKind(str, Enum):
    MEMORY = "memory"
    DECISION = "decision"
    EPISODE = "episode"
    SHARED_MOMENT = "shared_moment"
    TASK = "task"
    THREAD = "thread"
    ACTIVE_THREAD = "active_thread"
    MASHA_REFLECTION = "masha_reflection"


class ExternalContextHint(BaseModel):
    """Human-readable local context; never an outbound provider payload."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: ExternalContextHintKind
    text: str = Field(min_length=1, max_length=400)
    state: str | None = Field(default=None, max_length=40)


class ExternalContextResolution(BaseModel):
    """A bounded application-owned answer to a referential search request."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    hints: tuple[ExternalContextHint, ...] = Field(default=(), max_length=5)
    clarification_required: bool = False

    @model_validator(mode="after")
    def fit_total_text_budget(self):
        if sum(len(item.text) for item in self.hints) > 1_500:
            raise ValueError("external context hints exceed total text budget")
        return self


class ExternalContextHintProvider(Protocol):
    def resolve(
        self,
        *,
        current_message: str,
        project_id: str | None,
        recent_messages: tuple[str, ...],
        active_continuity_thread_id: str | None,
    ) -> ExternalContextResolution: ...


_REFERENCE_MARKERS = (
    "это", "эта", "этот", "эту", "этой", "того", "той", "та", "тот", "ту", "она", "него",
    "ней", "ним", "та тема", "этой теме", "тот проект", "та модель", "то дело",
    "та штука", "к которой мы хотели вернуться",
)


def requires_local_context_resolution(query_hint: str | None) -> bool:
    """Conservative gate: named public queries stay on W1's deterministic path."""
    if not query_hint or not query_hint.strip():
        return True
    normalized = " ".join(query_hint.casefold().replace("ё", "е").split())
    return any(
        marker == normalized or f" {marker} " in f" {normalized} "
        for marker in _REFERENCE_MARKERS
    )

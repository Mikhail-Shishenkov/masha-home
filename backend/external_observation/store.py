"""Persistent application-owned observations and opaque source resolution."""

from __future__ import annotations

import json
from pathlib import Path

from .models import ExternalObservation, ExternalObservationState, ObservationKind, ObservationStatus


class ExternalObservationStore:
    def __init__(self, path: Path, *, limit: int = 200):
        self.path = Path(path)
        self.limit = limit

    def save(self, observation: ExternalObservation) -> ExternalObservation:
        state = self._load()
        rows = [
            item for item in state.observations
            if item.request.observation_id != observation.request.observation_id
        ]
        rows.append(observation)
        self._write(ExternalObservationState(observations=tuple(rows[-self.limit :])))
        return observation

    def get(self, observation_id: str) -> ExternalObservation | None:
        return next(
            (item for item in self._load().observations if item.request.observation_id == observation_id),
            None,
        )

    def for_assistant_message(self, message_id: str) -> ExternalObservation | None:
        rows = self.for_assistant_message_all(message_id)
        return rows[-1] if rows else None

    def for_assistant_message_all(self, message_id: str) -> tuple[ExternalObservation, ...]:
        return tuple(
            item for item in self._load().observations if item.assistant_message_id == message_id
        )

    def latest_web_searches_for_origin_messages(
        self,
        message_ids: tuple[str, ...],
    ) -> tuple[ExternalObservation, ...]:
        allowed = set(message_ids)
        return tuple(
            item
            for item in reversed(self._load().observations)
            if item.request.origin_message_id in allowed
        )

    def latest_completed_web_search_for_origin_messages(
        self,
        message_ids: tuple[str, ...],
    ) -> ExternalObservation | None:
        """Return only a usable prior public subject from this conversation."""
        allowed = set(message_ids)
        return next(
            (
                item
                for item in reversed(self._load().observations)
                if item.request.origin_message_id in allowed
                and item.request.kind is ObservationKind.WEB_SEARCH
                and item.status is ObservationStatus.COMPLETED
                and item.evidence
            ),
            None,
        )

    def attach_assistant_message(self, observation_id: str, message_id: str) -> ExternalObservation:
        selected = self.get(observation_id)
        if selected is None:
            raise KeyError(observation_id)
        return self.save(selected.model_copy(update={"assistant_message_id": message_id}))

    def source_url(self, observation_id: str, source_id: str) -> str:
        selected = self.get(observation_id)
        if selected is None:
            raise KeyError(observation_id)
        if selected.fetched_page is not None and source_id == "page":
            return selected.fetched_page.final_url
        if selected.document_read_receipt_id is not None and source_id == "page" and selected.final_source_url is not None:
            return selected.final_source_url
        source = next((item for item in selected.evidence if item.source_id == source_id), None)
        if source is None:
            raise KeyError(source_id)
        return source.url

    def _load(self) -> ExternalObservationState:
        if not self.path.exists():
            return ExternalObservationState()
        return ExternalObservationState.model_validate(
            json.loads(self.path.read_text(encoding="utf-8"))
        )

    def _write(self, state: ExternalObservationState) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary.write_text(
            json.dumps(state.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        temporary.replace(self.path)

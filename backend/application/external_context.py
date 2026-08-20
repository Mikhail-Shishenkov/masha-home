"""Application-owned, bounded Recall adapter for explicit web references."""

from __future__ import annotations

import re

from backend.application.human_information import HumanAvailability, HumanRecallRequest, RecallMode, select_recall_mode
from backend.external_observation.context import (
    ExternalContextHint,
    ExternalContextHintKind,
    ExternalContextResolution,
)
from backend.memory.text_normalization import meaningful_tokens, normalize_search_text


_KIND_BY_CATEGORY = {
    "факт": ExternalContextHintKind.MEMORY,
    "решение": ExternalContextHintKind.DECISION,
    "эпизод": ExternalContextHintKind.EPISODE,
    "общий момент": ExternalContextHintKind.SHARED_MOMENT,
    "дело": ExternalContextHintKind.TASK,
    "тема": ExternalContextHintKind.THREAD,
}
_REFLECTION_MARKERS = (
    "ты говорила", "твоя идея", "ты думала", "в своих мыслях", "ты писала", "ты хотела посмотреть",
)
_REFERENCE_GLUE = {
    "маш", "маша", "проверь", "найди", "посмотри", "поищи", "интернете", "сети", "нового",
    "обновилась", "обновилось", "изменилось", "эта", "этот", "эту", "та", "тот", "ту", "она",
    "него", "ней", "ним", "модель", "тема", "проект", "дело", "штука", "который", "которую",
}
_RECENT_PUBLIC_NAME = re.compile(r"\b[A-Z][A-Za-z0-9+._-]{2,}\b")


class LocalExternalContextHintProvider:
    """Uses existing Human Information and Reflection projections, never storage IDs."""

    def __init__(self, *, human_information, reflections):
        self.human_information = human_information
        self.reflections = reflections
        self.calls: list[dict] = []

    def resolve(
        self,
        *,
        current_message: str,
        project_id: str | None,
        recent_messages: tuple[str, ...],
        active_continuity_thread_id: str | None,
    ) -> ExternalContextResolution:
        self.calls.append({
            "current_message": current_message,
            "project_id": project_id,
            "recent_messages": recent_messages,
            "active_continuity_thread_id": active_continuity_thread_id,
        })
        hints: list[ExternalContextHint] = []
        active = self._active_thread_hint(active_continuity_thread_id)
        if active is not None:
            hints.append(active)

        mode = select_recall_mode(current_message)
        recall_hints: list[ExternalContextHint] = []
        if mode is not RecallMode.FORGOTTEN_REVIEW and not self._recent_topic_is_explicit(recent_messages):
            recall = self.human_information.recall_information(HumanRecallRequest(
                query=current_message,
                project_id=project_id,
                mode=mode,
                recent_user_messages=recent_messages[-4:],
                limit=3,
                memory_budget_chars=1_200,
                max_record_chars=400,
            ))
            recall_hints = self._recall_hints(recall)

        # An active selected thread is explicit local context. Otherwise two
        # unrelated Recall candidates must not be resolved by recency alone.
        if active is None and len(recall_hints) > 1:
            return ExternalContextResolution(clarification_required=True)
        hints.extend(recall_hints)

        reflection = self._reflection_hint(current_message, project_id)
        if reflection is not None:
            hints.append(reflection)
        return ExternalContextResolution(hints=self._fit(hints))

    def _active_thread_hint(self, thread_id: str | None) -> ExternalContextHint | None:
        if thread_id is None:
            return None
        item = next(
            (
                item
                for item in self.human_information.information_items()
                if item.ref.entity_id == thread_id
                and item.record_type == "continuity_follow_up"
                and item.availability is HumanAvailability.ACTIVE
            ),
            None,
        )
        if item is None:
            return None
        return ExternalContextHint(
            kind=ExternalContextHintKind.ACTIVE_THREAD,
            text=item.label[:400],
            state="current",
        )

    @staticmethod
    def _recall_hints(recall) -> list[ExternalContextHint]:
        rows: list[ExternalContextHint] = []
        for item in recall.working_context[:3]:
            kind = _KIND_BY_CATEGORY.get(str(item.get("category", "")))
            text = str(item.get("content", "")).strip()
            if kind is None or not text:
                continue
            rows.append(ExternalContextHint(
                kind=kind,
                text=text[:400],
                state=str(item.get("state", ""))[:40] or None,
            ))
        return rows

    def _reflection_hint(self, current_message: str, project_id: str | None) -> ExternalContextHint | None:
        normalized = normalize_search_text(current_message)
        if not any(marker in normalized for marker in _REFLECTION_MARKERS):
            return None
        requested = {
            token for token in meaningful_tokens(current_message)
            if token not in _REFERENCE_GLUE
        }
        if not requested:
            return None
        for view in self.reflections.reflections():
            reflection = view.reflection
            if project_id and reflection.project_ids and project_id not in reflection.project_ids:
                continue
            text = f"{reflection.text} {reflection.meaning}".strip()
            if requested.isdisjoint(set(meaningful_tokens(text))):
                continue
            return ExternalContextHint(
                kind=ExternalContextHintKind.MASHA_REFLECTION,
                text=text[:400],
                state="subjective",
            )
        return None

    @staticmethod
    def _fit(hints: list[ExternalContextHint]) -> tuple[ExternalContextHint, ...]:
        rows: list[ExternalContextHint] = []
        used = 0
        for hint in hints[:5]:
            if used + len(hint.text) > 1_500:
                break
            rows.append(hint)
            used += len(hint.text)
        return tuple(rows)

    @staticmethod
    def _recent_topic_is_explicit(recent_messages: tuple[str, ...]) -> bool:
        """A recent named public subject is stronger than unrelated long-term Recall."""
        return any(_RECENT_PUBLIC_NAME.search(item) for item in recent_messages[-4:])

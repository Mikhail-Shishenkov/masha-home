"""UI-safe read-only projection of the shared Masha/Misha continuity."""

from __future__ import annotations

from .contracts import (
    ContinuityFollowUpView,
    RelationshipMomentView,
    SharedContinuityView,
)


class ContinuityApplicationService:
    """Expose bounded shared continuity without exposing MemoryDocument internals."""

    def __init__(self, *, continuity, memory_management):
        self._continuity = continuity
        self._memory_management = memory_management

    def view(
        self,
        *,
        memory_limit: int = 10,
        moments_limit: int = 5,
        threads_limit: int = 8,
    ) -> SharedContinuityView:
        moments = tuple(
            RelationshipMomentView(
                moment_id=item.id,
                title=item.title,
                text=self._continuity.relationship_text(item),
                created_at=item.created_at,
            )
            for item in self._continuity.relationship_memories(limit=moments_limit)
        )
        threads = tuple(
            ContinuityFollowUpView(
                thread_id=follow_up.id,
                topic=follow_up.topic,
                summary=follow_up.summary,
                reason_to_return=follow_up.reason_to_return,
                priority=follow_up.priority,
                revisit_after=follow_up.revisit_after,
            )
            for _, follow_up in self._continuity.open_follow_ups()[:threads_limit]
        )
        return SharedContinuityView(
            # Ordinary Fact/Decision/Episode belong to Memory, not to "our
            # history".  Only explicitly confirmed shared moments and threads
            # are allowed on this surface.
            confirmed_memories=(),
            moments=moments,
            open_threads=threads,
            quarantined_count=self._continuity.quarantined_count(),
        )


    def thread(self, thread_id: str) -> ContinuityFollowUpView:
        """Return one still-open UI-safe thread or fail closed."""
        matches = [
            item
            for item in self.view().open_threads
            if item.thread_id == thread_id
        ]
        if len(matches) != 1:
            raise KeyError("continuity thread not found")
        return matches[0]


    def thread_prompt(self, thread_id: str) -> str:
        matches = [item for item in self.view().open_threads if item.thread_id == thread_id]
        if len(matches) != 1:
            raise KeyError("continuity thread not found")
        thread = matches[0]
        return (
            "Давай вернёмся к нашей общей истории. "
            f"Открытая тема: {thread.summary}. Зачем вернуться: {thread.reason_to_return}."
        )

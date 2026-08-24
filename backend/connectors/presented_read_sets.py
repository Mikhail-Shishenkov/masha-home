"""Small application-owned recency rule for numbered connector results."""

from __future__ import annotations


class PresentedReadSetRegistry:
    """The newest real connector list owns a bare ordinal in its conversation."""

    def __init__(self):
        self._rows: dict[str, tuple[str, tuple[object, ...]]] = {}

    def present(self, conversation_id: str, owner: str, items: tuple[object, ...]) -> None:
        self._rows[conversation_id] = (owner, items)

    def items_for(self, conversation_id: str, owner: str) -> tuple[object, ...] | None:
        row = self._rows.get(conversation_id)
        return None if row is None or row[0] != owner else row[1]


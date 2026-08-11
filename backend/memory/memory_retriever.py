from datetime import datetime, timezone
from typing import Any

from .shared_continuity import is_readable_continuity_text


class MemoryRetriever:
    def __init__(self, memory_store):
        self.memory_store = memory_store

    def _parse_date(self, value: str) -> datetime:
        if not value:
            return datetime.min.replace(tzinfo=timezone.utc)

        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return datetime.min.replace(tzinfo=timezone.utc)

    def _matches_project(
        self,
        item: dict[str, Any],
        project_id: str | None
    ) -> bool:

        if project_id is None:
            return True

        # ContinuityState belongs to the Masha/Misha relationship, not one project.
        if item.get("relationship_key"):
            return True

        project_ids = item.get("project_ids", [])

        if project_id in project_ids:
            return True

        if item.get("id") == project_id:
            return True

        return False

    def _matches_status(self, item: dict[str, Any]) -> bool:
        if item.get("visibility", "visible") != "visible":
            return False

        status = item.get("status")

        if status is None:
            return True

        return status in ("active", "open", "current")

    def _importance(self, item: dict[str, Any]) -> float:
        return float(item.get("importance", 0.0))

    @staticmethod
    def _usable_continuity(item: dict[str, Any]) -> bool:
        return any(
            is_readable_continuity_text(value)
            for value in item.get("current_focus", [])
        ) or any(
            follow_up.get("status") == "open"
            and is_readable_continuity_text(follow_up.get("summary", ""))
            and is_readable_continuity_text(follow_up.get("reason_to_return", ""))
            for follow_up in item.get("intended_follow_ups", [])
        )

    def _recency_bonus(self, item: dict[str, Any]) -> float:
        updated_at = item.get(
            "updated_at",
            item.get("created_at", "")
        )

        parsed_date = self._parse_date(updated_at)

        if parsed_date == datetime.min.replace(tzinfo=timezone.utc):
            return 0.0

        now = datetime.now(parsed_date.tzinfo)
        age_days = (now - parsed_date).total_seconds() / 86400

        if age_days <= 1:
            return 0.3

        if age_days <= 7:
            return 0.2

        if age_days <= 30:
            return 0.1

        return 0.0

    def _type_bonus(self, item_type: str) -> float:
        bonuses = {
            "continuity_state": 0.25,
            "commitment": 0.2,
            "relationship_memory": 0.15,
            "decision": 0.15,
            "episode": 0.1,
            "fact": 0.0,
        }

        return bonuses.get(item_type, 0.0)

    def _score(
        self,
        item: dict[str, Any],
        item_type: str
    ) -> float:

        importance = self._importance(item)
        recency = self._recency_bonus(item)
        type_bonus = self._type_bonus(item_type)

        return importance + recency + type_bonus

    def retrieve(
        self,
        project_id: str | None = None,
        limit: int = 10,
    ) -> list[dict[str, Any]]:

        results = []

        collections = [
            ("fact", self.memory_store.data.get("facts", [])),
            ("decision", self.memory_store.data.get("decisions", [])),
            ("commitment", self.memory_store.data.get("commitments", [])),
            ("episode", self.memory_store.data.get("episodes", [])),
            (
                "relationship_memory",
                self.memory_store.data.get("relationship_memories", []),
            ),
            (
                "continuity_state",
                self.memory_store.data.get("continuity_states", []),
            ),
        ]

        for item_type, items in collections:

            for item in items:

                if item_type == "continuity_state" and not self._usable_continuity(item):
                    continue

                if not self._matches_project(item, project_id):
                    continue

                if not self._matches_status(item):
                    continue

                reasons = ["visible"]
                if item.get("status") is not None:
                    reasons.append("active_status")
                if item_type == "continuity_state":
                    reasons.append("relationship_scope")
                if project_id is not None:
                    reasons.append(f"project:{project_id}")
                results.append({
                    "type": item_type,
                    "data": item,
                    "score": self._score(item, item_type),
                    "reasons": reasons,
                })

        results.sort(
            key=lambda item: item["score"],
            reverse=True,
        )

        return self._bounded_with_shared_coverage(results, limit)

    @staticmethod
    def _bounded_with_shared_coverage(
        results: list[dict[str, Any]],
        limit: int,
    ) -> list[dict[str, Any]]:
        """Keep the global bound while preserving at most one shared-history slot each."""
        if limit <= 0:
            return []
        selected = list(results[:limit])
        if limit < 2:
            return selected
        protected_types = {"relationship_memory", "continuity_state"}
        for required_type in ("relationship_memory", "continuity_state"):
            if any(item["type"] == required_type for item in selected):
                continue
            candidate = next(
                (item for item in results if item["type"] == required_type),
                None,
            )
            if candidate is None:
                continue
            replacement = next(
                (
                    index
                    for index in range(len(selected) - 1, -1, -1)
                    if selected[index]["type"] not in protected_types
                ),
                None,
            )
            if replacement is None:
                continue
            selected[replacement] = {
                **candidate,
                "reasons": [
                    *candidate.get("reasons", []),
                    "bounded_shared_continuity_coverage",
                ],
            }
        selected.sort(key=lambda item: item["score"], reverse=True)
        return selected

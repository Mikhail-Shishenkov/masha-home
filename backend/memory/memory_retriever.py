from datetime import datetime, timezone
from typing import Any


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

        # Facts / Decisions / Commitments
        project_ids = item.get("project_ids", [])

        if project_id in project_ids:
            return True

        # Episodes хранят проекты внутри context
        context = item.get("context", {})
        context_projects = context.get("projects", [])

        if project_id in context_projects:
            return True

        # Сам Project
        if item.get("id") == project_id:
            return True

        return False

    def _matches_status(self, item: dict[str, Any]) -> bool:
        status = item.get("status")

        # Episodes не имеют status
        if status is None:
            return True

        return status in ("active", "open")

    def _importance(self, item: dict[str, Any]) -> float:
        return float(item.get("importance", 0.0))

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
            "commitment": 0.2,
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
        ]

        for item_type, items in collections:

            for item in items:

                if not self._matches_project(item, project_id):
                    continue

                if not self._matches_status(item):
                    continue

                results.append({
                    "type": item_type,
                    "data": item,
                    "score": self._score(item, item_type),
                })

        results.sort(
            key=lambda item: item["score"],
            reverse=True,
        )

        return results[:limit]
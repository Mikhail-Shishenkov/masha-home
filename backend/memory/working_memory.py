from typing import Any


class WorkingMemory:
    def __init__(self, max_items: int = 8):
        self.max_items = max_items
        self.items: list[dict[str, Any]] = []

    def clear(self):
        self.items.clear()

    def load(self, memories: list[dict[str, Any]]):
        self.clear()

        self.items = memories[:self.max_items]

    def add(self, memory: dict[str, Any]):
        self.items.append(memory)

        self.items.sort(
            key=lambda item: item.get("score", 0.0),
            reverse=True,
        )

        self.items = self.items[:self.max_items]

    def remove(self, memory_id: str) -> bool:
        original_count = len(self.items)

        self.items = [
            item
            for item in self.items
            if item["data"].get("id") != memory_id
        ]

        return len(self.items) < original_count

    def get_all(self) -> list[dict[str, Any]]:
        return list(self.items)

    def get_by_type(self, memory_type: str) -> list[dict[str, Any]]:
        return [
            item
            for item in self.items
            if item.get("type") == memory_type
        ]

    def contains(self, memory_id: str) -> bool:
        return any(
            item["data"].get("id") == memory_id
            for item in self.items
        )

    def __len__(self):
        return len(self.items)
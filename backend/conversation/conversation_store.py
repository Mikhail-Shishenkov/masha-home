from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from .conversation_models import (
    Conversation,
    ConversationMessage,
    ConversationMessageOrigin,
    ConversationRole,
)


class ConversationStore:
    """Portable JSON history. It is separate from long-term memory."""

    def __init__(self, file_path: str | Path):
        self.file_path = Path(file_path)
        self.file_path.parent.mkdir(parents=True, exist_ok=True)
        self._data = self._load()

    def create(self) -> Conversation:
        conversation = Conversation(id=str(uuid4()), created_at=self._now())
        self._data["conversations"].append(conversation.model_dump(mode="json"))
        self._save()
        return conversation

    def get(self, conversation_id: str) -> Conversation:
        for raw in self._data["conversations"]:
            if raw["id"] == conversation_id:
                return Conversation.model_validate(raw)
        raise KeyError(f"unknown conversation: {conversation_id}")

    def latest(self) -> Conversation | None:
        """Return the most recently created conversation, if this history has one."""
        if not self._data["conversations"]:
            return None
        return Conversation.model_validate(self._data["conversations"][-1])

    def latest_message(self) -> ConversationMessage | None:
        """Return the globally newest persisted message, independent of creation order."""
        if not self._data["messages"]:
            return None
        return max(
            (ConversationMessage.model_validate(raw) for raw in self._data["messages"]),
            key=lambda message: (message.created_at, message.id),
        )

    def recent(self, *, limit: int | None = 8) -> tuple[Conversation, ...]:
        """Return conversations ordered by the latest actual interaction."""
        if limit is not None and limit < 1:
            return ()
        latest_by_conversation: dict[str, datetime] = {}
        for raw in self._data["messages"]:
            message = ConversationMessage.model_validate(raw)
            previous = latest_by_conversation.get(message.conversation_id)
            if previous is None or message.created_at > previous:
                latest_by_conversation[message.conversation_id] = message.created_at
        conversations = [Conversation.model_validate(raw) for raw in self._data["conversations"]]
        return tuple(
            sorted(
                conversations,
                key=lambda conversation: (
                    latest_by_conversation.get(conversation.id, conversation.created_at),
                    conversation.id,
                ),
                reverse=True,
            )[:limit]
        )

    def append(
        self,
        conversation_id: str,
        role: ConversationRole,
        content: str,
        *,
        origin: ConversationMessageOrigin | None = None,
    ) -> ConversationMessage:
        self.get(conversation_id)
        message = ConversationMessage(
            id=str(uuid4()),
            role=role,
            content=content,
            created_at=self._now(),
            conversation_id=conversation_id,
            origin=origin or (
                ConversationMessageOrigin.USER
                if role is ConversationRole.USER
                else ConversationMessageOrigin.MODEL
            ),
        )
        self._data["messages"].append(message.model_dump(mode="json"))
        self._save()
        return message

    def messages(self, conversation_id: str, *, limit: int | None = 16) -> tuple[ConversationMessage, ...]:
        self.get(conversation_id)
        messages = [
            ConversationMessage.model_validate(raw)
            for raw in self._data["messages"]
            if raw["conversation_id"] == conversation_id
        ]
        return tuple(messages if limit is None else messages[-limit:])

    def last_interaction_at(self, conversation_id: str) -> datetime | None:
        messages = self.messages(conversation_id, limit=1)
        return messages[-1].created_at if messages else None

    def _load(self) -> dict[str, list[dict]]:
        if not self.file_path.exists():
            return {"conversations": [], "messages": []}
        with self.file_path.open("r", encoding="utf-8") as file:
            raw = json.load(file)
        if set(raw) != {"conversations", "messages"}:
            raise ValueError("invalid conversation history document")
        return raw

    def _save(self) -> None:
        temporary = self.file_path.with_suffix(".tmp")
        temporary.write_text(
            json.dumps(self._data, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        temporary.replace(self.file_path)

    @staticmethod
    def _now() -> datetime:
        return datetime.now(timezone.utc)

"""Closed local WebChannel port for one Masha Home conversation surface."""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor

from PySide6.QtCore import QObject, Signal, Slot

from backend.application import ConversationTurnStatus, MashaApplication


HOME_PROJECT_ID = "project_masha_home"
MAX_MESSAGE_CHARACTERS = 4_000


class LocalConversationBridge(QObject):
    """A tiny allowlisted bridge; it never exposes application services to JavaScript."""

    event = Signal(str)

    def __init__(self, application: MashaApplication | None, parent=None):
        super().__init__(parent)
        self._application = application
        self._session = None
        self._conversation_id: str | None = None
        self._turn_in_flight = False
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="masha-conversation")

    @Slot()
    def loadInitialState(self):  # noqa: N802 - Qt slot name is part of the JS contract
        if self._application is None:
            self._emit({"kind": "home_unavailable"})
            return
        self._session = self._application.open_home_session()
        snapshot = self._session.opened()
        conversation = self._application.latest_conversation(limit=16)
        if conversation is not None:
            self._conversation_id = conversation.conversation_id
        self._emit(
            {
                "kind": "home_initial",
                "snapshot": snapshot.model_dump(mode="json"),
                "conversation": None if conversation is None else conversation.model_dump(mode="json"),
                "recent": self._recent_payload(),
            }
        )

    @Slot()
    def loadRecentConversations(self):  # noqa: N802 - Qt slot name is part of the JS contract
        if self._application is None:
            self._emit({"kind": "home_unavailable"})
            return
        self._emit(
            {
                "kind": "recent_conversations",
                "recent": self._recent_payload(),
                "active_conversation_id": self._conversation_id,
            }
        )

    @Slot(str)
    def openConversation(self, conversation_id: str):  # noqa: N802 - Qt slot name is part of the JS contract
        if self._application is None or self._turn_in_flight:
            self._emit({"kind": "turn_rejected", "reason": "turn_in_flight"})
            return
        try:
            conversation = self._application.conversation(conversation_id, limit=16)
        except Exception:
            self._emit({"kind": "conversation_unavailable"})
            return
        self._conversation_id = conversation.conversation_id
        self._session = self._application.open_home_session()
        self._emit(
            {
                "kind": "conversation_opened",
                "snapshot": self._session.opened().model_dump(mode="json"),
                "conversation": conversation.model_dump(mode="json"),
                "recent": self._recent_payload(),
            }
        )

    @Slot()
    def startNewConversation(self):  # noqa: N802 - Qt slot name is part of the JS contract
        """Forget only the window's opaque reference; no history is deleted."""
        if self._application is None:
            self._emit({"kind": "home_unavailable"})
            return
        if self._turn_in_flight:
            self._emit({"kind": "turn_rejected", "reason": "turn_in_flight"})
            return
        self._conversation_id = None
        self._session = self._application.open_home_session()
        self._emit(
            {
                "kind": "conversation_started",
                "snapshot": self._session.opened().model_dump(mode="json"),
            }
        )

    @Slot(str)
    def submitMessage(self, content: str):  # noqa: N802 - Qt slot name is part of the JS contract
        normalized = content.strip()
        if not normalized:
            self._emit({"kind": "input_rejected", "reason": "empty"})
            return
        if len(normalized) > MAX_MESSAGE_CHARACTERS:
            self._emit({"kind": "input_rejected", "reason": "too_long"})
            return
        if self._application is None or self._session is None:
            self._emit({"kind": "home_unavailable"})
            return
        if self._turn_in_flight:
            self._emit({"kind": "turn_rejected", "reason": "turn_in_flight"})
            return

        self._turn_in_flight = True
        self._emit(
            {
                "kind": "turn_started",
                "content": normalized,
                "snapshot": self._session.user_sent().model_dump(mode="json"),
            }
        )
        future = self._executor.submit(
            self._send_turn,
            normalized,
        )
        future.add_done_callback(self._finish_turn)

    def _send_turn(self, content: str):
        """Publish the deterministic thinking phase before local model execution."""
        self._emit(
            {
                "kind": "turn_thinking",
                "snapshot": self._session.assistant_thinking().model_dump(mode="json"),
            }
        )
        return self._application.send_message(
            content,
            project_id=HOME_PROJECT_ID,
            conversation_id=self._conversation_id,
        )

    def _finish_turn(self, future) -> None:
        try:
            result = future.result()
        except Exception:
            # Application code normally returns a controlled result.  The bridge
            # still must not leak an exception into the renderer if that invariant
            # is ever violated below it.
            result_payload = None
            snapshot = self._session.model_unavailable(
                profile_id="primary",
                display_name="Локальная модель",
            )
        else:
            self._conversation_id = result.conversation_id or self._conversation_id
            result_payload = result.model_dump(mode="json")
            if result.status is ConversationTurnStatus.COMPLETED:
                snapshot = self._session.assistant_responded()
            else:
                snapshot = self._session.model_unavailable(
                    profile_id=result.active_profile_id,
                    display_name=self._active_model_name(),
                )
        self._turn_in_flight = False
        self._emit(
            {
                "kind": "turn_result",
                "result": result_payload,
                "snapshot": snapshot.model_dump(mode="json"),
            }
        )

    def close(self) -> None:
        self._executor.shutdown(wait=False, cancel_futures=True)

    def _active_model_name(self) -> str:
        if self._session is None:
            return "Локальная модель"
        return self._session.active_model_display_name

    def _recent_payload(self) -> list[dict]:
        if self._application is None:
            return []
        return [item.model_dump(mode="json") for item in self._application.recent_conversations(limit=8)]

    def _emit(self, payload: dict) -> None:
        self.event.emit(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))

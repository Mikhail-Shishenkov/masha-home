"""Closed local WebChannel port for one Masha Home conversation surface."""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from threading import Lock

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
        self._session_lock = Lock()
        self._conversation_id: str | None = None
        self._turn_in_flight = False
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="masha-conversation")

    @Slot()
    def loadInitialState(self):  # noqa: N802 - Qt slot name is part of the JS contract
        if self._application is None:
            self._emit({"kind": "home_unavailable"})
            return
        self._session = self._application.open_home_session()
        snapshot = self._session_snapshot("opened")
        conversation = self._application.latest_conversation(limit=16)
        if conversation is not None:
            self._conversation_id = conversation.conversation_id
        pending = (
            None
            if conversation is None
            else self._application.pending_confirmation(conversation.conversation_id)
        )
        if pending is not None:
            snapshot = self._session_snapshot(
                "confirmation_requested",
                title=pending.title,
                summary=pending.subject,
            )
        self._emit(
            {
                "kind": "home_initial",
                "snapshot": snapshot.model_dump(mode="json"),
                "conversation": None if conversation is None else conversation.model_dump(mode="json"),
                "recent": self._recent_payload(),
                "commitments_count": sum(
                    item.can_propose_completion
                    for item in self._application.commitments(limit=12).items
                ),
                "pending_confirmation": None if pending is None else pending.model_dump(mode="json"),
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

    @Slot()
    def loadHomeAttention(self):  # noqa: N802 - Qt slot name is part of the JS contract
        if self._application is None:
            self._emit({"kind": "home_unavailable"})
            return
        self._emit(
            {
                "kind": "home_attention",
                "attention": self._application.home_attention(
                    conversation_id=self._conversation_id
                ).model_dump(mode="json"),
            }
        )

    @Slot()
    def loadCommitments(self):  # noqa: N802 - Qt slot name is part of the JS contract
        if self._application is None or self._turn_in_flight:
            self._emit({"kind": "commitments_unavailable"})
            return
        commitments = self._application.commitments(limit=12)
        if self._session is None:
            self._session = self._application.open_home_session()
        summary = (
            "Открытых дел нет"
            if not commitments.items
            else f"Дел рядом: {len(commitments.items)}"
        )
        snapshot = self._session_snapshot("commitments_opened", summary=summary)
        self._emit(
            {
                "kind": "commitments_loaded",
                "commitments": commitments.model_dump(mode="json"),
                "snapshot": snapshot.model_dump(mode="json"),
            }
        )

    @Slot()
    def engageEmergencyStop(self):  # noqa: N802 - Qt slot name is part of the JS contract
        if self._application is None:
            self._emit({"kind": "home_unavailable"})
            return
        safety = self._application.emergency_stop()
        if self._session is None:
            self._session = self._application.open_home_session()
        snapshot = self._session_snapshot(
            "emergency_stop", reason=safety.reason or "manual_emergency_stop"
        )
        self._emit(
            {
                "kind": "safety_changed",
                "safety": safety.model_dump(mode="json"),
                "snapshot": snapshot.model_dump(mode="json"),
            }
        )

    @Slot()
    def resumeAutonomy(self):  # noqa: N802 - Qt slot name is part of the JS contract
        if self._application is None:
            self._emit({"kind": "home_unavailable"})
            return
        safety = self._application.resume_autonomy()
        if self._session is None:
            self._session = self._application.open_home_session()
        snapshot = self._session_snapshot("autonomy_resumed")
        self._emit(
            {
                "kind": "safety_changed",
                "safety": safety.model_dump(mode="json"),
                "snapshot": snapshot.model_dump(mode="json"),
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
        pending = self._application.pending_confirmation(conversation.conversation_id)
        snapshot = self._session_snapshot("opened")
        if pending is not None:
            snapshot = self._session_snapshot(
                "confirmation_requested",
                title=pending.title,
                summary=pending.subject,
            )
        self._emit(
            {
                "kind": "conversation_opened",
                "snapshot": snapshot.model_dump(mode="json"),
                "conversation": conversation.model_dump(mode="json"),
                "recent": self._recent_payload(),
                "pending_confirmation": None if pending is None else pending.model_dump(mode="json"),
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
                "snapshot": self._session_snapshot("opened").model_dump(mode="json"),
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
                "snapshot": self._session_snapshot("user_sent").model_dump(mode="json"),
            }
        )
        future = self._executor.submit(
            self._send_turn,
            normalized,
        )
        future.add_done_callback(self._finish_turn)

    @Slot(str)
    def proposeCommitmentCompletion(self, commitment_id: str):  # noqa: N802
        if self._application is None or self._session is None:
            self._emit({"kind": "home_unavailable"})
            return
        if self._turn_in_flight:
            self._emit({"kind": "commitment_operation_rejected", "reason": "turn_in_flight"})
            return
        visible = {
            item.commitment_id: item
            for item in self._application.commitments(limit=12).items
        }
        selected = visible.get(commitment_id)
        if selected is None or not selected.can_propose_completion:
            self._emit({"kind": "commitment_operation_rejected", "reason": "stale_or_invalid"})
            return
        try:
            result = self._application.propose_commitment_completion(
                commitment_id=commitment_id,
                conversation_id=self._conversation_id,
                project_id=HOME_PROJECT_ID,
            )
        except Exception:
            self._emit({"kind": "commitment_operation_rejected", "reason": "proposal_failed"})
            return
        self._conversation_id = result.conversation_id
        snapshot = self._session_snapshot(
            "confirmation_requested",
            title=result.pending_confirmation.title,
            summary=result.pending_confirmation.subject,
        )
        self._emit(
            {
                "kind": "commitment_completion_proposed",
                "result": result.model_dump(mode="json"),
                "snapshot": snapshot.model_dump(mode="json"),
            }
        )

    @Slot(str, str)
    def resolveConfirmation(self, proposal_id: str, decision: str):  # noqa: N802
        if self._application is None or self._session is None or self._conversation_id is None:
            self._emit({"kind": "home_unavailable"})
            return
        if self._turn_in_flight:
            self._emit({"kind": "turn_rejected", "reason": "turn_in_flight"})
            return
        if self._application.status().emergency_stop_engaged:
            self._emit({"kind": "confirmation_rejected", "reason": "safety_stop"})
            return
        pending = self._application.pending_confirmation(self._conversation_id)
        if (
            pending is None
            or pending.proposal_id != proposal_id
            or decision not in {"confirm", "reject"}
        ):
            self._emit({"kind": "confirmation_rejected", "reason": "stale_or_invalid"})
            return
        self._turn_in_flight = True
        snapshot = self._session_snapshot(
            "confirmation_resolving",
            title=(
                "Оставляю без изменений"
                if decision == "reject"
                else "Сохраняю обязательство"
                if pending.confirmation_type == "commitment_create"
                else "Завершаю обязательство"
            ),
        )
        self._emit(
            {
                "kind": "confirmation_started",
                "proposal_id": proposal_id,
                "decision": decision,
                "snapshot": snapshot.model_dump(mode="json"),
            }
        )
        future = self._executor.submit(
            self._application.resolve_confirmation,
            conversation_id=self._conversation_id,
            proposal_id=proposal_id,
            decision=decision,
            project_id=HOME_PROJECT_ID,
        )
        future.add_done_callback(self._finish_confirmation)

    def _send_turn(self, content: str):
        """Publish the deterministic thinking phase before local model execution."""
        if self._application.status().model_available:
            self._emit(
                {
                    "kind": "turn_thinking",
                    "snapshot": self._session_snapshot("assistant_thinking").model_dump(mode="json"),
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
            snapshot = self._session_snapshot(
                "model_unavailable",
                profile_id="primary",
                display_name="Локальная модель",
            )
        else:
            self._conversation_id = result.conversation_id or self._conversation_id
            result_payload = result.model_dump(mode="json")
            if result.status is ConversationTurnStatus.COMPLETED:
                if result.pending_confirmation is not None:
                    snapshot = self._session_snapshot(
                        "confirmation_requested",
                        title=result.pending_confirmation.title,
                        summary=result.pending_confirmation.subject,
                    )
                else:
                    snapshot = self._session_snapshot("assistant_responded")
            else:
                snapshot = self._session_snapshot(
                    "model_unavailable",
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

    def _finish_confirmation(self, future) -> None:
        try:
            result = future.result()
        except Exception:
            result_payload = None
            snapshot = self._session_snapshot(
                "confirmation_failed",
                summary="Изменение не применено",
            )
        else:
            result_payload = result.model_dump(mode="json")
            summary = (
                "Изменение подтверждено"
                if result.status.value == "confirmed"
                else "Ничего не изменено"
                if result.status.value == "rejected"
                else "Изменение не применено"
            )
            snapshot = self._session_snapshot(
                "confirmation_resolved"
                if result.status.value != "failed"
                else "confirmation_failed",
                summary=summary,
            )
        self._turn_in_flight = False
        self._emit(
            {
                "kind": "confirmation_result",
                "result": result_payload,
                "snapshot": snapshot.model_dump(mode="json"),
                "commitments_count": (
                    0
                    if self._application is None
                    else sum(
                        item.can_propose_completion
                        for item in self._application.commitments(limit=12).items
                    )
                ),
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

    def _session_snapshot(self, method_name: str, **kwargs):
        """Serialize reducer access across the UI and the local model worker."""
        with self._session_lock:
            method = getattr(self._session, method_name)
            return method(**kwargs)

    def _emit(self, payload: dict) -> None:
        self.event.emit(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))

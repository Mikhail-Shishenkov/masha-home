"""Closed local WebChannel port for one Masha Home conversation surface."""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from threading import Lock

from PySide6.QtCore import QObject, Signal, Slot
from PySide6.QtWidgets import QFileDialog

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
        self._proactive_refresh_in_flight = False
        self._visible_proactive_ids: set[str] = set()
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="masha-conversation")

    @Slot()
    def loadInitialState(self):  # noqa: N802 - Qt slot name is part of the JS contract
        if self._application is None:
            self._emit({"kind": "home_unavailable"})
            return
        self._session = self._application.open_home_session()
        snapshot = self._session_snapshot("opened")
        conversation = self._application.latest_conversation()
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
        proactive = self._application.proactive_interactions(limit=6)
        self._visible_proactive_ids = {item.interaction_id for item in proactive.items}
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
                "agent_runs_count": len(self._application.agent_runs(limit=8).items),
                "proactive_interactions_count": len(proactive.items),
                "continuity_count": self._continuity_count(),
                "reflection_items_count": self._reflection_count(),
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
    def loadAgentRuns(self):  # noqa: N802 - Qt slot name is part of the JS contract
        if self._application is None or self._turn_in_flight:
            self._emit({"kind": "activities_unavailable"})
            return
        runs = self._application.agent_runs(limit=8)
        if self._session is None:
            self._session = self._application.open_home_session()
        snapshot = self._session_snapshot("opened")
        if runs.items:
            first = runs.items[0]
            snapshot = self._session_snapshot(
                "activity_opened",
                run_id=first.run_id,
                title=first.goal,
                status=first.status,
            )
        self._emit(
            {
                "kind": "agent_runs_loaded",
                "runs": runs.model_dump(mode="json"),
                "snapshot": snapshot.model_dump(mode="json"),
            }
        )

    @Slot()
    def loadProactiveInteractions(self):  # noqa: N802 - Qt slot name is part of the JS contract
        if self._application is None or self._turn_in_flight:
            self._emit({"kind": "proactive_unavailable"})
            return
        interactions = self._application.proactive_interactions(limit=6)
        self._visible_proactive_ids = {item.interaction_id for item in interactions.items}
        if self._session is None:
            self._session = self._application.open_home_session()
        snapshot = self._session_snapshot("opened")
        if interactions.items:
            first = interactions.items[0]
            snapshot = self._session_snapshot(
                "proactive_opened",
                event_id=first.interaction_id,
                text=first.message,
            )
        self._emit(
            {
                "kind": "proactive_interactions_loaded",
                "interactions": interactions.model_dump(mode="json"),
                "snapshot": snapshot.model_dump(mode="json"),
            }
        )

    @Slot()
    def refreshProactiveInteractions(self):  # noqa: N802
        """Push newly delivered local interactions into an already open Home.

        Detection/formulation remains owned by the existing proactive runtime.
        This read-only heartbeat only projects delivery records that did not
        exist at the previous observation, once per stable event_id.
        """
        if self._application is None or self._turn_in_flight or self._proactive_refresh_in_flight:
            return
        self._proactive_refresh_in_flight = True
        future = self._executor.submit(
            self._application.refresh_proactive_interactions,
            limit=6,
        )
        future.add_done_callback(self._finish_proactive_refresh)

    def _finish_proactive_refresh(self, future) -> None:
        try:
            interactions = future.result()
        except Exception:
            self._proactive_refresh_in_flight = False
            return
        current_ids = {item.interaction_id for item in interactions.items}
        new_ids = current_ids - self._visible_proactive_ids
        self._visible_proactive_ids = current_ids
        self._proactive_refresh_in_flight = False
        if not new_ids:
            return
        first = next(item for item in interactions.items if item.interaction_id in new_ids)
        if self._session is None:
            self._session = self._application.open_home_session()
        snapshot = self._session_snapshot(
            "proactive_opened",
            event_id=first.interaction_id,
            text=first.message,
        )
        self._emit({
            "kind": "proactive_interactions_loaded",
            "interactions": interactions.model_dump(mode="json"),
            "snapshot": snapshot.model_dump(mode="json"),
            "delivery_origin": "local_runtime",
        })

    @Slot(str, str)
    def resolveProactiveInteraction(self, interaction_id: str, decision: str):  # noqa: N802
        if self._application is None or self._turn_in_flight:
            self._emit({"kind": "proactive_resolution_rejected"})
            return
        visible = {
            item.interaction_id: item
            for item in self._application.proactive_interactions(limit=6).items
        }
        selected = visible.get(interaction_id)
        if selected is None or decision not in selected.allowed_actions:
            self._emit({"kind": "proactive_resolution_rejected"})
            return
        try:
            resolved = self._application.resolve_proactive(interaction_id, decision)
        except (KeyError, ValueError):
            self._emit({"kind": "proactive_resolution_rejected"})
            return
        snapshot = self._session_snapshot(
            "proactive_resolved",
            event_id=interaction_id,
            decision=decision,
        )
        self._emit(
            {
                "kind": "proactive_interaction_resolved",
                "interaction": resolved.model_dump(mode="json"),
                "remaining_count": len(
                    self._application.proactive_interactions(limit=6).items
                ),
                "snapshot": snapshot.model_dump(mode="json"),
            }
        )

    @Slot()
    def loadSharedContinuity(self):  # noqa: N802
        if self._application is None or self._turn_in_flight:
            self._emit({"kind": "continuity_unavailable"})
            return
        continuity = self._application.shared_continuity()
        snapshot = self._session_snapshot(
            "continuity_opened",
            summary=(
                "Пока здесь тихо"
                if not continuity.confirmed_memories and not continuity.moments and not continuity.open_threads
                else f"Память и общие нити: {len(continuity.confirmed_memories) + len(continuity.moments) + len(continuity.open_threads)}"
            ),
        )
        self._emit(
            {
                "kind": "shared_continuity_loaded",
                "continuity": continuity.model_dump(mode="json"),
                "snapshot": snapshot.model_dump(mode="json"),
            }
        )

    @Slot(str)
    def continueContinuityThread(self, thread_id: str):  # noqa: N802
        if self._application is None or self._turn_in_flight:
            self._emit({"kind": "continuity_unavailable"})
            return
        self._turn_in_flight = True
        future = self._executor.submit(
            self._application.continue_continuity_thread,
            thread_id,
            conversation_id=self._conversation_id,
            project_id=HOME_PROJECT_ID,
        )
        future.add_done_callback(self._finish_continuity_thread)

    @Slot()
    def loadReflectionWorkspace(self):  # noqa: N802
        if self._application is None or self._turn_in_flight:
            self._emit({"kind": "reflections_unavailable"})
            return
        workspace = self._application.reflection_workspace()
        decisions = len(workspace.pending) + len(workspace.help_offers)
        snapshot = self._session_snapshot(
            "reflections_opened",
            summary=(
                "Мыслей пока нет"
                if not workspace.adopted and not decisions
                else f"Мыслей: {len(workspace.adopted)} · решений: {decisions}"
            ),
            decision=decisions > 0,
        )
        self._emit(
            {
                "kind": "reflection_workspace_loaded",
                "workspace": workspace.model_dump(mode="json"),
                "snapshot": snapshot.model_dump(mode="json"),
            }
        )

    @Slot()
    def loadWorkbench(self):  # noqa: N802
        if self._application is None or self._turn_in_flight:
            self._emit({"kind": "workbench_unavailable"})
            return
        workbench = self._application.workbench()
        decision = bool(workbench.pending) or any(
            profile.enabled and not profile.active for profile in workbench.profiles
        )
        snapshot = self._session_snapshot(
            "workbench_opened",
            summary=(
                "Локальный режим под контролем"
                if not workbench.pending
                else f"Ждут решения: {len(workbench.pending)}"
            ),
            decision=decision,
        )
        self._emit(
            {
                "kind": "workbench_loaded",
                "workbench": workbench.model_dump(mode="json"),
                "snapshot": snapshot.model_dump(mode="json"),
            }
        )

    @Slot(str)
    def useModelProfile(self, profile_id: str):  # noqa: N802
        if self._application is None or self._turn_in_flight:
            self._emit({"kind": "model_switch_rejected", "reason": "turn_in_flight"})
            return
        self._emit(
            {
                "kind": "model_switch_started",
                "snapshot": self._session_snapshot("model_switch_started").model_dump(mode="json"),
            }
        )
        result = self._application.use_model(profile_id)
        if result.status.value != "applied":
            self._emit(
                {
                    "kind": "model_switch_rejected",
                    "result": result.model_dump(mode="json"),
                }
            )
            return
        snapshot = self._session_snapshot(
            "model_changed",
            active_model=result.active_profile,
            status=self._application.status(),
        )
        self._emit(
            {
                "kind": "model_switch_applied",
                "result": result.model_dump(mode="json"),
                "workbench": self._application.workbench().model_dump(mode="json"),
                "snapshot": snapshot.model_dump(mode="json"),
            }
        )

    @Slot()
    def chooseSkillPackage(self):  # noqa: N802
        if self._application is None or self._turn_in_flight:
            self._emit({"kind": "skill_install_rejected", "reason": "unavailable"})
            return
        source, _ = QFileDialog.getOpenFileName(
            None,
            "Выбрать локальный ZIP-пакет навыка",
            "",
            "Пакет навыка (*.zip)",
        )
        if not source:
            source = QFileDialog.getExistingDirectory(None, "Выбрать локальную папку навыка")
        if not source:
            self._emit({"kind": "skill_install_cancelled"})
            return
        try:
            preview = self._application.propose_skill_install(source)
        except Exception:
            self._emit({"kind": "skill_install_rejected", "reason": "validation_failed"})
            return
        self._emit({"kind": "skill_install_preview", "preview": preview.model_dump(mode="json")})

    @Slot(str, str)
    def resolveSkillInstall(self, proposal_id: str, decision: str):  # noqa: N802
        if self._application is None or decision not in {"confirm", "reject"}:
            self._emit({"kind": "skill_install_rejected", "reason": "stale_or_invalid"})
            return
        try:
            result = self._application.resolve_skill_install(proposal_id, decision)
        except Exception:
            self._emit({"kind": "skill_install_rejected", "reason": "apply_failed"})
            return
        self._emit({"kind": "skill_install_result", "result": result.model_dump(mode="json")})
    @Slot(str, str)
    def resolveReflection(self, candidate_id: str, decision: str):  # noqa: N802
        if self._application is None or self._turn_in_flight:
            self._emit({"kind": "reflection_resolution_rejected"})
            return
        if self._application.status().emergency_stop_engaged:
            self._emit({"kind": "reflection_resolution_rejected", "reason": "safety_stop"})
            return
        try:
            result = self._application.resolve_reflection(candidate_id, decision)
        except (KeyError, ValueError):
            self._emit({"kind": "reflection_resolution_rejected", "reason": "stale_or_invalid"})
            return
        workspace = self._application.reflection_workspace()
        snapshot = self._session_snapshot("reflection_action_resolved", summary=result.message)
        self._emit(
            {
                "kind": "reflection_resolved",
                "result": result.model_dump(mode="json"),
                "workspace": workspace.model_dump(mode="json"),
                "remaining_count": self._reflection_count(),
                "snapshot": snapshot.model_dump(mode="json"),
            }
        )

    @Slot(str, str)
    def resolveHonestHelp(self, candidate_id: str, decision: str):  # noqa: N802
        if self._application is None or self._turn_in_flight:
            self._emit({"kind": "honest_help_rejected"})
            return
        if self._application.status().emergency_stop_engaged:
            self._emit({"kind": "honest_help_rejected", "reason": "safety_stop"})
            return
        if decision == "dismiss":
            self._finish_honest_help_direct(candidate_id, decision)
            return
        self._turn_in_flight = True
        self._emit(
            {
                "kind": "honest_help_started",
                "snapshot": self._session_snapshot(
                    "reflection_action_started",
                    title="Думаю над принятой помощью",
                ).model_dump(mode="json"),
            }
        )
        future = self._executor.submit(
            self._application.resolve_honest_help,
            candidate_id,
            decision,
        )
        future.add_done_callback(self._finish_honest_help)

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
            conversation = self._application.conversation(conversation_id)
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
                else "Сохраняю подтверждённое изменение"
                if pending.confirmation_type not in {"commitment_create", "commitment_complete"}
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

    def _finish_continuity_thread(self, future) -> None:
        try:
            result = future.result()
        except Exception:
            result_payload = None
            snapshot = self._session_snapshot("model_unavailable", profile_id="primary", display_name=self._active_model_name())
        else:
            self._conversation_id = result.conversation_id or self._conversation_id
            result_payload = result.model_dump(mode="json")
            snapshot = self._session_snapshot("assistant_responded")
        self._turn_in_flight = False
        self._emit({"kind": "continuity_thread_result", "result": result_payload, "snapshot": snapshot.model_dump(mode="json")})

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

    def _finish_honest_help_direct(self, candidate_id: str, decision: str) -> None:
        try:
            result = self._application.resolve_honest_help(candidate_id, decision)
        except (KeyError, ValueError):
            self._emit({"kind": "honest_help_rejected", "reason": "stale_or_invalid"})
            return
        workspace = self._application.reflection_workspace()
        snapshot = self._session_snapshot("reflection_action_resolved", summary=result.message)
        self._emit(
            {
                "kind": "honest_help_resolved",
                "result": result.model_dump(mode="json"),
                "conversation": None,
                "workspace": workspace.model_dump(mode="json"),
                "remaining_count": self._reflection_count(),
                "snapshot": snapshot.model_dump(mode="json"),
            }
        )

    def _finish_honest_help(self, future) -> None:
        try:
            result = future.result()
        except Exception:
            result = None
            workspace = self._application.reflection_workspace()
            snapshot = self._session_snapshot(
                "reflection_action_failed",
                summary="Помощь не была сформулирована",
            )
        else:
            self._conversation_id = result.conversation_id or self._conversation_id
            workspace = self._application.reflection_workspace()
            snapshot = self._session_snapshot(
                "reflection_action_resolved"
                if result.status == "delivered"
                else "reflection_action_failed",
                summary=result.message,
            )
        self._turn_in_flight = False
        conversation = (
            None
            if result is None or result.conversation_id is None
            else self._application.conversation(result.conversation_id)
        )
        self._emit(
            {
                "kind": "honest_help_resolved",
                "result": None if result is None else result.model_dump(mode="json"),
                "conversation": None if conversation is None else conversation.model_dump(mode="json"),
                "workspace": workspace.model_dump(mode="json"),
                "remaining_count": self._reflection_count(),
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
        return [item.model_dump(mode="json") for item in self._application.recent_conversations()]

    def _continuity_count(self) -> int:
        if self._application is None:
            return 0
        view = self._application.shared_continuity()
        return len(view.confirmed_memories) + len(view.moments) + len(view.open_threads)

    def _reflection_count(self) -> int:
        if self._application is None:
            return 0
        view = self._application.reflection_workspace()
        return len(view.adopted) + len(view.pending) + len(view.help_offers)

    def _session_snapshot(self, method_name: str, **kwargs):
        """Serialize reducer access across the UI and the local model worker."""
        with self._session_lock:
            method = getattr(self._session, method_name)
            return method(**kwargs)

    def _emit(self, payload: dict) -> None:
        self.event.emit(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))

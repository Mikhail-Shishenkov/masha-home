"""Closed local WebChannel port for one Masha Home conversation surface."""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from threading import Lock

from PySide6.QtCore import QObject, Signal, Slot
from PySide6.QtWidgets import QFileDialog

from backend.application import ConversationTurnStatus, MashaApplication
from backend.application.human_information import (
    HumanSearchRequest,
    HumanSearchScope,
    RecallMode,
)


HOME_PROJECT_ID = "project_masha_home"
MAX_MESSAGE_CHARACTERS = 4_000
OBJECT_PAGE_SIZE = 10


class LocalConversationBridge(QObject):
    """A tiny allowlisted bridge; it never exposes application services to JavaScript."""

    event = Signal(str)

    def __init__(self, application: MashaApplication | None, parent=None):
        super().__init__(parent)
        self._application = application
        self._session = None
        self._session_lock = Lock()
        self._conversation_id: str | None = None
        self._conversation_page_revision = 0
        self._human_search_revision = 0
        self._human_search_action_refs: dict[str, str] = {}
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
        self._conversation_id = (
            None
            if conversation is None
            else conversation.conversation_id
        )

        self._clear_human_search_context()

        pending = (
            None
            if conversation is None
            else self._application.pending_confirmation(
                conversation.conversation_id
            )
        )

        if pending is not None:
            snapshot = self._session_snapshot(
                "confirmation_requested",
                title=pending.title,
                summary=pending.subject,
            )

        commitments = self._application.commitments(limit=None)

        proactive = self._application.proactive_interactions(limit=6)
        self._visible_proactive_ids = {
            item.interaction_id
            for item in proactive.items
        }

        self._emit(
            {
                "kind": "home_initial",
                "snapshot": snapshot.model_dump(mode="json"),
                "conversation": (
                    None
                    if conversation is None
                    else conversation.model_dump(mode="json")
                ),
                "recent": self._recent_payload(),
                "commitments_count": commitments.actionable_total,
                "overdue_commitments_count": sum(
                    item.status == "overdue"
                    for item in commitments.items
                ),
                "agent_runs_count": len(
                    self._application.agent_runs(limit=8).items
                ),
                "proactive_interactions_count": len(proactive.items),
                "continuity_count": self._continuity_count(),
                "reflection_items_count": self._reflection_count(),
                "pending_confirmation": (
                    None
                    if pending is None
                    else pending.model_dump(mode="json")
                ),
                "memory_candidate": self._memory_candidate_payload(
                    pending=pending
                ),
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
                "recent": self._reset_conversation_page_payload(),
                "active_conversation_id": self._conversation_id,
                "append": False,
            }
        )

    @Slot(int)
    def loadMoreConversations(self, offset: int):  # noqa: N802
        if self._application is None or self._turn_in_flight:
            return
        self._emit({
            "kind": "recent_conversations",
            "recent": self._conversation_page_payload(offset),
            "active_conversation_id": self._conversation_id,
            "append": True,
        })

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
        commitments = self._application.commitments(limit=OBJECT_PAGE_SIZE, offset=0)
        if self._session is None:
            self._session = self._application.open_home_session()
        summary = (
            "Открытых дел нет"
            if not commitments.items
            else f"Дел рядом: {commitments.total}"
        )
        snapshot = self._session_snapshot("commitments_opened", summary=summary)
        self._emit(
            {
                "kind": "commitments_loaded",
                "commitments": commitments.model_dump(mode="json"),
                "snapshot": snapshot.model_dump(mode="json"),
                "append": False,
            }
        )

    @Slot(int)
    def loadMoreCommitments(self, offset: int):  # noqa: N802
        if self._application is None or self._turn_in_flight:
            return
        commitments = self._application.commitments(
            limit=OBJECT_PAGE_SIZE,
            offset=max(0, offset),
        )
        self._emit({
            "kind": "commitments_loaded",
            "commitments": commitments.model_dump(mode="json"),
            "snapshot": None,
            "append": True,
        })

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

    @Slot()
    def refreshHomeTime(self):  # noqa: N802
        """Refresh Presentation time without changing conversation or domain state."""
        if self._application is None or self._session is None:
            return
        self._emit
        snapshot = self._session_snapshot("observe_time")

        self._emit(
            {
                "kind": "home_time",
                "snapshot": snapshot.model_dump(mode="json"),
            }
        )

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

    @Slot(str, str, bool)
    def searchInformation(self, query: str, scope: str, forgotten: bool):  # noqa: N802
        """Project existing Human Information search without a chat turn."""
        if self._application is None or self._turn_in_flight:
            self._emit({"kind": "human_search_unavailable"})
            return
        try:
            selected_scope = HumanSearchScope(scope)
        except ValueError:
            self._emit({"kind": "human_search_unavailable"})
            return
        normalized_query = query.strip()
        result = self._application.search_information(HumanSearchRequest(
            query=normalized_query,
            scope=selected_scope,
            project_id=HOME_PROJECT_ID,
            mode=(
                RecallMode.FORGOTTEN_REVIEW
                if forgotten
                else RecallMode.RETROSPECTIVE
            ),
            limit=20,
        ))
        matches = result.matches
        if self._conversation_id is not None:
            self._application.register_presented_information(
                result,
                conversation_id=self._conversation_id,
            )
        self._human_search_revision += 1
        self._human_search_action_refs = {
            f"result-{self._human_search_revision}-{index}": match.item.ref.entity_id
            for index, match in enumerate(matches, 1)
        }
        ref_by_record = {
            record_id: ref
            for ref, record_id in self._human_search_action_refs.items()
        }
        self._emit({
            "kind": "human_search_loaded",
            "query": normalized_query,
            "scope": selected_scope.value,
            "forgotten": forgotten,
            "items": [
                {
                    "kind": match.item.kind.value,
                    "label": match.item.label,
                    "state": match.item.domain_state,
                    "availability": match.item.availability.value,
                    "reference": ref_by_record[match.item.ref.entity_id],
                    "can_restore": (
                        forgotten
                        and match.item.availability.value == "forgotten"
                        and "restore" in {
                            action.value for action in match.item.ref.allowed_actions
                        }
                    ),
                }
                for match in matches
            ],
        })

    @Slot()
    def clearInformationSearch(self):  # noqa: N802
        """Clear UI action tokens and the one application-owned ordinal context."""
        self._clear_human_search_context()

    @Slot(str)
    def restoreInformation(self, reference: str):  # noqa: N802
        """Propose restoring one result selected from the latest search page."""
        if self._application is None or self._turn_in_flight:
            self._emit({"kind": "memory_restore_unavailable"})
            return
        record_id = self._human_search_action_refs.get(reference)
        if record_id is None:
            self._emit({"kind": "memory_restore_unavailable"})
            return
        if self._conversation_id is None:
            self._emit({
                "kind": "memory_restore_unavailable",
                "message": "Сначала начнём разговор — и тогда я смогу вернуть это в память.",
            })
            return
        if self._application.pending_confirmation(self._conversation_id) is not None:
            self._emit({
                "kind": "memory_restore_unavailable",
                "message": "Сначала закончим с решением, которое уже ждёт ответа.",
            })
            return
        try:
            pending = self._application.restore_information(
                record_id=record_id,
                conversation_id=self._conversation_id,
            )
        except (KeyError, RuntimeError, ValueError):
            self._emit({"kind": "memory_restore_unavailable"})
            return
        snapshot = self._session_snapshot(
            "confirmation_requested",
            title=pending.title,
            summary=pending.subject,
        )
        self._emit({
            "kind": "memory_restore_proposed",
            "pending_confirmation": pending.model_dump(mode="json"),
            "snapshot": snapshot.model_dump(mode="json"),
        })

    @Slot(str, str)
    def resolveMemoryCandidate(self, candidate_id: str, decision: str):  # noqa: N802
        """Resolve one passive candidate through the typed application boundary."""
        if self._application is None or self._turn_in_flight:
            self._emit({"kind": "memory_candidate_rejected"})
            return
        pending = self._pending_confirmation()
        candidate = self._memory_candidate_payload(pending=pending)
        if (
            candidate is None
            or candidate["candidate_id"] != candidate_id
            or decision not in {"approve", "reject"}
        ):
            self._emit({"kind": "memory_candidate_rejected"})
            return
        try:
            if decision == "approve":
                result = self._application.approve_memory_candidate(
                    candidate_id,
                    supersede_existing=candidate["relation"] == "possible_update",
                )
            else:
                result = self._application.reject_memory_candidate(candidate_id)
        except (KeyError, ValueError):
            self._emit({"kind": "memory_candidate_rejected"})
            return
        self._emit({
            "kind": "memory_candidate_resolved",
            "status": result.status,
            "message": "Запомнила." if result.status == "approved" else "Хорошо, не буду сохранять.",
            "memory_candidate": self._memory_candidate_payload(pending=self._pending_confirmation()),
        })

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
        self._clear_human_search_context()
        self._conversation_id = conversation.conversation_id
        self._application.discard_presented_information(self._conversation_id)
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
                "recent": self._reset_conversation_page_payload(),
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
        self._clear_human_search_context()
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

        # Direct UI action tokens never survive a conversation turn. The
        # application-owned PresentedEntitySet remains available just long
        # enough for the capability router to resolve an ordinal command; an
        # unhandled/model turn invalidates it inside ConversationService.
        self._invalidate_human_search_tokens()
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
        selected = self._application.commitment(commitment_id)
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

    @Slot(str)
    def proposeCommitmentCancellation(self, commitment_id: str):  # noqa: N802
        if self._application is None or self._session is None:
            self._emit({"kind": "home_unavailable"})
            return

        if self._turn_in_flight:
            self._emit({
                "kind": "commitment_operation_rejected",
                "reason": "turn_in_flight",
            })
            return

        selected = self._application.commitment(commitment_id)

        if selected is None or not selected.can_propose_completion:
            self._emit({
                "kind": "commitment_operation_rejected",
                "reason": "stale_or_invalid",
            })
            return

        try:
            result = self._application.propose_commitment_cancellation(
                commitment_id=commitment_id,
                conversation_id=self._conversation_id,
                project_id=HOME_PROJECT_ID,
            )
        except Exception:
            self._emit({
                "kind": "commitment_operation_rejected",
                "reason": "proposal_failed",
            })
            return

        self._conversation_id = result.conversation_id

        snapshot = self._session_snapshot(
            "confirmation_requested",
            title=result.pending_confirmation.title,
            summary=result.pending_confirmation.subject,
        )

        self._emit(
            {
                "kind": "commitment_cancellation_proposed",
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
                if pending.confirmation_type not in {
                    "commitment_create",
                    "commitment_complete",
                    "commitment_cancel",
                }
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
                "memory_candidate": self._memory_candidate_payload(
                    pending=None if result_payload is None else result.pending_confirmation,
                ),
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
                        for item in self._application.commitments(limit=None).items
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
        self._clear_human_search_context()
        self._executor.shutdown(wait=False, cancel_futures=True)

    def _invalidate_human_search_tokens(self) -> None:
        self._human_search_revision += 1
        self._human_search_action_refs = {}

    def _clear_human_search_context(self) -> None:
        self._invalidate_human_search_tokens()
        if self._application is not None and self._conversation_id is not None:
            self._application.discard_presented_information(self._conversation_id)

    def _active_model_name(self) -> str:
        if self._session is None:
            return "Локальная модель"
        return self._session.active_model_display_name

    def _recent_payload(self) -> dict:
        return self._reset_conversation_page_payload()

    def _pending_confirmation(self):
        if self._application is None or self._conversation_id is None:
            return None
        return self._application.pending_confirmation(self._conversation_id)

    def _memory_candidate_payload(self, *, pending) -> dict | None:
        """One safe, human-only candidate projection; IDs stay bridge-internal."""
        if self._application is None or pending is not None:
            return None
        if self._application.status().emergency_stop_engaged:
            return None
        # An existing high-priority operation (including a skill review) wins.
        if self._application.workbench().pending:
            return None
        candidates = self._application.list_pending_memory_candidates()
        if not candidates:
            return None
        item = candidates[0]
        return {
            "candidate_id": item.candidate_id,
            "summary": item.summary,
            "relation": item.relation,
            "requires_explicit_supersession": item.requires_explicit_supersession,
        }

    def _reset_conversation_page_payload(self) -> dict:
        self._conversation_page_revision += 1
        return self._conversation_page_payload(0)

    def _conversation_page_payload(self, offset: int) -> dict:
        if self._application is None:
            return {
                "items": [], "offset": 0, "page_size": OBJECT_PAGE_SIZE,
                "total": 0, "has_more": False, "next_offset": None, "query": None,
                "revision": self._conversation_page_revision,
            }
        payload = self._application.conversation_page(
            offset=max(0, offset),
            limit=OBJECT_PAGE_SIZE,
        ).model_dump(mode="json")
        payload["revision"] = self._conversation_page_revision
        return payload

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

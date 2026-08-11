"""One explainable local heartbeat over the existing temporal subsystems."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict

from backend.temporal.proactive import ProactiveDecisionEngine, ProactivePolicy
from backend.temporal.proactive_interaction import ProactiveInteractionUnavailableError
from backend.temporal.proactive_events import ProactiveEventState
from backend.temporal.proactive_runtime import ControlledProactiveRuntime
from backend.temporal.temporal_models import ProactiveDecision
from backend.temporal.temporal_runtime import TemporalRuntime
from backend.runtime.safety import AutonomySafetyStore


class DailyCycleItem(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["reminder", "check_in"]
    event_id: str | None = None
    decision: str
    state: str
    reason: str


class DailyCycleReceipt(BaseModel):
    """Technical receipt without generated message text or memory payloads."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    cycle_id: str
    started_at: datetime
    finished_at: datetime
    model_profile: str
    items: tuple[DailyCycleItem, ...] = ()
    error: str | None = None
    halted_reason: str | None = None

    @property
    def delivered_count(self) -> int:
        return sum(item.state == "delivered" and item.decision in {"remind", "check_in"} for item in self.items)

    @property
    def suppressed_count(self) -> int:
        return sum(item.decision == "suppress" for item in self.items)

    @property
    def result(self) -> str:
        if self.error:
            return "error"
        if self.delivered_count:
            return "delivered"
        return "suppress"

    @property
    def reason(self) -> str:
        if self.halted_reason is not None:
            return self.halted_reason
        delivered = next((item for item in self.items if item.state == "delivered"), None)
        if delivered is not None:
            return delivered.reason
        unavailable = next((item for item in self.items if item.reason == "local_model_unavailable"), None)
        if unavailable is not None:
            return unavailable.reason
        return self.items[-1].reason if self.items else "no_events"


class DailyRuntimeJournal:
    """Bounded local operating journal; it is not Memory or conversation history."""

    def __init__(self, path: Path, *, limit: int = 100):
        self.path = Path(path)
        self.limit = limit
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, receipt: DailyCycleReceipt) -> DailyCycleReceipt:
        rows = self.list()
        rows.append(receipt)
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(
            json.dumps([item.model_dump(mode="json") for item in rows[-self.limit :]], ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        temporary.replace(self.path)
        return receipt

    def list(self) -> list[DailyCycleReceipt]:
        if not self.path.exists():
            return []
        return [DailyCycleReceipt.model_validate(item) for item in json.loads(self.path.read_text(encoding="utf-8"))]

    def latest(self) -> DailyCycleReceipt | None:
        rows = self.list()
        return rows[-1] if rows else None


class DailyRuntime:
    """Orchestrates REMIND before CHECK_IN without owning either domain."""

    def __init__(self, *, history, temporal_engine, repository, identity_kernel, router, model_profiles, safety_store: AutonomySafetyStore):
        self.temporal_engine = temporal_engine
        self.repository = repository
        self.model_profiles = model_profiles
        self.safety_store = safety_store
        self.controlled = ControlledProactiveRuntime(
            history=history,
            temporal_engine=temporal_engine,
            repository=repository,
            identity_kernel=identity_kernel,
            router=router,
            model_profiles=model_profiles,
        )
        self.decisions = ProactiveDecisionEngine()

    def run_cycle(self, policy: ProactivePolicy) -> DailyCycleReceipt:
        started_at = self.temporal_engine.clock.now_utc()
        profile = self.model_profiles.get_active_profile()
        if self.safety_store.is_engaged():
            return DailyCycleReceipt(
                cycle_id=f"dcy1_{uuid4().hex}",
                started_at=started_at,
                finished_at=self.temporal_engine.clock.now_utc(),
                model_profile=profile.profile_id,
                halted_reason="emergency_stop_engaged",
            )
        items: list[DailyCycleItem] = []
        document = self.repository.read_document()
        commitments = {} if document is None else {item.id: item for item in document.commitments}
        temporal_context = TemporalRuntime(self.repository, self.temporal_engine).recover()
        reminders_sent, last_delivery = self.controlled.interaction_store.delivery_stats(started_at)
        reminder_blocks_checkin = False
        cycle_contact_reserved = False
        awaiting_response = any(item["state"] == "delivered" for item in self.controlled.interaction_store.list())

        for event in temporal_context.events:
            if self.safety_store.is_engaged():
                items.append(DailyCycleItem(kind="reminder", event_id=event.event_id, decision="suppress", state="suppressed", reason="emergency_stop_engaged"))
                break
            interaction = self.controlled.interaction_store.get(event.event_id)
            if interaction is not None and interaction["state"] in {"delivered", "acknowledged", "dismissed", "resolved", "expired"}:
                if interaction["state"] == "delivered":
                    reminder_blocks_checkin = True
                items.append(DailyCycleItem(kind="reminder", event_id=event.event_id, decision="suppress", state=interaction["state"], reason=f"terminal_or_delivered:{interaction['state']}"))
                continue

            if awaiting_response:
                reminder_blocks_checkin = True
                self.controlled.record_decision(event.event_id, ProactiveDecision.SUPPRESS.value, "awaiting_user_response", entity_type="temporal_event")
                items.append(DailyCycleItem(kind="reminder", event_id=event.event_id, decision="suppress", state="suppressed", reason="awaiting_user_response"))
                continue
            if cycle_contact_reserved:
                reminder_blocks_checkin = True
                self.controlled.record_decision(event.event_id, ProactiveDecision.SUPPRESS.value, "cycle_delivery_limit", entity_type="temporal_event")
                items.append(DailyCycleItem(kind="reminder", event_id=event.event_id, decision="suppress", state="suppressed", reason="cycle_delivery_limit"))
                continue

            evaluation = self.decisions.evaluate_reminder(
                policy,
                now=started_at,
                reminders_sent=reminders_sent,
                last_reminder_at=last_delivery,
            )
            self.controlled.record_decision(event.event_id, evaluation.decision.value, evaluation.reason, entity_type="temporal_event")
            if evaluation.decision is not ProactiveDecision.REMIND:
                items.append(DailyCycleItem(kind="reminder", event_id=event.event_id, decision=evaluation.decision.value, state="suppressed", reason=evaluation.reason))
                continue

            commitment = commitments[event.source_commitment_id]
            cycle_contact_reserved = True
            candidate = self.decisions.candidate(
                event,
                commitment_text=commitment.text,
                temporal_context=self.temporal_engine.context(None),
                decision=evaluation.decision,
                generated_at=started_at,
            )
            if self.safety_store.is_engaged():
                items.append(DailyCycleItem(kind="reminder", event_id=event.event_id, decision="suppress", state="suppressed", reason="emergency_stop_engaged"))
                break
            try:
                interaction = self.controlled.interactions.formulate(candidate)
                state = interaction["state"]
                if state == "delivered":
                    reminders_sent += 1
                    last_delivery = started_at
                reminder_blocks_checkin = state in {"candidate", "delivered"}
                items.append(DailyCycleItem(kind="reminder", event_id=event.event_id, decision=evaluation.decision.value, state=state, reason=evaluation.reason))
            except ProactiveInteractionUnavailableError:
                reminder_blocks_checkin = True
                items.append(DailyCycleItem(kind="reminder", event_id=event.event_id, decision=evaluation.decision.value, state="candidate", reason="local_model_unavailable"))

        try:
            if self.safety_store.is_engaged():
                checkin = None
                items.append(DailyCycleItem(kind="check_in", decision="suppress", state="suppressed", reason="emergency_stop_engaged"))
            else:
                checkin = self.controlled.run_checkin_cycle(policy, reminder_pending=reminder_blocks_checkin)
        except ProactiveInteractionUnavailableError:
            candidates = self.controlled.event_store.find_by_state(ProactiveEventState.CANDIDATE)
            event_id = candidates[-1].event_id if candidates else None
            items.append(DailyCycleItem(kind="check_in", event_id=event_id, decision="check_in", state="candidate", reason="local_model_unavailable"))
            checkin = None
        if checkin is not None and (checkin.event_id is not None or checkin.reason != "absence_threshold_not_reached"):
            items.append(DailyCycleItem(kind="check_in", event_id=checkin.event_id, decision="check_in" if checkin.decision == "delivered" else "suppress", state=checkin.decision, reason=checkin.reason or "unknown"))

        finished_at = self.temporal_engine.clock.now_utc()
        return DailyCycleReceipt(
            cycle_id=f"dcy1_{uuid4().hex}",
            started_at=started_at,
            finished_at=finished_at,
            model_profile=profile.profile_id,
            items=tuple(items),
        )

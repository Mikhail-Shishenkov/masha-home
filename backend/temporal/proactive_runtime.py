"""One controlled proactive cycle; no scheduling or autonomous decisions."""

from __future__ import annotations

from dataclasses import dataclass

from .checkin_detection import CheckInDetector
from .checkin_lifecycle import CheckInLifecycleRuntime
from .proactive import ProactivePolicy
from .proactive_events import ProactiveEventStore
from .proactive_interaction import ProactiveInteractionService, ProactiveInteractionStore
from .temporal_models import CheckInCandidate, ProactiveDecision
from .temporal_runtime import TemporalRuntime


@dataclass(frozen=True)
class ProactiveCycleResult:
    decision: str
    message: str | None = None
    reason: str | None = None


class ControlledProactiveRuntime:
    def __init__(self, *, history, temporal_engine, repository, identity_kernel, router, model_profiles):
        self.history = history
        self.temporal_engine = temporal_engine
        self.repository = repository
        self.event_store = ProactiveEventStore(repository)
        self.interaction_store = ProactiveInteractionStore(repository)
        self.interactions = ProactiveInteractionService(store=self.interaction_store, identity_kernel=identity_kernel, router=router, model_profiles=model_profiles)

    def run_checkin_cycle(self, policy: ProactivePolicy) -> ProactiveCycleResult:
        now = self.temporal_engine.clock.now_utc()
        event = CheckInDetector(self.history, self.temporal_engine, self.event_store).detect(policy)
        if event is None:
            return ProactiveCycleResult("suppress", reason="absence_threshold_not_reached")
        reminder_pending = any(
            (record := self.interaction_store.get(item.event_id)) is None or record["state"] == "candidate"
            for item in TemporalRuntime(self.repository, self.temporal_engine).recover().events
        )
        sent, last_delivery = self.interaction_store.delivery_stats(now)
        evaluation = CheckInLifecycleRuntime(self.event_store).evaluate(event.event_id, policy, now=now, reminders_sent=sent, last_delivery_at=last_delivery, reminder_pending=reminder_pending)
        self._record_decision(event.event_id, evaluation.decision.value, evaluation.reason)
        if evaluation.decision is not ProactiveDecision.CHECK_IN:
            return ProactiveCycleResult("suppress", reason=evaluation.reason)
        payload = evaluation.event.payload
        candidate = CheckInCandidate(event_id=evaluation.event.event_id, absence_duration_seconds=int(payload["absence_seconds"]), last_message_at=payload["anchor_created_at"], current_local_time=self.temporal_engine.clock.now_local(), proactive_level=policy.proactive_level)
        interaction = self.interactions.formulate(candidate)
        return ProactiveCycleResult(interaction["state"], message=interaction.get("message_text"), reason=evaluation.reason)

    def _record_decision(self, event_id: str, decision: str, reason: str) -> None:
        previous = [item for item in self.repository.list_audit_events() if item["action"] == "proactive_decision" and item["entity_id"] == event_id]
        payload = {"decision": decision, "reason": reason, "model_profile": self.interactions.model_profiles.get_active_profile().profile_id}
        if previous and previous[-1]["payload"] == payload:
            return
        self.repository.record_event(action="proactive_decision", entity_type="proactive_event", entity_id=event_id, payload=payload)

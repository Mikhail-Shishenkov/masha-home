"""Pure, deterministic initiative permission checks for MEM-12.1."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, time
from enum import Enum
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .temporal_engine import MOSCOW, TemporalContext
from .temporal_models import CommitmentDueEvent, ProactiveCandidate, ProactiveDecision


class ProactiveEventOrigin(str, Enum):
    """Trust boundary: only local deterministic events exist in MEM-12.9."""

    LOCAL_TEMPORAL_EVENT = "local_temporal_event"
    EXTERNAL_EVENT = "external_event"


@dataclass(frozen=True)
class ProactiveEvaluation:
    decision: ProactiveDecision
    reason: str


class ProactivePolicy(BaseModel):
    """User-controlled local operating policy, separate from identity and memory."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    enabled: bool = False
    proactive_level: int = Field(default=0, ge=0, le=5)
    cooldown_seconds: int = Field(default=86_400, ge=0)
    quiet_hours_start: time | None = None
    quiet_hours_end: time | None = None
    maximum_reminders: int = Field(default=1, ge=0)
    allow_commitment_reminders: bool = False
    allow_checkins: bool = False
    daily_message_limit: int = Field(default=1, ge=0)
    absence_threshold_seconds: int = Field(default=0, ge=0)
    runtime_mode: str = Field(default="manual", pattern="^(manual|background)$")
    cycle_interval_seconds: int = Field(default=300, ge=10)

    @model_validator(mode="after")
    def validate_quiet_hours(self):
        if (self.quiet_hours_start is None) != (self.quiet_hours_end is None):
            raise ValueError("quiet hours require both start and end")
        return self


class ProactiveDecisionEngine:
    """Returns permission only; it never creates text, sends, or mutates."""

    @staticmethod
    def external_boundary(origin: ProactiveEventOrigin) -> tuple[ProactiveDecision | None, str]:
        if origin is ProactiveEventOrigin.EXTERNAL_EVENT:
            return ProactiveDecision.SUPPRESS, "external_event_not_implemented"
        return None, "local_temporal_event"

    def decide(
        self,
        event: CommitmentDueEvent,
        policy: ProactivePolicy,
        *,
        now: datetime,
        last_reminder_at: datetime | None = None,
        reminders_sent: int = 0,
        mutation_requested: bool = False,
    ) -> ProactiveDecision:
        return self.evaluate_reminder(
            policy,
            now=now,
            last_reminder_at=last_reminder_at,
            reminders_sent=reminders_sent,
            mutation_requested=mutation_requested,
        ).decision

    def evaluate_reminder(
        self,
        policy: ProactivePolicy,
        *,
        now: datetime,
        last_reminder_at: datetime | None = None,
        reminders_sent: int = 0,
        mutation_requested: bool = False,
    ) -> ProactiveEvaluation:
        """Return a deterministic permission and an application-owned reason."""
        if mutation_requested:
            return ProactiveEvaluation(ProactiveDecision.REQUIRE_CONFIRMATION, "mutation_requires_confirmation")
        if not policy.enabled:
            return ProactiveEvaluation(ProactiveDecision.SUPPRESS, "proactive_disabled")
        if policy.proactive_level < 1:
            return ProactiveEvaluation(ProactiveDecision.SUPPRESS, "level_below_reminder")
        if not policy.allow_commitment_reminders:
            return ProactiveEvaluation(ProactiveDecision.SUPPRESS, "reminders_disabled")
        if self._in_quiet_hours(now, policy):
            return ProactiveEvaluation(ProactiveDecision.SUPPRESS, "quiet_hours")
        if reminders_sent >= min(policy.maximum_reminders, policy.daily_message_limit):
            return ProactiveEvaluation(ProactiveDecision.SUPPRESS, "daily_limit")
        if last_reminder_at is not None and (now - last_reminder_at).total_seconds() < policy.cooldown_seconds:
            return ProactiveEvaluation(ProactiveDecision.SUPPRESS, "cooldown")
        return ProactiveEvaluation(ProactiveDecision.REMIND, "authorised")

    def decide_checkin(self, policy: ProactivePolicy, *, absence_seconds: int | None, now: datetime, last_reminder_at: datetime | None = None, reminders_sent: int = 0) -> ProactiveDecision:
        if not policy.enabled or policy.proactive_level < 2 or not policy.allow_checkins: return ProactiveDecision.SUPPRESS
        if absence_seconds is None or absence_seconds < policy.absence_threshold_seconds: return ProactiveDecision.SUPPRESS
        if self._in_quiet_hours(now, policy) or reminders_sent >= policy.daily_message_limit: return ProactiveDecision.SUPPRESS
        if last_reminder_at is not None and (now-last_reminder_at).total_seconds() < policy.cooldown_seconds: return ProactiveDecision.SUPPRESS
        return ProactiveDecision.CHECK_IN

    @staticmethod
    def candidate(
        event: CommitmentDueEvent,
        *,
        commitment_text: str,
        temporal_context: TemporalContext,
        decision: ProactiveDecision,
        generated_at: datetime,
    ) -> ProactiveCandidate:
        """Build a bounded, non-delivered candidate after a policy decision."""
        return ProactiveCandidate(
            candidate_id=f"{event.event_id}:{decision.value}",
            event=event,
            source_commitment_id=event.source_commitment_id,
            source_commitment_text=commitment_text,
            temporal_context=temporal_context,
            decision=decision,
            generated_at=generated_at,
        )

    @staticmethod
    def _in_quiet_hours(now: datetime, policy: ProactivePolicy) -> bool:
        if policy.quiet_hours_start is None or policy.quiet_hours_end is None:
            return False
        current = now.astimezone(MOSCOW).timetz().replace(tzinfo=None)
        start, end = policy.quiet_hours_start, policy.quiet_hours_end
        if start == end:
            return True
        if start < end:
            return start <= current < end
        return current >= start or current < end


class ProactivePolicyStore:
    """Local operating configuration; deliberately separate from identity/memory."""
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.save(ProactivePolicy())

    def load(self) -> ProactivePolicy:
        return ProactivePolicy.model_validate(json.loads(self.path.read_text(encoding="utf-8")))

    def save(self, policy: ProactivePolicy) -> ProactivePolicy:
        self.path.write_text(
            json.dumps(policy.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        return policy

"""Bounded, receipt-first application agent loop with no LLM planner."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Callable, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, JsonValue, model_validator

from .autonomy import (
    ActionAutonomyEngine,
    ActionAutonomyPolicyStore,
    ActionDecision,
    ActionEvaluation,
    ActionRequest,
)
from .models import utc_now
from .registry import SkillRegistry
from .tools import ToolAdapter


class StrictAgentModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class AgentStepStatus(str, Enum):
    AWAITING_CONFIRMATION = "awaiting_confirmation"
    DENIED = "denied"
    EXECUTING = "executing"
    VERIFIED = "verified"
    FAILED = "failed"


class AgentRunStatus(str, Enum):
    RUNNING = "running"
    AWAITING_CONFIRMATION = "awaiting_confirmation"
    COMPLETED = "completed"
    DENIED = "denied"
    FAILED = "failed"
    BUDGET_EXHAUSTED = "budget_exhausted"


TERMINAL_RUN_STATES = {
    AgentRunStatus.COMPLETED,
    AgentRunStatus.DENIED,
    AgentRunStatus.FAILED,
    AgentRunStatus.BUDGET_EXHAUSTED,
}


class AgentStep(StrictAgentModel):
    step_id: str = Field(pattern=r"^step_[a-z0-9_]{1,60}$")
    title: str = Field(min_length=3, max_length=200)
    tool_id: str = Field(pattern=r"^[a-z][a-z0-9_-]{1,63}$")
    operation: str = Field(pattern=r"^[a-z][a-z0-9_]{1,63}$")
    action: ActionRequest
    inputs: dict[str, JsonValue] = Field(default_factory=dict)

    @model_validator(mode="after")
    def bounded_inputs(self):
        serialized = json.dumps(self.inputs, ensure_ascii=False, sort_keys=True)
        if len(serialized.encode("utf-8")) > 16_384:
            raise ValueError("agent step inputs exceed 16 KiB")
        return self


class AgentPlan(StrictAgentModel):
    plan_id: str = Field(pattern=r"^plan_[a-z0-9_-]{3,80}$")
    goal: str = Field(min_length=5, max_length=500)
    steps: tuple[AgentStep, ...] = Field(min_length=1, max_length=20)
    max_steps: int = Field(default=10, ge=1, le=20)
    max_duration_seconds: int = Field(default=300, ge=1, le=3600)
    created_at: AwareDatetime

    @model_validator(mode="after")
    def unique_steps(self):
        ids = [item.step_id for item in self.steps]
        if len(ids) != len(set(ids)):
            raise ValueError("agent plan contains duplicate step ids")
        return self

    def digest(self) -> str:
        payload = self.model_dump(mode="json")
        return hashlib.sha256(
            json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
        ).hexdigest()


class AgentStepReceipt(StrictAgentModel):
    step_id: str
    title: str
    tool_id: str
    operation: str
    status: AgentStepStatus
    policy_decision: ActionDecision
    policy_reason: str
    confirmation_required: bool = False
    confirmed_at: AwareDatetime | None = None
    confirmed_by: Literal["misha"] | None = None
    started_at: AwareDatetime | None = None
    finished_at: AwareDatetime | None = None
    result_summary: str | None = Field(default=None, max_length=500)
    verification_code: str | None = Field(default=None, max_length=200)

    @model_validator(mode="after")
    def confirmation_provenance(self):
        if (self.confirmed_at is None) != (self.confirmed_by is None):
            raise ValueError("confirmation requires both timestamp and actor")
        return self


class AgentRunReceipt(StrictAgentModel):
    plan_id: str
    plan_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    goal: str
    status: AgentRunStatus
    started_at: AwareDatetime
    updated_at: AwareDatetime
    finished_at: AwareDatetime | None = None
    terminal_reason: str | None = None
    steps: tuple[AgentStepReceipt, ...] = ()

    @model_validator(mode="after")
    def unique_step_receipts(self):
        ids = [item.step_id for item in self.steps]
        if len(ids) != len(set(ids)):
            raise ValueError("agent run contains duplicate step receipts")
        if self.status in TERMINAL_RUN_STATES and self.finished_at is None:
            raise ValueError("terminal agent run requires finished_at")
        return self


class AgentRunJournal(StrictAgentModel):
    schema_version: Literal["1.0"] = "1.0"
    runs: tuple[AgentRunReceipt, ...] = ()


class AgentRunError(RuntimeError):
    pass


class AgentRunStore:
    """Bounded local receipts; no raw inputs, outputs, Memory, or conversation data."""

    def __init__(self, path: Path, *, limit: int = 100):
        self.path = Path(path)
        self.limit = limit

    def list(self) -> tuple[AgentRunReceipt, ...]:
        if not self.path.exists():
            return ()
        return AgentRunJournal.model_validate(
            json.loads(self.path.read_text(encoding="utf-8"))
        ).runs

    def get(self, plan_id: str) -> AgentRunReceipt | None:
        return next((item for item in self.list() if item.plan_id == plan_id), None)

    def save(self, receipt: AgentRunReceipt) -> AgentRunReceipt:
        rows = list(self.list())
        index = next((index for index, item in enumerate(rows) if item.plan_id == receipt.plan_id), None)
        if index is None:
            rows.append(receipt)
        else:
            rows[index] = receipt
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary.write_text(
            json.dumps(
                AgentRunJournal(runs=tuple(rows[-self.limit :])).model_dump(mode="json"),
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        temporary.replace(self.path)
        return receipt


class BoundedAgentLoop:
    """Executes only injected tools after deterministic permission and verification."""

    def __init__(
        self,
        *,
        registry: SkillRegistry,
        policy_store: ActionAutonomyPolicyStore,
        run_store: AgentRunStore,
        tools: tuple[ToolAdapter, ...],
        clock: Callable[[], datetime] = utc_now,
    ):
        self.registry = registry
        self.policy_store = policy_store
        self.run_store = run_store
        self.tools = {tool.tool_id: tool for tool in tools}
        if len(self.tools) != len(tools):
            raise ValueError("duplicate tool id")
        self._clock = clock
        self.decisions = ActionAutonomyEngine()

    def run(self, plan: AgentPlan) -> AgentRunReceipt:
        digest = plan.digest()
        receipt = self.run_store.get(plan.plan_id)
        if receipt is not None and receipt.plan_sha256 != digest:
            raise AgentRunError("plan id already belongs to different plan content")
        if receipt is not None and receipt.status in TERMINAL_RUN_STATES:
            return receipt
        if receipt is None:
            now = self._now()
            receipt = self.run_store.save(
                AgentRunReceipt(
                    plan_id=plan.plan_id,
                    plan_sha256=digest,
                    goal=plan.goal,
                    status=AgentRunStatus.RUNNING,
                    started_at=now,
                    updated_at=now,
                )
            )

        existing = {item.step_id: item for item in receipt.steps}
        interrupted = next(
            (item for item in receipt.steps if item.status is AgentStepStatus.EXECUTING),
            None,
        )
        if interrupted is not None:
            return self._terminal(
                receipt,
                AgentRunStatus.FAILED,
                "interrupted_execution_requires_review",
            )

        for step in plan.steps:
            previous = existing.get(step.step_id)
            if previous is not None and previous.status is AgentStepStatus.VERIFIED:
                continue
            if self._executed_count(receipt) >= plan.max_steps:
                return self._terminal(receipt, AgentRunStatus.BUDGET_EXHAUSTED, "step_budget_exhausted")
            if (self._now() - receipt.started_at).total_seconds() >= plan.max_duration_seconds:
                return self._terminal(receipt, AgentRunStatus.BUDGET_EXHAUSTED, "time_budget_exhausted")

            tool = self.tools.get(step.tool_id)
            if tool is None:
                failed = self._step_receipt(
                    step,
                    ActionEvaluation(decision=ActionDecision.DENY, reason="tool_not_injected"),
                    status=AgentStepStatus.FAILED,
                    finished=True,
                    result_summary="Configured tool is unavailable.",
                    verification_code="tool_not_injected",
                )
                receipt = self._with_step(receipt, failed, AgentRunStatus.FAILED, "tool_not_injected")
                return receipt

            evaluation = self.decisions.evaluate(
                step.action,
                policy=self.policy_store.load(),
                registry=self.registry,
            )
            if evaluation.decision is ActionDecision.DENY:
                denied = self._step_receipt(
                    step,
                    evaluation,
                    status=AgentStepStatus.DENIED,
                    finished=True,
                )
                return self._with_step(receipt, denied, AgentRunStatus.DENIED, evaluation.reason)

            confirmed_at = None if previous is None else previous.confirmed_at
            if evaluation.decision is ActionDecision.REQUIRE_CONFIRMATION and confirmed_at is None:
                waiting = self._step_receipt(
                    step,
                    evaluation,
                    status=AgentStepStatus.AWAITING_CONFIRMATION,
                    confirmation_required=True,
                )
                return self._with_step(
                    receipt,
                    waiting,
                    AgentRunStatus.AWAITING_CONFIRMATION,
                    evaluation.reason,
                    terminal=False,
                )

            executing = self._step_receipt(
                step,
                evaluation,
                status=AgentStepStatus.EXECUTING,
                confirmed_at=confirmed_at,
                confirmed_by=None if confirmed_at is None else "misha",
                started=True,
            )
            receipt = self._with_step(
                receipt,
                executing,
                AgentRunStatus.RUNNING,
                None,
                terminal=False,
            )
            try:
                result = tool.execute(step.operation, step.inputs)
            except Exception as error:
                failed = executing.model_copy(
                    update={
                        "status": AgentStepStatus.FAILED,
                        "finished_at": self._now(),
                        "result_summary": "Tool raised an unexpected local error.",
                        "verification_code": f"tool_exception:{type(error).__name__}",
                    }
                )
                return self._with_step(receipt, failed, AgentRunStatus.FAILED, "tool_exception")
            if not result.success:
                failed = executing.model_copy(
                    update={
                        "status": AgentStepStatus.FAILED,
                        "finished_at": self._now(),
                        "result_summary": result.summary,
                        "verification_code": result.evidence_code,
                    }
                )
                return self._with_step(receipt, failed, AgentRunStatus.FAILED, result.error or "tool_failed")
            verification = tool.verify(step.operation, step.inputs, result)
            if not verification.verified:
                failed = executing.model_copy(
                    update={
                        "status": AgentStepStatus.FAILED,
                        "finished_at": self._now(),
                        "result_summary": result.summary,
                        "verification_code": verification.code,
                    }
                )
                return self._with_step(receipt, failed, AgentRunStatus.FAILED, "verification_failed")
            verified = executing.model_copy(
                update={
                    "status": AgentStepStatus.VERIFIED,
                    "finished_at": self._now(),
                    "result_summary": result.summary,
                    "verification_code": verification.code,
                }
            )
            receipt = self._with_step(
                receipt,
                verified,
                AgentRunStatus.RUNNING,
                None,
                terminal=False,
            )
            existing[step.step_id] = verified

        return self._terminal(receipt, AgentRunStatus.COMPLETED, "all_steps_verified")

    def confirm(self, plan_id: str, step_id: str) -> AgentRunReceipt:
        receipt = self.run_store.get(plan_id)
        if receipt is None:
            raise AgentRunError("agent run not found")
        if receipt.status is not AgentRunStatus.AWAITING_CONFIRMATION:
            raise AgentRunError("agent run is not awaiting confirmation")
        step = next((item for item in receipt.steps if item.step_id == step_id), None)
        if step is None or step.status is not AgentStepStatus.AWAITING_CONFIRMATION:
            raise AgentRunError("agent step is not awaiting confirmation")
        confirmed = step.model_copy(
            update={"confirmed_at": self._now(), "confirmed_by": "misha"}
        )
        return self._with_step(
            receipt,
            confirmed,
            AgentRunStatus.AWAITING_CONFIRMATION,
            receipt.terminal_reason,
            terminal=False,
        )

    def _step_receipt(
        self,
        step: AgentStep,
        evaluation: ActionEvaluation,
        *,
        status: AgentStepStatus,
        confirmation_required: bool = False,
        confirmed_at: datetime | None = None,
        confirmed_by: Literal["misha"] | None = None,
        started: bool = False,
        finished: bool = False,
        result_summary: str | None = None,
        verification_code: str | None = None,
    ) -> AgentStepReceipt:
        now = self._now()
        return AgentStepReceipt(
            step_id=step.step_id,
            title=step.title,
            tool_id=step.tool_id,
            operation=step.operation,
            status=status,
            policy_decision=evaluation.decision,
            policy_reason=evaluation.reason,
            confirmation_required=confirmation_required,
            confirmed_at=confirmed_at,
            confirmed_by=confirmed_by,
            started_at=now if started else None,
            finished_at=now if finished else None,
            result_summary=result_summary,
            verification_code=verification_code,
        )

    def _with_step(
        self,
        receipt: AgentRunReceipt,
        step: AgentStepReceipt,
        status: AgentRunStatus,
        reason: str | None,
        *,
        terminal: bool | None = None,
    ) -> AgentRunReceipt:
        rows = list(receipt.steps)
        index = next((index for index, item in enumerate(rows) if item.step_id == step.step_id), None)
        if index is None:
            rows.append(step)
        else:
            rows[index] = step
        now = self._now()
        is_terminal = status in TERMINAL_RUN_STATES if terminal is None else terminal
        return self.run_store.save(
            receipt.model_copy(
                update={
                    "steps": tuple(rows),
                    "status": status,
                    "updated_at": now,
                    "finished_at": now if is_terminal else None,
                    "terminal_reason": reason,
                }
            )
        )

    def _terminal(
        self,
        receipt: AgentRunReceipt,
        status: AgentRunStatus,
        reason: str,
    ) -> AgentRunReceipt:
        now = self._now()
        return self.run_store.save(
            receipt.model_copy(
                update={
                    "status": status,
                    "updated_at": now,
                    "finished_at": now,
                    "terminal_reason": reason,
                }
            )
        )

    @staticmethod
    def _executed_count(receipt: AgentRunReceipt) -> int:
        return sum(
            item.status in {AgentStepStatus.EXECUTING, AgentStepStatus.VERIFIED, AgentStepStatus.FAILED}
            for item in receipt.steps
        )

    def _now(self) -> datetime:
        value = self._clock()
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("agent loop clock must return aware datetime")
        return value

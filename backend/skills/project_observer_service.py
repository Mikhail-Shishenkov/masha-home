"""Application-owned plans for the bounded Project Observer tool."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Callable

from pydantic import BaseModel, ConfigDict, JsonValue

from .agent_loop import AgentPlan, AgentRunReceipt, AgentStep, BoundedAgentLoop
from .autonomy import ActionRequest
from .models import SkillCapability, SkillRisk, utc_now
from .project_observer import (
    PROJECT_OBSERVER_SKILL_ID,
    PROJECT_OBSERVER_TOOL_ID,
    PROJECT_SCOPE,
)


class ProjectObservation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    receipt: AgentRunReceipt
    output: JsonValue | None = None


class ProjectObserverService:
    """Creates one-step application plans; it cannot widen tool or policy scope."""

    def __init__(
        self,
        *,
        agent_loop: BoundedAgentLoop,
        clock: Callable[[], datetime] = utc_now,
    ):
        self.agent_loop = agent_loop
        self._clock = clock

    def observe(self, operation: str, inputs: dict[str, JsonValue]) -> ProjectObservation:
        created_at = self._now()
        identity = hashlib.sha256(
            json.dumps(
                {
                    "operation": operation,
                    "inputs": inputs,
                    "created_at": created_at.isoformat(),
                },
                ensure_ascii=False,
                sort_keys=True,
            ).encode("utf-8")
        ).hexdigest()[:24]
        plan = AgentPlan(
            plan_id=f"plan_observe_{identity}",
            goal="Безопасно прочитать ограниченную часть локального проекта",
            steps=(
                AgentStep(
                    step_id="step_observe_project",
                    title="Прочитать разрешённое состояние проекта",
                    tool_id=PROJECT_OBSERVER_TOOL_ID,
                    operation=operation,
                    action=ActionRequest(
                        skill_id=PROJECT_OBSERVER_SKILL_ID,
                        capability=SkillCapability.LOCAL_READ,
                        scope=PROJECT_SCOPE,
                        risk_level=SkillRisk.OBSERVE,
                        required_autonomy_level=1,
                    ),
                    inputs=inputs,
                ),
            ),
            max_steps=1,
            max_duration_seconds=30,
            created_at=created_at,
        )
        captured: list[JsonValue | None] = []
        receipt = self.agent_loop.run(
            plan,
            on_verified_result=lambda _step, result: captured.append(result.output),
        )
        return ProjectObservation(
            receipt=receipt,
            output=captured[0] if captured else None,
        )

    def _now(self) -> datetime:
        value = self._clock()
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("project observer clock must return aware datetime")
        return value

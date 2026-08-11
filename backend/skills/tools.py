"""Injected tool boundary and a deterministic Fake Tool for Stage 16.3."""

from __future__ import annotations

import hashlib
import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Callable

from pydantic import BaseModel, ConfigDict, Field, JsonValue


class StrictToolModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ToolExecutionResult(StrictToolModel):
    success: bool
    summary: str = Field(min_length=1, max_length=500)
    output: JsonValue | None = None
    evidence_code: str = Field(min_length=1, max_length=200)
    error: str | None = Field(default=None, max_length=500)


class ToolVerification(StrictToolModel):
    verified: bool
    code: str = Field(min_length=1, max_length=200)


class ToolAdapter(ABC):
    """Application-injected operation boundary; tools never grant permission."""

    skill_id: str
    tool_id: str

    @abstractmethod
    def execute(self, operation: str, inputs: dict[str, JsonValue]) -> ToolExecutionResult:
        pass

    @abstractmethod
    def verify(
        self,
        operation: str,
        inputs: dict[str, JsonValue],
        result: ToolExecutionResult,
    ) -> ToolVerification:
        pass


@dataclass
class FakeTool(ToolAdapter):
    """No-I/O tool for tests; supported operations are deterministic."""

    skill_id: str = "project_observer"
    tool_id: str = "fake"
    on_execute: Callable[[str], None] | None = None
    calls: list[str] = field(default_factory=list, init=False)

    def execute(self, operation: str, inputs: dict[str, JsonValue]) -> ToolExecutionResult:
        self.calls.append(operation)
        if self.on_execute is not None:
            self.on_execute(operation)
        digest = hashlib.sha256(
            json.dumps(inputs, ensure_ascii=False, sort_keys=True).encode("utf-8")
        ).hexdigest()[:16]
        if operation == "fail":
            return ToolExecutionResult(
                success=False,
                summary="Fake Tool reported a deterministic failure.",
                evidence_code=f"fake-failed:{digest}",
                error="simulated_failure",
            )
        if operation not in {"echo", "unverified"}:
            return ToolExecutionResult(
                success=False,
                summary="Fake Tool does not support this operation.",
                evidence_code=f"fake-unsupported:{digest}",
                error="unsupported_operation",
            )
        return ToolExecutionResult(
            success=True,
            summary="Fake Tool completed the bounded operation.",
            output=inputs,
            evidence_code=f"fake-result:{digest}",
        )

    def verify(
        self,
        operation: str,
        inputs: dict[str, JsonValue],
        result: ToolExecutionResult,
    ) -> ToolVerification:
        if not result.success:
            return ToolVerification(verified=False, code="execution_failed")
        if operation == "unverified":
            return ToolVerification(verified=False, code="simulated_unverified_result")
        expected = hashlib.sha256(
            json.dumps(inputs, ensure_ascii=False, sort_keys=True).encode("utf-8")
        ).hexdigest()[:16]
        return ToolVerification(
            verified=(result.output == inputs and result.evidence_code == f"fake-result:{expected}"),
            code="fake_evidence_verified",
        )

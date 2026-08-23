"""Durable, secret-free journal controlling offline recovery lifecycle."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from pydantic import ValidationError

from .recovery_models import RecoveryPhase, RecoveryState


class RecoveryError(RuntimeError):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


class RecoveryJournal:
    def __init__(self, project_root: Path):
        self.root = Path(project_root)
        self.path = self.root / "local-data" / "recovery" / "state.json"

    def load(self) -> RecoveryState | None:
        if not self.path.exists():
            return None
        try:
            return RecoveryState.model_validate_json(self.path.read_bytes())
        except (OSError, ValidationError, ValueError) as error:
            raise RecoveryError("recovery_blocked") from error

    def save(self, state: RecoveryState) -> RecoveryState:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(state.model_dump_json(indent=2) + "\n", encoding="utf-8")
        temporary.replace(self.path)
        return state

    def transition(self, state: RecoveryState, phase: RecoveryPhase, *, error_code: str | None = None) -> RecoveryState:
        return self.save(state.model_copy(update={
            "phase": phase,
            "updated_at": datetime.now(timezone.utc),
            "error_code": error_code,
        }))

    def assert_start_allowed(self) -> None:
        state = self.load()
        if state is not None and state.phase in {
            RecoveryPhase.APPLYING,
            RecoveryPhase.VERIFYING,
            RecoveryPhase.ROLLING_BACK,
            RecoveryPhase.BLOCKED,
        }:
            raise RecoveryError("recovery_blocked")

    def is_hold(self) -> bool:
        state = self.load()
        return state is not None and state.phase is RecoveryPhase.HOLD

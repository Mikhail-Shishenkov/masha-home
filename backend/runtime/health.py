"""Read-only daily-use health checks for the local Masha Home runtime."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict

from backend.temporal.proactive import ProactivePolicyStore


class HealthCheck(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str
    status: Literal["ok", "warning", "error"]
    detail: str


class RuntimeHealthReport(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    status: Literal["ready", "degraded", "unavailable"]
    checks: tuple[HealthCheck, ...]


class RuntimeHealthService:
    """Checks existing boundaries without repairing or mutating them."""

    def __init__(self, *, service, project_root: Path, daemon):
        self.service = service
        self.project_root = Path(project_root)
        self.daemon = daemon

    def inspect(self) -> RuntimeHealthReport:
        checks = (
            self._identity_memory(),
            self._sqlite(),
            self._history(),
            self._model(),
            self._policy(),
            self._backup(),
            self._daemon(),
        )
        if any(item.status == "error" for item in checks):
            status = "unavailable"
        elif any(item.status == "warning" for item in checks):
            status = "degraded"
        else:
            status = "ready"
        return RuntimeHealthReport(status=status, checks=checks)

    def _daemon(self) -> HealthCheck:
        try:
            liveness = self.daemon.liveness()
        except Exception as error:
            return HealthCheck(
                name="daemon",
                status="warning",
                detail=f"состояние неизвестно: {type(error).__name__}: {error}",
            )
        if liveness.state == "running":
            return HealthCheck(name="daemon", status="ok", detail="работает")
        if liveness.state == "stopped":
            return HealthCheck(name="daemon", status="warning", detail="не запущен")
        return HealthCheck(
            name="daemon",
            status="warning",
            detail=f"состояние неизвестно: {liveness.detail}",
        )

    def _identity_memory(self) -> HealthCheck:
        try:
            self.service.identity_kernel.validate_memory_identity(self.service.memory_retriever.memory_store)
            version = self.service.identity_kernel.build_context().identity_version
            return HealthCheck(name="identity", status="ok", detail=f"manifest и memory согласованы: {version}")
        except Exception as error:
            return HealthCheck(name="identity", status="error", detail=str(error))

    def _sqlite(self) -> HealthCheck:
        try:
            with self.service.memory_retriever.memory_store._connection() as connection:
                result = connection.execute("PRAGMA quick_check").fetchone()[0]
            status = "ok" if result == "ok" else "error"
            return HealthCheck(name="sqlite", status=status, detail=str(result))
        except Exception as error:
            return HealthCheck(name="sqlite", status="error", detail=str(error))

    def _history(self) -> HealthCheck:
        try:
            latest = self.service.history.latest_message()
            return HealthCheck(name="history", status="ok", detail="история читается" if latest is not None else "история пуста")
        except Exception as error:
            return HealthCheck(name="history", status="error", detail=str(error))

    def _model(self) -> HealthCheck:
        try:
            profile = self.service.model_profiles.get_active_profile()
            provider = self.service.router.get_provider(profile.provider_id)
            if provider is None or not provider.is_available():
                return HealthCheck(name="model", status="warning", detail=f"{profile.profile_id}: Ollama недоступна")
            model_available = getattr(provider, "is_model_available", None)
            if callable(model_available) and not model_available(profile.model_id):
                return HealthCheck(name="model", status="warning", detail=f"модель {profile.model_id} недоступна")
            return HealthCheck(name="model", status="ok", detail=f"{profile.profile_id}: {profile.model_id}")
        except Exception as error:
            return HealthCheck(name="model", status="error", detail=str(error))

    def _policy(self) -> HealthCheck:
        try:
            policy = ProactivePolicyStore(self.service.model_profiles.path.parent / "proactive-policy.json").load()
            return HealthCheck(name="policy", status="ok", detail=f"{'включена' if policy.enabled else 'выключена'}, режим {policy.runtime_mode}, уровень {policy.proactive_level}")
        except Exception as error:
            return HealthCheck(name="policy", status="error", detail=str(error))

    def _backup(self) -> HealthCheck:
        backups = sorted((self.project_root / "local-data" / "memory-backups").glob("*.sqlite3"), key=lambda path: path.stat().st_mtime, reverse=True)
        if not backups:
            return HealthCheck(name="backup", status="warning", detail="проверенной резервной копии пока нет")
        latest = backups[0]
        try:
            with sqlite3.connect(latest) as connection:
                result = connection.execute("PRAGMA quick_check").fetchone()[0]
            return HealthCheck(name="backup", status="ok" if result == "ok" else "error", detail=f"{latest.name}: {result}")
        except Exception as error:
            return HealthCheck(name="backup", status="error", detail=str(error))

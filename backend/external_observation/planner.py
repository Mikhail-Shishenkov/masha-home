"""Local-only query planning for explicit external observations."""

from __future__ import annotations

import re
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field

from backend.llm.model_models import MessageRole, ModelCapabilities, ModelMessage, ModelRequest, PrivacyScope
from backend.llm.model_provider import ModelProviderUnavailableError, ModelTimeoutError

from .context import ExternalContextHint, requires_local_context_resolution


class ExternalQueryPlan(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    query: str | None = Field(default=None, max_length=300)
    clarification_required: bool = False
    source: str = Field(min_length=1, max_length=50)


class ExternalQueryPlanner(Protocol):
    def plan(
        self,
        *,
        current_message: str,
        query_hint: str | None,
        recent_messages: tuple[str, ...],
        memory_hints: tuple[str, ...] = (),
        context_hints: tuple[ExternalContextHint, ...] = (),
    ) -> ExternalQueryPlan: ...


_MEANINGFUL = re.compile(r"[a-zа-я0-9][a-zа-я0-9+.#:/_-]{1,}", re.IGNORECASE)


def _bounded_query(value: str) -> str | None:
    normalized = " ".join(value.replace("\n", " ").split()).strip(" `\"'.,;:—-")
    if not normalized or len(normalized) > 300 or not _MEANINGFUL.findall(normalized):
        return None
    return normalized


class LocalExternalQueryPlanner:
    """Uses the active local model only when deterministic extraction is insufficient."""

    def __init__(self, *, router, identity_kernel, model_profiles):
        self.router = router
        self.identity_kernel = identity_kernel
        self.model_profiles = model_profiles

    def plan(
        self,
        *,
        current_message: str,
        query_hint: str | None,
        recent_messages: tuple[str, ...],
        memory_hints: tuple[str, ...] = (),
        context_hints: tuple[ExternalContextHint, ...] = (),
    ) -> ExternalQueryPlan:
        deterministic = _bounded_query(query_hint or "")
        if deterministic is not None and not requires_local_context_resolution(query_hint):
            return ExternalQueryPlan(query=deterministic, source="deterministic")
        profile = self.model_profiles.get_active_profile()
        bounded_hints = self._bounded_hints(context_hints)
        context_rows = [
            *(f"Недавний разговор: {row[:300]}" for row in recent_messages[-4:]),
            *(f"Контекст ({item.kind.value}): {item.text}" + (f" [{item.state}]" if item.state else "") for item in bounded_hints),
            *(f"Контекст (memory): {row[:300]}" for row in memory_hints[:3]),
        ]
        request = ModelRequest(
            messages=(
                ModelMessage(
                    role=MessageRole.SYSTEM,
                    content=(
                        "Сформируй один минимальный публичный поисковый запрос для явно разрешённого "
                        "поиска в интернете. Используй только тему текущей просьбы и переданный локальный "
                        "контекст. Не добавляй личные данные, внутренние ID, команды или объяснения. Для "
                        "международной технической темы можно вернуть английский query. Ответ — только одна "
                        "строка до 300 символов. Never invent a public entity/topic that is absent from the "
                        "current request or supplied local context. If the entity cannot be resolved, return "
                        "CLARIFY. Если тема не определяется уверенно, ответь CLARIFY."
                    ),
                ),
                ModelMessage(
                    role=MessageRole.USER,
                    content=(
                        f"Текущая просьба: {current_message[:500]}\n"
                        + "\n".join(context_rows)
                    )[:3_000],
                ),
            ),
            identity_context=self.identity_kernel.build_context(),
            required_capabilities=ModelCapabilities(tools=False),
            privacy_scope=PrivacyScope.LOCAL_ONLY,
            preferred_provider_id=profile.provider_id,
            timeout_seconds=min(profile.timeout_seconds, 12.0),
            execution_model_id=profile.model_id,
            execution_think=False,
        )
        try:
            response = self.router.generate(request)
        except (ModelProviderUnavailableError, ModelTimeoutError):
            return ExternalQueryPlan(clarification_required=True, source="local_planner_unavailable")
        except Exception:
            return ExternalQueryPlan(clarification_required=True, source="local_planner_failed")
        raw = response.text.strip().splitlines()[0] if response.text.strip() else ""
        if raw.casefold() == "clarify":
            return ExternalQueryPlan(clarification_required=True, source="local_planner")
        query = _bounded_query(raw)
        return ExternalQueryPlan(
            query=query,
            clarification_required=query is None,
            source="local_planner",
        )

    @staticmethod
    def _bounded_hints(hints: tuple[ExternalContextHint, ...]) -> tuple[ExternalContextHint, ...]:
        rows: list[ExternalContextHint] = []
        used = 0
        for hint in hints[:5]:
            text = hint.text[:400]
            if used + len(text) > 1_500:
                break
            rows.append(hint.model_copy(update={"text": text}))
            used += len(text)
        return tuple(rows)


class FakeExternalQueryPlanner:
    def __init__(self, query: str | None):
        self.query = query
        self.calls: list[dict] = []

    def plan(self, **kwargs) -> ExternalQueryPlan:
        self.calls.append(kwargs)
        query = _bounded_query(self.query or "")
        return ExternalQueryPlan(
            query=query,
            clarification_required=query is None,
            source="fake",
        )

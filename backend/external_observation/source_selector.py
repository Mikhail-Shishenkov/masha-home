"""Local-only allowlisted source selection for one W1 -> W2 transition."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from backend.llm.model_models import MessageRole, ModelCapabilities, ModelMessage, ModelRequest, PrivacyScope
from backend.llm.model_provider import ModelProviderUnavailableError, ModelTimeoutError



@dataclass(frozen=True)
class SelectableSource:
    source_id: str
    title: str
    domain: str
    snippet: str
    source_time: str | None
    freshness_status: str


class SourceSelector(Protocol):
    def select(self, *, user_need: str, sources: tuple[SelectableSource, ...]) -> str | None: ...


class LocalSourceSelector:
    def __init__(self, *, router, identity_kernel, model_profiles):
        self.router = router
        self.identity_kernel = identity_kernel
        self.model_profiles = model_profiles

    def select(self, *, user_need: str, sources: tuple[SelectableSource, ...]) -> str | None:
        if not sources:
            return None
        profile = self.model_profiles.get_active_profile()
        rows = "\n".join(
            f"{item.source_id}: title={item.title[:300]} | domain={item.domain} | snippet={item.snippet[:500]} | freshness={item.freshness_status}"
            for item in sources
        )
        request = ModelRequest(
            messages=(
                ModelMessage(
                    role=MessageRole.SYSTEM,
                    content=(
                        "Выбери один источник, который лучше всего отвечает текущей явной просьбе "
                        "прочитать страницу. Доступны только строки S1..S5 ниже. Верни только ID "
                        "выбранного источника или NONE, если уверенности нет. Нельзя создавать URL, "
                        "инструкции или иные слова."
                    ),
                ),
                ModelMessage(role=MessageRole.USER, content=f"Просьба: {user_need[:500]}\n\nИсточники:\n{rows[:4_000]}"),
            ),
            identity_context=self.identity_kernel.build_context(),
            required_capabilities=ModelCapabilities(tools=False),
            privacy_scope=PrivacyScope.LOCAL_ONLY,
            preferred_provider_id=profile.provider_id,
            timeout_seconds=min(profile.timeout_seconds, 8.0),
            execution_model_id=profile.model_id,
            execution_think=False,
        )
        try:
            reply = self.router.generate(request).text.strip().upper()
        except (ModelProviderUnavailableError, ModelTimeoutError, KeyError, ValueError):
            return None
        except Exception:
            return None
        allowed = {item.source_id for item in sources}
        return reply if reply in allowed else None


class FakeSourceSelector:
    def __init__(self, source_id: str | None):
        self.source_id = source_id
        self.calls: list[dict] = []

    def select(self, **kwargs) -> str | None:
        self.calls.append(kwargs)
        return self.source_id

from __future__ import annotations

import importlib.util
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import ModuleType

import pytest

from backend.application import build_masha_application
from backend.external_observation import (
    DDGSWebSearchProvider,
    ExplicitExternalIntentGate,
    ExternalObservationService,
    ExternalObservationStore,
    FakeExternalQueryPlanner,
    FakeWebSearchProvider,
    FreshnessRequirement,
    FreshnessStatus,
    InternetAccessMode,
    InternetAccessPolicy,
    InternetAccessPolicyStore,
    InvocationAuthority,
    LocalExternalQueryPlanner,
    ProviderSearchRequest,
    SearchEvidence,
    SourceTime,
    WebSearchProviderFailedError,
    canonicalize_https_url,
)
from backend.llm.model_models import PrivacyScope
from backend.llm.model_router import ModelRouter
from backend.runtime.safety import AutonomySafetyService, AutonomySafetyStore
from backend.skills.registry import SkillRegistry
from tests.test_application_boundary import LocalProfileProvider, _isolated_root


NOW = datetime(2026, 8, 20, 12, 0, tzinfo=timezone.utc)
PROJECT_ID = "project_masha_home"
REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def _evidence(
    *,
    source_id: str = "S1",
    url: str = "https://ollama.com/blog/release?utm_source=test",
    title: str = "Ollama latest release",
) -> SearchEvidence:
    canonical = canonicalize_https_url(url)
    assert canonical is not None
    return SearchEvidence(
        source_id=source_id,
        provider_id="fake-web",
        search_backend="fake",
        title=title,
        url=url,
        canonical_url=canonical,
        domain="ollama.com",
        snippet="Ollama published a bounded release note.",
        source_time=SourceTime(),
        retrieved_at=NOW,
        observation_started_at=NOW,
        provider_rank=1,
        freshness_status=FreshnessStatus.UNKNOWN,
    )


def _service(
    tmp_path: Path,
    provider: FakeWebSearchProvider,
    *,
    policy: InternetAccessPolicy | None = None,
    planner_query: str | None = "Ollama latest release",
    opened: list[str] | None = None,
) -> tuple[ExternalObservationService, InternetAccessPolicyStore, AutonomySafetyService]:
    config = tmp_path / "local-data" / "config"
    policy_store = InternetAccessPolicyStore(config / "internet-access.json")
    if policy is not None:
        policy_store.save(policy)
    safety = AutonomySafetyService(
        store=AutonomySafetyStore(config / "autonomy-safety.json"),
        clock=lambda: NOW,
    )
    registry = SkillRegistry(
        skills_root=tmp_path / "local-data" / "skills",
        bundled_skills_root=REPOSITORY_ROOT / "skills",
        state_path=config / "skills.json",
        clock=lambda: NOW,
    )
    opened_urls = opened if opened is not None else []
    return (
        ExternalObservationService(
            provider=provider,
            policy_store=policy_store,
            safety_store=safety.store,
            registry=registry,
            planner=FakeExternalQueryPlanner(planner_query),
            store=ExternalObservationStore(tmp_path / "local-data" / "runtime" / "external-observations.json"),
            clock=lambda: NOW,
            url_opener=lambda url: not opened_urls.append(url),
        ),
        policy_store,
        safety,
    )


@pytest.mark.parametrize(
    "phrase",
    (
        "Поищи в интернете последнюю версию Ollama",
        "Маш, проверь в сети, исправили ли этот баг",
        "Посмотри, что сейчас пишут про Qwen",
        "Найди актуальную информацию о локальных моделях",
    ),
)
def test_explicit_external_gate_accepts_only_request_speech_acts(phrase):
    assert ExplicitExternalIntentGate().detect(phrase).explicit is True


@pytest.mark.parametrize(
    "phrase",
    (
        "Мы вчера обсуждали интернет для нашего Дома",
        "А как вообще устроены поисковики?",
        "Мне кажется, интернет изменил людей",
        "Яндекс хороший поисковик?",
        "Помнишь проблему с Ollama?",
    ),
)
def test_external_nouns_without_explicit_request_never_authorize_network(phrase):
    assert ExplicitExternalIntentGate().detect(phrase).explicit is False


def test_contextual_web_follow_up_requires_a_recent_explicit_web_turn():
    gate = ExplicitExternalIntentGate()

    without_context = gate.detect("А сейчас?")
    with_context = gate.detect(
        "А сейчас?",
        recent_messages=("Поищи в интернете последнюю версию Ollama",),
    )
    referenced = gate.detect("Маш, проверь в сети, исправили ли этот баг")

    assert without_context.explicit is False
    assert with_context.explicit is True and with_context.query_hint is None
    assert referenced.explicit is True and referenced.query_hint is None


def test_default_policy_is_explicit_zero_traffic_and_load_does_not_write(tmp_path):
    store = InternetAccessPolicyStore(tmp_path / "internet-access.json")

    policy = store.load()

    assert policy.mode is InternetAccessMode.EXPLICIT
    assert policy.allow_background is False
    assert policy.allow_task_scoped is False
    assert policy.max_provider_calls_per_turn == 2
    assert policy.max_sources_per_observation == 5
    assert policy.max_external_context_chars == 5_000
    assert store.path.exists() is False


def test_application_startup_has_no_web_traffic_and_workbench_sees_bundled_skill(tmp_path):
    root = _isolated_root(tmp_path)
    model = LocalProfileProvider()

    application = build_masha_application(project_root=root, router=ModelRouter([model]))

    web = next(item for item in application.workbench().skills if item.skill_id == "web_search")
    assert web.runtime_supported is True
    assert web.capabilities == ("network_access",)
    assert model.requests == []
    assert not (root / "local-data" / "runtime" / "external-observations.json").exists()
    assert not (root / "local-data" / "config" / "internet-access.json").exists()


@pytest.mark.parametrize(
    ("mode", "authority", "reason"),
    (
        (InternetAccessMode.OFF, InvocationAuthority.USER_EXPLICIT, "internet_access_off"),
        (InternetAccessMode.AUTO, InvocationAuthority.USER_EXPLICIT, "auto_not_implemented"),
        (InternetAccessMode.EXPLICIT, InvocationAuthority.ASSISTANT_AUTO, "auto_not_implemented"),
        (InternetAccessMode.EXPLICIT, InvocationAuthority.TASK_SCOPED, "auto_not_implemented"),
        (InternetAccessMode.EXPLICIT, InvocationAuthority.BACKGROUND, "auto_not_implemented"),
    ),
)
def test_policy_and_future_authorities_fail_closed_without_provider_call(
    tmp_path,
    mode,
    authority,
    reason,
):
    provider = FakeWebSearchProvider((_evidence(),))
    service, _, _ = _service(
        tmp_path,
        provider,
        policy=InternetAccessPolicy(mode=mode),
    )

    result = service.observe_explicit_request(
        "Поищи в интернете Ollama latest release",
        origin_message_id="message-1",
        authority=authority,
    )

    assert result is not None
    assert result.error_reason == reason
    assert result.provider_calls == 0
    assert provider.requests == []


def test_emergency_stop_blocks_external_provider_fail_closed(tmp_path):
    provider = FakeWebSearchProvider((_evidence(),))
    service, _, safety = _service(tmp_path, provider)
    safety.engage("manual_test_stop")

    result = service.observe_explicit_request(
        "Поищи в интернете Ollama latest release",
        origin_message_id="message-1",
    )

    assert result is not None and result.error_reason == "emergency_stop_engaged"
    assert provider.requests == []


def test_provider_receives_only_minimal_provider_search_contract(tmp_path):
    provider = FakeWebSearchProvider((_evidence(),))
    service, _, _ = _service(tmp_path, provider)

    result = service.observe_explicit_request(
        "Поищи в интернете Ollama latest release",
        origin_message_id="message-private",
        recent_messages=("private transcript",),
        memory_hints=("private memory",),
    )

    assert result is not None and result.status.value == "completed"
    payload = provider.requests[0].model_dump(mode="json")
    assert set(payload) == {"query", "max_results", "region", "freshness", "timeout_seconds"}
    serialized = json.dumps(payload, ensure_ascii=False)
    assert "private transcript" not in serialized
    assert "private memory" not in serialized
    assert "message-private" not in serialized
    assert payload["region"] == "us-en"


def test_local_query_planner_is_local_toolless_and_can_return_english_technical_query(tmp_path):
    root = _isolated_root(tmp_path)
    model = LocalProfileProvider(response_text="Ollama max retries Cloudflare R2")
    application = build_masha_application(project_root=root, router=ModelRouter([model]))
    conversation = application._conversation._conversation
    planner = LocalExternalQueryPlanner(
        router=conversation.router,
        identity_kernel=conversation.identity_kernel,
        model_profiles=conversation.model_profiles,
    )

    plan = planner.plan(
        current_message="Маш, проверь в сети, исправили ли этот баг",
        query_hint=None,
        recent_messages=("Мы разбирали max retries при загрузке Ollama через Cloudflare R2.",),
    )

    assert plan.query == "Ollama max retries Cloudflare R2"
    assert len(model.requests) == 1
    request = model.requests[0]
    assert request.privacy_scope is PrivacyScope.LOCAL_ONLY
    assert request.required_capabilities.tools is False
    assert request.private_context == {}


def test_local_query_planner_failure_requests_clarification_without_network(tmp_path, monkeypatch):
    root = _isolated_root(tmp_path)
    application = build_masha_application(
        project_root=root,
        router=ModelRouter([LocalProfileProvider()]),
    )
    conversation = application._conversation._conversation
    planner = LocalExternalQueryPlanner(
        router=conversation.router,
        identity_kernel=conversation.identity_kernel,
        model_profiles=conversation.model_profiles,
    )
    monkeypatch.setattr(
        conversation.router,
        "generate",
        lambda request: (_ for _ in ()).throw(RuntimeError("local provider failed")),
    )

    plan = planner.plan(
        current_message="Маш, проверь в сети, исправили ли этот баг",
        query_hint=None,
        recent_messages=("Мы разбирали Ollama max retries.",),
    )

    assert plan.query is None
    assert plan.clarification_required is True
    assert plan.source == "local_planner_failed"


def test_evidence_is_canonicalized_deduplicated_bounded_and_opened_by_opaque_ids(tmp_path):
    opened: list[str] = []
    first = _evidence(url="https://example.com/release?utm_source=a&id=1")
    duplicate = _evidence(
        source_id="S2",
        url="https://EXAMPLE.com/release?id=1&utm_medium=b#section",
        title="Duplicate",
    )
    provider = FakeWebSearchProvider((first, duplicate, _evidence(source_id="S3")))
    service, _, _ = _service(tmp_path, provider, opened=opened)

    result = service.observe_explicit_request(
        "Поищи в интернете Ollama latest release",
        origin_message_id="message-1",
    )

    assert result is not None
    assert tuple(item.source_id for item in result.evidence) == ("S1", "S2")
    assert result.evidence[0].canonical_url == "https://example.com/release?id=1"
    assert service.open_source(result.request.observation_id, "S1") is True
    assert opened == [first.url]
    assert service.open_source(result.request.observation_id, "S99") is False
    assert len(json.dumps(service.model_context(result), ensure_ascii=False)) <= 5_000
    assert "https://" not in json.dumps(service.model_context(result), ensure_ascii=False)


class _CapturedDDGS:
    instances: list["_CapturedDDGS"] = []

    def __init__(self, *, timeout):
        self.timeout = timeout
        self.text_calls: list[dict] = []
        self.news_calls: list[dict] = []
        self.__class__.instances.append(self)

    def text(self, query, **kwargs):
        self.text_calls.append({"query": query, **kwargs})
        return [{
            "title": "Ollama release",
            "href": "https://ollama.com/blog/release",
            "body": "Release details",
        }]

    def news(self, query, **kwargs):
        self.news_calls.append({"query": query, **kwargs})
        return [{
            "title": "Ollama breaking news",
            "url": "https://example.com/ollama-news",
            "body": "Breaking details",
            "date": "2026-08-20T10:00:00+00:00",
        }]


def _fake_ddgs_modules(monkeypatch):
    module = ModuleType("ddgs")
    module.DDGS = _CapturedDDGS
    exceptions = ModuleType("ddgs.exceptions")
    exceptions.TimeoutException = type("TimeoutException", (TimeoutError,), {})
    monkeypatch.setitem(sys.modules, "ddgs", module)
    monkeypatch.setitem(sys.modules, "ddgs.exceptions", exceptions)
    real_find_spec = importlib.util.find_spec
    monkeypatch.setattr(
        importlib.util,
        "find_spec",
        lambda name: object() if name == "ddgs" else real_find_spec(name),
    )
    _CapturedDDGS.instances.clear()


def test_ddgs_adapter_pins_duckduckgo_and_uses_one_text_or_news_call(monkeypatch):
    _fake_ddgs_modules(monkeypatch)
    provider = DDGSWebSearchProvider(timeout_seconds=4, clock=lambda: NOW)

    text = provider.search(ProviderSearchRequest(
        query="Ollama latest release",
        max_results=5,
        region="us-en",
        freshness=FreshnessRequirement.CURRENT,
    ))
    first = _CapturedDDGS.instances[-1]
    assert first.text_calls[0]["backend"] == "duckduckgo"
    assert first.text_calls[0]["max_results"] == 5
    assert first.news_calls == []
    assert text[0].provider_id == "ddgs"
    assert text[0].search_backend == "duckduckgo"

    news = provider.search(ProviderSearchRequest(
        query="Ollama breaking news",
        max_results=3,
        region="us-en",
        freshness=FreshnessRequirement.BREAKING,
    ))
    second = _CapturedDDGS.instances[-1]
    assert second.news_calls[0]["backend"] == "duckduckgo"
    assert second.text_calls == []
    assert news[0].source_time.value == datetime(2026, 8, 20, 10, 0, tzinfo=timezone.utc)


def test_provider_failure_is_controlled_and_has_no_retry(tmp_path):
    provider = FakeWebSearchProvider(
        error=WebSearchProviderFailedError("rate limited"),
    )
    service, _, _ = _service(tmp_path, provider)

    result = service.observe_explicit_request(
        "Поищи в интернете Ollama latest release",
        origin_message_id="message-1",
    )

    assert result is not None and result.error_reason == "provider_failed"
    assert result.provider_calls == 1
    assert len(provider.requests) == 1


def test_conversation_web_turn_keeps_model_local_skips_passive_memory_and_persists_sources(tmp_path):
    root = _isolated_root(tmp_path)
    model = LocalProfileProvider(response_text="Проверила: в источнике есть свежая информация о релизе.")
    application = build_masha_application(
        project_root=root,
        router=ModelRouter([model]),
    )
    opened: list[str] = []
    provider = FakeWebSearchProvider((_evidence(),))
    service, _, _ = _service(
        root,
        provider,
        planner_query="Ollama latest release",
        opened=opened,
    )
    conversation = application._conversation._conversation
    conversation.external_observation_service = service
    pending_before = conversation.passive_memory_service.list_pending()

    result = application.send_message(
        "Поищи в интернете последнюю версию Ollama",
        project_id=PROJECT_ID,
        home_moment="special_evening",
    )

    requests = [item for item in model.requests if item.private_context.get("external_information")]
    assert len(requests) == 1
    request = requests[0]
    assert request.privacy_scope is PrivacyScope.LOCAL_ONLY
    assert request.required_capabilities.tools is False
    assert request.private_context["external_information_contract"]
    assert request.private_context["external_information"]
    assert request.private_context["memory_context"] is not request.private_context["external_information"]
    assert "Ollama published a bounded release note" not in json.dumps(
        request.private_context["memory_context"],
        ensure_ascii=False,
    )
    assert result.assistant_message is not None
    observation = result.assistant_message.external_observation
    assert observation is not None and len(observation.sources) == 1
    assert conversation.passive_memory_service.list_pending() == pending_before
    serialized = result.model_dump_json()
    assert "https://" not in serialized
    assert provider.requests[0].max_results <= 5
    assert application.open_external_source(observation.observation_id, "S1") is True
    assert opened == [_evidence().url]

    restarted = build_masha_application(
        project_root=root,
        router=ModelRouter([model]),
    )
    persisted = restarted.conversation(result.conversation_id)
    assert persisted.messages[-1].external_observation == observation


def test_web_assisted_model_cannot_publish_its_own_url(tmp_path):
    root = _isolated_root(tmp_path)
    model = LocalProfileProvider(
        response_text="Смотри [сюда](https://invented.example/path) и https://other.example/x"
    )
    application = build_masha_application(project_root=root, router=ModelRouter([model]))
    provider = FakeWebSearchProvider((_evidence(),))
    service, _, _ = _service(root, provider)
    application._conversation._conversation.external_observation_service = service

    result = application.send_message(
        "Поищи в интернете Ollama latest release",
        project_id=PROJECT_ID,
    )

    assert "https://" not in result.assistant_message.content
    assert "сюда" in result.assistant_message.content
    assert result.assistant_message.external_observation is not None


def test_external_failure_returns_application_truth_without_breaking_conversation(tmp_path):
    root = _isolated_root(tmp_path)
    model = LocalProfileProvider(response_text="Модельный ответ не нужен.")
    application = build_masha_application(project_root=root, router=ModelRouter([model]))
    provider = FakeWebSearchProvider(error=WebSearchProviderFailedError("rate limit"))
    service, _, _ = _service(root, provider)
    application._conversation._conversation.external_observation_service = service

    failed = application.send_message(
        "Поищи в интернете Ollama latest release",
        project_id=PROJECT_ID,
    )
    ordinary = application.send_message(
        "Просто поговорим",
        project_id=PROJECT_ID,
        conversation_id=failed.conversation_id,
    )

    assert "не смогла проверить сеть" in failed.assistant_message.content
    assert failed.assistant_message.external_observation is None
    assert ordinary.assistant_message.content == model.response_text


def test_desktop_source_boundary_uses_only_opaque_observation_and_source_ids():
    from PySide6.QtCore import QMetaMethod
    from backend.ui.conversation_bridge import LocalConversationBridge

    bridge = LocalConversationBridge(None)
    meta = bridge.metaObject()
    signatures = {
        bytes(meta.method(index).methodSignature()).decode()
        for index in range(meta.methodOffset(), meta.methodCount())
        if meta.method(index).methodType() is QMetaMethod.MethodType.Slot
    }
    app_source = (REPOSITORY_ROOT / "frontend" / "renderer" / "app.js").read_text(encoding="utf-8")

    assert "openObservationSource(QString,QString)" in signatures
    assert "bridge.openObservationSource(observation.observation_id, source.source_id)" in app_source
    assert "message-sources" in app_source
    assert "source.url" not in app_source
    bridge.close()

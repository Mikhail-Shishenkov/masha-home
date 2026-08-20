from __future__ import annotations

import json
from datetime import datetime, timezone
from types import SimpleNamespace
from pathlib import Path

import pytest

from backend.application.external_context import LocalExternalContextHintProvider
from backend.application.human_information import HumanAvailability
from backend.external_observation import (
    ExternalContextHint,
    ExternalContextHintKind,
    ExternalContextResolution,
    ExternalObservationService,
    ExternalObservationStore,
    FakeExternalQueryPlanner,
    FakeWebSearchProvider,
    FreshnessStatus,
    InternetAccessPolicyStore,
    ObservationStatus,
    SafeFetchResponse,
    SearchEvidence,
    SourceTime,
    canonicalize_https_url,
)
from backend.external_observation.context import requires_local_context_resolution
from backend.external_observation.intent import ExplicitExternalIntentGate
from backend.external_observation.planner import LocalExternalQueryPlanner
from backend.llm.model_router import ModelRouter
from backend.runtime.safety import AutonomySafetyService, AutonomySafetyStore
from backend.skills.registry import SkillRegistry
from tests.test_application_boundary import LocalProfileProvider, _isolated_root


NOW = datetime(2026, 8, 20, 12, 0, tzinfo=timezone.utc)
ROOT = Path(__file__).resolve().parents[1]


class _Hints:
    def __init__(self, resolution=ExternalContextResolution()):
        self.resolution = resolution
        self.calls = []

    def resolve(self, **kwargs):
        self.calls.append(kwargs)
        return self.resolution


class _Fetcher:
    def __init__(self):
        self.calls = []

    def fetch(self, url):
        self.calls.append(url)
        return SafeFetchResponse(
            requested_url=url,
            final_url=url,
            headers={"content-type": "text/plain"},
            body=b"A readable public page with enough bounded text for this W3 fixture.",
            redirects=0,
        )


def _evidence() -> SearchEvidence:
    url = "https://ollama.com/blog/releases"
    return SearchEvidence(
        source_id="S1", provider_id="fake", search_backend="fake",
        title="Ollama releases", url=url, canonical_url=canonicalize_https_url(url),
        domain="ollama.com", snippet="Public release details.", source_time=SourceTime(),
        retrieved_at=NOW, observation_started_at=NOW, provider_rank=1,
        freshness_status=FreshnessStatus.UNKNOWN,
    )


def _service(tmp_path, *, hints=None, planner_query="Ollama latest release", fetcher=None):
    config = tmp_path / "local-data" / "config"
    safety = AutonomySafetyService(
        store=AutonomySafetyStore(config / "autonomy-safety.json"),
        clock=lambda: NOW,
    )
    provider = FakeWebSearchProvider((_evidence(),))
    return ExternalObservationService(
        provider=provider,
        policy_store=InternetAccessPolicyStore(config / "internet-access.json"),
        safety_store=safety.store,
        registry=SkillRegistry(
            skills_root=tmp_path / "local-data" / "skills",
            bundled_skills_root=ROOT / "skills",
            state_path=config / "skills.json",
            clock=lambda: NOW,
        ),
        planner=FakeExternalQueryPlanner(planner_query),
        store=ExternalObservationStore(tmp_path / "local-data" / "runtime" / "external-observations.json"),
        context_hint_provider=hints,
        fetcher=fetcher,
        clock=lambda: NOW,
    ), provider


def test_self_contained_explicit_query_skips_w3_context_and_provider_receives_only_query(tmp_path):
    hints = _Hints()
    service, provider = _service(tmp_path, hints=hints, planner_query="Python")

    result = service.observe_explicit_request(
        "Найди последнюю версию Python",
        origin_message_id="message-1",
        project_id="private-project",
    )

    assert result is not None and result.status is ObservationStatus.COMPLETED
    assert hints.calls == []
    assert provider.requests[0].query == "Python"
    assert set(provider.requests[0].model_dump()) == {"query", "max_results", "region", "freshness", "timeout_seconds"}


def test_referential_search_passes_only_minimal_final_query_and_never_persists_hints(tmp_path):
    secret = "Мы обсуждали дома личную причину, не отправляй её наружу"
    hints = _Hints(ExternalContextResolution(hints=(ExternalContextHint(
        kind=ExternalContextHintKind.DECISION,
        text=f"Решение: пользоваться Ollama. {secret}",
        state="current",
    ),)))
    service, provider = _service(tmp_path, hints=hints)

    result = service.observe_explicit_request(
        "Проверь в интернете, обновилась ли та модель",
        origin_message_id="message-1",
        recent_messages=("Недавний разговор про Ollama",),
        project_id="private-project",
    )

    assert result is not None and result.request.query == "Ollama latest release"
    assert len(hints.calls) == len(provider.requests) == 1
    assert secret not in json.dumps(provider.requests[0].model_dump(), ensure_ascii=False)
    journal = service.store.path.read_text(encoding="utf-8")
    assert secret not in journal
    assert "Ollama latest release" in journal


def test_ambiguous_context_fails_closed_without_network(tmp_path):
    hints = _Hints(ExternalContextResolution(clarification_required=True))
    service, provider = _service(tmp_path, hints=hints)

    result = service.observe_explicit_request(
        "Проверь в интернете, обновилась ли та модель",
        origin_message_id="message-1",
    )

    assert result is not None and result.status is ObservationStatus.CLARIFICATION_REQUIRED
    assert result.error_reason == "context_clarification_required"
    assert provider.requests == []


def test_search_then_fetch_uses_context_once_and_keeps_one_search_one_fetch(tmp_path):
    hints = _Hints(ExternalContextResolution(hints=(ExternalContextHint(
        kind=ExternalContextHintKind.ACTIVE_THREAD, text="Тема: Ollama release", state="current",
    ),)))
    fetcher = _Fetcher()
    service, provider = _service(tmp_path, hints=hints, fetcher=fetcher)
    service.source_selector = SimpleNamespace(select=lambda **kwargs: "S1")

    result = service.observe_fetch_request(
        "Найди ту модель и прочитай страницу",
        origin_message_id="message-1",
        conversation_message_ids=("message-1",),
        project_id="private-project",
    )

    assert result is not None and [item.request.kind.value for item in result] == ["web_search", "web_fetch"]
    assert len(hints.calls) == len(provider.requests) == len(fetcher.calls) == 1


def test_direct_fetch_source_reference_and_ordinary_conversation_bypass_w3_resolution(tmp_path):
    hints = _Hints()
    fetcher = _Fetcher()
    service, provider = _service(tmp_path, hints=hints, fetcher=fetcher)

    direct = service.observe_fetch_request(
        "прочитай https://public.example/page",
        origin_message_id="message-1",
        conversation_message_ids=("message-1",),
    )
    ordinary = service.observe_explicit_request("давай поговорим о сайтах", origin_message_id="message-2")
    search = service.observe_explicit_request("Поищи в интернете Ollama", origin_message_id="message-3")
    source = service.observe_fetch_request(
        "прочитай S1",
        origin_message_id="message-4",
        conversation_message_ids=("message-3", "message-4"),
    )

    assert direct is not None and source is not None and search is not None
    assert ordinary is None
    assert hints.calls == []
    assert len(provider.requests) == 1 and len(fetcher.calls) == 2


@pytest.mark.parametrize("kind", tuple(ExternalContextHintKind))
def test_typed_hint_contract_has_no_storage_id_and_enforces_single_hint_budget(kind):
    hint = ExternalContextHint(kind=kind, text="Human-readable local context", state="current")
    assert "id" not in hint.model_dump()
    with pytest.raises(ValueError):
        ExternalContextHint(kind=kind, text="x" * 401)


def test_hint_resolution_budget_rejects_more_than_five_or_over_1500_chars():
    hint = ExternalContextHint(kind=ExternalContextHintKind.MEMORY, text="x" * 400)
    with pytest.raises(ValueError):
        ExternalContextResolution(hints=(hint, hint, hint, hint, hint))
    with pytest.raises(ValueError):
        ExternalContextResolution(hints=(hint, hint, hint, hint, hint, hint))


def test_local_planner_labels_hints_and_stays_local_toolless_without_internal_ids(tmp_path):
    root = _isolated_root(tmp_path)
    model = LocalProfileProvider(response_text="Ollama latest release")
    application = __import__("backend.application", fromlist=["build_masha_application"]).build_masha_application(
        project_root=root,
        router=ModelRouter([model]),
    )
    conversation = application._conversation._conversation
    planner = LocalExternalQueryPlanner(
        router=conversation.router,
        identity_kernel=conversation.identity_kernel,
        model_profiles=conversation.model_profiles,
    )
    plan = planner.plan(
        current_message="Проверь в интернете, обновилась ли та модель",
        query_hint="обновилась ли та модель",
        recent_messages=("Мы ставили Ollama.",),
        context_hints=(ExternalContextHint(
            kind=ExternalContextHintKind.DECISION,
            text="Решение: использовать Ollama для локальных моделей",
            state="current",
        ),),
    )

    request = model.requests[-1]
    serialized = "\n".join(item.content for item in request.messages)
    assert plan.query == "Ollama latest release"
    assert "Контекст (decision)" in serialized
    assert "internal_id" not in serialized
    assert request.privacy_scope.value == "local_only"
    assert request.required_capabilities.tools is False
    assert len(serialized) <= 3_000


class _Human:
    def __init__(self, *, rows=(), active=()):
        self.rows = rows
        self.active = active
        self.calls = 0
        self.proposal_store = SimpleNamespace(read=lambda: (_ for _ in ()).throw(AssertionError("pending candidates must not be read")))

    def recall_information(self, request):
        self.calls += 1
        return SimpleNamespace(working_context=self.rows)

    def information_items(self):
        return self.active


class _Reflections:
    def __init__(self, rows=()):
        self.rows = rows
        self.calls = 0

    def reflections(self):
        self.calls += 1
        return self.rows


def test_recent_named_public_topic_beats_unrelated_long_term_recall():
    human = _Human(rows=(
        {"category": "факт", "content": "Qwen release", "state": "current"},
        {"category": "решение", "content": "Devstral coding", "state": "current"},
    ))
    resolver = LocalExternalContextHintProvider(human_information=human, reflections=_Reflections())

    result = resolver.resolve(
        current_message="Проверь в интернете, обновилась ли она",
        project_id=None,
        recent_messages=("Мы вчера ставили Ollama и обсуждали его релиз.",),
        active_continuity_thread_id=None,
    )

    assert result.clarification_required is False
    assert result.hints == ()
    assert human.calls == 0


def test_forgotten_and_pending_never_participate_and_reflection_requires_explicit_reference():
    human = _Human(rows=({"category": "факт", "content": "Ollama private note", "state": "current"},))
    reflections = _Reflections((SimpleNamespace(reflection=SimpleNamespace(
        text="OpenHands deserves a look", meaning="OpenHands topic", project_ids=[]
    )),))
    resolver = LocalExternalContextHintProvider(human_information=human, reflections=reflections)

    forgotten = resolver.resolve(
        current_message="Поищи в интернете то, что я просил забыть",
        project_id=None, recent_messages=(), active_continuity_thread_id=None,
    )
    ordinary = resolver.resolve(
        current_message="Проверь в интернете ту тему",
        project_id=None, recent_messages=(), active_continuity_thread_id=None,
    )
    explicit_reflection = resolver.resolve(
        current_message="В своих мыслях ты писала про OpenHands, найди новости",
        project_id=None, recent_messages=(), active_continuity_thread_id=None,
    )

    assert forgotten.hints == () and human.calls == 2
    assert all(item.kind is not ExternalContextHintKind.MASHA_REFLECTION for item in ordinary.hints)
    assert [item.kind for item in explicit_reflection.hints][-1] is ExternalContextHintKind.MASHA_REFLECTION
    assert len([item for item in explicit_reflection.hints if item.kind is ExternalContextHintKind.MASHA_REFLECTION]) == 1


def test_active_thread_is_a_single_strong_hint_and_conflicting_recall_is_not_guessed():
    active_item = SimpleNamespace(
        ref=SimpleNamespace(entity_id="thread-private"),
        record_type="continuity_follow_up",
        availability=HumanAvailability.ACTIVE,
        label="Тема · открыто: Qwen release",
    )
    human = _Human(
        active=(active_item,),
        rows=(
            {"category": "факт", "content": "Qwen release", "state": "current"},
            {"category": "решение", "content": "Devstral coding", "state": "current"},
        ),
    )
    resolver = LocalExternalContextHintProvider(human_information=human, reflections=_Reflections())

    active = resolver.resolve(
        current_message="Проверь в интернете, что нового у той модели",
        project_id=None, recent_messages=(), active_continuity_thread_id="thread-private",
    )
    ambiguous = resolver.resolve(
        current_message="Проверь в интернете, обновилась ли та модель",
        project_id=None, recent_messages=(), active_continuity_thread_id=None,
    )

    assert active.clarification_required is False
    assert active.hints[0].kind is ExternalContextHintKind.ACTIVE_THREAD
    assert ambiguous.clarification_required is True


@pytest.mark.parametrize("query, expected", [
    ("последнюю версию Python", False),
    ("новости Ollama", False),
    ("обновилась ли та модель", True),
    ("", True),
])
def test_contextual_reference_gate_is_conservative(query, expected):
    assert requires_local_context_resolution(query) is expected


@pytest.mark.parametrize("phrase", [
    "Найди, что нового у того проекта, про который мы говорили",
    "Посмотри новости по той теме, которую я взял с собой",
    "Ты писала в своих мыслях про OpenHands — найди, что у него нового",
])
def test_contextual_freshness_requests_are_explicit_external_intent(phrase):
    assert ExplicitExternalIntentGate().detect(phrase).explicit is True


@pytest.mark.parametrize("category, kind", [
    ("факт", ExternalContextHintKind.MEMORY),
    ("решение", ExternalContextHintKind.DECISION),
    ("эпизод", ExternalContextHintKind.EPISODE),
    ("общий момент", ExternalContextHintKind.SHARED_MOMENT),
    ("дело", ExternalContextHintKind.TASK),
    ("тема", ExternalContextHintKind.THREAD),
])
def test_current_human_information_categories_map_to_bounded_hint_kinds(category, kind):
    human = _Human(rows=({"category": category, "content": "Public product topic", "state": "current"},))
    resolver = LocalExternalContextHintProvider(human_information=human, reflections=_Reflections())

    result = resolver.resolve(
        current_message="Проверь в интернете ту тему",
        project_id=None, recent_messages=(), active_continuity_thread_id=None,
    )

    assert result.clarification_required is False
    assert result.hints[0].kind is kind

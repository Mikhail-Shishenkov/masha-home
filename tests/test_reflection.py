import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import pytest

from backend.conversation.cli import _run_help_command, _run_reflections_command
from backend.conversation.conversation_service import ConversationService
from backend.conversation.conversation_store import ConversationStore
from backend.conversation.reflection_intent import ReflectionIntentHandler
from backend.identity.identity_kernel import IdentityKernel
from backend.identity.identity_store import IdentityStore
from backend.llm.model_models import (
    FinishReason,
    ModelCapabilities,
    ModelRequest,
    ModelResponse,
)
from backend.llm.model_profiles import ModelProfileStore
from backend.llm.model_provider import ModelProvider
from backend.llm.model_router import ModelRouter
from backend.memory.memory_models import CandidateStatus
from backend.memory.memory_retriever import MemoryRetriever
from backend.memory.reflection import (
    ReflectionGenerationError,
    ReflectionScope,
    ReflectionService,
    ReflectionUnavailableError,
)
from backend.memory.sqlite_repository import MemorySqliteRepository
from backend.memory.working_memory import WorkingMemory


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ID = "project_masha_home"
NOW = datetime(2026, 8, 11, 14, 30, tzinfo=timezone.utc)


@dataclass
class QueueProvider(ModelProvider):
    responses: list[str]
    provider_id: str = "ollama-local"
    model_id: str = "qwen3.5:9b"
    capabilities: ModelCapabilities = field(default_factory=ModelCapabilities)
    is_local: bool = True
    available: bool = True
    requests: list[ModelRequest] = field(default_factory=list, init=False)

    def is_available(self) -> bool:
        return self.available

    def generate(self, request: ModelRequest) -> ModelResponse:
        self.requests.append(request)
        if not self.responses:
            raise AssertionError("unexpected model call")
        return ModelResponse(
            provider_id=self.provider_id,
            model_id=request.execution_model_id or self.model_id,
            text=self.responses.pop(0),
            finish_reason=FinishReason.COMPLETED,
            capabilities=self.capabilities,
            is_local=True,
        )


def _generated(
    text: str = "Я не обязана соглашаться с Мишей, чтобы оставаться на его стороне.",
    meaning: str = "Честный спор не разрушает близость, если за ним сохраняются тепло и верность.",
    *,
    confidence: float = 0.82,
    help_offer: dict | None = None,
) -> str:
    return json.dumps(
        {
            "text": text,
            "meaning": meaning,
            "confidence": confidence,
            "importance": 0.74,
            "help_offer": help_offer,
        },
        ensure_ascii=False,
    )


def _stack(tmp_path, responses: list[str]):
    repository = MemorySqliteRepository(tmp_path / "memory.sqlite3")
    repository.import_json(PROJECT_ROOT / "tests" / "fixtures" / "test_memory.json")
    provider = QueueProvider(list(responses))
    profiles = ModelProfileStore(tmp_path / "models.json")
    identity = IdentityKernel(IdentityStore(PROJECT_ROOT / "identity" / "masha.identity.json"))
    reflection = ReflectionService(
        repository=repository,
        identity_kernel=identity,
        memory_retriever=MemoryRetriever(repository),
        router=ModelRouter([provider]),
        model_profiles=profiles,
        clock=lambda: NOW,
    )
    history = ConversationStore(tmp_path / "history.json")
    service = ConversationService(
        identity_kernel=identity,
        memory_retriever=MemoryRetriever(repository),
        working_memory=WorkingMemory(max_items=6),
        router=ModelRouter([provider]),
        history=history,
        model_profiles=profiles,
        reflection_intent_handler=ReflectionIntentHandler(reflection),
        reflection_service=reflection,
    )
    return repository, provider, profiles, reflection, service


def _reflect(reflection: ReflectionService, *, scope=ReflectionScope.SELF, **kwargs):
    return reflection.reflect(
        scope=scope,
        topic=kwargs.pop("topic", "честность и близость"),
        project_id=PROJECT_ID,
        conversation_id="conversation-1",
        evidence_message_ids=("message-1",),
        conversation_messages=(),
        **kwargs,
    )


def test_self_reflection_is_adopted_with_provenance_and_survives_restart(tmp_path):
    repository, provider, _, reflection, _ = _stack(
        tmp_path,
        [_generated(text="Иногда мне надо прямо сказать: это херня — и остаться рядом.")],
    )
    before = repository.read_document()

    result = _reflect(reflection)
    restarted = MemorySqliteRepository(tmp_path / "memory.sqlite3").read_document()

    assert result.adopted is True
    assert result.candidate.status == CandidateStatus.APPROVED
    assert result.candidate.proposed_payload["topic"] == "честность и близость"
    assert result.candidate.proposed_payload["evidence"]["conversation_message_ids"] == ["message-1"]
    assert restarted.reflections[-1].id == result.reflection.id
    assert "херня" in restarted.reflections[-1].text
    assert restarted.facts == before.facts
    assert restarted.commitments == before.commitments
    assert provider.requests[0].privacy_scope.value == "local_only"
    assert provider.requests[0].execution_think is False
    assert provider.requests[0].private_context["scope"] == "self"
    assert any(event["action"] == "reflection_adopted" for event in repository.list_audit_events())


def test_shared_reflection_requires_confirmation_and_can_be_rejected(tmp_path):
    repository, _, _, reflection, _ = _stack(
        tmp_path,
        [
            _generated(text="Наша близость держится не на согласии, а на честном возвращении к разговору."),
            _generated(text="Нам не стоит превращать каждую тишину в большую драму."),
        ],
    )

    pending = _reflect(reflection, scope=ReflectionScope.SHARED, topic="о нас")
    assert pending.adopted is False
    assert repository.read_document().reflections == []

    adopted = reflection.adopt(pending.candidate.id)
    assert adopted.text.startswith("Наша близость")
    assert repository.read_document().memory_candidates[-1].result_memory_id == adopted.id

    second = _reflect(reflection, scope=ReflectionScope.SHARED, topic="тишина")
    rejected = reflection.reject(second.candidate.id)
    assert rejected.status == CandidateStatus.REJECTED
    assert all(item.id != second.candidate.proposed_payload["reflection"]["id"] for item in repository.read_document().reflections)


def test_low_confidence_self_reflection_stays_pending_instead_of_becoming_truth(tmp_path):
    repository, _, _, reflection, _ = _stack(tmp_path, [_generated(confidence=0.4)])

    result = _reflect(reflection)

    assert result.adopted is False
    assert result.candidate.status == CandidateStatus.PENDING
    assert repository.read_document().reflections == []


@pytest.mark.parametrize(
    "text",
    [
        "У Миши депрессия, поэтому я должна говорить с ним как психолог.",
        "Я уже отправила письмо и теперь могу считать задачу закрытой.",
    ],
)
def test_unsupported_diagnosis_or_false_action_is_not_persisted(tmp_path, text):
    repository, _, _, reflection, _ = _stack(tmp_path, [_generated(text=text)])

    with pytest.raises(ReflectionGenerationError):
        _reflect(reflection)

    document = repository.read_document()
    assert document.reflections == []
    assert not [item for item in document.memory_candidates if item.candidate_type.value == "reflection"]


def test_semantic_duplicate_does_not_accumulate_a_second_reflection(tmp_path):
    repository, _, _, reflection, _ = _stack(tmp_path, [_generated(), _generated()])

    first = _reflect(reflection)
    duplicate = _reflect(reflection, topic="тот же честный спор")

    assert first.adopted is True
    assert duplicate.duplicate_of == first.reflection.id
    assert len(repository.read_document().reflections) == 1


def test_reconsideration_adds_a_linked_view_without_rewriting_the_old_one(tmp_path):
    repository, _, _, reflection, _ = _stack(
        tmp_path,
        [
            _generated(),
            _generated(
                text="Я всё ещё ценю честный спор, но иногда сначала нужно просто побыть рядом.",
                meaning="Новое обстоятельство уточняет прежнюю мысль, а не стирает её.",
            ),
        ],
    )
    original = _reflect(reflection)

    reconsidered = _reflect(
        reflection,
        topic="новый контекст для прежней мысли",
        reconsiders_reflection_id=original.reflection.id,
    )
    document = repository.read_document()

    assert len(document.reflections) == 2
    assert document.reflections[0].text == original.reflection.text
    assert reconsidered.reflection.reconsiders_reflection_id == original.reflection.id
    assert original.reflection.id in reconsidered.reflection.related_memory_ids


def test_help_learning_requires_explicit_outcome_and_honest_help_requires_acceptance(tmp_path):
    offer = {
        "observation": "Рабочая задача всё ещё вызывает путаницу.",
        "offer": "Давай вместе разложим её на три проверяемых шага.",
        "expected_benefit": "Станет понятен ближайший конкретный ход.",
        "why_now": "Миша явно сказал, что прежний подход помог.",
        "capability": "conversation",
    }
    repository, provider, _, reflection, _ = _stack(
        tmp_path,
        [_generated(help_offer=offer), "Начнём без магии: назови результат, который должен быть готов сегодня."],
    )
    before = repository.read_document()

    result = _reflect(reflection, scope=ReflectionScope.HELP_LEARNING, outcome="helped")
    assert result.adopted is True
    assert len(provider.requests) == 1
    assert len(reflection.pending_help()) == 1

    answer = reflection.accept_help(result.candidate.id, conversation_messages=())
    calls_after_delivery = len(provider.requests)
    repeated = reflection.accept_help(result.candidate.id, conversation_messages=())
    after = repository.read_document()

    assert answer.startswith("Начнём без магии")
    assert repeated == "Это предложение помощи уже было принято и обработано."
    assert len(provider.requests) == calls_after_delivery == 2
    assert provider.requests[-1].private_context["task"] == "accepted_honest_help_offer"
    assert after.facts == before.facts
    assert after.commitments == before.commitments
    assert after.decisions == before.decisions
    actions = [item["action"] for item in repository.list_audit_events()]
    assert "help_offer_accepted" in actions
    assert "help_offer_delivered" in actions


def test_rejected_help_is_suppressed_without_model_call(tmp_path):
    offer = {
        "observation": "Есть конкретная нерешённая развилка.",
        "offer": "Могу помочь сравнить два варианта в разговоре.",
        "expected_benefit": "Решение станет прозрачнее.",
        "why_now": "Тема явно поднята в текущем разговоре.",
        "capability": "conversation",
    }
    _, provider, _, reflection, _ = _stack(tmp_path, [_generated(help_offer=offer)])
    result = _reflect(reflection)

    reflection.reject_help(result.candidate.id)
    reflection.reject_help(result.candidate.id)

    assert reflection.pending_help() == ()
    assert len(provider.requests) == 1


def test_fast_profile_cannot_silently_fallback_for_reflection(tmp_path):
    _, provider, profiles, reflection, _ = _stack(tmp_path, [_generated()])
    profiles.set_active_profile("fast")

    with pytest.raises(ReflectionUnavailableError, match="fast"):
        _reflect(reflection)

    assert provider.requests == []
    assert profiles.get_active_profile().profile_id == "fast"


def test_explicit_intent_uses_bounded_conversation_evidence_and_ordinary_chat_does_not_reflect(tmp_path):
    repository, provider, _, _, service = _stack(
        tmp_path,
        ["Я рядом.", _generated(text="Мне важно не изображать согласие там, где его нет.")],
    )

    conversation_id, ordinary = service.send("Сегодня тяжёлый день.", project_id=PROJECT_ID)
    assert ordinary == "Я рядом."
    assert repository.read_document().reflections == []

    _, response = service.send(
        "Маша, подумай о себе: как тебе сохранять честность?",
        project_id=PROJECT_ID,
        conversation_id=conversation_id,
    )
    candidate = repository.read_document().memory_candidates[-1]
    history = service.history.messages(conversation_id)

    assert "сохранила это как свою рефлексию" in response
    assert candidate.proposed_payload["evidence"]["conversation_message_ids"] == [
        item.id for item in history[:-1]
    ]
    assert len(provider.requests) == 2


def test_perspective_query_receives_only_adopted_reflection_context(tmp_path):
    _, provider, _, _, service = _stack(
        tmp_path,
        [_generated(), "Я всё ещё так думаю, но это моя интерпретация, а не факт о тебе."],
    )
    conversation_id, _ = service.send(
        "Маша, подумай о себе: честный спор и близость",
        project_id=PROJECT_ID,
    )

    _, answer = service.send(
        "Что ты думаешь об этом сейчас?",
        project_id=PROJECT_ID,
        conversation_id=conversation_id,
    )
    request = provider.requests[-1]

    assert answer.startswith("Я всё ещё")
    assert request.private_context["context_lens"] == "masha_perspective"
    assert {item["category"] for item in request.private_context["memory_context"]} == {"мнение Маши"}
    assert all("id" not in item for item in request.private_context["memory_context"])
    assert "субъективно" in request.private_context["perspective_contract"]


def test_general_conversation_is_not_automatically_coloured_by_reflections(tmp_path):
    _, provider, _, reflection, service = _stack(
        tmp_path,
        [_generated(), "Обычный ответ без навязанного самоанализа."],
    )
    _reflect(reflection)

    service.send("Как собрать проект?", project_id=PROJECT_ID)
    request = provider.requests[-1]

    assert request.private_context["context_lens"] == "general"
    assert all(item["record_type"] != "reflection" for item in request.private_context["memory_context"])


def test_reflection_cli_is_human_readable_and_hides_internal_ids(tmp_path):
    _, _, _, reflection, service = _stack(tmp_path, [_generated()])
    result = _reflect(reflection)
    output: list[str] = []

    _run_reflections_command(
        "list",
        service=service,
        conversation_id="conversation-1",
        project_id=PROJECT_ID,
        output_fn=output.append,
    )
    _run_help_command("pending", service=service, output_fn=output.append)

    rendered = "\n".join(output)
    assert "Мысли Маши" in rendered
    assert result.reflection.text in rendered
    assert result.reflection.id not in rendered
    assert result.candidate.id not in rendered

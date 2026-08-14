import json
from pathlib import Path
from types import SimpleNamespace

from backend.conversation.capability_router import (
    CapabilityIntent,
    LocalSemanticIntentClassifier,
    NaturalLanguageCapabilityRouter,
    ParsedCapabilityIntent,
    normalize_utterance,
)
from backend.identity.identity_kernel import IdentityKernel
from backend.identity.identity_store import IdentityStore
from backend.llm.fake_provider import FakeProvider
from backend.llm.model_models import MessageRole, PrivacyScope
from backend.llm.model_router import ModelRouter
from backend.llm.model_provider import ModelProviderUnavailableError, ModelTimeoutError


ROOT = Path(__file__).resolve().parents[1]


def test_normalization_handles_addressing_spacing_and_word_numbers():
    assert normalize_utterance("  Машенька,  напомни через две минуты! ") == "напомни через 2 минуты"


def test_fixed_allowlist_router_uses_composable_patterns_not_sentence_dictionary():
    router = NaturalLanguageCapabilityRouter()
    cases = {
        "Маш, что у меня сегодня?": CapabilityIntent.QUERY_COMMITMENTS,
        "Какие у нас дела?": CapabilityIntent.QUERY_COMMITMENTS,
        "Что было запланировано?": CapabilityIntent.QUERY_COMMITMENTS,
        "Добавь мне задачу купить молоко": CapabilityIntent.CREATE_COMMITMENT,
        "Запиши в дела позвонить врачу": CapabilityIntent.CREATE_COMMITMENT,
        "Надо не забыть купить корм": CapabilityIntent.CREATE_COMMITMENT,
        "Билеты купил": CapabilityIntent.COMPLETE_COMMITMENT,
        "С молоком закончили": CapabilityIntent.COMPLETE_COMMITMENT,
        "Забудь, что я люблю чай": CapabilityIntent.FORGET_MEMORY,
        "К чему мы хотели вернуться?": CapabilityIntent.QUERY_CONTINUITY,
        "Напомни через две минуты сказать мяу": CapabilityIntent.CREATE_COMMITMENT,
        "дело добавь купить билеты": CapabilityIntent.CREATE_COMMITMENT,
        "добавь обязательство купить билеты": CapabilityIntent.CREATE_COMMITMENT,
        "добавь нам дело купить билеты": CapabilityIntent.CREATE_COMMITMENT,
        "и ещё задача купить билеты": CapabilityIntent.CREATE_COMMITMENT,
    }
    for phrase, expected in cases.items():
        parsed = router.route(phrase)
        assert parsed is not None
        assert parsed.intent is expected
        assert parsed.confidence >= router.CONFIDENCE_THRESHOLD


def test_shared_history_aliases_route_locally_without_hijacking_general_history():
    router = NaturalLanguageCapabilityRouter()
    for phrase in (
        "Что есть в нашей истории?",
        "Что у нас есть в истории?",
        "Что у нас в истории?",
        "Покажи нашу историю",
        "Что сохранено в нашей истории?",
        "Что есть в общей истории?",
    ):
        parsed = router.route(phrase)
        assert parsed is not None
        assert parsed.intent is CapabilityIntent.QUERY_CONTINUITY

    assert router.route("Расскажи историю Рима") is None


def test_only_shared_history_context_enables_optional_semantic_routing():
    class SharedHistoryClassifier:
        def __init__(self):
            self.calls = []

        def classify(self, message):
            self.calls.append(message)
            return ParsedCapabilityIntent(
                intent=CapabilityIntent.QUERY_CONTINUITY,
                confidence=0.91,
                source="local_semantic",
            )

    classifier = SharedHistoryClassifier()
    router = NaturalLanguageCapabilityRouter(classifier)
    phrase = "Может, покажешь, что у нас сохранено в истории?"

    parsed = router.route(phrase)

    assert parsed is not None and parsed.intent is CapabilityIntent.QUERY_CONTINUITY
    assert classifier.calls == [phrase]

    class Exploding:
        def classify(self, message):
            raise AssertionError("general history must not enter capability classification")

    assert NaturalLanguageCapabilityRouter(Exploding()).route("Расскажи историю Рима") is None


def test_forget_wins_over_broad_today_query_and_keeps_reference_text():
    parsed = NaturalLanguageCapabilityRouter().route(
        "Забудь, что сегодня мы запустили первый MVP Дома"
    )

    assert parsed is not None
    assert parsed.intent is CapabilityIntent.FORGET_MEMORY
    assert parsed.entity == "сегодня мы запустили первый mvp дома"


def test_generic_what_about_reference_requires_real_record_context():
    router = NaturalLanguageCapabilityRouter()
    assert router.route("Что там с билетами?") is None
    assert router.route("Что с погодой?") is None
    assert router.route("Что с фильмом?") is None
    assert router.route("Как тебе кофе?") is None


def test_low_confidence_semantic_classification_falls_through_to_conversation():
    class LowConfidence:
        def classify(self, message):
            return ParsedCapabilityIntent(
                intent=CapabilityIntent.CREATE_COMMITMENT,
                confidence=0.55,
                entity="позвонить врачу",
                source="local_semantic",
            )

    assert NaturalLanguageCapabilityRouter(LowConfidence()).route("может, надо бы дело про врача") is None


def test_high_confidence_semantic_result_is_still_limited_to_allowlist():
    class HighConfidence:
        def classify(self, message):
            assert message == "может, добавим задачу про врача"
            return ParsedCapabilityIntent(
                intent=CapabilityIntent.CREATE_COMMITMENT,
                confidence=0.88,
                entity="позвонить врачу",
                source="local_semantic",
            )

    result = NaturalLanguageCapabilityRouter(HighConfidence()).route("может, добавим задачу про врача")
    assert result is not None
    assert result.intent is CapabilityIntent.CREATE_COMMITMENT
    assert result.entity == "позвонить врачу"


def test_semantic_classifier_is_not_called_without_a_capability_signal():
    class Exploding:
        def classify(self, message):
            raise AssertionError("ordinary conversation must not be classified")

    assert NaturalLanguageCapabilityRouter(Exploding()).route("Как тебе сегодняшний вечер?") is None


def test_explicit_continuity_markers_win_over_task_words():
    router = NaturalLanguageCapabilityRouter()
    for phrase in (
        "Не потеряй тему задачи про поездку",
        "Оставь эту нить про выбор билетов",
        "Давай к плану отпуска потом вернёмся",
    ):
        parsed = router.route(phrase)
        assert parsed is not None
        assert parsed.intent is CapabilityIntent.OPEN_CONTINUITY


def test_semantic_provider_failure_falls_through_to_conversation():
    class Unavailable:
        def __init__(self, error):
            self.error = error

        def classify(self, message):
            raise self.error

    for error in (
        ModelProviderUnavailableError("offline"),
        ModelTimeoutError("slow"),
    ):
        assert NaturalLanguageCapabilityRouter(Unavailable(error)).route(
            "Может, заведём задачу про врача?"
        ) is None


def test_local_semantic_classifier_sees_only_current_utterance_and_fixed_allowlist():
    provider = FakeProvider(response_text=json.dumps({
        "intent": "create_commitment",
        "confidence": 0.91,
        "entity": "позвонить врачу",
        "temporal_scope": None,
    }, ensure_ascii=False))
    profiles = SimpleNamespace(get_active_profile=lambda: SimpleNamespace(
        provider_id=provider.provider_id,
        model_id=provider.model_id,
        timeout_seconds=30.0,
    ))
    classifier = LocalSemanticIntentClassifier(
        router=ModelRouter([provider]),
        identity_kernel=IdentityKernel(IdentityStore(ROOT / "identity" / "masha.identity.json")),
        model_profiles=profiles,
    )

    result = classifier.classify("Может, заведём задачу про врача?")

    assert result is not None
    assert result.intent is CapabilityIntent.CREATE_COMMITMENT
    assert result.entity == "позвонить врачу"
    assert provider.last_request is not None
    assert provider.last_request.privacy_scope is PrivacyScope.LOCAL_ONLY
    assert provider.last_request.private_context == {}
    assert len(provider.last_request.messages) == 2
    assert provider.last_request.messages[0].role is MessageRole.SYSTEM
    assert "shared history" in provider.last_request.messages[0].content
    assert provider.last_request.messages[1].role is MessageRole.USER
    assert provider.last_request.messages[1].content == "Может, заведём задачу про врача?"


def test_scoped_memory_query_carries_natural_topic():
    parsed = NaturalLanguageCapabilityRouter().route(
        "Кстати, а что ты помнишь про то, что я люблю пить?"
    )

    assert parsed is not None
    assert parsed.intent is CapabilityIntent.QUERY_MEMORY
    assert parsed.entity == "то что я люблю пить"

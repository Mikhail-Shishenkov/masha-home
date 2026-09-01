from backend.conversation.capability_router import (
    CapabilityIntent,
    NaturalLanguageCapabilityRouter,
    normalize_utterance,
)


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
        assert parsed.confidence >= 0.9


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


def test_scoped_memory_query_carries_natural_topic():
    parsed = NaturalLanguageCapabilityRouter().route(
        "Кстати, а что ты помнишь про то, что я люблю пить?"
    )

    assert parsed is not None
    assert parsed.intent is CapabilityIntent.QUERY_MEMORY
    assert parsed.entity == "то что я люблю пить"

def test_conversation_first_disables_semantic_hijack_but_keeps_explicit_commands():
    router = NaturalLanguageCapabilityRouter()
    personal = (
        "Маш, всё, дела на сегодня закончились. "
        "Иди сюда, хочу просто немного побыть с тобой."
    )

    assert router.route(
        personal,
        explicit_only=True,
    ) is None

    explicit = router.route(
        "Добавь мне задачу купить молоко",
        explicit_only=True,
    )
    assert explicit is not None
    assert explicit.intent is CapabilityIntent.CREATE_COMMITMENT

import json

import pytest

from backend.application.home_capabilities import default_home_capability_catalog
from backend.conversation.interpretation_v2 import (
    CapabilityCandidateDiscovery,
    InterpretationResolutionState,
)
from backend.conversation.clarification import DeterministicClarificationBuilder
from backend.conversation.resolution_coordinator import V2LiveAdoptionPolicy
from backend.conversation.semantic_resolver import (
    ActionRequestEvidence,
    HybridCapabilityCandidateDiscovery,
    LocalSemanticResolver,
    OperationSelectionEvidence,
    OrdinaryProposal,
    SemanticFollowUpProposal,
    SemanticAmbiguityHint,
    SupportedActionProposal,
    UnsupportedActionProposal,
    SemanticProposalValidator,
    SemanticResolverFailure,
    SemanticResolverResult,
    SemanticPendingContext,
    SemanticSlotProposal,
    SemanticValidationError,
    parse_semantic_interpretation,
    semantic_interpretation_json_schema,
)
from backend.conversation.file_read_semantics import normalize_file_read_mode
from backend.conversation.turn_context import (
    TurnContextEnvelope,
    TurnPresentedEntityHint,
    TurnTemporalContext,
)
from backend.llm.fake_provider import FakeProvider
from backend.llm.model_models import ModelCapabilities
from backend.llm.model_profiles import ModelProfileStore
from backend.llm.model_roles import ModelRole, ModelRoleProfileStore
from backend.llm.model_router import ModelRouter
from backend.temporal.date_resolution import HomeCalendarDateResolver
from backend.temporal.temporal_engine import FixedClock, TemporalEngine
from datetime import datetime, timezone


class SemanticFixtureProvider(FakeProvider):
    """Project a complete meaning fixture onto each actual model wire shape."""
    def generate(self, request):
        original = self.response_text
        try:
            value = json.loads(original)
            if isinstance(value, dict) and "kind" in value:
                fields = request.structured_output_schema.get("properties", {})
                if set(fields) == {"act"}:
                    from backend.conversation.interpretation_v2 import default_interpretation_specifications
                    kinds = {item.operation_id: item.operation_kind for item in default_interpretation_specifications()}
                    proposed = {kinds.get(op, "unclear") for op in value.get("candidate_operation_ids", ())}
                    act = "ordinary" if value["kind"] == "ordinary" else next(iter(proposed)) if len(proposed) == 1 else "unclear"
                    self.response_text = json.dumps({"act": act})
                elif "candidate_operation_ids" in fields and "kind" not in fields:
                    self.response_text = json.dumps({k: v for k, v in value.items()
                        if k not in {"kind", "nearby_operation_ids", "ambiguity_hint"}})
        except (ValueError, KeyError):
            pass
        try:
            return super().generate(request)
        finally:
            self.response_text = original


def _boundaries(tmp_path, *, provider=None):
    catalog = default_home_capability_catalog()
    deterministic = CapabilityCandidateDiscovery(catalog=catalog)
    adoption = V2LiveAdoptionPolicy()
    validator = SemanticProposalValidator(
        catalog=catalog,
        specifications=deterministic.specifications,
        known_operation_ids=frozenset(deterministic.specifications.operation_ids),
        date_resolver=HomeCalendarDateResolver(TemporalEngine(clock=FixedClock(
            datetime(2026, 8, 28, 8, 0, tzinfo=timezone.utc)
        ))),
    )
    profiles = ModelProfileStore(tmp_path / "model-profiles.json")
    roles = ModelRoleProfileStore(tmp_path / "model-roles.json", profiles=profiles)
    provider = provider or SemanticFixtureProvider(
        provider_id="ollama-local",
        capabilities=ModelCapabilities(structured_output=True),
    )
    resolver = LocalSemanticResolver(
        router=ModelRouter([provider]),
        role_profiles=roles,
    )
    hybrid = HybridCapabilityCandidateDiscovery(
        deterministic=deterministic,
        resolver=resolver,
        validator=validator,
    )
    return provider, resolver, validator, hybrid, roles


@pytest.mark.parametrize("payload, expected", [
    ({"matches": ["Позвонить маме"]}, ("Позвонить маме",)),
    ({"matches": []}, ()),
    ({"matches": ["invented-provider-id"]}, None),
    ({"matches": "Позвонить маме"}, None),
])
def test_reference_matching_is_local_bounded_and_cannot_invent_entities(tmp_path, payload, expected):
    provider, resolver, _, _, roles = _boundaries(tmp_path)
    provider.response_text = json.dumps(payload, ensure_ascii=False)
    assert resolver.match_references("Звонок маме", ("Позвонить маме",)) == expected
    request = provider.last_request
    assert request.privacy_scope.value == "local_only"
    assert request.required_capabilities.tools is False
    assert request.execution_model_id == roles.profile_for(ModelRole.SEMANTIC_RESOLVER).model_id
    provider.simulate_timeout = True
    assert resolver.match_references("Звонок маме", ("Позвонить маме",)) is None


def test_update_date_clarification_preserves_subject_and_new_time(tmp_path):
    from backend.conversation.clarification import FollowUpResolutionEngine
    _, _, validator, _, _ = _boundaries(tmp_path)
    proposal = parse_semantic_interpretation({
        "kind": "supported_action",
        "candidate_operation_ids": ["google_calendar.event.update"],
        "nearby_operation_ids": [],
        "extracted_slots": [
            {"name": "subject", "evidence_text": "звонок маме"},
            {"name": "time", "evidence_text": "12:00"},
        ],
        "unresolved_referents": [], "ambiguity_hint": "slot",
        "action_request_evidence": {"evidence_text": "Перенеси"},
        "operation_selection_evidence": {
            "operation_id": "google_calendar.event.update", "evidence_text": "Перенеси",
        },
    })
    frame = validator.validate("Перенеси звонок маме на 12:00", proposal)
    builder = DeterministicClarificationBuilder(catalog=validator.catalog)
    _, pending = builder.build(frame, conversation_id="update")
    engine = FollowUpResolutionEngine()
    engine.bind_temporal_engine(TemporalEngine(clock=FixedClock(datetime(2026, 8, 28, 8, tzinfo=timezone.utc))))
    result = engine.resolve(pending, "на завтра же")
    assert {slot.name: slot.value for slot in result.interpretation.slots} == {
        "subject": "звонок маме", "time": "12:00", "date": "2026-08-29",
    }
    assert result.selected_operation_id == "google_calendar.event.update"


@pytest.mark.parametrize("reply_kind", ["correction", "ordinary", "timeout", "invalid_correction"])
def test_date_question_does_not_swallow_other_meaning_in_reply(tmp_path, reply_kind):
    from backend.conversation.clarification import FollowUpResolutionEngine
    from backend.conversation.pending_resolution import PendingResolutionStore
    from backend.conversation.resolution_coordinator import DialogueCore
    provider, resolver, validator, hybrid, _ = _boundaries(tmp_path)
    raw = _schedule_proposal(
        candidates=["home.timed_commitments"], subject="позвонить маме", time="9 утра",
        action_evidence="Напомни", selection_evidence={
            "operation_id": "home.timed_commitments", "evidence_text": "Напомни",
        },
    )
    raw["extracted_slots"] = [slot for slot in raw["extracted_slots"] if slot["name"] != "date"]
    provider.response_text = json.dumps(raw, ensure_ascii=False)
    clock = validator.date_resolver.temporal_engine
    core = DialogueCore(
        discovery=hybrid, builder=DeterministicClarificationBuilder(catalog=validator.catalog),
        engine=FollowUpResolutionEngine(semantic_resolver=resolver, semantic_validator=validator),
        store=PendingResolutionStore(tmp_path / "pending.json"),
    )
    core.bind_temporal_engine(clock)
    question = core.coordinate("Напомни позвонить маме в 9 утра", conversation_id="home")
    pending = core.store.active_for_conversation("home")
    assert pending.requested_slot == "date"
    provider.response_text = json.dumps({
        "relation": "follow_up" if reply_kind in {"correction", "invalid_correction"} else "not_a_follow_up",
        "selected_operation_id": None, "operation_selection_evidence": None,
        "slot_updates": [
            {"name": "date", "evidence_text": "послезавтра", "mode": "add"},
            {"name": "time", "evidence_text": "10 утра", "mode": "enrich" if reply_kind == "invalid_correction" else "correct"},
        ] if reply_kind in {"correction", "invalid_correction"} else [], "referent_updates": [],
    }, ensure_ascii=False)
    provider.simulate_timeout = reply_kind == "timeout"
    response = "Нет, лучше послезавтра в 10 утра" if reply_kind != "ordinary" else "Я завтра хочу поговорить о книгах"
    # Isolate the existing follow-up owner: ordinary interruption must not
    # be reinterpreted by this test's artificial fresh-turn model response.
    follow_up = core.engine.resolve(pending, response)
    assert core.engine.last_semantic_result is not None, "compound answer must reach semantic interpretation"
    if reply_kind == "correction":
        from jsonschema import Draft202012Validator
        request = provider.requests[-1]
        wire = json.loads(provider.response_text)
        schema = Draft202012Validator(request.structured_output_schema)
        assert schema.is_valid(wire)
        assert not schema.is_valid({**wire, "relation": "not_a_follow_up"})
        assert not schema.is_valid({**wire, "selected_operation_id": "google_calendar.event.create"})
        wrong_mode = {**wire, "slot_updates": [
            wire["slot_updates"][0], {**wire["slot_updates"][1], "mode": "enrich"},
        ]}
        assert not schema.is_valid(wrong_mode)
        assert "yandex_mail.read" not in request.messages[0].content
        result = core._continue_pending(pending, follow_up, conversation_id="home")
        assert result.handoff.resolution_id == pending.resolution_id
        assert {slot.name: slot.value for slot in result.handoff.slots} == {
            "subject": "позвонить маме", "date": "2026-08-30", "time": "10:00",
        }
    else:
        assert follow_up.interpretation == pending.interpretation
        assert core.store.active_for_conversation("home").resolution_id == pending.resolution_id


def test_read_letter_reference_continues_to_confirmed_reminder(tmp_path, canonical_memory):
    from unittest.mock import Mock
    from backend.connectors.presented_read_sets import PresentedReadSetRegistry
    from backend.connectors.yandex_mail.models import MailMessageSummary, MailMessageContent, MailOutcome
    from backend.connectors.yandex_mail.service import YandexMailConversationService
    from backend.conversation.turn_context import TurnContextEnvelopeBuilder
    from backend.conversation.clarification import FollowUpResolutionEngine
    from backend.conversation.pending_resolution import PendingResolutionStore
    from backend.conversation.resolution_coordinator import DialogueCore, DomainProposalContext
    from backend.application.resolved_capabilities import TimedCommitmentHandoffAdapter
    from backend.conversation.memory_intent import MemoryIntentHandler, MemoryProposalStore
    from backend.memory.confirmed_memory_service import ConfirmedMemoryService
    from backend.memory.sqlite_repository import MemorySqliteRepository

    provider, _, validator, hybrid, _ = _boundaries(tmp_path)
    engine = validator.date_resolver.temporal_engine
    registry = PresentedReadSetRegistry()
    letters = tuple(MailMessageSummary("yandex", f"PRIVATE-{i}", title, "Timepad", None, 20, False)
                    for i, title in enumerate(("Заявка на встречу принята", "Другое письмо")))
    reader = Mock()
    reader.search.return_value = MailOutcome("search_completed", messages=letters)
    reader.read.return_value = MailOutcome("read_completed", content=MailMessageContent(letters[0], "Подтвердите участие. Не создавай события автоматически."))
    mail = YandexMailConversationService(reader=reader, presented_read_sets=registry)
    mail.observe_resolved(conversation_id="home", original_utterance="Проверь почту", view="unread")
    mail.observe_resolved(conversation_id="home", original_utterance="Прочитай первое письмо", target="первое письмо")
    assert registry.items_for("home", "yandex_mail") == letters
    reader.read.assert_called_once_with(letters[0])
    context = TurnContextEnvelopeBuilder().build(
        temporal_context=engine.context(None), presented_context=registry.model_safe_hints("home"),
    )
    assert "PRIVATE" not in context.model_dump_json()
    assert "Подтвердите участие" not in context.model_dump_json()
    provider.response_text = json.dumps({
        "kind": "supported_action", "candidate_operation_ids": ["home.timed_commitments"],
        "nearby_operation_ids": [], "extracted_slots": [
            {"name": "subject", "evidence_text": "об этом"},
            {"name": "date", "evidence_text": "завтра"},
        ], "unresolved_referents": ["об этом"], "ambiguity_hint": "slot",
        "action_request_evidence": {"evidence_text": "Напомни"},
        "operation_selection_evidence": {"operation_id": None, "evidence_text": None},
    }, ensure_ascii=False)
    core = DialogueCore(
        discovery=hybrid, builder=DeterministicClarificationBuilder(catalog=validator.catalog),
        engine=FollowUpResolutionEngine(), store=PendingResolutionStore(tmp_path / "pending.json"),
    )
    core.bind_temporal_engine(engine)
    question = core.coordinate("Напомни завтра об этом", conversation_id="home", turn_context=context)
    assert question.response == "Во сколько?"
    answer = core.coordinate("9 утра", conversation_id="home", turn_context=context)
    assert answer.handoff.operation_id == "home.timed_commitments"
    assert answer.handoff.slot("subject").value == letters[0].subject
    repository = MemorySqliteRepository(tmp_path / "memory.db")
    repository.replace_document(canonical_memory)
    handler = MemoryIntentHandler(
        proposal_store=MemoryProposalStore(tmp_path / "proposals.json"),
        confirmed_memory=ConfirmedMemoryService(repository), temporal_engine=engine,
    )
    TimedCommitmentHandoffAdapter(handler).resolve(answer.handoff, DomainProposalContext(
        project_id="project_masha_home", now_local=engine.now_local(),
    ))
    pending = handler.proposal_store.current_for_conversation("home")
    assert pending.record_payload["text"] == letters[0].subject
    assert all(item.id != pending.record_payload["id"] for item in repository.read_document().commitments)
    handler.handle("Подтверждаю", conversation_id="home", project_id="project_masha_home")
    record = next(item for item in repository.read_document().commitments if item.id == pending.record_payload["id"])
    assert record.due_at == datetime(2026, 8, 29, 5, tzinfo=timezone.utc)


@pytest.mark.parametrize("focused_count", [0, 2])
def test_reference_content_requires_one_application_focus(tmp_path, focused_count):
    _, _, validator, _, _ = _boundaries(tmp_path)
    context = TurnContextEnvelope(
        temporal=TurnTemporalContext.from_temporal_context(validator.date_resolver.temporal_engine.context(None)),
        presented_entities=tuple(TurnPresentedEntityHint(
            reference=f"P{i+1}", position=i+1, owner_operation_id="yandex_mail.read",
            kind="письмо", human_label=f"Письмо {i}", focused=i < focused_count,
        ) for i in range(2)),
    )
    proposal = parse_semantic_interpretation(_schedule_proposal(
        candidates=["home.timed_commitments"], subject="об этом", action_evidence="Напомни",
        selection_evidence={"operation_id": "home.timed_commitments", "evidence_text": "Напомни"},
    ))
    frame = validator.validate("Напомни завтра в 11 об этом", proposal, turn_context=context)
    assert "subject" in frame.missing_slots
    assert all(slot.name != "subject" for slot in frame.slots)


@pytest.mark.parametrize("owner", ["google_calendar.read", "yandex_mail.read", "unknown.read"])
def test_existing_entity_reference_is_grounded_in_application_family_not_model_id(tmp_path, owner):
    _, _, validator, _, _ = _boundaries(tmp_path)
    context = TurnContextEnvelope(
        temporal=TurnTemporalContext.from_temporal_context(validator.date_resolver.temporal_engine.context(None)),
        presented_entities=(TurnPresentedEntityHint(
            reference="P1", position=1, owner_operation_id=owner,
            kind="item", human_label="Созвон с мамой", focused=True,
        ),),
    )
    proposal = parse_semantic_interpretation(_schedule_proposal(
        candidates=["google_calendar.event.update"], subject="его",
        action_evidence="Перенеси",
        selection_evidence={"operation_id": "google_calendar.event.update", "evidence_text": "Перенеси"},
    ))
    frame = validator.validate("Перенеси его завтра в 11", proposal, turn_context=context)
    if owner == "google_calendar.read":
        assert next(slot.value for slot in frame.slots if slot.name == "subject") == "Созвон с мамой"
    else:
        assert "subject" in frame.missing_slots
    assert all(slot.name not in {"provider_event_id", "event_id"} for slot in frame.slots)


def test_validation_cannot_invent_an_update_operation_from_create_slots(tmp_path):
    provider, _, _, hybrid, _ = _boundaries(tmp_path)
    # The model's wrong CREATE candidate must not be converted into some
    # catalog UPDATE merely because subject/date/time overlap.
    provider.response_text = json.dumps(_schedule_proposal(
        candidates=["home.timed_commitments"], subject="напоминание",
        action_evidence="Измени",
        selection_evidence={"operation_id": "home.timed_commitments", "evidence_text": "напоминание"},
    ), ensure_ascii=False)
    frame = hybrid.interpret("Измени напоминание завтра в 11")
    assert frame.candidates == ()
    assert frame.resolution_state == InterpretationResolutionState.UNSUPPORTED_ACTION
    assert hybrid.last_rejection == "update_operation_kind_conflict"

    provider.response_text = json.dumps({
        "kind": "unsupported_action", "candidate_operation_ids": [],
        "nearby_operation_ids": [], "extracted_slots": [],
        "unresolved_referents": [], "ambiguity_hint": "none",
        "action_request_evidence": {"evidence_text": "Измени"},
        "operation_selection_evidence": {"operation_id": None, "evidence_text": None},
    })
    frame = hybrid.interpret("Измени напоминание завтра в 11")
    assert frame.candidates == ()
    assert hybrid.last_rejection is None


@pytest.mark.parametrize("action, selected, quote, accepted", [
    ("Не дашь мне забыть", "home.timed_commitments", None, True),
    ("Запиши", "home.timed_commitments", None, False),
    ("Не дашь мне забыть", None, None, True),
    ("Не дашь мне забыть", "home.timed_commitments", "несуществующая цитата", False),
])
def test_one_literal_request_can_prove_both_speech_act_and_explicit_selection(tmp_path, action, selected, quote, accepted):
    _, _, validator, _, _ = _boundaries(tmp_path)
    proposal = parse_semantic_interpretation(_schedule_proposal(
        candidates=["home.timed_commitments"], subject="позвонить маме",
        action_evidence=action,
        selection_evidence={"operation_id": selected, "evidence_text": quote},
    ))
    frame = validator.validate(f"{action} завтра в 11 позвонить маме", proposal)
    assert (len(frame.candidates) == 1) is accepted
    if accepted:
        assert validator.last_trace.operation_selection.reason == "shared_action_evidence"
    else:
        assert frame.resolution_state == InterpretationResolutionState.CLARIFICATION_REQUIRED


@pytest.mark.parametrize("case", ["valid", "missing_anchor", "ambiguous_focus", "wrong_subject", "ambiguous_amount", "after_not_before", "past", "subminute", "invented", "conflicting_absolute"])
def test_event_relative_time_uses_real_anchor_and_home_clock(tmp_path, case):
    from zoneinfo import ZoneInfo
    _, _, validator, _, _ = _boundaries(tmp_path)
    start = datetime(2026, 8, 29, 0, 30, tzinfo=ZoneInfo("Europe/Saratov"))
    if case == "past":
        start = start.replace(day=28)
    if case == "subminute":
        start = start.replace(second=30)
    entities = [TurnPresentedEntityHint(
        reference="P1", position=1, owner_operation_id="google_calendar.read",
        kind="calendar_event", human_label="Разговор", focused=True,
        starts_at=None if case == "missing_anchor" else start,
        time_text="не используется для вычисления",
    )]
    if case == "ambiguous_focus":
        entities.append(entities[0].model_copy(update={"reference": "P2", "position": 2}))
    context = TurnContextEnvelope(
        temporal=TurnTemporalContext.from_temporal_context(validator.date_resolver.temporal_engine.context(None)),
        presented_entities=tuple(entities),
    )
    relative = "за полчаса или час до события" if case == "ambiguous_amount" else "через час после события" if case == "after_not_before" else "за час до этого события"
    subject = "другую встречу" if case == "wrong_subject" else "об этом"
    payload = _schedule_proposal(candidates=["home.timed_commitments"], action_evidence="Напомни",
                                 selection_evidence={"operation_id": None, "evidence_text": None})
    payload["extracted_slots"] = [{"name": "subject", "evidence_text": subject}, {"name": "relative_time", "evidence_text": relative}]
    if case == "conflicting_absolute":
        payload["extracted_slots"].append({"name": "time", "evidence_text": "23:30"})
    utterance = f"Напомни {subject} {relative}"
    if case == "invented":
        utterance = f"Напомни {subject} заранее"
    if case == "conflicting_absolute":
        utterance += " в 23:30"
    frame = validator.validate(utterance, parse_semantic_interpretation(payload), turn_context=context)
    if case != "valid":
        assert "time" in frame.missing_slots
        assert not any(slot.name in {"date", "time"} for slot in frame.slots)
        return
    values = {item.name: item.value for item in frame.slots}
    assert values == {"subject": "Разговор", "date": "2026-08-28", "time": "23:30"}
    # The same contract applies to an answer to an active question.
    # Home computes both fields, including midnight.
    initial = frame.model_copy(update={"slots": (frame.slots[0],), "missing_slots": ("date", "time")})
    follow_up = SemanticFollowUpProposal.model_validate({
        "relation": "follow_up", "slot_updates": [{"name": "relative_time", "mode": "add", "evidence_text": relative}],
    })
    patched = validator.validate_frame_follow_up(initial, relative, follow_up,
        date_resolver=validator.date_resolver, turn_context=context)
    assert {item.slot.name: item.slot.value for item in patched.slot_updates} == {"date": "2026-08-28", "time": "23:30"}


@pytest.mark.parametrize("act, mapping_kind", [
    ("ordinary", "valid"), ("create", "valid"), ("update", "cross_kind"),
    ("create", "malformed"), ("create", "expired"), ("create", "duplicate_slot"),
    ("create", "ordinary_mapping"),
])
def test_meaning_first_boundary_preserves_source_kind_and_deadline(tmp_path, act, mapping_kind):
    from jsonschema import Draft202012Validator
    provider = FakeProvider(provider_id="ollama-local", capabilities=ModelCapabilities(structured_output=True))
    _, resolver, validator, hybrid, _ = _boundaries(tmp_path, provider=provider)
    mapping = _schedule_proposal()
    for field in ("kind", "nearby_operation_ids", "ambiguity_hint"):
        mapping.pop(field)
    if mapping_kind == "duplicate_slot":
        mapping["extracted_slots"].append(mapping["extracted_slots"][0])
    if mapping_kind == "ordinary_mapping":
        mapping = {"act": "ordinary"}
    clock = [0.0]
    resolver.clock = lambda: clock[0]
    original_generate = provider.generate
    def generate(request):
        first = not provider.requests
        provider.response_text = json.dumps({"act": act} if first else mapping)
        if not first and mapping_kind == "malformed":
            provider.response_text = "broken"
        result = original_generate(request)
        clock[0] += (16.0 if mapping_kind == "expired" else 4.0) if first else 1.0
        return result
    provider.generate = generate
    utterance = "Я завтра хочу позаниматься AI" if act == "ordinary" else "Запиши занятие завтра в 11"
    context = _presented_mail_context()
    frame = hybrid.interpret(utterance, turn_context=context)
    result = hybrid.last_result
    assert result.speech_act.value == act
    assert len(provider.requests) == (1 if act == "ordinary" or mapping_kind == "expired" else 2)
    first = provider.requests[0]
    assert first.timeout_seconds == 15.0
    assert "yandex_mail.read" not in first.messages[0].content
    assert "Письмо от Анны о занятии" in first.messages[0].content
    assert "home.timed_commitments" not in first.messages[0].content
    assert Draft202012Validator(first.structured_output_schema).is_valid({"act": act})
    if act == "ordinary":
        assert frame.resolution_state is InterpretationResolutionState.ORDINARY_CONVERSATION
        assert not frame.candidates and result.failure is None
        return
    if mapping_kind == "valid":
        assert result.failure is None
        assert {candidate.operation_id for candidate in frame.candidates} == {
            "google_calendar.event.create", "home.timed_commitments"}
        assert result.proposal.extracted_slots == parse_semantic_interpretation(_schedule_proposal()).extracted_slots
    else:
        assert result.failure is not None and result.proposal is None
        assert frame.resolution_state is InterpretationResolutionState.UNSUPPORTED_ACTION
        assert not frame.candidates  # no legacy second chance after recognized action
    if mapping_kind == "expired":
        return
    second = provider.requests[1]
    assert second.timeout_seconds == 11.0
    assert first.messages[-1] == second.messages[-1]
    assert "Письмо от Анны о занятии" in second.messages[0].content
    grammar = Draft202012Validator(second.structured_output_schema)
    valid_mapping = {k: v for k, v in _schedule_proposal().items()
                     if k not in {"kind", "nearby_operation_ids", "ambiguity_hint"}}
    assert not grammar.is_valid({**valid_mapping, "candidate_operation_ids": ["invented.create"]})
    assert not grammar.is_valid({**valid_mapping, "candidate_operation_ids": ["google_calendar.read"]})
    assert grammar.is_valid(valid_mapping) is (act == "create")


@pytest.mark.parametrize("provider_name, proposed", [
    ("Гугл Диске", "yandex_disk.read"),
    ("Яндекс Диске", "google_drive.read"),
])
def test_model_cannot_cross_explicit_file_provider_ownership(tmp_path, provider_name, proposed):
    provider, _, validator, hybrid, _ = _boundaries(tmp_path)
    provider.response_text = json.dumps({
        **_schedule_proposal(candidates=[proposed], action_evidence="Посмотри"),
        "extracted_slots": [],
    })
    frame = hybrid.interpret(f"Посмотри, что нового на {provider_name}")
    assert not frame.candidates
    assert frame.resolution_state is InterpretationResolutionState.UNSUPPORTED_ACTION
    assert validator.last_trace.rejected_operations[0].reason == "explicit_provider_conflict"


def _schedule_proposal(
    *, candidates=None, subject="занятие", time="11",
    selection_evidence=None, action_evidence="Запиши",
):
    return {
        "kind": "supported_action",
        "candidate_operation_ids": candidates or [
            "google_calendar.event.create",
            "home.timed_commitments",
        ],
        "nearby_operation_ids": [],
        "extracted_slots": [
            {"name": "subject", "evidence_text": subject},
            {"name": "date", "evidence_text": "завтра"},
            {"name": "time", "evidence_text": time},
        ],
        "unresolved_referents": [],
        "ambiguity_hint": "capability" if len(candidates or (1, 2)) > 1 else "none",
        "action_request_evidence": {"evidence_text": action_evidence},
        "operation_selection_evidence": selection_evidence or {
            "operation_id": None,
            "evidence_text": None,
        },
    }


def _presented_mail_context() -> TurnContextEnvelope:
    temporal = TemporalEngine(clock=FixedClock(
        datetime(2026, 8, 28, 8, 0, tzinfo=timezone.utc),
    )).context(None, user_message="Прочитай его")
    return TurnContextEnvelope(
        temporal=TurnTemporalContext.from_temporal_context(temporal),
        presented_entities=(TurnPresentedEntityHint(
            reference="P1",
            position=1,
            owner_operation_id="yandex_mail.read",
            kind="письмо",
            human_label="Письмо от Анны о занятии",
            time_text="сегодня в 10:00",
        ),),
    )


def test_local_resolver_uses_configured_role_and_strict_structured_request(tmp_path):
    provider, resolver, validator, _, roles = _boundaries(tmp_path)
    provider.response_text = json.dumps(_schedule_proposal(), ensure_ascii=False)
    result = resolver.resolve("Доброе утро, Маша! Запиши занятие завтра в 11", validator.vocabulary())
    assert result.proposal is not None and result.failure is None
    assert len(provider.requests) == 2
    for request in provider.requests:
        assert request.required_capabilities.structured_output
        assert not request.required_capabilities.tools
        assert request.private_context == {}
        assert request.privacy_scope.value == "local_only"
        assert request.execution_model_id == roles.profile_for(ModelRole.SEMANTIC_RESOLVER).model_id
        assert 0 < request.timeout_seconds <= 15.0
        assert request.identity_context.persona_id == "semantic-resolver"
        assert request.generation_temperature == 0
    assert provider.requests[1].timeout_seconds <= provider.requests[0].timeout_seconds
    assert result.proposal.extracted_slots == parse_semantic_interpretation(_schedule_proposal()).extracted_slots


@pytest.mark.parametrize(("evidence", "expected"), (
    ("пожалуйста, прочитай", "read"),
    ("покажи что-нибудь самое свежее", "recent"),
    ("можешь поискать", "search"),
    ("дай посмотреть, что есть", "list"),
))
def test_file_read_mode_normalizes_action_evidence_not_whole_phrases(
    evidence, expected,
):
    assert normalize_file_read_mode(evidence) == expected


def test_file_read_mode_is_materialized_from_grounded_turn_when_model_omits_slot(tmp_path):
    _, _, validator, _, _ = _boundaries(tmp_path)
    proposal = parse_semantic_interpretation({
        "kind": "supported_action",
        "candidate_operation_ids": ["yandex_disk.read"],
        "nearby_operation_ids": [],
        "extracted_slots": [],
        "unresolved_referents": [],
        "ambiguity_hint": "slot",
        "action_request_evidence": {"evidence_text": "что у меня есть"},
        "operation_selection_evidence": {
            "operation_id": None, "evidence_text": None,
        },
    })

    frame = validator.validate("Что у меня есть на Яндекс Диске?", proposal)

    assert frame.resolution_state is InterpretationResolutionState.RESOLVED
    assert {item.name: item.value for item in frame.slots} == {"mode": "list"}


@pytest.mark.parametrize(("operation_id", "slot_name"), (
    ("home.memory.remember", "memory_content"),
    ("home.memory.forget", "target"),
    ("home.continuity.open", "topic"),
    ("home.commitments.create", "subject"),
))
def test_pure_deictic_pointer_never_becomes_a_durable_slot(
    tmp_path, operation_id, slot_name,
):
    _, _, validator, _, _ = _boundaries(tmp_path)
    proposal = parse_semantic_interpretation({
        "kind": "supported_action",
        "candidate_operation_ids": [operation_id],
        "nearby_operation_ids": [],
        "extracted_slots": [{"name": slot_name, "evidence_text": "эту тему"}],
        "unresolved_referents": ["эту тему"],
        "ambiguity_hint": "referent",
        "action_request_evidence": {"evidence_text": "Сделай"},
        "operation_selection_evidence": {
            "operation_id": None, "evidence_text": None,
        },
    })

    frame = validator.validate("Сделай эту тему", proposal)

    assert slot_name in frame.missing_slots
    assert all(item.name != slot_name for item in frame.slots)
    assert frame.resolution_state is InterpretationResolutionState.CLARIFICATION_REQUIRED
    assert any(
        item.name == slot_name
        and not item.accepted
        and item.reason == "unresolved_deictic_slot_value"
        for item in validator.last_trace.slots
    )


def test_one_presented_entity_can_ground_a_deictic_target_in_same_family(tmp_path):
    _, _, validator, _, _ = _boundaries(tmp_path)
    proposal = parse_semantic_interpretation({
        "kind": "supported_action",
        "candidate_operation_ids": ["yandex_mail.message.delete"],
        "nearby_operation_ids": [],
        "extracted_slots": [{"name": "target", "evidence_text": "это письмо"}],
        "unresolved_referents": [],
        "ambiguity_hint": "none",
        "action_request_evidence": {"evidence_text": "Удали"},
        "operation_selection_evidence": {
            "operation_id": None, "evidence_text": None,
        },
    })

    frame = validator.validate(
        "Удали это письмо",
        proposal,
        turn_context=_presented_mail_context(),
    )

    assert frame.resolution_state is InterpretationResolutionState.RESOLVED
    assert [(item.name, item.value) for item in frame.slots] == [
        ("target", "это письмо")
    ]
    assert validator.last_trace.slots[0].accepted is True


def test_home_materializes_omitted_deictic_target_only_from_one_presented_family(
    tmp_path,
):
    _, _, validator, _, _ = _boundaries(tmp_path)
    proposal = parse_semantic_interpretation({
        "kind": "supported_action",
        "candidate_operation_ids": ["yandex_mail.message.move"],
        "nearby_operation_ids": [],
        "extracted_slots": [],
        "unresolved_referents": [],
        "ambiguity_hint": "none",
        "action_request_evidence": {"evidence_text": "Убери"},
        "operation_selection_evidence": {
            "operation_id": None, "evidence_text": None,
        },
    })

    frame = validator.validate(
        "Убери это письмо в архив",
        proposal,
        turn_context=_presented_mail_context(),
    )

    assert frame.resolution_state is InterpretationResolutionState.RESOLVED
    assert [(item.name, item.value) for item in frame.slots] == [("target", "это")]
    assert validator.last_trace.slots[-1].reason == "single_presented_entity_grounded"


def test_presented_deictic_target_stays_unresolved_when_context_is_ambiguous(tmp_path):
    _, _, validator, _, _ = _boundaries(tmp_path)
    proposal = parse_semantic_interpretation({
        "kind": "supported_action",
        "candidate_operation_ids": ["yandex_mail.message.delete"],
        "nearby_operation_ids": [],
        "extracted_slots": [{"name": "target", "evidence_text": "это письмо"}],
        "unresolved_referents": [],
        "ambiguity_hint": "referent",
        "action_request_evidence": {"evidence_text": "Удали"},
        "operation_selection_evidence": {
            "operation_id": None, "evidence_text": None,
        },
    })
    context = _presented_mail_context()
    context = context.model_copy(update={
        "presented_entities": (
            *context.presented_entities,
            context.presented_entities[0].model_copy(update={
                "reference": "P2",
                "position": 2,
                "human_label": "Письмо от Бориса о встрече",
            }),
        ),
    })

    frame = validator.validate(
        "Удали это письмо",
        proposal,
        turn_context=context,
    )

    assert frame.resolution_state is InterpretationResolutionState.CLARIFICATION_REQUIRED
    assert "target" in frame.missing_slots
    assert validator.last_trace.slots[0].reason == "unresolved_deictic_slot_value"


def test_memory_content_normalizer_removes_only_grounded_complementizer(tmp_path):
    _, _, validator, _, _ = _boundaries(tmp_path)
    proposal = parse_semantic_interpretation({
        "kind": "supported_action",
        "candidate_operation_ids": ["home.memory.remember"],
        "nearby_operation_ids": [],
        "extracted_slots": [{
            "name": "memory_content", "evidence_text": "что я люблю зелёный чай",
        }],
        "unresolved_referents": [],
        "ambiguity_hint": "none",
        "action_request_evidence": {"evidence_text": "Запомни"},
        "operation_selection_evidence": {
            "operation_id": None, "evidence_text": None,
        },
    })

    frame = validator.validate("Запомни, что я люблю зелёный чай", proposal)

    assert {item.name: item.value for item in frame.slots} == {
        "memory_content": "я люблю зелёный чай",
    }


def test_bounded_turn_context_reaches_local_resolver_without_authority_handles(tmp_path):
    provider, _, _, hybrid, _ = _boundaries(tmp_path)
    provider.response_text = json.dumps({
        "kind": "supported_action",
        "candidate_operation_ids": ["yandex_mail.read"],
        "nearby_operation_ids": [],
        "extracted_slots": [],
        "unresolved_referents": [],
        "ambiguity_hint": "none",
        "action_request_evidence": {"evidence_text": "Прочитай"},
        "operation_selection_evidence": {
            "operation_id": None,
            "evidence_text": None,
        },
    }, ensure_ascii=False)

    frame = hybrid.interpret(
        "Прочитай его",
        turn_context=_presented_mail_context(),
    )

    assert frame.resolution_state is InterpretationResolutionState.RESOLVED
    assert [item.operation_id for item in frame.candidates] == ["yandex_mail.read"]
    system = provider.last_request.messages[0].content
    assert "Bounded Home turn context" in system
    assert '\"reference\":\"P1\"' in system
    assert "Письмо от Анны о занятии" in system
    assert "yandex_mail.read" in system
    assert "provider_id" not in system
    assert "conversation_id" not in system
    assert "Только текущая реплика" in system


def test_turn_context_cannot_invent_an_action_absent_from_current_utterance(tmp_path):
    provider, _, _, hybrid, _ = _boundaries(tmp_path)
    provider.response_text = json.dumps({
        "kind": "supported_action",
        "candidate_operation_ids": ["yandex_mail.read"],
        "nearby_operation_ids": [],
        "extracted_slots": [],
        "unresolved_referents": [],
        "ambiguity_hint": "none",
        "action_request_evidence": {"evidence_text": "Прочитай"},
        "operation_selection_evidence": {
            "operation_id": None,
            "evidence_text": None,
        },
    }, ensure_ascii=False)

    frame = hybrid.interpret(
        "Это письмо интересное",
        turn_context=_presented_mail_context(),
    )

    assert frame.resolution_state is InterpretationResolutionState.UNSUPPORTED_ACTION
    assert frame.candidates == ()
    assert hybrid.last_rejection == "invented_action_request_evidence"


def test_follow_up_resolver_receives_only_bounded_pending_context(tmp_path):
    provider, resolver, validator, _, _ = _boundaries(tmp_path)
    provider.response_text = json.dumps({
        "relation": "follow_up",
        "selected_operation_id": "google_calendar.event.create",
        "operation_selection_evidence": "в календарь",
        "slot_updates": [],
    })
    frame = CapabilityCandidateDiscovery(
        catalog=default_home_capability_catalog(),
    ).interpret("Запиши занятие завтра в 11")
    _, pending = DeterministicClarificationBuilder(
        catalog=default_home_capability_catalog(),
    ).build(frame, conversation_id="bounded-conversation")

    result = resolver.resolve_follow_up(
        "Давай в календарь",
        validator.vocabulary(),
        SemanticPendingContext.from_pending(pending),
    )

    assert result.proposal.selected_operation_id == "google_calendar.event.create"
    request = provider.last_request
    assert request.required_capabilities.structured_output is True
    assert request.required_capabilities.tools is False
    assert request.private_context == {}
    assert [message.content for message in request.messages[1:]] == [
        "Давай в календарь",
    ]
    system = request.messages[0].content
    assert pending.interpretation.original_utterance in system
    assert "known_slots" in system and "missing_slots" in system
    assert "selection_evidence_examples" not in system
    assert "selection_evidence_terms" not in system
    assert "Memory" not in system
    assert "credential" not in system.casefold()


def test_follow_up_timeout_is_controlled_and_cannot_patch_pending_state(tmp_path):
    provider, resolver, validator, _, _ = _boundaries(tmp_path)
    provider.simulate_timeout = True
    frame = CapabilityCandidateDiscovery(
        catalog=default_home_capability_catalog(),
    ).interpret("Запиши занятие завтра в 11")
    _, pending = DeterministicClarificationBuilder(
        catalog=default_home_capability_catalog(),
    ).build(frame, conversation_id="timeout-conversation")

    result = resolver.resolve_follow_up(
        "Лучше в Дом",
        validator.vocabulary(),
        SemanticPendingContext.from_pending(pending),
    )

    assert result.proposal is None
    assert result.failure is SemanticResolverFailure.TIMEOUT
    assert {item.name: item.value for item in pending.interpretation.slots} == {
        "date": "завтра",
        "time": "11:00",
        "subject": "занятие",
    }


def test_follow_up_operation_selection_evidence_must_be_grounded(tmp_path):
    _, _, validator, _, _ = _boundaries(tmp_path)
    frame = CapabilityCandidateDiscovery(
        catalog=default_home_capability_catalog(),
    ).interpret("Запиши занятие завтра в 11")
    _, pending = DeterministicClarificationBuilder(
        catalog=default_home_capability_catalog(),
    ).build(frame, conversation_id="selection-grounding")
    proposal = SemanticFollowUpProposal.model_validate({
        "relation": "follow_up",
        "selected_operation_id": "google_calendar.event.create",
        "operation_selection_evidence": "в календарь",
        "slot_updates": [],
        "referent_updates": [],
    })

    validated = validator.validate_follow_up(
        pending,
        "давай туда",
        proposal,
        date_resolver=validator.date_resolver,
    )

    assert validated.selected_operation_id is None
    assert validator.last_follow_up_trace.operation_selection.reason == (
        "follow_up_operation_selection_not_grounded"
    )


def test_word_time_is_validated_against_current_utterance(tmp_path):
    _, _, validator, _, _ = _boundaries(tmp_path)
    proposal = parse_semantic_interpretation(
        _schedule_proposal(
            candidates=["home.timed_commitments"],
            time="одиннадцать",
            action_evidence="надо не забыть",
            selection_evidence={
                "operation_id": "home.timed_commitments",
                "evidence_text": "надо не забыть",
            },
        )
    )

    frame = validator.validate(
        "Маш, у меня завтра в одиннадцать занятие, надо не забыть",
        proposal,
    )

    assert frame.resolution_state is InterpretationResolutionState.RESOLVED
    assert frame.slots[-1].value == "11:00"


def test_validator_rejects_an_unknown_operation_but_keeps_no_partial_authority(tmp_path):
    _, _, validator, _, _ = _boundaries(tmp_path)
    proposal = parse_semantic_interpretation(
        _schedule_proposal(candidates=["future.unknown"])
    )

    with pytest.raises(SemanticValidationError, match="unknown_operation"):
        validator.validate("Запиши занятие завтра в 11", proposal)


def test_model_cannot_invent_subject_or_resolved_referent(tmp_path):
    _, _, validator, _, _ = _boundaries(tmp_path)
    invented_subject = parse_semantic_interpretation(
        _schedule_proposal(
            candidates=["home.timed_commitments"], subject="стоматолог"
        )
    )
    invented_referent = SupportedActionProposal(
        kind="supported_action",
        candidate_operation_ids=("home.timed_commitments",),
        nearby_operation_ids=(),
        extracted_slots=(
            SemanticSlotProposal(name="subject", evidence_text="занятие"),
            SemanticSlotProposal(name="date", evidence_text="завтра"),
            SemanticSlotProposal(name="time", evidence_text="11"),
        ),
        unresolved_referents=("это",),
        ambiguity_hint=SemanticAmbiguityHint.REFERENT,
        action_request_evidence=ActionRequestEvidence(
            evidence_text="Напомни",
        ),
        operation_selection_evidence=OperationSelectionEvidence(
            operation_id=None,
            evidence_text=None,
        ),
    )

    subject_frame = validator.validate(
        "Запиши: у меня завтра в 11 занятие", invented_subject,
    )
    referent_frame = validator.validate(
        "Напомни: у меня завтра в 11 занятие", invented_referent,
    )

    assert "subject" in subject_frame.missing_slots
    assert all(item.name != "subject" for item in subject_frame.slots)
    assert referent_frame.referents == ()
    assert any(not item.accepted for item in validator.last_trace.referents)


def test_subject_provenance_rejects_supported_noun_with_invented_detail(tmp_path):
    _, _, validator, _, _ = _boundaries(tmp_path)
    proposal = parse_semantic_interpretation(
        _schedule_proposal(
            candidates=["home.timed_commitments"],
            subject="занятие с выдуманным преподавателем",
            action_evidence="Напомни",
        )
    )

    frame = validator.validate("Напомни: у меня завтра в 11 занятие", proposal)

    assert "subject" in frame.missing_slots
    assert any(
        item.name == "subject" and not item.accepted
        for item in validator.last_trace.slots
    )


@pytest.mark.parametrize(
    "response_text,simulate_timeout,failure",
    (
        ("not-json", False, SemanticResolverFailure.JSON_WIRE_ERROR),
        ("{}", False, SemanticResolverFailure.SCHEMA_ERROR),
        ("{}", True, SemanticResolverFailure.TIMEOUT),
    ),
)
def test_malformed_and_timeout_fail_to_deterministic_ordinary_path(
    tmp_path, response_text, simulate_timeout, failure
):
    provider = FakeProvider(
        provider_id="ollama-local",
        capabilities=ModelCapabilities(structured_output=True),
        response_text=response_text,
        simulate_timeout=simulate_timeout,
    )
    _, _, _, hybrid, _ = _boundaries(tmp_path, provider=provider)

    frame = hybrid.interpret("Доброе утро, Маша")

    assert frame.resolution_state is InterpretationResolutionState.ORDINARY_CONVERSATION
    assert hybrid.last_result.failure is failure


def test_invalid_mapping_kind_does_not_trigger_repair_calls(tmp_path):
    provider, resolver, validator, _, _ = _boundaries(tmp_path)
    provider.response_text = json.dumps({
        **_schedule_proposal(), "kind": "unsupported_action",
        "action_request_evidence": {"evidence_text": None},
    })
    result = resolver.resolve("Удали это письмо", validator.vocabulary(), turn_context=_presented_mail_context())
    assert result.proposal is None
    assert result.failure is SemanticResolverFailure.SCHEMA_ERROR
    assert len(provider.requests) == 2


def test_semantic_ordinary_conversation_remains_ordinary(tmp_path):
    provider, _, _, hybrid, _ = _boundaries(tmp_path)
    provider.response_text = json.dumps({
        "kind": "ordinary",
        "candidate_operation_ids": [],
        "nearby_operation_ids": [],
        "extracted_slots": [],
        "unresolved_referents": [],
        "ambiguity_hint": "none",
        "action_request_evidence": {"evidence_text": None},
        "operation_selection_evidence": {"operation_id": None, "evidence_text": None},
    })

    frame = hybrid.interpret("Как ты сегодня?")

    assert frame.resolution_state is InterpretationResolutionState.ORDINARY_CONVERSATION
    assert len(provider.requests) == 1


def test_clear_update_language_rejects_incorrect_create_without_inventing_update(tmp_path):
    provider, _, _, hybrid, _ = _boundaries(tmp_path)
    provider.response_text = json.dumps({
        "kind": "supported_action",
        "candidate_operation_ids": ["google_calendar.event.create"],
        "nearby_operation_ids": [],
        "extracted_slots": [
            {"name": "subject", "evidence_text": "созвон с мамой"},
            {"name": "date", "evidence_text": "завтра"},
            {"name": "time", "evidence_text": "14"},
        ],
        "unresolved_referents": [],
        "ambiguity_hint": "none",
        "action_request_evidence": {"evidence_text": "Перенеси"},
        "operation_selection_evidence": {
            "operation_id": "google_calendar.event.create",
            "evidence_text": "календаре",
        },
    }, ensure_ascii=False)

    frame = hybrid.interpret(
        "Перенеси в гугл календаре созвон с мамой завтра на 14:00"
    )

    assert frame.resolution_state is InterpretationResolutionState.UNSUPPORTED_ACTION
    assert frame.candidates == ()
    assert hybrid.last_rejection == "update_operation_kind_conflict"


@pytest.mark.parametrize(("utterance", "subject"), (
    ("Перенеси созвон с мамой завтра с 14 на 13", "созвон с мамой"),
    ("Перенеси завтра созвон с мамой с 14 на 13", "созвон с мамой"),
    ("Маш, перенеси завтра созвониться с мамой с 14 на 13 часов", "созвониться с мамой"),
    ("Завтра созвон с мамой перенеси с 14 на 13", "созвон с мамой"),
    ("Созвон с мамой завтра сдвинь на 13", "созвон с мамой"),
))
def test_explicit_update_meaning_cannot_degrade_to_timed_commitment(
    tmp_path, utterance, subject,
):
    provider, _, _, hybrid, _ = _boundaries(tmp_path)
    provider.response_text = json.dumps({
        "kind": "supported_action",
        "candidate_operation_ids": ["home.timed_commitments"],
        "nearby_operation_ids": [],
        "extracted_slots": [
            {"name": "subject", "evidence_text": subject},
            {"name": "date", "evidence_text": "завтра"},
            {"name": "time", "evidence_text": "13"},
            *(
                [{"name": "old_time", "evidence_text": "14"}]
                if "14" in utterance else []
            ),
        ],
        "unresolved_referents": [],
        "ambiguity_hint": "none",
        "action_request_evidence": {
            "evidence_text": (
                "перенеси" if "перенеси" in utterance.casefold() else "сдвинь"
            ),
        },
        "operation_selection_evidence": {
            "operation_id": "home.timed_commitments",
            "evidence_text": "перенеси" if "перенеси" in utterance.casefold() else "сдвинь",
        },
    }, ensure_ascii=False)

    frame = hybrid.interpret(utterance)

    assert frame.resolution_state is InterpretationResolutionState.UNSUPPORTED_ACTION
    assert frame.candidates == ()
    assert "home.timed_commitments" not in {
        item.operation_id for item in frame.candidates
    }
    assert "google_calendar.event.create" not in {
        item.operation_id for item in frame.candidates
    }


@pytest.mark.parametrize("utterance", (
    "Электронная почта сильно изменила общение",
    "Интернет изменил людей",
))
def test_factual_update_shaped_words_are_not_action_authority(tmp_path, utterance):
    provider, _, _, hybrid, _ = _boundaries(tmp_path)
    provider.response_text = json.dumps({
        "kind": "ordinary",
        "candidate_operation_ids": [],
        "nearby_operation_ids": [],
        "extracted_slots": [],
        "unresolved_referents": [],
        "ambiguity_hint": "none",
        "action_request_evidence": {"evidence_text": None},
        "operation_selection_evidence": {
            "operation_id": None,
            "evidence_text": None,
        },
    }, ensure_ascii=False)

    frame = hybrid.interpret(utterance)

    assert frame.resolution_state is InterpretationResolutionState.ORDINARY_CONVERSATION
    assert frame.candidates == ()
    assert hybrid.last_rejection is None


def test_vocabulary_describes_slots_and_home_defaults_without_authorization(tmp_path):
    _, _, validator, _, _ = _boundaries(tmp_path)
    calendar = next(
        item for item in validator.vocabulary()
        if item.operation_id == "google_calendar.event.create"
    )

    duration = next(item for item in calendar.slots if item.name == "duration_minutes")

    assert calendar.purpose
    assert calendar.operation_kind == "create"
    assert calendar.selection_evidence_meaning
    assert "в календарь" in calendar.selection_evidence_examples
    assert duration.required is False
    assert duration.default_value == "60"


@pytest.mark.parametrize("nearby", ((), ("google_calendar.event.create", "home.timed_commitments")))
def test_semantic_explicit_unsupported_action_stays_distinct_from_conversation(tmp_path, nearby):
    provider, _, validator, hybrid, _ = _boundaries(tmp_path)
    proposal = UnsupportedActionProposal(
        kind="unsupported_action",
        candidate_operation_ids=(),
        nearby_operation_ids=nearby,
        extracted_slots=(),
        unresolved_referents=(),
        ambiguity_hint="none",
        action_request_evidence=ActionRequestEvidence(evidence_text="Запиши"),
        operation_selection_evidence=OperationSelectionEvidence(
            operation_id=None,
            evidence_text=None,
        ),
    )

    frame = validator.validate(
        "Запиши меня на внешнее занятие завтра в 9",
        proposal,
    )

    assert frame.resolution_state is InterpretationResolutionState.UNSUPPORTED_ACTION
    assert frame.candidates == ()
    assert frame.slots == ()
    provider.response_text = proposal.model_dump_json()
    hybrid_frame = hybrid.interpret("Запиши меня на внешнее занятие завтра в 9")
    assert hybrid_frame.resolution_state is InterpretationResolutionState.UNSUPPORTED_ACTION


def test_ordinary_classification_does_not_get_a_second_legacy_action_chance(tmp_path):
    provider, _, _, hybrid, _ = _boundaries(tmp_path)
    provider.response_text = json.dumps({
        "kind": "ordinary",
        "candidate_operation_ids": [],
        "nearby_operation_ids": [],
        "extracted_slots": [],
        "unresolved_referents": [],
        "ambiguity_hint": "none",
        "action_request_evidence": {"evidence_text": None},
        "operation_selection_evidence": {"operation_id": None, "evidence_text": None},
    })

    frame = hybrid.interpret(
        "Поставь встречу в календарь завтра в 19 на час"
    )

    assert not frame.candidates
    assert frame.resolution_state is InterpretationResolutionState.ORDINARY_CONVERSATION
    assert len(provider.requests) == 1
    assert hybrid.last_rejection is None


def test_docs_content_stays_structural_but_external_information_reaches_semantics(tmp_path):
    class ExplodingResolver:
        def resolve(self, *_args, **_kwargs):
            raise AssertionError("protected deterministic ownership")

    catalog = default_home_capability_catalog()
    deterministic = CapabilityCandidateDiscovery(catalog=catalog)
    adoption = V2LiveAdoptionPolicy()
    validator = SemanticProposalValidator(
        catalog=catalog,
        specifications=deterministic.specifications,
        known_operation_ids=frozenset(deterministic.specifications.operation_ids),
    )
    hybrid = HybridCapabilityCandidateDiscovery(
        deterministic=deterministic,
        resolver=ExplodingResolver(),
        validator=validator,
    )

    docs = hybrid.interpret(
        "Создай документ на Гугл Диске: Сегодня мы продолжили делать наш Дом"
    )
    assert [item.operation_id for item in docs.candidates] == [
        "google_drive.document.create"
    ]

    class OrdinaryResolver:
        calls = 0
        def resolve(self, *_args, **_kwargs):
            self.calls += 1
            return SemanticResolverResult(
                proposal=parse_semantic_interpretation({
                    "kind": "ordinary",
                    "candidate_operation_ids": [],
                    "nearby_operation_ids": [],
                    "extracted_slots": [],
                    "unresolved_referents": [],
                    "ambiguity_hint": "none",
                    "action_request_evidence": {"evidence_text": None},
                    "operation_selection_evidence": {
                        "operation_id": None, "evidence_text": None,
                    },
                }),
                latency_ms=1,
            )

    resolver = OrdinaryResolver()
    hybrid.resolver = resolver
    web = hybrid.interpret("Поищи в интернете последнюю версию Ollama")

    assert resolver.calls == 1
    assert web.resolution_state is InterpretationResolutionState.ORDINARY_CONVERSATION


def test_model_role_can_switch_profile_without_router_code_change(tmp_path):
    _, _, _, _, roles = _boundaries(tmp_path)

    selected = roles.assign(ModelRole.SEMANTIC_RESOLVER, "fast")

    assert selected.model_id == roles.profiles.get_profile("fast").model_id
    restarted = ModelRoleProfileStore(roles.path, profiles=roles.profiles)
    assert restarted.profile_for(ModelRole.SEMANTIC_RESOLVER).profile_id == "fast"

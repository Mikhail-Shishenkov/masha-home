import json
from datetime import datetime, timedelta, timezone

import pytest

from backend.application.home_capabilities import default_home_capability_catalog
from backend.conversation.clarification import (
    DeterministicClarificationBuilder,
    FollowUpOutcome,
    FollowUpResolutionEngine,
)
from backend.conversation.interpretation_v2 import (
    CapabilityCandidateDiscovery,
    InterpretationSlot,
    InterpretationValueOrigin,
)
from backend.conversation.pending_resolution import (
    PendingResolutionConflictError,
    PendingResolutionStatus,
    PendingResolutionStore,
    PendingResolutionStoreCorruptError,
    PendingResolutionTransitionError,
)


class MutableClock:
    def __init__(self, value: datetime):
        self.value = value

    def __call__(self) -> datetime:
        return self.value


def _pending(clock: MutableClock, *, resolution_id: str, conversation_id: str = "conversation-1"):
    catalog = default_home_capability_catalog()
    frame = CapabilityCandidateDiscovery(catalog=catalog).interpret(
        "Запиши занятие завтра в 10 на час"
    )
    return DeterministicClarificationBuilder(
        catalog=catalog,
        clock=clock,
        resolution_id_factory=lambda: resolution_id,
    ).build(frame, conversation_id=conversation_id)[1]


def test_pending_is_active_before_ttl_and_deterministically_expires_after_it(tmp_path):
    clock = MutableClock(datetime(2026, 8, 27, 12, 0, tzinfo=timezone.utc))
    pending = _pending(
        clock,
        resolution_id="00000000-0000-0000-0000-000000000031",
    )
    store = PendingResolutionStore(tmp_path / "pending-resolutions.json", clock=clock)
    store.save(pending)

    clock.value += timedelta(minutes=29, seconds=59)
    assert store.active_for_conversation("conversation-1") == pending

    clock.value += timedelta(seconds=2)
    assert store.active_for_conversation("conversation-1") is None
    expired = store.get(pending.resolution_id)
    assert expired is not None
    assert expired.status is PendingResolutionStatus.EXPIRED
    assert expired.terminal_reason == "ttl_expired"


def test_expired_resolution_cannot_be_resolved_or_return_to_pending(tmp_path):
    clock = MutableClock(datetime(2026, 8, 27, 12, 0, tzinfo=timezone.utc))
    pending = _pending(
        clock,
        resolution_id="00000000-0000-0000-0000-000000000032",
    )
    store = PendingResolutionStore(tmp_path / "pending-resolutions.json", clock=clock)
    store.save(pending)
    result = FollowUpResolutionEngine().resolve(pending, "в календарь")
    clock.value += timedelta(minutes=31)

    with pytest.raises(PendingResolutionTransitionError):
        store.resolve(pending.resolution_id, result.interpretation)
    with pytest.raises(PendingResolutionTransitionError):
        store.cancel(pending.resolution_id)
    assert store.get(pending.resolution_id).status is PendingResolutionStatus.EXPIRED


def test_one_active_per_conversation_and_explicit_new_save_supersedes_old(tmp_path):
    clock = MutableClock(datetime(2026, 8, 27, 12, 0, tzinfo=timezone.utc))
    first = _pending(
        clock,
        resolution_id="00000000-0000-0000-0000-000000000033",
    )
    clock.value += timedelta(minutes=1)
    second = _pending(
        clock,
        resolution_id="00000000-0000-0000-0000-000000000034",
    )
    store = PendingResolutionStore(tmp_path / "pending-resolutions.json", clock=clock)
    store.save(first)

    with pytest.raises(PendingResolutionConflictError):
        store.save(second)
    store.save(second, supersede_active=True)

    assert store.get(first.resolution_id).status is PendingResolutionStatus.SUPERSEDED
    assert store.get(first.resolution_id).terminal_reason == "superseded_by_new_resolution"
    assert store.active_for_conversation("conversation-1") == second
    with pytest.raises(PendingResolutionTransitionError):
        store.cancel(first.resolution_id)


def test_cancelled_and_resolved_terminal_records_are_immutable(tmp_path):
    clock = MutableClock(datetime(2026, 8, 27, 12, 0, tzinfo=timezone.utc))
    cancelled = _pending(
        clock,
        resolution_id="00000000-0000-0000-0000-000000000035",
        conversation_id="cancelled-conversation",
    )
    resolved = _pending(
        clock,
        resolution_id="00000000-0000-0000-0000-000000000036",
        conversation_id="resolved-conversation",
    )
    store = PendingResolutionStore(tmp_path / "pending-resolutions.json", clock=clock)
    store.save(cancelled)
    store.save(resolved)
    store.cancel(cancelled.resolution_id)
    resolution = FollowUpResolutionEngine().resolve(resolved, "в календарь")
    stored = store.resolve(resolved.resolution_id, resolution.interpretation)

    assert stored.status is PendingResolutionStatus.RESOLVED
    for resolution_id in (cancelled.resolution_id, resolved.resolution_id):
        with pytest.raises(PendingResolutionTransitionError):
            store.supersede(resolution_id)


def test_restart_between_question_and_reply_recovers_same_frame_and_resolves(tmp_path):
    clock = MutableClock(datetime(2026, 8, 27, 12, 0, tzinfo=timezone.utc))
    path = tmp_path / "pending-resolutions.json"
    pending = _pending(
        clock,
        resolution_id="00000000-0000-0000-0000-000000000037",
    )
    PendingResolutionStore(path, clock=clock).save(pending)

    recovered_store = PendingResolutionStore(path, clock=clock)
    recovered = recovered_store.active_for_conversation("conversation-1")
    result = FollowUpResolutionEngine().resolve(recovered, "В календарь")
    final = recovered_store.resolve(recovered.resolution_id, result.interpretation)

    assert result.outcome is FollowUpOutcome.RESOLVED
    assert final.resolution_id == pending.resolution_id
    assert final.status is PendingResolutionStatus.RESOLVED
    assert final.interpretation.original_utterance == pending.interpretation.original_utterance
    assert {slot.name: slot.value for slot in final.interpretation.slots} == {
        "date": "завтра",
        "time": "10:00",
        "duration_minutes": "60",
        "subject": "занятие",
    }


def test_store_is_versioned_bounded_and_compacts_old_terminal_records(tmp_path):
    clock = MutableClock(datetime(2026, 8, 27, 12, 0, tzinfo=timezone.utc))
    path = tmp_path / "pending-resolutions.json"
    store = PendingResolutionStore(
        path,
        clock=clock,
        max_records=2,
        terminal_retention=1,
    )
    ids = [
        "00000000-0000-0000-0000-000000000041",
        "00000000-0000-0000-0000-000000000042",
    ]
    for index, resolution_id in enumerate(ids):
        pending = _pending(
            clock,
            resolution_id=resolution_id,
            conversation_id=f"conversation-{index}",
        )
        store.save(pending)
        store.cancel(resolution_id)
        clock.value += timedelta(minutes=1)

    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["schema_version"] == "2.0"
    assert [item["resolution_id"] for item in payload["resolutions"]] == [ids[-1]]


def test_version_one_question_shape_migrates_to_first_class_active_question(tmp_path):
    clock = MutableClock(datetime(2026, 8, 27, 12, 0, tzinfo=timezone.utc))
    path = tmp_path / "pending-resolutions.json"
    pending = _pending(
        clock,
        resolution_id="00000000-0000-0000-0000-000000000049",
    )
    row = pending.model_dump(mode="json")
    question = row.pop("active_question")
    row.update({
        "clarification_kind": question["kind"],
        "choices": question["choices"],
        "requested_slot": question["requested_slot"],
        "referent_expression": question["referent_expression"],
    })
    path.write_text(
        json.dumps({"schema_version": "1.0", "resolutions": [row]}, ensure_ascii=False),
        encoding="utf-8",
    )

    recovered = PendingResolutionStore(path, clock=clock).active_for_conversation(
        "conversation-1"
    )

    assert recovered.resolution_id == pending.resolution_id
    assert recovered.active_question.kind.value == "capability"
    assert recovered.active_question.choices == pending.active_question.choices


def test_corrupt_store_is_reported_and_never_silently_discarded(tmp_path):
    path = tmp_path / "pending-resolutions.json"
    path.write_text('{"schema_version":"1.0","resolutions":[', encoding="utf-8")
    store = PendingResolutionStore(path)

    with pytest.raises(PendingResolutionStoreCorruptError):
        store.active_for_conversation("conversation-1")


def test_expire_due_and_explicit_supersede_transitions_are_observable(tmp_path):
    clock = MutableClock(datetime(2026, 8, 27, 12, 0, tzinfo=timezone.utc))
    first = _pending(
        clock,
        resolution_id="00000000-0000-0000-0000-000000000043",
        conversation_id="first",
    )
    second = _pending(
        clock,
        resolution_id="00000000-0000-0000-0000-000000000044",
        conversation_id="second",
    )
    store = PendingResolutionStore(tmp_path / "pending-resolutions.json", clock=clock)
    store.save(first)
    store.save(second)
    superseded = store.supersede(first.resolution_id)
    clock.value += timedelta(minutes=31)

    assert store.expire_due() == 1
    assert superseded.status is PendingResolutionStatus.SUPERSEDED
    assert store.get(second.resolution_id).status is PendingResolutionStatus.EXPIRED


def test_atomic_replace_failure_preserves_previous_document_and_cleans_temp(tmp_path, monkeypatch):
    clock = MutableClock(datetime(2026, 8, 27, 12, 0, tzinfo=timezone.utc))
    path = tmp_path / "pending-resolutions.json"
    pending = _pending(
        clock,
        resolution_id="00000000-0000-0000-0000-000000000045",
    )
    store = PendingResolutionStore(path, clock=clock)
    store.save(pending)
    original = path.read_bytes()

    def fail_replace(source, destination):
        raise OSError("simulated atomic replace failure")

    monkeypatch.setattr("backend.conversation.pending_resolution.os.replace", fail_replace)
    with pytest.raises(OSError, match="simulated atomic replace failure"):
        store.cancel(pending.resolution_id)

    assert path.read_bytes() == original
    assert not path.with_suffix(path.suffix + ".tmp").exists()


def test_store_rejects_a_patch_that_changes_known_slots_or_fakes_resolution(tmp_path):
    clock = MutableClock(datetime(2026, 8, 27, 12, 0, tzinfo=timezone.utc))
    pending = _pending(
        clock,
        resolution_id="00000000-0000-0000-0000-000000000046",
    )
    store = PendingResolutionStore(tmp_path / "pending-resolutions.json", clock=clock)
    store.save(pending)
    legitimate = FollowUpResolutionEngine().resolve(pending, "в календарь").interpretation
    tampered_slots = tuple(
        InterpretationSlot(
            name=slot.name,
            value="20:00",
            origin=InterpretationValueOrigin.EXPLICIT,
        )
        if slot.name == "time"
        else slot
        for slot in legitimate.slots
    )
    tampered = legitimate.model_copy(update={"slots": tampered_slots})

    with pytest.raises(PendingResolutionTransitionError, match="known slot"):
        store.resolve(pending.resolution_id, tampered)


def test_partial_slot_progress_persists_next_dimension_across_restart(tmp_path):
    clock = MutableClock(datetime(2026, 8, 27, 12, 0, tzinfo=timezone.utc))
    path = tmp_path / "pending-resolutions.json"
    catalog = default_home_capability_catalog()
    builder = DeterministicClarificationBuilder(
        catalog=catalog,
        clock=clock,
        resolution_id_factory=lambda: "00000000-0000-0000-0000-000000000047",
    )
    frame = CapabilityCandidateDiscovery(catalog=catalog).interpret("Поставь в календарь")
    _, pending = builder.build(frame, conversation_id="conversation-1")
    store = PendingResolutionStore(path, clock=clock)
    store.save(pending)

    partial = FollowUpResolutionEngine().resolve(pending, "Занятие по AI")
    next_request = builder.build_request(
        partial.interpretation,
        conversation_id=pending.conversation_id,
        resolution_id=pending.resolution_id,
    )
    store.update_pending(
        pending.resolution_id,
        partial.interpretation,
        clarification_kind=next_request.clarification_kind,
        choices=next_request.choices,
        requested_slot=next_request.requested_slot,
        referent_expression=next_request.referent_expression,
    )

    recovered = PendingResolutionStore(path, clock=clock).active_for_conversation(
        "conversation-1"
    )
    assert partial.outcome is FollowUpOutcome.STILL_UNRESOLVED
    assert recovered.resolution_id == pending.resolution_id
    assert recovered.requested_slot == "date"
    assert {slot.name: slot.value for slot in recovered.interpretation.slots} == {
        "subject": "Занятие по AI"
    }

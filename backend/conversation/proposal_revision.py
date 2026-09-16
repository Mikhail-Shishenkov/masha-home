"""Shared meaning validation for unconfirmed drafts; no dialogue state."""

from backend.memory.memory_models import Commitment, ReminderDeliveryMode
from backend.temporal.date_resolution import HomeCalendarDateResolver
from .interpretation_v2 import (
    CandidateEvidence, CapabilityCandidate, InterpretationFrame,
    InterpretationSlot, InterpretationValueOrigin,
)
from .semantic_resolver import (
    SemanticFollowUpRelation, SemanticKnownSlot, SemanticPendingContext,
)


def revise_pending_reminder(handler, proposal, message: str, *, engine) -> str | None:
    """Reuse the existing semantic wire and Home validator, not another router.

    The current application proposal supplies all prior values. No terminal
    clarification is reopened, no operation ID or mutation handle reaches the
    model, and only the existing reminder owner may replace the draft.
    """
    if (
        proposal.record_type != "commitment" or proposal.operation != "create"
        or handler.is_proposal_decision(message)
        or engine.semantic_resolver is None or engine.semantic_validator is None
    ):
        return None
    try:
        record = Commitment.model_validate(proposal.record_payload)
    except ValueError:
        return "Не смогла прочитать это предложение напоминания. Ничего не сохраняю."
    if record.due_at is None or record.reminder_delivery_mode is not ReminderDeliveryMode.EXPLICIT_USER_REMINDER:
        return None
    due = record.due_at.astimezone(handler.temporal_engine.home_timezone.tzinfo)
    values = {"subject": record.text, "date": due.date().isoformat(), "time": due.strftime("%H:%M")}
    unchanged = (
        f"Пока оставила предложение без изменений: напомнить {record.text} — "
        f"{due:%d.%m.%Y %H:%M}. Уточни правку или подтверди этот вариант."
    )
    try:
        revised = _validated_revision(
            values, "home.timed_commitments", message, engine=engine,
            temporal_engine=handler.temporal_engine,
        )
        if revised is None:
            return None
        if revised == values:
            return unchanged
        return handler.revise_timed_commitment_proposal(proposal, **revised)
    except (ValueError, OSError):
        engine.last_semantic_rejection = "draft_revision_unavailable"
        return unchanged


def revise_pending_calendar(service, proposal, message, *, engine, temporal_engine):
    if engine.semantic_resolver is None or engine.semantic_validator is None:
        return None
    from backend.connectors.google_calendar.draft_revision import calendar_draft, replace_calendar_draft

    try:
        values = calendar_draft(service, proposal)[2]
    except ValueError:
        return "Это действие уже запускалось или его черновик недоступен. Не меняю его как новое предложение."
    try:
        operation_id = "google_calendar.event.create" if proposal.operation == "google_calendar_create" else "google_calendar.event.update"
        revised = _validated_revision(
            values, operation_id, message, engine=engine, temporal_engine=temporal_engine,
        )
        if revised is None:
            return None
        if revised != values:
            return replace_calendar_draft(
                service, proposal, revised, now_local=temporal_engine.context(None).current_local_time,
            )
    except (ValueError, OSError):
        engine.last_semantic_rejection = "draft_revision_unavailable"
    return (
        f"Предложение пока не изменилось: «{values['subject']}» — {values['date']} "
        f"в {values['time']}, на {values['duration_minutes']} мин. "
        "Уточни правку или подтверди этот вариант. Ничего в календаре не меняла."
    )


def _validated_revision(values, operation_id, message, *, engine, temporal_engine):
    validator = engine.semantic_validator
    engine.last_semantic_rejection = None
    engine.last_semantic_result = None
    try:
        frame = InterpretationFrame(
            original_utterance=f"Предложение: {values['subject']}", resolution_state="resolved",
            candidates=(CapabilityCandidate(
                operation_id=operation_id, slot_names=tuple(values),
                evidence=(CandidateEvidence(signal="existing unconfirmed application draft"),),
            ),),
            slots=tuple(InterpretationSlot(
                name=name, value=value, origin=InterpretationValueOrigin.EXPLICIT,
            ) for name, value in values.items()),
        )
        context = SemanticPendingContext(
            original_utterance=frame.original_utterance,
            candidate_operation_ids=(operation_id,),
            known_slots=tuple(SemanticKnownSlot(name=k, value=v) for k, v in values.items()),
            clarification_kind="proposal_revision",
        )
        result = engine.semantic_resolver.resolve_follow_up(message, validator.vocabulary(), context)
        engine.last_semantic_result = result
        if result.proposal is None:
            engine.last_semantic_rejection = result.failure.value
            raise ValueError("semantic revision unavailable")
        update = validator.validate_frame_follow_up(
            frame, message, result.proposal,
            date_resolver=HomeCalendarDateResolver(temporal_engine),
        )
        if update.relation is SemanticFollowUpRelation.NOT_A_FOLLOW_UP:
            return None
        trace = validator.last_follow_up_trace
        if (
            result.proposal.selected_operation_id is not None
            or result.proposal.referent_updates
            or any(not item.accepted for item in trace.slots)
            or any(item.slot.name not in values for item in update.slot_updates)
        ):
            engine.last_semantic_rejection = "draft_revision_rejected"
            raise ValueError("draft revision rejected")
        revised = {**values, **{item.slot.name: item.slot.value for item in update.slot_updates}}
        return revised
    except (ValueError, OSError):
        engine.last_semantic_rejection = "draft_revision_unavailable"
        raise

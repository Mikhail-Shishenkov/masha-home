"""Local revision of pristine Calendar proposals, never provider execution."""

from datetime import timedelta
from uuid import uuid4
from zoneinfo import ZoneInfo

from backend.conversation.memory_intent import MemoryProposal, ProposalStatus
from .intent import calendar_create_from_resolved_slots


def calendar_draft(service, proposal):
    writer = service.writer if proposal.operation == "google_calendar_create" else service.updater
    receipt = writer.receipt_store.get(proposal.record_payload.get("operation_id"))
    if (
        proposal.status is not ProposalStatus.PENDING
        or service.proposal_store.current_for_conversation(proposal.conversation_id) != proposal
        or receipt is None or receipt.status != "proposed"
        or receipt.confirmed_at is not None or receipt.verified_at is not None
        or receipt.operation.model_dump(mode="json") != proposal.record_payload
    ):
        raise ValueError("not a pristine Calendar draft")
    operation = receipt.operation
    desired = operation if proposal.operation == "google_calendar_create" else operation.desired
    start = desired.start.astimezone(ZoneInfo(operation.home_timezone))
    values = {
        "subject": desired.title, "date": start.date().isoformat(), "time": start.strftime("%H:%M"),
        "duration_minutes": str(int((desired.end - desired.start).total_seconds() // 60)),
    }
    return writer, receipt, values


def replace_calendar_draft(service, proposal, values, *, now_local):
    writer, receipt, old_values = calendar_draft(service, proposal)
    old = receipt.operation
    creating = proposal.operation == "google_calendar_create"
    # The update target is already a real bound event. A subject correction
    # cannot silently select a different provider object (or rename this one).
    if not creating and values["subject"] != old_values["subject"]:
        raise ValueError("changing a bound target requires a new lookup")
    duration = int(values["duration_minutes"])
    if not 1 <= duration <= 1440:
        raise ValueError("invalid duration")
    intent = calendar_create_from_resolved_slots(
        subject=values["subject"], date=values["date"], time_value=values["time"],
        duration=timedelta(minutes=duration), now_local=now_local.astimezone(ZoneInfo(old.home_timezone)),
    )
    if intent.clarification is not None:
        raise ValueError("incomplete revision")
    state = {"title": intent.title, "start": intent.start, "end": intent.end}
    operation = type(old).model_validate({
        **old.model_dump(mode="python"), "operation_id": str(uuid4()),
        **(state if creating else {"desired": state}),
    })
    revised_receipt = type(receipt).model_validate({
        **receipt.model_dump(mode="python"), "operation": operation,
        **({"provider_event_id": operation.provider_event_id()} if creating else {}),
    })
    replacement = MemoryProposal.model_validate({
        **proposal.model_dump(mode="python"), "id": str(uuid4()),
        "record_payload": operation.model_dump(mode="json"), "created_at": now_local,
    })
    # Persist evidence before publishing its preview. A crash before the atomic
    # swap leaves the old preview usable; an orphan receipt grants no authority.
    writer.receipt_store.put(revised_receipt)
    service.proposal_store.replace_pending(proposal, replacement)
    try:
        writer.reject(old)
    except OSError:
        # The obsolete proposal is already durably cancelled. Its old ID can
        # no longer authorize anything, even if audit retirement cannot finish.
        pass
    prefix = "Поставить" if creating else "Перенести"
    return (
        f"{prefix} «{intent.title}» в Основном календаре: "
        f"{intent.start:%d.%m.%Y в %H:%M}–{intent.end:%H:%M}? "
        "Изменила только предложение. Подтверждаешь?"
    )

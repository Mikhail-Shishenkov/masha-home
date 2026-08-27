import pytest

from backend.application.capability_catalog import (
    CapabilityAvailability,
    CapabilityCatalog,
    CapabilityDescriptor,
    CapabilityEffect,
    CapabilityNotFoundError,
    CapabilityOperationKind,
    CapabilityRisk,
    DuplicateCapabilityError,
)


def _descriptor(operation_id: str) -> CapabilityDescriptor:
    return CapabilityDescriptor(
        operation_id=operation_id,
        display_name="Отправить сообщение Мише",
        family="telegram",
        kind=CapabilityOperationKind.CREATE,
        effect=CapabilityEffect.EXTERNAL_MUTATION,
        risk=CapabilityRisk.CONSEQUENTIAL,
        verification_required=True,
        proactive_eligible=False,
        agent_eligible=False,
    )


def test_synthetic_future_operation_extends_catalog_without_central_snapshot_field():
    descriptor = _descriptor("telegram.send_to_misha")
    catalog = CapabilityCatalog()

    catalog.register(descriptor)
    snapshot = catalog.snapshot({descriptor.operation_id: CapabilityAvailability.BLOCKED})

    assert catalog.descriptors() == (descriptor,)
    assert snapshot.get("telegram.send_to_misha").availability is CapabilityAvailability.BLOCKED
    assert snapshot.operations[0].operation == descriptor


def test_catalog_registration_and_available_state_do_not_execute_or_grant_authority():
    side_effects = []
    catalog = CapabilityCatalog((_descriptor("telegram.send_to_misha"),))

    snapshot = catalog.snapshot({"telegram.send_to_misha": "available"})

    assert side_effects == []
    assert snapshot.get("telegram.send_to_misha").availability is CapabilityAvailability.AVAILABLE
    assert not hasattr(catalog, "execute")
    assert not hasattr(catalog, "authorize")
    assert not hasattr(snapshot, "permission")


def test_duplicate_and_unknown_operation_ids_fail_deterministically():
    descriptor = _descriptor("telegram.send_to_misha")
    catalog = CapabilityCatalog((descriptor,))

    with pytest.raises(DuplicateCapabilityError, match="telegram.send_to_misha"):
        catalog.register(descriptor)
    with pytest.raises(CapabilityNotFoundError, match="telegram.unknown"):
        catalog.get("telegram.unknown")
    with pytest.raises(CapabilityNotFoundError, match="telegram.unknown"):
        catalog.snapshot({"telegram.unknown": "available"})


def test_catalog_enumeration_is_stable_and_unreported_state_is_unavailable():
    send = _descriptor("telegram.send_to_misha")
    receive = _descriptor("telegram.receive")
    catalog = CapabilityCatalog((send, receive))

    snapshot = catalog.snapshot({"telegram.send_to_misha": "available"})

    assert [item.operation.operation_id for item in snapshot.operations] == [
        "telegram.receive",
        "telegram.send_to_misha",
    ]
    assert snapshot.get("telegram.receive").availability is CapabilityAvailability.UNAVAILABLE

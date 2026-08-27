"""Descriptive catalog of operations known to Masha Home.

Discovery is not authority: this module cannot execute an operation, inspect
credentials, or grant permission.  Runtime availability is only a projection
of whether Home currently has an operation in a usable state.
"""

from __future__ import annotations

from enum import Enum
from typing import Iterable, Mapping

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictCapabilityModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class CapabilityAvailability(str, Enum):
    AVAILABLE = "available"
    BLOCKED = "blocked"
    NEEDS_RECONNECT = "needs_reconnect"
    UNAVAILABLE = "unavailable"


class CapabilityOperationKind(str, Enum):
    OBSERVE = "observe"
    READ = "read"
    CREATE = "create"
    UPDATE = "update"
    MANAGE = "manage"


class CapabilityEffect(str, Enum):
    READ_ONLY = "read_only"
    LOCAL_MUTATION = "local_mutation"
    EXTERNAL_MUTATION = "external_mutation"


class CapabilityRisk(str, Enum):
    OBSERVE = "observe"
    REVERSIBLE = "reversible"
    CONSEQUENTIAL = "consequential"


class CapabilityDescriptor(StrictCapabilityModel):
    """Stable metadata for one operation; every field is non-authoritative."""

    operation_id: str = Field(
        pattern=r"^[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+$",
        max_length=100,
    )
    display_name: str = Field(min_length=3, max_length=120)
    family: str = Field(pattern=r"^[a-z][a-z0-9_]{1,63}$")
    kind: CapabilityOperationKind
    effect: CapabilityEffect
    risk: CapabilityRisk
    verification_required: bool = False
    proactive_eligible: bool = False
    agent_eligible: bool = False

    @model_validator(mode="after")
    def mutation_risk_is_not_understated(self):
        if self.effect is CapabilityEffect.EXTERNAL_MUTATION and self.risk is not CapabilityRisk.CONSEQUENTIAL:
            raise ValueError("external mutation capability must be consequential")
        if self.effect is CapabilityEffect.LOCAL_MUTATION and self.risk is CapabilityRisk.OBSERVE:
            raise ValueError("local mutation capability cannot be observe-only")
        return self


class CapabilityState(StrictCapabilityModel):
    operation: CapabilityDescriptor
    availability: CapabilityAvailability


class CapabilityCatalogSnapshot(StrictCapabilityModel):
    operations: tuple[CapabilityState, ...] = ()

    @model_validator(mode="after")
    def operation_ids_are_unique(self):
        operation_ids = [item.operation.operation_id for item in self.operations]
        if len(operation_ids) != len(set(operation_ids)):
            raise ValueError("capability snapshot contains duplicate operation IDs")
        return self

    def get(self, operation_id: str) -> CapabilityState:
        match = next(
            (item for item in self.operations if item.operation.operation_id == operation_id),
            None,
        )
        if match is None:
            raise CapabilityNotFoundError(operation_id)
        return match


class CapabilityCatalogError(RuntimeError):
    pass


class DuplicateCapabilityError(CapabilityCatalogError):
    pass


class CapabilityNotFoundError(CapabilityCatalogError):
    pass


class CapabilityCatalog:
    """Pure descriptive registry. It provides neither execution nor authority."""

    def __init__(self, descriptors: Iterable[CapabilityDescriptor] = ()):
        self._descriptors: dict[str, CapabilityDescriptor] = {}
        for descriptor in descriptors:
            self.register(descriptor)

    def register(self, descriptor: CapabilityDescriptor) -> CapabilityDescriptor:
        if descriptor.operation_id in self._descriptors:
            raise DuplicateCapabilityError(descriptor.operation_id)
        self._descriptors[descriptor.operation_id] = descriptor
        return descriptor

    def descriptors(self) -> tuple[CapabilityDescriptor, ...]:
        return tuple(self._descriptors[key] for key in sorted(self._descriptors))

    def get(self, operation_id: str) -> CapabilityDescriptor:
        try:
            return self._descriptors[operation_id]
        except KeyError as error:
            raise CapabilityNotFoundError(operation_id) from error

    def snapshot(
        self,
        availability: Mapping[str, CapabilityAvailability | str],
    ) -> CapabilityCatalogSnapshot:
        unknown = sorted(set(availability) - set(self._descriptors))
        if unknown:
            raise CapabilityNotFoundError(unknown[0])
        return CapabilityCatalogSnapshot(
            operations=tuple(
                CapabilityState(
                    operation=descriptor,
                    availability=CapabilityAvailability(
                        availability.get(
                            descriptor.operation_id,
                            CapabilityAvailability.UNAVAILABLE,
                        )
                    ),
                )
                for descriptor in self.descriptors()
            )
        )

"""Small application-owned contracts for consequential action preparation.

These values describe what Home actually prepared. They carry no proposal
identifier, provider identifier, credential, or authority to execute.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ProposalPreparationStatus(str, Enum):
    PENDING_CONFIRMATION = "pending_confirmation"
    NO_ACTION = "no_action"


class ProposalPreparation(BaseModel):
    """Truth at the application proposal boundary, before confirmation."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    response: str = Field(min_length=1, max_length=2000)
    status: ProposalPreparationStatus
    application_operation: str | None = Field(
        default=None,
        min_length=1,
        max_length=100,
    )

    @model_validator(mode="after")
    def operation_matches_status(self):
        if (
            self.status is ProposalPreparationStatus.PENDING_CONFIRMATION
            and self.application_operation is None
        ):
            raise ValueError("pending confirmation requires an application operation")
        if (
            self.status is ProposalPreparationStatus.NO_ACTION
            and self.application_operation is not None
        ):
            raise ValueError("no-action preparation cannot name a pending operation")
        return self

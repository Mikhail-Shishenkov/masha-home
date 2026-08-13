from __future__ import annotations

from enum import Enum
from typing import Annotated

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator


NonEmptyStr = Annotated[str, Field(min_length=1)]


class ConversationRole(str, Enum):
    USER = "user"
    ASSISTANT = "assistant"


class ConversationMessageOrigin(str, Enum):
    """Authorship boundary for persisted transcript messages."""

    USER = "user"
    MODEL = "model"
    APPLICATION = "application"


class ConversationMessage(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: NonEmptyStr
    role: ConversationRole
    content: NonEmptyStr
    created_at: AwareDatetime
    conversation_id: NonEmptyStr
    origin: ConversationMessageOrigin

    @model_validator(mode="before")
    @classmethod
    def infer_legacy_origin(cls, value):
        """Old histories had only roles; preserve them without a migration."""
        if isinstance(value, dict) and "origin" not in value:
            value = dict(value)
            value["origin"] = (
                ConversationMessageOrigin.USER.value
                if value.get("role") == ConversationRole.USER.value
                else ConversationMessageOrigin.MODEL.value
            )
        return value


class Conversation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: NonEmptyStr
    created_at: AwareDatetime

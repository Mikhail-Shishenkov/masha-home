from __future__ import annotations

from enum import Enum
from typing import Annotated

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field


NonEmptyStr = Annotated[str, Field(min_length=1)]


class ConversationRole(str, Enum):
    USER = "user"
    ASSISTANT = "assistant"


class ConversationMessage(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: NonEmptyStr
    role: ConversationRole
    content: NonEmptyStr
    created_at: AwareDatetime
    conversation_id: NonEmptyStr


class Conversation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: NonEmptyStr
    created_at: AwareDatetime


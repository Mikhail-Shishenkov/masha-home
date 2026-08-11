from enum import Enum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, JsonValue, model_validator

from backend.identity.identity_models import IdentityContext


NonEmptyStr = Annotated[str, Field(min_length=1)]
PositiveSeconds = Annotated[float, Field(gt=0)]


class MessageRole(str, Enum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"


class PrivacyScope(str, Enum):
    LOCAL_ONLY = "local_only"
    EXTERNAL_ALLOWED = "external_allowed"


class FinishReason(str, Enum):
    COMPLETED = "completed"
    LENGTH = "length"


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ModelCapabilities(StrictModel):
    structured_output: bool = False
    tools: bool = False
    vision: bool = False
    streaming: bool = False

    def supports(self, required: "ModelCapabilities") -> bool:
        return all(
            not required_value or getattr(self, field_name)
            for field_name, required_value in required.model_dump().items()
        )


class ModelMessage(StrictModel):
    role: MessageRole
    content: NonEmptyStr


class ModelRequest(StrictModel):
    messages: tuple[ModelMessage, ...]
    identity_context: IdentityContext
    private_context: dict[str, JsonValue] = Field(default_factory=dict)
    required_capabilities: ModelCapabilities = Field(default_factory=ModelCapabilities)
    privacy_scope: PrivacyScope = PrivacyScope.LOCAL_ONLY
    preferred_provider_id: NonEmptyStr | None = None
    timeout_seconds: PositiveSeconds = 30.0
    execution_model_id: NonEmptyStr | None = None
    execution_think: bool = False

    @model_validator(mode="after")
    def validate_messages(self):
        if not self.messages:
            raise ValueError("ModelRequest requires at least one message")
        return self


class ModelResponse(StrictModel):
    provider_id: NonEmptyStr
    model_id: NonEmptyStr
    text: NonEmptyStr
    finish_reason: FinishReason
    capabilities: ModelCapabilities
    is_local: bool

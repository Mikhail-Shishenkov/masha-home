from enum import Enum
import json
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, JsonValue, model_validator

from backend.identity.identity_models import IdentityContext


NonEmptyStr = Annotated[str, Field(min_length=1)]
PositiveSeconds = Annotated[float, Field(gt=0)]
GenerationTemperature = Annotated[float, Field(ge=0, le=2)]


def _json_depth(value: JsonValue, depth: int = 0) -> int:
    if not isinstance(value, (dict, list)) or not value:
        return depth
    children = value.values() if isinstance(value, dict) else value
    return max(_json_depth(child, depth + 1) for child in children)


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
    structured_output_schema: dict[str, JsonValue] | None = None
    generation_temperature: GenerationTemperature | None = None

    @model_validator(mode="after")
    def validate_messages(self):
        if not self.messages:
            raise ValueError("ModelRequest requires at least one message")
        if (
            self.structured_output_schema is not None
            and not self.required_capabilities.structured_output
        ):
            raise ValueError(
                "structured_output_schema requires structured_output capability"
            )
        if self.structured_output_schema is not None:
            encoded = json.dumps(
                self.structured_output_schema,
                ensure_ascii=False,
                separators=(",", ":"),
            )
            if len(encoded) > 32_000 or _json_depth(self.structured_output_schema) > 16:
                raise ValueError("structured output schema exceeds bounded contract")
        return self


class ModelResponse(StrictModel):
    provider_id: NonEmptyStr
    model_id: NonEmptyStr
    text: NonEmptyStr
    finish_reason: FinishReason
    capabilities: ModelCapabilities
    is_local: bool

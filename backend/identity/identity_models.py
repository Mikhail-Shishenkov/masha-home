from enum import Enum
from typing import Annotated, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator


NonEmptyStr = Annotated[str, Field(min_length=1)]


class ManifestStatus(str, Enum):
    DRAFT = "draft"
    APPROVED = "approved"


class VisualStatus(str, Enum):
    UNAPPROVED = "unapproved"
    APPROVED = "approved"


class ProtectedIdentityModel(BaseModel):
    """Immutable loaded data; only an explicit user workflow may replace a manifest."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class PersonaIdentity(ProtectedIdentityModel):
    id: NonEmptyStr
    name: NonEmptyStr
    role: NonEmptyStr
    core_traits: tuple[NonEmptyStr, ...]
    communication_principles: tuple[NonEmptyStr, ...]
    relationship_expressions: tuple[NonEmptyStr, ...]
    growth_areas: tuple[NonEmptyStr, ...]


class VisualAsset(ProtectedIdentityModel):
    id: NonEmptyStr
    relative_path: NonEmptyStr
    sha256: Annotated[str, Field(pattern=r"^[A-F0-9]{64}$")]
    purpose: NonEmptyStr

    @model_validator(mode="after")
    def validate_relative_path(self):
        if self.relative_path.startswith(("/", "\\")) or ".." in self.relative_path:
            raise ValueError("visual asset path must stay inside the project")
        return self


class VisualIdentityManifest(ProtectedIdentityModel):
    status: VisualStatus
    assets: tuple[VisualAsset, ...]
    canonical_asset_ids: tuple[NonEmptyStr, ...]
    description: str | None
    allowed_variations: tuple[NonEmptyStr, ...]

    @model_validator(mode="after")
    def validate_approved_visual_identity(self):
        if self.status == VisualStatus.APPROVED and not self.canonical_asset_ids:
            raise ValueError("approved visual identity requires a canonical asset")
        asset_ids = {asset.id for asset in self.assets}
        if len(asset_ids) != len(self.assets):
            raise ValueError("visual asset ids must be unique")
        if not set(self.canonical_asset_ids).issubset(asset_ids):
            raise ValueError("canonical asset ids must reference declared assets")
        return self


class IdentityManifest(ProtectedIdentityModel):
    schema_version: Literal["1.0"]
    identity_version: NonEmptyStr
    status: ManifestStatus
    persona: PersonaIdentity
    visual_identity: VisualIdentityManifest
    approved_by: NonEmptyStr | None
    approved_at: AwareDatetime | None

    @model_validator(mode="after")
    def validate_approval(self):
        approved = self.status == ManifestStatus.APPROVED
        if approved and (self.approved_by is None or self.approved_at is None):
            raise ValueError("approved manifest requires approved_by and approved_at")
        if approved and not self.persona.core_traits:
            raise ValueError("approved manifest requires at least one core trait")
        if not approved and (self.approved_by is not None or self.approved_at is not None):
            raise ValueError("draft manifest cannot have approval metadata")
        return self


class IdentityContext(ProtectedIdentityModel):
    identity_version: NonEmptyStr
    manifest_status: ManifestStatus
    persona_id: NonEmptyStr
    name: NonEmptyStr
    role: NonEmptyStr
    core_traits: tuple[NonEmptyStr, ...]
    communication_principles: tuple[NonEmptyStr, ...]
    relationship_expressions: tuple[NonEmptyStr, ...]
    growth_areas: tuple[NonEmptyStr, ...]
    visual_status: VisualStatus
    canonical_asset_ids: tuple[NonEmptyStr, ...]


class IdentityRegressionScenario(ProtectedIdentityModel):
    id: NonEmptyStr
    title: NonEmptyStr
    user_message: NonEmptyStr
    expected_principles: tuple[NonEmptyStr, ...]
    prohibited_patterns: tuple[NonEmptyStr, ...]


class IdentityRegressionSuite(ProtectedIdentityModel):
    schema_version: Literal["1.0"]
    identity_version: NonEmptyStr
    scenarios: tuple[IdentityRegressionScenario, ...]

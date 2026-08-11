"""UI-facing local model profile operations with no fallback."""

from __future__ import annotations

from backend.llm.model_profiles import LocalModelProfile, ModelProfileStore
from backend.llm.model_router import ModelRouter

from .catalogs import error_label, model_availability_label
from .contracts import (
    ApplicationErrorCode,
    ModelAvailabilityCode,
    ModelProfileView,
    ModelSwitchResult,
    ModelSwitchStatus,
)


class ModelSettingsService:
    """Checks the selected local model before changing only the active profile."""

    def __init__(self, *, profiles: ModelProfileStore, router: ModelRouter):
        self._profiles = profiles
        self._router = router

    def list_profiles(self) -> tuple[ModelProfileView, ...]:
        active_id = self._profiles.get_active_profile().profile_id
        return tuple(self._view(profile, active_id=active_id) for profile in self._profiles.list_profiles())

    def current(self) -> ModelProfileView:
        profile = self._profiles.get_active_profile()
        return self._view(profile, active_id=profile.profile_id)

    def use(self, profile_id: str) -> ModelSwitchResult:
        try:
            candidate = self._profiles.get_profile(profile_id)
        except KeyError:
            return self._rejected(profile_id, ApplicationErrorCode.PROFILE_NOT_FOUND)
        if not candidate.enabled:
            return self._rejected(profile_id, ApplicationErrorCode.PROFILE_DISABLED)

        availability = self._availability(candidate)
        error = self._error_for(availability)
        if error is not None:
            return self._rejected(profile_id, error)

        self._profiles.set_active_profile(profile_id)
        return ModelSwitchResult(
            status=ModelSwitchStatus.APPLIED,
            requested_profile_id=profile_id,
            active_profile=self.current(),
        )

    def _rejected(self, profile_id: str, code: ApplicationErrorCode) -> ModelSwitchResult:
        return ModelSwitchResult(
            status=ModelSwitchStatus.REJECTED,
            requested_profile_id=profile_id,
            active_profile=self.current(),
            error_code=code,
            error_label=error_label(code),
        )

    def _view(self, profile: LocalModelProfile, *, active_id: str) -> ModelProfileView:
        availability = self._availability(profile)
        return ModelProfileView(
            profile_id=profile.profile_id,
            display_name=profile.display_name,
            model_id=profile.model_id,
            capabilities=profile.capabilities,
            description=profile.description,
            enabled=profile.enabled,
            active=profile.profile_id == active_id,
            available=availability is ModelAvailabilityCode.AVAILABLE,
            availability_code=availability,
            availability_label=model_availability_label(availability),
        )

    def _availability(self, profile: LocalModelProfile) -> ModelAvailabilityCode:
        if not profile.enabled:
            return ModelAvailabilityCode.DISABLED
        if not profile.model_id:
            return ModelAvailabilityCode.MODEL_NOT_CONFIGURED
        provider = self._router.get_provider(profile.provider_id)
        if provider is None:
            return ModelAvailabilityCode.PROVIDER_NOT_FOUND
        if not provider.is_available():
            return ModelAvailabilityCode.PROVIDER_UNAVAILABLE
        model_check = getattr(provider, "is_model_available", None)
        if not callable(model_check):
            return ModelAvailabilityCode.MODEL_CHECK_UNAVAILABLE
        if not model_check(profile.model_id):
            return ModelAvailabilityCode.MODEL_UNAVAILABLE
        return ModelAvailabilityCode.AVAILABLE

    @staticmethod
    def _error_for(code: ModelAvailabilityCode) -> ApplicationErrorCode | None:
        return {
            ModelAvailabilityCode.AVAILABLE: None,
            ModelAvailabilityCode.DISABLED: ApplicationErrorCode.PROFILE_DISABLED,
            ModelAvailabilityCode.PROVIDER_NOT_FOUND: ApplicationErrorCode.PROVIDER_NOT_FOUND,
            ModelAvailabilityCode.PROVIDER_UNAVAILABLE: ApplicationErrorCode.PROVIDER_UNAVAILABLE,
            ModelAvailabilityCode.MODEL_NOT_CONFIGURED: ApplicationErrorCode.MODEL_NOT_CONFIGURED,
            ModelAvailabilityCode.MODEL_UNAVAILABLE: ApplicationErrorCode.MODEL_UNAVAILABLE,
            ModelAvailabilityCode.MODEL_CHECK_UNAVAILABLE: ApplicationErrorCode.MODEL_CHECK_UNAVAILABLE,
        }[code]

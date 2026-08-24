"""Drive reuses Home-wide external-network safety controls."""

from __future__ import annotations

from backend.external_observation.policy import InternetAccessMode


class GoogleDriveNetworkBlocked(RuntimeError):
    pass


def assert_google_drive_network_allowed(*, policy_store=None, safety_store=None) -> None:
    if safety_store is not None and safety_store.is_engaged():
        raise GoogleDriveNetworkBlocked("emergency_stop_engaged")
    if policy_store is not None and policy_store.load().mode is InternetAccessMode.OFF:
        raise GoogleDriveNetworkBlocked("internet_access_off")

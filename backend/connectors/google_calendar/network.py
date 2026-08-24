"""Reuse Home-wide network safety controls without creating connector permissions."""

from __future__ import annotations

from backend.external_observation.policy import InternetAccessMode


class GoogleCalendarNetworkBlocked(RuntimeError):
    pass


def assert_google_network_allowed(*, policy_store=None, safety_store=None) -> None:
    if safety_store is not None and safety_store.is_engaged():
        raise GoogleCalendarNetworkBlocked("emergency_stop_engaged")
    if policy_store is not None and policy_store.load().mode is InternetAccessMode.OFF:
        raise GoogleCalendarNetworkBlocked("internet_access_off")

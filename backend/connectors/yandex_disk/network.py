from backend.external_observation.policy import InternetAccessMode


class YandexDiskNetworkBlocked(RuntimeError):
    pass


def assert_yandex_disk_network_allowed(*, policy_store=None, safety_store=None) -> None:
    if safety_store is not None and safety_store.is_engaged():
        raise YandexDiskNetworkBlocked("emergency_stop_engaged")
    if policy_store is not None and policy_store.load().mode is InternetAccessMode.OFF:
        raise YandexDiskNetworkBlocked("internet_access_off")

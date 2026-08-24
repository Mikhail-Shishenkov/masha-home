from backend.external_observation.policy import InternetAccessMode
class YandexMailNetworkBlocked(RuntimeError): pass
def assert_yandex_mail_network_allowed(*, policy_store=None, safety_store=None):
    if safety_store is not None and safety_store.is_engaged(): raise YandexMailNetworkBlocked("emergency_stop_engaged")
    if policy_store is not None and policy_store.load().mode is InternetAccessMode.OFF: raise YandexMailNetworkBlocked("internet_access_off")

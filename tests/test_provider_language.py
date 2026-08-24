from backend.connectors.provider_language import normalize_command_prefix, normalize_explicit_provider


def test_explicit_provider_variants_normalize_to_one_application_owned_id():
    for phrase in ("Google Drive", "Гугл Диск", "Гугл Диске", "Google Диск", "Drive", "Драйв", "Драйве"):
        assert normalize_explicit_provider(f"покажи файлы в {phrase}").provider_id == "google_drive"
    for phrase in ("Яндекс Диск", "Яндекс Диске", "Yandex Disk", "Yandex Диск"):
        assert normalize_explicit_provider(f"покажи файлы на {phrase}").provider_id == "yandex_disk"


def test_command_typos_are_corrected_only_before_explicit_provider_or_in_small_prefix():
    normalized = normalize_explicit_provider("Маша, найди последние файы на Яндекс диске")
    assert normalized.text == "маша найди последние файлы на yandex_disk"
    assert normalize_command_prefix("прочитай файл файы", token_limit=2).endswith("файы")
    assert normalize_explicit_provider("прочитай файл файы на Яндекс Диске").text == "прочитай файл файы на yandex_disk"

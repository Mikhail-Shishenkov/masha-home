from backend.temporal.duration_resolution import HomeDurationResolver
from backend.temporal.clock_evidence import resolve_clock_evidence


def test_duration_normalization_is_bounded_and_does_not_steal_clock_phrases():
    resolver = HomeDurationResolver()

    assert resolver.resolve("на час").minutes == 60
    assert resolver.resolve("12 минут").minutes == 12
    assert resolver.resolve("полчаса").minutes == 30
    assert resolver.resolve("12").ambiguous_unit is True
    assert resolver.resolve("в 12 часов дня") is None
    assert resolver.resolve("12 часов дня") is None
    assert resolver.resolve("встреча на 12 часов дня") is None
    assert resolver.resolve("на 25 часов") is None


def test_clock_evidence_cannot_strip_duration_relation_or_day_period():
    for utterance, quote in (
        ("Напомни за час до начала", "час"),
        ("Напомни через 2 часа", "2"),
        ("Продли на два часа", "два"),
        ("Продли на два часа", "два часа"),
        ("Поставь в час дня", "час"),
        ("Напомни за час до начала", "за час до начала"),
    ):
        assert resolve_clock_evidence(utterance, quote) is None, (utterance, quote)
    for quote, expected in (("в час дня", "13:00"), ("двадцать один", "21:00"),
                            ("9 утра", "09:00"), ("на 14:30", "14:30")):
        assert resolve_clock_evidence(quote, quote) == expected

from backend.temporal.duration_resolution import HomeDurationResolver


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

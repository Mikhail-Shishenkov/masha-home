from backend.llm.masha_benchmark_suite import MASHA_HOME_V1


def test_suite_has_twenty_unique_short_fixed_cases():
    assert len(MASHA_HOME_V1) == 20
    assert len({case.id for case in MASHA_HOME_V1}) == 20
    assert all(case.think is False for case in MASHA_HOME_V1)
    assert all(case.num_predict <= 70 for case in MASHA_HOME_V1)

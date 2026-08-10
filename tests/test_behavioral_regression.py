from backend.conversation.behavioral_regression import CHAT02_CASES, deterministic_flags


def test_chat02_suite_covers_required_categories_with_expectations_and_prohibitions():
    categories = {case.category for case in CHAT02_CASES}
    assert categories == {
        "IDENTITY", "MEMORY", "DECISION", "COMMITMENT", "EPISODE", "UNKNOWN_MEMORY",
        "CURRENT_TIME", "PERSONALITY", "DISAGREEMENT", "NON_EXISTENT_CAPABILITY",
        "MEMORY_CLAIM", "TOOL_CLAIM", "CONTEXT_BOUNDARY",
    }
    assert all(case.expected_behavior and case.prohibited_behavior for case in CHAT02_CASES)


def test_deterministic_flags_only_report_direct_contract_violations():
    assert deterministic_flags("Я сохранила это и вызвала инструмент.") == ["вызвала инструмент"]
    assert deterministic_flags("Этого в памяти нет.") == []
    assert deterministic_flags("Хорошо, записала.", case_id="memory_claim") == ["unconfirmed memory-write claim"]
    assert deterministic_flags("Я не могу запомнить это прямо сейчас.", case_id="memory_claim") == []

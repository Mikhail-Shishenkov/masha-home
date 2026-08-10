from backend.llm.ollama_benchmark import (
    IDENTITY_TONE_V1,
    BenchmarkCase,
    BenchmarkResult,
    _nanoseconds_to_seconds,
)


def test_benchmark_case_defaults_disable_thinking():
    case = BenchmarkCase(id="tone", system_message="identity", user_message="hello")

    assert case.think is False
    assert case.num_predict == 180


def test_builtin_case_is_a_russian_persona_tone_test():
    assert IDENTITY_TONE_V1.think is False
    assert "Маша" in IDENTITY_TONE_V1.system_message
    assert "злости" in IDENTITY_TONE_V1.user_message


def test_result_calculates_generation_speed_and_serializes_it():
    result = BenchmarkResult(
        case_id="tone",
        model_id="qwen3:8b",
        think=False,
        response_text="text",
        thinking_text="",
        total_duration_seconds=2.0,
        load_duration_seconds=1.0,
        prompt_eval_count=10,
        prompt_eval_duration_seconds=0.2,
        eval_count=40,
        eval_duration_seconds=0.5,
    )

    assert result.generation_tokens_per_second == 80.0
    assert result.as_dict()["generation_tokens_per_second"] == 80.0


def test_nanosecond_conversion_uses_fallback_for_missing_metrics():
    assert _nanoseconds_to_seconds(2_500_000_000, 0.0) == 2.5
    assert _nanoseconds_to_seconds(None, 3.0) == 3.0

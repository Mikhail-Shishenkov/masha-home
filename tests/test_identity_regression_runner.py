from pathlib import Path

from backend.identity.run_identity_regression import run_identity_regression
from backend.llm.fake_provider import FakeProvider
from backend.llm.model_router import ModelRouter


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_identity_regression_runner_uses_fixture_memory_and_writes_local_raw_output(tmp_path):
    provider = FakeProvider(provider_id="ollama-local", response_text="Я Маша, не человек и не Миша.")
    output_path = tmp_path / "identity-regressions" / "run.json"

    result = run_identity_regression(
        router=ModelRouter([provider]),
        manifest_path=PROJECT_ROOT / "identity" / "masha.identity.json",
        suite_path=PROJECT_ROOT / "identity" / "masha.regression.json",
        fixture_memory_path=PROJECT_ROOT / "tests" / "fixtures" / "test_memory.json",
        project_id="project_masha_home",
        output_path=output_path,
    )

    assert output_path.is_file()
    assert result["suite_identity_version"] == "masha-0.1"
    assert len(result["results"]) == 3
    assert all(item["passed"] for item in result["results"])
    assert provider.last_request is not None
    assert provider.last_request.identity_context.identity_version == "masha-0.1"

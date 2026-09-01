# Release scenarios

`scenarios.json` is the migration catalog for the 96 deterministic Critical Product Journeys.

A catalog entry with `status: planned` is **not** a passing release test. It becomes implemented only after a concrete test under this directory proves the end-state invariant, or a named narrow contract test proves the lower-level invariant more directly.

Deletion rule: a legacy test may be removed only after every unique invariant it owns has moved either to a concrete release journey here or to a narrow invariant under `tests/contract/`.

Target gate after migration: exactly 96 release journeys. External network/Ollama checks belong to `tests/live_smoke/`; model-quality benchmarks belong to `evals/`.

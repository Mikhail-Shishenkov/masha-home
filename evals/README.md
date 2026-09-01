# Model evals

This directory is the destination for nondeterministic language/model benchmarks currently mixed into `tests/`. Evals measure model quality over corpora and may require repeated trials or a live Ollama model; they are not deterministic product-release regression tests.

Phase 1 only creates this boundary. Benchmark runners/fixtures move here in a later patch after their shared fixture references are audited.

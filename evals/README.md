# Masha Home — model and language evals

`evals/` is the boundary for **nondeterministic language/model quality**. It is intentionally separate from deterministic product tests.

Core principle:

> **Green deterministic tests do not mean conversational quality is accepted.**

A release-quality AI system needs three different kinds of evidence.

## 1. Deterministic tests

`tests/` should protect invariants that must be reproducible:

- domain and application contracts;
- authority / permission boundaries;
- confirmation semantics;
- operation and receipt truth;
- persistence and recovery;
- deterministic temporal normalization;
- application-owned IDs and selected real objects;
- fail-closed provider / capability ownership;
- deterministic adapter and schema validation.

These tests answer: **can the system violate a hard contract?**

## 2. Evals

`evals/` should measure behavior that is intentionally variable because an LLM participates:

- paraphrase robustness;
- speech-act classification quality;
- capability mapping quality;
- slot / field extraction quality;
- relative-time language quality;
- multi-turn reference continuity;
- correction handling;
- natural Russian wording;
- preservation of topic and context;
- cross-chat continuity behavior;
- model-dependent language quality;
- robustness on unseen formulations.

Evals may use repeated trials, fixed corpora, synthetic application context and an explicitly selected local model. They are evidence about model/system behavior, not authorization and not mutation truth.

A model failure must not be repaired by silently relaxing application authority or grounding rules.

## 3. Human acceptance

Human Review is required for the final conversational product experience:

- complete dialogue journeys, not isolated prompts;
- whether corrections feel natural;
- whether Masha remembers the right context without inventing it;
- whether ordinary conversation remains ordinary;
- whether actions and confirmations are understandable;
- whether the resulting Russian feels coherent, warm and non-mechanical;
- whether the whole Home is useful rather than merely test-green.

The current `new/agent-coherence-continuation` checkpoint is a concrete example: deterministic gates are green, while relative-time extraction and complete multi-turn conversational acceptance remain open.

## Scope discipline

Do not turn variable language quality into hundreds of exact-string unit tests or phrase-specific routing rules.

Use the split:

- **deterministic invariant → test**;
- **variable language behavior → eval**;
- **final product feel → Human Review**.

Phase 1 established this directory boundary. Benchmark runners/fixtures should move here only after their shared dependencies and intended ownership are audited; this file does not authorize a framework migration or a new evaluation platform.

# UI-06H — Slice C: Workbench

Status: **IMPLEMENTED**

## Purpose

The Home now has one contextual `Режим` object — a calm local workbench rather
than a permanent administration dashboard. It makes existing operating truth
visible without granting the renderer general control over Skills, Permissions
or local runtime.

## What is visible

- active and configured local Model Profiles with deterministic availability;
- registered local Skills, their declared capabilities and runtime-adapter
  status;
- effective standing permissions and pending Skill/Agent decisions;
- the fact of active Agent Runs, without exposing a tool protocol or receipts
  beyond the already implemented `Работа` object.

The workbench consumes bounded immutable application contracts. It never
receives local paths, SQLite details, integrity hashes, grant IDs, proposal IDs,
audit payloads, raw skill packages or provider endpoints.

## Explicit action boundary

`Выбрать вручную` is the only new action. It invokes the existing LLM-03
`ModelSettingsService`: the local provider and requested model are checked first;
on failure the existing active profile remains unchanged; there is no fallback.

Changing a model modifies only the execution profile and Presentation Model
overlay. Identity, Memory, Commitments, Temporal Context, Conversation history,
Proactive policy and agent permissions remain unchanged. It is still allowed
while Emergency Stop is engaged because profile choice is operating
configuration, not autonomous execution.

Skill installation, upgrades, grant changes, policy levels and agent execution
remain deliberately CLI-only for now. They need their own explicit proposal and
confirmation UX rather than a generic web surface.

## Visual notes from the UI review

Two low-risk polish fixes landed alongside Slice C:

- a leaving Masha scene is sent behind the incoming frame immediately, reducing
  readable double-image overlap during rapid changes;
- long contextual objects keep their title/close affordance visible while their
  contents scroll.

The remaining higher-level review observations are collected for the next UI
polish pass: reduce technical density in continuity records, constrain very long
model answers, and make every temporary surface close/recede with one calmer
shared rhythm.

## Deliberate limitations

- no skill installation or update UI;
- no grant/policy editor;
- no scheduler or daemon controls;
- no automatic model switching or fallback;
- no new agent capability;
- no access to Identity, Memory or SQLite from the renderer.

## Next

Slice D: Runtime health and operating preferences, then a focused visual polish
pass based on the recorded UI review.

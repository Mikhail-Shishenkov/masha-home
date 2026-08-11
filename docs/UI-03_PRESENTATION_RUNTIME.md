# UI-03 — Presentation Runtime Foundation and Tier 0 Prototype

Status: **IMPLEMENTED**

Date: **2026-08-11**

## Purpose

UI-03 proves the architecture:

```text
UI-01 application state
→ immutable presentation model
→ deterministic reducer
→ renderer
```

It does not implement the final frontend, visual identity asset pack, animation
engine, voice or a new domain capability.

## Implementation

`backend.presentation` contains:

- immutable renderer-neutral models for Home, Masha presence, pose, expression,
  attention, activity, ambient state and independent operating overlays;
- universal `InteractionSurface` and observable `ActivityPresentation`;
- immutable presentation events;
- a pure `PresentationReducer` and small in-process `PresentationRuntime` state
  holder;
- a read-only adapter from UI-01 `MashaStatusView`, `ModelProfileView` and
  canonical `VisualAssetView` metadata;
- pure `TierZeroRenderer` scene projection;
- a no-LLM `TierZeroPrototypeController` and disposable Tk desktop window.

No presentation object contains filesystem paths, repositories, persistence
handles, callbacks or executable UI payloads.

## Compositional state

Masha is composed from independent axes:

```text
VisualIdentity
+ BasePose
+ ExpressionCue
+ AttentionState
+ PresenceActivity
+ AmbientState
```

Operating truth is independent:

```text
SafetyOverlay
+ ProactiveOverlay / level
+ ModelOverlay / active profile
+ RuntimeMode / daemon state
+ Window focus / privacy mask
```

Emergency stop changes the safety overlay without ending ordinary speaking or
changing Visual Identity. Model switching changes the execution overlay only.
An unfocused window masks sensitive Surface content without closing it.

## Surface lifecycle

The implemented lifecycle is:

```text
created → active → minimized/background → completed/closed
```

Only one non-terminal Surface may have the `primary` role. Surfaces declare
their available actions through closed `SurfaceCapability` values and cannot
embed frontend code.

## Activity lifecycle

Implemented presentation states:

```text
queued → running → waiting/completed/failed/cancelled
```

Progress is `none`, `indeterminate`, `steps` or `fraction`. Measured progress
requires explicit completed/total units. Fluent text never creates progress or
completion.

## Safety behaviour

Presentation Runtime is not a replacement permission gate. It consumes UI-safe
application facts. As defence in depth, the reducer refuses to present a newly
started autonomous Activity or proactive delivery as active while its safety
overlay is `autonomy_stopped`. Releasing the overlay does not resume either.

The Stage 16 safety service and domain runtimes remain authoritative.

## Tier 0 prototype

Run locally:

```powershell
.\masha.ps1 home
```

or:

```powershell
.\.venv\Scripts\python.exe -m backend.presentation.prototype
```

The prototype is one structural Shared Room scene with Masha as its central
presence, a conversation area and contextual Activity Surface. It uses only
standard-library Tk and the Presentation Runtime. It does not call Ollama,
`MashaApplication`, repositories or external services.

Local scenario controls:

| Key / area | Scenario |
|---|---|
| `1` / conversation | sent message → processing → response |
| `2` / Activity Surface | queued → running → progress → completed |
| `3` / initiative indicator | candidate → delivered → acknowledged |
| `4` / safety indicator | emergency stop / explicit release |
| `5` / model indicator | primary → fast → unavailable → primary |
| `6` / runtime indicator | manual / background |
| window focus | focused / privacy-masked unfocused state |

These are presentation scenarios, not domain operations. Their purpose is to
feel and inspect composition without an LLM.

The abstract Tier 0 figure is a structural placeholder, not approved final
appearance, clothing or art direction. `visual asset: masha.canonical` is an
opaque identifier, not a path.

## Verification

- presentation + UI-01 targeted regression: `28 passed`;
- full regression: `307 passed`;
- real Tk window lifecycle: 66 Canvas objects rendered, window loop entered and
  closed successfully;
- production SQLite SHA-256 checked before and after the regression;
- no Identity, Memory, Commitment, Temporal, Proactive Decision, LLM-03,
  ModelRouter, Agent Loop, Safety or SQLite schema change.

## Known limitations

- UI-01 calls are synchronous; no true streaming/application event bus exists;
- the prototype controller uses local scenario events, not live conversation;
- Tk is a disposable Tier 0 adapter, not the selected production framework;
- there is no final avatar, layered 2D rig, authored animation or asset catalog;
- no persisted presentation preferences;
- no unified UI-safe detail/action boundary for proposals and agent runs;
- no voice, media processing, external events or device control;
- no pause/cancel/external-wait domain semantics are invented.

## Next step

UI-04 should select and implement the first actual desktop shell only after a
short visual prototype decision. It should consume the existing Presentation
Runtime rather than reimplement its reducer. The smallest useful UI-04 scope is
live UI-01 conversation/status wiring, Tier 0 canonical-image rendering and one
real Activity/confirmation projection; it should not add voice, rich animation
or new autonomy.

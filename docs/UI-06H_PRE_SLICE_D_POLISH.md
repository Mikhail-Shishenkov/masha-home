# UI-06H — pre-Slice-D visual and interaction polish

**Status:** implemented. This is a presentation-only pass over Slice A/B/C.

## What changed

- A transition now removes readable outgoing surfaces before the next one becomes readable. During the short exit the old surface has no pointer events; the incoming shell appears before its content.
- The home conversation recedes while a contextual surface is open and returns only after that surface has left. A pose/image swap is not requested by opening the Working corner.
- `Режим` became **`Уголок`**; the surface itself remains **`Рабочий уголок`**.
- The workbench retains exactly the existing projections and model-switch action, but speaks in human terms: **Как я думаю**, **Что я умею**, **Что мне можно**. Manual model switching still uses the existing availability check and has no fallback.
- Shared continuity no longer labels visible entries with memory-record types and cleans a small set of legacy implementation words in renderer copy. Domain memory and its records are unchanged.
- Ordinary surfaces no longer rely on WebEngine-expensive `backdrop-filter` or `clip-path`. Hardware compositing remains the default for responsive 4K interaction. A software fallback exists only for a known-bad graphics driver via `MASHA_HOME_SOFTWARE_COMPOSITING=1`. Emergency Stop remains visually exceptional.

## Deliberately unchanged

- Identity, Memory, SQLite schema, Temporal Runtime, Agent Loop, safety semantics, and Slice A/B/C application projections.
- Conversation content and its persistence.
- Manual model selection remains available while Emergency Stop is engaged; it is an operating preference, not autonomous action.

## Result to review

Record the same quick path: Conversation → Дела → Наша история → Уголок → Conversation. At no point should two readable textual surfaces overlap: the old conversation is now fully concealed, not merely dimmed. Visual depth is preserved by opaque local gradients rather than live blur.

Slice D is not started by this document.

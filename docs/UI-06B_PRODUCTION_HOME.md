# UI-06B — Production Home implementation record

Date: 2026-08-12  
Status: IMPLEMENTED, pending final human visual acceptance

## Boundary

```text
MashaApplication UI-safe views
→ LocalConversationBridge (typed allowlist)
→ deterministic renderer events
→ root frontend/
→ masha://home/ in PySide6 WebEngine
```

The renderer is offline-only. It cannot access SQLite, repositories, Identity,
Memory, Ollama endpoints, arbitrary filesystem paths or arbitrary backend
commands. LLM output cannot choose layout, animation, scene assets or safety
state.

## Implemented slice

- one full-scene room with Masha as the persistent anchor;
- bounded real conversation and composer;
- New conversation without deleting previous history;
- temporary spatial shelf of recent conversations;
- bounded Home Attention projection: active conversation, model availability
  and actual safety state only;
- immediate Emergency Stop and explicit Resume;
- Conversation and draft remain available while autonomy is stopped;
- honest model-unavailable state with no fake thinking or fake reply;
- deterministic listening, processing, speaking, safety and unavailable visual
  mapping;
- wide, standard, narrow and very-narrow desktop composition;
- keyboard focus, visible focus, Escape lifecycle and reduced-motion fallback.
- bounded composer: no manual browser resize grip, automatic growth up to a
  fixed limit, an internal styled scrollbar after that limit, `Enter` to send
  and `Shift+Enter` for a deliberate line break.
- interruptible two-layer full-scene crossfade with one central deterministic
  timing policy: normal, attention, safety and reduced-motion paths;
- clean production mode without visible local/profile diagnostics;
- Home Attention uses the right contextual zone and temporarily recedes
  Conversation instead of covering Masha or creating a second card wall.

## Deliberately absent

Memory, Commitments, Activities, Proactive/Check-in, Skills, Permissions, model
switching, Voice, Media, Devices and automatic privacy are not rendered. Their
backend existence is not treated as a user-facing capability.

## Persistence and safety

This stage adds no SQLite migration and no renderer persistence. Stop/Resume
use the existing application safety authority. Resume clears the safety latch
only; it does not automatically restart work. The presentation session is
serialized between the UI thread and the local model worker so Stop remains
deterministic during an in-flight conversation turn.

## Packaging

Source development resolves `frontend/` directly. Installed packages resolve
the same tree from `share/masha-home/frontend`. Both are served through the
same traversal-protected local origin and CSP.

## Visual QA result

The static renderer was inspected at 4K, standard and narrow desktop sizes. The room
geography remains stable, Masha stays visually dominant, Conversation occupies
the right quiet zone and no sidebar/dashboard/card wall appears. Native bridge
behaviour is covered by isolated deterministic application/bridge tests; final
human acceptance should be performed with `.\masha.ps1 home` on the target 4K
display.

The supplied native recording was also reviewed. It exposed three visual
problems now addressed in the renderer: title/transcript crowding, Home
Attention covering Masha, and a safety state that read too much like a dark
browser modal. Automated geometry and transition-policy checks are green, but
the revised native crossfade and safety ambience still require human visual
acceptance; this document therefore does not claim final visual closure.

## Known limits

- conversation loads a bounded latest window and has no earlier-message
  pagination yet;
- there is no retry/cancel application contract;
- current full-scene assets use crossfades rather than a layered character rig;
- the Home view has a minimum desktop window size and is not a mobile UI;
- static browser preview cannot interact because WebChannel intentionally
  exists only inside the local desktop host.

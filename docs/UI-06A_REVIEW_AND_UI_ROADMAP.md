# UI-06A Review Gate — Visual/UX Audit and UI Roadmap

Дата: 2026-08-12  
Статус: **CRITICAL DESIGN REVIEW — no production implementation**

## 1. Current state

The project has a credible local architecture and a working desktop
conversation slice. It does not yet have a production-complete visual Home.
The visible desktop renderer is a small cinematic proof that Masha can remain
the room's anchor while a conversation surface appears beside her. It must not
be mistaken for evidence that every backend feature now has user-facing UX.

The current physical layout is split as follows:

```text
backend/application/     application-owned UI-safe contracts and facade
backend/presentation/    deterministic reducer and composition contracts
backend/ui/              PySide6 host, local origin, closed bridge
backend/ui/frontend/     current production renderer and bundled scene assets
frontend/                empty
docs/prototypes/         disposable visual workshops
docs/assets/             review/workshop assets
```

This arrangement was useful for packaging the first PySide6/WebEngine slice,
but is not the recommended long-term boundary. The target boundary is:

```text
frontend/                production renderer, visual assets, renderer-side adapters,
                         host integration entry
backend/                 domain, application facade, presentation contracts/runtime,
                         Python desktop host and closed bridge
docs/                    design contracts, workshops, disposable prototypes/review boards
```

**No transfer is performed by this audit.** Moving `backend/ui/frontend` is a
separate packaging/origin migration: `local_origin.py`, Qt resource serving,
package-data and host tests currently deliberately depend on its location.

## 2. What is genuinely ready

- Local desktop host with a hardened `masha://home/` origin, no external
  renderer network access, and a closed WebChannel.
- Real local one-turn conversation through `MashaApplication`, with a bounded
  transcript, New conversation and recent conversation list.
- Deterministic listening, processing and speaking presentation transitions.
- Full-scene Masha + room assets rather than a cut-out avatar card.
- Public read-only Home snapshot, model availability state, and existing
  `MashaApplication.emergency_stop()` / `resume_autonomy()` facade methods.
- Presentation Runtime and CompositionResolver concepts for surfaces,
  activity, safety, proactive, model and window-focus states.
- Explicit local domain capabilities for Memory, commitments, temporal runtime,
  proactive events, check-in, skills, grants and bounded agent work.

## 3. What is only design or a contract

- Home gesture / “what is alive now”.
- A rendered safety overlay and Stop/Resume command in the desktop bridge.
- Typed confirmation surface.
- Real Activity surface driven by agent/runtime state.
- Commitment, proactive and check-in surfaces.
- Manual privacy mode.
- First-launch choreography and welcome-after-absence runtime event.
- Renderer-side use of semantic `CompositionPlan` beyond the current fixed
  conversation placement.
- Reduced-motion and accessibility policy.

## 4. What is missing

- UI-safe application projections for pending confirmations, commitments,
  proactive deliveries/check-ins, activities, skills/grants and agent runs.
- Closed bridge methods only for actions deliberately approved for UI.
- A truthful activity/event stream or bounded refresh projection; current UI
  cannot fabricate lifecycle progress.
- A manual privacy preference and exact host/renderer policy.
- An absence-aware welcome candidate that cannot duplicate history or let the
  renderer invent a proactive contact.
- First production frontend ownership at root `frontend/`; current renderer is
  packaged inside backend UI.
- Visual asset matrix and quality gate before expanding expression/outfit packs.

## 5. Capability → UX readiness matrix

| Capability | Backend | App boundary | Presentation | UI-safe view | Interaction contract | Visual readiness | User exposure now |
|---|---|---|---|---|---|---|---|
| First launch | partial | snapshot | partial | partial | design only | canonical idle | **DESIGN ONLY** |
| Ordinary conversation | yes | yes | yes | yes | yes | listening/thinking/speaking | **READY** |
| New conversation | yes | yes | yes | yes | yes | idle/conversation | **READY** |
| Return old conversation | yes | yes | partial | yes | yes | current shelf | **READY** |
| Long conversation | yes | bounded 16 messages | partial | partial | partial | no extra asset | **READY, bounded** |
| Pending confirmation | yes | no unified view | yes | no | design only | surface language only | **DO NOT EXPOSE YET** |
| Activity | yes | no activity view | yes | no | design only | working candidate | **DO NOT EXPOSE YET** |
| Commitment approaching due | yes | no view | partial | no | design only | work object undefined | **DO NOT EXPOSE YET** |
| Proactive reminder | yes | counts only | yes | no delivery view | design only | invitation language only | **DO NOT EXPOSE YET** |
| Check-in | yes | counts only | yes | no candidate/delivery view | design only | invitation language only | **DO NOT EXPOSE YET** |
| Emergency Stop | yes | yes | yes | yes | approved semantics | overlay missing | **READY FOR NARROW SLICE** |
| Model unavailable | yes | yes | yes | yes | partial | idle/presence works | **READY, improve recovery UX** |
| Model switching | yes | yes | yes | yes | no approved spatial interaction | none required | **MENTION ONLY / DO NOT EXPOSE** |
| Home overview | status facts yes | no bounded attention view | yes | no | approved design | no asset needed | **DO NOT EXPOSE YET** |
| Memory / continuity | yes | no | partial | no | design only | calm surface undefined | **DO NOT EXPOSE YET** |
| Skills | yes | no | partial | no | no | none | **DO NOT EXPOSE YET** |
| Permissions / grants | yes | status only | partial | no | no | no | **DO NOT EXPOSE YET** |
| Manual privacy | no policy | no | focus support only | no | decision made, contract absent | veil undefined | **DO NOT EXPOSE YET** |
| Voice | no | no | design | no | no | no | **DO NOT EXPOSE YET** |
| Media | no | no | concept | no | no | no | **DO NOT EXPOSE YET** |
| Devices | no | no | concept | no | no | no | **DO NOT EXPOSE YET** |

## 6. Scenario storyboards

Each storyboard follows `discovery → invitation → focus → action → feedback →
completion → return to room`. “GAP” means a truthful implementation needs an
additional bounded application projection before any renderer work.

### 6.1 First launch — GAP

The room fades in already inhabited. Masha is seated, calm and grounded in the
room; the first five seconds contain only the room, Masha, a small local mark,
and a quiet invitation to write. The conversation surface does not dominate
until Misha engages. The hidden things are all subsystem controls and feature
claims. Misha's minimal action is simply writing. She becomes attentive;
ambient depth quiets only slightly; a conversational surface expands from the
right quiet zone. No setup state is persisted. The exact first-launch marker
and deterministic invitation eligibility are not yet application projections.

### 6.2 Ordinary conversation — READY

Discovery is the visible composer. Misha writes; Masha listens, with attentive
pose, attention toward user and close-conversation ambient. Send creates a
local, provisional user message and the scene becomes thoughtful/inward while
the worker runs. A real response returns her to speaking/warm attention.
Failure is a controlled local availability text, not fabricated speech.
Cancellation is not available yet; return is the surface remaining softly as
the current context. The active conversation and history are persistent;
listening/thinking are temporary.

### 6.3 New conversation — READY

The quiet New conversation affordance is discovered inside the conversation
surface. Misha activates it; the current thread returns to the shelf, the
surface becomes a fresh invitation, and Masha settles calmly. No conversation
is deleted. Completion is a clean context; cancellation is simply not taking
the action. Current thread reference is temporary; persisted histories remain.

### 6.4 Return to old conversation — READY

“Разговоры” opens the temporary shelf rather than a sidebar. Misha selects a
thread; it takes the conversational focus, shelf recedes, Masha remains
present, and the transcript becomes the bounded latest window. Failure is an
honest unavailable-thread message. Long history is not loaded or invented.
The selected thread persists as the window context; the shelf is temporary.

### 6.5 Long conversation — PARTIAL

The transcript becomes an internally scrollable context without moving the
room. Reading old messages does not force a jump to the latest. The current
implementation has only 16 loaded messages and no “earlier” gesture, search,
Markdown, attachments, retry or cancellation. Those must not be visually
promised. Masha stays a stable anchor; ambient remains quiet. **GAP:** bounded
pagination/retrieval contract and content rendering policy.

### 6.6 Pending confirmation — GAP

A real typed pending proposal would be discovered through the Home gesture or
its originating conversation, invited as a focused decision surface near the
work/quiet zone, and make Masha attentive toward it. Confirm/reject/adjust
would call only the proposal's allowed operation. Its completion is an honest
“изменение подтверждено/не сделано” resolution; it can recede after action.
No unified pending-proposal application view exists, so this scenario cannot
be implemented honestly now.

### 6.7 Activity — GAP

A verified task would occupy the workspace and direct Masha's focus there.
The surface has real queued/running/waiting/completed/failed/cancelled state,
not a spinner. Conversation stays usable. On focus loss it continues or pauses
only according to its domain contract, never renderer behaviour. Completion
leaves a calm resolution and may recede. **GAP:** no application activity view,
no live lifecycle source and no renderer composition use.

### 6.8 Commitment approaching due — GAP

Only an existing deterministic commitment may become a small work object after
presence/invitation. Misha can open it, mark completed only through the
existing explicit proposal flow, or say “не сейчас”; it does not become a
notification feed. Masha is calm/focused, never accusatory. **GAP:** no
commitment read/preview surface or Home projection.

### 6.9 Proactive reminder — GAP

Only a persisted, policy-authorised, undismissed delivery can invite Misha.
It appears after the room, never as a notification dump. Acknowledge/dismiss
is contextual; Masha is warm/focused; return restores the room. **GAP:** no
UI-safe delivery/acknowledgement projection or bridge interaction.

### 6.10 Check-in — GAP

Only deterministic absence detection and policy authorisation may create the
candidate. Masha is warmly attentive; the invitation is small and can be
dismissed. Absence is not interpreted as distress. **GAP:** no relevant
candidate/delivery UI projection. The renderer itself must never create a
check-in.

### 6.11 Emergency Stop — ready for narrow slice

The Stop affordance is always discoverable and separate from standard controls.
On activation, a safety pause overlay takes priority, room ambience quiets,
and Masha becomes calm/neutral. Autonomous activity is visually paused;
conversation and draft remain available. Resume clears the safety latch but
does not restart work. **GAP:** the facade exists, but no bridge slot, rendered
overlay, or user-reviewed visual prominence yet exists.

### 6.12 Model unavailable — READY, incomplete recovery

The existing model label and controlled conversation result reveal that the
local model cannot respond. Masha remains physically present, not “offline”.
No text is fabricated. The conversation surface retains what was safely
persisted. A retry/cancellation gesture is not yet contractually present;
therefore it must not appear in UI.

## 7. Interaction grammar quality review

UI-06A's grammar preserves the UI-04C direction if it is applied with three
rules:

1. **Presence first:** Masha and coherent room composition occupy visual
   priority before any surface.
2. **A surface is a temporary piece of the room:** it has a source zone,
   lifecycle and exit; it is not a card on an infinite canvas.
3. **Only truth earns visual attention:** no capability gets a place merely
   because a backend module exists.

Risk: a “Home overview” can quickly become a hidden dashboard. It must be a
small, bounded, momentary answer to “what needs attention now?”, showing only
existing typed objects, then receding. It must never become `Memory /
Commitments / Activities / Settings` navigation.

## 8. Visual identity requirements

The current pack proves a direction, not a complete production visual system.
Production Tier 1 should be built from semantic need, with quality gates for
identity consistency, anatomy, room geography, contact/shadow, camera,
lighting, right-side quiet zone and visual readability without text.

### Minimum Tier 1 matrix (target, not a batch request)

| Axis | Minimum production need | Current state |
|---|---|---|
| Appearance | one approved canonical face/hair/body treatment | mostly established; variants need strict review |
| Pose | settled seated, attentive/listening, thoughtful, working | four scene candidates exist; only first three connected to UX |
| Expression | calm, warm, attentive, thoughtful, focused, firm; extend to 8–12 only when events justify them | labels/partial assets; not yet a full controlled expression system |
| Attention | toward user, inward, toward surface, resting/room | model supports it; renderer uses only subset |
| Outfit | canonical home; one deliberate special; 1–2 future practical variants | canonical home exists; special evening is provisional and never default |
| Ambient relation | active home, close conversation, work, quiet, safety, manual privacy | semantic model exists; renderer has minimal filters only |
| Transitions | crossfade, ambient depth, surface reveal/return, reduced motion | crossfade only |

Assets should not be generated to meet a count. Every new frame requires a
specific deterministic UX event and human visual review.

## 9. Room + Masha asset strategy

### Compared approaches

| Approach | Strengths | Failure mode |
|---|---|---|
| A. Separate Masha + separate room + compositing | flexible outfits/poses; potentially economical after a real rig exists | the current known failure: cut-out feel, inconsistent perspective/light/shadow/scale/contact |
| B. Full scene: room + Masha master, with deterministic interaction layers | coherent lighting, camera, physical anchor, shadows and atmosphere; strongest premium result now | each semantic scene costs a reviewed asset; less free-form animation |

### Recommendation

Adopt **B for hero scenes and Tier 1**: a coherent “Room + Masha” master per
approved semantic state, with renderer-owned layers for surface glass, light,
depth, focus veil and motion. Do not split Masha from the room until there is a
purpose-built rig/lighting pipeline capable of preserving contact quality.

This keeps current character identity stable and permits later layered 2D or
rigged movement without asking a generative model to produce every runtime
transition. It also leaves the room evolvable through application-owned visual
preferences, not arbitrary LLM code.

## 10. Minimum believable motion

Masha must feel alive when no LLM work occurs, but movement is not evidence of
emotion or autonomous intention.

```text
At most one subtle motion channel is active at a time:
ambient breathing/depth OR gaze/attention shift OR surface transition.
```

- Breath/depth: extremely slow opacity/parallax/lighting shift, not anatomical
  image warping.
- Attention: state-bound transition between approved full-scene frames, not
  random gaze tracking.
- Micro-expression: only a reviewed state transition and only when there is a
  deterministic presentation event.
- Posture: one scene-to-scene change at semantic boundaries, never idle
  morphing.
- Light: a gentle response to conversation/work/safety state; no flashing or
  mood diagnosis.
- Respect `prefers-reduced-motion` / an equivalent local preference later.

Prohibited: face morphing, limb warping, random smiles, gaze wandering,
continuous decorative motion, generated in-between frames, and animation that
pretends a task is progressing.

## 11. Space transformation strategy

Without a new layout engine, the renderer can safely vary: room depth/light,
surface position/scale/opacity, quiet-zone allocation, focus veil, current
scene, and temporary visual objects whose domain state already exists.

Future Home evolution is intentionally one-way:

```text
Masha proposes an environment change
→ human approves
→ application-owned presentation preference/configuration changes
→ deterministic renderer applies known variation
```

Immutable: identity anchor, safety/control rules and resource boundary.
Configurable after approval: lighting preference, approved room variant, motion
intensity and future object placements. Dynamic: focus, surfaces and ambient.
No LLM produces layout, CSS, renderer code or an arbitrary asset URL.

## 12. Button / gesture audit

| Capability | Visibility | Form | Rationale |
|---|---|---|---|
| Send/message | always | text input + button/Enter | direct human expression |
| Conversation shelf | contextual/persistent gesture | temporary spatial shelf | threads are context, not navigation |
| Home overview | always, quiet | gesture / small spatial cue | a momentary status of the Home, not a menu |
| Emergency Stop | always | dedicated safety control | exception: safety critical |
| Resume | temporary | explicit button in safety overlay | prevents accidental autonomous restart |
| Confirmation | temporary | typed choice surface | decision needs an unambiguous action |
| Activity | contextual | workspace object/surface | only a real activity earns it |
| Commitment | contextual | desk/work object | time-relevant work, not task dashboard |
| Proactive/check-in | contextual | invitation surface | only real delivery/candidate |
| Memory | hidden until relevant | conversational action / calm surface | not chat history and not a page |
| Model switch | hidden until deliberate operating mode | focused operating surface | must remain manual, not casual chat toggle |
| Skills/permissions | hidden until ready | focused operating/approval surface | never “Run Agent” shortcut |

## 13. Error and state language

| Situation | Waiting/processing | Success | Partial/failed | Cancelled/unavailable |
|---|---|---|---|---|
| Conversation | Masha listens then thinks; no fake timer | real persisted answer | controlled local failure text | unavailable keeps Masha present; no fabricated response |
| Activity | workspace exists only with a real state | verified completion | named blocked/failed state, no fake progress | cancelled remains a truthful object briefly |
| Confirmation | focused decision awaits Misha | confirmed mutation receipt | validation/rejection stated plainly | rejected means no mutation |
| Commitment | only real due state appears | explicit completion flow | overdue is computed, not a system failure | “not now” affects only presentation/lifecycle allowed by domain |
| Proactive | candidate/delivery state only | acknowledgement/dismiss receipt | suppressed/blocked is not an error | no new contact produced by UI |
| Safety | pause overlay | latch engaged/released | no false “all stopped” claim | release is not an automatic restart |

Never use generic `Loading…`, global spinners, technical exception dumps, or
success visual language without a verified domain result.

## 14. Responsive desktop strategy

The existing `CompositionResolver` distinguishes wide, standard, narrow and
very narrow desktop classes. The production renderer currently does not
consume this plan fully. Target behaviour:

| Viewport | Masha | Conversation | Other surface |
|---|---|---|---|
| Wide | 40–50% visual field, room-first | right quiet zone | workspace/decision uses remaining zone |
| Standard | 35–45%, remains physically grounded | narrower right surface | one primary contextual object |
| Narrow | Masha stays large and spatially grounded, not avatar-card | surface moves/expands below or to adjacent quiet zone | secondary surfaces minimize/background |
| Very narrow desktop | room and Masha retain identity; no mobile tab bar | conversation is primary but not a full dashboard | only one focused surface; Home gesture remains available |

The exact Masha percentage is a human visual decision. A global compact mobile
UI, sidebar, or dashboard conversion is rejected.

## 15. Frontend host comparison

| Option | Strength | Cost/risk | Verdict |
|---|---|---|---|
| PySide6 + WebEngine | direct Python integration, offline origin control, Qt packaging/window lifecycle, modern HTML/CSS/WebGL path, good future voice/media bridge | larger binary/WebEngine footprint; frontend needs separate ownership | **recommended now** |
| Tauri | small desktop shell, strong web frontend ecosystem | Rust bridge/build complexity; Python process lifecycle/typed local bridge must be designed anew | viable later, not a migration now |
| Electron | mature web/GPU/media ecosystem | heavy runtime, Node process/security surface, redundant for local Python core | not justified for MVP |
| Native Qt/QML only | strong native lifecycle, no WebEngine | slower visual iteration and fewer web-layer assets/tools; requires another renderer implementation | possible Tier 2, not current direction |

Recommendation: retain **PySide6 + WebEngine** as host. Move the renderer to
root `frontend/` in a separately reviewed migration, keeping host and closed
bridge in backend. This provides a clean path to future GPU/WebGL/WebGPU,
voice/media UI and long-running local application while preserving Python's
domain authority.

## 16. Domain / Presentation / Visual boundary

| Example | Layer | Authority |
|---|---|---|
| Activity exists / is running | domain/application | existing agent/runtime state |
| Activity surface opens | presentation | deterministic reducer/composition using bounded event/view |
| workspace light becomes warmer | visual decoration | renderer applies known state token |
| Commitment is due | domain/temporal | deterministic Temporal Engine |
| a commitment object is visible | presentation | application projection + composition |
| Masha turns toward desk | visual/presence | deterministic event mapping |
| Masha suggests an environment change | conversation proposal | LLM may formulate proposal only |
| approved lighting changes | application/presentation preference | human-approved deterministic config |

The LLM cannot directly command the latter two layers.

## 17. Explicitly rejected patterns

- dashboard, side navigation, toolbar, notification bell, card wall;
- avatar widget in front of unrelated UI;
- permanent dominant chat rectangle;
- task-kanban or “Run Agent” controls;
- feature icons for unimplemented voice/media/device capabilities;
- randomly animated character, face morphing or cut-out compositing;
- UI-generated check-ins/welcomes/history entries;
- status badges that collapse safety, model, privacy and proactive semantics;
- raw audit/SQLite/UUID/error trace exposure.

## 18. Recommended implementation order

0. **Frontend boundary migration design** — decide/package/test the move of
   production renderer from `backend/ui/frontend` to root `frontend/`; do not
   merge it invisibly into a feature slice.
1. **UI-06B.0, visual composition review** — answer the critical questions
   below and approve a first production Tier 1 asset matrix.
2. **UI-06B.1, Home Attention & Safety** — smallest bounded read-only Home
   attention view plus Stop/Resume bridge actions and independent overlay.
3. **UI-06C, Conversation resilience** — history pagination, retry/cancel
   semantics only after application contract review; preserve room-first layout.
4. **UI-06D, typed confirmation + activity projection** — real state only;
   no simulated activity.
5. **UI-06E, commitments/proactive delivery surfaces** — after their specific
   read/acknowledgement boundary is approved.
6. **UI-06F, Memory/continuity and deliberate operating space** — no default
   dashboard; skills/permissions/model controls arrive only as focused
   operating interactions.

## 19. Risks and open architectural decisions

1. **Frontend ownership conflict:** current packaged renderer in
   `backend/ui/frontend` conflicts with intended root `frontend/` boundary.
   No code change is made here. A migration must preserve `masha://` origin,
   CSP, resource traversal protections, packaging and tests.
2. **Manual privacy conflict:** Presentation Runtime has a `WindowFocusChanged`
   privacy ambient path, but Misha chose manual-only privacy and the desktop
   host does not dispatch focus events. Required decision: retain focus events
   for future non-privacy visual behaviour, or redefine them after an explicit
   privacy policy. Do not wire automatic masking today.
3. **Welcome-after-absence gap:** history can provide an anchor, but no
   application-owned welcome view/event exists. UI must not use a frontend
   timeout to simulate this or create a history message.
4. **Asset readiness risk:** current complete scene assets are 16:9 masters;
   responsive composition requires human review on 4K wide, standard and narrow
   desktop before the renderer treats them as production-ready.
5. **State-to-asset gap:** semantic expression vocabulary is richer than the
   active scene mapping. Do not make the model's words pick a facial asset.

## 20. Questions for Misha

### Critical before UI-06B

1. What visual share should Masha occupy in the **wide idle** frame: about
   **30%, 40%, or 50%**? Recommendation: 40–45%.
2. During normal conversation, should the right conversation surface be
   **always faintly present** or **appear only after interaction**?
   Recommendation: faintly present after the first conversation, small on true
   first launch.
3. Maximum lighting transformation during real Activity: **subtle**,
   **noticeable**, or **cinematic**? Recommendation: noticeable but local to
   workspace, never a whole-room mode switch.
4. During ordinary conversation, does Masha look **mostly directly at Misha**,
   or have **occasional deterministic soft gaze-away pauses** while thinking?
   Recommendation: direct while listening/speaking; gaze-away only processing.
5. Is the Home gesture best expressed as a **small room object**, a **quiet
   corner mark**, or a **keyboard-first gesture with a minimal visual hint**?
   Recommendation: quiet corner mark + keyboard shortcut later.
6. Stop placement: **small persistent lower-corner control** or **room-object
   reveal through Home gesture**? Recommendation: lower-corner, visually quiet
   until used, because safety-critical.
7. Should Stop require a confirmation before engaging? Recommendation: no;
   immediate engage, explicit Resume only.
8. On manual Privacy mode, should the room become **softly blurred**, **darkened
   with surfaces hidden**, or **show a neutral privacy scene**? Recommendation:
   darkened, surfaces hidden, Masha/room abstractly visible.

### Important before production frontend

9. Should conversation shelf read as **physical shelf**, **floating surface**,
   or **desk notes**? Recommendation: physical shelf/notes, opening temporarily.
10. How much of the room may a focused surface darken: roughly **10%, 20%, or
    35%**? Recommendation: 15–20%.
11. Is the approved canonical home outfit the only default, with all other
    outfits requiring manual/explicit selection? Recommendation: yes.
12. Should Special Evening be **only an explicit user-selected mode**, or may
    it appear under a future deterministic contextual rule? Recommendation:
    explicit only until its visual family is approved.
13. Idle motion level: **almost still**, **one slow ambient cue**, or **subtle
    periodic posture variation**? Recommendation: one slow ambient cue.
14. Should the room's time of day be static initially, or have a deterministic
    local time-of-day lighting variation? Recommendation: static until the
    visual pack covers it coherently.
15. Should model availability be visible as **one quiet local status mark** or
    only when it becomes unavailable? Recommendation: quiet mark; expanded
    explanation only on failure.
16. Do you want keyboard shortcuts for Home, shelf, Stop, and privacy from the
    first real frontend slice? Recommendation: Home/shelf/Stop only; privacy
    after manual policy exists.
17. When a real activity is running, should conversation remain **fully
    readable beside it** or **collapse to a compact reply line**? Recommendation:
    readable but secondary.
18. For a due commitment, should “не сейчас” mean **only hide it for this
    session** or **explicitly dismiss/snooze via a domain action**? Recommendation:
    only hide until a separate domain-approved suppression contract exists.

### Later

19. Which 3–4 future practical outfit contexts matter most: morning/home,
    work/focus, walk/outside, evening, other?
20. Which future room changes may Masha propose: lighting only, object
    placement, room variants, or routines as well?
21. Should voice eventually be conversation-first while the text transcript
    remains visible, or should voice have a separate quiet mode?
22. Should images/media appear as temporary desk/room surfaces or a dedicated
    gallery mode?
23. Which local devices, if any, may become part of the Home later?
24. Do you prefer one canonical room that deepens over time, or a small number
    of user-approved room variants?

## Review conclusion

UI-06B must not begin until the critical visual decisions, frontend boundary
decision and the manual-privacy/open-contract issue are settled. The right next
work is not adding surfaces; it is choosing how the Home holds attention while
remaining a believable room with Masha inside it.

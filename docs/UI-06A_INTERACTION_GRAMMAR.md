# UI-06A — Interaction Grammar Workshop

Дата: 2026-08-12  
Статус: **DESIGN CONTRACT — implementation requires a separate approval**

## 1. Design principles

Masha Home is one local living space, not a dashboard, administrative console,
or a collection of product pages. Masha is the persistent visual anchor; a
function appears as an Interaction Surface only when it has a reason to take
attention.

The approved interaction sequence is:

```text
presence → invitation → context → deliberate action → return to room
```

The inverse is prohibited: no launch into a notification wall, task dashboard,
or all-purpose toolbar. Layout, animation, safety state and visual expression
are selected deterministically by application/presentation state, never by
LLM output.

## 2. Decisions confirmed by Misha

| Topic | Decision |
|---|---|
| Always available | Conversation, a quiet Home gesture, and Emergency Stop |
| Home gesture | Opens a temporary overview of what is alive now; it is not a menu |
| Conversation history | A temporary, spatial conversation shelf |
| Privacy | Manual-only privacy mode; no automatic masking on focus loss |
| Commitments / proactive | Appear as contextual spatial objects only when relevant; each offers a human “not now” path |
| Return after absence | **Soft welcome after absence:** presence → invitation → relevant context |
| Welcome order | Room/Masha first; after a short deterministic pause: “С возвращением. С чего начнём?”; important pending items may follow without taking over the conversation |
| Stop semantics | Stops autonomous/background work only; conversation, history and draft remain usable; resume never restarts work automatically |

## 3. Capability inventory and readiness

| Capability | Backend | Public application contract | Presentation support | UI-safe projection | Safe to expose visually now? | Missing piece |
|---|---|---|---|---|---|---|
| Conversation / new conversation | implemented | implemented | implemented | implemented | **READY** | robustness work only |
| Recent conversations | implemented | implemented | partial | implemented | **READY** | spatial shelf refinement, longer history |
| Identity / canonical visual identity | implemented | read-only assets + snapshot | implemented | implemented | **READY** | asset matrix expansion only after semantic need |
| Emergency Stop / resume | implemented | `emergency_stop`, `resume_autonomy` | implemented | yes | **READY FOR CONTROL** | closed bridge command and approved visual treatment |
| Model status | implemented | snapshot/current model | implemented | read-only | **READY FOR STATUS** | controlled model UI if desired |
| Model switching | implemented | `use_model` | implemented | yes | **DESIGN ONLY** | deliberate interaction contract + bridge command |
| Pending confirmations | implemented, typed flows | no unified UI projection | implemented | no | **NEEDS PROJECTION** | typed pending-control boundary |
| Activities / agent runs | implemented | no public activity view | implemented | no | **NEEDS PROJECTION** | read-only activity/run lifecycle boundary |
| Commitments / temporal state | implemented | no Home-facing view | partial | no | **NEEDS PROJECTION** | commitment read/preview boundary |
| Long-term Memory / shared continuity | implemented | no Home-facing view | partial | no | **NEEDS PROJECTION** | bounded read/proposal boundary |
| Proactive reminder / check-in | implemented | status counts only | implemented | no candidate/delivery content | **NEEDS PROJECTION** | safe delivery/acknowledgement boundary |
| Skills / grants / permissions | implemented | status aggregation only | partial | no | **NEEDS PROJECTION** | focused inspection/approval contracts |
| Privacy mode | design/presentation support | no persistent preference/control | implemented | no | **DESIGN ONLY** | manual privacy policy and host contract |
| Voice / media / devices | not implemented | no | concept only | no | **DO NOT EXPOSE** | independent product boundaries |

## 4. Interaction grammar

### Discovery

The Home teaches interaction by calm affordance, not an instruction sheet:

- the conversation surface is the immediate invitation to speak;
- the Home gesture is a single quiet spatial cue, available in any state, that
  reveals current meaningful things rather than a navigation menu;
- the conversation shelf appears from the existing “Разговоры” affordance and
  disappears after a thread is chosen;
- a relevant commitment, confirmation, activity or proactive message earns its
  own contextual object only when it exists in the application state;
- Emergency Stop is always discoverable, visually independent, and never
  presented as a normal feature button.

No empty Memory, Activities, Skills, or Settings panels are shown merely to
advertise future capability.

### Focus

One focus owns the room at a time. The ordering is:

```text
safety overlay
→ explicit confirmation
→ active user interaction
→ active activity
→ relevant proactive item
→ ambient Home presence
```

Lower-priority surfaces recede rather than disappear destructively. A user can
continue a normal conversation while a real activity is visible in the
workspace. A safety overlay can cover autonomous interaction but does not
erase the conversation or draft.

### Surface lifecycle

All surfaces follow the existing conceptual lifecycle:

```text
created → active → minimized/background → completed/closed
```

Visual rules:

- **Created:** begins from a semantically related room zone; no pop-in card.
- **Active:** gets the readable quiet zone and may modestly dim secondary room
  detail, never Masha herself.
- **Background:** reduces to a trace/object only if the operation still exists.
- **Completed:** gives a short, calm resolution cue, then returns control to
  the room.
- **Closed:** leaves no fake persistent record; real history remains in its
  actual store.
- **Cancelled / dismissed:** states exactly that no action was taken or no
  further attention is requested; it never pretends completion.

### Presence, attention and expression

Masha does not act as a decorative avatar. Her state is an independent,
deterministic presentation projection.

| Interaction | Pose / attention | Permitted expression | Not permitted |
|---|---|---|---|
| idle / first presence | settled, toward room/user | calm, warm | exaggerated welcome, permanent smile |
| user types/sends | attentive/listening, toward user | attentive | thinking before a turn begins |
| model processing | thoughtful, inward | thoughtful | anxious/absent/diagnostic concern |
| response | speaking, toward user | warm, amused where explicit deterministic cue exists | asset chosen by answer text |
| real activity | working, toward workspace | focused | fake progress or feigned completion |
| explicit confirmation | attentive, toward surface | attentive, firm if a refusal is deterministic | coercive / impatient affect |
| commitment due | attention toward relevant work object | calm / focused | guilt, diagnosis, alarmistic pose |
| check-in | toward user | warm | treating absence as evidence of distress |
| emergency stop | neutral, no task attention | calm | punitive, frightened, or “broken” Masha |
| model unavailable | present but unable to respond | attentive / calm | false speaking / fake answer |

`quiet beside` and `firm disagreement` assets remain inactive until an approved
application-owned cue reaches the Presentation Runtime. User text and LLM
output cannot choose them.

### Motion and ambient

- Use slow opacity, depth and placement transitions; no bounce, carousel,
  spinner, reward animation, or abrupt full-room scene change for ordinary
  work.
- A surface expands from its room zone and returns there. It does not fly from
  a global toolbar.
- Ambient can slightly quiet secondary detail during conversation, direct a
  soft work focus for activity, or create a distinct safety pause. It never
  changes domain state.
- Motion must have a deterministic duration and reduced-motion fallback.
- The canonical room remains stable enough to preserve a sense of place.

### Errors

Errors are local situations, not developer dumps:

- Model unavailable: Masha remains present; the conversation surface explains
  that the local model cannot answer now and offers the relevant recovery path
  once that interaction exists.
- Failed activity: workspace says what did not finish; no success language.
- Rejected/expired confirmation: the decision surface closes into an honest
  “не меняла” resolution.
- Missing future capability: do not render it at all; never say Masha has a
  feature that lacks a verified backend path.

## 5. Always available, contextual, temporary

### Always available

1. **Conversation:** one accessible input and current conversational context.
2. **Home gesture:** a single quiet affordance for “what is alive now”. It
   opens a temporary overview; it does not become navigation.
3. **Emergency Stop:** safety-critical affordance, visually distinct from
   ordinary controls. It pauses autonomous work only.
4. **Conversation shelf gesture:** available from conversation context, not a
   permanent sidebar.

### Contextual

- pending typed confirmation;
- active/waiting/failed real activity;
- relevant upcoming/due/overdue commitment;
- delivered reminder or check-in;
- model availability recovery state;
- a selected old conversation;
- future approved manual privacy state.

### Temporary

- welcome-after-absence invitation;
- surface completion and cancellation resolutions;
- model switching decision;
- skill-install or permission approval;
- retry affordance after a controlled failure.

## 6. Button audit

| Capability | Button? | Approved interaction direction |
|---|---|---|
| Conversation | yes, text entry/send | direct human expression is appropriate |
| Conversation shelf | not a persistent nav button | quiet contextual gesture; shelf is temporary |
| Home overview | not a toolbar tab | one ambient spatial gesture |
| Memory | no default button | appears through explicit memory request or a calm relevant surface |
| Commitment | no default button | work object appears when relevant or explicitly requested |
| Proactive policy | no slider on Home | deliberate operating-space decision later |
| Activity | no generic “run” button | exists only when a real activity/offer exists |
| Confirmation | yes/no/adjust are valid, but typed | focused decision surface; never generic arbitrary action |
| Skills / permissions | no ordinary Home controls | deliberate operating space, after safe projections |
| Model switch | not a chat-adjacent shortcut | deliberate operating action, preserving manual-only contract |
| Emergency Stop | **yes, exceptional** | always reachable safety control; separate visual language |

## 7. First launch and return after absence

### First launch

The empty Home opens as a calm room with Masha already there. There is no
wizard, feature tour, checklist, or dashboard. The conversational invitation
is readable but small: she is present first, the surface second. After the
first sent message, the Home may reveal the conversation shelf gesture; other
capabilities remain undisclosed until a real context exists.

What persists after first launch is only actual existing local state: a
conversation after its first persisted message, and separately any explicit
memory/commitment decision. The UI never invents a “setup completed” record.

### Return after absence — confirmed storyboard

```text
return home
→ ambient transition restores the room
→ Masha is calm, settled, attention gently toward Misha
→ deterministic short pause
→ soft invitation: «С возвращением. С чего начнём?»
→ only then, if a real high-relevance item exists, it becomes a small
  contextual object; conversation remains unobscured
→ Misha may speak, open Home, select the item, or simply leave it alone
```

The pause, placement, room transition and eligibility are deterministic.
The content may travel through the ordinary conversation path only once a
separate approved contract proves it cannot create an unsolicited duplicate
history message or claim a capability. No LLM decides timing, layout, visual
state or priority.

**Current gap:** the desktop host does not yet have an absence-aware
application projection or manual privacy policy. Therefore this storyboard is
design-only; it must not be simulated by frontend timing alone.

## 8. Required user-journey storyboards

These are the agreed language for future implementation; items marked GAP need
a safe application projection before their renderer exists.

| Scenario | Space behaviour |
|---|---|
| Ordinary conversation | Misha writes; Masha becomes attentive; a soft right-side surface opens. During local processing she turns inward; on a real answer she returns attention to Misha. The surface stays as the current context without covering her. |
| New conversation | Misha uses the subtle New conversation action. The old thread remains on the shelf; the current surface clears without suggesting deletion. Masha returns to a calm invitation. |
| Return to old conversation | The shelf opens temporarily; Misha chooses a familiar thread; it comes forward and the shelf recedes. Masha remains the anchor, not an entry in a list. |
| Long conversation | The surface grows internally and scrolls; the room does not lurch or force the reader to the bottom. Earlier history needs an explicit, later load-more interaction. |
| Pending confirmation (GAP) | A real typed proposal takes the focused decision place. Masha is attentive to the surface; the room quiets. Confirm, reject, or adjust resolve the actual proposal, not a generic UI state. |
| Activity (GAP) | A verified activity opens the workspace. Masha turns toward it; conversation remains available. Waiting, failure, cancellation and completion are named honestly and only from real lifecycle state. |
| Commitment approaching due (GAP) | A relevant work object appears softly after presence/invitation. It can be opened, completed through the existing explicit flow, or deferred with “не сейчас”; it does not accuse or diagnose. |
| Proactive reminder (GAP) | A delivered, deterministic candidate becomes a small invitation. It may be acknowledged or dismissed; no new candidate is fabricated by the renderer. |
| Check-in (GAP) | After a policy-authorised absence event, Masha offers a calm check-in. Absence is a signal, not a diagnosis; “не сейчас” restores quiet. |
| Emergency Stop | The safety control engages an independent pause overlay. Masha remains present; active autonomous work visibly pauses. Conversation and draft remain available. Resume clears the latch but starts nothing. |
| Model unavailable | Masha stays visually present. The conversation surface says the local model is unavailable; it does not fabricate a reply. A future retry is only enabled after an explicit contract. |

## 9. Safety, privacy and focus rules

### Safety

- Safety is independent from proactive off, model unavailable, daemon stopped,
  pending confirmation and activity failure.
- Stop should look like a deliberate pause of autonomous action, not a red
  technical badge or total application failure.
- Stop does not remove conversation, draft, history, Identity, Memory,
  Commitment or permissions.
- Resume means “permission to consider future authorised work again”, never
  “restart everything”.

### Privacy

Manual privacy mode is the chosen policy. Window focus loss alone changes no
content, state, or persistence. When later implemented, manual privacy must
mask the renderer only; it must not erase/reload/re-query conversation history
or trigger model work. Focus restoration returns exactly to the previous room
and surface state.

## 10. Explicitly rejected UI patterns

- permanent sidebar, dashboard or page navigation as the Home default;
- a grid of cards representing every backend subsystem;
- generic “Loading…” screens, permanent spinners and fake progress;
- a chat rectangle that permanently dominates/obscures Masha;
- notification dumps on return after absence;
- model-selected scenes, moods, layout, safety state or animation;
- raw IDs, JSON, audit details, SQLite terms or developer health dumps;
- showing voice, media, devices, RAG or tools as if they are available now;
- treating check-in as a mental-health diagnosis;
- making special evening a status indicator or default outfit.

## 11. Smallest architectural extensions identified

No extension is implemented by this workshop.

| UX requirement | Missing safe contract | Smallest future extension |
|---|---|---|
| Home gesture / “alive now” | bounded actionable Home view | one read-only `HomeAttentionView` composed from existing status and typed pending records; no service handles |
| Stop/resume in desktop Home | facade exists, closed bridge lacks allowlisted commands | two typed bridge actions returning `SafetyView`; no new safety semantics |
| Return-after-absence welcome | absence/relevance UI projection | read-only welcome candidate with deterministic eligibility and no generated message persistence |
| Pending confirmation | unified typed pending projection | application view enumerating existing proposal categories and allowed resolutions |
| Real activity surface | application-owned read view | bounded activity/run summary plus lifecycle events from existing receipts/state |
| Commitment/proactive objects | Home-facing read/ack views | typed views over existing records/lifecycles, never direct SQLite access |
| Manual privacy | operating preference/host projection | explicit local renderer-only privacy state; no hidden focus trigger |

If any of these prove to require a change to Identity, Memory, Commitment,
Temporal, Proactive, Agent Loop or Safety semantics, implementation stops for a
separate architectural decision.

## 12. Next implementation stage

**Recommended: UI-06B — Home Attention & Safety Slice.**

This is intentionally narrower than a full Home control centre:

```text
existing MashaApplication status + SafetyView
→ bounded read-only Home Attention projection
→ closed bridge actions for Stop / Resume only
→ deterministic presentation event / temporary Home overview surface
```

It validates the new grammar with the smallest truthful capability set:
conversation remains primary, the Home gesture reveals only actual current
state, and Stop remains always reachable. It does not expose Memory,
Commitments, Proactive, Activities, Skills, model switching or privacy before
their own projections and interaction contracts are approved.

# UI-05.5 / UI-06 — Full UI/UX Capability Audit

Дата аудита: 2026-08-11  
Статус: **DESIGN / NO PRODUCTION CHANGE**

## Executive summary

Masha Home уже имеет необычно сильное основание: локальная личность Маши,
подтверждаемая память, время и обязательства, управляемая инициативность,
границы навыков и аварийная остановка. Но desktop Home пока является честным
первым **conversation shell**, а не полным местом, через которое человек может
воспользоваться этими возможностями.

Сегодня без CLI Миша интуитивно поймёт, где Маша, как написать ей, что она
думает/отвечает, как начать чистую ветку и как вернуться к нескольким недавним
разговорам. Он не сможет понять, что именно Маша помнит, какие обязательства
есть, что требует решения, как работают инициативность и stop, какие навыки
установлены или что делает Agent Loop. Эти возможности существуют в коде, но
не существуют в пользовательском интерфейсе; это **GAP**, а не частичная
готовность.

Следующий этап не должен быть набором страниц. Его задача — создать
**Interaction Grammar Дома**: постоянные, контекстные и временные способы
увидеть состояние и открыть одну уже существующую возможность через surface,
не раскрывая SQLite, UUID, CLI-термины или dashboard.

## Scope and evidence

Проверены фактические `backend/application`, `backend/presentation`, desktop
host/bridge, conversation, memory, temporal/proactive, runtime safety,
skills/permissions/agent loop, CLI entry points и UI-01…UI-05E документация.

- Полный regression: **342 passed** (`.venv\\Scripts\\python.exe -m pytest -q`).
- Рабочее дерево на начало аудита: чистое, HEAD `bc4e16b`.
- Аудит не меняет production-код, Presentation Runtime, доменные контракты или
  SQLite schema.
- `ARCHITECTURE_SNAPSHOT.md` полезен как исторический источник, но его ранние
  верхние разделы не являются полным индексом поздних Stage 13–16/UI-05
  реализаций; фактический код и тесты имеют приоритет.

## Capability map

Легенда: **Yes** — есть и доступно в текущем desktop Home; **CLI** — реально
работает, но только через командную строку; **Contract** — имеется безопасный
контракт/Presentation Runtime, но нет UI; **No** — не реализовано.

| Capability | Backend | Application boundary | Presentation | UI now | How used now | GAP / blocker | Priority |
|---|---|---|---|---|---|---|---|
| Conversation | Yes | Yes | Yes | Yes | Home composer | no streaming, retry/cancel/markdown | P0 |
| Conversations/history | Yes, JSON local | Yes | partial | Yes | Recent list, New conversation | only 8 summaries/16 messages; no title/search/long-history paging | P0 |
| Identity / visual identity | Yes | Yes, read-only assets | Yes | Yes, bounded scenes | Home | only 7 registered scene assets; several semantics inactive | P0 |
| Long-term Memory | Yes, SQLite + audit | No UI-facing boundary | Contract only | CLI | chat intents / `memory` commands | no safe user-facing read/proposal surface | P0 |
| Commitments | Yes, SQLite + audit | No | Contract only | CLI | chat intent / `commitments` | no commitment surface, due/complete UX | P0 |
| Temporal | Yes, UTC/Moscow deterministic engine | indirect only | Contract only | No | conversation/CLI/runtime | time is not made legible in Home | P1 |
| Proactive reminders | Yes | status aggregation only | Contract only | No | CLI/runtime | delivery/acknowledgement not visible | P0 |
| Check-in | Yes | status count only | Contract only | No | runtime/CLI | candidate, message and response lifecycle absent from Home | P1 |
| Model profiles | Yes | Yes | model overlay | read-only label | CLI `model` | no manual profile switch UI; no human availability detail | P1 |
| Activities | Agent/presentation contracts Yes | no public activity boundary | Yes | No | CLI agent receipts | UI cannot observe real activity lifecycle | P0 |
| Confirmations | proposal flows Yes | no unified boundary | Yes | workshop only | CLI/conversation confirmation | no focused, typed confirmation surface | P0 |
| Skills | registry/install Yes | no | Contract only | No | `skills` CLI | discovery/install/integrity UI absent | P1 |
| Permissions | Yes | status snapshot only | safety overlay | No | `permissions` CLI | inspect/grant/revoke/approval UI absent | P1 |
| Agent Loop | bounded local loop Yes | no | Activity contract | No | `agent` CLI | no plan/run/receipt UI boundary | P1 |
| Emergency Stop | Yes | Yes | Yes | no control | `permissions stop/resume` | Home can display state but cannot act | P0 |
| Runtime mode / daemon | Yes | status snapshot | yes | no | CLI/background launcher | manual/background meaning opaque | P1 |
| Privacy | Presentation contract only | no preference contract | reducer supports unfocused | No | none | policy and host behaviour undecided | P1 |
| Voice readiness | Design only | No | Contract/design | No | none | no audio/interrupt/capture boundary | P2 |
| Media readiness | No | No | surface concept only | No | none | no media domain/boundary | P2 |
| Devices/environment | No | No | composition concept only | No | none | separate external-device boundary required | P3 |
| Long-running operations | bounded agent/runtime exists | no public run projection | activity model Yes | No | CLI receipts | no read-only activity feed or controls | P0 |
| Errors/unavailable | Yes | controlled conversation result | model unavailable state | partial | Home conversation | no timeout retry/cancel; health detail hidden | P0 |
| Settings/preferences | scattered local stores | model/status only | design only | No | CLI/config | needs operating-preferences boundary, not a raw settings page | P1 |
| Diagnostics/developer | Yes | status partly | no | No | `status`, `receipts`, raw CLI | should remain deliberately separate from normal Home | P2 |

## Current user journey map

| Journey | Actual state | UX judgement |
|---|---|---|
| First launch / returning home | opens room, Masha, latest actual conversation and composer | **READY**, but little orientation about available abilities |
| Normal, new, and recent conversation | send one turn, New conversation, open recent thread | **IMPLEMENTED**, bounded and local |
| Long conversation | transcript scrolls, but only latest 16 messages load | **GAP**: no loading earlier/history orientation |
| Masha listening/thinking/responding | deterministic scene switches, one send in flight | **IMPLEMENTED**, no streaming or cancellation |
| Model unavailable / timeout | controlled error, Masha remains visible | **PARTIAL**: no actionable retry/diagnostic distinction |
| Model switch | backend/CLI only | **GAP** |
| Memory proposal / confirmation | deterministic, explicit and audited | **CLI/conversation intent only**, no Home UX |
| Commitment creation / due / completion | deterministic, explicit and audited | **CLI/conversation intent only**, no Home UX |
| Proactive reminder / check-in | event/lifecycle/delivery backend exists | **GAP**: not exposed in Home |
| Proactive disabled / background mode | state aggregated | **GAP**: no human explanation/control in Home |
| Emergency stop / resume | persistent latch works; normal chat remains independent | **GAP**: not exposed as a user control |
| Activity queued/running/waiting/completed/failed | PresentationReducer models all states | **GAP**: no application activity projection or real renderer path |
| Skill discovery/install/permission | local registry, explicit proposal and integrity checks | **CLI only** |
| Agent run / approval / result | bounded receipt-first loop and CLI journal | **CLI only** |
| Background/daemon / return after absence | explicit launcher and daily runtime exist | **GAP**: Home has no legible ambient/recovery story |
| Privacy/unfocused window | state contract exists | **No operational UX** |
| Future voice, media, environment | design concepts only | **FUTURE**, must not be represented as available |

## Mental model for Misha

The Home must communicate five truths without requiring a menu:

1. **Маша рядом.** The room and her presence are the stable anchor, not a
   decoration behind a chat.
2. **Разговор — способ попросить и понять.** The composer is always the
   lowest-friction path; it never claims that an operation happened before its
   deterministic result exists.
3. **Вещи с последствиями становятся предметами внимания.** Memory,
   commitment, permission, and confirmation appear as temporary, named
   surfaces only when relevant, never as hidden model claims.
4. **Дом показывает, что происходит, но не прячет власть.** Model unavailable,
   waiting for a decision, activity, proactive autonomy and emergency stop are
   semantically distinct.
5. **Миша сохраняет последнюю инстанцию.** Masha may formulate, propose and
   work in allowed bounds; the UI makes the boundary visible and offers a
   simple stop.

## Interaction grammar: one living space, not a menu

### Persistent but quiet

- Masha and the room.
- Composer / current conversation context.
- A minimal orientation mark (local-only state, never a dashboard).
- A discoverable but visually quiet **Home gesture**: one click/keyboard
  affordance opening a transient “what is alive now” layer, not navigation.
- Safety stop must be always reachable after its semantics and confirmation
  language are approved; it should never be a permanent flashing alarm.

### Contextual surfaces

- Conversation is present while talking, then can recede.
- A confirmation surface takes foreground only while an explicit mutation or
  permission needs Misha's choice.
- An activity surface occupies the workspace only while a real activity exists.
- A commitment can appear as a work object when relevant (upcoming, due,
  completion), not as a permanent task page.
- A proactive/check-in surface appears only after the deterministic runtime has
  already created a candidate/delivery state.

### Never persistent

- UUIDs, SQLite/audit details, raw proposal payloads, model capability lists,
  agent receipts, developer health checks, all settings categories, or a grid
  of empty cards.

### Spatial assignment (design, not implementation)

| Human meaning | Natural Home expression |
|---|---|
| talk / resume a thread | soft right-side conversation surface near Masha |
| remember / revisit a shared thread | calm side surface beside Masha, lower visual priority |
| commitment / a piece of work | desk/table work object; becomes focused near its deadline |
| active work | workspace opens; conversation stays available but quieter |
| confirmation | focused decision surface, never disguised as chat text |
| proactive / check-in | small invitation from Masha, with an unambiguous “not now” |
| safety | independent safety overlay with clear pause/resume meaning |
| operating preferences | separate deliberate “Home mode”, entered intentionally and exited cleanly |

## Masha as UI

The renderer already has composable axes (pose, expression, attention,
activity, ambient and independent overlays). It must remain deterministic:
assistant text or LLM emotion guesses cannot select an image.

| Semantic signal | Primary carrier | Current implementation |
|---|---|---|
| presence / inviting interaction | Masha + room | canonical idle scene |
| listening / waiting | Masha | `listening-v1`, turn start |
| thinking | Masha + subtle ambient | `thinking-candidate`, turn in flight |
| speaking | Masha + conversation surface | conversation candidate after complete response |
| working | Masha + future workspace | scene registry exists; no real Activity source |
| calm disagreement | Masha | visual asset registered, but no approved deterministic cue reaches it |
| quiet beside | Masha + quiet room | visual asset registered, but no approved deterministic cue reaches it |
| confirmation | focused surface | contract/workshop only |
| proactive/check-in | invitation surface | contract/workshop only |
| autonomy stopped | independent overlay + room tone | state contract exists; not rendered in desktop shell |
| privacy/unfocused | room veil + content masking | contract exists; no host policy/rendering |

**Asset conclusion.** Keep full-scene, room-plus-Masha compositions, their calm
right-side quiet zone, and deterministic scene registry/crossfade. Do not use
cut-out character overlays, fake scene selection from text, generic visual
effects, or special-evening as a default state. The current assets need a
deliberate matrix before generating more images.

## Visual asset matrix

| Family | Needed now | State | Notes |
|---|---|---|---|
| Canonical idle | 1 full-scene master | Implemented | current visual anchor |
| Conversation / listening | 2 full-scene frames | Implemented | distinct send/wait/response communication |
| Thinking | 1 full-scene frame | Implemented | bounded deterministic use |
| Working | 1 full-scene frame | Implemented asset, no runtime source | do not expand before Activity UX |
| Quiet beside | 1 reviewed frame | Implemented asset, inactive | requires approved explicit cue |
| Firm disagreement | 1 reviewed frame | Implemented asset, inactive | requires approved explicit cue |
| Confirmation/check-in/safety/privacy | no new Masha frame required first | GAP in layers | use surface/ambient/overlay language |
| Emotion range | matrix first, not image batch | Future | only add when event semantics exist |
| Outfits / special evening | optional, deliberate | provisional | not default and not a status indicator |
| Motion | crossfade now | partial | later reduced-motion, attention/micro-motion contract |

## Conversation UX assessment

**Implemented:** local bridge, bounded input (4,000 chars), one in-flight
turn, read-only recent branch list, explicit New conversation, scrolling that
does not force a reader away from old messages, controlled unavailable result,
and deterministic scene changes.

**P0 gaps:** retry after timeout/unavailable; manual cancellation semantics;
loading earlier messages; clear active-thread identity; keyboard shortcut
contract; text selection/copy ergonomics; accessible focus states; reliable
long-message layout; an honest compact capability hint on first use.

**Not current capability:** streaming, Markdown/code rendering, images,
attachments, search, branch/fork semantics. They must not be implied by the
visual UI before a safe content/attachment boundary exists.

### Multi-conversation models (choose later)

1. **Conversation shelf (recommended):** a small transient shelf opens from
   “Разговоры”, showing recent contexts as physical notes; select one and the
   shelf disappears. Preserves the current design and avoids a sidebar.
2. **Table of threads:** a subtle desk object opens a focused temporary surface
   for longer history/search. Better when there are many conversations.
3. **Context trail:** a compact breadcrumb in the conversation surface plus a
   “вернуться к…” gesture. Good supplement, insufficient alone for discovery.

## Activity, confirmation, and operation UX assessment

The Presentation Runtime already models queued, running, waiting, completed,
failed and cancelled activities. That is a **READY contract**, not a working
Home feature: the application boundary has no UI-safe activity projection and
the desktop host receives no real Agent Run lifecycle.

The first implementation should not simulate progress. It should add a
read-only activity projection from existing receipts/state, then a focused
surface for an actual run. Conversation remains usable, while the workspace
shows a named task, current known step, waiting/blocked reason, and only
verified result. No central spinner and no fabricated progress.

Confirmation must be typed by the existing domain operation (memory proposal,
commitment mutation, skill installation, permission, help/reflection). It
cannot be a generic “Yes” component that performs arbitrary actions.

## Memory, commitment, temporal, proactive UX assessment

The human model should be a single chain:

```text
«Маша помнит»
→ confirmed information / shared thread
→ «у меня есть обязательство»
→ deterministic due state
→ eligible local reminder/check-in
→ visible invitation or decision
→ Misha acknowledges, dismisses, confirms, completes, or declines
```

Memory is not chat history. A commitment is not a fact and is not complete
because it was mentioned. A proactive delivery is not a memory mutation.
The UI needs to preserve these distinctions in language and surface type,
without exposing underlying records.

P0 work is not a Memory page: it is a unified, explicit **decision and work
surface** that can show a pending confirmation or a relevant commitment. A
separate calm “remembered/shared” surface can follow once a read-only
application boundary exists.

## Safety, privacy and availability assessment

The architecture correctly distinguishes these states. Current desktop UI
largely collapses them into a small runtime string or a conversation error.

| State | Required human meaning | UI direction |
|---|---|---|
| proactive off | Masha will not initiate | quiet operational statement, not danger |
| autonomy stopped | new autonomous steps/cycles blocked; chat remains available | independent safety overlay + reachable resume |
| model unavailable | Masha cannot formulate now; no data left the computer | local availability surface with retry/diagnostic path |
| daemon stopped | no background heartbeat currently runs | operating state, not an error if manual mode |
| awaiting confirmation | Misha's decision is required; nothing happened yet | focused decision surface |
| activity paused/failed | task did not silently continue/finish | workspace status, preserve result evidence |
| privacy/unfocused | screen content is masked, not erased | user-approved host policy + visual veil |

Emergency Stop must never delete drafts/history, change Identity/Memory, or
block ordinary conversation merely because proactive/agent activity paused.

## Future readiness

| Area | Preserve now | Do not build now |
|---|---|---|
| Voice | listening/speaking/interruption presentation semantics; composer can coexist as transcript | capture, TTS, VAD, audio transport |
| Media | `InteractionSurface` can host bounded media | arbitrary filesystem/gallery/media generation UI |
| Environment | room has immutable base, configurable user preferences, dynamic application state, and Masha-proposable changes | device control, external event feeds, arbitrary frontend code |

For future room evolution: the base room and identity anchors are immutable;
user preferences are explicit persistent settings; dynamic state is application
owned; Masha may only create a proposal that a human/policy approves before
presentation changes. The LLM never writes frontend code or layout directly.

## Gap matrix

| Capability | Backend | Boundary | Presentation | UI/UX | Priority | Blocker | Human decision | Recommended stage |
|---|---|---|---|---|---|---|---|---|
| First-use orientation/capability language | Yes facts | partial | Yes | Gap | P0 | no interaction grammar | what must always be discoverable | UI-06A |
| Safety stop/resume | Yes | Yes | Yes | Gap | P0 | closed bridge command absent | degree of visual prominence | UI-06A |
| Pending typed confirmation | Yes | No unified | Yes | Gap | P0 | application projection required | confirmation hierarchy | UI-06B |
| Activity visibility | Yes | No | Yes | Gap | P0 | read-only run/activity view required | how much work detail is visible | UI-06B |
| Commitments in Home | Yes | No | partial | Gap | P0 | UI-safe read/proposal boundary | desk/work-object metaphor | UI-06C |
| Proactive/check-in in Home | Yes | status partial | Yes | Gap | P0 | delivery/ack boundary | desired visible initiative language | UI-06D |
| Conversation robustness | Yes | Yes | Yes | partial | P0 | bounded history/result contract extension | retry/cancel behaviour | UI-06A |
| Memory/shared continuity | Yes | No | partial | Gap | P1 | read-only boundary | how visible remembered material should be | UI-06E |
| Model profiles | Yes | Yes | Yes | Gap | P1 | bridge control/read UI | where model control belongs | UI-06F |
| Permissions/skills | Yes | status partial | partial | Gap | P1 | focused boundary | desired approval language | UI-06G |
| Privacy/unfocus | contract | No policy | Yes | Gap | P1 | preference/host decision | masking trigger and depth | UI-06H |
| Voice | No runtime | No | Design | Future | P2 | whole audio stack | voice-first boundaries | later |
| Media | No | No | Concept | Future | P2 | media domain | ownership/storage policy | later |
| Devices/environment | No | No | Concept | Future | P3 | external-event/device boundary | which devices, consent and safety | research |

## Architectural invariants — do not change for UI work

- Identity remains owned by `IdentityKernel`, never by the model or renderer.
- SQLite long-term Memory is local and changes only through its explicit
  proposal/confirmation contracts; chat history is separate JSON history.
- Temporal truth, due state and event identity are deterministic; the LLM does
  not calculate dates, make delivery decisions or mutate commitments.
- `ModelRouter` and manual active `ModelProfile` remain the only execution
  selection mechanism: no UI-triggered fallback or automatic switching.
- Presentation Runtime/reducer stays deterministic and has no domain authority.
- Desktop renderer goes only through `MashaApplication` and a closed local
  bridge; no direct SQLite, Memory, Identity, service handle, HTTP/cloud or
  arbitrary RPC access.
- Emergency stop is a higher-priority persistent latch; release does not start
  activities.
- Skill declaration/install/permission/agent execution remain distinct; UI
  cannot compress them into a one-click “enable agent”.

## Freely improvable presentation work

- Scene composition, typography, spacing, responsive behaviour and reduced
  motion after visual review.
- Transition pacing and non-intrusive ambient treatment.
- Surface choreography while respecting `CompositionPlan` and explicit
  lifecycle.
- Readability/accessibility and keyboard interaction.
- Full-scene asset quality, only after an approved semantic asset matrix.

## Roadmap: next six UX stages

1. **UI-06A — Home Interaction Grammar & Conversation Reliability.** Define
   persistent/contextual/temporary affordances; add only needed closed bridge
   commands for safety and conversation recovery, plus first-use orientation.
2. **UI-06B — Real Activity & Confirmation Surfaces.** Create UI-safe,
   read-only projections for existing activity/pending controls and render real
   lifecycle/typed confirmations; no simulated agent behaviour.
3. **UI-06C — Commitments as Work Objects.** Read commitments and explicit
   mutation previews through an application boundary; show temporal state in
   the Home workspace.
4. **UI-06D — Proactive Presence.** Render real delivered reminder/check-in
   states, acknowledgement/dismiss controls and clear autonomy boundaries.
5. **UI-06E — Memory & Shared Continuity.** Add calm read/proposal surfaces for
   confirmed memory and shared threads; never use chat history as memory.
6. **UI-06F — Deliberate Home Mode.** Model profile, permissions, skills,
   privacy and diagnostics are grouped into intentional operating spaces,
   not a permanent dashboard. Privacy requires prior user decision.

Activities/confirmation come before full agent UI because they give the Home a
truthful universal way to show work and ask for a decision. Voice, media and
environment remain later independent programs of work.

## Questions requiring Misha's decision

1. What must always be reachable in one gesture: only conversation + Stop, or
   conversation + Stop + “what is alive now”?
2. Should privacy masking begin automatically when the window loses focus, or
   only on an explicit privacy gesture? What should remain visible when masked?
3. When returning after an absence, should Home first show a quiet presence,
   the most important pending item, or ask Misha which mode he wants?
4. How visually assertive may a due/overdue commitment be before it becomes
   intrusive? This sets the work-object hierarchy, not just its color.
5. Which of the three conversation models should mature first: transient shelf,
   desk of threads, or context trail? The audit recommends the shelf.
6. Should model profile switching remain a deliberate operating-mode action
   outside normal conversation, or be reachable from the conversation surface?
7. For future room evolution, which changes are acceptable as Masha proposals:
   only ambience/layout, or also user-approved room objects and routines?

## Recommendation

**Next stage: UI-06A — Home Interaction Grammar & Conversation Reliability.**

It is the smallest safe step that changes the answer to “what can I do here?”
without converting the Home into a dashboard or prematurely building Memory,
Agent, or Settings pages. It should start with a design contract and an audit
of exact existing application methods; implementation only follows after the
interaction grammar and the seven human decisions above are settled.

## Final answer to the first-user test

**Not yet, not fully.** Misha can find Masha, talk, start a clean conversation,
and reopen a few recent ones without instruction. He cannot yet intuitively
discover the real boundaries of memory, commitments, initiative, safety,
activities, permissions, skills, model choice, or what has changed while he
was away. The correct order is: make the Home's interaction grammar and safety
legible; make real work and confirmations visible; then bring commitments,
proactivity, memory and deliberate operating controls into their natural
surfaces.

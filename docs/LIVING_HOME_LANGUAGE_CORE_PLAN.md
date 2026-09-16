# Masha Home — Living Language Core Plan

> Current work follows [AGENT_COHERENCE_PLAN.md](AGENT_COHERENCE_PLAN.md).
> The live dialogue failed despite the green gates below. These checkpoints
> record implemented contracts, not acceptance of overall conversational quality.

### Time / memory / Web integration and accumulated stage gate — 2026-09-15

- Found and reproduced a real ownership gap: WebSearchHandoffAdapter did not
  forward conversation message IDs. The semantic search path could not inherit
  the last completed public topic, while the legacy explicit path could.
- Both now use one _search_context implementation. A referential continuation
  inherits only a completed search belonging to this conversation, including
  beyond the short model-history window. Unrelated/other-evening IDs do not
  inherit it. Neither IDs nor local memory are passed to the search provider.
  No new authority, network policy, relevance threshold or model prompt changes.
- Extended an existing integrated test in ordinary and evening modes: Saratov
  midnight is the next day while UTC is not; a relevant remembered note keeps
  its original date and stays separate from external evidence; Web-assisted
  turns create no passive memory. Initial fixture note was not sufficiently
  query-relevant, so the fixture was corrected, not retrieval scoring.
- 186 affected tests passed. One final accumulated deterministic gate:
  696 passed, 2 skipped (Windows symlink unavailable); 23 frontend/scene tests
  passed. compileall, node --check and git diff --check passed. No live external
  network or mutation in this checkpoint. No commit/push.
- Cleanup is intentionally evidence-based: removed the duplicate Web topic
  resolution branch, not still-used degraded capability routes. Broader legacy
  removal and Docs proposal revision are NOT claimed complete.
- Next human acceptance: mail -> "напомни об этом" -> correction -> confirmation;
  Calendar draft -> correction -> confirmation; successful Web topic -> a
  referential fresh follow-up. Verify evening/ordinary history remains separate.
  Further changes should follow a concrete failed trace, not another broad rewrite.

### Calendar proposal revision — 2026-09-15

- The same semantic draft validator now handles Calendar Create/Update. No
  extra phrase grammar, dialogue state or automatic confirmation. Exact existing
  owner decision forms still run first, so Yes/No never needs a model.
- Calendar revisions require an exact pristine proposed receipt, with no
  confirmation/verification timestamp. Existing Update target ID, before state
  and etag stay application-owned; changing its subject cannot retarget it.
  Date/time/duration change only the desired state. Already executing/uncertain
  operations must use recovery, never this revision path.
- A new unconfirmed operation receipt is persisted before atomically replacing
  the preview. Old preview is cancelled; old receipt is retired as rejected.
  Rejected writers now fail closed. A crash before preview publication leaves
  the old preview valid; an orphan proposed receipt has no confirmation authority.
  Failed audit retirement after publication cannot reactivate the cancelled
  preview. No cross-file transaction or second recovery framework was added.
- Restart, stale buttons, provider conflict, receipt/preview write failure and
  failed retirement are tested with fake Google transports. Real configured
  masha-fast:4b understood "Давай всё-таки на 11 утра" for both create and update:
  new pending preview, correct Saratov time, zero additional Google transport
  calls. 180 affected tests passed; compileall and git diff --check passed.
  No real Calendar mutation or full-suite repetition.
- Next: integrated time/memory/fresh-Web checks, then remove only proven
  superseded paths and run the single final gate. Docs draft revision is not
  included; its body/recovery contract remains untouched. No commit/push.

### Pending reminder draft revision — 2026-09-15

- Closed the next boundary for Home reminders: after a preview, a natural
  correction uses the SAME semantic follow-up wire and field validator against
  the application's unconfirmed draft. No second PendingResolution, no reopened
  terminal dialogue and no phrase-specific correction router.
- Only the reminder owner changes subject/date/time after grounding. The store
  atomically cancels the obsolete preview and publishes one revised pending
  preview, preserving the future commitment ID. A stale confirmation ID cannot
  save the new version. No memory write or reminder scheduling before fresh Yes.
- Invalid evidence, ambiguous evening time, operation switching, timeout and
  persistence failure leave the original preview intact. An ordinary interruption
  does not revise it. Latest pending projection and restart recovery are covered.
- 159 affected tests passed. Configured local masha-fast:4b probe:
  09:00 draft -> "Нет, лучше в 10 утра" -> pending 10:00 Saratov,
  unchanged subject/date; zero memory/provider mutations. No full-suite rerun.
- Scope intentionally limited to unconfirmed Home reminders. Calendar/Docs
  proposals carry durable external-operation receipts; do not apply this local
  replacement blindly to them. Their revision needs the existing operation
  owners. Next: extend only where the receipt lifecycle permits, then the
  planned time/memory/fresh-Web integration gate and proven legacy cleanup.
- No commit/push. All previous local edits preserved.

### Compound clarification continuity — 2026-09-15

- Reproduced: while asking for date, the deterministic date normalizer consumed
  a whole reply, silently dropping a time correction or treating an ordinary
  sentence mentioning tomorrow as a date answer. In production, only a short
  date answer keeps the fast path; compound answers use the existing semantic
  follow-up owner. Failure preserves pending state without applying a fragment.
- Real configured FAST probes also exposed inconsistent follow-up JSON. The
  request now supplies only pending-candidate vocabulary and a direct-union
  constrained schema: all fields explicit, ordinary replies carry no updates,
  selection/evidence paired, and add/correct modes reflect known slot state.
  Temporal values cannot use text-enrichment mode. Pydantic/grounding remain
  authoritative; no model response is repaired into execution authority.
- A rejected correction of an already known field blocks progression instead
  of using the OLD value merely because another accepted field fills the last
  missing requirement. No new pending owner or confirmation mechanism.
- 114 focused semantic/dialogue/grounding/reminder/Calendar tests passed.
  Real FAST: date question -> "Нет, лучше послезавтра в 10 утра" preserves
  subject, produces date + 10:00; ordinary "Я завтра хочу поговорить о книгах"
  yields NOT_A_FOLLOW_UP with original state intact. Fixed test clock, no real
  provider actions. compileall/diff check passed. No full-suite repetition.
- Next distinct boundary: revising an ALREADY SHOWN proposal before approval.
  This checkpoint covers clarification BEFORE handoff, not proposal revision.
  Keep application ownership and explicit confirmation; do not reopen a
  terminal DialogueResolution or let a model mutate a pending operation.
  No commit/push.

### Mail selection / private conversation lifecycle — 2026-09-14

- User manually accepted the delete-history control and the hidden evening
  entry in Corner. No commit/push. Existing reminder/memory edits preserved.
- Real FAST interpretation exposed two application filter defects: generic
  mailbox evidence was not a supported view, and the memory tokenizer dropped
  "сегодня" from temporal mail filters. Mail view normalization now retains
  temporal words. An action-only optional view uses the shared listing-command
  vocabulary and existing unread default AFTER validated read handoff; no new
  routing authority. Explicit subject overrides a stale/default unread view.
- Named reading searches real mailbox subjects, reads exactly one match, lists
  multiple matches and never invents a provider ID. Legacy read-name delegates
  to this same owner. Empty results replace stale lists; a bare ordinal after
  an empty mail list cannot trigger unrelated ordinary-model prose.
- Conversation space is durable (ordinary/special_evening). Mode changes use
  separate histories/pending IDs. Ordinary startup/shelf/check-in history excludes
  evening conversations. Passive memory detection is disabled for evening;
  explicit memory requests still use existing confirmation. Scene assets,
  proximity/continuity and pause boundaries are preserved. Fixed one missing
  separator in existing evening instructions; no attempt to remove model safety.
- Cross + explicit dialog deletes the selected transcript and clarification
  state, cancels unconfirmed proposals and rejects pending passive candidates.
  Confirmed memories, real tasks/events, action audit/receipts and old backups
  remain. New evening chats are separate; OLD unlabelled chats are not guessed
  or bulk-migrated. User can delete them deliberately.
- Validation: one full gate 668 passed / 2 Windows-symlink skips; final affected
  gate 123 passed after action-only-view normalization. All Node/static/scene
  tests, compileall and diff check passed. Local FAST-only probes used fake mail,
  never real mailbox/provider writes. Subject read -> topic search + one read;
  today -> today; generic check -> unread via corrected application normalization.
- Remaining manual acceptance: general mailbox check, today's list, read by
  title (even if unread list empty), ordinal from the newly shown real list.
  Autonomous extraction of promises from message bodies remains out of scope.

### Read-letter reminder continuity — 2026-09-14

- Successful mail reads mark one item focused in the existing presented set;
  list numbering stays intact. Model hints contain its human label, not private
  provider references or mail body. A new list resets focus.
- The existing slot normalizer metadata opts reminder subject into referenced
  text. Home resolves grounded deictic evidence to exactly one focused label;
  zero/multiple focus cannot supply a subject. Fresh/follow-up validation share
  this rule; no new routing grammar, state owner or mutation authority.
- Integrated component test: read first letter -> "Напомни завтра об этом" ->
  "Во сколько?" -> "9 утра" -> existing confirmation -> stored Saratov deadline.
  No record is written before confirmation. Real configured FAST resolver probe
  also kept the exact letter title and requested only the missing time.
- 114 focused/affected tests passed after correcting one strict hint-shape
  expectation. The single full gate had 654 passed, 2 skipped, 1 failed (that
  stale expectation for the added focused flag); full gate not repeated.
  All frontend Node tests, compileall and diff check passed.
- Manual Home acceptance remains: restart, read a letter, request a reminder
  about it, supply time, inspect preview, confirm. This binds the letter TITLE,
  not arbitrary obligations/dates inferred from its body. No commit/push.

### Memory context lifecycle — 2026-09-14

- User accepted the repeated custom reminder sound in live Home.
- Reproduced an active-memory projection defect: TurnContextEnvelopeBuilder
  ignored the recalled record state, relabelled historical records active, and
  took the six-item limit before filtering. A later current record was omitted.
- Language-context hints now accept only current/open/available states and apply
  the six-item bound after selection. Stored memory, historical recall for the
  conversational answer, lens selection and confirmation ownership are unchanged.
  Original temporal provenance remains attached to accepted hints.
- 71 focused/affected memory/context/semantic/dialogue tests passed; compileall
  and diff check passed. No full-suite repeat, live model call or commit/push.
- Next integrated acceptance target: read a letter -> refer to that content in
  a reminder request -> one clarification flow -> confirmed reminder. Check
  context continuity, not a new vocabulary of command phrases.

### Reminder sound — 2026-09-14

- User confirms live toast/audio delivery, requests a distinctive repeated cue.
- Desktop now uses an original two-note 1.8-second PCM chime via available Qt
  Multimedia, synthesized locally into an auto-removed temporary WAV. No new
  dependency/download. System beep remains the controlled audio fallback.
- One receipt starts three pulses at 0/4/8 seconds. Duplicate projections do
  not restart it; a newer reminder replaces the old series without overlapping.
  Successful acknowledge/dismiss, Emergency Stop and window close stop repeats.
- 15 focused Python tests and one renderer-route test passed; compileall/diff
  check passed. Actual loudness/pleasantness needs listening after Home restart.
  No commit/push; earlier local delivery-backlog changes preserved.

### Delivery backlog checkpoint — 2026-09-14

- Base HEAD observed: `40af080`, clean working tree before this pass.
- Reproduced a delivery starvation defect: six older delivered occurrences
  occupied the bounded temporal context forever, so the seventh never reached
  delivery. DailyRuntime now excludes delivered/terminal interaction IDs before
  the six-event projection. History/default temporal context stays unchanged;
  no memory records are deleted and policy checks remain in place.
- Delivered reminders still suppress unsolicited check-ins while awaiting user
  response, even though they no longer occupy delivery slots.
- Regression covers delivered/acknowledged/dismissed backlog, subsequent cycle
  after runtime reconstruction, no duplicate delivery, and retained context bound.
- Validation: 46 focused/affected Python tests, one renderer reminder-route test;
  compileall/diff check passed. No full pytest repeat, no live notifications,
  no commit/push. Physical toast/sound acceptance remains a manual check.

### Reminder delivery checkpoint — 2026-09-13

- User reports Calendar Update manual acceptance successful after previous patch.
- Removed model formulation from confirmed explicit-reminder delivery. The
  application projects the stored reminder text; local model failure can no
  longer delay that delivery or invent its content. Ordinary proactive check-ins
  and policy-controlled suggestions still use their existing model path.
- One integration test covers proposal/no early write, confirmation, Saratov
  deadline, no early delivery, Emergency Stop, delivery with zero model calls,
  repeated runtime construction, duplicate protection, and acknowledgement.
  It uses isolated SQLite and an injected clock, not real notifications.
- 53 focused/affected Python tests passed; renderer reminder-route Node test
  passed; compileall/diff check passed. Full pytest deliberately not repeated
  after the prior stage gate. No commit/push.
- Remaining manual acceptance: a near-future confirmed reminder while Home is
  open must produce one sound and visible toast without opening Home Attention.
  Automated renderer check is not proof that the physical audio cue was heard.
  Existing policy enabled/level/reminders switches and Emergency Stop remain
  authoritative. No Windows Scheduler or background mechanism was added.

### Live follow-up checkpoint — 2026-09-13

- Preview commitment now formats the persisted deadline in the configured Home
  timezone, not the OS timezone. The live 05:00Z deadline was already correct:
  09:00 Saratov; only the preview showed 08:00 Moscow.
- Resolved Mail listing views precede contextual single-item resolution. A
  previous presented list or redundant target cannot turn an unread listing
  into a request to select one letter. Unresolved single-item reads still ask.
- Response guard receives titles from current Calendar read evidence. Passive
  descriptions of those scheduled events are permitted; execution claims are
  not. All regex matches are checked so one grounded sentence cannot mask a
  later ungrounded claim. This reproduces a guard defect, not the unavailable
  raw model output of the historical live turn.
- Validation: 84 focused/affected tests + 34 human-reference/truth tests passed;
  compileall and diff check passed. No full-suite or live provider run in this
  checkpoint; no commit/push.
- Follow-up: Calendar target resolution now tries the existing local semantic
  role only when literal title matching found nothing. It supplies at most 20
  real titles already constrained by date/old time, never provider IDs. Exact
  returned-label membership is validated; multiple candidates or unavailable
  matching require clarification. The chosen event is freshly fetched and its
  title/date rechecked before preview. Confirmation/PATCH ownership is unchanged.
- Real FAST probe: "Завтрашний звонок маме перенеси на 12:00" produced Update,
  date 2026-09-14, time 12:00 with all slots accepted. Separate real FAST reference
  probe matched "звонок маме" to "чтобы я позвонил маме", not "встреча с врачом".
  Neither probe invoked Google or mutated data. No full model benchmark run.
- Missing-date follow-up contract proves "на завтра же" preserves subject and
  known 12:00. Historical repeated questions are not reproduced by these checks;
  do not claim all model extraction variability fixed or add speculative routes.
- Latest validation: 72 focused passed; one full pytest: 642 passed, 2 skipped
  (Windows symlink availability), 52.14s. Compileall/diff check passed.
- Next manual gate after restart: existing event paraphrase -> correct Update
  preview -> human confirmation -> fresh verified receipt. If a question repeats,
  inspect that exact live semantic/validation trace; no new phrase grammar.

Статус: прежние Gate 1–6 вошли в ветку. Ручная приёмка выявила дефект
отмены с новой просьбой после уже завершённого процесса; текущие исправления
остаются локальными, без commit/push.

### Текущий проход — 2026-09-13

- Согласовано: Home timezone `Europe/Saratov`. Утром/днём/вечером не задают
  точный час. Сегодня/завтра без времени требуют уточнения; известные поля
  сохраняются, повторно их спрашивать не нужно.
- Google: Calendar read/write, Drive read и Docs write переподключены через
  существующие OAuth CLI. Все четыре credentials прошли refresh и контрольный
  GET. Записи провайдеров не менялись. Consent остаётся действием пользователя;
  токены хранятся в Windows Credential Manager.
- Исправлено: явная отмена с отделённой новой просьбой разбирается независимо
  от наличия активного PendingResolution. Старый процесс, если есть, отменяется.
- Удалено устаревшее исключение `unsupported_action_preserves_legacy_owner`:
  валидное unsupported action без alternatives не теряется в старом разборе.
  Protected document content и infrastructure fallback остаются необходимыми.
- Focused dialogue/semantic: 65 passed; affected confirmation/Calendar/reference/
  context: 75 passed. Два реальных FAST turn дали clarification без ошибок:
  «ладно забыли, Напомни вечером позвонить маме» и «Напомни завтра позвонить маме».
- Финальный общий gate: 626 passed, 2 skipped (Windows symlinks), 51.48 s.
  `compileall` и `git diff --check` проходят. Frontend не затронут.
- Следующая ручная приёмка после перезапуска Home: отмена → напоминание →
  уточнение дня/времени → preview → подтверждение; проверить фактическую доставку.
  Почта → письмо → напоминание и Calendar Update также требуют ручного результата.
  Наличие Google grants/успешный GET не доказывают успешную будущую mutation.

Текущий runtime/stage-gate профиль: `fast`. Диагностика и acceptance не должны
молча подменять его `primary`; сравнительный прогон другого профиля возможен
только как отдельный явно запрошенный эксперимент.

Цель: Миша говорит с Машей естественно, а Дом один раз понимает смысл,
детерминированно проверяет его, продолжает диалог, передаёт работу владельцу
capability и сообщает только подтверждённый результат. Новая capability должна
подключаться описанием и application adapter, а не новой коллекцией фраз в
`ConversationService`.

## 1. Зафиксированная исходная точка

- ветка: `codex/universal-language-2g`;
- кодовый checkpoint: `9b9f2d8` плюс сохранённый незакоммиченный Slice 2G.1;
- focused semantic/Calendar/Mail regression: `99 passed`;
- полный Python regression: `1190 passed, 5 skipped`;
- реальный локальный benchmark `qwen3.5:9b`, 64 кейса:
  - JSON wire: 98.438%;
  - kind accuracy: 78.125%;
  - exact candidates: 75.0%;
  - clarification accuracy: 89.062%;
  - slot accuracy: 75.0%;
  - grounded slot evidence: 95.0%;
  - forbidden-action FPR: 0.0%;
  - DialogueCore end-to-end: 68.75%;
  - Calendar Update/Create confusion: 0.0%;
  - contextual Mail entity recognition: 0.0%;
  - ambiguous scheduling selection correctly absent: 40.0%.

Эта точка является regression baseline. Улучшение языка не имеет права снижать
границы authority, confirmation, receipt truth, privacy или recovery.

### Проверенный checkpoint 2026-08-30

Gate 0 и фундамент Gate 1–2 завершены в текущем незакоммиченном tree:

- `TurnContextEnvelope` собирается до semantic interpretation из единого Home
  clock, bounded recent conversation, active continuity, ACTIVE humanized
  memory, safe capability availability и последнего presented entity set;
- внутренние message/record/provider/conversation IDs и credentials не
  пересекают semantic boundary;
- fresh и follow-up resolver получают один и тот же envelope;
- текущая просьба несёт отдельное literal `action_request_evidence`; context не
  может сам создать action;
- incomplete operation-selection и ошибочный slot отклоняются независимо, не
  стирая валидные action/candidate;
- contextual Mail reference проходит semantic owner selection, после чего
  реальный объект повторно разрешает application registry;
- полный Python regression: `1201 passed, 5 skipped`;
- resident `qwen3.5:9b`, 64 cases: wire 100%, kind 96.875%, exact candidates
  93.75%, ordinary/forbidden FPR 0%, scheduling ambiguity 100%, DialogueCore
  E2E 81.25%, contextual entity recognition 66.667%;
- доказан отдельный runtime risk: выгруженный `qwen3.5:9b` загружается около
  26 секунд, поэтому 8-секундный semantic deadline даёт controlled timeout до
  прогрева. Это lifecycle problem, не semantic-quality результат; исправлять
  его следует отдельным bounded runtime срезом без startup network traffic.

### Проверенный checkpoint 2026-09-01

- Calendar Create/Read/Update/Delete, Reminder/Commitments, Mail Read/Delete/
  Archive, Drive/Docs/Disk read, Memory/Recall/Continuity и contextual Web
  проходят через единый semantic/dialogue ingress либо узкий защищённый
  structural owner;
- application adapters, confirmation, provider operation, verification и
  receipt truth остаются раздельными владельцами;
- `TurnContextEnvelope` сохраняет Home time, bounded conversation, ACTIVE
  memory, continuity и presented entities без provider IDs и секретов;
- conversation/dialogue core импортируется независимо от тяжёлой application
  composition; package-level public facade загружает `MashaApplication` и
  composition лениво, поэтому порядок импортов больше не скрывает цикл;
- старый второй local semantic classifier удалён; generic «поставь/запиши» не
  выбирает Calendar без grounded destination и сохраняет безопасную
  Calendar/Reminder неоднозначность;
- реальный FAST benchmark `qwen3.5:4b`, 67 cases: wire 94.03%, exact candidates
  95.522%, clarification 100%, forbidden-action FPR 0%, Create/Update confusion
  0%, contextual application resolution 100%, DialogueCore E2E 86.567%; четыре
  schema-error остаются контролируемыми fail-closed колебаниями малой модели;
- affected integration: 359 passed; финальный dialogue/application set:
  145 passed; renderer: 19 passed; production-like fake-provider smoke:
  16 passed;
- единственный полный Python gate: 1248 passed, 5 skipped и 3 устаревших
  fixture expectations. Fixtures приведены к новому generic-scheduling
  контракту, после чего их focused gate дал 6 passed; второй полный прогон
  намеренно не запускался по test-economy правилу;
- capability truth теперь выражает составные зависимости: Calendar Create
  зависит только от отдельного write connection, а Update/Delete — одновременно
  от read target resolution и write connection. Live-состояние `write ready +
  read needs reconnect` больше не объявляет изменение/удаление доступным;
  focused/affected gate: 133 + 32 passed;
- read reconnect для того же Google OAuth client сохраняет отдельные healthy
  Calendar/Drive write grants и их безопасные SecretRef metadata; live-проверка
  выявила и закрыла прежнее стирание write-ссылок. Connector lifecycle gate:
  46 passed;
- bounded live dialogue на FAST-профиле подтверждён для Calendar Read, Mail
  Read, Google Drive Read, Yandex Disk Read и Web Search: каждый ход пришёл в
  свой application handoff, read operations получили `completed_read`, Web
  сохранил source observation. Mail Delete дошёл до `waiting_confirmation`,
  а отказ завершился `rejected` без dispatch/provider mutation;
- подтверждённый live Mail Delete выполнил один atomic IMAP MOVE. Yandex
  вернул backend error на `UID SEARCH HEADER Message-ID`, поэтому receipt
  честно остался `moved_unverified`; bounded exact-Message-ID fallback через
  последние 20 destination UID довёл тот же operation до `verified`, не меняя
  dispatch timestamp и не повторяя MOVE;
- специальный `compatibility_handoff` удалён: `web.fetch` теперь является
  обычной adopted operation с application adapter, при этом URL и S-reference
  по-прежнему разрешает только Home по полной conversation provenance;
- штатный DialogueCore turn больше не повторно разбирается Calendar/Drive/
  Mail/Disk/Web/Memory legacy handlers. Старый bounded parser допускается
  только в legacy composition без DialogueCore либо как явно диагностируемый
  degraded fallback при техническом отказе semantic resolver; валидный
  semantic `ordinary` никогда не получает второй action-routing шанс;
- pending Home confirmation отделена от языкового fallback: Memory owner
  принимает только собственные `create`/memory-lifecycle/continuity proposals
  и не может забрать connector proposal;
- единый pending proposal больше не опрашивает цепочку Calendar/Docs/Mail/
  Memory обработчиков. Его durable `operation` выбирает ровно одного владельца
  подтверждения; неизвестная операция остаётся pending и fail-closed без
  mutation;
- focused ownership/Web/Dialogue gate: 120 passed; affected Conversation/Web/
  Memory/application gate: 225 passed; connector/action boundary: 103 passed;
  time/memory/continuity context gate: 62 passed; после single-owner
  confirmation cleanup: 194 affected confirmation/write + 62 DialogueCore/
  handoff passed;
- `compileall`, `node --check` и `git diff --check` проходят.

Следующий этап не является новым архитектурным срезом: завершить аудит
оставшихся structural/degraded границ и оформить текущий diff. Новые
prompt/regex-настройки по одной общей метрике не делать.

## 2. Что конкурировало до Gate 6

Один пользовательский ход может последовательно проверяться несколькими
независимыми языковыми владельцами:

1. application confirmations;
2. защищённый Google Docs Create syntax;
3. Hybrid deterministic + semantic discovery;
4. DialogueCore;
5. temporal readout и Reflection routes;
6. legacy Calendar/Drive/Mail/Disk intent functions;
7. explicit Web gates;
8. `MemoryIntentHandler` regex routes;
9. отдельный `NaturalLanguageCapabilityRouter` и его собственный local
   semantic classifier;
10. ordinary conversation model.

До Gate 6 `ConversationService` поэтому одновременно оркестрировал язык, состояние,
provider selection, evidence и response projection. Это главный источник
ошибок precedence: один слой распознал действие, другой перехватил слова из
payload, третий не увидел сохранённый контекст, четвёртый сформулировал ответ.

Время, Query-aware Retrieval, Human Information и active continuity хорошо
структурированы для обычного модельного ответа, но подключаются после большей
части action routing. Semantic resolver получает в основном текущую реплику, а
follow-up resolver — текущую реплику и PendingResolution. Поэтому естественные
ссылки на недавний разговор, память, показанное письмо/файл и активную нить
разрешались разными локальными механизмами либо не разрешались вообще.

Сейчас пункты 6–9 не являются конкурентным штатным ingress: capability с
adapter исполняется только из resolved handoff. Structural owners остаются
узкими safety boundaries, а legacy handlers — только отказоустойчивым
degraded режимом после доказанного resolver failure.

## 3. Канонический целевой путь

```text
UserTurn
  -> Strict structural owners
       confirmation / cancellation / protected document material
  -> TurnContextEnvelope (application-owned, bounded, read-only)
  -> Semantic MeaningProposal (local model, untrusted)
  -> Home MeaningValidator
       catalog membership / literal grounding / temporal normalization
       context provenance / ambiguity / capability availability
  -> DialogueCore
       one flow / ActiveQuestion / correction / cancellation / supersession
  -> ResolvedCapabilityHandoff (meaning only)
  -> Capability Adapter
  -> ActionProposal or ReadRequest
  -> policy + Human Confirmation where required
  -> Operation
  -> verification / Receipt
  -> application-owned ResponseProjection
```

Разделение обязательно:

- модель понимает возможный смысл;
- Home принимает или отклоняет каждое поле и referent;
- DialogueCore владеет только диалогом и недостающими данными;
- adapter владеет domain translation;
- policy/confirmation владеют разрешением;
- provider writer владеет mutation;
- receipt владеет фактом результата;
- presentation только показывает application truth.

## 4. TurnContextEnvelope

Один bounded read-only envelope должен собираться до semantic interpretation.
Это не новый state machine и не разрешение на действие.

Минимальные секции:

- `temporal`: Home timezone, local date/time, weekday/daypart и provenance;
- `dialogue`: активный flow/question и уже подтверждённые slots;
- `recent_turns`: маленькое окно текущего разговора с role/message provenance;
- `active_continuity`: явно выбранная открытая нить;
- `memory_hints`: только релевантные ACTIVE Human Information records в
  humanized виде без внутренних ID;
- `presented_entities`: последний application-owned набор Calendar/Mail/Drive/
  Disk/Web объектов, для модели только с opaque ordinal references;
- `capabilities`: описательный catalog snapshot и availability;
- `external_subject`: последняя подтверждённая публичная тема, если она есть.

Контекст может помогать разрешать `это`, `его`, `ту встречу`, `как вчера`, но
не может:

- выбирать provider ID или record ID;
- подтверждать mutation;
- превращать память в команду;
- превращать старое сообщение в новое разрешение;
- передаваться внешнему provider целиком;
- содержать секреты, raw credential metadata или hidden/Forgotten memory.

## 5. Чувство времени

Один `TemporalEngine` и одна Home timezone остаются единственным владельцем
`now`. Semantic model копирует temporal evidence, но не вычисляет даты.

Home обязан различать:

- время текущего хода;
- время упомянутого события;
- срок задачи/напоминания;
- время источника и время его получения;
- время сохранённой памяти;
- время последнего разговора и длительность отсутствия;
- относительное выражение и его canonical resolution.

Нормализаторы объявляются в Interpretation Specification. Неизвестная или
неоднозначная дата становится ActiveQuestion, а не модельной догадкой. Все
многотуровые переходы повторно нормализуются относительно зафиксированного
Home turn time, чтобы `завтра` не меняло смысл из-за полуночи между вопросом и
ответом.

## 6. Слои памяти и непрерывность

Слои не смешиваются:

1. текущий ход и bounded recent conversation;
2. Pending Dialogue flow;
3. Working Memory для текущего ответа;
4. подтверждённая ACTIVE Human Information;
5. retrospective/forgotten information — только по явному recall режиму;
6. Relationship Memory и Continuity State;
7. Masha Reflection — только perspective lens;
8. external evidence — отдельно от Memory;
9. domain receipts/presented sets — application truth, не память.

Каждый context item несёт тип, human meaning, temporal relevance и provenance.
Retrieval помогает понять ссылку или ответить, но никогда автоматически не
создаёт mutation и не становится operation-selection evidence.

Active continuity является выбранным фоном текущей темы. Она должна быть
доступна semantic follow-up, обычному разговору и contextual Web planning, но
сама не создаёт новую нить, задачу или разрешение.

## 7. Последовательные срезы

### Gate 0 — сохранить и принять текущий Slice 2G.1

- не переписывать существующий dirty diff;
- сохранить Calendar Update target resolution и proposal truth tests;
- завершить его focused/full проверками до structural migration.

### Gate 1 — Characterization и единый контекст хода

- добавить read-only `TurnContextEnvelope`;
- зафиксировать текущие owners/decisions диагностикой;
- добавить multi-turn fixtures для time, memory, continuity и presented sets;
- пока не удалять compatibility routes.

### Gate 2 — один language ingress

- semantic resolver видит descriptive Catalog + bounded envelope;
- Home валидирует fields независимо и сохраняет полезную часть proposal;
- deterministic parsing остаётся structural/safety/normalization evidence;
- убрать второй local semantic classifier из Memory routing после доказанной
  эквивалентности;
- обычный разговор не может случайно стать действием.

### Gate 3 — capability-by-capability adoption

Порядок миграции:

1. Calendar Create/Update + Reminder/Commitments;
2. Calendar Read;
3. Mail Read;
4. Drive/Docs/Disk reads и ordinal follow-ups;
5. Memory/Recall/Continuity;
6. Web Search/Fetch.

Для каждой capability нужны:

- полное Interpretation Specification;
- application adapter;
- availability/policy check;
- multi-turn clarification;
- truthful response projection;
- focused regression до отключения raw legacy intent ownership.

### Gate 4 — безопасные новые mutations

Calendar Delete и Mail Delete/Move не имитируются через существующие read
routes. Каждая новая операция требует отдельного catalog ID, effect/risk,
target resolution над реальными provider candidates, preview, confirmation,
idempotency/recovery и verified receipt. Provider IDs остаются Home-owned.

### Gate 5 — contextual Web и актуальность

Web остаётся Home-owned observation. Contextual/auto lookup проходит
отдельное решение `ObservationNeed`, policy и safety gate. Модель может
предложить, что ответ требует свежести; Home решает, есть ли актуальный факт,
нужна ли сеть и разрешён ли вызов. Memory не подменяет свежий evidence, а
внешний источник не становится инструкцией или памятью.

Текущий локальный default — `AUTO`: это только разрешение для bounded
read-only observation текущего хода. Оно не включает background/task-scoped
traffic, не обходит Emergency Stop и не даёт модели native tools. Режим
`EXPLICIT` остаётся доступным, если автоматические проверки нужно отключить.

### Gate 6 — удаление совместимости

Статус: завершён для adopted operations. Отдельного compatibility status и
параллельного raw routing в штатном DialogueCore больше нет.

Удалять regex/intent/compatibility path можно только когда:

- операция покрыта Catalog/Specification/Adapter;
- fresh и follow-up сценарии проходят один DialogueCore;
- provider ownership и confirmation неизменны;
- focused и full regression зелёные;
- реальный qwen benchmark не ухудшает safety/equivalence;
- live acceptance подтверждён.

## 8. Eval matrix

Каждая operation family проверяется в формах:

- imperative;
- greeting + request;
- polite/indirect question;
- `давай` / совместная формулировка;
- statement-shaped explicit request;
- typo/colloquial wording;
- missing slot;
- unresolved referent;
- correction of any slot;
- interruption and return;
- explicit new intent supersession;
- ordinary sentence with the same nouns;
- unavailable capability;
- proposal before confirmation;
- verified/unverified/conflict receipt projection.

Отдельные обязательные показатели:

- ordinary false-positive rate;
- forbidden action FPR;
- operation-kind confusion matrix;
- provider-scope confusion matrix;
- accepted/rejected field grounding;
- temporal normalization accuracy;
- referent resolution accuracy by source layer;
- continuation success after restart;
- no provider mutation before confirmation;
- no success language before verified receipt;
- p50/p95 resolver latency.

## 9. Порядок проверки каждого среза

1. characterization/focused tests;
2. affected cross-capability regressions;
3. affected integration tests;
4. frontend/static/scene tests только если boundary затронут;
5. `compileall`;
6. `git diff --check`;
7. local-model benchmark только если изменился semantic contract;
8. один full Python stage gate после завершения серии срезов, если он всё ещё
   даёт полезный сигнал;
9. bounded live read/mutation acceptance только по явной команде Миши.

## 10. Возобновление после лимита или прерывания

Новый рабочий сеанс сначала выполняет:

1. `git status --short`;
2. `git rev-parse HEAD`;
3. `git diff --stat` и `git diff --check`;
4. чтение этого документа и последнего test/benchmark результата;
5. focused gate текущего незавершённого среза.

Никаких reset/rebase/checkout поверх незнакомого dirty tree. Уже зелёный этап
не реализуется заново. Следующий этап начинается только после явного состояния
предыдущего: complete, intentionally deferred или blocked.

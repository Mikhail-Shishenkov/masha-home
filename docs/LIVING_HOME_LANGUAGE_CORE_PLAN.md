# Masha Home — Living Language Core Plan

Статус: Gate 1–6 реализованы в незакоммиченном tree; остались ручной live
acceptance и оформление изменений.

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

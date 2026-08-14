# Masha Home — Project Canon

Статус: текущий архитектурный канон и roadmap  
Дата фиксации: 2026-08-14  
Источник: `Роадмап Маши.docx`

## 1. Что такое Masha Home

Masha Home — персональная local-first система для одного пользователя и
устойчивый цифровой компаньон по имени Маша.

Цель проекта — не создать очередной чат над LLM, а построить постоянное
цифровое пространство, в котором Маша:

- сохраняет идентичность при смене модели;
- помнит значимые факты, решения, события и общую историю;
- понимает время и обязательства;
- умеет сама замечать потенциально важную информацию;
- вспоминает нужный прошлый контекст в подходящий момент;
- помогает с делами;
- постепенно получает доступ к внешней информации и инструментам;
- способна проявлять ограниченную инициативу;
- выполняет действия только в пределах явно определённых разрешений.

LLM является заменяемым когнитивным движком, а не владельцем личности, памяти
или полномочий Маши.

## 2. Непереговорные архитектурные принципы

### Identity принадлежит приложению

`Masha != LLM`.

Identity Kernel, persona manifest, визуальный канон и утверждённые постоянные
свойства существуют независимо от Qwen или будущей модели. Смена модели не
должна означать смену личности.

### Application владеет действиями

LLM может понять намерение, предложить, сформулировать и рассуждать. Она не
может самостоятельно писать в SQLite, забывать память, закрывать дело,
отправлять сообщение, выдавать себе permission или утверждать, что действие
выполнено.

Мутации принадлежат application/domain layer.

### Human Confirmation остаётся границей безопасности

Чувствительные и изменяющие состояние действия проходят путь:

```text
intent -> reference resolution -> real entity -> proposal -> human confirmation -> mutation -> receipt/audit
```

### Local-first

Базовые функции должны сохраняться без интернета: разговор, Identity, память,
история, дела, время и локальная модель. Личная память не передаётся удалённому
провайдеру автоматически.

### История важнее бесследной перезаписи

Предпочтительные механизмы: supersession, status transition, archive/history,
restore и audit. Hard Delete — отдельная будущая privacy-операция.

## 3. Человеческая модель Дома

Внутри система может иметь десятки типов. Снаружи Миша должен мыслить максимум
четырьмя пространствами:

- **Разговор** — главное пространство взаимодействия с Машей.
- **Дела** — то, что требует действия. По умолчанию здесь живут только open,
  upcoming и overdue.
- **Наша история** — значимое прошлое и продолжение общего контекста: моменты,
  память и темы, к которым хотели вернуться.
- **Уголок** — как устроена и что умеет Маша: как она думает, что умеет, что ей
  можно.

Emergency Stop существует отдельно как safety control.

Не должно быть постоянных верхнеуровневых разделов `Memory Candidates`, `Facts`,
`ContinuityState`, `Agent Receipts`, `Permissions Dashboard` или `Archive`.

## 4. Внутренняя информационная модель

Backend сохраняет богатые типы:

- `Fact` — относительно устойчивое знание.
- `Decision` — осознанно принятое решение.
- `Commitment` — дело или обязательство.
- `Episode` — значимое событие или исторический контекст.
- `RelationshipMemory` — наш общий подтверждённый момент.
- `Continuity` — редкая закладка: к этому стоит вернуться позже. Нить не
  является делом.
- `MashaReflection` — субъективная мысль Маши, отдельная от факта о Мише.
- `MemoryCandidate` — предложение что-то сохранить. Candidate не является
  Memory.

Pending-кандидаты не участвуют в `MemoryRetriever`; только подтверждение
создаёт реальную запись.

## 5. Главная модель памяти

Нужны три разных понятия:

```text
Storage -> Recall -> Working Context
```

`Storage` — всё, что действительно хранит Дом и что со временем может стать
большим.

`Recall` — механизм, который решает, что из прошлого полезно вспомнить именно
сейчас.

`Working Context` — маленький пакет информации, реально передаваемый модели на
конкретный ход.

Memory не равна Context. Этот принцип сохраняется и после появления более
мощного компьютера.

## 6. Lifecycle информации

Внешне используются три человеческих состояния:

- **ACTIVE** — актуально сейчас: active Fact, active Decision, open Commitment,
  open Continuity, current RelationshipMemory.
- **ARCHIVED / PAST** — существовало, но больше не является текущим: completed
  Commitment, resolved Continuity, superseded Decision, superseded Fact,
  cancelled Commitment. Это прошлый опыт, не мусор.
- **FORGOTTEN** — Миша явно попросил Машу перестать использовать информацию.
  Забытое нельзя использовать, пока Миша явно не попросит посмотреть забытое.

`ARCHIVED != FORGOTTEN`. Архивное можно вспомнить ретроспективно. Забытое
можно восстановить только через отдельное подтверждаемое действие.

Обычный `forget` меняет visibility на hidden и не меняет доменный статус.
Hard Delete остаётся будущей необратимой privacy-операцией.

## 7. Recall

Recall существует в трёх режимах:

- **CURRENT** — обычный разговор, видит только ACTIVE.
- **RETROSPECTIVE** — вопросы про прошлое; видит ACTIVE + ARCHIVED, но не
  FORGOTTEN.
- **FORGOTTEN_REVIEW** — только явный просмотр забытого.

Модель может отвечать разговорно из Identity/history, но application не должна
инжектить ложный или нерелевантный сохранённый контекст.

## 8. Как Recall выглядит в разговоре

Model-facing context не должен содержать `record_id`, `confidence`, retrieval
score, SQLite, `relationship_memory`, `continuity_state` и другие технические
детали.

Маша может сказать «помню», когда это помогает человеку, но не обязана
раскрывать механизм Recall. Прошлый контекст должен улучшать ответ, а не
засорять разговор служебными сведениями.

## 9. Retrieval

Текущий Query-aware Retrieval сохраняется:

- фильтрация по реальному статусу;
- lexical relevance;
- threshold;
- no fill-to-limit;
- bounded Working Memory;
- без LLM-вызова для базового поиска.

Рабочий контракт остаётся примерно: 6 records, 3600 chars total, 2000 chars per
record. Recall является надстройкой, которая определяет, какой слой прошлого
вообще разрешено искать.

## 10. Human Search

Поиск должен быть один, но результат понятен человеку. Backend может вернуть
разные доменные сущности, а UI показывает человеческие виды:

- Память;
- История;
- Дело;
- Открытая тема.

Минимальные scopes: всё, история, дела. Time filters поддерживаются backend:
сегодня, 7 дней, 30 дней, период. Календарь в UI добавляется только после
реального опыта использования.

## 11. Время

Один `TemporalEngine` является источником временной истины.

Production Home timezone задаётся application-owned конфигурацией с default
`Europe/Saratov` и fallback `UTC+04:00`, а не старым `Europe/Moscow`.

Время используется для текущей даты, daypart, relative dates, commitments,
reminders, proactive и будущего поиска. LLM не угадывает время.

## 12. Conversation History и Long-term Memory

Conversation transcript сохраняется отдельно. Сейчас это JSON
`ConversationStore`, который загружается целиком и атомарно переписывается при
добавлении сообщений. Это приемлемо на текущем этапе, но является будущим
техническим долгом.

Сообщение в transcript не становится долговременной памятью автоматически.
Structured Recall не равен raw transcript search.

## 13. Passive Memory

v0.3 вводит первую осторожную способность Маши заметить потенциально важную
информацию:

```text
ordinary conversation -> deterministic eligibility -> MemoryCandidate -> user review -> confirmed memory
```

Не каждая реплика становится кандидатом. Чувствительные данные исключаются.
Pending имеет TTL. Нет автоматического подтверждения и второго Qwen-вызова на
каждый turn.

## 14. Human Reference Resolution

Приложение должно понимать человеческие ссылки на реальные application-owned
объекты:

- «удали третью»;
- «убери вторую строку»;
- «забудь её»;
- «эту про модель».

Правило:

```text
human phrase -> reference -> entity -> allowed action -> proposal -> confirmation
```

Ordinal truth может устанавливать только `APPLICATION`-generated list.
Qwen-generated список не создаёт reference truth.

## 15. Proactivity

Хорошая проактивность строится не вокруг `event -> say something`, а вокруг
цепочки:

```text
event/goal -> Recall -> current context -> previous experience/preferences -> should Masha intervene? -> what is useful? -> permission/policy -> action/message
```

Память может информировать действие. Память никогда не авторизует действие.

## 16. Tools и агенты

В проекте уже есть ранний фундамент: Skill Registry, Permission policy,
Emergency Stop, bounded Agent Loop, Project Observer и receipts.

При появлении настоящего Tool Gateway нельзя создавать параллельную
архитектуру. Будущий поток:

```text
Goal -> Recall -> Plan -> Application tool catalog -> Permission -> Tool execution -> Receipt
```

LLM не получает произвольный shell или network.

## 17. Presentation / Presence

Presence является полноценным доменом продукта, а не косметикой.

Главный Home: пространство -> Маша -> контекстная поверхность. Не
`background + dashboard`.

Постоянная навигация: Дела, Наша история, Уголок, Stop. Conversation остаётся
центральным пространством.

Работа, Рядом, Мысли, confirmation, memory candidate review и agent progress —
временные contextual surfaces, а не новые комнаты.

## 18. Текущее техническое состояние

К checkpoint v0.3.1 Slice A реализованы:

- Identity Kernel;
- SQLite Memory v0.4;
- audit/provenance;
- local Ollama model profiles;
- Conversation Engine;
- Query-aware Retrieval;
- Working Memory;
- explicit memory lifecycle;
- Commitments;
- Temporal Grounding;
- reminders/proactive runtime;
- Continuity;
- Masha Reflections / Honest Help;
- skills/permissions/limited agent foundation;
- Emergency Stop;
- Qt/QWebEngine Home;
- typed `MashaApplication`;
- Passive Memory;
- Human Reference Resolution;
- Human Information Model, restore и Recall foundation.

Production composition использует SQLite `masha.sqlite3`, Identity Kernel,
`MemoryRetriever`, `TemporalEngine`, local Ollama provider и
`PassiveMemoryService`.

## 19. Известный технический долг

Не blockers текущего этапа, но отслеживаются:

- Human Home UX для памяти/поиска ещё не завершён;
- `MemoryIntentHandler` уже слишком велик и не должен принимать новые доменные
  обязанности;
- `ConversationStore` JSON не рассчитан на годы transcript history;
- raw conversation search отсутствует;
- backup покрывает прежде всего memory DB, а не весь Дом;
- frontend `app.js` и Qt bridge нуждаются в ограниченном структурном разделении
  перед дальнейшим ростом;
- документация исторически расходилась с production, поэтому старые документы
  помечаются как historical records.

## 20. Roadmap

### v0.3 — Masha learns what may be worth remembering

Статус: завершённый checkpoint.

Реализованы Passive Memory, provenance, pending isolation, approve/reject/expire,
Human Reference Resolution и application-owned ordinal context.

### v0.3.1 — Human Information & Recall

Два slice, один release.

Slice A — Foundation: HumanEntity model, ACTIVE / ARCHIVED / FORGOTTEN,
Restore, unified Human Search contract, CURRENT / RETROSPECTIVE /
FORGOTTEN Recall, active-only tasks, historical retrieval for resolved,
completed and superseded records, model context without internal IDs,
current state over stale application readout, canonical Human Information spec.

Slice B — Human Home UX: passive memory review, possible-update review, unified
search, human result kinds, completed tasks hidden from normal Home, `Наша
история` as a human aggregation, typed UI actions, limited frontend/bridge
structural split, no dashboard.

After Slice A + Slice B: tag `v0.3.1`.

### v0.3.2 — Presence & Home UX Foundation

Place × state scene matrix, about 10-14 canonical scenes, deterministic
presence state, time-of-day ambience, subtle room motion, contextual surfaces
integrated into room, responsive Home, no LLM mood inference.

### v0.4 — Tool Gateway + Web Read-only

Application-owned fixed tool catalog, `web.search`, `web.read/fetch`,
timeouts/budgets, privacy classification, permission checks, receipts, no
arbitrary URLs or commands controlled directly by LLM. Recall is used when
forming tool intent.

### v0.5 — Read-only Connectors

Likely order: Telegram, Calendar, Mail, Files/Drive. Read-only first. Before
expanding the external perimeter, verify Home-wide backup/recovery, not only
memory backup.

### v0.5.1 — Confirmed External Actions

Sending messages, creating or changing calendar events, external writes, Human
Confirmation, receipt and permission boundary.

### v0.6 — Proactive UX + Ambient State

Separate reminder/check-in policies, richer but bounded initiative, quiet mode,
ambient lamps/light for runtime, pending attention, quiet, thinking and
proactive events. These are application events, not model-inferred emotions.

### v0.7 — Bounded Useful Agents

Goals, plans, budgets, tool scopes, Stop, audit, resumability rules, current
permissions and Recall before planning/actions.

### v0.8 — Semantic Knowledge / RAG if justified

Only if lexical retrieval becomes insufficient. Personal memory, document
knowledge and raw conversation archive must remain distinct instead of being
merged into one vector store.

### v0.9 — Rich Home Expansion

Vision, attachments, voice, richer activities, scene expansion and richer
spatial interaction. The visual foundation should already exist from v0.3.2.

### v1.0 — Local Personal System

Target set: persistent cross-chat memory, passive memory, Recall, time, tasks,
web, connectors, controlled tools, bounded agents, proactive behaviour,
interchangeable models, permissions/audit, external entry points,
backup/recovery and stable Home.

## 21. Четыре эпохи проекта

```text
I.   REMEMBERS
     v0.1 -> v0.2.x

II.  LEARNS WHAT TO REMEMBER AND HOW TO RECALL
     v0.3 -> v0.3.x

III. SEES AND ACTS OUTSIDE HOME
     v0.4 -> v0.6

IV.  PERFORMS BOUNDED LONGER WORK
     v0.7 -> v1.0
```

Текущий проект находится в эпохе II: Human Information foundation уже
реализован, следующий практический шаг — Human Home UX для памяти и поиска.

## Исторические документы

Старые документы не удаляются. Они остаются журналом решений и этапов, но не
заменяют этот канон:

- `docs/IMPLEMENTATION_PLAN.md` — historical implementation record.
- `docs/ARCHITECTURE_SNAPSHOT.md` — historical architecture snapshot.
- `docs/PROJECT_CONTEXT.md` — historical project inception context.
- `docs/DECISIONS.md` — живой журнал решений; старые решения заменяются новыми
  явно, а не редактируются задним числом.
- `docs/MEMORY_SPEC.md` — нормативная спецификация Memory v0.4, не roadmap.

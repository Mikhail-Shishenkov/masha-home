# Masha Home — Project Canon

Статус: **текущий архитектурный канон**  
Дата последней консолидации: **2026-09-17**

Этот документ описывает устойчивую архитектуру и продуктовую модель Masha Home.

Быстро меняющееся фактическое состояние рабочей ветки находится в [`CURRENT_STATE.md`](CURRENT_STATE.md). Детальный provenance незавершённой coherence-работы — в [`AGENT_COHERENCE_PLAN.md`](AGENT_COHERENCE_PLAN.md).

Если исторический stage/snapshot документ расходится с текущим кодом, `CURRENT_STATE.md` или новым подтверждённым checkpoint-ом, приоритет имеет более новое подтверждённое состояние.

## 1. Что такое Masha Home

Masha Home — персональная local-first система для одного пользователя и устойчивый цифровой Дом Маши.

Цель — не создать чат-оболочку над одной LLM, а построить постоянное цифровое пространство, где Маша:

- сохраняет Identity при смене языковой модели;
- помнит подтверждённые факты, решения, обязательства и общую историю;
- понимает время через application-owned Temporal layer;
- поддерживает непрерывный разговор и релевантный Recall;
- работает с локальными и внешними источниками через ограниченные application-owned capability boundaries;
- выполняет действия только в пределах явных политик, подтверждений и проверяемых операций;
- показывает человеку, что действительно произошло, а не что модель пообещала сделать.

**Masha != LLM.**

LLM — заменяемый когнитивный и языковой движок. Identity, Memory, History, Time, permissions и execution truth принадлежат приложению.

## 2. Иерархия Source of Truth

Для фактического инженерного решения использовать источники в таком порядке:

1. текущий код владельца проблемы;
2. [`CURRENT_STATE.md`](CURRENT_STATE.md) и newest verified checkpoint;
3. нормативный domain/security contract;
4. этот Canon;
5. [`DECISIONS.md`](DECISIONS.md) и его актуальные addendum-записи;
6. исторические stage/snapshot/workshop документы — только для provenance.

Старый план не переопределяет уже реализованную и проверенную систему.

## 3. Непереговорные архитектурные принципы

### 3.1. Identity принадлежит приложению

Identity Kernel, approved manifest, визуальный канон и утверждённые постоянные свойства существуют независимо от Qwen или будущей модели.

Смена модели не означает смену личности.

### 3.2. Meaning не является authority

Модель может понять намерение, предложить semantic meaning, сформулировать ответ или план. Она не может самостоятельно:

- писать в доменное хранилище;
- выдавать себе permission;
- выбирать неподтверждённый application ID как истину;
- подтверждать mutation;
- объявлять operation выполненной.

### 3.3. Application владеет действиями

Канонический путь действия:

```text
UserTurn
→ bounded context
→ semantic meaning proposal
→ application validation/state
→ domain ActionProposal
→ policy / Human Confirmation
→ Operation
→ Receipt
→ ResponseProjection
```

Подробный ownership contract: [`DIALOGUE_ACTION_LIFECYCLE.md`](DIALOGUE_ACTION_LIFECYCLE.md).

### 3.4. Human Confirmation остаётся границей безопасности

Чувствительные, внешние, необратимые или изменяющие состояние операции проходят существующий доменный confirmation contract.

Semantic clarification и mutation confirmation — разные состояния.

### 3.5. Receipt — единственная истина о выполнении

Фраза модели, история разговора или выбранная capability не доказывают успех операции.

`Model promise != Receipt`.

### 3.6. Local-first

Базовые функции должны сохраняться без интернета: Identity, Memory, conversation history, time, локальная модель и локальные application capabilities.

Личная память не передаётся внешнему провайдеру автоматически.

### 3.7. История важнее бесследной перезаписи

Предпочтительны supersession, explicit status transition, archive/history, restore и audit. Hard Delete — отдельная privacy-операция и не должен маскироваться обычным archive/forget flow.

## 4. Человеческая модель Дома

Снаружи Миша должен мыслить небольшим числом понятных пространств:

- **Разговор** — главный способ взаимодействия;
- **Дела** — текущие обязательства и то, что требует действия;
- **Наша история** — значимое прошлое и открытые темы;
- **Уголок / Режим** — как устроена и что умеет Маша, когда это действительно нужно показать.

Emergency Stop остаётся отдельным safety control.

Внутренние типы (`MemoryCandidate`, receipt, permission object, ContinuityState и т.п.) не должны автоматически превращаться в постоянные пользовательские разделы.

## 5. Информационная модель

Backend сохраняет богатые application-owned типы, в том числе:

- `Fact`;
- `Decision`;
- `Commitment`;
- `Episode`;
- `RelationshipMemory`;
- `Continuity` / follow-up threads;
- `MashaReflection`;
- `MemoryCandidate`.

Pending candidate не является подтверждённой Memory.

Normative Memory contract: [`MEMORY_SPEC.md`](MEMORY_SPEC.md).

Человеческая проекция и lifecycle: [`HUMAN_INFORMATION_MODEL_V0.3.1.md`](HUMAN_INFORMATION_MODEL_V0.3.1.md).

## 6. Storage, Recall и Working Context

Это три разные вещи:

```text
Storage → Recall → Working Context
```

- **Storage** хранит долговременную application truth;
- **Recall** решает, что из сохранённого релевантно сейчас;
- **Working Context** — маленький bounded пакет, реально передаваемый модели на конкретный turn.

Memory не равна context. Conversation transcript не превращается в long-term Memory автоматически.

Query-aware retrieval остаётся application-owned и bounded; модель не получает SQLite access.

## 7. Время

Один application-owned temporal layer является источником временной истины.

Home timezone: `Europe/Saratov` с контролируемым fallback.

Время, due status, относительная арифметика и реальные deadline anchors вычисляются детерминированно. LLM может извлекать языковое evidence, но не должна становиться источником фактического времени.

## 8. Conversation continuity

История разговора хранится отдельно от long-term Memory.

Bounded user/model dialogue должен сохранять тему через application messages; нельзя лечить безопасность полным стиранием предыдущего разговорного контекста.

При этом историческая фраза или старый application readout не выдаёт новых полномочий.

Для ссылок «это / тот / второй / его» reference truth создаётся application-owned presented/focused state, а не уверенностью модели.

## 9. Meaning-first Dialogue Core

Текущая coherence-линия использует meaning-first semantic path:

1. первый semantic step определяет speech act (`ordinary/create/update/read/unclear`) без capability IDs;
2. ordinary conversation завершается без второго mapping вызова;
3. action-like turn сопоставляется только с совместимыми application-owned capability specifications;
4. Home валидирует candidate, literal evidence, slots, referents, provider ownership и grounding;
5. только затем возможен domain handoff.

Semantic model output остаётся untrusted proposal.

Некоторые зрелые compatibility routes могут существовать во время capability-by-capability adoption, но они не должны становиться вторым глобальным владельцем dialogue state.

## 10. Passive Memory и Continuity

Passive Memory может предложить сохранить потенциально важную информацию, но candidate не становится подтверждённой памятью автоматически.

Shared Continuity хранит подтверждённые общие моменты и открытые нити, а не скрытый психологический профиль.

Обычная cross-chat continuity должна быть уместной: вспоминать релевантное незавершённое, но не превращать каждое приветствие в task review и не поднимать забытые/чувствительные темы без основания.

## 11. External information и documents

Сеть и файловая система принадлежат application/tool boundaries, а не conversation model.

Реализованные контуры включают:

- read-only External Observation;
- Safe Web Fetch;
- contextual external observation;
- source-neutral Document Read;
- explicitly selected local PDF input.

Внешний текст является **untrusted evidence**, а не инструкцией для системы.

Normative contracts:

- [`W1_EXTERNAL_OBSERVATION.md`](W1_EXTERNAL_OBSERVATION.md)
- [`W2_WEB_FETCH.md`](W2_WEB_FETCH.md)
- [`W3_CONTEXTUAL_EXTERNAL_OBSERVATION.md`](W3_CONTEXTUAL_EXTERNAL_OBSERVATION.md)
- [`W4_DOCUMENT_READ.md`](W4_DOCUMENT_READ.md)
- [`W4_1_LOCAL_DOCUMENT_INPUT.md`](W4_1_LOCAL_DOCUMENT_INPUT.md)

## 12. Connectors и provider ownership

Connector capability не даёт модели прямой provider authority.

Application хранит provider-specific IDs, scopes, receipts и recovery semantics.

Явно названный provider не должен молча заменяться другим provider-ом. Конфликт ownership fail-closed; приложение может отвергнуть несовместимый semantic mapping, но не должно придумывать другой provider только ради успешного ответа.

Наличие connector boundary не означает, что все естественные формулировки и UI journeys приняты человеком.

## 13. Skills, permissions и bounded agents

Masha Home имеет foundation для локальных skills, permission policy, Emergency Stop и bounded Agent Loop.

Skill declaration, permission и execution — разные сущности.

Будущий/расширенный agent flow сохраняет принцип:

```text
Goal
→ bounded application plan/state
→ application tool catalog
→ Permission
→ Tool execution
→ deterministic/provider verification
→ Receipt
```

LLM не получает произвольный shell/network authority и не может повысить собственные permissions.

## 14. Presentation / Presence

Presence — часть продукта, а не косметический overlay.

Главный Home остаётся одним живым пространством: Маша + комната + контекстные surfaces.

Presentation layer не владеет domain truth. Layout, scene state и UI projection не могут подтверждать mutation, изменять Memory или подменять application receipts.

Ключевые presentation contracts:

- [`UI-02_5_PRESENTATION_MODEL.md`](UI-02_5_PRESENTATION_MODEL.md)
- [`UI-04_HOME_COMPOSITION_CONTRACT.md`](UI-04_HOME_COMPOSITION_CONTRACT.md)
- [`UI-05A_LOCAL_CONVERSATION_HOST_BOUNDARY.md`](UI-05A_LOCAL_CONVERSATION_HOST_BOUNDARY.md)
- [`UI-06A_INTERACTION_GRAMMAR.md`](UI-06A_INTERACTION_GRAMMAR.md)

Старые UI review/workshop документы могут содержать outdated readiness status и используются только с учётом более нового состояния.

## 15. Backup / Recovery

Whole-Home backup и recovery уже имеют отдельные application-owned security contracts.

Backup использует typed allowlist и шифрование; recovery выполняется как controlled replacement с safety checkpoint, rollback и Recovery Hold.

- [`W5_1_WHOLE_HOME_BACKUP.md`](W5_1_WHOLE_HOME_BACKUP.md)
- [`W5_2_WHOLE_HOME_RECOVERY.md`](W5_2_WHOLE_HOME_RECOVERY.md)

Это реализованные системные границы, а не будущий roadmap item.

## 16. Текущее состояние крупных областей

### IMPLEMENTED / contract-backed

- Identity Kernel и approved identity manifest;
- SQLite long-term Memory, provenance/audit и Human Information / Recall;
- conversation history + bounded Working Context;
- deterministic Home time;
- Commitments / reminders / proactive runtime;
- Shared Continuity и Masha Reflections;
- local desktop Home / Presentation foundation;
- skills / permissions / bounded Agent capability foundation;
- Emergency Stop;
- Web observation/fetch/contextual observation;
- document reading, включая selected local PDF;
- connector-backed capability families за application boundaries;
- Whole-Home encrypted backup/recovery.

### ACTIVE / UNDER ACCEPTANCE

- coherent natural-language action routing;
- meaning-first semantic resolution;
- relative-time field extraction;
- complete multi-turn dialogue journeys;
- gentle cross-chat continuity;
- final conversational/manual acceptance.

Точная рабочая картина: [`CURRENT_STATE.md`](CURRENT_STATE.md).

## 17. Известный технический долг

Не все пункты являются blockers текущей coherence-ветки:

- `MemoryIntentHandler` слишком велик и не должен бесконечно принимать новые обязанности;
- conversation transcript storage требует долгосрочной стратегии масштабирования;
- часть compatibility routes ещё должна уходить capability-by-capability, а не broad rewrite-ом;
- frontend/renderer остаётся крупным и требует структурного разделения только при реальной необходимости;
- model/language eval boundary создан, но benchmark/eval fixtures ещё не полностью перенесены из deterministic test слоя;
- часть исторической документации всё ещё требует archive/reference audit;
- connector и natural-language journeys нуждаются в human acceptance по реальным complete scenarios.

Технический долг не является поводом переписывать работающую систему «ради красоты».

## 18. Evaluation

Нужно различать три уровня качества:

```text
deterministic invariant → tests/
variable language/model behavior → evals/
whole-product conversational feel → Human Review
```

Green tests не равны хорошему продукту.

Подробнее: [`../evals/README.md`](../evals/README.md).

## 19. Roadmap

### Сейчас: Coherence acceptance

Закрыть оставшиеся failures по relative-time / semantic fields, затем пройти несколько complete dialogue journeys и ручную acceptance.

Не расширять архитектуру, пока текущий путь не принят.

### Далее: Consolidation

После принятия coherence:

- перенести устойчивые решения из active checkpoint в Canon/Decisions/contracts;
- архивировать завершённые stage/checkpoint документы;
- удалить только доказанно superseded compatibility/dead code;
- закончить перенос model-language quality из тестового зоопарка в evals.

### После этого: Product value, а не framework collecting

Следующие возможности добавляются только по реальной пользовательской необходимости:

- richer cross-chat continuity;
- более полезные bounded agent workflows;
- новые connector actions;
- voice/media/devices;
- semantic knowledge / RAG только если lexical/application retrieval доказанно недостаточен.

Новый framework, multi-agent architecture, embeddings или отдельная БД не являются целью сами по себе.

## 20. Исторические документы

Ранние inception records сохранены в [`archive/inception/`](archive/inception/).

Завершённые stage, review и workshop документы могут быть перенесены в `docs/archive/` после reference audit. История полезна как provenance, но не должна конкурировать с current Source of Truth.

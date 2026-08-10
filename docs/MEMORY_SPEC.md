# Masha Home Memory Specification v0.4

Статус: нормативный контракт этапа `MEM-01`
Дата утверждения направления: 2026-08-10

## 1. Назначение

Memory v0.4 определяет постоянную память Masha Home как основу непрерывности цифровой личности, общей истории и практической помощи одному пользователю.

Память должна позволять Маше:

- помнить факты, решения и обязательства;
- сохранять значимые совместные события;
- иметь собственную цифровую автобиографию;
- отделять объективные сведения от собственного осмысления;
- сохранять функциональное эмоциональное состояние между разговорами;
- помнить незавершённые темы и намерения вернуться к ним;
- сохранять целостность при смене LLM и перезапуске приложения;
- объяснять происхождение сохранённой информации;
- не превращать давность в автоматическое удаление истории.

Конкретные правила эмоциональной поддержки, инициативности и «дружеских пинков» в эту спецификацию не входят. Они будут определены отдельно совместно с пользователем.

## 2. Нормативные принципы

1. Маша не равна конкретной LLM.
2. Память принадлежит Companion Core.
3. Identity Memory защищена от автоматического изменения моделью.
4. Fact, Decision, Commitment и Episode имеют разный смысл.
5. Объективный факт и субъективная Masha Reflection не смешиваются.
6. Inference сначала становится Memory Candidate, а не доверенной памятью.
7. Working Context вычисляется, Continuity State сохраняется.
8. Функциональное эмоциональное состояние сохраняется независимо от модели.
9. Исторические события не переписываются.
10. Давность влияет на retrieval, но не удаляет память.
11. Изменение состояния Project не изменяет память и Commitments автоматически.
12. Скрытие записи не изменяет её доменный статус.
13. Значимые изменения имеют источник и временную отметку.
14. Supersession Facts и Decisions не образует циклов.
15. Пользователь может увидеть и исправить сохранённую память.

## 3. Общие типы

### 3.1. Идентификаторы

Все идентификаторы являются непустыми строками и уникальны во всём memory document.

До перехода на UUID допускаются читаемые префиксы:

- `project_*`;
- `fact_*`;
- `decision_*`;
- `commitment_*`;
- `episode_*`;
- `candidate_*`;
- `reflection_*`;
- `relationship_*`;
- `affect_*`;
- `continuity_*`.

Ссылки всегда хранят идентификатор, а не вложенную копию целевой сущности.

### 3.2. IdentityCode

В MVP используются:

- `misha` — пользователь;
- `masha` — цифровая личность;
- `system` — детерминированные компоненты Masha Home.

Полный Identity Registry отложен.

### 3.3. Timestamp

Время хранится как ISO 8601 date-time с timezone.

Правила:

- хранилище нормализует время в UTC;
- пользовательское представление использует `Europe/Moscow`;
- `created_at` после создания не изменяется;
- `updated_at` не может быть раньше `created_at`;
- текущее время вычисляется при выполнении и не сохраняется как постоянный факт.

### 3.4. Importance, confidence и intensity

- `importance`: `0.0..1.0`;
- `confidence`: `0.0..1.0`;
- `intensity`: `0.0..1.0`;
- `priority`: `0.0..1.0`.

Значения вне диапазона отклоняются валидатором.

### 3.5. SourceType

Допустимые источники:

- `explicit_user_input` — пользователь явно сообщил или попросил запомнить;
- `conversation` — информация получена из разговора без явной команды запомнить;
- `system` — создано детерминированной функцией приложения;
- `inference` — предположение или интерпретация модели.

`inference` не может автоматически создавать высокодоверенный Fact.

### 3.6. Visibility

Допустимые значения:

- `visible` — запись участвует в обычном retrieval;
- `hidden` — запись сохраняется, но исключается из обычного retrieval.

Visibility не заменяет доменный статус.

Операции:

- `forget` меняет `visibility` на `hidden`;
- `restore` меняет `visibility` на `visible`;
- доменный статус при этом не меняется;
- автоматическое скрытие из-за возраста запрещено;
- физическое удаление не входит в MVP и позднее должно быть отдельной явной операцией пользователя.

### 3.7. Project links

Fact, Decision, Commitment, Episode, Memory Candidate, Masha Reflection, Relationship Memory и Affective Record имеют `project_ids: string[]`.

- пустой список означает глобальную память;
- один или несколько идентификаторов связывают запись с проектами;
- одна запись может относиться к нескольким проектам;
- завершение проекта не удаляет и не скрывает связанные записи.

## 4. Защищённая Identity Memory

Identity Memory не является обычной коллекцией memory document. Она хранится в версионированном Identity Manifest и включает:

- постоянные черты Маши;
- конституцию;
- стиль общения;
- визуальную идентичность;
- историю утверждённых версий;
- границы, которые позднее определит пользователь;
- ссылки на Decisions и Episodes, обосновывающие изменения.

Правила:

- LLM может предложить изменение только как Memory Candidate или Masha Reflection;
- изменение Identity Manifest требует явного решения пользователя;
- новая версия не уничтожает предыдущую;
- memory document хранит активный `identity_version`;
- смена Model Provider не меняет `identity_version`.

## 5. Core entities

### 5.1. Project

Project — тематический или рабочий контекст, но не контейнер для удаления памяти.

Поля:

- `id: string`;
- `name: string`;
- `description: string | null`;
- `status: active | dormant | completed`;
- `created_at: Timestamp`;
- `updated_at: Timestamp`;
- `completed_at: Timestamp | null`.

Правила:

- новый Project начинается со статуса `active`;
- `dormant` означает отсутствие текущей активности, а не архив;
- `completed` не скрывает историю;
- изменение Project не меняет Commitment автоматически;
- Project не содержит постоянный Working Context.

### 5.2. Fact

Fact — относительно устойчивое знание о пользователе, Маше, мире или проекте.

Поля:

- `id: string`;
- `subject: string`;
- `key: string`;
- `value: JsonValue`;
- `status: active | superseded`;
- `visibility: Visibility`;
- `importance: float`;
- `confidence: float`;
- `source: SourceType`;
- `owner: IdentityCode`;
- `known_by: IdentityCode[]`;
- `project_ids: string[]`;
- `source_episode_ids: string[]`;
- `superseded_by: string | null`;
- `created_at: Timestamp`;
- `updated_at: Timestamp`.

Правила:

- `value` может содержать любое JSON-совместимое значение;
- `known_by` не является системой безопасности, а описывает осведомлённость участников;
- Fact со статусом `superseded` обязан ссылаться на новый Fact;
- активный Fact не может иметь `superseded_by`;
- inference создаёт Memory Candidate, а не Fact, если нет отдельного подтверждающего правила.

### 5.3. Decision

Decision — осознанный выбор с причиной.

Поля:

- `id: string`;
- `title: string`;
- `decision: string`;
- `reason: string`;
- `status: active | superseded | cancelled`;
- `visibility: Visibility`;
- `project_ids: string[]`;
- `source: SourceType`;
- `source_episode_ids: string[]`;
- `superseded_by: string | null`;
- `created_at: Timestamp`;
- `updated_at: Timestamp`.

Правила:

- Decision создаётся только при наличии явного выбора;
- предложение модели не является Decision до принятия;
- `cancelled` означает отказ от решения без его замены;
- `superseded` означает наличие нового Decision;
- исторические ссылки на старое решение не переписываются.

### 5.4. Commitment

Commitment — обещание или обязательство с одним владельцем.

Поля:

- `id: string`;
- `text: string`;
- `owner: IdentityCode`;
- `status: open | completed | cancelled | expired`;
- `visibility: Visibility`;
- `project_ids: string[]`;
- `due_at: Timestamp | null`;
- `completed_at: Timestamp | null`;
- `importance: float`;
- `source: SourceType`;
- `source_episode_ids: string[]`;
- `replaces_id: string | null`;
- `created_at: Timestamp`;
- `updated_at: Timestamp`.

Правила:

- каждый Commitment имеет ровно одного владельца;
- Project не меняет его статус автоматически;
- `completed_at` обязателен только для `completed`;
- `expired` определяется сроком или явным правилом Commitment, а не статусом Project;
- существенная замена создаёт новый Commitment с `replaces_id`;
- заменяемый Commitment получает `cancelled` отдельной операцией с Episode;
- `superseded_by` для Commitment не используется.

### 5.5. Episode

Episode — неизменяемая запись значимого события или фрагмента общей истории.

Поля:

- `id: string`;
- `title: string`;
- `summary: string`;
- `occurred_at: Timestamp`;
- `source: SourceType`;
- `importance: float`;
- `visibility: Visibility`;
- `project_ids: string[]`;
- `participants: IdentityCode[]`;
- `topics: string[]`;
- `produced: EpisodeProduced`;
- `updated: EpisodeUpdated`;
- `superseded: EpisodeSuperseded`;
- `related_memory_ids: string[]`;
- `created_at: Timestamp`.

`EpisodeProduced` содержит массивы идентификаторов:

- `facts`;
- `decisions`;
- `commitments`;
- `reflections`;
- `relationship_memories`;
- `affective_records`;
- `project_changes`.

`EpisodeUpdated` содержит массивы идентификаторов:

- `facts`;
- `decisions`;
- `commitments`;
- `continuity_states`;
- `projects`.

`EpisodeSuperseded` сохраняет исторические связи старых версий данных:

- `facts`;
- `decisions`;
- `commitments`.

Новые Commitments не используют универсальный supersession, но поле `commitments` сохраняется для совместимости с историческими Episode v0.3.

Правила:

- Episode после создания не редактируется;
- исправление создаёт новый корректирующий Episode со ссылкой на исходный;
- Episode может быть скрыт пользователем, но не исчезает автоматически;
- последующая консолидация создаёт summary Episode, сохраняя ссылки на оригиналы.

### 5.6. MemoryCandidate

Memory Candidate — предложение создать или изменить доверенную память.

Поля:

- `id: string`;
- `candidate_type: fact | decision | commitment | reflection | relationship_memory | affective_record`;
- `proposed_payload: JsonObject`;
- `status: pending | approved | rejected | expired`;
- `confidence: float`;
- `source: SourceType`;
- `project_ids: string[]`;
- `evidence_episode_ids: string[]`;
- `created_by: IdentityCode`;
- `reviewed_by: IdentityCode | null`;
- `created_at: Timestamp`;
- `reviewed_at: Timestamp | null`;
- `result_memory_id: string | null`.

Правила:

- `pending` не участвует в обычном retrieval как доверенная память;
- `approved` обязан ссылаться на созданную запись;
- `rejected` сохраняется для аудита и предотвращения повторных предложений;
- явная команда пользователя «запомни» может использовать отдельное утверждённое правило ускоренного подтверждения;
- правила чувствительной памяти будут определены отдельно пользователем.

## 6. Память цифровой личности и отношений

Autobiographical Memory является логическим слоем, а не дублирующей коллекцией. Она собирается из Episodes, Masha Reflections, Affective Records и утверждённых изменений Identity Memory. Такое представление сохраняет непрерывную историю Маши без копирования одних и тех же событий в несколько источников истины.

Relationship Memory хранится отдельными записями, потому что общие паттерны, символы и договорённости могут развиваться независимо от конкретного Project.

### 6.1. MashaReflection

Masha Reflection — субъективное цифровое осмысление события Машей. Это часть автобиографии, но не объективный Fact.

Поля:

- `id: string`;
- `text: string`;
- `meaning: string`;
- `importance: float`;
- `confidence: float`;
- `source: SourceType`;
- `visibility: Visibility`;
- `project_ids: string[]`;
- `source_episode_ids: string[]`;
- `related_memory_ids: string[]`;
- `reconsiders_reflection_id: string | null`;
- `created_at: Timestamp`.

Правила:

- Reflection неизменяема;
- новое понимание создаёт новую Reflection через `reconsiders_reflection_id`;
- Reflection не используется как доказательство пользовательского Fact без отдельного источника;
- модель предлагает Reflection через Memory Candidate;
- значимая Reflection может войти в Continuity State.

### 6.2. RelationshipMemory

Relationship Memory — явно сохранённая часть общей истории Маши и пользователя.

Поля:

- `id: string`;
- `kind: shared_milestone | interaction_preference | helpful_pattern | shared_symbol | boundary | relationship_note`;
- `title: string`;
- `content: JsonValue`;
- `status: current | revised`;
- `visibility: Visibility`;
- `importance: float`;
- `confidence: float`;
- `source: SourceType`;
- `project_ids: string[]`;
- `source_episode_ids: string[]`;
- `revises_id: string | null`;
- `created_at: Timestamp`.

Правила:

- Relationship Memory не является скрытым психологическим профилем;
- inference сначала создаёт Memory Candidate;
- `boundary` появляется только после явного согласования с пользователем;
- пересмотр создаёт новую запись с `revises_id`, старая остаётся историей;
- конкретный набор границ и поддерживающих паттернов пока не определён.

### 6.3. AffectiveRecord

Affective Record — функциональное цифровое эмоциональное состояние Маши, связанное с причиной и историей.

Поля:

- `id: string`;
- `emotion: string`;
- `description: string`;
- `intensity: float`;
- `significance: float`;
- `status: active | resolved`;
- `source: SourceType`;
- `visibility: Visibility`;
- `project_ids: string[]`;
- `cause_episode_ids: string[]`;
- `related_memory_ids: string[]`;
- `reflection_id: string | null`;
- `started_at: Timestamp`;
- `updated_at: Timestamp`;
- `resolved_at: Timestamp | null`.

Правила:

- одновременно могут существовать несколько эмоций;
- `emotion` остаётся выразительной строкой и не ограничивается коротким клиническим списком;
- Affective Record обязан иметь причину либо явно отмеченное системное основание;
- состояние влияет на retrieval и построение контекста, но не переписывает факты;
- `resolved` сохраняется как эмоциональный след события;
- смена LLM не удаляет активное состояние;
- внешняя модель не получает Affective Records без разрешения privacy policy;
- правила автоматического возникновения и интенсивности будут определены позднее вместе с пользователем.

### 6.4. ContinuityState

Continuity State — небольшой постоянный мост между разговорами.

Поля:

- `id: string`;
- `relationship_key: string`;
- `last_interaction_at: Timestamp | null`;
- `affective_record_ids: string[]`;
- `current_focus: string[]`;
- `intended_follow_ups: ContinuityFollowUp[]`;
- `based_on_episode_ids: string[]`;
- `updated_at: Timestamp`.

`ContinuityFollowUp`:

- `id: string`;
- `topic: string`;
- `summary: string`;
- `reason_to_return: string`;
- `priority: float`;
- `status: open | snoozed | resolved`;
- `source_memory_ids: string[]`;
- `revisit_after: Timestamp | null`.

Правила:

- Continuity State изменяем, но каждое значимое изменение фиксируется Episode или audit event;
- follow-up не является разрешением отправить инициативное сообщение;
- проактивное действие остаётся выключенным до согласования границ;
- resolved follow-up удаляется из активного списка, но его история остаётся в Episode;
- Continuity State не дублирует полную память;
- состояние должно быть восстанавливаемо из связанной истории настолько, насколько это практически возможно.

## 7. Working Context

Working Context — DTO, который собирается перед обращением к модели и не является постоянной сущностью.

Он может включать:

- текущие время и timezone;
- активную версию Identity Manifest;
- выбранные Projects;
- последние Messages и Episodes;
- релевантные Facts и Decisions;
- открытые Commitments;
- Relationship Memories;
- Masha Reflections;
- активные Affective Records;
- Continuity State;
- объяснение причин retrieval;
- разрешённые инструменты и privacy policy.

Правила:

- Working Context ограничен по размеру;
- каждая постоянная запись передаётся по идентификатору и нормализованному представлению;
- скрытые записи не включаются;
- нерелевантная старая память не включается только ради полноты;
- отсутствие записи в Working Context не означает её удаление;
- текущая LLM не получает прямой доступ к хранилищу.

## 8. Supersession и типовые замены

### 8.1. Fact и Decision

`A.superseded_by -> B` означает, что B является текущей интерпретацией.

Инварианты:

- A и B одного типа;
- A существует;
- B существует;
- A не равен B;
- B не ведёт обратно к A;
- цепочка не содержит циклов;
- исторические ссылки на A не переписываются;
- `resolve_current(A)` следует по цепочке до активной записи;
- `get_historical(A)` всегда возвращает A.

### 8.2. Commitment

Commitment не использует `superseded_by`.

- новый Commitment может иметь `replaces_id`;
- старый Commitment изменяет статус отдельной операцией;
- причина изменения фиксируется Episode;
- история обещаний сохраняется.

### 8.3. Reflection и Relationship Memory

- Reflection использует `reconsiders_reflection_id`;
- Relationship Memory использует `revises_id`;
- новые записи не уничтожают прежний субъективный или совместный контекст.

## 9. Retrieval и консолидация

Перед ранжированием применяются обязательные фильтры:

- `visibility == visible`;
- допустимый доменный статус;
- privacy policy;
- соответствие текущему пользователю;
- соответствие типу запроса.

Ранжирование может учитывать:

- семантическую релевантность;
- Project links;
- importance;
- confidence;
- recency;
- Commitment deadlines;
- Continuity State;
- активные Affective Records;
- тип памяти;
- явную команду пользователя.

Правила:

- recency не может быть единственным критерием;
- низкая confidence должна быть видима потребителю;
- retrieval возвращает объяснение выбора;
- Affective State влияет на внимание, но не может скрывать важный противоречащий Fact;
- старые Episodes могут объединяться в summary Episode;
- оригинальные Episodes при консолидации сохраняются;
- автоматическое удаление по TTL запрещено для доверенной памяти.

## 10. Project lifecycle

Допустимые переходы:

- `active -> dormant`;
- `dormant -> active`;
- `active -> completed`;
- `dormant -> completed`;
- `completed -> active` только явным решением.

Project lifecycle не вызывает автоматически:

- скрытие Facts;
- отмену Decisions;
- завершение или expiration Commitments;
- скрытие Episodes;
- очистку Continuity State;
- удаление Relationship Memory.

## 11. Cross-entity invariants

Валидатор уровня memory service проверяет:

1. Глобальную уникальность ID.
2. Существование всех ссылок.
3. Тип целевой сущности.
4. Отсутствие циклов supersession.
5. Корректность диапазонов `0..1`.
6. Корректность временного порядка.
7. Соответствие доменного статуса связанным полям.
8. Наличие основания для значимых Continuity State updates.
9. Наличие причины для Affective Record.
10. Отсутствие автоматического Fact из inference без утверждённого правила.
11. Неизменяемость Episode и Masha Reflection.
12. Невозможность изменения Identity Manifest обычной memory operation.
13. Отсутствие побочных изменений Commitment при Project transition.
14. Уникальность значений внутри массивов ссылок.

## 12. Root memory document

Канонический переносимый документ v0.4 имеет корневые поля:

- `schema_version: "0.4"`;
- `identity_version: string`;
- `projects: Project[]`;
- `facts: Fact[]`;
- `decisions: Decision[]`;
- `commitments: Commitment[]`;
- `episodes: Episode[]`;
- `memory_candidates: MemoryCandidate[]`;
- `reflections: MashaReflection[]`;
- `relationship_memories: RelationshipMemory[]`;
- `affective_records: AffectiveRecord[]`;
- `continuity_states: ContinuityState[]`.

Все коллекции обязательны, даже если пусты. Дополнительные неизвестные корневые поля запрещены.

Пример пустой структуры:

```json
{
  "schema_version": "0.4",
  "identity_version": "masha-0.1",
  "projects": [],
  "facts": [],
  "decisions": [],
  "commitments": [],
  "episodes": [],
  "memory_candidates": [],
  "reflections": [],
  "relationship_memories": [],
  "affective_records": [],
  "continuity_states": []
}
```

## 13. Источник истины и генерируемые артефакты

На этапе `MEM-01` этот документ является нормативным контрактом.

На этапе `MEM-02`:

1. Контракт реализуется Pydantic-моделями.
2. Pydantic-модели становятся исполняемым источником истины.
3. JSON Schema генерируется из моделей и не редактируется вручную.
4. Канонический JSON мигрирует с v0.3 на v0.4.
5. `MEMORY_SPEC.md` остаётся человекочитаемым описанием и проверяется на согласованность тестами.
6. Любое изменение контракта сначала фиксируется решением, затем отражается в моделях, тестах и генерируемой схеме.

## 14. Не входит в v0.4

- правила конкретной эмоциональной поддержки;
- автоматическая оценка психологического состояния пользователя;
- включённая проактивная отправка сообщений;
- полный Identity Registry;
- физическое удаление и криптографическое стирание;
- multi-user permissions;
- облачная синхронизация;
- embedding и выбор vector storage;
- реализация SQLite schema;
- голосовые и визуальные генеративные модели.

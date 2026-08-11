# Stage 15 — Masha Perspective & Honest Help

Статус: **IMPLEMENTED (15.1, bounded 15.2, 15.3)**

## Зачем

Stage 15 даёт Маше собственную, сохраняемую точку зрения, не превращая вывод
LLM в факт о Мише или новую Identity. Это не фоновый дневник и не скрытый
психологический профиль. Рефлексия возникает только по явному запросу или из
явно сообщённого результата помощи, имеет evidence и confidence, может быть
отклонена или позднее пересмотрена.

Отличительная черта контура: Маша может честно сформулировать своё понимание,
включая несогласие, юмор или органичный мат, но система не разрешает ей
выдумывать диагнозы, выполненные действия и несуществующие возможности.

## Пользовательский flow

```text
Маша, подумай о себе: почему тебе важно спорить честно?
→ одна локальная генерация reflection candidate
→ deterministic validation + deduplication
→ при confidence >= 0.55 собственная рефлексия Маши сохраняется

Маша, подумай о нас: почему мы возвращаемся к этой теме?
→ reflection candidate + preview
→ «прими рефлексию» / «отклони рефлексию»
→ только принятую интерпретацию можно использовать дальше

Маша, пересмотри рефлексию о <тема>: <новый контекст>
→ новая неизменяемая рефлексия
→ reconsiders_reflection_id указывает на прежнюю
→ прежняя запись не переписывается

Маша, это помогло: ...
Маша, это не помогло: ...
→ bounded help-learning reflection с явным outcome
```

Диагностический CLI остаётся человекочитаемым:

```text
reflections list
reflections pending
reflections show <номер>
reflections adopt <номер>
reflections reject <номер>
reflections reconsider <номер> <новый контекст>
help pending
help accept <номер>
help reject <номер>
```

UUID и внутренние payload показываются только с `--raw`.

## Архитектура

```text
explicit reflection intent
  → ReflectionIntentHandler
  → existing IdentityKernel
  → existing MemoryRetriever (bounded evidence)
  → bounded conversation evidence
  → provider-neutral ModelRequest / LOCAL_ONLY / think=false
  → ModelRouter → active local ModelProfile
  → strict JSON parse + deterministic validation + semantic dedup
  → existing MemoryCandidate(type=reflection)
  ├─ self / explicit help outcome + sufficient confidence → MashaReflection
  └─ shared or uncertain → pending → explicit adopt/reject
  → existing MemorySqliteRepository + audit

explicit perspective question
  → existing MemoryRetriever
  → reflection-only bounded context lens
  → ConversationContextCompiler
  → ordinary local conversation response
```

Новая SQLite migration не потребовалась. `MashaReflection`,
`MemoryCandidate`, `reconsiders_reflection_id` и audit уже входят в текущий
Memory v0.4 / repository contract. Provenance текущего разговора, scope,
исходная тема, explicit outcome и optional Help Offer хранятся в валидируемом
candidate payload.

## Дисциплина перспективы

- `MashaReflection` — мнение Маши, а не `Fact`, `Decision`, `Episode`, диагноз
  Миши, действие или часть защищённой Identity.
- Обычный разговор не создаёт рефлексии автоматически.
- Обычный general context не получает рефлексии автоматически. Они передаются
  только при явном вопросе о мнении/пересмотре Маши.
- Shared reflection не становится общей правдой без подтверждения Миши.
- Низкая confidence оставляет self-reflection pending.
- Семантический дубль не создаёт вторую постоянную запись.
- Пересмотр добавляет новую точку зрения и сохраняет прежнюю исторически.
- Диагностические и false-action формулировки отклоняются до persistence.
- Мат не фильтруется сам по себе: допустима живая речь, но не унижение и не
  маскировка недостоверного утверждения.

## Honest Help Bridge

`HelpOffer` не является действием или разрешением на tools. Он содержит только
наблюдение, конкретное разговорное предложение, ожидаемую пользу и причину
своевременности. Предложение становится доступно только у принятой рефлексии.

```text
adopted reflection with HelpOffer
  → human-readable offer
  → explicit «давай, помоги»
  → одна локальная formulation через active ModelProfile
  → conversation-only result
  → accepted/delivered audit state
```

Отклонение подавляет предложение. Повторное принятие уже доставленного offer
идемпотентно и не вызывает LLM снова. Ни принятие, ни доставка не меняют Fact,
Memory, Identity, Commitment, TemporalContext или proactive policy.

## Model boundary

Используется только активный локальный профиль, `ModelRouter`,
`PrivacyScope.LOCAL_ONLY` и `think=false`. Reflection flow требует capability
`structured_output`; текущий `primary` (`qwen3.5:9b`) её имеет. `fast` не
подменяется автоматически: система возвращает контролируемую недоступность.
Провайдер не владеет сохранённой рефлексией и не решает её lifecycle.

## Сознательно не реализовано

- фоновый дневник, sleep-time reflection и периодическая генерация;
- автоматическое извлечение рефлексий из каждого диалога;
- автоматическое определение эмоционального или психологического состояния;
- изменение Identity manifest;
- влияние рефлексий на proactive decisions;
- scheduler, tools, external APIs, model fallback или automatic switching;
- автоматическое выполнение Help Offer;
- embeddings/vector dedup и массовая консолидация старых рефлексий.

## Известные ограничения

- explicit intents пока распознаются небольшим deterministic набором фраз;
- structured JSON всё ещё формулирует локальная модель, поэтому некорректный
  ответ безопасно отклоняется, но автоматически не исправляется retry-циклом;
- deduplication лексическая и намеренно консервативная;
- Help Bridge даёт только результат, возможный внутри разговора;
- отдельный UX/UI для просмотра evidence пока отсутствует, детали доступны в
  local `--raw` diagnostics.

## Проверка реализации

- deterministic Stage 15 regression: `14 passed`;
- полный regression проекта: `183 passed`;
- isolated local Ollama smoke: `qwen3.5:9b`, `think=false`, reflection save,
  restart recovery и perspective reply — успешно;
- production SQLite SHA-256 до и после:
  `55F0C17A3190C97C1FFC60EDF228AEBCE77793E3D08064455F87810181A7548E`.

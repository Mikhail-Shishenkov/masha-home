# Masha Home — Current State

Дата сверки: **2026-09-17**  
Статус: **текущее фактическое состояние рабочей ветки; не release note**

Этот документ отвечает только на вопрос: **«что является текущей инженерной реальностью Masha Home сейчас?»**

Он не заменяет Конституцию, доменные контракты или журнал решений. Для незавершённой coherence-работы подробный trace/provenance остаётся в [`AGENT_COHERENCE_PLAN.md`](AGENT_COHERENCE_PLAN.md).

## 1. Ветка и release status

Активная рабочая линия: `new/agent-coherence-continuation`.

Исходный опубликованный coherence checkpoint: `7d9e10066b5c2f05bd6f34aba73b2a4ff37a6d7a` от 2026-09-16. После него выполняется только документационная консолидация; она не превращает checkpoint в release.

Текущая ветка:

- сохранена как recoverable engineering checkpoint;
- **не принята для merge в `main`**;
- **не считается завершённой по natural-language quality**.

Последнее полное deterministic evidence внутри coherence checkpoint:

- `pytest -q -m "not live_smoke"` → **736 passed, 2 skipped**;
- `compileall` и `git diff --check` были clean;
- после narrow Google Drive description correction: **122 focused/affected tests passed**;
- Node gate: **23 entries passed**.

Это evidence конкретного checkpoint-а, а не обещание, что нынешний HEAD повторно прогнан после docs-only правок.

## 2. Неподвижные архитектурные границы

### Masha != LLM

Identity, Memory, history, time, permissions и execution truth принадлежат приложению. Модель заменяема.

### Meaning != authority

LLM может предложить смысл реплики и bounded evidence. Она не может:

- выдавать себе capability;
- выбирать application-owned ID как факт без grounding;
- подтверждать mutation;
- объявлять operation выполненной;
- превращать старую историю разговора в новое разрешение.

### Mutation truth

Значимое действие сохраняет разделение:

```text
meaning
→ application validation / state
→ domain ActionProposal
→ policy / Human Confirmation
→ Operation
→ Receipt
→ response projection
```

Model promise ≠ Receipt.

## 3. Текущий dialogue / semantic path

Coherence-ветка заменила operation-first semantic wire на **meaning-first** путь.

Первый semantic request определяет только speech act:

```text
ordinary | create | update | read | unclear
```

На этом шаге модель не получает capability IDs/catalog как выбор действия.

Если реплика является action request, второй bounded шаг получает исходную реплику, текущий bounded turn context и только совместимые application-owned capability specifications.

Результат второго шага остаётся untrusted semantic mapping. Home проверяет:

- supported operation/candidate;
- literal evidence;
- slots и их provenance;
- referents;
- provider ownership;
- grounding;
- application availability/adoption.

Mapping failure после распознанного action request fail-closed в контролируемый unsupported/clarification path; он не выдаёт модели свободную mutation authority.

## 4. Context continuity

Подтверждённый root cause предыдущей «амнезии»: старый `_model_history` обрезал весь предыдущий user/model dialogue после последнего APPLICATION message.

Coherence checkpoint удалил это destructive truncation и сохранил bounded history. Application messages остаются описательной историей результата, а не authorization.

Current turn context также связывает semantic understanding и response generation с application-owned проекциями выбранных/показанных реальных объектов и verified action results.

## 5. Что уже измерено на FAST

Checkpoint измерял semantic behavior на настроенном локальном FAST profile `masha-fast:4b` (`think=false`, temperature 0 в resolver probes).

Доказаны на ограниченных измеренных наборах:

- ordinary personal request остаётся ordinary;
- один relative reminder case корректно использовал focused Calendar event и вычислил 13:00 для события в 14:00;
- saved-reminder update не превращается в duplicate create;
- explicit Google Drive provider conflict больше не может молча уйти в Yandex;
- narrow human-name correction `Google Drive (Гугл Диск)` дала 7/7 правильного routing на измеренном наборе.

Это **не universal language proof**.

## 6. Что ещё НЕ принято

### Relative-time field extraction

Фраза типа:

> «Не дай мне забыть об этом, напомни за полчаса до события»

может выбрать правильную reminder capability, но модель всё ещё способна вернуть date/time вместо `relative_time`. Application правильно отклоняет неподходящие поля; ослаблять grounding ради красивого успеха нельзя.

### Complete multi-turn dialogue journeys

Нужны маленькие законченные сценарии:

```text
earlier result
→ clarification / correction
→ confirmation
→ verified outcome
```

и отдельная проверка обычного нового разговора с уместным продолжением незавершённой темы.

### Human conversational acceptance

Deterministic tests не принимают естественный язык. Нужна ручная приёмка живых complete journeys на реальном локальном профиле.

## 7. Реализованные системные контуры

Текущая система уже имеет application-owned контракты для следующих областей:

- Identity Kernel;
- SQLite long-term Memory и Human Information / Recall;
- conversation history и bounded model context;
- deterministic Home time (`Europe/Saratov`);
- Commitments / reminders / proactive runtime;
- Shared Continuity и Masha Reflections;
- bounded Skills / permissions / Agent capability foundation;
- Emergency Stop;
- local desktop Home / Presentation contracts;
- read-only Web observation and safe Web Fetch;
- contextual external observation;
- bounded PDF/document reading, включая explicitly selected local PDF;
- connector-backed capability families behind application ownership boundaries;
- encrypted Whole-Home backup;
- Whole-Home recovery with checkpoint/rollback and Recovery Hold.

Наличие контура не означает, что каждая natural-language формулировка, connector journey или UI surface полностью принята человеком.

## 8. Evaluation rule

Качество разделено по владельцам:

```text
hard deterministic invariant → tests/
variable language/model behavior → evals/
whole-product conversational feel → Human Review
```

Green tests ≠ good conversation.

Подробнее: [`../evals/README.md`](../evals/README.md).

## 9. Следующий инженерный gate

Не начинать новый broad redesign.

Продолжить с [`AGENT_COHERENCE_PLAN.md`](AGENT_COHERENCE_PLAN.md):

1. измерить оставшиеся relative-time mapping/field failures;
2. не добавлять phrase-specific routing и не ослаблять evidence/grounding;
3. прогнать несколько complete multi-turn journeys на synthetic/fake adapters;
4. затем выполнить ручную live acceptance;
5. только после этого повторить нужные gates и отдельно решать вопрос merge.

## 10. Источники истины

- продуктовые принципы → [`../CONSTITUTION.md`](../CONSTITUTION.md);
- текущий фактический implementation status → **этот документ**;
- архитектурный канон → [`MASHA_HOME_CANON.md`](MASHA_HOME_CANON.md);
- принятые решения → [`DECISIONS.md`](DECISIONS.md);
- dialogue/action ownership → [`DIALOGUE_ACTION_LIFECYCLE.md`](DIALOGUE_ACTION_LIFECYCLE.md);
- active engineering provenance → [`AGENT_COHERENCE_PLAN.md`](AGENT_COHERENCE_PLAN.md);
- доменные/security contracts → соответствующие `MEMORY_*`, `W*`, Presentation и provider-specific документы.

Historical snapshot/stage/workshop документы объясняют, **как мы сюда пришли**, но не переопределяют текущее состояние.

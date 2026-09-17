# Masha Home — карта документации

Этот файл — только навигация. Он не создаёт новый источник архитектурной истины.

Правило приоритета: **текущий код + `CURRENT_STATE.md` + подтверждённые checkpoint-ы + нормативные контракты важнее исторических планов и снимков**.

## Current Source of Truth

- [`../CONSTITUTION.md`](../CONSTITUTION.md) — продуктовые и человеческие принципы Masha Home.
- [`CURRENT_STATE.md`](CURRENT_STATE.md) — фактическое implementation/release состояние на сегодня.
- [`MASHA_HOME_CANON.md`](MASHA_HOME_CANON.md) — стабильная архитектурная модель и продуктовый roadmap.
- [`DECISIONS.md`](DECISIONS.md) — журнал принятых и superseding решений.
- [`DIALOGUE_ACTION_LIFECYCLE.md`](DIALOGUE_ACTION_LIFECYCLE.md) — ownership и lifecycle для meaning / proposal / confirmation / operation / receipt.
- [`AGENT_COHERENCE_PLAN.md`](AGENT_COHERENCE_PLAN.md) — активная continuation capsule ветки `new/agent-coherence-continuation`. Это рабочий checkpoint, не релиз.

Если status/roadmap-текст старого документа расходится с `CURRENT_STATE.md` и newest verified checkpoint, приоритет имеет более новое подтверждённое состояние.

## Нормативные и runtime-контракты

### Identity и Memory

- [`IDENTITY_GUIDE.md`](IDENTITY_GUIDE.md)
- [`MEMORY_SPEC.md`](MEMORY_SPEC.md)
- [`HUMAN_INFORMATION_MODEL_V0.3.1.md`](HUMAN_INFORMATION_MODEL_V0.3.1.md)
- [`PASSIVE_MEMORY_V0.3.md`](PASSIVE_MEMORY_V0.3.md)
- [`QUERY_AWARE_RETRIEVAL_V0.2.md`](QUERY_AWARE_RETRIEVAL_V0.2.md)

### Web / Documents / External evidence

- [`W1_EXTERNAL_OBSERVATION.md`](W1_EXTERNAL_OBSERVATION.md)
- [`W2_WEB_FETCH.md`](W2_WEB_FETCH.md)
- [`W3_CONTEXTUAL_EXTERNAL_OBSERVATION.md`](W3_CONTEXTUAL_EXTERNAL_OBSERVATION.md)
- [`W4_DOCUMENT_READ.md`](W4_DOCUMENT_READ.md)
- [`W4_1_LOCAL_DOCUMENT_INPUT.md`](W4_1_LOCAL_DOCUMENT_INPUT.md)

### Backup / Recovery

- [`W5_1_WHOLE_HOME_BACKUP.md`](W5_1_WHOLE_HOME_BACKUP.md)
- [`W5_2_WHOLE_HOME_RECOVERY.md`](W5_2_WHOLE_HOME_RECOVERY.md)

### Presentation / Home UI

Не каждый `UI-*` файл является текущим контрактом. Часть файлов фиксирует workshop/review history.

Стабильные архитектурные точки входа:

- [`UI-02_5_PRESENTATION_MODEL.md`](UI-02_5_PRESENTATION_MODEL.md)
- [`UI-04_HOME_COMPOSITION_CONTRACT.md`](UI-04_HOME_COMPOSITION_CONTRACT.md)
- [`UI-05A_LOCAL_CONVERSATION_HOST_BOUNDARY.md`](UI-05A_LOCAL_CONVERSATION_HOST_BOUNDARY.md)
- [`UI-06A_INTERACTION_GRAMMAR.md`](UI-06A_INTERACTION_GRAMMAR.md) — interaction model; readiness-статусы нужно читать с учётом более новых checkpoint-ов.

## Active engineering history

- [`LIVING_HOME_LANGUAGE_CORE_PLAN.md`](LIVING_HOME_LANGUAGE_CORE_PLAN.md) — реализованные language-core checkpoint-ы и provenance. Новая работа продолжается в `AGENT_COHERENCE_PLAN.md`.
- [`AGENT_COHERENCE_PLAN.md`](AGENT_COHERENCE_PLAN.md) — единственный активный continuation-план этой ветки.

## Historical records

Исторические inception-документы сохранены в:

- [`archive/inception/ARCHITECTURE_SNAPSHOT.md`](archive/inception/ARCHITECTURE_SNAPSHOT.md)
- [`archive/inception/IMPLEMENTATION_PLAN.md`](archive/inception/IMPLEMENTATION_PLAN.md)
- [`archive/inception/PROJECT_CONTEXT.md`](archive/inception/PROJECT_CONTEXT.md)

Старые пути `ARCHITECTURE_SNAPSHOT.md`, `IMPLEMENTATION_PLAN.md`, `PROJECT_CONTEXT.md` оставлены как короткие redirect-stubs, чтобы не ломать старые ссылки. Они не являются текущим roadmap.

Завершённые `STAGE_*`, старые `MEM-*` design records и часть UI workshop/review документов остаются кандидатами на `docs/archive/`, но только после отдельного reference/runtime audit. Возраст файла сам по себе не является причиной для архивации.

## Evaluation

См. [`../evals/README.md`](../evals/README.md).

Короткое правило:

- deterministic tests проверяют инварианты и application truth;
- evals проверяют вариативное качество языка/semantic behavior;
- Human Review принимает целостный пользовательский опыт.

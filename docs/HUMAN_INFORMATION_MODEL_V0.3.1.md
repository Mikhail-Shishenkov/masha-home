# Masha Home v0.3.1 — Human Information Model

Статус: канонический application-контракт Slice A
Базовая версия: `v0.3` / `f446f42fa8f115876709b06982f20277000a06df`

## Граница архитектуры

Система сохраняет три раздельных слоя:

1. **Storage** — богатые доменные записи Memory v0.4 и их собственные lifecycle.
2. **Recall** — application-owned выбор информации для поиска или текущего разговора.
3. **Working Context** — не более 6 человекочитаемых элементов, 3600 символов суммарно и 2000 символов на элемент для одного ModelRequest.

`HumanInformationService` агрегирует домены, но не владеет их переходами и не
добавляет второй статус в хранилище. `MemoryIntentHandler` остаётся обработчиком
явных conversational capabilities: поиск и восстановление делегируются
отдельному сервису, а запись выполняется существующим proposal/confirmation
контрактом `MemoryManagementService`.

## Четыре человеческих типа

| HumanEntityKind | Доменные записи |
|---|---|
| MEMORY | `Fact`, `Decision` |
| HISTORY | `Episode`, `RelationshipMemory` |
| TASK | `Commitment` |
| THREAD | отдельный `ContinuityFollowUp` |

`ContinuityState` не является человеческим результатом. `MashaReflection`,
`AffectiveRecord` и `MemoryCandidate` не входят в унифицированный поиск этого
этапа. Passive candidates остаются отдельным review workflow.

## Availability: ACTIVE, ARCHIVED, FORGOTTEN

- **ACTIVE** — запись является текущей и может участвовать в CURRENT Recall.
- **ARCHIVED** — запись законно относится к прошлому и доступна нормальному
  поиску/RETROSPECTIVE Recall.
- **FORGOTTEN** — Миша явно попросил не использовать запись. Она исключена из
  Home, CURRENT, RETROSPECTIVE и обычного поиска; увидеть её можно только через
  явный `FORGOTTEN_REVIEW`.

ARCHIVED не хранится отдельным флагом: он выводится из реального доменного
статуса. FORGOTTEN имеет приоритет и в Memory v0.4 представлен
`visibility=hidden`.

### Lifecycle truth matrix

| Stored record / state | Kind | Availability | Default Home | Normal search | CURRENT | RETROSPECTIVE | FORGOTTEN_REVIEW | Human action | Confirmation | Trustworthy time |
|---|---|---|---:|---:|---:|---:|---:|---|---:|---|
| Fact `active`, visible | MEMORY | ACTIVE | yes | yes | yes, if relevant | yes | no | forget | yes | `created_at` |
| Fact `superseded`, visible | MEMORY | ARCHIVED | no | yes | no | yes | no | forget | yes | `created_at` |
| Fact hidden, any status | MEMORY | FORGOTTEN | no | no | no | no | yes | restore | yes | `created_at` |
| Decision `active`, visible | MEMORY | ACTIVE | yes | yes | yes, if relevant | yes | no | forget | yes | `created_at` |
| Decision `superseded/cancelled`, visible | MEMORY | ARCHIVED | no | yes | no | yes | no | forget | yes | `created_at` |
| Decision hidden, any status | MEMORY | FORGOTTEN | no | no | no | no | yes | restore | yes | `created_at` |
| Episode visible | HISTORY | ACTIVE | selected only | yes | yes, if relevant | yes | no | forget | yes | `occurred_at` |
| Episode hidden | HISTORY | FORGOTTEN | no | no | no | no | yes | restore | yes | `occurred_at` |
| RelationshipMemory `current`, visible | HISTORY | ACTIVE | selected only | yes | yes, if relevant | yes | no | forget | yes | `created_at` |
| RelationshipMemory `revised`, visible | HISTORY | ARCHIVED | no | yes | no | yes | no | forget | yes | `created_at` |
| RelationshipMemory hidden | HISTORY | FORGOTTEN | no | no | no | no | yes | restore | yes | `created_at` |
| Commitment `open`, visible | TASK | ACTIVE | yes | yes | yes, if relevant | yes | no | complete / forget | yes | `created_at` |
| Commitment `completed/cancelled/expired`, visible | TASK | ARCHIVED | no | yes | no | yes | no | forget | yes | `completed_at` when completed, otherwise `created_at` |
| Commitment hidden, any status | TASK | FORGOTTEN | no | no | no | no | yes | restore | yes | same domain time as above |
| ContinuityFollowUp `open` | THREAD | ACTIVE | yes | yes | yes, if relevant | yes | no | resolve | yes | none |
| ContinuityFollowUp `resolved/snoozed` | THREAD | ARCHIVED | no | yes | no | yes | no | none | n/a | none |
| MemoryCandidate any status | — | excluded | no | no | no | no | no | candidate review only | existing candidate flow | `created_at` only in its own workflow |

У `ContinuityFollowUp` нет собственного creation timestamp. Время родительского
`ContinuityState.updated_at` не подставляется.

## Forget, restore и legacy archive

- **FORGET**: `visible → hidden`; исключает запись из обычного использования,
  но сохраняет content, provenance, audit и доменный статус.
- **RESTORE**: `hidden → visible`; не меняет доменный статус или provenance,
  требует отдельного подтверждения и пишет `memory_restore` audit event.
- **HARD DELETE**: необратимое уничтожение; не реализовано.

Legacy `MemoryMutationOperation.ARCHIVE` сохранён для совместимости и, как и
раньше, скрывает запись. Он **не** определяет человеческий ARCHIVED. Новые
search/recall flows вычисляют archive только из доменного lifecycle.

Restore использует один user-facing pending slot, транзакцию целого
валидированного документа, proposal-specific audit/postcondition и безопасный
retry существующего confirmation pipeline. Фраза «Верни её» разрешается только
от application-owned `PresentedEntitySet`; видимость не меняется до «да».

## Search contract

Публичная граница — `search_information(HumanSearchRequest)`.

- scopes: `ALL`, `HISTORY` (memory/history/thread), `TASKS`;
- обычный explicit search: ACTIVE + ARCHIVED, FORGOTTEN исключён;
- forgotten search: только явный `FORGOTTEN_REVIEW`;
- deterministic lexical relevance, phrase signal и небольшая recency-поправка;
- relevance gate до limit, без fill-to-limit и без embeddings/vector DB;
- mixed results сортируются по relevance, затем детерминированно;
- conversation rendering переиспользует `PresentedEntitySet`, поэтому ordinal
  означает реальную typed application entity, а не номер из текста Qwen.

Опциональный time filter поддерживает `today`, последние 7/30 дней и явный
локальный диапазон. Он использует один Home timezone provider. Активный default
этого репозитория — `Europe/Saratov`; сохранение времени остаётся UTC.

## Recall contract

Публичная граница — `recall_information(HumanRecallRequest)`.

- **CURRENT**: только ACTIVE. Existing Query-aware Retrieval остаётся первичным
  selector с принятыми threshold/budget; human layer нормализует его результат
  и может дополнить релевантным TASK/THREAD без второго model call.
- **RETROSPECTIVE**: ACTIVE + ARCHIVED; применяется для «помнишь», «раньше»,
  «что я уже сделал» и других детерминированных past markers.
- **FORGOTTEN_REVIEW**: только FORGOTTEN и только по явному запросу.

`CURRENT` сохраняет lexical gate, thresholds `0.30/0.26`, no-fill behavior и
локальный optional semantic extension существующего retriever. Capability
routing по-прежнему выполняется до retrieval. На один пользовательский ход не
добавляется второй Qwen call.

Deictic «по этому поводу» может дополнить lexical query максимум тремя
последними user turns. Это не RAG по raw transcript и не новая conversation
storage schema.

## Model-facing privacy and stale readouts

В `ModelRequest.private_context["memory_context"]` допускаются только
человекочитаемые поля `category`, `content`, `state`, `time`, `confidence`.
Compiler применяет allow-list. Туда не попадают IDs/UUID, `record_id`,
`candidate_id`, `memory_reference`, scores, retrieval reasons, audit payload,
SQLite path или названия developer enums/classes. Полный internal trace остаётся
в `HumanRecallResult.trace` для диагностики.

APPLICATION-сообщения остаются в человеческом transcript, но не replay-ятся в
model history. Текущая domain state/Recall становится единственным authority;
старый список больше не может вернуть забытую, завершённую, закрытую или
заменённую запись как актуальную system truth.

## Сознательно отложено

UI поиска/архива, embeddings, vector DB, LLM-driven routing, raw transcript
search/RAG, hard delete, automatic candidate approval, proactivity tools и
изменение scene/navigation не входят в Slice A.

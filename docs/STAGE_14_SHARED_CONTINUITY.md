# Stage 14 — Shared Continuity

Статус: **IMPLEMENTED**

## Зачем

Stage 14 превращает предусмотренные Memory v0.4 сущности `RelationshipMemory`
и `ContinuityState` в работающий пользовательский контур. Это не ещё один
профиль пользователя и не автоматическое резюме чата. Это подтверждённая
память о том, что имеет значение **между Машей и Мишей**, плюс небольшой список
тем, к которым они сознательно хотят вернуться.

Главное отличие от обычной companion memory: система не считает красивую
интерпретацию модели общей правдой. Она хранит происхождение записи, различает
факт, событие, обязательство, relational meaning и открытую нить, а запись
возникает только после явного подтверждения Миши.

## Человекочитаемые сценарии

В разговоре:

```text
Маша, сохрани как наш момент: мы впервые запустили тебя полностью локально
→ preview
→ да
→ RelationshipMemory в SQLite + audit

Маша, оставь открытой нитью: придумать наш домашний ритуал запуска
→ preview
→ да
→ ContinuityFollowUp в существующем ContinuityState + audit

Маша, закрой нить: домашний ритуал
→ preview
→ да
→ статус follow-up становится resolved + audit
```

CLI:

```text
continuity
continuity open <тема>
continuity resolve <тема>
continuity confirm
continuity reject
continuity --raw
```

Обычный вывод называется «Что между нами продолжается» и не показывает UUID,
payload или внутренние IDs. `--raw` остаётся локальной диагностикой.

## Архитектура

```text
explicit user phrase
  → MemoryIntentHandler
  → existing MemoryProposalStore
  → human preview
  → explicit confirmation
  ├─ RelationshipMemory → ConfirmedMemoryService
  └─ ContinuityState update → SharedContinuityService
  → existing MemorySqliteRepository
  → existing audit log

MemorySqliteRepository
  → existing MemoryRetriever
  → bounded WorkingMemory
  → ConversationContextCompiler
  → provider-neutral ModelRequest
  → ModelRouter → active local model
```

Новая SQLite migration не потребовалась: обе сущности уже входят в Memory v0.4
и хранятся в `memory_records` существующего repository.

## Семантические границы

- `Fact` — утверждение о мире или пользователе.
- `Episode` — историческое событие.
- `Commitment` — обязательство, которое можно выполнить или отменить.
- `RelationshipMemory` — явно подтверждённое значение для общей истории.
- `ContinuityFollowUp` — тема, к которой стоит вернуться; это не Commitment.

Открытая нить не разрешает Маше самостоятельно писать пользователю и не меняет
proactive policy. Закрытие нити не завершает Commitment. Обычный разговор не
создаёт ни одну из этих записей автоматически.

## Perspective discipline

Сейчас система сохраняет только явно заявленный Мишей текст и метаданные
подтверждения. Она не генерирует «мнение Маши» задним числом и не изображает
согласие двух сторон там, где его не было. Будущая Masha Reflection должна быть
отдельной сущностью с собственным provenance и отдельным согласованным flow.

## Legacy data dignity

В production SQLite обнаружены старые `ContinuityState`-фрагменты с повреждённой
кодировкой. Stage 14 не удаляет и не исправляет их без решения пользователя.
Очевидный mojibake детерминированно исключается из normal retrieval и human UX,
остаётся неизменным в SQLite и доступен через `continuity --raw`. Новые корректные
нити в том же состоянии продолжают работать.

## Не входит

- автоматическое извлечение отношений или эмоций из чата;
- скрытый психологический профиль;
- автоматическая запись «точки зрения Маши»;
- изменение Identity manifest;
- новые границы поддержки или «дружеского пинка»;
- разрешение на proactive contact;
- scheduler, tools, external APIs или model fallback;
- автоматическая очистка legacy-данных.


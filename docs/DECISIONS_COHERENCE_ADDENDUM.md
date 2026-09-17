# Masha Home — Coherence Decisions Addendum

Статус: **принятые решения активного coherence checkpoint; подлежат переносу в основной `DECISIONS.md` после acceptance/merge preparation**  
Дата: 2026-09-17

Этот addendum существует, чтобы не переписывать старый append-only decision log задним числом во время незавершённой ветки.

## COH-001. Bounded conversation history сохраняется через application messages

Статус: **Принято и реализовано в coherence checkpoint; требуется conversational acceptance**

Bounded prior user/model dialogue сохраняется. Application history может присутствовать как датированное descriptive context, но не выдаёт новой authority. Mutation truth остаётся у proposal/confirmation/operation/receipt owners.

## COH-002. Semantic resolution является meaning-first

Статус: **Принято и реализовано; natural-language acceptance не завершена**

Первый model step определяет только speech act:

```text
ordinary | create | update | read | unclear
```

Для action-like turn отдельный bounded mapping step использует исходную пользовательскую реплику и только совместимые application-owned capability specifications.

Это supersedes operation-first interpretation wiring прежних Slice 2A–2E, сохраняя их authority invariants.

## COH-003. Semantic output никогда не является execution authority

Статус: **Принято**

Speech-act proposal, semantic mapping, `InterpretationFrame` и resolved handoff содержат только meaning/evidence. Они не создают permission, confirmation, mutation result или receipt.

## COH-004. Presented/focused real objects являются application-owned reference truth

Статус: **Принято и реализовано для текущего bounded context**

Модель может понимать «это», «его», «тот второй», но реальный referent должен происходить из application-owned presented/focused state. Модель не создаёт реальный ID из текста.

## COH-005. Provider ownership conflict fail-closed

Статус: **Принято и реализовано как validation boundary**

Явно названный provider не должен молча заменяться другим. Application может veto конфликтующий semantic candidate, но не обязана придумывать замену ради успешного ответа. Упоминание provider-а как темы не равно request destination.

## COH-006. Relative-time arithmetic и language extraction разделены

Статус: **Принято; language extraction ещё under acceptance**

Language layer предоставляет grounded temporal evidence/field intent. Application-owned temporal components выполняют реальную арифметику по typed anchor.

Нельзя ослаблять grounding, подменять domain identity или добавлять phrase-specific routing ради прохождения примера.

Current known blocker: модель может выбрать правильную reminder capability, но вернуть date/time вместо `relative_time`.

## COH-007. Deterministic tests не являются conversational acceptance

Статус: **Принято**

```text
hard invariant → deterministic tests
variable semantic/language behavior → evals
complete product feel → Human Review
```

Зелёный deterministic gate не доказывает естественность языка и качество complete dialogue journey.

## COH-008. Complete dialogue journey является единицей conversational acceptance

Статус: **Принято; gate ещё не закрыт**

Для действий acceptance должна включать минимум:

```text
context/result
→ reference
→ clarification/correction
→ proposal/preview
→ explicit confirmation
→ operation
→ verified receipt
→ natural follow-up
```

Engineering writes по возможности проверяются fake/synthetic adapters.

## COH-009. Merge требует отдельного human approval после acceptance

Статус: **Принято для текущей ветки**

Публикация recoverable checkpoint и docs-only работа не равны approval на merge.

До merge должны быть relevant deterministic gates, semantic/language evals, ручная acceptance complete journeys и отдельное решение Миши.

## Текущие открытые вопросы

1. надёжность `relative_time` field extraction на fixed + unseen paraphrases;
2. complete multi-turn action journeys;
3. gentle cross-chat continuity без task-review greeting и sensitive resurfacing;
4. перенос variable language benchmarks из deterministic test слоя в `evals/` без framework-overbuild;
5. capability-by-capability retirement только доказанно superseded compatibility routes;
6. human acceptance connector-backed natural-language journeys;
7. декомпозиция крупных модулей только по реальной change pressure, не ради метрик размера.

Web, document read, whole-Home backup/recovery и basic agent capability foundation больше не являются «будущими архитектурными вопросами»: эти boundaries уже реализованы и документированы.

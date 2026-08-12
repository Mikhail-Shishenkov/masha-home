# UI-06F — Slice A: Activity and Proactive Presence

Дата: 2026-08-12
Статус: **IMPLEMENTED**

## Что подключено

После принятия capability grammar production Home получил два контекстных
объекта. Они не являются постоянными пунктами меню:

- `Работа` появляется только при наличии настоящего локального Agent Run receipt;
- `Рядом` появляется только для уже доставленного Reminder или Check-in.

Agent Run проецируется через bounded application view. Renderer видит цель,
человеческий статус и названия зафиксированных шагов, но не получает tool IDs,
operations, policy reasons, plan hash, inputs или raw results. UI не предлагает
pause/cancel/continue, потому что общего production-контракта этих действий пока
нет.

Proactive surface не обнаруживает события, не принимает policy-решения и не
вызывает LLM. Он показывает результат уже существующего deterministic runtime и
позволяет выполнить только поддерживаемые lifecycle actions:

```text
delivered → acknowledged | dismissed
```

Acknowledge/dismiss меняют только proactive interaction/event lifecycle. Memory,
Identity, Commitment и Conversation history не изменяются.

## Цепочка

```text
AgentRunStore receipt
→ ActivityApplicationService
→ MashaApplication
→ allowlisted WebChannel read
→ Activity surface

ProactiveInteractionStore delivered row
→ ProactiveApplicationService
→ MashaApplication
→ allowlisted WebChannel read/action
→ Reminder or Check-in surface
→ existing acknowledge/dismiss lifecycle
```

## Границы

- нет новых agent actions;
- нет fake progress;
- нет scheduler или polling;
- нет новых LLM-вызовов;
- нет automatic proactive delivery;
- нет schema migration;
- нет доступа renderer к SQLite или local-data;
- Emergency Stop не обходится и не запускает работу.

Следующий срез после проверки интерфейса: **Slice B — Memory, Shared Continuity,
Reflection and Honest Help**, сначала как read-only UI-safe projections.

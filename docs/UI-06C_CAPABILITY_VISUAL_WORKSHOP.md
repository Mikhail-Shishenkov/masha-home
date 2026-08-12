# UI-06C — Capability Visual Workshop

Дата: 2026-08-12  
Статус: **DISPOSABLE VISUAL WORKSHOP — NO BACKEND BINDING**

## Цель

Показать в одной согласованной визуальной грамматике десять уже существующих
возможностей Masha Home до создания новых UI-safe application projections и
production bridge actions.

## География

- диван и пространство «между нами»: check-in, общая история, рефлексия;
- журнальный столик: обязательство, напоминание, подтверждение;
- рабочий стол: Activity/Agent Run, навыки/permissions, модели и runtime;
- каноничная комната и Маша остаются одним неподвижным кадром;
- меняются ambient focus, spatial surface и его содержимое, а не Identity.

## Сцены

1. Commitment;
2. typed Confirmation;
3. Activity / Agent Run;
4. proactive Reminder;
5. Check-in;
6. Shared Continuity;
7. Masha Reflection / Honest Help;
8. Skills / Permissions;
9. Local Model Profiles;
10. Runtime problem / recovery.

## Границы

- нет доступа к backend, SQLite, Ollama, IdentityKernel или local-data;
- нет новых LLM-вызовов и model-selected presentation;
- действия внутри workshop создают только локальный presentation receipt;
- ни один surface не утверждает, что mutation уже выполнена;
- production `frontend/` и закрытый WebChannel bridge не изменяются;
- никакие новые позы или выражения Маши не генерируются до визуального выбора.

## Следующий gate

После совместного визуального review выбираются сцены и lifecycle, которые
переходят в production. Для них отдельно создаются bounded UI-safe views и
allowlisted actions. Рекомендуемый первый binding slice:

```text
Commitment + typed Confirmation + Activity + Proactive delivery
```

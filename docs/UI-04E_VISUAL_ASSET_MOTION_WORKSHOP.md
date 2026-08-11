# UI-04E — Visual Asset & Motion Workshop

Статус: **DISPOSABLE LAYERED WORKSHOP IMPLEMENTED / VISUAL REVIEW REQUIRED**

Дата: **2026-08-11**

## Цель

UI-04E заменяет UI-04D carousel как основной способ проверки композиции. Вместо
переключения цельных storyboard-кадров prototype собирает одну сцену из слоёв:

```text
Room
→ depth + ambient light
→ Masha pose/outfit
→ Masha expression + attention
→ spatial Interaction Surfaces
→ environmental response
→ safety overlay
```

UI-04D остаётся reference layer. UI-04E не является production frontend,
framework decision или новым Presentation Runtime.

## Архитектурная граница

Workshop повторяет renderer-neutral смыслы существующего `CompositionPlan`:

- `presence_first` — default;
- `conversation_first` — deep conversation;
- `adaptive_cinematic` — Activity;
- wide / standard / narrow / very narrow desktop hierarchy;
- независимые Presence, Surface, ambient и safety axes.

Backend, `CompositionResolver`, Identity, Memory, SQLite, LLM, Agent Loop и
domain contracts не изменяются. Runtime visual generation отсутствует.

## Asset registry

Registry находится в `prototypes/ui-04e/workshop-core.js`. Renderer видит только
opaque IDs. Пути к PNG остаются деталями disposable adapter.

Identity / Room:

```text
masha.visual.identity
room.default
room.evening
```

Pose:

```text
masha.pose.idle
masha.pose.conversation
masha.pose.activity
masha.pose.attention
```

Expression:

```text
masha.expression.neutral
masha.expression.warm
masha.expression.happy
masha.expression.amused
masha.expression.thoughtful
masha.expression.skeptical
masha.expression.slightly_annoyed
masha.expression.concerned
masha.expression.focused
masha.expression.tender
```

Attention:

```text
masha.attention.none
masha.attention.user
masha.attention.surface
```

Outfit:

```text
masha.outfit.everyday
masha.outfit.work
masha.outfit.evening
masha.outfit.special_evening
```

Surface / Safety:

```text
surface.conversation
surface.activity
surface.confirmation
surface.proactive
overlay.safety
```

## Deterministic state

`workshop-core.js` содержит immutable state, pure reducer и projection. Состояния
выбираются только фиксированными events workshop. Не существует event, через
который LLM могла бы выбрать coordinates, expression, motion или safety state.

Оси остаются композиционными: `attention=user + pose=activity + outfit=work +
safety=normal` является нормальной комбинацией, а не новым giant enum.

## Motion primitives

Authoring vocabulary:

- `attention_shift`;
- `surface_reveal` / `surface_expand`;
- `shared_focus`;
- `room_focus`;
- `pose_blend`;
- `working_surface_reveal`;
- `activity_complete`;
- `ambient_return`;
- `ambient_cue` / `whisper_reveal`;
- `attention_to_object` / `decision_reveal`;
- `autonomous_freeze` / `safety_boundary`.

Primitives ограничены CSS transitions/animations, детерминированы, повторяемы,
interruptible через отмену pending timers и имеют static fallback через
`prefers-reduced-motion`.

## Transition scenarios

1. Idle → Conversation: attention, затем Soft Surface.
2. Conversation → Deep: shared focus и расширение Conversation без исчезновения Маши.
3. Conversation → Activity: room focus, pose blend, Working Surface.
4. Activity → Completed: completing, затем спокойный ambient return.
5. Idle → Check-in: attention, ambient cue, только затем whisper.
6. Confirmation: внимание к spatial Decision Surface.
7. Emergency Stop: autonomous motion freeze и тонкая safety boundary; Conversation
   и Маша остаются доступными.

## Responsive contract

Один layout поддерживает wide, standard, narrow и very narrow desktop. На узком
окне сохраняются Маша и primary Surface; supporting trace исчезает первой.
Вертикальный card/dashboard layout не создаётся.

## Special evening

`special_evening` остаётся одним из восьми visual states, не application mode.
Он использует вечерний room tone, редкий нарядный outfit и `amused/user`
presence. Умеренная чувственность допустима; porn UI, nudity и отдельная
sexualized interaction semantics отсутствуют.

## Disposable

- generated room and raster atlases;
- chroma-key extraction quality;
- CSS coordinates, crop geometry, palette, typography and timing;
- specific clothing, pose details and wording inside Surfaces;
- browser adapter and keyboard controls.

## Contract candidates after review

- layered order and semantic separation;
- opaque registry IDs;
- closed pose/expression/attention/outfit vocabularies;
- deterministic reducer and authored motion vocabulary;
- Presence First default with B/C transformations;
- emergency stop freezes autonomy rather than removing Masha;
- narrow desktop hierarchy and reduced-motion fallback.

Переход к production frontend запрещён до совместного визуального review.

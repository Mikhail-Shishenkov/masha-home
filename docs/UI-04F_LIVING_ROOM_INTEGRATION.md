# UI-04F — Living Room Integration Prototype

Статус: **DISPOSABLE VERTICAL SLICE IMPLEMENTED / HUMAN VISUAL REVIEW REQUIRED**

Дата: **2026-08-11**

## Результат

UI-04F превращает layered workshop в одну постоянную комнату. Маша больше не
собирается из отдельного тела и прямоугольного face crop: каждый pose asset уже
содержит согласованные лицо, волосы, тело, выражение, перспективу и свет.

```text
immutable local state
→ deterministic projection
→ canonical room
→ integrated Masha character state
→ ambient/depth response
→ spatial Conversation / Activity
→ safety/privacy overlays
```

Это disposable browser adapter. Backend, UI-01, `CompositionResolver`, Identity,
Memory, SQLite, LLM, Agent Loop и network не изменены и не подключены.

## Canonical registry

Poses:

```text
masha.pose.idle
masha.pose.conversation
masha.pose.thinking
masha.pose.working
masha.pose.attention_user
masha.pose.attention_surface
```

Expressions:

```text
neutral · warm · happy · amused · thoughtful
skeptical · slightly_annoyed · concerned · focused · tender
```

Attention:

```text
none · user · surface
```

Outfits:

```text
everyday · work · evening · home_evening · special_evening
```

`home_evening` предназначен для спокойного долгого разговора. `special_evening`
остаётся редким эстетичным state, не application mode и не interaction policy.

## Vertical slice

```text
IDLE
→ CONVERSATION
→ ACTIVITY
→ PROGRESS 0 / 28 / 62 / 88 / 100
→ COMPLETED
→ COLLAPSING
→ AMBIENT RETURN
→ IDLE
```

Progress меняет только содержимое существующего Activity spatial object. Комната
не перекомпоновывается на каждом значении. Completion использует authored
`completed → collapsing → ambient_return` и возвращает attention к пользователю.

## Visual composition

- одна canonical room;
- Маша centre-left с контактной тенью и согласованным amber/blue light;
- Conversation справа как световая плоскость без closed card border;
- Activity расширяет рабочую область, но сохраняет supporting Conversation;
- narrow/very-narrow сохраняют Presence и primary Surface;
- supporting Conversation исчезает первой;
- emergency stop замораживает autonomous light paths, но не убирает Машу и chat;
- privacy маскирует содержимое без изменения Identity или lifecycle.

## Motion contract

Разрешены только authored opacity, transform, scale, position, light intensity,
surface reveal/collapse и pose crossfade. Crossfade использует два bounded
character buffers и прерывается новым state. AI morphing, random motion,
physics-driven body deformation и LLM control отсутствуют.

`prefers-reduced-motion` сводит переходы к мгновенной semantic смене.

## Persistent / non-disposable после review

Пока ни один raster asset не объявляется production-canonical. Кандидаты на
устойчивый visual contract:

- одна комната и Presence First hierarchy;
- интегрированный full-character asset вместо face overlay;
- opaque asset registry;
- шесть pose meanings, десять expressions, три attention states, пять outfits;
- spatial Surface lifecycle;
- deterministic vertical slice и ambient return;
- safety/privacy/reduced-motion boundaries.

## Disposable

- конкретные generated PNG;
- chroma-key extraction и зелёный fringe на тонких волосах;
- точные масштабы, crop, coordinates и camera framing;
- contact shadow, palette, typography, wording и CSS effects;
- transition durations;
- direct-file browser adapter и prototype controls.

## Что требуется от человека

1. Подтвердить масштаб Маши и точку её опоры на полу.
2. Подтвердить, что лицо остаётся одной Машей во всех шести poses.
3. Проверить, что Conversation и Activity выглядят частью комнаты без chrome.
4. Выбрать допустимую интенсивность рабочего ambient.
5. Подтвердить `home_evening` и `special_evening` как разные, но родственные states.
6. Решить, достаточно ли Tier 1 layered 2D или нужен более дорогой authored rig.

Framework до этого review не выбирается.

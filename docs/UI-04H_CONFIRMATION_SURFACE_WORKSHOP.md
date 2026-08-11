# UI-04H — Confirmation Surface Workshop

Статус: **DISPOSABLE PROTOTYPE IMPLEMENTED / HUMAN VISUAL REVIEW REQUIRED**

## Цель

Проверить две связанные UI-гипотезы: спокойный Conversation Surface с composer
и explicit confirmation должны существовать рядом с Машей, а не как
dashboard-card или глобальная блокирующая modal.

```text
approved full-scene Conversation asset
→ bounded decision fixture
→ deterministic local reducer
→ translucent near-right Decision Surface
```

## Что реализовано

- Используется цельная `scene.conversation`, а не раздельные room/character
  layers.
- Surface занимает правую quiet zone, не перекрывает лицо или тело Маши.
- Conversation Surface остаётся доступной, когда появляется Decision Surface.
- Composer хранит только bounded in-memory fixture и не имитирует ответ модели.
- Activity Surface показывает локальный presentation lifecycle: running, completed или failed;
  он не запускает agent run и не меняет доменные данные.
- Proactive check-in — только локальный candidate: его можно увидеть, подтвердить ответом или
  скрыть; он не является отправленным сообщением и не создаёт persistent state.
- Emergency Stop и privacy остаются presentation overlay: они не переписывают Safety runtime,
  не мутируют domain state и не запускают побочных действий.
- Нижняя строка состояния — только тихая локальная навигация между visual fixtures; это не
  production navigation, не источник доменного состояния и не доступ к backend.
- В каждый момент раскрыта одна главная поверхность: разговор, задача, решение или check-in.
  Скрытая задача/check-in не отменяется: меняется только presentation focus.
- Conversation Surface показывает bounded in-memory transcript и блокирует отправку до
  демонстрационного fixture-ответа. Это не ConversationService, не LLM streaming и не история,
  сохранённая на диске.
- Переходы surface используют короткую CSS-анимацию и отключаются через `prefers-reduced-motion`.
- Preview показывает только человеческое намерение и три понятных действия:
  подтвердить, изменить, не сейчас.
- `confirm` и `dismiss` меняют только in-memory visual fixture. Никакой Memory,
  Commitment, SQLite или proposal не изменяются.
- Emergency stop скрывает decision surface и блокирует prototype-confirmation.
- Privacy скрывает читаемый контекст, не меняя identity или lifecycle.
- Нет network, model call, persistence, backend import или production frontend
  dependency.

## Review questions

1. Surface выглядит частью комнаты, а не большой стеклянной карточкой?
2. Маша остаётся главным визуальным anchor?
3. Понятно ли, что именно ждёт решения пользователя?
4. Достаточно ли спокойна surface для memory/commitment confirmation?
5. Emergency stop и privacy не теряются в сцене?

## Границы

Это не frontend, не UI-01 integration и не новый confirmation contract.
UI-04H не меняет Identity, Memory, Commitment, Temporal Runtime, Safety,
ModelRouter, Presentation Runtime, CompositionResolver или SQLite.

## Проверки

```powershell
node --test docs/prototypes/ui-04h/confirmation.test.cjs
```

Проверяется локальная asset registry, отсутствие domain mutation, suppression
при emergency stop, privacy invariant и отсутствие запрещённых network/backend
imports.

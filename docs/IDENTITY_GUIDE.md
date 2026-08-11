# Identity Kernel: как утверждать Машу

> **Current runtime status (2026-08-11):** production identity is loaded only by
> `IdentityKernel` from the approved manifest. At CLI startup its
> `identity_version` is validated against the active SQLite memory document;
> a mismatch stops startup without changing either source.

`identity/masha.identity.json` — единственный защищённый источник личности Маши. Он читается Identity Kernel и не должен изменяться LLM, памятью или внешним провайдером.

Manifest версии `masha-0.1` утверждён пользователем. В нём зафиксированы неизменные черты, принципы речи, области естественного развития и два канонических визуальных референса с SHA-256-хэшами. Выражения близости допустимы как язык текстового или визуального образа, но приложение не выдаёт их за реальные физические действия.

Чтобы изменить следующую версию, пользователь определяет:

1. 3–7 постоянных черт, которые Маша не меняет сама.
2. 3–7 принципов её речи и поведения в разговоре.
3. Что в ней может развиваться со временем, но не является неизменной чертой.
4. Канонический визуальный материал и допустимые вариации.
5. Примеры фраз «так можно» и «так нельзя» — без автоматического расширения границ эмоциональной поддержки.

После явного утверждения manifest получает новую версию, автора и время утверждения. Изменение постоянных свойств создаёт новую версию; прошлый manifest сохраняется в истории, а не перезаписывается незаметно. Сценарии из `identity/masha.regression.json` проверяют, что будущая модель сохраняет этот образ в типовых диалогах.

## ID-03 — Identity Evolution Design (design only)

Этот раздел задаёт будущий контракт, но **не реализован** в текущем runtime.
Нынешний manifest `masha-0.1` не изменяется этой задачей.

### Lifecycle

```text
DRAFT → REVIEW → EXPLICIT USER APPROVAL → NEW IDENTITY VERSION
      → MEMORY COMPATIBILITY CHECK → OPTIONAL MEMORY MIGRATION
      → ACTIVATION → ROLLBACK (when explicitly requested)
```

`identity_version` — неизменяемый идентификатор одобренного содержимого
Identity manifest, например `masha-0.1`. Новая версия создаётся для каждого
одобренного изменения identity: старый approved manifest сохраняется как
отдельный артефакт, а не переписывается. Прямое редактирование активного
approved manifest запрещено; изменения начинаются только как draft.

Смена технической схемы при семантически неизменном содержимом, адрес
локального runtime, модель, `think`-режим, размер контекста и другие runtime
настройки не являются изменением Identity и не требуют новой identity version.
Они не должны становиться полями IdentityContext.

### Классификация полей текущего manifest

| Категория | Поля | Почему |
| --- | --- | --- |
| A. Immutable core | `persona.id`, `persona.name`, `persona.role`, `persona.core_traits`, `persona.communication_principles`, `persona.relationship_expressions`, `visual_identity.assets`, `visual_identity.canonical_asset_ids`, `visual_identity.description` | Определяют непрерывность Маши, манеру отношений и канонический образ. Любое изменение требует нового manifest и версии. |
| B. Evolvable identity | `persona.growth_areas`, `visual_identity.allowed_variations` | Описывают разрешённое развитие, но всё равно меняются только через explicit approval и новую версию. |
| C. Operating metadata, not persona/runtime state | `schema_version`, `identity_version`, `status`, `approved_by`, `approved_at`, `visual_identity.status`, asset `id`, `relative_path`, `sha256`, `purpose` | Это метаданные структуры, утверждения или ссылок на asset, а не характер и не текущий runtime state. Они остаются в versioned artifact для проверки целостности, но не должны трактоваться как личность в IdentityContext. |

В manifest не должны появляться настроение, текущие чувства, состояние отношений,
эпизоды общения, ситуативные предпочтения или история совместных событий. Это
runtime/memory state; их границы не определяются этим документом.

### Совместимость памяти

Текущее `MemoryDocument.identity_version = masha-0.1` означает: активная
память проверена для работы с Identity `masha-0.1`. Текущий CLI требует точного
совпадения этой версии с approved manifest.

Для будущего перехода на `masha-0.2` до activation выполняется явная проверка
записей, а не массовая автоматическая перепись:

- независимые факты, проекты и подтверждённые обязательства обычно остаются
  семантически корректны и требуют только явного решения о совместимости;
- запись, смысл которой зависит от прежней формулировки Identity, помечается
  для review;
- противоречащая новой Identity запись требует явного решения пользователя:
  оставить, пересмотреть или архивировать;
- исторический Episode не переписывается: он остаётся свидетельством прошлого,
  но может быть отмечен как относящийся к старой версии;
- записи, не зависящие от Identity, не получают новую интерпретацию лишь из-за
  смены версии.

Активация новой Identity без зафиксированного compatibility outcome невозможна.
Нынешняя SQLite schema не хранит per-record compatibility и migration history;
для реализации потребуется отдельная, согласованная schema change.

### Будущий migration contract

Будущая операция должна содержать минимум:

```text
old_identity_version, new_identity_version, affected_records,
migration_reason, compatibility_outcome, approved_by, approved_at,
timestamp, audit_event_id, rollback_status
```

Её инициирует пользователь либо LLM только как предложение. Пользователь
одобряет и Identity change, и любое изменение long-term memory. LLM не может
выполнять migration. При отказе draft не активируется, а память и текущая
Identity остаются без изменений.

### Approval и rollback

Минимальная будущая операция должна ясно показывать пользователю: старую и
новую версии, список изменённых полей, затронутые memory records, выбранное
compatibility outcome и действие «применить» / «отклонить». Никакое молчание,
обычное сообщение или ответ модели не считается approval.

Rollback выбирает ранее approved immutable manifest и также запускает
compatibility check памяти. Он возможен без rollback memory лишь когда все
записи совместимы с возвращаемой версией; иначе activation блокируется до
явного решения по затронутым записям. Audit должен фиксировать старую и новую
версии, автора approval, diff, время, affected records, migration status и
rollback status. Тихое сохранение несовместимой памяти недопустимо.

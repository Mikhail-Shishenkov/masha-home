# Stage 16 — Agent Capability Gateway

## Status

- `16.1 Skill Contract & Registry`: **IMPLEMENTED**
- `16.2 Action Autonomy Policy`: **PLANNED**
- `16.3 Bounded Agent Loop`: **PLANNED**
- `16.4 First Local Skill`: **PLANNED**
- `16.5 Skill Installation / Upgrade`: **PLANNED**
- `16.6 Permissions UX & Emergency Stop`: **PLANNED**

Stage 16.1 создаёт только безопасный фундамент добавляемых навыков. Он не даёт
Маше инструменты и не меняет действующий conversation contract, согласно
которому tools пока отсутствуют.

## Главный контракт

```text
Skill manifest
  → декларирует возможности, риск, scope и максимум автономности
  → НЕ выдаёт разрешение

Skill Registry
  → обнаруживает локальный пакет
  → валидирует строгий manifest
  → проверяет безопасные package paths
  → вычисляет SHA-256 всего пакета
  → фиксирует explicit registration Миши
  → НЕ импортирует entrypoint
  → НЕ выполняет код
```

Skill, Tool и Permission остаются разными сущностями:

- Skill описывает процедуру и требуемые возможности.
- Tool в будущих этапах предоставит конкретную операцию.
- Action Autonomy Policy решит, разрешена ли операция в заданной области.

LLM не сможет самостоятельно создать себе capability или повысить permission.

## Skill package v1

```text
skills/<skill_id>/
  skill.json
  SKILL.md
  optional future implementation files
```

Manifest содержит только поля, для которых уже определена архитектурная роль:

- стабильные `skill_id`, `version`, `description`;
- optional future `entrypoint`;
- `capabilities`;
- `requested_scopes`;
- `risk_level`;
- `maximum_autonomy_level` — потолок, не разрешение;
- dry-run/rollback declarations;
- deterministic verification description.

Capability taxonomy v1:

- `local_read`;
- `local_write`;
- `process_execution`;
- `network_access`;
- `external_communication`;
- `destructive_operation`;
- `memory_write`;
- `identity_write`.

Manifest не может занизить очевидный риск: write не бывает `observe`, network,
communication и Memory write не ниже `consequential`, destructive и Identity
write всегда `restricted`.

## Persistence and integrity

Registration state хранится в `local-data/config/skills.json`. Это operating
configuration, отдельная от:

- Identity;
- long-term Memory и SQLite schema;
- conversation history;
- proactive policy;
- ModelProfileStore.

Пакет не копируется и не скачивается. Registry фиксирует SHA-256 всех файлов
пакета. Состояния:

- `unregistered` — локально найден, но Миша ещё не зарегистрировал;
- `verified` — текущий пакет совпадает с зарегистрированным digest;
- `modified` — файлы или версия изменились;
- `missing` — зарегистрированная папка исчезла;
- `invalid` — manifest или package boundary некорректны.

Изменённый пакет не считается обновлённым автоматически. Explicit upgrade flow
будет отдельной частью 16.5.

## Human-readable UX

```powershell
.\masha.ps1 skills list
.\masha.ps1 skills show <skill_id>
.\masha.ps1 skills verify <skill_id>
.\masha.ps1 skills register <skill_id>
```

Обычный вывод показывает название, версию, возможности, scope, риск и ясное
предупреждение, что registration не разрешает execution. Digest и полный
технический payload доступны только через `--raw`.

## Security properties

- discovery/list не создаёт registry state;
- registry принимает пакеты только внутри configured `skills/` root;
- unsafe relative paths и symlinks отклоняются;
- entrypoint остаётся строкой и никогда не импортируется;
- registration идемпотентна для неизменившегося пакета;
- tampering обнаруживается после restart;
- никакие данные не отправляются наружу;
- SQLite schema, Identity, Memory, Temporal и LLM runtime не изменяются.

## Not implemented in 16.1

- permission grants;
- enable/disable execution;
- tool adapters;
- import или запуск entrypoint;
- LLM planning;
- agent loop;
- filesystem/process/network actions;
- установка, копирование, скачивание или upgrade пакетов;
- background execution;
- automatic autonomy level;
- новая SQLite migration.

## Known limitations

- registry is a single-user local JSON store without cross-process locking;
- `requested_scopes` are declarations until Stage 16.2 normalizes and enforces them;
- SHA-256 detects local modification but is not publisher signature verification;
- unregister, upgrade and external package installation are intentionally absent;
- a future executor must re-check package integrity immediately before every run,
  not rely on an earlier `verify` command.

## Next safe step

`Stage 16.2 — Action Autonomy Policy`: отдельная локальная policy должна
выдавать standing grants по сочетанию skill + capability + scope + risk и
определять `ALLOW`, `REQUIRE_CONFIRMATION` или `DENY`. Даже после 16.2 никакой
tool не исполняется до отдельного 16.3/16.4.

## Verification

- Stage 16.1 deterministic tests: `15 passed`;
- full project regression: `198 passed`;
- launcher smoke: `masha.ps1 skills list` is human-readable and read-only;
- registration/restart/integrity smoke is covered on an isolated registry;
- production SQLite SHA-256 remained
  `55F0C17A3190C97C1FFC60EDF228AEBCE77793E3D08064455F87810181A7548E`.

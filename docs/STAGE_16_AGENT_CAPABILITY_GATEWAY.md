# Stage 16 — Agent Capability Gateway

## Status

- `16.1 Skill Contract & Registry`: **IMPLEMENTED**
- `16.2 Action Autonomy Policy`: **IMPLEMENTED**
- `16.3 Bounded Agent Loop`: **IMPLEMENTED**
- `16.4 First Local Skill`: **IMPLEMENTED**
- `16.5 Skill Installation / Upgrade`: **IMPLEMENTED**
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
реализован в Stage 16.5 через отдельный preview и confirmation.

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
- registry принимает пакеты только внутри configured bundled `skills/` или
  ignored local `local-data/skills/` roots;
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
- `requested_scopes` are exact symbolic boundaries enforced by Stage 16.2;
  filesystem-path normalization remains part of the future concrete tool adapter;
- SHA-256 detects local modification but is not publisher signature verification;
- unregister, upgrade and external package installation are intentionally absent;
- a future executor must re-check package integrity immediately before every run,
  not rely on an earlier `verify` command.

## Stage 16.2 — Action Autonomy Policy

Persistent policy находится в `local-data/config/action-autonomy.json`, отдельно
от proactive policy. Она содержит только master switch, глобальный maximum
autonomy level и точечные standing grants.

Уровни действий:

- 0 — только советовать, никакого silent execution;
- 1 — наблюдать и диагностировать;
- 2 — безопасные обратимые локальные действия;
- 3 — ограниченные многошаговые задачи;
- 4 — заранее разрешённые локальные routines.

Уровень не является разрешением сам по себе. Для `ALLOW` одновременно нужны:

1. registered + verified skill package;
2. capability и scope внутри manifest;
3. risk и required level внутри manifest ceiling;
4. включённая action policy;
5. action внутри global level;
6. точный standing grant по skill + capability + scope;
7. risk и level внутри grant.

Решения полностью deterministic:

- `ALLOW` — действие укладывается в постоянные границы;
- `REQUIRE_CONFIRMATION` — действие допустимо, но пересекает standing grant;
- `DENY` — skill/package/manifest/master boundary нарушены.

`ActionRequest` является application-owned contract. LLM не может занизить
risk: минимальный риск детерминирован capability. Policy engine не получает
ModelRouter и физически не способен выполнить действие.

Непередаваемые границы Stage 16.2:

- `identity_write` → `DENY`;
- `memory_write` → existing explicit confirmation flow;
- `destructive_operation` → confirmation;
- `external_communication` → confirmation.

Для них standing grant создать нельзя. Network access остаётся consequential и
может быть разрешён только явно конкретному skill/scope; network tool пока не
существует.

Human CLI:

```powershell
.\masha.ps1 skills policy status|on|off|level <0-4>
.\masha.ps1 skills permissions
.\masha.ps1 skills grant <skill> <capability> <scope> <level> [risk]
.\masha.ps1 skills revoke <номер>
.\masha.ps1 skills check <skill> <capability> <scope> <level> [risk]
```

`check` только объясняет решение и всегда пишет, что действие не запускалось.
В normal UX внутренние grant IDs скрыты.

## Next safe step

`Stage 16.6 — Permissions UX & Emergency Stop`: provide one clear human control
surface for installed skills, effective permissions, active/running work and a
local emergency stop. Do not add background autonomy implicitly.

## Verification

- Stage 16.1 deterministic tests: `15 passed`;
- Stage 16.2 deterministic tests: `19 passed`;
- combined Skill Registry + Action Autonomy regression: `34 passed`;
- full project regression: `217 passed`;
- launcher smoke: `masha.ps1 skills list` is human-readable and read-only;
- registration/restart/integrity smoke is covered on an isolated registry;
- production SQLite SHA-256 remained
  `55F0C17A3190C97C1FFC60EDF228AEBCE77793E3D08064455F87810181A7548E`.

Stage 16.2 deterministic coverage includes disabled policy, manifest boundary,
standing grants, narrower risk, autonomy ceilings, revocation, restart,
tampering and non-delegable operations.

## Stage 16.3 — Bounded Agent Loop

Stage 16.3 adds an application-owned sequential loop without an LLM planner and
without real computer access:

```text
AgentPlan
  → step/time/input budgets
  → current Skill Registry integrity
  → current Action Autonomy Policy
  → ALLOW / REQUIRE_CONFIRMATION / DENY
  → pre-execution receipt(state=executing)
  → injected Fake Tool
  → deterministic tool verification
  → verified step receipt
  → next step or terminal result
```

The plan is immutable and digest-bound. Maximums are 20 steps, 3600 seconds and
16 KiB input per step. The current stage accepts plans only from application
code/tests; LLM output is not an authority and is not connected.

### Confirmation

`REQUIRE_CONFIRMATION` pauses before the tool call. Explicit confirmation stores
`confirmed_by=misha` and timestamp, bound to the same plan digest and step. The
confirmation call itself never executes the tool. A separate `run()` resumes
and re-evaluates current policy; confirmation can bypass only
`REQUIRE_CONFIRMATION`, never `DENY`.

### Restart and exactness

- completed, denied, failed and budget-exhausted runs are terminal and never
  silently retried;
- verified steps are skipped after restart;
- same `plan_id` with different content is rejected;
- policy and skill integrity are evaluated again before every new step;
- `executing` is persisted before calling a tool;
- an `executing` step found after restart becomes
  `interrupted_execution_requires_review`, not an automatic replay.

### Proof of result

The loop calls tool verification after every successful execution. A tool
failure, exception or unverified result can never produce `completed`. The
receipt stores bounded summaries and verification codes, not raw step inputs or
tool outputs.

Receipts live in ignored `local-data/runtime/agent-runs.json`, capped at 100.
They are operating evidence, not Memory, Identity or conversation history.

Human read-only UX:

```powershell
.\masha.ps1 agent runs
.\masha.ps1 agent show <номер>
```

Normal output hides plan IDs and hashes. `--raw` remains diagnostic.

### Still not implemented

- real filesystem/process/network tools;
- manifest entrypoint loading;
- LLM goal decomposition or planning;
- background agent execution;
- plan persistence independent of the receipt;
- retries, rollback orchestration or branching plans;
- ConversationService integration;
- automatic Memory or Identity mutation.

### Stage 16.3 verification

- Bounded Agent Loop deterministic tests: `19 passed`;
- Registry + Autonomy + Agent targeted regression: `53 passed`;
- full project regression: `236 passed`;
- read-only launcher smoke: `masha.ps1 agent runs` — successful and created no file;
- production SQLite SHA-256 remained
  `55F0C17A3190C97C1FFC60EDF228AEBCE77793E3D08064455F87810181A7548E`.

## Stage 16.4 — First Local Skill

`ProjectObserver` is the first real Tool Adapter. Its package is declarative:
`entrypoint=null`, capability `local_read`, exact scope
`workspace:masha-home`, observe risk and autonomy ceiling 1. Application code,
not the manifest, injects the adapter into `BoundedAgentLoop`.

```text
human observe command
  → application-owned one-step AgentPlan
  → Skill Registry integrity
  → Action Autonomy Policy
  → tool_id + skill_id binding
  → ProjectObserverTool
  → repeat-read deterministic verification
  → verified ephemeral result
  → human-readable output
```

Supported operations are intentionally small:

- `list_tree`: bounded depth and entry count;
- `read_text`: bounded UTF-8 text from an extension allowlist;
- `inspect_path`: type, bounded size and SHA-256 for a permitted file.

The resolved workspace root is mandatory. Traversal, absolute paths, symlinks,
`.git`, `.venv`, `local-data`, environment/credential files and key material
are blocked. The adapter has no write method, network client or subprocess
runner. It cannot access Identity, Memory, Commitment, TemporalContext,
ConversationService, ModelRouter or SQLite.

Raw observed text is returned only through an in-process callback after the
verified receipt is persisted. Agent receipts still contain only summary and
verification code, so project contents do not become operating history or
Memory. A Tool Adapter must now declare `skill_id`; a mismatched injected tool
is rejected before execution.

Human commands:

```powershell
.\masha.ps1 observe tree [path]
.\masha.ps1 observe read <path>
.\masha.ps1 observe inspect <path>
```

The package is shipped discovered but not automatically registered. Execution
still requires explicit registration, enabled action autonomy and the exact
standing `local_read` grant. There is no LLM planning or automatic permission.

### Stage 16.4 verification

- ProjectObserver + Agent Loop deterministic tests: `32 passed`;
- Registry + Autonomy + Agent + ProjectObserver targeted regression: `66 passed`;
- full project regression: `249 passed`;
- isolated Windows launcher/CLI smoke covered registration, restart-persistent policy/grant,
  tree, text read, metadata/hash inspection and receipt privacy;
- smoke state was removed and no production skill policy was created;
- production SQLite SHA-256 remained
  `55F0C17A3190C97C1FFC60EDF228AEBCE77793E3D08064455F87810181A7548E`.

## Stage 16.5 — Safe Local Installation and Upgrade

The installer is an application service shared by the current CLI and a future
UI. A UI file/folder picker will pass a local directory or ZIP path into the
same contract; the user never needs to copy package code into the repository.

```text
local folder or ZIP selected by Misha
  → bounded inert staging snapshot
  → strict path/size/count/symlink validation
  → SkillManifest + whole-package SHA-256 validation
  → semantic-version and current-integrity check
  → human/UI-ready SkillInstallProposal
  → explicit confirmation
  → revoke old grants on upgrade
  → guarded package swap
  → new Registry integrity pin
  → verified installed package
```

`SkillInstallProposal` exposes the human-relevant preview: skill/name, current
and proposed versions, requested capabilities/scopes, risk, autonomy ceiling,
added/changed/removed files, number of permissions that will be revoked and
whether an application-wired runtime adapter exists. IDs, digests and staging
paths remain technical `--raw` data.

Before confirmation the destination `local-data/skills/` package and Registry
pin are not changed. Bundled repository packages under `skills/` are never
overwritten by UI/CLI installation. The source is copied once into ignored inert staging, so changing or
removing the selected original afterward cannot change the confirmed bytes.
Confirmation revalidates the staged digest. Reject removes the staged snapshot.

Directory and ZIP ingestion enforce:

- local sources only; no URL, marketplace or network client;
- maximum 200 files, 2 MiB per file and 10 MiB total;
- maximum path depth/length and case-insensitive duplicate detection;
- no absolute/traversal/ADS paths, symlinks, encrypted ZIP entries or compiled
  Python artifacts;
- bounded extraction based on actual bytes, not trusted ZIP metadata alone;
- UTF-8 and Windows UTF-8 BOM support for `skill.json`.

Upgrade requires a strictly newer semantic version and a currently verified
package matching the preview. All existing standing grants for that skill are
revoked before activation. Global action-autonomy settings remain unchanged,
but the new package receives no permissions automatically. Installation state
survives restart and repeated confirmation of a completed proposal is
idempotent.

The package manifest remains inert. No entrypoint is imported during preview,
confirmation, registration or later registry checks. A package without a known
application-wired safe adapter can be previewed but confirmation is blocked.
Therefore Stage 16.5 installs safe package declarations; it does not turn
arbitrary downloaded Python into executable authority.

Registry resolves an installed local package first and falls back to the
bundled repository package only when no local override exists. This lets the UI
upgrade a bundled skill without dirtying git or rewriting project code. Removing
an override later would expose the bundled bytes with a mismatched integrity pin,
so execution remains blocked until an explicit future uninstall/recovery flow.

Human CLI:

```powershell
.\masha.ps1 skills install <local-folder-or-zip>
.\masha.ps1 skills install pending
.\masha.ps1 skills install confirm
.\masha.ps1 skills install reject
.\masha.ps1 skills installs
```

This is intentionally ready for a later UI with: local file/folder picker →
preview card → explicit Install/Update or Cancel button. Stage 16.5 does not
implement the visual UI itself.

### Stage 16.5 verification

- Skill Installer deterministic tests: `21 passed`;
- Installer + Registry + Action Policy + ProjectObserver targeted regression: `66 passed`;
- full project regression: `270 passed`;
- isolated Windows launcher smoke covered bundled v1 registration, explicit
  grant, v1.1 local override preview/confirmation, restart verification,
  unchanged bundled bytes and grant revocation;
- Windows UTF-8 BOM manifest handling is covered;
- smoke state was removed and no production install/registry/policy state was created;
- production SQLite SHA-256 remained
  `55F0C17A3190C97C1FFC60EDF228AEBCE77793E3D08064455F87810181A7548E`.

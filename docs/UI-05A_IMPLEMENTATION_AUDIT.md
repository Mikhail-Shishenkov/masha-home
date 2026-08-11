# UI-05A — Desktop Shell Implementation Audit

Статус: **UI-05A.2 IMPLEMENTED / FOLLOW-UP AUDIT PENDING UI-05B**

Дата: 2026-08-11

## Scope audit

Проверены фактические UI-02/02.5/03/04 contracts, `backend/presentation`,
`backend/application`, `masha.ps1`, dependency manifest и текущий working tree.
Никакой production-code, зависимости или SQLite в ходе audit не изменялись.

## Что уже можно переиспользовать

| Component | Фактическое состояние | Роль в UI-05 |
| --- | --- | --- |
| `MashaApplication` | active | единственный application entry point для host |
| `ConversationApplicationService` | active | `ConversationView` и controlled `ConversationTurnResult` |
| `MashaStatusView`, `ModelProfileView`, `SafetyView`, `VisualAssetView` | active immutable UI-safe contracts | bounded bridge payloads |
| `presentation_model_from_application_state` | active read-only adapter | базовая проекция status/model/assets |
| `PresentationRuntime` | active, renderer-neutral | deterministic interaction state |
| `CompositionResolver` / `CompositionPlan` | active, pure | semantic layout authority |
| UI-04H browser workshop | active but disposable | source visual language only, not production renderer |
| `masha.ps1 home` | active | starts the controlled PySide6 desktop shell; the Tk Tier-0 remains separately callable |

## Gaps

1. **Desktop technology is absent.** `PySide6`, `QtWebEngine` и `QtWebChannel` не
   установлены в current `.venv`; `pyproject.toml` не объявляет их optional dependency.
2. **Current `home` is not the web prototype.** Он запускает `backend.presentation.prototype`,
   disposable Tk `TierZeroHomeWindow`.
3. **Controlled origin отсутствует.** Нет `masha://` custom URL scheme, resource handler,
   CSP, navigation policy или WebEngine profile hardening.
4. **Bridge отсутствует.** Нет published QWebChannel QObject и нет allowlisted UI commands.
5. **Unified live Home Snapshot отсутствует.** `MashaApplication` выдаёт безопасные данные
   отдельными методами, но не единый atomic UI snapshot. Frontend не должен склеивать их сам.
6. **Presentation path не собран в public facade.** `CompositionResolver` и presentation adapter
   существуют, но `MashaApplication` не публикует `HomePresentationModel`/`CompositionPlan`
   вместе с conversation content.
7. **Production web assets отсутствуют.** `docs/prototypes` остаётся workshop пространством;
   production renderer нуждается в отдельной asset/theme directory.

## Correct UI-05A architecture

```text
PySide6 Desktop Host
  owns window + lifecycle + hardened WebEngine profile + masha:// origin
  ↓ bounded WebChannel bridge
Application-owned UI projection
  MashaApplication snapshots/results → PresentationRuntime → CompositionResolver
  ↓ JSON-safe presentation/content view
HTML/CSS/JS renderer
```

Host не импортируется в Presentation Runtime. Renderer не импортирует Python internals.
`CompositionPlan` определяет semantic placement; `ConversationView` несёт содержание
переписки. Они передаются вместе в bounded UI snapshot, но не смешиваются по смыслу.

## Security baseline for the shell

- Register `masha` scheme before creating `QApplication`.
- Serve only allowlisted bundled frontend files below one asset root.
- Set CSP: `default-src 'self'; connect-src 'none'; frame-src 'none'; object-src 'none'`.
- Reject external navigation, popup windows, downloads and unknown URL schemes.
- Disable remote resource access and DNS prefetch; do not expose local filesystem URLs.
- Publish one explicit bridge object with a closed method catalog and typed payloads.
- No `eval`, arbitrary QObject slot exposure, filesystem method, generic service call or shell.
- DevTools remain development-only.

## Minimal UI-05 slices

| Slice | Deliverable | Explicitly excluded |
| --- | --- | --- |
| UI-05A.1 | PySide6 window, hardened `masha://home/`, static renderer, `masha.ps1 home` | real application state, UI commands |
| UI-05A.2 | read-only Home Snapshot: status, active model, safety, canonical visual descriptor, CompositionPlan | conversation submit, proactive/action controls |
| UI-05B | one real local conversation turn through `MashaApplication` | streaming, browser transport, external services |
| UI-05C | explicit safety/model controls through closed bridge commands | autonomous new capabilities |

## First implementation plan: UI-05A.1

1. Add a `ui` optional dependency group for pinned PySide6 including WebEngine.
2. Add a new desktop-host package, isolated from `backend/presentation`.
3. Register `masha://` as a secure local scheme before `QApplication`.
4. Add an allowlisted static resource handler serving a new production frontend root.
5. Create a minimal Home window that loads only `masha://home/index.html`.
6. Add host-only tests for scheme registration/configuration and resource-root traversal denial.
7. Switch `masha.ps1 home` from Tk Tier-0 to the new host only after the host smoke succeeds.
8. Keep `backend.presentation.prototype` callable directly as the retained Tier-0 fallback.

## Planned files for UI-05A.1

```text
pyproject.toml
masha.ps1
backend/ui/__init__.py
backend/ui/desktop_host.py
backend/ui/local_origin.py
backend/ui/frontend/index.html
backend/ui/frontend/styles.css
backend/ui/frontend/app.js
tests/test_desktop_host.py
docs/UI-05A_DESKTOP_SHELL.md
```

The exact Qt module/package names will be confirmed only after installing the declared optional
dependency. No existing Identity, Memory, LLM, Temporal, Agent, Safety or SQLite module is a
planned edit.

## Human decisions required before later slices

- **UI-05A.1:** none beyond the already accepted PySide6 + Qt WebEngine direction.
- **UI-05A.2:** confirm whether privacy masking should activate immediately on window unfocus;
  this is a user-facing privacy semantic, not a renderer detail.
- **UI-05B:** choose the default local `project_id` binding visible to the desktop host.

## Audit conclusion

UI-05A.1 can be implemented without changing existing domain architecture. The only new
production concern is the desktop shell boundary itself. A unified Home Snapshot is deferred to
UI-05A.2 so that the first executable window is small, auditable and reversible.

## Implementation follow-up (UI-05A.1–A.2)

The original audit gaps for the desktop shell and the unified read-only projection are now
closed. `masha.ps1 home` starts the hardened `masha://home/` PySide6 shell. The public
`MashaApplication.home_snapshot()` is the sole source for the initial renderer payload:
`MashaStatusView`, active `ModelProfileView`, canonical `VisualAssetView` metadata,
`HomePresentationModel`, and a deterministic `CompositionPlan` are created together by the
application layer. The desktop host injects that JSON once after the local document loads.

There is intentionally no renderer-to-host bridge yet: no QWebChannel, no JavaScript command,
no message submission, no persistence mutation, and no direct browser access to a domain
service. A future UI-05B conversation command must be a separate explicit contract.

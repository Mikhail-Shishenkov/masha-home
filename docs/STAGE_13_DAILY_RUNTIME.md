# Stage 13 — Daily Runtime Hardening

Status: **IMPLEMENTED**

## Purpose

Stage 13 turns the separate MEM-12 capabilities into one local, explainable
daily heartbeat. It does not add a new memory system, personality layer,
scheduler authority, external channel or agent permission.

```text
Daily Runtime
→ recover deterministic temporal events
→ evaluate Commitment reminders first
→ reserve at most one contact per heartbeat
→ evaluate CHECK_IN only when no higher-priority contact is active
→ formulate through the active local ModelProfile
→ persist existing delivery state
→ write a bounded operating receipt
```

## Distinctive contracts

### One heartbeat, one contact

A cycle may formulate at most one new proactive message. Additional eligible
events remain pending with deterministic reason `cycle_delivery_limit`. If a
previous proactive message is still waiting for the user, new contacts are
suppressed with `awaiting_user_response`.

This is an attention-respect rule owned by the application. The LLM cannot
override it.

### Explainable heartbeat

Every manual or background cycle may be recorded in
`local-data/runtime/daily-runtime-receipts.json`. The journal is capped at 100
receipts and contains event kind, technical event identity, decision, state,
reason, timestamps and active profile. It deliberately excludes generated
message text, conversation content and Memory payloads.

Receipts are operating diagnostics. They are not long-term Memory,
conversation history or Identity.

### Local calendar semantics

Daily delivery limits use the Moscow UTC+03:00 calendar boundary established
by MEM-11. Internal timestamps remain UTC.

## Runtime health

`python -m backend.runtime.cli status` performs read-only checks for:

- Identity/Memory version compatibility;
- SQLite `quick_check`;
- readable conversation history;
- active local model/provider availability;
- proactive policy validity;
- latest local SQLite backup integrity;
- daemon state.

A missing backup or stopped daemon is a warning, not silent repair. Health does
not change Identity, Memory, Commitments, history or policy.

## Human entry point

```powershell
.\masha.ps1 chat
.\masha.ps1 status
.\masha.ps1 run
.\masha.ps1 receipts
.\masha.ps1 background
.\masha.ps1 stop
```

There is no OS autostart. Background mode remains an explicit local user
choice. No external notification channel is connected.

## Preserved boundaries

- Identity remains in `IdentityKernel`.
- Long-term Memory remains in SQLite and changes only through existing flows.
- Commitment state is not changed by delivery or acknowledgement.
- Temporal truth remains deterministic and independent of the LLM.
- Model selection remains manual; no fallback exists.
- Receipts and health are operating infrastructure, not personality.
- No generated message can change a decision reason.

## Known limitations

- Delivery is local; there is no system notification, mobile push or remote channel.
- The PowerShell launcher does not install autostart or a Windows Service.
- Backup health verifies existing backup integrity but does not create or rotate backups automatically.
- Text safety still relies on bounded formulation contracts; no new response validator is introduced.

# W5.2 — Whole-Home Recovery Core

W5.2 restores a previously verified W5.1 `.mashabackup` as a **replacement**, never as a
merge. It is an offline operation: it does not use Conversation, an LLM, renderer JavaScript, or
the active `MashaApplication`.

Before mutation recovery requires both the desktop Home runtime lease and ProactiveDaemon to be
positively stopped. Running or unknown PID liveness fails closed; recovery never kills a process.
The desktop host owns `local-data/runtime/home-runtime.lock` for its lifetime. A stale lease is
reclaimed only after the PID is known dead.

`preview_restore` authenticates and validates the backup, returning only safe metadata. Apply
requires the previewed `backup_id` again and re-verifies/materializes the encrypted bundle before
mutation. Only W5.1 format `1.0` and application-data version `0.1` are supported.

`REPLACE` first produces and verifies an encrypted safety checkpoint in
`local-data/recovery/checkpoints/`. `FRESH` is only allowed where no prior Memory, conversation
history, or installed local skill state exists. Static components replace their exact owned target;
an optional component absent from the backup removes the old owned file. Installed local skills are
replaced as one owned boundary. Unknown `local-data` files and bundled `skills/` are untouched.

Recovery is journaled in `local-data/recovery/state.json` with secret-free phases: previewed,
checkpointed, applying, verifying, hold, rolling back, rolled back, released, and blocked. A normal
composition refuses to boot through dangerous incomplete states. If apply fails in REPLACE, the
verified checkpoint is materialized and applied as compensating rollback. A failed rollback leaves
`BLOCKED`; no second destructive action is attempted automatically.

Excluded actionable files (proposal/install/local-document and daemon transient state) are moved to
the recovery quarantine before apply where present. Rollback restores them. A successful restore
enters **Recovery Hold**: normal local Home inspection/conversation remains possible, but proactive
runtime is suppressed. `release_recovery_hold` validates current structure, marks the journal
released, then removes retained checkpoint/quarantine; it never starts the daemon.

Secrets remain excluded. No passphrase, encryption key, raw backup body, or secret value enters the
journal. The minimal offline CLI reads the passphrase only with `getpass`:

`python -m backend.backup.recovery_cli --project-root <home> preview <backup>`

The destructive recovery drill is isolated under pytest `tmp_path`: it creates state A, backs it up,
mutates to state B, restores A, verifies removal of B-owned data, and confirms Recovery Hold.

Current limitation: W5.2 does not offer a recovery UI or automatic restart, does not implement
cross-version migrations, and intentionally defers the optional manual rollback-from-HOLD command.

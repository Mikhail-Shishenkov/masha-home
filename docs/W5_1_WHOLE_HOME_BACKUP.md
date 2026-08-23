# W5.1 — Whole-Home Backup Core

W5.1 protects the durable Home state against loss of the computer. It creates a portable,
encrypted `.mashabackup` and verifies it before reporting success. It does **not** restore
anything; restore preview, replacement, rollback, and Recovery Hold are W5.2 work.

## Inventory

The backup uses a typed allowlist, never a recursive copy of `local-data/`.

Required components are the Identity manifest, the Memory SQLite database, and conversation
history. When present, it also includes the current Home configuration (timezone, model,
proactive, safety, internet, autonomy, and skill registry settings), bounded runtime receipts
(external observation, document read, daily runtime, and agent run history), and verified local
skill packages under `local-data/skills/`.

Installed skills are copied only after their existing registry digest verifies. Packages are not
imported or executed, and symlinks are rejected. Bundled repository skills are release assets and
are not duplicated.

Explicitly excluded: `.env` files, secrets/tokens, `local-data/secrets/`, arbitrary unknown local
data, pending install/action proposals, W4.1 local-document staging, model binaries, source code,
virtual environments, scene assets, logs, caches, benchmarks, temporary files, and OS metadata.
The encrypted manifest records `secrets_included: false` and `recovery_hold_required: true`.

## Format and cryptography

The `.mashabackup` envelope has a minimal unauthenticated-contents-free header: magic/version,
Scrypt parameters and salt, and AES-GCM nonce. It reveals no Home filenames, Identity, component
inventory, or conversations. The header is AES-GCM associated data, so changing it invalidates
decryption.

The encrypted payload is a POSIX-name tar containing `manifest.json` and allowlisted components.
The manifest is typed/versioned and includes a backup id/time, compatibility metadata, component
IDs/logical paths, sizes, SHA-256 hashes, `recovery_hold_required: true`, and
`snapshot_requires_quiescence: true`. A component `format_version` is present only when its own
contract declares one; W5.1 does not infer a schema version from a `.json` suffix.

Passphrases use Scrypt with random 16-byte salt, `n=32768`, `r=8`, `p=1`, deriving a 32-byte key.
Payload encryption is AES-256-GCM with a fresh random 12-byte nonce. The passphrase and key are
never persisted, logged, exposed to UI/model context, or placed in the manifest.

Creation writes the tar and encrypts it in chunks; it does not assemble the whole backup in RAM.
A bounded plaintext tar and verification tar live in OS temporary storage and are cleaned in normal
success/failure paths. A machine crash may leave temporary plaintext until OS/application cleanup;
this is the remaining W5.1 local-staging limitation.

## Snapshot and verification

Memory is snapshotted via SQLite `Connection.backup()` into a distinct temporary database, then
checked with `PRAGMA quick_check`; WAL/SHM sidecars are never archive components. Non-SQLite files
are read only from their explicit paths and their snapshot size/SHA-256 are recorded.

The v1 encrypted envelope is bounded to 2 GiB. The caller supplies the destination—W5.1 chooses no default folder. Existing files are never
overwritten. A unique partial file is written beside the final destination, then reopened and fully
verified before atomic replacement. Verification authenticates/decrypts, validates header and
manifest, rejects unsafe/duplicate/undeclared tar entries, rechecks every component hash/size,
parses Identity, validates the SQLite snapshot and its exact identity-version compatibility,
validates the required conversation history, and rechecks installed skill registry digests against
the archived packages. It never applies state to the live Home.

Keep at least one verified backup **off the Home computer**. W5.1 guarantees a consistent SQLite
snapshot and atomic per-file snapshots, but a whole-Home snapshot is fully consistent only after
the caller has quiesced Home writes. W5.2 owns quiesce/current-turn completion, pausing writers,
restart/bootstrap, restore/rollback, and Recovery Hold. W5.1 has no scheduling, cloud upload,
secret backup, or restore workflow.

# UI-05A — Desktop Shell

Status: **UI-05B IN PROGRESS**

UI-05A.1 introduces a local PySide6 + Qt WebEngine host. It owns the desktop window,
the hardened WebEngine profile and a closed `masha://home/` frontend origin. It does not
own Presentation Runtime, CompositionResolver, Identity, Memory, SQLite, ModelRouter or
Ollama.

The renderer uses the approved canonical full-scene asset and has no QWebChannel commands,
browser network access or production conversation surface. UI-05A.2 adds a one-way,
application-owned `HomeSnapshotView`: status, active profile, canonical visual descriptor,
`HomePresentationModel` and a deterministic `CompositionPlan` are assembled inside
`MashaApplication` and injected once from the local host to the renderer. JavaScript cannot
invoke the application or mutate state. UI-05B will add one real conversation turn through a
separate, closed command contract.

## UI-05B local conversation slice

The production shell now registers exactly one closed `mashaHome` Qt WebChannel object. Its
allowlisted methods are `loadInitialState()`, `startNewConversation()`, and `submitMessage(content)`. JavaScript receives
JSON events only; it cannot obtain `MashaApplication`, a repository, a provider, a filesystem
path, or a generic invocation handle.

`submitMessage` accepts bounded non-empty text, uses the application-owned fixed local project
identifier, and is executed by one local worker. The conversation surface permits only one
in-flight turn: Send is disabled until a controlled result returns. The renderer receives the
existing `ConversationTurnResult` and never fabricates an assistant reply. The latest real
conversation is loaded through the application boundary at startup, bounded to 16 messages.

The Home presentation session maps the known conversation lifecycle deterministically:
`opened → listening → thinking → speaking` (or local model unavailable). It is renderer-neutral
and does not mutate Identity, Memory, Commitment, Temporal state, model selection, or SQLite
schema. The only additional bundled origin is Qt's local `qrc:///qtwebchannel/qwebchannel.js`
client; browser network access remains disabled.

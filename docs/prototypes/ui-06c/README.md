# UI-06C — Capability Visual Workshop

Disposable visual workshop for ten implemented Masha Home capabilities. It is
not a production frontend and has no backend, persistence, local-model or
personal-data connection.

Open `index.html` directly. Use the bottom scene strip or the left/right arrow
keys. Surface actions only demonstrate presentation receipts; they do not
perform domain operations.

The workshop deliberately keeps one canonical full-scene room and one visual
identity. Capability differences are expressed through spatial origin, light,
surface structure and lifecycle instead of changing Masha's pose on every
state transition.

Each of the ten moments can now be evaluated through the same grammar:
`appeared → focused → waiting → resolved/dismissed`. These transitions are
presentation-only and deliberately disconnected from backend operations.

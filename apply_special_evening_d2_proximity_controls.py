from __future__ import annotations

from pathlib import Path

ROOT = Path.cwd()
STAGED: dict[Path, str] = {}


class PatchError(RuntimeError):
    pass


def read(path: str) -> str:
    file_path = ROOT / path
    if file_path not in STAGED:
        if not file_path.exists():
            raise PatchError(f"{path}: file not found")
        STAGED[file_path] = file_path.read_text(encoding="utf-8")
    return STAGED[file_path]


def stage(path: str, text: str) -> None:
    STAGED[ROOT / path] = text


def replace_once(path: str, old: str, new: str, label: str) -> None:
    text = read(path)
    count = text.count(old)
    if count != 1:
        raise PatchError(f"{path}: {label}: expected 1 match, found {count}")
    stage(path, text.replace(old, new, 1))
    print(f"[CHECK] {path}: {label}")


def insert_after(path: str, anchor: str, addition: str, label: str) -> None:
    text = read(path)
    count = text.count(anchor)
    if count != 1:
        raise PatchError(f"{path}: {label}: expected 1 anchor, found {count}")
    stage(path, text.replace(anchor, anchor + addition, 1))
    print(f"[CHECK] {path}: {label}")


def insert_before(path: str, anchor: str, addition: str, label: str) -> None:
    text = read(path)
    count = text.count(anchor)
    if count != 1:
        raise PatchError(f"{path}: {label}: expected 1 anchor, found {count}")
    stage(path, text.replace(anchor, addition + anchor, 1))
    print(f"[CHECK] {path}: {label}")


def append_once(path: str, marker: str, block: str, label: str) -> None:
    text = read(path)
    if marker in text:
        raise PatchError(f"{path}: {label}: already present")
    if not text.endswith("\n"):
        text += "\n"
    stage(path, text + "\n" + block.strip() + "\n")
    print(f"[CHECK] {path}: {label}")


try:
    replace_once(
        "backend/presentation/__init__.py",
        '''    HomeMoment,
    HomePresentationModel,
''',
        '''    HomeMoment,
    HomeProximity,
    HomePresentationModel,
''',
        "export HomeProximity import",
    )

    replace_once(
        "backend/presentation/__init__.py",
        '''    "HomeMoment",
    "HomePresentationModel",
''',
        '''    "HomeMoment",
    "HomeProximity",
    "HomePresentationModel",
''',
        "export HomeProximity in __all__",
    )

    replace_once(
        "backend/ui/conversation_bridge.py",
        '''from backend.presentation import HomeMoment
''',
        '''from backend.presentation import HomeMoment, HomeProximity
''',
        "import HomeProximity in bridge",
    )

    insert_before(
        "backend/ui/conversation_bridge.py",
        '''    @Slot()
    def leaveSpecialEvening(self):  # noqa: N802
''',
        '''    @Slot()
    def advanceSpecialEveningProximity(self):  # noqa: N802
        if self._presentation_session is None:
            return
        current = self._session_snapshot("special_evening_proximity_advance")
        if current.presentation.home_moment is not HomeMoment.SPECIAL_EVENING:
            return

        proximity = current.presentation.home_proximity
        target = (
            HomeProximity.CLOSE
            if proximity is HomeProximity.WIDE
            else HomeProximity.NEAR
            if proximity is HomeProximity.CLOSE
            else HomeProximity.CLOSE
        )

        snapshot = self._presentation_session.set_special_proximity(target)
        if snapshot is None:
            return

        self._emit(
            {
                "kind": "special_evening_proximity_changed",
                "snapshot": snapshot.model_dump(mode="json"),
                "proximity": snapshot.presentation.home_proximity.value,
            }
        )

''',
        "add advance proximity slot",
    )

    insert_after(
        "backend/ui/conversation_bridge.py",
        '''                "active_continuity_thread": self._active_continuity_payload(),
''',
        '''                "special_evening_controls": self._special_evening_controls_payload(),
''',
        "publish controls payload",
    )

    insert_after(
        "backend/ui/conversation_bridge.py",
        '''                "kind": "special_evening_entered",
                "snapshot": snapshot.model_dump(mode="json"),
''',
        '''                "controls": self._special_evening_controls_payload(),
''',
        "publish controls on enter",
    )

    insert_after(
        "backend/ui/conversation_bridge.py",
        '''                "kind": "special_evening_left",
                "snapshot": snapshot.model_dump(mode="json"),
''',
        '''                "controls": self._special_evening_controls_payload(),
''',
        "publish controls on leave",
    )

    insert_after(
        "backend/ui/conversation_bridge.py",
        '''    def _active_continuity_payload(self) -> dict | None:
        if self._application is None or self._conversation_id is None:
            return None
        thread = self._application.active_continuity_thread(
            conversation_id=self._conversation_id,
        )
        return (
            None
            if thread is None
            else thread.model_dump(mode="json")
        )

''',
        '''    def _special_evening_controls_payload(self) -> dict:
        snapshot = self._session_snapshot("special_evening_controls")
        moment = snapshot.presentation.home_moment
        proximity = snapshot.presentation.home_proximity
        enabled = moment is HomeMoment.SPECIAL_EVENING

        if not enabled:
            return {
                "enabled": False,
                "proximity": proximity.value,
                "label": "",
            }

        if proximity is HomeProximity.WIDE:
            label = "Ближе"
        elif proximity is HomeProximity.CLOSE:
            label = "Ещё ближе"
        else:
            label = "Чуть дальше"

        return {
            "enabled": True,
            "proximity": proximity.value,
            "label": label,
        }

''',
        "add controls helper",
    )

    insert_after(
        "frontend/index.html",
        '''  >Вдвоём</button>

''',
        '''  <button
    class="special-proximity-toggle"
    id="special-proximity-toggle"
    type="button"
    hidden
    disabled
  >Ближе</button>

''',
        "add special proximity button",
    )

    insert_after(
        "frontend/renderer/app.js",
        '''const historyInboxReject = document.getElementById("history-inbox-reject");
''',
        '''const specialProximityToggle = document.getElementById("special-proximity-toggle");
''',
        "bind special proximity button",
    )

    insert_after(
        "frontend/renderer/app.js",
        '''let activeContinuityThread = null;
''',
        '''let specialEveningControls = { enabled: false, proximity: "wide", label: "" };
''',
        "add control state",
    )

    insert_before(
        "frontend/renderer/app.js",
        '''function renderContinuity(view) {
''',
        '''function renderSpecialEveningControls(controls, snapshot) {
  specialEveningControls = controls || { enabled: false, proximity: "wide", label: "" };
  const homeMoment = snapshot?.presentation?.home_moment || document.documentElement.dataset.homeMoment || "ordinary";
  const active = specialEveningControls.enabled && homeMoment === "special_evening";

  specialProximityToggle.hidden = !active;
  specialProximityToggle.disabled = !active || inFlight;
  specialProximityToggle.textContent = specialEveningControls.label || "Ближе";
  specialProximityToggle.dataset.proximity = specialEveningControls.proximity || "wide";
}

''',
        "add controls renderer",
    )

    insert_after(
        "frontend/renderer/app.js",
        '''    renderMemoryCandidate(payload.memory_candidate);
    renderActiveContinuityThread(payload.active_continuity_thread);
''',
        '''    renderSpecialEveningControls(payload.special_evening_controls, payload.snapshot);
''',
        "restore controls on initial load",
    )

    insert_after(
        "frontend/renderer/app.js",
        '''    renderPendingConfirmation(payload.pending_confirmation);
    renderActiveContinuityThread(payload.active_continuity_thread);
''',
        '''    renderSpecialEveningControls(payload.special_evening_controls, payload.snapshot);
''',
        "restore controls on conversation open",
    )

    insert_after(
        "frontend/renderer/app.js",
        '''    specialEveningToggle.setAttribute("aria-pressed", "true");
''',
        '''    renderSpecialEveningControls(payload.controls, payload.snapshot);
''',
        "render controls on enter",
    )

    insert_after(
        "frontend/renderer/app.js",
        '''    specialEveningToggle.setAttribute("aria-pressed", "false");
''',
        '''    renderSpecialEveningControls(payload.controls, payload.snapshot);
''',
        "render controls on leave",
    )

    insert_after(
        "frontend/renderer/app.js",
        '''  if (payload.kind === "continuity_thread_cleared") {
    applySnapshot(payload.snapshot);
    renderActiveContinuityThread(null);
    surfaceStatus.textContent = "";
    input.focus();
    return;
  }
''',
        '''
  if (payload.kind === "special_evening_proximity_changed") {
    applySnapshot(payload.snapshot);
    renderSpecialEveningControls(
      {
        enabled: true,
        proximity: payload.proximity,
        label:
          payload.proximity === "wide"
            ? "Ближе"
            : payload.proximity === "close"
            ? "Ещё ближе"
            : "Чуть дальше",
      },
      payload.snapshot
    );
    input.focus();
    return;
  }
''',
        "handle proximity change event",
    )

    insert_after(
        "frontend/renderer/app.js",
        '''specialEveningToggle.addEventListener("click", () => {
  if (!ready || inFlight || specialEveningToggle.disabled) return;
  if (document.documentElement.dataset.homeMoment === "special_evening") {
    bridge.leaveSpecialEvening();
    return;
  }
  bridge.enterSpecialEvening();
});
''',
        '''
specialProximityToggle.addEventListener("click", () => {
  if (!ready || inFlight || specialProximityToggle.disabled) return;
  bridge.advanceSpecialEveningProximity();
});
''',
        "wire proximity button",
    )

    insert_after(
        "frontend/renderer/app.js",
        '''  document.documentElement.dataset.homeMoment = presentation.home_moment || "ordinary";
''',
        '''  document.documentElement.dataset.homeProximity = presentation.home_proximity || "wide";
''',
        "publish proximity dataset",
    )

    append_once(
        "frontend/styles/home.css",
        "/* Special Evening 2.0 — proximity controls */",
        '''
/* Special Evening 2.0 — proximity controls */

.special-proximity-toggle {
  border: 1px solid rgba(226, 188, 126, .34);
  background: rgba(126, 81, 41, .18);
  color: rgba(251, 238, 216, .9);
  border-radius: 999px;
  padding: 8px 15px;
  font: 500 12px/1 system-ui, sans-serif;
  letter-spacing: .01em;
  cursor: pointer;
  transition: border-color .16s ease, background-color .16s ease, opacity .16s ease;
}

.special-proximity-toggle:hover:not(:disabled) {
  border-color: rgba(236, 201, 144, .54);
  background: rgba(146, 94, 45, .25);
}

.special-proximity-toggle:disabled {
  opacity: .45;
  cursor: default;
}

.special-proximity-toggle[data-proximity="close"] {
  background: rgba(138, 86, 47, .22);
}

.special-proximity-toggle[data-proximity="near"] {
  border-color: rgba(235, 197, 139, .52);
  background: rgba(157, 94, 45, .28);
}
''',
        "add button styles",
    )

    replace_once(
        "frontend/scenes/scene-map.js",
        '''  const presence = presentation.presence || {};
  const activity = presence.activity;
  const attention = presence.attention;
  const expression = presence.expression?.code;
  const specialEvening =
  period === "evening"
  && presentation.home_moment === "special_evening";

if (specialEvening) {
  switch (activity) {
    case "speaking":
      return scenes.specialClose;

    case "listening":
      return chooseVariant(
        presentation,
        scenes.specialClose,
        scenes.specialMug
      );

    case "waiting":
      return scenes.specialClose;

    case "processing":
      return scenes.specialThoughtful;

    case "idle":
      if (presence.ambient === "quiet") {
        return scenes.specialQuiet;
      }
      return scenes.specialEvening;

    default:
      break;
  }
}
''',
        '''  const presence = presentation.presence || {};
  const activity = presence.activity;
  const attention = presence.attention;
  const expression = presence.expression?.code;
  const specialEvening =
  period === "evening"
  && presentation.home_moment === "special_evening";
  const specialProximity = presentation.home_proximity || "wide";

if (specialEvening) {
  if (["skeptical", "serious"].includes(expression)) {
    return scenes.firmDisagreement;
  }

  if (specialProximity === "near") {
    switch (activity) {
      case "processing":
        return scenes.specialThoughtful;
      case "idle":
        return presence.ambient === "quiet"
          ? scenes.specialQuiet
          : scenes.specialMug;
      default:
        return chooseVariant(
          presentation,
          scenes.specialMug,
          scenes.specialQuiet
        );
    }
  }

  if (specialProximity === "close") {
    switch (activity) {
      case "processing":
        return scenes.specialThoughtful;
      case "idle":
        return presence.ambient === "quiet"
          ? scenes.specialMug
          : scenes.specialClose;
      default:
        return chooseVariant(
          presentation,
          scenes.specialClose,
          scenes.specialMug
        );
    }
  }

  switch (activity) {
    case "processing":
      return scenes.specialThoughtful;
    case "idle":
      return presence.ambient === "quiet"
        ? scenes.specialQuiet
        : scenes.specialEvening;
    default:
      return scenes.specialEvening;
  }
}
''',
        "make special evening proximity-driven",
    )

    append_once(
        "frontend/renderer/living-threads.test.cjs",
        'assert.match(css, /\.thread-context/);',
        '''
assert.match(html, /id="special-proximity-toggle"/);
assert.match(app, /renderSpecialEveningControls/);
assert.match(app, /advanceSpecialEveningProximity/);
assert.match(app, /dataset\.homeProximity/);
''',
        "extend renderer smoke test",
    )

    append_once(
        "tests/test_presentation_runtime.py",
        "def test_special_evening_proximity_roundtrip_session_boundary():",
        '''
def test_special_evening_proximity_roundtrip_session_boundary():
    from backend.application.home_snapshot import HomeSnapshotService
    from backend.presentation import HomeProximity

    snapshot_service = HomeSnapshotService(
        status=MashaStatusView(
            active_model=ModelProfileView(
                profile_id="local",
                label="Local",
                available=True,
                availability_code=ModelAvailabilityCode.READY,
            ),
            visual_assets=VisualAssetView(
                tier="tier_1_2d",
                supports_animation=False,
                supports_moments=True,
            ),
            observed_at=NOW,
        )
    )
    session = snapshot_service.open_session()
    session.opened()

    assert session.enter_special_evening() is None

    night_service = HomeSnapshotService(
        status=MashaStatusView(
            active_model=ModelProfileView(
                profile_id="local",
                label="Local",
                available=True,
                availability_code=ModelAvailabilityCode.READY,
            ),
            visual_assets=VisualAssetView(
                tier="tier_1_2d",
                supports_animation=False,
                supports_moments=True,
            ),
            observed_at=NOW,
        ),
        clock=lambda: datetime(2026, 8, 11, 20, 0, tzinfo=timezone.utc),
    )
    evening = night_service.open_session()
    evening.opened()
    entered = evening.enter_special_evening()
    assert entered is not None
    changed = evening.set_special_proximity(HomeProximity.CLOSE)
    assert changed is not None
    assert changed.presentation.home_proximity is HomeProximity.CLOSE
''',
        "add session test",
    )

    for file_path, text in STAGED.items():
        if file_path.suffix == ".py":
            compile(text, str(file_path), "exec")

except (PatchError, SyntaxError) as exc:
    print()
    print(f"[STOP] {exc}")
    print("No files were written.")
    raise SystemExit(1)

for file_path, text in STAGED.items():
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(text, encoding="utf-8")
    print(f"[WRITE] {file_path.relative_to(ROOT)}")

print()
print("Special Evening 2.0 D2 applied: proximity controls.")
print("Review: git diff")
print(r"Python: .\.venv\Scripts\python.exe -m pytest tests/test_presentation_runtime.py -q")
print(r"Frontend: node frontend\renderer\living-threads.test.cjs")

from __future__ import annotations

from pathlib import Path

ROOT = Path.cwd()
STAGED: dict[Path, str] = {}


class PatchError(RuntimeError):
    pass


def read(path: str) -> str:
    p = ROOT / path
    if p not in STAGED:
        if not p.exists():
            raise PatchError(f"{path}: file not found")
        STAGED[p] = p.read_text(encoding="utf-8-sig")
    return STAGED[p]


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


try:
    if "class HomeProximity(str, Enum):" not in read("backend/presentation/models.py"):
        raise PatchError("D1 proximity foundation is missing")
    if "def set_special_proximity(" not in read("backend/application/home_snapshot.py"):
        raise PatchError("HomePresentationSession.set_special_proximity is missing")

    replace_once('frontend/renderer/app.js', '\ndocument.documentElement.dataset.homeMoment =\n  homeMoment;\n\nspecialEveningToggle.hidden =\n  !specialEveningAvailable;\n', '\ndocument.documentElement.dataset.homeMoment =\n  homeMoment;\n\nconst homeProximity =\n  presentation.home_proximity || "wide";\n\ndocument.documentElement.dataset.homeProximity =\n  homeProximity;\n\nspecialEveningToggle.hidden =\n  !specialEveningAvailable;\n\nspecialProximityToggle.hidden =\n  !specialEveningActive;\n\nspecialProximityToggle.dataset.proximity =\n  homeProximity;\n\nspecialProximityToggle.textContent =\n  homeProximity === "wide"\n    ? "Ближе"\n    : homeProximity === "close"\n    ? "Ещё ближе"\n    : "Чуть дальше";\n', 'render proximity from Presentation')

    replace_once('frontend/scenes/scene-map.js', '\n  const presence = presentation.presence || {};\n  const activity = presence.activity;\n  const attention = presence.attention;\n  const expression = presence.expression?.code;\n  const specialEvening =\n  period === "evening"\n  && presentation.home_moment === "special_evening";\n\nif (specialEvening) {\n  switch (activity) {\n    case "speaking":\n      return scenes.specialClose;\n\n    case "listening":\n      return chooseVariant(\n        presentation,\n        scenes.specialClose,\n        scenes.specialMug\n      );\n\n    case "waiting":\n      return scenes.specialClose;\n\n    case "processing":\n      return scenes.specialThoughtful;\n\n    case "idle":\n      if (presence.ambient === "quiet") {\n        return scenes.specialQuiet;\n      }\n      return scenes.specialEvening;\n\n    default:\n      break;\n  }\n}\n', '\n  const presence = presentation.presence || {};\n  const activity = presence.activity;\n  const attention = presence.attention;\n  const expression = presence.expression?.code;\n  const specialEvening =\n  period === "evening"\n  && presentation.home_moment === "special_evening";\n  const specialProximity =\n    presentation.home_proximity || "wide";\n\nif (specialEvening) {\n  if (["skeptical", "serious"].includes(expression)) {\n    return scenes.firmDisagreement;\n  }\n\n  if (specialProximity === "near") {\n    if (activity === "processing") {\n      return scenes.specialThoughtful;\n    }\n\n    if (activity === "idle" && presence.ambient === "quiet") {\n      return scenes.specialQuiet;\n    }\n\n    return chooseVariant(\n      presentation,\n      scenes.specialMug,\n      scenes.specialQuiet\n    );\n  }\n\n  if (specialProximity === "close") {\n    if (activity === "processing") {\n      return scenes.specialThoughtful;\n    }\n\n    if (activity === "idle" && presence.ambient === "quiet") {\n      return scenes.specialMug;\n    }\n\n    return chooseVariant(\n      presentation,\n      scenes.specialClose,\n      scenes.specialMug\n    );\n  }\n\n  if (activity === "processing") {\n    return scenes.specialThoughtful;\n  }\n\n  if (activity === "idle" && presence.ambient === "quiet") {\n    return scenes.specialQuiet;\n  }\n\n  return scenes.specialEvening;\n}\n', 'make Special Evening proximity-first')

    insert_after('backend/application/home_snapshot.py', '\ndef home_moment(self) -> HomeMoment:\n    # UI-only authored moment; never persisted as domain memory.\n    return self._runtime.model.home_moment\n\n', '\n@property\ndef home_proximity(self) -> HomeProximity:\n    # UI-only authored closeness; never persisted as domain memory.\n    return self._runtime.model.home_proximity\n\n', 'expose current Home proximity')

    insert_after('backend/ui/conversation_bridge.py', '\nfrom backend.application.human_information import (\n    HumanSearchRequest,\n    HumanSearchScope,\n    RecallMode,\n)\n', '\nfrom backend.presentation import HomeProximity\n', 'import HomeProximity')

    insert_after('frontend/index.html', '\n>Вдвоём</button>\n\n', '\n<button\n  class="special-proximity-toggle"\n  id="special-proximity-toggle"\n  type="button"\n  hidden\n  disabled\n>Ближе</button>\n\n', 'add proximity button')

    insert_after('frontend/renderer/app.js', '\nconst specialEveningToggle = document.getElementById("special-evening-toggle");\n', '\nconst specialProximityToggle =\n  document.getElementById("special-proximity-toggle");\n', 'bind proximity button')

    insert_after('frontend/renderer/app.js', '\nspecialEveningToggle.disabled = !enabled || waiting;\n', '\nspecialProximityToggle.disabled =\n  !enabled || waiting || Boolean(pendingConfirmation);\n', 'disable proximity while busy')

    insert_after('frontend/renderer/app.js', '\nspecialEveningToggle.addEventListener("click", () => {\n  if (!ready || inFlight || pendingConfirmation) {\n    return;\n  }\n\n  const active =\n    document.documentElement.dataset.homeMoment\n    === "special_evening";\n\n  bridge.setSpecialEvening(!active);\n});\n', '\nspecialProximityToggle.addEventListener("click", () => {\n  if (\n    !ready\n    || inFlight\n    || pendingConfirmation\n    || specialProximityToggle.hidden\n  ) {\n    return;\n  }\n\n  bridge.advanceSpecialEveningProximity();\n});\n', 'wire proximity control')

    insert_before('backend/ui/conversation_bridge.py', '\n@Slot(int)\ndef settleAssistantPresence(\n', '\n@Slot()\ndef advanceSpecialEveningProximity(self):  # noqa: N802\n    """Move one authored step closer/farther inside Special Evening."""\n    if self._application is None or self._session is None:\n        self._emit({"kind": "home_unavailable"})\n        return\n\n    if self._turn_in_flight:\n        return\n\n    current = self._session.home_proximity\n\n    if current is HomeProximity.WIDE:\n        target = HomeProximity.CLOSE\n    elif current is HomeProximity.CLOSE:\n        target = HomeProximity.NEAR\n    else:\n        target = HomeProximity.CLOSE\n\n    snapshot = self._session_snapshot(\n        "set_special_proximity",\n        proximity=target,\n    )\n\n    if snapshot is None:\n        self._emit({\n            "kind": "special_evening_unavailable",\n        })\n        return\n\n    self._emit({\n        "kind": "special_evening_changed",\n        "snapshot": snapshot.model_dump(mode="json"),\n    })\n\n', 'add bounded proximity slot')

    css_path = "frontend/styles/home.css"
    css = read(css_path)
    marker = "/* Special Evening 2.0 - proximity */"
    if marker in css:
        raise PatchError("D2 proximity styles already present")
    stage(css_path, css + '\n/* Special Evening 2.0 - proximity */\n\n.special-proximity-toggle {\n  padding: 5px 11px;\n  border: 1px solid rgba(232, 184, 116, .24);\n  border-radius: 999px;\n  background: rgba(117, 69, 29, .11);\n  color: rgba(255, 222, 174, .78);\n  letter-spacing: .035em;\n  opacity: .9;\n  transition:\n    color 220ms ease,\n    border-color 220ms ease,\n    background 220ms ease,\n    box-shadow 280ms ease,\n    transform 220ms var(--ease-home);\n}\n\n.special-proximity-toggle:hover:not(:disabled) {\n  color: #fff0d3;\n  border-color: rgba(248, 205, 143, .6);\n  background: rgba(133, 78, 32, .24);\n  box-shadow: 0 0 18px rgba(205, 134, 61, .1);\n  transform: translateY(-1px);\n}\n\n.special-proximity-toggle[data-proximity="near"] {\n  color: #ffe7c1;\n  border-color: rgba(248, 205, 143, .48);\n  background: rgba(133, 78, 32, .28);\n}\n\n.special-proximity-toggle:disabled {\n  opacity: .38;\n  transform: none;\n  box-shadow: none;\n}\n')
    print("[CHECK] frontend/styles/home.css: add proximity styles")

    new_path = ROOT / 'frontend/renderer/special-evening-proximity.test.cjs'
    if new_path.exists():
        raise PatchError('frontend/renderer/special-evening-proximity.test.cjs: already exists')
    STAGED[new_path] = '"use strict";\n\nconst assert = require("node:assert/strict");\nconst fs = require("node:fs");\nconst path = require("node:path");\n\nconst root = path.join(__dirname, "..");\nconst app = fs.readFileSync(path.join(__dirname, "app.js"), "utf8");\nconst html = fs.readFileSync(path.join(root, "index.html"), "utf8");\nconst css = fs.readFileSync(path.join(root, "styles", "home.css"), "utf8");\nconst scenes = fs.readFileSync(path.join(root, "scenes", "scene-map.js"), "utf8");\n\nassert.match(html, /id="special-proximity-toggle"/);\nassert.match(app, /advanceSpecialEveningProximity/);\nassert.match(app, /dataset\\.homeProximity/);\nassert.match(app, /Ещё ближе/);\nassert.match(app, /Чуть дальше/);\n\nassert.match(scenes, /presentation\\.home_proximity/);\nassert.match(scenes, /specialProximity === "close"/);\nassert.match(scenes, /specialProximity === "near"/);\n\nconst specialAt = scenes.indexOf("if (specialEvening)");\nconst boundaryAt = scenes.indexOf(\n  \'if (["skeptical", "serious"].includes(expression))\',\n  specialAt\n);\nconst nearAt = scenes.indexOf(\'if (specialProximity === "near")\', specialAt);\n\nassert.ok(specialAt >= 0);\nassert.ok(boundaryAt > specialAt && boundaryAt < nearAt);\n\nassert.match(css, /Special Evening 2\\.0 - proximity/);\n\nconsole.log("special evening proximity tests passed");\n'
    print("[CHECK] frontend/renderer/special-evening-proximity.test.cjs: create")

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
print("D2 applied: explicit Special Evening proximity controls.")
print("Review: git diff")
print()
print(
    r"Python: .\.venv\Scripts\python.exe -m pytest "
    r"tests/test_presentation_runtime.py -q"
)
print(
    r"Frontend: node frontend\renderer\special-evening-proximity.test.cjs"
)

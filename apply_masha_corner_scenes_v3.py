from __future__ import annotations

import datetime as dt
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parent

SCENE_MAP = ROOT / "frontend" / "scenes" / "scene-map.js"
APP_JS = ROOT / "frontend" / "renderer" / "app.js"
CORNER_TEST = ROOT / "frontend" / "scenes" / "corner-scene.test.cjs"

DAY_CORNER = ROOT / "frontend" / "assets" / "presence" / "day" / "corner"
EVENING_CORNER = ROOT / "frontend" / "assets" / "presence" / "evening" / "corner"
ASSET_NAMES = ("corner_day.png", "corner_evening.png")


def read_preserving_bom(path: Path) -> tuple[str, bool, str]:
    data = path.read_bytes()
    had_bom = data.startswith(b"\xef\xbb\xbf")
    decoded = data.decode("utf-8-sig")
    newline = "\r\n" if "\r\n" in decoded else "\n"
    # Patch against one canonical newline style so Windows CRLF does not
    # invalidate exact code anchors.
    normalized = decoded.replace("\r\n", "\n")
    return normalized, had_bom, newline


def write_preserving_bom(path: Path, text: str, had_bom: bool, newline: str) -> None:
    rendered = text if newline == "\n" else text.replace("\n", "\r\n")
    data = rendered.encode("utf-8")
    if had_bom:
        data = b"\xef\xbb\xbf" + data
    path.write_bytes(data)


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected exactly one anchor, found {count}")
    return text.replace(old, new, 1)


def ensure_assets() -> None:
    expected = {
        "corner_day.png": DAY_CORNER / "corner_day.png",
        "corner_evening.png": EVENING_CORNER / "corner_evening.png",
    }

    missing = [path for path in expected.values() if not path.exists()]
    if missing:
        details = "\n".join(f"  {path}" for path in missing)
        raise FileNotFoundError(
            "Missing Corner asset(s). Expected:\n" + details
        )

    print("Corner assets: OK")
    for name, path in expected.items():
        print(f"  {name}: {path.relative_to(ROOT)}")


def backup_files() -> Path:
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    backup_dir = Path(tempfile.gettempdir()) / f"masha-home-corner-backup-{stamp}"
    backup_dir.mkdir(parents=True, exist_ok=True)
    for path in (SCENE_MAP, APP_JS):
        shutil.copy2(path, backup_dir / path.name)
    if CORNER_TEST.exists():
        shutil.copy2(CORNER_TEST, backup_dir / CORNER_TEST.name)
    print(f"Backup: {backup_dir}")
    return backup_dir


def patch_scene_map() -> None:
    text, bom, newline = read_preserving_bom(SCENE_MAP)

    if "const CORNER_SCENES = Object.freeze({" not in text:
        anchor = '  const SCENES = Object.freeze({ day: DAY_SCENES, evening: EVENING_SCENES });'
        addition = '''  const SCENES = Object.freeze({ day: DAY_SCENES, evening: EVENING_SCENES });

  // The Workbench ("Уголок") is a place, not a conversational activity.
  // It keeps Home's day/evening clock but owns its own visual assets.
  const CORNER_SCENES = Object.freeze({
    day: scene(
      "day",
      "corner",
      "assets/presence/day/corner/corner_day.png",
      "Маша в своём дневном рабочем уголке"
    ),
    evening: scene(
      "evening",
      "corner",
      "assets/presence/evening/corner/corner_evening.png",
      "Маша в своём вечернем рабочем уголке"
    ),
  });'''
        text = replace_once(text, anchor, addition, "scene-map registry")

    if "function resolveCornerScene(presentation)" not in text:
        anchor = "  function chooseVariant(presentation, primary, alternate) {"
        addition = '''  function resolveCornerScene(presentation) {
    const period = resolveHomePeriod(presentation);
    return CORNER_SCENES[period];
  }

  function chooseVariant(presentation, primary, alternate) {'''
        text = replace_once(text, anchor, addition, "corner resolver")

    old_preload = '''    Object.values(SCENES).flatMap((family) => Object.values(family)).forEach((item) => {
      const image = new Image();
      image.src = item.source;
    });'''
    new_preload = '''    [
      ...Object.values(SCENES).flatMap((family) => Object.values(family)),
      ...Object.values(CORNER_SCENES),
    ].forEach((item) => {
      const image = new Image();
      image.src = item.source;
    });'''
    if "...Object.values(CORNER_SCENES)" not in text:
        text = replace_once(text, old_preload, new_preload, "corner preload")

    old_api = (
        "  const api = Object.freeze({ SCENES, TRANSITION_POLICY, resolveHomePeriod, "
        "resolveScene, resolveTransition, preload });"
    )
    new_api = (
        "  const api = Object.freeze({ SCENES, CORNER_SCENES, TRANSITION_POLICY, "
        "resolveHomePeriod, resolveScene, resolveCornerScene, resolveTransition, preload });"
    )
    if "resolveCornerScene, resolveTransition" not in text:
        text = replace_once(text, old_api, new_api, "scene-map API")

    write_preserving_bom(SCENE_MAP, text, bom, newline)
    print("Patched frontend/scenes/scene-map.js")


def patch_app() -> None:
    text, bom, newline = read_preserving_bom(APP_JS)

    if "let cornerSceneActive = false;" not in text:
        anchor = 'let activeSceneId = "scene.home.idle";'
        addition = '''let activeSceneId = "scene.home.idle";
let lastPresentation = null;
let cornerSceneActive = false;'''
        text = replace_once(text, anchor, addition, "app scene state")

    if "function setCornerSceneActive(active)" not in text:
        anchor = "function applyScene(presentation) {"
        addition = '''function setCornerSceneActive(active) {
  const nextActive = Boolean(active);
  if (cornerSceneActive === nextActive) return;

  cornerSceneActive = nextActive;
  if (lastPresentation) applyScene(lastPresentation);
}

function applyScene(presentation) {'''
        text = replace_once(text, anchor, addition, "corner state helper")

    old_apply = '''function applyScene(presentation) {
  const next = window.MashaSceneMap.resolveScene(presentation);'''
    new_apply = '''function applyScene(presentation) {
  if (presentation) lastPresentation = presentation;
  const sourcePresentation = presentation || lastPresentation;
  const next = cornerSceneActive
    ? window.MashaSceneMap.resolveCornerScene(sourcePresentation)
    : window.MashaSceneMap.resolveScene(sourcePresentation);'''
    if "window.MashaSceneMap.resolveCornerScene(sourcePresentation)" not in text:
        text = replace_once(text, old_apply, new_apply, "corner-aware applyScene")

    transition_anchor = "function transitionToSurface(open, { preserveCandidate = false } = {}) {\n"
    transition_new = (
        "function transitionToSurface(open, { preserveCandidate = false } = {}) {\n"
        "  // Any non-Workbench surface returns to the normal Presence scene first.\n"
        "  setCornerSceneActive(false);\n"
    )
    if "Any non-Workbench surface returns to the normal Presence scene first." not in text:
        text = replace_once(text, transition_anchor, transition_new, "surface transition reset")

    return_anchor = "function returnToConversation() {\n"
    return_new = (
        "function returnToConversation() {\n"
        "  setCornerSceneActive(false);\n"
    )
    if "function returnToConversation() {\n  setCornerSceneActive(false);" not in text:
        text = replace_once(text, return_anchor, return_new, "conversation return reset")

    old_workbench = '''workbenchTrigger.addEventListener("click", () => {
  if (!ready || inFlight || pendingConfirmation) return;
  const opening = workbenchSurface.hidden;
  if (opening) transitionToSurface(() => bridge.loadWorkbench());
  else returnToConversation();
});'''
    new_workbench = '''workbenchTrigger.addEventListener("click", () => {
  if (!ready || inFlight || pendingConfirmation) return;
  const opening = workbenchSurface.hidden;
  if (opening) {
    transitionToSurface(() => bridge.loadWorkbench());
    // Workbench owns a distinct visual state while keeping the same Home.
    setCornerSceneActive(true);
  } else {
    returnToConversation();
  }
});'''
    if "Workbench owns a distinct visual state while keeping the same Home." not in text:
        text = replace_once(text, old_workbench, new_workbench, "workbench scene switch")

    write_preserving_bom(APP_JS, text, bom, newline)
    print("Patched frontend/renderer/app.js")


def write_test() -> None:
    content = r'''"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const sceneMap = require("./scene-map.js");

test("Workbench corner follows Home day/evening period", () => {
  const day = sceneMap.resolveCornerScene({
    observed_at: "2026-08-27T12:00:00+03:00",
  });
  const evening = sceneMap.resolveCornerScene({
    observed_at: "2026-08-27T20:00:00+03:00",
  });

  assert.equal(day.id, "scene.home.day.corner");
  assert.equal(day.source, "assets/presence/day/corner/corner_day.png");
  assert.equal(evening.id, "scene.home.evening.corner");
  assert.equal(evening.source, "assets/presence/evening/corner/corner_evening.png");
});

test("Corner period uses Home observed_at, not the browser clock", () => {
  assert.equal(
    sceneMap.resolveHomePeriod({ observed_at: "2026-08-27T06:59:59+03:00" }),
    "evening"
  );
  assert.equal(
    sceneMap.resolveHomePeriod({ observed_at: "2026-08-27T07:00:00+03:00" }),
    "day"
  );
  assert.equal(
    sceneMap.resolveHomePeriod({ observed_at: "2026-08-27T17:59:59+03:00" }),
    "day"
  );
  assert.equal(
    sceneMap.resolveHomePeriod({ observed_at: "2026-08-27T18:00:00+03:00" }),
    "evening"
  );
});
'''
    CORNER_TEST.write_text(content, encoding="utf-8")
    print("Wrote frontend/scenes/corner-scene.test.cjs")


def run_check(args: list[str], label: str) -> None:
    print(f"\n[{label}] {' '.join(args)}")
    result = subprocess.run(args, cwd=ROOT)
    if result.returncode != 0:
        raise RuntimeError(f"{label} failed with exit code {result.returncode}")


def main() -> int:
    if not SCENE_MAP.exists() or not APP_JS.exists():
        print("Put this script in the Masha Home repository root and run it there.", file=sys.stderr)
        return 2

    print("Masha Home — manual Corner scene patch")
    print(f"Repo: {ROOT}")

    ensure_assets()
    backup_files()
    patch_scene_map()
    patch_app()
    write_test()

    run_check(["node", "--check", str(SCENE_MAP.relative_to(ROOT))], "scene-map syntax")
    run_check(["node", "--check", str(APP_JS.relative_to(ROOT))], "renderer syntax")
    run_check(
        [
            "node",
            "--test",
            "frontend/scenes/scene-map.test.cjs",
            "frontend/scenes/corner-scene.test.cjs",
        ],
        "scene tests",
    )
    run_check(["git", "diff", "--check"], "git diff check")

    print("\nREADY")
    print("Expected behaviour:")
    print("  Workbench / Уголок -> frontend/assets/presence/day/corner/corner_day.png from 07:00 to 17:59 Home time")
    print("  Workbench / Уголок -> frontend/assets/presence/evening/corner/corner_evening.png from 18:00 to 06:59 Home time")
    print("  Leaving Уголок -> restores the current normal Presence scene")
    print("  Presentation updates while Уголок is open keep the Corner visual")
    print("\nInspect:")
    print("  git diff -- frontend/scenes/scene-map.js frontend/renderer/app.js frontend/scenes/corner-scene.test.cjs")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

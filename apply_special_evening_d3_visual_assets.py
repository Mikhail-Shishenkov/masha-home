from __future__ import annotations

from pathlib import Path
import hashlib

ROOT = Path.cwd()
PACK_ROOT = Path(__file__).resolve().parent
ASSET_SOURCE = PACK_ROOT / "d3_assets"

TARGET_DIR = ROOT / "frontend" / "assets" / "presence" / "evening"
SCENE_MAP = ROOT / "frontend" / "scenes" / "scene-map.js"
TEST_FILE = ROOT / "frontend" / "renderer" / "special-evening-visual-assets.test.cjs"

EXPECTED_ASSETS = {
    "special-close.png": "c92850a96285e4a1795f16f0e269e25a93faff80e807e1a64dab573a2b675574",
    "special-near.png": "f75f40857d6d0edd13245cde46da0767b805adce8ca3bcb900d79d1d21ed7e11",
    "special-quiet-near.png": "4feaf21f3d9cd58f8dcc749e4a6e1c74d1e0c0ca9a7bab66f7aad7f7a94c4fc6",
}


class PatchError(RuntimeError):
    pass


def decode_text(path: Path) -> tuple[str, str, str]:
    raw = path.read_bytes()

    if raw.startswith(b"\xff\xfe") or raw.startswith(b"\xfe\xff"):
        encoding = "utf-16"
    elif raw.startswith(b"\xef\xbb\xbf"):
        encoding = "utf-8-sig"
    else:
        encoding = "utf-8"

    try:
        text = raw.decode(encoding)
    except UnicodeDecodeError as exc:
        raise PatchError(f"{path}: cannot decode {encoding}: {exc}") from exc

    newline = "\r\n" if "\r\n" in text else "\n"
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    return normalized, encoding, newline


def encode_text(text: str, encoding: str, newline: str) -> bytes:
    rendered = text.replace("\n", newline)

    if encoding == "utf-16":
        return rendered.encode("utf-16")
    if encoding == "utf-8-sig":
        return rendered.encode("utf-8-sig")
    return rendered.encode("utf-8")


try:
    staged_assets: dict[Path, bytes] = {}

    for name, expected_hash in EXPECTED_ASSETS.items():
        source = ASSET_SOURCE / name

        if not source.exists():
            raise PatchError(f"missing asset in pack: {source}")

        raw = source.read_bytes()

        if not raw.startswith(b"\x89PNG\r\n\x1a\n"):
            raise PatchError(f"{source}: not a PNG file")

        actual_hash = hashlib.sha256(raw).hexdigest()

        if actual_hash != expected_hash:
            raise PatchError(
                f"{source}: checksum mismatch "
                f"(expected {expected_hash}, got {actual_hash})"
            )

        target = TARGET_DIR / name

        if target.exists():
            raise PatchError(
                f"{target}: already exists; refusing to overwrite an authored asset"
            )

        staged_assets[target] = raw
        print(f"[CHECK] asset {name}: approved checksum")

    if not SCENE_MAP.exists():
        raise PatchError("frontend/scenes/scene-map.js not found")

    scene_text, scene_encoding, scene_newline = decode_text(SCENE_MAP)

    required = (
        'presentation.home_proximity || "wide"',
        'if (specialProximity === "near")',
        'if (specialProximity === "close")',
        'specialClose: scene(',
        'specialMug: scene(',
        'specialQuiet: scene(',
    )
    missing = [marker for marker in required if marker not in scene_text]

    if missing:
        raise PatchError(
            "D2 proximity foundation is not in the expected state: "
            + ", ".join(missing)
        )

    for marker in (
        "specialNear: scene(",
        "specialQuietNear: scene(",
        "assets/presence/evening/special-near.png",
        "assets/presence/evening/special-quiet-near.png",
    ):
        if marker in scene_text:
            raise PatchError(
                f"scene-map already contains D3 marker: {marker}"
            )

    old_close = '''    specialClose: scene(
  "evening",
  "special_close",
  "assets/presence/evening/special-cozy-close.png",
  "Маша совсем рядом в тихом вечернем доме"
),
'''

    new_close = '''    specialClose: scene(
  "evening",
  "special_close",
  "assets/presence/evening/special-close.png",
  "Маша рядом с тобой в тёплом вечернем доме"
),

specialNear: scene(
  "evening",
  "special_near",
  "assets/presence/evening/special-near.png",
  "Маша совсем рядом и внимательно смотрит на тебя"
),

specialQuietNear: scene(
  "evening",
  "special_quiet_near",
  "assets/presence/evening/special-quiet-near.png",
  "Маша расслабилась совсем рядом и просто остаётся с тобой"
),
'''

    if scene_text.count(old_close) != 1:
        raise PatchError(
            "scene-map registry: expected one legacy specialClose block"
        )

    scene_text = scene_text.replace(old_close, new_close, 1)
    print("[CHECK] scene registry: add canonical close/near/quiet-near")

    special_start = scene_text.find("if (specialEvening) {")
    following_marker = '  if (\n  activity === "idle"\n'
    special_end = scene_text.find(
        following_marker,
        special_start + len("if (specialEvening) {"),
    )

    if special_start < 0 or special_end < 0:
        raise PatchError("scene-map: Special Evening resolver block not found")

    special_block = '''if (specialEvening) {
  if (["skeptical", "serious"].includes(expression)) {
    return scenes.firmDisagreement;
  }

  if (specialProximity === "near") {
    if (
      activity === "idle"
      && presence.ambient === "quiet"
    ) {
      return scenes.specialQuietNear;
    }

    return scenes.specialNear;
  }

  if (specialProximity === "close") {
    return scenes.specialClose;
  }

  return scenes.specialEvening;
}
'''

    scene_text = (
        scene_text[:special_start]
        + special_block
        + scene_text[special_end:]
    )
    print("[CHECK] scene resolver: deterministic wide -> close -> near")

    if TEST_FILE.exists():
        raise PatchError(
            "frontend/renderer/special-evening-visual-assets.test.cjs already exists"
        )

    test_text = r'''"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const root = path.join(__dirname, "..");
const scenes = fs.readFileSync(
  path.join(root, "scenes", "scene-map.js"),
  "utf8"
);

assert.match(scenes, /assets\/presence\/evening\/special-close\.png/);
assert.match(scenes, /assets\/presence\/evening\/special-near\.png/);
assert.match(scenes, /assets\/presence\/evening\/special-quiet-near\.png/);

assert.match(scenes, /specialNear: scene\(/);
assert.match(scenes, /specialQuietNear: scene\(/);

const specialAt = scenes.indexOf("if (specialEvening)");
const ordinaryAt = scenes.indexOf(
  '  if (\n  activity === "idle"\n',
  specialAt
);

assert.ok(specialAt >= 0);
assert.ok(ordinaryAt > specialAt);

const specialBlock = scenes.slice(specialAt, ordinaryAt);

assert.match(
  specialBlock,
  /specialProximity === "near"[\s\S]*scenes\.specialQuietNear/
);
assert.match(
  specialBlock,
  /specialProximity === "near"[\s\S]*return scenes\.specialNear/
);
assert.match(
  specialBlock,
  /specialProximity === "close"[\s\S]*return scenes\.specialClose/
);
assert.match(specialBlock, /return scenes\.specialEvening/);

assert.doesNotMatch(specialBlock, /chooseVariant\(/);
assert.doesNotMatch(specialBlock, /scenes\.specialMug/);
assert.doesNotMatch(specialBlock, /scenes\.specialQuiet;/);

console.log("special evening D3 visual asset tests passed");
'''

except PatchError as exc:
    print()
    print(f"[STOP] {exc}")
    print("No files were written.")
    raise SystemExit(1)

# Write only after every preflight check passed.
TARGET_DIR.mkdir(parents=True, exist_ok=True)

for target, raw in staged_assets.items():
    target.write_bytes(raw)
    print(f"[WRITE] {target.relative_to(ROOT)}")

SCENE_MAP.write_bytes(
    encode_text(scene_text, scene_encoding, scene_newline)
)
print(
    f"[WRITE] {SCENE_MAP.relative_to(ROOT)} "
    f"({scene_encoding}, {'CRLF' if scene_newline == chr(13)+chr(10) else 'LF'})"
)

TEST_FILE.parent.mkdir(parents=True, exist_ok=True)
TEST_FILE.write_text(test_text, encoding="utf-8")
print(f"[WRITE] {TEST_FILE.relative_to(ROOT)}")

print()
print("D3 applied: canonical Special Evening visual family.")
print()
print("Mapping:")
print("  wide                  -> special-cozy-wide.png")
print("  close                 -> special-close.png")
print("  near                  -> special-near.png")
print("  near + idle + quiet   -> special-quiet-near.png")
print()
print("Run:")
print(r"  node frontend\renderer\special-evening-proximity.test.cjs")
print(r"  node frontend\renderer\special-evening-visual-assets.test.cjs")
print(r"  .\.venv\Scripts\python.exe -m pytest tests/test_presentation_runtime.py -q")

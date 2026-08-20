from pathlib import Path

path = Path(r"frontend/scenes/scene-map.js")
raw = path.read_bytes()

if raw.startswith(b"\xff\xfe") or raw.startswith(b"\xfe\xff"):
    text = raw.decode("utf-16")
    path.write_text(text, encoding="utf-8-sig", newline="")
    print("[OK] scene-map.js normalized: UTF-16 -> UTF-8 with BOM")
elif raw.startswith(b"\xef\xbb\xbf"):
    print("[OK] scene-map.js is already UTF-8 with BOM")
else:
    try:
        raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise SystemExit(f"[STOP] Unknown text encoding: {exc}")
    print("[OK] scene-map.js is already UTF-8")

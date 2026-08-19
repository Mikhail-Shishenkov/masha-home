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
        STAGED[p] = p.read_text(encoding="utf-8")
    return STAGED[p]


def replace_once(path: str, old: str, new: str, label: str) -> None:
    text = read(path)
    count = text.count(old)
    if count != 1:
        raise PatchError(
            f"{path}: {label}: expected 1 exact match, found {count}"
        )
    STAGED[ROOT / path] = text.replace(old, new, 1)
    print(f"[CHECK] {path}: {label}")


try:
    replace_once(
        "backend/llm/fake_provider.py",
        '''    response_text: str = "Тестовый ответ Маши."
    last_request: ModelRequest | None = field(default=None, init=False)
''',
        '''    response_text: str = "Тестовый ответ Маши."
    last_request: ModelRequest | None = field(default=None, init=False)
    requests: list[ModelRequest] = field(default_factory=list, init=False)
''',
        "add request history",
    )

    replace_once(
        "backend/llm/fake_provider.py",
        '''        self.last_request = request
        return ModelResponse(
''',
        '''        self.last_request = request
        self.requests.append(request)
        return ModelResponse(
''',
        "record every request",
    )

    replace_once(
        "tests/test_application_boundary.py",
        '''    assert provider.last_request is not None
    assert provider.last_request.private_context["home_moment"] == "special_evening"
    assert "РЕЖИМ «ВДВОЁМ»" in (
        provider.last_request.private_context["home_moment_contract"]
    )
''',
        '''    conversation_requests = [
        request
        for request in provider.requests
        if request.private_context.get("home_moment") == "special_evening"
    ]

    assert conversation_requests
    conversation_request = conversation_requests[-1]
    assert "РЕЖИМ «ВДВОЁМ»" in (
        conversation_request.private_context["home_moment_contract"]
    )
''',
        "inspect conversation request instead of expression-classifier request",
    )

    for path, text in STAGED.items():
        if path.suffix == ".py":
            compile(text, str(path), "exec")

except (PatchError, SyntaxError) as exc:
    print()
    print(f"[STOP] {exc}")
    print("No files were written.")
    raise SystemExit(1)

for path, text in STAGED.items():
    path.write_text(text, encoding="utf-8")
    print(f"[WRITE] {path.relative_to(ROOT)}")

print()
print("Fix applied.")
print(
    r"Run: .\.venv\Scripts\python.exe -m pytest "
    r"tests/test_capability_router.py tests/test_context_compiler.py "
    r"tests/test_chat_capability_integration.py tests/test_application_boundary.py -q"
)

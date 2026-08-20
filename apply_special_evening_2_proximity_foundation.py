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


def append_once(path: str, marker: str, block: str, label: str) -> None:
    text = read(path)
    if marker in text:
        raise PatchError(f"{path}: {label}: already present")
    if not text.endswith("\n"):
        text += "\n"
    stage(path, text + "\n" + block.strip() + "\n")
    print(f"[CHECK] {path}: {label}")


try:
    insert_after(
        "backend/presentation/models.py",
        '''class HomeMoment(str, Enum):
    ORDINARY = "ordinary"
    SPECIAL_EVENING = "special_evening"

''',
        '''class HomeProximity(str, Enum):
    WIDE = "wide"
    CLOSE = "close"
    NEAR = "near"


''',
        "add HomeProximity",
    )

    replace_once(
        "backend/presentation/models.py",
        '''    home_state: HomeState = HomeState.READY
    home_moment: HomeMoment = HomeMoment.ORDINARY
    window_state: WindowState = WindowState.FOCUSED
''',
        '''    home_state: HomeState = HomeState.READY
    home_moment: HomeMoment = HomeMoment.ORDINARY
    home_proximity: HomeProximity = HomeProximity.WIDE
    window_state: WindowState = WindowState.FOCUSED
''',
        "add proximity to HomePresentationModel",
    )

    replace_once(
        "backend/presentation/events.py",
        '''from .models import HomeMoment, InteractionSurface, RuntimeMode
''',
        '''from .models import HomeMoment, HomeProximity, InteractionSurface, RuntimeMode
''',
        "import HomeProximity in events",
    )

    insert_after(
        "backend/presentation/events.py",
        '''class HomeMomentChanged(PresentationEvent):
    kind: Literal["home_moment_changed"] = "home_moment_changed"
    moment: HomeMoment

''',
        '''class HomeProximityChanged(PresentationEvent):
    kind: Literal["home_proximity_changed"] = "home_proximity_changed"
    proximity: HomeProximity


''',
        "add HomeProximityChanged",
    )

    replace_once(
        "backend/presentation/reducer.py",
        '''    HomeMomentChanged,
)
''',
        '''    HomeMomentChanged,
    HomeProximityChanged,
)
''',
        "import proximity event",
    )

    replace_once(
        "backend/presentation/reducer.py",
        '''    HomePresentationModel,
    InteractionSurface,
''',
        '''    HomePresentationModel,
    HomeMoment,
    HomeProximity,
    InteractionSurface,
''',
        "import proximity models",
    )

    replace_once(
        "backend/presentation/reducer.py",
        '''        if isinstance(event, HomeMomentChanged):
            return model.model_copy(
                update={
                    "home_moment": event.moment,
                }
            )

        if isinstance(event, UserSentMessage):
''',
        '''        if isinstance(event, HomeMomentChanged):
            update = {
                "home_moment": event.moment,
            }
            if event.moment is HomeMoment.ORDINARY:
                update["home_proximity"] = HomeProximity.WIDE
            return model.model_copy(update=update)

        if isinstance(event, HomeProximityChanged):
            if model.home_moment is not HomeMoment.SPECIAL_EVENING:
                return model
            return model.model_copy(
                update={
                    "home_proximity": event.proximity,
                }
            )

        if isinstance(event, UserSentMessage):
''',
        "reduce proximity deterministically",
    )

    replace_once(
        "backend/presentation/__init__.py",
        '''    HomeMomentChanged,
)
''',
        '''    HomeMomentChanged,
    HomeProximityChanged,
)
''',
        "export proximity event import",
    )

    replace_once(
        "backend/presentation/__init__.py",
        '''    HomeMoment,
)
''',
        '''    HomeMoment,
    HomeProximity,
)
''',
        "export proximity model import",
    )

    insert_after(
        "backend/presentation/__init__.py",
        '''    "HomeState",
''',
        '''    "HomeMoment",
    "HomeProximity",
    "HomeMomentChanged",
    "HomeProximityChanged",
''',
        "add proximity symbols to __all__",
    )

    replace_once(
        "backend/application/home_snapshot.py",
        '''    HomeMoment,
    HomeMomentChanged,
)
''',
        '''    HomeMoment,
    HomeMomentChanged,
    HomeProximity,
    HomeProximityChanged,
)
''',
        "import proximity in Home session",
    )

    insert_after(
        "backend/application/home_snapshot.py",
        '''    def leave_special_evening(self) -> HomeSnapshotView:
        """Return Home to the ordinary day/evening presence family."""
        return self._dispatch(
            HomeMomentChanged(
                occurred_at=self._now(),
                moment=HomeMoment.ORDINARY,
            )
        )

''',
        '''    def set_special_proximity(
            self,
            proximity: HomeProximity,
    ) -> HomeSnapshotView | None:
        """Change closeness only inside the explicit Special Evening."""
        if (
            self._runtime.model.home_moment
            is not HomeMoment.SPECIAL_EVENING
        ):
            return None

        return self._dispatch(
            HomeProximityChanged(
                occurred_at=self._now(),
                proximity=proximity,
            )
        )

''',
        "add session proximity boundary",
    )

    replace_once(
        "tests/test_presentation_runtime.py",
        '''    HomeMomentChanged,
    HomeMoment,
)
''',
        '''    HomeMomentChanged,
    HomeProximityChanged,
    HomeMoment,
)
''',
        "import proximity event in tests",
    )

    replace_once(
        "tests/test_presentation_runtime.py",
        '''    HomePresentationModel,
    InteractionSurface,
''',
        '''    HomePresentationModel,
    HomeProximity,
    InteractionSurface,
''',
        "import proximity model in tests",
    )

    append_once(
        "tests/test_presentation_runtime.py",
        "def test_special_evening_proximity_is_explicit_and_resets_when_leaving():",
        r'''
def test_special_evening_proximity_is_explicit_and_resets_when_leaving():
    reducer = PresentationReducer()
    model = _open_model()

    ignored = reducer.reduce(
        model,
        _event(
            HomeProximityChanged,
            proximity=HomeProximity.NEAR,
        ),
    )
    assert ignored.home_proximity is HomeProximity.WIDE

    special = reducer.reduce(
        model,
        _event(
            HomeMomentChanged,
            seconds=2,
            moment=HomeMoment.SPECIAL_EVENING,
        ),
    )
    assert special.home_proximity is HomeProximity.WIDE

    close = reducer.reduce(
        special,
        _event(
            HomeProximityChanged,
            seconds=3,
            proximity=HomeProximity.CLOSE,
        ),
    )
    assert close.home_proximity is HomeProximity.CLOSE

    near = reducer.reduce(
        close,
        _event(
            HomeProximityChanged,
            seconds=4,
            proximity=HomeProximity.NEAR,
        ),
    )
    assert near.home_proximity is HomeProximity.NEAR

    ordinary = reducer.reduce(
        near,
        _event(
            HomeMomentChanged,
            seconds=5,
            moment=HomeMoment.ORDINARY,
        ),
    )
    assert ordinary.home_proximity is HomeProximity.WIDE
''',
        "add proximity reducer test",
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
print("Special Evening 2.0 foundation applied.")
print(
    r"Run: .\.venv\Scripts\python.exe -m pytest "
    r"tests/test_presentation_runtime.py -q"
)

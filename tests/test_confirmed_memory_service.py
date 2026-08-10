import pytest
from pydantic import ValidationError

from backend.memory.confirmed_memory_service import (
    ConfirmedMemoryService,
    ExplicitMemoryConfirmation,
)
from backend.memory.memory_models import IdentityCode, SourceType
from backend.memory.memory_store import MemoryStore
from backend.memory.sqlite_repository import MemorySqliteRepository


def _explicit_fact(store: MemoryStore, memory_id: str = "fact_confirmed"):
    source = store.get_fact("fact_002")
    return source.model_copy(
        update={
            "id": memory_id,
            "key": "confirmed_preference",
            "value": "written only after explicit confirmation",
            "source": SourceType.EXPLICIT_USER_INPUT,
            "source_episode_ids": [],
        }
    )


def test_confirmed_memory_writes_one_explicit_prepared_record(memory_path: str):
    store = MemoryStore(memory_path)
    service = ConfirmedMemoryService(store)
    fact = _explicit_fact(store)

    saved = service.confirm(
        ExplicitMemoryConfirmation(confirmed_by=IdentityCode.MISHA, record=fact)
    )
    reloaded = MemoryStore(memory_path)

    assert saved.id == "fact_confirmed"
    assert reloaded.get_fact("fact_confirmed") is not None
    assert reloaded.get_fact("fact_confirmed").value == "written only after explicit confirmation"


def test_confirmation_rejects_non_explicit_or_duplicate_records(memory_path: str):
    store = MemoryStore(memory_path)
    service = ConfirmedMemoryService(store)
    fact = _explicit_fact(store)

    with pytest.raises(ValidationError, match="explicit_user_input"):
        ExplicitMemoryConfirmation(
            confirmed_by=IdentityCode.MISHA,
            record=fact.model_copy(update={"source": SourceType.CONVERSATION}),
        )

    confirmation = ExplicitMemoryConfirmation(confirmed_by=IdentityCode.MISHA, record=fact)
    service.confirm(confirmation)
    with pytest.raises(ValueError, match="already exists"):
        service.confirm(confirmation)


def test_confirmed_memory_uses_the_existing_sqlite_repository_contract(tmp_path, memory_path: str):
    json_store = MemoryStore(memory_path)
    repository = MemorySqliteRepository(tmp_path / "memory.sqlite3")
    repository.replace_document(json_store.read_document())
    fact = _explicit_fact(json_store, memory_id="fact_confirmed_sqlite")

    ConfirmedMemoryService(repository).confirm(
        ExplicitMemoryConfirmation(confirmed_by=IdentityCode.MISHA, record=fact)
    )

    document = repository.read_document()
    assert document is not None
    assert any(item.id == "fact_confirmed_sqlite" for item in document.facts)

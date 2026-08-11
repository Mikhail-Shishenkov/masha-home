import json

import pytest

from backend.conversation.memory_intent import MemoryProposalStore, ProposalStatus
from backend.memory.memory_management import MemoryManagementService, MemoryMutationOperation
from backend.memory.memory_models import MemoryDocument
from backend.memory.memory_retriever import MemoryRetriever
from backend.memory.sqlite_repository import MemorySqliteRepository


PROJECT_ID = "project_masha_home"


def _service(tmp_path, canonical_memory):
    repository = MemorySqliteRepository(tmp_path / "memory.sqlite3")
    repository.replace_document(canonical_memory)
    return MemoryManagementService(repository), repository, MemoryProposalStore(tmp_path / "proposals.json")


def test_inspection_lists_gets_and_filters_local_sqlite_memory(tmp_path, canonical_memory):
    service, _, _ = _service(tmp_path, canonical_memory)

    facts = service.list(record_type="fact", project_id=PROJECT_ID, query="python")
    view = service.get("fact_002")

    assert [item.record_id for item in facts] == ["fact_002"]
    assert view is not None
    assert view.identity_version == "masha-0.1"
    assert view.source == "conversation"
    assert view.confidence == 1.0


def test_archive_and_forget_are_pending_then_hidden_with_audit(tmp_path, canonical_memory):
    service, repository, proposals = _service(tmp_path, canonical_memory)
    original = json.dumps(repository.read_document().model_dump(mode="json"), sort_keys=True)
    archive = service.propose(proposals, operation=MemoryMutationOperation.ARCHIVE,
                              record_id="fact_001", conversation_id="c")

    assert json.dumps(repository.read_document().model_dump(mode="json"), sort_keys=True) == original
    service.confirm_proposal(archive, proposals)
    forget = service.propose(proposals, operation=MemoryMutationOperation.FORGET,
                             record_id="fact_002", conversation_id="c")
    service.confirm_proposal(forget, proposals)

    assert service.get("fact_001").payload["visibility"] == "hidden"
    assert service.get("fact_002").payload["visibility"] == "hidden"
    assert all(item["data"]["id"] not in {"fact_001", "fact_002"}
               for item in MemoryRetriever(repository).retrieve(project_id=PROJECT_ID, limit=20))
    assert {"memory_archive", "memory_forget"} <= {event["action"] for event in repository.list_audit_events()}


def test_rejected_or_unconfirmed_edit_does_not_mutate_memory(tmp_path, canonical_memory):
    service, repository, proposals = _service(tmp_path, canonical_memory)
    replacement = service.get("fact_001").payload | {"value": "changed"}
    proposal = service.propose(proposals, operation=MemoryMutationOperation.EDIT,
                               record_id="fact_001", conversation_id="c", replacement_payload=replacement)
    before = repository.read_document().model_dump(mode="json")
    proposals.set_status(proposal.id, ProposalStatus.CANCELLED)

    assert repository.read_document().model_dump(mode="json") == before


def test_confirmed_mutation_proposal_is_idempotent(tmp_path, canonical_memory):
    service, _, proposals = _service(tmp_path, canonical_memory)
    proposal = service.propose(proposals, operation=MemoryMutationOperation.ARCHIVE,
                               record_id="fact_001", conversation_id="c")
    service.confirm_proposal(proposal, proposals)

    with pytest.raises(ValueError, match="not a pending"):
        service.confirm_proposal(proposals.get(proposal.id), proposals)


def test_supersession_keeps_old_record_and_retrieves_current_replacement(tmp_path, canonical_memory):
    service, repository, proposals = _service(tmp_path, canonical_memory)
    old = service.get("fact_001").payload
    replacement = old | {"id": "fact_repository_new", "value": "local-only repository",
                         "status": "active", "superseded_by": None, "supersedes_id": "fact_001"}
    proposal = service.propose(proposals, operation=MemoryMutationOperation.SUPERSEDE,
                               record_id="fact_001", conversation_id="c", replacement_payload=replacement)
    service.confirm_proposal(proposal, proposals)

    document = repository.read_document()
    old_after = next(item for item in document.facts if item.id == "fact_001")
    new_after = next(item for item in document.facts if item.id == "fact_repository_new")
    retrieved = MemoryRetriever(repository).retrieve(project_id=PROJECT_ID, limit=20)

    assert old_after.status.value == "superseded"
    assert old_after.superseded_by == "fact_repository_new"
    assert new_after.supersedes_id == "fact_001"
    assert any(item["data"]["id"] == "fact_repository_new" for item in retrieved)
    assert all(item["data"]["id"] != "fact_001" for item in retrieved)
    assert any(event["payload"].get("proposal_id") == proposal.id for event in repository.list_audit_events())


def test_conflicts_trace_and_restart_are_local_and_deterministic(tmp_path, canonical_memory):
    service, repository, _ = _service(tmp_path, canonical_memory)
    payload = repository.read_document().model_dump(mode="json")
    payload["facts"].append(payload["facts"][0] | {"id": "fact_conflict", "value": "other repository"})
    repository.replace_document(MemoryDocument.model_validate(payload), action="test_conflict")

    conflicts = service.conflicts(project_id=PROJECT_ID)
    retrieved = MemoryRetriever(repository).retrieve(project_id=PROJECT_ID, limit=20)
    trace = service.trace(retrieved)
    restarted = MemoryManagementService(MemorySqliteRepository(repository.database_path))

    assert any({item.record_id for item in group} == {"fact_001", "fact_conflict"} for group in conflicts)
    assert trace and trace[0].record_id == retrieved[0]["data"]["id"]
    assert "active_status" in trace[0].reasons
    assert restarted.get("fact_conflict") is not None

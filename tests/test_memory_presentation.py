from backend.conversation.cli import _run_memory_command
from backend.conversation.memory_intent import MemoryProposalStore
from backend.memory.memory_management import MemoryManagementService
from backend.memory.sqlite_repository import MemorySqliteRepository


def _runtime(tmp_path, canonical_memory):
    repository = MemorySqliteRepository(tmp_path / "memory.sqlite3")
    repository.replace_document(canonical_memory)
    return MemoryManagementService(repository), MemoryProposalStore(tmp_path / "proposals.json")


def test_memory_commands_render_human_text_and_keep_raw_diagnostics(tmp_path, canonical_memory):
    management, proposals = _runtime(tmp_path, canonical_memory)
    output = []
    run = lambda text: _run_memory_command(text, memory_management=management, proposal_store=proposals, conversation_id="c", output_fn=output.append)

    run("list")
    assert "Что я помню" in output[-1] and "fact_" not in output[-1]
    run("get fact_001")
    assert "Память:" in output[-1] and "Тип: факт" in output[-1]
    run("find python")
    assert "Изучает Python" in output[-1]
    run("get fact_001 --raw")
    assert '"record_id": "fact_001"' in output[-1]


def test_memory_mutation_preview_requires_explicit_cli_confirmation(tmp_path, canonical_memory):
    management, proposals = _runtime(tmp_path, canonical_memory)
    output = []
    _run_memory_command("archive fact_001", memory_management=management, proposal_store=proposals, conversation_id="c", output_fn=output.append)
    assert "Применить?" in output[-1]
    assert management.get("fact_001").payload["visibility"] == "visible"
    _run_memory_command("confirm", memory_management=management, proposal_store=proposals, conversation_id="c", output_fn=output.append)
    assert management.get("fact_001").payload["visibility"] == "hidden"

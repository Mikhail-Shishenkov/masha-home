from pathlib import Path
from datetime import datetime, timezone

import pytest

from backend.conversation.conversation_service import ConversationService, ConversationUnavailableError
from backend.conversation.conversation_store import ConversationStore
from backend.conversation.memory_intent import MemoryIntentHandler, MemoryProposalStore
from backend.memory.confirmed_memory_service import ConfirmedMemoryService
from backend.identity.identity_kernel import IdentityKernel
from backend.identity.identity_store import IdentityStore
from backend.llm.fake_provider import FakeProvider
from backend.llm.model_provider import ModelProviderUnavailableError
from backend.llm.model_router import ModelRouter
from backend.memory.memory_retriever import MemoryRetriever
from backend.memory.memory_store import MemoryStore
from backend.memory.working_memory import WorkingMemory
from backend.connectors.google_calendar.reader import CalendarReadOutcome, CalendarEventEvidence
from backend.connectors.google_drive.reader import DriveReadOutcome, ResolvedDriveDocumentRequest
from backend.document_read import DocumentEvidence, DocumentPageEvidence, DocumentReadReceipt, DocumentReadSourceKind


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _service(tmp_path, provider):
    store = MemoryStore(PROJECT_ROOT / "tests" / "fixtures" / "test_memory.json")
    return ConversationService(
        identity_kernel=IdentityKernel(IdentityStore(PROJECT_ROOT / "identity" / "masha.identity.json")),
        memory_retriever=MemoryRetriever(store),
        working_memory=WorkingMemory(),
        router=ModelRouter([provider]),
        history=ConversationStore(tmp_path / "history.json"),
    )


def test_service_routes_identity_bounded_memory_time_and_history(tmp_path):
    provider = FakeProvider(provider_id="ollama-local", response_text="Я здесь.")
    service = _service(tmp_path, provider)

    conversation_id, text = service.send("Привет, Маша.", project_id="project_masha_home")

    assert text == "Я здесь."
    assert provider.last_request is not None
    assert provider.last_request.identity_context.name == "Маша"
    assert "current_local_time" in provider.last_request.private_context
    assert len(provider.last_request.private_context["memory_context"]) <= 6
    assert [message.role.value for message in service.history.messages(conversation_id)] == ["user", "assistant"]


def test_service_returns_controlled_error_for_unavailable_local_model(tmp_path):
    service = _service(tmp_path, FakeProvider(provider_id="ollama-local", available=False))

    with pytest.raises(ConversationUnavailableError, match="Локальная модель"):
        service.send("Привет", project_id="project_masha_home")

    assert len(service.history.messages(next(iter(service.history._data["conversations"]))["id"])) == 1


def test_service_reloads_history_and_uses_it_for_continuation_without_memory_mutation(tmp_path):
    provider = FakeProvider(provider_id="ollama-local", response_text="first")
    first_service = _service(tmp_path, provider)
    original_memory = (PROJECT_ROOT / "tests" / "fixtures" / "test_memory.json").read_bytes()

    conversation_id, _ = first_service.send("first user turn", project_id="project_masha_home")

    reloaded_provider = FakeProvider(provider_id="ollama-local", response_text="second")
    reloaded_service = _service(tmp_path, reloaded_provider)
    continued_id, text = reloaded_service.send(
        "second user turn",
        project_id="project_masha_home",
        conversation_id=conversation_id,
    )

    assert continued_id == conversation_id
    assert text == "second"
    assert [message.content for message in reloaded_provider.last_request.messages] == [
        "first user turn",
        "first",
        "second user turn",
    ]
    assert [message.role.value for message in reloaded_service.history.messages(conversation_id)] == [
        "user", "assistant", "user", "assistant"
    ]
    assert (PROJECT_ROOT / "tests" / "fixtures" / "test_memory.json").read_bytes() == original_memory


def test_service_handles_explicit_memory_without_calling_the_model(tmp_path, memory_path):
    provider = FakeProvider(provider_id="ollama-local", response_text="should not be used")
    memory_store = MemoryStore(memory_path)
    service = ConversationService(
        identity_kernel=IdentityKernel(IdentityStore(PROJECT_ROOT / "identity" / "masha.identity.json")),
        memory_retriever=MemoryRetriever(memory_store),
        working_memory=WorkingMemory(),
        router=ModelRouter([provider]),
        history=ConversationStore(tmp_path / "history.json"),
        memory_intent_handler=MemoryIntentHandler(
            proposal_store=MemoryProposalStore(tmp_path / "proposals.json"),
            confirmed_memory=ConfirmedMemoryService(memory_store),
        ),
    )
    original_memory = Path(memory_path).read_bytes()

    conversation_id, proposal = service.send("Запомни, что я предпочитаю локальные модели", project_id="project_masha_home")
    _, confirmation = service.send("Да", project_id="project_masha_home", conversation_id=conversation_id)

    assert "Сохраняем?" in proposal
    assert confirmation == "Готово, сохранила."
    assert provider.last_request is None
    assert Path(memory_path).read_bytes() != original_memory


def test_service_does_not_create_memory_from_an_ordinary_message(tmp_path, memory_path):
    provider = FakeProvider(provider_id="ollama-local", response_text="ordinary reply")
    memory_store = MemoryStore(memory_path)
    service = ConversationService(
        identity_kernel=IdentityKernel(IdentityStore(PROJECT_ROOT / "identity" / "masha.identity.json")),
        memory_retriever=MemoryRetriever(memory_store),
        working_memory=WorkingMemory(),
        router=ModelRouter([provider]),
        history=ConversationStore(tmp_path / "history.json"),
        memory_intent_handler=MemoryIntentHandler(
            proposal_store=MemoryProposalStore(tmp_path / "proposals.json"),
            confirmed_memory=ConfirmedMemoryService(memory_store),
        ),
    )
    original_memory = Path(memory_path).read_bytes()

    _, response = service.send("Я сегодня ездил на мотоцикле", project_id="project_masha_home")

    assert response == "ordinary reply"
    assert Path(memory_path).read_bytes() == original_memory


def test_calendar_evidence_reaches_only_local_model_context_and_not_history_or_memory(tmp_path):
    provider = FakeProvider(provider_id="ollama-local", response_text="Сегодня одна встреча.")

    class Calendar:
        def observe(self, _message, *, now_local):
            return CalendarReadOutcome("completed", (
                CalendarEventEvidence("primary", "Личный", "event-1", "Созвон", now_local, now_local, False, None, "confirmed"),
            ), now_local, now_local)
        def human_failure(self, _outcome):
            return "unavailable"

    service = _service(tmp_path, provider)
    service.google_calendar_service = Calendar()
    conversation_id, response = service.send("что у меня сегодня?", project_id="project_masha_home")

    assert response == "Сегодня одна встреча."
    assert provider.last_request.private_context["external_information"][0]["kind"] == "google_calendar"
    serialized = provider.last_request.model_dump_json()
    assert "REFRESH_TOKEN" not in serialized and "ACCESS_TOKEN" not in serialized
    assert all("Созвон" not in message.content for message in service.history.messages(conversation_id))


def test_drive_document_evidence_reaches_local_model_without_passive_memory(tmp_path):
    provider = FakeProvider(provider_id="ollama-local", response_text="В документе есть SQL план.")
    receipt = DocumentReadReceipt(
        receipt_id="doc-drive-1",
        source_kind=DocumentReadSourceKind.CONNECTOR,
        source_reference="drive-file-id-must-not-reach-model",
        source_domain="drive.google.com",
        display_name="SQL план",
        completed_at=datetime(2026, 8, 24, tzinfo=timezone.utc),
        evidence=DocumentEvidence(
            title="SQL план",
            page_count=1,
            pages_read=1,
            extracted_chars=23,
            content_sha256="a" * 64,
            pages=(DocumentPageEvidence(page_number=1, text="SQL plan evidence text."),),
        ),
    )

    class Drive:
        def observe(self, _message, *, conversation_id):
            assert conversation_id
            return DriveReadOutcome("read_completed", document_receipt=receipt)
        def human_result(self, _outcome):
            return "unavailable"

    class Passive:
        def __init__(self): self.calls = []
        def observe_safely(self, request): self.calls.append(request)

    service = _service(tmp_path, provider)
    passive = Passive()
    service.google_drive_service = Drive()
    service.passive_memory_service = passive
    conversation_id, response = service.send("прочитай файл SQL план", project_id="project_masha_home")

    assert response == "В документе есть SQL план."
    assert provider.last_request.private_context["external_information"][0]["kind"] == "document_read"
    serialized = provider.last_request.model_dump_json()
    assert "drive-file-id-must-not-reach-model" not in serialized
    assert "SQL plan evidence text." in serialized
    assert passive.calls == []
    assert all("SQL plan evidence text." not in item.content for item in service.history.messages(conversation_id))


@pytest.mark.parametrize("user_text", ("Прочитай второй", "Прочитай файл 03. Конспекты и готовые ответы"))
def test_resolved_drive_selection_replaces_only_model_current_request(tmp_path, user_text):
    provider = FakeProvider(provider_id="ollama-local", response_text="В выбранном документе есть конспекты.")
    receipt = DocumentReadReceipt(
        receipt_id="doc-drive-resolved",
        source_kind=DocumentReadSourceKind.CONNECTOR,
        source_reference="drive-file-id-must-not-reach-model",
        source_domain="drive.google.com",
        display_name="03. Конспекты и готовые ответы",
        completed_at=datetime(2026, 8, 24, tzinfo=timezone.utc),
        evidence=DocumentEvidence(
            title="Конспекты",
            page_count=1,
            pages_read=1,
            extracted_chars=23,
            content_sha256="b" * 64,
            pages=(DocumentPageEvidence(page_number=1, text="SQL plan evidence text."),),
        ),
    )

    class Drive:
        def observe(self, _message, *, conversation_id):
            return DriveReadOutcome(
                "read_completed",
                document_receipt=receipt,
                resolved_document_request=ResolvedDriveDocumentRequest(
                    display_name="03. Конспекты и готовые ответы",
                ),
            )
        def human_result(self, _outcome):
            return "unavailable"

    service = _service(tmp_path, provider)
    service.google_drive_service = Drive()
    conversation_id, _ = service.send(user_text, project_id="project_masha_home")

    assert service.history.messages(conversation_id)[0].content == user_text
    model_current = provider.last_request.messages[-1].content
    assert "03. Конспекты и готовые ответы" in model_current
    assert "уже разрешена приложением" in model_current
    assert "номер раздела" in model_current
    serialized = provider.last_request.model_dump_json()
    assert "drive-file-id-must-not-reach-model" not in serialized
    assert "SQL plan evidence text." in serialized
    assert "Выбранный файл и смысл чтения уже определены приложением" in provider.last_request.private_context["external_information_contract"]

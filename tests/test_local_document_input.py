from __future__ import annotations

import json
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace

import pytest
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

from backend.application import build_masha_application
from backend.document_read import (
    DocumentReadError,
    LocalDocumentInputError,
    LocalDocumentInputService,
)
from backend.document_read.reader import MAX_RAW_PDF_BYTES
from backend.external_observation import InternetAccessMode, InternetAccessPolicy, InternetAccessPolicyStore
from backend.llm.model_router import ModelRouter
from tests.test_support import LocalProfileProvider, _isolated_root


PROJECT_ID = "project_masha_home"


def _pdf(*pages: str) -> bytes:
    writer = PdfWriter()
    font = writer._add_object(DictionaryObject({
        NameObject("/Type"): NameObject("/Font"),
        NameObject("/Subtype"): NameObject("/Type1"),
        NameObject("/BaseFont"): NameObject("/Helvetica"),
    }))
    for text in pages:
        page = writer.add_blank_page(width=612, height=792)
        page[NameObject("/Resources")] = DictionaryObject({
            NameObject("/Font"): DictionaryObject({NameObject("/F1"): font}),
        })
        stream = DecodedStreamObject()
        stream.set_data(f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode("latin-1"))
        page[NameObject("/Contents")] = writer._add_object(stream)
    target = BytesIO()
    writer.write(target)
    return target.getvalue()


def _write_pdf(tmp_path: Path, name="report.pdf", *pages: str) -> Path:
    target = tmp_path / name
    target.write_bytes(_pdf(*(pages or ("Readable local evidence.",))))
    return target


def test_staging_projection_is_basename_size_and_opaque_token_only(tmp_path):
    selected = _write_pdf(tmp_path, "report.pdf")
    service = LocalDocumentInputService()

    projection = service.stage_selected_path(selected)

    payload = projection.model_dump(mode="json")
    assert payload["display_name"] == "report.pdf"
    assert payload["byte_size"] == selected.stat().st_size
    assert payload["token"].startswith("local_doc_")
    assert str(selected) not in json.dumps(payload)
    assert str(selected.parent) not in json.dumps(payload)


def test_local_staging_rejects_directory_symlink_and_oversize_before_parser(tmp_path):
    service = LocalDocumentInputService()
    with pytest.raises(LocalDocumentInputError, match="local_document_not_regular_file"):
        service.stage_selected_path(tmp_path)

    target = _write_pdf(tmp_path, "target.pdf")
    link = tmp_path / "link.pdf"
    try:
        link.symlink_to(target)
    except OSError:
        pytest.skip("symlink creation is unavailable on this Windows test host")
    with pytest.raises(LocalDocumentInputError, match="local_document_symlink_unsupported"):
        service.stage_selected_path(link)

    too_large = tmp_path / "large.pdf"
    too_large.write_bytes(b"%PDF-" + b"x" * MAX_RAW_PDF_BYTES)
    with pytest.raises(LocalDocumentInputError, match="local_document_too_large"):
        service.stage_selected_path(too_large)


def test_bounded_read_detects_file_growth_after_size_check(tmp_path, monkeypatch):
    selected = tmp_path / "race.pdf"
    selected.write_bytes(b"%PDF-" + b"x" * MAX_RAW_PDF_BYTES)
    original_stat = Path.stat

    def smaller_stat(path, *args, **kwargs):
        result = original_stat(path, *args, **kwargs)
        if path == selected and kwargs.get("follow_symlinks", True):
            return SimpleNamespace(st_size=1, st_mode=result.st_mode)
        return result

    monkeypatch.setattr(Path, "stat", smaller_stat)
    with pytest.raises(LocalDocumentInputError, match="local_document_too_large"):
        LocalDocumentInputService().stage_selected_path(selected)


def test_second_selection_clear_and_one_shot_token_lifecycle(tmp_path):
    service = LocalDocumentInputService()
    first = service.stage_selected_path(_write_pdf(tmp_path, "first.pdf"))
    second = service.stage_selected_path(_write_pdf(tmp_path, "second.pdf"))

    with pytest.raises(LocalDocumentInputError, match="local_document_token_invalid"):
        service.consume(first.token)
    assert service.clear("not-the-token") is False
    assert service.clear(second.token) is True
    with pytest.raises(LocalDocumentInputError, match="local_document_token_invalid"):
        service.consume(second.token)

    selected = service.stage_selected_path(_write_pdf(tmp_path, "third.pdf"))
    document = service.consume(selected.token)
    assert document.display_name == "third.pdf"
    with pytest.raises(LocalDocumentInputError, match="local_document_token_invalid"):
        service.consume(selected.token)


def test_local_pdf_turn_is_one_shot_local_only_and_path_free(tmp_path):
    root = _isolated_root(tmp_path)
    selected = _write_pdf(tmp_path, "report.pdf", "First page.", "Second page has authorization requirements.")
    raw_pdf = selected.read_bytes()
    provider = LocalProfileProvider(response_text="Я прочитала PDF: на второй странице есть требования.")
    application = build_masha_application(project_root=root, router=ModelRouter([provider]))
    workbench_skill = next(item for item in application.workbench().skills if item.skill_id == "local_document_read")
    assert workbench_skill.usage == "Только по твоей просьбе"
    assert "читать выбранный PDF" in workbench_skill.can
    staged = application.stage_local_document(str(selected))

    result = application.send_message_with_document(
        "Что написано на второй странице?",
        token=staged.token,
        project_id=PROJECT_ID,
    )

    assert result.assistant_message is not None
    assert result.assistant_message.local_documents[0].source_kind == "local"
    assert result.assistant_message.local_documents[0].display_name == "report.pdf"
    assert "прочитала pdf" in result.assistant_message.content.casefold()
    assert application.list_pending_memory_candidates() == ()
    request = next(item for item in provider.requests if item.private_context.get("external_information"))
    assert request.privacy_scope.value == "local_only" and request.required_capabilities.tools is False
    context = json.dumps(request.private_context, ensure_ascii=False)
    assert "Second page has authorization requirements." in context
    assert str(selected) not in context and selected.name in context
    serialized = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (root / "local-data" / "runtime").glob("*.json")
    )
    assert str(selected) not in serialized
    assert raw_pdf.decode("latin-1", errors="ignore") not in serialized

    with pytest.raises(LocalDocumentInputError, match="local_document_token_invalid"):
        application.send_message_with_document("ещё раз", token=staged.token, project_id=PROJECT_ID)

    restarted = build_masha_application(project_root=root, router=ModelRouter([LocalProfileProvider()]))
    transcript = restarted.conversation(result.conversation_id)
    assert transcript.messages[-1].local_documents[0].display_name == "report.pdf"


def test_local_pdf_remains_available_when_internet_access_is_off(tmp_path):
    root = _isolated_root(tmp_path)
    InternetAccessPolicyStore(root / "local-data" / "config" / "internet-access.json").save(
        InternetAccessPolicy(mode=InternetAccessMode.OFF)
    )
    selected = _write_pdf(tmp_path, "offline.pdf")
    application = build_masha_application(
        project_root=root,
        router=ModelRouter([LocalProfileProvider(response_text="Я прочитала PDF.")]),
    )
    staged = application.stage_local_document(str(selected))

    result = application.send_message_with_document("Прочитай PDF", token=staged.token, project_id=PROJECT_ID)

    assert result.assistant_message is not None
    assert result.assistant_message.local_documents[0].display_name == "offline.pdf"


@pytest.mark.parametrize(("response_text", "allowed"), [
    ("Я прочитала PDF и отвечаю по нему.", True),
    ("Я прочитала сайт и отвечаю по нему.", False),
    ("На второй странице документа есть вывод.", True),
])
def test_local_receipt_controls_document_and_webpage_claim_truth(tmp_path, response_text, allowed):
    root = _isolated_root(tmp_path)
    selected = _write_pdf(tmp_path, "report.pdf", "Page one.", "Page two.")
    provider = LocalProfileProvider(response_text=response_text)
    application = build_masha_application(project_root=root, router=ModelRouter([provider]))
    staged = application.stage_local_document(str(selected))

    result = application.send_message_with_document("Прочитай этот PDF", token=staged.token, project_id=PROJECT_ID)

    assert result.assistant_message is not None
    if allowed:
        assert result.assistant_message.content == response_text
    else:
        assert "прочитала сайт" not in result.assistant_message.content.casefold()
        assert "не читала страницу" in result.assistant_message.content.casefold()


def test_fake_pdf_and_typed_path_never_create_local_file_authority(tmp_path):
    root = _isolated_root(tmp_path)
    selected = tmp_path / "fake.pdf"
    selected.write_bytes(b"not a pdf")
    provider = LocalProfileProvider(response_text="Обычный разговор.")
    application = build_masha_application(project_root=root, router=ModelRouter([provider]))
    staged = application.stage_local_document(str(selected))

    with pytest.raises(DocumentReadError, match="pdf_unreadable"):
        application.send_message_with_document("Прочитай документ", token=staged.token, project_id=PROJECT_ID)
    assert provider.requests == []

    requests_before_typed_path = len(provider.requests)
    result = application.send_message(f"Маш, прочитай {selected}", project_id=PROJECT_ID)
    assert result.assistant_message is not None
    assert result.assistant_message.local_documents == ()
    assert len(provider.requests) > requests_before_typed_path
    assert not any(
        item.private_context.get("external_information")
        for item in provider.requests[requests_before_typed_path:]
    )

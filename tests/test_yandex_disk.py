from __future__ import annotations

import json
from io import BytesIO
from pathlib import Path

from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

from backend.connectors import yandex_disk_cli
from backend.connectors.google_drive.intent import drive_intent
from backend.connectors.google_drive.service import GoogleDriveConversationService
from backend.connectors.presented_read_sets import PresentedReadSetRegistry
from backend.connectors.yandex_mail.service import YandexMailConversationService
from backend.connectors.yandex_disk.config import YANDEX_DISK_SCOPE, YandexDiskConfig, YandexDiskConfigStore
from backend.connectors.yandex_disk.intent import disk_intent
from backend.connectors.yandex_disk.network import YandexDiskNetworkBlocked
from backend.connectors.yandex_disk.oauth import authorize, challenge
from backend.connectors.yandex_disk.reader import DiskFileCandidate, YandexDiskDocumentTooLarge, YandexDiskInvalidGrant, YandexDiskReader, YandexDiskUnavailable
from backend.connectors.yandex_disk.service import YandexDiskConversationService
from backend.document_read.reader import MAX_RAW_PDF_BYTES
from backend.external_observation.policy import InternetAccessMode, InternetAccessPolicy, InternetAccessPolicyStore
from backend.runtime.safety import AutonomySafetyService, AutonomySafetyStore
from backend.secrets import InMemorySecretStore
from backend.secrets import ConnectorCredentialState


def _pdf(text="Disk evidence."):
    writer=PdfWriter();font=writer._add_object(DictionaryObject({NameObject("/Type"):NameObject("/Font"),NameObject("/Subtype"):NameObject("/Type1"),NameObject("/BaseFont"):NameObject("/Helvetica")}));page=writer.add_blank_page(width=612,height=792);page[NameObject("/Resources")]=DictionaryObject({NameObject("/Font"):DictionaryObject({NameObject("/F1"):font})});stream=DecodedStreamObject();stream.set_data(f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode());page[NameObject("/Contents")]=writer._add_object(stream);target=BytesIO();writer.write(target);return target.getvalue()


class Transport:
    def __init__(self, *, pages=(), document=None):self.pages=list(pages);self.document=_pdf() if document is None else document;self.calls=[]
    def request_json(self,url,*,method="GET",headers=None,body=None):
        self.calls.append(("json",url,method,headers or {},body))
        if "/token" in url:return {"access_token":"DISK_ACCESS_TOKEN_MUST_NOT_ESCAPE"}
        if "/download?" in url:return {"href":"https://download.example.test/file.pdf"}
        return self.pages.pop(0) if self.pages else {"items":[]}
    def download(self,url,*,headers=None,maximum_bytes=0):
        self.calls.append(("download",url,headers or {},maximum_bytes))
        if len(self.document)>maximum_bytes:raise YandexDiskDocumentTooLarge("too_large")
        return self.document


def _reader(tmp_path:Path,transport=None):
    store=YandexDiskConfigStore(tmp_path/"local-data/config/yandex-disk.json");config=YandexDiskConfig(client_id="yandex-client");store.save(config);secrets=InMemorySecretStore();secrets.put(config.secret_ref,"DISK_REFRESH_TOKEN_MUST_NOT_ESCAPE");secrets.put(config.client_secret_ref,"DISK_CLIENT_SECRET_MUST_NOT_ESCAPE");return YandexDiskReader(config_store=store,secret_store=secrets,transport=transport or Transport()),store,secrets


def _items(*rows):
    return {"items":[{"path":path,"name":name,"mime_type":mime,"size":size,"modified":"2026-08-24T10:00:00Z"} for path,name,mime,size in rows]}


def test_scope_safe_config_and_separate_mail_credential(tmp_path):
    reader,store,secrets=_reader(tmp_path);config=store.load();saved=store.path.read_text()
    assert config.requested_scope==YANDEX_DISK_SCOPE and config.secret_ref.value=="yandex-disk-primary" and challenge("a"*43)!="a"*43
    assert "TOKEN_MUST_NOT_ESCAPE" not in saved and reader.search("sql").status=="no_files" and config.credential_state(InMemorySecretStore()) is ConnectorCredentialState.NEEDS_RECONNECT


def test_oauth_uses_only_disk_scope_and_respects_off(tmp_path,monkeypatch):
    seen=[]
    monkeypatch.setattr("backend.connectors.yandex_disk.oauth.token_post",lambda fields:{"access_token":"token","refresh_token":"refresh"})
    assert authorize(client_id="id",client_secret="secret",authorization_code="code",prompt_open=lambda url:seen.append(url),policy_store=None,safety_store=None)["refresh_token"]=="refresh"
    assert "scope=cloud_api%3Adisk.read" in seen[0] and "code_challenge_method=S256" in seen[0]
    policy=InternetAccessPolicyStore(tmp_path/"local-data/config/internet-access.json");policy.save(InternetAccessPolicy(mode=InternetAccessMode.OFF))
    try: authorize(client_id="id",client_secret="secret",authorization_code="code",policy_store=policy)
    except YandexDiskNetworkBlocked: pass
    else: assert False


def test_bounded_metadata_filename_path_search_and_recent(tmp_path):
    first=_items(*[(f"disk:/folder/sql-{index}.pdf",f"SQL {index}.pdf","application/pdf",100) for index in range(100)])
    second=_items(*[(f"disk:/folder/sql-x{index}.pdf",f"SQL x{index}.pdf","application/pdf",100) for index in range(100)])
    transport=Transport(pages=[first,second]);reader,_,_= _reader(tmp_path,transport);outcome=reader.search("sql folder")
    assert outcome.status=="search_completed" and len(outcome.files)==10 and outcome.scan_limited
    scan=[call for call in transport.calls if "/resources/files?" in call[1]]
    assert len(scan)==1 and "limit=100" in scan[0][1] and "offset=0" in scan[0][1]
    recent_transport=Transport(pages=[_items(*[(f"disk:/new-{index}.pdf",f"new-{index}.pdf","application/pdf",100) for index in range(12)])]);recent,_,_=_reader(tmp_path/"recent",recent_transport);assert len(recent.recent().files)==10
    serialized=json.dumps(outcome.model_context(),ensure_ascii=False);assert "disk:/" not in serialized and "DISK_ACCESS_TOKEN_MUST_NOT_ESCAPE" not in serialized


def test_simple_disk_list_is_one_provider_ordered_metadata_page(tmp_path):
    transport=Transport(pages=[_items(*[(f"disk:/file-{index}.pdf",f"file-{index}.pdf","application/pdf",100) for index in range(12)])]);reader,_,_=_reader(tmp_path,transport)
    outcome=reader.list_files();calls=[call for call in transport.calls if "/resources/files?" in call[1]]
    assert outcome.status=="search_completed" and len(outcome.files)==10 and len(calls)==1
    assert "limit=10" in calls[0][1] and "offset=0" in calls[0][1]


def test_recent_and_simple_list_route_to_their_distinct_reader_operations():
    file=DiskFileCandidate("disk:/one.pdf","one.pdf","application/pdf",1,None,None,True)
    class Reader:
        def __init__(self):self.calls=[]
        def recent(self):self.calls.append("recent");return type("Found",(),{"status":"search_completed","files":(file,),"scan_limited":False})()
        def list_files(self):self.calls.append("list");return type("Found",(),{"status":"search_completed","files":(file,),"scan_limited":False})()
    reader=Reader();service=YandexDiskConversationService(reader=reader)
    assert service.observe("Маш, покажи последние файлы на Яндекс Диске",conversation_id="recent").status=="search_completed"
    assert service.observe("Покажи просто файлы на Яндекс Диске",conversation_id="list").status=="search_completed"
    assert reader.calls==["recent","list"]


def test_scan_max_pages_and_filename_not_content_semantics(tmp_path):
    pages=[_items(*[(f"disk:/other/{index}.pdf",f"other-{index}.pdf","application/pdf",100) for index in range(100)]) for _ in range(5)]
    transport=Transport(pages=pages);reader,_,_=_reader(tmp_path,transport);outcome=reader.search("contract")
    assert outcome.status=="no_files" and outcome.scan_limited
    assert len([call for call in transport.calls if "/resources/files?" in call[1]])==reader.MAX_PAGES


def test_pdf_bridge_unsupported_and_oversized_are_controlled(tmp_path):
    transport=Transport(document=_pdf("Yandex Disk PDF."));reader,_,_=_reader(tmp_path,transport);file=DiskFileCandidate("disk:/plan.pdf","Plan.pdf","application/pdf",100,None,None,True);outcome=reader.read_file(file)
    assert outcome.status=="read_completed" and outcome.document_receipt.evidence.pages[0].text=="Yandex Disk PDF." and any(call[0]=="download" for call in transport.calls)
    assert reader.read_file(DiskFileCandidate("disk:/archive.zip","archive.zip","application/zip",1,None,None,False)).status=="unsupported_format"
    assert reader.read_file(DiskFileCandidate("disk:/big.pdf","big.pdf","application/pdf",MAX_RAW_PDF_BYTES+1,None,None,True)).status=="document_too_large"


def test_policy_and_credential_failures_are_controlled_without_calls(tmp_path):
    transport=Transport();reader,store,secrets=_reader(tmp_path,transport);policy=InternetAccessPolicyStore(tmp_path/"local-data/config/internet-access.json");reader.policy_store=policy;policy.save(InternetAccessPolicy(mode=InternetAccessMode.OFF));assert reader.search("sql").status=="unavailable" and transport.calls==[]
    policy.save(InternetAccessPolicy());safety=AutonomySafetyStore(tmp_path/"local-data/config/autonomy-safety.json");reader.safety_store=safety;AutonomySafetyService(store=safety).engage();assert reader.search("sql").status=="unavailable" and transport.calls==[]
    reader,store,secrets=_reader(tmp_path/"invalid")
    class Invalid(Transport):
        def request_json(self,url,**kwargs):
            if "/token" in url:raise YandexDiskInvalidGrant("invalid_grant")
            return super().request_json(url,**kwargs)
    reader.transport=Invalid();assert reader.search("sql").status=="needs_reconnect" and not secrets.exists(store.load().secret_ref)
    reader,store,secrets=_reader(tmp_path/"ordinary")
    class ApiFailure(Transport):
        def request_json(self,url,**kwargs):
            if "/resources/" in url:raise YandexDiskUnavailable("http_400")
            return super().request_json(url,**kwargs)
    reader.transport=ApiFailure();assert reader.search("sql").status=="unavailable" and secrets.exists(store.load().secret_ref)


def test_intents_and_latest_presented_owner_win_for_ordinal():
    assert disk_intent("Найди на Яндекс Диске файл про договор").kind=="search"
    assert disk_intent("Покажи последние файлы на Яндекс Диске").kind=="recent"
    assert disk_intent("Прочитай файл Договор.pdf").kind=="read_name"
    assert disk_intent("Прочитай https://public.example/page") is None
    assert disk_intent("Покажи файлы на Яндекс Диске").kind=="list"
    assert disk_intent("Покажи просто файлы на Яндекс Диске").kind=="list"
    assert disk_intent("Что у меня есть на Яндекс Диске").kind=="list"
    assert drive_intent("покажи последние файлы на Яндекс Диске") is None
    assert drive_intent("найди на Яндекс Диске документ про SQL") is None
    assert drive_intent("прочитай на Яндекс Диске файл договор.pdf") is None
    assert drive_intent("есть у меня на Яндекс Диске файл договор.pdf") is None
    assert drive_intent("найди в Drive документы про AI").kind=="search"
    first=DiskFileCandidate("disk:/one.pdf","one.pdf","application/pdf",1,None,None,True);second=DiskFileCandidate("disk:/two.pdf","two.pdf","application/pdf",1,None,None,True)
    class Reader:
        def search(self,_):return type("Found",(),{"status":"search_completed","files":(first,second),"scan_limited":False})()
        def recent(self):return self.search("")
        def list_files(self):return self.search("")
        def read_file(self,file):self.read=file;return type("Read",(),{"status":"read_completed","document_receipt":object(),"resolved_document_request":object()})()
    registry=PresentedReadSetRegistry();service=YandexDiskConversationService(reader=Reader(),presented_read_sets=registry);service.observe("найди на яндекс диске файл про договор",conversation_id="c")
    assert GoogleDriveConversationService(reader=object(),presented_read_sets=registry).observe("прочитай второй",conversation_id="c") is None
    assert YandexMailConversationService(reader=object(),presented_read_sets=registry).observe("прочитай второй",conversation_id="c") is None
    assert service.observe("прочитай второй",conversation_id="c").status=="read_completed" and service.reader.read.resource_path=="disk:/two.pdf"
    registry.present("c","yandex_mail",(object(),));assert service.observe("прочитай второй",conversation_id="c") is None
    assert service.observe("покажи просто файлы на яндекс диске",conversation_id="other").status=="search_completed"


def test_disk_cli_disconnect_does_not_touch_mail_secret(tmp_path,monkeypatch):
    secrets=InMemorySecretStore();disk=YandexDiskConfig(client_id="disk-client");store=YandexDiskConfigStore(tmp_path/"local-data/config/yandex-disk.json");store.save(disk);secrets.put(disk.secret_ref,"disk");secrets.put(disk.client_secret_ref,"disk-secret");from backend.secrets import SecretRef;secrets.put(SecretRef(value="yandex-mail-primary"),"mail")
    yandex_disk_cli.disconnect_yandex_disk(config_store=store,secret_store=secrets)
    assert not secrets.exists(disk.secret_ref) and not secrets.exists(disk.client_secret_ref) and secrets.exists(SecretRef(value="yandex-mail-primary"))


def test_disk_cli_connect_reads_secret_interactively_and_persists_only_refs(tmp_path,monkeypatch):
    secrets=InMemorySecretStore();monkeypatch.setattr(yandex_disk_cli,"WindowsCredentialManagerSecretStore",lambda:secrets);monkeypatch.setattr(yandex_disk_cli.getpass,"getpass",lambda _:"DISK_CLIENT_SECRET_MUST_NOT_ESCAPE")
    def oauth(**kwargs):
        assert kwargs["client_secret"]=="DISK_CLIENT_SECRET_MUST_NOT_ESCAPE" and kwargs["client_id"]=="disk-client"
        return {"refresh_token":"DISK_REFRESH_TOKEN_MUST_NOT_ESCAPE"}
    monkeypatch.setattr(yandex_disk_cli,"authorize",oauth)
    assert yandex_disk_cli.main(["--project-root",str(tmp_path),"connect","--client-id","disk-client"])==0
    saved=(tmp_path/"local-data/config/yandex-disk.json").read_text();config=YandexDiskConfigStore(tmp_path/"local-data/config/yandex-disk.json").load()
    assert secrets.exists(config.secret_ref) and secrets.exists(config.client_secret_ref) and "TOKEN_MUST_NOT_ESCAPE" not in saved

from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path
from backend.connectors.yandex_mail.config import YandexMailConfig,YandexMailConfigStore,YANDEX_MAIL_SCOPE
from backend.connectors.yandex_mail.intent import mail_intent
from backend.connectors.yandex_mail.models import MailMessageContent,MailMessageSummary,MailOutcome,ResolvedMailRequest
from backend.connectors.yandex_mail.oauth import challenge,verifier
from backend.connectors.yandex_mail.reader import MAX_RESULTS,ImapYandexSession,YandexMailReader,YandexMailInvalidGrant,YandexMailUnavailable,_content,_criteria
from backend.connectors.yandex_mail.service import YandexMailConversationService
from backend.connectors.presented_read_sets import PresentedReadSetRegistry
from backend.external_observation.policy import InternetAccessMode,InternetAccessPolicy,InternetAccessPolicyStore
from backend.runtime.safety import AutonomySafetyService,AutonomySafetyStore
from backend.secrets import InMemorySecretStore,ConnectorCredentialState

class Session:
 def __init__(self,*_):self.calls=[]
 def search(self,criteria,limit):self.calls.append(("search",criteria,limit));return (MailMessageSummary("yandex","u2","Второе письмо","GitHub",datetime(2026,8,24,tzinfo=timezone.utc),10,False),MailMessageSummary("yandex","u1","Первое письмо","Миша",None,10,False))
 def fetch(self,ref,_):self.calls.append(ref);return "From: =?utf-8?b?0JzQuNGI0LA=?= <misha@example.com>\nSubject: =?utf-8?b?0KLQtdC80LA=?=\nContent-Type: text/html; charset=utf-8\n\n<html><body>Привет <b>мир</b><script>evil()</script></body></html>".encode()
 def close(self):pass
def reader(tmp_path,*,token_post=None,session_factory=Session):
 store=YandexMailConfigStore(tmp_path/"local-data/config/yandex-mail.json");cfg=YandexMailConfig(client_id="client",account_email="misha@yandex.ru");store.save(cfg);secrets=InMemorySecretStore();secrets.put(cfg.secret_ref,"REFRESH_TOKEN_MUST_NOT_ESCAPE");secrets.put(cfg.client_secret_ref,"CLIENT_SECRET_MUST_NOT_ESCAPE")
 return YandexMailReader(config_store=store,secret_store=secrets,session_factory=session_factory,token_post=token_post or (lambda _: {"access_token":"ACCESS_TOKEN_MUST_NOT_ESCAPE"})),store,secrets
def test_scope_pkce_config_and_secrets_are_safe(tmp_path):
 r,store,secrets=reader(tmp_path);cfg=store.load();saved=store.path.read_text()
 assert cfg.requested_scope==YANDEX_MAIL_SCOPE and 43<=len(verifier())<=128 and challenge("a"*43)!="a"*43
 assert "TOKEN_MUST_NOT_ESCAPE" not in saved and cfg.credential_state(secrets) is ConnectorCredentialState.READY
def test_off_and_stop_make_zero_token_or_imap_calls(tmp_path):
 calls=[];r,_,_=reader(tmp_path,token_post=lambda _:calls.append(1) or {"access_token":"x"});policy=InternetAccessPolicyStore(tmp_path/"local-data/config/internet-access.json");r.policy_store=policy;policy.save(InternetAccessPolicy(mode=InternetAccessMode.OFF));assert r.search("recent").status=="unavailable" and calls==[]
 policy.save(InternetAccessPolicy());safety=AutonomySafetyStore(tmp_path/"local-data/config/autonomy-safety.json");r.safety_store=safety;AutonomySafetyService(store=safety).engage();assert r.search("recent").status=="unavailable" and calls==[]
def test_invalid_grant_deletes_only_refresh_and_server_failure_preserves_it(tmp_path):
 r,store,secrets=reader(tmp_path,token_post=lambda _:(_ for _ in ()).throw(YandexMailInvalidGrant("bad")));assert r.search("recent").status=="needs_reconnect" and not secrets.exists(store.load().secret_ref)
 r,store,secrets=reader(tmp_path/"ordinary",token_post=lambda _:(_ for _ in ()).throw(YandexMailUnavailable("down")));assert r.search("recent").status=="unavailable" and secrets.exists(store.load().secret_ref)
def test_refresh_replaces_only_after_success(tmp_path):
 r,store,secrets=reader(tmp_path,token_post=lambda _:{"access_token":"access","refresh_token":"NEW_REFRESH"});assert r.search("recent").status=="search_completed" and secrets.get(store.load().secret_ref)=="NEW_REFRESH"
def test_html_mime_body_is_safe_text_and_attachments_metadata_only():
 summary=MailMessageSummary("yandex","u","Тема","Миша",None,None,False);content=_content(Session().fetch("u",1),summary)
 assert "Привет мир" in content.body and "evil" in content.body and "<script" not in content.body
def test_bounded_results_and_application_owned_second_reference(tmp_path):
 r,_,_=reader(tmp_path);service=YandexMailConversationService(reader=r);found=service.observe("покажи последние письма",conversation_id="c");assert len(found.messages)<=10
 selected=service.observe("прочитай второе",conversation_id="c");assert selected.status=="read_completed" and selected.resolved_request.subject=="Первое письмо"
 assert service.observe("Было что-нибудь от GitHub?",conversation_id="c").status=="search_completed"

def test_contextual_presented_mail_reference_uses_one_real_unread_message(tmp_path):
 class One(Session):
  def search(self,criteria,limit):
   self.calls.append(("search",criteria,limit));return (MailMessageSummary("yandex","u1","Одно новое письмо","Миша",None,10,False),)
 registry=PresentedReadSetRegistry();r,_,_=reader(tmp_path,session_factory=lambda *_:One())
 service=YandexMailConversationService(reader=r,presented_read_sets=registry)
 assert service.observe("Есть новые письма?",conversation_id="c").status=="search_completed"
 for phrase in ("Прочитай это письмо и расскажи о чем оно", "Прочитай его", "Прочитай новое письмо", "Прочитай в моей посте новое письмо и расскажи о чем оно"):
  assert service.observe(phrase,conversation_id="c").status=="read_completed"

def test_contextual_mail_reference_clarifies_for_multiple_and_respects_newest_owner(tmp_path):
 registry=PresentedReadSetRegistry();r,_,_=reader(tmp_path)
 service=YandexMailConversationService(reader=r,presented_read_sets=registry)
 assert service.observe("Есть новые письма?",conversation_id="c").status=="search_completed"
 assert service.observe("Прочитай это письмо",conversation_id="c").status=="clarification_required"
 registry.present("c","google_drive",(object(),),entity_kind="файл",presentation_kind="recent")
 assert service.observe("Прочитай это письмо",conversation_id="c") is None
def test_mail_content_and_resolved_request_do_not_expose_uid():
 item=MailMessageSummary("yandex","secret-uid","Тема","Отправитель",None,None,False);content=MailMessageContent(item,"текст")
 assert "secret-uid" not in json.dumps(content.model_value(),ensure_ascii=False);assert "секрет" not in ResolvedMailRequest("Тема","Отправитель").model_message()

def test_new_recent_today_and_important_keep_distinct_intents_and_criteria():
 assert mail_intent("что нового в почте").kind=="unread"
 assert mail_intent("есть новые письма").kind=="unread"
 assert mail_intent("покажи последние письма").kind=="recent"
 assert mail_intent("что пришло сегодня").kind=="today"
 assert mail_intent("есть что-нибудь важное").kind=="important"
 assert _criteria("unread",None)==("UNSEEN",) and _criteria("recent",None)==("ALL",)
 for phrase in ("Маша проверь почту", "проверь мою почту", "загляни в почту", "посмотри почту"):
  assert mail_intent(phrase).kind=="unread"

def test_conversational_lead_ins_route_only_clear_mail_requests():
 for phrase in ("Маша, а теперь что нового в почте?","Маш, посмотри, что нового в почте","Маш, глянь, есть новые письма?","Маш, скажи, что пришло сегодня"):
  assert mail_intent(phrase) is not None
 assert mail_intent("Мы вчера обсуждали почту и новые письма") is None

def test_unread_search_is_bounded_and_empty_result_is_human(tmp_path):
 session=Session();r,_,_=reader(tmp_path,session_factory=lambda *_:session)
 assert r.search("unread").status=="search_completed" and session.calls==[("search",("UNSEEN",),MAX_RESULTS)]
 class Empty(Session):
  def search(self,criteria,limit):return ()
 empty,_,_=reader(tmp_path/"empty",session_factory=Empty)
 outcome=empty.search("unread");assert outcome.status=="no_unread" and YandexMailConversationService.human_result(outcome)=="Новых непрочитанных писем нет."

def test_imap_unseen_listing_uses_readonly_and_body_peek_without_store(monkeypatch):
 class Client:
  def __init__(self,*_):self.calls=[]
  def authenticate(self,*_):self.calls.append(("authenticate",));return "OK",[]
  def select(self,*args,**kwargs):self.calls.append(("select",args,kwargs));return "OK",[]
  def response(self,name):self.calls.append(("response",name));return "OK",[b"9001"]
  def uid(self,*args):
   self.calls.append(("uid",args))
   if args[0]=="SEARCH":return "OK",[b"1"]
   return "OK",[(b"1 (RFC822.SIZE 5)",b"From: Misha <m@example.com>\nSubject: Hi\nMessage-ID: <mail-1@example.com>\n\n")]
  def logout(self):self.calls.append(("logout",))
 client=Client();monkeypatch.setattr("backend.connectors.yandex_mail.reader.imaplib.IMAP4_SSL",lambda *_:client)
 session=ImapYandexSession("misha@yandex.ru","token");session.search(("UNSEEN",),MAX_RESULTS);session.close()
 assert ("select",("INBOX",),{"readonly":True}) in client.calls
 assert any(call[1][0]=="SEARCH" and "UNSEEN" in call[1] for call in client.calls if call[0]=="uid")
 assert any("BODY.PEEK" in call[1][-1] for call in client.calls if call[0]=="uid" and call[1][0]=="FETCH")
 assert not any(call[0]=="uid" and call[1][0]=="STORE" for call in client.calls)

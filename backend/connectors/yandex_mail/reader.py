"""Bounded Yandex OAuth refresh and strictly read-only IMAP evidence."""
from __future__ import annotations
import base64, email, imaplib, json, re
from datetime import datetime, timezone
from email.header import decode_header, make_header
from email.utils import parseaddr, parsedate_to_datetime
from html.parser import HTMLParser
from typing import Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from .config import YandexMailConfigStore
from .models import MailMessageContent, MailMessageSummary, MailOutcome, ResolvedMailRequest
from .network import YandexMailNetworkBlocked, assert_yandex_mail_network_allowed

MAX_RESULTS=10; MAX_RAW_MESSAGE_BYTES=1024*1024; MAX_BODY_CHARS=8000
class YandexMailUnavailable(RuntimeError): pass
class YandexMailInvalidGrant(RuntimeError): pass
class YandexMailTooLarge(RuntimeError): pass
class MailSession(Protocol):
 def search(self, criteria: tuple[str,...], limit:int)->tuple[MailMessageSummary,...]:...
 def fetch(self, reference:str, maximum_bytes:int)->bytes:...
 def close(self)->None:...

class _Text(HTMLParser):
 def __init__(self): super().__init__(); self.rows=[]
 def handle_data(self,data): self.rows.append(data)
 def text(self): return " ".join(" ".join(self.rows).split())

class ImapYandexSession:
 def __init__(self,email_address,access_token):
  self.client=imaplib.IMAP4_SSL("imap.yandex.com",993); payload=f"user={email_address}\x01auth=Bearer {access_token}\x01\x01".encode(); self.client.authenticate("XOAUTH2",lambda _:payload); typ,_=self.client.select("INBOX",readonly=True)
  if typ!="OK": raise YandexMailUnavailable("mailbox_unavailable")
 def search(self,criteria,limit):
  typ,data=self.client.uid("SEARCH",None,*criteria)
  if typ!="OK": raise YandexMailUnavailable("mail_search_unavailable")
  ids=data[0].split()[-limit:][::-1]; rows=[]
  for raw in ids:
   uid=raw.decode(); typ,data=self.client.uid("FETCH",uid,"(BODY.PEEK[HEADER.FIELDS (SUBJECT FROM DATE)] RFC822.SIZE BODYSTRUCTURE)")
   if typ=="OK" and data: rows.append(_summary(uid,data))
  return tuple(rows)
 def fetch(self,reference,maximum_bytes):
  typ,data=self.client.uid("FETCH",reference,"(RFC822.SIZE BODY.PEEK[])")
  if typ!="OK" or not data: raise YandexMailUnavailable("mail_fetch_unavailable")
  raw=next((x[1] for x in data if isinstance(x,tuple) and isinstance(x[1],bytes)),b"")
  if len(raw)>maximum_bytes: raise YandexMailTooLarge("message_too_large")
  return raw
 def close(self):
  try:self.client.logout()
  except Exception:pass

class YandexMailReader:
 def __init__(self,*,config_store,secret_store,session_factory=None,policy_store=None,safety_store=None,token_post=None): self.config_store=config_store;self.secret_store=secret_store;self.session_factory=session_factory or ImapYandexSession;self.policy_store=policy_store;self.safety_store=safety_store;self.token_post=token_post or _token_post
 def search(self,kind,query=None):
  config,token,outcome=self._token()
  if outcome:return outcome
  try:
   session=self._session(config.account_email,token); rows=session.search(_criteria(kind,query),MAX_RESULTS); session.close(); return MailOutcome(("no_unread" if kind=="unread" else "no_messages") if not rows else ("important_completed" if kind=="important" else "search_completed"),rows)
  except (YandexMailUnavailable,YandexMailNetworkBlocked,imaplib.IMAP4.error,OSError):return MailOutcome("unavailable")
 def read(self,item):
  config,token,outcome=self._token()
  if outcome:return outcome
  try:
   session=self._session(config.account_email,token); raw=session.fetch(item.message_ref,MAX_RAW_MESSAGE_BYTES);session.close(); content=_content(raw,item);return MailOutcome("read_completed",content=content,resolved_request=ResolvedMailRequest(item.subject,item.sender))
  except YandexMailTooLarge:return MailOutcome("message_too_large")
  except (YandexMailUnavailable,YandexMailNetworkBlocked,imaplib.IMAP4.error,OSError):return MailOutcome("unavailable")
 def _session(self,email_address,token): assert_yandex_mail_network_allowed(policy_store=self.policy_store,safety_store=self.safety_store);return self.session_factory(email_address,token)
 def _token(self):
  config=self.config_store.load()
  if config is None:return None,None,MailOutcome("disconnected")
  refresh=self.secret_store.get(config.secret_ref);secret=self.secret_store.get(config.client_secret_ref)
  if not refresh or not secret:return None,None,MailOutcome("needs_reconnect")
  try:
   assert_yandex_mail_network_allowed(policy_store=self.policy_store,safety_store=self.safety_store); payload=self.token_post({"grant_type":"refresh_token","refresh_token":refresh,"client_id":config.client_id,"client_secret":secret})
  except YandexMailInvalidGrant:self.secret_store.delete(config.secret_ref);return None,None,MailOutcome("needs_reconnect")
  except (YandexMailUnavailable,YandexMailNetworkBlocked):return None,None,MailOutcome("unavailable")
  token=payload.get("access_token")
  if not isinstance(token,str) or not token:return None,None,MailOutcome("needs_reconnect")
  replacement=payload.get("refresh_token")
  if isinstance(replacement,str) and replacement:self.secret_store.put(config.secret_ref,replacement)
  return config,token,None

def _token_post(fields):
 request=Request("https://oauth.yandex.ru/token",data=urlencode(fields).encode(),headers={"Content-Type":"application/x-www-form-urlencoded"},method="POST")
 try:
  with urlopen(request,timeout=15) as response: raw=response.read(1024*1024+1)
 except HTTPError as error:
  try: invalid=json.loads(error.read(8192)).get("error")=="invalid_grant"
  except Exception: invalid=False
  if invalid:raise YandexMailInvalidGrant("reconnect_required")
  raise YandexMailUnavailable("oauth_unavailable") from error
 except (URLError,OSError) as error:raise YandexMailUnavailable("oauth_unavailable") from error
 try:return json.loads(raw)
 except Exception as error:raise YandexMailUnavailable("oauth_invalid") from error
def _criteria(kind,q):
 if kind=="unread":return("UNSEEN",)
 if kind=="today":return("SINCE",datetime.now().strftime("%d-%b-%Y"))
 if kind=="sender":return("FROM",q)
 if kind=="topic":return("SUBJECT",q)
 return("ALL",)
def _decode(value):
 try:return str(make_header(decode_header(value or "")))[:300]
 except Exception:return ""
def _summary(uid,data):
 raw=next((x[1] for x in data if isinstance(x,tuple) and isinstance(x[1],bytes)),b""); msg=email.message_from_bytes(raw); name,address=parseaddr(_decode(msg.get("From",""))); sender=(name or address or "Неизвестный отправитель")[:300]
 try:received=parsedate_to_datetime(msg.get("Date"));received=received.astimezone(timezone.utc) if received else None
 except Exception:received=None
 size_match=re.search(rb"RFC822\.SIZE (\d+)",b" ".join(x[0] for x in data if isinstance(x,tuple) and isinstance(x[0],bytes))); size=int(size_match.group(1)) if size_match else None
 return MailMessageSummary("yandex",uid,_decode(msg.get("Subject")) or "Без темы",sender,received,size,False)
def _content(raw,summary):
 msg=email.message_from_bytes(raw); plain=None;html=None;attachments=[]
 for part in msg.walk():
  disposition=part.get_content_disposition();ctype=part.get_content_type();name=part.get_filename()
  if disposition=="attachment": attachments.append({"filename":_decode(name) or "вложение","content_type":ctype});continue
  if ctype in {"text/plain","text/html"} and disposition!="attachment":
   try:text=part.get_payload(decode=True).decode(part.get_content_charset() or "utf-8",errors="replace")
   except Exception:continue
   if ctype=="text/plain" and plain is None:plain=text
   elif ctype=="text/html" and html is None:html=text
 body=plain if plain is not None else _html_text(html or "")
 body=" ".join(body.split())[:MAX_BODY_CHARS]
 if not body: raise YandexMailUnavailable("mail_unreadable")
 return MailMessageContent(summary,body,tuple(attachments[:20]))
def _html_text(value): parser=_Text();parser.feed(value);return parser.text()

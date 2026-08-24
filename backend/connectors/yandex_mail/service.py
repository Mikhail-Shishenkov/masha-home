from .intent import mail_intent
from .models import MailOutcome
class YandexMailConversationService:
 def __init__(self,*,reader,presented_read_sets=None):self.reader=reader;self._presented={};self.presented_read_sets=presented_read_sets
 def _rows(self,conversation_id):
  if self.presented_read_sets is not None:
   return self.presented_read_sets.items_for(conversation_id,"yandex_mail")
  return self._presented.get(conversation_id,())
 def _present(self,conversation_id,rows):
  self._presented[conversation_id]=rows
  if self.presented_read_sets is not None:self.presented_read_sets.present(conversation_id,"yandex_mail",rows)
 def observe(self,message,*,conversation_id):
  intent=mail_intent(message)
  if intent is None:return None
  if intent.kind=="read_ordinal":
   rows=self._rows(conversation_id); index=(intent.ordinal or 0)-1
   if rows is None:return None
   return MailOutcome("clarification_required") if index<0 or index>=len(rows) else self.reader.read(rows[index])
  if intent.kind=="read_name":
   rows=self._rows(conversation_id)
   if rows is None:return None
   matches=[x for x in rows if x.subject.casefold()==intent.query.casefold()]
   return self.reader.read(matches[0]) if len(matches)==1 else MailOutcome("clarification_required")
  outcome=self.reader.search(intent.kind,intent.query)
  if outcome.status=="search_completed":self._present(conversation_id,outcome.messages)
  return outcome
 @staticmethod
 def human_result(outcome):
  if outcome.status=="search_completed":return "Нашла в Яндекс Почте:\n"+"\n".join(f"{i}. {x.subject} — {x.sender}" for i,x in enumerate(outcome.messages,1))
  return {"disconnected":"Яндекс Почта не подключена.","needs_reconnect":"Нужно переподключить Яндекс Почту.","unavailable":"Сейчас не удалось обратиться к почте.","no_unread":"Новых непрочитанных писем нет.","no_messages":"Писем по этому запросу не нашла.","message_too_large":"Это письмо слишком большое для безопасного чтения.","clarification_required":"Уточни, какое именно письмо прочитать."}.get(outcome.status,"Не смогла разобрать содержимое этого письма.")

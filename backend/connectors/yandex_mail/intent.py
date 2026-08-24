from __future__ import annotations
import re
from dataclasses import dataclass
from backend.connectors.provider_language import normalize_command_prefix
_ORD={"первое":1,"первый":1,"второе":2,"второй":2,"третье":3,"третий":3}
@dataclass(frozen=True)
class MailIntent: kind:str; query:str|None=None; ordinal:int|None=None

def _request_text(message:str)->str:
    text=" ".join(re.sub(r"[^\w\s@.'-]", " ", message.casefold().replace("ё","е")).split())
    prefix=r"^(?:маш(?:а|енька)? )?(?:(?:а )?теперь )?(?:(?:посмотри|глянь|скажи) )?"
    return re.sub(prefix,"",text,count=1)

def mail_intent(message:str):
    normalized=normalize_command_prefix(message, token_limit=2)
    if re.fullmatch(r"(?:маш(?:а|енька)? )?(?:проверь (?:мою )?почту|загляни в почту|посмотри почту)",normalized): return MailIntent("unread")
    text=_request_text(normalized)
    if re.fullmatch(r"(?:маш(?:а|енька)? )?прочитай (?:письмо )?(первое|первый|второе|второй|третье|третий)",text):
        return MailIntent("read_ordinal",ordinal=_ORD[text.split()[-1]])
    if re.fullmatch(r"(?:что важн\w* пришло(?: сегодня)?|есть что(?:\s|-)+нибудь важное)",text): return MailIntent("important")
    if re.fullmatch(r"(?:что нового в почте|есть новые письма|что нового пришло|покажи новые письма)",text): return MailIntent("unread")
    if re.fullmatch(r"(?:покажи последние письма|какие последние письма)",text): return MailIntent("recent")
    if re.fullmatch(r"что пришло сегодня",text): return MailIntent("today")
    match=re.match(r"^(?:маш(?:а|енька)? )?(?:найди|есть) письм\w* от (.+)$",text)
    if match:return MailIntent("sender",match.group(1)[:200])
    match=re.match(r"^(?:маш(?:а|енька)? )?было что(?:\s|-)+нибудь от (.+)$",text)
    if match:return MailIntent("sender",match.group(1)[:200])
    match=re.match(r"^(?:маш(?:а|енька)? )?найди письм\w* (?:про|о) (.+)$",text)
    if match:return MailIntent("topic",match.group(1)[:200])
    match=re.match(r"^(?:маш(?:а|енька)? )?(?:прочитай письмо|что написано в письме) (.+)$",text)
    if match:return MailIntent("read_name",match.group(1)[:300])
    return None

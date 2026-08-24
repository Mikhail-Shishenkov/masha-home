from __future__ import annotations
import re
from dataclasses import dataclass
_ORD={"первое":1,"первый":1,"второе":2,"второй":2,"третье":3,"третий":3}
@dataclass(frozen=True)
class MailIntent: kind:str; query:str|None=None; ordinal:int|None=None
def mail_intent(message:str):
    text=" ".join(re.sub(r"[^\w\s@.'-]", " ", message.casefold().replace("ё","е")).split())
    if re.fullmatch(r"(?:маш(?:а|енька)? )?прочитай (?:письмо )?(первое|первый|второе|второй|третье|третий)",text):
        return MailIntent("read_ordinal",ordinal=_ORD[text.split()[-1]])
    if re.search(r"\b(?:что нового в почте|покажи последние письма|что пришло сегодня|важн\w* пришло сегодня|есть что нибудь важное)\b",text): return MailIntent("important" if "важн" in text else ("today" if "сегодня" in text else "recent"))
    match=re.match(r"^(?:маш(?:а|енька)? )?(?:найди|есть) письм\w* от (.+)$",text)
    if match:return MailIntent("sender",match.group(1)[:200])
    match=re.match(r"^(?:маш(?:а|енька)? )?было что(?:\s|-)+нибудь от (.+)$",text)
    if match:return MailIntent("sender",match.group(1)[:200])
    match=re.match(r"^(?:маш(?:а|енька)? )?найди письм\w* (?:про|о) (.+)$",text)
    if match:return MailIntent("topic",match.group(1)[:200])
    match=re.match(r"^(?:маш(?:а|енька)? )?(?:прочитай письмо|что написано в письме) (.+)$",text)
    if match:return MailIntent("read_name",match.group(1)[:300])
    return None

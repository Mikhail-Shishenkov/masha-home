"""Trust boundary for model-authored conversational responses.

The model can phrase a response, but only the application can attest that a
state change happened. Ordinary model turns carry no application receipt, so
mutation-success language is rejected before it enters conversation history.
"""

from __future__ import annotations

import hashlib
import re
from collections import deque
from datetime import datetime, timezone

from backend.memory.text_normalization import meaningful_tokens


_FIRST_PERSON_MUTATION = re.compile(
    r"(?:^|[.!?]\s+)(?:я\s+)?(?:"
    r"сохран(?:ил|ила|или|ено)|запис(?:ал|ала|али|ано)|добав(?:ил|ила|или|лено)|"
    r"созда(?:л|ла|ли|но)|измен(?:ил|ила|или|ено)|обнов(?:ил|ила|или|лено)|"
    r"заб(?:ыл|ыла|ыли)|удал(?:ил|ила|или|ено)|скр(?:ыл|ыла|ыли|ыто)|"
    r"заверш(?:ил|ила|или|ено)|закр(?:ыл|ыла|ыли|ыто)|"
    r"выполн(?:ил|ила|или|ено)|отправ(?:ил|ила|или|лено)|"
    r"постав(?:ил|ила|или|лено)|перен(?:ес|есла|если|есено)"
    r")\b",
    re.IGNORECASE,
)
_RESULT_STATE_CLAIM = re.compile(
    r"\b(?:дело|задач[аиу]?|обязательство|напоминание|запись|память|событие)\b"
    r".{0,80}\b(?:создан[ао]?|добавлен[ао]?|сохранен[ао]?|записан[ао]?|"
    r"изменен[ао]?|обновлен[ао]?|удален[ао]?|скрыт[ао]?|завершен[ао]?|"
    r"выполнен[ао]?|отправлен[ао]?)\b",
    re.IGNORECASE | re.DOTALL,
)
_ENGLISH_MUTATION = re.compile(
    r"(?:^|[.!?]\s+)(?:i(?:'ve| have)?\s+)?(?:saved|added|created|updated|"
    r"changed|forgot|deleted|completed|sent)\b",
    re.IGNORECASE,
)
_SUCCESS_MUTATION_SEQUENCE = re.compile(
    r"\b(?:готово|сделано|успешно|уже|вс[её])\b.{0,80}\b(?:"
    r"сохран\w*|запис\w*|добав\w*|созда\w*|измен\w*|обнов\w*|"
    r"заб(?:ыл|ыла|ыли|ыто)|удал\w*|скр\w*|заверш\w*|закр\w*|выполн\w*|отправ\w*"
    r")\b",
    re.IGNORECASE | re.DOTALL,
)
# Finite present, past and near-future forms are claims of execution just as
# much as a completed-result sentence.  Keep this separate from infinitives:
# "думаю, стоит удалить" is discussion, while "эту нить удаляю" is an
# unreceipted claim that an application-owned change is taking place.
_EXECUTION_MUTATION_FORM = re.compile(
    r"\b(?:"
    r"сохран(?:я(?:ю|ешь|ет|ем|ете|ют)|ю|ишь|ит|им|ите|ят|ил(?:а|и)?|ено)|"
    r"запис(?:ыва(?:ю|ешь|ет|ем|ете|ют)|ываю|ываешь|ывают|ал(?:а|и)?|ано)|"
    r"добав(?:ля(?:ю|ешь|ет|ем|ете|ют)|лю|ишь|ит|им|ите|ят|ил(?:а|и)?|лено)|"
    r"созда(?:ю|ешь|ет|ем|ете|ют|м|дите|дут|л(?:а|и)?|но)|"
    r"измен(?:я(?:ю|ешь|ет|ем|ете|ют)|ю|ишь|ит|им|ите|ят|ил(?:а|и)?|ено)|"
    r"обнов(?:ля(?:ю|ешь|ет|ем|ете|ют)|лю|ишь|ит|им|ите|ят|ил(?:а|и)?|лено)|"
    r"удал(?:я(?:ю|ешь|ет|ем|ете|ют)|ю|ишь|ит|им|ите|ят|ил(?:а|и)?|ено)|"
    r"убира(?:ю|ешь|ет|ем|ете|ют)|убер(?:у|ешь|ет|ем|ете|ут)|убрал(?:а|и)?|убрано|"
    r"скрыва(?:ю|ешь|ет|ем|ете|ют)|скро(?:ю|ешь|ет|ем|ете|ют)|скрыл(?:а|и)?|"
    r"заверша(?:ю|ешь|ет|ем|ете|ют)|заверш(?:у|ишь|ит|им|ите|ат|ил(?:а|и)?|ено)|"
    r"закрыва(?:ю|ешь|ет|ем|ете|ют)|закро(?:ю|ешь|ет|ем|ете|ют)|закрыл(?:а|и)?|"
    r"выполня(?:ю|ешь|ет|ем|ете|ют)|выполн(?:ю|ишь|ит|им|ите|ят|ил(?:а|и)?|ено)|"
    r"отправля(?:ю|ешь|ет|ем|ете|ют)|отправ(?:лю|ишь|ит|им|ите|ят|ил(?:а|и)?|лено)|"
    r"поменя(?:ю|ешь|ет|ем|ете|ют|л(?:а|и)?)"
    r")\b",
    re.IGNORECASE,
)

UNRECEIPTED_MUTATION_RESPONSE = (
    "Я не могу подтвердить это действие: в этом сообщении Дом ничего не менял. "
    "Могу обсудить это или подготовить отдельное предложение для твоего подтверждения."
)

_GUARD_PATTERNS = (
    ("first_person_mutation", _FIRST_PERSON_MUTATION),
    ("result_state_claim", _RESULT_STATE_CLAIM),
    ("english_mutation", _ENGLISH_MUTATION),
    ("success_mutation_sequence", _SUCCESS_MUTATION_SEQUENCE),
    ("execution_mutation_form", _EXECUTION_MUTATION_FORM),
)
_APPLICATION_STATE_NOUN = re.compile(
    r"\b(?:дело|задач\w*|обязательств\w*|напоминан\w*|запис\w*|памят\w*|"
    r"событи\w*|нить|нити|тему|темы|приложени\w*|календар\w*)\b",
    re.IGNORECASE,
)
_BLOCKED_DIAGNOSTICS: deque[dict[str, str | int]] = deque(maxlen=100)


def response_guard_diagnostics() -> tuple[dict[str, str | int], ...]:
    """Return content-free local diagnostics for support/status boundaries."""
    return tuple(dict(item) for item in _BLOCKED_DIAGNOSTICS)


def _sentence_for_match(text: str, match: re.Match[str]) -> str:
    start = max(text.rfind(".", 0, match.start()), text.rfind("!", 0, match.start()), text.rfind("?", 0, match.start()))
    ends = [position for mark in ".!?" if (position := text.find(mark, match.end())) >= 0]
    end = min(ends) if ends else len(text)
    return text[start + 1 : end]


def _is_application_claim(rule: str, text: str, match: re.Match[str]) -> bool:
    if rule == "english_mutation":
        return True
    # Russian change language is authoritative only when its sentence names
    # application-owned state. This keeps ordinary descriptions such as
    # "яркость изменяется" and "я изменила мнение" conversational.
    sentence = _sentence_for_match(text, match)
    if _APPLICATION_STATE_NOUN.search(sentence):
        return True
    return (
        rule in {"first_person_mutation", "execution_mutation_form"}
        and re.search(r"\bя\b.{0,48}\b(?:это|его|ее|её)\b", sentence, re.IGNORECASE) is not None
    )


def _is_grounded_completed_readout(
    rule: str,
    text: str,
    match: re.Match[str],
    grounded_completed_items: tuple[str, ...],
) -> bool:
    """Allow a read-only report of an actually supplied completed task."""
    if rule not in {
        "result_state_claim",
        "success_mutation_sequence",
        "execution_mutation_form",
    }:
        return False
    sentence = _sentence_for_match(text, match)
    if re.search(r"\b(?:завершен\w*|выполнен\w*)\b", sentence, re.IGNORECASE) is None:
        return False
    sentence_tokens = set(meaningful_tokens(sentence))
    for content in grounded_completed_items:
        content_tokens = set(meaningful_tokens(content))
        distinctive = {
            token for token in content_tokens
            if token not in {"заверш", "завершен", "выполн", "выполнен", "статус"}
        }
        if distinctive & sentence_tokens:
            return True
    return False


def render_model_response(
    text: str,
    *,
    application_receipts: tuple[str, ...] = (),
    grounded_completed_items: tuple[str, ...] = (),
) -> str:
    """Return mutation-success wording only when the application issued a receipt.

    The receipt allowlist is structural. Lexical detection is a final output
    guard, not the authority that decides whether a mutation happened.
    """
    if application_receipts:
        return text
    for rule, pattern in _GUARD_PATTERNS:
        match = pattern.search(text)
        if (
            match
            and not _is_grounded_completed_readout(
                rule,
                text,
                match,
                grounded_completed_items,
            )
            and _is_application_claim(rule, text, match)
        ):
            _BLOCKED_DIAGNOSTICS.append({
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "rule": rule,
                "character_count": len(text),
                "content_digest": hashlib.sha256(text.encode("utf-8")).hexdigest()[:16],
            })
            return UNRECEIPTED_MUTATION_RESPONSE
    return text

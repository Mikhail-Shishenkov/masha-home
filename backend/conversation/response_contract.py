"""Trust boundary for model-authored conversational responses.

The model can phrase a response, but only the application can attest that a
state change happened. Ordinary model turns carry no application receipt, so
mutation-success language is rejected before it enters conversation history.
"""

from __future__ import annotations

import re


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
    r"заб\w*|удал\w*|скр\w*|заверш\w*|закр\w*|выполн\w*|отправ\w*"
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


def render_model_response(text: str, *, application_receipts: tuple[str, ...] = ()) -> str:
    """Return mutation-success wording only when the application issued a receipt.

    The receipt allowlist is structural. Lexical detection is a final output
    guard, not the authority that decides whether a mutation happened.
    """
    if application_receipts:
        return text
    if any(pattern.search(text) for pattern in (
        _FIRST_PERSON_MUTATION,
        _RESULT_STATE_CLAIM,
        _ENGLISH_MUTATION,
        _SUCCESS_MUTATION_SEQUENCE,
        _EXECUTION_MUTATION_FORM,
    )):
        return UNRECEIPTED_MUTATION_RESPONSE
    return text

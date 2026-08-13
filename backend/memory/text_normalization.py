"""Small deterministic Russian-aware text normalization shared by memory paths."""

from __future__ import annotations

import re


_SPACE = re.compile(r"\s+")
_PUNCTUATION = re.compile(r"[^\w\s'-]+", re.UNICODE)

# These are conversational glue or very broad nouns.  Removing them prevents
# words such as "тема", "дело", "Маша" and "сегодня" from dominating memory
# ranking while preserving the subject words that carry the user's meaning.
_STOP_WORDS = {
    "а", "без", "бы", "был", "была", "были", "было", "в", "вам", "вас",
    "все", "вот", "где", "да", "для", "до", "его", "ее", "ей", "ему",
    "если", "есть", "еще", "же", "за", "и", "из", "или", "им", "их",
    "к", "как", "какая", "какие", "какой", "когда", "которая", "который",
    "ли", "маша", "маш", "мне", "мой", "моя", "мои", "мы", "на", "над",
    "нам", "нами", "нас", "насчет", "не", "нее", "ней", "нет", "но", "ну", "о",
    "об", "она", "они", "оно", "от", "по", "под", "помнишь", "помнить",
    "помню", "про", "с", "сама", "сам", "сейчас", "сегодня", "так", "та", "такая",
    "такой", "там", "тебе", "тебя", "тема", "тему", "то", "тот", "ты", "у", "уже",
    "что", "эта", "эти", "это", "этой", "этом", "этот", "я", "дело", "дела",
    "нить", "нити",
}


def normalize_search_text(value: str) -> str:
    """Normalize text without treating IDs or punctuation as meaning."""
    text = value.casefold().replace("ё", "е").replace("_", " ").replace("-", " ")
    text = _PUNCTUATION.sub(" ", text)
    return _SPACE.sub(" ", text).strip()


def stem_russian_token(token: str) -> str:
    """Conservative suffix stemmer derived from the existing memory matcher."""
    if not token or token.isdigit():
        return token
    suffixes = (
        "иями", "ениями", "ение", "ения", "ений", "ении", "остью", "ости",
        "ями", "ами", "ого", "его", "ему", "ому", "ыми", "ими", "аться",
        "яться", "ались", "ялись", "ется", "ются", "ится", "или", "ыли", "али", "яли", "ить", "ыть",
        "ать", "ешь", "ишь", "ете", "ите", "ет", "ит", "ют", "ут",
        "ят", "ат", "кой", "ская", "ский", "ские", "ских", "ую", "юю",
        "ая", "яя", "ое", "ее", "ые", "ие", "ых", "их", "ой", "ей",
        "ов", "ев", "ах", "ях", "ом", "ем", "ам", "ям", "ию", "ью",
        "ия", "ья", "ии", "ку", "ка", "ы", "и", "а", "я", "о", "у",
        "ю", "е", "ь",
    )
    for suffix in suffixes:
        if token.endswith(suffix) and len(token) - len(suffix) >= 3:
            return token[: -len(suffix)]
    return token


def meaningful_tokens(value: str) -> tuple[str, ...]:
    tokens: list[str] = []
    for token in normalize_search_text(value).split():
        if len(token) <= 1 or token in _STOP_WORDS:
            continue
        stem = stem_russian_token(token)
        if len(stem) > 1:
            tokens.append(stem)
    return tuple(tokens)

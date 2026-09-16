"""Clock normalization of literal evidence, never intent/action selection."""
import re


_HOURS = {
    "ноль": 0, "час": 1, "один": 1, "одна": 1, "два": 2, "две": 2,
    "три": 3, "четыре": 4, "пять": 5, "шесть": 6, "семь": 7,
    "восемь": 8, "девять": 9, "десять": 10, "одиннадцать": 11,
    "двенадцать": 12, "тринадцать": 13, "четырнадцать": 14,
    "пятнадцать": 15, "шестнадцать": 16, "семнадцать": 17,
    "восемнадцать": 18, "девятнадцать": 19, "двадцать": 20,
    "двадцать один": 21, "двадцать два": 22, "двадцать три": 23,
}
_CLOCK = re.compile(
    r"(?:(?P<prefix>в|на|с)\s+)?(?P<hour>\d{1,2}|"
    + "|".join(sorted(_HOURS, key=len, reverse=True))
    + r")(?::(?P<minute>\d{2}))?(?P<unit>\s+час(?:а|ов)?)?"
    r"(?:\s+(?P<period>утра|дня|вечера|ночи))?"
)


def _normalize(text: str) -> str:
    return " ".join(text.casefold().replace("ё", "е").split()).strip(" .!?\n")


def resolve_clock_evidence(utterance: str, evidence: str) -> str | None:
    """Require a whole clock expression, including its relation/period.

    A substring inside a duration cannot become a clock by losing its preposition.
    Multiple occurrences with differing surrounding semantics require clarification.
    """
    text, quote = _normalize(utterance), _normalize(evidence)
    match = _CLOCK.fullmatch(quote)
    if match is None:
        return None
    occurrences = tuple(re.finditer(r"(?<!\w)" + re.escape(quote) + r"(?!\w)", text))
    if not occurrences:
        return None
    for occurrence in occurrences:
        before, after = text[:occurrence.start()], text[occurrence.end():]
        if re.search(r"\b(?:за|через)\s*$", before):
            return None
        if re.search(r"\bна\s*$", before) and not match.group("period") and (
            match.group("unit") or match.group("hour") == "час"
            or re.match(r"\s+час(?:а|ов)?\b", after)
        ):
            return None
        if re.match(r"\s+(?:до|после|раньше|позже|утра|дня|вечера|ночи)\b", after):
            return None
    if match.group("prefix") == "на" and not match.group("period") and (
        match.group("unit") or match.group("hour") == "час"
    ):
        return None
    hour_text = match.group("hour")
    hour = int(hour_text) if hour_text.isdigit() else _HOURS[hour_text]
    minute = int(match.group("minute") or 0)
    period = match.group("period")
    if period in {"дня", "вечера"} and 1 <= hour <= 11:
        hour += 12
    elif period == "ночи":
        if hour == 12:
            hour = 0
        elif 6 <= hour <= 11:
            hour += 12
    if hour > 23 or minute > 59:
        return None
    return f"{hour:02d}:{minute:02d}"

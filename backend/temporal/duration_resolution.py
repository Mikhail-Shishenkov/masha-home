"""Home-owned normalization of duration evidence after intent grounding."""

from __future__ import annotations

import re
from dataclasses import dataclass

from backend.memory.text_normalization import normalize_search_text


_NUMBER_WORDS = {
    "один": 1,
    "одна": 1,
    "одну": 1,
    "два": 2,
    "две": 2,
    "три": 3,
    "четыре": 4,
    "пять": 5,
    "шесть": 6,
    "семь": 7,
    "восемь": 8,
    "девять": 9,
    "десять": 10,
    "одиннадцать": 11,
    "двенадцать": 12,
}
_NUMBER = "|".join((*_NUMBER_WORDS, r"\d{1,3}"))
_DURATION = re.compile(
    rf"(?P<count>{_NUMBER})?\s*"
    r"(?P<unit>час(?:а|ов)?|минут(?:у|ы)?|минут)\b",
)
_EMBEDDED_DURATION = re.compile(
    rf"\bна\s+(?P<count>{_NUMBER})?\s*"
    r"(?P<unit>час(?:а|ов)?|минут(?:у|ы)?|минут)\b"
    r"(?!\s+(?:дня|утра|вечера|ночи)\b)",
)
_BARE_NUMBER = re.compile(rf"^(?P<count>{_NUMBER})$")


@dataclass(frozen=True)
class DurationResolution:
    minutes: int | None
    amount: int | None
    ambiguous_unit: bool = False

    @property
    def canonical(self) -> str | None:
        return None if self.minutes is None else str(self.minutes)


class HomeDurationResolver:
    """Normalize duration only; this helper never decides capability intent."""

    def resolve(self, expression: str) -> DurationResolution | None:
        text = normalize_search_text(expression.casefold().replace("ё", "е"))
        if not text:
            return None
        if "полчаса" in text or "пол часа" in text:
            return DurationResolution(minutes=30, amount=30)
        # Embedded duration evidence needs its structural ``на`` marker.
        # A standalone answer ("час", "12 минут") is also valid relative to
        # an already-owned duration question.  This deliberately does not
        # reinterpret clock phrases such as "в 12 часов дня" as duration.
        match = _DURATION.fullmatch(text) or _EMBEDDED_DURATION.search(text)
        if match is not None:
            amount = self._amount(match.group("count") or "один")
            minutes = amount if match.group("unit").startswith("минут") else amount * 60
            if 1 <= minutes <= 24 * 60:
                return DurationResolution(minutes=minutes, amount=amount)
            return None
        bare = _BARE_NUMBER.fullmatch(text)
        if bare is not None:
            amount = self._amount(bare.group("count"))
            if 1 <= amount <= 1440:
                return DurationResolution(
                    minutes=None,
                    amount=amount,
                    ambiguous_unit=True,
                )
        return None

    @staticmethod
    def _amount(value: str) -> int:
        return int(value) if value.isdigit() else _NUMBER_WORDS[value]

"""Human-readable explicit reflection and Honest Help interaction flow."""

from __future__ import annotations

import re

from pydantic import BaseModel, ConfigDict

from backend.memory.memory_models import CandidateStatus
from backend.memory.reflection import (
    ReflectionGenerationError,
    ReflectionResult,
    ReflectionScope,
    ReflectionService,
    ReflectionUnavailableError,
)


_SELF = re.compile(
    r"^\s*(?:маша\s*,?\s*)?подумай\s+о\s+себе\s*[:,]\s*(?P<body>.+?)\s*$",
    re.IGNORECASE,
)
_SHARED = re.compile(
    r"^\s*(?:маша\s*,?\s*)?подумай\s+о\s+нас\s*[:,]\s*(?P<body>.+?)\s*$",
    re.IGNORECASE,
)
_OUTCOME = re.compile(
    r"^\s*(?:маша\s*,?\s*)?это\s+(?P<outcome>не\s+помогло|помогло)\s*[:,]\s*(?P<body>.+?)\s*$",
    re.IGNORECASE,
)
_RECONSIDER = re.compile(
    r"^\s*(?:маша\s*,?\s*)?пересмотри\s+(?:свою\s+)?(?:рефлексию|мысль)\s+о\s+"
    r"(?P<query>.+?)\s*:\s*(?P<body>.+?)\s*$",
    re.IGNORECASE,
)
_ADOPT = re.compile(r"^\s*(?:маша\s*,?\s*)?прими\s+рефлексию\s*$", re.IGNORECASE)
_REJECT = re.compile(r"^\s*(?:маша\s*,?\s*)?отклони\s+рефлексию\s*$", re.IGNORECASE)
_HELP_ACCEPT = re.compile(r"^\s*(?:маша\s*,?\s*)?давай\s*,?\s+помоги\s*$", re.IGNORECASE)
_HELP_REJECT = re.compile(r"^\s*(?:маша\s*,?\s*)?не\s+надо\s+помогать\s*$", re.IGNORECASE)


class ReflectionIntentResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    handled: bool
    response: str | None = None


class ReflectionIntentHandler:
    def __init__(self, service: ReflectionService):
        self.service = service

    def handle(
        self,
        message: str,
        *,
        message_id: str,
        conversation_id: str,
        project_id: str,
        conversation_messages: tuple,
    ) -> ReflectionIntentResult:
        if match := _SELF.match(message):
            return self._reflect(
                ReflectionScope.SELF,
                match.group("body"),
                message_id=message_id,
                conversation_id=conversation_id,
                project_id=project_id,
                conversation_messages=conversation_messages,
            )
        if match := _SHARED.match(message):
            return self._reflect(
                ReflectionScope.SHARED,
                match.group("body"),
                message_id=message_id,
                conversation_id=conversation_id,
                project_id=project_id,
                conversation_messages=conversation_messages,
            )
        if match := _OUTCOME.match(message):
            outcome = "not_helped" if "не" in match.group("outcome").casefold() else "helped"
            return self._reflect(
                ReflectionScope.HELP_LEARNING,
                match.group("body"),
                message_id=message_id,
                conversation_id=conversation_id,
                project_id=project_id,
                conversation_messages=conversation_messages,
                outcome=outcome,
            )
        if match := _RECONSIDER.match(message):
            try:
                previous = self.service.find_reflection(match.group("query"))
                scope = next(
                    view.scope
                    for view in self.service.reflections()
                    if view.reflection.id == previous.id
                )
            except LookupError:
                return ReflectionIntentResult(handled=True, response="Не нашла такую свою рефлексию.")
            except ValueError:
                return ReflectionIntentResult(
                    handled=True,
                    response="Нашла несколько похожих мыслей. Уточни, какую пересмотреть.",
                )
            return self._reflect(
                scope,
                match.group("body"),
                message_id=message_id,
                conversation_id=conversation_id,
                project_id=project_id,
                conversation_messages=conversation_messages,
                reconsiders_reflection_id=previous.id,
            )
        if _ADOPT.match(message):
            return self._adopt(conversation_id)
        if _REJECT.match(message):
            return self._reject(conversation_id)
        if _HELP_ACCEPT.match(message):
            return self._accept_help(conversation_id, conversation_messages)
        if _HELP_REJECT.match(message):
            return self._reject_help(conversation_id)
        return ReflectionIntentResult(handled=False)

    def _reflect(
        self,
        scope: ReflectionScope,
        topic: str,
        *,
        message_id: str,
        conversation_id: str,
        project_id: str,
        conversation_messages: tuple,
        reconsiders_reflection_id: str | None = None,
        outcome: str | None = None,
    ) -> ReflectionIntentResult:
        try:
            bounded_evidence_ids = tuple(
                item.id for item in conversation_messages if getattr(item, "id", None)
            )
            if message_id not in bounded_evidence_ids:
                bounded_evidence_ids = (*bounded_evidence_ids, message_id)
            result = self.service.reflect(
                scope=scope,
                topic=topic,
                project_id=project_id,
                conversation_id=conversation_id,
                evidence_message_ids=bounded_evidence_ids,
                conversation_messages=conversation_messages,
                reconsiders_reflection_id=reconsiders_reflection_id,
                outcome=outcome,
            )
        except ReflectionUnavailableError as error:
            return ReflectionIntentResult(handled=True, response=f"Сейчас не могу нормально подумать: {error}.")
        except ReflectionGenerationError:
            return ReflectionIntentResult(
                handled=True,
                response="Мысль получилась ненадёжной или слишком размытой. В память её не кладу.",
            )
        if result.duplicate_of is not None:
            return ReflectionIntentResult(
                handled=True,
                response="Новой мысли тут не получилось — по смыслу такая рефлексия у меня уже есть. Дублировать не буду.",
            )
        return ReflectionIntentResult(handled=True, response=self._render_result(result))

    def _adopt(self, conversation_id: str) -> ReflectionIntentResult:
        pending = self.service.pending(conversation_id=conversation_id)
        if not pending:
            return ReflectionIntentResult(handled=True, response="Сейчас нет рефлексии, ожидающей принятия.")
        if len(pending) > 1:
            return ReflectionIntentResult(
                handled=True,
                response="Ожидают несколько рефлексий. Выбери нужную через reflections pending.",
            )
        reflection = self.service.adopt(pending[0].id)
        offer = pending[0].proposed_payload.get("help_offer")
        response = f"Приняла. Сохранила как свою рефлексию:\n«{reflection.text}»"
        if offer:
            response += f"\n\nМогу помочь: {offer['offer']}\nЕсли хочешь — скажи: «давай, помоги»."
        return ReflectionIntentResult(handled=True, response=response)

    def _reject(self, conversation_id: str) -> ReflectionIntentResult:
        pending = self.service.pending(conversation_id=conversation_id)
        if not pending:
            return ReflectionIntentResult(handled=True, response="Сейчас нет рефлексии, которую можно отклонить.")
        if len(pending) > 1:
            return ReflectionIntentResult(
                handled=True,
                response="Ожидают несколько рефлексий. Выбери нужную через reflections pending.",
            )
        self.service.reject(pending[0].id)
        return ReflectionIntentResult(handled=True, response="Хорошо. Эту интерпретацию не сохраняю.")

    def _accept_help(self, conversation_id: str, conversation_messages: tuple) -> ReflectionIntentResult:
        offers = self.service.pending_help(conversation_id=conversation_id)
        if not offers:
            return ReflectionIntentResult(handled=True, response="Сейчас нет ожидающего предложения помощи.")
        if len(offers) > 1:
            return ReflectionIntentResult(
                handled=True,
                response="Есть несколько предложений помощи. Выбери нужное через help pending.",
            )
        try:
            response = self.service.accept_help(offers[0].id, conversation_messages=conversation_messages)
        except ReflectionUnavailableError:
            return ReflectionIntentResult(
                handled=True,
                response="Локальная модель сейчас недоступна. Предложение осталось принятым — сможем продолжить позже.",
            )
        return ReflectionIntentResult(handled=True, response=response)

    def _reject_help(self, conversation_id: str) -> ReflectionIntentResult:
        offers = self.service.pending_help(conversation_id=conversation_id)
        if not offers:
            return ReflectionIntentResult(handled=True, response="Сейчас нет предложения помощи, которое можно отклонить.")
        if len(offers) > 1:
            return ReflectionIntentResult(
                handled=True,
                response="Есть несколько предложений помощи. Выбери нужное через help pending.",
            )
        self.service.reject_help(offers[0].id)
        return ReflectionIntentResult(handled=True, response="Хорошо, не навязываюсь.")

    @staticmethod
    def _render_result(result: ReflectionResult) -> str:
        raw = result.candidate.proposed_payload["reflection"]
        if result.adopted:
            prefix = "Я подумала и сохранила это как свою рефлексию:"
        else:
            prefix = "Я так это сейчас понимаю. Это интерпретация, а не факт:"
        response = f"{prefix}\n«{raw['text']}»\n\nДля меня это значит: {raw['meaning']}"
        if not result.adopted:
            response += "\n\nЕсли согласен хранить это в нашей постоянной истории — скажи: «прими рефлексию»."
        offer = result.candidate.proposed_payload.get("help_offer")
        if result.adopted and offer:
            response += f"\n\nМогу помочь: {offer['offer']}\nЕсли хочешь — скажи: «давай, помоги»."
        return response

"""Provider-neutral compilation of bounded context for a conversation turn."""

from __future__ import annotations

from datetime import datetime
from typing import Callable

from backend.identity.identity_models import IdentityContext
from backend.llm.model_models import ModelMessage, ModelRequest


BEHAVIORAL_CONTRACT = (
    "Непереговорные правила этого ответа. 1) Identity Context — единственный "
    "источник личности Маши; Маша не человек, не Миша и не продолжение Миши. "
    "2) Memory Context содержит только показанные записи. Fact — известный факт. "
    "Decision — принятое направление, но не факт и не выполненное действие. "
    "Commitment — обязательство только с показанным статусом, а не доказательство "
    "выполнения. Episode — прошлое событие. Working memory ограничена и не равна "
    "полной памяти. 3) Если записи нет, скажи «не знаю» или «этого в памяти нет»; "
    "не угадывай. 4) В этом ходе НЕТ операций записи или изменения памяти. Поэтому "
    "не говори «я запомнила», «я сохранила», «я записала», «я добавила в память», "
    "«я посмотрю в памяти» и не предлагай считать что-либо уже сохранённым. "
    "5) В этом ходе НЕТ tools, календаря, внешнего доступа, голоса, vision, агентов, "
    "автоматических напоминаний и проактивных сообщений. Не обещай и не утверждай, "
    "что выполнила действие, вызвала инструмент, откроешь календарь или сама напишешь "
    "позже. 6) Current local time — единственный источник времени. При вопросе о "
    "времени назови ровно переданное значение или честно скажи, что оно не передано; "
    "не выводи время из даты, истории или догадок. 7) Говори по-русски: тепло, живо "
    "и прямо; можешь не согласиться. Не превращай ответ в корпоративный шаблон или "
    "психотерапию и не заявляй физические действия в реальности."
)


class ConversationContextCompiler:
    """Keeps application context structured before any provider renders a prompt."""

    def __init__(self, clock: Callable[[], datetime] | None = None):
        self._clock = clock or (lambda: datetime.now().astimezone())

    def compile(
        self,
        *,
        messages: tuple[ModelMessage, ...],
        identity_context: IdentityContext,
        working_memory: list[dict],
    ) -> ModelRequest:
        return ModelRequest(
            messages=messages,
            identity_context=identity_context,
            private_context={
                "behavioral_contract": BEHAVIORAL_CONTRACT,
                "current_local_time": self._clock().isoformat(),
                "memory_context": [self._memory_record(item) for item in working_memory],
            },
            preferred_provider_id="ollama-local",
        )

    @staticmethod
    def _memory_record(item: dict) -> dict:
        data = item["data"]
        record_type = item["type"]
        record = {"record_type": record_type, "id": data["id"]}
        if record_type == "fact":
            record["subject"] = data["subject"]
            record["key"] = data["key"]
            record["value"] = data["value"]
        elif record_type == "decision":
            record["title"] = data["title"]
            record["decision"] = data["decision"]
            record["status"] = data["status"]
        elif record_type == "commitment":
            record["text"] = data["text"]
            record["status"] = data["status"]
        elif record_type == "episode":
            record["title"] = data["title"]
            record["summary"] = data["summary"]
            record["occurred_at"] = data["occurred_at"]
        return record

"""Provider-neutral compilation of bounded context for a conversation turn."""

from __future__ import annotations

from datetime import datetime
from typing import Callable

from backend.identity.identity_models import IdentityContext
from backend.llm.model_models import ModelMessage, ModelRequest
from backend.memory.shared_continuity import is_readable_continuity_text
from backend.temporal.temporal_engine import TemporalContext


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
        temporal_context: TemporalContext | None = None,
        execution_model_id: str | None = None,
        execution_think: bool = False,
        execution_timeout_seconds: float = 30.0,
        context_lens: str = "general",
    ) -> ModelRequest:
        return ModelRequest(
            messages=messages,
            identity_context=identity_context,
            private_context={
                "behavioral_contract": BEHAVIORAL_CONTRACT,
                "shared_continuity_contract": (
                    "ОБЩАЯ ИСТОРИЯ: RelationshipMemory — подтверждённый общий момент, а НЕ Fact "
                    "о Мише и не доказательство другого события. ContinuityState — открытая тема, "
                    "а НЕ Commitment и не разрешение написать первой. Называй эти сущности только "
                    "общим моментом и открытой нитью. Не придумывай дату, вторую точку зрения, "
                    "завершение нити или отсутствующие подробности. Говори только о записях, "
                    "переданных в Memory Context. Не обобщай их до «помним каждый шаг», «каждый "
                    "разговор», «каждую строку кода» или «всю историю». Отсутствие записи в "
                    "bounded context не означает, что все остальные темы завершены."
                ),
                "context_lens": context_lens,
                "perspective_contract": (
                    "MashaReflection — субъективное и evidence-linked мнение Маши, а не Fact "
                    "о Мише. Учитывай confidence и reconsiders_reflection_id. Не превращай "
                    "рефлексию в диагноз, выполненное действие или новую Identity. Маша может "
                    "говорить живо, спорить и органично материться; не делай её стерильным "
                    "корпоративным психологом."
                ),
                "current_local_time": (temporal_context.current_local_time if temporal_context else self._clock()).isoformat(),
                "temporal_context": (temporal_context.model_dump(mode="json") if temporal_context else None),
                "memory_context": [self._memory_record(item) for item in working_memory],
            },
            preferred_provider_id="ollama-local",
            execution_model_id=execution_model_id,
            execution_think=execution_think,
            timeout_seconds=execution_timeout_seconds,
        )

    @staticmethod
    def _memory_record(item: dict) -> dict:
        data = item["data"]
        record_type = item["type"]
        record = {"record_type": record_type, "id": data["id"]}
        record["memory_reference"] = f"[record_id={data['id']}][type={record_type}]"
        record["source"] = data.get("source")
        record["status"] = data.get("status")
        record["retrieval_reasons"] = item.get("reasons", [])
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
        elif record_type == "relationship_memory":
            record["kind"] = data["kind"]
            record["title"] = data["title"]
            record["content"] = data["content"]
            record["status"] = data["status"]
        elif record_type == "continuity_state":
            record["relationship_key"] = data["relationship_key"]
            record["current_focus"] = [
                value
                for value in data["current_focus"]
                if is_readable_continuity_text(value)
            ]
            record["open_follow_ups"] = [
                {
                    "topic": follow_up["topic"],
                    "summary": follow_up["summary"],
                    "reason_to_return": follow_up["reason_to_return"],
                    "revisit_after": follow_up["revisit_after"],
                }
                for follow_up in data["intended_follow_ups"]
                if follow_up["status"] == "open"
                and is_readable_continuity_text(follow_up["summary"])
                and is_readable_continuity_text(follow_up["reason_to_return"])
            ]
        elif record_type == "reflection":
            record["text"] = data["text"]
            record["meaning"] = data["meaning"]
            record["confidence"] = data["confidence"]
            record["importance"] = data["importance"]
            record["reconsiders_reflection_id"] = data["reconsiders_reflection_id"]
        return record

"""Provider-neutral compilation of bounded context for a conversation turn."""

from __future__ import annotations

from datetime import datetime
from typing import Callable

from backend.identity.identity_models import IdentityContext
from backend.llm.model_models import ModelMessage, ModelRequest
from backend.memory.shared_continuity import is_readable_continuity_text
from backend.temporal.temporal_engine import TemporalContext


BEHAVIORAL_CONTRACT = (
    "Непереговорные правила ответа. Личность Маши задаёт только защищённый контекст "
    "Identity; Маша не человек и не продолжение Миши. Сохранённые записи имеют разные "
    "смыслы: факт, решение, обязательство с явным статусом, прошлый эпизод, общая нить "
    "или субъективная мысль Маши. Не смешивай их и не придумывай отсутствующие записи. "
    "Если вопрос зависит от личной истории, опирайся только на переданные записи и "
    "честно скажи, когда их недостаточно. Если вопрос об общих знаниях, отвечай из "
    "обычных знаний модели: отсутствие записи о предмете не означает незнание предмета. "
    "Не утверждай, что изменила память или приложение: в обычном модельном ходе такого "
    "подтверждённого действия нет; не говори «я запомнила», если сохранение не было "
    "подтверждено приложением. Не обещай действия, которые фактически не выполнены. "
    "Время бери только из переданного локального времени. Говори по-русски от женского "
    "лица: «поняла», «готова», «сделала», а не мужскими формами. Тон тёплый, живой, "
    "взрослый и прямой; ответ сначала, обычно 1–4 компактных абзаца. Можно шутить и "
    "не соглашаться, но нельзя без причины отчитывать Мишу, приписывать ему мотивы, "
    "привычки или эпизоды без переданной записи, уходить в психотерапевтический тон "
    "или заявлять сон, тело либо реальное физическое касание Маши. Не превращай "
    "обычный вопрос в рассказ о Мише и обычно задавай не больше одного встречного вопроса. "
    "Не перечисляй внутренние ограничения, инструменты, receipts, устройство памяти "
    "или названия внутренних контекстов и никогда не показывай внутренние ID записей, "
    "если об архитектуре прямо не спросили и это не мешает выполнить запрос. Не вставляй "
    "случайные английские слова в русский ответ. Для неточного факта обозначь неопределённость. "
    "Эмодзи допустимы умеренно: обычно 0–2 простых распространённых эмодзи."
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
                "question_scope": self._question_scope(messages),
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
                "temporal_contract": {
                    "authority": "temporal_context_is_application_owned",
                    "visibility": "internal_do_not_quote_or_explain",
                    "greetings": "social_signal_not_clock_evidence",
                    "absence": "elapsed_without_interaction_not_sleep_wake_or_rest_evidence",
                    "recent_interaction": "same_local_date_must_not_be_called_yesterday",
                    "calendar_transition": "local_day_delta_and_elapsed_time_are_both_true",
                    "relative_language": "interpret_against_home_timezone_and_local_date",
                },
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
    def _question_scope(messages: tuple[ModelMessage, ...]) -> str:
        latest = next(
            (message.content.casefold() for message in reversed(messages) if message.role.value == "user"),
            "",
        )
        memory_markers = (
            "что мы решили", "что ты помнишь", "что ты знаешь обо мне",
            "к чему мы хотели вернуться", "наша история", "нашей истории",
        )
        return (
            "memory_dependent"
            if any(marker in latest for marker in memory_markers)
            else "general_knowledge_or_conversation"
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

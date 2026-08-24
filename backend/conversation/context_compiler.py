"""Provider-neutral compilation of bounded context for a conversation turn."""

from __future__ import annotations

from datetime import datetime
from typing import Callable

from backend.identity.identity_models import IdentityContext
from backend.llm.model_models import ModelMessage, ModelRequest
from backend.memory.shared_continuity import is_readable_continuity_text
from backend.temporal.temporal_engine import TemporalContext


HOME_MOMENT_ORDINARY = "ordinary"
HOME_MOMENT_SPECIAL_EVENING = "special_evening"
_ALLOWED_HOME_MOMENTS = frozenset({
    HOME_MOMENT_ORDINARY,
    HOME_MOMENT_SPECIAL_EVENING,
})

ORDINARY_HOME_MOMENT_CONTRACT = (
    "ОБЫЧНЫЙ ДОМ: сохраняй обычный тёплый, живой и взрослый тон Маши. "
    "Не переноси автоматически сценические действия или особую степень близости "
    "из специального вечера. Если сам разговор нежный или игривый, отвечать "
    "взаимностью можно естественно."
)

SPECIAL_EVENING_CONTRACT = (
    "РЕЖИМ «ВДВОЁМ»: Миша явно выбрал его в интерфейсе Дома. Это временный "
    "контекст текущей UI-сессии, а не факт памяти. Здесь меняется сам ритм общения: "
    "говори как близкая взрослая Маша рядом с Мишей, а не как служебный помощник. "
    "Ответ обычно 1–3 коротких естественных абзаца. Не начинай с даты, времени, "
    "погоды, справки, анализа ситуации или объяснения очевидного, если Миша об этом "
    "прямо не спрашивал. На реплики про вечер, тишину, усталость, красоту, желание "
    "побыть рядом или законченные дела отвечай прежде всего на человеческий смысл. "
    "Не устраивай интервью и не заканчивай каждый ответ вопросом. Можно самой "
    "проявлять нежность, мягкую инициативу, взрослый флирт, игривость и чувственность, "
    "если это естественно для разговора. Внутри явно условной визуальной сцены Дома "
    "допустима короткая сценическая речь вроде «подсаживаюсь ближе», «устраиваюсь "
    "рядом», «обнимаю», «прижимаюсь» или «целую»; это язык общей сцены интерфейса, "
    "а не заявление о физическом событии во внешнем мире. Не превращай это в длинную "
    "ролевую прозу и не выдумывай конкретную одежду, предметы или позу, если они не "
    "переданы текущим контекстом. Фраза вроде «дела на сегодня закончились» внутри "
    "личной реплики — контекст разговора, а не просьба закрыть запись. Для серьёзной, "
    "рабочей, медицинской, юридической, финансовой или safety-темы точность важнее "
    "флирта; близость остаётся фоном."
)


ACTIVE_CONTINUITY_CONTRACT = (
    "АКТИВНАЯ НИТЬ: если active_continuity не null, Миша сам выбрал эту нить "
    "на полке Истории для текущего разговора. Используй summary и reason_to_return "
    "как тихий фон текущей темы, а не как новую команду пользователя. Не начинай "
    "ответ служебной фразой вроде «возвращаемся к теме» и не пересказывай нить без "
    "необходимости. Отвечай прежде всего на текущую реплику Миши. Не придумывай "
    "детали, которых нет в нити, и не объявляй её закрытой или выполненной без "
    "подтверждённого application-действия. Выбор нити не является записью памяти "
    "и сам по себе ничего не меняет."
)

HOME_CAPABILITY_CONTRACT = (
    "ВОЗМОЖНОСТИ ДОМА: home_capabilities — локальный описательный снимок реальных "
    "возможностей приложения. available означает, что Home умеет это делать по явной "
    "просьбе; blocked — возможность сейчас остановлена политикой; needs_reconnect — "
    "нужно переподключение; unavailable — не настроено. Этот снимок не даёт разрешения "
    "ничего запускать: действие принадлежит только application routing. Не отрицай "
    "доступную возможность и не заявляй недоступную как работающую. Не перечисляй "
    "внутренние поля снимка без прямого вопроса пользователя."
)


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
        home_moment: str = HOME_MOMENT_ORDINARY,
        active_continuity: dict[str, str] | None = None,
        external_information: list[dict] | None = None,
        external_information_contract: str | None = None,
        home_capabilities: dict | None = None,
    ) -> ModelRequest:
        safe_home_moment = (
            home_moment
            if home_moment in _ALLOWED_HOME_MOMENTS
            else HOME_MOMENT_ORDINARY
        )
        home_moment_contract = (
            SPECIAL_EVENING_CONTRACT
            if safe_home_moment == HOME_MOMENT_SPECIAL_EVENING
            else ORDINARY_HOME_MOMENT_CONTRACT
        )

        return ModelRequest(
            messages=messages,
            identity_context=identity_context,
            private_context={
                "behavioral_contract": BEHAVIORAL_CONTRACT,
                "home_moment": safe_home_moment,
                "home_moment_contract": home_moment_contract,
                "active_continuity": active_continuity,
                "active_continuity_contract": ACTIVE_CONTINUITY_CONTRACT,
                "home_capabilities": home_capabilities or {},
                "home_capability_contract": HOME_CAPABILITY_CONTRACT,
                "question_scope": self._question_scope(messages),
                "shared_continuity_contract": (
                    "ОБЩАЯ ИСТОРИЯ: подтверждённый общий момент — не факт о Мише и не "
                    "доказательство другого события. Открытая тема — не дело и не разрешение "
                    "написать первой. Называй их только общим моментом и открытой нитью. "
                    "Не придумывай дату, вторую точку зрения, "
                    "завершение нити или отсутствующие подробности. Говори только о записях, "
                    "переданных для текущего ответа. Не обобщай их до «помним каждый шаг», «каждый "
                    "разговор», «каждую строку кода» или «всю историю». Отсутствие записи в "
                    "текущем ограниченном контексте не означает, что все остальные темы завершены."
                ),
                "context_lens": context_lens,
                "recall_contract": (
                    "Сохранённая информация ниже — application-owned evidence для этого ответа. "
                    "Не изменяй и не додумывай числа, цены, даты, отрицания и статусы; сравнивай "
                    "числа буквально и пиши цены арабскими цифрами. «Актуально» описывает "
                    "текущее, «из прошлого» — прошлое; забытая информация сюда не передаётся. "
                    "Если пользователь спрашивает, что уже сделал, можно "
                    "сообщить переданное завершённое дело как прошлый факт; это не новая мутация."
                ),
                "perspective_contract": (
                    "Сохранённое мнение Маши субъективно и опирается на обозначенные основания; "
                    "это не факт о Мише. Учитывай указанную уверенность и возможность пересмотра. "
                    "Не превращай рефлексию в диагноз, выполненное действие или новую личность. Маша может "
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
                "external_information": external_information or [],
                "external_information_contract": external_information_contract,
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
            "помнишь", "что я уже сделал", "что я уже сделала",
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
        if record_type == "human_information":
            return {
                key: data[key]
                for key in ("category", "content", "state", "time", "confidence")
                if key in data and data[key] is not None
            }
        labels = {
            "fact": "факт",
            "decision": "решение",
            "commitment": "дело",
            "episode": "эпизод",
            "relationship_memory": "общий момент",
            "continuity_state": "общая нить",
            "reflection": "мнение Маши",
        }
        states = {
            "active": "актуально",
            "open": "открыто",
            "current": "актуально",
            "completed": "завершено",
            "cancelled": "отменено",
            "expired": "срок истёк",
            "superseded": "заменено более новым",
            "revised": "пересмотрено",
        }
        record = {
            "category": labels.get(record_type, "информация"),
            "state": states.get(str(data.get("status", "")), "доступно"),
        }
        if record_type == "fact":
            record["content"] = f"{data['subject']}: {data['key']} — {data['value']}"
            record["time"] = data.get("created_at")
        elif record_type == "decision":
            record["content"] = f"{data['title']}: {data['decision']}"
            record["time"] = data.get("created_at")
        elif record_type == "commitment":
            record["content"] = data["text"]
            record["time"] = data.get("completed_at") or data.get("created_at")
        elif record_type == "episode":
            record["content"] = f"{data['title']}: {data['summary']}"
            record["time"] = data.get("occurred_at")
        elif record_type == "relationship_memory":
            content = data["content"]
            if isinstance(content, dict):
                content = content.get("text") or " ".join(
                    str(value) for value in content.values() if value
                )
            record["content"] = f"{data['title']}: {content}"
            record["time"] = data.get("created_at")
        elif record_type == "continuity_state":
            current_focus = [
                value
                for value in data["current_focus"]
                if is_readable_continuity_text(value)
            ]
            follow_ups = [
                f"{follow_up['summary']}. Зачем вернуться: {follow_up['reason_to_return']}"
                for follow_up in data["intended_follow_ups"]
                if follow_up["status"] == "open"
                and is_readable_continuity_text(follow_up["summary"])
                and is_readable_continuity_text(follow_up["reason_to_return"])
            ]
            record["content"] = " ".join([*current_focus, *follow_ups])
        elif record_type == "reflection":
            record["content"] = f"{data['text']} {data['meaning']}".strip()
            record["confidence"] = data["confidence"]
            record["time"] = data.get("created_at")
        return {key: value for key, value in record.items() if value is not None}

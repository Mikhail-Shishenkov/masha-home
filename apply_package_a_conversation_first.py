
from __future__ import annotations

from pathlib import Path
import re

ROOT = Path.cwd()
STAGED: dict[Path, str] = {}


class PatchError(RuntimeError):
    pass


def read(path: str) -> str:
    p = ROOT / path
    if p not in STAGED:
        if not p.exists():
            raise PatchError(f"{path}: file not found")
        STAGED[p] = p.read_text(encoding="utf-8")
    return STAGED[p]


def stage(path: str, text: str) -> None:
    STAGED[ROOT / path] = text


def replace_once(path: str, old: str, new: str, *, label: str) -> None:
    text = read(path)
    count = text.count(old)
    if count != 1:
        raise PatchError(
            f"{path}: {label}: expected 1 exact match, found {count}"
        )
    stage(path, text.replace(old, new, 1))
    print(f"[CHECK] {path}: {label}")


def regex_once(path: str, pattern: str, repl: str, *, label: str, flags: int = 0) -> None:
    text = read(path)
    updated, count = re.subn(pattern, repl, text, count=1, flags=flags)
    if count != 1:
        raise PatchError(
            f"{path}: {label}: expected 1 regex match, found {count}"
        )
    stage(path, updated)
    print(f"[CHECK] {path}: {label}")


def insert_before_once(path: str, marker: str, block: str, *, label: str) -> None:
    text = read(path)
    if block.strip() in text:
        print(f"[SKIP] {path}: {label} already present")
        return
    count = text.count(marker)
    if count != 1:
        raise PatchError(
            f"{path}: {label}: expected 1 marker, found {count}"
        )
    stage(path, text.replace(marker, block + marker, 1))
    print(f"[CHECK] {path}: {label}")


def append_test(path: str, marker: str, block: str) -> None:
    text = read(path)
    if marker in text:
        print(f"[SKIP] {path}: test already present")
        return
    if not text.endswith("\n"):
        text += "\n"
    stage(path, text + "\n" + block.strip() + "\n")
    print(f"[CHECK] {path}: test ready")


def ensure_python_compiles() -> None:
    for path, text in STAGED.items():
        if path.suffix == ".py":
            try:
                compile(text, str(path), "exec")
            except SyntaxError as exc:
                raise PatchError(
                    f"{path.relative_to(ROOT)}: generated Python does not compile: "
                    f"{exc.msg} at line {exc.lineno}"
                ) from exc


try:
    # ------------------------------------------------------------------
    # 1. Presentation -> application: expose current UI-only Home moment.
    # ------------------------------------------------------------------
    path = "backend/application/home_snapshot.py"
    text = read(path)
    if "def home_moment(self)" not in text:
        replace_once(
            path,
            """    @property
    def active_model_display_name(self) -> str:
        return self._active_model.display_name
""",
            """    @property
    def home_moment(self) -> HomeMoment:
        # UI-only authored moment; never persisted as domain memory.
        return self._runtime.model.home_moment

    @property
    def active_model_display_name(self) -> str:
        return self._active_model.display_name
""",
            label="expose current Home moment",
        )
    else:
        print(f"[SKIP] {path}: home_moment property already present")

    # ------------------------------------------------------------------
    # 2. Public application boundary carries a bounded string cue.
    # ------------------------------------------------------------------
    path = "backend/application/application.py"
    text = read(path)
    if "home_moment: str = \"ordinary\"" not in text.split("def conversation(", 1)[0]:
        replace_once(
            path,
            """    def send_message(self, content: str, *, project_id: str, conversation_id: str | None = None) -> ConversationTurnResult:
        return self._conversation.send_message(content, project_id=project_id, conversation_id=conversation_id)
""",
            """    def send_message(
        self,
        content: str,
        *,
        project_id: str,
        conversation_id: str | None = None,
        home_moment: str = "ordinary",
    ) -> ConversationTurnResult:
        return self._conversation.send_message(
            content,
            project_id=project_id,
            conversation_id=conversation_id,
            home_moment=home_moment,
        )
""",
            label="thread home_moment through send_message",
        )
    else:
        print(f"[SKIP] {path}: send_message already carries home_moment")

    text = read(path)
    continuation_chunk = text.split("def continue_continuity_thread(", 1)
    if len(continuation_chunk) == 2 and "home_moment: str = \"ordinary\"" not in continuation_chunk[1].split("def reflection_workspace", 1)[0]:
        replace_once(
            path,
            """    def continue_continuity_thread(
        self,
        thread_id: str,
        *,
        conversation_id: str | None,
        project_id: str,
    ) -> ConversationTurnResult:
        prompt = self._continuity.thread_prompt(thread_id)
        return self._conversation.send_message(
            prompt,
            project_id=project_id,
            conversation_id=conversation_id,
            allow_capability_routing=False,
            active_continuity_thread_id=thread_id,
        )
""",
            """    def continue_continuity_thread(
        self,
        thread_id: str,
        *,
        conversation_id: str | None,
        project_id: str,
        home_moment: str = "ordinary",
    ) -> ConversationTurnResult:
        prompt = self._continuity.thread_prompt(thread_id)
        return self._conversation.send_message(
            prompt,
            project_id=project_id,
            conversation_id=conversation_id,
            allow_capability_routing=False,
            active_continuity_thread_id=thread_id,
            home_moment=home_moment,
        )
""",
            label="thread home_moment through continuity resume",
        )
    else:
        print(f"[SKIP] {path}: continuity already carries home_moment")

    # ------------------------------------------------------------------
    # 3. Application conversation adapter forwards the cue.
    # ------------------------------------------------------------------
    path = "backend/application/conversation.py"
    text = read(path)
    send_head = text.split("    def send_message(", 1)[1].split("    def ", 1)[0]
    if "home_moment: str = \"ordinary\"" not in send_head:
        replace_once(
            path,
            """        allow_capability_routing: bool = True,
        active_continuity_thread_id: str | None = None,
    ) -> ConversationTurnResult:
""",
            """        allow_capability_routing: bool = True,
        active_continuity_thread_id: str | None = None,
        home_moment: str = "ordinary",
    ) -> ConversationTurnResult:
""",
            label="add home_moment parameter",
        )

    text = read(path)
    if "home_moment=home_moment" not in text.split("    def send_message(", 1)[1].split("    def ", 1)[0]:
        replace_once(
            path,
            """                allow_capability_routing=allow_capability_routing,
                active_continuity_thread_id=active_thread_id,
            )
""",
            """                allow_capability_routing=allow_capability_routing,
                active_continuity_thread_id=active_thread_id,
                home_moment=home_moment,
            )
""",
            label="forward home_moment to ConversationService",
        )

    # ------------------------------------------------------------------
    # 4. ConversationService owns the mode switch:
    #    ordinary = normal router, special_evening = conversation-first.
    # ------------------------------------------------------------------
    path = "backend/conversation/conversation_service.py"
    text = read(path)
    send_head = text.split("    def send(", 1)[1].split("        conversation =", 1)[0]
    if "home_moment: str = \"ordinary\"" not in send_head:
        replace_once(
            path,
            """        allow_capability_routing: bool = True,
        active_continuity_thread_id: str | None = None,
    ) -> tuple[str, str]:
""",
            """        allow_capability_routing: bool = True,
        active_continuity_thread_id: str | None = None,
        home_moment: str = "ordinary",
    ) -> tuple[str, str]:
""",
            label="add home_moment to ConversationService",
        )

    text = read(path)
    capability_call = """                active_continuity_thread_id=active_continuity_thread_id,
                conversation_messages=self.history.messages(
                    conversation.id,
                    limit=self.history_limit,
                ),
            )
"""
    if "conversation_first=home_moment == \"special_evening\"" not in text:
        replace_once(
            path,
            capability_call,
            """                active_continuity_thread_id=active_continuity_thread_id,
                conversation_messages=self.history.messages(
                    conversation.id,
                    limit=self.history_limit,
                ),
                conversation_first=home_moment == "special_evening",
            )
""",
            label="make Special Evening conversation-first",
        )

    text = read(path)
    compile_window = text.split("request = self.context_compiler.compile(", 1)[1].split("        )", 1)[0]
    if "home_moment=home_moment" not in compile_window:
        replace_once(
            path,
            """            execution_timeout_seconds=30.0 if active_profile is None else active_profile.timeout_seconds,
            context_lens=context_lens.value,
        )
""",
            """            execution_timeout_seconds=30.0 if active_profile is None else active_profile.timeout_seconds,
            context_lens=context_lens.value,
            home_moment=home_moment,
        )
""",
            label="pass Home moment to model context compiler",
        )

    # ------------------------------------------------------------------
    # 5. MemoryIntentHandler: explicit commands survive, inferred helpers go quiet.
    # ------------------------------------------------------------------
    path = "backend/conversation/memory_intent.py"
    text = read(path)
    handle_head = text.split("    def handle(", 1)[1].split("        # A plain human confirmation", 1)[0]
    if "conversation_first: bool = False" not in handle_head:
        replace_once(
            path,
            """        active_continuity_thread_id: str | None = None,
        conversation_messages: tuple[ConversationMessage, ...] = (),
    ) -> MemoryIntentResult:
""",
            """        active_continuity_thread_id: str | None = None,
        conversation_messages: tuple[ConversationMessage, ...] = (),
        conversation_first: bool = False,
    ) -> MemoryIntentResult:
""",
            label="add conversation_first policy",
        )

    text = read(path)
    if "# Conversation-first sessions discard stale shelf clarifications." not in text:
        replace_once(
            path,
            """        pending = self.proposal_store.current_for_conversation(conversation_id) is not None

        human_clarification = self._human_entity_clarifications.get(conversation_id)
""",
            """        pending = self.proposal_store.current_for_conversation(conversation_id) is not None

        # Conversation-first sessions discard stale shelf clarifications.
        # An explicit new command below can still open a fresh shelf interaction.
        if conversation_first:
            self._continuity_clarifications.pop(conversation_id, None)
            self._human_entity_clarifications.pop(conversation_id, None)

        human_clarification = self._human_entity_clarifications.get(conversation_id)
""",
            label="drop stale clarification interruptions",
        )

    text = read(path)
    old_route = "self.capability_router.route(message)"
    new_route = (
        "self.capability_router.route(\n"
        "                message,\n"
        "                allow_semantic=not conversation_first,\n"
        "                explicit_only=conversation_first,\n"
        "            )"
    )
    # Replace all occurrences inside handle.  There are clarification calls plus
    # the final capability call; all should obey the same policy.
    if old_route in text:
        count = text.count(old_route)
        stage(path, text.replace(old_route, new_route))
        print(f"[CHECK] {path}: route policy applied to {count} call(s)")

    text = read(path)
    if "if not conversation_first and _COMPLETE_IMPLICIT.match(message):" not in text:
        replace_once(
            path,
            """        if _COMPLETE_IMPLICIT.match(message):
""",
            """        if not conversation_first and _COMPLETE_IMPLICIT.match(message):
""",
            label="disable implicit completion clarification in conversation-first mode",
        )

    text = read(path)
    if "if not conversation_first and _AMBIGUOUS_COMMITMENT_FOLLOW_UP.match(message):" not in text:
        replace_once(
            path,
            """        if _AMBIGUOUS_COMMITMENT_FOLLOW_UP.match(message):
""",
            """        if not conversation_first and _AMBIGUOUS_COMMITMENT_FOLLOW_UP.match(message):
""",
            label="disable ambiguous task follow-up in conversation-first mode",
        )

    text = read(path)
    if "if not conversation_first and (reference := _COMMITMENT_REFERENCE_QUERY.match(message)):" not in text:
        replace_once(
            path,
            """        if reference := _COMMITMENT_REFERENCE_QUERY.match(message):
""",
            """        if not conversation_first and (reference := _COMMITMENT_REFERENCE_QUERY.match(message)):
""",
            label="disable inferred commitment references in conversation-first mode",
        )

    # ------------------------------------------------------------------
    # 6. Capability router: deterministic explicit actions first; semantic can say "none".
    # ------------------------------------------------------------------
    path = "backend/conversation/capability_router.py"
    text = read(path)
    if "def route(self, message: str, *, allow_semantic: bool = True, explicit_only: bool = False)" not in text:
        replace_once(
            path,
            """    def route(self, message: str) -> ParsedCapabilityIntent | None:
        text = normalize_utterance(message)
        if not text:
            return None
        deterministic = self._deterministic(text)
        if deterministic is not None:
            return deterministic
        if self.classifier is None or not self._has_capability_signal(text):
            return None
""",
            """    def route(
        self,
        message: str,
        *,
        allow_semantic: bool = True,
        explicit_only: bool = False,
    ) -> ParsedCapabilityIntent | None:
        text = normalize_utterance(message)
        if not text:
            return None
        deterministic = self._deterministic(text, explicit_only=explicit_only)
        if deterministic is not None:
            return deterministic
        if explicit_only or not allow_semantic:
            return None
        if self.classifier is None or not self._has_capability_signal(text):
            return None
""",
            label="add explicit-only / semantic-off routing policy",
        )

    text = read(path)
    if "def _deterministic(text: str, *, explicit_only: bool = False)" not in text:
        replace_once(
            path,
            """    @staticmethod
    def _deterministic(text: str) -> ParsedCapabilityIntent | None:
""",
            """    @staticmethod
    def _deterministic(
        text: str,
        *,
        explicit_only: bool = False,
    ) -> ParsedCapabilityIntent | None:
""",
            label="make deterministic router mode-aware",
        )

    # Tighten broad deterministic reads so incidental words do not own a turn.
    text = read(path)
    old_reads = """        if re.search(r"\\b(?:к чему|что|какие)\\b.*\\b(?:вернут|продолжа|не закончил|нить|тем|наш(?:а|ей) истор)\\w*\\b", text):
            return ParsedCapabilityIntent(intent=CapabilityIntent.QUERY_CONTINUITY, confidence=0.97)
        if re.search(r"\\b(?:какие|что|покажи)\\b.*\\b(?:дел|задач|план|запланир|обязательств)\\w*\\b", text):
            scope = "today" if "сегодня" in text else None
            return ParsedCapabilityIntent(intent=CapabilityIntent.QUERY_COMMITMENTS, confidence=0.96, temporal_scope=scope)
        if re.search(r"\\bчто\\b.*\\b(?:сегодня|запланир)\\w*\\b", text):
            return ParsedCapabilityIntent(intent=CapabilityIntent.QUERY_COMMITMENTS, confidence=0.91, temporal_scope="today" if "сегодня" in text else None)
        if re.search(r"\\b(?:что|покажи)\\b.*\\b(?:помн|памят|зна)\\w*\\b", text):
            return ParsedCapabilityIntent(
                intent=CapabilityIntent.QUERY_MEMORY,
                confidence=0.96,
                entity=memory_query_entity(text),
            )

        # Writes: these only lead to proposals in MemoryIntentHandler.
"""
    new_reads = """        if re.match(
            r"^(?:к чему (?:мы )?(?:хотели )?вернут\\w*|"
            r"что (?:у нас )?(?:остал\\w*|продолжа\\w*|не закончен\\w*|не закрыт\\w*).*(?:тем|нит)\\w*|"
            r"какие (?:у нас )?(?:тем|нит)\\w*.*(?:открыт|остал|продолжа)\\w*)$",
            text,
        ):
            return ParsedCapabilityIntent(
                intent=CapabilityIntent.QUERY_CONTINUITY,
                confidence=0.97,
            )

        if re.match(
            r"^(?:"
            r"какие (?:у (?:меня|нас) )?(?:сейчас )?(?:дела|задачи|обязательства)|"
            r"что (?:у (?:меня|нас) )?(?:сейчас )?(?:по )?(?:делам|задачам|обязательствам)|"
            r"что (?:у (?:меня|нас) )?сегодня|"
            r"что (?:было )?запланировано(?: на сегодня)?|"
            r"покажи (?:мои |наши )?(?:дела|задачи|обязательства|планы)"
            r")$",
            text,
        ):
            scope = "today" if "сегодня" in text else None
            return ParsedCapabilityIntent(
                intent=CapabilityIntent.QUERY_COMMITMENTS,
                confidence=0.96,
                temporal_scope=scope,
            )

        if re.match(
            r"^(?:(?:кстати а |а )?что ты (?:обо мне )?"
            r"(?:помнишь|знаешь)(?: про .+)?|"
            r"покажи (?:мою )?память)$",
            text,
        ):
            return ParsedCapabilityIntent(
                intent=CapabilityIntent.QUERY_MEMORY,
                confidence=0.96,
                entity=memory_query_entity(text),
            )

        # In conversation-first mode implicit completion aliases do not own the turn.
        if explicit_only:
            return None

        # Writes: these only lead to proposals in MemoryIntentHandler.
"""
    if old_reads in text:
        replace_once(
            path,
            old_reads,
            new_reads,
            label="tighten deterministic read aliases and stop inferred completion",
        )
    elif "In conversation-first mode implicit completion aliases do not own the turn." not in text:
        raise PatchError(
            f"{path}: could not find deterministic read block to tighten"
        )

    text = read(path)
    old_prompt = """                    "Classify one Russian utterance into this fixed allowlist: " + allowed + ". "
                    "Definitions: create_commitment means create a new task, plan, obligation or reminder; "
                    "complete_commitment means mark an existing task done; query_commitments means ask about "
                    "existing tasks or plans; query_memory means ask for confirmed remembered facts; "
                    "forget_memory means remove a confirmed fact; open_continuity means explicitly preserve "
                    "a discussion topic for later; query_continuity means ask which preserved topics remain "
                    "or what is stored in our shared history. "
                    "Return JSON only: {\\\"intent\\\": string, \\\"confidence\\\": 0..1, "
                    "\\\"entity\\\": string|null, \\\"temporal_scope\\\": string|null}. "
                    "For create/complete/forget/open intents, entity is the concise object or action "
                    "from the utterance with request words removed; it must be null only when the "
                    "utterance contains no resolvable object. Preserve dates and relative time in entity. "
                    "Do not answer the user and do not invent stored records."
"""
    new_prompt = """                    "Classify one Russian utterance into this fixed allowlist: " + allowed + ", or null. "
                    "A capability exists only when the primary speech act is a clear request to read or "
                    "change application-owned memory, commitments, reminders, or continuity. "
                    "Definitions: create_commitment means create a new task, plan, obligation or reminder; "
                    "complete_commitment means mark an existing stored task done; query_commitments means ask "
                    "about existing tasks or plans; query_memory means ask for confirmed remembered facts; "
                    "forget_memory means remove a confirmed fact; open_continuity means explicitly preserve "
                    "a discussion topic for later; query_continuity means ask which preserved topics remain "
                    "or what is stored in our shared history. "
                    "Ordinary conversation, narration, ambience, feelings, relationship talk, or a mixed "
                    "personal sentence that merely contains words such as дела, задача, план, закончили, "
                    "помнишь, история or тема must return null unless the utterance is actually asking for "
                    "one allowlisted application action. "
                    "Example: «Маш, всё, дела на сегодня закончились. Иди сюда, хочу просто немного побыть "
                    "с тобой.» is ordinary conversation and must return null. "
                    "Example: «С отчётом закончили» may be complete_commitment because the whole utterance "
                    "is a completion statement about one resolvable task. "
                    "Return JSON only: {\\\"intent\\\": string|null, \\\"confidence\\\": 0..1, "
                    "\\\"entity\\\": string|null, \\\"temporal_scope\\\": string|null}. "
                    "For create/complete/forget/open intents, entity is the concise object or action from "
                    "the utterance with request words removed. Preserve dates and relative time in entity. "
                    "For ordinary conversation return intent=null, entity=null, temporal_scope=null. "
                    "Do not answer the user and do not invent stored records."
"""
    if old_prompt in text:
        replace_once(
            path,
            old_prompt,
            new_prompt,
            label="allow semantic classifier to choose ordinary conversation",
        )
    elif "For ordinary conversation return intent=null" not in text:
        raise PatchError(f"{path}: semantic classifier prompt not recognised")

    text = read(path)
    old_parse = """        try:
            payload = json.loads(response.text.strip().removeprefix("```json").removesuffix("```").strip())
            payload["source"] = "local_semantic"
            return ParsedCapabilityIntent.model_validate(payload)
        except (ValueError, TypeError, KeyError):
            return None
"""
    new_parse = """        try:
            payload = json.loads(
                response.text.strip()
                .removeprefix("```json")
                .removesuffix("```")
                .strip()
            )
            if payload.get("intent") in {
                None,
                "",
                "none",
                "null",
                "conversation",
                "ordinary_conversation",
            }:
                return None
            payload["source"] = "local_semantic"
            return ParsedCapabilityIntent.model_validate(payload)
        except (ValueError, TypeError, KeyError):
            return None
"""
    if old_parse in text:
        replace_once(
            path,
            old_parse,
            new_parse,
            label="parse semantic null as conversation",
        )
    elif 'payload.get("intent") in {' not in text:
        raise PatchError(f"{path}: semantic result parser not recognised")

    # ------------------------------------------------------------------
    # 7. Model context: Special Evening changes the rhythm of conversation.
    # ------------------------------------------------------------------
    path = "backend/conversation/context_compiler.py"
    text = read(path)
    if "SPECIAL_EVENING_CONTRACT" not in text:
        insert_before_once(
            path,
            "BEHAVIORAL_CONTRACT = (\n",
            """HOME_MOMENT_ORDINARY = "ordinary"
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
    "placeholder"
)


""",
            label="add Home moment conversation contracts",
        )

    desired_special_contract = """SPECIAL_EVENING_CONTRACT = (
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
)"""
    text = read(path)
    updated, count = re.subn(
        r'SPECIAL_EVENING_CONTRACT = \(.*?\n\)',
        desired_special_contract,
        text,
        count=1,
        flags=re.DOTALL,
    )
    if count != 1:
        raise PatchError(f"{path}: could not normalise SPECIAL_EVENING_CONTRACT")
    stage(path, updated)
    print(f"[CHECK] {path}: Special Evening dialogue contract normalised")

    text = read(path)
    compile_head = text.split("    def compile(", 1)[1].split("    ) -> ModelRequest:", 1)[0]
    if "home_moment:" not in compile_head:
        replace_once(
            path,
            """        execution_timeout_seconds: float = 30.0,
        context_lens: str = "general",
    ) -> ModelRequest:
        return ModelRequest(
""",
            """        execution_timeout_seconds: float = 30.0,
        context_lens: str = "general",
        home_moment: str = HOME_MOMENT_ORDINARY,
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
""",
            label="allowlist Home moment in compiler",
        )

    text = read(path)
    if '"home_moment_contract": home_moment_contract' not in text:
        replace_once(
            path,
            """                "behavioral_contract": BEHAVIORAL_CONTRACT,
                "question_scope": self._question_scope(messages),
""",
            """                "behavioral_contract": BEHAVIORAL_CONTRACT,
                "home_moment": safe_home_moment,
                "home_moment_contract": home_moment_contract,
                "question_scope": self._question_scope(messages),
""",
            label="publish bounded Home moment to model context",
        )

    # ------------------------------------------------------------------
    # 8. Qt bridge reads current PresentationSession moment when starting a turn.
    # ------------------------------------------------------------------
    path = "backend/ui/conversation_bridge.py"
    text = read(path)
    if "def _current_home_moment(self)" not in text:
        replace_once(
            path,
            """    def _active_model_name(self) -> str:
        if self._session is None:
            return "Локальная модель"
        return self._session.active_model_display_name
""",
            """    def _active_model_name(self) -> str:
        if self._session is None:
            return "Локальная модель"
        return self._session.active_model_display_name

    def _current_home_moment(self) -> str:
        # Read under the same lock used by Presentation mutations.
        with self._session_lock:
            if self._session is None:
                return "ordinary"
            return self._session.home_moment.value
""",
            label="add locked Home moment read",
        )

    text = read(path)
    send_turn_block = text.split("    def _send_turn(", 1)[1].split("    def _finish_turn", 1)[0]
    if "home_moment=self._current_home_moment()" not in send_turn_block:
        replace_once(
            path,
            """        return self._application.send_message(
            content,
            project_id=HOME_PROJECT_ID,
            conversation_id=self._conversation_id,
        )
""",
            """        return self._application.send_message(
            content,
            project_id=HOME_PROJECT_ID,
            conversation_id=self._conversation_id,
            home_moment=self._current_home_moment(),
        )
""",
            label="send current Home moment with chat turn",
        )

    text = read(path)
    cont_block = text.split("    def continueContinuityThread(", 1)[1].split("    @Slot()", 1)[0]
    if "home_moment=" not in cont_block:
        replace_once(
            path,
            """        self._turn_in_flight = True
        future = self._executor.submit(
            self._application.continue_continuity_thread,
            thread_id,
            conversation_id=self._conversation_id,
            project_id=HOME_PROJECT_ID,
        )
""",
            """        home_moment = self._current_home_moment()
        self._turn_in_flight = True
        future = self._executor.submit(
            self._application.continue_continuity_thread,
            thread_id,
            conversation_id=self._conversation_id,
            project_id=HOME_PROJECT_ID,
            home_moment=home_moment,
        )
""",
            label="preserve Home moment when resuming a thread",
        )

    # ------------------------------------------------------------------
    # 9. Regression tests.
    # ------------------------------------------------------------------
    append_test(
        "tests/test_capability_router.py",
        "def test_conversation_first_disables_semantic_hijack_but_keeps_explicit_commands():",
        """
def test_conversation_first_disables_semantic_hijack_but_keeps_explicit_commands():
    class Exploding:
        def classify(self, message):
            raise AssertionError("semantic classifier must not run in conversation-first mode")

    router = NaturalLanguageCapabilityRouter(Exploding())
    personal = (
        "Маш, всё, дела на сегодня закончились. "
        "Иди сюда, хочу просто немного побыть с тобой."
    )

    assert router.route(
        personal,
        allow_semantic=False,
        explicit_only=True,
    ) is None

    explicit = router.route(
        "Добавь мне задачу купить молоко",
        allow_semantic=False,
        explicit_only=True,
    )
    assert explicit is not None
    assert explicit.intent is CapabilityIntent.CREATE_COMMITMENT
""",
    )

    append_test(
        "tests/test_capability_router.py",
        "def test_local_semantic_classifier_can_return_plain_conversation():",
        """
def test_local_semantic_classifier_can_return_plain_conversation():
    provider = FakeProvider(response_text=json.dumps({
        "intent": None,
        "confidence": 0.99,
        "entity": None,
        "temporal_scope": None,
    }, ensure_ascii=False))
    profiles = SimpleNamespace(get_active_profile=lambda: SimpleNamespace(
        provider_id=provider.provider_id,
        model_id=provider.model_id,
        timeout_seconds=30.0,
    ))
    classifier = LocalSemanticIntentClassifier(
        router=ModelRouter([provider]),
        identity_kernel=IdentityKernel(
            IdentityStore(ROOT / "identity" / "masha.identity.json")
        ),
        model_profiles=profiles,
    )

    assert classifier.classify(
        "Маш, всё, дела на сегодня закончились. Иди сюда."
    ) is None
    assert provider.last_request is not None
    assert "ordinary conversation" in provider.last_request.messages[0].content
    assert "intent=null" in provider.last_request.messages[0].content
""",
    )

    append_test(
        "tests/test_context_compiler.py",
        "def test_special_evening_changes_conversation_rhythm_without_becoming_memory():",
        """
def test_special_evening_changes_conversation_rhythm_without_becoming_memory():
    compiler = ConversationContextCompiler(
        lambda: datetime(2026, 8, 20, 1, 12, tzinfo=timezone.utc)
    )
    identity = IdentityKernel(
        IdentityStore(PROJECT_ROOT / "identity" / "masha.identity.json")
    ).build_context()

    request = compiler.compile(
        messages=(ModelMessage(role="user", content="Маша, какая красивая ночь."),),
        identity_context=identity,
        working_memory=[],
        home_moment="special_evening",
    )

    private = request.private_context
    assert private["home_moment"] == "special_evening"
    assert "РЕЖИМ «ВДВОЁМ»" in private["home_moment_contract"]
    assert "Не устраивай интервью" in private["home_moment_contract"]
    assert "человеческий смысл" in private["home_moment_contract"]
    assert private["memory_context"] == []
""",
    )

    append_test(
        "tests/test_application_boundary.py",
        "def test_special_evening_personal_sentence_reaches_model_instead_of_shelf_router(tmp_path):",
        """
def test_special_evening_personal_sentence_reaches_model_instead_of_shelf_router(tmp_path):
    _, provider, application = _application(tmp_path)
    phrase = (
        "Маш, всё, дела на сегодня закончились. "
        "Иди сюда, хочу просто немного побыть с тобой."
    )

    result = application.send_message(
        phrase,
        project_id=PROJECT_ID,
        home_moment="special_evening",
    )

    assert result.status is ConversationTurnStatus.COMPLETED
    assert result.assistant_message is not None
    assert result.assistant_message.content == provider.response_text
    assert provider.last_request is not None
    assert provider.last_request.private_context["home_moment"] == "special_evening"
    assert "РЕЖИМ «ВДВОЁМ»" in (
        provider.last_request.private_context["home_moment_contract"]
    )
""",
    )

    ensure_python_compiles()

except PatchError as exc:
    print()
    print(f"[STOP] {exc}")
    print("No files were written.")
    raise SystemExit(1)

for path, text in STAGED.items():
    path.write_text(text, encoding="utf-8")
    print(f"[WRITE] {path.relative_to(ROOT)}")

print()
print("Package A applied.")
print("Review: git diff")
print(
    "Tests: .\\.venv\\Scripts\\python.exe -m pytest "
    "tests/test_capability_router.py tests/test_context_compiler.py "
    "tests/test_chat_capability_integration.py tests/test_application_boundary.py -q"
)

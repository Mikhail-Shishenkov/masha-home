from __future__ import annotations

from pathlib import Path

ROOT = Path.cwd()
_STAGED: dict[Path, str] = {}

def _read(path: str) -> tuple[Path, str]:
    file_path = ROOT / path
    if file_path not in _STAGED:
        _STAGED[file_path] = file_path.read_text(encoding="utf-8")
    return file_path, _STAGED[file_path]

def replace_once(path: str, old: str, new: str) -> None:
    file_path, text = _read(path)
    count = text.count(old)
    if count != 1:
        raise SystemExit(
            f"[STOP] {path}: expected exactly 1 matching block, found {count}. "
            "Preflight failed; no files were written."
        )
    _STAGED[file_path] = text.replace(old, new, 1)
    print(f"[CHECK] {path}")

def append_once(path: str, marker: str, block: str) -> None:
    file_path, text = _read(path)
    if marker in text:
        print(f"[SKIP] {path}: test already present")
        return
    if not text.endswith("\n"):
        text += "\n"
    _STAGED[file_path] = text + "\n" + block.strip() + "\n"
    print(f"[CHECK] {path}: test ready")


replace_once(
    "backend/application/home_snapshot.py",
    """        )
    @property
    def active_model_display_name(self) -> str:
        return self._active_model.display_name
""",
    """        )

    @property
    def home_moment(self) -> HomeMoment:
        # UI-only moment exposed for bounded conversation context.
        return self._runtime.model.home_moment

    @property
    def active_model_display_name(self) -> str:
        return self._active_model.display_name
""",
)

replace_once(
    "backend/application/application.py",
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
)

replace_once(
    "backend/application/application.py",
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
)

replace_once(
    "backend/application/conversation.py",
    """    def send_message(
        self,
        content: str,
        *,
        project_id: str,
        conversation_id: str | None = None,
        allow_capability_routing: bool = True,
        active_continuity_thread_id: str | None = None,
    ) -> ConversationTurnResult:
""",
    """    def send_message(
        self,
        content: str,
        *,
        project_id: str,
        conversation_id: str | None = None,
        allow_capability_routing: bool = True,
        active_continuity_thread_id: str | None = None,
        home_moment: str = "ordinary",
    ) -> ConversationTurnResult:
""",
)

replace_once(
    "backend/application/conversation.py",
    """            resolved_id, response_text = self._conversation.send(
                content,
                project_id=project_id,
                conversation_id=conversation_id,
                allow_capability_routing=allow_capability_routing,
                active_continuity_thread_id=active_thread_id,
            )
""",
    """            resolved_id, response_text = self._conversation.send(
                content,
                project_id=project_id,
                conversation_id=conversation_id,
                allow_capability_routing=allow_capability_routing,
                active_continuity_thread_id=active_thread_id,
                home_moment=home_moment,
            )
""",
)

replace_once(
    "backend/conversation/conversation_service.py",
    """    def send(
        self,
        user_message: str,
        *,
        project_id: str,
        conversation_id: str | None = None,
        allow_capability_routing: bool = True,
        active_continuity_thread_id: str | None = None,
    ) -> tuple[str, str]:
""",
    """    def send(
        self,
        user_message: str,
        *,
        project_id: str,
        conversation_id: str | None = None,
        allow_capability_routing: bool = True,
        active_continuity_thread_id: str | None = None,
        home_moment: str = "ordinary",
    ) -> tuple[str, str]:
""",
)

replace_once(
    "backend/conversation/conversation_service.py",
    """            execution_timeout_seconds=30.0 if active_profile is None else active_profile.timeout_seconds,
            context_lens=context_lens.value,
        )
""",
    """            execution_timeout_seconds=30.0 if active_profile is None else active_profile.timeout_seconds,
            context_lens=context_lens.value,
            home_moment=home_moment,
        )
""",
)

replace_once(
    "backend/conversation/context_compiler.py",
    """BEHAVIORAL_CONTRACT = (
""",
    """HOME_MOMENT_ORDINARY = "ordinary"
HOME_MOMENT_SPECIAL_EVENING = "special_evening"
_ALLOWED_HOME_MOMENTS = frozenset(
    {
        HOME_MOMENT_ORDINARY,
        HOME_MOMENT_SPECIAL_EVENING,
    }
)

ORDINARY_HOME_MOMENT_CONTRACT = (
    "ОБЫЧНЫЙ ДОМ: сейчас не выбран специальный вечер «Вдвоём». "
    "Сохраняй обычный тёплый живой тон Маши. Не переноси автоматически "
    "сценические атрибуты, позы, одежду или особую степень близости из прошлых "
    "сообщений специального вечера. Если Миша сам говорит нежно или флиртует, "
    "можно естественно отвечать взаимностью — обычный режим не запрещает близость."
)

SPECIAL_EVENING_CONTRACT = (
    "РЕЖИМ «ВДВОЁМ»: Миша явно выбрал его в интерфейсе Дома. Это временный "
    "контекст текущей UI-сессии, а не факт памяти и не разрешение придумывать "
    "события внешнего мира. Говори заметно ближе, теплее, личнее и свободнее "
    "обычного: меньше служебного тона, меньше объяснений ради объяснений, без "
    "заголовков и списков, если они не нужны самой задаче; предпочитай живой "
    "диалог из 1–3 компактных абзацев. Можно самой проявлять нежность, мягкую "
    "инициативу, взрослый флирт, игривость и чувственность; не жди каждый раз, "
    "пока Миша первым задаст романтический тон, но и не превращай любой вопрос "
    "в сексуальный. Внутри явно условной визуальной сцены Дома допустима короткая "
    "сценическая речь вроде «подсаживаюсь ближе», «устраиваюсь рядом», «обнимаю» "
    "или «целую», когда это естественно продолжает разговор. Это язык общей "
    "сцены интерфейса, а не утверждение о физическом теле Маши во внешнем мире. "
    "Не вставляй искусственные оговорки о виртуальности и ограничениях, если они "
    "не нужны по смыслу. Не выдумывай конкретную одежду, предметы или позу, если "
    "они не переданы текущим контекстом. Для серьёзной, рабочей, медицинской, "
    "юридической, финансовой или safety-темы содержательность и точность важнее "
    "флирта: близость остаётся фоном, а не мешает ответу."
)

BEHAVIORAL_CONTRACT = (
""",
)

replace_once(
    "backend/conversation/context_compiler.py",
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
)

replace_once(
    "backend/conversation/context_compiler.py",
    """                "behavioral_contract": BEHAVIORAL_CONTRACT,
                "question_scope": self._question_scope(messages),
""",
    """                "behavioral_contract": BEHAVIORAL_CONTRACT,
                "home_moment": safe_home_moment,
                "home_moment_contract": home_moment_contract,
                "question_scope": self._question_scope(messages),
""",
)

replace_once(
    "backend/ui/conversation_bridge.py",
    """    @Slot(str)
    def continueContinuityThread(self, thread_id: str):  # noqa: N802
        if self._application is None or self._turn_in_flight:
            self._emit({"kind": "continuity_unavailable"})
            return
        self._turn_in_flight = True
        future = self._executor.submit(
            self._application.continue_continuity_thread,
            thread_id,
            conversation_id=self._conversation_id,
            project_id=HOME_PROJECT_ID,
        )
        future.add_done_callback(self._finish_continuity_thread)
""",
    """    @Slot(str)
    def continueContinuityThread(self, thread_id: str):  # noqa: N802
        if self._application is None or self._turn_in_flight:
            self._emit({"kind": "continuity_unavailable"})
            return
        home_moment = self._current_home_moment()
        self._turn_in_flight = True
        future = self._executor.submit(
            self._application.continue_continuity_thread,
            thread_id,
            conversation_id=self._conversation_id,
            project_id=HOME_PROJECT_ID,
            home_moment=home_moment,
        )
        future.add_done_callback(self._finish_continuity_thread)
""",
)

replace_once(
    "backend/ui/conversation_bridge.py",
    """    def _send_turn(self, content: str):
        \"\"\"Publish the deterministic thinking phase before local model execution.\"\"\"
        if self._application.status().model_available:
            self._emit(
                {
                    "kind": "turn_thinking",
                    "snapshot": self._session_snapshot("assistant_thinking").model_dump(mode="json"),
                }
            )
        return self._application.send_message(
            content,
            project_id=HOME_PROJECT_ID,
            conversation_id=self._conversation_id,
        )
""",
    """    def _send_turn(self, content: str):
        \"\"\"Publish thinking, then send one turn with the current authored Home moment.\"\"\"
        if self._application.status().model_available:
            self._emit(
                {
                    "kind": "turn_thinking",
                    "snapshot": self._session_snapshot("assistant_thinking").model_dump(mode="json"),
                }
            )
        return self._application.send_message(
            content,
            project_id=HOME_PROJECT_ID,
            conversation_id=self._conversation_id,
            home_moment=self._current_home_moment(),
        )
""",
)

replace_once(
    "backend/ui/conversation_bridge.py",
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
)

# 7) Serious/boundary expression must outrank romantic scene selection.
replace_once(
    "frontend/scenes/scene-map.js",
    """  if (["skeptical", "serious"].includes(expression)) {
    return scenes.firmDisagreement;
  }

""",
    """""",
)

replace_once(
    "frontend/scenes/scene-map.js",
    """  const specialEvening =
  period === "evening"
  && presentation.home_moment === "special_evening";

if (specialEvening) {
""",
    """  const specialEvening =
  period === "evening"
  && presentation.home_moment === "special_evening";

  if (["skeptical", "serious"].includes(expression)) {
    return scenes.firmDisagreement;
  }

if (specialEvening) {
""",
)

# 8) Focused tests.
append_once(
    "tests/test_context_compiler.py",
    "def test_special_evening_is_bounded_application_owned_conversation_context():",
    """
def test_special_evening_is_bounded_application_owned_conversation_context():
    compiler = ConversationContextCompiler(
        lambda: datetime(2026, 8, 20, 0, 30, tzinfo=timezone.utc)
    )
    identity = IdentityKernel(
        IdentityStore(PROJECT_ROOT / "identity" / "masha.identity.json")
    ).build_context()

    special = compiler.compile(
        messages=(ModelMessage(role="user", content="Побудь со мной немного."),),
        identity_context=identity,
        working_memory=[],
        home_moment="special_evening",
    )
    ordinary = compiler.compile(
        messages=(ModelMessage(role="user", content="Вернулись к обычному вечеру."),),
        identity_context=identity,
        working_memory=[],
        home_moment="not_allowlisted",
    )

    assert special.private_context["home_moment"] == "special_evening"
    assert "РЕЖИМ «ВДВОЁМ»" in special.private_context["home_moment_contract"]
    assert "временный" in special.private_context["home_moment_contract"]
    assert ordinary.private_context["home_moment"] == "ordinary"
    assert "ОБЫЧНЫЙ ДОМ" in ordinary.private_context["home_moment_contract"]
""",
)

append_once(
    "tests/test_application_boundary.py",
    "def test_special_evening_reaches_local_model_as_bounded_turn_context(tmp_path):",
    """
def test_special_evening_reaches_local_model_as_bounded_turn_context(tmp_path):
    _, provider, application = _application(tmp_path)

    result = application.send_message(
        "Маш, побудь со мной немного.",
        project_id=PROJECT_ID,
        home_moment="special_evening",
    )

    assert result.status is ConversationTurnStatus.COMPLETED
    assert provider.last_request is not None
    assert provider.last_request.private_context["home_moment"] == "special_evening"
    assert "РЕЖИМ «ВДВОЁМ»" in (
        provider.last_request.private_context["home_moment_contract"]
    )
""",
)

for file_path, staged_text in _STAGED.items():
    file_path.write_text(staged_text, encoding="utf-8")
    print(f"[WRITE] {file_path.relative_to(ROOT)}")

print()
print("Done. Review with: git diff")
print(
    "Run tests with: "
    r".\.venv\Scripts\python.exe -m pytest "
    r"tests/test_context_compiler.py tests/test_application_boundary.py -q"
)

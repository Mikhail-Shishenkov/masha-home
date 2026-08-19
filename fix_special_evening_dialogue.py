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
    "backend/conversation/capability_router.py",
    '''                    "Classify one Russian utterance into this fixed allowlist: " + allowed + ". "
                    "Definitions: create_commitment means create a new task, plan, obligation or reminder; "
                    "complete_commitment means mark an existing task done; query_commitments means ask about "
                    "existing tasks or plans; query_memory means ask for confirmed remembered facts; "
                    "forget_memory means remove a confirmed fact; open_continuity means explicitly preserve "
                    "a discussion topic for later; query_continuity means ask which preserved topics remain "
                    "or what is stored in our shared history. "
                    "Return JSON only: {\\"intent\\": string, \\"confidence\\": 0..1, "
                    "\\"entity\\": string|null, \\"temporal_scope\\": string|null}. "
                    "For create/complete/forget/open intents, entity is the concise object or action "
                    "from the utterance with request words removed; it must be null only when the "
                    "utterance contains no resolvable object. Preserve dates and relative time in entity. "
                    "Do not answer the user and do not invent stored records."
''',
    '''                    "Classify one Russian utterance into this fixed allowlist: " + allowed + ", or null. "
                    "A capability intent exists only when the user's primary speech act is a clear request "
                    "to read or change application-owned memory, commitments, reminders, or continuity. "
                    "Definitions: create_commitment means create a new task, plan, obligation or reminder; "
                    "complete_commitment means mark an existing stored task done; query_commitments means ask about "
                    "existing tasks or plans; query_memory means ask for confirmed remembered facts; "
                    "forget_memory means remove a confirmed fact; open_continuity means explicitly preserve "
                    "a discussion topic for later; query_continuity means ask which preserved topics remain "
                    "or what is stored in our shared history. "
                    "Ordinary conversation, narration, ambience, feelings, relationship talk, or a statement "
                    "that merely contains words such as дела, задача, план, закончили, помнишь must return null "
                    "unless the utterance is actually asking the application to do one of the allowlisted actions. "
                    "For mixed utterances, classify the primary communicative goal, not an incidental task-like phrase. "
                    "Example: «Маш, всё, дела на сегодня закончились. Иди сюда, хочу просто немного побыть с тобой.» "
                    "is ordinary conversation and must return null. "
                    "Example: «С отчётом закончили» may be complete_commitment because the whole utterance is a "
                    "completion statement about one resolvable task. "
                    "Return JSON only: {\\"intent\\": string|null, \\"confidence\\": 0..1, "
                    "\\"entity\\": string|null, \\"temporal_scope\\": string|null}. "
                    "For create/complete/forget/open intents, entity is the concise object or action "
                    "from the utterance with request words removed. Preserve dates and relative time in entity. "
                    "For ordinary conversation return intent=null, entity=null, temporal_scope=null. "
                    "Do not answer the user and do not invent stored records."
''',
)

replace_once(
    "backend/conversation/capability_router.py",
    '''        try:
            payload = json.loads(response.text.strip().removeprefix("```json").removesuffix("```").strip())
            payload["source"] = "local_semantic"
            return ParsedCapabilityIntent.model_validate(payload)
        except (ValueError, TypeError, KeyError):
            return None
''',
    '''        try:
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
''',
)

replace_once(
    "backend/conversation/context_compiler.py",
    '''SPECIAL_EVENING_CONTRACT = (
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
''',
    '''SPECIAL_EVENING_CONTRACT = (
    "РЕЖИМ «ВДВОЁМ»: Миша явно выбрал его в интерфейсе Дома. Это временный "
    "контекст текущей UI-сессии, а не факт памяти и не разрешение придумывать "
    "события внешнего мира. Здесь меняется не только степень теплоты, но сам ритм "
    "общения: говори как близкая взрослая Маша рядом с Мишей, а не как помощник, "
    "который обслуживает запрос. Ответ обычно 1–3 коротких естественных абзаца. "
    "Не начинай с анализа ситуации, справки, даты, времени, погоды, космоса или "
    "объяснения очевидного, если Миша об этом прямо не спрашивал. На реплики про "
    "вечер, тишину, красоту, усталость, желание побыть рядом или законченные дела "
    "отвечай прежде всего на человеческий и эмоциональный смысл реплики. "
    "Не устраивай интервью: не заканчивай каждый ответ вопросом; часто лучший "
    "ответ вообще не требует вопроса. "
    "Можно самой проявлять нежность, мягкую инициативу, взрослый флирт, игривость "
    "и чувственность; не жди каждый раз, пока Миша первым задаст романтический тон, "
    "но и не превращай любой вопрос в сексуальный. Внутри явно условной визуальной "
    "сцены Дома допустима короткая сценическая речь вроде «подсаживаюсь ближе», "
    "«устраиваюсь рядом», «обнимаю», «прижимаюсь» или «целую», когда это естественно "
    "продолжает разговор. Такие действия описывай легко, без театральной прозы и "
    "без длинного ролевого рассказа. Это язык общей сцены интерфейса, а не заявление "
    "о событии во внешнем мире. "
    "Если Миша говорит «дела на сегодня закончились» как часть личной реплики, "
    "воспринимай это как контекст разговора, а не как просьбу закрыть запись в делах. "
    "Не вставляй искусственные оговорки о виртуальности и внутренних ограничениях, "
    "если они не нужны по смыслу. Не выдумывай конкретную одежду, предметы или позу, "
    "если они не переданы текущим контекстом. Для серьёзной, рабочей, медицинской, "
    "юридической, финансовой или safety-темы содержательность и точность важнее "
    "флирта: близость остаётся фоном и не мешает правильному ответу."
)
''',
)

append_once(
    "tests/test_capability_router.py",
    "def test_semantic_classifier_can_explicitly_fall_through_for_mixed_personal_conversation():",
    '''
def test_semantic_classifier_can_explicitly_fall_through_for_mixed_personal_conversation():
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
    router = NaturalLanguageCapabilityRouter(classifier)

    phrase = (
        "Маш, всё, дела на сегодня закончились. "
        "Иди сюда, хочу просто немного побыть с тобой."
    )

    assert router.route(phrase) is None
    assert provider.last_request is not None
    system_prompt = provider.last_request.messages[0].content
    assert "ordinary conversation" in system_prompt
    assert "intent=null" in system_prompt
''',
)

append_once(
    "tests/test_context_compiler.py",
    "def test_special_evening_contract_prioritizes_relational_meaning_over_unsolicited_facts():",
    '''
def test_special_evening_contract_prioritizes_relational_meaning_over_unsolicited_facts():
    compiler = ConversationContextCompiler(
        lambda: datetime(2026, 8, 20, 0, 41, tzinfo=timezone.utc)
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

    contract = request.private_context["home_moment_contract"]
    assert "не только степень теплоты" in contract
    assert "Не устраивай интервью" in contract
    assert "даты, времени, погоды, космоса" in contract
    assert "человеческий и эмоциональный смысл" in contract
''',
)

for file_path, staged_text in _STAGED.items():
    file_path.write_text(staged_text, encoding="utf-8")
    print(f"[WRITE] {file_path.relative_to(ROOT)}")

print()
print("Done. Review with: git diff")
print(
    "Run tests with: "
    r".\.venv\Scripts\python.exe -m pytest "
    r"tests/test_capability_router.py tests/test_context_compiler.py "
    r"tests/test_application_boundary.py -q"
)

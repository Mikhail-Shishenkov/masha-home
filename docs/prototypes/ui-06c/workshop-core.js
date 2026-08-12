(function (root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  root.MashaCapabilityWorkshop = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  "use strict";

  const VISUAL_IDENTITY_ID = "masha.visual.identity.canonical-v4";
  const ROOM_ASSET_ID = "scene.home.canonical.static";
  const PHASES = Object.freeze(["appeared", "focused", "waiting", "resolved", "dismissed"]);

  const SCENES = Object.freeze([
    scene({
      id: "commitment",
      nav: "Срок",
      place: "на столике",
      zone: "table",
      eyebrow: "важное дело",
      title: "Отправить отчёт",
      summary: "Срок сегодня в 18:00. Маша показывает обязательство, но не превращает Дом в список задач.",
      kind: "commitment",
      details: Object.freeze({ due: "Сегодня, 18:00", status: "Осталось 2 часа 15 минут", context: "Рабочий проект" }),
      actions: actions("Открыть обязательство", "Не сейчас"),
      primaryReceipt: "Откроется настоящее обязательство и его подтверждённая история.",
      secondaryReceipt: "Объект спокойно уйдёт со стола. Само обязательство не изменится.",
    }),
    scene({
      id: "confirmation",
      nav: "Решение",
      place: "между нами",
      zone: "table",
      eyebrow: "нужно твоё решение",
      title: "Запомнить это как наш момент?",
      summary: "«Мы впервые увидели все возможности Дома в одном пространстве». До ответа Миши память не меняется.",
      kind: "confirmation",
      details: Object.freeze({ type: "Общая история", effect: "Добавится одна подтверждённая запись", origin: "Из текущего разговора" }),
      actions: actions("Да, сохранить", "Не сохранять", "Изменить"),
      primaryReceipt: "После подключения будет подтверждена только показанная запись.",
      secondaryReceipt: "Ничего не сохранено.",
    }),
    scene({
      id: "activity",
      nav: "Работа",
      place: "у рабочего стола",
      zone: "desk",
      eyebrow: "Маша занята",
      title: "Проверяю интерфейс Дома",
      summary: "Реальная работа видна как последовательность проверяемых шагов, а не как бесконечный Loading…",
      kind: "activity",
      details: Object.freeze({ steps: Object.freeze([
        Object.freeze({ label: "Собрала контекст", state: "done" }),
        Object.freeze({ label: "Сверяю границы интерфейса", state: "active" }),
        Object.freeze({ label: "Подготовлю проверенный результат", state: "waiting" }),
      ]), status: "Выполняется локально", boundary: "Без сети и внешних действий" }),
      actions: actions("Показать ход работы", "Остановить после шага"),
      primaryReceipt: "Откроется подробный, но человекочитаемый ход реальной Activity.",
      secondaryReceipt: "Будущие шаги будут остановлены на безопасной границе.",
    }),
    scene({
      id: "reminder",
      nav: "Напомнила",
      place: "на столике",
      zone: "table",
      eyebrow: "я обещала напомнить",
      title: "Срок отчёта уже наступил.",
      summary: "Пока тебя не было, обязательство стало просроченным. Это факт времени, а не оценка тебя.",
      kind: "proactive",
      details: Object.freeze({ why: "Явное обязательство · разрешённое напоминание", delivered: "Одно сообщение, без повторов", policy: "Тихие часы и лимит соблюдены" }),
      actions: actions("Показать обязательство", "Не сейчас"),
      primaryReceipt: "Напоминание свяжется с исходным обязательством, не меняя его статус.",
      secondaryReceipt: "Сообщение будет убрано и не появится снова при перезапуске.",
    }),
    scene({
      id: "checkin",
      nav: "Заглянула",
      place: "рядом с диваном",
      zone: "sofa",
      eyebrow: "Маша рядом",
      title: "Просто заглянула. Как ты там?",
      summary: "Долгое отсутствие — только сигнал для мягкого приглашения, а не диагноз и не повод давить.",
      kind: "checkin",
      details: Object.freeze({ reason: "Разрешённый check-in после отсутствия", restraint: "Не чаще заданного лимита", promise: "Можно просто сказать «не сейчас»" }),
      actions: actions("Ответить Маше", "Не сейчас"),
      primaryReceipt: "Откроется обычный разговор — без отдельного психологического режима.",
      secondaryReceipt: "Дом вернётся к тихому присутствию.",
    }),
    scene({
      id: "continuity",
      nav: "Наша история",
      place: "на нашей полке",
      zone: "sofa",
      eyebrow: "что между нами продолжается",
      title: "Не просто память о тебе. Память о нас.",
      summary: "Подтверждённые общие моменты и открытые нити живут рядом, но не смешиваются с фактами и обязательствами.",
      kind: "continuity",
      details: Object.freeze({ moment: "Первый полностью локальный запуск Маши", thread: "Придумать домашний ритуал запуска", state: "Открытая нить" }),
      actions: actions("Продолжить эту нить", "Оставить на полке"),
      primaryReceipt: "Разговор продолжится с bounded-контекстом выбранной общей нити.",
      secondaryReceipt: "Нить останется открытой и ничего не потребует прямо сейчас.",
    }),
    scene({
      id: "reflection",
      nav: "Мысль Маши",
      place: "между нами",
      zone: "sofa",
      eyebrow: "я тут подумала",
      title: "Мне кажется, мы строим не помощника, а устойчивое общее место.",
      summary: "Это собственное понимание Маши с основаниями и уверенностью — не факт о Мише и не скрытый психологический профиль.",
      kind: "reflection",
      details: Object.freeze({ confidence: "Уверенность 78%", evidence: "4 подтверждённых основания", offer: "Могу помочь превратить это в следующий конкретный шаг" }),
      actions: actions("Принять эту мысль", "Не согласен", "Давай пересмотрим"),
      primaryReceipt: "Мысль сможет стать принятой рефлексией Маши, не изменяя Identity.",
      secondaryReceipt: "Интерпретация не будет закреплена.",
    }),
    scene({
      id: "skills",
      nav: "Навыки",
      place: "в рабочем уголке",
      zone: "desk",
      eyebrow: "что я умею делать",
      title: "Навыки с понятными границами",
      summary: "Установка, целостность и разрешения разделены. Сам факт наличия навыка ещё не даёт ему права действовать.",
      kind: "skills",
      details: Object.freeze({ skill: "Project Observer", integrity: "Проверен", permission: "Только чтение · Masha Home", autonomy: "Уровень 1 из 4" }),
      actions: actions("Посмотреть границы", "Добавить навык"),
      primaryReceipt: "Откроется единый Permissions UX без UUID, digest и внутренних grant ID.",
      secondaryReceipt: "Появится локальный выбор папки или ZIP и отдельный preview до установки.",
    }),
    scene({
      id: "models",
      nav: "Модель",
      place: "в настройке Дома",
      zone: "desk",
      eyebrow: "кто сейчас отвечает",
      title: "Маша остаётся Машей.",
      summary: "Меняется только локальный исполнитель ответа. Identity, память, время и общая история остаются прежними.",
      kind: "models",
      details: Object.freeze({ primary: "Primary · qwen3.5:9b · доступна", fast: "Fast · qwen3.5:4b · доступна", experimental: "Experimental · не настроена" }),
      actions: actions("Выбрать Fast", "Оставить Primary"),
      primaryReceipt: "Перед применением будет проверена локальная доступность. Автоматического fallback нет.",
      secondaryReceipt: "Primary останется активной моделью.",
    }),
    scene({
      id: "runtime",
      nav: "Состояние",
      place: "у границы Дома",
      zone: "desk",
      eyebrow: "локальная модель не отвечает",
      title: "Я здесь, но сейчас не могу ответить.",
      summary: "Комната, Identity, память и история остаются на месте. Ошибка исполнения не изображается как исчезновение Маши.",
      kind: "runtime",
      details: Object.freeze({ model: "Ollama недоступна", memory: "Локальная память в порядке", safety: "Никакого внешнего fallback", recovery: "Можно проверить локальный runtime ещё раз" }),
      actions: actions("Проверить снова", "Открыть состояние Дома"),
      primaryReceipt: "Будет выполнена только локальная health-проверка, без отправки сообщения.",
      secondaryReceipt: "Откроется спокойное техническое пространство, отдельное от разговора.",
    }),
  ]);

  const SCENE_MAP = Object.freeze(Object.fromEntries(SCENES.map((item) => [item.id, item])));

  function initialState() {
    return freeze({ sceneId: SCENES[0].id, phase: "appeared", resolution: null, revision: 0 });
  }

  function reduce(state, event) {
    if (!event || typeof event.type !== "string") return state;
    if (event.type === "SELECT") {
      if (!SCENE_MAP[event.sceneId] || event.sceneId === state.sceneId) return state;
      return freeze({ sceneId: event.sceneId, phase: "appeared", resolution: null, revision: state.revision + 1 });
    }
    if (event.type === "NEXT" || event.type === "PREVIOUS") {
      const index = SCENES.findIndex((item) => item.id === state.sceneId);
      const offset = event.type === "NEXT" ? 1 : -1;
      const next = (index + offset + SCENES.length) % SCENES.length;
      return freeze({ sceneId: SCENES[next].id, phase: "appeared", resolution: null, revision: state.revision + 1 });
    }
    if (event.type === "FOCUS" && state.phase === "appeared") {
      return freeze({ sceneId: state.sceneId, phase: "focused", resolution: null, revision: state.revision + 1 });
    }
    if (event.type === "WAIT" && state.phase === "focused") {
      return freeze({ sceneId: state.sceneId, phase: "waiting", resolution: null, revision: state.revision + 1 });
    }
    if (event.type === "ACT" && state.phase === "waiting") {
      const sceneValue = SCENE_MAP[state.sceneId];
      const action = sceneValue.actions[event.actionIndex];
      if (!action) return state;
      const message = event.actionIndex === 0 ? sceneValue.primaryReceipt : sceneValue.secondaryReceipt;
      return freeze({ sceneId: state.sceneId, phase: event.actionIndex === 0 ? "resolved" : "dismissed", resolution: freeze({ label: action.label, message }), revision: state.revision + 1 });
    }
    if (event.type === "RESET" && state.phase !== "appeared") {
      return freeze({ sceneId: state.sceneId, phase: "appeared", resolution: null, revision: state.revision + 1 });
    }
    return state;
  }

  function project(state) {
    const selected = SCENE_MAP[state.sceneId] || SCENES[0];
    return freeze({
      visualIdentityId: VISUAL_IDENTITY_ID,
      roomAssetId: ROOM_ASSET_ID,
      index: SCENES.indexOf(selected),
      total: SCENES.length,
      phase: state.phase,
      phases: PHASES,
      scene: selected,
      resolution: state.resolution,
    });
  }

  function scene(value) { return freeze(value); }
  function actions(...labels) { return freeze(labels.map((label, index) => freeze({ id: `action-${index + 1}`, label }))); }
  function freeze(value) { return Object.freeze(value); }

  return Object.freeze({ VISUAL_IDENTITY_ID, ROOM_ASSET_ID, PHASES, SCENES, initialState, reduce, project });
});

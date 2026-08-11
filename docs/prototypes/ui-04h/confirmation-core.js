(function (root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  root.UI04H = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  "use strict";

  const registry = Object.freeze({
    "masha.visual.identity": Object.freeze({ kind: "identity", version: "canonical-v4" }),
    "scene.conversation": Object.freeze({ kind: "scene", source: "../../assets/ui-04g/conversation-candidate.png" }),
    "scene.idle": Object.freeze({ kind: "scene", source: "../../assets/ui-04g/canonical-master.png" }),
  });

  function initialState() {
    return freeze({
      phase: "conversation", safety: "normal", privacy: false, chrome: false,
      activityStatus: "idle", activityStep: 0, proactiveStatus: "idle", activeSurface: "conversation", revision: 0,
      messages: freeze([freeze({ id: "fixture-masha-1", role: "assistant", content: "Я здесь. С чего начнём?" })]),
      assistantStatus: "ready",
    });
  }

  function reduce(state, event) {
    const next = Object.assign({}, state);
    switch (event.type) {
      case "OPEN_CONFIRMATION": next.phase = "confirmation"; next.activeSurface = "decision"; break;
      case "OPEN_CONVERSATION": next.activeSurface = "conversation"; break;
      case "SEND_DRAFT":
        if (state.assistantStatus !== "ready") return state;
        const content = typeof event.content === "string" ? event.content.trim().slice(0, 500) : "";
        if (!content) return state;
        next.messages = freeze(state.messages.concat(freeze({ id: `fixture-user-${state.revision + 1}`, role: "user", content })));
        next.assistantStatus = "thinking";
        next.phase = "conversation";
        next.activeSurface = "conversation";
        break;
      case "SIMULATED_ASSISTANT_RESPONSE":
        if (state.assistantStatus !== "thinking") return state;
        next.messages = freeze(state.messages.concat(freeze({
          id: `fixture-masha-${state.revision + 1}`,
          role: "assistant",
          content: "Я тут. Давай спокойно продолжим.",
        })));
        next.assistantStatus = "ready";
        next.activeSurface = "conversation";
        break;
      case "OPEN_ACTIVITY":
        if (state.activityStatus === "idle") {
          next.activityStatus = "running";
          next.activityStep = 1;
        }
        next.activeSurface = "activity";
        break;
      case "ACTIVITY_PROGRESS":
        if (state.activityStatus !== "running") return state;
        next.activityStep = Math.min(state.activityStep + 1, 3);
        break;
      case "ACTIVITY_COMPLETE":
        if (state.activityStatus !== "running") return state;
        next.activityStatus = "completed";
        next.activityStep = 3;
        break;
      case "ACTIVITY_FAIL":
        if (state.activityStatus !== "running") return state;
        next.activityStatus = "failed";
        break;
      case "DISMISS_ACTIVITY":
        if (state.activityStatus === "idle") return state;
        next.activityStatus = "idle";
        next.activityStep = 0;
        next.activeSurface = "conversation";
        break;
      case "APPEAR_CHECKIN":
        if (state.safety === "stopped") return state;
        next.proactiveStatus = "pending";
        next.activeSurface = "checkin";
        break;
      case "ACKNOWLEDGE_CHECKIN":
        if (state.safety === "stopped" || state.proactiveStatus !== "pending") return state;
        next.proactiveStatus = "acknowledged";
        next.activeSurface = "conversation";
        break;
      case "DISMISS_CHECKIN":
        if (state.safety === "stopped" || state.proactiveStatus !== "pending") return state;
        next.proactiveStatus = "dismissed";
        next.activeSurface = "conversation";
        break;
      case "CONFIRM_PREVIEW":
        if (state.safety === "stopped" || state.phase !== "confirmation") return state;
        next.phase = "confirmed";
        next.activeSurface = "conversation";
        break;
      case "DISMISS_PREVIEW":
        if (state.safety === "stopped" || state.phase !== "confirmation") return state;
        next.phase = "dismissed";
        next.activeSurface = "conversation";
        break;
      case "EMERGENCY_STOP": next.safety = "stopped"; next.activeSurface = "conversation"; break;
      case "RESUME_PRESENTATION": next.safety = "normal"; break;
      case "TOGGLE_PRIVACY": next.privacy = !state.privacy; break;
      case "TOGGLE_CHROME": next.chrome = !state.chrome; break;
      default: return state;
    }
    next.revision = state.revision + 1;
    return freeze(next);
  }

  function project(state) {
    const decisionVisible = state.safety === "normal" && state.phase === "confirmation" && state.activeSurface === "decision";
    const proactiveVisible = state.safety === "normal" && state.proactiveStatus === "pending" && state.activeSurface === "checkin";
    const activityVisible = state.activityStatus !== "idle" && state.activeSurface === "activity";
    const conversationVisible = state.activeSurface === "conversation" || state.safety === "stopped";
    return freeze({
      identityId: "masha.visual.identity",
      sceneId: "scene.conversation",
      sceneSource: registry["scene.conversation"].source,
      decisionVisible,
      activityVisible,
      proactiveVisible,
      conversationVisible,
      focus: conversationVisible ? "conversation" : state.activeSurface,
      decisionState: state.phase,
      safety: state.safety,
      privacy: state.privacy,
      chrome: state.chrome,
      conversation: freeze({
        origin: "между нами",
        messages: freeze(state.messages.map((message) => freeze({ ...message }))),
        assistantStatus: state.assistantStatus,
        composerPlaceholder: "Напиши Маше…",
      }),
      decision: freeze({
        title: "Нужно твоё решение",
        preview: "Сохранить договорённость: вернуться к плану утром?",
        confirmLabel: "Подтвердить",
        editLabel: "Изменить",
        dismissLabel: "Не сейчас",
      }),
      activity: freeze(activityPresentation(state.activityStatus, state.activityStep)),
      proactive: freeze({
        status: state.proactiveStatus,
        eyebrow: "Маша рядом",
        message: "Просто заглянула. Как ты там?",
        replyLabel: "Ответить",
        dismissLabel: "Не сейчас",
      }),
    });
  }

  function activityPresentation(status, step) {
    const steps = ["собираю контекст", "сверяю детали", "готовлю результат"];
    if (status === "completed") return { status, eyebrow: "готово", title: "Можно двигаться дальше.", detail: "Результат подготовлен. Он не был отправлен или сохранён.", actionLabel: "Вернуться к разговору", step: 3, steps };
    if (status === "failed") return { status, eyebrow: "нужна пауза", title: "Не получилось закончить.", detail: "Никаких действий не выполнено. Можно попробовать иначе.", actionLabel: "Закрыть", step, steps };
    return { status, eyebrow: "Маша занята", title: "Разбираюсь с этим.", detail: "Пока только локальная визуальная демонстрация хода задачи.", actionLabel: "Показать следующий шаг", step, steps };
  }

  function freeze(value) { return Object.freeze(value); }
  return Object.freeze({ registry, initialState, reduce, project });
});

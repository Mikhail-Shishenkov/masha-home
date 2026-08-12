"use strict";

const workshop = window.MashaCapabilityWorkshop;
const home = document.getElementById("capability-workshop");
const surface = document.getElementById("capability-surface");
const counter = document.getElementById("scene-counter");
const eyebrow = document.getElementById("surface-eyebrow");
const place = document.getElementById("surface-place");
const title = document.getElementById("surface-title");
const summary = document.getElementById("surface-summary");
const body = document.getElementById("surface-body");
const actions = document.getElementById("surface-actions");
const receipt = document.getElementById("surface-receipt");
const dots = document.getElementById("scene-dots");
let state = workshop.initialState();

function element(tag, className, content) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (content !== undefined) node.textContent = content;
  return node;
}

function detailLine(label, value, stateName) {
  const row = element("div", "detail-line");
  if (stateName) row.dataset.state = stateName;
  row.append(element("span", "detail-label", label), element("strong", "detail-value", value));
  return row;
}

function renderBody(scene) {
  body.replaceChildren();
  const d = scene.details;
  if (scene.kind === "activity") {
    const meta = element("div", "activity-meta");
    meta.append(detailLine("Состояние", d.status), detailLine("Граница", d.boundary));
    const steps = element("ol", "activity-steps");
    d.steps.forEach((step) => {
      const item = element("li", "activity-step", step.label);
      item.dataset.state = step.state;
      steps.append(item);
    });
    body.append(meta, steps);
    return;
  }
  if (scene.kind === "continuity") {
    const moment = element("div", "continuity-item");
    moment.append(element("span", "detail-label", "Наш момент"), element("strong", "continuity-text", d.moment));
    const thread = element("div", "continuity-item is-thread");
    thread.append(element("span", "detail-label", d.state), element("strong", "continuity-text", d.thread));
    body.append(moment, thread);
    return;
  }
  if (scene.kind === "reflection") {
    body.append(
      detailLine("Статус", "Мнение Маши, не факт"),
      detailLine("Основания", d.evidence),
      detailLine("Уверенность", d.confidence),
      detailLine("Честная помощь", d.offer),
    );
    return;
  }
  if (scene.kind === "skills") {
    const skill = element("div", "skill-object");
    skill.append(element("span", "skill-mark", "✓"), element("strong", "skill-name", d.skill));
    skill.append(element("span", "skill-integrity", d.integrity));
    body.append(skill, detailLine("Разрешение", d.permission), detailLine("Автономность", d.autonomy));
    return;
  }
  if (scene.kind === "models") {
    body.append(
      detailLine("●", d.primary, "active"),
      detailLine("○", d.fast, "available"),
      detailLine("—", d.experimental, "disabled"),
    );
    return;
  }
  if (scene.kind === "runtime") {
    body.append(
      detailLine("Исполнение", d.model, "warning"),
      detailLine("Память", d.memory, "safe"),
      detailLine("Граница", d.safety),
      detailLine("Выход", d.recovery),
    );
    return;
  }
  const labels = {
    commitment: [["До", d.due], ["Сейчас", d.status], ["Контекст", d.context]],
    confirmation: [["Тип", d.type], ["Изменение", d.effect], ["Источник", d.origin]],
    proactive: [["Почему", d.why], ["Доставка", d.delivered], ["Policy", d.policy]],
    checkin: [["Основание", d.reason], ["Сдержанность", d.restraint], ["Выбор", d.promise]],
  };
  (labels[scene.kind] || []).forEach(([label, value]) => body.append(detailLine(label, value)));
}

function renderActions(view) {
  actions.replaceChildren();
  view.scene.actions.forEach((action, index) => {
    const button = element("button", index === 0 ? "surface-action is-primary" : "surface-action", action.label);
    button.type = "button";
    button.addEventListener("click", () => dispatch({ type: "ACT", actionIndex: index }));
    actions.append(button);
  });
}

function renderDots(view) {
  dots.replaceChildren();
  workshop.SCENES.forEach((scene, index) => {
    const button = element("button", "scene-dot", scene.nav);
    button.type = "button";
    button.dataset.sceneId = scene.id;
    button.setAttribute("aria-label", `${index + 1}. ${scene.nav}`);
    button.setAttribute("aria-pressed", String(index === view.index));
    if (index === view.index) button.dataset.current = "true";
    button.addEventListener("click", () => dispatch({ type: "SELECT", sceneId: scene.id }));
    dots.append(button);
  });
}

function render() {
  const view = workshop.project(state);
  const scene = view.scene;
  home.dataset.zone = scene.zone;
  home.dataset.tone = scene.kind;
  surface.dataset.scene = scene.id;
  counter.textContent = `${String(view.index + 1).padStart(2, "0")} / ${String(view.total).padStart(2, "0")}`;
  eyebrow.textContent = scene.eyebrow;
  place.textContent = scene.place;
  title.textContent = scene.title;
  summary.textContent = scene.summary;
  renderBody(scene);
  renderActions(view);
  renderDots(view);
  receipt.hidden = view.resolution === null;
  receipt.textContent = view.resolution?.message || "";
  if (view.resolution) receipt.addEventListener("click", () => dispatch({ type: "RESET" }), { once: true });
}

function dispatch(event) {
  const next = workshop.reduce(state, event);
  if (next === state) return;
  state = next;
  surface.classList.remove("is-arriving");
  void surface.offsetWidth;
  surface.classList.add("is-arriving");
  render();
}

document.getElementById("previous-scene").addEventListener("click", () => dispatch({ type: "PREVIOUS" }));
document.getElementById("next-scene").addEventListener("click", () => dispatch({ type: "NEXT" }));
document.addEventListener("keydown", (event) => {
  if (event.key === "ArrowRight") dispatch({ type: "NEXT" });
  if (event.key === "ArrowLeft") dispatch({ type: "PREVIOUS" });
  if (event.key === "Escape") dispatch({ type: "RESET" });
});

render();

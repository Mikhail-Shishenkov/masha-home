"use strict";

const ASSETS = "../../assets";

const scenarios = Object.freeze([
  {
    id: "idle",
    title: "Маша дома",
    note: "Комната, присутствие и почти полное отсутствие интерфейса.",
    variant: "presence first",
    source: `${ASSETS}/ui-04c/presence-first.png`,
    crop: [0, 0],
  },
  {
    id: "conversation",
    title: "Разговор",
    note: "Conversation мягко раскрывается справа, не вытесняя Машу.",
    variant: "presence first",
    source: `${ASSETS}/ui-04c/presence-first.png`,
    crop: [1, 0],
  },
  {
    id: "deep-conversation",
    title: "Глубокий разговор",
    note: "Разговор получает больше пространства, но Маша остаётся участником комнаты.",
    variant: "conversation first",
    source: `${ASSETS}/ui-04c/conversation-first.png`,
    crop: [1, 0],
  },
  {
    id: "activity",
    title: "Совместная работа",
    note: "Свет, глубина и положение Маши собирают комнату в рабочее пространство.",
    variant: "adaptive cinematic",
    source: `${ASSETS}/ui-04c/adaptive-cinematic.png`,
    crop: [2, 0],
  },
  {
    id: "confirmation",
    title: "Нужно твоё решение",
    note: "Один ясный объект внимания вместо системного modal dialog.",
    variant: "presence + decision",
    source: `${ASSETS}/ui-04c/presence-first.png`,
    crop: [0, 1],
  },
  {
    id: "check-in",
    title: "Я рядом",
    note: "Инициатива начинается со взгляда и света; panel может не понадобиться.",
    variant: "adaptive ambient",
    source: `${ASSETS}/ui-04c/adaptive-cinematic.png`,
    crop: [1, 1],
  },
  {
    id: "emergency-stop",
    title: "Автономность остановлена",
    note: "Автономный слой замер. Маша и разговор остаются доступными.",
    variant: "safety overlay",
    source: `${ASSETS}/ui-04c/conversation-first.png`,
    crop: [2, 1],
  },
  {
    id: "special-evening",
    title: "Особенный вечер",
    note: "Редкий красивый visual state, а не отдельный режим приложения.",
    variant: "special evening",
    source: `${ASSETS}/ui-04d/special-evening.png`,
    crop: null,
  },
]);

const home = document.querySelector("#home");
const ambient = document.querySelector("#ambient");
const image = document.querySelector("#scene-image");
const stateIndex = document.querySelector("#state-index");
const stateTitle = document.querySelector("#state-title");
const stateNote = document.querySelector("#state-note");
const dock = document.querySelector("#scenario-dock");
const viewportMode = document.querySelector("#viewport-mode");

let currentIndex = 0;
let chromePinnedHidden = false;
let chromeTimer = null;

function buildDock() {
  scenarios.forEach((scenario, index) => {
    const dot = document.createElement("button");
    dot.type = "button";
    dot.className = "scenario-dot";
    dot.dataset.index = String(index);
    dot.setAttribute("aria-label", `${index + 1}. ${scenario.title}`);
    dot.addEventListener("click", () => showScenario(index));
    dock.append(dot);
  });
}

function setSceneImage(scenario) {
  image.className = scenario.crop ? "scene-image board-image" : "scene-image full-image";
  image.style.setProperty("--crop-column", scenario.crop ? scenario.crop[0] : 0);
  image.style.setProperty("--crop-row", scenario.crop ? scenario.crop[1] : 0);
  image.alt = `${scenario.title}. ${scenario.note}`;
  image.src = scenario.source;
  ambient.style.backgroundImage = `url("${scenario.source}")`;
}

function showScenario(index) {
  currentIndex = (index + scenarios.length) % scenarios.length;
  const scenario = scenarios[currentIndex];

  home.classList.add("is-changing");
  window.setTimeout(() => {
    home.dataset.scenario = scenario.id;
    setSceneImage(scenario);
    stateIndex.textContent = `${String(currentIndex + 1).padStart(2, "0")} / ${String(scenarios.length).padStart(2, "0")} · ${scenario.variant}`;
    stateTitle.textContent = scenario.title;
    stateNote.textContent = scenario.note;
    document.querySelectorAll(".scenario-dot").forEach((dot, dotIndex) => {
      dot.classList.toggle("is-active", dotIndex === currentIndex);
      dot.setAttribute("aria-current", dotIndex === currentIndex ? "true" : "false");
    });
    window.setTimeout(() => home.classList.remove("is-changing"), 80);
  }, 180);
}

function updateViewportMode() {
  viewportMode.textContent = window.innerWidth <= 760
    ? "narrow desktop composition"
    : "wide composition";
}

function revealChromeTemporarily() {
  if (chromePinnedHidden) return;
  home.classList.remove("chrome-hidden");
  window.clearTimeout(chromeTimer);
  chromeTimer = window.setTimeout(() => home.classList.add("chrome-hidden"), 4200);
}

function toggleChrome() {
  chromePinnedHidden = !chromePinnedHidden;
  home.classList.toggle("chrome-hidden", chromePinnedHidden);
  if (!chromePinnedHidden) revealChromeTemporarily();
}

async function toggleFullscreen() {
  if (document.fullscreenElement) {
    await document.exitFullscreen();
  } else {
    await document.documentElement.requestFullscreen();
  }
}

document.querySelector("#previous").addEventListener("click", () => showScenario(currentIndex - 1));
document.querySelector("#next").addEventListener("click", () => showScenario(currentIndex + 1));

document.addEventListener("keydown", (event) => {
  if (event.key === "ArrowLeft") showScenario(currentIndex - 1);
  if (event.key === "ArrowRight" || event.key === " ") showScenario(currentIndex + 1);
  if (event.key.toLowerCase() === "h") toggleChrome();
  if (event.key.toLowerCase() === "f") toggleFullscreen();
  if (/^[1-8]$/.test(event.key)) showScenario(Number(event.key) - 1);
});

document.addEventListener("mousemove", revealChromeTemporarily);
document.addEventListener("pointerdown", revealChromeTemporarily);
window.addEventListener("resize", updateViewportMode);

buildDock();
updateViewportMode();
showScenario(0);
revealChromeTemporarily();

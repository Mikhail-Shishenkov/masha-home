"use strict";

(function registerHumanInformationPresentation(global) {
  function describe(item) {
    if (item?.availability === "forgotten") {
      return Object.freeze({ context: "Сейчас не использую в памяти", tone: "forgotten" });
    }
    if (item?.kind === "task") {
      return item.availability === "active" && item.state === "open"
        ? Object.freeze({ context: "Открытое дело", tone: "current" })
        : Object.freeze({ context: "Завершённое дело", tone: "past" });
    }
    if (item?.kind === "thread") {
      return item.availability === "active" && item.state === "open"
        ? Object.freeze({ context: "Открытая нить", tone: "current" })
        : Object.freeze({ context: "Закрытая тема", tone: "past" });
    }
    if (item?.kind === "memory") {
      return item.availability === "active"
        ? Object.freeze({ context: "То, что я помню сейчас", tone: "current" })
        : Object.freeze({ context: "Память из прошлого", tone: "past" });
    }
    return item?.availability === "active"
      ? Object.freeze({ context: "Наш момент", tone: "current" })
      : Object.freeze({ context: "Момент из прошлого", tone: "past" });
  }

  const api = Object.freeze({ describe });
  global.MashaHumanInformation = api;
  if (typeof module !== "undefined" && module.exports) module.exports = api;
})(typeof window !== "undefined" ? window : globalThis);

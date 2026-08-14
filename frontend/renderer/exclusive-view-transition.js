"use strict";

(function registerExclusiveViewTransition(global) {
  function create({
    history,
    search,
    exitMs = 110,
    setTimer = setTimeout,
    clearTimer = clearTimeout,
    requestFrame = requestAnimationFrame,
  }) {
    const views = { history, search };
    let visible = history.hidden ? "search" : "history";
    let timer = null;

    function cleanup() {
      for (const view of Object.values(views)) {
        view.classList.remove("is-history-leaving", "is-history-entering");
      }
    }

    function show(next) {
      if (!views[next]) throw new Error("unknown history view");
      if (timer !== null) clearTimer(timer);
      timer = null;
      cleanup();
      if (next === visible) {
        views[visible].hidden = false;
        views[visible === "history" ? "search" : "history"].hidden = true;
        return;
      }
      const outgoing = views[visible];
      const incoming = views[next];
      outgoing.hidden = false;
      incoming.hidden = true;
      outgoing.classList.add("is-history-leaving");
      timer = setTimer(() => {
        timer = null;
        outgoing.hidden = true;
        outgoing.classList.remove("is-history-leaving");
        incoming.classList.add("is-history-entering");
        incoming.hidden = false;
        visible = next;
        requestFrame(() => incoming.classList.remove("is-history-entering"));
      }, exitMs);
    }

    return Object.freeze({ show, visible: () => visible });
  }

  const api = Object.freeze({ create });
  global.MashaExclusiveViewTransition = api;
  if (typeof module !== "undefined" && module.exports) module.exports = api;
})(typeof window !== "undefined" ? window : globalThis);

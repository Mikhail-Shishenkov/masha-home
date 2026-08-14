"use strict";

(function registerCandidatePresentation(global) {
  function create({ delayMs = 1200, isQuiet, onReveal, setTimer = setTimeout, clearTimer = clearTimeout }) {
    let pending = null;
    let timer = null;
    let revealed = false;

    function cancelTimer() {
      if (timer !== null) clearTimer(timer);
      timer = null;
    }

    function reconsider() {
      if (!pending || revealed || timer !== null || !isQuiet()) return;
      timer = setTimer(() => {
        timer = null;
        if (!pending || !isQuiet()) return;
        revealed = true;
        onReveal(pending);
      }, delayMs);
    }

    function offer(candidate) {
      cancelTimer();
      pending = candidate || null;
      revealed = false;
      reconsider();
    }

    function defer() {
      cancelTimer();
      revealed = false;
    }

    function clear() {
      cancelTimer();
      pending = null;
      revealed = false;
    }

    return Object.freeze({ offer, defer, reconsider, clear, pending: () => pending });
  }

  const api = Object.freeze({ create });
  global.MashaCandidatePresentation = api;
  if (typeof module !== "undefined" && module.exports) module.exports = api;
})(typeof window !== "undefined" ? window : globalThis);

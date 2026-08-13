"use strict";

// One narrow recovery primitive for an interrupted cross-fade that resolves
// back to the scene which is still recorded as active.
(function registerSceneTransitionSafety(global) {
  function restoreActiveLayer(layers, activeIndex) {
    layers.forEach((layer, index) => {
      layer.onload = null;
      layer.onerror = null;
      layer.classList.remove("is-incoming", "is-revealed", "is-leaving");
      layer.classList.toggle("is-active", index === activeIndex);
    });
  }

  const api = Object.freeze({ restoreActiveLayer });
  global.MashaSceneTransitionSafety = api;
  if (typeof module !== "undefined" && module.exports) module.exports = api;
})(typeof window !== "undefined" ? window : globalThis);

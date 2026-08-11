"use strict";

// Closed, deterministic visual registry. Presentation events choose an activity;
// neither assistant text nor the model ever selects an image asset.
(function registerMashaSceneMap(global) {
  const SCENES = Object.freeze({
    idle: Object.freeze({
      id: "scene.home.idle",
      source: "assets/canonical-master.png",
      alt: "Маша дома, в своей гостиной",
    }),
    conversation: Object.freeze({
      id: "scene.home.conversation",
      source: "assets/conversation-candidate.png",
      alt: "Маша внимательно слушает в гостиной",
    }),
    thinking: Object.freeze({
      id: "scene.home.thinking",
      source: "assets/thinking-candidate.png",
      alt: "Маша задумалась в гостиной",
    }),
    activity: Object.freeze({
      id: "scene.home.activity",
      source: "assets/activity-candidate.png",
      alt: "Маша занята делом в гостиной",
    }),
    quietBeside: Object.freeze({
      id: "scene.home.quiet_beside",
      source: "assets/quiet-beside-v1.png",
      alt: "Маша тихо рядом в гостиной",
    }),
    firmDisagreement: Object.freeze({
      id: "scene.home.firm_disagreement",
      source: "assets/firm-disagreement-v1.png",
      alt: "Маша спокойно и твёрдо не согласна",
    }),
    listening: Object.freeze({
      id: "scene.home.listening",
      source: "assets/listening-v1.png",
      alt: "Маша внимательно слушает в гостиной",
    }),
  });

  function resolveScene(presentation) {
    if (!presentation || presentation.home_state === "unavailable") return SCENES.idle;
    if (presentation.overlays?.model === "model_unavailable") return SCENES.idle;
    if (
      presentation.presence?.ambient === "quiet"
      && presentation.presence?.attention === "toward_user"
    ) return SCENES.quietBeside;
    if (["skeptical", "serious"].includes(presentation.presence?.expression?.code)) {
      return SCENES.firmDisagreement;
    }
    switch (presentation.presence?.activity) {
      case "speaking":
        return SCENES.conversation;
      case "listening":
      case "waiting":
        return SCENES.listening;
      case "processing":
        return SCENES.thinking;
      case "working":
        return SCENES.activity;
      default:
        return SCENES.idle;
    }
  }

  function preload() {
    if (typeof Image !== "function") return;
    Object.values(SCENES).forEach((scene) => {
      const image = new Image();
      image.src = scene.source;
    });
  }

  const api = Object.freeze({ SCENES, resolveScene, preload });
  global.MashaSceneMap = api;
  if (typeof module !== "undefined" && module.exports) module.exports = api;
})(typeof window !== "undefined" ? window : globalThis);

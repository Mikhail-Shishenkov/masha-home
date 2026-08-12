"use strict";

// Closed, deterministic visual registry. Presentation events choose an activity;
// neither assistant text nor the model ever selects an image asset.
(function registerMashaSceneMap(global) {
  const TRANSITION_POLICY = Object.freeze({
    initial: Object.freeze({ kind: "initial", exitMs: 0, enterMs: 520, settleMs: 0, minimumHoldMs: 500 }),
    normal: Object.freeze({ kind: "normal", exitMs: 190, enterMs: 330, settleMs: 110, minimumHoldMs: 720 }),
    attention: Object.freeze({ kind: "attention", exitMs: 160, enterMs: 280, settleMs: 120, minimumHoldMs: 620 }),
    safety: Object.freeze({ kind: "safety", exitMs: 120, enterMs: 220, settleMs: 0, minimumHoldMs: 300 }),
    reduced: Object.freeze({ kind: "reduced", exitMs: 0, enterMs: 1, settleMs: 0, minimumHoldMs: 0 }),
  });
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
        return SCENES.listening;
      case "waiting":
        return presentation.presence?.attention === "toward_user" ? SCENES.listening : SCENES.idle;
      case "confirmation":
        return SCENES.idle;
      case "processing":
        return SCENES.thinking;
      case "working":
        return SCENES.activity;
      default:
        return SCENES.idle;
    }
  }

  function resolveTransition({ presentation, reducedMotion = false, initial = false } = {}) {
    if (reducedMotion) return TRANSITION_POLICY.reduced;
    if (initial) return TRANSITION_POLICY.initial;
    if (presentation?.overlays?.safety === "autonomy_stopped") {
      return TRANSITION_POLICY.safety;
    }
    if (["listening", "waiting"].includes(presentation?.presence?.activity)) {
      return TRANSITION_POLICY.attention;
    }
    return TRANSITION_POLICY.normal;
  }

  function preload() {
    if (typeof Image !== "function") return;
    Object.values(SCENES).forEach((scene) => {
      const image = new Image();
      image.src = scene.source;
    });
  }

  const api = Object.freeze({ SCENES, TRANSITION_POLICY, resolveScene, resolveTransition, preload });
  global.MashaSceneMap = api;
  if (typeof module !== "undefined" && module.exports) module.exports = api;
})(typeof window !== "undefined" ? window : globalThis);

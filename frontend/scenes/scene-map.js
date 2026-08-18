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

  function scene(period, key, source, alt) {
    return Object.freeze({ id: `scene.home.${period}.${key}`, source, alt });
  }

  const DAY_SCENES = Object.freeze({
    idle: scene("day", "idle", "assets/presence/day/idle.png", "Маша дома в спокойном дневном свете"),
    conversation: scene("day", "conversation", "assets/presence/day/conversation.png", "Маша разговаривает в светлой гостиной"),
    listening: scene("day", "listening", "assets/presence/day/listening.png", "Маша внимательно слушает в светлой гостиной"),
    thinking: scene("day", "thinking", "assets/presence/day/thinking.png", "Маша задумалась в светлой гостиной"),
    activity: scene("day", "activity", "assets/presence/day/activity.png", "Маша занята делом дома при дневном свете"),
    speakingOpen: scene("day", "speaking_open", "assets/presence/day/speaking-open.png", "Маша тепло и открыто отвечает в дневной гостиной"),
    quietBeside: scene("day", "quiet_beside", "assets/presence/day/listening.png", "Маша тихо рядом в светлой гостиной"),
    stop: scene("day", "stop", "assets/presence/day/stop.png", "Маша отдыхает с книгой в тихой дневной гостиной"),
    firmDisagreement: scene("day", "firm_disagreement", "assets/presence/day/boundary.png", "Маша спокойно и твёрдо не согласна"),
  });

  const EVENING_SCENES = Object.freeze({
    idle: scene("evening", "idle", "assets/presence/evening/idle.png", "Маша дома в тёплой вечерней гостиной"),
    conversation: scene("evening", "conversation", "assets/presence/evening/conversation.png", "Маша разговаривает в вечерней гостиной"),
    listening: scene("evening", "listening", "assets/presence/evening/listening.png", "Маша внимательно слушает в вечерней гостиной"),
    thinking: scene("evening", "thinking", "assets/presence/evening/thinking.png", "Маша задумалась в вечерней гостиной"),
    activity: scene("evening", "activity", "assets/presence/evening/activity.png", "Маша занята делом в вечернем доме"),
    speakingOpen: scene("evening", "speaking_open", "assets/presence/evening/speaking-open.png", "Маша тепло отвечает и открыто обращается к тебе"),
    listeningWithMug: scene("evening", "listening_with_mug", "assets/presence/evening/listeningWithMug.png", "Маша внимательно слушает с кружкой в руках"),
    thoughtfulAway: scene("evening", "thoughtful_away", "assets/presence/evening/thoughtful-away.png", "Маша ненадолго отвела взгляд, обдумывая ответ"),
    focusedWork: scene("evening", "focused_work", "assets/presence/evening/focused-work.png", "Маша сосредоточенно занята делом"),
    quietBeside: scene("evening", "quiet_beside", "assets/presence/evening/quiet-beside.png", "Маша тихо рядом в вечерней гостиной"),
    firmDisagreement: scene("evening", "firm_disagreement", "assets/presence/evening/boundary.png", "Маша спокойно и твёрдо не согласна"),
    stop: scene("evening", "stop", "assets/presence/evening/stop.png", "Маша отдыхает с книгой в тёплой вечерней гостиной"),
    specialEvening: scene("evening", "special", "assets/presence/evening/special-cozy-wide.png", "Особенный тихий вечер дома с Машей"),
  });

  const SCENES = Object.freeze({ day: DAY_SCENES, evening: EVENING_SCENES });

  function resolveHomePeriod(presentation) {
    // observed_at belongs to the Presentation Runtime and already carries Home's
    // local offset. The renderer never substitutes a browser clock.
    const match = /T(\d{2}):/.exec(presentation?.observed_at || "");
    if (!match) return "evening";
    const hour = Number(match[1]);
    return hour >= 7 && hour < 18 ? "day" : "evening";
  }

  function chooseVariant(presentation, primary, alternate) {
    const revision = Number(presentation?.revision);

    if (!Number.isInteger(revision) || revision < 0) {
      return primary;
    }
      return revision % 2 === 0 ? primary : alternate;
  }

  function resolveScene(presentation) {
  const period = resolveHomePeriod(presentation);
  const scenes = SCENES[period];

  if (!presentation || presentation.home_state === "unavailable") {
    return scenes.idle;
  }

  if (presentation.overlays?.model === "model_unavailable") {
    return scenes.idle;
  }
  if (presentation.overlays?.safety === "autonomy_stopped") {
  return scenes.stop;
  }

  const presence = presentation.presence || {};
  const activity = presence.activity;
  const attention = presence.attention;
  const expression = presence.expression?.code;

  if (
  activity === "idle"
  && attention === "toward_user"
) {
  return scenes.quietBeside;
}

  if (
    presence.ambient === "quiet"
    && attention === "toward_user"
  ) {
    return scenes.quietBeside;
  }

  if (["skeptical", "serious"].includes(expression)) {
    return scenes.firmDisagreement;
  }

  /*
   * Contextual alternates currently belong to the coherent evening family.
   * Daytime keeps its authored day scene set rather than unexpectedly
   * switching lighting just for visual variety.
   */
  const canUseEveningVariants = period === "evening";

  switch (activity) {
    case "speaking":
      if (period === "day" && expression === "warm_smile") {
        return chooseVariant(
          presentation,
          scenes.conversation,
          scenes.speakingOpen
        );
      }

  if (canUseEveningVariants && expression === "warm_smile") {
        return chooseVariant(
          presentation,
          scenes.conversation,
          scenes.speakingOpen
        );
      }

      return scenes.conversation;

    case "listening":
      if (canUseEveningVariants) {
        return chooseVariant(
          presentation,
          scenes.listening,
          scenes.listeningWithMug
        );
      }
      return scenes.listening;

    case "waiting":
      if (attention === "proactive") {
        return scenes.calmAttentive || scenes.listening;
      }

      if (attention === "toward_user") {
        if (canUseEveningVariants) {
          return chooseVariant(
            presentation,
            scenes.listening,
            scenes.listeningWithMug
          );
        }
        return scenes.listening;
      }

      return scenes.idle;

    case "confirmation":
      return scenes.idle;

    case "processing":
      if (canUseEveningVariants && expression === "thoughtful") {
        return chooseVariant(
          presentation,
          scenes.thinking,
          scenes.thoughtfulAway
        );
      }
      return scenes.thinking;

    case "working":
      if (canUseEveningVariants) {
        return chooseVariant(
          presentation,
          scenes.activity,
          scenes.focusedWork
        );
      }
      return scenes.activity;

    default:
      return scenes.idle;
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
    Object.values(SCENES).flatMap((family) => Object.values(family)).forEach((item) => {
      const image = new Image();
      image.src = item.source;
    });
  }

  const api = Object.freeze({ SCENES, TRANSITION_POLICY, resolveHomePeriod, resolveScene, resolveTransition, preload });
  global.MashaSceneMap = api;
  if (typeof module !== "undefined" && module.exports) module.exports = api;
})(typeof window !== "undefined" ? window : globalThis);

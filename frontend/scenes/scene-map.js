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
    idle: scene("day", "idle", "assets/presence/day/idle.png", "╨Ь╨░╤И╨░ ╨┤╨╛╨╝╨░ ╨▓ ╤Б╨┐╨╛╨║╨╛╨╣╨╜╨╛╨╝ ╨┤╨╜╨╡╨▓╨╜╨╛╨╝ ╤Б╨▓╨╡╤В╨╡"),
    conversation: scene("day", "conversation", "assets/presence/day/conversation.png", "╨Ь╨░╤И╨░ ╤А╨░╨╖╨│╨╛╨▓╨░╤А╨╕╨▓╨░╨╡╤В ╨▓ ╤Б╨▓╨╡╤В╨╗╨╛╨╣ ╨│╨╛╤Б╤В╨╕╨╜╨╛╨╣"),
    listening: scene("day", "listening", "assets/presence/day/listening.png", "╨Ь╨░╤И╨░ ╨▓╨╜╨╕╨╝╨░╤В╨╡╨╗╤М╨╜╨╛ ╤Б╨╗╤Г╤И╨░╨╡╤В ╨▓ ╤Б╨▓╨╡╤В╨╗╨╛╨╣ ╨│╨╛╤Б╤В╨╕╨╜╨╛╨╣"),
    thinking: scene("day", "thinking", "assets/presence/day/thinking.png", "╨Ь╨░╤И╨░ ╨╖╨░╨┤╤Г╨╝╨░╨╗╨░╤Б╤М ╨▓ ╤Б╨▓╨╡╤В╨╗╨╛╨╣ ╨│╨╛╤Б╤В╨╕╨╜╨╛╨╣"),
    activity: scene("day", "activity", "assets/presence/day/activity.png", "╨Ь╨░╤И╨░ ╨╖╨░╨╜╤П╤В╨░ ╨┤╨╡╨╗╨╛╨╝ ╨┤╨╛╨╝╨░ ╨┐╤А╨╕ ╨┤╨╜╨╡╨▓╨╜╨╛╨╝ ╤Б╨▓╨╡╤В╨╡"),
    speakingOpen: scene("day", "speaking_open", "assets/presence/day/speaking-open.png", "╨Ь╨░╤И╨░ ╤В╨╡╨┐╨╗╨╛ ╨╕ ╨╛╤В╨║╤А╤Л╤В╨╛ ╨╛╤В╨▓╨╡╤З╨░╨╡╤В ╨▓ ╨┤╨╜╨╡╨▓╨╜╨╛╨╣ ╨│╨╛╤Б╤В╨╕╨╜╨╛╨╣"),
    quietBeside: scene("day", "quiet_beside", "assets/presence/day/listening.png", "╨Ь╨░╤И╨░ ╤В╨╕╤Е╨╛ ╤А╤П╨┤╨╛╨╝ ╨▓ ╤Б╨▓╨╡╤В╨╗╨╛╨╣ ╨│╨╛╤Б╤В╨╕╨╜╨╛╨╣"),
    stop: scene("day", "stop", "assets/presence/day/stop.png", "╨Ь╨░╤И╨░ ╨╛╤В╨┤╤Л╤Е╨░╨╡╤В ╤Б ╨║╨╜╨╕╨│╨╛╨╣ ╨▓ ╤В╨╕╤Е╨╛╨╣ ╨┤╨╜╨╡╨▓╨╜╨╛╨╣ ╨│╨╛╤Б╤В╨╕╨╜╨╛╨╣"),
    firmDisagreement: scene("day", "firm_disagreement", "assets/presence/day/boundary.png", "╨Ь╨░╤И╨░ ╤Б╨┐╨╛╨║╨╛╨╣╨╜╨╛ ╨╕ ╤В╨▓╤С╤А╨┤╨╛ ╨╜╨╡ ╤Б╨╛╨│╨╗╨░╤Б╨╜╨░"),
  });

  const EVENING_SCENES = Object.freeze({
    idle: scene("evening", "idle", "assets/presence/evening/idle.png", "╨Ь╨░╤И╨░ ╨┤╨╛╨╝╨░ ╨▓ ╤В╤С╨┐╨╗╨╛╨╣ ╨▓╨╡╤З╨╡╤А╨╜╨╡╨╣ ╨│╨╛╤Б╤В╨╕╨╜╨╛╨╣"),
    conversation: scene("evening", "conversation", "assets/presence/evening/conversation.png", "╨Ь╨░╤И╨░ ╤А╨░╨╖╨│╨╛╨▓╨░╤А╨╕╨▓╨░╨╡╤В ╨▓ ╨▓╨╡╤З╨╡╤А╨╜╨╡╨╣ ╨│╨╛╤Б╤В╨╕╨╜╨╛╨╣"),
    listening: scene("evening", "listening", "assets/presence/evening/listening.png", "╨Ь╨░╤И╨░ ╨▓╨╜╨╕╨╝╨░╤В╨╡╨╗╤М╨╜╨╛ ╤Б╨╗╤Г╤И╨░╨╡╤В ╨▓ ╨▓╨╡╤З╨╡╤А╨╜╨╡╨╣ ╨│╨╛╤Б╤В╨╕╨╜╨╛╨╣"),
    thinking: scene("evening", "thinking", "assets/presence/evening/thinking.png", "╨Ь╨░╤И╨░ ╨╖╨░╨┤╤Г╨╝╨░╨╗╨░╤Б╤М ╨▓ ╨▓╨╡╤З╨╡╤А╨╜╨╡╨╣ ╨│╨╛╤Б╤В╨╕╨╜╨╛╨╣"),
    activity: scene("evening", "activity", "assets/presence/evening/activity.png", "╨Ь╨░╤И╨░ ╨╖╨░╨╜╤П╤В╨░ ╨┤╨╡╨╗╨╛╨╝ ╨▓ ╨▓╨╡╤З╨╡╤А╨╜╨╡╨╝ ╨┤╨╛╨╝╨╡"),
    speakingOpen: scene("evening", "speaking_open", "assets/presence/evening/speaking-open.png", "╨Ь╨░╤И╨░ ╤В╨╡╨┐╨╗╨╛ ╨╛╤В╨▓╨╡╤З╨░╨╡╤В ╨╕ ╨╛╤В╨║╤А╤Л╤В╨╛ ╨╛╨▒╤А╨░╤Й╨░╨╡╤В╤Б╤П ╨║ ╤В╨╡╨▒╨╡"),
    listeningWithMug: scene("evening", "listening_with_mug", "assets/presence/evening/listeningWithMug.png", "╨Ь╨░╤И╨░ ╨▓╨╜╨╕╨╝╨░╤В╨╡╨╗╤М╨╜╨╛ ╤Б╨╗╤Г╤И╨░╨╡╤В ╤Б ╨║╤А╤Г╨╢╨║╨╛╨╣ ╨▓ ╤А╤Г╨║╨░╤Е"),
    thoughtfulAway: scene("evening", "thoughtful_away", "assets/presence/evening/thoughtful-away.png", "╨Ь╨░╤И╨░ ╨╜╨╡╨╜╨░╨┤╨╛╨╗╨│╨╛ ╨╛╤В╨▓╨╡╨╗╨░ ╨▓╨╖╨│╨╗╤П╨┤, ╨╛╨▒╨┤╤Г╨╝╤Л╨▓╨░╤П ╨╛╤В╨▓╨╡╤В"),
    focusedWork: scene("evening", "focused_work", "assets/presence/evening/focused-work.png", "╨Ь╨░╤И╨░ ╤Б╨╛╤Б╤А╨╡╨┤╨╛╤В╨╛╤З╨╡╨╜╨╜╨╛ ╨╖╨░╨╜╤П╤В╨░ ╨┤╨╡╨╗╨╛╨╝"),
    quietBeside: scene("evening", "quiet_beside", "assets/presence/evening/quiet-beside.png", "╨Ь╨░╤И╨░ ╤В╨╕╤Е╨╛ ╤А╤П╨┤╨╛╨╝ ╨▓ ╨▓╨╡╤З╨╡╤А╨╜╨╡╨╣ ╨│╨╛╤Б╤В╨╕╨╜╨╛╨╣"),
    firmDisagreement: scene("evening", "firm_disagreement", "assets/presence/evening/boundary.png", "╨Ь╨░╤И╨░ ╤Б╨┐╨╛╨║╨╛╨╣╨╜╨╛ ╨╕ ╤В╨▓╤С╤А╨┤╨╛ ╨╜╨╡ ╤Б╨╛╨│╨╗╨░╤Б╨╜╨░"),
    stop: scene("evening", "stop", "assets/presence/evening/stop.png", "╨Ь╨░╤И╨░ ╨╛╤В╨┤╤Л╤Е╨░╨╡╤В ╤Б ╨║╨╜╨╕╨│╨╛╨╣ ╨▓ ╤В╤С╨┐╨╗╨╛╨╣ ╨▓╨╡╤З╨╡╤А╨╜╨╡╨╣ ╨│╨╛╤Б╤В╨╕╨╜╨╛╨╣"),
    specialEvening: scene("evening", "special", "assets/presence/evening/special-cozy-wide.png", "╨Ю╤Б╨╛╨▒╨╡╨╜╨╜╤Л╨╣ ╤В╨╕╤Е╨╕╨╣ ╨▓╨╡╤З╨╡╤А ╨┤╨╛╨╝╨░ ╤Б ╨Ь╨░╤И╨╡╨╣"),
    specialClose: scene(
  "evening",
  "special_close",
  "assets/presence/evening/special-cozy-close.png",
  "Маша совсем рядом в тихом вечернем доме"
),

specialMug: scene(
  "evening",
  "special_mug",
  "assets/presence/evening/cozy-with-mug.png",
  "Маша уютно устроилась рядом с кружкой"
),

specialQuiet: scene(
  "evening",
  "special_quiet",
  "assets/presence/evening/quiet-with-mug.png",
  "Маша тихо сидит рядом с тобой"
),

specialThoughtful: scene(
  "evening",
  "special_thoughtful",
  "assets/presence/evening/thoughtful-with-mug.png",
  "Маша задумалась рядом в тёплом вечернем свете"
),
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
  const specialEvening =
  period === "evening"
  && presentation.home_moment === "special_evening";
  const specialProximity =
    presentation.home_proximity || "wide";

if (specialEvening) {
  if (["skeptical", "serious"].includes(expression)) {
    return scenes.firmDisagreement;
  }

  if (specialProximity === "near") {
    if (activity === "processing") {
      return scenes.specialThoughtful;
    }
    if (activity === "idle" && presence.ambient === "quiet") {
      return scenes.specialQuiet;
    }
    return chooseVariant(
      presentation,
      scenes.specialMug,
      scenes.specialQuiet
    );
  }

  if (specialProximity === "close") {
    if (activity === "processing") {
      return scenes.specialThoughtful;
    }
    if (activity === "idle" && presence.ambient === "quiet") {
      return scenes.specialMug;
    }
    return chooseVariant(
      presentation,
      scenes.specialClose,
      scenes.specialMug
    );
  }

  if (activity === "processing") {
    return scenes.specialThoughtful;
  }

  if (activity === "idle" && presence.ambient === "quiet") {
    return scenes.specialQuiet;
  }

  return scenes.specialEvening;
}
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

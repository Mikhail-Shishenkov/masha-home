(function (root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  root.UI04E = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  "use strict";

  const ASSET_ROOT = "../../assets/ui-04e";

  const assetRegistry = Object.freeze({
    "masha.visual.identity": Object.freeze({ kind: "identity", version: "workshop-1" }),
    "room.default": Object.freeze({ kind: "room", source: `${ASSET_ROOT}/room-default.png`, tone: "default" }),
    "room.evening": Object.freeze({ kind: "room", source: `${ASSET_ROOT}/room-default.png`, tone: "evening" }),

    "masha.pose.idle": atlas("masha-pose-atlas.png", 2, 2, 0, 0),
    "masha.pose.conversation": atlas("masha-pose-atlas.png", 2, 2, 1, 0),
    "masha.pose.activity": atlas("masha-pose-atlas.png", 2, 2, 0, 1),
    "masha.pose.attention": atlas("masha-pose-atlas.png", 2, 2, 1, 1),

    "masha.expression.neutral": atlas("masha-expression-atlas.png", 5, 2, 0, 0),
    "masha.expression.warm": atlas("masha-expression-atlas.png", 5, 2, 1, 0),
    "masha.expression.happy": atlas("masha-expression-atlas.png", 5, 2, 2, 0),
    "masha.expression.amused": atlas("masha-expression-atlas.png", 5, 2, 3, 0),
    "masha.expression.thoughtful": atlas("masha-expression-atlas.png", 5, 2, 4, 0),
    "masha.expression.skeptical": atlas("masha-expression-atlas.png", 5, 2, 0, 1),
    "masha.expression.slightly_annoyed": atlas("masha-expression-atlas.png", 5, 2, 1, 1),
    "masha.expression.concerned": atlas("masha-expression-atlas.png", 5, 2, 2, 1),
    "masha.expression.focused": atlas("masha-expression-atlas.png", 5, 2, 3, 1),
    "masha.expression.tender": atlas("masha-expression-atlas.png", 5, 2, 4, 1),

    "masha.attention.none": Object.freeze({ kind: "attention", gaze: "ambient" }),
    "masha.attention.user": Object.freeze({ kind: "attention", gaze: "user" }),
    "masha.attention.surface": Object.freeze({ kind: "attention", gaze: "surface" }),

    "masha.outfit.everyday": atlas("masha-outfit-atlas.png", 2, 2, 0, 0),
    "masha.outfit.work": atlas("masha-outfit-atlas.png", 2, 2, 1, 0),
    "masha.outfit.evening": atlas("masha-outfit-atlas.png", 2, 2, 0, 1),
    "masha.outfit.special_evening": atlas("masha-outfit-atlas.png", 2, 2, 1, 1),

    "surface.conversation": Object.freeze({ kind: "surface", visualClass: "soft" }),
    "surface.activity": Object.freeze({ kind: "surface", visualClass: "working" }),
    "surface.confirmation": Object.freeze({ kind: "surface", visualClass: "decision" }),
    "surface.proactive": Object.freeze({ kind: "surface", visualClass: "whisper" }),
    "overlay.safety": Object.freeze({ kind: "overlay", visualClass: "safety" }),
  });

  const expressions = Object.freeze([
    "neutral", "warm", "happy", "amused", "thoughtful",
    "skeptical", "slightly_annoyed", "concerned", "focused", "tender",
  ]);
  const attentions = Object.freeze(["none", "user", "surface"]);
  const poses = Object.freeze(["idle", "conversation", "activity", "attention"]);
  const outfits = Object.freeze(["everyday", "work", "evening", "special_evening"]);
  const surfaceSamples = Object.freeze(["none", "conversation", "activity", "confirmation", "proactive"]);

  const scenarios = Object.freeze([
    scenario("idle", "Маша дома", "idle", "warm", "none", "everyday", "default", [], "normal"),
    scenario("conversation", "Разговор", "conversation", "warm", "user", "everyday", "default", ["conversation"], "normal"),
    scenario("deep_conversation", "Глубокий разговор", "conversation", "thoughtful", "user", "everyday", "default", ["conversation"], "normal", "deep"),
    scenario("activity", "Совместная работа", "activity", "focused", "surface", "work", "default", ["conversation", "activity"], "normal"),
    scenario("confirmation", "Нужно твоё решение", "attention", "skeptical", "surface", "everyday", "default", ["confirmation"], "normal"),
    scenario("check_in", "Я рядом", "attention", "tender", "user", "everyday", "default", ["proactive"], "normal"),
    scenario("emergency_stop", "Автономность остановлена", "idle", "concerned", "user", "everyday", "default", ["conversation"], "stopped"),
    scenario("special_evening", "Особенный вечер", "attention", "amused", "user", "special_evening", "evening", [], "normal"),
  ]);

  const motionSequences = Object.freeze([
    motion("idle_to_conversation", "Idle → Conversation", "idle", "conversation", ["attention_shift", "surface_reveal"]),
    motion("conversation_to_deep", "Conversation → Deep", "conversation", "deep_conversation", ["shared_focus", "surface_expand"]),
    motion("conversation_to_activity", "Conversation → Activity", "conversation", "activity", ["room_focus", "pose_blend", "working_surface_reveal"]),
    motion("activity_to_completed", "Activity → Completed", "activity", "idle", ["activity_complete", "ambient_return"]),
    motion("idle_to_check_in", "Idle → Check-in", "idle", "check_in", ["attention_shift", "ambient_cue", "whisper_reveal"]),
    motion("confirmation_focus", "Confirmation", "conversation", "confirmation", ["attention_to_object", "decision_reveal"]),
    motion("emergency_stop", "Emergency Stop", "activity", "emergency_stop", ["autonomous_freeze", "safety_boundary"]),
  ]);

  const modes = Object.freeze(["scenario", "expression", "attention", "pose", "outfit", "surface", "motion"]);

  function atlas(file, columns, rows, column, row) {
    return Object.freeze({
      kind: "atlas",
      source: `${ASSET_ROOT}/${file}`,
      columns,
      rows,
      column,
      row,
    });
  }

  function scenario(id, title, pose, expression, attention, outfit, room, surfaces, safety, depth) {
    return Object.freeze({
      id, title, pose, expression, attention, outfit, room,
      surfaces: Object.freeze(surfaces.slice()),
      safety,
      depth: depth || "normal",
    });
  }

  function motion(id, title, from, to, primitives) {
    return Object.freeze({ id, title, from, to, primitives: Object.freeze(primitives.slice()) });
  }

  function initialState() {
    return deepFreeze({
      mode: "scenario",
      scenarioIndex: 0,
      expressionIndex: 0,
      attentionIndex: 0,
      poseIndex: 0,
      outfitIndex: 0,
      surfaceIndex: 0,
      motionIndex: 0,
      motionStep: -1,
      chromeHidden: false,
      reducedMotion: false,
      revision: 0,
    });
  }

  function reduce(state, event) {
    const next = Object.assign({}, state);
    switch (event.type) {
      case "SELECT_SCENARIO":
        next.mode = "scenario";
        next.scenarioIndex = wrap(event.index, scenarios.length);
        next.motionStep = -1;
        break;
      case "SET_MODE":
        if (!modes.includes(event.mode)) return state;
        next.mode = event.mode;
        next.motionStep = -1;
        break;
      case "NEXT":
        incrementForMode(next, 1);
        break;
      case "PREVIOUS":
        incrementForMode(next, -1);
        break;
      case "MOTION_STEP":
        next.motionStep = event.step;
        break;
      case "TOGGLE_CHROME":
        next.chromeHidden = !state.chromeHidden;
        break;
      case "SET_REDUCED_MOTION":
        next.reducedMotion = Boolean(event.enabled);
        break;
      case "RESET":
        return initialState();
      default:
        return state;
    }
    next.revision = state.revision + 1;
    return deepFreeze(next);
  }

  function project(state) {
    let result = scenarios[state.scenarioIndex];
    if (state.mode === "expression") {
      result = Object.assign({}, scenarios[0], { expression: expressions[state.expressionIndex] });
    } else if (state.mode === "attention") {
      const attention = attentions[state.attentionIndex];
      result = Object.assign({}, scenarios[0], {
        attention,
        expression: attention === "user" ? "warm" : attention === "surface" ? "thoughtful" : "neutral",
        surfaces: attention === "surface" ? ["conversation"] : [],
      });
    } else if (state.mode === "pose") {
      result = Object.assign({}, scenarios[0], { pose: poses[state.poseIndex] });
    } else if (state.mode === "outfit") {
      const outfit = outfits[state.outfitIndex];
      result = Object.assign({}, scenarios[0], {
        outfit,
        room: outfit === "special_evening" ? "evening" : "default",
        expression: outfit === "special_evening" ? "amused" : "warm",
      });
    } else if (state.mode === "surface") {
      const surface = surfaceSamples[state.surfaceIndex];
      result = Object.assign({}, scenarios[0], {
        surfaces: surface === "none" ? [] : [surface],
        attention: surface === "none" ? "none" : surface === "proactive" ? "user" : "surface",
        expression: surface === "confirmation" ? "skeptical" : surface === "proactive" ? "tender" : "focused",
      });
    } else if (state.mode === "motion") {
      const sequence = motionSequences[state.motionIndex];
      const target = state.motionStep < 0 ? sequence.from : sequence.to;
      result = scenarios.find((item) => item.id === target) || scenarios[0];
    }
    return deepFreeze(Object.assign({}, result));
  }

  function currentLabel(state) {
    if (state.mode === "scenario") return scenarios[state.scenarioIndex].title;
    if (state.mode === "expression") return `expression · ${expressions[state.expressionIndex]}`;
    if (state.mode === "attention") return `attention · ${attentions[state.attentionIndex]}`;
    if (state.mode === "pose") return `pose · ${poses[state.poseIndex]}`;
    if (state.mode === "outfit") return `outfit · ${outfits[state.outfitIndex]}`;
    if (state.mode === "surface") return `surface · ${surfaceSamples[state.surfaceIndex]}`;
    return `motion · ${motionSequences[state.motionIndex].title}`;
  }

  function incrementForMode(state, delta) {
    const map = {
      scenario: ["scenarioIndex", scenarios.length],
      expression: ["expressionIndex", expressions.length],
      attention: ["attentionIndex", attentions.length],
      pose: ["poseIndex", poses.length],
      outfit: ["outfitIndex", outfits.length],
      surface: ["surfaceIndex", surfaceSamples.length],
      motion: ["motionIndex", motionSequences.length],
    };
    const [key, length] = map[state.mode];
    state[key] = wrap(state[key] + delta, length);
    state.motionStep = -1;
  }

  function wrap(index, length) {
    return (Number(index) % length + length) % length;
  }

  function deepFreeze(value) {
    if (!value || typeof value !== "object" || Object.isFrozen(value)) return value;
    Object.values(value).forEach(deepFreeze);
    return Object.freeze(value);
  }

  return Object.freeze({
    assetRegistry,
    expressions,
    attentions,
    poses,
    outfits,
    surfaceSamples,
    scenarios,
    motionSequences,
    modes,
    initialState,
    reduce,
    project,
    currentLabel,
  });
});

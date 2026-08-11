(function (root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  root.UI04F = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  "use strict";

  const ASSET_ROOT = "../../assets/ui-04f";
  const WORKSHOP_ROOT = "../../assets/ui-04e";

  const registry = Object.freeze({
    "masha.visual.identity": Object.freeze({ kind: "identity", version: "living-slice-1" }),
    "room.canonical": Object.freeze({ kind: "room", source: `${ASSET_ROOT}/room-canonical.png`, tone: "default" }),
    "room.canonical_evening": Object.freeze({ kind: "room", source: `${ASSET_ROOT}/room-canonical.png`, tone: "evening" }),

    "masha.pose.idle": atlas(`${ASSET_ROOT}/masha-integrated-pose-atlas.png`, 3, 2, 0, 0),
    "masha.pose.conversation": atlas(`${ASSET_ROOT}/masha-integrated-pose-atlas.png`, 3, 2, 1, 0),
    "masha.pose.thinking": atlas(`${ASSET_ROOT}/masha-integrated-pose-atlas.png`, 3, 2, 2, 0),
    "masha.pose.working": atlas(`${ASSET_ROOT}/masha-integrated-pose-atlas.png`, 3, 2, 0, 1),
    "masha.pose.attention_user": atlas(`${ASSET_ROOT}/masha-integrated-pose-atlas.png`, 3, 2, 1, 1),
    "masha.pose.attention_surface": atlas(`${ASSET_ROOT}/masha-integrated-pose-atlas.png`, 3, 2, 2, 1),

    "masha.expression.neutral": semantic("expression"),
    "masha.expression.warm": semantic("expression"),
    "masha.expression.happy": semantic("expression"),
    "masha.expression.amused": semantic("expression"),
    "masha.expression.thoughtful": semantic("expression"),
    "masha.expression.skeptical": semantic("expression"),
    "masha.expression.slightly_annoyed": semantic("expression"),
    "masha.expression.concerned": semantic("expression"),
    "masha.expression.focused": semantic("expression"),
    "masha.expression.tender": semantic("expression"),

    "masha.attention.none": semantic("attention"),
    "masha.attention.user": semantic("attention"),
    "masha.attention.surface": semantic("attention"),

    "masha.outfit.everyday": Object.freeze({ kind: "outfit", composedWith: "masha.pose.idle" }),
    "masha.outfit.work": Object.freeze({ kind: "outfit", composedWith: "masha.pose.working" }),
    "masha.outfit.evening": atlas(`${WORKSHOP_ROOT}/masha-outfit-atlas.png`, 2, 2, 0, 1),
    "masha.outfit.home_evening": atlas(`${ASSET_ROOT}/masha-evening-atlas.png`, 2, 1, 0, 0),
    "masha.outfit.special_evening": atlas(`${ASSET_ROOT}/masha-evening-atlas.png`, 2, 1, 1, 0),

    "surface.conversation": semantic("soft_surface"),
    "surface.activity": semantic("working_surface"),
    "overlay.safety": semantic("safety"),
    "overlay.privacy": semantic("privacy"),
  });

  const poses = Object.freeze(["idle", "conversation", "thinking", "working", "attention_user", "attention_surface"]);
  const expressions = Object.freeze([
    "neutral", "warm", "happy", "amused", "thoughtful",
    "skeptical", "slightly_annoyed", "concerned", "focused", "tender",
  ]);
  const attentions = Object.freeze(["none", "user", "surface"]);
  const outfits = Object.freeze(["everyday", "work", "evening", "home_evening", "special_evening"]);
  const scenarioOrder = Object.freeze([
    "idle", "conversation", "activity", "completed",
    "home_evening", "special_evening", "thinking_attention", "safety",
  ]);
  const progressSteps = Object.freeze([0, 28, 62, 88, 100]);

  const scenarios = deepFreeze({
    idle: scene("idle", "Маша дома", "idle", "warm", "none", "everyday", "default", [], "normal"),
    conversation: scene("conversation", "Разговор", "conversation", "warm", "user", "everyday", "default", [surface("conversation", "active", "primary")], "normal"),
    activity: scene("activity", "Работаем вместе", "working", "focused", "surface", "work", "work", [
      surface("conversation", "background", "supporting"),
      surface("activity", "running", "primary"),
    ], "normal"),
    completed: scene("completed", "Готово", "attention_user", "happy", "user", "work", "work", [
      surface("conversation", "background", "supporting"),
      surface("activity", "completed", "primary"),
    ], "normal"),
    home_evening: scene("home_evening", "Тихий вечер", "attention_user", "tender", "user", "home_evening", "evening", [surface("conversation", "active", "primary")], "normal"),
    special_evening: scene("special_evening", "Особенный вечер", "attention_user", "amused", "user", "special_evening", "evening", [], "normal"),
    thinking_attention: scene("thinking_attention", "Я думаю", "thinking", "thoughtful", "surface", "everyday", "focus", [surface("conversation", "active", "primary")], "normal"),
    safety: scene("safety", "Автономность остановлена", "attention_user", "concerned", "user", "everyday", "quiet", [surface("conversation", "active", "primary")], "stopped"),
  });

  function atlas(source, columns, rows, column, row) {
    return Object.freeze({ kind: "atlas", source, columns, rows, column, row });
  }

  function semantic(kind) {
    return Object.freeze({ kind });
  }

  function surface(id, lifecycle, role) {
    return Object.freeze({ id, lifecycle, role, sensitive: true });
  }

  function scene(id, title, pose, expression, attention, outfit, ambient, surfaces, safety) {
    return {
      id, title, pose, expression, attention, outfit, ambient,
      surfaces: surfaces.slice(), safety,
    };
  }

  function initialState() {
    return deepFreeze({
      scenarioId: "idle",
      activityProgressIndex: 0,
      completionPhase: "settled",
      reducedMotion: false,
      privacy: false,
      chromeHidden: false,
      revision: 0,
    });
  }

  function reduce(state, event) {
    const next = Object.assign({}, state);
    switch (event.type) {
      case "SELECT_SCENARIO":
        if (!scenarioOrder.includes(event.scenarioId)) return state;
        next.scenarioId = event.scenarioId;
        next.activityProgressIndex = event.scenarioId === "completed" ? progressSteps.length - 1 : 0;
        next.completionPhase = event.scenarioId === "completed" ? "completed" : "settled";
        break;
      case "ADVANCE":
        advanceVerticalSlice(next);
        break;
      case "SET_COMPLETION_PHASE":
        if (!Object.freeze(["completed", "collapsing", "ambient_return"]).includes(event.phase)) return state;
        next.scenarioId = "completed";
        next.activityProgressIndex = progressSteps.length - 1;
        next.completionPhase = event.phase;
        break;
      case "TOGGLE_PRIVACY":
        next.privacy = !state.privacy;
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

  function advanceVerticalSlice(state) {
    if (state.scenarioId === "idle") {
      state.scenarioId = "conversation";
    } else if (state.scenarioId === "conversation") {
      state.scenarioId = "activity";
      state.activityProgressIndex = 0;
    } else if (state.scenarioId === "activity") {
      if (state.activityProgressIndex < progressSteps.length - 1) {
        state.activityProgressIndex += 1;
      } else {
        state.scenarioId = "completed";
        state.completionPhase = "completed";
      }
    } else if (state.scenarioId === "completed") {
      if (state.completionPhase === "completed") state.completionPhase = "collapsing";
      else if (state.completionPhase === "collapsing") state.completionPhase = "ambient_return";
      else {
        state.scenarioId = "idle";
        state.activityProgressIndex = 0;
        state.completionPhase = "settled";
      }
    }
  }

  function project(state) {
    const base = scenarios[state.scenarioId];
    const result = {
      identityId: "masha.visual.identity",
      roomId: base.ambient === "evening" ? "room.canonical_evening" : "room.canonical",
      id: base.id,
      title: base.title,
      pose: base.pose,
      expression: base.expression,
      attention: base.attention,
      outfit: base.outfit,
      ambient: base.ambient,
      safety: base.safety,
      surfaces: base.surfaces.map((item) => Object.assign({}, item)),
      activityProgress: base.id === "activity" || base.id === "completed"
        ? progressSteps[state.activityProgressIndex]
        : null,
      completionPhase: state.completionPhase,
      privacy: state.privacy,
      reducedMotion: state.reducedMotion,
    };

    if (state.privacy) {
      result.surfaces = result.surfaces.map((item) => Object.assign({}, item, { masked: item.sensitive }));
    }
    if (state.completionPhase === "ambient_return") {
      result.pose = "attention_user";
      result.expression = "warm";
      result.attention = "user";
      result.ambient = "default";
      result.surfaces = result.surfaces.map((item) => Object.assign({}, item, { lifecycle: "closing" }));
    }
    return deepFreeze(result);
  }

  function characterAsset(sceneModel) {
    if (["home_evening", "special_evening", "evening"].includes(sceneModel.outfit)) {
      return registry[`masha.outfit.${sceneModel.outfit}`];
    }
    return registry[`masha.pose.${sceneModel.pose}`];
  }

  function deepFreeze(value) {
    if (!value || typeof value !== "object" || Object.isFrozen(value)) return value;
    Object.values(value).forEach(deepFreeze);
    return Object.freeze(value);
  }

  return Object.freeze({
    registry,
    poses,
    expressions,
    attentions,
    outfits,
    scenarioOrder,
    progressSteps,
    scenarios,
    initialState,
    reduce,
    project,
    characterAsset,
  });
});

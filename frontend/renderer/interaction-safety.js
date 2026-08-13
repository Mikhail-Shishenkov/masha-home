"use strict";

(function expose(root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  if (root) root.MashaInteractionSafety = api;
})(typeof window === "undefined" ? null : window, () => {
  function preserveComposer(input, documentRef, update) {
    const draft = input.value;
    const disabled = input.disabled;
    const focused = documentRef.activeElement === input;
    const selectionStart = input.selectionStart;
    const selectionEnd = input.selectionEnd;
    const result = update();
    if (input.value !== draft) input.value = draft;
    if (input.disabled !== disabled) input.disabled = disabled;
    if (focused && documentRef.activeElement !== input) {
      input.focus({ preventScroll: true });
    }
    if (
      focused
      && Number.isInteger(selectionStart)
      && Number.isInteger(selectionEnd)
      && (input.selectionStart !== selectionStart || input.selectionEnd !== selectionEnd)
      && typeof input.setSelectionRange === "function"
    ) {
      input.setSelectionRange(selectionStart, selectionEnd);
    }
    return result;
  }

  function isBackgroundProactiveProjection(payload) {
    return payload?.kind === "proactive_interactions_loaded"
      && payload?.delivery_origin === "local_runtime";
  }

  function acceptConversationPage(state, page, append) {
    const revision = Number(page?.revision ?? -1);
    if (!append) return revision >= state.revision;
    return revision === state.revision && page?.offset === state.nextOffset;
  }

  return { preserveComposer, isBackgroundProactiveProjection, acceptConversationPage };
});

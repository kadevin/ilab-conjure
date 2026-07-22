// @ts-nocheck
import { getLegacyBridge } from "./state";
import { formatTranslation, LOCALE_CHANGE_EVENT, translate } from "./i18n";
import { webAppDocumentTitle } from "./web-app-title";

const THEME_STORAGE_KEY = "codex-image-theme-preference";
const THEME_OPTIONS = new Set(["system", "light", "dark"]);
const SIDEBAR_WIDTH_STORAGE_KEY = "codex-image-sidebar-width";
const SIDEBAR_MIN_WIDTH = 280;
const SIDEBAR_MAX_WIDTH = 520;
const SIDEBAR_DEFAULT_WIDTH = 347;
const COMPACT_SHELL_MAX_WIDTH = 1180;

const bridge = getLegacyBridge();
const state = bridge.state;
const els = bridge.els;

let shellUiInitialized = false;
let shellUiEventsBound = false;
let sidebarResizeFrameId = null;
let sidebarResizePendingWidth = null;
let themeTransitionLockFrameId = null;

function legacyMethod(name, ...args) {
  const method = getLegacyBridge().methods[name];
  if (typeof method !== "function") {
    throw new Error("Legacy method " + name + " is not initialized");
  }
  return method(...args);
}

function formatTaskStatus(task) { return legacyMethod("formatTaskStatus", task); }
function closePromptPopover() { legacyMethod("closePromptPopover"); }
function closePromptSnippetPopover() { legacyMethod("closePromptSnippetPopover"); }
function closeArchiveModal() { legacyMethod("closeArchiveModal"); }
function closeGallery() { legacyMethod("closeGallery"); }
function closeImageEditor() { legacyMethod("closeImageEditor"); }
function revokeUploadPreviewUrls(sources) { legacyMethod("revokeUploadPreviewUrls", sources); }
function finishBatchMarqueeSelection() { legacyMethod("finishBatchMarqueeSelection"); }
function setPromptText(value) { legacyMethod("setPromptText", value); }
function setMode(mode) { legacyMethod("setMode", mode); }
function updateSizeFromPreset() { legacyMethod("updateSizeFromPreset"); }
function updatePromptCount() { legacyMethod("updatePromptCount"); }
function updateQuantity() { legacyMethod("updateQuantity"); }
function updateCompression() { legacyMethod("updateCompression"); }
function renderImageStrip() { legacyMethod("renderImageStrip"); }
function renderTasks() { legacyMethod("renderTasks"); }
function renderPreview() { legacyMethod("renderPreview"); }
function updateRequestPreview() { legacyMethod("updateRequestPreview"); }
function clearTaskParameterInspection() { legacyMethod("clearTaskParameterInspection"); }
function i18nText(key, fallback) {
  const value = translate(key);
  return value === key ? fallback : value;
}

function handleShellLocaleChange() {
  if (!els.statusText) return;
  const current = String(els.statusText.textContent || "").trim();
  const waitingLabels = [translate("status.waiting", "zh-CN"), translate("status.waiting", "en")];
  if (waitingLabels.includes(current)) {
    setStatus(translate("status.waiting"), "");
  }
}

function bindShellUiEvents() {
  if (shellUiEventsBound) return;
  shellUiEventsBound = true;
  els.themeSwitcher?.addEventListener("click", (event) => {
    const button = event.target.closest("[data-theme-option]");
    if (!button) return;
    applyThemePreference(button.dataset.themeOption || "system");
  });
  state.themeSystemQuery = window.matchMedia?.("(prefers-color-scheme: dark)");
  state.themeSystemQuery?.addEventListener?.("change", handleThemeSystemChange);
  document.addEventListener(LOCALE_CHANGE_EVENT, handleShellLocaleChange);
  if (els.copyJsonButton) {
    els.copyJsonButton.addEventListener("click", copyJson);
  }
  els.newTaskButton?.addEventListener("click", resetForm);
  els.sidebarResizeHandle?.addEventListener("pointerdown", startSidebarResize);
  els.sidebarResizeHandle?.addEventListener("keydown", handleSidebarResizeKeydown);
  els.sidebarResizeHandle?.addEventListener("dblclick", resetSidebarWidth);
  syncSidebarResizeHandleAria();
}

function normalizeThemePreference(value) {
  return THEME_OPTIONS.has(value) ? value : "system";
}

function resolveEffectiveTheme(preference = state.themePreference) {
  if (preference === "dark" || preference === "light") return preference;
  return window.matchMedia?.("(prefers-color-scheme: dark)")?.matches ? "dark" : "light";
}

function updateThemeSwitcher() {
  els.themeSwitcher?.querySelectorAll("[data-theme-option]").forEach((button) => {
    const active = button.dataset.themeOption === state.themePreference;
    button.classList.toggle("active", active);
    button.setAttribute("aria-pressed", active ? "true" : "false");
  });
}

function lockThemeTransitions() {
  document.documentElement.classList.add("theme-transition-lock");
  if (themeTransitionLockFrameId !== null) {
    cancelAnimationFrame(themeTransitionLockFrameId);
  }
  themeTransitionLockFrameId = requestAnimationFrame(() => {
    themeTransitionLockFrameId = requestAnimationFrame(() => {
      document.documentElement.classList.remove("theme-transition-lock");
      themeTransitionLockFrameId = null;
    });
  });
}

function applyThemePreference(preference, { persist = true } = {}) {
  state.themePreference = normalizeThemePreference(preference);
  const effectiveTheme = resolveEffectiveTheme(state.themePreference);
  if (document.documentElement.dataset.theme !== effectiveTheme) {
    lockThemeTransitions();
  }
  document.documentElement.dataset.theme = effectiveTheme;
  document.documentElement.dataset.themePreference = state.themePreference;
  if (persist) {
    try {
      localStorage.setItem(THEME_STORAGE_KEY, state.themePreference);
    } catch {
      // Browser storage may be unavailable in restricted contexts.
    }
  }
  updateThemeSwitcher();
}

function restoreThemePreference() {
  let saved = "system";
  try {
    saved = localStorage.getItem(THEME_STORAGE_KEY) || "system";
  } catch {
    saved = "system";
  }
  applyThemePreference(saved, { persist: false });
}

function handleThemeSystemChange() {
  if (state.themePreference === "system") {
    applyThemePreference("system", { persist: false });
  }
}

function restoreSidebarWidth() {
  try {
    const saved = Number.parseInt(localStorage.getItem(SIDEBAR_WIDTH_STORAGE_KEY) || "", 10);
    if (!Number.isNaN(saved)) {
      applySidebarWidth(saved, { persist: false });
    }
  } catch {
    // Browser storage may be unavailable in restricted contexts.
  }
}

function sidebarMaxWidth() {
  const viewportWidth = window.innerWidth || SIDEBAR_MAX_WIDTH;
  if (viewportWidth <= COMPACT_SHELL_MAX_WIDTH) return viewportWidth;
  return Math.min(SIDEBAR_MAX_WIDTH, Math.max(SIDEBAR_MIN_WIDTH, viewportWidth - 760));
}

function clampSidebarWidth(value) {
  const width = Number.parseInt(value, 10);
  if (Number.isNaN(width)) return SIDEBAR_MIN_WIDTH;
  return Math.min(sidebarMaxWidth(), Math.max(SIDEBAR_MIN_WIDTH, width));
}

function sidebarWidthFromCss() {
  const widthOwner = els.sidebar || document.documentElement;
  const inlineWidth = Number.parseInt(widthOwner.style.getPropertyValue("--sidebar-width") || "", 10);
  if (!Number.isNaN(inlineWidth)) return clampSidebarWidth(inlineWidth);
  const tokenWidth = Number.parseInt(getComputedStyle(widthOwner).getPropertyValue("--sidebar-width") || "", 10);
  return Number.isNaN(tokenWidth) ? null : clampSidebarWidth(tokenWidth);
}

function currentSidebarWidth() {
  return sidebarWidthFromCss() ?? SIDEBAR_DEFAULT_WIDTH;
}

function syncSidebarResizeHandleAria(width = null) {
  const handle = els.sidebarResizeHandle;
  if (!handle) return;
  const currentWidth = width !== null ? width : currentSidebarWidth();
  handle.setAttribute("aria-valuemin", String(SIDEBAR_MIN_WIDTH));
  handle.setAttribute("aria-valuemax", String(SIDEBAR_MAX_WIDTH));
  handle.setAttribute("aria-valuenow", String(currentWidth));
}

function applySidebarWidth(width, { persist = true } = {}) {
  const nextWidth = clampSidebarWidth(width);
  (els.sidebar || document.documentElement).style.setProperty("--sidebar-width", `${nextWidth}px`);
  syncSidebarResizeHandleAria(nextWidth);
  if (persist) {
    try {
      localStorage.setItem(SIDEBAR_WIDTH_STORAGE_KEY, String(nextWidth));
    } catch {
      // Browser storage may be unavailable in restricted contexts.
    }
  }
}

function resetSidebarWidth() {
  applySidebarWidth(SIDEBAR_DEFAULT_WIDTH);
}

function scheduleSidebarResizeWidth(width) {
  sidebarResizePendingWidth = clampSidebarWidth(width);
  if (sidebarResizeFrameId !== null) return;
  sidebarResizeFrameId = window.requestAnimationFrame(() => {
    sidebarResizeFrameId = null;
    const nextWidth = sidebarResizePendingWidth;
    sidebarResizePendingWidth = null;
    if (nextWidth === null) return;
    applySidebarWidth(nextWidth, { persist: false });
  });
}

function flushSidebarResizeWidth(width) {
  if (sidebarResizeFrameId !== null) {
    window.cancelAnimationFrame(sidebarResizeFrameId);
    sidebarResizeFrameId = null;
  }
  sidebarResizePendingWidth = null;
  applySidebarWidth(width, { persist: true });
}

function startSidebarResize(event) {
  if (!els.sidebar || event.button !== 0) return;
  event.preventDefault();
  const currentWidth = currentSidebarWidth();
  state.sidebarResize = {
    pointerId: event.pointerId,
    startX: event.clientX,
    startWidth: currentWidth,
    lastWidth: currentWidth,
  };
  els.sidebar.classList.add("resizing");
  if (els.sidebarResizeShield) {
    els.sidebarResizeShield.hidden = false;
  }
  els.sidebarResizeHandle?.setPointerCapture?.(event.pointerId);
  window.addEventListener("pointermove", updateSidebarResize);
  window.addEventListener("pointerup", finishSidebarResize);
  window.addEventListener("pointercancel", finishSidebarResize);
}

function updateSidebarResize(event) {
  const resize = state.sidebarResize;
  if (!resize || event.pointerId !== resize.pointerId) return;
  event.preventDefault();
  resize.lastWidth = resize.startWidth + event.clientX - resize.startX;
  scheduleSidebarResizeWidth(resize.lastWidth);
}

function finishSidebarResize(event) {
  const resize = state.sidebarResize;
  if (!resize || event.pointerId !== resize.pointerId) return;
  const nextWidth = resize.lastWidth ?? resize.startWidth;
  state.sidebarResize = null;
  els.sidebar?.classList.remove("resizing");
  if (els.sidebarResizeShield) {
    els.sidebarResizeShield.hidden = true;
  }
  els.sidebarResizeHandle?.releasePointerCapture?.(event.pointerId);
  window.removeEventListener("pointermove", updateSidebarResize);
  window.removeEventListener("pointerup", finishSidebarResize);
  window.removeEventListener("pointercancel", finishSidebarResize);
  flushSidebarResizeWidth(nextWidth);
}

function handleSidebarResizeKeydown(event) {
  if (!els.sidebar) return;
  const step = event.shiftKey ? 32 : 16;
  const currentWidth = currentSidebarWidth();
  if (event.key === "ArrowLeft") {
    event.preventDefault();
    applySidebarWidth(currentWidth - step);
  } else if (event.key === "ArrowRight") {
    event.preventDefault();
    applySidebarWidth(currentWidth + step);
  } else if (event.key === "Home") {
    event.preventDefault();
    applySidebarWidth(SIDEBAR_MIN_WIDTH);
  } else if (event.key === "End") {
    event.preventDefault();
    applySidebarWidth(SIDEBAR_MAX_WIDTH);
  }
}

function updateDocumentTitle() {
  const summary = state.queue.summary || {};
  const waitingCount = Number(summary.waiting_count ?? state.queue.waiting.length ?? 0);
  const runningCount = Number(summary.running_count ?? state.queue.running.length ?? 0);
  const total = waitingCount + runningCount;
  let status = "";
  if (runningCount > 0) {
    status = formatTranslation("document.generatingQueue", { total });
  } else if (waitingCount > 0) {
    status = formatTranslation("document.queuedWaiting", { count: waitingCount });
  } else {
    const selected = state.tasks.find((item) => String(item.task_id) === String(state.selectedTaskId));
    status = selected ? formatTaskStatus(selected) : "";
  }
  const defaultTitle = getLegacyBridge().constants.defaultDocumentTitle;
  const fullTitle = status ? `${status} · ${defaultTitle}` : defaultTitle;
  document.title = webAppDocumentTitle(status, fullTitle);
}

function setStatus(message, type) {
  if (!els.statusText) return;
  els.statusText.textContent = message;
  els.statusText.className = `status-text ${type || ""}`;
}

function resetForm() {
  const outputSettingsLocked = Boolean(legacyMethod("isOutputSettingsLocked"));
  closePromptPopover();
  closePromptSnippetPopover();
  closeArchiveModal();
  closeGallery();
  closeImageEditor();
  state.selectedTaskId = null;
  clearTaskParameterInspection();
  state.mode = "generate";
  revokeUploadPreviewUrls(state.images);
  state.images = [];
  legacyMethod("clearReferenceFiles", { silent: true });
  state.batchMode = false;
  state.batchSelectedTaskIds = [];
  state.batchSelectionAnchorTaskId = null;
  finishBatchMarqueeSelection();
  setPromptText("");
  if (!outputSettingsLocked) {
    if (els.customSizeToggle) els.customSizeToggle.checked = false;
    if (els.nInput) els.nInput.value = "1";
    if (els.resolution) els.resolution.value = "standard";
    if (els.ratio) els.ratio.value = "1:1";
    if (els.orientation) els.orientation.value = "square";
    els.size.value = "1024x1024";
    els.quality.value = "auto";
    els.outputFormat.value = "png";
    els.moderation.value = "auto";
    els.compression.value = "80";
    if (els.promptFidelity) els.promptFidelity.value = "strict";
    if (els.webSearch) els.webSearch.checked = false;
    [els.nInput, els.resolution, els.ratio, els.orientation, els.quality, els.outputFormat, els.moderation, els.promptFidelity, els.webSearch].forEach((sel) => {
      if (sel) sel.dispatchEvent(new Event("change"));
    });
    updateSizeFromPreset();
  }
  setMode("generate");
  updatePromptCount();
  updateQuantity();
  updateCompression();
  renderImageStrip();
  renderTasks();
  renderPreview();
  updateRequestPreview();
  if (outputSettingsLocked) legacyMethod("showLockedOutputSettings");
  setStatus(translate("status.waiting"), "");
}

async function copyJson() {
  if (!els.requestJson) return;
  await navigator.clipboard.writeText(els.requestJson.textContent);
  setStatus(translate("status.jsonCopied"), "ok");
}

export function initShellUiFeature() {
  if (shellUiInitialized) return;
  shellUiInitialized = true;
  Object.assign(getLegacyBridge().methods, {
    bindShellUiEvents,
    normalizeThemePreference,
    resolveEffectiveTheme,
    updateThemeSwitcher,
    applyThemePreference,
    restoreThemePreference,
    handleThemeSystemChange,
    restoreSidebarWidth,
    sidebarMaxWidth,
    clampSidebarWidth,
    applySidebarWidth,
    resetSidebarWidth,
    syncSidebarResizeHandleAria,
    startSidebarResize,
    updateSidebarResize,
    finishSidebarResize,
    handleSidebarResizeKeydown,
    updateDocumentTitle,
    setStatus,
    resetForm,
    copyJson,
  });
}

// @ts-nocheck
import { getLegacyBridge } from "./state";
import { formatTranslation, LOCALE_CHANGE_EVENT, translate } from "./i18n";

const THEME_STORAGE_KEY = "codex-image-theme-preference";
const THEME_OPTIONS = new Set(["system", "light", "dark"]);
const SIDEBAR_WIDTH_STORAGE_KEY = "codex-image-sidebar-width";
const SIDEBAR_MIN_WIDTH = 280;
const SIDEBAR_MAX_WIDTH = 520;

const bridge = getLegacyBridge();
const state = bridge.state;
const els = bridge.els;

let shellUiInitialized = false;
let shellUiEventsBound = false;
let previewPanelHeightFrameId = null;

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

function applyThemePreference(preference, { persist = true } = {}) {
  state.themePreference = normalizeThemePreference(preference);
  const effectiveTheme = resolveEffectiveTheme(state.themePreference);
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
  if (viewportWidth <= 1024) return viewportWidth;
  return Math.min(SIDEBAR_MAX_WIDTH, Math.max(SIDEBAR_MIN_WIDTH, viewportWidth - 760));
}

function clampSidebarWidth(value) {
  const width = Number.parseInt(value, 10);
  if (Number.isNaN(width)) return SIDEBAR_MIN_WIDTH;
  return Math.min(sidebarMaxWidth(), Math.max(SIDEBAR_MIN_WIDTH, width));
}

function applySidebarWidth(width, { persist = true } = {}) {
  const nextWidth = clampSidebarWidth(width);
  document.documentElement.style.setProperty("--sidebar-width", `${nextWidth}px`);
  if (persist) {
    try {
      localStorage.setItem(SIDEBAR_WIDTH_STORAGE_KEY, String(nextWidth));
    } catch {
      // Browser storage may be unavailable in restricted contexts.
    }
  }
  schedulePreviewPanelHeightSync();
}

function startSidebarResize(event) {
  if (!els.sidebar || event.button !== 0) return;
  event.preventDefault();
  const currentWidth = els.sidebar.getBoundingClientRect().width || SIDEBAR_MIN_WIDTH;
  state.sidebarResize = {
    pointerId: event.pointerId,
    startX: event.clientX,
    startWidth: currentWidth,
  };
  els.sidebar.classList.add("resizing");
  document.body.classList.add("sidebar-resizing");
  els.sidebarResizeHandle?.setPointerCapture?.(event.pointerId);
  window.addEventListener("pointermove", updateSidebarResize);
  window.addEventListener("pointerup", finishSidebarResize);
  window.addEventListener("pointercancel", finishSidebarResize);
}

function updateSidebarResize(event) {
  const resize = state.sidebarResize;
  if (!resize || event.pointerId !== resize.pointerId) return;
  applySidebarWidth(resize.startWidth + event.clientX - resize.startX, { persist: false });
}

function finishSidebarResize(event) {
  const resize = state.sidebarResize;
  if (!resize || event.pointerId !== resize.pointerId) return;
  const currentWidth = els.sidebar?.getBoundingClientRect().width || resize.startWidth;
  applySidebarWidth(currentWidth, { persist: true });
  state.sidebarResize = null;
  els.sidebar?.classList.remove("resizing");
  document.body.classList.remove("sidebar-resizing");
  els.sidebarResizeHandle?.releasePointerCapture?.(event.pointerId);
  window.removeEventListener("pointermove", updateSidebarResize);
  window.removeEventListener("pointerup", finishSidebarResize);
  window.removeEventListener("pointercancel", finishSidebarResize);
}

function handleSidebarResizeKeydown(event) {
  if (!els.sidebar) return;
  const step = event.shiftKey ? 32 : 16;
  const currentWidth = els.sidebar.getBoundingClientRect().width || SIDEBAR_MIN_WIDTH;
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

function setupPreviewPanelHeightSync() {
  if (!els.controlsCol || !els.previewCol || !els.previewPanel) return;
  window.addEventListener("resize", schedulePreviewPanelHeightSync);
  if (window.ResizeObserver) {
    const observer = new ResizeObserver(schedulePreviewPanelHeightSync);
    observer.observe(els.controlsCol);
    els.controlsCol.querySelectorAll(":scope > .panel").forEach((panel) => observer.observe(panel));
  }
  schedulePreviewPanelHeightSync();
}

function schedulePreviewPanelHeightSync() {
  if (previewPanelHeightFrameId !== null) {
    window.cancelAnimationFrame(previewPanelHeightFrameId);
  }
  previewPanelHeightFrameId = window.requestAnimationFrame(() => {
    previewPanelHeightFrameId = null;
    syncPreviewPanelHeight();
  });
}

function syncPreviewPanelHeight() {
  if (!els.controlsCol || !els.previewCol || !els.previewPanel) return;
  if (window.matchMedia("(max-width: 1024px)").matches) {
    els.previewCol.style.removeProperty("--controls-col-height");
    els.previewPanel.style.removeProperty("--controls-col-height");
    return;
  }
  const panels = [...els.controlsCol.querySelectorAll(":scope > .panel")];
  if (!panels.length) return;
  const firstPanelRect = panels[0].getBoundingClientRect();
  const lastPanelRect = panels[panels.length - 1].getBoundingClientRect();
  const height = Math.max(260, Math.ceil(lastPanelRect.bottom - firstPanelRect.top));
  els.previewCol.style.setProperty("--controls-col-height", `${height}px`);
  els.previewPanel.style.setProperty("--controls-col-height", `${height}px`);
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
  document.title = status ? `${status} · ${getLegacyBridge().constants.defaultDocumentTitle}` : getLegacyBridge().constants.defaultDocumentTitle;
}

function setStatus(message, type) {
  if (!els.statusText) return;
  els.statusText.textContent = message;
  els.statusText.className = `status-text ${type || ""}`;
}

function resetForm() {
  closePromptPopover();
  closePromptSnippetPopover();
  closeArchiveModal();
  closeGallery();
  closeImageEditor();
  state.selectedTaskId = null;
  state.mode = "generate";
  revokeUploadPreviewUrls(state.images);
  state.images = [];
  state.batchMode = false;
  state.batchSelectedTaskIds = [];
  finishBatchMarqueeSelection();
  setPromptText("");
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
  [els.nInput, els.resolution, els.ratio, els.orientation, els.quality, els.outputFormat, els.moderation, els.promptFidelity].forEach((sel) => {
    if (sel) sel.dispatchEvent(new Event("change"));
  });
  setMode("generate");
  updateSizeFromPreset();
  updatePromptCount();
  updateQuantity();
  updateCompression();
  renderImageStrip();
  renderTasks();
  renderPreview();
  updateRequestPreview();
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
    startSidebarResize,
    updateSidebarResize,
    finishSidebarResize,
    handleSidebarResizeKeydown,
    setupPreviewPanelHeightSync,
    schedulePreviewPanelHeightSync,
    syncPreviewPanelHeight,
    updateDocumentTitle,
    setStatus,
    resetForm,
    copyJson,
  });
}

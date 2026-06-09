// @ts-nocheck
import { formatTranslation, LOCALE_CHANGE_EVENT, translate } from "./i18n";
import { getLegacyBridge } from "./state";

const bridge = getLegacyBridge();
const els = bridge.els;

let overlayPopoversInitialized = false;
let overlayPopoverEventsBound = false;
let confirmPopoverEl = null;
const confirmPopoverState = {
  anchor: null,
  onConfirm: null,
};

let promptPopoverEl = null;
const promptPopoverState = {
  anchor: null,
  data: null,
  optimizedPrompt: "",
  copyTimerId: null,
};

function legacyMethod(name, ...args) {
  const method = getLegacyBridge().methods[name];
  if (typeof method !== "function") {
    throw new Error("Legacy method " + name + " is not initialized");
  }
  return method(...args);
}

function escapeHtml(value) { return legacyMethod("escapeHtml", value); }
function closeGalleryEditPopover() { legacyMethod("closeGalleryEditPopover"); }
function handlePromptDocumentClick(event) { legacyMethod("handlePromptDocumentClick", event); }
function handleGalleryDocumentClick(event) { legacyMethod("handleGalleryDocumentClick", event); }
function closeCompressionPopover() { legacyMethod("closeCompressionPopover"); }
function handleImageEditorHistoryShortcut(event) { return legacyMethod("handleImageEditorHistoryShortcut", event); }
function hideMentionSuggest() { legacyMethod("hideMentionSuggest"); }
function hideColorSuggest() { legacyMethod("hideColorSuggest"); }
function hidePromptSnippetSuggest() { legacyMethod("hidePromptSnippetSuggest"); }
function hidePromptSnippetSelectionButton() { legacyMethod("hidePromptSnippetSelectionButton"); }
function closePromptSnippetPopover() { legacyMethod("closePromptSnippetPopover"); }
function closeArchiveModal() { legacyMethod("closeArchiveModal"); }
function closeImageEditor() { legacyMethod("closeImageEditor"); }
function closeGallery() { legacyMethod("closeGallery"); }
function closeApiSettingsModal() { legacyMethod("closeApiSettingsModal"); }
function closePromptTemplateDrawer() { legacyMethod("closePromptTemplateDrawer"); }

function bindOverlayPopoverEvents() {
  if (overlayPopoverEventsBound) return;
  overlayPopoverEventsBound = true;
  document.addEventListener("click", handleDocumentClick);
  document.addEventListener("keydown", handleDocumentKeydown);
}

function ensureConfirmPopover() {
  if (confirmPopoverEl) return confirmPopoverEl;
  confirmPopoverEl = document.createElement("div");
  confirmPopoverEl.className = "confirm-popover hidden";
  confirmPopoverEl.setAttribute("role", "dialog");
  confirmPopoverEl.setAttribute("aria-label", translate("action.confirm"));
  document.body.appendChild(confirmPopoverEl);
  return confirmPopoverEl;
}

function openConfirmPopover(anchor, options = {}) {
  if (!anchor) return;
  const popover = ensureConfirmPopover();
  if (!popover.classList.contains("hidden") && confirmPopoverState.anchor === anchor) {
    closeConfirmPopover();
    return;
  }

  closePromptPopover();
  closeGalleryEditPopover();
  confirmPopoverState.anchor = anchor;
  confirmPopoverState.onConfirm = typeof options.onConfirm === "function" ? options.onConfirm : null;
  const message = options.message ? `<p class="confirm-popover-message">${escapeHtml(options.message)}</p>` : "";
  const detail = options.detail ? `<div class="confirm-popover-detail">${escapeHtml(options.detail)}</div>` : "";
  const confirmText = options.confirmText || translate("action.confirm");
  popover.innerHTML = `
    <div class="confirm-popover-title">${escapeHtml(options.title || translate("action.confirmQuestion"))}</div>
    ${message}
    ${detail}
    <div class="confirm-popover-actions">
      <button class="ghost-button text-sm" type="button" data-confirm-popover-cancel>${escapeHtml(translate("action.cancel"))}</button>
      <button class="ghost-button text-sm danger-button confirm-popover-confirm" type="button" data-confirm-popover-confirm>${escapeHtml(confirmText)}</button>
    </div>
  `;
  popover.querySelector("[data-confirm-popover-cancel]")?.addEventListener("click", closeConfirmPopover);
  popover.querySelector("[data-confirm-popover-confirm]")?.addEventListener("click", async () => {
    const onConfirm = confirmPopoverState.onConfirm;
    closeConfirmPopover();
    if (onConfirm) await onConfirm();
  });
  popover.classList.remove("hidden");
  positionConfirmPopover(anchor, popover);
  popover.querySelector("[data-confirm-popover-confirm]")?.focus({ preventScroll: true });
}

function closeConfirmPopover() {
  if (!confirmPopoverEl) return;
  confirmPopoverEl.classList.add("hidden");
  confirmPopoverState.anchor = null;
  confirmPopoverState.onConfirm = null;
}

function positionConfirmPopover(anchor, popover) {
  const anchorRect = anchor.getBoundingClientRect();
  const margin = 10;
  const width = Math.min(280, Math.max(220, window.innerWidth - margin * 2));
  popover.style.width = `${width}px`;
  popover.style.left = "0px";
  popover.style.top = "0px";
  const height = popover.offsetHeight;
  const left = clampPopoverPosition(anchorRect.right - width, margin, window.innerWidth - width - margin);
  const belowTop = anchorRect.bottom + 8;
  const top = belowTop + height <= window.innerHeight - margin
    ? belowTop
    : clampPopoverPosition(anchorRect.top - height - 8, margin, window.innerHeight - height - margin);
  popover.style.left = `${left}px`;
  popover.style.top = `${top}px`;
}

function normalizedPromptText(value) {
  return String(value || "").trim();
}

function promptLengthLabel(value) {
  return formatTranslation("promptPopover.charCount", {
    count: Array.from(normalizedPromptText(value)).length,
  });
}

function promptPopoverSection(label, text, meta, tone = "") {
  const toneClass = tone ? ` prompt-popover-section-${tone}` : "";
  return `
    <section class="prompt-popover-section${toneClass}">
      <div class="prompt-popover-section-head">
        <div class="prompt-popover-label">${escapeHtml(label)}</div>
        <span class="prompt-popover-meta">${escapeHtml(meta || promptLengthLabel(text))}</span>
      </div>
      <pre class="prompt-popover-text">${escapeHtml(text || translate("promptPopover.empty"))}</pre>
    </section>
  `;
}

function submittedPromptDetails(originalPrompt, submittedPrompt) {
  if (!normalizedPromptText(submittedPrompt)) return "";
  if (normalizedPromptText(originalPrompt) === normalizedPromptText(submittedPrompt)) return "";
  return `
    <details class="prompt-popover-submitted">
      <summary>${escapeHtml(translate("promptPopover.submitted"))}</summary>
      <pre class="prompt-popover-submitted-text">${escapeHtml(submittedPrompt)}</pre>
    </details>
  `;
}

function ensurePromptPopover() {
  if (promptPopoverEl) return promptPopoverEl;
  promptPopoverEl = document.createElement("div");
  promptPopoverEl.className = "prompt-popover hidden";
  promptPopoverEl.setAttribute("role", "dialog");
  promptPopoverEl.setAttribute("aria-label", translate("promptPopover.title"));
  document.body.appendChild(promptPopoverEl);
  return promptPopoverEl;
}

function openPromptPopover(anchor, data) {
  const popover = ensurePromptPopover();
  const originalPrompt = data.originalPrompt || data.submittedPrompt || "";
  const submittedPrompt = data.submittedPrompt || originalPrompt || "";
  const optimizedPrompt = data.optimizedPrompt || "";
  promptPopoverState.anchor = anchor;
  promptPopoverState.data = data;
  promptPopoverState.optimizedPrompt = optimizedPrompt;
  clearPromptPopoverCopyTimer();
  popover.setAttribute("aria-label", translate("promptPopover.title"));
  const optimizedLength = optimizedPrompt ? promptLengthLabel(optimizedPrompt) : translate("promptPopover.notReturned");
  popover.innerHTML = `
    <div class="prompt-popover-header">
      <div>
        <strong>${escapeHtml(translate("promptPopover.title"))}</strong>
        <span class="prompt-popover-summary">${escapeHtml(formatTranslation("promptPopover.summary", {
          original: promptLengthLabel(originalPrompt),
          optimized: optimizedLength,
        }))}</span>
      </div>
      <button class="prompt-popover-close" type="button" aria-label="${escapeHtml(translate("promptPopover.close"))}">×</button>
    </div>
    <div class="prompt-popover-body">
      <div class="prompt-popover-compare">
        ${promptPopoverSection(translate("promptPopover.original"), originalPrompt || translate("promptPopover.empty"), promptLengthLabel(originalPrompt), "original")}
        ${promptPopoverSection(translate("promptPopover.optimized"), optimizedPrompt || translate("promptPopover.noOptimized"), optimizedLength, optimizedPrompt ? "optimized" : "empty")}
      </div>
      ${submittedPromptDetails(originalPrompt, submittedPrompt)}
    </div>
    <div class="prompt-popover-actions">
      <button class="prompt-copy-button" type="button" data-copy-optimized-prompt ${optimizedPrompt ? "" : "disabled"}>${escapeHtml(translate("promptPopover.copyOptimized"))}</button>
    </div>
  `;
  popover.querySelector(".prompt-popover-close")?.addEventListener("click", closePromptPopover);
  popover.querySelector("[data-copy-optimized-prompt]")?.addEventListener("click", (event) => {
    copyOptimizedPrompt(event.currentTarget);
  });
  popover.classList.remove("hidden");
  positionPromptPopover(anchor, popover);
}

function positionPromptPopover(anchor, popover) {
  const anchorRect = anchor.getBoundingClientRect();
  const margin = 12;
  const width = Math.min(860, Math.max(360, window.innerWidth - margin * 2));
  popover.style.left = "0px";
  popover.style.top = "0px";
  popover.style.width = `${width}px`;
  const height = popover.offsetHeight;
  const left = clampPopoverPosition(
    anchorRect.left + anchorRect.width / 2 - width / 2,
    margin,
    window.innerWidth - width - margin,
  );
  const preferredTop = anchorRect.top - height - margin;
  const fallbackTop = anchorRect.bottom + margin;
  const top = preferredTop >= margin
    ? preferredTop
    : clampPopoverPosition(fallbackTop, margin, window.innerHeight - height - margin);
  popover.style.left = `${left}px`;
  popover.style.top = `${top}px`;
}

function clampPopoverPosition(value, min, max) {
  return Math.min(Math.max(value, min), Math.max(min, max));
}

function closePromptPopover() {
  if (!promptPopoverEl) return;
  promptPopoverEl.classList.add("hidden");
  promptPopoverState.anchor = null;
  promptPopoverState.data = null;
  promptPopoverState.optimizedPrompt = "";
  clearPromptPopoverCopyTimer();
}

function clearPromptPopoverCopyTimer() {
  if (!promptPopoverState.copyTimerId) return;
  window.clearTimeout(promptPopoverState.copyTimerId);
  promptPopoverState.copyTimerId = null;
}

async function copyOptimizedPrompt(button) {
  const text = promptPopoverState.optimizedPrompt;
  if (!text) return;
  await navigator.clipboard.writeText(text);
  button.textContent = translate("promptPopover.copied");
  clearPromptPopoverCopyTimer();
  promptPopoverState.copyTimerId = window.setTimeout(() => {
    button.textContent = translate("promptPopover.copyOptimized");
    promptPopoverState.copyTimerId = null;
  }, 1200);
}

function rerenderPromptPopoverForLocale() {
  if (!promptPopoverEl || promptPopoverEl.classList.contains("hidden")) return;
  if (!promptPopoverState.anchor || !promptPopoverState.data) return;
  openPromptPopover(promptPopoverState.anchor, promptPopoverState.data);
}

function handleDocumentClick(event) {
  const target = event.target;
  handlePromptDocumentClick(event);
  if (promptPopoverEl && !promptPopoverEl.classList.contains("hidden")) {
    const clickedPopover = promptPopoverEl.contains(target);
    const clickedPromptButton = target.closest?.("[data-prompt-popover-index]");
    if (!clickedPopover && !clickedPromptButton) {
      closePromptPopover();
    }
  }
  handleGalleryDocumentClick(event);
  if (confirmPopoverEl && !confirmPopoverEl.classList.contains("hidden")) {
    const clickedPopover = confirmPopoverEl.contains(target);
    const clickedAnchor = confirmPopoverState.anchor?.contains?.(target);
    if (!clickedPopover && !clickedAnchor) {
      closeConfirmPopover();
    }
  }
  if (!els.compressionPopover || els.compressionPopover.classList.contains("hidden")) return;
  if (els.compressionPopover.contains(target) || els.outputFormatField?.contains(target)) return;
  closeCompressionPopover();
}

function handleDocumentKeydown(event) {
  if (handleImageEditorHistoryShortcut(event)) return;
  if (event.key === "Escape") {
    hideMentionSuggest();
    hideColorSuggest();
    hidePromptSnippetSuggest();
    hidePromptSnippetSelectionButton();
    closeCompressionPopover();
    closePromptPopover();
    closePromptSnippetPopover();
    closeGalleryEditPopover();
    closeConfirmPopover();
    closeArchiveModal();
    closeImageEditor();
    closeGallery();
    closeApiSettingsModal();
    closePromptTemplateDrawer();
  }
}

export function initOverlayPopoversFeature() {
  if (overlayPopoversInitialized) return;
  overlayPopoversInitialized = true;
  document.addEventListener(LOCALE_CHANGE_EVENT, rerenderPromptPopoverForLocale);
  Object.assign(getLegacyBridge().methods, {
    bindOverlayPopoverEvents,
    ensureConfirmPopover,
    openConfirmPopover,
    closeConfirmPopover,
    positionConfirmPopover,
    promptPopoverSection,
    ensurePromptPopover,
    openPromptPopover,
    positionPromptPopover,
    clampPopoverPosition,
    closePromptPopover,
    clearPromptPopoverCopyTimer,
    copyOptimizedPrompt,
    handleDocumentClick,
    handleDocumentKeydown,
  });
}

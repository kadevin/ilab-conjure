import { updateExecutionSummary } from "./execution-summary";
import { getLegacyBridge } from "./state";
import { updateTransparencyControls } from "./background-controls";
import { translate } from "./i18n";

const { els } = getLegacyBridge();
let compressionPositionFrame = 0;
let extraOptionsCompact = false;

function positionCompressionPopover(): void {
  const popover = els.compressionPopover as HTMLElement | null;
  const anchor = document.getElementById("outputCompressionButton");
  if (!popover || !anchor || popover.classList.contains("hidden")) return;
  const rect = anchor.getBoundingClientRect();
  const viewport = window.visualViewport;
  let leftEdge = (viewport?.offsetLeft || 0) + 12;
  const topEdge = (viewport?.offsetTop || 0) + 12;
  let rightEdge = leftEdge + (viewport?.width || window.innerWidth) - 24;
  const bottomEdge = topEdge + (viewport?.height || window.innerHeight) - 24;
  const panel = anchor.closest<HTMLElement>(".output-panel");
  if (panel) {
    const bounds = panel.getBoundingClientRect();
    const style = getComputedStyle(panel);
    leftEdge = Math.max(leftEdge, bounds.left + parseFloat(style.paddingLeft));
    rightEdge = Math.min(rightEdge, bounds.right - parseFloat(style.paddingRight));
  }
  if (!rect.width || !rect.height || anchor.closest("[inert]") || rect.bottom <= topEdge || rect.top >= bottomEdge) {
    closeCompressionPopover();
    return;
  }
  for (let parent = anchor.parentElement; parent && parent !== document.body; parent = parent.parentElement) {
    if (!/(auto|scroll|hidden|clip)/.test(getComputedStyle(parent).overflowY)) continue;
    const bounds = parent.getBoundingClientRect();
    if (rect.bottom <= bounds.top || rect.top >= bounds.bottom) {
      closeCompressionPopover();
      return;
    }
  }
  popover.style.maxWidth = `${Math.max(0, rightEdge - leftEdge)}px`;
  popover.style.maxHeight = `${Math.max(0, bottomEdge - topEdge)}px`;
  const { width, height } = popover.getBoundingClientRect();
  const below = rect.bottom + 8;
  const top = below + height <= bottomEdge ? below : rect.top - height - 8;
  popover.style.left = `${Math.max(leftEdge, Math.min(rect.right - width, rightEdge - width))}px`;
  popover.style.top = `${Math.max(topEdge, Math.min(top, bottomEdge - height))}px`;
}

function scheduleCompressionPosition(): void {
  cancelAnimationFrame(compressionPositionFrame);
  compressionPositionFrame = requestAnimationFrame(positionCompressionPopover);
}

function legacyMethod(name: string, ...args: any[]): any {
  const method = getLegacyBridge().methods[name];
  if (typeof method !== "function") {
    throw new Error("Legacy method " + name + " is not initialized");
  }
  return method(...args);
}

function buildPreviewRequest(): any { return legacyMethod("buildPreviewRequest"); }

export function updateRangeProgress(input: any): void {
  if (!input) return;
  const min = Number(input.min || 0);
  const max = Number(input.max || 100);
  const value = Number(input.value || min);
  const progress = max > min ? ((value - min) / (max - min)) * 100 : 0;
  input.style.setProperty("--range-progress", `${Math.max(0, Math.min(100, progress))}%`);
}

export function currentQuantity(): number {
  const value = Number.parseInt(els.nInput?.value || "1", 10);
  if (Number.isNaN(value)) return 1;
  return Math.min(4, Math.max(1, value));
}

export function updateQuantity(): void {
  if (!els.nInput) return;
  els.nInput.value = String(currentQuantity());
  if (els.nValue) {
    els.nValue.textContent = els.nInput.value;
  }
  if (els.nInput.matches?.('input[type="range"]')) {
    updateRangeProgress(els.nInput);
  }
}

export function updateCompression(): void {
  const controls = document.querySelector<HTMLElement>(".controls-col");
  const image26 = getLegacyBridge().state.selectedModelId?.startsWith("gpt-image-2.6-");
  const compact = image26 || !!controls && getComputedStyle(controls).getPropertyValue("--compact-composer").trim() === "1";
  const button = document.getElementById("outputCompressionButton");
  const options = document.querySelector("#outputFormatField .output-format-options");
  let layoutFocus: HTMLElement | null = null;
  if (compact !== extraOptionsCompact && els.compressionPopover && options) {
    if (compact && document.activeElement === els.transparentBackground) layoutFocus = button;
    if (!compact && els.outputFormat.value === "png" && els.compressionPopover.contains(document.activeElement)) layoutFocus = els.transparentBackground;
    closeCompressionPopover();
    extraOptionsCompact = compact;
    // Move the existing control so values, draft persistence and handlers remain shared.
    if (compact) els.compressionPopover.prepend(els.transparentBackgroundField);
    else options.append(els.transparentBackgroundField);
  }
  els.compressionPopover?.classList.toggle("output-extra-options", extraOptionsCompact);
  button?.classList.toggle("is-extra-options", extraOptionsCompact);
  const labelKey = extraOptionsCompact ? "output.extraOptions" : "output.compression";
  const label = button?.querySelector("span");
  if (label) {
    label.dataset.i18n = labelKey;
    label.textContent = translate(labelKey);
  }
  button?.setAttribute("data-i18n-attr", `aria-label:${labelKey};title:${labelKey}`);
  button?.setAttribute("aria-label", translate(labelKey));
  button?.setAttribute("title", translate(labelKey));
  els.compressionPopover?.setAttribute("data-i18n-attr", `aria-label:${labelKey}`);
  els.compressionPopover?.setAttribute("aria-label", translate(labelKey));
  updateTransparencyControls();
  const format = els.outputFormat.value;
  const compressionEnabled = ["jpeg", "webp"].includes(format);
  const gif = image26 && format === "gif";
  document.getElementById("gifOptions")?.classList.toggle("hidden", !gif);
  if (els.frameCount) {
    els.frameCount.disabled = !gif;
    const size = els.size?.value === "custom" ? `${els.customWidth?.value}x${els.customHeight?.value}` : els.size?.value;
    const dimensions = String(size || "").match(/^(\d+)x(\d+)$/);
    const frameLimit = dimensions ? Math.floor(128 * 1024 * 1024 / (Number(dimensions[1]) * Number(dimensions[2]))) : 64;
    els.frameCount.max = String(Math.max(2, Math.min(64, frameLimit)));
  }
  if (els.frameDuration) els.frameDuration.disabled = !gif;
  const duration = document.getElementById("gifDuration");
  if (duration) {
    const seconds = Number(els.frameCount?.value) * Number(els.frameDuration?.value) / 1000;
    duration.textContent = Number.isFinite(seconds) ? `${Number(seconds.toFixed(2))} s` : "—";
  }
  const optionsAvailable = gif || compressionEnabled || (extraOptionsCompact && !els.transparentBackgroundField?.classList.contains("hidden"));
  button?.classList.toggle("hidden", !optionsAvailable);
  els.compressionField?.classList.toggle("hidden", !compressionEnabled);
  els.compression.disabled = !compressionEnabled;
  if (!optionsAvailable) {
    closeCompressionPopover();
  }
  els.compressionValue.textContent = `${els.compression.value}%`;
  updateRangeProgress(els.compression);
  if (layoutFocus && layoutFocus.getClientRects().length && !(layoutFocus as HTMLInputElement).disabled) layoutFocus.focus({ preventScroll: true });
  if (!els.compressionPopover?.classList.contains("hidden")) {
    // Format changes can disable the focused control while keeping extra options open.
    if (els.compressionPopover.contains(document.activeElement) && (document.activeElement as HTMLInputElement)?.disabled) {
      focusFirstOutputOption();
    }
    scheduleCompressionPosition();
  }
}

function focusFirstOutputOption(): void {
  const first = Array.from((els.compressionPopover as HTMLElement)?.querySelectorAll<HTMLInputElement>("input:not(:disabled)") || []).find(field => field.getClientRects().length);
  (first || els.compressionPopover)?.focus({ preventScroll: true });
}

export function openCompressionPopover(): void {
  updateCompression();
  if (!els.compressionPopover || document.getElementById("outputCompressionButton")?.classList.contains("hidden")) return;
  // The shared focus manager recognizes aria-controls portals as child popovers.
  document.body.append(els.compressionPopover);
  els.compressionPopover.classList.remove("hidden");
  els.compressionPopover.setAttribute("aria-hidden", "false");
  document.getElementById("outputCompressionButton")?.setAttribute("aria-expanded", "true");
  positionCompressionPopover();
  if (els.compressionPopover.classList.contains("hidden")) return;
  window.addEventListener("resize", scheduleCompressionPosition);
  document.addEventListener("scroll", scheduleCompressionPosition, true);
  window.visualViewport?.addEventListener("resize", scheduleCompressionPosition);
  window.visualViewport?.addEventListener("scroll", scheduleCompressionPosition);
  if (!els.compressionPopover.classList.contains("hidden")) focusFirstOutputOption();
}

export function closeCompressionPopover(): void {
  if (!els.compressionPopover) return;
  const restoreFocus = els.compressionPopover.contains(document.activeElement);
  els.compressionPopover.classList.add("hidden");
  els.compressionPopover.setAttribute("aria-hidden", "true");
  document.getElementById("outputCompressionButton")?.setAttribute("aria-expanded", "false");
  cancelAnimationFrame(compressionPositionFrame);
  window.removeEventListener("resize", scheduleCompressionPosition);
  document.removeEventListener("scroll", scheduleCompressionPosition, true);
  window.visualViewport?.removeEventListener("resize", scheduleCompressionPosition);
  window.visualViewport?.removeEventListener("scroll", scheduleCompressionPosition);
  els.outputFormatField?.append(els.compressionPopover);
  if (restoreFocus) document.getElementById("outputCompressionButton")?.focus({ preventScroll: true });
}

export function handleOutputFormatDoubleClick(event: any): void {
  const button = event.target.closest("[data-val]");
  if (!button || !["jpeg", "webp"].includes(button.dataset.val)) return;
  openCompressionPopover();
}

export function syncRadioButtons(...selects: any[]): void {
  selects.filter(Boolean).forEach((select) => {
    select.dispatchEvent(new Event("change"));
  });
}

export function updateRequestPreview(): void {
  updateExecutionSummary();
  if (!els.requestJson) return;
  els.requestJson.textContent = JSON.stringify(buildPreviewRequest(), null, 2);
}

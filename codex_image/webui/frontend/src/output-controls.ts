import { updateExecutionSummary } from "./execution-summary";
import { getLegacyBridge } from "./state";
import { updateTransparencyControls } from "./background-controls";

const { els } = getLegacyBridge();

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
  updateTransparencyControls();
  const compressionEnabled = els.outputFormat.value !== "png";
  els.compression.disabled = !compressionEnabled;
  if (!compressionEnabled) {
    closeCompressionPopover();
  }
  els.compressionValue.textContent = `${els.compression.value}%`;
  updateRangeProgress(els.compression);
}

export function openCompressionPopover(): void {
  if (!els.compressionPopover || els.outputFormat.value === "png") return;
  els.compressionPopover.classList.remove("hidden");
  els.compressionPopover.setAttribute("aria-hidden", "false");
}

export function closeCompressionPopover(): void {
  if (!els.compressionPopover) return;
  els.compressionPopover.classList.add("hidden");
  els.compressionPopover.setAttribute("aria-hidden", "true");
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

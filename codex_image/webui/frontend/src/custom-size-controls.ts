import { getLegacyBridge } from "./state";
import {
  DEFAULT_ORIENTATION,
  DEFAULT_RATIO,
  DEFAULT_RESOLUTION,
  GPT_IMAGE_2_SIZE_PRESETS,
  ORIENTATION_DEFAULT_RATIOS,
  RATIO_COUNTERPARTS,
  RATIO_ORIENTATION,
  customDimensionValue,
  customSizeValidationMessage,
  findPresetForSize,
  orientationForDimensions,
  sizeForPreset,
} from "./size-presets";
import { syncRadioButtons, updateRequestPreview } from "./output-controls";
import { formatTranslation, LOCALE_CHANGE_EVENT } from "./i18n";

const CUSTOM_SIZE_TRANSITION_MS = 220;
const CUSTOM_SIZE_HEIGHT_SNAP_TOLERANCE = 4;

const bridge = getLegacyBridge();
const state = bridge.state;
const els = bridge.els;
const customSizeTransitionTimers = new WeakMap<HTMLElement, number>();

function measuredElementHeight(element: any): number {
  if (!element) return 0;
  return Math.ceil(element.getBoundingClientRect().height);
}

export function handleSizeModeEvent(event: any): void {
  const button = event.target.closest?.("[data-custom-size-mode]");
  if (!button || !els.sizeModeGroup?.contains(button)) return;
  setCustomSizeMode(button.dataset.customSizeMode === "custom");
}

export function setCustomSizeMode(isCustom: any): void {
  if (els.customSizeToggle) els.customSizeToggle.checked = Boolean(isCustom);
  updateSizeFromPreset();
}

export function swapCustomSizeDimensions(event?: any): void {
  event?.preventDefault?.();
  if (!els.customWidth || !els.customHeight) return;
  const width = els.customWidth.value;
  els.customWidth.value = els.customHeight.value;
  els.customHeight.value = width;
  if (typeof swapCustomRatioDigits === "function") swapCustomRatioDigits();
  updateCustomSize();
  updatePixelPreview("custom");
  updateRequestPreview();
}

export function sanitizeCustomRatioInput(input: any): string {
  const value = String(input?.value ?? "");
  const digit = value.match(/[1-9]/)?.[0] || "";
  if (input && input.value !== digit) input.value = digit;
  return digit;
}

export function customRatioDigitValue(input: any): number | null {
  const digit = sanitizeCustomRatioInput(input);
  return digit ? Number(digit) : null;
}

export function customAspectRatioFromManualInputs(): number | null {
  const widthRatio = customRatioDigitValue(els.customRatioWidth);
  const heightRatio = customRatioDigitValue(els.customRatioHeight);
  if (!widthRatio || !heightRatio) return null;
  return widthRatio / heightRatio;
}

export function normalizeAspectDimension(value: number): string {
  const steppedValue = Math.round(value / 16) * 16;
  const boundedValue = Math.min(3840, Math.max(16, steppedValue));
  return String(boundedValue);
}

export function updateCustomRatioFieldState(): void {
  const locked = Boolean(state.customAspectRatioLocked);
  els.customRatioField?.classList.toggle("active", locked);
}

export function setCustomAspectRatioFromManualInputs(): void {
  const ratio = customAspectRatioFromManualInputs();
  state.customAspectRatioLocked = Boolean(ratio);
  state.customAspectRatioValue = ratio;
  state.customAspectRatioSource = "manual";
  updateCustomRatioFieldState();
}

export function applyCustomAspectRatioFromWidth(): void {
  if (!state.customAspectRatioLocked || !state.customAspectRatioValue) return;
  if (!els.customWidth || !els.customHeight) return;
  const width = customDimensionValue(els.customWidth);
  if (!width) return;
  els.customHeight.value = normalizeAspectDimension(width / state.customAspectRatioValue);
}

export function handleCustomRatioInput(input: any): void {
  sanitizeCustomRatioInput(input);
  setCustomAspectRatioFromManualInputs();
  applyCustomAspectRatioFromWidth();
}

export function singleDigitAspectRatioForDimensions(width: any, height: any) {
  const numericWidth = Number(width);
  const numericHeight = Number(height);
  if (!Number.isFinite(numericWidth) || !Number.isFinite(numericHeight) || numericWidth <= 0 || numericHeight <= 0) return null;

  function gcd(left: number, right: number): number {
    let a = Math.round(Math.abs(left));
    let b = Math.round(Math.abs(right));
    while (b) {
      const remainder = a % b;
      a = b;
      b = remainder;
    }
    return a || 1;
  }

  const divisor = gcd(numericWidth, numericHeight);
  const reducedWidth = Math.round(numericWidth / divisor);
  const reducedHeight = Math.round(numericHeight / divisor);
  if (reducedWidth >= 1 && reducedWidth <= 9 && reducedHeight >= 1 && reducedHeight <= 9) {
    return { width: reducedWidth, height: reducedHeight };
  }

  const targetRatio = numericWidth / numericHeight;
  let best = { width: 1, height: 1, error: Number.POSITIVE_INFINITY };
  for (let widthRatio = 1; widthRatio <= 9; widthRatio += 1) {
    for (let heightRatio = 1; heightRatio <= 9; heightRatio += 1) {
      const candidateRatio = widthRatio / heightRatio;
      const error = Math.abs(Math.log(candidateRatio / targetRatio));
      if (error < best.error) {
        best = { width: widthRatio, height: heightRatio, error };
      }
    }
  }
  return { width: best.width, height: best.height };
}

export function firstReferenceImageSource(): any {
  return (Array.isArray(state.images) ? state.images : []).find((source: any) => (
    source && !source.missing && Boolean(sourceUrlForAspectRatio(source))
  ));
}

export function updateCustomRatioReferenceButtonState(): void {
  if (!els.customRatioFromImageButton) return;
  const enabled = Boolean(firstReferenceImageSource());
  els.customRatioFromImageButton.disabled = !enabled;
  els.customRatioFromImageButton.setAttribute("aria-disabled", enabled ? "false" : "true");
}

export function sourceUrlForAspectRatio(source: any): string {
  if (!source || source.missing) return "";
  if (source.kind === "upload") return source.previewUrl || "";
  return source.image_url || source.previewUrl || "";
}

export function loadImageDimensions(url: any) {
  return new Promise((resolve, reject) => {
    const image = new Image();
    image.onload = () => {
      const width = image.naturalWidth || image.width;
      const height = image.naturalHeight || image.height;
      if (width > 0 && height > 0) {
        resolve({ width, height });
      } else {
        reject(new Error(formatTranslation("output.imageSizeUnavailable")));
      }
    };
    image.onerror = () => reject(new Error(formatTranslation("output.imageLoadFailed")));
    image.src = String(url || "");
  });
}

export function applyCustomAspectRatioDigits(widthRatio: any, heightRatio: any): void {
  if (!els.customRatioWidth || !els.customRatioHeight) return;
  els.customRatioWidth.value = String(widthRatio || "");
  els.customRatioHeight.value = String(heightRatio || "");
  setCustomAspectRatioFromManualInputs();
  applyCustomAspectRatioFromWidth();
  updateCustomSize();
  updatePixelPreview("custom");
  updateRequestPreview();
}

export async function applyFirstReferenceImageAspectRatio(event?: any): Promise<void> {
  event?.preventDefault?.();
  const source = firstReferenceImageSource();
  updateCustomRatioReferenceButtonState();
  if (!source) return;
  const url = sourceUrlForAspectRatio(source);
  if (!url) return;
  return loadImageDimensions(url).catch(() => null).then((dimensions: any) => {
    if (!dimensions) return;
    const ratio = singleDigitAspectRatioForDimensions(dimensions.width, dimensions.height);
    if (!ratio) return;
    applyCustomAspectRatioDigits(ratio.width, ratio.height);
  });
}

export function handleCustomDimensionInput(input: any): void {
  if (!state.customAspectRatioLocked || !state.customAspectRatioValue) return;
  if (!els.customWidth || !els.customHeight) return;
  const value = customDimensionValue(input);
  if (!value) return;
  if (input === els.customWidth) {
    els.customHeight.value = normalizeAspectDimension(value / state.customAspectRatioValue);
    return;
  }
  if (input === els.customHeight) {
    els.customWidth.value = normalizeAspectDimension(value * state.customAspectRatioValue);
  }
}

function swapCustomRatioDigits(): void {
  if (!els.customRatioWidth || !els.customRatioHeight) return;
  const widthRatio = els.customRatioWidth.value;
  els.customRatioWidth.value = els.customRatioHeight.value;
  els.customRatioHeight.value = widthRatio;
  setCustomAspectRatioFromManualInputs();
}

export function updateSizeFromPreset(event: any = null): void {
  const changedControl = sizeControlName(event?.target);
  syncRatioAndOrientation(changedControl);

  if (els.customSizeToggle?.checked) {
    if (els.size?.value !== "custom") {
      populateCustomSizeFromCurrentPreset();
    }
    els.size.value = "custom";
    if (typeof setCustomAspectRatioFromManualInputs === "function") setCustomAspectRatioFromManualInputs();
    if (typeof applyCustomAspectRatioFromWidth === "function") applyCustomAspectRatioFromWidth();
    updateCustomSize();
    updatePixelPreview("custom");
    updateRequestPreview();
    return;
  }

  const size = sizeForPreset(els.resolution?.value, els.ratio?.value);
  els.size.value = size;
  updatePixelPreview(size);
  updateCustomSize();
  updateRequestPreview();
}

export function populateCustomSizeFromCurrentPreset(): void {
  if (!els.customWidth || !els.customHeight) return;
  const [width, height] = sizeForPreset(els.resolution?.value, els.ratio?.value).split("x");
  if (!width || !height) return;
  els.customWidth.value = width;
  els.customHeight.value = height;
}

export function sizeControlName(target: any): string | null {
  if (target === els.resolution) return "resolution";
  if (target === els.ratio) return "ratio";
  if (target === els.orientation) return "orientation";
  return null;
}

export function syncRatioAndOrientation(changedControl: any): void {
  if (!els.resolution || !els.ratio || !els.orientation) return;

  if (!GPT_IMAGE_2_SIZE_PRESETS[els.resolution.value]) {
    setSizeControlValue(els.resolution, DEFAULT_RESOLUTION);
  }
  if (!RATIO_ORIENTATION[els.ratio.value]) {
    setSizeControlValue(els.ratio, DEFAULT_RATIO);
  }
  if (!ORIENTATION_DEFAULT_RATIOS[els.orientation.value]) {
    setSizeControlValue(els.orientation, RATIO_ORIENTATION[els.ratio.value] || DEFAULT_ORIENTATION);
  }

  if (changedControl === "orientation") {
    syncRatioFromOrientation();
    return;
  }
  syncOrientationFromRatio();
}

export function syncOrientationFromRatio(): void {
  const nextOrientation = RATIO_ORIENTATION[els.ratio.value] || DEFAULT_ORIENTATION;
  setSizeControlValue(els.orientation, nextOrientation);
}

export function syncRatioFromOrientation(): void {
  const orientation = els.orientation.value;
  if (orientation === "square") {
    setSizeControlValue(els.ratio, DEFAULT_RATIO);
    return;
  }
  if (RATIO_ORIENTATION[els.ratio.value] === orientation) return;

  const counterpart = RATIO_COUNTERPARTS[els.ratio.value];
  if (counterpart && RATIO_ORIENTATION[counterpart] === orientation) {
    setSizeControlValue(els.ratio, counterpart);
    return;
  }
  setSizeControlValue(els.ratio, ORIENTATION_DEFAULT_RATIOS[orientation] || DEFAULT_RATIO);
}

export function setSizeControlValue(select: any, value: any): boolean {
  if (!select || select.value === value) return false;
  select.value = value;
  select.dispatchEvent(new Event("change", { bubbles: true }));
  return true;
}

export function updatePixelPreview(size: any): void {
  if (!els.pixelPreview) return;
  if (size === "auto") {
    els.pixelPreview.textContent = formatTranslation("output.pixelPreviewAuto");
    return;
  }
  if (size === "custom") {
    const message = customSizeValidationMessage();
    if (message) {
      els.pixelPreview.textContent = formatTranslation("output.pixelPreviewValue", { value: message });
      return;
    }
    els.pixelPreview.textContent = formatTranslation("output.pixelPreviewValue", {
      value: `${customDimensionValue(els.customWidth)} x ${customDimensionValue(els.customHeight)} px`,
    });
    return;
  }
  const [width, height] = String(size).split("x");
  els.pixelPreview.textContent = formatTranslation("output.pixelPreviewValue", { value: `${width} x ${height} px` });
}

document.addEventListener(LOCALE_CHANGE_EVENT, () => updatePixelPreview(els.size?.value || ""));

export function syncSizeControlsFromSize(size: any): void {
  if (!size || size === "auto") {
    if (els.customSizeToggle) els.customSizeToggle.checked = false;
    if (els.resolution) els.resolution.value = DEFAULT_RESOLUTION;
    if (els.ratio) els.ratio.value = DEFAULT_RATIO;
    if (els.orientation) els.orientation.value = DEFAULT_ORIENTATION;
    updateSizeFromPreset();
    syncRadioButtons(els.resolution, els.ratio, els.orientation);
    return;
  }

  const presetMatch = findPresetForSize(size);
  if (presetMatch) {
    if (els.customSizeToggle) els.customSizeToggle.checked = false;
    els.resolution.value = presetMatch.resolution;
    els.ratio.value = presetMatch.ratio;
    els.orientation.value = presetMatch.orientation;
    updateSizeFromPreset();
    syncRadioButtons(els.resolution, els.ratio, els.orientation);
    return;
  }

  const [width, height] = String(size).split("x");
  if (width && height) {
    if (els.customSizeToggle) els.customSizeToggle.checked = true;
    els.size.value = "custom";
    els.customWidth.value = width;
    els.customHeight.value = height;
    updatePixelPreview("custom");
    updateCustomSize();
    updateRequestPreview();
  }
}

export { orientationForDimensions };

function setCustomSizeModeLayout(isCustom: any): void {
  els.customSize?.classList.toggle("hidden", !isCustom);
  els.customSize?.classList.toggle("custom-size-collapsed", !isCustom);
  els.customSize?.setAttribute("aria-hidden", isCustom ? "false" : "true");
  els.settingsGrid?.classList.toggle("custom-size-mode", isCustom);
}

function measureCustomSizeModeHeight(isCustom: any): number {
  const grid = els.settingsGrid;
  const customSize = els.customSize;
  if (!grid) return 0;

  const originalHeight = grid.style.height;
  const originalGridTransition = grid.style.transition;
  const originalCustomTransition = customSize?.style.transition || "";
  const originalCustomMode = grid.classList.contains("custom-size-mode");
  const originalCustomHidden = customSize?.classList.contains("hidden") || false;
  const originalCustomCollapsed = customSize?.classList.contains("custom-size-collapsed") || false;
  const originalCustomAriaHidden = customSize?.getAttribute("aria-hidden");

  grid.style.transition = "none";
  grid.style.height = "";
  if (customSize) customSize.style.transition = "none";
  setCustomSizeModeLayout(isCustom);
  const height = measuredElementHeight(grid);

  grid.classList.toggle("custom-size-mode", originalCustomMode);
  if (customSize) {
    customSize.classList.toggle("hidden", originalCustomHidden);
    customSize.classList.toggle("custom-size-collapsed", originalCustomCollapsed);
    if (originalCustomAriaHidden === null) {
      customSize.removeAttribute("aria-hidden");
    } else {
      customSize.setAttribute("aria-hidden", originalCustomAriaHidden);
    }
    customSize.style.transition = originalCustomTransition;
  }
  grid.style.height = originalHeight;
  grid.style.transition = originalGridTransition;
  return height;
}

function transitionCustomSizeMode(isCustom: any): void {
  const grid = els.settingsGrid;
  const customSize = els.customSize;
  if (!grid || !customSize) {
    setCustomSizeModeLayout(isCustom);
    state.customSizeMode = isCustom;
    return;
  }

  if (state.customSizeMode === null) {
    state.customSizeMode = isCustom;
    grid.style.height = "";
    grid.classList.remove("is-size-transitioning");
    setCustomSizeModeLayout(isCustom);
    return;
  }

  const pendingTimerId = customSizeTransitionTimers.get(grid);
  if (state.customSizeMode === isCustom && !pendingTimerId) {
    grid.style.height = "";
    grid.classList.remove("is-size-transitioning");
    setCustomSizeModeLayout(isCustom);
    return;
  }

  state.customSizeMode = isCustom;
  state.customSizeTransitionSeq += 1;
  const transitionSeq = state.customSizeTransitionSeq;
  if (pendingTimerId) {
    window.clearTimeout(pendingTimerId);
    customSizeTransitionTimers.delete(grid);
  }

  const reduceMotion = window.matchMedia?.("(prefers-reduced-motion: reduce)")?.matches;
  if (reduceMotion) {
    grid.style.height = "";
    grid.classList.remove("is-size-transitioning");
    setCustomSizeModeLayout(isCustom);
    return;
  }

  const fromHeight = measuredElementHeight(grid);
  const targetHeight = measureCustomSizeModeHeight(isCustom);
  if (Math.abs(targetHeight - fromHeight) <= CUSTOM_SIZE_HEIGHT_SNAP_TOLERANCE) {
    grid.style.height = "";
    grid.classList.remove("is-size-transitioning");
    setCustomSizeModeLayout(isCustom);
    return;
  }

  grid.style.height = `${fromHeight}px`;
  grid.classList.add("is-size-transitioning");

  if (isCustom) {
    customSize.classList.remove("hidden");
    customSize.classList.add("custom-size-collapsed");
    customSize.setAttribute("aria-hidden", "false");
    grid.classList.add("custom-size-mode");
    void grid.offsetHeight;
    window.requestAnimationFrame(() => {
      if (transitionSeq !== state.customSizeTransitionSeq) return;
      customSize.classList.remove("custom-size-collapsed");
      grid.style.height = `${targetHeight}px`;
    });
  } else {
    customSize.classList.remove("hidden");
    customSize.classList.remove("custom-size-collapsed");
    customSize.setAttribute("aria-hidden", "false");
    grid.classList.add("custom-size-mode");

    void grid.offsetHeight;
    window.requestAnimationFrame(() => {
      if (transitionSeq !== state.customSizeTransitionSeq) return;
      customSize.classList.add("custom-size-collapsed");
      grid.classList.remove("custom-size-mode");
      grid.style.height = `${targetHeight}px`;
    });
  }

  const timerId = window.setTimeout(() => {
    if (transitionSeq !== state.customSizeTransitionSeq) return;
    setCustomSizeModeLayout(isCustom);
    grid.style.height = "";
    grid.classList.remove("is-size-transitioning");
    customSizeTransitionTimers.delete(grid);
  }, CUSTOM_SIZE_TRANSITION_MS);
  customSizeTransitionTimers.set(grid, timerId);
}

export function updateCustomSize(): void {
  const isCustom = els.size?.value === "custom";
  transitionCustomSizeMode(isCustom);
  if (els.customSizeToggle) els.customSizeToggle.checked = isCustom;
  els.sizeModeGroup?.querySelectorAll("[data-custom-size-mode]").forEach((button: any) => {
    const active = button.dataset.customSizeMode === (isCustom ? "custom" : "preset");
    button.classList.toggle("active", active);
    button.setAttribute("aria-pressed", active ? "true" : "false");
  });
  const message = isCustom ? customSizeValidationMessage() : "";
  els.customSize?.classList.toggle("has-error", Boolean(message));
  if (els.customSizeHint) {
    els.customSizeHint.textContent = message || formatTranslation("output.customSizeHint");
  }
  updateCustomRatioFieldState();
}

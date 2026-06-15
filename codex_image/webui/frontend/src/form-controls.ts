import { getLegacyBridge } from "./state";
import {
  closeMainModelCombobox,
  currentMainModel,
  handleMainModelKeydown,
  mainModelOptionsForQuery,
  openMainModelCombobox,
  persistMainModel,
  renderMainModelOptions,
  restoreMainModel,
  selectMainModelOption,
} from "./main-model-combobox";
import {
  closeCompressionPopover,
  currentQuantity,
  handleOutputFormatDoubleClick,
  openCompressionPopover,
  syncRadioButtons,
  updateCompression,
  updateQuantity,
  updateRequestPreview,
} from "./output-controls";
import {
  customSizeValidationMessage,
  currentImageToolModel,
  currentSize,
  currentTaskParams,
  currentWebSearchEnabled,
  webSearchSupportedForCurrentBackend,
} from "./size-presets";
import {
  applyFirstReferenceImageAspectRatio,
  handleCustomDimensionInput,
  handleCustomRatioInput,
  handleSizeModeEvent,
  swapCustomSizeDimensions,
  syncSizeControlsFromSize,
  updateCustomSize,
  updatePixelPreview,
  updateSizeFromPreset,
  updateCustomRatioFieldState,
  updateCustomRatioReferenceButtonState,
} from "./custom-size-controls";
import { LOCALE_CHANGE_EVENT, translate } from "./i18n";

const bridge = getLegacyBridge();
const state = bridge.state;
const els = bridge.els;

let formControlsInitialized = false;
let formControlEventsBound = false;

function syncRunButtonLabel(): void {
  if (!els.runButton || state.runTimerId) return;
  const mode = state.mode === "edit" ? "edit" : "generate";
  els.runButton.textContent = translate(mode === "edit" ? "prompt.runEdit" : "prompt.run");
  els.runButton.title = translate(mode === "edit" ? "prompt.runEditTitle" : "prompt.runTitle");
}

export function bindFormControlEvents(): void {
  if (formControlEventsBound) return;
  formControlEventsBound = true;

  document.querySelectorAll("[data-mode]").forEach((button: any) => {
    button.addEventListener("click", () => setMode(button.dataset.mode));
  });

  [
    els.mainModel,
    els.webSearch,
    els.model,
    els.size,
    els.customWidth,
    els.customHeight,
    els.quality,
    els.outputFormat,
    els.moderation,
    els.compression,
    els.nInput,
    els.promptFidelity,
  ].filter(Boolean).forEach((element: any) => element.addEventListener("input", () => {
    persistMainModel();
    updateQuantity();
    updateCompression();
    if (element === els.customWidth || element === els.customHeight) handleCustomDimensionInput(element);
    updateCustomSize();
    if (element === els.customWidth || element === els.customHeight) updatePixelPreview("custom");
    updateRequestPreview();
  }));

  els.mainModel?.addEventListener("focus", () => openMainModelCombobox({ showAll: true }));
  els.mainModel?.addEventListener("click", () => {
    if (!state.mainModelComboboxOpen) openMainModelCombobox({ showAll: true });
  });
  els.mainModel?.addEventListener("input", () => {
    state.mainModelShowAllOptions = false;
    openMainModelCombobox();
    renderMainModelOptions();
  });
  els.mainModel?.addEventListener("keydown", handleMainModelKeydown);
  els.mainModelToggle?.addEventListener("click", (event: any) => {
    event.preventDefault();
    if (state.mainModelComboboxOpen) {
      closeMainModelCombobox();
    } else {
      openMainModelCombobox({ showAll: true });
      els.mainModel?.focus();
    }
  });
  document.addEventListener("click", (event: any) => {
    if (!els.mainModelCombobox || els.mainModelCombobox.contains(event.target)) return;
    closeMainModelCombobox();
  });

  [els.resolution, els.ratio, els.orientation].filter(Boolean).forEach((element: any) => {
    element.addEventListener("input", updateSizeFromPreset);
    element.addEventListener("change", updateSizeFromPreset);
  });
  [els.customRatioWidth, els.customRatioHeight].filter(Boolean).forEach((element: any) => {
    element.addEventListener("input", () => {
      handleCustomRatioInput(element);
      updateCustomSize();
      updatePixelPreview("custom");
      updateRequestPreview();
    });
  });
  els.sizeModeGroup?.addEventListener("click", handleSizeModeEvent);
  els.swapCustomSizeButton?.addEventListener("click", swapCustomSizeDimensions);
  els.customRatioFromImageButton?.addEventListener("click", (event: any) => {
    void applyFirstReferenceImageAspectRatio(event);
  });
  if (els.customSizeToggle) {
    els.customSizeToggle.addEventListener("change", updateSizeFromPreset);
  }
  els.outputFormatGroup?.addEventListener("dblclick", handleOutputFormatDoubleClick);
}

export function setMode(mode: any): void {
  state.mode = mode;
  document.querySelectorAll("[data-mode]").forEach((button: any) => {
    button.classList.toggle("active", button.dataset.mode === mode);
  });
  if (!state.runTimerId) {
    syncRunButtonLabel();
  }
  syncRadioButtons(els.quality, els.outputFormat, els.moderation);
  updateRequestPreview();
}

export function initFormControlsFeature(): void {
  if (formControlsInitialized) return;
  formControlsInitialized = true;
  document.addEventListener(LOCALE_CHANGE_EVENT, syncRunButtonLabel);
  Object.assign(getLegacyBridge().methods, {
    bindFormControlEvents,
    setMode,
    syncRunButtonLabel,
    updateQuantity,
    updateCompression,
    openCompressionPopover,
    closeCompressionPopover,
    currentSize,
    currentTaskParams,
    currentMainModel,
    currentQuantity,
    currentImageToolModel,
    currentWebSearchEnabled,
    webSearchSupportedForCurrentBackend,
    restoreMainModel,
    persistMainModel,
    syncSizeControlsFromSize,
    updateSizeFromPreset,
    updateCustomSize,
    updateCustomRatioFieldState,
    updateCustomRatioReferenceButtonState,
    updatePixelPreview,
    customSizeValidationMessage,
    syncRadioButtons,
    updateRequestPreview,
    mainModelOptionsForQuery,
    openMainModelCombobox,
    closeMainModelCombobox,
    renderMainModelOptions,
    selectMainModelOption,
    handleMainModelKeydown,
    handleSizeModeEvent,
    handleCustomDimensionInput,
    handleCustomRatioInput,
    applyFirstReferenceImageAspectRatio,
    swapCustomSizeDimensions,
    handleOutputFormatDoubleClick,
  });
}

import { isGptImageModel } from "./gpt-image-models";
import { translate } from "./i18n";
import { getLegacyBridge } from "./state";

let transparentPreference = false;

export function setBackgroundControl(value: unknown): void {
  const { els } = getLegacyBridge();
  const background = value === "transparent" || value === "opaque" ? value : "auto";
  transparentPreference = background === "transparent";
  if (els.background) els.background.value = background;
  if (els.transparentBackground) els.transparentBackground.checked = background === "transparent";
}

export function updateTransparencyControls(): void {
  const { els, state } = getLegacyBridge();
  if (!els.transparentBackground) return;
  const supported = !state.generationCatalog || isGptImageModel(state.selectedModelId || "");
  const formatSupported = els.outputFormat?.value !== "jpeg";
  if (els.background?.value === "transparent") transparentPreference = true;
  const enabled = supported && formatSupported && transparentPreference;
  if (supported && els.background) {
    if (enabled) els.background.value = "transparent";
    else if (els.background.value === "transparent") els.background.value = "auto";
  }
  els.transparentBackground.checked = enabled;
  els.transparentBackground.disabled = !supported || !formatSupported;
  els.transparentBackgroundField?.classList.toggle("hidden", !supported);
  const label = document.getElementById("transparentBackgroundLabel");
  const labelKey = formatSupported ? "output.transparentBackground" : "output.transparencyUnavailable";
  if (label) {
    label.dataset.i18n = labelKey;
    label.textContent = translate(labelKey);
  }
  if (els.transparentBackgroundField) {
    els.transparentBackgroundField.title = formatSupported ? "" : translate("output.transparencyFormat");
  }
}

export function handleTransparentBackgroundChange(): void {
  const { els, methods } = getLegacyBridge();
  setBackgroundControl(els.transparentBackground?.checked ? "transparent" : "auto");
  updateTransparencyControls();
  methods.updateCompression?.();
  methods.saveCurrentModelParameterDraft?.();
  methods.updateRequestPreview?.();
  methods.refreshOutputSettingsLock?.();
}

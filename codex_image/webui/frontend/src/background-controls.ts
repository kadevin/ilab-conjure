import { isGptImageModel } from "./gpt-image-models";
import { translate } from "./i18n";
import { getLegacyBridge } from "./state";

export function setBackgroundControl(value: unknown): void {
  const { els } = getLegacyBridge();
  const background = value === "transparent" || value === "opaque" ? value : "auto";
  if (els.background) els.background.value = background;
  if (els.transparentBackground) els.transparentBackground.checked = background === "transparent";
}

export function updateTransparencyControls(): void {
  const { els, state } = getLegacyBridge();
  if (!els.transparentBackground) return;
  const supported = !state.generationCatalog || isGptImageModel(state.selectedModelId || "");
  const enabled = supported && els.background?.value === "transparent";
  els.transparentBackground.checked = els.background?.value === "transparent";
  els.transparentBackground.disabled = !supported;
  els.transparentBackgroundField?.classList.toggle("hidden", !supported);
  const jpegOption = els.outputFormat?.querySelector('option[value="jpeg"]');
  const jpegButton = els.outputFormatGroup?.querySelector('[data-val="jpeg"]');
  if (jpegOption) jpegOption.disabled = enabled;
  if (jpegButton) {
    jpegButton.disabled = enabled;
    jpegButton.title = enabled ? translate("output.transparencyFormat") : "";
  }
  if (enabled && els.outputFormat?.value === "jpeg") {
    els.outputFormat.value = "png";
    els.outputFormat.dispatchEvent(new Event("change"));
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

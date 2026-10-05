import { getLegacyBridge } from "./state";

/** Keep the preset in flow so both size editors always occupy the same area. */
export function setCustomSizeModeLayout(isCustom: boolean): void {
  const { els, state } = getLegacyBridge();
  const preset = document.getElementById("presetSizeFields");
  if (preset) {
    preset.inert = isCustom;
    preset.setAttribute("aria-hidden", String(isCustom));
  }
  if (els.customSize) {
    els.customSize.inert = !isCustom;
    els.customSize.setAttribute("aria-hidden", String(!isCustom));
  }
  els.settingsGrid?.classList.toggle("custom-size-mode", isCustom);
  state.customSizeMode = isCustom;
}

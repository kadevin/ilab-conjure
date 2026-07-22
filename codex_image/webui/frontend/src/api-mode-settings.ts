import { getLegacyBridge } from "./state";
import { selectedProviderBinding } from "./provider-selection";
import { resolveModeSettingsVisibility, type ModeSettingsVisibility } from "./mode-settings-visibility";

const bridge = getLegacyBridge();
const els = bridge.els;

function legacyMethod(name: string, ...args: any[]): any {
  const method = getLegacyBridge().methods[name];
  if (typeof method !== "function") {
    throw new Error("Legacy method " + name + " is not initialized");
  }
  return method(...args);
}

function currentAuthSource(): string { return legacyMethod("currentAuthSource"); }
function currentApiMode(): string { return legacyMethod("currentApiMode"); }
function currentCodexMode(): string { return legacyMethod("currentCodexMode"); }

export function setModeSpecificElementVisibility(element: any, visible: any): void {
  if (!element) return;
  element.setAttribute("aria-hidden", visible ? "false" : "true");
  if (visible) {
    element.classList.remove("hidden");
    element.classList.remove("mode-collapsed");
    return;
  }
  element.classList.add("mode-collapsed");
  element.classList.add("hidden");
}

function applyModeSettingsVisibility(visibility: ModeSettingsVisibility): void {
  const showModeSettings = visibility.showMainModel
    || visibility.showApiDirectNotice
    || visibility.showPromptFidelity;
  setModeSpecificElementVisibility(els.modeSettingsSlot, showModeSettings);
  setModeSpecificElementVisibility(els.modeSpecificSettings, showModeSettings);
  setModeSpecificElementVisibility(els.mainModelField, visibility.showMainModel);
  setModeSpecificElementVisibility(els.apiDirectSettingsNotice, visibility.showApiDirectNotice);
  setModeSpecificElementVisibility(els.promptFidelityField, visibility.showPromptFidelity);
}

function updateWebSearchAvailability(authSource: any = currentAuthSource()): void {
  const binding = selectedProviderBinding();
  const supported = binding
    ? binding.protocol_profile.endsWith("_responses")
    : authSource === "api" ? currentApiMode() === "responses" : currentCodexMode() === "responses";
  if (els.webSearch) {
    const wasChecked = Boolean(els.webSearch.checked);
    els.webSearch.disabled = !supported;
    if (!supported) els.webSearch.checked = false;
    if (wasChecked && !els.webSearch.checked) {
      els.webSearch.dispatchEvent(new Event("input"));
    }
  }
  if (els.webSearchField) {
    els.webSearchField.classList.toggle("is-disabled", !supported);
    els.webSearchField.setAttribute("aria-disabled", supported ? "false" : "true");
  }
}

export function setModeSettingsVariant(isDirectApi: any, visibility?: ModeSettingsVisibility): void {
  const slot = els.modeSettingsSlot;
  if (slot) {
    slot.style.height = "";
    slot.classList.remove("is-transitioning");
  }
  applyModeSettingsVisibility(visibility || resolveModeSettingsVisibility({
    catalogAvailable: false,
    modelId: null,
    protocolProfile: null,
    legacyDirectApi: Boolean(isDirectApi),
  }));
}

export function updateModeSpecificSettings(authSource: any = currentAuthSource()): void {
  const binding = selectedProviderBinding();
  const isDirectApi = binding
    ? !binding.protocol_profile.endsWith("_responses")
    : (authSource === "api" && currentApiMode() !== "responses")
      || (authSource === "codex" && currentCodexMode() !== "responses");
  setModeSettingsVariant(isDirectApi, resolveModeSettingsVisibility({
    catalogAvailable: Boolean(getLegacyBridge().state.generationCatalog),
    modelId: getLegacyBridge().state.selectedModelId,
    protocolProfile: binding?.protocol_profile || null,
    legacyDirectApi: isDirectApi,
  }));
  updateWebSearchAvailability(authSource);
  legacyMethod("syncReferenceFileAvailability");
  const refreshOutputSettingsLock = getLegacyBridge().methods.refreshOutputSettingsLock;
  if (typeof refreshOutputSettingsLock === "function") refreshOutputSettingsLock();
}

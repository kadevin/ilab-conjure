// @ts-nocheck
import { getLegacyBridge } from "./state";
import { LOCALE_CHANGE_EVENT, translate } from "./i18n";

const bridge = getLegacyBridge();
const els = bridge.els;

let storageSettingsFeatureInitialized = false;

function legacyMethod(name: string, ...args: any[]): any {
  const method = getLegacyBridge().methods[name];
  if (typeof method !== "function") {
    throw new Error("Legacy method " + name + " is not initialized");
  }
  return method(...args);
}

function setStatus(message: any, type?: any): void { legacyMethod("setStatus", message, type); }
function closePromptPopover(): void { legacyMethod("closePromptPopover"); }

async function refreshSettings() {
  if (!els.settingsInputRoot) return;
  try {
    const response = await fetch("/api/settings");
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || translate("settings.loadFailed"));
    populateSettingsForm(data.settings || {});
  } catch (error: any) {
    if (els.settingsStatus) els.settingsStatus.textContent = error.message || translate("settings.loadFailed");
  }
}

function populateSettingsForm(settings: any) {
  if (els.settingsInputRoot) els.settingsInputRoot.value = settings.input_root || "";
  if (els.settingsOutputRoot) els.settingsOutputRoot.value = settings.output_root || "";
  if (els.settingsGalleryRoot) els.settingsGalleryRoot.value = settings.gallery_root || "";
  if (els.settingsSourceDataRoot) els.settingsSourceDataRoot.value = settings.source_data_root || "";
}

function openSettingsModal() {
  closePromptPopover();
  refreshSettings();
  if (els.settingsStatus) els.settingsStatus.textContent = translate("settings.status");
  els.settingsModal?.classList.remove("hidden");
  els.settingsModal?.setAttribute("aria-hidden", "false");
}

function closeSettingsModal() {
  els.settingsModal?.classList.add("hidden");
  els.settingsModal?.setAttribute("aria-hidden", "true");
}

async function saveSettings() {
  if (!els.saveSettingsButton) return;
  els.saveSettingsButton.disabled = true;
  try {
    const response = await fetch("/api/settings", {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        input_root: els.settingsInputRoot?.value || "",
        output_root: els.settingsOutputRoot?.value || "",
        gallery_root: els.settingsGalleryRoot?.value || "",
        source_data_root: els.settingsSourceDataRoot?.value || "",
      }),
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || translate("settings.saveFailed"));
    populateSettingsForm(data.settings || {});
    if (els.settingsStatus) {
      els.settingsStatus.textContent = data.restart_required ? translate("settings.savedRestart") : translate("settings.saved");
    }
    setStatus(translate("settings.savedRestartStatus"), "ok");
  } catch (error: any) {
    if (els.settingsStatus) els.settingsStatus.textContent = error.message || translate("settings.saveFailed");
    setStatus(error.message || translate("settings.saveFailed"), "error");
  } finally {
    els.saveSettingsButton.disabled = false;
  }
}

export function initStorageSettingsFeature() {
  if (storageSettingsFeatureInitialized) return;
  storageSettingsFeatureInitialized = true;
  document.addEventListener(LOCALE_CHANGE_EVENT, () => {
    if (!els.settingsModal?.classList.contains("hidden") && els.settingsStatus) {
      els.settingsStatus.textContent = translate("settings.status");
    }
  });
  Object.assign(getLegacyBridge().methods, {
    refreshSettings,
    populateSettingsForm,
    openSettingsModal,
    closeSettingsModal,
    saveSettings,
  });
}

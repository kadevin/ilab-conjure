// @ts-nocheck
import { getLegacyBridge } from "./state";
import { LOCALE_CHANGE_EVENT, translate } from "./i18n";
import { closeSystemSettingsModal, openSystemSettingsModal } from "./system-settings";
import { showTransientNotice } from "./task-notifications";

const bridge = getLegacyBridge();
const els = bridge.els;

let storageSettingsFeatureInitialized = false;
let previousPaths: Record<string, string> = {};
let previousPathsAnnounced = false;

const pathLabels: Record<string, string> = {
  input_root: "settings.inputRoot",
  output_root: "settings.outputRoot",
  gallery_root: "settings.galleryRoot",
  source_data_root: "settings.sourceDataRoot",
};

function renderPreviousPaths(): void {
  const details = els.settingsPreviousPaths;
  const list = els.settingsPreviousPathsList;
  if (!details || !list) return;
  list.replaceChildren();
  for (const [key, label] of Object.entries(pathLabels)) {
    const path = previousPaths[key];
    if (typeof path !== "string" || !path) continue;
    const term = document.createElement("dt");
    term.textContent = translate(label);
    const value = document.createElement("dd");
    value.textContent = path;
    list.append(term, value);
  }
  details.hidden = !list.childElementCount;
  if (details.hidden) details.open = false;
}

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
    previousPaths = data.previous_paths || {};
    renderPreviousPaths();
    if (Object.keys(previousPaths).length && !previousPathsAnnounced) {
      previousPathsAnnounced = true;
      showTransientNotice(translate("settings.previousPathsNotice"));
    }
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
  openSystemSettingsModal("storage");
}

function closeSettingsModal() {
  closeSystemSettingsModal();
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
    renderPreviousPaths();
    if (!els.systemSettingsModal?.classList.contains("hidden") && !els.systemSettingsStoragePanel?.hidden && els.settingsStatus) {
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

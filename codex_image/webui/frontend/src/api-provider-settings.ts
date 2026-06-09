import { getLegacyBridge } from "./state";
import {
  API_SETTINGS_STORAGE_KEY,
  DEFAULT_API_BASE_URL,
  DEFAULT_API_IMAGE_MODEL,
  DEFAULT_API_IMAGES_CONCURRENCY,
  DEFAULT_API_MODE,
} from "./state-defaults";
import { refreshHealth } from "./auth-source";
import { updateModeSpecificSettings } from "./api-mode-settings";
import { formatTranslation, translate } from "./i18n";

const bridge = getLegacyBridge();
const state = bridge.state;
const els = bridge.els;

function legacyMethod(name: string, ...args: any[]): any {
  const method = getLegacyBridge().methods[name];
  if (typeof method !== "function") {
    throw new Error("Legacy method " + name + " is not initialized");
  }
  return method(...args);
}

function setStatus(message: any, type?: any): void { legacyMethod("setStatus", message, type); }
function updateRequestPreview(): void { legacyMethod("updateRequestPreview"); }
function closePromptPopover(): void { legacyMethod("closePromptPopover"); }

export function normalizeApiProvider(provider: any = {}, index: any = 0): any {
  const fallbackId = index === 0 ? "default" : `provider-${index + 1}`;
  const id = String(provider.id || fallbackId).trim().toLowerCase().replace(/[^a-z0-9_-]+/g, "-").replace(/^-+|-+$/g, "") || fallbackId;
  return {
    id,
    name: String(provider.name || (id === "default" ? "Default" : `Provider ${index + 1}`)).trim() || id,
    base_url: String(provider.base_url || DEFAULT_API_BASE_URL).trim() || DEFAULT_API_BASE_URL,
    api_key: String(provider.api_key || "").trim(),
    image_model: String(provider.image_model || DEFAULT_API_IMAGE_MODEL).trim() || DEFAULT_API_IMAGE_MODEL,
    api_mode: provider.api_mode === "responses" ? "responses" : DEFAULT_API_MODE,
    images_concurrency: normalizeApiImagesConcurrency(provider.images_concurrency),
    api_key_set: Boolean(provider.api_key_set || provider.api_key),
    api_key_masked: String(provider.api_key_masked || ""),
  };
}

export function normalizeApiImagesConcurrency(value: any): number {
  const parsed = Number.parseInt(value, 10);
  if (Number.isNaN(parsed)) return DEFAULT_API_IMAGES_CONCURRENCY;
  return Math.min(32, Math.max(1, parsed));
}

export function normalizeApiSettings(settings: any = {}): any {
  const rawProviders = Array.isArray(settings.providers) && settings.providers.length
    ? settings.providers
    : [{
      id: settings.active_provider_id || "default",
      name: settings.name || "Default",
      base_url: settings.base_url,
      api_key: settings.api_key,
      image_model: settings.image_model,
      api_mode: settings.api_mode,
      images_concurrency: settings.images_concurrency,
      api_key_set: settings.api_key_set,
      api_key_masked: settings.api_key_masked,
    }];
  const providers: any[] = [];
  const seen = new Set<string>();
  rawProviders.forEach((provider: any, index: number) => {
    const normalized = normalizeApiProvider(provider, index);
    if (seen.has(normalized.id)) return;
    seen.add(normalized.id);
    providers.push(normalized);
  });
  if (!providers.length) providers.push(normalizeApiProvider({}, 0));
  const requestedActive = String(settings.active_provider_id || providers[0].id).trim().toLowerCase();
  const activeProvider = providers.find((provider) => provider.id === requestedActive) || providers[0];
  return {
    active_provider_id: activeProvider.id,
    providers,
  };
}

export function activeApiProvider(): any {
  const settings = normalizeApiSettings(state.apiSettings);
  state.apiSettings = settings;
  return settings.providers.find((provider: any) => provider.id === settings.active_provider_id) || settings.providers[0];
}

export function restoreApiSettings(): void {
  try {
    const saved = JSON.parse(localStorage.getItem(API_SETTINGS_STORAGE_KEY) || "{}");
    state.apiSettings = normalizeApiSettings(saved);
  } catch {
    state.apiSettings = normalizeApiSettings();
  }
}

export function persistApiSettings(): void {
  try {
    localStorage.setItem(API_SETTINGS_STORAGE_KEY, JSON.stringify({
      active_provider_id: state.apiSettings.active_provider_id,
      providers: state.apiSettings.providers,
    }));
  } catch {
    // Browser storage may be unavailable in restricted contexts.
  }
}

export function mergeApiProviderKeys(serverSettings: any): any {
  const localById = new Map<string, any>((state.apiSettings.providers || []).map((provider: any) => [provider.id, provider]));
  const normalized = normalizeApiSettings(serverSettings);
  normalized.providers = normalized.providers.map((provider: any) => {
    const local = localById.get(provider.id);
    return local?.api_key ? { ...provider, api_key: local.api_key } : provider;
  });
  return normalized;
}

export async function refreshApiSettings(): Promise<void> {
  try {
    const response = await fetch("/api/api-settings");
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || translate("apiSettings.loadFailed"));
    state.apiSettings = mergeApiProviderKeys(data.settings || {});
    populateApiSettingsForm();
    updateModeSpecificSettings();
    updateRequestPreview();
  } catch (error: any) {
    setApiSettingsFeedback(error.message || translate("apiSettings.loadFailed"), "error");
  }
}

export function populateApiSettingsForm(): void {
  const provider = activeApiProvider();
  if (els.apiProviderQuick) {
    els.apiProviderQuick.innerHTML = "";
    state.apiSettings.providers.forEach((item: any) => {
      const option = document.createElement("option");
      option.value = item.id;
      option.textContent = item.name || item.id;
      els.apiProviderQuick.append(option);
    });
    els.apiProviderQuick.value = provider.id;
  }
  if (els.apiProvider) {
    els.apiProvider.innerHTML = "";
    state.apiSettings.providers.forEach((item: any) => {
      const option = document.createElement("option");
      option.value = item.id;
      option.textContent = item.name || item.id;
      els.apiProvider.append(option);
    });
    els.apiProvider.value = provider.id;
  }
  if (els.apiProviderName) els.apiProviderName.value = provider.name || "";
  if (els.apiBaseUrl) els.apiBaseUrl.value = provider.base_url || DEFAULT_API_BASE_URL;
  if (els.apiMode) {
    els.apiMode.value = provider.api_mode || DEFAULT_API_MODE;
    els.apiMode.dispatchEvent(new Event("change"));
  }
  if (els.apiImageModel) els.apiImageModel.value = provider.image_model || DEFAULT_API_IMAGE_MODEL;
  if (els.apiImagesConcurrency) els.apiImagesConcurrency.value = String(normalizeApiImagesConcurrency(provider.images_concurrency));
  if (els.apiKey) {
    els.apiKey.value = provider.api_key || "";
    els.apiKey.placeholder = provider.api_key_set && !provider.api_key
      ? translate("apiSettings.savedKeyPlaceholder")
      : "sk-...";
  }
  if (els.deleteApiProviderButton) {
    els.deleteApiProviderButton.disabled = state.apiSettings.providers.length <= 1;
  }
  updateModeSpecificSettings();
}

export function readApiSettingsForm(): any {
  const settings = normalizeApiSettings(state.apiSettings);
  const activeId = settings.active_provider_id;
  settings.providers = settings.providers.map((provider: any) => provider.id === activeId ? normalizeApiProvider({
    ...provider,
    name: els.apiProviderName?.value || provider.name,
    base_url: els.apiBaseUrl?.value || DEFAULT_API_BASE_URL,
    api_key: els.apiKey?.value || "",
    api_mode: els.apiMode?.value || DEFAULT_API_MODE,
    image_model: els.apiImageModel?.value || DEFAULT_API_IMAGE_MODEL,
    images_concurrency: normalizeApiImagesConcurrency(els.apiImagesConcurrency?.value),
  }, 0) : provider);
  state.apiSettings = normalizeApiSettings(settings);
  return state.apiSettings;
}

export function currentApiProviderId(): string {
  return activeApiProvider().id;
}

export function currentApiProviderLabel(): string {
  const provider = activeApiProvider();
  return String(provider.name || provider.id || "").trim() || provider.id;
}

export function addApiProvider(): void {
  readApiSettingsForm();
  const id = `provider-${Date.now()}`;
  state.apiSettings.providers.push(normalizeApiProvider({
    id,
    name: translate("apiSettings.newProvider"),
    base_url: DEFAULT_API_BASE_URL,
    image_model: DEFAULT_API_IMAGE_MODEL,
    api_mode: DEFAULT_API_MODE,
    images_concurrency: DEFAULT_API_IMAGES_CONCURRENCY,
  }, state.apiSettings.providers.length));
  state.apiSettings.active_provider_id = id;
  populateApiSettingsForm();
  persistApiSettings();
  updateModeSpecificSettings();
  updateRequestPreview();
}

export function deleteApiProvider(): void {
  readApiSettingsForm();
  if (state.apiSettings.providers.length <= 1) return;
  const activeId = state.apiSettings.active_provider_id;
  state.apiSettings.providers = state.apiSettings.providers.filter((provider: any) => provider.id !== activeId);
  state.apiSettings.active_provider_id = state.apiSettings.providers[0]?.id || "default";
  populateApiSettingsForm();
  persistApiSettings();
  updateModeSpecificSettings();
  updateRequestPreview();
}

export function openApiSettingsModal(): void {
  closePromptPopover();
  populateApiSettingsForm();
  setApiSettingsFeedback(translate("apiSettings.status"), "");
  els.apiSettingsModal?.classList.remove("hidden");
  els.apiSettingsModal?.setAttribute("aria-hidden", "false");
  els.apiBaseUrl?.focus();
}

export function closeApiSettingsModal(): void {
  els.apiSettingsModal?.classList.add("hidden");
  els.apiSettingsModal?.setAttribute("aria-hidden", "true");
}

export function currentApiImageModel(): string {
  return (activeApiProvider().image_model || DEFAULT_API_IMAGE_MODEL).trim() || DEFAULT_API_IMAGE_MODEL;
}

export function currentApiMode(): string {
  return activeApiProvider().api_mode === "responses" ? "responses" : DEFAULT_API_MODE;
}

export function currentApiImagesConcurrency(): number {
  return normalizeApiImagesConcurrency(activeApiProvider().images_concurrency);
}

export function apiModeLabel(mode: any): string {
  return mode === "responses" ? "Responses" : translate("apiSettings.modeImagesShort");
}

export function backendForAuthSource(authSource: any, apiMode: any = currentApiMode()): string {
  return authSource === "api"
    ? (apiMode === "responses" ? "openai_responses" : "openai_images")
    : "codex_responses";
}

export function taskBackendValue(task: any): string {
  return String(task?.backend || task?.requested_backend || "").trim();
}

export function taskApiProviderId(task: any): string {
  return String(
    task?.api_provider_id
    || task?.params?.api_provider_id
    || task?.request?.webui_api_provider_id
    || task?.request?.api_provider_id
    || "",
  ).trim();
}

export function taskApiProviderLabel(task: any): string {
  const providerId = taskApiProviderId(task);
  if (!providerId) return "";
  const providerName = String(
    task?.api_provider_name
    || task?.params?.api_provider_name
    || task?.request?.webui_api_provider_name
    || task?.request?.api_provider_name
    || "",
  ).trim();
  const configuredProvider = state.apiSettings.providers.find((provider: any) => provider.id === providerId);
  const label = providerName || configuredProvider?.name || providerId;
  return label === providerId ? label : `${label} (${providerId})`;
}

export function taskBackendLabel(task: any): string {
  const backend = taskBackendValue(task);
  const provider = taskApiProviderLabel(task);
  return [backend, provider].filter(Boolean).join(" · ");
}

export function setApiSettingsFeedback(message: any, type: any = ""): void {
  if (!els.apiSettingsStatus) return;
  els.apiSettingsStatus.textContent = message;
  els.apiSettingsStatus.className = `api-settings-feedback ${type || ""}`.trim();
}

export async function saveApiSettings(): Promise<void> {
  if (!els.saveApiSettingsButton) return;
  if (state.apiSettingsSaveTimerId) {
    window.clearTimeout(state.apiSettingsSaveTimerId);
    state.apiSettingsSaveTimerId = null;
  }
  const settings = readApiSettingsForm();
  persistApiSettings();
  const payload: any = {
    active_provider_id: settings.active_provider_id,
    providers: settings.providers.map((provider: any) => {
      const item: any = {
        id: provider.id,
        name: provider.name,
        base_url: provider.base_url,
        image_model: provider.image_model,
        api_mode: provider.api_mode,
      };
      item.images_concurrency = provider.images_concurrency;
      if (provider.api_key || !provider.api_key_set) item.api_key = provider.api_key;
      return item;
    }),
  };
  els.saveApiSettingsButton.disabled = true;
  els.saveApiSettingsButton.textContent = translate("apiSettings.saving");
  setApiSettingsFeedback(translate("apiSettings.savingStatus"), "running");
  try {
    const response = await fetch("/api/api-settings", {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || translate("apiSettings.saveFailed"));
    state.apiSettings = mergeApiProviderKeys(data.settings || {});
    persistApiSettings();
    populateApiSettingsForm();
    setApiSettingsFeedback(formatTranslation("apiSettings.savedSummary", {
      provider: activeApiProvider().name,
      mode: apiModeLabel(currentApiMode()),
      model: currentApiImageModel(),
      concurrency: currentApiImagesConcurrency(),
    }), "ok");
    els.saveApiSettingsButton.textContent = translate("apiSettings.savedShort");
    state.apiSettingsSaveTimerId = window.setTimeout(() => {
      els.saveApiSettingsButton.textContent = translate("apiSettings.save");
      state.apiSettingsSaveTimerId = null;
    }, 1600);
    setStatus(translate("apiSettings.savedStatus"), "ok");
    await refreshHealth();
    updateRequestPreview();
  } catch (error: any) {
    setApiSettingsFeedback(error.message || translate("apiSettings.saveFailed"), "error");
    els.saveApiSettingsButton.textContent = translate("apiSettings.saveFailedShort");
    setStatus(error.message || translate("apiSettings.saveFailed"), "error");
  } finally {
    els.saveApiSettingsButton.disabled = false;
    if (!state.apiSettingsSaveTimerId && els.saveApiSettingsButton.textContent !== translate("apiSettings.save")) {
      state.apiSettingsSaveTimerId = window.setTimeout(() => {
        els.saveApiSettingsButton.textContent = translate("apiSettings.save");
        state.apiSettingsSaveTimerId = null;
      }, 1600);
    }
  }
}

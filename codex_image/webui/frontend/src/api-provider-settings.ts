import { getLegacyBridge } from "./state";
import {
  API_SETTINGS_STORAGE_KEY,
  DEFAULT_API_BASE_URL,
  DEFAULT_API_IMAGE_MODEL,
  DEFAULT_API_IMAGES_CONCURRENCY,
  DEFAULT_API_MODE,
  DEFAULT_CODEX_MODE,
} from "./state-defaults";
import { refreshHealth } from "./auth-source";
import { refreshGenerationCatalog } from "./model-catalog";
import { providerBindingSelectionKey, selectedProviderBinding } from "./provider-selection";
import { updateModeSpecificSettings } from "./api-mode-settings";
import { formatTranslation, translate } from "./i18n";
import { closeSystemSettingsModal, openSystemSettingsModal } from "./system-settings";
import { resetApiAdvancedSettings } from "./api-advanced-settings";
import { syncThemedSelect } from "./themed-select";
import {
  apiProviderMatchesSearch,
  scrollActiveApiProviderCardIntoView,
  updateApiProviderListPresentation,
} from "./api-provider-list-ui";
import {
  BINDING_PROTOCOL_LABELS,
  BINDING_COMPATIBILITY_LABELS,
  availableCompatibilityLayers,
  availableProtocolsForModel,
  bindingFromProtocol,
  bindingTemplateForProtocol,
  bindingTemplateForCompatibility,
  bindingTemplateSuggestion,
  isBindingTemplateBaseUrl,
  normalizeProviderBindings,
  readProviderBindingCards,
  renderProviderBindingCards,
  validateProviderBindingOverlaps,
} from "./provider-model-bindings";
import type { BindingProtocol } from "./provider-model-bindings";
import type { BindingCompatibility } from "./provider-model-bindings";

const bridge = getLegacyBridge();
const state = bridge.state;
const els = bridge.els;
let apiSettingsAutosaveTimerId: number | null = null;

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
function openConfirmPopover(...args: any[]): void { legacyMethod("openConfirmPopover", ...args); }

export function normalizeApiProvider(provider: any = {}, index: any = 0): any {
  const fallbackId = index === 0 ? "default" : `provider-${index + 1}`;
  const id = String(provider.id || fallbackId).trim().toLowerCase().replace(/[^a-z0-9_-]+/g, "-").replace(/^-+|-+$/g, "") || fallbackId;
  const legacyMode = provider.api_mode === "responses" ? "responses" : DEFAULT_API_MODE;
  const bindings = normalizeProviderBindings(
    Array.isArray(provider.bindings) && provider.bindings.length
      ? provider.bindings
      : [{
        id: `${id}-gpt-image-2`,
        canonical_model_id: "gpt-image-2",
        remote_model_id: String(provider.image_model || DEFAULT_API_IMAGE_MODEL).trim() || DEFAULT_API_IMAGE_MODEL,
        protocol_profile: legacyMode === "responses" ? "openai_responses" : "openai_images",
        parameter_codec: legacyMode === "responses" ? "gpt_openai_responses" : "gpt_openai_images",
        operations: ["generate", "edit"],
      }],
    id,
  );
  const gptBinding = bindings.find((binding) => binding.canonical_model_id === "gpt-image-2") || bindings[0];
  const apiMode = gptBinding?.protocol_profile === "openai_responses" ? "responses" : "images";
  const concurrency = normalizeApiImagesConcurrency(provider.concurrency ?? provider.images_concurrency);
  return {
    id,
    name: String(provider.name || (id === "default" ? "Default" : `Provider ${index + 1}`)).trim() || id,
    base_url: String(provider.base_url || DEFAULT_API_BASE_URL).trim() || DEFAULT_API_BASE_URL,
    api_key: String(provider.api_key || "").trim(),
    concurrency,
    bindings,
    image_model: gptBinding?.remote_model_id || DEFAULT_API_IMAGE_MODEL,
    api_mode: apiMode,
    images_concurrency: concurrency,
    api_key_set: Boolean(provider.api_key_set || provider.api_key),
    api_key_masked: String(provider.api_key_masked || ""),
    api_key_source_provider_id: String(provider.api_key_source_provider_id || "").trim(),
    icon_emoji: String(provider.icon_emoji || "").trim(),
    default_model_ids: Array.isArray(provider.default_model_ids)
      ? provider.default_model_ids.map((value: any) => String(value || "").trim()).filter(Boolean)
      : [],
  };
}

function appendProviderIdentity(target: HTMLElement, provider: any, className: string): void {
  const icon = String(provider?.icon_emoji || "").trim();
  if (icon) {
    const emoji = document.createElement("span");
    emoji.className = "api-provider-emoji";
    emoji.setAttribute("aria-hidden", "true");
    emoji.textContent = icon;
    target.append(emoji);
  }
  const label = document.createElement("span");
  label.className = className;
  label.textContent = provider?.name || provider?.id || "";
  target.append(label);
}

export function normalizeApiImagesConcurrency(value: any): number {
  const parsed = Number.parseInt(value, 10);
  if (Number.isNaN(parsed)) return DEFAULT_API_IMAGES_CONCURRENCY;
  return Math.min(32, Math.max(1, parsed));
}

function normalizeCodexMode(value: any): string {
  return value === "responses" ? "responses" : DEFAULT_CODEX_MODE;
}

function providerById(providerId: any, settings: any = state.apiSettings): any {
  const normalized = normalizeApiSettings(settings);
  return normalized.providers.find((provider: any) => provider.id === providerId) || normalized.providers[0];
}

function providerMode(provider: any): string {
  const binding = provider?.bindings?.find?.((item: any) => item.canonical_model_id === "gpt-image-2") || provider?.bindings?.[0];
  return binding?.protocol_profile === "openai_responses" ? "responses" : DEFAULT_API_MODE;
}

function apiBaseUrlForEndpoint(value: any): string {
  const withoutQueryOrFragment = String(value || DEFAULT_API_BASE_URL).trim().split(/[?#]/, 1)[0] || "";
  let baseUrl = withoutQueryOrFragment.replace(/\/+$/, "") || DEFAULT_API_BASE_URL;
  for (const suffix of ["/responses", "/images/generations", "/images/edits"]) {
    if (!baseUrl.endsWith(suffix)) continue;
    baseUrl = baseUrl.slice(0, -suffix.length).replace(/\/+$/, "");
    break;
  }
  return baseUrl || DEFAULT_API_BASE_URL;
}

export function updateApiRequestEndpointPreview(): void {
  if (!els.apiRequestEndpointPreview) return;
  const provider = state.apiProviderDraft || activeApiProvider();
  const baseUrl = apiBaseUrlForEndpoint(els.apiBaseUrl?.value || provider?.base_url);
  const bindingCount = readProviderBindingCards(els.apiProviderBindings).length || provider?.bindings?.length || 0;
  const preview = `${baseUrl} · ${bindingCount} · ${translate("apiSettings.modelBindings")}`;
  els.apiRequestEndpointPreview.textContent = preview;
  els.apiRequestEndpointPreview.title = preview;
}

function providerHasApiKey(provider: any): boolean {
  return Boolean(provider?.api_key || provider?.api_key_set);
}

function providerKeyLabel(provider: any): string {
  if (!providerHasApiKey(provider)) return translate("apiSettings.keyNotSet");
  return provider.api_key_masked || translate("apiSettings.keySaved");
}

function providerMetaLabel(provider: any): string {
  return [
    `${provider?.bindings?.length || 0} · ${translate("apiSettings.modelBindings")}`,
    formatTranslation("apiSettings.concurrencyValue", {
      concurrency: String(normalizeApiImagesConcurrency(provider?.concurrency ?? provider?.images_concurrency)),
    }),
  ].filter(Boolean).join(" · ");
}

function uniqueCopiedProviderId(provider: any): string {
  const base = String(provider?.id || provider?.name || "provider")
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9_-]+/g, "-")
    .replace(/^-+|-+$/g, "")
    || "provider";
  const existing = new Set((state.apiSettings.providers || []).map((item: any) => item.id));
  const root = `${base}-copy`;
  if (!existing.has(root)) return root;
  for (let index = 2; index < 1000; index += 1) {
    const candidate = `${root}-${index}`;
    if (!existing.has(candidate)) return candidate;
  }
  return `provider-${Date.now()}`;
}

function copiedProviderName(provider: any): string {
  const sourceName = String(provider?.name || provider?.id || translate("apiSettings.newProvider")).trim();
  const rootName = formatTranslation("apiSettings.copyProviderName", { name: sourceName });
  const existing = new Set((state.apiSettings.providers || []).map((item: any) => String(item.name || "").trim()));
  if (!existing.has(rootName)) return rootName;
  for (let index = 2; index < 1000; index += 1) {
    const candidate = `${rootName} ${index}`;
    if (!existing.has(candidate)) return candidate;
  }
  return `${rootName} ${Date.now()}`;
}

function setElementText(element: any, value: any): void {
  if (element) element.textContent = String(value ?? "");
}

export function setApiKeyRevealVisible(visible: boolean): void {
  if (!els.apiKey) return;
  const canReveal = Boolean(els.apiKey.value);
  const shouldReveal = Boolean(visible && canReveal);
  els.apiKey.type = shouldReveal ? "text" : "password";
  els.apiKeyRevealButton?.setAttribute("aria-pressed", shouldReveal ? "true" : "false");
  const label = translate(shouldReveal ? "apiSettings.hideApiKey" : "apiSettings.showApiKey");
  els.apiKeyRevealButton?.setAttribute("aria-label", label);
  els.apiKeyRevealButton?.setAttribute("title", label);
  els.apiKeyRevealButton?.classList.toggle("active", shouldReveal);
}

export function hideApiKeyReveal(): void {
  setApiKeyRevealVisible(false);
}

export function updateApiKeyRevealButton(): void {
  if (!els.apiKeyRevealButton) return;
  const canReveal = Boolean(els.apiKey?.value);
  if (!canReveal) hideApiKeyReveal();
  els.apiKeyRevealButton.disabled = !canReveal;
  const label = translate("apiSettings.showApiKey");
  els.apiKeyRevealButton.setAttribute("aria-label", label);
  els.apiKeyRevealButton.setAttribute("title", label);
}

export function revealApiKeyWhilePressed(event?: Event): void {
  if (!els.apiKey?.value || els.apiKeyRevealButton?.disabled) return;
  event?.preventDefault();
  setApiKeyRevealVisible(true);
}

function scrollApiProviderEditorIntoView(): void {
  window.requestAnimationFrame(() => {
    els.apiProviderEditor?.scrollIntoView?.({ block: "nearest", inline: "nearest" });
  });
}

function setApiProviderEditorVisible(visible: boolean): void {
  els.apiProviderSection?.classList.toggle("editing", visible);
  els.apiProviderSection?.setAttribute("aria-hidden", visible ? "true" : "false");
  if (visible) els.apiProviderSection?.setAttribute("inert", "");
  else els.apiProviderSection?.removeAttribute("inert");
  els.apiProviderEditor?.classList.toggle("hidden", !visible);
  els.apiProviderEditor?.setAttribute("aria-hidden", visible ? "false" : "true");
  els.apiProviderDetail?.classList.toggle("hidden", visible);
  els.apiSettingsActions?.classList.toggle("hidden", visible);
  els.apiSettingsActions?.setAttribute("aria-hidden", visible ? "true" : "false");
  if (els.editApiProviderButton) els.editApiProviderButton.disabled = visible;
  if (els.addApiProviderButton) els.addApiProviderButton.disabled = visible;
  if (els.copyApiProviderButton) els.copyApiProviderButton.disabled = visible;
  if (els.sortApiProvidersButton) els.sortApiProvidersButton.disabled = visible;
  if (els.deleteApiProviderButton) {
    els.deleteApiProviderButton.disabled = visible || normalizeApiSettings(state.apiSettings).providers.length <= 1;
  }
  if (!visible) hideApiKeyReveal();
}

function apiProviderEditorActive(): boolean {
  return Boolean(state.apiProviderEditingId && state.apiProviderDraft);
}

function draftProviderFromForm(): any {
  const draft = state.apiProviderDraft || activeApiProvider();
  const bindingCards = readProviderBindingCards(els.apiProviderBindings);
  return normalizeApiProvider({
    ...draft,
    name: els.apiProviderName?.value || draft.name,
    icon_emoji: els.apiProviderIconEmoji ? els.apiProviderIconEmoji.value : draft.icon_emoji,
    base_url: els.apiBaseUrl?.value || DEFAULT_API_BASE_URL,
    api_key: els.apiKey?.value || "",
    concurrency: normalizeApiImagesConcurrency(els.apiImagesConcurrency?.value),
    bindings: bindingCards,
    default_model_ids: bindingCards.filter((binding) => binding.is_default).map((binding) => binding.canonical_model_id),
    api_key_set: Boolean(draft.api_key_set || draft.api_key || draft.api_key_source_provider_id),
    api_key_masked: draft.api_key_masked,
    api_key_source_provider_id: draft.api_key_source_provider_id,
  }, 0);
}

function writeProviderForm(provider: any): void {
  if (els.apiProviderName) els.apiProviderName.value = provider.name || "";
  if (els.apiProviderIconEmoji) els.apiProviderIconEmoji.value = provider.icon_emoji || "";
  if (els.apiBaseUrl) els.apiBaseUrl.value = provider.base_url || DEFAULT_API_BASE_URL;
  if (els.apiImagesConcurrency) els.apiImagesConcurrency.value = String(normalizeApiImagesConcurrency(provider.concurrency ?? provider.images_concurrency));
  if (els.apiKey) {
    els.apiKey.value = provider.api_key || "";
    els.apiKey.placeholder = provider.api_key_set && !provider.api_key
      ? translate("apiSettings.savedKeyPlaceholder")
      : "sk-...";
  }
  hideApiKeyReveal();
  updateApiKeyRevealButton();
  renderProviderBindingCards(
    els.apiProviderBindings,
    provider.bindings || [],
    state.generationCatalog?.models || [],
    provider.id,
    state.apiSettings.default_provider_by_model || {},
  );
  updateApiRequestEndpointPreview();
  resetApiAdvancedSettings();
}

function defaultsForProviderDraft(provider: any): Record<string, string> {
  const defaults = { ...(state.apiSettings.default_provider_by_model || {}) };
  (provider.default_model_ids || []).forEach((modelId: string) => { defaults[modelId] = provider.id; });
  return defaults;
}

export function renderApiProviderList(): void {
  const settings = normalizeApiSettings(state.apiSettings);
  state.apiSettings = settings;
  const sorting = Boolean(state.apiProviderSortMode && settings.providers.length > 1);
  const searchQuery = updateApiProviderListPresentation(settings.providers.length, sorting);
  setElementText(els.apiProviderCount, formatTranslation("apiSettings.providerCount", {
    count: String(settings.providers.length),
  }));
  if (els.sortApiProvidersButton) {
    const canSort = settings.providers.length > 1;
    els.sortApiProvidersButton.classList.toggle("hidden", !canSort);
    els.sortApiProvidersButton.classList.toggle("active", sorting);
    els.sortApiProvidersButton.disabled = apiProviderEditorActive() || !canSort;
    els.sortApiProvidersButton.textContent = translate(sorting ? "apiSettings.finishSortProviders" : "apiSettings.sortProviders");
    els.sortApiProvidersButton.setAttribute("aria-pressed", sorting ? "true" : "false");
  }
  els.addApiProviderButton?.classList.toggle("hidden", sorting || apiProviderEditorActive());
  if (!els.apiProviderList) return;
  els.apiProviderList.classList.toggle("is-sorting", sorting);
  els.apiProviderList.setAttribute("role", sorting ? "list" : "listbox");
  if (sorting) {
    const rows = settings.providers.map((provider: any, index: number) => {
      const row = document.createElement("div");
      row.className = `api-provider-sort-row${provider.id === settings.active_provider_id ? " active" : ""}`;
      row.dataset.apiProviderId = provider.id;
      row.setAttribute("role", "listitem");
      const content = document.createElement("div");
      content.className = "api-provider-sort-content";
      const name = document.createElement("strong");
      name.className = "api-provider-sort-name";
      appendProviderIdentity(name, provider, "api-provider-choice-label");
      const meta = document.createElement("span");
      meta.textContent = providerMetaLabel(provider);
      content.append(name, meta);
      const controls = document.createElement("div");
      controls.className = "api-provider-sort-actions";
      [
        ["up", "apiSettings.moveProviderUp", "apiSettings.moveProviderUpAria", index <= 0],
        ["down", "apiSettings.moveProviderDown", "apiSettings.moveProviderDownAria", index >= settings.providers.length - 1],
      ].forEach(([direction, labelKey, ariaKey, disabled]: any[]) => {
        const button = document.createElement("button");
        button.type = "button";
        button.className = "ghost-button api-provider-sort-button";
        button.dataset.apiProviderId = provider.id;
        button.dataset.apiProviderSort = direction;
        button.disabled = Boolean(disabled);
        button.textContent = translate(labelKey);
        button.setAttribute("aria-label", formatTranslation(ariaKey, { provider: provider.name || provider.id }));
        controls.append(button);
      });
      row.append(content, controls);
      return row;
    });
    els.apiProviderList.replaceChildren(...rows);
    return;
  }
  const visibleProviders = settings.providers.filter((provider: any) => apiProviderMatchesSearch(provider, searchQuery));
  const buttons = visibleProviders.map((provider: any) => {
    const button = document.createElement("button");
    const active = provider.id === settings.active_provider_id;
    button.type = "button";
    button.className = `api-provider-choice${active ? " active" : ""}`;
    button.dataset.apiProviderId = provider.id;
    button.setAttribute("role", "option");
    button.setAttribute("aria-selected", active ? "true" : "false");
    const name = document.createElement("strong");
    name.className = "api-provider-choice-name";
    appendProviderIdentity(name, provider, "api-provider-choice-label");
    const meta = document.createElement("span");
    meta.textContent = providerMetaLabel(provider);
    button.append(name, meta);
    return button;
  });
  if (!buttons.length) {
    const empty = document.createElement("div");
    empty.className = "api-provider-search-empty";
    empty.textContent = translate("apiSettings.noProviderSearchResults");
    els.apiProviderList.replaceChildren(empty);
    return;
  }
  els.apiProviderList.replaceChildren(...buttons);
  if (!searchQuery) scrollActiveApiProviderCardIntoView(settings.active_provider_id, "center");
}

function renderApiProviderDetail(): void {
  const provider = activeApiProvider();
  setElementText(els.apiProviderDetailBaseUrl, provider.base_url || DEFAULT_API_BASE_URL);
  setElementText(els.apiProviderDetailKey, providerKeyLabel(provider));
  setElementText(
    els.apiProviderDetailMode,
    `${provider.bindings?.length || 0} · ${translate("apiSettings.modelBindings")}`,
  );
  setElementText(els.apiProviderDetailConcurrency, normalizeApiImagesConcurrency(provider.concurrency ?? provider.images_concurrency));
}

function renderApiProviderEditor(): void {
  const editing = apiProviderEditorActive();
  setApiProviderEditorVisible(editing);
  if (!editing) return;
  const isNew = Boolean(state.apiProviderDraftIsNew);
  setElementText(els.apiProviderEditorTitle, translate(isNew ? "apiSettings.newProviderTitle" : "apiSettings.editProvider"));
  writeProviderForm(state.apiProviderDraft);
}

function applyApiProviderDraft(settings: any): any {
  if (!apiProviderEditorActive()) return normalizeApiSettings(settings);
  const draft = draftProviderFromForm();
  const normalized = normalizeApiSettings(settings);
  const index = normalized.providers.findIndex((provider: any) => provider.id === draft.id);
  if (index >= 0) {
    normalized.providers[index] = normalizeApiProvider({ ...normalized.providers[index], ...draft }, index);
  } else {
    normalized.providers.push(normalizeApiProvider(draft, normalized.providers.length));
  }
  normalized.active_provider_id = draft.id;
  const defaultModelIds = new Set(draft.default_model_ids || []);
  for (const binding of draft.bindings || []) {
    const modelId = binding.canonical_model_id;
    if (defaultModelIds.has(modelId)) normalized.default_provider_by_model[modelId] = draft.id;
    else if (normalized.default_provider_by_model[modelId] === draft.id) delete normalized.default_provider_by_model[modelId];
  }
  for (const modelId of Object.keys(normalized.default_provider_by_model)) {
    if (normalized.default_provider_by_model[modelId] !== draft.id) continue;
    if (!(draft.bindings || []).some((binding: any) => binding.canonical_model_id === modelId)) {
      delete normalized.default_provider_by_model[modelId];
    }
  }
  state.apiProviderEditingId = null;
  state.apiProviderDraft = null;
  state.apiProviderDraftIsNew = false;
  return normalizeApiSettings(normalized);
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
    schema_version: 2,
    codex_mode: normalizeCodexMode(settings.codex_mode),
    active_provider_id: activeProvider.id,
    default_provider_by_model: { ...(settings.default_provider_by_model || { "gpt-image-2": activeProvider.id }) },
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
      codex_mode: state.apiSettings.codex_mode,
      active_provider_id: state.apiSettings.active_provider_id,
      default_provider_by_model: state.apiSettings.default_provider_by_model,
      providers: state.apiSettings.providers.map((provider: any) => ({
        id: provider.id,
        name: provider.name,
        icon_emoji: provider.icon_emoji || "",
        concurrency: provider.concurrency,
        bindings: provider.bindings,
        api_key_set: provider.api_key_set,
        api_key_masked: provider.api_key_masked,
      })),
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
    renderAuthSourceAfterProviderChange();
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
  renderApiProviderList();
  renderApiProviderDetail();
  renderApiProviderEditor();
  updateModeSpecificSettings();
}

export function readApiSettingsForm(options: any = {}): any {
  const settings = normalizeApiSettings(state.apiSettings);
  state.apiSettings = options.applyProviderDraft ? applyApiProviderDraft(settings) : normalizeApiSettings(settings);
  return state.apiSettings;
}

export function currentApiProviderId(): string {
  if (state.selectedProviderId && state.selectedProviderId !== "codex") return state.selectedProviderId;
  return activeApiProvider().id;
}

export function currentApiProviderLabel(): string {
  const selected = state.generationCatalog?.providers.find((provider: any) => provider.id === state.selectedProviderId);
  if (selected) return String(selected.name || selected.id);
  const provider = activeApiProvider();
  return String(provider.name || provider.id || "").trim() || provider.id;
}

export function addApiProvider(): void {
  if (apiProviderEditorActive()) {
    setApiSettingsFeedback(translate("apiSettings.finishEditFirst"), "error");
    return;
  }
  state.apiProviderSortMode = false;
  const id = `provider-${Date.now()}`;
  state.apiProviderEditingId = id;
  state.apiProviderDraftIsNew = true;
  state.apiProviderDraft = normalizeApiProvider({
    id,
    name: translate("apiSettings.newProvider"),
    base_url: DEFAULT_API_BASE_URL,
    concurrency: DEFAULT_API_IMAGES_CONCURRENCY,
    bindings: [bindingFromProtocol(`${id}-gpt-image-2`, "gpt-image-2", DEFAULT_API_IMAGE_MODEL, "openai_images")],
  }, state.apiSettings.providers.length);
  populateApiSettingsForm();
  setApiSettingsFeedback(translate("apiSettings.newDraftStatus"), "running");
  scrollApiProviderEditorIntoView();
  els.apiProviderName?.focus();
}

export function copyApiProvider(): void {
  if (apiProviderEditorActive()) {
    setApiSettingsFeedback(translate("apiSettings.finishEditFirst"), "error");
    return;
  }
  state.apiProviderSortMode = false;
  const provider = activeApiProvider();
  const copiesSavedKey = providerHasApiKey(provider);
  const id = uniqueCopiedProviderId(provider);
  state.apiProviderEditingId = id;
  state.apiProviderDraftIsNew = true;
  state.apiProviderDraft = normalizeApiProvider({
    ...provider,
    bindings: provider.bindings.map((binding: any, index: number) => ({ ...binding, id: `${id}-binding-${index + 1}` })),
    id,
    name: copiedProviderName(provider),
    api_key: "",
    api_key_set: copiesSavedKey,
    api_key_masked: provider.api_key_masked || "",
    api_key_source_provider_id: copiesSavedKey ? provider.id : "",
  }, state.apiSettings.providers.length);
  populateApiSettingsForm();
  setApiSettingsFeedback(translate(copiesSavedKey ? "apiSettings.copyProviderStatus" : "apiSettings.copyProviderWithoutKeyStatus"), "running");
  scrollApiProviderEditorIntoView();
  els.apiProviderName?.focus();
}

export function deleteApiProvider(): void {
  if (apiProviderEditorActive()) {
    setApiSettingsFeedback(translate("apiSettings.finishEditFirst"), "error");
    return;
  }
  if (state.apiSettings.providers.length <= 1) return;
  const activeId = state.apiSettings.active_provider_id;
  state.apiSettings.providers = state.apiSettings.providers.filter((provider: any) => provider.id !== activeId);
  state.apiSettings.active_provider_id = state.apiSettings.providers[0]?.id || "default";
  Object.entries(state.apiSettings.default_provider_by_model || {}).forEach(([modelId, providerId]) => {
    if (providerId === activeId) delete state.apiSettings.default_provider_by_model[modelId];
  });
  Object.entries(state.lastProviderByModel || {}).forEach(([modelId, providerId]) => {
    if (providerId === activeId) delete state.lastProviderByModel[modelId];
  });
  if (state.apiSettings.providers.length <= 1) state.apiProviderSortMode = false;
  populateApiSettingsForm();
  persistApiSettings();
  renderAuthSourceAfterProviderChange();
  setApiSettingsFeedback(translate("apiSettings.deleteProviderStatus"), "running");
  queueApiSettingsAutosave();
}

export function confirmDeleteApiProvider(anchor: any = els.deleteApiProviderButton): void {
  if (apiProviderEditorActive()) {
    setApiSettingsFeedback(translate("apiSettings.finishEditFirst"), "error");
    return;
  }
  if (state.apiSettings.providers.length <= 1) return;
  const provider = activeApiProvider();
  openConfirmPopover(anchor || els.deleteApiProviderButton, {
    title: translate("apiSettings.deleteProviderTitle"),
    message: formatTranslation("apiSettings.deleteProviderMessage", {
      provider: provider.name || provider.id,
    }),
    detail: translate("apiSettings.deleteProviderDetail"),
    confirmText: translate("action.delete"),
    onConfirm: () => deleteApiProvider(),
  });
}

export function openApiSettingsModal(): void {
  closePromptPopover();
  state.apiProviderEditingId = null;
  state.apiProviderDraft = null;
  state.apiProviderDraftIsNew = false;
  if (els.apiProviderSearch) els.apiProviderSearch.value = "";
  populateApiSettingsForm();
  setApiSettingsFeedback("", "");
  openSystemSettingsModal("api");
  scrollActiveApiProviderCardIntoView(activeApiProvider().id, "center");
}

export function openGenerationProviderSettings(): void {
  openApiSettingsModal();
}

export function closeApiSettingsModal(): void {
  closeSystemSettingsModal();
}

export function selectApiProvider(providerId: any, anchor?: HTMLElement | null): void {
  const id = String(providerId || "").trim();
  if (!id) return;
  if (apiProviderEditorActive()) {
    setApiSettingsFeedback(translate("apiSettings.finishEditFirst"), "error");
    return;
  }
  if (state.apiProviderSortMode) return;
  const provider = providerById(id);
  const continueSwitch = () => {
    state.apiSettings = normalizeApiSettings({
      ...state.apiSettings,
      active_provider_id: provider.id,
    });
    populateApiSettingsForm();
    scrollActiveApiProviderCardIntoView(provider.id, "nearest");
    persistApiSettings();
    legacyMethod("selectGenerationProvider", provider.id);
    renderAuthSourceAfterProviderChange();
    queueApiSettingsAutosave();
  };
  if (provider.id === currentApiProviderId()) {
    continueSwitch();
    return;
  }
  void anchor;
  continueSwitch();
}

export function editApiProvider(): void {
  if (apiProviderEditorActive()) return;
  state.apiProviderSortMode = false;
  const provider = activeApiProvider();
  state.apiProviderEditingId = provider.id;
  state.apiProviderDraftIsNew = false;
  state.apiProviderDraft = normalizeApiProvider({ ...provider }, 0);
  populateApiSettingsForm();
  setApiSettingsFeedback(translate("apiSettings.editDraftStatus"), "running");
  scrollApiProviderEditorIntoView();
  els.apiProviderName?.focus();
}

export function cancelApiProviderEdit(): void {
  if (!apiProviderEditorActive()) return;
  els.systemSettingsApiTab?.focus({ preventScroll: true });
  state.apiProviderEditingId = null;
  state.apiProviderDraft = null;
  state.apiProviderDraftIsNew = false;
  populateApiSettingsForm();
  setApiSettingsFeedback("", "");
  scrollActiveApiProviderCardIntoView(activeApiProvider().id, "center");
}

export function toggleApiProviderSortMode(): void {
  if (apiProviderEditorActive()) {
    setApiSettingsFeedback(translate("apiSettings.finishEditFirst"), "error");
    return;
  }
  const settings = normalizeApiSettings(state.apiSettings);
  if (settings.providers.length <= 1) return;
  state.apiProviderSortMode = !state.apiProviderSortMode;
  renderApiProviderList();
  if (!state.apiProviderSortMode) scrollActiveApiProviderCardIntoView(settings.active_provider_id, "center");
  setApiSettingsFeedback(state.apiProviderSortMode ? translate("apiSettings.sortProviderModeStatus") : "", state.apiProviderSortMode ? "running" : "");
}

export function moveApiProvider(providerId: any, direction: any): void {
  if (!state.apiProviderSortMode || apiProviderEditorActive()) return;
  const settings = normalizeApiSettings(state.apiSettings);
  const index = settings.providers.findIndex((provider: any) => provider.id === providerId);
  const offset = direction === "up" ? -1 : direction === "down" ? 1 : 0;
  const nextIndex = index + offset;
  if (index < 0 || nextIndex < 0 || nextIndex >= settings.providers.length) return;
  const providers = [...settings.providers];
  [providers[index], providers[nextIndex]] = [providers[nextIndex], providers[index]];
  state.apiSettings = normalizeApiSettings({
    ...settings,
    providers,
    active_provider_id: settings.active_provider_id,
  });
  persistApiSettings();
  renderApiProviderList();
  setApiSettingsFeedback(translate("apiSettings.sortProviderStatus"), "running");
  queueApiSettingsAutosave();
}

export async function saveApiProviderEdit(): Promise<void> {
  if (!apiProviderEditorActive()) return;
  await saveApiSettings();
}

export function addProviderBinding(): void {
  if (!apiProviderEditorActive()) return;
  const draft = draftProviderFromForm();
  const models = state.generationCatalog?.models || [];
  const model = models.find((item: any) => !draft.bindings.some((binding: any) => binding.canonical_model_id === item.id))
    || models[0];
  if (!model) {
    setApiSettingsFeedback(translate("apiSettings.catalogRequiredForBinding"), "error");
    return;
  }
  const bindingId = `${draft.id}-binding-${Date.now()}`;
  const protocol = availableProtocolsForModel(model.id)[0];
  if (!protocol) {
    setApiSettingsFeedback(translate("apiSettings.catalogRequiredForBinding"), "error");
    return;
  }
  draft.bindings.push(bindingFromProtocol(
    bindingId,
    model.id,
    model.official_model_id || model.id,
    protocol,
    [...model.operations],
  ));
  if (!state.apiSettings.default_provider_by_model?.[model.id]) {
    draft.default_model_ids = [...new Set([...(draft.default_model_ids || []), model.id])];
  }
  state.apiProviderDraft = draft;
  renderProviderBindingCards(
    els.apiProviderBindings,
    draft.bindings,
    models,
    draft.id,
    defaultsForProviderDraft(draft),
  );
  updateApiRequestEndpointPreview();
}

export function removeProviderBinding(bindingId: string): void {
  if (!apiProviderEditorActive()) return;
  const draft = draftProviderFromForm();
  if (draft.bindings.length <= 1) {
    setApiSettingsFeedback(translate("apiSettings.keepOneBinding"), "error");
    return;
  }
  draft.bindings = draft.bindings.filter((binding: any) => binding.id !== bindingId);
  state.apiProviderDraft = draft;
  renderProviderBindingCards(
    els.apiProviderBindings,
    draft.bindings,
    state.generationCatalog?.models || [],
    draft.id,
    defaultsForProviderDraft(draft),
  );
  updateApiRequestEndpointPreview();
}

export function handleProviderBindingEditorChange(event: Event): void {
  const target = event.target as HTMLInputElement | HTMLSelectElement | null;
  const card = target?.closest<HTMLElement>("[data-binding-id]");
  if (!target || !card) return;
  if (target.matches("[data-binding-model]")) {
    const modelId = target.value;
    const protocols = availableProtocolsForModel(modelId);
    const defaultProtocol = protocols[0];
    const protocolSelect = card.querySelector<HTMLSelectElement>("[data-binding-protocol]");
    if (protocolSelect) {
      protocolSelect.replaceChildren(...protocols.map((protocol) => {
        const option = document.createElement("option");
        option.value = protocol;
        option.textContent = BINDING_PROTOCOL_LABELS[protocol];
        return option;
      }));
      protocolSelect.value = protocols[0] || "";
      syncThemedSelect(protocolSelect);
    }
    const compatibilitySelect = card.querySelector<HTMLSelectElement>("[data-binding-compatibility]");
    if (compatibilitySelect) {
      compatibilitySelect.replaceChildren(...(defaultProtocol
        ? availableCompatibilityLayers(modelId, defaultProtocol)
        : []).map((compatibility) => {
        const option = document.createElement("option");
        option.value = compatibility;
        option.textContent = BINDING_COMPATIBILITY_LABELS[compatibility];
        return option;
      }));
      compatibilitySelect.value = "standard";
      syncThemedSelect(compatibilitySelect);
    }
    card.dataset.bindingProtocolChanged = "true";
    card.dataset.bindingCompatibilityChanged = "true";
    if (state.apiProviderDraftIsNew && defaultProtocol) {
      const suggestion = bindingTemplateSuggestion(bindingTemplateForProtocol(modelId, defaultProtocol));
      const currentBase = String(els.apiBaseUrl?.value || "").trim();
      if (!currentBase || isBindingTemplateBaseUrl(currentBase)) els.apiBaseUrl.value = suggestion.base_url;
    }
    const remoteInput = card.querySelector<HTMLInputElement>("[data-binding-remote-model]");
    const model = state.generationCatalog?.models.find((item: any) => item.id === modelId);
    if (remoteInput && !remoteInput.value.trim()) remoteInput.value = model?.official_model_id || modelId;
    const existingOperations = String(card.dataset.bindingModelOperations || "")
      .split(",")
      .filter(Boolean);
    card.dataset.bindingModelOperations = (model?.operations || existingOperations).join(",");
  }
  if (target.matches("[data-binding-default]")) {
    const modelId = card.querySelector<HTMLSelectElement>("[data-binding-model]")?.value;
    if (modelId) {
      (els.apiProviderBindings as HTMLElement | null)?.querySelectorAll<HTMLElement>("[data-binding-id]").forEach((item) => {
        if (item === card) return;
        if (item.querySelector<HTMLSelectElement>("[data-binding-model]")?.value !== modelId) return;
        const checkbox = item.querySelector<HTMLInputElement>("[data-binding-default]");
        if (checkbox) checkbox.checked = (target as HTMLInputElement).checked;
      });
    }
  }
  if (target.matches("[data-binding-protocol]")) {
    card.dataset.bindingProtocolChanged = "true";
    const modelId = card.querySelector<HTMLSelectElement>("[data-binding-model]")?.value || "";
    const compatibilitySelect = card.querySelector<HTMLSelectElement>("[data-binding-compatibility]");
    const protocol = target.value as BindingProtocol;
    if (compatibilitySelect) {
      compatibilitySelect.replaceChildren(...availableCompatibilityLayers(modelId, protocol).map((compatibility) => {
        const option = document.createElement("option");
        option.value = compatibility;
        option.textContent = BINDING_COMPATIBILITY_LABELS[compatibility];
        return option;
      }));
      compatibilitySelect.value = "standard";
      syncThemedSelect(compatibilitySelect);
    }
    card.dataset.bindingCompatibilityChanged = "true";
    if (state.apiProviderDraftIsNew) {
      const templateId = bindingTemplateForProtocol(modelId, protocol);
      const suggestion = bindingTemplateSuggestion(templateId);
      const currentBase = String(els.apiBaseUrl?.value || "").trim();
      if (!currentBase || isBindingTemplateBaseUrl(currentBase)) els.apiBaseUrl.value = suggestion.base_url;
    }
  }
  if (target.matches("[data-binding-compatibility]")) {
    card.dataset.bindingCompatibilityChanged = "true";
    if (state.apiProviderDraftIsNew) {
      const modelId = card.querySelector<HTMLSelectElement>("[data-binding-model]")?.value || "";
      const protocol = (card.querySelector<HTMLSelectElement>("[data-binding-protocol]")?.value
        || availableProtocolsForModel(modelId)[0]) as BindingProtocol;
      const templateId = bindingTemplateForCompatibility(
        modelId,
        protocol,
        target.value as BindingCompatibility,
      );
      const suggestion = bindingTemplateSuggestion(templateId);
      const currentBase = String(els.apiBaseUrl?.value || "").trim();
      if (!currentBase || isBindingTemplateBaseUrl(currentBase)) els.apiBaseUrl.value = suggestion.base_url;
    }
  }
  updateApiRequestEndpointPreview();
}

function renderAuthSourceAfterProviderChange(): void {
  legacyMethod("renderAuthSource", state.authStatus);
  legacyMethod("renderProviderSelection");
  updateModeSpecificSettings();
  updateRequestPreview();
}

export function currentApiImageModel(): string {
  const provider = activeApiProvider();
  const binding = provider.bindings?.find((item: any) => item.canonical_model_id === state.selectedModelId)
    || provider.bindings?.find((item: any) => item.canonical_model_id === "gpt-image-2")
    || provider.bindings?.[0];
  return String(binding?.remote_model_id || provider.image_model || DEFAULT_API_IMAGE_MODEL).trim() || DEFAULT_API_IMAGE_MODEL;
}

export function currentApiMode(): string {
  const binding = selectedProviderBinding();
  if (binding) return String(binding.protocol_profile).includes("responses") ? "responses" : "images";
  return activeApiProvider().api_mode === "responses" ? "responses" : DEFAULT_API_MODE;
}

export function currentCodexMode(): string {
  const binding = selectedProviderBinding();
  if (state.selectedProviderId === "codex" && binding) {
    return binding.protocol_profile === "codex_responses" ? "responses" : "images";
  }
  state.apiSettings = normalizeApiSettings(state.apiSettings);
  return normalizeCodexMode(state.apiSettings.codex_mode);
}

export function currentApiImagesConcurrency(): number {
  const provider = activeApiProvider();
  return normalizeApiImagesConcurrency(provider.concurrency ?? provider.images_concurrency);
}

export function apiModeLabel(mode: any): string {
  return mode === "responses" ? "Responses" : translate("apiSettings.modeImagesShort");
}

export function codexModeLabel(mode: any): string {
  return mode === "responses" ? "Codex Responses" : "Codex Image";
}

function backendDisplayLabel(backend: string): string {
  if (backend === "codex_images") return "Codex Image";
  if (backend === "codex_responses") return "Codex Responses";
  if (backend === "openai_images") return "API Image";
  if (backend === "openai_responses") return "API Responses";
  return backend;
}

function backendModeLabel(backend: string): string {
  if (backend === "codex_images" || backend === "openai_images") return "Image";
  if (backend === "codex_responses" || backend === "openai_responses") return "Responses";
  return "";
}

export function syncCodexModeNotes(): void {
  // Kept as a no-op bridge for older extension hooks. Codex protocol selection now lives in the provider menu.
}

export function selectCodexMode(mode: any, anchor?: HTMLElement | null): boolean {
  const normalized = normalizeCodexMode(mode);
  void anchor;
  state.apiSettings = normalizeApiSettings({ ...state.apiSettings, codex_mode: normalized });
  legacyMethod("syncCodexCatalogMode", normalized);
  legacyMethod("selectGenerationProvider", providerBindingSelectionKey("codex", `codex-gpt-image-2-${normalized}`));
  legacyMethod("renderProviderSelection");
  updateModeSpecificSettings();
  updateRequestPreview();
  persistApiSettings();
  queueApiSettingsAutosave();
  return true;
}

export function queueApiSettingsAutosave(): void {
  if (apiProviderEditorActive()) return;
  if (apiSettingsAutosaveTimerId !== null) {
    window.clearTimeout(apiSettingsAutosaveTimerId);
  }
  setApiSettingsFeedback(translate("apiSettings.autoSaving"), "running");
  apiSettingsAutosaveTimerId = window.setTimeout(() => {
    apiSettingsAutosaveTimerId = null;
    void saveApiSettings({ auto: true });
  }, 260);
}

export function backendForAuthSource(authSource: any, apiMode: any = currentApiMode(), codexMode: any = currentCodexMode()): string {
  if (authSource === "api") {
    return apiMode === "responses" ? "openai_responses" : "openai_images";
  }
  return codexMode === "responses" ? "codex_responses" : "codex_images";
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
    || task?.provider_id
    || "",
  ).trim();
}

export function taskApiProviderLabel(task: any): string {
  const providerId = taskApiProviderId(task);
  const providerName = String(
    task?.api_provider_name
    || task?.params?.api_provider_name
    || task?.request?.webui_api_provider_name
    || task?.request?.api_provider_name
    || task?.provider
    || "",
  ).trim();
  const configuredProvider = providerId ? state.apiSettings.providers.find((provider: any) => provider.id === providerId) : null;
  const label = providerName || configuredProvider?.name || providerId;
  if (!label) return "";
  return !providerId || label === providerId ? label : `${label} (${providerId})`;
}

export function taskBackendLabel(task: any): string {
  const backend = taskBackendValue(task);
  const provider = taskApiProviderLabel(task);
  const backendLabel = backendDisplayLabel(backend);
  if (provider && backend.startsWith("openai_")) {
    return [provider, backendModeLabel(backend)].filter(Boolean).join(" · ");
  }
  return [backendLabel, provider].filter(Boolean).join(" · ");
}

export function setApiSettingsFeedback(message: any, type: any = ""): void {
  [els.apiSettingsStatus].filter(Boolean).forEach((statusElement: any) => {
    statusElement.textContent = message;
    statusElement.className = `api-settings-feedback settings-action-status ${type || ""}`.trim();
  });
}

function saveButtons(): any[] {
  return [els.saveApiProviderEditButton].filter(Boolean);
}

function setSaveButtonsDisabled(disabled: boolean): void {
  saveButtons().forEach((button) => { button.disabled = disabled; });
}

function setSaveButtonText(stateName: "saving" | "saved" | "failed" | "default"): void {
  const providerText = {
    saving: translate("apiSettings.saving"),
    saved: translate("apiSettings.savedShort"),
    failed: translate("apiSettings.saveFailedShort"),
    default: translate("apiSettings.saveProvider"),
  }[stateName];
  if (els.saveApiProviderEditButton) els.saveApiProviderEditButton.textContent = providerText;
}

export async function saveApiSettings(options: any = {}): Promise<boolean> {
  const autoSave = Boolean(options.auto);
  if (autoSave && apiProviderEditorActive()) return true;
  if (state.apiSettingsSaveTimerId) {
    window.clearTimeout(state.apiSettingsSaveTimerId);
    state.apiSettingsSaveTimerId = null;
  }
  const previousSettings = normalizeApiSettings(state.apiSettings);
  const previousEditingId = state.apiProviderEditingId;
  const previousDraft = state.apiProviderDraft ? structuredClone(state.apiProviderDraft) : null;
  const previousDraftIsNew = state.apiProviderDraftIsNew;
  if (!autoSave && apiProviderEditorActive()) {
    const bindings = readProviderBindingCards(els.apiProviderBindings);
    if (!bindings.length || bindings.some((binding) => !binding.canonical_model_id
      || !binding.remote_model_id || !binding.operations.length)) {
      setApiSettingsFeedback(translate("apiSettings.bindingRequiredFields"), "error");
      return false;
    }
    const overlap = validateProviderBindingOverlaps(bindings);
    if (overlap) {
      setApiSettingsFeedback(formatTranslation("apiSettings.bindingOverlap", {
        model: overlap.canonicalModelId,
        operation: overlap.operation,
      }), "error");
      (els.apiProviderBindings as HTMLElement | null)?.querySelector<HTMLElement>(`[data-binding-id="${CSS.escape(overlap.secondBindingId)}"]`)?.scrollIntoView?.({ block: "nearest" });
      return false;
    }
  }
  const settings = readApiSettingsForm({ applyProviderDraft: !autoSave });
  persistApiSettings();
  const payload: any = {
    schema_version: 2,
    codex_mode: settings.codex_mode,
    active_provider_id: settings.active_provider_id,
    default_provider_by_model: settings.default_provider_by_model,
    providers: settings.providers.map((provider: any) => {
      const item: any = {
        id: provider.id,
        name: provider.name,
        icon_emoji: provider.icon_emoji || "",
        base_url: provider.base_url,
        concurrency: provider.concurrency,
        bindings: provider.bindings,
      };
      if (provider.api_key || !provider.api_key_set) item.api_key = provider.api_key;
      if (!provider.api_key && provider.api_key_source_provider_id) {
        item.api_key_source_provider_id = provider.api_key_source_provider_id;
      }
      return item;
    }),
  };
  if (!autoSave) {
    setSaveButtonsDisabled(true);
    setSaveButtonText("saving");
  }
  setApiSettingsFeedback(translate(autoSave ? "apiSettings.autoSaving" : "apiSettings.savingStatus"), "running");
  try {
    const response = await fetch("/api/api-settings", {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || translate("apiSettings.saveFailed"));
    state.apiSettings = mergeApiProviderKeys(data.settings || {});
    state.apiProviderEditingId = null;
    state.apiProviderDraft = null;
    state.apiProviderDraftIsNew = false;
    persistApiSettings();
    populateApiSettingsForm();
    setApiSettingsFeedback(autoSave ? translate("apiSettings.autoSaved") : formatTranslation("apiSettings.savedSummary", {
      codex: codexModeLabel(currentCodexMode()),
      provider: activeApiProvider().name,
      mode: apiModeLabel(currentApiMode()),
      model: currentApiImageModel(),
      concurrency: currentApiImagesConcurrency(),
    }), "ok");
    if (!autoSave) setSaveButtonText("saved");
    state.apiSettingsSaveTimerId = window.setTimeout(() => {
      if (!autoSave) setSaveButtonText("default");
      state.apiSettingsSaveTimerId = null;
    }, 1600);
    setStatus(translate("apiSettings.savedStatus"), "ok");
    await refreshGenerationCatalog();
    await refreshHealth();
    updateRequestPreview();
    return true;
  } catch (error: any) {
    state.apiSettings = previousSettings;
    state.apiProviderEditingId = previousEditingId;
    state.apiProviderDraft = previousDraft;
    state.apiProviderDraftIsNew = previousDraftIsNew;
    persistApiSettings();
    populateApiSettingsForm();
    setApiSettingsFeedback(error.message || translate("apiSettings.saveFailed"), "error");
    if (!autoSave) setSaveButtonText("failed");
    setStatus(error.message || translate("apiSettings.saveFailed"), "error");
    return false;
  } finally {
    if (!autoSave) setSaveButtonsDisabled(false);
    if (!autoSave && !state.apiSettingsSaveTimerId && els.saveApiProviderEditButton?.textContent !== translate("apiSettings.saveProvider")) {
      state.apiSettingsSaveTimerId = window.setTimeout(() => {
        setSaveButtonText("default");
        state.apiSettingsSaveTimerId = null;
      }, 1600);
    }
  }
}

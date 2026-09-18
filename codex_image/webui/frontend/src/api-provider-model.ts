import type { ProviderModelBindingSettings } from "./types";

export interface ApiProviderDraft {
  id: string; name: string; base_url: string; api_key: string;
  concurrency: number; bindings: ProviderModelBindingSettings[];
  image_model: string; api_mode: string; images_concurrency: number;
  api_key_set: boolean; api_key_masked: string; api_key_source_provider_id: string;
  icon_emoji: string; default_model_ids: string[];
}

export interface ApiProviderSettings {
  schema_version: number; codex_mode: string; active_provider_id: string;
  default_provider_by_model: Record<string, string>; providers: ApiProviderDraft[];
}

import { normalizeProviderBindings } from "./provider-model-bindings";
import { DEFAULT_API_BASE_URL, DEFAULT_API_IMAGE_MODEL, DEFAULT_API_IMAGES_CONCURRENCY, DEFAULT_API_MODE, DEFAULT_CODEX_MODE } from "./state-defaults";

export function normalizeApiProvider(provider: any = {}, index: number = 0): ApiProviderDraft {
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

export function normalizeApiImagesConcurrency(value: any): number {
  const parsed = Number.parseInt(value, 10);
  if (Number.isNaN(parsed)) return DEFAULT_API_IMAGES_CONCURRENCY;
  return Math.min(32, Math.max(1, parsed));
}

export function normalizeCodexMode(value: any): string {
  return value === "responses" ? "responses" : DEFAULT_CODEX_MODE;
}

export function normalizeApiSettings(settings: any = {}): ApiProviderSettings {
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
  const providers: ApiProviderDraft[] = [];
  const seen = new Set<string>();
  rawProviders.forEach((provider: any, index: number) => {
    const normalized = normalizeApiProvider(provider, index);
    if (seen.has(normalized.id)) return;
    seen.add(normalized.id);
    providers.push(normalized);
  });
  if (!providers.length) providers.push(normalizeApiProvider({}, 0));
  const requestedActive = String(settings.active_provider_id || providers[0]!.id).trim().toLowerCase();
  const activeProvider = providers.find((provider) => provider.id === requestedActive) || providers[0]!;
  return {
    schema_version: 2,
    codex_mode: normalizeCodexMode(settings.codex_mode),
    active_provider_id: activeProvider.id,
    default_provider_by_model: { ...(settings.default_provider_by_model || { "gpt-image-2": activeProvider.id }) },
    providers,
  };
}

export function applyProviderDraft(settings: ApiProviderSettings, draft: ApiProviderDraft): ApiProviderSettings {
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
  // Every configured model needs a default, including the model a binding left.
  // Keep valid choices and prefer another supporter when this draft opted out.
  const fallbackProviders = normalized.providers.filter((provider: any) => provider.id !== draft.id).concat(draft);
  for (const provider of fallbackProviders) {
    for (const binding of provider.bindings) {
      normalized.default_provider_by_model[binding.canonical_model_id] ??= provider.id;
    }
  }
  return normalizeApiSettings(normalized);
}

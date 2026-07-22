import type { GenerationCatalog, GenerationOperation } from "./types";
import { getLegacyBridge } from "./state";
import { renderModelSelectors } from "./model-selection";
import {
  eligibleProviderBindings,
  renderProviderSelection,
  resolveProviderSelection,
} from "./provider-selection";

export const MODEL_SELECTION_STORAGE_KEY = "codex-image-model-selection-v1";

interface StoredModelSelection {
  selectedModelId?: string;
  lastModelByFamily?: Record<string, string>;
  lastProviderByModel?: Record<string, string>;
  lastProviderSelectionByModel?: Record<string, string>;
  parameterDraftsByModel?: Record<string, Record<string, unknown>>;
  parameterDraftVersionsByModel?: Record<string, number>;
}

function stringRecord(value: unknown): Record<string, string> {
  if (!value || typeof value !== "object" || Array.isArray(value)) return {};
  return Object.fromEntries(Object.entries(value).filter((entry): entry is [string, string] => (
    typeof entry[0] === "string" && typeof entry[1] === "string"
  )));
}

export function safeDraftValue(value: unknown, depth = 0): unknown {
  if (value === null || ["string", "number", "boolean"].includes(typeof value)) return value;
  if (depth >= 6) return undefined;
  if (Array.isArray(value)) return value
    .map((item) => safeDraftValue(item, depth + 1))
    .filter((item) => item !== undefined);
  if (!value || typeof value !== "object") return undefined;
  const output: Record<string, unknown> = {};
  for (const [key, item] of Object.entries(value)) {
    if (/api.?key|base.?url|remote.?model|secret|token|credential/i.test(key)) continue;
    const safe = safeDraftValue(item, depth + 1);
    if (safe !== undefined) output[key] = safe;
  }
  return output;
}

function draftRecord(value: unknown): Record<string, Record<string, unknown>> {
  const safe = safeDraftValue(value);
  return safe && typeof safe === "object" && !Array.isArray(safe)
    ? safe as Record<string, Record<string, unknown>>
    : {};
}

function positiveIntegerRecord(value: unknown): Record<string, number> {
  if (!value || typeof value !== "object" || Array.isArray(value)) return {};
  return Object.fromEntries(Object.entries(value).filter((entry): entry is [string, number] => (
    typeof entry[0] === "string" && typeof entry[1] === "number" && Number.isInteger(entry[1]) && entry[1] > 0
  )));
}

export function restoreModelSelection(): void {
  try {
    const stored = JSON.parse(localStorage.getItem(MODEL_SELECTION_STORAGE_KEY) || "{}") as StoredModelSelection;
    const { state } = getLegacyBridge();
    state.selectedModelId = typeof stored.selectedModelId === "string" ? stored.selectedModelId : null;
    state.lastModelByFamily = stringRecord(stored.lastModelByFamily);
    state.lastProviderByModel = stringRecord(stored.lastProviderByModel);
    state.lastProviderSelectionByModel = stringRecord(stored.lastProviderSelectionByModel);
    state.parameterDraftsByModel = draftRecord(stored.parameterDraftsByModel);
    state.parameterDraftVersionsByModel = positiveIntegerRecord(stored.parameterDraftVersionsByModel);
  } catch {
    localStorage.removeItem(MODEL_SELECTION_STORAGE_KEY);
  }
}

export function persistModelSelection(): void {
  const { state } = getLegacyBridge();
  const stored: StoredModelSelection = {
    ...(state.selectedModelId ? { selectedModelId: state.selectedModelId } : {}),
    lastModelByFamily: stringRecord(state.lastModelByFamily),
    lastProviderByModel: stringRecord(state.lastProviderByModel),
    lastProviderSelectionByModel: stringRecord(state.lastProviderSelectionByModel),
    parameterDraftsByModel: draftRecord(state.parameterDraftsByModel),
    parameterDraftVersionsByModel: positiveIntegerRecord(state.parameterDraftVersionsByModel),
  };
  localStorage.setItem(MODEL_SELECTION_STORAGE_KEY, JSON.stringify(stored));
}

export function isGenerationCatalog(value: unknown): value is GenerationCatalog {
  if (!value || typeof value !== "object" || Array.isArray(value)) return false;
  const candidate = value as Record<string, unknown>;
  const object = (item: unknown): item is Record<string, unknown> => Boolean(item) && typeof item === "object" && !Array.isArray(item);
  const nonempty = (item: unknown): item is string => typeof item === "string" && item.length > 0;
  const operation = (item: unknown): item is GenerationOperation => item === "generate" || item === "edit";
  const operations = (item: unknown): item is GenerationOperation[] => Array.isArray(item) && item.length > 0 && item.every(operation);
  const finiteOrNull = (item: unknown): boolean => item === null || (typeof item === "number" && Number.isFinite(item));
  const valueType = (item: unknown): boolean => ["string", "integer", "boolean", "object"].includes(String(item));
  const hasValueType = (kind: unknown, item: unknown): boolean => kind === "string" ? typeof item === "string"
    : kind === "integer" ? Number.isInteger(item) && typeof item !== "boolean"
      : kind === "boolean" ? typeof item === "boolean"
        : kind === "object" ? object(item) : false;
  const parameter = (item: unknown): boolean => {
    if (!object(item)) return false;
    const objectChoicesValid = item.object_choices === undefined || Array.isArray(item.object_choices)
      && item.object_choices.every((row) => object(row) && nonempty(row.key) && nonempty(row.label_key)
        && nonempty(row.default) && Array.isArray(row.allowed_values) && row.allowed_values.length > 0
        && row.allowed_values.every(nonempty) && row.allowed_values.includes(row.default)
        && Array.isArray(row.label_keys) && row.label_keys.length === row.allowed_values.length
        && row.label_keys.every(nonempty));
    const objectPresetsValid = item.object_presets === undefined || Array.isArray(item.object_presets)
      && item.object_presets.every((preset) => object(preset) && nonempty(preset.id)
        && nonempty(preset.label_key) && object(preset.value) && typeof preset.matches_empty === "boolean");
    return nonempty(item.id) && nonempty(item.label_key)
      && ["model", "canvas", "generation", "advanced"].includes(String(item.group))
      && ["select", "segmented", "boolean_segmented", "toggle", "slider", "number", "text", "notice", "choice_grid", "object_presets", "aspect_ratio_grid"].includes(String(item.control))
      && valueType(item.value_type) && hasValueType(item.value_type, item.default)
      && Array.isArray(item.allowed_values) && item.allowed_values.every((value) => hasValueType(item.value_type, value))
      && (item.scope === "application" || item.scope === "model")
      && finiteOrNull(item.minimum) && finiteOrNull(item.maximum) && finiteOrNull(item.step)
      && operations(item.operations) && typeof item.full_width === "boolean"
      && objectChoicesValid
      && objectPresetsValid
      && (item.control !== "boolean_segmented" || item.value_type === "boolean")
      && (item.control !== "choice_grid" || item.value_type === "object"
        && Array.isArray(item.object_choices) && item.object_choices.length > 0)
      && (item.control !== "object_presets" || item.value_type === "object"
        && Array.isArray(item.object_choices) && item.object_choices.length > 0
        && Array.isArray(item.object_presets) && item.object_presets.length > 0)
      && (item.control !== "aspect_ratio_grid" || item.value_type === "string"
        && Array.isArray(item.allowed_values) && item.allowed_values.length > 0)
      && Array.isArray(item.visible_when) && item.visible_when.every((condition) => object(condition)
        && nonempty(condition.parameter_id)
        && ["equals", "not_equals", "in"].includes(String(condition.operator))
        && (condition.operator !== "in" || Array.isArray(condition.value)));
  };
  if (candidate.schema_version !== 1 || !Number.isInteger(candidate.manifest_version) || (candidate.manifest_version as number) <= 0
      || !Array.isArray(candidate.families) || candidate.families.length === 0
      || !Array.isArray(candidate.models) || candidate.models.length === 0
      || !Array.isArray(candidate.providers) || candidate.providers.length === 0 || !object(candidate.default_provider_by_model)
      || !object(candidate.codex)) return false;
  const families = candidate.families as Record<string, unknown>[];
  if (!families.every((family) => object(family) && nonempty(family.id) && nonempty(family.display_name)
      && nonempty(family.short_name) && nonempty(family.label_key))) return false;
  const familyIds = new Set(families.map((family) => family.id as string));
  if (familyIds.size !== families.length) return false;
  const models = candidate.models as Record<string, unknown>[];
  if (!models.every((model) => object(model) && nonempty(model.id) && nonempty(model.family_id)
      && familyIds.has(model.family_id) && nonempty(model.display_name) && nonempty(model.official_model_id)
      && Number.isInteger(model.version) && (model.version as number) > 0 && operations(model.operations)
      && Array.isArray(model.parameters) && model.parameters.every(parameter)
      && new Set((model.parameters as Record<string, unknown>[]).map((item) => item.id)).size === model.parameters.length
      && (model.parameters as Record<string, unknown>[]).every((item) => (item.visible_when as Record<string, unknown>[])
        .every((condition) => (model.parameters as Record<string, unknown>[]).some((candidate) => candidate.id === condition.parameter_id)))
      && object(model.input_constraints) && Number.isInteger(model.input_constraints.max_images)
      && (model.input_constraints.max_images as number) >= 0
      && typeof model.input_constraints.supports_mask === "boolean"
      && typeof model.input_constraints.supports_reference_files === "boolean"
      && (model.expand_advanced_parameters === undefined || typeof model.expand_advanced_parameters === "boolean"))) return false;
  const modelIds = new Set(models.map((model) => model.id as string));
  if (modelIds.size !== models.length) return false;
  const providers = candidate.providers as Record<string, unknown>[];
  const bindingValid = (binding: unknown): boolean => {
    if (!object(binding) || !nonempty(binding.id) || !nonempty(binding.canonical_model_id)
        || !modelIds.has(binding.canonical_model_id) || !nonempty(binding.remote_model_id)
        || !nonempty(binding.protocol_profile) || !nonempty(binding.parameter_codec)
        || !operations(binding.operations) || (binding.available !== undefined && typeof binding.available !== "boolean")) return false;
    const model = models.find((item) => item.id === binding.canonical_model_id);
    return Boolean(model) && (binding.operations as GenerationOperation[]).every((item) => (model?.operations as GenerationOperation[]).includes(item));
  };
  if (!providers.every((provider) => object(provider) && nonempty(provider.id) && nonempty(provider.name)
      && typeof provider.builtin === "boolean" && typeof provider.available === "boolean"
      && (provider.icon_emoji === undefined || nonempty(provider.icon_emoji))
      && Array.isArray(provider.bindings) && provider.bindings.length > 0 && provider.bindings.every(bindingValid)
      && new Set((provider.bindings as Record<string, unknown>[]).map((binding) => binding.id)).size === provider.bindings.length)) return false;
  const providerIds = new Set(providers.map((provider) => provider.id as string));
  if (providerIds.size !== providers.length) return false;
  if (!Object.entries(candidate.default_provider_by_model).every(([modelId, providerId]) => modelIds.has(modelId)
      && typeof providerId === "string" && providerIds.has(providerId)
      && (providers.find((provider) => provider.id === providerId)?.bindings as Record<string, unknown>[])
        .some((binding) => binding.canonical_model_id === modelId))) return false;
  const codex = candidate.codex;
  if (typeof codex.available !== "boolean" || (codex.mode !== "images" && codex.mode !== "responses")) return false;
  const codexProvider = providers.find((provider) => provider.id === "codex");
  if (codex.available && !codexProvider) return false;
  if (codexProvider) {
    if (codexProvider.builtin !== true || codexProvider.available !== codex.available
        || (codexProvider.bindings as unknown[]).length !== 2) return false;
    const expected = new Map([
      ["codex-gpt-image-2-images", ["codex_images", "gpt_codex_images"]],
      ["codex-gpt-image-2-responses", ["codex_responses", "gpt_codex_responses"]],
    ]);
    if (!(codexProvider.bindings as unknown[]).every((binding) => object(binding)
        && binding.canonical_model_id === "gpt-image-2"
        && binding.remote_model_id === "gpt-image-2"
        && expected.get(String(binding.id))?.[0] === binding.protocol_profile
        && expected.get(String(binding.id))?.[1] === binding.parameter_codec)) return false;
  }
  return true;
}

export function initialCatalogSelection(
  catalog: GenerationCatalog,
  storedModelId: string | null | undefined,
  lastProviderByModel: Record<string, string>,
  operation: GenerationOperation,
  lastProviderSelectionByModel: Record<string, string> = {},
): { familyId: string | null; modelId: string | null; providerId: string | null; bindingId: string | null } {
  const model = catalog.models.find((item) => item.id === storedModelId)
    || catalog.models.find((item) => item.id === "gpt-image-2")
    || catalog.models[0];
  if (!model) return { familyId: null, modelId: null, providerId: null, bindingId: null };
  const entries = eligibleProviderBindings(catalog, model.id, operation);
  const selected = resolveProviderSelection(
    entries,
    lastProviderSelectionByModel[model.id],
    lastProviderByModel[model.id],
    catalog.default_provider_by_model[model.id],
    catalog.codex.mode,
  );
  return {
    familyId: model.family_id,
    modelId: model.id,
    providerId: selected?.provider.id || null,
    bindingId: selected?.binding.id || null,
  };
}

export async function refreshGenerationCatalog(): Promise<void> {
  const { state } = getLegacyBridge();
  try {
    const response = await fetch("/api/generation-catalog", { headers: { Accept: "application/json" } });
    const payload: unknown = await response.json();
    if (!response.ok || !isGenerationCatalog(payload)) throw new Error("generation catalog unavailable");
    state.generationCatalog = payload;
    state.generationCatalogError = null;
    const selection = initialCatalogSelection(
      payload,
      state.selectedModelId,
      state.lastProviderByModel,
      state.mode as GenerationOperation,
      state.lastProviderSelectionByModel,
    );
    state.selectedFamilyId = selection.familyId;
    state.selectedModelId = selection.modelId;
    state.selectedProviderId = selection.providerId;
    state.selectedProviderBindingId = selection.bindingId;
    if (selection.modelId && selection.providerId && selection.bindingId) {
      state.lastProviderByModel[selection.modelId] = selection.providerId;
      state.lastProviderSelectionByModel[selection.modelId] = `${selection.providerId}::${selection.bindingId}`;
    }
    persistModelSelection();
  } catch (error) {
    state.generationCatalog = null;
    state.generationCatalogError = error instanceof Error ? error.message : "generation catalog unavailable";
    state.selectedFamilyId = null;
    state.selectedModelId = null;
    state.selectedProviderId = null;
    state.selectedProviderBindingId = null;
  }
  renderModelSelectors();
  renderProviderSelection();
  getLegacyBridge().methods.renderCurrentModelParameters?.();
  getLegacyBridge().methods.updateModeSpecificSettings?.();
  getLegacyBridge().methods.updateRequestPreview?.();
}

export function initModelCatalogFeature(): void {
  Object.assign(getLegacyBridge().methods, {
    persistModelSelection,
    refreshGenerationCatalog,
    restoreModelSelection,
  });
}

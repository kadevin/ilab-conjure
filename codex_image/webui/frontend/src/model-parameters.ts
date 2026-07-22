import { LOCALE_CHANGE_EVENT, translate } from "./i18n";
import { aspectRatioSlots, createAspectRatioIcon } from "./aspect-ratio-controls";
import { refreshSegmentedIndicators } from "./segmented-indicator";
import { getLegacyBridge } from "./state";
import type {
  CatalogModel,
  CatalogObjectPreset,
  CatalogParameterDefinition,
  GenerationOperation,
  ParameterMigrationReport,
} from "./types";

interface RenderContext {
  readOnly: boolean;
  model: CatalogModel;
  values: Record<string, unknown>;
  root: HTMLElement;
}

type ParameterRenderer = (
  definition: CatalogParameterDefinition,
  value: unknown,
  context: RenderContext,
) => HTMLElement;

function cloneValue(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(cloneValue);
  if (value && typeof value === "object") {
    return Object.fromEntries(Object.entries(value).map(([key, item]) => [key, cloneValue(item)]));
  }
  return value;
}

function gptSizeValid(value: unknown): boolean {
  if (typeof value !== "string") return false;
  const match = value.match(/^(\d+)x(\d+)$/i);
  if (!match) return false;
  const width = Number(match[1]);
  const height = Number(match[2]);
  if (!Number.isInteger(width) || !Number.isInteger(height)) return false;
  if (width < 16 || width > 3840 || height < 16 || height > 3840) return false;
  if (width % 16 !== 0 || height % 16 !== 0) return false;
  if (Math.max(width, height) / Math.min(width, height) > 3) return false;
  const pixels = width * height;
  return pixels >= 655360 && pixels <= 8294400;
}

export function parameterValueValid(definition: CatalogParameterDefinition, value: unknown): boolean {
  if (definition.id === "canvas.size" && definition.allowed_values.length === 0) {
    return gptSizeValid(value);
  }
  const typeValid = definition.value_type === "string" ? typeof value === "string"
    : definition.value_type === "integer" ? typeof value === "number" && Number.isInteger(value)
      : definition.value_type === "boolean" ? typeof value === "boolean"
        : definition.value_type === "object" ? Boolean(value) && typeof value === "object" && !Array.isArray(value)
          : false;
  if (!typeValid) return false;
  if (definition.object_choices?.length && value && typeof value === "object" && !Array.isArray(value)) {
    const choices = new Map(definition.object_choices.map((row) => [row.key, row]));
    for (const [key, item] of Object.entries(value)) {
      const row = choices.get(key);
      if (row && (typeof item !== "string" || !row.allowed_values.includes(item))) return false;
    }
  }
  if (definition.allowed_values.length && !definition.allowed_values.includes(value)) return false;
  if (typeof value === "number") {
    if (definition.minimum !== null && value < definition.minimum) return false;
    if (definition.maximum !== null && value > definition.maximum) return false;
    if (definition.step !== null) {
      const base = definition.minimum ?? 0;
      const quotient = (value - base) / definition.step;
      if (Math.abs(quotient - Math.round(quotient)) > 1e-9) return false;
    }
  }
  return true;
}

export function nextObjectChoiceValue(
  definition: Pick<CatalogParameterDefinition, "object_choices">,
  value: Record<string, unknown>,
  key: string,
  next: string,
): Record<string, unknown> {
  const row = definition.object_choices?.find((item) => item.key === key);
  if (!row || !row.allowed_values.includes(next)) return { ...value };
  const updated = { ...value };
  if (next === row.default) delete updated[key];
  else updated[key] = next;
  return updated;
}

function managedPresetKeys(definition: Pick<CatalogParameterDefinition, "object_presets">): Set<string> {
  return new Set(definition.object_presets?.flatMap((preset) => Object.keys(preset.value)) || []);
}

export function matchingObjectPreset(
  definition: Pick<CatalogParameterDefinition, "object_presets">,
  value: Record<string, unknown>,
): CatalogObjectPreset | null {
  const presets = definition.object_presets || [];
  const managedKeys = managedPresetKeys(definition);
  const presentManagedKeys = [...managedKeys].filter((key) => key in value);
  if (presentManagedKeys.length === 0) {
    return presets.find((preset) => preset.matches_empty) || null;
  }
  return presets.find((preset) => (
    [...managedKeys].every((key) => key in value && key in preset.value && value[key] === preset.value[key])
  )) || null;
}

export function nextObjectPresetValue(
  definition: Pick<CatalogParameterDefinition, "object_presets">,
  value: Record<string, unknown>,
  preset: CatalogObjectPreset,
): Record<string, unknown> {
  if (!definition.object_presets?.some((item) => item.id === preset.id)) return { ...value };
  const updated = { ...value };
  managedPresetKeys(definition).forEach((key) => delete updated[key]);
  Object.assign(updated, cloneValue(preset.value));
  return updated;
}

function conditionMatches(
  condition: CatalogParameterDefinition["visible_when"][number],
  values: Record<string, unknown>,
): boolean {
  const actual = values[condition.parameter_id];
  if (condition.operator === "equals") return actual === condition.value;
  if (condition.operator === "not_equals") return actual !== condition.value;
  return Array.isArray(condition.value) && condition.value.includes(actual);
}

export function initializeParameterDraft(
  model: CatalogModel,
  previous: Record<string, unknown> = {},
): ParameterMigrationReport {
  const values: Record<string, unknown> = {};
  const defaulted: ParameterMigrationReport["defaulted"] = [];
  const definitions = new Map(model.parameters.map((definition) => [definition.id, definition]));
  for (const definition of model.parameters) {
    if (!(definition.id in previous)) {
      values[definition.id] = cloneValue(definition.default);
      continue;
    }
    const prior = previous[definition.id];
    if (parameterValueValid(definition, prior)) {
      values[definition.id] = cloneValue(prior);
    } else {
      const replacement = cloneValue(definition.default);
      values[definition.id] = replacement;
      defaulted.push({ id: definition.id, previous: cloneValue(prior), replacement: cloneValue(replacement) });
    }
  }
  const dropped = Object.entries(previous)
    .filter(([id]) => !definitions.has(id))
    .map(([id, prior]) => ({ id, previous: cloneValue(prior) }));
  return { values, defaulted, dropped };
}

export function migrateParameterValues(
  model: CatalogModel,
  previous: Record<string, unknown>,
): ParameterMigrationReport {
  return initializeParameterDraft(model, previous);
}

export function parameterAffectsVisibility(model: CatalogModel, parameterId: string): boolean {
  return model.parameters.some((definition) => definition.visible_when.some(
    (condition) => condition.parameter_id === parameterId,
  ));
}

export function activeParameterValuesFor(
  model: CatalogModel,
  operation: GenerationOperation,
  draft: Record<string, unknown>,
): Record<string, unknown> {
  const values = Object.fromEntries(model.parameters.map((definition) => {
    const value = draft[definition.id];
    return [definition.id, cloneValue(parameterValueValid(definition, value) ? value : definition.default)];
  }));
  return Object.fromEntries(model.parameters
    .filter((definition) => definition.operations.includes(operation))
    .filter((definition) => definition.control !== "notice")
    .filter((definition) => definition.visible_when.every((condition) => conditionMatches(condition, values)))
    .map((definition) => [definition.id, cloneValue(values[definition.id])]));
}

export function activeParameterValues(model: CatalogModel): Record<string, unknown> {
  const { state } = getLegacyBridge();
  return activeParameterValuesFor(
    model,
    state.mode as GenerationOperation,
    state.parameterDraftsByModel[model.id] || {},
  );
}

function fieldShell(definition: CatalogParameterDefinition): HTMLDivElement {
  const field = document.createElement("div");
  field.className = `field model-parameter-field${definition.full_width ? " full-width" : ""}`;
  field.dataset.parameterId = definition.id;
  const label = document.createElement("span");
  label.className = "model-parameter-label";
  label.textContent = translate(definition.label_key);
  field.append(label);
  return field;
}

function setReadOnly(control: HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement, readOnly: boolean): void {
  if (!readOnly) return;
  control.disabled = true;
  control.tabIndex = -1;
  control.setAttribute("aria-readonly", "true");
}

function interactiveModel(context: RenderContext): CatalogModel {
  if (context.readOnly) return context.model;
  const { state } = getLegacyBridge();
  return state.generationCatalog?.models.find((model) => model.id === state.selectedModelId) || context.model;
}

function commitValue(context: RenderContext, definition: CatalogParameterDefinition, value: unknown, rerender = false): void {
  if (context.readOnly) return;
  const model = interactiveModel(context);
  const currentDefinition = model.parameters.find((item) => item.id === definition.id);
  if (!currentDefinition) return;
  setParameterValue(model.id, currentDefinition.id, value);
  if (rerender) renderModelParameters(model, { readOnly: false });
}

function renderSelect(
  definition: CatalogParameterDefinition,
  value: unknown,
  context: RenderContext,
): HTMLElement {
  const field = fieldShell(definition);
  const select = document.createElement("select");
  select.className = "control";
  select.setAttribute("aria-label", translate(definition.label_key));
  definition.allowed_values.forEach((allowed) => {
    const option = document.createElement("option");
    option.value = String(allowed);
    option.textContent = String(allowed);
    select.append(option);
  });
  select.value = String(value);
  setReadOnly(select, context.readOnly);
  select.addEventListener("change", () => commitValue(
    context,
    definition,
    select.value,
    parameterAffectsVisibility(interactiveModel(context), definition.id),
  ));
  field.append(select);
  return field;
}

function renderSegmented(
  definition: CatalogParameterDefinition,
  value: unknown,
  context: RenderContext,
): HTMLElement {
  const field = fieldShell(definition);
  if (definition.allowed_values.length === 1) {
    const staticValue = document.createElement("div");
    staticValue.className = "control model-parameter-static-value";
    staticValue.textContent = String(definition.allowed_values[0]);
    staticValue.setAttribute("aria-label", translate(definition.label_key));
    field.append(staticValue);
    return field;
  }
  const group = document.createElement("div");
  const multiline = definition.allowed_values.length > 4;
  group.className = `radio-group model-parameter-segmented${multiline ? " model-parameter-segmented-multiline" : ""}`;
  group.setAttribute("role", "group");
  group.setAttribute("aria-label", translate(definition.label_key));
  definition.allowed_values.forEach((allowed) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = `radio-btn${allowed === value ? " active" : ""}`;
    button.textContent = String(allowed);
    button.disabled = context.readOnly;
    button.tabIndex = context.readOnly ? -1 : 0;
    button.setAttribute("aria-pressed", allowed === value ? "true" : "false");
    button.addEventListener("click", () => {
      if (context.readOnly || button.classList.contains("active")) return;
      group.querySelectorAll<HTMLButtonElement>(".radio-btn").forEach((item) => {
        const active = item === button;
        item.classList.toggle("active", active);
        item.setAttribute("aria-pressed", active ? "true" : "false");
      });
      commitValue(
        context,
        definition,
        allowed,
        parameterAffectsVisibility(interactiveModel(context), definition.id),
      );
      refreshSegmentedIndicators();
    });
    group.append(button);
  });
  field.append(group);
  return field;
}

function renderBooleanSegmented(
  definition: CatalogParameterDefinition,
  value: unknown,
  context: RenderContext,
): HTMLElement {
  const field = fieldShell(definition);
  const group = document.createElement("div");
  group.className = "radio-group model-parameter-segmented model-parameter-boolean-segmented";
  group.setAttribute("role", "group");
  group.setAttribute("aria-label", translate(definition.label_key));
  const choices = [
    { value: false, label: translate("output.lock.disabled") },
    { value: true, label: translate("output.lock.enabled") },
  ];
  choices.forEach((choice) => {
    const button = document.createElement("button");
    const active = choice.value === Boolean(value);
    button.type = "button";
    button.className = `radio-btn${active ? " active" : ""}`;
    button.textContent = choice.label;
    button.disabled = context.readOnly;
    button.tabIndex = context.readOnly ? -1 : 0;
    button.setAttribute("aria-pressed", active ? "true" : "false");
    button.addEventListener("click", () => {
      if (context.readOnly || button.classList.contains("active")) return;
      group.querySelectorAll<HTMLButtonElement>(".radio-btn").forEach((item) => {
        const isActive = item === button;
        item.classList.toggle("active", isActive);
        item.setAttribute("aria-pressed", isActive ? "true" : "false");
      });
      commitValue(
        context,
        definition,
        choice.value,
        parameterAffectsVisibility(interactiveModel(context), definition.id),
      );
      refreshSegmentedIndicators();
    });
    group.append(button);
  });
  field.append(group);
  return field;
}

function renderToggle(
  definition: CatalogParameterDefinition,
  value: unknown,
  context: RenderContext,
): HTMLElement {
  const field = fieldShell(definition);
  const label = document.createElement("label");
  label.className = "web-search-toggle model-parameter-toggle";
  const input = document.createElement("input");
  input.type = "checkbox";
  input.checked = Boolean(value);
  input.setAttribute("aria-label", translate(definition.label_key));
  setReadOnly(input, context.readOnly);
  const track = document.createElement("span");
  track.className = "web-search-toggle-track";
  track.setAttribute("aria-hidden", "true");
  const text = document.createElement("span");
  text.className = "web-search-toggle-text";
  text.textContent = translate(input.checked ? "output.lock.enabled" : "output.lock.disabled");
  input.addEventListener("change", () => {
    text.textContent = translate(input.checked ? "output.lock.enabled" : "output.lock.disabled");
    commitValue(
      context,
      definition,
      input.checked,
      parameterAffectsVisibility(interactiveModel(context), definition.id),
    );
  });
  label.append(input, track, text);
  field.append(label);
  return field;
}

function renderNumeric(
  definition: CatalogParameterDefinition,
  value: unknown,
  context: RenderContext,
  slider: boolean,
): HTMLElement {
  const field = fieldShell(definition);
  const input = document.createElement("input");
  input.className = slider ? "slider" : "control";
  input.type = slider ? "range" : "number";
  input.value = String(value);
  input.setAttribute("aria-label", translate(definition.label_key));
  if (definition.minimum !== null) input.min = String(definition.minimum);
  if (definition.maximum !== null) input.max = String(definition.maximum);
  if (definition.step !== null) input.step = String(definition.step);
  setReadOnly(input, context.readOnly);
  const output = document.createElement("output");
  output.className = "model-parameter-number-value";
  output.textContent = String(value);
  const error = document.createElement("span");
  error.className = "model-parameter-error hidden";
  error.setAttribute("role", "alert");
  input.addEventListener("input", () => {
    const next = Number(input.value);
    output.textContent = input.value;
    const message = parameterValueValid(definition, next) ? "" : translate("modelParameters.invalidValue");
    error.textContent = message;
    error.classList.toggle("hidden", !message);
    setValidationError(interactiveModel(context).id, definition.id, message);
    if (!message) commitValue(context, definition, next);
  });
  if (slider) field.append(input, output, error);
  else field.append(input, error);
  return field;
}

function renderSlider(definition: CatalogParameterDefinition, value: unknown, context: RenderContext): HTMLElement {
  return renderNumeric(definition, value, context, true);
}

function renderNumber(definition: CatalogParameterDefinition, value: unknown, context: RenderContext): HTMLElement {
  return renderNumeric(definition, value, context, false);
}

function setValidationError(modelId: string, parameterId: string, message: string): void {
  const { state, els } = getLegacyBridge();
  const errors = state.parameterValidationErrorsByModel[modelId] || {};
  if (message) errors[parameterId] = message;
  else delete errors[parameterId];
  state.parameterValidationErrorsByModel[modelId] = errors;
  if (els.runButton) els.runButton.disabled = !state.authAvailable || Object.keys(errors).length > 0;
}

function renderText(
  definition: CatalogParameterDefinition,
  value: unknown,
  context: RenderContext,
): HTMLElement {
  const field = fieldShell(definition);
  const input = definition.value_type === "object" ? document.createElement("textarea") : document.createElement("input");
  input.className = "control model-parameter-text";
  input.setAttribute("aria-label", translate(definition.label_key));
  if (input instanceof HTMLTextAreaElement) {
    input.rows = 4;
    input.value = JSON.stringify(value, null, 2);
  } else {
    input.type = "text";
    input.value = String(value);
  }
  setReadOnly(input, context.readOnly);
  const error = document.createElement("span");
  error.className = "model-parameter-error hidden";
  error.setAttribute("role", "alert");
  const handle = () => {
    if (context.readOnly) return;
    if (definition.value_type !== "object") {
      const message = parameterValueValid(definition, input.value) ? "" : translate("modelParameters.invalidValue");
      error.textContent = message;
      error.classList.toggle("hidden", !message);
      setValidationError(interactiveModel(context).id, definition.id, message);
      if (!message) commitValue(context, definition, input.value);
      return;
    }
    let parsed: unknown;
    let message = "";
    try {
      parsed = JSON.parse(input.value);
      if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) message = translate("modelParameters.objectRequired");
    } catch {
      message = translate("modelParameters.invalidJson");
    }
    error.textContent = message;
    error.classList.toggle("hidden", !message);
    setValidationError(interactiveModel(context).id, definition.id, message);
    if (!message) commitValue(context, definition, parsed);
  };
  input.addEventListener("input", handle);
  input.addEventListener("blur", handle);
  field.append(input, error);
  return field;
}

function renderNotice(
  definition: CatalogParameterDefinition,
  value: unknown,
  _context: RenderContext,
): HTMLElement {
  const notice = document.createElement("p");
  notice.className = `model-parameter-notice${definition.full_width ? " full-width" : ""}`;
  notice.dataset.parameterId = definition.id;
  notice.textContent = String(value || translate(definition.label_key));
  return notice;
}

function renderChoiceGrid(
  definition: CatalogParameterDefinition,
  value: unknown,
  context: RenderContext,
): HTMLElement {
  const field = fieldShell(definition);
  field.classList.add("model-parameter-choice-grid");
  const current = value && typeof value === "object" && !Array.isArray(value)
    ? value as Record<string, unknown>
    : {};
  definition.object_choices?.forEach((row) => {
    const choiceRow = document.createElement("div");
    choiceRow.className = "model-parameter-choice-row";
    const label = document.createElement("span");
    label.className = "model-parameter-choice-label";
    label.textContent = translate(row.label_key);
    const group = document.createElement("div");
    group.className = "radio-group model-parameter-choice-options model-parameter-segmented-multiline";
    group.setAttribute("role", "group");
    group.setAttribute("aria-label", translate(row.label_key));
    const selected = typeof current[row.key] === "string" ? String(current[row.key]) : row.default;
    row.allowed_values.forEach((allowed, index) => {
      const button = document.createElement("button");
      const active = selected === allowed;
      button.type = "button";
      button.className = `radio-btn${active ? " active" : ""}`;
      button.textContent = translate(row.label_keys[index] || row.label_key);
      button.title = allowed;
      button.disabled = context.readOnly;
      button.tabIndex = context.readOnly ? -1 : 0;
      button.setAttribute("aria-pressed", active ? "true" : "false");
      button.addEventListener("click", () => {
        if (context.readOnly || button.classList.contains("active")) return;
        group.querySelectorAll<HTMLButtonElement>(".radio-btn").forEach((item) => {
          const isActive = item === button;
          item.classList.toggle("active", isActive);
          item.setAttribute("aria-pressed", isActive ? "true" : "false");
        });
        const nextValue = nextObjectChoiceValue(definition, current, row.key, allowed);
        Object.keys(current).forEach((key) => delete current[key]);
        Object.assign(current, nextValue);
        commitValue(context, definition, nextValue);
      });
      group.append(button);
    });
    choiceRow.append(label, group);
    field.append(choiceRow);
  });
  return field;
}

function renderObjectPresets(
  definition: CatalogParameterDefinition,
  value: unknown,
  context: RenderContext,
): HTMLElement {
  const field = fieldShell(definition);
  const group = document.createElement("div");
  group.className = "radio-group model-parameter-object-presets";
  group.setAttribute("role", "group");
  group.setAttribute("aria-label", translate(definition.label_key));
  let current = value && typeof value === "object" && !Array.isArray(value)
    ? { ...value as Record<string, unknown> }
    : {};
  const selected = matchingObjectPreset(definition, current);
  definition.object_presets?.forEach((preset) => {
    const button = document.createElement("button");
    const active = selected?.id === preset.id;
    button.type = "button";
    button.className = `radio-btn${active ? " active" : ""}`;
    button.textContent = translate(preset.label_key);
    button.disabled = context.readOnly;
    button.tabIndex = context.readOnly ? -1 : 0;
    button.setAttribute("aria-pressed", active ? "true" : "false");
    button.addEventListener("click", () => {
      if (context.readOnly || button.classList.contains("active")) return;
      group.querySelectorAll<HTMLButtonElement>(".radio-btn").forEach((item) => {
        const isActive = item === button;
        item.classList.toggle("active", isActive);
        item.setAttribute("aria-pressed", isActive ? "true" : "false");
      });
      current = nextObjectPresetValue(definition, current, preset);
      commitValue(context, definition, current);
      refreshSegmentedIndicators();
    });
    group.append(button);
  });
  field.append(group);
  return field;
}

function renderAspectRatioGrid(
  definition: CatalogParameterDefinition,
  value: unknown,
  context: RenderContext,
): HTMLElement {
  const field = fieldShell(definition);
  const group = document.createElement("div");
  group.className = "radio-group model-aspect-ratio-grid";
  group.setAttribute("role", "group");
  group.setAttribute("aria-label", translate(definition.label_key));
  aspectRatioSlots(definition.allowed_values.map(String)).forEach((ratioSlot) => {
    const slot = document.createElement("div");
    slot.className = "aspect-ratio-slot";
    ratioSlot.values.forEach((allowed) => {
      const button = document.createElement("button");
      const active = allowed === value;
      button.type = "button";
      button.className = `radio-btn${active ? " active" : ""}`;
      button.dataset.val = allowed;
      button.disabled = context.readOnly;
      button.tabIndex = context.readOnly ? -1 : 0;
      button.setAttribute("aria-pressed", active ? "true" : "false");
      const icon = createAspectRatioIcon(allowed);
      const label = document.createElement("span");
      label.className = "aspect-ratio-label";
      label.textContent = allowed;
      if (icon) button.append(icon, label);
      else {
        button.classList.add("aspect-ratio-no-icon");
        button.append(label);
      }
      button.addEventListener("click", () => {
        if (context.readOnly || button.classList.contains("active")) return;
        group.querySelectorAll<HTMLButtonElement>(".radio-btn").forEach((item) => {
          const isActive = item === button;
          item.classList.toggle("active", isActive);
          item.setAttribute("aria-pressed", isActive ? "true" : "false");
        });
        commitValue(context, definition, allowed);
      });
      slot.append(button);
    });
    group.append(slot);
  });
  field.append(group);
  return field;
}

export const PARAMETER_RENDERERS: Record<CatalogParameterDefinition["control"], ParameterRenderer> = {
  select: renderSelect,
  segmented: renderSegmented,
  boolean_segmented: renderBooleanSegmented,
  toggle: renderToggle,
  slider: renderSlider,
  number: renderNumber,
  text: renderText,
  notice: renderNotice,
  choice_grid: renderChoiceGrid,
  object_presets: renderObjectPresets,
  aspect_ratio_grid: renderAspectRatioGrid,
};

export function advancedParametersAreExpanded(model: CatalogModel, readOnly: boolean): boolean {
  return readOnly || model.expand_advanced_parameters === true;
}

export function legacyParameterVisibility(modelId: string, sizeMode: unknown): {
  legacyGpt: boolean;
  customSize: boolean;
} {
  const legacyGpt = modelId === "gpt-image-2";
  return {
    legacyGpt,
    customSize: legacyGpt && sizeMode === "custom",
  };
}

function parameterTranslations(definition: CatalogParameterDefinition): string[] {
  return [
    translate(definition.label_key),
    ...(definition.object_choices || []).flatMap((choice) => [
      translate(choice.label_key),
      ...choice.label_keys.map((key) => translate(key)),
    ]),
    ...(definition.object_presets || []).map((preset) => translate(preset.label_key)),
  ];
}

export function parameterRenderFingerprint(
  definition: CatalogParameterDefinition,
  value: unknown,
  readOnly: boolean,
): string {
  return JSON.stringify([definition, value, readOnly, parameterTranslations(definition)]);
}

function resolvedParameterValues(
  model: CatalogModel,
  values: Record<string, unknown>,
): Record<string, unknown> {
  return Object.fromEntries(model.parameters.map((definition) => [
    definition.id,
    parameterValueValid(definition, values[definition.id]) ? values[definition.id] : cloneValue(definition.default),
  ]));
}

function visibleParameterDefinitions(
  model: CatalogModel,
  values: Record<string, unknown>,
  operation: GenerationOperation,
): CatalogParameterDefinition[] {
  return model.parameters
    .filter((definition) => definition.operations.includes(operation))
    .filter((definition) => definition.visible_when.every((condition) => conditionMatches(condition, values)));
}

export function renderParameterDefinitionsInto(
  root: HTMLElement,
  model: CatalogModel,
  values: Record<string, unknown>,
  options: { readOnly: boolean; operation?: GenerationOperation },
): void {
  const operation = options.operation || "generate";
  const resolvedValues = resolvedParameterValues(model, values);
  root.replaceChildren();
  const context: RenderContext = { readOnly: options.readOnly, model, values: resolvedValues, root };
  const visibleDefinitions = visibleParameterDefinitions(model, resolvedValues, operation);
  visibleDefinitions
    .filter((definition) => definition.group !== "advanced")
    .forEach((definition) => root.append(PARAMETER_RENDERERS[definition.control](definition, resolvedValues[definition.id], context)));
  const advancedDefinitions = visibleDefinitions.filter((definition) => definition.group === "advanced");
  if (advancedDefinitions.length) {
    const content = document.createElement("div");
    content.className = "model-parameter-advanced-grid";
    advancedDefinitions.forEach((definition) => content.append(
      PARAMETER_RENDERERS[definition.control](definition, resolvedValues[definition.id], context),
    ));
    if (advancedParametersAreExpanded(model, options.readOnly)) {
      content.classList.add("model-parameter-advanced-grid-expanded", "full-width");
      root.append(content);
    } else {
      const details = document.createElement("details");
      details.className = "model-parameter-advanced full-width";
      const summary = document.createElement("summary");
      summary.textContent = translate("apiSettings.advancedSettings");
      details.append(summary, content);
      root.append(details);
    }
  }
  refreshSegmentedIndicators();
}

export function renderInteractiveParameterDefinitionsInto(
  root: HTMLElement,
  model: CatalogModel,
  values: Record<string, unknown>,
  operation: GenerationOperation,
): void {
  const resolvedValues = resolvedParameterValues(model, values);
  const visibleDefinitions = visibleParameterDefinitions(model, resolvedValues, operation);
  if (visibleDefinitions.some((definition) => definition.group === "advanced")) {
    renderParameterDefinitionsInto(root, model, values, { readOnly: false, operation });
    return;
  }
  const context: RenderContext = { readOnly: false, model, values: resolvedValues, root };
  const existingFields = new Map(Array.from(root.children).flatMap((child) => {
    const parameterId = (child as HTMLElement).dataset.parameterId;
    return parameterId ? [[parameterId, child as HTMLElement]] : [];
  }));
  const fields = visibleDefinitions.map((definition) => {
    const fingerprint = parameterRenderFingerprint(definition, resolvedValues[definition.id], false);
    const existingField = existingFields.get(definition.id);
    if (existingField?.dataset.renderFingerprint === fingerprint) return existingField;
    const field = PARAMETER_RENDERERS[definition.control](definition, resolvedValues[definition.id], context);
    field.dataset.renderFingerprint = fingerprint;
    return field;
  });
  root.replaceChildren(...fields);
  refreshSegmentedIndicators();
}

function ensureModelDraft(model: CatalogModel): ParameterMigrationReport {
  const { state } = getLegacyBridge();
  const previous = state.parameterDraftsByModel[model.id] || {};
  const report = initializeParameterDraft(model, previous);
  state.parameterDraftsByModel[model.id] = report.values;
  state.parameterDraftVersionsByModel[model.id] = model.version;
  return report;
}

export function renderModelParameters(
  model: CatalogModel,
  options: { readOnly: boolean; root?: HTMLElement; values?: Record<string, unknown> } = { readOnly: false },
): void {
  const { state, els } = getLegacyBridge();
  const root = options.root || els.modelParameterGrid as HTMLElement | null;
  if (!root) return;
  if (options.readOnly) {
    renderParameterDefinitionsInto(root, model, options.values || {}, { readOnly: true, operation: state.mode as GenerationOperation });
    return;
  }
  ensureModelDraft(model);
  const visibility = legacyParameterVisibility(model.id, els.size?.value);
  const legacyGpt = visibility.legacyGpt;
  state.customSizeTransitionSeq += 1;
  state.customSizeMode = visibility.customSize;
  const legacyElements = [
    els.sizeModeGroup?.closest(".custom-size-control"),
    els.orientation?.closest(".orientation-field"),
    els.resolution?.closest(".resolution-field"),
    els.ratio?.closest(".ratio-field"),
    els.quality?.closest(".quantity-quality-row"),
    els.pixelPreview,
    els.outputFormatField,
    els.moderation?.closest(".moderation-field"),
  ].filter(Boolean) as HTMLElement[];
  legacyElements.forEach((element) => {
    element.classList.toggle("hidden", !legacyGpt);
  });
  if (els.customSize) {
    els.customSize.classList.toggle("hidden", !visibility.customSize);
    els.customSize.classList.toggle("custom-size-collapsed", !visibility.customSize);
    els.customSize.setAttribute("aria-hidden", visibility.customSize ? "false" : "true");
  }
  els.settingsGrid?.classList.toggle("custom-size-mode", visibility.customSize);
  els.webSearchField?.classList.toggle("hidden", !legacyGpt);
  root.classList.toggle("hidden", legacyGpt);
  if (legacyGpt) root.replaceChildren();
  else renderInteractiveParameterDefinitionsInto(
    root,
    model,
    state.parameterDraftsByModel[model.id] || {},
    state.mode as GenerationOperation,
  );
}

export function setParameterValue(modelId: string, parameterId: string, value: unknown): void {
  const { state } = getLegacyBridge();
  const model = state.generationCatalog?.models.find((item) => item.id === modelId);
  const definition = model?.parameters.find((item) => item.id === parameterId);
  if (!model || !definition || !parameterValueValid(definition, value)) return;
  state.parameterDraftsByModel[modelId] = {
    ...(state.parameterDraftsByModel[modelId] || {}),
    [parameterId]: cloneValue(value),
  };
  if (definition.scope === "application") {
    state.generationCatalog?.models.forEach((item) => {
      if (item.parameters.some((parameter) => parameter.id === parameterId)) {
        state.parameterDraftsByModel[item.id] = {
          ...(state.parameterDraftsByModel[item.id] || {}),
          [parameterId]: cloneValue(value),
        };
      }
    });
  }
  getLegacyBridge().methods.persistModelSelection?.();
  getLegacyBridge().methods.updateRequestPreview?.();
}

export function renderCurrentModelParameters(): void {
  const { state } = getLegacyBridge();
  const model = state.generationCatalog?.models.find((item) => item.id === state.selectedModelId);
  if (model) renderModelParameters(model, { readOnly: false });
}

export function initModelParametersFeature(): void {
  Object.assign(getLegacyBridge().methods, {
    activeParameterValues,
    renderCurrentModelParameters,
    renderModelParameters,
    setParameterValue,
  });
  document.addEventListener(LOCALE_CHANGE_EVENT, renderCurrentModelParameters);
}

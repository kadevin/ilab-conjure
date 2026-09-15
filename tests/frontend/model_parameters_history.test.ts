import assert from "node:assert/strict";
import test from "node:test";

import type { CatalogModel, GenerationCatalog } from "../../codex_image/webui/frontend/src/types";
import {
  activeParameterValuesFor,
  advancedParametersAreExpanded,
  initializeParameterDraft,
  legacyParameterVisibility,
  matchingObjectPreset,
  migrateParameterValues,
  nextObjectChoiceValue,
  nextObjectPresetValue,
  parameterAffectsVisibility,
  parameterRenderFingerprint,
} from "../../codex_image/webui/frontend/src/model-parameters";
import {
  aspectRatioRect,
  aspectRatioSlots,
} from "../../codex_image/webui/frontend/src/aspect-ratio-controls";
import {
  adoptTaskParameters,
  inspectTaskParameters,
  legacyGenerationSnapshot,
  notifyParameterMigration,
  reconcileTaskParameterInspection,
  taskParameterInspectionAction,
  taskParameterInspectionMatchesSelectedModel,
  taskParameterInspectorModel,
  taskParameterInspectorTitle,
  taskParameterInspectorParameters,
} from "../../codex_image/webui/frontend/src/task-parameter-inspector";
import { appendCanonicalGenerationFields, currentGenerationSelection } from "../../codex_image/webui/frontend/src/generation-request";
import { translate } from "../../codex_image/webui/frontend/src/i18n";

const parameters: CatalogModel["parameters"] = [
  { id: "canvas.resolution", label_key: "canvas.resolution", group: "canvas", control: "segmented", value_type: "string", default: "1K", allowed_values: ["1K", "2K"], scope: "model", minimum: null, maximum: null, step: null, visible_when: [], operations: ["generate"], full_width: false },
  { id: "feature.enabled", label_key: "feature.enabled", group: "advanced", control: "toggle", value_type: "boolean", default: false, allowed_values: [], scope: "model", minimum: null, maximum: null, step: null, visible_when: [], operations: ["generate"], full_width: false },
  { id: "feature.payload", label_key: "feature.payload", group: "advanced", control: "text", value_type: "object", default: {}, allowed_values: [], scope: "model", minimum: null, maximum: null, step: null, visible_when: [{ parameter_id: "feature.enabled", operator: "equals", value: true }], operations: ["generate"], full_width: true },
  { id: "output.count", label_key: "output.quantity", group: "generation", control: "number", value_type: "integer", default: 1, allowed_values: [], scope: "application", minimum: 1, maximum: 4, step: 1, visible_when: [], operations: ["generate"], full_width: false },
];

const model: CatalogModel = {
  id: "model-a",
  family_id: "family-a",
  display_name: "Model A",
  official_model_id: "model-a",
  version: 2,
  operations: ["generate"],
  parameters,
  input_constraints: { max_images: 0, supports_mask: false, supports_reference_files: false },
};

const catalog: GenerationCatalog = {
  schema_version: 1,
  manifest_version: 1,
  families: [{ id: "family-a", display_name: "Family A", short_name: "A", label_key: "family.a" }],
  models: [model],
  providers: [{
    id: "provider-a",
    name: "Provider A",
    builtin: false,
    available: true,
    bindings: [{ id: "binding-a", canonical_model_id: "model-a", remote_model_id: "relay/model-a", protocol_profile: "openai_images", parameter_codec: "test", operations: ["generate"] }],
  }],
  default_provider_by_model: { "model-a": "provider-a" },
  codex: { available: false, mode: "images" },
};

function installBridge() {
  const state: any = {
    generationCatalog: catalog,
    selectedFamilyId: "family-a",
    selectedModelId: "model-a",
    selectedProviderId: "provider-a",
    parameterDraftsByModel: { "model-a": { "canvas.resolution": "2K", "feature.enabled": false, "feature.payload": { keep: true }, "output.count": 3 } },
    lastModelByFamily: {},
    lastProviderByModel: {},
    mode: "generate",
    inspectedGenerationSnapshot: null,
  };
  const previousWindow = (globalThis as any).window;
  (globalThis as any).window = { __codexImageWebUI: { state, els: {}, methods: { renderTaskParameterInspector() {} } } };
  return { state, restore: () => { (globalThis as any).window = previousWindow; } };
}

const gptVersions = ["gpt-image-2", "gpt-image-2.5-flare", "gpt-image-2.5-sunburst"];

function installGptAdoptionBridge(selectedModelId: string) {
  const previous = { window: globalThis.window, document: globalThis.document };
  const gptParameters: CatalogModel["parameters"] = [
    { ...parameters[0], id: "canvas.size", default: "1024x1024", allowed_values: [] },
    { ...parameters[0], id: "gpt.quality", default: "auto", allowed_values: ["auto", "low", "medium", "high"] },
    { ...parameters[0], id: "gpt.background", default: "auto", allowed_values: ["auto", "opaque", "transparent"] },
    { ...parameters[0], id: "output.format", default: "png", allowed_values: ["png", "jpeg", "webp"] },
    { ...parameters[0], id: "gpt.moderation", default: "auto", allowed_values: ["auto", "low"] },
    parameters[3],
  ];
  const gptCatalog: GenerationCatalog = {
    ...catalog,
    families: [...catalog.families, { id: "gpt-image", display_name: "GPT", short_name: "GPT", label_key: "gpt" }],
    models: [model, ...gptVersions.map(id => ({ ...model, id, family_id: "gpt-image", parameters: gptParameters }))],
    providers: [...catalog.providers, ...gptVersions.map((id, index) => ({
      id: `gpt-${index}`, name: `GPT provider ${index}`, available: true, builtin: false,
      bindings: ["images", "responses"].map(protocol => ({
        id: `gpt-${index}-${protocol}`, canonical_model_id: id, remote_model_id: `vendor/${id}`,
        protocol_profile: `openai_${protocol}`, parameter_codec: `gpt_openai_${protocol}`, operations: ["generate" as const],
      })),
    }))],
    default_provider_by_model: { ...catalog.default_provider_by_model, ...Object.fromEntries(gptVersions.map((id, index) => [id, `gpt-${index}`])) },
  };
  const index = gptVersions.indexOf(selectedModelId);
  const providerId = index < 0 ? "provider-a" : `gpt-${index}`;
  const bindingId = index < 0 ? "binding-a" : `gpt-${index}-responses`;
  const state: any = {
    generationCatalog: gptCatalog, selectedModelId, selectedFamilyId: index < 0 ? "family-a" : "gpt-image",
    selectedProviderId: providerId, selectedProviderBindingId: bindingId, mode: "generate",
    lastModelByFamily: {}, lastProviderByModel: { [selectedModelId]: providerId },
    lastProviderSelectionByModel: { [selectedModelId]: `${providerId}::${bindingId}` },
    parameterDraftsByModel: {}, parameterDraftVersionsByModel: {},
  };
  const els: any = Object.fromEntries(Object.entries({
    size: "1024x1024", quality: "auto", background: "auto", outputFormat: "png", moderation: "auto", nInput: "1",
  }).map(([id, value]) => [id, {
    value, selectedValue: value,
    dispatchEvent() { this.selectedValue = this.value; },
  }]));
  let preview: ReturnType<typeof currentGenerationSelection> | null = null;
  const methods = {
    currentTaskParams: () => ({ size: els.size.value, quality: els.quality.value, background: els.background.value,
      output_format: els.outputFormat.value, moderation: els.moderation.value, n: Number(els.nInput.value) }),
    syncSizeControlsFromSize: (size: string) => { els.size.value = size; },
    syncRadioButtons: (...inputs: any[]) => inputs.filter(Boolean).forEach(input => input.dispatchEvent(new Event("change"))),
    persistModelSelection() {},
    updateRequestPreview() { preview = currentGenerationSelection(); },
  };
  (globalThis as any).window = { __codexImageWebUI: { state, els, methods } };
  (globalThis as any).document = { querySelectorAll: () => [] };
  return { state, els, preview: () => preview, restore() { Object.assign(globalThis, previous); } };
}

test("adopting GPT history preserves the current version, provider and protocol binding", () => {
  for (const selectedModelId of gptVersions) {
    for (const historicalModelId of gptVersions) {
      const { state, restore } = installGptAdoptionBridge(selectedModelId);
      const before = [state.selectedModelId, state.selectedProviderId, state.selectedProviderBindingId];
      const snapshot = { canonical_model_id: historicalModelId, provider_id: "gpt-0",
        requested_parameters: { "gpt.quality": "high", "output.count": 3 } };
      try {
        adoptTaskParameters({ task_id: "historical", mode: "generate", generation_snapshot: snapshot } as any);
        assert.deepEqual([state.selectedModelId, state.selectedProviderId, state.selectedProviderBindingId], before);
        assert.equal(snapshot.canonical_model_id, historicalModelId);
      } finally { restore(); }
    }
  }
});

test("adopted GPT parameters reach the controls and request after provider selection", () => {
  for (const targetModelId of gptVersions) {
    for (const sourceModelId of ["model-a", targetModelId]) {
      const { state, els, preview, restore } = installGptAdoptionBridge(sourceModelId);
      const requested = { "canvas.size": "1536x1024", "gpt.quality": "high", "output.count": 3,
        "gpt.background": "transparent", "output.format": "png", "gpt.moderation": "low" };
      const task = { task_id: "historical", mode: "generate", generation_snapshot: {
        canonical_model_id: targetModelId, provider_id: `gpt-${gptVersions.indexOf(targetModelId)}`,
        requested_parameters: requested,
      } } as any;
      try {
        const report = adoptTaskParameters(task);
        assert.equal(state.selectedModelId, targetModelId);
        assert.equal(els.quality.value, "high");
        assert.equal(els.nInput.value, "3");
        assert.equal(els.nInput.selectedValue, "3");
        assert.equal(els.quality.selectedValue, "high");
        assert.equal(els.size.value, "1536x1024");
        assert.equal(els.background.value, "transparent");
        assert.equal(els.moderation.value, "low");
        assert.deepEqual(preview()?.parameters, requested);
        assert.deepEqual(report.values, requested);
        assert.deepEqual(task.generation_snapshot.requested_parameters, requested);
      } finally { restore(); }
    }
  }
});

test("draft initialization preserves valid values, defaults invalid values, and reports drops", () => {
  assert.deepEqual(initializeParameterDraft(model, {
    "canvas.resolution": "2K",
    "feature.enabled": "yes",
    removed: "old",
  }), {
    values: {
      "canvas.resolution": "2K",
      "feature.enabled": false,
      "feature.payload": {},
      "output.count": 1,
    },
    defaulted: [{ id: "feature.enabled", previous: "yes", replacement: false }],
    dropped: [{ id: "removed", previous: "old" }],
  });
});

test("parameter migration feedback skips clean reports and summarizes adjusted legacy values", () => {
  const notices: string[] = [];
  const { restore } = installBridge();
  (globalThis as any).window.__codexImageWebUI.methods.showTransientNotice = (message: string) => notices.push(message);
  try {
    notifyParameterMigration({ values: {}, defaulted: [], dropped: [] });
    assert.deepEqual(notices, []);
    notifyParameterMigration({
      values: {},
      defaulted: [{ id: "canvas.resolution", previous: "legacy", replacement: "1K" }],
      dropped: [{ id: "removed", previous: true }],
    });
    assert.equal(notices.length, 1);
    assert.match(notices[0], /2/);
  } finally {
    restore();
  }
});

test("active values keep hidden drafts but omit them from canonical submission", () => {
  const draft = { "canvas.resolution": "2K", "feature.enabled": false, "feature.payload": { keep: true }, "output.count": 3 };
  assert.deepEqual(activeParameterValuesFor(model, "generate", draft), {
    "canvas.resolution": "2K",
    "feature.enabled": false,
    "output.count": 3,
  });
});

test("only parameters referenced by visibility conditions require a full form rerender", () => {
  assert.equal(parameterAffectsVisibility(model, "canvas.resolution"), false);
  assert.equal(parameterAffectsVisibility(model, "feature.enabled"), true);
});

test("parameter render fingerprints reuse unchanged controls and replace changed controls", () => {
  const definition = parameters[0];
  const baseline = parameterRenderFingerprint(definition, "1K", false);
  assert.equal(parameterRenderFingerprint(definition, "1K", false), baseline);
  assert.notEqual(parameterRenderFingerprint(definition, "2K", false), baseline);
  assert.notEqual(parameterRenderFingerprint({
    ...definition,
    allowed_values: ["1K", "2K", "4K"],
  }, "1K", false), baseline);
});

test("compound safety choices update four independent keys without changing the object contract", () => {
  const safety = {
    id: "gemini.safety_settings",
    label_key: "gemini.safetySettings",
    group: "advanced",
    control: "choice_grid",
    value_type: "object",
    default: {},
    allowed_values: [],
    scope: "model",
    minimum: null,
    maximum: null,
    step: null,
    visible_when: [],
    operations: ["generate"],
    full_width: true,
    object_choices: [{
      key: "HARM_CATEGORY_HARASSMENT",
      label_key: "gemini.safety.harassment",
      default: "HARM_BLOCK_THRESHOLD_UNSPECIFIED",
      allowed_values: ["HARM_BLOCK_THRESHOLD_UNSPECIFIED", "OFF", "BLOCK_ONLY_HIGH"],
      label_keys: ["gemini.safety.unspecified", "gemini.safety.off", "gemini.safety.high"],
    }],
  } as const;
  const existing = { legacy: "preserved", HARM_CATEGORY_HATE_SPEECH: "BLOCK_NONE" };
  assert.deepEqual(nextObjectChoiceValue(safety, existing, "HARM_CATEGORY_HARASSMENT", "BLOCK_ONLY_HIGH"), {
    legacy: "preserved",
    HARM_CATEGORY_HATE_SPEECH: "BLOCK_NONE",
    HARM_CATEGORY_HARASSMENT: "BLOCK_ONLY_HIGH",
  });
  assert.deepEqual(nextObjectChoiceValue(safety, {
    ...existing,
    HARM_CATEGORY_HARASSMENT: "OFF",
  }, "HARM_CATEGORY_HARASSMENT", "HARM_BLOCK_THRESHOLD_UNSPECIFIED"), existing);
});

test("compound safety presets replace four managed keys while preserving unknown history keys", () => {
  const categories = [
    "HARM_CATEGORY_HARASSMENT",
    "HARM_CATEGORY_HATE_SPEECH",
    "HARM_CATEGORY_SEXUALLY_EXPLICIT",
    "HARM_CATEGORY_DANGEROUS_CONTENT",
  ];
  const offValue = Object.fromEntries(categories.map((key) => [key, "OFF"]));
  const blockAllValue = Object.fromEntries(categories.map((key) => [key, "BLOCK_LOW_AND_ABOVE"]));
  const safety = {
    id: "gemini.safety_settings",
    label_key: "gemini.safetySettings",
    group: "advanced",
    control: "object_presets",
    value_type: "object",
    default: offValue,
    allowed_values: [],
    scope: "model",
    minimum: null,
    maximum: null,
    step: null,
    visible_when: [],
    operations: ["generate"],
    full_width: true,
    object_choices: categories.map((key) => ({
      key,
      label_key: key,
      default: "HARM_BLOCK_THRESHOLD_UNSPECIFIED",
      allowed_values: ["HARM_BLOCK_THRESHOLD_UNSPECIFIED", "OFF", "BLOCK_ONLY_HIGH", "BLOCK_LOW_AND_ABOVE"],
      label_keys: ["unspecified", "off", "high", "all"],
    })),
    object_presets: [
      { id: "off", label_key: "off", value: offValue, matches_empty: true },
      { id: "block_all", label_key: "all", value: blockAllValue, matches_empty: false },
    ],
  } as const;

  assert.equal(matchingObjectPreset(safety, {})?.id, "off");
  assert.equal(matchingObjectPreset(safety, offValue)?.id, "off");
  assert.equal(matchingObjectPreset(safety, blockAllValue)?.id, "block_all");
  assert.equal(matchingObjectPreset(safety, {
    ...offValue,
    HARM_CATEGORY_HARASSMENT: "BLOCK_ONLY_HIGH",
  }), null, "mixed legacy values must not pretend to match a preset");
  assert.deepEqual(nextObjectPresetValue(safety, {
    legacy: "preserved",
    ...offValue,
  }, safety.object_presets[1]), {
    legacy: "preserved",
    ...blockAllValue,
  });
});

test("aspect ratio slots keep the approved first column and extended reciprocal pairs", () => {
  const common = ["1:1", "2:3", "3:2", "3:4", "4:3", "4:5", "5:4", "9:16", "16:9", "21:9"];
  assert.deepEqual(aspectRatioSlots(common).map((slot) => slot.values), [
    ["1:1", "21:9"],
    ["4:5", "5:4"],
    ["3:4", "4:3"],
    ["2:3", "3:2"],
    ["9:16", "16:9"],
  ]);
  assert.deepEqual(aspectRatioSlots([...common, "1:4", "1:8", "4:1", "8:1"]).slice(-2).map((slot) => slot.values), [
    ["1:4", "4:1"],
    ["1:8", "8:1"],
  ]);
});

test("aspect ratio SVG geometry preserves orientation and keeps extreme ratios visible", () => {
  const portrait = aspectRatioRect("1:8");
  const landscape = aspectRatioRect("8:1");
  assert.ok(portrait && landscape);
  assert.ok(portrait.width >= 2);
  assert.ok(portrait.height > portrait.width);
  assert.ok(landscape.height >= 2);
  assert.ok(landscape.width > landscape.height);
  assert.equal(aspectRatioRect("auto"), null);
});

test("advanced parameter expansion is manifest driven and history remains expanded", () => {
  assert.equal(advancedParametersAreExpanded({ ...model, expand_advanced_parameters: true }, false), true);
  assert.equal(advancedParametersAreExpanded({ ...model, expand_advanced_parameters: false }, false), false);
  assert.equal(advancedParametersAreExpanded({ ...model, expand_advanced_parameters: false }, true), true);
});

test("legacy GPT custom size is visible only for the GPT custom mode", () => {
  assert.deepEqual(legacyParameterVisibility("gpt-image-2", "preset"), {
    legacyGpt: true,
    customSize: false,
  });
  assert.deepEqual(legacyParameterVisibility("gpt-image-2", "custom"), {
    legacyGpt: true,
    customSize: true,
  });
  assert.deepEqual(legacyParameterVisibility("nano-banana-2", "custom"), {
    legacyGpt: false,
    customSize: false,
  });
});

test("migration has exact values, defaults, and dropped fields", () => {
  assert.deepEqual(migrateParameterValues(model, {
    "canvas.resolution": "4K",
    "feature.enabled": true,
    unknown: 9,
  }), {
    values: {
      "canvas.resolution": "1K",
      "feature.enabled": true,
      "feature.payload": {},
      "output.count": 1,
    },
    defaulted: [{ id: "canvas.resolution", previous: "4K", replacement: "1K" }],
    dropped: [{ id: "unknown", previous: 9 }],
  });
});

test("history inspect only stores a snapshot and cannot mutate frozen composer state", () => {
  const { state, restore } = installBridge();
  const composerBefore = structuredClone({
    selectedFamilyId: state.selectedFamilyId,
    selectedModelId: state.selectedModelId,
    selectedProviderId: state.selectedProviderId,
    parameterDraftsByModel: state.parameterDraftsByModel,
  });
  Object.freeze(state.parameterDraftsByModel["model-a"]);
  Object.freeze(state.parameterDraftsByModel);
  try {
    inspectTaskParameters({ task_id: "history", generation_snapshot: {
      schema_version: 1,
      family_id: "family-a",
      canonical_model_id: "model-a",
      model_manifest_version: 2,
      provider_id: "deleted-provider",
      provider_name: "Deleted Relay",
      binding_id: "old-binding",
      remote_model_id: "relay/old-model",
      protocol_profile: "openai_images",
      parameter_codec: "test",
      requested_parameters: { "canvas.resolution": "1K" },
      mapped_request: {},
    } } as any);
    assert.deepEqual({
      selectedFamilyId: state.selectedFamilyId,
      selectedModelId: state.selectedModelId,
      selectedProviderId: state.selectedProviderId,
      parameterDraftsByModel: state.parameterDraftsByModel,
    }, composerBefore);
    assert.equal(state.inspectedGenerationSnapshot.provider_name, "Deleted Relay");
  } finally {
    restore();
  }
});

test("old tasks receive a GPT-compatible legacy snapshot", () => {
  const snapshot = legacyGenerationSnapshot({
    task_id: "legacy",
    params: { size: "1536x1024", quality: "high", output_format: "webp", n: 2 },
  } as any);
  assert.equal(snapshot.legacy, true);
  assert.equal(snapshot.canonical_model_id, "gpt-image-2");
  assert.deepEqual(snapshot.requested_parameters, {
    "canvas.size": "1536x1024",
    "gpt.quality": "high",
    "output.format": "webp",
    "gpt.moderation": "auto",
    "output.count": 2,
  });
});

test("tasks without frozen snapshots retain their canonical request instead of becoming Image 2", () => {
  const { state, restore } = installBridge();
  try {
    for (const canonicalModelId of [...gptVersions, "nano-banana-2"]) {
      const requested = { "output.count": 3, "canvas.size": "1536x1024", "gpt.quality": "high" };
      const task = { task_id: "pending-failed", status: "failed", local_pending: true,
        params: { model: `vendor/${canonicalModelId}`, quality: "low", n: 1 },
        request: { canonical_model_id: canonicalModelId, provider_id: "current-provider", binding_id: "exact-binding",
          api_provider_name: "Current provider", requested_backend: "openai_responses", parameters: requested },
      } as any;
      inspectTaskParameters(task);
      const snapshot = state.inspectedGenerationSnapshot;
      assert.equal(snapshot.canonical_model_id, canonicalModelId);
      assert.equal(snapshot.family_id, canonicalModelId === "nano-banana-2" ? "gemini-image" : "gpt-image");
      assert.equal(snapshot.provider_id, "current-provider");
      assert.equal(snapshot.provider_name, "Current provider");
      assert.equal(snapshot.binding_id, "exact-binding");
      assert.equal(snapshot.remote_model_id, `vendor/${canonicalModelId}`);
      assert.equal(snapshot.protocol_profile, "openai_responses");
      assert.equal(snapshot.legacy, false);
      assert.deepEqual(snapshot.requested_parameters, requested);
    }
  } finally { restore(); }
});

test("legacy snapshots preserve explicit background data for the restored inspector control", () => {
  assert.equal(Object.hasOwn(legacyGenerationSnapshot({
    task_id: "without-background",
    params: { size: "1024x1024" },
  } as any).requested_parameters, "gpt.background"), false);
  const snapshot = legacyGenerationSnapshot({
    task_id: "with-background",
    params: { size: "1024x1024", background: "transparent" },
  } as any);
  assert.equal(snapshot.requested_parameters["gpt.background"], "transparent");
  assert.equal(taskParameterInspectorParameters(snapshot)["gpt.background"], "transparent");
});

test("GPT history inspector mirrors the visible Image editor controls", () => {
  const snapshot = {
    schema_version: 1,
    family_id: "gpt-image",
    canonical_model_id: "gpt-image-2",
    model_manifest_version: 1,
    provider_id: "relay",
    provider_name: "Relay",
    binding_id: "relay-images",
    remote_model_id: "gpt-image-2",
    protocol_profile: "openai_images",
    parameter_codec: "gpt_openai_images",
    requested_parameters: {
      "canvas.size": "2160x3840",
      "gpt.output_compression": 100,
      "gpt.moderation": "low",
      "gpt.web_search": false,
      "output.count": 2,
    },
    mapped_request: {},
    legacy: false,
  } as any;
  const outputCount = {
    id: "output.count",
    label_key: "output.quantity",
    group: "generation",
    control: "number",
    value_type: "integer",
    default: 1,
    allowed_values: [],
    scope: "application",
    minimum: 1,
    maximum: 4,
    step: 1,
    visible_when: [],
    operations: ["generate"],
    full_width: false,
  } as any;
  const inspector = taskParameterInspectorModel(snapshot, {
    ...model,
    id: "gpt-image-2",
    family_id: "gpt-image",
    parameters: [
      outputCount,
      { ...outputCount, id: "gpt.moderation", label_key: "output.moderation", control: "segmented", value_type: "string", allowed_values: ["auto", "low"], group: "advanced" },
      { ...outputCount, id: "gpt.output_compression", label_key: "output.compression", control: "slider" },
      { ...outputCount, id: "gpt.web_search", label_key: "output.webSearch", control: "toggle", value_type: "boolean" },
    ],
  } as any);

  assert.deepEqual(taskParameterInspectorParameters(snapshot), {
    "canvas.size": "2160x3840",
    "gpt.moderation": "low",
    "output.count": 2,
  });
  assert.deepEqual(inspector?.parameters.map((definition) => definition.id), ["output.count", "gpt.moderation"]);
  assert.equal(inspector?.parameters[0]?.control, "segmented");
  assert.deepEqual(inspector?.parameters[0]?.allowed_values, [1, 2, 3, 4]);
  assert.equal(inspector?.parameters[1]?.group, "generation");
  assert.equal(translate("output.size", "zh-CN"), "输出尺寸");
});

test("history inspection closes when the selected model catches up with the task", () => {
  const snapshot = { canonical_model_id: "gpt-image-2" } as any;
  assert.equal(taskParameterInspectionMatchesSelectedModel(snapshot, "nano-banana-2"), false);
  assert.equal(taskParameterInspectionMatchesSelectedModel(snapshot, "gpt-image-2"), true);
  const task = { task_id: "gpt-history", generation_snapshot: snapshot } as any;
  assert.equal(taskParameterInspectionAction(task, "nano-banana-2", false), "inspect");
  assert.equal(taskParameterInspectionAction(task, "gpt-image-2", false), "clear");
  assert.equal(taskParameterInspectionAction(task, "nano-banana-2", true), "preserve");
});

test("GPT history reconciliation keeps the shared editor and current provider version", () => {
  const { state, restore } = installBridge();
  try {
    for (const historicalModel of ["gpt-image-2", "gpt-image-2.5-flare", "gpt-image-2.5-sunburst"]) {
      const snapshot = { canonical_model_id: historicalModel } as any;
      const task = { task_id: "gpt-history", generation_snapshot: snapshot } as any;
      for (const selectedModel of ["gpt-image-2", "gpt-image-2.5-flare", "gpt-image-2.5-sunburst"]) {
        assert.equal(taskParameterInspectionMatchesSelectedModel(snapshot, selectedModel), true);
        assert.equal(taskParameterInspectionAction(task, selectedModel, false), "clear");
        assert.equal(taskParameterInspectionAction(task, selectedModel, true), "preserve");
        Object.assign(state, {
          selectedModelId: selectedModel,
          selectedProviderId: "current-provider",
          selectedProviderBindingId: "current-binding",
          selectedTaskId: task.task_id,
          tasks: [task],
          inspectedGenerationSnapshot: snapshot,
        });
        const drafts = structuredClone(state.parameterDraftsByModel);
        reconcileTaskParameterInspection();
        assert.equal(state.inspectedGenerationSnapshot, null);
        assert.equal(state.selectedModelId, selectedModel);
        assert.equal(state.selectedProviderId, "current-provider");
        assert.equal(state.selectedProviderBindingId, "current-binding");
        assert.deepEqual(state.parameterDraftsByModel, drafts);
        assert.equal(task.generation_snapshot.canonical_model_id, historicalModel);
      }
    }
  } finally {
    restore();
  }
});

test("history title shows the canonical model once and does not present the remote image model as a main model", () => {
  const title = taskParameterInspectorTitle({
    schema_version: 1,
    family_id: "family-a",
    canonical_model_id: "model-a",
    model_manifest_version: 2,
    provider_id: "provider-a",
    provider_name: "Provider A",
    binding_id: "binding-a",
    remote_model_id: "model-a",
    protocol_profile: "openai_images",
    parameter_codec: "test",
    requested_parameters: {},
    mapped_request: {},
    legacy: false,
  }, catalog);
  assert.equal(title.split("Model A").length - 1, 1);
  assert.doesNotMatch(title, /model-a/);
  assert.match(title, /Provider A/);
});

test("canonical fields are deterministic and do not include image data", () => {
  const form = new FormData();
  appendCanonicalGenerationFields(form, {
    canonicalModelId: "model-a",
    providerId: "provider-a",
    parameters: { z: 1, a: "value" },
  });
  assert.equal(form.get("canonical_model_id"), "model-a");
  assert.equal(form.get("provider_id"), "provider-a");
  assert.equal(form.get("parameters_json"), '{"a":"value","z":1}');
  assert.doesNotMatch(String(form.get("parameters_json")), /data:image/);
});

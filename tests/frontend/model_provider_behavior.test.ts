import assert from "node:assert/strict";
import test from "node:test";

import type { GenerationCatalog } from "../../codex_image/webui/frontend/src/types";
import { eligibleProviders, renderProviderSelection, resolveProviderId, selectedProviderBinding, selectGenerationProvider, settingsTabForProvider } from "../../codex_image/webui/frontend/src/provider-selection";
import { initialCatalogSelection, isGenerationCatalog, persistModelSelection, safeDraftValue } from "../../codex_image/webui/frontend/src/model-catalog";
import {
  canonicalControlValues,
  canonicalParametersForSubmission,
  migratePortableModelDraft,
} from "../../codex_image/webui/frontend/src/model-parameter-drafts";
import { resolveModeSettingsVisibility } from "../../codex_image/webui/frontend/src/mode-settings-visibility";
import {
  renderModelSelectors,
  selectConcreteModel,
  selectModelFamily,
  usesExpandedConcreteModelOptions,
} from "../../codex_image/webui/frontend/src/model-selection";

const catalog: GenerationCatalog = {
  schema_version: 1,
  manifest_version: 1,
  families: [
    { id: "family-a", display_name: "Family A", short_name: "A", label_key: "family.a" },
    { id: "family-b", display_name: "Family B", short_name: "B", label_key: "family.b" },
  ],
  models: [
    { id: "model-a", family_id: "family-a", display_name: "Model A", official_model_id: "model-a", version: 1, operations: ["generate", "edit"], parameters: [], input_constraints: { max_images: 1, supports_mask: false, supports_reference_files: false } },
    { id: "model-b", family_id: "family-b", display_name: "Model B", official_model_id: "model-b", version: 1, operations: ["generate"], parameters: [], input_constraints: { max_images: 1, supports_mask: false, supports_reference_files: false } },
  ],
  providers: [
    { id: "unavailable", name: "Unavailable", builtin: false, available: false, bindings: [{ id: "u-a", canonical_model_id: "model-a", remote_model_id: "private", protocol_profile: "openai_images", parameter_codec: "gpt_openai_images", operations: ["generate"] }] },
    { id: "edit-only", name: "Edit", builtin: false, available: true, bindings: [{ id: "e-a", canonical_model_id: "model-a", remote_model_id: "private", protocol_profile: "openai_images", parameter_codec: "gpt_openai_images", operations: ["edit"] }] },
    { id: "first", name: "First provider with an extremely long accessible name", builtin: false, available: true, bindings: [{ id: "f-a", canonical_model_id: "model-a", remote_model_id: "private", protocol_profile: "openai_images", parameter_codec: "gpt_openai_images", operations: ["generate"] }] },
    { id: "default", name: "Default", builtin: false, available: true, bindings: [{ id: "d-a", canonical_model_id: "model-a", remote_model_id: "private", protocol_profile: "openai_images", parameter_codec: "gpt_openai_images", operations: ["generate", "edit"] }] },
    { id: "other", name: "Other", builtin: false, available: true, bindings: [{ id: "o-b", canonical_model_id: "model-b", remote_model_id: "private", protocol_profile: "openai_images", parameter_codec: "gemini_openai_images", operations: ["generate"], available: false }] },
  ],
  default_provider_by_model: { "model-a": "default" },
  codex: { available: false, mode: "images" },
};

class FakeClassList {
  private readonly values = new Set<string>();

  add(...names: string[]): void {
    names.forEach((name) => this.values.add(name));
  }

  remove(...names: string[]): void {
    names.forEach((name) => this.values.delete(name));
  }

  contains(name: string): boolean {
    return this.values.has(name);
  }

  toggle(name: string, force?: boolean): boolean {
    const active = force === undefined ? !this.values.has(name) : force;
    if (active) this.values.add(name);
    else this.values.delete(name);
    return active;
  }
}

class FakeElement {
  readonly attributes = new Map<string, string>();
  readonly children: FakeElement[] = [];
  readonly classList = new FakeClassList();
  readonly dataset: Record<string, string> = {};
  closestResult: FakeElement | null = null;
  parentElement: FakeElement | null = null;
  className = "";
  disabled = false;
  innerHTML = "";
  textContent = "";
  title = "";
  value = "";

  get options(): FakeElement[] {
    return this.children;
  }

  append(...children: FakeElement[]): void {
    children.forEach((child) => {
      child.parentElement = this;
      this.children.push(child);
    });
  }

  replaceChildren(...children: FakeElement[]): void {
    this.children.forEach((child) => {
      child.parentElement = null;
    });
    this.children.splice(0, this.children.length, ...children);
    children.forEach((child) => {
      child.parentElement = this;
    });
  }

  remove(): void {
    if (!this.parentElement) return;
    const index = this.parentElement.children.indexOf(this);
    if (index >= 0) this.parentElement.children.splice(index, 1);
    this.parentElement = null;
  }

  setAttribute(name: string, value: string): void {
    this.attributes.set(name, value);
  }

  getAttribute(name: string): string | null {
    return this.attributes.get(name) ?? null;
  }

  removeAttribute(name: string): void {
    this.attributes.delete(name);
  }

  closest(_selector: string): FakeElement | null {
    return this.closestResult;
  }

  querySelectorAll(selector: string): FakeElement[] {
    if (selector.includes("[data-family-id]")) return this.children.filter((child) => Boolean(child.dataset.familyId));
    if (selector.includes("[data-model-id]")) return this.children.filter((child) => Boolean(child.dataset.modelId));
    return this.children;
  }

  addEventListener(_type: string, _listener: (...args: any[]) => void): void {}

  focus(): void {}
}

function model(id: string, familyId: string): GenerationCatalog["models"][number] {
  return {
    id,
    family_id: familyId as GenerationCatalog["families"][number]["id"],
    display_name: id,
    official_model_id: id,
    version: 1,
    operations: ["generate"],
    parameters: [],
    input_constraints: { max_images: 1, supports_mask: false, supports_reference_files: false },
  };
}

test("eligibleProviders filters by exact model, operation, and availability", () => {
  assert.deepEqual(eligibleProviders(catalog, "model-a", "generate").map((provider) => provider.id), ["first", "default"]);
  assert.deepEqual(eligibleProviders(catalog, "model-a", "edit").map((provider) => provider.id), ["edit-only", "default"]);
  assert.deepEqual(eligibleProviders(catalog, "model-b", "edit"), []);
  assert.deepEqual(eligibleProviders(catalog, "model-b", "generate"), [], "runtime-unavailable bindings stay hidden");
});

test("resolveProviderId uses last, then backend default, then first", () => {
  const eligible = eligibleProviders(catalog, "model-a", "generate");
  assert.equal(resolveProviderId(eligible, "first", "default"), "first");
  assert.equal(resolveProviderId(eligible, "missing", "default"), "default");
  assert.equal(resolveProviderId(eligible, "missing", "missing"), "first");
  assert.equal(resolveProviderId([], "first", "default"), null);
});

test("provider settings route all providers to API settings", () => {
  assert.equal(settingsTabForProvider("codex"), "api");
  assert.equal(settingsTabForProvider("default"), "api");
  assert.equal(settingsTabForProvider(null), "api");
});

test("concrete model selection expands only when a family has multiple choices", () => {
  assert.equal(usesExpandedConcreteModelOptions([catalog.models[0]]), false);
  assert.equal(usesExpandedConcreteModelOptions(catalog.models), true);
});

test("cross-family concrete model selection rebuilds the active family and its model choices", () => {
  const familyOptions = new FakeElement();
  const familyIndicator = new FakeElement();
  familyIndicator.classList.add("segmented-indicator");
  familyOptions.append(familyIndicator);
  const concreteModelOptions = new FakeElement();
  const concreteModelField = new FakeElement();
  const concreteModelSelect = new FakeElement();
  concreteModelSelect.closestResult = concreteModelField;
  const generationProviderSelect = new FakeElement();
  const previousWindow = (globalThis as any).window;
  const previousDocument = (globalThis as any).document;
  const crossFamilyCatalog: GenerationCatalog = {
    schema_version: 1,
    manifest_version: 1,
    families: [
      { id: "gpt-image", display_name: "GPT Image", short_name: "GPT", label_key: "family.gpt" },
      { id: "gemini-image", display_name: "Gemini", short_name: "Gemini", label_key: "family.gemini" },
    ],
    models: [
      model("gpt-image-2", "gpt-image"),
      model("nano-banana-pro", "gemini-image"),
      model("nano-banana-2", "gemini-image"),
      model("nano-banana-2-lite", "gemini-image"),
    ],
    providers: [],
    default_provider_by_model: {},
    codex: { available: false, mode: "images" },
  };
  const state: any = {
    generationCatalog: crossFamilyCatalog,
    selectedFamilyId: "gpt-image",
    selectedModelId: "gpt-image-2",
    selectedProviderId: null,
    selectedProviderBindingId: null,
    lastModelByFamily: {},
    lastProviderByModel: {},
    lastProviderSelectionByModel: {},
    parameterDraftsByModel: {},
    parameterDraftVersionsByModel: {},
    parameterMigrationByModel: {},
    parameterValidationErrorsByModel: {},
    mode: "generate",
    inspectedGenerationSnapshot: null,
  };

  let reconciledInspections = 0;

  (globalThis as any).document = {
    createElement: () => new FakeElement(),
    querySelectorAll: () => [],
  };
  (globalThis as any).window = {
    requestAnimationFrame(callback: FrameRequestCallback) {
      callback(0);
      return 1;
    },
    __codexImageWebUI: {
      state,
      els: {
        modelFamilyOptions: familyOptions,
        concreteModelOptions,
        concreteModelSelect,
        generationProviderSelect,
      },
      methods: {
        persistModelSelection() {},
        updateModeSpecificSettings() {},
        refreshOutputSettingsLock() {},
        reconcileTaskParameterInspection() {
          reconciledInspections += 1;
          if (state.inspectedGenerationSnapshot?.canonical_model_id === state.selectedModelId) {
            state.inspectedGenerationSnapshot = null;
          }
        },
        updateRequestPreview() {},
      },
    },
  };

  try {
    renderModelSelectors();
    assert.ok(familyOptions.children.includes(familyIndicator), "the family selection indicator remains mounted for a continuous slide");
    selectConcreteModel("nano-banana-2-lite");

    assert.equal(state.selectedFamilyId, "gemini-image");
    assert.ok(familyOptions.children.includes(familyIndicator), "cross-family selection keeps the same indicator mounted");
    assert.equal(familyOptions.children.find((item) => item.getAttribute("aria-checked") === "true")?.dataset.familyId, "gemini-image");
    assert.deepEqual(concreteModelOptions.children.map((item) => item.dataset.modelId), [
      "nano-banana-pro",
      "nano-banana-2",
      "nano-banana-2-lite",
    ]);
    assert.equal(concreteModelOptions.children.find((item) => item.getAttribute("aria-pressed") === "true")?.dataset.modelId, "nano-banana-2-lite");

    state.inspectedGenerationSnapshot = { canonical_model_id: "gpt-image-2" };
    selectModelFamily("gpt-image");
    assert.equal(state.selectedModelId, "gpt-image-2");
    assert.equal(state.inspectedGenerationSnapshot, null, "matching history inspection returns to the editable model form");
    assert.equal(reconciledInspections, 2, "both concrete-model and family changes reconcile the inspector");
  } finally {
    (globalThis as any).window = previousWindow;
    (globalThis as any).document = previousDocument;
  }
});

test("Gemini model switches carry valid shared values and default unsupported choices", () => {
  const parameter = (id: string, defaultValue: unknown, allowedValues: unknown[] = []) => ({
    id,
    label_key: id,
    group: "generation",
    control: typeof defaultValue === "object" ? "object_presets" : "segmented",
    value_type: typeof defaultValue === "number" ? "integer" : typeof defaultValue === "object" ? "object" : "string",
    default: defaultValue,
    allowed_values: allowedValues,
    scope: id === "output.count" ? "application" : "model",
    minimum: null,
    maximum: null,
    step: null,
    visible_when: [],
    operations: ["generate"],
    full_width: false,
  });
  const source = {
    ...catalog.models[0],
    id: "nano-banana-2",
    family_id: "gemini-image",
    parameters: [
      parameter("canvas.aspect_ratio", "1:1", ["1:1", "1:8"]),
      parameter("canvas.resolution", "1K", ["1K", "2K"]),
      parameter("output.count", 1, [1, 2, 3, 4]),
      parameter("gemini.safety_settings", {}),
      parameter("gemini.google_search", "off", ["off", "on"]),
    ],
  } as any;
  const lite = {
    ...source,
    id: "nano-banana-2-lite",
    parameters: [
      parameter("canvas.aspect_ratio", "1:1", ["1:1"]),
      parameter("canvas.resolution", "1K", ["1K"]),
      parameter("output.count", 1, [1, 2, 3, 4]),
      parameter("gemini.safety_settings", {}),
    ],
  } as any;

  assert.deepEqual(migratePortableModelDraft(source, lite, {
    "canvas.aspect_ratio": "1:8",
    "canvas.resolution": "2K",
    "output.count": 3,
    "gemini.safety_settings": { HARM_CATEGORY_HARASSMENT: "OFF" },
    "gemini.google_search": "on",
  }, {
    "canvas.aspect_ratio": "1:1",
    "canvas.resolution": "1K",
    "output.count": 1,
    "gemini.safety_settings": {},
  }), {
    "canvas.aspect_ratio": "1:1",
    "canvas.resolution": "1K",
    "output.count": 3,
    "gemini.safety_settings": { HARM_CATEGORY_HARASSMENT: "OFF" },
  });

  assert.equal(migratePortableModelDraft(lite, source, {
    "canvas.aspect_ratio": "1:1",
    "canvas.resolution": "1K",
    "output.count": 3,
    "gemini.safety_settings": {},
  }, {
    "canvas.aspect_ratio": "1:8",
    "canvas.resolution": "2K",
    "output.count": 1,
    "gemini.safety_settings": {},
    "gemini.google_search": "on",
  })["gemini.google_search"], "on", "target-only search keeps its prior draft");
});

test("GPT-only controls stay hidden for Gemini even without an eligible provider", () => {
  const legacy = { catalogAvailable: false, modelId: null, protocolProfile: null };
  assert.deepEqual(resolveModeSettingsVisibility({ ...legacy, legacyDirectApi: false }), {
    showMainModel: true,
    showApiDirectNotice: false,
    showPromptFidelity: true,
  });
  assert.deepEqual(resolveModeSettingsVisibility({ ...legacy, legacyDirectApi: true }), {
    showMainModel: false,
    showApiDirectNotice: true,
    showPromptFidelity: true,
  });

  for (const modelId of ["nano-banana-pro", "nano-banana-2", "nano-banana-2-lite"]) {
    for (const protocolProfile of [null, "gemini_generate_content", "openai_images"]) {
      assert.deepEqual(resolveModeSettingsVisibility({
        catalogAvailable: true,
        modelId,
        protocolProfile,
        legacyDirectApi: false,
      }), {
        showMainModel: false,
        showApiDirectNotice: false,
        showPromptFidelity: false,
      }, `${modelId} must not expose GPT-only controls for ${protocolProfile || "no binding"}`);
    }
  }

  assert.deepEqual(resolveModeSettingsVisibility({
    catalogAvailable: true,
    modelId: "gpt-image-2",
    protocolProfile: "codex_responses",
    legacyDirectApi: false,
  }), {
    showMainModel: true,
    showApiDirectNotice: false,
    showPromptFidelity: true,
  });
  assert.deepEqual(resolveModeSettingsVisibility({
    catalogAvailable: true,
    modelId: "gpt-image-2",
    protocolProfile: "codex_images",
    legacyDirectApi: true,
  }), {
    showMainModel: false,
    showApiDirectNotice: true,
    showPromptFidelity: true,
  });
});

test("initial selection ignores stale IDs and does not invent a provider", () => {
  assert.deepEqual(initialCatalogSelection(catalog, "missing", { "model-a": "missing" }, "generate"), {
    familyId: "family-a",
    modelId: "model-a",
    providerId: "default",
    bindingId: "d-a",
  });
  const noProviders = { ...catalog, providers: [], default_provider_by_model: {} };
  assert.equal(initialCatalogSelection(noProviders, "model-b", {}, "generate").providerId, null);
  assert.equal(initialCatalogSelection(noProviders, "model-b", {}, "generate").bindingId, null);
});

test("initial Codex selection retains the exact persisted protocol binding", () => {
  const codexCatalog: GenerationCatalog = {
    ...catalog,
    families: [{ id: "gpt-image", display_name: "GPT Image", short_name: "GPT", label_key: "family.gpt" }],
    models: [{
      id: "gpt-image-2",
      family_id: "gpt-image",
      display_name: "GPT Image 2",
      official_model_id: "gpt-image-2",
      version: 1,
      operations: ["generate", "edit"],
      parameters: [],
      input_constraints: { max_images: 1, supports_mask: false, supports_reference_files: false },
    }],
    providers: [{
      id: "codex",
      name: "Codex",
      builtin: true,
      available: true,
      bindings: [
        { id: "codex-gpt-image-2-images", canonical_model_id: "gpt-image-2", remote_model_id: "gpt-image-2", protocol_profile: "codex_images", parameter_codec: "gpt_codex_images", operations: ["generate", "edit"] },
        { id: "codex-gpt-image-2-responses", canonical_model_id: "gpt-image-2", remote_model_id: "gpt-image-2", protocol_profile: "codex_responses", parameter_codec: "gpt_codex_responses", operations: ["generate", "edit"] },
      ],
    }],
    default_provider_by_model: { "gpt-image-2": "codex" },
    codex: { available: true, mode: "images" },
  };

  const selection = (initialCatalogSelection as any)(
    codexCatalog,
    "gpt-image-2",
    { "gpt-image-2": "codex" },
    "generate",
    { "gpt-image-2": "codex::codex-gpt-image-2-responses" },
  );

  assert.equal(selection.providerId, "codex");
  assert.equal(selection.bindingId, "codex-gpt-image-2-responses");
});

test("deep draft sanitization never preserves an over-depth compound secret", () => {
  const deep = { level: { level: { level: { level: { level: { level: { level: {
    harmless: "must-not-survive-as-a-compound",
    apiKey: "deep-secret",
  } } } } } } } };
  const safe = safeDraftValue(deep);
  const serialized = JSON.stringify(safe);
  assert.doesNotMatch(serialized, /deep-secret|must-not-survive-as-a-compound/);
});

test("catalog validation rejects malformed operations and broken Codex invariants", () => {
  assert.equal(isGenerationCatalog(catalog), true);
  const invalidOperation = structuredClone(catalog) as any;
  invalidOperation.models[0].operations = ["delete"];
  assert.equal(isGenerationCatalog(invalidOperation), false);

  const invalidCodex = structuredClone(catalog) as any;
  invalidCodex.codex = { available: true, mode: "images" };
  invalidCodex.providers.push({
    id: "codex",
    name: "Codex",
    builtin: true,
    available: true,
    bindings: [{
      id: "codex-wrong-model",
      canonical_model_id: "model-b",
      remote_model_id: "model-b",
      protocol_profile: "codex_images",
      parameter_codec: "gpt_codex_images",
      operations: ["generate"],
    }],
  });
  assert.equal(isGenerationCatalog(invalidCodex), false);
});

test("persistModelSelection serializes no deeply nested secret compound", () => {
  let serialized = "";
  const previousWindow = (globalThis as any).window;
  const previousStorage = (globalThis as any).localStorage;
  (globalThis as any).localStorage = { setItem: (_key: string, value: string) => { serialized = value; } };
  (globalThis as any).window = { __codexImageWebUI: { state: {
    selectedModelId: "model-a",
    lastModelByFamily: {},
    lastProviderByModel: {},
    parameterDraftsByModel: { "model-a": { nested: { a: { b: { c: { d: { e: { apiKey: "stored-secret", value: "too-deep" } } } } } } } },
  }, els: {}, methods: {} } };
  try {
    persistModelSelection();
    assert.doesNotMatch(serialized, /stored-secret|too-deep/);
  } finally {
    (globalThis as any).window = previousWindow;
    (globalThis as any).localStorage = previousStorage;
  }
});

test("canonical controls honor binding protocol and format conditions", () => {
  const params = { output_format: "webp", output_compression: 63, web_search: true, n: 2 };
  assert.equal(canonicalControlValues(params, "openai_responses")["gpt.web_search"], true);
  assert.equal(canonicalControlValues(params, "openai_images")["gpt.web_search"], false);
  assert.equal(canonicalControlValues(params, "openai_images")["gpt.output_compression"], 63);
  assert.equal("gpt.output_compression" in canonicalControlValues({ ...params, output_format: "png" }, "openai_responses"), false);
});

test("per-model draft is restored but current visible controls win at submission", () => {
  const model = {
    ...catalog.models[0],
    parameters: [
      { id: "output.format", label_key: "output.format", group: "generation", control: "select", value_type: "string", default: "png", allowed_values: ["png", "webp"], scope: "model", minimum: null, maximum: null, step: null, visible_when: [], operations: ["generate"], full_width: false },
      { id: "gpt.output_compression", label_key: "output.compression", group: "advanced", control: "slider", value_type: "integer", default: 80, allowed_values: [], scope: "model", minimum: 0, maximum: 100, step: 1, visible_when: [{ parameter_id: "output.format", operator: "in", value: ["jpeg", "webp"] }], operations: ["generate"], full_width: false },
    ],
  } as any;
  assert.deepEqual(canonicalParametersForSubmission(model, "generate", {
    "output.format": "webp",
    "gpt.output_compression": 42,
  }, {
    "output.format": "webp",
    "gpt.output_compression": 67,
  }), { "output.format": "webp", "gpt.output_compression": 67 });
  assert.deepEqual(canonicalParametersForSubmission(model, "generate", {
    "output.format": "webp",
    "gpt.output_compression": 42,
  }, { "output.format": "png" }), { "output.format": "png" });
});

test("Codex eligibility is defensive even when catalog data claims another family", () => {
  const unsafe = structuredClone(catalog) as GenerationCatalog;
  unsafe.codex = { available: false, mode: "images" };
  unsafe.providers.push({
    id: "codex",
    name: "Codex",
    builtin: true,
    available: true,
    bindings: [{ id: "c-b", canonical_model_id: "model-b", remote_model_id: "model-b", protocol_profile: "codex_images", parameter_codec: "gpt_codex_images", operations: ["generate"] }],
  });
  assert.deepEqual(eligibleProviders(unsafe, "model-b", "generate").map((provider) => provider.id), []);
});

test("health/auth races cannot override catalog provider availability", async () => {
  const previousWindow = (globalThis as any).window;
  const previousFetch = (globalThis as any).fetch;
  let rejectHealth: (reason: Error) => void = () => undefined;
  let renders = 0;
  let modeRecomputes = 0;
  const state: any = {
    generationCatalog: null,
    selectedFamilyId: "family-a",
    selectedModelId: "model-a",
    selectedProviderId: "default",
    lastProviderByModel: { "model-a": "default" },
    mode: "generate",
    authAvailable: false,
    authStatus: null,
  };
  const els: any = {
    apiStatus: { className: "" },
    runButton: { disabled: true },
    apiProviderQuick: { classList: { add() {} } },
  };
  const methods: any = {
    renderProviderSelection() { renders += 1; state.authAvailable = Boolean(state.selectedProviderId); els.runButton.disabled = !state.authAvailable; },
    updateModeSpecificSettings() { modeRecomputes += 1; },
    updateRequestPreview() {},
    syncReferenceFileAvailability() {},
    currentApiMode() { return "images"; },
    currentCodexMode() { return "images"; },
    currentApiProviderLabel() { return "Default"; },
    apiModeLabel() { return "Images"; },
    codexModeLabel() { return "Codex Image"; },
    setStatus() {},
  };
  (globalThis as any).window = { __codexImageWebUI: { state, els, methods } };
  (globalThis as any).fetch = () => new Promise((_resolve, reject) => { rejectHealth = reject; });
  try {
    const auth = await import("../../codex_image/webui/frontend/src/auth-source");
    const pendingHealth = auth.refreshHealth();
    state.generationCatalog = catalog;
    rejectHealth(new Error("health endpoint temporarily unavailable"));
    await pendingHealth;
    assert.equal(state.authAvailable, true);
    assert.equal(els.runButton.disabled, false);

    (globalThis as any).fetch = async () => ({
      ok: true,
      json: async () => ({ selected_source: "api", auth_available: false }),
    });
    assert.equal(await auth.setAuthSource("api"), true);
    assert.equal(state.authAvailable, true, "legacy auth response cannot disable an eligible provider");
    assert.ok(renders >= 2);
    assert.ok(modeRecomputes >= 2);
  } finally {
    (globalThis as any).window = previousWindow;
    (globalThis as any).fetch = previousFetch;
  }
});

test("transparent background controls preserve opaque history and restore JPEG availability", async () => {
  const { setBackgroundControl, updateTransparencyControls, handleTransparentBackgroundChange } = await import("../../codex_image/webui/frontend/src/background-controls");
  const previousWindow = (globalThis as any).window;
  const field = () => ({ classList: new FakeClassList(), dataset: {} as Record<string, string>, textContent: "" });
  const jpegOption = { disabled: false };
  const jpegButton = { disabled: false, title: "" };
  let saved = 0;
  const els: any = {
    background: { value: "auto" }, transparentBackground: { checked: false, disabled: false },
    transparentBackgroundField: field(),
    outputFormat: { value: "jpeg", querySelector: () => jpegOption, dispatchEvent: () => {} },
    outputFormatGroup: { querySelector: () => jpegButton },
  };
  const state: any = { generationCatalog: null, selectedModelId: "gpt-image-2" };
  (globalThis as any).window = { __codexImageWebUI: { els, state, methods: { saveCurrentModelParameterDraft: () => saved++ } } };
  try {
    setBackgroundControl("opaque");
    updateTransparencyControls();
    assert.equal(els.background.value, "opaque");
    assert.equal(els.transparentBackground.checked, false);
    els.transparentBackground.checked = true;
    handleTransparentBackgroundChange();
    assert.equal(els.background.value, "transparent");
    assert.equal(els.outputFormat.value, "png");
    assert.equal(jpegButton.disabled, true);
    assert.equal(jpegOption.disabled, true);
    assert.match(jpegButton.title, /PNG/);
    assert.equal(saved, 1);
    els.transparentBackground.checked = false;
    handleTransparentBackgroundChange();
    assert.equal(els.background.value, "auto");
    assert.equal(els.outputFormat.value, "png");
    assert.equal(jpegButton.disabled, false);
    assert.equal(jpegOption.disabled, false);
    setBackgroundControl("transparent");
    state.generationCatalog = { models: [], providers: [] };
    state.selectedModelId = "nano-banana-pro";
    updateTransparencyControls();
    assert.equal(els.transparentBackgroundField.classList.contains("hidden"), true);
    assert.equal(jpegOption.disabled, false);
    assert.equal(els.background.value, "transparent", "hidden GPT draft is preserved");
  } finally {
    (globalThis as any).window = previousWindow;
  }
});

test("transparency badges use pixel evidence, never request metadata alone", async () => {
  const { transparencyStatus, requestedTransparentBackground } = await import("../../codex_image/webui/frontend/src/transparency-status");
  assert.equal(transparencyStatus(undefined, true), null);
  assert.equal(transparencyStatus(false, false), null);
  assert.ok(transparencyStatus(false, true)?.hint);
  assert.ok(transparencyStatus(true, false)?.label);
  assert.equal(requestedTransparentBackground({ background: "transparent" }), false);
  assert.equal(requestedTransparentBackground({ params: { background: "transparent" } }), true);
  assert.equal(requestedTransparentBackground({ generation_snapshot: { requested_parameters: { "gpt.background": "auto" } }, params: { background: "transparent" } }), false);
});

test("catalog refresh restores saved parameters before request preview, and honors an existing lock", async () => {
  const { refreshGenerationCatalog } = await import("../../codex_image/webui/frontend/src/model-catalog");
  const previous = { window: (globalThis as any).window, document: (globalThis as any).document, fetch: globalThis.fetch, localStorage: (globalThis as any).localStorage };
  const order: string[] = [];
  let locked = false;
  (globalThis as any).window = { __codexImageWebUI: { state: {
    generationCatalog: null, selectedModelId: "model-a", mode: "generate", lastProviderByModel: {}, lastProviderSelectionByModel: {}, parameterDraftsByModel: {}, parameterDraftVersionsByModel: {},
  }, els: {}, methods: {
    isOutputSettingsLocked: () => locked,
    restoreCurrentModelParameterDraft: () => order.push("restore"),
    updateRequestPreview: () => order.push("preview"),
  } } };
  (globalThis as any).document = { querySelectorAll: () => [], createElement: () => new FakeElement() };
  (globalThis as any).localStorage = { setItem: () => {} };
  globalThis.fetch = (async () => ({ ok: true, json: async () => catalog })) as any;
  try {
    await refreshGenerationCatalog();
    assert.deepEqual(order, ["restore", "preview"]);
    order.length = 0;
    locked = true;
    await refreshGenerationCatalog();
    assert.deepEqual(order, ["preview"]);
  } finally {
    (globalThis as any).window = previous.window;
    (globalThis as any).document = previous.document;
    globalThis.fetch = previous.fetch;
    (globalThis as any).localStorage = previous.localStorage;
  }
});

test("catalog refresh follows a changed selected binding instead of switching suppliers", async (t) => {
  const { refreshGenerationCatalog } = await import("../../codex_image/webui/frontend/src/model-catalog");
  const { restoreCurrentModelParameterDraft } = await import("../../codex_image/webui/frontend/src/model-parameter-drafts");
  const previous = { window: globalThis.window, document: globalThis.document, fetch: globalThis.fetch, localStorage: globalThis.localStorage };
  const parameters: any[] = [{
    id: "gpt.quality", label_key: "quality", group: "generation", control: "select", value_type: "string",
    default: "auto", allowed_values: ["auto", "high"], scope: "model", minimum: null, maximum: null,
    step: null, visible_when: [], operations: ["generate", "edit"], full_width: false,
  }];
  const provider = (id: string, modelId: string): any => ({
    id, name: id, builtin: false, available: true,
    bindings: [{ id: `${id}-binding`, canonical_model_id: modelId, remote_model_id: modelId,
      protocol_profile: "openai_images", parameter_codec: "gpt_openai_images", operations: ["generate", "edit"] }],
  });
  const before: GenerationCatalog = {
    ...catalog,
    families: [{ id: "gpt-image", display_name: "GPT Image", short_name: "GPT", label_key: "gpt" }],
    models: ["gpt-image-2", "gpt-image-2.5-flare", "gpt-image-2.5-sunburst"].map(id => ({
      ...model(id, "gpt-image"), operations: ["generate", "edit"], parameters,
    })),
    providers: [provider("edited", "gpt-image-2"), provider("fallback", "gpt-image-2")],
    default_provider_by_model: { "gpt-image-2": "edited" },
  };
  const state: any = {};
  const els: any = { quality: new FakeElement(), concreteModelSelect: new FakeElement(), generationProviderSelect: new FakeElement() };
  const previews: string[] = [];
  const prepare = (nextModel: string, locked = false) => {
    Object.assign(state, {
      generationCatalog: structuredClone(before), selectedFamilyId: "gpt-image", selectedModelId: "gpt-image-2",
      selectedProviderId: "edited", selectedProviderBindingId: "edited-binding", mode: "generate",
      lastModelByFamily: { "gpt-image": "gpt-image-2" }, lastProviderByModel: { "gpt-image-2": "edited" },
      lastProviderSelectionByModel: { "gpt-image-2": "edited::edited-binding" },
      parameterDraftsByModel: {}, parameterDraftVersionsByModel: {}, parameterValidationErrorsByModel: {},
    });
    els.quality.value = "high";
    previews.length = 0;
    (globalThis as any).window = { __codexImageWebUI: { state, els, methods: {
      isOutputSettingsLocked: () => locked, currentTaskParams: () => ({ quality: els.quality.value }),
      restoreCurrentModelParameterDraft, persistModelSelection,
      updateRequestPreview: () => previews.push(`${state.selectedModelId}:${state.selectedProviderId}`),
    } } };
    const after = structuredClone(before);
    after.providers[0].bindings[0].canonical_model_id = nextModel;
    after.providers[0].bindings[0].remote_model_id = nextModel;
    after.default_provider_by_model = { "gpt-image-2": "fallback", [nextModel]: "edited" };
    globalThis.fetch = (async () => ({ ok: true, json: async () => after })) as any;
    return after;
  };
  (globalThis as any).document = { querySelectorAll: () => [], createElement: () => new FakeElement() };
  (globalThis as any).localStorage = { setItem() {} };
  try {
    for (const nextModel of ["gpt-image-2.5-flare", "gpt-image-2.5-sunburst"]) {
      for (const locked of [false, true]) {
        await t.test(`${nextModel} follows the selected binding with parameters ${locked ? "locked" : "unlocked"}`, async () => {
          prepare(nextModel, locked);
          await refreshGenerationCatalog();
          assert.equal(state.selectedModelId, nextModel);
          assert.equal(state.selectedProviderId, "edited");
          assert.equal(state.selectedProviderBindingId, "edited-binding");
          assert.equal(state.lastModelByFamily["gpt-image"], nextModel);
          assert.equal(els.concreteModelSelect.value, nextModel);
          assert.equal(els.generationProviderSelect.value, "edited::edited-binding");
          assert.equal(els.quality.value, "high");
          assert.equal(state.parameterDraftsByModel[nextModel]["gpt.quality"], "high");
          assert.deepEqual(previews, [`${nextModel}:edited`], "no preview uses a fallback supplier during the transition");
        });
        await t.test(`${nextModel} restores a moved binding after reload with parameters ${locked ? "locked" : "unlocked"}`, async () => {
          prepare(nextModel, locked);
          state.generationCatalog = null;
          state.selectedProviderId = null;
          state.selectedProviderBindingId = null;
          state.parameterDraftsByModel["gpt-image-2"] = { "gpt.quality": "high" };
          els.quality.value = "auto";
          await refreshGenerationCatalog();
          assert.equal(state.selectedModelId, nextModel);
          assert.equal(state.selectedProviderId, "edited");
          assert.equal(state.selectedProviderBindingId, "edited-binding");
          assert.equal(state.lastModelByFamily["gpt-image"], nextModel);
          assert.equal(state.lastProviderSelectionByModel[nextModel], "edited::edited-binding");
          assert.equal(els.quality.value, "high");
          assert.equal(state.parameterDraftsByModel[nextModel]["gpt.quality"], "high");
          assert.deepEqual(previews, [`${nextModel}:edited`]);
        });
      }
    }
    await t.test("editing another provider does not change the current model or supplier", async () => {
      prepare("gpt-image-2.5-flare");
      state.selectedProviderId = "fallback";
      state.selectedProviderBindingId = "fallback-binding";
      state.lastProviderByModel["gpt-image-2"] = "fallback";
      state.lastProviderSelectionByModel["gpt-image-2"] = "fallback::fallback-binding";
      await refreshGenerationCatalog();
      assert.equal(state.selectedModelId, "gpt-image-2");
      assert.equal(state.selectedProviderId, "fallback");
    });
    await t.test("an unavailable replacement binding is not selected", async () => {
      const after = prepare("gpt-image-2.5-flare");
      after.providers[0].bindings[0].available = false;
      await refreshGenerationCatalog();
      assert.equal(state.selectedModelId, "gpt-image-2");
      assert.equal(state.selectedProviderId, "fallback");
    });
    await t.test("reload rejects moved bindings unavailable for the current operation", async () => {
      const after = prepare("gpt-image-2.5-flare");
      after.providers[0].bindings[0].operations = ["edit"];
      const selection = initialCatalogSelection(after, "gpt-image-2", state.lastProviderByModel, "generate", state.lastProviderSelectionByModel);
      assert.equal(selection.modelId, "gpt-image-2");
      assert.equal(selection.providerId, "fallback");
    });
    await t.test("changing another binding on the same supplier keeps the selected binding", async () => {
      const after = prepare("gpt-image-2.5-flare");
      after.providers[0].bindings[0] = structuredClone(before.providers[0].bindings[0]);
      after.providers[0].bindings.push({
        ...after.providers[0].bindings[0], id: "other-binding", canonical_model_id: "gpt-image-2.5-flare",
      });
      await refreshGenerationCatalog();
      assert.equal(state.selectedModelId, "gpt-image-2");
      assert.equal(state.selectedProviderId, "edited");
      assert.equal(state.selectedProviderBindingId, "edited-binding");
    });
  } finally {
    globalThis.window = previous.window;
    globalThis.document = previous.document;
    globalThis.fetch = previous.fetch;
    globalThis.localStorage = previous.localStorage;
  }
});

test("GPT versions share one parameter panel and are selected through provider bindings", () => {
  const previous = { window: globalThis.window, document: globalThis.document };
  const binding = (id: string, modelId: string, protocol = "openai_images"): any => ({
    id, canonical_model_id: modelId, remote_model_id: `vendor/${modelId}`, protocol_profile: protocol,
    parameter_codec: "gpt_openai_images", operations: ["generate", "edit"],
  });
  const provider = (id: string, bindings: any[]): any => ({ id, name: id, available: true, builtin: id === "codex", bindings });
  const parameters: any[] = [{
    id: "gpt.quality", label_key: "quality", group: "generation", control: "select", value_type: "string",
    default: "auto", allowed_values: ["auto", "high"], scope: "model", minimum: null, maximum: null,
    step: null, visible_when: [], operations: ["generate", "edit"], full_width: false,
  }];
  const gptCatalog: GenerationCatalog = {
    ...catalog,
    families: [
      { id: "gpt-image", display_name: "GPT", short_name: "GPT", label_key: "gpt" },
      { id: "gemini-image", display_name: "Gemini", short_name: "Gemini", label_key: "gemini" },
    ],
    models: [
      ...["gpt-image-2", "gpt-image-2.5-flare", "gpt-image-2.5-sunburst"].map(id => ({ ...model(id, "gpt-image"), parameters })),
      model("nano-banana-pro", "gemini-image"), model("nano-banana-2", "gemini-image"),
    ],
    providers: [
      provider("old", [binding("old-2", "gpt-image-2")]),
      provider("modern", [binding("modern-flare", "gpt-image-2.5-flare")]),
      provider("multi", [binding("multi-2", "gpt-image-2"), binding("multi-sunburst", "gpt-image-2.5-sunburst")]),
      provider("codex", [
        { ...binding("codex-images", "gpt-image-2", "codex_images"), display_name: "Codex Image" },
        { ...binding("codex-responses", "gpt-image-2", "codex_responses"), display_name: "Codex Responses" },
      ]),
      provider("gemini", [binding("gemini-pro", "nano-banana-pro"), binding("gemini-2", "nano-banana-2")]),
      { ...provider("unavailable", [binding("unavailable-flare", "gpt-image-2.5-flare")]), available: false },
      provider("edit-only", [{ ...binding("edit-only-sunburst", "gpt-image-2.5-sunburst"), operations: ["edit"] }]),
    ],
    default_provider_by_model: { "gpt-image-2": "old", "gpt-image-2.5-flare": "modern", "gpt-image-2.5-sunburst": "multi" },
    codex: { available: true, mode: "images" },
  };
  const field = new FakeElement();
  const els: any = {
    concreteModelSelect: new FakeElement(), concreteModelOptions: new FakeElement(),
    generationProviderSelect: new FakeElement(), quality: new FakeElement(), runButton: new FakeElement(),
  };
  els.concreteModelSelect.closestResult = field;
  els.quality.value = "high";
  const state: any = {
    generationCatalog: gptCatalog, selectedFamilyId: "gpt-image", selectedModelId: "gpt-image-2", mode: "generate",
    selectedProviderId: "old", selectedProviderBindingId: "old-2", lastModelByFamily: {},
    lastProviderByModel: { "gpt-image-2": "old" }, lastProviderSelectionByModel: { "gpt-image-2": "old::old-2" },
    parameterDraftsByModel: {}, parameterDraftVersionsByModel: {}, parameterValidationErrorsByModel: {},
  };
  (globalThis as any).window = { __codexImageWebUI: { state, els, methods: {
    currentTaskParams: () => ({ quality: els.quality.value }), persistModelSelection() {},
  } } };
  (globalThis as any).document = { querySelectorAll: () => [], createElement: () => new FakeElement() };
  try {
    renderModelSelectors();
    renderProviderSelection();
    assert.equal(field.classList.contains("hidden"), true, "GPT has no separate model selector");
    const choices = els.generationProviderSelect.options;
    assert.deepEqual(choices.map((option: any) => option.value), [
      "old::old-2", "modern::modern-flare", "multi::multi-2", "multi::multi-sunburst",
      "codex::codex-images", "codex::codex-responses",
    ]);
    assert.notEqual(choices[2].textContent, choices[3].textContent, "multiple versions on one supplier remain distinguishable");
    selectGenerationProvider("modern::modern-flare");
    assert.equal(state.selectedModelId, "gpt-image-2.5-flare");
    assert.equal(state.selectedProviderId, "modern");
    assert.equal(selectedProviderBinding()?.remote_model_id, "vendor/gpt-image-2.5-flare");
    assert.equal(els.quality.value, "high");
    assert.equal(field.classList.contains("hidden"), true);
    selectGenerationProvider("codex::codex-responses");
    assert.equal(state.selectedModelId, "gpt-image-2");
    assert.equal(state.selectedProviderBindingId, "codex-responses");
    assert.equal(selectedProviderBinding()?.protocol_profile, "codex_responses");
    selectGenerationProvider("multi::multi-sunburst");
    assert.equal(state.selectedModelId, "gpt-image-2.5-sunburst");
    assert.equal(state.selectedProviderBindingId, "multi-sunburst");

    state.selectedModelId = "gpt-image-2";
    state.generationCatalog = { ...gptCatalog, providers: [gptCatalog.providers[1]] };
    renderProviderSelection();
    assert.equal(els.generationProviderSelect.disabled, false, "another GPT version remains selectable when the old model has no provider");
    assert.equal(els.runButton.disabled, true, "generation still requires an exact model binding");
    selectGenerationProvider("modern::modern-flare");
    assert.equal(els.runButton.disabled, false);

    state.generationCatalog = gptCatalog;
    state.selectedFamilyId = "gemini-image";
    state.selectedModelId = "nano-banana-pro";
    renderModelSelectors();
    renderProviderSelection();
    assert.equal(field.classList.contains("hidden"), false, "Gemini keeps its concrete-model controls");
    assert.deepEqual(els.generationProviderSelect.options.map((option: any) => option.value), ["gemini::gemini-pro"]);
  } finally {
    globalThis.window = previous.window;
    globalThis.document = previous.document;
  }
});

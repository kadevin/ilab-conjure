import assert from "node:assert/strict";
import test from "node:test";

import {
  availableCompatibilityLayers,
  availableProtocolsForModel,
  bindingForCompatibilitySelection,
  bindingForProtocolSelection,
  bindingFromProtocol,
  compatibilityForBinding,
  isBindingTemplateBaseUrl,
  normalizeProviderBindings,
  protocolForBinding,
  readProviderBindingCards,
  resolvedBindingOperations,
  validateProviderBindingOverlaps,
} from "../../codex_image/webui/frontend/src/provider-model-bindings";

test("only known template URLs are safe to replace during a new-provider compatibility change", () => {
  assert.equal(isBindingTemplateBaseUrl("https://api.change2pro.com/v1beta"), true);
  assert.equal(isBindingTemplateBaseUrl("https://openrouter.ai/api/v1/"), true);
  assert.equal(isBindingTemplateBaseUrl("https://private-relay.example/v1"), false);
});

test("one provider preserves GPT and Nano Banana bindings with arbitrary remote IDs", () => {
  const bindings = normalizeProviderBindings([
    bindingFromProtocol("relay-gpt", "gpt-image-2", "vendor/gpt.image:2-pro", "openai_images"),
    bindingFromProtocol("relay-nano", "nano-banana-pro", "models/nano.banana:pro-2", "gemini"),
  ], "relay");
  assert.deepEqual(bindings.map((item) => item.remote_model_id), [
    "vendor/gpt.image:2-pro",
    "models/nano.banana:pro-2",
  ]);
  assert.equal(validateProviderBindingOverlaps(bindings), null);
});

test("three direct protocols map explicitly by canonical model", () => {
  assert.deepEqual(availableProtocolsForModel("gpt-image-2"), ["openai_images", "openai_responses"]);
  assert.deepEqual(availableProtocolsForModel("unsupported-image"), []);
  assert.deepEqual(availableProtocolsForModel("nano-banana-pro"), ["gemini", "openai_images"]);

  const generateContent = bindingFromProtocol("b", "nano-banana-2", "anything/custom-looking", "gemini");
  assert.equal(generateContent.protocol_profile, "gemini_generate_content");
  assert.equal(generateContent.parameter_codec, "gemini_generate_content_image");
  const geminiOpenAI = bindingFromProtocol("c", "nano-banana-2-lite", "custom", "openai_images");
  assert.equal(geminiOpenAI.protocol_profile, "openai_images");
  assert.equal(geminiOpenAI.parameter_codec, "gemini_openai_images");
  const gpt = bindingFromProtocol("d", "gpt-image-2", "custom", "openai_images");
  assert.equal(gpt.protocol_profile, "openai_images");
  assert.equal(gpt.parameter_codec, "gpt_openai_images");
  const gptResponses = bindingFromProtocol(
    "responses",
    "gpt-image-2",
    "custom",
    "openai_responses",
    ["generate", "edit"],
  );
  assert.equal(gptResponses.protocol_profile, "openai_responses");
  assert.equal(gptResponses.parameter_codec, "gpt_openai_responses");
  assert.equal(protocolForBinding(gptResponses), "openai_responses");
  assert.throws(
    () => bindingFromProtocol("f", "gpt-image-2", "custom", "gemini"),
    /unsupported_binding_protocol/,
  );
});

test("compatibility layers stay binding-scoped and map to explicit transports", () => {
  assert.deepEqual(
    availableCompatibilityLayers("nano-banana-2", "gemini"),
    ["standard", "gemini_image_config", "change2pro"],
  );
  assert.deepEqual(
    availableCompatibilityLayers("nano-banana-2", "openai_images"),
    ["standard", "t8_newapi", "openrouter"],
  );
  assert.deepEqual(
    availableCompatibilityLayers("gpt-image-2", "openai_responses"),
    ["standard"],
  );

  const standard = bindingFromProtocol(
    "nano",
    "nano-banana-2",
    "gemini-3.1-flash-image",
    "gemini",
  );
  const imageConfig = bindingForCompatibilitySelection(
    standard,
    "nano-banana-2",
    standard.remote_model_id,
    "gemini",
    "gemini_image_config",
    true,
    ["generate", "edit"],
  );
  assert.equal(imageConfig.protocol_profile, "gemini_generate_content");
  assert.equal(imageConfig.parameter_codec, "gemini_generate_content_image_config");
  assert.equal(compatibilityForBinding(imageConfig), "gemini_image_config");

  const change2pro = bindingForCompatibilitySelection(
    standard,
    "nano-banana-2",
    "gemini-3.1-flash-image-preview",
    "gemini",
    "change2pro",
    true,
    ["generate", "edit"],
  );
  assert.equal(change2pro.protocol_profile, "gemini_change2pro_generate_content");
  assert.equal(change2pro.parameter_codec, "gemini_generate_content_image_config");
  assert.equal(change2pro.remote_model_id, "gemini-3.1-flash-image-preview");
  assert.equal(compatibilityForBinding(change2pro), "change2pro");

  const t8 = bindingForCompatibilitySelection(
    standard,
    "nano-banana-2",
    standard.remote_model_id,
    "openai_images",
    "t8_newapi",
    true,
    ["generate", "edit"],
  );
  assert.equal(t8.protocol_profile, "t8_images");
  assert.equal(t8.parameter_codec, "gemini_t8_images");
  assert.equal(compatibilityForBinding(t8), "t8_newapi");
  assert.equal(t8.remote_model_id, standard.remote_model_id);

  const openrouter = bindingForCompatibilitySelection(
    standard,
    "nano-banana-2",
    "google/gemini-3.1-flash-image",
    "openai_images",
    "openrouter",
    true,
    ["generate", "edit"],
  );
  assert.equal(openrouter.protocol_profile, "openrouter_images");
  assert.equal(openrouter.parameter_codec, "gemini_openrouter_images");
  assert.equal(compatibilityForBinding(openrouter), "openrouter");
});

test("unchanged protocol selection preserves the existing binding", () => {
  const responses = normalizeProviderBindings([{
    id: "responses",
    canonical_model_id: "gpt-image-2",
    remote_model_id: "relay/gpt-custom",
    protocol_profile: "openai_responses",
    parameter_codec: "gpt_openai_responses",
    operations: ["generate", "edit"],
  }], "relay")[0];
  assert.deepEqual(
    bindingForProtocolSelection(responses, "gpt-image-2", "relay/gpt-custom", "openai_responses", false, ["generate", "edit"]),
    responses,
  );
});

test("aspect-ratio prompt remains binding-scoped through normalization and protocol changes", () => {
  const original = normalizeProviderBindings([{
    id: "responses",
    canonical_model_id: "gpt-image-2",
    remote_model_id: "relay/gpt-custom",
    protocol_profile: "openai_responses",
    parameter_codec: "gpt_openai_responses",
    operations: ["generate", "edit"],
    append_aspect_ratio_prompt: true,
  }], "relay")[0];

  assert.equal(original.append_aspect_ratio_prompt, true);
  const changed = bindingForProtocolSelection(
    original,
    "gpt-image-2",
    original.remote_model_id,
    "openai_images",
    true,
    ["generate", "edit"],
  );
  assert.equal(changed.append_aspect_ratio_prompt, true);
});

test("GPT direct protocol changes normalize only that model binding", () => {
  const images = bindingFromProtocol("gpt", "gpt-image-2", "relay/gpt", "openai_images");
  const responses = bindingForProtocolSelection(
    images,
    "gpt-image-2",
    "relay/gpt",
    "openai_responses",
    true,
    ["generate", "edit"],
  );
  assert.equal(responses.protocol_profile, "openai_responses");
  assert.equal(responses.parameter_codec, "gpt_openai_responses");
  const restored = bindingForProtocolSelection(
    responses,
    "gpt-image-2",
    "relay/gpt",
    "openai_images",
    true,
    ["generate", "edit"],
  );
  assert.equal(restored.protocol_profile, "openai_images");
  assert.equal(restored.parameter_codec, "gpt_openai_images");
});

test("overlapping model operations are rejected but disjoint operations are allowed", () => {
  const generate = bindingFromProtocol("a", "gpt-image-2", "one", "openai_images", ["generate"]);
  const edit = bindingFromProtocol("b", "gpt-image-2", "two", "openai_images", ["edit"]);
  assert.equal(validateProviderBindingOverlaps([generate, edit]), null);
  const duplicate = bindingFromProtocol("c", "gpt-image-2", "three", "openai_images", ["generate"]);
  assert.deepEqual(validateProviderBindingOverlaps([generate, duplicate]), {
    firstBindingId: "a",
    secondBindingId: "c",
    canonicalModelId: "gpt-image-2",
    operation: "generate",
  });
});

test("binding cards use the model-resolved operations instead of editable operation checkboxes", () => {
  const card = {
    dataset: {
      bindingId: "relay-gpt",
      bindingOriginalModelId: "gpt-image-2",
      bindingOriginalProtocolProfile: "openai_images",
      bindingOriginalParameterCodec: "gpt_openai_images",
      bindingProtocolChanged: "false",
      bindingCompatibilityChanged: "false",
      bindingModelOperations: "generate,edit",
    },
    querySelector(selector: string) {
      if (selector === "[data-binding-model]") return { value: "gpt-image-2" };
      if (selector === "[data-binding-remote-model]") return { value: "relay/gpt-image-2" };
      if (selector === "[data-binding-protocol]") return { value: "openai_images" };
      if (selector === "[data-binding-compatibility]") return { value: "standard" };
      if (selector === "[data-binding-ratio-prompt]") return { checked: true };
      if (selector === "[data-binding-default]") return { checked: false };
      return null;
    },
    querySelectorAll() {
      return [];
    },
  } as unknown as HTMLElement;
  const container = {
    querySelectorAll() {
      return [card];
    },
  } as unknown as HTMLElement;

  const bindings = readProviderBindingCards(container);

  assert.deepEqual(bindings[0].operations, ["generate", "edit"]);
  assert.equal(bindings[0].append_aspect_ratio_prompt, true);
});

test("binding cards preserve legacy split operations while single bindings adopt the model operations", () => {
  const model = {
    id: "gpt-image-2",
    operations: ["generate", "edit"],
  } as any;
  const single = bindingFromProtocol("single", "gpt-image-2", "relay/single", "openai_images", ["generate"]);
  assert.deepEqual(resolvedBindingOperations(single, [single], model), ["generate", "edit"]);

  const generate = bindingFromProtocol("generate", "gpt-image-2", "relay/generate", "openai_images", ["generate"]);
  const edit = bindingFromProtocol("edit", "gpt-image-2", "relay/edit", "openai_images", ["edit"]);
  assert.deepEqual(resolvedBindingOperations(generate, [generate, edit], model), ["generate"]);
  assert.deepEqual(resolvedBindingOperations(edit, [generate, edit], model), ["edit"]);
});

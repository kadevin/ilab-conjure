import type {
  CatalogModel,
  GenerationOperation,
  ProviderModelBindingSettings,
} from "./types";
import { translate } from "./i18n";
import { destroyThemedSelects, mountThemedSelect } from "./themed-select";

export type BindingTemplateId = keyof typeof BINDING_TEMPLATES;
export type BindingProtocol = "gemini" | "openai_images" | "openai_responses";
export type BindingCompatibility = "standard" | "gemini_image_config" | "change2pro" | "t8_newapi" | "openrouter";

export const BINDING_TEMPLATES = {
  gpt_openai_images: {
    protocol_profile: "openai_images",
    parameter_codec: "gpt_openai_images",
    base_url: "https://api.openai.com/v1",
  },
  gpt_openai_responses: {
    protocol_profile: "openai_responses",
    parameter_codec: "gpt_openai_responses",
    base_url: "https://api.openai.com/v1",
  },
  gemini_generate_content: {
    protocol_profile: "gemini_generate_content",
    parameter_codec: "gemini_generate_content_image",
    base_url: "https://generativelanguage.googleapis.com/v1beta",
  },
  gemini_generate_content_image_config: {
    protocol_profile: "gemini_generate_content",
    parameter_codec: "gemini_generate_content_image_config",
    base_url: "https://api.change2pro.com/v1beta",
  },
  gemini_change2pro_generate_content: {
    protocol_profile: "gemini_change2pro_generate_content",
    parameter_codec: "gemini_generate_content_image_config",
    base_url: "https://api.change2pro.com/v1",
  },
  gemini_openai_images: {
    protocol_profile: "openai_images",
    parameter_codec: "gemini_openai_images",
    base_url: "https://generativelanguage.googleapis.com/v1beta/openai",
  },
  gemini_t8_images: {
    protocol_profile: "t8_images",
    parameter_codec: "gemini_t8_images",
    base_url: "https://ai.t8star.org/v1",
  },
  gemini_openrouter_images: {
    protocol_profile: "openrouter_images",
    parameter_codec: "gemini_openrouter_images",
    base_url: "https://openrouter.ai/api/v1",
  },
} as const;

export const BINDING_PROTOCOL_LABELS: Record<BindingProtocol, string> = {
  gemini: "Gemini",
  openai_images: "OpenAI Images",
  openai_responses: "OpenAI Responses",
};

export const BINDING_COMPATIBILITY_LABELS: Record<BindingCompatibility, string> = {
  standard: "标准",
  gemini_image_config: "Gemini ImageConfig",
  change2pro: "Change2Pro / Gemini v1beta",
  t8_newapi: "T8 / NewAPI",
  openrouter: "OpenRouter",
};

function slug(value: unknown, fallback: string): string {
  return String(value || fallback).trim().toLowerCase()
    .replace(/[^a-z0-9_-]+/g, "-").replace(/^-+|-+$/g, "") || fallback;
}

function normalizedOperations(value: unknown): GenerationOperation[] {
  const operations = Array.isArray(value)
    ? value.filter((item): item is GenerationOperation => item === "generate" || item === "edit")
    : [];
  return [...new Set(operations)];
}

export function resolvedBindingOperations(
  binding: ProviderModelBindingSettings,
  bindings: ProviderModelBindingSettings[],
  model?: CatalogModel,
): GenerationOperation[] {
  const hasLegacySplitBindings = bindings.filter(
    (candidate) => candidate.canonical_model_id === binding.canonical_model_id,
  ).length > 1;
  if (hasLegacySplitBindings || !model) return binding.operations;
  return [...model.operations];
}

export function availableProtocolsForModel(modelId: string): BindingProtocol[] {
  if (modelId.startsWith("nano-banana")) return ["gemini", "openai_images"];
  if (modelId === "gpt-image-2") return ["openai_images", "openai_responses"];
  return [];
}

export function availableCompatibilityLayers(
  modelId: string,
  protocol: BindingProtocol,
): BindingCompatibility[] {
  if (modelId.startsWith("nano-banana") && protocol === "gemini") {
    return ["standard", "gemini_image_config", "change2pro"];
  }
  if (modelId.startsWith("nano-banana") && protocol === "openai_images") {
    return ["standard", "t8_newapi", "openrouter"];
  }
  return ["standard"];
}

export function protocolForBinding(binding: Partial<ProviderModelBindingSettings>): BindingProtocol {
  const profile = String(binding.protocol_profile || "");
  if (profile.startsWith("gemini_")) return "gemini";
  return profile.includes("responses") ? "openai_responses" : "openai_images";
}

export function compatibilityForBinding(
  binding: Partial<ProviderModelBindingSettings>,
): BindingCompatibility {
  if (binding.protocol_profile === "gemini_change2pro_generate_content") return "change2pro";
  const codec = String(binding.parameter_codec || "");
  if (codec === "gemini_generate_content_image_config") return "gemini_image_config";
  if (codec === "gemini_t8_images") return "t8_newapi";
  if (codec === "gemini_openrouter_images") return "openrouter";
  return "standard";
}

export function bindingTemplateForProtocol(
  modelId: string,
  protocol: BindingProtocol,
): BindingTemplateId {
  if (!availableProtocolsForModel(modelId).includes(protocol)) {
    throw new Error("unsupported_binding_protocol");
  }
  if (modelId.startsWith("nano-banana")) {
    return protocol === "gemini" ? "gemini_generate_content" : "gemini_openai_images";
  }
  if (modelId === "gpt-image-2") {
    return protocol === "openai_responses" ? "gpt_openai_responses" : "gpt_openai_images";
  }
  throw new Error("unsupported_binding_protocol");
}

export function bindingTemplateForCompatibility(
  modelId: string,
  protocol: BindingProtocol,
  compatibility: BindingCompatibility,
): BindingTemplateId {
  if (!availableCompatibilityLayers(modelId, protocol).includes(compatibility)) {
    throw new Error("unsupported_binding_compatibility");
  }
  if (compatibility === "gemini_image_config") {
    return "gemini_generate_content_image_config";
  }
  if (compatibility === "change2pro") return "gemini_change2pro_generate_content";
  if (compatibility === "t8_newapi") return "gemini_t8_images";
  if (compatibility === "openrouter") return "gemini_openrouter_images";
  return bindingTemplateForProtocol(modelId, protocol);
}

export function bindingFromTemplate(
  id: string,
  canonicalModelId: string,
  remoteModelId: string,
  templateId: BindingTemplateId,
  operations: GenerationOperation[] = ["generate", "edit"],
): ProviderModelBindingSettings {
  const template = BINDING_TEMPLATES[templateId];
  return {
    id: slug(id, `binding-${Date.now()}`),
    canonical_model_id: String(canonicalModelId || "").trim(),
    remote_model_id: String(remoteModelId || "").trim(),
    protocol_profile: template.protocol_profile,
    parameter_codec: template.parameter_codec,
    operations: normalizedOperations(operations),
  };
}

export function bindingFromProtocol(
  id: string,
  canonicalModelId: string,
  remoteModelId: string,
  protocol: BindingProtocol,
  operations: GenerationOperation[] = ["generate", "edit"],
): ProviderModelBindingSettings {
  return bindingFromTemplate(
    id,
    canonicalModelId,
    remoteModelId,
    bindingTemplateForProtocol(canonicalModelId, protocol),
    operations,
  );
}

export function bindingForProtocolSelection(
  original: ProviderModelBindingSettings,
  canonicalModelId: string,
  remoteModelId: string,
  protocol: BindingProtocol,
  protocolChanged: boolean,
  operations: GenerationOperation[],
): ProviderModelBindingSettings {
  if (!protocolChanged && canonicalModelId === original.canonical_model_id) {
    return {
      ...original,
      remote_model_id: remoteModelId,
      operations: normalizedOperations(operations),
    };
  }
  return {
    ...bindingFromProtocol(
      original.id,
      canonicalModelId,
      remoteModelId,
      protocol,
      operations,
    ),
    append_aspect_ratio_prompt: Boolean(original.append_aspect_ratio_prompt),
  };
}

export function bindingForCompatibilitySelection(
  original: ProviderModelBindingSettings,
  canonicalModelId: string,
  remoteModelId: string,
  protocol: BindingProtocol,
  compatibility: BindingCompatibility,
  selectionChanged: boolean,
  operations: GenerationOperation[],
): ProviderModelBindingSettings {
  if (!selectionChanged && canonicalModelId === original.canonical_model_id) {
    return {
      ...original,
      remote_model_id: remoteModelId,
      operations: normalizedOperations(operations),
    };
  }
  return {
    ...bindingFromTemplate(
      original.id,
      canonicalModelId,
      remoteModelId,
      bindingTemplateForCompatibility(canonicalModelId, protocol, compatibility),
      operations,
    ),
    append_aspect_ratio_prompt: Boolean(original.append_aspect_ratio_prompt),
  };
}

export function normalizeProviderBindings(
  bindings: unknown,
  providerId = "provider",
): ProviderModelBindingSettings[] {
  if (!Array.isArray(bindings)) return [];
  const seen = new Set<string>();
  return bindings.filter((item): item is Record<string, unknown> => Boolean(item && typeof item === "object"))
    .map((item, index) => {
      let id = slug(item.id, `${providerId}-binding-${index + 1}`);
      while (seen.has(id)) id = `${id}-${index + 1}`;
      seen.add(id);
      const fallbackProtocol = availableProtocolsForModel(String(item.canonical_model_id || ""))[0];
      const fallbackTemplate = fallbackProtocol
        ? BINDING_TEMPLATES[bindingTemplateForProtocol(String(item.canonical_model_id || ""), fallbackProtocol)]
        : null;
      return {
        id,
        canonical_model_id: String(item.canonical_model_id || "").trim(),
        remote_model_id: String(item.remote_model_id || "").trim(),
        protocol_profile: String(item.protocol_profile || fallbackTemplate?.protocol_profile || "").trim(),
        parameter_codec: String(item.parameter_codec || fallbackTemplate?.parameter_codec || "").trim(),
        operations: normalizedOperations(item.operations),
        append_aspect_ratio_prompt: Boolean(item.append_aspect_ratio_prompt),
      };
    });
}

export interface ProviderBindingOverlap {
  firstBindingId: string;
  secondBindingId: string;
  canonicalModelId: string;
  operation: GenerationOperation;
}

export function validateProviderBindingOverlaps(
  bindings: ProviderModelBindingSettings[],
): ProviderBindingOverlap | null {
  const claimed = new Map<string, string>();
  for (const binding of bindings) {
    for (const operation of binding.operations) {
      const key = `${binding.canonical_model_id}\u0000${operation}`;
      const firstBindingId = claimed.get(key);
      if (firstBindingId) {
        return {
          firstBindingId,
          secondBindingId: binding.id,
          canonicalModelId: binding.canonical_model_id,
          operation,
        };
      }
      claimed.set(key, binding.id);
    }
  }
  return null;
}

export function suggestedTemplateForModel(modelId: string): BindingTemplateId {
  const protocol = availableProtocolsForModel(modelId)[0];
  if (!protocol) throw new Error("unsupported_binding_protocol");
  return bindingTemplateForProtocol(modelId, protocol);
}

export function bindingTemplateSuggestion(templateId: BindingTemplateId): {
  base_url: string;
} {
  const template = BINDING_TEMPLATES[templateId];
  return { base_url: template.base_url };
}

export function isBindingTemplateBaseUrl(value: string): boolean {
  const normalized = String(value || "").trim().replace(/\/+$/, "");
  return Object.values(BINDING_TEMPLATES).some(
    (template) => template.base_url.replace(/\/+$/, "") === normalized,
  );
}

function option(value: string, label: string, selected: boolean): HTMLOptionElement {
  const element = document.createElement("option");
  element.value = value;
  element.textContent = label;
  element.selected = selected;
  return element;
}

export function renderProviderBindingCards(
  container: HTMLElement | null,
  bindings: ProviderModelBindingSettings[],
  models: CatalogModel[],
  providerId: string,
  defaults: Record<string, string>,
): void {
  if (!container) return;
  destroyThemedSelects(container);
  const normalizedBindings = normalizeProviderBindings(bindings, providerId);
  const cards = normalizedBindings.map((binding, index) => {
    const card = document.createElement("fieldset");
    card.className = "provider-binding-card";
    card.dataset.bindingId = binding.id;
    const legend = document.createElement("legend");
    legend.textContent = `模型绑定 ${index + 1}`;
    const remove = document.createElement("button");
    remove.type = "button";
    remove.className = "ghost-button danger-button provider-binding-remove";
    remove.dataset.removeProviderBinding = binding.id;
    remove.dataset.i18n = "apiSettings.removeBinding";
    remove.textContent = translate("apiSettings.removeBinding");
    const grid = document.createElement("div");
    grid.className = "provider-binding-grid";

    const modelField = document.createElement("div");
    modelField.className = "field";
    const modelLabel = document.createElement("span");
    modelLabel.id = `provider-binding-${binding.id}-model-label`;
    modelLabel.textContent = "具体型号";
    const modelSelect = document.createElement("select");
    modelSelect.className = "control";
    modelSelect.dataset.bindingModel = "";
    modelSelect.setAttribute("aria-labelledby", modelLabel.id);
    models.forEach((model) => modelSelect.append(option(model.id, model.display_name, model.id === binding.canonical_model_id)));
    modelField.append(modelLabel, modelSelect);

    const protocolField = document.createElement("div");
    protocolField.className = "field";
    const protocolLabel = document.createElement("span");
    protocolLabel.id = `provider-binding-${binding.id}-protocol-label`;
    protocolLabel.textContent = "协议";
    const protocolSelect = document.createElement("select");
    protocolSelect.className = "control";
    protocolSelect.dataset.bindingProtocol = "";
    protocolSelect.setAttribute("aria-labelledby", protocolLabel.id);
    const selectedProtocol = protocolForBinding(binding);
    const selectedModel = models.find((model) => model.id === binding.canonical_model_id);
    card.dataset.bindingModelOperations = resolvedBindingOperations(
      binding,
      normalizedBindings,
      selectedModel,
    ).join(",");
    availableProtocolsForModel(binding.canonical_model_id).forEach((protocol) => {
      protocolSelect.append(option(protocol, BINDING_PROTOCOL_LABELS[protocol], protocol === selectedProtocol));
    });
    protocolField.append(protocolLabel, protocolSelect);

    const remoteField = document.createElement("label");
    remoteField.className = "field provider-binding-remote-model";
    remoteField.append(document.createTextNode("中转站模型名称"));
    const remoteInput = document.createElement("input");
    remoteInput.className = "control";
    remoteInput.type = "text";
    remoteInput.autocomplete = "off";
    remoteInput.value = binding.remote_model_id;
    remoteInput.dataset.bindingRemoteModel = "";
    remoteInput.placeholder = "例如 vendor/model.name:version-1";
    remoteField.append(remoteInput);

    const compatibilityField = document.createElement("div");
    compatibilityField.className = "field provider-binding-compatibility";
    const compatibilityLabel = document.createElement("span");
    compatibilityLabel.id = `provider-binding-${binding.id}-compatibility-label`;
    compatibilityLabel.textContent = "兼容层";
    const compatibilitySelect = document.createElement("select");
    compatibilitySelect.className = "control";
    compatibilitySelect.dataset.bindingCompatibility = "";
    compatibilitySelect.setAttribute("aria-labelledby", compatibilityLabel.id);
    const selectedCompatibility = compatibilityForBinding(binding);
    availableCompatibilityLayers(binding.canonical_model_id, selectedProtocol).forEach((compatibility) => {
      compatibilitySelect.append(option(
        compatibility,
        BINDING_COMPATIBILITY_LABELS[compatibility],
        compatibility === selectedCompatibility,
      ));
    });
    compatibilityField.append(compatibilityLabel, compatibilitySelect);

    const ratioPromptField = document.createElement("label");
    ratioPromptField.className = "provider-binding-toggle provider-binding-ratio-prompt";
    ratioPromptField.dataset.i18nAttr = "title:apiSettings.appendRatioPrompt";
    const ratioPromptInput = document.createElement("input");
    ratioPromptInput.type = "checkbox";
    ratioPromptInput.dataset.bindingRatioPrompt = "";
    ratioPromptInput.checked = Boolean(binding.append_aspect_ratio_prompt);
    const ratioPromptLabel = document.createElement("span");
    ratioPromptLabel.dataset.i18n = "apiSettings.appendRatioPrompt";
    ratioPromptLabel.textContent = translate("apiSettings.appendRatioPrompt");
    ratioPromptField.append(ratioPromptInput, ratioPromptLabel);

    const defaultField = document.createElement("label");
    defaultField.className = "provider-binding-toggle provider-binding-default";
    defaultField.dataset.i18nAttr = "title:apiSettings.defaultProviderForModel";
    const defaultInput = document.createElement("input");
    defaultInput.type = "checkbox";
    defaultInput.dataset.bindingDefault = "";
    defaultInput.checked = defaults[binding.canonical_model_id] === providerId;
    const defaultLabel = document.createElement("span");
    defaultLabel.dataset.i18n = "apiSettings.defaultProviderForModel";
    defaultLabel.textContent = translate("apiSettings.defaultProviderForModel");
    defaultField.append(defaultInput, defaultLabel);

    const footer = document.createElement("div");
    footer.className = "provider-binding-footer";
    const footerSettings = document.createElement("div");
    footerSettings.className = "provider-binding-footer-settings";
    footerSettings.append(ratioPromptField, defaultField);
    footer.append(footerSettings, remove);

    card.dataset.bindingOriginalModelId = binding.canonical_model_id;
    card.dataset.bindingOriginalProtocolProfile = binding.protocol_profile;
    card.dataset.bindingOriginalParameterCodec = binding.parameter_codec;
    card.dataset.bindingProtocolChanged = "false";
    card.dataset.bindingCompatibilityChanged = "false";
    grid.append(modelField, protocolField, remoteField, compatibilityField, footer);
    card.append(legend, grid);
    return card;
  });
  container.replaceChildren(...cards);
  container.querySelectorAll<HTMLSelectElement>("[data-binding-model], [data-binding-protocol], [data-binding-compatibility]")
    .forEach((select) => mountThemedSelect(select));
}

export function readProviderBindingCards(container: HTMLElement | null): Array<ProviderModelBindingSettings & { is_default: boolean }> {
  if (!container) return [];
  return [...container.querySelectorAll<HTMLElement>("[data-binding-id]")].map((card) => {
    const modelId = card.querySelector<HTMLSelectElement>("[data-binding-model]")?.value || "";
    const remoteModelId = card.querySelector<HTMLInputElement>("[data-binding-remote-model]")?.value || "";
    const protocol = (card.querySelector<HTMLSelectElement>("[data-binding-protocol]")?.value
      || availableProtocolsForModel(modelId)[0]) as BindingProtocol;
    const compatibility = (card.querySelector<HTMLSelectElement>("[data-binding-compatibility]")?.value
      || "standard") as BindingCompatibility;
    const operations = normalizedOperations(
      String(card.dataset.bindingModelOperations || "").split(","),
    );
    const original: ProviderModelBindingSettings = {
      id: card.dataset.bindingId || "binding",
      canonical_model_id: card.dataset.bindingOriginalModelId || modelId,
      remote_model_id: remoteModelId,
      protocol_profile: card.dataset.bindingOriginalProtocolProfile || "",
      parameter_codec: card.dataset.bindingOriginalParameterCodec || "",
      operations,
      append_aspect_ratio_prompt: Boolean(
        card.querySelector<HTMLInputElement>("[data-binding-ratio-prompt]")?.checked
      ),
    };
    return {
      ...bindingForCompatibilitySelection(
        original,
        modelId,
        remoteModelId,
        protocol,
        compatibility,
        card.dataset.bindingProtocolChanged === "true"
          || card.dataset.bindingCompatibilityChanged === "true",
        operations,
      ),
      is_default: Boolean(card.querySelector<HTMLInputElement>("[data-binding-default]")?.checked),
    };
  });
}

import type { BindingCompatibility, BindingProtocol } from "./provider-model-bindings";
import {
  BINDING_COMPATIBILITY_LABELS,
  BINDING_PROTOCOL_LABELS,
  availableCompatibilityLayers,
  availableProtocolsForModel,
  bindingTemplateForCompatibility,
  bindingTemplateForProtocol,
  bindingTemplateSuggestion,
  isBindingTemplateBaseUrl,
  remoteModelAfterSelection
} from "./provider-model-bindings";
import { syncThemedSelect } from "./themed-select";

interface BindingEditorContext {
  state: { readonly apiProviderDraftIsNew: boolean; readonly generationCatalog?: { models: Array<{ id: string; official_model_id?: string; operations?: string[] }> } | null };
  els: { apiBaseUrl: HTMLInputElement; apiProviderBindings: HTMLElement | null };
  updateApiRequestEndpointPreview(): void;
}

export function handleProviderBindingEditorChange(event: Event, context: BindingEditorContext): void {
  const { state, els, updateApiRequestEndpointPreview } = context;
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
    const previousModelId = card.dataset.bindingPreviousModelId || card.dataset.bindingOriginalModelId || "";
    const previousModel = state.generationCatalog?.models.find((item: any) => item.id === previousModelId);
    if (remoteInput) remoteInput.value = remoteModelAfterSelection(
      remoteInput.value,
      previousModel?.official_model_id || previousModelId,
      model?.official_model_id || modelId,
    );
    card.dataset.bindingPreviousModelId = modelId;
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

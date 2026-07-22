import type { CatalogModel, GenerationCatalog, ModelFamilyId } from "./types";
import { getLegacyBridge } from "./state";
import { renderProviderSelection } from "./provider-selection";
import {
  migratePortableModelDraft,
  restoreCurrentModelParameterDraft,
  saveCurrentModelParameterDraft,
} from "./model-parameter-drafts";
import { modelFamilyBrandMarkHtml } from "./model-family-icons";
import { refreshSegmentedIndicators } from "./segmented-indicator";

export function modelsForFamily(catalog: GenerationCatalog, familyId: ModelFamilyId): CatalogModel[] {
  return catalog.models.filter((model) => model.family_id === familyId);
}

export function usesExpandedConcreteModelOptions(models: CatalogModel[]): boolean {
  return models.length > 1;
}

function familyOptionButtons(): HTMLButtonElement[] {
  const options = getLegacyBridge().els.modelFamilyOptions as HTMLElement | null;
  return options ? Array.from(options.querySelectorAll<HTMLButtonElement>("[data-family-id]")) : [];
}

function focusFamilyOption(familyId: ModelFamilyId): void {
  window.requestAnimationFrame(() => {
    familyOptionButtons().find((button) => button.dataset.familyId === familyId)?.focus();
  });
}

export function selectModelFamily(familyId: ModelFamilyId): void {
  const { state } = getLegacyBridge();
  const catalog = state.generationCatalog;
  const family = catalog?.families.find((item) => item.id === familyId);
  if (!catalog || !family) return;
  const models = modelsForFamily(catalog, familyId);
  const remembered = state.lastModelByFamily[familyId];
  const model = models.find((item) => item.id === remembered) || models[0];
  if (!model) return;
  saveCurrentModelParameterDraft();
  state.selectedFamilyId = familyId;
  state.selectedModelId = model.id;
  state.lastModelByFamily[familyId] = model.id;
  getLegacyBridge().methods.persistModelSelection?.();
  renderModelSelectors();
  renderProviderSelection();
  restoreCurrentModelParameterDraft();
  getLegacyBridge().methods.reconcileTaskParameterInspection?.();
  getLegacyBridge().methods.updateModeSpecificSettings?.();
  getLegacyBridge().methods.refreshOutputSettingsLock?.();
  getLegacyBridge().methods.updateRequestPreview?.();
  focusFamilyOption(familyId);
}

export function selectConcreteModel(modelId: string): void {
  const { state } = getLegacyBridge();
  const model = state.generationCatalog?.models.find((item) => item.id === modelId);
  if (!model) return;
  const sourceModel = state.generationCatalog?.models.find((item) => item.id === state.selectedModelId);
  const familyChanged = sourceModel?.family_id !== model.family_id;
  saveCurrentModelParameterDraft();
  if (sourceModel?.family_id === model.family_id) {
    state.parameterDraftsByModel[model.id] = migratePortableModelDraft(
      sourceModel,
      model,
      state.parameterDraftsByModel[sourceModel.id] || {},
      state.parameterDraftsByModel[model.id] || {},
    );
  }
  state.selectedModelId = model.id;
  state.selectedFamilyId = model.family_id;
  state.lastModelByFamily[model.family_id] = model.id;
  getLegacyBridge().methods.persistModelSelection?.();
  if (familyChanged) renderModelSelectors();
  else updateConcreteModelSelection(model.id);
  renderProviderSelection();
  restoreCurrentModelParameterDraft();
  getLegacyBridge().methods.reconcileTaskParameterInspection?.();
  getLegacyBridge().methods.updateModeSpecificSettings?.();
  getLegacyBridge().methods.refreshOutputSettingsLock?.();
  getLegacyBridge().methods.updateRequestPreview?.();
}

export function updateConcreteModelSelection(modelId: string): void {
  const { state, els } = getLegacyBridge();
  const modelSelect = els.concreteModelSelect as HTMLSelectElement | null;
  const modelOptions = els.concreteModelOptions as HTMLElement | null;
  if (modelSelect) modelSelect.value = modelId;
  modelOptions?.querySelectorAll<HTMLButtonElement>("[data-model-id]").forEach((button) => {
    const active = button.dataset.modelId === modelId;
    button.classList.toggle("active", active);
    button.setAttribute("aria-pressed", active ? "true" : "false");
  });
  const model = state.generationCatalog?.models.find((item) => item.id === modelId);
  if (modelSelect) modelSelect.title = model?.display_name || "";
  refreshSegmentedIndicators();
}

export function renderModelSelectors(): void {
  const { state, els } = getLegacyBridge();
  const catalog = state.generationCatalog;
  const familyOptions = els.modelFamilyOptions as HTMLElement | null;
  const modelSelect = els.concreteModelSelect as HTMLSelectElement | null;
  const modelOptions = els.concreteModelOptions as HTMLElement | null;
  const modelField = modelSelect?.closest(".concrete-model-field") as HTMLElement | null;
  if (!catalog) {
    if (familyOptions) {
      familyOptions.replaceChildren();
      familyOptions.setAttribute("aria-disabled", "true");
    }
    if (modelSelect) modelSelect.disabled = true;
    modelOptions?.replaceChildren();
    modelOptions?.classList.add("hidden");
    modelField?.classList.add("hidden");
    return;
  }
  const selectedFamily = catalog.families.find((family) => family.id === state.selectedFamilyId);
  if (familyOptions) {
    // Keep the shared indicator mounted so its transform can interpolate from
    // the previous family instead of being recreated at the destination.
    familyOptions.querySelectorAll<HTMLElement>("[data-family-id]").forEach((item) => item.remove());
    familyOptions.removeAttribute("aria-disabled");
    catalog.families.forEach((family) => {
      const item = document.createElement("button");
      item.type = "button";
      item.role = "radio";
      const active = family.id === state.selectedFamilyId;
      item.className = `model-family-segment radio-btn${active ? " active" : ""}`;
      item.dataset.familyId = family.id;
      item.title = family.display_name;
      item.setAttribute("aria-label", family.display_name);
      item.setAttribute("aria-checked", active ? "true" : "false");
      const icon = document.createElement("span");
      icon.className = `model-family-segment-icon model-family-segment-icon-${family.id}`;
      icon.setAttribute("aria-hidden", "true");
      icon.innerHTML = modelFamilyBrandMarkHtml(family.id, "model-family-brand-mark");
      const label = document.createElement("span");
      label.className = "model-family-segment-label";
      label.textContent = family.short_name || family.display_name;
      item.append(icon, label);
      familyOptions.append(item);
    });
  }
  if (modelSelect && selectedFamily) {
    const familyModels = modelsForFamily(catalog, selectedFamily.id);
    const expanded = usesExpandedConcreteModelOptions(familyModels);
    modelField?.classList.toggle("hidden", !expanded);
    modelSelect.replaceChildren();
    familyModels.forEach((model) => {
      const option = document.createElement("option");
      option.value = model.id;
      option.textContent = model.display_name;
      option.title = model.display_name;
      modelSelect.append(option);
    });
    modelSelect.value = state.selectedModelId || "";
    modelSelect.disabled = modelSelect.options.length === 0;
    modelSelect.title = catalog.models.find((model) => model.id === state.selectedModelId)?.display_name || "";
    modelSelect.classList.toggle("hidden", expanded);
    if (modelOptions) {
      modelOptions.replaceChildren();
      modelOptions.classList.toggle("hidden", !expanded);
      if (expanded) {
        familyModels.forEach((model) => {
          const button = document.createElement("button");
          const active = model.id === state.selectedModelId;
          button.type = "button";
          button.className = `radio-btn${active ? " active" : ""}`;
          button.dataset.modelId = model.id;
          button.textContent = model.display_name;
          button.title = model.display_name;
          button.setAttribute("aria-pressed", active ? "true" : "false");
          button.addEventListener("click", () => {
            if (!button.classList.contains("active")) selectConcreteModel(model.id);
          });
          modelOptions.append(button);
        });
      }
    }
  }
  refreshSegmentedIndicators();
}

export function handleModelFamilyOptionsKeydown(event: KeyboardEvent): void {
  const buttons = familyOptionButtons();
  const current = (event.target as HTMLElement | null)?.closest?.("[data-family-id]") as HTMLButtonElement | null;
  const index = buttons.indexOf(current || (document.activeElement as HTMLButtonElement));
  const delta = event.key === "ArrowDown" || event.key === "ArrowRight"
    ? 1
    : event.key === "ArrowUp" || event.key === "ArrowLeft" ? -1 : 0;
  const targetIndex = event.key === "Home"
    ? 0
    : event.key === "End"
      ? buttons.length - 1
      : delta && buttons.length ? (index + delta + buttons.length) % buttons.length : -1;
  if (targetIndex < 0 || !buttons.length) return;
  event.preventDefault();
  const target = buttons[targetIndex];
  const familyId = target?.dataset.familyId as ModelFamilyId | undefined;
  if (!familyId) return;
  selectModelFamily(familyId);
}

export function initModelSelectionFeature(): void {
  Object.assign(getLegacyBridge().methods, {
    handleModelFamilyOptionsKeydown,
    renderModelSelectors,
    selectConcreteModel,
    selectModelFamily,
    updateConcreteModelSelection,
  });
}

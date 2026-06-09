import { getLegacyBridge } from "./state";
import { updateRequestPreview } from "./output-controls";
import { translate } from "./i18n";

export const DEFAULT_MAIN_MODEL = "gpt-5.4-mini";
export const MAIN_MODEL_OPTIONS = ["gpt-5.5", "gpt-5.4", "gpt-5.4-mini", "gpt-5.3-codex", "gpt-5.2"];
export const RETIRED_MAIN_MODEL_OPTIONS = new Set(["gpt-5.3-codex-spark"]);
export const MAIN_MODEL_STORAGE_KEY = "codex-image-main-model";

const bridge = getLegacyBridge();
const state = bridge.state;
const els = bridge.els;

function legacyMethod(name: string, ...args: any[]): any {
  const method = getLegacyBridge().methods[name];
  if (typeof method !== "function") {
    throw new Error("Legacy method " + name + " is not initialized");
  }
  return method(...args);
}

function escapeHtml(value: any): string { return legacyMethod("escapeHtml", value); }

export function mainModelOptionsForQuery(query: any): string[] {
  const normalized = String(query || "").trim().toLowerCase();
  if (!normalized) return MAIN_MODEL_OPTIONS.slice();
  return MAIN_MODEL_OPTIONS.filter((model) => model.toLowerCase().includes(normalized));
}

export function openMainModelCombobox({ showAll = false }: any = {}): void {
  if (!els.mainModel || !els.mainModelOptions || !els.mainModelCombobox) return;
  if (showAll) {
    state.mainModelShowAllOptions = true;
    const selectedIndex = MAIN_MODEL_OPTIONS.indexOf(currentMainModel());
    state.mainModelOptionIndex = selectedIndex >= 0 ? selectedIndex : 0;
  }
  state.mainModelComboboxOpen = true;
  renderMainModelOptions();
  els.mainModelOptions.classList.remove("hidden");
  els.mainModelCombobox.setAttribute("aria-expanded", "true");
  els.mainModel.setAttribute("aria-expanded", "true");
}

export function closeMainModelCombobox(): void {
  state.mainModelComboboxOpen = false;
  state.mainModelOptionIndex = 0;
  state.mainModelShowAllOptions = false;
  els.mainModelOptions?.classList.add("hidden");
  els.mainModelCombobox?.setAttribute("aria-expanded", "false");
  els.mainModel?.setAttribute("aria-expanded", "false");
  els.mainModel?.removeAttribute("aria-activedescendant");
}

export function renderMainModelOptions(): void {
  if (!els.mainModel || !els.mainModelOptions) return;
  const query = state.mainModelShowAllOptions ? "" : els.mainModel.value;
  const options = mainModelOptionsForQuery(query);
  state.mainModelOptionIndex = Math.min(Math.max(0, state.mainModelOptionIndex), Math.max(0, options.length - 1));
  if (!options.length) {
    els.mainModelOptions.innerHTML = `<div class="model-combobox-empty" role="option" aria-disabled="true">${escapeHtml(translate("output.mainModelCustomForInput"))}</div>`;
    els.mainModel.removeAttribute("aria-activedescendant");
    return;
  }
  els.mainModelOptions.innerHTML = options.map((model, index) => {
    const active = index === state.mainModelOptionIndex;
    const selected = model === currentMainModel();
    return `
      <button
        id="mainModelOption-${index}"
        class="model-combobox-option${active ? " active" : ""}${selected ? " selected" : ""}"
        type="button"
        role="option"
        aria-selected="${selected ? "true" : "false"}"
        data-main-model-option="${escapeHtml(model)}"
      >${escapeHtml(model)}</button>
    `;
  }).join("");
  els.mainModel.setAttribute("aria-activedescendant", `mainModelOption-${state.mainModelOptionIndex}`);
  els.mainModelOptions.querySelectorAll("[data-main-model-option]").forEach((button: any) => {
    button.addEventListener("mousedown", (event: any) => event.preventDefault());
    button.addEventListener("click", () => selectMainModelOption(button.dataset.mainModelOption));
  });
}

export function selectMainModelOption(model: any): void {
  if (!els.mainModel || !model) return;
  els.mainModel.value = model;
  persistMainModel();
  updateRequestPreview();
  closeMainModelCombobox();
  els.mainModel.focus();
}

export function handleMainModelKeydown(event: any): void {
  if (!els.mainModelOptions) return;
  const options = mainModelOptionsForQuery(els.mainModel?.value || "");
  if (event.key === "ArrowDown") {
    event.preventDefault();
    if (!state.mainModelComboboxOpen) {
      state.mainModelShowAllOptions = true;
      state.mainModelOptionIndex = 0;
      openMainModelCombobox();
      return;
    }
    if (options.length) state.mainModelOptionIndex = (state.mainModelOptionIndex + 1) % options.length;
    renderMainModelOptions();
  } else if (event.key === "ArrowUp") {
    event.preventDefault();
    if (!state.mainModelComboboxOpen) {
      state.mainModelShowAllOptions = true;
      state.mainModelOptionIndex = Math.max(0, MAIN_MODEL_OPTIONS.length - 1);
      openMainModelCombobox();
      return;
    }
    if (options.length) state.mainModelOptionIndex = (state.mainModelOptionIndex - 1 + options.length) % options.length;
    renderMainModelOptions();
  } else if (event.key === "Enter" && state.mainModelComboboxOpen && options.length) {
    event.preventDefault();
    selectMainModelOption(options[state.mainModelOptionIndex]);
  } else if (event.key === "Escape") {
    closeMainModelCombobox();
  }
}

export function currentMainModel(): string {
  return (els.mainModel?.value || DEFAULT_MAIN_MODEL).trim() || DEFAULT_MAIN_MODEL;
}

export function restoreMainModel(): void {
  if (!els.mainModel) return;
  try {
    const saved = localStorage.getItem(MAIN_MODEL_STORAGE_KEY);
    let model = (saved || DEFAULT_MAIN_MODEL).trim() || DEFAULT_MAIN_MODEL;
    if (RETIRED_MAIN_MODEL_OPTIONS.has(model)) {
      model = DEFAULT_MAIN_MODEL;
      localStorage.setItem(MAIN_MODEL_STORAGE_KEY, model);
    }
    els.mainModel.value = model;
  } catch {
    els.mainModel.value = DEFAULT_MAIN_MODEL;
  }
  renderMainModelOptions();
}

export function persistMainModel(): void {
  if (!els.mainModel) return;
  try {
    localStorage.setItem(MAIN_MODEL_STORAGE_KEY, currentMainModel());
  } catch {
    // Browser storage may be unavailable in restricted contexts.
  }
}

import type { CatalogModel } from "./types";
import { getLegacyBridge } from "./state";
import { mountThemedSelect, syncThemedSelect } from "./themed-select";

/** Keep the familiar controls, with choices taken from the selected manifest. */
export function syncGptModelControls(model: CatalogModel): void {
  const { els, state } = getLegacyBridge();
  const quality = model.parameters.find(parameter => parameter.id === "gpt.quality");
  const format = model.parameters.find(parameter => parameter.id === "output.format");
  const extended = !!quality?.allowed_values.includes("max");
  const complexity = model.parameters.some(parameter => parameter.id === "gpt.complexity");
  const root = document.getElementById("outputFileSettings");
  if (!root) return;
  root?.classList.toggle("extended-quality", extended);
  root?.classList.toggle("image26-controls", complexity);
  document.getElementById("complexityField")?.classList.toggle("hidden", !complexity);
  if (els.complexity) els.complexity.disabled = !complexity;
  document.querySelectorAll<HTMLButtonElement>("#qualityGroup [data-val]").forEach(button => {
    const supported = quality?.allowed_values.includes(button.dataset.val) ?? true;
    button.hidden = !supported;
    button.classList.toggle("hidden", !supported);
    button.disabled = !supported;
  });
  for (const option of Array.from((els.quality as HTMLSelectElement)?.options || [])) {
    option.disabled = !(quality?.allowed_values.includes(option.value) ?? true);
  }
  const select = els.outputFormat as HTMLSelectElement | null;
  if (!select) return;
  for (const option of Array.from(select.options)) {
    const supported = format?.allowed_values.includes(option.value) ?? ["png", "jpeg", "webp"].includes(option.value);
    option.hidden = !supported;
    option.disabled = !supported || (state.mode === "edit" && ["svg", "gif"].includes(option.value));
  }
  if (select.selectedOptions[0]?.disabled) select.value = "png";
  // Mount once. The existing radio buttons remain available for older models.
  if (complexity) mountThemedSelect(select);
  select.closest(".themed-select")?.classList.toggle("hidden", !complexity);
  els.outputFormatGroup?.classList.toggle("hidden", complexity);
  syncThemedSelect(select);
}

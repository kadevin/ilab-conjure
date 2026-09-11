import { currentGenerationSelection } from "./generation-request";
import { getLegacyBridge } from "./state";
import { formatTranslation, translate } from "./i18n";
export function updateExecutionSummary(): void {
  const element = document.getElementById("executionSummary");
  if (!element) return;
  const selection = currentGenerationSelection();
  const { state } = getLegacyBridge();
  const model = state.generationCatalog?.models.find(item => item.id === selection.canonicalModelId);
  const provider = state.generationCatalog?.providers.find(item => item.id === selection.providerId);
  const p = selection.parameters;
  const size = String(p["canvas.size"] || p["canvas.aspect_ratio"] || "");
  const resolution = String(p["output.resolution"] || p["canvas.resolution"] || "");
  element.textContent = [translate("ux.execution"), model?.display_name || translate("modelSelection.providerUnavailable"), provider?.name, size, resolution, formatTranslation("ux.imageCount", { count: Number(p["output.count"] || 1) }), p["gpt.background"] === "transparent" ? translate("output.transparentBackground") : ""].filter(Boolean).join(" · ");
  element.dataset.modelId = selection.canonicalModelId;
  element.dataset.providerId = selection.providerId;
  element.dataset.parameters = JSON.stringify(p);
}

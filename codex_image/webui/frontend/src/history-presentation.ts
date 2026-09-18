import { taskOutputRecords } from "./history-detail-media";
import type { HistoryFilterKey, HistoryTask } from "./history-types";
import { formatTranslation, translate } from "./i18n";
import { localizedTaskStatus } from "./task-recovery";
import { submittedPromptForTask } from "./transparency-status";

const HISTORY_RATIO_OTHER_VALUE = "__other__";

const HISTORY_THUMBNAIL_CACHE_VERSION = "thumb-768-fit";

export function escapeHtml(value: unknown): string {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

export function formatDate(value: string): string {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value.slice(0, 16).replace("T", " ");
  return date.toLocaleString(undefined, { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" });
}

export function setText(element: HTMLElement | null, text: string): void {
  if (element) element.textContent = text;
}

export function truncateText(value: unknown, limit: number): string {
  const text = String(value || "").replace(/\s+/g, " ").trim();
  return text.length <= limit ? text : text.slice(0, limit - 1).trimEnd() + "…";
}

export function historyFilterAttribute(key: HistoryFilterKey): string {
  return key.replace(/_/g, "-");
}

export function facetDisplayValue(key: HistoryFilterKey, value: string): string {
  if (key === "mode") {
    if (value === "generate") return translate("history.type.textToImage");
    if (value === "edit") return translate("history.type.imageToImage");
  }
  if (key === "prompt_mode") {
    if (value === "strict") return translate("history.promptMode.strict");
    if (value === "original") return translate("history.promptMode.original");
    if (value === "off") return translate("history.promptMode.off");
  }
  if (key === "quality") {
    if (value === "high") return translate("history.quality.high");
    if (value === "medium") return translate("history.quality.medium");
    if (value === "low") return translate("history.quality.low");
    if (value === "auto") return translate("history.quality.auto");
  }
  if (key === "orientation") {
    if (value === "portrait") return translate("output.portrait");
    if (value === "landscape") return translate("output.landscape");
    if (value === "square") return translate("output.square");
  }
  if (key === "ratio" && value === HISTORY_RATIO_OTHER_VALUE) return translate("history.ratioOther");
  return value;
}

export function historyTaskAccessibleLabel(task: HistoryTask): string {
  const title = String(task.prompt_preview || task.mode || task.task_id)
    .replace(/\s+/g, " ")
    .trim();
  const conciseTitle = title.length > 96 ? `${title.slice(0, 96)}…` : title;
  return [
    conciseTitle,
    formatDate(task.created_at),
    localizedTaskStatus(task.status || ""),
  ].filter(Boolean).join(" · ");
}

export function historyTaskStackDepth(imageCount: number): number {
  if (!Number.isFinite(imageCount) || imageCount <= 1) return 0;
  return Math.min(3, imageCount - 1);
}

export function historyTaskStackLayers(stackDepth: number): string {
  if (!Number.isFinite(stackDepth) || stackDepth <= 0) return "";
  return Array.from({ length: stackDepth }, (_, index) => {
    const layer = index + 1;
    return `<span class="history-task-stack-layer" data-history-stack-layer="${String(layer)}" aria-hidden="true"></span>`;
  }).join("");
}

export function historyTaskSourceLabel(task: Partial<HistoryTask> & Record<string, any>): string {
  const provider = String(
    task.provider
    || task.api_provider_name
    || task.params?.api_provider_name
    || task.request?.webui_api_provider_name
    || task.request?.api_provider_name
    || "",
  ).trim();
  const backend = historyBackendDisplayLabel(task.backend);
  const channel = historyBackendChannelLabel(task.backend);
  if (provider) return [provider, channel].filter(Boolean).join(" · ");
  return backend;
}

export function historyBackendDisplayLabel(backend: unknown): string {
  const value = String(backend || "").trim();
  if (value === "codex_images") return "Codex Image";
  if (value === "codex_responses") return "Codex Responses";
  if (value === "openai_images") return "API Image";
  if (value === "openai_responses") return "API Responses";
  return value;
}

export function historyBackendChannelLabel(backend: unknown): string {
  const value = String(backend || "").trim();
  if (value === "openai_images") return "Image";
  if (value === "openai_responses") return "Responses";
  return "";
}

export function historyThumbnailRatioStyle(task: HistoryTask): string {
  const fromSize = parseAspectRatioParts(task.size, "x");
  const fromRatio = fromSize || parseAspectRatioParts(task.ratio, ":");
  if (!fromRatio) return "";
  const [width, height] = fromRatio;
  const ratio = Math.min(3.2, Math.max(0.42, width / height));
  return `style="--history-task-thumb-ratio: ${width} / ${height}; --history-task-card-ratio: ${ratio.toFixed(4)}"`;
}

export function parseAspectRatioParts(value: unknown, separator: "x" | ":"): [number, number] | null {
  const text = String(value || "").trim().toLowerCase();
  const pattern = separator === "x" ? /^(\d+)\s*x\s*(\d+)$/ : /^(\d+)\s*:\s*(\d+)$/;
  const match = text.match(pattern);
  if (!match) return null;
  const width = Number.parseInt(match[1] || "", 10);
  const height = Number.parseInt(match[2] || "", 10);
  if (!Number.isFinite(width) || !Number.isFinite(height) || width <= 0 || height <= 0) return null;
  return [width, height];
}

export function formatHistorySizeLabel(value: unknown): string {
  return String(value || "").trim().replace(/^(\d+)\s*x\s*(\d+)$/i, "$1 x $2");
}

export function historyThumbnailUrl(task: HistoryTask): string {
  const url = String(task.thumbnail_url || "");
  if (!url) return "";
  const staticThumbMatch = url.match(/(?:^|\/)(\d{14}-[a-f0-9]+)-image-(\d+)-thumb\.[a-z0-9]+(?:[?#].*)?$/i);
  if (url.includes("/outputs/thumbnails/") && staticThumbMatch && staticThumbMatch[1] === task.task_id) {
    const outputIndex = staticThumbMatch[2] || "1";
    return versionHistoryThumbnailUrl(`/api/tasks/${encodeURIComponent(task.task_id)}/outputs/${encodeURIComponent(outputIndex)}/thumbnail`);
  }
  return versionHistoryThumbnailUrl(url);
}

export function versionHistoryThumbnailUrl(url: string): string {
  if (!url.startsWith("/api/tasks/") || !url.includes("/thumbnail")) return url;
  const separator = url.includes("?") ? "&" : "?";
  return `${url}${separator}v=${HISTORY_THUMBNAIL_CACHE_VERSION}`;
}

export function detailTitle(task: any): string {
  return truncateText(task.prompt_preview || task.prompt || task.mode || task.task_id || translate("history.untitled"), 120);
}

export function historyTaskArchived(task: any): boolean {
  return Boolean(task?.archived || task?.archived_at);
}

export function historyTaskDeleteBlocked(task: any): boolean {
  const status = String(task?.status || "");
  return Boolean(task?.local_pending || status === "running" || status === "cancelling" || status === "submitting" || status === "queued");
}

export function historyTaskGeneratedCount(task: any): number {
  const generated = positiveInt(task?.generated_count);
  if (generated !== null) return generated;
  const outputs = Array.isArray(task?.outputs) ? task.outputs.filter((output: any) => output && !output.deleted && output.status !== "failed") : [];
  if (outputs.length) return outputs.length;
  if (Array.isArray(task?.output_urls)) return task.output_urls.filter(Boolean).length;
  return task?.output_url ? 1 : 0;
}

export function historyTaskPromptForClipboard(task: any): string {
  return String(task?.prompt || task?.prompt_preview || task?.prompt_for_model || "").trim();
}

export function promptCompareHtml(task: any): string {
  const originalPrompt = promptTextValue(task.prompt || "");
  const submittedPrompt = promptTextValue(submittedPromptForTask(task));
  const revisedPrompt = revisedPromptText(task);
  const hasDistinctOutputPrompts = hasDistinctOutputRevisedPrompts(task);
  const seen = new Set<string>();
  const panels: string[] = [];
  const addPanel = (kind: string, title: string, text: string): boolean => {
    const value = promptTextValue(text);
    const key = normalizePromptForCompare(value);
    if (!key || seen.has(key)) return false;
    seen.add(key);
    panels.push(promptPanelHtml(kind, title, value));
    return true;
  };

  addPanel("original", translate("history.promptOriginal"), originalPrompt);
  const hasRevisedPanel = hasDistinctOutputPrompts ? false : addPanel("revised", translate("history.promptRevised"), revisedPrompt);
  if (task.generation_snapshot?.transparency_instruction) {
    addPanel("submitted", translate("history.promptSubmittedActual"), submittedPrompt);
  } else if (!hasRevisedPanel) {
    addPanel("submitted", translate("history.promptSubmitted"), submittedPrompt);
  }
  if (hasDistinctOutputPrompts) {
    panels.push(`<p class="history-prompt-note">${escapeHtml(translate("history.outputRevisedPromptNotice"))}</p>`);
  }
  return panels.length ? `<section class="history-prompt-compare" aria-label="${escapeHtml(translate("history.promptCompare"))}">${panels.join("")}</section>` : "";
}

export function promptTextValue(value: unknown): string {
  return String(value || "").trim();
}

export function normalizePromptForCompare(value: string): string {
  return promptTextValue(value).replace(/\s+/g, " ").trim();
}

export function uniquePromptTexts(values: unknown[]): string[] {
  const seen = new Set<string>();
  const result: string[] = [];
  values.forEach((value) => {
    const text = promptTextValue(value);
    const key = normalizePromptForCompare(text);
    if (!key || seen.has(key)) return;
    seen.add(key);
    result.push(text);
  });
  return result;
}

export function revisedPromptText(task: any): string {
  const values: unknown[] = [];
  if (Array.isArray(task.revised_prompts)) values.push(...task.revised_prompts);
  if (task.revised_prompt) values.push(task.revised_prompt);
  if (Array.isArray(task.outputs)) {
    task.outputs.forEach((output: any) => {
      if (output?.revised_prompt) values.push(output.revised_prompt);
    });
  }
  return uniquePromptTexts(values).join("\n\n");
}

export function outputRevisedPromptTexts(task: any): string[] {
  return uniquePromptTexts(taskOutputRecords(task).map((record) => record.revisedPrompt));
}

export function hasDistinctOutputRevisedPrompts(task: any): boolean {
  return outputRevisedPromptTexts(task).length > 1;
}

export function promptPanelHtml(kind: string, title: string, text: string): string {
  return `
    <article class="history-prompt-panel">
      <div class="history-prompt-panel-header">
        <h3>${escapeHtml(title)}</h3>
        <button
          class="ghost-button text-sm history-prompt-copy"
          type="button"
          data-history-copy-prompt-kind="${escapeHtml(kind)}"
          aria-label="${escapeHtml(formatTranslation("history.copyPromptPanel", { title }))}"
        >${escapeHtml(translate("history.copyPromptShort"))}</button>
      </div>
      <div class="history-detail-prompt">${escapeHtml(text || translate("history.promptEmpty"))}</div>
    </article>
  `;
}

export function positiveInt(value: unknown): number | null {
  const parsed = Number.parseInt(String(value ?? ""), 10);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : null;
}

export function errorMessage(error: unknown, fallback: string): string {
  return error instanceof Error && error.message ? error.message : fallback;
}

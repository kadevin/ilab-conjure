import { historyCardTagsHtml, historyFavoriteButtonHtml } from "./history-organization";
import { escapeHtml, facetDisplayValue, formatDate, formatHistorySizeLabel, historyTaskAccessibleLabel, historyTaskGeneratedCount, historyTaskSourceLabel, historyTaskStackDepth, historyTaskStackLayers, historyThumbnailRatioStyle, historyThumbnailUrl } from "./history-presentation";
import type { HistoryTask } from "./history-types";
import { translate } from "./i18n";

export function historyTaskCardHtml(task: HistoryTask, selection: { selectedTaskIds: ReadonlySet<string>; selectedTaskId: string }): string {
  const taskId = escapeHtml(task.task_id);
  const thumbnailUrl = historyThumbnailUrl(task);
  const ratioStyle = historyThumbnailRatioStyle(task);
  const imageCount = historyTaskGeneratedCount(task);
  const stackDepth = historyTaskStackDepth(imageCount);
  const stackLayers = historyTaskStackLayers(stackDepth);
  const thumb = thumbnailUrl
    ? `<img class="transparency-grid" src="${escapeHtml(thumbnailUrl)}" alt="" loading="lazy" decoding="async" draggable="false">`
    : "";
  const counts = `${task.generated_count || 0}/${task.total_count || 0}`;
  const selected = selection.selectedTaskIds.has(task.task_id)
    || selection.selectedTaskId === task.task_id;
  const active = selection.selectedTaskId === task.task_id;
  const accessibleLabel = historyTaskAccessibleLabel(task);
  const source = historyTaskSourceLabel(task);
  const promptMode = facetDisplayValue("prompt_mode", task.prompt_mode || "");
  const quality = facetDisplayValue("quality", task.quality || "");
  const favoriteButton = historyFavoriteButtonHtml(
    task.task_id,
    Boolean(task.favorite),
    escapeHtml,
    translate(
      task.favorite
        ? "history.unfavoriteTask"
        : "history.favoriteTask",
    ),
  );
  const tagChips = historyCardTagsHtml(
    Array.isArray(task.tags) ? task.tags : [],
    escapeHtml,
  );
  const metaItems = [
    { kind: "date", value: formatDate(task.created_at) },
    { kind: "status", value: task.status },
    { kind: "size", value: formatHistorySizeLabel(task.size || task.ratio || task.orientation || "") },
    { kind: "prompt-mode", value: promptMode },
    { kind: "quality", value: quality },
    { kind: "source", value: source },
    { kind: "count", value: counts },
  ].filter((item) => item.value);
  return `
    <article
      class="history-task-card${active ? " active" : ""}${selected ? " selected" : ""}"
      data-history-task-card-id="${taskId}"
      data-history-created-at="${escapeHtml(task.created_at)}"
      data-history-image-count="${String(imageCount)}"
      data-history-stack-depth="${String(stackDepth)}"
      role="listitem"
      aria-current="${active ? "true" : "false"}"
      ${ratioStyle}
    >
      ${favoriteButton}
      <button class="history-task-open" type="button" data-history-task-id="${taskId}" aria-label="${escapeHtml(accessibleLabel)}" aria-pressed="${selected ? "true" : "false"}">
        <span class="history-task-thumb">
          ${stackLayers}
          <span class="history-task-thumb-frame">${thumb}</span>
        </span>
        <span class="history-task-copy">
          <span class="history-task-title">${escapeHtml(task.prompt_preview || task.mode || task.task_id)}</span>
          ${tagChips}
          <span class="history-task-meta">
            ${metaItems.map((item) => `<span data-history-meta-kind="${escapeHtml(item.kind)}">${escapeHtml(item.value)}</span>`).join("")}
          </span>
        </span>
      </button>
    </article>
  `;
}

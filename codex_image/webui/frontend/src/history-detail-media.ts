import { formatTranslation, translate } from "./i18n";
import { escapeHtml } from "./webui-utils";

export type HistoryOutputRecord = {
  url: string;
  index: number;
  selected: boolean;
  revisedPrompt: string;
  width: number | null;
  height: number | null;
};

type HistoryInputRecord = {
  url: string;
  thumbnailUrl: string;
  label: string;
};

function positiveInt(value: unknown): number | null {
  const parsed = Number.parseInt(String(value ?? ""), 10);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : null;
}

function parseSizeParts(value: unknown): [number, number] | null {
  const match = String(value || "").trim().toLowerCase().match(/^(\d+)\s*x\s*(\d+)$/);
  if (!match) return null;
  const width = positiveInt(match[1]);
  const height = positiveInt(match[2]);
  return width && height ? [width, height] : null;
}

function outputSizeForTask(task: any, index: number, output: any = {}): [number, number] | null {
  return parseSizeParts(output?.size || output?.output_size)
    || parseSizeParts(Array.isArray(task?.output_sizes) ? task.output_sizes[index] : "")
    || parseSizeParts(task?.output_size)
    || parseSizeParts(task?.params?.size);
}

function outputOrientation(record: HistoryOutputRecord): "portrait" | "landscape" | "square" | "unknown" {
  if (!record.width || !record.height) return "unknown";
  if (record.width > record.height) return "landscape";
  if (record.height > record.width) return "portrait";
  return "square";
}

export function taskSelectedOutputIndexes(task: any): Set<number> {
  const indexes = new Set<number>();
  if (Array.isArray(task?.selected_output_indexes)) {
    task.selected_output_indexes.forEach((value: any) => {
      const index = positiveInt(value);
      if (index !== null) indexes.add(index);
    });
  }
  return indexes;
}

export function taskOutputRecords(task: any): HistoryOutputRecord[] {
  const selectedIndexes = taskSelectedOutputIndexes(task);
  const records: HistoryOutputRecord[] = [];
  const outputs = Array.isArray(task?.outputs) ? task.outputs : [];
  outputs.forEach((output: any, fallbackIndex: number) => {
    if (!output || output.deleted || output.status === "deleted") return;
    const url = String(output.url || output.output_url || "");
    if (!url || output.status === "failed") return;
    const outputIndex = positiveInt(output.index) || fallbackIndex + 1;
    const size = outputSizeForTask(task, fallbackIndex, output);
    records.push({
      url,
      index: outputIndex,
      selected: selectedIndexes.has(outputIndex),
      revisedPrompt: String(output.revised_prompt || ""),
      width: size?.[0] || null,
      height: size?.[1] || null,
    });
  });
  if (records.length) return records;
  const urls = Array.isArray(task?.output_urls) ? task.output_urls : (task?.output_url ? [task.output_url] : []);
  return urls
    .filter(Boolean)
    .map((url: string, index: number) => {
      const outputIndex = index + 1;
      const size = outputSizeForTask(task, index);
      return {
        url: String(url),
        index: outputIndex,
        selected: selectedIndexes.has(outputIndex),
        revisedPrompt: String(task?.revised_prompts?.[index] || task?.revised_prompt || ""),
        width: size?.[0] || null,
        height: size?.[1] || null,
      };
    });
}

export function historyDetailImagesLayoutClass(records: HistoryOutputRecord[]): string {
  if (records.length <= 1) return "";
  const orientations = records.map(outputOrientation);
  const known = orientations.filter((orientation) => orientation !== "unknown");
  const allKnown = known.length === records.length;
  const orientation = allKnown && known.every((value) => value === "portrait")
    ? "portrait"
    : allKnown && known.every((value) => value === "landscape")
      ? "landscape"
      : allKnown && known.every((value) => value === "square")
        ? "square"
        : "mixed";
  const stack = records.length === 2 && (orientation === "landscape" || orientation === "square");
  return ` history-detail-images-multi history-detail-images-count-${Math.min(records.length, 4)} history-detail-images-${orientation}${stack ? " history-detail-images-stack" : ""}`;
}

function inputRecordLabel(source: any, fallbackIndex: number): string {
  return String(source?.name || source?.filename || source?.category_name || source?.category || formatTranslation("history.inputReferenceIndex", { index: fallbackIndex }));
}

export function taskInputRecords(task: any): HistoryInputRecord[] {
  const records: HistoryInputRecord[] = [];
  const seen = new Set<string>();
  const addRecord = (url: unknown, thumbnailUrl: unknown, label: unknown): void => {
    const fullUrl = String(url || thumbnailUrl || "");
    const thumb = String(thumbnailUrl || url || "");
    if (!fullUrl || seen.has(fullUrl)) return;
    seen.add(fullUrl);
    records.push({
      url: fullUrl,
      thumbnailUrl: thumb,
      label: String(label || formatTranslation("history.inputReferenceIndex", { index: records.length + 1 })),
    });
  };

  if (Array.isArray(task?.input_sources)) {
    task.input_sources.forEach((source: any, index: number) => {
      if (!source || source.missing) return;
      addRecord(source.image_url || source.url, source.thumbnail_url || source.image_url || source.url, inputRecordLabel(source, index + 1));
    });
  }

  if (!records.length) {
    const inputUrls = Array.isArray(task?.input_urls) ? task.input_urls : [];
    const inputThumbnailUrls = Array.isArray(task?.input_thumbnail_urls) ? task.input_thumbnail_urls : [];
    inputUrls.forEach((url: string, index: number) => {
      addRecord(url, inputThumbnailUrls[index] || url, formatTranslation("history.inputReferenceIndex", { index: index + 1 }));
    });
  }

  return records;
}

function outputRevisedPromptHtml(taskId: string, record: HistoryOutputRecord, index: number): string {
  const revisedPrompt = String(record.revisedPrompt || "").trim();
  if (!revisedPrompt) return "";
  const displayIndex = index + 1;
  const title = formatTranslation("history.outputRevisedPromptTitle", { index: displayIndex });
  return `
    <div class="history-detail-output-prompt">
      <div class="history-detail-output-prompt-header">
        <span>${escapeHtml(title)}</span>
        <button
          class="ghost-button text-sm history-prompt-copy"
          type="button"
          data-history-copy-output-prompt-task-id="${escapeHtml(taskId)}"
          data-history-copy-output-prompt-index="${record.index}"
          aria-label="${escapeHtml(formatTranslation("history.copyOutputPromptPanel", { index: displayIndex }))}"
        >${escapeHtml(translate("history.copyPromptShort"))}</button>
      </div>
      <div class="history-detail-output-prompt-text">${escapeHtml(revisedPrompt)}</div>
    </div>
  `;
}

function historyDetailImageHtml(
  taskId: string,
  record: HistoryOutputRecord,
  index: number,
  selectedCount: number,
  totalCount: number,
): string {
  const selectedClass = record.selected ? " selected" : "";
  const selectedText = record.selected ? translate("history.selected") : translate("history.select");
  const outputBadge = totalCount > 1 ? `<span class="history-detail-output-index">${index + 1} / ${totalCount}</span>` : "";
  const revisedPrompt = outputRevisedPromptHtml(taskId, record, index);
  return `
    <article class="history-detail-image history-detail-output-card${selectedClass}">
      <button
        class="history-detail-image-preview history-detail-output-preview"
        type="button"
        data-history-lightbox-url="${escapeHtml(record.url)}"
        data-history-lightbox-index="${index}"
        aria-label="${escapeHtml(translate("history.openPreview"))}"
      >
        ${outputBadge}
        <img src="${escapeHtml(record.url)}" alt="" loading="lazy" decoding="async">
      </button>
      <div class="history-detail-image-actions" aria-label="${escapeHtml(translate("history.outputActions"))}">
        <button
          class="history-detail-overlay-button"
          type="button"
          aria-pressed="${record.selected ? "true" : "false"}"
          data-history-output-selected-task-id="${escapeHtml(taskId)}"
          data-history-output-selected-index="${record.index}"
        >${selectedText}</button>
        <a class="history-detail-overlay-button" href="${escapeHtml(record.url)}" download>${escapeHtml(formatTranslation("history.downloadIndex", { index: index + 1 }))}</a>
        <button class="history-detail-overlay-button primary" type="button" data-history-reference-handoff-url="${escapeHtml(record.url)}">${escapeHtml(translate("history.addReference"))}</button>
        ${selectedCount === 1 && record.selected ? `<a class="history-detail-overlay-button" href="${escapeHtml(record.url)}" download>${escapeHtml(translate("history.downloadSelected"))}</a>` : ""}
      </div>
      ${revisedPrompt}
    </article>
  `;
}

export function historyDetailImagesHtml(taskId: string, records: HistoryOutputRecord[], selectedCount: number): string {
  return records.map((record, index) => historyDetailImageHtml(taskId, record, index, selectedCount, records.length)).join("");
}

export function historyInputReferencesHtml(task: any): string {
  const records = taskInputRecords(task);
  if (!records.length) return "";
  const thumbs = records.map((record, index) => `
    <button
      class="history-detail-input-thumb"
      type="button"
      title="${escapeHtml(record.label)}"
      data-history-input-lightbox-index="${index}"
      aria-label="${escapeHtml(formatTranslation("history.inputReferenceIndex", { index: index + 1 }))}"
    >
      <img src="${escapeHtml(record.thumbnailUrl)}" alt="" loading="lazy" decoding="async">
    </button>
  `).join("");
  return `
    <section class="history-detail-inputs" aria-label="${escapeHtml(translate("history.inputReferences"))}">
      <div class="history-detail-inputs-header">
        <h3>${escapeHtml(translate("history.inputReferences"))}</h3>
        <span>${records.length}</span>
      </div>
      <div class="history-detail-inputs-list">${thumbs}</div>
    </section>
  `;
}

export function historyLightboxUrlsFromTask(task: any): string[] {
  return taskOutputRecords(task).map((record) => record.url).filter(Boolean);
}

export function historyInputLightboxUrlsFromTask(task: any): string[] {
  return taskInputRecords(task).map((record) => record.url).filter(Boolean);
}

import { getLegacyBridge } from "./state";
import { formatTranslation, translate } from "./i18n";

const RATIO_ORIENTATION: Record<string, string> = {
  "1:1": "square",
  "4:5": "portrait",
  "5:4": "landscape",
  "3:4": "portrait",
  "4:3": "landscape",
  "2:3": "portrait",
  "3:2": "landscape",
  "9:16": "portrait",
  "16:9": "landscape",
  "9:21": "portrait",
  "21:9": "landscape",
};

const GPT_IMAGE_2_SIZE_PRESETS: Record<string, Record<string, [number, number]>> = {
  standard: {
    "1:1": [1024, 1024],
    "4:5": [1024, 1280],
    "5:4": [1280, 1024],
    "3:4": [1152, 1536],
    "4:3": [1536, 1152],
    "2:3": [1024, 1536],
    "3:2": [1536, 1024],
    "9:16": [864, 1536],
    "16:9": [1536, 864],
    "9:21": [672, 1568],
    "21:9": [1568, 672],
  },
  "2k": {
    "1:1": [2048, 2048],
    "4:5": [1600, 2000],
    "5:4": [2000, 1600],
    "3:4": [1536, 2048],
    "4:3": [2048, 1536],
    "2:3": [1344, 2016],
    "3:2": [2016, 1344],
    "9:16": [1152, 2048],
    "16:9": [2048, 1152],
    "9:21": [1152, 2688],
    "21:9": [2688, 1152],
  },
  "4k": {
    "1:1": [2880, 2880],
    "4:5": [2560, 3200],
    "5:4": [3200, 2560],
    "3:4": [2448, 3264],
    "4:3": [3264, 2448],
    "2:3": [2336, 3504],
    "3:2": [3504, 2336],
    "9:16": [2160, 3840],
    "16:9": [3840, 2160],
    "9:21": [1632, 3808],
    "21:9": [3808, 1632],
  },
};

function legacyMethod(name: string, ...args: any[]): any {
  const method = getLegacyBridge().methods[name];
  if (typeof method !== "function") {
    throw new Error("Legacy bridge method " + name + " is not available");
  }
  return method(...args);
}

function escapeHtml(...args: any[]) { return legacyMethod("escapeHtml", ...args); }

function taskRatio(task: any) {
  const dimensions = taskSizeDimensions(task);
  if (!dimensions) return "";
  const [width, height] = dimensions;
  for (const ratios of Object.values(GPT_IMAGE_2_SIZE_PRESETS)) {
    for (const [ratio, presetDimensions] of Object.entries(ratios)) {
      if (presetDimensions[0] === width && presetDimensions[1] === height) return ratio;
    }
  }
  const divisor = greatestCommonDivisor(width, height);
  const normalized = `${Math.round(width / divisor)}:${Math.round(height / divisor)}`;
  if (normalized === "3:7") return "9:21";
  if (normalized === "7:3") return "21:9";
  return normalized;
}

function taskOrientation(task: any) {
  const ratio = taskRatio(task);
  if (RATIO_ORIENTATION[ratio]) return RATIO_ORIENTATION[ratio];
  const dimensions = taskSizeDimensions(task);
  if (!dimensions) return "";
  const [width, height] = dimensions;
  if (width === height) return "square";
  return width > height ? "landscape" : "portrait";
}

function taskPromptFidelity(task: any) {
  const value = String(task?.params?.prompt_fidelity || task?.request?.prompt_fidelity || "strict");
  return ["original", "strict", "off"].includes(value) ? value : "strict";
}

function taskResolution(task: any) {
  const dimensions = taskSizeDimensions(task);
  if (!dimensions) return "";
  const [width, height] = dimensions;
  for (const [resolution, ratios] of Object.entries(GPT_IMAGE_2_SIZE_PRESETS)) {
    const matchesPreset = Object.values(ratios).some((presetDimensions) => {
      return presetDimensions[0] === width && presetDimensions[1] === height;
    });
    if (matchesPreset) return resolution;
  }
  return "";
}

function taskSizeDimensions(task: any): [number, number] | null {
  const size = String(task?.output_size || task?.params?.size || task?.request?.size || "");
  const match = size.match(/^(\d{2,5})x(\d{2,5})$/i);
  if (!match) return null;
  const width = Number.parseInt(match[1] || "", 10);
  const height = Number.parseInt(match[2] || "", 10);
  if (!width || !height) return null;
  return [width, height];
}

function greatestCommonDivisor(left: number, right: number): number {
  let a = Math.abs(left);
  let b = Math.abs(right);
  while (b) {
    const remainder = a % b;
    a = b;
    b = remainder;
  }
  return a || 1;
}

function taskInputUrls(task: any) {
  if (Array.isArray(task.input_urls) && task.input_urls.length) {
    return task.input_urls;
  }
  if (!Array.isArray(task.input_files) || !task.task_id) {
    return [];
  }
  return task.input_files.map((filename: any) => `/inputs/${encodeURIComponent(filename)}`);
}

function taskInputThumbnailRoute(task: any, index: any) {
  const inputIndex = positiveInt(index);
  if (!task?.task_id || inputIndex === null) return "";
  return `/api/tasks/${encodeURIComponent(task.task_id)}/inputs/${inputIndex}/thumbnail`;
}

function taskInputThumbnailUrls(task: any) {
  if (!task) return [];
  if (Array.isArray(task.input_thumbnail_urls) && task.input_thumbnail_urls.length) {
    return task.input_thumbnail_urls.filter(Boolean);
  }
  return taskInputUrls(task).map((_: any, index: number) => taskInputThumbnailRoute(task, index + 1)).filter(Boolean);
}

function isLegacyOutputInputUrl(url: any) {
  return typeof url === "string" && /^\/outputs\/[^/]+\/inputs\//.test(url);
}

function taskInputPreviewUrls(task: any) {
  const thumbnailUrls = taskInputThumbnailUrls(task);
  if (Array.isArray(task?.input_sources) && task.input_sources.length) {
    const inputUrls = taskInputUrls(task);
    let uploadInputIndex = 0;
    return task.input_sources.map((source: any) => {
      if (source?.kind !== "upload") return source?.image_url;
      const fallbackUrl = inputUrls[uploadInputIndex];
      const thumbnailUrl = source.thumbnail_url || thumbnailUrls[uploadInputIndex];
      uploadInputIndex += 1;
      if (thumbnailUrl) return thumbnailUrl;
      if (fallbackUrl && isLegacyOutputInputUrl(source.image_url)) return fallbackUrl;
      return source.image_url || fallbackUrl;
    }).filter(Boolean);
  }
  return thumbnailUrls.length ? thumbnailUrls : taskInputUrls(task);
}

function outputFileUrl(filename: any) {
  const clean = String(filename || "").split("/").filter(Boolean).map(encodeURIComponent).join("/");
  return clean ? `/outputs/${clean}` : "";
}

function taskThumbnailRoute(task: any, index: any) {
  const outputIndex = positiveInt(index);
  if (!task?.task_id || outputIndex === null) return "";
  return `/api/tasks/${encodeURIComponent(task.task_id)}/outputs/${outputIndex}/thumbnail`;
}

function taskThumbnailUrls(task: any) {
  if (!task) return [];
  const deletedIndexes = taskDeletedOutputIndexes(task);
  const urls: string[] = [];
  const pushUrl = (url: any, index: any) => {
    const clean = String(url || "").trim();
    const outputIndex = positiveInt(index);
    if (!clean || (outputIndex !== null && deletedIndexes.has(outputIndex)) || urls.includes(clean)) return;
    urls.push(clean);
  };

  if (Array.isArray(task.thumbnail_urls) && task.thumbnail_urls.length) {
    task.thumbnail_urls.forEach((url: any, fallbackIndex: any) => {
      pushUrl(url, taskOutputIndexFromUrl(url) || fallbackIndex + 1);
    });
    if (urls.length) return urls;
  }

  if (Array.isArray(task?.outputs)) {
    task.outputs.forEach((record: any, fallbackIndex: any) => {
      if (!record || typeof record !== "object" || taskOutputRecordIsDeleted(record)) return;
      const index = positiveInt(record.index) || fallbackIndex + 1;
      if (deletedIndexes.has(index) || record.status !== "completed") return;
      const recordUrl = record.thumbnail_url || outputFileUrl(record.thumbnail_file) || (record.url || record.file ? taskThumbnailRoute(task, index) : "");
      pushUrl(recordUrl, index);
    });
    if (urls.length) return urls;
  }

  taskOutputUrls(task).forEach((url: any, fallbackIndex: any) => {
    const index = taskOutputIndexFromUrl(url) || fallbackIndex + 1;
    pushUrl(taskThumbnailRoute(task, index), index);
  });
  return urls;
}

function taskOutputUrls(task: any) {
  if (!task) return [];
  const deletedIndexes = taskDeletedOutputIndexes(task);
  if (Array.isArray(task.output_urls) && task.output_urls.length) {
    return task.output_urls.filter((url: any, fallbackIndex: any) => {
      const record = Array.isArray(task?.outputs)
        ? task.outputs.find((item: any) => taskOutputRecordMatchesUrl(item, url))
        : null;
      const index = positiveInt(record?.index) || taskOutputIndexFromUrl(url) || fallbackIndex + 1;
      return !deletedIndexes.has(index) && !taskOutputRecordIsDeleted(record);
    });
  }
  const singleIndex = taskOutputIndexFromUrl(task.output_url) || 1;
  if (task.output_url && !deletedIndexes.has(singleIndex)) return [task.output_url];
  return [];
}

function taskDeletedOutputIndexes(task: any) {
  const indexes = new Set<number>();
  if (Array.isArray(task?.deleted_output_indexes)) {
    task.deleted_output_indexes.forEach((value: any) => {
      const index = positiveInt(value);
      if (index !== null) indexes.add(index);
    });
  }
  if (Array.isArray(task?.outputs)) {
    task.outputs.forEach((record: any, fallbackIndex: any) => {
      if (!taskOutputRecordIsDeleted(record)) return;
      const index = positiveInt(record?.index) || fallbackIndex + 1;
      indexes.add(index);
    });
  }
  return indexes;
}

function taskSelectedOutputIndexes(task: any) {
  const deletedIndexes = taskDeletedOutputIndexes(task);
  const indexes: number[] = [];
  if (!Array.isArray(task?.selected_output_indexes)) return indexes;
  task.selected_output_indexes.forEach((value: any) => {
    const index = positiveInt(value);
    if (index === null || deletedIndexes.has(index) || indexes.includes(index)) return;
    indexes.push(index);
  });
  return indexes.sort((left, right) => left - right);
}

function taskOutputSelected(task: any, outputIndex: any) {
  const index = positiveInt(outputIndex);
  if (index === null) return false;
  return taskSelectedOutputIndexes(task).includes(index);
}

function taskOutputRecordIsDeleted(record: any) {
  if (!record || typeof record !== "object") return false;
  return Boolean(record.deleted) || record.status === "deleted";
}

function taskOutputRecordMatchesUrl(record: any, url: any) {
  if (!record || typeof record !== "object") return false;
  if (record.url && String(record.url) === String(url)) return true;
  const recordIndex = positiveInt(record.index);
  const urlIndex = taskOutputIndexFromUrl(url);
  return recordIndex !== null && urlIndex !== null && recordIndex === urlIndex;
}

function taskImageBlockStates(task: any) {
  const total = taskTotalCount(task);
  const records = taskOutputRecordsByIndex(task);
  const status = String(task?.status || "");
  const states = [];
  let runningAssigned = false;
  const hasExplicitRunningRecords = Array.from(records.values()).some((record: any) => record?.status === "running");
  for (let index = 1; index <= total; index += 1) {
    const record = records.get(index);
    if (record?.status === "completed") {
      states.push(taskOutputRecordHasDisplayableImage(record) ? "completed" : "waiting");
    } else if (record?.status === "failed") {
      states.push("failed");
    } else if (record?.status === "running") {
      states.push("running");
    } else if (record?.status === "queued" || record?.status === "waiting") {
      states.push(record.status);
    } else if (status === "running" && !hasExplicitRunningRecords && !runningAssigned) {
      states.push("running");
      runningAssigned = true;
    } else if (status === "queued" || status === "submitting") {
      states.push("queued");
    } else if (status === "failed" || status === "partial_failed") {
      states.push("failed");
    } else if (status === "completed") {
      states.push("completed");
    } else {
      states.push("waiting");
    }
  }
  return states;
}

function taskVisibleCompletedCount(task: any) {
  if (!task) return 0;
  const completedRecords = [...taskOutputRecordsByIndex(task).values()]
    .filter((record: any) => record?.status === "completed" && taskOutputRecordHasDisplayableImage(record))
    .length;
  return Math.max(completedRecords, taskOutputUrls(task).length);
}

function taskOutputRecordHasDisplayableImage(record: any) {
  return Boolean(record?.url);
}

function taskOutputRecordsByIndex(task: any) {
  const records = new Map();
  const outputUrls = taskOutputUrls(task);
  const structuredOutputs = Array.isArray(task?.outputs) ? task.outputs : [];
  if (!structuredOutputs.length) {
    outputUrls.forEach((url: any, index: any) => {
      records.set(index + 1, { index: index + 1, status: "completed", url });
    });
    return records;
  }
  structuredOutputs.forEach((record: any, fallbackIndex: any) => {
    if (!record || typeof record !== "object") return;
    if (taskOutputRecordIsDeleted(record)) return;
    const index = positiveInt(record.index) || fallbackIndex + 1;
    if (taskDeletedOutputIndexes(task).has(index)) return;
    const previous = records.get(index) || {};
    records.set(index, { ...previous, ...record, url: record.url || previous.url });
  });
  outputUrls.forEach((url: any, fallbackIndex: any) => {
    if (!url) return;
    const duplicateUrl = [...records.values()].some((record: any) => record?.url === url);
    if (duplicateUrl) return;
    const index = taskOutputIndexFromUrl(url) || fallbackIndex + 1;
    const previous = records.get(index);
    if (previous) {
      records.set(index, { ...previous, status: previous.status || "completed", url: previous.url || url });
    } else {
      records.set(index, { index, status: "completed", url });
    }
  });
  return records;
}

function taskOutputIndexFromUrl(url: any) {
  const match = String(url || "").match(/-image-(\d+)(?=\.[a-z0-9]+(?:[?#].*)?$|$)/i);
  return positiveInt(match?.[1]);
}

function compressTaskImageBlockStates(states: any) {
  if (states.length <= 12) return states;
  const compressed = [];
  for (let index = 0; index < 12; index += 1) {
    const start = Math.floor((index * states.length) / 12);
    const end = Math.max(start + 1, Math.floor(((index + 1) * states.length) / 12));
    compressed.push(compressedTaskImageState(states.slice(start, end)));
  }
  return compressed;
}

function compressedTaskImageState(states: any) {
  if (states.includes("failed")) return "failed";
  if (states.includes("running")) return "running";
  if (states.length && states.every((state: any) => state === "completed")) return "completed";
  if (states.includes("queued")) return "queued";
  return "waiting";
}

function taskImageStatusCounts(states: any) {
  return states.reduce((counts: any, state: any) => {
    counts[state] = (counts[state] || 0) + 1;
    return counts;
  }, { completed: 0, failed: 0, running: 0, queued: 0, waiting: 0 });
}

function positiveInt(value: any) {
  const parsed = Number.parseInt(value ?? "", 10);
  return !Number.isNaN(parsed) && parsed > 0 ? parsed : null;
}

function taskFailureMessage(task: any) {
  if (!task || (task.status !== "failed" && task.status !== "partial_failed")) return "";
  return String(task.error || task.last_error || "").trim();
}

function canRetryFailedTask(task: any) {
  if (!task || task.local_pending) return false;
  if (!["failed", "partial_failed"].includes(task.status)) return false;
  if (taskHasNonRetryableError(task)) return false;
  const states = taskImageBlockStates(task);
  return states.includes("failed");
}

function canAcceptTaskSuccesses(task: any) {
  if (!task || task.local_pending) return false;
  if (!["failed", "partial_failed"].includes(task.status)) return false;
  return taskOutputUrls(task).length > 0;
}

function taskRetryReasonText(task: any) {
  const message = String(task?.last_error || task?.error || "").toLowerCase();
  if (message.includes("usage limit") || message.includes("quota") || message.includes("rate limit")) {
    return translate("taskDerived.usageLimited");
  }
  if (message.includes("incompleteread") || message.includes("timeout") || message.includes("network")) {
    return formatTranslation("taskStatus.connectionInterrupted");
  }
  return formatTranslation("taskStatus.lastFailed");
}

function taskRetryStateText(task: any) {
  if (!task) return "";
  const attempts = positiveInt(task.attempts) || 0;
  const maxAttempts = positiveInt(task.max_attempts) || 0;
  const retryingSlots = Array.isArray(task.retrying_failed_slots) ? task.retrying_failed_slots : [];
  const manualRetryRequested = Boolean(task.retry_requested_at || retryingSlots.length);
  const hasRetryContext = Boolean(task.last_error || task.error || manualRetryRequested);
  if (!hasRetryContext || !maxAttempts) return "";
  const reason = taskRetryReasonText(task);
  if (task.status === "queued" && attempts < maxAttempts) {
    return formatTranslation("taskStatus.waitingRetry", {
      reason,
      attempt: attempts + 1,
      max: maxAttempts,
    });
  }
  if (task.status === "running") {
    if (attempts <= 1 && !manualRetryRequested) return "";
    return formatTranslation("taskStatus.retrying", {
      reason,
      attempt: Math.max(1, attempts),
      max: maxAttempts,
    });
  }
  if (["failed", "partial_failed"].includes(task.status)) {
    if (taskHasNonRetryableError(task)) {
      return formatTranslation("taskStatus.nonRetryableAttempt", {
        attempt: Math.max(1, attempts),
        max: maxAttempts,
      });
    }
    if (attempts > 0) {
      return formatTranslation("taskStatus.manualRetryAvailable");
    }
  }
  return "";
}

function taskHasNonRetryableError(task: any) {
  const message = String(task?.error || task?.last_error || "").toLowerCase();
  if (!message) return false;
  if (message.includes("usage limit") || message.includes("quota") || message.includes("rate limit")) return true;
  if (!message.includes("http 400")) return false;
  return [
    "invalid_request_error",
    "invalid_value",
    "expected a base64-encoded data url",
    "unsupported mime type",
  ].some((token: any) => message.includes(token));
}

function taskRuntimeText(task: any) {
  if (!task || !["completed", "failed", "partial_failed"].includes(task.status)) return "";
  const startedAt = timestampMs(task.started_at || task.created_at);
  const endedAt = timestampMs(task.completed_at || task.updated_at);
  if (startedAt === null || endedAt === null || endedAt < startedAt) return "";
  const seconds = Math.floor((endedAt - startedAt) / 1000);
  const completion = taskCompletionTimestampText(task);
  const duration = formatDuration(seconds);
  return completion
    ? formatTranslation("taskStatus.runtimeCompleted", { duration, time: completion.shortText })
    : formatTranslation("taskStatus.runtime", { duration });
}

function taskCompletionTimestampText(task: any) {
  const completedAt = taskCompletionTimestampMs(task);
  if (completedAt === null) return null;
  return { shortText: formatLocalTimestamp(completedAt, false) };
}

function taskCompletionTimestampTitle(task: any) {
  const completedAt = taskCompletionTimestampMs(task);
  if (completedAt === null) return "";
  return formatTranslation("taskStatus.completedAt", { time: formatLocalTimestamp(completedAt, true) });
}

function taskCompletionTimestampMs(task: any) {
  if (!task || !["completed", "failed", "partial_failed"].includes(task.status)) return null;
  return timestampMs(task.completed_at || task.updated_at);
}

function formatLocalTimestamp(timestamp: number, includeSeconds: boolean) {
  const value = new Date(timestamp);
  if (Number.isNaN(value.getTime())) return "";
  const year = value.getFullYear();
  const month = String(value.getMonth() + 1).padStart(2, "0");
  const day = String(value.getDate()).padStart(2, "0");
  const hours = String(value.getHours()).padStart(2, "0");
  const minutes = String(value.getMinutes()).padStart(2, "0");
  const seconds = String(value.getSeconds()).padStart(2, "0");
  return includeSeconds
    ? `${year}-${month}-${day} ${hours}:${minutes}:${seconds}`
    : `${month}-${day} ${hours}:${minutes}`;
}

function timestampMs(value: any) {
  if (typeof value === "number" && Number.isFinite(value)) {
    return value;
  }
  if (typeof value === "string" && value.trim()) {
    const parsed = Date.parse(value);
    return Number.isFinite(parsed) ? parsed : null;
  }
  return null;
}

function elapsedSecondsSince(value: any) {
  const startedAt = timestampMs(value);
  if (startedAt === null) return 0;
  return Math.max(0, Math.floor((Date.now() - startedAt) / 1000));
}

function elapsedMillisecondsSince(value: any) {
  const startedAt = timestampMs(value);
  if (startedAt === null) return 0;
  return Math.max(0, Date.now() - startedAt);
}

function formatDuration(totalSeconds: any) {
  const safeSeconds = Number.isFinite(totalSeconds) && totalSeconds > 0 ? totalSeconds : 0;
  const minutes = Math.floor(safeSeconds / 60);
  const seconds = safeSeconds % 60;
  return `${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
}

function formatDurationParts(totalMilliseconds: any) {
  const safeMilliseconds = Number.isFinite(totalMilliseconds) && totalMilliseconds > 0 ? totalMilliseconds : 0;
  const minutes = Math.floor(safeMilliseconds / 60000);
  const seconds = Math.floor((safeMilliseconds % 60000) / 1000);
  const deciseconds = Math.floor((safeMilliseconds % 1000) / 100);
  const clock = `${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
  const fraction = `.${deciseconds}`;
  return { clock, fraction, text: `${clock}${fraction}` };
}

function formatDurationTenths(totalMilliseconds: any) {
  return formatDurationParts(totalMilliseconds).text;
}

function elapsedWheelMarkup(char: any) {
  const safeChar = escapeHtml(char);
  if (/^\d$/.test(char)) {
    const digitStrip = "0123456789"
      .split("")
      .map((digit: any) => `<span>${digit}</span>`)
      .join("");
    return `<span class="elapsed-wheel" aria-hidden="true" data-elapsed-char="${safeChar}" data-elapsed-char-value="${safeChar}" style="--digit-offset: ${safeChar};"><span class="elapsed-wheel-strip">${digitStrip}</span></span>`;
  }
  return `<span class="elapsed-separator" aria-hidden="true" data-elapsed-char="${safeChar}" data-elapsed-char-value="${safeChar}">${safeChar}</span>`;
}

function elapsedPartMarkup(text: any) {
  return Array.from(text).map((char: any) => elapsedWheelMarkup(char)).join("");
}

function elapsedTimerMarkup(totalMilliseconds: any) {
  const elapsed = formatDurationParts(totalMilliseconds);
  return `<span class="elapsed-main">${elapsedPartMarkup(elapsed.clock)}</span><span class="elapsed-ms">${elapsedPartMarkup(elapsed.fraction)}</span>`;
}

function elapsedTimerSpan(kind: any, startValue: any) {
  const elapsedMs = elapsedMillisecondsSince(startValue);
  const elapsed = formatDurationTenths(elapsedMs);
  return `<span class="elapsed-timer" aria-label="${elapsed}" data-preview-elapsed="${escapeHtml(kind)}" data-preview-start="${escapeHtml(startValue || "")}">${elapsedTimerMarkup(elapsedMs)}</span>`;
}

function taskGeneratedCount(task: any, fallback: any = 0) {
  const visibleCompleted = taskVisibleCompletedCount(task);
  if (visibleCompleted || Array.isArray(task?.outputs) || Array.isArray(task?.output_urls) || task?.output_url) {
    return visibleCompleted;
  }
  const value = Number.parseInt(task?.generated_count ?? "", 10);
  if (!Number.isNaN(value)) return value;
  return fallback;
}

function taskTotalCount(task: any) {
  const value = Number.parseInt(task?.total_count ?? task?.params?.n ?? "", 10);
  if (!Number.isNaN(value) && value > 0) return value;
  return 1;
}

function taskOutputIndex(task: any, url: any, visibleIndex: any) {
  const output = Array.isArray(task?.outputs)
    ? task.outputs.find((item: any) => item?.status === "completed" && item?.url === url)
    : null;
  const value = Number.parseInt(output?.index ?? "", 10);
  if (!Number.isNaN(value) && value > 0) return value;
  return visibleIndex + 1;
}

function taskProgressStartValue(task: any) {
  if (!task) return "";
  if (task.status === "running" && taskRetryStateText(task)) {
    return task?.attempt_started_at || task?.updated_at || task?.retry_requested_at || task?.queued_at || task?.started_at || task?.created_at || "";
  }
  return task?.attempt_started_at || task?.started_at || task?.queued_at || task?.created_at || "";
}

export function initTaskDerivedFeature() {
  Object.assign(getLegacyBridge().methods, {
    taskRatio,
    taskOrientation,
    taskPromptFidelity,
    taskResolution,
    taskSizeDimensions,
    greatestCommonDivisor,
    taskInputUrls,
    taskInputThumbnailUrls,
    taskInputThumbnailRoute,
    taskInputPreviewUrls,
    taskThumbnailUrls,
    taskThumbnailRoute,
    taskOutputUrls,
    taskDeletedOutputIndexes,
    taskSelectedOutputIndexes,
    taskOutputSelected,
    taskImageBlockStates,
    taskVisibleCompletedCount,
    taskOutputRecordIsDeleted,
    taskOutputRecordMatchesUrl,
    taskOutputRecordHasDisplayableImage,
    taskOutputRecordsByIndex,
    taskOutputIndexFromUrl,
    compressTaskImageBlockStates,
    compressedTaskImageState,
    taskImageStatusCounts,
    positiveInt,
    taskFailureMessage,
    canRetryFailedTask,
    canAcceptTaskSuccesses,
    taskRetryReasonText,
    taskRetryStateText,
    taskHasNonRetryableError,
    taskRuntimeText,
    taskCompletionTimestampText,
    taskCompletionTimestampTitle,
    timestampMs,
    elapsedSecondsSince,
    elapsedMillisecondsSince,
    formatDuration,
    formatDurationParts,
    formatDurationTenths,
    elapsedWheelMarkup,
    elapsedPartMarkup,
    elapsedTimerMarkup,
    elapsedTimerSpan,
    taskGeneratedCount,
    taskTotalCount,
    taskOutputIndex,
    taskProgressStartValue,
  });
}

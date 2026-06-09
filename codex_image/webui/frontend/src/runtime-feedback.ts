import { getLegacyBridge } from "./state";
import { formatTranslation, translate } from "./i18n";
import type { WebUITask } from "./types";

function legacyMethod(name: string, ...args: any[]): any {
  const method = getLegacyBridge().methods[name];
  if (typeof method !== "function") {
    throw new Error("Legacy bridge method " + name + " is not available");
  }
  return method(...args);
}

const renderTasks = (...args: any[]) => legacyMethod("renderTasks", ...args);
const renderPreview = (...args: any[]) => legacyMethod("renderPreview", ...args);
const revokeTaskUploadPreviewUrls = (...args: any[]) => legacyMethod("revokeTaskUploadPreviewUrls", ...args);
const taskProgressStartValue = (...args: any[]) => legacyMethod("taskProgressStartValue", ...args);
const taskStatusAccessibleLabel = (...args: any[]) => legacyMethod("taskStatusAccessibleLabel", ...args);
const taskMetaText = (...args: any[]) => legacyMethod("taskMetaText", ...args);
const taskRuntimeText = (...args: any[]) => legacyMethod("taskRuntimeText", ...args);
const taskRetryStateText = (...args: any[]) => legacyMethod("taskRetryStateText", ...args);
const timestampMs = (...args: any[]) => legacyMethod("timestampMs", ...args);
const elapsedSecondsSince = (...args: any[]) => legacyMethod("elapsedSecondsSince", ...args);
const elapsedMillisecondsSince = (...args: any[]) => legacyMethod("elapsedMillisecondsSince", ...args);
const formatDuration = (...args: any[]) => legacyMethod("formatDuration", ...args);
const formatDurationParts = (...args: any[]) => legacyMethod("formatDurationParts", ...args);
const formatDurationTenths = (...args: any[]) => legacyMethod("formatDurationTenths", ...args);
const elapsedPartMarkup = (...args: any[]) => legacyMethod("elapsedPartMarkup", ...args);
const elapsedTimerMarkup = (...args: any[]) => legacyMethod("elapsedTimerMarkup", ...args);
const setStatus = (...args: any[]) => legacyMethod("setStatus", ...args);
const getPromptText = (...args: any[]) => legacyMethod("getPromptText", ...args);
const syncRunButtonLabel = (...args: any[]) => legacyMethod("syncRunButtonLabel", ...args);

export function updateTaskInState(task: WebUITask | null | undefined): boolean {
  const state = getLegacyBridge().state;
  if (!task?.task_id) return false;
  const taskId = String(task.task_id);
  const previousIndex = state.tasks.findIndex((item: any) => String(item.task_id) === taskId);
  if (previousIndex === -1) {
    state.tasks.unshift(task);
    return true;
  }
  const previousTask = state.tasks[previousIndex];
  if (previousTask?.local_pending) {
    revokeTaskUploadPreviewUrls(previousTask);
  }
  state.tasks = state.tasks.map((item: any, index: number) => (index === previousIndex ? task : item));
  if (state.pendingTaskId && String(state.pendingTaskId) === taskId && !task.local_pending) {
    state.pendingTaskId = null;
  }
  return true;
}

export function formatTaskStatus(task: WebUITask | null | undefined): string {
  if (!task) return "";
  if (task.status === "submitting") return translate("taskStatus.submitting");
  if (task.status === "running") {
    const progressStartedAt = taskProgressStartValue(task);
    return progressStartedAt
      ? formatTranslation("taskStatus.runningWithElapsed", { elapsed: formatDuration(elapsedSecondsSince(progressStartedAt)) })
      : translate("taskStatus.running");
  }
  if (task.status === "completed") return translate("taskStatus.completed");
  if (task.status === "partial_failed") return translate("taskStatus.partialFailed");
  if (task.status === "failed") return translate("taskStatus.failed");
  if (task.status === "queued") return translate("taskStatus.queued");
  return task.status || "";
}

export function startUiClock(): void {
  const state = getLegacyBridge().state;
  if (state.uiClockTimerId) return;
  state.uiClockTimerId = window.setInterval(updateElapsedDisplays, 100);
}

export function updateElapsedDisplays(): void {
  updateTaskElapsedDisplays();
  window.updateQueueElapsedDisplays?.();
  updatePreviewElapsedDisplay();
}

export function updateTaskElapsedDisplays(): void {
  const { state, els } = getLegacyBridge();
  const root = els.taskHistoryShell || els.taskList;
  if (!root) return;
  const tasksById = new Map(state.tasks.map((task: any) => [String(task.task_id), task]));
  root.querySelectorAll("[data-task-status-id]").forEach((element: any) => {
    const task = tasksById.get(String(element.dataset.taskStatusId || ""));
    if (task) {
      element.textContent = formatTaskStatus(task) || translate("taskStatus.unknown");
      element.closest(".task-status-row")?.setAttribute("aria-label", taskStatusAccessibleLabel(task));
    }
  });
  root.querySelectorAll("[data-task-meta-id]").forEach((element: any) => {
    const task = tasksById.get(String(element.dataset.taskMetaId || ""));
    if (task) element.textContent = taskMetaText(task);
  });
  root.querySelectorAll("[data-task-runtime-id]").forEach((element: any) => {
    const task = tasksById.get(String(element.dataset.taskRuntimeId || ""));
    if (task) element.textContent = taskRuntimeText(task);
  });
  root.querySelectorAll("[data-task-retry-id]").forEach((element: any) => {
    const task = tasksById.get(String(element.dataset.taskRetryId || ""));
    if (task) element.textContent = taskRetryStateText(task);
  });
}

export function updatePreviewElapsedDisplay(): void {
  const { els } = getLegacyBridge();
  if (!els.previewGrid) return;
  els.previewGrid.querySelectorAll("[data-preview-elapsed]").forEach((element: any) => {
    updateElapsedTimerElement(element, elapsedMillisecondsSince(element.dataset.previewStart));
  });
}

function updateElapsedTimerElement(element: any, totalMilliseconds: number): void {
  const elapsed = formatDurationParts(totalMilliseconds);
  element.setAttribute("aria-label", elapsed.text);
  const main = element.querySelector(".elapsed-main");
  const ms = element.querySelector(".elapsed-ms");
  if (main && ms) {
    updateElapsedPartElement(main, elapsed.clock);
    updateElapsedPartElement(ms, elapsed.fraction);
    return;
  }
  element.innerHTML = elapsedTimerMarkup(totalMilliseconds);
}

function updateElapsedPartElement(element: any, text: string): void {
  const chars = Array.from(text);
  const charNodes = Array.from(element.querySelectorAll("[data-elapsed-char]"));
  if (charNodes.length !== chars.length) {
    element.innerHTML = elapsedPartMarkup(text);
    return;
  }
  for (const [index, node] of charNodes.entries()) {
    const char = chars[index];
    if ((node as any).dataset.elapsedCharValue === char) continue;
    if (!/^\d$/.test(char || "") || !(node as any).classList.contains("elapsed-wheel")) {
      element.innerHTML = elapsedPartMarkup(text);
      return;
    }
    (node as any).dataset.elapsedCharValue = char;
    (node as any).dataset.elapsedChar = char;
    (node as any).style.setProperty("--digit-offset", char);
  }
}

export function updatePromptCount(): void {
  const { els } = getLegacyBridge();
  if (!els.charCount) return;
  els.charCount.textContent = `${getPromptText().length} / 4000`;
}

export function addPendingTask(task: WebUITask): void {
  const state = getLegacyBridge().state;
  state.pendingTaskId = task.task_id;
  state.selectedTaskId = task.task_id;
  state.tasks = [task, ...state.tasks.filter((item: any) => item.task_id !== task.task_id)];
  renderTasks();
  renderPreview(task);
}

export function replacePendingTask(pendingTaskId: string, completedTask: WebUITask): void {
  const state = getLegacyBridge().state;
  const removedPendingTasks = state.tasks.filter((task: any) => (
    task?.local_pending
    && (task.task_id === completedTask.task_id || task.task_id === pendingTaskId)
  ));
  state.tasks = [
    completedTask,
    ...state.tasks.filter((task: any) => task.task_id !== completedTask.task_id && task.task_id !== pendingTaskId),
  ];
  removedPendingTasks.forEach(revokeTaskUploadPreviewUrls);
  state.selectedTaskId = completedTask.task_id;
  state.pendingTaskId = null;
  renderTasks();
  renderPreview(completedTask);
}

export function markPendingTaskFailed(pendingTaskId: string, message: string): void {
  const state = getLegacyBridge().state;
  const task = state.tasks.find((item: any) => item.task_id === pendingTaskId);
  if (!task) return;
  task.status = "failed";
  task.error = message;
  task.updated_at = new Date().toISOString();
  state.selectedTaskId = pendingTaskId;
  state.pendingTaskId = null;
  renderTasks();
  renderPreview(task);
}

export function startRunFeedback(task: WebUITask, actionLabel: string | null = null): void {
  const { state, els } = getLegacyBridge();
  stopRunFeedback();
  state.runFeedbackAction = actionLabel;
  state.runStartedAt = timestampMs(task.started_at || task.created_at) || Date.now();
  state.runTimerId = window.setInterval(updateRunFeedback, 100);
  els.runButton?.classList.add("running");
  updateRunFeedback();
}

export function updateRunFeedback(): void {
  const { state, els } = getLegacyBridge();
  if (!state.runStartedAt) return;
  const elapsed = formatDurationTenths(elapsedMillisecondsSince(state.runStartedAt));
  const action = state.runFeedbackAction || (state.mode === "edit" ? translate("runFeedback.editing") : translate("runFeedback.generating"));
  if (els.runButton) els.runButton.textContent = `${action} ${elapsed}`;
  setStatus(formatTranslation("runFeedback.status", { action, elapsed }), "running");
  updateElapsedDisplays();
  if (state.selectedTaskId === state.pendingTaskId) {
    renderPreview();
  }
}

export function stopRunFeedback(): void {
  const { state, els } = getLegacyBridge();
  if (state.runTimerId) {
    window.clearInterval(state.runTimerId);
  }
  state.runTimerId = null;
  state.runStartedAt = null;
  state.runFeedbackAction = null;
  els.runButton?.classList.remove("running");
  syncRunButtonLabel();
}

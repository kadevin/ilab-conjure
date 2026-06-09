import { getLegacyBridge } from "./state";
import { translate } from "./i18n";

const bridge = getLegacyBridge();
const state = bridge.state;
const els = bridge.els;

function legacyMethod(name: string, ...args: any[]): any {
  const method = getLegacyBridge().methods[name];
  if (typeof method !== "function") {
    throw new Error("Legacy bridge method " + name + " is not available");
  }
  return method(...args);
}

function errorMessage(error: unknown, fallback: string): string {
  return error instanceof Error ? error.message || fallback : fallback;
}

class TaskActionHttpError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = "TaskActionHttpError";
    this.status = status;
  }
}

function isTaskActionConflict(error: unknown): boolean {
  return error instanceof TaskActionHttpError && error.status === 409;
}

function setStatus(...args: any[]) { return legacyMethod("setStatus", ...args); }
function closePromptPopover(...args: any[]) { return legacyMethod("closePromptPopover", ...args); }
function setTaskArchiveState(...args: any[]) { return legacyMethod("setTaskArchiveState", ...args); }
function replaceTask(...args: any[]) { return legacyMethod("replaceTask", ...args); }
function removeBatchSelectedTaskId(...args: any[]) { return legacyMethod("removeBatchSelectedTaskId", ...args); }
function firstVisibleTaskId(...args: any[]) { return legacyMethod("firstVisibleTaskId", ...args); }
function renderTasks(...args: any[]) { return legacyMethod("renderTasks", ...args); }
function updateTaskSelectionVisuals(...args: any[]) { return legacyMethod("updateTaskSelectionVisuals", ...args); }
function renderArchiveButton(...args: any[]) { return legacyMethod("renderArchiveButton", ...args); }
function renderArchiveModal(...args: any[]) { return legacyMethod("renderArchiveModal", ...args); }
function renderPreview(...args: any[]) { return legacyMethod("renderPreview", ...args); }
function openConfirmPopover(...args: any[]) { return legacyMethod("openConfirmPopover", ...args); }
function canRetryFailedTask(...args: any[]) { return legacyMethod("canRetryFailedTask", ...args); }
function canAcceptTaskSuccesses(...args: any[]) { return legacyMethod("canAcceptTaskSuccesses", ...args); }
function currentApiProviderId(...args: any[]) { return legacyMethod("currentApiProviderId", ...args); }
function updateTaskInState(...args: any[]) { return legacyMethod("updateTaskInState", ...args); }

async function refreshTaskAfterActionConflict(taskId: any): Promise<boolean> {
  const normalizedTaskId = String(taskId || "").trim();
  if (!normalizedTaskId) return false;
  try {
    const response = await fetch(`/api/tasks/${encodeURIComponent(normalizedTaskId)}`);
    const data = await response.json().catch(() => ({}));
    if (!response.ok || !data.task) return false;
    const updatedTask = data.task;
    updateTaskInState(updatedTask);
    state.selectedTaskId = updatedTask.task_id;
    renderTasks();
    renderArchiveButton();
    renderArchiveModal();
    renderPreview(updatedTask);
    setStatus(translate("taskActions.updated"), "ok");
    return true;
  } catch (error) {
    console.warn(error);
    return false;
  }
}

async function archiveTask(taskId: any) {
  const task = state.tasks.find((item: any) => String(item.task_id) === String(taskId));
  if (!task) return;
  try {
    const updatedTask = await setTaskArchiveState(taskId, true);
    replaceTask(updatedTask);
    removeBatchSelectedTaskId(taskId);
    if (String(state.selectedTaskId) === String(taskId)) {
      state.selectedTaskId = firstVisibleTaskId();
    }
    renderTasks();
    renderArchiveButton();
    renderArchiveModal();
    renderPreview();
    setStatus(translate("taskActions.archived"), "ok");
  } catch (error) {
    setStatus(errorMessage(error, translate("taskActions.archiveFailed")), "error");
  }
}

async function deleteTask(taskId: any) {
  closePromptPopover();
  try {
    await deleteTaskById(taskId);
    renderTasks();
    renderArchiveButton();
    renderArchiveModal();
    renderPreview();
    setStatus(translate("taskActions.deleted"), "ok");
  } catch (error) {
    setStatus(errorMessage(error, translate("taskActions.deleteFailed")), "error");
  }
}

async function deleteTaskById(taskId: any) {
  const response = await fetch(`/api/tasks/${encodeURIComponent(taskId)}`, {
    method: "DELETE",
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(data.detail || translate("taskActions.deleteFailed"));
  }
  state.tasks = state.tasks.filter((item: any) => String(item.task_id) !== String(taskId));
  removeBatchSelectedTaskId(taskId);
  if (String(state.selectedTaskId) === String(taskId)) {
    state.selectedTaskId = firstVisibleTaskId();
  }
}

async function retryFailedTask(taskId: any) {
  closePromptPopover();
  const task = state.tasks.find((item: any) => String(item.task_id) === String(taskId));
  if (!task || !canRetryFailedTask(task)) {
    if (await refreshTaskAfterActionConflict(taskId)) return;
    setStatus(translate("taskActions.noRetryableFailedImages"), "error");
    return;
  }
  try {
    const response = await fetch(`/api/tasks/${encodeURIComponent(taskId)}/retry-failed`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ api_provider_id: currentApiProviderId() }),
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new TaskActionHttpError(data.detail || translate("taskActions.retryFailedOutputsFailed"), response.status);
    const updatedTask = data.task;
    state.tasks = [updatedTask, ...state.tasks.filter((item: any) => String(item.task_id) !== String(taskId))];
    state.selectedTaskId = updatedTask.task_id;
    renderTasks();
    renderPreview(updatedTask);
    await window.refreshQueue?.();
    setStatus(translate("taskActions.requeuedFailedImages"), "ok");
  } catch (error) {
    if (isTaskActionConflict(error) && await refreshTaskAfterActionConflict(taskId)) return;
    setStatus(errorMessage(error, translate("taskActions.retryFailedOutputsFailed")), "error");
  }
}

async function acceptTaskSuccesses(taskId: any) {
  closePromptPopover();
  const task = state.tasks.find((item: any) => String(item.task_id) === String(taskId));
  if (!task || !canAcceptTaskSuccesses(task)) {
    if (await refreshTaskAfterActionConflict(taskId)) return;
    setStatus(translate("taskActions.noAcceptableSuccessImages"), "error");
    return;
  }
  try {
    const response = await fetch(`/api/tasks/${encodeURIComponent(taskId)}/accept-successes`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new TaskActionHttpError(data.detail || translate("taskActions.acceptSuccessesFailed"), response.status);
    const updatedTask = data.task;
    updateTaskInState(updatedTask);
    state.selectedTaskId = updatedTask.task_id;
    renderTasks();
    renderArchiveButton();
    renderArchiveModal();
    renderPreview(updatedTask);
    setStatus(translate("taskActions.acceptedSuccesses"), "ok");
  } catch (error) {
    if (isTaskActionConflict(error) && await refreshTaskAfterActionConflict(taskId)) return;
    setStatus(errorMessage(error, translate("taskActions.acceptSuccessesFailed")), "error");
  }
}

async function markTaskViewed(taskId: any) {
  if (!taskId || state.taskViewedRequestIds.has(String(taskId))) return;
  const task = state.tasks.find((item: any) => String(item.task_id) === String(taskId));
  if (!task || task.local_pending) return;
  state.taskViewedRequestIds.add(String(taskId));
  const viewedAt = new Date().toISOString();
  task.viewed_at = viewedAt;
  updateTaskSelectionVisuals(taskId);
  try {
    const response = await fetch(`/api/tasks/${encodeURIComponent(taskId)}/viewed`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.detail || translate("taskActions.viewedUpdateFailed"));
    if (data.task) updateTaskInState(data.task);
    updateTaskSelectionVisuals(taskId);
  } catch (error) {
    console.warn(error);
  } finally {
    state.taskViewedRequestIds.delete(String(taskId));
  }
}

function openTaskDeleteConfirm(deleteButton: any, taskId: any) {
  closePromptPopover();
  const task = state.tasks.find((item) => String(item.task_id) === String(taskId));
  if (!task) return;
  if (task.status === "running" || task.local_pending) {
    setStatus(translate("taskActions.runningCannotDelete"), "error");
    return;
  }

  const title = task.prompt || task.mode || taskId;
  openConfirmPopover(deleteButton, {
    title: translate("taskActions.deleteTitle"),
    message: translate("taskActions.deleteMessage"),
    detail: title,
    confirmText: translate("action.delete"),
    onConfirm: async () => {
      await deleteTask(taskId);
    },
  });
}

export function initTaskActionsFeature() {
  Object.assign(getLegacyBridge().methods, {
    archiveTask,
    deleteTask,
    deleteTaskById,
    retryFailedTask,
    acceptTaskSuccesses,
    markTaskViewed,
    openTaskDeleteConfirm,
  });
}

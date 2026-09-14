import { getLegacyBridge } from "./state";
import { translate } from "./i18n";
import { prefersReducedMotion } from "./webui-utils";

const bridge = getLegacyBridge();
const state = bridge.state;
const els = bridge.els;
const TASK_CARD_REMOVING_CLASS = "task-card-removing";
const TASK_CARD_REMOVAL_FALLBACK_MS = 320;
const TASK_CARD_REFLOW_DURATION_MS = 180;
const TASK_CARD_REFLOW_EASING = "cubic-bezier(0.22, 1, 0.36, 1)";

type TaskCardLayout = Record<string, { left: number; top: number }>;
type TaskCardRemovalAction = "default" | "archive" | "delete";

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
function captureTaskHistoryLayout(...args: any[]) { return legacyMethod("captureTaskHistoryLayout", ...args); }
function animateTaskHistoryLayout(...args: any[]) { return legacyMethod("animateTaskHistoryLayout", ...args); }
function refreshTasksAfterDeletion(...args: any[]) { return legacyMethod("refreshTasksAfterDeletion", ...args); }

function taskCardElements() {
  return Array.from(document.querySelectorAll<HTMLElement>(".task-card[data-task-id]"));
}

function normalizedTaskIdSet(taskIds: any[]) {
  return new Set(taskIds.map((taskId) => String(taskId || "")).filter(Boolean));
}

function captureTaskCardLayout(excludedTaskIds: any[] = []): TaskCardLayout {
  const excluded = normalizedTaskIdSet(excludedTaskIds);
  return taskCardElements().reduce((layout, card) => {
    const taskId = String(card.dataset.taskId || "");
    if (!taskId || excluded.has(taskId)) return layout;
    const rect = card.getBoundingClientRect();
    layout[taskId] = { left: rect.left, top: rect.top };
    return layout;
  }, {} as TaskCardLayout);
}

function animateTaskCardReflow(previousLayout: TaskCardLayout) {
  if (prefersReducedMotion()) return;
  requestAnimationFrame(() => {
    taskCardElements().forEach((card) => {
      const taskId = String(card.dataset.taskId || "");
      const previous = previousLayout[taskId];
      if (!previous) return;
      const rect = card.getBoundingClientRect();
      const dx = previous.left - rect.left;
      const dy = previous.top - rect.top;
      if (Math.abs(dx) <= 0.5 && Math.abs(dy) <= 0.5) return;
      const computedTransform = getComputedStyle(card).transform;
      const settledTransform = computedTransform === "none" ? "translate(0px, 0px)" : computedTransform;
      card.animate(
        [
          { transform: `translate(${dx}px, ${dy}px) ${settledTransform}` },
          { transform: settledTransform },
        ],
        {
          duration: TASK_CARD_REFLOW_DURATION_MS,
          easing: TASK_CARD_REFLOW_EASING,
        },
      );
    });
  });
}

function waitForTaskCardRemoval(card: HTMLElement, action: TaskCardRemovalAction) {
  return new Promise<void>((resolve) => {
    let settled = false;
    const finish = () => {
      if (settled) return;
      settled = true;
      resolve();
    };
    card.addEventListener("animationend", finish, { once: true });
    window.setTimeout(finish, TASK_CARD_REMOVAL_FALLBACK_MS);
    card.classList.add(TASK_CARD_REMOVING_CLASS);
    card.dataset.taskRemovalAction = action;
    card.setAttribute("aria-busy", "true");
    card.tabIndex = -1;
  });
}

async function runTaskCardRemovalTransition(
  taskIds: any[],
  commit: () => void,
  action: TaskCardRemovalAction = "default",
) {
  const removingIds = normalizedTaskIdSet(taskIds);
  const previousCardLayout = captureTaskCardLayout([...removingIds]);
  const previousHistoryLayout = captureTaskHistoryLayout();
  const removingCards = taskCardElements().filter(
    (card) => removingIds.has(String(card.dataset.taskId || "")),
  );

  if (!prefersReducedMotion() && removingCards.length) {
    await Promise.all(removingCards.map((card) => waitForTaskCardRemoval(card, action)));
  }

  commit();
  animateTaskCardReflow(previousCardLayout);
  animateTaskHistoryLayout(previousHistoryLayout);
}

function taskListStructureKey(task: any): string {
  if (!task) return "";
  return JSON.stringify([
    task.status,
    task.local_pending,
    task.updated_at,
    task.completed_at,
    task.started_at,
    task.generated_count,
    task.failed_count,
    task.total_count,
    task.output_url,
    Array.isArray(task.output_urls) ? task.output_urls.join("|") : "",
    Array.isArray(task.thumbnail_urls) ? task.thumbnail_urls.join("|") : "",
    Array.isArray(task.input_thumbnail_urls) ? task.input_thumbnail_urls.join("|") : "",
    Array.isArray(task.outputs)
      ? task.outputs.map((item: any) => [
        item?.index,
        item?.status,
        item?.url,
        item?.thumbnail_url,
        item?.error,
        item?.completed_at,
      ].join(":")).join("|")
      : "",
  ]);
}

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
    renderTasks({ preserveScroll: true });
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
  if (!task) return false;
  try {
    const updatedTask = await setTaskArchiveState(taskId, true);
    replaceTask(updatedTask);
    removeBatchSelectedTaskId(taskId);
    if (String(state.selectedTaskId) === String(taskId)) {
      state.selectedTaskId = firstVisibleTaskId();
    }
    await runTaskCardRemovalTransition([taskId], renderTasks, "archive");
    renderArchiveButton();
    renderArchiveModal();
    renderPreview();
    setStatus(translate("taskActions.archived"), "ok");
    return true;
  } catch (error) {
    setStatus(errorMessage(error, translate("taskActions.archiveFailed")), "error");
    return false;
  }
}

async function deleteTask(taskId: any) {
  closePromptPopover();
  try {
    await deleteTaskById(taskId);
    await runTaskCardRemovalTransition([taskId], renderTasks, "delete");
    await refreshTasksAfterDeletion();
    renderArchiveButton();
    renderArchiveModal();
    renderPreview();
    setStatus(translate("taskActions.deleted"), "ok");
    return true;
  } catch (error) {
    setStatus(errorMessage(error, translate("taskActions.deleteFailed")), "error");
    return false;
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
    renderTasks({ preserveScroll: true });
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
  const beforeStructureKey = taskListStructureKey(task);
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
    let renderedStructuralUpdate = false;
    if (data.task) {
      const afterStructureKey = taskListStructureKey(data.task);
      const updated = updateTaskInState(data.task);
      if (updated && beforeStructureKey !== afterStructureKey) {
        renderTasks({ preserveScroll: true });
        renderArchiveButton();
        renderArchiveModal();
        renderPreview(data.task);
        renderedStructuralUpdate = true;
      }
    }
    if (!renderedStructuralUpdate) updateTaskSelectionVisuals(taskId);
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
  if (task.status === "running" || task.status === "cancelling" || task.local_pending) {
    setStatus(translate("taskActions.runningCannotDelete"), "error");
    return;
  }

  const title = task.prompt || task.mode || taskId;
  openConfirmPopover(deleteButton, {
    title: translate("taskActions.deleteTitle"),
    focusCancel: true,
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
    runTaskCardRemovalTransition,
    retryFailedTask,
    acceptTaskSuccesses,
    markTaskViewed,
    openTaskDeleteConfirm,
  });
}

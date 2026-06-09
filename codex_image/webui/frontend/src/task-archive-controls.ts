import { getLegacyBridge } from "./state";
import { formatTranslation, LOCALE_CHANGE_EVENT, translate } from "./i18n";

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

const ARCHIVED_TASKS_STORAGE_KEY = "codex-image-archived-task-ids";

function errorMessage(error: unknown, fallback: string): string {
  return error instanceof Error ? error.message || fallback : fallback;
}

function setStatus(...args: any[]) { return legacyMethod("setStatus", ...args); }
function renderTasks(...args: any[]) { return legacyMethod("renderTasks", ...args); }
function renderPreview(...args: any[]) { return legacyMethod("renderPreview", ...args); }
function closePromptPopover(...args: any[]) { return legacyMethod("closePromptPopover", ...args); }
function taskThumbHtml(...args: any[]) { return legacyMethod("taskThumbHtml", ...args); }
function escapeHtml(...args: any[]) { return legacyMethod("escapeHtml", ...args); }
function formatTaskStatus(...args: any[]) { return legacyMethod("formatTaskStatus", ...args); }
function openTaskDeleteConfirm(...args: any[]) { return legacyMethod("openTaskDeleteConfirm", ...args); }
function taskArchived(task: any) {
  return Boolean(task?.archived_at);
}

function restoreLegacyArchivedTasks() {
  try {
    const stored = JSON.parse(localStorage.getItem(ARCHIVED_TASKS_STORAGE_KEY) || "[]");
    state.legacyArchivedTaskIds = Array.isArray(stored) ? stored.filter(Boolean).map(String) : [];
  } catch {
    state.legacyArchivedTaskIds = [];
  }
}

function clearLegacyArchivedTasks() {
  try {
    localStorage.removeItem(ARCHIVED_TASKS_STORAGE_KEY);
  } catch {
    // Browser storage may be unavailable in restricted contexts.
  }
  state.legacyArchivedTaskIds = [];
}

function isTaskArchived(taskId: any) {
  const id = String(taskId);
  const task = state.tasks.find((item) => String(item.task_id) === id);
  return taskArchived(task) || state.legacyArchivedTaskIds.includes(id);
}

function firstVisibleTaskId() {
  return state.tasks.find((task) => !isTaskArchived(task.task_id))?.task_id || null;
}

function replaceTask(updatedTask: any) {
  if (!updatedTask?.task_id) return;
  state.tasks = state.tasks.map((task) => (
    String(task.task_id) === String(updatedTask.task_id) ? updatedTask : task
  ));
}

function cleanupSessionSelections() {
  const taskIds = new Set(state.tasks.map((task) => String(task.task_id)));
  state.batchSelectedTaskIds = state.batchSelectedTaskIds.filter((taskId: any) => {
    return taskIds.has(String(taskId)) && !isTaskArchived(taskId);
  });
}

async function setTaskArchiveState(taskId: any, archived: any) {
  const response = await fetch(`/api/tasks/${encodeURIComponent(taskId)}/archive`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ archived }),
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.detail || (archived ? translate("archive.archiveFailed") : translate("archive.restoreFailed")));
  return data.task;
}

async function migrateLegacyArchivedTasks() {
  const ids = state.legacyArchivedTaskIds.filter((taskId: any) => {
    const task = state.tasks.find((item) => String(item.task_id) === String(taskId));
    return task && !taskArchived(task);
  });
  if (!ids.length) {
    clearLegacyArchivedTasks();
    return;
  }

  const results = await Promise.allSettled(ids.map((taskId: any) => setTaskArchiveState(taskId, true)));
  let hasFailure = false;
  results.forEach((result) => {
    if (result.status === "fulfilled") {
      replaceTask(result.value);
    } else {
      hasFailure = true;
    }
  });
  if (!hasFailure) {
    clearLegacyArchivedTasks();
  }
}

function renderArchiveButton() {
  if (!els.archiveButton) return;
  const count = state.tasks.filter((task) => isTaskArchived(task.task_id)).length;
  els.archiveButton.textContent = count
    ? formatTranslation("footer.archiveCount", { count })
    : translate("footer.archive");
}

async function restoreArchivedTask(taskId: any) {
  try {
    const updatedTask = await setTaskArchiveState(taskId, false);
    replaceTask(updatedTask);
    renderTasks();
    renderArchiveButton();
    renderArchiveModal();
    setStatus(translate("archive.restored"), "ok");
  } catch (error) {
    setStatus(errorMessage(error, translate("archive.restoreFailed")), "error");
  }
}

function openArchiveModal() {
  closePromptPopover();
  renderArchiveModal();
  els.archiveModal?.classList.remove("hidden");
  els.archiveModal?.setAttribute("aria-hidden", "false");
}

function closeArchiveModal() {
  els.archiveModal?.classList.add("hidden");
  els.archiveModal?.setAttribute("aria-hidden", "true");
}

function renderArchiveModal() {
  if (!els.archiveList || !els.archiveCount) return;
  const archivedTasks = state.tasks.filter((task) => isTaskArchived(task.task_id));
  els.archiveCount.textContent = archivedTasks.length
    ? formatTranslation("archive.count", { count: archivedTasks.length })
    : translate("archive.empty");
  if (!archivedTasks.length) {
    els.archiveList.innerHTML = `<div class="archive-empty">${translate("archive.empty")}</div>`;
    return;
  }

  els.archiveList.innerHTML = archivedTasks.map((task) => {
    const image = taskThumbHtml(task, "archive-thumb");
    const title = escapeHtml(task.prompt || task.mode || "Untitled");
    const status = escapeHtml(formatTaskStatus(task));
    const size = escapeHtml(task.output_size || task.params?.size || "");
    const taskId = escapeHtml(task.task_id);
    return `
      <article class="archive-card" data-archive-select-task-id="${taskId}">
        ${image}
        <div class="archive-info">
          <strong>${title}</strong>
          <span>${status} · ${size}</span>
        </div>
        <div class="archive-card-actions">
          <button class="ghost-button text-sm" type="button" data-restore-archive-task-id="${taskId}">${translate("archive.restore")}</button>
          <button class="ghost-button text-sm danger-button" type="button" data-delete-archive-task-id="${taskId}">${translate("action.delete")}</button>
        </div>
      </article>
    `;
  }).join("");

  els.archiveList.querySelectorAll("[data-archive-select-task-id]").forEach((card: any) => {
    card.addEventListener("click", () => {
      legacyMethod("selectTask", card.dataset.archiveSelectTaskId);
      closeArchiveModal();
    });
  });
  els.archiveList.querySelectorAll("[data-restore-archive-task-id]").forEach((button: any) => {
    button.addEventListener("click", (event: any) => {
      event.stopPropagation();
      restoreArchivedTask(button.dataset.restoreArchiveTaskId);
    });
  });
  els.archiveList.querySelectorAll("[data-delete-archive-task-id]").forEach((button: any) => {
    button.addEventListener("click", (event: any) => {
      event.stopPropagation();
      openTaskDeleteConfirm(button, button.dataset.deleteArchiveTaskId);
    });
  });
}

export function initTaskArchiveControlsFeature() {
  document.addEventListener(LOCALE_CHANGE_EVENT, () => {
    renderArchiveButton();
    renderArchiveModal();
  });
  Object.assign(getLegacyBridge().methods, {
    taskArchived,
    restoreLegacyArchivedTasks,
    clearLegacyArchivedTasks,
    isTaskArchived,
    firstVisibleTaskId,
    replaceTask,
    cleanupSessionSelections,
    setTaskArchiveState,
    migrateLegacyArchivedTasks,
    renderArchiveButton,
    restoreArchivedTask,
    openArchiveModal,
    closeArchiveModal,
    renderArchiveModal,
  });
}

import { getLegacyBridge } from "./state";

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

const updateTaskInState = (...args: any[]) => legacyMethod("updateTaskInState", ...args);
const cleanupSessionSelections = (...args: any[]) => legacyMethod("cleanupSessionSelections", ...args);
const renderTasks = (...args: any[]) => legacyMethod("renderTasks", ...args);
const renderArchiveButton = (...args: any[]) => legacyMethod("renderArchiveButton", ...args);
const renderArchiveModal = (...args: any[]) => legacyMethod("renderArchiveModal", ...args);
const renderPreview = (...args: any[]) => legacyMethod("renderPreview", ...args);
const migrateLegacyArchivedTasks = (...args: any[]) => legacyMethod("migrateLegacyArchivedTasks", ...args);
const revokeTaskUploadPreviewUrls = (...args: any[]) => legacyMethod("revokeTaskUploadPreviewUrls", ...args);
const taskHasViewableUpdate = (...args: any[]) => legacyMethod("taskHasViewableUpdate", ...args);
const markTaskViewed = (...args: any[]) => legacyMethod("markTaskViewed", ...args);
const ensureSelectedTaskDetail = (...args: any[]) => legacyMethod("ensureSelectedTaskDetail", ...args);
const TASK_SEARCH_HISTORY_LIMIT = 100;
const TASK_SEARCH_HISTORY_DEBOUNCE_MS = 180;
let taskSearchHistoryTimerId = 0;

async function refreshTasks({ migrateLegacyArchives = false }: any = {}) {
  const requestSeq = ++state.tasksRequestSeq;
  const response = await fetch("/api/tasks/recent?limit=200");
  const data = await response.json();
  if (requestSeq !== state.tasksRequestSeq) return;
  await applyTasksSnapshot(data.tasks || [], { migrateLegacyArchives, requestSeq });
}

async function applyTasksSnapshot(tasks: any, { migrateLegacyArchives = false, requestSeq = state.tasksRequestSeq }: any = {}) {
  const previousLocalPendingTasks = state.tasks.filter((task: any) => task?.local_pending);
  const pendingTask = state.pendingTaskId ? state.tasks.find((task: any) => task.task_id === state.pendingTaskId) : null;
  state.tasks = Array.isArray(tasks) ? tasks : [];
  if (pendingTask?.local_pending && !state.tasks.some((task: any) => task.task_id === pendingTask.task_id)) {
    state.tasks.unshift(pendingTask);
  }
  const retainedTasks = new Set(state.tasks);
  previousLocalPendingTasks.forEach((task: any) => {
    if (!retainedTasks.has(task)) revokeTaskUploadPreviewUrls(task);
  });
  if (migrateLegacyArchives) {
    await migrateLegacyArchivedTasks();
    if (requestSeq !== state.tasksRequestSeq) return;
  }
  cleanupSessionSelections();
  renderTasks();
  renderArchiveButton();
  renderArchiveModal();
  await renderSelectedTaskPreview(requestSeq);
}

async function applyTaskUpdate(task: any) {
  if (!updateTaskInState(task)) return;
  if (String(task.task_id) === String(state.selectedTaskId) && taskHasViewableUpdate(task)) {
    void markTaskViewed(task.task_id);
  }
  cleanupSessionSelections();
  renderTasks();
  renderArchiveButton();
  renderArchiveModal();
  await renderSelectedTaskPreview();
}

function currentTaskSearchQuery(): string {
  return String(els.taskSearch?.value || "").trim();
}

function activeOrSelectedTask(task: any): boolean {
  const taskId = String(task?.task_id || "");
  const status = String(task?.status || "");
  return Boolean(taskId && (
    String(state.selectedTaskId || "") === taskId
    || task?.local_pending
    || ["submitting", "queued", "running"].includes(status)
  ));
}

function historyTaskSummaryToSidebarTask(task: any) {
  const size = String(task.size || "");
  const promptFidelity = String(task.prompt_mode || "");
  const providerName = String(task.provider || "");
  return {
    task_id: String(task.task_id || ""),
    summary_only: true,
    created_at: String(task.created_at || ""),
    updated_at: String(task.updated_at || ""),
    completed_at: String(task.completed_at || ""),
    status: String(task.status || ""),
    mode: String(task.mode || ""),
    prompt: String(task.prompt_preview || task.task_id || ""),
    output_size: size,
    params: {
      size,
      n: Number(task.total_count || 1) || 1,
      prompt_fidelity: promptFidelity,
      api_provider_name: providerName,
    },
    backend: String(task.backend || ""),
    requested_backend: String(task.backend || ""),
    api_provider_name: providerName,
    generated_count: Number(task.generated_count || 0) || 0,
    failed_count: Number(task.failed_count || 0) || 0,
    total_count: Number(task.total_count || 1) || 1,
    thumbnail_urls: task.thumbnail_url ? [String(task.thumbnail_url)] : [],
  };
}

function mergeTaskSearchHistoryResults(tasks: any[]) {
  const previousResultIds = new Set((state.taskSearchHistoryResultIds || []).map(String));
  const nextTasks = tasks.map(historyTaskSummaryToSidebarTask).filter((task) => task.task_id);
  const nextById = new Map(nextTasks.map((task) => [String(task.task_id), task]));
  const nextIds = new Set(nextById.keys());
  const merged: any[] = [];
  const seen = new Set<string>();
  state.tasks.forEach((task: any) => {
    const taskId = String(task?.task_id || "");
    if (!taskId) return;
    if (previousResultIds.has(taskId) && !nextIds.has(taskId) && !activeOrSelectedTask(task)) {
      return;
    }
    const replacement = nextById.get(taskId);
    if (replacement) {
      merged.push(task);
      seen.add(taskId);
      return;
    }
    merged.push(task);
  });
  nextTasks.forEach((task) => {
    if (seen.has(String(task.task_id))) return;
    merged.push(task);
  });
  state.tasks = merged;
  state.taskSearchHistoryResultIds = Array.from(nextIds);
  state.tasksRenderKey = null;
}

function clearTaskSearchHistoryResults() {
  const previousResultIds = new Set((state.taskSearchHistoryResultIds || []).map(String));
  if (!previousResultIds.size) return;
  state.tasks = state.tasks.filter((task: any) => {
    const taskId = String(task?.task_id || "");
    return !previousResultIds.has(taskId) || activeOrSelectedTask(task);
  });
  state.taskSearchHistoryResultIds = [];
  state.tasksRenderKey = null;
}

async function fetchTaskSearchHistoryResults(query: string, requestSeq: number) {
  const params = new URLSearchParams();
  params.set("q", query);
  params.set("limit", String(TASK_SEARCH_HISTORY_LIMIT));
  params.set("archived", "false");
  const response = await fetch(`/api/task-history/tasks?${params.toString()}`);
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.detail || "Task history search failed");
  if (requestSeq !== state.taskSearchHistoryRequestSeq || currentTaskSearchQuery() !== query) return;
  mergeTaskSearchHistoryResults(Array.isArray(data.tasks) ? data.tasks : []);
  renderTasks({ preserveScroll: true });
}

async function syncTaskSearchHistoryResults() {
  window.clearTimeout(taskSearchHistoryTimerId);
  const query = currentTaskSearchQuery();
  const requestSeq = ++state.taskSearchHistoryRequestSeq;
  if (!query) {
    clearTaskSearchHistoryResults();
    renderTasks({ preserveScroll: true });
    return;
  }
  taskSearchHistoryTimerId = window.setTimeout(() => {
    void fetchTaskSearchHistoryResults(query, requestSeq).catch((error) => {
      if (requestSeq !== state.taskSearchHistoryRequestSeq) return;
      console.warn(error);
    });
  }, TASK_SEARCH_HISTORY_DEBOUNCE_MS);
}

async function renderSelectedTaskPreview(requestSeq: number | null = null) {
  const selectedTask = state.tasks.find((item: any) => String(item.task_id) === String(state.selectedTaskId));
  if (selectedTask?.summary_only) {
    try {
      const detailedTask = await ensureSelectedTaskDetail(selectedTask.task_id);
      if (requestSeq !== null && requestSeq !== state.tasksRequestSeq) return;
      if (detailedTask) {
        renderPreview(detailedTask);
        return;
      }
    } catch (error) {
      console.warn(error);
      if (requestSeq !== null && requestSeq !== state.tasksRequestSeq) return;
    }
  }
  renderPreview();
}

export function initTaskFeature() {
  Object.assign(getLegacyBridge().methods, {
    refreshTasks,
    applyTasksSnapshot,
    applyTaskUpdate,
    syncTaskSearchHistoryResults,
  });
}

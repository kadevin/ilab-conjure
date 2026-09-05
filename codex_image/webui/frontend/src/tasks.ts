import { getLegacyBridge } from "./state";
import {
  historyTaskRevealDestination,
  historyTaskRevealLayoutReady,
  sidebarTaskDateBucket,
  sidebarTaskRevealPagePlan,
} from "./history-task-reveal-model";
import { cssEscape } from "./webui-utils";

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
const TASK_SIDEBAR_GROUP_PAGE_SIZE = 50;
const TASK_SIDEBAR_REVEAL_PAGE_SIZE = 100;
const HISTORY_TASK_REVEAL_LAYOUT_TIMEOUT_MS = 5000;
let taskSearchHistoryTimerId = 0;

function activeHistoryTaskReveal() {
  const reveal = state.historyTaskReveal;
  if (!reveal?.ready) return null;
  if (String(reveal.taskId || "") !== String(state.selectedTaskId || "")) return null;
  return reveal;
}

function mergeSidebarTasks(baseTasks: any[], incomingTasks: any[]) {
  const merged = [...baseTasks];
  const indexById = new Map(
    merged.map((task: any, index: number) => [String(task?.task_id || ""), index]),
  );
  incomingTasks.forEach((incoming: any) => {
    const taskId = String(incoming?.task_id || "");
    if (!taskId) return;
    const index = indexById.get(taskId);
    if (index === undefined) {
      indexById.set(taskId, merged.length);
      merged.push(incoming);
      return;
    }
    const existing = merged[index];
    if (existing?.summary_only !== true && incoming?.summary_only === true) return;
    merged[index] = incoming;
  });
  return merged;
}

function retainHistoryTaskRevealAfterSnapshot() {
  const reveal = activeHistoryTaskReveal();
  if (!reveal) return;
  const retained = reveal.kind === "group" && reveal.groupTasks.length
    ? reveal.groupTasks
    : [reveal.task];
  state.tasks = mergeSidebarTasks(state.tasks, retained);
  if (reveal.kind === "group") {
    state.taskSidebarGroupLoadedCounts[reveal.groupKey] = Math.max(
      Number(state.taskSidebarGroupLoadedCounts?.[reveal.groupKey] || 0),
      Number(reveal.loadedCount || 0),
    );
  }
}

function normalizedTaskSearchResultQuery(query: string): string {
  return String(query || "").trim().toLowerCase();
}

async function refreshTasks({ migrateLegacyArchives = false }: any = {}) {
  const requestSeq = ++state.tasksRequestSeq;
  const response = await fetch("/api/tasks/sidebar?limit=50");
  const data = await response.json();
  if (requestSeq !== state.tasksRequestSeq) return;
  await applyTasksSnapshot(data.tasks || [], {
    migrateLegacyArchives,
    requestSeq,
    taskGroups: data.task_groups,
  });
}

async function applyTasksSnapshot(
  tasks: any,
  {
    migrateLegacyArchives = false,
    requestSeq = state.tasksRequestSeq,
    taskGroups,
  }: any = {},
) {
  const previousLocalPendingTasks = state.tasks.filter((task: any) => task?.local_pending);
  const pendingTask = state.pendingTaskId ? state.tasks.find((task: any) => task.task_id === state.pendingTaskId) : null;
  state.tasks = mergeActiveQueueTaskDetails(Array.isArray(tasks) ? tasks : []);
  if (Array.isArray(taskGroups)) {
    state.taskSidebarGroupLoadError = null;
    state.taskSidebarGroupCounts = Object.fromEntries(
      taskGroups.map((group: any) => [String(group?.key || ""), Math.max(0, Number(group?.count || 0))]),
    );
    state.taskSidebarGroupLoadedCounts = Object.fromEntries(
      taskGroups.map((group: any) => [String(group?.key || ""), Array.isArray(group?.tasks) ? group.tasks.length : 0]),
    );
  }
  retainHistoryTaskRevealAfterSnapshot();
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
  renderTasks({ preserveScroll: true });
  renderArchiveButton();
  renderArchiveModal();
  await renderSelectedTaskPreview(requestSeq);
}

function mergeActiveQueueTaskDetails(tasks: any[]) {
  const activeTasks = [
    ...(Array.isArray(state.queue?.waiting) ? state.queue.waiting : []),
    ...(Array.isArray(state.queue?.running) ? state.queue.running : []),
  ];
  const activeById = new Map(
    activeTasks
      .filter((task: any) => task?.task_id)
      .map((task: any) => [String(task.task_id), task]),
  );
  const merged = tasks.map((task: any) => {
    const taskId = String(task?.task_id || "");
    const activeTask = activeById.get(taskId);
    if (!activeTask) return task;
    activeById.delete(taskId);
    return { ...task, ...activeTask, summary_only: false };
  });
  activeById.forEach((task: any) => {
    merged.push({ ...task, summary_only: false });
  });
  return merged;
}

async function loadMoreSidebarTaskGroup(groupKey: any, { manual = false }: any = {}) {
  const key = String(groupKey || "");
  if (!key || state.taskSidebarGroupLoading) return false;
  if (!manual && String(state.taskSidebarGroupLoadError || "") === key) return false;
  const offset = Math.max(0, Number(state.taskSidebarGroupLoadedCounts?.[key] || 0));
  state.taskSidebarGroupLoading = key;
  state.taskSidebarGroupLoadError = null;
  try {
    const response = await fetch(
      `/api/tasks/sidebar/groups/${encodeURIComponent(key)}?offset=${offset}&limit=${TASK_SIDEBAR_GROUP_PAGE_SIZE}`,
    );
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.detail || "Task group loading failed");
    const incoming = Array.isArray(data.tasks) ? data.tasks : [];
    const incomingById = new Map(incoming.map((task: any) => [String(task?.task_id || ""), task]));
    state.tasks = state.tasks.map((task: any) => incomingById.get(String(task?.task_id || "")) || task);
    const existingIds = new Set(state.tasks.map((task: any) => String(task?.task_id || "")));
    incoming.forEach((task: any) => {
      const taskId = String(task?.task_id || "");
      if (!taskId || existingIds.has(taskId)) return;
      state.tasks.push(task);
      existingIds.add(taskId);
    });
    state.taskSidebarGroupCounts[key] = Math.max(0, Number(data.count || 0));
    state.taskSidebarGroupLoadedCounts[key] = Math.max(offset, Number(data.next_offset || offset + incoming.length));
    return true;
  } catch (_error) {
    state.taskSidebarGroupLoadError = key;
    return false;
  } finally {
    state.taskSidebarGroupLoading = null;
    renderTasks({ preserveScroll: true, appendGroupKey: key });
  }
}

async function fetchSidebarRevealPage(groupKey: string, offset: number) {
  const response = await fetch(
    `/api/tasks/sidebar/groups/${encodeURIComponent(groupKey)}?offset=${offset}&limit=${TASK_SIDEBAR_REVEAL_PAGE_SIZE}`,
  );
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.detail || "Task group loading failed");
  return data;
}

async function loadSidebarTaskGroupThroughTarget(reveal: any): Promise<boolean> {
  const groupKey = String(reveal.groupKey || "");
  const taskId = String(reveal.taskId || "");
  for (let attempt = 0; attempt < 2; attempt += 1) {
    const positionResponse = await fetch(
      `/api/tasks/sidebar/groups/${encodeURIComponent(groupKey)}/position/${encodeURIComponent(taskId)}`,
    );
    const positionData = await positionResponse.json().catch(() => ({}));
    if (!positionResponse.ok) throw new Error(positionData.detail || "Task position loading failed");
    if (!positionData.found) return false;
    const targetLoaded = state.tasks.some((task: any) => String(task?.task_id || "") === taskId);
    const loadedCount = Math.max(0, Number(state.taskSidebarGroupLoadedCounts?.[groupKey] || 0));
    const plan = sidebarTaskRevealPagePlan({
      targetIndex: Number(positionData.position),
      targetLoaded,
      loadedCount,
      pageSize: TASK_SIDEBAR_REVEAL_PAGE_SIZE,
    });
    if (!plan.found) return false;
    const pages = await Promise.all(plan.offsets.map((offset) => fetchSidebarRevealPage(groupKey, offset)));
    const fetchedTasks = pages.flatMap((page: any) => Array.isArray(page.tasks) ? page.tasks : []);
    if (!targetLoaded && !fetchedTasks.some((task: any) => String(task?.task_id || "") === taskId)) {
      continue;
    }
    const existingGroupTasks = state.tasks.filter((task: any) => (
      sidebarTaskDateBucket(task) === groupKey && !task?.archived_at
    ));
    const groupTasks = mergeSidebarTasks(
      mergeSidebarTasks(existingGroupTasks, fetchedTasks),
      [reveal.task],
    );
    const loadedThrough = pages.reduce((maximum: number, page: any, index: number) => {
      const offset = plan.offsets[index] || 0;
      return Math.max(maximum, Number(page.next_offset || offset + (page.tasks?.length || 0)));
    }, loadedCount);
    reveal.ready = true;
    reveal.groupTasks = groupTasks;
    reveal.loadedCount = loadedThrough;
    state.tasks = mergeSidebarTasks(state.tasks, groupTasks);
    state.taskSidebarGroupCounts[groupKey] = Math.max(
      Number(state.taskSidebarGroupCounts?.[groupKey] || 0),
      Number(positionData.count || 0),
      ...pages.map((page: any) => Number(page.count || 0)),
    );
    state.taskSidebarGroupLoadedCounts[groupKey] = loadedThrough;
    return true;
  }
  return false;
}

function activateTransientHistoryTaskReveal(reveal: any) {
  reveal.kind = "transient";
  reveal.groupKey = "current";
  reveal.ready = true;
  reveal.groupTasks = [reveal.task];
  reveal.loadedCount = 1;
  state.tasks = mergeSidebarTasks(state.tasks, [reveal.task]);
}

async function scrollHistoryTaskCardIntoView(taskId: string): Promise<boolean> {
  const selector = `.task-card[data-task-id="${cssEscape(taskId)}"]`;
  const deadline = Date.now() + HISTORY_TASK_REVEAL_LAYOUT_TIMEOUT_MS;
  while (Date.now() <= deadline) {
    const card = (els.taskHistoryShell || els.taskList)?.querySelector?.(selector);
    const groupItems = card instanceof HTMLElement
      ? card.closest("[data-task-group]")?.querySelector(".task-group-items-expanded")
      : null;
    if (historyTaskRevealLayoutReady({
      cardFound: card instanceof HTMLElement,
      groupRenderComplete: groupItems instanceof HTMLElement && groupItems.dataset.renderComplete === "true",
      groupLayoutStable: groupItems instanceof HTMLElement && groupItems.style.maxHeight === "none",
    }) && card instanceof HTMLElement) {
      card.scrollIntoView({
        block: "center",
        inline: "nearest",
        behavior: "auto",
      });
      card.focus({ preventScroll: true });
      return true;
    }
    await new Promise<void>((resolve) => requestAnimationFrame(() => resolve()));
  }
  return false;
}

async function revealHistoryTaskInSidebar(task: any): Promise<boolean> {
  const taskId = String(task?.task_id || "");
  if (!taskId) return false;
  const sequence = ++state.historyTaskRevealSeq;
  const destination = historyTaskRevealDestination(task);
  const reveal = {
    taskId,
    task,
    kind: destination.kind,
    groupKey: destination.groupKey,
    ready: false,
    groupTasks: [],
    loadedCount: 0,
  };
  state.historyTaskReveal = reveal;
  try {
    await refreshTasks();
  } catch (error) {
    console.warn(error);
  }
  if (sequence !== state.historyTaskRevealSeq || state.historyTaskReveal !== reveal) return false;
  if (reveal.kind === "group") {
    try {
      const located = await loadSidebarTaskGroupThroughTarget(reveal);
      if (!located) activateTransientHistoryTaskReveal(reveal);
    } catch (error) {
      console.warn(error);
      activateTransientHistoryTaskReveal(reveal);
    }
  } else {
    activateTransientHistoryTaskReveal(reveal);
  }
  if (sequence !== state.historyTaskRevealSeq || state.historyTaskReveal !== reveal) return false;
  legacyMethod("setExpandedTaskGroupKey", reveal.groupKey, { immediate: true });
  state.expandedTaskGroupAnimationPending = false;
  state.tasksRenderKey = null;
  renderTasks();
  return scrollHistoryTaskCardIntoView(taskId);
}

async function refreshTasksAfterDeletion() {
  await refreshTasks();
}

async function applyTaskUpdate(task: any) {
  const previousTask = state.tasks.find((item: any) => String(item?.task_id || "") === String(task?.task_id || ""));
  const movedFromActiveToHistory = Boolean(
    previousTask
    && ["submitting", "queued", "running"].includes(String(previousTask.status || ""))
    && !["submitting", "queued", "running"].includes(String(task?.status || "")),
  );
  if (!updateTaskInState(task)) return;
  if (String(task.task_id) === String(state.selectedTaskId) && taskHasViewableUpdate(task)) {
    void markTaskViewed(task.task_id);
  }
  cleanupSessionSelections();
  renderTasks({ preserveScroll: true });
  renderArchiveButton();
  renderArchiveModal();
  await renderSelectedTaskPreview();
  if (movedFromActiveToHistory) {
    await refreshTasks();
  }
}

function currentTaskSearchQuery(): string {
  return String(state.taskSearchQuery || "").trim();
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
    terminal_at: String(task.terminal_at || task.completed_at || ""),
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

function mergeTaskSearchHistoryResults(tasks: any[], query: string) {
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
  state.taskSearchHistoryResultQuery = normalizedTaskSearchResultQuery(query);
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
  state.taskSearchHistoryResultQuery = "";
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
  mergeTaskSearchHistoryResults(Array.isArray(data.tasks) ? data.tasks : [], query);
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
    loadMoreSidebarTaskGroup,
    revealHistoryTaskInSidebar,
    scrollHistoryTaskCardIntoView,
    refreshTasksAfterDeletion,
    syncTaskSearchHistoryResults,
  });
}

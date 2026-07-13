import { getEls } from "./dom";
import { formatTranslation, LOCALE_CHANGE_EVENT, translate } from "./i18n";
import { getLegacyBridge, getState } from "./state";
import type { QueueState, RealtimePayload, WebUITask } from "./types";

const REALTIME_EVENTS_URL = "/api/events?stream=1";
const QUEUE_DISPATCH_RESYNC_DELAY_MS = 1500;

type QueueTask = WebUITask & {
  output_size?: string;
  queue_position?: number;
  attempts?: number;
  max_attempts?: number;
  local_pending?: boolean;
  last_error?: string;
  retry_requested_at?: string;
  retrying_failed_slots?: unknown[];
};

let queueFeatureInitialized = false;

export function initializeQueueFeature(): void {
  if (queueFeatureInitialized) return;
  queueFeatureInitialized = true;
  exposeQueueWindowApi();
  bindQueueControls();
  document.addEventListener(LOCALE_CHANGE_EVENT, renderQueue);
}

function exposeQueueWindowApi(): void {
  window.startRealtimeUpdates = startRealtimeUpdates;
  window.closeRealtimeUpdates = closeRealtimeUpdates;
  window.refreshQueue = refreshQueue;
  window.applyQueueState = applyQueueState;
  window.applyQueueTasks = applyQueueTasks;
  window.updateQueueElapsedDisplays = updateQueueElapsedDisplays;
}

function bindQueueControls(): void {
  const els = getEls();
  els.queueButton?.addEventListener("click", jumpToActiveTaskGroup);
}

export function startRealtimeUpdates({ migrateLegacyArchives = false } = {}): boolean {
  const state = getState();
  if (!window.EventSource) return false;
  closeRealtimeUpdates();
  state.realtimeSnapshotNeedsArchiveMigration = migrateLegacyArchives;
  const source = new EventSource(REALTIME_EVENTS_URL);
  state.realtimeSource = source;
  source.onmessage = (event) => {
    handleRealtimeMessage(event).catch((error: unknown) => {
      console.error(error);
      getLegacyBridge().methods.setStatus(errorMessage(error, translate("queue.realtimeUpdateFailed")), "error");
    });
  };
  source.onerror = () => {
    if (state.realtimeSource !== source) return;
    const shouldMigrateArchives = state.realtimeSnapshotNeedsArchiveMigration;
    closeRealtimeUpdates();
    state.realtimeSnapshotNeedsArchiveMigration = false;
    void refreshQueue();
    void getLegacyBridge().methods.refreshTasks({ migrateLegacyArchives: shouldMigrateArchives });
    getLegacyBridge().methods.setStatus(translate("queue.realtimeDisconnected"), "error");
  };
  return true;
}

export function closeRealtimeUpdates(): void {
  const state = getState();
  if (!state.realtimeSource) return;
  state.realtimeSource.close();
  state.realtimeSource = null;
}

export async function handleRealtimeMessage(event: MessageEvent): Promise<void> {
  if (!event.data) return;
  const payload = JSON.parse(String(event.data)) as RealtimePayload;
  await handleRealtimePayload(payload);
}

export async function handleRealtimePayload(payload: RealtimePayload | null | undefined): Promise<void> {
  const bridge = getLegacyBridge();
  const state = bridge.state;
  state.tasksRequestSeq += 1;
  if (payload?.type === "snapshot") {
    applyQueueState(payload.queue);
    await bridge.methods.applyTasksSnapshot(payload.tasks || [], {
      migrateLegacyArchives: state.realtimeSnapshotNeedsArchiveMigration,
    });
    applyQueueTasks(payload.queue);
    state.realtimeSnapshotNeedsArchiveMigration = false;
    return;
  }
  if (payload?.type === "queue") {
    applyQueueState(payload.queue);
    await applyRealtimeTaskPayloads(payload.tasks || []);
    applyQueueTasks(payload.queue);
    return;
  }
  if (payload?.type === "task") {
    await applyRealtimeTaskPayloads(payload.task ? [payload.task] : []);
  }
}

async function applyRealtimeTaskPayloads(tasks: WebUITask[]): Promise<void> {
  const bridge = getLegacyBridge();
  const state = bridge.state;
  for (const task of tasks) {
    const previousTask = state.tasks.find((item) => String(item.task_id) === String(task?.task_id));
    bridge.methods.notifyTaskUpdate?.(previousTask, task);
    await bridge.methods.applyTaskUpdate(task);
  }
}

export async function refreshQueue(): Promise<void> {
  const bridge = getLegacyBridge();
  const state = bridge.state;
  const requestSeq = ++state.queueRequestSeq;
  try {
    const response = await fetch("/api/queue");
    const data = await response.json();
    if (requestSeq !== state.queueRequestSeq) return;
    if (!response.ok) {
      throw new Error(data.detail || translate("queue.readFailed"));
    }
    state.queue = normalizeQueueState(data);
    renderQueue();
  } catch (error: unknown) {
    bridge.methods.setStatus(errorMessage(error, translate("queue.readFailed")), "error");
  }
}

export function defaultQueueState(): QueueState {
  return { waiting: [], running: [], summary: { waiting_count: 0, running_count: 0, channel_count: 0 } };
}

export function normalizeQueueState(queue: QueueState | null | undefined): QueueState {
  const fallback = defaultQueueState();
  return {
    waiting: Array.isArray(queue?.waiting) ? queue.waiting : fallback.waiting,
    running: Array.isArray(queue?.running) ? queue.running : fallback.running,
    summary: queue?.summary || fallback.summary,
  };
}

export function invalidateQueueRequests(): void {
  getState().queueRequestSeq += 1;
}

export function applyQueueState(queue: QueueState | null | undefined): void {
  const state = getState();
  invalidateQueueRequests();
  state.queue = normalizeQueueState(queue);
  renderQueue();
}

export function renderQueue(): void {
  const bridge = getLegacyBridge();
  const state = bridge.state;
  const summary = state.queue.summary || {};
  const waitingCount = Number(summary.waiting_count ?? state.queue.waiting.length ?? 0);
  const runningCount = Number(summary.running_count ?? state.queue.running.length ?? 0);
  const channelCount = Number(summary.channel_count ?? 0);
  const usableChannelCount = Number(summary.usable_channel_count ?? channelCount);
  const dispatchPending = isQueueDispatchPending();

  renderQueueStatusChip({
    waitingCount,
    runningCount,
    channelCount,
    usableChannelCount,
    dispatchPending,
  });
  bridge.methods.updateDocumentTitle();
  if (dispatchPending) {
    scheduleQueueDispatchSync();
  } else {
    clearQueueDispatchSync();
  }
  const nextRenderKey = queueListRenderKey();
  if (state.queueRenderKey === nextRenderKey) {
    updateQueueElapsedDisplays();
    return;
  }
  state.queueRenderKey = nextRenderKey;
  renderActiveTaskGroupForQueueChange();
}

function renderActiveTaskGroupForQueueChange(): void {
  const bridge = getLegacyBridge();
  bridge.methods.renderTasks?.();
}

export function renderQueueStatusChip({
  waitingCount,
  runningCount,
  channelCount,
  usableChannelCount,
  dispatchPending,
}: {
  waitingCount: number;
  runningCount: number;
  channelCount: number;
  usableChannelCount: number;
  dispatchPending: boolean;
}): void {
  const els = getEls();
  const total = waitingCount + runningCount;
  const channelText = usableChannelCount === channelCount
    ? formatTranslation("queue.channel", { count: channelCount })
    : formatTranslation("queue.availableChannels", { usable: usableChannelCount, total: channelCount });
  const text = dispatchPending
    ? formatTranslation("queue.dispatching", { waiting: waitingCount })
    : total
      ? formatTranslation("queue.runningWaiting", { running: runningCount, waiting: waitingCount })
      : translate("queue.empty");
  const label = total
    ? formatTranslation("queue.statusLabel", { text, channelText })
    : translate("queue.emptyAria");
  if (els.queueStatusText) els.queueStatusText.textContent = text;
  if (els.queueButton) {
    els.queueButton.setAttribute("aria-label", label);
    els.queueButton.title = total ? translate("queue.jumpTitle") : translate("queue.emptyTitle");
    els.queueButton.classList.toggle("has-queue", total > 0 || dispatchPending);
  }
}

export function jumpToActiveTaskGroup(): void {
  const bridge = getLegacyBridge();
  const state = bridge.state;
  const hasActiveTasks = Boolean((state.queue.running || []).length || (state.queue.waiting || []).length);
  if (!hasActiveTasks) return;
  bridge.methods.revealActiveTaskGroup?.();
}

export function isQueueDispatchPending(): boolean {
  const state = getState();
  const summary = state.queue.summary || {};
  const waitingCount = Number(summary.waiting_count ?? state.queue.waiting.length ?? 0);
  const runningCount = Number(summary.running_count ?? state.queue.running.length ?? 0);
  const channelCount = Number(summary.channel_count ?? 0);
  const usableChannelCount = Number(summary.usable_channel_count ?? channelCount);
  return waitingCount > 0 && runningCount === 0 && usableChannelCount > 0;
}

export function scheduleQueueDispatchSync(): void {
  const state = getState();
  if (state.queueDispatchSyncTimerId) return;
  state.queueDispatchSyncTimerId = window.setTimeout(() => {
    state.queueDispatchSyncTimerId = null;
    if (isQueueDispatchPending()) {
      void refreshQueue();
    }
  }, QUEUE_DISPATCH_RESYNC_DELAY_MS);
}

export function clearQueueDispatchSync(): void {
  const state = getState();
  if (!state.queueDispatchSyncTimerId) return;
  window.clearTimeout(state.queueDispatchSyncTimerId);
  state.queueDispatchSyncTimerId = null;
}

function queueListRenderKey(): string {
  const state = getState();
  return JSON.stringify({
    summary: state.queue.summary || {},
    running: (state.queue.running || []).map((task) => [
      task.task_id,
      task.status,
      task.viewed_at,
      task.prompt,
      (task as QueueTask).channel_id,
      (task as QueueTask).account_id,
      task.started_at,
      (task as QueueTask).attempts,
    ]),
    waiting: (state.queue.waiting || []).map((task) => [
      task.task_id,
      task.status,
      task.prompt,
      task.params?.size,
      (task as QueueTask).queue_position,
    ]),
  });
}

function queueItemTitleText(task: WebUITask, position: number | null = null): string {
  const bridge = getLegacyBridge();
  const queueTask = task as QueueTask;
  const prefix = position ? `#${position}` : bridge.methods.formatTaskStatus(task) || translate("taskStatus.task");
  const mode = taskModeLabel(task);
  const count = formatTranslation("taskCard.count", { count: bridge.methods.taskTotalCount(task) });
  const size = queueTask.output_size || task.params?.size || "";
  return [prefix, mode, count, size].filter(Boolean).join(" · ");
}

function taskModeLabel(task: WebUITask): string {
  if (task.mode === "edit") return translate("taskMode.edit");
  if (task.mode === "generate") return translate("taskMode.generate");
  return "";
}

export async function promoteQueueTask(taskId: string | undefined): Promise<void> {
  const bridge = getLegacyBridge();
  if (!taskId) return;
  invalidateQueueRequests();
  try {
    const response = await fetch(`/api/queue/${encodeURIComponent(taskId)}/promote`, { method: "POST" });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.detail || translate("queue.promoteFailed"));
    applyQueueState(data);
    await bridge.methods.refreshTasks();
  } catch (error: unknown) {
    bridge.methods.setStatus(errorMessage(error, translate("queue.promoteFailed")), "error");
  }
}

export function moveQueueTask(taskId: string | undefined, direction: string | undefined): void {
  if (!taskId) return;
  const ids = (getState().queue.waiting || []).map((task) => task.task_id);
  const currentIndex = ids.indexOf(taskId);
  if (currentIndex < 0) return;
  const offset = direction === "up" ? -1 : direction === "down" ? 1 : 0;
  const nextIndex = currentIndex + offset;
  if (offset === 0 || nextIndex < 0 || nextIndex >= ids.length) return;
  const nextIds = ids.slice();
  const [moved] = nextIds.splice(currentIndex, 1);
  if (!moved) return;
  nextIds.splice(nextIndex, 0, moved);
  void reorderQueue(nextIds);
}

export function deleteQueuedTask(button: Element, taskId: string | undefined): void {
  const bridge = getLegacyBridge();
  if (!taskId) return;
  const task = bridge.state.queue.waiting.find((item) => item.task_id === taskId);
  const title = task ? queueItemTitleText(task, (task as QueueTask).queue_position || null) : taskId;
  bridge.methods.openConfirmPopover(button, {
    title: translate("queue.deleteWaitingTitleConfirm"),
    message: translate("queue.deleteWaitingMessage"),
    detail: title,
    confirmText: translate("action.delete"),
    onConfirm: async () => {
      await performDeleteQueuedTask(taskId);
    },
  });
}

export async function performDeleteQueuedTask(taskId: string): Promise<void> {
  const bridge = getLegacyBridge();
  const state = bridge.state;
  invalidateQueueRequests();
  try {
    const response = await fetch(`/api/queue/${encodeURIComponent(taskId)}`, { method: "DELETE" });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.detail || translate("queue.deleteQueuedFailed"));
    state.tasks = state.tasks.filter((item) => item.task_id !== taskId);
    if (state.selectedTaskId === taskId) {
      state.selectedTaskId = state.tasks[0]?.task_id || null;
    }
    applyQueueState({
      ...state.queue,
      waiting: state.queue.waiting.filter((item) => item.task_id !== taskId),
      summary: {
        ...(state.queue.summary || {}),
        waiting_count: Math.max(0, Number(state.queue.summary?.waiting_count || 0) - 1),
      },
    });
    await refreshQueue();
    await bridge.methods.refreshTasks();
    bridge.methods.renderPreview();
    bridge.methods.setStatus(translate("queue.queuedDeleted"), "ok");
  } catch (error: unknown) {
    bridge.methods.setStatus(errorMessage(error, translate("queue.deleteQueuedFailed")), "error");
  }
}

export function cancelRunningTask(button: Element, taskId: string | undefined): void {
  const bridge = getLegacyBridge();
  if (!taskId) return;
  const task = bridge.state.queue.running.find((item) => item.task_id === taskId);
  const title = task ? queueItemTitleText(task) : taskId;
  bridge.methods.openConfirmPopover(button, {
    title: translate("queue.cancelRunningTitleConfirm"),
    message: translate("queue.cancelRunningMessage"),
    detail: title,
    confirmText: translate("queue.cancelRunningConfirm"),
    onConfirm: async () => {
      await performCancelRunningTask(taskId);
    },
  });
}

async function performCancelRunningTask(taskId: string): Promise<void> {
  const bridge = getLegacyBridge();
  const state = bridge.state;
  invalidateQueueRequests();
  try {
    const response = await fetch(`/api/queue/${encodeURIComponent(taskId)}`, { method: "DELETE" });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.detail || translate("queue.cancelRunningFailed"));
    applyQueueState({
      ...state.queue,
      running: state.queue.running.filter((item) => item.task_id !== taskId),
      summary: {
        ...(state.queue.summary || {}),
        running_count: Math.max(0, Number(state.queue.summary?.running_count || 0) - 1),
      },
    });
    await refreshQueue();
    await bridge.methods.refreshTasks();
    bridge.methods.renderPreview();
    bridge.methods.setStatus(translate("queue.runningCancelled"), "ok");
  } catch (error: unknown) {
    bridge.methods.setStatus(errorMessage(error, translate("queue.cancelRunningFailed")), "error");
  }
}

export async function reorderQueue(taskIds: string[]): Promise<void> {
  const bridge = getLegacyBridge();
  invalidateQueueRequests();
  try {
    const response = await fetch(`/api/queue/reorder`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ task_ids: taskIds }),
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.detail || translate("queue.reorderFailed"));
    applyQueueState(data);
    await bridge.methods.refreshTasks();
  } catch (error: unknown) {
    bridge.methods.setStatus(errorMessage(error, translate("queue.reorderFailed")), "error");
    await refreshQueue();
  }
}

export function handleQueueDragStart(event: DragEvent): void {
  const target = eventTargetElement(event);
  const item = event.currentTarget instanceof HTMLElement && event.currentTarget.dataset.queueTaskId
    ? event.currentTarget
    : target?.closest("[data-queue-task-id]");
  if (!(item instanceof HTMLElement)) return;
  const draggedId = item.dataset.queueTaskId || null;
  getState().queueDragTaskId = draggedId;
  if (event.dataTransfer && draggedId) {
    event.dataTransfer.effectAllowed = "move";
    event.dataTransfer.setData("text/plain", draggedId);
  }
}

export function handleQueueDragOver(event: DragEvent): void {
  event.preventDefault();
  if (event.dataTransfer) {
    event.dataTransfer.dropEffect = "move";
  }
}

export function handleQueueDrop(event: DragEvent): void {
  event.preventDefault();
  event.stopPropagation();
  const state = getState();
  const draggedId = state.queueDragTaskId;
  if (!draggedId) return;
  const ids = (state.queue.waiting || []).map((task) => task.task_id);
  const nextIds = ids.filter((id) => id !== draggedId);
  const targetItem = eventTargetElement(event)?.closest("[data-queue-task-id]");
  const targetId = targetItem instanceof HTMLElement ? targetItem.dataset.queueTaskId : undefined;
  if (targetId === draggedId) return;
  if (!targetId) {
    nextIds.push(draggedId);
    void reorderQueue(nextIds);
    return;
  }
  const targetIndex = nextIds.indexOf(targetId);
  if (targetIndex < 0 || !(targetItem instanceof HTMLElement)) return;
  const targetRect = targetItem.getBoundingClientRect();
  const insertAfter = event.clientY > targetRect.top + targetRect.height / 2;
  nextIds.splice(insertAfter ? targetIndex + 1 : targetIndex, 0, draggedId);
  void reorderQueue(nextIds);
}

export function handleQueueDragEnd(_event: DragEvent): void {
  getState().queueDragTaskId = null;
}

export function applyQueueTasks(queue: QueueState | null | undefined): void {
  const bridge = getLegacyBridge();
  const tasks = [
    ...(Array.isArray(queue?.waiting) ? queue.waiting : []),
    ...(Array.isArray(queue?.running) ? queue.running : []),
  ];
  const queueTaskIds = new Set(tasks.map((task) => String(task.task_id)));
  const needsTaskReconcile = activeTasksNeedQueueReconcile(queueTaskIds);
  if (!tasks.length) {
    if (needsTaskReconcile) {
      void bridge.methods.refreshTasks();
    }
    return;
  }
  let changed = false;
  tasks.forEach((task) => {
    const previousTask = bridge.state.tasks.find((item) => String(item.task_id) === String(task.task_id));
    bridge.methods.notifyTaskUpdate?.(previousTask, task);
    changed = bridge.methods.updateTaskInState(task) || changed;
    if (String(task.task_id) === String(bridge.state.selectedTaskId) && bridge.methods.taskHasViewableUpdate(task)) {
      void bridge.methods.markTaskViewed(task.task_id);
    }
  });
  if (!changed) {
    if (needsTaskReconcile) {
      void bridge.methods.refreshTasks();
    }
    return;
  }
  bridge.methods.cleanupSessionSelections();
  bridge.methods.renderTasks();
  bridge.methods.renderArchiveButton();
  bridge.methods.renderArchiveModal();
  bridge.methods.renderPreview();
  if (needsTaskReconcile) {
    void bridge.methods.refreshTasks();
  }
}

function activeTasksNeedQueueReconcile(queueTaskIds: Set<string>): boolean {
  const bridge = getLegacyBridge();
  return bridge.state.tasks.some((task) => {
    const taskId = String(task?.task_id || "");
    if (!taskId || queueTaskIds.has(taskId) || task?.local_pending) return false;
    const status = String(task?.status || "");
    return status === "submitting" || status === "queued" || status === "running";
  });
}

export function updateQueueElapsedDisplays(): void {
  getLegacyBridge().methods.updateTaskElapsedDisplays?.();
}

function eventTargetElement(event: Event): Element | null {
  return event.target instanceof Element ? event.target : null;
}

function escapeHtml(value: unknown): string {
  return getLegacyBridge().methods.escapeHtml(value);
}

function errorMessage(error: unknown, fallback: string): string {
  return error instanceof Error && error.message ? error.message : fallback;
}

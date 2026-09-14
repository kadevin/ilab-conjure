import { getLegacyBridge } from "./state";
import { formatTranslation, LOCALE_CHANGE_EVENT } from "./i18n";
import { isBatchScopeSelected, toggleBatchScopeIds, waitingBatchTaskIds } from "./task-batch-selection-model";

const bridge = getLegacyBridge();
const state = bridge.state;
const els = bridge.els;
let groupSelectionSnapshot: { key: string; taskIds: string[] } | null = null;
let groupSelectionRequestSeq = 0;
let groupSelectionPending = false;

function legacyMethod(name: string, ...args: any[]): any {
  const method = getLegacyBridge().methods[name];
  if (typeof method !== "function") {
    throw new Error("Legacy bridge method " + name + " is not available");
  }
  return method(...args);
}

const TASK_CARD_SELECTOR = ".task-card[data-task-id]";

function errorMessage(error: unknown, fallback: string): string {
  return error instanceof Error ? error.message || fallback : fallback;
}

function setStatus(...args: any[]) { return legacyMethod("setStatus", ...args); }
function isTaskArchived(...args: any[]) { return legacyMethod("isTaskArchived", ...args); }
function renderTasks(...args: any[]) { return legacyMethod("renderTasks", ...args); }
function setTaskArchiveState(...args: any[]) { return legacyMethod("setTaskArchiveState", ...args); }
function replaceTask(...args: any[]) { return legacyMethod("replaceTask", ...args); }
function firstVisibleTaskId(...args: any[]) { return legacyMethod("firstVisibleTaskId", ...args); }
function renderArchiveButton(...args: any[]) { return legacyMethod("renderArchiveButton", ...args); }
function renderArchiveModal(...args: any[]) { return legacyMethod("renderArchiveModal", ...args); }
function renderPreview(...args: any[]) { return legacyMethod("renderPreview", ...args); }
function openConfirmPopover(...args: any[]) { return legacyMethod("openConfirmPopover", ...args); }
function runTaskCardRemovalTransition(...args: any[]) { return legacyMethod("runTaskCardRemovalTransition", ...args); }
function refreshTasksAfterDeletion(...args: any[]) { return legacyMethod("refreshTasksAfterDeletion", ...args); }
function taskFilterValues(...args: any[]) { return legacyMethod("taskFilterValues", ...args); }

function activeTaskIds() {
  return [...(state.queue.running || []), ...(state.queue.waiting || [])]
    .map((task: any) => String(task?.task_id || ""))
    .filter(Boolean);
}

function toggleBatchMode(force?: any) {
  state.batchMode = typeof force === "boolean" ? force : !state.batchMode;
  if (!state.batchMode) {
    groupSelectionRequestSeq += 1;
    groupSelectionPending = false;
    groupSelectionSnapshot = null;
    state.batchSelectedTaskIds = [];
    state.batchSelectionAnchorTaskId = null;
    state.batchSelectionIncludesUnloaded = false;
    finishBatchMarqueeSelection();
  }
  renderTasks({ preserveScroll: true });
  renderBatchToolbar();
}

function toggleBatchTaskSelection(taskId: any) {
  const id = String(taskId || "");
  if (!id || isTaskArchived(id)) return;
  if (state.batchSelectedTaskIds.includes(id)) {
    removeBatchSelectedTaskId(id);
  } else {
    state.batchSelectedTaskIds.push(id);
  }
  state.batchSelectionAnchorTaskId = id;
  syncBatchTaskSelectionVisuals();
}

function removeBatchSelectedTaskId(taskId: any) {
  const id = String(taskId || "");
  state.batchSelectedTaskIds = state.batchSelectedTaskIds.filter((item: any) => item !== id);
}

function visibleBatchTaskIds() {
  const root = els.taskHistoryShell || els.sidebarContent || els.taskList;
  if (!root) return [];
  return Array.from(root.querySelectorAll(TASK_CARD_SELECTOR))
    .map((card: any) => String(card.dataset.taskId || ""))
    .filter((taskId) => taskId && !isTaskArchived(taskId));
}

function applyBatchTaskSelection(taskIds: any[], anchorTaskId: any = null) {
  const wasBatchMode = Boolean(state.batchMode);
  state.batchSelectedTaskIds = Array.from(new Set(taskIds.map(String).filter(Boolean)));
  if (anchorTaskId) state.batchSelectionAnchorTaskId = String(anchorTaskId);
  state.batchMode = true;
  if (wasBatchMode) {
    syncBatchTaskSelectionVisuals();
  } else {
    renderTasks({ preserveScroll: true });
    renderBatchToolbar();
  }
}

function selectBatchTaskRange(anchorTaskId: any, taskId: any) {
  const id = String(taskId || "");
  if (!id || isTaskArchived(id)) return;
  const visibleIds = visibleBatchTaskIds();
  const fallbackAnchor = state.batchSelectedTaskIds.at(-1) || state.selectedTaskId || id;
  const anchor = String(anchorTaskId || fallbackAnchor || id);
  const anchorIndex = visibleIds.indexOf(anchor);
  const targetIndex = visibleIds.indexOf(id);
  if (anchorIndex < 0 || targetIndex < 0) {
    applyBatchTaskSelection([...state.batchSelectedTaskIds, id], id);
    return;
  }
  const [start, end] = anchorIndex <= targetIndex ? [anchorIndex, targetIndex] : [targetIndex, anchorIndex];
  applyBatchTaskSelection([...state.batchSelectedTaskIds, ...visibleIds.slice(start, end + 1)], anchor);
}

function handleBatchTaskShortcutSelection(taskId: any, event: MouseEvent | KeyboardEvent) {
  const id = String(taskId || "");
  if (!id || isTaskArchived(id)) return false;
  if (!event.shiftKey && !event.metaKey && !event.ctrlKey) return false;
  event.preventDefault();
  event.stopPropagation();
  if (event.shiftKey) {
    selectBatchTaskRange(state.batchSelectionAnchorTaskId || state.selectedTaskId || id, id);
    return true;
  }
  const selected = state.batchSelectedTaskIds.includes(id);
  const nextIds = selected
    ? state.batchSelectedTaskIds.filter((item: any) => String(item) !== id)
    : [...state.batchSelectedTaskIds, id];
  applyBatchTaskSelection(nextIds, id);
  return true;
}

function syncBatchTaskSelectionVisuals() {
  const selectedIds = new Set(state.batchSelectedTaskIds.map(String));
  const root = els.taskHistoryShell || els.sidebarContent || els.taskList;
  root?.querySelectorAll(TASK_CARD_SELECTOR).forEach((card: any) => {
    const selected = selectedIds.has(String(card.dataset.taskId || ""));
    card.classList.toggle("batch-selected", selected);
    const selectButton = card.querySelector("[data-batch-select-task-id]");
    if (selectButton) selectButton.setAttribute("aria-checked", selected ? "true" : "false");
  });
  renderBatchToolbar();
}

function renderBatchToolbar() {
  if (!els.batchToolbar) return;
  const activeIds = activeTaskIds();
  const showCancelShortcut = activeIds.length >= 2;
  if (!showCancelShortcut && document.activeElement === els.batchCancelTasksButton) {
    els.batchManageButton?.focus({ preventScroll: true });
  }
  if (els.batchCancelTasksButton) {
    els.batchCancelTasksButton.hidden = !showCancelShortcut;
    els.batchCancelTasksButton.classList.toggle("hidden", !showCancelShortcut);
  }
  els.batchToolbar.classList.toggle("hidden", !state.batchMode);
  els.taskList?.classList.toggle("batch-marquee-enabled", state.batchMode);
  els.batchManageButton?.classList.toggle("active", state.batchMode);
  els.batchManageButton?.setAttribute("aria-pressed", state.batchMode ? "true" : "false");
  const count = state.batchSelectedTaskIds.length;
  const activeIdSet = new Set(activeIds);
  const selectedActiveCount = state.batchSelectedTaskIds.filter((taskId: any) => activeIdSet.has(String(taskId))).length;
  if (els.batchSelectedCount) {
    els.batchSelectedCount.textContent = formatTranslation("batch.selectedCount", { count });
  }
  if (els.batchSelectGroupButton) {
    const scope = currentBatchGroupScope();
    const selected = isBatchScopeSelected(state.batchSelectedTaskIds, knownGroupScopeIds(scope));
    const key = selected ? "batch.deselectCurrentGroup" : "batch.selectCurrentGroup";
    const label = els.batchSelectGroupButton.querySelector("[data-batch-selection-label]") || els.batchSelectGroupButton;
    label.textContent = formatTranslation(key);
    label.setAttribute("data-i18n", key);
    els.batchSelectGroupButton.setAttribute("aria-pressed", String(selected));
    els.batchSelectGroupButton.setAttribute("aria-busy", String(groupSelectionPending));
    els.batchSelectGroupButton.disabled = groupSelectionPending || !scope.valid;
  }
  if (els.batchSelectWaitingButton) {
    const taskIds = waitingBatchTaskIds(state.queue);
    const selected = isBatchScopeSelected(state.batchSelectedTaskIds, taskIds);
    const key = selected ? "batch.deselectWaiting" : "batch.selectWaiting";
    const label = els.batchSelectWaitingButton.querySelector("[data-batch-selection-label]") || els.batchSelectWaitingButton;
    label.textContent = formatTranslation(key);
    label.setAttribute("data-i18n", key);
    els.batchSelectWaitingButton.setAttribute("aria-pressed", String(selected));
    els.batchSelectWaitingButton.disabled = taskIds.length === 0;
  }
  [els.batchArchiveButton, els.batchDeleteButton].forEach((button: any) => {
    if (button) button.disabled = count === 0;
  });
  if (els.batchCancelSelectedButton) {
    els.batchCancelSelectedButton.disabled = selectedActiveCount === 0;
  }
}

function selectWaitingTasksForBatch() {
  const taskIds = waitingBatchTaskIds(state.queue);
  if (!taskIds.length) return;
  toggleBatchScopeSelection(taskIds);
}

function toggleBatchScopeSelection(taskIds: string[]) {
  const nextIds = toggleBatchScopeIds(state.batchSelectedTaskIds, taskIds);
  const loadedIds = new Set((state.tasks || []).map((task: any) => String(task.task_id)));
  state.batchSelectionIncludesUnloaded = nextIds.some((id) => !loadedIds.has(id));
  state.batchSelectionAnchorTaskId = nextIds[nextIds.length - 1] || null;
  applyBatchTaskSelection(nextIds, state.batchSelectionAnchorTaskId);
}

function currentBatchGroupScope() {
  const groupKey = String(state.expandedTaskGroupKey || "");
  const filters = taskFilterValues();
  const params = new URLSearchParams();
  [
    ["status", filters.status],
    ["prompt_mode", filters.promptFidelity],
    ["ratio", filters.ratio],
    ["orientation", filters.orientation],
    ["resolution", filters.resolution],
  ].forEach(([key, value]) => {
    if (value) params.set(String(key), String(value));
  });
  const query = String(state.taskSearchQuery || "").trim();
  const count = state.taskSidebarGroupCounts?.[groupKey];
  return {
    groupKey, params, count,
    valid: !query && ["today", "yesterday", "last7"].includes(groupKey),
    key: JSON.stringify([groupKey, params.toString(), query, count]),
  };
}

function knownGroupScopeIds(scope: ReturnType<typeof currentBatchGroupScope>): string[] {
  if (!scope.valid) return [];
  if (groupSelectionSnapshot?.key === scope.key) return groupSelectionSnapshot.taskIds;
  if (typeof scope.count !== "number"
      || Number(state.taskSidebarGroupLoadedCounts?.[scope.groupKey] || 0) < scope.count) return [];
  const methods = getLegacyBridge().methods;
  const groups = methods.taskHistoryGroups?.(methods.filteredVisibleTasks?.() || [], "") || [];
  const group = groups.find((item: any) => item.key === scope.groupKey);
  return (group?.tasks || []).map((task: any) => String(task.task_id));
}

async function selectAllMatchingTasksInExpandedGroup() {
  const scope = currentBatchGroupScope();
  if (groupSelectionPending || !scope.valid || !state.batchMode) return;
  const knownIds = knownGroupScopeIds(scope);
  if (isBatchScopeSelected(state.batchSelectedTaskIds, knownIds)) {
    toggleBatchScopeSelection(knownIds);
    return;
  }
  const requestSeq = ++groupSelectionRequestSeq;
  const selectedBefore = JSON.stringify(state.batchSelectedTaskIds);
  const current = () => requestSeq === groupSelectionRequestSeq && state.batchMode
    && currentBatchGroupScope().key === scope.key
    && JSON.stringify(state.batchSelectedTaskIds) === selectedBefore;
  groupSelectionPending = true;
  renderBatchToolbar();
  try {
    const response = await fetch(
      `/api/tasks/sidebar/groups/${encodeURIComponent(scope.groupKey)}/selection?${scope.params.toString()}`,
    );
    const data = await response.json().catch(() => ({}));
    if (!current()) return;
    if (!response.ok) throw new Error(data.detail || formatTranslation("batch.selectFailed"));
    const taskIds = Array.isArray(data.task_ids) ? data.task_ids.map(String).filter(Boolean) : [];
    groupSelectionSnapshot = { key: scope.key, taskIds };
    toggleBatchScopeSelection(taskIds);
  } catch (error) {
    if (current()) setStatus(errorMessage(error, formatTranslation("batch.selectFailed")), "error");
  } finally {
    if (requestSeq === groupSelectionRequestSeq) {
      groupSelectionPending = false;
      renderBatchToolbar();
    }
  }
}

function selectActiveTasksForBatchCancel() {
  if (activeTaskIds().length < 2) return;
  state.batchSelectedTaskIds = activeTaskIds();
  state.batchSelectionAnchorTaskId = state.batchSelectedTaskIds[0] || null;
  state.batchSelectionIncludesUnloaded = false;
  state.batchMode = true;
  renderTasks({ preserveScroll: true });
  renderBatchToolbar();
  els.batchCancelSelectedButton?.focus({ preventScroll: true });
}

function openBatchCancelConfirm() {
  const runningIds = new Set((state.queue.running || []).map((task: any) => String(task?.task_id || "")));
  const waitingIds = new Set((state.queue.waiting || []).map((task: any) => String(task?.task_id || "")));
  const selectedActiveIds = state.batchSelectedTaskIds.filter(
    (taskId: any) => runningIds.has(String(taskId)) || waitingIds.has(String(taskId)),
  );
  const runningCount = selectedActiveIds.filter((taskId: any) => runningIds.has(String(taskId))).length;
  const waitingCount = selectedActiveIds.filter((taskId: any) => waitingIds.has(String(taskId))).length;
  if (!selectedActiveIds.length) {
    setStatus(formatTranslation("batch.noActiveSelected"), "error");
    return;
  }
  openConfirmPopover(els.batchCancelSelectedButton, {
    title: formatTranslation("batch.cancelTitle", { count: selectedActiveIds.length }),
    message: formatTranslation("batch.cancelMessage"),
    detail: formatTranslation("batch.cancelDetail", { running: runningCount, waiting: waitingCount }),
    confirmText: formatTranslation("batch.cancelConfirm"),
    onConfirm: async () => {
      await cancelSelectedActiveTasks(selectedActiveIds);
    },
  });
}

async function cancelSelectedActiveTasks(taskIds: any[]) {
  try {
    const response = await fetch("/api/queue/cancel-batch", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ task_ids: taskIds }),
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.detail || formatTranslation("batch.cancelFailed"));

    state.batchSelectedTaskIds = [];
    state.batchSelectionAnchorTaskId = null;
    state.batchSelectionIncludesUnloaded = false;
    state.batchMode = false;
    await window.refreshQueue?.();
    await legacyMethod("refreshTasks");
    renderPreview();
    const summary = data.summary || {};
    const statusType = Number(summary.failed || 0) > 0 ? "error" : "ok";
    setStatus(formatTranslation("batch.cancelResult", {
      cancelled: Number(summary.cancelled || 0),
      requested: Number(summary.cancellation_requested || 0),
      skipped: Number(summary.skipped || 0),
      failed: Number(summary.failed || 0),
    }), statusType);
  } catch (error) {
    renderTasks({ preserveScroll: true });
    setStatus(errorMessage(error, formatTranslation("batch.cancelFailed")), "error");
  }
}

async function archiveSelectedTasks() {
  const ids = state.batchSelectedTaskIds.slice();
  if (!ids.length) return;
  const updatedTasks = [];
  try {
    for (const taskId of ids as any[]) {
      const updatedTask = await setTaskArchiveState(taskId, true);
      updatedTasks.push(updatedTask);
    }
    updatedTasks.forEach(replaceTask);
    if (ids.includes(String(state.selectedTaskId))) {
      state.selectedTaskId = firstVisibleTaskId();
    }
    state.batchSelectedTaskIds = [];
    state.batchSelectionAnchorTaskId = null;
    state.batchSelectionIncludesUnloaded = false;
    state.batchMode = false;
    renderTasks();
    renderArchiveButton();
    renderArchiveModal();
    renderPreview();
    setStatus(formatTranslation("batch.archivedCount", { count: ids.length }), "ok");
  } catch (error) {
    updatedTasks.forEach(replaceTask);
    renderTasks();
    renderArchiveButton();
    renderArchiveModal();
    renderPreview();
    setStatus(errorMessage(error, formatTranslation("batch.archiveFailed")), "error");
  }
}

function openBatchDeleteConfirm() {
  const activeIds = new Set(activeTaskIds());
  const localPendingIds = new Set(
    state.tasks.filter((task: any) => task?.local_pending).map((task: any) => String(task.task_id || "")),
  );
  const deletableTaskIds = state.batchSelectedTaskIds
    .map(String)
    .filter((taskId: string) => !activeIds.has(taskId) && !localPendingIds.has(taskId));
  const skippedCount = state.batchSelectedTaskIds.length - deletableTaskIds.length;
  if (!deletableTaskIds.length) {
    setStatus(formatTranslation("batch.runningCannotDeleteSelected"), "error");
    return;
  }
  openConfirmPopover(els.batchDeleteButton, {
    title: formatTranslation("batch.deleteTitle", { count: deletableTaskIds.length }),
    message: formatTranslation("batch.deleteMessage"),
    detail: skippedCount ? formatTranslation("batch.deleteSkippedDetail", { count: skippedCount }) : "",
    confirmText: formatTranslation("action.delete"),
    onConfirm: async () => {
      await deleteSelectedTasks(deletableTaskIds, skippedCount);
    },
  });
}

async function deleteSelectedTasks(deletableTaskIds: string[], skippedCount = 0) {
  const deletedTaskIds: string[] = [];
  try {
    const response = await fetch("/api/tasks/delete-batch", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ task_ids: deletableTaskIds }),
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.detail || formatTranslation("batch.deleteFailed"));
    deletedTaskIds.push(...(Array.isArray(data.deleted) ? data.deleted.map(String) : []));
    skippedCount += Array.isArray(data.skipped) ? data.skipped.length : 0;
    state.tasks = state.tasks.filter((task: any) => !deletedTaskIds.includes(String(task?.task_id || "")));
    if (deletedTaskIds.includes(String(state.selectedTaskId || ""))) {
      state.selectedTaskId = firstVisibleTaskId();
    }
    state.batchSelectedTaskIds = [];
    state.batchSelectionAnchorTaskId = null;
    state.batchSelectionIncludesUnloaded = false;
    state.batchMode = false;
    await runTaskCardRemovalTransition(deletedTaskIds, renderTasks);
    await refreshTasksAfterDeletion();
    renderArchiveButton();
    renderArchiveModal();
    renderPreview();
    const skippedText = skippedCount ? formatTranslation("batch.deleteSkippedSuffix", { count: skippedCount }) : "";
    setStatus(formatTranslation("batch.deletedCount", { count: deletedTaskIds.length, skipped: skippedText }), "ok");
  } catch (error) {
    if (deletedTaskIds.length) {
      await runTaskCardRemovalTransition(deletedTaskIds, renderTasks);
    } else {
      renderTasks();
    }
    renderArchiveButton();
    renderArchiveModal();
    renderPreview();
    setStatus(errorMessage(error, formatTranslation("batch.deleteFailed")), "error");
  }
}

function handleTaskListPointerDown(event: any) {
  if (!state.batchMode || !els.taskList || event.button !== 0) return;
  if (event.target.closest("button, input, select, textarea, a")) return;
  if (!event.target.closest(".task-card[data-task-id]") && event.target !== els.taskList) return;

  state.batchSelectionDrag = {
    pointerId: event.pointerId,
    startX: event.clientX,
    startY: event.clientY,
    currentX: event.clientX,
    currentY: event.clientY,
    active: false,
    originSelectedTaskIds: state.batchSelectedTaskIds.slice(),
    marquee: null,
  };
  window.addEventListener("pointermove", handleTaskListPointerMove);
  window.addEventListener("pointerup", handleTaskListPointerUp);
  window.addEventListener("pointercancel", handleTaskListPointerUp);
}

function handleTaskListPointerMove(event: any) {
  const drag = state.batchSelectionDrag;
  if (!drag || event.pointerId !== drag.pointerId) return;
  drag.currentX = event.clientX;
  drag.currentY = event.clientY;

  if (!drag.active) {
    const distance = Math.hypot(drag.currentX - drag.startX, drag.currentY - drag.startY);
    if (distance < 6) return;
    drag.active = true;
    state.suppressTaskClickAfterDrag = true;
    els.taskList?.classList.add("batch-marquee-active");
    drag.marquee = document.createElement("div");
    drag.marquee.className = "batch-selection-marquee";
    document.body.appendChild(drag.marquee);
  }

  event.preventDefault();
  updateBatchMarqueeSelection();
}

function handleTaskListPointerUp(event: any) {
  const drag = state.batchSelectionDrag;
  if (!drag || event.pointerId !== drag.pointerId) return;
  if (drag.active) {
    event.preventDefault();
    updateBatchMarqueeSelection();
  }
  finishBatchMarqueeSelection();
}

function updateBatchMarqueeSelection() {
  const drag = state.batchSelectionDrag;
  if (!drag?.active) return;

  const selectionRect = normalizeSelectionRect(drag.startX, drag.startY, drag.currentX, drag.currentY);
  if (drag.marquee) {
    drag.marquee.style.left = `${selectionRect.left}px`;
    drag.marquee.style.top = `${selectionRect.top}px`;
    drag.marquee.style.width = `${selectionRect.width}px`;
    drag.marquee.style.height = `${selectionRect.height}px`;
  }

  const nextSelectedIds = new Set(drag.originSelectedTaskIds.map(String));
  els.taskList.querySelectorAll(TASK_CARD_SELECTOR).forEach((card: any) => {
    const cardRect = card.getBoundingClientRect();
    if (rectsIntersect(selectionRect, cardRect)) {
      nextSelectedIds.add(String(card.dataset.taskId));
    }
  });
  applyBatchSelectionPreview([...nextSelectedIds]);
}

function applyBatchSelectionPreview(taskIds: any) {
  const nextIds = taskIds.map(String).filter((id: any) => id && !isTaskArchived(id));
  const nextSet = new Set(nextIds);
  const previous = state.batchSelectedTaskIds.map(String).sort().join("|");
  const next = nextIds.slice().sort().join("|");
  if (previous === next) return;

  state.batchSelectedTaskIds = nextIds;
  state.batchSelectionAnchorTaskId = nextIds.length ? nextIds[nextIds.length - 1] : state.batchSelectionAnchorTaskId || null;
  els.taskList.querySelectorAll(TASK_CARD_SELECTOR).forEach((card: any) => {
    const selected = nextSet.has(String(card.dataset.taskId));
    card.classList.toggle("batch-selected", selected);
    const selectButton = card.querySelector("[data-batch-select-task-id]");
    if (selectButton) selectButton.setAttribute("aria-checked", selected ? "true" : "false");
  });
  renderBatchToolbar();
}

function normalizeSelectionRect(startX: any, startY: any, currentX: any, currentY: any) {
  const left = Math.min(startX, currentX);
  const top = Math.min(startY, currentY);
  const right = Math.max(startX, currentX);
  const bottom = Math.max(startY, currentY);
  return {
    left,
    top,
    right,
    bottom,
    width: right - left,
    height: bottom - top,
  };
}

function rectsIntersect(selectionRect: any, cardRect: any) {
  return selectionRect.left <= cardRect.right
    && selectionRect.right >= cardRect.left
    && selectionRect.top <= cardRect.bottom
    && selectionRect.bottom >= cardRect.top;
}

function finishBatchMarqueeSelection() {
  const drag = state.batchSelectionDrag;
  if (drag?.marquee) {
    drag.marquee.remove();
  }
  state.batchSelectionDrag = null;
  els.taskList?.classList.remove("batch-marquee-active");
  window.removeEventListener("pointermove", handleTaskListPointerMove);
  window.removeEventListener("pointerup", handleTaskListPointerUp);
  window.removeEventListener("pointercancel", handleTaskListPointerUp);
}

export function initTaskBatchControlsFeature() {
  document.addEventListener(LOCALE_CHANGE_EVENT, renderBatchToolbar);
  Object.assign(getLegacyBridge().methods, {
    toggleBatchMode,
    toggleBatchTaskSelection,
    removeBatchSelectedTaskId,
    visibleBatchTaskIds,
    applyBatchTaskSelection,
    selectBatchTaskRange,
    handleBatchTaskShortcutSelection,
    renderBatchToolbar,
    activeTaskIds,
    selectActiveTasksForBatchCancel,
    selectWaitingTasksForBatch,
    selectAllMatchingTasksInExpandedGroup,
    openBatchCancelConfirm,
    cancelSelectedActiveTasks,
    archiveSelectedTasks,
    openBatchDeleteConfirm,
    deleteSelectedTasks,
    handleTaskListPointerDown,
    handleTaskListPointerMove,
    handleTaskListPointerUp,
    updateBatchMarqueeSelection,
    applyBatchSelectionPreview,
    normalizeSelectionRect,
    rectsIntersect,
    finishBatchMarqueeSelection,
  });
}

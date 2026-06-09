import { getLegacyBridge } from "./state";
import { formatTranslation, LOCALE_CHANGE_EVENT } from "./i18n";

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
function deleteTaskById(...args: any[]) { return legacyMethod("deleteTaskById", ...args); }

function toggleBatchMode(force?: any) {
  state.batchMode = typeof force === "boolean" ? force : !state.batchMode;
  if (!state.batchMode) {
    state.batchSelectedTaskIds = [];
    finishBatchMarqueeSelection();
  }
  renderTasks();
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
  renderTasks();
}

function removeBatchSelectedTaskId(taskId: any) {
  const id = String(taskId || "");
  state.batchSelectedTaskIds = state.batchSelectedTaskIds.filter((item: any) => item !== id);
}

function renderBatchToolbar() {
  if (!els.batchToolbar) return;
  els.batchToolbar.classList.toggle("hidden", !state.batchMode);
  els.taskList?.classList.toggle("batch-marquee-enabled", state.batchMode);
  els.batchManageButton?.classList.toggle("active", state.batchMode);
  const count = state.batchSelectedTaskIds.length;
  if (els.batchSelectedCount) {
    els.batchSelectedCount.textContent = formatTranslation("batch.selectedCount", { count });
  }
  [els.batchArchiveButton, els.batchDeleteButton].forEach((button: any) => {
    if (button) button.disabled = count === 0;
  });
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
  const selectedTasks = state.batchSelectedTaskIds
    .map((taskId: any) => state.tasks.find((task: any) => String(task.task_id) === String(taskId)))
    .filter(Boolean);
  const deletableTasks = selectedTasks.filter((task: any) => task.status !== "running" && !task.local_pending);
  const skippedCount = selectedTasks.length - deletableTasks.length;
  if (!deletableTasks.length) {
    setStatus(formatTranslation("batch.runningCannotDeleteSelected"), "error");
    return;
  }
  openConfirmPopover(els.batchDeleteButton, {
    title: formatTranslation("batch.deleteTitle", { count: deletableTasks.length }),
    message: formatTranslation("batch.deleteMessage"),
    detail: skippedCount ? formatTranslation("batch.deleteSkippedDetail", { count: skippedCount }) : "",
    confirmText: formatTranslation("action.delete"),
    onConfirm: async () => {
      await deleteSelectedTasks(deletableTasks, skippedCount);
    },
  });
}

async function deleteSelectedTasks(deletableTasks: any, skippedCount = 0) {
  try {
    for (const task of deletableTasks as any[]) {
      await deleteTaskById(task.task_id);
    }
    state.batchSelectedTaskIds = [];
    state.batchMode = false;
    renderTasks();
    renderArchiveButton();
    renderArchiveModal();
    renderPreview();
    const skippedText = skippedCount ? formatTranslation("batch.deleteSkippedSuffix", { count: skippedCount }) : "";
    setStatus(formatTranslation("batch.deletedCount", { count: deletableTasks.length, skipped: skippedText }), "ok");
  } catch (error) {
    renderTasks();
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
  els.taskList.querySelectorAll(TASK_CARD_SELECTOR).forEach((card: any) => {
    const selected = nextSet.has(String(card.dataset.taskId));
    card.classList.toggle("batch-selected", selected);
    const selectButton = card.querySelector("[data-batch-select-task-id]");
    if (selectButton) selectButton.setAttribute("aria-pressed", selected ? "true" : "false");
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
    renderBatchToolbar,
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

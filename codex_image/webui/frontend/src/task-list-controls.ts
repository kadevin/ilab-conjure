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

const renderTasks = () => legacyMethod("renderTasks");
const syncTaskSearchHistoryResults = () => legacyMethod("syncTaskSearchHistoryResults");
const taskSearchQuery = () => legacyMethod("taskSearchQuery");
const filteredVisibleTasks = (...args: any[]) => legacyMethod("filteredVisibleTasks", ...args);
const taskHistoryGroups = (...args: any[]) => legacyMethod("taskHistoryGroups", ...args);
const setExpandedTaskGroupKey = (...args: any[]) => legacyMethod("setExpandedTaskGroupKey", ...args);
const scrollExpandedTaskGroupToTop = (...args: any[]) => legacyMethod("scrollExpandedTaskGroupToTop", ...args);
const captureTaskHistoryLayout = (...args: any[]) => legacyMethod("captureTaskHistoryLayout", ...args);
const animateTaskHistoryLayout = (...args: any[]) => legacyMethod("animateTaskHistoryLayout", ...args);
const archiveTask = (...args: any[]) => legacyMethod("archiveTask", ...args);
const openTaskDeleteConfirm = (...args: any[]) => legacyMethod("openTaskDeleteConfirm", ...args);
const toggleBatchMode = (...args: any[]) => legacyMethod("toggleBatchMode", ...args);
const toggleBatchTaskSelection = (...args: any[]) => legacyMethod("toggleBatchTaskSelection", ...args);
const handleBatchTaskShortcutSelection = (...args: any[]) => legacyMethod("handleBatchTaskShortcutSelection", ...args);
const archiveSelectedTasks = (...args: any[]) => legacyMethod("archiveSelectedTasks", ...args);
const openBatchDeleteConfirm = (...args: any[]) => legacyMethod("openBatchDeleteConfirm", ...args);
const handleTaskListPointerDown = (...args: any[]) => legacyMethod("handleTaskListPointerDown", ...args);
const closeArchiveModal = (...args: any[]) => legacyMethod("closeArchiveModal", ...args);

let taskListControlsInitialized = false;
let taskListControlEventsBound = false;

function bindTaskListControlEvents() {
  if (taskListControlEventsBound) return;
  taskListControlEventsBound = true;

  els.archiveModalClose?.addEventListener("click", closeArchiveModal);
  els.archiveModal?.addEventListener("click", (event: any) => {
    if (event.target === els.archiveModal) closeArchiveModal();
  });
  els.batchManageButton?.addEventListener("click", () => toggleBatchMode());
  els.batchArchiveButton?.addEventListener("click", archiveSelectedTasks);
  els.batchDeleteButton?.addEventListener("click", openBatchDeleteConfirm);
  els.batchCancelButton?.addEventListener("click", () => toggleBatchMode(false));
  els.taskSearch.addEventListener("input", handleTaskSearchInput);
  [els.taskRatioFilter, els.taskOrientationFilter, els.taskPromptFidelityFilter, els.taskResolutionFilter]
    .filter(Boolean)
    .forEach((element: any) => {
      element.addEventListener("change", renderTasks);
    });
  bindTaskListEvents();
}

function handleTaskSearchInput() {
  renderTasks();
  void syncTaskSearchHistoryResults();
}

function replacementGroupKey(currentKey: string) {
  const query = taskSearchQuery();
  const groups = taskHistoryGroups(filteredVisibleTasks(query), query).filter((group: any) => group.tasks.length);
  const index = groups.findIndex((group: any) => String(group.key) === String(currentKey));
  return groups[index + 1]?.key || groups[index - 1]?.key || "";
}

function bindTaskListEvents() {
  const interactiveRoot = els.taskHistoryShell || els.sidebarContent || els.taskList;
  interactiveRoot?.addEventListener("click", handleTaskListClick);
  interactiveRoot?.addEventListener("keydown", handleTaskListKeydown);
  els.taskList?.addEventListener("pointerdown", handleTaskListPointerDown);
}

function taskHistoryInteractiveRoot() {
  return els.taskHistoryShell || els.sidebarContent || els.taskList;
}

function commitExpandedTaskGroupKey(nextKey: string | null, behavior: ScrollBehavior | null = null) {
  const previousLayout = captureTaskHistoryLayout();
  const changed = nextKey === null
    ? setExpandedTaskGroupKey(null, { immediate: true })
    : setExpandedTaskGroupKey(nextKey, { immediate: true });
  if (changed) {
    renderTasks();
    animateTaskHistoryLayout(previousLayout);
  }
  if (nextKey && behavior) {
    scrollExpandedTaskGroupToTop(behavior);
  }
}

function collapseExpandedTaskGroup(nextKey: string | null) {
  commitExpandedTaskGroupKey(nextKey);
}

function handleTaskListClick(event: any) {
  if (state.suppressTaskClickAfterDrag) {
    state.suppressTaskClickAfterDrag = false;
    event.preventDefault();
    event.stopPropagation();
    return;
  }

  const toggleButton = event.target.closest("[data-task-group-toggle-key]");
  if (toggleButton) {
    event.stopPropagation();
    const key = String(toggleButton.dataset.taskGroupToggleKey || "");
    if (toggleButton.classList.contains("task-group-header-split")) {
      collapseExpandedTaskGroup(null);
    } else {
      commitExpandedTaskGroupKey(key, "auto");
    }
    return;
  }

  const archiveButton = event.target.closest("[data-archive-task-id]");
  if (archiveButton) {
    event.stopPropagation();
    archiveTask(archiveButton.dataset.archiveTaskId);
    return;
  }

  const batchButton = event.target.closest("[data-batch-select-task-id]");
  if (batchButton) {
    event.stopPropagation();
    toggleBatchTaskSelection(batchButton.dataset.batchSelectTaskId);
    return;
  }

  const deleteButton = event.target.closest("[data-delete-task-id]");
  if (deleteButton) {
    event.stopPropagation();
    openTaskDeleteConfirm(deleteButton, deleteButton.dataset.deleteTaskId);
    return;
  }

  const card = event.target.closest(".task-card[data-task-id]");
  const root = taskHistoryInteractiveRoot();
  if (!card || !root?.contains(card)) return;
  if (handleBatchTaskShortcutSelection(card.dataset.taskId, event)) return;
  if (state.batchMode) {
    toggleBatchTaskSelection(card.dataset.taskId);
    return;
  }
  legacyMethod("selectTask", card.dataset.taskId);
}

function handleTaskListKeydown(event: any) {
  if (event.key !== "Enter" && event.key !== " ") return;
  const card = event.target.closest(".task-card[data-task-id]");
  const root = taskHistoryInteractiveRoot();
  if (!card || !root?.contains(card) || event.target.closest("button")) return;
  event.preventDefault();
  if (handleBatchTaskShortcutSelection(card.dataset.taskId, event)) return;
  if (state.batchMode) {
    toggleBatchTaskSelection(card.dataset.taskId);
  } else {
    legacyMethod("selectTask", card.dataset.taskId);
  }
}

export function initTaskListControlsFeature() {
  if (taskListControlsInitialized) return;
  taskListControlsInitialized = true;
  Object.assign(getLegacyBridge().methods, {
    bindTaskListControlEvents,
    bindTaskListEvents,
    handleTaskListClick,
    handleTaskListKeydown,
  });
}

import { LOCALE_CHANGE_EVENT, translate } from "./i18n";
import { getLegacyBridge } from "./state";
import { createTaskCardView } from "./task-card-view";
import { createTaskListModel } from "./task-list-model";
import { createTaskListViewport } from "./task-list-viewport";
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

function escapeHtml(...args: any[]) { return legacyMethod("escapeHtml", ...args); }
function updateDocumentTitle(...args: any[]) { return legacyMethod("updateDocumentTitle", ...args); }
function isTaskArchived(...args: any[]) { return legacyMethod("isTaskArchived", ...args); }
function taskArchived(...args: any[]) { return legacyMethod("taskArchived", ...args); }
function renderBatchToolbar(...args: any[]) { return legacyMethod("renderBatchToolbar", ...args); }
function updateTaskElapsedDisplays(...args: any[]) { return legacyMethod("updateTaskElapsedDisplays", ...args); }
function taskBackendLabel(...args: any[]) { return legacyMethod("taskBackendLabel", ...args); }
function taskApiProviderId(...args: any[]) { return legacyMethod("taskApiProviderId", ...args); }
function taskApiProviderLabel(...args: any[]) { return legacyMethod("taskApiProviderLabel", ...args); }
function formatTaskCardStatus(...args: any[]) { return legacyMethod("formatTaskCardStatus", ...args); }
function formatTaskStatus(...args: any[]) { return legacyMethod("formatTaskStatus", ...args); }
function ensureExpandedTaskGroupKey(...args: any[]) { return legacyMethod("ensureExpandedTaskGroupKey", ...args); }
function renderTaskHistoryAnchors(...args: any[]) { return legacyMethod("renderTaskHistoryAnchors", ...args); }
function setExpandedTaskGroupKey(...args: any[]) { return legacyMethod("setExpandedTaskGroupKey", ...args); }
function scrollExpandedTaskGroupToTop(...args: any[]) { return legacyMethod("scrollExpandedTaskGroupToTop", ...args); }
function captureTaskHistoryLayout(...args: any[]) { return legacyMethod("captureTaskHistoryLayout", ...args); }
function animateTaskHistoryLayout(...args: any[]) { return legacyMethod("animateTaskHistoryLayout", ...args); }
function scheduleLatestTaskNavigationRefresh(...args: any[]) { return legacyMethod("scheduleLatestTaskNavigationRefresh", ...args); }
function scheduleSidebarTaskGroupAutoLoad(...args: any[]) {
  const method = getLegacyBridge().methods.scheduleSidebarTaskGroupAutoLoad;
  return typeof method === "function" ? method(...args) : undefined;
}
function consumeLatestTaskNavigationScrollAnchor(...args: any[]) { return legacyMethod("consumeLatestTaskNavigationScrollAnchor", ...args); }
function rememberLatestTaskNavigationBeforeRender(...args: any[]) { return legacyMethod("rememberLatestTaskNavigationBeforeRender", ...args); }
const taskRatio = (...args: any[]) => legacyMethod("taskRatio", ...args);
const taskOrientation = (...args: any[]) => legacyMethod("taskOrientation", ...args);
const taskPromptFidelity = (...args: any[]) => legacyMethod("taskPromptFidelity", ...args);
const taskResolution = (...args: any[]) => legacyMethod("taskResolution", ...args);
const taskInputPreviewUrls = (...args: any[]) => legacyMethod("taskInputPreviewUrls", ...args);
const taskThumbnailUrls = (...args: any[]) => legacyMethod("taskThumbnailUrls", ...args);
const taskOutputUrls = (...args: any[]) => legacyMethod("taskOutputUrls", ...args);
const taskImageBlockStates = (...args: any[]) => legacyMethod("taskImageBlockStates", ...args);
const compressTaskImageBlockStates = (...args: any[]) => legacyMethod("compressTaskImageBlockStates", ...args);
const taskImageStatusCounts = (...args: any[]) => legacyMethod("taskImageStatusCounts", ...args);
const taskRetryStateText = (...args: any[]) => legacyMethod("taskRetryStateText", ...args);
const taskCardRetryStateText = (...args: any[]) => legacyMethod("taskCardRetryStateText", ...args);
const taskDurationText = (...args: any[]) => legacyMethod("taskDurationText", ...args);
const taskRuntimeText = (...args: any[]) => legacyMethod("taskRuntimeText", ...args);
const taskProgressStartValue = (...args: any[]) => legacyMethod("taskProgressStartValue", ...args);
const elapsedTimerSpan = (...args: any[]) => legacyMethod("elapsedTimerSpan", ...args);
const taskCompletionTimestampText = (...args: any[]) => legacyMethod("taskCompletionTimestampText", ...args);
const taskCompletionTimestampTitle = (...args: any[]) => legacyMethod("taskCompletionTimestampTitle", ...args);
const timestampMs = (...args: any[]) => legacyMethod("timestampMs", ...args);


const { taskAnchorLayout, taskSearchHistoryResultMatches, taskMatchesSearch, taskMatchesFilters, activeTaskSections, activeTaskGroup, taskQueueSection, waitingQueueIndex, taskHasUnreadUpdate, taskHasViewableUpdate, taskHistoryGroups, isAlwaysVisibleTask, queueTaskIdsBySection, activeTaskOrderIndex, activeTasksForGroup, taskHistoryActivityTimestamp, taskDateBucket, taskGroupCount, taskListRenderKey, activeQueueTaskListRenderKey } = createTaskListModel({
  getState: () => ({ activeTaskGroupCollapsed: state.activeTaskGroupCollapsed, batchMode: state.batchMode, batchSelectedTaskIds: state.batchSelectedTaskIds, expandedTaskGroupKey: state.expandedTaskGroupKey, historyTaskReveal: state.historyTaskReveal, queue: state.queue, selectedTaskId: state.selectedTaskId, taskSearchHistoryResultIds: state.taskSearchHistoryResultIds, taskSearchHistoryResultQuery: state.taskSearchHistoryResultQuery, taskSidebarGroupCounts: state.taskSidebarGroupCounts, tasks: state.tasks }),
  taskArchived: (...args: Parameters<typeof taskArchived>) => taskArchived(...args),
  taskBackendLabel: (...args: Parameters<typeof taskBackendLabel>) => taskBackendLabel(...args),
  taskFilterValues: (...args: Parameters<typeof taskFilterValues>) => taskFilterValues(...args),
  taskOrientation: (...args: Parameters<typeof taskOrientation>) => taskOrientation(...args),
  taskOutputUrls: (...args: Parameters<typeof taskOutputUrls>) => taskOutputUrls(...args),
  taskPromptFidelity: (...args: Parameters<typeof taskPromptFidelity>) => taskPromptFidelity(...args),
  taskRatio: (...args: Parameters<typeof taskRatio>) => taskRatio(...args),
  taskResolution: (...args: Parameters<typeof taskResolution>) => taskResolution(...args),
  timestampMs: (...args: Parameters<typeof timestampMs>) => timestampMs(...args),
});

const { expandedTaskGroupHeaderHtml, renderExpandedTaskGroupBodyShellHtml, renderExpandedTaskGroupShellHtml, activeTaskSectionHtml, activeTaskDispatchPendingHtml, activeTaskGroupHtml, expandedTaskGroupHtml, taskGroupHtml, taskGroupButtonLabel, taskQueueReorderHintVisible, taskQueueReorderHintHtml, taskCardSwipeActionLabel, taskCardSwipeActionTitle, taskCardSwipeActionHtml, taskCardSwipeActionsHtml, taskCardSwipeKeyboardShortcuts, taskCardHtml, taskGroupLoadMoreHtml, taskThumbShowsLoading, taskThumbSpinnerStyle, taskThumbHtml, taskStatusLabelHtml, taskModelFamilyIconHtml, taskStatusAccessibleLabel, taskMetaDetailsText, taskMetaDetailsWithCompletionText, taskCardCompletionTimeText, taskCardElapsedLineHtml, taskCardRunningTimerHtml, taskCardProviderLabel, taskCardRuntimeText, taskImageBlocksHtml, taskImageSummaryText, taskImageSummaryVisible, taskMetaText } = createTaskCardView({
  getState: () => ({ activeTaskGroupCollapsed: state.activeTaskGroupCollapsed, batchMode: state.batchMode, batchSelectedTaskIds: state.batchSelectedTaskIds, generationCatalog: state.generationCatalog, queue: state.queue, selectedTaskId: state.selectedTaskId, taskSidebarGroupLoadError: state.taskSidebarGroupLoadError, taskSidebarGroupLoadedCounts: state.taskSidebarGroupLoadedCounts, taskSidebarGroupLoading: state.taskSidebarGroupLoading }),
  activeTaskSections: (...args: Parameters<typeof activeTaskSections>) => activeTaskSections(...args),
  compressTaskImageBlockStates: (...args: Parameters<typeof compressTaskImageBlockStates>) => compressTaskImageBlockStates(...args),
  elapsedTimerSpan: (...args: Parameters<typeof elapsedTimerSpan>) => elapsedTimerSpan(...args),
  escapeHtml: (...args: Parameters<typeof escapeHtml>) => escapeHtml(...args),
  formatTaskCardStatus: (...args: Parameters<typeof formatTaskCardStatus>) => formatTaskCardStatus(...args),
  formatTaskStatus: (...args: Parameters<typeof formatTaskStatus>) => formatTaskStatus(...args),
  queueTaskIdsBySection: (...args: Parameters<typeof queueTaskIdsBySection>) => queueTaskIdsBySection(...args),
  taskApiProviderId: (...args: Parameters<typeof taskApiProviderId>) => taskApiProviderId(...args),
  taskApiProviderLabel: (...args: Parameters<typeof taskApiProviderLabel>) => taskApiProviderLabel(...args),
  taskCardRetryStateText: (...args: Parameters<typeof taskCardRetryStateText>) => taskCardRetryStateText(...args),
  taskCompletionTimestampText: (...args: Parameters<typeof taskCompletionTimestampText>) => taskCompletionTimestampText(...args),
  taskCompletionTimestampTitle: (...args: Parameters<typeof taskCompletionTimestampTitle>) => taskCompletionTimestampTitle(...args),
  taskDurationText: (...args: Parameters<typeof taskDurationText>) => taskDurationText(...args),
  taskGroupCount: (...args: Parameters<typeof taskGroupCount>) => taskGroupCount(...args),
  taskHasUnreadUpdate: (...args: Parameters<typeof taskHasUnreadUpdate>) => taskHasUnreadUpdate(...args),
  taskImageBlockStates: (...args: Parameters<typeof taskImageBlockStates>) => taskImageBlockStates(...args),
  taskImageStatusCounts: (...args: Parameters<typeof taskImageStatusCounts>) => taskImageStatusCounts(...args),
  taskInputPreviewUrls: (...args: Parameters<typeof taskInputPreviewUrls>) => taskInputPreviewUrls(...args),
  taskOutputUrls: (...args: Parameters<typeof taskOutputUrls>) => taskOutputUrls(...args),
  taskProgressStartValue: (...args: Parameters<typeof taskProgressStartValue>) => taskProgressStartValue(...args),
  taskQueueSection: (...args: Parameters<typeof taskQueueSection>) => taskQueueSection(...args),
  taskRetryStateText: (...args: Parameters<typeof taskRetryStateText>) => taskRetryStateText(...args),
  taskRuntimeText: (...args: Parameters<typeof taskRuntimeText>) => taskRuntimeText(...args),
  taskThumbnailUrls: (...args: Parameters<typeof taskThumbnailUrls>) => taskThumbnailUrls(...args),
  timestampMs: (...args: Parameters<typeof timestampMs>) => timestampMs(...args),
  waitingQueueIndex: (...args: Parameters<typeof waitingQueueIndex>) => waitingQueueIndex(...args),
  isQueueDispatchPending: () => legacyMethod("isQueueDispatchPending"),
});

const { captureTaskListScrollAnchors, captureTaskListScrollAnchor, restoreTaskListScrollAnchors, restoreTaskListScrollAnchor, applyActiveTaskGroupHtml, draggedTaskStillWaiting, renderActiveTaskGroup, flushDeferredActiveTaskGroupRender, discardDeferredActiveTaskGroupRender, expandedTaskGroupBodyElements, finalizeExpandedTaskGroupBody, animateExpandedTaskGroupBody, expandedTaskGroupItemsContainer, updateExpandedTaskGroupCount, appendExpandedTaskGroupPage, scheduleExpandedTaskGroupItemsRender, renderExpandedTaskGroupHeader, invalidateTaskGroupRender } = createTaskListViewport({
  getState: () => ({ queue: state.queue, queueDragTaskId: state.queueDragTaskId }),
  els: { taskHistoryShell: els.taskHistoryShell, sidebarContent: els.sidebarContent, taskActiveList: els.taskActiveList, taskList: els.taskList, taskHistoryCurrentAnchor: els.taskHistoryCurrentAnchor },
  consumeLatestTaskNavigationScrollAnchor: (...args: Parameters<typeof consumeLatestTaskNavigationScrollAnchor>) => consumeLatestTaskNavigationScrollAnchor(...args),
  expandedTaskGroupHeaderHtml: (...args: Parameters<typeof expandedTaskGroupHeaderHtml>) => expandedTaskGroupHeaderHtml(...args),
  scheduleLatestTaskNavigationRefresh: (...args: Parameters<typeof scheduleLatestTaskNavigationRefresh>) => scheduleLatestTaskNavigationRefresh(...args),
  scheduleSidebarTaskGroupAutoLoad: (...args: Parameters<typeof scheduleSidebarTaskGroupAutoLoad>) => scheduleSidebarTaskGroupAutoLoad(...args),
  taskCardHtml: (...args: Parameters<typeof taskCardHtml>) => taskCardHtml(...args),
  taskGroupCount: (...args: Parameters<typeof taskGroupCount>) => taskGroupCount(...args),
  taskGroupLoadMoreHtml: (...args: Parameters<typeof taskGroupLoadMoreHtml>) => taskGroupLoadMoreHtml(...args),
  updateTaskElapsedDisplays: (...args: Parameters<typeof updateTaskElapsedDisplays>) => updateTaskElapsedDisplays(...args),
  cancelActiveTaskQueueReorder: (options) => getLegacyBridge().methods.cancelActiveTaskQueueReorder?.(options),
  consumeExpansionAnimation: () => { const pending = state.expandedTaskGroupAnimationPending === true; state.expandedTaskGroupAnimationPending = false; return pending; },
});

function renderTasks(options: { preserveScroll?: boolean; appendGroupKey?: string } = {}) {
  if (options.preserveScroll) rememberLatestTaskNavigationBeforeRender();
  const scrollAnchors = options.preserveScroll ? captureTaskListScrollAnchors() : [];
  const query = taskSearchQuery();
  const filters = taskFilterValues();
  const revealedTaskId = String(
    state.historyTaskReveal?.ready
      && String(state.historyTaskReveal?.taskId || "") === String(state.selectedTaskId || "")
      ? state.historyTaskReveal.taskId
      : "",
  );
  const visibleTasks = state.tasks.filter((task: any) => (
    !isTaskArchived(task.task_id) || String(task?.task_id || "") === revealedTaskId
  ));
  const tasks = visibleTasks.filter((task: any) => {
    return String(task?.task_id || "") === revealedTaskId
      || (taskMatchesSearch(task, query) && taskMatchesFilters(task, filters));
  });
  const visibleTaskIds = visibleTasks.map((task: any) => String(task.task_id));
  if (!state.batchSelectionIncludesUnloaded) {
    state.batchSelectedTaskIds = state.batchSelectedTaskIds.filter((taskId: any) => visibleTaskIds.includes(String(taskId)));
  }
  renderBatchToolbar();
  const activeGroup = activeTaskGroup(tasks, query);
  const groups = taskHistoryGroups(tasks, query);
  const expandedGroup = ensureExpandedTaskGroupKey(groups);
  const layout = taskAnchorLayout(groups, expandedGroup?.key || null, query);
  const nextRenderKey = taskListRenderKey(tasks, query, layout, filters, activeGroup);
  const appendGroupKey = String(options.appendGroupKey || "");
  if (
    appendGroupKey
    && appendExpandedTaskGroupPage(layout.expandedGroup, appendGroupKey, layout.expandedKey)
  ) {
    state.tasksRenderKey = nextRenderKey;
    updateExpandedTaskGroupCount(layout.expandedGroup);
    updateTaskElapsedDisplays();
    updateTaskSelectionVisuals();
    updateDocumentTitle();
    restoreTaskListScrollAnchors(scrollAnchors);
    scheduleLatestTaskNavigationRefresh();
    return;
  }
  if (!appendGroupKey && state.tasksRenderKey === nextRenderKey) {
    updateTaskElapsedDisplays();
    restoreTaskListScrollAnchors(scrollAnchors);
    scheduleLatestTaskNavigationRefresh();
    return;
  }
  state.tasksRenderKey = nextRenderKey;
  renderTaskHistoryAnchors(layout);
  const activeHtml = activeGroup ? activeTaskGroupHtml(activeGroup) : "";
  renderActiveTaskGroup(activeHtml);

  if (!tasks.length) {
    invalidateTaskGroupRender();
    renderExpandedTaskGroupHeader(null);
    els.taskList.innerHTML = `<div class="task-meta">${escapeHtml(translate("taskList.empty"))}</div>`;
    updateDocumentTitle();
    restoreTaskListScrollAnchors(scrollAnchors);
    scheduleLatestTaskNavigationRefresh();
    return;
  }
  if (!layout.expandedGroup) {
    invalidateTaskGroupRender();
    renderExpandedTaskGroupHeader(null);
    els.taskList.innerHTML = "";
    updateDocumentTitle();
    restoreTaskListScrollAnchors(scrollAnchors);
    scheduleLatestTaskNavigationRefresh();
    return;
  }

  const group = layout.expandedGroup;
  const shouldAnimateExpandedGroup = state.expandedTaskGroupAnimationPending === true;
  renderExpandedTaskGroupHeader(group, {
    startExpanded: !shouldAnimateExpandedGroup,
  });
  els.taskList.innerHTML = renderExpandedTaskGroupBodyShellHtml(group);
  scheduleExpandedTaskGroupItemsRender(group, layout.expandedKey || group?.key || null);
  updateDocumentTitle();
  restoreTaskListScrollAnchors(scrollAnchors);
  scheduleLatestTaskNavigationRefresh();
}

function taskCardRoot() {
  return els.taskHistoryShell || els.sidebarContent || els.taskList;
}

function taskCardElement(taskId: any) {
  const root = taskCardRoot();
  if (!root || taskId == null) return null;
  return root.querySelector(`.task-card[data-task-id="${cssEscape(taskId)}"]`);
}

function updateTaskSelectionVisuals(taskId: any = state.selectedTaskId) {
  const root = taskCardRoot();
  if (!root) return;
  const selectedId = taskId == null ? "" : String(taskId);
  root.querySelectorAll(".task-card.active").forEach((card: any) => {
    if (String(card.dataset.taskId || "") !== selectedId) {
      card.classList.remove("active");
      card.removeAttribute("aria-current");
    }
  });
  const selectedCard = taskCardElement(taskId);
  if (selectedCard) {
    selectedCard.classList.add("active");
    selectedCard.setAttribute("aria-current", "true");
    selectedCard.dataset.activeLabel = translate("taskList.viewing");
    selectedCard.classList.remove("unread");
    selectedCard.dataset.taskUnread = "false";
    selectedCard.querySelector(".task-unread-dot")?.remove();
  }
  updateDocumentTitle();
}

function taskSearchQuery() {
  return String(state.taskSearchQuery || "").trim().toLowerCase();
}

function taskFilterValues() {
  return {
    status: els.taskStatusFilter?.value || "",
    ratio: els.taskRatioFilter?.value || "",
    orientation: els.taskOrientationFilter?.value || "",
    promptFidelity: els.taskPromptFidelityFilter?.value || "",
    resolution: els.taskResolutionFilter?.value || "",
  };
}

function filteredVisibleTasks(query: any = taskSearchQuery(), filters: any = taskFilterValues()) {
  return state.tasks.filter((task: any) => {
    return !isTaskArchived(task.task_id) && taskMatchesSearch(task, query) && taskMatchesFilters(task, filters);
  });
}

function clearTaskListFiltersForActiveGroup() {
  let changed = false;
  if (els.taskSearch?.value) {
    els.taskSearch.value = "";
    changed = true;
  }
  [els.taskStatusFilter, els.taskRatioFilter, els.taskOrientationFilter, els.taskPromptFidelityFilter, els.taskResolutionFilter]
    .filter(Boolean)
    .forEach((element: any) => {
      if (element.value) {
        element.value = "";
        changed = true;
      }
    });
  if (changed) {
    getLegacyBridge().methods.updateTaskFilterSummary?.();
  }
  return changed;
}

function revealActiveTaskGroup() {
  const activeTasks = state.tasks.filter((task: any) => !isTaskArchived(task.task_id) && isAlwaysVisibleTask(task));
  if (!activeTasks.length) return;
  const visibleActiveTasks = filteredVisibleTasks().filter((task: any) => isAlwaysVisibleTask(task));
  const clearedControls = visibleActiveTasks.length ? false : clearTaskListFiltersForActiveGroup();
  const previousLayout = captureTaskHistoryLayout();
  if (clearedControls) {
    renderTasks();
    animateTaskHistoryLayout(previousLayout);
  }
  scrollExpandedTaskGroupToTop("smooth");
  if (clearedControls) {
    legacyMethod("setStatus", translate("status.shownActiveTasks"), "ok");
  }
}

export function initTaskListRenderFeature() {
  document.addEventListener(LOCALE_CHANGE_EVENT, () => {
    state.tasksRenderKey = null;
    renderTasks();
  });
  Object.assign(getLegacyBridge().methods, {
    renderTasks,
    flushDeferredActiveTaskGroupRender,
    discardDeferredActiveTaskGroupRender,
    taskSearchQuery,
    taskFilterValues,
    taskMatchesSearch,
    taskMatchesFilters,
    filteredVisibleTasks,
    taskAnchorLayout,
    renderExpandedTaskGroupHeader,
    renderExpandedTaskGroupBodyShellHtml,
    renderExpandedTaskGroupShellHtml,
    scheduleExpandedTaskGroupItemsRender,
    expandedTaskGroupHtml,
    activeTaskGroupHtml,
    activeTaskSections,
    activeTaskOrderIndex,
    revealActiveTaskGroup,
    taskGroupHtml,
    taskGroupButtonLabel,
    taskCardHtml,
    taskHasUnreadUpdate,
    taskHasViewableUpdate,
    taskHistoryGroups,
    taskHistoryActivityTimestamp,
    isAlwaysVisibleTask,
    taskDateBucket,
    taskGroupCount,
    taskListRenderKey,
    taskCardElement,
    updateTaskSelectionVisuals,
    taskThumbHtml,
    taskStatusLabelHtml,
    taskStatusAccessibleLabel,
    taskMetaDetailsText,
    taskCardProviderLabel,
    taskCardRuntimeText,
    taskImageBlocksHtml,
    taskImageSummaryText,
    taskMetaText,
  });
}

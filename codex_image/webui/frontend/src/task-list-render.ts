import { getLegacyBridge } from "./state";
import { taskWasCancelled } from "./task-cancellation";
import { cssEscape, prefersReducedMotion } from "./webui-utils";
import { formatTranslation, LOCALE_CHANGE_EVENT, translate } from "./i18n";
import { groundingAttributionKey, groundingSourceCount } from "./grounding-attribution";
import { modelFamilyBrandMarkHtml } from "./model-family-icons";
import {
  taskCanvasSummaryParts,
  taskChannelLabel,
  taskModelDisplayName,
  taskModelFamilyId,
} from "./task-model-summary";
import {
  taskCardSwipeActionsForState,
  TASK_QUEUE_REORDER_HINT_STORAGE_KEY,
  type TaskCardSwipeAction,
  type TaskCardSwipeActions,
} from "./task-card-swipe-logic";
import { sidebarTaskDateBucket } from "./history-task-reveal-model";

const bridge = getLegacyBridge();
const state = bridge.state;
const els = bridge.els;
const EXPANDED_TASK_GROUP_INITIAL_CARD_COUNT = 24;
const EXPANDED_TASK_GROUP_CHUNK_SIZE = 48;
const EXPANDED_TASK_GROUP_ANIMATION_FALLBACK_MS = 320;
const TASK_THUMB_OUTER_SPIN_DURATION_MS = 1300;
const TASK_THUMB_INNER_SPIN_DURATION_MS = 950;
const TASK_THUMB_INNER_SPIN_OFFSET_MS = 280;
let expandedTaskGroupRenderToken = 0;
type QueueTaskIdSections = { running: Map<string, number>; waiting: Map<string, number> };
type TaskListScrollAnchor = {
  scroller: HTMLElement;
  root: HTMLElement;
  scrollTop: number;
  taskId?: string;
  offsetTop?: number;
  retryMissingTask?: boolean;
};
let queueTaskIdsCacheKey = "";
let queueTaskIdsCache: QueueTaskIdSections | null = null;
let deferredActiveTaskHtml: string | null = null;

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
  renderHistoryLibraryGroup(tasks, query);
  const activeHtml = activeGroup ? activeTaskGroupHtml(activeGroup) : "";
  renderActiveTaskGroup(activeHtml);

  if (!tasks.length) {
    expandedTaskGroupRenderToken += 1;
    renderExpandedTaskGroupHeader(null);
    els.taskList.innerHTML = `<div class="task-meta">${escapeHtml(translate("taskList.empty"))}</div>`;
    updateDocumentTitle();
    restoreTaskListScrollAnchors(scrollAnchors);
    scheduleLatestTaskNavigationRefresh();
    return;
  }
  if (!layout.expandedGroup) {
    expandedTaskGroupRenderToken += 1;
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

function captureTaskListScrollAnchors(): TaskListScrollAnchor[] {
  const historyAnchor = captureTaskListScrollAnchor(
    els.sidebarContent || els.taskHistoryShell || els.taskList,
    els.taskList,
    { retryMissingTask: true },
  );
  return [
    captureTaskListScrollAnchor(els.taskActiveList, els.taskActiveList),
    consumeLatestTaskNavigationScrollAnchor(historyAnchor),
  ].filter((anchor): anchor is TaskListScrollAnchor => Boolean(anchor));
}

function captureTaskListScrollAnchor(
  scroller: HTMLElement | null,
  root: HTMLElement | null,
  { retryMissingTask = false }: { retryMissingTask?: boolean } = {},
): TaskListScrollAnchor | null {
  if (!scroller || !root) return null;
  const scrollerRect = scroller.getBoundingClientRect();
  const cards = Array.from(root.querySelectorAll(".task-card[data-task-id]")) as HTMLElement[];
  const visibleCard = cards.find((card) => {
    const rect = card.getBoundingClientRect();
    return rect.bottom > scrollerRect.top && rect.top < scrollerRect.bottom;
  });
  if (!visibleCard) return { scroller, root, scrollTop: scroller.scrollTop, retryMissingTask };
  const rect = visibleCard.getBoundingClientRect();
  const anchor: TaskListScrollAnchor = {
    scroller,
    root,
    scrollTop: scroller.scrollTop,
    offsetTop: rect.top - scrollerRect.top,
    retryMissingTask,
  };
  if (visibleCard.dataset.taskId) anchor.taskId = visibleCard.dataset.taskId;
  return anchor;
}

function restoreTaskListScrollAnchors(anchors: TaskListScrollAnchor[]): void {
  anchors.forEach(restoreTaskListScrollAnchor);
}

function restoreTaskListScrollAnchor(anchor: TaskListScrollAnchor | null): void {
  if (!anchor?.scroller) return;
  let attempts = 12;
  const restore = () => {
    if (!anchor.scroller.isConnected) return;
    if (anchor.taskId) {
      const card = anchor.root.querySelector(`.task-card[data-task-id="${cssEscape(anchor.taskId)}"]`);
      if (card instanceof HTMLElement) {
        const scrollerRect = anchor.scroller.getBoundingClientRect();
        const rect = card.getBoundingClientRect();
        anchor.scroller.scrollTop += rect.top - scrollerRect.top - (anchor.offsetTop || 0);
        return;
      }
    }
    if (anchor.taskId && anchor.retryMissingTask && attempts > 0) {
      attempts -= 1;
      requestAnimationFrame(restore);
      return;
    }
    anchor.scroller.scrollTop = anchor.scrollTop;
  };
  restore();
}

function renderHistoryLibraryGroup(tasks: any[], query: string) {
  if (!els.taskHistoryLibrarySlot) return;
  const html = historyLibraryGroup(tasks, query);
  els.taskHistoryLibrarySlot.innerHTML = html;
  els.taskHistoryLibrarySlot.classList.toggle("hidden", !html);
}

function applyActiveTaskGroupHtml(activeHtml: string) {
  if (!els.taskActiveList) return;
  els.taskActiveList.innerHTML = activeHtml;
  els.taskActiveList.classList.toggle("hidden", !activeHtml);
}

function draggedTaskStillWaiting(): boolean {
  const taskId = String(state.queueDragTaskId || "");
  return Boolean(taskId && (state.queue.waiting || []).some(
    (task: any) => String(task?.task_id || "") === taskId,
  ));
}

function renderActiveTaskGroup(activeHtml: string) {
  if (!els.taskActiveList) return;
  if (state.queueDragTaskId && draggedTaskStillWaiting()) {
    deferredActiveTaskHtml = activeHtml;
    return;
  }
  if (state.queueDragTaskId) {
    getLegacyBridge().methods.cancelActiveTaskQueueReorder?.({ flushDeferred: false });
  }
  deferredActiveTaskHtml = null;
  applyActiveTaskGroupHtml(activeHtml);
}

function flushDeferredActiveTaskGroupRender(): boolean {
  if (state.queueDragTaskId || deferredActiveTaskHtml === null) return false;
  const activeHtml = deferredActiveTaskHtml;
  deferredActiveTaskHtml = null;
  const anchor = captureTaskListScrollAnchor(els.taskActiveList, els.taskActiveList);
  applyActiveTaskGroupHtml(activeHtml);
  restoreTaskListScrollAnchor(anchor);
  updateTaskElapsedDisplays();
  return true;
}

function discardDeferredActiveTaskGroupRender(): boolean {
  if (deferredActiveTaskHtml === null) return false;
  deferredActiveTaskHtml = null;
  return true;
}

function taskAnchorLayout(groups: any[], expandedKey: string | null, query: string) {
  if (query) {
    return {
      top: [],
      bottom: [],
      expandedGroup: groups[0] || null,
      expandedKey: groups[0]?.key || expandedKey || null,
      queryMode: true,
    };
  }
  const index = groups.findIndex((group: any) => String(group.key) === String(expandedKey));
  if (index < 0) {
    return {
      top: groups,
      bottom: [],
      expandedGroup: null,
      expandedKey: null,
      queryMode: false,
    };
  }
  return {
    top: index > 0 ? groups.slice(0, index) : [],
    bottom: groups.slice(index + 1),
    expandedGroup: groups[index] || null,
    expandedKey,
    queryMode: false,
  };
}

function expandedTaskGroupBodyElements(groupKey: string) {
  const escapedGroupKey = cssEscape(groupKey);
  const body = els.taskList?.querySelector(
    `.task-group-items-expanded[data-expanded-task-group-items-key="${escapedGroupKey}"]`,
  ) as HTMLElement | null;
  const headerButton = els.taskHistoryCurrentAnchor?.querySelector(
    `.task-group-header-split[data-task-group-toggle-key="${escapedGroupKey}"]`,
  ) as HTMLElement | null;
  return { body, headerButton };
}

function finalizeExpandedTaskGroupBody(groupKey: string) {
  const { body, headerButton } = expandedTaskGroupBodyElements(groupKey);
  headerButton?.setAttribute("aria-expanded", "true");
  if (!body) return;
  body.style.maxHeight = "none";
  body.style.opacity = "1";
}

function animateExpandedTaskGroupBody(groupKey: string) {
  if (prefersReducedMotion()) {
    finalizeExpandedTaskGroupBody(groupKey);
    return;
  }
  const { body, headerButton } = expandedTaskGroupBodyElements(groupKey);
  if (!body) return;
  headerButton?.setAttribute("aria-expanded", "false");
  body.style.maxHeight = "0px";
  body.style.opacity = "0";
  void body.offsetHeight;
  requestAnimationFrame(() => {
    headerButton?.setAttribute("aria-expanded", "true");
    body.style.maxHeight = `${body.scrollHeight}px`;
    body.style.opacity = "1";
  });
  let fallbackTimerId = 0;
  const finalize = () => {
    window.clearTimeout(fallbackTimerId);
    body.removeEventListener("transitionend", handleTransitionEnd);
    body.style.maxHeight = "none";
    body.style.opacity = "1";
  };
  const handleTransitionEnd = (event: TransitionEvent) => {
    if (event.propertyName !== "max-height") return;
    finalize();
  };
  body.addEventListener("transitionend", handleTransitionEnd);
  fallbackTimerId = window.setTimeout(finalize, EXPANDED_TASK_GROUP_ANIMATION_FALLBACK_MS);
}

function expandedTaskGroupItemsContainer(groupKey: string) {
  if (!els.taskList) return null;
  return els.taskList.querySelector(
    `.task-group-items-expanded[data-expanded-task-group-items-key="${cssEscape(groupKey)}"]`,
  ) as HTMLElement | null;
}

function updateExpandedTaskGroupCount(group: any) {
  if (!group || !els.taskHistoryCurrentAnchor) return;
  const count = els.taskHistoryCurrentAnchor.querySelector(".task-group-count");
  if (count) count.textContent = String(taskGroupCount(group));
}

function appendExpandedTaskGroupPage(
  group: any,
  requestedGroupKey: string,
  activeGroupKey: string | null = null,
) {
  const groupKey = String(group?.key || "");
  const normalizedActiveGroupKey = String(activeGroupKey || groupKey);
  if (!groupKey || groupKey !== requestedGroupKey || normalizedActiveGroupKey !== groupKey) return false;
  const body = expandedTaskGroupItemsContainer(groupKey);
  if (!body || body.dataset.renderComplete !== "true") return false;
  const tasks = Array.isArray(group?.tasks) ? group.tasks : [];
  const existingCards = Array.from(body.querySelectorAll(".task-card[data-task-id]")) as HTMLElement[];
  if (existingCards.length > tasks.length) return false;
  const existingCardsMatch = existingCards.every((card, index) => (
    String(card.dataset.taskId || "") === String(tasks[index]?.task_id || "")
  ));
  if (!existingCardsMatch) return false;

  body.querySelectorAll("[data-load-more-task-group]").forEach((element) => element.remove());
  body.dataset.renderComplete = "false";
  scheduleExpandedTaskGroupItemsRender(group, normalizedActiveGroupKey, {
    startIndex: existingCards.length,
    preserveExisting: true,
  });
  return true;
}

function scheduleExpandedTaskGroupItemsRender(
  group: any,
  activeGroupKey: string | null = null,
  options: { startIndex?: number; preserveExisting?: boolean } = {},
) {
  const tasks = Array.isArray(group?.tasks) ? group.tasks : [];
  const groupKey = String(group?.key || "");
  if (!groupKey) return;
  const normalizedActiveGroupKey = String(activeGroupKey || groupKey);
  const preserveExisting = options.preserveExisting === true;
  const startIndex = Math.min(tasks.length, Math.max(0, Number(options.startIndex || 0)));
  const shouldAnimateExpand = !preserveExisting && state.expandedTaskGroupAnimationPending === true;
  state.expandedTaskGroupAnimationPending = false;
  const token = ++expandedTaskGroupRenderToken;
  let index = startIndex;
  const renderChunk = () => {
    if (token !== expandedTaskGroupRenderToken) return;
    if (normalizedActiveGroupKey !== groupKey) return;
    const body = expandedTaskGroupItemsContainer(groupKey);
    if (!body) return;
    const firstChunk = index === startIndex;
    const chunkSize = !preserveExisting && firstChunk
      ? EXPANDED_TASK_GROUP_INITIAL_CARD_COUNT
      : EXPANDED_TASK_GROUP_CHUNK_SIZE;
    const nextTasks = tasks.slice(index, index + chunkSize);
    if (!nextTasks.length) {
      body.insertAdjacentHTML("beforeend", taskGroupLoadMoreHtml(group));
      finalizeExpandedTaskGroupBody(groupKey);
      body.dataset.renderComplete = "true";
      scheduleLatestTaskNavigationRefresh();
      scheduleSidebarTaskGroupAutoLoad();
      return;
    }
    body.insertAdjacentHTML("beforeend", nextTasks.map((task: any) => taskCardHtml(task)).join(""));
    index += nextTasks.length;
    if (firstChunk) {
      if (shouldAnimateExpand) {
        animateExpandedTaskGroupBody(groupKey);
      } else {
        finalizeExpandedTaskGroupBody(groupKey);
      }
    } else if (body.style.maxHeight && body.style.maxHeight !== "none") {
      body.style.maxHeight = `${body.scrollHeight}px`;
    }
    if (index < tasks.length) {
      requestAnimationFrame(renderChunk);
    } else {
      body.insertAdjacentHTML("beforeend", taskGroupLoadMoreHtml(group));
      body.dataset.renderComplete = "true";
      scheduleSidebarTaskGroupAutoLoad();
    }
    scheduleLatestTaskNavigationRefresh();
  };
  requestAnimationFrame(renderChunk);
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

function taskSearchHistoryResultMatches(taskId: string, query: string) {
  if (!taskId || !query) return false;
  if (String(state.taskSearchHistoryResultQuery || "") !== query) return false;
  return (state.taskSearchHistoryResultIds || []).some((id: any) => String(id) === taskId);
}

function taskMatchesSearch(task: any, query: any) {
  const normalizedQuery = String(query || "").trim().toLowerCase();
  const taskId = String(task?.task_id || "");
  if (taskSearchHistoryResultMatches(taskId, normalizedQuery)) {
    return true;
  }
  const text = `${task.task_id || ""} ${task.prompt || ""} ${task.status || ""} ${task.mode || ""} ${taskBackendLabel(task)}`.toLowerCase();
  return text.includes(normalizedQuery);
}

function taskMatchesFilters(task: any, filters: any) {
  if (filters.status && String(task?.status || "") !== filters.status) return false;
  if (filters.ratio && taskRatio(task) !== filters.ratio) return false;
  if (filters.orientation && taskOrientation(task) !== filters.orientation) return false;
  if (filters.promptFidelity && taskPromptFidelity(task) !== filters.promptFidelity) return false;
  if (filters.resolution && taskResolution(task) !== filters.resolution) return false;
  return true;
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

function expandedTaskGroupHeaderHtml(group: any, options: { startExpanded?: boolean } = {}) {
  const groupKey = escapeHtml(group.key);
  const startExpanded = options.startExpanded !== false;
  return `
    <button
      class="task-group-header task-group-header-split"
      type="button"
      data-task-group-toggle-key="${groupKey}"
      data-task-group-expanded="true"
      aria-expanded="${startExpanded ? "true" : "false"}"
      aria-label="${escapeHtml(formatTranslation("taskGroup.collapse", { label: group.label }))}"
    >
      <span class="task-group-label-button">
        <span class="task-group-title">
          <span class="task-group-label">${escapeHtml(group.label)}</span>
          <span class="task-group-count-separator" aria-hidden="true">·</span>
          <span class="task-group-count">${taskGroupCount(group)}</span>
        </span>
      </span>
      <span
        class="task-group-arrow-button"
        aria-hidden="true"
      >
        <span class="task-group-toggle" aria-hidden="true">
          <svg class="task-group-toggle-icon" viewBox="0 0 12 12" focusable="false">
            <path d="M4 2.5 8 6 4 9.5" fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" stroke-width="1.8"/>
          </svg>
        </span>
      </span>
    </button>
  `;
}

function renderExpandedTaskGroupHeader(group: any | null, options: { startExpanded?: boolean } = {}) {
  if (!els.taskHistoryCurrentAnchor) return;
  const html = group ? expandedTaskGroupHeaderHtml(group, options) : "";
  els.taskHistoryCurrentAnchor.innerHTML = html;
  els.taskHistoryCurrentAnchor.classList.toggle("hidden", !html);
}

function renderExpandedTaskGroupBodyShellHtml(group: any) {
  const groupKey = escapeHtml(group.key);
  return `
    <section class="task-group task-group-expanded" data-task-group="${groupKey}">
      <div class="task-group-items task-group-items-expanded" data-expanded-task-group-items-key="${groupKey}"></div>
    </section>
  `;
}

function renderExpandedTaskGroupShellHtml(group: any, options: { startExpanded?: boolean } = {}) {
  const groupKey = escapeHtml(group.key);
  return `
    <section class="task-group task-group-expanded" data-task-group="${groupKey}">
      ${expandedTaskGroupHeaderHtml(group, options)}
      <div class="task-group-items task-group-items-expanded" data-expanded-task-group-items-key="${groupKey}"></div>
    </section>
  `;
}

function activeTaskSections(tasks: any[]) {
  const queueIds = queueTaskIdsBySection();
  const running: any[] = [];
  const waiting: any[] = [];
  tasks.forEach((task: any) => {
    const taskId = String(task?.task_id || "");
    const status = String(task?.status || "");
    if (queueIds.running.has(taskId) || status === "running" || status === "cancelling") {
      running.push(task);
    } else if (queueIds.waiting.has(taskId) || task?.local_pending || ["submitting", "queued"].includes(status)) {
      waiting.push(task);
    }
  });
  return { running, waiting };
}

function activeTaskSectionHtml(key: "running" | "waiting", label: string, tasks: any[]) {
  if (!tasks.length) return "";
  const sectionClass = key === "running"
    ? 'class="task-active-section task-active-section-running"'
    : 'class="task-active-section task-active-section-waiting"';
  const sectionData = key === "running"
    ? 'data-active-task-section="running"'
    : 'data-active-task-section="waiting"';
  const reorderHint = key === "waiting" ? taskQueueReorderHintHtml(tasks.length) : "";
  return `
    <div ${sectionClass} ${sectionData}>
      <div class="task-active-section-title">
        <span class="task-active-section-heading">
          <span>${escapeHtml(label)}</span>
          <span class="task-active-section-count-separator" aria-hidden="true">·</span>
          <span class="task-active-section-count">${tasks.length}</span>
        </span>
        ${reorderHint}
      </div>
      <div class="task-active-section-items">
        ${tasks.map((task: any) => taskCardHtml(task)).join("")}
      </div>
    </div>
  `;
}

function activeTaskDispatchPendingHtml() {
  return `
    <div class="task-active-empty" data-active-task-section="dispatch-pending">
      ${translate("taskGroup.dispatchPending")}
    </div>
  `;
}

function activeTaskGroup(tasks: any[], query: any = "") {
  if (query) return null;
  const activeTasks = activeTasksForGroup(tasks);
  if (!activeTasks.length) return null;
  return {
    key: "active",
    label: translate("sidebar.activeTasks"),
    tasks: activeTasks,
    collapsible: false,
    defaultCollapsed: false,
  };
}

function activeTaskGroupHtml(group: any) {
  const groupKey = escapeHtml(group.key);
  const sections = activeTaskSections(group.tasks || []);
  const dispatchPending = Boolean(legacyMethod("isQueueDispatchPending"));
  const collapsed = Boolean(state.activeTaskGroupCollapsed);
  const body = [
    activeTaskSectionHtml("running", translate("taskGroup.running"), sections.running),
    activeTaskSectionHtml("waiting", translate("taskGroup.waiting"), sections.waiting),
    !sections.running.length && !sections.waiting.length && dispatchPending ? activeTaskDispatchPendingHtml() : "",
  ].join("");
  const activeLabel = escapeHtml(group.label);
  const activeCount = group.tasks.length;
  const toggleLabel = escapeHtml(formatTranslation(collapsed ? "taskGroup.expand" : "taskGroup.collapse", { label: group.label }));
  return `
    <section class="task-group task-group-expanded task-group-active${collapsed ? " task-active-collapsed" : ""}" data-task-group="${groupKey}">
      <button
        class="task-group-header task-group-header-split task-active-group-header"
        type="button"
        data-active-task-group-toggle="true"
        aria-expanded="${collapsed ? "false" : "true"}"
        aria-label="${toggleLabel}"
      >
        <span class="task-group-label-button">
          <span class="task-group-title">
            <span class="task-group-label">${activeLabel}</span>
            <span class="task-group-count-separator" aria-hidden="true">·</span>
            <span class="task-group-count">${activeCount}</span>
          </span>
        </span>
        <span class="task-history-anchor-arrow" aria-hidden="true">
          <span class="task-group-toggle" aria-hidden="true">
            <svg class="task-group-toggle-icon" viewBox="0 0 12 12" focusable="false">
              <path d="M4 2.5 8 6 4 9.5" fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" stroke-width="1.8"/>
            </svg>
          </span>
        </span>
      </button>
      <div class="task-group-items task-group-items-expanded" data-active-task-group-items aria-hidden="${collapsed ? "true" : "false"}"${collapsed ? " inert" : ""}>
        ${body}
      </div>
    </section>
  `;
}

function expandedTaskGroupHtml(group: any) {
  const groupKey = escapeHtml(group.key);
  return `
    <section class="task-group task-group-expanded" data-task-group="${groupKey}">
      ${expandedTaskGroupHeaderHtml(group)}
      <div class="task-group-items task-group-items-expanded">
        ${group.tasks.map((task: any) => taskCardHtml(task)).join("")}
      </div>
    </section>
  `;
}

function taskGroupHtml(group: any) {
  return expandedTaskGroupHtml(group);
}

function taskGroupButtonLabel(group: any) {
  return formatTranslation("taskGroup.buttonLabel", { label: group.label, count: taskGroupCount(group) });
}

function taskQueueSection(task: any, queueIds = queueTaskIdsBySection()) {
  const taskId = String(task?.task_id || "");
  if (!taskId) return "";
  if (queueIds.running.has(taskId)) return "running";
  if (queueIds.waiting.has(taskId)) return "waiting";
  return "";
}

function waitingQueueIndex(taskId: any, queueIds = queueTaskIdsBySection()) {
  const normalizedTaskId = String(taskId || "");
  return queueIds.waiting.get(normalizedTaskId) ?? -1;
}

function taskQueueReorderHintVisible(waitingCount: number): boolean {
  if (waitingCount < 2) return false;
  try {
    return window.localStorage.getItem(TASK_QUEUE_REORDER_HINT_STORAGE_KEY) !== "1";
  } catch {
    return true;
  }
}

function taskQueueReorderHintHtml(waitingCount: number): string {
  if (!taskQueueReorderHintVisible(waitingCount)) return "";
  return `<span class="task-queue-reorder-hint">${escapeHtml(translate("queue.dragWaiting"))}</span>`;
}

function taskCardSwipeActionLabel(action: TaskCardSwipeAction): string {
  if (action === "archive") return translate("action.archive");
  if (action === "delete") return translate("action.delete");
  if (action === "stop") return translate("action.stop");
  if (action === "promote") return translate("queue.promote");
  return translate("action.cancel");
}

function taskCardSwipeActionTitle(action: TaskCardSwipeAction): string {
  if (action === "stop") return translate("queue.cancelRunningTitle");
  if (action === "promote") return translate("queue.promoteTitle");
  if (action === "cancel") return translate("batch.cancelSelected");
  return taskCardSwipeActionLabel(action);
}

function taskCardSwipeActionHtml(action: TaskCardSwipeAction | null): string {
  if (!action) return "";
  const label = escapeHtml(taskCardSwipeActionLabel(action));
  const title = escapeHtml(taskCardSwipeActionTitle(action));
  return `<button class="task-card-swipe-action task-card-swipe-${action}" type="button" data-task-card-action="${action}" aria-label="${title}" title="${title}" tabindex="-1" disabled>${label}</button>`;
}

function taskCardSwipeActionsHtml(actions: TaskCardSwipeActions) {
  if (!actions.positive && !actions.negative) return "";
  const actionGroupLabel = escapeHtml(translate("taskActions.group"));
  return `
      <div class="task-card-swipe-actions" role="group" aria-label="${actionGroupLabel}" aria-hidden="true" inert>
        ${taskCardSwipeActionHtml(actions.positive)}
        ${taskCardSwipeActionHtml(actions.negative)}
      </div>
  `;
}

function taskCardSwipeKeyboardShortcuts(actions: TaskCardSwipeActions, queueReorderable = false): string {
  const shortcuts = ["Shift+F10"];
  if (actions.negative) shortcuts.push("Delete", "Shift+ArrowLeft");
  if (actions.positive) shortcuts.push("Shift+ArrowRight");
  if (queueReorderable) shortcuts.push("Alt+ArrowUp", "Alt+ArrowDown");
  return shortcuts.join(" ");
}

function taskCardHtml(task: any) {
  const image = taskThumbHtml(task);
  const active = String(task.task_id) === String(state.selectedTaskId) ? " active" : "";
  const activeCurrent = active ? ' aria-current="true"' : "";
  const unread = taskHasUnreadUpdate(task);
  const unreadClass = unread ? " unread" : "";
  const statusClass = task.status ? ` ${escapeHtml(task.status)}` : "";
  const title = escapeHtml(task.prompt || task.mode || "Untitled");
  const taskId = escapeHtml(task.task_id);
  const showImageSummary = taskImageSummaryVisible(task);
  const imageBlocks = showImageSummary ? taskImageBlocksHtml(task) : "";
  const imageSummary = showImageSummary ? escapeHtml(taskImageSummaryText(task)) : "";
  const imageSummaryHtml = imageSummary ? `<span class="task-image-summary">${imageSummary}</span>` : "";
  const groundingCount = groundingSourceCount(task);
  const groundingHtml = groundingCount > 0
    ? `<span class="task-grounding-badge">${escapeHtml(formatTranslation("grounding.sourceCount", { count: groundingCount }))}</span>`
    : "";
  const retryFullText = taskRetryStateText(task);
  const retryText = taskCardRetryStateText(task) || retryFullText;
  const runningTimerHtml = taskCardRunningTimerHtml(task, taskId);
  const statusLabel = taskStatusLabelHtml(task);
  const modelFamilyIcon = taskModelFamilyIconHtml(task);
  const statusMetaText = retryText
    ? taskMetaDetailsWithCompletionText(task)
    : taskMetaDetailsText(task);
  const statusMeta = escapeHtml(statusMetaText);
  const taskTime = taskCardCompletionTimeText(task);
  const runtime = taskCardRuntimeText(task);
  const runtimeFullText = taskRuntimeText(task);
  const completionTitle = taskCompletionTimestampTitle(task);
  const runtimeTitleText = [runtimeFullText, completionTitle].filter(Boolean).join(" · ");
  const runtimeTitle = runtimeTitleText ? ` title="${escapeHtml(runtimeTitleText)}"` : "";
  const runtimeHtml = runtime ? `<span class="task-runtime" data-task-runtime-id="${taskId}" data-task-completed-at-id="${taskId}"${runtimeTitle}>${escapeHtml(runtime)}</span>` : "";
  const topTimeHtml = runningTimerHtml || runtimeHtml;
  const imageRow = showImageSummary ? `
          <span class="task-image-row">
            ${imageBlocks}
            <span class="task-status-row task-status-inline" aria-label="${escapeHtml(taskStatusAccessibleLabel(task))}">
              ${statusLabel}
              ${modelFamilyIcon}
            </span>
            ${imageSummaryHtml}
          </span>
    ` : "";
  const retryTitle = retryFullText && retryFullText !== retryText ? ` title="${escapeHtml(retryFullText)}"` : "";
  const retryHtml = retryText ? `<span class="task-retry-state" data-task-retry-id="${taskId}"${retryTitle}>${escapeHtml(retryText)}</span>` : "";
  const timeHtml = !retryText && taskTime ? `<span class="task-card-time">${escapeHtml(taskTime)}</span>` : "";
  const detailRightHtml = retryHtml || timeHtml;
  const detailRowClass = detailRightHtml ? "task-detail-row" : "task-detail-row task-detail-row-meta-only";
  const detailRow = statusMeta || detailRightHtml ? `
        <div class="${detailRowClass}">
          <span class="task-status-meta" data-task-meta-id="${taskId}">${statusMeta}</span>
          ${detailRightHtml}
        </div>
    ` : "";
  const batchSelected = state.batchSelectedTaskIds.includes(String(task.task_id));
  const batchClass = state.batchMode ? " batch-mode" : "";
  const batchSelectedClass = batchSelected ? " batch-selected" : "";
  const queueIds = queueTaskIdsBySection();
  const queueSection = taskQueueSection(task, queueIds);
  const queueClass = queueSection ? ` queue-${escapeHtml(queueSection)}` : "";
  const waitingIndexValue = waitingQueueIndex(task.task_id, queueIds);
  const queueReorderable = queueSection === "waiting"
    && waitingIndexValue >= 0
    && (state.queue.waiting || []).length > 1;
  const queueReorderDescription = queueReorderable
    ? escapeHtml(translate("queue.dragWaiting"))
    : "";
  const queueReorderData = queueReorderable
    ? ` data-queue-reorderable="true" aria-description="${queueReorderDescription}"`
    : "";
  const queueTaskData = queueSection === "waiting"
    ? ` data-queue-task-id="${taskId}"${queueReorderData}`
    : "";
  const swipeActions = taskCardSwipeActionsForState(
    queueSection,
    String(task.status || ""),
    Boolean(task.local_pending),
  );
  const swipeEnabled = Boolean(swipeActions.positive || swipeActions.negative);
  const swipeActionsHtml = taskCardSwipeActionsHtml(swipeActions);
  const swipeKeyboardShortcuts = escapeHtml(taskCardSwipeKeyboardShortcuts(swipeActions, queueReorderable));
  const batchSelect = state.batchMode ? `
      <button class="task-select-button" type="button" role="checkbox" data-batch-select-task-id="${taskId}" aria-checked="${batchSelected ? "true" : "false"}" aria-label="${escapeHtml(translate("taskList.selectSession"))}">
        <span></span>
      </button>
    ` : "";
  const unreadDot = unread ? `<span class="task-unread-dot" aria-label="${escapeHtml(translate("taskList.unreadUpdate"))}"></span>` : "";
  const activeLabel = escapeHtml(translate("taskList.viewing"));
  return `
    <div class="task-card${active}${unreadClass}${statusClass}${batchClass}${batchSelectedClass}${queueClass}" role="button" tabindex="0" data-task-id="${taskId}" data-task-unread="${unread ? "true" : "false"}" data-task-swipe-enabled="${swipeEnabled ? "true" : "false"}" data-task-swipe-positive-action="${escapeHtml(swipeActions.positive || "")}" data-task-swipe-negative-action="${escapeHtml(swipeActions.negative || "")}" data-active-label="${activeLabel}" aria-keyshortcuts="${swipeKeyboardShortcuts}"${activeCurrent}${queueTaskData}>
      ${swipeActionsHtml}
      <div class="task-card-swipe-surface">
        ${batchSelect}
        ${image}
        <div class="task-info">
          <div class="task-meta-row">
            ${imageRow}
            ${topTimeHtml}
          </div>
          <div class="task-title-row">
            ${unreadDot}
            <div class="task-title">${title}</div>
          </div>
          ${detailRow}
          ${groundingHtml}
        </div>
      </div>
    </div>
  `;
}

function taskHasUnreadUpdate(task: any) {
  if (!task || task.local_pending) return false;
  if (String(task.task_id) === String(state.selectedTaskId)) return false;
  if (!task.viewed_at) return false;
  if (!taskHasViewableUpdate(task)) return false;
  const viewedAt = timestampMs(task.viewed_at);
  const updatedAt = timestampMs(task.updated_at || task.completed_at || task.started_at || task.created_at);
  return viewedAt !== null && updatedAt !== null && updatedAt > viewedAt;
}

function taskHasViewableUpdate(task: any) {
  const status = String(task?.status || "");
  return ["completed", "failed", "partial_failed"].includes(status) || taskOutputUrls(task).length > 0;
}

function taskHistoryGroups(tasks: any, query: any) {
  if (query) {
    return [{
      key: "search",
      label: translate("taskGroup.searchResults"),
      tasks,
      collapsible: false,
      defaultCollapsed: false,
    }];
  }

  const groups: any[] = [];
  const assignedTaskIds = new Set();
  const addGroup = (key: any, label: any, groupTasks: any, options: any = {}) => {
    const count = Math.max(groupTasks.length, Number(options.count || 0));
    if (!count) return;
    groups.push({
      key,
      label,
      tasks: groupTasks,
      count,
      collapsible: Boolean(options.collapsible),
      defaultCollapsed: Boolean(options.defaultCollapsed),
    });
    groupTasks.forEach((task: any) => assignedTaskIds.add(String(task.task_id)));
  };
  const filters = taskFilterValues();
  const useServerCounts = Object.values(filters).every((value) => !String(value || ""));
  const serverCount = (key: string) => useServerCounts
    ? Math.max(0, Number(state.taskSidebarGroupCounts?.[key] || 0))
    : 0;
  const historicalTasks = tasks
    .filter((task: any) => !isAlwaysVisibleTask(task))
    .slice()
    .sort((left: any, right: any) => (
      taskHistoryActivityTimestamp(right) - taskHistoryActivityTimestamp(left)
      || String(right?.task_id || "").localeCompare(String(left?.task_id || ""))
    ));
  const unassignedTasks = () => historicalTasks.filter((task: any) => !assignedTaskIds.has(String(task.task_id)));

  const reveal = state.historyTaskReveal;
  const transientTaskId = reveal?.ready
    && reveal?.kind === "transient"
    && String(reveal?.taskId || "") === String(state.selectedTaskId || "")
      ? String(reveal.taskId)
      : "";
  if (transientTaskId) {
    addGroup(
      "current",
      translate("taskGroup.current"),
      unassignedTasks().filter((task: any) => String(task?.task_id || "") === transientTaskId),
      { collapsible: true, defaultCollapsed: false },
    );
  }

  addGroup(
    "today",
    translate("taskGroup.today"),
    unassignedTasks().filter((task: any) => taskDateBucket(task) === "today"),
    { collapsible: true, defaultCollapsed: false, count: serverCount("today") },
  );

  [
    ["yesterday", translate("taskGroup.yesterday")],
    ["last7", translate("taskGroup.last7")],
  ].forEach(([key, label]: any) => {
    addGroup(
      key,
      label,
      unassignedTasks().filter((task: any) => taskDateBucket(task) === key),
      { collapsible: true, defaultCollapsed: true, count: serverCount(String(key)) },
    );
  });

  return groups;
}

function historyLibraryGroup(tasks: any[], query: string) {
  if (query) return "";
  if (!tasks.some((task: any) => !isAlwaysVisibleTask(task))) return "";
  return `
    <a class="task-history-library-card" href="/history">
      <span>${escapeHtml(translate("footer.historyLibrary"))}</span>
      <small>${escapeHtml(translate("historyLibrary.openFull"))}</small>
    </a>
  `;
}

function isAlwaysVisibleTask(task: any) {
  const status = String(task?.status || "");
  return Boolean(task?.local_pending || ["submitting", "queued", "running"].includes(status));
}

function queueTaskIdsBySection() {
  const runningIds = (state.queue.running || []).map((task: any) => String(task.task_id || ""));
  const waitingIds = (state.queue.waiting || []).map((task: any) => String(task.task_id || ""));
  const cacheKey = `${runningIds.join("|")}::${waitingIds.join("|")}`;
  if (queueTaskIdsCache && queueTaskIdsCacheKey === cacheKey) return queueTaskIdsCache;
  queueTaskIdsCacheKey = cacheKey;
  queueTaskIdsCache = {
    running: new Map((state.queue.running || []).map((task: any, index: number) => [String(task.task_id), index])),
    waiting: new Map((state.queue.waiting || []).map((task: any, index: number) => [String(task.task_id), index])),
  };
  return queueTaskIdsCache;
}

function activeTaskOrderIndex(task: any, sectionIds = queueTaskIdsBySection()) {
  const taskId = String(task?.task_id || "");
  if (sectionIds.running.has(taskId)) return sectionIds.running.get(taskId) || 0;
  if (String(task?.status || "") === "running") return 1000;
  if (sectionIds.waiting.has(taskId)) return 2000 + (sectionIds.waiting.get(taskId) || 0);
  if (task?.local_pending || String(task?.status || "") === "submitting") return 3000;
  if (String(task?.status || "") === "queued") return 4000;
  return 5000;
}

function activeTasksForGroup(tasks: any[]) {
  const sectionIds = queueTaskIdsBySection();
  return tasks
    .filter((task: any) => isAlwaysVisibleTask(task))
    .slice()
    .sort((left: any, right: any) => activeTaskOrderIndex(left, sectionIds) - activeTaskOrderIndex(right, sectionIds));
}

function taskHistoryActivityTimestamp(task: any) {
  const timestamp = timestampMs(task?.terminal_at || task?.completed_at || task?.created_at);
  return timestamp === null ? Number.NEGATIVE_INFINITY : timestamp;
}

function taskDateBucket(task: any) {
  return sidebarTaskDateBucket(task);
}

function taskGroupCount(group: any) {
  const loadedCount = Array.isArray(group?.tasks) ? group.tasks.length : 0;
  return Math.max(loadedCount, Math.max(0, Number(group?.count || 0)));
}

function taskGroupLoadMoreHtml(group: any) {
  const renderedCount = Array.isArray(group?.tasks) ? group.tasks.length : 0;
  const loadedCount = Math.max(
    renderedCount,
    Math.max(0, Number(state.taskSidebarGroupLoadedCounts?.[String(group?.key || "")] || 0)),
  );
  const totalCount = Math.max(0, Number(group?.count || 0));
  if (!group?.key || loadedCount >= totalCount) return "";
  const loading = String(state.taskSidebarGroupLoading || "") === String(group.key);
  const failed = String(state.taskSidebarGroupLoadError || "") === String(group.key);
  const groupKey = escapeHtml(group.key);
  if (loading) {
    return `
      <div
        class="task-group-load-more task-group-load-more-sentinel"
        data-auto-load-task-group="${groupKey}"
        data-load-more-task-group="${groupKey}"
        aria-busy="true"
        aria-hidden="true"
        hidden
      ></div>
    `;
  }
  if (failed) {
    return `
      <button
        class="ghost-button text-sm task-group-load-more task-group-load-more-error"
        type="button"
        data-load-more-task-group="${groupKey}"
      >${escapeHtml(translate("taskGroup.loadFailedRetry"))}</button>
    `;
  }
  return `
    <div
      class="task-group-load-more task-group-load-more-sentinel"
      data-auto-load-task-group="${groupKey}"
      data-load-more-task-group="${groupKey}"
      aria-hidden="true"
      hidden
    ></div>
  `;
}

function taskListRenderKey(tasks: any, query: any, layout: any = {}, filters: any = {}, activeGroup: any = null) {
  return JSON.stringify({
    query,
    filters,
    activeQueue: activeQueueTaskListRenderKey(),
    activeGroup: activeGroup
      ? [activeGroup.key, activeGroup.label, activeGroup.tasks.length]
      : null,
    activeTaskGroupCollapsed: Boolean(state.activeTaskGroupCollapsed),
    batchMode: state.batchMode,
    batchSelectedTaskIds: state.batchSelectedTaskIds.map(String).sort(),
    archivedTaskIds: state.tasks.filter(taskArchived).map((task: any) => String(task.task_id)).sort(),
    expandedTaskGroupKey: state.expandedTaskGroupKey,
    historyTaskReveal: state.historyTaskReveal?.ready
      ? [state.historyTaskReveal.kind, state.historyTaskReveal.groupKey, state.historyTaskReveal.taskId]
      : null,
    queryMode: Boolean(layout.queryMode),
    expandedGroup: layout.expandedGroup
      ? [layout.expandedGroup.key, layout.expandedGroup.label, taskGroupCount(layout.expandedGroup)]
      : null,
    anchorGroups: [
      (layout.top || []).map((group: any) => [group.key, taskGroupCount(group)]),
      (layout.bottom || []).map((group: any) => [group.key, taskGroupCount(group)]),
    ],
    tasks: tasks.map((task: any) => [
      task.task_id,
      task.status,
      task.updated_at,
      task.completed_at,
      task.terminal_at,
      task.started_at,
      task.prompt,
      task.mode,
      task.backend,
      task.requested_backend,
      task.api_provider_id,
      task.api_provider_name,
      task.params?.api_provider_id,
      task.params?.api_provider_name,
      task.request?.webui_api_provider_id,
      task.request?.webui_api_provider_name,
      task.params?.size,
      task.output_url,
      Array.isArray(task.output_urls) ? task.output_urls.join("|") : "",
      Array.isArray(task.input_thumbnail_urls) ? task.input_thumbnail_urls.join("|") : "",
      Array.isArray(task.thumbnail_urls) ? task.thumbnail_urls.join("|") : "",
      task.preview_url,
      task.last_error || task.error || "",
      task.attempts,
      task.max_attempts,
      Array.isArray(task.retrying_failed_slots) ? task.retrying_failed_slots.join(",") : "",
      task.generated_count,
      task.failed_count,
      task.total_count,
      Array.isArray(task.input_sources)
        ? task.input_sources.map((item: any) => [item?.kind, item?.image_url, item?.thumbnail_url].join(":")).join("|")
        : "",
      Array.isArray(task.outputs)
        ? task.outputs.map((item: any) => [item?.index, item?.status, item?.url, item?.thumbnail_url, item?.error].join(":")).join("|")
        : "",
      groundingAttributionKey(task),
    ]),
  });
}

function activeQueueTaskListRenderKey() {
  return {
    running: (state.queue.running || []).map((task: any) => String(task.task_id || "")),
    waiting: (state.queue.waiting || []).map((task: any) => String(task.task_id || "")),
  };
}

function taskThumbShowsLoading(task: any) {
  const status = String(task?.status || "");
  return Boolean(task?.local_pending || ["submitting", "queued", "running"].includes(status));
}

function taskThumbSpinnerStyle(task: any) {
  const origin = timestampMs(task?.created_at);
  if (origin === null) return "";
  const elapsed = Math.max(0, Date.now() - origin);
  const outerDelay = -(elapsed % TASK_THUMB_OUTER_SPIN_DURATION_MS);
  const innerDelay = -((elapsed + TASK_THUMB_INNER_SPIN_OFFSET_MS) % TASK_THUMB_INNER_SPIN_DURATION_MS);
  return ` style="--task-spinner-outer-delay: ${outerDelay}ms; --task-spinner-inner-delay: ${innerDelay}ms"`;
}

function taskThumbHtml(task: any, className: any = "task-thumb") {
  const outputUrl = taskOutputUrls(task)[0];
  const outputThumbnailUrl = taskThumbnailUrls(task)[0];
  const inputPreviewUrl = taskInputPreviewUrls(task)[0];
  const loading = taskThumbShowsLoading(task);
  const outputImageUrl = outputThumbnailUrl || outputUrl || (!loading ? task.preview_url : "");
  const imageUrl = outputImageUrl || inputPreviewUrl || task.preview_url;
  const safeClassName = escapeHtml(className);
  const loadingSpinner = loading
    ? `<span class="task-thumb-stack-spinner" aria-hidden="true"${taskThumbSpinnerStyle(task)}></span>`
    : "";
  if (outputImageUrl && inputPreviewUrl && outputImageUrl !== inputPreviewUrl) {
    const imageToImageLabel = escapeHtml(translate("taskCard.imageToImageThumb"));
    return `
      <div class="${safeClassName} task-thumb-stack" aria-label="${imageToImageLabel}">
        <img class="task-thumb-output" src="${escapeHtml(outputImageUrl)}" alt="" loading="lazy" decoding="async" draggable="false">
        <span class="task-thumb-reference-badge" aria-hidden="true">
          <img class="task-thumb-reference" src="${escapeHtml(inputPreviewUrl)}" alt="" loading="lazy" decoding="async" draggable="false">
        </span>
        ${loadingSpinner}
      </div>
    `;
  }
  if (inputPreviewUrl && loading) {
    const imageToImageLabel = escapeHtml(translate("taskCard.imageToImageThumb"));
    return `
      <div class="${safeClassName} task-thumb-single task-thumb-loading-reference" aria-label="${imageToImageLabel}">
        <img class="task-thumb-single-image" src="${escapeHtml(inputPreviewUrl)}" alt="" loading="lazy" decoding="async" draggable="false">
        ${loadingSpinner}
      </div>
    `;
  }
  if (imageUrl) {
    const thumbnailLabel = escapeHtml(translate(inputPreviewUrl
      ? "taskCard.imageToImageThumb"
      : "taskCard.textToImageThumb"));
    return `
      <div class="${safeClassName} task-thumb-single" aria-label="${thumbnailLabel}">
        <img class="task-thumb-single-image" src="${escapeHtml(imageUrl)}" alt="" loading="lazy" decoding="async" draggable="false">
      </div>
    `;
  }
  if (taskWasCancelled(task)) {
    return `<div class="${safeClassName} failed-thumb task-cancelled-thumb" aria-label="${escapeHtml(translate("queue.runningCancelled"))}"><span>×</span></div>`;
  }
  if (task.status === "failed") {
    return `<div class="${safeClassName} failed-thumb" aria-label="${escapeHtml(translate("taskCard.failedThumb"))}"><span>!</span></div>`;
  }
  return `<div class="${safeClassName} running-thumb"><span${taskThumbSpinnerStyle(task)}></span></div>`;
}

function taskStatusLabelHtml(task: any) {
  const label = escapeHtml(formatTaskCardStatus(task) || translate("taskStatus.unknown"));
  const taskId = escapeHtml(task?.task_id || "");
  return `<span class="task-status-label" data-task-status-id="${taskId}">${label}</span>`;
}

function taskModelFamilyIconHtml(task: any) {
  const familyId = taskModelFamilyId(task, state.generationCatalog);
  const modelName = taskModelDisplayName(task, state.generationCatalog);
  return `<span class="task-model-family-icon task-model-family-icon-${familyId}" title="${escapeHtml(modelName)}">${modelFamilyBrandMarkHtml(familyId, "task-model-family-brand-mark")}</span>`;
}

function taskStatusAccessibleLabel(task: any) {
  return [
    formatTaskCardStatus(task) || translate("taskStatus.unknown"),
    taskModelDisplayName(task, state.generationCatalog),
    taskImageSummaryText(task),
    taskMetaDetailsText(task),
  ]
    .filter(Boolean)
    .join(" · ");
}

function taskMetaDetailsText(task: any) {
  const backend = taskCardProviderLabel(task);
  return [...taskCanvasSummaryParts(task), backend].filter(Boolean).join(" · ");
}

function taskMetaDetailsWithCompletionText(task: any) {
  const statusMeta = taskMetaDetailsText(task);
  const completion = taskCompletionTimestampText(task);
  return [statusMeta, completion?.shortText].filter(Boolean).join(" · ");
}

function taskCardCompletionTimeText(task: any) {
  const completion = taskCompletionTimestampText(task);
  return completion?.shortText || "";
}

function taskCardElapsedLineHtml(key: string, values: Record<string, any>, elapsedHtml: string) {
  const marker = "__TASK_CARD_ELAPSED_TIMER__";
  return formatTranslation(key, { ...values, elapsed: marker })
    .split(marker)
    .map((part: string) => escapeHtml(part))
    .join(elapsedHtml);
}

function taskCardRunningTimerHtml(task: any, taskId: string) {
  if (!["running", "cancelling"].includes(String(task?.status || ""))) return "";
  const startedAt = taskProgressStartValue(task);
  if (!startedAt) return "";
  const elapsed = elapsedTimerSpan("task-card-running", startedAt);
  return `<span class="task-card-time task-card-running-timer" data-task-running-timer-id="${taskId}">${taskCardElapsedLineHtml("preview.elapsedLine", {}, elapsed)}</span>`;
}

function taskCardProviderLabel(task: any) {
  const providerLabel = String(taskApiProviderLabel(task) || "").trim();
  const providerId = String(taskApiProviderId(task) || "").trim();
  const backend = String(task?.backend || task?.requested_backend || "").trim();
  const channel = taskChannelLabel(task);
  if (providerLabel && (!providerId || providerLabel !== providerId)) {
    const providerIdSuffix = providerId ? `(${providerId})` : "";
    const label = providerIdSuffix && providerLabel.endsWith(providerIdSuffix)
      ? providerLabel.slice(0, -providerIdSuffix.length).trim()
      : providerLabel;
    return [label, channel].filter(Boolean).join(" · ");
  }
  if (backend === "codex_images") return "Codex Image";
  if (backend === "codex_responses") return "Codex Responses";
  if (backend === "openai_images") return "API Image";
  if (backend === "openai_responses") return "API Responses";
  return "";
}

function taskCardRuntimeText(task: any) {
  return taskDurationText(task);
}

function taskImageBlocksHtml(task: any) {
  const states = taskImageBlockStates(task);
  const visibleStates = compressTaskImageBlockStates(states);
  const total = states.length;
  const visibleCount = Math.min(total, 4);
  const compressedClass = states.length > visibleStates.length ? " compressed" : "";
  const blocks = visibleStates.map((blockState: any) => `<span class="task-image-block ${blockState}" aria-hidden="true"></span>`).join("");
  return `<div class="task-image-progress${compressedClass}" style="--task-block-count: ${visibleCount}" aria-hidden="true">${blocks}</div>`;
}

function taskImageSummaryText(task: any) {
  const states = taskImageBlockStates(task);
  const counts = taskImageStatusCounts(states);
  const parts = [];
  if (counts.running) parts.push(formatTranslation("taskCard.count", { count: counts.running }));
  if (counts.queued || counts.waiting) {
    const waitingCount = counts.queued + counts.waiting;
    parts.push(formatTranslation(counts.running ? "taskCard.waitingCount" : "taskCard.count", { count: waitingCount }));
  }
  return parts.join(" · ");
}

function taskImageSummaryVisible(task: any) {
  void task;
  return true;
}

function taskMetaText(task: any) {
  const status = formatTaskStatus(task);
  const backend = taskCardProviderLabel(task);
  return [status, ...taskCanvasSummaryParts(task), backend].filter(Boolean).join(" · ");
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

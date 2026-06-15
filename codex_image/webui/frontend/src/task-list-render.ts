import { getLegacyBridge } from "./state";
import { cssEscape, prefersReducedMotion } from "./webui-utils";
import { formatTranslation, LOCALE_CHANGE_EVENT, translate } from "./i18n";

const bridge = getLegacyBridge();
const state = bridge.state;
const els = bridge.els;
const EXPANDED_TASK_GROUP_INITIAL_CARD_COUNT = 24;
const EXPANDED_TASK_GROUP_CHUNK_SIZE = 48;
const EXPANDED_TASK_GROUP_ANIMATION_FALLBACK_MS = 320;
let expandedTaskGroupRenderToken = 0;
type QueueTaskIdSections = { running: Map<string, number>; waiting: Map<string, number> };
type TaskListScrollAnchor = {
  scroller: HTMLElement;
  scrollTop: number;
  taskId?: string;
  offsetTop?: number;
};
let queueTaskIdsCacheKey = "";
let queueTaskIdsCache: QueueTaskIdSections | null = null;

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
function formatTaskStatus(...args: any[]) { return legacyMethod("formatTaskStatus", ...args); }
function ensureExpandedTaskGroupKey(...args: any[]) { return legacyMethod("ensureExpandedTaskGroupKey", ...args); }
function renderTaskHistoryAnchors(...args: any[]) { return legacyMethod("renderTaskHistoryAnchors", ...args); }
function setExpandedTaskGroupKey(...args: any[]) { return legacyMethod("setExpandedTaskGroupKey", ...args); }
function scrollExpandedTaskGroupToTop(...args: any[]) { return legacyMethod("scrollExpandedTaskGroupToTop", ...args); }
function captureTaskHistoryLayout(...args: any[]) { return legacyMethod("captureTaskHistoryLayout", ...args); }
function animateTaskHistoryLayout(...args: any[]) { return legacyMethod("animateTaskHistoryLayout", ...args); }
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
const taskFailureMessage = (...args: any[]) => legacyMethod("taskFailureMessage", ...args);
const taskRetryStateText = (...args: any[]) => legacyMethod("taskRetryStateText", ...args);
const taskRuntimeText = (...args: any[]) => legacyMethod("taskRuntimeText", ...args);
const taskCompletionTimestampTitle = (...args: any[]) => legacyMethod("taskCompletionTimestampTitle", ...args);
const timestampMs = (...args: any[]) => legacyMethod("timestampMs", ...args);

function renderTasks(options: { preserveScroll?: boolean } = {}) {
  const scrollAnchor = options.preserveScroll ? captureTaskListScrollAnchor() : null;
  const query = taskSearchQuery();
  const filters = taskFilterValues();
  const visibleTasks = state.tasks.filter((task: any) => !isTaskArchived(task.task_id));
  const tasks = visibleTasks.filter((task: any) => {
    return taskMatchesSearch(task, query) && taskMatchesFilters(task, filters);
  });
  const visibleTaskIds = visibleTasks.map((task: any) => String(task.task_id));
  state.batchSelectedTaskIds = state.batchSelectedTaskIds.filter((taskId: any) => visibleTaskIds.includes(String(taskId)));
  renderBatchToolbar();
  const activeGroup = activeTaskGroup(tasks, query);
  const groups = taskHistoryGroups(tasks, query);
  const expandedGroup = ensureExpandedTaskGroupKey(groups);
  const layout = taskAnchorLayout(groups, expandedGroup?.key || null, query);
  const nextRenderKey = taskListRenderKey(tasks, query, layout, filters, activeGroup);
  if (state.tasksRenderKey === nextRenderKey) {
    updateTaskElapsedDisplays();
    restoreTaskListScrollAnchor(scrollAnchor);
    return;
  }
  state.tasksRenderKey = nextRenderKey;
  renderTaskHistoryAnchors(layout);
  renderHistoryLibraryGroup(tasks, query);
  const activeHtml = activeGroup ? activeTaskGroupHtml(activeGroup) : "";
  renderActiveTaskGroup(activeHtml);

  if (!tasks.length) {
    expandedTaskGroupRenderToken += 1;
    els.taskList.innerHTML = `<div class="task-meta">${escapeHtml(translate("taskList.empty"))}</div>`;
    updateDocumentTitle();
    restoreTaskListScrollAnchor(scrollAnchor);
    return;
  }
  if (!layout.expandedGroup) {
    expandedTaskGroupRenderToken += 1;
    els.taskList.innerHTML = "";
    updateDocumentTitle();
    restoreTaskListScrollAnchor(scrollAnchor);
    return;
  }

  const group = layout.expandedGroup;
  els.taskList.innerHTML = renderExpandedTaskGroupShellHtml(group);
  scheduleExpandedTaskGroupItemsRender(group, layout.expandedKey || group?.key || null);
  updateDocumentTitle();
  restoreTaskListScrollAnchor(scrollAnchor);
}

function taskListScrollContainer(): HTMLElement | null {
  return els.sidebarContent || els.taskHistoryShell || els.taskList || null;
}

function captureTaskListScrollAnchor(): TaskListScrollAnchor | null {
  const scroller = taskListScrollContainer();
  const root = taskCardRoot();
  if (!scroller || !root) return null;
  const scrollerRect = scroller.getBoundingClientRect();
  const cards = Array.from(root.querySelectorAll(".task-card[data-task-id]")) as HTMLElement[];
  const visibleCard = cards.find((card) => {
    const rect = card.getBoundingClientRect();
    return rect.bottom > scrollerRect.top && rect.top < scrollerRect.bottom;
  });
  if (!visibleCard) return { scroller, scrollTop: scroller.scrollTop };
  const rect = visibleCard.getBoundingClientRect();
  const anchor: TaskListScrollAnchor = {
    scroller,
    scrollTop: scroller.scrollTop,
    offsetTop: rect.top - scrollerRect.top,
  };
  if (visibleCard.dataset.taskId) anchor.taskId = visibleCard.dataset.taskId;
  return anchor;
}

function restoreTaskListScrollAnchor(anchor: TaskListScrollAnchor | null): void {
  if (!anchor?.scroller) return;
  let attempts = 12;
  const restore = () => {
    if (!anchor.scroller.isConnected) return;
    if (anchor.taskId) {
      const card = taskCardElement(anchor.taskId);
      if (card instanceof HTMLElement) {
        const scrollerRect = anchor.scroller.getBoundingClientRect();
        const rect = card.getBoundingClientRect();
        anchor.scroller.scrollTop += rect.top - scrollerRect.top - (anchor.offsetTop || 0);
        return;
      }
    }
    if (anchor.taskId && attempts > 0) {
      attempts -= 1;
      requestAnimationFrame(restore);
      return;
    }
    anchor.scroller.scrollTop = anchor.scrollTop;
  };
  requestAnimationFrame(restore);
}

function renderHistoryLibraryGroup(tasks: any[], query: string) {
  if (!els.taskHistoryLibrarySlot) return;
  const html = historyLibraryGroup(tasks, query);
  els.taskHistoryLibrarySlot.innerHTML = html;
  els.taskHistoryLibrarySlot.classList.toggle("hidden", !html);
}

function renderActiveTaskGroup(activeHtml: string) {
  if (!els.taskActiveList) return;
  els.taskActiveList.innerHTML = activeHtml;
  els.taskActiveList.classList.toggle("hidden", !activeHtml);
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
  const headerButton = els.taskList?.querySelector(
    `.task-group[data-task-group="${escapedGroupKey}"] .task-group-header-split`,
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

function scheduleExpandedTaskGroupItemsRender(group: any, activeGroupKey: string | null = null) {
  const tasks = Array.isArray(group?.tasks) ? group.tasks : [];
  const groupKey = String(group?.key || "");
  if (!groupKey) return;
  const normalizedActiveGroupKey = String(activeGroupKey || groupKey);
  const shouldAnimateExpand = state.expandedTaskGroupAnimationPending === true;
  state.expandedTaskGroupAnimationPending = false;
  const token = ++expandedTaskGroupRenderToken;
  let index = 0;
  const renderChunk = () => {
    if (token !== expandedTaskGroupRenderToken) return;
    if (normalizedActiveGroupKey !== groupKey) return;
    const body = expandedTaskGroupItemsContainer(groupKey);
    if (!body) return;
    const chunkSize = index === 0 ? EXPANDED_TASK_GROUP_INITIAL_CARD_COUNT : EXPANDED_TASK_GROUP_CHUNK_SIZE;
    const nextTasks = tasks.slice(index, index + chunkSize);
    if (!nextTasks.length) {
      finalizeExpandedTaskGroupBody(groupKey);
      body.dataset.renderComplete = "true";
      return;
    }
    body.insertAdjacentHTML("beforeend", nextTasks.map((task: any) => taskCardHtml(task)).join(""));
    index += nextTasks.length;
    if (index === nextTasks.length) {
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
      body.dataset.renderComplete = "true";
    }
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
  return els.taskSearch.value.trim().toLowerCase();
}

function taskFilterValues() {
  return {
    ratio: els.taskRatioFilter?.value || "",
    orientation: els.taskOrientationFilter?.value || "",
    promptFidelity: els.taskPromptFidelityFilter?.value || "",
    resolution: els.taskResolutionFilter?.value || "",
  };
}

function taskMatchesSearch(task: any, query: any) {
  const text = `${task.task_id || ""} ${task.prompt || ""} ${task.status || ""} ${task.mode || ""} ${taskBackendLabel(task)}`.toLowerCase();
  return text.includes(query);
}

function taskMatchesFilters(task: any, filters: any) {
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
  [els.taskRatioFilter, els.taskOrientationFilter, els.taskPromptFidelityFilter, els.taskResolutionFilter]
    .filter(Boolean)
    .forEach((element: any) => {
      if (element.value) {
        element.value = "";
        changed = true;
      }
    });
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

function renderExpandedTaskGroupShellHtml(group: any) {
  const groupKey = escapeHtml(group.key);
  return `
    <section class="task-group task-group-expanded" data-task-group="${groupKey}">
      <button
        class="task-group-header task-group-header-split"
        type="button"
        data-task-group-toggle-key="${groupKey}"
        data-task-group-expanded="true"
        aria-expanded="false"
        aria-label="${escapeHtml(formatTranslation("taskGroup.collapse", { label: group.label }))}"
      >
        <span class="task-group-label-button">
          <span class="task-group-title">
            <span class="task-group-label">${escapeHtml(group.label)}</span>
            <span class="task-group-count-separator" aria-hidden="true"> · </span>
            <span class="task-group-count">${group.tasks.length}</span>
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
    if (queueIds.running.has(taskId) || status === "running") {
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
  return `
    <div ${sectionClass} ${sectionData}>
      <div class="task-active-section-title">
        <span>${escapeHtml(label)}</span>
        <span class="task-active-section-count">${tasks.length}</span>
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
    label: translate("taskGroup.active"),
    tasks: activeTasks,
    collapsible: false,
    defaultCollapsed: false,
  };
}

function activeTaskGroupHtml(group: any) {
  const groupKey = escapeHtml(group.key);
  const sections = activeTaskSections(group.tasks || []);
  const dispatchPending = Boolean(legacyMethod("isQueueDispatchPending"));
  const body = [
    activeTaskSectionHtml("running", translate("taskGroup.running"), sections.running),
    activeTaskSectionHtml("waiting", translate("taskGroup.waiting"), sections.waiting),
    !sections.running.length && !sections.waiting.length && dispatchPending ? activeTaskDispatchPendingHtml() : "",
  ].join("");
  return `
    <section class="task-group task-group-expanded task-group-active" data-task-group="${groupKey}">
      <div
        class="task-group-header task-group-header-split task-active-group-header"
        role="heading"
        aria-level="2"
      >
        <span class="task-group-label-button">
          <span class="task-group-title">
            <span class="task-group-label">${escapeHtml(group.label)}</span>
            <span class="task-group-count-separator" aria-hidden="true"> · </span>
            <span class="task-group-count">${group.tasks.length}</span>
          </span>
        </span>
      </div>
      <div class="task-group-items task-group-items-expanded">
        ${body}
      </div>
    </section>
  `;
}

function expandedTaskGroupHtml(group: any) {
  const groupKey = escapeHtml(group.key);
  return `
    <section class="task-group task-group-expanded" data-task-group="${groupKey}">
      <button
        class="task-group-header task-group-header-split"
        type="button"
        data-task-group-toggle-key="${groupKey}"
        data-task-group-expanded="true"
        aria-expanded="true"
        aria-label="${escapeHtml(formatTranslation("taskGroup.collapse", { label: group.label }))}"
      >
        <span class="task-group-label-button">
          <span class="task-group-title">
            <span class="task-group-label">${escapeHtml(group.label)}</span>
            <span class="task-group-count-separator" aria-hidden="true"> · </span>
            <span class="task-group-count">${group.tasks.length}</span>
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
  return formatTranslation("taskGroup.buttonLabel", { label: group.label, count: group.tasks.length });
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

function taskQueueActionIconHtml(icon: "cancel" | "up" | "down" | "top" | "delete") {
  if (icon === "cancel") {
    return `<svg class="task-queue-action-icon" viewBox="0 0 16 16" aria-hidden="true" focusable="false">
        <path d="M5.25 5.25h5.5v5.5h-5.5z" />
      </svg>`;
  }
  if (icon === "up") {
    return `<svg class="task-queue-action-icon" viewBox="0 0 16 16" aria-hidden="true" focusable="false">
        <path d="M8 12V4.5" />
        <path d="M4.75 7.75 8 4.5l3.25 3.25" />
      </svg>`;
  }
  if (icon === "down") {
    return `<svg class="task-queue-action-icon" viewBox="0 0 16 16" aria-hidden="true" focusable="false">
        <path d="M8 4v7.5" />
        <path d="M4.75 8.25 8 11.5l3.25-3.25" />
      </svg>`;
  }
  if (icon === "top") {
    return `<svg class="task-queue-action-icon" viewBox="0 0 16 16" aria-hidden="true" focusable="false">
        <path d="M4.5 3.5h7" />
        <path d="M8 12.5V6" />
        <path d="M5.25 8.75 8 6l2.75 2.75" />
      </svg>`;
  }
  return `<svg class="task-queue-action-icon" viewBox="0 0 16 16" aria-hidden="true" focusable="false">
      <path d="M5.25 6.25v5.5" />
      <path d="M8 6.25v5.5" />
      <path d="M10.75 6.25v5.5" />
      <path d="M4.25 4.25h7.5" />
      <path d="M6.25 4.25l.5-1h2.5l.5 1" />
      <path d="M5 4.25h6l-.45 9H5.45z" />
    </svg>`;
}

function taskQueueActionStripHtml(task: any, queueSection = taskQueueSection(task), waitingIndex = waitingQueueIndex(task?.task_id)) {
  if (!queueSection) return "";
  const taskId = escapeHtml(task.task_id);
  if (queueSection === "running") {
    const runningActionsLabel = escapeHtml(translate("queue.runningActions"));
    const cancelTitle = escapeHtml(translate("queue.cancelRunningTitle"));
    return `
      <div class="task-queue-actions task-queue-actions-running" role="group" aria-label="${runningActionsLabel}" data-task-queue-section="${escapeHtml(queueSection)}">
        <button class="task-queue-action task-queue-cancel-button" type="button" data-task-queue-cancel-id="${taskId}" aria-label="${cancelTitle}" title="${cancelTitle}">${taskQueueActionIconHtml("cancel")}</button>
      </div>
    `;
  }
  const waitingCount = (state.queue.waiting || []).length;
  const disableMoveUp = waitingIndex <= 0;
  const disableMoveDown = waitingIndex < 0 || waitingIndex >= waitingCount - 1;
  const waitingActionsLabel = escapeHtml(translate("queue.waitingActions"));
  const dragWaitingLabel = escapeHtml(translate("queue.dragWaiting"));
  const dragSortLabel = escapeHtml(translate("queue.dragSort"));
  const moveUpTitle = escapeHtml(translate("queue.moveUpTitle"));
  const moveDownTitle = escapeHtml(translate("queue.moveDownTitle"));
  const promoteTitle = escapeHtml(translate("queue.promoteTitle"));
  const deleteTitle = escapeHtml(translate("queue.deleteWaitingTitle"));
  return `
    <div class="task-queue-actions task-queue-actions-waiting" role="group" aria-label="${waitingActionsLabel}" data-task-queue-section="${escapeHtml(queueSection)}">
      <button class="task-queue-drag-handle" type="button" draggable="true" data-task-queue-drag-handle-id="${taskId}" aria-label="${dragWaitingLabel}" title="${dragSortLabel}">
        <svg class="task-queue-drag-icon" viewBox="0 0 16 16" aria-hidden="true" focusable="false">
          <path d="M5 3.5h.1M5 8h.1M5 12.5h.1M10.5 3.5h.1M10.5 8h.1M10.5 12.5h.1" />
        </svg>
      </button>
      <button class="task-queue-action" type="button" data-task-queue-move-id="${taskId}" data-task-queue-direction="up" aria-label="${moveUpTitle}" title="${moveUpTitle}"${disableMoveUp ? " disabled" : ""}>${taskQueueActionIconHtml("up")}</button>
      <button class="task-queue-action" type="button" data-task-queue-move-id="${taskId}" data-task-queue-direction="down" aria-label="${moveDownTitle}" title="${moveDownTitle}"${disableMoveDown ? " disabled" : ""}>${taskQueueActionIconHtml("down")}</button>
      <button class="task-queue-action" type="button" data-task-queue-promote-id="${taskId}" aria-label="${promoteTitle}" title="${promoteTitle}">${taskQueueActionIconHtml("top")}</button>
      <button class="task-queue-action task-queue-delete-button" type="button" data-task-queue-delete-id="${taskId}" aria-label="${deleteTitle}" title="${deleteTitle}">${taskQueueActionIconHtml("delete")}</button>
    </div>
  `;
}

function taskCardActionsHtml(taskId: string, queueSection = "") {
  if (queueSection) return "";
  const actionGroupLabel = escapeHtml(translate("taskActions.group"));
  const archiveLabel = escapeHtml(translate("taskContext.archive"));
  const deleteLabel = escapeHtml(translate("taskContext.delete"));
  return `
      <div class="task-card-actions" role="group" aria-label="${actionGroupLabel}">
        <button class="task-archive-button" type="button" data-archive-task-id="${taskId}" aria-label="${archiveLabel}" title="${archiveLabel}">
          <svg class="task-action-icon" viewBox="0 0 20 20" aria-hidden="true" focusable="false">
            <path d="M4 6h12v11H4z" />
            <path d="M6 3h8l2 3H4l2-3z" />
            <path d="M10 8v5" />
            <path d="M7.5 10.5L10 13l2.5-2.5" />
          </svg>
        </button>
        <button class="task-delete-button" type="button" data-delete-task-id="${taskId}" aria-label="${deleteLabel}" title="${deleteLabel}">
          <svg class="task-action-icon task-delete-icon" viewBox="0 0 20 20" aria-hidden="true" focusable="false">
            <path d="M5 5h10" />
            <path d="M8 5l1-2h2l1 2" />
            <path d="M6 5l1 12h6l1-12" />
            <path d="M8.5 8v6M11.5 8v6" />
          </svg>
        </button>
      </div>
  `;
}

function taskCardHtml(task: any) {
  const image = taskThumbHtml(task);
  const active = String(task.task_id) === String(state.selectedTaskId) ? " active" : "";
  const activeCurrent = active ? ' aria-current="true"' : "";
  const unread = taskHasUnreadUpdate(task);
  const unreadClass = unread ? " unread" : "";
  const statusClass = task.status ? ` ${escapeHtml(task.status)}` : "";
  const title = escapeHtml(task.prompt || task.mode || "Untitled");
  const statusLight = taskStatusLightHtml(task);
  const statusMeta = escapeHtml(taskMetaDetailsText(task));
  const imageBlocks = taskImageBlocksHtml(task);
  const imageSummary = escapeHtml(taskImageSummaryText(task));
  const retryText = taskRetryStateText(task);
  const runtime = taskRuntimeText(task);
  const completionTitle = taskCompletionTimestampTitle(task);
  const taskId = escapeHtml(task.task_id);
  const runtimeTitle = completionTitle ? ` title="${escapeHtml(completionTitle)}"` : "";
  const runtimeHtml = runtime ? `<div class="task-runtime" data-task-runtime-id="${taskId}" data-task-completed-at-id="${taskId}"${runtimeTitle}>${escapeHtml(runtime)}</div>` : "";
  const retryHtml = retryText ? `<div class="task-retry-state" data-task-retry-id="${taskId}">${escapeHtml(retryText)}</div>` : "";
  const batchSelected = state.batchSelectedTaskIds.includes(String(task.task_id));
  const batchClass = state.batchMode ? " batch-mode" : "";
  const batchSelectedClass = batchSelected ? " batch-selected" : "";
  const queueIds = queueTaskIdsBySection();
  const queueSection = taskQueueSection(task, queueIds);
  const queueClass = queueSection ? ` queue-${escapeHtml(queueSection)}` : "";
  const queueTaskData = queueSection === "waiting" ? ` data-queue-task-id="${taskId}"` : "";
  const queueActions = taskQueueActionStripHtml(task, queueSection, waitingQueueIndex(task.task_id, queueIds));
  const taskActions = taskCardActionsHtml(taskId, queueSection);
  const batchSelect = state.batchMode ? `
      <button class="task-select-button" type="button" data-batch-select-task-id="${taskId}" aria-pressed="${batchSelected ? "true" : "false"}" aria-label="${escapeHtml(translate("taskList.selectSession"))}">
        <span></span>
      </button>
    ` : "";
  const unreadDot = unread ? `<span class="task-unread-dot" aria-label="${escapeHtml(translate("taskList.unreadUpdate"))}"></span>` : "";
  const activeLabel = escapeHtml(translate("taskList.viewing"));
  return `
    <div class="task-card${active}${unreadClass}${statusClass}${batchClass}${batchSelectedClass}${queueClass}" role="button" tabindex="0" data-task-id="${taskId}" data-task-unread="${unread ? "true" : "false"}" data-active-label="${activeLabel}"${activeCurrent}${queueTaskData}>
      ${batchSelect}
      ${image}
      <div class="task-info">
        <div class="task-title-row">
          ${unreadDot}
          <div class="task-title">${title}</div>
        </div>
        <div class="task-status-row" aria-label="${escapeHtml(taskStatusAccessibleLabel(task))}">
          ${statusLight}
          <span class="task-status-meta">${statusMeta}</span>
        </div>
        <div class="task-image-row">
          ${imageBlocks}
          <span class="task-image-summary">${imageSummary}</span>
        </div>
        ${retryHtml}
        ${runtimeHtml}
      </div>
      ${queueActions}
      ${taskActions}
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
    if (!groupTasks.length) return;
    groups.push({
      key,
      label,
      tasks: groupTasks,
      collapsible: Boolean(options.collapsible),
      defaultCollapsed: Boolean(options.defaultCollapsed),
    });
    groupTasks.forEach((task: any) => assignedTaskIds.add(String(task.task_id)));
  };
  const historicalTasks = tasks.filter((task: any) => !isAlwaysVisibleTask(task));
  const unassignedTasks = () => historicalTasks.filter((task: any) => !assignedTaskIds.has(String(task.task_id)));

  addGroup(
    "today",
    translate("taskGroup.today"),
    unassignedTasks().filter((task: any) => taskDateBucket(task) === "today"),
    { collapsible: true, defaultCollapsed: false },
  );

  [
    ["yesterday", translate("taskGroup.yesterday")],
    ["last7", translate("taskGroup.last7")],
  ].forEach(([key, label]: any) => {
    addGroup(
      key,
      label,
      unassignedTasks().filter((task: any) => taskDateBucket(task) === key),
      { collapsible: true, defaultCollapsed: true },
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

function taskDateBucket(task: any) {
  const timestamp = timestampMs(task?.created_at || task?.updated_at || task?.started_at);
  if (timestamp === null) return "older";
  const now = new Date();
  const taskDate = new Date(timestamp);
  const todayStart = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime();
  const taskDayStart = new Date(taskDate.getFullYear(), taskDate.getMonth(), taskDate.getDate()).getTime();
  const dayDiff = Math.floor((todayStart - taskDayStart) / 86400000);
  if (dayDiff <= 0) return "today";
  if (dayDiff === 1) return "yesterday";
  if (dayDiff <= 6) return "last7";
  return "older";
}

function taskListRenderKey(tasks: any, query: any, layout: any = {}, filters: any = {}, activeGroup: any = null) {
  return JSON.stringify({
    query,
    filters,
    activeQueue: activeQueueTaskListRenderKey(),
    activeGroup: activeGroup
      ? [activeGroup.key, activeGroup.label, activeGroup.tasks.length]
      : null,
    batchMode: state.batchMode,
    batchSelectedTaskIds: state.batchSelectedTaskIds.map(String).sort(),
    archivedTaskIds: state.tasks.filter(taskArchived).map((task: any) => String(task.task_id)).sort(),
    expandedTaskGroupKey: state.expandedTaskGroupKey,
    queryMode: Boolean(layout.queryMode),
    expandedGroup: layout.expandedGroup
      ? [layout.expandedGroup.key, layout.expandedGroup.label, layout.expandedGroup.tasks.length]
      : null,
    anchorGroups: [
      (layout.top || []).map((group: any) => [group.key, group.tasks.length]),
      (layout.bottom || []).map((group: any) => [group.key, group.tasks.length]),
    ],
    tasks: tasks.map((task: any) => [
      task.task_id,
      task.status,
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

function taskThumbHtml(task: any, className: any = "task-thumb") {
  const outputUrl = taskOutputUrls(task)[0];
  const outputThumbnailUrl = taskThumbnailUrls(task)[0];
  const inputPreviewUrl = taskInputPreviewUrls(task)[0];
  const imageUrl = outputThumbnailUrl || outputUrl || task.preview_url || inputPreviewUrl;
  const safeClassName = escapeHtml(className);
  if (imageUrl && inputPreviewUrl) {
    const loadingSpinner = taskThumbShowsLoading(task) ? '<span class="task-thumb-stack-spinner" aria-hidden="true"></span>' : "";
    const imageToImageLabel = escapeHtml(translate("taskCard.imageToImageThumb"));
    return `
      <div class="${safeClassName} task-thumb-stack" aria-label="${imageToImageLabel}">
        <img class="task-thumb-reference" src="${escapeHtml(inputPreviewUrl)}" alt="" loading="lazy" decoding="async">
        <img class="task-thumb-output" src="${escapeHtml(imageUrl)}" alt="" loading="lazy" decoding="async">
        ${loadingSpinner}
      </div>
    `;
  }
  if (imageUrl) {
    const textToImageLabel = escapeHtml(translate("taskCard.textToImageThumb"));
    const textBadge = escapeHtml(translate("taskCard.textBadge"));
    return `
      <div class="${safeClassName} task-thumb-single" aria-label="${textToImageLabel}">
        <img class="task-thumb-single-image" src="${escapeHtml(imageUrl)}" alt="" loading="lazy" decoding="async">
        <span class="task-thumb-mode-badge" aria-hidden="true">${textBadge}</span>
      </div>
    `;
  }
  if (task.status === "failed") {
    return `<div class="${safeClassName} failed-thumb" aria-label="${escapeHtml(translate("taskCard.failedThumb"))}"><span>!</span></div>`;
  }
  return `<div class="${safeClassName} running-thumb"><span></span></div>`;
}

function taskStatusLightHtml(task: any) {
  const tone = taskStatusTone(task);
  const label = escapeHtml(formatTaskStatus(task) || translate("taskStatus.unknown"));
  const taskId = escapeHtml(task?.task_id || "");
  return `
    <span class="task-status-light ${tone}" aria-hidden="true"></span>
    <span class="task-status-label" data-task-status-id="${taskId}">${label}</span>
  `;
}

function taskStatusTone(task: any) {
  const status = String(task?.status || "");
  if (["failed", "partial_failed"].includes(status)) return "failed";
  if (status === "completed") return "completed";
  if (status === "running") return "running";
  if (status === "queued" || status === "submitting") return "queued";
  return "unknown";
}

function taskStatusAccessibleLabel(task: any) {
  return [formatTaskStatus(task) || translate("taskStatus.unknown"), taskImageSummaryText(task), taskMetaDetailsText(task)]
    .filter(Boolean)
    .join(" · ");
}

function taskMetaDetailsText(task: any) {
  const failure = taskFailureMessage(task);
  const retryText = taskRetryStateText(task);
  const size = task.output_size || task.params?.size || "";
  const backend = taskBackendLabel(task);
  return [failure, retryText, size, backend].filter(Boolean).join(" · ");
}

function taskImageBlocksHtml(task: any) {
  const states = taskImageBlockStates(task);
  const visibleStates = compressTaskImageBlockStates(states);
  const total = states.length;
  const visibleCount = Math.min(total, 12);
  const compressedClass = states.length > visibleStates.length ? " compressed" : "";
  const blocks = visibleStates.map((blockState: any) => `<span class="task-image-block ${blockState}" aria-hidden="true"></span>`).join("");
  return `<div class="task-image-progress${compressedClass}" style="--task-block-count: ${visibleCount}" aria-hidden="true">${blocks}</div>`;
}

function taskImageSummaryText(task: any) {
  const states = taskImageBlockStates(task);
  const counts = taskImageStatusCounts(states);
  const parts = [
    formatTranslation("taskCard.count", { count: states.length }),
    formatTranslation("taskCard.successCount", { count: counts.completed }),
    formatTranslation("taskCard.failedCount", { count: counts.failed }),
  ];
  if (counts.running) parts.push(formatTranslation("taskCard.runningCount", { count: counts.running }));
  if (counts.queued || counts.waiting) {
    parts.push(formatTranslation("taskCard.waitingCount", { count: counts.queued + counts.waiting }));
  }
  return parts.join(" · ");
}

function taskMetaText(task: any) {
  const failure = taskFailureMessage(task);
  const status = failure ? `${formatTaskStatus(task)} · ${failure}` : formatTaskStatus(task);
  const size = task.output_size || task.params?.size || "";
  const backend = taskBackendLabel(task);
  return [status, size, backend].filter(Boolean).join(" · ");
}

export function initTaskListRenderFeature() {
  document.addEventListener(LOCALE_CHANGE_EVENT, () => {
    state.tasksRenderKey = null;
    renderTasks();
  });
  Object.assign(getLegacyBridge().methods, {
    renderTasks,
    taskSearchQuery,
    taskFilterValues,
    taskMatchesSearch,
    taskMatchesFilters,
    filteredVisibleTasks,
    taskAnchorLayout,
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
    isAlwaysVisibleTask,
    taskDateBucket,
    taskListRenderKey,
    taskCardElement,
    updateTaskSelectionVisuals,
    taskThumbHtml,
    taskStatusLightHtml,
    taskStatusTone,
    taskStatusAccessibleLabel,
    taskMetaDetailsText,
    taskImageBlocksHtml,
    taskImageSummaryText,
    taskMetaText,
  });
}

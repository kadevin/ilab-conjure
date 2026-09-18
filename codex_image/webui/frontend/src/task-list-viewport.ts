import type { WebUIElements } from "./elements";
import type { WebUIState } from "./state";
import type { TaskListScrollAnchor } from "./task-list-types";
import { cssEscape, prefersReducedMotion } from "./webui-utils";

export interface TaskListViewportDependencies {
  getState: () => Readonly<Pick<WebUIState, "queue" | "queueDragTaskId">>;
  els: Pick<WebUIElements, "sidebarContent" | "taskActiveList" | "taskHistoryCurrentAnchor" | "taskHistoryShell" | "taskList">;
  consumeLatestTaskNavigationScrollAnchor: (anchor: TaskListScrollAnchor | null) => TaskListScrollAnchor | null;
  expandedTaskGroupHeaderHtml: (group: any, options?: { startExpanded?: boolean }) => string;
  scheduleLatestTaskNavigationRefresh: () => void;
  scheduleSidebarTaskGroupAutoLoad: () => void;
  taskCardHtml: (task: any) => string;
  taskGroupCount: (group: any) => number;
  taskGroupLoadMoreHtml: (group: any) => string;
  updateTaskElapsedDisplays: () => void;
  cancelActiveTaskQueueReorder: (options: { flushDeferred: boolean }) => void;
  consumeExpansionAnimation: () => boolean;
}

export function createTaskListViewport(dependencies: TaskListViewportDependencies) {
  const { getState, els, consumeLatestTaskNavigationScrollAnchor, expandedTaskGroupHeaderHtml, scheduleLatestTaskNavigationRefresh, scheduleSidebarTaskGroupAutoLoad, taskCardHtml, taskGroupCount, taskGroupLoadMoreHtml, updateTaskElapsedDisplays, cancelActiveTaskQueueReorder, consumeExpansionAnimation } = dependencies;
  let expandedTaskGroupRenderToken = 0;
  let deferredActiveTaskHtml: string | null = null;
  const EXPANDED_TASK_GROUP_INITIAL_CARD_COUNT = 24;
  const EXPANDED_TASK_GROUP_CHUNK_SIZE = 48;
  const EXPANDED_TASK_GROUP_ANIMATION_FALLBACK_MS = 320;

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

  function applyActiveTaskGroupHtml(activeHtml: string) {
    if (!els.taskActiveList) return;
    els.taskActiveList.innerHTML = activeHtml;
    els.taskActiveList.classList.toggle("hidden", !activeHtml);
  }

  function draggedTaskStillWaiting(): boolean {
    const state = getState();
    const taskId = String(state.queueDragTaskId || "");
    return Boolean(taskId && (state.queue.waiting || []).some(
      (task: any) => String(task?.task_id || "") === taskId,
    ));
  }

  function renderActiveTaskGroup(activeHtml: string) {
    const state = getState();
    if (!els.taskActiveList) return;
    if (state.queueDragTaskId && draggedTaskStillWaiting()) {
      deferredActiveTaskHtml = activeHtml;
      return;
    }
    if (state.queueDragTaskId) {
      cancelActiveTaskQueueReorder({ flushDeferred: false });
    }
    deferredActiveTaskHtml = null;
    applyActiveTaskGroupHtml(activeHtml);
  }

  function flushDeferredActiveTaskGroupRender(): boolean {
    const state = getState();
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
    const animationPending = consumeExpansionAnimation();
    const shouldAnimateExpand = !preserveExisting && animationPending;
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

  function renderExpandedTaskGroupHeader(group: any | null, options: { startExpanded?: boolean } = {}) {
    if (!els.taskHistoryCurrentAnchor) return;
    const html = group ? expandedTaskGroupHeaderHtml(group, options) : "";
    els.taskHistoryCurrentAnchor.innerHTML = html;
    els.taskHistoryCurrentAnchor.classList.toggle("hidden", !html);
  }
  function invalidateTaskGroupRender(): void { expandedTaskGroupRenderToken += 1; }


  return { captureTaskListScrollAnchors, captureTaskListScrollAnchor, restoreTaskListScrollAnchors, restoreTaskListScrollAnchor, applyActiveTaskGroupHtml, draggedTaskStillWaiting, renderActiveTaskGroup, flushDeferredActiveTaskGroupRender, discardDeferredActiveTaskGroupRender, expandedTaskGroupBodyElements, finalizeExpandedTaskGroupBody, animateExpandedTaskGroupBody, expandedTaskGroupItemsContainer, updateExpandedTaskGroupCount, appendExpandedTaskGroupPage, scheduleExpandedTaskGroupItemsRender, renderExpandedTaskGroupHeader, invalidateTaskGroupRender };
}

import { getLegacyBridge } from "./state";
import { TASK_HISTORY_EXPANDED_GROUP_STORAGE_KEY } from "./state-defaults";
import { prefersReducedMotion } from "./webui-utils";
import { formatTranslation, LOCALE_CHANGE_EVENT, translate } from "./i18n";

const bridge = getLegacyBridge();
const state = bridge.state;
const els = bridge.els;
let latestTaskNavigationFrameId = 0;
let latestTaskNavigationPinToken = 0;
let latestTaskNavigationInitialized = false;
let latestTaskNavigationPreRenderAtLatest: boolean | null = null;
let latestTaskNavigationPreRenderFirstTaskAboveViewport: boolean | null = null;
let latestTaskNavigationPreRenderGroupKey = "";
const TASK_HISTORY_LAYOUT_EASING = "ease";
const TASK_HISTORY_LAYOUT_DURATION_MS = 180;

const TASK_GROUP_ORDER = ["active", "current", "today", "yesterday", "last7", "older", "search"];
const TASK_HISTORY_ALL_COLLAPSED_SENTINEL = "__all_collapsed__";

function legacyMethod(name: string, ...args: any[]): any {
  const method = getLegacyBridge().methods[name];
  if (typeof method !== "function") {
    throw new Error("Legacy bridge method " + name + " is not available");
  }
  return method(...args);
}

function escapeHtml(...args: any[]) { return legacyMethod("escapeHtml", ...args); }
function taskGroupCount(...args: any[]) { return legacyMethod("taskGroupCount", ...args); }

function element(node: any): HTMLElement | null {
  return node instanceof HTMLElement ? node : null;
}

function latestTaskNavigationTargetGroupKey(visibleGroupKeys: any[]) {
  const groupOrder = ["today", "yesterday", "last7"];
  const keys = new Set((visibleGroupKeys || []).map((key) => String(key || "")));
  return groupOrder.find((key) => keys.has(key)) || null;
}

function latestTaskNavigationViewModel(input: any) {
  const latestGroupKey = latestTaskNavigationTargetGroupKey(input?.visibleGroupKeys || []);
  const hasOverflow = Number(input?.scrollHeight || 0) > Number(input?.clientHeight || 0) + 1;
  const scrollTopThreshold = 8;
  const atLatestPosition = input?.renderInProgress && typeof input?.preRenderAtLatest === "boolean"
    ? input.preRenderAtLatest
    : Number(input?.scrollTop || 0) <= scrollTopThreshold;
  const atLatest = Boolean(
    latestGroupKey
    && String(input?.currentGroupKey || "") === latestGroupKey
    && atLatestPosition,
  );
  const firstTaskAboveViewport = input?.renderInProgress && typeof input?.preRenderFirstTaskAboveViewport === "boolean"
    ? input.preRenderFirstTaskAboveViewport
    : typeof input?.firstTaskBottom === "number" && input.firstTaskBottom <= Number(input?.viewportTop || 0);
  const noticeCount = Math.max(0, Number(input?.noticeCount || 0));
  return {
    visible: Boolean(
      hasOverflow
      && latestGroupKey
      && firstTaskAboveViewport
      && !input?.searchActive
      && !input?.batchMode
    ),
    atLatest,
    latestGroupKey,
    badgeText: noticeCount > 9 ? "9+" : (noticeCount > 0 ? String(noticeCount) : ""),
    shouldClearNotice: Boolean(atLatest && !input?.renderInProgress),
  };
}

function latestTaskNavigationNextNoticeCount(currentCount: number, atLatest: boolean) {
  if (atLatest) return 0;
  return Math.min(99, Math.max(0, Number(currentCount || 0)) + 1);
}

function latestTaskNavigationPinnedScrollAnchor(anchor: any, keepAtTop: boolean) {
  if (!anchor || !keepAtTop) return anchor;
  const pinnedAnchor = {
    ...anchor,
    scrollTop: 0,
    retryMissingTask: false,
  };
  delete pinnedAnchor.taskId;
  delete pinnedAnchor.offsetTop;
  return pinnedAnchor;
}

function consumeLatestTaskNavigationScrollAnchor(anchor: any) {
  const keepAtTop = Boolean(
    state.latestTaskKeepAtTop === true
    && Number(state.latestTaskKeepAtTopExpiresAt || 0) >= Date.now()
  );
  if (!keepAtTop) {
    state.latestTaskKeepAtTop = false;
    state.latestTaskKeepAtTopExpiresAt = 0;
  }
  return latestTaskNavigationPinnedScrollAnchor(anchor, keepAtTop);
}

function settleLatestTaskNavigationAtTop() {
  const token = ++latestTaskNavigationPinToken;
  let remainingFrames = 4;
  const pinToTop = () => {
    if (token !== latestTaskNavigationPinToken || state.latestTaskKeepAtTop !== true) return;
    const sidebarContent = element(els.sidebarContent);
    if (sidebarContent) sidebarContent.scrollTop = 0;
    remainingFrames -= 1;
    if (remainingFrames > 0) {
      requestAnimationFrame(pinToTop);
      return;
    }
    state.latestTaskKeepAtTop = false;
    state.latestTaskKeepAtTopExpiresAt = 0;
    scheduleLatestTaskNavigationRefresh();
  };
  requestAnimationFrame(pinToTop);
}

function cancelLatestTaskNavigationTopPin() {
  if (state.latestTaskKeepAtTop !== true) return;
  state.latestTaskKeepAtTop = false;
  state.latestTaskKeepAtTopExpiresAt = 0;
  latestTaskNavigationPinToken += 1;
}

function handleLatestTaskNavigationKeydown(event: KeyboardEvent) {
  const sidebarContent = element(els.sidebarContent);
  if (!sidebarContent || !(document.activeElement instanceof Node)) return;
  if (!sidebarContent.contains(document.activeElement)) return;
  if (!["ArrowUp", "ArrowDown", "PageUp", "PageDown", "Home", "End", " "].includes(event.key)) return;
  cancelLatestTaskNavigationTopPin();
}

function isAllCollapsedExpandedTaskGroupKey(groupKey: string | null) {
  return String(groupKey || "") === TASK_HISTORY_ALL_COLLAPSED_SENTINEL;
}

function normalizedExpandedTaskGroupKey(groupKey: string | null) {
  const key = String(groupKey || "");
  if (!key) return TASK_HISTORY_ALL_COLLAPSED_SENTINEL;
  return key;
}

function restoreExpandedTaskGroupKey() {
  try {
    const stored = localStorage.getItem(TASK_HISTORY_EXPANDED_GROUP_STORAGE_KEY) || "";
    state.expandedTaskGroupKey = stored || null;
  } catch {
    state.expandedTaskGroupKey = null;
  }
}

function persistExpandedTaskGroupKey() {
  try {
    if (state.expandedTaskGroupKey) {
      localStorage.setItem(TASK_HISTORY_EXPANDED_GROUP_STORAGE_KEY, state.expandedTaskGroupKey);
    } else {
      localStorage.removeItem(TASK_HISTORY_EXPANDED_GROUP_STORAGE_KEY);
    }
  } catch {
    // Ignore storage errors in restricted contexts.
  }
}

function nearestVisibleGroupKey(groups: any[], currentKey: string | null) {
  const visibleKeys = groups.map((group) => String(group.key));
  const currentIndex = TASK_GROUP_ORDER.indexOf(String(currentKey || ""));
  if (currentIndex < 0) return visibleKeys[0] || null;
  for (let index = currentIndex + 1; index < TASK_GROUP_ORDER.length; index += 1) {
    const nextKey = TASK_GROUP_ORDER[index];
    if (nextKey && visibleKeys.includes(nextKey)) return nextKey;
  }
  for (let index = currentIndex - 1; index >= 0; index -= 1) {
    const previousKey = TASK_GROUP_ORDER[index];
    if (previousKey && visibleKeys.includes(previousKey)) return previousKey;
  }
  return visibleKeys[0] || null;
}

function ensureExpandedTaskGroupKey(groups: any[]) {
  const visible = groups.filter((group) => taskGroupCount(group) > 0);
  if (!visible.length) {
    state.expandedTaskGroupKey = null;
    persistExpandedTaskGroupKey();
    return null;
  }
  if (isAllCollapsedExpandedTaskGroupKey(state.expandedTaskGroupKey)) {
    return null;
  }
  const existing = visible.find((group) => String(group.key) === String(state.expandedTaskGroupKey));
  if (existing) return existing;
  const fallbackKey = nearestVisibleGroupKey(visible, state.expandedTaskGroupKey);
  const fallback = visible.find((group) => String(group.key) === String(fallbackKey)) || visible[0] || null;
  state.expandedTaskGroupKey = fallback?.key || null;
  persistExpandedTaskGroupKey();
  return fallback;
}

function applyImmediateAnchorSelection(groupKey: string) {
  document.querySelectorAll("[data-task-group-anchor-key]").forEach((node) => {
    node.classList.toggle(
      "active",
      String((node as HTMLElement).dataset.taskGroupAnchorKey || "") === String(groupKey || ""),
    );
  });
}

function setExpandedTaskGroupKey(groupKey: string | null, { immediate = false }: { immediate?: boolean } = {}) {
  const key = normalizedExpandedTaskGroupKey(groupKey);
  if (state.expandedTaskGroupKey === key) {
    if (immediate) applyImmediateAnchorSelection(isAllCollapsedExpandedTaskGroupKey(key) ? "" : key);
    return false;
  }
  state.expandedTaskGroupKey = key;
  persistExpandedTaskGroupKey();
  if (!isAllCollapsedExpandedTaskGroupKey(key)) {
    state.expandedTaskGroupAnimationPending = true;
  }
  if (immediate) applyImmediateAnchorSelection(isAllCollapsedExpandedTaskGroupKey(key) ? "" : key);
  state.tasksRenderKey = null;
  return true;
}

function scrollExpandedTaskGroupToTop(behavior: ScrollBehavior = "smooth") {
  const sidebarContent = element(els.sidebarContent);
  if (!sidebarContent) return;
  sidebarContent.scrollTo({ top: 0, behavior: prefersReducedMotion() ? "auto" : behavior });
}

function visibleTaskHistoryGroupKeys() {
  const keys = new Set<string>();
  document.querySelectorAll<HTMLElement>("[data-task-group-anchor-key], #taskList [data-task-group]").forEach((node) => {
    const key = String(node.dataset.taskGroupAnchorKey || node.dataset.taskGroup || "");
    if (key) keys.add(key);
  });
  return Array.from(keys);
}

function currentTaskHistoryGroupKey() {
  const group = els.taskList?.querySelector?.("[data-task-group]");
  return String(group?.dataset?.taskGroup || state.expandedTaskGroupKey || "");
}

function taskHistoryRenderInProgress() {
  const expandedItems = els.taskList?.querySelector?.(".task-group-items-expanded");
  return Boolean(
    expandedItems
    && expandedItems instanceof HTMLElement
    && expandedItems.dataset.renderComplete !== "true"
  );
}

function latestTaskNavigationCurrentViewModel() {
  const sidebarContent = element(els.sidebarContent);
  const renderInProgress = taskHistoryRenderInProgress();
  const currentGroupKey = currentTaskHistoryGroupKey();
  const firstTask = element(els.taskList?.querySelector?.(".task-group-items-expanded .task-card[data-task-id]:not(.task-card-removing)"));
  return latestTaskNavigationViewModel({
    scrollTop: sidebarContent?.scrollTop || 0,
    scrollHeight: sidebarContent?.scrollHeight || 0,
    clientHeight: sidebarContent?.clientHeight || 0,
    firstTaskBottom: firstTask && firstTask.offsetHeight > 0 ? firstTask.getBoundingClientRect().bottom : null,
    viewportTop: sidebarContent ? sidebarContent.getBoundingClientRect().top + sidebarContent.clientTop : 0,
    currentGroupKey,
    visibleGroupKeys: visibleTaskHistoryGroupKeys(),
    searchActive: Boolean(String(els.taskSearch?.value || "").trim()),
    batchMode: Boolean(state.batchMode),
    noticeCount: state.latestTaskNoticeCount,
    renderInProgress,
    preRenderAtLatest: renderInProgress ? latestTaskNavigationPreRenderAtLatest : null,
    preRenderFirstTaskAboveViewport: renderInProgress && currentGroupKey === latestTaskNavigationPreRenderGroupKey
      ? latestTaskNavigationPreRenderFirstTaskAboveViewport : null,
  });
}

function rememberLatestTaskNavigationBeforeRender() {
  if (taskHistoryRenderInProgress()) return;
  const viewModel = latestTaskNavigationCurrentViewModel();
  latestTaskNavigationPreRenderAtLatest = viewModel.atLatest;
  latestTaskNavigationPreRenderFirstTaskAboveViewport = viewModel.visible;
  latestTaskNavigationPreRenderGroupKey = currentTaskHistoryGroupKey();
}

function focusExpandedTaskGroupHeader() {
  const header = els.taskHistoryCurrentAnchor?.querySelector?.(".task-group-header-split");
  if (header instanceof HTMLElement) header.focus({ preventScroll: true });
}

function refreshLatestTaskNavigation() {
  const button = element(els.taskLatestButton);
  const badge = element(els.taskLatestBadge);
  if (!button) return;
  const viewModel = latestTaskNavigationCurrentViewModel();
  if (viewModel.shouldClearNotice && state.latestTaskNoticeCount) {
    state.latestTaskNoticeCount = 0;
  }
  const noticeCount = Math.max(0, Number(state.latestTaskNoticeCount || 0));
  const badgeText = noticeCount > 9 ? "9+" : (noticeCount > 0 ? String(noticeCount) : "");
  const shouldHide = !viewModel.visible;
  if (shouldHide && document.activeElement === button) {
    focusExpandedTaskGroupHeader();
  }
  button.hidden = shouldHide;
  button.classList.toggle("hidden", shouldHide);
  button.classList.toggle("has-newer", noticeCount > 0);
  if (badge) {
    badge.textContent = badgeText;
    badge.hidden = !badgeText;
  }
  const label = noticeCount > 0
    ? formatTranslation("taskList.backToLatestWithCount", { count: noticeCount })
    : translate("taskList.backToLatest");
  button.setAttribute("aria-label", label);
  button.title = label;
}

function scheduleLatestTaskNavigationRefresh() {
  if (latestTaskNavigationFrameId) return;
  latestTaskNavigationFrameId = requestAnimationFrame(() => {
    latestTaskNavigationFrameId = 0;
    refreshLatestTaskNavigation();
  });
}

function notifyLatestTaskAvailable(task: any) {
  const incomingGroupKey = String(legacyMethod("taskDateBucket", task) || "");
  const viewModel = latestTaskNavigationCurrentViewModel();
  const atIncomingTask = Boolean(
    incomingGroupKey
    && viewModel.latestGroupKey === incomingGroupKey
    && viewModel.atLatest
  );
  if (atIncomingTask) {
    state.latestTaskKeepAtTop = true;
    state.latestTaskKeepAtTopExpiresAt = Date.now() + 500;
    settleLatestTaskNavigationAtTop();
  }
  state.latestTaskNoticeCount = latestTaskNavigationNextNoticeCount(
    state.latestTaskNoticeCount,
    atIncomingTask,
  );
  scheduleLatestTaskNavigationRefresh();
}

function returnToLatestTask() {
  const viewModel = latestTaskNavigationCurrentViewModel();
  if (!viewModel.latestGroupKey) return;
  state.latestTaskNoticeCount = 0;
  const changed = setExpandedTaskGroupKey(viewModel.latestGroupKey, { immediate: true });
  if (changed) {
    legacyMethod("renderTasks");
  }
  requestAnimationFrame(() => {
    focusExpandedTaskGroupHeader();
    scrollExpandedTaskGroupToTop("smooth");
    scheduleLatestTaskNavigationRefresh();
  });
}

function anchorRowHtml(group: any) {
  const key = escapeHtml(group.key);
  return `
    <button
      class="task-history-anchor-row"
      type="button"
      data-task-group-anchor-key="${key}"
      data-task-group-toggle-key="${key}"
      aria-expanded="false"
      aria-label="${escapeHtml(formatTranslation("taskGroup.expand", { label: group.label }))}"
    >
      <span class="task-history-anchor-label">
        <span class="task-group-title">
          <span class="task-group-label">${escapeHtml(group.label)}</span>
          <span class="task-group-count-separator" aria-hidden="true">·</span>
          <span class="task-group-count">${taskGroupCount(group)}</span>
        </span>
      </span>
      <span
        class="task-history-anchor-arrow"
        aria-hidden="true"
      >
        <span class="task-group-toggle" aria-hidden="true">
          <svg class="task-group-toggle-icon" data-ui-icon="chevron-right" width="16" height="16" viewBox="0 0 24 24" aria-hidden="true" focusable="false"><use href="/static/icons/ui.svg?v=1#chevron-right"/></svg>
        </span>
      </span>
    </button>
  `;
}

function renderTaskHistoryAnchors(layout: { top: any[]; bottom: any[]; expandedKey: string | null }) {
  const topAnchors = element(els.taskHistoryTopAnchors);
  const bottomAnchors = element(els.taskHistoryBottomAnchors);
  if (!topAnchors || !bottomAnchors) return;
  topAnchors.innerHTML = layout.top.map((group) => anchorRowHtml(group)).join("");
  bottomAnchors.innerHTML = layout.bottom.map((group) => anchorRowHtml(group)).join("");
  topAnchors.classList.toggle("hidden", !layout.top.length);
  bottomAnchors.classList.toggle("hidden", !layout.bottom.length);
  applyImmediateAnchorSelection(layout.expandedKey || "");
}

function taskHistoryLayoutElements() {
  const shell = element(els.taskHistoryShell);
  if (!shell) return [];
  return Array.from(
    shell.querySelectorAll<HTMLElement>(".task-history-anchor-row, .task-group-header-split"),
  ).map((node) => {
    const key = String(
      node.dataset.activeTaskGroupToggle
        ? "active"
        : node.dataset.taskGroupAnchorKey
        || node.dataset.taskGroupToggleKey
        || "",
    );
    if (!key) return null;
    const rect = node.getBoundingClientRect();
    const activeExpanded = node.dataset.activeTaskGroupToggle
      ? node.getAttribute("aria-expanded") === "true"
      : null;
    return {
      key,
      kind: activeExpanded === null
        ? (node.classList.contains("task-history-anchor-row") ? "anchor" : "expanded")
        : (activeExpanded ? "expanded" : "anchor"),
      node,
      rect: {
        top: rect.top,
        left: rect.left,
        width: rect.width,
        height: rect.height,
      },
    };
  }).filter(Boolean) as Array<{
    key: string;
    kind: "anchor" | "expanded";
    node: HTMLElement;
    rect: { top: number; left: number; width: number; height: number };
  }>;
}

function captureTaskHistoryLayout() {
  return taskHistoryLayoutElements().reduce((snapshot, item) => {
    snapshot[item.key] = {
      kind: item.kind,
      rect: item.rect,
    };
    return snapshot;
  }, {} as Record<string, { kind: "anchor" | "expanded"; rect: { top: number; left: number; width: number; height: number } }>);
}

function animateTaskHistoryLayout(previousLayout: Record<string, { kind: "anchor" | "expanded"; rect: { top: number; left: number; width: number; height: number } }> = {}) {
  if (prefersReducedMotion()) return;
  requestAnimationFrame(() => {
    taskHistoryLayoutElements().forEach((item) => {
      const previous = previousLayout[item.key];
      if (previous) {
        const dx = previous.rect.left - item.rect.left;
        const dy = previous.rect.top - item.rect.top;
        if (Math.abs(dx) > 0.5 || Math.abs(dy) > 0.5) {
          item.node.animate(
            [
              { transform: `translate(${dx}px, ${dy}px)` },
              { transform: "translate(0px, 0px)" },
            ],
            {
              duration: TASK_HISTORY_LAYOUT_DURATION_MS,
              easing: TASK_HISTORY_LAYOUT_EASING,
            },
          );
        }
        if (previous.kind !== item.kind) {
          const toggle = item.node.querySelector<HTMLElement>(".task-group-toggle");
          const fromAngle = previous.kind === "expanded" ? 90 : 0;
          const toAngle = item.kind === "expanded" ? 90 : 0;
          if (toggle && fromAngle !== toAngle) {
            toggle.animate(
              [
                { transform: `rotate(${fromAngle}deg)` },
                { transform: `rotate(${toAngle}deg)` },
              ],
              {
                duration: TASK_HISTORY_LAYOUT_DURATION_MS,
                easing: TASK_HISTORY_LAYOUT_EASING,
              },
            );
          }
        }
      }
    });
  });
}

export function initTaskHistoryAnchorsFeature() {
  Object.assign(getLegacyBridge().methods, {
    restoreExpandedTaskGroupKey,
    ensureExpandedTaskGroupKey,
    setExpandedTaskGroupKey,
    scrollExpandedTaskGroupToTop,
    renderTaskHistoryAnchors,
    captureTaskHistoryLayout,
    animateTaskHistoryLayout,
    scheduleLatestTaskNavigationRefresh,
    notifyLatestTaskAvailable,
    consumeLatestTaskNavigationScrollAnchor,
    rememberLatestTaskNavigationBeforeRender,
  });
  if (!latestTaskNavigationInitialized) {
    latestTaskNavigationInitialized = true;
    els.sidebarContent?.addEventListener("scroll", scheduleLatestTaskNavigationRefresh, { passive: true });
    els.sidebarContent?.addEventListener("wheel", cancelLatestTaskNavigationTopPin, { passive: true });
    els.sidebarContent?.addEventListener("pointerdown", cancelLatestTaskNavigationTopPin, { passive: true });
    els.taskLatestButton?.addEventListener("click", returnToLatestTask);
    window.addEventListener("resize", scheduleLatestTaskNavigationRefresh);
    document.addEventListener(LOCALE_CHANGE_EVENT, scheduleLatestTaskNavigationRefresh);
    document.addEventListener("keydown", handleLatestTaskNavigationKeydown);
  }
  scheduleLatestTaskNavigationRefresh();
}

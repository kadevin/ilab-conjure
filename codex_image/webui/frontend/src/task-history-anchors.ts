import { getLegacyBridge } from "./state";
import { TASK_HISTORY_EXPANDED_GROUP_STORAGE_KEY } from "./state-defaults";
import { formatTranslation } from "./i18n";

const bridge = getLegacyBridge();
const state = bridge.state;
const els = bridge.els;
let taskHistoryAnchorInsetObserver: ResizeObserver | null = null;
const TASK_HISTORY_LAYOUT_EASING = "ease";
const TASK_HISTORY_LAYOUT_DURATION_MS = 180;

const TASK_GROUP_ORDER = ["active", "today", "yesterday", "last7", "older", "search"];
const TASK_HISTORY_ALL_COLLAPSED_SENTINEL = "__all_collapsed__";

function legacyMethod(name: string, ...args: any[]): any {
  const method = getLegacyBridge().methods[name];
  if (typeof method !== "function") {
    throw new Error("Legacy bridge method " + name + " is not available");
  }
  return method(...args);
}

function escapeHtml(...args: any[]) { return legacyMethod("escapeHtml", ...args); }

function element(node: any): HTMLElement | null {
  return node instanceof HTMLElement ? node : null;
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

function syncTaskHistoryAnchorInset() {
  const shell = element(els.taskHistoryShell);
  const sidebarContent = element(els.sidebarContent);
  if (!shell || !sidebarContent) return;
  const scrollbarInset = Math.max(0, sidebarContent.offsetWidth - sidebarContent.clientWidth);
  shell.style.setProperty("--task-history-scrollbar-offset", `${scrollbarInset}px`);
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
  const visible = groups.filter((group) => Array.isArray(group?.tasks) && group.tasks.length);
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
  if (immediate) applyImmediateAnchorSelection(isAllCollapsedExpandedTaskGroupKey(key) ? "" : key);
  state.tasksRenderKey = null;
  return true;
}

function scrollExpandedTaskGroupToTop(behavior: ScrollBehavior = "smooth") {
  const sidebarContent = element(els.sidebarContent);
  if (!sidebarContent) return;
  sidebarContent.scrollTo({ top: 0, behavior });
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
          <span class="task-group-count-separator" aria-hidden="true"> · </span>
          <span class="task-group-count">${group.tasks.length}</span>
        </span>
      </span>
      <span
        class="task-history-anchor-arrow"
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

function renderTaskHistoryAnchors(layout: { top: any[]; bottom: any[]; expandedKey: string | null }) {
  const topAnchors = element(els.taskHistoryTopAnchors);
  const bottomAnchors = element(els.taskHistoryBottomAnchors);
  if (!topAnchors || !bottomAnchors) return;
  syncTaskHistoryAnchorInset();
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
      node.dataset.taskGroupAnchorKey
        || node.dataset.taskGroupToggleKey
        || "",
    );
    if (!key) return null;
    const rect = node.getBoundingClientRect();
    return {
      key,
      kind: node.classList.contains("task-history-anchor-row") ? "anchor" : "expanded",
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
  if (typeof ResizeObserver === "function" && !taskHistoryAnchorInsetObserver && element(els.sidebarContent)) {
    taskHistoryAnchorInsetObserver = new ResizeObserver(() => syncTaskHistoryAnchorInset());
    taskHistoryAnchorInsetObserver.observe(element(els.sidebarContent) as Element);
  }
  syncTaskHistoryAnchorInset();
  Object.assign(getLegacyBridge().methods, {
    restoreExpandedTaskGroupKey,
    ensureExpandedTaskGroupKey,
    setExpandedTaskGroupKey,
    scrollExpandedTaskGroupToTop,
    renderTaskHistoryAnchors,
    captureTaskHistoryLayout,
    animateTaskHistoryLayout,
  });
}

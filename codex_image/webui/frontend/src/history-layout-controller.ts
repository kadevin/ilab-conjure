import { createHistoryGridResizeController, historyGridAvailableWidth, historyGridCardsNeedLayout, type HistoryGridResizeController } from "./history-grid-resize";
import { type HistoryResizerSide, type HistoryViewMode } from "./history-types";
import { historyTaskCards } from "./history-window";

export function createHistoryLayoutController(options: {
  view(): HistoryViewMode;
  selectedTaskId(): string;
  card(taskId: string): HTMLElement | null;
  closeContextMenu(): void
}) {
  const lifetime = new AbortController();
  let bound = false;
  const els = {
    page: document.querySelector<HTMLElement>(".history-page"),
    sidebar: document.querySelector<HTMLElement>(".history-sidebar"),
    leftResizer: document.querySelector<HTMLElement>('[data-history-resizer="left"]'),
    rightResizer: document.querySelector<HTMLElement>('[data-history-resizer="right"]'),
    taskList: document.querySelector<HTMLElement>("#historyTaskList"),
    detail: document.querySelector<HTMLElement>("#historyDetail"),
  };

  const HISTORY_GRID_DEFAULT_GAP = 14;

  const HISTORY_LAYOUT_STORAGE_KEY = "codex-image-history-layout";

  const HISTORY_LAYOUT_DEFAULTS = { left: 280, right: 380 };

  const HISTORY_LAYOUT_LIMITS = {
    leftMin: 220,
    leftMax: 420,
    rightMin: 300,
    rightMax: 620,
    middleMin: 360,
  };

  type HistoryGridLayoutSettings = {
    targetHeight: number;
    minWidth: number;
    maxWidth: number;
    maxItems?: number;
  };

  type HistoryGridLayoutItem = {
    card: HTMLElement;
    ratio: number;
  };

  type HistoryGridLayoutSnapshot = {
    items: HistoryGridLayoutItem[];
    availableWidth: number;
    gap: number;
    settings: HistoryGridLayoutSettings;
  };

  type HistoryGridLayoutOptions = {
    snapshot?: HistoryGridLayoutSnapshot | null;
    availableWidth?: number | undefined;
  };

  type HistoryActiveResizer = {
    side: HistoryResizerSide;
    pointerId: number;
    startX: number;
    latestX: number;
    startLeft: number;
    startRight: number;
    maxCombinedWidth: number;
    gridLayoutSnapshot: HistoryGridLayoutSnapshot | null;
    element: HTMLElement;
  };

  const EMPTY_HISTORY_GRID_LAYOUT_OPTIONS: HistoryGridLayoutOptions = {};

  let historyGridLayoutFrame = 0;

  let pendingHistoryGridKeepTaskId = "";

  let historyResizeFrame = 0;

  let historyGridResizeObserver: ResizeObserver | null = null;

  let historyGridMutationObserver: MutationObserver | null = null;

  let historyGridResizeController: HistoryGridResizeController | null = null;

  let activeHistoryResizer: HistoryActiveResizer | null = null;

  function historyGridLayoutSettings(): HistoryGridLayoutSettings {
    if (window.matchMedia("(max-width: 600px)").matches) {
      return { targetHeight: 220, minWidth: 132, maxWidth: 320, maxItems: 2 };
    }
    if (window.matchMedia("(max-width: 760px)").matches) {
      return { targetHeight: 176, minWidth: 132, maxWidth: 320 };
    }
    return { targetHeight: 220, minWidth: 150, maxWidth: 430 };
  }

  function isHistoryTaskCardVisible(taskId: string): boolean {
    const list = els.taskList;
    const card = options.card(taskId);
    if (!list || !card) return false;
    const listRect = list.getBoundingClientRect();
    const cardRect = card.getBoundingClientRect();
    return cardRect.bottom > listRect.top
      && cardRect.top < listRect.bottom
      && cardRect.right > listRect.left
      && cardRect.left < listRect.right;
  }

  function activeHistoryTaskVisible(): string {
    const taskId = options.selectedTaskId();
    return taskId && isHistoryTaskCardVisible(taskId) ? taskId : "";
  }

  function ensureHistoryTaskCardVisible(taskId: string): void {
    options.card(taskId)?.scrollIntoView({ block: "nearest", inline: "nearest" });
  }

  function scheduleHistoryGridLayout(options: { keepTaskId?: string } = {}): void {
    if (options.keepTaskId) pendingHistoryGridKeepTaskId = options.keepTaskId;
    if (historyGridLayoutFrame) return;
    historyGridLayoutFrame = window.requestAnimationFrame(() => {
      historyGridLayoutFrame = 0;
      const keepTaskId = pendingHistoryGridKeepTaskId;
      pendingHistoryGridKeepTaskId = "";
      layoutJustifiedHistoryGrid();
      if (keepTaskId) ensureHistoryTaskCardVisible(keepTaskId);
    });
  }

  function parseCssPixels(value: string): number {
    const parsed = Number.parseFloat(value);
    return Number.isFinite(parsed) ? parsed : 0;
  }

  function clampNumber(value: number, min: number, max: number): number {
    return Math.min(max, Math.max(min, value));
  }

  function isHistoryResizableLayout(): boolean {
    return Boolean(els.page) && !window.matchMedia("(max-width: 1100px)").matches;
  }

  function readHistoryLayoutPreference(): { left: number; right: number } {
    try {
      const raw = localStorage.getItem(HISTORY_LAYOUT_STORAGE_KEY);
      if (!raw) return { ...HISTORY_LAYOUT_DEFAULTS };
      const parsed = JSON.parse(raw) as Partial<{ left: number; right: number }>;
      return {
        left: typeof parsed.left === "number" && Number.isFinite(parsed.left) ? parsed.left : HISTORY_LAYOUT_DEFAULTS.left,
        right: typeof parsed.right === "number" && Number.isFinite(parsed.right) ? parsed.right : HISTORY_LAYOUT_DEFAULTS.right,
      };
    } catch {
      return { ...HISTORY_LAYOUT_DEFAULTS };
    }
  }

  function historyLayoutMaxCombinedWidth(): number {
    const pageWidth = els.page?.getBoundingClientRect().width || window.innerWidth || 0;
    return Math.max(
      HISTORY_LAYOUT_LIMITS.leftMin + HISTORY_LAYOUT_LIMITS.rightMin,
      pageWidth - HISTORY_LAYOUT_LIMITS.middleMin,
    );
  }

  function constrainHistoryLayoutWidths(
    left: number,
    right: number,
    prioritySide: HistoryResizerSide | "" = "",
    maxCombinedWidth = historyLayoutMaxCombinedWidth(),
  ): { left: number; right: number } {
    let nextLeft = clampNumber(Math.round(left), HISTORY_LAYOUT_LIMITS.leftMin, HISTORY_LAYOUT_LIMITS.leftMax);
    let nextRight = clampNumber(Math.round(right), HISTORY_LAYOUT_LIMITS.rightMin, HISTORY_LAYOUT_LIMITS.rightMax);
    let overflow = nextLeft + nextRight - maxCombinedWidth;
    if (overflow > 0) {
      if (prioritySide === "left") {
        const rightReduction = Math.min(overflow, nextRight - HISTORY_LAYOUT_LIMITS.rightMin);
        nextRight -= rightReduction;
        overflow -= rightReduction;
        nextLeft -= Math.min(overflow, nextLeft - HISTORY_LAYOUT_LIMITS.leftMin);
      } else {
        const leftReduction = Math.min(overflow, nextLeft - HISTORY_LAYOUT_LIMITS.leftMin);
        nextLeft -= leftReduction;
        overflow -= leftReduction;
        nextRight -= Math.min(overflow, nextRight - HISTORY_LAYOUT_LIMITS.rightMin);
      }
    }
    return { left: Math.round(nextLeft), right: Math.round(nextRight) };
  }

  function getCurrentHistoryLayoutWidths(): { left: number; right: number } {
    const fromStyle = {
      left: parseCssPixels(els.page?.style.getPropertyValue("--history-sidebar-width") || ""),
      right: parseCssPixels(els.page?.style.getPropertyValue("--history-detail-width") || ""),
    };
    if (fromStyle.left && fromStyle.right) return fromStyle;
    const sidebarWidth = els.sidebar?.getBoundingClientRect().width || HISTORY_LAYOUT_DEFAULTS.left;
    const detailWidth = els.detail?.getBoundingClientRect().width || HISTORY_LAYOUT_DEFAULTS.right;
    return constrainHistoryLayoutWidths(sidebarWidth, detailWidth);
  }

  function applyHistoryLayoutWidths(
    left: number,
    right: number,
    options: {
      persist?: boolean;
      preserveActiveTask?: boolean;
      prioritySide?: HistoryResizerSide | "";
    } = {},
  ): void {
    if (!els.page) return;
    const keepTaskId = options.preserveActiveTask ? activeHistoryTaskVisible() : "";
    const widths = constrainHistoryLayoutWidths(left, right, options.prioritySide || "");
    els.page.style.setProperty("--history-sidebar-width", `${widths.left}px`);
    els.page.style.setProperty("--history-detail-width", `${widths.right}px`);
    els.leftResizer?.setAttribute("aria-valuenow", String(widths.left));
    els.rightResizer?.setAttribute("aria-valuenow", String(widths.right));
    scheduleHistoryGridLayout({ keepTaskId });
    if (options.persist) {
      try {
        localStorage.setItem(HISTORY_LAYOUT_STORAGE_KEY, JSON.stringify(widths));
      } catch {
        // Browser storage may be unavailable in restricted contexts.
      }
    }
  }

  function applyPendingHistoryResize(resize = activeHistoryResizer): void {
    historyResizeFrame = 0;
    if (!resize || !els.page) return;
    const delta = resize.latestX - resize.startX;
    const nextLeft = resize.side === "left" ? resize.startLeft + delta : resize.startLeft;
    const nextRight = resize.side === "right" ? resize.startRight - delta : resize.startRight;
    const widths = constrainHistoryLayoutWidths(
      nextLeft,
      nextRight,
      resize.side,
      resize.maxCombinedWidth,
    );
    els.page.style.setProperty("--history-sidebar-width", `${widths.left}px`);
    els.page.style.setProperty("--history-detail-width", `${widths.right}px`);
    els.leftResizer?.setAttribute("aria-valuenow", String(widths.left));
    els.rightResizer?.setAttribute("aria-valuenow", String(widths.right));
  }

  function layoutHistoryGridAfterResize(resize = activeHistoryResizer): void {
    if (!resize) return;
    const widths = getCurrentHistoryLayoutWidths();
    const availableWidth = resize.gridLayoutSnapshot
      ? resize.gridLayoutSnapshot.availableWidth
      + resize.startLeft + resize.startRight
      - widths.left - widths.right
      : undefined;
    layoutJustifiedHistoryGrid({
      snapshot: resize.gridLayoutSnapshot,
      availableWidth,
    });
  }

  function restoreHistoryLayoutPreference(): void {
    const stored = readHistoryLayoutPreference();
    const widths = constrainHistoryLayoutWidths(stored.left, stored.right);
    applyHistoryLayoutWidths(widths.left, widths.right);
  }

  function resetHistoryLayoutSide(side: HistoryResizerSide): void {
    const widths = getCurrentHistoryLayoutWidths();
    const nextLeft = side === "left" ? HISTORY_LAYOUT_DEFAULTS.left : widths.left;
    const nextRight = side === "right" ? HISTORY_LAYOUT_DEFAULTS.right : widths.right;
    applyHistoryLayoutWidths(nextLeft, nextRight, { persist: true, preserveActiveTask: true, prioritySide: side });
  }

  function resizeHistoryLayoutByKeyboard(side: HistoryResizerSide, event: KeyboardEvent): boolean {
    const step = event.shiftKey ? 48 : 16;
    const widths = getCurrentHistoryLayoutWidths();
    let nextLeft = widths.left;
    let nextRight = widths.right;
    if (event.key === "ArrowLeft") {
      if (side === "left") nextLeft -= step;
      else nextRight += step;
    } else if (event.key === "ArrowRight") {
      if (side === "left") nextLeft += step;
      else nextRight -= step;
    } else if (event.key === "Home") {
      if (side === "left") nextLeft = HISTORY_LAYOUT_LIMITS.leftMin;
      else nextRight = HISTORY_LAYOUT_LIMITS.rightMax;
    } else if (event.key === "End") {
      if (side === "left") nextLeft = HISTORY_LAYOUT_LIMITS.leftMax;
      else nextRight = HISTORY_LAYOUT_LIMITS.rightMin;
    } else if (event.key === "Enter" || event.key === " ") {
      resetHistoryLayoutSide(side);
      return true;
    } else {
      return false;
    }
    applyHistoryLayoutWidths(nextLeft, nextRight, { persist: true, preserveActiveTask: true, prioritySide: side });
    return true;
  }

  function startHistoryResize(side: HistoryResizerSide, event: PointerEvent, element: HTMLElement): void {
    if (event.button !== 0 || !isHistoryResizableLayout()) return;
    const widths = getCurrentHistoryLayoutWidths();
    activeHistoryResizer = {
      side,
      pointerId: event.pointerId,
      startX: event.clientX,
      latestX: event.clientX,
      startLeft: widths.left,
      startRight: widths.right,
      maxCombinedWidth: historyLayoutMaxCombinedWidth(),
      gridLayoutSnapshot: captureHistoryGridLayoutSnapshot(),
      element,
    };
    options.closeContextMenu();
    event.preventDefault();
    element.setPointerCapture?.(event.pointerId);
    els.page?.classList.add("history-resizing");
  }

  function updateHistoryResize(event: PointerEvent): void {
    if (!activeHistoryResizer || event.pointerId !== activeHistoryResizer.pointerId) return;
    activeHistoryResizer.latestX = event.clientX;
    if (historyResizeFrame) return;
    historyResizeFrame = window.requestAnimationFrame(() => applyPendingHistoryResize());
  }

  function endHistoryResize(event?: Event): void {
    const resize = activeHistoryResizer;
    if (!resize) return;
    const pointerEvent = event && "pointerId" in event ? event as PointerEvent : null;
    if (pointerEvent && pointerEvent.pointerId !== resize.pointerId) return;
    if (pointerEvent?.type === "pointerup") resize.latestX = pointerEvent.clientX;
    const keepTaskId = activeHistoryTaskVisible();
    activeHistoryResizer = null;
    if (historyResizeFrame) {
      window.cancelAnimationFrame(historyResizeFrame);
      historyResizeFrame = 0;
    }
    applyPendingHistoryResize(resize);
    layoutHistoryGridAfterResize(resize);
    if (resize.element.hasPointerCapture?.(resize.pointerId)) {
      resize.element.releasePointerCapture?.(resize.pointerId);
    }
    const widths = getCurrentHistoryLayoutWidths();
    try {
      localStorage.setItem(HISTORY_LAYOUT_STORAGE_KEY, JSON.stringify(widths));
    } catch {
      // Browser storage may be unavailable in restricted contexts.
    }
    els.page?.classList.remove("history-resizing");
    if (keepTaskId) ensureHistoryTaskCardVisible(keepTaskId);
  }

  function bindHistoryResizerEvents(): void {
    if (bound) return;
    bound = true;
    for (const resizer of [els.leftResizer, els.rightResizer]) {
      const side = resizer?.dataset.historyResizer as HistoryResizerSide | undefined;
      if (!resizer || (side !== "left" && side !== "right")) continue;
      resizer.addEventListener("pointerdown", (event) => startHistoryResize(side, event, resizer), { signal: lifetime.signal });
      resizer.addEventListener("lostpointercapture", endHistoryResize, { signal: lifetime.signal });
      resizer.addEventListener("dblclick", () => resetHistoryLayoutSide(side), { signal: lifetime.signal });
      resizer.addEventListener("keydown", (event) => {
        if (!isHistoryResizableLayout()) return;
        if (!resizeHistoryLayoutByKeyboard(side, event)) return;
        event.preventDefault();
        event.stopPropagation();
      }, { signal: lifetime.signal });
    }
    window.addEventListener("pointermove", updateHistoryResize, { signal: lifetime.signal });
    window.addEventListener("pointerup", endHistoryResize, { signal: lifetime.signal });
    window.addEventListener("pointercancel", endHistoryResize, { signal: lifetime.signal });
    window.addEventListener("blur", endHistoryResize, { signal: lifetime.signal });
    document.addEventListener("visibilitychange", () => {
      if (document.visibilityState === "hidden") endHistoryResize();
    }, { signal: lifetime.signal });
  }

  function bindHistoryGridResizeObserver(): void {
    const root = els.taskList;
    if (!root || historyGridResizeObserver || !("ResizeObserver" in window)) return;
    historyGridResizeController = createHistoryGridResizeController({
      isResizing: () => Boolean(activeHistoryResizer),
      scheduleLayout: () => scheduleHistoryGridLayout({ keepTaskId: activeHistoryTaskVisible() }),
    });
    historyGridResizeObserver = new ResizeObserver((entries) => {
      const entry = entries.find(({ target }) => target === root);
      if (entry) historyGridResizeController?.observeWidth(entry.contentRect.width);
    });
    historyGridResizeObserver.observe(root);
  }

  function historyGridLayoutIsIncomplete(root: HTMLElement): boolean {
    return historyGridCardsNeedLayout(historyTaskCards(root).map((card) => ({
      width: card.style.getPropertyValue("--history-task-card-width"),
      rowHeight: card.style.getPropertyValue("--history-task-row-height"),
    })));
  }

  function bindHistoryGridMutationObserver(): void {
    const root = els.taskList;
    if (!root || historyGridMutationObserver || !("MutationObserver" in window)) return;
    historyGridMutationObserver = new MutationObserver(() => {
      if (options.view() !== "grid" || !historyGridLayoutIsIncomplete(root)) return;
      scheduleHistoryGridLayout({ keepTaskId: activeHistoryTaskVisible() });
    });
    historyGridMutationObserver.observe(root, {
      attributes: true,
      attributeFilter: ["style"],
      childList: true,
      subtree: true,
    });
  }

  function historyTaskCardRatio(card: HTMLElement): number {
    const ratio = Number.parseFloat(card.style.getPropertyValue("--history-task-card-ratio"));
    return Number.isFinite(ratio) && ratio > 0 ? clampNumber(ratio, 0.42, 3.2) : 1;
  }

  function captureHistoryGridLayoutSnapshot(): HistoryGridLayoutSnapshot | null {
    const root = els.taskList;
    if (!root || options.view() !== "grid" || !root.classList.contains("history-view-grid")) return null;
    const cards = historyTaskCards(root);
    if (!cards.length) return null;
    const rootStyle = window.getComputedStyle(root);
    const availableWidth = historyGridAvailableWidth({
      boundingWidth: root.getBoundingClientRect().width,
      clientWidth: root.clientWidth,
      offsetWidth: root.offsetWidth,
      paddingLeft: parseCssPixels(rootStyle.paddingLeft),
      paddingRight: parseCssPixels(rootStyle.paddingRight),
    });
    if (availableWidth < 80) return null;
    return {
      items: cards.map((card) => ({ card, ratio: historyTaskCardRatio(card) })),
      availableWidth,
      gap: parseCssPixels(rootStyle.columnGap || rootStyle.gap) || HISTORY_GRID_DEFAULT_GAP,
      settings: historyGridLayoutSettings(),
    };
  }

  function applyHistoryGridRowLayout(
    row: HistoryGridLayoutItem[],
    options: { fillRow: boolean; availableWidth: number; gap: number; settings: HistoryGridLayoutSettings },
  ): void {
    if (!row.length) return;
    const { fillRow, availableWidth, gap, settings } = options;
    const gapWidth = gap * Math.max(0, row.length - 1);
    const availableContentWidth = Math.max(1, availableWidth - gapWidth);
    const ratioTotal = row.reduce((sum, item) => sum + item.ratio, 0) || 1;
    const rowHeight = fillRow ? availableContentWidth / ratioTotal : settings.targetHeight;
    let widths = row.map((item) => {
      const naturalWidth = item.ratio * rowHeight;
      return fillRow
        ? Math.max(1, Math.floor(naturalWidth))
        : Math.round(clampNumber(naturalWidth, settings.minWidth, Math.min(settings.maxWidth, availableWidth)));
    });

    if (fillRow) {
      let delta = Math.round(availableContentWidth - widths.reduce((sum, width) => sum + width, 0));
      const direction = delta >= 0 ? 1 : -1;
      delta = Math.abs(delta);
      for (let index = 0; index < widths.length && delta > 0; index = (index + 1) % widths.length) {
        widths[index] = (widths[index] || 1) + direction;
        delta -= 1;
      }
    }

    row.forEach((item, index) => {
      item.card.style.setProperty("--history-task-row-height", `${Math.max(1, Math.round(rowHeight))}px`);
      item.card.style.setProperty("--history-task-card-width", `${Math.max(1, widths[index] || 1)}px`);
    });
  }

  function layoutJustifiedHistoryGrid(
    layoutOptions: HistoryGridLayoutOptions = EMPTY_HISTORY_GRID_LAYOUT_OPTIONS,
  ): void {
    const snapshot = layoutOptions.snapshot === undefined
      ? captureHistoryGridLayoutSnapshot()
      : layoutOptions.snapshot;
    if (!snapshot) return;
    const availableWidth = layoutOptions.availableWidth ?? snapshot.availableWidth;
    if (availableWidth < 80) return;
    const { gap, settings } = snapshot;
    let row: HistoryGridLayoutItem[] = [];
    let rowRatioTotal = 0;

    for (const item of snapshot.items) {
      row.push(item);
      rowRatioTotal += item.ratio;
      const projectedWidth = (rowRatioTotal * settings.targetHeight) + (gap * Math.max(0, row.length - 1));
      if (row.length > 1 && (projectedWidth >= availableWidth || row.length >= (settings.maxItems ?? Infinity))) {
        applyHistoryGridRowLayout(row, { fillRow: true, availableWidth, gap, settings });
        row = [];
        rowRatioTotal = 0;
      }
    }

    applyHistoryGridRowLayout(row, { fillRow: false, availableWidth, gap, settings });
    historyGridResizeController?.commitLayout(availableWidth);
  }
  return {
    ensureHistoryTaskCardVisible,
    scheduleHistoryGridLayout,
    clampNumber,
    getCurrentHistoryLayoutWidths,
    applyHistoryLayoutWidths,
    restoreHistoryLayoutPreference,
    endHistoryResize,
    bindHistoryResizerEvents,
    bindHistoryGridResizeObserver,
    bindHistoryGridMutationObserver,
    layoutJustifiedHistoryGrid,
    dispose() { endHistoryResize(); lifetime.abort(); historyGridResizeObserver?.disconnect(); historyGridMutationObserver?.disconnect(); if (historyGridLayoutFrame) cancelAnimationFrame(historyGridLayoutFrame); if (historyResizeFrame) cancelAnimationFrame(historyResizeFrame); },
  };
}

import { LOCALE_CHANGE_EVENT, formatTranslation, restoreLocalePreference, translate } from "./i18n";
import {
  type HistoryWindowEdge,
  type HistoryWindowDirection,
  captureHistoryScrollAnchor,
  historyTaskCards,
  historyWindowEdgeCursor,
  restoreHistoryScrollAnchor,
} from "./history-window";

type HistoryFacet = { value: string; count: number };
type HistoryMonth = { month: string; count: number };
type HistorySummary = {
  total: number;
  archived_total: number;
  months: HistoryMonth[];
  prompt_modes: HistoryFacet[];
  qualities: HistoryFacet[];
  ratios: HistoryFacet[];
  orientations: HistoryFacet[];
  backends: HistoryFacet[];
  providers: HistoryFacet[];
};
type HistoryTask = {
  task_id: string;
  created_at: string;
  updated_at: string;
  completed_at: string;
  status: string;
  mode: string;
  size: string;
  quality: string;
  prompt_mode: string;
  ratio: string;
  orientation: string;
  backend: string;
  provider: string;
  archived: boolean;
  generated_count: number;
  failed_count: number;
  total_count: number;
  thumbnail_url: string;
  prompt_preview: string;
};
type HistoryFilterKey = "month" | "prompt_mode" | "quality" | "ratio" | "orientation" | "backend" | "provider" | "archived";
type HistoryViewMode = "grid" | "list";
type HistoryRenderPosition = "replace" | "append" | "prepend";
type HistoryTaskPage = { tasks: HistoryTask[]; next_cursor: string | null; previous_cursor?: string | null; detail?: string };
type HistoryContextMenuMode = "single" | "multi";

const HISTORY_FILTER_KEYS: HistoryFilterKey[] = ["month", "prompt_mode", "quality", "ratio", "orientation", "backend", "provider", "archived"];
const HISTORY_RATIO_OTHER_VALUE = "__other__";
const HISTORY_PAGE_LIMIT = 50;
const MAX_MOUNTED_TASK_CARDS = 300;
const HISTORY_REFERENCE_HANDOFF_KEY = "codex-image-history-reference-handoff";
const HISTORY_TASK_REUSE_HANDOFF_KEY = "codex-image-history-task-reuse-handoff";
const HISTORY_THEME_STORAGE_KEY = "codex-image-theme-preference";
const HISTORY_THUMBNAIL_CACHE_VERSION = "thumb-768-fit";
const HISTORY_GRID_DEFAULT_GAP = 14;

type HistoryGridLayoutSettings = {
  targetHeight: number;
  minWidth: number;
  maxWidth: number;
};

const historyState = {
  q: "",
  month: "",
  prompt_mode: "",
  quality: "",
  ratio: "",
  orientation: "",
  backend: "",
  provider: "",
  archived: "",
  sort: "newest",
  view: "grid" as HistoryViewMode,
  nextCursor: null as string | null,
  newerExhausted: true,
  loading: false,
  exhausted: false,
  loadedTaskIds: new Set<string>(),
  loadedTaskSummaries: new Map<string, HistoryTask>(),
  selectedTaskIds: new Set<string>(),
  selectedTaskId: "",
  selectionAnchorTaskId: "",
  deleteConfirming: false,
  deleteConfirmTaskId: "",
  deleteUnselectedConfirmTaskId: "",
  detailTask: null as any,
  contextMenuDeleteConfirmKey: "",
  contextMenu: {
    mode: "single" as HistoryContextMenuMode,
    taskId: "",
    taskIds: [] as string[],
    x: 0,
    y: 0,
  },
  requestId: 0,
};

let historyGridLayoutFrame = 0;
let historyContextMenuEl: HTMLElement | null = null;

const els = {
  page: document.querySelector<HTMLElement>(".history-page"),
  total: document.querySelector<HTMLElement>("#historyTotal"),
  search: document.querySelector<HTMLInputElement>("#historySearch"),
  searchClear: document.querySelector<HTMLButtonElement>("#historySearchClear"),
  monthList: document.querySelector<HTMLElement>("#historyMonthList"),
  promptModeList: document.querySelector<HTMLElement>("#historyPromptModeList"),
  qualityList: document.querySelector<HTMLElement>("#historyQualityList"),
  ratioList: document.querySelector<HTMLElement>("#historyRatioList"),
  orientationList: document.querySelector<HTMLElement>("#historyOrientationList"),
  backendList: document.querySelector<HTMLElement>("#historyBackendList"),
  providerList: document.querySelector<HTMLElement>("#historyProviderList"),
  archiveList: document.querySelector<HTMLElement>("#historyArchiveList"),
  sort: document.querySelector<HTMLSelectElement>("#historySort"),
  viewToggle: document.querySelector<HTMLElement>("#historyViewToggle"),
  resultSummary: document.querySelector<HTMLElement>("#historyResultSummary"),
  bulkToolbar: document.querySelector<HTMLElement>("#historyBulkToolbar"),
  bulkCount: document.querySelector<HTMLElement>("#historyBulkCount"),
  bulkArchive: document.querySelector<HTMLButtonElement>("#historyBulkArchiveButton"),
  bulkRestore: document.querySelector<HTMLButtonElement>("#historyBulkRestoreButton"),
  bulkDelete: document.querySelector<HTMLButtonElement>("#historyBulkDeleteButton"),
  bulkDeleteCancel: document.querySelector<HTMLButtonElement>("#historyBulkDeleteCancelButton"),
  taskList: document.querySelector<HTMLElement>("#historyTaskList"),
  detail: document.querySelector<HTMLElement>("#historyDetail"),
  sentinel: document.querySelector<HTMLElement>("[data-history-load-more]"),
  refresh: document.querySelector<HTMLButtonElement>("#historyRefreshButton"),
};

function escapeHtml(value: unknown): string {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

function formatDate(value: string): string {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value.slice(0, 16).replace("T", " ");
  return date.toLocaleString(undefined, { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" });
}

function setText(element: HTMLElement | null, text: string): void {
  if (element) element.textContent = text;
}

function normalizeHistoryThemePreference(value: unknown): "system" | "light" | "dark" {
  return value === "light" || value === "dark" ? value : "system";
}

function resolveHistoryTheme(preference: "system" | "light" | "dark"): "light" | "dark" {
  if (preference === "light" || preference === "dark") return preference;
  return window.matchMedia?.("(prefers-color-scheme: dark)")?.matches ? "dark" : "light";
}

function restoreHistoryThemePreference(): void {
  let saved = "system";
  try {
    saved = localStorage.getItem(HISTORY_THEME_STORAGE_KEY) || "system";
  } catch {
    saved = "system";
  }
  const preference = normalizeHistoryThemePreference(saved);
  document.documentElement.dataset.themePreference = preference;
  document.documentElement.dataset.theme = resolveHistoryTheme(preference);
}

function bindHistoryThemePreference(): void {
  window.matchMedia?.("(prefers-color-scheme: dark)")?.addEventListener?.("change", () => {
    if (document.documentElement.dataset.themePreference === "system") {
      restoreHistoryThemePreference();
    }
  });
}

function applyHistoryLocale(): void {
  restoreLocalePreference();
  document.title = translate("history.documentTitle");
}

function truncateText(value: unknown, limit: number): string {
  const text = String(value || "").replace(/\s+/g, " ").trim();
  return text.length <= limit ? text : text.slice(0, limit - 1).trimEnd() + "…";
}

function historyFilterAttribute(key: HistoryFilterKey): string {
  return key.replace(/_/g, "-");
}

function facetDisplayValue(key: HistoryFilterKey, value: string): string {
  if (key === "prompt_mode") {
    if (value === "strict") return translate("history.promptMode.strict");
    if (value === "original") return translate("history.promptMode.original");
    if (value === "off") return translate("history.promptMode.off");
  }
  if (key === "quality") {
    if (value === "high") return translate("history.quality.high");
    if (value === "medium") return translate("history.quality.medium");
    if (value === "low") return translate("history.quality.low");
    if (value === "auto") return translate("history.quality.auto");
  }
  if (key === "ratio" && value === HISTORY_RATIO_OTHER_VALUE) return translate("history.ratioOther");
  return value;
}

function syncStateFromUrl(): void {
  const params = new URLSearchParams(window.location.search);
  historyState.q = params.get("q") || "";
  historyState.sort = params.get("sort") === "oldest" ? "oldest" : "newest";
  historyState.view = params.get("view") === "list" ? "list" : "grid";
  for (const key of HISTORY_FILTER_KEYS) {
    historyState[key] = params.get(key) || "";
  }
  historyState.selectedTaskId = params.get("task") || "";
  if (els.search) els.search.value = historyState.q;
  if (els.sort) els.sort.value = historyState.sort;
  syncHistoryViewMode();
}

function updateHistoryUrl(): void {
  const params = new URLSearchParams();
  if (historyState.q) params.set("q", historyState.q);
  if (historyState.sort !== "newest") params.set("sort", historyState.sort);
  if (historyState.view !== "grid") params.set("view", historyState.view);
  for (const key of HISTORY_FILTER_KEYS) {
    if (historyState[key]) params.set(key, historyState[key]);
  }
  if (historyState.selectedTaskId) params.set("task", historyState.selectedTaskId);
  const query = params.toString();
  const nextUrl = query ? `${window.location.pathname}?${query}` : window.location.pathname;
  window.history.replaceState(null, "", nextUrl);
}

async function loadSummary(): Promise<void> {
  try {
    const response = await fetch("/api/task-history/summary");
    const summary = await response.json() as HistorySummary;
    if (!response.ok) throw new Error((summary as any).detail || translate("history.summaryFailed"));
    setText(els.total, formatTranslation("history.total", { total: summary.total, archived: summary.archived_total }));
    renderFacetButtons(els.monthList, "month", summary.months.map((item) => ({ value: item.month, count: item.count })), translate("history.allMonths"));
    renderFacetButtons(els.promptModeList, "prompt_mode", summary.prompt_modes || [], translate("history.allPromptModes"));
    renderFacetButtons(els.qualityList, "quality", summary.qualities || [], translate("history.allQualities"));
    renderFacetButtons(els.ratioList, "ratio", summary.ratios, translate("history.allRatios"));
    renderFacetButtons(els.orientationList, "orientation", summary.orientations || [], translate("history.allOrientations"));
    renderFacetButtons(els.backendList, "backend", summary.backends || [], translate("history.allBackends"));
    renderFacetButtons(els.providerList, "provider", summary.providers || [], translate("history.allProviders"));
    syncArchiveButtons();
  } catch (error) {
    setText(els.total, errorMessage(error, translate("history.summaryFailed")));
  }
}

function renderFacetButtons(root: HTMLElement | null, key: HistoryFilterKey, items: HistoryFacet[], allLabel: string): void {
  if (!root) return;
  const current = String(historyState[key] || "");
  const attr = historyFilterAttribute(key);
  root.innerHTML = [
    `<button class="history-filter-button ${current ? "" : "active"}" type="button" data-history-${attr}="">${escapeHtml(allLabel)}</button>`,
    ...items.map((item) => {
      const active = current === item.value ? " active" : "";
      return `<button class="history-filter-button${active}" type="button" data-history-${attr}="${escapeHtml(item.value)}">${escapeHtml(facetDisplayValue(key, item.value))} <span>${item.count}</span></button>`;
    }),
  ].join("");
}

function syncArchiveButtons(): void {
  document.querySelectorAll<HTMLElement>("[data-history-archived]").forEach((button) => {
    button.classList.toggle("active", button.getAttribute("data-history-archived") === historyState.archived);
  });
}

function queryParams(cursor?: string | null, direction: HistoryWindowDirection = "next"): string {
  const params = new URLSearchParams();
  params.set("limit", String(HISTORY_PAGE_LIMIT));
  params.set("sort", historyState.sort);
  if (cursor) params.set("cursor", cursor);
  if (direction !== "next") params.set("direction", direction);
  if (historyState.q) params.set("q", historyState.q);
  for (const key of HISTORY_FILTER_KEYS) {
    if (historyState[key]) params.set(key, historyState[key]);
  }
  return params.toString();
}

function syncHistoryViewMode(): void {
  const view = historyState.view === "list" ? "list" : "grid";
  historyState.view = view;
  els.taskList?.classList.toggle("history-view-grid", view === "grid");
  els.taskList?.classList.toggle("history-view-list", view === "list");
  els.viewToggle?.querySelectorAll<HTMLElement>("[data-history-view]").forEach((button) => {
    const active = button.dataset.historyView === view;
    button.classList.toggle("active", active);
    button.setAttribute("aria-pressed", active ? "true" : "false");
  });
  if (view === "grid") scheduleHistoryGridLayout();
}

function setHistoryViewMode(view: string): void {
  historyState.view = view === "list" ? "list" : "grid";
  syncHistoryViewMode();
  updateHistoryUrl();
}

function historyGridLayoutSettings(): HistoryGridLayoutSettings {
  if (window.matchMedia("(max-width: 760px)").matches) {
    return { targetHeight: 176, minWidth: 132, maxWidth: 320 };
  }
  return { targetHeight: 220, minWidth: 150, maxWidth: 430 };
}

function scheduleHistoryGridLayout(): void {
  if (historyGridLayoutFrame) window.cancelAnimationFrame(historyGridLayoutFrame);
  historyGridLayoutFrame = window.requestAnimationFrame(() => {
    historyGridLayoutFrame = 0;
    layoutJustifiedHistoryGrid();
  });
}

function parseCssPixels(value: string): number {
  const parsed = Number.parseFloat(value);
  return Number.isFinite(parsed) ? parsed : 0;
}

function clampNumber(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
}

function historyTaskCardRatio(card: HTMLElement): number {
  const ratio = Number.parseFloat(card.style.getPropertyValue("--history-task-card-ratio"));
  return Number.isFinite(ratio) && ratio > 0 ? clampNumber(ratio, 0.42, 3.2) : 1;
}

function applyHistoryGridRowLayout(
  row: Array<{ card: HTMLElement; ratio: number }>,
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

function layoutJustifiedHistoryGrid(): void {
  const root = els.taskList;
  if (!root || historyState.view !== "grid" || !root.classList.contains("history-view-grid")) return;
  const cards = historyTaskCards(root);
  if (!cards.length) return;
  const rootStyle = window.getComputedStyle(root);
  const availableWidth = root.clientWidth
    - parseCssPixels(rootStyle.paddingLeft)
    - parseCssPixels(rootStyle.paddingRight);
  if (availableWidth < 80) return;
  const gap = parseCssPixels(rootStyle.columnGap || rootStyle.gap) || HISTORY_GRID_DEFAULT_GAP;
  const settings = historyGridLayoutSettings();
  let row: Array<{ card: HTMLElement; ratio: number }> = [];
  let rowRatioTotal = 0;

  for (const card of cards) {
    const ratio = historyTaskCardRatio(card);
    row.push({ card, ratio });
    rowRatioTotal += ratio;
    const projectedWidth = (rowRatioTotal * settings.targetHeight) + (gap * Math.max(0, row.length - 1));
    if (row.length > 1 && projectedWidth >= availableWidth) {
      applyHistoryGridRowLayout(row, { fillRow: true, availableWidth, gap, settings });
      row = [];
      rowRatioTotal = 0;
    }
  }

  applyHistoryGridRowLayout(row, { fillRow: false, availableWidth, gap, settings });
}

function setLoadMoreState(label: string, options: { hidden?: boolean; busy?: boolean } = {}): void {
  if (!els.sentinel) return;
  els.sentinel.textContent = label;
  els.sentinel.hidden = Boolean(options.hidden);
  els.sentinel.toggleAttribute("aria-busy", Boolean(options.busy));
}

function maybeLoadMoreFromScroll(): void {
  if (!els.taskList || historyState.loading) return;
  if (els.taskList.scrollTop <= 320 && !historyState.newerExhausted) {
    void loadTasks({ direction: "previous" });
    return;
  }
  const remaining = els.taskList.scrollHeight - els.taskList.scrollTop - els.taskList.clientHeight;
  if (remaining <= 320 && !historyState.exhausted) void loadTasks({ direction: "next" });
}

async function loadTasks({ reset = false, direction = "next" }: { reset?: boolean; direction?: HistoryWindowDirection } = {}): Promise<void> {
  if (historyState.loading) return;
  if (!reset && direction === "next" && historyState.exhausted) return;
  if (!reset && direction === "previous" && historyState.newerExhausted) return;
  const cursor = taskWindowCursor(reset, direction);
  if (!reset && !cursor) {
    if (direction === "previous") historyState.newerExhausted = true;
    if (direction === "next") historyState.exhausted = true;
    return;
  }
  historyState.loading = true;
  const requestId = ++historyState.requestId;
  if (reset) {
    historyState.nextCursor = null;
    historyState.newerExhausted = true;
    historyState.exhausted = false;
    historyState.loadedTaskIds.clear();
    historyState.loadedTaskSummaries.clear();
    historyState.selectedTaskIds.clear();
    historyState.selectionAnchorTaskId = "";
    historyState.deleteConfirming = false;
    historyState.deleteConfirmTaskId = "";
    historyState.contextMenuDeleteConfirmKey = "";
    if (els.taskList) els.taskList.innerHTML = "";
    renderBulkToolbar();
  }
  setLoadMoreState(translate("history.loadingMore"), { busy: true });
  try {
    const response = await fetch(`/api/task-history/tasks?${queryParams(cursor, direction)}`);
    const data = await response.json() as HistoryTaskPage;
    if (!response.ok) throw new Error(data.detail || translate("history.tasksFailed"));
    if (requestId !== historyState.requestId) return;
    const tasks = data.tasks || [];
    renderTasks(tasks, { position: reset ? "replace" : direction === "previous" ? "prepend" : "append" });
    if (direction === "previous") {
      historyState.newerExhausted = !data.previous_cursor || !tasks.length;
    } else {
      historyState.nextCursor = data.next_cursor || null;
      historyState.exhausted = !historyState.nextCursor;
      if (reset) historyState.newerExhausted = true;
    }
    setLoadMoreState(
      historyState.exhausted ? translate("history.noMore") : "",
      { hidden: !historyState.exhausted, busy: false },
    );
    window.requestAnimationFrame(maybeLoadMoreFromScroll);
  } catch (error) {
    if (requestId === historyState.requestId) {
      const message = errorMessage(error, translate("history.tasksFailed"));
      if (els.taskList && historyTaskCards(els.taskList).length) {
        setText(els.resultSummary, message);
      } else {
        renderTaskListMessage("history-error", message);
      }
    }
    if (direction === "previous") {
      historyState.newerExhausted = false;
    } else {
      historyState.exhausted = false;
    }
    setLoadMoreState(translate("history.loadFailed"));
  } finally {
    if (requestId === historyState.requestId) historyState.loading = false;
  }
}

function taskWindowCursor(reset: boolean, direction: HistoryWindowDirection): string | null {
  if (reset || !els.taskList) return null;
  if (direction === "previous") return historyWindowEdgeCursor(els.taskList, "top");
  return historyState.nextCursor || historyWindowEdgeCursor(els.taskList, "bottom");
}

function renderTasks(tasks: HistoryTask[], { position }: { position: HistoryRenderPosition }): void {
  if (!els.taskList) return;
  syncHistoryViewMode();
  const anchor = position === "replace" ? null : captureHistoryScrollAnchor(els.taskList);
  if (position === "replace") els.taskList.innerHTML = "";
  const uniqueTasks = tasks
    .filter((task) => {
      if (historyState.loadedTaskIds.has(task.task_id)) return false;
      historyState.loadedTaskIds.add(task.task_id);
      historyState.loadedTaskSummaries.set(task.task_id, task);
      return true;
    });
  const html = uniqueTasks.map(taskCardHtml).join("");
  if (html) {
    els.taskList.querySelector(".history-empty, .history-error")?.remove();
    if (position === "prepend") {
      els.taskList.insertAdjacentHTML("afterbegin", html);
    } else {
      els.taskList.insertAdjacentHTML("beforeend", html);
    }
  }
  trimMountedTaskCards(position === "prepend" ? "bottom" : "top");
  layoutJustifiedHistoryGrid();
  restoreHistoryScrollAnchor(els.taskList, anchor);
  if (!els.taskList.querySelector(".history-task-card")) {
    renderTaskListMessage("history-empty", translate("history.noMatches"));
  }
  setText(els.resultSummary, formatTranslation("history.loadedCount", { count: historyState.loadedTaskIds.size }));
  updateTaskSelectionVisuals();
}

function renderTaskListMessage(className: string, message: string): void {
  if (!els.taskList) return;
  els.taskList.innerHTML = `<div class="${className}">${escapeHtml(message)}</div>`;
}

function trimMountedTaskCards(edge: HistoryWindowEdge): void {
  if (!els.taskList) return;
  const cards = historyTaskCards(els.taskList);
  const overflow = cards.length - MAX_MOUNTED_TASK_CARDS;
  if (overflow <= 0) return;
  const removedCards = edge === "bottom" ? cards.slice(cards.length - overflow) : cards.slice(0, overflow);
  for (const card of removedCards) {
    const taskId = card.dataset.historyTaskCardId || "";
    historyState.loadedTaskIds.delete(taskId);
    historyState.loadedTaskSummaries.delete(taskId);
    historyState.selectedTaskIds.delete(taskId);
    if (historyState.selectionAnchorTaskId === taskId) historyState.selectionAnchorTaskId = "";
    card.remove();
  }
  if (edge === "top") {
    historyState.newerExhausted = false;
  } else {
    historyState.exhausted = false;
    historyState.nextCursor = historyWindowEdgeCursor(els.taskList, "bottom") || historyState.nextCursor;
  }
  els.taskList.querySelector(".history-window-notice")?.remove();
}

function taskCardHtml(task: HistoryTask): string {
  const taskId = escapeHtml(task.task_id);
  const thumbnailUrl = historyThumbnailUrl(task);
  const ratioStyle = historyThumbnailRatioStyle(task);
  const thumb = thumbnailUrl
    ? `<img src="${escapeHtml(thumbnailUrl)}" alt="" loading="lazy" decoding="async" draggable="false">`
    : "";
  const counts = `${task.generated_count || 0}/${task.total_count || 0}`;
  const selected = historyState.selectedTaskIds.has(task.task_id);
  const active = historyState.selectedTaskId === task.task_id;
  const source = task.backend || task.provider || "";
  const promptMode = facetDisplayValue("prompt_mode", task.prompt_mode || "");
  const quality = facetDisplayValue("quality", task.quality || "");
  const metaItems = [
    { kind: "date", value: formatDate(task.created_at) },
    { kind: "status", value: task.status },
    { kind: "size", value: formatHistorySizeLabel(task.size || task.ratio || task.orientation || "") },
    { kind: "prompt-mode", value: promptMode },
    { kind: "quality", value: quality },
    { kind: "source", value: source },
    { kind: "count", value: counts },
  ].filter((item) => item.value);
  return `
    <article
      class="history-task-card${active ? " active" : ""}${selected ? " selected" : ""}"
      data-history-task-card-id="${taskId}"
      data-history-created-at="${escapeHtml(task.created_at)}"
      role="option"
      aria-selected="${active ? "true" : "false"}"
      ${ratioStyle}
    >
      <label class="history-task-select" aria-label="${escapeHtml(translate("history.selectTask"))}">
        <input type="checkbox" data-history-task-select="${taskId}" ${selected ? "checked" : ""}>
      </label>
      <span class="history-task-active-badge" aria-hidden="${active ? "false" : "true"}">${escapeHtml(translate("history.viewing"))}</span>
      <button class="history-task-open" type="button" data-history-task-id="${taskId}">
        <span class="history-task-thumb">${thumb}</span>
        <span class="history-task-copy">
          <span class="history-task-title">${escapeHtml(task.prompt_preview || task.mode || task.task_id)}</span>
          <span class="history-task-meta">
            ${metaItems.map((item) => `<span data-history-meta-kind="${escapeHtml(item.kind)}">${escapeHtml(item.value)}</span>`).join("")}
          </span>
        </span>
      </button>
    </article>
  `;
}

function historyThumbnailRatioStyle(task: HistoryTask): string {
  const fromSize = parseAspectRatioParts(task.size, "x");
  const fromRatio = fromSize || parseAspectRatioParts(task.ratio, ":");
  if (!fromRatio) return "";
  const [width, height] = fromRatio;
  const ratio = Math.min(3.2, Math.max(0.42, width / height));
  return `style="--history-task-thumb-ratio: ${width} / ${height}; --history-task-card-ratio: ${ratio.toFixed(4)}"`;
}

function parseAspectRatioParts(value: unknown, separator: "x" | ":"): [number, number] | null {
  const text = String(value || "").trim().toLowerCase();
  const pattern = separator === "x" ? /^(\d+)\s*x\s*(\d+)$/ : /^(\d+)\s*:\s*(\d+)$/;
  const match = text.match(pattern);
  if (!match) return null;
  const width = Number.parseInt(match[1] || "", 10);
  const height = Number.parseInt(match[2] || "", 10);
  if (!Number.isFinite(width) || !Number.isFinite(height) || width <= 0 || height <= 0) return null;
  return [width, height];
}

function formatHistorySizeLabel(value: unknown): string {
  return String(value || "").trim().replace(/^(\d+)\s*x\s*(\d+)$/i, "$1 x $2");
}

function historyThumbnailUrl(task: HistoryTask): string {
  const url = String(task.thumbnail_url || "");
  if (!url) return "";
  const staticThumbMatch = url.match(/(?:^|\/)(\d{14}-[a-f0-9]+)-image-(\d+)-thumb\.[a-z0-9]+(?:[?#].*)?$/i);
  if (url.includes("/outputs/thumbnails/") && staticThumbMatch && staticThumbMatch[1] === task.task_id) {
    const outputIndex = staticThumbMatch[2] || "1";
    return versionHistoryThumbnailUrl(`/api/tasks/${encodeURIComponent(task.task_id)}/outputs/${encodeURIComponent(outputIndex)}/thumbnail`);
  }
  return versionHistoryThumbnailUrl(url);
}

function versionHistoryThumbnailUrl(url: string): string {
  if (!url.startsWith("/api/tasks/") || !url.includes("/thumbnail")) return url;
  const separator = url.includes("?") ? "&" : "?";
  return `${url}${separator}v=${HISTORY_THUMBNAIL_CACHE_VERSION}`;
}

function updateTaskSelectionVisuals(taskId = historyState.selectedTaskId): void {
  els.taskList?.querySelectorAll<HTMLElement>(".history-task-card").forEach((card) => {
    const cardTaskId = card.dataset.historyTaskCardId || "";
    const active = Boolean(taskId && cardTaskId === taskId);
    const selected = historyState.selectedTaskIds.has(cardTaskId);
    card.classList.toggle("active", active);
    card.classList.toggle("selected", selected);
    card.setAttribute("aria-selected", active ? "true" : "false");
    const activeBadge = card.querySelector<HTMLElement>(".history-task-active-badge");
    activeBadge?.setAttribute("aria-hidden", active ? "false" : "true");
    const input = card.querySelector<HTMLInputElement>("[data-history-task-select]");
    if (input) input.checked = selected;
  });
}

function visibleHistoryTaskIds(): string[] {
  return Array.from(els.taskList?.querySelectorAll<HTMLElement>(".history-task-card[data-history-task-card-id]") || [])
    .map((card) => String(card.dataset.historyTaskCardId || ""))
    .filter(Boolean);
}

function applyHistoryTaskSelection(taskIds: string[], anchorTaskId = ""): void {
  historyState.selectedTaskIds = new Set(taskIds.filter(Boolean));
  if (anchorTaskId) historyState.selectionAnchorTaskId = anchorTaskId;
  historyState.deleteConfirming = false;
  historyState.contextMenuDeleteConfirmKey = "";
  updateTaskSelectionVisuals();
  renderBulkToolbar();
}

function clearHistoryTaskSelection({ updateVisuals = true } = {}): void {
  if (!historyState.selectedTaskIds.size && !historyState.selectionAnchorTaskId && !historyState.deleteConfirming) return;
  historyState.selectedTaskIds.clear();
  historyState.selectionAnchorTaskId = "";
  historyState.deleteConfirming = false;
  historyState.contextMenuDeleteConfirmKey = "";
  if (updateVisuals) updateTaskSelectionVisuals();
  renderBulkToolbar();
}

function toggleHistoryTaskSelection(taskId: string, anchor = true): void {
  if (!taskId) return;
  const next = new Set(historyState.selectedTaskIds);
  if (next.has(taskId)) {
    next.delete(taskId);
  } else {
    next.add(taskId);
  }
  historyState.selectedTaskIds = next;
  if (anchor) historyState.selectionAnchorTaskId = taskId;
  historyState.deleteConfirming = false;
  historyState.contextMenuDeleteConfirmKey = "";
  updateTaskSelectionVisuals();
  renderBulkToolbar();
}

function selectHistoryTaskRange(anchorTaskId: string, taskId: string): void {
  if (!taskId) return;
  const visibleIds = visibleHistoryTaskIds();
  const fallbackAnchor = historyState.selectionAnchorTaskId || historyState.selectedTaskId || taskId;
  const anchor = anchorTaskId || fallbackAnchor;
  const anchorIndex = visibleIds.indexOf(anchor);
  const targetIndex = visibleIds.indexOf(taskId);
  if (anchorIndex < 0 || targetIndex < 0) {
    applyHistoryTaskSelection([...historyState.selectedTaskIds, taskId], taskId);
    return;
  }
  const [start, end] = anchorIndex <= targetIndex ? [anchorIndex, targetIndex] : [targetIndex, anchorIndex];
  applyHistoryTaskSelection([...historyState.selectedTaskIds, ...visibleIds.slice(start, end + 1)], anchor);
}

function handleHistoryTaskShortcutSelection(taskId: string, event: MouseEvent | KeyboardEvent): boolean {
  if (!taskId || (!event.shiftKey && !event.metaKey && !event.ctrlKey)) return false;
  event.preventDefault();
  event.stopPropagation();
  if (event.shiftKey) {
    selectHistoryTaskRange(historyState.selectionAnchorTaskId || historyState.selectedTaskId || taskId, taskId);
    return true;
  }
  toggleHistoryTaskSelection(taskId);
  return true;
}

async function loadTaskDetail(taskId: string): Promise<void> {
  if (!taskId) return;
  historyState.selectedTaskId = taskId;
  historyState.deleteConfirming = false;
  historyState.deleteConfirmTaskId = "";
  historyState.deleteUnselectedConfirmTaskId = "";
  updateHistoryUrl();
  updateTaskSelectionVisuals(taskId);
  els.page?.classList.add("history-detail-open");
  renderDetailShell(translate("history.loadingDetail"));
  try {
    renderTaskDetail(await fetchHistoryTaskDetail(taskId));
  } catch (error) {
    renderDetailShell(errorMessage(error, translate("history.detailFailed")), "history-error");
  }
}

async function fetchHistoryTaskDetail(taskId: string): Promise<any> {
  const response = await fetch(`/api/tasks/${encodeURIComponent(taskId)}`);
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.detail || translate("history.detailFailed"));
  return data.task || {};
}

function renderDetailShell(message: string, className = "history-detail-empty"): void {
  if (!els.detail) return;
  els.detail.innerHTML = `
    <div class="history-detail-header">
      <div>
        <p class="history-detail-kicker">${escapeHtml(translate("history.detail"))}</p>
        <h2 class="history-detail-title">${escapeHtml(translate("history.detailTitle"))}</h2>
      </div>
      <button id="historyDetailClose" class="drawer-close-button history-detail-close" type="button" data-history-detail-close aria-label="${escapeHtml(translate("history.closeDetail"))}">×</button>
    </div>
    <div class="${className}">${escapeHtml(message)}</div>
  `;
}

function historyTaskModeLabel(mode: unknown): string {
  const value = String(mode || "");
  if (value === "generate") return translate("taskMode.generate");
  if (value === "edit") return translate("taskMode.edit");
  return value || translate("history.detail");
}

function renderTaskDetail(task: any): void {
  if (!els.detail) return;
  historyState.detailTask = task;
  const taskId = String(task.task_id || historyState.selectedTaskId || "");
  const urls = taskOutputRecords(task);
  const selectedCount = taskSelectedOutputIndexes(task).size;
  const images = urls.map((record, index) => historyDetailImageHtml(taskId, record, index, selectedCount)).join("");
  const zipHref = `/api/tasks/${encodeURIComponent(taskId)}/outputs.zip`;
  const canZip = urls.length > 1;
  const canDeleteUnselected = selectedCount > 0 && selectedCount < urls.length;
  const confirmingDeleteUnselected = historyState.deleteUnselectedConfirmTaskId === taskId;
  const archived = historyTaskArchived(task);
  const confirmingDeleteTask = historyState.deleteConfirmTaskId === taskId;
  const deleteBlocked = historyTaskDeleteBlocked(task);
  const title = detailTitle(task);
  els.detail.innerHTML = `
    <div class="history-detail-header">
      <div>
        <p class="history-detail-kicker">${escapeHtml(historyTaskModeLabel(task.mode))}</p>
        <h2 class="history-detail-title" title="${escapeHtml(task.prompt || title)}">${escapeHtml(title)}</h2>
      </div>
      <button id="historyDetailClose" class="drawer-close-button history-detail-close" type="button" data-history-detail-close aria-label="${escapeHtml(translate("history.closeDetail"))}">×</button>
    </div>
    <div class="history-detail-meta">
      <span>${escapeHtml(formatDate(task.created_at || ""))}</span>
      <span>${escapeHtml(task.status || "")}</span>
      <span>${escapeHtml(task.params?.size || task.output_size || "")}</span>
      <span>${escapeHtml(facetDisplayValue("prompt_mode", task.params?.prompt_fidelity || ""))}</span>
      <span>${escapeHtml(facetDisplayValue("quality", task.params?.quality || task.quality || ""))}</span>
      <span>${escapeHtml(task.backend || task.api_provider_name || "")}</span>
    </div>
    <div class="history-detail-actions">
      <button class="ghost-button text-sm" type="button" data-history-reuse-task="${escapeHtml(taskId)}">${escapeHtml(translate("history.reuseTask"))}</button>
      <button class="ghost-button text-sm" type="button" data-history-archive-task="${escapeHtml(taskId)}" data-history-archive-value="${archived ? "false" : "true"}">${escapeHtml(archived ? translate("archive.restore") : translate("action.archive"))}</button>
      <button class="ghost-button text-sm danger-button" type="button" data-history-delete-task="${escapeHtml(taskId)}" ${deleteBlocked ? "disabled" : ""}>${escapeHtml(confirmingDeleteTask ? translate("history.confirmDelete") : translate("action.delete"))}</button>
      ${canZip ? `<a class="ghost-button text-sm" href="${escapeHtml(zipHref)}" download>${escapeHtml(translate("history.downloadAll"))}</a>` : ""}
      ${selectedCount > 1 ? `<a class="ghost-button text-sm" href="${escapeHtml(zipHref)}?selected=1" download>${escapeHtml(translate("history.downloadSelected"))}</a>` : ""}
      ${canDeleteUnselected ? `<button class="ghost-button text-sm danger-button" type="button" data-history-delete-unselected="${escapeHtml(taskId)}">${escapeHtml(confirmingDeleteUnselected ? translate("history.confirmDeleteUnselected") : translate("history.deleteUnselected"))}</button>` : ""}
      ${confirmingDeleteUnselected ? `<button class="ghost-button text-sm" type="button" data-history-delete-unselected-cancel>${escapeHtml(translate("action.cancel"))}</button>` : ""}
    </div>
    <div class="history-detail-images">${images || `<div class="history-detail-empty">${escapeHtml(translate("history.noPreview"))}</div>`}</div>
    ${promptCompareHtml(task)}
  `;
}

function detailTitle(task: any): string {
  return truncateText(task.prompt_preview || task.prompt || task.mode || task.task_id || translate("history.untitled"), 120);
}

function historyTaskArchived(task: any): boolean {
  return Boolean(task?.archived || task?.archived_at);
}

function historyTaskDeleteBlocked(task: any): boolean {
  const status = String(task?.status || "");
  return Boolean(task?.local_pending || status === "running" || status === "submitting" || status === "queued");
}

function historyTaskGeneratedCount(task: any): number {
  const generated = positiveInt(task?.generated_count);
  if (generated !== null) return generated;
  const outputs = Array.isArray(task?.outputs) ? task.outputs.filter((output: any) => output && !output.deleted && output.status !== "failed") : [];
  if (outputs.length) return outputs.length;
  if (Array.isArray(task?.output_urls)) return task.output_urls.filter(Boolean).length;
  return task?.output_url ? 1 : 0;
}

function historyTaskSummary(taskId: string): HistoryTask | null {
  return historyState.loadedTaskSummaries.get(taskId) || null;
}

function historyTaskPromptForClipboard(task: any): string {
  return String(task?.prompt || task?.prompt_preview || task?.prompt_for_model || "").trim();
}

function taskOutputRecords(task: any): Array<{ url: string; index: number; selected: boolean; revisedPrompt: string }> {
  const selectedIndexes = taskSelectedOutputIndexes(task);
  const records: Array<{ url: string; index: number; selected: boolean; revisedPrompt: string }> = [];
  const outputs = Array.isArray(task.outputs) ? task.outputs : [];
  outputs.forEach((output: any, fallbackIndex: number) => {
    if (!output || output.deleted || output.status === "deleted") return;
    const url = String(output.url || output.output_url || "");
    if (!url || output.status === "failed") return;
    const outputIndex = positiveInt(output.index) || fallbackIndex + 1;
    records.push({
      url,
      index: outputIndex,
      selected: selectedIndexes.has(outputIndex),
      revisedPrompt: String(output.revised_prompt || ""),
    });
  });
  if (records.length) return records;
  const urls = Array.isArray(task.output_urls) ? task.output_urls : (task.output_url ? [task.output_url] : []);
  return urls
    .filter(Boolean)
    .map((url: string, index: number) => {
      const outputIndex = index + 1;
      return {
        url: String(url),
        index: outputIndex,
        selected: selectedIndexes.has(outputIndex),
        revisedPrompt: String(task.revised_prompts?.[index] || task.revised_prompt || ""),
      };
    });
}

function historyDetailImageHtml(
  taskId: string,
  record: { url: string; index: number; selected: boolean; revisedPrompt: string },
  index: number,
  selectedCount: number,
): string {
  const selectedClass = record.selected ? " selected" : "";
  const selectedText = record.selected ? translate("history.selected") : translate("history.select");
  return `
    <div class="history-detail-image${selectedClass}">
      <button
        class="history-detail-image-preview"
        type="button"
        data-history-lightbox-url="${escapeHtml(record.url)}"
        aria-label="${escapeHtml(translate("history.openPreview"))}"
      >
        <img src="${escapeHtml(record.url)}" alt="" loading="lazy" decoding="async">
      </button>
      <div class="history-detail-image-actions">
        <button
          class="ghost-button text-sm"
          type="button"
          aria-pressed="${record.selected ? "true" : "false"}"
          data-history-output-selected-task-id="${escapeHtml(taskId)}"
          data-history-output-selected-index="${record.index}"
        >${selectedText}</button>
        <a class="ghost-button text-sm" href="${escapeHtml(record.url)}" download>${escapeHtml(formatTranslation("history.downloadIndex", { index: index + 1 }))}</a>
        <button class="ghost-button text-sm" type="button" data-history-reference-handoff-url="${escapeHtml(record.url)}">${escapeHtml(translate("history.addReference"))}</button>
        ${selectedCount === 1 && record.selected ? `<a class="ghost-button text-sm" href="${escapeHtml(record.url)}" download>${escapeHtml(translate("history.downloadSelected"))}</a>` : ""}
      </div>
    </div>
  `;
}

function taskSelectedOutputIndexes(task: any): Set<number> {
  const indexes = new Set<number>();
  if (Array.isArray(task.selected_output_indexes)) {
    task.selected_output_indexes.forEach((value: any) => {
      const index = positiveInt(value);
      if (index !== null) indexes.add(index);
    });
  }
  return indexes;
}

function promptCompareHtml(task: any): string {
  const originalPrompt = promptTextValue(task.prompt || "");
  const submittedPrompt = promptTextValue(task.prompt_for_model || "");
  const revisedPrompt = revisedPromptText(task);
  const seen = new Set<string>();
  const panels: string[] = [];
  const addPanel = (kind: string, title: string, text: string): boolean => {
    const value = promptTextValue(text);
    const key = normalizePromptForCompare(value);
    if (!key || seen.has(key)) return false;
    seen.add(key);
    panels.push(promptPanelHtml(kind, title, value));
    return true;
  };

  addPanel("original", translate("history.promptOriginal"), originalPrompt);
  const hasRevisedPanel = addPanel("revised", translate("history.promptRevised"), revisedPrompt);
  if (!hasRevisedPanel) {
    addPanel("submitted", translate("history.promptSubmitted"), submittedPrompt);
  }
  return panels.length ? `<section class="history-prompt-compare" aria-label="${escapeHtml(translate("history.promptCompare"))}">${panels.join("")}</section>` : "";
}

function promptTextValue(value: unknown): string {
  return String(value || "").trim();
}

function normalizePromptForCompare(value: string): string {
  return promptTextValue(value).replace(/\s+/g, " ").trim();
}

function uniquePromptTexts(values: unknown[]): string[] {
  const seen = new Set<string>();
  const result: string[] = [];
  values.forEach((value) => {
    const text = promptTextValue(value);
    const key = normalizePromptForCompare(text);
    if (!key || seen.has(key)) return;
    seen.add(key);
    result.push(text);
  });
  return result;
}

function revisedPromptText(task: any): string {
  const values: unknown[] = [];
  if (Array.isArray(task.revised_prompts)) values.push(...task.revised_prompts);
  if (task.revised_prompt) values.push(task.revised_prompt);
  if (Array.isArray(task.outputs)) {
    task.outputs.forEach((output: any) => {
      if (output?.revised_prompt) values.push(output.revised_prompt);
    });
  }
  return uniquePromptTexts(values).join("\n\n");
}

function promptPanelHtml(kind: string, title: string, text: string): string {
  return `
    <article class="history-prompt-panel">
      <div class="history-prompt-panel-header">
        <h3>${escapeHtml(title)}</h3>
        <button
          class="ghost-button text-sm history-prompt-copy"
          type="button"
          data-history-copy-prompt-kind="${escapeHtml(kind)}"
          aria-label="${escapeHtml(formatTranslation("history.copyPromptPanel", { title }))}"
        >${escapeHtml(translate("history.copyPromptShort"))}</button>
      </div>
      <div class="history-detail-prompt">${escapeHtml(text || translate("history.promptEmpty"))}</div>
    </article>
  `;
}

function positiveInt(value: unknown): number | null {
  const parsed = Number.parseInt(String(value ?? ""), 10);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : null;
}

function applyFilter(key: HistoryFilterKey, value: string): void {
  historyState[key] = value;
  historyState.selectedTaskId = "";
  historyState.deleteConfirming = false;
  const attr = historyFilterAttribute(key);
  document.querySelectorAll(`[data-history-${attr}]`).forEach((node) => {
    node.classList.toggle("active", (node as HTMLElement).getAttribute(`data-history-${attr}`) === value);
  });
  updateHistoryUrl();
  void loadTasks({ reset: true });
}

function renderBulkToolbar(): void {
  if (!els.bulkToolbar || !els.bulkCount) return;
  const count = historyState.selectedTaskIds.size;
  els.page?.classList.toggle("history-bulk-selecting", count > 0);
  els.bulkToolbar.classList.toggle("hidden", count === 0);
  els.bulkToolbar.toggleAttribute("hidden", count === 0);
  els.bulkCount.textContent = count ? formatTranslation("history.selectedCount", { count }) : "";
  if (els.bulkDelete) {
    els.bulkDelete.textContent = historyState.deleteConfirming ? translate("history.confirmDelete") : translate("action.delete");
    els.bulkDelete.classList.toggle("danger-button", historyState.deleteConfirming);
  }
  els.bulkDeleteCancel?.classList.toggle("hidden", !historyState.deleteConfirming);
}

async function setTaskArchiveState(taskId: string, archived: boolean): Promise<any> {
  const response = await fetch(`/api/tasks/${encodeURIComponent(taskId)}/archive`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ archived }),
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.detail || (archived ? translate("taskActions.archiveFailed") : translate("archive.restoreFailed")));
  return data.task || null;
}

async function archiveSelectedTasks(archived: boolean): Promise<void> {
  await archiveHistoryTaskIds([...historyState.selectedTaskIds], archived);
}

async function archiveHistoryTaskIds(ids: string[], archived: boolean): Promise<void> {
  if (!ids.length) return;
  setText(els.resultSummary, archived ? translate("archive.archiving") : translate("archive.restoring"));
  try {
    await Promise.all(ids.map((taskId) => setTaskArchiveState(taskId, archived)));
    ids.forEach((taskId) => historyState.selectedTaskIds.delete(taskId));
    historyState.deleteConfirming = false;
    historyState.contextMenuDeleteConfirmKey = "";
    await loadSummary();
    await loadTasks({ reset: true });
    setText(els.resultSummary, archived ? formatTranslation("batch.archivedCount", { count: ids.length }) : formatTranslation("archive.restoredCount", { count: ids.length }));
  } catch (error) {
    setText(els.resultSummary, errorMessage(error, archived ? translate("taskActions.archiveFailed") : translate("archive.restoreFailed")));
  } finally {
    renderBulkToolbar();
  }
}

async function archiveSingleTask(taskId: string, archived: boolean): Promise<void> {
  if (!taskId) return;
  setText(els.resultSummary, archived ? translate("archive.archiving") : translate("archive.restoring"));
  try {
    const task = await setTaskArchiveState(taskId, archived);
    historyState.deleteConfirmTaskId = "";
    historyState.contextMenuDeleteConfirmKey = "";
    if (String(historyState.detailTask?.task_id || "") === taskId && task) {
      historyState.detailTask = task;
      renderTaskDetail(task);
    }
    await loadSummary();
    await loadTasks({ reset: true });
    setText(els.resultSummary, archived ? translate("taskActions.archived") : translate("archive.restored"));
  } catch (error) {
    setText(els.resultSummary, errorMessage(error, archived ? translate("taskActions.archiveFailed") : translate("archive.restoreFailed")));
  }
}

async function deleteSelectedTasks(): Promise<void> {
  const ids = [...historyState.selectedTaskIds];
  if (!ids.length) return;
  if (!historyState.deleteConfirming) {
    historyState.deleteConfirming = true;
    renderBulkToolbar();
    return;
  }
  setText(els.resultSummary, translate("archive.deleting"));
  try {
    for (const taskId of ids) {
      const response = await fetch(`/api/tasks/${encodeURIComponent(taskId)}`, { method: "DELETE" });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(data.detail || translate("taskActions.deleteFailed"));
    }
    historyState.selectedTaskIds.clear();
    historyState.deleteConfirming = false;
    historyState.contextMenuDeleteConfirmKey = "";
    await loadSummary();
    await loadTasks({ reset: true });
    setText(els.resultSummary, formatTranslation("batch.deletedCount", { count: ids.length, skipped: "" }));
  } catch (error) {
    setText(els.resultSummary, errorMessage(error, translate("taskActions.deleteFailed")));
  } finally {
    renderBulkToolbar();
  }
}

async function deleteSingleHistoryTask(taskId: string, { confirmInMenu = false }: { confirmInMenu?: boolean } = {}): Promise<boolean> {
  if (!taskId) return false;
  const confirmKey = `task:${taskId}`;
  const confirmed = confirmInMenu ? historyState.contextMenuDeleteConfirmKey === confirmKey : historyState.deleteConfirmTaskId === taskId;
  if (!confirmed) {
    historyState.deleteConfirmTaskId = taskId;
    if (confirmInMenu) historyState.contextMenuDeleteConfirmKey = confirmKey;
    if (String(historyState.detailTask?.task_id || "") === taskId) renderTaskDetail(historyState.detailTask);
    if (confirmInMenu) rerenderHistoryContextMenu();
    return false;
  }
  setText(els.resultSummary, translate("archive.deleting"));
  try {
    const response = await fetch(`/api/tasks/${encodeURIComponent(taskId)}`, { method: "DELETE" });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.detail || translate("taskActions.deleteFailed"));
    historyState.selectedTaskIds.delete(taskId);
    historyState.loadedTaskIds.delete(taskId);
    historyState.loadedTaskSummaries.delete(taskId);
    historyState.deleteConfirmTaskId = "";
    historyState.contextMenuDeleteConfirmKey = "";
    if (historyState.selectedTaskId === taskId) {
      historyState.selectedTaskId = "";
      historyState.detailTask = null;
      els.page?.classList.remove("history-detail-open");
      updateHistoryUrl();
      renderDetailShell(translate("history.detailEmpty"));
    }
    await loadSummary();
    await loadTasks({ reset: true });
    setText(els.resultSummary, translate("taskActions.deleted"));
    return true;
  } catch (error) {
    setText(els.resultSummary, errorMessage(error, translate("taskActions.deleteFailed")));
    return false;
  } finally {
    renderBulkToolbar();
  }
}

async function updateOutputSelection(button: HTMLElement): Promise<void> {
  const taskId = button.dataset.historyOutputSelectedTaskId || historyState.selectedTaskId;
  const outputIndex = positiveInt(button.dataset.historyOutputSelectedIndex);
  if (!taskId || outputIndex === null) return;
  const selected = button.getAttribute("aria-pressed") !== "true";
  try {
    const response = await fetch(`/api/tasks/${encodeURIComponent(taskId)}/outputs/${encodeURIComponent(String(outputIndex))}/selected`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ selected }),
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.detail || translate("taskActions.updated"));
    renderTaskDetail(data.task || {});
  } catch (error) {
    setText(els.resultSummary, errorMessage(error, translate("taskContext.actionFailed")));
  }
}

async function deleteUnselectedOutputs(taskId: string): Promise<void> {
  if (!taskId) return;
  if (historyState.deleteUnselectedConfirmTaskId !== taskId) {
    historyState.deleteUnselectedConfirmTaskId = taskId;
    renderTaskDetail(historyState.detailTask || {});
    return;
  }
  try {
    const response = await fetch(`/api/tasks/${encodeURIComponent(taskId)}/outputs/delete-unselected`, { method: "POST" });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.detail || translate("taskActions.deleteFailed"));
    historyState.deleteUnselectedConfirmTaskId = "";
    renderTaskDetail(data.task || {});
    await loadTasks({ reset: true });
  } catch (error) {
    setText(els.resultSummary, errorMessage(error, translate("taskActions.deleteFailed")));
  }
}

function promptTextForKind(kind: string): string {
  const task = historyState.detailTask || {};
  if (kind === "submitted") return String(task.prompt_for_model || "").trim();
  if (kind === "revised") {
    return revisedPromptText(task);
  }
  return String(task.prompt || task.prompt_preview || "").trim();
}

async function writeClipboardText(text: string): Promise<void> {
  if (navigator.clipboard?.writeText) {
    await navigator.clipboard.writeText(text);
    return;
  }
  const textarea = document.createElement("textarea");
  textarea.value = text;
  textarea.setAttribute("readonly", "");
  textarea.style.position = "fixed";
  textarea.style.opacity = "0";
  document.body.append(textarea);
  textarea.select();
  document.execCommand("copy");
  textarea.remove();
}

function setPromptCopyButtonFeedback(button: HTMLElement, message: string): void {
  const original = button.dataset.historyOriginalLabel || button.textContent || translate("history.copyPromptShort");
  button.dataset.historyOriginalLabel = original;
  button.textContent = message;
  button.classList.add("copied");
  window.setTimeout(() => {
    if (!button.isConnected) return;
    button.textContent = button.dataset.historyOriginalLabel || translate("history.copyPromptShort");
    button.classList.remove("copied");
  }, 1600);
}

async function copyPromptToClipboard(kind = "original", button?: HTMLElement): Promise<void> {
  const text = promptTextForKind(kind);
  if (!text) {
    if (button) {
      setPromptCopyButtonFeedback(button, translate("history.noPromptShort"));
    } else {
      setText(els.resultSummary, translate("history.noPrompt"));
    }
    return;
  }
  try {
    await writeClipboardText(text);
    if (button) setPromptCopyButtonFeedback(button, translate("history.promptCopiedShort"));
    setText(els.resultSummary, translate("history.promptCopied"));
  } catch (error) {
    if (button) setPromptCopyButtonFeedback(button, translate("history.promptCopyFailedShort"));
    setText(els.resultSummary, errorMessage(error, translate("history.promptCopyFailed")));
  }
}

function reuseHistoryTask(taskId: string): void {
  const task = historyState.detailTask || {};
  const actualTaskId = String(taskId || task.task_id || "");
  if (!actualTaskId) return;
  try {
    localStorage.setItem(HISTORY_TASK_REUSE_HANDOFF_KEY, JSON.stringify({
      task_id: actualTaskId,
      source: "history",
      added_at: new Date().toISOString(),
    }));
    window.location.href = "/";
  } catch (error) {
    setText(els.resultSummary, errorMessage(error, translate("taskContext.actionFailed")));
  }
}

async function copyHistoryTaskId(taskIds: string[]): Promise<void> {
  const ids = taskIds.filter(Boolean);
  if (!ids.length) return;
  try {
    await writeClipboardText(ids.join("\n"));
    setText(els.resultSummary, ids.length > 1 ? formatTranslation("history.taskIdsCopied", { count: ids.length }) : translate("taskContext.idCopied"));
  } catch (error) {
    setText(els.resultSummary, errorMessage(error, translate("taskContext.actionFailed")));
  }
}

async function copyHistoryTaskPrompts(taskIds: string[]): Promise<void> {
  const prompts: string[] = [];
  for (const taskId of taskIds.filter(Boolean)) {
    try {
      const detail = await fetchHistoryTaskDetail(taskId);
      const prompt = historyTaskPromptForClipboard(detail);
      if (prompt) prompts.push(prompt);
    } catch {
      const fallback = historyTaskPromptForClipboard(historyTaskSummary(taskId));
      if (fallback) prompts.push(fallback);
    }
  }
  if (!prompts.length) {
    setText(els.resultSummary, translate("history.noPrompt"));
    return;
  }
  try {
    await writeClipboardText(prompts.join("\n\n---\n\n"));
    setText(els.resultSummary, taskIds.length > 1 ? formatTranslation("history.promptsCopied", { count: prompts.length }) : translate("history.promptCopied"));
  } catch (error) {
    setText(els.resultSummary, errorMessage(error, translate("history.promptCopyFailed")));
  }
}

function triggerHistoryDownload(url: string, filename = ""): void {
  if (!url) return;
  const link = document.createElement("a");
  link.href = url;
  if (filename) {
    link.download = filename;
  } else {
    link.setAttribute("download", "");
  }
  link.style.display = "none";
  document.body.append(link);
  link.click();
  link.remove();
}

async function downloadHistoryTask(taskId: string): Promise<boolean> {
  const detail = await fetchHistoryTaskDetail(taskId);
  const records = taskOutputRecords(detail);
  if (!records.length) throw new Error(translate("history.noDownloadableOutputs"));
  if (records.length === 1) {
    triggerHistoryDownload(records[0]?.url || "");
  } else {
    triggerHistoryDownload(`/api/tasks/${encodeURIComponent(taskId)}/outputs.zip`, `${taskId}-images.zip`);
  }
  return true;
}

async function downloadHistoryTasks(taskIds: string[]): Promise<void> {
  let downloaded = 0;
  for (const taskId of taskIds.filter(Boolean)) {
    try {
      if (await downloadHistoryTask(taskId)) downloaded += 1;
    } catch {
      // Keep batch download best-effort; the status line reports the count.
    }
  }
  setText(
    els.resultSummary,
    downloaded > 1
      ? formatTranslation("history.batchDownloadStarted", { count: downloaded })
      : downloaded === 1
        ? translate("history.downloadStarted")
        : translate("history.noDownloadableOutputs"),
  );
}

function selectedHistoryContextTaskIds(clickedTaskId: string): string[] {
  if (historyState.selectedTaskIds.size > 1 && historyState.selectedTaskIds.has(clickedTaskId)) {
    return [...historyState.selectedTaskIds].filter(Boolean);
  }
  if (historyState.selectedTaskIds.size !== 1 || !historyState.selectedTaskIds.has(clickedTaskId)) {
    historyState.selectedTaskIds = new Set([clickedTaskId]);
    historyState.selectionAnchorTaskId = clickedTaskId;
    historyState.deleteConfirming = false;
    historyState.contextMenuDeleteConfirmKey = "";
    updateTaskSelectionVisuals();
    renderBulkToolbar();
  }
  return [clickedTaskId].filter(Boolean);
}

function openHistoryContextMenu(taskId: string, clientX: number, clientY: number): void {
  if (!taskId) return;
  const taskIds = selectedHistoryContextTaskIds(taskId);
  const mode: HistoryContextMenuMode = taskIds.length > 1 ? "multi" : "single";
  historyState.contextMenu = { mode, taskId, taskIds, x: clientX, y: clientY };
  const menu = ensureHistoryContextMenu();
  menu.dataset.historyContextTaskId = taskId;
  menu.dataset.historyContextMode = mode;
  menu.innerHTML = historyContextMenuHtml(mode, taskIds);
  menu.classList.remove("hidden");
  bindHistoryContextMenuActionEvents(menu);
  positionHistoryContextMenu(menu, clientX, clientY);
  menu.querySelector<HTMLButtonElement>(".history-context-menu-button:not(:disabled)")?.focus({ preventScroll: true });
}

function closeHistoryContextMenu(): void {
  if (!historyContextMenuEl) return;
  historyContextMenuEl.classList.add("hidden");
  historyContextMenuEl.removeAttribute("data-history-context-task-id");
  historyContextMenuEl.removeAttribute("data-history-context-mode");
}

function ensureHistoryContextMenu(): HTMLElement {
  if (historyContextMenuEl) return historyContextMenuEl;
  historyContextMenuEl = document.createElement("div");
  historyContextMenuEl.className = "history-context-menu hidden";
  historyContextMenuEl.setAttribute("role", "menu");
  historyContextMenuEl.setAttribute("aria-label", translate("history.contextMenuLabel"));
  document.body.append(historyContextMenuEl);
  return historyContextMenuEl;
}

function rerenderHistoryContextMenu(): void {
  if (!historyContextMenuEl || historyContextMenuEl.classList.contains("hidden")) return;
  historyContextMenuEl.setAttribute("aria-label", translate("history.contextMenuLabel"));
  historyContextMenuEl.innerHTML = historyContextMenuHtml(historyState.contextMenu.mode, historyState.contextMenu.taskIds);
  bindHistoryContextMenuActionEvents(historyContextMenuEl);
  positionHistoryContextMenu(historyContextMenuEl, historyState.contextMenu.x, historyState.contextMenu.y);
}

function historyContextMenuHtml(mode: HistoryContextMenuMode, taskIds: string[]): string {
  if (mode === "multi") return historyMultiContextMenuHtml(taskIds);
  return historySingleContextMenuHtml(taskIds[0] || "");
}

function historySingleContextMenuHtml(taskId: string): string {
  const summary = historyTaskSummary(taskId);
  const archived = historyTaskArchived(summary);
  const blocked = historyTaskDeleteBlocked(summary);
  const hasOutput = historyTaskGeneratedCount(summary) > 0;
  const confirmingDelete = historyState.contextMenuDeleteConfirmKey === `task:${taskId}`;
  return `
    <div class="history-context-menu-section">
      ${historyContextButton("reuse", translate("history.reuseTask"))}
      ${historyContextButton("copy-prompt", translate("history.copyPrompt"))}
      ${historyContextButton("copy-id", translate("taskContext.copyId"))}
      ${historyContextButton("download", translate("history.downloadTask"), !hasOutput)}
    </div>
    <div class="history-context-menu-section">
      ${historyContextButton("archive", archived ? translate("archive.restore") : translate("action.archive"))}
      ${historyContextButton("delete", confirmingDelete ? translate("history.confirmDelete") : translate("action.delete"), blocked, true)}
    </div>
  `;
}

function historyMultiContextMenuHtml(taskIds: string[]): string {
  const confirmKey = historySelectedDeleteConfirmKey(taskIds);
  const confirmingDelete = historyState.contextMenuDeleteConfirmKey === confirmKey;
  return `
    <div class="history-context-menu-section">
      ${historyContextButton("download-selected", translate("history.downloadSelectedTasks"))}
      ${historyContextButton("archive-selected", translate("action.archive"))}
      ${historyContextButton("restore-selected", translate("archive.restore"))}
      ${historyContextButton("delete-selected", confirmingDelete ? translate("history.confirmDeleteSelected") : translate("action.delete"), false, true)}
    </div>
  `;
}

function historyContextButton(action: string, label: string, disabled = false, danger = false): string {
  const disabledAttr = disabled ? " disabled" : "";
  const dangerClass = danger ? " danger" : "";
  return `<button class="history-context-menu-button${dangerClass}" type="button" role="menuitem" data-history-context-action="${escapeHtml(action)}"${disabledAttr}>${escapeHtml(label)}</button>`;
}

function bindHistoryContextMenuActionEvents(menu: HTMLElement): void {
  menu.querySelectorAll<HTMLButtonElement>("[data-history-context-action]").forEach((button) => {
    button.addEventListener("click", (event) => {
      event.preventDefault();
      event.stopPropagation();
      if (button.disabled) return;
      void handleHistoryContextMenuAction(button);
    });
  });
}

async function handleHistoryContextMenuAction(button: HTMLButtonElement): Promise<void> {
  const action = String(button.dataset.historyContextAction || "");
  const taskId = historyState.contextMenu.taskId;
  const taskIds = historyState.contextMenu.taskIds.filter(Boolean);
  try {
    if (action === "delete") {
      const deleted = await deleteSingleHistoryTask(taskId, { confirmInMenu: true });
      if (deleted) closeHistoryContextMenu();
      return;
    }
    if (action === "delete-selected") {
      await deleteHistoryContextSelectedTasks(taskIds);
      return;
    }
    closeHistoryContextMenu();
    if (action === "reuse") {
      reuseHistoryTask(taskId);
    } else if (action === "copy-prompt") {
      await copyHistoryTaskPrompts([taskId]);
    } else if (action === "copy-id") {
      await copyHistoryTaskId([taskId]);
    } else if (action === "download") {
      await downloadHistoryTasks([taskId]);
    } else if (action === "archive") {
      const archived = historyTaskArchived(historyTaskSummary(taskId));
      await archiveSingleTask(taskId, !archived);
    } else if (action === "copy-prompts") {
      await copyHistoryTaskPrompts(taskIds);
    } else if (action === "copy-ids") {
      await copyHistoryTaskId(taskIds);
    } else if (action === "download-selected") {
      await downloadHistoryTasks(taskIds);
    } else if (action === "archive-selected") {
      await archiveHistoryTaskIds(taskIds, true);
    } else if (action === "restore-selected") {
      await archiveHistoryTaskIds(taskIds, false);
    }
  } catch (error) {
    setText(els.resultSummary, errorMessage(error, translate("taskContext.actionFailed")));
  }
}

async function deleteHistoryContextSelectedTasks(taskIds: string[]): Promise<void> {
  const confirmKey = historySelectedDeleteConfirmKey(taskIds);
  if (historyState.contextMenuDeleteConfirmKey !== confirmKey) {
    historyState.contextMenuDeleteConfirmKey = confirmKey;
    historyState.deleteConfirming = true;
    renderBulkToolbar();
    rerenderHistoryContextMenu();
    return;
  }
  historyState.selectedTaskIds = new Set(taskIds);
  await deleteSelectedTasks();
  if (!historyState.deleteConfirming) closeHistoryContextMenu();
}

function historySelectedDeleteConfirmKey(taskIds: string[]): string {
  return `selected:${taskIds.slice().sort().join("|")}`;
}

function positionHistoryContextMenu(menu: HTMLElement, clientX: number, clientY: number): void {
  const margin = 8;
  menu.style.left = "0px";
  menu.style.top = "0px";
  const width = menu.offsetWidth;
  const height = menu.offsetHeight;
  const left = clampNumber(clientX, margin, Math.max(margin, window.innerWidth - width - margin));
  const top = clampNumber(clientY, margin, Math.max(margin, window.innerHeight - height - margin));
  menu.style.left = `${left}px`;
  menu.style.top = `${top}px`;
}

function handoffReferenceToMain(url: string): void {
  if (!url) return;
  localStorage.setItem(HISTORY_REFERENCE_HANDOFF_KEY, JSON.stringify([{ url, source: "history", added_at: new Date().toISOString() }]));
  window.location.href = "/";
}

function ensureHistoryLightbox(): HTMLElement {
  let lightbox = document.querySelector<HTMLElement>(".history-lightbox");
  if (lightbox) return lightbox;
  lightbox = document.createElement("div");
  lightbox.className = "history-lightbox";
  lightbox.hidden = true;
  lightbox.innerHTML = `
    <button class="drawer-close-button history-lightbox-close" type="button" data-history-lightbox-close aria-label="${escapeHtml(translate("history.closePreview"))}">×</button>
    <img alt="">
  `;
  document.body.append(lightbox);
  return lightbox;
}

function openHistoryLightbox(url: string): void {
  if (!url) return;
  const lightbox = ensureHistoryLightbox();
  const image = lightbox.querySelector<HTMLImageElement>("img");
  if (image) image.src = url;
  lightbox.hidden = false;
  document.body.classList.add("history-lightbox-open");
}

function closeHistoryLightbox(): void {
  const lightbox = document.querySelector<HTMLElement>(".history-lightbox");
  if (!lightbox || lightbox.hidden) return;
  lightbox.hidden = true;
  const image = lightbox.querySelector<HTMLImageElement>("img");
  if (image) image.removeAttribute("src");
  document.body.classList.remove("history-lightbox-open");
}

function closeDetail(): void {
  historyState.selectedTaskId = "";
  els.page?.classList.remove("history-detail-open");
  updateHistoryUrl();
  updateTaskSelectionVisuals("");
  renderDetailShell(translate("history.detailEmpty"));
}

function bindEvents(): void {
  let searchTimer = 0;
  els.search?.addEventListener("input", () => {
    window.clearTimeout(searchTimer);
    searchTimer = window.setTimeout(() => {
      historyState.q = els.search?.value.trim() || "";
      historyState.selectedTaskId = "";
      updateHistoryUrl();
      void loadTasks({ reset: true });
    }, 180);
  });
  els.searchClear?.addEventListener("click", () => {
    if (els.search) els.search.value = "";
    historyState.q = "";
    historyState.selectedTaskId = "";
    updateHistoryUrl();
    void loadTasks({ reset: true });
  });
  els.sort?.addEventListener("change", () => {
    historyState.sort = els.sort?.value === "oldest" ? "oldest" : "newest";
    historyState.selectedTaskId = "";
    updateHistoryUrl();
    void loadTasks({ reset: true });
  });
  document.addEventListener("change", (event) => {
    const target = event.target as HTMLElement | null;
    const checkbox = target?.closest<HTMLInputElement>("[data-history-task-select]");
    if (!checkbox) return;
    const taskId = checkbox.dataset.historyTaskSelect || "";
    if (checkbox.checked) {
      historyState.selectedTaskIds.add(taskId);
    } else {
      historyState.selectedTaskIds.delete(taskId);
    }
    historyState.selectionAnchorTaskId = taskId;
    historyState.deleteConfirming = false;
    updateTaskSelectionVisuals();
    renderBulkToolbar();
  });
  document.addEventListener("click", (event) => {
    const target = event.target as HTMLElement | null;
    const historySelect = target?.closest<HTMLElement>("[data-history-task-select]");
    if (historySelect) {
      if (handleHistoryTaskShortcutSelection(historySelect.dataset.historyTaskSelect || "", event)) return;
      event.stopPropagation();
      return;
    }
    const viewButton = target?.closest<HTMLElement>("[data-history-view]");
    if (viewButton) {
      setHistoryViewMode(viewButton.dataset.historyView || "grid");
      return;
    }
    const taskButton = target?.closest<HTMLElement>("[data-history-task-id]");
    if (taskButton) {
      if (handleHistoryTaskShortcutSelection(taskButton.dataset.historyTaskId || "", event)) return;
      clearHistoryTaskSelection({ updateVisuals: false });
      void loadTaskDetail(taskButton.dataset.historyTaskId || "");
      return;
    }
    const selectButton = target?.closest<HTMLElement>("[data-history-output-selected-task-id]");
    if (selectButton) {
      void updateOutputSelection(selectButton);
      return;
    }
    const deleteUnselectedButton = target?.closest<HTMLElement>("[data-history-delete-unselected]");
    if (deleteUnselectedButton) {
      void deleteUnselectedOutputs(deleteUnselectedButton.dataset.historyDeleteUnselected || "");
      return;
    }
    const archiveTaskButton = target?.closest<HTMLElement>("[data-history-archive-task]");
    if (archiveTaskButton) {
      void archiveSingleTask(archiveTaskButton.dataset.historyArchiveTask || "", archiveTaskButton.dataset.historyArchiveValue === "true");
      return;
    }
    const deleteTaskButton = target?.closest<HTMLElement>("[data-history-delete-task]");
    if (deleteTaskButton) {
      void deleteSingleHistoryTask(deleteTaskButton.dataset.historyDeleteTask || "");
      return;
    }
    const referenceHandoffButton = target?.closest<HTMLElement>("[data-history-reference-handoff-url]");
    if (referenceHandoffButton) {
      handoffReferenceToMain(referenceHandoffButton.dataset.historyReferenceHandoffUrl || "");
      return;
    }
    const copyPromptButton = target?.closest<HTMLElement>("[data-history-copy-prompt-kind]");
    if (copyPromptButton) {
      void copyPromptToClipboard(copyPromptButton.dataset.historyCopyPromptKind || "original", copyPromptButton);
      return;
    }
    const reuseTaskButton = target?.closest<HTMLElement>("[data-history-reuse-task]");
    if (reuseTaskButton) {
      reuseHistoryTask(reuseTaskButton.dataset.historyReuseTask || "");
      return;
    }
    const lightboxButton = target?.closest<HTMLElement>("[data-history-lightbox-url]");
    if (lightboxButton) {
      openHistoryLightbox(lightboxButton.dataset.historyLightboxUrl || "");
      return;
    }
    if (target?.closest("[data-history-lightbox-close]")) {
      closeHistoryLightbox();
      return;
    }
    const lightbox = target?.closest<HTMLElement>(".history-lightbox");
    if (lightbox && target === lightbox) {
      closeHistoryLightbox();
      return;
    }
    if (target?.closest("[data-history-delete-unselected-cancel]")) {
      historyState.deleteUnselectedConfirmTaskId = "";
      renderTaskDetail(historyState.detailTask || {});
      return;
    }
    if (target?.closest("[data-history-detail-close]")) {
      closeDetail();
      return;
    }
    for (const key of HISTORY_FILTER_KEYS) {
      const attr = historyFilterAttribute(key);
      const button = target?.closest<HTMLElement>(`[data-history-${attr}]`);
      if (button) {
        applyFilter(key, button.getAttribute(`data-history-${attr}`) || "");
        return;
      }
    }
  });
  els.taskList?.addEventListener("contextmenu", (event) => {
    const target = event.target as HTMLElement | null;
    const card = target?.closest<HTMLElement>(".history-task-card[data-history-task-card-id]");
    if (!card || !els.taskList?.contains(card)) return;
    event.preventDefault();
    event.stopPropagation();
    openHistoryContextMenu(card.dataset.historyTaskCardId || "", event.clientX, event.clientY);
  });
  els.taskList?.addEventListener("keydown", (event) => {
    if (event.key !== "ContextMenu" && !(event.shiftKey && event.key === "F10")) return;
    const target = event.target as HTMLElement | null;
    const card = target?.closest<HTMLElement>(".history-task-card[data-history-task-card-id]");
    if (!card || !els.taskList?.contains(card)) return;
    event.preventDefault();
    const rect = card.getBoundingClientRect();
    openHistoryContextMenu(card.dataset.historyTaskCardId || "", rect.left + 18, rect.top + 18);
  });
  document.addEventListener("click", (event) => {
    if (!historyContextMenuEl || historyContextMenuEl.classList.contains("hidden")) return;
    const target = event.target as HTMLElement | null;
    if (target && historyContextMenuEl.contains(target)) return;
    closeHistoryContextMenu();
  }, true);
  els.bulkArchive?.addEventListener("click", () => void archiveSelectedTasks(true));
  els.bulkRestore?.addEventListener("click", () => void archiveSelectedTasks(false));
  els.bulkDelete?.addEventListener("click", () => void deleteSelectedTasks());
  els.bulkDeleteCancel?.addEventListener("click", () => {
    historyState.deleteConfirming = false;
    renderBulkToolbar();
  });
  els.refresh?.addEventListener("click", () => {
    void loadSummary();
    void loadTasks({ reset: true });
  });
  els.taskList?.addEventListener("dragstart", (event) => {
    const target = event.target as HTMLElement | null;
    if (target?.closest(".history-task-thumb img")) event.preventDefault();
  });
  els.taskList?.addEventListener("scroll", () => {
    closeHistoryContextMenu();
    maybeLoadMoreFromScroll();
  }, { passive: true });
  window.addEventListener("resize", () => {
    closeHistoryContextMenu();
    scheduleHistoryGridLayout();
  }, { passive: true });
  document.addEventListener(LOCALE_CHANGE_EVENT, () => {
    document.title = translate("history.documentTitle");
    syncHistoryViewMode();
    syncArchiveButtons();
    els.taskList?.querySelectorAll<HTMLElement>(".history-task-active-badge").forEach((badge) => {
      badge.textContent = translate("history.viewing");
    });
    if (historyState.detailTask) {
      renderTaskDetail(historyState.detailTask);
    } else if (!historyState.selectedTaskId) {
      renderDetailShell(translate("history.detailEmpty"));
    }
    rerenderHistoryContextMenu();
    renderBulkToolbar();
    setLoadMoreState(historyState.loading
      ? translate("history.loadingMore")
      : historyState.exhausted
        ? translate("history.noMore")
        : "", {
      hidden: !historyState.loading && !historyState.exhausted,
      busy: historyState.loading,
    });
  });
  window.addEventListener("keydown", (event) => {
    if (event.key !== "Escape") return;
    if (historyContextMenuEl && !historyContextMenuEl.classList.contains("hidden")) {
      closeHistoryContextMenu();
      return;
    }
    const lightbox = document.querySelector<HTMLElement>(".history-lightbox");
    if (lightbox && !lightbox.hidden) {
      closeHistoryLightbox();
      return;
    }
    if (historyState.selectedTaskId) closeDetail();
  });
}

function errorMessage(error: unknown, fallback: string): string {
  return error instanceof Error && error.message ? error.message : fallback;
}

async function bootHistoryPage(): Promise<void> {
  restoreHistoryThemePreference();
  bindHistoryThemePreference();
  applyHistoryLocale();
  syncStateFromUrl();
  renderDetailShell(translate("history.detailEmpty"));
  bindEvents();
  await loadSummary();
  await loadTasks({ reset: true });
  if (historyState.selectedTaskId) {
    void loadTaskDetail(historyState.selectedTaskId);
  }
}

void bootHistoryPage();

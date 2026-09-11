import { copyTextToClipboard } from "./clipboard-text";
import { localizedTaskStatus, taskRecoveryMessage } from "./task-recovery";
import { submittedPromptForTask } from "./transparency-status";
import { LOCALE_CHANGE_EVENT, formatTranslation, translate } from "./i18n";
import { initializeHistoryShell } from "./history-shell";
import { initializeHistoryMobileFilters } from "./history-mobile-filters";
import {
  historyDetailImagesHtml,
  historyDetailImagesLayoutClass,
  historyInputLightboxUrlsFromTask,
  historyInputReferencesHtml,
  historyReferenceFilesHtml,
  historyLightboxUrlsFromTask,
  taskOutputRecords,
  taskSelectedOutputIndexes,
} from "./history-detail-media";
import {
  type HistoryScrollAnchor,
  type HistoryWindowEdge,
  type HistoryWindowDirection,
  captureHistoryScrollAnchor,
  createHistoryPositionSaveController,
  historyTaskArrowTargetCard,
  historyTaskCards,
  historyWindowEdgeCursor,
  isHistoryTaskArrowKey,
  restoreHistoryScrollAnchor,
} from "./history-window";
import {
  HISTORY_FILTER_QUERY_KEYS,
  clearHistoryLocationSnapshot,
  historySnapshotQuery,
  readHistoryLocationSnapshot,
  saveHistoryLocationSnapshot,
  type HistoryLoadOptions,
  type HistoryLoadResult,
} from "./history-scroll-memory";
import {
  clearHistoryActiveFilters,
  collectHistoryActiveFilters,
  removeHistoryActiveFilter,
  type HistoryActiveFilterItem,
  type HistoryActiveFilterSnapshot,
} from "./history-active-filters";
import {
  historyTaskPageQuery,
  loadHistoryAnchorPage,
  runHistoryPositionBoot,
  type HistoryPageQueryInput,
} from "./history-position-runtime";
import {
  closeHistoryLightbox,
  isHistoryLightboxOpen,
  openHistoryLightbox,
  type HistoryLightboxTaskDirection,
  type HistoryLightboxTaskNavigationContext,
} from "./history-lightbox";
import { webAppDocumentTitle } from "./web-app-title";
import { createGroundingAttribution } from "./grounding-attribution";
import {
  createHistoryExport,
  triggerHistoryExportDownload,
  type HistoryExportMode,
} from "./history-export";
import {
  createHistoryTag,
  createHistoryTagForTasks,
  deleteHistoryTag,
  historyCardTagsHtml,
  historyDetailTagsHtml,
  historyFavoriteButtonHtml,
  historyOrganizationSummarySupported,
  historyTagPickerCreateHtml,
  historyTagPickerHtml,
  historyTaskRowsSupportOrganization,
  HistoryOrganizationRequestError,
  organizeHistoryTasks,
  readHistoryOrganizationFilters,
  renameHistoryTag,
  taskMatchesHistoryOrganizationFilters,
  type HistoryOrganization,
  type HistoryOrganizationFilters,
  type HistoryTag,
  withHistoryTagFilter,
  withHistoryUntaggedFilter,
  writeHistoryOrganizationFilters,
} from "./history-organization";
import { refreshHistoryForRealtimeTask } from "./history-realtime";
import {
  createHistoryGridResizeController,
  historyGridAvailableWidth,
  historyGridCardsNeedLayout,
  type HistoryGridResizeController,
} from "./history-grid-resize";
import {
  createHistoryBackupController,
  estimateHistoryBackup,
  historyBackupViewState,
  type HistoryBackupEstimate,
  type HistoryBackupFilters,
  type HistoryBackupJob,
  type HistoryBackupScope,
} from "./history-backup";
import {
  createHistoryImportController,
  type HistoryImportPhase,
  type HistoryImportPreview,
  type HistoryImportResult,
  type HistoryImportSession,
  type HistoryImportTaskResult,
} from "./history-import";
import {
  historyDetailCloseEffect,
  historyManagementPanelHtml,
  historySelectionDetailResolution,
  historySelectionPanelHtml,
  nextHistoryActionPanelSection,
  shouldClearHistoryTaskFromBlankSurface,
  type HistoryActionPanelCopy,
  type HistoryActionPanelSection,
  type HistoryDetailMode,
} from "./history-action-panel";
import {
  historySelectAllTaskIds,
  isHistorySelectAllTasksShortcut,
} from "./history-selection-shortcuts";

type HistoryFacet = { value: string; count: number };
type HistoryMonth = { month: string; count: number };
type HistorySummary = {
  total: number;
  archived_total: number;
  favorite_total: number;
  untagged_total: number;
  tags: HistoryTag[];
  months: HistoryMonth[];
  modes: HistoryFacet[];
  prompt_modes: HistoryFacet[];
  qualities: HistoryFacet[];
  ratios: HistoryFacet[];
  orientations: HistoryFacet[];
  backends: HistoryFacet[];
  providers: HistoryFacet[];
};
type HistoryTask = HistoryOrganization & {
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
type HistoryFilterKey = (typeof HISTORY_FILTER_QUERY_KEYS)[number];
type HistoryViewMode = "grid" | "list";
type HistoryRenderPosition = "replace" | "append" | "prepend";
type HistoryTaskPage = { tasks: HistoryTask[]; next_cursor: string | null; previous_cursor?: string | null; anchor_found?: boolean; detail?: string };
type HistoryContextMenuMode = "single" | "multi";
type HistoryResizerSide = "left" | "right";
type HistoryOrganizationChange = {
  favorite?: boolean | null;
  add_tag_ids?: string[];
  remove_tag_ids?: string[];
};

const HISTORY_RATIO_OTHER_VALUE = "__other__";
const HISTORY_PAGE_LIMIT = 50;
const MAX_MOUNTED_TASK_CARDS = 300;
const HISTORY_REFERENCE_HANDOFF_KEY = "codex-image-history-reference-handoff";
const HISTORY_TASK_REUSE_HANDOFF_KEY = "codex-image-history-task-reuse-handoff";
const HISTORY_THUMBNAIL_CACHE_VERSION = "thumb-768-fit";
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

const historyState = {
  q: "",
  mode: "",
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
  selectionMode: false,
  deleteConfirming: false,
  pendingDeleteTaskIds: [] as string[],
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
let pendingHistoryGridKeepTaskId = "";
let historyResizeFrame = 0;
let historyGridResizeObserver: ResizeObserver | null = null;
let historyGridMutationObserver: MutationObserver | null = null;
let historyGridResizeController: HistoryGridResizeController | null = null;
let historyDetailLoadToken = 0;
let historyContextMenuEl: HTMLElement | null = null;
let historyTags: HistoryTag[] = [];
let historySummary: HistorySummary | null = null;
let historyOrganizationFilters: HistoryOrganizationFilters = {
  favorite: false,
  tagIds: [],
  untagged: false,
};
let historyTagDeleteConfirmId = "";
let historyTagPickerEl: HTMLElement | null = null;
let historyTagPickerTrigger: HTMLElement | null = null;
let historyTagPickerMode: "add" | "remove" | "detail" = "add";
let historyTagPickerTaskIds: string[] = [];
let historyTagPickerCreatePending = false;
let historyTagManagerCreatePending = false;
let historyOrganizationApiSupported: boolean | null = null;
let historyExportPickerEl: HTMLElement | null = null;
let historyExportTrigger: HTMLElement | null = null;
let historyExportTaskIds: string[] = [];
let historyExportPending = false;
let historyOrganizePickerEl: HTMLElement | null = null;
let historyOrganizeTrigger: HTMLElement | null = null;
let historyBackupReturnFocus: HTMLElement | null = null;
let historyImportReturnFocus: HTMLElement | null = null;
let selectedTaskIdsSnapshot: string[] = [];
let currentBackupJob: HistoryBackupJob | null = null;
let currentImportPreview: HistoryImportPreview | null = null;
let currentImportResult: HistoryImportResult | null = null;
let currentImportPhase: HistoryImportPhase = "idle";
let resumableImportSession: HistoryImportSession | null = null;
let historyImportResumePending = false;
let lastBackupAnnouncement = "";
let historyBackupDownloaded = false;
let historyBackupEstimateGeneration = 0;
const historyBackupEstimates = new Map<HistoryBackupScope["kind"], HistoryBackupEstimate>();
const historyBackupEstimateStates = new Map<HistoryBackupScope["kind"], "idle" | "loading" | "ready" | "unavailable">();
let activeHistoryResizer: HistoryActiveResizer | null = null;
let historyActionPanelExpanded: HistoryActionPanelSection = "";
let historyDetailReturnFocus: HTMLElement | null = null;

const els = {
  page: document.querySelector<HTMLElement>(".history-page"),
  sidebar: document.querySelector<HTMLElement>(".history-sidebar"),
  mobileFiltersButton: document.querySelector<HTMLButtonElement>("#historyMobileFiltersButton"),
  mobileFilterCount: document.querySelector<HTMLElement>("#historyMobileFilterCount"),
  filtersBackdrop: document.querySelector<HTMLButtonElement>("#historyFiltersBackdrop"),
  leftResizer: document.querySelector<HTMLElement>('[data-history-resizer="left"]'),
  rightResizer: document.querySelector<HTMLElement>('[data-history-resizer="right"]'),
  total: document.querySelector<HTMLElement>("#historyTotal"),
  search: document.querySelector<HTMLInputElement>("#historySearch"),
  searchClear: document.querySelector<HTMLButtonElement>("#historySearchClear"),
  favoriteList: document.querySelector<HTMLElement>("#historyFavoriteList"),
  tagFilterList: document.querySelector<HTMLElement>("#historyTagFilterList"),
  tagManageToggle: document.querySelector<HTMLButtonElement>("#historyTagManageToggle"),
  tagManager: document.querySelector<HTMLElement>("#historyTagManager"),
  tagManagerList: document.querySelector<HTMLElement>("#historyTagManagerList"),
  tagManagerStatus: document.querySelector<HTMLElement>("#historyTagManagerStatus"),
  tagNameInput: document.querySelector<HTMLInputElement>("#historyTagNameInput"),
  modeList: document.querySelector<HTMLElement>("#historyModeList"),
  monthList: document.querySelector<HTMLElement>("#historyMonthList"),
  promptModeList: document.querySelector<HTMLElement>("#historyPromptModeList"),
  qualityList: document.querySelector<HTMLElement>("#historyQualityList"),
  ratioList: document.querySelector<HTMLElement>("#historyRatioList"),
  orientationList: document.querySelector<HTMLElement>("#historyOrientationList"),
  backendList: document.querySelector<HTMLElement>("#historyBackendList"),
  providerList: document.querySelector<HTMLElement>("#historyProviderList"),
  archiveList: document.querySelector<HTMLElement>("#historyArchiveList"),
  sortToggle: document.querySelector<HTMLElement>("#historySortToggle"),
  viewToggle: document.querySelector<HTMLElement>("#historyViewToggle"),
  resultSummary: document.querySelector<HTMLElement>("#historyResultSummary"),
  activeFilters: document.querySelector<HTMLElement>("#historyActiveFilters"),
  activeFiltersLabel: document.querySelector<HTMLElement>("#historyActiveFiltersLabel"),
  activeFilterList: document.querySelector<HTMLElement>("#historyActiveFilterList"),
  clearAllFilters: document.querySelector<HTMLButtonElement>("#historyClearAllFilters"),
  managementButton: document.querySelector<HTMLButtonElement>("#historyManagementButton"),
  selectionDock: document.querySelector<HTMLElement>("#historySelectionDock"),
  selectionDockCount: document.querySelector<HTMLElement>("#historySelectionDockCount"),
  taskList: document.querySelector<HTMLElement>("#historyTaskList"),
  detail: document.querySelector<HTMLElement>("#historyDetail"),
  sentinel: document.querySelector<HTMLElement>("[data-history-load-more]"),
  refresh: document.querySelector<HTMLButtonElement>("#historyRefreshButton"),
  backupDialog: document.querySelector<HTMLElement>("#historyBackupDialog"),
  backupTitle: document.querySelector<HTMLElement>("#historyBackupTitle"),
  backupScopeHelp: document.querySelector<HTMLElement>("#historyBackupScopeHelp"),
  backupScopeFieldset: document.querySelector<HTMLFieldSetElement>("#historyBackupScopeFieldset"),
  backupScopeEstimate: document.querySelector<HTMLElement>("#historyBackupScopeEstimate"),
  backupScopeState: document.querySelector<HTMLElement>("#historyBackupScopeState"),
  backupSelectedScope: document.querySelector<HTMLInputElement>("#historyBackupScopeSelected"),
  backupProgressRegion: document.querySelector<HTMLElement>("#historyBackupProgressRegion"),
  backupProgressSummary: document.querySelector<HTMLElement>("#historyBackupProgressSummary"),
  backupProgress: document.querySelector<HTMLProgressElement>("#historyBackupProgress"),
  backupStats: document.querySelector<HTMLElement>("#historyBackupStats"),
  backupLive: document.querySelector<HTMLElement>("#historyBackupLive"),
  backupWarning: document.querySelector<HTMLElement>("#historyBackupWarning"),
  backupComplete: document.querySelector<HTMLElement>("#historyBackupComplete"),
  backupStart: document.querySelector<HTMLButtonElement>("#historyBackupStart"),
  backupCancel: document.querySelector<HTMLButtonElement>("#historyBackupCancel"),
  backupDownload: document.querySelector<HTMLButtonElement>("#historyBackupDownload"),
  backupDismiss: document.querySelector<HTMLButtonElement>("#historyBackupDismiss"),
  importDialog: document.querySelector<HTMLElement>("#historyImportDialog"),
  importTitle: document.querySelector<HTMLElement>("#historyImportTitle"),
  importFile: document.querySelector<HTMLInputElement>("#historyImportFile"),
  importProgress: document.querySelector<HTMLProgressElement>("#historyImportProgress"),
  importLive: document.querySelector<HTMLElement>("#historyImportLive"),
  importPreview: document.querySelector<HTMLElement>("#historyImportPreview"),
  importResult: document.querySelector<HTMLElement>("#historyImportResult"),
  importConfirm: document.querySelector<HTMLButtonElement>("#historyImportConfirm"),
  importCancel: document.querySelector<HTMLButtonElement>("#historyImportCancel"),
};

const historyPositionSaveController =
  createHistoryPositionSaveController({
    requestFrame: (callback) => window.requestAnimationFrame(callback),
    cancelFrame: (frameId) => window.cancelAnimationFrame(frameId),
    capture: () => els.taskList
      ? captureHistoryScrollAnchor(els.taskList)
      : null,
    save: saveCurrentHistoryLocation,
  });

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

function setHistoryTransferHidden(element: HTMLElement | null, hidden: boolean): void {
  if (!element) return;
  element.hidden = hidden;
  element.classList.toggle("hidden", hidden);
}

function currentHistoryBackupFilters(): HistoryBackupFilters {
  return {
    q: historyState.q,
    month: historyState.month,
    mode: historyState.mode,
    status: "",
    prompt_mode: historyState.prompt_mode,
    size: "",
    quality: historyState.quality,
    ratio: historyState.ratio,
    orientation: historyState.orientation,
    backend: historyState.backend,
    provider: historyState.provider,
    archived: historyState.archived === "true" ? true : historyState.archived === "false" ? false : null,
    favorite: historyOrganizationFilters.favorite ? true : null,
    tag_ids: [...historyOrganizationFilters.tagIds],
    untagged: historyOrganizationFilters.untagged,
    sort: historyState.sort === "oldest" ? "oldest" : "newest",
  };
}

function historyBackupScope(): HistoryBackupScope {
  const selected = els.backupDialog?.querySelector<HTMLInputElement>('input[name="history-backup-scope"]:checked')?.value;
  if (selected === "selected") {
    return { kind: "selected", taskIds: [...selectedTaskIdsSnapshot] };
  }
  if (selected === "all") return { kind: "all" };
  return { kind: "filtered", filters: currentHistoryBackupFilters() };
}

function renderHistoryBackupScopeEstimates(): void {
  if (historyBackupDownloaded) {
    setHistoryTransferHidden(els.backupScopeEstimate, true);
    return;
  }
  for (const kind of ["selected", "filtered", "all"] as const) {
    const target = els.backupDialog?.querySelector<HTMLElement>(
      `[data-history-backup-scope-count="${kind}"]`,
    ) || null;
    const estimate = historyBackupEstimates.get(kind);
    const state = historyBackupEstimateStates.get(kind) || "idle";
    const text = estimate
      ? formatTranslation("historyBackup.scopeCount", {
          eligible: estimate.eligible_tasks,
          total: estimate.total_tasks,
        })
      : state === "loading"
        ? translate("historyBackup.scopeCounting")
        : state === "unavailable"
          ? translate("historyBackup.scopeCountUnavailable")
          : kind === "selected" && selectedTaskIdsSnapshot.length === 0
            ? translate("historyBackup.scopeNoneSelected")
            : "";
    setText(target, text);
  }

  const locked = historyBackupViewState(currentBackupJob).scopeLocked;
  setHistoryTransferHidden(els.backupScopeEstimate, locked);
  if (locked) {
    setText(els.backupScopeEstimate, "");
    return;
  }
  const kind = historyBackupScope().kind;
  const estimate = historyBackupEstimates.get(kind);
  const state = historyBackupEstimateStates.get(kind) || "idle";
  if (estimate) {
    setText(els.backupScopeEstimate, formatTranslation("historyBackup.willBackup", {
      eligible: estimate.eligible_tasks,
      excluded: estimate.excluded_nonterminal,
    }));
  } else if (kind === "selected" && selectedTaskIdsSnapshot.length === 0) {
    setText(els.backupScopeEstimate, translate("historyBackup.selectTasksFirst"));
  } else if (state === "unavailable") {
    setText(els.backupScopeEstimate, translate("historyBackup.scopeCountUnavailable"));
  } else {
    setText(els.backupScopeEstimate, translate("historyBackup.scopeCounting"));
  }
}

async function loadHistoryBackupScopeEstimates(): Promise<void> {
  const generation = ++historyBackupEstimateGeneration;
  historyBackupEstimates.clear();
  historyBackupEstimateStates.clear();
  const scopes: HistoryBackupScope[] = [
    { kind: "filtered", filters: currentHistoryBackupFilters() },
    { kind: "all" },
  ];
  if (selectedTaskIdsSnapshot.length) {
    scopes.unshift({ kind: "selected", taskIds: [...selectedTaskIdsSnapshot] });
  } else {
    historyBackupEstimateStates.set("selected", "idle");
  }
  for (const scope of scopes) historyBackupEstimateStates.set(scope.kind, "loading");
  renderHistoryBackupScopeEstimates();
  await Promise.all(scopes.map(async (scope) => {
    try {
      const estimate = await estimateHistoryBackup(scope);
      if (generation !== historyBackupEstimateGeneration) return;
      historyBackupEstimates.set(scope.kind, estimate);
      historyBackupEstimateStates.set(scope.kind, "ready");
    } catch {
      if (generation !== historyBackupEstimateGeneration) return;
      historyBackupEstimateStates.set(scope.kind, "unavailable");
    }
    if (generation === historyBackupEstimateGeneration) renderHistoryBackupScopeEstimates();
  }));
}

function formatHistoryBytes(value: number | undefined): string {
  const bytes = Number(value || 0);
  if (!Number.isFinite(bytes) || bytes <= 0) return "0 B";
  const units = ["B", "KiB", "MiB", "GiB", "TiB"];
  const index = Math.min(units.length - 1, Math.floor(Math.log(bytes) / Math.log(1024)));
  return `${(bytes / (1024 ** index)).toFixed(index ? 1 : 0)} ${units[index]}`;
}

function historyBackupStatusText(job: HistoryBackupJob): string {
  const key = `historyBackup.${job.status}`;
  return translate(key);
}

function historyBackupErrorText(code: string): string {
  if (code.includes("space") || code.includes("disk")) return translate("historyBackup.errorDisk");
  if (code.includes("source") || code.includes("changed")) return translate("historyBackup.errorSourceChanged");
  if (code.includes("empty") || code.includes("eligible")) return translate("historyBackup.errorEmpty");
  return translate("historyBackup.errorIo");
}

function focusHistoryTransferError(kind: "backup" | "import", message: string): void {
  const summary = kind === "backup" ? els.backupLive : els.importLive;
  setText(summary, message);
  if (summary && !(kind === "backup" ? els.backupDialog : els.importDialog)?.hidden) {
    summary.focus();
  }
}

function isTransientHistoryBackupError(status: number): boolean {
  return status === 0 || status === 408 || status === 429 || status >= 500;
}

function historyBackupScopeText(kind: HistoryBackupScope["kind"] | undefined): string {
  if (kind === "selected") return translate("historyBackup.scopeSelected");
  if (kind === "filtered") return translate("historyBackup.scopeFiltered");
  if (kind === "all") return translate("historyBackup.scopeAll");
  return translate("historyBackup.scopeLockedUnknown");
}

function renderHistoryBackupLockedScope(job: HistoryBackupJob | null): void {
  const locked = historyBackupViewState(job).scopeLocked;
  setHistoryTransferHidden(els.backupScopeState, !locked);
  if (!job || !locked) {
    setText(els.backupScopeState, "");
    return;
  }
  const countsKnown = Number(job.total_tasks || 0) > 0
    || !["queued", "planning"].includes(job.status);
  setText(els.backupScopeState, formatTranslation(
    countsKnown ? "historyBackup.scopeLocked" : "historyBackup.scopeLockedPending",
    {
      scope: historyBackupScopeText(job.scope_kind),
      eligible: Number(job.eligible_tasks || 0),
    },
  ));
}

function renderHistoryBackupJob(job: HistoryBackupJob | null): void {
  currentBackupJob = job;
  if (historyBackupDownloaded) {
    setHistoryTransferHidden(els.backupScopeFieldset, true);
    setHistoryTransferHidden(els.backupScopeHelp, true);
    setHistoryTransferHidden(els.backupScopeEstimate, true);
    setHistoryTransferHidden(els.backupScopeState, true);
    setHistoryTransferHidden(els.backupProgressSummary, true);
    setHistoryTransferHidden(els.backupWarning, true);
    setHistoryTransferHidden(els.backupComplete, false);
    setHistoryTransferHidden(els.backupStart, true);
    setHistoryTransferHidden(els.backupCancel, true);
    setHistoryTransferHidden(els.backupDownload, true);
    setHistoryTransferHidden(els.backupDismiss, false);
    els.backupDismiss?.classList.remove("ghost-button");
    els.backupDismiss?.classList.add("run-button");
    if (els.backupDismiss) els.backupDismiss.dataset.i18n = "historyBackup.closePanel";
    setText(els.backupDismiss, translate("historyBackup.closePanel"));
    return;
  }
  setHistoryTransferHidden(els.backupScopeFieldset, false);
  setHistoryTransferHidden(els.backupScopeHelp, false);
  setHistoryTransferHidden(els.backupProgressSummary, false);
  setHistoryTransferHidden(els.backupComplete, true);
  els.backupDismiss?.classList.remove("run-button");
  els.backupDismiss?.classList.add("ghost-button");
  const view = historyBackupViewState(job);
  const missingInputWarning = job && Number(job.missing_input_files || 0) > 0
    ? formatTranslation("historyBackup.missingInputsWarning", {
        tasks: Number(job.tasks_with_missing_inputs || 0),
        files: Number(job.missing_input_files || 0),
      })
    : "";
  setHistoryTransferHidden(els.backupWarning, !missingInputWarning);
  setText(els.backupWarning, missingInputWarning);
  setHistoryTransferHidden(els.backupStart, view.active || view.ready);
  setHistoryTransferHidden(els.backupCancel, !view.active);
  setHistoryTransferHidden(els.backupDownload, !view.ready);
  setHistoryTransferHidden(els.backupDismiss, !view.dismissible);
  const dismissKey = view.ready ? "historyBackup.discard" : "historyBackup.dismiss";
  if (els.backupDismiss) els.backupDismiss.dataset.i18n = dismissKey;
  setText(els.backupDismiss, translate(dismissKey));
  if (els.backupScopeFieldset) els.backupScopeFieldset.disabled = view.scopeLocked;
  renderHistoryBackupLockedScope(job);
  renderHistoryBackupScopeEstimates();
  setHistoryTransferHidden(els.backupProgressRegion, view.progressMode === "hidden");
  if (els.backupProgress) {
    if (view.progressMode === "indeterminate") {
      els.backupProgress.removeAttribute("value");
    } else {
      els.backupProgress.value = view.progressValue;
    }
  }
  if (!job) {
    setText(els.backupStats, "");
    setText(els.backupLive, translate("historyBackup.idle"));
    return;
  }
  const totalBytes = Number(job.total_bytes || 0);
  const completedBytes = Number(job.completed_bytes || 0);
  setText(els.backupStats, formatTranslation("historyBackup.stats", {
    total: job.total_tasks || 0,
    eligible: job.eligible_tasks || 0,
    excluded: job.excluded_nonterminal || 0,
    bytes: `${formatHistoryBytes(completedBytes)} / ${formatHistoryBytes(totalBytes)}`,
  }));
  const statusAnnouncement = job.status === "failed"
    ? historyBackupErrorText(String(job.error_code || ""))
    : job.status === "ready"
      ? translate("historyBackup.readyDetail")
      : historyBackupStatusText(job);
  const announcement = missingInputWarning
    ? `${statusAnnouncement} ${missingInputWarning}`
    : statusAnnouncement;
  if (announcement !== lastBackupAnnouncement) {
    setText(els.backupLive, announcement);
    lastBackupAnnouncement = announcement;
  }
}

function renderHistoryBackupDownloaded(): void {
  historyBackupDownloaded = true;
  currentBackupJob = null;
  renderHistoryBackupJob(null);
  lastBackupAnnouncement = translate("historyBackup.downloaded");
  els.backupComplete?.focus();
}

function restoreHistoryDialogFocus(kind: "backup" | "import"): void {
  const target = kind === "backup" ? historyBackupReturnFocus : historyImportReturnFocus;
  target?.focus();
  if (kind === "backup") historyBackupReturnFocus = null;
  else historyImportReturnFocus = null;
}

function syncHistoryTransferModalState(): void {
  const backupOpen = Boolean(els.backupDialog && !els.backupDialog.hidden);
  const importOpen = Boolean(els.importDialog && !els.importDialog.hidden);
  if (els.page) els.page.inert = backupOpen || importOpen;
}

function activeHistoryTransferDialog(): HTMLElement | null {
  if (els.backupDialog && !els.backupDialog.hidden) return els.backupDialog;
  if (els.importDialog && !els.importDialog.hidden) return els.importDialog;
  return null;
}

function trapHistoryTransferFocus(event: KeyboardEvent): boolean {
  if (event.key !== "Tab") return false;
  const dialog = activeHistoryTransferDialog();
  if (!dialog) return false;
  const panel = dialog.querySelector<HTMLElement>(".history-transfer-panel[tabindex]");
  const focusable = [...dialog.querySelectorAll<HTMLElement>(
    'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])',
  )].filter((element) => !element.hidden && !element.closest("[hidden]") && element.getAttribute("aria-hidden") !== "true");
  if (!focusable.length) {
    event.preventDefault();
    panel?.focus();
    return true;
  }
  const first = focusable[0]!;
  const last = focusable[focusable.length - 1]!;
  const active = document.activeElement;
  if (event.shiftKey && (active === first || !dialog.contains(active))) {
    event.preventDefault();
    last.focus();
  } else if (!event.shiftKey && (active === last || !dialog.contains(active))) {
    event.preventDefault();
    first.focus();
  }
  return true;
}

function closeHistoryBackupDialog(options: { restoreFocus?: boolean } = {}): void {
  if (!els.backupDialog) return;
  historyBackupDownloaded = false;
  historyBackupEstimateGeneration += 1;
  setHistoryTransferHidden(els.backupDialog, true);
  els.backupDialog.setAttribute("aria-hidden", "true");
  syncHistoryTransferModalState();
  if (options.restoreFocus !== false) restoreHistoryDialogFocus("backup");
}

function openHistoryBackupDialog(trigger: HTMLElement, taskIds: readonly string[], preferSelected = false): void {
  if (els.importDialog && !els.importDialog.hidden) closeHistoryImportDialog({ restoreFocus: false });
  historyBackupReturnFocus = trigger;
  selectedTaskIdsSnapshot = [...taskIds];
  const selectedCount = selectedTaskIdsSnapshot.length;
  if (els.backupSelectedScope) {
    els.backupSelectedScope.disabled = selectedCount === 0;
    els.backupSelectedScope.checked = preferSelected && selectedCount > 0;
  }
  if (!els.backupSelectedScope?.checked) {
    const filtered = els.backupDialog?.querySelector<HTMLInputElement>('input[name="history-backup-scope"][value="filtered"]');
    if (filtered) filtered.checked = true;
  }
  setHistoryTransferHidden(els.backupDialog, false);
  els.backupDialog?.setAttribute("aria-hidden", "false");
  syncHistoryTransferModalState();
  renderHistoryBackupJob(currentBackupJob);
  if (historyBackupViewState(currentBackupJob).scopeLocked) {
    historyBackupEstimateGeneration += 1;
    historyBackupEstimates.clear();
    historyBackupEstimateStates.clear();
    renderHistoryBackupScopeEstimates();
  } else {
    void loadHistoryBackupScopeEstimates();
  }
  els.backupTitle?.focus();
}

function importGroupItems(preview: HistoryImportPreview, group: string): HistoryImportTaskResult[] {
  if (group === "restorable") return preview.restorable || [];
  if (group === "duplicate") return preview.duplicate || [];
  if (group === "conflict") return preview.conflict || [];
  return preview.invalid || [];
}

const HISTORY_IMPORT_SENSITIVE_REASONS = new Set([
  "backup_import_metadata_contains_sensitive_fields",
  "backup_import_request_contains_sensitive_fields",
]);
const HISTORY_IMPORT_MISMATCH_REASONS = new Set([
  "backup_import_task_fingerprint_mismatch",
  "backup_import_task_id_mismatch",
]);
const HISTORY_IMPORT_INVALID_REASONS = new Set([
  "backup_import_local_task_invalid", "backup_import_raster_invalid",
  "backup_import_reference_file_invalid", "backup_import_task_fingerprint_invalid",
  "backup_import_task_json_invalid", "backup_import_task_json_too_large",
  "backup_import_task_metadata_invalid", "backup_import_task_not_terminal",
  "backup_import_task_organization_invalid", "backup_import_task_required_json_invalid",
  "backup_import_task_required_json_missing",
]);

function historyImportReasonText(reason: string | null | undefined): string {
  if (reason && HISTORY_IMPORT_SENSITIVE_REASONS.has(reason)) return translate("historyImport.reasonSensitive");
  if (reason && HISTORY_IMPORT_MISMATCH_REASONS.has(reason)) return translate("historyImport.reasonMismatch");
  if (reason && HISTORY_IMPORT_INVALID_REASONS.has(reason)) return translate("historyImport.reasonInvalid");
  return translate("historyImport.reasonInvalid");
}

function renderHistoryImportPreview(preview: HistoryImportPreview | null): void {
  currentImportPreview = preview;
  setHistoryTransferHidden(els.importPreview, !preview);
  if (!preview || !els.importPreview) {
    if (els.importConfirm) els.importConfirm.disabled = true;
    setHistoryTransferHidden(els.importConfirm, true);
    return;
  }
  for (const group of ["restorable", "duplicate", "conflict", "invalid"]) {
    const details = els.importPreview.querySelector<HTMLElement>(`[data-history-import-group="${group}"]`);
    const items = importGroupItems(preview, group);
    const summary = details?.querySelector<HTMLElement>("summary");
    if (summary) summary.textContent = `${translate(`historyImport.${group}`)} · ${items.length}`;
    const list = details?.querySelector<HTMLOListElement>("ol");
    if (list) list.innerHTML = items.map((item) => `<li><code>${escapeHtml(item.task_id)}</code>${item.reason ? ` <span class="history-import-reason">${escapeHtml(historyImportReasonText(item.reason))}</span>` : ""}</li>`).join("");
  }
  const canRestore = preview.restorable.length > 0;
  if (els.importConfirm) els.importConfirm.disabled = !canRestore;
  setHistoryTransferHidden(els.importConfirm, false);
  setHistoryTransferHidden(els.importCancel, false);
}

function renderHistoryImportResult(result: HistoryImportResult | null): void {
  currentImportResult = result;
  setHistoryTransferHidden(els.importResult, !result);
  if (!result || !els.importResult) return;
  const values: Record<string, HistoryImportTaskResult[] | undefined> = {
    restored: result.restored, duplicates: result.duplicates, conflicts: result.conflicts,
    invalid: result.invalid, failed: result.failed, thumbnail_warnings: result.thumbnail_warnings,
    cleanup_warnings: result.cleanup_warnings,
  };
  for (const [key, items] of Object.entries(values)) {
    setText(els.importResult.querySelector<HTMLElement>(`[data-history-import-result="${key}"] dd`), String(items?.length || 0));
  }
}

function historyImportPhaseText(phase: HistoryImportPhase): string {
  const key = phase === "idle"
    ? "historyBackup.idle"
    : phase === "creating"
      ? "historyImport.uploading"
      : `historyImport.${phase}`;
  return translate(key);
}

function renderHistoryImportPhase(phase: HistoryImportPhase): void {
  currentImportPhase = phase;
  setText(els.importLive, historyImportPhaseText(phase));
  const restoring = phase === "restoring";
  const cancellable = ["creating", "uploading", "validating", "validated"].includes(phase);
  setHistoryTransferHidden(els.importCancel, !cancellable || restoring);
  if (els.importFile) els.importFile.disabled = restoring;
}

function closeHistoryImportDialog(options: { restoreFocus?: boolean } = {}): void {
  if (!els.importDialog) return;
  setHistoryTransferHidden(els.importDialog, true);
  els.importDialog.setAttribute("aria-hidden", "true");
  syncHistoryTransferModalState();
  if (options.restoreFocus !== false) restoreHistoryDialogFocus("import");
}

function openHistoryImportDialog(trigger: HTMLElement): void {
  if (els.backupDialog && !els.backupDialog.hidden) closeHistoryBackupDialog({ restoreFocus: false });
  historyImportReturnFocus = trigger;
  setHistoryTransferHidden(els.importDialog, false);
  els.importDialog?.setAttribute("aria-hidden", "false");
  syncHistoryTransferModalState();
  renderHistoryImportPhase(currentImportPhase);
  renderHistoryImportPreview(currentImportPreview);
  renderHistoryImportResult(currentImportResult);
  els.importTitle?.focus();
}

const backupController = createHistoryBackupController({
  onStatus: (job) => renderHistoryBackupJob(job),
  onError: (error) => {
    const message = historyBackupErrorText(error.code);
    if (!isTransientHistoryBackupError(error.status)) {
      currentBackupJob = null;
      renderHistoryBackupJob(null);
    }
    focusHistoryTransferError("backup", message);
  },
});

const importController = createHistoryImportController({
  onPhase: (phase) => renderHistoryImportPhase(phase),
  onProgress: (uploaded, total) => {
    if (els.importProgress) els.importProgress.value = total > 0 ? Math.min(100, Math.round(uploaded * 100 / total)) : 0;
  },
});

async function startHistoryBackup(): Promise<void> {
  const scope = historyBackupScope();
  if (scope.kind === "selected" && !scope.taskIds.length) return;
  historyBackupDownloaded = false;
  try {
    await backupController.start(scope);
  } catch (error) {
    if (!(error instanceof DOMException && error.name === "AbortError")) {
      focusHistoryTransferError("backup", historyBackupErrorText(String((error as { code?: string })?.code || "")));
    }
  }
}

async function cancelActiveHistoryBackup(): Promise<void> {
  try {
    await backupController.cancel();
  } catch (error) {
    focusHistoryTransferError("backup", historyBackupErrorText(String((error as { code?: string })?.code || "")));
  }
}

async function dismissHistoryBackupResult(): Promise<void> {
  const job = currentBackupJob;
  if (!job || !els.backupDismiss) return;
  els.backupDismiss.disabled = true;
  try {
    if (await backupController.dismiss(job.job_id)) {
      currentBackupJob = null;
      closeHistoryBackupDialog();
    }
  } catch (error) {
    focusHistoryTransferError("backup", historyBackupErrorText(String((error as { code?: string })?.code || "")));
  } finally {
    els.backupDismiss.disabled = false;
  }
}

function clearHistoryImportUI(): void {
  resumableImportSession = null;
  historyImportResumePending = false;
  currentImportPreview = null;
  currentImportResult = null;
  renderHistoryImportPreview(null);
  renderHistoryImportResult(null);
  if (els.importConfirm) els.importConfirm.disabled = true;
  setHistoryTransferHidden(els.importConfirm, true);
  if (els.importFile) {
    els.importFile.value = "";
    els.importFile.disabled = false;
  }
  if (els.importProgress) els.importProgress.value = 0;
}

async function cancelActiveHistoryImport(): Promise<boolean> {
  try {
    await importController.cancel();
    clearHistoryImportUI();
    renderHistoryImportPhase("cancelled");
    return true;
  } catch {
    focusHistoryTransferError("import", translate("historyImport.failed"));
    return false;
  }
}

async function chooseHistoryImport(file: File): Promise<void> {
  const resumePending = historyImportResumePending;
  currentImportPreview = null;
  currentImportResult = null;
  renderHistoryImportPreview(null);
  renderHistoryImportResult(null);
  try {
    let preview: HistoryImportPreview | null;
    if (historyImportResumePending) {
      preview = await importController.resumeUpload(file, file.name);
    } else {
      if (importController.activeSessionId() && !await cancelActiveHistoryImport()) return;
      preview = await importController.start(file, file.name);
    }
    if (!preview) return;
    historyImportResumePending = false;
    renderHistoryImportPreview(preview);
  } catch (error) {
    if (!(error instanceof DOMException && error.name === "AbortError")) {
      const activeSessionId = importController.activeSessionId();
      historyImportResumePending = Boolean(activeSessionId);
      if (activeSessionId && !resumePending) {
        resumableImportSession = {
          session_id: activeSessionId,
          filename: file.name,
          size_bytes: file.size,
          uploaded_bytes: 0,
          status: "uploading",
        };
      }
      focusHistoryTransferError("import", translate("historyImport.reselect"));
      if (els.importFile) els.importFile.disabled = false;
    }
  }
}

async function restoreHistoryImportSelection(): Promise<void> {
  if (!currentImportPreview?.restorable.length) return;
  setHistoryTransferHidden(els.importCancel, true);
  const terminalSessionId = importController.activeSessionId();
  try {
    const result = await importController.restore();
    if (!result) return;
    resumableImportSession = null;
    historyImportResumePending = false;
    renderHistoryImportResult(result);
    renderHistoryImportPreview(null);
    if (terminalSessionId) {
      await importController.acknowledgeTerminalAfterRefresh(
        terminalSessionId,
        refreshHistoryAfterImport,
      );
    } else {
      await refreshHistoryAfterImport();
    }
  } catch {
    renderHistoryImportPhase("failed");
    focusHistoryTransferError("import", translate("historyImport.failed"));
  }
}

async function resumeHistoryTransfers(): Promise<void> {
  try { await backupController.resume(); } catch { /* retained state remains available */ }
  try {
    const session = await importController.resume();
    if (!session) return;
    resumableImportSession = session;
    if ((session.status === "restored" || session.status === "failed") && session.result) {
      renderHistoryImportResult(session.result);
      renderHistoryImportPreview(null);
      renderHistoryImportPhase(session.status === "failed" ? "failed" : "restored");
      const acknowledged = await importController.acknowledgeTerminalAfterRefresh(
        session.session_id,
        refreshHistoryAfterImport,
      );
      if (acknowledged) resumableImportSession = null;
    } else if (session.status === "uploaded" || session.status === "validated") {
      const preview = await importController.resumeValidate();
      if (preview) renderHistoryImportPreview(preview);
    } else if (session.status === "uploading") {
      historyImportResumePending = true;
      renderHistoryImportPhase("uploading");
      setText(els.importLive, translate("historyImport.reselect"));
    } else if (session.status === "restored") {
      renderHistoryImportPhase("restored");
    } else {
      renderHistoryImportPhase(session.status === "interrupted" ? "interrupted" : "failed");
    }
  } catch {
    setText(els.importLive, translate("historyImport.failed"));
  }
}

function applyHistoryLocale(): void {
  document.title = historyDocumentTitle();
}

function historyDocumentTitle(): string {
  return webAppDocumentTitle(translate("history.title"), translate("history.documentTitle"));
}

function truncateText(value: unknown, limit: number): string {
  const text = String(value || "").replace(/\s+/g, " ").trim();
  return text.length <= limit ? text : text.slice(0, limit - 1).trimEnd() + "…";
}

function historyFilterAttribute(key: HistoryFilterKey): string {
  return key.replace(/_/g, "-");
}

function facetDisplayValue(key: HistoryFilterKey, value: string): string {
  if (key === "mode") {
    if (value === "generate") return translate("history.type.textToImage");
    if (value === "edit") return translate("history.type.imageToImage");
  }
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
  if (key === "orientation") {
    if (value === "portrait") return translate("output.portrait");
    if (value === "landscape") return translate("output.landscape");
    if (value === "square") return translate("output.square");
  }
  if (key === "ratio" && value === HISTORY_RATIO_OTHER_VALUE) return translate("history.ratioOther");
  return value;
}

function currentHistoryActiveFilterSnapshot(): HistoryActiveFilterSnapshot {
  const filters: HistoryActiveFilterSnapshot["filters"] = {};
  for (const key of HISTORY_FILTER_QUERY_KEYS) {
    filters[key] = historyState[key];
  }
  return {
    q: historyState.q,
    filters,
    organization: {
      favorite: historyOrganizationFilters.favorite,
      tagIds: [...historyOrganizationFilters.tagIds],
      untagged: historyOrganizationFilters.untagged,
    },
  };
}

function historyActiveFilterTitle(key: HistoryFilterKey): string {
  const translationKeys: Record<HistoryFilterKey, string> = {
    mode: "history.type",
    month: "history.month",
    prompt_mode: "history.promptMode",
    quality: "history.quality",
    ratio: "history.ratio",
    orientation: "history.orientation",
    backend: "history.backend",
    provider: "history.provider",
    archived: "history.archived",
  };
  return translate(translationKeys[key]);
}

function historyActiveFilterLabel(
  item: HistoryActiveFilterItem,
): string {
  if (item.kind === "q") {
    return `${translate("history.search")} · ${item.value}`;
  }
  if (item.kind === "favorite") {
    return translate("history.onlyFavorites");
  }
  if (item.kind === "untagged") {
    return translate("history.untagged");
  }
  if (item.kind === "tag") {
    const name = historyTags.find(
      (tag) => tag.tag_id === item.value,
    )?.name || item.value;
    return `${translate("history.tags")} · ${name}`;
  }
  const value = item.key === "archived"
    ? item.value === "true"
      ? translate("history.archivedOnly")
      : translate("history.unarchived")
    : facetDisplayValue(item.key, item.value);
  return `${historyActiveFilterTitle(item.key)} · ${value}`;
}

function renderHistoryActiveFilters(): void {
  const items = collectHistoryActiveFilters(
    currentHistoryActiveFilterSnapshot(),
  );
  const count = items.length;
  const hidden = count === 0;
  els.activeFilters?.classList.toggle("hidden", hidden);
  els.activeFilters?.toggleAttribute("hidden", hidden);
  els.activeFilters?.setAttribute(
    "aria-label",
    hidden
      ? translate("sidebar.filters")
      : formatTranslation("history.activeFilterCount", { count }),
  );
  setText(
    els.activeFiltersLabel,
    hidden
      ? ""
      : formatTranslation("history.activeFilterCount", { count }),
  );
  setText(els.clearAllFilters, translate("history.clearAllFilters"));
  if (els.activeFilterList) {
    els.activeFilterList.innerHTML = items.map((item) => {
      const label = historyActiveFilterLabel(item);
      const removeLabel = formatTranslation(
        "history.removeFilter",
        { label },
      );
      return `
        <span class="history-active-filter-item" role="listitem">
          <button
            class="history-active-filter-chip"
            type="button"
            data-history-remove-active-filter="${escapeHtml(item.id)}"
            aria-label="${escapeHtml(removeLabel)}"
            title="${escapeHtml(removeLabel)}"
          >
            <span class="history-active-filter-chip-label">${escapeHtml(label)}</span>
            <svg class="history-active-filter-chip-icon" viewBox="0 0 16 16" aria-hidden="true" focusable="false"><path d="m4 4 8 8m0-8-8 8" /></svg>
          </button>
        </span>
      `;
    }).join("");
  }
  els.mobileFilterCount?.classList.toggle("hidden", hidden);
  els.mobileFilterCount?.toggleAttribute("hidden", hidden);
  setText(els.mobileFilterCount, hidden ? "" : String(count));
  els.mobileFiltersButton?.classList.toggle(
    "has-active-filters",
    !hidden,
  );
  els.mobileFiltersButton?.setAttribute(
    "aria-label",
    hidden
      ? translate("sidebar.filters")
      : formatTranslation("history.filtersActive", { count }),
  );
}

function syncHistoryFilterButtonsFromState(): void {
  for (const key of HISTORY_FILTER_QUERY_KEYS) {
    const attr = historyFilterAttribute(key);
    document
      .querySelectorAll<HTMLElement>(`[data-history-${attr}]`)
      .forEach((button) => {
        button.classList.toggle(
          "active",
          button.getAttribute(`data-history-${attr}`) ===
            historyState[key],
        );
      });
  }
}

function applyHistoryActiveFilterSnapshot(
  snapshot: HistoryActiveFilterSnapshot,
): void {
  historyState.q = snapshot.q;
  for (const key of HISTORY_FILTER_QUERY_KEYS) {
    historyState[key] = String(snapshot.filters[key] || "");
  }
  historyOrganizationFilters = {
    favorite: snapshot.organization.favorite,
    tagIds: [...snapshot.organization.tagIds],
    untagged: snapshot.organization.untagged,
  };
  resetHistoryTaskSelectionState();
  clearHistoryDeleteConfirmation();
  if (els.search) els.search.value = historyState.q;
  syncHistorySearchClear();
  syncHistoryFilterButtonsFromState();
  renderHistoryOrganizationFilters();
  renderHistoryActiveFilters();
  updateHistoryUrl();
  void loadTasks({ reset: true });
}

function removeHistoryActiveFilterById(id: string): void {
  const snapshot = currentHistoryActiveFilterSnapshot();
  const item = collectHistoryActiveFilters(snapshot).find(
    (candidate) => candidate.id === id,
  );
  if (!item) return;
  applyHistoryActiveFilterSnapshot(
    removeHistoryActiveFilter(snapshot, item),
  );
}

function clearAllHistoryActiveFilters(): void {
  applyHistoryActiveFilterSnapshot(
    clearHistoryActiveFilters(
      currentHistoryActiveFilterSnapshot(),
    ),
  );
}

function historyOrientationIconHtml(value: string): string {
  if (value === "portrait") {
    return `<svg class="history-filter-icon history-filter-icon-portrait" viewBox="0 0 20 20" aria-hidden="true" focusable="false">
        <rect x="6.5" y="3" width="7" height="14" rx="2"></rect>
      </svg>`;
  }
  if (value === "landscape") {
    return `<svg class="history-filter-icon history-filter-icon-landscape" viewBox="0 0 20 20" aria-hidden="true" focusable="false">
        <rect x="3" y="6.5" width="14" height="7" rx="2"></rect>
      </svg>`;
  }
  if (value === "square") {
    return `<svg class="history-filter-icon history-filter-icon-square" viewBox="0 0 20 20" aria-hidden="true" focusable="false">
        <rect x="5" y="5" width="10" height="10" rx="2"></rect>
      </svg>`;
  }
  return `<svg class="history-filter-icon history-filter-icon-all" viewBox="0 0 20 20" aria-hidden="true" focusable="false">
      <rect x="3.5" y="4" width="5" height="8" rx="1.5"></rect>
      <rect x="10.5" y="5" width="6" height="4.5" rx="1.4"></rect>
      <rect x="10.5" y="11.5" width="5" height="5" rx="1.4"></rect>
    </svg>`;
}

function historyFilterButtonLabelHtml(key: HistoryFilterKey, label: string, value = ""): string {
  if (key !== "orientation") return escapeHtml(label);
  return `${historyOrientationIconHtml(value)}<span class="history-filter-label">${escapeHtml(label)}</span>`;
}

function syncStateFromUrl(): void {
  const params = new URLSearchParams(window.location.search);
  historyOrganizationFilters =
    readHistoryOrganizationFilters(params);
  historyState.q = params.get("q") || "";
  historyState.sort = params.get("sort") === "oldest" ? "oldest" : "newest";
  historyState.view = params.get("view") === "list" ? "list" : "grid";
  for (const key of HISTORY_FILTER_QUERY_KEYS) {
    historyState[key] = params.get(key) || "";
  }
  for (const key of ["backend", "provider"] as const) {
    const section = document.querySelector<HTMLDetailsElement>(`[data-history-filter-section="${key}"]`);
    if (section && historyState[key]) section.open = true;
  }
  historyState.selectedTaskId = params.get("task") || "";
  historyState.selectedTaskIds = historyState.selectedTaskId
    ? new Set([historyState.selectedTaskId])
    : new Set();
  historyState.selectionAnchorTaskId = historyState.selectedTaskId;
  historyState.selectionMode = false;
  if (els.search) els.search.value = historyState.q;
  syncHistorySearchClear();
  syncHistorySortMode();
  syncHistoryViewMode();
  renderHistoryActiveFilters();
}

function syncHistorySearchClear(): void {
  const hasQuery = Boolean(els.search?.value.trim());
  els.searchClear?.classList.toggle("hidden", !hasQuery);
  els.searchClear?.toggleAttribute("hidden", !hasQuery);
}

function updateHistoryUrl(): void {
  const params = new URLSearchParams();
  if (historyState.q) params.set("q", historyState.q);
  if (historyState.sort !== "newest") params.set("sort", historyState.sort);
  if (historyState.view !== "grid") params.set("view", historyState.view);
  for (const key of HISTORY_FILTER_QUERY_KEYS) {
    if (historyState[key]) params.set(key, historyState[key]);
  }
  writeHistoryOrganizationFilters(
    params,
    historyOrganizationFilters,
  );
  if (historyState.selectedTaskId) params.set("task", historyState.selectedTaskId);
  const query = params.toString();
  const nextUrl = query ? `${window.location.pathname}?${query}` : window.location.pathname;
  window.history.replaceState(null, "", nextUrl);
}

function saveCurrentHistoryLocation(
  anchor: NonNullable<HistoryScrollAnchor>,
): void {
  updateHistoryUrl();
  saveHistoryLocationSnapshot({
    version: 1,
    query: historySnapshotQuery(
      new URLSearchParams(window.location.search),
    ),
    anchor,
    savedAt: Date.now(),
  });
}

async function loadSummary(options: { throwOnError?: boolean } = {}): Promise<void> {
  try {
    const response = await fetch("/api/task-history/summary");
    const summary = await response.json() as HistorySummary;
    if (!response.ok) throw new Error((summary as any).detail || translate("history.summaryFailed"));
    if (!historyOrganizationSummarySupported(summary)) {
      historyOrganizationApiSupported = false;
      throw new Error(
        translate("history.backendRestartRequired"),
      );
    }
    historyOrganizationApiSupported = true;
    historySummary = summary;
    historyTags = Array.isArray(summary.tags) ? summary.tags : [];
    setText(els.total, formatTranslation("history.total", { total: summary.total, archived: summary.archived_total }));
    renderHistoryOrganizationFilters(summary);
    renderHistoryTagManager();
    renderFacetButtons(els.modeList, "mode", summary.modes || [], translate("history.allTypes"));
    renderFacetButtons(els.monthList, "month", summary.months.map((item) => ({ value: item.month, count: item.count })), translate("history.allMonths"));
    renderFacetButtons(els.promptModeList, "prompt_mode", summary.prompt_modes || [], translate("history.allPromptModes"));
    renderFacetButtons(els.qualityList, "quality", summary.qualities || [], translate("history.allQualities"));
    renderFacetButtons(els.ratioList, "ratio", summary.ratios, translate("history.allRatios"));
    renderFacetButtons(els.orientationList, "orientation", summary.orientations || [], translate("history.allOrientations"));
    renderFacetButtons(els.backendList, "backend", summary.backends || [], translate("history.allBackends"));
    renderFacetButtons(els.providerList, "provider", summary.providers || [], translate("history.allProviders"));
    syncArchiveButtons();
    renderHistoryActiveFilters();
  } catch (error) {
    const message = errorMessage(
      error,
      translate("history.summaryFailed"),
    );
    setText(els.total, message);
    if (historyOrganizationApiSupported === false) {
      setText(els.resultSummary, message);
    }
    if (options.throwOnError) throw error;
  }
}

function renderHistoryOrganizationFilters(
  summary?: Partial<HistorySummary>,
): void {
  const counts = summary || historySummary || {};
  if (els.favoriteList) {
    const active = historyOrganizationFilters.favorite;
    els.favoriteList.innerHTML = `
      <button
        class="history-filter-button${active ? " active" : ""}"
        type="button"
        data-history-favorite-filter
        aria-pressed="${active ? "true" : "false"}"
      >
        <span>${escapeHtml(translate("history.onlyFavorites"))}</span>
        <span class="history-filter-count">${Number(counts.favorite_total || 0)}</span>
      </button>
    `;
  }
  if (!els.tagFilterList) return;
  const selected = new Set(historyOrganizationFilters.tagIds);
  const untaggedActive = historyOrganizationFilters.untagged;
  els.tagFilterList.innerHTML = [
    `
      <button
        class="history-filter-button${untaggedActive ? " active" : ""}"
        type="button"
        data-history-untagged-filter
        aria-pressed="${untaggedActive ? "true" : "false"}"
      >
        <span>${escapeHtml(translate("history.untagged"))}</span>
        <span class="history-filter-count">${Number(counts.untagged_total || 0)}</span>
      </button>
    `,
    ...historyTags.map((tag) => {
      const active = selected.has(tag.tag_id);
      return `
        <button
          class="history-filter-button${active ? " active" : ""}"
          type="button"
          data-history-tag-filter="${escapeHtml(tag.tag_id)}"
          aria-pressed="${active ? "true" : "false"}"
        >
          <span>${escapeHtml(tag.name)}</span>
          <span class="history-filter-count">${Number(tag.count || 0)}</span>
        </button>
      `;
    }),
  ].join("");
}

function renderHistoryTagManager(): void {
  if (!els.tagManagerList) return;
  if (!historyTags.length) {
    els.tagManagerList.innerHTML = `
      <div class="history-tag-manager-empty">
        ${escapeHtml(translate("history.noTags"))}
      </div>
    `;
    return;
  }
  els.tagManagerList.innerHTML = historyTags
    .map((tag) => {
      const confirming =
        historyTagDeleteConfirmId === tag.tag_id;
      const affectedDeleteLabel = formatTranslation(
        "history.deleteTagAffected",
        {
          count: Number(tag.count || 0),
        },
      );
      const deleteLabel = confirming
        ? translate("history.confirmDelete")
        : translate("history.deleteTag");
      const deleteAriaLabel = confirming
        ? affectedDeleteLabel
        : deleteLabel;
      return `
        <div class="history-tag-manager-row" data-history-tag-row="${escapeHtml(tag.tag_id)}">
          <div class="history-tag-manager-row-field">
            <input
              class="control"
              type="text"
              maxlength="40"
              value="${escapeHtml(tag.name)}"
              data-history-tag-name="${escapeHtml(tag.tag_id)}"
              aria-label="${escapeHtml(translate("history.renameTag"))}"
            />
            <span class="history-filter-count">${Number(tag.count || 0)}</span>
          </div>
          <div class="history-tag-manager-row-actions">
            <button
              class="ghost-button text-sm"
              type="button"
              data-history-rename-tag="${escapeHtml(tag.tag_id)}"
            >${escapeHtml(translate("history.renameTag"))}</button>
            <button
              class="ghost-button text-sm${confirming ? " danger-button" : ""}"
              type="button"
              data-history-delete-tag="${escapeHtml(tag.tag_id)}"
              aria-label="${escapeHtml(deleteAriaLabel)}"
              title="${escapeHtml(deleteAriaLabel)}"
            >${escapeHtml(deleteLabel)}</button>
          </div>
        </div>
      `;
    })
    .join("");
}

function applyHistoryOrganizationFilterChange(
  filters: HistoryOrganizationFilters,
): void {
  if (historyOrganizationApiSupported === false) {
    setText(
      els.resultSummary,
      translate("history.backendRestartRequired"),
    );
    return;
  }
  historyOrganizationFilters = filters;
  resetHistoryTaskSelectionState();
  clearHistoryDeleteConfirmation();
  renderHistoryOrganizationFilters();
  renderHistoryActiveFilters();
  updateHistoryUrl();
  void loadTasks({ reset: true });
}

function historyTagMutationErrorMessage(
  error: unknown,
): string {
  if (
    error instanceof HistoryOrganizationRequestError &&
    error.status === 409
  ) {
    return translate("history.tagNameConflict");
  }
  return errorMessage(
    error,
    translate("history.organizationFailed"),
  );
}

function historyTagCreateErrorMessage(
  error: unknown,
): string {
  if (
    error instanceof HistoryOrganizationRequestError &&
    error.status === 404
  ) {
    return translate("history.backendRestartRequired");
  }
  return historyTagMutationErrorMessage(error);
}

async function createHistoryTagFromManager(): Promise<void> {
  if (historyTagManagerCreatePending) return;
  const name = els.tagNameInput?.value.trim() || "";
  if (!name) {
    els.tagNameInput?.focus();
    return;
  }
  const form = els.tagManager?.querySelector<HTMLFormElement>(
    "[data-history-tag-create]",
  );
  const controls = form?.querySelectorAll<
    HTMLInputElement | HTMLButtonElement
  >("input, button");
  historyTagManagerCreatePending = true;
  controls?.forEach((control) => {
    control.disabled = true;
  });
  setText(els.tagManagerStatus, "");
  try {
    const tag = await createHistoryTag(name);
    if (els.tagNameInput) els.tagNameInput.value = "";
    await loadSummary();
    setText(
      els.tagManagerStatus,
      `${translate("history.createTag")}：${tag.name}`,
    );
  } catch (error) {
    const message = historyTagCreateErrorMessage(error);
    setText(els.tagManagerStatus, message);
    setText(
      els.resultSummary,
      message,
    );
  } finally {
    historyTagManagerCreatePending = false;
    controls?.forEach((control) => {
      control.disabled = false;
    });
  }
}

async function renameHistoryTagFromManager(
  tagId: string,
): Promise<void> {
  const input = els.tagManagerList?.querySelector<HTMLInputElement>(
    `[data-history-tag-name="${CSS.escape(tagId)}"]`,
  );
  const name = input?.value.trim() || "";
  if (!name) return;
  try {
    const tag = await renameHistoryTag(tagId, name);
    const organizations: Record<string, HistoryOrganization> = {};
    for (const [taskId, task] of historyState.loadedTaskSummaries) {
      if (!task.tags.some((item) => item.tag_id === tagId)) {
        continue;
      }
      organizations[taskId] = {
        favorite: task.favorite,
        tags: task.tags.map((item) =>
          item.tag_id === tagId
            ? { ...item, name: tag.name }
            : item
        ),
      };
    }
    applyHistoryOrganizations(organizations);
    await loadSummary();
  } catch (error) {
    setText(
      els.resultSummary,
      historyTagMutationErrorMessage(error),
    );
  }
}

async function deleteHistoryTagFromManager(
  tagId: string,
): Promise<void> {
  if (historyTagDeleteConfirmId !== tagId) {
    historyTagDeleteConfirmId = tagId;
    renderHistoryTagManager();
    return;
  }
  try {
    await deleteHistoryTag(tagId);
    historyTagDeleteConfirmId = "";
    historyOrganizationFilters = {
      ...historyOrganizationFilters,
      tagIds: historyOrganizationFilters.tagIds.filter(
        (value) => value !== tagId,
      ),
    };
    const organizations: Record<string, HistoryOrganization> = {};
    for (const [taskId, task] of historyState.loadedTaskSummaries) {
      organizations[taskId] = {
        favorite: task.favorite,
        tags: task.tags.filter(
          (item) => item.tag_id !== tagId,
        ),
      };
    }
    applyHistoryOrganizations(organizations);
    updateHistoryUrl();
    await loadSummary();
  } catch (error) {
    setText(
      els.resultSummary,
      errorMessage(
        error,
        translate("history.organizationFailed"),
      ),
    );
  }
}

function renderFacetButtons(root: HTMLElement | null, key: HistoryFilterKey, items: HistoryFacet[], allLabel: string): void {
  if (!root) return;
  const current = String(historyState[key] || "");
  const attr = historyFilterAttribute(key);
  root.innerHTML = [
    `<button class="history-filter-button ${current ? "" : "active"}" type="button" data-history-filter-key="${key}" data-history-${attr}="">${historyFilterButtonLabelHtml(key, allLabel)}</button>`,
    ...items.map((item) => {
      const active = current === item.value ? " active" : "";
      return `<button class="history-filter-button${active}" type="button" data-history-filter-key="${key}" data-history-${attr}="${escapeHtml(item.value)}">${historyFilterButtonLabelHtml(key, facetDisplayValue(key, item.value), item.value)}<span class="history-filter-count">${item.count}</span></button>`;
    }),
  ].join("");
}

function syncArchiveButtons(): void {
  document.querySelectorAll<HTMLElement>("[data-history-archived]").forEach((button) => {
    button.classList.toggle("active", button.getAttribute("data-history-archived") === historyState.archived);
  });
}

function syncHistorySortMode(): void {
  const sort = historyState.sort === "oldest" ? "oldest" : "newest";
  historyState.sort = sort;
  els.sortToggle?.querySelectorAll<HTMLElement>("[data-history-sort]").forEach((button) => {
    const active = button.dataset.historySort === sort;
    button.classList.toggle("active", active);
    button.setAttribute("aria-pressed", active ? "true" : "false");
  });
}

function applyHistorySort(sort: string): void {
  const nextSort = sort === "oldest" ? "oldest" : "newest";
  if (historyState.sort === nextSort) return;
  historyState.sort = nextSort;
  resetHistoryTaskSelectionState();
  syncHistorySortMode();
  updateHistoryUrl();
  void loadTasks({ reset: true });
}

function historyPageQueryInput(
  cursor?: string | null,
  direction: HistoryWindowDirection = "next",
  anchorTaskId = "",
): HistoryPageQueryInput {
  const filters: HistoryPageQueryInput["filters"] = {};
  for (const key of HISTORY_FILTER_QUERY_KEYS) {
    if (historyState[key]) filters[key] = historyState[key];
  }
  return {
    limit: HISTORY_PAGE_LIMIT,
    sort: historyState.sort,
    cursor,
    direction,
    anchorTaskId,
    q: historyState.q,
    filters,
    organization: historyOrganizationFilters,
  };
}

function queryParams(
  cursor?: string | null,
  direction: HistoryWindowDirection = "next",
  anchorTaskId = "",
): string {
  return historyTaskPageQuery(
    historyPageQueryInput(cursor, direction, anchorTaskId),
  );
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
  if (window.matchMedia("(max-width: 600px)").matches) {
    return { targetHeight: 220, minWidth: 132, maxWidth: 320, maxItems: 2 };
  }
  if (window.matchMedia("(max-width: 760px)").matches) {
    return { targetHeight: 176, minWidth: 132, maxWidth: 320 };
  }
  return { targetHeight: 220, minWidth: 150, maxWidth: 430 };
}

function historyTaskCardElement(taskId: string): HTMLElement | null {
  if (!taskId || !els.taskList) return null;
  return historyTaskCards(els.taskList).find((card) => card.dataset.historyTaskCardId === taskId) || null;
}

function isHistoryTaskCardVisible(taskId: string): boolean {
  const list = els.taskList;
  const card = historyTaskCardElement(taskId);
  if (!list || !card) return false;
  const listRect = list.getBoundingClientRect();
  const cardRect = card.getBoundingClientRect();
  return cardRect.bottom > listRect.top
    && cardRect.top < listRect.bottom
    && cardRect.right > listRect.left
    && cardRect.left < listRect.right;
}

function activeHistoryTaskVisible(): string {
  const taskId = historyState.selectedTaskId;
  return taskId && isHistoryTaskCardVisible(taskId) ? taskId : "";
}

function ensureHistoryTaskCardVisible(taskId: string): void {
  historyTaskCardElement(taskId)?.scrollIntoView({ block: "nearest", inline: "nearest" });
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
  closeHistoryContextMenu();
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
  for (const resizer of [els.leftResizer, els.rightResizer]) {
    const side = resizer?.dataset.historyResizer as HistoryResizerSide | undefined;
    if (!resizer || (side !== "left" && side !== "right")) continue;
    resizer.addEventListener("pointerdown", (event) => startHistoryResize(side, event, resizer));
    resizer.addEventListener("lostpointercapture", endHistoryResize);
    resizer.addEventListener("dblclick", () => resetHistoryLayoutSide(side));
    resizer.addEventListener("keydown", (event) => {
      if (!isHistoryResizableLayout()) return;
      if (!resizeHistoryLayoutByKeyboard(side, event)) return;
      event.preventDefault();
      event.stopPropagation();
    });
  }
  window.addEventListener("pointermove", updateHistoryResize);
  window.addEventListener("pointerup", endHistoryResize);
  window.addEventListener("pointercancel", endHistoryResize);
  window.addEventListener("blur", endHistoryResize);
  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "hidden") endHistoryResize();
  });
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
    if (historyState.view !== "grid" || !historyGridLayoutIsIncomplete(root)) return;
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
  if (!root || historyState.view !== "grid" || !root.classList.contains("history-view-grid")) return null;
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
  options: HistoryGridLayoutOptions = EMPTY_HISTORY_GRID_LAYOUT_OPTIONS,
): void {
  const snapshot = options.snapshot === undefined
    ? captureHistoryGridLayoutSnapshot()
    : options.snapshot;
  if (!snapshot) return;
  const availableWidth = options.availableWidth ?? snapshot.availableWidth;
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

async function loadTasks(
  {
    reset = false,
    direction = "next",
    anchorTaskId: rawAnchorTaskId = "",
    anchor = null,
    throwOnError = false,
  }: HistoryLoadOptions & { throwOnError?: boolean } = {},
): Promise<HistoryLoadResult> {
  const emptyResult: HistoryLoadResult = {
    anchorFound: null,
    taskCount: 0,
  };
  const anchorTaskId = String(rawAnchorTaskId || "").trim();
  if (anchorTaskId && (!reset || direction !== "next")) {
    return emptyResult;
  }
  if (historyState.loading && !reset) return emptyResult;
  if (!reset && direction === "next" && historyState.exhausted) {
    return emptyResult;
  }
  if (!reset && direction === "previous" && historyState.newerExhausted) {
    return emptyResult;
  }
  const cursor = taskWindowCursor(reset, direction);
  if (!reset && !cursor) {
    if (direction === "previous") historyState.newerExhausted = true;
    if (direction === "next") historyState.exhausted = true;
    return emptyResult;
  }
  historyState.loading = true;
  const requestId = ++historyState.requestId;
  if (reset) {
    historyState.nextCursor = null;
    historyState.newerExhausted = true;
    historyState.exhausted = false;
    historyState.loadedTaskIds.clear();
    historyState.loadedTaskSummaries.clear();
    historyState.selectedTaskIds = historyState.selectedTaskId
      ? new Set([historyState.selectedTaskId])
      : new Set();
    historyState.selectionAnchorTaskId = historyState.selectedTaskId;
    historyState.selectionMode = false;
    clearHistoryDeleteConfirmation();
    historyState.deleteConfirmTaskId = "";
    if (els.taskList) els.taskList.innerHTML = "";
    renderBulkToolbar();
  }
  setLoadMoreState(translate("history.loadingMore"), { busy: true });
  try {
    const organizationFilterActive =
      historyOrganizationFilters.favorite ||
      historyOrganizationFilters.untagged ||
      historyOrganizationFilters.tagIds.length > 0;
    if (
      organizationFilterActive &&
      historyOrganizationApiSupported === false
    ) {
      throw new Error(
        translate("history.backendRestartRequired"),
      );
    }
    const requestPage = async (url: string): Promise<HistoryTaskPage> => {
      const response = await fetch(url);
      const data = await response.json() as HistoryTaskPage;
      if (!response.ok) {
        throw new Error(data.detail || translate("history.tasksFailed"));
      }
      return data;
    };
    const validateOrganizationRows = (tasks: HistoryTask[]): void => {
      if (
        organizationFilterActive &&
        !historyTaskRowsSupportOrganization(tasks)
      ) {
        historyOrganizationApiSupported = false;
        throw new Error(
          translate("history.backendRestartRequired"),
        );
      }
    };
    if (anchorTaskId) {
      const result = await loadHistoryAnchorPage({
        query: historyPageQueryInput(cursor, direction, anchorTaskId),
        anchor,
        request: requestPage,
        isCurrent: () => requestId === historyState.requestId,
        validate: validateOrganizationRows,
        render: (tasks) => renderTasks(tasks, { position: "replace" }),
        applyCursors: (previousCursor, nextCursor) => {
          historyState.newerExhausted = !previousCursor;
          historyState.nextCursor = nextCursor;
          historyState.exhausted = !nextCursor;
        },
        requestFrame: (callback) => window.requestAnimationFrame(callback),
        restore: (scrollAnchor) => {
          if (els.taskList) {
            restoreHistoryScrollAnchor(els.taskList, scrollAnchor);
          }
        },
        enableSave: () => historyPositionSaveController.enable(),
      });
      if (result.anchorFound !== true) return result;
      setLoadMoreState(
        historyState.exhausted ? translate("history.noMore") : "",
        { hidden: !historyState.exhausted, busy: false },
      );
      window.requestAnimationFrame(maybeLoadMoreFromScroll);
      return result;
    }
    const data = await requestPage(
      `/api/task-history/tasks?${queryParams(cursor, direction)}`,
    );
    if (requestId !== historyState.requestId) return emptyResult;
    const tasks = data.tasks || [];
    validateOrganizationRows(tasks);
    renderTasks(tasks, { position: reset ? "replace" : direction === "previous" ? "prepend" : "append" });
    if (direction === "previous") {
      historyState.newerExhausted = !data.previous_cursor || !tasks.length;
    } else {
      historyState.nextCursor = data.next_cursor || null;
      historyState.exhausted = !historyState.nextCursor;
      if (reset) historyState.newerExhausted = true;
      if (reset) historyPositionSaveController.enable();
    }
    setLoadMoreState(
      historyState.exhausted ? translate("history.noMore") : "",
      { hidden: !historyState.exhausted, busy: false },
    );
    window.requestAnimationFrame(maybeLoadMoreFromScroll);
    return {
      anchorFound: null,
      taskCount: tasks.length,
    };
  } catch (error) {
    if (requestId === historyState.requestId) {
      const message = errorMessage(error, translate("history.tasksFailed"));
      if (els.taskList && historyTaskCards(els.taskList).length) {
        setText(els.resultSummary, message);
      } else {
        renderTaskListMessage("history-error", message);
      }
      if (direction === "previous") {
        historyState.newerExhausted = false;
      } else {
        historyState.exhausted = false;
      }
      setLoadMoreState(translate("history.loadFailed"));
    }
    if (throwOnError) throw error;
    return emptyResult;
  } finally {
    if (requestId === historyState.requestId) historyState.loading = false;
  }
}

async function refreshHistoryAfterImport(): Promise<void> {
  await loadSummary({ throwOnError: true });
  await loadTasks({ reset: true, throwOnError: true });
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

function captureHistoryScrollAnchorSkipping(taskIds: Set<string>): HistoryScrollAnchor {
  if (!els.taskList) return null;
  const rootTop = els.taskList.getBoundingClientRect().top;
  for (const card of historyTaskCards(els.taskList)) {
    const taskId = String(card.dataset.historyTaskCardId || "");
    if (!taskId || taskIds.has(taskId)) continue;
    const rect = card.getBoundingClientRect();
    if (rect.bottom < rootTop) continue;
    return { taskId, offset: rect.top - rootTop };
  }
  return null;
}

function refreshHistoryWindowAfterMutation(
  mutate: () => void,
  options: { removedTaskIds?: string[] } = {},
): void {
  if (!els.taskList) {
    mutate();
    return;
  }
  const removedTaskIds = new Set(options.removedTaskIds || []);
  const currentAnchor = captureHistoryScrollAnchor(els.taskList);
  const anchor = currentAnchor && !removedTaskIds.has(currentAnchor.taskId)
    ? currentAnchor
    : captureHistoryScrollAnchorSkipping(removedTaskIds);
  mutate();
  if (!els.taskList.querySelector(".history-task-card")) {
    renderTaskListMessage("history-empty", translate("history.noMatches"));
  }
  layoutJustifiedHistoryGrid();
  restoreHistoryScrollAnchor(els.taskList, anchor);
  updateTaskSelectionVisuals();
  window.requestAnimationFrame(maybeLoadMoreFromScroll);
}

function removeHistoryTaskIdsFromWindow(taskIds: string[]): void {
  const ids = taskIds.filter(Boolean);
  if (!ids.length) return;
  refreshHistoryWindowAfterMutation(() => {
    ids.forEach((taskId) => {
      historyState.loadedTaskIds.delete(taskId);
      historyState.loadedTaskSummaries.delete(taskId);
      historyState.selectedTaskIds.delete(taskId);
      if (historyState.selectionAnchorTaskId === taskId) historyState.selectionAnchorTaskId = "";
      historyTaskCardElement(taskId)?.remove();
    });
  }, { removedTaskIds: ids });
  reconcileHistoryTaskSelection();
}

function removeHistoryTaskCardPreservingAnchor(
  taskId: string,
): void {
  removeHistoryTaskIdsFromWindow([taskId]);
}

function applyHistoryOrganizations(
  organizations: Record<string, HistoryOrganization>,
): void {
  const entries = Object.entries(organizations);
  if (!entries.length) return;
  const removedTaskIds = entries
    .filter(([taskId, organization]) => {
      const task = historyState.loadedTaskSummaries.get(taskId);
      return Boolean(
        task &&
          !taskMatchesHistoryOrganizationFilters(
            organization,
            historyOrganizationFilters,
          ),
      );
    })
    .map(([taskId]) => taskId);
  const removedSet = new Set(removedTaskIds);
  refreshHistoryWindowAfterMutation(() => {
    for (const [taskId, organization] of entries) {
      const task = historyState.loadedTaskSummaries.get(taskId);
      if (!task) continue;
      Object.assign(task, organization);
      if (removedSet.has(taskId)) {
        historyState.loadedTaskIds.delete(taskId);
        historyState.loadedTaskSummaries.delete(taskId);
        historyState.selectedTaskIds.delete(taskId);
        historyTaskCardElement(taskId)?.remove();
        continue;
      }
      const card = historyTaskCardElement(taskId);
      if (!card) continue;
      const template = document.createElement("template");
      template.innerHTML = taskCardHtml(task).trim();
      const nextCard = template.content.firstElementChild;
      if (nextCard) card.replaceWith(nextCard);
    }
  }, { removedTaskIds });
  const detailTaskId = String(
    historyState.detailTask?.task_id || "",
  );
  const detailOrganization = organizations[detailTaskId];
  if (detailOrganization) {
    Object.assign(historyState.detailTask, detailOrganization);
    if (removedSet.has(detailTaskId)) {
      historyState.detailTask = null;
    } else {
      renderTaskDetail(historyState.detailTask);
    }
  }
  if (removedSet.size) {
    reconcileHistoryTaskSelection();
  } else {
    renderBulkToolbar();
  }
}

async function organizeHistoryTaskIds(
  taskIds: string[],
  change: HistoryOrganizationChange,
): Promise<void> {
  const ids = [...new Set(taskIds.filter(Boolean))];
  if (!ids.length) return;
  try {
    const organizations = await organizeHistoryTasks({
      task_ids: ids,
      ...change,
    });
    applyHistoryOrganizations(organizations);
    await loadSummary();
  } catch (error) {
    setText(
      els.resultSummary,
      errorMessage(
        error,
        translate("history.organizationFailed"),
      ),
    );
  }
}

function historyTaskMatchesCurrentArchiveFilter(task: any): boolean {
  if (historyState.archived === "true") return historyTaskArchived(task);
  if (historyState.archived === "false") return !historyTaskArchived(task);
  return true;
}

function historyTaskSummaryFromDetail(taskId: string, task: any): HistoryTask | null {
  const previous = historyState.loadedTaskSummaries.get(taskId);
  const source = task || previous;
  if (!source) return null;
  const generatedCount = historyTaskGeneratedCount(source);
  const totalCount = positiveInt(source.total_count) ?? previous?.total_count ?? generatedCount;
  return {
    ...(previous || {}),
    ...(source || {}),
    task_id: taskId || String(source.task_id || previous?.task_id || ""),
    created_at: String(source.created_at || previous?.created_at || ""),
    updated_at: String(source.updated_at || previous?.updated_at || ""),
    completed_at: String(source.completed_at || previous?.completed_at || ""),
    status: String(source.status || previous?.status || ""),
    mode: String(source.mode || previous?.mode || ""),
    size: String(source.size || source.output_size || source.params?.size || previous?.size || ""),
    quality: String(source.quality || source.params?.quality || previous?.quality || ""),
    prompt_mode: String(source.prompt_mode || source.params?.prompt_fidelity || previous?.prompt_mode || ""),
    ratio: String(source.ratio || source.params?.ratio || previous?.ratio || ""),
    orientation: String(source.orientation || source.params?.orientation || previous?.orientation || ""),
    backend: String(source.backend || previous?.backend || ""),
    provider: String(source.provider || source.api_provider_name || previous?.provider || ""),
    archived: historyTaskArchived(source),
    generated_count: generatedCount || previous?.generated_count || 0,
    failed_count: positiveInt(source.failed_count) ?? previous?.failed_count ?? 0,
    total_count: totalCount || 0,
    thumbnail_url: String(source.thumbnail_url || previous?.thumbnail_url || ""),
    prompt_preview: String(source.prompt_preview || source.prompt || previous?.prompt_preview || ""),
    favorite: Boolean(source.favorite ?? previous?.favorite),
    tags: Array.isArray(source.tags)
      ? source.tags
      : previous?.tags || [],
  };
}

function upsertHistoryTaskSummaryCard(taskId: string, task: any): void {
  const summary = historyTaskSummaryFromDetail(taskId, task);
  if (!summary?.task_id) return;
  if (!historyTaskMatchesCurrentArchiveFilter(summary)) {
    removeHistoryTaskIdsFromWindow([summary.task_id]);
    return;
  }
  refreshHistoryWindowAfterMutation(() => {
    const card = historyTaskCardElement(summary.task_id);
    if (!card) return;
    historyState.loadedTaskIds.add(summary.task_id);
    historyState.loadedTaskSummaries.set(summary.task_id, summary);
    const template = document.createElement("template");
    template.innerHTML = taskCardHtml(summary).trim();
    const nextCard = template.content.firstElementChild;
    if (nextCard) card.replaceWith(nextCard);
  });
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

function historyTaskAccessibleLabel(task: HistoryTask): string {
  const title = String(task.prompt_preview || task.mode || task.task_id)
    .replace(/\s+/g, " ")
    .trim();
  const conciseTitle = title.length > 96 ? `${title.slice(0, 96)}…` : title;
  return [
    conciseTitle,
    formatDate(task.created_at),
    localizedTaskStatus(task.status || ""),
  ].filter(Boolean).join(" · ");
}

function taskCardHtml(task: HistoryTask): string {
  const taskId = escapeHtml(task.task_id);
  const thumbnailUrl = historyThumbnailUrl(task);
  const ratioStyle = historyThumbnailRatioStyle(task);
  const imageCount = historyTaskGeneratedCount(task);
  const stackDepth = historyTaskStackDepth(imageCount);
  const stackLayers = historyTaskStackLayers(stackDepth);
  const thumb = thumbnailUrl
    ? `<img class="transparency-grid" src="${escapeHtml(thumbnailUrl)}" alt="" loading="lazy" decoding="async" draggable="false">`
    : "";
  const counts = `${task.generated_count || 0}/${task.total_count || 0}`;
  const selected = historyState.selectedTaskIds.has(task.task_id)
    || historyState.selectedTaskId === task.task_id;
  const active = historyState.selectedTaskId === task.task_id;
  const accessibleLabel = historyTaskAccessibleLabel(task);
  const source = historyTaskSourceLabel(task);
  const promptMode = facetDisplayValue("prompt_mode", task.prompt_mode || "");
  const quality = facetDisplayValue("quality", task.quality || "");
  const favoriteButton = historyFavoriteButtonHtml(
    task.task_id,
    Boolean(task.favorite),
    escapeHtml,
    translate(
      task.favorite
        ? "history.unfavoriteTask"
        : "history.favoriteTask",
    ),
  );
  const tagChips = historyCardTagsHtml(
    Array.isArray(task.tags) ? task.tags : [],
    escapeHtml,
  );
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
      data-history-image-count="${String(imageCount)}"
      data-history-stack-depth="${String(stackDepth)}"
      role="listitem"
      aria-current="${active ? "true" : "false"}"
      ${ratioStyle}
    >
      ${favoriteButton}
      <button class="history-task-open" type="button" data-history-task-id="${taskId}" aria-label="${escapeHtml(accessibleLabel)}" aria-pressed="${selected ? "true" : "false"}">
        <span class="history-task-thumb">
          ${stackLayers}
          <span class="history-task-thumb-frame">${thumb}</span>
        </span>
        <span class="history-task-copy">
          <span class="history-task-title">${escapeHtml(task.prompt_preview || task.mode || task.task_id)}</span>
          ${tagChips}
          <span class="history-task-meta">
            ${metaItems.map((item) => `<span data-history-meta-kind="${escapeHtml(item.kind)}">${escapeHtml(item.value)}</span>`).join("")}
          </span>
        </span>
      </button>
    </article>
  `;
}

function historyTaskStackDepth(imageCount: number): number {
  if (!Number.isFinite(imageCount) || imageCount <= 1) return 0;
  return Math.min(3, imageCount - 1);
}

function historyTaskStackLayers(stackDepth: number): string {
  if (!Number.isFinite(stackDepth) || stackDepth <= 0) return "";
  return Array.from({ length: stackDepth }, (_, index) => {
    const layer = index + 1;
    return `<span class="history-task-stack-layer" data-history-stack-layer="${String(layer)}" aria-hidden="true"></span>`;
  }).join("");
}

function historyTaskSourceLabel(task: Partial<HistoryTask> & Record<string, any>): string {
  const provider = String(
    task.provider
    || task.api_provider_name
    || task.params?.api_provider_name
    || task.request?.webui_api_provider_name
    || task.request?.api_provider_name
    || "",
  ).trim();
  const backend = historyBackendDisplayLabel(task.backend);
  const channel = historyBackendChannelLabel(task.backend);
  if (provider) return [provider, channel].filter(Boolean).join(" · ");
  return backend;
}

function historyBackendDisplayLabel(backend: unknown): string {
  const value = String(backend || "").trim();
  if (value === "codex_images") return "Codex Image";
  if (value === "codex_responses") return "Codex Responses";
  if (value === "openai_images") return "API Image";
  if (value === "openai_responses") return "API Responses";
  return value;
}

function historyBackendChannelLabel(backend: unknown): string {
  const value = String(backend || "").trim();
  if (value === "openai_images") return "Image";
  if (value === "openai_responses") return "Responses";
  return "";
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
    const active = Boolean(historyState.selectedTaskIds.size === 1 && taskId && cardTaskId === taskId);
    const selected = historyState.selectedTaskIds.has(cardTaskId);
    card.classList.toggle("active", active);
    card.classList.toggle("selected", selected);
    card.setAttribute("aria-current", active ? "true" : "false");
    card.querySelector<HTMLElement>("[data-history-task-id]")
      ?.setAttribute("aria-pressed", selected ? "true" : "false");
  });
}

function visibleHistoryTaskIds(): string[] {
  return Array.from(els.taskList?.querySelectorAll<HTMLElement>(".history-task-card[data-history-task-card-id]") || [])
    .map((card) => String(card.dataset.historyTaskCardId || ""))
    .filter(Boolean);
}

function focusHistoryTaskButton(taskId: string): void {
  const card = historyTaskCardElement(taskId);
  const button = card?.querySelector<HTMLElement>("[data-history-task-id]");
  button?.focus({ preventScroll: true });
  ensureHistoryTaskCardVisible(taskId);
}

function handleHistoryTaskArrowNavigation(event: KeyboardEvent): boolean {
  if (isHistoryLightboxOpen()) return false;
  if (!isHistoryTaskArrowKey(event.key)) return false;
  if (event.altKey || event.metaKey || event.ctrlKey) return false;
  const target = event.target as HTMLElement | null;
  const taskButton = target?.closest<HTMLElement>("[data-history-task-id]");
  if (!taskButton || !els.taskList?.contains(taskButton)) return false;
  const taskId = taskButton.dataset.historyTaskId || "";
  const nextCard = historyTaskArrowTargetCard(els.taskList, taskId, event.key, historyState.view);
  if (!nextCard && historyState.view === "list" && (event.key === "ArrowLeft" || event.key === "ArrowRight")) return false;
  event.preventDefault();
  event.stopPropagation();
  const nextTaskId = nextCard?.dataset.historyTaskCardId || "";
  if (!nextTaskId) return true;
  focusHistoryTaskButton(nextTaskId);
  applyHistoryTaskSelection([nextTaskId], nextTaskId, nextTaskId);
  return true;
}

function applyHistoryTaskSelection(
  taskIds: string[],
  anchorTaskId = "",
  primaryTaskId = anchorTaskId,
): void {
  historyState.selectedTaskIds = new Set(taskIds.filter(Boolean));
  const selectedIds = [...historyState.selectedTaskIds];
  historyState.selectionAnchorTaskId = historyState.selectedTaskIds.has(anchorTaskId)
    ? anchorTaskId
    : selectedIds[0] || "";
  historyState.selectedTaskId = historyState.selectedTaskIds.has(primaryTaskId)
    ? primaryTaskId
    : selectedIds[0] || "";
  if (!historyState.selectedTaskId) {
    historyState.detailTask = null;
    historyState.selectionMode = false;
  }
  clearHistoryDeleteConfirmation();
  updateHistoryUrl();
  updateTaskSelectionVisuals();
  renderBulkToolbar();
  syncHistorySelectionDetail();
}

function reconcileHistoryTaskSelection(): void {
  applyHistoryTaskSelection(
    [...historyState.selectedTaskIds],
    historyState.selectionAnchorTaskId,
    historyState.selectedTaskId,
  );
  if (!historyState.selectedTaskId) {
    els.page?.classList.remove("history-detail-open");
  }
}

function clearHistoryTaskSelection({ updateVisuals = true } = {}): void {
  resetHistoryTaskSelectionState();
  clearHistoryDeleteConfirmation();
  updateHistoryUrl();
  if (updateVisuals) updateTaskSelectionVisuals();
  renderBulkToolbar();
  syncHistorySelectionDetail();
}

function resetHistoryTaskSelectionState(): void {
  historyState.selectedTaskIds.clear();
  historyState.selectedTaskId = "";
  historyState.selectionAnchorTaskId = "";
  historyState.selectionMode = false;
  historyState.detailTask = null;
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
  historyState.selectedTaskId = next.has(taskId)
    ? taskId
    : [...next][0] || "";
  if (!historyState.selectedTaskId) historyState.detailTask = null;
  clearHistoryDeleteConfirmation();
  updateHistoryUrl();
  updateTaskSelectionVisuals();
  renderBulkToolbar();
  syncHistorySelectionDetail();
}

function selectHistoryTaskRange(anchorTaskId: string, taskId: string): void {
  if (!taskId) return;
  const visibleIds = visibleHistoryTaskIds();
  const fallbackAnchor = historyState.selectionAnchorTaskId || historyState.selectedTaskId || taskId;
  const anchor = anchorTaskId || fallbackAnchor;
  const anchorIndex = visibleIds.indexOf(anchor);
  const targetIndex = visibleIds.indexOf(taskId);
  if (anchorIndex < 0 || targetIndex < 0) {
    applyHistoryTaskSelection([...historyState.selectedTaskIds, taskId], taskId, taskId);
    return;
  }
  const [start, end] = anchorIndex <= targetIndex ? [anchorIndex, targetIndex] : [targetIndex, anchorIndex];
  applyHistoryTaskSelection([...historyState.selectedTaskIds, ...visibleIds.slice(start, end + 1)], anchor, taskId);
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

function historySelectAllShortcutBlocked(): boolean {
  return Boolean(
    (els.backupDialog && !els.backupDialog.hidden)
    || (els.importDialog && !els.importDialog.hidden)
    || historyExportPickerEl
    || historyOrganizePickerEl
    || historyTagPickerEl
    || (historyContextMenuEl && !historyContextMenuEl.classList.contains("hidden"))
    || isHistoryLightboxOpen()
  );
}

function handleHistorySelectAllShortcut(event: KeyboardEvent): boolean {
  if (
    historySelectAllShortcutBlocked()
    || !isHistorySelectAllTasksShortcut(event, event.target as HTMLElement | null)
  ) return false;
  const taskIds = historySelectAllTaskIds(visibleHistoryTaskIds());
  if (!taskIds.length) return false;
  event.preventDefault();
  event.stopPropagation();
  window.getSelection()?.removeAllRanges();
  applyHistoryTaskSelection(taskIds, taskIds[0], taskIds[0]);
  return true;
}

async function loadTaskDetail(taskId: string): Promise<void> {
  if (!taskId) return;
  if (historyState.selectedTaskIds.size !== 1 || !historyState.selectedTaskIds.has(taskId)) {
    historyState.selectedTaskIds = new Set([taskId]);
    historyState.selectionAnchorTaskId = taskId;
    historyState.selectionMode = false;
    renderBulkToolbar();
  }
  const loadToken = ++historyDetailLoadToken;
  const keepCurrentDetail = els.detail?.dataset.historyDetailMode === "task" && Boolean(historyState.detailTask?.task_id);
  historyState.selectedTaskId = taskId;
  clearHistoryDeleteConfirmation();
  historyState.deleteConfirmTaskId = "";
  historyState.deleteUnselectedConfirmTaskId = "";
  updateHistoryUrl();
  updateTaskSelectionVisuals(taskId);
  els.page?.classList.add("history-detail-open");
  if (keepCurrentDetail) {
    els.detail?.classList.add("history-detail-pending");
    els.detail?.setAttribute("aria-busy", "true");
  } else {
    renderDetailShell(translate("history.loadingDetail"));
  }
  try {
    const detail = await fetchHistoryTaskDetail(taskId);
    if (!isCurrentHistoryDetailLoad(loadToken, taskId)) return;
    if (keepCurrentDetail) {
      await preloadHistoryDetailImages(detail);
    }
    if (!isCurrentHistoryDetailLoad(loadToken, taskId)) return;
    renderTaskDetail(detail);
  } catch (error) {
    if (!isCurrentHistoryDetailLoad(loadToken, taskId)) return;
    renderDetailShell(errorMessage(error, translate("history.detailFailed")), "history-error");
  } finally {
    if (isCurrentHistoryDetailLoad(loadToken, taskId)) {
      els.detail?.classList.remove("history-detail-pending");
      els.detail?.removeAttribute("aria-busy");
    }
  }
}

async function fetchHistoryTaskDetail(taskId: string): Promise<any> {
  const response = await fetch(`/api/tasks/${encodeURIComponent(taskId)}`);
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.detail || translate("history.detailFailed"));
  return {
    ...(data.task || {}),
    ...(data.organization || {}),
  };
}

function isCurrentHistoryDetailLoad(loadToken: number, taskId: string): boolean {
  return loadToken === historyDetailLoadToken
    && historyState.selectedTaskId === taskId
    && historyState.selectedTaskIds.size === 1
    && historyState.selectedTaskIds.has(taskId);
}

async function preloadHistoryDetailImages(task: any): Promise<void> {
  const urls = taskOutputRecords(task)
    .map((record) => record.url)
    .filter((url): url is string => Boolean(url));
  if (!urls.length) return;
  await Promise.all(urls.map((url) => preloadHistoryDetailImage(url)));
}

async function preloadHistoryDetailImage(url: string): Promise<boolean> {
  const image = document.createElement("img");
  const loadedPromise = waitForHistoryDetailImageLoad(image);
  image.decoding = "async";
  image.src = url;
  const loaded = image.complete && image.naturalWidth > 0 ? true : await loadedPromise;
  if (!loaded) return false;
  try {
    await image.decode?.();
  } catch {
    // Some browsers reject decode() for already usable cached images.
  }
  return true;
}

function waitForHistoryDetailImageLoad(image: HTMLImageElement): Promise<boolean> {
  return new Promise((resolve) => {
    image.onload = () => resolve(true);
    image.onerror = () => resolve(false);
  });
}

function renderDetailShell(message: string, className = "history-detail-empty"): void {
  if (!els.detail) return;
  els.detail.dataset.historyDetailMode = "empty";
  historyState.detailTask = null;
  els.detail.innerHTML = `
    <div class="history-detail-header">
      <div>
        <h2 class="history-detail-title history-detail-empty-title">${escapeHtml(translate("history.detail"))}</h2>
      </div>
      <button id="historyDetailClose" class="ghost-button drawer-close-button history-detail-close" type="button" data-history-detail-close aria-label="${escapeHtml(translate("history.closeDetail"))}">
        <svg class="drawer-close-icon" viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="M7 7L17 17M17 7L7 17" /></svg>
      </button>
    </div>
    <div class="${className}">${escapeHtml(message)}</div>
  `;
}

function historyActionPanelCopy(): HistoryActionPanelCopy {
  return {
    libraryTitle: translate("history.title"),
    libraryDescription: translate("historyBackup.description"),
    backup: translate("historyBackup.open"),
    importBackup: translate("historyBackup.importOpen"),
    selectTasks: translate("history.selectTask"),
    selectedCount: (count) => formatTranslation("history.selectedCount", { count }),
    exitSelection: translate("history.exitSelection"),
    organize: translate("history.organizeSelected"),
    favorite: translate("history.favoriteSelected"),
    unfavorite: translate("history.unfavoriteSelected"),
    addTag: translate("history.addTag"),
    removeTag: translate("history.removeTag"),
    archive: translate("action.archive"),
    restore: translate("archive.restore"),
    export: translate("history.export"),
    imagesOnly: translate("history.exportImagesOnly"),
    imagesWithPrompts: translate("history.exportImagesWithPrompts"),
    confirmDelete: translate("history.confirmDelete"),
    deleteTasks: translate("action.delete"),
    cancel: translate("action.cancel"),
    close: translate("action.close"),
  };
}

function renderHistoryManagementDetail(): void {
  if (!els.detail) return;
  els.detail.dataset.historyDetailMode = "management";
  historyState.detailTask = null;
  els.detail.innerHTML = historyManagementPanelHtml(historyActionPanelCopy(), {
    selectionMode: historyState.selectionMode,
  });
}

function renderSelectionDetail(): void {
  if (!els.detail) return;
  const count = historyState.selectedTaskIds.size;
  if (!count) return;
  els.detail.dataset.historyDetailMode = "selection";
  els.detail.innerHTML = historySelectionPanelHtml({
    copy: historyActionPanelCopy(),
    count,
    expandedSection: historyActionPanelExpanded,
    deleteConfirming: historyState.deleteConfirming,
  });
}

function syncHistorySelectionDetail(): void {
  if (!els.detail) return;
  const resolution = historySelectionDetailResolution({
    selectedCount: historyState.selectedTaskIds.size,
    selectedTaskId: historyState.selectedTaskId,
    detailTaskId: String(historyState.detailTask?.task_id || ""),
  });
  if (resolution === "selection") {
    renderSelectionDetail();
  } else if (resolution === "task") {
    renderTaskDetail(historyState.detailTask);
  } else if (resolution === "load-task") {
    void loadTaskDetail(historyState.selectedTaskId);
  } else {
    renderHistoryManagementDetail();
  }
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
  els.detail.dataset.historyDetailMode = "task";
  const taskId = String(task.task_id || historyState.selectedTaskId || "");
  const urls = taskOutputRecords(task);
  const selectedCount = taskSelectedOutputIndexes(task).size;
  const images = historyDetailImagesHtml(taskId, urls, selectedCount);
  const imageLayoutClass = historyDetailImagesLayoutClass(urls);
  const inputReferences = historyInputReferencesHtml(task);
  const referenceFiles = historyReferenceFilesHtml(task);
  const zipHref = `/api/tasks/${encodeURIComponent(taskId)}/outputs.zip`;
  const canZip = urls.length > 1;
  const singleDownloadHref = urls.length === 1 ? String(urls[0]?.url || "") : "";
  const hasSelectedOutputs = selectedCount > 0;
  const canDeleteUnselected = selectedCount > 0 && selectedCount < urls.length;
  const confirmingDeleteUnselected = historyState.deleteUnselectedConfirmTaskId === taskId;
  const archived = historyTaskArchived(task);
  const confirmingDeleteTask = historyState.deleteConfirmTaskId === taskId;
  const deleteBlocked = historyTaskDeleteBlocked(task);
  const title = detailTitle(task);
  const favorite = Boolean(task.favorite);
  const detailFavoriteButton = historyFavoriteButtonHtml(
    taskId,
    favorite,
    escapeHtml,
    translate(
      favorite
        ? "history.unfavoriteTask"
        : "history.favoriteTask",
    ),
  );
  const detailTags = historyDetailTagsHtml(
    Array.isArray(task.tags) ? task.tags : [],
    escapeHtml,
  );
  els.detail.innerHTML = `
    <div class="history-detail-header">
      <div>
        <p class="history-detail-kicker">${escapeHtml(historyTaskModeLabel(task.mode))}</p>
        <h2 class="history-detail-title" title="${escapeHtml(task.prompt || title)}">${escapeHtml(title)}</h2>
      </div>
      <button id="historyDetailClose" class="ghost-button drawer-close-button history-detail-close" type="button" data-history-detail-close aria-label="${escapeHtml(translate("history.closeDetail"))}">
        <svg class="drawer-close-icon" viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="M7 7L17 17M17 7L7 17" /></svg>
      </button>
    </div>
    <div class="history-detail-organization">
      ${detailFavoriteButton}
      <div class="history-detail-tags">
        ${detailTags || `<span class="history-tag-empty">${escapeHtml(translate("history.noTags"))}</span>`}
      </div>
      <button
        class="ghost-button text-sm"
        type="button"
        data-history-open-tag-picker="detail"
      >${escapeHtml(translate("history.addTag"))}</button>
    </div>
    <div class="history-detail-meta">
      <span>${escapeHtml(formatDate(task.created_at || ""))}</span>
      <span>${escapeHtml(localizedTaskStatus(task.status || ""))}</span>
      <span>${escapeHtml(task.params?.size || task.output_size || "")}</span>
      <span>${escapeHtml(facetDisplayValue("prompt_mode", task.params?.prompt_fidelity || ""))}</span>
      <span>${escapeHtml(facetDisplayValue("quality", task.params?.quality || task.quality || ""))}</span>
      <span>${escapeHtml(historyTaskSourceLabel(task))}</span>
    </div>
    <div class="history-detail-actions">
      <div class="history-detail-actions-result">
        <button class="ghost-button text-sm" type="button" data-history-reuse-task="${escapeHtml(taskId)}">${escapeHtml(translate("history.reuseTask"))}</button>
        ${selectedCount > 1
          ? `<a class="ghost-button text-sm" href="${escapeHtml(zipHref)}?selected=1" download>${escapeHtml(translate("history.downloadSelected"))}</a>`
          : canZip
          ? `<a class="ghost-button text-sm" href="${escapeHtml(zipHref)}" download>${escapeHtml(translate("history.downloadAll"))}</a>`
          : singleDownloadHref
            ? `<a class="ghost-button text-sm" href="${escapeHtml(singleDownloadHref)}" download>${escapeHtml(translate("history.downloadImage"))}</a>`
            : ""}
      </div>
      <div class="history-detail-actions-management">
        <button class="ghost-button text-sm" type="button" data-history-open-export="${escapeHtml(taskId)}">${escapeHtml(translate("history.export"))}</button>
        <button class="ghost-button text-sm" type="button" data-history-archive-task="${escapeHtml(taskId)}" data-history-archive-value="${archived ? "false" : "true"}">${escapeHtml(archived ? translate("archive.restore") : translate("action.archive"))}</button>
        ${hasSelectedOutputs
          ? `<button class="ghost-button text-sm danger-button" type="button" ${canDeleteUnselected && !deleteBlocked ? `data-history-delete-unselected="${escapeHtml(taskId)}"` : "disabled"}>${escapeHtml(confirmingDeleteUnselected ? translate("history.confirmDeleteUnselected") : translate("history.deleteUnselected"))}</button>`
          : `<button class="ghost-button text-sm danger-button" type="button" data-history-delete-task="${escapeHtml(taskId)}" ${deleteBlocked ? "disabled" : ""}>${escapeHtml(confirmingDeleteTask ? translate("history.confirmDelete") : translate("action.delete"))}</button>`}
      </div>
    </div>
    ${["failed", "partial_failed"].includes(task.status) ? `<div class="history-recovery"><p>${escapeHtml(taskRecoveryMessage(task))}</p><details><summary>${escapeHtml(translate("ux.errorDetails"))}</summary><p>${escapeHtml(String(task.error || task.last_error || ""))}</p></details><button type="button" class="ghost-button text-sm" data-history-reuse-task="${escapeHtml(taskId)}">${escapeHtml(translate("ux.openRecovery"))}</button></div>` : ""}
    <div class="history-detail-images${imageLayoutClass}">${images || `<div class="history-detail-empty">${escapeHtml(translate("history.noPreview"))}</div>`}</div>
    ${inputReferences}
    ${referenceFiles}
    ${promptCompareHtml(task)}
  `;
  const grounding = createGroundingAttribution(task);
  const imageGrid = els.detail.querySelector<HTMLElement>(".history-detail-images");
  if (grounding && imageGrid) imageGrid.insertAdjacentElement("afterend", grounding);
}

function detailTitle(task: any): string {
  return truncateText(task.prompt_preview || task.prompt || task.mode || task.task_id || translate("history.untitled"), 120);
}

function historyTaskArchived(task: any): boolean {
  return Boolean(task?.archived || task?.archived_at);
}

function historyTaskDeleteBlocked(task: any): boolean {
  const status = String(task?.status || "");
  return Boolean(task?.local_pending || status === "running" || status === "cancelling" || status === "submitting" || status === "queued");
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

function promptCompareHtml(task: any): string {
  const originalPrompt = promptTextValue(task.prompt || "");
  const submittedPrompt = promptTextValue(submittedPromptForTask(task));
  const revisedPrompt = revisedPromptText(task);
  const hasDistinctOutputPrompts = hasDistinctOutputRevisedPrompts(task);
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
  const hasRevisedPanel = hasDistinctOutputPrompts ? false : addPanel("revised", translate("history.promptRevised"), revisedPrompt);
  if (task.generation_snapshot?.transparency_instruction) {
    addPanel("submitted", translate("history.promptSubmittedActual"), submittedPrompt);
  } else if (!hasRevisedPanel) {
    addPanel("submitted", translate("history.promptSubmitted"), submittedPrompt);
  }
  if (hasDistinctOutputPrompts) {
    panels.push(`<p class="history-prompt-note">${escapeHtml(translate("history.outputRevisedPromptNotice"))}</p>`);
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

function outputRevisedPromptTexts(task: any): string[] {
  return uniquePromptTexts(taskOutputRecords(task).map((record) => record.revisedPrompt));
}

function hasDistinctOutputRevisedPrompts(task: any): boolean {
  return outputRevisedPromptTexts(task).length > 1;
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
  resetHistoryTaskSelectionState();
  clearHistoryDeleteConfirmation();
  const attr = historyFilterAttribute(key);
  document.querySelectorAll(`[data-history-${attr}]`).forEach((node) => {
    node.classList.toggle("active", (node as HTMLElement).getAttribute(`data-history-${attr}`) === value);
  });
  renderHistoryActiveFilters();
  updateHistoryUrl();
  void loadTasks({ reset: true });
}

function renderBulkToolbar(): void {
  const count = historyState.selectedTaskIds.size;
  els.page?.classList.toggle("history-bulk-selecting", count > 1 || historyState.selectionMode);
  els.page?.classList.toggle("history-selection-mode", historyState.selectionMode);
  els.selectionDock?.classList.toggle("hidden", count === 0);
  els.selectionDock?.toggleAttribute("hidden", count === 0);
  setText(
    els.selectionDockCount,
    count ? formatTranslation("history.selectedCount", { count }) : "",
  );
  if (!count) {
    historyActionPanelExpanded = "";
    closeHistoryOrganizePicker({ restoreFocus: false });
  }
  if (count && els.detail?.dataset.historyDetailMode === "selection") renderSelectionDetail();
}

function clearHistoryDeleteConfirmation(): void {
  historyState.deleteConfirming = false;
  historyState.pendingDeleteTaskIds = [];
  historyState.contextMenuDeleteConfirmKey = "";
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
    const tasks = await Promise.all(ids.map((taskId) => setTaskArchiveState(taskId, archived)));
    ids.forEach((taskId) => historyState.selectedTaskIds.delete(taskId));
    clearHistoryDeleteConfirmation();
    tasks.forEach((task, index) => {
      const taskId = ids[index] || String(task?.task_id || "");
      upsertHistoryTaskSummaryCard(taskId, task);
      if (taskId && String(historyState.detailTask?.task_id || "") === taskId && task) {
        historyState.detailTask = task;
        renderTaskDetail(task);
      }
    });
    reconcileHistoryTaskSelection();
    await loadSummary();
    setText(els.resultSummary, archived ? formatTranslation("batch.archivedCount", { count: ids.length }) : formatTranslation("archive.restoredCount", { count: ids.length }));
  } catch (error) {
    setText(els.resultSummary, errorMessage(error, archived ? translate("taskActions.archiveFailed") : translate("archive.restoreFailed")));
  } finally {
    renderBulkToolbar();
    syncHistorySelectionDetail();
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
    upsertHistoryTaskSummaryCard(taskId, task);
    await loadSummary();
    setText(els.resultSummary, archived ? translate("taskActions.archived") : translate("archive.restored"));
  } catch (error) {
    setText(els.resultSummary, errorMessage(error, archived ? translate("taskActions.archiveFailed") : translate("archive.restoreFailed")));
  }
}

async function deleteSelectedTasks(): Promise<void> {
  const selectedIds = [...historyState.selectedTaskIds].filter(Boolean);
  const ids = historyState.deleteConfirming && historyState.pendingDeleteTaskIds.length
    ? historyState.pendingDeleteTaskIds.slice()
    : selectedIds;
  if (!ids.length) {
    clearHistoryDeleteConfirmation();
    renderBulkToolbar();
    return;
  }
  if (!historyState.deleteConfirming) {
    historyState.pendingDeleteTaskIds = ids;
    historyState.deleteConfirming = true;
    renderBulkToolbar();
    return;
  }
  setText(els.resultSummary, translate("archive.deleting"));
  try {
    const results = await Promise.allSettled(ids.map(async (taskId) => {
      const response = await fetch(`/api/tasks/${encodeURIComponent(taskId)}`, { method: "DELETE" });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(data.detail || translate("taskActions.deleteFailed"));
      return taskId;
    }));
    const deletedIds = results
      .filter((result): result is PromiseFulfilledResult<string> => result.status === "fulfilled")
      .map((result) => result.value);
    const failedIds = ids.filter((taskId) => !deletedIds.includes(taskId));
    historyState.selectedTaskIds = new Set(failedIds);
    historyState.selectedTaskId = failedIds[0] || "";
    historyState.selectionAnchorTaskId = failedIds[0] || "";
    if (!failedIds.length) historyState.selectionMode = false;
    clearHistoryDeleteConfirmation();
    if (deletedIds.length) removeHistoryTaskIdsFromWindow(deletedIds);
    await loadSummary();
    if (deletedIds.length) {
      const skipped = failedIds.length ? ` · ${translate("taskActions.deleteFailed")} ${failedIds.length}` : "";
      setText(els.resultSummary, formatTranslation("batch.deletedCount", { count: deletedIds.length, skipped }));
    } else {
      setText(els.resultSummary, translate("taskActions.deleteFailed"));
    }
  } catch (error) {
    setText(els.resultSummary, errorMessage(error, translate("taskActions.deleteFailed")));
  } finally {
    updateTaskSelectionVisuals();
    renderBulkToolbar();
    syncHistorySelectionDetail();
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
    removeHistoryTaskIdsFromWindow([taskId]);
    await loadSummary();
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
    historyState.deleteConfirmTaskId = "";
    historyState.deleteUnselectedConfirmTaskId = "";
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
    upsertHistoryTaskSummaryCard(taskId, data.task || {});
  } catch (error) {
    setText(els.resultSummary, errorMessage(error, translate("taskActions.deleteFailed")));
  }
}

function promptTextForKind(kind: string): string {
  const task = historyState.detailTask || {};
  if (kind === "submitted") return submittedPromptForTask(task).trim();
  if (kind === "revised") {
    return revisedPromptText(task);
  }
  return String(task.prompt || task.prompt_preview || "").trim();
}

function outputPromptTextForIndex(outputIndex: unknown): string {
  const index = positiveInt(outputIndex);
  if (index === null) return "";
  const record = taskOutputRecords(historyState.detailTask || {}).find((output) => output.index === index);
  return String(record?.revisedPrompt || "").trim();
}

async function writeClipboardText(text: string): Promise<boolean> {
  return copyTextToClipboard(text);
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
    if (!await writeClipboardText(text)) return;
    if (button) setPromptCopyButtonFeedback(button, translate("history.promptCopiedShort"));
    setText(els.resultSummary, translate("history.promptCopied"));
  } catch (error) {
    if (button) setPromptCopyButtonFeedback(button, translate("history.promptCopyFailedShort"));
    setText(els.resultSummary, errorMessage(error, translate("history.promptCopyFailed")));
  }
}

async function copyOutputPromptToClipboard(outputIndex: unknown, button?: HTMLElement): Promise<void> {
  const text = outputPromptTextForIndex(outputIndex);
  if (!text) {
    if (button) {
      setPromptCopyButtonFeedback(button, translate("history.noPromptShort"));
    } else {
      setText(els.resultSummary, translate("history.noPrompt"));
    }
    return;
  }
  try {
    if (!await writeClipboardText(text)) return;
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
    if (!await writeClipboardText(ids.join("\n"))) return;
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
    if (!await writeClipboardText(prompts.join("\n\n---\n\n"))) return;
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
    applyHistoryTaskSelection([clickedTaskId], clickedTaskId, clickedTaskId);
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
      if (shouldDeleteCurrentHistorySelection(taskId)) {
        await deleteHistoryContextSelectedTasks([...historyState.selectedTaskIds]);
        return;
      }
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
    historyState.pendingDeleteTaskIds = taskIds.filter(Boolean);
    renderBulkToolbar();
    rerenderHistoryContextMenu();
    return;
  }
  historyState.selectedTaskIds = new Set(taskIds);
  historyState.pendingDeleteTaskIds = taskIds.filter(Boolean);
  await deleteSelectedTasks();
  if (!historyState.deleteConfirming) closeHistoryContextMenu();
}

function historySelectedDeleteConfirmKey(taskIds: string[]): string {
  return `selected:${taskIds.slice().sort().join("|")}`;
}

function shouldDeleteCurrentHistorySelection(taskId: string): boolean {
  return Boolean(taskId && historyState.selectedTaskIds.size > 1 && historyState.selectedTaskIds.has(taskId));
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

function handoffReferenceFileToMain(assetId: string): void {
  if (!/^[0-9a-f]{64}$/.test(assetId)) return;
  const task = historyState.detailTask || {};
  const file = Array.isArray(task.reference_files)
    ? task.reference_files.find((item: any) => String(item?.id || item?.reference_file_id || "") === assetId)
    : null;
  if (!file || file.missing) return;
  const requestedBackend = String(task.requested_backend || task.backend || "");
  const apiProviderId = String(task.api_provider_id || task.provider_id || task.params?.api_provider_id || "");
  const handoff = {
    reference_file_id: assetId,
    filename: String(file.filename || ""),
    mime_type: String(file.mime_type || ""),
    size_bytes: Number(file.size_bytes || 0),
    family: String(file.family || "text"),
    requested_backend: requestedBackend,
    api_provider_id: apiProviderId,
    source: "history",
    added_at: new Date().toISOString(),
  };
  localStorage.setItem(HISTORY_REFERENCE_HANDOFF_KEY, JSON.stringify([handoff]));
  window.location.href = "/";
}

function openHistoryDetailLightbox(index: number): void {
  const urls = historyLightboxUrlsFromTask(historyState.detailTask || {});
  openHistoryLightbox(urls, index, {
    taskId: historyState.selectedTaskId,
    onTaskNavigate: openHistoryTaskLightboxByDirection,
  });
}

function openHistoryInputLightbox(index: number): void {
  const urls = historyInputLightboxUrlsFromTask(historyState.detailTask || {});
  openHistoryLightbox(urls, index);
}

function historyAdjacentTaskId(taskId: string, direction: HistoryLightboxTaskDirection): string {
  if (!taskId) return "";
  const taskIds = visibleHistoryTaskIds();
  const index = taskIds.indexOf(taskId);
  if (index < 0) return "";
  const nextIndex = direction === "previous" ? index - 1 : index + 1;
  return taskIds[nextIndex] || "";
}

function shouldLoadHistoryAdjacentTask(taskId: string, direction: HistoryLightboxTaskDirection): boolean {
  if (!taskId) return false;
  const taskIds = visibleHistoryTaskIds();
  const index = taskIds.indexOf(taskId);
  if (index < 0) return false;
  if (direction === "previous") return index === 0 && !historyState.newerExhausted;
  return index === taskIds.length - 1 && !historyState.exhausted;
}

function syncHistoryLightboxDetail(taskId: string, detail: any): void {
  historyState.selectedTaskIds = new Set([taskId]);
  historyState.selectedTaskId = taskId;
  historyState.selectionAnchorTaskId = taskId;
  historyState.selectionMode = false;
  clearHistoryDeleteConfirmation();
  historyState.deleteConfirmTaskId = "";
  historyState.deleteUnselectedConfirmTaskId = "";
  historyState.detailTask = detail;
  els.page?.classList.add("history-detail-open");
  updateHistoryUrl();
  updateTaskSelectionVisuals(taskId);
  renderBulkToolbar();
  ensureHistoryTaskCardVisible(taskId);
  renderTaskDetail(detail);
}

async function historyTaskLightboxDetail(taskId: string): Promise<{ detail: any; urls: string[] }> {
  const detail = historyState.detailTask?.task_id === taskId ? historyState.detailTask : await fetchHistoryTaskDetail(taskId);
  const urls = historyLightboxUrlsFromTask(detail);
  return { detail, urls };
}

async function openHistoryTaskLightboxByDirection(
  direction: HistoryLightboxTaskDirection,
  context: HistoryLightboxTaskNavigationContext,
): Promise<void> {
  const currentTaskId = context.taskId || historyState.selectedTaskId;
  let cursorTaskId = currentTaskId;
  const visitedTaskIds = new Set<string>([currentTaskId]);
  for (;;) {
    let nextTaskId = historyAdjacentTaskId(cursorTaskId, direction);
    if (!nextTaskId && shouldLoadHistoryAdjacentTask(cursorTaskId, direction)) {
      await loadTasks({ direction });
      nextTaskId = historyAdjacentTaskId(cursorTaskId, direction);
    }
    if (!nextTaskId) {
      setText(els.resultSummary, translate("history.noMore"));
      return;
    }
    if (visitedTaskIds.has(nextTaskId)) {
      setText(els.resultSummary, translate("history.noMore"));
      return;
    }
    visitedTaskIds.add(nextTaskId);
    try {
      const { detail, urls } = await historyTaskLightboxDetail(nextTaskId);
      if (!urls.length) {
        cursorTaskId = nextTaskId;
        continue;
      }
      syncHistoryLightboxDetail(nextTaskId, detail);
      openHistoryLightbox(urls, context.imageIndex, {
        taskId: nextTaskId,
        onTaskNavigate: openHistoryTaskLightboxByDirection,
      });
      return;
    } catch (error) {
      setText(els.resultSummary, errorMessage(error, translate("history.detailFailed")));
      return;
    }
  }
}

async function openHistoryTaskLightbox(taskId: string, index = 0): Promise<void> {
  if (!taskId) return;
  try {
    const { detail, urls } = await historyTaskLightboxDetail(taskId);
    if (!urls.length) throw new Error(translate("history.noPreview"));
    syncHistoryLightboxDetail(taskId, detail);
    openHistoryLightbox(urls, index, {
      taskId,
      onTaskNavigate: openHistoryTaskLightboxByDirection,
    });
  } catch (error) {
    setText(els.resultSummary, errorMessage(error, translate("history.detailFailed")));
  }
}

function closeDetail(): void {
  const narrow = window.matchMedia("(max-width: 1100px)").matches;
  const mode = (els.detail?.dataset.historyDetailMode || "management") as HistoryDetailMode;
  if (historyDetailCloseEffect({ narrow, mode }) === "dismiss") {
    els.page?.classList.remove("history-detail-open");
    historyDetailReturnFocus?.focus();
    historyDetailReturnFocus = null;
    return;
  }
  historyDetailLoadToken += 1;
  historyState.selectedTaskIds.clear();
  historyState.selectedTaskId = "";
  historyState.selectionAnchorTaskId = "";
  historyState.selectionMode = false;
  historyState.detailTask = null;
  els.page?.classList.remove("history-detail-open");
  updateHistoryUrl();
  updateTaskSelectionVisuals("");
  renderBulkToolbar();
  renderHistoryManagementDetail();
  historyDetailReturnFocus?.focus();
  historyDetailReturnFocus = null;
}

function openHistoryManagementPanel(trigger: HTMLElement | null): void {
  historyDetailReturnFocus = trigger;
  renderHistoryManagementDetail();
  els.page?.classList.add("history-detail-open");
  requestAnimationFrame(() => els.detail?.querySelector<HTMLElement>(".history-detail-title")?.focus());
}

function openHistorySelectionPanel(trigger: HTMLElement | null): void {
  if (!historyState.selectedTaskIds.size) return;
  historyDetailReturnFocus = trigger;
  renderSelectionDetail();
  els.page?.classList.add("history-detail-open");
  requestAnimationFrame(() => els.detail?.querySelector<HTMLElement>(".history-detail-title")?.focus());
}

function closeHistoryTagPicker(
  { restoreFocus = true }: { restoreFocus?: boolean } = {},
): void {
  historyTagPickerEl?.remove();
  historyTagPickerEl = null;
  if (restoreFocus) historyTagPickerTrigger?.focus();
  historyTagPickerTrigger = null;
  historyTagPickerTaskIds = [];
}

function openHistoryTagPicker(
  trigger: HTMLElement,
  mode: "add" | "remove" | "detail",
  taskIds: string[],
): void {
  closeHistoryTagPicker({ restoreFocus: false });
  historyTagPickerTrigger = trigger;
  historyTagPickerMode = mode;
  historyTagPickerTaskIds = [
    ...new Set(taskIds.filter(Boolean)),
  ];
  const selectedTagIds =
    mode === "detail" &&
    String(historyState.detailTask?.task_id || "") ===
      historyTagPickerTaskIds[0]
      ? (historyState.detailTask?.tags || []).map(
          (tag: HistoryTag) => tag.tag_id,
        )
      : [];
  const picker = document.createElement("div");
  picker.className = "history-tag-picker";
  picker.setAttribute("role", "dialog");
  picker.setAttribute(
    "aria-label",
    translate(
      mode === "remove"
        ? "history.removeTag"
        : "history.addTag",
    ),
  );
  picker.innerHTML = `
    <div class="history-tag-picker-header">
      <strong>${escapeHtml(translate("history.tags"))}</strong>
      <button
        class="ghost-button drawer-close-button"
        type="button"
        data-history-close-tag-picker
        aria-label="${escapeHtml(translate("action.close"))}"
      ><svg class="drawer-close-icon" viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="M7 7L17 17M17 7L7 17" /></svg></button>
    </div>
    <div class="history-tag-picker-list">
      ${
        historyTags.length
          ? historyTagPickerHtml(
              historyTags,
              selectedTagIds,
              escapeHtml,
            )
          : `<div class="history-tag-manager-empty">${escapeHtml(translate("history.noTags"))}</div>`
      }
    </div>
    ${
      mode === "remove"
        ? ""
        : historyTagPickerCreateHtml(escapeHtml, {
            placeholder: translate("history.createTag"),
            submitLabel: translate("history.createTag"),
          })
    }
  `;
  document.body.append(picker);
  historyTagPickerEl = picker;
  picker
    .querySelector<HTMLFormElement>(
      "[data-history-tag-create-inline]",
    )
    ?.addEventListener("submit", (event) => {
      event.preventDefault();
      void createHistoryTagFromPicker();
    });
  const rect = trigger.getBoundingClientRect();
  const pickerRect = picker.getBoundingClientRect();
  const left = Math.max(
    12,
    Math.min(
      window.innerWidth - pickerRect.width - 12,
      rect.left,
    ),
  );
  const top = Math.max(
    12,
    Math.min(
      window.innerHeight - pickerRect.height - 12,
      rect.bottom + 8,
    ),
  );
  picker.style.left = `${left}px`;
  picker.style.top = `${top}px`;
  picker
    .querySelector<HTMLElement>(
      ".history-tag-picker-list input, "
        + "[data-history-tag-create-name], button",
    )
    ?.focus();
}

async function createHistoryTagFromPicker(): Promise<void> {
  const picker = historyTagPickerEl;
  if (!picker || historyTagPickerCreatePending) return;
  const input = picker.querySelector<HTMLInputElement>(
    "[data-history-tag-create-name]",
  );
  const submit = picker.querySelector<HTMLButtonElement>(
    "[data-history-tag-create-submit]",
  );
  const status = picker.querySelector<HTMLElement>(
    "[data-history-tag-create-status]",
  );
  const name = input?.value.trim() || "";
  if (!name) {
    input?.focus();
    return;
  }
  const taskIds = historyTagPickerTaskIds.slice();
  if (!taskIds.length) return;
  historyTagPickerCreatePending = true;
  if (input) input.disabled = true;
  if (submit) submit.disabled = true;
  setText(status, "");
  try {
    const result = await createHistoryTagForTasks(
      name,
      taskIds,
    );
    closeHistoryTagPicker({ restoreFocus: false });
    applyHistoryOrganizations(result.organizations);
    await loadSummary();
    setText(
      els.resultSummary,
      `${translate("history.createTag")}：${result.tag.name}`,
    );
  } catch (error) {
    const message = historyTagCreateErrorMessage(error);
    setText(status, message);
    setText(els.resultSummary, message);
    if (input) input.disabled = false;
    if (submit) submit.disabled = false;
    input?.focus();
    input?.select();
  } finally {
    historyTagPickerCreatePending = false;
    if (historyTagPickerEl === picker) {
      if (input) input.disabled = false;
      if (submit) submit.disabled = false;
    }
  }
}

async function applyHistoryTagPickerChange(
  input: HTMLInputElement,
): Promise<void> {
  const tagId = input.value;
  const ids = historyTagPickerTaskIds.slice();
  if (!tagId || !ids.length) return;
  const remove =
    historyTagPickerMode === "remove" ||
    (historyTagPickerMode === "detail" && !input.checked);
  closeHistoryTagPicker();
  await organizeHistoryTaskIds(
    ids,
    remove
      ? { remove_tag_ids: [tagId] }
      : { add_tag_ids: [tagId] },
  );
}

function closeHistoryOrganizePicker(
  { restoreFocus = true }: { restoreFocus?: boolean } = {},
): void {
  historyOrganizePickerEl?.remove();
  historyOrganizePickerEl = null;
  historyOrganizeTrigger?.setAttribute("aria-expanded", "false");
  if (restoreFocus) historyOrganizeTrigger?.focus();
  historyOrganizeTrigger = null;
}

function openHistoryOrganizePicker(trigger: HTMLElement): void {
  if (!historyState.selectedTaskIds.size) return;
  closeHistoryExportPicker({ restoreFocus: false });
  closeHistoryTagPicker({ restoreFocus: false });
  closeHistoryOrganizePicker({ restoreFocus: false });
  historyOrganizeTrigger = trigger;
  trigger.setAttribute("aria-expanded", "true");
  const picker = document.createElement("div");
  picker.className = "history-organize-picker";
  picker.setAttribute("role", "dialog");
  picker.setAttribute("aria-label", translate("history.organizeSelected"));
  picker.innerHTML = `
    <div class="history-organize-picker-header">
      <div>
        <strong>${escapeHtml(translate("history.organizeSelected"))}</strong>
        <span>${escapeHtml(formatTranslation("history.selectedCount", { count: historyState.selectedTaskIds.size }))}</span>
      </div>
      <button
        class="ghost-button drawer-close-button"
        type="button"
        data-history-close-organize
        aria-label="${escapeHtml(translate("action.close"))}"
      ><svg class="drawer-close-icon" viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="M7 7L17 17M17 7L7 17" /></svg></button>
    </div>
    <div class="history-organize-picker-actions">
      <button class="history-organize-action-button" type="button" data-history-bulk-favorite>
        <svg class="history-bulk-button-icon" viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="m12 3 2.7 5.5 6.1.9-4.4 4.3 1 6.1-5.4-2.9-5.4 2.9 1-6.1-4.4-4.3 6.1-.9Z" /></svg>
        <span>${escapeHtml(translate("history.favoriteSelected"))}</span>
      </button>
      <button class="history-organize-action-button" type="button" data-history-bulk-unfavorite>
        <svg class="history-bulk-button-icon" viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="m12 3 2.7 5.5 6.1.9-4.4 4.3 1 6.1-5.4-2.9-5.4 2.9 1-6.1-4.4-4.3 6.1-.9ZM5 5l14 14" /></svg>
        <span>${escapeHtml(translate("history.unfavoriteSelected"))}</span>
      </button>
      <button class="history-organize-action-button history-organize-group-start" type="button" data-history-open-tag-picker="add">
        <svg class="history-bulk-button-icon" viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="M4 5h9l7 7-8 8-8-8Z" /><path d="M9 9h.01M17 5v6m-3-3h6" /></svg>
        <span>${escapeHtml(translate("history.addTag"))}</span>
      </button>
      <button class="history-organize-action-button history-organize-group-start" type="button" data-history-open-tag-picker="remove">
        <svg class="history-bulk-button-icon" viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="M4 5h9l7 7-8 8-8-8Z" /><path d="M9 9h.01M15 8h6" /></svg>
        <span>${escapeHtml(translate("history.removeTag"))}</span>
      </button>
      <button class="history-organize-action-button history-organize-group-start" type="button" data-history-bulk-archive>
        <svg class="history-bulk-button-icon" viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="M4 7h16v13H4zM3 4h18v3H3zM9 12h6" /></svg>
        <span>${escapeHtml(translate("action.archive"))}</span>
      </button>
      <button class="history-organize-action-button history-organize-group-start" type="button" data-history-bulk-restore>
        <svg class="history-bulk-button-icon" viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="M4 7h16v13H4zM3 4h18v3H3zM12 17v-6m0 0-3 3m3-3 3 3" /></svg>
        <span>${escapeHtml(translate("archive.restore"))}</span>
      </button>
    </div>
  `;
  document.body.append(picker);
  historyOrganizePickerEl = picker;
  const rect = trigger.getBoundingClientRect();
  const pickerRect = picker.getBoundingClientRect();
  picker.style.left = `${Math.max(12, Math.min(window.innerWidth - pickerRect.width - 12, rect.left))}px`;
  picker.style.top = `${Math.max(12, Math.min(window.innerHeight - pickerRect.height - 12, rect.bottom + 8))}px`;
  picker.querySelector<HTMLElement>(".history-organize-action-button")?.focus();
}

function closeHistoryExportPicker(
  { restoreFocus = true }: { restoreFocus?: boolean } = {},
): void {
  historyExportPickerEl?.remove();
  historyExportPickerEl = null;
  historyExportTrigger?.setAttribute("aria-expanded", "false");
  if (restoreFocus) historyExportTrigger?.focus();
  historyExportTrigger = null;
  historyExportTaskIds = [];
}

function openHistoryExportPicker(
  trigger: HTMLElement,
  taskIds: string[],
): void {
  const frozenTaskIds = [
    ...new Set(taskIds.filter(Boolean)),
  ];
  if (!frozenTaskIds.length) return;
  closeHistoryOrganizePicker({ restoreFocus: false });
  closeHistoryTagPicker({ restoreFocus: false });
  closeHistoryExportPicker({ restoreFocus: false });
  historyExportTrigger = trigger;
  historyExportTaskIds = frozenTaskIds;
  trigger.setAttribute("aria-expanded", "true");
  const picker = document.createElement("div");
  picker.className = "history-export-picker";
  picker.setAttribute("role", "dialog");
  picker.setAttribute(
    "aria-label",
    translate("history.export"),
  );
  picker.innerHTML = `
    <div class="history-export-picker-header">
      <div>
        <strong>${escapeHtml(translate("history.export"))}</strong>
        <span>${escapeHtml(formatTranslation("history.selectedCount", { count: frozenTaskIds.length }))}</span>
      </div>
      <button
        class="ghost-button drawer-close-button"
        type="button"
        data-history-close-export
        aria-label="${escapeHtml(translate("history.closeExport"))}"
      ><svg class="drawer-close-icon" viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="M7 7L17 17M17 7L7 17" /></svg></button>
    </div>
    <div class="history-export-picker-actions">
      <button
        class="history-export-mode-button"
        type="button"
        data-history-export-mode="images_only"
      ><svg class="history-bulk-button-icon" viewBox="0 0 24 24" aria-hidden="true" focusable="false"><rect x="4" y="5" width="16" height="14" rx="2" /><path d="m6.5 16 4-4 3 3 2-2 2.5 3M15.5 9h.01" /></svg><span>${escapeHtml(translate("history.exportImagesOnly"))}</span></button>
      <button
        class="history-export-mode-button"
        type="button"
        data-history-export-mode="images_with_prompts"
      ><svg class="history-bulk-button-icon" viewBox="0 0 24 24" aria-hidden="true" focusable="false"><rect x="3" y="5" width="12" height="11" rx="2" /><path d="m5 14 3-3 2.5 2.5M18 8h3M18 12h3M17 16h4" /></svg><span>${escapeHtml(translate("history.exportImagesWithPrompts"))}</span></button>
    </div>
    <div class="history-export-picker-status" data-history-export-status></div>
  `;
  document.body.append(picker);
  historyExportPickerEl = picker;
  const rect = trigger.getBoundingClientRect();
  const pickerRect = picker.getBoundingClientRect();
  picker.style.left = `${Math.max(
    12,
    Math.min(
      window.innerWidth - pickerRect.width - 12,
      rect.left,
    ),
  )}px`;
  picker.style.top = `${Math.max(
    12,
    Math.min(
      window.innerHeight - pickerRect.height - 12,
      rect.bottom + 8,
    ),
  )}px`;
  picker
    .querySelector<HTMLElement>(
      "[data-history-export-mode]",
    )
    ?.focus();
}

async function runHistoryExport(
  mode: HistoryExportMode,
  taskIds: string[] = historyExportTaskIds.slice(),
  statusElement: HTMLElement | null = historyExportPickerEl?.querySelector<HTMLElement>(
    "[data-history-export-status]",
  ) || null,
): Promise<void> {
  if (historyExportPending) return;
  if (!taskIds.length) return;
  historyExportPending = true;
  const actionRoot = statusElement?.closest<HTMLElement>("[data-history-action-section]") || historyExportPickerEl;
  actionRoot
    ?.querySelectorAll<HTMLButtonElement>("button")
    .forEach((button) => {
      button.disabled = true;
    });
  setText(statusElement, translate("history.exportPreparing"));
  try {
    const result = await createHistoryExport(taskIds, mode);
    triggerHistoryExportDownload(result);
    setText(
      els.resultSummary,
      `${translate("history.exportStarted")} · ${formatTranslation(
        "history.exportSummary",
        {
          taskCount: result.task_count,
          imageCount: result.image_count,
        },
      )}`,
    );
    if (historyExportPickerEl?.contains(statusElement)) closeHistoryExportPicker();
    else setText(statusElement, translate("history.exportStarted"));
  } catch (error) {
    const message = errorMessage(
      error,
      translate("history.exportFailed"),
    );
    setText(statusElement, message);
    setText(els.resultSummary, message);
  } finally {
    historyExportPending = false;
    actionRoot
      ?.querySelectorAll<HTMLButtonElement>("button")
      .forEach((button) => {
        button.disabled = false;
      });
  }
}

function bindEvents(): void {
  bindHistoryResizerEvents();
  bindHistoryGridResizeObserver();
  bindHistoryGridMutationObserver();
  els.tagManager?.querySelector<HTMLFormElement>(
    "[data-history-tag-create]",
  )?.addEventListener("submit", (event) => {
    event.preventDefault();
    void createHistoryTagFromManager();
  });
  let searchTimer = 0;
  els.search?.addEventListener("input", () => {
    syncHistorySearchClear();
    window.clearTimeout(searchTimer);
    searchTimer = window.setTimeout(() => {
      historyState.q = els.search?.value.trim() || "";
      resetHistoryTaskSelectionState();
      renderHistoryActiveFilters();
      updateHistoryUrl();
      void loadTasks({ reset: true });
    }, 180);
  });
  els.searchClear?.addEventListener("click", () => {
    if (els.search) els.search.value = "";
    syncHistorySearchClear();
    els.search?.focus();
    historyState.q = "";
    resetHistoryTaskSelectionState();
    renderHistoryActiveFilters();
    updateHistoryUrl();
    void loadTasks({ reset: true });
  });
  els.sortToggle?.addEventListener("click", (event) => {
    const target = event.target as HTMLElement | null;
    const button = target?.closest<HTMLElement>("[data-history-sort]");
    if (!button || !els.sortToggle?.contains(button)) return;
    applyHistorySort(button.dataset.historySort || "newest");
  });
  document.addEventListener("change", (event) => {
    const target = event.target as HTMLElement | null;
    const backupScopeInput = target?.closest<HTMLInputElement>(
      'input[name="history-backup-scope"]',
    );
    if (backupScopeInput && els.backupDialog?.contains(backupScopeInput)) {
      renderHistoryBackupScopeEstimates();
      return;
    }
    if (target === els.importFile) {
      const file = els.importFile?.files?.[0];
      if (els.importFile) els.importFile.value = "";
      if (file) void chooseHistoryImport(file);
      return;
    }
    const tagPickerInput =
      target?.closest<HTMLInputElement>(
        ".history-tag-picker input[type=checkbox]",
      );
    if (
      tagPickerInput &&
      historyTagPickerEl?.contains(tagPickerInput)
    ) {
      void applyHistoryTagPickerChange(tagPickerInput);
      return;
    }
  });
  document.addEventListener("click", (event) => {
    const target = event.target as HTMLElement | null;
    if (shouldClearHistoryTaskFromBlankSurface({
      detailMode: (els.detail?.dataset.historyDetailMode || "management") as HistoryDetailMode,
      selectedCount: historyState.selectedTaskIds.size,
      selectionMode: historyState.selectionMode,
      isTaskListBlankSurface: target === els.taskList,
      button: event.button,
      hasModifier: event.shiftKey || event.metaKey || event.ctrlKey || event.altKey,
    })) {
      clearHistoryTaskSelection();
      els.page?.classList.remove("history-detail-open");
      return;
    }
    const removeActiveFilter = target?.closest<HTMLElement>(
      "[data-history-remove-active-filter]",
    );
    if (removeActiveFilter) {
      removeHistoryActiveFilterById(
        removeActiveFilter.dataset.historyRemoveActiveFilter || "",
      );
      return;
    }
    if (target?.closest("[data-history-clear-all-filters]")) {
      clearAllHistoryActiveFilters();
      return;
    }
    const openManagement = target?.closest<HTMLElement>("[data-history-open-management]");
    if (openManagement) {
      openHistoryManagementPanel(openManagement);
      return;
    }
    const enterSelectionMode = target?.closest<HTMLElement>("[data-history-enter-selection-mode]");
    if (enterSelectionMode) {
      historyState.selectionMode = true;
      renderBulkToolbar();
      renderHistoryManagementDetail();
      focusHistoryTaskButton(visibleHistoryTaskIds()[0] || "");
      return;
    }
    if (target?.closest("[data-history-exit-selection-mode]")) {
      clearHistoryTaskSelection();
      return;
    }
    const openSelectionActions = target?.closest<HTMLElement>("[data-history-open-selection-actions]");
    if (openSelectionActions) {
      openHistorySelectionPanel(openSelectionActions);
      return;
    }
    const toggleActionSection = target?.closest<HTMLElement>("[data-history-toggle-action-section]");
    if (toggleActionSection) {
      const requested = toggleActionSection.dataset.historyToggleActionSection === "export"
        ? "export"
        : "organize";
      historyActionPanelExpanded = nextHistoryActionPanelSection(historyActionPanelExpanded, requested);
      closeHistoryExportPicker({ restoreFocus: false });
      closeHistoryOrganizePicker({ restoreFocus: false });
      renderSelectionDetail();
      requestAnimationFrame(() => els.detail
        ?.querySelector<HTMLElement>(`[data-history-toggle-action-section="${requested}"]`)
        ?.focus());
      return;
    }
    if (target?.closest("[data-history-close-backup]")) {
      closeHistoryBackupDialog();
      return;
    }
    if (target?.closest("[data-history-close-import]")) {
      closeHistoryImportDialog();
      return;
    }
    const openBackup = target?.closest<HTMLElement>("[data-history-open-backup]");
    if (openBackup) {
      const preferSelected = openBackup.dataset.historyOpenBackup === "selected";
      closeHistoryOrganizePicker({ restoreFocus: false });
      openHistoryBackupDialog(openBackup, [...historyState.selectedTaskIds], preferSelected);
      return;
    }
    const openImport = target?.closest<HTMLElement>("[data-history-open-import]");
    if (openImport) {
      openHistoryImportDialog(openImport);
      return;
    }
    if (target?.closest("[data-history-start-backup]")) {
      void startHistoryBackup();
      return;
    }
    if (target?.closest("[data-history-cancel-backup]")) {
      void cancelActiveHistoryBackup();
      return;
    }
    if (target?.closest("[data-history-download-backup]")) {
      const job = currentBackupJob;
      if (job) {
        try {
          backupController.download(job);
          renderHistoryBackupDownloaded();
        } catch (error) {
          focusHistoryTransferError("backup", historyBackupErrorText(String((error as { code?: string })?.code || "")));
        }
      }
      return;
    }
    if (target?.closest("[data-history-dismiss-backup]")) {
      if (historyBackupDownloaded) {
        closeHistoryBackupDialog();
        return;
      }
      void dismissHistoryBackupResult();
      return;
    }
    if (target?.closest("[data-history-cancel-import]")) {
      if (currentImportPhase !== "restoring") void cancelActiveHistoryImport();
      return;
    }
    if (target?.closest("[data-history-confirm-import]")) {
      void restoreHistoryImportSelection();
      return;
    }
    if (target?.closest("[data-history-close-export]")) {
      closeHistoryExportPicker();
      return;
    }
    if (target?.closest("[data-history-close-organize]")) {
      closeHistoryOrganizePicker();
      return;
    }
    const organizeButton = target?.closest<HTMLElement>(
      "[data-history-open-organize]",
    );
    if (organizeButton) {
      if (historyOrganizePickerEl) {
        closeHistoryOrganizePicker();
      } else {
        openHistoryOrganizePicker(organizeButton);
      }
      return;
    }
    const exportModeButton = target?.closest<HTMLElement>(
      "[data-history-export-mode]",
    );
    if (exportModeButton) {
      const mode =
        exportModeButton.dataset.historyExportMode ===
        "images_with_prompts"
          ? "images_with_prompts"
          : "images_only";
      const inlineStatus = els.detail?.contains(exportModeButton)
        ? els.detail.querySelector<HTMLElement>("[data-history-action-export-status]")
        : null;
      void runHistoryExport(
        mode,
        inlineStatus ? [...historyState.selectedTaskIds] : historyExportTaskIds.slice(),
        inlineStatus || historyExportPickerEl?.querySelector<HTMLElement>("[data-history-export-status]") || null,
      );
      return;
    }
    const exportButton = target?.closest<HTMLElement>(
      "[data-history-open-export]",
    );
    if (exportButton) {
      const taskId =
        exportButton.dataset.historyOpenExport || "";
      openHistoryExportPicker(
        exportButton,
        taskId
          ? [taskId]
          : [...historyState.selectedTaskIds],
      );
      return;
    }
    if (target?.closest("[data-history-close-tag-picker]")) {
      closeHistoryTagPicker();
      return;
    }
    const tagManageToggle = target?.closest<HTMLElement>(
      "#historyTagManageToggle",
    );
    if (tagManageToggle) {
      const opening = Boolean(els.tagManager?.hidden);
      if (els.tagManager) {
        els.tagManager.hidden = !opening;
        els.tagManager.classList.toggle("hidden", !opening);
      }
      els.tagManageToggle?.setAttribute(
        "aria-expanded",
        opening ? "true" : "false",
      );
      if (opening) els.tagNameInput?.focus();
      return;
    }
    const renameTagButton = target?.closest<HTMLElement>(
      "[data-history-rename-tag]",
    );
    if (renameTagButton) {
      void renameHistoryTagFromManager(
        renameTagButton.dataset.historyRenameTag || "",
      );
      return;
    }
    const deleteTagButton = target?.closest<HTMLElement>(
      "[data-history-delete-tag]",
    );
    if (deleteTagButton) {
      void deleteHistoryTagFromManager(
        deleteTagButton.dataset.historyDeleteTag || "",
      );
      return;
    }
    if (target?.closest("[data-history-favorite-filter]")) {
      applyHistoryOrganizationFilterChange({
        ...historyOrganizationFilters,
        favorite: !historyOrganizationFilters.favorite,
      });
      return;
    }
    if (target?.closest("[data-history-untagged-filter]")) {
      applyHistoryOrganizationFilterChange(
        withHistoryUntaggedFilter(
          historyOrganizationFilters,
          !historyOrganizationFilters.untagged,
        ),
      );
      return;
    }
    const tagFilterButton = target?.closest<HTMLElement>(
      "[data-history-tag-filter]",
    );
    if (tagFilterButton) {
      const tagId =
        tagFilterButton.dataset.historyTagFilter || "";
      applyHistoryOrganizationFilterChange(
        withHistoryTagFilter(
          historyOrganizationFilters,
          tagId,
          !historyOrganizationFilters.tagIds.includes(tagId),
        ),
      );
      return;
    }
    if (target?.closest("[data-history-bulk-favorite]")) {
      closeHistoryOrganizePicker();
      void organizeHistoryTaskIds(
        [...historyState.selectedTaskIds],
        { favorite: true },
      );
      return;
    }
    if (target?.closest("[data-history-bulk-unfavorite]")) {
      closeHistoryOrganizePicker();
      void organizeHistoryTaskIds(
        [...historyState.selectedTaskIds],
        { favorite: false },
      );
      return;
    }
    const favoriteTaskButton = target?.closest<HTMLElement>(
      "[data-history-favorite-task]",
    );
    if (favoriteTaskButton) {
      const taskId =
        favoriteTaskButton.dataset.historyFavoriteTask || "";
      const task =
        historyState.loadedTaskSummaries.get(taskId) ||
        (String(historyState.detailTask?.task_id || "") ===
        taskId
          ? historyState.detailTask
          : null);
      void organizeHistoryTaskIds(
        [taskId],
        { favorite: !Boolean(task?.favorite) },
      );
      return;
    }
    const tagPickerButton = target?.closest<HTMLElement>(
      "[data-history-open-tag-picker]",
    );
    if (tagPickerButton) {
      const tagPickerTrigger = historyOrganizePickerEl?.contains(tagPickerButton)
        ? historyOrganizeTrigger || tagPickerButton
        : tagPickerButton;
      closeHistoryOrganizePicker({ restoreFocus: false });
      const rawMode =
        tagPickerButton.dataset.historyOpenTagPicker || "add";
      const mode =
        rawMode === "remove" || rawMode === "detail"
          ? rawMode
          : "add";
      const taskIds =
        mode === "detail"
          ? [String(historyState.detailTask?.task_id || "")]
          : [...historyState.selectedTaskIds];
      openHistoryTagPicker(tagPickerTrigger, mode, taskIds);
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
      const taskId = taskButton.dataset.historyTaskId || "";
      if (historyState.selectionMode) {
        toggleHistoryTaskSelection(taskId);
      } else {
        applyHistoryTaskSelection([taskId], taskId, taskId);
      }
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
      const taskId = deleteTaskButton.dataset.historyDeleteTask || "";
      if (shouldDeleteCurrentHistorySelection(taskId)) {
        void deleteSelectedTasks();
      } else {
        void deleteSingleHistoryTask(taskId);
      }
      return;
    }
    const referenceHandoffButton = target?.closest<HTMLElement>("[data-history-reference-handoff-url]");
    if (referenceHandoffButton) {
      handoffReferenceToMain(referenceHandoffButton.dataset.historyReferenceHandoffUrl || "");
      return;
    }
    const referenceFileHandoffButton = target?.closest<HTMLElement>("[data-history-reference-file-id]");
    if (referenceFileHandoffButton) {
      handoffReferenceFileToMain(referenceFileHandoffButton.dataset.historyReferenceFileId || "");
      return;
    }
    const copyOutputPromptButton = target?.closest<HTMLElement>("[data-history-copy-output-prompt-index]");
    if (copyOutputPromptButton) {
      void copyOutputPromptToClipboard(copyOutputPromptButton.dataset.historyCopyOutputPromptIndex, copyOutputPromptButton);
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
      const index = Number.parseInt(lightboxButton.dataset.historyLightboxIndex || "0", 10) || 0;
      openHistoryDetailLightbox(index);
      return;
    }
    const inputLightboxButton = target?.closest<HTMLElement>("[data-history-input-lightbox-index]");
    if (inputLightboxButton) {
      const index = Number.parseInt(inputLightboxButton.dataset.historyInputLightboxIndex || "0", 10) || 0;
      openHistoryInputLightbox(index);
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
    if (target?.closest("[data-history-bulk-archive]")) {
      closeHistoryOrganizePicker();
      void archiveSelectedTasks(true);
      return;
    }
    if (target?.closest("[data-history-bulk-restore]")) {
      closeHistoryOrganizePicker();
      void archiveSelectedTasks(false);
      return;
    }
    if (target?.closest("[data-history-bulk-delete]")) {
      void deleteSelectedTasks();
      return;
    }
    if (target?.closest("[data-history-cancel-bulk-delete]")) {
      clearHistoryDeleteConfirmation();
      renderBulkToolbar();
      return;
    }
    if (target?.closest("[data-history-bulk-clear]")) {
      clearHistoryTaskSelection();
      return;
    }
    if (target?.closest("[data-history-detail-close]")) {
      closeDetail();
      return;
    }
    for (const key of HISTORY_FILTER_QUERY_KEYS) {
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
  els.taskList?.addEventListener("dblclick", (event) => {
    const target = event.target as HTMLElement | null;
    const card = target?.closest<HTMLElement>(".history-task-card[data-history-task-card-id]");
    if (!card || !els.taskList?.contains(card)) return;
    event.preventDefault();
    event.stopPropagation();
    void openHistoryTaskLightbox(card.dataset.historyTaskCardId || "");
  });
  els.taskList?.addEventListener("keydown", (event) => {
    if (handleHistoryTaskArrowNavigation(event)) return;
    if (event.key !== "ContextMenu" && !(event.shiftKey && event.key === "F10")) return;
    const target = event.target as HTMLElement | null;
    const card = target?.closest<HTMLElement>(".history-task-card[data-history-task-card-id]");
    if (!card || !els.taskList?.contains(card)) return;
    event.preventDefault();
    const rect = card.getBoundingClientRect();
    openHistoryContextMenu(card.dataset.historyTaskCardId || "", rect.left + 18, rect.top + 18);
  });
  document.addEventListener("click", (event) => {
    const target = event.target as HTMLElement | null;
    if (
      historyExportPickerEl &&
      target &&
      !historyExportPickerEl.contains(target) &&
      !historyExportTrigger?.contains(target)
    ) {
      closeHistoryExportPicker();
    }
    if (
      historyOrganizePickerEl &&
      target &&
      !historyOrganizePickerEl.contains(target) &&
      !historyOrganizeTrigger?.contains(target)
    ) {
      closeHistoryOrganizePicker();
    }
    if (
      historyTagPickerEl &&
      target &&
      !historyTagPickerEl.contains(target) &&
      !historyTagPickerTrigger?.contains(target)
    ) {
      closeHistoryTagPicker();
    }
    if (!historyContextMenuEl || historyContextMenuEl.classList.contains("hidden")) return;
    if (target && historyContextMenuEl.contains(target)) return;
    closeHistoryContextMenu();
  }, true);
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
    historyPositionSaveController.schedule();
  }, { passive: true });
  window.addEventListener("resize", () => {
    closeHistoryContextMenu();
    const widths = getCurrentHistoryLayoutWidths();
    applyHistoryLayoutWidths(widths.left, widths.right, { preserveActiveTask: true });
  }, { passive: true });
  document.addEventListener(LOCALE_CHANGE_EVENT, () => {
    document.title = historyDocumentTitle();
    renderHistoryOrganizationFilters();
    renderHistoryTagManager();
    renderHistoryActiveFilters();
    syncHistoryViewMode();
    syncArchiveButtons();
    if (historyState.detailTask) {
      renderTaskDetail(historyState.detailTask);
    } else {
      syncHistorySelectionDetail();
    }
    rerenderHistoryContextMenu();
    renderBulkToolbar();
    renderHistoryBackupJob(currentBackupJob);
    renderHistoryBackupScopeEstimates();
    renderHistoryImportPhase(currentImportPhase);
    renderHistoryImportPreview(currentImportPreview);
    renderHistoryImportResult(currentImportResult);
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
    if (trapHistoryTransferFocus(event)) return;
    if (handleHistorySelectAllShortcut(event)) return;
    if (event.key !== "Escape") return;
    if (els.backupDialog && !els.backupDialog.hidden) {
      closeHistoryBackupDialog();
      return;
    }
    if (els.importDialog && !els.importDialog.hidden) {
      closeHistoryImportDialog();
      return;
    }
    if (historyExportPickerEl) {
      closeHistoryExportPicker();
      return;
    }
    if (historyOrganizePickerEl) {
      closeHistoryOrganizePicker();
      return;
    }
    if (historyTagPickerEl) {
      closeHistoryTagPicker();
      return;
    }
    if (historyContextMenuEl && !historyContextMenuEl.classList.contains("hidden")) {
      closeHistoryContextMenu();
      return;
    }
    if (isHistoryLightboxOpen()) {
      closeHistoryLightbox();
      return;
    }
    if (historyState.selectionMode && historyState.selectedTaskIds.size === 0) {
      clearHistoryTaskSelection();
      return;
    }
    if (els.page?.classList.contains("history-detail-open")) {
      closeDetail();
      return;
    }
    if (historyState.selectedTaskId) closeDetail();
  });
}

function errorMessage(error: unknown, fallback: string): string {
  return error instanceof Error && error.message ? error.message : fallback;
}

async function bootHistoryPage(): Promise<void> {
  initializeHistoryMobileFilters({
    page: els.page,
    sidebar: els.sidebar,
    trigger: els.mobileFiltersButton,
    backdrop: els.filtersBackdrop,
  });
  initializeHistoryShell({
    selectHistoryTask: loadTaskDetail,
    refreshHistoryTasks: async (task) => {
      await refreshHistoryForRealtimeTask({
        task,
        scroller: els.taskList,
        loadSummary,
        reloadNewestWindow: async () => {
          await loadTasks({ reset: true });
        },
        upsertTask: upsertHistoryTaskSummaryCard,
      });
    },
  });
  applyHistoryLocale();
  restoreHistoryLayoutPreference();
  let summaryLoaded = false;
  await runHistoryPositionBoot({
    params: new URLSearchParams(window.location.search),
    pathname: window.location.pathname,
    snapshot: readHistoryLocationSnapshot(),
    replaceLocation: (url) => window.history.replaceState(null, "", url),
    syncLocation: () => {
      syncStateFromUrl();
      renderHistoryManagementDetail();
      bindEvents();
    },
    loadPage: async (options) => {
      if (!summaryLoaded) {
        await loadSummary();
        summaryLoaded = true;
      }
      return loadTasks(options);
    },
    clearSnapshot: clearHistoryLocationSnapshot,
  });
  await resumeHistoryTransfers();
  if (historyState.selectedTaskId) {
    void loadTaskDetail(historyState.selectedTaskId);
  }
}

window.addEventListener("pagehide", () => {
  endHistoryResize();
  historyGridResizeObserver?.disconnect();
  historyGridMutationObserver?.disconnect();
  historyPositionSaveController.flush();
  backupController.dispose();
  importController.dispose();
}, { once: true });

void bootHistoryPage();

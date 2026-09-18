import {
  shouldClearHistoryTaskFromBlankSurface,
  type HistoryDetailMode
} from "./history-action-panel";
import { historyTaskCardHtml } from "./history-card-view";
import { createHistoryContextMenu } from "./history-context-menu";
import { createHistoryDetailController } from "./history-detail-controller";
import { createHistoryFiltersController } from "./history-filters-controller";
import { createHistoryLayoutController } from "./history-layout-controller";
import {
  closeHistoryLightbox,
  isHistoryLightboxOpen
} from "./history-lightbox";
import { createHistoryListController } from "./history-list-controller";
import { initializeHistoryMobileFilters } from "./history-mobile-filters";
import {
  type HistoryOrganization
} from "./history-organization";
import { createHistoryOrganizationUi } from "./history-organization-ui";
import {
  runHistoryPositionBoot
} from "./history-position-runtime";
import { setText } from "./history-presentation";
import { refreshHistoryForRealtimeTask } from "./history-realtime";
import {
  clearHistoryLocationSnapshot,
  readHistoryLocationSnapshot
} from "./history-scroll-memory";
import { createHistorySelectionModel } from "./history-selection-model";
import {
  historySelectAllTaskIds,
  isHistorySelectAllTasksShortcut,
} from "./history-selection-shortcuts";
import { initializeHistoryShell } from "./history-shell";
import { createHistoryTaskActions } from "./history-task-actions";
import { createHistoryTransferUi } from "./history-transfer-ui";
import { type HistoryTask } from "./history-types";
import {
  captureHistoryScrollAnchor,
  createHistoryPositionSaveController,
  historyTaskArrowTargetCard,
  isHistoryTaskArrowKey
} from "./history-window";
import { LOCALE_CHANGE_EVENT, formatTranslation, translate } from "./i18n";
import { webAppDocumentTitle } from "./web-app-title";

const lifetime = new AbortController();
let eventsBound = false;

const els = {
  page: document.querySelector<HTMLElement>(".history-page"),
  sidebar: document.querySelector<HTMLElement>(".history-sidebar"),
  mobileFiltersButton: document.querySelector<HTMLButtonElement>("#historyMobileFiltersButton"),
  filtersBackdrop: document.querySelector<HTMLButtonElement>("#historyFiltersBackdrop"),
  selectionDock: document.querySelector<HTMLElement>("#historySelectionDock"),
  selectionDockCount: document.querySelector<HTMLElement>("#historySelectionDockCount"),
  taskList: document.querySelector<HTMLElement>("#historyTaskList"),
  detail: document.querySelector<HTMLElement>("#historyDetail"),
  refresh: document.querySelector<HTMLButtonElement>("#historyRefreshButton"),
  backupDialog: document.querySelector<HTMLElement>("#historyBackupDialog"),
  importDialog: document.querySelector<HTMLElement>("#historyImportDialog"),
};

function applyHistoryLocale(): void {
  document.title = historyDocumentTitle();
}

function historyDocumentTitle(): string {
  return webAppDocumentTitle(translate("history.title"), translate("history.documentTitle"));
}

async function refreshHistoryAfterImport(): Promise<void> {
  await filters.loadSummary({ throwOnError: true });
  await list.loadTasks({ reset: true, throwOnError: true });
}

function updateTaskSelectionVisuals(taskId = selection.snapshot().selectedTaskId): void {
  els.taskList?.querySelectorAll<HTMLElement>(".history-task-card").forEach((card) => {
    const cardTaskId = card.dataset.historyTaskCardId || "";
    const active = Boolean(selection.snapshot().selectedTaskIds.size === 1 && taskId && cardTaskId === taskId);
    const selected = selection.snapshot().selectedTaskIds.has(cardTaskId);
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
  const card = list.historyTaskCardElement(taskId);
  const button = card?.querySelector<HTMLElement>("[data-history-task-id]");
  button?.focus({ preventScroll: true });
  layout.ensureHistoryTaskCardVisible(taskId);
}

function handleHistoryTaskArrowNavigation(event: KeyboardEvent): boolean {
  if (isHistoryLightboxOpen()) return false;
  if (!isHistoryTaskArrowKey(event.key)) return false;
  if (event.altKey || event.metaKey || event.ctrlKey) return false;
  const target = event.target as HTMLElement | null;
  const taskButton = target?.closest<HTMLElement>("[data-history-task-id]");
  if (!taskButton || !els.taskList?.contains(taskButton)) return false;
  const taskId = taskButton.dataset.historyTaskId || "";
  const nextCard = historyTaskArrowTargetCard(els.taskList, taskId, event.key, filters.snapshot().view);
  if (!nextCard && filters.snapshot().view === "list" && (event.key === "ArrowLeft" || event.key === "ArrowRight")) return false;
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
  selection.dispatch({ type: "replace", ids: taskIds, anchor: anchorTaskId, primary: primaryTaskId });
  if (!selection.snapshot().selectedTaskId) details.clear();
  actions.clearHistoryDeleteConfirmation();
  filters.updateHistoryUrl();
  updateTaskSelectionVisuals();
  renderBulkToolbar();
  details.syncHistorySelectionDetail();
}

function reconcileHistoryTaskSelection(): void {
  applyHistoryTaskSelection(
    [...selection.snapshot().selectedTaskIds],
    selection.snapshot().selectionAnchorTaskId,
    selection.snapshot().selectedTaskId,
  );
  if (!selection.snapshot().selectedTaskId) {
    els.page?.classList.remove("history-detail-open");
  }
}

function clearHistoryTaskSelection({ updateVisuals = true } = {}): void {
  resetHistoryTaskSelectionState();
  actions.clearHistoryDeleteConfirmation();
  filters.updateHistoryUrl();
  if (updateVisuals) updateTaskSelectionVisuals();
  renderBulkToolbar();
  details.syncHistorySelectionDetail();
}

function resetHistoryTaskSelectionState(): void {
  selection.dispatch({ type: "reset" });
  details.clear();
}

function toggleHistoryTaskSelection(taskId: string, anchor = true): void {
  if (!taskId) return;
  selection.dispatch({ type: "toggle", id: taskId, anchor });
  if (!selection.snapshot().selectedTaskId) details.clear();
  actions.clearHistoryDeleteConfirmation();
  filters.updateHistoryUrl();
  updateTaskSelectionVisuals();
  renderBulkToolbar();
  details.syncHistorySelectionDetail();
}

function selectHistoryTaskRange(anchorTaskId: string, taskId: string): void {
  if (!taskId) return;
  const visibleIds = visibleHistoryTaskIds();
  const fallbackAnchor = selection.snapshot().selectionAnchorTaskId || selection.snapshot().selectedTaskId || taskId;
  const anchor = anchorTaskId || fallbackAnchor;
  const anchorIndex = visibleIds.indexOf(anchor);
  const targetIndex = visibleIds.indexOf(taskId);
  if (anchorIndex < 0 || targetIndex < 0) {
    applyHistoryTaskSelection([...selection.snapshot().selectedTaskIds, taskId], taskId, taskId);
    return;
  }
  const [start, end] = anchorIndex <= targetIndex ? [anchorIndex, targetIndex] : [targetIndex, anchorIndex];
  applyHistoryTaskSelection([...selection.snapshot().selectedTaskIds, ...visibleIds.slice(start, end + 1)], anchor, taskId);
}

function handleHistoryTaskShortcutSelection(taskId: string, event: MouseEvent | KeyboardEvent): boolean {
  if (!taskId || (!event.shiftKey && !event.metaKey && !event.ctrlKey)) return false;
  event.preventDefault();
  event.stopPropagation();
  if (event.shiftKey) {
    selectHistoryTaskRange(selection.snapshot().selectionAnchorTaskId || selection.snapshot().selectedTaskId || taskId, taskId);
    return true;
  }
  toggleHistoryTaskSelection(taskId);
  return true;
}

function historySelectAllShortcutBlocked(): boolean {
  return Boolean(
    (els.backupDialog && !els.backupDialog.hidden)
    || (els.importDialog && !els.importDialog.hidden)
    || organizer.isOpen()
    || contextMenu.isOpen()
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

function renderBulkToolbar(): void {
  const count = selection.snapshot().selectedTaskIds.size;
  els.page?.classList.toggle("history-bulk-selecting", count > 1 || selection.snapshot().selectionMode);
  els.page?.classList.toggle("history-selection-mode", selection.snapshot().selectionMode);
  els.selectionDock?.classList.toggle("hidden", count === 0);
  els.selectionDock?.toggleAttribute("hidden", count === 0);
  setText(
    els.selectionDockCount,
    count ? formatTranslation("history.selectedCount", { count }) : "",
  );
  if (!count) {
    details.resetActionPanel();
    organizer.closeHistoryOrganizePicker({ restoreFocus: false });
  }
  if (count && els.detail?.dataset.historyDetailMode === "selection") details.renderSelectionDetail();
}

function bindEvents(): void {
  if (eventsBound) return;
  eventsBound = true;
  filters.bind();
  layout.bindHistoryResizerEvents();
  layout.bindHistoryGridResizeObserver();
  layout.bindHistoryGridMutationObserver();
  document.addEventListener("change", (event) => {
    const target = event.target as HTMLElement | null;
    if (transfers.handleChange(target)) return;
    const tagPickerInput =
      target?.closest<HTMLInputElement>(
        ".history-tag-picker input[type=checkbox]",
      );
    if (
      tagPickerInput &&
      organizer.tagPickerContains(tagPickerInput)
    ) {
      void organizer.applyHistoryTagPickerChange(tagPickerInput);
      return;
    }
  }, { signal: lifetime.signal });
  document.addEventListener("click", (event) => {
    const target = event.target as HTMLElement | null;
    if (shouldClearHistoryTaskFromBlankSurface({
      detailMode: (els.detail?.dataset.historyDetailMode || "management") as HistoryDetailMode,
      selectedCount: selection.snapshot().selectedTaskIds.size,
      selectionMode: selection.snapshot().selectionMode,
      isTaskListBlankSurface: target === els.taskList,
      button: event.button,
      hasModifier: event.shiftKey || event.metaKey || event.ctrlKey || event.altKey,
    })) {
      clearHistoryTaskSelection();
      els.page?.classList.remove("history-detail-open");
      return;
    }
    const openManagement = target?.closest<HTMLElement>("[data-history-open-management]");
    if (openManagement) {
      details.openHistoryManagementPanel(openManagement);
      return;
    }
    const enterSelectionMode = target?.closest<HTMLElement>("[data-history-enter-selection-mode]");
    if (enterSelectionMode) {
      selection.dispatch({ type: "enter-touch" });
      renderBulkToolbar();
      details.renderHistoryManagementDetail();
      focusHistoryTaskButton(visibleHistoryTaskIds()[0] || "");
      return;
    }
    if (target?.closest("[data-history-exit-selection-mode]")) {
      clearHistoryTaskSelection();
      return;
    }
    const openSelectionActions = target?.closest<HTMLElement>("[data-history-open-selection-actions]");
    if (openSelectionActions) {
      details.openHistorySelectionPanel(openSelectionActions);
      return;
    }
    const toggleActionSection = target?.closest<HTMLElement>("[data-history-toggle-action-section]");
    if (toggleActionSection) {
      const requested = toggleActionSection.dataset.historyToggleActionSection === "export"
        ? "export"
        : "organize";
      details.toggleActionSection(requested);
      return;
    }
    if (transfers.handleClick(target)) return;
    if (organizer.handleClick(target)) return;
    const favoriteTaskButton = target?.closest<HTMLElement>(
      "[data-history-favorite-task]",
    );
    if (favoriteTaskButton) {
      const taskId =
        favoriteTaskButton.dataset.historyFavoriteTask || "";
      const task =
        list.historyTaskSummary(taskId) ||
        (String(details.task()?.task_id || "") ===
          taskId
          ? details.task()
          : null);
      void actions.organizeHistoryTaskIds(
        [taskId],
        { favorite: !Boolean(task?.favorite) },
      );
      return;
    }
    const viewButton = target?.closest<HTMLElement>("[data-history-view]");
    if (viewButton) {
      filters.setHistoryViewMode(viewButton.dataset.historyView || "grid");
      return;
    }
    const taskButton = target?.closest<HTMLElement>("[data-history-task-id]");
    if (taskButton) {
      if (handleHistoryTaskShortcutSelection(taskButton.dataset.historyTaskId || "", event)) return;
      const taskId = taskButton.dataset.historyTaskId || "";
      if (selection.snapshot().selectionMode) {
        toggleHistoryTaskSelection(taskId);
      } else {
        applyHistoryTaskSelection([taskId], taskId, taskId);
      }
      return;
    }
    const selectButton = target?.closest<HTMLElement>("[data-history-output-selected-task-id]");
    if (selectButton) {
      void actions.updateOutputSelection(selectButton);
      return;
    }
    const deleteUnselectedButton = target?.closest<HTMLElement>("[data-history-delete-unselected]");
    if (deleteUnselectedButton) {
      void actions.deleteUnselectedOutputs(deleteUnselectedButton.dataset.historyDeleteUnselected || "");
      return;
    }
    const archiveTaskButton = target?.closest<HTMLElement>("[data-history-archive-task]");
    if (archiveTaskButton) {
      void actions.archiveSingleTask(archiveTaskButton.dataset.historyArchiveTask || "", archiveTaskButton.dataset.historyArchiveValue === "true");
      return;
    }
    const deleteTaskButton = target?.closest<HTMLElement>("[data-history-delete-task]");
    if (deleteTaskButton) {
      const taskId = deleteTaskButton.dataset.historyDeleteTask || "";
      if (actions.shouldDeleteCurrentHistorySelection(taskId)) {
        void actions.deleteSelectedTasks();
      } else {
        void actions.deleteSingleHistoryTask(taskId);
      }
      return;
    }
    const referenceHandoffButton = target?.closest<HTMLElement>("[data-history-reference-handoff-url]");
    if (referenceHandoffButton) {
      actions.handoffReferenceToMain(referenceHandoffButton.dataset.historyReferenceHandoffUrl || "");
      return;
    }
    const referenceFileHandoffButton = target?.closest<HTMLElement>("[data-history-reference-file-id]");
    if (referenceFileHandoffButton) {
      actions.handoffReferenceFileToMain(referenceFileHandoffButton.dataset.historyReferenceFileId || "");
      return;
    }
    const copyOutputPromptButton = target?.closest<HTMLElement>("[data-history-copy-output-prompt-index]");
    if (copyOutputPromptButton) {
      void actions.copyOutputPromptToClipboard(copyOutputPromptButton.dataset.historyCopyOutputPromptIndex, copyOutputPromptButton);
      return;
    }
    const copyPromptButton = target?.closest<HTMLElement>("[data-history-copy-prompt-kind]");
    if (copyPromptButton) {
      void actions.copyPromptToClipboard(copyPromptButton.dataset.historyCopyPromptKind || "original", copyPromptButton);
      return;
    }
    const reuseTaskButton = target?.closest<HTMLElement>("[data-history-reuse-task]");
    if (reuseTaskButton) {
      actions.reuseHistoryTask(reuseTaskButton.dataset.historyReuseTask || "");
      return;
    }
    const lightboxButton = target?.closest<HTMLElement>("[data-history-lightbox-url]");
    if (lightboxButton) {
      const index = Number.parseInt(lightboxButton.dataset.historyLightboxIndex || "0", 10) || 0;
      details.openHistoryDetailLightbox(index);
      return;
    }
    const inputLightboxButton = target?.closest<HTMLElement>("[data-history-input-lightbox-index]");
    if (inputLightboxButton) {
      const index = Number.parseInt(inputLightboxButton.dataset.historyInputLightboxIndex || "0", 10) || 0;
      details.openHistoryInputLightbox(index);
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
      organizer.closeHistoryOrganizePicker();
      void actions.archiveSelectedTasks(true);
      return;
    }
    if (target?.closest("[data-history-bulk-restore]")) {
      organizer.closeHistoryOrganizePicker();
      void actions.archiveSelectedTasks(false);
      return;
    }
    if (target?.closest("[data-history-bulk-delete]")) {
      void actions.deleteSelectedTasks();
      return;
    }
    if (target?.closest("[data-history-cancel-bulk-delete]")) {
      actions.clearHistoryDeleteConfirmation();
      renderBulkToolbar();
      return;
    }
    if (target?.closest("[data-history-bulk-clear]")) {
      clearHistoryTaskSelection();
      return;
    }
    if (target?.closest("[data-history-detail-close]")) {
      details.closeDetail();
      return;
    }
    if (filters.handleClick(target)) return;
  }, { signal: lifetime.signal });
  els.taskList?.addEventListener("contextmenu", (event) => {
    const target = event.target as HTMLElement | null;
    const card = target?.closest<HTMLElement>(".history-task-card[data-history-task-card-id]");
    if (!card || !els.taskList?.contains(card)) return;
    event.preventDefault();
    event.stopPropagation();
    contextMenu.openHistoryContextMenu(card.dataset.historyTaskCardId || "", event.clientX, event.clientY);
  }, { signal: lifetime.signal });
  els.taskList?.addEventListener("dblclick", (event) => {
    const target = event.target as HTMLElement | null;
    const card = target?.closest<HTMLElement>(".history-task-card[data-history-task-card-id]");
    if (!card || !els.taskList?.contains(card)) return;
    event.preventDefault();
    event.stopPropagation();
    void details.openHistoryTaskLightbox(card.dataset.historyTaskCardId || "");
  }, { signal: lifetime.signal });
  els.taskList?.addEventListener("keydown", (event) => {
    if (handleHistoryTaskArrowNavigation(event)) return;
    if (event.key !== "ContextMenu" && !(event.shiftKey && event.key === "F10")) return;
    const target = event.target as HTMLElement | null;
    const card = target?.closest<HTMLElement>(".history-task-card[data-history-task-card-id]");
    if (!card || !els.taskList?.contains(card)) return;
    event.preventDefault();
    const rect = card.getBoundingClientRect();
    contextMenu.openHistoryContextMenu(card.dataset.historyTaskCardId || "", rect.left + 18, rect.top + 18);
  }, { signal: lifetime.signal });
  document.addEventListener("click", (event) => {
    const target = event.target as HTMLElement | null;
    organizer.handleOutsideClick(target);
    if (!contextMenu.isOpen()) return;
    if (target && contextMenu.contains(target)) return;
    contextMenu.closeHistoryContextMenu();
  }, { capture: true, signal: lifetime.signal });
  els.refresh?.addEventListener("click", () => {
    void filters.loadSummary();
    void list.loadTasks({ reset: true });
  }, { signal: lifetime.signal });
  els.taskList?.addEventListener("dragstart", (event) => {
    const target = event.target as HTMLElement | null;
    if (target?.closest(".history-task-thumb img")) event.preventDefault();
  }, { signal: lifetime.signal });
  els.taskList?.addEventListener("scroll", () => {
    contextMenu.closeHistoryContextMenu();
    list.maybeLoadMoreFromScroll();
    historyPositionSaveController.schedule();
  }, { passive: true, signal: lifetime.signal });
  window.addEventListener("resize", () => {
    contextMenu.closeHistoryContextMenu();
    const widths = layout.getCurrentHistoryLayoutWidths();
    layout.applyHistoryLayoutWidths(widths.left, widths.right, { preserveActiveTask: true });
  }, { passive: true, signal: lifetime.signal });
  document.addEventListener(LOCALE_CHANGE_EVENT, () => {
    document.title = historyDocumentTitle();
    filters.renderHistoryOrganizationFilters();
    filters.renderHistoryTagManager();
    filters.renderHistoryActiveFilters();
    filters.syncHistoryViewMode();
    filters.syncArchiveButtons();
    if (details.task()) {
      details.renderTaskDetail(details.task());
    } else {
      details.syncHistorySelectionDetail();
    }
    contextMenu.rerenderHistoryContextMenu();
    renderBulkToolbar();
    transfers.renderLocale();
    list.setLoadMoreState(list.status().loading
      ? translate("history.loadingMore")
      : list.status().exhausted
        ? translate("history.noMore")
        : "", {
      hidden: !list.status().loading && !list.status().exhausted,
      busy: list.status().loading,
    });
  }, { signal: lifetime.signal });
  window.addEventListener("keydown", (event) => {
    if (transfers.trapFocus(event)) return;
    if (handleHistorySelectAllShortcut(event)) return;
    if (event.key !== "Escape") return;
    if (transfers.handleEscape()) return;
    if (organizer.handleEscape()) return;
    if (contextMenu.isOpen()) {
      contextMenu.closeHistoryContextMenu();
      return;
    }
    if (isHistoryLightboxOpen()) {
      closeHistoryLightbox();
      return;
    }
    if (selection.snapshot().selectionMode && selection.snapshot().selectedTaskIds.size === 0) {
      clearHistoryTaskSelection();
      return;
    }
    if (els.page?.classList.contains("history-detail-open")) {
      details.closeDetail();
      return;
    }
    if (selection.snapshot().selectedTaskId) details.closeDetail();
  }, { signal: lifetime.signal });
}

async function bootHistoryPage(): Promise<void> {
  initializeHistoryMobileFilters({
    page: els.page,
    sidebar: els.sidebar,
    trigger: els.mobileFiltersButton,
    backdrop: els.filtersBackdrop,
  });
  initializeHistoryShell({
    selectHistoryTask: details.loadTaskDetail,
    refreshHistoryTasks: async (task) => {
      await refreshHistoryForRealtimeTask({
        task,
        scroller: els.taskList,
        loadSummary: filters.loadSummary,
        reloadNewestWindow: async () => {
          await list.loadTasks({ reset: true });
        },
        upsertTask: list.upsertHistoryTaskSummaryCard,
      });
    },
  });
  applyHistoryLocale();
  layout.restoreHistoryLayoutPreference();
  let summaryLoaded = false;
  await runHistoryPositionBoot({
    params: new URLSearchParams(window.location.search),
    pathname: window.location.pathname,
    snapshot: readHistoryLocationSnapshot(),
    replaceLocation: (url) => window.history.replaceState(null, "", url),
    syncLocation: () => {
      filters.syncStateFromUrl();
      details.renderHistoryManagementDetail();
      bindEvents();
    },
    loadPage: async (options) => {
      if (!summaryLoaded) {
        await filters.loadSummary();
        summaryLoaded = true;
      }
      return list.loadTasks(options);
    },
    clearSnapshot: clearHistoryLocationSnapshot,
  });
  await transfers.resume();
  if (selection.snapshot().selectedTaskId) {
    void details.loadTaskDetail(selection.snapshot().selectedTaskId);
  }
}

window.addEventListener("pagehide", () => {
  lifetime.abort();
  layout.endHistoryResize();
  layout.dispose();
  historyPositionSaveController.flush();
  transfers.dispose();
  filters.dispose();
  list.dispose();
  details.dispose();
  contextMenu.dispose();
  organizer.dispose();
}, { once: true });

function taskCardHtml(task: HistoryTask): string { return historyTaskCardHtml(task, selection.snapshot()); }

const selection = createHistorySelectionModel();

const filters = createHistoryFiltersController({
  selectedTaskId: () => selection.snapshot().selectedTaskId,
  selectLocationTask(id) { selection.dispatch({ type: "location", id }); },
  resetSelection: resetHistoryTaskSelectionState,
  clearDeleteConfirmation: () => actions.clearHistoryDeleteConfirmation(),
  loadTasks: (options) => list.loadTasks(options),
  scheduleLayout: () => layout.scheduleHistoryGridLayout(),
  loadedTasks: () => list.summaries(),
  applyOrganizations: (organizations) => list.applyHistoryOrganizations(organizations),
});

const historyPositionSaveController =
  createHistoryPositionSaveController({
    requestFrame: (callback) => window.requestAnimationFrame(callback),
    cancelFrame: (frameId) => window.cancelAnimationFrame(frameId),
    capture: () => els.taskList
      ? captureHistoryScrollAnchor(els.taskList)
      : null,
    save: filters.saveCurrentHistoryLocation,
  });

const transfers = createHistoryTransferUi({
  backupFilters: filters.currentHistoryBackupFilters,
  selectedTaskIds: () => [...selection.snapshot().selectedTaskIds],
  refreshAfterImport: refreshHistoryAfterImport,
  beforeOpenBackup: () => organizer.closeHistoryOrganizePicker({ restoreFocus: false }),
});

const layout = createHistoryLayoutController({
  view: () => filters.snapshot().view,
  selectedTaskId: () => selection.snapshot().selectedTaskId,
  card: (id) => list.historyTaskCardElement(id),
  closeContextMenu: () => contextMenu.closeHistoryContextMenu(),
});

function onHistoryOrganizationsChanged(organizations: Record<string, HistoryOrganization>, removedTaskIds: string[]): void {
  const removedSet = new Set(removedTaskIds);
  const detailTaskId = String(
    details.task()?.task_id || "",
  );
  const detailOrganization = organizations[detailTaskId];
  if (detailOrganization) {
    details.updateOrganization(detailOrganization);
    if (removedSet.has(detailTaskId)) {
      details.clear();
    } else {
      details.renderTaskDetail(details.task());
    }
  }
  if (removedSet.size) {
    reconcileHistoryTaskSelection();
  } else {
    renderBulkToolbar();
  }
}

const list = createHistoryListController({
  filters,
  layout,
  renderCard: taskCardHtml,
  resetSelectionForLoad() { selection.dispatch({ type: "reload" }); actions.clearHistoryDeleteConfirmation(); actions.resetSingleDelete(); },
  renderToolbar: renderBulkToolbar,
  renderSelection: updateTaskSelectionVisuals,
  enablePositionSave: () => historyPositionSaveController.enable(),
  dropSelection(id) { selection.dispatch({ type: "drop", id, clearAnchor: true }); },
  reconcileSelection: reconcileHistoryTaskSelection,
  organizationsChanged: onHistoryOrganizationsChanged,
});

const details = createHistoryDetailController({
  selection,
  filters,
  list,
  confirmations: () => ({ deleteConfirming: actions.confirmations().deleteConfirming, deleteConfirmTaskId: actions.confirmations().deleteConfirmTaskId, deleteUnselectedConfirmTaskId: actions.confirmations().deleteUnselectedConfirmTaskId }),
  resetTaskConfirmations() { actions.clearHistoryDeleteConfirmation(); actions.resetTaskConfirmations(); },
  renderToolbar: renderBulkToolbar,
  renderSelection: updateTaskSelectionVisuals,
  mountedIds: visibleHistoryTaskIds,
  ensureVisible: layout.ensureHistoryTaskCardVisible,
  closeActionPickers() { organizer.closeHistoryExportPicker({ restoreFocus: false }); organizer.closeHistoryOrganizePicker({ restoreFocus: false }); },
});

const actions = createHistoryTaskActions({
  selection,
  filters,
  list,
  details,
  reconcileSelection: reconcileHistoryTaskSelection,
  renderToolbar: renderBulkToolbar,
  renderSelection: updateTaskSelectionVisuals,
  rerenderContextMenu: () => contextMenu.rerenderHistoryContextMenu(),
  closeContextMenu: () => contextMenu.closeHistoryContextMenu(),
});

const contextMenu = createHistoryContextMenu({
  selection,
  actions,
  list,
  applySelection: applyHistoryTaskSelection,
});

const organizer = createHistoryOrganizationUi({
  selection,
  actions,
  details,
  list,
  filters,
});

void bootHistoryPage();

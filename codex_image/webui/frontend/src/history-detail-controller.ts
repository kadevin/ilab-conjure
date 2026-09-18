import { createGroundingAttribution } from "./grounding-attribution";
import { historyDetailCloseEffect, historyManagementPanelHtml, historySelectionDetailResolution, historySelectionPanelHtml, nextHistoryActionPanelSection, type HistoryActionPanelCopy, type HistoryActionPanelSection, type HistoryDetailMode } from "./history-action-panel";
import { historyDetailImagesHtml, historyDetailImagesLayoutClass, historyInputLightboxUrlsFromTask, historyInputReferencesHtml, historyLightboxUrlsFromTask, historyReferenceFilesHtml, taskOutputRecords, taskSelectedOutputIndexes } from "./history-detail-media";
import type { createHistoryFiltersController } from "./history-filters-controller";
import { openHistoryLightbox, type HistoryLightboxTaskDirection, type HistoryLightboxTaskNavigationContext } from "./history-lightbox";
import type { createHistoryListController } from "./history-list-controller";
import { historyDetailTagsHtml, historyFavoriteButtonHtml, type HistoryOrganization } from "./history-organization";
import { detailTitle, errorMessage, escapeHtml, facetDisplayValue, formatDate, historyTaskArchived, historyTaskDeleteBlocked, historyTaskSourceLabel, positiveInt, promptCompareHtml, revisedPromptText, setText } from "./history-presentation";
import type { createHistorySelectionModel } from "./history-selection-model";
import { formatTranslation, translate } from "./i18n";
import { localizedTaskStatus, taskRecoveryMessage } from "./task-recovery";
import { submittedPromptForTask } from "./transparency-status";

export function createHistoryDetailController(deps: {
  selection: ReturnType<typeof createHistorySelectionModel>;
  filters: Pick<ReturnType<typeof createHistoryFiltersController>, "updateHistoryUrl">;
  list: Pick<ReturnType<typeof createHistoryListController>, "loadTasks" | "status">;
  confirmations(): { deleteConfirming: boolean; deleteConfirmTaskId: string; deleteUnselectedConfirmTaskId: string };
  resetTaskConfirmations(): void;
  renderToolbar(): void;
  renderSelection(taskId?: string): void;
  mountedIds(): string[];
  ensureVisible(id: string): void;
  closeActionPickers(): void;
}) {
  const els = {
    page: document.querySelector<HTMLElement>(".history-page"),
    resultSummary: document.querySelector<HTMLElement>("#historyResultSummary"),
    detail: document.querySelector<HTMLElement>("#historyDetail"),
  };

  let historyDetailLoadToken = 0;

  let historyActionPanelExpanded: HistoryActionPanelSection = "";

  let historyDetailReturnFocus: HTMLElement | null = null;
  let detailTask: any = null;
  async function loadTaskDetail(taskId: string): Promise<void> {
    if (!taskId) return;
    if (deps.selection.snapshot().selectedTaskIds.size !== 1 || !deps.selection.snapshot().selectedTaskIds.has(taskId)) {
      deps.selection.dispatch({ type: "detail", id: taskId });
      deps.renderToolbar();
    }
    const loadToken = ++historyDetailLoadToken;
    const keepCurrentDetail = els.detail?.dataset.historyDetailMode === "task" && Boolean(detailTask?.task_id);
    deps.selection.dispatch({ type: "detail", id: taskId });
    deps.resetTaskConfirmations();
    deps.filters.updateHistoryUrl();
    deps.renderSelection(taskId);
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
      && deps.selection.snapshot().selectedTaskId === taskId
      && deps.selection.snapshot().selectedTaskIds.size === 1
      && deps.selection.snapshot().selectedTaskIds.has(taskId);
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
    detailTask = null;
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
    detailTask = null;
    els.detail.innerHTML = historyManagementPanelHtml(historyActionPanelCopy(), {
      selectionMode: deps.selection.snapshot().selectionMode,
    });
  }

  function renderSelectionDetail(): void {
    if (!els.detail) return;
    const count = deps.selection.snapshot().selectedTaskIds.size;
    if (!count) return;
    els.detail.dataset.historyDetailMode = "selection";
    els.detail.innerHTML = historySelectionPanelHtml({
      copy: historyActionPanelCopy(),
      count,
      expandedSection: historyActionPanelExpanded,
      deleteConfirming: deps.confirmations().deleteConfirming,
    });
  }

  function syncHistorySelectionDetail(): void {
    if (!els.detail) return;
    const resolution = historySelectionDetailResolution({
      selectedCount: deps.selection.snapshot().selectedTaskIds.size,
      selectedTaskId: deps.selection.snapshot().selectedTaskId,
      detailTaskId: String(detailTask?.task_id || ""),
    });
    if (resolution === "selection") {
      renderSelectionDetail();
    } else if (resolution === "task") {
      renderTaskDetail(detailTask);
    } else if (resolution === "load-task") {
      void loadTaskDetail(deps.selection.snapshot().selectedTaskId);
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
    detailTask = task;
    els.detail.dataset.historyDetailMode = "task";
    const taskId = String(task.task_id || deps.selection.snapshot().selectedTaskId || "");
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
    const confirmingDeleteUnselected = deps.confirmations().deleteUnselectedConfirmTaskId === taskId;
    const archived = historyTaskArchived(task);
    const confirmingDeleteTask = deps.confirmations().deleteConfirmTaskId === taskId;
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

  function promptTextForKind(kind: string): string {
    const task = detailTask || {};
    if (kind === "submitted") return submittedPromptForTask(task).trim();
    if (kind === "revised") {
      return revisedPromptText(task);
    }
    return String(task.prompt || task.prompt_preview || "").trim();
  }

  function outputPromptTextForIndex(outputIndex: unknown): string {
    const index = positiveInt(outputIndex);
    if (index === null) return "";
    const record = taskOutputRecords(detailTask || {}).find((output) => output.index === index);
    return String(record?.revisedPrompt || "").trim();
  }

  function openHistoryDetailLightbox(index: number): void {
    const urls = historyLightboxUrlsFromTask(detailTask || {});
    openHistoryLightbox(urls, index, {
      taskId: deps.selection.snapshot().selectedTaskId,
      onTaskNavigate: openHistoryTaskLightboxByDirection,
    });
  }

  function openHistoryInputLightbox(index: number): void {
    const urls = historyInputLightboxUrlsFromTask(detailTask || {});
    openHistoryLightbox(urls, index);
  }

  function historyAdjacentTaskId(taskId: string, direction: HistoryLightboxTaskDirection): string {
    if (!taskId) return "";
    const taskIds = deps.mountedIds();
    const index = taskIds.indexOf(taskId);
    if (index < 0) return "";
    const nextIndex = direction === "previous" ? index - 1 : index + 1;
    return taskIds[nextIndex] || "";
  }

  function shouldLoadHistoryAdjacentTask(taskId: string, direction: HistoryLightboxTaskDirection): boolean {
    if (!taskId) return false;
    const taskIds = deps.mountedIds();
    const index = taskIds.indexOf(taskId);
    if (index < 0) return false;
    if (direction === "previous") return index === 0 && !deps.list.status().newerExhausted;
    return index === taskIds.length - 1 && !deps.list.status().exhausted;
  }

  function syncHistoryLightboxDetail(taskId: string, detail: any): void {
    deps.selection.dispatch({ type: "location", id: taskId });
    deps.resetTaskConfirmations();
    detailTask = detail;
    els.page?.classList.add("history-detail-open");
    deps.filters.updateHistoryUrl();
    deps.renderSelection(taskId);
    deps.renderToolbar();
    deps.ensureVisible(taskId);
    renderTaskDetail(detail);
  }

  async function historyTaskLightboxDetail(taskId: string): Promise<{ detail: any; urls: string[] }> {
    const detail = detailTask?.task_id === taskId ? detailTask : await fetchHistoryTaskDetail(taskId);
    const urls = historyLightboxUrlsFromTask(detail);
    return { detail, urls };
  }

  async function openHistoryTaskLightboxByDirection(
    direction: HistoryLightboxTaskDirection,
    context: HistoryLightboxTaskNavigationContext,
  ): Promise<void> {
    const currentTaskId = context.taskId || deps.selection.snapshot().selectedTaskId;
    let cursorTaskId = currentTaskId;
    const visitedTaskIds = new Set<string>([currentTaskId]);
    for (; ;) {
      let nextTaskId = historyAdjacentTaskId(cursorTaskId, direction);
      if (!nextTaskId && shouldLoadHistoryAdjacentTask(cursorTaskId, direction)) {
        await deps.list.loadTasks({ direction });
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
    deps.selection.dispatch({ type: "reset" });
    detailTask = null;
    els.page?.classList.remove("history-detail-open");
    deps.filters.updateHistoryUrl();
    deps.renderSelection("");
    deps.renderToolbar();
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
    if (!deps.selection.snapshot().selectedTaskIds.size) return;
    historyDetailReturnFocus = trigger;
    renderSelectionDetail();
    els.page?.classList.add("history-detail-open");
    requestAnimationFrame(() => els.detail?.querySelector<HTMLElement>(".history-detail-title")?.focus());
  }
  function toggleActionSection(requested: "export" | "organize"): void {
    historyActionPanelExpanded = nextHistoryActionPanelSection(historyActionPanelExpanded, requested);
    deps.closeActionPickers();
    renderSelectionDetail();
    requestAnimationFrame(() => els.detail
      ?.querySelector<HTMLElement>(`[data-history-toggle-action-section="${requested}"]`)
      ?.focus());
  }

  return {
    loadTaskDetail,
    fetchHistoryTaskDetail,
    renderHistoryManagementDetail,
    renderSelectionDetail,
    syncHistorySelectionDetail,
    renderTaskDetail,
    promptTextForKind,
    outputPromptTextForIndex,
    openHistoryDetailLightbox,
    openHistoryInputLightbox,
    openHistoryTaskLightbox,
    closeDetail,
    openHistoryManagementPanel,
    openHistorySelectionPanel,
    toggleActionSection,
    resetActionPanel() { historyActionPanelExpanded = ""; },
    task: () => detailTask,
    clear() { detailTask = null; },
    updateOrganization(organization: HistoryOrganization) { if (detailTask) detailTask = { ...detailTask, ...organization }; },
    dispose() { historyDetailLoadToken++; },
  };
}

import { copyTextToClipboard } from "./clipboard-text";
import type { createHistoryDetailController } from "./history-detail-controller";
import { taskOutputRecords } from "./history-detail-media";
import type { createHistoryFiltersController } from "./history-filters-controller";
import type { createHistoryListController } from "./history-list-controller";
import { organizeHistoryTasks } from "./history-organization";
import { errorMessage, historyTaskPromptForClipboard, positiveInt, setText } from "./history-presentation";
import type { createHistorySelectionModel } from "./history-selection-model";
import { type HistoryOrganizationChange } from "./history-types";
import { formatTranslation, translate } from "./i18n";

export function createHistoryTaskActions(deps: {
  selection: ReturnType<typeof createHistorySelectionModel>;
  filters: Pick<ReturnType<typeof createHistoryFiltersController>, "supported" | "loadSummary">;
  list: Pick<ReturnType<typeof createHistoryListController>, "applyHistoryOrganizations" | "upsertHistoryTaskSummaryCard" | "removeHistoryTaskIdsFromWindow" | "historyTaskSummary">;
  details: Pick<ReturnType<typeof createHistoryDetailController>, "task" | "renderTaskDetail" | "syncHistorySelectionDetail" | "fetchHistoryTaskDetail" | "promptTextForKind" | "outputPromptTextForIndex">;
  reconcileSelection(): void;
  renderToolbar(): void;
  renderSelection(): void;
  rerenderContextMenu(): void;
  closeContextMenu(): void;
}) {
  const els = {
    resultSummary: document.querySelector<HTMLElement>("#historyResultSummary"),
  };

  const historyState = {
    deleteConfirming: false,
    pendingDeleteTaskIds: [] as string[],
    deleteConfirmTaskId: "",
    deleteUnselectedConfirmTaskId: "",
    contextMenuDeleteConfirmKey: "",
  };
  const HISTORY_TASK_REUSE_HANDOFF_KEY = "codex-image-history-task-reuse-handoff";

  const HISTORY_REFERENCE_HANDOFF_KEY = "codex-image-history-reference-handoff";
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
      deps.list.applyHistoryOrganizations(organizations);
      await deps.filters.loadSummary();
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
    await archiveHistoryTaskIds([...deps.selection.snapshot().selectedTaskIds], archived);
  }

  async function archiveHistoryTaskIds(ids: string[], archived: boolean): Promise<void> {
    if (!ids.length) return;
    setText(els.resultSummary, archived ? translate("archive.archiving") : translate("archive.restoring"));
    try {
      const tasks = await Promise.all(ids.map((taskId) => setTaskArchiveState(taskId, archived)));
      ids.forEach((taskId) => deps.selection.dispatch({ type: "drop", id: taskId }));
      clearHistoryDeleteConfirmation();
      tasks.forEach((task, index) => {
        const taskId = ids[index] || String(task?.task_id || "");
        deps.list.upsertHistoryTaskSummaryCard(taskId, task);
        if (taskId && String(deps.details.task()?.task_id || "") === taskId && task) {
          deps.details.renderTaskDetail(task);
        }
      });
      deps.reconcileSelection();
      await deps.filters.loadSummary();
      setText(els.resultSummary, archived ? formatTranslation("batch.archivedCount", { count: ids.length }) : formatTranslation("archive.restoredCount", { count: ids.length }));
    } catch (error) {
      setText(els.resultSummary, errorMessage(error, archived ? translate("taskActions.archiveFailed") : translate("archive.restoreFailed")));
    } finally {
      deps.renderToolbar();
      deps.details.syncHistorySelectionDetail();
    }
  }

  async function archiveSingleTask(taskId: string, archived: boolean): Promise<void> {
    if (!taskId) return;
    setText(els.resultSummary, archived ? translate("archive.archiving") : translate("archive.restoring"));
    try {
      const task = await setTaskArchiveState(taskId, archived);
      historyState.deleteConfirmTaskId = "";
      historyState.contextMenuDeleteConfirmKey = "";
      if (String(deps.details.task()?.task_id || "") === taskId && task) {
        deps.details.renderTaskDetail(task);
      }
      deps.list.upsertHistoryTaskSummaryCard(taskId, task);
      await deps.filters.loadSummary();
      setText(els.resultSummary, archived ? translate("taskActions.archived") : translate("archive.restored"));
    } catch (error) {
      setText(els.resultSummary, errorMessage(error, archived ? translate("taskActions.archiveFailed") : translate("archive.restoreFailed")));
    }
  }

  async function deleteSelectedTasks(): Promise<void> {
    const selectedIds = [...deps.selection.snapshot().selectedTaskIds].filter(Boolean);
    const ids = historyState.deleteConfirming && historyState.pendingDeleteTaskIds.length
      ? historyState.pendingDeleteTaskIds.slice()
      : selectedIds;
    if (!ids.length) {
      clearHistoryDeleteConfirmation();
      deps.renderToolbar();
      return;
    }
    if (!historyState.deleteConfirming) {
      historyState.pendingDeleteTaskIds = ids;
      historyState.deleteConfirming = true;
      deps.renderToolbar();
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
      deps.selection.dispatch({ type: "failed", ids: failedIds });
      clearHistoryDeleteConfirmation();
      if (deletedIds.length) deps.list.removeHistoryTaskIdsFromWindow(deletedIds);
      await deps.filters.loadSummary();
      if (deletedIds.length) {
        const skipped = failedIds.length ? ` · ${translate("taskActions.deleteFailed")} ${failedIds.length}` : "";
        setText(els.resultSummary, formatTranslation("batch.deletedCount", { count: deletedIds.length, skipped }));
      } else {
        setText(els.resultSummary, translate("taskActions.deleteFailed"));
      }
    } catch (error) {
      setText(els.resultSummary, errorMessage(error, translate("taskActions.deleteFailed")));
    } finally {
      deps.renderSelection();
      deps.renderToolbar();
      deps.details.syncHistorySelectionDetail();
    }
  }

  async function deleteSingleHistoryTask(taskId: string, { confirmInMenu = false }: { confirmInMenu?: boolean } = {}): Promise<boolean> {
    if (!taskId) return false;
    const confirmKey = `task:${taskId}`;
    const confirmed = confirmInMenu ? historyState.contextMenuDeleteConfirmKey === confirmKey : historyState.deleteConfirmTaskId === taskId;
    if (!confirmed) {
      historyState.deleteConfirmTaskId = taskId;
      if (confirmInMenu) historyState.contextMenuDeleteConfirmKey = confirmKey;
      if (String(deps.details.task()?.task_id || "") === taskId) deps.details.renderTaskDetail(deps.details.task());
      if (confirmInMenu) deps.rerenderContextMenu();
      return false;
    }
    setText(els.resultSummary, translate("archive.deleting"));
    try {
      const response = await fetch(`/api/tasks/${encodeURIComponent(taskId)}`, { method: "DELETE" });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(data.detail || translate("taskActions.deleteFailed"));
      deps.selection.dispatch({ type: "drop", id: taskId });
      historyState.deleteConfirmTaskId = "";
      historyState.contextMenuDeleteConfirmKey = "";
      deps.list.removeHistoryTaskIdsFromWindow([taskId]);
      await deps.filters.loadSummary();
      setText(els.resultSummary, translate("taskActions.deleted"));
      return true;
    } catch (error) {
      setText(els.resultSummary, errorMessage(error, translate("taskActions.deleteFailed")));
      return false;
    } finally {
      deps.renderToolbar();
    }
  }

  async function updateOutputSelection(button: HTMLElement): Promise<void> {
    const taskId = button.dataset.historyOutputSelectedTaskId || deps.selection.snapshot().selectedTaskId;
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
      deps.details.renderTaskDetail(data.task || {});
    } catch (error) {
      setText(els.resultSummary, errorMessage(error, translate("taskContext.actionFailed")));
    }
  }

  async function deleteUnselectedOutputs(taskId: string): Promise<void> {
    if (!taskId) return;
    if (historyState.deleteUnselectedConfirmTaskId !== taskId) {
      historyState.deleteUnselectedConfirmTaskId = taskId;
      deps.details.renderTaskDetail(deps.details.task() || {});
      return;
    }
    try {
      const response = await fetch(`/api/tasks/${encodeURIComponent(taskId)}/outputs/delete-unselected`, { method: "POST" });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(data.detail || translate("taskActions.deleteFailed"));
      historyState.deleteUnselectedConfirmTaskId = "";
      deps.details.renderTaskDetail(data.task || {});
      deps.list.upsertHistoryTaskSummaryCard(taskId, data.task || {});
    } catch (error) {
      setText(els.resultSummary, errorMessage(error, translate("taskActions.deleteFailed")));
    }
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
    const text = deps.details.promptTextForKind(kind);
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
    const text = deps.details.outputPromptTextForIndex(outputIndex);
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
    const task = deps.details.task() || {};
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
        const detail = await deps.details.fetchHistoryTaskDetail(taskId);
        const prompt = historyTaskPromptForClipboard(detail);
        if (prompt) prompts.push(prompt);
      } catch {
        const fallback = historyTaskPromptForClipboard(deps.list.historyTaskSummary(taskId));
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
    const detail = await deps.details.fetchHistoryTaskDetail(taskId);
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

  async function deleteHistoryContextSelectedTasks(taskIds: string[]): Promise<void> {
    const confirmKey = historySelectedDeleteConfirmKey(taskIds);
    if (historyState.contextMenuDeleteConfirmKey !== confirmKey) {
      historyState.contextMenuDeleteConfirmKey = confirmKey;
      historyState.deleteConfirming = true;
      historyState.pendingDeleteTaskIds = taskIds.filter(Boolean);
      deps.renderToolbar();
      deps.rerenderContextMenu();
      return;
    }
    deps.selection.dispatch({ type: "context-delete", ids: taskIds });
    historyState.pendingDeleteTaskIds = taskIds.filter(Boolean);
    await deleteSelectedTasks();
    if (!historyState.deleteConfirming) deps.closeContextMenu();
  }

  function historySelectedDeleteConfirmKey(taskIds: string[]): string {
    return `selected:${taskIds.slice().sort().join("|")}`;
  }

  function shouldDeleteCurrentHistorySelection(taskId: string): boolean {
    return Boolean(taskId && deps.selection.snapshot().selectedTaskIds.size > 1 && deps.selection.snapshot().selectedTaskIds.has(taskId));
  }

  function handoffReferenceToMain(url: string): void {
    if (!url) return;
    localStorage.setItem(HISTORY_REFERENCE_HANDOFF_KEY, JSON.stringify([{ url, source: "history", added_at: new Date().toISOString() }]));
    window.location.href = "/";
  }

  function handoffReferenceFileToMain(assetId: string): void {
    if (!/^[0-9a-f]{64}$/.test(assetId)) return;
    const task = deps.details.task() || {};
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
  return {
    organizeHistoryTaskIds,
    clearHistoryDeleteConfirmation,
    archiveSelectedTasks,
    archiveHistoryTaskIds,
    archiveSingleTask,
    deleteSelectedTasks,
    deleteSingleHistoryTask,
    updateOutputSelection,
    deleteUnselectedOutputs,
    copyPromptToClipboard,
    copyOutputPromptToClipboard,
    reuseHistoryTask,
    copyHistoryTaskId,
    copyHistoryTaskPrompts,
    downloadHistoryTasks,
    deleteHistoryContextSelectedTasks,
    historySelectedDeleteConfirmKey,
    shouldDeleteCurrentHistorySelection,
    handoffReferenceToMain,
    handoffReferenceFileToMain,
    confirmations: () => ({ ...historyState, pendingDeleteTaskIds: [...historyState.pendingDeleteTaskIds] }),
    resetSingleDelete() { historyState.deleteConfirmTaskId = ""; },
    resetTaskConfirmations() { clearHistoryDeleteConfirmation(); historyState.deleteConfirmTaskId = ""; historyState.deleteUnselectedConfirmTaskId = ""; },
  };
}

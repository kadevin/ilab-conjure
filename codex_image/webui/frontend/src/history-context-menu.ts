import type { createHistoryListController } from "./history-list-controller";
import { errorMessage, escapeHtml, historyTaskArchived, historyTaskDeleteBlocked, historyTaskGeneratedCount, setText } from "./history-presentation";
import type { createHistorySelectionModel } from "./history-selection-model";
import type { createHistoryTaskActions } from "./history-task-actions";
import { type HistoryContextMenuMode } from "./history-types";
import { translate } from "./i18n";

export function createHistoryContextMenu(deps: {
  selection: ReturnType<typeof createHistorySelectionModel>;
  applySelection(ids: string[], anchor: string, primary: string): void;
  actions: Pick<ReturnType<typeof createHistoryTaskActions>, "confirmations" | "historySelectedDeleteConfirmKey" | "shouldDeleteCurrentHistorySelection" | "deleteHistoryContextSelectedTasks" | "deleteSingleHistoryTask" | "reuseHistoryTask" | "copyHistoryTaskPrompts" | "copyHistoryTaskId" | "downloadHistoryTasks" | "archiveSingleTask" | "archiveHistoryTaskIds">;
  list: Pick<ReturnType<typeof createHistoryListController>, "historyTaskSummary">;
}) {
  const els = {
    resultSummary: document.querySelector<HTMLElement>("#historyResultSummary"),
  };

  const historyState = {

    contextMenu: {
      mode: "single" as HistoryContextMenuMode,
      taskId: "",
      taskIds: [] as string[],
      x: 0,
      y: 0,
    },

  };

  let historyContextMenuEl: HTMLElement | null = null;
  function selectedHistoryContextTaskIds(clickedTaskId: string): string[] {
    if (deps.selection.snapshot().selectedTaskIds.size > 1 && deps.selection.snapshot().selectedTaskIds.has(clickedTaskId)) {
      return [...deps.selection.snapshot().selectedTaskIds].filter(Boolean);
    }
    if (deps.selection.snapshot().selectedTaskIds.size !== 1 || !deps.selection.snapshot().selectedTaskIds.has(clickedTaskId)) {
      deps.applySelection([clickedTaskId], clickedTaskId, clickedTaskId);
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
    const summary = deps.list.historyTaskSummary(taskId);
    const archived = historyTaskArchived(summary);
    const blocked = historyTaskDeleteBlocked(summary);
    const hasOutput = historyTaskGeneratedCount(summary) > 0;
    const confirmingDelete = deps.actions.confirmations().contextMenuDeleteConfirmKey === `task:${taskId}`;
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
    const confirmKey = deps.actions.historySelectedDeleteConfirmKey(taskIds);
    const confirmingDelete = deps.actions.confirmations().contextMenuDeleteConfirmKey === confirmKey;
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
        if (deps.actions.shouldDeleteCurrentHistorySelection(taskId)) {
          await deps.actions.deleteHistoryContextSelectedTasks([...deps.selection.snapshot().selectedTaskIds]);
          return;
        }
        const deleted = await deps.actions.deleteSingleHistoryTask(taskId, { confirmInMenu: true });
        if (deleted) closeHistoryContextMenu();
        return;
      }
      if (action === "delete-selected") {
        await deps.actions.deleteHistoryContextSelectedTasks(taskIds);
        return;
      }
      closeHistoryContextMenu();
      if (action === "reuse") {
        deps.actions.reuseHistoryTask(taskId);
      } else if (action === "copy-prompt") {
        await deps.actions.copyHistoryTaskPrompts([taskId]);
      } else if (action === "copy-id") {
        await deps.actions.copyHistoryTaskId([taskId]);
      } else if (action === "download") {
        await deps.actions.downloadHistoryTasks([taskId]);
      } else if (action === "archive") {
        const archived = historyTaskArchived(deps.list.historyTaskSummary(taskId));
        await deps.actions.archiveSingleTask(taskId, !archived);
      } else if (action === "copy-prompts") {
        await deps.actions.copyHistoryTaskPrompts(taskIds);
      } else if (action === "copy-ids") {
        await deps.actions.copyHistoryTaskId(taskIds);
      } else if (action === "download-selected") {
        await deps.actions.downloadHistoryTasks(taskIds);
      } else if (action === "archive-selected") {
        await deps.actions.archiveHistoryTaskIds(taskIds, true);
      } else if (action === "restore-selected") {
        await deps.actions.archiveHistoryTaskIds(taskIds, false);
      }
    } catch (error) {
      setText(els.resultSummary, errorMessage(error, translate("taskContext.actionFailed")));
    }
  }

  function clampNumber(value: number, min: number, max: number): number { return Math.min(max, Math.max(min, value)); }

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
  function isOpen(): boolean { return Boolean(historyContextMenuEl && !historyContextMenuEl.classList.contains("hidden")); }

  return {
    openHistoryContextMenu,
    closeHistoryContextMenu,
    rerenderHistoryContextMenu,
    isOpen,
    contains: (target: Node) => Boolean(historyContextMenuEl?.contains(target)),
    dispose() { historyContextMenuEl?.remove(); historyContextMenuEl = null; },
  };
}

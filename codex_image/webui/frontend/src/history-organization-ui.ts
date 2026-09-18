import type { createHistoryDetailController } from "./history-detail-controller";
import { createHistoryExport, triggerHistoryExportDownload, type HistoryExportMode } from "./history-export";
import type { createHistoryFiltersController } from "./history-filters-controller";
import type { createHistoryListController } from "./history-list-controller";
import { createHistoryTagForTasks, historyTagPickerCreateHtml, historyTagPickerHtml, type HistoryTag } from "./history-organization";
import { errorMessage, escapeHtml, setText } from "./history-presentation";
import type { createHistorySelectionModel } from "./history-selection-model";
import type { createHistoryTaskActions } from "./history-task-actions";
import { formatTranslation, translate } from "./i18n";

export function createHistoryOrganizationUi(deps: {
  selection: ReturnType<typeof createHistorySelectionModel>;
  actions: Pick<ReturnType<typeof createHistoryTaskActions>, "organizeHistoryTaskIds">;
  details: Pick<ReturnType<typeof createHistoryDetailController>, "task">;
  list: Pick<ReturnType<typeof createHistoryListController>, "applyHistoryOrganizations">;
  filters: Pick<ReturnType<typeof createHistoryFiltersController>, "tags" | "loadSummary" | "historyTagCreateErrorMessage">;
}) {
  const els = {
    resultSummary: document.querySelector<HTMLElement>("#historyResultSummary"),
    detail: document.querySelector<HTMLElement>("#historyDetail"),
  };

  let historyTagPickerEl: HTMLElement | null = null;

  let historyTagPickerTrigger: HTMLElement | null = null;

  let historyTagPickerMode: "add" | "remove" | "detail" = "add";

  let historyTagPickerTaskIds: string[] = [];

  let historyTagPickerCreatePending = false;

  let historyExportPickerEl: HTMLElement | null = null;

  let historyExportTrigger: HTMLElement | null = null;

  let historyExportTaskIds: string[] = [];

  let historyExportPending = false;

  let historyOrganizePickerEl: HTMLElement | null = null;

  let historyOrganizeTrigger: HTMLElement | null = null;
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
        String(deps.details.task()?.task_id || "") ===
        historyTagPickerTaskIds[0]
        ? (deps.details.task()?.tags || []).map(
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
      ${deps.filters.tags().length
        ? historyTagPickerHtml(
          deps.filters.tags(),
          selectedTagIds,
          escapeHtml,
        )
        : `<div class="history-tag-manager-empty">${escapeHtml(translate("history.noTags"))}</div>`
      }
    </div>
    ${mode === "remove"
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
      deps.list.applyHistoryOrganizations(result.organizations);
      await deps.filters.loadSummary();
      setText(
        els.resultSummary,
        `${translate("history.createTag")}：${result.tag.name}`,
      );
    } catch (error) {
      const message = deps.filters.historyTagCreateErrorMessage(error);
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
    await deps.actions.organizeHistoryTaskIds(
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
    if (!deps.selection.snapshot().selectedTaskIds.size) return;
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
        <span>${escapeHtml(formatTranslation("history.selectedCount", { count: deps.selection.snapshot().selectedTaskIds.size }))}</span>
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
  function handleClick(target: HTMLElement | null): boolean {
    if (target?.closest("[data-history-close-export]")) {
      closeHistoryExportPicker();
      return true;
    }
    if (target?.closest("[data-history-close-organize]")) {
      closeHistoryOrganizePicker();
      return true;
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
      return true;
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
        inlineStatus ? [...deps.selection.snapshot().selectedTaskIds] : historyExportTaskIds.slice(),
        inlineStatus || historyExportPickerEl?.querySelector<HTMLElement>("[data-history-export-status]") || null,
      );
      return true;
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
          : [...deps.selection.snapshot().selectedTaskIds],
      );
      return true;
    }
    if (target?.closest("[data-history-close-tag-picker]")) {
      closeHistoryTagPicker();
      return true;
    }
    if (target?.closest("[data-history-bulk-favorite]")) {
      closeHistoryOrganizePicker();
      void deps.actions.organizeHistoryTaskIds(
        [...deps.selection.snapshot().selectedTaskIds],
        { favorite: true },
      );
      return true;
    }
    if (target?.closest("[data-history-bulk-unfavorite]")) {
      closeHistoryOrganizePicker();
      void deps.actions.organizeHistoryTaskIds(
        [...deps.selection.snapshot().selectedTaskIds],
        { favorite: false },
      );
      return true;
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
          ? [String(deps.details.task()?.task_id || "")]
          : [...deps.selection.snapshot().selectedTaskIds];
      openHistoryTagPicker(tagPickerTrigger, mode, taskIds);
      return true;
    }

    return false;
  }
  function handleOutsideClick(target: HTMLElement | null): void {
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
  }
  function handleEscape(): boolean {
    if (historyExportPickerEl) {
      closeHistoryExportPicker();
      return true;
    }
    if (historyOrganizePickerEl) {
      closeHistoryOrganizePicker();
      return true;
    }
    if (historyTagPickerEl) {
      closeHistoryTagPicker();
      return true;
    }

    return false;
  }

  return {
    applyHistoryTagPickerChange,
    closeHistoryOrganizePicker,
    closeHistoryExportPicker,
    handleClick,
    handleOutsideClick,
    handleEscape,
    tagPickerContains: (target: Node) => Boolean(historyTagPickerEl?.contains(target)),
    isOpen: () => Boolean(historyTagPickerEl || historyExportPickerEl || historyOrganizePickerEl),
    dispose() { closeHistoryTagPicker({ restoreFocus: false }); closeHistoryExportPicker({ restoreFocus: false }); closeHistoryOrganizePicker({ restoreFocus: false }); },
  };
}

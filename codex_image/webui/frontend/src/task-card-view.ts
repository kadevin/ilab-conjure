import { groundingSourceCount } from "./grounding-attribution";
import { formatTranslation, translate } from "./i18n";
import { modelFamilyBrandMarkHtml } from "./model-family-icons";
import type { WebUIState } from "./state";
import { taskWasCancelled } from "./task-cancellation";
import { TASK_QUEUE_REORDER_HINT_STORAGE_KEY, taskCardSwipeActionsForState, type TaskCardSwipeAction, type TaskCardSwipeActions } from "./task-card-swipe-logic";
import type { QueueTaskIdSections } from "./task-list-types";
import { taskCanvasSummaryParts, taskChannelLabel, taskModelDisplayName, taskModelFamilyId } from "./task-model-summary";

export interface TaskCardViewDependencies {
  getState: () => Readonly<Pick<WebUIState, "activeTaskGroupCollapsed" | "batchMode" | "batchSelectedTaskIds" | "generationCatalog" | "queue" | "selectedTaskId" | "taskSidebarGroupLoadError" | "taskSidebarGroupLoadedCounts" | "taskSidebarGroupLoading">>;
  activeTaskSections: (tasks: any[]) => { running: any[]; waiting: any[] };
  compressTaskImageBlockStates: (states: any[]) => any[];
  elapsedTimerSpan: (key: string, value: any) => string;
  escapeHtml: (value: any) => string;
  formatTaskCardStatus: (task: any) => string;
  formatTaskStatus: (task: any) => string;
  queueTaskIdsBySection: () => QueueTaskIdSections;
  taskApiProviderId: (task: any) => string;
  taskApiProviderLabel: (task: any) => string;
  taskCardRetryStateText: (task: any) => string;
  taskCompletionTimestampText: (task: any) => { shortText?: string } | null;
  taskCompletionTimestampTitle: (task: any) => string;
  taskDurationText: (task: any) => string;
  taskGroupCount: (group: any) => number;
  taskHasUnreadUpdate: (task: any) => boolean;
  taskImageBlockStates: (task: any) => any[];
  taskImageStatusCounts: (states: any[]) => { running: number; queued: number; waiting: number };
  taskInputPreviewUrls: (task: any) => string[];
  taskOutputUrls: (task: any) => string[];
  taskProgressStartValue: (task: any) => any;
  taskQueueSection: (task: any, queueIds?: QueueTaskIdSections) => string;
  taskRetryStateText: (task: any) => string;
  taskRuntimeText: (task: any) => string;
  taskThumbnailUrls: (task: any) => string[];
  timestampMs: (value: any) => number | null;
  waitingQueueIndex: (taskId: any, queueIds?: QueueTaskIdSections) => number;
  isQueueDispatchPending: () => boolean;
}

export function createTaskCardView(dependencies: TaskCardViewDependencies) {
  const { getState, activeTaskSections, compressTaskImageBlockStates, elapsedTimerSpan, escapeHtml, formatTaskCardStatus, formatTaskStatus, queueTaskIdsBySection, taskApiProviderId, taskApiProviderLabel, taskCardRetryStateText, taskCompletionTimestampText, taskCompletionTimestampTitle, taskDurationText, taskGroupCount, taskHasUnreadUpdate, taskImageBlockStates, taskImageStatusCounts, taskInputPreviewUrls, taskOutputUrls, taskProgressStartValue, taskQueueSection, taskRetryStateText, taskRuntimeText, taskThumbnailUrls, timestampMs, waitingQueueIndex, isQueueDispatchPending } = dependencies;
  const TASK_THUMB_OUTER_SPIN_DURATION_MS = 1300;
  const TASK_THUMB_INNER_SPIN_DURATION_MS = 950;
  const TASK_THUMB_INNER_SPIN_OFFSET_MS = 280;

  function expandedTaskGroupHeaderHtml(group: any, options: { startExpanded?: boolean } = {}) {
    const groupKey = escapeHtml(group.key);
    const startExpanded = options.startExpanded !== false;
    return `
    <button
      class="task-group-header task-group-header-split"
      type="button"
      data-task-group-toggle-key="${groupKey}"
      data-task-group-expanded="true"
      aria-expanded="${startExpanded ? "true" : "false"}"
      aria-label="${escapeHtml(formatTranslation("taskGroup.collapse", { label: group.label }))}"
    >
      <span class="task-group-label-button">
        <span class="task-group-title">
          <span class="task-group-label">${escapeHtml(group.label)}</span>
          <span class="task-group-count-separator" aria-hidden="true">·</span>
          <span class="task-group-count">${taskGroupCount(group)}</span>
        </span>
      </span>
      <span
        class="task-group-arrow-button"
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

  function renderExpandedTaskGroupBodyShellHtml(group: any) {
    const groupKey = escapeHtml(group.key);
    return `
    <section class="task-group task-group-expanded" data-task-group="${groupKey}">
      <div class="task-group-items task-group-items-expanded" data-expanded-task-group-items-key="${groupKey}"></div>
    </section>
  `;
  }

  function renderExpandedTaskGroupShellHtml(group: any, options: { startExpanded?: boolean } = {}) {
    const groupKey = escapeHtml(group.key);
    return `
    <section class="task-group task-group-expanded" data-task-group="${groupKey}">
      ${expandedTaskGroupHeaderHtml(group, options)}
      <div class="task-group-items task-group-items-expanded" data-expanded-task-group-items-key="${groupKey}"></div>
    </section>
  `;
  }

  function activeTaskSectionHtml(key: "running" | "waiting", label: string, tasks: any[]) {
    if (!tasks.length) return "";
    const sectionClass = key === "running"
      ? 'class="task-active-section task-active-section-running"'
      : 'class="task-active-section task-active-section-waiting"';
    const sectionData = key === "running"
      ? 'data-active-task-section="running"'
      : 'data-active-task-section="waiting"';
    const reorderHint = key === "waiting" ? taskQueueReorderHintHtml(tasks.length) : "";
    return `
    <div ${sectionClass} ${sectionData}>
      <div class="task-active-section-title">
        <span class="task-active-section-heading">
          <span>${escapeHtml(label)}</span>
          <span class="task-active-section-count-separator" aria-hidden="true">·</span>
          <span class="task-active-section-count">${tasks.length}</span>
        </span>
        ${reorderHint}
      </div>
      <div class="task-active-section-items">
        ${tasks.map((task: any) => taskCardHtml(task)).join("")}
      </div>
    </div>
  `;
  }

  function activeTaskDispatchPendingHtml() {
    return `
    <div class="task-active-empty" data-active-task-section="dispatch-pending">
      ${translate("taskGroup.dispatchPending")}
    </div>
  `;
  }

  function activeTaskGroupHtml(group: any) {
    const state = getState();
    const groupKey = escapeHtml(group.key);
    const sections = activeTaskSections(group.tasks || []);
    const dispatchPending = Boolean(isQueueDispatchPending());
    const collapsed = Boolean(state.activeTaskGroupCollapsed);
    const body = [
      activeTaskSectionHtml("running", translate("taskGroup.running"), sections.running),
      activeTaskSectionHtml("waiting", translate("taskGroup.waiting"), sections.waiting),
      !sections.running.length && !sections.waiting.length && dispatchPending ? activeTaskDispatchPendingHtml() : "",
    ].join("");
    const activeLabel = escapeHtml(group.label);
    const activeCount = group.tasks.length;
    const toggleLabel = escapeHtml(formatTranslation(collapsed ? "taskGroup.expand" : "taskGroup.collapse", { label: group.label }));
    return `
    <section class="task-group task-group-expanded task-group-active${collapsed ? " task-active-collapsed" : ""}" data-task-group="${groupKey}">
      <button
        class="task-group-header task-group-header-split task-active-group-header"
        type="button"
        data-active-task-group-toggle="true"
        aria-expanded="${collapsed ? "false" : "true"}"
        aria-label="${toggleLabel}"
      >
        <span class="task-group-label-button">
          <span class="task-group-title">
            <span class="task-group-label">${activeLabel}</span>
            <span class="task-group-count-separator" aria-hidden="true">·</span>
            <span class="task-group-count">${activeCount}</span>
          </span>
        </span>
        <span class="task-history-anchor-arrow" aria-hidden="true">
          <span class="task-group-toggle" aria-hidden="true">
            <svg class="task-group-toggle-icon" viewBox="0 0 12 12" focusable="false">
              <path d="M4 2.5 8 6 4 9.5" fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" stroke-width="1.8"/>
            </svg>
          </span>
        </span>
      </button>
      <div class="task-group-items task-group-items-expanded" data-active-task-group-items aria-hidden="${collapsed ? "true" : "false"}"${collapsed ? " inert" : ""}>
        ${body}
      </div>
    </section>
  `;
  }

  function expandedTaskGroupHtml(group: any) {
    const groupKey = escapeHtml(group.key);
    return `
    <section class="task-group task-group-expanded" data-task-group="${groupKey}">
      ${expandedTaskGroupHeaderHtml(group)}
      <div class="task-group-items task-group-items-expanded">
        ${group.tasks.map((task: any) => taskCardHtml(task)).join("")}
      </div>
    </section>
  `;
  }

  function taskGroupHtml(group: any) {
    return expandedTaskGroupHtml(group);
  }

  function taskGroupButtonLabel(group: any) {
    return formatTranslation("taskGroup.buttonLabel", { label: group.label, count: taskGroupCount(group) });
  }

  function taskQueueReorderHintVisible(waitingCount: number): boolean {
    if (waitingCount < 2) return false;
    try {
      return window.localStorage.getItem(TASK_QUEUE_REORDER_HINT_STORAGE_KEY) !== "1";
    } catch {
      return true;
    }
  }

  function taskQueueReorderHintHtml(waitingCount: number): string {
    if (!taskQueueReorderHintVisible(waitingCount)) return "";
    return `<span class="task-queue-reorder-hint">${escapeHtml(translate("queue.dragWaiting"))}</span>`;
  }

  function taskCardSwipeActionLabel(action: TaskCardSwipeAction): string {
    if (action === "archive") return translate("action.archive");
    if (action === "delete") return translate("action.delete");
    if (action === "stop") return translate("action.stop");
    if (action === "promote") return translate("queue.promote");
    return translate("action.cancel");
  }

  function taskCardSwipeActionTitle(action: TaskCardSwipeAction): string {
    if (action === "stop") return translate("queue.cancelRunningTitle");
    if (action === "promote") return translate("queue.promoteTitle");
    if (action === "cancel") return translate("batch.cancelSelected");
    return taskCardSwipeActionLabel(action);
  }

  function taskCardSwipeActionHtml(action: TaskCardSwipeAction | null): string {
    if (!action) return "";
    const label = escapeHtml(taskCardSwipeActionLabel(action));
    const title = escapeHtml(taskCardSwipeActionTitle(action));
    return `<button class="task-card-swipe-action task-card-swipe-${action}" type="button" data-task-card-action="${action}" aria-label="${title}" title="${title}" tabindex="-1" disabled>${label}</button>`;
  }

  function taskCardSwipeActionsHtml(actions: TaskCardSwipeActions) {
    if (!actions.positive && !actions.negative) return "";
    const actionGroupLabel = escapeHtml(translate("taskActions.group"));
    return `
      <div class="task-card-swipe-actions" role="group" aria-label="${actionGroupLabel}" aria-hidden="true" inert>
        ${taskCardSwipeActionHtml(actions.positive)}
        ${taskCardSwipeActionHtml(actions.negative)}
      </div>
  `;
  }

  function taskCardSwipeKeyboardShortcuts(actions: TaskCardSwipeActions, queueReorderable = false): string {
    const shortcuts = ["Shift+F10"];
    if (actions.negative) shortcuts.push("Delete", "Shift+ArrowLeft");
    if (actions.positive) shortcuts.push("Shift+ArrowRight");
    if (queueReorderable) shortcuts.push("Alt+ArrowUp", "Alt+ArrowDown");
    return shortcuts.join(" ");
  }

  function taskCardHtml(task: any) {
    const state = getState();
    const image = taskThumbHtml(task);
    const active = String(task.task_id) === String(state.selectedTaskId) ? " active" : "";
    const activeCurrent = active ? ' aria-current="true"' : "";
    const unread = taskHasUnreadUpdate(task);
    const unreadClass = unread ? " unread" : "";
    const statusClass = task.status ? ` ${escapeHtml(task.status)}` : "";
    const title = escapeHtml(task.prompt || task.mode || "Untitled");
    const taskId = escapeHtml(task.task_id);
    const showImageSummary = taskImageSummaryVisible(task);
    const imageBlocks = showImageSummary ? taskImageBlocksHtml(task) : "";
    const imageSummary = showImageSummary ? escapeHtml(taskImageSummaryText(task)) : "";
    const imageSummaryHtml = imageSummary ? `<span class="task-image-summary">${imageSummary}</span>` : "";
    const groundingCount = groundingSourceCount(task);
    const groundingHtml = groundingCount > 0
      ? `<span class="task-grounding-badge">${escapeHtml(formatTranslation("grounding.sourceCount", { count: groundingCount }))}</span>`
      : "";
    const retryFullText = taskRetryStateText(task);
    const retryText = taskCardRetryStateText(task) || retryFullText;
    const runningTimerHtml = taskCardRunningTimerHtml(task, taskId);
    const statusLabel = taskStatusLabelHtml(task);
    const modelFamilyIcon = taskModelFamilyIconHtml(task);
    const statusMetaText = retryText
      ? taskMetaDetailsWithCompletionText(task)
      : taskMetaDetailsText(task);
    const statusMeta = escapeHtml(statusMetaText);
    const taskTime = taskCardCompletionTimeText(task);
    const runtime = taskCardRuntimeText(task);
    const runtimeFullText = taskRuntimeText(task);
    const completionTitle = taskCompletionTimestampTitle(task);
    const runtimeTitleText = [runtimeFullText, completionTitle].filter(Boolean).join(" · ");
    const runtimeTitle = runtimeTitleText ? ` title="${escapeHtml(runtimeTitleText)}"` : "";
    const runtimeHtml = runtime ? `<span class="task-runtime" data-task-runtime-id="${taskId}" data-task-completed-at-id="${taskId}"${runtimeTitle}>${escapeHtml(runtime)}</span>` : "";
    const topTimeHtml = runningTimerHtml || runtimeHtml;
    const imageRow = showImageSummary ? `
          <span class="task-image-row">
            ${imageBlocks}
            <span class="task-status-row task-status-inline" aria-label="${escapeHtml(taskStatusAccessibleLabel(task))}">
              ${statusLabel}
              ${modelFamilyIcon}
            </span>
            ${imageSummaryHtml}
          </span>
    ` : "";
    const retryTitle = retryFullText && retryFullText !== retryText ? ` title="${escapeHtml(retryFullText)}"` : "";
    const retryHtml = retryText ? `<span class="task-retry-state" data-task-retry-id="${taskId}"${retryTitle}>${escapeHtml(retryText)}</span>` : "";
    const timeHtml = !retryText && taskTime ? `<span class="task-card-time">${escapeHtml(taskTime)}</span>` : "";
    const detailRightHtml = retryHtml || timeHtml;
    const detailRowClass = detailRightHtml ? "task-detail-row" : "task-detail-row task-detail-row-meta-only";
    const detailRow = statusMeta || detailRightHtml ? `
        <div class="${detailRowClass}">
          <span class="task-status-meta" data-task-meta-id="${taskId}">${statusMeta}</span>
          ${detailRightHtml}
        </div>
    ` : "";
    const batchSelected = state.batchSelectedTaskIds.includes(String(task.task_id));
    const batchClass = state.batchMode ? " batch-mode" : "";
    const batchSelectedClass = batchSelected ? " batch-selected" : "";
    const queueIds = queueTaskIdsBySection();
    const queueSection = taskQueueSection(task, queueIds);
    const queueClass = queueSection ? ` queue-${escapeHtml(queueSection)}` : "";
    const waitingIndexValue = waitingQueueIndex(task.task_id, queueIds);
    const queueReorderable = queueSection === "waiting"
      && waitingIndexValue >= 0
      && (state.queue.waiting || []).length > 1;
    const queueReorderDescription = queueReorderable
      ? escapeHtml(translate("queue.dragWaiting"))
      : "";
    const queueReorderData = queueReorderable
      ? ` data-queue-reorderable="true" aria-description="${queueReorderDescription}"`
      : "";
    const queueTaskData = queueSection === "waiting"
      ? ` data-queue-task-id="${taskId}"${queueReorderData}`
      : "";
    const swipeActions = taskCardSwipeActionsForState(
      queueSection,
      String(task.status || ""),
      Boolean(task.local_pending),
    );
    const swipeEnabled = Boolean(swipeActions.positive || swipeActions.negative);
    const swipeActionsHtml = taskCardSwipeActionsHtml(swipeActions);
    const swipeKeyboardShortcuts = escapeHtml(taskCardSwipeKeyboardShortcuts(swipeActions, queueReorderable));
    const batchSelect = state.batchMode ? `
      <button class="task-select-button" type="button" role="checkbox" data-batch-select-task-id="${taskId}" aria-checked="${batchSelected ? "true" : "false"}" aria-label="${escapeHtml(translate("taskList.selectSession"))}">
        <span></span>
      </button>
    ` : "";
    const unreadDot = unread ? `<span class="task-unread-dot" aria-label="${escapeHtml(translate("taskList.unreadUpdate"))}"></span>` : "";
    const activeLabel = escapeHtml(translate("taskList.viewing"));
    return `
    <div class="task-card${active}${unreadClass}${statusClass}${batchClass}${batchSelectedClass}${queueClass}" role="button" tabindex="0" data-task-id="${taskId}" data-task-unread="${unread ? "true" : "false"}" data-task-swipe-enabled="${swipeEnabled ? "true" : "false"}" data-task-swipe-positive-action="${escapeHtml(swipeActions.positive || "")}" data-task-swipe-negative-action="${escapeHtml(swipeActions.negative || "")}" data-active-label="${activeLabel}" aria-keyshortcuts="${swipeKeyboardShortcuts}"${activeCurrent}${queueTaskData}>
      ${swipeActionsHtml}
      <div class="task-card-swipe-surface">
        <button type="button" class="task-touch-menu ghost-button" data-task-context-trigger aria-label="${escapeHtml(translate("mobile.taskActions"))}" aria-haspopup="menu">···</button>
        ${batchSelect}
        ${image}
        <div class="task-info">
          <div class="task-meta-row">
            ${imageRow}
            ${topTimeHtml}
          </div>
          <div class="task-title-row">
            ${unreadDot}
            <div class="task-title">${title}</div>
          </div>
          ${detailRow}
          ${groundingHtml}
        </div>
      </div>
    </div>
  `;
  }

  function taskGroupLoadMoreHtml(group: any) {
    const state = getState();
    const renderedCount = Array.isArray(group?.tasks) ? group.tasks.length : 0;
    const loadedCount = Math.max(
      renderedCount,
      Math.max(0, Number(state.taskSidebarGroupLoadedCounts?.[String(group?.key || "")] || 0)),
    );
    const totalCount = Math.max(0, Number(group?.count || 0));
    if (!group?.key || loadedCount >= totalCount) return "";
    const loading = String(state.taskSidebarGroupLoading || "") === String(group.key);
    const failed = String(state.taskSidebarGroupLoadError || "") === String(group.key);
    const groupKey = escapeHtml(group.key);
    if (loading) {
      return `
      <div
        class="task-group-load-more task-group-load-more-sentinel"
        data-auto-load-task-group="${groupKey}"
        data-load-more-task-group="${groupKey}"
        aria-busy="true"
        aria-hidden="true"
        hidden
      ></div>
    `;
    }
    if (failed) {
      return `
      <button
        class="ghost-button text-sm task-group-load-more task-group-load-more-error"
        type="button"
        data-load-more-task-group="${groupKey}"
      >${escapeHtml(translate("taskGroup.loadFailedRetry"))}</button>
    `;
    }
    return `
    <div
      class="task-group-load-more task-group-load-more-sentinel"
      data-auto-load-task-group="${groupKey}"
      data-load-more-task-group="${groupKey}"
      aria-hidden="true"
      hidden
    ></div>
  `;
  }

  function taskThumbShowsLoading(task: any) {
    const status = String(task?.status || "");
    return Boolean(task?.local_pending || ["submitting", "queued", "running"].includes(status));
  }

  function taskThumbSpinnerStyle(task: any) {
    const origin = timestampMs(task?.created_at);
    if (origin === null) return "";
    const elapsed = Math.max(0, Date.now() - origin);
    const outerDelay = -(elapsed % TASK_THUMB_OUTER_SPIN_DURATION_MS);
    const innerDelay = -((elapsed + TASK_THUMB_INNER_SPIN_OFFSET_MS) % TASK_THUMB_INNER_SPIN_DURATION_MS);
    return ` style="--task-spinner-outer-delay: ${outerDelay}ms; --task-spinner-inner-delay: ${innerDelay}ms"`;
  }

  function taskThumbHtml(task: any, className: any = "task-thumb") {
    const outputUrl = taskOutputUrls(task)[0];
    const outputThumbnailUrl = taskThumbnailUrls(task)[0];
    const inputPreviewUrl = taskInputPreviewUrls(task)[0];
    const loading = taskThumbShowsLoading(task);
    const outputImageUrl = outputThumbnailUrl || outputUrl || (!loading ? task.preview_url : "");
    const imageUrl = outputImageUrl || inputPreviewUrl || task.preview_url;
    const safeClassName = escapeHtml(className);
    const loadingSpinner = loading
      ? `<span class="task-thumb-stack-spinner" aria-hidden="true"${taskThumbSpinnerStyle(task)}></span>`
      : "";
    if (outputImageUrl && inputPreviewUrl && outputImageUrl !== inputPreviewUrl) {
      const imageToImageLabel = escapeHtml(translate("taskCard.imageToImageThumb"));
      return `
      <div class="${safeClassName} task-thumb-stack" aria-label="${imageToImageLabel}">
        <img class="task-thumb-output" src="${escapeHtml(outputImageUrl)}" alt="" loading="lazy" decoding="async" draggable="false">
        <span class="task-thumb-reference-badge" aria-hidden="true">
          <img class="task-thumb-reference" src="${escapeHtml(inputPreviewUrl)}" alt="" loading="lazy" decoding="async" draggable="false">
        </span>
        ${loadingSpinner}
      </div>
    `;
    }
    if (inputPreviewUrl && loading) {
      const imageToImageLabel = escapeHtml(translate("taskCard.imageToImageThumb"));
      return `
      <div class="${safeClassName} task-thumb-single task-thumb-loading-reference" aria-label="${imageToImageLabel}">
        <img class="task-thumb-single-image" src="${escapeHtml(inputPreviewUrl)}" alt="" loading="lazy" decoding="async" draggable="false">
        ${loadingSpinner}
      </div>
    `;
    }
    if (imageUrl) {
      const thumbnailLabel = escapeHtml(translate(inputPreviewUrl
        ? "taskCard.imageToImageThumb"
        : "taskCard.textToImageThumb"));
      return `
      <div class="${safeClassName} task-thumb-single" aria-label="${thumbnailLabel}">
        <img class="task-thumb-single-image" src="${escapeHtml(imageUrl)}" alt="" loading="lazy" decoding="async" draggable="false">
      </div>
    `;
    }
    if (taskWasCancelled(task)) {
      return `<div class="${safeClassName} failed-thumb task-cancelled-thumb" aria-label="${escapeHtml(translate("queue.runningCancelled"))}"><span>×</span></div>`;
    }
    if (task.status === "failed") {
      return `<div class="${safeClassName} failed-thumb" aria-label="${escapeHtml(translate("taskCard.failedThumb"))}"><span>!</span></div>`;
    }
    return `<div class="${safeClassName} running-thumb"><span${taskThumbSpinnerStyle(task)}></span></div>`;
  }

  function taskStatusLabelHtml(task: any) {
    const label = escapeHtml(formatTaskCardStatus(task) || translate("taskStatus.unknown"));
    const taskId = escapeHtml(task?.task_id || "");
    return `<span class="task-status-label" data-task-status-id="${taskId}">${label}</span>`;
  }

  function taskModelFamilyIconHtml(task: any) {
    const state = getState();
    const familyId = taskModelFamilyId(task, state.generationCatalog);
    const modelName = taskModelDisplayName(task, state.generationCatalog);
    return `<span class="task-model-family-icon task-model-family-icon-${familyId}" title="${escapeHtml(modelName)}">${modelFamilyBrandMarkHtml(familyId, "task-model-family-brand-mark")}</span>`;
  }

  function taskStatusAccessibleLabel(task: any) {
    const state = getState();
    return [
      formatTaskCardStatus(task) || translate("taskStatus.unknown"),
      taskModelDisplayName(task, state.generationCatalog),
      taskImageSummaryText(task),
      taskMetaDetailsText(task),
    ]
      .filter(Boolean)
      .join(" · ");
  }

  function taskMetaDetailsText(task: any) {
    const backend = taskCardProviderLabel(task);
    return [...taskCanvasSummaryParts(task), backend].filter(Boolean).join(" · ");
  }

  function taskMetaDetailsWithCompletionText(task: any) {
    const statusMeta = taskMetaDetailsText(task);
    const completion = taskCompletionTimestampText(task);
    return [statusMeta, completion?.shortText].filter(Boolean).join(" · ");
  }

  function taskCardCompletionTimeText(task: any) {
    const completion = taskCompletionTimestampText(task);
    return completion?.shortText || "";
  }

  function taskCardElapsedLineHtml(key: string, values: Record<string, any>, elapsedHtml: string) {
    const marker = "__TASK_CARD_ELAPSED_TIMER__";
    return formatTranslation(key, { ...values, elapsed: marker })
      .split(marker)
      .map((part: string) => escapeHtml(part))
      .join(elapsedHtml);
  }

  function taskCardRunningTimerHtml(task: any, taskId: string) {
    if (!["running", "cancelling"].includes(String(task?.status || ""))) return "";
    const startedAt = taskProgressStartValue(task);
    if (!startedAt) return "";
    const elapsed = elapsedTimerSpan("task-card-running", startedAt);
    return `<span class="task-card-time task-card-running-timer" data-task-running-timer-id="${taskId}">${taskCardElapsedLineHtml("preview.elapsedLine", {}, elapsed)}</span>`;
  }

  function taskCardProviderLabel(task: any) {
    const providerLabel = String(taskApiProviderLabel(task) || "").trim();
    const providerId = String(taskApiProviderId(task) || "").trim();
    const backend = String(task?.backend || task?.requested_backend || "").trim();
    const channel = taskChannelLabel(task);
    if (providerLabel && (!providerId || providerLabel !== providerId)) {
      const providerIdSuffix = providerId ? `(${providerId})` : "";
      const label = providerIdSuffix && providerLabel.endsWith(providerIdSuffix)
        ? providerLabel.slice(0, -providerIdSuffix.length).trim()
        : providerLabel;
      return [label, channel].filter(Boolean).join(" · ");
    }
    if (backend === "codex_images") return "Codex Image";
    if (backend === "codex_responses") return "Codex Responses";
    if (backend === "openai_images") return "API Image";
    if (backend === "openai_responses") return "API Responses";
    return "";
  }

  function taskCardRuntimeText(task: any) {
    return taskDurationText(task);
  }

  function taskImageBlocksHtml(task: any) {
    const states = taskImageBlockStates(task);
    const visibleStates = compressTaskImageBlockStates(states);
    const total = states.length;
    const visibleCount = Math.min(total, 4);
    const compressedClass = states.length > visibleStates.length ? " compressed" : "";
    const blocks = visibleStates.map((blockState: any) => `<span class="task-image-block ${blockState}" aria-hidden="true"></span>`).join("");
    return `<div class="task-image-progress${compressedClass}" style="--task-block-count: ${visibleCount}" aria-hidden="true">${blocks}</div>`;
  }

  function taskImageSummaryText(task: any) {
    const states = taskImageBlockStates(task);
    const counts = taskImageStatusCounts(states);
    const parts = [];
    if (counts.running) parts.push(formatTranslation("taskCard.count", { count: counts.running }));
    if (counts.queued || counts.waiting) {
      const waitingCount = counts.queued + counts.waiting;
      parts.push(formatTranslation(counts.running ? "taskCard.waitingCount" : "taskCard.count", { count: waitingCount }));
    }
    return parts.join(" · ");
  }

  function taskImageSummaryVisible(task: any) {
    void task;
    return true;
  }

  function taskMetaText(task: any) {
    const status = formatTaskStatus(task);
    const backend = taskCardProviderLabel(task);
    return [status, ...taskCanvasSummaryParts(task), backend].filter(Boolean).join(" · ");
  }

  return { expandedTaskGroupHeaderHtml, renderExpandedTaskGroupBodyShellHtml, renderExpandedTaskGroupShellHtml, activeTaskSectionHtml, activeTaskDispatchPendingHtml, activeTaskGroupHtml, expandedTaskGroupHtml, taskGroupHtml, taskGroupButtonLabel, taskQueueReorderHintVisible, taskQueueReorderHintHtml, taskCardSwipeActionLabel, taskCardSwipeActionTitle, taskCardSwipeActionHtml, taskCardSwipeActionsHtml, taskCardSwipeKeyboardShortcuts, taskCardHtml, taskGroupLoadMoreHtml, taskThumbShowsLoading, taskThumbSpinnerStyle, taskThumbHtml, taskStatusLabelHtml, taskModelFamilyIconHtml, taskStatusAccessibleLabel, taskMetaDetailsText, taskMetaDetailsWithCompletionText, taskCardCompletionTimeText, taskCardElapsedLineHtml, taskCardRunningTimerHtml, taskCardProviderLabel, taskCardRuntimeText, taskImageBlocksHtml, taskImageSummaryText, taskImageSummaryVisible, taskMetaText };
}

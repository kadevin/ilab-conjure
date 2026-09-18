import type { createHistoryFiltersController } from "./history-filters-controller";
import type { createHistoryLayoutController } from "./history-layout-controller";
import { createHistoryListView } from "./history-list-view";
import { historyTaskRowsSupportOrganization, taskMatchesHistoryOrganizationFilters, type HistoryOrganization } from "./history-organization";
import { loadHistoryAnchorPage } from "./history-position-runtime";
import { errorMessage, historyTaskArchived, historyTaskGeneratedCount, positiveInt, setText } from "./history-presentation";
import { type HistoryLoadOptions, type HistoryLoadResult } from "./history-scroll-memory";
import { type HistoryRenderPosition, type HistoryTask, type HistoryTaskPage } from "./history-types";
import { captureHistoryScrollAnchor, historyTaskCards, historyWindowEdgeCursor, restoreHistoryScrollAnchor, type HistoryWindowDirection, type HistoryWindowEdge } from "./history-window";
import { formatTranslation, translate } from "./i18n";

export function createHistoryListController(deps: {
  filters: Pick<ReturnType<typeof createHistoryFiltersController>, "organization" | "supported" | "markUnsupported" | "historyPageQueryInput" | "queryParams" | "syncHistoryViewMode" | "snapshot">;
  layout: Pick<ReturnType<typeof createHistoryLayoutController>, "layoutJustifiedHistoryGrid">;
  renderCard(task: HistoryTask): string;
  resetSelectionForLoad(): void;
  renderToolbar(): void;
  renderSelection(): void;
  enablePositionSave(): void;
  dropSelection(taskId: string): void;
  reconcileSelection(): void;
  organizationsChanged(organizations: Record<string, HistoryOrganization>, removedIds: string[]): void;
}) {
  const els = {
    resultSummary: document.querySelector<HTMLElement>("#historyResultSummary"),
    taskList: document.querySelector<HTMLElement>("#historyTaskList"),
    sentinel: document.querySelector<HTMLElement>("[data-history-load-more]"),
  };

  const view = createHistoryListView(els.taskList, els.sentinel);
  const { historyTaskCardElement, setLoadMoreState, captureHistoryScrollAnchorSkipping, renderTaskListMessage } = view;

  const historyState = {
    nextCursor: null as string | null,
    newerExhausted: true,
    loading: false,
    exhausted: false,
    loadedTaskIds: new Set<string>(),
    loadedTaskSummaries: new Map<string, HistoryTask>(),
    requestId: 0,
  };
  const MAX_MOUNTED_TASK_CARDS = 300;
  let disposed = false;
  const pendingFrames = new Map<number, () => void>();
  function requestWindowFrame(callback: () => void): number {
    const frame = window.requestAnimationFrame(() => {
      pendingFrames.delete(frame);
      callback();
    });
    pendingFrames.set(frame, callback);
    return frame;
  }
  function dispose(): void {
    disposed = true;
    historyState.requestId++;
    historyState.loading = false;
    // Finish guarded anchor promises after invalidating the request generation.
    for (const [frame, callback] of pendingFrames) {
      window.cancelAnimationFrame(frame);
      callback();
    }
    pendingFrames.clear();
  }

  function maybeLoadMoreFromScroll(): void {
    if (disposed || !els.taskList || historyState.loading) return;
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
    if (disposed) return emptyResult;
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
      deps.resetSelectionForLoad();
      if (els.taskList) els.taskList.innerHTML = "";
      deps.renderToolbar();
    }
    setLoadMoreState(translate("history.loadingMore"), { busy: true });
    try {
      const organizationFilterActive =
        deps.filters.organization().favorite ||
        deps.filters.organization().untagged ||
        deps.filters.organization().tagIds.length > 0;
      if (
        organizationFilterActive &&
        deps.filters.supported() === false
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
          deps.filters.markUnsupported();
          throw new Error(
            translate("history.backendRestartRequired"),
          );
        }
      };
      if (anchorTaskId) {
        const result = await loadHistoryAnchorPage({
          query: deps.filters.historyPageQueryInput(cursor, direction, anchorTaskId),
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
          requestFrame: requestWindowFrame,
          restore: (scrollAnchor) => {
            if (els.taskList) {
              restoreHistoryScrollAnchor(els.taskList, scrollAnchor);
            }
          },
          enableSave: () => deps.enablePositionSave(),
        });
        if (result.anchorFound !== true) return result;
        setLoadMoreState(
          historyState.exhausted ? translate("history.noMore") : "",
          { hidden: !historyState.exhausted, busy: false },
        );
        requestWindowFrame(maybeLoadMoreFromScroll);
        return result;
      }
      const data = await requestPage(
        `/api/task-history/tasks?${deps.filters.queryParams(cursor, direction)}`,
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
        if (reset) deps.enablePositionSave();
      }
      setLoadMoreState(
        historyState.exhausted ? translate("history.noMore") : "",
        { hidden: !historyState.exhausted, busy: false },
      );
      requestWindowFrame(maybeLoadMoreFromScroll);
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

  function taskWindowCursor(reset: boolean, direction: HistoryWindowDirection): string | null {
    if (reset || !els.taskList) return null;
    if (direction === "previous") return historyWindowEdgeCursor(els.taskList, "top");
    return historyState.nextCursor || historyWindowEdgeCursor(els.taskList, "bottom");
  }

  function renderTasks(tasks: HistoryTask[], { position }: { position: HistoryRenderPosition }): void {
    if (!els.taskList) return;
    deps.filters.syncHistoryViewMode();
    const anchor = position === "replace" ? null : captureHistoryScrollAnchor(els.taskList);
    if (position === "replace") els.taskList.innerHTML = "";
    const uniqueTasks = tasks
      .filter((task) => {
        if (historyState.loadedTaskIds.has(task.task_id)) return false;
        historyState.loadedTaskIds.add(task.task_id);
        historyState.loadedTaskSummaries.set(task.task_id, task);
        return true;
      });
    const html = uniqueTasks.map(deps.renderCard).join("");
    if (html) {
      els.taskList.querySelector(".history-empty, .history-error")?.remove();
      if (position === "prepend") {
        els.taskList.insertAdjacentHTML("afterbegin", html);
      } else {
        els.taskList.insertAdjacentHTML("beforeend", html);
      }
    }
    trimMountedTaskCards(position === "prepend" ? "bottom" : "top");
    deps.layout.layoutJustifiedHistoryGrid();
    restoreHistoryScrollAnchor(els.taskList, anchor);
    if (!els.taskList.querySelector(".history-task-card")) {
      renderTaskListMessage("history-empty", translate("history.noMatches"));
    }
    setText(els.resultSummary, formatTranslation("history.loadedCount", { count: historyState.loadedTaskIds.size }));
    deps.renderSelection();
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
    deps.layout.layoutJustifiedHistoryGrid();
    restoreHistoryScrollAnchor(els.taskList, anchor);
    deps.renderSelection();
    requestWindowFrame(maybeLoadMoreFromScroll);
  }

  function removeHistoryTaskIdsFromWindow(taskIds: string[]): void {
    const ids = taskIds.filter(Boolean);
    if (!ids.length) return;
    refreshHistoryWindowAfterMutation(() => {
      ids.forEach((taskId) => {
        historyState.loadedTaskIds.delete(taskId);
        historyState.loadedTaskSummaries.delete(taskId);
        deps.dropSelection(taskId);

        historyTaskCardElement(taskId)?.remove();
      });
    }, { removedTaskIds: ids });
    deps.reconcileSelection();
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
            deps.filters.organization(),
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
          deps.dropSelection(taskId);
          historyTaskCardElement(taskId)?.remove();
          continue;
        }
        const card = historyTaskCardElement(taskId);
        if (!card) continue;
        view.replaceCard(card, deps.renderCard(task));
      }
    }, { removedTaskIds });
    deps.organizationsChanged(organizations, removedTaskIds);
  }

  function historyTaskMatchesCurrentArchiveFilter(task: any): boolean {
    if (deps.filters.snapshot().archived === "true") return historyTaskArchived(task);
    if (deps.filters.snapshot().archived === "false") return !historyTaskArchived(task);
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
      view.replaceCard(card, deps.renderCard(summary));
    });
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

  function historyTaskSummary(taskId: string): HistoryTask | null {
    const task = historyState.loadedTaskSummaries.get(taskId);
    return task ? { ...task, tags: (task.tags || []).map(tag => ({ ...tag })) } : null;
  }
  return {
    historyTaskCardElement,
    setLoadMoreState,
    maybeLoadMoreFromScroll,
    loadTasks,
    removeHistoryTaskIdsFromWindow,
    applyHistoryOrganizations,
    upsertHistoryTaskSummaryCard,
    historyTaskSummary,
    summaries: () => [...historyState.loadedTaskSummaries.values()].map(task => ({ ...task, tags: (task.tags || []).map(tag => ({ ...tag })) })),
    status: () => ({ loading: historyState.loading, exhausted: historyState.exhausted, newerExhausted: historyState.newerExhausted }),
    dispose,
  };
}

import { groundingAttributionKey } from "./grounding-attribution";
import { sidebarTaskDateBucket } from "./history-task-reveal-model";
import { translate } from "./i18n";
import type { WebUIState } from "./state";
import type { QueueTaskIdSections } from "./task-list-types";

export interface TaskListModelDependencies {
  getState: () => Readonly<Pick<WebUIState, "activeTaskGroupCollapsed" | "batchMode" | "batchSelectedTaskIds" | "expandedTaskGroupKey" | "historyTaskReveal" | "queue" | "selectedTaskId" | "taskSearchHistoryResultIds" | "taskSearchHistoryResultQuery" | "taskSidebarGroupCounts" | "tasks">>;
  taskArchived: (task: any) => boolean;
  taskBackendLabel: (task: any) => string;
  taskFilterValues: () => { status: string; ratio: string; orientation: string; promptFidelity: string; resolution: string };
  taskOrientation: (task: any) => string;
  taskOutputUrls: (task: any) => string[];
  taskPromptFidelity: (task: any) => string;
  taskRatio: (task: any) => string;
  taskResolution: (task: any) => string;
  timestampMs: (value: any) => number | null;
}

export function createTaskListModel(dependencies: TaskListModelDependencies) {
  const { getState, taskArchived, taskBackendLabel, taskFilterValues, taskOrientation, taskOutputUrls, taskPromptFidelity, taskRatio, taskResolution, timestampMs } = dependencies;
  let queueTaskIdsCacheKey = "";
  let queueTaskIdsCache: QueueTaskIdSections | null = null;

  function taskAnchorLayout(groups: any[], expandedKey: string | null, query: string) {
    if (query) {
      return {
        top: [],
        bottom: [],
        expandedGroup: groups[0] || null,
        expandedKey: groups[0]?.key || expandedKey || null,
        queryMode: true,
      };
    }
    const index = groups.findIndex((group: any) => String(group.key) === String(expandedKey));
    if (index < 0) {
      return {
        top: groups,
        bottom: [],
        expandedGroup: null,
        expandedKey: null,
        queryMode: false,
      };
    }
    return {
      top: index > 0 ? groups.slice(0, index) : [],
      bottom: groups.slice(index + 1),
      expandedGroup: groups[index] || null,
      expandedKey,
      queryMode: false,
    };
  }

  function taskSearchHistoryResultMatches(taskId: string, query: string) {
    const state = getState();
    if (!taskId || !query) return false;
    if (String(state.taskSearchHistoryResultQuery || "") !== query) return false;
    return (state.taskSearchHistoryResultIds || []).some((id: any) => String(id) === taskId);
  }

  function taskMatchesSearch(task: any, query: any) {
    const normalizedQuery = String(query || "").trim().toLowerCase();
    const taskId = String(task?.task_id || "");
    if (taskSearchHistoryResultMatches(taskId, normalizedQuery)) {
      return true;
    }
    const text = `${task.task_id || ""} ${task.prompt || ""} ${task.status || ""} ${task.mode || ""} ${taskBackendLabel(task)}`.toLowerCase();
    return text.includes(normalizedQuery);
  }

  function taskMatchesFilters(task: any, filters: any) {
    if (filters.status && String(task?.status || "") !== filters.status) return false;
    if (filters.ratio && taskRatio(task) !== filters.ratio) return false;
    if (filters.orientation && taskOrientation(task) !== filters.orientation) return false;
    if (filters.promptFidelity && taskPromptFidelity(task) !== filters.promptFidelity) return false;
    if (filters.resolution && taskResolution(task) !== filters.resolution) return false;
    return true;
  }

  function activeTaskSections(tasks: any[]) {
    const queueIds = queueTaskIdsBySection();
    const running: any[] = [];
    const waiting: any[] = [];
    tasks.forEach((task: any) => {
      if (!isAlwaysVisibleTask(task)) return;
      const taskId = String(task?.task_id || "");
      const status = String(task?.status || "");
      if (queueIds.running.has(taskId) || status === "running" || status === "cancelling") {
        running.push(task);
      } else if (queueIds.waiting.has(taskId) || task?.local_pending || ["submitting", "queued"].includes(status)) {
        waiting.push(task);
      }
    });
    return { running, waiting };
  }

  function activeTaskGroup(tasks: any[], query: any = "") {
    if (query) return null;
    const activeTasks = activeTasksForGroup(tasks);
    if (!activeTasks.length) return null;
    return {
      key: "active",
      label: translate("sidebar.activeTasks"),
      tasks: activeTasks,
      collapsible: false,
      defaultCollapsed: false,
    };
  }

  function taskQueueSection(task: any, queueIds = queueTaskIdsBySection()) {
    const taskId = String(task?.task_id || "");
    if (!taskId) return "";
    if (queueIds.running.has(taskId)) return "running";
    if (queueIds.waiting.has(taskId)) return "waiting";
    return "";
  }

  function waitingQueueIndex(taskId: any, queueIds = queueTaskIdsBySection()) {
    const normalizedTaskId = String(taskId || "");
    return queueIds.waiting.get(normalizedTaskId) ?? -1;
  }

  function taskHasUnreadUpdate(task: any) {
    const state = getState();
    if (!task || task.local_pending) return false;
    if (String(task.task_id) === String(state.selectedTaskId)) return false;
    if (!task.viewed_at) return false;
    if (!taskHasViewableUpdate(task)) return false;
    const viewedAt = timestampMs(task.viewed_at);
    const updatedAt = timestampMs(task.updated_at || task.completed_at || task.started_at || task.created_at);
    return viewedAt !== null && updatedAt !== null && updatedAt > viewedAt;
  }

  function taskHasViewableUpdate(task: any) {
    const status = String(task?.status || "");
    return ["completed", "failed", "partial_failed"].includes(status) || taskOutputUrls(task).length > 0;
  }

  function taskHistoryGroups(tasks: any, query: any) {
    const state = getState();
    if (query) {
      return [{
        key: "search",
        label: translate("taskGroup.searchResults"),
        tasks,
        collapsible: false,
        defaultCollapsed: false,
      }];
    }

    const groups: any[] = [];
    const assignedTaskIds = new Set();
    const addGroup = (key: any, label: any, groupTasks: any, options: any = {}) => {
      const count = Math.max(groupTasks.length, Number(options.count || 0));
      if (!count) return;
      groups.push({
        key,
        label,
        tasks: groupTasks,
        count,
        collapsible: Boolean(options.collapsible),
        defaultCollapsed: Boolean(options.defaultCollapsed),
      });
      groupTasks.forEach((task: any) => assignedTaskIds.add(String(task.task_id)));
    };
    const filters = taskFilterValues();
    const useServerCounts = Object.values(filters).every((value) => !String(value || ""));
    const serverCount = (key: string) => useServerCounts
      ? Math.max(0, Number(state.taskSidebarGroupCounts?.[key] || 0))
      : 0;
    const historicalTasks = tasks
      .filter((task: any) => !isAlwaysVisibleTask(task))
      .slice()
      .sort((left: any, right: any) => (
        taskHistoryActivityTimestamp(right) - taskHistoryActivityTimestamp(left)
        || String(right?.task_id || "").localeCompare(String(left?.task_id || ""))
      ));
    const unassignedTasks = () => historicalTasks.filter((task: any) => !assignedTaskIds.has(String(task.task_id)));

    const reveal = state.historyTaskReveal;
    const transientTaskId = reveal?.ready
      && reveal?.kind === "transient"
      && String(reveal?.taskId || "") === String(state.selectedTaskId || "")
      ? String(reveal.taskId)
      : "";
    if (transientTaskId) {
      addGroup(
        "current",
        translate("taskGroup.current"),
        unassignedTasks().filter((task: any) => String(task?.task_id || "") === transientTaskId),
        { collapsible: true, defaultCollapsed: false },
      );
    }

    addGroup(
      "today",
      translate("taskGroup.today"),
      unassignedTasks().filter((task: any) => taskDateBucket(task) === "today"),
      { collapsible: true, defaultCollapsed: false, count: serverCount("today") },
    );

    [
      ["yesterday", translate("taskGroup.yesterday")],
      ["last7", translate("taskGroup.last7")],
    ].forEach(([key, label]: any) => {
      addGroup(
        key,
        label,
        unassignedTasks().filter((task: any) => taskDateBucket(task) === key),
        { collapsible: true, defaultCollapsed: true, count: serverCount(String(key)) },
      );
    });

    return groups;
  }

  function isAlwaysVisibleTask(task: any) {
    const status = String(task?.status || "");
    if (["failed", "completed", "cancelled"].includes(status)) return false;
    return Boolean(task?.local_pending || ["submitting", "queued", "running", "cancelling"].includes(status));
  }

  function queueTaskIdsBySection() {
    const state = getState();
    const runningIds = (state.queue.running || []).map((task: any) => String(task.task_id || ""));
    const waitingIds = (state.queue.waiting || []).map((task: any) => String(task.task_id || ""));
    const cacheKey = `${runningIds.join("|")}::${waitingIds.join("|")}`;
    if (queueTaskIdsCache && queueTaskIdsCacheKey === cacheKey) return queueTaskIdsCache;
    queueTaskIdsCacheKey = cacheKey;
    queueTaskIdsCache = {
      running: new Map((state.queue.running || []).map((task: any, index: number) => [String(task.task_id), index])),
      waiting: new Map((state.queue.waiting || []).map((task: any, index: number) => [String(task.task_id), index])),
    };
    return queueTaskIdsCache;
  }

  function activeTaskOrderIndex(task: any, sectionIds = queueTaskIdsBySection()) {
    const taskId = String(task?.task_id || "");
    if (sectionIds.running.has(taskId)) return sectionIds.running.get(taskId) || 0;
    if (String(task?.status || "") === "running") return 1000;
    if (sectionIds.waiting.has(taskId)) return 2000 + (sectionIds.waiting.get(taskId) || 0);
    if (task?.local_pending || String(task?.status || "") === "submitting") return 3000;
    if (String(task?.status || "") === "queued") return 4000;
    return 5000;
  }

  function activeTasksForGroup(tasks: any[]) {
    const sectionIds = queueTaskIdsBySection();
    return tasks
      .filter((task: any) => isAlwaysVisibleTask(task))
      .slice()
      .sort((left: any, right: any) => activeTaskOrderIndex(left, sectionIds) - activeTaskOrderIndex(right, sectionIds));
  }

  function taskHistoryActivityTimestamp(task: any) {
    const timestamp = timestampMs(task?.terminal_at || task?.completed_at || task?.created_at);
    return timestamp === null ? Number.NEGATIVE_INFINITY : timestamp;
  }

  function taskDateBucket(task: any) {
    return sidebarTaskDateBucket(task);
  }

  function taskGroupCount(group: any) {
    const loadedCount = Array.isArray(group?.tasks) ? group.tasks.length : 0;
    return Math.max(loadedCount, Math.max(0, Number(group?.count || 0)));
  }

  function taskListRenderKey(tasks: any, query: any, layout: any = {}, filters: any = {}, activeGroup: any = null) {
    const state = getState();
    return JSON.stringify({
      query,
      filters,
      activeQueue: activeQueueTaskListRenderKey(),
      activeGroup: activeGroup
        ? [activeGroup.key, activeGroup.label, activeGroup.tasks.length]
        : null,
      activeTaskGroupCollapsed: Boolean(state.activeTaskGroupCollapsed),
      batchMode: state.batchMode,
      batchSelectedTaskIds: state.batchSelectedTaskIds.map(String).sort(),
      archivedTaskIds: state.tasks.filter(taskArchived).map((task: any) => String(task.task_id)).sort(),
      expandedTaskGroupKey: state.expandedTaskGroupKey,
      historyTaskReveal: state.historyTaskReveal?.ready
        ? [state.historyTaskReveal.kind, state.historyTaskReveal.groupKey, state.historyTaskReveal.taskId]
        : null,
      queryMode: Boolean(layout.queryMode),
      expandedGroup: layout.expandedGroup
        ? [layout.expandedGroup.key, layout.expandedGroup.label, taskGroupCount(layout.expandedGroup)]
        : null,
      anchorGroups: [
        (layout.top || []).map((group: any) => [group.key, taskGroupCount(group)]),
        (layout.bottom || []).map((group: any) => [group.key, taskGroupCount(group)]),
      ],
      tasks: tasks.map((task: any) => [
        task.task_id,
        task.status,
        task.updated_at,
        task.completed_at,
        task.terminal_at,
        task.started_at,
        task.prompt,
        task.mode,
        task.backend,
        task.requested_backend,
        task.api_provider_id,
        task.api_provider_name,
        task.params?.api_provider_id,
        task.params?.api_provider_name,
        task.request?.webui_api_provider_id,
        task.request?.webui_api_provider_name,
        task.params?.size,
        task.output_url,
        Array.isArray(task.output_urls) ? task.output_urls.join("|") : "",
        Array.isArray(task.input_thumbnail_urls) ? task.input_thumbnail_urls.join("|") : "",
        Array.isArray(task.thumbnail_urls) ? task.thumbnail_urls.join("|") : "",
        task.preview_url,
        task.last_error || task.error || "",
        task.attempts,
        task.max_attempts,
        Array.isArray(task.retrying_failed_slots) ? task.retrying_failed_slots.join(",") : "",
        task.generated_count,
        task.failed_count,
        task.total_count,
        Array.isArray(task.input_sources)
          ? task.input_sources.map((item: any) => [item?.kind, item?.image_url, item?.thumbnail_url].join(":")).join("|")
          : "",
        Array.isArray(task.outputs)
          ? task.outputs.map((item: any) => [item?.index, item?.status, item?.url, item?.thumbnail_url, item?.error].join(":")).join("|")
          : "",
        groundingAttributionKey(task),
      ]),
    });
  }

  function activeQueueTaskListRenderKey() {
    const state = getState();
    return {
      running: (state.queue.running || []).map((task: any) => String(task.task_id || "")),
      waiting: (state.queue.waiting || []).map((task: any) => String(task.task_id || "")),
    };
  }

  return { taskAnchorLayout, taskSearchHistoryResultMatches, taskMatchesSearch, taskMatchesFilters, activeTaskSections, activeTaskGroup, taskQueueSection, waitingQueueIndex, taskHasUnreadUpdate, taskHasViewableUpdate, taskHistoryGroups, isAlwaysVisibleTask, queueTaskIdsBySection, activeTaskOrderIndex, activeTasksForGroup, taskHistoryActivityTimestamp, taskDateBucket, taskGroupCount, taskListRenderKey, activeQueueTaskListRenderKey };
}

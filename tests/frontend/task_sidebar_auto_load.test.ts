import assert from "node:assert/strict";
import test from "node:test";

class FakeEventTarget {
  readonly listeners = new Map<string, Array<(event: any) => void>>();
  isConnected = true;
  scrollHeight = 1000;
  scrollTop = 0;
  clientHeight = 300;
  sentinel: any = null;
  expandedBody: any = null;
  innerHTMLWriteCount = 0;
  private html = "";

  get innerHTML(): string {
    return this.html;
  }

  set innerHTML(value: string) {
    this.html = value;
    this.innerHTMLWriteCount += 1;
    for (const card of this.expandedBody?.cards || []) card.isConnected = false;
  }

  addEventListener(type: string, listener: (event: any) => void): void {
    const listeners = this.listeners.get(type) || [];
    listeners.push(listener);
    this.listeners.set(type, listeners);
  }

  dispatch(type: string, event: any = {}): void {
    for (const listener of this.listeners.get(type) || []) listener(event);
  }

  querySelector(selector: string): any {
    if (selector.includes("data-expanded-task-group-items-key")) {
      return this.expandedBody;
    }
    return selector.includes("load-more-task-group") ? this.sentinel : null;
  }

  querySelectorAll(): any[] {
    return [];
  }

  getBoundingClientRect(): any {
    return { top: 0, bottom: this.clientHeight };
  }

  contains(): boolean {
    return true;
  }
}

const frameQueue: Array<() => void> = [];
const sidebar = new FakeEventTarget();
const taskList = new FakeEventTarget();
const sentinel = {
  dataset: {
    loadMoreTaskGroup: "today",
  },
};
taskList.sentinel = sentinel;

const loadCalls: any[][] = [];
const renderCalls: any[][] = [];
const state: any = {
  tasks: [],
  queue: { waiting: [], running: [], summary: {} },
  taskSidebarGroupCounts: { today: 100 },
  taskSidebarGroupLoadedCounts: { today: 50 },
  taskSidebarGroupLoading: null,
  taskSidebarGroupLoadError: null,
  tasksRenderKey: null,
  suppressTaskClickAfterDrag: false,
};
const bridge: any = {
  state,
  els: {
    taskHistoryShell: null,
    sidebarContent: sidebar,
    taskList,
  },
  constants: { defaultDocumentTitle: "iLab CONJURE" },
  boot() {},
  methods: {
    loadMoreSidebarTaskGroup(...args: any[]) {
      loadCalls.push(args);
      state.taskSidebarGroupLoading = String(args[0] || "");
      return Promise.resolve(true);
    },
    handleTaskListPointerDown() {},
    renderTasks(...args: any[]) {
      renderCalls.push(args);
    },
    cleanupSessionSelections() {},
    renderArchiveButton() {},
    renderArchiveModal() {},
    renderPreview() {},
    revokeTaskUploadPreviewUrls() {},
  },
};

(globalThis as any).window = {
  __codexImageWebUI: bridge,
  CSS: {
    escape(value: unknown) {
      return String(value);
    },
  },
  requestAnimationFrame(callback: () => void) {
    frameQueue.push(callback);
    return frameQueue.length;
  },
  clearTimeout() {},
};
(globalThis as any).requestAnimationFrame = (callback: () => void) => {
  frameQueue.push(callback);
  return frameQueue.length;
};
(globalThis as any).document = {
  addEventListener() {},
};

function flushAnimationFrames(): void {
  while (frameQueue.length) frameQueue.shift()?.();
}

const { initTaskListControlsFeature } = await import(
  "../../codex_image/webui/frontend/src/task-list-controls"
);
initTaskListControlsFeature();
bridge.methods.bindTaskListEvents();

test("sidebar scrolling loads the next task page at the 320px boundary", () => {
  loadCalls.length = 0;
  state.taskSidebarGroupLoading = null;
  sidebar.scrollTop = 379;

  sidebar.dispatch("scroll");
  flushAnimationFrames();
  assert.equal(loadCalls.length, 0);

  sidebar.scrollTop = 380;
  sidebar.dispatch("scroll");
  flushAnimationFrames();
  assert.equal(loadCalls.length, 1);
  assert.equal(loadCalls[0]?.[0], "today");
});

test("further scrolling does not repeat an automatic load that already failed", () => {
  loadCalls.length = 0;
  state.taskSidebarGroupLoading = null;
  state.taskSidebarGroupLoadError = "today";
  sidebar.scrollTop = 380;

  sidebar.dispatch("scroll");
  flushAnimationFrames();

  assert.equal(loadCalls.length, 0);
});

test("clicking the failed-page fallback explicitly requests a manual retry", () => {
  loadCalls.length = 0;
  state.taskSidebarGroupLoading = null;
  state.taskSidebarGroupLoadError = "today";
  let stopped = false;

  bridge.methods.handleTaskListClick({
    target: {
      closest(selector: string) {
        return selector === "[data-load-more-task-group]" ? sentinel : null;
      },
    },
    stopPropagation() {
      stopped = true;
    },
  });

  assert.equal(stopped, true);
  assert.deepEqual(loadCalls, [["today", { manual: true }]]);
});

test("a failed automatic page load pauses until an explicit manual retry", async () => {
  loadCalls.length = 0;
  renderCalls.length = 0;
  state.taskSidebarGroupLoading = null;
  state.taskSidebarGroupLoadError = null;
  state.taskSidebarGroupLoadedCounts.today = 50;
  (globalThis as any).fetch = async () => new Response(
    JSON.stringify({ detail: "temporary failure" }),
    {
      status: 503,
      headers: { "content-type": "application/json" },
    },
  );

  const { initTaskFeature } = await import(
    "../../codex_image/webui/frontend/src/tasks"
  );
  initTaskFeature();

  let thrown: unknown;
  let result: unknown;
  try {
    result = await bridge.methods.loadMoreSidebarTaskGroup("today");
  } catch (error) {
    thrown = error;
  }

  assert.equal(thrown, undefined);
  assert.equal(result, false);
  assert.equal(state.taskSidebarGroupLoadError, "today");
  assert.equal(state.taskSidebarGroupLoading, null);

  let retryRequests = 0;
  (globalThis as any).fetch = async () => {
    retryRequests += 1;
    return new Response(JSON.stringify({
      count: 50,
      next_offset: 50,
      tasks: [],
    }), {
      status: 200,
      headers: { "content-type": "application/json" },
    });
  };

  assert.equal(await bridge.methods.loadMoreSidebarTaskGroup("today"), false);
  assert.equal(retryRequests, 0);
  assert.equal(
    await bridge.methods.loadMoreSidebarTaskGroup("today", { manual: true }),
    true,
  );
  assert.equal(retryRequests, 1);
  assert.equal(state.taskSidebarGroupLoadError, null);
});

test("loading another page leaves the rendered task cards untouched until the response arrives", async () => {
  renderCalls.length = 0;
  state.tasks = [{ task_id: "task-1", status: "completed" }];
  state.taskSidebarGroupLoading = null;
  state.taskSidebarGroupLoadError = null;
  state.taskSidebarGroupLoadedCounts.today = 1;

  let resolveFetch: ((response: Response) => void) | undefined;
  (globalThis as any).fetch = () => new Promise<Response>((resolve) => {
    resolveFetch = resolve;
  });

  const pendingLoad = bridge.methods.loadMoreSidebarTaskGroup("today");
  await Promise.resolve();

  assert.equal(state.taskSidebarGroupLoading, "today");
  assert.equal(renderCalls.length, 0);

  resolveFetch?.(new Response(JSON.stringify({
    count: 2,
    next_offset: 2,
    tasks: [{ task_id: "task-2", status: "completed" }],
  }), {
    status: 200,
    headers: { "content-type": "application/json" },
  }));

  assert.equal(await pendingLoad, true);
  assert.deepEqual(renderCalls, [[{
    preserveScroll: true,
    appendGroupKey: "today",
  }]]);
});

test("a successful sidebar snapshot clears a previous pagination failure", async () => {
  state.taskSidebarGroupLoadError = "today";
  state.tasksRequestSeq = 1;

  await bridge.methods.applyTasksSnapshot([], {
    requestSeq: 1,
    taskGroups: [{ key: "today", count: 100, tasks: [] }],
  });

  assert.equal(state.taskSidebarGroupLoadError, null);
});

test("rendering a completed task-group page installs a sentinel and checks for the next page", async () => {
  state.taskSidebarGroupLoading = null;
  state.taskSidebarGroupLoadError = null;
  sidebar.scrollTop = 380;
  loadCalls.length = 0;
  bridge.methods.loadMoreSidebarTaskGroup = (...args: any[]) => {
    loadCalls.push(args);
    state.taskSidebarGroupLoading = String(args[0] || "");
    return Promise.resolve(true);
  };
  bridge.methods.escapeHtml = (value: unknown) => String(value);
  bridge.methods.scheduleLatestTaskNavigationRefresh = () => undefined;

  const insertedHtml: string[] = [];
  const body = {
    dataset: {} as Record<string, string>,
    style: {} as Record<string, string>,
    insertAdjacentHTML(_position: string, html: string) {
      insertedHtml.push(html);
    },
  };
  taskList.expandedBody = body;

  const { initTaskListRenderFeature } = await import(
    "../../codex_image/webui/frontend/src/task-list-render"
  );
  initTaskListRenderFeature();
  bridge.methods.scheduleExpandedTaskGroupItemsRender({
    key: "today",
    count: 100,
    tasks: [],
  });
  flushAnimationFrames();

  assert.match(insertedHtml.join(""), /data-auto-load-task-group="today"/);
  assert.match(insertedHtml.join(""), /\shidden/);
  assert.doesNotMatch(insertedHtml.join(""), /<button/);
  assert.equal(body.dataset.renderComplete, "true");
  assert.equal(loadCalls.length, 1);
  assert.equal(loadCalls[0]?.[0], "today");
});

test("rendering a loaded page appends only the new cards and preserves existing card nodes", () => {
  const now = Date.now();
  const existingCard = {
    dataset: { taskId: "task-1" },
    isConnected: true,
  };
  let footerRemoved = false;
  const footer = {
    remove() {
      footerRemoved = true;
    },
  };
  const insertedHtml: string[] = [];
  const body = {
    cards: [existingCard],
    dataset: { renderComplete: "true" } as Record<string, string>,
    style: { maxHeight: "none", opacity: "1" } as Record<string, string>,
    scrollHeight: 1000,
    querySelectorAll(selector: string) {
      if (selector === ".task-card[data-task-id]") return this.cards;
      if (selector === "[data-load-more-task-group]") return [footer];
      return [];
    },
    insertAdjacentHTML(_position: string, html: string) {
      insertedHtml.push(html);
    },
  };
  taskList.expandedBody = body;
  taskList.innerHTMLWriteCount = 0;
  state.tasks = [
    {
      task_id: "task-1",
      status: "completed",
      prompt: "first",
      terminal_at: new Date(now).toISOString(),
    },
    {
      task_id: "task-2",
      status: "completed",
      prompt: "second",
      terminal_at: new Date(now - 1000).toISOString(),
    },
  ];
  Object.assign(state, {
    selectedTaskId: null,
    batchMode: false,
    batchSelectedTaskIds: [],
    batchSelectionIncludesUnloaded: false,
    expandedTaskGroupKey: "today",
    historyTaskReveal: null,
    generationCatalog: null,
    taskSidebarGroupCounts: { today: 3 },
    taskSidebarGroupLoadedCounts: { today: 2 },
    taskSidebarGroupLoading: null,
    taskSidebarGroupLoadError: null,
    tasksRenderKey: "before-page-load",
  });
  Object.assign(bridge.methods, {
    captureTaskHistoryLayout() {},
    compressTaskImageBlockStates(states: any[]) { return states; },
    consumeLatestTaskNavigationScrollAnchor(anchor: any) { return anchor; },
    elapsedTimerSpan() { return ""; },
    ensureExpandedTaskGroupKey(groups: any[]) { return groups[0] || null; },
    formatTaskCardStatus() { return "完成"; },
    isTaskArchived() { return false; },
    rememberLatestTaskNavigationBeforeRender() {},
    renderBatchToolbar() {},
    renderTaskHistoryAnchors() {},
    taskApiProviderId() { return ""; },
    taskApiProviderLabel() { return ""; },
    taskArchived() { return false; },
    taskBackendLabel() { return ""; },
    taskCardRetryStateText() { return ""; },
    taskCompletionTimestampText() { return null; },
    taskCompletionTimestampTitle() { return ""; },
    taskDurationText() { return ""; },
    taskImageBlockStates() { return []; },
    taskImageStatusCounts() { return { running: 0, queued: 0, waiting: 0 }; },
    taskInputPreviewUrls() { return []; },
    taskOutputUrls() { return []; },
    taskProgressStartValue() { return null; },
    taskRetryStateText() { return ""; },
    taskRuntimeText() { return ""; },
    taskThumbnailUrls() { return []; },
    timestampMs(value: unknown) {
      const timestamp = Date.parse(String(value || ""));
      return Number.isFinite(timestamp) ? timestamp : null;
    },
    updateDocumentTitle() {},
    updateTaskElapsedDisplays() {},
  });

  bridge.methods.renderTasks({ preserveScroll: true, appendGroupKey: "today" });
  flushAnimationFrames();

  assert.equal(taskList.innerHTMLWriteCount, 0);
  assert.equal(existingCard.isConnected, true);
  assert.equal(footerRemoved, true);
  assert.match(insertedHtml.join(""), /data-task-id="task-2"/);
  assert.doesNotMatch(insertedHtml.join(""), /data-task-id="task-1"/);
});

test("task-group pagination keeps loading visually inert and renders a retry button only after failure", () => {
  const renderPagination = (loading: string | null, error: string | null) => {
    state.taskSidebarGroupLoading = loading;
    state.taskSidebarGroupLoadError = error;
    const insertedHtml: string[] = [];
    taskList.expandedBody = {
      dataset: {} as Record<string, string>,
      style: {} as Record<string, string>,
      insertAdjacentHTML(_position: string, html: string) {
        insertedHtml.push(html);
      },
    };
    bridge.methods.scheduleExpandedTaskGroupItemsRender({
      key: "today",
      count: 100,
      tasks: [],
    });
    flushAnimationFrames();
    return insertedHtml.join("");
  };

  const loadingHtml = renderPagination("today", null);
  assert.match(loadingHtml, /data-auto-load-task-group="today"/);
  assert.match(loadingHtml, /aria-busy="true"/);
  assert.match(loadingHtml, /\shidden/);
  assert.doesNotMatch(loadingHtml, /role="status"/);
  assert.doesNotMatch(loadingHtml, /载入中/);
  assert.doesNotMatch(loadingHtml, /<button/);

  const failedHtml = renderPagination(null, "today");
  assert.match(failedHtml, /<button/);
  assert.match(failedHtml, />载入失败，点此重试<\/button>/);
  assert.match(failedHtml, /data-load-more-task-group="today"/);
});

test("a fully loaded group stays terminal when filters hide most loaded tasks", () => {
  state.taskSidebarGroupLoading = null;
  state.taskSidebarGroupLoadError = null;
  state.taskSidebarGroupLoadedCounts.today = 100;
  const insertedHtml: string[] = [];
  taskList.expandedBody = {
    dataset: {} as Record<string, string>,
    style: {} as Record<string, string>,
    insertAdjacentHTML(_position: string, html: string) {
      insertedHtml.push(html);
    },
  };

  bridge.methods.scheduleExpandedTaskGroupItemsRender({
    key: "today",
    count: 100,
    tasks: [],
  });
  flushAnimationFrames();

  assert.equal(insertedHtml.join(""), "");
});

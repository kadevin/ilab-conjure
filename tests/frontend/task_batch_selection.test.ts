import assert from "node:assert/strict";
import test from "node:test";

import { waitingBatchTaskIds } from "../../codex_image/webui/frontend/src/task-batch-selection-model";

test("waiting batch selection includes only valid waiting queue tasks", () => {
  assert.deepEqual(
    waitingBatchTaskIds({
      running: [
        { task_id: "running-1" },
      ],
      waiting: [
        { task_id: "waiting-1" },
        { task_id: "waiting-2" },
        { task_id: "waiting-1" },
        { task_id: "" },
        null,
      ],
    }),
    ["waiting-1", "waiting-2"],
  );
});

test("waiting batch selection is empty when no waiting tasks exist", () => {
  assert.deepEqual(waitingBatchTaskIds({ running: [{ task_id: "running-1" }] }), []);
  assert.deepEqual(waitingBatchTaskIds(null), []);
});

test("batch controls toggle complete scopes and discard stale selection responses", async (t) => {
  const previousWindow = (globalThis as any).window;
  const previousDocument = (globalThis as any).document;
  const previousFetch = globalThis.fetch;
  const element = () => ({
    textContent: "", disabled: false, hidden: false, attributes: {} as Record<string, string>,
    classList: { toggle() {}, remove() {} },
    setAttribute(key: string, value: string) { this.attributes[key] = value; },
    focus() {}, querySelector: () => null, querySelectorAll: () => [],
  });
  const els: any = Object.fromEntries([
    "batchToolbar", "batchSelectedCount", "batchManageButton", "batchSelectGroupButton",
    "batchSelectWaitingButton", "batchArchiveButton", "batchDeleteButton", "batchCancelSelectedButton",
    "taskList", "taskHistoryShell",
  ].map((key) => [key, element()]));
  const state: any = { queue: { running: [], waiting: [] } };
  let filters: any = {};
  let calls = 0;
  let errors: string[] = [];
  const methods: any = {
    renderTasks() {}, isTaskArchived: () => false,
    taskFilterValues: () => filters,
    filteredVisibleTasks: () => state.tasks,
    taskHistoryGroups: () => [{ key: "today", tasks: state.tasks.filter((task: any) => task.group === "today") }],
    setStatus: (message: string) => errors.push(message),
  };
  (globalThis as any).window = { __codexImageWebUI: { els, state, methods }, removeEventListener() {} };
  (globalThis as any).document = { addEventListener() {}, activeElement: null };
  const { initTaskBatchControlsFeature } = await import("../../codex_image/webui/frontend/src/task-batch-controls");
  initTaskBatchControlsFeature();
  const reset = () => {
    methods.toggleBatchMode(false);
    Object.assign(state, {
      batchMode: true, batchSelectedTaskIds: ["other"], expandedTaskGroupKey: "today", taskSearchQuery: "",
      queue: { running: [], waiting: [] },
      tasks: [{ task_id: "one", group: "today" }, { task_id: "two", group: "today" }, { task_id: "other" }],
      taskSidebarGroupCounts: { today: 3 }, taskSidebarGroupLoadedCounts: { today: 2 },
    });
    filters = {}; calls = 0; errors = [];
    globalThis.fetch = (async () => {
      calls += 1;
      return { ok: true, json: async () => ({ task_ids: ["one", "two", "unloaded"] }) };
    }) as any;
    methods.renderBatchToolbar();
  };
  try {
    await t.test("deselect includes unloaded IDs, keeps other selections and stays in batch mode", async () => {
      reset();
      await methods.selectAllMatchingTasksInExpandedGroup();
      assert.deepEqual(state.batchSelectedTaskIds, ["other", "one", "two", "unloaded"]);
      assert.equal(state.batchSelectionIncludesUnloaded, true);
      assert.equal(els.batchSelectGroupButton.attributes["data-i18n"], "batch.deselectCurrentGroup");
      assert.equal(els.batchSelectGroupButton.attributes["aria-pressed"], "true");
      await methods.selectAllMatchingTasksInExpandedGroup();
      assert.deepEqual(state.batchSelectedTaskIds, ["other"]);
      assert.equal(state.batchMode, true);
      assert.equal(state.batchSelectionIncludesUnloaded, false);
      assert.equal(calls, 1, "undoing all selection is immediate and needs no second request");
      assert.equal(els.batchSelectGroupButton.attributes["data-i18n"], "batch.selectCurrentGroup");
    });
    await t.test("partial selections restore the select-all label and fill only missing IDs", async () => {
      reset();
      await methods.selectAllMatchingTasksInExpandedGroup();
      methods.toggleBatchTaskSelection("two");
      assert.equal(els.batchSelectGroupButton.attributes["aria-pressed"], "false");
      await methods.selectAllMatchingTasksInExpandedGroup();
      assert.deepEqual(new Set(state.batchSelectedTaskIds), new Set(["other", "one", "two", "unloaded"]));
    });
    await t.test("manually selecting every loaded task also offers deselect-all", async () => {
      reset();
      state.taskSidebarGroupCounts.today = 2;
      state.batchSelectedTaskIds = ["other", "one", "two"];
      methods.renderBatchToolbar();
      assert.equal(els.batchSelectGroupButton.attributes["aria-pressed"], "true");
      await methods.selectAllMatchingTasksInExpandedGroup();
      assert.deepEqual(state.batchSelectedTaskIds, ["other"]);
      assert.equal(calls, 0);
    });
    await t.test("waiting selection is reversible without dropping unloaded history", () => {
      reset();
      state.batchSelectedTaskIds = ["unloaded"];
      state.queue.waiting = [{ task_id: "wait-1" }, { task_id: "wait-2" }];
      methods.selectWaitingTasksForBatch();
      assert.deepEqual(state.batchSelectedTaskIds, ["unloaded", "wait-1", "wait-2"]);
      assert.equal(state.batchSelectionIncludesUnloaded, true);
      assert.equal(els.batchSelectWaitingButton.attributes["data-i18n"], "batch.deselectWaiting");
      methods.selectWaitingTasksForBatch();
      assert.deepEqual(state.batchSelectedTaskIds, ["unloaded"]);
      state.queue.waiting = [];
      methods.renderBatchToolbar();
      assert.equal(els.batchSelectWaitingButton.disabled, true);
      assert.equal(els.batchSelectWaitingButton.attributes["aria-pressed"], "false");
    });
    for (const change of ["exit", "group", "filter", "selection"]) {
      await t.test(`pending requests cannot apply after ${change} changes`, async () => {
        reset();
        let resolve!: (value: any) => void;
        globalThis.fetch = (async () => { calls += 1; return new Promise((done) => { resolve = done; }); }) as any;
        const pending = methods.selectAllMatchingTasksInExpandedGroup();
        assert.equal(els.batchSelectGroupButton.disabled, true);
        await methods.selectAllMatchingTasksInExpandedGroup();
        assert.equal(calls, 1);
        if (change === "exit") methods.toggleBatchMode(false);
        if (change === "group") state.expandedTaskGroupKey = "yesterday";
        if (change === "filter") filters = { status: "failed" };
        if (change === "selection") methods.toggleBatchTaskSelection("one");
        const selection = state.batchSelectedTaskIds.slice();
        resolve({ ok: true, json: async () => ({ task_ids: ["unloaded"] }) });
        await pending;
        assert.deepEqual(state.batchSelectedTaskIds, selection);
        assert.equal(state.batchMode, change !== "exit");
        assert.equal(els.batchSelectGroupButton.attributes["aria-busy"], "false");
      });
    }
    await t.test("failure preserves selections and allows retry", async () => {
      reset();
      globalThis.fetch = (async () => { throw new Error("offline"); }) as any;
      await methods.selectAllMatchingTasksInExpandedGroup();
      assert.deepEqual(state.batchSelectedTaskIds, ["other"]);
      assert.equal(els.batchSelectGroupButton.disabled, false);
      assert.deepEqual(errors, ["offline"]);
    });
  } finally {
    (globalThis as any).window = previousWindow;
    (globalThis as any).document = previousDocument;
    globalThis.fetch = previousFetch;
  }
});

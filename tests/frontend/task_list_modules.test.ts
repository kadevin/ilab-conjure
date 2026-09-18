import assert from "node:assert/strict";
import test from "node:test";
import { createTaskListModel } from "../../codex_image/webui/frontend/src/task-list-model";
import { createTaskListViewport } from "../../codex_image/webui/frontend/src/task-list-viewport";

function modelFixture() {
  const state: any = {
    queue: { running: [], waiting: [] }, tasks: [], batchSelectedTaskIds: [],
    batchMode: false, selectedTaskId: null, taskSidebarGroupCounts: {},
  };
  const filters = { status: "", ratio: "", orientation: "", promptFidelity: "", resolution: "" };
  const model = createTaskListModel({
    getState: () => state,
    taskArchived: task => Boolean(task.archived), taskBackendLabel: task => task.backend || "",
    taskFilterValues: () => filters, taskOrientation: task => task.orientation,
    taskOutputUrls: task => task.output_urls || [], taskPromptFidelity: task => task.prompt_fidelity,
    taskRatio: task => task.ratio, taskResolution: task => task.resolution,
    timestampMs: value => value ? Date.parse(value) : null,
  });
  return { state, filters, model };
}

test("queue transitions retain section order without mutating task input", () => {
  const { state, model } = modelFixture();
  const first = { task_id: "a", status: "queued" };
  const second = { task_id: "b", status: "queued" };
  const pending = { task_id: "c", local_pending: true };
  const tasks = Object.freeze([pending, first, second]);
  state.queue.waiting = [second, first];
  assert.deepEqual(model.activeTasksForGroup([...tasks]).map(t => t.task_id), ["b", "a", "c"]);
  state.queue = { waiting: [first], running: [{ ...second, status: "running" }] };
  const ordered = model.activeTasksForGroup([...tasks]);
  assert.deepEqual(model.activeTaskSections(ordered).running.map(t => t.task_id), ["b"]);
  assert.deepEqual(model.activeTaskSections(ordered).waiting.map(t => t.task_id), ["a", "c"]);
  assert.deepEqual(tasks.map(t => t.task_id), ["c", "a", "b"]);
});

test("server search matches are accepted only for the current query", () => {
  const { state, model } = modelFixture();
  const task = { task_id: "a", prompt: "unrelated text" };
  state.taskSearchHistoryResultIds = ["a"];
  state.taskSearchHistoryResultQuery = "old";
  assert.equal(model.taskMatchesSearch(task, "old"), true);
  assert.equal(model.taskMatchesSearch(task, "new"), false);
  assert.equal(model.taskMatchesSearch(task, " UNRELATED "), true);
});

test("selection alone leaves the render key stable while queue and batch changes invalidate it", () => {
  const { state, model } = modelFixture();
  state.tasks = [{ task_id: "a", status: "queued" }];
  const key = model.taskListRenderKey(state.tasks, "");
  state.selectedTaskId = "a";
  assert.equal(model.taskListRenderKey(state.tasks, ""), key);
  state.queue.waiting = [{ task_id: "a" }];
  assert.notEqual(model.taskListRenderKey(state.tasks, ""), key);
  const queuedKey = model.taskListRenderKey(state.tasks, "");
  state.batchSelectedTaskIds = ["off-window"];
  assert.notEqual(model.taskListRenderKey(state.tasks, ""), queuedKey);
});

test("terminal activity ignores maintenance timestamps and anchor layout has a single current group", () => {
  const { model } = modelFixture();
  const task = { terminal_at: "2026-09-01T12:00:00Z", updated_at: "2026-09-17T12:00:00Z" };
  assert.equal(model.taskHistoryActivityTimestamp(task), Date.parse(task.terminal_at));
  const groups = [{ key: "today" }, { key: "yesterday" }, { key: "last7" }];
  const layout = model.taskAnchorLayout(groups, "yesterday", "");
  assert.deepEqual(layout.top, [groups[0]]);
  assert.equal(layout.expandedGroup, groups[1]);
  assert.deepEqual(layout.bottom, [groups[2]]);
  assert.deepEqual(model.taskAnchorLayout(groups, null, "search").bottom, []);
});

function viewportFixture() {
  const savedFrame = globalThis.requestAnimationFrame;
  const savedWindow = globalThis.window;
  globalThis.window = { CSS: { escape: (value: string) => value } } as any;
  const frames: FrameRequestCallback[] = [];
  globalThis.requestAnimationFrame = callback => { frames.push(callback); return frames.length; };
  const state = { queue: { running: [], waiting: [] as any[] }, queueDragTaskId: null as string | null };
  let animationPending = false;
  const bodies = new Map<string, any>();
  function body(key: string) {
    const result = {
      dataset: { renderComplete: "false" }, style: { maxHeight: "", opacity: "" }, cards: [] as any[],
      insertAdjacentHTML(_position: string, html: string) {
        for (const match of html.matchAll(/data-task-id="([^"]+)"/g)) this.cards.push({ dataset: { taskId: match[1] } });
      },
      querySelectorAll(selector: string) { return selector.startsWith(".task-card") ? this.cards : []; },
    };
    bodies.set(key, result);
    return result;
  }
  const active = { innerHTML: "", classList: { toggle() {} } };
  const controller = createTaskListViewport({
    getState: () => state as any,
    els: {
      taskList: { querySelector: (selector: string) => bodies.get(selector.match(/key="([^"]+)"/)?.[1] || "") || null },
      taskActiveList: active, taskHistoryCurrentAnchor: null, sidebarContent: null, taskHistoryShell: null,
    },
    consumeLatestTaskNavigationScrollAnchor: anchor => anchor,
    expandedTaskGroupHeaderHtml: () => "", scheduleLatestTaskNavigationRefresh() {}, scheduleSidebarTaskGroupAutoLoad() {},
    taskCardHtml: task => `<div data-task-id="${task.task_id}"></div>`,
    taskGroupCount: group => group.tasks.length, taskGroupLoadMoreHtml: () => "",
    updateTaskElapsedDisplays() {}, cancelActiveTaskQueueReorder() { state.queueDragTaskId = null; },
    consumeExpansionAnimation() { const pending = animationPending; animationPending = false; return pending; },
  });
  return {
    state, controller, body, active, frames,
    flush() { while (frames.length) frames.shift()!(0); },
    restore() { globalThis.requestAnimationFrame = savedFrame; globalThis.window = savedWindow; },
  };
}

test("a newer group invalidates queued old chunks and renders all cards once", () => {
  const f = viewportFixture();
  try {
    const old = f.body("old"), current = f.body("current");
    f.controller.scheduleExpandedTaskGroupItemsRender({ key: "old", tasks: [{ task_id: "old" }] });
    const tasks = Array.from({ length: 125 }, (_, i) => ({ task_id: String(i) }));
    f.controller.scheduleExpandedTaskGroupItemsRender({ key: "current", tasks });
    f.frames.shift()!(0);
    f.frames.shift()!(0);
    assert.equal(current.cards.length, 24);
    f.flush();
    assert.equal(old.cards.length, 0);
    assert.deepEqual(current.cards.map((c: any) => c.dataset.taskId), tasks.map(t => t.task_id));
    assert.equal(current.dataset.renderComplete, "true");
  } finally { f.restore(); }
});

test("append requires the existing prefix and explicit invalidation stops pending render", () => {
  const f = viewportFixture();
  try {
    const body = f.body("today");
    f.controller.scheduleExpandedTaskGroupItemsRender({ key: "today", tasks: [{ task_id: "a" }] });
    f.flush();
    assert.equal(f.controller.appendExpandedTaskGroupPage({ key: "today", tasks: [{ task_id: "wrong" }] }, "today"), false);
    assert.equal(f.controller.appendExpandedTaskGroupPage({ key: "today", tasks: [{ task_id: "a" }, { task_id: "b" }] }, "today"), true);
    f.flush();
    assert.deepEqual(body.cards.map((c: any) => c.dataset.taskId), ["a", "b"]);
    f.controller.scheduleExpandedTaskGroupItemsRender({ key: "today", tasks: [{ task_id: "stale" }] });
    f.controller.invalidateTaskGroupRender();
    f.flush();
    assert.equal(body.cards.length, 2);
  } finally { f.restore(); }
});

test("waiting drag defers active DOM replacement and leaving the queue releases the drag", () => {
  const f = viewportFixture();
  try {
    f.state.queueDragTaskId = "a";
    f.state.queue.waiting = [{ task_id: "a" }];
    f.controller.renderActiveTaskGroup("waiting");
    assert.equal(f.active.innerHTML, "");
    assert.equal(f.controller.flushDeferredActiveTaskGroupRender(), false);
    f.state.queue.waiting = [];
    f.controller.renderActiveTaskGroup("running");
    assert.equal(f.active.innerHTML, "running");
    assert.equal(f.state.queueDragTaskId, null);
    assert.equal(f.controller.discardDeferredActiveTaskGroupRender(), false);
  } finally { f.restore(); }
});

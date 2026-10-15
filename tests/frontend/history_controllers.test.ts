import assert from "node:assert/strict";
import test from "node:test";
import { createHistorySelectionModel, emptyHistorySelection, reduceHistorySelection } from "../../codex_image/webui/frontend/src/history-selection-model";
import { createHistoryListController } from "../../codex_image/webui/frontend/src/history-list-controller";
import { createHistoryDetailController } from "../../codex_image/webui/frontend/src/history-detail-controller";
import { createHistoryTaskActions } from "../../codex_image/webui/frontend/src/history-task-actions";
import { createHistoryFiltersController } from "../../codex_image/webui/frontend/src/history-filters-controller";

const noop = () => {};
function deferred<T>() { let resolve!: (value: T) => void; const promise = new Promise<T>(done => { resolve = done; }); return { promise, resolve }; }
function element() {
  const classes = new Set<string>();
  return { dataset: {} as Record<string, string>, innerHTML: "", textContent: "", hidden: false,
    classList: { add: (...names: string[]) => names.forEach(n => classes.add(n)), remove: (...names: string[]) => names.forEach(n => classes.delete(n)), contains: (name: string) => classes.has(name), toggle: noop },
    setAttribute: noop, removeAttribute: noop, toggleAttribute: noop, querySelector: () => null, querySelectorAll: () => [], focus: noop };
}
function environment(t: any, elements: Record<string, unknown> = {}) {
  t.mock.method(globalThis, "fetch", async () => { throw new Error("Unexpected request"); });
  const document = { querySelector: (selector: string) => elements[selector] || null, querySelectorAll: () => [] };
  const location = { search: "", pathname: "/history" };
  const window = { location, history: { replaceState: (_: any, _title: string, url: string) => { location.search = new URL(url, "http://test.local").search; } }, requestAnimationFrame: () => 1, cancelAnimationFrame: noop, matchMedia: () => ({ matches: false }) };
  const previous = ["document", "window", "localStorage"].map(key => [key, Object.getOwnPropertyDescriptor(globalThis, key)] as const);
  Object.assign(globalThis, { document, window, localStorage: { getItem: () => null, setItem: noop } });
  t.after(() => previous.forEach(([key, descriptor]) => descriptor ? Object.defineProperty(globalThis, key, descriptor) : Reflect.deleteProperty(globalThis, key)));
  return window;
}
const response = (data: unknown, ok = true) => ({ ok, json: async () => data }) as Response;
function listPorts() {
  return { filters: { organization: () => ({ favorite: false, untagged: false, tagIds: [] }), supported: () => true, markUnsupported: noop,
    queryParams: () => "limit=50", historyPageQueryInput: () => ({}), syncHistoryViewMode: noop, snapshot: () => ({ archived: "" }) },
    layout: { layoutJustifiedHistoryGrid: noop }, renderCard: () => "", resetSelectionForLoad: noop, renderToolbar: noop, renderSelection: noop,
    enablePositionSave: noop, dropSelection: noop, reconcileSelection: noop, organizationsChanged: noop } as any;
}
function detailPorts(selection = createHistorySelectionModel()) {
  return { selection, filters: { updateHistoryUrl: noop }, list: { loadTasks: async () => ({}), status: () => ({}) }, confirmations: () => ({}),
    resetTaskConfirmations: noop, renderToolbar: noop, renderSelection: noop, mountedIds: () => [], ensureVisible: noop, closeActionPickers: noop } as any;
}

test("selection snapshots cannot mutate the model, and previous reducer states stay unchanged", () => {
  const model = createHistorySelectionModel(); model.dispatch({ type: "replace", ids: ["a", "b"], anchor: "a", primary: "b" });
  const old = model.snapshot(); (old.selectedTaskIds as Set<string>).clear();
  assert.deepEqual([...model.snapshot().selectedTaskIds], ["a", "b"]);
  const state = reduceHistorySelection(emptyHistorySelection(), { type: "location", id: "a" });
  reduceHistorySelection(state, { type: "toggle", id: "b", anchor: true });
  assert.deepEqual([...state.selectedTaskIds], ["a"]);
});
test("selection has no dependency on mounted rows; additive selection preserves an off-window ID", () => {
  let state = reduceHistorySelection(emptyHistorySelection(), { type: "location", id: "off-window" });
  state = reduceHistorySelection(state, { type: "replace", ids: [...state.selectedTaskIds, "visible"], anchor: "visible", primary: "visible" });
  assert.deepEqual([...state.selectedTaskIds], ["off-window", "visible"]);
});
test("touch mode survives toggling the last item off and exits on explicit reset", () => {
  const model = createHistorySelectionModel(); model.dispatch({ type: "enter-touch" });
  model.dispatch({ type: "toggle", id: "a", anchor: true }); model.dispatch({ type: "toggle", id: "a", anchor: true });
  assert.equal(model.snapshot().selectionMode, true); assert.equal(model.snapshot().selectedTaskIds.size, 0);
  model.dispatch({ type: "reset" }); assert.equal(model.snapshot().selectionMode, false);
});
test("a stale list response cannot commit or clear the loading state of a newer query", async t => {
  environment(t); const a = deferred<Response>(), b = deferred<Response>(); let n = 0;
  t.mock.method(globalThis, "fetch", () => (++n === 1 ? a.promise : b.promise));
  const list = createHistoryListController(listPorts());
  const old = list.loadTasks({ reset: true }); const current = list.loadTasks({ reset: true });
  a.resolve(response({ tasks: [{ task_id: "old" }], next_cursor: "old-cursor" }));
  assert.equal((await old).taskCount, 0); assert.equal(list.status().loading, true);
  b.resolve(response({ tasks: [], next_cursor: null })); await current;
  assert.equal(list.status().loading, false); assert.equal(list.status().exhausted, true);
});
test("list response B then A leaves B's exhausted state intact", async t => {
  environment(t); const a = deferred<Response>(), b = deferred<Response>(); let n = 0;
  t.mock.method(globalThis, "fetch", () => (++n === 1 ? a.promise : b.promise));
  const list = createHistoryListController(listPorts()); const old = list.loadTasks({ reset: true }); const current = list.loadTasks({ reset: true });
  b.resolve(response({ tasks: [], next_cursor: null })); await current;
  a.resolve(response({ tasks: [{ task_id: "late" }], next_cursor: "late" })); await old;
  assert.equal(list.status().exhausted, true); assert.equal(list.status().loading, false);
});
test("failed ordinary pagination remains retryable and does not claim exhaustion", async t => {
  environment(t); let n = 0; t.mock.method(globalThis, "fetch", async () => ++n === 1 ? response({ detail: "offline" }, false) : response({ tasks: [], next_cursor: null }));
  const list = createHistoryListController(listPorts()); await assert.rejects(list.loadTasks({ reset: true, throwOnError: true }), /offline/);
  assert.equal(list.status().exhausted, false); await list.loadTasks({ reset: true }); assert.equal(n, 2);
});
test("realtime history requests honor cancellation and release loading for retry", async t => {
  environment(t);
  const list = createHistoryListController(listPorts());
  const filters = createHistoryFiltersController({
    selectedTaskId: () => "", selectLocationTask: noop, resetSelection: noop,
    clearDeleteConfirmation: noop, loadTasks: list.loadTasks, scheduleLayout: noop,
    loadedTasks: () => [], applyOrganizations: noop,
  });
  t.mock.method(globalThis, "fetch", (_url, options) => new Promise<Response>((_resolve, reject) => {
    options?.signal?.addEventListener("abort", () => reject(new DOMException("Aborted", "AbortError")), { once: true });
  }));
  const controller = new AbortController();
  const summary = filters.loadSummary({ signal: controller.signal, throwOnError: true });
  const page = list.loadTasks({ reset: true, signal: controller.signal, throwOnError: true });
  controller.abort();
  await assert.rejects(summary, { name: "AbortError" });
  await assert.rejects(page, { name: "AbortError" });
  assert.equal(list.status().loading, false);
  assert.equal(list.status().exhausted, false);
});

test("mounted refresh updates summaries, drops deleted cards and rejects results after a new query", async t => {
  const taskList = { ...element(), getBoundingClientRect: () => ({ top: 0 }) };
  environment(t, { "#historyTaskList": taskList });
  const ports = listPorts();
  const dropped: string[] = [];
  ports.dropSelection = (id: string) => dropped.push(id);
  const list = createHistoryListController(ports);
  const tasks = [{ task_id: "a", status: "running", tags: [] }, { task_id: "b", status: "completed", tags: [] }];
  t.mock.method(globalThis, "fetch", async () => response({ tasks, next_cursor: "next" }));
  await list.loadTasks({ reset: true });
  t.mock.method(globalThis, "fetch", async (_url, options) => {
    assert.deepEqual(JSON.parse(String(options?.body)).task_ids, ["a", "b"]);
    return response({ tasks: [{ ...tasks[0], status: "completed" }] });
  });
  await list.refreshMountedTasks();
  assert.equal(list.historyTaskSummary("a")?.status, "completed");
  assert.equal(list.historyTaskSummary("b"), null);
  assert.deepEqual(dropped, ["b"]);
  assert.equal(list.status().exhausted, false);
  const pending = deferred<Response>();
  t.mock.method(globalThis, "fetch", () => pending.promise);
  const stale = list.refreshMountedTasks();
  t.mock.method(globalThis, "fetch", async () => response({ tasks: [{ task_id: "c", status: "failed", tags: [] }], next_cursor: null }));
  await list.loadTasks({ reset: true });
  pending.resolve(response({ tasks: [] }));
  await stale;
  assert.equal(list.historyTaskSummary("c")?.status, "failed");
});
test("mounted refresh preserves user edits made in flight and ignores canceled results", async t => {
  const taskList = { ...element(), getBoundingClientRect: () => ({ top: 0 }) };
  environment(t, { "#historyTaskList": taskList });
  const list = createHistoryListController(listPorts());
  t.mock.method(globalThis, "fetch", async () => response({ tasks: [{ task_id: "a", status: "running", tags: [], favorite: false }], next_cursor: null }));
  await list.loadTasks({ reset: true });
  const pending = deferred<Response>();
  t.mock.method(globalThis, "fetch", () => pending.promise);
  const refresh = list.refreshMountedTasks();
  list.applyHistoryOrganizations({ a: { favorite: true, tags: [] } });
  pending.resolve(response({ tasks: [{ task_id: "a", status: "running", tags: [], favorite: false }] }));
  await refresh;
  assert.equal(list.historyTaskSummary("a")?.favorite, true);
  const canceled = deferred<Response>();
  const controller = new AbortController();
  t.mock.method(globalThis, "fetch", () => canceled.promise);
  const result = list.refreshMountedTasks({ signal: controller.signal });
  controller.abort();
  canceled.resolve(response({ tasks: [] }));
  await assert.rejects(result, { name: "AbortError" });
  assert.equal(list.historyTaskSummary("a")?.favorite, true);
});
test("background top reload preserves multi-selection and touch mode while explicit reload resets them", async t => {
  environment(t);
  const selection = createHistorySelectionModel();
  const ports = listPorts();
  ports.resetSelectionForLoad = () => selection.dispatch({ type: "reload" });
  const list = createHistoryListController(ports);
  selection.dispatch({ type: "replace", ids: ["a", "b"], primary: "b", anchor: "b" });
  selection.dispatch({ type: "enter-touch" });
  t.mock.method(globalThis, "fetch", async () => response({ tasks: [], next_cursor: null }));
  await list.loadTasks({ reset: true, preserveSelection: true });
  assert.deepEqual([...selection.snapshot().selectedTaskIds], ["a", "b"]);
  assert.equal(selection.snapshot().selectionMode, true);
  await list.loadTasks({ reset: true });
  assert.deepEqual([...selection.snapshot().selectedTaskIds], ["b"]);
  assert.equal(selection.snapshot().selectionMode, false);
});
test("detail B then A renders B and rejects A's late result", async t => {
  const panel = element(); environment(t, { "#historyDetail": panel });
  const a = deferred<Response>(), b = deferred<Response>(); let n = 0;
  t.mock.method(globalThis, "fetch", () => (++n === 1 ? a.promise : b.promise));
  const details = createHistoryDetailController(detailPorts()); const old = details.loadTaskDetail("a"), current = details.loadTaskDetail("b");
  b.resolve(response({ task: { task_id: "b", status: "completed" } })); await current;
  a.resolve(response({ task: { task_id: "a" } })); await old;
  assert.equal(details.task().task_id, "b"); assert.equal(panel.dataset.historyDetailMode, "task");
});

test("failed and canceled background reloads retain the loaded history window", async t => {
  const taskList = { ...element(), getBoundingClientRect: () => ({ top: 0 }) };
  environment(t, { "#historyTaskList": taskList });
  const list = createHistoryListController(listPorts());
  t.mock.method(globalThis, "fetch", async () => response({ tasks: [{ task_id: "a", status: "running", tags: [] }], next_cursor: "next" }));
  await list.loadTasks({ reset: true });
  const before = list.summaries();
  const pending = deferred<Response>();
  t.mock.method(globalThis, "fetch", () => pending.promise);
  const load = list.loadTasks({ reset: true, preserveSelection: true, throwOnError: true });
  assert.deepEqual(list.summaries(), before, "keep the current window while reading");
  pending.resolve(response({ detail: "offline" }, false));
  await assert.rejects(load, /offline/);
  assert.deepEqual(list.summaries(), before);
  const controller = new AbortController();
  t.mock.method(globalThis, "fetch", async () => { controller.abort(); return response({ tasks: [] }); });
  await assert.rejects(list.loadTasks({ reset: true, preserveSelection: true, signal: controller.signal, throwOnError: true }), { name: "AbortError" });
  assert.deepEqual(list.summaries(), before);
  assert.ok(!taskList.innerHTML.includes("aborted"));
});

test("history detail follows refreshed task data and rejects an older background read", async t => {
  const panel = element(); environment(t, { "#historyDetail": panel });
  let summary = { task_id: "a", status: "running", updated_at: "2026-10-15T00:00:00Z" };
  const ports = detailPorts(); ports.list.historyTaskSummary = () => summary;
  const details = createHistoryDetailController(ports);
  t.mock.method(globalThis, "fetch", async () => response({ task: summary }));
  await details.loadTaskDetail("a");
  summary = { ...summary, status: "completed", updated_at: "2026-10-15T00:01:00Z" };
  t.mock.method(globalThis, "fetch", async () => response({ task: { ...summary, output_urls: ["/synthetic.png"] } }));
  await details.refreshTaskDetail();
  assert.equal(details.task().status, "completed");
  assert.deepEqual(details.task().output_urls, ["/synthetic.png"]);
  summary = { ...summary, status: "queued", updated_at: "2026-10-15T00:02:00Z" };
  const pending = deferred<Response>(); t.mock.method(globalThis, "fetch", () => pending.promise);
  const old = details.refreshTaskDetail();
  const newest = { ...summary, status: "failed", updated_at: "2026-10-15T00:03:00Z" };
  await details.refreshTaskDetail({ task: newest });
  pending.resolve(response({ task: summary })); await old;
  assert.equal(details.task().status, "failed");
  assert.equal(details.task().updated_at, newest.updated_at);
  assert.equal(details.task().output_urls, undefined, "removed output fields must not survive a full update");
});

test("background reload does not pull a user back after scrolling during the request", async t => {
  const taskList = { ...element(), scrollTop: 0, getBoundingClientRect: () => ({ top: 0 }) };
  environment(t, { "#historyTaskList": taskList });
  const list = createHistoryListController(listPorts());
  t.mock.method(globalThis, "fetch", async () => response({ tasks: [{ task_id: "a", tags: [] }], next_cursor: "next" }));
  await list.loadTasks({ reset: true });
  const pending = deferred<Response>(); t.mock.method(globalThis, "fetch", () => pending.promise);
  const load = list.loadTasks({ reset: true, preserveSelection: true });
  taskList.scrollTop = 420;
  pending.resolve(response({ tasks: [{ task_id: "new", tags: [] }], next_cursor: null })); await load;
  assert.equal(list.summaries()[0].task_id, "a");
  assert.equal(taskList.scrollTop, 420); assert.equal(list.status().loading, false);
});

test("background top reload cannot undo a favorite edit or resurrect a removed task", async t => {
  const taskList = { ...element(), scrollTop: 0, getBoundingClientRect: () => ({ top: 0 }) };
  environment(t, { "#historyTaskList": taskList });
  const list = createHistoryListController(listPorts());
  const tasks = [{ task_id: "a", status: "completed", tags: [], favorite: false }];
  for (const mutation of ["favorite", "remove"]) {
    t.mock.method(globalThis, "fetch", async () => response({ tasks: structuredClone(tasks), next_cursor: "next" }));
    await list.loadTasks({ reset: true });
    const pending = deferred<Response>(); t.mock.method(globalThis, "fetch", () => pending.promise);
    const load = list.loadTasks({ reset: true, preserveSelection: true });
    if (mutation === "favorite") list.applyHistoryOrganizations({ a: { favorite: true, tags: [] } });
    else list.removeHistoryTaskIdsFromWindow(["a"]);
    pending.resolve(response({ tasks: structuredClone(tasks), next_cursor: null })); await load;
    if (mutation === "favorite") assert.equal(list.historyTaskSummary("a")?.favorite, true);
    else assert.equal(list.historyTaskSummary("a"), null);
    assert.equal(list.status().loading, false);
  }
});

test("a failed background detail read preserves the open detail and honors cancellation", async t => {
  const panel = element(), result = element(); environment(t, { "#historyDetail": panel, "#historyResultSummary": result });
  const ports = detailPorts(); ports.list.historyTaskSummary = () => ({ task_id: "a", updated_at: "2026-10-15T00:01:00Z" });
  const details = createHistoryDetailController(ports);
  t.mock.method(globalThis, "fetch", async () => response({ task: { task_id: "a", status: "running" } }));
  await details.loadTaskDetail("a"); const before = panel.innerHTML;
  t.mock.method(globalThis, "fetch", async () => response({ detail: "local detail unavailable" }, false));
  await details.refreshTaskDetail(); assert.equal(panel.innerHTML, before); assert.equal(result.textContent, "local detail unavailable");
  const controller = new AbortController();
  t.mock.method(globalThis, "fetch", async () => { controller.abort(); return response({ task: { task_id: "a", status: "failed" } }); });
  await assert.rejects(details.refreshTaskDetail({ signal: controller.signal }), { name: "AbortError" });
  assert.equal(panel.innerHTML, before); assert.equal(result.textContent, "local detail unavailable");
});

test("history summary rejects old results and canceled error messages", async t => {
  const total = element(); environment(t, { "#historyTotal": total });
  const filters = createHistoryFiltersController({ selectedTaskId: () => "", selectLocationTask: noop, resetSelection: noop,
    clearDeleteConfirmation: noop, loadTasks: async () => ({ anchorFound: null, taskCount: 0 }), scheduleLayout: noop,
    loadedTasks: () => [], applyOrganizations: noop });
  const summary = (name: string, count: number) => ({ total: count, archived_total: 0, favorite_total: 0, untagged_total: 0,
    tags: [{ tag_id: name, name }], months: [], ratios: [], orientations: [], backends: [] });
  const pending = deferred<Response>(); t.mock.method(globalThis, "fetch", () => pending.promise);
  const old = filters.loadSummary();
  t.mock.method(globalThis, "fetch", async () => response(summary("new", 2)));
  await filters.loadSummary(); const currentTotal = total.textContent;
  pending.resolve(response(summary("old", 1))); await old;
  assert.equal(total.textContent, currentTotal); assert.equal(filters.tags()[0].name, "new");
  const controller = new AbortController();
  t.mock.method(globalThis, "fetch", async () => { controller.abort(); throw controller.signal.reason; });
  await assert.rejects(filters.loadSummary({ signal: controller.signal, throwOnError: true }), { name: "AbortError" });
  assert.equal(total.textContent, currentTotal);
});
test("closing detail invalidates an outstanding request and clears selection", async t => {
  const panel = element(); environment(t, { "#historyDetail": panel }); const pending = deferred<Response>();
  t.mock.method(globalThis, "fetch", () => pending.promise); const ports = detailPorts(); const details = createHistoryDetailController(ports);
  const load = details.loadTaskDetail("a"); details.closeDetail(); pending.resolve(response({ task: { task_id: "a" } })); await load;
  assert.equal(details.task(), null); assert.equal(ports.selection.snapshot().selectedTaskIds.size, 0); assert.equal(panel.dataset.historyDetailMode, "management");
});
test("narrow selection drawer closes without clearing its selected tasks", t => {
  const panel = element(); panel.dataset.historyDetailMode = "selection"; const win = environment(t, { "#historyDetail": panel });
  win.matchMedia = () => ({ matches: true }); const ports = detailPorts(); ports.selection.dispatch({ type: "replace", ids: ["a", "b"], primary: "a", anchor: "a" });
  createHistoryDetailController(ports).closeDetail(); assert.deepEqual([...ports.selection.snapshot().selectedTaskIds], ["a", "b"]);
});
test("bulk delete freezes IDs and retains failed tasks after partial success", async t => {
  environment(t); const selection = createHistorySelectionModel(); const removed: string[][] = [], requested: string[] = [];
  const actions = createHistoryTaskActions({ selection, filters: { supported: () => true, loadSummary: async () => {} }, list: { removeHistoryTaskIdsFromWindow: ids => removed.push(ids) },
    details: { syncHistorySelectionDetail: noop }, reconcileSelection: noop, renderToolbar: noop, renderSelection: noop, rerenderContextMenu: noop, closeContextMenu: noop } as any);
  selection.dispatch({ type: "replace", ids: ["a", "b"], primary: "a", anchor: "a" }); await actions.deleteSelectedTasks();
  assert.deepEqual(actions.confirmations().pendingDeleteTaskIds, ["a", "b"]);
  selection.dispatch({ type: "replace", ids: ["c"], primary: "c", anchor: "c" });
  t.mock.method(globalThis, "fetch", async (url: any) => { requested.push(url); return response({}, url.endsWith("/a")); });
  await actions.deleteSelectedTasks(); assert.deepEqual(requested, ["/api/tasks/a", "/api/tasks/b"]); assert.deepEqual(removed, [["a"]]);
  assert.deepEqual([...selection.snapshot().selectedTaskIds], ["b"]); assert.equal(selection.snapshot().selectedTaskId, "b"); assert.equal(actions.confirmations().deleteConfirming, false);
});
test("canceling delete confirmation makes no request", async t => {
  environment(t); const selection = createHistorySelectionModel(); selection.dispatch({ type: "location", id: "a" });
  const actions = createHistoryTaskActions({ selection, renderToolbar: noop } as any);
  await actions.deleteSelectedTasks(); actions.clearHistoryDeleteConfirmation(); assert.deepEqual(actions.confirmations().pendingDeleteTaskIds, []);
});
test("query round-trip keeps tags/sort/view/task, view switches do not reload, backup filters own their arrays", t => {
  const win = environment(t); win.location.search = "?q=cat&sort=oldest&view=list&task=task-a&tag=one&tag=two&favorite=true&mode=generate";
  let selected = "", loads = 0;
  const filters = createHistoryFiltersController({ selectedTaskId: () => selected, selectLocationTask: id => { selected = id; }, resetSelection: noop, clearDeleteConfirmation: noop,
    loadTasks: async () => { loads++; return { anchorFound: null, taskCount: 0 }; }, scheduleLayout: noop, loadedTasks: () => [], applyOrganizations: noop });
  filters.syncStateFromUrl(); filters.updateHistoryUrl(); const params = new URLSearchParams(win.location.search);
  assert.equal(params.get("q"), "cat"); assert.equal(params.get("sort"), "oldest"); assert.equal(params.get("view"), "list"); assert.equal(params.get("task"), "task-a");
  assert.deepEqual(params.getAll("tag"), ["one", "two"]); filters.setHistoryViewMode("grid"); assert.equal(loads, 0);
  const backup = filters.currentHistoryBackupFilters(); backup.tag_ids.length = 0; assert.deepEqual(filters.organization().tagIds, ["one", "two"]);
});


test("disposing a list completes queued anchor promises and prevents new requests", async t => {
  const win = environment(t); const frames = new Map<number, () => void>();
  win.requestAnimationFrame = (callback: () => void) => { frames.set(1, callback); return 1; };
  win.cancelAnimationFrame = (id: number) => { frames.delete(id); };
  let requests = 0;
  t.mock.method(globalThis, "fetch", async () => { requests++; return response({ tasks: [], anchor_found: true, next_cursor: null }); });
  const ports = listPorts(); ports.filters.historyPageQueryInput = () => ({ limit: 50, sort: "newest", filters: {}, organization: { favorite: false, untagged: false, tagIds: [] } });
  const list = createHistoryListController(ports); const pending = list.loadTasks({ reset: true, anchorTaskId: "a" });
  await new Promise(done => setImmediate(done)); assert.equal(frames.size, 1);
  list.dispose(); assert.equal((await pending).taskCount, 0); assert.equal(frames.size, 0);
  await list.loadTasks({ reset: true }); assert.equal(requests, 1); assert.equal(list.status().loading, false);
});


test("curation keeps task deletion available and single outputs avoid duplicate actions", t => {
  const panel = element(); environment(t, { "#historyDetail": panel });
  const details = createHistoryDetailController(detailPorts());
  const task = { task_id: "curated", status: "completed", outputs: [{ index: 1, url: "/output/one.png" }], selected_output_indexes: [1] };
  details.renderTaskDetail(task);
  assert.match(panel.innerHTML, /data-history-delete-task="curated"/);
  assert.doesNotMatch(panel.innerHTML, /data-history-delete-unselected/);
  assert.doesNotMatch(panel.innerHTML, /data-history-output-selected-index/);
  assert.equal((panel.innerHTML.match(/href="\/output\/one.png" download/g) || []).length, 2, "one task download and one image download, with no duplicate curated download");
  details.renderTaskDetail({ ...task, outputs: [...task.outputs, { index: 2, url: "/output/two.png" }] });
  assert.match(panel.innerHTML, /data-history-delete-task="curated"/);
  assert.match(panel.innerHTML, /data-history-delete-unselected="curated"/);
  assert.match(panel.innerHTML, /data-history-output-selected-index="2"/);
  assert.equal((panel.innerHTML.match(/href="\/output\/one.png" download/g) || []).length, 2);
  details.renderTaskDetail({ ...task, outputs: [...task.outputs, { index: 2, url: "/output/two.png" }], selected_output_indexes: [1, 2] });
  assert.match(panel.innerHTML, /data-history-delete-task="curated"/);
  assert.doesNotMatch(panel.innerHTML, /data-history-delete-unselected/);
});

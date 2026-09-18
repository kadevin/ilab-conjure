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
test("detail B then A renders B and rejects A's late result", async t => {
  const panel = element(); environment(t, { "#historyDetail": panel });
  const a = deferred<Response>(), b = deferred<Response>(); let n = 0;
  t.mock.method(globalThis, "fetch", () => (++n === 1 ? a.promise : b.promise));
  const details = createHistoryDetailController(detailPorts()); const old = details.loadTaskDetail("a"), current = details.loadTaskDetail("b");
  b.resolve(response({ task: { task_id: "b", status: "completed" } })); await current;
  a.resolve(response({ task: { task_id: "a" } })); await old;
  assert.equal(details.task().task_id, "b"); assert.equal(panel.dataset.historyDetailMode, "task");
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

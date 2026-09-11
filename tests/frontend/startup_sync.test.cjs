const assert = require('node:assert/strict');
const test = require('node:test');
const fs = require('node:fs');
const path = require('node:path');
const ts = require('typescript');

const root = path.resolve('codex_image/webui/frontend/src');
const version = (revision, instance = 'server-a') => ({ instance, revision });
const task = (status = 'completed', task_id = 'task-a') => ({ task_id, status, prompt: 'synthetic task' });
const queue = (running = []) => ({ running, waiting: [], summary: { running_count: running.length, waiting_count: 0, channel_count: 0 } });
const page = (tasks, revision, instance) => ({ tasks, sync: version(revision, instance) });
const response = (data, ok = true) => ({ ok, json: async () => data });
const deferred = () => { let resolve; const promise = new Promise(r => { resolve = r; }); return { promise, resolve }; };
const flush = () => new Promise(resolve => setImmediate(resolve));

function fixture() {
  const state = {
    tasks: [], queue: queue(), tasksRequestSeq: 0, queueRequestSeq: 0,
    selectedTaskId: null, pendingTaskId: null, queueRenderKey: null,
    realtimeSnapshotNeedsArchiveMigration: true, taskSidebarGroupLoadedCounts: {},
    legacyArchivedTaskIds: [], batchSelectedTaskIds: [],
  };
  const calls = [];
  const storage = new Map();
  const methods = Object.fromEntries([
    'cleanupSessionSelections', 'renderTasks', 'renderArchiveButton', 'renderArchiveModal',
    'renderPreview', 'revokeTaskUploadPreviewUrls', 'markTaskViewed', 'notifyTaskUpdate',
    'updateDocumentTitle', 'setStatus',
  ].map(name => [name, () => {}]));
  methods.taskHasViewableUpdate = () => false;
  methods.updateTaskInState = task => {
    const index = state.tasks.findIndex(item => item.task_id === task.task_id);
    if (index < 0) state.tasks.push(task); else state.tasks[index] = task;
    return true;
  };
  methods.migrateLegacyArchivedTasks = async () => true;
  const bridge = { state, methods, els: {}, constants: {} };
  global.window = {
    __codexImageWebUI: bridge, setTimeout: () => 1, clearTimeout() {},
    startRealtimeUpdates: () => true, refreshQueue: async () => { calls.push('queue'); },
  };
  global.document = { addEventListener() {} };
  global.localStorage = { getItem: key => storage.get(key), removeItem: key => storage.delete(key) };
  let handler = async () => response(page([], 10));
  global.fetch = (...args) => { calls.push(args); return handler(...args); };
  const cache = new Map();
  function load(name) {
    if (name === './event-bindings') return { bindWebUIEvents() {} };
    if (name === './i18n') return { translate: key => key, formatTranslation: key => key, LOCALE_CHANGE_EVENT: 'locale' };
    if (name === './webui-utils') return { cssEscape: value => value };
    const filename = path.resolve(root, name) + '.ts';
    if (cache.has(filename)) return cache.get(filename).exports;
    const module = { exports: {} }; cache.set(filename, module);
    const compiled = ts.transpileModule(fs.readFileSync(filename, 'utf8'), {
      compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
    });
    new Function('require', 'module', 'exports', compiled.outputText)(load, module, module.exports);
    return module.exports;
  }
  load('./tasks').initTaskFeature();
  const realtime = load('./queue');
  return { state, methods, calls, storage, load, realtime, fetchWith(fn) { handler = fn; } };
}

test('startup loads HTTP history even when EventSource opens without a snapshot', async () => {
  const f = fixture();
  f.fetchWith(async () => response(page([task()], 1)));
  f.load('./boot').bootWebUI(f.state, {}, f.methods);
  await flush();
  assert.equal(f.state.tasks[0].status, 'completed');
  assert.ok(f.calls.includes('queue'));
  assert.equal(f.state.realtimeSnapshotNeedsArchiveMigration, false);
});

test('delayed SSE snapshot cannot regress newer HTTP tasks or queue', async () => {
  const f = fixture();
  f.fetchWith(async () => response(page([task()], 2)));
  await f.methods.refreshTasks();
  await f.realtime.handleRealtimePayload({ type: 'snapshot', ...page([task('running')], 1), queue: queue([task('running')]) });
  assert.equal(f.state.tasks[0].status, 'completed');
  assert.equal(f.state.queue.running.length, 0);
});

test('older HTTP response cannot replace a newer complete SSE snapshot', async () => {
  const f = fixture(); const pending = deferred();
  f.fetchWith(() => pending.promise);
  const refresh = f.methods.refreshTasks();
  await f.realtime.handleRealtimePayload({ type: 'snapshot', ...page([task()], 2), queue: queue() });
  pending.resolve(response(page([task('running')], 1)));
  assert.equal(await refresh, false);
  assert.equal(f.state.tasks[0].status, 'completed');
});

test('queue-only event does not cancel an in-flight complete history request', async () => {
  const f = fixture(); const pending = deferred();
  f.fetchWith(() => pending.promise);
  const refresh = f.methods.refreshTasks();
  await f.realtime.handleRealtimePayload({ type: 'queue', sync: version(2), queue: queue() });
  pending.resolve(response(page([task()], 1)));
  assert.equal(await refresh, true);
  assert.equal(f.state.tasks.length, 1);
});

test('newer task updates and additions survive an older HTTP snapshot', async () => {
  const f = fixture(); const pending = deferred();
  f.fetchWith(() => pending.promise);
  const refresh = f.methods.refreshTasks();
  await f.realtime.handleRealtimePayload({ type: 'task', sync: version(3), task: { ...task(), generated_count: 2 } });
  await f.realtime.handleRealtimePayload({ type: 'task', sync: version(4), task: task('completed', 'task-b') });
  pending.resolve(response(page([task(), task('completed', 'history')], 2)));
  await refresh;
  assert.equal(f.state.tasks.find(t => t.task_id === 'task-a').generated_count, 2);
  assert.deepEqual(f.state.tasks.map(t => t.task_id).sort(), ['history', 'task-a', 'task-b']);
  await f.realtime.handleRealtimePayload({ type: 'queue', sync: version(1), queue: queue([task('running')]) });
  assert.equal(f.state.tasks.find(t => t.task_id === 'task-a').status, 'completed');
});

test('HTTP failure preserves history and the pending migration; SSE can recover', async () => {
  const f = fixture(); f.state.tasks = [task()];
  f.fetchWith(async () => response({ detail: 'temporary failure' }, false));
  await assert.rejects(f.methods.refreshTasks({ migrateLegacyArchives: true }), /temporary failure/);
  assert.equal(f.state.tasks.length, 1);
  assert.equal(f.state.realtimeSnapshotNeedsArchiveMigration, true);
  await f.realtime.handleRealtimePayload({ type: 'snapshot', ...page([task('completed', 'recovered')], 2), queue: queue() });
  assert.equal(f.state.tasks[0].task_id, 'recovered');
  assert.equal(f.state.realtimeSnapshotNeedsArchiveMigration, false);
});

test('overlapping HTTP and SSE migrations make one archive write and retain failed migrations', async () => {
  const f = fixture(); f.load('./task-archive-controls').initTaskArchiveControlsFeature();
  f.state.legacyArchivedTaskIds = ['task-a'];
  const pending = deferred(); let writes = 0;
  f.fetchWith((url, options) => {
    if (options?.method === 'PATCH') { writes++; return pending.promise; }
    return Promise.resolve(response(page([task()], 1)));
  });
  const http = f.methods.refreshTasks({ migrateLegacyArchives: true });
  await flush();
  const sse = f.realtime.handleRealtimePayload({ type: 'snapshot', ...page([task()], 2), queue: queue() });
  await flush();
  assert.equal(writes, 1);
  pending.resolve(response({ detail: 'retry later' }, false));
  await Promise.all([http, sse]);
  assert.equal(f.state.realtimeSnapshotNeedsArchiveMigration, true);
  assert.deepEqual(f.state.legacyArchivedTaskIds, ['task-a']);
  f.fetchWith(async () => response({ task: { ...task(), archived_at: '2026-09-11' } }));
  await f.realtime.handleRealtimePayload({ type: 'snapshot', ...page([task()], 3), queue: queue() });
  assert.equal(f.state.realtimeSnapshotNeedsArchiveMigration, false);
  assert.deepEqual(f.state.legacyArchivedTaskIds, []);
  assert.ok(f.state.tasks[0].archived_at);
});

test('server restart accepts its fresh instance and rejects late responses from the retired instance', async () => {
  const f = fixture();
  await f.methods.applyTasksSnapshot([task()], { sync: version(99) });
  await f.methods.applyTasksSnapshot([task('completed', 'restart')], { sync: version(1, 'server-b') });
  assert.equal(await f.methods.applyTasksSnapshot([task('running')], { sync: version(100) }), false);
  assert.equal(f.state.tasks[0].task_id, 'restart');
});

function lanFixture() {
  const f = fixture();
  const node = () => ({
    checked: false, disabled: true, hidden: false, textContent: '', children: [], listeners: {},
    classList: { toggle() {} }, setAttribute() {},
    addEventListener(name, callback) { this.listeners[name] = callback; },
    replaceChildren() { this.children = []; }, append(...children) { this.children.push(...children); },
    focus() {}, select() {},
  });
  const els = window.__codexImageWebUI.els;
  Object.assign(els, { lanAccessEnabled: node(), lanAccessStatus: node(), lanAccessAddresses: node() });
  global.document.createElement = node;
  f.load('./lan-access-settings').initLanAccessSettingsFeature();
  return { ...f, els };
}
const lanSettings = (enabled, active = false) => ({ enabled, active, restart_required: enabled !== active, host_override: false, addresses: ['http://192.168.1.10:8787/'] });

test('LAN toggle disables duplicate saves, rolls back failures, and distinguishes pending activation', async () => {
  const f = lanFixture();
  f.fetchWith(async () => response(lanSettings(false)));
  await f.methods.refreshLanAccess();
  assert.equal(f.els.lanAccessEnabled.disabled, false);
  assert.equal(f.els.lanAccessStatus.textContent, 'lanAccess.localOnly');
  const failed = deferred(); let writes = 0;
  f.fetchWith((_url, options) => { assert.equal(options.method, 'PATCH'); writes++; return failed.promise; });
  f.els.lanAccessEnabled.checked = true;
  f.els.lanAccessEnabled.listeners.change();
  f.els.lanAccessEnabled.listeners.change();
  assert.equal(writes, 1);
  assert.equal(f.els.lanAccessEnabled.disabled, true);
  failed.resolve(response({}, false)); await flush();
  assert.equal(f.els.lanAccessEnabled.checked, false);
  assert.equal(f.els.lanAccessEnabled.disabled, false);
  assert.equal(f.els.lanAccessStatus.textContent, 'lanAccess.failed');
  f.fetchWith(async () => response(lanSettings(true)));
  f.els.lanAccessEnabled.checked = true;
  f.els.lanAccessEnabled.listeners.change(); await flush();
  assert.equal(f.els.lanAccessStatus.textContent, 'lanAccess.pendingEnable');
  assert.equal(f.els.lanAccessAddresses.hidden, false);
  const copy = f.els.lanAccessAddresses.children[0].children[1];
  Object.defineProperty(global, 'navigator', { configurable: true, value: { clipboard: { writeText: async () => {} } } });
  copy.listeners.click(); await flush();
  assert.equal(copy.textContent, 'lanAccess.copied');
  assert.equal(f.els.lanAccessStatus.textContent, 'lanAccess.pendingEnable');
});

test('LAN settings ignore stale reads and show active access until a saved disable is restarted', async () => {
  const f = lanFixture(); const older = deferred(); const newer = deferred();
  let requests = 0; f.fetchWith(() => ++requests === 1 ? older.promise : newer.promise);
  const first = f.methods.refreshLanAccess(); const second = f.methods.refreshLanAccess();
  newer.resolve(response(lanSettings(false, true))); await second;
  older.resolve(response(lanSettings(true, true))); await first;
  assert.equal(f.els.lanAccessEnabled.checked, false);
  assert.equal(f.els.lanAccessStatus.textContent, 'lanAccess.pendingDisable');
});

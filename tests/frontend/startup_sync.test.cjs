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

function realtimeFixture() {
  const f = fixture();
  const sources = [];
  const timers = new Map();
  let clock = 0, timerId = 0;
  window.setTimeout = (callback, delay) => {
    const id = ++timerId;
    timers.set(id, { callback, at: clock + delay });
    return id;
  };
  window.clearTimeout = id => timers.delete(id);
  class FakeEventSource {
    static CLOSED = 2;
    readyState = 0;
    listeners = new Map();
    constructor(url) { this.url = url; sources.push(this); }
    addEventListener(type, callback) { this.listeners.set(type, callback); }
    close() { this.readyState = 2; }
    open() { this.readyState = 1; this.onopen?.(); }
    error(state = 0) { this.readyState = state; this.onerror?.(); }
    message(payload) { this.onmessage?.({ data: JSON.stringify(payload) }); }
    heartbeat() { this.listeners.get('heartbeat')?.({ data: '{}' }); }
  }
  window.EventSource = global.EventSource = FakeEventSource;
  const status = { textContent: '' };
  window.__codexImageWebUI.els.statusText = status;
  f.methods.setStatus = text => { status.textContent = text; };
  let revision = 0, currentTask = task('running');
  f.fetchWith(async url => response(url === '/api/queue'
    ? { ...queue(currentTask.status === 'running' ? [currentTask] : []), sync: version(++revision) }
    : page([currentTask], ++revision)));
  return {
    ...f, sources, timers, status,
    setTask(value) { currentTask = value; },
    async advance(ms) {
      const end = clock + ms;
      for (;;) {
        const next = [...timers].filter(([, timer]) => timer.at <= end).sort((a, b) => a[1].at - b[1].at)[0];
        if (!next) break;
        clock = next[1].at;
        timers.delete(next[0]);
        next[1].callback();
        await flush();
      }
      clock = end;
    },
  };
}

test('a single stream error keeps reconciling tasks until push recovers', async () => {
  const f = realtimeFixture();
  f.methods.renderPreview = () => f.methods.setStatus('status.waiting');
  try {
    f.realtime.startRealtimeUpdates();
    const source = f.sources[0];
    source.open();
    source.error();
    await flush();
    f.setTask(task('completed'));
    await f.advance(5000);
    assert.equal(f.state.tasks[0].status, 'completed');
    assert.equal(f.status.textContent, 'queue.realtimePolling');
    source.open();
    source.message({ type: 'snapshot', ...page([task()], 100), queue: queue() });
    await flush();
    const calls = f.calls.length;
    await f.advance(5000);
    assert.equal(f.calls.length, calls, 'healthy push must stop fallback requests');
    assert.notEqual(f.status.textContent, 'queue.realtimePolling');
    assert.notEqual(f.status.textContent, 'queue.realtimeDisconnected');
  } finally { f.realtime.closeRealtimeUpdates(); }
  assert.equal(f.timers.size, 0);
});

test('a permanently closed stream is recreated and old callbacks are ignored', async () => {
  const f = realtimeFixture();
  try {
    f.realtime.startRealtimeUpdates();
    const old = f.sources[0];
    old.error(2);
    await flush();
    await f.advance(5000);
    assert.equal(f.sources.length, 2);
    f.sources[1].open();
    f.sources[1].heartbeat();
    old.error();
    old.message({ type: 'task', sync: version(1000), task: task('failed') });
    await flush();
    assert.notEqual(f.state.tasks[0].status, 'failed');
    assert.equal(f.status.textContent, '');
  } finally { f.realtime.closeRealtimeUpdates(); }
});

test('a silent stream is replaced; heartbeats keep healthy connections alive', async () => {
  const f = realtimeFixture();
  try {
    f.realtime.startRealtimeUpdates();
    f.sources[0].open();
    for (let i = 0; i < 4; i++) {
      await f.advance(15000);
      f.sources[0].heartbeat();
    }
    assert.equal(f.sources.length, 1);
    assert.equal(f.calls.length, 0);
    await f.advance(45000);
    assert.equal(f.sources[0].readyState, 2);
    assert.equal(f.sources.length, 2);
    assert.ok(f.calls.length > 0);
  } finally { f.realtime.closeRealtimeUpdates(); }
});

test('a stalled fallback request times out and recovery can try again', async () => {
  const f = realtimeFixture();
  try {
    f.fetchWith((_url, options) => new Promise((_resolve, reject) => {
      options?.signal?.addEventListener('abort', () => reject(new Error('aborted')), { once: true });
    }));
    f.realtime.startRealtimeUpdates();
    f.sources[0].error();
    await f.advance(10000);
    f.fetchWith(async url => response(url === '/api/queue'
      ? { ...queue(), sync: version(5) } : page([task()], 6)));
    await f.advance(5000);
    assert.equal(f.state.tasks[0]?.status, 'completed');
  } finally { f.realtime.closeRealtimeUpdates(); }
  await flush();
  assert.equal(f.timers.size, 0);
});

test('failed queue requests cannot report a healthy fallback and closing aborts pending work', async () => {
  const f = realtimeFixture();
  try {
    f.fetchWith(async url => url === '/api/queue'
      ? response({ detail: 'unavailable' }, false) : response(page([task()], 1)));
    f.realtime.startRealtimeUpdates();
    f.sources[0].error();
    await flush();
    assert.equal(f.status.textContent, 'queue.realtimeDisconnected');
    const signals = [];
    f.fetchWith((_url, options) => new Promise((_resolve, reject) => {
      signals.push(options.signal);
      options.signal.addEventListener('abort', () => reject(new Error('aborted')), { once: true });
    }));
    await f.advance(5000);
    f.realtime.closeRealtimeUpdates();
    f.status.textContent = 'new task status';
    await flush();
    assert.ok(signals.length >= 1);
    assert.ok(signals.every(signal => signal.aborted));
    assert.equal(f.status.textContent, 'new task status');
    assert.equal(f.timers.size, 0);
  } finally { f.realtime.closeRealtimeUpdates(); }
});

test('a stalled selected detail is aborted and the next fallback updates task state', async () => {
  const f = realtimeFixture();
  f.load('./task-selection').initTaskSelectionFeature();
  f.state.selectedTaskId = 'task-a';
  let detailSignal, revision = 0, stalled = true;
  f.fetchWith(async (url, options) => {
    if (url === '/api/tasks/task-a') {
      detailSignal = options?.signal;
      return new Promise((_resolve, reject) => {
        detailSignal?.addEventListener('abort', () => reject(new DOMException('Aborted', 'AbortError')), { once: true });
      });
    }
    return response(url === '/api/queue'
      ? { ...queue(), sync: version(++revision) }
      : page([{ ...task(stalled ? 'completed' : 'failed'), summary_only: stalled }], ++revision));
  });
  try {
    f.realtime.startRealtimeUpdates();
    f.sources[0].error(2);
    await flush();
    await f.advance(10000);
    stalled = false;
    await f.advance(5000);
    assert.equal(f.state.tasks[0]?.status, 'failed');
    assert.equal(detailSignal?.aborted, true);
    assert.equal(f.status.textContent, 'queue.realtimePolling');
  } finally { f.realtime.closeRealtimeUpdates(); }
});

test('a delayed queue response cannot leave completed tasks in the running queue', async () => {
  const f = realtimeFixture();
  await f.realtime.handleRealtimePayload({ type: 'snapshot', ...page([task('running')], 1), queue: queue([task('running')]) });
  let revision = 1, pendingQueue;
  f.fetchWith(async url => {
    const sync = version(++revision);
    if (url === '/api/queue') {
      pendingQueue = deferred();
      await pendingQueue.promise;
      return response({ ...queue(), sync });
    }
    return response({ tasks: [task()], sync });
  });
  try {
    f.realtime.startRealtimeUpdates();
    f.sources[0].error();
    for (let poll = 0; poll < 2; poll++) {
      await flush();
      pendingQueue.resolve();
      await flush();
      assert.equal(f.state.tasks[0].status, 'completed');
      assert.deepEqual(f.state.queue.running, []);
      if (poll === 0) await f.advance(5000);
    }
  } finally { f.realtime.closeRealtimeUpdates(); }
});

test('an aborted detail response cannot overwrite the next task snapshot', async () => {
  const f = fixture();
  f.load('./task-selection').initTaskSelectionFeature();
  f.state.selectedTaskId = 'task-a';
  f.state.tasks = [{ ...task(), summary_only: true }];
  const pending = deferred();
  f.fetchWith(() => pending.promise);
  const controller = new AbortController();
  const detail = f.methods.ensureSelectedTaskDetail('task-a', { signal: controller.signal });
  controller.abort();
  f.state.tasks = [task('failed')];
  pending.resolve(response({ task: task() }));
  await assert.rejects(detail, { name: 'AbortError' });
  assert.equal(f.state.tasks[0].status, 'failed');
});

test('a non-cancellable bridge refresh cannot retain the fallback lock after timeout', async () => {
  const f = realtimeFixture();
  const pending = deferred();
  const refreshTasks = f.methods.refreshTasks;
  f.methods.refreshTasks = () => pending.promise;
  try {
    f.realtime.startRealtimeUpdates();
    f.sources[0].error();
    await flush();
    await f.advance(10000);
    f.methods.refreshTasks = refreshTasks;
    f.setTask(task('failed'));
    await f.advance(5000);
    assert.equal(f.state.tasks[0]?.status, 'failed');
    assert.equal(f.status.textContent, 'queue.realtimePolling');
    pending.resolve();
    await flush();
    assert.equal(f.state.tasks[0]?.status, 'failed');
  } finally { pending.resolve(); f.realtime.closeRealtimeUpdates(); }
});

test('a late selected detail cannot overwrite a retry received through SSE', async () => {
  const f = fixture();
  f.load('./task-selection').initTaskSelectionFeature();
  f.methods.updateTaskInState = f.load('./runtime-feedback').updateTaskInState;
  f.state.selectedTaskId = 'task-a';
  const pending = deferred();
  f.fetchWith(() => pending.promise);
  const old = { ...task('failed'), updated_at: '2026-10-13T10:00:00Z' };
  const snapshot = f.realtime.handleRealtimePayload({ type: 'snapshot', ...page([{ ...old, summary_only: true }], 1), queue: queue() });
  await flush();
  await f.realtime.handleRealtimePayload({ type: 'task', sync: version(2), task: { ...task('queued'), updated_at: '2026-10-13T10:01:00Z' } });
  pending.resolve(response({ task: old }));
  await snapshot;
  assert.equal(f.state.tasks[0].status, 'queued');
});

test('a concurrent summary refresh still restores the selected task full inputs', async () => {
  const f = fixture();
  const summary = { task_id: 'task-a', status: 'completed', mode: 'edit', summary_only: true, updated_at: '2026-10-15T01:00:00Z' };
  const full = { ...summary, summary_only: false, prompt: 'Full synthetic prompt', local_input_files: [{ kind: 'asset', id: 'reference' }], reference_files: [{ id: 'notes', family: 'text', filename: 'notes.txt' }] };
  Object.assign(f.state, { tasks: [summary], taskInputRestoreSeq: 0, images: [], referenceFiles: [], mode: 'generate' });
  let prompt = '';
  Object.assign(f.methods, Object.fromEntries(['closePromptPopover', 'updateTaskSelectionVisuals', 'renderReferenceFiles', 'renderImageStrip', 'updateRequestPreview', 'revokeUploadPreviewUrls', 'showTaskOutputSettings', 'clearTaskParameterInspection'].map(name => [name, () => {}])));
  Object.assign(f.methods, { isOutputSettingsLocked: () => true, getPromptText: () => prompt, applyTaskToForm: value => { prompt = value.prompt || ''; }, taskRequestPreviewPayload: () => null, taskInputUrls: () => [] });
  document.getElementById = () => null;
  f.load('./task-selection').initTaskSelectionFeature();
  const pending = deferred();
  f.fetchWith(() => pending.promise);
  const selecting = f.methods.selectTask('task-a');
  const snapshot = f.methods.applyTasksSnapshot([{ ...summary }], { sync: version(2) });
  pending.resolve(response({ task: full }));
  await Promise.all([selecting, snapshot]);
  assert.equal(prompt, full.prompt);
  assert.deepEqual(f.state.images, full.local_input_files);
  assert.equal(f.state.referenceFiles[0]?.id, 'notes');
});

test('a newer summary causes detail to be refetched instead of returning a summary', async () => {
  const f = fixture();
  f.load('./task-selection').initTaskSelectionFeature();
  const old = { ...task('failed'), summary_only: true, updated_at: '2026-10-15T01:00:00Z' };
  const fresh = { ...old, status: 'completed', updated_at: '2026-10-15T01:01:00Z' };
  f.state.tasks = [old]; f.state.selectedTaskId = 'task-a';
  const pending = deferred(); let reads = 0;
  f.fetchWith(() => ++reads === 1 ? pending.promise : Promise.resolve(response({ task: { ...fresh, summary_only: false } })));
  const detail = f.methods.ensureSelectedTaskDetail();
  f.state.tasks = [fresh];
  pending.resolve(response({ task: { ...old, summary_only: false } }));
  const result = await detail;
  assert.equal(reads, 2);
  assert.equal(result.status, 'completed');
  assert.equal(result.summary_only, false);
  f.state.tasks = [{ ...fresh }]; reads = 0;
  f.fetchWith(async () => { reads++; return response({ task: { ...old, summary_only: false } }); });
  await assert.rejects(f.methods.ensureSelectedTaskDetail(), /status.taskChangedDuringLoad/);
  assert.equal(reads, 2, 'repeated stale responses must not cause an unbounded retry loop');
});

test('obsolete queue read failures cannot overwrite a healthy snapshot but current failures remain visible', async () => {
  const f = realtimeFixture();
  let rejectOld;
  f.fetchWith(() => new Promise((_resolve, reject) => { rejectOld = reject; }));
  try {
    f.realtime.startRealtimeUpdates();
    const oldRead = f.realtime.refreshQueue();
    f.sources[0].open();
    f.sources[0].message({ type: 'snapshot', ...page([task()], 10), queue: queue() });
    await flush();
    rejectOld(new TypeError('Failed to fetch'));
    await oldRead;
    assert.equal(f.status.textContent, '');
    assert.equal(f.state.tasks[0].status, 'completed');
    f.fetchWith(async () => { throw new TypeError('Current read failed'); });
    await f.realtime.refreshQueue();
    assert.equal(f.status.textContent, 'Current read failed');
    f.fetchWith(async () => response({ ...queue(), updated_at: 'new', sync: version(11) }));
    f.methods.refreshTasks = async () => { throw new Error('Task refresh failed'); };
    await f.realtime.refreshQueue();
    assert.equal(f.status.textContent, 'Task refresh failed');
  } finally { f.realtime.closeRealtimeUpdates(); }
});

test('push recovery retires old polling and an idle timeout cannot report a new error', async () => {
  const f = realtimeFixture();
  const signals = [];
  f.fetchWith((_url, options) => new Promise((_resolve, reject) => {
    signals.push(options.signal);
    options.signal.addEventListener('abort', () => reject(options.signal.reason), { once: true });
  }));
  try {
    f.realtime.startRealtimeUpdates();
    f.sources[0].error();
    await flush();
    f.sources[0].open();
    f.sources[0].message({ type: 'snapshot', ...page([task()], 5), queue: queue() });
    await flush();
    assert.equal(signals[0].aborted, true);
    await f.advance(10000);
    f.sources[0].heartbeat();
    assert.equal(f.state.tasks[0].status, 'completed');
    assert.equal(f.status.textContent, '');
    assert.equal(f.sources[0].readyState, 1);
  } finally { f.realtime.closeRealtimeUpdates(); }
});

test('browsers without EventSource still keep their task state current', async () => {
  const f = realtimeFixture();
  window.EventSource = undefined;
  try {
    assert.equal(f.realtime.startRealtimeUpdates(), false);
    await flush();
    f.setTask(task('completed'));
    await f.advance(5000);
    assert.equal(f.state.tasks[0].status, 'completed');
    assert.equal(f.sources.length, 0);
  } finally { f.realtime.closeRealtimeUpdates(); }
});

test('startup loads HTTP history even when EventSource opens without a snapshot', async () => {
  const f = fixture();
  f.fetchWith(async () => response(page([task()], 1)));
  f.load('./boot').bootWebUI(f.state, {}, f.methods);
  await flush();
  assert.equal(f.state.tasks[0].status, 'completed');
  assert.ok(f.calls.includes('queue'));
  assert.equal(f.state.realtimeSnapshotNeedsArchiveMigration, false);
});

test('late startup and recovery failures cannot overwrite a newer healthy push snapshot', async () => {
  const f = realtimeFixture();
  let rejectRead;
  f.fetchWith(() => new Promise((_resolve, reject) => { rejectRead = reject; }));
  window.startRealtimeUpdates = f.realtime.startRealtimeUpdates;
  try {
    f.load('./boot').bootWebUI(f.state, {}, f.methods);
    f.sources[0].open();
    f.sources[0].message({ type: 'snapshot', ...page([task()], 10), queue: queue() });
    await flush();
    rejectRead(new TypeError('obsolete startup failure'));
    await flush();
    assert.equal(f.status.textContent, '');

    f.fetchWith(async url => response(url === '/api/queue'
      ? { ...queue(), sync: version(11) } : page([task()], 12)));
    f.sources[0].error();
    await flush();
    f.fetchWith(() => new Promise((_resolve, reject) => { rejectRead = reject; }));
    f.sources[0].open();
    f.sources[0].message({ type: 'snapshot', ...page([task()], 20), queue: queue() });
    await flush();
    rejectRead(new TypeError('obsolete recovery failure'));
    await flush();
    assert.equal(f.status.textContent, '');
    assert.equal(f.state.tasks[0].status, 'completed');
  } finally { f.realtime.closeRealtimeUpdates(); }
});

test('a task update also retires a failed sidebar read without replacing its array', async () => {
  const f = fixture();
  f.state.tasks = [task('running')];
  const tasks = f.state.tasks;
  let rejectRead;
  f.fetchWith(() => new Promise((_resolve, reject) => { rejectRead = reject; }));
  const read = f.methods.refreshTasks();
  await f.realtime.handleRealtimePayload({ type: 'task', sync: version(10), task: task('running') });
  assert.equal(f.state.tasks, tasks);
  rejectRead(new TypeError('obsolete sidebar failure'));
  assert.equal(await read, false);
});

test('a queue reconciliation failure after a newer push cannot overwrite its status', async () => {
  const f = realtimeFixture();
  let rejectRefresh;
  f.methods.refreshTasks = () => new Promise((_resolve, reject) => { rejectRefresh = reject; });
  f.fetchWith(async () => response({ ...queue(), updated_at: 'changed', sync: version(1) }));
  const read = f.realtime.refreshQueue(); await flush();
  await f.realtime.handleRealtimePayload({ type: 'snapshot', ...page([task()], 2), queue: queue() });
  rejectRefresh(new Error('obsolete reconciliation failure')); await read;
  assert.equal(f.status.textContent, '');
});

test('startup restores the composer before history handoffs and task requests', async () => {
  const f = fixture();
  const restored = deferred();
  const order = [];
  f.methods.restoreComposerNavigationDraft = () => { order.push('restore'); return restored.promise; };
  f.methods.restoreHistoryReferenceHandoff = () => order.push('reference');
  f.methods.restoreHistoryTaskReuseHandoff = () => order.push('reuse');
  f.load('./boot').bootWebUI(f.state, {}, f.methods);
  assert.deepEqual(order, ['restore']);
  assert.equal(f.calls.length, 0);
  restored.resolve();
  await flush();
  assert.deepEqual(order, ['restore', 'reference', 'reuse']);
  assert.ok(f.calls.includes('queue'));
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

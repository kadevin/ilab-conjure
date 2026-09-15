import assert from "node:assert/strict";
import test from "node:test";

function setupQueueTransition() {
  const waitingTask = {
    task_id: "waiting-to-running",
    prompt: "queue transition",
    status: "queued",
    created_at: "2026-07-29T00:00:00Z",
    updated_at: "2026-07-29T00:00:00Z",
    total_count: 1,
  };
  const runningTask = {
    ...waitingTask,
    status: "running",
    started_at: "2026-07-29T00:00:01Z",
    updated_at: "2026-07-29T00:00:01Z",
    channel_id: "codex:0",
  };
  const state: any = {
    tasks: [waitingTask],
    selectedTaskId: null,
    queue: {
      waiting: [{ ...waitingTask, queue_position: 1 }],
      running: [],
      summary: {
        waiting_count: 1,
        running_count: 0,
        channel_count: 1,
        usable_channel_count: 1,
      },
    },
    queueRequestSeq: 0,
    queueDispatchSyncTimerId: null,
    queueRenderKey: null,
  };
  const renderedStates: Array<{ status: string; waiting: string[]; running: string[] }> = [];
  const bridge: any = {
    state,
    els: {},
    constants: { defaultDocumentTitle: "iLab CONJURE" },
    boot() {},
    methods: {
      cleanupSessionSelections() {},
      markTaskViewed() {},
      notifyTaskUpdate() {},
      renderArchiveButton() {},
      renderArchiveModal() {},
      renderPreview() {},
      renderTasks() {
        renderedStates.push({
          status: String(state.tasks[0]?.status || ""),
          waiting: state.queue.waiting.map((task: any) => String(task.task_id)),
          running: state.queue.running.map((task: any) => String(task.task_id)),
        });
      },
      setStatus() {},
      taskHasViewableUpdate() {
        return false;
      },
      updateDocumentTitle() {},
      updateTaskInState(task: any) {
        const index = state.tasks.findIndex((item: any) => String(item.task_id) === String(task.task_id));
        if (index < 0) state.tasks.unshift(task);
        else state.tasks[index] = task;
        return true;
      },
    },
  };
  (globalThis as any).window = {
    __codexImageWebUI: bridge,
    clearTimeout,
    setTimeout,
  };
  return { state, bridge, renderedStates, waitingTask, runningTask };
}

test("waiting-to-running queue updates render one consistent task-card state", async () => {
  const { runningTask, renderedStates } = setupQueueTransition();
  const { handleRealtimePayload } = await import(
    "../../codex_image/webui/frontend/src/queue"
  );
  await handleRealtimePayload({
    type: "queue",
    queue: {
      waiting: [],
      running: [runningTask],
      summary: {
        waiting_count: 0,
        running_count: 1,
        channel_count: 1,
        usable_channel_count: 1,
      },
    },
  } as any);

  assert.deepEqual(renderedStates, [
    {
      status: "running",
      waiting: [],
      running: ["waiting-to-running"],
    },
  ]);
});

test("REST queue refresh reconciles the card and preview before rendering", async () => {
  const { state, bridge, runningTask, renderedStates } = setupQueueTransition();
  const previews: string[] = [];
  bridge.methods.renderPreview = () => previews.push(state.tasks[0].status);
  (globalThis as any).fetch = async () => new Response(JSON.stringify({
    waiting: [], running: [runningTask], summary: { waiting_count: 0, running_count: 1 },
  }));
  const { refreshQueue } = await import("../../codex_image/webui/frontend/src/queue");
  await refreshQueue();
  assert.deepEqual(renderedStates.map(frame => frame.status), ["running"]);
  assert.deepEqual(previews, ["running"]);
});

test("an empty queue event reconciles tasks that finished between stream checks", async () => {
  const { state, bridge, waitingTask } = setupQueueTransition();
  let refreshed = false;
  bridge.methods.refreshTasks = async () => {
    await Promise.resolve();
    refreshed = true;
    state.tasks = [{ ...waitingTask, status: "failed", error: "HTTP 404 model_not_found" }];
  };
  const { handleRealtimePayload } = await import("../../codex_image/webui/frontend/src/queue");
  await handleRealtimePayload({ type: "queue", queue: {
    waiting: [], running: [], summary: {}, updated_at: "2026-09-14T06:15:42Z",
  } } as any);
  assert.equal(refreshed, true);
  assert.equal(state.tasks[0].status, "failed");
  assert.equal(state.queue.running.length, 0);
});

test("terminal local submissions are retained outside the active queue groups", async () => {
  const { bridge, state } = setupQueueTransition();
  state.queue = { running: [], waiting: [] };
  const previousDocument = globalThis.document;
  (globalThis as any).document = { addEventListener() {} };
  try {
    const { initTaskListRenderFeature } = await import("../../codex_image/webui/frontend/src/task-list-render");
    initTaskListRenderFeature();
    const terminal = ["failed", "completed", "cancelled"].map(status => ({
      task_id: `pending-${status}`, status, local_pending: true,
    }));
    terminal.forEach(task => assert.equal(bridge.methods.isAlwaysVisibleTask(task), false));
    const submitting = { task_id: "pending-submit", status: "submitting", local_pending: true };
    const cancelling = { task_id: "server-cancelling", status: "cancelling" };
    assert.equal(bridge.methods.isAlwaysVisibleTask(submitting), true);
    assert.equal(bridge.methods.isAlwaysVisibleTask(cancelling), true);
    assert.deepEqual(bridge.methods.activeTaskSections([...terminal, submitting, cancelling]), {
      running: [cancelling], waiting: [submitting],
    });
    assert.equal(terminal[0].local_pending, true);
  } finally { (globalThis as any).document = previousDocument; }
});

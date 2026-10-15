import assert from "node:assert/strict";
import test from "node:test";

import { refreshHistoryForRealtimeTask } from "../../codex_image/webui/frontend/src/history-realtime";

test("terminal task updates preserve a history window scrolled away from the top", async () => {
  const scroller = { scrollTop: 420 };
  const calls: string[] = [];

  await refreshHistoryForRealtimeTask({
    task: { task_id: "finished-task", status: "completed" },
    scroller,
    loadSummary: async () => {
      calls.push("summary");
    },
    reloadNewestWindow: async () => {
      calls.push("reload");
      scroller.scrollTop = 0;
    },
    refreshCurrentWindow: async () => { calls.push("current"); },
    upsertTask: (taskId) => {
      calls.push(`upsert:${taskId}`);
    },
  });

  assert.deepEqual(calls, ["upsert:finished-task", "summary"]);
  assert.equal(scroller.scrollTop, 420);
});

test("terminal task updates refresh the newest window when already at the top", async () => {
  const calls: string[] = [];

  await refreshHistoryForRealtimeTask({
    task: { task_id: "finished-task", status: "completed" },
    scroller: { scrollTop: 0 },
    loadSummary: async () => {
      calls.push("summary");
    },
    reloadNewestWindow: async () => {
      calls.push("reload");
    },
    refreshCurrentWindow: async () => { calls.push("current"); },
    upsertTask: (taskId) => {
      calls.push(`upsert:${taskId}`);
    },
  });

  assert.deepEqual(calls, ["upsert:finished-task", "summary", "reload"]);
});

test("fallback refreshes mounted cards without resetting a scrolled history window", async () => {
  const scroller = { scrollTop: 420 };
  const calls: string[] = [];
  await refreshHistoryForRealtimeTask({
    task: undefined, scroller,
    loadSummary: async () => { calls.push("summary"); },
    reloadNewestWindow: async () => { calls.push("reload"); scroller.scrollTop = 0; },
    refreshCurrentWindow: async () => { calls.push("current"); },
    upsertTask: () => { calls.push("upsert"); },
  });
  assert.deepEqual(calls, ["summary", "current"]);
  assert.equal(scroller.scrollTop, 420);
});

test("scrolling while summary loads prevents a fallback from resetting to the top", async () => {
  const scroller = { scrollTop: 0 };
  const calls: string[] = [];
  await refreshHistoryForRealtimeTask({
    task: undefined, scroller,
    loadSummary: async () => { scroller.scrollTop = 420; },
    reloadNewestWindow: async () => { calls.push("reload"); },
    refreshCurrentWindow: async () => { calls.push("current"); },
    upsertTask: () => {},
  });
  assert.deepEqual(calls, ["current"]);
});

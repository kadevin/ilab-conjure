import assert from "node:assert/strict";
import test from "node:test";
import { updateTaskElapsedDisplays } from "../../codex_image/webui/frontend/src/runtime-feedback";

test("elapsed tick visits each mounted card once with at most one scan per root", () => {
  const previousWindow = globalThis.window, previousElement = globalThis.HTMLElement;
  let rootQueries = 0, cardQueries = 0;
  class Element {
    dataset: any; children: Element[];
    constructor(id: string, children: Element[] = []) { this.dataset = { taskId: id }; this.children = children; }
    querySelector() { cardQueries++; return null; }
    querySelectorAll(selector: string) {
      if (selector === ".task-card[data-task-id]") { rootQueries++; return this.children; }
      return [];
    }
  }
  globalThis.HTMLElement = Element as any;
  const cards = Array.from({ length: 3000 }, (_, i) => new Element(`id-${i}`));
  const root = new Element("root", cards), nested = new Element("nested", cards.slice(0, 100));
  globalThis.window = { __codexImageWebUI: { state: { tasks: cards.map(c => ({ task_id: c.dataset.taskId, status: "queued" })) }, els: { taskList: root, taskActiveList: nested }, methods: {} } } as any;
  try {
    updateTaskElapsedDisplays();
    assert.equal(rootQueries, 2);
    assert.equal(cardQueries, 3000 * 4);
    (globalThis.window as any).__codexImageWebUI.state.tasks = [];
    updateTaskElapsedDisplays();
    assert.equal(rootQueries, 2);
  } finally { globalThis.window = previousWindow; globalThis.HTMLElement = previousElement; }
});

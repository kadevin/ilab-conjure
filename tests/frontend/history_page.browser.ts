/** Real-page acceptance runner. Serve with /qa, /qa-baseline and 675 synthetic tasks.
 * The iframe uses the application's actual history bundle and backend. No user data.
 */
import { loadAcceptanceFrame, prepareFixtureOrigin } from "./browser_acceptance";

const variant = new URLSearchParams(location.search).get("variant") || "current";
const frame = document.querySelector<HTMLIFrameElement>("#historyFrame")!;
const output = document.querySelector<HTMLElement>("#results")!;
const results: Array<{ name: string; passed: boolean; detail?: unknown }> = [];
const errors: string[] = [];
const pause = (ms = 60) => new Promise(done => setTimeout(done, ms));
async function until(check: () => boolean, name: string, timeout = 12000) {
  const end = Date.now() + timeout;
  while (!check()) {
    if (errors.length) throw new Error(`Application runtime failed: ${errors.join("; ")}`);
    if (Date.now() > end) throw new Error(`Timeout: ${name}`);
    await pause(40);
  }
  await pause();
}
function check(name: string, condition: boolean, detail?: unknown) {
  results.push({ name, passed: condition, detail });
  output.textContent = JSON.stringify({ variant, running: true, results });
  if (!condition) throw new Error(name + ": " + JSON.stringify(detail));
}
async function run() {
  await prepareFixtureOrigin();
  localStorage.removeItem("codex-image-history-location");
  localStorage.setItem("codex-image-locale-preference", "en");
  await loadAcceptanceFrame(frame, `${variant === "baseline" ? "/qa-baseline" : "/qa-history"}?sort=oldest&view=list`, errors);
  const w = frame.contentWindow!, d = frame.contentDocument!;
  const find = (selector: string) => d.querySelector<HTMLElement>(selector)!;
  const list = find("#historyTaskList");
  const cards = () => Array.from(list.querySelectorAll<HTMLElement>(".history-task-card"));
  const ids = () => cards().map(c => c.dataset.historyTaskCardId!);
  const num = (id: string) => Number(id.split("-").at(-1));
  const click = (selector: string, modifiers: MouseEventInit = {}) => { const el = find(selector); if (!el) throw new Error("Missing control: " + selector); el.dispatchEvent(new w.MouseEvent("click", { bubbles: true, ...modifiers })); };
  const key = (key: string, options: KeyboardEventInit = {}) => w.dispatchEvent(new w.KeyboardEvent("keydown", { key, bubbles: true, ...options }));
  const detail = find("#historyDetail");
  await until(() => cards().length >= 50, "first page");
  check("shared shell and desktop list loaded", Boolean(find(".history-top-nav")) && w.innerWidth === 1440 && cards().length >= 50);
  click('[data-history-task-id="qa-history-0000"]');
  await until(() => detail.dataset.historyDetailMode === "task", "single detail");
  const methods = (w as any).__codexImageWebUI.methods;
  const reuseControl = () => find('[data-history-reuse-task="qa-history-0000"]');
  reuseControl().focus({ preventScroll: true });
  const changedDetail = await fetch("/api/tasks/qa-history-0000/outputs/1/selected", {
    method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ selected: true }),
  });
  if (!changedDetail.ok) throw new Error("Could not update synthetic detail");
  await methods.refreshTasks();
  check("background polling updates the open detail and preserves its focus", Boolean(detail.querySelector(".history-detail-output-card.selected"))
    && d.activeElement === reuseControl());
  click('[data-history-task-id="qa-history-0001"]', { ctrlKey: true });
  check("Ctrl selection switches detail to bulk panel", detail.dataset.historyDetailMode === "selection" && cards().filter(c => c.classList.contains("selected")).length === 2);
  await (w as any).__codexImageWebUI.methods.refreshTasks();
  check("background refresh at the top preserves multi-selection", list.scrollTop === 0
    && cards().slice(0, 2).every(c => c.classList.contains("selected"))
    && detail.dataset.historyDetailMode === "selection");
  const originalFetch = w.fetch;
  const focusedTop = () => find('[data-history-task-id="qa-history-0001"]');
  focusedTop().focus({ preventScroll: true });
  const beforeFailure = cards()[0];
  try {
    w.fetch = (input, options) => String(input).startsWith("/api/task-history/tasks?")
      ? Promise.reject(new TypeError("synthetic background failure")) : originalFetch(input, options);
    let failed = false;
    try { await methods.refreshTasks(); } catch { failed = true; }
    check("failed background top reload preserves cards, selection and focus", failed && cards()[0] === beforeFailure
      && cards().slice(0, 2).every(card => card.classList.contains("selected")) && d.activeElement === focusedTop());
  } finally { w.fetch = originalFetch; }
  await methods.refreshTasks();
  check("successful background top reload restores the focused task control", d.activeElement === focusedTop());
  let releasePage: (() => void) | undefined;
  let concurrentRefresh: Promise<void> | undefined;
  try {
    w.fetch = async (input, options) => {
      const response = await originalFetch(input, options);
      if (!String(input).startsWith("/api/task-history/tasks?")) return response;
      return new Promise<Response>(resolve => { releasePage = () => resolve(response); });
    };
    concurrentRefresh = methods.refreshTasks();
    await until(() => Boolean(releasePage), "delayed background page");
    const favoriteSelector = '[data-history-favorite-task="qa-history-0001"]';
    click(favoriteSelector);
    await until(() => find(favoriteSelector).getAttribute("aria-pressed") === "true", "favorite edited during refresh");
    releasePage!(); await concurrentRefresh;
    check("late background page preserves a newer favorite edit", find(favoriteSelector).getAttribute("aria-pressed") === "true"
      && cards().slice(0, 2).every(card => card.classList.contains("selected")));
  } finally {
    w.fetch = originalFetch;
    releasePage?.();
    await concurrentRefresh;
  }
  list.scrollTop = 380;
  const focusedTaskId = "qa-history-0005";
  const focusedControl = () => find(`[data-history-task-id="${focusedTaskId}"]`);
  const beforeRefresh = focusedControl();
  beforeRefresh.focus({ preventScroll: true });
  const beforeScroll = list.scrollTop;
  const favoriteResponse = await fetch("/api/task-history/organize", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ task_ids: [focusedTaskId], favorite: true }),
  });
  if (!favoriteResponse.ok) throw new Error("Could not update synthetic history task");
  await (w as any).__codexImageWebUI.methods.refreshTasks();
  check("mounted update retains keyboard focus, scroll and selection", focusedControl() !== beforeRefresh
    && d.activeElement === focusedControl() && Math.abs(list.scrollTop - beforeScroll) <= 2
    && cards().filter(c => c.classList.contains("selected")).length === 2);
  const afterRefresh = focusedControl();
  await (w as any).__codexImageWebUI.methods.refreshTasks();
  check("unchanged polling retains the existing focused control", focusedControl() === afterRefresh && d.activeElement === afterRefresh);
  list.scrollTop = 0;
  const seen = new Set(ids()); let anchorDelta: number | null = null;
  for (let n = 0; n < 20 && num(ids().at(-1)!) < 674; n++) {
    const last = ids().at(-1), count = cards().length;
    list.scrollTop = list.scrollHeight;
    const top = list.getBoundingClientRect().top;
    const anchor = cards().find(c => c.getBoundingClientRect().bottom >= top)!;
    const offset = anchor.getBoundingClientRect().top - top, anchorId = anchor.dataset.historyTaskCardId;
    list.dispatchEvent(new w.Event("scroll"));
    await until(() => ids().at(-1) !== last, "next page");
    ids().forEach(id => seen.add(id));
    check(`forward window ${n + 1}: bounded, ordered, unique`, cards().length <= 300 && new Set(ids()).size === ids().length && ids().every((id, i, all) => i === 0 || num(id) === num(all[i - 1]) + 1));
    if (count === 300 && anchorDelta === null) {
      const retained = cards().find(c => c.dataset.historyTaskCardId === anchorId);
      anchorDelta = retained ? Math.abs(retained.getBoundingClientRect().top - list.getBoundingClientRect().top - offset) : Infinity;
      check("forward trim preserves visible anchor within 2px", anchorDelta <= 2, anchorDelta);
    }
  }
  check("all 675 tasks reachable forward", seen.size === 675, seen.size);
  check("off-window selection survives trimming", detail.dataset.historyDetailMode === "selection" && /2/.test(find("#historySelectionDockCount").textContent || ""));
  for (let n = 0; n < 20 && num(ids()[0]) > 0; n++) {
    const first = ids()[0]; list.scrollTop = 0; list.dispatchEvent(new w.Event("scroll"));
    await until(() => ids()[0] !== first, "previous page");
    check(`reverse window ${n + 1}: bounded, ordered, unique`, cards().length <= 300 && new Set(ids()).size === ids().length && ids().every((id, i, all) => i === 0 || num(id) === num(all[i - 1]) + 1));
  }
  check("selected cards restored when window returns", cards().slice(0, 2).every(c => c.classList.contains("selected")));
  key("a", { ctrlKey: true });
  check("Ctrl+A selects only mounted 300 tasks", cards().length === 300 && cards().every(c => c.classList.contains("selected")) && /300/.test(find("#historySelectionDockCount").textContent || ""));
  click("[data-history-bulk-clear]");
  click('[data-history-view="grid"]'); await pause(150);
  check("grid view lays out the same window", cards().length === 300 && list.classList.contains("history-view-grid") && Number.parseFloat(cards()[0].style.getPropertyValue("--history-task-card-width")) > 0);
  click('[data-history-task-id="qa-history-0000"]'); await until(() => detail.dataset.historyDetailMode === "task", "detail in grid");
  const card = cards()[0]; card.dispatchEvent(new w.MouseEvent("contextmenu", { bubbles: true, clientX: 450, clientY: 200 }));
  check("context menu opens", !find(".history-context-menu").classList.contains("hidden")); key("Escape");
  check("one Escape closes menu and preserves detail", find(".history-context-menu").classList.contains("hidden") && detail.dataset.historyDetailMode === "task");
  click("[data-history-lightbox-url]"); await until(() => Boolean(find(".history-lightbox:not([hidden])")), "lightbox"); key("Escape");
  check("lightbox closes without clearing task", !find(".history-lightbox:not([hidden])") && detail.dataset.historyDetailMode === "task");
  key("Escape"); check("closing detail clears URL task", detail.dataset.historyDetailMode === "management" && !new URL(w.location.href).searchParams.has("task"));
  const search = find("#historySearch") as HTMLInputElement;
  search.value = "Synthetic QA history 0674"; search.dispatchEvent(new w.Event("input", { bubbles: true }));
  await until(() => cards().length === 1 && ids()[0] === "qa-history-0674", "search");
  check("search updates URL and filtered tasks", new URL(w.location.href).searchParams.get("q") === search.value);
  click("[data-history-clear-all-filters]"); await until(() => cards().length >= 50, "clear filters");
  check("clear filters retains sort and grid view", new URL(w.location.href).searchParams.get("sort") === "oldest" && list.classList.contains("history-view-grid"));
  click("[data-history-open-backup]"); await until(() => !find("#historyBackupDialog").hidden, "backup dialog");
  check("backup modal isolates page", find(".history-page").inert && Boolean(d.activeElement?.closest("#historyBackupDialog")));
  key("Escape"); check("backup Escape restores page and focus", find("#historyBackupDialog").hidden && !find(".history-page").inert && Boolean(d.activeElement?.matches("[data-history-open-backup]")));
  click("[data-history-open-import]"); await until(() => !find("#historyImportDialog").hidden, "import dialog"); key("Escape");
  check("import opens and closes without starting upload", find("#historyImportDialog").hidden);
  for (const width of [1440, 390]) {
    frame.style.width = `${width}px`; frame.style.height = width === 390 ? "844px" : "900px"; await pause(250);
    for (const theme of ["light", "dark"]) {
      d.documentElement.dataset.theme = theme; await pause();
      check(`${width}px ${theme}: no page overflow`, d.documentElement.scrollWidth <= w.innerWidth + 1, { page: d.documentElement.scrollWidth, viewport: w.innerWidth });
    }
  }
  click("[data-history-enter-selection-mode]"); click("[data-history-task-id]");
  check("mobile touch mode toggles task selection", find(".history-page").classList.contains("history-selection-mode"));
  list.scrollTop = 0;
  await (w as any).__codexImageWebUI.methods.refreshTasks();
  check("background top refresh keeps mobile selection mode", find(".history-page").classList.contains("history-selection-mode")
    && cards().filter(c => c.classList.contains("selected")).length === 1);
  click("[data-history-open-selection-actions]"); key("Escape");
  check("mobile drawer dismissal retains selection", /1/.test(find("#historySelectionDockCount").textContent || "") && !find(".history-page").classList.contains("history-detail-open"));
  check("no uncaught runtime errors", errors.length === 0, errors);
}
void run().catch(error => { results.push({ name: "runner", passed: false, detail: String(error) }); }).finally(async () => {
  const report = { variant, passed: results.length > 0 && results.every(r => r.passed) && errors.length === 0, results, errors };
  output.textContent = JSON.stringify(report); await fetch("/qa-results", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(report) });
});

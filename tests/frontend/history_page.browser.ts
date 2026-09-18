/** Real-page acceptance runner. Serve with /qa, /qa-baseline and 675 synthetic tasks.
 * The iframe uses the application's actual history bundle and backend. No user data.
 */
const variant = new URLSearchParams(location.search).get("variant") || "current";
const frame = document.querySelector<HTMLIFrameElement>("#historyFrame")!;
const output = document.querySelector<HTMLElement>("#results")!;
const results: Array<{ name: string; passed: boolean; detail?: unknown }> = [];
const errors: string[] = [];
const pause = (ms = 60) => new Promise(done => setTimeout(done, ms));
async function until(check: () => boolean, name: string, timeout = 12000) {
  const end = Date.now() + timeout;
  while (!check()) { if (Date.now() > end) throw new Error(`Timeout: ${name}`); await pause(40); }
  await pause();
}
function check(name: string, condition: boolean, detail?: unknown) {
  results.push({ name, passed: condition, detail });
  output.textContent = JSON.stringify({ variant, running: true, results });
  if (!condition) throw new Error(name + ": " + JSON.stringify(detail));
}
async function run() {
  localStorage.removeItem("codex-image-history-location");
  localStorage.setItem("codex-image-locale-preference", "en");
  frame.src = `${variant === "baseline" ? "/qa-baseline" : "/history"}?sort=oldest&view=list`;
  await new Promise(done => frame.addEventListener("load", done, { once: true }));
  const w = frame.contentWindow!, d = frame.contentDocument!;
  w.addEventListener("error", event => errors.push(event.message));
  w.addEventListener("unhandledrejection", event => errors.push(String(event.reason)));
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
  click('[data-history-task-id="qa-history-0001"]', { ctrlKey: true });
  check("Ctrl selection switches detail to bulk panel", detail.dataset.historyDetailMode === "selection" && cards().filter(c => c.classList.contains("selected")).length === 2);
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
  click("[data-history-open-selection-actions]"); key("Escape");
  check("mobile drawer dismissal retains selection", /1/.test(find("#historySelectionDockCount").textContent || "") && !find(".history-page").classList.contains("history-detail-open"));
  check("no uncaught runtime errors", errors.length === 0, errors);
}
void run().catch(error => { results.push({ name: "runner", passed: false, detail: String(error) }); }).finally(async () => {
  const report = { variant, passed: results.every(r => r.passed), results, errors };
  output.textContent = JSON.stringify(report); await fetch("/qa-results", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(report) });
});

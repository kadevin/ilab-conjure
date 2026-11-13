import { loadAcceptanceFrame, prepareFixtureOrigin } from "./browser_acceptance";

const frame = document.querySelector<HTMLIFrameElement>("#historyFrame")!;
const output = document.querySelector<HTMLElement>("#results")!;
const errors: string[] = [];
const failures: string[] = [];
let assertions = 0;

async function until(predicate: () => boolean, label: string): Promise<void> {
  const deadline = Date.now() + 6000;
  while (!predicate()) {
    if (Date.now() >= deadline) throw new Error(`Timed out: ${label}`);
    await new Promise(resolve => setTimeout(resolve, 25));
  }
}

function check(name: string, condition: boolean): void {
  assertions++;
  if (!condition) failures.push(name);
}

async function run(): Promise<void> {
  await prepareFixtureOrigin();
  await loadAcceptanceFrame(frame, "/qa-app", errors);
  const win = frame.contentWindow!;
  const doc = frame.contentDocument!;
  const find = <T extends HTMLElement = HTMLElement>(selector: string) => doc.querySelector<T>(selector)!;
  const taskId = "qa-history-0674";
  const prompt = "Synthetic QA history 0674";
  const cardSelector = `.task-card[data-task-id="${taskId}"]`;
  const deleteRequests: Array<{ path: string; reply: (response: Response) => void }> = [];
  const fetch = win.fetch.bind(win);
  win.fetch = (input, init) => {
    const url = new URL(input instanceof win.Request ? input.url : String(input), win.location.href);
    if (init?.method === "DELETE" && url.pathname.startsWith("/api/tasks/")) {
      return new Promise<Response>(reply => deleteRequests.push({ path: url.pathname, reply }));
    }
    return fetch(input, init);
  };

  const search = find<HTMLInputElement>("#taskSearch");
  search.dispatchEvent(new win.Event("paste", { bubbles: true }));
  search.value = prompt;
  search.dispatchEvent(new win.Event("input", { bubbles: true }));
  await until(() => Boolean(find(cardSelector)), "synthetic task card mounted");
  const card = find(cardSelector);
  if (!card?.getClientRects().length) throw new Error("Synthetic task card did not render");
  card.focus();

  const menuDelete = () => find<HTMLButtonElement>('[data-task-context-action="delete"]');
  const confirm = () => doc.querySelector<HTMLElement>(".confirm-popover:not(.hidden)");
  const cancel = "[data-confirm-popover-cancel]";
  const settle = () => new Promise<void>(resolve => setTimeout(resolve, 0));
  const openMenu = (card: HTMLElement) => {
    const { left, top } = card.getBoundingClientRect();
    card.dispatchEvent(new win.MouseEvent("contextmenu", { bubbles: true, clientX: left + 16, clientY: top + 16 }));
  };

  openMenu(card);
  menuDelete().click();
  await settle();
  check("one menu click opens the confirmation and keeps the card closed", Boolean(confirm())
    && !doc.querySelector(".task-context-menu:not(.hidden)")
    && !card.classList.contains("task-card-swipe-open"));
  if (!confirm()) return;
  check("confirmation identifies the clicked task and focuses Cancel", find(".confirm-popover-detail").textContent === prompt
    && doc.activeElement === find(cancel));
  check("opening confirmation does not delete", deleteRequests.length === 0);
  find(cancel).dispatchEvent(new win.KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
  await settle();
  check("Escape returns to the card without deleting", !confirm() && doc.activeElement === card && deleteRequests.length === 0);

  openMenu(card);
  menuDelete().click();
  await settle();
  const { state, methods } = win.__codexImageWebUI!;
  state.tasksRenderKey = null;
  methods.renderTasks();
  // Cancel in the gap between the old card's removal and the next render frame.
  const redrawPending = !card.isConnected && !find(cardSelector);
  find(cancel).click();
  await until(() => Boolean(find(cardSelector)), "replacement card mounted");
  const replacement = find(cardSelector);
  check(`cancelling during a redraw focuses the replacement card (gap=${redrawPending}, focus=${doc.activeElement?.tagName}#${doc.activeElement?.id}, attached=${card.isConnected})`,
    redrawPending && doc.activeElement === replacement && deleteRequests.length === 0);

  replacement.dispatchEvent(new win.KeyboardEvent("keydown", { key: "F10", shiftKey: true, bubbles: true }));
  menuDelete().click();
  await settle();
  find("[data-confirm-popover-confirm]").click();
  check("confirmation sends one delete request for the clicked task", deleteRequests.length === 1
    && deleteRequests[0]?.path === `/api/tasks/${taskId}`);

  state.tasksRenderKey = null;
  methods.renderTasks();
  await until(() => Boolean(find(cardSelector)), "card remounted during delete");
  openMenu(find(cardSelector));
  check("delete is disabled on a remounted card while its request is in flight", menuDelete().disabled);
  menuDelete().click();
  await settle();
  confirm()?.querySelector<HTMLButtonElement>("[data-confirm-popover-confirm]")?.click();
  check("reopening the menu cannot send a second delete", !confirm() && deleteRequests.length === 1);

  const failure = "QA task retained";
  deleteRequests.forEach(request => request.reply(new win.Response(JSON.stringify({ detail: failure }), { status: 409 })));
  await until(() => find("#statusText").textContent === failure, "failed delete settled");
  openMenu(find(cardSelector));
  check("failure unlocks deletion for another attempt", !menuDelete().disabled);
  menuDelete().click();
  await settle();
  check("an unlocked task can open its confirmation again", Boolean(confirm()));
  confirm()?.querySelector<HTMLButtonElement>(cancel)?.click();
}

void run().catch(error => { failures.push(String(error)); }).then(() => {
  output.textContent = JSON.stringify({ passed: !failures.length && !errors.length, assertions, failures, errors });
});

/** Synthetic acceptance for lazy provider replies and preview popover feedback. */
import { loadAcceptanceFrame, prepareFixtureOrigin } from "./browser_acceptance";

const frame = document.querySelector<HTMLIFrameElement>("#historyFrame")!;
const output = document.querySelector<HTMLElement>("#results")!;
const errors: string[] = [];
const failures: string[] = [];
let assertions = 0;
const pause = (ms = 80) => new Promise(resolve => setTimeout(resolve, ms));
function check(name: string, pass: boolean) { assertions++; if (!pass) failures.push(name); }

async function run() {
  await prepareFixtureOrigin();
  localStorage.clear();
  localStorage.setItem("codex-image-locale-preference", "zh-CN");
  await loadAcceptanceFrame(frame, "/qa-app", errors);
  const w = frame.contentWindow as any, d = frame.contentDocument!;
  const methods = w.__codexImageWebUI.methods;
  w.closeRealtimeUpdates?.();
  const find = <T extends HTMLElement = HTMLElement>(selector: string) => d.querySelector<T>(selector)!;
  const nativeFetch = w.fetch.bind(w);
  const requests: string[] = [];
  let responseMode = "ok", resolveSlow: ((value: Response) => void) | null = null;
  const payload = { version: 1, records: [{ status: 200, kind: "json", body: {
    id: "synthetic-provider-reply", usage: { total_tokens: 37 },
    data: [{ b64_json: "[omitted: binary data]", revised_prompt: "<img src=x onerror=alert(1)>" }],
    details: Array.from({ length: 120 }, (_, index) => ({ index, text: "Synthetic response detail" })),
  } }], omitted_records: 0 };
  const response = (value = payload) => new w.Response(JSON.stringify(value), { status: 200 });
  w.fetch = (url: any, options: any) => {
    if (!String(url).endsWith("/provider-responses")) return nativeFetch(url, options);
    requests.push(String(url));
    if (responseMode === "slow") return new Promise(resolve => { resolveSlow = resolve; });
    if (responseMode === "error") return Promise.resolve(new w.Response("{}", { status: 503 }));
    return Promise.resolve(response(responseMode === "missing" ? { ...payload, records: [] } : payload));
  };
  const task = { task_id: "qa-provider-reply", status: "completed", prompt: "Synthetic original prompt",
    prompt_for_model: "Synthetic submitted prompt", revised_prompt: "Synthetic optimized prompt",
    params: { size: "1024x1024" }, output_urls: ["/static/brand/favicon.svg"], total_count: 1, generated_count: 1 };
  methods.renderPreview(task);
  await pause();
  const anchor = find<HTMLButtonElement>("[data-prompt-popover-index]");
  if (!anchor) throw new Error("Preview prompt entry missing");
  anchor.click();
  await pause();
  check("opening comparison does not fetch diagnostic data", requests.length === 0);
  check("submitted prompt precedes provider response", [...d.querySelectorAll(".prompt-popover-body > details")]
    .map(e => e.classList.contains("prompt-popover-response")).join() === "false,true");
  find(".prompt-popover-response summary").click();
  await pause();
  check("preview forwards the actual task ID", requests[0] === "/api/tasks/qa-provider-reply/provider-responses");
  check("response contains provider usage", find(".prompt-response-json").textContent!.includes('"total_tokens": 37'));
  check("JSON is rendered as text", !find(".prompt-response-json").querySelector("img")
    && find(".prompt-response-json").textContent!.includes("<img src=x"));
  find(".prompt-popover-response summary").click(); await pause();
  find(".prompt-popover-response summary").click(); await pause();
  check("reopening loaded details does not refetch", requests.length === 1);
  frame.style.width = "390px";
  await pause();
  const resized = find(".prompt-popover").getBoundingClientRect();
  check("resizing an open popover keeps it visible", resized.left >= 0 && resized.right <= 390 && resized.bottom <= 699);
  frame.style.width = "1366px";
  await pause();

  // Match pseudo-class specificity while exercising computed fills in this fixture.
  const link = find<HTMLLinkElement>('link[href*="styles.css"]');
  const styles = d.createElement("style");
  styles.textContent = (await (await nativeFetch(link.href)).text())
    .replace(/:hover\b/g, "[data-qa-hover]").replace(/:active\b/g, "[data-qa-pressed]")
    + "\n*,*::before,*::after{transition:none!important;animation:none!important;}";
  d.head.append(styles); link.disabled = true;
  for (const theme of ["light", "dark"]) {
    find(`[data-theme-option="${theme}"]`).click();
    for (const [width, height] of [[1366, 699], [390, 740]]) {
      frame.style.width = `${width}px`; frame.style.height = `${height}px`;
      await pause(); anchor.click(); await pause();
      find(".prompt-popover-response summary").click(); await pause();
      const box = find(".prompt-popover").getBoundingClientRect();
      const scrollbarColors = [...d.querySelectorAll(".prompt-popover-body, .prompt-popover-text, .prompt-popover-submitted-text")]
        .map(e => w.getComputedStyle(e).scrollbarColor);
      check(`${theme}/${width}: all popover scrollbars share theme colors`, scrollbarColors.every(color => color !== "auto" && color === scrollbarColors[0]));
      check(`${theme}/${width}: popover stays inside viewport (${[box.left, box.top, box.right, box.bottom].join(",")})`, box.left >= 0 && box.top >= 0 && box.right <= width && box.bottom <= height);
      check(`${theme}/${width}: response scrolls without horizontal overflow`, find(".prompt-response-json").scrollHeight > find(".prompt-response-json").clientHeight
        && find(".prompt-popover").scrollWidth <= find(".prompt-popover").clientWidth + 1);
      check(`${theme}/${width}: expanded JSON has useful visible space`, box.bottom - find(".prompt-response-json").getBoundingClientRect().top >= 80);
      for (const selector of [".prompt-popover-close", "[data-copy-optimized-prompt]", ".prompt-response-actions button", ".prompt-popover-response summary"]) {
        const e = find(selector), normal = w.getComputedStyle(e).backgroundColor;
        e.setAttribute("data-qa-hover", ""); const hover = w.getComputedStyle(e).backgroundColor;
        e.setAttribute("data-qa-pressed", ""); const pressed = w.getComputedStyle(e).backgroundColor;
        e.removeAttribute("data-qa-hover"); e.removeAttribute("data-qa-pressed");
        check(`${theme}/${width}/${selector}: hover and press are distinct`, normal !== hover && hover !== pressed);
      }
      find(".prompt-popover-close").focus(); find(".prompt-popover-close").click();
      check(`${theme}/${width}: closing restores trigger focus`, d.activeElement === anchor);
    }
  }

  responseMode = "missing";
  anchor.click(); find(".prompt-popover-response summary").click(); await pause();
  check("old tasks show missing response, not metadata", find(".prompt-response-status").textContent!.includes("未保存")
    && find<HTMLPreElement>(".prompt-response-json").hidden);
  methods.closePromptPopover();
  responseMode = "error";
  anchor.click(); find(".prompt-popover-response summary").click(); await pause();
  check("failed fetch provides retry", !find<HTMLButtonElement>(".prompt-response-actions button:last-child").hidden);
  responseMode = "ok"; find(".prompt-response-actions button:last-child").click(); await pause();
  check("retry loads response", !find<HTMLPreElement>(".prompt-response-json").hidden);
  methods.closePromptPopover();
  responseMode = "slow";
  anchor.click(); find(".prompt-popover-response summary").click(); await pause();
  methods.closePromptPopover();
  responseMode = "missing";
  methods.openPromptPopover(anchor, { taskId: "other-task", originalPrompt: "Other task" });
  find(".prompt-popover-response summary").click(); await pause();
  resolveSlow!(response()); await pause();
  check("late response cannot replace another task", find(".prompt-response-status").textContent!.includes("未保存")
    && !find(".prompt-response-json").textContent!.includes("synthetic-provider-reply"));
  methods.closePromptPopover();
  styles.remove(); link.disabled = false;
  frame.style.width = "1366px"; frame.style.height = "699px";
  responseMode = "ok";
  const demo = document.createElement("button"); demo.textContent = "Open response demo";
  demo.onclick = () => anchor.click(); document.body.prepend(demo);
  check("no runtime or resource errors", errors.length === 0);
  output.textContent = JSON.stringify({ passed: failures.length === 0, assertions, failures, errors }, null, 2);
}
run().catch(error => { output.textContent = JSON.stringify({ passed: false, error: String(error), assertions, failures, errors }); });

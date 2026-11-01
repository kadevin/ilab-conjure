/** Targeted toolbar and theme acceptance, using only the isolated fixture origin. */
import { loadAcceptanceFrame, prepareFixtureOrigin } from "./browser_acceptance";

const frame = document.querySelector<HTMLIFrameElement>("#historyFrame")!;
const output = document.querySelector<HTMLElement>("#results")!;
const errors: string[] = [];
const failures: Array<{ name: string; detail?: unknown }> = [];
const measurements: unknown[] = [];
let assertions = 0;
const pause = (ms = 250) => new Promise(resolve => setTimeout(resolve, ms));
function check(name: string, pass: boolean, detail?: unknown) {
  assertions++;
  if (!pass) failures.push({ name, detail });
}

async function run() {
  await prepareFixtureOrigin();
  localStorage.clear();
  localStorage.setItem("codex-image-locale-preference", "zh-CN");
  const provider = (id: string) => ({
    id, name: `QA ${id}`, base_url: "https://relay.example/v1", api_key: "synthetic-qa-key", concurrency: 3,
    bindings: [{ id: `${id}-image`, canonical_model_id: "gpt-image-2", remote_model_id: "gpt-image-2",
      protocol_profile: "openai_images", parameter_codec: "gpt_openai_images", operations: ["generate", "edit"] }],
  });
  const seed = await fetch("/api/api-settings", { method: "PATCH", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ schema_version: 2, codex_mode: "images", active_provider_id: "a",
      providers: [provider("a"), provider("b")], default_provider_by_model: { "gpt-image-2": "a" } }) });
  if (!seed.ok) throw new Error(`Fixture settings failed: ${seed.status} ${await seed.text()}`);
  await loadAcceptanceFrame(frame, "/qa-app", errors);
  const w = frame.contentWindow!, d = frame.contentDocument!;
  const deadline = Date.now() + 15000;
  while (!w.__codexImageWebUI?.state.generationCatalog) {
    if (Date.now() > deadline) throw new Error("Catalog did not load");
    await pause(50);
  }
  const { state, methods } = w.__codexImageWebUI;
  methods.selectGenerationProvider!("a");
  const find = <T extends HTMLElement = HTMLElement>(selector: string) => d.querySelector<T>(selector)!;
  const rect = (selector: string) => find(selector).getBoundingClientRect();
  const visible = (selector: string) => rect(selector).width > 0;
  const input = (selector: string, value: string) => {
    find<HTMLInputElement>(selector).value = value;
    find(selector).dispatchEvent(new w.Event("input", { bubbles: true }));
  };
  const resize = async (width: number, height: number) => {
    frame.style.width = `${width}px`; frame.style.height = `${height}px`; await pause();
  };
  for (const theme of ["light", "dark"]) {
    find(`[data-theme-option="${theme}"]`).click();
    for (const locale of ["zh-CN", "en"]) {
      w.__codexImageI18n.setLocale(locale);
      for (const [width, height] of [[1920, 1080], [1512, 773], [1366, 768], [1280, 720], [1024, 768], [390, 844], [320, 740]]) {
        await resize(width, height);
        methods.setPromptText!("第一行\n第二行\n第三行");
        const name = `${theme} ${locale} ${width}x${height}`;
        const before = { footer: rect(".prompt-footer").height, editor: rect("#promptEditor").height,
          template: rect("#promptTemplateButton").y, output: rect(".output-panel").y };
        find("#promptFindButton").click(); await pause();
        check(`${name}: tools replace the original buttons`, !visible("#clearPromptButton") && !visible("#promptFindButton") && visible("#promptFindPanel"));
        check(`${name}: search receives focus`, d.activeElement === find("#promptFindInput"));
        check(`${name}: tools fit without horizontal overflow`, find("#promptFindPanel").scrollWidth <= find("#promptFindPanel").clientWidth + 1);
        const editor = find("#promptEditor"), style = w.getComputedStyle(editor);
        const threeLines = 3 * parseFloat(style.lineHeight) + parseFloat(style.paddingTop)
          + parseFloat(style.paddingBottom) + parseFloat(style.borderTopWidth) + parseFloat(style.borderBottomWidth);
        check(`${name}: editor keeps three visible lines`, editor.getBoundingClientRect().height >= threeLines - 1
          && editor.scrollHeight <= editor.clientHeight + 1);
        const tools = [...d.querySelectorAll<HTMLElement>("#promptFindPanel input, #promptFindPanel button")];
        check(`${name}: controls do not overlap`, tools.every((a, i) => tools.slice(i + 1).every(b => {
          const x = a.getBoundingClientRect(), y = b.getBoundingClientRect();
          return x.right <= y.left + 1 || y.right <= x.left + 1 || x.bottom <= y.top + 1 || y.bottom <= x.top + 1;
        })));
        if (width >= 1280) {
          check(`${name}: opening find preserves toolbar and editor height`, Math.abs(rect(".prompt-footer").height - before.footer) < 1 && Math.abs(rect("#promptEditor").height - before.editor) < 1,
            { before, footer: rect(".prompt-footer").height, editor: rect("#promptEditor").height });
          check(`${name}: template and output remain in place`, Math.abs(rect("#promptTemplateButton").y - before.template) < 1 && Math.abs(rect(".output-panel").y - before.output) < 1);
        }
        if (width <= 390) check(`${name}: touch actions retain targets`, tools.every(e => e.getBoundingClientRect().height >= 44 && e.getBoundingClientRect().width >= 44));
        find("#promptFindInput").dispatchEvent(new w.KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
        check(`${name}: Escape restores original tools and focus`, !visible("#promptFindPanel") && visible("#clearPromptButton") && d.activeElement === find("#promptFindButton"));
      }
    }
  }

  await resize(1512, 773);
  w.__codexImageI18n.setLocale("zh-CN");
  methods.setPromptText!("甲 甲 ");
  for (const className of ["gallery-chip", "color-chip", "prompt-snippet-chip"]) {
    const chip = d.createElement("span"); chip.className = className; chip.textContent = "甲";
    chip.contentEditable = "false"; find("#promptEditor").append(chip);
  }
  find("#promptFindButton").click();
  input("#promptFindInput", "甲");
  check("typing a query does not run a search", find("#promptFindCount").textContent === "0 处");
  find('[data-prompt-find-action="count"]').click();
  check("search counts only ordinary text", find("#promptFindCount").textContent === "2 处");
  input("#promptReplaceInput", "乙"); find('[data-prompt-find-action="replace-all"]').click();
  check("replace keeps all atomic chips intact", find("#promptEditor").textContent === "乙 乙 甲甲甲"
    && [...d.querySelectorAll("#promptEditor [contenteditable=false]")].every(e => e.textContent === "甲"));
  find("#promptFindClose").click();
  check("close button restores entry focus", d.activeElement === find("#promptFindButton"));
  methods.setPromptText!("");

  // Equal-specificity attributes exercise the complete production cascade in this
  // fixture. This checks state styling, not native pointer dispatch or touch events.
  const link = find<HTMLLinkElement>('link[href*="styles.css"]');
  const css = await (await fetch(link.href)).text();
  const stateStyles = d.createElement("style");
  stateStyles.textContent = css.replace(/:hover\b/g, "[data-qa-hover]").replace(/:active\b/g, "[data-qa-pressed]")
    + "\n*,*::before,*::after{transition:none!important;animation:none!important;}";
  d.head.append(stateStyles); link.disabled = true;
  const canvas = d.createElement("canvas"), ctx = canvas.getContext("2d")!;
  const rgb = (color: string) => {
    ctx.clearRect(0, 0, 1, 1); ctx.fillStyle = color; ctx.fillRect(0, 0, 1, 1);
    return [...ctx.getImageData(0, 0, 1, 1).data].slice(0, 3);
  };
  const distance = (a: string, b: string) => Math.hypot(...rgb(a).map((v, i) => v - rgb(b)[i]));
  const contrast = (a: string, b: string) => {
    const luminance = (color: string) => rgb(color).map(v => v / 255).map(v => v <= .04045 ? v / 12.92 : ((v + .055) / 1.055) ** 2.4)
      .reduce((sum, v, i) => sum + v * [.2126, .7152, .0722][i], 0);
    const values = [luminance(a), luminance(b)].sort((a, b) => b - a);
    return (values[0] + .05) / (values[1] + .05);
  };
  const background = (e: Element) => w.getComputedStyle(e).backgroundColor;
  const buttonStates = (selector: string) => {
    const button = find<HTMLButtonElement>(selector), normal = background(button);
    button.setAttribute("data-qa-hover", ""); const hover = background(button);
    button.setAttribute("data-qa-pressed", ""); const pressed = background(button);
    button.removeAttribute("data-qa-hover"); button.removeAttribute("data-qa-pressed");
    check(`${d.documentElement.dataset.theme} ${selector}: distinct hover and press`, distance(normal, hover) >= 16 && distance(hover, pressed) >= 8, { normal, hover, pressed });
    const disabled = button.disabled; button.disabled = true;
    const muted = background(button); button.setAttribute("data-qa-hover", "");
    check(`${selector}: disabled has no hover feedback`, background(button) === muted);
    button.removeAttribute("data-qa-hover"); button.disabled = disabled;
    return normal;
  };
  for (const theme of ["light", "dark"]) {
    find(`[data-theme-option="${theme}"]`).click(); await pause();
    const common = buttonStates("#promptFindButton");
    for (const selector of ["#pasteClipboardButton", "#clearPromptButton", "#clearImagesButton", "#batchManageButton"]) buttonStates(selector);
    find("#batchManageButton").click();
    for (const selector of ["#batchSelectGroupButton", "#batchSelectWaitingButton", "#batchArchiveButton", "#batchDeleteButton"]) {
      const button = find<HTMLButtonElement>(selector), wasDisabled = button.disabled;
      button.disabled = false; buttonStates(selector); button.disabled = wasDisabled;
    }
    find("#batchManageButton").click();
    const timestamp = new Date().toISOString();
    state.tasks = [{ task_id: "qa-feedback-card", status: "completed", mode: "generate", prompt: "QA task",
      created_at: timestamp, completed_at: timestamp, params: { model: "gpt-image-2", size: "1024x1024", n: 1 },
      output_urls: [], thumbnail_urls: [] }];
    state.taskSidebarGroupCounts = {};
    methods.renderTasks!(); await pause();
    const card = find(".task-card"), savedClass = card.className, surface = card.querySelector(".task-card-swipe-surface")!;
    for (const status of ["", "unread", "running", "failed", "partial_failed", "active", "batch-selected", "active running", "active failed", "batch-selected failed"]) {
      card.className = `task-card ${status}`;
      const normal = background(surface), bounds = card.getBoundingClientRect();
      card.setAttribute("data-qa-hover", ""); const hover = background(surface);
      card.setAttribute("data-qa-pressed", ""); const pressed = background(surface);
      check(`${theme} ${status || "normal"} card: hover survives status`, distance(normal, hover) >= 12, { normal, hover });
      check(`${theme} ${status || "normal"} card: press differs from hover`, distance(hover, pressed) >= 8);
      check(`${theme} ${status || "normal"} card: stable footprint`, card.getBoundingClientRect().height === bounds.height && card.getBoundingClientRect().width === bounds.width);
      card.removeAttribute("data-qa-hover"); card.removeAttribute("data-qa-pressed");
    }
    card.className = savedClass;
    methods.openApiSettingsModal!(); await pause();
    for (const selector of ["#sortApiProvidersButton", "#editApiProviderButton", "#copyApiProviderButton", "#deleteApiProviderButton"]) {
      check(`${theme} ${selector}: same opaque secondary surface`, buttonStates(selector) === common && w.getComputedStyle(find(selector)).opacity === "1");
    }
    find("#systemSettingsNetworkTab").click();
    const target = w.getComputedStyle(find("#promptEditor"), "::before").color;
    for (const selector of ["#taskSearch", "#promptFindInput", "#promptReplaceInput", "#promptTemplateSearch", "#networkEgressCustomProxy"]) {
      const e = find(selector), placeholder = w.getComputedStyle(e, "::placeholder");
      check(`${theme} ${selector}: theme placeholder`, placeholder.color === target && placeholder.opacity === "1");
      check(`${theme} ${selector}: readable placeholder`, contrast(placeholder.color, background(e)) >= 4.5);
    }
    measurements.push({ theme, secondarySurface: common, placeholder: target });
    find("#systemSettingsModalClose").click();
  }
  link.disabled = false; stateStyles.remove();
  output.textContent = JSON.stringify({ passed: !failures.length && !errors.length, assertions, failures, errors, measurements }, null, 2);
}

run().catch(error => { output.textContent = JSON.stringify({ passed: false, assertions, failures, errors, fatal: String(error), stack: error?.stack }, null, 2); });

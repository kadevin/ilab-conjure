/** Filled-icon rendering and layout acceptance on the synthetic fixture only. */
import { loadAcceptanceFrame, prepareFixtureOrigin } from "./browser_acceptance";

const frame = document.querySelector<HTMLIFrameElement>("#historyFrame")!;
const output = document.querySelector<HTMLElement>("#results")!;
const errors: string[] = [];
const failures: Array<{ name: string; detail?: unknown }> = [];
let assertions = 0;
const pause = () => new Promise(resolve => setTimeout(resolve, 250));
function check(name: string, pass: boolean, detail?: unknown) {
  assertions++;
  if (!pass) failures.push({ name, detail });
}

async function run() {
  await prepareFixtureOrigin();
  localStorage.clear();
  localStorage.setItem("codex-image-locale-preference", "zh-CN");
  await loadAcceptanceFrame(frame, "/qa-app", errors);
  const w = frame.contentWindow!, d = frame.contentDocument!;
  const readyBy = Date.now() + 15000;
  while (!w.__codexImageWebUI?.state.generationCatalog || d.querySelector("#recentAssetList")?.hasAttribute("aria-busy")) {
    if (Date.now() > readyBy) throw new Error("Fixture did not finish loading");
    await pause();
  }
  w.__codexImageWebUI!.state.recentAssets = [{ id: "qa-icon-recent", filename: "QA reference",
    image_url: "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='16' height='16'/%3E" }];
  w.__codexImageWebUI!.methods.renderRecentAssets!();
  const find = (selector: string) => d.querySelector<HTMLElement>(selector)!;
  const resize = async (width: number, height: number) => {
    frame.style.width = `${width}px`; frame.style.height = `${height}px`; await pause();
  };
  const inspect = (name: string) => {
    const icons = [...d.querySelectorAll<SVGSVGElement>("svg[data-ui-icon]")]
      .filter(icon => icon.getBoundingClientRect().width > 0 && w.getComputedStyle(icon).visibility !== "hidden");
    check(`${name}: visible icons loaded and painted`, icons.length > 0 && icons.every(icon => {
      const box = icon.getBBox(); return box.width > 0 && box.height > 0;
    }));
    const clipped = icons.filter(icon => {
      const button = icon.closest("button"); if (!button) return false;
      const a = icon.getBoundingClientRect(), b = button.getBoundingClientRect();
      return a.left < b.left - 1 || a.right > b.right + 1 || a.top < b.top - 1 || a.bottom > b.bottom + 1;
    }).map(icon => icon.parentElement?.id || icon.dataset.uiIcon);
    check(`${name}: icons stay inside buttons`, !clipped.length, clipped);
    check(`${name}: decorative icons do not acquire keyboard stops`, icons.every(icon =>
      icon.getAttribute("aria-hidden") === "true" && icon.getAttribute("focusable") === "false"));
    for (const id of ["clearPromptButton", "promptFindButton", "pasteClipboardButton", "galleryManageButton"]) {
      const button = find(`#${id}`), icon = button.querySelector("svg")!;
      if (button.getBoundingClientRect().width) {
        check(`${name} ${id}: legible icon with retained label`, icon.getBoundingClientRect().width >= 16
          && !!(button.textContent?.trim() || button.getAttribute("aria-label")));
      }
    }
  };
  for (const theme of ["light", "dark"]) {
    find(`[data-theme-option="${theme}"]`).click();
    for (const [width, height] of [[1920, 1080], [1512, 773], [1280, 699], [390, 844]]) {
      await resize(width, height); inspect(`${theme} ${width}x${height}`);
    }
  }
  await resize(1512, 773);
  const openLock = find(".output-settings-lock-open"), closedLock = find(".output-settings-lock-closed");
  const before = w.getComputedStyle(find("#outputSettingsLockButton")).backgroundColor;
  check("unlocked state shows an open shackle", w.getComputedStyle(openLock).display !== "none" && w.getComputedStyle(closedLock).display === "none");
  find("#outputSettingsLockButton").click(); await pause();
  check("lock state changes glyph, fill and accessible state", w.getComputedStyle(openLock).display === "none" && w.getComputedStyle(closedLock).display !== "none"
    && w.getComputedStyle(find("#outputSettingsLockButton")).backgroundColor !== before
    && find("#outputSettingsLockButton").getAttribute("aria-pressed") === "true");
  find("#outputSettingsLockButton").click();
  const eye = find("#recentAssetVisibilityToggle"), eyeBefore = eye.getAttribute("aria-expanded");
  eye.click(); await pause();
  check("recent upload visibility switches one eye icon at a time", eye.getAttribute("aria-expanded") !== eyeBefore
    && [...eye.querySelectorAll("svg")].filter(icon => icon.getBoundingClientRect().width > 0).length === 1);
  eye.click();
  find("#batchManageButton").click(); await pause();
  check("batch selection starts with one visible mark", [...d.querySelectorAll("#batchSelectGroupButton use")]
    .filter(mark => w.getComputedStyle(mark).display !== "none").length === 1);
  find("#batchManageButton").click();
  find("#promptFindButton").focus();
  check("keyboard focus remains on the button", d.activeElement === find("#promptFindButton"));

  w.__codexImageWebUI!.methods.openApiSettingsModal!(); await pause();
  inspect("API settings");
  find("#systemSettingsModalClose").click();

  // Render every symbol at actual UI sizes, including normally hidden states.
  const response = await fetch("/static/icons/ui.svg?v=1");
  check("sprite served as SVG", response.ok && !!response.headers.get("content-type")?.includes("image/svg+xml"));
  const sprite = new DOMParser().parseFromString(await response.text(), "image/svg+xml");
  const ids = [...sprite.querySelectorAll("symbol")].map(symbol => symbol.id);
  const atlas = document.createElement("section"); atlas.id = "qaIconAtlas";
  atlas.style.cssText = "display:grid;grid-template-columns:repeat(8,100px);gap:8px;padding:16px;width:max-content;font:12px system-ui";
  for (const theme of ["light", "dark"]) for (const id of ids) {
    const cell = document.createElement("div"); cell.dataset.theme = theme;
    cell.style.cssText = `padding:10px;border-radius:8px;background:${theme === "dark" ? "#18251f" : "#f6f8f5"};color:${theme === "dark" ? "#a5c5b5" : "#335d4d"}`;
    cell.innerHTML = `<div style="display:flex;gap:12px;align-items:center;height:26px"><svg width="16" height="16" viewBox="0 0 24 24"><use href="/static/icons/ui.svg?v=1#${id}"/></svg><svg width="20" height="20" viewBox="0 0 24 24"><use href="/static/icons/ui.svg?v=1#${id}"/></svg></div><span>${id}</span>`;
    atlas.append(cell);
  }
  document.body.prepend(atlas); await pause();
  check("every sprite symbol renders at both sizes and themes", [...atlas.querySelectorAll<SVGSVGElement>("svg")]
    .every(icon => { const box = icon.getBBox(); return box.width > 0 && box.height > 0 && box.x >= 0 && box.y >= 0 && box.x + box.width <= 24.1 && box.y + box.height <= 24.1; }));
  await loadAcceptanceFrame(frame, "/qa-history", errors); await pause();
  const historyIcons = [...frame.contentDocument!.querySelectorAll<SVGSVGElement>("svg[data-ui-icon]")]
    .filter(icon => icon.getBoundingClientRect().width > 0);
  check("history uses the same successfully rendered symbols", historyIcons.length > 0 && historyIcons.every(icon => {
    const box = icon.getBBox(); return box.width > 0 && box.height > 0;
  }));
  output.textContent = JSON.stringify({ passed: !failures.length && !errors.length, assertions, failures, errors }, null, 2);
}
run().catch(error => { output.textContent = JSON.stringify({ passed: false, assertions, failures, errors, fatal: String(error) }, null, 2); });

import { loadAcceptanceFrame, prepareFixtureOrigin } from "./browser_acceptance";
import { checkAppearanceCoverage } from "./appearance-coverage.browser";
const frame = document.querySelector<HTMLIFrameElement>("#historyFrame")!;
const output = document.querySelector<HTMLElement>("#results")!;
const errors: string[] = [], failures: string[] = [];
let assertions = 0;
const pause = () => new Promise(resolve => setTimeout(resolve, 180));
const check = (name: string, pass: boolean) => { assertions++; if (!pass) failures.push(name); };
const key = "ilab-conjure-appearance";
async function run() {
  await prepareFixtureOrigin();
  localStorage.clear();
  localStorage.setItem("codex-image-locale-preference", "zh-CN");
  const blue = { version: 1, preset: "custom", primary: "#386FC4", background: "cool" };
  for (const page of ["/qa-app", "/qa-history"]) {
    frame.style.width = "1440px"; frame.style.height = "900px";
    localStorage.removeItem(key);
    localStorage.setItem("codex-image-theme-preference", "light");
    await loadAcceptanceFrame(frame, page, errors);
    const w = frame.contentWindow!, d = frame.contentDocument!;
    const find = <T extends HTMLElement = HTMLElement>(selector: string) => d.querySelector<T>(selector)!;
    const click = (selector: string) => find(selector).click();
    const input = (value: string) => { find<HTMLInputElement>("#appearanceHex").value = value; find("#appearanceHex").dispatchEvent(new w.Event("input", { bubbles: true })); };
    const token = (name: string) => w.getComputedStyle(d.documentElement).getPropertyValue(name).trim();
    const opened = () => !find("#appearancePopover").hidden;
    const open = async () => {
      if (opened()) click("#appearanceCancel");
      if (d.body.classList.contains("mobile-ui")) { click(".mobile-more-button"); await pause(); }
      const trigger = find("#appearanceTrigger");
      check(`${page}: trigger reachable`, trigger.getClientRects().length > 0 && !trigger.closest("[inert]"));
      trigger.focus(); trigger.click(); await pause();
    };
    check(`${page}: original light primary`, token("--primary") === "#457b66");
    await open();
    check(`${page}: grouped theme control`, find("#themeSwitcher").contains(find("#appearanceTrigger")));
    check(`${page}: nonmodal preview`, find("#appearancePopover").getAttribute("aria-modal") === "false" && !find(page === "/qa-app" ? ".layout-container" : ".history-page").inert);
    click('[data-appearance-preset="blue"]');
    check(`${page}: live preview`, d.documentElement.dataset.appearance === "custom" && token("--primary") !== "#457b66");
    check(`${page}: preview not saved`, localStorage.getItem(key) === null);
    click("#appearanceCancel");
    check(`${page}: cancel closes and restores original`, !opened() && token("--primary") === "#457b66" && d.activeElement === find("#appearanceTrigger"));
    await open(); input("#ffff");
    check(`${page}: invalid input blocked`, find<HTMLButtonElement>("#appearanceApply").disabled && find("#appearanceHex").getAttribute("aria-invalid") === "true");
    input("#FACC15");
    check(`${page}: valid input recovers`, !find<HTMLButtonElement>("#appearanceApply").disabled);
    click('[data-appearance-preset="blue"]'); click("#appearanceApply");
    check(`${page}: apply closes and persists`, !opened() && JSON.stringify(JSON.parse(localStorage.getItem(key)!)) === JSON.stringify(blue));
    await open(); click('[data-appearance-preset="purple"]');
    d.body.dispatchEvent(new w.MouseEvent("click", { bubbles: true }));
    check(`${page}: outside click cancels`, !opened() && find<HTMLInputElement>("#appearanceHex").value === blue.primary);
    await open(); click('[data-appearance-preset="purple"]');
    find("#appearanceHex").focus();
    find("#appearanceHex").dispatchEvent(new w.KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
    check(`${page}: Escape cancels and returns focus`, !opened() && find<HTMLInputElement>("#appearanceHex").value === blue.primary && d.activeElement === find("#appearanceTrigger"));
    w.__codexImageWebUI!.methods.openSystemSettingsModal!("language"); await pause();
    check(`${page}: settings has shortcut only`, Boolean(find("#appearanceShortcut")) && !find("#systemSettingsLanguagePanel").contains(find("#appearanceHex")));
    click("#appearanceShortcut"); await pause();
    check(`${page}: shortcut closes modal first`, opened() && find("#systemSettingsModal").classList.contains("hidden") && !find("#appearanceHex").closest("[inert]"));
    click("#appearanceClose");
    const amber = { ...blue, primary: "#A66D25", background: "warm" };
    await open(); click('[data-appearance-preset="purple"]');
    const purplePreview = token("--primary");
    localStorage.setItem(key, JSON.stringify(amber)); await pause();
    check(`${page}: external save preserves edited draft and preview`, opened()
      && find<HTMLInputElement>("#appearanceHex").value === "#8057B0" && token("--primary") === purplePreview);
    click("#appearanceCancel");
    check(`${page}: cancel restores latest external save`, find<HTMLInputElement>("#appearanceHex").value === amber.primary);
    await open(); click('[data-appearance-preset="purple"]');
    localStorage.setItem(key, JSON.stringify(blue)); await pause(); click("#appearanceApply");
    check(`${page}: apply saves local draft over external save`, !opened() && JSON.parse(localStorage.getItem(key)!).primary === "#8057B0");
    await open();
    localStorage.setItem(key, JSON.stringify(amber)); await pause();
    check(`${page}: untouched panel still synchronizes`, opened() && find<HTMLInputElement>("#appearanceHex").value === amber.primary);
    input("#12");
    localStorage.setItem(key, JSON.stringify(blue)); await pause();
    check(`${page}: external save preserves incomplete HEX and validation`, find<HTMLInputElement>("#appearanceHex").value === "#12"
      && find<HTMLButtonElement>("#appearanceApply").disabled && find("#appearanceHex").getAttribute("aria-invalid") === "true");
    click("#appearanceCancel");
    check(`${page}: invalid draft cancellation restores latest save`, find<HTMLInputElement>("#appearanceHex").value === blue.primary);
    await open();
    find<HTMLInputElement>("#appearanceColor").value = "#123456";
    find("#appearanceColor").dispatchEvent(new w.Event("input", { bubbles: true }));
    localStorage.removeItem(key); await pause();
    check(`${page}: external removal preserves picker draft`, opened() && find<HTMLInputElement>("#appearanceHex").value === "#123456");
    click("#appearanceCancel");
    check(`${page}: cancel after external removal restores default`, d.documentElement.dataset.appearance === "default");
    await open(); click('[data-appearance-preset="blue"]'); click("#appearanceApply");
    await open(); click("#appearanceReset");
    localStorage.setItem(key, JSON.stringify(amber)); await pause();
    check(`${page}: external save preserves reset preview`, d.documentElement.dataset.appearance === "default");
    click("#appearanceCancel");
    // Keep the existing layout acceptance baseline unchanged.
    await open(); click('[data-appearance-preset="blue"]'); click("#appearanceApply");
    for (const theme of ["light", "dark"]) {
      for (const locale of ["zh-CN", "en"]) {
        w.__codexImageI18n.setLocale(locale);
        for (const [width, height] of [[1440, 900], [1024, 768], [820, 1180], [390, 844], [320, 740], [600, 360]]) {
          frame.style.width = `${width}px`; frame.style.height = `${height}px`; await pause();
          const mobile = d.body.classList.contains("mobile-ui");
          if (mobile) { click(".mobile-more-button"); await pause(); }
          click(`[data-theme-option="${theme}"]`);
          await open();
          const label = `${page}/${theme}/${locale}/${width}x${height}`;
          const panel = find("#appearancePopover"), rect = panel.getBoundingClientRect();
          check(`${label}: within viewport`, rect.width > 0 && rect.left >= 0 && rect.right <= width && rect.top >= 0 && rect.bottom <= height);
          check(`${label}: no overflow`, panel.scrollWidth <= panel.clientWidth + 1 && d.documentElement.scrollWidth <= width);
          check(`${label}: no stacked modal`, find("#mobileMore").classList.contains("hidden") && find("#systemSettingsModal").classList.contains("hidden"));
          check(`${label}: focus enters preview`, panel.contains(d.activeElement) && !find("#appearanceHex").closest("[inert]"));
          const button = find("#appearanceApply").getBoundingClientRect(), cancel = find("#appearanceCancel").getBoundingClientRect();
          check(`${label}: actions reachable and aligned`, button.bottom <= height && button.left >= 0 && Math.abs(cancel.y - button.y) < 1 && Math.abs(cancel.height - button.height) < 1);
          if (mobile) check(`${label}: touch targets`, button.height >= 44 && find("#appearanceColor").getBoundingClientRect().height >= 44);
          const card = find('[data-appearance-preset="blue"] .appearance-preview');
          check(`${label}: visible color preview`, card.getBoundingClientRect().height >= 40 && w.getComputedStyle(card).backgroundColor !== "rgba(0, 0, 0, 0)");
          find("#appearanceApply").focus();
          find("#appearanceApply").dispatchEvent(new w.KeyboardEvent("keydown", { key: "Tab", bubbles: true, cancelable: true }));
          check(`${label}: Tab wraps`, d.activeElement === find("#appearanceReset"));
          find("#appearanceReset").dispatchEvent(new w.KeyboardEvent("keydown", { key: "Tab", shiftKey: true, bubbles: true, cancelable: true }));
          check(`${label}: Shift Tab wraps`, d.activeElement === find("#appearanceApply"));
          find("#appearanceHex").focus();
          check(`${label}: editable focus`, d.activeElement === find("#appearanceHex"));
          click("#appearanceCancel"); await pause();
          check(`${label}: close returns visible focus`, d.activeElement === find(mobile ? ".mobile-more-button" : "#appearanceTrigger"));
        }
      }
    }
    // Every supported translation must fit without clipping a color option.
    frame.style.width = "1440px"; frame.style.height = "900px"; await pause();
    for (const locale of ["zh-CN", "zh-TW", "zh-HK", "ja", "ko", "en", "vi", "es", "pt", "fr", "de", "ru", "it", "hi"]) {
      w.__codexImageI18n.setLocale(locale); await open();
      check(`${page}/${locale}: background labels fit`, Array.from(d.querySelectorAll<HTMLElement>(".appearance-tones button")).every(button => button.scrollWidth <= button.clientWidth + 1));
      check(`${page}/${locale}: translated actions fit`, Array.from(d.querySelectorAll<HTMLElement>(".appearance-actions button")).every(button => button.scrollWidth <= button.clientWidth + 1));
      click("#appearanceCancel");
    }
    await checkAppearanceCoverage(frame, page, open, check);
    // Theme switching remains one click while comparing a draft on desktop.
    frame.style.width = "1440px"; frame.style.height = "900px"; await pause(); await open();
    click('[data-appearance-preset="purple"]'); click('[data-theme-option="light"]'); await pause();
    check(`${page}: theme switch preserves draft`, opened() && find<HTMLInputElement>("#appearanceHex").value === "#8057B0" && d.documentElement.dataset.theme === "light");
    click('[data-theme-option="dark"]'); await pause();
    click("#appearanceReset"); click("#appearanceApply");
    check(`${page}: reset original dark palette`, token("--primary") === "#72b79b");
    await open(); click('[data-appearance-preset="blue"]'); click("#appearanceApply");
    const primary = token("--primary");
    await open(); click('[data-appearance-preset="purple"]'); click("#appearanceTrigger");
    check(`${page}: toggle closes and cancels preview`, !opened() && token("--primary") === primary);
    await open();
    // Crossing the mobile breakpoint preserves the draft and panel reachability.
    click('[data-appearance-preset="purple"]');
    frame.style.width = "390px"; frame.style.height = "844px"; await pause();
    check(`${page}: responsive relocation`, opened() && find<HTMLInputElement>("#appearanceHex").value === "#8057B0" && find("#appearancePopover").getBoundingClientRect().right <= 390);
    click("#appearanceCancel");
    check(`${page}: relocated focus fallback`, d.activeElement === find(".mobile-more-button"));
    await loadAcceptanceFrame(frame, page, errors);
    check(`${page}: reload restores skin`, frame.contentDocument!.documentElement.dataset.appearance === "custom");
    localStorage.setItem(key, JSON.stringify({ version: 1, preset: "default", primary: "#457B66", background: "tinted" })); await pause();
    check(`${page}: storage synchronization`, frame.contentDocument!.documentElement.dataset.appearance === "default");
  }
  output.textContent = JSON.stringify({ passed: failures.length === 0 && errors.length === 0, assertions, failures, errors }, null, 2);
}
run().catch(error => { output.textContent = JSON.stringify({ passed: false, assertions, failures, errors, error: String(error) }, null, 2); });

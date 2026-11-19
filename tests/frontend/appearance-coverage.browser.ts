import { colorContrast } from "../../codex_image/webui/frontend/src/appearance";

/** Component specimens use production CSS; the popover and scroll containers are real UI nodes. */
export async function checkAppearanceCoverage(frame: HTMLIFrameElement, page: string,
  open: () => Promise<void>, check: (name: string, pass: boolean) => void) {
  const w = frame.contentWindow!, d = frame.contentDocument!;
  const pause = () => new Promise(resolve => setTimeout(resolve, 200));
  const find = (selector: string) => d.querySelector<HTMLElement>(selector)!;
  const click = (selector: string) => find(selector).click();
  const token = (name: string) => w.getComputedStyle(d.documentElement).getPropertyValue(`--${name}`).trim();
  const canvas = d.createElement("canvas"), context = canvas.getContext("2d")!;
  const rgba = (color: string) => {
    context.clearRect(0, 0, 1, 1); context.fillStyle = color; context.fillRect(0, 0, 1, 1);
    return [...context.getImageData(0, 0, 1, 1).data];
  };
  const hex = (color: string) => "#" + rgba(color).slice(0, 3).map(c => c.toString(16).padStart(2, "0")).join("");
  const same = (a: string, b: string) => rgba(a).join() === rgba(b).join();
  // Exercise hover/focus styling separately from native pointer/keyboard dispatch.
  const link = d.querySelector<HTMLLinkElement>('link[href*="styles.css"]')!;
  const styles = d.createElement("style");
  styles.textContent = (await (await fetch(link.href)).text()).replace(/:hover\b/g, "[data-qa-hover]")
    .replace(/:focus-visible\b/g, "[data-qa-focus]")
    + "\n*,*::before,*::after{transition:none!important;animation:none!important}";
  d.head.append(styles); link.disabled = true;
  const specimens = d.createElement("div");
  specimens.innerHTML = `<div class="thumb"><button class="add-upload-to-gallery">Add</button><span class="thumb-edited-badge">Edited</span></div>
    <div class="gallery-edit-popover"></div><div class="prompt-popover"></div>
    <div class="lightbox-zoom-toolbar"><button class="lightbox-zoom-mode" aria-pressed="true">Fit</button></div>
    <button class="gallery-chip-remove">×</button><span class="color-chip-swatch" style="--color-code:#ff3b30"></span>
    <div class="system-settings-tabs"><span class="segmented-indicator"></span></div>`;
  // Out of layout; still receives all production media/container rules.
  specimens.style.cssText = "position:fixed;left:-10000px;top:0;width:300px;pointer-events:none";
  d.body.append(specimens);
  const sample = (selector: string) => specimens.querySelector<HTMLElement>(selector)!;
  const danger = token("danger"), status = token("status-blue");
  const originalSwatch = w.getComputedStyle(sample(".color-chip-swatch")).backgroundColor;
  for (const theme of ["light", "dark"]) {
    frame.style.width = "1440px"; frame.style.height = "400px"; await pause();
    click(`[data-theme-option="${theme}"]`); await open();
    let previousThumb = "";
    for (const preset of ["purple", "blue"]) {
      click(`[data-appearance-preset="${preset}"]`); click('[data-background-tone="neutral"]'); await pause();
      const label = `${page}/${theme}/${preset}`;
      for (const e of d.querySelectorAll<HTMLElement>('#appearanceApply, .appearance-tones [aria-pressed="true"], .appearance-preset[aria-pressed="true"]')) {
        const selector = e.id || e.className;
        e.setAttribute("data-qa-focus", "");
        const style = w.getComputedStyle(e);
        check(`${label}: ${selector} has visible external focus`, style.outlineStyle === "solid" && parseFloat(style.outlineWidth) >= 2
          && parseFloat(style.outlineOffset) >= 2
          && colorContrast(hex(style.outlineColor), hex(w.getComputedStyle(find("#appearancePopover")).backgroundColor)) >= 3);
        e.removeAttribute("data-qa-focus");
      }
      const thumb = token("scrollbar-thumb"), track = token("scrollbar-track");
      check(`${label}: scrollbar follows hue on neutral background`, thumb !== previousThumb && new Set(rgba(thumb).slice(0, 3)).size > 1);
      previousThumb = thumb;
      check(`${label}: scrollbar contrast`, colorContrast(hex(thumb), hex(track)) >= 3);
      const panel = find(".appearance-settings");
      check(`${label}: short window really scrolls`, panel.scrollHeight > panel.clientHeight);
      for (const selector of [".appearance-settings", ".sidebar-content", ".task-active-list", ".prompt-editor",
        ".gallery-drawer-main", ".prompt-template-body", ".mobile-sheet-content"]) {
        for (const e of d.querySelectorAll<HTMLElement>(selector)) {
          const style = w.getComputedStyle(e);
          check(`${label}: ${selector} scrollbar themed`, style.scrollbarColor !== "auto" && style.scrollbarWidth === "thin");
        }
      }
      const dashboard = d.querySelector(".dashboard");
      if (dashboard) check(`${label}: intentionally hidden scrollbar preserved`, w.getComputedStyle(dashboard).scrollbarWidth === "none");
      for (const selector of [".add-upload-to-gallery", ".thumb-edited-badge"]) {
        const e = sample(selector);
        for (const hover of [false, true]) {
          e.toggleAttribute("data-qa-hover", hover);
          const style = w.getComputedStyle(e);
          check(`${label}: ${selector}/${hover} opaque readable image action`, rgba(style.backgroundColor)[3] === 255
            && style.opacity === "1" && colorContrast(hex(style.color), hex(style.backgroundColor)) >= 4.5);
        }
        e.removeAttribute("data-qa-hover");
      }
      for (const selector of [".gallery-edit-popover", ".prompt-popover"]) {
        const style = w.getComputedStyle(sample(selector));
        check(`${label}: ${selector} border and shadow themed`, same(style.borderTopColor, token("line")) && style.boxShadow.includes("rgba(0, 0, 0,"));
      }
      for (const selector of [".lightbox-zoom-toolbar", ".lightbox-zoom-mode"]) {
        const style = w.getComputedStyle(sample(selector));
        check(`${label}: ${selector} readable`, colorContrast(hex(style.color), hex(style.backgroundColor)) >= 4.5);
      }
      const indicator = w.getComputedStyle(sample(".segmented-indicator"));
      check(`${label}: selected indicator follows primary`, same(indicator.backgroundColor, token("primary")) && !indicator.boxShadow.includes("40, 116, 85"));
      const meta = d.querySelector<HTMLMetaElement>('meta[name="theme-color"]')!;
      check(`${label}: browser chrome follows draft and theme`, same(meta.content, token("primary")));
      const manifest = await (await fetch(d.querySelector<HTMLLinkElement>('link[rel="manifest"]')!.href)).json();
      check(`${label}: manifest colors follow draft; identity stable`, same(manifest.theme_color, token("primary"))
        && same(manifest.background_color, token("bg")) && manifest.id === "/" && manifest.start_url === "/");
      check(`${label}: paint swatch unchanged`, w.getComputedStyle(sample(".color-chip-swatch")).backgroundColor === originalSwatch);
    }
    // Manual mode changes retain the unsaved seed and update chrome via the observer.
    click(`[data-theme-option="${theme === "light" ? "dark" : "light"}"]`); await pause();
    check(`${page}: mode switch updates draft chrome`, same(d.querySelector<HTMLMetaElement>('meta[name="theme-color"]')!.content, token("primary")));
    click("#appearanceCancel"); await pause();
    check(`${page}: cancel restores chrome with the page`, same(d.querySelector<HTMLMetaElement>('meta[name="theme-color"]')!.content, token("primary")));
  }
  // Compare semantic colors in their original mode, independently of skin.
  click('[data-theme-option="dark"]'); await pause();
  check(`${page}: semantic status tokens remain independent`, token("danger") === danger && token("status-blue") === status);
  specimens.remove(); styles.remove(); link.disabled = false;
  frame.style.width = "1440px"; frame.style.height = "900px"; await pause();
}

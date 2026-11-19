import { APPEARANCE_CHANGE_EVENT, APPEARANCE_STORAGE_KEY, DEFAULT_APPEARANCE, applyAppearance, appearanceTokens, readAppearance, persistAppearance, type Appearance, type BackgroundTone } from "./appearance";
import { translate, LOCALE_CHANGE_EVENT } from "./i18n";

let draft: Appearance = { ...DEFAULT_APPEARANCE };
let draftEdited = false;
let initialized = false;
let returnFocus: HTMLElement | null = null;
let openRequest = 0;
const presets = [
  { id: "default", color: "#457B66", background: "tinted" },
  { id: "blue", color: "#386FC4", background: "cool" },
  { id: "purple", color: "#8057B0", background: "neutral" },
  { id: "amber", color: "#A66D25", background: "warm" },
] as const;
const element = <T extends HTMLElement>(id: string) => document.getElementById(id) as T | null;

function feedback(key = ""): void {
  const status = element("appearanceStatus");
  if (status) { status.dataset.message = key; status.textContent = key ? translate(key) : ""; }
}
function sync(): void {
  const hex = element<HTMLInputElement>("appearanceHex");
  const picker = element<HTMLInputElement>("appearanceColor");
  if (!hex || !picker) return;
  hex.value = picker.value = draft.primary;
  hex.setAttribute("aria-invalid", "false");
  element<HTMLButtonElement>("appearanceApply")!.disabled = false;
  document.querySelectorAll<HTMLElement>("[data-appearance-preset]").forEach(button => {
    const preset = presets.find(p => p.id === button.dataset.appearancePreset)!;
    button.setAttribute("aria-pressed", String(preset.id === "default" ? draft.preset === "default"
      : draft.preset === "custom" && draft.primary === preset.color && draft.background === preset.background));
  });
  document.querySelectorAll<HTMLElement>("[data-background-tone]").forEach(button => {
    button.setAttribute("aria-pressed", String(button.dataset.backgroundTone === draft.background));
  });
  updatePresetPreviews();
}
function updatePresetPreviews(): void {
  const dark = document.documentElement.dataset.theme === "dark";
  document.querySelectorAll<HTMLElement>("[data-appearance-preset]").forEach(button => {
    const preset = presets.find(p => p.id === button.dataset.appearancePreset)!;
    const tokens = appearanceTokens({ version: 1, preset: "custom", primary: preset.color, background: preset.background }, dark);
    const original = dark ? { bg: "#101815", surface: "#17221e", primary: "#72b79b", text: "#e7f0ec" }
      : { bg: "#f3f6f4", surface: "#ffffff", primary: "#457b66", text: "#1f352f" };
    for (const name of ["bg", "surface", "primary", "text"] as const) {
      button.style.setProperty(`--preview-${name}`, preset.id === "default" ? original[name] : tokens[name]!);
    }
  });
}
function restoreSavedAppearance(): void {
  if (!initialized) return;
  draftEdited = false;
  draft = readAppearance(); applyAppearance(draft); sync(); feedback();
}
export function closeAppearancePopover(restoreFocus = true): void {
  openRequest++;
  const popover = element("appearancePopover");
  if (!popover || popover.hidden) return;
  popover.hidden = true;
  element("appearanceTrigger")?.setAttribute("aria-expanded", "false");
  restoreSavedAppearance();
  if (restoreFocus) {
    const target = returnFocus?.getClientRects().length && !returnFocus.closest(".hidden, [hidden], [inert]")
      ? returnFocus : document.querySelector<HTMLElement>(".mobile-more-button");
    target?.focus({ preventScroll: true });
  }
  returnFocus = null;
}
function positionPopover(): void {
  const popover = element("appearancePopover");
  if (!popover || popover.hidden) return;
  const trigger = element("appearanceTrigger")!;
  const anchor = trigger.getClientRects().length ? trigger : document.querySelector<HTMLElement>(".mobile-more-button")!;
  const viewport = window.visualViewport;
  const leftEdge = viewport?.offsetLeft || 0, topEdge = viewport?.offsetTop || 0;
  const width = viewport?.width || window.innerWidth, height = viewport?.height || window.innerHeight;
  const margin = 12;
  popover.style.width = `${Math.min(320, width - margin * 2)}px`;
  popover.style.maxHeight = `${height - margin * 2}px`;
  const tones = popover.querySelector<HTMLElement>(".appearance-tones")!;
  tones.classList.remove("appearance-tones-wrapped");
  if (Array.from(tones.children).some(button => button.scrollWidth > button.clientWidth + 1)) {
    tones.classList.add("appearance-tones-wrapped");
  }
  const rect = anchor.getBoundingClientRect();
  const below = rect.bottom + 8;
  const top = below + popover.offsetHeight <= topEdge + height - margin ? below
    : Math.max(topEdge + margin, rect.top - popover.offsetHeight - 8);
  popover.style.left = `${Math.max(leftEdge + margin, Math.min(rect.right - popover.offsetWidth, leftEdge + width - popover.offsetWidth - margin))}px`;
  popover.style.top = `${Math.max(topEdge + margin, top)}px`;
}
function openPopover(): void {
  const request = ++openRequest;
  // Let the settings/mobile sheet release its focus and inert state first.
  requestAnimationFrame(() => {
    if (request !== openRequest) return;
    restoreSavedAppearance();
    const trigger = element("appearanceTrigger")!;
    returnFocus = trigger.getClientRects().length ? trigger : document.querySelector<HTMLElement>(".mobile-more-button");
    element("appearancePopover")!.hidden = false;
    trigger.setAttribute("aria-expanded", "true");
    positionPopover();
    element("appearancePopover")!.querySelector<HTMLElement>('[data-appearance-preset][aria-pressed="true"]')?.focus({ preventScroll: true });
    if (!element("appearancePopover")!.contains(document.activeElement)) element("appearanceHex")!.focus({ preventScroll: true });
  });
}
export function initAppearanceSettings(closeSettings: () => boolean): void {
  if (initialized) return;
  const panel = element("systemSettingsLanguagePanel");
  const scroll = panel?.querySelector(".system-settings-scroll");
  const switcher = element("themeSwitcher");
  if (!panel || !scroll || !switcher) return;
  initialized = true;
  const trigger = document.createElement("button");
  trigger.id = "appearanceTrigger";
  trigger.type = "button";
  trigger.className = "theme-option appearance-trigger";
  trigger.setAttribute("aria-controls", "appearancePopover");
  trigger.setAttribute("aria-expanded", "false");
  trigger.setAttribute("aria-haspopup", "dialog");
  trigger.innerHTML = '<span class="appearance-current-color" aria-hidden="true"></span><svg width="10" height="10" viewBox="0 0 10 10" aria-hidden="true"><path fill="currentColor" d="m1 3 4 4 4-4Z"/></svg>';
  switcher.append(trigger);
  const shortcut = document.createElement("button");
  shortcut.id = "appearanceShortcut";
  shortcut.type = "button";
  shortcut.className = "ghost-button appearance-shortcut";
  shortcut.dataset.i18n = "appearance.open";
  scroll.append(shortcut);
  const popover = document.createElement("section");
  popover.id = "appearancePopover";
  popover.className = "appearance-popover";
  popover.hidden = true;
  popover.setAttribute("role", "dialog");
  popover.setAttribute("aria-modal", "false");
  popover.setAttribute("aria-labelledby", "appearanceTitle");
  popover.innerHTML = `<header class="appearance-heading"><strong id="appearanceTitle" data-i18n="appearance.skin"></strong><div class="appearance-heading-actions">
    <button id="appearanceReset" class="ghost-button" type="button"><svg width="16" height="16" viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" d="M4 3v7h7L8.3 7.3A6 6 0 1 1 6 12H3a9 9 0 1 0 3.2-6.9Z"/></svg></button>
    <button id="appearanceClose" class="ghost-button drawer-close-button" type="button"><svg width="16" height="16" viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" d="m6.4 4.3 5.6 5.6 5.6-5.6 2.1 2.1-5.6 5.6 5.6 5.6-2.1 2.1-5.6-5.6-5.6 5.6-2.1-2.1 5.6-5.6-5.6-5.6Z"/></svg></button></div></header>`;
  const section = document.createElement("div");
  section.className = "appearance-settings";
  section.innerHTML = `
    <div class="field">
      <div class="appearance-presets" role="group" aria-label="${translate("appearance.skin")}" data-i18n-attr="aria-label:appearance.skin">
        ${presets.map(p => `<button type="button" class="appearance-preset" data-appearance-preset="${p.id}" aria-pressed="false"><span class="appearance-preview" aria-hidden="true"><span class="appearance-preview-rail"></span><span class="appearance-preview-page"><span>Aa</span><i></i></span></span><span data-i18n="appearance.${p.id}"></span></button>`).join("")}
      </div>
    </div>
    <div class="field"><label for="appearanceHex" data-i18n="appearance.primary"></label>
      <div class="appearance-color-row">
        <input id="appearanceColor" type="color" aria-label="${translate("appearance.primary")}" data-i18n-attr="aria-label:appearance.primary" />
        <input id="appearanceHex" class="control" type="text" maxlength="7" spellcheck="false" autocomplete="off" placeholder="#457B66" aria-describedby="appearanceHint appearanceStatus" />
      </div>
      <span id="appearanceHint" class="field-hint" data-i18n="appearance.hint"></span>
    </div>
    <div class="field"><span data-i18n="appearance.background"></span>
      <div class="appearance-tones" role="group" aria-label="${translate("appearance.background")}" data-i18n-attr="aria-label:appearance.background">
        ${["neutral", "warm", "cool", "tinted"].map(t => `<button type="button" class="ghost-button" data-background-tone="${t}" aria-pressed="false" data-i18n="appearance.${t}"></button>`).join("")}
      </div>
    </div>`;
  popover.append(section);
  const actions = document.createElement("div");
  actions.className = "appearance-actions";
  actions.innerHTML = `<p id="appearanceStatus" role="status" aria-live="polite"></p>
    <button id="appearanceCancel" type="button" class="ghost-button" data-i18n="appearance.cancel"></button>
    <button id="appearanceApply" type="button" class="run-button" data-i18n="appearance.apply"></button>`;
  popover.append(actions);
  document.body.append(popover);
  const localize = () => {
    popover.querySelectorAll<HTMLElement>("[data-i18n]").forEach(e => { e.textContent = translate(e.dataset.i18n!); });
    popover.querySelectorAll<HTMLElement>('[role="group"]').forEach(group => group.setAttribute("aria-label", translate(group.classList.contains("appearance-presets") ? "appearance.skin" : "appearance.background")));
    trigger.title = translate("appearance.open");
    trigger.setAttribute("aria-label", translate("appearance.open"));
    shortcut.textContent = translate("appearance.open");
    element("appearanceColor")!.setAttribute("aria-label", translate("appearance.primary"));
    element("appearanceClose")!.setAttribute("aria-label", translate("action.close"));
    element("appearanceReset")!.setAttribute("aria-label", translate("appearance.reset"));
    element("appearanceReset")!.title = translate("appearance.reset");
    feedback(element("appearanceStatus")?.dataset.message);
    positionPopover();
  };
  localize();
  document.addEventListener(LOCALE_CHANGE_EVENT, localize);
  const preview = () => { draftEdited = true; applyAppearance(draft); sync(); feedback(); };
  trigger.addEventListener("click", () => { if (popover.hidden) openPopover(); else closeAppearancePopover(); });
  shortcut.addEventListener("click", () => { if (closeSettings()) openPopover(); });
  element("appearanceReset")!.addEventListener("click", () => { draft = { ...DEFAULT_APPEARANCE }; preview(); });
  section.addEventListener("click", event => {
    const button = (event.target as HTMLElement).closest<HTMLElement>("button");
    if (!button) return;
    if (button.dataset.appearancePreset) {
      const p = presets.find(p => p.id === button.dataset.appearancePreset)!;
      draft = p.id === "default" ? { ...DEFAULT_APPEARANCE } : { version: 1, preset: "custom", primary: p.color, background: p.background };
    } else if (button.dataset.backgroundTone) {
      draft = { ...draft, preset: "custom", background: button.dataset.backgroundTone as BackgroundTone };
    } else return;
    preview();
  });
  element<HTMLInputElement>("appearanceColor")!.addEventListener("input", event => {
    draft = { ...draft, preset: "custom", primary: (event.target as HTMLInputElement).value.toUpperCase() }; preview();
  });
  element<HTMLInputElement>("appearanceHex")!.addEventListener("input", event => {
    // Incomplete input is also a local edit and must survive external saves.
    draftEdited = true;
    const input = event.target as HTMLInputElement;
    const valid = /^#[\da-f]{6}$/i.test(input.value);
    input.setAttribute("aria-invalid", String(!valid));
    element<HTMLButtonElement>("appearanceApply")!.disabled = !valid;
    if (!valid) { feedback("appearance.invalid"); return; }
    draft = { ...draft, preset: "custom", primary: input.value.toUpperCase() }; preview();
  });
  element("appearanceCancel")!.addEventListener("click", () => closeAppearancePopover());
  element("appearanceClose")!.addEventListener("click", () => closeAppearancePopover());
  element("appearanceApply")!.addEventListener("click", () => {
    if (!persistAppearance(draft)) { feedback("appearance.saveFailed"); return; }
    document.dispatchEvent(new Event(APPEARANCE_CHANGE_EVENT));
    closeAppearancePopover();
  });
  document.addEventListener("click", event => {
    if (!popover.hidden && !popover.contains(event.target as Node) && !switcher.contains(event.target as Node)) closeAppearancePopover(false);
  }, true);
  document.addEventListener("focusin", event => {
    if (!popover.hidden && !popover.contains(event.target as Node) && !switcher.contains(event.target as Node)) closeAppearancePopover(false);
  });
  document.addEventListener("keydown", event => {
    if (popover.hidden) return;
    if (event.key === "Escape") { event.preventDefault(); event.stopImmediatePropagation(); closeAppearancePopover(); }
    if (event.key === "Tab") {
      const buttons = Array.from(popover.querySelectorAll<HTMLElement>("button:not(:disabled), input:not(:disabled)"));
      const first = buttons[0]!, last = buttons[buttons.length - 1]!;
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
    }
  }, true);
  window.addEventListener("resize", positionPopover);
  window.visualViewport?.addEventListener("resize", positionPopover);
  window.visualViewport?.addEventListener("scroll", positionPopover);
  new ResizeObserver(positionPopover).observe(popover);
  new MutationObserver(updatePresetPreviews).observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
  window.addEventListener("storage", event => {
    if (event.key !== APPEARANCE_STORAGE_KEY && event.key !== null) return;
    // Keep the preview and input intact while editing. Closing reads the latest
    // saved value; applying explicitly writes this draft over external changes.
    if (popover.hidden || !draftEdited) restoreSavedAppearance();
  });
  document.addEventListener(APPEARANCE_CHANGE_EVENT, restoreSavedAppearance);
  restoreSavedAppearance();
}

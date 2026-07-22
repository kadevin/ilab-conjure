import { getLegacyBridge } from "./state";
import { refreshSegmentedIndicators } from "./segmented-indicator";

let systemSettingsFeatureInitialized = false;
let systemSettingsHeightAnimationToken = 0;
let systemSettingsHeightAnimationTimer: number | undefined;

type SystemSettingsTab = "api" | "codex" | "network" | "language" | "storage";

const MIN_SYSTEM_SETTINGS_MODAL_EDGE = 30;
const VALID_TABS = new Set<SystemSettingsTab>(["api", "codex", "network", "language", "storage"]);

function normalizedTab(tab: any): SystemSettingsTab {
  return VALID_TABS.has(tab) ? tab : "api";
}

function maybeCall(name: string, ...args: any[]): void {
  const method = getLegacyBridge().methods[name];
  if (typeof method === "function") method(...args);
}

function systemSettingsPanel(): HTMLElement | null {
  const { els } = getLegacyBridge();
  return els.systemSettingsModal?.querySelector(".system-settings-modal-panel") || null;
}

function shouldAnimateSystemSettingsHeight(): boolean {
  const { els } = getLegacyBridge();
  if (els.systemSettingsModal?.classList.contains("hidden")) return false;
  return !window.matchMedia?.("(prefers-reduced-motion: reduce)")?.matches;
}

function clearSystemSettingsHeightAnimation(panel: HTMLElement): void {
  systemSettingsHeightAnimationToken += 1;
  if (systemSettingsHeightAnimationTimer !== undefined) {
    window.clearTimeout(systemSettingsHeightAnimationTimer);
    systemSettingsHeightAnimationTimer = undefined;
  }
  panel.classList.remove("is-height-animating");
  panel.style.height = "";
}

function positionSystemSettingsModal(): void {
  const { els } = getLegacyBridge();
  const modal = els.systemSettingsModal as HTMLElement | null;
  const panel = systemSettingsPanel();
  if (!modal || !panel || modal.classList.contains("hidden")) return;
  const viewportHeight = window.innerHeight || document.documentElement.clientHeight || 0;
  const panelHeight = panel.getBoundingClientRect().height;
  const centeredTop = Math.floor((viewportHeight - panelHeight) / 2);
  const top = Math.max(MIN_SYSTEM_SETTINGS_MODAL_EDGE, centeredTop);
  modal.style.setProperty("--system-settings-modal-top", `${top}px`);
}

function systemSettingsTargetHeight(panel: HTMLElement): number {
  const style = window.getComputedStyle(panel);
  const borderHeight = (parseFloat(style.borderTopWidth) || 0) + (parseFloat(style.borderBottomWidth) || 0);
  const naturalHeight = Math.ceil(panel.scrollHeight + borderHeight);
  const maxHeight = parseFloat(style.maxHeight);
  return Number.isFinite(maxHeight) ? Math.min(naturalHeight, Math.ceil(maxHeight)) : naturalHeight;
}

function animateSystemSettingsPanelHeight(panel: HTMLElement, beforeHeight: number): void {
  const afterHeight = systemSettingsTargetHeight(panel);
  if (Math.abs(afterHeight - beforeHeight) < 1) {
    clearSystemSettingsHeightAnimation(panel);
    return;
  }
  systemSettingsHeightAnimationToken += 1;
  const token = systemSettingsHeightAnimationToken;
  panel.classList.add("is-height-animating");
  panel.style.height = `${beforeHeight}px`;
  panel.getBoundingClientRect();
  window.requestAnimationFrame(() => {
    if (token !== systemSettingsHeightAnimationToken) return;
    panel.style.height = `${afterHeight}px`;
  });
  const cleanup = (event?: TransitionEvent): void => {
    if (event && (event.target !== panel || event.propertyName !== "height")) return;
    if (token !== systemSettingsHeightAnimationToken) return;
    systemSettingsHeightAnimationToken += 1;
    if (systemSettingsHeightAnimationTimer !== undefined) {
      window.clearTimeout(systemSettingsHeightAnimationTimer);
      systemSettingsHeightAnimationTimer = undefined;
    }
    panel.removeEventListener("transitionend", cleanup);
    panel.classList.remove("is-height-animating");
    panel.style.height = "";
  };
  panel.addEventListener("transitionend", cleanup);
  systemSettingsHeightAnimationTimer = window.setTimeout(() => cleanup(), 320);
}

export function setSystemSettingsTab(tab: any, options: { refresh?: boolean } = {}): void {
  const selected = normalizedTab(tab);
  const { els } = getLegacyBridge();
  const panel = systemSettingsPanel();
  const animateHeight = Boolean(panel && shouldAnimateSystemSettingsHeight());
  const beforeHeight = animateHeight && panel ? panel.getBoundingClientRect().height : 0;
  if (animateHeight && panel) clearSystemSettingsHeightAnimation(panel);
  const buttons = Array.from(els.systemSettingsTabs?.querySelectorAll("[data-system-settings-tab]") || []);
  buttons.forEach((button: any) => {
    const active = button.dataset.systemSettingsTab === selected;
    button.classList.toggle("active", active);
    button.setAttribute("aria-selected", active ? "true" : "false");
    button.tabIndex = active ? 0 : -1;
  });
  [
    ["api", els.systemSettingsApiPanel],
    ["codex", els.systemSettingsCodexPanel],
    ["network", els.systemSettingsNetworkPanel],
    ["language", els.systemSettingsLanguagePanel],
    ["storage", els.systemSettingsStoragePanel],
  ].forEach(([name, panel]: any[]) => {
    if (!panel) return;
    const active = name === selected;
    panel.hidden = !active;
    panel.setAttribute("aria-hidden", active ? "false" : "true");
  });
  if (options.refresh === false) return;
  if (selected === "storage") maybeCall("refreshSettings");
  if (selected === "network") maybeCall("refreshNetworkEgressSettings");
  if (selected === "api" || selected === "codex") {
    maybeCall("setApiSettingsFeedback", "", "");
    maybeCall("populateApiSettingsForm");
    maybeCall("updateModeSpecificSettings");
  }
  refreshSegmentedIndicators();
  if (animateHeight && panel) animateSystemSettingsPanelHeight(panel, beforeHeight);
}

export function openSystemSettingsModal(tab: any = "api"): void {
  const { els } = getLegacyBridge();
  const wasHidden = els.systemSettingsModal?.classList.contains("hidden") ?? true;
  setSystemSettingsTab(tab);
  els.systemSettingsModal?.classList.remove("hidden");
  els.systemSettingsModal?.setAttribute("aria-hidden", "false");
  if (wasHidden) positionSystemSettingsModal();
  refreshSegmentedIndicators();
}

export function closeSystemSettingsModal(): void {
  const { els } = getLegacyBridge();
  els.systemSettingsModal?.classList.add("hidden");
  els.systemSettingsModal?.setAttribute("aria-hidden", "true");
  (els.systemSettingsModal as HTMLElement | null)?.style.removeProperty("--system-settings-modal-top");
}

export function openSystemSettingsFromUrl(): void {
  const params = new URLSearchParams(window.location.search);
  if (params.get("settings") !== "1") return;
  const requestedTab = params.get("settingsTab") || params.get("tab");
  const settingsTab = requestedTab && VALID_TABS.has(requestedTab as SystemSettingsTab)
    ? requestedTab
    : "";
  openSystemSettingsModal(settingsTab || "api");
  const url = new URL(window.location.href);
  url.searchParams.delete("settings");
  url.searchParams.delete("settingsTab");
  url.searchParams.delete("tab");
  window.history.replaceState(window.history.state, "", `${url.pathname}${url.search}${url.hash}`);
}

function handleSystemSettingsTabClick(event: Event): void {
  const target = event.target as HTMLElement | null;
  const button = target?.closest?.("[data-system-settings-tab]") as HTMLElement | null;
  if (!button) return;
  event.preventDefault();
  setSystemSettingsTab(button.dataset.systemSettingsTab || "api");
}

function handleSystemSettingsResize(): void {
  positionSystemSettingsModal();
}

export function initSystemSettingsFeature(): void {
  if (systemSettingsFeatureInitialized) return;
  systemSettingsFeatureInitialized = true;
  const { els } = getLegacyBridge();
  els.systemSettingsTabs?.addEventListener("click", handleSystemSettingsTabClick);
  window.addEventListener("resize", handleSystemSettingsResize);
  Object.assign(getLegacyBridge().methods, {
    setSystemSettingsTab,
    openSystemSettingsModal,
    openSystemSettingsFromUrl,
    closeSystemSettingsModal,
  });
}

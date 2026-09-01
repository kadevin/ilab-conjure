import { getLegacyBridge } from "./state";
import { refreshSegmentedIndicators } from "./segmented-indicator";
import { translate } from "./i18n";

let systemSettingsFeatureInitialized = false;
let systemSettingsHeightAnimationToken = 0;
let systemSettingsHeightAnimationTimer: number | undefined;
let systemSettingsReturnFocus: HTMLElement | null = null;
let userConfigBackupOpen = false;
let userConfigBackupTrigger: HTMLElement | null = null;
let storagePanelScrollTop = 0;

type SystemSettingsTab = "api" | "network" | "language" | "storage";

const MIN_SYSTEM_SETTINGS_MODAL_EDGE = 30;
const VALID_TABS = new Set<SystemSettingsTab>(["api", "network", "language", "storage"]);

function normalizedTab(tab: any): SystemSettingsTab {
  if (tab === "codex") return "api";
  return VALID_TABS.has(tab) ? tab : "api";
}

function maybeCall(name: string, ...args: any[]): any {
  const method = getLegacyBridge().methods[name];
  if (typeof method === "function") return method(...args);
  return undefined;
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
  if (userConfigBackupOpen) closeUserConfigBackupView({ restoreFocus: false, force: true });
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
  if (selected === "network") maybeCall("refreshNetworkEgress");
  if (selected === "api") {
    maybeCall("setApiSettingsFeedback", "", "");
    maybeCall("populateApiSettingsForm");
    maybeCall("updateModeSpecificSettings");
  }
  refreshSegmentedIndicators();
  if (animateHeight && panel) animateSystemSettingsPanelHeight(panel, beforeHeight);
}

export function userConfigBackupViewIsOpen(): boolean {
  return userConfigBackupOpen;
}

export function openUserConfigBackupView(trigger?: HTMLElement): void {
  const { els } = getLegacyBridge();
  if (userConfigBackupOpen) return;
  setSystemSettingsTab("storage");
  userConfigBackupOpen = true;
  userConfigBackupTrigger = trigger ?? (
    document.activeElement instanceof HTMLElement ? document.activeElement : null
  );
  storagePanelScrollTop = Number(els.systemSettingsStoragePanel?.scrollTop || 0);
  const panel = systemSettingsPanel();
  const animateHeight = Boolean(panel && shouldAnimateSystemSettingsHeight());
  const beforeHeight = animateHeight && panel ? panel.getBoundingClientRect().height : 0;
  if (animateHeight && panel) clearSystemSettingsHeightAnimation(panel);
  if (els.systemSettingsTabs instanceof HTMLElement) {
    els.systemSettingsTabs.hidden = true;
    els.systemSettingsTabs.inert = true;
    els.systemSettingsTabs.setAttribute("aria-hidden", "true");
  }
  [
    els.systemSettingsApiPanel,
    els.systemSettingsNetworkPanel,
    els.systemSettingsLanguagePanel,
    els.systemSettingsStoragePanel,
  ].forEach((settingsPanel: HTMLElement | null) => {
    if (!settingsPanel) return;
    settingsPanel.hidden = true;
    settingsPanel.inert = true;
    settingsPanel.setAttribute("aria-hidden", "true");
  });
  if (els.userConfigBackupView instanceof HTMLElement) {
    els.userConfigBackupView.hidden = false;
    els.userConfigBackupView.inert = false;
    els.userConfigBackupView.setAttribute("aria-hidden", "false");
  }
  els.userConfigBackupBackButton?.classList.remove("hidden");
  if (els.systemSettingsTitle) {
    els.systemSettingsTitle.dataset.i18n = "userConfigBackup.title";
    els.systemSettingsTitle.textContent = translate("userConfigBackup.title");
  }
  maybeCall("openUserConfigBackupController");
  refreshSegmentedIndicators();
  if (animateHeight && panel) animateSystemSettingsPanelHeight(panel, beforeHeight);
  (els.userConfigBackupBackButton as HTMLElement | null)?.focus({ preventScroll: true });
}

export function closeUserConfigBackupView(
  options: { restoreFocus?: boolean; force?: boolean; closeModal?: boolean } = {},
): boolean {
  if (!userConfigBackupOpen) return true;
  if (!options.force && maybeCall("guardUserConfigBackupClose", options.closeModal === true) === false) return false;
  const { els } = getLegacyBridge();
  const panel = systemSettingsPanel();
  const animateHeight = Boolean(panel && shouldAnimateSystemSettingsHeight());
  const beforeHeight = animateHeight && panel ? panel.getBoundingClientRect().height : 0;
  if (animateHeight && panel) clearSystemSettingsHeightAnimation(panel);
  userConfigBackupOpen = false;
  if (els.userConfigBackupView instanceof HTMLElement) {
    els.userConfigBackupView.hidden = true;
    els.userConfigBackupView.inert = true;
    els.userConfigBackupView.setAttribute("aria-hidden", "true");
  }
  if (els.systemSettingsTabs instanceof HTMLElement) {
    els.systemSettingsTabs.hidden = false;
    els.systemSettingsTabs.inert = false;
    els.systemSettingsTabs.setAttribute("aria-hidden", "false");
  }
  els.userConfigBackupBackButton?.classList.add("hidden");
  if (els.systemSettingsTitle) {
    els.systemSettingsTitle.dataset.i18n = "systemSettings.title";
    els.systemSettingsTitle.textContent = translate("systemSettings.title");
  }
  [
    ["api", els.systemSettingsApiPanel],
    ["network", els.systemSettingsNetworkPanel],
    ["language", els.systemSettingsLanguagePanel],
    ["storage", els.systemSettingsStoragePanel],
  ].forEach(([name, settingsPanel]: any[]) => {
    if (!(settingsPanel instanceof HTMLElement)) return;
    settingsPanel.inert = false;
    const active = name === "storage";
    settingsPanel.hidden = !active;
    settingsPanel.setAttribute("aria-hidden", active ? "false" : "true");
  });
  setSystemSettingsTab("storage", { refresh: false });
  if (els.systemSettingsStoragePanel) els.systemSettingsStoragePanel.scrollTop = storagePanelScrollTop;
  maybeCall("closeUserConfigBackupController");
  refreshSegmentedIndicators();
  if (animateHeight && panel) animateSystemSettingsPanelHeight(panel, beforeHeight);
  if (options.restoreFocus !== false && userConfigBackupTrigger?.isConnected) {
    userConfigBackupTrigger.focus({ preventScroll: true });
  }
  userConfigBackupTrigger = null;
  return true;
}

export function openSystemSettingsModal(tab: any = "api"): void {
  const { els } = getLegacyBridge();
  const modal = els.systemSettingsModal as HTMLElement | null;
  const wasHidden = modal?.classList.contains("hidden") ?? true;
  if (wasHidden) {
    const activeElement = document.activeElement;
    systemSettingsReturnFocus = activeElement instanceof HTMLElement
      && activeElement !== document.body
      && !modal?.contains(activeElement)
      ? activeElement
      : null;
  }
  setSystemSettingsTab(tab);
  modal?.classList.remove("hidden");
  modal?.setAttribute("aria-hidden", "false");
  if (wasHidden) positionSystemSettingsModal();
  refreshSegmentedIndicators();
}

export function closeSystemSettingsModal(options: { force?: boolean } = {}): void {
  if (userConfigBackupOpen && !closeUserConfigBackupView({
    restoreFocus: false,
    force: options.force === true,
    closeModal: true,
  })) return;
  const { els } = getLegacyBridge();
  const modal = els.systemSettingsModal as HTMLElement | null;
  const activeElement = document.activeElement;
  if (modal && activeElement instanceof HTMLElement && modal.contains(activeElement)) {
    const returnFocus = systemSettingsReturnFocus;
    if (returnFocus?.isConnected && !returnFocus.closest("[inert]")) {
      returnFocus.focus({ preventScroll: true });
    }
    if (modal.contains(document.activeElement)) activeElement.blur();
  }
  systemSettingsReturnFocus = null;
  modal?.classList.add("hidden");
  modal?.setAttribute("aria-hidden", "true");
  modal?.style.removeProperty("--system-settings-modal-top");
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

function handleUserConfigBackupEntry(event: Event): void {
  const trigger = event.currentTarget;
  openUserConfigBackupView(trigger instanceof HTMLElement ? trigger : undefined);
}

function handleSystemSettingsKeydown(event: KeyboardEvent): void {
  if (event.key !== "Escape" || !userConfigBackupOpen) return;
  event.preventDefault();
  event.stopImmediatePropagation();
  closeUserConfigBackupView();
}

export function initSystemSettingsFeature(): void {
  if (systemSettingsFeatureInitialized) return;
  systemSettingsFeatureInitialized = true;
  const { els } = getLegacyBridge();
  els.systemSettingsTabs?.addEventListener("click", handleSystemSettingsTabClick);
  els.openUserConfigBackupButton?.addEventListener("click", handleUserConfigBackupEntry);
  els.userConfigBackupBackButton?.addEventListener("click", () => closeUserConfigBackupView());
  window.addEventListener("resize", handleSystemSettingsResize);
  document.addEventListener("keydown", handleSystemSettingsKeydown, true);
  Object.assign(getLegacyBridge().methods, {
    setSystemSettingsTab,
    openSystemSettingsModal,
    openSystemSettingsFromUrl,
    closeSystemSettingsModal,
    openUserConfigBackupView,
    closeUserConfigBackupView,
    userConfigBackupViewIsOpen,
  });
}

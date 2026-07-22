const HOST_SELECTORS = [
  ".radio-group:not(.ratio-group):not(.model-parameter-segmented-multiline):not(.model-aspect-ratio-grid)",
  "#authSourceGroup",
  "#systemSettingsTabs",
  ".history-view-toggle",
  ".history-sort-toggle",
];
const HOST_SELECTOR = HOST_SELECTORS.join(", ");
const BUTTON_SELECTOR = ".radio-btn, .auth-source-button, .system-settings-tab, .history-view-button, .history-sort-button";
const INDICATOR_CLASS = "segmented-indicator";
const HOST_CLASS = "segmented-indicator-host";
const READY_CLASS = "segmented-indicator-ready";

const initializedHosts = new WeakSet<HTMLElement>();
const scheduledFrames = new WeakMap<HTMLElement, number>();
let segmentedIndicatorsInitialized = false;
let resizeObserver: ResizeObserver | null = null;

function activeSegment(host: HTMLElement): HTMLElement | null {
  return host.querySelector<HTMLElement>(".radio-btn.active, .auth-source-button.active, .system-settings-tab.active, .history-view-button.active, .history-sort-button.active");
}

function ensureIndicator(host: HTMLElement): HTMLElement {
  const existing = Array.from(host.children).find((child) => child.classList.contains(INDICATOR_CLASS));
  if (existing instanceof HTMLElement) return existing;

  const indicator = document.createElement("span");
  indicator.className = INDICATOR_CLASS;
  indicator.setAttribute("aria-hidden", "true");
  host.insertBefore(indicator, host.firstElementChild);
  return indicator;
}

function updateIndicator(host: HTMLElement): boolean {
  scheduledFrames.delete(host);
  if (!host.isConnected) return false;

  const indicator = ensureIndicator(host);
  const active = activeSegment(host);
  if (!active) {
    host.classList.remove(READY_CLASS);
    indicator.style.setProperty("--segmented-indicator-opacity", "0");
    return false;
  }

  const hostRect = host.getBoundingClientRect();
  const activeRect = active.getBoundingClientRect();
  if (hostRect.width <= 0 || hostRect.height <= 0 || activeRect.width <= 0 || activeRect.height <= 0) {
    host.classList.remove(READY_CLASS);
    indicator.style.setProperty("--segmented-indicator-opacity", "0");
    return false;
  }
  const hostStyle = window.getComputedStyle(host);
  const borderLeft = Number.parseFloat(hostStyle.borderLeftWidth) || 0;
  const borderTop = Number.parseFloat(hostStyle.borderTopWidth) || 0;
  indicator.style.setProperty("--segmented-indicator-x", `${activeRect.left - hostRect.left - borderLeft}px`);
  indicator.style.setProperty("--segmented-indicator-y", `${activeRect.top - hostRect.top - borderTop}px`);
  indicator.style.setProperty("--segmented-indicator-width", `${activeRect.width}px`);
  indicator.style.setProperty("--segmented-indicator-height", `${activeRect.height}px`);
  indicator.style.setProperty("--segmented-indicator-opacity", "1");
  return true;
}

function commitIndicatorUpdate(host: HTMLElement): void {
  if (updateIndicator(host)) host.classList.add(READY_CLASS);
}

function scheduleIndicatorUpdate(host: HTMLElement): void {
  if (scheduledFrames.has(host)) return;
  scheduledFrames.set(host, window.requestAnimationFrame(() => commitIndicatorUpdate(host)));
}

function watchButtonClassChanges(host: HTMLElement): void {
  const observer = new MutationObserver(() => scheduleIndicatorUpdate(host));
  host.querySelectorAll(BUTTON_SELECTOR).forEach((button) => {
    observer.observe(button, { attributes: true, attributeFilter: ["class"] });
  });
}

function initHost(host: HTMLElement): boolean {
  if (initializedHosts.has(host)) return false;
  initializedHosts.add(host);
  host.classList.add(HOST_CLASS);
  ensureIndicator(host);
  host.addEventListener("click", () => scheduleIndicatorUpdate(host));
  watchButtonClassChanges(host);
  if ("ResizeObserver" in window) {
    resizeObserver ||= new ResizeObserver((entries) => {
      entries.forEach((entry) => scheduleIndicatorUpdate(entry.target as HTMLElement));
    });
    resizeObserver.observe(host);
  }
  commitIndicatorUpdate(host);
  return true;
}

export function refreshSegmentedIndicators(): void {
  document.querySelectorAll<HTMLElement>(HOST_SELECTOR).forEach((host) => {
    if (!initHost(host)) scheduleIndicatorUpdate(host);
  });
}

export function initSegmentedIndicatorFeature(): void {
  if (segmentedIndicatorsInitialized) return;
  segmentedIndicatorsInitialized = true;
  document.querySelectorAll<HTMLElement>(HOST_SELECTOR).forEach(initHost);
  window.addEventListener("resize", refreshSegmentedIndicators, { passive: true });
  (document as any).fonts?.ready?.then(refreshSegmentedIndicators).catch(() => {});
}

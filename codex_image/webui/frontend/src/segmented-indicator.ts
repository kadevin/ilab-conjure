const HOST_SELECTORS = [".radio-group:not(.ratio-group)", "#authSourceGroup", "#languageSwitcher", ".history-view-toggle", ".history-sort-toggle"];
const HOST_SELECTOR = HOST_SELECTORS.join(", ");
const BUTTON_SELECTOR = ".radio-btn, .auth-source-button, .language-option, .history-view-button, .history-sort-button";
const INDICATOR_CLASS = "segmented-indicator";
const HOST_CLASS = "segmented-indicator-host";

const initializedHosts = new WeakSet<HTMLElement>();
const scheduledFrames = new WeakMap<HTMLElement, number>();
let segmentedIndicatorsInitialized = false;
let resizeObserver: ResizeObserver | null = null;

function activeSegment(host: HTMLElement): HTMLElement | null {
  return host.querySelector<HTMLElement>(".radio-btn.active, .auth-source-button.active, .language-option.active, .history-view-button.active, .history-sort-button.active");
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

function updateIndicator(host: HTMLElement): void {
  scheduledFrames.delete(host);
  if (!host.isConnected) return;

  const indicator = ensureIndicator(host);
  const active = activeSegment(host);
  if (!active) {
    indicator.style.setProperty("--segmented-indicator-opacity", "0");
    return;
  }

  const hostRect = host.getBoundingClientRect();
  const activeRect = active.getBoundingClientRect();
  const hostStyle = window.getComputedStyle(host);
  const borderLeft = Number.parseFloat(hostStyle.borderLeftWidth) || 0;
  const borderTop = Number.parseFloat(hostStyle.borderTopWidth) || 0;
  indicator.style.setProperty("--segmented-indicator-x", `${activeRect.left - hostRect.left - borderLeft}px`);
  indicator.style.setProperty("--segmented-indicator-y", `${activeRect.top - hostRect.top - borderTop}px`);
  indicator.style.setProperty("--segmented-indicator-width", `${activeRect.width}px`);
  indicator.style.setProperty("--segmented-indicator-height", `${activeRect.height}px`);
  indicator.style.setProperty("--segmented-indicator-opacity", "1");
}

function scheduleIndicatorUpdate(host: HTMLElement): void {
  if (scheduledFrames.has(host)) return;
  scheduledFrames.set(host, window.requestAnimationFrame(() => updateIndicator(host)));
}

function watchButtonClassChanges(host: HTMLElement): void {
  const observer = new MutationObserver(() => scheduleIndicatorUpdate(host));
  host.querySelectorAll(BUTTON_SELECTOR).forEach((button) => {
    observer.observe(button, { attributes: true, attributeFilter: ["class"] });
  });
}

function initHost(host: HTMLElement): void {
  if (initializedHosts.has(host)) return;
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
  scheduleIndicatorUpdate(host);
}

function updateAllIndicators(): void {
  document.querySelectorAll<HTMLElement>(HOST_SELECTOR).forEach(scheduleIndicatorUpdate);
}

export function initSegmentedIndicatorFeature(): void {
  if (segmentedIndicatorsInitialized) return;
  segmentedIndicatorsInitialized = true;
  document.querySelectorAll<HTMLElement>(HOST_SELECTOR).forEach(initHost);
  window.addEventListener("resize", updateAllIndicators, { passive: true });
  (document as any).fonts?.ready?.then(updateAllIndicators).catch(() => {});
}

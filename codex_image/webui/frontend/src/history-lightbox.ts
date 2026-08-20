import { translate } from "./i18n";
import {
  bindLightboxZoomChrome,
  hideLightboxShortcutHint,
  isLightboxAtOrBelowFitScale,
  lightboxActionForKey,
  lightboxImageActualSizeScale,
  lightboxScaleFromWheel,
  lightboxSteppedScale,
  lightboxZoomChromeHtml,
  normalizeLightboxScale,
  showLightboxShortcutHint,
  shouldCloseLightboxFromClick,
  updateLightboxZoomChrome,
} from "./lightbox-controls";
import type {
  LightboxTaskDirection,
  LightboxTaskNavigation,
  LightboxTaskNavigationContext,
} from "./lightbox-controls";
import { escapeHtml } from "./webui-utils";

type HistoryLightboxState = {
  urls: string[];
  index: number;
  taskId: string;
  onTaskNavigate: HistoryLightboxTaskNavigation | null;
  scale: number;
  pointX: number;
  pointY: number;
  panning: boolean;
  startX: number;
  startY: number;
  isTransitioning: boolean;
};

export type HistoryLightboxTaskDirection = LightboxTaskDirection;
export type HistoryLightboxTaskNavigationContext = LightboxTaskNavigationContext;
export type HistoryLightboxTaskNavigation = LightboxTaskNavigation;
export type HistoryLightboxOptions = {
  taskId?: string;
  onTaskNavigate?: HistoryLightboxTaskNavigation;
};

let historyLightboxEl: HTMLDivElement | null = null;

const historyLightboxState: HistoryLightboxState = {
  urls: [],
  index: 0,
  taskId: "",
  onTaskNavigate: null,
  scale: 1,
  pointX: 0,
  pointY: 0,
  panning: false,
  startX: 0,
  startY: 0,
  isTransitioning: false,
};

function clampedHistoryLightboxIndex(index: number, count: number): number {
  return Math.min(Math.max(0, index), Math.max(0, count - 1));
}

function historyLightboxSlotIndexes(index: number, count: number) {
  const current = clampedHistoryLightboxIndex(index, count);
  return {
    previous: current > 0 ? current - 1 : null,
    current,
    next: current + 1 < count ? current + 1 : null,
  };
}

function historyLightboxImage(): HTMLImageElement | null {
  return historyLightboxEl?.querySelector<HTMLImageElement>("[data-history-lightbox-image]") || null;
}

function historyLightboxSlot(slot: "previous" | "current" | "next"): HTMLElement | null {
  return historyLightboxEl?.querySelector<HTMLElement>(`[data-history-lightbox-slot="${slot}"]`) || null;
}

function bindHistoryLightboxSlots(index = historyLightboxState.index): void {
  if (!historyLightboxEl || !historyLightboxState.urls.length) return;
  const slots = historyLightboxSlotIndexes(index, historyLightboxState.urls.length);
  (["previous", "current", "next"] as const).forEach((slotName) => {
    const slot = historyLightboxSlot(slotName);
    const image = slot?.querySelector<HTMLImageElement>("img") || null;
    const slotIndex = slots[slotName];
    const unavailable = slotIndex === null;
    slot?.classList.toggle("is-unavailable", unavailable);
    slot?.setAttribute("aria-hidden", unavailable ? "true" : "false");
    if (slot instanceof HTMLButtonElement) {
      slot.disabled = unavailable;
      slot.tabIndex = unavailable ? -1 : 0;
    }
    if (!image) return;
    if (unavailable) image.removeAttribute("src");
    else image.src = historyLightboxState.urls[slotIndex] || "";
  });
  historyLightboxEl.classList.toggle("is-single", historyLightboxState.urls.length === 1);
}

async function decodeHistoryLightboxBoundSlots(): Promise<void> {
  if (!historyLightboxEl) return;
  const images = Array.from(
    historyLightboxEl.querySelectorAll<HTMLImageElement>("[data-history-lightbox-slot] img[src]"),
  );
  await Promise.allSettled(images.map(async (image) => {
    if (!image.complete || image.naturalWidth === 0) {
      await new Promise<void>((resolve, reject) => {
        image.addEventListener("load", () => resolve(), { once: true });
        image.addEventListener("error", () => reject(new Error("History lightbox slot failed to load")), { once: true });
      });
    }
    if (typeof image.decode === "function") await image.decode();
  }));
}

async function preloadHistoryLightboxImage(url: string): Promise<HTMLImageElement> {
  const image = new Image();
  await new Promise<void>((resolve, reject) => {
    image.onload = () => resolve();
    image.onerror = () => reject(new Error("History lightbox image failed to load"));
    image.src = url;
    if (image.complete && image.naturalWidth > 0) resolve();
  });
  if (typeof image.decode === "function") {
    await image.decode().catch(() => undefined);
  }
  return image;
}

async function preloadHistoryLightboxSlotImages(index: number): Promise<Map<string, HTMLImageElement>> {
  const slots = historyLightboxSlotIndexes(index, historyLightboxState.urls.length);
  const urls = Array.from(new Set(
    Object.values(slots)
      .filter((slotIndex): slotIndex is number => slotIndex !== null)
      .map((slotIndex) => historyLightboxState.urls[slotIndex])
      .filter((url): url is string => Boolean(url)),
  ));
  const results = await Promise.allSettled(urls.map(async (url) => [url, await preloadHistoryLightboxImage(url)] as const));
  return new Map(
    results
      .filter((result): result is PromiseFulfilledResult<readonly [string, HTMLImageElement]> => result.status === "fulfilled")
      .map((result) => result.value),
  );
}

type HistoryLightboxRect = { left: number; top: number; width: number; height: number };

function historyLightboxEdgeRect(
  side: "previous" | "next",
  image: HTMLImageElement,
  peek: HTMLElement,
): HistoryLightboxRect {
  const peekRect = peek.getBoundingClientRect();
  const ratio = Math.max(0.05, image.naturalWidth / Math.max(1, image.naturalHeight));
  let height = peekRect.height;
  let width = height * ratio;
  const maxWidth = window.innerWidth * 0.62;
  if (width > maxWidth) {
    width = maxWidth;
    height = width / ratio;
  }
  return {
    left: side === "previous" ? peekRect.width - width : window.innerWidth - peekRect.width,
    top: (window.innerHeight - height) / 2,
    width,
    height,
  };
}

function historyLightboxTransitionGhost(
  src: string,
  rect: HistoryLightboxRect,
  opacity = 1,
): HTMLImageElement {
  const ghost = document.createElement("img");
  ghost.className = "history-lightbox-transition-ghost";
  ghost.alt = "";
  ghost.draggable = false;
  ghost.src = src;
  Object.assign(ghost.style, {
    left: `${rect.left}px`,
    top: `${rect.top}px`,
    width: `${rect.width}px`,
    height: `${rect.height}px`,
    opacity: `${opacity}`,
  });
  return ghost;
}

function historyLightboxGhostKeyframes(
  from: HistoryLightboxRect,
  to: HistoryLightboxRect,
  fromOpacity: number,
  toOpacity: number,
): Keyframe[] {
  const translateX = to.left - from.left;
  const translateY = to.top - from.top;
  return [
    { opacity: fromOpacity, transform: "translate3d(0, 0, 0) scale(1)" },
    {
      opacity: toOpacity,
      transform: `translate3d(${translateX}px, ${translateY}px, 0) scale(${to.width / from.width})`,
    },
  ];
}

function historyLightboxIncomingGhostKeyframes(
  from: HistoryLightboxRect,
  to: HistoryLightboxRect,
  fromOpacity: number,
  toOpacity: number,
): Keyframe[] {
  const translateX = from.left - to.left;
  const translateY = from.top - to.top;
  return [
    {
      opacity: fromOpacity,
      transform: `translate3d(${translateX}px, ${translateY}px, 0) scale(${from.width / to.width})`,
    },
    { opacity: toOpacity, transform: "translate3d(0, 0, 0) scale(1)" },
  ];
}

async function animateHistoryLightboxSwap(
  direction: "previous" | "next",
  targetImage: HTMLImageElement,
  targetIndex: number,
): Promise<HTMLDivElement | null> {
  if (!historyLightboxEl) return null;
  const currentImage = historyLightboxImage();
  const targetPeek = historyLightboxSlot(direction);
  const outgoingSide = direction === "next" ? "previous" : "next";
  const outgoingPeek = historyLightboxSlot(outgoingSide);
  if (!currentImage || !targetPeek || !outgoingPeek) return null;

  const currentRect = currentImage.getBoundingClientRect();
  const incomingEdgeRect = historyLightboxEdgeRect(direction, targetImage, targetPeek);
  const outgoingEdgeRect = historyLightboxEdgeRect(outgoingSide, currentImage, outgoingPeek);
  const incomingStartOpacity = Number.parseFloat(getComputedStyle(targetPeek).opacity) || 0.48;
  const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const layer = document.createElement("div");
  layer.className = "history-lightbox-transition-layer";
  const outgoingGhost = historyLightboxTransitionGhost(currentImage.currentSrc || currentImage.src, currentRect);
  layer.append(outgoingGhost);
  historyLightboxEl.append(layer);
  historyLightboxEl.classList.add("is-shared-switching");
  bindHistoryLightboxSlots(targetIndex);
  await decodeHistoryLightboxBoundSlots();
  await nextHistoryLightboxFrame();
  const centerRect = currentImage.getBoundingClientRect();
  const incomingGhost = historyLightboxTransitionGhost(
    targetImage.currentSrc || targetImage.src,
    centerRect,
    reduceMotion ? 0 : incomingStartOpacity,
  );
  layer.append(incomingGhost);

  const duration = reduceMotion ? 100 : 320;
  const easing = "cubic-bezier(0.22, 1, 0.36, 1)";
  await Promise.all([
    outgoingGhost.animate(
      historyLightboxGhostKeyframes(
        currentRect,
        reduceMotion ? currentRect : outgoingEdgeRect,
        1,
        0,
      ),
      { duration, easing, fill: "forwards" },
    ).finished,
    incomingGhost.animate(
      historyLightboxIncomingGhostKeyframes(
        reduceMotion ? centerRect : incomingEdgeRect,
        centerRect,
        reduceMotion ? 0 : incomingStartOpacity,
        1,
      ),
      { duration, easing, fill: "forwards" },
    ).finished,
  ]);
  return layer;
}

function nextHistoryLightboxFrame(): Promise<void> {
  return new Promise((resolve) => window.requestAnimationFrame(() => resolve()));
}

async function settleHistoryLightboxSwap(layer: HTMLDivElement | null): Promise<void> {
  if (!historyLightboxEl) {
    layer?.remove();
    return;
  }
  historyLightboxEl.classList.add("is-shared-settling");
  await nextHistoryLightboxFrame();
  await nextHistoryLightboxFrame();
  layer?.remove();
  historyLightboxEl.classList.remove("is-shared-switching");
  await nextHistoryLightboxFrame();
  historyLightboxEl.classList.remove("is-shared-settling");
}

function isHistoryLightboxActive(): boolean {
  return Boolean(historyLightboxEl && !historyLightboxEl.hidden);
}

function stopHistoryLightboxPanning(): void {
  historyLightboxState.panning = false;
  historyLightboxEl?.classList.toggle(
    "is-zoomed",
    !isLightboxAtOrBelowFitScale(historyLightboxState.scale),
  );
}

function setHistoryLightboxTransform(): void {
  const image = historyLightboxImage();
  if (!image) return;
  image.style.transform = `translate(${historyLightboxState.pointX}px, ${historyLightboxState.pointY}px) scale(${historyLightboxState.scale})`;
  historyLightboxEl?.classList.toggle(
    "is-zoomed",
    !isLightboxAtOrBelowFitScale(historyLightboxState.scale) || historyLightboxState.panning,
  );
  updateLightboxZoomChrome(historyLightboxEl, historyLightboxState.scale, image);
}

function setHistoryLightboxScale(scale: number): void {
  historyLightboxState.scale = normalizeLightboxScale(scale);
  if (isLightboxAtOrBelowFitScale(historyLightboxState.scale)) {
    historyLightboxState.pointX = 0;
    historyLightboxState.pointY = 0;
    historyLightboxState.panning = false;
  }
  setHistoryLightboxTransform();
}

function zoomHistoryLightbox(direction: "in" | "out"): void {
  setHistoryLightboxScale(lightboxSteppedScale(historyLightboxState.scale, direction));
}

function showHistoryLightboxActualSize(): void {
  setHistoryLightboxScale(lightboxImageActualSizeScale(historyLightboxImage()));
}

function resetHistoryLightboxTransform(): void {
  historyLightboxState.scale = 1;
  historyLightboxState.pointX = 0;
  historyLightboxState.pointY = 0;
  stopHistoryLightboxPanning();
  setHistoryLightboxTransform();
}

function updateHistoryLightboxControls(): void {
  if (!historyLightboxEl) return;
  const hasMultipleImages = historyLightboxState.urls.length > 1;
  const counter = historyLightboxEl.querySelector<HTMLElement>("[data-history-lightbox-counter]");
  counter?.classList.toggle("hidden", !hasMultipleImages);
  if (counter) {
    counter.textContent = hasMultipleImages ? `${historyLightboxState.index + 1} / ${historyLightboxState.urls.length}` : "";
  }
  updateLightboxZoomChrome(historyLightboxEl, historyLightboxState.scale, historyLightboxImage());
}

function showHistoryLightboxImage(index: number): void {
  if (!historyLightboxEl || !historyLightboxState.urls.length) return;
  historyLightboxState.index = clampedHistoryLightboxIndex(index, historyLightboxState.urls.length);
  bindHistoryLightboxSlots();
  resetHistoryLightboxTransform();
  updateHistoryLightboxControls();
}

async function transitionHistoryLightboxTo(index: number): Promise<void> {
  if (!historyLightboxEl || !isHistoryLightboxActive() || historyLightboxState.isTransitioning) return;
  const targetIndex = clampedHistoryLightboxIndex(index, historyLightboxState.urls.length);
  if (targetIndex === historyLightboxState.index) return;
  const direction = targetIndex > historyLightboxState.index ? "next" : "previous";
  historyLightboxState.isTransitioning = true;
  try {
    const targetUrl = historyLightboxState.urls[targetIndex] || "";
    const preloadedImages = await preloadHistoryLightboxSlotImages(targetIndex);
    const targetImage = preloadedImages.get(targetUrl) || await preloadHistoryLightboxImage(targetUrl);
    resetHistoryLightboxTransform();
    const transitionLayer = await animateHistoryLightboxSwap(direction, targetImage, targetIndex);
    historyLightboxState.index = targetIndex;
    bindHistoryLightboxSlots();
    resetHistoryLightboxTransform();
    updateHistoryLightboxControls();
    await settleHistoryLightboxSwap(transitionLayer);
  } catch {
    // Keep the current image visible if the adjacent image cannot be decoded.
    bindHistoryLightboxSlots();
  } finally {
    historyLightboxEl.classList.remove("is-shared-switching", "is-shared-settling");
    historyLightboxEl.querySelector(".history-lightbox-transition-layer")?.remove();
    historyLightboxState.isTransitioning = false;
  }
}

function showPreviousHistoryLightboxImage(): void {
  if (!isHistoryLightboxActive() || historyLightboxState.urls.length < 2) return;
  void transitionHistoryLightboxTo(historyLightboxState.index - 1);
}

function showNextHistoryLightboxImage(): void {
  if (!isHistoryLightboxActive() || historyLightboxState.urls.length < 2) return;
  void transitionHistoryLightboxTo(historyLightboxState.index + 1);
}

function navigateHistoryLightboxTask(direction: HistoryLightboxTaskDirection): void {
  if (!isHistoryLightboxActive() || !historyLightboxState.onTaskNavigate) return;
  void historyLightboxState.onTaskNavigate(direction, {
    taskId: historyLightboxState.taskId,
    imageIndex: historyLightboxState.index,
  });
}

function showPreviousHistoryTask(): void {
  navigateHistoryLightboxTask("previous");
}

function showNextHistoryTask(): void {
  navigateHistoryLightboxTask("next");
}

function ensureHistoryLightbox(): HTMLDivElement {
  if (historyLightboxEl) return historyLightboxEl;

  historyLightboxEl = document.createElement("div");
  historyLightboxEl.className = "history-lightbox";
  historyLightboxEl.tabIndex = -1;
  historyLightboxEl.hidden = true;
  historyLightboxEl.setAttribute("role", "dialog");
  historyLightboxEl.setAttribute("aria-modal", "true");
  historyLightboxEl.setAttribute("aria-label", translate("lightbox.label"));
  historyLightboxEl.innerHTML = `
    <button class="history-lightbox-close" type="button" data-history-lightbox-close aria-label="${escapeHtml(translate("lightbox.close"))}">
      <svg class="drawer-close-icon" viewBox="0 0 24 24" aria-hidden="true" focusable="false">
        <path d="M6 6l12 12M18 6L6 18"></path>
      </svg>
    </button>
    <button class="history-lightbox-peek history-lightbox-peek-previous" type="button" data-history-lightbox-slot="previous" aria-label="${escapeHtml(translate("lightbox.previous"))}">
      <img alt="" draggable="false">
    </button>
    <div class="history-lightbox-track" data-history-lightbox-track>
      <div class="history-lightbox-current-frame" data-history-lightbox-slot="current">
        <img class="history-lightbox-current-image" alt="" draggable="false" data-history-lightbox-image>
      </div>
    </div>
    <button class="history-lightbox-peek history-lightbox-peek-next" type="button" data-history-lightbox-slot="next" aria-label="${escapeHtml(translate("lightbox.next"))}">
      <img alt="" draggable="false">
    </button>
    <div class="history-lightbox-counter" data-history-lightbox-counter aria-live="polite"></div>
    ${lightboxZoomChromeHtml()}
  `;
  document.body.append(historyLightboxEl);

  historyLightboxEl.querySelector<HTMLElement>("[data-history-lightbox-close]")?.addEventListener("click", closeHistoryLightbox);
  historyLightboxSlot("previous")?.addEventListener("click", showPreviousHistoryLightboxImage);
  historyLightboxSlot("next")?.addEventListener("click", showNextHistoryLightboxImage);
  bindLightboxZoomChrome(historyLightboxEl, {
    zoomOut: () => zoomHistoryLightbox("out"),
    zoomIn: () => zoomHistoryLightbox("in"),
    fit: resetHistoryLightboxTransform,
    actualSize: showHistoryLightboxActualSize,
  });

  historyLightboxEl.addEventListener("wheel", (event) => {
    if (!isHistoryLightboxActive()) return;
    event.preventDefault();
    setHistoryLightboxScale(lightboxScaleFromWheel(historyLightboxState.scale, event.deltaY));
  }, { passive: false });

  historyLightboxEl.addEventListener("click", (event) => {
    if (shouldCloseLightboxFromClick(event.target, historyLightboxEl!)) closeHistoryLightbox();
  });

  const image = historyLightboxImage();
  image?.addEventListener("mousedown", (event) => {
    if (event.button !== 0) {
      stopHistoryLightboxPanning();
      return;
    }
    if (isLightboxAtOrBelowFitScale(historyLightboxState.scale)) {
      stopHistoryLightboxPanning();
      return;
    }
    event.preventDefault();
    historyLightboxState.panning = true;
    historyLightboxState.startX = event.clientX - historyLightboxState.pointX;
    historyLightboxState.startY = event.clientY - historyLightboxState.pointY;
  });
  image?.addEventListener("contextmenu", stopHistoryLightboxPanning);
  image?.addEventListener("load", updateHistoryLightboxControls);

  window.addEventListener("mousemove", (event) => {
    if (!historyLightboxState.panning) return;
    if (event.buttons !== undefined && (event.buttons & 1) !== 1) {
      stopHistoryLightboxPanning();
      return;
    }
    historyLightboxState.pointX = event.clientX - historyLightboxState.startX;
    historyLightboxState.pointY = event.clientY - historyLightboxState.startY;
    setHistoryLightboxTransform();
  });
  window.addEventListener("mouseup", stopHistoryLightboxPanning);
  window.addEventListener("blur", stopHistoryLightboxPanning);
  window.addEventListener("keydown", (event) => {
    if (!isHistoryLightboxActive()) return;
    const action = lightboxActionForKey(event.key);
    if (event.key === "Escape") {
      event.preventDefault();
      event.stopPropagation();
      closeHistoryLightbox();
    } else if (event.key === "ArrowLeft" && action === "previous-image") {
      event.preventDefault();
      event.stopPropagation();
      showPreviousHistoryLightboxImage();
    } else if (event.key === "ArrowRight" && action === "next-image") {
      event.preventDefault();
      event.stopPropagation();
      showNextHistoryLightboxImage();
    } else if (event.key === "ArrowUp" && action === "previous-task") {
      event.preventDefault();
      event.stopPropagation();
      showPreviousHistoryTask();
    } else if (event.key === "ArrowDown" && action === "next-task") {
      event.preventDefault();
      event.stopPropagation();
      showNextHistoryTask();
    } else if (event.key === "PageUp" && action === "previous-task") {
      event.preventDefault();
      event.stopPropagation();
      showPreviousHistoryTask();
    } else if (event.key === "PageDown" && action === "next-task") {
      event.preventDefault();
      event.stopPropagation();
      showNextHistoryTask();
    } else if (action === "zoom-in") {
      event.preventDefault();
      zoomHistoryLightbox("in");
    } else if (action === "zoom-out") {
      event.preventDefault();
      zoomHistoryLightbox("out");
    } else if (action === "fit") {
      event.preventDefault();
      resetHistoryLightboxTransform();
    } else if (action === "actual-size") {
      event.preventDefault();
      showHistoryLightboxActualSize();
    }
  });

  return historyLightboxEl;
}

export function openHistoryLightbox(urls: string[], index = 0, options: HistoryLightboxOptions = {}): void {
  const nextUrls = Array.isArray(urls) ? urls.filter(Boolean) : [];
  if (!nextUrls.length) return;
  const wasActive = isHistoryLightboxActive();
  const lightbox = ensureHistoryLightbox();
  historyLightboxState.urls = nextUrls;
  historyLightboxState.index = clampedHistoryLightboxIndex(index, nextUrls.length);
  historyLightboxState.taskId = String(options.taskId || "");
  historyLightboxState.onTaskNavigate = options.onTaskNavigate || null;
  historyLightboxState.isTransitioning = false;
  showHistoryLightboxImage(historyLightboxState.index);
  lightbox.hidden = false;
  document.body.classList.add("history-lightbox-open");
  lightbox.focus({ preventScroll: true });
  updateHistoryLightboxControls();
  if (!wasActive) {
    showLightboxShortcutHint(lightbox, Boolean(historyLightboxState.onTaskNavigate));
  }
}

export function syncHistoryLightboxUrls(urls: string[]): void {
  if (!isHistoryLightboxActive() || !Array.isArray(urls) || !urls.length) return;
  const currentUrl = historyLightboxState.urls[historyLightboxState.index];
  if (!currentUrl) return;
  const nextUrls = urls.filter(Boolean);
  const nextIndex = nextUrls.indexOf(currentUrl);
  if (nextIndex === -1) return;
  historyLightboxState.urls = nextUrls;
  historyLightboxState.index = nextIndex;
  bindHistoryLightboxSlots();
  updateHistoryLightboxControls();
}

export function closeHistoryLightbox(): void {
  if (!historyLightboxEl || historyLightboxEl.hidden) return;
  historyLightboxEl.hidden = true;
  historyLightboxEl.querySelectorAll<HTMLImageElement>("img").forEach((image) => image.removeAttribute("src"));
  historyLightboxEl.classList.remove(
    "is-shared-switching",
    "is-single",
    "is-zoomed",
  );
  stopHistoryLightboxPanning();
  historyLightboxState.urls = [];
  historyLightboxState.index = 0;
  historyLightboxState.taskId = "";
  historyLightboxState.onTaskNavigate = null;
  historyLightboxState.isTransitioning = false;
  hideLightboxShortcutHint(historyLightboxEl);
  resetHistoryLightboxTransform();
  document.body.classList.remove("history-lightbox-open");
}

export function isHistoryLightboxOpen(): boolean {
  return isHistoryLightboxActive();
}

import { translate } from "./i18n";
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
};

export type HistoryLightboxTaskDirection = "previous" | "next";
export type HistoryLightboxTaskNavigationContext = {
  taskId: string;
  imageIndex: number;
};
export type HistoryLightboxTaskNavigation = (
  direction: HistoryLightboxTaskDirection,
  context: HistoryLightboxTaskNavigationContext,
) => void | Promise<void>;
type HistoryLightboxOptions = {
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
};

function normalizedHistoryLightboxIndex(index: number, count: number): number {
  if (!count) return 0;
  return ((index % count) + count) % count;
}

function historyLightboxImage(): HTMLImageElement | null {
  return historyLightboxEl?.querySelector<HTMLImageElement>("[data-history-lightbox-image]") || null;
}

function isHistoryLightboxActive(): boolean {
  return Boolean(historyLightboxEl && !historyLightboxEl.hidden);
}

function stopHistoryLightboxPanning(): void {
  historyLightboxState.panning = false;
}

function setHistoryLightboxTransform(): void {
  const image = historyLightboxImage();
  if (!image) return;
  image.style.transform = `translate(${historyLightboxState.pointX}px, ${historyLightboxState.pointY}px) scale(${historyLightboxState.scale})`;
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
  const prevButton = historyLightboxEl.querySelector<HTMLElement>("[data-history-lightbox-prev]");
  const nextButton = historyLightboxEl.querySelector<HTMLElement>("[data-history-lightbox-next]");
  const counter = historyLightboxEl.querySelector<HTMLElement>("[data-history-lightbox-counter]");
  [prevButton, nextButton, counter].forEach((element) => {
    element?.classList.toggle("hidden", !hasMultipleImages);
  });
  if (counter) {
    counter.textContent = hasMultipleImages ? `${historyLightboxState.index + 1} / ${historyLightboxState.urls.length}` : "";
  }
}

function showHistoryLightboxImage(index: number): void {
  if (!historyLightboxEl || !historyLightboxState.urls.length) return;
  const image = historyLightboxImage();
  if (!image) return;
  historyLightboxState.index = normalizedHistoryLightboxIndex(index, historyLightboxState.urls.length);
  image.src = historyLightboxState.urls[historyLightboxState.index] || "";
  resetHistoryLightboxTransform();
  updateHistoryLightboxControls();
}

function showPreviousHistoryLightboxImage(): void {
  if (!isHistoryLightboxActive() || historyLightboxState.urls.length < 2) return;
  showHistoryLightboxImage(historyLightboxState.index - 1);
}

function showNextHistoryLightboxImage(): void {
  if (!isHistoryLightboxActive() || historyLightboxState.urls.length < 2) return;
  showHistoryLightboxImage(historyLightboxState.index + 1);
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
    <button class="history-lightbox-nav history-lightbox-prev" type="button" data-history-lightbox-prev aria-label="${escapeHtml(translate("lightbox.previous"))}">&lsaquo;</button>
    <img alt="" draggable="false" data-history-lightbox-image>
    <button class="history-lightbox-nav history-lightbox-next" type="button" data-history-lightbox-next aria-label="${escapeHtml(translate("lightbox.next"))}">&rsaquo;</button>
    <div class="history-lightbox-counter" data-history-lightbox-counter aria-live="polite"></div>
  `;
  document.body.append(historyLightboxEl);

  historyLightboxEl.querySelector<HTMLElement>("[data-history-lightbox-close]")?.addEventListener("click", closeHistoryLightbox);
  historyLightboxEl.querySelector<HTMLElement>("[data-history-lightbox-prev]")?.addEventListener("click", showPreviousHistoryLightboxImage);
  historyLightboxEl.querySelector<HTMLElement>("[data-history-lightbox-next]")?.addEventListener("click", showNextHistoryLightboxImage);

  historyLightboxEl.addEventListener("wheel", (event) => {
    if (!isHistoryLightboxActive()) return;
    event.preventDefault();
    const delta = event.deltaY * -0.005;
    historyLightboxState.scale = Math.min(Math.max(0.5, historyLightboxState.scale + delta), 5);
    setHistoryLightboxTransform();
  }, { passive: false });

  historyLightboxEl.addEventListener("click", (event) => {
    if (event.target === historyLightboxEl) closeHistoryLightbox();
  });

  const image = historyLightboxImage();
  image?.addEventListener("mousedown", (event) => {
    if (event.button !== 0) {
      stopHistoryLightboxPanning();
      return;
    }
    event.preventDefault();
    historyLightboxState.panning = true;
    historyLightboxState.startX = event.clientX - historyLightboxState.pointX;
    historyLightboxState.startY = event.clientY - historyLightboxState.pointY;
  });
  image?.addEventListener("contextmenu", stopHistoryLightboxPanning);

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
    if (event.key === "ArrowLeft") {
      event.preventDefault();
      showPreviousHistoryLightboxImage();
    } else if (event.key === "ArrowRight") {
      event.preventDefault();
      showNextHistoryLightboxImage();
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      showPreviousHistoryTask();
    } else if (event.key === "ArrowDown") {
      event.preventDefault();
      showNextHistoryTask();
    } else if (event.key === "PageUp") {
      event.preventDefault();
      showPreviousHistoryTask();
    } else if (event.key === "PageDown") {
      event.preventDefault();
      showNextHistoryTask();
    }
  });

  return historyLightboxEl;
}

export function openHistoryLightbox(urls: string[], index = 0, options: HistoryLightboxOptions = {}): void {
  const nextUrls = Array.isArray(urls) ? urls.filter(Boolean) : [];
  if (!nextUrls.length) return;
  const lightbox = ensureHistoryLightbox();
  historyLightboxState.urls = nextUrls;
  historyLightboxState.index = normalizedHistoryLightboxIndex(index, nextUrls.length);
  historyLightboxState.taskId = String(options.taskId || "");
  historyLightboxState.onTaskNavigate = options.onTaskNavigate || null;
  showHistoryLightboxImage(historyLightboxState.index);
  lightbox.hidden = false;
  document.body.classList.add("history-lightbox-open");
  updateHistoryLightboxControls();
}

export function closeHistoryLightbox(): void {
  if (!historyLightboxEl || historyLightboxEl.hidden) return;
  historyLightboxEl.hidden = true;
  const image = historyLightboxImage();
  if (image) image.removeAttribute("src");
  stopHistoryLightboxPanning();
  historyLightboxState.urls = [];
  historyLightboxState.index = 0;
  historyLightboxState.taskId = "";
  historyLightboxState.onTaskNavigate = null;
  resetHistoryLightboxTransform();
  document.body.classList.remove("history-lightbox-open");
}

export function isHistoryLightboxOpen(): boolean {
  return isHistoryLightboxActive();
}

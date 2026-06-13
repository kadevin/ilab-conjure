import { getLegacyBridge } from "./state";
import { translate } from "./i18n";

interface LightboxState {
  scale: number;
  panning: boolean;
  pointX: number;
  pointY: number;
  startX: number;
  startY: number;
  urls: string[];
  index: number;
}

declare global {
  interface Window {
    closeLightbox?: () => void;
    showLightboxImage?: (index: number) => void;
    showPreviousLightboxImage?: () => void;
    showNextLightboxImage?: () => void;
  }
}

let lightboxFeatureInitialized = false;
let lightboxEl: HTMLDivElement | null = null;

const lightboxState: LightboxState = {
  scale: 1,
  panning: false,
  pointX: 0,
  pointY: 0,
  startX: 0,
  startY: 0,
  urls: [],
  index: 0,
};

function legacyMethod(name: string, ...args: any[]): any {
  const method = getLegacyBridge().methods[name];
  if (typeof method !== "function") {
    throw new Error("Legacy bridge method " + name + " is not available");
  }
  return method(...args);
}

function isLightboxActive(): boolean {
  return Boolean(lightboxEl?.classList.contains("active"));
}

function lightboxImage(): HTMLImageElement | null {
  return lightboxEl?.querySelector<HTMLImageElement>("#lightboxImg") || null;
}

function setLightboxTransform(): void {
  const img = lightboxImage();
  if (!img) return;
  img.style.transform = `translate(${lightboxState.pointX}px, ${lightboxState.pointY}px) scale(${lightboxState.scale})`;
}

function resetLightboxTransform(): void {
  lightboxState.scale = 1;
  lightboxState.pointX = 0;
  lightboxState.pointY = 0;
  stopLightboxPanning();
  setLightboxTransform();
}

function stopLightboxPanning(): void {
  lightboxState.panning = false;
}

function updateLightboxControls(): void {
  if (!lightboxEl) return;
  const hasMultipleImages = lightboxState.urls.length > 1;
  const prevButton = lightboxEl.querySelector(".lightbox-prev");
  const nextButton = lightboxEl.querySelector(".lightbox-next");
  const counter = lightboxEl.querySelector(".lightbox-counter");
  [prevButton, nextButton, counter].forEach((element) => {
    element?.classList.toggle("hidden", !hasMultipleImages);
  });
  if (counter) {
    counter.textContent = hasMultipleImages ? `${lightboxState.index + 1} / ${lightboxState.urls.length}` : "";
  }
}

function normalizedLightboxIndex(index: number, count: number): number {
  if (!count) return 0;
  return ((index % count) + count) % count;
}

function syncActiveLightboxUrls(urls: string[]): void {
  if (!isLightboxActive() || !Array.isArray(urls) || !urls.length) return;
  const currentUrl = lightboxState.urls[lightboxState.index];
  if (!currentUrl) return;
  const nextIndex = urls.indexOf(currentUrl);
  if (nextIndex === -1) return;
  lightboxState.urls = urls.slice();
  lightboxState.index = nextIndex;
  updateLightboxControls();
}

function showLightboxImage(index: number): void {
  if (!lightboxEl || !lightboxState.urls.length) return;
  const img = lightboxImage();
  if (!img) return;
  lightboxState.index = normalizedLightboxIndex(index, lightboxState.urls.length);
  img.src = lightboxState.urls[lightboxState.index] || "";
  resetLightboxTransform();
  updateLightboxControls();
}

function showPreviousLightboxImage(): void {
  if (!isLightboxActive() || lightboxState.urls.length < 2) return;
  showLightboxImage(lightboxState.index - 1);
}

function showNextLightboxImage(): void {
  if (!isLightboxActive() || lightboxState.urls.length < 2) return;
  showLightboxImage(lightboxState.index + 1);
}

function ensureLightboxElement(): HTMLDivElement {
  if (lightboxEl) return lightboxEl;

  lightboxEl = document.createElement("div");
  lightboxEl.className = "lightbox";
  lightboxEl.setAttribute("role", "dialog");
  lightboxEl.setAttribute("aria-modal", "true");
  lightboxEl.setAttribute("aria-label", translate("lightbox.label"));
  lightboxEl.innerHTML = `
      <button class="lightbox-close" type="button" aria-label="${translate("lightbox.close")}">
        <svg class="drawer-close-icon" viewBox="0 0 24 24" aria-hidden="true" focusable="false">
          <path d="M6 6l12 12M18 6L6 18"></path>
        </svg>
      </button>
      <button class="lightbox-nav lightbox-prev" type="button" aria-label="${translate("lightbox.previous")}">&lsaquo;</button>
      <img id="lightboxImg" src="" alt="" draggable="false">
      <button class="lightbox-nav lightbox-next" type="button" aria-label="${translate("lightbox.next")}">&rsaquo;</button>
      <div class="lightbox-counter" aria-live="polite"></div>
    `;
  document.body.appendChild(lightboxEl);

  const img = lightboxEl.querySelector<HTMLImageElement>("img");
  const lightboxClose = lightboxEl.querySelector(".lightbox-close");
  const prevButton = lightboxEl.querySelector(".lightbox-prev");
  const nextButton = lightboxEl.querySelector(".lightbox-next");
  lightboxClose?.addEventListener("click", closeLightbox);
  prevButton?.addEventListener("click", showPreviousLightboxImage);
  nextButton?.addEventListener("click", showNextLightboxImage);

  lightboxEl.addEventListener("wheel", (event) => {
    if (!isLightboxActive()) return;
    event.preventDefault();
    const delta = event.deltaY * -0.005;
    lightboxState.scale = Math.min(Math.max(0.5, lightboxState.scale + delta), 5);
    setLightboxTransform();
  });

  lightboxEl.addEventListener("click", (event) => {
    if (event.target === lightboxEl) closeLightbox();
  });

  img?.addEventListener("mousedown", (event) => {
    if (event.button !== 0) {
      stopLightboxPanning();
      return;
    }
    event.preventDefault();
    lightboxState.panning = true;
    lightboxState.startX = event.clientX - lightboxState.pointX;
    lightboxState.startY = event.clientY - lightboxState.pointY;
  });

  img?.addEventListener("contextmenu", stopLightboxPanning);

  window.addEventListener("mousemove", (event) => {
    if (!lightboxState.panning) return;
    if (event.buttons !== undefined && (event.buttons & 1) !== 1) {
      stopLightboxPanning();
      return;
    }
    lightboxState.pointX = event.clientX - lightboxState.startX;
    lightboxState.pointY = event.clientY - lightboxState.startY;
    setLightboxTransform();
  });

  window.addEventListener("mouseup", stopLightboxPanning);
  window.addEventListener("blur", stopLightboxPanning);

  window.addEventListener("keydown", (event) => {
    if (!isLightboxActive()) return;
    if (event.key === "Escape") {
      closeLightbox();
    } else if (event.key === "ArrowLeft") {
      event.preventDefault();
      showPreviousLightboxImage();
    } else if (event.key === "ArrowRight") {
      event.preventDefault();
      showNextLightboxImage();
    }
  });

  return lightboxEl;
}

function openLightbox(url: string, urls: string[] = [], index = 0): void {
  const element = ensureLightboxElement();
  const nextUrls = Array.isArray(urls) && urls.length ? urls.filter(Boolean) : [url].filter(Boolean);
  lightboxState.urls = nextUrls.length ? nextUrls : [url].filter(Boolean);
  const matchedIndex = lightboxState.urls.indexOf(url);
  lightboxState.index = matchedIndex >= 0 ? matchedIndex : normalizedLightboxIndex(index, lightboxState.urls.length);
  showLightboxImage(lightboxState.index);
  document.body.classList.add("lightbox-open");
  element.classList.add("active");
  updateLightboxControls();
}

function closeLightbox(): void {
  if (!lightboxEl) return;
  lightboxEl.classList.remove("active");
  document.body.classList.remove("lightbox-open");
  stopLightboxPanning();
  lightboxState.urls = [];
  lightboxState.index = 0;
}

async function addToInput(url: string): Promise<void> {
  try {
    const file = await legacyMethod("imageFileFromUrl", url, "preview-" + Date.now());
    legacyMethod("addImageFiles", [file]);
  } catch (error) {
    console.error("Failed to add image to input", error);
  }
}

export function initLightboxFeature(): void {
  if (lightboxFeatureInitialized) return;
  lightboxFeatureInitialized = true;

  window.openLightbox = openLightbox;
  window.closeLightbox = closeLightbox;
  window.showLightboxImage = showLightboxImage;
  window.showPreviousLightboxImage = showPreviousLightboxImage;
  window.showNextLightboxImage = showNextLightboxImage;
  window.addToInput = addToInput;

  Object.assign(getLegacyBridge().methods, {
    syncActiveLightboxUrls,
  });
}

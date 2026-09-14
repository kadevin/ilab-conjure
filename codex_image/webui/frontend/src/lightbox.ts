import { translate } from "./i18n";
import {
  closeHistoryLightbox,
  openHistoryLightbox,
  syncHistoryLightboxUrls,
} from "./history-lightbox";
import type { HistoryLightboxTaskNavigation } from "./history-lightbox";
import { getLegacyBridge } from "./state";

export type LightboxOptions = {
  taskId?: string;
  onTaskNavigate?: HistoryLightboxTaskNavigation;
};

let lightboxFeatureInitialized = false;

function legacyMethod(name: string, ...args: any[]): any {
  const method = getLegacyBridge().methods[name];
  if (typeof method !== "function") {
    throw new Error("Legacy bridge method " + name + " is not available");
  }
  return method(...args);
}

function openLightbox(url: string, urls: string[] = [], index = 0, options: LightboxOptions = {}): void {
  const nextUrls = Array.isArray(urls) && urls.length
    ? urls.filter(Boolean)
    : [url].filter(Boolean);
  if (!nextUrls.length) return;
  const matchedIndex = nextUrls.indexOf(url);
  const requestedIndex = matchedIndex >= 0 ? matchedIndex : index;
  openHistoryLightbox(nextUrls, requestedIndex, options);
}

function syncActiveLightboxUrls(urls: string[]): void {
  syncHistoryLightboxUrls(urls);
}

async function addToInput(url: string, anchor?: HTMLButtonElement): Promise<void> {
  if (anchor?.disabled) return;
  let feedback = anchor?.parentElement?.querySelector<HTMLElement>(".reference-add-feedback");
  if (anchor && !feedback) {
    feedback = document.createElement("span"); feedback.className = "reference-add-feedback"; feedback.setAttribute("role", "status"); anchor.after(feedback);
  }
  if (anchor) { anchor.disabled = true; anchor.setAttribute("aria-busy", "true"); }
  if (feedback) feedback.textContent = translate("ux.addingReference");
  try {
    legacyMethod("setStatus", translate("ux.addingReference"), "");
    const file = await legacyMethod("imageFileFromUrl", url, "preview-" + Date.now());
    await legacyMethod("addImageFiles", [file]);
    legacyMethod("setStatus", translate("ux.referenceAdded"), "ok");
    if (feedback) feedback.textContent = translate("ux.referenceAdded");
  } catch (error) {
    legacyMethod("setStatus", `${translate("ux.referenceFailed")} ${error instanceof Error ? error.message : ""}`, "error");
    if (feedback) feedback.textContent = translate("ux.referenceFailed");
  } finally {
    if (anchor) { anchor.disabled = false; anchor.removeAttribute("aria-busy"); }
  }
}

export function initLightboxFeature(): void {
  if (lightboxFeatureInitialized) return;
  lightboxFeatureInitialized = true;

  window.openLightbox = openLightbox;
  window.closeLightbox = closeHistoryLightbox;
  window.addToInput = addToInput;

  Object.assign(getLegacyBridge().methods, {
    syncActiveLightboxUrls,
  });
}

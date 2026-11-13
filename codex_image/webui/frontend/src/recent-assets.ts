import { getLegacyBridge } from "./state";
import { formatTranslation, LOCALE_CHANGE_EVENT, translate } from "./i18n";

const bridge = getLegacyBridge();
const state = bridge.state;
const els = bridge.els;

let recentAssetsFeatureInitialized = false;
const RECENT_ASSET_RENDER_BATCH_SIZE = 12;
const RECENT_ASSET_LOAD_AHEAD_PX = 96;
const RECENT_ASSET_REFRESH_TIMEOUT_MS = 5000;
const RECENT_ASSET_PREVIEW_VISIBILITY_KEY = "codex-image-recent-asset-previews-hidden";
let recentAssetRenderLimit = RECENT_ASSET_RENDER_BATCH_SIZE;
let recentAssetPreviewsHidden = false;
let recentAssetLoadState: "idle" | "loading" | "error" = "idle";
let recentAssetLoadError = "";
let recentAssetRefreshController: AbortController | null = null;

function legacyMethod(name: string, ...args: any[]): any {
  const method = getLegacyBridge().methods[name];
  if (typeof method !== "function") {
    throw new Error("Legacy method " + name + " is not initialized");
  }
  return method(...args);
}

function escapeHtml(value: any): string { return legacyMethod("escapeHtml", value); }
function setStatus(message: any, type?: any): void { legacyMethod("setStatus", message, type); }
function openConfirmPopover(anchor: any, options: any): void { legacyMethod("openConfirmPopover", anchor, options); }
function setMode(mode: any): void { legacyMethod("setMode", mode); }
function addReferenceAssetInput(item: any): void { legacyMethod("addReferenceAssetInput", item); }
function renderImageStrip(): void { legacyMethod("renderImageStrip"); }
function updateRequestPreview(): void { legacyMethod("updateRequestPreview"); }

function recentAssetName(item: any): string {
  return item?.filename || translate("recentAssets.defaultName");
}

function recentAssetReferenceCount(item: any): number {
  const count = Number(item?.reference_count);
  return Number.isInteger(count) && count > 0 ? count : 0;
}

function recentAssetRequiresHide(item: any): boolean {
  return recentAssetReferenceCount(item) > 0 || item?.deletable === false;
}

function recentAssetRequestError(data: any, fallback: string): string {
  const detail = data?.detail;
  if (detail?.code === "reference_asset_in_use") {
    const count = Math.max(1, Number(detail.reference_count) || 1);
    return formatTranslation("recentAssets.inUse", { count });
  }
  if (typeof detail === "string" && detail.trim()) return detail;
  if (typeof detail?.message === "string" && detail.message.trim()) return detail.message;
  return fallback;
}

function syncRecentAssetPreviewVisibility() {
  els.recentAssetDock?.classList.toggle("previews-hidden", recentAssetPreviewsHidden);
  els.recentAssetList?.setAttribute("aria-hidden", String(recentAssetPreviewsHidden));
  els.recentAssetList?.toggleAttribute("inert", recentAssetPreviewsHidden);
  const label = translate(recentAssetPreviewsHidden ? "recentAssets.showPreviews" : "recentAssets.hidePreviews");
  els.recentAssetVisibilityToggle?.setAttribute("aria-expanded", String(!recentAssetPreviewsHidden));
  els.recentAssetVisibilityToggle?.setAttribute("aria-label", label);
  els.recentAssetVisibilityToggle?.setAttribute("title", label);
}

function readRecentAssetPreviewsHidden(): boolean {
  try {
    return localStorage.getItem(RECENT_ASSET_PREVIEW_VISIBILITY_KEY) === "true";
  } catch {
    return false;
  }
}

function toggleRecentAssetPreviews() {
  recentAssetPreviewsHidden = !recentAssetPreviewsHidden;
  try {
    localStorage.setItem(RECENT_ASSET_PREVIEW_VISIBILITY_KEY, String(recentAssetPreviewsHidden));
  } catch {
    // Keep the toggle usable when browser storage is unavailable.
  }
  syncRecentAssetPreviewVisibility();
}

async function refreshRecentAssets() {
  const list = els.recentAssetList as HTMLElement | null;
  if (!list) return;
  recentAssetRefreshController?.abort();
  const controller = new AbortController();
  recentAssetRefreshController = controller;
  const { signal } = controller;
  const timeout = window.setTimeout(() => controller.abort(), RECENT_ASSET_REFRESH_TIMEOUT_MS);
  recentAssetLoadState = "loading";
  recentAssetLoadError = "";
  list.setAttribute("aria-busy", "true");
  renderRecentAssetDock(list.childElementCount > 0);
  let preparedImages: Map<string, HTMLImageElement> | undefined;
  try {
    const response = await fetch("/api/reference-assets/recent?limit=50", { signal });
    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.detail || translate("recentAssets.loadFailed"));
    }
    signal.throwIfAborted();
    const items = Array.isArray(data.items) ? data.items : [];
    preparedImages = await prepareRecentAssetImages(list, items, signal);
    signal.throwIfAborted();
    state.recentAssets = items;
    recentAssetLoadState = "idle";
  } catch (error: any) {
    if (recentAssetRefreshController !== controller) return;
    recentAssetLoadState = "error";
    recentAssetLoadError = signal.aborted ? translate("recentAssets.loadFailed") : error?.message || translate("recentAssets.loadFailed");
  } finally {
    window.clearTimeout(timeout);
    controller.abort();
    if (recentAssetRefreshController === controller) {
      recentAssetRefreshController = null;
      list.removeAttribute("aria-busy");
      renderRecentAssets(preparedImages);
    }
  }
}

function renderRecentAssetStatus() {
  if (!els.recentAssetStatus) return;
  if (recentAssetLoadState === "idle") {
    els.recentAssetStatus.hidden = true;
    els.recentAssetStatus.innerHTML = "";
    return;
  }
  els.recentAssetStatus.hidden = false;
  if (recentAssetLoadState === "loading") {
    els.recentAssetStatus.className = "recent-asset-status is-loading";
    els.recentAssetStatus.textContent = translate("history.loading");
    return;
  }
  els.recentAssetStatus.className = "recent-asset-status is-error";
  els.recentAssetStatus.innerHTML = `
    <span>${escapeHtml(recentAssetLoadError || translate("recentAssets.loadFailed"))}</span>
    <button class="ghost-button text-sm" type="button" data-recent-assets-retry>${escapeHtml(translate("action.refresh"))}</button>
  `;
}

function renderRecentAssetDock(hasItems: boolean) {
  els.recentAssetDock?.classList.toggle("hidden", !hasItems && recentAssetLoadState === "idle");
  els.recentAssetDock?.classList.toggle("is-loading", recentAssetLoadState === "loading");
  renderRecentAssetStatus();
  syncRecentAssetPreviewVisibility();
}

function recentAssetCards(list: HTMLElement) {
  return new Map(Array.from(list.querySelectorAll<HTMLElement>(".recent-asset-button"),
    card => [card.dataset.recentAssetId, card]));
}

function setRecentAssetImageSource(image: HTMLImageElement, item: any) {
  const thumbnailUrl = item.thumbnail_url || item.image_url;
  if (image.dataset.thumbnailSrc === thumbnailUrl && image.dataset.fullSrc === item.image_url) return;
  image.dataset.thumbnailSrc = thumbnailUrl;
  image.dataset.fullSrc = item.image_url;
  image.src = thumbnailUrl;
}

function useRecentAssetImageFallback(image: HTMLImageElement): boolean {
  const originalUrl = image.dataset.fullSrc;
  if (!originalUrl || image.getAttribute("src") === originalUrl) return false;
  image.src = originalUrl;
  return true;
}

function recentAssetsInViewport(list: HTMLElement, items: any[]) {
  if (recentAssetPreviewsHidden || !list.firstElementChild || !list.clientWidth) return [];
  const style = getComputedStyle(list);
  const gap = parseFloat(style.columnGap) || 0;
  const padding = (parseFloat(style.paddingLeft) || 0) + (parseFloat(style.paddingRight) || 0);
  const stride = list.firstElementChild.getBoundingClientRect().width + gap;
  if (!stride) return [];
  const count = Math.min(items.length, recentAssetRenderLimit);
  const maxScroll = Math.max(0, count * stride - gap + padding - list.clientWidth);
  const start = Math.min(Math.max(0, list.scrollLeft), maxScroll);
  // Include a neighboring card for partial tiles and fractional pixel rounding.
  return items.slice(Math.max(0, Math.floor(start / stride) - 1),
    Math.min(count, Math.ceil((start + list.clientWidth) / stride) + 1));
}

async function decodeRecentAssetImage(item: any, signal: AbortSignal): Promise<HTMLImageElement> {
  signal.throwIfAborted();
  const image = new Image();
  image.decoding = "async";
  let cancel!: () => void;
  const aborted = new Promise<never>((_resolve, reject) => {
    cancel = () => {
      image.removeAttribute("src");
      reject(signal.reason);
    };
    signal.addEventListener("abort", cancel, { once: true });
  });
  try {
    setRecentAssetImageSource(image, item);
    try {
      await Promise.race([image.decode(), aborted]);
    } catch {
      signal.throwIfAborted();
      if (!useRecentAssetImageFallback(image)) throw new Error(translate("recentAssets.loadFailed"));
      await Promise.race([image.decode(), aborted]).catch(() => {
        signal.throwIfAborted();
        throw new Error(translate("recentAssets.loadFailed"));
      });
    }
    signal.throwIfAborted();
    return image;
  } finally {
    signal.removeEventListener("abort", cancel);
  }
}

async function prepareRecentAssetImages(list: HTMLElement, items: any[], signal: AbortSignal) {
  const validItems = items.filter(item => item?.id && item?.image_url);
  const cards = recentAssetCards(list);
  const prepared = new Map<string, HTMLImageElement>();
  // Scrolling or resizing while images decode can change which tiles will be visible.
  while (!signal.aborted) {
    const missing = recentAssetsInViewport(list, validItems).filter(item => {
      if (prepared.has(item.id)) return false;
      const current = cards.get(item.id)?.querySelector("img");
      return !(current?.complete && current.naturalWidth > 0
        && current.dataset.thumbnailSrc === (item.thumbnail_url || item.image_url)
        && current.dataset.fullSrc === item.image_url);
    });
    if (!missing.length) break;
    await Promise.all(missing.map(async item => {
      prepared.set(item.id, await decodeRecentAssetImage(item, signal));
    }));
  }
  return prepared;
}

function createRecentAssetCard(id: string) {
  const card = document.createElement("div");
  card.className = "recent-asset-button";
  card.dataset.recentAssetId = id;
  card.innerHTML = `
      <button class="recent-asset-use" type="button">
        <img loading="lazy" decoding="async">
        <span></span>
      </button>
      <button class="recent-asset-delete" type="button">×</button>
  `;
  card.querySelector<HTMLButtonElement>(".recent-asset-use")!.dataset.referenceAssetId = id;
  return card;
}

function updateRecentAssetCard(card: HTMLElement, item: any, preparedImage?: HTMLImageElement) {
  const name = recentAssetName(item);
  const hideOnly = recentAssetRequiresHide(item);
  const use = card.querySelector<HTMLButtonElement>(".recent-asset-use")!;
  const action = card.querySelector<HTMLButtonElement>(".recent-asset-delete")!;
  let image = use.querySelector("img")!;
  if (preparedImage) {
    image.replaceWith(preparedImage);
    image = preparedImage;
  }
  setRecentAssetImageSource(image, item);
  image.alt = name;
  card.title = name;
  use.querySelector("span")!.textContent = name;
  use.setAttribute("aria-label", formatTranslation("recentAssets.use", { name }));
  action.classList.toggle("is-hide", hideOnly);
  action.removeAttribute(hideOnly ? "data-reference-asset-delete" : "data-reference-asset-hide");
  action.setAttribute(hideOnly ? "data-reference-asset-hide" : "data-reference-asset-delete", item.id);
  action.setAttribute("aria-label", formatTranslation(hideOnly ? "recentAssets.hide" : "recentAssets.delete", { name }));
  action.title = hideOnly
    ? formatTranslation("recentAssets.inUse", { count: recentAssetReferenceCount(item) })
    : translate("recentAssets.deleteTitle");
}

function renderRecentAssets(preparedImages?: Map<string, HTMLImageElement>) {
  const list = els.recentAssetList as HTMLElement | null;
  if (!list) return;
  const items = state.recentAssets.filter((item: any) => item?.id && item?.image_url);
  const visibleItems = items.slice(0, recentAssetRenderLimit);
  const desiredIds = new Set(visibleItems.map((item: any) => item.id));
  const cards = recentAssetCards(list);
  const scrollLeft = list.scrollLeft;
  const focused = document.activeElement as HTMLElement | null;
  renderRecentAssetDock(items.length > 0);

  cards.forEach((card, id) => {
    if (!desiredIds.has(id)) card.remove();
  });
  visibleItems.forEach((item: any, index: number) => {
    const card = cards.get(item.id) || createRecentAssetCard(item.id);
    updateRecentAssetCard(card, item, preparedImages?.get(item.id));
    if (list.children[index] !== card) list.insertBefore(card, list.children[index] || null);
  });
  if (focused && list.contains(focused) && focused !== document.activeElement) focused.focus({ preventScroll: true });
  if (list.scrollLeft !== scrollLeft) list.scrollLeft = scrollLeft;
}

function handleRecentAssetImageError(event: Event) {
  const image = event.target;
  if (!(image instanceof HTMLImageElement)) return;
  useRecentAssetImageFallback(image);
}

function handleRecentAssetClick(event: Event) {
  const target = event.target instanceof Element ? event.target : null;
  const hideButton = target?.closest("[data-reference-asset-hide]") as HTMLElement | null;
  if (hideButton) {
    event.stopPropagation();
    const item = state.recentAssets.find((candidate: any) => candidate.id === hideButton.dataset.referenceAssetHide);
    if (!item) return;
    const referenceCount = recentAssetReferenceCount(item);
    openConfirmPopover(hideButton, {
      title: translate("recentAssets.hideTitle"),
      message: formatTranslation("recentAssets.hideMessage", { count: referenceCount }),
      detail: `${recentAssetName(item)} · ${formatTranslation("recentAssets.inUse", { count: referenceCount })}`,
      confirmText: translate("action.confirm"),
      danger: false,
      onConfirm: () => hideRecentAsset(item.id),
    });
    return;
  }
  const deleteButton = target?.closest("[data-reference-asset-delete]") as HTMLElement | null;
  if (deleteButton) {
    event.stopPropagation();
    const item = state.recentAssets.find((candidate: any) => candidate.id === deleteButton.dataset.referenceAssetDelete);
    if (!item) return;
    openConfirmPopover(deleteButton, {
      title: translate("recentAssets.deleteTitle"),
      message: translate("recentAssets.deleteMessage"),
      detail: recentAssetName(item),
      confirmText: translate("action.delete"),
      onConfirm: () => deleteRecentAsset(item.id),
    });
    return;
  }
  const useButton = target?.closest("[data-reference-asset-id]") as HTMLElement | null;
  if (!useButton) return;
  const item = state.recentAssets.find((candidate: any) => candidate.id === useButton.dataset.referenceAssetId);
  if (item) addReferenceAssetInput(item);
}

function handleRecentAssetScroll() {
  const list = els.recentAssetList;
  if (!list || recentAssetRenderLimit >= state.recentAssets.length) return;
  const remaining = list.scrollWidth - list.clientWidth - list.scrollLeft;
  if (remaining > RECENT_ASSET_LOAD_AHEAD_PX) return;
  recentAssetRenderLimit += RECENT_ASSET_RENDER_BATCH_SIZE;
  renderRecentAssets();
}

function wheelDeltaInPixels(event: WheelEvent) {
  const dominantDelta = Math.abs(event.deltaX) > Math.abs(event.deltaY) ? event.deltaX : event.deltaY;
  if (event.deltaMode === WheelEvent.DOM_DELTA_LINE) return dominantDelta * 16;
  if (event.deltaMode === WheelEvent.DOM_DELTA_PAGE) {
    return dominantDelta * Math.max(1, els.recentAssetList?.clientWidth || 1);
  }
  return dominantDelta;
}

function handleRecentAssetWheel(event: WheelEvent) {
  const list = els.recentAssetList;
  if (!list) return;
  const maxScrollLeft = Math.max(0, list.scrollWidth - list.clientWidth);
  if (!maxScrollLeft) return;
  const wheelDelta = wheelDeltaInPixels(event);
  if (!wheelDelta) return;
  const nextScrollLeft = Math.min(maxScrollLeft, Math.max(0, list.scrollLeft + wheelDelta));
  if (nextScrollLeft === list.scrollLeft) return;
  event.preventDefault();
  list.scrollLeft = nextScrollLeft;
}

async function hideRecentAsset(assetId: any) {
  if (!assetId) return;
  try {
    const response = await fetch(`/api/reference-assets/${encodeURIComponent(assetId)}/hide`, {
      method: "POST",
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(recentAssetRequestError(data, translate("recentAssets.hideFailed")));
    }
    state.recentAssets = state.recentAssets.filter((item: any) => item.id !== assetId);
    renderRecentAssets();
    if (recentAssetLoadState === "loading") void refreshRecentAssets();
    setStatus(translate("recentAssets.hidden"), "ok");
  } catch (error: any) {
    setStatus(error.message || translate("recentAssets.hideFailed"), "error");
  }
}

async function deleteRecentAsset(assetId: any) {
  if (!assetId) return;
  try {
    const response = await fetch(`/api/reference-assets/${encodeURIComponent(assetId)}`, {
      method: "DELETE",
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      if (data?.detail?.code === "reference_asset_in_use") {
        const referenceCount = Math.max(1, Number(data.detail.reference_count) || 1);
        state.recentAssets = state.recentAssets.map((item: any) => (
          item.id === assetId
            ? { ...item, reference_count: referenceCount, deletable: false }
            : item
        ));
        renderRecentAssets();
      }
      throw new Error(recentAssetRequestError(data, translate("recentAssets.deleteFailed")));
    }
    state.recentAssets = state.recentAssets.filter((item: any) => item.id !== assetId);
    state.images = state.images.filter((source: any) => !(source.kind === "asset" && source.id === assetId));
    if (!state.images.length) {
      setMode("generate");
    }
    renderRecentAssets();
    if (recentAssetLoadState === "loading") void refreshRecentAssets();
    renderImageStrip();
    updateRequestPreview();
    setStatus(translate("recentAssets.deleted"), "ok");
  } catch (error: any) {
    setStatus(error.message || translate("recentAssets.deleteFailed"), "error");
  }
}

export function initRecentAssetsFeature() {
  if (recentAssetsFeatureInitialized) return;
  recentAssetsFeatureInitialized = true;
  recentAssetPreviewsHidden = readRecentAssetPreviewsHidden();
  syncRecentAssetPreviewVisibility();
  els.recentAssetList?.addEventListener("wheel", handleRecentAssetWheel, { passive: false });
  els.recentAssetList?.addEventListener("scroll", handleRecentAssetScroll, { passive: true });
  els.recentAssetList?.addEventListener("click", handleRecentAssetClick);
  els.recentAssetList?.addEventListener("error", handleRecentAssetImageError, true);
  els.recentAssetStatus?.addEventListener("click", (event: Event) => {
    const target = event.target instanceof Element ? event.target : null;
    if (!target?.closest("[data-recent-assets-retry]")) return;
    void refreshRecentAssets();
  });
  els.recentAssetVisibilityToggle?.addEventListener("click", toggleRecentAssetPreviews);
  document.addEventListener(LOCALE_CHANGE_EVENT, () => renderRecentAssets());
  Object.assign(getLegacyBridge().methods, {
    refreshRecentAssets,
    renderRecentAssets,
    handleRecentAssetWheel,
    handleRecentAssetScroll,
    toggleRecentAssetPreviews,
    hideRecentAsset,
    deleteRecentAsset,
  });
}

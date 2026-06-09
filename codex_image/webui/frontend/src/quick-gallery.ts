import { getLegacyBridge } from "./state";
import { formatTranslation } from "./i18n";

const QUICK_GALLERY_WHEEL_COOLDOWN_MS = 220;
const bridge = getLegacyBridge();
const state = bridge.state;
const els = bridge.els;

let quickGalleryFeatureInitialized = false;
let quickGalleryFocusFrameId: number | null = null;
let quickGalleryWheelLockTimerId: number | null = null;

function legacyMethod(name: string, ...args: any[]): any {
  const method = getLegacyBridge().methods[name];
  if (typeof method !== "function") {
    throw new Error("Legacy method " + name + " is not initialized");
  }
  return method(...args);
}

function escapeHtml(value: any): string { return legacyMethod("escapeHtml", value); }
function addGalleryInput(item: any, options?: any): void { legacyMethod("addGalleryInput", item, options); }
function filterGalleryItems(category?: any): any[] { return legacyMethod("filterGalleryItems", category); }
function findGalleryItem(itemId: any): any { return legacyMethod("findGalleryItem", itemId); }
function categoryLabel(category: any): string { return legacyMethod("categoryLabel", category); }
function renderGalleryCategoryControls(): void { legacyMethod("renderGalleryCategoryControls"); }

function renderQuickGalleryDock() {
  renderGalleryCategoryControls();
  renderQuickGalleryList();
  hideQuickGalleryPreview();
}

function renderQuickGalleryList() {
  if (!els.quickGalleryList) return;
  const items = filterGalleryItems();
  if (!items.length) {
    state.quickGalleryFocusItemId = null;
    els.quickGalleryList.innerHTML = `<div class="quick-gallery-empty">${escapeHtml(formatTranslation("quickGallery.empty", { category: categoryLabel(state.activeGalleryCategory) }))}</div>`;
    scheduleQuickGalleryFocusUpdate();
    return;
  }
  ensureQuickGalleryFocusItem(items);
  els.quickGalleryList.innerHTML = items.map((item: any) => `
    <button class="quick-gallery-item" type="button" data-quick-gallery-use="${escapeHtml(item.id)}">
      <span>${escapeHtml(item.name)}</span>
    </button>
  `).join("");
  els.quickGalleryList.querySelectorAll("[data-quick-gallery-use]").forEach((button: any) => {
    button.addEventListener("mouseenter", () => previewQuickGalleryItem(button.dataset.quickGalleryUse));
    button.addEventListener("focus", () => {
      previewQuickGalleryItem(button.dataset.quickGalleryUse);
      focusQuickGalleryItem(button.dataset.quickGalleryUse);
    });
    button.addEventListener("mouseleave", hideQuickGalleryPreview);
    button.addEventListener("blur", hideQuickGalleryPreview);
    button.addEventListener("click", () => {
      const item = findGalleryItem(button.dataset.quickGalleryUse);
      if (!item) return;
      const alreadySelected = state.images.some((source: any) => source.kind === "gallery" && source.id === item.id);
      addGalleryInput(item);
      if (!alreadySelected) {
        animateGalleryItemToInput(item, button);
      }
      hideQuickGalleryPreview();
    });
  });
  els.quickGalleryList.scrollTop = 0;
  scheduleQuickGalleryFocusUpdate();
}

function ensureQuickGalleryFocusItem(items: any) {
  if (!items.length) {
    state.quickGalleryFocusItemId = null;
    return;
  }
  if (!items.some((item: any) => item.id === state.quickGalleryFocusItemId)) {
    state.quickGalleryFocusItemId = items[0].id;
  }
}

function previewQuickGalleryItem(itemId: any) {
  state.hoveredGalleryItemId = itemId || null;
  if (!els.quickGalleryPreview) return;
  const item = findGalleryItem(itemId);
  els.quickGalleryList?.querySelectorAll("[data-quick-gallery-use]").forEach((button: any) => {
    button.classList.toggle("active", button.dataset.quickGalleryUse === itemId);
  });
  if (!item) {
    hideQuickGalleryPreview();
    return;
  }
  els.quickGalleryPreview.innerHTML = `
    <img src="${escapeHtml(item.image_url)}" alt="${escapeHtml(item.name)}">
    <span>${escapeHtml(item.name)}</span>
  `;
  els.quickGalleryPreview.classList.add("visible");
  scheduleQuickGalleryFocusUpdate();
}

function hideQuickGalleryPreview() {
  state.hoveredGalleryItemId = null;
  els.quickGalleryPreview?.classList.remove("visible");
  els.quickGalleryList?.querySelectorAll("[data-quick-gallery-use]").forEach((button: any) => {
    button.classList.remove("active");
  });
  scheduleQuickGalleryFocusUpdate();
}

function scheduleQuickGalleryFocusUpdate() {
  if (quickGalleryFocusFrameId !== null) {
    window.cancelAnimationFrame(quickGalleryFocusFrameId);
  }
  quickGalleryFocusFrameId = window.requestAnimationFrame(() => {
    quickGalleryFocusFrameId = null;
    updateQuickGalleryFocus();
  });
}

function updateQuickGalleryFocus() {
  if (!els.quickGalleryList) return;
  const buttons = Array.from(els.quickGalleryList.querySelectorAll(".quick-gallery-item")) as HTMLElement[];
  if (!buttons.length) return;
  const hoveredButton = state.hoveredGalleryItemId
    ? buttons.find((button) => button.dataset.quickGalleryUse === state.hoveredGalleryItemId)
    : null;
  const focusedButton = state.quickGalleryFocusItemId
    ? buttons.find((button) => button.dataset.quickGalleryUse === state.quickGalleryFocusItemId)
    : null;
  const focusButton = hoveredButton || focusedButton || buttons[0];
  if (!focusButton) return;
  const focusIndex = buttons.indexOf(focusButton);
  buttons.forEach((button) => {
    button.classList.remove("center", "near");
  });
  focusButton.classList.add("center");
  buttons
    .map((button) => ({ button, distance: Math.abs(buttons.indexOf(button) - focusIndex) }))
    .filter(({ button }) => button !== focusButton)
    .sort((left, right) => left.distance - right.distance)
    .slice(0, 2)
    .forEach(({ button }) => button.classList.add("near"));
}

function handleQuickGalleryBoundaryWheel(event: any) {
  if (!els.quickGalleryList) return;
  const list = els.quickGalleryList;
  const buttons = Array.from(list.querySelectorAll(".quick-gallery-item")) as HTMLElement[];
  if (!buttons.length || Math.abs(event.deltaY) <= Math.abs(event.deltaX)) return;
  event.preventDefault();
  if (quickGalleryWheelLockTimerId !== null) return;
  quickGalleryWheelLockTimerId = window.setTimeout(() => {
    quickGalleryWheelLockTimerId = null;
  }, QUICK_GALLERY_WHEEL_COOLDOWN_MS);
  const direction = event.deltaY > 0 ? 1 : -1;
  const currentIndex = currentQuickGalleryFocusIndex(buttons);
  const nextIndex = currentIndex + direction;
  if (nextIndex < 0) {
    triggerQuickGalleryBounce("top");
    return;
  }
  if (nextIndex >= buttons.length) {
    triggerQuickGalleryBounce("bottom");
    return;
  }
  scrollQuickGalleryItemToFocus(buttons[nextIndex]);
}

function triggerQuickGalleryBounce(direction: any) {
  if (!els.quickGalleryList) return;
  const className = direction === "bottom" ? "bounce-bottom" : "bounce-top";
  els.quickGalleryList.classList.remove("bounce-top", "bounce-bottom");
  void els.quickGalleryList.offsetHeight;
  els.quickGalleryList.classList.add(className);
  window.setTimeout(() => {
    els.quickGalleryList?.classList.remove(className);
  }, 180);
}

function currentQuickGalleryFocusIndex(buttons: any) {
  const focusIndex = buttons.findIndex((button: any) => button.dataset.quickGalleryUse === state.quickGalleryFocusItemId);
  if (focusIndex >= 0) return focusIndex;
  const classIndex = buttons.findIndex((button: any) => button.classList.contains("center"));
  if (classIndex >= 0) return classIndex;
  return 0;
}

function focusQuickGalleryItem(itemId: any) {
  if (!els.quickGalleryList || !itemId) return;
  const button = (Array.from(els.quickGalleryList.querySelectorAll(".quick-gallery-item")) as HTMLElement[])
    .find((itemButton) => itemButton.dataset.quickGalleryUse === itemId);
  scrollQuickGalleryItemToFocus(button);
}

function scrollQuickGalleryItemToFocus(button: any, behavior: any = "smooth") {
  if (!els.quickGalleryList || !button) return;
  const list = els.quickGalleryList;
  state.quickGalleryFocusItemId = button.dataset.quickGalleryUse || state.quickGalleryFocusItemId;
  const targetTop = button.offsetTop;
  const maxScrollTop = Math.max(0, list.scrollHeight - list.clientHeight);
  list.scrollTo({
    top: Math.max(0, Math.min(maxScrollTop, targetTop)),
    behavior,
  });
  scheduleQuickGalleryFocusUpdate();
}

function animateGalleryItemToInput(item: any, fromEl: any) {
  if (!item?.image_url || !fromEl || !els.imageStrip) return;
  const sourceRect = (els.quickGalleryPreview?.classList.contains("visible") ? els.quickGalleryPreview : fromEl).getBoundingClientRect();
  const targetRect = (els.imageStrip.querySelector(".thumb:last-child") || els.imageUploadSource || els.imageStrip).getBoundingClientRect();
  if (!sourceRect || !targetRect) return;
  const clone = document.createElement("img");
  clone.className = "gallery-fly-clone";
  clone.src = item.image_url;
  clone.alt = "";
  clone.style.left = `${sourceRect.left}px`;
  clone.style.top = `${sourceRect.top}px`;
  clone.style.width = `${sourceRect.width}px`;
  clone.style.height = `${sourceRect.height}px`;
  document.body.appendChild(clone);
  const deltaX = targetRect.left + (targetRect.width / 2) - sourceRect.left - (sourceRect.width / 2);
  const deltaY = targetRect.top + (targetRect.height / 2) - sourceRect.top - (sourceRect.height / 2);
  clone.animate([
    { transform: "translate3d(0, 0, 0) scale(1)", opacity: 0.96 },
    { transform: `translate3d(${deltaX}px, ${deltaY}px, 0) scale(0.28)`, opacity: 0.18 },
  ], { duration: 220, easing: "cubic-bezier(0.2, 0.8, 0.2, 1)" }).addEventListener("finish", () => clone.remove());
}

export function initQuickGalleryFeature() {
  if (quickGalleryFeatureInitialized) return;
  quickGalleryFeatureInitialized = true;
  Object.assign(getLegacyBridge().methods, {
    renderQuickGalleryDock,
    renderQuickGalleryList,
    ensureQuickGalleryFocusItem,
    previewQuickGalleryItem,
    hideQuickGalleryPreview,
    scheduleQuickGalleryFocusUpdate,
    updateQuickGalleryFocus,
    handleQuickGalleryBoundaryWheel,
    triggerQuickGalleryBounce,
    currentQuickGalleryFocusIndex,
    focusQuickGalleryItem,
    scrollQuickGalleryItemToFocus,
    animateGalleryItemToInput,
  });
}

import { getLegacyBridge } from "./state";
import { setGalleryDragPreview } from "./gallery-drag-preview";
import { formatTranslation, LOCALE_CHANGE_EVENT, translate } from "./i18n";

const GALLERY_GRID_TRANSITION_MS = 220;
const bridge = getLegacyBridge();
const state = bridge.state;
const els = bridge.els;

let galleryGridFeatureInitialized = false;
let galleryGridEventsBound = false;
let draggedGalleryItemId: string | null = null;
let galleryGridDropTargetId: string | null = null;
let galleryGridDropPlacement: "before" | "after" = "after";
let galleryGridOriginalOrder: string[] = [];

function legacyMethod(name: string, ...args: any[]): any {
  const method = getLegacyBridge().methods[name];
  if (typeof method !== "function") {
    throw new Error("Legacy method " + name + " is not initialized");
  }
  return method(...args);
}

function escapeHtml(value: any): string { return legacyMethod("escapeHtml", value); }
function ensureActiveGalleryCategory(): void { legacyMethod("ensureActiveGalleryCategory"); }
function categoryLabel(category: any): string { return legacyMethod("categoryLabel", category); }
function findGalleryItem(itemId: any): any { return legacyMethod("findGalleryItem", itemId); }
function filterGalleryItems(category?: any): any[] { return legacyMethod("filterGalleryItems", category); }
function addGalleryInput(item: any, options?: any): void { legacyMethod("addGalleryInput", item, options); }
function closeGallery(): void { legacyMethod("closeGallery"); }
function renameGalleryItem(button: any, itemId: any): void { legacyMethod("renameGalleryItem", button, itemId); }
function replaceGalleryItemImage(itemId: any): Promise<void> { return legacyMethod("replaceGalleryItemImage", itemId); }
function moveGalleryItem(button: any, itemId: any): void { legacyMethod("moveGalleryItem", button, itemId); }
function editGalleryPromptNote(button: any, itemId: any): void { legacyMethod("editGalleryPromptNote", button, itemId); }
function deleteGalleryItem(button: any, itemId: any): void { legacyMethod("deleteGalleryItem", button, itemId); }
function applyGalleryItemOrder(category: any, itemIds: string[]): void { legacyMethod("applyGalleryItemOrder", category, itemIds); }
function persistGalleryItemOrder(category: any, itemIds: string[]): Promise<void> { return legacyMethod("persistGalleryItemOrder", category, itemIds); }

function cssEscape(value: any): string {
  const text = String(value || "");
  if (window.CSS?.escape) return window.CSS.escape(text);
  return text.replace(/["\\]/g, "\\$&");
}

function measuredElementHeight(element: any): number {
  if (!element) return 0;
  return Math.ceil(element.getBoundingClientRect().height);
}

function renderGalleryGrid(options: any = {}) {
  if (options.animateHeight) {
    renderGalleryGridWithHeightTransition();
    return;
  }
  resetGalleryGridTransition(false);
  renderGalleryGridContent();
}

function renderGalleryGridWithHeightTransition() {
  if (!els.galleryGrid) return;
  if (!shouldAnimateGalleryGridHeight()) {
    renderGalleryGridContent();
    return;
  }
  const currentLayer = activeGalleryGridLayer();
  if (!currentLayer) {
    renderGalleryGridContent();
    return;
  }
  const transitionSeq = state.galleryGridTransitionSeq + 1;
  state.galleryGridTransitionSeq = transitionSeq;
  window.clearTimeout(state.galleryGridTransitionTimerId);

  els.galleryGrid.querySelectorAll(".gallery-grid-layer").forEach((layer: Element) => {
    if (layer !== currentLayer) layer.remove();
  });

  const startHeight = els.galleryGrid.getBoundingClientRect().height;
  els.galleryGrid.style.height = `${startHeight}px`;
  els.galleryGrid.classList.add("is-transitioning");

  const items = activeGalleryGridItems();
  const nextLayer = document.createElement("div");
  nextLayer.className = "gallery-grid-layer mode-transition mode-collapsed";
  nextLayer.innerHTML = galleryGridContentHtml(items);
  els.galleryGrid.append(nextLayer);

  const targetHeight = measuredElementHeight(nextLayer);
  void els.galleryGrid.offsetHeight;
  window.requestAnimationFrame(() => {
    if (state.galleryGridTransitionSeq !== transitionSeq) return;
    currentLayer.classList.add("mode-collapsed");
    nextLayer.classList.remove("mode-collapsed");
    els.galleryGrid.style.height = `${targetHeight}px`;
    bindGalleryGridActions(nextLayer);
    state.galleryGridTransitionTimerId = window.setTimeout(() => {
      if (state.galleryGridTransitionSeq !== transitionSeq) return;
      currentLayer.remove();
      resetGalleryGridTransition(false);
    }, GALLERY_GRID_TRANSITION_MS);
  });
}

function shouldAnimateGalleryGridHeight() {
  if (!els.galleryDrawer || !els.galleryDrawer.classList.contains("open")) return false;
  return !window.matchMedia?.("(prefers-reduced-motion: reduce)")?.matches;
}

function resetGalleryGridTransition(invalidate: any = true) {
  if (invalidate) state.galleryGridTransitionSeq += 1;
  window.clearTimeout(state.galleryGridTransitionTimerId);
  state.galleryGridTransitionTimerId = null;
  els.galleryGrid?.classList.remove("is-transitioning");
  if (els.galleryGrid) els.galleryGrid.style.height = "";
}

function renderGalleryGridContent() {
  if (!els.galleryGrid) return;
  const items = activeGalleryGridItems();
  els.galleryGrid.innerHTML = galleryGridLayerHtml(items);
  bindGalleryGridActions(els.galleryGrid);
}

function activeGalleryGridItems() {
  ensureActiveGalleryCategory();
  const items = filterGalleryItems(state.activeGalleryCategory);
  if (els.galleryDrawerSubtitle) {
    els.galleryDrawerSubtitle.textContent = formatTranslation("gallery.drawerSubtitle", {
      category: categoryLabel(state.activeGalleryCategory),
    });
  }
  return items;
}

function activeGalleryGridLayer(): Element | null {
  if (!els.galleryGrid) return null;
  const layers = Array.from(els.galleryGrid.querySelectorAll(".gallery-grid-layer")) as Element[];
  return layers.find((layer) => !layer.classList.contains("mode-collapsed")) || layers[layers.length - 1] || null;
}

function galleryGridLayerHtml(items: any) {
  return `<div class="gallery-grid-layer mode-transition">${galleryGridContentHtml(items)}</div>`;
}

function galleryGridContentHtml(items: any) {
  if (!items.length) {
    return `<div class="gallery-empty">${translate("gallery.emptyCategory")}</div>`;
  }
  return items.map((item: any) => `
    <article class="gallery-card" data-gallery-id="${escapeHtml(item.id)}">
      <button
        class="gallery-card-drag-strip"
        type="button"
        draggable="true"
        data-gallery-id="${escapeHtml(item.id)}"
        data-gallery-order-handle
        aria-label="${escapeHtml(formatTranslation("gallery.dragSortImage", { name: item.name }))}"
        title="${translate("gallery.dragSort")}"
      >
        <span class="gallery-card-drag-strip-icon" aria-hidden="true">
          <svg viewBox="0 0 16 16" focusable="false">
            <circle cx="5" cy="4" r="1.1" />
            <circle cx="11" cy="4" r="1.1" />
            <circle cx="5" cy="8" r="1.1" />
            <circle cx="11" cy="8" r="1.1" />
            <circle cx="5" cy="12" r="1.1" />
            <circle cx="11" cy="12" r="1.1" />
          </svg>
        </span>
        <span>${translate("gallery.dragSort")}</span>
      </button>
      <div class="gallery-card-media">
        <img src="${escapeHtml(item.image_url)}" alt="${escapeHtml(item.name)}" draggable="false">
      </div>
      <div class="gallery-card-body">
        <div class="gallery-card-heading">
          <strong>${escapeHtml(item.name)}</strong>
        </div>
        <span>${escapeHtml(categoryLabel(item.category))}</span>
      </div>
      <div class="gallery-card-actions">
        <button class="ghost-button text-sm" type="button" data-gallery-use="${escapeHtml(item.id)}">${translate("gallery.use")}</button>
        <button class="ghost-button text-sm" type="button" data-gallery-replace="${escapeHtml(item.id)}">${translate("gallery.replace")}</button>
        <button class="ghost-button text-sm" type="button" data-gallery-rename="${escapeHtml(item.id)}">${translate("gallery.rename")}</button>
        <button class="ghost-button text-sm" type="button" data-gallery-move="${escapeHtml(item.id)}">${translate("gallery.moveCategory")}</button>
        <button class="ghost-button text-sm" type="button" data-gallery-note="${escapeHtml(item.id)}">${translate("gallery.note")}</button>
        <button class="ghost-button text-sm danger-button" type="button" data-gallery-delete="${escapeHtml(item.id)}">${translate("gallery.delete")}</button>
      </div>
    </article>
  `).join("");
}

function bindGalleryGridActions(root: any = els.galleryGrid) {
  return root;
}

function handleGalleryGridClick(event: any) {
  const button = event.target.closest?.("[data-gallery-use],[data-gallery-rename],[data-gallery-replace],[data-gallery-move],[data-gallery-note],[data-gallery-delete]");
  if (!button || !els.galleryGrid?.contains(button)) return;
  if (button.dataset.galleryUse) {
    const item = findGalleryItem(button.dataset.galleryUse);
    if (item) addGalleryInput(item);
    closeGallery();
    return;
  }
  if (button.dataset.galleryRename) {
    renameGalleryItem(button, button.dataset.galleryRename);
    return;
  }
  if (button.dataset.galleryReplace) {
    replaceGalleryItemImage(button.dataset.galleryReplace);
    return;
  }
  if (button.dataset.galleryMove) {
    moveGalleryItem(button, button.dataset.galleryMove);
    return;
  }
  if (button.dataset.galleryNote) {
    editGalleryPromptNote(button, button.dataset.galleryNote);
    return;
  }
  if (button.dataset.galleryDelete) {
    deleteGalleryItem(button, button.dataset.galleryDelete);
  }
}

function clearGalleryGridDragState() {
  const originalOrder = galleryGridOriginalOrder.slice();
  const shouldRestoreOriginalOrder = Boolean(draggedGalleryItemId && originalOrder.length);
  if (shouldRestoreOriginalOrder) restoreGalleryGridDomOrder(originalOrder);
  draggedGalleryItemId = null;
  galleryGridDropTargetId = null;
  galleryGridDropPlacement = "after";
  galleryGridOriginalOrder = [];
  els.galleryGrid?.classList.remove("is-drag-sorting");
  els.galleryGrid?.querySelectorAll?.(".gallery-card").forEach((card: any) => {
    card.classList.remove("is-dragging", "drop-target", "drop-before", "drop-after");
  });
}

function finishGalleryGridDrag() {
  draggedGalleryItemId = null;
  galleryGridDropTargetId = null;
  galleryGridDropPlacement = "after";
  galleryGridOriginalOrder = [];
  els.galleryGrid?.classList.remove("is-drag-sorting");
  els.galleryGrid?.querySelectorAll?.(".gallery-card").forEach((card: any) => {
    card.classList.remove("is-dragging", "drop-target", "drop-before", "drop-after");
  });
}

function galleryCardElement(itemId: any) {
  return els.galleryGrid?.querySelector?.(`.gallery-card[data-gallery-id="${cssEscape(itemId)}"]`) || null;
}

function activeGalleryGridLayerElement() {
  const layer = activeGalleryGridLayer();
  return layer instanceof HTMLElement ? layer : null;
}

function galleryGridDomOrder(): string[] {
  const layer = activeGalleryGridLayerElement();
  return Array.from(layer?.querySelectorAll(".gallery-card[data-gallery-id]") || [])
    .map((card: any) => String(card.dataset.galleryId || ""))
    .filter(Boolean);
}

function sameGalleryGridOrder(left: string[], right: string[]): boolean {
  return left.length === right.length && left.every((id, index) => id === right[index]);
}

function restoreGalleryGridDomOrder(itemIds: string[]) {
  const layer = activeGalleryGridLayerElement();
  if (!layer) return;
  const cards = new Map(
    Array.from(layer.querySelectorAll(".gallery-card[data-gallery-id]"))
      .map((card: any) => [String(card.dataset.galleryId || ""), card] as [string, HTMLElement])
  );
  itemIds.forEach((itemId) => {
    const card = cards.get(itemId);
    if (card) layer.append(card);
  });
}

function moveGalleryGridDragPlaceholder(targetCard: HTMLElement, placement: "before" | "after") {
  if (!draggedGalleryItemId) return;
  const draggedCard = galleryCardElement(draggedGalleryItemId) as HTMLElement | null;
  const parent = targetCard.parentElement;
  if (!draggedCard || !parent || draggedCard === targetCard || draggedCard.parentElement !== parent) return;
  if (placement === "before") {
    parent.insertBefore(draggedCard, targetCard);
    return;
  }
  parent.insertBefore(draggedCard, targetCard.nextSibling);
}

function galleryCardDropPlacement(event: DragEvent, card: HTMLElement) {
  const rect = card.getBoundingClientRect();
  const xDelta = event.clientX - (rect.left + rect.width / 2);
  const yDelta = event.clientY - (rect.top + rect.height / 2);
  if (Math.abs(yDelta) > Math.abs(xDelta)) {
    return yDelta < 0 ? "before" : "after";
  }
  return xDelta < 0 ? "before" : "after";
}

function handleGalleryGridDragStart(event: DragEvent) {
  const handle = (event.target as Element | null)?.closest?.("[data-gallery-order-handle]");
  const itemId = String((handle as HTMLElement | null)?.dataset.galleryId || "");
  if (!handle || !itemId || !els.galleryGrid?.contains(handle)) return;
  const item = findGalleryItem(itemId);
  const card = galleryCardElement(itemId) as HTMLElement | null;
  draggedGalleryItemId = itemId;
  galleryGridDropTargetId = null;
  galleryGridDropPlacement = "after";
  galleryGridOriginalOrder = activeGalleryGridItems().map((galleryItem: any) => String(galleryItem.id));
  event.dataTransfer?.setData("text/plain", itemId);
  if (event.dataTransfer) event.dataTransfer.effectAllowed = "move";
  setGalleryDragPreview(event, {
    type: "item",
    title: item?.name || translate("gallery.imageFallback"),
    subtitle: categoryLabel(item?.category || state.activeGalleryCategory),
    imageUrl: item?.image_url,
    sourceElement: card,
  });
  window.requestAnimationFrame(() => {
    galleryCardElement(itemId)?.classList.add("is-dragging");
    els.galleryGrid?.classList.add("is-drag-sorting");
  });
}

function handleGalleryGridDragOver(event: DragEvent) {
  if (!draggedGalleryItemId || !els.galleryGrid) return;
  event.preventDefault();
  if (event.dataTransfer) event.dataTransfer.dropEffect = "move";
  const targetCard = (event.target as Element | null)?.closest?.(".gallery-card[data-gallery-id]") as HTMLElement | null;
  if (!targetCard || !els.galleryGrid.contains(targetCard)) return;
  const targetId = String(targetCard.dataset.galleryId || "");
  if (!targetId || targetId === draggedGalleryItemId) return;
  const placement = galleryCardDropPlacement(event, targetCard);
  if (galleryGridDropTargetId === targetId && galleryGridDropPlacement === placement) return;
  galleryGridDropTargetId = targetId;
  galleryGridDropPlacement = placement;
  moveGalleryGridDragPlaceholder(targetCard, placement);
  els.galleryGrid.querySelectorAll(".gallery-card").forEach((card: any) => {
    card.classList.toggle("drop-target", card === targetCard);
    card.classList.toggle("drop-before", card === targetCard && placement === "before");
    card.classList.toggle("drop-after", card === targetCard && placement === "after");
  });
}

function handleGalleryGridDrop(event: DragEvent) {
  if (!draggedGalleryItemId) {
    finishGalleryGridDrag();
    return;
  }
  const draggedId = draggedGalleryItemId;
  event.preventDefault();
  const originalOrder = galleryGridOriginalOrder.length
    ? galleryGridOriginalOrder.slice()
    : activeGalleryGridItems().map((item: any) => String(item.id));
  const reorderedIds = galleryGridDomOrder();
  finishGalleryGridDrag();
  if (!reorderedIds.includes(draggedId) || sameGalleryGridOrder(originalOrder, reorderedIds)) return;
  applyGalleryItemOrder(state.activeGalleryCategory, reorderedIds);
  void persistGalleryItemOrder(state.activeGalleryCategory, reorderedIds);
}

function handleGalleryGridDragEnd() {
  clearGalleryGridDragState();
}

function bindGalleryGridEvents() {
  if (galleryGridEventsBound) return;
  galleryGridEventsBound = true;
  els.galleryGrid?.addEventListener("click", handleGalleryGridClick);
  els.galleryGrid?.addEventListener("dragstart", handleGalleryGridDragStart);
  els.galleryGrid?.addEventListener("dragover", handleGalleryGridDragOver);
  els.galleryGrid?.addEventListener("drop", handleGalleryGridDrop);
  els.galleryGrid?.addEventListener("dragend", handleGalleryGridDragEnd);
  els.galleryGrid?.addEventListener("dragleave", (event: DragEvent) => {
    if (!draggedGalleryItemId) return;
    const related = event.relatedTarget as Node | null;
    if (related && els.galleryGrid?.contains(related)) return;
    els.galleryGrid?.querySelectorAll(".gallery-card").forEach((card: any) => {
      card.classList.remove("drop-target", "drop-before", "drop-after");
    });
    galleryGridDropTargetId = null;
  });
}

export function initGalleryGridFeature() {
  if (galleryGridFeatureInitialized) return;
  galleryGridFeatureInitialized = true;
  document.addEventListener(LOCALE_CHANGE_EVENT, () => {
    renderGalleryGrid();
  });
  bindGalleryGridEvents();
  Object.assign(getLegacyBridge().methods, {
    renderGalleryGrid,
    renderGalleryGridWithHeightTransition,
    shouldAnimateGalleryGridHeight,
    resetGalleryGridTransition,
    renderGalleryGridContent,
    activeGalleryGridItems,
    activeGalleryGridLayer,
    galleryGridLayerHtml,
    galleryGridContentHtml,
    bindGalleryGridActions,
    handleGalleryGridClick,
    handleGalleryGridDragStart,
    handleGalleryGridDragOver,
    handleGalleryGridDrop,
    handleGalleryGridDragEnd,
  });
}

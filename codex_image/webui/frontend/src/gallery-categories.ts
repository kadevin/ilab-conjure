import { getLegacyBridge } from "./state";
import { setGalleryDragPreview } from "./gallery-drag-preview";
import { formatTranslation, LOCALE_CHANGE_EVENT, translate } from "./i18n";

interface GalleryCategory {
  id: string;
  name: string;
  prompt_role: string;
  order: number;
  locked: boolean;
}

const DEFAULT_GALLERY_CATEGORY_IDS = ["portrait", "character", "product"];
const DEFAULT_GALLERY_CATEGORY_LEGACY_LABELS: Record<string, string> = {
  portrait: "\u4eba\u50cf",
  character: "\u89d2\u8272",
  product: "\u4ea7\u54c1",
};
const DEFAULT_GALLERY_CATEGORY_LEGACY_ROLES: Record<string, string> = {
  portrait: "\u4eba\u50cf\u53c2\u8003",
  character: "\u89d2\u8272\u53c2\u8003",
  product: "\u4ea7\u54c1\u53c2\u8003",
};

const DEFAULT_GALLERY_CATEGORY_I18N_KEYS: Record<string, string> = {
  portrait: "gallery.categoryPortrait",
  character: "gallery.categoryCharacter",
  product: "gallery.categoryProduct",
};

const DEFAULT_GALLERY_CATEGORY_ROLE_I18N_KEYS: Record<string, string> = {
  portrait: "gallery.categoryPortraitRole",
  character: "gallery.categoryCharacterRole",
  product: "gallery.categoryProductRole",
};

const bridge = getLegacyBridge();
const state = bridge.state;
const els = bridge.els;

let galleryCategoriesFeatureInitialized = false;
let galleryCategoriesEventsBound = false;
let galleryCategoryManagerExpanded = false;
let draggedGalleryCategoryId: string | null = null;
let galleryCategoryDropTargetId: string | null = null;
let galleryCategoryDropPlacement: "before" | "after" = "after";
let galleryCategoryOriginalOrder: string[] = [];

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
function closeConfirmPopover(): void { legacyMethod("closeConfirmPopover"); }
function closeGalleryEditPopover(): void { legacyMethod("closeGalleryEditPopover"); }
function renderQuickGalleryDock(): void { legacyMethod("renderQuickGalleryDock"); }
function renderGalleryGrid(options?: any): void { legacyMethod("renderGalleryGrid", options); }
function renderImageStrip(): void { legacyMethod("renderImageStrip"); }
function updateRequestPreview(): void { legacyMethod("updateRequestPreview"); }
function refreshGallery(): Promise<void> { return legacyMethod("refreshGallery"); }

function cssEscape(value: any): string {
  const text = String(value || "");
  if (window.CSS?.escape) return window.CSS.escape(text);
  return text.replace(/["\\]/g, "\\$&");
}

function defaultGalleryCategories(): GalleryCategory[] {
  return DEFAULT_GALLERY_CATEGORY_IDS.map((id, index) => ({
    id,
    name: defaultGalleryCategoryLabel(id) || id,
    prompt_role: defaultGalleryCategoryPromptRole(id),
    order: (index + 1) * 10,
    locked: false,
  }));
}

function defaultGalleryCategoryLabel(categoryId: any): string {
  const key = DEFAULT_GALLERY_CATEGORY_I18N_KEYS[String(categoryId || "")];
  return key ? translate(key) : "";
}

function defaultGalleryCategoryPromptRole(categoryId: any): string {
  const key = DEFAULT_GALLERY_CATEGORY_ROLE_I18N_KEYS[String(categoryId || "")];
  return key ? translate(key) : "";
}

function displayGalleryCategoryName(category: GalleryCategory): string {
  const defaultLabel = defaultGalleryCategoryLabel(category.id);
  const storedDefaultLabel = DEFAULT_GALLERY_CATEGORY_LEGACY_LABELS[category.id];
  if (defaultLabel && (!category.name || category.name === storedDefaultLabel)) {
    return defaultLabel;
  }
  return category.name;
}

function displayGalleryCategoryPromptRole(category: GalleryCategory): string {
  const defaultRole = defaultGalleryCategoryPromptRole(category.id);
  const storedDefaultRole = DEFAULT_GALLERY_CATEGORY_LEGACY_ROLES[category.id];
  if (defaultRole && (!category.prompt_role || category.prompt_role === storedDefaultRole)) {
    return defaultRole;
  }
  return category.prompt_role;
}

function normalizeGalleryCategory(category: any): GalleryCategory | null {
  const id = String(category?.id || "").trim();
  if (!id) return null;
  const name = String(category?.name || defaultGalleryCategoryLabel(id) || DEFAULT_GALLERY_CATEGORY_LEGACY_LABELS[id] || id).trim() || id;
  const promptRole = String(category?.prompt_role || defaultGalleryCategoryPromptRole(id) || name).trim() || name;
  const order = Number.isFinite(Number(category?.order)) ? Number(category.order) : 0;
  return {
    id,
    name,
    prompt_role: promptRole,
    order,
    locked: Boolean(category?.locked),
  };
}

function normalizeGalleryCategories(categories: any): GalleryCategory[] {
  const source: any[] = Array.isArray(categories) && categories.length ? categories : defaultGalleryCategories();
  const seen = new Set();
  return source
    .map(normalizeGalleryCategory)
    .filter((category): category is GalleryCategory => {
      if (!category || seen.has(category.id)) return false;
      seen.add(category.id);
      return true;
    })
    .sort((left, right) => (left.order - right.order) || left.name.localeCompare(right.name, "zh-CN", { numeric: true, sensitivity: "base" }));
}

function handleQuickGalleryCategoryEvent(event: any) {
  const button = event.target.closest?.("[data-quick-gallery-category]");
  if (!button || !els.quickGalleryRail?.contains(button)) return;
  setQuickGalleryCategory(button.dataset.quickGalleryCategory);
}

function ensureActiveGalleryCategory() {
  if (findGalleryCategory(state.activeGalleryCategory)) return;
  state.activeGalleryCategory = state.galleryCategories[0]?.id || "portrait";
}

function renderGalleryCategoryControls() {
  ensureActiveGalleryCategory();
  const categories = normalizeGalleryCategories(state.galleryCategories);
  if (els.quickGalleryRail) {
    els.quickGalleryRail.innerHTML = categories.map((category) => `
      <button class="quick-gallery-category${category.id === state.activeGalleryCategory ? " active" : ""}" data-quick-gallery-category="${escapeHtml(category.id)}" type="button">${escapeHtml(categoryLabel(category.id))}</button>
    `).join("");
  }
  if (els.galleryCategoryInput) {
    const currentValue = els.galleryCategoryInput.value || state.activeGalleryCategory;
    els.galleryCategoryInput.innerHTML = categories.map((category) => `
      <option value="${escapeHtml(category.id)}">${escapeHtml(categoryLabel(category.id))}</option>
    `).join("");
    els.galleryCategoryInput.value = findGalleryCategory(currentValue) ? currentValue : state.activeGalleryCategory;
  }
  renderGalleryDrawerCategoryTabs();
  renderGalleryCategoryManager();
  syncGalleryCategoryManagerVisibility();
}

function renderGalleryDrawerCategoryTabs() {
  if (!els.galleryDrawerCategoryTabs) return;
  const categories = normalizeGalleryCategories(state.galleryCategories);
  els.galleryDrawerCategoryTabs.innerHTML = categories.map((category) => `
    <button
      class="quick-gallery-category${category.id === state.activeGalleryCategory ? " active" : ""}"
      data-gallery-drawer-category="${escapeHtml(category.id)}"
      type="button"
    >
      ${escapeHtml(categoryLabel(category.id))}
    </button>
  `).join("");
}

function renderGalleryCategoryManager() {
  if (!els.galleryCategoryList) return;
  const categories = normalizeGalleryCategories(state.galleryCategories);
  els.galleryCategoryList.innerHTML = categories.map((category) => `
    <div
      class="gallery-category-row${category.id === state.activeGalleryCategory ? " is-current" : ""}"
      data-gallery-category-row="${escapeHtml(category.id)}"
      ${category.id === state.activeGalleryCategory ? 'aria-current="true"' : ""}
    >
      <div class="gallery-category-row-toolbar">
        <button
          class="ghost-button gallery-drag-handle gallery-category-drag-handle"
          type="button"
          draggable="true"
          data-gallery-category-id="${escapeHtml(category.id)}"
          data-gallery-category-drag-handle
          aria-label="${escapeHtml(formatTranslation("gallery.dragSortCategory", { name: categoryLabel(category.id) }))}"
          title="${translate("gallery.dragSort")}"
        >
          <svg viewBox="0 0 16 16" aria-hidden="true" focusable="false">
            <circle cx="5" cy="4" r="1.1" />
            <circle cx="11" cy="4" r="1.1" />
            <circle cx="5" cy="8" r="1.1" />
            <circle cx="11" cy="8" r="1.1" />
            <circle cx="5" cy="12" r="1.1" />
            <circle cx="11" cy="12" r="1.1" />
          </svg>
        </button>
      </div>
      <input class="control" type="text" maxlength="32" value="${escapeHtml(categoryLabel(category.id))}" data-gallery-category-name="${escapeHtml(category.id)}" aria-label="${escapeHtml(translate("gallery.categoryName"))}">
      <input class="control" type="text" maxlength="48" value="${escapeHtml(categoryPromptRole(category.id))}" data-gallery-category-prompt-role="${escapeHtml(category.id)}" aria-label="${escapeHtml(translate("gallery.categoryPromptRole"))}">
      <div class="gallery-category-row-actions">
        <button class="ghost-button text-sm" type="button" data-gallery-category-save="${escapeHtml(category.id)}">${escapeHtml(translate("gallery.categorySave"))}</button>
        <button class="ghost-button text-sm danger-button" type="button" data-gallery-category-delete="${escapeHtml(category.id)}" ${categories.length <= 1 ? "disabled" : ""}>${escapeHtml(translate("gallery.categoryDelete"))}</button>
      </div>
    </div>
  `).join("");
}

function handleGalleryDrawerCategoryTabClick(event: any) {
  const button = event.target.closest?.("[data-gallery-drawer-category]");
  if (!button || !els.galleryDrawerCategoryTabs?.contains(button)) return;
  setGalleryDrawerCategory(button.dataset.galleryDrawerCategory);
}

function handleGalleryCategoryListClick(event: any) {
  const button = event.target.closest?.("[data-gallery-category-save],[data-gallery-category-delete]");
  if (!button || !els.galleryCategoryList?.contains(button) || button.disabled) return;
  if (button.dataset.galleryCategorySave) {
    updateGalleryCategory(button.dataset.galleryCategorySave);
    return;
  }
  if (button.dataset.galleryCategoryDelete) {
    deleteGalleryCategory(button, button.dataset.galleryCategoryDelete);
  }
}

function toggleGalleryCategoryManager() {
  galleryCategoryManagerExpanded = !galleryCategoryManagerExpanded;
  syncGalleryCategoryManagerVisibility();
}

function syncGalleryCategoryManagerVisibility() {
  els.galleryCategoryManagePanel?.classList.toggle("hidden", !galleryCategoryManagerExpanded);
  els.galleryCategoryManageToggle?.setAttribute("aria-expanded", galleryCategoryManagerExpanded ? "true" : "false");
  els.galleryCategoryManageToggle?.classList.toggle("active", galleryCategoryManagerExpanded);
}

async function refreshGalleryCategories() {
  try {
    const response = await fetch("/api/gallery/categories");
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || translate("gallery.categoryLoadFailed"));
    state.galleryCategories = normalizeGalleryCategories(data.categories);
    ensureActiveGalleryCategory();
    renderGalleryCategoryControls();
    renderQuickGalleryDock();
    renderGalleryGrid();
    renderImageStrip();
    updateRequestPreview();
  } catch (error: any) {
    setStatus(error.message || translate("gallery.categoryLoadFailed"), "error");
  }
}

async function createGalleryCategory() {
  const name = els.newGalleryCategoryName?.value.trim() || "";
  const promptRole = els.newGalleryCategoryPromptRole?.value.trim() || name;
  if (!name) {
    setStatus(translate("gallery.categoryNameRequired"), "error");
    return;
  }
  try {
    const response = await fetch("/api/gallery/categories", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name, prompt_role: promptRole }),
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || translate("gallery.categoryCreateFailed"));
    if (els.newGalleryCategoryName) els.newGalleryCategoryName.value = "";
    if (els.newGalleryCategoryPromptRole) els.newGalleryCategoryPromptRole.value = "";
    state.activeGalleryCategory = data.category?.id || state.activeGalleryCategory;
    await refreshGalleryCategories();
    setStatus(translate("gallery.categoryCreated"), "ok");
  } catch (error: any) {
    setStatus(error.message || translate("gallery.categoryCreateFailed"), "error");
  }
}

async function updateGalleryCategory(categoryId: any) {
  const row = els.galleryCategoryList?.querySelector(`[data-gallery-category-row="${cssEscape(categoryId)}"]`);
  if (!row) return;
  const name = row.querySelector("[data-gallery-category-name]")?.value.trim();
  const promptRole = row.querySelector("[data-gallery-category-prompt-role]")?.value.trim() || name;
  const category = findGalleryCategory(categoryId);
  if (!name) {
    setStatus(translate("gallery.categoryNameRequired"), "error");
    return;
  }
  try {
    const response = await fetch(`/api/gallery/categories/${encodeURIComponent(categoryId)}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name, prompt_role: promptRole, order: category?.order }),
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || translate("gallery.categorySaveFailed"));
    await refreshGalleryCategories();
    setStatus(translate("gallery.categorySaved"), "ok");
  } catch (error: any) {
    setStatus(error.message || translate("gallery.categorySaveFailed"), "error");
  }
}

function deleteGalleryCategory(button: any, categoryId: any) {
  const category = findGalleryCategory(categoryId);
  if (!category || state.galleryCategories.length <= 1) return;
  const moveTo = state.galleryCategories.find((candidate: any) => candidate.id !== categoryId)?.id;
  const target = findGalleryCategory(moveTo);
  openConfirmPopover(button, {
    title: translate("gallery.categoryDeleteTitle"),
    message: translate("gallery.categoryDeleteMessage"),
    detail: target ? `${categoryLabel(category.id)} -> ${categoryLabel(target.id)}` : categoryLabel(category.id),
    confirmText: translate("gallery.categoryDeleteConfirm"),
    onConfirm: async () => {
      await performDeleteGalleryCategory(categoryId, moveTo, category.name);
    },
  });
}

async function performDeleteGalleryCategory(categoryId: any, moveTo: any, categoryName: any) {
  try {
    const response = await fetch(`/api/gallery/categories/${encodeURIComponent(categoryId)}?move_to=${encodeURIComponent(moveTo)}`, {
      method: "DELETE",
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.detail || translate("gallery.categoryDeleteFailed"));
    if (state.activeGalleryCategory === categoryId) state.activeGalleryCategory = moveTo;
    await refreshGallery();
    setStatus(formatTranslation("gallery.categoryDeletedMigrated", { name: categoryName }), "ok");
  } catch (error: any) {
    setStatus(error.message || translate("gallery.categoryDeleteFailed"), "error");
  }
}

function setQuickGalleryCategory(category: any) {
  if (!findGalleryCategory(category)) return;
  state.activeGalleryCategory = category;
  state.hoveredGalleryItemId = null;
  state.quickGalleryFocusItemId = null;
  renderGalleryCategoryControls();
  renderQuickGalleryDock();
  if (els.galleryDrawer?.classList.contains("open")) renderGalleryGrid({ animateHeight: true });
}

function setGalleryDrawerCategory(category: any) {
  if (!findGalleryCategory(category)) return;
  state.activeGalleryCategory = category;
  state.hoveredGalleryItemId = null;
  state.quickGalleryFocusItemId = null;
  closeGalleryEditPopover();
  closeConfirmPopover();
  renderGalleryCategoryControls();
  renderQuickGalleryDock();
  renderGalleryGrid({ animateHeight: true });
}

function findGalleryCategory(categoryId: any) {
  return state.galleryCategories.find((category: any) => category.id === categoryId);
}

function categoryRow(categoryId: any) {
  return els.galleryCategoryList?.querySelector?.(`[data-gallery-category-row="${cssEscape(categoryId)}"]`) || null;
}

function clearGalleryCategoryDragState() {
  const originalOrder = galleryCategoryOriginalOrder.slice();
  const shouldRestoreOriginalOrder = Boolean(draggedGalleryCategoryId && originalOrder.length);
  if (shouldRestoreOriginalOrder) restoreGalleryCategoryDomOrder(originalOrder);
  draggedGalleryCategoryId = null;
  galleryCategoryDropTargetId = null;
  galleryCategoryDropPlacement = "after";
  galleryCategoryOriginalOrder = [];
  els.galleryCategoryList?.classList.remove("is-drag-sorting");
  els.galleryCategoryList?.querySelectorAll?.(".gallery-category-row").forEach((row: any) => {
    row.classList.remove("is-dragging", "drop-target", "drop-before", "drop-after");
  });
}

function finishGalleryCategoryDrag() {
  draggedGalleryCategoryId = null;
  galleryCategoryDropTargetId = null;
  galleryCategoryDropPlacement = "after";
  galleryCategoryOriginalOrder = [];
  els.galleryCategoryList?.classList.remove("is-drag-sorting");
  els.galleryCategoryList?.querySelectorAll?.(".gallery-category-row").forEach((row: any) => {
    row.classList.remove("is-dragging", "drop-target", "drop-before", "drop-after");
  });
}

function applyGalleryCategoryOrder(categoryIds: string[]) {
  const orderMap = new Map(categoryIds.map((categoryId, index) => [categoryId, (index + 1) * 10]));
  state.galleryCategories = normalizeGalleryCategories(
    state.galleryCategories.map((category: any) => (
      orderMap.has(category.id)
        ? { ...category, order: orderMap.get(category.id) }
        : category
    ))
  );
  renderGalleryCategoryControls();
  renderQuickGalleryDock();
  renderGalleryGrid();
}

function categoryDomOrder(): string[] {
  return Array.from(els.galleryCategoryList?.querySelectorAll("[data-gallery-category-row]") || [])
    .map((row: any) => String(row.dataset.galleryCategoryRow || ""))
    .filter(Boolean);
}

function sameGalleryCategoryOrder(left: string[], right: string[]): boolean {
  return left.length === right.length && left.every((id, index) => id === right[index]);
}

function restoreGalleryCategoryDomOrder(categoryIds: string[]) {
  if (!els.galleryCategoryList) return;
  const rows = new Map(
    Array.from(els.galleryCategoryList.querySelectorAll("[data-gallery-category-row]"))
      .map((row: any) => [String(row.dataset.galleryCategoryRow || ""), row] as [string, HTMLElement])
  );
  categoryIds.forEach((categoryId) => {
    const row = rows.get(categoryId);
    if (row) els.galleryCategoryList?.append(row);
  });
}

function moveGalleryCategoryDragPlaceholder(targetRow: HTMLElement, placement: "before" | "after") {
  if (!draggedGalleryCategoryId || !els.galleryCategoryList) return;
  const draggedRow = categoryRow(draggedGalleryCategoryId) as HTMLElement | null;
  if (!draggedRow || draggedRow === targetRow) return;
  if (placement === "before") {
    els.galleryCategoryList.insertBefore(draggedRow, targetRow);
    return;
  }
  els.galleryCategoryList.insertBefore(draggedRow, targetRow.nextSibling);
}

async function persistGalleryCategoryOrder(categoryIds: string[]) {
  try {
    const response = await fetch("/api/gallery/categories/reorder", {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ category_ids: categoryIds }),
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.detail || translate("gallery.categoryOrderUpdateFailed"));
    state.galleryCategories = normalizeGalleryCategories(data.categories);
    renderGalleryCategoryControls();
    renderQuickGalleryDock();
    renderGalleryGrid();
    setStatus(translate("gallery.categoryOrderUpdated"), "ok");
  } catch (error: any) {
    await refreshGalleryCategories();
    setStatus(error.message || translate("gallery.categoryOrderUpdateFailed"), "error");
  }
}

function handleGalleryCategoryDragStart(event: DragEvent) {
  const handle = (event.target as Element | null)?.closest?.("[data-gallery-category-drag-handle]");
  const categoryId = String((handle as HTMLElement | null)?.dataset.galleryCategoryId || "");
  if (!handle || !categoryId || !els.galleryCategoryList?.contains(handle)) return;
  const category = findGalleryCategory(categoryId);
  draggedGalleryCategoryId = categoryId;
  galleryCategoryDropTargetId = null;
  galleryCategoryDropPlacement = "after";
  galleryCategoryOriginalOrder = normalizeGalleryCategories(state.galleryCategories).map((galleryCategory) => galleryCategory.id);
  event.dataTransfer?.setData("text/plain", categoryId);
  if (event.dataTransfer) event.dataTransfer.effectAllowed = "move";
  setGalleryDragPreview(event, {
    type: "category",
    title: category?.name || categoryId,
    subtitle: category ? categoryPromptRole(category.id) : translate("gallery.categoryFallback"),
    sourceElement: categoryRow(categoryId) as HTMLElement | null,
  });
  window.requestAnimationFrame(() => {
    categoryRow(categoryId)?.classList.add("is-dragging");
    els.galleryCategoryList?.classList.add("is-drag-sorting");
  });
}

function handleGalleryCategoryDragOver(event: DragEvent) {
  if (!draggedGalleryCategoryId || !els.galleryCategoryList) return;
  event.preventDefault();
  if (event.dataTransfer) event.dataTransfer.dropEffect = "move";
  const targetRow = (event.target as Element | null)?.closest?.("[data-gallery-category-row]") as HTMLElement | null;
  if (!targetRow || !els.galleryCategoryList.contains(targetRow)) return;
  const targetId = String(targetRow.dataset.galleryCategoryRow || "");
  if (!targetId || targetId === draggedGalleryCategoryId) return;
  const rect = targetRow.getBoundingClientRect();
  const placement = (event.clientY - rect.top) < (rect.height / 2) ? "before" : "after";
  if (galleryCategoryDropTargetId === targetId && galleryCategoryDropPlacement === placement) return;
  galleryCategoryDropTargetId = targetId;
  galleryCategoryDropPlacement = placement;
  moveGalleryCategoryDragPlaceholder(targetRow, placement);
  els.galleryCategoryList.querySelectorAll(".gallery-category-row").forEach((row: any) => {
    row.classList.toggle("drop-target", row === targetRow);
    row.classList.toggle("drop-before", row === targetRow && placement === "before");
    row.classList.toggle("drop-after", row === targetRow && placement === "after");
  });
}

function handleGalleryCategoryDrop(event: DragEvent) {
  if (!draggedGalleryCategoryId) {
    finishGalleryCategoryDrag();
    return;
  }
  const draggedId = draggedGalleryCategoryId;
  event.preventDefault();
  const originalOrder = galleryCategoryOriginalOrder.length
    ? galleryCategoryOriginalOrder.slice()
    : normalizeGalleryCategories(state.galleryCategories).map((category) => category.id);
  const reorderedIds = categoryDomOrder();
  finishGalleryCategoryDrag();
  if (!reorderedIds.includes(draggedId) || sameGalleryCategoryOrder(originalOrder, reorderedIds)) return;
  applyGalleryCategoryOrder(reorderedIds);
  void persistGalleryCategoryOrder(reorderedIds);
}

function handleGalleryCategoryDragEnd() {
  clearGalleryCategoryDragState();
}

function categoryLabel(category: any) {
  const galleryCategory = findGalleryCategory(category);
  if (galleryCategory) return displayGalleryCategoryName(galleryCategory);
  return defaultGalleryCategoryLabel(category) || category || translate("gallery.uncategorized");
}

function categoryPromptRole(category: any) {
  const galleryCategory = findGalleryCategory(category);
  return galleryCategory
    ? displayGalleryCategoryPromptRole(galleryCategory)
    : defaultGalleryCategoryPromptRole(category) || defaultGalleryCategoryLabel(category) || translate("gallery.referenceRole");
}

function bindGalleryCategoryEvents() {
  if (galleryCategoriesEventsBound) return;
  galleryCategoriesEventsBound = true;
  els.galleryDrawerCategoryTabs?.addEventListener("click", handleGalleryDrawerCategoryTabClick);
  els.galleryCategoryManageToggle?.addEventListener("click", toggleGalleryCategoryManager);
  els.galleryCategoryList?.addEventListener("click", handleGalleryCategoryListClick);
  els.galleryCategoryList?.addEventListener("dragstart", handleGalleryCategoryDragStart);
  els.galleryCategoryList?.addEventListener("dragover", handleGalleryCategoryDragOver);
  els.galleryCategoryList?.addEventListener("drop", handleGalleryCategoryDrop);
  els.galleryCategoryList?.addEventListener("dragend", handleGalleryCategoryDragEnd);
  els.galleryCategoryList?.addEventListener("dragleave", (event: DragEvent) => {
    if (!draggedGalleryCategoryId) return;
    const related = event.relatedTarget as Node | null;
    if (related && els.galleryCategoryList?.contains(related)) return;
    els.galleryCategoryList?.querySelectorAll(".gallery-category-row").forEach((row: any) => {
      row.classList.remove("drop-target", "drop-before", "drop-after");
    });
    galleryCategoryDropTargetId = null;
  });
}

export function initGalleryCategoriesFeature() {
  if (galleryCategoriesFeatureInitialized) return;
  galleryCategoriesFeatureInitialized = true;
  document.addEventListener(LOCALE_CHANGE_EVENT, () => {
    renderGalleryCategoryControls();
    renderQuickGalleryDock();
    renderGalleryGrid();
    renderImageStrip();
    updateRequestPreview();
  });
  bindGalleryCategoryEvents();
  Object.assign(getLegacyBridge().methods, {
    defaultGalleryCategories,
    defaultGalleryCategoryLabel,
    normalizeGalleryCategory,
    normalizeGalleryCategories,
    handleQuickGalleryCategoryEvent,
    ensureActiveGalleryCategory,
    renderGalleryCategoryControls,
    renderGalleryDrawerCategoryTabs,
    renderGalleryCategoryManager,
    handleGalleryDrawerCategoryTabClick,
    handleGalleryCategoryListClick,
    toggleGalleryCategoryManager,
    refreshGalleryCategories,
    createGalleryCategory,
    updateGalleryCategory,
    deleteGalleryCategory,
    performDeleteGalleryCategory,
    setQuickGalleryCategory,
    setGalleryDrawerCategory,
    findGalleryCategory,
    categoryLabel,
    categoryPromptRole,
    applyGalleryCategoryOrder,
    persistGalleryCategoryOrder,
    handleGalleryCategoryDragStart,
    handleGalleryCategoryDragOver,
    handleGalleryCategoryDrop,
    handleGalleryCategoryDragEnd,
  });
}

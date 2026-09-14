import { getLegacyBridge } from "./state";

const DRAG_START_THRESHOLD_PX = 6;
const AUTO_SCROLL_EDGE_PX = 36;
const AUTO_SCROLL_MAX_STEP_PX = 12;

type DragSession = {
  pointerId: number;
  handle: HTMLButtonElement;
  row: HTMLElement;
  originalOrder: string[];
  startX: number;
  startY: number;
  offsetX: number;
  offsetY: number;
  latestX: number;
  latestY: number;
  active: boolean;
  layer: HTMLElement | null;
  preview: HTMLElement | null;
  animationFrameId: number | null;
};

let initialized = false;
let providerList: HTMLElement | null = null;
let dragSession: DragSession | null = null;

export function isCompleteProviderOrder(
  candidate: readonly string[],
  current: readonly string[],
): boolean {
  if (candidate.length !== current.length || new Set(candidate).size !== candidate.length) return false;
  const currentIds = new Set(current);
  return candidate.every((id) => currentIds.has(id));
}

export function moveProviderId(
  order: readonly string[],
  providerId: string,
  targetIndex: number,
): string[] {
  const sourceIndex = order.indexOf(providerId);
  if (sourceIndex < 0) return [...order];
  const boundedTarget = Math.max(0, Math.min(order.length - 1, targetIndex));
  if (sourceIndex === boundedTarget) return [...order];
  const next = [...order];
  const [provider] = next.splice(sourceIndex, 1);
  if (provider === undefined) return [...order];
  next.splice(boundedTarget, 0, provider);
  return next;
}

export function providerOrderFromRows(list: HTMLElement): string[] {
  return Array.from(list.querySelectorAll<HTMLElement>(".api-provider-sort-row[data-api-provider-id]"))
    .map((row) => row.dataset.apiProviderId || "")
    .filter(Boolean);
}

function sortModeEnabled(): boolean {
  const bridge = getLegacyBridge();
  return Boolean(bridge.state.apiProviderSortMode && providerList?.classList.contains("is-sorting"));
}

function sameOrder(left: readonly string[], right: readonly string[]): boolean {
  return left.length === right.length && left.every((id, index) => id === right[index]);
}

function restoreProviderRows(list: HTMLElement, order: readonly string[]): void {
  const rowsById = new Map(
    Array.from(list.querySelectorAll<HTMLElement>(".api-provider-sort-row[data-api-provider-id]"))
      .map((row) => [row.dataset.apiProviderId || "", row]),
  );
  order.forEach((providerId) => {
    const row = rowsById.get(providerId);
    if (row) list.append(row);
  });
}

function removeDragListeners(): void {
  window.removeEventListener("pointermove", handlePointerMove);
  window.removeEventListener("pointerup", handlePointerUp);
  window.removeEventListener("pointercancel", handlePointerCancel);
  window.removeEventListener("keydown", handleWindowKeydown);
}

function cleanUpDrag(restoreOrder: boolean): DragSession | null {
  const session = dragSession;
  if (!session) return null;
  dragSession = null;
  removeDragListeners();
  if (session.animationFrameId !== null) window.cancelAnimationFrame(session.animationFrameId);
  if (restoreOrder && providerList) restoreProviderRows(providerList, session.originalOrder);
  session.row.classList.remove("is-dragging");
  session.layer?.remove();
  document.body.classList.remove("api-provider-sort-dragging");
  try {
    if (session.handle.hasPointerCapture(session.pointerId)) {
      session.handle.releasePointerCapture(session.pointerId);
    }
  } catch {
    // The browser may release capture before pointercancel reaches the window.
  }
  return session;
}

export function cancelApiProviderSortInteraction(restoreOrder = true): void {
  cleanUpDrag(restoreOrder);
}

function positionPreview(session: DragSession): void {
  if (!session.preview) return;
  const left = session.latestX - session.offsetX;
  const top = session.latestY - session.offsetY;
  session.preview.style.transform = `translate3d(${left}px, ${top}px, 0)`;
}

function createDragPreview(session: DragSession): void {
  const rect = session.row.getBoundingClientRect();
  const layer = document.createElement("div");
  layer.className = "api-provider-sort-drag-layer";
  layer.setAttribute("aria-hidden", "true");
  const preview = session.row.cloneNode(true) as HTMLElement;
  preview.classList.remove("is-dragging");
  preview.classList.add("api-provider-sort-drag-preview");
  preview.removeAttribute("role");
  preview.style.width = `${rect.width}px`;
  preview.style.height = `${rect.height}px`;
  preview.querySelectorAll<HTMLElement>("button, [tabindex]").forEach((element) => {
    element.setAttribute("tabindex", "-1");
  });
  layer.append(preview);
  document.body.append(layer);
  session.layer = layer;
  session.preview = preview;
  session.offsetX = session.startX - rect.left;
  session.offsetY = session.startY - rect.top;
  session.row.classList.add("is-dragging");
  document.body.classList.add("api-provider-sort-dragging");
  positionPreview(session);
}

function rowAtPoint(clientX: number, clientY: number): HTMLElement | null {
  if (!providerList) return null;
  for (const element of document.elementsFromPoint(clientX, clientY)) {
    const row = element.closest<HTMLElement>(".api-provider-sort-row[data-api-provider-id]");
    if (row && row.parentElement === providerList && row !== dragSession?.row) return row;
  }
  return null;
}

function reorderRowAtPoint(clientX: number, clientY: number): void {
  const session = dragSession;
  const target = rowAtPoint(clientX, clientY);
  if (!session?.active || !target) return;
  const targetRect = target.getBoundingClientRect();
  if (clientY < targetRect.top + targetRect.height / 2) {
    if (target.previousElementSibling !== session.row) target.before(session.row);
  } else if (target.nextElementSibling !== session.row) {
    target.after(session.row);
  }
}

function scrollContainer(): HTMLElement | null {
  return providerList?.closest<HTMLElement>(".system-settings-section") || null;
}

function autoScrollStep(): void {
  const session = dragSession;
  if (!session?.active) return;
  const container = scrollContainer();
  if (container && container.scrollHeight > container.clientHeight) {
    const rect = container.getBoundingClientRect();
    let step = 0;
    if (session.latestY < rect.top + AUTO_SCROLL_EDGE_PX) {
      const intensity = Math.min(1, (rect.top + AUTO_SCROLL_EDGE_PX - session.latestY) / AUTO_SCROLL_EDGE_PX);
      step = -Math.ceil(AUTO_SCROLL_MAX_STEP_PX * intensity);
    } else if (session.latestY > rect.bottom - AUTO_SCROLL_EDGE_PX) {
      const intensity = Math.min(1, (session.latestY - (rect.bottom - AUTO_SCROLL_EDGE_PX)) / AUTO_SCROLL_EDGE_PX);
      step = Math.ceil(AUTO_SCROLL_MAX_STEP_PX * intensity);
    }
    if (step !== 0) {
      const previousScrollTop = container.scrollTop;
      container.scrollTop += step;
      if (container.scrollTop !== previousScrollTop) {
        reorderRowAtPoint(session.latestX, session.latestY);
      }
    }
  }
  session.animationFrameId = window.requestAnimationFrame(autoScrollStep);
}

function activateDrag(session: DragSession): void {
  if (session.active) return;
  session.active = true;
  try {
    session.handle.setPointerCapture(session.pointerId);
  } catch {
    // Pointer capture can fail if the pointer was released between events.
  }
  createDragPreview(session);
  session.animationFrameId = window.requestAnimationFrame(autoScrollStep);
}

function handlePointerMove(event: PointerEvent): void {
  const session = dragSession;
  if (!session || event.pointerId !== session.pointerId) return;
  session.latestX = event.clientX;
  session.latestY = event.clientY;
  if (!session.active) {
    const deltaX = event.clientX - session.startX;
    const deltaY = event.clientY - session.startY;
    if (Math.hypot(deltaX, deltaY) < DRAG_START_THRESHOLD_PX) return;
    activateDrag(session);
  }
  event.preventDefault();
  positionPreview(session);
  reorderRowAtPoint(event.clientX, event.clientY);
}

function submitProviderOrder(order: string[], focusProviderId: string): void {
  const method = getLegacyBridge().methods.reorderApiProviders;
  if (typeof method === "function") method(order, focusProviderId);
}

function handlePointerUp(event: PointerEvent): void {
  const session = dragSession;
  if (!session || event.pointerId !== session.pointerId) return;
  const nextOrder = session.active && providerList ? providerOrderFromRows(providerList) : session.originalOrder;
  const providerId = session.row.dataset.apiProviderId || "";
  const wasActive = session.active;
  const originalOrder = session.originalOrder;
  cleanUpDrag(false);
  if (wasActive) event.preventDefault();
  if (wasActive && !sameOrder(nextOrder, originalOrder)) submitProviderOrder(nextOrder, providerId);
}

function handlePointerCancel(event: PointerEvent): void {
  if (event.pointerId !== dragSession?.pointerId) return;
  cleanUpDrag(true);
}

function handleWindowKeydown(event: KeyboardEvent): void {
  if (event.key === "Escape" && dragSession) {
    event.preventDefault();
    cleanUpDrag(true);
  }
}

function handlePointerDown(event: PointerEvent): void {
  if (!providerList || !sortModeEnabled() || event.button !== 0 || dragSession) return;
  const handle = (event.target as HTMLElement | null)?.closest<HTMLButtonElement>(
    "button[data-api-provider-sort-handle]",
  );
  const row = handle?.closest<HTMLElement>(".api-provider-sort-row[data-api-provider-id]");
  if (!handle || !row || row.parentElement !== providerList) return;
  dragSession = {
    pointerId: event.pointerId,
    handle,
    row,
    originalOrder: providerOrderFromRows(providerList),
    startX: event.clientX,
    startY: event.clientY,
    offsetX: 0,
    offsetY: 0,
    latestX: event.clientX,
    latestY: event.clientY,
    active: false,
    layer: null,
    preview: null,
    animationFrameId: null,
  };
  window.addEventListener("pointermove", handlePointerMove, { passive: false });
  window.addEventListener("pointerup", handlePointerUp);
  window.addEventListener("pointercancel", handlePointerCancel);
  window.addEventListener("keydown", handleWindowKeydown);
}

function handleSortKeydown(event: KeyboardEvent): void {
  if (!providerList || !sortModeEnabled() || dragSession) return;
  const handle = (event.target as HTMLElement | null)?.closest<HTMLButtonElement>(
    "button[data-api-provider-sort-handle]",
  );
  const providerId = handle?.dataset.apiProviderId || "";
  if (!handle || !providerId) return;
  const order = providerOrderFromRows(providerList);
  const index = order.indexOf(providerId);
  if (index < 0) return;
  let targetIndex: number | null = null;
  if (event.key === "ArrowUp") targetIndex = index - 1;
  else if (event.key === "ArrowDown") targetIndex = index + 1;
  else if (event.key === "Home") targetIndex = 0;
  else if (event.key === "End") targetIndex = order.length - 1;
  if (targetIndex === null) return;
  event.preventDefault();
  const nextOrder = moveProviderId(order, providerId, targetIndex);
  if (!sameOrder(nextOrder, order)) submitProviderOrder(nextOrder, providerId);
}

export function initApiProviderSortFeature(): void {
  if (initialized) return;
  const list = getLegacyBridge().els.apiProviderList as HTMLElement | null;
  if (!list) return;
  initialized = true;
  providerList = list;
  list.addEventListener("pointerdown", handlePointerDown);
  list.addEventListener("keydown", handleSortKeydown);
}

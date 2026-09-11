import { getLegacyBridge } from "./state";
import { prefersReducedMotion } from "./webui-utils";
import { cancelRunningTask, performCancelWaitingTask, promoteQueueTask } from "./queue";
import {
  resolveTaskCardSwipe,
  resolveTaskCardSwipeSurfaceOffset,
  taskCardSwipeActionRequiresConfirmation,
  TASK_CARD_SWIPE_OPEN_PX,
  type TaskCardSwipeAction,
  type TaskCardSwipeActions,
  type TaskCardSwipeFrame,
} from "./task-card-swipe-logic";

const bridge = getLegacyBridge();
const state = bridge.state;
const els = bridge.els;
const TASK_CARD_SWIPE_SETTLE_MS = 180;

type ActiveTaskCardSwipe = {
  pointerId: number;
  card: HTMLElement;
  startX: number;
  startY: number;
  startOffset: number;
  width: number;
  actions: TaskCardSwipeActions;
  horizontal: boolean;
  frame: TaskCardSwipeFrame;
};

let taskCardSwipeInitialized = false;
let activeSwipe: ActiveTaskCardSwipe | null = null;
let openTaskCard: HTMLElement | null = null;

function legacyMethod(name: string, ...args: any[]): any {
  const method = getLegacyBridge().methods[name];
  if (typeof method !== "function") {
    throw new Error("Legacy bridge method " + name + " is not available");
  }
  return method(...args);
}

function taskCardSwipeRoot(): HTMLElement | null {
  return els.taskHistoryShell || els.sidebarContent || els.taskList;
}

function eventTargetElement(event: Event): Element | null {
  return event.target instanceof Element ? event.target : null;
}

const TASK_CARD_SWIPE_ACTIONS = new Set<TaskCardSwipeAction>([
  "archive",
  "delete",
  "stop",
  "promote",
  "cancel",
]);

function taskCardSwipeAction(value: unknown): TaskCardSwipeAction | null {
  const action = String(value || "") as TaskCardSwipeAction;
  return TASK_CARD_SWIPE_ACTIONS.has(action) ? action : null;
}

function taskCardSwipeActions(card: HTMLElement): TaskCardSwipeActions {
  return {
    positive: taskCardSwipeAction(card.dataset.taskSwipePositiveAction),
    negative: taskCardSwipeAction(card.dataset.taskSwipeNegativeAction),
  };
}

function taskCardSwipeActionOffset(card: HTMLElement, action: TaskCardSwipeAction): number | null {
  const actions = taskCardSwipeActions(card);
  if (actions.positive === action) return TASK_CARD_SWIPE_OPEN_PX;
  if (actions.negative === action) return -TASK_CARD_SWIPE_OPEN_PX;
  return null;
}

function taskCardActionElements(card: HTMLElement) {
  const actions = card.querySelector<HTMLElement>(".task-card-swipe-actions");
  const buttons = Array.from(card.querySelectorAll<HTMLButtonElement>("[data-task-card-action]"));
  return { actions, buttons };
}

function setTaskCardActionAvailability(
  card: HTMLElement,
  direction: TaskCardSwipeAction | null,
  focusAction = false,
): void {
  const { actions, buttons } = taskCardActionElements(card);
  if (actions) {
    actions.setAttribute("aria-hidden", direction ? "false" : "true");
    if (direction) actions.removeAttribute("inert");
    else actions.setAttribute("inert", "");
  }
  buttons.forEach((button) => {
    const open = taskCardSwipeAction(button.dataset.taskCardAction) === direction;
    button.disabled = !open;
    button.tabIndex = open ? 0 : -1;
  });
  if (focusAction) {
    (buttons.find((button) => !button.disabled) || card).focus();
  }
}

function clearTaskCardSwipeStyles(card: HTMLElement): void {
  card.classList.remove(
    "task-card-swiping",
    "task-card-swipe-open",
    "task-card-swipe-settling",
    "task-card-action-pending",
  );
  card.removeAttribute("data-task-swipe-direction");
  card.removeAttribute("data-task-action-pending");
  card.removeAttribute("aria-busy");
  card.style.removeProperty("--task-card-swipe-x");
  setTaskCardActionAvailability(card, null);
}

function setTaskCardSwipePosition(card: HTMLElement, offset: number): void {
  const surfaceOffset = resolveTaskCardSwipeSurfaceOffset(offset);
  card.style.setProperty("--task-card-swipe-x", `${surfaceOffset}px`);
}

function closeTaskCardDrawer(
  card: HTMLElement,
  options: { immediate?: boolean; focusCard?: boolean } = {},
): void {
  const immediate = options.immediate === true || prefersReducedMotion();
  card.classList.remove("task-card-swiping", "task-card-swipe-open");
  card.classList.toggle("task-card-swipe-settling", !immediate);
  setTaskCardSwipePosition(card, 0);
  card.removeAttribute("data-task-swipe-direction");
  setTaskCardActionAvailability(card, null);
  if (openTaskCard === card) openTaskCard = null;
  if (options.focusCard) card.focus();
  if (immediate) {
    clearTaskCardSwipeStyles(card);
    return;
  }
  window.setTimeout(() => {
    if (!card.classList.contains("task-card-swipe-open") && !card.classList.contains("task-card-swiping")) {
      clearTaskCardSwipeStyles(card);
    }
  }, TASK_CARD_SWIPE_SETTLE_MS);
}

export function closeOpenTaskCardDrawer(options: { focusCard?: boolean; immediate?: boolean } = {}): void {
  const card = openTaskCard;
  if (!card) return;
  closeTaskCardDrawer(card, options);
}

function openTaskCardDrawer(
  card: HTMLElement,
  direction: TaskCardSwipeAction,
  focusAction = false,
): boolean {
  const offset = taskCardSwipeActionOffset(card, direction);
  if (offset === null) return false;
  if (openTaskCard && openTaskCard !== card) {
    closeTaskCardDrawer(openTaskCard, { immediate: prefersReducedMotion() });
  }
  card.classList.remove("task-card-swiping", "task-card-swipe-settling");
  card.classList.add("task-card-swipe-open");
  card.dataset.taskSwipeDirection = direction;
  setTaskCardSwipePosition(card, offset);
  setTaskCardActionAvailability(card, direction, focusAction);
  openTaskCard = card;
  return true;
}

function taskCardById(taskId: unknown): HTMLElement | null {
  const normalizedTaskId = String(taskId || "");
  if (!normalizedTaskId) return null;
  const root = taskCardSwipeRoot();
  if (!root) return null;
  return Array.from(root.querySelectorAll<HTMLElement>('.task-card[data-task-swipe-enabled="true"]'))
    .find((card) => String(card.dataset.taskId || "") === normalizedTaskId) || null;
}

export function revealTaskCardAction(
  taskId: unknown,
  action: TaskCardSwipeAction,
  focusAction = false,
): boolean {
  if (state.batchMode) return false;
  const card = taskCardById(taskId);
  if (!card || card.classList.contains("task-card-removing")) return false;
  return openTaskCardDrawer(card, action, focusAction);
}

function suppressClickAfterTaskCardSwipe(): void {
  state.suppressTaskClickAfterDrag = true;
  window.setTimeout(() => {
    state.suppressTaskClickAfterDrag = false;
  }, 0);
}

function stopTaskCardSwipeTracking(
  swipe: ActiveTaskCardSwipe,
  options: { releaseCapture?: boolean } = {},
): void {
  window.removeEventListener("pointermove", handleTaskCardSwipePointerMove);
  window.removeEventListener("pointerup", handleTaskCardSwipePointerUp);
  window.removeEventListener("pointercancel", handleTaskCardSwipePointerCancel);
  swipe.card.removeEventListener("lostpointercapture", handleTaskCardSwipeLostPointerCapture);
  if (activeSwipe === swipe) activeSwipe = null;
  if (options.releaseCapture !== false) {
    try {
      if (swipe.card.hasPointerCapture?.(swipe.pointerId)) {
        swipe.card.releasePointerCapture(swipe.pointerId);
      }
    } catch {
      // Capture may already have been transferred or cleared by the browser.
    }
  }
}

export function cancelActiveTaskCardSwipeTracking(
  options: { releaseCapture?: boolean } = {},
): boolean {
  const swipe = activeSwipe;
  if (!swipe) return false;
  stopTaskCardSwipeTracking(swipe, options);
  if (swipe.horizontal) suppressClickAfterTaskCardSwipe();
  closeTaskCardDrawer(swipe.card, { immediate: true });
  return true;
}

function resetInterruptedTaskCardSwipe(swipe: ActiveTaskCardSwipe): void {
  stopTaskCardSwipeTracking(swipe);
  if (swipe.horizontal) suppressClickAfterTaskCardSwipe();
  closeTaskCardDrawer(swipe.card, { immediate: true });
}

function applyTaskCardSwipeFrame(swipe: ActiveTaskCardSwipe, frame: TaskCardSwipeFrame): void {
  swipe.horizontal = true;
  swipe.frame = frame;
  if (openTaskCard === swipe.card) openTaskCard = null;
  swipe.card.classList.remove("task-card-swipe-open", "task-card-swipe-settling");
  swipe.card.classList.add("task-card-swiping");
  swipe.card.dataset.taskSwipeDirection = String(frame.direction || "");
  setTaskCardSwipePosition(swipe.card, frame.offset);
  setTaskCardActionAvailability(swipe.card, null);
}

function resolveTaskCardSwipeEventFrame(
  swipe: ActiveTaskCardSwipe,
  event: PointerEvent,
): TaskCardSwipeFrame {
  return resolveTaskCardSwipe(
    event.clientX - swipe.startX,
    event.clientY - swipe.startY,
    swipe.width,
    swipe.startOffset,
    swipe.actions,
  );
}

async function performTaskCardAction(
  card: HTMLElement,
  action: TaskCardSwipeAction,
  button: HTMLButtonElement,
): Promise<void> {
  if (card.classList.contains("task-card-action-pending")) return;
  const taskId = String(card.dataset.taskId || "");
  if (!taskId || card.dataset.taskSwipeDirection !== action) return;
  if (taskCardSwipeActionRequiresConfirmation(action) && action === "stop") {
    cancelRunningTask(button, taskId);
    closeTaskCardDrawer(card, { immediate: true });
    return;
  }
  if (action === "delete") {
    legacyMethod("openTaskDeleteConfirm", button, taskId);
    return;
  }
  card.classList.add("task-card-action-pending");
  card.dataset.taskActionPending = action;
  card.setAttribute("aria-busy", "true");
  setTaskCardActionAvailability(card, null);
  if (openTaskCard === card) openTaskCard = null;
  try {
    const succeeded = action === "archive"
      ? await legacyMethod("archiveTask", taskId)
      : action === "promote"
          ? await promoteQueueTask(taskId)
          : action === "cancel"
            ? await performCancelWaitingTask(taskId)
            : false;
    if (succeeded === false && card.isConnected) {
      card.classList.remove("task-card-action-pending");
      card.removeAttribute("data-task-action-pending");
      card.removeAttribute("aria-busy");
      openTaskCardDrawer(card, action, true);
    } else if ((action === "promote" || action === "cancel") && card.isConnected) {
      closeTaskCardDrawer(card);
    }
  } catch (error) {
    console.warn(error);
    if (card.isConnected) {
      card.classList.remove("task-card-action-pending");
      card.removeAttribute("data-task-action-pending");
      card.removeAttribute("aria-busy");
      openTaskCardDrawer(card, action, true);
    }
  }
}

function handleTaskCardSwipePointerDown(event: PointerEvent): void {
  if (state.batchMode) return;
  if (!event.isPrimary) return;
  if (event.pointerType === "mouse" && event.button !== 0) return;
  const target = eventTargetElement(event);
  if (!target || target.closest("button, input, select, textarea, a")) return;
  const root = taskCardSwipeRoot();
  const card = target.closest<HTMLElement>('.task-card[data-task-swipe-enabled="true"]');
  if (
    !root
    || !card
    || !root.contains(card)
    || card.classList.contains("task-card-removing")
    || card.classList.contains("task-card-action-pending")
  ) return;
  const surface = card.querySelector<HTMLElement>(".task-card-swipe-surface");
  if (!surface) return;

  if (activeSwipe) {
    closeTaskCardDrawer(activeSwipe.card, { immediate: true });
    stopTaskCardSwipeTracking(activeSwipe);
  }
  if (openTaskCard && openTaskCard !== card) {
    closeTaskCardDrawer(openTaskCard, { immediate: prefersReducedMotion() });
  }

  const rect = card.getBoundingClientRect();
  const actions = taskCardSwipeActions(card);
  const openDirection = taskCardSwipeAction(card.dataset.taskSwipeDirection);
  const startOffset = card.classList.contains("task-card-swipe-open")
    && openDirection
    ? (taskCardSwipeActionOffset(card, openDirection) || 0)
    : 0;
  activeSwipe = {
    pointerId: event.pointerId,
    card,
    startX: event.clientX,
    startY: event.clientY,
    startOffset,
    width: Math.max(1, rect.width),
    actions,
    horizontal: false,
    frame: resolveTaskCardSwipe(0, 0, rect.width, startOffset, actions),
  };
  window.addEventListener("pointermove", handleTaskCardSwipePointerMove);
  window.addEventListener("pointerup", handleTaskCardSwipePointerUp);
  window.addEventListener("pointercancel", handleTaskCardSwipePointerCancel);
  card.addEventListener("lostpointercapture", handleTaskCardSwipeLostPointerCapture);
  try {
    card.setPointerCapture?.(event.pointerId);
  } catch {
    // Window listeners still provide a fallback when pointer capture is unavailable.
  }
}

function handleTaskCardSwipePointerMove(event: PointerEvent): void {
  const swipe = activeSwipe;
  if (!swipe || event.pointerId !== swipe.pointerId) return;
  const frame = resolveTaskCardSwipeEventFrame(swipe, event);
  swipe.frame = frame;
  if (frame.axis === "pending") return;
  if (frame.axis === "vertical") {
    stopTaskCardSwipeTracking(swipe);
    return;
  }

  if (event.cancelable) event.preventDefault();
  applyTaskCardSwipeFrame(swipe, frame);
}

function handleTaskCardSwipePointerUp(event: PointerEvent): void {
  const swipe = activeSwipe;
  if (!swipe || event.pointerId !== swipe.pointerId) return;
  const frame = resolveTaskCardSwipeEventFrame(swipe, event);
  if (frame.axis === "horizontal") {
    applyTaskCardSwipeFrame(swipe, frame);
  } else {
    swipe.frame = frame;
  }
  stopTaskCardSwipeTracking(swipe);
  if (!swipe.horizontal) return;
  if (event.cancelable) event.preventDefault();
  suppressClickAfterTaskCardSwipe();
  if (swipe.frame.revealDirection) {
    openTaskCardDrawer(swipe.card, swipe.frame.revealDirection);
  } else {
    closeTaskCardDrawer(swipe.card);
  }
}

function handleTaskCardSwipePointerCancel(event: PointerEvent): void {
  const swipe = activeSwipe;
  if (!swipe || event.pointerId !== swipe.pointerId) return;
  stopTaskCardSwipeTracking(swipe);
  if (!swipe.horizontal) return;
  suppressClickAfterTaskCardSwipe();
  const originalDirection = swipe.startOffset > 0
    ? swipe.actions.positive
    : swipe.startOffset < 0
      ? swipe.actions.negative
      : null;
  if (originalDirection) openTaskCardDrawer(swipe.card, originalDirection);
  else closeTaskCardDrawer(swipe.card, { immediate: true });
}

function handleTaskCardSwipeLostPointerCapture(event: PointerEvent): void {
  const swipe = activeSwipe;
  if (!swipe || event.pointerId !== swipe.pointerId) return;
  resetInterruptedTaskCardSwipe(swipe);
}

function handleTaskCardSwipeWindowBlur(): void {
  const swipe = activeSwipe;
  if (swipe) resetInterruptedTaskCardSwipe(swipe);
  closeOpenTaskCardDrawer({ immediate: true });
}

function handleTaskCardSwipeVisibilityChange(): void {
  if (document.visibilityState !== "hidden") return;
  handleTaskCardSwipeWindowBlur();
}

function handleTaskCardSwipeClick(event: MouseEvent): void {
  const target = eventTargetElement(event);
  const button = target?.closest<HTMLButtonElement>("[data-task-card-action]");
  if (!button) return;
  const root = taskCardSwipeRoot();
  const card = button.closest<HTMLElement>('.task-card[data-task-swipe-enabled="true"]');
  if (!root || !card || !root.contains(card) || button.disabled) return;
  const action = taskCardSwipeAction(button.dataset.taskCardAction);
  if (!action) return;
  event.preventDefault();
  event.stopPropagation();
  void performTaskCardAction(card, action, button);
}

function handleTaskCardSwipeKeydown(event: KeyboardEvent): void {
  const target = eventTargetElement(event);
  const card = target?.closest<HTMLElement>('.task-card[data-task-swipe-enabled="true"]');
  if (!card) return;
  if (event.key === "Escape" && card.classList.contains("task-card-swipe-open")) {
    event.preventDefault();
    event.stopPropagation();
    closeTaskCardDrawer(card, { focusCard: true });
    return;
  }
  if (!event.shiftKey) return;
  if (event.key === "ArrowRight") {
    const action = taskCardSwipeActions(card).positive;
    if (!action) return;
    event.preventDefault();
    event.stopPropagation();
    openTaskCardDrawer(card, action, true);
  } else if (event.key === "ArrowLeft") {
    const action = taskCardSwipeActions(card).negative;
    if (!action) return;
    event.preventDefault();
    event.stopPropagation();
    openTaskCardDrawer(card, action, true);
  }
}

function handleTaskCardSwipeDocumentPointerDown(event: PointerEvent): void {
  if (!openTaskCard) return;
  const target = eventTargetElement(event);
  if (target && openTaskCard.contains(target)) return;
  closeOpenTaskCardDrawer();
}

function handleTaskCardSwipeDocumentKeydown(event: KeyboardEvent): void {
  if (event.key !== "Escape" || !openTaskCard) return;
  event.preventDefault();
  closeOpenTaskCardDrawer({ focusCard: true });
}

function handleTaskCardSwipeScroll(): void {
  closeOpenTaskCardDrawer({ immediate: prefersReducedMotion() });
}

export function initTaskCardSwipeFeature(): void {
  if (taskCardSwipeInitialized) return;
  taskCardSwipeInitialized = true;
  const root = taskCardSwipeRoot();
  if (!root) return;
  root.addEventListener("pointerdown", handleTaskCardSwipePointerDown);
  root.addEventListener("click", handleTaskCardSwipeClick);
  root.addEventListener("keydown", handleTaskCardSwipeKeydown);
  document.addEventListener("pointerdown", handleTaskCardSwipeDocumentPointerDown, true);
  document.addEventListener("keydown", handleTaskCardSwipeDocumentKeydown);
  document.addEventListener("scroll", handleTaskCardSwipeScroll, true);
  window.addEventListener("blur", handleTaskCardSwipeWindowBlur);
  document.addEventListener("visibilitychange", handleTaskCardSwipeVisibilityChange);
  Object.assign(getLegacyBridge().methods, {
    revealTaskCardAction,
    closeOpenTaskCardDrawer,
    cancelActiveTaskCardSwipeTracking,
  });
}

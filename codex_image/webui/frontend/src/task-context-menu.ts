import { getLegacyBridge } from "./state";
import { LOCALE_CHANGE_EVENT, translate } from "./i18n";
import { moveQueueTask } from "./queue";

const bridge = getLegacyBridge();
const state = bridge.state;
const els = bridge.els;

let taskContextMenuInitialized = false;
let taskContextMenuEventsBound = false;
let taskContextMenuEl: HTMLElement | null = null;
let taskListMutationObserver: MutationObserver | null = null;

function legacyMethod(name: string, ...args: any[]): any {
  const method = getLegacyBridge().methods[name];
  if (typeof method !== "function") {
    throw new Error("Legacy bridge method " + name + " is not available");
  }
  return method(...args);
}

function escapeHtml(...args: any[]) { return legacyMethod("escapeHtml", ...args); }
function setStatus(...args: any[]) { return legacyMethod("setStatus", ...args); }
function closePromptPopover(...args: any[]) { return legacyMethod("closePromptPopover", ...args); }
function selectTask(...args: any[]) { return legacyMethod("selectTask", ...args); }
function revealTaskCardAction(...args: any[]) { return legacyMethod("revealTaskCardAction", ...args); }

function bindTaskContextMenuEvents() {
  if (taskContextMenuEventsBound) return;
  taskContextMenuEventsBound = true;

  taskContextMenuRoots().forEach((root) => {
    root.addEventListener("click", event => {
      const trigger = (event.target as Element).closest<HTMLElement>("[data-task-context-trigger]");
      const card = trigger?.closest<HTMLElement>(".task-card[data-task-id]");
      if (!trigger || !card) return;
      event.preventDefault(); event.stopPropagation();
      const rect = trigger.getBoundingClientRect();
      openTaskContextMenu(card, rect.left, rect.bottom);
    }, true);
    root.addEventListener("contextmenu", handleTaskListContextMenu);
    root.addEventListener("keydown", handleTaskListContextMenuKeydown);
  });
  document.addEventListener("click", handleTaskContextDocumentClick, true);
  document.addEventListener("keydown", handleTaskContextDocumentKeydown);
  document.addEventListener("scroll", closeTaskContextMenu, true);
  window.addEventListener("resize", closeTaskContextMenu);
  if ("MutationObserver" in window) {
    taskListMutationObserver = new MutationObserver(closeTaskContextMenu);
    taskContextMenuRoots().forEach((root) => taskListMutationObserver?.observe(root, { childList: true }));
  }
}

function taskContextMenuRoots(): HTMLElement[] {
  return [els.taskActiveList, els.taskList].filter((root): root is HTMLElement => root instanceof HTMLElement);
}

function taskContextMenuContains(card: HTMLElement): boolean {
  return taskContextMenuRoots().some((root) => root.contains(card));
}

function handleTaskListContextMenu(event: MouseEvent) {
  const target = eventTargetElement(event);
  const card = target?.closest(".task-card[data-task-id]") as HTMLElement | null;
  if (!card || !taskContextMenuContains(card)) return;
  event.preventDefault();
  event.stopPropagation();
  if (card.classList.contains("queue-reorder-armed") || card.classList.contains("queue-dragging")) return;
  openTaskContextMenu(card, event.clientX, event.clientY);
}

function handleTaskListContextMenuKeydown(event: KeyboardEvent) {
  if (event.key !== "ContextMenu" && !(event.shiftKey && event.key === "F10")) return;
  const target = eventTargetElement(event);
  const card = target?.closest(".task-card[data-task-id]") as HTMLElement | null;
  if (!card || !taskContextMenuContains(card)) return;
  event.preventDefault();
  const rect = card.getBoundingClientRect();
  openTaskContextMenu(card, rect.left + 18, rect.top + 18);
}

function handleTaskContextDocumentClick(event: MouseEvent) {
  if (!taskContextMenuEl || taskContextMenuEl.classList.contains("hidden")) return;
  const target = eventTargetElement(event);
  if (target && taskContextMenuEl.contains(target)) return;
  closeTaskContextMenu();
}

function handleTaskContextDocumentKeydown(event: KeyboardEvent) {
  if (event.key === "Escape") closeTaskContextMenu();
}

function openTaskContextMenu(card: HTMLElement, clientX: number, clientY: number) {
  const taskId = String(card.dataset.taskId || "");
  const task = taskById(taskId);
  if (!task) return;
  closePromptPopover();
  const menu = ensureTaskContextMenu();
  menu.dataset.taskContextTaskId = taskId;
  menu.innerHTML = taskContextMenuHtml(task);
  menu.classList.remove("hidden");
  bindTaskContextMenuActionEvents(menu);
  positionTaskContextMenu(menu, clientX, clientY);
  const firstButton = menu.querySelector<HTMLButtonElement>(".task-context-menu-button:not(:disabled)");
  firstButton?.focus({ preventScroll: true });
}

function closeTaskContextMenu() {
  if (!taskContextMenuEl) return;
  taskContextMenuEl.classList.add("hidden");
  taskContextMenuEl.removeAttribute("data-task-context-task-id");
}

function ensureTaskContextMenu() {
  if (taskContextMenuEl) return taskContextMenuEl;
  taskContextMenuEl = document.createElement("div");
  taskContextMenuEl.className = "task-context-menu hidden";
  taskContextMenuEl.setAttribute("role", "menu");
  taskContextMenuEl.setAttribute("aria-label", translate("mobile.taskActions"));
  document.body.appendChild(taskContextMenuEl);
  return taskContextMenuEl;
}

function rerenderTaskContextMenuForLocale() {
  if (!taskContextMenuEl) return;
  taskContextMenuEl.setAttribute("aria-label", translate("mobile.taskActions"));
  if (taskContextMenuEl.classList.contains("hidden")) return;
  const taskId = String(taskContextMenuEl.dataset.taskContextTaskId || "");
  const task = taskById(taskId);
  if (!task) return;
  taskContextMenuEl.innerHTML = taskContextMenuHtml(task);
  bindTaskContextMenuActionEvents(taskContextMenuEl);
}

function taskContextMenuHtml(task: any) {
  const hasOutput = taskHasOutput(task);
  const queueSection = taskContextQueueSection(task);
  const waitingIndex = queueSection === "waiting"
    ? (state.queue.waiting || []).findIndex((item: any) => String(item?.task_id || "") === String(task?.task_id || ""))
    : -1;
  const waitingCount = (state.queue.waiting || []).length;
  const lifecycleActions = queueSection === "running"
    ? taskContextButton("stop", translate("action.stop"), task.status === "cancelling", true)
    : queueSection === "waiting"
      ? [
          taskContextButton("move-up", translate("queue.moveUpTitle"), waitingIndex <= 0),
          taskContextButton("move-down", translate("queue.moveDownTitle"), waitingIndex < 0 || waitingIndex >= waitingCount - 1),
          taskContextButton("promote", translate("queue.promote")),
          taskContextButton("cancel", translate("action.cancel"), false, true),
        ].join("")
      : [
          taskContextButton("archive", translate("taskContext.archive")),
          taskContextButton("delete", translate("taskContext.delete"), false, true),
        ].join("");
  return `
    <div class="task-context-menu-section">
      ${taskContextButton("view", translate("taskContext.view"))}
    </div>
    <div class="task-context-menu-section">
      ${taskContextButton("copy-id", translate("taskContext.copyId"))}
      ${taskContextButton("copy-prompt", translate("taskContext.copyPrompt"), !taskCanCopyPrompt(task))}
      ${taskContextButton("reveal-output", translate("taskContext.revealOutput"), !hasOutput)}
    </div>
    <div class="task-context-menu-section">
      ${lifecycleActions}
    </div>
  `;
}

function taskContextQueueSection(task: any): "running" | "waiting" | null {
  const taskId = String(task?.task_id || "");
  if ((state.queue.running || []).some((item: any) => String(item?.task_id || "") === taskId)) {
    return "running";
  }
  if ((state.queue.waiting || []).some((item: any) => String(item?.task_id || "") === taskId)) {
    return "waiting";
  }
  if (["running", "cancelling"].includes(String(task?.status || ""))) return "running";
  if (String(task?.status || "") === "queued") return "waiting";
  return null;
}

function taskContextButton(action: string, label: string, disabled = false, danger = false) {
  const disabledAttr = disabled ? " disabled" : "";
  const dangerClass = danger ? " danger" : "";
  return `<button class="task-context-menu-button${dangerClass}" type="button" role="menuitem" data-task-context-action="${action}"${disabledAttr}>${escapeHtml(label)}</button>`;
}

function bindTaskContextMenuActionEvents(menu: HTMLElement) {
  menu.querySelectorAll<HTMLButtonElement>("[data-task-context-action]").forEach((button) => {
    button.addEventListener("click", (event) => {
      event.preventDefault();
      event.stopPropagation();
      if (button.disabled) return;
      void handleTaskContextMenuAction(button);
    });
  });
}

async function handleTaskContextMenuAction(button: HTMLButtonElement) {
  const action = String(button.dataset.taskContextAction || "");
  const taskId = String(taskContextMenuEl?.dataset.taskContextTaskId || "");
  const task = taskById(taskId);
  if (!task) {
    closeTaskContextMenu();
    return;
  }

  if (["archive", "delete", "stop", "promote", "cancel"].includes(action)) {
    closeTaskContextMenu();
    revealTaskCardAction(taskId, action, true);
    return;
  }

  if (action === "move-up" || action === "move-down") {
    closeTaskContextMenu();
    moveQueueTask(taskId, action === "move-up" ? "up" : "down");
    return;
  }

  closeTaskContextMenu();
  try {
    if (action === "view") {
      await selectTask(taskId);
    } else if (action === "copy-id") {
      await copyText(taskId);
      setStatus(translate("taskContext.idCopied"), "ok");
    } else if (action === "copy-prompt") {
      const detailedTask = await ensureTaskContextTaskDetail(taskId, task);
      const prompt = taskPromptText(detailedTask);
      if (!prompt) throw new Error(translate("taskContext.noPrompt"));
      await copyText(prompt);
      setStatus(translate("taskContext.promptCopied"), "ok");
    } else if (action === "reveal-output") {
      await revealTaskOutputDirectory(taskId);
    }
  } catch (error) {
    setStatus(errorMessage(error, translate("taskContext.actionFailed")), "error");
  }
}

async function revealTaskOutputDirectory(taskId: string) {
  const response = await fetch(`/api/tasks/${encodeURIComponent(taskId)}/reveal-output`, {
    method: "POST",
    headers: { "X-Requested-With": "codex-image-webui" },
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.detail || translate("taskContext.revealFailed"));
  setStatus(translate("taskContext.revealOpened"), "ok");
}

async function copyText(text: string) {
  if (navigator.clipboard?.writeText) {
    await navigator.clipboard.writeText(text);
    return;
  }
  const input = document.createElement("textarea");
  input.value = text;
  input.setAttribute("readonly", "");
  input.style.position = "fixed";
  input.style.left = "-9999px";
  document.body.appendChild(input);
  input.select();
  document.execCommand("copy");
  input.remove();
}

function taskById(taskId: string) {
  return state.tasks.find((item: any) => String(item.task_id) === String(taskId));
}

function taskCanCopyPrompt(task: any) {
  return Boolean(task?.summary_only || taskPromptText(task));
}

function taskPromptText(task: any) {
  return String(task?.prompt || task?.prompt_for_model || "").trim();
}

async function ensureTaskContextTaskDetail(taskId: string, task: any) {
  if (!task?.summary_only) return task;
  const response = await fetch(`/api/tasks/${encodeURIComponent(taskId)}`);
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.detail || translate("notifications.taskMissing"));
  const fullTask = data.task;
  return replaceTaskInState(taskId, fullTask);
}

function replaceTaskInState(taskId: string, task: any) {
  if (!task?.task_id) return task;
  const index = state.tasks.findIndex((item: any) => String(item.task_id) === String(taskId));
  if (index >= 0) {
    state.tasks.splice(index, 1, task);
  } else {
    state.tasks.unshift(task);
  }
  return task;
}

function taskHasOutput(task: any) {
  if (task?.output_url) return true;
  if (Array.isArray(task?.output_urls) && task.output_urls.length) return true;
  if (Array.isArray(task?.output_files) && task.output_files.length) return true;
  if (!Array.isArray(task?.outputs)) return false;
  return task.outputs.some((record: any) => record?.status === "completed" && (record.url || record.file));
}

function positionTaskContextMenu(menu: HTMLElement, clientX: number, clientY: number) {
  const margin = 8;
  menu.style.left = "0px";
  menu.style.top = "0px";
  const width = menu.offsetWidth;
  const height = menu.offsetHeight;
  const left = clamp(clientX, margin, Math.max(margin, window.innerWidth - width - margin));
  const top = clamp(clientY, margin, Math.max(margin, window.innerHeight - height - margin));
  menu.style.left = `${left}px`;
  menu.style.top = `${top}px`;
}

function clamp(value: number, min: number, max: number) {
  return Math.min(Math.max(value, min), max);
}

function eventTargetElement(event: Event) {
  return event.target instanceof Element ? event.target : null;
}

function errorMessage(error: unknown, fallback: string) {
  return error instanceof Error && error.message ? error.message : fallback;
}

export function initTaskContextMenuFeature() {
  if (taskContextMenuInitialized) return;
  taskContextMenuInitialized = true;
  bindTaskContextMenuEvents();
  document.addEventListener(LOCALE_CHANGE_EVENT, rerenderTaskContextMenuForLocale);
  Object.assign(getLegacyBridge().methods, {
    openTaskContextMenu,
    closeTaskContextMenu,
  });
}

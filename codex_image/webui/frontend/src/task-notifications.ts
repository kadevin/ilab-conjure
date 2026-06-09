import { getLegacyBridge } from "./state";
import { formatTranslation, LOCALE_CHANGE_EVENT, translate } from "./i18n";
import type { TaskNotification, TaskNotificationSettings, TaskStatus, WebUITask } from "./types";

const TASK_NOTIFICATION_SETTINGS_KEY = "codex-image-task-notification-settings";
const TASK_NOTIFICATION_SEEN_KEY = "codex-image-task-notification-seen";
const MAX_TASK_NOTIFICATIONS = 30;
const MAX_SEEN_TASK_NOTIFICATION_KEYS = 400;
const TASK_NOTIFICATION_TOAST_MS = 5200;

type TerminalTaskStatus = Extract<TaskStatus, "completed" | "failed" | "partial_failed">;

let taskNotificationsFeatureInitialized = false;

export function initTaskNotificationsFeature(): void {
  if (taskNotificationsFeatureInitialized) return;
  taskNotificationsFeatureInitialized = true;
  restoreTaskNotificationSettings();
  restoreTaskNotificationSeenKeys();
  bindTaskNotificationEvents();
  document.addEventListener(LOCALE_CHANGE_EVENT, renderTaskNotifications);
  renderTaskNotifications();
  Object.assign(getLegacyBridge().methods, {
    notifyTaskUpdate,
    openTaskNotificationCenter,
    renderTaskNotifications,
    requestSystemNotificationPermission,
  });
}

function notifyTaskUpdate(previousTask: WebUITask | null | undefined, nextTask: WebUITask | null | undefined): void {
  const status = terminalTaskStatus(nextTask?.status);
  if (!nextTask || !status || !shouldNotifyTerminalTask(previousTask, nextTask)) return;
  const notification = buildTaskNotification(nextTask, status);
  rememberTaskNotification(nextTask, status);
  if (getLegacyBridge().state.taskNotificationSettings.inApp) {
    addTaskNotification(notification);
    showTaskNotificationToast(notification);
  }
  sendSystemTaskNotification(notification);
}

function shouldNotifyTerminalTask(previousTask: WebUITask | null | undefined, nextTask: WebUITask | null | undefined): boolean {
  const status = terminalTaskStatus(nextTask?.status);
  if (!previousTask || !nextTask?.task_id || !status) return false;
  if (terminalTaskStatus(previousTask.status)) return false;
  return !getLegacyBridge().state.taskNotificationSeenKeys.has(taskNotificationSeenKey(nextTask, status));
}

function openTaskNotificationCenter(): void {
  const state = getLegacyBridge().state;
  state.taskNotificationCenterOpen = true;
  state.taskNotifications = state.taskNotifications.map((notification: TaskNotification) => ({
    ...notification,
    unread: false,
  }));
  renderTaskNotifications();
}

function closeTaskNotificationCenter(): void {
  const state = getLegacyBridge().state;
  if (!state.taskNotificationCenterOpen) return;
  state.taskNotificationCenterOpen = false;
  renderTaskNotifications();
}

function toggleTaskNotificationCenter(): void {
  if (getLegacyBridge().state.taskNotificationCenterOpen) {
    closeTaskNotificationCenter();
    return;
  }
  openTaskNotificationCenter();
}

function renderTaskNotifications(): void {
  const bridge = getLegacyBridge();
  const state = bridge.state;
  const els = bridge.els;
  const unreadCount = state.taskNotifications.filter((notification: TaskNotification) => notification.unread).length;
  state.taskNotificationUnreadCount = unreadCount;
  const unreadLabel = unreadCount > 0
    ? formatTranslation("notifications.unread", { count: unreadCount })
    : translate("notifications.title");

  if (els.taskNotificationBadge) {
    els.taskNotificationBadge.textContent = "";
    els.taskNotificationBadge.setAttribute("aria-hidden", "true");
    els.taskNotificationBadge.classList.toggle("hidden", unreadCount === 0);
  }
  if (els.taskNotificationButton) {
    els.taskNotificationButton.classList.toggle("has-unread", unreadCount > 0);
    els.taskNotificationButton.setAttribute("aria-label", unreadLabel);
    els.taskNotificationButton.title = unreadLabel;
    els.taskNotificationButton.setAttribute("aria-expanded", state.taskNotificationCenterOpen ? "true" : "false");
  }
  if (els.taskNotificationUnreadSummary) {
    els.taskNotificationUnreadSummary.textContent = formatTranslation("notifications.unreadSummary", { count: unreadCount });
    els.taskNotificationUnreadSummary.classList.toggle("hidden", unreadCount === 0);
  }
  if (els.taskNotificationCenter) {
    els.taskNotificationCenter.classList.toggle("hidden", !state.taskNotificationCenterOpen);
    els.taskNotificationCenter.setAttribute("aria-hidden", state.taskNotificationCenterOpen ? "false" : "true");
  }
  if (!els.taskNotificationList) return;
  if (!state.taskNotifications.length) {
    els.taskNotificationList.innerHTML = `<div class="task-notification-empty">${translate("notifications.empty")}</div>`;
    return;
  }
  els.taskNotificationList.innerHTML = state.taskNotifications
    .map((notification: TaskNotification) => taskNotificationItemHtml(notification))
    .join("");
}

async function requestSystemNotificationPermission(): Promise<boolean> {
  if (typeof Notification === "undefined") {
    setStatus(translate("notifications.systemUnsupported"), "error");
    return false;
  }
  if (Notification.permission === "granted") return true;
  if (Notification.permission === "denied") {
    setStatus(translate("notifications.systemBlocked"), "error");
    return false;
  }
  const permission = await Notification.requestPermission();
  if (permission !== "granted") {
    setStatus(translate("notifications.systemDenied"), "error");
    return false;
  }
  setStatus(translate("notifications.systemEnabled"), "ok");
  return true;
}

function bindTaskNotificationEvents(): void {
  const els = getLegacyBridge().els;
  els.taskNotificationButton?.addEventListener("click", (event: MouseEvent) => {
    event.stopPropagation();
    toggleTaskNotificationCenter();
  });
  els.taskNotificationClearButton?.addEventListener("click", (event: MouseEvent) => {
    event.stopPropagation();
    clearTaskNotifications();
  });
  els.taskNotificationList?.addEventListener("click", (event: MouseEvent) => {
    const item = eventTargetElement(event)?.closest("[data-task-notification-id]");
    if (!(item instanceof HTMLElement)) return;
    const notification = notificationById(item.dataset.taskNotificationId);
    if (notification) void openNotificationTask(notification);
  });
  els.taskNotificationInApp?.addEventListener("change", handleTaskNotificationInAppChange);
  els.taskNotificationSystem?.addEventListener("change", (event: Event) => {
    void handleTaskNotificationSystemChange(event);
  });
  document.addEventListener("click", handleTaskNotificationDocumentClick);
  document.addEventListener("keydown", handleTaskNotificationKeydown);
}

function handleTaskNotificationInAppChange(event: Event): void {
  const input = event.currentTarget;
  if (!(input instanceof HTMLInputElement)) return;
  const state = getLegacyBridge().state;
  state.taskNotificationSettings = {
    ...state.taskNotificationSettings,
    inApp: input.checked,
  };
  persistTaskNotificationSettings();
}

async function handleTaskNotificationSystemChange(event: Event): Promise<void> {
  const input = event.currentTarget;
  if (!(input instanceof HTMLInputElement)) return;
  const state = getLegacyBridge().state;
  if (!input.checked) {
    state.taskNotificationSettings = { ...state.taskNotificationSettings, system: false };
    persistTaskNotificationSettings();
    return;
  }
  const granted = await requestSystemNotificationPermission();
  state.taskNotificationSettings = { ...state.taskNotificationSettings, system: granted };
  input.checked = granted;
  persistTaskNotificationSettings();
}

function handleTaskNotificationDocumentClick(event: MouseEvent): void {
  const target = event.target;
  const els = getLegacyBridge().els;
  if (!(target instanceof Node)) return;
  if (els.taskNotificationCenter?.contains(target) || els.taskNotificationButton?.contains(target)) return;
  closeTaskNotificationCenter();
}

function handleTaskNotificationKeydown(event: KeyboardEvent): void {
  if (event.key === "Escape") closeTaskNotificationCenter();
}

function addTaskNotification(notification: TaskNotification): void {
  const state = getLegacyBridge().state;
  state.taskNotifications = [notification, ...state.taskNotifications].slice(0, MAX_TASK_NOTIFICATIONS);
  renderTaskNotifications();
}

function clearTaskNotifications(): void {
  const state = getLegacyBridge().state;
  state.taskNotifications = [];
  renderTaskNotifications();
}

function showTaskNotificationToast(notification: TaskNotification): void {
  const bridge = getLegacyBridge();
  const region = bridge.els.taskNotificationToastRegion;
  if (!region) return;
  const toast = document.createElement("button");
  toast.type = "button";
  toast.className = "task-notification-item task-notification-toast";
  toast.dataset.taskNotificationId = notification.id;
  toast.innerHTML = taskNotificationInnerHtml(notification);
  toast.addEventListener("click", () => {
    toast.remove();
    void openNotificationTask(notification);
  });
  region.prepend(toast);
  const timerId = window.setTimeout(() => {
    toast.remove();
    bridge.state.taskNotificationToastTimerIds = bridge.state.taskNotificationToastTimerIds.filter((id: number) => id !== timerId);
  }, TASK_NOTIFICATION_TOAST_MS);
  bridge.state.taskNotificationToastTimerIds.push(timerId);
}

function sendSystemTaskNotification(notification: TaskNotification): void {
  const settings = getLegacyBridge().state.taskNotificationSettings;
  if (!settings.system || typeof Notification === "undefined" || Notification.permission !== "granted") return;
  const options: NotificationOptions = { body: taskNotificationDisplayMessage(notification) };
  if (notification.thumbnail_url) options.icon = notification.thumbnail_url;
  const systemNotification = new Notification(taskNotificationDisplayTitle(notification), options);
  systemNotification.onclick = () => {
    window.focus();
    void openNotificationTask(notification);
    systemNotification.close();
  };
}

async function openNotificationTask(notification: TaskNotification): Promise<void> {
  const bridge = getLegacyBridge();
  const task = bridge.state.tasks.find((item: WebUITask) => String(item.task_id) === String(notification.task_id));
  markTaskNotificationRead(notification.id);
  closeTaskNotificationCenter();
  if (!task) {
    setStatus(translate("notifications.taskMissing"), "error");
    return;
  }
  window.focus();
  try {
    const selectTask = bridge.methods.selectTask;
    if (typeof selectTask !== "function") throw new Error("selectTask is unavailable");
    await selectTask(task.task_id);
  } catch {
    setStatus(translate("notifications.taskMissing"), "error");
  }
}

function markTaskNotificationRead(notificationId: string): void {
  const state = getLegacyBridge().state;
  state.taskNotifications = state.taskNotifications.map((notification: TaskNotification) => (
    notification.id === notificationId ? { ...notification, unread: false } : notification
  ));
  renderTaskNotifications();
}

function notificationById(notificationId: string | undefined): TaskNotification | null {
  if (!notificationId) return null;
  return getLegacyBridge().state.taskNotifications.find((notification: TaskNotification) => (
    notification.id === notificationId
  )) || null;
}

function buildTaskNotification(task: WebUITask, status: TerminalTaskStatus): TaskNotification {
  const thumbnailUrl = firstTaskThumbnailUrl(task);
  const successCount = completedOutputCount(task);
  const failedCount = positiveNumber(task.failed_count);
  const prompt = promptSnippet(task.prompt || task.prompt_for_model || "");
  const errorMessage = String(task.last_error || task.error || "");
  return {
    id: taskNotificationSeenKey(task, status),
    task_id: task.task_id,
    status,
    title: taskNotificationTitle(status),
    message: taskNotificationMessageFromParts(status, {
      successCount,
      failedCount,
      prompt,
      errorMessage,
    }),
    success_count: successCount,
    failed_count: failedCount,
    prompt_snippet: prompt,
    error_message: errorMessage,
    created_at: new Date().toISOString(),
    ...(thumbnailUrl ? { thumbnail_url: thumbnailUrl } : {}),
    unread: true,
  };
}

function taskNotificationTitle(status: TerminalTaskStatus): string {
  if (status === "failed") return translate("notifications.taskFailed");
  if (status === "partial_failed") return translate("notifications.taskPartial");
  return translate("notifications.taskCompleted");
}

function taskNotificationMessage(task: WebUITask, status: TerminalTaskStatus): string {
  return taskNotificationMessageFromParts(status, {
    successCount: completedOutputCount(task),
    failedCount: positiveNumber(task.failed_count),
    prompt: promptSnippet(task.prompt || task.prompt_for_model || ""),
    errorMessage: String(task.last_error || task.error || ""),
  });
}

function taskNotificationMessageFromParts(
  status: TerminalTaskStatus,
  parts: { successCount?: number; failedCount?: number; prompt?: string; errorMessage?: string },
): string {
  if (status === "failed") return String(parts.errorMessage || translate("notifications.generationFailed"));
  const countText = parts.successCount
    ? formatTranslation("notifications.successCount", { count: parts.successCount })
    : translate("notifications.resultAvailable");
  const failureText = status === "partial_failed" && parts.failedCount
    ? formatTranslation("notifications.failedCount", { count: parts.failedCount })
    : "";
  return [countText, failureText, parts.prompt || ""].filter(Boolean).join(" · ");
}

function taskNotificationDisplayTitle(notification: TaskNotification): string {
  return taskNotificationTitle(notification.status);
}

function taskNotificationDisplayMessage(notification: TaskNotification): string {
  if (
    notification.success_count !== undefined ||
    notification.failed_count !== undefined ||
    notification.prompt_snippet !== undefined ||
    notification.error_message !== undefined
  ) {
    return taskNotificationMessageFromParts(notification.status, {
      successCount: positiveNumber(notification.success_count),
      failedCount: positiveNumber(notification.failed_count),
      prompt: notification.prompt_snippet || "",
      errorMessage: notification.error_message || notification.message,
    });
  }
  return notification.message;
}

function firstTaskThumbnailUrl(task: WebUITask): string | undefined {
  const bridge = getLegacyBridge();
  const urls = bridge.methods.taskThumbnailUrls?.(task);
  if (Array.isArray(urls) && urls[0]) return String(urls[0]);
  if (Array.isArray(task.thumbnail_urls) && task.thumbnail_urls[0]) return String(task.thumbnail_urls[0]);
  const output = Array.isArray(task.outputs) ? task.outputs.find((record) => record?.status === "completed") : null;
  if (output?.thumbnail_url) return String(output.thumbnail_url);
  if (output?.thumbnail_file) return outputFileUrl(output.thumbnail_file);
  if (output?.url || output?.file) {
    const index = positiveNumber(output.index) || 1;
    return `/api/tasks/${encodeURIComponent(task.task_id)}/outputs/${index}/thumbnail`;
  }
  if (Array.isArray(task.output_urls) && task.output_urls.some(Boolean)) {
    return `/api/tasks/${encodeURIComponent(task.task_id)}/outputs/1/thumbnail`;
  }
  return undefined;
}

function taskNotificationItemHtml(notification: TaskNotification): string {
  const unreadClass = notification.unread ? " unread" : "";
  return `<button class="task-notification-item${unreadClass}" type="button" data-task-notification-id="${escapeHtml(notification.id)}">
    ${taskNotificationInnerHtml(notification)}
  </button>`;
}

function taskNotificationInnerHtml(notification: TaskNotification): string {
  const thumbnail = notification.thumbnail_url
    ? `<img class="task-notification-thumb" src="${escapeHtml(notification.thumbnail_url)}" alt="">`
    : `<span class="task-notification-thumb task-notification-thumb-placeholder" aria-hidden="true">${escapeHtml(statusGlyph(notification.status))}</span>`;
  return `${thumbnail}
    <span class="task-notification-body">
      <span class="task-notification-title">${escapeHtml(taskNotificationDisplayTitle(notification))}</span>
      <span class="task-notification-message">${escapeHtml(taskNotificationDisplayMessage(notification))}</span>
      <span class="task-notification-time">${escapeHtml(formatNotificationTime(notification.created_at))}</span>
    </span>`;
}

function statusGlyph(status: TerminalTaskStatus): string {
  if (status === "failed") return "!";
  if (status === "partial_failed") return "~";
  return "✓";
}

function formatNotificationTime(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

function terminalTaskStatus(status: unknown): TerminalTaskStatus | null {
  if (status === "completed" || status === "failed" || status === "partial_failed") return status;
  return null;
}

function taskNotificationSeenKey(task: WebUITask, status: TerminalTaskStatus): string {
  const revision = task.completed_at || task.updated_at || task.last_error || task.error || "";
  return `${task.task_id}:${status}:${revision}`;
}

function rememberTaskNotification(task: WebUITask, status: TerminalTaskStatus): void {
  const state = getLegacyBridge().state;
  state.taskNotificationSeenKeys.add(taskNotificationSeenKey(task, status));
  while (state.taskNotificationSeenKeys.size > MAX_SEEN_TASK_NOTIFICATION_KEYS) {
    const firstKey = state.taskNotificationSeenKeys.values().next().value;
    if (typeof firstKey !== "string") break;
    state.taskNotificationSeenKeys.delete(firstKey);
  }
  persistTaskNotificationSeenKeys();
}

function restoreTaskNotificationSettings(): void {
  const state = getLegacyBridge().state;
  state.taskNotificationSettings = defaultTaskNotificationSettings();
  try {
    const stored = JSON.parse(localStorage.getItem(TASK_NOTIFICATION_SETTINGS_KEY) || "{}") as Partial<TaskNotificationSettings>;
    state.taskNotificationSettings = {
      inApp: stored.inApp !== false,
      system: stored.system === true && typeof Notification !== "undefined" && Notification.permission === "granted",
    };
  } catch {
    state.taskNotificationSettings = defaultTaskNotificationSettings();
  }
  persistTaskNotificationSettings();
  syncTaskNotificationSettingsInputs();
}

function defaultTaskNotificationSettings(): TaskNotificationSettings {
  return { inApp: true, system: false };
}

function persistTaskNotificationSettings(): void {
  try {
    localStorage.setItem(TASK_NOTIFICATION_SETTINGS_KEY, JSON.stringify(getLegacyBridge().state.taskNotificationSettings));
  } catch {
    // Local storage can be unavailable in private browser contexts.
  }
  syncTaskNotificationSettingsInputs();
}

function syncTaskNotificationSettingsInputs(): void {
  const bridge = getLegacyBridge();
  const settings = bridge.state.taskNotificationSettings;
  if (bridge.els.taskNotificationInApp instanceof HTMLInputElement) {
    bridge.els.taskNotificationInApp.checked = settings.inApp;
  }
  if (bridge.els.taskNotificationSystem instanceof HTMLInputElement) {
    bridge.els.taskNotificationSystem.checked = settings.system;
  }
}

function restoreTaskNotificationSeenKeys(): void {
  const state = getLegacyBridge().state;
  try {
    const stored = JSON.parse(localStorage.getItem(TASK_NOTIFICATION_SEEN_KEY) || "[]");
    state.taskNotificationSeenKeys = new Set(Array.isArray(stored) ? stored.filter((key) => typeof key === "string") : []);
  } catch {
    state.taskNotificationSeenKeys = new Set();
  }
}

function persistTaskNotificationSeenKeys(): void {
  try {
    const keys = Array.from(getLegacyBridge().state.taskNotificationSeenKeys).slice(-MAX_SEEN_TASK_NOTIFICATION_KEYS);
    localStorage.setItem(TASK_NOTIFICATION_SEEN_KEY, JSON.stringify(keys));
  } catch {
    // Notification delivery should not depend on storage availability.
  }
}

function outputFileUrl(filename: string): string {
  if (filename.startsWith("/outputs/")) return filename;
  const clean = filename.split("/").filter(Boolean).map(encodeURIComponent).join("/");
  return clean ? `/outputs/${clean}` : "";
}

function completedOutputCount(task: WebUITask): number {
  if (Array.isArray(task.outputs)) {
    return task.outputs.filter((record) => record?.status === "completed").length;
  }
  if (Array.isArray(task.output_urls)) return task.output_urls.filter(Boolean).length;
  return positiveNumber(task.generated_count);
}

function positiveNumber(value: unknown): number {
  const number = Number(value);
  return Number.isFinite(number) && number > 0 ? Math.floor(number) : 0;
}

function promptSnippet(value: unknown): string {
  const text = String(value || "").replace(/\s+/g, " ").trim();
  if (!text) return "";
  return text.length > 48 ? `${text.slice(0, 48)}...` : text;
}

function escapeHtml(value: unknown): string {
  return getLegacyBridge().methods.escapeHtml(value);
}

function setStatus(message: string, type?: string): void {
  getLegacyBridge().methods.setStatus(message, type);
}

function eventTargetElement(event: Event): Element | null {
  return event.target instanceof Element ? event.target : null;
}

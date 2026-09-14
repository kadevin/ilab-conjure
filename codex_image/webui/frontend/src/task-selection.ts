// @ts-nocheck
import { preserveComposerDraft, markComposerBaseline } from "./composer-draft";
import { formatTranslation, translate } from "./i18n";
import { getLegacyBridge } from "./state";
import { taskOutputSettingsView } from "./task-model-summary";

const bridge = getLegacyBridge();
const state = bridge.state;
const els = bridge.els;

let taskSelectionInitialized = false;
const HISTORY_TASK_REUSE_HANDOFF_KEY = "codex-image-history-task-reuse-handoff";
let selectedTaskDetailRequestSeq = 0;

function legacyMethod(name, ...args) {
  const method = getLegacyBridge().methods[name];
  if (typeof method !== "function") {
    throw new Error("Legacy method " + name + " is not initialized");
  }
  return method(...args);
}

function setStatus(message, type) { legacyMethod("setStatus", message, type); }
function closePromptPopover() { legacyMethod("closePromptPopover"); }
function markTaskViewed(taskId) { return legacyMethod("markTaskViewed", taskId); }
function applyTaskToForm(task, options = {}) { legacyMethod("applyTaskToForm", task, options); }
function updateTaskSelectionVisuals(taskId) { legacyMethod("updateTaskSelectionVisuals", taskId); }
function renderPreview(task) { legacyMethod("renderPreview", task); }
function taskFailureMessage(task) { return legacyMethod("taskFailureMessage", task); }
function taskRequestPreviewPayload(task) { return legacyMethod("taskRequestPreviewPayload", task); }
function revokeUploadPreviewUrls(sources) { legacyMethod("revokeUploadPreviewUrls", sources); }
function renderImageStrip() { legacyMethod("renderImageStrip"); }
function updateRequestPreview() { legacyMethod("updateRequestPreview"); }
function taskInputUrls(task) { return legacyMethod("taskInputUrls", task); }
function taskOutputUrls(task) { return legacyMethod("taskOutputUrls", task); }
function uploadSource(file) { return legacyMethod("uploadSource", file); }
function gallerySource(item) { return legacyMethod("gallerySource", item); }
function assetSource(item) { return legacyMethod("assetSource", item); }
function inspectTaskParameters(task) { legacyMethod("inspectTaskParameters", task); }
function clearTaskParameterInspection() { legacyMethod("clearTaskParameterInspection"); }
function renderTasks(options = {}) { legacyMethod("renderTasks", options); }
function revealHistoryTaskInSidebar(task) { return legacyMethod("revealHistoryTaskInSidebar", task); }

function applyTaskToFormWithOutputLock(task) {
  const outputSettingsLocked = Boolean(legacyMethod("isOutputSettingsLocked"));
  const outputView = taskOutputSettingsView(task, String(state.selectedModelId || ""), outputSettingsLocked);
  applyTaskToForm(task, {
    preserveOutputSettings: outputView !== "editor",
    preserveComposer: false,
  });
  if (outputView === "locked-summary") {
    clearTaskParameterInspection();
    legacyMethod("showTaskOutputSettings", task);
    return;
  }
  if (outputView === "parameter-inspector") {
    inspectTaskParameters(task);
    return;
  }
  clearTaskParameterInspection();
  legacyMethod("showLockedOutputSettings");
}

function selectedTaskInputRestoreCurrent(taskId, restoreSeq) {
  if (restoreSeq == null) return true;
  return state.taskInputRestoreSeq === restoreSeq && String(state.selectedTaskId) === String(taskId);
}

function applySelectedTaskRequestPreview(task) {
  const requestPayload = taskRequestPreviewPayload(task);
  if (requestPayload && els.requestJson) {
    els.requestJson.textContent = JSON.stringify(requestPayload, null, 2);
  }
}

function applyTaskInputRestoreSources(sources, taskId, restoreSeq) {
  if (!selectedTaskInputRestoreCurrent(taskId, restoreSeq)) {
    revokeUploadPreviewUrls(sources);
    return false;
  }
  revokeUploadPreviewUrls(state.images);
  state.images = sources.filter(Boolean);
  renderImageStrip();
  updateRequestPreview();
  return true;
}

function renderSelectedTask(task, taskId) {
  const wasBrowsingTasks = getLegacyBridge().methods.closeCompactTasks?.();
  applySelectedTaskRequestPreview(task);
  updateTaskSelectionVisuals(taskId);
  renderPreview(task);
  if (wasBrowsingTasks) getLegacyBridge().methods.showMobilePreview?.();
  if (task.status === "failed") {
    setStatus(taskFailureMessage(task) || translate("taskActions.failedFallback"), "error");
  } else if (!["running", "cancelling"].includes(String(task.status || ""))) {
    setStatus(formatTranslation("status.loadedTask", { taskId }), "ok");
  }
}

function isLegacyOutputInputUrl(url) {
  return typeof url === "string" && /^\/outputs\/[^/]+\/inputs\//.test(url);
}

function historyInputCandidateUrls(sourceUrl, fallbackUrl) {
  const urls = [];
  const addUrl = (url) => {
    if (url && !urls.includes(url)) urls.push(url);
  };
  if (isLegacyOutputInputUrl(sourceUrl)) {
    addUrl(fallbackUrl);
    addUrl(sourceUrl);
  } else {
    addUrl(sourceUrl);
    addUrl(fallbackUrl);
  }
  return urls;
}

async function loadFullTaskDetail(taskId) {
  const response = await fetch(`/api/tasks/${encodeURIComponent(taskId)}`);
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.detail || translate("notifications.taskMissing"));
  return data.task;
}

async function ensureSelectedTaskDetail(taskId = state.selectedTaskId) {
  const normalizedTaskId = String(taskId || "").trim();
  if (!normalizedTaskId) return null;
  const task = state.tasks.find((item) => String(item.task_id) === normalizedTaskId);
  if (!task) return null;
  if (!task.summary_only) return task;
  const detailSeq = ++selectedTaskDetailRequestSeq;
  const fullTask = await loadFullTaskDetail(normalizedTaskId);
  if (detailSeq !== selectedTaskDetailRequestSeq) return null;
  if (String(state.selectedTaskId) !== normalizedTaskId) return null;
  return replaceSelectedTaskDetail(normalizedTaskId, fullTask);
}

function replaceSelectedTaskDetail(taskId, task) {
  if (!task?.task_id) return task;
  const index = state.tasks.findIndex((item) => String(item.task_id) === String(taskId));
  if (index >= 0) {
    state.tasks.splice(index, 1, task);
  } else {
    state.tasks.unshift(task);
  }
  return task;
}

async function restoreTaskReferenceFiles(task, options = {}) {
  const taskId = options.taskId ?? task?.task_id;
  const restoreSeq = options.restoreSeq;
  const referenceFiles = Array.isArray(task?.reference_files) ? task.reference_files : [];
  if (!selectedTaskInputRestoreCurrent(taskId, restoreSeq)) return false;
  state.referenceFiles = [];
  legacyMethod("renderReferenceFiles");
  if (!referenceFiles.length) {
    updateRequestPreview();
    return true;
  }

  state.referenceFiles = referenceFiles.map((item) => ({
    kind: "asset",
    id: String(item?.id || item?.reference_file_id || ""),
    filename: String(item?.filename || ""),
    mime_type: String(item?.mime_type || "application/octet-stream"),
    size_bytes: Number(item?.size_bytes || 0),
    family: item?.family,
    missing: Boolean(item?.missing),
  })).filter((item) => item.id && ["pdf", "spreadsheet", "document", "text"].includes(item.family));
  legacyMethod("renderReferenceFiles");
  updateRequestPreview();
  return true;
}

async function fetchHistoryInputBlob(candidateUrls, sourceUrl) {
  for (const url of candidateUrls) {
    const response = await fetch(url);
    if (response.ok) {
      return response.blob();
    }
  }
  throw new Error(formatTranslation("status.historyInputLoadFailed", { url: candidateUrls[0] || sourceUrl }));
}

async function restoreTaskInputs(task, options = {}) {
  const taskId = options.taskId ?? task?.task_id;
  const restoreSeq = options.restoreSeq;
  if (Array.isArray(task.local_input_files)) {
    return applyTaskInputRestoreSources(task.local_input_files.slice(), taskId, restoreSeq);
  }

  if (Array.isArray(task.input_sources) && task.input_sources.length) {
    const restoredSources = [];
    const inputUrls = taskInputUrls(task);
    const inputNames = Array.isArray(task.input_files) ? task.input_files : [];
    let uploadInputIndex = 0;
    const uploadSources = task.input_sources.filter((source) => source?.kind === "upload" && source.image_url);
    if (uploadSources.length && selectedTaskInputRestoreCurrent(taskId, restoreSeq)) {
      setStatus(translate("status.loadingHistoryInputs"), "");
    }
    try {
      for (const [index, source] of task.input_sources.entries()) {
        if (!selectedTaskInputRestoreCurrent(taskId, restoreSeq)) {
          revokeUploadPreviewUrls(restoredSources);
          return false;
        }
        if (source.kind === "gallery") {
          restoredSources.push(gallerySource(source));
        } else if (source.kind === "asset") {
          restoredSources.push(assetSource(source));
        } else if (source.kind === "upload" && source.image_url) {
          const fallbackUrl = inputUrls[uploadInputIndex];
          const fallbackFileName = inputNames[uploadInputIndex];
          uploadInputIndex += 1;
          const candidateUrls = historyInputCandidateUrls(source.image_url, fallbackUrl);
          const blob = await fetchHistoryInputBlob(candidateUrls, source.image_url);
          const fallbackName = `history-input-${index + 1}`;
          restoredSources.push(uploadSource(new File([blob], source.filename || source.name || fallbackFileName || fallbackName, { type: blob.type || "application/octet-stream" })));
        } else {
          restoredSources.push(source);
        }
      }
    } catch (error) {
      revokeUploadPreviewUrls(restoredSources);
      throw error;
    }
    return applyTaskInputRestoreSources(restoredSources, taskId, restoreSeq);
  }

  const urls = taskInputUrls(task);
  const gallerySources = Array.isArray(task.gallery_refs)
    ? task.gallery_refs.map((ref) => gallerySource(ref))
    : [];
  if (!urls.length) {
    return applyTaskInputRestoreSources(gallerySources, taskId, restoreSeq);
  }

  if (selectedTaskInputRestoreCurrent(taskId, restoreSeq)) {
    setStatus(translate("status.loadingHistoryInputs"), "");
  }
  const inputNames = Array.isArray(task.input_files) ? task.input_files : [];
  const files = [];
  try {
    for (const [index, url] of urls.entries()) {
      if (!selectedTaskInputRestoreCurrent(taskId, restoreSeq)) {
        revokeUploadPreviewUrls(files);
        return false;
      }
      const response = await fetch(url);
      if (!response.ok) {
        throw new Error(formatTranslation("status.historyInputLoadFailed", { url }));
      }
      const blob = await response.blob();
      const fallbackName = `history-input-${index + 1}`;
      files.push(uploadSource(new File([blob], inputNames[index] || fallbackName, { type: blob.type || "application/octet-stream" })));
    }
  } catch (error) {
    revokeUploadPreviewUrls(files);
    throw error;
  }
  return applyTaskInputRestoreSources([...files, ...gallerySources], taskId, restoreSeq);
}

async function selectTask(taskId) {
  closePromptPopover();
  const leavingHistoryReveal = Boolean(
    state.historyTaskReveal
    && String(state.historyTaskReveal.taskId || "") !== String(taskId || ""),
  );
  if (leavingHistoryReveal) {
    state.historyTaskReveal = null;
    state.historyTaskRevealSeq += 1;
    state.tasksRenderKey = null;
  }
  state.selectedTaskId = taskId;
  if (leavingHistoryReveal) renderTasks({ preserveScroll: true });
  let task = state.tasks.find((item) => String(item.task_id) === String(taskId));
  if (!task) return;
  if (task.summary_only) {
    const detailSeq = ++state.taskInputRestoreSeq;
    updateTaskSelectionVisuals(taskId);
    setStatus(translate("status.loadingHistoryInputs"), "");
    try {
      const fullTask = await loadFullTaskDetail(taskId);
      if (!selectedTaskInputRestoreCurrent(taskId, detailSeq)) return;
      task = replaceSelectedTaskDetail(taskId, fullTask);
    } catch (error) {
      if (!selectedTaskInputRestoreCurrent(taskId, detailSeq)) return;
      setStatus(error.message || translate("notifications.taskMissing"), "error");
      return;
    }
  }
  const restoreSeq = ++state.taskInputRestoreSeq;
  void markTaskViewed(taskId);
  preserveComposerDraft();
  applyTaskToFormWithOutputLock(task);
  const restoredPrompt = legacyMethod("getPromptText");
  await restoreTaskReferenceFiles(task, { taskId, restoreSeq });
  if (!selectedTaskInputRestoreCurrent(taskId, restoreSeq)) return;
  renderSelectedTask(task, taskId);
  try {
    await restoreTaskInputs(task, { taskId, restoreSeq });
  } catch (error) {
    if (!selectedTaskInputRestoreCurrent(taskId, restoreSeq)) return;
    revokeUploadPreviewUrls(state.images);
    state.images = [];
    renderImageStrip();
    setStatus(error.message, "error");
    return;
  }
  if (!selectedTaskInputRestoreCurrent(taskId, restoreSeq)) return;
  markComposerBaseline(restoredPrompt);
  applySelectedTaskRequestPreview(task);
  if (!["running", "cancelling"].includes(String(task.status || ""))) renderSelectedTask(task, taskId);
}

function mainLightboxTaskIds() {
  const root = els.taskHistoryShell || els.sidebarContent || els.taskList;
  if (!root) return [];
  const seen = new Set();
  return Array.from(root.querySelectorAll(".task-card[data-task-id]"))
    .map((card) => String(card.dataset.taskId || ""))
    .filter((taskId) => {
      if (!taskId || seen.has(taskId)) return false;
      seen.add(taskId);
      const task = state.tasks.find((item) => String(item.task_id) === taskId);
      if (!task) return false;
      return taskOutputUrls(task).length > 0
        || (Array.isArray(task.thumbnail_urls) && task.thumbnail_urls.length > 0)
        || Number(task.generated_count || 0) > 0;
    });
}

async function openMainTaskLightboxByDirection(direction, context) {
  const taskIds = mainLightboxTaskIds();
  const currentTaskId = String(context?.taskId || state.selectedTaskId || "");
  const currentIndex = taskIds.indexOf(currentTaskId);
  if (currentIndex < 0) return;
  const step = direction === "previous" ? -1 : 1;
  for (let index = currentIndex + step; index >= 0 && index < taskIds.length; index += step) {
    const taskId = taskIds[index];
    await selectTask(taskId);
    const task = state.tasks.find((item) => String(item.task_id) === taskId);
    const urls = taskOutputUrls(task);
    if (!urls.length) continue;
    const imageIndex = Math.min(Math.max(0, Number(context?.imageIndex) || 0), urls.length - 1);
    window.openLightbox?.(urls[imageIndex], urls, imageIndex, {
      taskId,
      onTaskNavigate: openMainTaskLightboxByDirection,
    });
    return;
  }
}

async function restoreHistoryTaskReuseHandoff() {
  let raw = "";
  try {
    raw = localStorage.getItem(HISTORY_TASK_REUSE_HANDOFF_KEY) || "";
    if (!raw) return;
    localStorage.removeItem(HISTORY_TASK_REUSE_HANDOFF_KEY);
    const parsed = JSON.parse(raw);
    let task = parsed?.task || null;
    const taskId = String(parsed?.task_id || task?.task_id || "");
    if (!taskId) return;
    if (!task?.task_id) {
      task = await loadFullTaskDetail(taskId);
    }
    closePromptPopover();
    state.selectedTaskId = taskId;
    await revealHistoryTaskInSidebar(task);
    const restoreSeq = ++state.taskInputRestoreSeq;
    preserveComposerDraft();
  applyTaskToFormWithOutputLock(task);
  const restoredPrompt = legacyMethod("getPromptText");
    await restoreTaskReferenceFiles(task, { taskId, restoreSeq });
    if (!selectedTaskInputRestoreCurrent(taskId, restoreSeq)) return;
    renderSelectedTask(task, taskId);
    try {
      await restoreTaskInputs(task, { taskId, restoreSeq });
    } catch (error) {
      if (!selectedTaskInputRestoreCurrent(taskId, restoreSeq)) return;
      revokeUploadPreviewUrls(state.images);
      state.images = [];
      renderImageStrip();
      setStatus(error.message || translate("referenceCollector.addFailed"), "error");
      return;
    }
    if (!selectedTaskInputRestoreCurrent(taskId, restoreSeq)) return;
    applySelectedTaskRequestPreview(task);
    renderSelectedTask(task, taskId);
    setStatus(formatTranslation("status.reusedTask", { taskId }), "ok");
  } catch (error) {
    localStorage.removeItem(HISTORY_TASK_REUSE_HANDOFF_KEY);
    setStatus(error.message || translate("taskContext.actionFailed"), "error");
  }
}

export function initTaskSelectionFeature() {
  if (taskSelectionInitialized) return;
  taskSelectionInitialized = true;
  Object.assign(getLegacyBridge().methods, {
    ensureSelectedTaskDetail,
    openMainTaskLightboxByDirection,
    selectTask,
    restoreHistoryTaskReuseHandoff,
  });
}

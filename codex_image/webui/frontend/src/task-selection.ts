// @ts-nocheck
import { formatTranslation, translate } from "./i18n";
import { getLegacyBridge } from "./state";

const bridge = getLegacyBridge();
const state = bridge.state;
const els = bridge.els;

let taskSelectionInitialized = false;

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
function applyTaskToForm(task) { legacyMethod("applyTaskToForm", task); }
function updateTaskSelectionVisuals(taskId) { legacyMethod("updateTaskSelectionVisuals", taskId); }
function renderPreview(task) { legacyMethod("renderPreview", task); }
function taskFailureMessage(task) { return legacyMethod("taskFailureMessage", task); }
function taskRequestPreviewPayload(task) { return legacyMethod("taskRequestPreviewPayload", task); }
function revokeUploadPreviewUrls(sources) { legacyMethod("revokeUploadPreviewUrls", sources); }
function renderImageStrip() { legacyMethod("renderImageStrip"); }
function updateRequestPreview() { legacyMethod("updateRequestPreview"); }
function taskInputUrls(task) { return legacyMethod("taskInputUrls", task); }
function uploadSource(file) { return legacyMethod("uploadSource", file); }
function gallerySource(item) { return legacyMethod("gallerySource", item); }
function assetSource(item) { return legacyMethod("assetSource", item); }

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
  applySelectedTaskRequestPreview(task);
  updateTaskSelectionVisuals(taskId);
  renderPreview(task);
  if (task.status === "failed") {
    setStatus(taskFailureMessage(task) || translate("taskActions.failedFallback"), "error");
  } else if (task.status !== "running") {
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
  state.selectedTaskId = taskId;
  const task = state.tasks.find((item) => String(item.task_id) === String(taskId));
  if (!task) return;
  const restoreSeq = ++state.taskInputRestoreSeq;
  void markTaskViewed(taskId);
  applyTaskToForm(task);
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
  applySelectedTaskRequestPreview(task);
  if (task.status !== "running") renderSelectedTask(task, taskId);
}

export function initTaskSelectionFeature() {
  if (taskSelectionInitialized) return;
  taskSelectionInitialized = true;
  Object.assign(getLegacyBridge().methods, {
    selectTask,
  });
}

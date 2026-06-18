import { getLegacyBridge } from "./state";
import { translate } from "./i18n";

const bridge = getLegacyBridge();
const state = bridge.state;
const els = bridge.els;

function legacyMethod(name: string, ...args: any[]): any {
  const method = getLegacyBridge().methods[name];
  if (typeof method !== "function") {
    throw new Error("Legacy bridge method " + name + " is not available");
  }
  return method(...args);
}

const SUBMIT_TASK_TIMEOUT_MS = 45000;

function errorMessage(error: unknown, fallback: string): string {
  return error instanceof Error ? error.message || fallback : fallback;
}

function setStatus(...args: any[]) { return legacyMethod("setStatus", ...args); }
function setMode(...args: any[]) { return legacyMethod("setMode", ...args); }
function setPromptWithGalleryRefs(...args: any[]) { return legacyMethod("setPromptWithGalleryRefs", ...args); }
function persistMainModel(...args: any[]) { return legacyMethod("persistMainModel", ...args); }
function normalizeApiSettings(...args: any[]) { return legacyMethod("normalizeApiSettings", ...args); }
function normalizeApiImagesConcurrency(...args: any[]) { return legacyMethod("normalizeApiImagesConcurrency", ...args); }
function persistApiSettings(...args: any[]) { return legacyMethod("persistApiSettings", ...args); }
function populateApiSettingsForm(...args: any[]) { return legacyMethod("populateApiSettingsForm", ...args); }
function syncSizeControlsFromSize(...args: any[]) { return legacyMethod("syncSizeControlsFromSize", ...args); }
function updatePromptCount(...args: any[]) { return legacyMethod("updatePromptCount", ...args); }
function updateQuantity(...args: any[]) { return legacyMethod("updateQuantity", ...args); }
function syncRadioButtons(...args: any[]) { return legacyMethod("syncRadioButtons", ...args); }
function updateCompression(...args: any[]) { return legacyMethod("updateCompression", ...args); }
function updateCustomSize(...args: any[]) { return legacyMethod("updateCustomSize", ...args); }
function updateRequestPreview(...args: any[]) { return legacyMethod("updateRequestPreview", ...args); }
function currentTaskParams(...args: any[]) { return legacyMethod("currentTaskParams", ...args); }
function uploadInputs(...args: any[]) { return legacyMethod("uploadInputs", ...args); }
function galleryInputs(...args: any[]) { return legacyMethod("galleryInputs", ...args); }
function referenceAssetInputs(...args: any[]) { return legacyMethod("referenceAssetInputs", ...args); }
function currentAuthSource(...args: any[]) { return legacyMethod("currentAuthSource", ...args); }
function backendForAuthSource(...args: any[]) { return legacyMethod("backendForAuthSource", ...args); }
function currentApiMode(...args: any[]) { return legacyMethod("currentApiMode", ...args); }
function currentCodexMode(...args: any[]) { return legacyMethod("currentCodexMode", ...args); }
function getPromptText(...args: any[]) { return legacyMethod("getPromptText", ...args); }
function currentPromptForModel(...args: any[]) { return legacyMethod("currentPromptForModel", ...args); }
function currentPromptFidelity(...args: any[]) { return legacyMethod("currentPromptFidelity", ...args); }
function currentApiProviderId(...args: any[]) { return legacyMethod("currentApiProviderId", ...args); }
function currentApiProviderLabel(...args: any[]) { return legacyMethod("currentApiProviderLabel", ...args); }
function currentApiImagesConcurrency(...args: any[]) { return legacyMethod("currentApiImagesConcurrency", ...args); }
function currentMainModel(...args: any[]) { return legacyMethod("currentMainModel", ...args); }
function sourcePreviewUrl(...args: any[]) { return legacyMethod("sourcePreviewUrl", ...args); }
function syncPromptFromEditor(...args: any[]) { return legacyMethod("syncPromptFromEditor", ...args); }
function syncGalleryInputsFromPrompt(...args: any[]) { return legacyMethod("syncGalleryInputsFromPrompt", ...args); }
function missingGalleryInputs(...args: any[]) { return legacyMethod("missingGalleryInputs", ...args); }
function missingReferenceAssetInputs(...args: any[]) { return legacyMethod("missingReferenceAssetInputs", ...args); }
function customSizeValidationMessage(...args: any[]) { return legacyMethod("customSizeValidationMessage", ...args); }
function updatePixelPreview(...args: any[]) { return legacyMethod("updatePixelPreview", ...args); }
function addPendingTask(...args: any[]) { return legacyMethod("addPendingTask", ...args); }
function replacePendingTask(...args: any[]) { return legacyMethod("replacePendingTask", ...args); }
function startRunFeedback(...args: any[]) { return legacyMethod("startRunFeedback", ...args); }
function stopRunFeedback(...args: any[]) { return legacyMethod("stopRunFeedback", ...args); }
function markPendingTaskFailed(...args: any[]) { return legacyMethod("markPendingTaskFailed", ...args); }
function refreshRecentAssets(...args: any[]) { return legacyMethod("refreshRecentAssets", ...args); }
function renderPreview(...args: any[]) { return legacyMethod("renderPreview", ...args); }

function applyTaskToForm(task: any) {
  const params = task.params || {};
  setMode(task.mode || "generate");
  setPromptWithGalleryRefs(task.prompt || "", task.gallery_refs || []);
  const mainModel = params.main_model || task.request?.model;
  if (mainModel && els.mainModel) {
    els.mainModel.value = mainModel;
    persistMainModel();
  }
  if (params.api_mode) {
    state.apiSettings = normalizeApiSettings(state.apiSettings);
    if (params.api_provider_id && state.apiSettings.providers.some((provider: any) => provider.id === params.api_provider_id)) {
      state.apiSettings.active_provider_id = params.api_provider_id;
    }
    state.apiSettings.providers = state.apiSettings.providers.map((provider: any) => (
      provider.id === state.apiSettings.active_provider_id
        ? {
          ...provider,
          api_mode: params.api_mode,
          images_concurrency: params.api_images_concurrency
            ? normalizeApiImagesConcurrency(params.api_images_concurrency)
            : provider.images_concurrency,
        }
        : provider
    ));
    persistApiSettings();
    populateApiSettingsForm();
  }
  if (params.codex_mode) {
    state.apiSettings = normalizeApiSettings({
      ...state.apiSettings,
      codex_mode: params.codex_mode,
    });
    persistApiSettings();
    populateApiSettingsForm();
  }
  if (els.promptFidelity) {
    const fidelity = ["strict", "original", "off"].includes(params.prompt_fidelity) ? params.prompt_fidelity : "strict";
    els.promptFidelity.value = fidelity;
    els.promptFidelity.dispatchEvent(new Event("change"));
  }
  if (els.webSearch) {
    els.webSearch.checked = Boolean(params.web_search);
    els.webSearch.dispatchEvent(new Event("input"));
  }
  if (params.model) els.model.value = params.model;
  if (params.size) syncSizeControlsFromSize(params.size);
  if (params.n && els.nInput) {
    els.nInput.value = String(params.n);
  }
  if (params.quality) els.quality.value = params.quality;
  if (params.output_format) els.outputFormat.value = params.output_format;
  if (params.moderation) els.moderation.value = params.moderation;
  if (params.output_compression !== null && params.output_compression !== undefined) {
    els.compression.value = params.output_compression;
  }
  [els.quality, els.outputFormat, els.moderation].forEach((element: any) => {
    element.dispatchEvent(new Event("change"));
  });
  updatePromptCount();
  updateQuantity();
  syncRadioButtons(els.nInput);
  updateCompression();
  updateCustomSize();
  updateRequestPreview();
}

function buildPreviewRequest() {
  const params = currentTaskParams();
  const uploads = uploadInputs();
  const galleries = galleryInputs();
  const assets = referenceAssetInputs();
  const authSource = currentAuthSource();
  const isApi = authSource === "api";
  const isCodex = authSource === "codex";
  const codexMode = isCodex ? currentCodexMode() : null;
  const requestedBackend = backendForAuthSource(authSource, isApi ? currentApiMode() : null, codexMode);
  const payload: Record<string, any> = {
    mode: state.mode,
    auth_source: authSource,
    requested_backend: requestedBackend,
    prompt: getPromptText(),
    prompt_for_model: currentPromptForModel(),
    model: params.model,
    size: params.size,
    quality: params.quality,
    output_format: params.output_format,
    moderation: params.moderation,
    output_compression: params.output_compression,
    prompt_fidelity: currentPromptFidelity(),
    web_search: Boolean(params.web_search),
    n: params.n,
    images: uploads.map((source: any) => source.name),
    gallery_image_ids: galleries.map((source: any) => source.id),
    reference_asset_ids: assets.map((source: any) => source.id),
  };
  if (isApi) {
    const apiMode = currentApiMode();
    const action = state.mode === "edit" || uploads.length || assets.length || galleries.length ? "edit" : "generate";
    payload.api_provider_id = currentApiProviderId();
    payload.api_provider_name = currentApiProviderLabel();
    payload.webui_api_provider_id = payload.api_provider_id;
    payload.webui_api_provider_name = payload.api_provider_name;
    payload.api_mode = apiMode;
    payload.api_images_concurrency = currentApiImagesConcurrency();
    if (apiMode === "responses") {
      payload.endpoint = "/responses";
      payload.model = params.main_model;
      const imageTool: Record<string, any> = {
        type: "image_generation",
        action,
        model: params.model,
        size: params.size,
        quality: params.quality,
        output_format: params.output_format,
        moderation: params.moderation,
      };
      payload.tools = params.web_search
        ? [{ type: "web_search", search_context_size: "low" }, imageTool]
        : [imageTool];
      if (params.web_search) {
        payload.tool_choice = "required";
        payload.parallel_tool_calls = false;
      }
      if (params.output_compression !== null && params.output_compression !== undefined) {
        imageTool.output_compression = params.output_compression;
      }
    } else {
      payload.endpoint = action === "edit" ? "/images/edits" : "/images/generations";
    }
  } else if (isCodex) {
    const action = state.mode === "edit" || uploads.length || assets.length || galleries.length ? "edit" : "generate";
    payload.codex_mode = codexMode;
    if (codexMode === "responses") {
      payload.endpoint = "/responses";
      payload.main_model = params.main_model;
      payload.model = params.main_model;
      const imageTool: Record<string, any> = {
        type: "image_generation",
        action,
        model: params.model,
        size: params.size,
        quality: params.quality,
        output_format: params.output_format,
        moderation: params.moderation,
      };
      payload.tools = params.web_search
        ? [{ type: "web_search", search_context_size: "low" }, imageTool]
        : [imageTool];
      if (params.web_search) {
        payload.tool_choice = "required";
        payload.parallel_tool_calls = false;
      }
      if (params.output_compression !== null && params.output_compression !== undefined) {
        imageTool.output_compression = params.output_compression;
      }
    } else {
      payload.endpoint = action === "edit" ? "/images/edits" : "/images/generations";
      payload.main_model = params.main_model;
    }
  } else {
    payload.main_model = params.main_model;
  }
  return payload;
}

function createPendingTask() {
  const taskId = `pending-${Date.now()}`;
  const now = new Date().toISOString();
  const localInputFiles = state.images.slice();
  const previewSource = localInputFiles[0];
  const request = buildPreviewRequest();
  return {
    task_id: taskId,
    local_pending: true,
    created_at: now,
    updated_at: now,
    started_at: now,
    mode: state.mode,
    status: "submitting",
    prompt: getPromptText(),
    prompt_for_model: currentPromptForModel(),
    requested_backend: request.requested_backend,
    api_provider_id: request.api_provider_id,
    api_provider_name: request.api_provider_name,
    params: currentTaskParams(),
    input_files: localInputFiles.filter((source: any) => source.kind === "upload").map((source: any) => source.name),
    gallery_refs: localInputFiles.filter((source: any) => source.kind === "gallery"),
    input_sources: localInputFiles,
    local_input_files: localInputFiles,
    preview_url: sourcePreviewUrl(previewSource),
    request,
  };
}

function addQueuedTask(task: any) {
  replacePendingTask(state.pendingTaskId || task.task_id, task);
}

async function runTask() {
  syncPromptFromEditor();
  syncGalleryInputsFromPrompt();
  const prompt = getPromptText();
  const promptForModel = currentPromptForModel();
  const uploads = uploadInputs();
  const galleries = galleryInputs();
  const assets = referenceAssetInputs();
  if (missingGalleryInputs().length) {
    setStatus(translate("status.missingGalleryReference"), "error");
    return;
  }
  if (missingReferenceAssetInputs().length) {
    setStatus(translate("status.missingRecentReference"), "error");
    return;
  }
  if (!prompt) {
    setStatus(translate("status.emptyPrompt"), "error");
    return;
  }
  if (state.mode === "edit" && !uploads.length && !assets.length && !galleries.length) {
    setStatus(translate("status.editNeedsImage"), "error");
    return;
  }
  const customSizeError = els.size?.value === "custom" ? customSizeValidationMessage() : "";
  if (customSizeError) {
    updateCustomSize();
    updatePixelPreview("custom");
    setStatus(customSizeError, "error");
    return;
  }

  const form = new FormData();
  form.append("prompt", prompt);
  form.append("prompt_for_model", promptForModel);
  const params = currentTaskParams();
  form.append("main_model", currentMainModel());
  form.append("model", params.model);
  form.append("size", params.size);
  if (params.resolution) form.append("resolution", params.resolution);
  if (params.ratio) form.append("ratio", params.ratio);
  if (params.orientation) form.append("orientation", params.orientation);
  form.append("quality", params.quality);
  form.append("output_format", params.output_format);
  form.append("moderation", params.moderation);
  form.append("n", String(params.n));
  form.append("prompt_fidelity", currentPromptFidelity());
  if (params.web_search) form.append("web_search", "true");
  if (currentAuthSource() === "api") {
    form.append("api_provider_id", currentApiProviderId());
    form.append("api_mode", currentApiMode());
  } else if (currentAuthSource() === "codex") {
    form.append("codex_mode", currentCodexMode());
  }
  if (els.outputFormat.value !== "png") {
    form.append("output_compression", String(params.output_compression));
  }
  galleries.forEach((source: any) => form.append("gallery_image_ids", source.id));
  assets.forEach((source: any) => form.append("reference_asset_ids", source.id));

  if (state.mode === "generate") {
    uploads.forEach((source: any) => form.append("reference_images", source.file));
  } else {
    uploads.forEach((source: any) => form.append("images", source.file));
  }

  const pendingTask = createPendingTask();
  addPendingTask(pendingTask);
  if (els.requestJson) {
    els.requestJson.textContent = JSON.stringify(pendingTask.request, null, 2);
  }
  startRunFeedback(pendingTask, translate("taskStatus.submitting"));
  els.runButton.disabled = true;

  const controller = new AbortController();
  const submitTimeoutId = window.setTimeout(() => controller.abort(), SUBMIT_TASK_TIMEOUT_MS);
  try {
    const response = await fetch(state.mode === "edit" ? "/api/edit" : "/api/generate", {
      method: "POST",
      body: form,
      signal: controller.signal,
    });
    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.detail || translate("taskSubmit.requestFailed"));
    }
    addQueuedTask(data.task);
    if (els.requestJson) {
      els.requestJson.textContent = JSON.stringify(data.request || {}, null, 2);
    }
    stopRunFeedback();
    setStatus(translate("taskSubmit.queued"), "ok");
    await window.refreshQueue?.();
    await refreshRecentAssets();
    renderPreview(data.task);
  } catch (error) {
    stopRunFeedback();
    const message = error instanceof DOMException && error.name === "AbortError"
      ? translate("taskSubmit.timeout")
      : errorMessage(error, translate("taskSubmit.failed"));
    markPendingTaskFailed(pendingTask.task_id, message);
    setStatus(message, "error");
  } finally {
    window.clearTimeout(submitTimeoutId);
    stopRunFeedback();
    els.runButton.disabled = !state.authAvailable;
  }
}

export function initTaskSubmitFeature() {
  Object.assign(getLegacyBridge().methods, {
    applyTaskToForm,
    buildPreviewRequest,
    createPendingTask,
    addQueuedTask,
    runTask,
  });
}

import { getLegacyBridge } from "./state";
import { currentLocaleCode, translate } from "./i18n";
import { selectedProviderBinding } from "./provider-selection";
import { appendCanonicalGenerationFields, currentGenerationSelection } from "./generation-request";
import { taskOutputControlValues } from "./task-model-summary";

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

interface ApplyTaskToFormOptions {
  preserveOutputSettings?: boolean;
  preserveComposer?: boolean;
}

function errorMessage(error: unknown, fallback: string): string {
  return error instanceof Error ? error.message || fallback : fallback;
}

function setStatus(...args: any[]) { return legacyMethod("setStatus", ...args); }
function setMode(...args: any[]) { return legacyMethod("setMode", ...args); }
function setPromptWithGalleryRefs(...args: any[]) { return legacyMethod("setPromptWithGalleryRefs", ...args); }
function persistMainModel(...args: any[]) { return legacyMethod("persistMainModel", ...args); }
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
function currentCodexMode(...args: any[]) { return legacyMethod("currentCodexMode", ...args); }
function getPromptText(...args: any[]) { return legacyMethod("getPromptText", ...args); }
function currentPromptForModel(...args: any[]) { return legacyMethod("currentPromptForModel", ...args); }
function currentPromptFidelity(...args: any[]) { return legacyMethod("currentPromptFidelity", ...args); }
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
function referenceFileUploads(...args: any[]) { return legacyMethod("referenceFileUploads", ...args); }
function storedReferenceFileInputs(...args: any[]) { return legacyMethod("storedReferenceFileInputs", ...args); }
function missingReferenceFileInputs(...args: any[]) { return legacyMethod("missingReferenceFileInputs", ...args); }
function renderPreview(...args: any[]) { return legacyMethod("renderPreview", ...args); }

export function currentCanonicalParameters(): Record<string, unknown> {
  return currentGenerationSelection().parameters;
}

function selectedRoutingFields(): { authSource: "codex" | "api"; requestedBackend: string } {
  const authSource = state.selectedProviderId === "codex" ? "codex" : "api";
  const profile = selectedProviderBinding()?.protocol_profile || "";
  return { authSource, requestedBackend: profile || (authSource === "codex" ? "codex_images" : "api_images") };
}

const REFERENCE_FILE_ERROR_KEYS: Record<string, string> = {
  reference_file_empty: "referenceFiles.errorEmpty",
  reference_file_type_unsupported: "referenceFiles.errorUnsupported",
  reference_file_type_mismatch: "referenceFiles.errorMismatch",
  reference_file_invalid: "referenceFiles.errorInvalid",
  reference_file_too_large: "referenceFiles.errorTooLarge",
  reference_files_total_too_large: "referenceFiles.errorTotalTooLarge",
  reference_file_missing: "referenceFiles.errorMissing",
  reference_files_require_responses: "referenceFiles.requiresResponses",
  provider_reference_files_unsupported: "referenceFiles.errorProviderUnsupported",
};

function apiErrorMessage(detail: unknown, fallback: string): string {
  if (typeof detail === "string" && detail) return detail;
  if (detail && typeof detail === "object" && "message" in detail) return String((detail as any).message || fallback);
  return fallback;
}

function sanitizedApiMessage(detail: unknown, fallback: string): string {
  return apiErrorMessage(detail, fallback).replace(/[\u0000-\u001f\u007f]/g, " ").trim().slice(0, 500) || fallback;
}

function responseErrorMessage(detail: unknown): string {
  const fallback = translate("taskSubmit.requestFailed");
  const code = typeof detail === "string"
    ? detail
    : detail && typeof detail === "object" && "code" in detail
      ? String((detail as any).code || "")
      : "";
  const localeKey = REFERENCE_FILE_ERROR_KEYS[code];
  return localeKey ? translate(localeKey) : sanitizedApiMessage(detail, fallback);
}

function referenceFileMetadata(source: any) {
  return {
    ...(source.kind === "asset" && source.id ? { id: source.id } : {}),
    kind: source.kind,
    filename: source.filename,
    mime_type: source.mime_type,
    size_bytes: source.size_bytes,
    family: source.family,
    missing: Boolean(source.missing),
  };
}

export function applyTaskOutputParams(task: any): void {
  const params = task.params || {};
  const request = task.request || {};
  const output = taskOutputControlValues(task);
  const usesResponses = params.api_mode === "responses"
    || params.codex_mode === "responses"
    || request.api_mode === "responses"
    || request.codex_mode === "responses"
    || request.endpoint === "/responses";
  const mainModel = params.main_model || request.main_model || (usesResponses ? request.model : "");
  if (mainModel && els.mainModel) {
    els.mainModel.value = mainModel;
    persistMainModel();
  }
  if (els.promptFidelity) {
    const fidelity = ["strict", "original", "off"].includes(params.prompt_fidelity) ? params.prompt_fidelity : "strict";
    els.promptFidelity.value = fidelity;
    els.promptFidelity.dispatchEvent(new Event("change"));
  }
  if (els.webSearch) {
    els.webSearch.checked = Boolean(output.web_search);
    els.webSearch.dispatchEvent(new Event("input"));
  }
  if (params.model && els.model) els.model.value = params.model;
  if (output.size) syncSizeControlsFromSize(output.size);
  if (output.n && els.nInput) {
    els.nInput.value = String(output.n);
  }
  if (output.quality && els.quality) els.quality.value = output.quality;
  if (output.output_format && els.outputFormat) els.outputFormat.value = output.output_format;
  if (output.moderation && els.moderation) els.moderation.value = output.moderation;
  if (output.output_compression !== null && output.output_compression !== undefined && els.compression) {
    els.compression.value = output.output_compression;
  }
  [els.quality, els.outputFormat, els.moderation].forEach((element: any) => {
    element?.dispatchEvent(new Event("change"));
  });
  updateQuantity();
  syncRadioButtons(els.nInput);
  updateCompression();
  updateCustomSize();
  updateRequestPreview();
}

function applyTaskToForm(task: any, options?: ApplyTaskToFormOptions) {
  if (options?.preserveComposer) {
    updateRequestPreview();
    return;
  }
  setMode(task.mode || "generate");
  setPromptWithGalleryRefs(task.prompt || task.prompt_for_model || "", task.gallery_refs || []);
  if (!options?.preserveOutputSettings) applyTaskOutputParams(task);
  updatePromptCount();
  updateRequestPreview();
}

function buildPreviewRequest() {
  const params = currentTaskParams();
  const uploads = uploadInputs();
  const galleries = galleryInputs();
  const assets = referenceAssetInputs();
  const fileUploads = referenceFileUploads();
  const storedFiles = storedReferenceFileInputs();
  const { authSource, requestedBackend } = selectedRoutingFields();
  const isApi = authSource === "api";
  const isCodex = authSource === "codex";
  const codexMode = isCodex ? currentCodexMode() : null;
  const parameters = currentCanonicalParameters();
  const selection = currentGenerationSelection();
  const payload: Record<string, any> = {
    mode: state.mode,
    auth_source: authSource,
    requested_backend: requestedBackend,
    canonical_model_id: selection.canonicalModelId,
    provider_id: selection.providerId,
    parameters,
    ui_language: currentLocaleCode(),
    prompt: getPromptText(),
    prompt_for_model: currentPromptForModel(),
    images: uploads.map((source: any) => source.name),
    gallery_image_ids: galleries.map((source: any) => source.id),
    reference_asset_ids: assets.map((source: any) => source.id),
    reference_files: fileUploads.map((source: any) => source.filename),
    reference_file_ids: storedFiles.map((source: any) => source.id),
  };
  const usesGptPromptProcessing = !state.generationCatalog || state.selectedModelId === "gpt-image-2";
  if (usesGptPromptProcessing) payload.prompt_fidelity = currentPromptFidelity();
  if (isApi) {
    payload.api_provider_id = state.selectedProviderId;
    payload.api_provider_name = state.generationCatalog?.providers.find((provider: any) => provider.id === state.selectedProviderId)?.name || "";
    payload.webui_api_provider_id = payload.api_provider_id;
    payload.webui_api_provider_name = payload.api_provider_name;
    payload.endpoint = selectedProviderBinding()?.protocol_profile || "";
  } else if (isCodex) {
    payload.codex_mode = codexMode;
    if (usesGptPromptProcessing) payload.main_model = params.main_model;
  }
  return payload;
}

function createPendingTask() {
  const taskId = `pending-${Date.now()}`;
  const now = new Date().toISOString();
  const localInputFiles = state.images.slice();
  const previewSource = localInputFiles[0];
  const request = buildPreviewRequest();
  const localReferenceFiles = state.referenceFiles.map(referenceFileMetadata);
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
    reference_files: localReferenceFiles,
    local_reference_files: localReferenceFiles,
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
  const fileUploads = referenceFileUploads();
  const storedFiles = storedReferenceFileInputs();
  if (missingGalleryInputs().length) {
    setStatus(translate("status.missingGalleryReference"), "error");
    return;
  }
  if (missingReferenceAssetInputs().length) {
    setStatus(translate("status.missingRecentReference"), "error");
    return;
  }
  if (missingReferenceFileInputs().length) {
    setStatus(translate("referenceFiles.errorMissing"), "error");
    return;
  }
  if (!prompt) {
    setStatus(translate("status.emptyPrompt"), "error");
    return;
  }
  if (!state.selectedModelId || !state.selectedProviderId || !state.authAvailable) {
    setStatus(translate("modelSelection.providerUnavailable"), "error");
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
  form.append("ui_language", currentLocaleCode());
  appendCanonicalGenerationFields(form, currentGenerationSelection());
  if (!state.generationCatalog || state.selectedModelId === "gpt-image-2") {
    form.append("main_model", currentMainModel());
    form.append("prompt_fidelity", currentPromptFidelity());
  }
  galleries.forEach((source: any) => form.append("gallery_image_ids", source.id));
  assets.forEach((source: any) => form.append("reference_asset_ids", source.id));
  fileUploads.forEach((source: any) => form.append("reference_files", source.file));
  storedFiles.forEach((source: any) => form.append("reference_file_ids", source.id));

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
      throw new Error(responseErrorMessage(data.detail));
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
    applyTaskOutputParams,
    applyTaskToForm,
    buildPreviewRequest,
    currentCanonicalParameters,
    createPendingTask,
    addQueuedTask,
    runTask,
  });
}

import { getEls } from "./dom";
import { formatTranslation, LOCALE_CHANGE_EVENT, translate } from "./i18n";
import { getLegacyBridge, getState } from "./state";

let inputSourcesFeatureInitialized = false;

function legacyMethod(name: string, ...args: any[]) {
  return getLegacyBridge().methods[name]?.(...args);
}

function setStatus(message: string, type?: string) {
  legacyMethod("setStatus", message, type);
}

function escapeHtml(value: any) {
  return legacyMethod("escapeHtml", value);
}

function uploadSource(file: File) {
  return {
    kind: "upload",
    file,
    originalFile: file,
    name: file.name,
    previewUrl: URL.createObjectURL(file),
    edited: false,
  };
}

function gallerySource(item: any) {
  return {
    kind: "gallery",
    id: item.id,
    name: item.name,
    category: item.category,
    category_name: item.category_name || legacyMethod("categoryLabel", item.category),
    category_prompt_role: item.category_prompt_role || legacyMethod("categoryPromptRole", item.category),
    prompt_note: item.prompt_note || "",
    image_url: item.image_url || "",
    previewUrl: item.image_url || "",
    missing: Boolean(item.missing),
  };
}

function assetSource(item: any) {
  return {
    kind: "asset",
    id: item.id,
    name: item.name || item.filename || "",
    filename: item.filename || "",
    mime_type: item.mime_type || "",
    image_url: item.image_url || "",
    previewUrl: item.image_url || "",
    missing: Boolean(item.missing),
  };
}

function sourcePreviewUrl(source: any) {
  if (!source) return "";
  if (source.kind === "upload") return source.previewUrl;
  return source.image_url || source.previewUrl || "";
}

function sourceListUsesPreviewUrl(sources: any, previewUrl: string, ignoredSources = new Set()) {
  return Array.isArray(sources) && sources.some((source) => {
    if (!source || ignoredSources.has(source)) return false;
    if (typeof source === "string") return source === previewUrl;
    return sourcePreviewUrl(source) === previewUrl || source.preview_url === previewUrl;
  });
}

function uploadPreviewUrlInUse(previewUrl: string, options: any = {}) {
  const state = getState();
  if (!previewUrl) return false;
  const ignoredCurrentSources = options.ignoredCurrentSources || new Set();
  const ignoredTasks = options.ignoredTasks || new Set();
  if (sourceListUsesPreviewUrl(state.images, previewUrl, ignoredCurrentSources)) return true;
  return state.tasks.some((task) => {
    if (!task || ignoredTasks.has(task)) return false;
    return task.preview_url === previewUrl
      || sourceListUsesPreviewUrl(task.local_input_files, previewUrl)
      || sourceListUsesPreviewUrl(task.input_sources, previewUrl);
  });
}

function revokeUploadPreviewUrl(source: any, options: any = {}) {
  if (!source || source.kind !== "upload" || !source.previewUrl?.startsWith("blob:")) return;
  if (uploadPreviewUrlInUse(source.previewUrl, options)) return;
  URL.revokeObjectURL(source.previewUrl);
}

function revokeUploadPreviewUrls(sources: any) {
  const uploadSources = (Array.isArray(sources) ? sources : []).filter((source) => source?.kind === "upload");
  const ignoredCurrentSources = new Set(uploadSources);
  uploadSources.forEach((source) => revokeUploadPreviewUrl(source, { ignoredCurrentSources }));
}

function taskUploadSources(task: any) {
  const sources: any[] = [];
  const seenPreviewUrls = new Set();
  [task?.local_input_files, task?.input_sources].forEach((list) => {
    if (!Array.isArray(list)) return;
    list.forEach((source) => {
      if (!source || source.kind !== "upload" || !source.previewUrl) return;
      if (seenPreviewUrls.has(source.previewUrl)) return;
      seenPreviewUrls.add(source.previewUrl);
      sources.push(source);
    });
  });
  return sources;
}

function revokeTaskUploadPreviewUrls(task: any) {
  if (!task) return;
  const ignoredTasks = new Set([task]);
  taskUploadSources(task).forEach((source) => revokeUploadPreviewUrl(source, { ignoredTasks }));
}

function sourceName(source: any) {
  if (!source) return "";
  if (source.kind === "upload") return source.name || source.file?.name || translate("inputSource.uploadFallback");
  if (source.kind === "asset") return source.name || source.filename || translate("recentAssets.defaultName");
  return source.name || translate("inputSource.galleryFallback");
}

function addGalleryInput(item: any, options: any = {}) {
  const state = getState();
  if (!item) return;
  const alreadySelected = state.images.some((source: any) => source.kind === "gallery" && source.id === item.id);
  if (!alreadySelected) {
    state.images.push(gallerySource(item));
    if (state.mode !== "edit") {
      legacyMethod("setMode", "edit");
    }
    legacyMethod("renderImageStrip");
  }
  if (options.syncPrompt !== false) legacyMethod("ensurePromptGalleryMention", item);
  legacyMethod("updateRequestPreview");
}

function galleryInputs() {
  const galleries = getState().images.filter((image: any) => image.kind === "gallery");
  return galleries.filter((image: any) => !image.missing);
}

function referenceAssetInputs() {
  return getState().images.filter((image: any) => image.kind === "asset" && !image.missing);
}

function uploadInputs() {
  return getState().images.filter((image: any) => image.kind === "upload");
}

function addImageFiles(files: any, options: any = {}) {
  const state = getState();
  const imageFiles = Array.from(files || []).filter((file: any) => file?.type?.startsWith("image/")) as File[];
  if (!imageFiles.length) {
    if (options.emptyMessage) setStatus(options.emptyMessage, "error");
    return false;
  }
  state.images.push(...imageFiles.map((file) => uploadSource(file)));
  if (state.images.length > 0 && state.mode !== "edit") {
    legacyMethod("setMode", "edit");
  }
  legacyMethod("renderImageStrip");
  legacyMethod("updateRequestPreview");
  if (options.successMessage) {
    setStatus(typeof options.successMessage === "function" ? options.successMessage(imageFiles.length) : options.successMessage, "ok");
  }
  return true;
}

function clipboardImageFilename(type: any, index: number) {
  const extensionByType: Record<string, string> = {
    "image/gif": "gif",
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
  };
  const extension = extensionByType[String(type || "").toLowerCase()] || "png";
  const timestamp = new Date().toISOString().replace(/[:.]/g, "-");
  return `clipboard-${timestamp}-${index + 1}.${extension}`;
}

function clipboardFileFromDataTransferItem(item: any, index: number) {
  const file = item?.getAsFile?.();
  if (!file) return null;
  const type = file.type || item.type || "image/png";
  return new File([file], clipboardImageFilename(type, index), {
    type,
    lastModified: file.lastModified || Date.now(),
  });
}

function imageFilesFromClipboardItems(items: any) {
  return Array.from(items || [])
    .filter((item: any) => item?.kind === "file" && item.type?.startsWith("image/"))
    .map((item, index) => clipboardFileFromDataTransferItem(item, index))
    .filter(Boolean);
}

function clipboardPasteShortcutLabel() {
  return /Mac|iPhone|iPad|iPod/.test(String(globalThis.navigator?.platform || "")) ? "Cmd+V" : "Ctrl+V";
}

function clipboardReadFallbackMessage(prefix: string) {
  return formatTranslation("inputSource.focusPasteFallback", {
    prefix,
    shortcut: clipboardPasteShortcutLabel(),
  });
}

function focusImagePasteTarget() {
  const els = getEls();
  els.imageUploadSource?.focus({ preventScroll: true });
}

function handleImagePaste(event: ClipboardEvent) {
  const files = imageFilesFromClipboardItems(event.clipboardData?.items);
  if (!files.length) return;
  event.preventDefault();
  addImageFiles(files, {
    successMessage: (count: number) => formatTranslation("inputSource.pastedCount", { count }),
  });
}

async function readClipboardImageFiles() {
  const clipboardItems = await navigator.clipboard?.read();
  const files: File[] = [];
  for (const item of clipboardItems || []) {
    const imageType = item.types.find((type) => type.startsWith("image/"));
    if (!imageType) continue;
    const blob = await item.getType(imageType);
    files.push(new File([blob], clipboardImageFilename(imageType, files.length), {
      type: imageType,
      lastModified: Date.now(),
    }));
  }
  return files;
}

async function pasteClipboardImages() {
  const els = getEls();
  if (!navigator.clipboard?.read) {
    focusImagePasteTarget();
    setStatus(clipboardReadFallbackMessage(translate("inputSource.clipboardUnsupported")), "error");
    return;
  }
  els.pasteClipboardButton.disabled = true;
  try {
    const files = await readClipboardImageFiles();
    const added = addImageFiles(files, {
      emptyMessage: clipboardReadFallbackMessage(translate("inputSource.clipboardEmpty")),
      successMessage: (count: number) => formatTranslation("inputSource.pastedCount", { count }),
    });
    if (!added) focusImagePasteTarget();
  } catch (error: any) {
    focusImagePasteTarget();
    const reason = ["NotAllowedError", "SecurityError"].includes(String(error?.name || ""))
      ? translate("inputSource.clipboardDenied")
      : translate("inputSource.clipboardReadFailed");
    setStatus(clipboardReadFallbackMessage(reason), "error");
  } finally {
    els.pasteClipboardButton.disabled = false;
  }
}

function missingGalleryInputs() {
  return getState().images.filter((image: any) => image.kind === "gallery" && image.missing);
}

function missingReferenceAssetInputs() {
  return getState().images.filter((image: any) => image.kind === "asset" && image.missing);
}

function addReferenceAssetInput(item: any) {
  const state = getState();
  if (!item?.id) return;
  const alreadySelected = state.images.some((source: any) => source.kind === "asset" && source.id === item.id);
  if (alreadySelected) return;
  state.images.push(assetSource(item));
  if (state.mode !== "edit") {
    legacyMethod("setMode", "edit");
  }
  legacyMethod("renderImageStrip");
  legacyMethod("updateRequestPreview");
}

function collectReferenceOutput(url: string, options: any = {}) {
  const state = getState();
  if (!url) return;
  if (state.collectedReferences.some((item: any) => item.url === url)) {
    setStatus(translate("referenceCollector.alreadyStaged"), "ok");
    return;
  }
  state.collectedReferences.push({
    url,
    name: options.name || "",
    sourceTaskId: options.sourceTaskId || "",
    outputIndex: options.outputIndex || null,
  });
  renderReferenceCollector();
  setStatus(formatTranslation("referenceCollector.staged", { count: state.collectedReferences.length }), "ok");
}

function renderReferenceCollector() {
  const state = getState();
  const els = getEls();
  if (!els.referenceCollector) return;
  const items = state.collectedReferences;
  if (!items.length) {
    els.referenceCollector.classList.add("hidden");
    els.referenceCollector.innerHTML = "";
    return;
  }
  els.referenceCollector.classList.remove("hidden");
  els.referenceCollector.innerHTML = `
    <div class="reference-collector-header">
      <span>${escapeHtml(formatTranslation("referenceCollector.title", { count: items.length }))}</span>
      <div class="reference-collector-actions">
        <button class="ghost-button text-sm" type="button" data-reference-collector-add-all>${escapeHtml(translate("referenceCollector.addAll"))}</button>
        <button class="ghost-button text-sm" type="button" data-reference-collector-clear>${escapeHtml(translate("action.clear"))}</button>
      </div>
    </div>
    <div class="reference-collector-list">
      ${items.map((item: any, index: number) => `
        <div class="reference-collector-item" title="${escapeHtml(item.name || translate("referenceCollector.itemFallback"))}">
          <img src="${escapeHtml(item.url)}" alt="">
          <button type="button" data-reference-collector-remove="${index}" aria-label="${escapeHtml(formatTranslation("referenceCollector.remove"))}">×</button>
        </div>
      `).join("")}
    </div>
  `;
  els.referenceCollector.querySelector("[data-reference-collector-add-all]")?.addEventListener("click", addCollectedReferencesToInput);
  els.referenceCollector.querySelector("[data-reference-collector-clear]")?.addEventListener("click", () => clearCollectedReferences());
  els.referenceCollector.querySelectorAll("[data-reference-collector-remove]").forEach((button: any) => {
    button.addEventListener("click", () => removeCollectedReference(button.dataset.referenceCollectorRemove));
  });
}

function removeCollectedReference(index: any) {
  const itemIndex = Number.parseInt(index, 10);
  if (!Number.isInteger(itemIndex) || itemIndex < 0 || itemIndex >= getState().collectedReferences.length) return;
  getState().collectedReferences.splice(itemIndex, 1);
  renderReferenceCollector();
}

function clearCollectedReferences(options: any = {}) {
  getState().collectedReferences = [];
  renderReferenceCollector();
  if (!options.silent) setStatus(translate("referenceCollector.cleared"), "ok");
}

function imageExtensionFromType(type: any) {
  const normalized = String(type || "").toLowerCase();
  if (normalized === "image/jpeg") return "jpg";
  if (normalized === "image/webp") return "webp";
  if (normalized === "image/gif") return "gif";
  return "png";
}

function filenameFromImageUrl(url: string, fallback: string) {
  try {
    const pathname = new URL(url, window.location.origin).pathname;
    const filename = decodeURIComponent(pathname.split("/").filter(Boolean).pop() || "");
    return filename || fallback;
  } catch {
    return fallback;
  }
}

function ensureImageFilenameExtension(filename: string, type: any) {
  const clean = String(filename || "").replace(/[\\/:*?"<>|]+/g, "-").trim() || "reference.png";
  if (/\.(png|jpe?g|webp|gif)$/i.test(clean)) return clean;
  return `${clean}.${imageExtensionFromType(type)}`;
}

async function imageFileFromUrl(url: string, fallbackName: string) {
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(formatTranslation("referenceCollector.readFailed", { status: response.status }));
  }
  const blob = await response.blob();
  const type = blob.type || "image/png";
  const filename = ensureImageFilenameExtension(filenameFromImageUrl(url, fallbackName), type);
  return new File([blob], filename, { type });
}

function collectedReferenceFilename(item: any, index: number) {
  return ensureImageFilenameExtension(item?.name || `collected-reference-${index + 1}`, "image/png");
}

async function addCollectedReferencesToInput() {
  const state = getState();
  const els = getEls();
  const items = state.collectedReferences.slice();
  if (!items.length) return;
  const addButton = els.referenceCollector?.querySelector("[data-reference-collector-add-all]");
  if (addButton) addButton.disabled = true;
  try {
    const files: File[] = [];
    for (const [index, item] of items.entries()) {
      files.push(await imageFileFromUrl(item.url, collectedReferenceFilename(item, index)));
    }
    const added = addImageFiles(files, {
      successMessage: (count: number) => formatTranslation("referenceCollector.added", { count }),
    });
    if (added) clearCollectedReferences({ silent: true });
  } catch (error: any) {
    setStatus(error.message || translate("referenceCollector.addFailed"), "error");
    renderReferenceCollector();
  }
}

function bindInputSourceEvents() {
  const els = getEls();
  els.pasteClipboardButton?.addEventListener("click", pasteClipboardImages);
  document.addEventListener("paste", handleImagePaste);
}

export function initInputSourcesFeature() {
  if (inputSourcesFeatureInitialized) return;
  inputSourcesFeatureInitialized = true;
  bindInputSourceEvents();
  document.addEventListener(LOCALE_CHANGE_EVENT, renderReferenceCollector);
  Object.assign(getLegacyBridge().methods, {
    uploadSource,
    gallerySource,
    assetSource,
    sourcePreviewUrl,
    revokeUploadPreviewUrl,
    revokeUploadPreviewUrls,
    revokeTaskUploadPreviewUrls,
    sourceName,
    addGalleryInput,
    galleryInputs,
    referenceAssetInputs,
    uploadInputs,
    addImageFiles,
    handleImagePaste,
    pasteClipboardImages,
    missingGalleryInputs,
    missingReferenceAssetInputs,
    addReferenceAssetInput,
    collectReferenceOutput,
    renderReferenceCollector,
    imageFileFromUrl,
  });
}

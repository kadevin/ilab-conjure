import { getEls } from "./dom";
import { formatTranslation, LOCALE_CHANGE_EVENT, translate } from "./i18n";
import { referenceFileIconSvgMarkup } from "./reference-file-icons";
import { getLegacyBridge, getState } from "./state";

export type ReferenceFileSource = {
  kind: "upload" | "asset";
  id?: string;
  file?: File;
  filename: string;
  mime_type: string;
  size_bytes: number;
  family: "pdf" | "spreadsheet" | "document" | "text";
  missing?: boolean;
};

const FAMILY_BY_EXTENSION: Record<string, ReferenceFileSource["family"]> = {
  pdf: "pdf",
  xla: "spreadsheet", xlb: "spreadsheet", xlc: "spreadsheet", xlm: "spreadsheet",
  xls: "spreadsheet", xlt: "spreadsheet", xlw: "spreadsheet", xlsx: "spreadsheet",
  csv: "spreadsheet", tsv: "spreadsheet", iif: "spreadsheet",
  doc: "document", docx: "document", dot: "document", odt: "document", rtf: "document",
  pot: "document", ppa: "document", pps: "document", ppt: "document", pwz: "document",
  wiz: "document", pptx: "document",
};
const TEXT_EXTENSIONS = new Set([
  "asm", "bat", "c", "cc", "conf", "cpp", "css", "cxx", "def", "dic", "eml", "h", "hh",
  "htm", "html", "ics", "ifb", "in", "js", "json", "ksh", "list", "log", "markdown", "md",
  "mht", "mhtml", "mime", "mjs", "nws", "pl", "py", "rst", "s", "sql", "srt", "text", "txt",
  "vcf", "vtt", "xml",
]);
const MIME_BY_EXTENSION: Record<string, string> = {
  pdf: "application/pdf",
  xlsx: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
  csv: "text/csv", tsv: "text/tsv", iif: "text/x-iif",
  doc: "application/msword",
  docx: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
  odt: "application/vnd.oasis.opendocument.text", rtf: "application/rtf",
  pptx: "application/vnd.openxmlformats-officedocument.presentationml.presentation",
};

let initialized = false;
let requirementActionVisible = false;
let requirementFeedback: HTMLElement | null = null;

function legacyMethod(name: string, ...args: any[]): any {
  return getLegacyBridge().methods[name]?.(...args);
}

function extension(filename: string): string {
  return String(filename || "").split(".").pop()?.toLowerCase() || "";
}

function familyForFilename(filename: string): ReferenceFileSource["family"] | null {
  const suffix = extension(filename);
  return FAMILY_BY_EXTENSION[suffix] || (TEXT_EXTENSIONS.has(suffix) ? "text" : null);
}

function isImageFile(file: File): boolean {
  return String(file.type || "").startsWith("image/")
    || /\.(avif|bmp|gif|heic|heif|jpe?g|png|tiff?|webp)$/i.test(file.name || "");
}

export function partitionReferenceDropFiles(files: Iterable<File> | ArrayLike<File>) {
  const result: { images: File[]; referenceFiles: File[]; unsupported: File[] } = {
    images: [], referenceFiles: [], unsupported: [],
  };
  Array.from(files || []).forEach((file) => {
    if (isImageFile(file)) result.images.push(file);
    else if (familyForFilename(file.name)) result.referenceFiles.push(file);
    else result.unsupported.push(file);
  });
  return result;
}

function responsesEnabled(): boolean {
  const authSource = legacyMethod("currentAuthSource") || "codex";
  return authSource === "api"
    ? legacyMethod("currentApiMode") === "responses"
    : legacyMethod("currentCodexMode") === "responses";
}

function renderFormatIcon(target: HTMLElement, filename: string): void {
  target.className = "reference-file-icon";
  target.setAttribute("aria-hidden", "true");
  target.innerHTML = referenceFileIconSvgMarkup(filename);
}

function showResponsesRequirement(): void {
  requirementActionVisible = true;
  legacyMethod("setStatus", translate("referenceFiles.requiresResponses"), "error");
  renderReferenceFiles();
}

function activateResponsesRequirementAction(): void {
  if ((legacyMethod("currentAuthSource") || "codex") === "api") {
    legacyMethod("openApiSettingsModal");
    return;
  }
  legacyMethod("selectCodexMode", "responses");
  requirementActionVisible = false;
  renderReferenceFiles();
  syncReferenceFileAvailability();
  legacyMethod("setStatus", translate("referenceFiles.responsesEnabled"), "ok");
}

function uploadSource(file: File, family: ReferenceFileSource["family"]): ReferenceFileSource {
  const suffix = extension(file.name);
  return {
    kind: "upload",
    file,
    filename: file.name,
    mime_type: file.type || MIME_BY_EXTENSION[suffix] || "application/octet-stream",
    size_bytes: file.size,
    family,
  };
}

function storedSource(item: any): ReferenceFileSource | null {
  const family = item?.family;
  if (!item?.id || !["pdf", "spreadsheet", "document", "text"].includes(family)) return null;
  return {
    kind: "asset",
    id: String(item.id),
    filename: String(item.filename || translate("referenceFiles.missing")),
    mime_type: String(item.mime_type || "application/octet-stream"),
    size_bytes: Number(item.size_bytes || 0),
    family,
    missing: Boolean(item.missing),
  };
}

export function addReferenceFileInput(input: File | ReferenceFileSource | any): boolean {
  if (!responsesEnabled()) {
    showResponsesRequirement();
    return false;
  }
  const state = getState();
  let source: ReferenceFileSource | null = null;
  if (input instanceof File) {
    const family = familyForFilename(input.name);
    if (!family) {
      legacyMethod("setStatus", translate("referenceFiles.errorUnsupported"), "error");
      return false;
    }
    if (state.referenceFiles.some((item: any) => item.kind === "upload" && item.file === input)) return false;
    source = uploadSource(input, family);
  } else {
    source = storedSource(input);
    if (!source) return false;
    if (state.referenceFiles.some((item: any) => item.kind === "asset" && item.id === source?.id)) return false;
  }
  requirementActionVisible = false;
  state.referenceFiles.push(source);
  renderReferenceFiles();
  legacyMethod("updateRequestPreview");
  return true;
}

export function referenceFileUploads(): ReferenceFileSource[] {
  return getState().referenceFiles.filter((source: ReferenceFileSource) => source.kind === "upload" && Boolean(source.file));
}

export function storedReferenceFileInputs(): ReferenceFileSource[] {
  return getState().referenceFiles.filter((source: ReferenceFileSource) => source.kind === "asset" && Boolean(source.id) && !source.missing);
}

export function missingReferenceFileInputs(): ReferenceFileSource[] {
  return getState().referenceFiles.filter((source: ReferenceFileSource) => source.kind === "asset" && Boolean(source.missing));
}

export function clearReferenceFiles(_options: { silent?: boolean } = {}): void {
  getState().referenceFiles = [];
  requirementActionVisible = false;
  renderReferenceFiles();
  legacyMethod("updateRequestPreview");
}

function removeReferenceFile(index: number): void {
  const state = getState();
  if (!Number.isInteger(index) || index < 0 || index >= state.referenceFiles.length) return;
  state.referenceFiles.splice(index, 1);
  renderReferenceFiles();
  legacyMethod("updateRequestPreview");
}

export function renderReferenceFiles(): void {
  const els = getEls();
  const container = els.referenceFileSelection as HTMLElement | null;
  if (!container) return;
  requirementFeedback?.remove();
  requirementFeedback = null;
  container.replaceChildren();
  const sources = getState().referenceFiles as ReferenceFileSource[];
  if (!sources.length && !requirementActionVisible) {
    container.classList.add("hidden");
    legacyMethod("updateImageStripDensity");
    return;
  }
  container.classList.toggle("hidden", !sources.length);
  if (requirementActionVisible) {
    const feedback = document.createElement("div");
    feedback.className = "reference-file-requirement";
    const message = document.createElement("span");
    message.textContent = translate("referenceFiles.requiresResponses");
    const action = document.createElement("button");
    action.type = "button";
    action.className = "ghost-button text-sm";
    action.textContent = (legacyMethod("currentAuthSource") || "codex") === "api"
      ? translate("referenceFiles.openApiSettings")
      : translate("referenceFiles.switchToResponses");
    action.addEventListener("click", activateResponsesRequirementAction);
    feedback.append(message, action);
    els.imageUploaderGrid?.append(feedback);
    requirementFeedback = feedback;
  }
  sources.forEach((source, index) => {
    const tile = document.createElement("div");
    tile.className = `reference-file-thumb thumb reference-file-${source.family}${source.missing ? " is-missing" : ""}`;
    tile.title = source.filename;
    tile.tabIndex = 0;
    tile.setAttribute("aria-label", source.filename);
    const icon = document.createElement("span");
    renderFormatIcon(icon, source.filename);
    const name = document.createElement("span");
    name.className = "reference-file-name";
    name.textContent = source.filename;
    const remove = document.createElement("button");
    remove.type = "button";
    remove.className = "thumb-remove reference-file-remove";
    remove.setAttribute("aria-label", formatTranslation("referenceFiles.remove", { filename: source.filename }));
    remove.title = translate("action.remove");
    remove.innerHTML = '<span class="thumb-remove-icon" aria-hidden="true"><svg viewBox="0 0 16 16" focusable="false"><path d="M4.5 4.5 11.5 11.5M11.5 4.5 4.5 11.5" fill="none" stroke="currentColor" stroke-linecap="round" stroke-width="1.8"/></svg></span>';
    remove.addEventListener("click", () => removeReferenceFile(index));
    tile.append(icon, name, remove);
    container.append(tile);
  });
  legacyMethod("updateImageStripDensity");
  if (requirementActionVisible) {
    els.imageUploaderGrid?.classList.add("has-inputs");
  }
}

export function syncReferenceFileAvailability(): void {
  const supported = responsesEnabled();
  if (supported && requirementActionVisible) {
    requirementActionVisible = false;
    renderReferenceFiles();
    const status = getEls().statusText as HTMLElement | null;
    if (status?.textContent === translate("referenceFiles.requiresResponses")) {
      legacyMethod("setStatus", translate("status.waiting"), "");
    }
  }
}

export function initReferenceFileInputsFeature(): void {
  if (initialized) return;
  initialized = true;
  const els = getEls();
  document.addEventListener("change", (event) => {
    const target = event.target as HTMLElement | null;
    if (target?.matches?.("#generationProviderSelect, #apiMode")) syncReferenceFileAvailability();
  });
  els.authSourceGroup?.addEventListener("click", () => queueMicrotask(syncReferenceFileAvailability));
  document.addEventListener(LOCALE_CHANGE_EVENT, renderReferenceFiles);
  syncReferenceFileAvailability();
  Object.assign(getLegacyBridge().methods, {
    referenceFileUploads,
    storedReferenceFileInputs,
    missingReferenceFileInputs,
    addReferenceFileInput,
    clearReferenceFiles,
    renderReferenceFiles,
    syncReferenceFileAvailability,
  });
}

import { getLegacyBridge } from "./state";
import { translate } from "./i18n";

type Draft = { prompt: string; images: any[]; files: any[]; mode: string };
let baseline = "";
let drafts: Draft[] = [];
function capture(): Draft {
  const { state, methods } = getLegacyBridge();
  return { prompt: methods.getPromptText?.() || "", images: [...(state.images || [])], files: [...(state.referenceFiles || [])], mode: state.mode };
}
function key(draft: Draft): string {
  return JSON.stringify([draft.prompt, draft.images.map(item => [item.id, item.name, item.previewUrl, item.file?.size, item.file?.lastModified]), draft.files.map(item => [item.id, item.filename, item.file?.size]), draft.mode]);
}
export function composerFingerprint(): string { return key(capture()); }
export function markComposerBaseline(prompt?: string): void {
  const draft = capture();
  if (prompt !== undefined) draft.prompt = prompt;
  baseline = key(draft);
}
export function composerHasChanges(): boolean {
  const draft = capture();
  return Boolean(draft.prompt || draft.images.length || draft.files.length) && key(draft) !== baseline;
}
export function preserveComposerDraft(): void {
  if (!composerHasChanges()) return;
  const draft = capture();
  if (key(drafts[drafts.length - 1] || { prompt: "", images: [], files: [], mode: "generate" }) !== key(draft)) drafts.push(draft);
  renderRestoreButton();
}
function renderRestoreButton(): void {
  const button = document.getElementById("restoreComposerDraft") as HTMLButtonElement | null;
  if (button) { button.hidden = !drafts.length; button.textContent = translate("ux.restoreDraft"); }
}
export function restoreComposerDraft(): void {
  const draft = drafts.pop();
  if (!draft) return;
  // Retain the current work too; File objects survive revoked preview URLs.
  preserveComposerDraft();
  const { state, methods } = getLegacyBridge();
  state.taskInputRestoreSeq += 1;
  state.selectedTaskId = null;
  methods.revokeUploadPreviewUrls?.(state.images);
  state.images = draft.images.map(item => item.kind === "upload" && item.file ? { ...item, previewUrl: URL.createObjectURL(item.file) } : { ...item });
  state.referenceFiles = draft.files.map(item => ({ ...item }));
  methods.setPromptText?.(draft.prompt);
  methods.setMode?.(draft.mode);
  methods.clearTaskParameterInspection?.();
  methods.renderImageStrip?.();
  methods.renderReferenceFiles?.();
  methods.renderTasks?.();
  methods.renderPreview?.();
  methods.updatePromptCount?.();
  methods.updateRequestPreview?.();
  methods.setStatus?.(translate("ux.draftRestored"), "ok");
  baseline = "";
  renderRestoreButton();
}
export function initComposerDraft(): void {
  markComposerBaseline();
  document.getElementById("restoreComposerDraft")?.addEventListener("click", restoreComposerDraft);
  window.addEventListener("beforeunload", event => {
    const { state, els } = getLegacyBridge();
    const editingImage = els.imageEditorModal && !els.imageEditorModal.classList.contains("hidden");
    if (!composerHasChanges() && !drafts.length && !state.apiProviderEditingId && !editingImage) return;
    event.preventDefault(); event.returnValue = "";
  });
}

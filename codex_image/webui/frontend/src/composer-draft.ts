import { getLegacyBridge } from "./state";
import { translate } from "./i18n";
import { composerNavigationStore, type ComposerDraft as Draft, type ComposerNavigationSnapshot, type ComposerNavigationStore } from "./composer-navigation-storage";

let baseline = "";
let drafts: Draft[] = [];
function capture(): Draft {
  const { state, methods } = getLegacyBridge();
  return { prompt: methods.getPromptText?.() || "", images: (state.images || []).map((item: any) => ({ ...item })), files: (state.referenceFiles || []).map((item: any) => ({ ...item })), mode: state.mode };
}
function key(draft: Draft): string {
  return JSON.stringify([draft.prompt, draft.images.map(item => [item.id, item.name, item.file ? null : item.previewUrl, item.file?.size, item.file?.lastModified]), draft.files.map(item => [item.id, item.filename, item.file?.size, item.file?.lastModified]), draft.mode]);
}
export function composerFingerprint(): string { return key(capture()); }
export function markComposerSubmitted(fingerprint: string): void {
  drafts = drafts.filter(draft => key(draft) !== fingerprint);
  if (composerFingerprint() === fingerprint) baseline = fingerprint;
  renderRestoreButton();
}
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
  if (button) { button.hidden = !drafts.length; button.textContent = translate("ux.restoreDraft"); button.title = translate("ux.restoreInputsHint"); }
}
export function restoreComposerDraft(): void {
  const draft = drafts.pop();
  if (!draft) return;
  // Retain the current work too; File objects survive revoked preview URLs.
  preserveComposerDraft();
  applyDraft(draft);
  getLegacyBridge().methods.setStatus?.(translate("ux.draftRestored"), "ok");
  baseline = "";
  renderRestoreButton();
}
function applyDraft(draft: Draft): void {
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
}
function hasUnsavedEditor(): boolean {
  const { state, els } = getLegacyBridge();
  return Boolean(state.apiProviderEditingId || (els.imageEditorModal && !els.imageEditorModal.classList.contains("hidden")));
}
function snapshot(): ComposerNavigationSnapshot { return { current: capture(), drafts: [...drafts], baseline }; }
function navigationKey(value = snapshot()): string {
  return JSON.stringify([key(value.current), value.drafts.map(key), value.baseline]);
}
function hasHistoryHandoff(): boolean {
  try {
    return Boolean(localStorage.getItem("codex-image-history-task-reuse-handoff")
      || localStorage.getItem("codex-image-history-reference-handoff"));
  } catch { return false; }
}
export function initComposerDraft(store: ComposerNavigationStore = composerNavigationStore): void {
  drafts = [];
  markComposerBaseline();
  let savedNavigationKey: string | null = null;
  let saving = false;
  let restoring: Promise<void> | null = null;
  getLegacyBridge().methods.restoreComposerNavigationDraft = () => {
    if (!store.hasPending()) return;
    const initialKey = navigationKey();
    restoring = (async () => {
      try {
        const saved = await store.load();
        if (!saved) return;
        const editedWhileLoading = navigationKey() !== initialKey;
        drafts = [...saved.drafts, ...drafts];
        if (hasHistoryHandoff() || editedWhileLoading) {
          if (saved.current.prompt || saved.current.images.length || saved.current.files.length) drafts.push(saved.current);
        } else {
          applyDraft(saved.current);
          baseline = saved.baseline;
        }
        renderRestoreButton();
        await store.clear();
      } catch {
        getLegacyBridge().methods.setStatus?.(translate("ux.historyDraftRestoreFailed"), "error");
      }
    })().finally(() => { restoring = null; });
    return restoring;
  };
  document.getElementById("restoreComposerDraft")?.addEventListener("click", restoreComposerDraft);
  document.addEventListener?.("click", event => {
    if (event.defaultPrevented || event.button !== 0 || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
    const anchor = (event.target as Element | null)?.closest?.("a[href]") as HTMLAnchorElement | null;
    if (!anchor || anchor.target && anchor.target !== "_self" || anchor.hasAttribute("download")) return;
    const url = new URL(anchor.href, window.location.href);
    if (url.origin !== window.location.origin || url.pathname !== "/history" || hasUnsavedEditor()) return;
    const current = capture();
    if (!current.prompt && !current.images.length && !current.files.length && !drafts.length && !store.hasPending()) return;
    event.preventDefault();
    if (saving) return;
    saving = true;
    anchor.setAttribute("aria-busy", "true");
    void (async () => {
      try {
        if (restoring) await restoring;
        let saved: ComposerNavigationSnapshot;
        do {
          saved = snapshot();
          await store.save(saved);
        } while (navigationKey(saved) !== navigationKey());
        if (hasUnsavedEditor()) return;
        savedNavigationKey = navigationKey(saved);
        window.location.assign(url.href);
      } catch {
        savedNavigationKey = null;
        getLegacyBridge().methods.setStatus?.(translate("ux.historyDraftSaveFailed"), "error");
      } finally {
        saving = false;
        anchor.removeAttribute("aria-busy");
      }
    })();
  });
  window.addEventListener("pageshow", event => {
    if (!event.persisted) return;
    savedNavigationKey = null;
    // BFCache already retained the complete in-memory composer.
    restoring = store.clear().catch(() => {}).finally(() => { restoring = null; });
  });
  window.addEventListener("beforeunload", event => {
    if (!hasUnsavedEditor() && savedNavigationKey === navigationKey()) return;
    if (!composerHasChanges() && !drafts.length && !hasUnsavedEditor() && !store.hasPending()) return;
    event.preventDefault(); event.returnValue = "";
  });
}

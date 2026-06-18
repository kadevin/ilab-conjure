import type { WebUIElements } from "./elements";
import type { LegacyMethods } from "./legacy-bridge";
import type { WebUIState } from "./state";

function call(methods: LegacyMethods, name: string, ...args: any[]): any {
  return methods[name]?.(...args);
}

async function handleRefreshButtonClick(methods: LegacyMethods): Promise<void> {
  call(methods, "closePromptPopover");
  await call(methods, "refreshTasks");
}

function isRunTaskShortcut(event: KeyboardEvent): boolean {
  return event.key === "Enter"
    && event.metaKey
    && !event.ctrlKey
    && !event.altKey
    && !event.shiftKey
    && !event.repeat
    && !event.isComposing;
}

function hasOpenShortcutBlockingLayer(): boolean {
  return Boolean(document.querySelector(
    "#promptTemplateDrawer.open, #galleryDrawer.open, .modal-overlay:not(.hidden), .prompt-popover:not(.hidden), .confirm-popover:not(.hidden), .compression-popover:not(.hidden), .task-notification-center:not(.hidden)"
  ));
}

function handleRunTaskShortcut(event: KeyboardEvent, els: WebUIElements, methods: LegacyMethods): void {
  if (!isRunTaskShortcut(event)) return;
  if (hasOpenShortcutBlockingLayer() || els.runButton.disabled) return;
  event.preventDefault();
  void call(methods, "runTask");
}

export function bindWebUIEvents(state: WebUIState, els: WebUIElements, methods: LegacyMethods): void {
  call(methods, "bindShellUiEvents");
  call(methods, "bindFormControlEvents");

  els.clearPromptButton.addEventListener("click", () => {
    call(methods, "setPromptText", "");
    call(methods, "syncGalleryInputsFromPrompt");
    call(methods, "updatePromptCount");
    call(methods, "updateRequestPreview");
  });
  els.quickGalleryRail?.addEventListener("mouseover", (event: Event) => call(methods, "handleQuickGalleryCategoryEvent", event));
  els.quickGalleryRail?.addEventListener("focusin", (event: Event) => call(methods, "handleQuickGalleryCategoryEvent", event));
  els.quickGalleryRail?.addEventListener("click", (event: Event) => call(methods, "handleQuickGalleryCategoryEvent", event));
  els.quickGalleryList?.addEventListener("scroll", () => call(methods, "scheduleQuickGalleryFocusUpdate"));
  els.quickGalleryList?.addEventListener("wheel", (event: Event) => call(methods, "handleQuickGalleryBoundaryWheel", event), { passive: false });
  els.addGalleryCategoryButton?.addEventListener("click", () => call(methods, "createGalleryCategory"));
  els.addToGalleryClose?.addEventListener("click", () => call(methods, "closeAddToGallery"));
  els.addToGalleryModal?.addEventListener("click", (event: Event) => {
    if (event.target === els.addToGalleryModal) call(methods, "closeAddToGallery");
  });
  els.saveToGalleryButton?.addEventListener("click", () => call(methods, "saveUploadToGallery"));
  els.settingsButton?.addEventListener("click", () => call(methods, "openSettingsModal"));
  els.settingsModalClose?.addEventListener("click", () => call(methods, "closeSettingsModal"));
  els.settingsModal?.addEventListener("click", (event: Event) => {
    if (event.target === els.settingsModal) call(methods, "closeSettingsModal");
  });
  els.saveSettingsButton?.addEventListener("click", () => call(methods, "saveSettings"));
  els.authSourceGroup?.addEventListener("click", (event: Event) => call(methods, "handleAuthSourceClick", event));
  els.apiSourceSettingsButton?.addEventListener("click", () => call(methods, "openApiSettingsModal"));
  els.apiDirectSettingsButton?.addEventListener("click", () => call(methods, "openApiSettingsModal"));
  els.apiSettingsModalClose?.addEventListener("click", () => call(methods, "closeApiSettingsModal"));
  els.apiSettingsModal?.addEventListener("click", (event: Event) => {
    if (event.target === els.apiSettingsModal) call(methods, "closeApiSettingsModal");
  });
  els.saveApiSettingsButton?.addEventListener("click", () => call(methods, "saveApiSettings"));
  els.apiProviderQuick?.addEventListener("change", () => {
    call(methods, "readApiSettingsForm");
    state.apiSettings.active_provider_id = els.apiProviderQuick?.value || call(methods, "currentApiProviderId");
    call(methods, "populateApiSettingsForm");
    call(methods, "persistApiSettings");
    call(methods, "renderAuthSource", state.authStatus);
    call(methods, "updateRequestPreview");
  });
  els.apiProvider?.addEventListener("change", () => {
    call(methods, "readApiSettingsForm");
    state.apiSettings.active_provider_id = els.apiProvider?.value || call(methods, "currentApiProviderId");
    call(methods, "populateApiSettingsForm");
    call(methods, "persistApiSettings");
    call(methods, "renderAuthSource", state.authStatus);
    call(methods, "updateRequestPreview");
  });
  els.addApiProviderButton?.addEventListener("click", () => call(methods, "addApiProvider"));
  els.deleteApiProviderButton?.addEventListener("click", () => call(methods, "deleteApiProvider"));
  [els.codexMode, els.apiProviderName, els.apiBaseUrl, els.apiKey, els.apiMode, els.apiImageModel, els.apiImagesConcurrency].filter(Boolean).forEach((element) => {
    element?.addEventListener("input", () => {
      call(methods, "readApiSettingsForm");
      call(methods, "persistApiSettings");
      call(methods, "renderAuthSource", state.authStatus);
      call(methods, "updateModeSpecificSettings");
      call(methods, "updateRequestPreview");
    });
  });
  call(methods, "bindOverlayPopoverEvents");
  els.runButton.addEventListener("click", () => call(methods, "runTask"));
  document.addEventListener("keydown", (event) => handleRunTaskShortcut(event, els, methods));
  els.refreshButton.addEventListener("click", () => {
    void handleRefreshButtonClick(methods);
  });
  call(methods, "bindTaskListControlEvents");
}

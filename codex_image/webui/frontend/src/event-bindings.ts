import type { WebUIElements } from "./elements";
import type { LegacyMethods } from "./legacy-bridge";
import type { WebUIState } from "./state";

function call(methods: LegacyMethods, name: string, ...args: any[]): any {
  return methods[name]?.(...args);
}

async function handleRefreshButtonClick(methods: LegacyMethods): Promise<void> {
  call(methods, "closePromptPopover");
  await window.refreshQueue?.();
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

let systemSettingsBackdropPointerDown = false;

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
  els.systemSettingsModalClose?.addEventListener("click", () => call(methods, "closeSystemSettingsModal"));
  els.systemSettingsModal?.addEventListener("pointerdown", (event: Event) => {
    systemSettingsBackdropPointerDown = event.target === els.systemSettingsModal;
  });
  els.systemSettingsModal?.addEventListener("click", (event: Event) => {
    if (event.target === els.systemSettingsModal && systemSettingsBackdropPointerDown) {
      call(methods, "closeSystemSettingsModal");
    }
    systemSettingsBackdropPointerDown = false;
  });
  els.saveSettingsButton?.addEventListener("click", () => call(methods, "saveSettings"));
  els.authSourceGroup?.addEventListener("click", (event: Event) => call(methods, "handleAuthSourceClick", event));
  els.apiDirectSettingsButton?.addEventListener("click", () => call(methods, "openApiSettingsModal"));
  els.modelFamilyOptions?.addEventListener("click", (event: Event) => {
    const item = (event.target as HTMLElement | null)?.closest?.("[data-family-id]") as HTMLElement | null;
    if (item?.dataset.familyId) call(methods, "selectModelFamily", item.dataset.familyId);
  });
  els.modelFamilyOptions?.addEventListener("keydown", (event: KeyboardEvent) => call(methods, "handleModelFamilyOptionsKeydown", event));
  els.concreteModelSelect?.addEventListener("change", () => call(methods, "selectConcreteModel", els.concreteModelSelect.value));
  els.generationProviderSelect?.addEventListener("change", () => call(methods, "selectGenerationProvider", els.generationProviderSelect.value));
  els.generationProviderSettingsButton?.addEventListener("click", () => call(methods, "openGenerationProviderSettings"));
  els.apiProviderQuick?.addEventListener("change", () => {
    call(methods, "selectApiProvider", els.apiProviderQuick?.value || call(methods, "currentApiProviderId"));
  });
  els.apiProvider?.addEventListener("change", () => {
    call(methods, "selectApiProvider", els.apiProvider?.value || call(methods, "currentApiProviderId"));
  });
  els.apiProviderSearch?.addEventListener("input", () => call(methods, "renderApiProviderList"));
  els.apiProviderList?.addEventListener("click", (event: Event) => {
    const sortButton = (event.target as HTMLElement | null)?.closest?.("[data-api-provider-sort]") as HTMLElement | null;
    if (sortButton) {
      call(methods, "moveApiProvider", sortButton.dataset.apiProviderId, sortButton.dataset.apiProviderSort);
      return;
    }
    const button = (event.target as HTMLElement | null)?.closest?.("[data-api-provider-id]") as HTMLElement | null;
    if (!button) return;
    call(methods, "selectApiProvider", button.dataset.apiProviderId);
  });
  els.editApiProviderButton?.addEventListener("click", () => call(methods, "editApiProvider"));
  els.copyApiProviderButton?.addEventListener("click", () => call(methods, "copyApiProvider"));
  els.addApiProviderButton?.addEventListener("click", () => call(methods, "addApiProvider"));
  els.sortApiProvidersButton?.addEventListener("click", () => call(methods, "toggleApiProviderSortMode"));
  els.deleteApiProviderButton?.addEventListener("click", () => call(methods, "confirmDeleteApiProvider", els.deleteApiProviderButton));
  els.cancelApiProviderEditButton?.addEventListener("click", () => call(methods, "cancelApiProviderEdit"));
  els.saveApiProviderEditButton?.addEventListener("click", () => call(methods, "saveApiProviderEdit"));
  els.addProviderBindingButton?.addEventListener("click", () => call(methods, "addProviderBinding"));
  els.apiProviderBindings?.addEventListener("click", (event: Event) => {
    const button = (event.target as HTMLElement | null)?.closest?.("[data-remove-provider-binding]") as HTMLElement | null;
    if (button?.dataset.removeProviderBinding) call(methods, "removeProviderBinding", button.dataset.removeProviderBinding);
  });
  els.apiProviderBindings?.addEventListener("change", (event: Event) => call(methods, "handleProviderBindingEditorChange", event));
  els.apiKeyRevealButton?.addEventListener("pointerdown", (event: Event) => call(methods, "revealApiKeyWhilePressed", event));
  els.apiKeyRevealButton?.addEventListener("pointerup", () => call(methods, "hideApiKeyReveal"));
  els.apiKeyRevealButton?.addEventListener("pointercancel", () => call(methods, "hideApiKeyReveal"));
  els.apiKeyRevealButton?.addEventListener("pointerleave", () => call(methods, "hideApiKeyReveal"));
  els.apiKeyRevealButton?.addEventListener("blur", () => call(methods, "hideApiKeyReveal"));
  els.apiKeyRevealButton?.addEventListener("keydown", (event: KeyboardEvent) => {
    if (event.key === " " || event.key === "Enter") call(methods, "revealApiKeyWhilePressed", event);
  });
  els.apiKeyRevealButton?.addEventListener("keyup", () => call(methods, "hideApiKeyReveal"));
  els.apiKey?.addEventListener("input", () => call(methods, "updateApiKeyRevealButton"));
  els.apiBaseUrl?.addEventListener("input", () => call(methods, "updateApiRequestEndpointPreview"));
  call(methods, "bindOverlayPopoverEvents");
  els.runButton.addEventListener("click", () => call(methods, "runTask"));
  document.addEventListener("keydown", (event) => handleRunTaskShortcut(event, els, methods));
  els.refreshButton.addEventListener("click", () => {
    void handleRefreshButtonClick(methods);
  });
  call(methods, "bindTaskListControlEvents");
}

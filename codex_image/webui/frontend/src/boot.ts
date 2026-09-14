import type { WebUIElements } from "./elements";
import type { LegacyMethods } from "./legacy-bridge";
import type { WebUIState } from "./state";
import { bindWebUIEvents } from "./event-bindings";

function call(methods: LegacyMethods, name: string, ...args: any[]): any {
  return methods[name]?.(...args);
}

export function bootWebUI(state: WebUIState, els: WebUIElements, methods: LegacyMethods): void {
  bindWebUIEvents(state, els, methods);
  call(methods, "restoreThemePreference");
  call(methods, "restoreSidebarWidth");
  call(methods, "restoreMainModel");
  call(methods, "restoreApiSettings");
  call(methods, "restoreModelSelection");
  call(methods, "syncReferenceFileAvailability");
  call(methods, "refreshColorPalette");
  call(methods, "refreshPromptSnippets");
  call(methods, "refreshPromptTemplates");
  call(methods, "renderGalleryCategoryControls");
  call(methods, "restoreLegacyArchivedTasks");
  call(methods, "restoreExpandedTaskGroupKey");
  call(methods, "setMode", "generate");
  call(methods, "updatePromptCount");
  call(methods, "updateQuantity");
  call(methods, "updateCompression");
  call(methods, "updateSizeFromPreset");
  call(methods, "updateCustomSize");
  call(methods, "restoreOutputSettingsLock");
  call(methods, "renderImageStrip");
  call(methods, "restoreCollectedReferences");
  void call(methods, "restoreHistoryReferenceHandoff");
  void call(methods, "restoreHistoryTaskReuseHandoff");
  call(methods, "refreshSettings");
  call(methods, "refreshApiSettings");
  call(methods, "refreshHealth");
  void call(methods, "refreshGenerationCatalog");
  call(methods, "refreshGallery");
  call(methods, "refreshRecentAssets");
  window.startRealtimeUpdates?.({ migrateLegacyArchives: true });
  void window.refreshQueue?.();
  void Promise.resolve(call(methods, "refreshTasks", { migrateLegacyArchives: true })).catch((error) => {
    console.error(error);
    call(methods, "setStatus", String(error?.message || error), "error");
  });
  call(methods, "startUiClock");
  call(methods, "updateRequestPreview");
  call(methods, "openSystemSettingsFromUrl");
}

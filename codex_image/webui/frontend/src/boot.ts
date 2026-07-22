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
  void call(methods, "restoreHistoryReferenceHandoff");
  void call(methods, "restoreHistoryTaskReuseHandoff");
  call(methods, "refreshSettings");
  call(methods, "refreshApiSettings");
  call(methods, "refreshNetworkEgressSettings");
  call(methods, "refreshHealth");
  call(methods, "refreshGallery");
  call(methods, "refreshRecentAssets");
  const realtimeStarted = window.startRealtimeUpdates?.({ migrateLegacyArchives: true });
  if (!realtimeStarted) {
    void window.refreshQueue?.();
    void call(methods, "refreshTasks", { migrateLegacyArchives: true });
  }
  call(methods, "startUiClock");
  call(methods, "updateRequestPreview");
  call(methods, "openSystemSettingsFromUrl");
}

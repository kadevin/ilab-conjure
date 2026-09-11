import { initOverlayFocus } from "./overlay-focus";
import { initMobileShell } from "./mobile-shell";
import "../legacy-app.js";
import { initApiAdvancedSettingsFeature } from "./api-advanced-settings";
import { initApiSettingsFeature } from "./api-settings";
import { bindSharedTopNavSettingsEvents } from "./event-bindings";
import { initI18nFeature } from "./i18n";
import { initModelCatalogFeature } from "./model-catalog";
import { initLanAccessSettingsFeature } from "./lan-access-settings";
import { initNetworkEgressSettingsFeature } from "./network-egress-settings";
import { initOverlayPopoversFeature } from "./overlay-popovers";
import { initProviderSelectionFeature } from "./provider-selection";
import { initializeQueueFeature } from "./queue";
import { initSegmentedIndicatorFeature } from "./segmented-indicator";
import { initShellUiFeature } from "./shell-ui";
import { getLegacyBridge } from "./state";
import { initStorageSettingsFeature } from "./storage-settings";
import { initSystemSettingsFeature } from "./system-settings";
import { initTaskNotificationsFeature } from "./task-notifications";
import { initThemedSelectFeature } from "./themed-select";
import type { WebUITask } from "./types";

interface HistoryShellOptions {
  selectHistoryTask(taskId: string): Promise<void> | void;
  refreshHistoryTasks?(task?: WebUITask | null): Promise<void> | void;
}

let historyShellInitialized = false;

function noOp(): void {}

function taskHasViewableUpdate(task: WebUITask | null | undefined): boolean {
  const status = String(task?.status || "");
  return ["completed", "failed", "partial_failed"].includes(status)
    || Boolean(task?.output_url)
    || Boolean(task?.output_urls?.length)
    || Boolean(task?.outputs?.length);
}

function isTerminalTask(task: WebUITask | null | undefined): boolean {
  return ["completed", "failed", "partial_failed"].includes(
    String(task?.status || ""),
  );
}

export function initializeHistoryShell(
  options: HistoryShellOptions,
): void {
  if (historyShellInitialized) return;
  historyShellInitialized = true;

  const bridge = getLegacyBridge();
  const methods = bridge.methods;
  Object.assign(methods, {
    syncReferenceFileAvailability: () => {},
    closeGalleryEditPopover: noOp,
    handlePromptDocumentClick: noOp,
    handleGalleryDocumentClick: noOp,
    closeCompressionPopover: noOp,
    handleImageEditorHistoryShortcut: () => false,
    hideMentionSuggest: noOp,
    hideColorSuggest: noOp,
    hidePromptSnippetSuggest: noOp,
    hidePromptSnippetSelectionButton: noOp,
    closePromptSnippetPopover: noOp,
    closeArchiveModal: noOp,
    closeImageEditor: noOp,
    closeGallery: noOp,
    closePromptTemplateDrawer: noOp,
    applyTasksSnapshot: async (tasks: WebUITask[]) => {
      bridge.state.tasks = Array.isArray(tasks) ? tasks : [];
    },
    applyTaskUpdate: async (task: WebUITask | null | undefined) => {
      if (!task?.task_id) return;
      methods.updateTaskInState(task);
      if (isTerminalTask(task)) {
        await options.refreshHistoryTasks?.(task);
      }
    },
    refreshTasks: async () => {
      await options.refreshHistoryTasks?.();
    },
    selectTask: async (taskId: string) => {
      bridge.state.selectedTaskId = String(taskId);
      await options.selectHistoryTask(String(taskId));
    },
    revealActiveTaskGroup: () => {
      window.location.assign("/");
    },
    taskHasViewableUpdate,
    updateDocumentTitle: () => {},
  });

  initShellUiFeature();
  initThemedSelectFeature();
  initI18nFeature();
  initApiSettingsFeature();
  initApiAdvancedSettingsFeature();
  initStorageSettingsFeature();
  initNetworkEgressSettingsFeature();
  initLanAccessSettingsFeature();
  initSystemSettingsFeature();
  initOverlayPopoversFeature();
  initOverlayFocus();
  initTaskNotificationsFeature();
  initProviderSelectionFeature();
  initModelCatalogFeature();
  initializeQueueFeature();
  initSegmentedIndicatorFeature();
  initMobileShell();

  methods.bindShellUiEvents?.();
  bindSharedTopNavSettingsEvents(bridge.els, methods);
  methods.restoreThemePreference?.();
  methods.restoreApiSettings?.();
  methods.restoreModelSelection?.();
  methods.refreshSettings?.();
  methods.refreshApiSettings?.();
  void methods.refreshGenerationCatalog?.();
  methods.openSystemSettingsFromUrl?.();

  const realtimeStarted = window.startRealtimeUpdates?.();
  if (!realtimeStarted) {
    void window.refreshQueue?.();
  }
}

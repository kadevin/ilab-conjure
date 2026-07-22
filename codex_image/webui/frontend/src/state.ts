import type { GenerationCatalog, GenerationSnapshotView, ModelFamilyId, QueueState, TaskNotification, TaskNotificationSettings, WebUITask } from "./types";
import type { WebUIBridge } from "./legacy-bridge";
import type { Locale } from "./i18n/types";

export interface WebUIState {
  [key: string]: any;
  tasks: WebUITask[];
  referenceFiles: any[];
  selectedTaskId: string | null;
  queue: QueueState;
  queueRenderKey: string | null;
  queueRequestSeq: number;
  queueDispatchSyncTimerId: number | null;
  tasksRequestSeq: number;
  realtimeSource: EventSource | null;
  realtimeSnapshotNeedsArchiveMigration: boolean;
  queueDragTaskId: string | null;
  activeTaskGroupCollapsed: boolean;
  expandedTaskGroupKey: string | null;
  taskNotifications: TaskNotification[];
  taskNotificationUnreadCount: number;
  taskNotificationCenterOpen: boolean;
  taskNotificationToastTimerIds: number[];
  taskNotificationSettings: TaskNotificationSettings;
  taskNotificationSeenKeys: Set<string>;
  generationCatalog: GenerationCatalog | null;
  generationCatalogError: string | null;
  selectedFamilyId: ModelFamilyId | null;
  selectedModelId: string | null;
  selectedProviderId: string | null;
  selectedProviderBindingId: string | null;
  lastModelByFamily: Record<string, string>;
  lastProviderByModel: Record<string, string>;
  lastProviderSelectionByModel: Record<string, string>;
  parameterDraftsByModel: Record<string, Record<string, unknown>>;
  parameterDraftVersionsByModel: Record<string, number>;
  parameterValidationErrorsByModel: Record<string, Record<string, string>>;
  inspectedGenerationSnapshot: GenerationSnapshotView | null;
}

export type LegacyBridge = WebUIBridge;

declare global {
  interface Window {
    __codexImageWebUI?: LegacyBridge;
    __codexImageI18n?: {
      applyLocaleToDocument: () => void;
      locale: () => Locale;
      setLocale: (locale: Locale, options?: { persist?: boolean }) => void;
      t: (key: string, locale?: Locale) => string;
    };
    startRealtimeUpdates?: (options?: { migrateLegacyArchives?: boolean }) => boolean;
    closeRealtimeUpdates?: () => void;
    refreshQueue?: () => Promise<void>;
    applyQueueState?: (queue: QueueState | null | undefined) => void;
    applyQueueTasks?: (queue: QueueState | null | undefined) => void;
    updateQueueElapsedDisplays?: () => void;
    openLightbox?: (url: string, urls?: string[], index?: number) => void;
    closeLightbox?: () => void;
    showLightboxImage?: (index: number) => void;
    showPreviousLightboxImage?: () => void;
    showNextLightboxImage?: () => void;
    addToInput?: (url: string) => Promise<void>;
  }
}

export function getLegacyBridge(): LegacyBridge {
  const bridge = window.__codexImageWebUI;
  if (!bridge) {
    throw new Error("WebUI legacy bridge is not initialized");
  }
  return bridge;
}

export function getState(): WebUIState {
  return getLegacyBridge().state;
}

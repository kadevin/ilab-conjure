import type { QueueState, TaskNotification, TaskNotificationSettings, WebUITask } from "./types";
import type { WebUIBridge } from "./legacy-bridge";

export interface WebUIState {
  [key: string]: any;
  tasks: WebUITask[];
  selectedTaskId: string | null;
  queue: QueueState;
  queueRenderKey: string | null;
  queueRequestSeq: number;
  queueDispatchSyncTimerId: number | null;
  tasksRequestSeq: number;
  realtimeSource: EventSource | null;
  realtimeSnapshotNeedsArchiveMigration: boolean;
  queueDragTaskId: string | null;
  expandedTaskGroupKey: string | null;
  taskNotifications: TaskNotification[];
  taskNotificationUnreadCount: number;
  taskNotificationCenterOpen: boolean;
  taskNotificationToastTimerIds: number[];
  taskNotificationSettings: TaskNotificationSettings;
  taskNotificationSeenKeys: Set<string>;
}

export type LegacyBridge = WebUIBridge;

declare global {
  interface Window {
    __codexImageWebUI?: LegacyBridge;
    __codexImageI18n?: {
      applyLocaleToDocument: () => void;
      locale: () => "zh-CN" | "en";
      setLocale: (locale: "zh-CN" | "en", options?: { persist?: boolean }) => void;
      t: (key: string, locale?: "zh-CN" | "en") => string;
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

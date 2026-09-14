import type { WebUIElements } from "./elements";
import type { WebUIState } from "./state";
import type { WebUITask } from "./types";

export type LegacyMethod = (...args: any[]) => any;
export interface LegacyMethods {
  [methodName: string]: LegacyMethod;
  setStatus(message: string, type?: string): void;
  applyTasksSnapshot(
    tasks: WebUITask[],
    options?: {
      migrateLegacyArchives?: boolean;
      requestSeq?: number;
      taskGroups?: Array<{ key: string; count: number; tasks?: WebUITask[] }>;
      sync?: { instance: string; revision: number } | undefined;
    },
  ): Promise<boolean | void>;
  applyTaskUpdate(task: WebUITask | null | undefined): void;
  ensureSelectedTaskDetail(taskId?: string | null): Promise<WebUITask | null> | WebUITask | null;
  notifyTaskUpdate(previousTask: WebUITask | null | undefined, nextTask: WebUITask | null | undefined): void;
  refreshTasks(options?: { migrateLegacyArchives?: boolean }): Promise<boolean | void>;
  updateDocumentTitle(): void;
  updateTaskInState(task: WebUITask | null | undefined): boolean;
  taskHasViewableUpdate(task: WebUITask | null | undefined): boolean;
  markTaskViewed(taskId: string): Promise<void> | void;
  cleanupSessionSelections(): void;
  renderTasks(options?: { preserveScroll?: boolean }): void;
  scheduleLatestTaskNavigationRefresh(): void;
  notifyLatestTaskAvailable(task: WebUITask | null | undefined): void;
  consumeLatestTaskNavigationScrollAnchor(anchor: any): any;
  rememberLatestTaskNavigationBeforeRender(): void;
  renderArchiveButton(): void;
  renderArchiveModal(): void;
  renderPreview(task?: WebUITask | null): void;
  runTask(): Promise<void>;
  openConfirmPopover(
    anchor: Element,
    options: {
      title: string;
      message: string;
      detail?: string;
      confirmText: string;
      onConfirm: () => Promise<void> | void;
    },
  ): void;
  formatTaskCardStatus(task: WebUITask | null | undefined): string;
  formatTaskStatus(task: WebUITask | null | undefined): string;
  taskTotalCount(task: WebUITask | null | undefined): number;
  taskBackendLabel(task: WebUITask | null | undefined): string;
  taskRetryStateText(task: WebUITask | null | undefined): string;
  escapeHtml(value: unknown): string;
  uploadSource(file: File): any;
  gallerySource(item: any): any;
  assetSource(item: any): any;
  imageFileFromUrl(url: string, fallbackName: string): Promise<File>;
  addImageFiles(files: File[], options?: any): void;
  sourcePreviewUrl(source: any): string;
  sourceName(source: any): string;
  isEditableImageSource(source: any): boolean;
  addImages(event: Event): void;
  clearImages(): void;
  updateImageStripDensity(): void;
  revokeUploadPreviewUrl(source: any, options?: any): void;
  revokeUploadPreviewUrls(sources: any): void;
  revokeTaskUploadPreviewUrls(task: any): void;
  addGalleryInput(item: any, options?: any): void;
  galleryInputs(): any[];
  referenceAssetInputs(): any[];
  uploadInputs(): any[];
  missingGalleryInputs(): any[];
  missingReferenceAssetInputs(): any[];
  addReferenceAssetInput(item: any): void;
  collectReferenceOutput(url: string, options?: any): void;
  renderReferenceCollector(): void;
  restoreCollectedReferences(): void;
  addPendingTask(task: WebUITask): void;
  replacePendingTask(pendingTaskId: string, completedTask: WebUITask): void;
  syncPromptGalleryMentionsFromInputs(): void;
  getPromptText(): string;
  setPromptText(value: string): void;
  updatePromptCount(): void;
  renderImageStrip(): void;
  updateRequestPreview(): void;
}

export interface WebUIBridge {
  state: WebUIState;
  els: WebUIElements;
  boot(): void;
  constants: {
    defaultDocumentTitle: string;
  };
  methods: LegacyMethods;
}

export function installLegacyBridge(bridge: WebUIBridge): WebUIBridge {
  window.__codexImageWebUI = bridge;
  return bridge;
}

export function callBridgeMethod(name: string, ...args: any[]): any {
  const method = window.__codexImageWebUI?.methods?.[name];
  if (typeof method !== "function") {
    throw new Error("Legacy bridge method " + name + " is not available");
  }
  return method(...args);
}

export function bindBridgeMethod(name: string, options: { required?: boolean } = {}): LegacyMethod {
  const proxy: LegacyMethod = (...args: any[]) => {
    const method = window.__codexImageWebUI?.methods?.[name];
    if (typeof method !== "function" || method === proxy) {
      if (options.required) {
        throw new Error("Legacy bridge method " + name + " is not initialized");
      }
      return undefined;
    }
    return method(...args);
  };
  return proxy;
}

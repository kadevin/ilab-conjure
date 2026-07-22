import type { WebUIState } from "./state";

export const DEFAULT_GALLERY_CATEGORY_LABELS = {
  portrait: "\u4eba\u50cf",
  character: "\u89d2\u8272",
  product: "\u4ea7\u54c1",
};

export const DEFAULT_GALLERY_CATEGORIES = [
  { id: "portrait", name: "\u4eba\u50cf", prompt_role: "\u4eba\u50cf\u53c2\u8003", order: 10 },
  { id: "character", name: "\u89d2\u8272", prompt_role: "\u89d2\u8272\u53c2\u8003", order: 20 },
  { id: "product", name: "\u4ea7\u54c1", prompt_role: "\u4ea7\u54c1\u53c2\u8003", order: 30 },
];

export const PROMPT_SNIPPETS_ENDPOINT = "/api/prompt-snippets";
export const DEFAULT_API_BASE_URL = "https://api.openai.com/v1";
export const DEFAULT_API_IMAGE_MODEL = "gpt-image-2";
export const DEFAULT_API_MODE = "images";
export const DEFAULT_CODEX_MODE = "images";
export const DEFAULT_API_IMAGES_CONCURRENCY = 4;
export const API_SETTINGS_STORAGE_KEY = "codex-image-api-settings";
export const DEFAULT_DOCUMENT_TITLE = document.title || "iLab CONJURE";
export const SUBMIT_TASK_TIMEOUT_MS = 45000;
export const TASK_CARD_SELECTOR = ".task-card[data-task-id]";
export const TASK_HISTORY_EXPANDED_GROUP_STORAGE_KEY = "codex-image-task-history-expanded-group";
export const PROMPT_TOKEN_PATTERN = /@([^\s@，。,.#~～〜∼˜]+)|#([0-9a-fA-F]{6}|[0-9a-fA-F]{3})(?![0-9a-fA-F])|(?:^|[\s\n，。,.；;：:！？!?、（）()\[\]【】"'“”‘’])([~～〜∼˜]+)([^\s~～〜∼˜@#，。,.；;：:！？!?、（）()\[\]【】"'“”‘’]+)/g;
export const PROMPT_SNIPPET_TRIGGER_PATTERN = /(^|[\s\n，。,.；;：:！？!?、（）()\[\]【】"'“”‘’])([~～〜∼˜]+)([^\s~～〜∼˜@#，。,.；;：:！？!?、（）()\[\]【】"'“”‘’]*)$/;
export const QUICK_GALLERY_WHEEL_COOLDOWN_MS = 220;

export function defaultGalleryCategories() {
  return DEFAULT_GALLERY_CATEGORIES.map((category) => ({ ...category }));
}

export function createDefaultState(): WebUIState {
  return {
  mode: "generate",
  images: [],
  referenceFiles: [],
  tasks: [],
  selectedTaskId: null,
  taskInputRestoreSeq: 0,
  authAvailable: false,
  runTimerId: null,
  runStartedAt: null,
  runFeedbackAction: null,
  uiClockTimerId: null,
  previewRenderKey: null,
  tasksRenderKey: null,
  taskSearchHistoryResultIds: [],
  taskSearchHistoryResultQuery: "",
  taskSearchHistoryRequestSeq: 0,
  pendingTaskId: null,
  galleryItems: [],
  promptSnippets: [],
  promptTemplates: [],
  promptTemplateCategories: [],
  promptTemplateFilter: "all",
  promptTemplateCategory: "",
  promptTemplateQuery: "",
  selectedPromptTemplateId: null,
  recentAssets: [],
  collectedReferences: [],
  galleryCategories: defaultGalleryCategories(),
  activeGalleryCategory: "portrait",
  hoveredGalleryItemId: null,
  quickGalleryFocusItemId: null,
  colorPalette: {
    version: 1,
    favorites: [
      { name: "\u767d\u8272", hex: "#FFFFFF", order: 10 },
      { name: "\u9ed1\u8272", hex: "#111111", order: 20 },
      { name: "\u6696\u7c73\u8272", hex: "#F6E8D8", order: 30 },
      { name: "\u6d45\u7eff", hex: "#E6F0EC", order: 40 },
      { name: "\u54c1\u724c\u7eff", hex: "#457B66", order: 50 },
      { name: "\u6843\u6a59", hex: "#F4B183", order: 60 },
      { name: "\u6d45\u84dd", hex: "#B7D7F0", order: 70 },
      { name: "\u6d45\u7c89", hex: "#F8D7DA", order: 80 },
    ],
    recent_colors: [],
    recent_limit: 6,
  },
  colorPaletteManageMode: false,
  selectedColorCode: "#FFFFFF",
  activeColorRange: null,
  activeColorChip: null,
  activePromptSnippetRange: null,
  activePromptSnippetChip: null,
  promptSnippetSelectionRange: null,
  promptSnippetSelectionText: "",
  addToGalleryIndex: null,
  authStatus: null,
  pendingAuthSource: null,
  customSizeMode: null,
  customSizeTransitionSeq: 0,
  customAspectRatioLocked: false,
  customAspectRatioValue: null,
  customAspectRatioSource: "manual",
  galleryGridTransitionSeq: 0,
  galleryGridTransitionTimerId: null,
  queue: { waiting: [], running: [], summary: { waiting_count: 0, running_count: 0, channel_count: 0 } },
  queueRenderKey: null,
  queueRequestSeq: 0,
  queueDispatchSyncTimerId: null,
  taskViewedRequestIds: new Set(),
  tasksRequestSeq: 0,
  realtimeSource: null,
  realtimeSnapshotNeedsArchiveMigration: false,
  queueDragTaskId: null,
  activeTaskGroupCollapsed: false,
  expandedTaskGroupKey: null,
  expandedTaskGroupAnimationPending: false,
  taskNotifications: [],
  taskNotificationUnreadCount: 0,
  taskNotificationCenterOpen: false,
  taskNotificationToastTimerIds: [],
  taskNotificationSettings: { inApp: true, system: false },
  taskNotificationSeenKeys: new Set(),
  generationCatalog: null,
  generationCatalogError: null,
  selectedFamilyId: null,
  selectedModelId: null,
  selectedProviderId: null,
  selectedProviderBindingId: null,
  lastModelByFamily: {},
  lastProviderByModel: {},
  lastProviderSelectionByModel: {},
  parameterDraftsByModel: {},
  parameterDraftVersionsByModel: {},
  parameterValidationErrorsByModel: {},
  inspectedGenerationSnapshot: null,
  draggedPromptChip: null,
  legacyArchivedTaskIds: [],
  batchMode: false,
  batchSelectedTaskIds: [],
  batchSelectionAnchorTaskId: null,
  batchSelectionDrag: null,
  suppressTaskClickAfterDrag: false,
  sidebarResize: null,
  themePreference: "system",
  themeSystemQuery: null,
  apiSettings: {
    codex_mode: DEFAULT_CODEX_MODE,
    active_provider_id: "default",
    providers: [{
      id: "default",
      name: "Default",
      base_url: DEFAULT_API_BASE_URL,
      api_key: "",
      image_model: DEFAULT_API_IMAGE_MODEL,
      api_mode: DEFAULT_API_MODE,
      images_concurrency: DEFAULT_API_IMAGES_CONCURRENCY,
    }],
  },
  apiSettingsSaveTimerId: null,
  mainModelComboboxOpen: false,
  mainModelOptionIndex: 0,
  mainModelShowAllOptions: false,
  } as WebUIState;
}

export const ARCHIVED_TASKS_STORAGE_KEY = "codex-image-archived-task-ids";

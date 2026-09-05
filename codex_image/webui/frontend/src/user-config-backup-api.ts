export const USER_CONFIG_SECTIONS = ["chips", "gallery", "templates", "settings"] as const;
export const USER_CONFIG_RESTORE_CHUNK_BYTES = 8 * 1024 * 1024;
export const USER_CONFIG_TRANSFER_STORAGE_KEY = "ilab-user-config-transfer";

export type UserConfigSection = typeof USER_CONFIG_SECTIONS[number];
export type UserConfigRestoreGroup =
  | "colors" | "prompt_snippets" | "gallery_items"
  | "prompt_templates" | "settings";
export type UserConfigRestoreMode = "incremental" | "replace";
export type UserConfigBackupStatus =
  | "queued" | "planning" | "packing" | "ready"
  | "failed" | "cancelled" | "expired" | "interrupted";
export type UserConfigRestoreStatus =
  | "uploading" | "uploaded" | "validating" | "validated"
  | "restoring" | "restored" | "failed" | "cancelled" | "interrupted";

export interface UserConfigClientPreferences {
  theme: "system" | "light" | "dark";
  notifications: { in_app: boolean; system: boolean };
}

export interface UserConfigSectionSummary {
  section: UserConfigSection;
  item_count: number;
  size_bytes: number;
  warnings: string[];
}

export interface UserConfigBackupRequest {
  sections: UserConfigSection[];
  include_api_keys: boolean;
  client_preferences: UserConfigClientPreferences | null;
}

export interface UserConfigBackupJob {
  job_id: string;
  status: UserConfigBackupStatus;
  created_at: string;
  updated_at: string;
  sections: UserConfigSection[];
  total_members: number;
  completed_members: number;
  total_bytes: number;
  completed_bytes: number;
  warnings: string[];
  filename: string | null;
  download_url: string | null;
  error_code: string | null;
}

export interface UserConfigBackupActionPriority {
  create: "primary" | "secondary";
  download: "primary" | "secondary";
}

export interface UserConfigRestoreSession {
  session_id: string;
  filename: string;
  size_bytes: number;
  uploaded_bytes: number;
  status: UserConfigRestoreStatus;
  created_at: string;
  updated_at: string;
  archive_sha256?: string | null;
  error_code?: string | null;
}

export interface UserConfigRestoreSectionPreview {
  section: UserConfigSection;
  archive_count: number;
  identical_count: number;
  conflicts: number;
  missing_assets: number;
  replace_existing_count: number;
  estimated_write_bytes: number;
  warnings: string[];
  current_fingerprint: string;
  groups: UserConfigRestoreGroupPreview[];
}

export interface UserConfigRestoreGroupPreview {
  group: UserConfigRestoreGroup;
  archive_count: number;
  current_count: number;
}

export interface UserConfigRestorePreview {
  session_id: string;
  archive_sha256: string;
  preview_revision: string;
  format_version: number;
  restorable: boolean;
  contains_secrets: boolean;
  sections: UserConfigRestoreSectionPreview[];
  path_fields: Record<string, string>;
  keyed_provider_retention_count: number;
  gallery_history_reference_impact: number;
  warnings: string[];
}

export interface UserConfigSectionRestoreStats {
  added: number;
  replaced: number;
  skipped: number;
  recovery_copies: number;
  warnings: string[];
}

export interface UserConfigRestoreResult {
  session_id: string;
  status: "restored";
  sections: UserConfigSection[];
  mode: UserConfigRestoreMode;
  section_stats: Partial<Record<UserConfigSection, UserConfigSectionRestoreStats>>;
  client_preferences: UserConfigClientPreferences | null;
  restart_required: boolean;
}

export interface UserConfigRestoreSnapshot {
  session: UserConfigRestoreSession;
  preview: UserConfigRestorePreview | null;
  result: UserConfigRestoreResult | null;
}

export interface ReplacementConfirmationState {
  archiveSha256: string;
  sections: UserConfigSection[];
  mode: UserConfigRestoreMode;
  acknowledged: boolean;
}

export interface EmptyUserConfigReplacementGroup {
  section: UserConfigSection;
  group: UserConfigRestoreGroup;
  archiveCount: number;
  currentCount: number;
}

type FetchLike = (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>;
type StorageLike = Pick<Storage, "getItem" | "setItem" | "removeItem">;
type TimerHandle = unknown;
type AnchorLike = { href: string; hidden: boolean; click(): void; remove(): void };
type DocumentLike = {
  createElement(tag: "a"): AnchorLike;
  body?: { appendChild(node: AnchorLike): unknown } | null;
};

export interface UserConfigRequestOptions {
  fetch?: FetchLike;
  signal?: AbortSignal;
}

export interface UploadUserConfigRestoreOptions extends UserConfigRequestOptions {
  onProgress?: (uploadedBytes: number, totalBytes: number) => void;
}

export interface UserConfigTransferControllerOptions {
  fetch?: FetchLike;
  storage?: StorageLike | null;
  setTimeout?: (callback: () => void, delay: number) => TimerHandle;
  clearTimeout?: (handle: TimerHandle) => void;
  onBackupStatus?: (job: UserConfigBackupJob) => void;
  onRestoreStatus?: (snapshot: UserConfigRestoreSnapshot) => void;
  onError?: (error: UserConfigTransferApiError) => void;
}

export class UserConfigTransferApiError extends Error {
  readonly code: string;
  readonly status: number;

  constructor(code: string, status: number) {
    super(code);
    this.name = "UserConfigTransferApiError";
    this.code = code;
    this.status = status;
  }
}

export function userConfigBackupStatusMessageKey(job: UserConfigBackupJob): string {
  if (job.status === "failed" && job.error_code) return job.error_code;
  return `userConfigBackup.status.${job.status}`;
}

export function userConfigBackupActionPriority(
  status: UserConfigBackupStatus | null,
): UserConfigBackupActionPriority {
  if (status === "ready") {
    return { create: "secondary", download: "primary" };
  }
  return { create: "primary", download: "secondary" };
}

export function emptyUserConfigReplacementGroups(
  preview: UserConfigRestorePreview,
  sections: readonly UserConfigSection[],
): EmptyUserConfigReplacementGroup[] {
  const selected = new Set(sections);
  return preview.sections.flatMap((section) => {
    if (!selected.has(section.section)) return [];
    return section.groups
      .filter((group) => group.archive_count === 0 && group.current_count > 0)
      .map((group) => ({
        section: section.section,
        group: group.group,
        archiveCount: group.archive_count,
        currentCount: group.current_count,
      }));
  });
}

function currentFetch(): FetchLike {
  if (typeof globalThis.fetch !== "function") throw new Error("user_config_transfer_fetch_unavailable");
  return globalThis.fetch.bind(globalThis);
}

function currentStorage(): StorageLike | null {
  try { return globalThis.sessionStorage; } catch { return null; }
}

function currentDocument(): DocumentLike | null {
  try { return typeof document === "undefined" ? null : document as unknown as DocumentLike; } catch { return null; }
}

function normalizeSections(sections: readonly UserConfigSection[]): UserConfigSection[] {
  const unique: UserConfigSection[] = [];
  for (const section of sections) {
    if (!USER_CONFIG_SECTIONS.includes(section) || unique.includes(section)) continue;
    unique.push(section);
  }
  if (!unique.length || sections.some((section) => !USER_CONFIG_SECTIONS.includes(section))) {
    throw new Error("user_config_backup_sections_invalid");
  }
  return unique;
}

export function buildUserConfigBackupRequest(
  sections: readonly UserConfigSection[],
  includeApiKeys: boolean,
  clientPreferences: UserConfigClientPreferences,
): UserConfigBackupRequest {
  const normalized = normalizeSections(sections);
  const settingsSelected = normalized.includes("settings");
  return {
    sections: normalized,
    include_api_keys: settingsSelected && includeApiKeys,
    client_preferences: settingsSelected ? clientPreferences : null,
  };
}

export function createReplacementConfirmation(
  archiveSha256: string,
  sections: readonly UserConfigSection[],
  mode: UserConfigRestoreMode,
): ReplacementConfirmationState {
  return { archiveSha256, sections: normalizeSections(sections), mode, acknowledged: false };
}

export function updateReplacementConfirmation(
  current: ReplacementConfirmationState,
  patch: Partial<Pick<ReplacementConfirmationState, "archiveSha256" | "sections" | "mode" | "acknowledged">>,
): ReplacementConfirmationState {
  const sections = patch.sections ? normalizeSections(patch.sections) : [...current.sections];
  const archiveSha256 = patch.archiveSha256 ?? current.archiveSha256;
  const mode = patch.mode ?? current.mode;
  const contractChanged = archiveSha256 !== current.archiveSha256
    || mode !== current.mode
    || sections.join("\0") !== current.sections.join("\0");
  return {
    archiveSha256,
    sections,
    mode,
    acknowledged: contractChanged ? false : (patch.acknowledged ?? current.acknowledged),
  };
}

export function buildUserConfigRestoreRequest(
  confirmation: ReplacementConfirmationState,
  previewRevision: string,
): {
  sections: UserConfigSection[];
  mode: UserConfigRestoreMode;
  archive_sha256: string;
  preview_revision: string;
  confirm_replace: boolean;
} | null {
  if (confirmation.mode === "replace" && !confirmation.acknowledged) return null;
  return {
    sections: normalizeSections(confirmation.sections),
    mode: confirmation.mode,
    archive_sha256: confirmation.archiveSha256,
    preview_revision: previewRevision,
    confirm_replace: confirmation.mode === "replace" && confirmation.acknowledged,
  };
}

async function safeApiError(response: Response): Promise<UserConfigTransferApiError> {
  let code = "user_config_transfer_request_failed";
  try {
    const payload: unknown = await response.json();
    const detail = payload && typeof payload === "object"
      ? (payload as Record<string, unknown>).detail
      : null;
    const candidate = detail && typeof detail === "object"
      ? (detail as Record<string, unknown>).code
      : null;
    if (typeof candidate === "string" && /^user_config_(?:backup|restore)_[a-z0-9_]{1,96}$/.test(candidate)) {
      code = candidate;
    }
  } catch {
    // Unknown response bodies are not exposed to the interface.
  }
  return new UserConfigTransferApiError(code, response.status);
}

async function requestJson<T>(url: string, init: RequestInit, fetchFn: FetchLike): Promise<T> {
  const response = await fetchFn(url, init);
  if (!response.ok) throw await safeApiError(response);
  return await response.json() as T;
}

function withSignal(init: RequestInit, signal?: AbortSignal): RequestInit {
  return signal ? { ...init, signal } : init;
}

export async function readUserConfigSummary(options: UserConfigRequestOptions = {}): Promise<UserConfigSectionSummary[]> {
  const payload = await requestJson<{ sections: UserConfigSectionSummary[] }>(
    "/api/user-config-backups/summary", withSignal({ method: "GET" }, options.signal), options.fetch ?? currentFetch(),
  );
  return payload.sections;
}

export async function createUserConfigBackup(
  request: UserConfigBackupRequest,
  options: UserConfigRequestOptions = {},
): Promise<UserConfigBackupJob> {
  const payload = await requestJson<{ job: UserConfigBackupJob }>(
    "/api/user-config-backups",
    withSignal({
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(request),
    }, options.signal),
    options.fetch ?? currentFetch(),
  );
  return payload.job;
}

export async function getUserConfigBackup(jobId: string, options: UserConfigRequestOptions = {}): Promise<UserConfigBackupJob> {
  const payload = await requestJson<{ job: UserConfigBackupJob }>(
    `/api/user-config-backups/${encodeURIComponent(jobId)}`,
    withSignal({ method: "GET" }, options.signal), options.fetch ?? currentFetch(),
  );
  return payload.job;
}

export async function cancelUserConfigBackup(jobId: string, options: UserConfigRequestOptions = {}): Promise<UserConfigBackupJob> {
  const payload = await requestJson<{ job: UserConfigBackupJob }>(
    `/api/user-config-backups/${encodeURIComponent(jobId)}`,
    withSignal({ method: "DELETE" }, options.signal), options.fetch ?? currentFetch(),
  );
  return payload.job;
}

export function directDownloadUserConfigBackup(
  downloadUrl: string,
  documentLike: DocumentLike | null = currentDocument(),
): void {
  if (!documentLike) throw new Error("user_config_backup_document_unavailable");
  const anchor = documentLike.createElement("a");
  anchor.href = downloadUrl;
  anchor.hidden = true;
  documentLike.body?.appendChild(anchor);
  try { anchor.click(); } finally { anchor.remove(); }
}

export async function createUserConfigRestore(
  file: Pick<File, "name" | "size">,
  options: UserConfigRequestOptions = {},
): Promise<{ session: UserConfigRestoreSession; upload_chunk_bytes: number }> {
  return requestJson(
    "/api/user-config-restores",
    withSignal({
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ filename: file.name, size_bytes: file.size }),
    }, options.signal),
    options.fetch ?? currentFetch(),
  );
}

async function sha256Hex(blob: Blob): Promise<string> {
  const digest = await globalThis.crypto.subtle.digest("SHA-256", await blob.arrayBuffer());
  return Array.from(new Uint8Array(digest), (value) => value.toString(16).padStart(2, "0")).join("");
}

export async function uploadUserConfigRestore(
  file: Blob,
  upload: Pick<UserConfigRestoreSession, "session_id"> & { upload_chunk_bytes?: number },
  options: UploadUserConfigRestoreOptions = {},
): Promise<UserConfigRestoreSession> {
  const fetchFn = options.fetch ?? currentFetch();
  const chunkBytes = upload.upload_chunk_bytes ?? USER_CONFIG_RESTORE_CHUNK_BYTES;
  let current: UserConfigRestoreSession | null = null;
  for (let offset = 0; offset < file.size; offset += chunkBytes) {
    const chunk = file.slice(offset, Math.min(file.size, offset + chunkBytes));
    const payload = await requestJson<{ session: UserConfigRestoreSession }>(
      `/api/user-config-restores/${encodeURIComponent(upload.session_id)}/chunks`,
      withSignal({
        method: "PUT",
        headers: {
          "content-type": "application/octet-stream",
          "x-upload-offset": String(offset),
          "x-chunk-sha256": await sha256Hex(chunk),
        },
        body: chunk,
      }, options.signal),
      fetchFn,
    );
    current = payload.session;
    options.onProgress?.(current.uploaded_bytes, file.size);
  }
  if (!current) throw new Error("user_config_restore_empty_file");
  return current;
}

export async function validateUserConfigRestore(sessionId: string, options: UserConfigRequestOptions = {}): Promise<UserConfigRestorePreview> {
  const payload = await requestJson<{ preview: UserConfigRestorePreview }>(
    `/api/user-config-restores/${encodeURIComponent(sessionId)}/validate`,
    withSignal({ method: "POST" }, options.signal), options.fetch ?? currentFetch(),
  );
  return payload.preview;
}

export async function startUserConfigRestore(
  sessionId: string,
  request: NonNullable<ReturnType<typeof buildUserConfigRestoreRequest>>,
  options: UserConfigRequestOptions = {},
): Promise<UserConfigRestoreResult> {
  const payload = await requestJson<{ result: UserConfigRestoreResult }>(
    `/api/user-config-restores/${encodeURIComponent(sessionId)}/restore`,
    withSignal({
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(request),
    }, options.signal),
    options.fetch ?? currentFetch(),
  );
  return payload.result;
}

export async function getUserConfigRestore(sessionId: string, options: UserConfigRequestOptions = {}): Promise<UserConfigRestoreSnapshot> {
  return requestJson(
    `/api/user-config-restores/${encodeURIComponent(sessionId)}`,
    withSignal({ method: "GET" }, options.signal), options.fetch ?? currentFetch(),
  );
}

export async function cancelUserConfigRestore(sessionId: string, options: UserConfigRequestOptions = {}): Promise<boolean> {
  const payload = await requestJson<{ cancelled: boolean }>(
    `/api/user-config-restores/${encodeURIComponent(sessionId)}`,
    withSignal({ method: "DELETE" }, options.signal), options.fetch ?? currentFetch(),
  );
  return payload.cancelled;
}

const BACKUP_TERMINAL = new Set<UserConfigBackupStatus>(["ready", "failed", "cancelled", "expired", "interrupted"]);
const RESTORE_TERMINAL = new Set<UserConfigRestoreStatus>(["restored", "failed", "cancelled", "interrupted"]);

function writeStoredIds(storage: StorageLike | null, backupJobId: string | null, restoreSessionId: string | null): void {
  try {
    storage?.setItem(USER_CONFIG_TRANSFER_STORAGE_KEY, JSON.stringify({ version: 1, backupJobId, restoreSessionId }));
  } catch {
    // In-memory operation remains available when session storage is restricted.
  }
}

function readStoredIds(storage: StorageLike | null): { backupJobId: string | null; restoreSessionId: string | null } {
  if (!storage) return { backupJobId: null, restoreSessionId: null };
  try {
    const raw = storage.getItem(USER_CONFIG_TRANSFER_STORAGE_KEY);
    const parsed: unknown = raw ? JSON.parse(raw) : null;
    if (!parsed || typeof parsed !== "object") throw new Error("invalid");
    const record = parsed as Record<string, unknown>;
    const validId = (value: unknown) => value === null || (typeof value === "string" && /^[0-9a-f]{32}$/.test(value));
    if (record.version !== 1 || !validId(record.backupJobId) || !validId(record.restoreSessionId)) throw new Error("invalid");
    return {
      backupJobId: record.backupJobId as string | null,
      restoreSessionId: record.restoreSessionId as string | null,
    };
  } catch {
    try { storage.removeItem(USER_CONFIG_TRANSFER_STORAGE_KEY); } catch { /* ignored */ }
    return { backupJobId: null, restoreSessionId: null };
  }
}

export function createUserConfigTransferController(options: UserConfigTransferControllerOptions = {}) {
  const fetchFn = options.fetch ?? currentFetch();
  const storage = options.storage === undefined ? currentStorage() : options.storage;
  const setTimeoutFn = options.setTimeout ?? ((callback, delay) => globalThis.setTimeout(callback, delay));
  const clearTimeoutFn = options.clearTimeout ?? ((handle) => globalThis.clearTimeout(handle as ReturnType<typeof setTimeout>));
  let backupJobId: string | null = null;
  let restoreSessionId: string | null = null;
  let timer: TimerHandle | null = null;
  let disposed = false;
  let generation = 0;
  let delay = 750;

  const persist = () => writeStoredIds(storage, backupJobId, restoreSessionId);
  const clearTimer = () => {
    if (timer !== null) clearTimeoutFn(timer);
    timer = null;
  };
  const stableError = (error: unknown) => error instanceof UserConfigTransferApiError
    ? error
    : new UserConfigTransferApiError("user_config_transfer_network_error", 0);
  const schedule = (token: number, poll: () => Promise<void>) => {
    if (disposed || token !== generation || timer !== null) return;
    timer = setTimeoutFn(async () => {
      timer = null;
      if (!disposed && token === generation) await poll();
    }, delay);
    delay = Math.min(2500, Math.round(delay * 1.5));
  };
  const pollBackup = async (token: number): Promise<void> => {
    if (!backupJobId || disposed || token !== generation) return;
    try {
      const job = await getUserConfigBackup(backupJobId, { fetch: fetchFn });
      if (disposed || token !== generation) return;
      options.onBackupStatus?.(job);
      if (!BACKUP_TERMINAL.has(job.status)) schedule(token, () => pollBackup(token));
    } catch (error) {
      options.onError?.(stableError(error));
      if (!disposed && token === generation) schedule(token, () => pollBackup(token));
    }
  };
  const pollRestore = async (token: number): Promise<void> => {
    if (!restoreSessionId || disposed || token !== generation) return;
    try {
      const snapshot = await getUserConfigRestore(restoreSessionId, { fetch: fetchFn });
      if (disposed || token !== generation) return;
      options.onRestoreStatus?.(snapshot);
      if (!RESTORE_TERMINAL.has(snapshot.session.status)) schedule(token, () => pollRestore(token));
    } catch (error) {
      options.onError?.(stableError(error));
      if (!disposed && token === generation) schedule(token, () => pollRestore(token));
    }
  };

  return {
    async resume(): Promise<void> {
      generation += 1;
      disposed = false;
      clearTimer();
      delay = 750;
      const stored = readStoredIds(storage);
      backupJobId = stored.backupJobId;
      restoreSessionId = stored.restoreSessionId;
      const token = generation;
      if (restoreSessionId) await pollRestore(token);
      else if (backupJobId) await pollBackup(token);
    },
    async startBackup(request: UserConfigBackupRequest): Promise<UserConfigBackupJob> {
      generation += 1;
      disposed = false;
      clearTimer();
      delay = 750;
      const token = generation;
      const job = await createUserConfigBackup(request, { fetch: fetchFn });
      if (token !== generation || disposed) return job;
      backupJobId = job.job_id;
      persist();
      options.onBackupStatus?.(job);
      if (!BACKUP_TERMINAL.has(job.status)) schedule(token, () => pollBackup(token));
      return job;
    },
    trackRestore(sessionId: string): void {
      generation += 1;
      disposed = false;
      clearTimer();
      delay = 750;
      restoreSessionId = sessionId;
      persist();
      const token = generation;
      schedule(token, () => pollRestore(token));
    },
    clearBackup(): void { backupJobId = null; if (!restoreSessionId) clearTimer(); persist(); },
    clearRestore(): void { restoreSessionId = null; if (!backupJobId) clearTimer(); persist(); },
    activeBackupJobId: () => backupJobId,
    activeRestoreSessionId: () => restoreSessionId,
    dispose(): void { disposed = true; generation += 1; clearTimer(); },
  };
}

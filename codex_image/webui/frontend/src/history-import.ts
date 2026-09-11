import { sha256Hex } from "./sha256";

export type HistoryImportStatus =
  | "uploading"
  | "uploaded"
  | "validated"
  | "restoring"
  | "restored"
  | "failed"
  | "interrupted";

export type HistoryImportPhase =
  | "idle"
  | "creating"
  | "uploading"
  | "validating"
  | "validated"
  | "restoring"
  | "restored"
  | "failed"
  | "interrupted"
  | "cancelled";

export interface HistoryImportSession {
  session_id: string;
  filename: string;
  size_bytes: number;
  uploaded_bytes: number;
  status: HistoryImportStatus;
  created_at?: string;
  updated_at?: string;
  whole_file_sha256?: string | null;
  error_code?: string | null;
  upload_chunk_bytes?: number;
}

export interface HistoryImportTaskResult {
  task_id: string;
  classification: string;
  reason?: string | null;
}

export interface HistoryImportPreview {
  session_id: string;
  whole_file_sha256?: string;
  restorable: HistoryImportTaskResult[];
  duplicate?: HistoryImportTaskResult[];
  conflict?: HistoryImportTaskResult[];
  invalid?: HistoryImportTaskResult[];
}

export interface HistoryImportResult {
  restored: HistoryImportTaskResult[];
  duplicates?: HistoryImportTaskResult[];
  conflicts?: HistoryImportTaskResult[];
  invalid?: HistoryImportTaskResult[];
  failed: HistoryImportTaskResult[];
  thumbnail_warnings?: HistoryImportTaskResult[];
  cleanup_warnings: HistoryImportTaskResult[];
}

export interface HistoryImportSnapshot extends HistoryImportSession {
  result: HistoryImportResult | null;
}

type FetchLike = (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>;
type StorageLike = Pick<Storage, "getItem" | "setItem" | "removeItem">;
type CryptoLike = Pick<Crypto, "subtle">;

export interface HistoryImportRequestOptions {
  fetch?: FetchLike;
  signal?: AbortSignal | undefined;
}

export interface HistoryImportUploadOptions extends HistoryImportRequestOptions {
  crypto?: CryptoLike;
  onProgress?: ((uploadedBytes: number, totalBytes: number) => void) | undefined;
  onUploadComplete?: (() => void) | undefined;
}

export interface HistoryImportControllerOptions {
  fetch?: FetchLike;
  storage?: StorageLike | null;
  crypto?: CryptoLike;
  onPhase?: (phase: HistoryImportPhase) => void;
  onProgress?: (uploadedBytes: number, totalBytes: number) => void;
}

export const HISTORY_IMPORT_STORAGE_KEY = "ilab-history-backup-import";
export const DEFAULT_HISTORY_IMPORT_CHUNK_BYTES = 8 * 1024 * 1024;

export class HistoryImportApiError extends Error {
  readonly code: string;
  readonly status: number;

  constructor(code: string, message: string, status: number) {
    super(message);
    this.name = "HistoryImportApiError";
    this.code = code;
    this.status = status;
  }
}

function currentFetch(): FetchLike {
  const value = globalThis.fetch;
  if (typeof value !== "function") throw new Error("history_import_fetch_unavailable");
  return value.bind(globalThis);
}

function currentStorage(): StorageLike | null {
  try { return globalThis.sessionStorage; } catch { return null; }
}

async function apiError(response: Response): Promise<HistoryImportApiError> {
  let code = "backup_request_failed";
  let message = code;
  try {
    const payload: unknown = await response.json();
    if (payload && typeof payload === "object") {
      const detail = (payload as Record<string, unknown>).detail;
      if (detail && typeof detail === "object") {
        const record = detail as Record<string, unknown>;
        if (typeof record.code === "string" && /^[a-z][a-z0-9_]{2,127}$/.test(record.code)) {
          code = record.code;
          message = typeof record.message === "string" && record.message === code
            ? record.message
            : code;
        }
      }
    }
  } catch {
    // Unknown bodies are intentionally not copied into the public error.
  }
  return new HistoryImportApiError(code, message, response.status);
}

async function requestJson<T>(url: string, init: RequestInit, fetchFn: FetchLike): Promise<T> {
  const response = await fetchFn(url, init);
  if (!response.ok) throw await apiError(response);
  return await response.json() as T;
}

function withSignal(init: RequestInit, signal: AbortSignal | undefined): RequestInit {
  return signal ? { ...init, signal } : init;
}

export async function createHistoryImport(
  filename: string,
  sizeBytes: number,
  options: HistoryImportRequestOptions = {},
): Promise<HistoryImportSession> {
  const session = await requestJson<HistoryImportSession>(
    "/api/task-history/backup-imports",
    withSignal({
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ filename, size_bytes: sizeBytes }),
    }, options.signal),
    options.fetch ?? currentFetch(),
  );
  return {
    ...session,
    upload_chunk_bytes: positiveChunkSize(session.upload_chunk_bytes),
  };
}

export async function getHistoryImport(
  sessionId: string,
  options: HistoryImportRequestOptions = {},
): Promise<HistoryImportSnapshot> {
  const payload = await requestJson<unknown>(
    `/api/task-history/backup-imports/${encodeURIComponent(sessionId)}`,
    withSignal({ method: "GET" }, options.signal),
    options.fetch ?? currentFetch(),
  );
  return parseHistoryImportSnapshot(payload);
}

export async function appendHistoryImportChunk(
  sessionId: string,
  offset: number,
  bytes: ArrayBuffer,
  sha256: string,
  options: HistoryImportRequestOptions = {},
): Promise<HistoryImportSession> {
  return requestJson<HistoryImportSession>(
    `/api/task-history/backup-imports/${encodeURIComponent(sessionId)}/chunks`,
    withSignal({
      method: "PUT",
      headers: {
        "x-chunk-offset": String(offset),
        "x-chunk-sha256": sha256,
      },
      body: bytes,
    }, options.signal),
    options.fetch ?? currentFetch(),
  );
}

export async function validateHistoryImport(
  sessionId: string,
  options: HistoryImportRequestOptions = {},
): Promise<HistoryImportPreview> {
  return requestJson<HistoryImportPreview>(
    `/api/task-history/backup-imports/${encodeURIComponent(sessionId)}/validate`,
    withSignal({ method: "POST" }, options.signal),
    options.fetch ?? currentFetch(),
  );
}

export async function restoreHistoryImport(
  sessionId: string,
  options: HistoryImportRequestOptions = {},
): Promise<HistoryImportResult> {
  return requestJson<HistoryImportResult>(
    `/api/task-history/backup-imports/${encodeURIComponent(sessionId)}/restore`,
    withSignal({ method: "POST" }, options.signal),
    options.fetch ?? currentFetch(),
  );
}

export async function cancelHistoryImport(
  sessionId: string,
  options: HistoryImportRequestOptions = {},
): Promise<{ session_id: string; status: "cancelled" }> {
  return requestJson<{ session_id: string; status: "cancelled" }>(
    `/api/task-history/backup-imports/${encodeURIComponent(sessionId)}`,
    withSignal({ method: "DELETE" }, options.signal),
    options.fetch ?? currentFetch(),
  );
}

function positiveChunkSize(value: unknown): number {
  return typeof value === "number"
    && Number.isInteger(value)
    && value > 0
    && value <= DEFAULT_HISTORY_IMPORT_CHUNK_BYTES
    ? value
    : DEFAULT_HISTORY_IMPORT_CHUNK_BYTES;
}

const IMPORT_STATUSES = new Set<string>([
  "uploading", "uploaded", "validated", "restoring", "restored", "failed", "interrupted",
]);
const IMPORT_CLASSIFICATIONS = new Set<string>([
  "restorable", "restored", "duplicate", "conflict", "invalid", "failed",
  "thumbnail_warning", "cleanup_warning",
]);

function invalidResponse(): never {
  throw new Error("history_import_response_invalid");
}

function parseTaskResults(value: unknown): HistoryImportTaskResult[] {
  if (!Array.isArray(value)) invalidResponse();
  return value.map((item) => {
    if (!item || typeof item !== "object" || Array.isArray(item)) invalidResponse();
    const record = item as Record<string, unknown>;
    if (!Object.keys(record).every((key) => ["task_id", "classification", "reason"].includes(key))) invalidResponse();
    if (
      typeof record.task_id !== "string"
      || !/^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/.test(record.task_id)
      || typeof record.classification !== "string"
      || !IMPORT_CLASSIFICATIONS.has(record.classification)
      || (record.reason !== undefined && record.reason !== null
        && (typeof record.reason !== "string" || !/^[a-z][a-z0-9_]{2,127}$/.test(record.reason)))
    ) invalidResponse();
    const parsed: HistoryImportTaskResult = {
      task_id: record.task_id,
      classification: record.classification,
    };
    if (record.reason !== undefined) parsed.reason = record.reason as string | null;
    return parsed;
  });
}

function parseImportResult(value: unknown): HistoryImportResult | null {
  if (value === null || value === undefined) return null;
  if (!value || typeof value !== "object" || Array.isArray(value)) invalidResponse();
  const record = value as Record<string, unknown>;
  const keys = [
    "restored", "duplicates", "conflicts", "invalid", "failed",
    "thumbnail_warnings", "cleanup_warnings",
  ];
  if (Object.keys(record).length !== keys.length || !keys.every((key) => key in record)) invalidResponse();
  return {
    restored: parseTaskResults(record.restored),
    duplicates: parseTaskResults(record.duplicates),
    conflicts: parseTaskResults(record.conflicts),
    invalid: parseTaskResults(record.invalid),
    failed: parseTaskResults(record.failed),
    thumbnail_warnings: parseTaskResults(record.thumbnail_warnings),
    cleanup_warnings: parseTaskResults(record.cleanup_warnings),
  };
}

function parseHistoryImportSnapshot(value: unknown): HistoryImportSnapshot {
  if (!value || typeof value !== "object" || Array.isArray(value)) invalidResponse();
  const record = value as Record<string, unknown>;
  if (
    typeof record.session_id !== "string" || !/^[0-9a-f]{32}$/.test(record.session_id)
    || typeof record.filename !== "string" || !record.filename
    || typeof record.size_bytes !== "number" || !Number.isInteger(record.size_bytes) || record.size_bytes < 0
    || typeof record.uploaded_bytes !== "number" || !Number.isInteger(record.uploaded_bytes) || record.uploaded_bytes < 0
    || typeof record.status !== "string" || !IMPORT_STATUSES.has(record.status)
    || (record.error_code !== undefined && record.error_code !== null && typeof record.error_code !== "string")
  ) invalidResponse();
  const result = parseImportResult(record.result);
  if (record.status === "restored" && result === null) invalidResponse();
  return {
    ...(record as unknown as HistoryImportSession),
    status: record.status as HistoryImportStatus,
    upload_chunk_bytes: positiveChunkSize(record.upload_chunk_bytes),
    result,
  };
}

function abortError(signal: AbortSignal): unknown {
  return signal.reason ?? new DOMException("aborted", "AbortError");
}

function throwIfAborted(signal: AbortSignal | undefined): void {
  if (signal?.aborted) throw abortError(signal);
}

function isRetryableChunkError(error: unknown): boolean {
  if (error instanceof DOMException && error.name === "AbortError") return false;
  if (!(error instanceof HistoryImportApiError)) return true;
  return error.status === 408 || error.status === 429 || error.status >= 500;
}

export async function uploadAndValidateHistoryImport(
  file: Blob,
  initialSession: HistoryImportSession,
  options: HistoryImportUploadOptions = {},
): Promise<HistoryImportPreview> {
  if (file.size !== initialSession.size_bytes) {
    throw new HistoryImportApiError("backup_import_size_invalid", "backup_import_size_invalid", 422);
  }
  const fetchFn = options.fetch ?? currentFetch();
  const cryptoLike = options.crypto ?? globalThis.crypto;
  const chunkBytes = positiveChunkSize(initialSession.upload_chunk_bytes);
  let offset = initialSession.uploaded_bytes;
  if (!Number.isInteger(offset) || offset < 0 || offset > file.size) {
    throw new HistoryImportApiError("backup_import_offset_invalid", "backup_import_offset_invalid", 409);
  }
  while (offset < file.size) {
    throwIfAborted(options.signal);
    const end = Math.min(file.size, offset + chunkBytes);
    const slice = file.slice(offset, end);
    const bytes = await slice.arrayBuffer();
    const sha256 = await sha256Hex(bytes, cryptoLike);
    let uploaded: HistoryImportSession | null = null;
    let lastError: unknown = null;
    for (let attempt = 0; attempt < 2; attempt += 1) {
      throwIfAborted(options.signal);
      try {
        uploaded = await appendHistoryImportChunk(
          initialSession.session_id,
          offset,
          bytes,
          sha256,
          { fetch: fetchFn, signal: options.signal },
        );
        throwIfAborted(options.signal);
        break;
      } catch (error) {
        lastError = error;
        if (options.signal?.aborted || attempt === 1 || !isRetryableChunkError(error)) throw error;
      }
    }
    if (!uploaded) throw lastError;
    const expected = end;
    if (uploaded.uploaded_bytes !== expected) {
      throw new HistoryImportApiError("backup_import_offset_invalid", "backup_import_offset_invalid", 409);
    }
    offset = expected;
    options.onProgress?.(offset, file.size);
    throwIfAborted(options.signal);
  }
  if (offset !== file.size) {
    throw new HistoryImportApiError("backup_import_upload_incomplete", "backup_import_upload_incomplete", 409);
  }
  options.onUploadComplete?.();
  throwIfAborted(options.signal);
  return validateHistoryImport(initialSession.session_id, {
    fetch: fetchFn,
    signal: options.signal,
  });
}

export function readStoredHistoryImportSessionId(
  storage: StorageLike | null = currentStorage(),
): string | null {
  if (!storage) return null;
  try {
    const raw = storage.getItem(HISTORY_IMPORT_STORAGE_KEY);
    if (!raw) return null;
    const parsed: unknown = JSON.parse(raw);
    if (
      parsed && typeof parsed === "object"
      && Object.keys(parsed).length === 2
      && (parsed as Record<string, unknown>).version === 1
      && typeof (parsed as Record<string, unknown>).sessionId === "string"
      && /^[0-9a-f]{32}$/.test((parsed as { sessionId: string }).sessionId)
    ) {
      return (parsed as { sessionId: string }).sessionId;
    }
  } catch {
    // Invalid state is removed below.
  }
  try { storage.removeItem(HISTORY_IMPORT_STORAGE_KEY); } catch { /* ignored */ }
  return null;
}

function storeSessionId(storage: StorageLike | null, sessionId: string): void {
  if (!storage) return;
  try {
    storage.setItem(HISTORY_IMPORT_STORAGE_KEY, JSON.stringify({ version: 1, sessionId }));
  } catch {
    // The active in-memory controller remains usable.
  }
}

function clearSessionId(storage: StorageLike | null): void {
  try { storage?.removeItem(HISTORY_IMPORT_STORAGE_KEY); } catch { /* ignored */ }
}

function phaseForStatus(status: HistoryImportStatus): HistoryImportPhase {
  if (status === "uploaded" || status === "uploading") return "uploading";
  return status;
}

export function createHistoryImportController(options: HistoryImportControllerOptions = {}) {
  const fetchFn = options.fetch ?? currentFetch();
  const storage = options.storage === undefined ? currentStorage() : options.storage;
  const cryptoLike = options.crypto ?? globalThis.crypto;
  let sessionId: string | null = null;
  let activeAbort: AbortController | null = null;
  let generation = 0;
  let disposed = false;
  const adoptedSessionIds = new Set<string>();
  const deletions = new Map<string, Promise<{ session_id: string; status: "cancelled" }>>();

  const abortActive = () => {
    activeAbort?.abort();
    activeAbort = null;
  };
  const isCurrent = (operationGeneration: number) => (
    operationGeneration === generation && !disposed
  );
  const beginIntent = (nextDisposed = false) => {
    generation += 1;
    disposed = nextDisposed;
    abortActive();
    return generation;
  };
  const supersededError = () => new DOMException("superseded", "AbortError");
  const deleteExact = (
    targetSessionId: string,
  ): Promise<{ session_id: string; status: "cancelled" }> => {
    const existing = deletions.get(targetSessionId);
    if (existing) return existing;
    const request = cancelHistoryImport(targetSessionId, { fetch: fetchFn });
    deletions.set(targetSessionId, request);
    void request.then(
      () => { if (deletions.get(targetSessionId) === request) deletions.delete(targetSessionId); },
      () => { if (deletions.get(targetSessionId) === request) deletions.delete(targetSessionId); },
    );
    return request;
  };
  const retireExact = async (targetSessionId: string): Promise<void> => {
    try {
      await deleteExact(targetSessionId);
    } catch {
      // A replacement may proceed; server startup recovery owns failed cleanup.
    }
  };
  const waitForRetirements = (): Promise<void> | null => {
    const pending = [...deletions.values()];
    if (!pending.length) return null;
    return Promise.all(pending.map(async (request) => {
      try { await request; } catch { /* replacement may proceed */ }
    })).then(() => undefined);
  };
  const setPhase = (operationGeneration: number, phase: HistoryImportPhase): boolean => {
    if (!isCurrent(operationGeneration)) return false;
    options.onPhase?.(phase);
    return isCurrent(operationGeneration);
  };
  const run = async <T>(
    operationGeneration: number,
    operation: (signal: AbortSignal) => Promise<T>,
  ): Promise<T> => {
    if (!isCurrent(operationGeneration)) throw new DOMException("superseded", "AbortError");
    const abort = new AbortController();
    activeAbort = abort;
    try {
      return await operation(abort.signal);
    } finally {
      if (activeAbort === abort) activeAbort = null;
    }
  };
  const cleanupOrphan = async (orphanSessionId: string): Promise<void> => {
    if (adoptedSessionIds.has(orphanSessionId)) return;
    await retireExact(orphanSessionId);
  };

  return {
    async start(file: Blob, filename: string): Promise<HistoryImportPreview> {
      const previousSessionId = sessionId ?? readStoredHistoryImportSessionId(storage);
      const operationGeneration = beginIntent(false);
      sessionId = null;
      clearSessionId(storage);
      if (!setPhase(operationGeneration, "creating")) {
        throw supersededError();
      }
      if (previousSessionId) await retireExact(previousSessionId);
      const pendingRetirements = waitForRetirements();
      if (pendingRetirements) await pendingRetirements;
      if (!isCurrent(operationGeneration)) throw supersededError();
      return run(operationGeneration, async (signal) => {
        const session = await createHistoryImport(filename, file.size, { fetch: fetchFn, signal });
        if (!isCurrent(operationGeneration)) {
          await cleanupOrphan(session.session_id);
          throw supersededError();
        }
        sessionId = session.session_id;
        adoptedSessionIds.add(sessionId);
        storeSessionId(storage, sessionId);
        if (!setPhase(operationGeneration, "uploading")) {
          throw supersededError();
        }
        const preview = await uploadAndValidateHistoryImport(file, session, {
          fetch: fetchFn,
          crypto: cryptoLike,
          signal,
          onProgress: (uploaded, total) => {
            if (isCurrent(operationGeneration)) options.onProgress?.(uploaded, total);
          },
          onUploadComplete: () => { setPhase(operationGeneration, "validating"); },
        });
        if (!isCurrent(operationGeneration)) {
          throw supersededError();
        }
        setPhase(operationGeneration, "validated");
        return preview;
      });
    },
    async resume(): Promise<HistoryImportSnapshot | null> {
      const operationGeneration = beginIntent(false);
      sessionId = readStoredHistoryImportSessionId(storage);
      if (sessionId) adoptedSessionIds.add(sessionId);
      if (!sessionId) return null;
      const current = sessionId;
      const session = await run(
        operationGeneration,
        (signal) => getHistoryImport(current, { fetch: fetchFn, signal }),
      );
      if (!isCurrent(operationGeneration)) return null;
      setPhase(operationGeneration, phaseForStatus(session.status));
      if (!isCurrent(operationGeneration)) return null;
      return session;
    },
    async resumeUpload(file: Blob, filename: string): Promise<HistoryImportPreview | null> {
      const current = sessionId ?? readStoredHistoryImportSessionId(storage);
      const operationGeneration = beginIntent(false);
      if (!current) return null;
      sessionId = current;
      adoptedSessionIds.add(current);
      storeSessionId(storage, current);
      return run(operationGeneration, async (signal) => {
        const session = await getHistoryImport(current, { fetch: fetchFn, signal });
        if (!isCurrent(operationGeneration)) return null;
        if (
          session.status !== "uploading"
          && session.status !== "uploaded"
          && session.status !== "validated"
        ) {
          throw new HistoryImportApiError(
            "backup_import_status_invalid",
            "backup_import_status_invalid",
            409,
          );
        }
        if (filename !== session.filename || file.size !== session.size_bytes) {
          throw new HistoryImportApiError(
            "backup_import_file_mismatch",
            "backup_import_file_mismatch",
            422,
          );
        }
        if (
          !Number.isInteger(session.uploaded_bytes)
          || session.uploaded_bytes < 0
          || session.uploaded_bytes > file.size
        ) {
          throw new HistoryImportApiError(
            "backup_import_offset_invalid",
            "backup_import_offset_invalid",
            409,
          );
        }
        if (session.status === "uploaded" || session.status === "validated") {
          options.onProgress?.(file.size, file.size);
          if (!isCurrent(operationGeneration)) return null;
          if (!setPhase(operationGeneration, "validating")) return null;
          const preview = await validateHistoryImport(current, { fetch: fetchFn, signal });
          if (!isCurrent(operationGeneration)) return null;
          setPhase(operationGeneration, "validated");
          return preview;
        }
        if (!setPhase(operationGeneration, "uploading")) return null;
        options.onProgress?.(session.uploaded_bytes, file.size);
        if (!isCurrent(operationGeneration)) return null;
        const preview = await uploadAndValidateHistoryImport(file, session, {
          fetch: fetchFn,
          crypto: cryptoLike,
          signal,
          onProgress: (uploaded, total) => {
            if (isCurrent(operationGeneration)) options.onProgress?.(uploaded, total);
          },
          onUploadComplete: () => { setPhase(operationGeneration, "validating"); },
        });
        if (!isCurrent(operationGeneration)) return null;
        setPhase(operationGeneration, "validated");
        return preview;
      });
    },
    async resumeValidate(): Promise<HistoryImportPreview | null> {
      const current = sessionId ?? readStoredHistoryImportSessionId(storage);
      const operationGeneration = beginIntent(false);
      if (!current) return null;
      sessionId = current;
      adoptedSessionIds.add(current);
      storeSessionId(storage, current);
      return run(operationGeneration, async (signal) => {
        const session = await getHistoryImport(current, { fetch: fetchFn, signal });
        if (!isCurrent(operationGeneration)) return null;
        if (session.status !== "uploaded" && session.status !== "validated") {
          throw new HistoryImportApiError(
            "backup_import_status_invalid",
            "backup_import_status_invalid",
            409,
          );
        }
        if (!setPhase(operationGeneration, "validating")) return null;
        const preview = await validateHistoryImport(current, { fetch: fetchFn, signal });
        if (!isCurrent(operationGeneration)) return null;
        setPhase(operationGeneration, "validated");
        return preview;
      });
    },
    async restore(): Promise<HistoryImportResult | null> {
      const operationGeneration = beginIntent(false);
      if (!sessionId) sessionId = readStoredHistoryImportSessionId(storage);
      if (!sessionId) return null;
      adoptedSessionIds.add(sessionId);
      if (!setPhase(operationGeneration, "restoring")) return null;
      const current = sessionId;
      const result = await run(
        operationGeneration,
        (signal) => restoreHistoryImport(current, { fetch: fetchFn, signal }),
      );
      if (!isCurrent(operationGeneration)) return null;
      setPhase(operationGeneration, result.failed.length ? "failed" : "restored");
      if (!isCurrent(operationGeneration)) return null;
      return result;
    },
    acknowledgeTerminal(expectedSessionId: string): boolean {
      if (!/^[0-9a-f]{32}$/.test(expectedSessionId)) return false;
      if (sessionId !== expectedSessionId) return false;
      if (readStoredHistoryImportSessionId(storage) !== expectedSessionId) return false;
      clearSessionId(storage);
      if (sessionId === expectedSessionId) sessionId = null;
      return true;
    },
    async acknowledgeTerminalAfterRefresh(
      expectedSessionId: string,
      refresh: () => Promise<void>,
    ): Promise<boolean> {
      await refresh();
      return this.acknowledgeTerminal(expectedSessionId);
    },
    async cancel(): Promise<boolean> {
      const current = sessionId ?? readStoredHistoryImportSessionId(storage);
      const operationGeneration = beginIntent(false);
      if (!setPhase(operationGeneration, "cancelled")) return false;
      if (!current) {
        return false;
      }
      await deleteExact(current);
      if (!isCurrent(operationGeneration)) return false;
      sessionId = null;
      clearSessionId(storage);
      return true;
    },
    dispose(): void { beginIntent(true); },
    activeSessionId(): string | null { return sessionId; },
  };
}

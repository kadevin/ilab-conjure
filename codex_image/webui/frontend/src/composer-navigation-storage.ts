import type { ImageMentionContext } from "./prompt-image-mentions";
export type ComposerDraft = { prompt: string; prompt_image_mentions?: ImageMentionContext | null; images: any[]; files: any[]; mode: string };
export type ComposerNavigationSnapshot = { current: ComposerDraft; drafts: ComposerDraft[]; baseline: string };
export interface ComposerNavigationStore {
  hasPending(): boolean;
  save(snapshot: ComposerNavigationSnapshot): Promise<void>;
  load(): Promise<ComposerNavigationSnapshot | null>;
  clear(): Promise<void>;
}

const POINTER = "codex-image-composer-navigation";
const DATABASE = "codex-image-composer-navigation";
const STORE = "drafts";
const MAX_AGE = 7 * 24 * 60 * 60 * 1000;

function openDatabase(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(DATABASE, 1);
    let blocked = false;
    request.onupgradeneeded = () => {
      request.result.createObjectStore(STORE).createIndex("savedAt", "savedAt");
    };
    request.onsuccess = () => {
      if (blocked) { request.result.close(); return; }
      request.result.onversionchange = () => request.result.close();
      resolve(request.result);
    };
    request.onerror = () => reject(request.error);
    request.onblocked = () => { blocked = true; reject(new Error("Draft storage is blocked")); };
  });
}

async function transaction<T>(mode: IDBTransactionMode, action: (store: IDBObjectStore) => IDBRequest<T>): Promise<T> {
  const database = await openDatabase();
  try {
    return await new Promise<T>((resolve, reject) => {
      const tx = database.transaction(STORE, mode);
      const request = action(tx.objectStore(STORE));
      tx.oncomplete = () => resolve(request.result);
      tx.onabort = () => reject(tx.error || request.error || new Error("Draft transaction aborted"));
      tx.onerror = () => reject(tx.error || request.error);
    });
  } finally { database.close(); }
}

function validDraft(value: any): value is ComposerDraft {
  return value && typeof value.prompt === "string" && typeof value.mode === "string"
    && Array.isArray(value.images) && Array.isArray(value.files);
}

// File and Blob objects use IndexedDB's structured clone, without base64 conversion
// or server uploads. Only the lookup token is kept in this tab's sessionStorage.
export const composerNavigationStore: ComposerNavigationStore = {
  hasPending() {
    try { return Boolean(sessionStorage.getItem(POINTER)); } catch { return false; }
  },
  async save(snapshot) {
    const token = sessionStorage.getItem(POINTER) || globalThis.crypto?.randomUUID?.()
      || `${Date.now()}-${Math.random().toString(36).slice(2)}`;
    await transaction("readwrite", store => {
      // Reclaim abandoned copies on a subsequent handoff, without reading blobs.
      const stale = store.index("savedAt").openKeyCursor(IDBKeyRange.upperBound(Date.now() - MAX_AGE));
      stale.onsuccess = () => {
        const cursor = stale.result;
        if (!cursor) return;
        if (cursor.primaryKey !== token) store.delete(cursor.primaryKey);
        cursor.continue();
      };
      return store.put({ snapshot, savedAt: Date.now() }, token);
    });
    try { sessionStorage.setItem(POINTER, token); }
    catch (error) {
      await transaction("readwrite", store => store.delete(token)).catch(() => {});
      throw error;
    }
  },
  async load() {
    const token = sessionStorage.getItem(POINTER);
    if (!token) return null;
    const record = await transaction<any>("readonly", store => store.get(token));
    const snapshot = record?.snapshot;
    if (!validDraft(snapshot?.current) || !Array.isArray(snapshot?.drafts)
      || !snapshot.drafts.every(validDraft) || typeof snapshot.baseline !== "string") {
      throw new Error("Invalid navigation draft");
    }
    return snapshot;
  },
  async clear() {
    const token = sessionStorage.getItem(POINTER);
    if (!token) return;
    await transaction("readwrite", store => store.delete(token));
    if (sessionStorage.getItem(POINTER) === token) sessionStorage.removeItem(POINTER);
  },
};

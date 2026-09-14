import assert from "node:assert/strict";
import test from "node:test";
import { webcrypto } from "node:crypto";

import {
  HistoryImportApiError,
  createHistoryImport,
  createHistoryImportController,
  getHistoryImport,
  readStoredHistoryImportSessionId,
  uploadAndValidateHistoryImport,
} from "../../codex_image/webui/frontend/src/history-import.ts";

class MemoryStorage {
  readonly values = new Map<string, string>();
  getItem(key: string): string | null { return this.values.get(key) ?? null; }
  setItem(key: string, value: string): void { this.values.set(key, value); }
  removeItem(key: string): void { this.values.delete(key); }
}

function json(value: unknown, status = 200): Response {
  return new Response(JSON.stringify(value), {
    status,
    headers: { "content-type": "application/json" },
  });
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
}

class SliceOnlyBlob {
  readonly size: number;
  readonly type = "application/zip";
  readonly slices: Array<[number, number]> = [];
  private readonly bytes: Uint8Array;
  constructor(bytes: Uint8Array) {
    this.bytes = bytes;
    this.size = bytes.byteLength;
  }
  slice(start = 0, end = this.size) {
    this.slices.push([start, end]);
    const bytes = this.bytes.slice(start, end);
    return { size: bytes.byteLength, arrayBuffer: async () => bytes.buffer };
  }
  async arrayBuffer(): Promise<ArrayBuffer> { throw new Error("whole file read forbidden"); }
}

test("import create/get are typed, use advertised chunk size, and sanitize unknown errors", async () => {
  const calls: Array<[string, RequestInit | undefined]> = [];
  const fetchFn = async (url: RequestInfo | URL, init?: RequestInit) => {
    calls.push([String(url), init]);
    if (init?.method === "POST") return json({
      session_id: "a".repeat(32), filename: "backup.zip", size_bytes: 9,
      uploaded_bytes: 0, status: "uploading", upload_chunk_bytes: 3,
    });
    return json({ detail: { code: "backup_import_not_found", message: "missing" } }, 404);
  };
  const created = await createHistoryImport("backup.zip", 9, { fetch: fetchFn });
  assert.equal(created.upload_chunk_bytes, 3);
  assert.deepEqual(JSON.parse(String(calls[0]?.[1]?.body)), { filename: "backup.zip", size_bytes: 9 });
  await assert.rejects(
    getHistoryImport(created.session_id, { fetch: fetchFn }),
    (error: unknown) => error instanceof HistoryImportApiError
      && error.code === "backup_import_not_found" && error.status === 404,
  );
  const secretFetch = async () => json({
    detail: { code: "backup_internal_error", message: "secret_prompt /private/request.json" },
  }, 500);
  await assert.rejects(
    getHistoryImport(created.session_id, { fetch: secretFetch }),
    (error: unknown) => error instanceof HistoryImportApiError
      && error.code === "backup_internal_error" && !error.message.includes("secret_prompt"),
  );
});

test("chunk upload slices once, retries identical bytes once, reports monotonic progress, then validates", async () => {
  const file = new SliceOnlyBlob(Uint8Array.from({ length: 25 }, (_, index) => index));
  const requests: Array<{ url: string; init: RequestInit }> = [];
  let failedFirst = false;
  const fetchFn = async (url: RequestInfo | URL, init: RequestInit = {}) => {
    requests.push({ url: String(url), init });
    if (String(url).endsWith("/chunks") && !failedFirst) {
      failedFirst = true;
      throw new TypeError("temporary network failure");
    }
    if (String(url).endsWith("/validate")) return json({ session_id: "b".repeat(32), restorable: [] });
    const offset = Number(new Headers(init.headers).get("x-chunk-offset"));
    const length = (init.body as ArrayBuffer).byteLength;
    return json({ session_id: "b".repeat(32), uploaded_bytes: offset + length, status: "uploading" });
  };
  const progress: number[] = [];
  const stages: string[] = [];
  await uploadAndValidateHistoryImport(
    file as unknown as Blob,
    {
      session_id: "b".repeat(32), filename: "backup.zip", size_bytes: 25,
      uploaded_bytes: 0, status: "uploading", upload_chunk_bytes: 10,
    },
    {
      fetch: fetchFn,
      crypto: webcrypto as unknown as Crypto,
      onProgress: (uploaded) => progress.push(uploaded),
      onUploadComplete: () => stages.push("upload-complete"),
    },
  );

  const chunks = requests.filter((item) => item.url.endsWith("/chunks"));
  assert.deepEqual(file.slices, [[0, 10], [10, 20], [20, 25]]);
  assert.deepEqual(chunks.map((item) => new Headers(item.init.headers).get("x-chunk-offset")), ["0", "0", "10", "20"]);
  assert.equal(chunks[0]?.init.body, chunks[1]?.init.body);
  assert.equal(new Headers(chunks[0]?.init.headers).has("content-length"), false);
  assert.equal(new Headers(chunks[0]?.init.headers).get("x-chunk-sha256"), new Headers(chunks[1]?.init.headers).get("x-chunk-sha256"));
  assert.deepEqual(progress, [10, 20, 25]);
  assert.deepEqual(stages, ["upload-complete"]);
  assert.equal(requests.at(-1)?.url.endsWith("/validate"), true);
});

test("upload stops before validate when the second attempt fails", async () => {
  const file = new SliceOnlyBlob(Uint8Array.from([1, 2, 3]));
  const urls: string[] = [];
  const fetchFn = async (url: RequestInfo | URL) => {
    urls.push(String(url));
    throw new TypeError("offline");
  };
  await assert.rejects(uploadAndValidateHistoryImport(
    file as unknown as Blob,
    { session_id: "c".repeat(32), filename: "x.zip", size_bytes: 3, uploaded_bytes: 0, status: "uploading", upload_chunk_bytes: 3 },
    { fetch: fetchFn, crypto: webcrypto as unknown as Crypto },
  ));
  assert.equal(urls.length, 2);
  assert.equal(urls.some((url) => url.endsWith("/validate")), false);
});

test("import controller restores only versioned id, aborts active upload before DELETE, and clears on cancel", async () => {
  const storage = new MemoryStorage();
  storage.setItem("ilab-history-backup-import", "broken");
  assert.equal(readStoredHistoryImportSessionId(storage), null);
  storage.setItem("ilab-history-backup-import", JSON.stringify({ version: 2, sessionId: "old" }));
  assert.equal(readStoredHistoryImportSessionId(storage), null);

  let uploadSignal: AbortSignal | undefined;
  let rejectUpload: ((reason?: unknown) => void) | undefined;
  const calls: string[] = [];
  const fetchFn = async (url: RequestInfo | URL, init: RequestInit = {}): Promise<Response> => {
    calls.push(`${init.method ?? "GET"} ${String(url)}`);
    if (init.method === "POST" && String(url).endsWith("backup-imports")) return json({
      session_id: "d".repeat(32), filename: "backup.zip", size_bytes: 3,
      uploaded_bytes: 0, status: "uploading", upload_chunk_bytes: 3,
    });
    if (init.method === "DELETE") return json({ session_id: "d".repeat(32), status: "cancelled" });
    uploadSignal = init.signal ?? undefined;
    return new Promise((_resolve, reject) => { rejectUpload = reject; });
  };
  const phases: string[] = [];
  const controller = createHistoryImportController({
    fetch: fetchFn,
    storage,
    crypto: webcrypto as unknown as Crypto,
    onPhase: (phase) => phases.push(phase),
  });
  const started = controller.start(new Blob([Uint8Array.from([1, 2, 3])]), "backup.zip");
  for (let attempt = 0; attempt < 100 && !rejectUpload; attempt += 1) {
    await new Promise<void>((resolve) => setImmediate(resolve));
  }
  assert.ok(rejectUpload, "upload request should be active before cancellation");
  assert.equal(storage.getItem("ilab-history-backup-import"), JSON.stringify({ version: 1, sessionId: "d".repeat(32) }));
  const cancelled = controller.cancel();
  assert.equal(uploadSignal?.aborted, true);
  rejectUpload?.(new DOMException("aborted", "AbortError"));
  await assert.rejects(started);
  await cancelled;
  assert.equal(calls.at(-1), `DELETE /api/task-history/backup-imports/${"d".repeat(32)}`);
  assert.equal(storage.getItem("ilab-history-backup-import"), null);
  assert.equal(phases.at(-1), "cancelled");
});

test("restore existing session queries status; terminal restore clears storage", async () => {
  const storage = new MemoryStorage();
  storage.setItem("ilab-history-backup-import", JSON.stringify({ version: 1, sessionId: "e".repeat(32) }));
  const fetchFn = async (url: RequestInfo | URL, init: RequestInit = {}) => {
    if (String(url).endsWith("/restore")) return json({ restored: [], failed: [], cleanup_warnings: [] });
    return json({ session_id: "e".repeat(32), filename: "backup.zip", size_bytes: 3, uploaded_bytes: 3, status: "validated" });
  };
  const controller = createHistoryImportController({ fetch: fetchFn, storage, crypto: webcrypto as unknown as Crypto });
  const session = await controller.resume();
  assert.equal(session?.status, "validated");
  assert.notEqual(storage.getItem("ilab-history-backup-import"), null);
  await controller.restore();
  assert.notEqual(storage.getItem("ilab-history-backup-import"), null);
  assert.equal(controller.acknowledgeTerminal("e".repeat(32)), true);
  assert.equal(storage.getItem("ilab-history-backup-import"), null);
});

test("terminal resume returns a strict nested result and retains it until matching acknowledgement", async () => {
  const storage = new MemoryStorage();
  const sessionId = "6".repeat(32);
  storage.setItem("ilab-history-backup-import", JSON.stringify({ version: 1, sessionId }));
  const controller = createHistoryImportController({
    fetch: async () => json({
      session_id: sessionId, filename: "backup.zip", size_bytes: 3,
      uploaded_bytes: 3, status: "restored", result: {
        restored: [{ task_id: "task-1", classification: "restored", reason: "backup_import_restored" }],
        duplicates: [], conflicts: [], invalid: [], failed: [],
        thumbnail_warnings: [], cleanup_warnings: [],
      },
    }),
    storage,
    crypto: webcrypto as unknown as Crypto,
  });

  const resumed = await controller.resume();
  assert.equal(resumed?.result?.restored[0]?.task_id, "task-1");
  assert.notEqual(storage.getItem("ilab-history-backup-import"), null);
  storage.setItem(
    "ilab-history-backup-import",
    JSON.stringify({ version: 1, sessionId: "7".repeat(32) }),
  );
  assert.equal(controller.acknowledgeTerminal(sessionId), false);
  assert.equal(readStoredHistoryImportSessionId(storage), "7".repeat(32));
});

test("terminal acknowledgement waits for both strict refresh steps and matching active identity", async () => {
  for (const failure of ["summary", "tasks"] as const) {
    const storage = new MemoryStorage();
    const sessionId = failure === "summary" ? "9".repeat(32) : "0".repeat(32);
    storage.setItem("ilab-history-backup-import", JSON.stringify({ version: 1, sessionId }));
    const controller = createHistoryImportController({
      fetch: async () => json({
        session_id: sessionId, filename: "backup.zip", size_bytes: 1,
        uploaded_bytes: 1, status: "restored", result: {
          restored: [], duplicates: [], conflicts: [], invalid: [], failed: [],
          thumbnail_warnings: [], cleanup_warnings: [],
        },
      }),
      storage,
      crypto: webcrypto as unknown as Crypto,
    });
    await controller.resume();
    await assert.rejects(controller.acknowledgeTerminalAfterRefresh(sessionId, async () => {
      if (failure === "summary") throw new Error("summary failed");
      await Promise.resolve();
      throw new Error("tasks failed");
    }));
    assert.equal(readStoredHistoryImportSessionId(storage), sessionId);
    assert.equal(controller.activeSessionId(), sessionId);
    assert.equal(await controller.acknowledgeTerminalAfterRefresh(sessionId, async () => undefined), true);
    assert.equal(readStoredHistoryImportSessionId(storage), null);
  }
});

test("terminal GET rejects malformed nested results", async () => {
  await assert.rejects(
    getHistoryImport("8".repeat(32), {
      fetch: async () => json({
        session_id: "8".repeat(32), filename: "backup.zip", size_bytes: 1,
        uploaded_bytes: 1, status: "restored", result: { restored: "not-an-array" },
      }),
    }),
    /history_import_response_invalid/,
  );
});

test("invalid or oversized advertised chunk sizes fall back to 8 MiB", async () => {
  const invalidSizes = [0, -1, Number.NaN, 8 * 1024 * 1024 + 1];
  for (const advertised of invalidSizes) {
    const slices: Array<[number, number]> = [];
    const size = 8 * 1024 * 1024 + 1;
    const file = {
      size,
      slice(start: number, end: number) {
        slices.push([start, end]);
        return { arrayBuffer: async () => new ArrayBuffer(end - start) };
      },
    } as unknown as Blob;
    const fetchFn = async (url: RequestInfo | URL, init: RequestInit = {}) => {
      if (String(url).endsWith("/validate")) return json({ session_id: "f".repeat(32), restorable: [] });
      const offset = Number(new Headers(init.headers).get("x-chunk-offset"));
      return json({ uploaded_bytes: offset + (init.body as ArrayBuffer).byteLength, status: "uploading" });
    };
    await uploadAndValidateHistoryImport(file, {
      session_id: "f".repeat(32), filename: "backup.zip", size_bytes: size,
      uploaded_bytes: 0, status: "uploading", upload_chunk_bytes: advertised,
    }, { fetch: fetchFn, crypto: webcrypto as unknown as Crypto });
    assert.deepEqual(slices, [[0, 8 * 1024 * 1024], [8 * 1024 * 1024, size]]);
  }
});

test("definitive chunk 409 is not retried and never validates", async () => {
  const urls: string[] = [];
  const fetchFn = async (url: RequestInfo | URL) => {
    urls.push(String(url));
    return json({ detail: { code: "backup_import_offset_invalid", message: "backup_import_offset_invalid" } }, 409);
  };
  await assert.rejects(uploadAndValidateHistoryImport(
    new Blob([Uint8Array.from([1, 2, 3])]),
    { session_id: "7".repeat(32), filename: "x.zip", size_bytes: 3, uploaded_bytes: 0, status: "uploading", upload_chunk_bytes: 3 },
    { fetch: fetchFn, crypto: webcrypto as unknown as Crypto },
  ));
  assert.equal(urls.length, 1);
  assert.equal(urls.some((url) => url.endsWith("/validate")), false);
});

test("late create after cancel is deleted and cannot change cancelled phase or storage", async () => {
  const storage = new MemoryStorage();
  const pendingCreate = deferred<Response>();
  const calls: string[] = [];
  const phases: string[] = [];
  const fetchFn = async (url: RequestInfo | URL, init: RequestInit = {}) => {
    calls.push(`${init.method ?? "GET"} ${String(url)}`);
    if (init.method === "DELETE") return json({ session_id: String(url).split("/").at(-1), status: "cancelled" });
    return pendingCreate.promise;
  };
  const controller = createHistoryImportController({
    fetch: fetchFn, storage, crypto: webcrypto as unknown as Crypto,
    onPhase: (phase) => phases.push(phase),
  });
  const stale = controller.start(new Blob([Uint8Array.from([1])]), "backup.zip");
  await controller.cancel();
  pendingCreate.resolve(json({
    session_id: "8".repeat(32), filename: "backup.zip", size_bytes: 1,
    uploaded_bytes: 0, status: "uploading", upload_chunk_bytes: 1,
  }));
  await assert.rejects(stale);

  assert.equal(calls.includes(`DELETE /api/task-history/backup-imports/${"8".repeat(32)}`), true);
  assert.equal(storage.getItem("ilab-history-backup-import"), null);
  assert.equal(phases.at(-1), "cancelled");
  assert.equal(controller.activeSessionId(), null);
});

test("stale import create with the current session id is not deleted", async () => {
  const storage = new MemoryStorage();
  const first = deferred<Response>();
  const sharedId = "b".repeat(32);
  const calls: string[] = [];
  let createCount = 0;
  const controller = createHistoryImportController({
    fetch: async (url, init = {}) => {
      calls.push(`${init.method ?? "GET"} ${String(url)}`);
      if (init.method === "DELETE") return json({ session_id: sharedId, status: "cancelled" });
      if (init.method === "POST" && String(url).endsWith("backup-imports")) {
        createCount += 1;
        return createCount === 1 ? first.promise : json({
          session_id: sharedId, filename: "new.zip", size_bytes: 0,
          uploaded_bytes: 0, status: "uploaded", upload_chunk_bytes: 1,
        });
      }
      if (String(url).endsWith("/restore")) {
        return json({ restored: [], failed: [], cleanup_warnings: [] });
      }
      return json({ session_id: sharedId, restorable: [] });
    },
    storage,
    crypto: webcrypto as unknown as Crypto,
  });

  const stale = controller.start(new Blob(), "old.zip");
  const staleRejected = assert.rejects(stale, (error: unknown) => (
    error instanceof DOMException && error.name === "AbortError"
  ));
  await controller.start(new Blob(), "new.zip");
  await controller.restore();
  controller.acknowledgeTerminal(sharedId);
  first.resolve(json({
    session_id: sharedId, filename: "old.zip", size_bytes: 0,
    uploaded_bytes: 0, status: "uploaded", upload_chunk_bytes: 1,
  }));
  await staleRejected;

  assert.equal(calls.some((call) => call.startsWith("DELETE")), false);
  assert.equal(controller.activeSessionId(), null);
  assert.equal(storage.getItem("ilab-history-backup-import"), null);
});

test("adopted import id survives restore and a no-op resume before stale create cleanup", async () => {
  const storage = new MemoryStorage();
  const first = deferred<Response>();
  const sharedId = "f".repeat(32);
  const calls: string[] = [];
  let createCount = 0;
  const controller = createHistoryImportController({
    fetch: async (url, init = {}) => {
      calls.push(`${init.method ?? "GET"} ${String(url)}`);
      if (init.method === "DELETE") return json({ session_id: sharedId, status: "cancelled" });
      if (init.method === "POST" && String(url).endsWith("backup-imports")) {
        createCount += 1;
        return createCount === 1 ? first.promise : json({
          session_id: sharedId, filename: "new.zip", size_bytes: 0,
          uploaded_bytes: 0, status: "uploaded", upload_chunk_bytes: 1,
        });
      }
      if (String(url).endsWith("/restore")) {
        return json({ restored: [], failed: [], cleanup_warnings: [] });
      }
      return json({ session_id: sharedId, restorable: [] });
    },
    storage,
    crypto: webcrypto as unknown as Crypto,
  });

  const stale = controller.start(new Blob(), "old.zip");
  const staleRejected = assert.rejects(stale, (error: unknown) => (
    error instanceof DOMException && error.name === "AbortError"
  ));
  await controller.start(new Blob(), "new.zip");
  await controller.restore();
  controller.acknowledgeTerminal(sharedId);
  assert.equal(await controller.resume(), null);
  first.resolve(json({
    session_id: sharedId, filename: "old.zip", size_bytes: 0,
    uploaded_bytes: 0, status: "uploaded", upload_chunk_bytes: 1,
  }));
  await staleRejected;

  assert.equal(calls.some((call) => call.startsWith("DELETE")), false);
  assert.equal(controller.activeSessionId(), null);
  assert.equal(storage.getItem("ilab-history-backup-import"), null);
});

test("import restart retires one stored id before concurrent replacement create", async () => {
  const storage = new MemoryStorage();
  const retiredId = "c".repeat(32);
  storage.setItem("ilab-history-backup-import", JSON.stringify({ version: 1, sessionId: retiredId }));
  const pendingDelete = deferred<Response>();
  const calls: string[] = [];
  const controller = createHistoryImportController({
    fetch: async (url, init = {}) => {
      calls.push(`${init.method ?? "GET"} ${String(url)}`);
      if (init.method === "DELETE") return pendingDelete.promise;
      if (init.method === "POST" && String(url).endsWith("backup-imports")) return json({
        session_id: retiredId, filename: "replacement.zip", size_bytes: 0,
        uploaded_bytes: 0, status: "uploaded", upload_chunk_bytes: 1,
      });
      return json({ session_id: retiredId, restorable: [] });
    },
    storage,
    crypto: webcrypto as unknown as Crypto,
  });

  const superseded = controller.start(new Blob(), "first.zip");
  const current = controller.start(new Blob(), "replacement.zip");
  await Promise.resolve();
  assert.deepEqual(calls, [`DELETE /api/task-history/backup-imports/${retiredId}`]);
  assert.equal(storage.getItem("ilab-history-backup-import"), null);

  pendingDelete.resolve(json({ session_id: retiredId, status: "cancelled" }));
  await assert.rejects(superseded, (error: unknown) => (
    error instanceof DOMException && error.name === "AbortError"
  ));
  await current;

  assert.equal(calls.filter((call) => call.startsWith("DELETE")).length, 1);
  assert.equal(calls.filter((call) => call === "POST /api/task-history/backup-imports").length, 1);
  assert.equal(controller.activeSessionId(), retiredId);
  assert.equal(storage.getItem("ilab-history-backup-import"), JSON.stringify({ version: 1, sessionId: retiredId }));
});

test("import restart retires its active id before creating and storing a replacement", async () => {
  const storage = new MemoryStorage();
  const oldId = "d".repeat(32);
  const newId = "e".repeat(32);
  const calls: string[] = [];
  let createCount = 0;
  const controller = createHistoryImportController({
    fetch: async (url, init = {}) => {
      calls.push(`${init.method ?? "GET"} ${String(url)}`);
      if (init.method === "DELETE") return json({ session_id: oldId, status: "cancelled" });
      if (init.method === "POST" && String(url).endsWith("backup-imports")) {
        createCount += 1;
        return json({
          session_id: createCount === 1 ? oldId : newId,
          filename: "backup.zip", size_bytes: 0, uploaded_bytes: 0,
          status: "uploaded", upload_chunk_bytes: 1,
        });
      }
      return json({ session_id: createCount === 1 ? oldId : newId, restorable: [] });
    },
    storage,
    crypto: webcrypto as unknown as Crypto,
  });

  await controller.start(new Blob(), "old.zip");
  await controller.start(new Blob(), "new.zip");

  const oldDelete = calls.indexOf(`DELETE /api/task-history/backup-imports/${oldId}`);
  const createCalls = calls
    .map((call, index) => [call, index] as const)
    .filter(([call]) => call === "POST /api/task-history/backup-imports");
  assert.equal(createCalls.length, 2);
  assert.ok(oldDelete > createCalls[0]![1]);
  assert.ok(oldDelete < createCalls[1]![1]);
  assert.equal(controller.activeSessionId(), newId);
  assert.equal(storage.getItem("ilab-history-backup-import"), JSON.stringify({ version: 1, sessionId: newId }));
});

test("late chunk after cancel cannot report progress, validate, or overwrite phase", async () => {
  const storage = new MemoryStorage();
  const pendingChunk = deferred<Response>();
  const phases: string[] = [];
  const progress: number[] = [];
  const calls: string[] = [];
  const fetchFn = async (url: RequestInfo | URL, init: RequestInit = {}) => {
    calls.push(`${init.method ?? "GET"} ${String(url)}`);
    if (init.method === "POST" && String(url).endsWith("backup-imports")) return json({
      session_id: "9".repeat(32), filename: "backup.zip", size_bytes: 3,
      uploaded_bytes: 0, status: "uploading", upload_chunk_bytes: 3,
    });
    if (init.method === "DELETE") return json({ session_id: "9".repeat(32), status: "cancelled" });
    if (init.method === "PUT") return pendingChunk.promise;
    return json({ session_id: "9".repeat(32), restorable: [] });
  };
  const controller = createHistoryImportController({
    fetch: fetchFn, storage, crypto: webcrypto as unknown as Crypto,
    onPhase: (phase) => phases.push(phase), onProgress: (value) => progress.push(value),
  });
  const stale = controller.start(new Blob([Uint8Array.from([1, 2, 3])]), "backup.zip");
  for (let attempt = 0; attempt < 100 && !calls.some((call) => call.startsWith("PUT")); attempt += 1) {
    await new Promise<void>((resolve) => setImmediate(resolve));
  }
  await controller.cancel();
  pendingChunk.resolve(json({ session_id: "9".repeat(32), uploaded_bytes: 3, status: "uploaded" }));
  await assert.rejects(stale);

  assert.deepEqual(progress, []);
  assert.equal(calls.some((call) => call.endsWith("/validate")), false);
  assert.equal(phases.at(-1), "cancelled");
  assert.equal(storage.getItem("ilab-history-backup-import"), null);
});

test("late restore result after cancel cannot replace cancelled phase", async () => {
  const storage = new MemoryStorage();
  storage.setItem("ilab-history-backup-import", JSON.stringify({ version: 1, sessionId: "a".repeat(32) }));
  const pendingRestore = deferred<Response>();
  const phases: string[] = [];
  const fetchFn = async (url: RequestInfo | URL, init: RequestInit = {}) => {
    if (init.method === "DELETE") return json({ session_id: "a".repeat(32), status: "cancelled" });
    if (String(url).endsWith("/restore")) return pendingRestore.promise;
    return json({
      session_id: "a".repeat(32), filename: "backup.zip", size_bytes: 1,
      uploaded_bytes: 1, status: "validated",
    });
  };
  const controller = createHistoryImportController({
    fetch: fetchFn, storage, crypto: webcrypto as unknown as Crypto,
    onPhase: (phase) => phases.push(phase),
  });
  await controller.resume();
  const staleRestore = controller.restore();
  await Promise.resolve();
  await controller.cancel();
  pendingRestore.resolve(json({ restored: [], failed: [], cleanup_warnings: [] }));

  assert.equal(await staleRestore, null);
  assert.equal(phases.at(-1), "cancelled");
  assert.equal(storage.getItem("ilab-history-backup-import"), null);
  assert.equal(controller.activeSessionId(), null);
});

test("resume upload refreshes the stored session offset and continues without create or delete", async () => {
  const storage = new MemoryStorage();
  const sessionId = "1".repeat(32);
  storage.setItem("ilab-history-backup-import", JSON.stringify({ version: 1, sessionId }));
  const calls: string[] = [];
  const offsets: string[] = [];
  const file = new SliceOnlyBlob(Uint8Array.from([0, 1, 2, 3, 4, 5]));
  const controller = createHistoryImportController({
    fetch: async (url, init = {}) => {
      calls.push(`${init.method ?? "GET"} ${String(url)}`);
      if (init.method === "PUT") {
        const offset = new Headers(init.headers).get("x-chunk-offset") || "";
        offsets.push(offset);
        return json({ session_id: sessionId, uploaded_bytes: Number(offset) + 2, status: "uploading" });
      }
      if (String(url).endsWith("/validate")) return json({ session_id: sessionId, restorable: [] });
      return json({
        session_id: sessionId, filename: "backup.zip", size_bytes: 6,
        uploaded_bytes: 4, status: "uploading", upload_chunk_bytes: 2,
      });
    },
    storage,
    crypto: webcrypto as unknown as Crypto,
  });

  const preview = await controller.resumeUpload(file as unknown as Blob, "backup.zip");

  assert.equal(preview?.session_id, sessionId);
  assert.deepEqual(file.slices, [[4, 6]]);
  assert.deepEqual(offsets, ["4"]);
  assert.equal(calls.some((call) => call === "POST /api/task-history/backup-imports"), false);
  assert.equal(calls.some((call) => call.startsWith("DELETE ")), false);
  assert.notEqual(storage.getItem("ilab-history-backup-import"), null);
});

test("late resume validation is isolated by a newer start and cancel", async () => {
  const storage = new MemoryStorage();
  const oldId = "2".repeat(32);
  const newId = "3".repeat(32);
  storage.setItem("ilab-history-backup-import", JSON.stringify({ version: 1, sessionId: oldId }));
  const pendingValidation = deferred<Response>();
  const phases: string[] = [];
  const controller = createHistoryImportController({
    fetch: async (url, init = {}) => {
      const value = String(url);
      if (value.endsWith(`${oldId}/validate`)) return pendingValidation.promise;
      if (init.method === "DELETE") return json({ session_id: value.split("/").at(-1), status: "cancelled" });
      if (init.method === "POST" && value.endsWith("backup-imports")) return json({
        session_id: newId, filename: "new.zip", size_bytes: 0,
        uploaded_bytes: 0, status: "uploaded", upload_chunk_bytes: 1,
      });
      if (value.endsWith(`/${oldId}`)) return json({
        session_id: oldId, filename: "old.zip", size_bytes: 1,
        uploaded_bytes: 1, status: "uploaded", upload_chunk_bytes: 1,
      });
      return json({ session_id: newId, restorable: [] });
    },
    storage,
    crypto: webcrypto as unknown as Crypto,
    onPhase: (phase) => phases.push(phase),
  });

  const staleValidation = controller.resumeValidate();
  for (let attempt = 0; attempt < 100 && phases.at(-1) !== "validating"; attempt += 1) {
    await new Promise<void>((resolve) => setImmediate(resolve));
  }
  await controller.start(new Blob(), "new.zip");
  await controller.cancel();
  pendingValidation.resolve(json({ session_id: oldId, restorable: [{ task_id: "stale", classification: "restorable" }] }));

  assert.equal(await staleValidation, null);
  assert.equal(phases.at(-1), "cancelled");
  assert.equal(controller.activeSessionId(), null);
  assert.equal(storage.getItem("ilab-history-backup-import"), null);
});

test("resume upload mismatch preserves the stored session for another reselect", async () => {
  const storage = new MemoryStorage();
  const sessionId = "4".repeat(32);
  storage.setItem("ilab-history-backup-import", JSON.stringify({ version: 1, sessionId }));
  const calls: string[] = [];
  const controller = createHistoryImportController({
    fetch: async (url, init = {}) => {
      calls.push(`${init.method ?? "GET"} ${String(url)}`);
      return json({
        session_id: sessionId, filename: "backup.zip", size_bytes: 4,
        uploaded_bytes: 2, status: "uploading", upload_chunk_bytes: 2,
      });
    },
    storage,
    crypto: webcrypto as unknown as Crypto,
  });

  await assert.rejects(
    controller.resumeUpload(new Blob([Uint8Array.from([1, 2, 3])]), "backup.zip"),
    (error: unknown) => error instanceof HistoryImportApiError
      && error.code === "backup_import_file_mismatch",
  );

  assert.equal(calls.some((call) => call.startsWith("DELETE ")), false);
  assert.equal(calls.some((call) => call.startsWith("POST ")), false);
  assert.equal(controller.activeSessionId(), sessionId);
  assert.notEqual(storage.getItem("ilab-history-backup-import"), null);
});

test("resume upload rejects filename and size mismatches without replacing the session, then resumes the matching file", async () => {
  const storage = new MemoryStorage();
  const sessionId = "5".repeat(32);
  storage.setItem("ilab-history-backup-import", JSON.stringify({ version: 1, sessionId }));
  const calls: string[] = [];
  const controller = createHistoryImportController({
    fetch: async (url, init = {}) => {
      calls.push(`${init.method ?? "GET"} ${String(url)}`);
      if (init.method === "PUT") {
        const offset = Number(new Headers(init.headers).get("x-chunk-offset"));
        return json({ session_id: sessionId, uploaded_bytes: offset + 2, status: "uploaded" });
      }
      if (String(url).endsWith("/validate")) return json({ session_id: sessionId, restorable: [] });
      return json({
        session_id: sessionId, filename: "right.zip", size_bytes: 4,
        uploaded_bytes: 2, status: "uploading", upload_chunk_bytes: 2,
      });
    },
    storage,
    crypto: webcrypto as unknown as Crypto,
  });

  await assert.rejects(
    controller.resumeUpload(new Blob([Uint8Array.from([1, 2, 3, 4])]), "wrong.zip"),
    (error: unknown) => error instanceof HistoryImportApiError
      && error.code === "backup_import_file_mismatch",
  );
  await assert.rejects(
    controller.resumeUpload(new Blob([Uint8Array.from([1, 2, 3])]), "right.zip"),
    (error: unknown) => error instanceof HistoryImportApiError
      && error.code === "backup_import_file_mismatch",
  );

  assert.equal(calls.some((call) => call.startsWith("DELETE ")), false);
  assert.equal(calls.some((call) => call === "POST /api/task-history/backup-imports"), false);
  assert.equal(controller.activeSessionId(), sessionId);
  assert.notEqual(storage.getItem("ilab-history-backup-import"), null);

  const preview = await controller.resumeUpload(
    new Blob([Uint8Array.from([1, 2, 3, 4])]),
    "right.zip",
  );
  assert.equal(preview?.session_id, sessionId);
  assert.equal(calls.some((call) => call.startsWith("DELETE ")), false);
  assert.equal(calls.some((call) => call === "POST /api/task-history/backup-imports"), false);
});

test("HTTP LAN import initializes and validates chunk hashes without Web Crypto", async () => {
  const descriptor = Object.getOwnPropertyDescriptor(globalThis, "crypto");
  Object.defineProperty(globalThis, "crypto", { configurable: true, value: {} });
  try {
    let chunks = 0;
    const controller = createHistoryImportController({
      storage: new MemoryStorage(),
      fetch: async (url, init = {}) => {
        if (String(url).endsWith("/chunks")) {
          chunks++;
          const expected = Buffer.from(await webcrypto.subtle.digest("SHA-256", init.body as ArrayBuffer)).toString("hex");
          assert.equal(new Headers(init.headers).get("x-chunk-sha256"), expected);
          return json({ session_id: "lan", uploaded_bytes: 3, status: "uploaded" });
        }
        if (String(url).endsWith("/validate")) return json({ session_id: "lan", restorable: [] });
        return json({ session_id: "lan", filename: "backup.zip", size_bytes: 3, uploaded_bytes: 0, status: "uploading", upload_chunk_bytes: 8 });
      },
    });
    const preview = await controller.start(new Blob(["abc"]), "backup.zip");
    assert.equal(preview.session_id, "lan");
    assert.equal(chunks, 1);
  } finally {
    if (descriptor) Object.defineProperty(globalThis, "crypto", descriptor);
    else Reflect.deleteProperty(globalThis, "crypto");
  }
});

test("HTTP SHA-256 fallback matches native hashing at block boundaries and upload chunk size", async () => {
  const { sha256Hex } = await import("../../codex_image/webui/frontend/src/sha256");
  for (const length of [0, 1, 55, 56, 63, 64, 65, 1024, 8 * 1024 * 1024]) {
    const bytes = Uint8Array.from({ length }, (_, index) => index % 251).buffer;
    const expected = Buffer.from(await webcrypto.subtle.digest("SHA-256", bytes)).toString("hex");
    assert.equal(await sha256Hex(bytes, null), expected);
  }
});

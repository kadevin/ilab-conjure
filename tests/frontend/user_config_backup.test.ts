import assert from "node:assert/strict";
import test from "node:test";

import * as userConfigBackupApi from "../../codex_image/webui/frontend/src/user-config-backup-api";
import {
  USER_CONFIG_TRANSFER_STORAGE_KEY,
  UserConfigTransferApiError,
  buildUserConfigBackupRequest,
  buildUserConfigRestoreRequest,
  cancelUserConfigRestore,
  createReplacementConfirmation,
  createUserConfigBackup,
  createUserConfigRestore,
  createUserConfigTransferController,
  directDownloadUserConfigBackup,
  emptyUserConfigReplacementGroups,
  userConfigBackupStatusMessageKey,
  updateReplacementConfirmation,
  uploadUserConfigRestore,
  type UserConfigSection,
} from "../../codex_image/webui/frontend/src/user-config-backup-api";
import {
  applyUserConfigClientPreferences,
  readUserConfigClientPreferences,
} from "../../codex_image/webui/frontend/src/task-notifications";

type BackupActionPriority = {
  create: "primary" | "secondary";
  download: "primary" | "secondary";
};

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

test("backup selection is strict and disabling settings clears API keys", () => {
  const preferences = {
    theme: "dark" as const,
    notifications: { in_app: true, system: false },
  };
  assert.deepEqual(buildUserConfigBackupRequest(
    ["gallery", "settings", "gallery"], true, preferences,
  ), {
    sections: ["gallery", "settings"],
    include_api_keys: true,
    client_preferences: preferences,
  });
  assert.deepEqual(buildUserConfigBackupRequest(["templates"], true, preferences), {
    sections: ["templates"],
    include_api_keys: false,
    client_preferences: null,
  });
  assert.throws(() => buildUserConfigBackupRequest([], false, preferences));
  assert.throws(() => buildUserConfigBackupRequest(["settings", "invalid" as UserConfigSection], false, preferences));
});

test("restore upload uses ordered 8 MiB chunks and per-chunk sha256", async () => {
  const bytes = new Uint8Array(8 * 1024 * 1024 + 3);
  bytes.fill(7);
  const file = new Blob([bytes]) as Blob & { name: string };
  file.name = "settings.zip";
  const calls: Array<{ offset: string | null; length: number; digest: string | null }> = [];
  const fetchFn = async (_url: RequestInfo | URL, init?: RequestInit) => {
    const headers = new Headers(init?.headers);
    const body = init?.body as Blob;
    calls.push({
      offset: headers.get("x-upload-offset"),
      length: body.size,
      digest: headers.get("x-chunk-sha256"),
    });
    return json({ session: {
      session_id: "b".repeat(32), filename: file.name, size_bytes: file.size,
      uploaded_bytes: Number(headers.get("x-upload-offset")) + body.size,
      status: "uploading", created_at: "", updated_at: "",
    } });
  };
  const progress: number[] = [];
  await uploadUserConfigRestore(file, { session_id: "b".repeat(32), upload_chunk_bytes: 8 * 1024 * 1024 }, {
    fetch: fetchFn,
    onProgress: (uploaded) => progress.push(uploaded),
  });
  assert.deepEqual(calls.map(({ offset, length }) => [offset, length]), [
    ["0", 8 * 1024 * 1024],
    [String(8 * 1024 * 1024), 3],
  ]);
  assert.ok(calls.every((call) => /^[0-9a-f]{64}$/.test(call.digest || "")));
  assert.deepEqual(progress, [8 * 1024 * 1024, file.size]);
});

test("create and cancel restore use stable endpoints and safe errors", async () => {
  const calls: Array<[string, string]> = [];
  const fetchFn = async (url: RequestInfo | URL, init?: RequestInit) => {
    calls.push([String(url), init?.method ?? "GET"]);
    if (init?.method === "DELETE") return json({ cancelled: true });
    return json({ detail: { code: "user_config_restore_active", message: "/private/archive.zip" } }, 409);
  };
  await assert.rejects(
    createUserConfigRestore({ name: "archive.zip", size: 10 }, { fetch: fetchFn }),
    (error: unknown) => error instanceof UserConfigTransferApiError
      && error.code === "user_config_restore_active"
      && !error.message.includes("private"),
  );
  await cancelUserConfigRestore("c".repeat(32), { fetch: fetchFn });
  assert.deepEqual(calls, [
    ["/api/user-config-restores", "POST"],
    [`/api/user-config-restores/${"c".repeat(32)}`, "DELETE"],
  ]);
});

test("download uses the one-time URL directly without fetching a blob", () => {
  let clicked = 0;
  let removed = 0;
  const anchor: any = {
    href: "", hidden: false,
    click: () => { clicked += 1; },
    remove: () => { removed += 1; },
  };
  directDownloadUserConfigBackup("/api/user-config-backups/id/download", {
    createElement: () => anchor,
    body: { appendChild: (node: unknown) => assert.equal(node, anchor) },
  });
  assert.equal(anchor.href, "/api/user-config-backups/id/download");
  assert.equal(anchor.hidden, true);
  assert.equal(clicked, 1);
  assert.equal(removed, 1);
});

test("failed backup status exposes its stable reason instead of a generic failure", () => {
  const failedJob = {
    job_id: "f".repeat(32), status: "failed" as const,
    sections: ["gallery" as const], created_at: "", updated_at: "",
    total_members: 0, completed_members: 0, total_bytes: 0, completed_bytes: 0,
    warnings: [], filename: null, download_url: null,
    error_code: "user_config_backup_gallery_invalid",
  };
  assert.equal(
    userConfigBackupStatusMessageKey(failedJob),
    "user_config_backup_gallery_invalid",
  );
  assert.equal(
    userConfigBackupStatusMessageKey({ ...failedJob, error_code: null }),
    "userConfigBackup.status.failed",
  );
  assert.equal(
    userConfigBackupStatusMessageKey({ ...failedJob, status: "ready" }),
    "userConfigBackup.status.ready",
  );
});

test("ready backup promotes download and demotes creating another backup", () => {
  const priority = (
    userConfigBackupApi as unknown as {
      userConfigBackupActionPriority?: (status: string | null) => BackupActionPriority;
    }
  ).userConfigBackupActionPriority;

  assert.equal(typeof priority, "function");
  assert.deepEqual(priority?.("ready"), {
    create: "secondary",
    download: "primary",
  });
  assert.deepEqual(priority?.(null), {
    create: "primary",
    download: "secondary",
  });
});

test("replacement acknowledgment is invalidated by digest, sections, or mode", () => {
  const base = createReplacementConfirmation("a".repeat(64), ["chips", "gallery"], "replace");
  const acknowledged = updateReplacementConfirmation(base, { acknowledged: true });
  assert.equal(buildUserConfigRestoreRequest(acknowledged, "p".repeat(64))?.confirm_replace, true);
  assert.equal(buildUserConfigRestoreRequest(
    updateReplacementConfirmation(acknowledged, { sections: ["chips"] }), "p".repeat(64),
  ), null);
  assert.equal(buildUserConfigRestoreRequest(
    updateReplacementConfirmation(acknowledged, { archiveSha256: "b".repeat(64) }), "p".repeat(64),
  ), null);
  const incremental = updateReplacementConfirmation(acknowledged, { mode: "incremental" });
  assert.deepEqual(buildUserConfigRestoreRequest(incremental, "p".repeat(64)), {
    sections: ["chips", "gallery"], mode: "incremental",
    archive_sha256: "a".repeat(64), preview_revision: "p".repeat(64), confirm_replace: false,
  });
});

test("empty archive groups with current data are unsafe for replacement", () => {
  const preview = {
    session_id: "a".repeat(32),
    archive_sha256: "b".repeat(64),
    preview_revision: "c".repeat(64),
    format_version: 1,
    restorable: true,
    contains_secrets: false,
    sections: [
      {
        section: "chips" as const,
        archive_count: 1,
        identical_count: 0,
        conflicts: 0,
        missing_assets: 0,
        replace_existing_count: 4,
        estimated_write_bytes: 100,
        warnings: [],
        current_fingerprint: "d".repeat(64),
        groups: [
          { group: "colors", archive_count: 1, current_count: 3 },
          { group: "prompt_snippets", archive_count: 0, current_count: 1 },
        ],
      },
      {
        section: "gallery" as const,
        archive_count: 0,
        identical_count: 0,
        conflicts: 0,
        missing_assets: 0,
        replace_existing_count: 2,
        estimated_write_bytes: 10,
        warnings: [],
        current_fingerprint: "e".repeat(64),
        groups: [
          { group: "gallery_items", archive_count: 0, current_count: 2 },
        ],
      },
    ],
    path_fields: {},
    keyed_provider_retention_count: 0,
    gallery_history_reference_impact: 0,
    warnings: [],
  };

  assert.deepEqual(
    emptyUserConfigReplacementGroups(preview, ["chips", "gallery"]),
    [
      { section: "chips", group: "prompt_snippets", archiveCount: 0, currentCount: 1 },
      { section: "gallery", group: "gallery_items", archiveCount: 0, currentCount: 2 },
    ],
  );
  assert.deepEqual(emptyUserConfigReplacementGroups(preview, ["chips"]), [
    { section: "chips", group: "prompt_snippets", archiveCount: 0, currentCount: 1 },
  ]);
});

test("controller keeps only versioned ids, one timer, and stops at terminal", async () => {
  const storage = new MemoryStorage();
  const timers: Array<{ active: boolean; callback: () => Promise<void> }> = [];
  const statuses = ["planning", "ready"];
  const observed: string[] = [];
  const fetchFn = async (_url: RequestInfo | URL, init?: RequestInit) => json({ job: {
    job_id: "d".repeat(32), status: init?.method === "POST" ? "queued" : statuses.shift(),
    sections: ["chips"], created_at: "", updated_at: "", total_members: 0,
    completed_members: 0, total_bytes: 0, completed_bytes: 0, warnings: [],
    filename: null, download_url: null, error_code: null,
  } });
  const controller = createUserConfigTransferController({
    storage,
    fetch: fetchFn,
    setTimeout: (callback) => {
      const timer = { active: true, callback: async () => { timer.active = false; await callback(); } };
      timers.push(timer);
      return timer;
    },
    clearTimeout: (timer: any) => { timer.active = false; },
    onBackupStatus: (job) => observed.push(job.status),
  });
  await controller.startBackup({ sections: ["chips"], include_api_keys: false, client_preferences: null });
  assert.equal(storage.getItem(USER_CONFIG_TRANSFER_STORAGE_KEY), JSON.stringify({
    version: 1, backupJobId: "d".repeat(32), restoreSessionId: null,
  }));
  assert.equal(timers.filter((timer) => timer.active).length, 1);
  await timers[0]?.callback();
  assert.equal(timers.filter((timer) => timer.active).length, 1);
  await timers.at(-1)?.callback();
  assert.deepEqual(observed, ["queued", "planning", "ready"]);
  assert.equal(timers.filter((timer) => timer.active).length, 0);
});

test("client preferences read and apply without touching seen notification state", () => {
  const storage = new MemoryStorage();
  storage.setItem("codex-image-theme-preference", "dark");
  storage.setItem("codex-image-task-notification-settings", JSON.stringify({ inApp: false, system: true }));
  storage.setItem("codex-image-task-notification-seen", "[\"keep\"]");
  assert.deepEqual(readUserConfigClientPreferences(storage), {
    theme: "dark", notifications: { in_app: false, system: true },
  });

  const result = applyUserConfigClientPreferences({
    theme: "light", notifications: { in_app: true, system: true },
  }, "replace", {
    storage,
    notificationPermission: "denied",
    applyTheme: () => undefined,
  });
  assert.deepEqual(result.warnings, ["user_config_restore_system_notification_permission_missing"]);
  assert.equal(storage.getItem("codex-image-theme-preference"), "light");
  assert.equal(storage.getItem("codex-image-task-notification-settings"), JSON.stringify({ inApp: true, system: false }));
  assert.equal(storage.getItem("codex-image-task-notification-seen"), "[\"keep\"]");

  const missing = new MemoryStorage();
  missing.setItem("codex-image-theme-preference", "dark");
  applyUserConfigClientPreferences({
    theme: "light", notifications: { in_app: false, system: false },
  }, "incremental", { storage: missing, notificationPermission: "granted", applyTheme: () => undefined });
  assert.equal(missing.getItem("codex-image-theme-preference"), "dark");
  assert.equal(missing.getItem("codex-image-task-notification-settings"), JSON.stringify({ inApp: false, system: false }));
});

test("backup request posts the exact validated payload", async () => {
  let body = "";
  const fetchFn = async (_url: RequestInfo | URL, init?: RequestInit) => {
    body = String(init?.body || "");
    return json({ job: { job_id: "e".repeat(32), status: "queued" } });
  };
  await createUserConfigBackup({ sections: ["chips"], include_api_keys: false, client_preferences: null }, { fetch: fetchFn });
  assert.deepEqual(JSON.parse(body), { sections: ["chips"], include_api_keys: false, client_preferences: null });
});

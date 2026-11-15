import assert from "node:assert/strict";
import test from "node:test";
import { initTaskDerivedFeature } from "../../codex_image/webui/frontend/src/task-derived";

const methods: Record<string, (...args: any[]) => any> = {};
(globalThis as any).window = { __codexImageWebUI: { methods } };
initTaskDerivedFeature();

const sources = [
  { kind: "upload", name: "first.png", previewUrl: "blob:local-first" },
  { kind: "gallery", image_url: "/api/gallery/gallery-one/image" },
  { kind: "asset", image_url: "/api/reference-assets/asset-one/image" },
  { kind: "upload", name: "last.png", previewUrl: "blob:local-last" },
];
const previews = sources.map(source => source.previewUrl || source.image_url);

test("pending and locally failed tasks retain ordered local input previews", () => {
  for (const status of ["submitting", "failed"]) {
    const task = {
      task_id: "pending-123", local_pending: true, status,
      input_files: ["first.png", "last.png"], input_sources: sources,
      local_input_files: sources,
    };
    assert.deepEqual(methods.taskInputPreviewUrls(task), previews);
    assert.equal(methods.taskInputThumbnailRoute(task, 1), "");
    assert.deepEqual(methods.taskInputThumbnailUrls(task), []);
  }
});

test("local-only preview records work without input_sources or uploaded files", () => {
  const task = { task_id: "pending-456", local_pending: true, local_input_files: sources };
  assert.deepEqual(methods.taskInputPreviewUrls(task), previews);
  assert.deepEqual(methods.taskInputPreviewUrls({ ...task, local_input_files: [] }), []);
});

test("accepted tasks keep server thumbnail mapping for interleaved inputs", () => {
  const task = {
    task_id: "accepted-123", status: "queued", input_files: ["first.png", "last.png"],
    input_sources: sources,
  };
  assert.deepEqual(methods.taskInputPreviewUrls(task), [
    "/api/tasks/accepted-123/inputs/1/thumbnail",
    sources[1].image_url,
    sources[2].image_url,
    "/api/tasks/accepted-123/inputs/2/thumbnail",
  ]);
  assert.deepEqual(methods.taskInputPreviewUrls({
    ...task, input_thumbnail_urls: ["/cached/first.webp", "/cached/last.webp"],
  }), ["/cached/first.webp", sources[1].image_url, sources[2].image_url, "/cached/last.webp"]);
});

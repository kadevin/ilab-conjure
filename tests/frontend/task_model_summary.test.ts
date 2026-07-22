import assert from "node:assert/strict";
import test from "node:test";

import {
  taskCanvasSummaryParts,
  taskCanonicalModelId,
  taskChannelLabel,
  taskModelFamilyId,
  taskModelDisplayName,
  taskOutputSettingsView,
  taskOutputControlValues,
  taskRequestedParameters,
  taskUsesCanonicalModelSummary,
} from "../../codex_image/webui/frontend/src/task-model-summary";
import { modelFamilyBrandMarkHtml } from "../../codex_image/webui/frontend/src/model-family-icons";
import type { GenerationCatalog } from "../../codex_image/webui/frontend/src/types";

const catalog = {
  models: [
    { id: "gpt-image-2", family_id: "gpt-image", display_name: "GPT Image 2" },
    { id: "nano-banana-pro", family_id: "gemini-image", display_name: "Nano Banana Pro" },
    { id: "nano-banana-2", family_id: "gemini-image", display_name: "Nano Banana 2" },
    { id: "nano-banana-2-lite", family_id: "gemini-image", display_name: "Nano Banana 2 Lite" },
  ],
} as GenerationCatalog;

test("canonical task summaries prefer frozen generation snapshots", () => {
  const task = {
    task_id: "history",
    generation_snapshot: {
      canonical_model_id: "nano-banana-2",
      requested_parameters: {
        "canvas.aspect_ratio": "16:9",
        "canvas.resolution": "2K",
        "output.count": 3,
      },
    },
    request: {
      canonical_model_id: "gpt-image-2",
      parameters: { "canvas.size": "1024x1024" },
    },
  };

  assert.equal(taskCanonicalModelId(task), "nano-banana-2");
  assert.equal(taskModelDisplayName(task, catalog), "Nano Banana 2");
  assert.equal(taskModelFamilyId(task, catalog), "gemini-image");
  assert.deepEqual(taskCanvasSummaryParts(task), ["16:9", "2K"]);
  assert.deepEqual(taskRequestedParameters(task), {
    "canvas.aspect_ratio": "16:9",
    "canvas.resolution": "2K",
    "output.count": 3,
  });
  assert.equal(taskUsesCanonicalModelSummary(task), true);
});

test("history output controls prefer frozen canonical parameters over stale legacy params", () => {
  const task = {
    generation_snapshot: {
      requested_parameters: {
        "canvas.size": "1024x1536",
        "gpt.quality": "high",
        "gpt.moderation": "low",
        "gpt.web_search": true,
        "output.count": 4,
        "output.format": "png",
        "gpt.output_compression": 90,
      },
    },
    params: {
      size: "auto",
      quality: "low",
      moderation: "auto",
      web_search: false,
      n: 1,
      output_format: "jpeg",
      output_compression: 55,
    },
  };

  assert.deepEqual(taskOutputControlValues(task), {
    size: "1024x1536",
    quality: "high",
    moderation: "low",
    web_search: true,
    n: 4,
    output_format: "png",
    output_compression: 90,
  });
});

test("pending task summaries use canonical request data before a snapshot exists", () => {
  const task = {
    task_id: "pending",
    request: {
      canonical_model_id: "nano-banana-pro",
      parameters: {
        "canvas.aspect_ratio": "16:9",
        "canvas.resolution": "2K",
        "output.count": 1,
      },
    },
  };

  assert.equal(taskCanonicalModelId(task), "nano-banana-pro");
  assert.equal(taskModelDisplayName(task, catalog), "Nano Banana Pro");
  assert.equal(taskModelFamilyId(task, catalog), "gemini-image");
  assert.deepEqual(taskCanvasSummaryParts(task), ["16:9", "2K"]);
  assert.deepEqual(taskRequestedParameters(task), task.request.parameters);
  assert.equal(taskUsesCanonicalModelSummary(task), true);
});

test("legacy GPT tasks keep the existing size and provider summary path", () => {
  const task = { task_id: "legacy", params: { size: "1024x1024", ratio: "1:1", resolution: "standard" } };

  assert.equal(taskCanonicalModelId(task), "gpt-image-2");
  assert.equal(taskModelDisplayName(task, catalog), "GPT Image 2");
  assert.deepEqual(taskRequestedParameters(task), {});
  assert.deepEqual(taskCanvasSummaryParts(task), ["1:1", "1K"]);
  assert.equal(taskModelFamilyId(task, catalog), "gpt-image");
  assert.equal(taskUsesCanonicalModelSummary(task), false);
});

test("legacy custom sizes derive an honest ratio and exact pixel resolution", () => {
  assert.deepEqual(taskCanvasSummaryParts({
    params: { size: "1280x1024" },
  }), ["5:4", "1280×1024"]);
  assert.deepEqual(taskCanvasSummaryParts({}), []);
});

test("unknown canonical model IDs remain truthful instead of being guessed", () => {
  const task = {
    task_id: "future",
    generation_snapshot: {
      canonical_model_id: "future-image-model",
      requested_parameters: {},
    },
  };

  assert.equal(taskModelDisplayName(task, catalog), "future-image-model");
  assert.equal(taskModelFamilyId(task, catalog), "unknown");
  assert.equal(taskUsesCanonicalModelSummary(task), true);
});

test("locked task selection keeps the visual summary while unlocked cross-model history uses the inspector", () => {
  const geminiTask = {
    generation_snapshot: { canonical_model_id: "nano-banana-2-lite" },
  };

  assert.equal(taskOutputSettingsView(geminiTask, "gpt-image-2", true), "locked-summary");
  assert.equal(taskOutputSettingsView(geminiTask, "gpt-image-2", false), "parameter-inspector");
  assert.equal(taskOutputSettingsView(geminiTask, "nano-banana-2-lite", false), "editor");
});

test("task cards use the shared Gemini brand mark asset", () => {
  const icon = modelFamilyBrandMarkHtml("gemini-image", "task-model-family-brand-mark");

  assert.match(icon, /task-model-family-brand-mark/);
  assert.match(icon, /\/static\/brand\/model-marks\/gemini\.svg/);
});

test("task channel summaries normalize provider protocol profiles", () => {
  assert.equal(taskChannelLabel({ backend: "t8_images", requested_backend: "openai_images" }), "Image");
  assert.equal(taskChannelLabel({ backend: "openrouter_images" }), "Image");
  assert.equal(taskChannelLabel({ backend: "gemini_generate_content" }), "Gemini");
  assert.equal(taskChannelLabel({ backend: "gemini_change2pro_generate_content" }), "Gemini");
  assert.equal(taskChannelLabel({ backend: "openai_responses" }), "Responses");
  assert.equal(taskChannelLabel({
    backend: "unknown_provider_transport",
    requested_backend: "openai_images",
  }), "Image");
  assert.equal(taskChannelLabel({
    generation_snapshot: { protocol_profile: "gemini_generate_content" },
  }), "Gemini");
});

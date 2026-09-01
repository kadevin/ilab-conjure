import assert from "node:assert/strict";
import test from "node:test";

class FakeClassList {
  private readonly values = new Set<string>();

  add(...names: string[]): void {
    names.forEach((name) => this.values.add(name));
  }

  remove(...names: string[]): void {
    names.forEach((name) => this.values.delete(name));
  }

  contains(name: string): boolean {
    return this.values.has(name);
  }
}

const runButton = {
  classList: new FakeClassList(),
  disabled: false,
  textContent: "开始生成",
  title: "开始生成（Cmd+Enter）",
};

const state: any = {
  authAvailable: true,
  generationCatalog: {
    schema_version: 1,
    manifest_version: 1,
    families: [{ id: "gpt-image", display_name: "GPT Image", short_name: "GPT", label_key: "family.gpt" }],
    models: [{
      id: "gpt-image-2",
      family_id: "gpt-image",
      display_name: "GPT Image 2",
      official_model_id: "gpt-image-2",
      version: 1,
      operations: ["generate"],
      parameters: [],
      input_constraints: { max_images: 1, supports_mask: false, supports_reference_files: false },
    }],
    providers: [{
      id: "provider-a",
      name: "Provider A",
      builtin: false,
      available: true,
      bindings: [{
        id: "binding-a",
        canonical_model_id: "gpt-image-2",
        remote_model_id: "gpt-image-2",
        protocol_profile: "openai_images",
        parameter_codec: "gpt_openai_images",
        operations: ["generate"],
      }],
    }],
    default_provider_by_model: { "gpt-image-2": "provider-a" },
    codex: { available: false, mode: "images" },
  },
  historyTaskReveal: null,
  historyTaskRevealSeq: 0,
  images: [],
  mode: "generate",
  parameterDraftsByModel: { "gpt-image-2": {} },
  pendingTaskId: null,
  referenceFiles: [],
  runFeedbackAction: null,
  runStartedAt: null,
  runTimerId: null,
  selectedModelId: "gpt-image-2",
  selectedProviderBindingId: "binding-a",
  selectedProviderId: "provider-a",
  selectedTaskId: null,
  tasks: [],
};

const els: any = {
  requestJson: { textContent: "" },
  runButton,
  size: { value: "1024x1024" },
};

const methods: Record<string, (...args: any[]) => any> = {};
const bridge: any = { state, els, methods };
const fakeWindow: any = {
  __codexImageWebUI: bridge,
  clearInterval() {},
  clearTimeout: globalThis.clearTimeout.bind(globalThis),
  refreshQueue: async () => {},
  setInterval: () => 1,
  setTimeout: globalThis.setTimeout.bind(globalThis),
};

(globalThis as any).window = fakeWindow;
(globalThis as any).document = { hidden: false };

const runtimeFeedback = await import("../../codex_image/webui/frontend/src/runtime-feedback");
const { initTaskSubmitFeature } = await import("../../codex_image/webui/frontend/src/task-submit");

function resetSubmissionState(): void {
  state.historyTaskReveal = null;
  state.historyTaskRevealSeq = 0;
  state.images = [];
  state.pendingTaskId = null;
  state.referenceFiles = [];
  state.runFeedbackAction = null;
  state.runStartedAt = null;
  state.runTimerId = null;
  state.selectedTaskId = null;
  state.tasks = [];
  runButton.disabled = false;
  runButton.textContent = "开始生成";
  runButton.title = "开始生成（Cmd+Enter）";
  runButton.classList.remove("running");

  Object.assign(methods, {
    addPendingTask(task: any) {
      state.pendingTaskId = task.task_id;
      state.selectedTaskId = task.task_id;
      state.tasks = [task];
    },
    currentMainModel: () => "gpt-5",
    currentPromptFidelity: () => "strict",
    currentPromptForModel: () => "测试提示词",
    currentTaskParams: () => ({ api_mode: "images", model: "gpt-image-2", n: 1, size: "1024x1024" }),
    customSizeValidationMessage: () => "",
    galleryInputs: () => [],
    getPromptText: () => "测试提示词",
    markPendingTaskFailed() {},
    missingGalleryInputs: () => [],
    missingReferenceAssetInputs: () => [],
    missingReferenceFileInputs: () => [],
    referenceAssetInputs: () => [],
    referenceFileUploads: () => [],
    refreshRecentAssets: async () => {},
    renderPreview() {},
    replacePendingTask(_pendingTaskId: string, task: any) {
      state.pendingTaskId = null;
      state.selectedTaskId = task.task_id;
      state.tasks = [task];
    },
    setStatus() {},
    sourcePreviewUrl: () => "",
    startRunFeedback() {},
    stopRunFeedback() {},
    storedReferenceFileInputs: () => [],
    syncGalleryInputsFromPrompt() {},
    syncPromptFromEditor() {},
    uploadInputs: () => [],
  });
  initTaskSubmitFeature();
}

function deferredFetch() {
  const resolvers: Array<(response: Response) => void> = [];
  let calls = 0;
  (globalThis as any).fetch = () => {
    calls += 1;
    return new Promise<Response>((resolve) => resolvers.push(resolve));
  };
  return {
    calls: () => calls,
    resolveAll() {
      resolvers.forEach((resolve, index) => resolve(new Response(JSON.stringify({
        request: {},
        task: { task_id: `queued-${index + 1}`, status: "queued" },
      }), {
        headers: { "Content-Type": "application/json" },
        status: 200,
      })));
    },
  };
}

test("run feedback leaves the generate button visually unchanged", () => {
  resetSubmissionState();
  Object.assign(methods, {
    elapsedMillisecondsSince: () => 0,
    formatDurationTenths: () => "0.0 秒",
    renderTasks() {},
    setStatus() {},
    syncRunButtonLabel() {},
    timestampMs: (value: string) => Date.parse(value),
  });
  const before = {
    disabled: runButton.disabled,
    running: runButton.classList.contains("running"),
    textContent: runButton.textContent,
    title: runButton.title,
  };

  runtimeFeedback.startRunFeedback({
    task_id: "pending-visual",
    status: "submitting",
    created_at: new Date().toISOString(),
  } as any, "提交中");

  assert.deepEqual({
    disabled: runButton.disabled,
    running: runButton.classList.contains("running"),
    textContent: runButton.textContent,
    title: runButton.title,
  }, before);
  runtimeFeedback.stopRunFeedback();
});

test("submission keeps the generate button availability unchanged while awaiting the server", async () => {
  resetSubmissionState();
  const pendingFetch = deferredFetch();
  const submission = methods.runTask();
  let assertionError: unknown = null;
  try {
    assert.equal(pendingFetch.calls(), 1);
    assert.equal(runButton.disabled, false);
  } catch (error) {
    assertionError = error;
  } finally {
    pendingFetch.resolveAll();
    await submission;
  }
  if (assertionError) throw assertionError;
});

test("a second submission is ignored until the first server response arrives", async () => {
  resetSubmissionState();
  const pendingFetch = deferredFetch();
  const firstSubmission = methods.runTask();
  const secondSubmission = methods.runTask();
  let assertionError: unknown = null;
  try {
    assert.equal(pendingFetch.calls(), 1);
  } catch (error) {
    assertionError = error;
  } finally {
    pendingFetch.resolveAll();
    await Promise.all([firstSubmission, secondSubmission]);
  }
  if (assertionError) throw assertionError;
});

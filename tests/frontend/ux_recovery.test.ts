import assert from "node:assert/strict";
import test from "node:test";
import { suggestLegalSize } from "../../codex_image/webui/frontend/src/size-suggestion";
import { taskRecoveryKind } from "../../codex_image/webui/frontend/src/task-recovery";

test("template creation records the current model and edits preserve the stored model hint", async () => {
  const previous = { window: globalThis.window, document: globalThis.document, fetch: globalThis.fetch };
  const form: any = {
    dataset: { promptTemplateFormId: "" },
    querySelector: () => ({ value: "Synthetic template", checked: false }),
  };
  const state: any = { selectedModelId: "gpt-image-2.5-flare", promptTemplates: [] };
  const requests: any[] = [];
  const methods: any = { setStatus() {} };
  (globalThis as any).window = { __codexImageWebUI: { state, methods, els: {
    promptTemplateForm: { querySelector: () => form, classList: { add() {} }, addEventListener() {} },
  } } };
  (globalThis as any).document = { addEventListener() {} };
  globalThis.fetch = (async (_url: string, options: any) => {
    const payload = JSON.parse(options.body);
    requests.push({ method: options.method, payload });
    const existing = state.promptTemplates.find((item: any) => item.id === form.dataset.promptTemplateFormId);
    return { ok: true, json: async () => ({ templates: [{ ...existing, ...payload, id: "saved" }], categories: [] }) };
  }) as any;
  try {
    const { initPromptTemplatesFeature } = await import("../../codex_image/webui/frontend/src/prompt-templates");
    initPromptTemplatesFeature();
    for (const modelId of ["gpt-image-2", "gpt-image-2.5-flare", "gpt-image-2.5-sunburst", "nano-banana-2"]) {
      state.selectedModelId = modelId;
      form.dataset.promptTemplateFormId = "";
      await methods.savePromptTemplateFromDrawer();
      assert.equal(requests.at(-1).method, "POST");
      assert.equal(requests.at(-1).payload.model_hint, modelId);
      state.selectedModelId = "gpt-image-2";
      form.dataset.promptTemplateFormId = "saved";
      await methods.savePromptTemplateFromDrawer();
      assert.equal(requests.at(-1).method, "PATCH");
      assert.equal(Object.hasOwn(requests.at(-1).payload, "model_hint"), false);
      assert.equal(state.promptTemplates[0].model_hint, modelId);
    }
  } finally { Object.assign(globalThis, previous); }
});

test("size corrections satisfy provider limits without silently changing the source", () => {
  for (const [w, h] of [[16,16],[1,10000],[0,0],[9999,9999],[800,1200],[NaN,Infinity]]) {
    const result = suggestLegalSize(w!, h!);
    assert.ok(result.width >= 16 && result.width <= 3840);
    assert.ok(result.height >= 16 && result.height <= 3840);
    assert.equal(result.width % 16, 0); assert.equal(result.height % 16, 0);
    assert.ok(result.width * result.height >= 655360 && result.width * result.height <= 8294400);
    assert.ok(Math.max(result.width/result.height,result.height/result.width) <= 3);
  }
  assert.deepEqual(suggestLegalSize(1024,1024), {width:1024,height:1024});
  const square = suggestLegalSize(16,16); assert.equal(square.width, square.height);
});
test("credential errors require account repair while transient errors remain retryable", () => {
  for (const error of ['HTTP 401 invalid_api_key','401 Unauthorized','authentication_error','Incorrect API key provided']) assert.equal(taskRecoveryKind({error}), 'credentials');
  assert.equal(taskRecoveryKind({error:'HTTP 503 upstream unavailable'}),'temporary');
  assert.equal(taskRecoveryKind({last_error:'insufficient_quota'}),'quota');
  assert.equal(taskRecoveryKind({error:'unsupported mime type'}),'input');
});

test("draft restoration preserves prompt chips, files and image blobs across a destructive switch", async () => {
  const state: any = { images: [], referenceFiles: [], mode: 'generate', taskInputRestoreSeq: 0, selectedTaskId: null };
  let prompt = '';
  const restoreButton: any = { hidden: true, textContent: '' };
  const methods: any = {
    getPromptText: () => prompt, setPromptText: (value: string) => { prompt = value; },
    setMode: (mode: string) => { state.mode = mode; },
    revokeUploadPreviewUrls: (images: any[]) => images.forEach(image => URL.revokeObjectURL(image.previewUrl)),
  };
  (globalThis as any).window = { __codexImageWebUI: { state, methods, els: {} } };
  (globalThis as any).document = { getElementById: () => restoreButton };
  const drafts = await import('../../codex_image/webui/frontend/src/composer-draft');
  drafts.markComposerBaseline();
  const file = new File(['test'], 'reference.png', {type:'image/png'});
  prompt = 'draft @reference ~snippet #ffffff';
  state.images = [{kind:'upload',file,name:file.name,previewUrl:URL.createObjectURL(file),thumbnail_url:'data:image/webp;base64,c2NyaXB0'}];
  state.referenceFiles = [{id:'document-1',filename:'notes.pdf'}];
  const fingerprint = drafts.composerFingerprint();
  drafts.preserveComposerDraft();
  methods.revokeUploadPreviewUrls(state.images);
  state.images=[];state.referenceFiles=[];prompt=''; drafts.markComposerBaseline();
  drafts.restoreComposerDraft();
  assert.equal(prompt,'draft @reference ~snippet #ffffff');
  assert.equal(state.images[0].file,file); assert.equal(state.referenceFiles[0].id,'document-1');
  assert.equal(state.images[0].thumbnail_url,'data:image/webp;base64,c2NyaXB0');
  assert.equal(await (await fetch(state.images[0].previewUrl)).text(),'test');
  assert.equal(state.selectedTaskId,null); assert.equal(state.taskInputRestoreSeq,1);
  assert.equal(drafts.composerFingerprint(), fingerprint, "recreating a preview URL does not change draft identity");
  URL.revokeObjectURL(state.images[0].previewUrl);
});

test("reference read errors remain visible, retain inputs and release the button", async () => {
  const images = [{ id:'existing-reference' }];
  let status = '';
  const methods: any = {
    setStatus: (message: string) => { status = message; },
    imageFileFromUrl: async () => { throw new Error('图片读取失败：404'); },
    addImageFiles: () => { throw new Error('must not add a failed resource'); },
  };
  const feedback: any = { textContent:'', setAttribute() {} };
  const anchor: any = { disabled:false, parentElement:{querySelector:()=>feedback}, setAttribute() {}, removeAttribute() {} };
  (globalThis as any).window = {__codexImageWebUI:{state:{images},methods,els:{}}};
  const { initLightboxFeature } = await import('../../codex_image/webui/frontend/src/lightbox');
  initLightboxFeature();
  await (globalThis as any).window.addToInput('/missing-image.png', anchor);
  assert.match(status,/404/); assert.match(feedback.textContent,/未能加入/);
  assert.equal(anchor.disabled,false); assert.equal(images.length,1);
});


test("provider resolution clears only the stale Codex health warning", async () => {
  const statusText: any = { textContent: "No Codex session detected", dataset: {statusSource:"codex-health"} };
  const state: any = {
    generationCatalog: { models: [{id:"gpt-image-2",family_id:"gpt-image"}], providers: [], default_provider_by_model: {}, codex: {mode:"images",available:false} },
    selectedModelId: "gpt-image-2", mode:"generate", lastProviderSelectionByModel:{}, lastProviderByModel:{},
  };
  const runButton = {disabled:false};
  (globalThis as any).window = {__codexImageWebUI:{state,els:{statusText,runButton},methods:{
    setStatus: (message: string) => {statusText.textContent=message;delete statusText.dataset.statusSource;},
  }}};
  const { renderProviderSelection } = await import('../../codex_image/webui/frontend/src/provider-selection');
  renderProviderSelection();
  assert.equal(statusText.textContent, ""); assert.equal(runButton.disabled,true);
  state.generationCatalog.providers=[{id:"api",name:"API",available:true,bindings:[{id:"image",canonical_model_id:"gpt-image-2",operations:["generate"],available:true}]}];
  statusText.textContent="Task request failed: 503";
  renderProviderSelection();
  assert.equal(statusText.textContent,"Task request failed: 503");
  assert.equal(runButton.disabled,false); assert.equal(state.selectedProviderId,"api");
});

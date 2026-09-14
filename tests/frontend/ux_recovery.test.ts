import assert from "node:assert/strict";
import test from "node:test";
import { suggestLegalSize } from "../../codex_image/webui/frontend/src/size-suggestion";
import { taskRecoveryKind } from "../../codex_image/webui/frontend/src/task-recovery";

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
  state.images = [{kind:'upload',file,name:file.name,previewUrl:URL.createObjectURL(file)}];
  state.referenceFiles = [{id:'document-1',filename:'notes.pdf'}];
  drafts.preserveComposerDraft();
  methods.revokeUploadPreviewUrls(state.images);
  state.images=[];state.referenceFiles=[];prompt=''; drafts.markComposerBaseline();
  drafts.restoreComposerDraft();
  assert.equal(prompt,'draft @reference ~snippet #ffffff');
  assert.equal(state.images[0].file,file); assert.equal(state.referenceFiles[0].id,'document-1');
  assert.equal(await (await fetch(state.images[0].previewUrl)).text(),'test');
  assert.equal(state.selectedTaskId,null); assert.equal(state.taskInputRestoreSeq,1);
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
    generationCatalog: { models: [], providers: [], default_provider_by_model: {}, codex: {mode:"images",available:false} },
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

/** Real controls and editor with synthetic local images; never calls a provider. */
import { loadAcceptanceFrame, prepareFixtureOrigin } from "./browser_acceptance";
const frame = document.querySelector<HTMLIFrameElement>("#historyFrame")!;
const output = document.querySelector<HTMLElement>("#results")!;
const failures: any[] = [], errors: string[] = [];
let assertions = 0;
const pause = (ms = 100) => new Promise(resolve => setTimeout(resolve, ms));
function check(name: string, pass: boolean, detail?: unknown) { assertions++; if (!pass) failures.push({ name, detail }); }

async function run() {
  await prepareFixtureOrigin(); localStorage.clear();
  await loadAcceptanceFrame(frame, "/qa-app", errors);
  const w = frame.contentWindow!, d = frame.contentDocument!;
  const find = <T extends HTMLElement = HTMLElement>(selector: string) => d.querySelector<T>(selector)!;
  const until = async (predicate: () => boolean) => { const end = Date.now() + 15000; while (!predicate()) { if (Date.now() > end) throw new Error("initialization timed out"); await pause(); } };
  await until(() => !!w.__codexImageWebUI?.state.generationCatalog);
  const { state, methods } = w.__codexImageWebUI!;
  state.generationCatalog.providers.push({ id: "qa-image26", name: "Synthetic Image 2.6", builtin: false, available: true, bindings: [{
    id: "image26", canonical_model_id: "gpt-image-2.6-flare", remote_model_id: "gpt-image-2.6-flare",
    protocol_profile: "openai_images", parameter_codec: "gpt_openai_images", operations: ["generate", "edit"],
  }] });
  methods.selectConcreteModel("gpt-image-2.6-flare");
  methods.selectGenerationProvider("qa-image26");
  const input = (selector: string, value: string) => { const e = find<HTMLInputElement>(selector); e.value = value; e.dispatchEvent(new w.Event("input", {bubbles: true})); e.dispatchEvent(new w.Event("change", {bubbles: true})); };
  const params = () => methods.currentCanonicalParameters();
  const button = find<HTMLButtonElement>("#outputCompressionButton"), popup = find("#compressionPopover");
  for (const theme of ["light", "dark"]) {
    find(`[data-theme-option="${theme}"]`).click();
    for (const [width, height] of [[1512, 773], [1280, 699], [375, 812]]) {
      frame.style.width = `${width}px`; frame.style.height = `${height}px`; await pause(250);
      if (d.body.classList.contains("mobile-ui")) { find(".mobile-parameters-button").click(); await pause(); }
      const name = `${theme} ${width}x${height}`;
      input("#outputFormat", "gif"); input("#frameCount", "12"); input("#frameDuration", "100");
      input("#quality", "max"); input("#complexity", "low");
      button.scrollIntoView({ block: "center" }); await pause(); button.click(); await pause();
      const box = popup.getBoundingClientRect();
      check(`${name}: GIF options inside popover`, !popup.classList.contains("hidden") && popup.contains(find("#frameCount")) && d.activeElement === find("#frameCount"));
      check(`${name}: popover contained`, box.left >= 0 && box.right <= w.innerWidth && box.top >= 0 && box.bottom <= w.innerHeight, { left: box.left, right: box.right, top: box.top, bottom: box.bottom });
      check(`${name}: duration calculation`, find("#gifDuration").textContent === "1.2 s");
      check(`${name}: no irrelevant controls`, find<HTMLInputElement>("#compression").disabled && find<HTMLInputElement>("#transparentBackground").disabled);
      check(`${name}: canonical request`, params()["gpt.complexity"] === "low" && params()["gpt.quality"] === "max" && params()["gpt.frame_count"] === 12 && !("gpt.output_compression" in params()));
      const quality = find(".quality-field").getBoundingClientRect(), row = find(".quantity-quality-row").getBoundingClientRect();
      check(`${name}: quality spans row`, Math.abs(quality.width - row.width) < 1);
      check(`${name}: no panel horizontal overflow`, find("#outputFileSettings").scrollWidth <= find("#outputFileSettings").clientWidth + 1);
      find("#frameCount").dispatchEvent(new w.KeyboardEvent("keydown", {key: "Escape", bubbles: true}));
      check(`${name}: Escape returns focus`, popup.classList.contains("hidden") && d.activeElement === button);
      input("#outputFormat", "png"); check(`${name}: animation fields omitted for PNG`, !("gpt.frame_count" in params()));
      input("#outputFormat", "gif"); check(`${name}: GIF values retained`, params()["gpt.frame_count"] === 12 && params()["gpt.frame_duration_ms"] === 100);
      if (d.body.classList.contains("mobile-ui")) find("#mobileParameters .drawer-close-button").click();
    }
  }
  frame.style.width = "1280px"; frame.style.height = "800px"; await pause(250);
  const lockedParams = params();
  find('#outputSettingsLockButton').click(); find('#outputSettingsLockButton').click();
  check("unlock preserves complexity and GIF timing", JSON.stringify(params()) === JSON.stringify(lockedParams), params());
  find('#outputSettingsLockButton').click();
  find<HTMLInputElement>('#frameCount').value = '2'; find<HTMLInputElement>('#frameDuration').value = '200'; find<HTMLSelectElement>('#complexity').value = 'high';
  methods.restoreOutputSettingsLock();
  check("persisted lock restores complexity and GIF timing", JSON.stringify(params()) === JSON.stringify(lockedParams), params());
  find('#outputSettingsLockButton').click();
  const historical = { ...state.tasks[0], summary_only: false, mode: 'generate', prompt: 'Synthetic GIF history', input_sources: [], local_input_files: [], reference_files: [], generation_snapshot: {
    canonical_model_id: 'gpt-image-2.6-flare', provider_id: 'qa-image26', protocol_profile: 'openai_images',
    requested_parameters: { ...lockedParams, 'canvas.size': '512x512' },
  } };
  state.tasks[0] = historical;
  methods.selectConcreteModel('gpt-image-2');
  const olderParams = params();
  await methods.selectTask(historical.task_id);
  check("cross-version history opens the inspector", !find('#taskParameterInspector').classList.contains('hidden'));
  check("cross-version history preserves current request until adoption", JSON.stringify(params()) === JSON.stringify(olderParams));
  find('#taskParameterInspector .task-parameter-adopt').click();
  check("adoption selects the compatible historical model", state.selectedModelId === 'gpt-image-2.6-flare' && state.selectedProviderId === 'qa-image26');
  check("adoption preserves GIF format, dimensions and timing", params()['output.format'] === 'gif' && params()['canvas.size'] === '512x512' && params()['gpt.frame_count'] === 12 && params()['gpt.frame_duration_ms'] === 100 && params()['gpt.complexity'] === 'low', params());
  find('[data-custom-size-mode="custom"]').click();
  input("#customWidth", "512"); input("#customHeight", "512"); input("#frameCount", "64");
  check("small GIF canvas allows 64 frames", params()["canvas.size"] === "512x512" && find<HTMLInputElement>("#frameCount").checkValidity(), {size: params()["canvas.size"], width: find<HTMLInputElement>("#customWidth").value, height: find<HTMLInputElement>("#customHeight").value, max: find<HTMLInputElement>("#frameCount").max});
  input("#customWidth", "3840"); input("#customHeight", "3840");
  check("GIF frame limit follows canvas pixel budget", Number(find<HTMLInputElement>("#frameCount").max) === 9 && !find<HTMLInputElement>("#frameCount").checkValidity());
  check("invalid GIF frame count remains editable", find<HTMLInputElement>("#frameCount").value === "64");
  input("#frameCount", "9");
  check("GIF frame limit accepts a corrected value", find<HTMLInputElement>("#frameCount").checkValidity());
  find('[data-custom-size-mode="preset"]').click(); input("#frameCount", "12");
  methods.setMode("edit");
  check("edit mode excludes generated formats", find<HTMLSelectElement>("#outputFormat").value === "png" && [...find<HTMLSelectElement>("#outputFormat").options].filter(option => ["svg", "gif"].includes(option.value)).every(option => option.disabled));
  const canvas = d.createElement("canvas"); canvas.width = 8192; canvas.height = 512;
  const ctx = canvas.getContext("2d")!; ctx.fillStyle = "#457b66"; ctx.fillRect(0, 0, 8192, 512);
  const blob = await new Promise<Blob>(resolve => canvas.toBlob(value => resolve(value!), "image/png"));
  const file = new w.File([blob], "synthetic.png", { type: "image/png" });
  methods.addImageFiles([file]); await pause();
  const original = state.images[0].file;
  await methods.openImageEditor(0);
  find('[data-image-editor-mode="markup"]').click(); await pause();
  check("markup mode keeps image geometry fixed", find("#imageEditorModal").classList.contains("markup-mode") && w.getComputedStyle(find('[data-image-editor-tool="crop"]')).display === "none");
  const surface = find("#imageEditorKonvaMount .konvajs-content"); const rect = surface.getBoundingClientRect();
  const draw = (type: string, x: number) => surface.dispatchEvent(new w.PointerEvent(type, {bubbles: true, pointerId: 7, button: 0, buttons: type === "pointerup" ? 0 : 1, clientX: rect.left + rect.width * x, clientY: rect.top + rect.height * .5 }));
  draw("pointerdown", .25); draw("pointermove", .75); draw("pointerup", .75); await pause();
  const mount = find('#imageEditorKonvaMount');
  find('#imageEditorUndo').click();
  check("markup undo preserves original wide coordinates", mount.style.getPropertyValue('--image-editor-stage-raw-width') === '8192px' && find<HTMLCanvasElement>('#imageEditorCanvas').width === 8192);
  find('#imageEditorRedo').click();
  check("markup redo preserves original wide coordinates", mount.style.getPropertyValue('--image-editor-stage-raw-width') === '8192px' && find<HTMLCanvasElement>('#imageEditorCanvas').width === 8192);
  find("#imageEditorSave").click(); await until(() => find("#imageEditorModal").classList.contains("hidden"));
  check("markup preserves base file", state.images[0].file === original);
  const markup = state.images[0].markupFile;
  check("markup saved as separate PNG", !!markup && markup.type === "image/png");
  if (markup) {
    const bitmap = await w.createImageBitmap(markup); const layer = d.createElement("canvas"); layer.width = bitmap.width; layer.height = bitmap.height;
    const layerCtx = layer.getContext("2d")!; layerCtx.drawImage(bitmap, 0, 0); bitmap.close();
    const pixels = layerCtx.getImageData(0, 0, layer.width, layer.height).data;
    check("markup has matching dimensions and transparent background", layer.width === 8192 && layer.height === 512 && pixels.some((v, i) => i % 4 === 3 && v === 0) && pixels.some((v, i) => i % 4 === 3 && v > 0));
    await methods.openImageEditor(0); await pause();
    check("saved markup reopens in markup mode", find("#imageEditorModal").classList.contains("markup-mode"));
    check("reopened markup retains original wide coordinates", mount.style.getPropertyValue('--image-editor-stage-raw-width') === '8192px');
    find("#imageEditorClose").click();
  }
  methods.selectConcreteModel("gpt-image-2");
  check("Image 2 keeps its original controls", find("#complexityField").classList.contains("hidden") && find('#qualityGroup [data-val="max"]').classList.contains("hidden") && !find("#outputFormatGroup").classList.contains("hidden"));
  return {passed: !failures.length && !errors.length, assertions, failures, errors};
}
void run().catch(error => ({passed: false, assertions, failures, errors: [...errors, String(error)]})).then(async report => { output.textContent = JSON.stringify(report); await fetch("/qa-results", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(report)}); });

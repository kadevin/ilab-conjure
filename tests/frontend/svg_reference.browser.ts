/** Real SVG rasterization and edit validation; the fixture never runs its queue. */
import { loadAcceptanceFrame, prepareFixtureOrigin } from "./browser_acceptance";

const frame = document.querySelector<HTMLIFrameElement>("#historyFrame")!;
const output = document.querySelector<HTMLElement>("#results")!;
const errors: string[] = [], failures: string[] = [];
let assertions = 0;
const pause = () => new Promise(resolve => setTimeout(resolve, 40));
function check(name: string, passed: boolean) { assertions++; if (!passed) failures.push(name); }
async function until(predicate: () => boolean) {
  const end = Date.now() + 10000;
  while (!predicate()) { if (Date.now() > end) throw new Error("Initialization timed out"); await pause(); }
}

async function run() {
  await prepareFixtureOrigin(); localStorage.clear();
  const model = "gpt-image-2.6-flare", provider = "qa-svg-reference";
  const seeded = await fetch("/api/api-settings", { method: "PATCH", headers: {"Content-Type": "application/json"}, body: JSON.stringify({
    schema_version: 2, codex_mode: "images", active_provider_id: provider,
    default_provider_by_model: { [model]: provider }, providers: [{
      id: provider, name: "Synthetic SVG reference", base_url: "https://relay.example/v1", api_key: "synthetic-only", concurrency: 1,
      bindings: [{id: "svg-reference", canonical_model_id: model, remote_model_id: model,
        protocol_profile: "openai_images", parameter_codec: "gpt_openai_images", operations: ["generate", "edit"]}],
    }],
  }) });
  if (!seeded.ok) throw new Error(`Fixture settings failed: ${seeded.status}`);
  await loadAcceptanceFrame(frame, "/qa-app", errors);
  const w = frame.contentWindow!, d = frame.contentDocument!;
  await until(() => !!w.__codexImageWebUI?.state.generationCatalog);
  const {state, methods, els} = w.__codexImageWebUI!;
  methods.selectConcreteModel(model); methods.selectGenerationProvider(provider);
  const input = (selector: string, value: string) => {
    const element = d.querySelector<HTMLInputElement>(selector)!; element.value = value;
    element.dispatchEvent(new w.Event("change", {bubbles: true}));
  };
  const validatePng = async (file: File, width: number, height: number, label: string) => {
    check(`${label}: PNG bytes and name`, file.type === "image/png" && file.name.endsWith(".png") && !file.name.endsWith(".svg.png") && new Uint8Array(await file.arrayBuffer())[0] === 137);
    const bitmap = await w.createImageBitmap(file);
    check(`${label}: dimensions retained`, bitmap.width === width && bitmap.height === height);
    const canvas = d.createElement("canvas"); canvas.width = width; canvas.height = height;
    const context = canvas.getContext("2d")!; context.drawImage(bitmap, 0, 0); bitmap.close();
    const foreground = context.getImageData(4, 4, 1, 1).data;
    check(`${label}: content and alpha retained`, foreground[0] === 255 && foreground[3] === 255 && context.getImageData(width - 1, height - 1, 1, 1).data[3] === 0);
  };
  const svgUrl = "/qa-svg-reference/fixed.svg";
  const original = await (await fetch(svgUrl)).text();
  await w.addToInput!(svgUrl);
  check("direct add changes to edit", state.mode === "edit" && state.images.length === 1);
  const png = state.images[0].file;
  await validatePng(png, 64, 32, "direct add");
  check("direct add has the correct extension", png.name === "fixed.png");
  const form = new w.FormData();
  form.set("prompt", "Synthetic SVG reuse"); form.set("canonical_model_id", model); form.set("provider_id", provider);
  form.set("parameters_json", JSON.stringify({"output.format": "svg"})); form.append("images", png);
  const submitted = await fetch("/api/edit", { method: "POST", body: form });
  const queued = await submitted.json();
  check("PNG reference accepted by real edit API with SVG output", submitted.ok && queued.task?.status === "queued" && queued.task?.mode === "edit" && queued.task?.generation_snapshot?.requested_parameters?.["output.format"] === "svg");
  check("original SVG download remains unchanged", await (await fetch(svgUrl)).text() === original);

  methods.collectReferenceOutput("/qa-svg-reference/viewbox.svg", {name: "viewbox.svg"});
  await methods.addCollectedReferencesToInput();
  check("staged reference added and staging cleared", state.images.length === 2 && state.collectedReferences.length === 0);
  await validatePng(state.images[1].file, 80, 40, "viewBox-only staged SVG");
  localStorage.setItem("codex-image-history-reference-handoff", JSON.stringify([{url: svgUrl, name: "fixed.svg"}]));
  await methods.restoreHistoryReferenceHandoff();
  check("history handoff uses PNG and clears its message", state.images.length === 3 && state.images[2].file.type === "image/png" && !localStorage.getItem("codex-image-history-reference-handoff"));
  const rasterUrl = "/api/tasks/qa-history-0000/outputs/1/thumbnail";
  const raster = await (await fetch(rasterUrl)).blob();
  const reused = await methods.imageFileFromUrl(rasterUrl, "reference.png");
  check("raster reference bytes and MIME are unchanged", reused.type === raster.type && String(new Uint8Array(await reused.arrayBuffer())) === String(new Uint8Array(await raster.arrayBuffer())));
  const previousFiles = state.images.map((item: any) => item.file);
  methods.collectReferenceOutput("/qa-svg-reference/oversized.svg", {name: "oversized.svg"});
  await methods.addCollectedReferencesToInput({replace: true});
  check("failed conversion preserves existing inputs and staged item", state.images.length === previousFiles.length && state.images.every((item: any, index: number) => item.file === previousFiles[index]) && state.collectedReferences.length === 1);
  check("failed conversion has an actionable message", els.statusText.textContent.includes("PNG"));

  // Exercise the real request error boundary in both languages without running queued tasks.
  input("#outputFormat", "gif"); methods.setPromptText("Synthetic GIF validation");
  const originalFetch = w.fetch.bind(w);
  let inject = "", requests = 0;
  w.fetch = (async (request: RequestInfo | URL, init?: RequestInit) => {
    if (String(request) === "/api/edit" && init?.method === "POST") {
      requests++;
      const body = init.body as FormData;
      if (inject === "mask") body.append("mask", png, "mask.png");
      else {
        const parameters = JSON.parse(String(body.get("parameters_json")));
        parameters["gpt.output_compression"] = 80; body.set("parameters_json", JSON.stringify(parameters));
      }
    }
    return originalFetch(request, init);
  }) as typeof w.fetch;
  try {
    for (const [locale, maskText, compressionText] of [["zh-CN", "移除蒙版", "移除压缩参数"], ["en", "Remove the mask", "Remove compression"]]) {
      input("#languageSelect", locale); await pause();
      for (const [kind, expected] of [["mask", maskText], ["compression", compressionText]]) {
        inject = kind;
        const before = requests;
        await methods.runTask();
        check(`${locale}: ${kind} failure makes one request`, requests === before + 1);
        check(`${locale}: ${kind} failure gives a localized remedy`, els.statusText.textContent.includes(expected));
      }
    }
  } finally { w.fetch = originalFetch; }
  return {passed: !failures.length && !errors.length, assertions, failures, errors};
}
void run().catch(error => ({passed: false, assertions, failures, errors: [...errors, String(error.stack || error)]})).then(async report => {
  output.textContent = JSON.stringify(report);
  await fetch("/qa-results", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(report)});
});

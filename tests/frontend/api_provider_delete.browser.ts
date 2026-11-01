/** Delete/failed-write acceptance against isolated real settings storage. */
import { loadAcceptanceFrame, prepareFixtureOrigin } from "./browser_acceptance";

const frame = document.querySelector<HTMLIFrameElement>("#historyFrame")!;
const output = document.querySelector<HTMLElement>("#results")!;
const errors: string[] = [];
const failures: string[] = [];
let assertions = 0;
function check(name: string, pass: boolean) { assertions++; if (!pass) failures.push(name); }
const pause = (ms = 30) => new Promise(resolve => setTimeout(resolve, ms));
async function until(condition: () => boolean | Promise<boolean>, description: string) {
  const deadline = Date.now() + 10000;
  while (!await condition()) {
    if (Date.now() >= deadline) throw new Error(`Timed out: ${description}`);
    await pause();
  }
}
const ids = (settings: any) => settings.providers.map((p: any) => p.id).join(",");
const readSaved = async () => (await (await fetch("/api/api-settings")).json()).settings;

async function run() {
  await prepareFixtureOrigin();
  localStorage.clear();
  localStorage.setItem("codex-image-locale-preference", "zh-CN");
  const provider = (id: string, models: string[]) => ({
    id, name: `QA ${id}`, base_url: "https://relay.example/v1", api_key: "synthetic-qa-key",
    concurrency: 3, bindings: models.map((model, i) => ({
      id: `${id}-${i}`, canonical_model_id: model, remote_model_id: model,
      protocol_profile: "openai_images", parameter_codec: model.startsWith("gpt") ? "gpt_openai_images" : "gemini_openai_images",
      operations: ["generate", "edit"],
    })),
  });
  const seed = {
    schema_version: 2, codex_mode: "images", active_provider_id: "a",
    providers: [provider("a", ["gpt-image-2", "nano-banana-2"]),
      provider("b", ["gpt-image-2", "nano-banana-2"]), provider("c", ["nano-banana-2-lite"])],
    default_provider_by_model: { "gpt-image-2": "b", "nano-banana-2": "a", "nano-banana-2-lite": "c" },
  };
  const seeded = await fetch("/api/api-settings", { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify(seed) });
  if (!seeded.ok) throw new Error(`Fixture settings failed: ${seeded.status}`);
  await loadAcceptanceFrame(frame, "/qa-app", errors);
  const w = frame.contentWindow!, d = frame.contentDocument!;
  const { state, methods } = w.__codexImageWebUI!;
  await until(() => ids(state.apiSettings) === "a,b,c" && !!state.generationCatalog, "initial settings");
  methods.selectGenerationProvider!("a");
  methods.persistApiSettings!();
  methods.openApiSettingsModal!();
  const find = <T extends HTMLElement = HTMLElement>(selector: string) => d.querySelector<T>(selector)!;
  const panel = find("#systemSettingsApiPanel");
  const confirmDelete = async () => {
    find("#deleteApiProviderButton").click();
    await until(() => !!d.querySelector("[data-confirm-popover-confirm]"), "delete confirmation");
    find("[data-confirm-popover-confirm]").click();
  };
  const originalFetch = w.fetch.bind(w);
  let writes = 0;
  let release: (() => void) | undefined;
  let rejectWith = "default_provider_mapping_missing";
  w.fetch = (async (request: RequestInfo | URL, init?: RequestInit) => {
    if (String(request) === "/api/api-settings" && init?.method === "PATCH") {
      writes++;
      await new Promise<void>(resolve => { release = resolve; });
      if (rejectWith === "offline") throw new TypeError("Synthetic network failure");
      if (rejectWith) return new w.Response(JSON.stringify({ detail: rejectWith }), { status: 400 });
    }
    return originalFetch(request, init);
  }) as typeof w.fetch;
  for (const [theme, width, failure] of [["light", 1366, "default_provider_mapping_missing"], ["dark", 390, "offline"]] as const) {
    find(`[data-theme-option="${theme}"]`).click();
    frame.style.width = `${width}px`; frame.style.height = "768px";
    await pause(300);
    rejectWith = failure; release = undefined;
    const before = JSON.stringify(state.apiSettings);
    const beforeSelection = JSON.stringify([state.selectedProviderId, state.selectedProviderBindingId, state.lastProviderByModel, state.lastProviderSelectionByModel]);
    const beforeStorage = localStorage.getItem("codex-image-api-settings");
    const beforeWrites = writes;
    await confirmDelete();
    await until(() => !!release, "pending deletion");
    check(`${theme}: pending delete leaves card and selection intact`, ids(state.apiSettings) === "a,b,c" && state.apiSettings.active_provider_id === "a");
    check(`${theme}: controls are busy`, panel.hasAttribute("inert") && panel.getAttribute("aria-busy") === "true");
    await methods.deleteApiProvider!();
    methods.selectApiProvider!("b");
    methods.addApiProvider!();
    await pause(350);
    check(`${theme}: repeated actions cannot race the save`, writes === beforeWrites + 1 && !state.apiProviderEditingId && state.apiSettings.active_provider_id === "a");
    release!();
    await until(() => !panel.hasAttribute("aria-busy"), "failed delete settled");
    check(`${theme}: failed delete preserves settings`, JSON.stringify(state.apiSettings) === before);
    check(`${theme}: failed delete preserves generation selection`, JSON.stringify([state.selectedProviderId, state.selectedProviderBindingId, state.lastProviderByModel, state.lastProviderSelectionByModel]) === beforeSelection);
    check(`${theme}: browser cache has no phantom deletion`, localStorage.getItem("codex-image-api-settings") === beforeStorage);
    check(`${theme}: failed delete did not reach storage`, ids(await readSaved()) === "a,b,c");
    check(`${theme}: error is visible and controls recover`, find("#apiSettingsStatus").classList.contains("error") && !panel.hasAttribute("inert"));
    check(`${theme}: error code is not exposed`, !find("#apiSettingsStatus").textContent?.includes("default_provider_mapping_missing"));
    check(`${theme}: failure returns focus to delete`, d.activeElement === find("#deleteApiProviderButton"));
    check(`${theme}: panel stays within viewport`, panel.scrollWidth <= panel.clientWidth + 1);
  }
  rejectWith = ""; release = undefined;
  await confirmDelete();
  await until(() => !!release, "successful deletion pending");
  release!();
  await until(() => ids(state.apiSettings) === "b,c" && !panel.hasAttribute("aria-busy"), "successful deletion committed");
  w.fetch = originalFetch;
  let saved = await readSaved();
  check("successful delete is persisted with complete defaults", ids(saved) === "b,c" && saved.default_provider_by_model["nano-banana-2"] === "b" && saved.default_provider_by_model["gpt-image-2"] === "b");
  check("remaining secrets stay saved and absent from browser inputs", saved.providers.every((p: any) => p.api_key_set && !p.api_key) && !find<HTMLInputElement>("#apiKey").value);
  check("generation selection moves off deleted supplier", state.selectedProviderId === "b");
  methods.selectApiProvider!("c");
  await until(() => find("#apiSettingsStatus").textContent === "" && state.apiSettings.active_provider_id === "c", "selection changed");
  await until(async () => (await readSaved()).active_provider_id === "c" && !panel.hasAttribute("aria-busy"), "selection saved");
  check("switching suppliers after deletion persists without mapping errors", (await readSaved()).active_provider_id === "c" && !find("#apiSettingsStatus").classList.contains("error"));
  await confirmDelete();
  await until(() => ids(state.apiSettings) === "b" && !panel.hasAttribute("aria-busy"), "second deletion committed");
  saved = await readSaved();
  check("deleting last supporter removes only its obsolete default", !("nano-banana-2-lite" in saved.default_provider_by_model) && saved.default_provider_by_model["nano-banana-2"] === "b");
  check("last provider remains protected", find<HTMLButtonElement>("#deleteApiProviderButton").disabled);
  await loadAcceptanceFrame(frame, "/qa-app?after-delete", errors);
  const reloaded = frame.contentWindow!.__codexImageWebUI!;
  await until(() => ids(reloaded.state.apiSettings) === "b" && !!reloaded.state.generationCatalog, "reload restores saved deletion");
  reloaded.methods.openApiSettingsModal!();
  check("refresh cannot resurrect deleted suppliers", ids(reloaded.state.apiSettings) === "b" && frame.contentDocument!.querySelectorAll("#apiProviderList [data-api-provider-id]").length === 1);
  check("no application errors", errors.length === 0);
  return { passed: failures.length === 0 && errors.length === 0, assertions, failures, errors };
}
void run().catch(error => ({ passed: false, assertions, failures, errors: [...errors, String(error)] }))
  .then(async report => {
    output.textContent = JSON.stringify(report);
    await fetch("/qa-results", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(report) });
  });

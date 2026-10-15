/** Host image-mention and clipboard suites against the isolated real WebUI. */
import { loadAcceptanceFrame, prepareFixtureOrigin } from "./browser_acceptance";

const suite = location.pathname.split("/").at(-1)!;
const scripts: Record<string, string> = {
  "image-mentions": "image_mentions.browser",
  "prompt-paste": "prompt_paste.browser",
};
const frame = document.querySelector<HTMLIFrameElement>("#historyFrame")!;
const output = document.querySelector<HTMLElement>("#results")!;
const errors: string[] = [];

async function until(check: () => boolean, name: string): Promise<void> {
  const deadline = Date.now() + 15000;
  while (true) {
    if (errors.length) throw new Error(`Application runtime failed: ${errors.join("; ")}`);
    if (check()) return;
    if (Date.now() > deadline) throw new Error(`Timeout: ${name}`);
    await new Promise(resolve => setTimeout(resolve, 50));
  }
}

async function run(): Promise<Record<string, unknown>> {
  await prepareFixtureOrigin();
  // The mention suite verifies the Chinese reference labels explicitly.
  localStorage.setItem("codex-image-locale-preference", "zh-CN");
  const before = await fetch("/qa-unexpected-requests").then(response => response.json());
  await loadAcceptanceFrame(frame, "/qa-app", errors);
  const win = frame.contentWindow!;
  const doc = frame.contentDocument!;
  await until(() => Boolean(win.__codexImageWebUI?.state.generationCatalog), "application catalog");
  const script = doc.createElement("script");
  script.src = `/qa-script/${scripts[suite]}.js`;
  doc.body.append(script);
  let report: { passed: boolean; [key: string]: unknown } | undefined;
  await until(() => {
    const text = suite === "image-mentions"
      ? doc.querySelector("#image-mention-test-results")?.textContent
      : doc.body.textContent;
    try { report = JSON.parse(text || ""); } catch { return false; }
    return typeof report?.passed === "boolean";
  }, "suite results");
  const after = await fetch("/qa-unexpected-requests").then(response => response.json());
  const unexpectedRequests = after.requests.slice(before.requests.length);
  return { ...report, suite, errors, unexpectedRequests,
    passed: report!.passed && errors.length === 0 && unexpectedRequests.length === 0 };
}

void run().catch(error => ({ suite, passed: false, fatal: String(error), errors })).then(async report => {
  output.textContent = JSON.stringify(report);
  await fetch("/qa-results", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(report) });
});

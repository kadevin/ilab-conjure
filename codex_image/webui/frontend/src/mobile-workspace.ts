import { LOCALE_CHANGE_EVENT, translate } from "./i18n";
import { createMobileSheet, MOBILE_WORKSPACE_QUERY } from "./mobile-shell";
import { getLegacyBridge } from "./state";

export function initMobileWorkspace(): void {
  const output = document.querySelector<HTMLElement>(".output-panel");
  const run = document.getElementById("runButton");
  const dashboard = document.querySelector<HTMLElement>(".dashboard");
  const preview = document.querySelector<HTMLElement>(".preview-panel");
  if (!output || !run || !dashboard || !preview) return;
  const query = window.matchMedia(MOBILE_WORKSPACE_QUERY);
  const sheet = createMobileSheet("mobileParameters", "outputSettings.title");
  const lock = document.getElementById("outputSettingsLockButton");
  const lockOrigin = document.createComment("mobile-output-lock-origin");
  lock?.before(lockOrigin);
  const sheetHeader = sheet.root.querySelector(".mobile-sheet-heading");
  const outputOrigin = document.createComment("mobile-output-origin");
  const runOrigin = document.createComment("mobile-run-origin");
  output.before(outputOrigin); run.before(runOrigin);
  const summary = document.createElement("button");
  summary.type = "button";
  summary.className = "mobile-parameter-summary ghost-button";
  const summaryLabel = document.createElement("strong");
  const summaryValue = document.createElement("span");
  summary.append(summaryLabel, summaryValue);
  output.after(summary);
  const dock = document.createElement("div");
  dock.className = "mobile-generate-dock";
  const parameters = document.createElement("button");
  parameters.type = "button";
  parameters.className = "ghost-button mobile-parameters-button";
  for (const button of [parameters, summary]) {
    button.setAttribute("aria-controls", sheet.root.id);
    button.setAttribute("aria-expanded", "false");
    button.addEventListener("click", () => sheet.open(button));
  }
  dock.append(parameters); document.querySelector(".layout-container")!.append(dock);
  const back = document.createElement("button");
  back.type = "button"; back.className = "ghost-button mobile-return-edit";
  preview.querySelector(".preview-heading")?.append(back);
  let editorScroll = 0;
  const showPreview = () => {
    if (!query.matches) return;
    sheet.close();
    editorScroll = dashboard.scrollTop;
    if (document.activeElement instanceof HTMLElement) document.activeElement.blur();
    requestAnimationFrame(() => {
      preview.scrollIntoView({ block: "start" });
      preview.focus({ preventScroll: true });
    });
  };
  const showEditor = () => {
    dashboard.scrollTop = editorScroll;
    const prompt = document.getElementById("promptEditor");
    prompt?.scrollIntoView({ block: "nearest" });
    prompt?.focus({ preventScroll: true });
  };
  back.addEventListener("click", showEditor);
  getLegacyBridge().methods.showGenerationEditor = showEditor;
  getLegacyBridge().methods.showMobilePreview = showPreview;
  const feedback = document.getElementById("statusText");
  const feedbackOrigin = document.createComment("mobile-feedback-origin");
  feedback?.before(feedbackOrigin);
  const sync = () => {
    sheet.close();
    if (query.matches) {
      sheet.content.append(output); dock.append(run);
      if (lock && sheetHeader) sheetHeader.insertBefore(lock, sheetHeader.lastElementChild);
      if (feedback) summary.before(feedback);
    } else {
      outputOrigin.after(output); runOrigin.after(run);
      if (lock) lockOrigin.after(lock);
      if (feedback) feedbackOrigin.after(feedback);
    }
  };
  const label = () => {
    parameters.textContent = translate("mobile.parameters");
    summaryLabel.textContent = `${translate("outputSettings.title")} ›`;
    back.textContent = translate("mobile.backToEditor");
  };
  label(); document.addEventListener(LOCALE_CHANGE_EVENT, label);
  const execution = document.getElementById("executionSummary");
  const syncSummary = () => { summaryValue.textContent = execution?.textContent || ""; };
  if (execution) new MutationObserver(syncSummary).observe(execution, { childList: true, characterData: true, subtree: true });
  syncSummary(); query.addEventListener("change", sync); sync();
}

import { translate } from "./i18n";
import { escapeHtml } from "./webui-utils";

export function submittedPromptForTask(task: any): string {
  return [task?.prompt_for_model || task?.prompt || "", task?.generation_snapshot?.transparency_instruction || ""]
    .filter(Boolean).join("\n\n");
}

export function requestedTransparentBackground(task: any): boolean {
  return (task?.generation_snapshot?.requested_parameters?.["gpt.background"]
    ?? task?.request?.parameters?.["gpt.background"]
    ?? task?.params?.background) === "transparent";
}

export function transparencyStatus(hasTransparency: unknown, requested: boolean): { label: string; hint: string } | null {
  if (hasTransparency === true) return { label: translate("preview.transparencyDetected"), hint: "" };
  if (hasTransparency === false && requested) {
    return { label: translate("preview.transparencyMissing"), hint: translate("preview.transparencyRetryHint") };
  }
  return null;
}

export function transparencyStatusHtml(hasTransparency: unknown, requested: boolean): string {
  const status = transparencyStatus(hasTransparency, requested);
  return status ? `<span class="output-transparency-status" title="${escapeHtml(status.hint || status.label)}">${escapeHtml(status.label)}</span>` : "";
}

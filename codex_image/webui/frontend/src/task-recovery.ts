import { translate } from "./i18n";
export type TaskRecovery = "credentials" | "quota" | "input" | "temporary";
export function taskRecoveryKind(task: any): TaskRecovery {
  const text = String(task?.error || task?.last_error || "").toLowerCase();
  const statusMatch = text.match(/\bhttp(?:\s+(?:error|status))?\s*[:=]?\s*(\d{3})\b/)
    || text.match(/\bstatus(?:\s+code)?\s*[:=]\s*(\d{3})\b/);
  const status = statusMatch ? Number(statusMatch[1]) : null;
  if (status === 401 || status === 403) return "credentials";
  if (status !== null && status >= 500 && status <= 599) return "temporary";
  if (status === null && /invalid_api_key|authentication_error|unauthorized|incorrect api key/.test(text)) return "credentials";
  if (/quota|usage limit|insufficient_quota|billing/.test(text)) return "quota";
  if (status === 400 || status === 422) return "input";
  if (status === null && /invalid[_ ](?:parameters?|value)|unsupported mime|base64-encoded data url/.test(text)) return "input";
  return "temporary";
}
export function taskRecoveryMessage(task: any): string {
  return translate(`ux.recovery.${taskRecoveryKind(task)}`);
}
export function localizedTaskStatus(status: string): string {
  return translate(status === "partial_failed" ? "taskStatus.partialFailed" : `taskStatus.${status}`);
}

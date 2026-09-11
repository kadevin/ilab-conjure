import { translate } from "./i18n";
export type TaskRecovery = "credentials" | "quota" | "input" | "temporary";
export function taskRecoveryKind(task: any): TaskRecovery {
  const text = String(task?.error || task?.last_error || "").toLowerCase();
  if (/\b401\b|invalid_api_key|authentication_error|unauthorized|incorrect api key/.test(text)) return "credentials";
  if (/quota|usage limit|insufficient_quota|billing/.test(text)) return "quota";
  if (/invalid_value|unsupported mime|base64-encoded data url/.test(text)) return "input";
  return "temporary";
}
export function taskRecoveryMessage(task: any): string {
  return translate(`ux.recovery.${taskRecoveryKind(task)}`);
}
export function localizedTaskStatus(status: string): string {
  return translate(status === "partial_failed" ? "taskStatus.partialFailed" : `taskStatus.${status}`);
}

import { translate } from "./i18n";
import { copyTextToClipboard } from "./clipboard-text";

/** Load diagnostic data only when requested, and never render a reply into another task. */
export function mountProviderResponseDetails(
  host: HTMLElement, taskId: string, onLayout: () => void,
): () => void {
  const details = document.createElement("details");
  details.className = "prompt-popover-submitted prompt-popover-response";
  const summary = document.createElement("summary");
  summary.textContent = translate("promptPopover.response");
  const status = document.createElement("p");
  status.className = "prompt-response-status";
  status.setAttribute("role", "status");
  const note = document.createElement("p");
  note.className = "prompt-response-note";
  note.textContent = translate("promptPopover.responseNote");
  note.hidden = true;
  const tools = document.createElement("div");
  tools.className = "prompt-response-actions";
  const copy = document.createElement("button");
  copy.type = "button";
  copy.className = "prompt-copy-button prompt-copy-inline";
  copy.textContent = translate("templates.copy");
  copy.setAttribute("aria-label", translate("promptPopover.copyResponse"));
  copy.disabled = true;
  copy.hidden = true;
  const retry = document.createElement("button");
  retry.type = "button";
  retry.className = "prompt-copy-button prompt-copy-inline";
  retry.textContent = translate("promptPopover.retryResponse");
  retry.hidden = true;
  tools.append(copy, retry);
  const pre = document.createElement("pre");
  pre.className = "prompt-popover-submitted-text prompt-response-json";
  pre.tabIndex = 0;
  pre.hidden = true;
  pre.setAttribute("aria-label", translate("promptPopover.response"));
  details.append(summary, status, note, tools, pre);
  host.append(details);

  let disposed = false;
  let loaded = false;
  let pending = false;
  let controller: AbortController | null = null;
  let copyTimer: number | undefined;
  let requestTimer: number | undefined;
  async function load() {
    if (pending || loaded || disposed) return;
    if (!taskId) {
      loaded = true;
      status.textContent = translate("promptPopover.responseMissing");
      return;
    }
    pending = true;
    retry.hidden = true;
    status.textContent = translate("promptPopover.responseLoading");
    controller = new AbortController();
    requestTimer = window.setTimeout(() => controller?.abort(), 20000);
    try {
      const response = await fetch(`/api/tasks/${encodeURIComponent(taskId)}/provider-responses`, {
        signal: controller.signal, cache: "no-store",
      });
      if (!response.ok) throw new Error("provider_response_unavailable");
      const data = await response.json();
      if (data?.version !== 1 || !Array.isArray(data.records)) throw new Error("provider_response_invalid");
      if (disposed) return;
      loaded = true;
      status.textContent = data.records.length ? "" : translate("promptPopover.responseMissing");
      if (data.records.length) {
        pre.textContent = JSON.stringify(data, null, 2);
        pre.hidden = false;
        copy.disabled = false;
        copy.hidden = false;
        note.hidden = false;
      }
    } catch {
      if (disposed) return;
      status.textContent = translate("promptPopover.responseError");
      retry.hidden = false;
    } finally {
      window.clearTimeout(requestTimer);
      pending = false;
      if (!disposed) onLayout();
    }
  }
  details.addEventListener("toggle", () => {
    if (details.open) void load();
    onLayout();
  });
  retry.addEventListener("click", () => { void load(); });
  copy.addEventListener("click", async () => {
    if (!pre.textContent || !await copyTextToClipboard(pre.textContent) || disposed) return;
    copy.textContent = translate("promptPopover.copied");
    window.clearTimeout(copyTimer);
    copyTimer = window.setTimeout(() => { copy.textContent = translate("templates.copy"); }, 1200);
  });
  return () => {
    disposed = true;
    controller?.abort();
    window.clearTimeout(requestTimer);
    window.clearTimeout(copyTimer);
  };
}

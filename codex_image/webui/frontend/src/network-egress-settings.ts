import { LOCALE_CHANGE_EVENT, translate } from "./i18n";
import { refreshSegmentedIndicators } from "./segmented-indicator";
import { getLegacyBridge } from "./state";

type NetworkEgressMode = "auto" | "system" | "direct" | "custom";

interface NetworkEgressSettingsPayload {
  mode: NetworkEgressMode;
  custom_proxy_url: string;
}

interface ResolvedNetworkEgress {
  requested_mode: NetworkEgressMode;
  route: "direct" | "proxy";
  source: "auto" | "system" | "direct" | "custom";
  proxy_url?: string;
}

let networkEgressFeatureInitialized = false;
let lastResolvedNetworkEgress: ResolvedNetworkEgress | null = null;

function elements() {
  return getLegacyBridge().els;
}

function setNetworkEgressFeedback(message: string, type = ""): void {
  const status = elements().networkEgressStatus as HTMLElement | null;
  if (!status) return;
  status.textContent = message;
  status.className = `api-settings-feedback settings-action-status${type ? ` ${type}` : ""}`;
}

function routeLabel(resolved: ResolvedNetworkEgress | null): string {
  if (!resolved) return translate("networkEgress.unavailable");
  let key = "networkEgress.routeDirect";
  if (resolved.route === "proxy" && resolved.source === "custom") key = "networkEgress.routeCustom";
  else if (resolved.route === "proxy" && resolved.source === "system") key = "networkEgress.routeSystem";
  else if (resolved.source === "auto") key = "networkEgress.routeAutoDirect";
  else if (resolved.source === "system") key = "networkEgress.routeSystemDirect";
  const label = translate(key);
  return resolved.proxy_url ? `${label} · ${resolved.proxy_url}` : label;
}

function renderResolvedNetworkEgress(resolved: ResolvedNetworkEgress | null): void {
  lastResolvedNetworkEgress = resolved;
  const target = elements().networkEgressResolvedRoute as HTMLElement | null;
  if (target) target.textContent = routeLabel(resolved);
}

function selectNetworkEgressMode(mode: NetworkEgressMode): void {
  const els = elements();
  const select = els.networkEgressMode as HTMLSelectElement | null;
  if (select) select.value = mode;
  const buttons = Array.from(els.networkEgressModeGroup?.querySelectorAll("[data-val]") || []);
  buttons.forEach((button: any) => button.classList.toggle("active", button.dataset.val === mode));
  if (els.networkEgressCustomField) {
    els.networkEgressCustomField.hidden = mode !== "custom" && mode !== "auto";
  }
  refreshSegmentedIndicators();
}

function readNetworkEgressForm(): NetworkEgressSettingsPayload {
  const els = elements();
  return {
    mode: ((els.networkEgressMode as HTMLSelectElement | null)?.value || "system") as NetworkEgressMode,
    custom_proxy_url: (els.networkEgressCustomProxyUrl as HTMLInputElement | null)?.value.trim() || "",
  };
}

function populateNetworkEgressSettings(payload: any): void {
  const settings = payload?.settings || {};
  const mode = (["auto", "system", "direct", "custom"].includes(settings.mode) ? settings.mode : "system") as NetworkEgressMode;
  const customInput = elements().networkEgressCustomProxyUrl as HTMLInputElement | null;
  if (customInput) customInput.value = settings.custom_proxy_url || "";
  selectNetworkEgressMode(mode);
  renderResolvedNetworkEgress(payload?.resolved || null);
}

async function responseJson(response: Response): Promise<any> {
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.detail || translate("networkEgress.requestFailed"));
  return data;
}

export async function refreshNetworkEgressSettings(): Promise<void> {
  try {
    const payload = await responseJson(await fetch("/api/network-egress"));
    populateNetworkEgressSettings(payload);
  } catch (error: any) {
    setNetworkEgressFeedback(error.message || translate("networkEgress.loadFailed"), "error");
  }
}

async function saveNetworkEgressSettings(): Promise<void> {
  const button = elements().saveNetworkEgressButton as HTMLButtonElement | null;
  if (!button) return;
  button.disabled = true;
  setNetworkEgressFeedback(translate("networkEgress.saving"), "running");
  try {
    const payload = await responseJson(await fetch("/api/network-egress", {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(readNetworkEgressForm()),
    }));
    populateNetworkEgressSettings(payload);
    setNetworkEgressFeedback(translate("networkEgress.saved"), "ok");
  } catch (error: any) {
    setNetworkEgressFeedback(error.message || translate("networkEgress.saveFailed"), "error");
  } finally {
    button.disabled = false;
  }
}

async function testNetworkEgress(): Promise<void> {
  const button = elements().testNetworkEgressButton as HTMLButtonElement | null;
  if (!button) return;
  button.disabled = true;
  setNetworkEgressFeedback(translate("networkEgress.testing"), "running");
  try {
    const payload = await responseJson(await fetch("/api/network-egress/test", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(readNetworkEgressForm()),
    }));
    renderResolvedNetworkEgress(payload.resolved || null);
    const elapsed = Number.isFinite(payload.elapsed_ms) ? ` · ${payload.elapsed_ms} ms` : "";
    setNetworkEgressFeedback(
      payload.ok
        ? `${translate("networkEgress.testSucceeded")}${elapsed}`
        : `${translate("networkEgress.testFailed")}: ${payload.error || translate("networkEgress.unavailable")}`,
      payload.ok ? "ok" : "error",
    );
  } catch (error: any) {
    setNetworkEgressFeedback(error.message || translate("networkEgress.testFailed"), "error");
  } finally {
    button.disabled = false;
  }
}

function handleModeClick(event: Event): void {
  const button = (event.target as HTMLElement | null)?.closest?.("[data-val]") as HTMLElement | null;
  if (!button) return;
  selectNetworkEgressMode(button.dataset.val as NetworkEgressMode);
  setNetworkEgressFeedback("", "");
}

export function initNetworkEgressSettingsFeature(): void {
  if (networkEgressFeatureInitialized) return;
  networkEgressFeatureInitialized = true;
  const els = elements();
  els.networkEgressModeGroup?.addEventListener("click", handleModeClick);
  els.saveNetworkEgressButton?.addEventListener("click", () => void saveNetworkEgressSettings());
  els.testNetworkEgressButton?.addEventListener("click", () => void testNetworkEgress());
  document.addEventListener(LOCALE_CHANGE_EVENT, () => renderResolvedNetworkEgress(lastResolvedNetworkEgress));
  Object.assign(getLegacyBridge().methods, {
    refreshNetworkEgressSettings,
    populateNetworkEgressSettings,
    saveNetworkEgressSettings,
    testNetworkEgress,
    selectNetworkEgressMode,
  });
}

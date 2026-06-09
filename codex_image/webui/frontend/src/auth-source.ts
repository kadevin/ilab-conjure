import { getLegacyBridge } from "./state";
import { updateModeSpecificSettings } from "./api-mode-settings";
import { formatTranslation, translate } from "./i18n";

const bridge = getLegacyBridge();
const state = bridge.state;
const els = bridge.els;

function legacyMethod(name: string, ...args: any[]): any {
  const method = getLegacyBridge().methods[name];
  if (typeof method !== "function") {
    throw new Error("Legacy method " + name + " is not initialized");
  }
  return method(...args);
}

function setStatus(message: any, type?: any): void { legacyMethod("setStatus", message, type); }
function updateRequestPreview(): void { legacyMethod("updateRequestPreview"); }
function currentApiMode(): string { return legacyMethod("currentApiMode"); }
function currentApiProviderLabel(): string { return legacyMethod("currentApiProviderLabel"); }
function apiModeLabel(mode: any): string { return legacyMethod("apiModeLabel", mode); }

export async function refreshHealth(): Promise<void> {
  try {
    const response = await fetch("/api/health");
    const data = await response.json();
    state.authAvailable = Boolean(data.auth_available);
    state.authStatus = data.auth || null;
    renderAuthSource(state.authStatus);
    els.apiStatus.className = `status-dot ${state.authAvailable ? "ok" : "error"}`;
    els.runButton.disabled = !state.authAvailable;
    if (!state.authAvailable) {
      setStatus(translate("auth.missingCodexSession"), "error");
    }
    updateRequestPreview();
  } catch (error: any) {
    state.authAvailable = false;
    els.apiStatus.className = "status-dot error";
    els.runButton.disabled = true;
    setStatus(error.message, "error");
  }
}

export async function setAuthSource(source: any): Promise<void> {
  state.pendingAuthSource = source;
  applyAuthSourceSelection(source);
  updateRequestPreview();
  try {
    const response = await fetch("/api/auth", {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ source }),
    });
    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.detail || translate("auth.switchFailed"));
    }
    state.pendingAuthSource = null;
    state.authStatus = data;
    state.authAvailable = Boolean(data.auth_available);
    renderAuthSource(data);
    els.apiStatus.className = `status-dot ${state.authAvailable ? "ok" : "error"}`;
    els.runButton.disabled = !state.authAvailable;
    setStatus(authSourceDetailText(data), state.authAvailable ? "ok" : "error");
    updateRequestPreview();
  } catch (error: any) {
    state.pendingAuthSource = null;
    renderAuthSource(state.authStatus);
    updateRequestPreview();
    setStatus(error.message || translate("auth.switchFailed"), "error");
  }
}

export function handleAuthSourceClick(event: any): void {
  const button = event.target.closest?.("[data-auth-source]");
  if (!button) return;
  const source = button.dataset.authSource;
  setAuthSource(source);
}

export function renderAuthSource(auth: any): void {
  const selected = state.pendingAuthSource || auth?.selected_source || "codex";
  applyAuthSourceSelection(selected);
  if (els.authSourceDetail) {
    const text = auth ? authSourceDetailText(auth) : translate("auth.checking");
    els.authSourceDetail.textContent = text;
    els.authSourceDetail.title = text;
  }
}

export function applyAuthSourceSelection(source: any): void {
  const selected = source || "codex";
  els.authSourceGroup?.querySelectorAll("[data-auth-source]").forEach((button: any) => {
    const active = button.dataset.authSource === selected;
    button.classList.toggle("active", active);
    button.setAttribute("aria-pressed", active ? "true" : "false");
  });
  els.apiProviderQuick?.classList.add("hidden");
  updateModeSpecificSettings(selected);
}

export function authSourceDetailText(auth: any): string {
  if (!auth) return translate("auth.checking");
  const selected = sourceLabel(auth.selected_source);
  const effectiveApi = auth.effective_source === "api";
  if (!auth.auth_available) {
    if (auth.selected_source === "api" || effectiveApi) {
      return formatTranslation("auth.sourceUnavailable", { source: selected });
    }
    return formatTranslation("auth.sourceUnavailable", { source: selected });
  }
  if (effectiveApi) {
    const provider = currentApiProviderLabel();
    const mode = apiModeLabel(currentApiMode());
    return `API · ${provider} · ${mode}`;
  }
  return "Codex";
}

export function sourceLabel(source: any): string {
  if (source === "codex") return "Codex";
  if (source === "api") return "API";
  return translate("auth.notActive");
}

export function currentAuthSource(): string {
  return state.pendingAuthSource || state.authStatus?.selected_source || "codex";
}

export function isDirectApiMode(authSource: any = currentAuthSource()): boolean {
  return authSource === "api" && currentApiMode() !== "responses";
}

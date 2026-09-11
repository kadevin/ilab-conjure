import { formatTranslation, LOCALE_CHANGE_EVENT, translate } from "./i18n";
import { getLegacyBridge } from "./state";

interface LanAccessSettings {
  enabled: boolean;
  active: boolean;
  restart_required: boolean;
  host_override: boolean;
  addresses: string[];
}

let currentSettings: LanAccessSettings | null = null;
let requestSequence = 0;
let saving = false;
let initialized = false;

function feedback(message: string, error = false): void {
  const { els } = getLegacyBridge();
  if (!els.lanAccessStatus) return;
  els.lanAccessStatus.textContent = message;
  els.lanAccessStatus.classList.toggle("error", error);
}

async function copyAddress(input: HTMLInputElement, button: HTMLButtonElement): Promise<void> {
  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(input.value);
    } else {
      input.focus();
      input.select();
      if (!document.execCommand("copy")) throw new Error("copy unavailable");
    }
    button.textContent = translate("lanAccess.copied");
  } catch {
    input.focus();
    input.select();
    button.textContent = translate("lanAccess.copyManually");
  }
}

function render(settings: LanAccessSettings): void {
  const { els } = getLegacyBridge();
  currentSettings = settings;
  if (els.lanAccessEnabled) els.lanAccessEnabled.checked = settings.enabled;
  const key = settings.host_override ? "hostOverride"
    : settings.restart_required ? settings.enabled ? "pendingEnable" : "pendingDisable"
    : settings.active ? "active" : "localOnly";
  feedback(translate(`lanAccess.${key}`));
  if (!els.lanAccessAddresses) return;
  els.lanAccessAddresses.replaceChildren();
  els.lanAccessAddresses.hidden = !settings.enabled && !settings.active;
  if (els.lanAccessAddresses.hidden) return;
  if (!settings.addresses.length) {
    const note = document.createElement("p");
    note.className = "lan-access-help";
    note.textContent = translate("lanAccess.noAddress");
    els.lanAccessAddresses.append(note);
  }
  for (const address of settings.addresses) {
    const row = document.createElement("div");
    row.className = "lan-access-address";
    const input = document.createElement("input");
    input.className = "control";
    input.value = address;
    input.readOnly = true;
    input.setAttribute("aria-label", translate("lanAccess.address"));
    const button = document.createElement("button");
    button.type = "button";
    button.className = "ghost-button";
    button.textContent = translate("templates.copy");
    button.setAttribute("aria-label", formatTranslation("lanAccess.copyAddress", { address }));
    button.addEventListener("click", () => void copyAddress(input, button));
    row.append(input, button);
    els.lanAccessAddresses.append(row);
  }
}

export async function refreshLanAccess(): Promise<void> {
  if (saving) return;
  const sequence = ++requestSequence;
  const { els } = getLegacyBridge();
  if (els.lanAccessEnabled) els.lanAccessEnabled.disabled = true;
  try {
    const response = await fetch("/api/lan-access");
    if (!response.ok) throw new Error("read failed");
    const data = await response.json();
    if (sequence === requestSequence) render(data);
  } catch {
    if (sequence === requestSequence) feedback(translate("lanAccess.failed"), true);
  } finally {
    if (sequence === requestSequence && els.lanAccessEnabled) {
      els.lanAccessEnabled.disabled = currentSettings === null;
    }
  }
}

async function saveLanAccess(): Promise<void> {
  const { els } = getLegacyBridge();
  if (saving || !els.lanAccessEnabled || !currentSettings) return;
  saving = true;
  const restoreFocus = document.activeElement === els.lanAccessEnabled;
  ++requestSequence;
  els.lanAccessEnabled.disabled = true;
  const enabled = els.lanAccessEnabled.checked;
  feedback(translate("lanAccess.saving"));
  try {
    const response = await fetch("/api/lan-access", {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ enabled }),
    });
    if (!response.ok) throw new Error("save failed");
    render(await response.json());
  } catch {
    els.lanAccessEnabled.checked = currentSettings.enabled;
    feedback(translate("lanAccess.failed"), true);
  } finally {
    saving = false;
    els.lanAccessEnabled.disabled = false;
    if (restoreFocus && document.activeElement === document.body) els.lanAccessEnabled.focus();
  }
}

export function initLanAccessSettingsFeature(): void {
  if (initialized) return;
  initialized = true;
  const { els, methods } = getLegacyBridge();
  els.lanAccessEnabled?.addEventListener("change", () => void saveLanAccess());
  document.addEventListener(LOCALE_CHANGE_EVENT, () => {
    if (currentSettings && !saving) render(currentSettings);
  });
  Object.assign(methods, { refreshLanAccess });
}

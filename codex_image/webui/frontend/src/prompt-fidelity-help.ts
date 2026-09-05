import { currentAuthSource } from "./auth-source";
import { currentApiMode, currentCodexMode } from "./api-provider-settings";
import { LOCALE_CHANGE_EVENT, translate } from "./i18n";
import { escapeHtml } from "./webui-utils";

type PromptTransport = "images" | "responses";
type PromptFidelity = "original" | "strict" | "off";

const HELP_MARGIN = 12;
const HELP_GAP = 8;

let promptFidelityHelpInitialized = false;
let promptFidelityHelpPopover: HTMLElement | null = null;
let promptFidelityHelpPinned = false;
let promptFidelityHelpCloseTimer: number | null = null;

function promptTransport(): PromptTransport {
  const authSource = currentAuthSource();
  if (authSource === "api") return currentApiMode() === "responses" ? "responses" : "images";
  if (authSource === "codex") return currentCodexMode() === "responses" ? "responses" : "images";
  return "images";
}

function currentPromptFidelity(): PromptFidelity {
  const value = (document.querySelector("#promptFidelity") as HTMLSelectElement | null)?.value;
  return value === "original" || value === "strict" ? value : "off";
}

function ensurePromptFidelityHelpPopover(): HTMLElement {
  if (promptFidelityHelpPopover?.isConnected) return promptFidelityHelpPopover;
  promptFidelityHelpPopover = document.createElement("div");
  promptFidelityHelpPopover.id = "promptFidelityHelpPopover";
  promptFidelityHelpPopover.className = "prompt-fidelity-help-popover hidden";
  promptFidelityHelpPopover.setAttribute("role", "tooltip");
  promptFidelityHelpPopover.setAttribute("aria-hidden", "true");
  document.body.appendChild(promptFidelityHelpPopover);
  return promptFidelityHelpPopover;
}

function promptFidelityDescriptionKey(transport: PromptTransport, mode: PromptFidelity): string {
  const modeKey = mode === "off" ? "automatic" : mode;
  return `output.promptHelp.${transport}.${modeKey}`;
}

function renderPromptFidelityHelp(): void {
  const popover = ensurePromptFidelityHelpPopover();
  const transport = promptTransport();
  const activeMode = currentPromptFidelity();
  const modes: Array<{ value: PromptFidelity; label: string }> = [
    { value: "original", label: translate("output.modeOriginal") },
    { value: "strict", label: translate("output.modeStrict") },
    { value: "off", label: translate("output.modeCreative") },
  ];
  const rows = modes.map(({ value, label }) => {
    const activeClass = value === activeMode ? " is-active" : "";
    return `
      <div class="prompt-fidelity-help-row${activeClass}" data-prompt-fidelity-help-mode="${value}">
        <dt>${escapeHtml(label)}</dt>
        <dd>${escapeHtml(translate(promptFidelityDescriptionKey(transport, value)))}</dd>
      </div>
    `;
  }).join("");
  popover.innerHTML = `
    <div class="prompt-fidelity-help-header">
      <strong>${escapeHtml(translate("output.promptHelpTitle"))}</strong>
      <span>${escapeHtml(translate(`output.promptHelp.${transport}Channel`))}</span>
    </div>
    <dl class="prompt-fidelity-help-list">${rows}</dl>
  `;
}

function positionPromptFidelityHelp(trigger: HTMLElement, popover: HTMLElement): void {
  const triggerRect = trigger.getBoundingClientRect();
  const viewportWidth = window.innerWidth;
  const viewportHeight = window.innerHeight;
  const width = Math.min(440, Math.max(280, viewportWidth - HELP_MARGIN * 2));
  popover.style.width = `${width}px`;
  popover.style.left = "0px";
  popover.style.top = "0px";
  const height = popover.offsetHeight;
  const left = Math.min(
    viewportWidth - width - HELP_MARGIN,
    Math.max(HELP_MARGIN, triggerRect.left),
  );
  const below = triggerRect.bottom + HELP_GAP;
  const above = triggerRect.top - height - HELP_GAP;
  const top = below + height <= viewportHeight - HELP_MARGIN
    ? below
    : Math.max(HELP_MARGIN, above);
  popover.style.left = `${left}px`;
  popover.style.top = `${top}px`;
}

function cancelPromptFidelityHelpClose(): void {
  if (promptFidelityHelpCloseTimer === null) return;
  window.clearTimeout(promptFidelityHelpCloseTimer);
  promptFidelityHelpCloseTimer = null;
}

function openPromptFidelityHelp(trigger: HTMLElement, pinned = promptFidelityHelpPinned): void {
  cancelPromptFidelityHelpClose();
  promptFidelityHelpPinned = pinned;
  const popover = ensurePromptFidelityHelpPopover();
  renderPromptFidelityHelp();
  popover.classList.remove("hidden");
  popover.setAttribute("aria-hidden", "false");
  trigger.setAttribute("aria-expanded", String(promptFidelityHelpPinned));
  positionPromptFidelityHelp(trigger, popover);
}

function closePromptFidelityHelp(trigger: HTMLElement): void {
  cancelPromptFidelityHelpClose();
  promptFidelityHelpPinned = false;
  const popover = ensurePromptFidelityHelpPopover();
  popover.classList.add("hidden");
  popover.setAttribute("aria-hidden", "true");
  trigger.setAttribute("aria-expanded", "false");
}

function schedulePromptFidelityHelpClose(trigger: HTMLElement): void {
  cancelPromptFidelityHelpClose();
  promptFidelityHelpCloseTimer = window.setTimeout(() => {
    promptFidelityHelpCloseTimer = null;
    if (promptFidelityHelpPinned || trigger.matches(":hover, :focus-visible") || promptFidelityHelpPopover?.matches(":hover")) return;
    closePromptFidelityHelp(trigger);
  }, 90);
}

export function initPromptFidelityHelpFeature(): void {
  if (promptFidelityHelpInitialized) return;
  const trigger = document.querySelector<HTMLElement>("#promptFidelityHelpButton");
  if (!trigger) return;
  promptFidelityHelpInitialized = true;
  const popover = ensurePromptFidelityHelpPopover();

  trigger.addEventListener("pointerenter", () => openPromptFidelityHelp(trigger));
  trigger.addEventListener("pointerleave", () => schedulePromptFidelityHelpClose(trigger));
  trigger.addEventListener("focus", () => openPromptFidelityHelp(trigger));
  trigger.addEventListener("blur", () => schedulePromptFidelityHelpClose(trigger));
  trigger.addEventListener("click", (event) => {
    event.stopPropagation();
    if (promptFidelityHelpPinned) {
      closePromptFidelityHelp(trigger);
      return;
    }
    openPromptFidelityHelp(trigger, true);
  });

  popover.addEventListener("pointerenter", cancelPromptFidelityHelpClose);
  popover.addEventListener("pointerleave", () => schedulePromptFidelityHelpClose(trigger));
  document.querySelector("#promptFidelity")?.addEventListener("change", () => {
    if (!popover.classList.contains("hidden")) openPromptFidelityHelp(trigger);
  });
  document.addEventListener(LOCALE_CHANGE_EVENT, () => {
    if (!popover.classList.contains("hidden")) openPromptFidelityHelp(trigger);
  });
  document.addEventListener("pointerdown", (event) => {
    const target = event.target as Node | null;
    if (!promptFidelityHelpPinned || !target || trigger.contains(target) || popover.contains(target)) return;
    closePromptFidelityHelp(trigger);
  });
  document.addEventListener("keydown", (event) => {
    if (event.key !== "Escape" || popover.classList.contains("hidden")) return;
    closePromptFidelityHelp(trigger);
    trigger.focus({ preventScroll: true });
  });
  window.addEventListener("resize", () => {
    if (!popover.classList.contains("hidden")) positionPromptFidelityHelp(trigger, popover);
  });
  document.addEventListener("scroll", () => {
    if (!popover.classList.contains("hidden")) positionPromptFidelityHelp(trigger, popover);
  }, true);
}

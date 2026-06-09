import { getLegacyBridge } from "./state";
import { formatTranslation, translate } from "./i18n";

interface PromptFindMatch {
  node: Text;
  start: number;
  end: number;
}

const bridge = getLegacyBridge();
const els = bridge.els;

const PROMPT_FIND_ELEMENT_NODE = 1;
const PROMPT_FIND_TEXT_NODE = 3;

let promptFindInitialized = false;
let promptFindMatches: PromptFindMatch[] = [];

function legacyMethod(name: string, ...args: any[]): any {
  const method = getLegacyBridge().methods[name];
  if (typeof method !== "function") {
    throw new Error("Legacy method " + name + " is not initialized");
  }
  return method(...args);
}

function syncPromptAfterFindMutation(): void {
  legacyMethod("syncPromptFromEditor");
  legacyMethod("syncGalleryInputsFromPrompt");
  legacyMethod("updatePromptCount");
  legacyMethod("updateRequestPreview");
}

function promptFindCell(): HTMLElement | null {
  return els.promptFindPanel?.closest(".prompt-template-recent-cell") || null;
}

function promptFindQuery(): string {
  return String(els.promptFindInput?.value || "");
}

function promptFindReplacement(): string {
  return String(els.promptReplaceInput?.value || "");
}

function isPromptFindOpen(): boolean {
  return Boolean(els.promptFindPanel && !els.promptFindPanel.classList.contains("hidden"));
}

function isNodeInsidePromptAtomicChip(node: Node): boolean {
  const element = node.nodeType === PROMPT_FIND_ELEMENT_NODE
    ? node as Element
    : node.parentElement || (node.parentNode?.nodeType === PROMPT_FIND_ELEMENT_NODE ? node.parentNode as Element : null);
  return Boolean(element?.closest(".gallery-chip, .color-chip, .prompt-snippet-chip"));
}

function collectPromptFindMatchesFromNode(node: Node, needle: string, matches: PromptFindMatch[]): void {
  if (isNodeInsidePromptAtomicChip(node)) return;
  if (node.nodeType === PROMPT_FIND_TEXT_NODE) {
    const textNode = node as Text;
    const text = textNode.textContent || "";
    let start = text.indexOf(needle);
    while (start !== -1) {
      matches.push({ node: textNode, start, end: start + needle.length });
      start = text.indexOf(needle, start + needle.length);
    }
    return;
  }
  Array.from(node.childNodes || []).forEach((child) => collectPromptFindMatchesFromNode(child, needle, matches));
}

function collectPromptFindMatches(query = promptFindQuery()): PromptFindMatch[] {
  const root = els.promptEditor as HTMLElement | null;
  const needle = String(query || "");
  if (!root || !needle) return [];

  root.normalize();
  const matches: PromptFindMatch[] = [];
  collectPromptFindMatchesFromNode(root, needle, matches);
  return matches;
}

function promptFindActionButtons(): HTMLButtonElement[] {
  return Array.from(els.promptFindPanel?.querySelectorAll("[data-prompt-find-action]") || []);
}

function setPromptFindStatus(message: string): void {
  if (els.promptFindStatus) els.promptFindStatus.textContent = message;
}

function setPromptFindCount(count = promptFindMatches.length): void {
  if (els.promptFindCount) {
    els.promptFindCount.textContent = formatTranslation("prompt.matchCount", { count });
  }
}

function updatePromptFindControls(): void {
  const hasQuery = Boolean(promptFindQuery());
  promptFindActionButtons().forEach((button) => {
    const action = button.dataset.promptFindAction || "";
    button.disabled = (action === "count" || action === "replace-all") && !hasQuery;
  });
}

function countPromptFindMatches(): void {
  promptFindMatches = collectPromptFindMatches();
  setPromptFindCount();
  setPromptFindStatus(promptFindMatches.length ? formatTranslation("prompt.foundCount", { count: promptFindMatches.length }) : translate("prompt.noMatch"));
  updatePromptFindControls();
}

function replaceAllPromptMatches(): void {
  const matches = collectPromptFindMatches();
  promptFindMatches = matches;
  if (!matches.length) {
    setPromptFindCount(0);
    setPromptFindStatus(translate("prompt.noMatch"));
    updatePromptFindControls();
    return;
  }
  const replacement = promptFindReplacement();
  for (let index = matches.length - 1; index >= 0; index -= 1) {
    const match = matches[index];
    if (!match) continue;
    const text = match.node.textContent || "";
    match.node.textContent = `${text.slice(0, match.start)}${replacement}${text.slice(match.end)}`;
  }
  syncPromptAfterFindMutation();
  promptFindMatches = collectPromptFindMatches();
  setPromptFindCount();
  setPromptFindStatus(formatTranslation("prompt.replacedCount", { count: matches.length }));
  updatePromptFindControls();
}

function clearPromptFindResult(): void {
  promptFindMatches = [];
  setPromptFindCount(0);
  setPromptFindStatus("");
  updatePromptFindControls();
}

function setPromptFindOpen(open: boolean): void {
  if (!els.promptFindPanel) return;
  els.promptFindPanel.classList.toggle("hidden", !open);
  promptFindCell()?.classList.toggle("find-active", open);
  els.promptFindButton?.setAttribute("aria-expanded", open ? "true" : "false");
  if (open) {
    clearPromptFindResult();
    els.promptFindInput?.focus({ preventScroll: true });
    return;
  }
  clearPromptFindResult();
  els.promptFindButton?.focus({ preventScroll: true });
}

function handlePromptFindAction(action: string): void {
  if (action === "count") {
    countPromptFindMatches();
  } else if (action === "replace-all") {
    replaceAllPromptMatches();
  }
}

function bindPromptFindActionButtons(): void {
  promptFindActionButtons().forEach((button) => {
    button.addEventListener("click", (event) => {
      event.preventDefault();
      handlePromptFindAction(button.dataset.promptFindAction || "");
    });
  });
}

function handlePromptFindKeydown(event: KeyboardEvent): void {
  if (event.key === "Escape") {
    event.preventDefault();
    setPromptFindOpen(false);
  }
}

function handlePromptFindShortcut(event: KeyboardEvent): void {
  const isFindShortcut = (event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "f";
  if (!isFindShortcut || event.altKey || event.shiftKey) {
    return;
  }
  const activeElement = document.activeElement;
  const insidePromptEditor = Boolean(activeElement && els.promptEditor?.contains(activeElement));
  const insideFindPanel = Boolean(activeElement && els.promptFindPanel?.contains(activeElement));
  if (!insidePromptEditor && !insideFindPanel) return;
  event.preventDefault();
  setPromptFindOpen(true);
}

export function initPromptFindReplaceFeature(): void {
  if (promptFindInitialized) return;
  promptFindInitialized = true;
  if (!els.promptFindButton || !els.promptFindPanel || !els.promptFindInput) return;

  els.promptFindButton.addEventListener("click", () => setPromptFindOpen(!isPromptFindOpen()));
  bindPromptFindActionButtons();
  els.promptFindClose?.addEventListener("click", () => setPromptFindOpen(false));
  els.promptFindPanel.addEventListener("keydown", handlePromptFindKeydown);
  els.promptFindInput.addEventListener("input", () => {
    clearPromptFindResult();
  });
  els.promptReplaceInput?.addEventListener("input", () => {
    setPromptFindStatus("");
    updatePromptFindControls();
  });
  els.clearPromptButton?.addEventListener("click", () => {
    if (isPromptFindOpen()) window.setTimeout(() => clearPromptFindResult(), 0);
  });
  document.addEventListener("keydown", handlePromptFindShortcut);
}

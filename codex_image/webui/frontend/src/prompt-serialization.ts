import { restoreImageMentions, validImageMentionContext, type ImageMentionContext } from "./prompt-image-mentions";
import { getLegacyBridge } from "./state";

const bridge = getLegacyBridge();
const els = bridge.els;

function legacyMethod(name: string, ...args: any[]): any {
  const method = getLegacyBridge().methods[name];
  if (typeof method !== "function") {
    throw new Error("Legacy method " + name + " is not initialized");
  }
  return method(...args);
}

function createGalleryChip(item: any): HTMLElement { return legacyMethod("createGalleryChip", item); }
function createColorChip(colorCode: any): HTMLElement { return legacyMethod("createColorChip", colorCode); }
function normalizeHexColor(value: any): string { return legacyMethod("normalizeHexColor", value); }
function findPromptSnippetRefAt(promptText: any, cursor: any): any { return legacyMethod("findPromptSnippetRefAt", promptText, cursor); }
function createPromptSnippetChip(snippet: any): HTMLElement { return legacyMethod("createPromptSnippetChip", snippet); }
function updatePromptChipSelectionState(): void { legacyMethod("updatePromptChipSelectionState"); }
function galleryRefsByMentionLength(refs: any): any[] { return legacyMethod("galleryRefsByMentionLength", refs); }
function findGalleryRefMentionAt(promptText: any, cursor: any, refs: any): any {
  return legacyMethod("findGalleryRefMentionAt", promptText, cursor, refs);
}
function hideMentionSuggest(): void { legacyMethod("hideMentionSuggest"); }
function hideColorSuggest(): void { legacyMethod("hideColorSuggest"); }
function hidePromptSnippetSuggest(): void { legacyMethod("hidePromptSnippetSuggest"); }
function hidePromptSnippetSelectionButton(): void { legacyMethod("hidePromptSnippetSelectionButton"); }
function closePromptSnippetPopover(): void { legacyMethod("closePromptSnippetPopover"); }

export function getPromptText(): string {
  if (!els.promptEditor) return els.prompt.value;
  return normalizePromptEditorText(promptTextFromNode(els.promptEditor).replace(/\u00a0/g, " ")).trim();
}

export function normalizePromptEditorText(value: any): string {
  return String(value || "").replace(/\r\n?/g, "\n");
}

export function createPromptTextFragment(text: any): { fragment: DocumentFragment; lastNode: Node | null } {
  const normalized = normalizePromptEditorText(text);
  const fragment = document.createDocumentFragment();
  let lastNode: Node | null = null;
  normalized.split("\n").forEach((part, index) => {
    if (index > 0) {
      lastNode = document.createElement("br");
      fragment.append(lastNode);
    }
    if (!part) return;
    lastNode = document.createTextNode(part);
    fragment.append(lastNode);
  });
  return { fragment, lastNode };
}

export function promptTextFromNode(node: any, imageRenderer?: (chip: HTMLElement) => string): string {
  let text = "";
  node.childNodes.forEach((child: any) => {
    if (child.nodeType === Node.TEXT_NODE) {
      text += child.textContent || "";
      return;
    }
    if (child.nodeType !== Node.ELEMENT_NODE) return;
    if (child.classList.contains("gallery-chip")) {
      text += imageRenderer ? imageRenderer(child) : child.dataset.imageRefText || `@${child.dataset.galleryName || child.textContent.trim()}`;
      return;
    }
    if (child.classList.contains("color-chip")) {
      text += child.dataset.colorCode || child.textContent.trim();
      return;
    }
    if (child.classList.contains("prompt-snippet-chip")) {
      text += `~${child.dataset.promptSnippetTag || child.textContent.replace(/^~/, "").trim()}`;
      return;
    }
    if (child.tagName === "BR") {
      text += "\n";
      return;
    }
    text += promptTextFromNode(child, imageRenderer);
    if (child.tagName === "DIV" || child.tagName === "P") {
      text += "\n";
    }
  });
  return text;
}

export function promptSelectionText(): string {
  const selection = window.getSelection();
  if (!selection || !selection.rangeCount || !els.promptEditor) return "";
  const parts = [];
  for (let index = 0; index < selection.rangeCount; index += 1) {
    const range = selection.getRangeAt(index);
    if (range.collapsed || !rangeIntersectsNode(range, els.promptEditor)) continue;
    parts.push(promptTextFromRange(range));
  }
  return parts.join("").replace(/\u00a0/g, " ");
}

export function promptTextFromRange(range: any): string {
  const fragment = range.cloneContents();
  return promptTextFromNode(fragment);
}

export function rangeIntersectsNode(range: any, node: any): boolean {
  if (!range || !node) return false;
  try {
    return range.intersectsNode(node);
  } catch {
    return false;
  }
}

export function selectPromptEditorContents(): void {
  if (!els.promptEditor) return;
  els.promptEditor.focus();
  const range = document.createRange();
  range.selectNodeContents(els.promptEditor);
  const selection = window.getSelection();
  if (!selection) return;
  selection.removeAllRanges();
  selection.addRange(range);
  updatePromptChipSelectionState();
}

export function setPromptText(text: any): void {
  const normalized = normalizePromptEditorText(text);
  if (els.promptEditor) {
    els.promptEditor.innerHTML = "";
    const { fragment } = createPromptTextFragment(normalized);
    els.promptEditor.append(fragment);
  }
  els.prompt.value = normalized;
  hideMentionSuggest();
  hideColorSuggest();
  hidePromptSnippetSuggest();
  hidePromptSnippetSelectionButton();
  closePromptSnippetPopover();
}

export function setPromptWithGalleryRefs(text: any, refs: any, mentions?: ImageMentionContext, sources: any[] = []): void {
  if (!els.promptEditor) {
    setPromptText(text);
    return;
  }
  const refList = Array.isArray(refs) ? refs : [];
  const sortedRefs = galleryRefsByMentionLength(refList);
  const promptText = normalizePromptEditorText(text);
  clearPromptEditorSelection();
  els.promptEditor.innerHTML = "";
  if (validImageMentionContext(mentions, promptText)) {
    restoreImageMentions(mentions, sources, part => appendRestoredPromptText(part, []));
  } else {
    appendRestoredPromptText(promptText, mentions ? [] : sortedRefs);
  }
  syncPromptFromEditor();
  hideMentionSuggest();
  hideColorSuggest();
  hidePromptSnippetSuggest();
  hidePromptSnippetSelectionButton();
  closePromptSnippetPopover();
}

function appendRestoredPromptText(promptText: string, sortedRefs: any[]): void {
  let cursor = 0;
  let plainStart = 0;
  while (cursor < promptText.length) {
    const refMatch = findGalleryRefMentionAt(promptText, cursor, sortedRefs);
    if (refMatch) {
      appendPromptText(promptText.slice(plainStart, cursor));
      els.promptEditor.append(createGalleryChip(refMatch.ref));
      cursor = refMatch.end;
      plainStart = cursor;
      continue;
    }
    const colorMatch = promptText.slice(cursor).match(/^#([0-9a-fA-F]{6}|[0-9a-fA-F]{3})(?![0-9a-fA-F])/);
    if (colorMatch) {
      const match = colorMatch;
      const colorCode = normalizeHexColor(match[0]);
      appendPromptText(promptText.slice(plainStart, cursor));
      els.promptEditor.append(createColorChip(colorCode));
      cursor += match[0].length;
      plainStart = cursor;
      continue;
    }
    const snippetMatch = findPromptSnippetRefAt(promptText, cursor);
    if (snippetMatch) {
      appendPromptText(promptText.slice(plainStart, cursor));
      els.promptEditor.append(createPromptSnippetChip(snippetMatch.snippet));
      cursor = snippetMatch.end;
      plainStart = cursor;
      continue;
    }
    cursor += 1;
  }
  appendPromptText(promptText.slice(plainStart));
}

function clearPromptEditorSelection(): void {
  const selection = window.getSelection();
  if (!selection?.rangeCount || !els.promptEditor) return;
  const intersectsEditor = Array.from({ length: selection.rangeCount }, (_, index) => selection.getRangeAt(index))
    .some((range) => rangeIntersectsNode(range, els.promptEditor));
  if (intersectsEditor) selection.removeAllRanges();
}

export function appendPromptText(text: any): void {
  const { fragment } = createPromptTextFragment(text);
  els.promptEditor.append(fragment);
}

export function clearPromptEditorIfEmpty(): void {
  if (!els.promptEditor) return;
  const visibleText = promptTextFromNode(els.promptEditor).replace(/\u00a0/g, " ").trim();
  if (!visibleText) {
    els.promptEditor.textContent = "";
  }
}

export function syncPromptFromEditor(): void {
  els.prompt.value = getPromptText();
}

export function initPromptSerializationFeature(): void {
  Object.assign(getLegacyBridge().methods, {
    getPromptText,
    normalizePromptEditorText,
    createPromptTextFragment,
    promptTextFromNode,
    promptSelectionText,
    promptTextFromRange,
    rangeIntersectsNode,
    selectPromptEditorContents,
    setPromptText,
    setPromptWithGalleryRefs,
    appendPromptText,
    clearPromptEditorIfEmpty,
    syncPromptFromEditor,
  });
}

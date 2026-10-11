import { handleImageMentionKey } from "./prompt-mention-menu";
import { getLegacyBridge } from "./state";
import {
  handlePromptEditorPaste,
  insertPlainPromptText,
  promptPasteTextFromClipboard,
  promptPlainTextFromHtml,
} from "./prompt-editor-paste";

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

function getPromptText(): string { return legacyMethod("getPromptText"); }
function promptTextFromNode(node: any): string { return legacyMethod("promptTextFromNode", node); }
function promptSelectionText(): string { return legacyMethod("promptSelectionText"); }
function rangeIntersectsNode(range: any, node: any): boolean { return legacyMethod("rangeIntersectsNode", range, node); }
function selectPromptEditorContents(): void { legacyMethod("selectPromptEditorContents"); }
function syncGalleryInputsFromPrompt(): boolean { return legacyMethod("syncGalleryInputsFromPrompt"); }
function updateMentionSuggest(): void { legacyMethod("updateMentionSuggest"); }
function hideMentionSuggest(): void { legacyMethod("hideMentionSuggest"); }
function hideColorSuggest(): void { legacyMethod("hideColorSuggest"); }
function updateColorSuggest(): void { legacyMethod("updateColorSuggest"); }
function insertColorCode(colorCode: any): void { legacyMethod("insertColorCode", colorCode); }
function openColorChipEditor(chip: any): void { legacyMethod("openColorChipEditor", chip); }
function hidePromptSnippetSuggest(): void { legacyMethod("hidePromptSnippetSuggest"); }
function hidePromptSnippetSelectionButton(): void { legacyMethod("hidePromptSnippetSelectionButton"); }
function closePromptSnippetPopover(): void { legacyMethod("closePromptSnippetPopover"); }
function promptSnippetSuggestElement(): HTMLElement | null { return legacyMethod("promptSnippetSuggestElement"); }
function findPromptSnippetById(id: any): any { return legacyMethod("findPromptSnippetById", id); }
function insertPromptSnippet(snippet: any): void { legacyMethod("insertPromptSnippet", snippet); }
function updatePromptSnippetSuggest(): void { legacyMethod("updatePromptSnippetSuggest"); }
function updatePromptSnippetSelectionButton(): void { legacyMethod("updatePromptSnippetSelectionButton"); }
function openPromptSnippetChipPopover(chip: any): void { legacyMethod("openPromptSnippetChipPopover", chip); }
function updatePromptCount(): void { legacyMethod("updatePromptCount"); }
function updateRequestPreview(): void { legacyMethod("updateRequestPreview"); }
function removePromptGalleryChip(chip: any): void { legacyMethod("removePromptGalleryChip", chip); }

export function handlePromptEditorCopy(event: any): void {
  if (!event.clipboardData) return;
  const text = promptSelectionText();
  if (!text) return;
  event.preventDefault();
  event.clipboardData.setData("text/plain", text);
}

export function promptEditorFocusInside(): boolean {
  const activeElement = document.activeElement;
  return Boolean(activeElement && els.promptEditor && els.promptEditor.contains(activeElement));
}

export function updatePromptChipSelectionState(): void {
  const chips = Array.from(els.promptEditor?.querySelectorAll(".gallery-chip, .color-chip, .prompt-snippet-chip") || []);
  if (!chips.length) return;
  const selection = window.getSelection();
  const ranges: Range[] = [];
  if (selection && !selection.isCollapsed && selection.rangeCount && els.promptEditor) {
    for (let index = 0; index < selection.rangeCount; index += 1) {
      const range = selection.getRangeAt(index);
      if (rangeIntersectsNode(range, els.promptEditor)) ranges.push(range);
    }
  }
  chips.forEach((chip: any) => {
    const selected = ranges.some((range: any) => rangeIntersectsNode(range, chip));
    chip.classList.toggle("prompt-chip-selected", selected);
  });
}

export function syncPromptFromEditor(): void {
  els.prompt.value = getPromptText();
}

export function handlePromptEditorKeydown(event: any): void {
  if (event.isComposing || event.keyCode === 229) return;
  if (handleImageMentionKey(event)) return;
  if (isPromptEditorArrowKey(event.key)) {
    event.stopPropagation();
    return;
  }
  if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "a") {
    event.preventDefault();
    selectPromptEditorContents();
    return;
  }
  if (event.key === "Backspace" || event.key === "Delete") {
    const chip = promptChipAtCaretForDeletion(event.key) || promptChipFallbackForDeletion(event.key);
    if (chip) {
      event.preventDefault();
      removePromptGalleryChip(chip);
      return;
    }
  }
  if (event.key === "Escape") {
    hideMentionSuggest();
    hideColorSuggest();
    hidePromptSnippetSuggest();
    hidePromptSnippetSelectionButton();
    closePromptSnippetPopover();
    return;
  }
  if (event.key === "Enter" && !els.colorSuggest.classList.contains("hidden")) {
    event.preventDefault();
    const input = els.colorSuggest.querySelector("[data-color-hex-input]");
    insertColorCode((input as any)?.value || state.selectedColorCode);
    return;
  }
  const promptSnippetSuggest = promptSnippetSuggestElement();
  if (event.key === "Enter" && promptSnippetSuggest && !promptSnippetSuggest.classList.contains("hidden")) {
    const first = promptSnippetSuggest.querySelector("[data-prompt-snippet-id]");
    if (first) {
      event.preventDefault();
      const snippet = findPromptSnippetById((first as any).dataset.promptSnippetId);
      if (snippet) insertPromptSnippet(snippet);
    }
  }
}

function isPromptEditorArrowKey(key: string): boolean {
  return key === "ArrowUp" || key === "ArrowDown" || key === "ArrowLeft" || key === "ArrowRight";
}

export function handlePromptEditorClick(event: any): void {
  if (event.detail >= 3 && !event.target.closest?.("button")) {
    event.preventDefault();
    event.stopPropagation();
    selectPromptEditorContents();
    return;
  }
  const removeButton = event.target.closest?.("[data-remove-gallery-chip], [data-remove-color-chip], [data-remove-prompt-snippet-chip]");
  if (removeButton && els.promptEditor.contains(removeButton)) {
    event.preventDefault();
    event.stopPropagation();
    removePromptGalleryChip(removeButton.closest(".gallery-chip, .color-chip, .prompt-snippet-chip"));
    return;
  }
  const editColorButton = event.target.closest?.("[data-edit-color-chip]");
  if (editColorButton && els.promptEditor.contains(editColorButton)) {
    event.preventDefault();
    event.stopPropagation();
    openColorChipEditor(editColorButton.closest(".color-chip"));
    return;
  }
  const snippetChip = event.target.closest?.(".prompt-snippet-chip");
  if (snippetChip && els.promptEditor.contains(snippetChip) && !event.target.closest?.("[data-remove-prompt-snippet-chip]")) {
    event.preventDefault();
    event.stopPropagation();
    openPromptSnippetChipPopover(snippetChip);
  }
}

export function promptChipAtCaretForDeletion(key: any): any {
  const selection = window.getSelection();
  if (!selection || !selection.rangeCount || !selection.isCollapsed || !els.promptEditor) return null;
  if (!els.promptEditor.contains(selection.anchorNode)) return null;

  const range = selection.getRangeAt(0);
  const isBackspace = key === "Backspace";
  const container = range.startContainer;
  const offset = range.startOffset;
  if (container.nodeType === Node.TEXT_NODE) {
    const text = container.textContent || "";
    if (isBackspace && offset > 0) return null;
    if (!isBackspace && offset < text.length) return null;
    const sibling = isBackspace ? container.previousSibling : container.nextSibling;
    return sibling?.nodeType === Node.ELEMENT_NODE && isPromptAtomicChip(sibling) ? sibling : null;
  }
  if (container.nodeType === Node.ELEMENT_NODE) {
    const children = Array.from(container.childNodes);
    const candidate = children[isBackspace ? offset - 1 : offset];
    return candidate?.nodeType === Node.ELEMENT_NODE && isPromptAtomicChip(candidate) ? candidate : null;
  }
  return null;
}

export function promptChipFallbackForDeletion(key: any): any {
  if (!els.promptEditor) return null;
  const chips = Array.from(els.promptEditor.querySelectorAll(".gallery-chip, .color-chip[data-color-code], .prompt-snippet-chip[data-prompt-snippet-tag]"));
  if (!chips.length) return null;
  const textWithoutChips = Array.from(els.promptEditor.childNodes).reduce<string>((text: string, child: any) => {
    if (child.nodeType === Node.ELEMENT_NODE && isPromptAtomicChip(child)) {
      return text;
    }
    return text + (child.textContent || "");
  }, "");
  if (textWithoutChips.trim()) return null;
  return key === "Backspace" ? chips[chips.length - 1] : chips[0];
}

export function isPromptAtomicChip(node: any): boolean {
  return Boolean(node?.classList?.contains("gallery-chip") || node?.classList?.contains("color-chip") || node?.classList?.contains("prompt-snippet-chip"));
}

export function promptChipFromEvent(event: any): any {
  const chip = event.target.closest?.(".gallery-chip, .color-chip, .prompt-snippet-chip");
  if (!chip || !els.promptEditor?.contains(chip)) return null;
  return chip;
}

export function handlePromptChipDragStart(event: any): void {
  const chip = promptChipFromEvent(event);
  if (!chip || event.target.closest?.("[data-remove-gallery-chip], [data-remove-color-chip], [data-remove-prompt-snippet-chip]")) {
    event.preventDefault();
    return;
  }
  state.draggedPromptChip = chip;
  chip.classList.add("prompt-chip-dragging");
  event.dataTransfer.effectAllowed = "move";
  event.dataTransfer.setData("text/plain", promptTextFromNode(chip));
}

export function handlePromptChipDragOver(event: any): void {
  if (!state.draggedPromptChip) return;
  event.preventDefault();
  event.dataTransfer.dropEffect = "move";
  clearPromptChipDropClasses();
  const targetChip = promptDropTargetChip(event);
  if (!targetChip) return;
  targetChip.classList.add(promptDropPlacement(event, targetChip) === "before" ? "prompt-chip-drop-before" : "prompt-chip-drop-after");
}

export function handlePromptEditorDrop(event: any): void {
  handlePromptChipDrop(event);
}

export function handlePromptChipDrop(event: any): void {
  const chip = state.draggedPromptChip;
  if (!chip || !els.promptEditor?.contains(chip)) return;
  event.preventDefault();
  clearPromptChipDropClasses();
  const targetChip = promptDropTargetChip(event);
  if (targetChip) {
    const insertBefore = promptDropPlacement(event, targetChip) === "before" ? targetChip : targetChip.nextSibling;
    els.promptEditor.insertBefore(chip, insertBefore);
  } else {
    const range = promptRangeFromPoint(event.clientX, event.clientY);
    if (range && els.promptEditor.contains(range.startContainer)) {
      range.insertNode(chip);
    } else {
      els.promptEditor.append(chip);
    }
  }
  const trailingBoundary = normalizePromptChipBoundaries(chip);
  syncPromptAfterChipMutation();
  setCaretAfterNode(trailingBoundary || chip);
}

export function handlePromptChipDragEnd(): void {
  state.draggedPromptChip?.classList.remove("prompt-chip-dragging");
  state.draggedPromptChip = null;
  clearPromptChipDropClasses();
}

export function promptDropTargetChip(event: any): any {
  const chip = promptChipFromEvent(event);
  if (!chip || chip === state.draggedPromptChip) return null;
  return chip;
}

export function promptDropPlacement(event: any, chip: any): string {
  const rect = chip.getBoundingClientRect();
  const horizontal = rect.width >= rect.height;
  const position = horizontal ? event.clientX - rect.left : event.clientY - rect.top;
  const size = horizontal ? rect.width : rect.height;
  return position < size / 2 ? "before" : "after";
}

export function clearPromptChipDropClasses(): void {
  els.promptEditor?.querySelectorAll(".prompt-chip-drop-before, .prompt-chip-drop-after").forEach((chip: any) => {
    chip.classList.remove("prompt-chip-drop-before", "prompt-chip-drop-after");
  });
}

export function promptRangeFromPoint(x: any, y: any): Range | null {
  if (document.caretRangeFromPoint) {
    return document.caretRangeFromPoint(x, y);
  }
  if (document.caretPositionFromPoint) {
    const position = document.caretPositionFromPoint(x, y);
    if (!position) return null;
    const range = document.createRange();
    range.setStart(position.offsetNode, position.offset);
    range.collapse(true);
    return range;
  }
  return null;
}

export function normalizePromptChipBoundaries(chip: any): Node | null {
  if (!chip || !els.promptEditor?.contains(chip)) return null;
  ensurePromptChipLeadingBoundary(chip);
  return ensurePromptChipTrailingBoundary(chip);
}

export function ensurePromptChipLeadingBoundary(chip: any): Node | null {
  const previousNode = chip.previousSibling;
  if (!previousNode) return null;
  if (previousNode.nodeType === Node.TEXT_NODE && /[\s\u00a0]$/.test(previousNode.textContent || "")) {
    return null;
  }
  els.promptEditor.insertBefore(document.createTextNode(" "), chip);
  return chip.previousSibling;
}

export function ensurePromptChipTrailingBoundary(chip: any): Node | null {
  const nextNode = chip.nextSibling;
  if (!nextNode) {
    chip.after(document.createTextNode(" "));
    return chip.nextSibling;
  }
  if (nextNode.nodeType === Node.TEXT_NODE && /^[\s\u00a0]/.test(nextNode.textContent || "")) {
    return null;
  }
  els.promptEditor.insertBefore(document.createTextNode(" "), nextNode);
  return chip.nextSibling;
}

export function syncPromptAfterChipMutation(): void {
  clearPromptEditorIfEmpty();
  syncPromptFromEditor();
  updatePromptCount();
  const galleryInputsChanged = syncGalleryInputsFromPrompt();
  if (!galleryInputsChanged) updateRequestPreview();
  hideMentionSuggest();
  hideColorSuggest();
  hidePromptSnippetSuggest();
}

export function mentionRangeRect(range: any): DOMRect | null {
  const rect = range.getBoundingClientRect();
  if (rect && (rect.width || rect.height)) return rect;
  const rects = range.getClientRects();
  return rects.length ? rects[0] : null;
}

export function clearPromptEditorIfEmpty(): void {
  if (!els.promptEditor) return;
  const visibleText = promptTextFromNode(els.promptEditor).replace(/\u00a0/g, " ").trim();
  if (!visibleText) {
    els.promptEditor.textContent = "";
  }
}

export function setCaretToEnd(element: any): void {
  element.focus();
  const range = document.createRange();
  range.selectNodeContents(element);
  range.collapse(false);
  const selection = window.getSelection();
  if (!selection) return;
  selection.removeAllRanges();
  selection.addRange(range);
}

export function setCaretAfterNode(node: any): void {
  if (!node) return;
  const range = document.createRange();
  if (node.nodeType === Node.TEXT_NODE) {
    range.setStart(node, (node.textContent || "").length);
  } else {
    range.setStartAfter(node);
  }
  range.collapse(true);
  const selection = window.getSelection();
  if (!selection) return;
  selection.removeAllRanges();
  selection.addRange(range);
  els.promptEditor?.focus();
}

export function bindPromptEditorEvents(): void {
  const updateAfterInput = () => {
    syncPromptFromEditor();
    updatePromptCount();
    const galleryInputsChanged = syncGalleryInputsFromPrompt();
    updateMentionSuggest();
    updateColorSuggest();
    updatePromptSnippetSuggest();
    if (!galleryInputsChanged) updateRequestPreview();
  };
  els.promptEditor?.addEventListener("input", (event: InputEvent) => {
    if (!event.isComposing) updateAfterInput();
  });
  els.promptEditor?.addEventListener("compositionend", updateAfterInput);
  els.promptEditor?.addEventListener("keyup", (event: KeyboardEvent) => {
    if (event.isComposing || event.keyCode === 229 || ["Escape", "ArrowUp", "ArrowDown", "Enter"].includes(event.key)) return;
    updateMentionSuggest();
    updateColorSuggest();
    updatePromptSnippetSuggest();
    updatePromptSnippetSelectionButton();
  });
  els.promptEditor?.addEventListener("keydown", handlePromptEditorKeydown);
  els.promptEditor?.addEventListener("copy", handlePromptEditorCopy);
  els.promptEditor?.addEventListener("paste", handlePromptEditorPaste);
  els.promptEditor?.addEventListener("click", handlePromptEditorClick);
  els.promptEditor?.addEventListener("dragstart", handlePromptChipDragStart);
  els.promptEditor?.addEventListener("dragover", handlePromptChipDragOver);
  els.promptEditor?.addEventListener("drop", handlePromptChipDrop);
  els.promptEditor?.addEventListener("dragend", handlePromptChipDragEnd);
  els.promptEditor?.addEventListener("mouseup", updatePromptSnippetSelectionButton);
  els.promptEditor?.addEventListener("blur", () => {
    window.setTimeout(() => {
      if (!els.mentionSuggest?.contains(document.activeElement)) hideMentionSuggest();
      hidePromptSnippetSuggest();
      if (!els.colorSuggest?.contains(document.activeElement) && !promptEditorFocusInside()) hideColorSuggest();
    }, 160);
  });
  document.addEventListener("selectionchange", () => {
    updatePromptChipSelectionState();
    updatePromptSnippetSelectionButton();
  });
}

export function initPromptEditorEventsFeature(): void {
  Object.assign(getLegacyBridge().methods, {
    handlePromptEditorCopy,
    promptPlainTextFromHtml,
    promptPasteTextFromClipboard,
    insertPlainPromptText,
    handlePromptEditorPaste,
    promptEditorFocusInside,
    updatePromptChipSelectionState,
    syncPromptFromEditor,
    handlePromptEditorKeydown,
    handlePromptEditorClick,
    promptChipAtCaretForDeletion,
    promptChipFallbackForDeletion,
    isPromptAtomicChip,
    promptChipFromEvent,
    handlePromptChipDragStart,
    handlePromptChipDragOver,
    handlePromptEditorDrop,
    handlePromptChipDrop,
    handlePromptChipDragEnd,
    promptDropTargetChip,
    promptDropPlacement,
    clearPromptChipDropClasses,
    promptRangeFromPoint,
    normalizePromptChipBoundaries,
    ensurePromptChipLeadingBoundary,
    ensurePromptChipTrailingBoundary,
    syncPromptAfterChipMutation,
    mentionRangeRect,
    clearPromptEditorIfEmpty,
    setCaretToEnd,
    setCaretAfterNode,
    bindPromptEditorEvents,
  });
}

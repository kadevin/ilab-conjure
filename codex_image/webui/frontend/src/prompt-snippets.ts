import { getLegacyBridge } from "./state";
import { positionPromptPopoverAtAnchor } from "./prompt-popover-position";
import { formatTranslation, translate } from "./i18n";

const PROMPT_SNIPPETS_ENDPOINT = "/api/prompt-snippets";
const DEFAULT_PROMPT_SNIPPET_CATEGORY = "\u5e38\u7528";
const PROMPT_SNIPPET_TRIGGER_CHARS = "~～〜∼˜";
const PROMPT_SNIPPET_BOUNDARY_CHARS = "，。,.；;：:！？!?、（）()[]【】\"'“”‘’";
const PROMPT_SNIPPET_TRIGGER_PATTERN = /(^|[\s\n，。,.；;：:！？!?、（）()\[\]【】"'“”‘’])([~～〜∼˜]+)([^\s~～〜∼˜@#，。,.；;：:！？!?、（）()\[\]【】"'“”‘’]*)$/;

const bridge = getLegacyBridge();
const state = bridge.state;
const els = bridge.els;

let promptSnippetSuggestEl: HTMLElement | null = null;
let promptSnippetSelectionButtonEl: HTMLButtonElement | null = null;
let promptSnippetPopoverEl: HTMLElement | null = null;
const promptSnippetPopoverState: Record<string, any> = {
  mode: null,
  chip: null,
  snippetId: null,
};

function legacyMethod(name: string, ...args: any[]): any {
  const method = getLegacyBridge().methods[name];
  if (typeof method !== "function") {
    throw new Error("Legacy method " + name + " is not initialized");
  }
  return method(...args);
}

function escapeHtml(value: any): string { return legacyMethod("escapeHtml", value); }
function setStatus(message: any, type?: any): void { legacyMethod("setStatus", message, type); }
function getPromptText(): string { return legacyMethod("getPromptText"); }
function promptTextFromRange(range: any): string { return legacyMethod("promptTextFromRange", range); }
function rangeIntersectsNode(range: any, node: any): boolean { return legacyMethod("rangeIntersectsNode", range, node); }
function appendPromptText(text: any): void { legacyMethod("appendPromptText", text); }
function mentionRangeRect(range: any): any { return legacyMethod("mentionRangeRect", range); }
function removePromptGalleryChip(chip: any): void { legacyMethod("removePromptGalleryChip", chip); }
function syncPromptAfterChipMutation(): void { legacyMethod("syncPromptAfterChipMutation"); }
function setCaretAfterNode(node: any): void { legacyMethod("setCaretAfterNode", node); }

function normalizePromptSnippet(value: any) {
  if (!value || typeof value !== "object") return null;
  const tag = String(value.tag || "").trim().replace(/^[~～〜∼˜]+/, "");
  const content = String(value.content || "").trim();
  if (!tag || !content) return null;
  return {
    id: String(value.id || tag).trim() || tag,
    tag,
    title: String(value.title || tag).trim() || tag,
    content,
    category: String(value.category || DEFAULT_PROMPT_SNIPPET_CATEGORY).trim() || DEFAULT_PROMPT_SNIPPET_CATEGORY,
    order: Number.isFinite(Number(value.order)) ? Number.parseInt(value.order, 10) : 0,
    created_at: value.created_at || "",
    updated_at: value.updated_at || "",
  };
}

function normalizePromptSnippetList(items: any) {
  return (Array.isArray(items) ? items : [])
    .map(normalizePromptSnippet)
    .filter(Boolean)
    .sort((left: any, right: any) => (left.order - right.order) || left.tag.localeCompare(right.tag, "zh-Hans-CN"));
}

function isPromptSnippetTriggerChar(value: any) {
  const candidate = String(value || "");
  return candidate.length === 1 && PROMPT_SNIPPET_TRIGGER_CHARS.includes(candidate);
}

function isPromptSnippetBoundaryChar(value: any) {
  return !value || /\s/.test(String(value)) || PROMPT_SNIPPET_BOUNDARY_CHARS.includes(String(value));
}

function normalizePromptSnippetTrigger(value: any) {
  return String(value || "")
    .split("")
    .some((char) => isPromptSnippetTriggerChar(char)) ? "~" : "";
}

async function refreshPromptSnippets() {
  try {
    const response = await fetch(PROMPT_SNIPPETS_ENDPOINT);
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || translate("snippets.loadFailed"));
    state.promptSnippets = normalizePromptSnippetList(data.snippets);
    updatePromptSnippetSuggest();
  } catch (error: any) {
    console.warn(error.message || translate("snippets.loadFailed"));
    state.promptSnippets = [];
  }
}

function promptSnippetSuggestElement() {
  if (promptSnippetSuggestEl) return promptSnippetSuggestEl;
  promptSnippetSuggestEl = document.createElement("div");
  promptSnippetSuggestEl.className = "prompt-snippet-suggest hidden";
  promptSnippetSuggestEl.setAttribute("aria-label", translate("snippets.suggestLabel"));
  els.promptEditor?.closest(".prompt-editor-wrap")?.appendChild(promptSnippetSuggestEl);
  return promptSnippetSuggestEl;
}

function promptSnippetSelectionButtonElement() {
  if (promptSnippetSelectionButtonEl) return promptSnippetSelectionButtonEl;
  promptSnippetSelectionButtonEl = document.createElement("button");
  promptSnippetSelectionButtonEl.className = "prompt-snippet-save-button hidden";
  promptSnippetSelectionButtonEl.type = "button";
  promptSnippetSelectionButtonEl.textContent = translate("snippets.saveSelection");
  promptSnippetSelectionButtonEl.setAttribute("aria-label", translate("snippets.saveSelectionLabel"));
  promptSnippetSelectionButtonEl.addEventListener("mousedown", (event: any) => event.preventDefault());
  promptSnippetSelectionButtonEl.addEventListener("click", (event: any) => {
    event.preventDefault();
    event.stopPropagation();
    openPromptSnippetSavePopover();
  });
  els.promptEditor?.closest(".prompt-editor-wrap")?.appendChild(promptSnippetSelectionButtonEl);
  return promptSnippetSelectionButtonEl;
}

function promptSnippetPopoverElement() {
  if (promptSnippetPopoverEl) return promptSnippetPopoverEl;
  promptSnippetPopoverEl = document.createElement("div");
  promptSnippetPopoverEl.className = "prompt-snippet-popover hidden";
  promptSnippetPopoverEl.setAttribute("role", "dialog");
  promptSnippetPopoverEl.setAttribute("aria-label", translate("snippets.popoverLabel"));
  els.promptEditor?.closest(".prompt-editor-wrap")?.appendChild(promptSnippetPopoverEl);
  return promptSnippetPopoverEl;
}

function activePromptSnippetMatch() {
  const selection = window.getSelection();
  if (!selection || !selection.rangeCount || !selection.isCollapsed || !els.promptEditor) return null;
  if (!els.promptEditor.contains(selection.anchorNode)) return null;
  const selectionRange = selection.getRangeAt(0);
  let container = selectionRange.startContainer;
  let offset = selectionRange.startOffset;
  if (container.nodeType === Node.ELEMENT_NODE) {
    const previousNode = container.childNodes[offset - 1];
    if (previousNode?.nodeType !== Node.TEXT_NODE) return null;
    container = previousNode;
    offset = (previousNode.textContent || "").length;
  }
  if (container.nodeType !== Node.TEXT_NODE) return null;
  const textBeforeCaret = (container.textContent || "").slice(0, offset);
  const match = textBeforeCaret.match(PROMPT_SNIPPET_TRIGGER_PATTERN);
  if (!match) return null;
  if (!normalizePromptSnippetTrigger(match[2])) return null;
  const token = `${match[2]}${match[3] || ""}`;
  const tokenStart = offset - token.length;
  const range = document.createRange();
  range.setStart(container, tokenStart);
  range.setEnd(container, offset);
  return {
    query: match[3] || "",
    range,
  };
}

function updatePromptSnippetSuggest() {
  const suggest = promptSnippetSuggestElement();
  if (!suggest || !els.promptEditor) return;
  const match = activePromptSnippetMatch();
  if (!match) {
    hidePromptSnippetSuggest();
    return;
  }
  const query = match.query.toLowerCase();
  const snippets = promptSnippetsForQuery(query).slice(0, 8);
  if (!snippets.length) {
    hidePromptSnippetSuggest();
    return;
  }
  state.activePromptSnippetRange = match.range.cloneRange();
  suggest.innerHTML = snippets.map((snippet: any) => `
    <button type="button" class="prompt-snippet-option" data-prompt-snippet-id="${escapeHtml(snippet.id)}">
      <span class="prompt-snippet-option-tag">~${escapeHtml(snippet.tag)}</span>
      <span class="prompt-snippet-option-main">
        <span>${escapeHtml(snippet.title)}</span>
        <small>${escapeHtml(promptSnippetPreview(snippet.content))}</small>
      </span>
      <small>${escapeHtml(snippet.category)}</small>
    </button>
  `).join("");
  suggest.querySelectorAll("[data-prompt-snippet-id]").forEach((button: any) => {
    button.addEventListener("mousedown", (event: any) => event.preventDefault());
    button.addEventListener("click", () => {
      const snippet = findPromptSnippetById(button.dataset.promptSnippetId);
      if (snippet) insertPromptSnippet(snippet);
    });
  });
  positionPromptSnippetSuggestAtCaret(match);
  suggest.classList.remove("hidden");
}

function promptSnippetsForQuery(query: any) {
  const normalized = String(query || "").trim().toLowerCase();
  if (!normalized) return state.promptSnippets.slice();
  return state.promptSnippets.filter((snippet: any) => (
    snippet.tag.toLowerCase().includes(normalized)
    || snippet.title.toLowerCase().includes(normalized)
    || snippet.content.toLowerCase().includes(normalized)
  ));
}

function promptSnippetPreview(text: any) {
  const clean = String(text || "").replace(/\s+/g, " ").trim();
  return clean.length > 42 ? `${clean.slice(0, 42)}...` : clean;
}

function positionPromptSnippetSuggestAtCaret(match: any) {
  const suggest = promptSnippetSuggestElement();
  if (!suggest || !els.promptEditor || !match?.range) return;
  const host = els.promptEditor.closest(".prompt-editor-wrap") || els.promptEditor;
  const anchorRect = mentionRangeRect(match.range) || els.promptEditor.getBoundingClientRect();
  positionPromptPopoverAtAnchor(
    suggest,
    host,
    anchorRect,
    {
      left: "--prompt-snippet-left",
      top: "--prompt-snippet-top",
      width: "--prompt-snippet-width",
      maxHeight: "--prompt-popover-max-height",
    },
    { minWidth: 260, maxWidth: 380, maxHeight: 260 },
  );
}

function insertPromptSnippet(snippet: any) {
  const normalized = normalizePromptSnippet(snippet);
  if (!normalized || !els.promptEditor) return;
  let match = activePromptSnippetMatch();
  if (!match?.range && state.activePromptSnippetRange) {
    match = { query: "", range: state.activePromptSnippetRange };
  }
  let trailingSpace = null;
  if (match?.range) {
    match.range.deleteContents();
    const chip = createPromptSnippetChip(normalized);
    trailingSpace = document.createTextNode(" ");
    match.range.insertNode(chip);
    chip.after(trailingSpace);
  } else {
    const currentText = getPromptText();
    if (currentText && !/\s$/.test(currentText)) appendPromptText(" ");
    els.promptEditor.append(createPromptSnippetChip(normalized));
    trailingSpace = document.createTextNode(" ");
    els.promptEditor.append(trailingSpace);
  }
  syncPromptAfterChipMutation();
  hidePromptSnippetSuggest();
  setCaretAfterNode(trailingSpace);
}

function createPromptSnippetChip(snippet: any) {
  const normalized = normalizePromptSnippet(snippet) || {
    id: "",
    tag: "",
    title: "",
    content: "",
    category: DEFAULT_PROMPT_SNIPPET_CATEGORY,
  };
  const chip = document.createElement("span");
  chip.className = "prompt-snippet-chip";
  chip.contentEditable = "false";
  chip.tabIndex = 0;
  chip.draggable = true;
  chip.dataset.promptChip = "snippet";
  chip.dataset.promptSnippetId = normalized.id;
  chip.dataset.promptSnippetTag = normalized.tag;
  chip.dataset.promptSnippetTitle = normalized.title;
  chip.dataset.promptSnippetContent = normalized.content;
  chip.dataset.promptSnippetCategory = normalized.category;
  chip.title = normalized.content;
  const mark = document.createElement("span");
  mark.className = "prompt-snippet-chip-mark";
  mark.textContent = "~";
  const label = document.createElement("span");
  label.className = "prompt-snippet-chip-label";
  label.textContent = normalized.tag;
  const remove = document.createElement("button");
  remove.className = "prompt-snippet-chip-remove";
  remove.type = "button";
  remove.setAttribute("data-remove-prompt-snippet-chip", "");
  remove.setAttribute("aria-label", formatTranslation("snippets.remove", { tag: normalized.tag }));
  remove.textContent = "×";
  chip.append(mark, label, remove);
  chip.addEventListener("keydown", (event: any) => {
    if (event.key === "Backspace" || event.key === "Delete") {
      event.preventDefault();
      removePromptGalleryChip(chip);
    }
    if (event.key === "Enter") {
      event.preventDefault();
      openPromptSnippetChipPopover(chip);
    }
  });
  return chip;
}

function findPromptSnippetRefAt(promptText: any, cursor: any) {
  const trigger = promptText[cursor];
  if (!isPromptSnippetTriggerChar(trigger)) return null;
  const previous = cursor > 0 ? promptText[cursor - 1] : "";
  if (!isPromptSnippetBoundaryChar(previous)) return null;
  let tagStart = cursor + 1;
  while (isPromptSnippetTriggerChar(promptText[tagStart])) tagStart += 1;
  const rest = promptText.slice(tagStart);
  const match = rest.match(/^([^\s~～〜∼˜@#，。,.；;：:！？!?、（）()\[\]【】"'“”‘’]+)/);
  if (!match) return null;
  const tag = match[1];
  const snippet = findPromptSnippetByTag(tag);
  if (!snippet) return null;
  return { snippet, end: tagStart + tag.length };
}

function findPromptSnippetById(id: any) {
  return state.promptSnippets.find((snippet: any) => snippet.id === id) || null;
}

function findPromptSnippetByTag(tag: any) {
  const key = String(tag || "").replace(/^[~～〜∼˜]+/, "").toLowerCase();
  return state.promptSnippets.find((snippet: any) => snippet.tag.toLowerCase() === key) || null;
}

function expandPromptSnippets(prompt: any) {
  const text = String(prompt || "");
  return text.replace(/(^|[\s\n，。,.；;：:！？!?、（）()\[\]【】"'“”‘’])([~～〜∼˜]+)([^\s~～〜∼˜@#，。,.；;：:！？!?、（）()\[\]【】"'“”‘’]+)/g, (full: any, prefix: any, _trigger: any, tag: any) => {
    const snippet = findPromptSnippetByTag(tag);
    if (!snippet) return full;
    return `${prefix}${snippet.content}`;
  });
}

function getPromptSelectionForSnippet() {
  const selection = window.getSelection();
  if (!selection || !selection.rangeCount || selection.isCollapsed || !els.promptEditor) return null;
  const range = selection.getRangeAt(0);
  if (!rangeIntersectsNode(range, els.promptEditor)) return null;
  const text = promptTextFromRange(range).replace(/\u00a0/g, " ").trim();
  if (!text || selectionContainsPromptAtomicChip(range)) return null;
  return { range: range.cloneRange(), text };
}

function selectionContainsPromptAtomicChip(range: any) {
  if (!range || range.collapsed) return false;
  const fragment = range.cloneContents();
  return Boolean(fragment.querySelector?.(".gallery-chip, .color-chip, .prompt-snippet-chip"));
}

function updatePromptSnippetSelectionButton() {
  if (promptSnippetPopoverEl && !promptSnippetPopoverEl.classList.contains("hidden")) return;
  const selection = getPromptSelectionForSnippet();
  if (!selection) {
    hidePromptSnippetSelectionButton();
    return;
  }
  showPromptSnippetSelectionButton(selection);
}

function showPromptSnippetSelectionButton(selection: any) {
  const button = promptSnippetSelectionButtonElement();
  if (!button || !selection?.range) return;
  state.promptSnippetSelectionRange = selection.range.cloneRange();
  state.promptSnippetSelectionText = selection.text;
  const editorRect = promptSnippetVisibleEditorRect();
  const rect = promptSnippetSelectionAnchorRect(selection, editorRect);
  if (!rect || !editorRect) return;
  const buttonWidth = 54;
  const buttonHeight = 30;
  const gap = 6;
  const viewportWidth = window.innerWidth || document.documentElement.clientWidth || rect.right;
  const maxLeft = Math.max(8, viewportWidth - buttonWidth - 8);
  const minTop = Math.max(8, editorRect.top + 4);
  const maxTop = Math.max(minTop, editorRect.bottom - buttonHeight - 4);
  const endpointLeft = rect.right;
  const inlineLeft = endpointLeft + gap;
  const left = inlineLeft <= maxLeft
    ? Math.max(8, inlineLeft)
    : Math.min(maxLeft, Math.max(8, endpointLeft - buttonWidth));
  const preferredTop = inlineLeft <= maxLeft
    ? Math.max(8, rect.top + Math.max(0, (rect.height - buttonHeight) / 2))
    : Math.max(8, rect.bottom + gap);
  const top = Math.min(maxTop, Math.max(minTop, preferredTop));
  button.style.setProperty("--prompt-snippet-save-left", `${left}px`);
  button.style.setProperty("--prompt-snippet-save-top", `${top}px`);
  button.classList.remove("hidden");
}

function promptSnippetSelectionAnchorRect(selection: any, editorRect: any) {
  if (!selection?.range || !editorRect) return null;
  const endRange = selection.range.cloneRange();
  endRange.collapse(false);
  const endRect = clipRectToBounds(mentionRangeRect(endRange), editorRect);
  if (endRect && (endRect.width || endRect.height)) return endRect;
  const visibleRects = promptSnippetSelectionVisibleRects(selection.range, editorRect);
  return visibleRects.length ? visibleRects[visibleRects.length - 1] : promptSnippetFallbackVisibleAnchorRect(editorRect);
}

function promptSnippetVisibleEditorRect() {
  if (!els.promptEditor) return null;
  const rect = els.promptEditor.getBoundingClientRect();
  const viewportWidth = window.innerWidth || document.documentElement.clientWidth || rect.right;
  const viewportHeight = window.innerHeight || document.documentElement.clientHeight || rect.bottom;
  return clipRectToBounds(rect, {
    left: 8,
    top: 8,
    right: Math.max(8, viewportWidth - 8),
    bottom: Math.max(8, viewportHeight - 8),
  });
}

function promptSnippetSelectionVisibleRects(range: any, editorRect: any) {
  return Array.from(range.getClientRects())
    .map((rect: any) => clipRectToBounds(rect, editorRect))
    .filter((rect: any) => rect && (rect.width || rect.height));
}

function promptSnippetFallbackVisibleAnchorRect(editorRect: any) {
  if (!editorRect) return null;
  const width = Math.max(1, Math.min(12, editorRect.width));
  const height = Math.max(1, Math.min(24, editorRect.height));
  return {
    left: Math.max(editorRect.left, editorRect.right - width),
    right: editorRect.right,
    top: Math.max(editorRect.top, editorRect.bottom - height),
    bottom: editorRect.bottom,
    width,
    height,
  };
}

function clipRectToBounds(rect: any, bounds: any) {
  if (!rect || !bounds) return null;
  const left = Math.max(rect.left, bounds.left);
  const right = Math.min(rect.right, bounds.right);
  const top = Math.max(rect.top, bounds.top);
  const bottom = Math.min(rect.bottom, bounds.bottom);
  const width = Math.max(0, right - left);
  const height = Math.max(0, bottom - top);
  if (!width && !height) return null;
  return { left, right, top, bottom, width, height };
}

function hidePromptSnippetSelectionButton() {
  const button = promptSnippetSelectionButtonElement();
  button?.classList.add("hidden");
  button?.style.removeProperty("--prompt-snippet-save-left");
  button?.style.removeProperty("--prompt-snippet-save-top");
}

function openPromptSnippetSavePopover() {
  if (!state.promptSnippetSelectionText || !state.promptSnippetSelectionRange) return;
  const snippet = {
    tag: suggestPromptSnippetTag(state.promptSnippetSelectionText),
    title: "",
    content: state.promptSnippetSelectionText,
    category: DEFAULT_PROMPT_SNIPPET_CATEGORY,
  };
  renderPromptSnippetForm("save", snippet);
  positionPromptSnippetPopoverAtSelectionButton();
}

function openPromptSnippetChipPopover(chip: any) {
  const snippet = promptSnippetFromChip(chip);
  if (!snippet) return;
  const popover = promptSnippetPopoverElement();
  if (!popover) return;
  promptSnippetPopoverState.mode = "chip";
  promptSnippetPopoverState.chip = chip;
  promptSnippetPopoverState.snippetId = snippet.id;
  popover.innerHTML = `
    <div class="prompt-snippet-popover-title">~${escapeHtml(snippet.tag)}</div>
    <div class="prompt-snippet-popover-meta">${escapeHtml(snippet.title)} · ${escapeHtml(snippet.category)}</div>
    <div class="prompt-snippet-popover-preview">${escapeHtml(snippet.content)}</div>
    <div class="prompt-snippet-popover-actions">
      <button class="ghost-button text-sm" type="button" data-prompt-snippet-expand>${escapeHtml(translate("snippets.expand"))}</button>
      <button class="ghost-button text-sm" type="button" data-prompt-snippet-edit>${escapeHtml(translate("snippets.edit"))}</button>
      <button class="ghost-button text-sm" type="button" data-prompt-snippet-close>${escapeHtml(translate("snippets.close"))}</button>
    </div>
  `;
  function handlePopoverActionClick(event: any, action: () => void) {
    event.preventDefault();
    event.stopPropagation();
    action();
  }
  popover.querySelector("[data-prompt-snippet-expand]")?.addEventListener("click", (event: any) => handlePopoverActionClick(event, () => expandPromptSnippetChip(chip)));
  popover.querySelector("[data-prompt-snippet-edit]")?.addEventListener("click", (event: any) => handlePopoverActionClick(event, () => renderPromptSnippetForm("edit", snippet, chip)));
  popover.querySelector("[data-prompt-snippet-close]")?.addEventListener("click", (event: any) => handlePopoverActionClick(event, closePromptSnippetPopover));
  positionPromptSnippetPopoverAtChip(chip);
  popover.classList.remove("hidden");
}

function renderPromptSnippetForm(mode: any, snippet: any, chip: any = null) {
  const popover = promptSnippetPopoverElement();
  if (!popover) return;
  promptSnippetPopoverState.mode = mode;
  promptSnippetPopoverState.chip = chip;
  promptSnippetPopoverState.snippetId = snippet.id || null;
  popover.innerHTML = `
    <form class="prompt-snippet-form">
      <div class="prompt-snippet-popover-title">${escapeHtml(mode === "edit" ? translate("snippets.editTitle") : translate("snippets.saveTitle"))}</div>
      <label class="prompt-snippet-field">
        <span>${escapeHtml(translate("snippets.shortTag"))}</span>
        <input class="prompt-snippet-input" type="text" maxlength="24" value="${escapeHtml(snippet.tag || "")}" data-prompt-snippet-tag>
      </label>
      <label class="prompt-snippet-field">
        <span>${escapeHtml(translate("snippets.title"))}</span>
        <input class="prompt-snippet-input" type="text" maxlength="80" value="${escapeHtml(snippet.title || "")}" placeholder="${escapeHtml(translate("snippets.titlePlaceholder"))}" data-prompt-snippet-title>
      </label>
      <label class="prompt-snippet-field">
        <span>${escapeHtml(translate("snippets.category"))}</span>
        <input class="prompt-snippet-input" type="text" maxlength="32" value="${escapeHtml(snippet.category || DEFAULT_PROMPT_SNIPPET_CATEGORY)}" data-prompt-snippet-category>
      </label>
      <label class="prompt-snippet-field">
        <span>${escapeHtml(translate("snippets.content"))}</span>
        <textarea class="prompt-snippet-input prompt-snippet-textarea" maxlength="4000" data-prompt-snippet-content>${escapeHtml(snippet.content || "")}</textarea>
      </label>
      <div class="prompt-snippet-popover-actions">
        <button class="ghost-button text-sm" type="button" data-prompt-snippet-cancel>${escapeHtml(translate("snippets.cancel"))}</button>
        <button class="ghost-button text-sm" type="submit">${escapeHtml(mode === "edit" ? translate("snippets.save") : translate("snippets.saveSelection"))}</button>
      </div>
    </form>
  `;
  popover.querySelector("[data-prompt-snippet-cancel]")?.addEventListener("click", closePromptSnippetPopover);
  popover.querySelector(".prompt-snippet-form")?.addEventListener("submit", (event: any) => {
    event.preventDefault();
    savePromptSnippetFromPopover();
  });
  popover.classList.remove("hidden");
  window.setTimeout(() => (popover.querySelector("[data-prompt-snippet-tag]") as any)?.focus(), 0);
}

async function savePromptSnippetFromPopover() {
  const popover = promptSnippetPopoverElement();
  if (!popover) return;
  const payload = {
    tag: (popover.querySelector("[data-prompt-snippet-tag]") as any)?.value || "",
    title: (popover.querySelector("[data-prompt-snippet-title]") as any)?.value || "",
    category: (popover.querySelector("[data-prompt-snippet-category]") as any)?.value || DEFAULT_PROMPT_SNIPPET_CATEGORY,
    content: (popover.querySelector("[data-prompt-snippet-content]") as any)?.value || "",
  };
  try {
    const isEdit = promptSnippetPopoverState.mode === "edit" && promptSnippetPopoverState.snippetId;
    const response = await fetch(isEdit ? `${PROMPT_SNIPPETS_ENDPOINT}/${encodeURIComponent(promptSnippetPopoverState.snippetId)}` : PROMPT_SNIPPETS_ENDPOINT, {
      method: isEdit ? "PATCH" : "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || translate("snippets.saveFailed"));
    state.promptSnippets = normalizePromptSnippetList(data.snippets);
    const snippet = normalizePromptSnippet(data.snippet);
    if (isEdit && promptSnippetPopoverState.chip) {
      updatePromptSnippetChip(promptSnippetPopoverState.chip, snippet);
      syncPromptAfterChipMutation();
    } else if (snippet) {
      replacePromptSelectionWithSnippet(snippet);
    }
    closePromptSnippetPopover();
    hidePromptSnippetSelectionButton();
    setStatus(translate("snippets.saved"), "ok");
  } catch (error: any) {
    setStatus(error.message || translate("snippets.saveFailed"), "error");
  }
}

function replacePromptSelectionWithSnippet(snippet: any) {
  if (!state.promptSnippetSelectionRange || !els.promptEditor) return;
  const range = state.promptSnippetSelectionRange;
  if (!els.promptEditor.contains(range.commonAncestorContainer)) return;
  range.deleteContents();
  const chip = createPromptSnippetChip(snippet);
  const trailingSpace = document.createTextNode(" ");
  range.insertNode(chip);
  chip.after(trailingSpace);
  syncPromptAfterChipMutation();
  setCaretAfterNode(trailingSpace);
}

function promptSnippetFromChip(chip: any) {
  if (!chip) return null;
  const byId = findPromptSnippetById(chip.dataset.promptSnippetId);
  return byId || normalizePromptSnippet({
    id: chip.dataset.promptSnippetId,
    tag: chip.dataset.promptSnippetTag,
    title: chip.dataset.promptSnippetTitle,
    content: chip.dataset.promptSnippetContent,
    category: chip.dataset.promptSnippetCategory,
  });
}

function updatePromptSnippetChip(chip: any, snippet: any) {
  const normalized = normalizePromptSnippet(snippet);
  if (!chip || !normalized) return;
  chip.dataset.promptSnippetId = normalized.id;
  chip.dataset.promptSnippetTag = normalized.tag;
  chip.dataset.promptSnippetTitle = normalized.title;
  chip.dataset.promptSnippetContent = normalized.content;
  chip.dataset.promptSnippetCategory = normalized.category;
  chip.title = normalized.content;
  const label = chip.querySelector(".prompt-snippet-chip-label");
  if (label) label.textContent = normalized.tag;
  const remove = chip.querySelector("[data-remove-prompt-snippet-chip]");
  if (remove) remove.setAttribute("aria-label", formatTranslation("snippets.remove", { tag: normalized.tag }));
}

function expandPromptSnippetChip(chip: any) {
  const snippet = promptSnippetFromChip(chip);
  if (!snippet || !els.promptEditor?.contains(chip)) return;
  const text = document.createTextNode(snippet.content);
  chip.replaceWith(text);
  closePromptSnippetPopover();
  syncPromptAfterChipMutation();
  setCaretAfterNode(text);
}

function suggestPromptSnippetTag(text: any) {
  const clean = String(text || "")
    .replace(/[~～@#，。,.]/g, " ")
    .replace(/\s+/g, "")
    .trim();
  return clean.slice(0, 8) || translate("snippets.defaultTag");
}

function positionPromptSnippetPopoverAtSelectionButton() {
  const popover = promptSnippetPopoverElement();
  const button = promptSnippetSelectionButtonElement();
  if (!popover || !button) return;
  const buttonRect = button.getBoundingClientRect();
  positionPromptSnippetPopover(buttonRect);
}

function positionPromptSnippetPopoverAtChip(chip: any) {
  if (!chip || !els.promptEditor) return;
  const chipRect = chip.getBoundingClientRect();
  positionPromptSnippetPopover(chipRect);
}

function positionPromptSnippetPopover(anchorRect: any) {
  const popover = promptSnippetPopoverElement();
  if (!popover || !els.promptEditor) return;
  const host = els.promptEditor.closest(".prompt-editor-wrap") || els.promptEditor;
  positionPromptPopoverAtAnchor(
    popover,
    host,
    anchorRect,
    {
      left: "--prompt-snippet-popover-left",
      top: "--prompt-snippet-popover-top",
      width: "--prompt-snippet-popover-width",
      maxHeight: "--prompt-popover-max-height",
    },
    { minWidth: 280, maxWidth: 380, maxHeight: 360, minVisibleHeight: 150 },
  );
}

function closePromptSnippetPopover() {
  if (!promptSnippetPopoverEl) return;
  promptSnippetPopoverEl.classList.add("hidden");
  promptSnippetPopoverEl.innerHTML = "";
  promptSnippetPopoverEl.style.removeProperty("--prompt-snippet-popover-left");
  promptSnippetPopoverEl.style.removeProperty("--prompt-snippet-popover-top");
  promptSnippetPopoverEl.style.removeProperty("--prompt-snippet-popover-width");
  promptSnippetPopoverEl.style.removeProperty("--prompt-popover-max-height");
  promptSnippetPopoverState.mode = null;
  promptSnippetPopoverState.chip = null;
  promptSnippetPopoverState.snippetId = null;
  state.promptSnippetSelectionRange = null;
  state.promptSnippetSelectionText = "";
}

function hidePromptSnippetSuggest() {
  const suggest = promptSnippetSuggestElement();
  if (!suggest) return;
  suggest.classList.add("hidden");
  suggest.innerHTML = "";
  suggest.style.removeProperty("--prompt-snippet-left");
  suggest.style.removeProperty("--prompt-snippet-top");
  suggest.style.removeProperty("--prompt-snippet-width");
  suggest.style.removeProperty("--prompt-popover-max-height");
  state.activePromptSnippetRange = null;
}

function handlePromptSnippetDocumentClick(target: any) {
  if (promptSnippetSuggestEl && !promptSnippetSuggestEl.classList.contains("hidden")) {
    const clickedSuggest = promptSnippetSuggestEl.contains(target);
    const clickedPromptEditor = els.promptEditor?.contains(target);
    if (!clickedSuggest && !clickedPromptEditor) {
      hidePromptSnippetSuggest();
    }
  }
  if (promptSnippetPopoverEl && !promptSnippetPopoverEl.classList.contains("hidden")) {
    const clickedPopover = promptSnippetPopoverEl.contains(target);
    const clickedChip = target.closest?.(".prompt-snippet-chip");
    const clickedSave = promptSnippetSelectionButtonEl?.contains(target);
    if (!clickedPopover && !clickedChip && !clickedSave) {
      closePromptSnippetPopover();
    }
  }
}

export function initPromptSnippetsFeature(): void {
  Object.assign(getLegacyBridge().methods, {
    normalizePromptSnippet,
    normalizePromptSnippetList,
    refreshPromptSnippets,
    promptSnippetSuggestElement,
    promptSnippetSelectionButtonElement,
    promptSnippetPopoverElement,
    activePromptSnippetMatch,
    updatePromptSnippetSuggest,
    promptSnippetsForQuery,
    promptSnippetPreview,
    positionPromptSnippetSuggestAtCaret,
    insertPromptSnippet,
    createPromptSnippetChip,
    findPromptSnippetRefAt,
    findPromptSnippetById,
    findPromptSnippetByTag,
    expandPromptSnippets,
    getPromptSelectionForSnippet,
    selectionContainsPromptAtomicChip,
    updatePromptSnippetSelectionButton,
    showPromptSnippetSelectionButton,
    promptSnippetSelectionAnchorRect,
    hidePromptSnippetSelectionButton,
    openPromptSnippetSavePopover,
    openPromptSnippetChipPopover,
    renderPromptSnippetForm,
    savePromptSnippetFromPopover,
    replacePromptSelectionWithSnippet,
    promptSnippetFromChip,
    updatePromptSnippetChip,
    expandPromptSnippetChip,
    suggestPromptSnippetTag,
    positionPromptSnippetPopoverAtSelectionButton,
    positionPromptSnippetPopoverAtChip,
    positionPromptSnippetPopover,
    closePromptSnippetPopover,
    hidePromptSnippetSuggest,
    handlePromptSnippetDocumentClick,
  });
}

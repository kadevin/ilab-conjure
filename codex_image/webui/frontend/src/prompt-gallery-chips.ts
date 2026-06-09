import { getLegacyBridge } from "./state";
import { positionPromptPopoverAtAnchor } from "./prompt-popover-position";
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

function escapeHtml(value: any): string { return legacyMethod("escapeHtml", value); }
function categoryLabel(category: any): string { return legacyMethod("categoryLabel", category); }
function categoryPromptRole(category: any): string { return legacyMethod("categoryPromptRole", category); }
function findGalleryItem(itemId: any): any { return legacyMethod("findGalleryItem", itemId); }
function addGalleryInput(item: any, options?: any): void { legacyMethod("addGalleryInput", item, options); }
function gallerySource(item: any): any { return legacyMethod("gallerySource", item); }
function galleryInputs(): any[] { return legacyMethod("galleryInputs"); }
function renderImageStrip(): void { legacyMethod("renderImageStrip"); }
function setMode(mode: any): void { legacyMethod("setMode", mode); }
function updatePromptCount(): void { legacyMethod("updatePromptCount"); }
function updateRequestPreview(): void { legacyMethod("updateRequestPreview"); }
function getPromptText(): string { return legacyMethod("getPromptText"); }
function appendPromptText(text: any): void { legacyMethod("appendPromptText", text); }
function syncPromptFromEditor(): void { legacyMethod("syncPromptFromEditor"); }
function clearPromptEditorIfEmpty(): void { legacyMethod("clearPromptEditorIfEmpty"); }
function hideColorSuggest(): void { legacyMethod("hideColorSuggest"); }
function hidePromptSnippetSuggest(): void { legacyMethod("hidePromptSnippetSuggest"); }
function setCaretAfterNode(node: any): void { legacyMethod("setCaretAfterNode", node); }
function mentionRangeRect(range: any): any { return legacyMethod("mentionRangeRect", range); }

export function galleryRefsByMentionLength(refs: any): any[] {
  return (Array.isArray(refs) ? refs : [])
    .filter((ref: any) => ref?.name && !ref.missing && ref.image_url)
    .slice()
    .sort((left: any, right: any) => String(right.name || "").length - String(left.name || "").length);
}

export function findGalleryRefMentionAt(promptText: any, cursor: any, refs: any): any {
  if (promptText[cursor] !== "@") return null;
  for (const ref of refs) {
    const name = String(ref.name || "");
    if (!name) continue;
    const mention = `@${name}`;
    if (promptText.startsWith(mention, cursor)) {
      return { ref, end: cursor + mention.length };
    }
  }
  return null;
}

export function updateMentionSuggest(): void {
  if (!els.mentionSuggest || !els.promptEditor) return;
  const match = activeMentionMatch();
  if (!match) {
    hideMentionSuggest();
    return;
  }
  const query = match.query.toLowerCase();
  const items = state.galleryItems.filter((item: any) => item.name.toLowerCase().includes(query)).slice(0, 8);
  if (!items.length) {
    hideMentionSuggest();
    return;
  }
  els.mentionSuggest.innerHTML = items.map((item: any) => `
    <button type="button" class="mention-option" data-mention-id="${escapeHtml(item.id)}">
      <img src="${escapeHtml(item.image_url)}" alt="">
      <span>@${escapeHtml(item.name)}</span>
      <small>${escapeHtml(categoryLabel(item.category))}</small>
    </button>
  `).join("");
  els.mentionSuggest.querySelectorAll("[data-mention-id]").forEach((button: any) => {
    button.addEventListener("mousedown", (event: any) => {
      event.preventDefault();
      const item = findGalleryItem(button.dataset.mentionId);
      if (item) insertGalleryMention(item);
    });
  });
  positionMentionSuggestAtCaret(match);
  els.mentionSuggest.classList.remove("hidden");
}

export function activeMentionMatch(): any {
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
  const match = textBeforeCaret.match(/@([^\s@，。,.]*)$/);
  if (!match) return null;
  const tokenStart = offset - match[0].length;
  const range = document.createRange();
  range.setStart(container, tokenStart);
  range.setEnd(container, offset);
  return {
    query: match[1] || "",
    range,
  };
}

export function insertGalleryMention(item: any): void {
  const match = activeMentionMatch();
  let trailingSpace = null;
  if (match?.range) {
    match.range.deleteContents();
    const chip = createGalleryChip(item);
    trailingSpace = document.createTextNode(" ");
    match.range.insertNode(chip);
    chip.after(trailingSpace);
  } else {
    const currentText = getPromptText();
    if (currentText && !/\s$/.test(currentText)) {
      appendPromptText(" ");
    }
    els.promptEditor.append(createGalleryChip(item));
    trailingSpace = document.createTextNode(" ");
    els.promptEditor.append(trailingSpace);
  }
  addGalleryInput(item, { syncPrompt: false });
  syncPromptFromEditor();
  updatePromptCount();
  updateRequestPreview();
  hideMentionSuggest();
  hideColorSuggest();
  setCaretAfterNode(trailingSpace);
}

export function positionMentionSuggestAtCaret(match: any): void {
  if (!els.mentionSuggest || !els.promptEditor || !match?.range) return;
  const host = els.promptEditor.closest(".prompt-editor-wrap") || els.promptEditor;
  const anchorRect = mentionRangeRect(match.range) || els.promptEditor.getBoundingClientRect();
  positionPromptPopoverAtAnchor(
    els.mentionSuggest,
    host,
    anchorRect,
    {
      left: "--mention-left",
      top: "--mention-top",
      width: "--mention-width",
      maxHeight: "--prompt-popover-max-height",
    },
    { minWidth: 220, maxWidth: 340, maxHeight: 240 },
  );
}

export function createGalleryChip(item: any): HTMLElement {
  const chip = document.createElement("span");
  chip.className = "gallery-chip";
  chip.contentEditable = "false";
  chip.tabIndex = 0;
  chip.draggable = true;
  chip.dataset.promptChip = "gallery";
  chip.dataset.galleryId = item.id;
  chip.dataset.galleryName = item.name;
  chip.dataset.galleryCategory = item.category || "";
  chip.dataset.galleryCategoryName = item.category_name || categoryLabel(item.category);
  chip.dataset.galleryCategoryPromptRole = item.category_prompt_role || categoryPromptRole(item.category);
  chip.dataset.galleryPromptNote = item.prompt_note || "";
  chip.dataset.galleryImageUrl = item.image_url || "";
  const image = document.createElement("img");
  image.src = item.image_url || "";
  image.alt = "";
  const label = document.createElement("span");
  label.textContent = `@${item.name}`;
  const remove = document.createElement("button");
  remove.className = "gallery-chip-remove";
  remove.type = "button";
  remove.setAttribute("data-remove-gallery-chip", "");
  remove.setAttribute("aria-label", formatTranslation("promptGallery.remove", { name: item.name }));
  remove.textContent = "×";
  chip.append(image, label, remove);
  chip.addEventListener("keydown", (event: any) => {
    if (event.key === "Backspace" || event.key === "Delete") {
      event.preventDefault();
      removePromptGalleryChip(chip);
    }
  });
  return chip;
}

export function removePromptGalleryChip(chip: any): void {
  if (!chip || !els.promptEditor?.contains(chip)) return;
  const nextNode = chip.nextSibling;
  chip.remove();
  if (nextNode?.nodeType === Node.TEXT_NODE && !nextNode.textContent.trim()) {
    nextNode.remove();
  }
  clearPromptEditorIfEmpty();
  syncPromptFromEditor();
  updatePromptCount();
  const galleryInputsChanged = syncGalleryInputsFromPrompt();
  if (!galleryInputsChanged) updateRequestPreview();
  hideMentionSuggest();
  hideColorSuggest();
  setCaretToEnd(els.promptEditor);
}

export function currentPromptGalleryIds(): Set<any> {
  if (!els.promptEditor) return new Set();
  return new Set(
    Array.from(els.promptEditor.querySelectorAll(".gallery-chip[data-gallery-id]"))
      .map((chip: any) => chip.dataset.galleryId)
      .filter(Boolean)
  );
}

export function ensurePromptGalleryMention(item: any): void {
  if (!item || !els.promptEditor || currentPromptGalleryIds().has(item.id)) {
    syncPromptFromEditor();
    return;
  }
  const currentText = getPromptText();
  if (currentText && !/\s$/.test(currentText)) {
    appendPromptText(" ");
  }
  els.promptEditor.append(createGalleryChip(item));
  appendPromptText(" ");
  syncPromptFromEditor();
  updatePromptCount();
  hideMentionSuggest();
  hideColorSuggest();
}

export function syncGalleryInputsFromPrompt(): boolean {
  const chips = Array.from(els.promptEditor?.querySelectorAll(".gallery-chip[data-gallery-id]") || []);
  const mentionedIds = new Set(chips.map((chip: any) => chip.dataset.galleryId).filter(Boolean));
  const beforeKey = imageSourcesKey(state.images);
  const uploads = state.images.filter((source: any) => source.kind !== "gallery");
  const existingById = new Map(state.images.filter((source: any) => source.kind === "gallery").map((source: any) => [source.id, source]));
  const galleries = chips.map((chip: any) => {
    const itemId = chip.dataset.galleryId;
    const existing = existingById.get(itemId);
    if (existing) return existing;
    const item = findGalleryItem(itemId);
    if (item) return gallerySource(item);
    return gallerySource({
      id: itemId,
      name: chip.dataset.galleryName || chip.textContent.replace(/^@/, "").trim() || translate("gallery.imageFallback"),
      category: chip.dataset.galleryCategory || "",
      category_name: chip.dataset.galleryCategoryName || "",
      category_prompt_role: chip.dataset.galleryCategoryPromptRole || "",
      prompt_note: chip.dataset.galleryPromptNote || "",
      image_url: chip.dataset.galleryImageUrl || "",
      missing: true,
    });
  }).filter((source: any) => source.id && mentionedIds.has(source.id));
  state.images = [...uploads, ...galleries];
  if (imageSourcesKey(state.images) === beforeKey) return false;
  if (!state.images.length) {
    setMode("generate");
  }
  renderImageStrip();
  updateRequestPreview();
  return true;
}

export function imageSourcesKey(sources: any): string {
  return JSON.stringify((sources || []).map((source: any) => [
    source.kind,
    source.kind === "gallery" ? source.id : source.name,
    Boolean(source.missing),
  ]));
}

export function syncPromptGalleryMentionsFromInputs(): boolean {
  if (!els.promptEditor) return false;
  const selectedGalleryIds = new Set(galleryInputs().map((source: any) => source.id));
  let changed = false;
  els.promptEditor.querySelectorAll(".gallery-chip[data-gallery-id]").forEach((chip: any) => {
    if (!selectedGalleryIds.has(chip.dataset.galleryId)) {
      chip.remove();
      changed = true;
    }
  });
  if (!changed) return false;
  clearPromptEditorIfEmpty();
  syncPromptFromEditor();
  updatePromptCount();
  return true;
}

export function hideMentionSuggest(): void {
  if (!els.mentionSuggest) return;
  els.mentionSuggest.classList.add("hidden");
  els.mentionSuggest.innerHTML = "";
  els.mentionSuggest.style.removeProperty("--mention-left");
  els.mentionSuggest.style.removeProperty("--mention-top");
  els.mentionSuggest.style.removeProperty("--mention-width");
  els.mentionSuggest.style.removeProperty("--prompt-popover-max-height");
}

function setCaretToEnd(element: any): void {
  legacyMethod("setCaretToEnd", element);
}

export function initPromptGalleryChipsFeature(): void {
  Object.assign(getLegacyBridge().methods, {
    galleryRefsByMentionLength,
    findGalleryRefMentionAt,
    updateMentionSuggest,
    activeMentionMatch,
    insertGalleryMention,
    positionMentionSuggestAtCaret,
    createGalleryChip,
    removePromptGalleryChip,
    currentPromptGalleryIds,
    ensurePromptGalleryMention,
    syncGalleryInputsFromPrompt,
    imageSourcesKey,
    syncPromptGalleryMentionsFromInputs,
    hideMentionSuggest,
  });
}

import { getLegacyBridge } from "./state";
import { translate } from "./i18n";
import { createImageMentionChip, imageMentionLabel, imageReferenceKey } from "./prompt-image-mentions";

let activeIndex = 0;
let lastQuery = "";
let limit = 8;
let candidates: any[] = [];
let mentionRange: Range | null = null;

export function updateImageMentionMenu(): void {
  const { els, state, methods } = getLegacyBridge();
  const match = methods.activeMentionMatch!();
  if (!match) { methods.hideMentionSuggest!(); return; }
  mentionRange = match.range.cloneRange();
  const query = match.query.toLocaleLowerCase();
  if (query !== lastQuery || els.mentionSuggest.classList.contains("hidden")) { activeIndex = 0; limit = 8; }
  lastQuery = query;
  const selected = new Set(state.images.filter((item: any) => item.kind === "gallery").map((item: any) => item.id));
  const current = state.images.filter((item: any) => !item.missing && [imageMentionLabel(item), item.name, item.filename]
    .some(value => String(value || "").toLocaleLowerCase().includes(query)));
  const galleries = state.galleryItems.filter((item: any) => !item.missing && !selected.has(item.id)
    && [item.name, item.category_name, methods.categoryLabel!(item.category)].some(value => String(value || "").toLocaleLowerCase().includes(query)));
  candidates = [...current, ...galleries.slice(0, limit).map((item: any) => ({ ...item, kind: "gallery" }))];
  const escape = methods.escapeHtml;
  const row = (source: any, index: number) => {
    const label = source.kind === "gallery" ? source.name : `${imageMentionLabel(source)} · ${source.name || source.filename || ""}`;
    const badge = source.kind === "gallery" ? methods.categoryLabel!(source.category)
      : translate(source.kind === "asset" ? "imageInput.recentBadge" : "imageInput.uploadBadge");
    return `<button type="button" role="option" id="image-mention-option-${index}" class="mention-option" data-image-mention-index="${index}">
      <img src="${escape(source.previewUrl || source.image_url || "")}" alt=""><span>${escape(label)}</span><small>${escape(badge)}</small></button>`;
  };
  els.mentionSuggest.setAttribute("role", "listbox");
  els.mentionSuggest.setAttribute("aria-label", translate("promptMention.choose"));
  els.mentionSuggest.innerHTML = (current.length ? `<div class="mention-group-label">${escape(translate("promptMention.current"))}</div>${current.map(row).join("")}` : "")
    + (galleries.length ? `<div class="mention-group-label">${escape(translate("promptMention.gallery"))}</div>${candidates.slice(current.length).map((item, index) => row(item, index + current.length)).join("")}` : "")
    + (!candidates.length ? `<div class="mention-group-label">${escape(translate("promptMention.empty"))}</div>` : "")
    + (galleries.length > limit ? `<button type="button" class="mention-more">${escape(translate("promptMention.more"))}</button>` : "");
  els.mentionSuggest.querySelectorAll("[data-image-mention-index]").forEach((button: HTMLButtonElement) => {
    button.addEventListener("mousedown", event => event.preventDefault());
    button.addEventListener("click", () => selectImageMention(Number(button.dataset.imageMentionIndex)));
  });
  const more = els.mentionSuggest.querySelector(".mention-more");
  more?.addEventListener("mousedown", (event: MouseEvent) => event.preventDefault());
  more?.addEventListener("click", () => {
    restoreMentionSelection();
    limit += 24;
    updateImageMentionMenu();
    els.promptEditor.focus({ preventScroll: true });
  });
  activeIndex = Math.min(activeIndex, Math.max(0, candidates.length - 1));
  methods.positionMentionSuggestAtCaret!(match);
  els.mentionSuggest.classList.remove("hidden");
  els.promptEditor.setAttribute("aria-controls", "mentionSuggest");
  els.promptEditor.setAttribute("aria-expanded", "true");
  highlight();
}

function highlight(): void {
  const { els } = getLegacyBridge();
  els.mentionSuggest.querySelectorAll("[data-image-mention-index]").forEach((button: HTMLElement, index: number) => {
    button.classList.toggle("is-active", index === activeIndex);
    button.setAttribute("aria-selected", String(index === activeIndex));
  });
  if (candidates.length) els.promptEditor.setAttribute("aria-activedescendant", `image-mention-option-${activeIndex}`);
  else els.promptEditor.removeAttribute("aria-activedescendant");
}

export function handleImageMentionKey(event: KeyboardEvent): boolean {
  const { els } = getLegacyBridge();
  if (event.isComposing || event.keyCode === 229 || els.mentionSuggest?.classList.contains("hidden")) return false;
  if (!candidates.length) return false;
  if (!["ArrowUp", "ArrowDown", "Enter"].includes(event.key) || event.metaKey || event.ctrlKey) return false;
  event.preventDefault();
  event.stopPropagation();
  if (event.key === "Enter") selectImageMention(activeIndex);
  else if (candidates.length) {
    activeIndex = (activeIndex + (event.key === "ArrowDown" ? 1 : -1) + candidates.length) % candidates.length;
    highlight();
    document.getElementById(`image-mention-option-${activeIndex}`)?.scrollIntoView({ block: "nearest" });
  }
  return true;
}

function selectImageMention(index: number): void {
  const source = candidates[index];
  if (!source) return;
  const { state, methods } = getLegacyBridge();
  if (!restoreMentionSelection()) return;
  if (source.kind === "gallery") { methods.insertGalleryMention!(source); return; }
  if (!state.images.some((item: any) => imageReferenceKey(item) === imageReferenceKey(source))) return;
  const match = methods.activeMentionMatch!();
  if (!match?.range) return;
  match.range.deleteContents();
  const chip = createImageMentionChip(source);
  const space = document.createTextNode(" ");
  match.range.insertNode(chip);
  chip.after(space);
  methods.syncPromptFromEditor!();
  methods.updatePromptCount!();
  methods.updateRequestPreview!();
  methods.hideMentionSuggest!();
  methods.hideColorSuggest!();
  methods.hidePromptSnippetSuggest!();
  methods.setCaretAfterNode!(space);
}

function restoreMentionSelection(): boolean {
  const { els, methods } = getLegacyBridge();
  if (methods.activeMentionMatch!()) return true;
  if (!mentionRange || !els.promptEditor.contains(mentionRange.startContainer) || !mentionRange.toString().startsWith("@")) return false;
  const selection = window.getSelection();
  selection?.removeAllRanges();
  selection?.addRange(mentionRange.cloneRange());
  selection?.collapseToEnd();
  els.promptEditor.focus({ preventScroll: true });
  return Boolean(methods.activeMentionMatch!());
}

import { getLegacyBridge } from "./state";
import { formatTranslation, translate } from "./i18n";

export type ImageMentionSource = { kind: string; id?: string; index?: number; missing?: boolean };
export type ImageMentionPart = string | { text: string; source: ImageMentionSource };
export type ImageMentionContext = { version: 1; parts: ImageMentionPart[] };

export function validImageMentionContext(value: any, prompt: string): value is ImageMentionContext {
  return value?.version === 1 && Array.isArray(value.parts) && value.parts.every((part: any) =>
    typeof part === "string" || (part && typeof part.text === "string" && part.source
      && ["local", "asset", "gallery"].includes(part.source.kind) && typeof part.source.id === "string"))
    && value.parts.map((part: ImageMentionPart) => typeof part === "string" ? part : part.text).join("") === prompt;
}

export function imageReferenceKey(source: any): string {
  if (source.prompt_ref_key) return source.prompt_ref_key;
  source.prompt_ref_key = source.kind === "upload"
    ? `local:${Array.from(crypto.getRandomValues(new Uint32Array(4))).join("-")}` : `${source.kind}:${source.id}`;
  return source.prompt_ref_key;
}

function sourcePointer(source: any): ImageMentionSource {
  return source.kind === "upload"
    ? { kind: "local", id: imageReferenceKey(source) }
    : { kind: source.kind, id: source.id };
}

function findSource(pointer: ImageMentionSource, sources: any[]): any {
  if (pointer.missing) return null;
  return sources.find(source => pointer.kind === "local"
    ? imageReferenceKey(source) === pointer.id
    : source.kind === pointer.kind && source.id === pointer.id);
}

export function imageMentionLabel(source: any, sources = getLegacyBridge().state.images): string {
  return source.kind === "gallery" ? source.name
    : formatTranslation("promptMention.image", { number: sources.indexOf(source) + 1 });
}

export function createImageMentionChip(source: any, fallback?: { text: string; source: ImageMentionSource }): HTMLElement {
  const { methods } = getLegacyBridge();
  if (source?.kind === "gallery") {
    const chip = methods.createGalleryChip!(source);
    chip.dataset.imageRefKey = imageReferenceKey(source);
    return chip;
  }
  const chip = document.createElement("span");
  chip.className = "gallery-chip image-mention-chip";
  chip.contentEditable = "false";
  chip.tabIndex = 0;
  chip.draggable = true;
  chip.dataset.promptChip = "image";
  chip.dataset.imageRefKey = source ? imageReferenceKey(source) : `${fallback?.source.kind}:${fallback?.source.id}`;
  chip.dataset.imageRefText = fallback?.text || `@${imageMentionLabel(source)}`;
  chip.dataset.imageRefSource = JSON.stringify(source ? sourcePointer(source) : { ...fallback?.source, missing: true });
  if (source?.previewUrl || source?.image_url) {
    const image = document.createElement("img");
    image.src = source.previewUrl || source.image_url;
    image.alt = "";
    chip.append(image);
  }
  const label = document.createElement("span");
  label.dataset.imageRefLabel = "";
  label.textContent = chip.dataset.imageRefText;
  const remove = document.createElement("button");
  remove.type = "button";
  remove.className = "gallery-chip-remove";
  remove.setAttribute("data-remove-gallery-chip", "");
  remove.setAttribute("aria-label", translate("promptMention.remove"));
  remove.title = translate("promptMention.remove");
  remove.textContent = "×";
  chip.title = source ? source.name || source.filename || "" : translate("promptMention.missing");
  chip.classList.toggle("image-mention-missing", !source || Boolean(source.missing));
  chip.append(label, remove);
  chip.addEventListener("keydown", event => {
    if (event.key === "Backspace" || event.key === "Delete") {
      event.preventDefault();
      event.stopPropagation();
      methods.removePromptGalleryChip!(chip);
    }
  });
  return chip;
}

export function captureImageMentions(): ImageMentionContext | null {
  const { els, state, methods } = getLegacyBridge();
  if (!els.promptEditor) return null;
  const mentions: Exclude<ImageMentionPart, string>[] = [];
  let marker = "\u0000image-mention:";
  while (methods.getPromptText!().includes(marker)) marker += ":";
  const marked = methods.promptTextFromNode!(els.promptEditor, (chip: HTMLElement) => {
    const key = chip.dataset.imageRefKey;
    const stored = chip.dataset.imageRefSource ? JSON.parse(chip.dataset.imageRefSource) : null;
    const source = !stored?.missing && state.images.find((item: any) => key ? imageReferenceKey(item) === key
      : item.kind === "gallery" && item.id === chip.dataset.galleryId);
    const pointer = source ? sourcePointer(source) : stored || { kind: "gallery", id: chip.dataset.galleryId };
    const text = (chip.dataset.imageRefText || `@${chip.dataset.galleryName}`).replace(/\u00a0/g, " ").replace(/\r\n?/g, "\n");
    mentions.push({ text, source: pointer });
    return `${marker}${mentions.length - 1}\u0000`;
  }).replace(/\u00a0/g, " ").replace(/\r\n?/g, "\n").trim();
  if (!mentions.length) return null;
  const parts: ImageMentionPart[] = [];
  let cursor = 0;
  for (let index = 0; index < mentions.length; index++) {
    const token = `${marker}${index}\u0000`;
    const position = marked.indexOf(token, cursor);
    if (position > cursor) parts.push(marked.slice(cursor, position));
    parts.push(mentions[index]!);
    cursor = position + token.length;
  }
  if (cursor < marked.length) parts.push(marked.slice(cursor));
  return { version: 1, parts };
}

export function imageMentionPayload(): any {
  const context = captureImageMentions();
  if (!context) return null;
  const { state, methods } = getLegacyBridge();
  const uploads = state.images.filter((source: any) => source.kind === "upload");
  const parts = context.parts.map(part => {
    if (typeof part === "string") return part;
    const source = findSource(part.source, state.images);
    return { ...part, source: source?.kind === "upload"
      ? { kind: "upload", index: uploads.indexOf(source) }
      : source ? { kind: source.kind, id: source.id } : { ...part.source, missing: true } };
  });
  return { version: 1, template: formatTranslation("promptMention.reference", { number: "{number}" }), parts,
    model_parts: parts.map(part => typeof part === "string" ? methods.expandPromptSnippets!(part) : part) };
}

export function imageMentionsValid(): boolean {
  const { state } = getLegacyBridge();
  return (captureImageMentions()?.parts || []).every(part => typeof part === "string"
    || Boolean(findSource(part.source, state.images) && !findSource(part.source, state.images).missing));
}

export function restoreImageMentions(context: ImageMentionContext, sources: any[], appendText: (text: string) => void): void {
  const { els } = getLegacyBridge();
  for (const part of context.parts) {
    if (typeof part === "string") appendText(part);
    else els.promptEditor.append(createImageMentionChip(findSource(part.source, sources), part));
  }
}

export function refreshImageMentionChips(removeMissing = false): void {
  const { els, state, methods } = getLegacyBridge();
  els.promptEditor?.querySelectorAll(".image-mention-chip").forEach((chip: HTMLElement) => {
    if (chip.dataset.imageRefSource && JSON.parse(chip.dataset.imageRefSource).missing) {
      return;
    }
    const source = state.images.find((item: any) => imageReferenceKey(item) === chip.dataset.imageRefKey);
    if (!source) { if (removeMissing) chip.remove(); return; }
    const text = `@${imageMentionLabel(source)}`;
    chip.dataset.imageRefText = text;
    chip.dataset.imageRefSource = JSON.stringify(sourcePointer(source));
    chip.querySelector("[data-image-ref-label]")!.textContent = text;
    chip.classList.toggle("image-mention-missing", Boolean(source.missing));
  });
  methods.syncPromptFromEditor?.();
  methods.updatePromptCount?.();
}

export function rebindEditedImageMentions(previous: any, next: any): void {
  const { els } = getLegacyBridge();
  const previousKey = imageReferenceKey(previous);
  // A stored image can be added again after editing; the edited upload is distinct.
  next.prompt_ref_key = previous.kind === "upload" ? previousKey : undefined;
  els.promptEditor?.querySelectorAll(".gallery-chip").forEach((chip: HTMLElement) => {
    if (chip.dataset.imageRefKey === previousKey
      || (previous.kind === "gallery" && chip.dataset.galleryId === previous.id)) {
      chip.replaceWith(createImageMentionChip(next));
    }
  });
}

export function imageMentionTemplateText(): string {
  const context = captureImageMentions();
  return context ? context.parts.map(part => typeof part === "string" ? part
    : part.source.kind === "gallery" ? part.text : `{{${part.text.replace(/^@/, "")}}}`).join("")
    : getLegacyBridge().methods.getPromptText!();
}

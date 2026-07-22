import { getLegacyBridge } from "./state";
import { formatTranslation, translate } from "./i18n";

const bridge = getLegacyBridge();
const els = bridge.els;

function legacyMethod(name: string, ...args: any[]): any {
  const method = getLegacyBridge().methods[name];
  if (typeof method !== "function") {
    throw new Error("Legacy method " + name + " is not initialized");
  }
  return method(...args);
}

function getPromptText(): string { return legacyMethod("getPromptText"); }
function expandPromptSnippets(prompt: any): string { return legacyMethod("expandPromptSnippets", prompt); }
function galleryInputs(): any[] { return legacyMethod("galleryInputs"); }
function uploadInputs(): any[] { return legacyMethod("uploadInputs"); }
function referenceAssetInputs(): any[] { return legacyMethod("referenceAssetInputs"); }
function categoryPromptRole(category: any): string { return legacyMethod("categoryPromptRole", category); }
export function promptTokenReplacement(prompt: any): string {
  return expandPromptSnippets(prompt);
}

export function galleryPromptText(galleries: any[] = galleryInputs()): string {
  if (!galleries.length) return "";
  const referenceOffset = uploadInputs().length + referenceAssetInputs().length;
  const lines = galleries.map((source: any, index: any) => galleryReferenceInstruction(source, referenceOffset + index + 1));
  return `${translate("promptModel.galleryHeader")}\n${lines.join("\n")}`;
}

export function buildPromptForModel(): string {
  const prompt = expandPromptSnippets(getPromptText());
  const galleries = galleryInputs();
  const galleryText = galleryPromptText(galleries);
  if (!galleryText) return prompt;
  return `${prompt}\n\n${galleryText}`;
}

export function galleryReferenceInstruction(source: any, number: any): string {
  const role = source.category_prompt_role || categoryPromptRole(source.category);
  const promptNote = String(source.prompt_note || "").trim();
  return formatTranslation("promptModel.galleryInstruction", {
    number,
    name: source.name,
    role,
    note: promptNote ? ` ${promptNote}` : "",
  });
}

export function currentPromptForModel(): string {
  if (!supportsGptPromptProcessing()) return buildPromptForModel();
  return currentPromptFidelity() === "original" ? expandPromptSnippets(getPromptText()) : buildPromptForModel();
}

export function currentPromptFidelity(): string {
  if (!supportsGptPromptProcessing()) return "off";
  const value = els.promptFidelity?.value || "strict";
  return ["strict", "original", "off"].includes(value) ? value : "strict";
}

export function supportsGptPromptProcessing(): boolean {
  const { state } = getLegacyBridge();
  return !state.generationCatalog || state.selectedModelId === "gpt-image-2";
}

export function initPromptModelFeature(): void {
  Object.assign(getLegacyBridge().methods, {
    promptTokenReplacement,
    galleryPromptText,
    buildPromptForModel,
    galleryReferenceInstruction,
    currentPromptForModel,
    currentPromptFidelity,
    supportsGptPromptProcessing,
  });
}

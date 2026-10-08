import { isGptImageModel } from "./gpt-image-models";
import { getLegacyBridge } from "./state";
import { translate } from "./i18n";

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
function categoryPromptRole(category: any): string { return legacyMethod("categoryPromptRole", category); }
export function promptTokenReplacement(prompt: any): string {
  return expandPromptSnippets(prompt);
}

export function galleryPrompt() {
  const galleries = galleryInputs();
  if (!galleries.length || currentPromptFidelity() === "original") return null;
  return {
    header: translate("promptModel.galleryHeader"),
    template: translate("promptModel.galleryInstruction"),
    references: galleries.map((source: any) => {
      const promptNote = String(source.prompt_note || "").trim();
      return {
        id: source.id,
        name: source.name,
        role: source.category_prompt_role || categoryPromptRole(source.category),
        note: promptNote ? ` ${promptNote}` : "",
      };
    }),
  };
}

export function buildPromptForModel(): string {
  // Gallery guidance stays structured until the server resolves duplicate image identities.
  return expandPromptSnippets(getPromptText());
}

export function currentPromptForModel(): string {
  return buildPromptForModel();
}

export function currentPromptFidelity(): string {
  if (!supportsGptPromptProcessing()) return "off";
  const value = els.promptFidelity?.value || "off";
  return ["strict", "original", "off"].includes(value) ? value : "off";
}

export function supportsGptPromptProcessing(): boolean {
  const { state } = getLegacyBridge();
  return !state.generationCatalog || isGptImageModel(state.selectedModelId);
}

export function initPromptModelFeature(): void {
  Object.assign(getLegacyBridge().methods, {
    promptTokenReplacement,
    galleryPrompt,
    buildPromptForModel,
    currentPromptForModel,
    currentPromptFidelity,
    supportsGptPromptProcessing,
  });
}

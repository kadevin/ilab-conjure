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

function rangeIntersectsNode(range: any, node: any): boolean { return legacyMethod("rangeIntersectsNode", range, node); }
function createPromptTextFragment(text: any): { fragment: DocumentFragment; lastNode: Node | null } {
  return legacyMethod("createPromptTextFragment", text);
}
function setCaretAfterNode(node: any): void { legacyMethod("setCaretAfterNode", node); }
function syncPromptAfterChipMutation(): void { legacyMethod("syncPromptAfterChipMutation"); }
function updateMentionSuggest(): void { legacyMethod("updateMentionSuggest"); }
function updateColorSuggest(): void { legacyMethod("updateColorSuggest"); }
function updatePromptSnippetSuggest(): void { legacyMethod("updatePromptSnippetSuggest"); }

function clipboardHasImageFile(data: DataTransfer): boolean {
  return Array.from(data.items || []).some((item) => item.kind === "file" && item.type?.startsWith("image/"));
}

export function promptPlainTextFromHtml(html: any): string {
  // Template contents are inert: parsing must neither run handlers nor fetch
  // resources. Never insert this fragment into the live document.
  const container = document.createElement("template");
  container.innerHTML = String(html || "");
  return normalizePromptPasteText(promptPlainTextFromHtmlNode(container.content));
}

function promptPlainTextFromHtmlNode(node: any): string {
  let text = "";
  node.childNodes.forEach((child: any) => {
    if (child.nodeType === Node.TEXT_NODE) {
      text += child.textContent || "";
      return;
    }
    if (child.nodeType !== Node.ELEMENT_NODE) return;
    const tagName = child.tagName;
    if (["SCRIPT", "STYLE", "NOSCRIPT"].includes(tagName)) return;
    if (tagName === "BR") {
      text += "\n";
      return;
    }
    const isBlock = ["ADDRESS", "ARTICLE", "ASIDE", "BLOCKQUOTE", "DD", "DIV", "DL", "DT", "FIGCAPTION", "FIGURE", "FOOTER", "H1", "H2", "H3", "H4", "H5", "H6", "HEADER", "HR", "LI", "MAIN", "NAV", "OL", "P", "PRE", "SECTION", "TABLE", "TR", "UL"].includes(tagName);
    if (isBlock && text && !text.endsWith("\n")) text += "\n";
    text += promptPlainTextFromHtmlNode(child);
    if (isBlock && text && !text.endsWith("\n")) text += "\n";
  });
  return text;
}

function normalizePromptPasteText(text: any): string {
  return String(text || "")
    .replace(/\r\n?/g, "\n")
    .replace(/\u00a0/g, " ")
    .replace(/[ \t]+\n/g, "\n")
    .replace(/\n[ \t]+/g, "\n")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
}

export function promptPasteTextFromClipboard(data: DataTransfer): string {
  const plain = data.getData("text/plain");
  if (plain) return normalizePromptPasteText(plain);
  const html = data.getData("text/html");
  return html ? promptPlainTextFromHtml(html) : "";
}

export function insertPlainPromptText(text: any): void {
  if (!els.promptEditor) return;
  const normalized = normalizePromptPasteText(text);
  if (!normalized) return;
  els.promptEditor.focus();
  const { fragment, lastNode } = createPromptTextFragment(normalized);
  if (!lastNode) return;
  const selection = window.getSelection();
  if (!selection || !selection.rangeCount) {
    els.promptEditor.append(fragment);
    setCaretAfterNode(lastNode);
    return;
  }
  const range = selection.getRangeAt(0);
  if (!rangeIntersectsNode(range, els.promptEditor)) {
    els.promptEditor.append(fragment);
    setCaretAfterNode(lastNode);
    return;
  }
  range.deleteContents();
  range.insertNode(fragment);
  setCaretAfterNode(lastNode);
}

export function handlePromptEditorPaste(event: any): void {
  if (!event.clipboardData || !els.promptEditor?.contains(event.target)) return;
  if (clipboardHasImageFile(event.clipboardData)) return;
  const text = promptPasteTextFromClipboard(event.clipboardData);
  if (!text) return;
  event.preventDefault();
  insertPlainPromptText(text);
  syncPromptAfterChipMutation();
  updateMentionSuggest();
  updateColorSuggest();
  updatePromptSnippetSuggest();
}

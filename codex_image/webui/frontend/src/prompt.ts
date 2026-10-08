import { getLegacyBridge } from "./state";
import {
  appendPromptText,
  clearPromptEditorIfEmpty,
  getPromptText,
  initPromptSerializationFeature,
  promptSelectionText,
  promptTextFromNode,
  promptTextFromRange,
  rangeIntersectsNode,
  selectPromptEditorContents,
  setPromptText,
  setPromptWithGalleryRefs,
} from "./prompt-serialization";
import {
  activeMentionMatch,
  createGalleryChip,
  currentPromptGalleryIds,
  ensurePromptGalleryMention,
  findGalleryRefMentionAt,
  galleryRefsByMentionLength,
  hideMentionSuggest,
  imageSourcesKey,
  initPromptGalleryChipsFeature,
  insertGalleryMention,
  positionMentionSuggestAtCaret,
  removePromptGalleryChip,
  syncGalleryInputsFromPrompt,
  syncPromptGalleryMentionsFromInputs,
  updateMentionSuggest,
} from "./prompt-gallery-chips";
import {
  bindPromptEditorEvents,
  clearPromptChipDropClasses,
  ensurePromptChipLeadingBoundary,
  ensurePromptChipTrailingBoundary,
  handlePromptChipDragEnd,
  handlePromptChipDragOver,
  handlePromptChipDragStart,
  handlePromptChipDrop,
  handlePromptEditorClick,
  handlePromptEditorCopy,
  handlePromptEditorDrop,
  handlePromptEditorKeydown,
  initPromptEditorEventsFeature,
  isPromptAtomicChip,
  mentionRangeRect,
  normalizePromptChipBoundaries,
  promptChipAtCaretForDeletion,
  promptChipFallbackForDeletion,
  promptChipFromEvent,
  promptDropPlacement,
  promptDropTargetChip,
  promptEditorFocusInside,
  promptRangeFromPoint,
  setCaretAfterNode,
  setCaretToEnd,
  syncPromptAfterChipMutation,
  syncPromptFromEditor,
  updatePromptChipSelectionState,
} from "./prompt-editor-events";
import {
  buildPromptForModel,
  currentPromptFidelity,
  currentPromptForModel,
  galleryPrompt,
  initPromptModelFeature,
  promptTokenReplacement,
} from "./prompt-model";

const bridge = getLegacyBridge();
const els = bridge.els;

let promptFeatureInitialized = false;

function legacyMethod(name: string, ...args: any[]): any {
  const method = getLegacyBridge().methods[name];
  if (typeof method !== "function") {
    throw new Error("Legacy method " + name + " is not initialized");
  }
  return method(...args);
}

function closePromptColorSuggest(): void { legacyMethod("hideColorSuggest"); }
function handlePromptSnippetDocumentClick(target: any): void { legacyMethod("handlePromptSnippetDocumentClick", target); }

function handlePromptDocumentClick(event: any): void {
  const target = event.target;
  if (els.colorSuggest && !els.colorSuggest.classList.contains("hidden")) {
    const clickedColorSuggest = els.colorSuggest.contains(target);
    const clickedPromptEditor = els.promptEditor?.contains(target);
    if (!clickedColorSuggest && !clickedPromptEditor) {
      closePromptColorSuggest();
    }
  }
  handlePromptSnippetDocumentClick(target);
}

export function initPromptFeature(): void {
  if (promptFeatureInitialized) return;
  promptFeatureInitialized = true;
  initPromptSerializationFeature();
  initPromptGalleryChipsFeature();
  initPromptEditorEventsFeature();
  initPromptModelFeature();
  Object.assign(getLegacyBridge().methods, {
    handlePromptDocumentClick,
  });
  bindPromptEditorEvents();
}

void appendPromptText;
void buildPromptForModel;
void clearPromptChipDropClasses;
void clearPromptEditorIfEmpty;
void createGalleryChip;
void currentPromptFidelity;
void currentPromptForModel;
void currentPromptGalleryIds;
void ensurePromptChipLeadingBoundary;
void ensurePromptChipTrailingBoundary;
void ensurePromptGalleryMention;
void findGalleryRefMentionAt;
void galleryPrompt;
void galleryRefsByMentionLength;
void getPromptText;
void handlePromptChipDragEnd;
void handlePromptChipDragOver;
void handlePromptChipDragStart;
void handlePromptChipDrop;
void handlePromptEditorClick;
void handlePromptEditorCopy;
void handlePromptEditorDrop;
void handlePromptEditorKeydown;
void hideMentionSuggest;
void imageSourcesKey;
void insertGalleryMention;
void isPromptAtomicChip;
void mentionRangeRect;
void normalizePromptChipBoundaries;
void positionMentionSuggestAtCaret;
void promptChipAtCaretForDeletion;
void promptChipFallbackForDeletion;
void promptChipFromEvent;
void promptDropPlacement;
void promptDropTargetChip;
void promptEditorFocusInside;
void promptRangeFromPoint;
void promptSelectionText;
void promptTextFromNode;
void promptTextFromRange;
void promptTokenReplacement;
void rangeIntersectsNode;
void removePromptGalleryChip;
void selectPromptEditorContents;
void setCaretAfterNode;
void setCaretToEnd;
void setPromptText;
void setPromptWithGalleryRefs;
void syncGalleryInputsFromPrompt;
void syncPromptAfterChipMutation;
void syncPromptFromEditor;
void syncPromptGalleryMentionsFromInputs;
void updateMentionSuggest;
void updatePromptChipSelectionState;
void activeMentionMatch;

// Run after app.js in an isolated WebUI with synthetic data. No generation calls.
import { captureImageMentions, createImageMentionChip, imageMentionPayload, imageMentionsValid,
  refreshImageMentionChips, rebindEditedImageMentions, imageMentionTemplateText } from "../../codex_image/webui/frontend/src/prompt-image-mentions";
import { preserveComposerDraft, restoreComposerDraft } from "../../codex_image/webui/frontend/src/composer-draft";
import { handleImageMentionKey } from "../../codex_image/webui/frontend/src/prompt-mention-menu";

async function run() {
  const bridge = window.__codexImageWebUI;
  const { state, methods, els } = bridge;
  const results: { name: string; passed: boolean; error?: string }[] = [];
  const check = (condition: unknown, message: string) => { if (!condition) throw new Error(message); };
  const test = (name: string, action: () => void) => {
    try { action(); results.push({ name, passed: true }); }
    catch (error) { results.push({ name, passed: false, error: String(error) }); }
  };
  const canvas = document.createElement("canvas"); canvas.width = 16; canvas.height = 16;
  canvas.getContext("2d")!.fillRect(0, 0, 16, 16);
  const blob = await new Promise<Blob>(resolve => canvas.toBlob(value => resolve(value!)));
  const makeUpload = () => methods.uploadSource!(new File([blob], "same.png", { type: "image/png" }));
  const a = makeUpload(), b = makeUpload();
  const gallery = { id: "fixture-gallery", name: "same.png", kind: "gallery", category: "portrait", image_url: canvas.toDataURL() };
  const reset = () => { state.images = [a, b]; state.galleryItems = [gallery]; methods.setPromptText!(""); };
  const add = (source: any) => { els.promptEditor.append(createImageMentionChip(source)); methods.appendPromptText!(" "); methods.syncPromptFromEditor!(); };
  reset();
  test("same-name uploads have distinct identities and repeated mentions do not attach images", () => {
    add(a); add(b); add(a);
    const refs = imageMentionPayload().parts.filter((part: any) => typeof part !== "string");
    check(refs.map((part: any) => part.source.index).join() === "0,1,0", "Wrong upload indices");
    check(state.images.length === 2, "Repeated mention added image");
  });
  test("reordering changes labels and transport indices, not target identity", () => {
    state.images = [b, a]; refreshImageMentionChips();
    const refs = imageMentionPayload().parts.filter((part: any) => typeof part !== "string");
    check(refs.map((part: any) => part.source.index).join() === "1,0,1", "Reference changed identity");
    check(methods.getPromptText().includes("@图2"), "Label not refreshed");
  });
  test("removing one upload mention retains all selected images", () => {
    methods.removePromptGalleryChip!(els.promptEditor.querySelector(".gallery-chip"));
    check(state.images.length === 2 && els.promptEditor.querySelectorAll(".gallery-chip").length === 2, "Unexpected attachment removal");
  });
  test("draft removal and restore recover text, references, blobs and other inputs together", () => {
    preserveComposerDraft(true);
    const before = methods.getPromptText();
    state.images = []; methods.syncPromptGalleryMentionsFromInputs!();
    check(!els.promptEditor.querySelector(".gallery-chip"), "Removed image left a live mention");
    restoreComposerDraft();
    check(state.images.length === 2 && methods.getPromptText() === before && imageMentionsValid(), "Draft lost references");
  });
  test("structured history restores same-name gallery and upload without matching by label", () => {
    const sources = [{ ...a, kind: "asset", id: "asset-fixture", prompt_ref_key: undefined }, gallery];
    const parts = [{ text: "@same.png", source: { kind: "asset", id: "asset-fixture" } }, " and ",
      { text: "@same.png", source: { kind: "gallery", id: gallery.id } }];
    state.images = sources;
    methods.setPromptWithGalleryRefs!("@same.png and @same.png", [gallery], { version: 1, parts }, sources);
    check(imageMentionPayload().parts.filter((part: any) => typeof part !== "string").map((part: any) => part.source.kind).join() === "asset,gallery", "History rebound same-name images");
  });
  test("gallery chip deletion preserves existing linkage", () => {
    methods.removePromptGalleryChip!(els.promptEditor.querySelector("[data-gallery-id]"));
    check(state.images.length === 1 && state.images[0].kind === "asset", "Gallery not detached or upload removed");
  });
  test("editing an image preserves references while changing to a local upload", () => {
    const previous = state.images[0]; const next = makeUpload();
    state.images[0] = next; rebindEditedImageMentions(previous, next); refreshImageMentionChips();
    check(imageMentionPayload().parts.some((part: any) => part.source?.kind === "upload" && part.source.index === 0), "Edit broke reference");
  });
  test("missing history assets stay unresolved and block submission", () => {
    const part = { text: "@图1", source: { kind: "asset", id: "missing" } };
    methods.setPromptWithGalleryRefs!("@图1", [], { version: 1, parts: [part] }, []);
    check(!imageMentionsValid() && Boolean(els.promptEditor.querySelector(".image-mention-missing")), "Missing reference silently rebound");
  });
  test("plain pasted or template @ text does not become a live image reference", () => {
    methods.setPromptText!("plain @图1 @same.png");
    check(captureImageMentions() === null, "Plain text became a live reference");
  });
  test("upload references become template placeholders", () => {
    reset(); add(a);
    check(imageMentionTemplateText().includes("{{图1}}"), "Template binds another task's image");
  });
  test("menu groups current references and gallery and keyboard selects second upload", () => {
    reset(); methods.setPromptText!("@"); methods.setCaretToEnd!(els.promptEditor); methods.updateMentionSuggest!();
    check(els.mentionSuggest.querySelectorAll(".mention-group-label").length === 2, "Missing groups");
    els.promptEditor.dispatchEvent(new KeyboardEvent("keydown", { key: "ArrowDown", bubbles: true, cancelable: true }));
    els.promptEditor.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true, cancelable: true }));
    check(imageMentionPayload().parts[0].source.index === 1, "Keyboard selected wrong image");
    check(els.mentionSuggest.classList.contains("hidden"), "Menu stayed open");
  });
  test("IME confirmation does not insert the first candidate", () => {
    methods.setPromptText!("@"); methods.setCaretToEnd!(els.promptEditor); methods.updateMentionSuggest!();
    els.promptEditor.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", isComposing: true, bubbles: true, cancelable: true }));
    check(captureImageMentions() === null, "IME confirmation inserted an image");
  });
  test("selected gallery appears once and repeated mentions keep it attached", () => {
    reset(); state.images.push(gallery); methods.setPromptText!("@"); methods.setCaretToEnd!(els.promptEditor); methods.updateMentionSuggest!();
    check(els.mentionSuggest.querySelectorAll("[data-image-mention-index]").length === 3, "Selected gallery duplicated");
    methods.setPromptText!(""); add(gallery); add(gallery);
    methods.removePromptGalleryChip!(els.promptEditor.querySelector("[data-gallery-id]"));
    check(state.images.some((source: any) => source.id === gallery.id), "One remaining mention lost image");
  });
  test("editing a gallery image then adding its original does not collide", () => {
    state.images = [gallery]; methods.setPromptText!(""); add(gallery);
    const edited = makeUpload(); state.images = [edited]; rebindEditedImageMentions(gallery, edited);
    state.images.push(gallery); add(gallery);
    const parts = imageMentionPayload().parts.filter((part: any) => typeof part !== "string");
    check(parts.map((part: any) => part.source.kind).join() === "upload,gallery", "Edited image captured original identity");
  });
  test("unresolved backup identity stays missing even when an unrelated ID exists", () => {
    state.images = [gallery];
    const part = { text: "@same.png", source: { kind: "gallery", id: gallery.id, missing: true } };
    methods.setPromptWithGalleryRefs!(part.text, [gallery], { version: 1, parts: [part] }, [gallery]);
    refreshImageMentionChips();
    check(!imageMentionsValid() && imageMentionPayload().parts[0].source.missing, "Missing identity rebound");
    state.images = []; methods.syncPromptGalleryMentionsFromInputs!();
    check(Boolean(els.promptEditor.querySelector(".image-mention-missing")) && !imageMentionsValid(), "Unrelated removal silently erased missing reference");
  });
  test("filename spaces and dots are searchable while email and other triggers close mentions", () => {
    reset(); const named = { ...a, name: "product front.png" }; state.images = [named];
    methods.setPromptText!("Use @product front.p"); methods.setCaretToEnd!(els.promptEditor); methods.updateMentionSuggest!();
    check(els.mentionSuggest.querySelectorAll("[data-image-mention-index]").length === 1, "Filename search failed");
    for (const text of ["user@example.com", "@ #ffffff", "@ ~snippet"]) {
      methods.setPromptText!(text); methods.setCaretToEnd!(els.promptEditor); methods.updateMentionSuggest!();
      check(els.mentionSuggest.classList.contains("hidden"), `Unexpected mention menu: ${text}`);
    }
  });
  test("empty candidate list leaves Enter available to the editor", () => {
    reset(); methods.setPromptText!("@nothing-matches"); methods.setCaretToEnd!(els.promptEditor); methods.updateMentionSuggest!();
    const event = new KeyboardEvent("keydown", { key: "Enter", cancelable: true });
    check(!handleImageMentionKey(event) && !event.defaultPrevented, "Empty list swallowed Enter");
  });
  test("gallery labels with nonbreaking spaces match the visible submitted text", () => {
    const spaced = { ...gallery, name: "two\u00a0words" }; state.images = [spaced]; methods.setPromptText!(""); add(spaced);
    const text = imageMentionPayload().parts.map((part: any) => typeof part === "string" ? part : part.text).join("");
    check(text === methods.getPromptText(), "Mention serialization changed whitespace");
  });
  test("structured restoration retains color and snippet chips around image references", () => {
    reset();
    state.promptSnippets = [{ id: "qa-snippet", tag: "qatest", content: "a soft studio light" }];
    const parts = ["#ff0000 ~qatest ", { text: "@same.png", source: { kind: "gallery", id: gallery.id } }];
    state.images = [gallery];
    methods.setPromptWithGalleryRefs!("#ff0000 ~qatest @same.png", [gallery], { version: 1, parts }, [gallery]);
    check(Boolean(els.promptEditor.querySelector(".color-chip")), "Color chip lost");
    check(Boolean(els.promptEditor.querySelector(".prompt-snippet-chip")), "Snippet chip lost");
    check(imageMentionPayload().model_parts.some((part: any) => typeof part === "string" && part.includes("a soft studio light")), "Snippet not expanded");
  });
  test("deleting a focused chip removes only that chip and keeps uploads", () => {
    reset(); add(a); add(b);
    const chip = els.promptEditor.querySelector(".image-mention-chip") as HTMLElement;
    chip.focus(); chip.dispatchEvent(new KeyboardEvent("keydown", { key: "Delete", bubbles: true, cancelable: true }));
    check(els.promptEditor.querySelectorAll(".image-mention-chip").length === 1 && state.images.length === 2, "Focused delete removed other input");
    state.images.push(gallery); add(gallery); add(gallery);
    const galleryChip = els.promptEditor.querySelector("[data-gallery-id]") as HTMLElement;
    galleryChip.focus(); galleryChip.dispatchEvent(new KeyboardEvent("keydown", { key: "Backspace", bubbles: true, cancelable: true }));
    check(els.promptEditor.querySelectorAll("[data-gallery-id]").length === 1 && state.images.length === 3, "Focused gallery delete bubbled to another chip");
  });
  methods.hideMentionSuggest!();
  const report = document.createElement("pre"); report.id = "image-mention-test-results";
  report.textContent = JSON.stringify({ passed: results.every(result => result.passed), results }); document.body.append(report);
}
void run().catch(error => { const report = document.createElement("pre"); report.id = "image-mention-test-results"; report.textContent = JSON.stringify({ passed: false, fatal: String(error) }); document.body.append(report); });

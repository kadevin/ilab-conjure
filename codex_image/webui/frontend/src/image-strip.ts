import { getEls } from "./dom";
import { getLegacyBridge, getState } from "./state";
import { formatTranslation, LOCALE_CHANGE_EVENT, translate } from "./i18n";
import { uploadThumbnailUrl } from "./upload-thumbnails";

let imageStripFeatureInitialized = false;

function legacyMethod(name: string, ...args: any[]) {
  return getLegacyBridge().methods[name]?.(...args);
}

function addImages(event: any) {
  legacyMethod("addMixedInputFiles", event.target.files || []);
  event.target.value = "";
}

function clearImages() {
  const state = getState();
  legacyMethod("revokeUploadPreviewUrls", state.images);
  state.images = [];
  legacyMethod("clearReferenceFiles", { silent: true });
  legacyMethod("syncPromptGalleryMentionsFromInputs");
  legacyMethod("setMode", "generate");
  renderImageStrip();
  legacyMethod("updateRequestPreview");
}

function createThumbAddIcon() {
  const icon = document.createElement("span");
  icon.className = "thumb-add-icon";
  icon.setAttribute("aria-hidden", "true");
  icon.innerHTML = '<svg viewBox="0 0 16 16" fill="none" focusable="false" xmlns="http://www.w3.org/2000/svg"><path d="M8 3.5v9M3.5 8h9" stroke="currentColor" stroke-linecap="round"/></svg>';
  return icon;
}

function createThumbRemoveIcon() {
  const icon = document.createElement("span");
  icon.className = "thumb-remove-icon";
  icon.setAttribute("aria-hidden", "true");
  icon.innerHTML = '<svg viewBox="0 0 16 16" fill="none" focusable="false" xmlns="http://www.w3.org/2000/svg"><path d="M4.5 4.5 11.5 11.5M11.5 4.5 4.5 11.5" stroke="currentColor" stroke-linecap="round" stroke-width="1.8"/></svg>';
  return icon;
}

function imageStripNeedsCompactGrid() {
  const state = getState();
  const els = getEls();
  const thumbCount = state.images.length + state.referenceFiles.length;
  if (!els.imageUploaderGrid || !thumbCount) return false;
  const availableWidth = Math.max(0, els.imageUploaderGrid.clientWidth - 24);
  if (!availableWidth) return false;
  const fullSizeThumbsWidth = thumbCount * 116 + Math.max(0, thumbCount - 1) * 10;
  const fullSizeUploadWidth = 118;
  const fullSizeUploadGap = 10;
  return fullSizeThumbsWidth + fullSizeUploadGap + fullSizeUploadWidth > availableWidth;
}

function updateImageStripDensity() {
  const state = getState();
  const els = getEls();
  const hasImages = Boolean(state.images.length);
  const hasInputs = Boolean(state.images.length + state.referenceFiles.length);
  const compactGrid = imageStripNeedsCompactGrid();
  els.imageUploaderGrid?.classList.toggle("has-images", hasImages);
  els.imageUploaderGrid?.classList.toggle("has-inputs", hasInputs);
  els.imageUploaderGrid?.classList.toggle("compact-grid", compactGrid);
}

function wheelDeltaInPixels(event: WheelEvent) {
  const dominantDelta = Math.abs(event.deltaX) > Math.abs(event.deltaY) ? event.deltaX : event.deltaY;
  if (event.deltaMode === WheelEvent.DOM_DELTA_LINE) return dominantDelta * 16;
  if (event.deltaMode === WheelEvent.DOM_DELTA_PAGE) {
    const els = getEls();
    return dominantDelta * Math.max(1, els.imageStrip?.clientWidth || 1);
  }
  return dominantDelta;
}

function handleImageStripWheel(event: WheelEvent) {
  const els = getEls();
  const scrollTarget = els.imageThumbList;
  if (!scrollTarget) return;
  const maxScrollLeft = Math.max(0, scrollTarget.scrollWidth - scrollTarget.clientWidth);
  if (!maxScrollLeft) return;
  const wheelDelta = wheelDeltaInPixels(event);
  if (!wheelDelta) return;
  const nextScrollLeft = Math.min(maxScrollLeft, Math.max(0, scrollTarget.scrollLeft + wheelDelta));
  if (nextScrollLeft === scrollTarget.scrollLeft) return;
  event.preventDefault();
  scrollTarget.scrollLeft = nextScrollLeft;
}

function renderImageStrip() {
  const state = getState();
  const els = getEls();
  const hasImages = Boolean(state.images.length);
  const thumbItems = els.imageThumbItems;
  updateImageStripDensity();
  if (!thumbItems) return;
  if (!hasImages) {
    thumbItems.innerHTML = "";
    legacyMethod("updateCustomRatioReferenceButtonState");
    return;
  }

  thumbItems.innerHTML = "";
  state.images.forEach((source: any, index: number) => {
    const wrapper = document.createElement("div");
    wrapper.className = `thumb ${source.kind === "gallery" ? "gallery-thumb" : source.kind === "asset" ? "asset-thumb" : "upload-thumb"}${source.missing ? " missing-thumb" : ""}`;
    const image = document.createElement("img");
    const isUploadedImage = source.kind === "upload" && source.file instanceof File;
    const preserveAnimation = isUploadedImage && (/^image\/gif$/i.test(source.file.type) || /\.gif$/i.test(source.file.name));
    const previewUrl = source.kind === "asset" && source.thumbnail_url
      ? source.thumbnail_url
      : isUploadedImage && !preserveAnimation
        ? source.thumbnail_url || ""
        : legacyMethod("sourcePreviewUrl", source);
    if (previewUrl) {
      image.src = previewUrl;
      if (source.kind === "asset" && source.thumbnail_url && source.image_url) {
        image.addEventListener("error", () => { image.src = source.image_url; }, { once: true });
      }
    } else if (isUploadedImage) {
      image.style.visibility = "hidden";
      void uploadThumbnailUrl(source.file).then((thumbnailUrl) => {
        source.thumbnail_url = thumbnailUrl;
        if (!image.isConnected || !state.images.includes(source)) return;
        image.src = thumbnailUrl;
        image.style.visibility = "";
      }).catch(() => {
        if (!image.isConnected || !state.images.includes(source)) return;
        image.src = source.previewUrl;
        image.style.visibility = "";
      });
    }
    image.alt = legacyMethod("sourceName", source);
    wrapper.title = source.missing
      ? (source.kind === "asset" ? translate("imageInput.deletedRecent") : translate("imageInput.deletedGallery"))
      : legacyMethod("sourceName", source);
    if (legacyMethod("isEditableImageSource", source)) {
      wrapper.classList.add("editable-thumb");
      wrapper.tabIndex = 0;
      wrapper.setAttribute("role", "button");
      wrapper.setAttribute("aria-label", formatTranslation("imageInput.editImage", { name: legacyMethod("sourceName", source) }));
      wrapper.addEventListener("click", (event: any) => {
        if (event.target.closest("button")) return;
        legacyMethod("openImageEditor", index);
      });
      wrapper.addEventListener("keydown", (event: KeyboardEvent) => {
        if ((event.target as Element | null)?.closest("button")) return;
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          legacyMethod("openImageEditor", index);
        }
      });
    }
    const badge = document.createElement("span");
    badge.className = "thumb-badge";
    badge.textContent = source.kind === "gallery"
      ? legacyMethod("categoryLabel", source.category)
      : source.kind === "asset"
        ? translate("imageInput.recentBadge")
        : translate("imageInput.uploadBadge");
    const remove = document.createElement("button");
    remove.type = "button";
    remove.className = "thumb-remove";
    remove.setAttribute("aria-label", translate("imageInput.removeImage"));
    remove.title = translate("imageInput.removeImage");
    remove.append(createThumbRemoveIcon());
    remove.addEventListener("click", (event) => {
      event.stopPropagation();
      const removedSource = state.images[index];
      legacyMethod("revokeUploadPreviewUrl", removedSource, { ignoredCurrentSources: new Set([removedSource]) });
      state.images.splice(index, 1);
      legacyMethod("syncPromptGalleryMentionsFromInputs");
      if (!state.images.length) {
        legacyMethod("setMode", "generate");
      }
      renderImageStrip();
      legacyMethod("updateRequestPreview");
    });
    wrapper.append(image, badge, remove);
    if (legacyMethod("canAddSourceToGallery", source)) {
      const addToGallery = document.createElement("button");
      addToGallery.type = "button";
      addToGallery.className = "add-upload-to-gallery";
      addToGallery.setAttribute("aria-label", translate("imageInput.addToGallery"));
      addToGallery.title = translate("imageInput.addToGallery");
      addToGallery.append(createThumbAddIcon(), document.createTextNode(translate("imageInput.addToGalleryShort")));
      addToGallery.addEventListener("click", (event) => {
        event.stopPropagation();
        legacyMethod("openAddToGallery", index);
      });
      wrapper.append(addToGallery);
    }
    if (source.edited) {
      const editedBadge = document.createElement("span");
      editedBadge.className = "thumb-edited-badge";
      editedBadge.textContent = translate("imageInput.editedBadge");
      wrapper.append(editedBadge);
    }
    thumbItems.append(wrapper);
  });
  legacyMethod("updateCustomRatioReferenceButtonState");
}

function bindImageStripEvents() {
  const els = getEls();
  els.imageInput?.addEventListener("change", addImages);
  els.clearImagesButton?.addEventListener("click", clearImages);
  els.imageStrip?.addEventListener("wheel", handleImageStripWheel, { passive: false });
  window.addEventListener("resize", updateImageStripDensity);
  document.addEventListener(LOCALE_CHANGE_EVENT, renderImageStrip);
}

export function initImageStripFeature() {
  if (imageStripFeatureInitialized) return;
  imageStripFeatureInitialized = true;
  bindImageStripEvents();
  Object.assign(getLegacyBridge().methods, {
    addImages,
    clearImages,
    updateImageStripDensity,
    handleImageStripWheel,
    renderImageStrip,
  });
}

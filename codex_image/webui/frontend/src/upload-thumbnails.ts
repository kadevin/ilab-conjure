const MAX_PREVIEW_EDGE = 256;
const previewByFile = new WeakMap<File, Promise<string>>();
let previousPreview: Promise<unknown> = Promise.resolve();

async function createUploadThumbnail(file: File): Promise<string> {
  let bitmap: ImageBitmap | null = null;
  let image: HTMLImageElement | null = null;
  let imageUrl = "";
  try {
    if (typeof createImageBitmap === "function") {
      try {
        bitmap = await createImageBitmap(file, {
          resizeWidth: MAX_PREVIEW_EDGE,
          resizeQuality: "high",
        });
      } catch (_) {
        // Some WebViews can display a format in <img> but cannot create an ImageBitmap from it.
      }
    }
    if (!bitmap) {
      imageUrl = URL.createObjectURL(file);
      image = new Image();
      image.decoding = "async";
      image.src = imageUrl;
      await image.decode();
    }
    const source = bitmap || image;
    if (!source) throw new Error("Image preview unavailable");
    const sourceWidth = bitmap?.width || image?.naturalWidth || 0;
    const sourceHeight = bitmap?.height || image?.naturalHeight || 0;
    if (!sourceWidth || !sourceHeight) throw new Error("Image preview has no dimensions");
    const scale = Math.min(1, MAX_PREVIEW_EDGE / Math.max(sourceWidth, sourceHeight));
    const canvas = document.createElement("canvas");
    canvas.width = Math.max(1, Math.round(sourceWidth * scale));
    canvas.height = Math.max(1, Math.round(sourceHeight * scale));
    const context = canvas.getContext("2d");
    if (!context) throw new Error("Image preview canvas unavailable");
    context.drawImage(source, 0, 0, canvas.width, canvas.height);
    return canvas.toDataURL("image/webp", 0.82);
  } finally {
    bitmap?.close();
    if (imageUrl) URL.revokeObjectURL(imageUrl);
  }
}

export function uploadThumbnailUrl(file: File): Promise<string> {
  const existing = previewByFile.get(file);
  if (existing) return existing;
  const pending = previousPreview.then(() => createUploadThumbnail(file));
  previousPreview = pending.then(() => undefined, () => undefined);
  previewByFile.set(file, pending);
  return pending;
}

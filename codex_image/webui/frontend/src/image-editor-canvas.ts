import { translate } from "./i18n";
import type { ImageEditorLayer } from "./image-editor-types";

const IMAGE_EDITOR_MAX_EXPORT_EDGE = 4096;
const IMAGE_EDITOR_LAYER_THUMB_SIZE = 96;
const pixelSnapshots = new WeakMap<HTMLCanvasElement, HTMLCanvasElement>();

export function markImageEditorCanvasChanged(canvas: HTMLCanvasElement) {
  pixelSnapshots.delete(canvas);
}

export function rememberImageEditorCanvasSnapshot(canvas: HTMLCanvasElement, snapshot: HTMLCanvasElement) {
  pixelSnapshots.set(canvas, snapshot);
}

/** Immutable pixel versions are shared by geometry-only history entries. */
export function captureImageEditorCanvas(canvas: HTMLCanvasElement): HTMLCanvasElement {
  const previous = pixelSnapshots.get(canvas);
  if (previous && previous.width === canvas.width && previous.height === canvas.height && previous.width > 0) return previous;
  const snapshot = imageEditorCanvasSnapshot(canvas);
  if (!snapshot) throw new Error(translate("imageEditor.canvasCreateFailed"));
  pixelSnapshots.set(canvas, snapshot);
  return snapshot;
}

export function editedUploadFilename(name: any) {
  const sourceName = String(name || "input.png");
  const dotIndex = sourceName.lastIndexOf(".");
  const base = dotIndex > 0 ? sourceName.slice(0, dotIndex) : sourceName;
  return `${base}-edited.png`;
}

export function imageEditorCanvasSnapshot(canvas: any) {
  if (!canvas) return null;
  const snapshot = document.createElement("canvas");
  snapshot.width = canvas.width;
  snapshot.height = canvas.height;
  const ctx = snapshot.getContext("2d");
  if (!ctx) return null;
  ctx.drawImage(canvas, 0, 0);
  return snapshot;
}

export function imageEditorLayerAttrs(node: any) {
  return {
    x: node.x(),
    y: node.y(),
    width: node.width(),
    height: node.height(),
    scaleX: node.scaleX(),
    scaleY: node.scaleY(),
    rotation: node.rotation(),
    opacity: node.opacity(),
  };
}

export async function loadImageEditorImage(file: any) {
  const objectUrl = URL.createObjectURL(file);
  try {
    const image = new Image();
    image.decoding = "async";
    image.src = objectUrl;
    await image.decode();
    return image;
  } finally {
    URL.revokeObjectURL(objectUrl);
  }
}

export function imageEditorExportDimensions(image: any) {
  const width = image.naturalWidth || image.width;
  const height = image.naturalHeight || image.height;
  const longest = Math.max(width, height);
  if (longest <= IMAGE_EDITOR_MAX_EXPORT_EDGE) {
    return { width, height, scale: 1 };
  }
  const scale = IMAGE_EDITOR_MAX_EXPORT_EDGE / longest;
  return {
    width: Math.max(1, Math.round(width * scale)),
    height: Math.max(1, Math.round(height * scale)),
    scale,
  };
}

export function imageEditorCanvasFromImage(image: HTMLImageElement, dimensions = imageEditorExportDimensions(image)) {
  const canvas = document.createElement("canvas");
  canvas.width = dimensions.width;
  canvas.height = dimensions.height;
  const ctx = canvas.getContext("2d");
  if (!ctx) throw new Error(translate("imageEditor.canvasCreateFailed"));
  ctx.drawImage(image, 0, 0, dimensions.width, dimensions.height);
  return canvas;
}

export function imageEditorClampedCanvasDimensions(width: number, height: number) {
  return {
    width: Math.max(1, Math.min(IMAGE_EDITOR_MAX_EXPORT_EDGE, Math.round(width))),
    height: Math.max(1, Math.min(IMAGE_EDITOR_MAX_EXPORT_EDGE, Math.round(height))),
  };
}

export function resizeImageEditorBackingCanvas(canvas: HTMLCanvasElement | null, width: number, height: number, offsetX: number, offsetY: number) {
  if (!canvas) return;
  if (canvas.width === width && canvas.height === height && !offsetX && !offsetY) return;
  markImageEditorCanvasChanged(canvas);
  const snapshot = imageEditorCanvasSnapshot(canvas);
  const ctx = canvas.getContext("2d", { willReadFrequently: true });
  if (!ctx) return;
  canvas.width = width;
  canvas.height = height;
  ctx.clearRect(0, 0, width, height);
  if (snapshot) {
    ctx.drawImage(snapshot, offsetX, offsetY);
    snapshot.width = snapshot.height = 0;
  }
}

export function imageEditorExportBlob(canvas: any) {
  return new Promise<Blob>((resolve, reject) => {
    canvas.toBlob((blob: Blob | null) => {
      if (blob) {
        resolve(blob);
      } else {
        reject(new Error(translate("imageEditor.saveFailed")));
      }
    }, "image/png");
  });
}

export function imageEditorLayerThumbnailUrl(layer: ImageEditorLayer) {
  if (!layer.canvas?.width || !layer.canvas?.height) return "";
  try {
    const thumbnailCanvas = document.createElement("canvas");
    thumbnailCanvas.width = IMAGE_EDITOR_LAYER_THUMB_SIZE;
    thumbnailCanvas.height = IMAGE_EDITOR_LAYER_THUMB_SIZE;
    const ctx = thumbnailCanvas.getContext("2d");
    if (!ctx) return "";
    const scale = Math.min(
      thumbnailCanvas.width / Math.max(1, layer.canvas.width),
      thumbnailCanvas.height / Math.max(1, layer.canvas.height),
    );
    const width = Math.max(1, Math.round(layer.canvas.width * scale));
    const height = Math.max(1, Math.round(layer.canvas.height * scale));
    ctx.drawImage(
      layer.canvas,
      Math.round((thumbnailCanvas.width - width) / 2),
      Math.round((thumbnailCanvas.height - height) / 2),
      width,
      height,
    );
    return thumbnailCanvas.toDataURL("image/png");
  } catch {
    return "";
  }
}

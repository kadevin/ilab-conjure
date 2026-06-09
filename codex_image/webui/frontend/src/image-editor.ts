import { getEls } from "./dom";
import { getLegacyBridge, getState } from "./state";
import { translate } from "./i18n";

const IMAGE_EDITOR_PROMPT_HINT_LEGACY = "\u56fe\u4e2d\u7684\u624b\u7ed8\u7bad\u5934\u548c\u6807\u8bb0\u4ec5\u7528\u4e8e\u6307\u793a\u7f16\u8f91\u8981\u6c42\uff0c\u4e0d\u8981\u4fdd\u7559\u5728\u6700\u7ec8\u753b\u9762\u4e2d\u3002";
const IMAGE_EDITOR_MAX_EXPORT_EDGE = 4096;
const IMAGE_EDITOR_HISTORY_LIMIT = 30;

interface ImageEditorState {
  sessionId: number;
  sourceIndex: number | null;
  source: any;
  originalFile: File | null;
  image: HTMLImageElement | null;
  baseCanvas: HTMLCanvasElement | null;
  workCanvas: HTMLCanvasElement | null;
  brushBoundaryCanvas: HTMLCanvasElement | null;
  brushOverlayCanvas: HTMLCanvasElement | null;
  displayScale: number;
  tool: string;
  color: string;
  strokeWidth: number;
  crop: any;
  hasInstructionMarks: boolean;
  history: any[];
  historyIndex: number;
  drawing: any;
}

const imageEditorState = {
  sessionId: 0,
  sourceIndex: null,
  source: null,
  originalFile: null,
  image: null,
  baseCanvas: null,
  workCanvas: null,
  brushBoundaryCanvas: null,
  brushOverlayCanvas: null,
  displayScale: 1,
  tool: "crop",
  color: "#ff3b30",
  strokeWidth: 8,
  crop: null,
  hasInstructionMarks: false,
  history: [],
  historyIndex: -1,
  drawing: null,
} as ImageEditorState;

let imageEditorFeatureInitialized = false;

function legacyMethod(name: string, ...args: any[]) {
  return getLegacyBridge().methods[name]?.(...args);
}

function editedUploadFilename(name: any) {
  const sourceName = String(name || "input.png");
  const dotIndex = sourceName.lastIndexOf(".");
  const base = dotIndex > 0 ? sourceName.slice(0, dotIndex) : sourceName;
  return `${base}-edited.png`;
}

function isEditableImageSource(source: any) {
  if (!source || source.missing) return false;
  if (source.kind === "upload") return Boolean(source.file);
  return ["gallery", "asset"].includes(source.kind) && Boolean(legacyMethod("sourcePreviewUrl", source));
}

function imageEditorSourceName(source: any) {
  if (!source) return "input.png";
  if (source.kind === "asset") return source.filename || source.name || "recent-image.png";
  if (source.kind === "gallery") return source.name || "gallery-image.png";
  return source.originalFile?.name || source.file?.name || source.name || "input.png";
}

async function remoteImageSourceFile(source: any) {
  const imageUrl = legacyMethod("sourcePreviewUrl", source);
  if (!imageUrl) throw new Error(translate("imageEditor.loadForEditFailed"));
  const response = await fetch(imageUrl);
  if (!response.ok) throw new Error(translate("imageEditor.loadForEditFailed"));
  const blob = await response.blob();
  return new File([blob], imageEditorSourceName(source), {
    type: blob.type || source.mime_type || "image/png",
    lastModified: Date.now(),
  });
}

async function imageEditorSourceFile(source: any) {
  if (source.kind === "upload") return source.originalFile || source.file;
  return remoteImageSourceFile(source);
}

function setImageEditorStatus(message: any, type = "") {
  const els = getEls();
  if (!els.imageEditorStatus) return;
  els.imageEditorStatus.textContent = message || "";
  els.imageEditorStatus.className = `image-editor-status ${type || ""}`.trim();
}

function nextImageEditorSession() {
  imageEditorState.sessionId += 1;
  return imageEditorState.sessionId;
}

function imageEditorContext(canvas = imageEditorState.workCanvas) {
  return canvas?.getContext("2d", { willReadFrequently: true }) || null;
}

function imageEditorBrushBoundaryContext() {
  return imageEditorState.brushBoundaryCanvas?.getContext("2d", { willReadFrequently: true }) || null;
}

function imageEditorBrushOverlayContext() {
  return imageEditorState.brushOverlayCanvas?.getContext("2d", { willReadFrequently: true }) || null;
}

function imageEditorVisibleContext() {
  return getEls().imageEditorCanvas?.getContext("2d") || null;
}

function imageEditorCanvasSnapshot(canvas: any) {
  if (!canvas) return null;
  const snapshot = document.createElement("canvas");
  snapshot.width = canvas.width;
  snapshot.height = canvas.height;
  const ctx = snapshot.getContext("2d");
  if (!ctx) return null;
  ctx.drawImage(canvas, 0, 0);
  return snapshot;
}

function imageEditorSnapshot() {
  const workCanvas = imageEditorCanvasSnapshot(imageEditorState.workCanvas);
  if (!workCanvas) return null;
  return {
    workCanvas,
    brushBoundaryCanvas: imageEditorCanvasSnapshot(imageEditorState.brushBoundaryCanvas),
    brushOverlayCanvas: imageEditorCanvasSnapshot(imageEditorState.brushOverlayCanvas),
    hasInstructionMarks: imageEditorState.hasInstructionMarks,
  };
}

function restoreImageEditorCanvas(canvas: any, snapshot: any) {
  if (!canvas || !snapshot) return;
  const ctx = imageEditorContext(canvas);
  if (!ctx) return;
  canvas.width = snapshot.width;
  canvas.height = snapshot.height;
  ctx.clearRect(0, 0, snapshot.width, snapshot.height);
  ctx.drawImage(snapshot, 0, 0);
}

function restoreImageEditorSnapshot(snapshot: any) {
  const canvas = imageEditorState.workCanvas;
  if (!snapshot || !canvas) return;
  const workSnapshot = snapshot.workCanvas || snapshot;
  restoreImageEditorCanvas(canvas, workSnapshot);
  imageEditorState.hasInstructionMarks = Boolean(snapshot.hasInstructionMarks);
  if (imageEditorState.brushBoundaryCanvas) {
    const boundarySnapshot = snapshot.brushBoundaryCanvas;
    if (boundarySnapshot) {
      restoreImageEditorCanvas(imageEditorState.brushBoundaryCanvas, boundarySnapshot);
    } else {
      const boundaryCtx = imageEditorBrushBoundaryContext();
      boundaryCtx?.clearRect(0, 0, imageEditorState.brushBoundaryCanvas.width, imageEditorState.brushBoundaryCanvas.height);
    }
  }
  if (imageEditorState.brushOverlayCanvas) {
    const overlaySnapshot = snapshot.brushOverlayCanvas;
    if (overlaySnapshot) {
      restoreImageEditorCanvas(imageEditorState.brushOverlayCanvas, overlaySnapshot);
    } else {
      const overlayCtx = imageEditorBrushOverlayContext();
      overlayCtx?.clearRect(0, 0, imageEditorState.brushOverlayCanvas.width, imageEditorState.brushOverlayCanvas.height);
    }
  }
  renderImageEditor();
}

async function loadImageEditorImage(file: any) {
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

function imageEditorExportDimensions(image: any) {
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

function initializeImageEditorCanvases(image: any) {
  const dimensions = imageEditorExportDimensions(image);
  const baseCanvas = document.createElement("canvas");
  const workCanvas = document.createElement("canvas");
  const brushBoundaryCanvas = document.createElement("canvas");
  const brushOverlayCanvas = document.createElement("canvas");
  baseCanvas.width = dimensions.width;
  baseCanvas.height = dimensions.height;
  workCanvas.width = dimensions.width;
  workCanvas.height = dimensions.height;
  brushBoundaryCanvas.width = dimensions.width;
  brushBoundaryCanvas.height = dimensions.height;
  brushOverlayCanvas.width = dimensions.width;
  brushOverlayCanvas.height = dimensions.height;

  const baseCtx = baseCanvas.getContext("2d");
  if (!baseCtx) throw new Error(translate("imageEditor.canvasCreateFailed"));
  baseCtx.drawImage(image, 0, 0, dimensions.width, dimensions.height);

  const workCtx = workCanvas.getContext("2d");
  if (!workCtx) throw new Error(translate("imageEditor.canvasCreateFailed"));
  workCtx.drawImage(baseCanvas, 0, 0);

  imageEditorState.baseCanvas = baseCanvas;
  imageEditorState.workCanvas = workCanvas;
  imageEditorState.brushBoundaryCanvas = brushBoundaryCanvas;
  imageEditorState.brushOverlayCanvas = brushOverlayCanvas;
  imageEditorState.crop = null;
  imageEditorState.hasInstructionMarks = false;
  imageEditorState.history = [];
  imageEditorState.historyIndex = -1;
  pushImageEditorHistory();
}

function renderImageEditor() {
  const els = getEls();
  const visible = els.imageEditorCanvas;
  const work = imageEditorState.workCanvas;
  if (!visible || !work) return;

  visible.width = work.width;
  visible.height = work.height;
  const ctx = imageEditorVisibleContext();
  if (!ctx) return;
  ctx.clearRect(0, 0, visible.width, visible.height);
  ctx.drawImage(work, 0, 0);
  updateImageEditorCropBox();
  updateImageEditorControls();
}

function pushImageEditorHistory() {
  const snapshot = imageEditorSnapshot();
  if (!snapshot) return;
  imageEditorState.history = imageEditorState.history.slice(0, imageEditorState.historyIndex + 1);
  imageEditorState.history.push(snapshot);
  imageEditorState.historyIndex = imageEditorState.history.length - 1;
  if (imageEditorState.history.length > IMAGE_EDITOR_HISTORY_LIMIT) {
    const trimCount = imageEditorState.history.length - IMAGE_EDITOR_HISTORY_LIMIT;
    imageEditorState.history = imageEditorState.history.slice(trimCount);
    imageEditorState.historyIndex = Math.max(0, imageEditorState.historyIndex - trimCount);
  }
  updateImageEditorControls();
}

function undoImageEdit() {
  if (imageEditorState.historyIndex <= 0) return;
  imageEditorState.historyIndex -= 1;
  restoreImageEditorSnapshot(imageEditorState.history[imageEditorState.historyIndex]);
}

function redoImageEdit() {
  if (imageEditorState.historyIndex >= imageEditorState.history.length - 1) return;
  imageEditorState.historyIndex += 1;
  restoreImageEditorSnapshot(imageEditorState.history[imageEditorState.historyIndex]);
}

function updateImageEditorControls() {
  const els = getEls();
  const canUndo = imageEditorState.historyIndex > 0;
  const canRedo = imageEditorState.historyIndex >= 0 && imageEditorState.historyIndex < imageEditorState.history.length - 1;
  if (els.imageEditorUndo) els.imageEditorUndo.disabled = !canUndo;
  if (els.imageEditorRedo) els.imageEditorRedo.disabled = !canRedo;
  if (els.imageEditorStrokeValue) els.imageEditorStrokeValue.textContent = `${imageEditorState.strokeWidth}px`;
  document.querySelectorAll<HTMLElement>("[data-image-editor-tool]").forEach((button) => {
    button.classList.toggle("active", button.dataset.imageEditorTool === imageEditorState.tool);
  });
  document.querySelectorAll<HTMLElement>("[data-image-editor-color]").forEach((button) => {
    button.classList.toggle("active", button.dataset.imageEditorColor?.toLowerCase() === imageEditorState.color.toLowerCase());
  });
}

function updateImageEditorCropBox() {
  const els = getEls();
  const box = els.imageEditorCropBox;
  const canvas = els.imageEditorCanvas;
  const crop = imageEditorState.crop;
  if (!box || !canvas || !crop) {
    box?.classList.add("hidden");
    return;
  }
  const scaleX = canvas.clientWidth / Math.max(1, canvas.width);
  const scaleY = canvas.clientHeight / Math.max(1, canvas.height);
  box.style.left = `${crop.left * scaleX}px`;
  box.style.top = `${crop.top * scaleY}px`;
  box.style.width = `${crop.width * scaleX}px`;
  box.style.height = `${crop.height * scaleY}px`;
  box.classList.remove("hidden");
}

function imageEditorPoint(event: any) {
  const canvas = getEls().imageEditorCanvas;
  if (!canvas) return { x: 0, y: 0 };
  const rect = canvas.getBoundingClientRect();
  const scaleX = canvas.width / Math.max(1, rect.width);
  const scaleY = canvas.height / Math.max(1, rect.height);
  return {
    x: Math.max(0, Math.min(canvas.width, (event.clientX - rect.left) * scaleX)),
    y: Math.max(0, Math.min(canvas.height, (event.clientY - rect.top) * scaleY)),
  };
}

function normalizedRect(start: any, end: any) {
  const left = Math.min(start.x, end.x);
  const top = Math.min(start.y, end.y);
  const width = Math.abs(end.x - start.x);
  const height = Math.abs(end.y - start.y);
  if (width < 4 || height < 4) return null;
  return { left, top, width, height };
}

function imageEditorPointDistance(from: any, to: any) {
  return Math.hypot(to.x - from.x, to.y - from.y);
}

function isImageEditorLineGesture(from: any, to: any) {
  return imageEditorPointDistance(from, to) >= 4;
}

function imageEditorPixelOffset(index: any) {
  return index * 4;
}

function imageEditorBucketFillColor() {
  const normalized = String(imageEditorState.color || "#ff3b30").replace("#", "").trim();
  const hex = /^[0-9a-fA-F]{6}$/.test(normalized) ? normalized : "ff3b30";
  return [
    Number.parseInt(hex.slice(0, 2), 16),
    Number.parseInt(hex.slice(2, 4), 16),
    Number.parseInt(hex.slice(4, 6), 16),
    255,
  ];
}

function imageEditorBoundaryPixelBlocks(data: any, index: any) {
  return data[imageEditorPixelOffset(index) + 3] > 0;
}

function imageEditorBoundaryHasPixels(data: any) {
  for (let offset = 3; offset < data.length; offset += 4) {
    if (data[offset] > 0) return true;
  }
  return false;
}

function imageEditorPixelTouchesCanvasEdge(index: any, width: any, height: any) {
  const column = index % width;
  const row = Math.floor(index / width);
  return column === 0 || column === width - 1 || row === 0 || row === height - 1;
}

function paintBucketFillRegion(point: any) {
  const canvas = imageEditorState.workCanvas;
  const ctx = imageEditorContext(canvas);
  const boundaryCanvas = imageEditorState.brushBoundaryCanvas;
  const boundaryCtx = imageEditorBrushBoundaryContext();
  if (!canvas || !ctx || !boundaryCanvas || !boundaryCtx) return false;

  const width = canvas.width;
  const height = canvas.height;
  const x = Math.max(0, Math.min(width - 1, Math.floor(point.x)));
  const y = Math.max(0, Math.min(height - 1, Math.floor(point.y)));
  const boundaryData = boundaryCtx.getImageData(0, 0, width, height).data;
  if (!imageEditorBoundaryHasPixels(boundaryData)) return false;

  const startIndex = y * width + x;
  if (imageEditorBoundaryPixelBlocks(boundaryData, startIndex)) return false;

  const visited = new Uint8Array(width * height);
  const stack = new Int32Array(width * height);
  const region: number[] = [];
  let stackLength = 0;
  const pushPixel = (index: number) => {
    if (visited[index]) return;
    visited[index] = 1;
    if (imageEditorBoundaryPixelBlocks(boundaryData, index)) return;
    stack[stackLength] = index;
    stackLength += 1;
  };

  pushPixel(startIndex);
  while (stackLength > 0) {
    stackLength -= 1;
    const index = stack[stackLength];
    if (index === undefined) break;
    if (imageEditorPixelTouchesCanvasEdge(index, width, height)) return false;
    region.push(index);

    const column = index % width;
    if (column > 0) pushPixel(index - 1);
    if (column < width - 1) pushPixel(index + 1);
    if (index >= width) pushPixel(index - width);
    if (index < width * (height - 1)) pushPixel(index + width);
  }

  if (!region.length) return false;
  const imageData = ctx.getImageData(0, 0, width, height);
  const data = imageData.data;
  const fill = imageEditorBucketFillColor();
  const [red = 0, green = 0, blue = 0, alpha = 255] = fill;
  region.forEach((index) => {
    const offset = imageEditorPixelOffset(index);
    data[offset] = red;
    data[offset + 1] = green;
    data[offset + 2] = blue;
    data[offset + 3] = alpha;
  });
  ctx.putImageData(imageData, 0, 0);
  redrawImageEditorBrushOverlay(ctx);
  return true;
}

function configureImageEditorStroke(ctx: any, options: any = {}) {
  if (!ctx) return;
  ctx.strokeStyle = imageEditorState.color;
  ctx.fillStyle = imageEditorState.color;
  ctx.lineWidth = imageEditorState.strokeWidth;
  ctx.lineCap = options.lineCap || "round";
  ctx.lineJoin = options.lineJoin || "round";
  ctx.miterLimit = options.miterLimit || 10;
}

function drawEditorBrushBoundarySegment(from: any, to: any) {
  const ctx = imageEditorBrushBoundaryContext();
  if (!ctx) return;
  ctx.strokeStyle = "#000";
  ctx.fillStyle = "#000";
  ctx.lineWidth = imageEditorState.strokeWidth;
  ctx.lineCap = "round";
  ctx.lineJoin = "round";
  ctx.beginPath();
  ctx.moveTo(from.x, from.y);
  ctx.lineTo(to.x, to.y);
  ctx.stroke();
}

function drawEditorBrushOverlaySegment(from: any, to: any) {
  const ctx = imageEditorBrushOverlayContext();
  if (!ctx) return;
  configureImageEditorStroke(ctx);
  ctx.beginPath();
  ctx.moveTo(from.x, from.y);
  ctx.lineTo(to.x, to.y);
  ctx.stroke();
}

function redrawImageEditorBrushOverlay(ctx: any) {
  if (!ctx || !imageEditorState.brushOverlayCanvas) return;
  ctx.drawImage(imageEditorState.brushOverlayCanvas, 0, 0);
}

function drawEditorBrushSegment(from: any, to: any) {
  const ctx = imageEditorContext();
  if (!ctx) return;
  configureImageEditorStroke(ctx);
  ctx.beginPath();
  ctx.moveTo(from.x, from.y);
  ctx.lineTo(to.x, to.y);
  ctx.stroke();
  drawEditorBrushBoundarySegment(from, to);
  drawEditorBrushOverlaySegment(from, to);
}

function drawEditorArrowOnContext(ctx: any, start: any, end: any) {
  if (!ctx) return;
  configureImageEditorStroke(ctx, { lineCap: "butt", lineJoin: "miter" });
  const angle = Math.atan2(end.y - start.y, end.x - start.x);
  const headLength = Math.max(12, imageEditorState.strokeWidth * 3.2);
  const shaftEnd = {
    x: end.x - headLength * Math.cos(angle),
    y: end.y - headLength * Math.sin(angle),
  };
  ctx.beginPath();
  ctx.moveTo(start.x, start.y);
  ctx.lineTo(shaftEnd.x, shaftEnd.y);
  ctx.stroke();
  ctx.beginPath();
  ctx.moveTo(end.x, end.y);
  ctx.lineTo(end.x - headLength * Math.cos(angle - Math.PI / 6), end.y - headLength * Math.sin(angle - Math.PI / 6));
  ctx.lineTo(end.x - headLength * Math.cos(angle + Math.PI / 6), end.y - headLength * Math.sin(angle + Math.PI / 6));
  ctx.closePath();
  ctx.fill();
}

function previewEditorArrow(start: any, end: any) {
  renderImageEditor();
  const ctx = imageEditorVisibleContext();
  if (!ctx) return;
  drawEditorArrowOnContext(ctx, start, end);
}

function handleImageEditorPointerDown(event: any) {
  if (!imageEditorState.workCanvas) return;
  event.preventDefault();
  const point = imageEditorPoint(event);
  if (imageEditorState.tool === "fill") {
    if (paintBucketFillRegion(point)) {
      imageEditorState.hasInstructionMarks = true;
      pushImageEditorHistory();
      setImageEditorStatus("");
    } else {
      setImageEditorStatus(translate("imageEditor.closedRegionRequired"), "error");
    }
    renderImageEditor();
    return;
  }
  getEls().imageEditorCanvas?.setPointerCapture?.(event.pointerId);
  imageEditorState.drawing = {
    pointerId: event.pointerId,
    start: point,
    last: point,
  };
  if (imageEditorState.tool === "crop") {
    imageEditorState.crop = { left: point.x, top: point.y, width: 0, height: 0 };
    updateImageEditorCropBox();
  }
}

function handleImageEditorPointerMove(event: any) {
  const drawing = imageEditorState.drawing;
  if (!drawing || drawing.pointerId !== event.pointerId) return;
  event.preventDefault();
  const point = imageEditorPoint(event);
  if (imageEditorState.tool === "brush") {
    drawEditorBrushSegment(drawing.last, point);
    if (imageEditorPointDistance(drawing.last, point) > 0) {
      imageEditorState.hasInstructionMarks = true;
    }
    drawing.last = point;
    renderImageEditor();
    return;
  }
  if (imageEditorState.tool === "arrow") {
    previewEditorArrow(drawing.start, point);
    return;
  }
  if (imageEditorState.tool === "crop") {
    imageEditorState.crop = normalizedRect(drawing.start, point);
    updateImageEditorCropBox();
  }
}

function handleImageEditorPointerUp(event: any) {
  const drawing = imageEditorState.drawing;
  if (!drawing || drawing.pointerId !== event.pointerId) return;
  event.preventDefault();
  const point = imageEditorPoint(event);
  getEls().imageEditorCanvas?.releasePointerCapture?.(event.pointerId);
  if (imageEditorState.tool === "arrow") {
    const ctx = imageEditorContext();
    if (ctx && isImageEditorLineGesture(drawing.start, point)) {
      drawEditorArrowOnContext(ctx, drawing.start, point);
      imageEditorState.hasInstructionMarks = true;
      pushImageEditorHistory();
    }
  } else if (imageEditorState.tool === "brush") {
    pushImageEditorHistory();
  } else if (imageEditorState.tool === "crop") {
    imageEditorState.crop = normalizedRect(drawing.start, point);
  }
  imageEditorState.drawing = null;
  renderImageEditor();
}

function handleImageEditorPointerCancel(event: any) {
  const drawing = imageEditorState.drawing;
  if (!drawing || drawing.pointerId !== event.pointerId) return;
  getEls().imageEditorCanvas?.releasePointerCapture?.(event.pointerId);
  if (imageEditorState.tool === "brush") {
    pushImageEditorHistory();
  } else if (imageEditorState.tool === "crop") {
    imageEditorState.crop = null;
  }
  imageEditorState.drawing = null;
  renderImageEditor();
}

function imageEditorCanvasForSave() {
  const sourceCanvas = imageEditorState.workCanvas;
  if (!sourceCanvas) return null;
  const crop = imageEditorState.crop;
  if (!crop) return sourceCanvas;

  const output = document.createElement("canvas");
  output.width = Math.max(1, Math.round(crop.width));
  output.height = Math.max(1, Math.round(crop.height));
  const ctx = output.getContext("2d");
  if (!ctx) return null;
  ctx.drawImage(
    sourceCanvas,
    crop.left,
    crop.top,
    crop.width,
    crop.height,
    0,
    0,
    output.width,
    output.height,
  );
  return output;
}

function imageEditorExportBlob(canvas: any) {
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

function ensureImageEditorPromptHint() {
  const current = legacyMethod("getPromptText");
  const hint = translate("imageEditor.promptHint");
  if (current.includes(hint) || current.includes(IMAGE_EDITOR_PROMPT_HINT_LEGACY)) return;
  const next = current ? `${current}\n${hint}` : hint;
  legacyMethod("setPromptText", next);
  legacyMethod("updatePromptCount");
}

async function saveImageEdit() {
  const state = getState();
  const els = getEls();
  const sessionId = imageEditorState.sessionId;
  const source = imageEditorState.source;
  const saveCanvas = imageEditorCanvasForSave();
  if (!source || !isEditableImageSource(source) || !saveCanvas || !state.images.includes(source)) {
    setImageEditorStatus(translate("imageEditor.saveFailed"), "error");
    return;
  }
  if (els.imageEditorSave) els.imageEditorSave.disabled = true;
  try {
    const blob = await imageEditorExportBlob(saveCanvas);
    const sourceIndex = state.images.indexOf(source);
    if (
      sessionId !== imageEditorState.sessionId
      || imageEditorState.source !== source
      || sourceIndex < 0
    ) {
      return;
    }
    const filename = editedUploadFilename(source.originalFile?.name || source.name || source.file?.name);
    const file = new File([blob], filename, {
      type: "image/png",
      lastModified: Date.now(),
    });
    const nextSource = {
      kind: "upload",
      file,
      originalFile: source.originalFile || imageEditorState.originalFile || file,
      name: filename,
      previewUrl: URL.createObjectURL(file),
      edited: true,
    };
    state.images[sourceIndex] = nextSource;
    legacyMethod("revokeUploadPreviewUrl", source);
    legacyMethod("syncPromptGalleryMentionsFromInputs");
    if (imageEditorState.hasInstructionMarks) ensureImageEditorPromptHint();
    legacyMethod("renderImageStrip");
    legacyMethod("updateRequestPreview");
    closeImageEditor();
    legacyMethod("setStatus", translate("imageEditor.saved"), "ok");
  } catch (error: any) {
    setImageEditorStatus(error.message || translate("imageEditor.saveFailed"), "error");
  } finally {
    if (els.imageEditorSave) els.imageEditorSave.disabled = false;
  }
}

async function openImageEditor(index: any) {
  const state = getState();
  const els = getEls();
  const source = state.images[index];
  if (!source || !isEditableImageSource(source)) {
    legacyMethod("setStatus", translate("imageEditor.uneditable"), "error");
    return;
  }

  const sessionId = nextImageEditorSession();
  imageEditorState.sourceIndex = index;
  imageEditorState.source = source;
  imageEditorState.originalFile = null;
  imageEditorState.tool = "crop";
  imageEditorState.color = els.imageEditorColor?.value || "#ff3b30";
  imageEditorState.strokeWidth = Number(els.imageEditorStroke?.value || 8);
  imageEditorState.hasInstructionMarks = false;
  imageEditorState.drawing = null;
  setImageEditorStatus("");
  if (els.imageEditorSubtitle) {
    els.imageEditorSubtitle.textContent = legacyMethod("sourceName", source) || translate("imageEditor.inputFallback");
  }

  els.imageEditorModal?.classList.remove("hidden");
  try {
    const file = await imageEditorSourceFile(source);
    if (sessionId !== imageEditorState.sessionId || imageEditorState.source !== source) return;
    imageEditorState.originalFile = file;
    const image = await loadImageEditorImage(file);
    if (sessionId !== imageEditorState.sessionId || imageEditorState.source !== source) return;
    imageEditorState.image = image;
    initializeImageEditorCanvases(image);
    renderImageEditor();
  } catch {
    if (sessionId !== imageEditorState.sessionId || imageEditorState.source !== source) return;
    closeImageEditor();
    legacyMethod("setStatus", translate("imageEditor.openFailed"), "error");
  }
}

function closeImageEditor() {
  const els = getEls();
  nextImageEditorSession();
  els.imageEditorModal?.classList.add("hidden");
  imageEditorState.sourceIndex = null;
  imageEditorState.source = null;
  imageEditorState.originalFile = null;
  imageEditorState.image = null;
  imageEditorState.baseCanvas = null;
  imageEditorState.workCanvas = null;
  imageEditorState.brushBoundaryCanvas = null;
  imageEditorState.brushOverlayCanvas = null;
  imageEditorState.crop = null;
  imageEditorState.hasInstructionMarks = false;
  imageEditorState.history = [];
  imageEditorState.historyIndex = -1;
  imageEditorState.drawing = null;
  setImageEditorStatus("");
  updateImageEditorControls();
}

function setImageEditorTool(tool: any) {
  if (!["brush", "arrow", "crop", "fill"].includes(tool)) return;
  imageEditorState.tool = tool;
  imageEditorState.drawing = null;
  updateImageEditorControls();
}

async function resetImageEdit() {
  const sessionId = imageEditorState.sessionId;
  const source = imageEditorState.source;
  const file = imageEditorState.originalFile;
  if (!file) return;
  try {
    const image = await loadImageEditorImage(file);
    if (
      sessionId !== imageEditorState.sessionId
      || imageEditorState.source !== source
      || imageEditorState.originalFile !== file
    ) return;
    imageEditorState.image = image;
    initializeImageEditorCanvases(image);
    renderImageEditor();
    setImageEditorStatus(translate("imageEditor.resetDone"));
  } catch {
    if (
      sessionId !== imageEditorState.sessionId
      || imageEditorState.source !== source
      || imageEditorState.originalFile !== file
    ) return;
    setImageEditorStatus(translate("imageEditor.resetFailed"), "error");
  }
}

function isImageEditorModalOpen() {
  const els = getEls();
  return Boolean(els.imageEditorModal && !els.imageEditorModal.classList.contains("hidden"));
}

function handleImageEditorHistoryShortcut(event: KeyboardEvent) {
  if (!isImageEditorModalOpen()) return false;
  if (!(event.metaKey || event.ctrlKey) || event.altKey) return false;
  if (event.key.toLowerCase() === "z" && event.shiftKey) {
    event.preventDefault();
    redoImageEdit();
    return true;
  }
  if (event.key.toLowerCase() === "z") {
    event.preventDefault();
    undoImageEdit();
    return true;
  }
  if (event.key.toLowerCase() === "y") {
    event.preventDefault();
    redoImageEdit();
    return true;
  }
  return false;
}

function bindImageEditorEvents() {
  const els = getEls();
  els.imageEditorClose?.addEventListener("click", closeImageEditor);
  els.imageEditorCancel?.addEventListener("click", closeImageEditor);
  els.imageEditorModal?.addEventListener("click", (event: MouseEvent) => {
    if (event.target === els.imageEditorModal) closeImageEditor();
  });
  document.querySelectorAll<HTMLElement>("[data-image-editor-tool]").forEach((button) => {
    button.addEventListener("click", () => setImageEditorTool(button.dataset.imageEditorTool));
  });
  document.querySelectorAll<HTMLElement>("[data-image-editor-color]").forEach((button) => {
    button.addEventListener("click", () => {
      imageEditorState.color = button.dataset.imageEditorColor || imageEditorState.color;
      if (els.imageEditorColor) els.imageEditorColor.value = imageEditorState.color;
      updateImageEditorControls();
    });
  });
  els.imageEditorColor?.addEventListener("input", () => {
    imageEditorState.color = els.imageEditorColor.value || imageEditorState.color;
    updateImageEditorControls();
  });
  els.imageEditorStroke?.addEventListener("input", () => {
    imageEditorState.strokeWidth = Number(els.imageEditorStroke.value || 8);
    updateImageEditorControls();
  });
  els.imageEditorUndo?.addEventListener("click", undoImageEdit);
  els.imageEditorRedo?.addEventListener("click", redoImageEdit);
  els.imageEditorReset?.addEventListener("click", resetImageEdit);
  els.imageEditorSave?.addEventListener("click", saveImageEdit);
  els.imageEditorCanvas?.addEventListener("pointerdown", handleImageEditorPointerDown);
  els.imageEditorCanvas?.addEventListener("pointermove", handleImageEditorPointerMove);
  els.imageEditorCanvas?.addEventListener("pointerup", handleImageEditorPointerUp);
  els.imageEditorCanvas?.addEventListener("pointercancel", handleImageEditorPointerCancel);
}

export function initImageEditorFeature() {
  if (imageEditorFeatureInitialized) return;
  imageEditorFeatureInitialized = true;
  bindImageEditorEvents();
  Object.assign(getLegacyBridge().methods, {
    openImageEditor,
    closeImageEditor,
    isEditableImageSource,
    handleImageEditorHistoryShortcut,
    isImageEditorModalOpen,
  });
}

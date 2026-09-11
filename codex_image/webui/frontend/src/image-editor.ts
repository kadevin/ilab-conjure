import Konva from "konva";

import { getEls } from "./dom";
import { getLegacyBridge, getState } from "./state";
import { translate } from "./i18n";
import type {
  ImageEditorLayer,
  ImageEditorLayerSnapshot,
  ImageEditorSnapshot,
  ImageEditorState,
} from "./image-editor-types";

const IMAGE_EDITOR_PROMPT_HINT_LEGACY = "\u56fe\u4e2d\u7684\u624b\u7ed8\u7bad\u5934\u548c\u6807\u8bb0\u4ec5\u7528\u4e8e\u6307\u793a\u7f16\u8f91\u8981\u6c42\uff0c\u4e0d\u8981\u4fdd\u7559\u5728\u6700\u7ec8\u753b\u9762\u4e2d\u3002";
const IMAGE_EDITOR_MAX_EXPORT_EDGE = 4096;
const IMAGE_EDITOR_HISTORY_LIMIT = 30;
const IMAGE_EDITOR_LAYER_FIT_RATIO = 0.72;
const IMAGE_EDITOR_LAYER_THUMB_SIZE = 96;

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
  konvaStage: null,
  konvaLayer: null,
  konvaTransformer: null,
  markNode: null,
  previewNode: null,
  layers: [],
  selectedLayerId: null,
  displayScale: 1,
  tool: "crop",
  color: "#ff3b30",
  strokeWidth: 8,
  crop: null,
  canvasScope: "base",
  hasInstructionMarks: false,
  history: [],
  historyIndex: -1,
  drawing: null,
} as ImageEditorState;

let imageEditorFeatureInitialized = false;
let imageEditorLayerSequence = 0;

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

function imageEditorLayerAttrs(node: any) {
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

function imageEditorSnapshot(): ImageEditorSnapshot | null {
  if (!imageEditorState.workCanvas) return null;
  return {
    layers: imageEditorState.layers.map((layer) => ({
      id: layer.id,
      sourceIndex: layer.sourceIndex,
      name: layer.name,
      canvas: imageEditorCanvasSnapshot(layer.canvas) || layer.canvas,
      attrs: imageEditorLayerAttrs(layer.node),
      edited: layer.edited,
    })),
    workCanvas: imageEditorCanvasSnapshot(imageEditorState.workCanvas) || imageEditorState.workCanvas,
    brushBoundaryCanvas: imageEditorCanvasSnapshot(imageEditorState.brushBoundaryCanvas),
    brushOverlayCanvas: imageEditorCanvasSnapshot(imageEditorState.brushOverlayCanvas),
    canvasScope: imageEditorState.canvasScope,
    crop: imageEditorState.crop ? { ...imageEditorState.crop } : null,
    selectedLayerId: imageEditorState.selectedLayerId,
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

function rebuildImageEditorLayers(snapshots: ImageEditorLayerSnapshot[]) {
  const konvaLayer = imageEditorState.konvaLayer;
  if (!konvaLayer) return;
  imageEditorState.layers.forEach((layer) => layer.node?.destroy?.());
  imageEditorState.layers = [];
  snapshots.forEach((snapshot) => {
    const canvas = imageEditorCanvasSnapshot(snapshot.canvas) || snapshot.canvas;
    const layer = createImageEditorLayerFromCanvas(canvas, {
      id: snapshot.id,
      source: null,
      sourceIndex: snapshot.sourceIndex,
      name: snapshot.name,
      attrs: snapshot.attrs,
      edited: snapshot.edited,
      pushHistory: false,
    });
    imageEditorState.layers.push(layer);
  });
  orderImageEditorKonvaNodes();
}

function restoreImageEditorSnapshot(snapshot: ImageEditorSnapshot | null) {
  if (!snapshot) return;
  imageEditorState.canvasScope = snapshot.canvasScope || "base";
  resizeImageEditorCanvas(snapshot.workCanvas.width, snapshot.workCanvas.height, 0, 0);
  rebuildImageEditorLayers(snapshot.layers);
  restoreImageEditorCanvas(imageEditorState.workCanvas, snapshot.workCanvas);
  imageEditorState.hasInstructionMarks = Boolean(snapshot.hasInstructionMarks);
  imageEditorState.crop = snapshot.crop ? { ...snapshot.crop } : null;
  imageEditorState.selectedLayerId = snapshot.selectedLayerId;
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
  selectImageEditorLayer(snapshot.selectedLayerId, { updateTool: false });
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

function imageEditorCanvasFromImage(image: HTMLImageElement, dimensions = imageEditorExportDimensions(image)) {
  const canvas = document.createElement("canvas");
  canvas.width = dimensions.width;
  canvas.height = dimensions.height;
  const ctx = canvas.getContext("2d");
  if (!ctx) throw new Error(translate("imageEditor.canvasCreateFailed"));
  ctx.drawImage(image, 0, 0, dimensions.width, dimensions.height);
  return canvas;
}

function imageEditorBaseDimensions() {
  const baseCanvas = imageEditorState.baseCanvas;
  return {
    width: Math.max(1, Math.round(baseCanvas?.width || imageEditorState.konvaStage?.width?.() || 1)),
    height: Math.max(1, Math.round(baseCanvas?.height || imageEditorState.konvaStage?.height?.() || 1)),
  };
}

function imageEditorClampedCanvasDimensions(width: number, height: number) {
  return {
    width: Math.max(1, Math.min(IMAGE_EDITOR_MAX_EXPORT_EDGE, Math.round(width))),
    height: Math.max(1, Math.min(IMAGE_EDITOR_MAX_EXPORT_EDGE, Math.round(height))),
  };
}

function resizeImageEditorBackingCanvas(canvas: HTMLCanvasElement | null, width: number, height: number, offsetX: number, offsetY: number) {
  if (!canvas) return;
  if (canvas.width === width && canvas.height === height && !offsetX && !offsetY) return;
  const snapshot = imageEditorCanvasSnapshot(canvas);
  const ctx = canvas.getContext("2d", { willReadFrequently: true });
  if (!ctx) return;
  canvas.width = width;
  canvas.height = height;
  ctx.clearRect(0, 0, width, height);
  if (snapshot) ctx.drawImage(snapshot, offsetX, offsetY);
}

function resizeImageEditorCanvas(width: number, height: number, offsetX = 0, offsetY = 0) {
  const dimensions = imageEditorClampedCanvasDimensions(width, height);
  const stage = imageEditorState.konvaStage;
  const didResize = stage?.width?.() !== dimensions.width || stage?.height?.() !== dimensions.height;
  const didShift = Boolean(offsetX || offsetY);
  if (!didResize && !didShift) return false;

  stage?.width?.(dimensions.width);
  stage?.height?.(dimensions.height);
  resizeImageEditorBackingCanvas(imageEditorState.workCanvas, dimensions.width, dimensions.height, offsetX, offsetY);
  resizeImageEditorBackingCanvas(imageEditorState.brushBoundaryCanvas, dimensions.width, dimensions.height, offsetX, offsetY);
  resizeImageEditorBackingCanvas(imageEditorState.brushOverlayCanvas, dimensions.width, dimensions.height, offsetX, offsetY);
  imageEditorState.layers.forEach((layer) => {
    layer.node?.x?.((layer.node.x?.() || 0) + offsetX);
    layer.node?.y?.((layer.node.y?.() || 0) + offsetY);
  });
  if (imageEditorState.crop) {
    imageEditorState.crop = {
      ...imageEditorState.crop,
      left: imageEditorState.crop.left + offsetX,
      top: imageEditorState.crop.top + offsetY,
    };
  }
  if (imageEditorState.markNode) {
    imageEditorState.markNode.image(imageEditorState.workCanvas);
    imageEditorState.markNode.x(0);
    imageEditorState.markNode.y(0);
    imageEditorState.markNode.width(dimensions.width);
    imageEditorState.markNode.height(dimensions.height);
  }
  updateImageEditorDisplayScale();
  imageEditorState.konvaLayer?.batchDraw?.();
  return true;
}

function imageEditorLayerClientRect(layer: ImageEditorLayer) {
  const rect = layer.node.getClientRect?.({ skipShadow: true, skipStroke: true }) || layer.node.getClientRect?.() || null;
  if (
    !rect
    || !Number.isFinite(rect.x)
    || !Number.isFinite(rect.y)
    || !Number.isFinite(rect.width)
    || !Number.isFinite(rect.height)
  ) {
    return null;
  }
  return {
    minX: rect.x,
    minY: rect.y,
    maxX: rect.x + Math.max(0, rect.width),
    maxY: rect.y + Math.max(0, rect.height),
  };
}

function imageEditorBaseLayerOffset() {
  const baseLayer = imageEditorState.layers[0] || null;
  return {
    x: baseLayer?.node?.x?.() || 0,
    y: baseLayer?.node?.y?.() || 0,
  };
}

function fitImageEditorCanvasToLayers(options: { preserveCurrent?: boolean; pushHistory?: boolean; status?: boolean } = {}) {
  const stage = imageEditorState.konvaStage;
  if (!stage) return false;
  const baseDimensions = imageEditorBaseDimensions();
  const preserveCurrent = options.preserveCurrent !== false;
  let minX = preserveCurrent ? 0 : Math.min(0, imageEditorBaseLayerOffset().x);
  let minY = preserveCurrent ? 0 : Math.min(0, imageEditorBaseLayerOffset().y);
  let maxX = preserveCurrent ? stage.width() : Math.max(baseDimensions.width, imageEditorBaseLayerOffset().x + baseDimensions.width);
  let maxY = preserveCurrent ? stage.height() : Math.max(baseDimensions.height, imageEditorBaseLayerOffset().y + baseDimensions.height);

  imageEditorState.layers.forEach((layer) => {
    const rect = imageEditorLayerClientRect(layer);
    if (!rect) return;
    minX = Math.min(minX, Math.floor(rect.minX));
    minY = Math.min(minY, Math.floor(rect.minY));
    maxX = Math.max(maxX, Math.ceil(rect.maxX));
    maxY = Math.max(maxY, Math.ceil(rect.maxY));
  });

  const width = Math.max(1, maxX - minX);
  const height = Math.max(1, maxY - minY);
  const offsetX = minX < 0 || !preserveCurrent ? -minX : 0;
  const offsetY = minY < 0 || !preserveCurrent ? -minY : 0;
  const resized = resizeImageEditorCanvas(width, height, offsetX, offsetY);
  if (resized && options.pushHistory) pushImageEditorHistory();
  if (resized && options.status) setImageEditorStatus(translate("imageEditor.canvasFitDone"));
  return resized;
}

function resetImageEditorCanvasToBase(options: { pushHistory?: boolean; status?: boolean } = {}) {
  const baseDimensions = imageEditorBaseDimensions();
  const baseOffset = imageEditorBaseLayerOffset();
  const resized = resizeImageEditorCanvas(baseDimensions.width, baseDimensions.height, -baseOffset.x, -baseOffset.y);
  if (resized && options.pushHistory) pushImageEditorHistory();
  if (options.status) setImageEditorStatus(translate("imageEditor.canvasBaseDone"));
  return resized;
}

function fitImageEditorLayerAttrs(canvas: HTMLCanvasElement, baseWidth: number, baseHeight: number, isBase = false) {
  if (isBase) {
    return { x: 0, y: 0, width: canvas.width, height: canvas.height, scaleX: 1, scaleY: 1, rotation: 0, opacity: 1 };
  }
  const fitScale = Math.min(
    1,
    (baseWidth * IMAGE_EDITOR_LAYER_FIT_RATIO) / Math.max(1, canvas.width),
    (baseHeight * IMAGE_EDITOR_LAYER_FIT_RATIO) / Math.max(1, canvas.height),
  );
  const width = Math.max(1, Math.round(canvas.width * fitScale));
  const height = Math.max(1, Math.round(canvas.height * fitScale));
  return {
    x: Math.round((baseWidth - width) / 2),
    y: Math.round((baseHeight - height) / 2),
    width,
    height,
    scaleX: 1,
    scaleY: 1,
    rotation: 0,
    opacity: 1,
  };
}

function createImageEditorLayerFromCanvas(canvas: HTMLCanvasElement, options: any) {
  const attrs = options.attrs || fitImageEditorLayerAttrs(
    canvas,
    imageEditorState.konvaStage?.width?.() || canvas.width,
    imageEditorState.konvaStage?.height?.() || canvas.height,
    Boolean(options.isBase),
  );
  const node = new Konva.Image({
    image: canvas,
    x: attrs.x,
    y: attrs.y,
    width: attrs.width,
    height: attrs.height,
    scaleX: attrs.scaleX ?? 1,
    scaleY: attrs.scaleY ?? 1,
    rotation: attrs.rotation ?? 0,
    opacity: attrs.opacity ?? 1,
    draggable: imageEditorState.tool === "select",
    name: "image-editor-layer-node",
  });
  const layer: ImageEditorLayer = {
    id: options.id || `image-layer-${Date.now()}-${imageEditorLayerSequence += 1}`,
    source: options.source,
    sourceIndex: options.sourceIndex ?? null,
    name: options.name || translate("imageEditor.inputFallback"),
    canvas,
    node,
    edited: Boolean(options.edited),
  };
  node.on("click tap", (event: any) => {
    if (imageEditorState.tool === "select") {
      const point = imageEditorPoint(event.evt || event);
      const hitLayer = imageEditorLayerAtPoint(point) || layer;
      selectImageEditorLayer(hitLayer.id, { updateTool: false });
    }
  });
  node.on("dragstart", (event: any) => {
    if (imageEditorState.tool === "select") {
      const point = imageEditorPoint(event.evt || event);
      const hitLayer = imageEditorLayerAtPoint(point) || layer;
      selectImageEditorLayer(hitLayer.id, { updateTool: false });
    }
  });
  node.on("dragend transformend", () => {
    if (imageEditorState.tool === "select") {
      if (imageEditorState.canvasScope === "fit") {
        fitImageEditorCanvasToLayers({ preserveCurrent: true });
      }
      pushImageEditorHistory();
      renderImageEditorLayerList();
    }
  });
  imageEditorState.konvaLayer?.add(node);
  return layer;
}

function imageEditorLayerFromNode(node: any) {
  return imageEditorState.layers.find((layer) => layer.node === node) || null;
}

function isImageEditorTransformerTarget(node: any) {
  let current = node;
  while (current) {
    if (current === imageEditorState.konvaTransformer) return true;
    current = current.getParent?.();
  }
  return false;
}

function imageEditorLayerAtPoint(point: any) {
  for (let index = imageEditorState.layers.length - 1; index >= 0; index -= 1) {
    const layer = imageEditorState.layers[index];
    if (!layer) continue;
    const rect = layer.node.getClientRect?.() || null;
    if (
      rect
      && point.x >= rect.x
      && point.x <= rect.x + rect.width
      && point.y >= rect.y
      && point.y <= rect.y + rect.height
    ) {
      return layer;
    }
  }
  return null;
}

function orderImageEditorKonvaNodes() {
  imageEditorState.layers.forEach((layer, index) => {
    layer.node?.zIndex?.(index);
  });
  imageEditorState.markNode?.moveToTop?.();
  imageEditorState.previewNode?.moveToTop?.();
  imageEditorState.konvaTransformer?.moveToTop?.();
  imageEditorState.konvaLayer?.batchDraw?.();
}

function createImageEditorMarkNode() {
  if (!imageEditorState.workCanvas) return null;
  const markNode = new Konva.Image({
    image: imageEditorState.workCanvas,
    x: 0,
    y: 0,
    width: imageEditorState.workCanvas.width,
    height: imageEditorState.workCanvas.height,
    listening: false,
    name: "image-editor-mark-layer",
  });
  imageEditorState.konvaLayer?.add(markNode);
  return markNode;
}

function destroyImageEditorKonva() {
  clearImageEditorPreview();
  imageEditorState.konvaTransformer?.destroy?.();
  imageEditorState.konvaLayer?.destroy?.();
  imageEditorState.konvaStage?.destroy?.();
  imageEditorState.konvaTransformer = null;
  imageEditorState.konvaLayer = null;
  imageEditorState.konvaStage = null;
  imageEditorState.markNode = null;
  imageEditorState.previewNode = null;
}

function initializeImageEditorKonva(width: number, height: number) {
  const els = getEls();
  const container = els.imageEditorKonvaMount;
  if (!container) throw new Error(translate("imageEditor.canvasCreateFailed"));
  destroyImageEditorKonva();
  container.innerHTML = "";
  const stage = new Konva.Stage({
    container,
    width,
    height,
  });
  const layer = new Konva.Layer();
  const transformer = new Konva.Transformer({
    rotateEnabled: true,
    keepRatio: true,
    shiftBehavior: "inverted",
    anchorSize: 14,
    anchorStroke: "#2F6FE4",
    anchorFill: "#FFFFFF",
    borderStroke: "#2F6FE4",
    rotateAnchorOffset: 28,
    enabledAnchors: [
      "top-left",
      "top-center",
      "top-right",
      "middle-left",
      "middle-right",
      "bottom-left",
      "bottom-center",
      "bottom-right",
    ],
  });
  stage.add(layer);
  layer.add(transformer);
  imageEditorState.konvaStage = stage;
  imageEditorState.konvaLayer = layer;
  imageEditorState.konvaTransformer = transformer;
  bindImageEditorStageEvents(stage);
}

function initializeImageEditorCanvases(image: any) {
  const dimensions = imageEditorExportDimensions(image);
  const baseCanvas = imageEditorCanvasFromImage(image, dimensions);
  const workCanvas = document.createElement("canvas");
  const brushBoundaryCanvas = document.createElement("canvas");
  const brushOverlayCanvas = document.createElement("canvas");
  workCanvas.width = dimensions.width;
  workCanvas.height = dimensions.height;
  brushBoundaryCanvas.width = dimensions.width;
  brushBoundaryCanvas.height = dimensions.height;
  brushOverlayCanvas.width = dimensions.width;
  brushOverlayCanvas.height = dimensions.height;

  imageEditorState.baseCanvas = baseCanvas;
  imageEditorState.workCanvas = workCanvas;
  imageEditorState.brushBoundaryCanvas = brushBoundaryCanvas;
  imageEditorState.brushOverlayCanvas = brushOverlayCanvas;
  imageEditorState.crop = null;
  imageEditorState.canvasScope = "base";
  imageEditorState.hasInstructionMarks = false;
  imageEditorState.history = [];
  imageEditorState.historyIndex = -1;
  imageEditorState.layers = [];
  imageEditorState.selectedLayerId = null;
  initializeImageEditorKonva(dimensions.width, dimensions.height);
  const baseLayer = createImageEditorLayerFromCanvas(baseCanvas, {
    source: imageEditorState.source,
    sourceIndex: imageEditorState.sourceIndex,
    name: imageEditorSourceName(imageEditorState.source),
    isBase: true,
    edited: false,
  });
  imageEditorState.layers.push(baseLayer);
  imageEditorState.markNode = createImageEditorMarkNode();
  orderImageEditorKonvaNodes();
  selectImageEditorLayer(baseLayer.id, { updateTool: false });
  renderImageEditorInsertList();
  renderImageEditorLayerList();
  pushImageEditorHistory();
}

function renderImageEditor() {
  const els = getEls();
  const visible = els.imageEditorCanvas;
  const stage = imageEditorState.konvaStage;
  const work = imageEditorState.workCanvas;
  if (visible && work) {
    visible.width = work.width;
    visible.height = work.height;
  }
  if (imageEditorState.markNode && work) {
    imageEditorState.markNode.image(work);
    imageEditorState.markNode.width(work.width);
    imageEditorState.markNode.height(work.height);
  }
  updateImageEditorDisplayScale();
  updateImageEditorCropBox();
  updateImageEditorControls();
  renderImageEditorLayerList();
  stage?.batchDraw?.();
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
  const snapshot = imageEditorState.history[imageEditorState.historyIndex] || null;
  restoreImageEditorSnapshot(snapshot);
}

function redoImageEdit() {
  if (imageEditorState.historyIndex >= imageEditorState.history.length - 1) return;
  imageEditorState.historyIndex += 1;
  const snapshot = imageEditorState.history[imageEditorState.historyIndex] || null;
  restoreImageEditorSnapshot(snapshot);
}

function updateImageEditorControls() {
  const els = getEls();
  const canUndo = imageEditorState.historyIndex > 0;
  const canRedo = imageEditorState.historyIndex >= 0 && imageEditorState.historyIndex < imageEditorState.history.length - 1;
  const selectedLayer = selectedImageEditorLayer();
  if (els.imageEditorUndo) els.imageEditorUndo.disabled = !canUndo;
  if (els.imageEditorRedo) els.imageEditorRedo.disabled = !canRedo;
  if (els.imageEditorLayerUp) els.imageEditorLayerUp.disabled = !selectedLayer || imageEditorState.layers.indexOf(selectedLayer) >= imageEditorState.layers.length - 1;
  if (els.imageEditorLayerDown) els.imageEditorLayerDown.disabled = !selectedLayer || imageEditorState.layers.indexOf(selectedLayer) <= 0;
  if (els.imageEditorLayerDelete) els.imageEditorLayerDelete.disabled = !selectedLayer || imageEditorState.layers.length <= 1;
  if (els.imageEditorStrokeValue) els.imageEditorStrokeValue.textContent = `${imageEditorState.strokeWidth}px`;
  document.querySelectorAll<HTMLElement>("[data-image-editor-tool]").forEach((button) => {
    button.classList.toggle("active", button.dataset.imageEditorTool === imageEditorState.tool);
    button.setAttribute("aria-pressed", String(button.dataset.imageEditorTool === imageEditorState.tool));
  });
  document.querySelectorAll<HTMLElement>("[data-image-editor-color]").forEach((button) => {
    button.classList.toggle("active", button.dataset.imageEditorColor?.toLowerCase() === imageEditorState.color.toLowerCase());
  });
  document.querySelectorAll<HTMLElement>("[data-image-editor-canvas-scope]").forEach((button) => {
    button.classList.toggle("active", button.dataset.imageEditorCanvasScope === imageEditorState.canvasScope);
  });
  imageEditorState.layers.forEach((layer) => {
    layer.node?.draggable?.(imageEditorState.tool === "select");
  });
  const transformerNodes = imageEditorState.tool === "select" && selectedLayer ? [selectedLayer.node] : [];
  imageEditorState.konvaTransformer?.nodes?.(transformerNodes);
  imageEditorState.konvaTransformer?.moveToTop?.();
}

function imageEditorAvailableCanvasHeight(wrap: HTMLElement) {
  const maxHeight = Number.parseFloat(window.getComputedStyle(wrap).maxHeight || "");
  if (Number.isFinite(maxHeight) && maxHeight > 0) return maxHeight;
  return Math.min(window.innerHeight * 0.62, 640);
}

function updateImageEditorTransformerAffordance(displayScale: number) {
  const transformer = imageEditorState.konvaTransformer;
  if (!transformer) return;
  const safeScale = Math.max(0.1, displayScale || 1);
  transformer.anchorSize?.(Math.max(14, Math.round(14 / safeScale)));
  transformer.anchorStrokeWidth?.(Math.max(1, Math.round(1.5 / safeScale)));
  transformer.borderStrokeWidth?.(Math.max(1, Math.round(1 / safeScale)));
  transformer.rotateAnchorOffset?.(Math.max(28, Math.round(28 / safeScale)));
}

function updateImageEditorDisplayScale() {
  const els = getEls();
  const wrap = els.imageEditorCanvasWrap;
  const mount = els.imageEditorKonvaMount;
  const stage = imageEditorState.konvaStage;
  if (!wrap || !mount || !stage) return;
  const width = stage.width();
  const height = stage.height();
  if (!width || !height) return;

  const wrapRect = wrap.getBoundingClientRect();
  const availableWidth = Math.max(1, wrap.clientWidth || wrapRect.width || width);
  const availableHeight = Math.max(1, imageEditorAvailableCanvasHeight(wrap));
  const displayScale = Math.min(1, availableWidth / width, availableHeight / height);
  const displayWidth = Math.max(1, Math.round(width * displayScale));
  const displayHeight = Math.max(1, Math.round(height * displayScale));

  imageEditorState.displayScale = displayScale;
  updateImageEditorTransformerAffordance(displayScale);
  mount.style.width = `${displayWidth}px`;
  mount.style.height = `${displayHeight}px`;
  mount.style.setProperty("--image-editor-stage-width", `${displayWidth}px`);
  mount.style.setProperty("--image-editor-stage-height", `${displayHeight}px`);
  mount.style.setProperty("--image-editor-stage-raw-width", `${width}px`);
  mount.style.setProperty("--image-editor-stage-raw-height", `${height}px`);
  mount.style.setProperty("--image-editor-stage-scale", String(displayScale));
}

function updateImageEditorCropBox() {
  const els = getEls();
  const box = els.imageEditorCropBox;
  const wrap = els.imageEditorCanvasWrap;
  const stage = imageEditorState.konvaStage;
  const crop = imageEditorState.crop;
  if (!box || !wrap || !stage || !crop) {
    box?.classList.add("hidden");
    return;
  }
  const content = els.imageEditorKonvaMount?.querySelector(".konvajs-content") as HTMLElement | null;
  const rect = content?.getBoundingClientRect() || wrap.getBoundingClientRect();
  const wrapRect = wrap.getBoundingClientRect();
  const scaleX = rect.width / Math.max(1, stage.width());
  const scaleY = rect.height / Math.max(1, stage.height());
  box.style.left = `${rect.left - wrapRect.left + crop.left * scaleX}px`;
  box.style.top = `${rect.top - wrapRect.top + crop.top * scaleY}px`;
  box.style.width = `${crop.width * scaleX}px`;
  box.style.height = `${crop.height * scaleY}px`;
  box.classList.remove("hidden");
}

function imageEditorPoint(event: any) {
  const stage = imageEditorState.konvaStage;
  const canvas = getEls().imageEditorCanvas;
  const mount = getEls().imageEditorKonvaMount;
  const target = mount?.querySelector(".konvajs-content") || mount || canvas;
  const stageWidth = stage?.width?.() || canvas?.width || 0;
  const stageHeight = stage?.height?.() || canvas?.height || 0;
  if (target && typeof event?.clientX === "number" && typeof event?.clientY === "number") {
    const rect = target.getBoundingClientRect();
    const scaleX = stageWidth / Math.max(1, rect.width);
    const scaleY = stageHeight / Math.max(1, rect.height);
    return {
      x: Math.max(0, Math.min(stageWidth, (event.clientX - rect.left) * scaleX)),
      y: Math.max(0, Math.min(stageHeight, (event.clientY - rect.top) * scaleY)),
    };
  }
  if (stage && event && typeof event.clientX === "number" && typeof event.clientY === "number") {
    stage.setPointersPositions?.(event);
  }
  const pointer = stage?.getPointerPosition?.();
  if (pointer) {
    return {
      x: Math.max(0, Math.min(stageWidth || stage.width(), pointer.x)),
      y: Math.max(0, Math.min(stageHeight || stage.height(), pointer.y)),
    };
  }
  return {
    x: 0,
    y: 0,
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

function imageEditorArrowGeometry(start: any, end: any) {
  const strokeWidth = Math.max(1, Number(imageEditorState.strokeWidth) || 1);
  const dx = end.x - start.x;
  const dy = end.y - start.y;
  const length = Math.max(1, Math.hypot(dx, dy));
  const unitX = dx / length;
  const unitY = dy / length;
  const perpX = -unitY;
  const perpY = unitX;
  const headLength = Math.min(Math.max(16, strokeWidth * 2.8), Math.max(16, length * 0.55));
  const headWidth = Math.max(18, strokeWidth * 2.2);
  const overlap = Math.min(headLength * 0.42, Math.max(2, strokeWidth * 0.28));
  const shaftDistance = Math.max(0, headLength - overlap);
  const baseCenter = {
    x: end.x - unitX * headLength,
    y: end.y - unitY * headLength,
  };
  return {
    headLength,
    headWidth,
    shaftEnd: {
      x: end.x - unitX * shaftDistance,
      y: end.y - unitY * shaftDistance,
    },
    headLeft: {
      x: baseCenter.x + perpX * (headWidth / 2),
      y: baseCenter.y + perpY * (headWidth / 2),
    },
    headRight: {
      x: baseCenter.x - perpX * (headWidth / 2),
      y: baseCenter.y - perpY * (headWidth / 2),
    },
  };
}

function drawEditorArrowOnContext(ctx: any, start: any, end: any) {
  if (!ctx) return;
  configureImageEditorStroke(ctx, { lineCap: "butt", lineJoin: "miter" });
  const geometry = imageEditorArrowGeometry(start, end);
  ctx.beginPath();
  ctx.moveTo(start.x, start.y);
  ctx.lineTo(geometry.shaftEnd.x, geometry.shaftEnd.y);
  ctx.stroke();
  ctx.beginPath();
  ctx.moveTo(end.x, end.y);
  ctx.lineTo(geometry.headLeft.x, geometry.headLeft.y);
  ctx.lineTo(geometry.headRight.x, geometry.headRight.y);
  ctx.closePath();
  ctx.fill();
}

function clearImageEditorPreview() {
  imageEditorState.previewNode?.destroy?.();
  imageEditorState.previewNode = null;
  imageEditorState.konvaLayer?.batchDraw?.();
}

function previewEditorArrow(start: any, end: any) {
  if (!imageEditorState.konvaLayer) return;
  const points = [start.x, start.y, end.x, end.y];
  const geometry = imageEditorArrowGeometry(start, end);
  if (!imageEditorState.previewNode) {
    imageEditorState.previewNode = new Konva.Arrow({
      points,
      stroke: imageEditorState.color,
      fill: imageEditorState.color,
      strokeWidth: imageEditorState.strokeWidth,
      pointerLength: geometry.headLength,
      pointerWidth: geometry.headWidth,
      lineCap: "butt",
      lineJoin: "miter",
      listening: false,
      name: "image-editor-preview-arrow",
    });
    imageEditorState.konvaLayer.add(imageEditorState.previewNode);
  } else {
    imageEditorState.previewNode.points(points);
    imageEditorState.previewNode.stroke(imageEditorState.color);
    imageEditorState.previewNode.fill(imageEditorState.color);
    imageEditorState.previewNode.strokeWidth(imageEditorState.strokeWidth);
    imageEditorState.previewNode.pointerLength(geometry.headLength);
    imageEditorState.previewNode.pointerWidth(geometry.headWidth);
  }
  imageEditorState.previewNode.moveToTop?.();
  imageEditorState.konvaLayer.batchDraw?.();
}

function selectedImageEditorLayer() {
  return imageEditorState.layers.find((layer) => layer.id === imageEditorState.selectedLayerId) || null;
}

function imageEditorLayerLocalPoint(layer: ImageEditorLayer, point: any) {
  const transform = layer.node.getAbsoluteTransform().copy();
  transform.invert();
  return transform.point(point);
}

function imageEditorLayerCanvasPoint(layer: ImageEditorLayer, point: any) {
  const local = imageEditorLayerLocalPoint(layer, point);
  const widthScale = layer.canvas.width / Math.max(1, layer.node.width());
  const heightScale = layer.canvas.height / Math.max(1, layer.node.height());
  return {
    x: local.x * widthScale,
    y: local.y * heightScale,
  };
}

function imageEditorLayerCanvasStrokeWidth(layer: ImageEditorLayer) {
  const widthScale = layer.canvas.width / Math.max(1, layer.node.width());
  const heightScale = layer.canvas.height / Math.max(1, layer.node.height());
  return Math.max(1, imageEditorState.strokeWidth * ((widthScale + heightScale) / 2));
}

function applyImageEditorLayerEraseSegment(layer: ImageEditorLayer, from: any, to: any) {
  const ctx = layer.canvas.getContext("2d");
  if (!ctx) return false;
  const start = imageEditorLayerCanvasPoint(layer, from);
  const end = imageEditorLayerCanvasPoint(layer, to);
  ctx.save();
  ctx.globalCompositeOperation = "destination-out";
  ctx.lineWidth = imageEditorLayerCanvasStrokeWidth(layer);
  ctx.lineCap = "round";
  ctx.lineJoin = "round";
  ctx.beginPath();
  ctx.moveTo(start.x, start.y);
  ctx.lineTo(end.x, end.y);
  ctx.stroke();
  ctx.restore();
  layer.edited = true;
  layer.node.image(layer.canvas);
  layer.node.getLayer()?.batchDraw?.();
  return true;
}

function applyImageEditorLayerEraseDot(layer: ImageEditorLayer, point: any) {
  const ctx = layer.canvas.getContext("2d");
  if (!ctx) return false;
  const local = imageEditorLayerCanvasPoint(layer, point);
  ctx.save();
  ctx.globalCompositeOperation = "destination-out";
  ctx.beginPath();
  ctx.arc(local.x, local.y, imageEditorLayerCanvasStrokeWidth(layer) / 2, 0, Math.PI * 2);
  ctx.fill();
  ctx.restore();
  layer.edited = true;
  layer.node.image(layer.canvas);
  layer.node.getLayer()?.batchDraw?.();
  return true;
}

function applyImageEditorLayerEraseStroke(layer: ImageEditorLayer, points: any[]) {
  if (!layer || points.length < 2) return false;
  let changed = false;
  for (let index = 1; index < points.length; index += 1) {
    changed = applyImageEditorLayerEraseSegment(layer, points[index - 1], points[index]) || changed;
  }
  return changed;
}

function handleImageEditorPointerDown(event: any) {
  if (!imageEditorState.konvaStage) return;
  if (imageEditorState.tool === "select") return;
  event.preventDefault?.();
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
  if (imageEditorState.tool === "eraser") {
    const layer = selectedImageEditorLayer();
    if (!layer) {
      setImageEditorStatus(translate("imageEditor.selectLayerFirst"), "error");
      return;
    }
    const captureTarget = captureImageEditorPointer(event);
    const changed = applyImageEditorLayerEraseDot(layer, point);
    imageEditorState.drawing = {
      pointerId: event.pointerId,
      captureTarget,
      layerId: layer.id,
      start: point,
      last: point,
      points: [point],
      changed,
    };
    return;
  }
  const captureTarget = captureImageEditorPointer(event);
  imageEditorState.drawing = {
    pointerId: event.pointerId,
    captureTarget,
    start: point,
    last: point,
    points: [point],
  };
  if (imageEditorState.tool === "crop") {
    imageEditorState.crop = { left: point.x, top: point.y, width: 0, height: 0 };
    updateImageEditorCropBox();
  }
}

function handleImageEditorPointerMove(event: any) {
  const drawing = imageEditorState.drawing;
  if (!drawing) return;
  if (drawing.pointerId !== undefined && event.pointerId !== undefined && drawing.pointerId !== event.pointerId) return;
  event.preventDefault?.();
  const point = imageEditorPoint(event);
  if (imageEditorState.tool === "eraser") {
    const layer = selectedImageEditorLayer();
    if (layer && layer.id === drawing.layerId) {
      drawing.changed = applyImageEditorLayerEraseSegment(layer, drawing.last, point) || drawing.changed;
    }
    drawing.points.push(point);
    drawing.last = point;
    return;
  }
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
  if (!drawing) return;
  if (drawing.pointerId !== undefined && event.pointerId !== undefined && drawing.pointerId !== event.pointerId) return;
  event.preventDefault?.();
  const point = imageEditorPoint(event);
  releaseImageEditorPointer(event, drawing.captureTarget);
  if (imageEditorState.tool === "eraser") {
    drawing.points.push(point);
    const layer = selectedImageEditorLayer();
    if (
      layer
      && layer.id === drawing.layerId
      && imageEditorPointDistance(drawing.last, point) > 0
    ) {
      drawing.changed = applyImageEditorLayerEraseSegment(layer, drawing.last, point) || drawing.changed;
    }
    if (drawing.changed) {
      pushImageEditorHistory();
      setImageEditorStatus("");
    }
  } else if (imageEditorState.tool === "arrow") {
    const ctx = imageEditorContext();
    if (ctx && isImageEditorLineGesture(drawing.start, point)) {
      drawEditorArrowOnContext(ctx, drawing.start, point);
      imageEditorState.hasInstructionMarks = true;
      pushImageEditorHistory();
    }
    clearImageEditorPreview();
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
  if (!drawing) return;
  if (drawing.pointerId !== undefined && event.pointerId !== undefined && drawing.pointerId !== event.pointerId) return;
  releaseImageEditorPointer(event, drawing.captureTarget);
  if (imageEditorState.tool === "brush") {
    pushImageEditorHistory();
  } else if (imageEditorState.tool === "eraser") {
    if (drawing.changed) pushImageEditorHistory();
  } else if (imageEditorState.tool === "arrow") {
    clearImageEditorPreview();
  } else if (imageEditorState.tool === "crop") {
    imageEditorState.crop = null;
  }
  imageEditorState.drawing = null;
  renderImageEditor();
}

function captureImageEditorPointer(event: any) {
  if (event?.pointerId === undefined) return null;
  const target = event.currentTarget || event.target || imageEditorState.konvaStage?.container?.();
  try {
    target?.setPointerCapture?.(event.pointerId);
    return target || null;
  } catch {
    return null;
  }
}

function releaseImageEditorPointer(event: any, target: any) {
  if (event?.pointerId === undefined || !target) return;
  try {
    target.releasePointerCapture?.(event.pointerId);
  } catch {
    // Pointer capture is best-effort; missing capture should not cancel the edit.
  }
}

function imageEditorCompositeCanvas() {
  const stage = imageEditorState.konvaStage;
  if (!stage) return null;
  const crop = imageEditorState.crop;
  const wasTransformerVisible = imageEditorState.konvaTransformer?.visible?.();
  imageEditorState.konvaTransformer?.visible?.(false);
  imageEditorState.konvaLayer?.batchDraw?.();
  const config = crop
    ? {
      x: crop.left,
      y: crop.top,
      width: Math.max(1, Math.round(crop.width)),
      height: Math.max(1, Math.round(crop.height)),
      pixelRatio: 1,
    }
    : { pixelRatio: 1 };
  const canvas = stage.toCanvas(config);
  imageEditorState.konvaTransformer?.visible?.(wasTransformerVisible !== false);
  imageEditorState.konvaLayer?.batchDraw?.();
  return canvas;
}

function imageEditorCanvasForSave() {
  if (imageEditorState.canvasScope === "fit") {
    fitImageEditorCanvasToLayers({ preserveCurrent: true });
  }
  return imageEditorCompositeCanvas();
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
      originalFile: file,
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
    closeImageEditor(true);
    legacyMethod("setStatus", translate("imageEditor.saved"), "ok");
  } catch (error: any) {
    setImageEditorStatus(error.message || translate("imageEditor.saveFailed"), "error");
  } finally {
    if (els.imageEditorSave) els.imageEditorSave.disabled = false;
  }
}

function sourcePreviewUrlForEditor(source: any) {
  if (!source) return "";
  if (source.kind === "upload") return source.previewUrl || "";
  return legacyMethod("sourcePreviewUrl", source) || "";
}

function renderImageEditorInsertList() {
  const state = getState();
  const list = getEls().imageEditorInsertList;
  if (!list) return;
  list.textContent = "";
  const sources = state.images
    .map((source: any, index: number) => ({ source, index }))
    .filter((item: any) => item.index !== imageEditorState.sourceIndex && isEditableImageSource(item.source));
  if (!sources.length) {
    const empty = document.createElement("div");
    empty.className = "image-editor-insert-empty";
    empty.textContent = translate("imageEditor.emptyInsertList");
    list.append(empty);
    return;
  }
  sources.forEach(({ source, index }: any) => {
    const row = document.createElement("button");
    row.type = "button";
    row.className = "image-editor-insert-item";
    row.dataset.sourceIndex = String(index);
    const thumbUrl = sourcePreviewUrlForEditor(source);
    if (thumbUrl) {
      const img = document.createElement("img");
      img.src = thumbUrl;
      img.alt = "";
      img.loading = "lazy";
      row.append(img);
    } else {
      const placeholder = document.createElement("span");
      placeholder.className = "image-editor-layer-thumb";
      placeholder.textContent = "IMG";
      row.append(placeholder);
    }
    const text = document.createElement("span");
    text.className = "image-editor-insert-name";
    text.textContent = legacyMethod("sourceName", source) || imageEditorSourceName(source);
    row.append(text);
    row.addEventListener("click", () => insertImageEditorLayerFromSource(source));
    list.append(row);
  });
}

function imageEditorLayerThumbnailUrl(layer: ImageEditorLayer) {
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

function renderImageEditorLayerList() {
  const list = getEls().imageEditorLayerList;
  if (!list) return;
  list.textContent = "";
  [...imageEditorState.layers].reverse().forEach((layer) => {
    const row = document.createElement("button");
    row.type = "button";
    row.className = "image-editor-layer-item";
    row.classList.toggle("active", layer.id === imageEditorState.selectedLayerId);
    row.dataset.layerId = layer.id;
    const thumb = document.createElement("span");
    thumb.className = "image-editor-layer-thumb";
    const thumbnailUrl = imageEditorLayerThumbnailUrl(layer);
    if (thumbnailUrl) {
      const thumbnail = document.createElement("img");
      thumbnail.src = thumbnailUrl;
      thumbnail.alt = "";
      thumbnail.decoding = "async";
      thumbnail.draggable = false;
      thumb.append(thumbnail);
    } else {
      thumb.textContent = String(imageEditorState.layers.indexOf(layer) + 1);
    }
    row.append(thumb);
    const content = document.createElement("span");
    const name = document.createElement("span");
    name.className = "image-editor-layer-name";
    name.textContent = layer.name || translate("imageEditor.baseLayer");
    const meta = document.createElement("span");
    meta.className = "image-editor-layer-meta";
    const width = Math.max(1, Math.round(layer.node.width() * layer.node.scaleX()));
    const height = Math.max(1, Math.round(layer.node.height() * layer.node.scaleY()));
    meta.textContent = `${width}×${height}`;
    content.append(name, meta);
    row.append(content);
    row.addEventListener("click", () => selectImageEditorLayer(layer.id, { updateTool: true }));
    list.append(row);
  });
  updateImageEditorControls();
}

async function insertImageEditorLayerFromSource(source: any) {
  const sessionId = imageEditorState.sessionId;
  if (!imageEditorState.konvaStage || !isEditableImageSource(source)) return;
  try {
    const file = await imageEditorSourceFile(source);
    if (sessionId !== imageEditorState.sessionId) return;
    const image = await loadImageEditorImage(file);
    if (sessionId !== imageEditorState.sessionId) return;
    const canvas = imageEditorCanvasFromImage(image);
    const sourceIndex = getState().images.indexOf(source);
    const layer = createImageEditorLayerFromCanvas(canvas, {
      source,
      sourceIndex,
      name: legacyMethod("sourceName", source) || imageEditorSourceName(source),
      edited: false,
    });
    imageEditorState.layers.push(layer);
    if (imageEditorState.canvasScope === "fit") {
      fitImageEditorCanvasToLayers({ preserveCurrent: true });
    }
    orderImageEditorKonvaNodes();
    selectImageEditorLayer(layer.id, { updateTool: true });
    pushImageEditorHistory();
    renderImageEditor();
  } catch (error: any) {
    setImageEditorStatus(error.message || translate("imageEditor.loadForEditFailed"), "error");
  }
}

function selectImageEditorLayer(layerId: string | null, options: any = {}) {
  imageEditorState.selectedLayerId = layerId;
  const layer = selectedImageEditorLayer();
  if (options.updateTool && layer) {
    imageEditorState.tool = "select";
  }
  imageEditorState.konvaTransformer?.nodes?.(imageEditorState.tool === "select" && layer ? [layer.node] : []);
  imageEditorState.konvaTransformer?.moveToTop?.();
  imageEditorState.konvaLayer?.batchDraw?.();
  renderImageEditorLayerList();
  updateImageEditorControls();
}

function moveImageEditorLayer(direction: any) {
  const layer = selectedImageEditorLayer();
  if (!layer) return;
  const index = imageEditorState.layers.indexOf(layer);
  const nextIndex = direction === "up" ? index + 1 : index - 1;
  if (nextIndex < 0 || nextIndex >= imageEditorState.layers.length) return;
  imageEditorState.layers.splice(index, 1);
  imageEditorState.layers.splice(nextIndex, 0, layer);
  orderImageEditorKonvaNodes();
  pushImageEditorHistory();
  renderImageEditorLayerList();
}

function deleteSelectedImageEditorLayer() {
  const layer = selectedImageEditorLayer();
  if (!layer || imageEditorState.layers.length <= 1) return;
  const index = imageEditorState.layers.indexOf(layer);
  imageEditorState.layers = imageEditorState.layers.filter((item) => item !== layer);
  layer.node?.destroy?.();
  const next = imageEditorState.layers[Math.min(index, imageEditorState.layers.length - 1)] || imageEditorState.layers[0] || null;
  imageEditorState.selectedLayerId = next?.id || null;
  orderImageEditorKonvaNodes();
  selectImageEditorLayer(imageEditorState.selectedLayerId, { updateTool: false });
  pushImageEditorHistory();
  renderImageEditor();
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
  imageEditorState.canvasScope = "base";
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

function closeImageEditor(force = false) {
  const els = getEls();
  if (force !== true && (imageEditorState.historyIndex > 0 || Boolean(imageEditorState.crop?.width && imageEditorState.crop?.height))) {
    legacyMethod("openConfirmPopover", els.imageEditorClose, {
      title: translate("ux.discardEdits"),
      focusCancel: true,
      message: translate("ux.imageUnsaved"),
      confirmText: translate("ux.discardEdits"),
      onConfirm: () => closeImageEditor(true),
    });
    return;
  }
  nextImageEditorSession();
  els.imageEditorModal?.classList.add("hidden");
  destroyImageEditorKonva();
  imageEditorState.sourceIndex = null;
  imageEditorState.source = null;
  imageEditorState.originalFile = null;
  imageEditorState.image = null;
  imageEditorState.baseCanvas = null;
  imageEditorState.workCanvas = null;
  imageEditorState.brushBoundaryCanvas = null;
  imageEditorState.brushOverlayCanvas = null;
  imageEditorState.layers = [];
  imageEditorState.selectedLayerId = null;
  imageEditorState.crop = null;
  imageEditorState.hasInstructionMarks = false;
  imageEditorState.history = [];
  imageEditorState.historyIndex = -1;
  imageEditorState.drawing = null;
  imageEditorState.canvasScope = "base";
  setImageEditorStatus("");
  renderImageEditorInsertList();
  renderImageEditorLayerList();
  updateImageEditorControls();
}

function setImageEditorTool(tool: any) {
  if (!["select", "brush", "arrow", "crop", "fill", "eraser"].includes(tool)) return;
  imageEditorState.tool = tool;
  imageEditorState.drawing = null;
  clearImageEditorPreview();
  updateImageEditorControls();
  imageEditorState.konvaLayer?.batchDraw?.();
}

function setImageEditorCanvasScope(scope: any) {
  if (!["base", "fit"].includes(scope)) return;
  if (!imageEditorState.konvaStage) return;
  if (scope === imageEditorState.canvasScope) return;
  imageEditorState.canvasScope = scope;
  if (scope === "fit") {
    fitImageEditorCanvasToLayers({ preserveCurrent: false, pushHistory: true, status: true });
  } else {
    resetImageEditorCanvasToBase({ pushHistory: true, status: true });
  }
  renderImageEditor();
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
    imageEditorState.tool = "crop";
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

function bindImageEditorStageEvents(stage: any) {
  const hasPointerEvents = typeof window !== "undefined" && "PointerEvent" in window;
  const downEvents = hasPointerEvents ? "pointerdown" : "mousedown touchstart";
  const moveEvents = hasPointerEvents ? "pointermove" : "mousemove touchmove";
  const upEvents = hasPointerEvents ? "pointerup pointercancel" : "mouseup touchend";
  stage.on(downEvents, (event: any) => {
    if (imageEditorState.tool === "select") {
      if (isImageEditorTransformerTarget(event.target)) return;
      if (event.target === stage) selectImageEditorLayer(null, { updateTool: false });
      return;
    }
    handleImageEditorPointerDown(event.evt || event);
  });
  stage.on(moveEvents, (event: any) => handleImageEditorPointerMove(event.evt || event));
  stage.on(upEvents, (event: any) => {
    if (event.type === "pointercancel") {
      handleImageEditorPointerCancel(event.evt || event);
      return;
    }
    handleImageEditorPointerUp(event.evt || event);
  });
}

function bindImageEditorEvents() {
  const els = getEls();
  els.imageEditorClose?.addEventListener("click", () => closeImageEditor());
  els.imageEditorCancel?.addEventListener("click", () => closeImageEditor());
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
  document.querySelectorAll<HTMLElement>("[data-image-editor-canvas-scope]").forEach((button) => {
    button.addEventListener("click", () => setImageEditorCanvasScope(button.dataset.imageEditorCanvasScope));
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
  els.imageEditorLayerUp?.addEventListener("click", () => moveImageEditorLayer("up"));
  els.imageEditorLayerDown?.addEventListener("click", () => moveImageEditorLayer("down"));
  els.imageEditorLayerDelete?.addEventListener("click", deleteSelectedImageEditorLayer);
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

import Konva from "konva";
import { captureImageEditorCanvas, rememberImageEditorCanvasSnapshot } from "./image-editor-canvas";
import { editedUploadFilename, imageEditorCanvasFromImage, imageEditorCanvasSnapshot, imageEditorClampedCanvasDimensions, imageEditorExportBlob, imageEditorExportDimensions, imageEditorLayerAttrs, loadImageEditorImage, resizeImageEditorBackingCanvas } from "./image-editor-canvas";
import { createImageEditorDrawing } from "./image-editor-drawing";
import { createImageEditorFill } from "./image-editor-fill-client";
import { createImageEditorHistory } from "./image-editor-history";
import { createImageEditorPanel } from "./image-editor-panel";
import { createImageEditorPointer } from "./image-editor-pointer";

import { getEls } from "./dom";
import { translate } from "./i18n";
import type {
  ImageEditorLayer,
  ImageEditorLayerSnapshot,
  ImageEditorSnapshot,
  ImageEditorState,
} from "./image-editor-types";
import { getLegacyBridge, getState } from "./state";

const IMAGE_EDITOR_PROMPT_HINT_LEGACY = "\u56fe\u4e2d\u7684\u624b\u7ed8\u7bad\u5934\u548c\u6807\u8bb0\u4ec5\u7528\u4e8e\u6307\u793a\u7f16\u8f91\u8981\u6c42\uff0c\u4e0d\u8981\u4fdd\u7559\u5728\u6700\u7ec8\u753b\u9762\u4e2d\u3002";
const IMAGE_EDITOR_LAYER_FIT_RATIO = 0.72;

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
  layers: [],
  selectedLayerId: null,
  displayScale: 1,
  tool: "crop",
  color: "#ff3b30",
  strokeWidth: 8,
  crop: null,
  canvasScope: "base",
  hasInstructionMarks: false,
} as ImageEditorState;

let imageEditorFeatureInitialized = false;
let imageEditorLayerSequence = 0;
const editorFill = createImageEditorFill();
let pendingFill: Promise<boolean | null> | null = null;

const editorHistory = createImageEditorHistory<ImageEditorSnapshot>({
  capture: () => { editorFill.cancel(); return imageEditorSnapshot(); },
  restore: snapshot => { editorFill.cancel(); restoreImageEditorSnapshot(snapshot); },
  changed: () => updateImageEditorControls(),
  resources: snapshot => [
    ...snapshot.layers.map(layer => layer.canvas), snapshot.workCanvas,
    snapshot.brushBoundaryCanvas, snapshot.brushOverlayCanvas,
  ].filter((canvas): canvas is HTMLCanvasElement => Boolean(canvas)),
});
const { pushImageEditorHistory } = editorHistory;
function undoImageEdit() { editorFill.cancel(); editorHistory.undoImageEdit(); }
function redoImageEdit() { editorFill.cancel(); editorHistory.redoImageEdit(); }

function paintBucketFillRegion(point: { x: number; y: number }): Promise<boolean | null> {
  const { workCanvas, brushBoundaryCanvas, color } = imageEditorState;
  if (!workCanvas || !brushBoundaryCanvas) return Promise.resolve(false);
  const pending = editorFill.fill(point, workCanvas, brushBoundaryCanvas, color, redrawImageEditorBrushOverlay)
    .finally(() => { if (pendingFill === pending) pendingFill = null; });
  pendingFill = pending;
  return pending;
}

const editorPointer = createImageEditorPointer({
  getTool: () => imageEditorState.tool,
  cancelPendingFill: () => editorFill.cancel(),
  hasStage: () => Boolean(imageEditorState.konvaStage),
  getStageContainer: () => imageEditorState.konvaStage?.container?.() || null,
  markInstruction: () => { imageEditorState.hasInstructionMarks = true; },
  setCrop: crop => { imageEditorState.crop = crop; },
  imageEditorPoint: (...args: Parameters<typeof imageEditorPoint>) => imageEditorPoint(...args),
  paintBucketFillRegion: (...args: Parameters<typeof paintBucketFillRegion>) => paintBucketFillRegion(...args),
  pushImageEditorHistory: (...args: Parameters<typeof pushImageEditorHistory>) => pushImageEditorHistory(...args),
  setImageEditorStatus: (...args: Parameters<typeof setImageEditorStatus>) => setImageEditorStatus(...args),
  renderImageEditor: (...args: Parameters<typeof renderImageEditor>) => renderImageEditor(...args),
  selectedImageEditorLayer: (...args: Parameters<typeof selectedImageEditorLayer>) => selectedImageEditorLayer(...args),
  applyImageEditorLayerEraseDot: (...args: Parameters<typeof applyImageEditorLayerEraseDot>) => applyImageEditorLayerEraseDot(...args),
  applyImageEditorLayerEraseSegment: (...args: Parameters<typeof applyImageEditorLayerEraseSegment>) => applyImageEditorLayerEraseSegment(...args),
  updateImageEditorCropBox: (...args: Parameters<typeof updateImageEditorCropBox>) => updateImageEditorCropBox(...args),
  previewEditorArrow: (...args: Parameters<typeof previewEditorArrow>) => previewEditorArrow(...args),
  drawEditorBrushSegment: (...args: Parameters<typeof drawEditorBrushSegment>) => drawEditorBrushSegment(...args),
  imageEditorContext: (...args: Parameters<typeof imageEditorContext>) => imageEditorContext(...args),
  drawEditorArrowOnContext: (...args: Parameters<typeof drawEditorArrowOnContext>) => drawEditorArrowOnContext(...args),
  clearImageEditorPreview: (...args: Parameters<typeof clearImageEditorPreview>) => clearImageEditorPreview(...args),
});
const { handleImageEditorPointerDown, handleImageEditorPointerMove, handleImageEditorPointerUp, handleImageEditorPointerCancel, captureImageEditorPointer, releaseImageEditorPointer } = editorPointer;

const { renderImageEditorInsertList, renderImageEditorLayerList } = createImageEditorPanel({
  getSources: () => getState().images,
  getEditorSnapshot: () => ({ sourceIndex: imageEditorState.sourceIndex, layers: imageEditorState.layers, selectedLayerId: imageEditorState.selectedLayerId }),
  getPanelElements: () => ({ imageEditorInsertList: getEls().imageEditorInsertList, imageEditorLayerList: getEls().imageEditorLayerList }),
  isEditableImageSource: (...args: Parameters<typeof isEditableImageSource>) => isEditableImageSource(...args),
  sourcePreviewUrlForEditor: (...args: Parameters<typeof sourcePreviewUrlForEditor>) => sourcePreviewUrlForEditor(...args),
  sourceName: source => legacyMethod("sourceName", source),
  imageEditorSourceName: (...args: Parameters<typeof imageEditorSourceName>) => imageEditorSourceName(...args),
  insertImageEditorLayerFromSource: (...args: Parameters<typeof insertImageEditorLayerFromSource>) => insertImageEditorLayerFromSource(...args),
  selectImageEditorLayer: (...args: Parameters<typeof selectImageEditorLayer>) => selectImageEditorLayer(...args),
  updateImageEditorControls: (...args: Parameters<typeof updateImageEditorControls>) => updateImageEditorControls(...args),
});

const editorDrawing = createImageEditorDrawing({
  getBrushSettings: () => ({ color: imageEditorState.color, strokeWidth: imageEditorState.strokeWidth }),
  getOverlayCanvas: () => imageEditorState.brushOverlayCanvas,
  getKonvaLayer: () => imageEditorState.konvaLayer,
  imageEditorBrushBoundaryContext: (...args: Parameters<typeof imageEditorBrushBoundaryContext>) => imageEditorBrushBoundaryContext(...args),
  imageEditorBrushOverlayContext: (...args: Parameters<typeof imageEditorBrushOverlayContext>) => imageEditorBrushOverlayContext(...args),
  imageEditorContext: (...args: Parameters<typeof imageEditorContext>) => imageEditorContext(...args),
});
const { configureImageEditorStroke, drawEditorBrushBoundarySegment, drawEditorBrushOverlaySegment, redrawImageEditorBrushOverlay, drawEditorBrushSegment, drawEditorArrowOnContext, clearImageEditorPreview, previewEditorArrow, imageEditorLayerLocalPoint, imageEditorLayerCanvasPoint, imageEditorLayerCanvasStrokeWidth, applyImageEditorLayerEraseSegment, applyImageEditorLayerEraseDot, applyImageEditorLayerEraseStroke } = editorDrawing;

function legacyMethod(name: string, ...args: any[]) {
  return getLegacyBridge().methods[name]?.(...args);
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

function imageEditorSnapshot(): ImageEditorSnapshot | null {
  if (!imageEditorState.workCanvas) return null;
  return {
    layers: imageEditorState.layers.map((layer) => ({
      id: layer.id,
      sourceIndex: layer.sourceIndex,
      name: layer.name,
      canvas: captureImageEditorCanvas(layer.canvas),
      attrs: imageEditorLayerAttrs(layer.node),
      edited: layer.edited,
    })),
    workCanvas: captureImageEditorCanvas(imageEditorState.workCanvas),
    brushBoundaryCanvas: imageEditorState.brushBoundaryCanvas ? captureImageEditorCanvas(imageEditorState.brushBoundaryCanvas) : null,
    brushOverlayCanvas: imageEditorState.brushOverlayCanvas ? captureImageEditorCanvas(imageEditorState.brushOverlayCanvas) : null,
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
  rememberImageEditorCanvasSnapshot(canvas, snapshot);
}

function rebuildImageEditorLayers(snapshots: ImageEditorLayerSnapshot[]) {
  const konvaLayer = imageEditorState.konvaLayer;
  if (!konvaLayer) return;
  imageEditorState.layers.forEach((layer) => layer.node?.destroy?.());
  imageEditorState.layers = [];
  snapshots.forEach((snapshot) => {
    const canvas = imageEditorCanvasSnapshot(snapshot.canvas);
    if (!canvas) throw new Error(translate("imageEditor.canvasCreateFailed"));
    rememberImageEditorCanvasSnapshot(canvas, snapshot.canvas);
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

function imageEditorBaseDimensions() {
  const baseCanvas = imageEditorState.baseCanvas;
  return {
    width: Math.max(1, Math.round(baseCanvas?.width || imageEditorState.konvaStage?.width?.() || 1)),
    height: Math.max(1, Math.round(baseCanvas?.height || imageEditorState.konvaStage?.height?.() || 1)),
  };
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
  editorDrawing.promotePreview();
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
  editorDrawing.resetPreview();
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
  editorFill.cancel();
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
  editorHistory.reset();
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

function updateImageEditorControls() {
  const els = getEls();
  const canUndo = editorHistory.canUndo();
  const canRedo = editorHistory.canRedo();
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

function selectedImageEditorLayer() {
  return imageEditorState.layers.find((layer) => layer.id === imageEditorState.selectedLayerId) || null;
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
  if (pendingFill) {
    try { if (await pendingFill === null) return; }
    catch { setImageEditorStatus(translate("imageEditor.saveFailed"), "error"); return; }
    if (sessionId !== imageEditorState.sessionId || imageEditorState.source !== source) return;
  }
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
  editorPointer.clearDrawing();
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
  if (force !== true && (editorHistory.canUndo() || Boolean(imageEditorState.crop?.width && imageEditorState.crop?.height))) {
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
  editorHistory.reset();
  editorPointer.clearDrawing();
  imageEditorState.canvasScope = "base";
  setImageEditorStatus("");
  renderImageEditorInsertList();
  renderImageEditorLayerList();
  updateImageEditorControls();
}

function setImageEditorTool(tool: any) {
  if (!["select", "brush", "arrow", "crop", "fill", "eraser"].includes(tool)) return;
  imageEditorState.tool = tool;
  editorPointer.clearDrawing();
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
  editorFill.cancel();
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

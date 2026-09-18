import Konva from "konva";
import { markImageEditorCanvasChanged } from "./image-editor-canvas";
import { imageEditorArrowGeometry } from "./image-editor-geometry";
import type { ImageEditorLayer } from "./image-editor-types";

export interface ImageEditorDrawingDependencies {
  getBrushSettings: () => { color: string; strokeWidth: number };
  getOverlayCanvas: () => HTMLCanvasElement | null;
  getKonvaLayer: () => Konva.Layer | null;
  imageEditorBrushBoundaryContext: () => CanvasRenderingContext2D | null;
  imageEditorBrushOverlayContext: () => CanvasRenderingContext2D | null;
  imageEditorContext: () => CanvasRenderingContext2D | null;
}

export function createImageEditorDrawing(dependencies: ImageEditorDrawingDependencies) {
  const { getBrushSettings, getOverlayCanvas, getKonvaLayer, imageEditorBrushBoundaryContext, imageEditorBrushOverlayContext, imageEditorContext } = dependencies;
  let previewNode: Konva.Arrow | null = null;
  function configureImageEditorStroke(ctx: any, options: any = {}) {
    if (!ctx) return;
    ctx.strokeStyle = getBrushSettings().color;
    ctx.fillStyle = getBrushSettings().color;
    ctx.lineWidth = getBrushSettings().strokeWidth;
    ctx.lineCap = options.lineCap || "round";
    ctx.lineJoin = options.lineJoin || "round";
    ctx.miterLimit = options.miterLimit || 10;
  }

  function drawEditorBrushBoundarySegment(from: any, to: any) {
    const ctx = imageEditorBrushBoundaryContext();
    if (!ctx) return;
    ctx.strokeStyle = "#000";
    ctx.fillStyle = "#000";
    ctx.lineWidth = getBrushSettings().strokeWidth;
    ctx.lineCap = "round";
    ctx.lineJoin = "round";
    ctx.beginPath();
    ctx.moveTo(from.x, from.y);
    ctx.lineTo(to.x, to.y);
    ctx.stroke();
    markImageEditorCanvasChanged(ctx.canvas);
  }

  function drawEditorBrushOverlaySegment(from: any, to: any) {
    const ctx = imageEditorBrushOverlayContext();
    if (!ctx) return;
    configureImageEditorStroke(ctx);
    ctx.beginPath();
    ctx.moveTo(from.x, from.y);
    ctx.lineTo(to.x, to.y);
    ctx.stroke();
    markImageEditorCanvasChanged(ctx.canvas);
  }

  function redrawImageEditorBrushOverlay(ctx: any) {
    if (!ctx || !getOverlayCanvas()) return;
    ctx.drawImage(getOverlayCanvas(), 0, 0);
  }

  function drawEditorBrushSegment(from: any, to: any) {
    const ctx = imageEditorContext();
    if (!ctx) return;
    configureImageEditorStroke(ctx);
    ctx.beginPath();
    ctx.moveTo(from.x, from.y);
    ctx.lineTo(to.x, to.y);
    ctx.stroke();
    markImageEditorCanvasChanged(ctx.canvas);
    drawEditorBrushBoundarySegment(from, to);
    drawEditorBrushOverlaySegment(from, to);
  }

  function drawEditorArrowOnContext(ctx: any, start: any, end: any) {
    if (!ctx) return;
    configureImageEditorStroke(ctx, { lineCap: "butt", lineJoin: "miter" });
    const geometry = imageEditorArrowGeometry(start, end, getBrushSettings().strokeWidth);
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
    markImageEditorCanvasChanged(ctx.canvas);
  }

  function clearImageEditorPreview() {
    previewNode?.destroy?.();
    previewNode = null;
    getKonvaLayer()?.batchDraw?.();
  }

  function previewEditorArrow(start: any, end: any) {
    const layer = getKonvaLayer();
    if (!layer) return;
    const points = [start.x, start.y, end.x, end.y];
    const geometry = imageEditorArrowGeometry(start, end, getBrushSettings().strokeWidth);
    if (!previewNode) {
      previewNode = new Konva.Arrow({
        points,
        stroke: getBrushSettings().color,
        fill: getBrushSettings().color,
        strokeWidth: getBrushSettings().strokeWidth,
        pointerLength: geometry.headLength,
        pointerWidth: geometry.headWidth,
        lineCap: "butt",
        lineJoin: "miter",
        listening: false,
        name: "image-editor-preview-arrow",
      });
      layer.add(previewNode);
    } else {
      previewNode.points(points);
      previewNode.stroke(getBrushSettings().color);
      previewNode.fill(getBrushSettings().color);
      previewNode.strokeWidth(getBrushSettings().strokeWidth);
      previewNode.pointerLength(geometry.headLength);
      previewNode.pointerWidth(geometry.headWidth);
    }
    previewNode.moveToTop?.();
    layer.batchDraw?.();
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
    return Math.max(1, getBrushSettings().strokeWidth * ((widthScale + heightScale) / 2));
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
    markImageEditorCanvasChanged(layer.canvas);
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
    markImageEditorCanvasChanged(layer.canvas);
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
  return { configureImageEditorStroke, drawEditorBrushBoundarySegment, drawEditorBrushOverlaySegment, redrawImageEditorBrushOverlay, drawEditorBrushSegment, drawEditorArrowOnContext, clearImageEditorPreview, previewEditorArrow, imageEditorLayerLocalPoint, imageEditorLayerCanvasPoint, imageEditorLayerCanvasStrokeWidth, applyImageEditorLayerEraseSegment, applyImageEditorLayerEraseDot, applyImageEditorLayerEraseStroke, promotePreview: () => previewNode?.moveToTop(), resetPreview: () => { previewNode = null; } };
}

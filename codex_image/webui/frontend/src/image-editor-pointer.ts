import { translate } from "./i18n";
import { imageEditorPointDistance, isImageEditorLineGesture, normalizedRect } from "./image-editor-geometry";
import type { ImageEditorLayer } from "./image-editor-types";

export interface ImageEditorPointerDependencies {
  getTool: () => string;
  hasStage: () => boolean;
  getStageContainer: () => HTMLElement | null;
  markInstruction: () => void;
  setCrop: (crop: { left: number; top: number; width: number; height: number } | null) => void;
  imageEditorPoint: (event: any) => { x: number; y: number };
  paintBucketFillRegion: (point: { x: number; y: number }) => boolean | Promise<boolean | null>;
  cancelPendingFill?: () => void;
  pushImageEditorHistory: () => void;
  setImageEditorStatus: (message: string, type?: string) => void;
  renderImageEditor: () => void;
  selectedImageEditorLayer: () => ImageEditorLayer | null;
  applyImageEditorLayerEraseDot: (layer: ImageEditorLayer, point: any) => boolean;
  applyImageEditorLayerEraseSegment: (layer: ImageEditorLayer, from: any, to: any) => boolean;
  updateImageEditorCropBox: () => void;
  previewEditorArrow: (from: any, to: any) => void;
  drawEditorBrushSegment: (from: any, to: any) => void;
  imageEditorContext: () => CanvasRenderingContext2D | null;
  drawEditorArrowOnContext: (context: CanvasRenderingContext2D, from: any, to: any) => void;
  clearImageEditorPreview: () => void;
}

export function createImageEditorPointer(dependencies: ImageEditorPointerDependencies) {
  const { getTool, hasStage, getStageContainer, markInstruction, setCrop, imageEditorPoint, paintBucketFillRegion, pushImageEditorHistory, setImageEditorStatus, renderImageEditor, selectedImageEditorLayer, applyImageEditorLayerEraseDot, applyImageEditorLayerEraseSegment, updateImageEditorCropBox, previewEditorArrow, drawEditorBrushSegment, imageEditorContext, drawEditorArrowOnContext, clearImageEditorPreview } = dependencies;
  let drawingState: any = null;

  function handleImageEditorPointerDown(event: any) {
    if (!hasStage()) return;
    dependencies.cancelPendingFill?.();
    if (getTool() === "select") return;
    event.preventDefault?.();
    const point = imageEditorPoint(event);
    if (getTool() === "fill") {
      const commit = (filled: boolean | null) => {
        if (filled === null) return;
        if (filled) {
          markInstruction();
          pushImageEditorHistory();
          setImageEditorStatus("");
        } else {
          setImageEditorStatus(translate("imageEditor.closedRegionRequired"), "error");
        }
        renderImageEditor();
      };
      const result = paintBucketFillRegion(point);
      if (typeof result === "boolean") commit(result);
      else void result.then(commit).catch(() => setImageEditorStatus(translate("imageEditor.canvasCreateFailed"), "error"));
      return;
    }
    if (getTool() === "eraser") {
      const layer = selectedImageEditorLayer();
      if (!layer) {
        setImageEditorStatus(translate("imageEditor.selectLayerFirst"), "error");
        return;
      }
      const captureTarget = captureImageEditorPointer(event);
      const changed = applyImageEditorLayerEraseDot(layer, point);
      drawingState = {
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
    drawingState = {
      pointerId: event.pointerId,
      captureTarget,
      start: point,
      last: point,
      points: [point],
    };
    if (getTool() === "crop") {
      setCrop({ left: point.x, top: point.y, width: 0, height: 0 });
      updateImageEditorCropBox();
    }
  }

  function handleImageEditorPointerMove(event: any) {
    const drawing = drawingState;
    if (!drawing) return;
    if (drawing.pointerId !== undefined && event.pointerId !== undefined && drawing.pointerId !== event.pointerId) return;
    event.preventDefault?.();
    const point = imageEditorPoint(event);
    if (getTool() === "eraser") {
      const layer = selectedImageEditorLayer();
      if (layer && layer.id === drawing.layerId) {
        drawing.changed = applyImageEditorLayerEraseSegment(layer, drawing.last, point) || drawing.changed;
      }
      drawing.points.push(point);
      drawing.last = point;
      return;
    }
    if (getTool() === "brush") {
      drawEditorBrushSegment(drawing.last, point);
      if (imageEditorPointDistance(drawing.last, point) > 0) {
        markInstruction();
      }
      drawing.last = point;
      renderImageEditor();
      return;
    }
    if (getTool() === "arrow") {
      previewEditorArrow(drawing.start, point);
      return;
    }
    if (getTool() === "crop") {
      setCrop(normalizedRect(drawing.start, point));
      updateImageEditorCropBox();
    }
  }

  function handleImageEditorPointerUp(event: any) {
    const drawing = drawingState;
    if (!drawing) return;
    if (drawing.pointerId !== undefined && event.pointerId !== undefined && drawing.pointerId !== event.pointerId) return;
    event.preventDefault?.();
    const point = imageEditorPoint(event);
    releaseImageEditorPointer(event, drawing.captureTarget);
    if (getTool() === "eraser") {
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
    } else if (getTool() === "arrow") {
      const ctx = imageEditorContext();
      if (ctx && isImageEditorLineGesture(drawing.start, point)) {
        drawEditorArrowOnContext(ctx, drawing.start, point);
        markInstruction();
        pushImageEditorHistory();
      }
      clearImageEditorPreview();
    } else if (getTool() === "brush") {
      pushImageEditorHistory();
    } else if (getTool() === "crop") {
      setCrop(normalizedRect(drawing.start, point));
    }
    drawingState = null;
    renderImageEditor();
  }

  function handleImageEditorPointerCancel(event: any) {
    dependencies.cancelPendingFill?.();
    const drawing = drawingState;
    if (!drawing) return;
    if (drawing.pointerId !== undefined && event.pointerId !== undefined && drawing.pointerId !== event.pointerId) return;
    releaseImageEditorPointer(event, drawing.captureTarget);
    if (getTool() === "brush") {
      pushImageEditorHistory();
    } else if (getTool() === "eraser") {
      if (drawing.changed) pushImageEditorHistory();
    } else if (getTool() === "arrow") {
      clearImageEditorPreview();
    } else if (getTool() === "crop") {
      setCrop(null);
    }
    drawingState = null;
    renderImageEditor();
  }

  function captureImageEditorPointer(event: any) {
    if (event?.pointerId === undefined) return null;
    const target = event.currentTarget || event.target || getStageContainer();
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

  return { handleImageEditorPointerDown, handleImageEditorPointerMove, handleImageEditorPointerUp, handleImageEditorPointerCancel, captureImageEditorPointer, releaseImageEditorPointer, clearDrawing: () => { dependencies.cancelPendingFill?.(); drawingState = null; } };
}

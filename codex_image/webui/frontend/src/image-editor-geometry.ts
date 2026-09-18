import { enclosedFillPatch } from "./image-editor-fill";
import { markImageEditorCanvasChanged } from "./image-editor-canvas";
export function normalizedRect(start: any, end: any) {
  const left = Math.min(start.x, end.x);
  const top = Math.min(start.y, end.y);
  const width = Math.abs(end.x - start.x);
  const height = Math.abs(end.y - start.y);
  if (width < 4 || height < 4) return null;
  return { left, top, width, height };
}

export function imageEditorPointDistance(from: any, to: any) {
  return Math.hypot(to.x - from.x, to.y - from.y);
}

export function isImageEditorLineGesture(from: any, to: any) {
  return imageEditorPointDistance(from, to) >= 4;
}

export function imageEditorPixelOffset(index: any) {
  return index * 4;
}

export function imageEditorBucketFillColor(color: string) {
  const normalized = String(color || "#ff3b30").replace("#", "").trim();
  const hex = /^[0-9a-fA-F]{6}$/.test(normalized) ? normalized : "ff3b30";
  return [
    Number.parseInt(hex.slice(0, 2), 16),
    Number.parseInt(hex.slice(2, 4), 16),
    Number.parseInt(hex.slice(4, 6), 16),
    255,
  ];
}

export function imageEditorBoundaryPixelBlocks(data: any, index: any) {
  return data[imageEditorPixelOffset(index) + 3] > 0;
}

export function imageEditorBoundaryHasPixels(data: any) {
  for (let offset = 3; offset < data.length; offset += 4) {
    if (data[offset] > 0) return true;
  }
  return false;
}

export function imageEditorPixelTouchesCanvasEdge(index: any, width: any, height: any) {
  const column = index % width;
  const row = Math.floor(index / width);
  return column === 0 || column === width - 1 || row === 0 || row === height - 1;
}

export function imageEditorArrowGeometry(start: any, end: any, strokeWidthValue: number) {
  const strokeWidth = Math.max(1, Number(strokeWidthValue) || 1);
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

export function fillImageEditorRegion(point: { x: number; y: number }, canvas: HTMLCanvasElement | null, boundaryCanvas: HTMLCanvasElement | null, color: string, redrawOverlay: (context: CanvasRenderingContext2D) => void) {
  const ctx = canvas?.getContext("2d", { willReadFrequently: true });
  const boundaryCtx = boundaryCanvas?.getContext("2d", { willReadFrequently: true });
  if (!canvas || !ctx || !boundaryCanvas || !boundaryCtx) return false;

  const width = canvas.width;
  const height = canvas.height;
  const boundaryData = boundaryCtx.getImageData(0, 0, width, height).data;
  const patch = enclosedFillPatch(boundaryData, width, height, point.x, point.y, imageEditorBucketFillColor(color));
  if (!patch) return false;
  const imageData = ctx.getImageData(0, 0, width, height);
  for (let row = 0; row < patch.height; row++) for (let col = 0; col < patch.width; col++) {
    const source = (row * patch.width + col) * 4;
    if (!patch.pixels[source + 3]) continue;
    const target = ((row + patch.top) * width + col + patch.left) * 4;
    imageData.data.set(patch.pixels.subarray(source, source + 4), target);
  }
  ctx.putImageData(imageData, 0, 0);
  redrawOverlay(ctx);
  markImageEditorCanvasChanged(canvas);
  return true;
}

import { imageEditorBucketFillColor } from "./image-editor-geometry";
import { markImageEditorCanvasChanged } from "./image-editor-canvas";
import type { FillPatch } from "./image-editor-fill";

export function createImageEditorFill() {
  let cancelPending: (() => void) | null = null;

  function cancel() { cancelPending?.(); }

  function fill(point: { x: number; y: number }, canvas: HTMLCanvasElement, boundary: HTMLCanvasElement, color: string, redrawOverlay: (ctx: CanvasRenderingContext2D) => void): Promise<boolean | null> {
    cancel();
    return new Promise((resolve, reject) => {
      const ctx = canvas.getContext("2d"), boundaryCtx = boundary.getContext("2d", { willReadFrequently: true });
      if (!ctx || !boundaryCtx) { resolve(false); return; }
      const worker = new Worker("/static/image-editor-fill-worker.js?v=1");
      let settled = false;
      const finish = (result: boolean | null, error?: Error) => {
        if (settled) return;
        settled = true;
        worker.terminate();
        cancelPending = null;
        if (error) reject(error); else resolve(result);
      };
      cancelPending = () => finish(null);
      worker.onerror = () => finish(null, new Error("Image fill worker failed"));
      worker.onmessage = (event: MessageEvent<FillPatch | null>) => {
        if (settled) return;
        try {
          const patch = event.data;
          if (!patch) { finish(false); return; }
          const surface = document.createElement("canvas");
          surface.width = patch.width; surface.height = patch.height;
          const patchCtx = surface.getContext("2d");
          if (!patchCtx) { finish(null, new Error("Image fill canvas unavailable")); return; }
          patchCtx.putImageData(new ImageData(patch.pixels as Uint8ClampedArray<ArrayBuffer>, patch.width, patch.height), 0, 0);
          ctx.drawImage(surface, patch.left, patch.top);
          surface.width = surface.height = 0;
          redrawOverlay(ctx);
          markImageEditorCanvasChanged(canvas);
          finish(true);
        } catch (error) { finish(null, error as Error); }
      };
      try {
        const pixels = boundaryCtx.getImageData(0, 0, canvas.width, canvas.height).data;
        worker.postMessage({ boundary: pixels, width: canvas.width, height: canvas.height, point, color: imageEditorBucketFillColor(color) }, [pixels.buffer]);
      } catch (error) { finish(null, error as Error); }
    });
  }
  return { fill, cancel };
}

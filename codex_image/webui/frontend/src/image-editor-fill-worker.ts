import { enclosedFillPatch } from "./image-editor-fill";

self.onmessage = event => {
  const { boundary, width, height, point, color } = event.data;
  const patch = enclosedFillPatch(boundary, width, height, point.x, point.y, color);
  // Dedicated worker, terminated by the owner on completion or cancellation.
  (self as any).postMessage(patch, patch ? [patch.pixels.buffer] : []);
};

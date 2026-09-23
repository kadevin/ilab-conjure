import assert from "node:assert/strict";
import test from "node:test";
import { uploadThumbnailUrl } from "../../codex_image/webui/frontend/src/upload-thumbnails";

test("large upload previews stay bounded, reuse each File and decode one at a time", async () => {
  const previousDocument = globalThis.document;
  const previousCreateImageBitmap = globalThis.createImageBitmap;
  const canvases: Array<{ width: number; height: number }> = [];
  let active = 0;
  let maxActive = 0;
  let decodeCount = 0;
  let closeCount = 0;
  (globalThis as any).document = {
    createElement: (tag: string) => {
      assert.equal(tag, "canvas");
      const canvas = {
        width: 0, height: 0,
        getContext: () => ({ drawImage: () => undefined }),
        toDataURL: () => `data:image/webp;size=${canvas.width}x${canvas.height}`,
      };
      canvases.push(canvas);
      return canvas;
    },
  };
  (globalThis as any).createImageBitmap = async (file: File, options: any) => {
    assert.equal(options.resizeWidth, 256);
    active += 1;
    maxActive = Math.max(maxActive, active);
    decodeCount += 1;
    await new Promise(resolve => setImmediate(resolve));
    active -= 1;
    return {
      width: 256, height: file.name.includes("portrait") ? 455 : 144,
      close: () => { closeCount += 1; },
    };
  };
  try {
    const landscape = new File(["synthetic"], "landscape.png", { type: "image/png" });
    const portrait = new File(["synthetic"], "portrait.png", { type: "image/png" });
    const first = uploadThumbnailUrl(landscape);
    assert.equal(uploadThumbnailUrl(landscape), first);
    const previews = await Promise.all([first, uploadThumbnailUrl(portrait)]);
    assert.deepEqual(previews, ["data:image/webp;size=256x144", "data:image/webp;size=144x256"]);
    assert.equal(maxActive, 1);
    assert.equal(decodeCount, 2);
    assert.equal(closeCount, 2);
    assert.deepEqual(canvases.map(canvas => [canvas.width, canvas.height]), [[256, 144], [144, 256]]);
    assert.equal(await uploadThumbnailUrl(landscape), previews[0]);
    assert.equal(decodeCount, 2);
  } finally {
    (globalThis as any).document = previousDocument;
    (globalThis as any).createImageBitmap = previousCreateImageBitmap;
  }
});

test("preview generation falls back to image decode when ImageBitmap is unavailable", async () => {
  const previousDocument = globalThis.document;
  const previousCreateImageBitmap = globalThis.createImageBitmap;
  const previousImage = globalThis.Image;
  const createObjectURL = URL.createObjectURL;
  const revokeObjectURL = URL.revokeObjectURL;
  const revoked: string[] = [];
  (globalThis as any).createImageBitmap = undefined;
  (globalThis as any).Image = class {
    naturalWidth = 3840;
    naturalHeight = 2160;
    src = "";
    decoding = "";
    async decode() { assert.equal(this.src, "blob:synthetic-upload"); }
  };
  (globalThis as any).document = {
    createElement: () => {
      const canvas = {
        width: 0, height: 0,
        getContext: () => ({ drawImage: () => undefined }),
        toDataURL: () => `data:image/webp;size=${canvas.width}x${canvas.height}`,
      };
      return canvas;
    },
  };
  URL.createObjectURL = () => "blob:synthetic-upload";
  URL.revokeObjectURL = url => { revoked.push(url); };
  try {
    const file = new File(["synthetic"], "fallback.png", { type: "image/png" });
    assert.equal(await uploadThumbnailUrl(file), "data:image/webp;size=256x144");
    assert.deepEqual(revoked, ["blob:synthetic-upload"]);
  } finally {
    (globalThis as any).document = previousDocument;
    (globalThis as any).createImageBitmap = previousCreateImageBitmap;
    (globalThis as any).Image = previousImage;
    URL.createObjectURL = createObjectURL;
    URL.revokeObjectURL = revokeObjectURL;
  }
});

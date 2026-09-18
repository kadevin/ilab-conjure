import assert from "node:assert/strict";
import test from "node:test";
import { createImageEditorHistory } from "../../codex_image/webui/frontend/src/image-editor-history";
import { createImageEditorPointer } from "../../codex_image/webui/frontend/src/image-editor-pointer";
import { fillImageEditorRegion, imageEditorArrowGeometry, normalizedRect } from "../../codex_image/webui/frontend/src/image-editor-geometry";
import { imageEditorExportDimensions } from "../../codex_image/webui/frontend/src/image-editor-canvas";

test("undo then edit discards only the redo branch", () => {
  let current = { value: 0 };
  const restored: number[] = [];
  const history = createImageEditorHistory({
    capture: () => ({ ...current }), changed() {},
    restore(snapshot) { current = { ...snapshot! }; restored.push(current.value); },
  });
  history.pushImageEditorHistory();
  current.value = 1; history.pushImageEditorHistory();
  current.value = 2; history.pushImageEditorHistory();
  history.undoImageEdit();
  assert.equal(current.value, 1);
  assert.equal(history.canRedo(), true);
  current.value = 3; history.pushImageEditorHistory();
  assert.equal(history.canRedo(), false);
  history.undoImageEdit(); history.undoImageEdit(); history.undoImageEdit();
  assert.deepEqual(restored, [1, 1, 0]);
  history.redoImageEdit(); history.redoImageEdit();
  assert.equal(current.value, 3);
});

test("history retains thirty snapshots and reset releases undo and redo", () => {
  let value = 0, last = -1;
  const history = createImageEditorHistory({ capture: () => ({ value }), restore: s => { last = s!.value; }, changed() {} });
  for (; value < 40; value++) history.pushImageEditorHistory();
  for (let i = 0; i < 50; i++) history.undoImageEdit();
  assert.equal(last, 10);
  assert.equal(history.canUndo(), false);
  assert.equal(history.canRedo(), true);
  history.reset();
  assert.equal(history.canUndo(), false);
  assert.equal(history.canRedo(), false);
});

test("an unavailable canvas snapshot does not add a history entry", () => {
  let changes = 0;
  const history = createImageEditorHistory({ capture: () => null, restore() { assert.fail("no snapshot"); }, changed() { changes++; } });
  history.pushImageEditorHistory(); history.undoImageEdit(); history.redoImageEdit();
  assert.equal(changes, 0);
});

function fillFixture(closed: boolean) {
  const width = 5, height = 5;
  const boundary = new Uint8ClampedArray(width * height * 4);
  for (let y = 1; y <= 3; y++) for (let x = 1; x <= 3; x++) {
    if (x === 1 || x === 3 || y === 1 || y === 3) boundary[(y * width + x) * 4 + 3] = 255;
  }
  if (!closed) boundary[(1 * width + 2) * 4 + 3] = 0;
  const data = new Uint8ClampedArray(width * height * 4);
  let commits = 0, overlays = 0;
  const context = { getImageData: () => ({ data }), putImageData() { commits++; } };
  const canvas = { width, height, getContext: () => context } as any;
  const boundaryCanvas = { width, height, getContext: () => ({ getImageData: () => ({ data: boundary }) }) } as any;
  return { data, fill: (point = { x: 2, y: 2 }) => fillImageEditorRegion(point, canvas, boundaryCanvas, "#123456", () => { overlays++; }), counts: () => ({ commits, overlays }) };
}

test("closed fill changes only the enclosed pixel then restores the overlay", () => {
  const f = fillFixture(true);
  assert.equal(f.fill(), true);
  assert.deepEqual([...f.data.slice(48, 52)], [0x12, 0x34, 0x56, 255]);
  assert.equal(f.data.filter((value, i) => i < 48 || i >= 52).every(value => value === 0), true);
  assert.deepEqual(f.counts(), { commits: 1, overlays: 1 });
});

test("open regions and boundary clicks never commit pixel changes", () => {
  const open = fillFixture(false), closed = fillFixture(true);
  assert.equal(open.fill(), false);
  assert.equal(closed.fill({ x: 1, y: 1 }), false);
  assert.deepEqual(open.counts(), { commits: 0, overlays: 0 });
  assert.deepEqual(closed.counts(), { commits: 0, overlays: 0 });
});

test("crop normalization and export scaling retain their size limits", () => {
  assert.deepEqual(normalizedRect({ x: 12, y: 20 }, { x: 2, y: 4 }), { left: 2, top: 4, width: 10, height: 16 });
  assert.equal(normalizedRect({ x: 0, y: 0 }, { x: 3, y: 10 }), null);
  assert.deepEqual(imageEditorExportDimensions({ width: 8192, height: 4096 }), { width: 4096, height: 2048, scale: 0.5 });
  const arrow = imageEditorArrowGeometry({ x: 0, y: 0 }, { x: 0, y: 0 }, 8);
  assert.equal(Number.isFinite(arrow.headLeft.x) && Number.isFinite(arrow.headRight.y), true);
});

function pointerFixture(initialTool = "crop") {
  let tool = initialTool, crop: any = null, pushes = 0, marks = 0, renders = 0, fillSuccess = false;
  const released: number[] = [];
  const target = { setPointerCapture() {}, releasePointerCapture: (id: number) => released.push(id) };
  const pointer = createImageEditorPointer({
    getTool: () => tool, hasStage: () => true, getStageContainer: () => target as any,
    markInstruction() { marks++; }, setCrop(value) { crop = value; },
    imageEditorPoint: e => ({ x: e.x, y: e.y }), paintBucketFillRegion: () => fillSuccess,
    pushImageEditorHistory() { pushes++; }, setImageEditorStatus() {}, renderImageEditor() { renders++; },
    selectedImageEditorLayer: () => null, applyImageEditorLayerEraseDot: () => false,
    applyImageEditorLayerEraseSegment: () => false, updateImageEditorCropBox() {},
    previewEditorArrow() {}, drawEditorBrushSegment() {}, imageEditorContext: () => null,
    drawEditorArrowOnContext() {}, clearImageEditorPreview() {},
  });
  const event = (id: number, x: number, y: number) => ({ pointerId: id, x, y, currentTarget: target, preventDefault() {} });
  return { pointer, event, setTool: (value: string) => { tool = value; }, enableFill: () => { fillSuccess = true; }, state: () => ({ crop, pushes, marks, renders, released }) };
}

test("crop ignores another pointer and cancellation clears the crop without adding instruction marks", () => {
  const f = pointerFixture();
  f.pointer.handleImageEditorPointerDown(f.event(1, 1, 1));
  f.pointer.handleImageEditorPointerMove(f.event(2, 20, 20));
  assert.equal(f.state().crop.width, 0);
  f.pointer.handleImageEditorPointerMove(f.event(1, 20, 20));
  assert.equal(f.state().crop.width, 19);
  f.pointer.handleImageEditorPointerCancel(f.event(1, 20, 20));
  assert.equal(f.state().crop, null);
  assert.deepEqual(f.state().released, [1]);
  assert.equal(f.state().marks, 0);
  assert.equal(f.state().pushes, 0);
});

test("only a successful fill marks the edit and records history", () => {
  const f = pointerFixture("fill");
  f.pointer.handleImageEditorPointerDown(f.event(1, 2, 2));
  assert.equal(f.state().marks, 0);
  f.enableFill();
  f.pointer.handleImageEditorPointerDown(f.event(1, 2, 2));
  assert.equal(f.state().marks, 1);
  assert.equal(f.state().pushes, 1);
});

test("clearing a gesture prevents a stale pointer-up from committing it", () => {
  const f = pointerFixture("brush");
  f.pointer.handleImageEditorPointerDown(f.event(1, 2, 2));
  f.pointer.clearDrawing();
  f.pointer.handleImageEditorPointerUp(f.event(1, 20, 20));
  assert.equal(f.state().pushes, 0);
});

import { enclosedFillPatch } from "../../codex_image/webui/frontend/src/image-editor-fill";
import { captureImageEditorCanvas, markImageEditorCanvasChanged } from "../../codex_image/webui/frontend/src/image-editor-canvas";
import { createImageEditorFill } from "../../codex_image/webui/frontend/src/image-editor-fill-client";

test("scanline fill matches four-connected flood fill including holes and diagonal gaps", () => {
  let seed = 42;
  const random = () => { seed = (Math.imul(seed, 1664525) + 1013904223) >>> 0; return seed / 4294967296; };
  for (let attempt = 0; attempt < 200; attempt++) {
    const w = 20, h = 17, data = new Uint8ClampedArray(w * h * 4);
    for (let i = 0; i < w * h; i++) if (random() < .35) data[i * 4 + 3] = 1;
    if (attempt % 2 === 0) for (let y = 0; y < h; y++) for (let x = 0; x < w; x++) {
      if (!x || !y || x === w - 1 || y === h - 1) data[(y * w + x) * 4 + 3] = 255;
    }
    const x = Math.floor(random() * w), y = Math.floor(random() * h);
    const pending = [y * w + x], region = new Set<number>();
    let open = false;
    while (pending.length) {
      const i = pending.pop()!;
      if (region.has(i) || data[i * 4 + 3]) continue;
      region.add(i);
      if (i % w === 0 || i % w === w - 1 || i < w || i >= w * (h - 1)) { open = true; break; }
      pending.push(i - 1, i + 1, i - w, i + w);
    }
    const patch = enclosedFillPatch(data, w, h, x, y, [1, 2, 3, 255]);
    if (open || !region.size) assert.equal(patch, null);
    else {
      assert.ok(patch);
      const actual = new Set<number>();
      for (let row = 0; row < patch.height; row++) for (let col = 0; col < patch.width; col++) {
        if (patch.pixels[(row * patch.width + col) * 4 + 3]) actual.add((row + patch.top) * w + col + patch.left);
      }
      assert.deepEqual(actual, region);
    }
  }
});

test("pixel versions share unchanged surfaces and recreate released versions", () => {
  const previous = globalThis.document;
  let copies = 0;
  globalThis.document = { createElement: () => ({ width: 0, height: 0, getContext: () => ({ drawImage() { copies++; } }) }) } as any;
  try {
    const canvas = { width: 4096, height: 4096 } as HTMLCanvasElement;
    const first = captureImageEditorCanvas(canvas);
    for (let i = 0; i < 30; i++) assert.equal(captureImageEditorCanvas(canvas), first);
    assert.equal(copies, 1);
    markImageEditorCanvasChanged(canvas);
    assert.notEqual(captureImageEditorCanvas(canvas), first);
    const last = captureImageEditorCanvas(canvas);
    last.width = last.height = 0;
    assert.notEqual(captureImageEditorCanvas(canvas), last);
    assert.equal(copies, 3);
  } finally { globalThis.document = previous; }
});

test("history budgets unique pixels, releases redo and retains a usable undo", () => {
  const canvas = () => ({ width: 10, height: 10 }) as HTMLCanvasElement;
  const base = canvas();
  let pixels = canvas(), restored: any;
  const history = createImageEditorHistory({ capture: () => ({ base, pixels }), restore: s => { restored = s; }, changed() {}, resources: s => [s.base, s.pixels], byteBudget: 1200 });
  for (let i = 0; i < 30; i++) history.pushImageEditorHistory();
  assert.equal(history.retainedBytes(), 800);
  const firstPixels = pixels;
  pixels = canvas(); history.pushImageEditorHistory();
  const redoPixels = pixels;
  history.undoImageEdit();
  pixels = canvas(); history.pushImageEditorHistory();
  assert.equal(redoPixels.width, 0);
  assert.equal(firstPixels.width, 10);
  pixels = canvas(); history.pushImageEditorHistory();
  assert.equal(history.retainedBytes(), 1200);
  assert.equal(firstPixels.width, 0);
  history.undoImageEdit(); assert.equal(restored.base, base);
  history.reset();
  assert.equal(base.width, 0);
  assert.equal(history.retainedBytes(), 0);
});

test("cancelled fill terminates its worker and ignores a late result", async () => {
  const previous = globalThis.Worker;
  const workers: any[] = [];
  globalThis.Worker = class {
    onmessage: any; onerror: any; terminated = false;
    constructor() { workers.push(this); }
    postMessage() {} terminate() { this.terminated = true; }
  } as any;
  try {
    let commits = 0;
    const ctx = { getImageData: () => ({ data: new Uint8ClampedArray(100) }), drawImage: () => { commits++; } };
    const canvas = { width: 5, height: 5, getContext: () => ctx } as any;
    const client = createImageEditorFill();
    const pending = client.fill({ x: 2, y: 2 }, canvas, canvas, "#123456", () => {});
    client.cancel();
    assert.equal(await pending, null);
    assert.equal(workers[0].terminated, true);
    workers[0].onmessage({ data: { pixels: [], width: 1, height: 1 } });
    assert.equal(commits, 0);
    const next = client.fill({ x: 2, y: 2 }, canvas, canvas, "#123456", () => {});
    workers[1].onmessage({ data: null });
    assert.equal(await next, false);
  } finally { globalThis.Worker = previous; }
});

import assert from "node:assert/strict";
import test from "node:test";
import { bindImageTouchGestures, createImageTouchGesture, type ImageTransform } from "../../codex_image/webui/frontend/src/lightbox-touch";
import { mobileKeyboardInset } from "../../codex_image/webui/frontend/src/mobile-shell";
import { shouldCloseLightboxFromClick } from "../../codex_image/webui/frontend/src/lightbox-controls";

function harness(initial: ImageTransform = { scale: 1, x: 0, y: 0 }) {
  let transform = initial;
  const navigation: string[] = [];
  const gesture = createImageTouchGesture({ read: () => transform, write: value => { transform = value; }, navigate: direction => navigation.push(direction) });
  return { gesture, navigation, read: () => transform };
}

test("keyboard avoidance ignores browser chrome and page pinch zoom", () => {
  assert.equal(mobileKeyboardInset(true, 844, { height: 510, offsetTop: 20, scale: 1 }), 314);
  assert.equal(mobileKeyboardInset(true, 844, { height: 780, offsetTop: 0, scale: 1 }), 0);
  assert.equal(mobileKeyboardInset(true, 844, { height: 400, offsetTop: 0, scale: 2 }), 0);
  assert.equal(mobileKeyboardInset(false, 844, { height: 400, offsetTop: 0, scale: 1 }), 0);
  assert.equal(mobileKeyboardInset(true, 844, null), 0);
});

test("pinch keeps the point under the fingers anchored and never switches the image", () => {
  const { gesture, navigation, read } = harness();
  gesture.down(1, { x: 0, y: 0 }); gesture.down(2, { x: 100, y: 0 });
  gesture.move(2, { x: 200, y: 0 });
  assert.deepEqual(read(), { scale: 2, x: 0, y: 0 });
  assert.equal(gesture.up(2), true);
  gesture.move(1, { x: -80, y: 10 });
  assert.deepEqual(read(), { scale: 2, x: -80, y: 10 });
  assert.equal(gesture.up(1), true);
  assert.deepEqual(navigation, []);
});

test("zoom about an off-centre midpoint compensates image translation", () => {
  const { gesture, read } = harness();
  gesture.down(1, { x: 50, y: 30 }); gesture.down(2, { x: 150, y: 30 });
  gesture.move(1, { x: 0, y: 30 }); gesture.move(2, { x: 200, y: 30 });
  assert.deepEqual(read(), { scale: 2, x: -100, y: -30 });
});

test("fit mode distinguishes taps, vertical movement and deliberate horizontal swipes", () => {
  const { gesture, navigation } = harness();
  gesture.down(1, { x: 0, y: 0 }); gesture.move(1, { x: 3, y: 2 });
  assert.equal(gesture.up(1), false);
  gesture.down(1, { x: 0, y: 0 }); gesture.move(1, { x: 40, y: 140 }); gesture.up(1);
  assert.deepEqual(navigation, []);
  gesture.down(1, { x: 0, y: 0 }); gesture.move(1, { x: -90, y: 10 });
  assert.equal(gesture.up(1), true); assert.deepEqual(navigation, ["next"]);
  gesture.down(1, { x: 0, y: 0 }); gesture.move(1, { x: 90, y: 10 }); gesture.up(1);
  assert.deepEqual(navigation, ["next", "previous"]);
});

test("zoomed drag pans without changing images; cancellation cannot trigger navigation", () => {
  const { gesture, navigation, read } = harness({ scale: 3, x: 10, y: 20 });
  gesture.down(1, { x: 0, y: 0 }); gesture.move(1, { x: 90, y: 30 }); gesture.up(1);
  assert.deepEqual(read(), { scale: 3, x: 100, y: 50 }); assert.deepEqual(navigation, []);
  const fit = harness();
  fit.gesture.down(1, { x: 0, y: 0 }); fit.gesture.move(1, { x: 90, y: 0 });
  assert.equal(fit.gesture.up(1, true), true); assert.deepEqual(fit.navigation, []);
  fit.gesture.reset();
  fit.gesture.move(1, { x: 100, y: 0 }); assert.equal(fit.gesture.up(1), false);
});

test("pinch limits scale to the fitted image and five times its size", () => {
  const { gesture, read } = harness();
  gesture.down(1, { x: 0, y: 0 }); gesture.down(2, { x: 100, y: 0 });
  gesture.move(2, { x: 10000, y: 0 }); assert.equal(read().scale, 5);
  gesture.move(2, { x: 1, y: 0 }); assert.equal(read().scale, 1);
});

test("touch event wiring captures drags and suppresses their trailing click without taking over mouse input", () => {
  const listeners = new Map<string, Function>();
  const captured = new Set<number>();
  const root: any = {
    addEventListener: (name: string, handler: Function) => listeners.set(name, handler),
    setPointerCapture: (id: number) => captured.add(id), hasPointerCapture: (id: number) => captured.has(id),
    releasePointerCapture: (id: number) => captured.delete(id),
  };
  const image: any = { getBoundingClientRect: () => ({ x: 0, y: 0, width: 400, height: 400 }) };
  const navigation: string[] = [];
  const reset = bindImageTouchGestures(root, image, { read: () => ({ scale: 1, x: 0, y: 0 }), write() {}, tap() {}, navigate: direction => navigation.push(direction) });
  const event = (type: string, x: number, pointerType = "touch") => ({ type, pointerId: 1, pointerType, clientX: x, clientY: 200, target: { closest: () => null }, preventDefault() {} });
  listeners.get("pointerdown")!(event("pointerdown", 200, "mouse")); assert.equal(captured.size, 0);
  listeners.get("pointerdown")!(event("pointerdown", 200)); assert.equal(captured.size, 1);
  listeners.get("pointermove")!(event("pointermove", 80));
  listeners.get("pointerup")!(event("pointerup", 80));
  assert.equal(captured.size, 0); assert.deepEqual(navigation, ["next"]);
  let stopped = false;
  listeners.get("click")!({ target: { closest: () => null }, preventDefault() {}, stopImmediatePropagation: () => { stopped = true; } });
  assert.equal(stopped, true);
  reset(); stopped = false;
  listeners.get("click")!({ target: { closest: () => null }, preventDefault() {}, stopImmediatePropagation: () => { stopped = true; } });
  assert.equal(stopped, false);
});

test("touch taps close the backdrop without a synthetic click and preserve the original image target", () => {
  const listeners = new Map<string, Function>();
  const captured = new Set<number>();
  const root: any = {
    closest: () => null,
    addEventListener: (name: string, handler: Function) => listeners.set(name, handler),
    setPointerCapture: (id: number) => captured.add(id), hasPointerCapture: (id: number) => captured.has(id),
    releasePointerCapture: (id: number) => captured.delete(id),
  };
  const image: any = {
    closest: (selector: string) => selector.includes("img") ? image : null,
    getBoundingClientRect: () => ({ x: 20, y: 68, width: 300, height: 524 }),
  };
  const closeButton = { closest: () => closeButton };
  let closed = 0;
  const taps: EventTarget[] = [];
  const navigation: string[] = [];
  bindImageTouchGestures(root, image, {
    read: () => ({ scale: 1, x: 0, y: 0 }), write() {},
    navigate: direction => navigation.push(direction),
    tap: target => { taps.push(target!); if (shouldCloseLightboxFromClick(target, root)) closed++; },
  });
  const fire = (type: string, target: any, x = 150, id = 1) => listeners.get(type)!({
    type, target, pointerType: "touch", pointerId: id, clientX: x, clientY: 200, preventDefault() {},
  });
  // Captured pointerup is retargeted to the root even when the tap began on the image.
  fire("pointerdown", image); fire("pointerup", root);
  assert.deepEqual(taps, [image]); assert.equal(closed, 0);
  fire("pointerdown", root, 5); fire("pointerup", root, 5);
  assert.equal(closed, 1, "backdrop exits even if iOS never emits click");
  let stopped = false;
  const click = (target: any) => listeners.get("click")!({ target, preventDefault() {}, stopImmediatePropagation() { stopped = true; } });
  click(root); assert.equal(stopped, true, "retargeted synthetic click must not exit twice");
  // Close/zoom/navigation controls keep their native click, including just after a gesture.
  fire("pointerdown", closeButton); assert.equal(captured.size, 0);
  fire("pointerup", closeButton); stopped = false; click(closeButton);
  assert.equal(stopped, false); assert.equal(taps.length, 2);
  fire("pointerdown", image); fire("pointermove", root, 60); fire("pointerup", root, 60);
  assert.deepEqual(navigation, ["next"]); assert.equal(closed, 1); assert.equal(taps.length, 2);
  fire("pointerdown", image); fire("pointerdown", image, 250, 2);
  fire("pointerup", root, 250, 2); fire("pointerup", root);
  fire("pointerdown", root, 5); fire("pointercancel", root, 5); fire("lostpointercapture", root, 5);
  assert.equal(taps.length, 2, "pinch and cancelled touches cannot become backdrop taps");
});

test("clipboard success is reported only after copying; denied HTTP fallback exposes selectable text", async () => {
  const oldDocument = (globalThis as any).document;
  const oldNavigator = Object.getOwnPropertyDescriptor(globalThis, "navigator");
  const oldRAF = (globalThis as any).requestAnimationFrame;
  class Element {
    children: Element[] = []; className = ""; style: any = {}; value = ""; textContent = ""; readOnly = false;
    attributes: Record<string, string> = {}; parent: Element | null = null; selected = false;
    classList = { add: (v: string) => { this.className += ` ${v}`; }, remove: (v: string) => { this.className = this.className.replace(v, ""); } };
    constructor(public tag: string) {}
    append(...nodes: Element[]) { nodes.forEach(node => { node.parent = this; this.children.push(node); }); }
    replaceChildren(...nodes: Element[]) { this.children = []; this.append(...nodes); }
    setAttribute(key: string, value: string) { this.attributes[key] = value; }
    addEventListener() {} closest() { return null; }
    remove() { if (this.parent) this.parent.children = this.parent.children.filter(node => node !== this); }
    focus() { doc.activeElement = this; } select() { this.selected = true; }
  }
  let allowLegacyCopy = false;
  const doc: any = { body: new Element("body"), activeElement: null, createElement: (tag: string) => new Element(tag), addEventListener() {}, execCommand: () => allowLegacyCopy };
  const copied: string[] = [];
  try {
    (globalThis as any).document = doc;
    (globalThis as any).requestAnimationFrame = (callback: Function) => { callback(); return 1; };
    Object.defineProperty(globalThis, "navigator", { configurable: true, value: { clipboard: { writeText: async (text: string) => { copied.push(text); } } } });
    const { copyTextToClipboard } = await import('../../codex_image/webui/frontend/src/clipboard-text');
    assert.equal(await copyTextToClipboard('第一行\nSecond line'), true); assert.deepEqual(copied, ['第一行\nSecond line']);
    (globalThis as any).navigator.clipboard = undefined;
    allowLegacyCopy = true; assert.equal(await copyTextToClipboard('legacy copy'), true);
    (globalThis as any).navigator.clipboard = { writeText: async () => { throw new Error('permission denied'); } };
    assert.equal(await copyTextToClipboard('permission fallback'), true);
    (globalThis as any).navigator.clipboard = undefined;
    allowLegacyCopy = false; assert.equal(await copyTextToClipboard('select this text'), false);
    assert.equal(doc.activeElement.tag, 'textarea'); assert.equal(doc.activeElement.value, 'select this text');
    assert.equal(doc.activeElement.readOnly, true); assert.equal(doc.activeElement.selected, true);
    assert.equal(doc.body.children.some((node: Element) => node.className.includes('mobile-sheet') && !node.className.includes('hidden')), true);
  } finally {
    (globalThis as any).document = oldDocument; (globalThis as any).requestAnimationFrame = oldRAF;
    if (oldNavigator) Object.defineProperty(globalThis, "navigator", oldNavigator); else delete (globalThis as any).navigator;
  }
});

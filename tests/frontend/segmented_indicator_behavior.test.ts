import assert from "node:assert/strict";
import test from "node:test";

import {
  initSegmentedIndicatorFeature,
  refreshSegmentedIndicators,
} from "../../codex_image/webui/frontend/src/segmented-indicator";

type Rect = { left: number; top: number; width: number; height: number };

class FakeClassList {
  private readonly values = new Set<string>();

  add(...names: string[]): void {
    names.forEach((name) => this.values.add(name));
  }

  remove(...names: string[]): void {
    names.forEach((name) => this.values.delete(name));
  }

  contains(name: string): boolean {
    return this.values.has(name);
  }
}

class FakeStyle {
  private readonly values = new Map<string, string>();

  setProperty(name: string, value: string): void {
    this.values.set(name, value);
  }

  getPropertyValue(name: string): string {
    return this.values.get(name) ?? "";
  }
}

class FakeElement {
  readonly children: FakeElement[] = [];
  readonly classList = new FakeClassList();
  readonly style = new FakeStyle();
  readonly listeners = new Map<string, Array<() => void>>();
  private currentClassName = "";
  isConnected = true;

  constructor(private rect: Rect = { left: 0, top: 0, width: 0, height: 0 }) {}

  get firstElementChild(): FakeElement | null {
    return this.children[0] ?? null;
  }

  get className(): string {
    return this.currentClassName;
  }

  set className(value: string) {
    this.currentClassName = value;
    value.split(/\s+/).filter(Boolean).forEach((name) => this.classList.add(name));
  }

  setRect(rect: Rect): void {
    this.rect = rect;
  }

  getBoundingClientRect(): Rect {
    return this.rect;
  }

  setAttribute(_name: string, _value: string): void {}

  insertBefore(child: FakeElement, before: FakeElement | null): void {
    const index = before ? this.children.indexOf(before) : -1;
    this.children.splice(index >= 0 ? index : this.children.length, 0, child);
  }

  append(...children: FakeElement[]): void {
    this.children.push(...children);
  }

  querySelector(selector: string): FakeElement | null {
    if (!selector.includes(".active")) return null;
    return this.children.find((child) => child.classList.contains("active")) ?? null;
  }

  querySelectorAll(selector: string): FakeElement[] {
    if (selector.includes(".radio-btn")) {
      return this.children.filter((child) => child.classList.contains("radio-btn"));
    }
    return [];
  }

  addEventListener(type: string, listener: () => void): void {
    const listeners = this.listeners.get(type) ?? [];
    listeners.push(listener);
    this.listeners.set(type, listeners);
  }
}

test("new segmented controls start in final geometry while later selections update on the next frame", () => {
  const host = new FakeElement({ left: 100, top: 40, width: 220, height: 36 });
  const first = new FakeElement({ left: 103, top: 43, width: 80, height: 30 });
  first.classList.add("radio-btn", "active");
  const second = new FakeElement({ left: 183, top: 43, width: 134, height: 30 });
  second.classList.add("radio-btn");
  host.append(first, second);

  const initiallyHiddenHost = new FakeElement({ left: 0, top: 0, width: 0, height: 0 });
  const initiallyHiddenActive = new FakeElement({ left: 0, top: 0, width: 0, height: 0 });
  initiallyHiddenActive.classList.add("radio-btn", "active");
  initiallyHiddenHost.append(initiallyHiddenActive);

  const animationFrames: Array<() => void> = [];
  const mutationCallbacks: Array<() => void> = [];
  const previousDocument = (globalThis as any).document;
  const previousWindow = (globalThis as any).window;
  const previousHTMLElement = (globalThis as any).HTMLElement;
  const previousMutationObserver = (globalThis as any).MutationObserver;

  (globalThis as any).HTMLElement = FakeElement;
  (globalThis as any).MutationObserver = class {
    constructor(callback: () => void) {
      mutationCallbacks.push(callback);
    }

    observe(): void {}
  };
  (globalThis as any).document = {
    createElement: () => new FakeElement(),
    querySelectorAll: () => [host, initiallyHiddenHost],
  };
  (globalThis as any).window = {
    addEventListener() {},
    getComputedStyle: () => ({ borderLeftWidth: "1px", borderTopWidth: "1px" }),
    requestAnimationFrame: (callback: () => void) => {
      animationFrames.push(callback);
      return animationFrames.length;
    },
  };

  try {
    initSegmentedIndicatorFeature();

    const indicator = host.children.find((child) => child.classList.contains("segmented-indicator"));
    assert.ok(indicator);
    assert.equal(indicator.style.getPropertyValue("--segmented-indicator-x"), "2px");
    assert.equal(indicator.style.getPropertyValue("--segmented-indicator-y"), "2px");
    assert.equal(indicator.style.getPropertyValue("--segmented-indicator-width"), "80px");
    assert.equal(indicator.style.getPropertyValue("--segmented-indicator-height"), "30px");
    assert.equal(indicator.style.getPropertyValue("--segmented-indicator-opacity"), "1");
    assert.equal(animationFrames.length, 0, "initial geometry is committed before the browser can paint an origin state");

    const initiallyHiddenIndicator = initiallyHiddenHost.children.find(
      (child) => child.classList.contains("segmented-indicator"),
    );
    assert.ok(initiallyHiddenIndicator);
    assert.equal(
      initiallyHiddenHost.classList.contains("segmented-indicator-ready"),
      false,
      "a zero-sized hidden control must not become animation-ready",
    );
    assert.equal(initiallyHiddenIndicator.style.getPropertyValue("--segmented-indicator-opacity"), "0");

    first.classList.remove("active");
    second.classList.add("active");
    mutationCallbacks[0]();

    assert.equal(indicator.style.getPropertyValue("--segmented-indicator-x"), "2px");
    assert.equal(animationFrames.length, 1, "later selection changes are coalesced for a smooth slide");
    animationFrames.shift()?.();
    assert.equal(indicator.style.getPropertyValue("--segmented-indicator-x"), "82px");
    assert.equal(indicator.style.getPropertyValue("--segmented-indicator-width"), "134px");

    initiallyHiddenHost.setRect({ left: 30, top: 20, width: 126, height: 36 });
    initiallyHiddenActive.setRect({ left: 33, top: 23, width: 120, height: 30 });
    refreshSegmentedIndicators();
    assert.equal(
      initiallyHiddenHost.classList.contains("segmented-indicator-ready"),
      false,
      "the first visible geometry is still committed without an entrance transition",
    );
    animationFrames.splice(0).forEach((callback) => callback());
    assert.equal(initiallyHiddenIndicator.style.getPropertyValue("--segmented-indicator-x"), "2px");
    assert.equal(initiallyHiddenIndicator.style.getPropertyValue("--segmented-indicator-width"), "120px");
    assert.equal(initiallyHiddenHost.classList.contains("segmented-indicator-ready"), true);
  } finally {
    (globalThis as any).document = previousDocument;
    (globalThis as any).window = previousWindow;
    (globalThis as any).HTMLElement = previousHTMLElement;
    (globalThis as any).MutationObserver = previousMutationObserver;
  }
});

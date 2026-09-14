export type ImageTransform = { scale: number; x: number; y: number };
type Point = { x: number; y: number };
type GestureOptions = {
  read(): ImageTransform;
  write(transform: ImageTransform): void;
  navigate(direction: "previous" | "next"): void;
};

/** Coordinates are relative to the untransformed image centre. */
export function createImageTouchGesture(options: GestureOptions) {
  const points = new Map<number, Point>();
  let initial = options.read();
  let start: Point = { x: 0, y: 0 };
  let distance = 0;
  let multiTouch = false;
  let moved = false;
  const center = () => {
    const [a, b] = [...points.values()];
    return b ? { x: (a!.x + b.x) / 2, y: (a!.y + b.y) / 2 } : a!;
  };
  const separation = () => {
    const [a, b] = [...points.values()];
    return b ? Math.hypot(b.x - a!.x, b.y - a!.y) : 0;
  };
  const rebase = () => { initial = options.read(); start = center(); distance = separation(); };
  return {
    down(id: number, point: Point) {
      if (!points.size) { moved = false; multiTouch = false; }
      points.set(id, point);
      if (points.size > 1) multiTouch = true;
      rebase();
    },
    move(id: number, point: Point) {
      if (!points.has(id)) return;
      points.set(id, point);
      const current = center();
      const dx = current.x - start.x, dy = current.y - start.y;
      if (Math.hypot(dx, dy) > 8 || points.size > 1) moved = true;
      if (points.size > 1 && distance > 0) {
        const scale = Math.max(1, Math.min(5, initial.scale * separation() / distance));
        const ratio = scale / initial.scale;
        options.write({ scale, x: current.x - (start.x - initial.x) * ratio, y: current.y - (start.y - initial.y) * ratio });
      } else if (initial.scale > 1.025) {
        options.write({ scale: initial.scale, x: initial.x + dx, y: initial.y + dy });
      }
    },
    up(id: number, cancelled = false) {
      if (!points.has(id)) return false;
      const end = points.get(id)!;
      if (!cancelled && points.size === 1 && !multiTouch && initial.scale <= 1.025) {
        const dx = end.x - start.x, dy = end.y - start.y;
        if (Math.abs(dx) >= 48 && Math.abs(dx) > Math.abs(dy) * 1.4) options.navigate(dx < 0 ? "next" : "previous");
      }
      points.delete(id);
      const suppressClick = moved || multiTouch || cancelled;
      if (points.size) rebase();
      return suppressClick;
    },
    reset() { points.clear(); moved = false; multiTouch = false; },
  };
}

export function bindImageTouchGestures(root: HTMLElement, image: HTMLImageElement, options: GestureOptions & {
  tap(target: EventTarget | null): void;
}) {
  const gesture = createImageTouchGesture(options);
  const targets = new Map<number, EventTarget | null>();
  let suppressUntil = 0;
  const localPoint = (event: PointerEvent) => {
    const rect = image.getBoundingClientRect();
    const current = options.read();
    return { x: event.clientX - (rect.x + rect.width / 2 - current.x), y: event.clientY - (rect.y + rect.height / 2 - current.y) };
  };
  root.addEventListener("pointerdown", event => {
    if (event.pointerType === "mouse" || (event.target as Element).closest("button, a, [role=toolbar]")) return;
    event.preventDefault();
    targets.set(event.pointerId, event.target);
    gesture.down(event.pointerId, localPoint(event));
    root.setPointerCapture(event.pointerId);
  });
  root.addEventListener("pointermove", event => {
    if (event.pointerType === "mouse" || !root.hasPointerCapture(event.pointerId)) return;
    gesture.move(event.pointerId, localPoint(event));
  });
  const finish = (event: PointerEvent) => {
    if (event.pointerType === "mouse" || !targets.has(event.pointerId)) return;
    const target = targets.get(event.pointerId)!;
    targets.delete(event.pointerId);
    if (event.type === "pointerup") gesture.move(event.pointerId, localPoint(event));
    const consumed = gesture.up(event.pointerId, event.type !== "pointerup");
    if (root.hasPointerCapture(event.pointerId)) root.releasePointerCapture(event.pointerId);
    // Pointer capture retargets clicks to the root; iOS may omit the click after
    // preventDefault. Resolve taps using their original target in either case.
    if (!consumed && event.type === "pointerup") options.tap(target);
    suppressUntil = Date.now() + 500;
  };
  root.addEventListener("pointerup", finish);
  root.addEventListener("pointercancel", finish);
  root.addEventListener("lostpointercapture", finish);
  root.addEventListener("click", event => {
    if (Date.now() < suppressUntil && !(event.target as Element).closest("button, a, [role=toolbar]")) {
      event.preventDefault(); event.stopImmediatePropagation();
    }
  }, true);
  return () => { gesture.reset(); targets.clear(); suppressUntil = 0; };
}

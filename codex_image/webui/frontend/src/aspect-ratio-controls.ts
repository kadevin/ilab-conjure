export interface AspectRatioSlot {
  values: string[];
}

export interface AspectRatioRect {
  x: number;
  y: number;
  width: number;
  height: number;
}

const PREFERRED_RATIO_SLOTS = [
  ["1:1", "21:9"],
  ["4:5", "5:4"],
  ["3:4", "4:3"],
  ["2:3", "3:2"],
  ["9:16", "16:9"],
  ["1:4", "4:1"],
  ["1:8", "8:1"],
  ["1:2", "2:1"],
  ["9:19.5", "19.5:9"],
  ["9:20", "20:9"],
] as const;

function parsedRatio(value: string): { width: number; height: number } | null {
  const match = value.trim().match(/^(\d+(?:\.\d+)?):(\d+(?:\.\d+)?)$/);
  if (!match) return null;
  const width = Number(match[1]);
  const height = Number(match[2]);
  if (!Number.isFinite(width) || !Number.isFinite(height) || width <= 0 || height <= 0) return null;
  return { width, height };
}

function reciprocal(left: string, right: string): boolean {
  const a = parsedRatio(left);
  const b = parsedRatio(right);
  if (!a || !b) return false;
  return Math.abs(a.width * b.width - a.height * b.height) < 1e-9;
}

export function aspectRatioSlots(values: string[]): AspectRatioSlot[] {
  const available = new Set(values);
  const used = new Set<string>();
  const slots: AspectRatioSlot[] = [];
  PREFERRED_RATIO_SLOTS.forEach((preferred, index) => {
    const matched: string[] = preferred.filter((value) => available.has(value) && !used.has(value));
    if (!matched.length) return;
    if (index === 0 && matched.length === 1 && matched[0] === "1:1" && available.has("auto")) {
      matched.push("auto");
    }
    matched.forEach((value) => used.add(value));
    slots.push({ values: [...matched] });
  });
  values.forEach((value) => {
    if (used.has(value)) return;
    used.add(value);
    const pair = values.find((candidate) => !used.has(candidate) && reciprocal(value, candidate));
    if (pair) used.add(pair);
    slots.push({ values: pair ? [value, pair] : [value] });
  });
  return slots;
}

export function aspectRatioRect(value: string): AspectRatioRect | null {
  const ratio = parsedRatio(value);
  if (!ratio) return null;
  const maximum = 16;
  const minimum = 2;
  let width = maximum;
  let height = maximum;
  if (ratio.width > ratio.height) height = Math.max(minimum, maximum * ratio.height / ratio.width);
  else if (ratio.height > ratio.width) width = Math.max(minimum, maximum * ratio.width / ratio.height);
  return {
    x: (20 - width) / 2,
    y: (20 - height) / 2,
    width,
    height,
  };
}

const SVG_NAMESPACE = "http://www.w3.org/2000/svg";

export function createAspectRatioIcon(value: string): SVGSVGElement | null {
  const geometry = aspectRatioRect(value);
  if (!geometry) return null;
  const svg = document.createElementNS(SVG_NAMESPACE, "svg");
  svg.classList.add("aspect-ratio-icon");
  svg.setAttribute("viewBox", "0 0 20 20");
  svg.setAttribute("aria-hidden", "true");
  svg.setAttribute("focusable", "false");
  const rect = document.createElementNS(SVG_NAMESPACE, "rect");
  rect.setAttribute("x", String(geometry.x));
  rect.setAttribute("y", String(geometry.y));
  rect.setAttribute("width", String(geometry.width));
  rect.setAttribute("height", String(geometry.height));
  rect.setAttribute("rx", "1");
  rect.setAttribute("fill", "none");
  rect.setAttribute("stroke", "currentColor");
  rect.setAttribute("stroke-width", "1.35");
  rect.setAttribute("vector-effect", "non-scaling-stroke");
  svg.append(rect);
  return svg;
}

export function decorateLegacyAspectRatioButtons(root: ParentNode = document): void {
  root.querySelectorAll<HTMLButtonElement>("#ratioGroup .radio-btn[data-val]").forEach((button) => {
    if (button.querySelector(".aspect-ratio-icon")) return;
    const value = button.dataset.val || button.textContent?.trim() || "";
    const icon = createAspectRatioIcon(value);
    if (!icon) return;
    const label = document.createElement("span");
    label.className = "aspect-ratio-label";
    label.textContent = value;
    button.replaceChildren(icon, label);
  });
}

export function initAspectRatioControlsFeature(): void {
  decorateLegacyAspectRatioButtons();
}

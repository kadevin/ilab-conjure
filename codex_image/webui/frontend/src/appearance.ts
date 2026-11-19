export type BackgroundTone = "neutral" | "warm" | "cool" | "tinted";
export interface Appearance {
  version: 1;
  preset: "default" | "custom";
  primary: string;
  background: BackgroundTone;
}
export const APPEARANCE_STORAGE_KEY = "ilab-conjure-appearance";
export const APPEARANCE_CHANGE_EVENT = "ilab-appearance-change";
export const DEFAULT_APPEARANCE: Appearance = { version: 1, preset: "default", primary: "#457B66", background: "tinted" };
export function normalizeAppearance(value: unknown): Appearance {
  const v = value as Partial<Appearance> | null;
  if (!v || v.version !== 1 || !["default", "custom"].includes(v.preset || "")
    || typeof v.primary !== "string" || !/^#[\da-f]{6}$/i.test(v.primary)
    || !["neutral", "warm", "cool", "tinted"].includes(v.background || "")) return { ...DEFAULT_APPEARANCE };
  return v.preset === "default" ? { ...DEFAULT_APPEARANCE }
    : { version: 1, preset: "custom", primary: v.primary.toUpperCase(), background: v.background! };
}
export function readAppearance(storage?: Pick<Storage, "getItem">): Appearance {
  try { return normalizeAppearance(JSON.parse((storage ?? localStorage).getItem(APPEARANCE_STORAGE_KEY) || "null")); }
  catch { return { ...DEFAULT_APPEARANCE }; }
}
export function persistAppearance(value: Appearance, storage?: Pick<Storage, "setItem">): boolean {
  try { (storage ?? localStorage).setItem(APPEARANCE_STORAGE_KEY, JSON.stringify(normalizeAppearance(value))); return true; }
  catch { return false; }
}

const linear = (v: number) => v <= .04045 ? v / 12.92 : ((v + .055) / 1.055) ** 2.4;
const channels = (hex: string) => [1, 3, 5].map(i => parseInt(hex.slice(i, i + 2), 16) / 255);
export function colorContrast(a: string, b: string): number {
  const luminance = (hex: string) => channels(hex).map(linear).reduce((sum, v, i) => sum + v * [.2126, .7152, .0722][i]!, 0);
  const [x, y] = [luminance(a), luminance(b)].sort((a, b) => b - a);
  return (x! + .05) / (y! + .05);
}
function seedChromaHue(hex: string): [number, number] {
  const [r, g, b] = channels(hex).map(linear) as [number, number, number];
  const l = Math.cbrt(.4122214708 * r + .5363325363 * g + .0514459929 * b);
  const m = Math.cbrt(.2119034982 * r + .6806995451 * g + .1073969566 * b);
  const s = Math.cbrt(.0883024619 * r + .2817188376 * g + .6299787005 * b);
  const a = 1.9779984951 * l - 2.428592205 * m + .4505937099 * s;
  const bb = .0259040371 * l + .7827717662 * m - .808675766 * s;
  return [Math.hypot(a, bb), Math.atan2(bb, a)];
}
// OKLCH -> sRGB; reduce chroma before quantizing instead of clipping hue.
function color(lightness: number, chroma: number, hue: number): string {
  let rgb: number[] = [];
  for (let attempt = 0; attempt < 80; attempt++) {
    const a = chroma * Math.cos(hue), b = chroma * Math.sin(hue);
    const l = (lightness + .3963377774 * a + .2158037573 * b) ** 3;
    const m = (lightness - .1055613458 * a - .0638541728 * b) ** 3;
    const s = (lightness - .0894841775 * a - 1.291485548 * b) ** 3;
    rgb = [4.0767416621 * l - 3.3077115913 * m + .2309699292 * s,
      -1.2684380046 * l + 2.6097574011 * m - .3413193965 * s,
      -.0041960863 * l - .7034186147 * m + 1.707614701 * s];
    if (rgb.every(v => v >= -.00001 && v <= 1.00001)) break;
    chroma *= .85;
  }
  return "#" + rgb.map(v => Math.max(0, Math.min(255, Math.round(255 * (v <= .0031308 ? 12.92 * v : 1.055 * v ** (1 / 2.4) - .055))))).map(v => v.toString(16).padStart(2, "0")).join("");
}
export function appearanceTokens(value: Appearance, dark: boolean): Record<string, string> {
  const appearance = normalizeAppearance(value);
  if (appearance.preset === "default") return {};
  const [c, h] = seedChromaHue(appearance.primary);
  const hue = appearance.background === "warm" ? 80 * Math.PI / 180
    : appearance.background === "cool" ? 250 * Math.PI / 180 : h;
  const tint = appearance.background === "neutral" || (appearance.background === "tinted" && c < .005) ? 0 : .012;
  const neutral = (l: number) => color(l, tint, hue);
  const brand = (l: number) => color(l, Math.min(c, .16), h);
  const surface = neutral(dark ? .24 : .995);
  let primaryL = dark ? .77 : .51;
  const foreground = dark ? "#101010" : "#ffffff";
  while (colorContrast(brand(primaryL), foreground) < 4.8 || colorContrast(brand(primaryL), surface) < 4.5) {
    primaryL += dark ? .005 : -.005;
    if (primaryL <= .2 || primaryL >= .9) break;
  }
  const primary = brand(primaryL);
  const selectedHover = brand(primaryL + (dark ? .035 : -.025));
  const selectedPressed = brand(primaryL - .045);
  const soft = color(dark ? .32 : .93, Math.min(c, .035), h);
  const tokens: Record<string, string> = {
    bg: neutral(dark ? .18 : .97), surface, "surface-soft": neutral(dark ? .28 : .98),
    line: neutral(dark ? .37 : .89), text: neutral(dark ? .95 : .24),
    "text-secondary": neutral(dark ? .82 : .37), muted: neutral(dark ? .64 : .6),
    "text-muted": neutral(dark ? .73 : .46), "control-border": neutral(dark ? .62 : .55),
    primary, "primary-foreground": foreground, "primary-strong": brand(dark ? .87 : .4), "primary-light": soft,
    "action-shadow": `${primary}29`,
    "secondary-action-surface": soft, "secondary-action-hover": color(dark ? .39 : .87, Math.min(c, .04), h),
    "secondary-action-pressed": color(dark ? .44 : .81, Math.min(c, .04), h),
    "model-family-rail-surface": neutral(dark ? .34 : .92), "model-family-indicator-surface": surface,
    "task-card-surface-selected-hover": selectedHover, "task-card-surface-selected-pressed": selectedPressed,
    "task-card-selected-secondary": foreground,
    "task-card-drawer-archive-surface": primary, "task-card-drawer-archive-text": foreground,
    "history-stack-layer-1": neutral(dark ? .44 : .9), "history-stack-layer-2": neutral(dark ? .37 : .81),
    "history-stack-layer-3": neutral(dark ? .3 : .72),
    code: neutral(.15), "code-text": neutral(.9),
    "scrollbar-track": color(dark ? .28 : .94, Math.min(c, .018), h), "scrollbar-thumb": brand(dark ? .62 : .58),
    "scrollbar-thumb-hover": primary,
    "shadow-rgb": "0, 0, 0",
    "viewer-overlay": `${color(.16, Math.min(c, .025), h)}d1`,
    "viewer-surface": color(.25, Math.min(c, .025), h),
    "viewer-hover": color(.34, Math.min(c, .035), h),
    "viewer-foreground": "#f5f5f5", "viewer-muted": "#d6d6d6",
    "viewer-border": "#ffffff33", "viewer-accent": brand(.82), "viewer-accent-foreground": "#101010",
    "focus-ring": primary, "task-card-focus-ring": primary,
    "shadow-sm": `0 2px 8px ${dark ? "#00000033" : "#0000000a"}`,
    "shadow-popover": `0 14px 34px ${dark ? "#00000061" : "#00000029"}`,
    "shadow-modal": `0 24px 80px ${dark ? "#0000007a" : "#0000003d"}`,
    overlay: dark ? "#0000009e" : "#00000075", "overlay-subtle": dark ? "#00000070" : "#00000047",
  };
  const textSurfaces = ["bg", "surface", "surface-soft", "primary-light", "secondary-action-hover", "secondary-action-pressed"];
  for (const [name, initial] of [["text", dark ? .95 : .24], ["text-secondary", dark ? .82 : .37], ["text-muted", dark ? .73 : .46]] as const) {
    let l = initial;
    while (textSurfaces.some(key => colorContrast(neutral(l), tokens[key]!) < 4.6) && l > .1 && l < .99) l += dark ? .005 : -.005;
    tokens[name] = neutral(l);
  }
  // Status text must remain legible even on a user-selected hue.
  for (const [name, hue] of [["danger", 25], ["info", 255], ["waiting", 85]] as const) {
    let l = dark ? .3 : .95;
    const statusColor = () => color(l, .06, hue * Math.PI / 180);
    while ([primary, selectedHover, selectedPressed].some(bg => colorContrast(statusColor(), bg) < 4.6) && l > .1 && l < .99) l += dark ? -.005 : .005;
    tokens[`task-card-selected-${name}`] = statusColor();
  }
  return tokens;
}

export function applyAppearance(value: Appearance): void {
  if (typeof document === "undefined") return;
  const appearance = normalizeAppearance(value);
  let style = document.getElementById("appearance-tokens") as HTMLStyleElement | null;
  if (!style) { style = document.createElement("style"); style.id = "appearance-tokens"; document.head.append(style); }
  style.textContent = [false, true].map(dark => {
    const tokens = appearanceTokens(appearance, dark);
    return `:root[data-theme="${dark ? "dark" : "light"}"][data-appearance="custom"]{${Object.entries(tokens).map(([k, v]) => `--${k}:${v};`).join("")}}`;
  }).join("\n");
  document.documentElement.dataset.appearance = appearance.preset;
  // Bootstrap and the main bundle share this node; bind the theme observer once.
  style.dataset.appearance = JSON.stringify(appearance);
  const syncChrome = () => {
    const current = normalizeAppearance(JSON.parse(style!.dataset.appearance!));
    const dark = document.documentElement.dataset.theme === "dark";
    const tokens = appearanceTokens(current, dark);
    const primary = tokens.primary || (dark ? "#72b79b" : "#457b66");
    const background = tokens.bg || (dark ? "#101815" : "#f3f6f4");
    document.querySelector('meta[name="theme-color"]')?.setAttribute("content", primary);
    const manifest = document.querySelector<HTMLLinkElement>('link[rel="manifest"]');
    if (manifest) manifest.setAttribute("href", `/manifest.webmanifest?${new URLSearchParams({ theme_color: primary, background_color: background })}`);
  };
  syncChrome();
  if (!style.dataset.chromeBound) {
    style.dataset.chromeBound = "true";
    new MutationObserver(syncChrome).observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
  }
}

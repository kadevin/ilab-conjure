(() => {
  // codex_image/webui/frontend/src/appearance.ts
  var APPEARANCE_STORAGE_KEY = "ilab-conjure-appearance";
  var DEFAULT_APPEARANCE = { version: 1, preset: "default", primary: "#457B66", background: "tinted" };
  function normalizeAppearance(value) {
    const v = value;
    if (!v || v.version !== 1 || !["default", "custom"].includes(v.preset || "") || typeof v.primary !== "string" || !/^#[\da-f]{6}$/i.test(v.primary) || !["neutral", "warm", "cool", "tinted"].includes(v.background || "")) return { ...DEFAULT_APPEARANCE };
    return v.preset === "default" ? { ...DEFAULT_APPEARANCE } : { version: 1, preset: "custom", primary: v.primary.toUpperCase(), background: v.background };
  }
  function readAppearance(storage) {
    try {
      return normalizeAppearance(JSON.parse((storage ?? localStorage).getItem(APPEARANCE_STORAGE_KEY) || "null"));
    } catch {
      return { ...DEFAULT_APPEARANCE };
    }
  }
  var linear = (v) => v <= 0.04045 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4;
  var channels = (hex) => [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255);
  function colorContrast(a, b) {
    const luminance = (hex) => channels(hex).map(linear).reduce((sum, v, i) => sum + v * [0.2126, 0.7152, 0.0722][i], 0);
    const [x, y] = [luminance(a), luminance(b)].sort((a2, b2) => b2 - a2);
    return (x + 0.05) / (y + 0.05);
  }
  function seedChromaHue(hex) {
    const [r, g, b] = channels(hex).map(linear);
    const l = Math.cbrt(0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b);
    const m = Math.cbrt(0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b);
    const s = Math.cbrt(0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b);
    const a = 1.9779984951 * l - 2.428592205 * m + 0.4505937099 * s;
    const bb = 0.0259040371 * l + 0.7827717662 * m - 0.808675766 * s;
    return [Math.hypot(a, bb), Math.atan2(bb, a)];
  }
  function color(lightness, chroma, hue) {
    let rgb = [];
    for (let attempt = 0; attempt < 80; attempt++) {
      const a = chroma * Math.cos(hue), b = chroma * Math.sin(hue);
      const l = (lightness + 0.3963377774 * a + 0.2158037573 * b) ** 3;
      const m = (lightness - 0.1055613458 * a - 0.0638541728 * b) ** 3;
      const s = (lightness - 0.0894841775 * a - 1.291485548 * b) ** 3;
      rgb = [
        4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s,
        -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s,
        -0.0041960863 * l - 0.7034186147 * m + 1.707614701 * s
      ];
      if (rgb.every((v) => v >= -1e-5 && v <= 1.00001)) break;
      chroma *= 0.85;
    }
    return "#" + rgb.map((v) => Math.max(0, Math.min(255, Math.round(255 * (v <= 31308e-7 ? 12.92 * v : 1.055 * v ** (1 / 2.4) - 0.055))))).map((v) => v.toString(16).padStart(2, "0")).join("");
  }
  function appearanceTokens(value, dark) {
    const appearance = normalizeAppearance(value);
    if (appearance.preset === "default") return {};
    const [c, h] = seedChromaHue(appearance.primary);
    const hue = appearance.background === "warm" ? 80 * Math.PI / 180 : appearance.background === "cool" ? 250 * Math.PI / 180 : h;
    const tint = appearance.background === "neutral" || appearance.background === "tinted" && c < 5e-3 ? 0 : 0.012;
    const neutral = (l) => color(l, tint, hue);
    const brand = (l) => color(l, Math.min(c, 0.16), h);
    const surface = neutral(dark ? 0.24 : 0.995);
    let primaryL = dark ? 0.77 : 0.51;
    const foreground = dark ? "#101010" : "#ffffff";
    while (colorContrast(brand(primaryL), foreground) < 4.8 || colorContrast(brand(primaryL), surface) < 4.5) {
      primaryL += dark ? 5e-3 : -5e-3;
      if (primaryL <= 0.2 || primaryL >= 0.9) break;
    }
    const primary = brand(primaryL);
    const selectedHover = brand(primaryL + (dark ? 0.035 : -0.025));
    const selectedPressed = brand(primaryL - 0.045);
    const soft = color(dark ? 0.32 : 0.93, Math.min(c, 0.035), h);
    const tokens = {
      bg: neutral(dark ? 0.18 : 0.97),
      surface,
      "surface-soft": neutral(dark ? 0.28 : 0.98),
      line: neutral(dark ? 0.37 : 0.89),
      text: neutral(dark ? 0.95 : 0.24),
      "text-secondary": neutral(dark ? 0.82 : 0.37),
      muted: neutral(dark ? 0.64 : 0.6),
      "text-muted": neutral(dark ? 0.73 : 0.46),
      "control-border": neutral(dark ? 0.62 : 0.55),
      primary,
      "primary-foreground": foreground,
      "primary-strong": brand(dark ? 0.87 : 0.4),
      "primary-light": soft,
      "action-shadow": `${primary}29`,
      "secondary-action-surface": soft,
      "secondary-action-hover": color(dark ? 0.39 : 0.87, Math.min(c, 0.04), h),
      "secondary-action-pressed": color(dark ? 0.44 : 0.81, Math.min(c, 0.04), h),
      "model-family-rail-surface": neutral(dark ? 0.34 : 0.92),
      "model-family-indicator-surface": surface,
      "task-card-surface-selected-hover": selectedHover,
      "task-card-surface-selected-pressed": selectedPressed,
      "task-card-selected-secondary": foreground,
      "task-card-drawer-archive-surface": primary,
      "task-card-drawer-archive-text": foreground,
      "history-stack-layer-1": neutral(dark ? 0.44 : 0.9),
      "history-stack-layer-2": neutral(dark ? 0.37 : 0.81),
      "history-stack-layer-3": neutral(dark ? 0.3 : 0.72),
      code: neutral(0.15),
      "code-text": neutral(0.9),
      "scrollbar-track": color(dark ? 0.28 : 0.94, Math.min(c, 0.018), h),
      "scrollbar-thumb": brand(dark ? 0.62 : 0.58),
      "scrollbar-thumb-hover": primary,
      "shadow-rgb": "0, 0, 0",
      "viewer-overlay": `${color(0.16, Math.min(c, 0.025), h)}d1`,
      "viewer-surface": color(0.25, Math.min(c, 0.025), h),
      "viewer-hover": color(0.34, Math.min(c, 0.035), h),
      "viewer-foreground": "#f5f5f5",
      "viewer-muted": "#d6d6d6",
      "viewer-border": "#ffffff33",
      "viewer-accent": brand(0.82),
      "viewer-accent-foreground": "#101010",
      "focus-ring": primary,
      "task-card-focus-ring": primary,
      "shadow-sm": `0 2px 8px ${dark ? "#00000033" : "#0000000a"}`,
      "shadow-popover": `0 14px 34px ${dark ? "#00000061" : "#00000029"}`,
      "shadow-modal": `0 24px 80px ${dark ? "#0000007a" : "#0000003d"}`,
      overlay: dark ? "#0000009e" : "#00000075",
      "overlay-subtle": dark ? "#00000070" : "#00000047"
    };
    const textSurfaces = ["bg", "surface", "surface-soft", "primary-light", "secondary-action-hover", "secondary-action-pressed"];
    for (const [name, initial] of [["text", dark ? 0.95 : 0.24], ["text-secondary", dark ? 0.82 : 0.37], ["text-muted", dark ? 0.73 : 0.46]]) {
      let l = initial;
      while (textSurfaces.some((key) => colorContrast(neutral(l), tokens[key]) < 4.6) && l > 0.1 && l < 0.99) l += dark ? 5e-3 : -5e-3;
      tokens[name] = neutral(l);
    }
    for (const [name, hue2] of [["danger", 25], ["info", 255], ["waiting", 85]]) {
      let l = dark ? 0.3 : 0.95;
      const statusColor = () => color(l, 0.06, hue2 * Math.PI / 180);
      while ([primary, selectedHover, selectedPressed].some((bg) => colorContrast(statusColor(), bg) < 4.6) && l > 0.1 && l < 0.99) l += dark ? -5e-3 : 5e-3;
      tokens[`task-card-selected-${name}`] = statusColor();
    }
    return tokens;
  }
  function applyAppearance(value) {
    if (typeof document === "undefined") return;
    const appearance = normalizeAppearance(value);
    let style = document.getElementById("appearance-tokens");
    if (!style) {
      style = document.createElement("style");
      style.id = "appearance-tokens";
      document.head.append(style);
    }
    style.textContent = [false, true].map((dark) => {
      const tokens = appearanceTokens(appearance, dark);
      return `:root[data-theme="${dark ? "dark" : "light"}"][data-appearance="custom"]{${Object.entries(tokens).map(([k, v]) => `--${k}:${v};`).join("")}}`;
    }).join("\n");
    document.documentElement.dataset.appearance = appearance.preset;
    style.dataset.appearance = JSON.stringify(appearance);
    const syncChrome = () => {
      const current = normalizeAppearance(JSON.parse(style.dataset.appearance));
      const dark = document.documentElement.dataset.theme === "dark";
      const tokens = appearanceTokens(current, dark);
      const primary = tokens.primary || (dark ? "#72b79b" : "#457b66");
      const background = tokens.bg || (dark ? "#101815" : "#f3f6f4");
      document.querySelector('meta[name="theme-color"]')?.setAttribute("content", primary);
      const manifest = document.querySelector('link[rel="manifest"]');
      if (manifest) manifest.setAttribute("href", `/manifest.webmanifest?${new URLSearchParams({ theme_color: primary, background_color: background })}`);
    };
    syncChrome();
    if (!style.dataset.chromeBound) {
      style.dataset.chromeBound = "true";
      new MutationObserver(syncChrome).observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
    }
  }

  // codex_image/webui/frontend/src/appearance-bootstrap.ts
  applyAppearance(readAppearance());
})();
//# sourceMappingURL=appearance-bootstrap.js.map

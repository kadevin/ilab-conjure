// @ts-nocheck
import { getLegacyBridge } from "./state";
import { formatTranslation, translate } from "./i18n";

const DEFAULT_COLOR_CODE = "#FFFFFF";
const DEFAULT_COLOR_SWATCHES = ["#FFFFFF", "#111111", "#F6E8D8", "#E6F0EC", "#457B66", "#F4B183", "#B7D7F0", "#F8D7DA"];
const DEFAULT_COLOR_SWATCH_NAME_KEYS = [
  "colors.white",
  "colors.black",
  "colors.warmBeige",
  "colors.lightGreen",
  "colors.brandGreen",
  "colors.peachOrange",
  "colors.lightBlue",
  "colors.lightPink",
];
const COLOR_PALETTE_ENDPOINT = "/api/color-palette";
const COLOR_PALETTE_IMPORT_ENDPOINT = "/api/color-palette/import";

const bridge = getLegacyBridge();
const state = bridge.state;
const els = bridge.els;

let colorPaletteInitialized = false;

function legacyMethod(name, ...args) {
  const method = getLegacyBridge().methods[name];
  if (typeof method !== "function") {
    throw new Error("Legacy method " + name + " is not initialized");
  }
  return method(...args);
}

function setStatus(message, type) { legacyMethod("setStatus", message, type); }
function renderColorSuggest(...args) { return legacyMethod("renderColorSuggest", ...args); }
function updateColorSuggest(...args) { return legacyMethod("updateColorSuggest", ...args); }

function defaultColorPalette() {
  return {
    version: 1,
    favorites: DEFAULT_COLOR_SWATCHES.map((hex, index) => ({
      name: translate(DEFAULT_COLOR_SWATCH_NAME_KEYS[index] || "") || `Color ${index + 1}`,
      hex,
      order: (index + 1) * 10,
    })),
    recent_colors: [],
    recent_limit: 6,
  };
}

function normalizeColorPalette(value) {
  const fallback = defaultColorPalette();
  const palette = value && typeof value === "object" ? value : {};
  const favorites = Array.isArray(palette.favorites)
    ? palette.favorites.map((item, index) => normalizeColorPaletteItem(item, index)).filter(Boolean)
    : fallback.favorites;
  const recentLimit = Number.isFinite(Number(palette.recent_limit))
    ? Math.min(24, Math.max(0, Number.parseInt(palette.recent_limit, 10)))
    : fallback.recent_limit;
  const recentColors = Array.isArray(palette.recent_colors)
    ? dedupeColors(palette.recent_colors.map(normalizeHexColor).filter(Boolean)).slice(0, recentLimit)
    : [];
  return {
    version: 1,
    favorites,
    recent_colors: recentColors,
    recent_limit: recentLimit,
  };
}

function normalizeColorPaletteItem(item, index) {
  if (!item || typeof item !== "object") return null;
  const hex = normalizeHexColor(item.hex);
  if (!hex) return null;
  return {
    name: String(item.name || `Color ${index + 1}`).trim() || `Color ${index + 1}`,
    hex,
    order: Number.isFinite(Number(item.order)) ? Number.parseInt(item.order, 10) : (index + 1) * 10,
  };
}

function dedupeColors(colors) {
  const result = [];
  colors.forEach((color) => {
    if (color && !result.includes(color)) result.push(color);
  });
  return result;
}

async function refreshColorPalette() {
  try {
    const response = await fetch(COLOR_PALETTE_ENDPOINT);
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || translate("colors.loadFailed"));
    state.colorPalette = normalizeColorPalette(data.palette);
    state.selectedColorCode = state.colorPalette.recent_colors[0] || favoriteColorsForDisplay()[0]?.hex || DEFAULT_COLOR_CODE;
    updateColorSuggest();
  } catch (error) {
    console.warn(error.message || translate("colors.loadFailed"));
    state.colorPalette = defaultColorPalette();
  }
}

async function persistColorPalette(payload) {
  const response = await fetch(COLOR_PALETTE_ENDPOINT, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const data = await response.json();
  if (!response.ok) throw new Error(data.detail || translate("colors.saveFailed"));
  state.colorPalette = normalizeColorPalette(data.palette);
  return state.colorPalette;
}

async function importColorPalette(file) {
  if (!file) return;
  const form = new FormData();
  form.append("file", file);
  const response = await fetch(COLOR_PALETTE_IMPORT_ENDPOINT, {
    method: "POST",
    body: form,
  });
  const data = await response.json();
  if (!response.ok) throw new Error(data.detail || translate("colors.importFailed"));
  state.colorPalette = normalizeColorPalette(data.palette);
  renderColorSuggest({ query: state.selectedColorCode.slice(1), range: state.activeColorRange });
  els.colorSuggest?.classList.remove("hidden");
  els.promptEditor?.focus({ preventScroll: true });
  setStatus(formatTranslation("colors.importedCount", { count: data.imported || 0 }), "ok");
}

function toggleColorPaletteManageMode() {
  state.colorPaletteManageMode = !state.colorPaletteManageMode;
  renderColorSuggest({ query: state.selectedColorCode.slice(1), range: state.activeColorRange });
  els.colorSuggest?.classList.remove("hidden");
  els.promptEditor?.focus({ preventScroll: true });
}

function favoriteColorsForDisplay() {
  const favorites = Array.isArray(state.colorPalette?.favorites) ? state.colorPalette.favorites : [];
  return Array.isArray(state.colorPalette?.favorites) ? favorites : defaultColorPalette().favorites;
}

function recentColorsForDisplay() {
  const favoriteHex = new Set(favoriteColorsForDisplay().map((item) => item.hex));
  return (state.colorPalette?.recent_colors || []).filter((color) => !favoriteHex.has(color));
}

function rememberRecentColor(colorCode) {
  const normalized = normalizeHexColor(colorCode);
  if (!normalized) return;
  const recentLimit = state.colorPalette?.recent_limit ?? 6;
  const recentColors = dedupeColors([normalized, ...(state.colorPalette?.recent_colors || [])]).slice(0, recentLimit);
  state.colorPalette = { ...state.colorPalette, recent_colors: recentColors };
  state.selectedColorCode = normalized;
  void persistColorPalette({ recent_colors: recentColors }).catch((error) => {
    console.warn(error.message || translate("colors.recentSaveFailed"));
  });
}

async function saveFavoriteColor() {
  const input = els.colorSuggest?.querySelector("[data-color-hex-input]");
  const nameInput = els.colorSuggest?.querySelector("[data-color-name-input]");
  const normalized = normalizeHexColor(input?.value || state.selectedColorCode);
  if (!normalized) return;
  const favorites = favoriteColorsForDisplay().filter((item) => item.hex !== normalized);
  favorites.push({
    name: String(nameInput?.value || normalized).trim() || normalized,
    hex: normalized,
    order: (favorites.length + 1) * 10,
  });
  try {
    await persistColorPalette({ favorites });
    renderColorSuggest({ query: normalized.slice(1), range: state.activeColorRange });
    els.colorSuggest?.classList.remove("hidden");
    els.promptEditor?.focus({ preventScroll: true });
  } catch (error) {
    console.warn(error.message || translate("colors.favoriteSaveFailed"));
  }
}

async function removeFavoriteColor(colorCode) {
  const normalized = normalizeHexColor(colorCode);
  if (!normalized) return;
  const favorites = favoriteColorsForDisplay().filter((item) => item.hex !== normalized);
  try {
    await persistColorPalette({ favorites });
    renderColorSuggest({ query: state.selectedColorCode.slice(1), range: state.activeColorRange });
    els.colorSuggest?.classList.remove("hidden");
    els.promptEditor?.focus({ preventScroll: true });
  } catch (error) {
    console.warn(error.message || translate("colors.favoriteDeleteFailed"));
  }
}

function normalizeHexColor(value) {
  const raw = String(value || "").trim().replace(/^#/, "");
  if (/^[0-9a-fA-F]{3}$/.test(raw)) {
    return `#${raw.split("").map((char) => char + char).join("").toUpperCase()}`;
  }
  if (/^[0-9a-fA-F]{6}$/.test(raw)) {
    return `#${raw.toUpperCase()}`;
  }
  return "";
}

export function initColorPaletteFeature() {
  if (colorPaletteInitialized) return;
  colorPaletteInitialized = true;
  Object.assign(getLegacyBridge().methods, {
    defaultColorPalette,
    normalizeColorPalette,
    normalizeColorPaletteItem,
    dedupeColors,
    refreshColorPalette,
    persistColorPalette,
    importColorPalette,
    toggleColorPaletteManageMode,
    favoriteColorsForDisplay,
    recentColorsForDisplay,
    rememberRecentColor,
    saveFavoriteColor,
    removeFavoriteColor,
    normalizeHexColor,
  });
}

import { getLegacyBridge } from "./state";
import { positionPromptPopoverAtAnchor } from "./prompt-popover-position";
import { formatTranslation, translate } from "./i18n";

const DEFAULT_COLOR_CODE = "#FFFFFF";
const COLOR_PALETTE_EXPORT_CSS_ENDPOINT = "/api/color-palette/export.css";

const bridge = getLegacyBridge();
const state = bridge.state;
const els = bridge.els;

function legacyMethod(name: string, ...args: any[]): any {
  const method = getLegacyBridge().methods[name];
  if (typeof method !== "function") {
    throw new Error("Legacy method " + name + " is not initialized");
  }
  return method(...args);
}

function escapeHtml(value: any): string { return legacyMethod("escapeHtml", value); }
function setStatus(message: any, type?: any): void { legacyMethod("setStatus", message, type); }
function normalizeHexColor(value: any): string { return legacyMethod("normalizeHexColor", value); }
function favoriteColorsForDisplay(): any[] { return legacyMethod("favoriteColorsForDisplay"); }
function recentColorsForDisplay(): any[] { return legacyMethod("recentColorsForDisplay"); }
function saveFavoriteColor(): Promise<void> { return legacyMethod("saveFavoriteColor"); }
function toggleColorPaletteManageMode(): void { legacyMethod("toggleColorPaletteManageMode"); }
function importColorPalette(file: any): Promise<void> { return legacyMethod("importColorPalette", file); }
function removeFavoriteColor(colorCode: any): Promise<void> { return legacyMethod("removeFavoriteColor", colorCode); }
function rememberRecentColor(colorCode: any): void { legacyMethod("rememberRecentColor", colorCode); }
function getPromptText(): string { return legacyMethod("getPromptText"); }
function appendPromptText(text: any): void { legacyMethod("appendPromptText", text); }
function syncPromptFromEditor(): void { legacyMethod("syncPromptFromEditor"); }
function updatePromptCount(): void { legacyMethod("updatePromptCount"); }
function updateRequestPreview(): void { legacyMethod("updateRequestPreview"); }
function mentionRangeRect(range: any): any { return legacyMethod("mentionRangeRect", range); }
function syncPromptAfterChipMutation(): void { legacyMethod("syncPromptAfterChipMutation"); }
function setCaretAfterNode(node: any): void { legacyMethod("setCaretAfterNode", node); }
function removePromptGalleryChip(chip: any): void { legacyMethod("removePromptGalleryChip", chip); }

function updateColorSuggest() {
  if (!els.colorSuggest || !els.promptEditor) return;
  const match = activeColorMatch();
  if (!match) {
    hideColorSuggest();
    return;
  }
  renderColorSuggest(match);
  positionColorSuggestAtCaret(match);
  els.colorSuggest.classList.remove("hidden");
}

function activeColorMatch() {
  const selection = window.getSelection();
  if (!selection || !selection.rangeCount || !selection.isCollapsed || !els.promptEditor) return null;
  if (!els.promptEditor.contains(selection.anchorNode)) return null;
  const selectionRange = selection.getRangeAt(0);
  let container = selectionRange.startContainer;
  let offset = selectionRange.startOffset;
  if (container.nodeType === Node.ELEMENT_NODE) {
    const previousNode = container.childNodes[offset - 1];
    if (previousNode?.nodeType !== Node.TEXT_NODE) return null;
    container = previousNode;
    offset = (previousNode.textContent || "").length;
  }
  if (container.nodeType !== Node.TEXT_NODE) return null;
  const textBeforeCaret = (container.textContent || "").slice(0, offset);
  const match = textBeforeCaret.match(/#([0-9a-fA-F]{0,6})$/);
  if (!match) return null;
  const tokenStart = offset - match[0].length;
  const range = document.createRange();
  range.setStart(container, tokenStart);
  range.setEnd(container, offset);
  return {
    query: match[1] || "",
    range,
  };
}

function renderColorSuggest(match: any) {
  if (!els.colorSuggest) return;
  state.activeColorRange = match.range ? match.range.cloneRange() : null;
  const queryColor = match.query ? normalizeHexColor(`#${match.query}`) : "";
  const favoriteColors = favoriteColorsForDisplay();
  const recentColors = recentColorsForDisplay();
  const selected = queryColor || state.selectedColorCode || recentColors[0] || favoriteColors[0]?.hex || DEFAULT_COLOR_CODE;
  state.selectedColorCode = selected;
  const editingColor = state.activeColorChip ? normalizeHexColor(state.activeColorChip.dataset.colorCode) || DEFAULT_COLOR_CODE : "";
  const isEditingDirty = Boolean(editingColor && selected !== editingColor);
  const typedValue = match.query ? `#${match.query.toUpperCase()}` : selected;
  const actionLabel = state.activeColorChip ? translate("colors.update") : translate("colors.insert");
  const swatchRowClass = state.colorPaletteManageMode ? "color-swatch-row is-managing" : "color-swatch-row";
  const swatchButtons = [
    ...favoriteColors.map((item: any) => colorSwatchButton(item.hex, item.name, { removable: state.colorPaletteManageMode })),
    ...recentColors.map((color: any) => colorSwatchButton(color, translate("colors.recentLabel"))),
  ].join("");
  els.colorSuggest.innerHTML = `
    <div class="color-suggest-main" data-color-original="${escapeHtml(editingColor)}">
      <div class="color-value-control${isEditingDirty ? " is-dirty" : ""}" data-color-value-control>
        <label class="color-picker-control" title="${escapeHtml(translate("colors.pick"))}" aria-label="${escapeHtml(translate("colors.pick"))}">
          <input class="color-picker-input" type="color" value="${escapeHtml(selected)}" data-color-picker>
          <span class="color-picker-swatch" style="--active-color: ${escapeHtml(selected)}">
            <svg class="color-picker-icon" viewBox="0 0 24 24" aria-hidden="true" focusable="false">
              <path d="M14.5 4.5l5 5-8.8 8.8H6.5v-4.2l8-9.6z"></path>
              <path d="M12.7 6.4l4.9 4.9"></path>
            </svg>
            <span class="color-picker-label">${escapeHtml(translate("colors.pickShort"))}</span>
          </span>
        </label>
        <input class="color-hex-input" type="text" value="${escapeHtml(typedValue)}" maxlength="7" spellcheck="false" aria-label="${escapeHtml(translate("colors.hexValue"))}" data-color-hex-input>
      </div>
      <button class="ghost-button text-sm color-insert-button${isEditingDirty ? " is-dirty" : ""}" type="button" data-insert-color${editingColor && !isEditingDirty ? " disabled" : ""}>${actionLabel}</button>
      <div class="color-suggest-actions">
        <button class="ghost-button text-sm" type="button" data-save-favorite-color>${escapeHtml(translate("colors.save"))}</button>
        <a class="ghost-button text-sm color-export-link" href="${COLOR_PALETTE_EXPORT_CSS_ENDPOINT}" target="_blank" rel="noopener" data-color-palette-export>${escapeHtml(translate("colors.exportPs"))}</a>
        <label class="ghost-button text-sm color-import-label" data-color-palette-import>
          ${escapeHtml(translate("colors.importPs"))}
          <input class="color-import-input" type="file" accept=".aco,.css,.html,.htm,.svg,.txt" data-color-palette-import-input>
        </label>
        <button class="ghost-button text-sm color-manage-button" type="button" aria-pressed="${state.colorPaletteManageMode ? "true" : "false"}" data-color-palette-manage>${escapeHtml(state.colorPaletteManageMode ? translate("colors.done") : translate("colors.manage"))}</button>
      </div>
      <div class="color-update-hint${isEditingDirty ? "" : " hidden"}" role="status" aria-live="polite" data-color-update-hint>${escapeHtml(translate("colors.pendingUpdate"))}</div>
    </div>
    <div class="${swatchRowClass}" aria-label="${escapeHtml(translate("colors.favorites"))}">
      ${swatchButtons}
    </div>
  `;
  bindColorSuggestEvents();
}

function colorNameForHex(colorCode: any) {
  const normalized = normalizeHexColor(colorCode);
  if (!normalized) return "";
  return favoriteColorsForDisplay().find((item: any) => item.hex === normalized)?.name || "";
}

function colorSwatchButton(color: any, label: any = "", { removable = false } = {}) {
  const normalized = normalizeHexColor(color) || DEFAULT_COLOR_CODE;
  const deleteLabel = escapeHtml(formatTranslation("colors.deleteFavorite", { name: label || normalized }));
  return `
    <span class="color-swatch-item">
      <button class="color-swatch-button" type="button" title="${escapeHtml(label ? `${label} ${normalized}` : normalized)}" data-color-swatch="${escapeHtml(normalized)}" style="--swatch-color: ${escapeHtml(normalized)}">
        <span>${escapeHtml(label ? `${label} ${normalized}` : normalized)}</span>
      </button>
      ${removable ? `<button class="color-swatch-remove" type="button" title="${deleteLabel}" aria-label="${deleteLabel}" data-remove-favorite-color="${escapeHtml(normalized)}">
        <svg class="color-swatch-remove-icon" viewBox="0 0 24 24" aria-hidden="true" focusable="false">
          <path d="M7 7L17 17M17 7L7 17"></path>
        </svg>
      </button>` : ""}
    </span>
  `;
}

function bindColorSuggestEvents() {
  if (!els.colorSuggest) return;
  const picker = els.colorSuggest.querySelector("[data-color-picker]");
  const input = els.colorSuggest.querySelector("[data-color-hex-input]");
  const insert = els.colorSuggest.querySelector("[data-insert-color]");
  const swatchPreview = els.colorSuggest.querySelector(".color-picker-swatch");
  const valueControl = els.colorSuggest.querySelector("[data-color-value-control]");
  const hint = els.colorSuggest.querySelector("[data-color-update-hint]");
  const originalColor = normalizeHexColor(els.colorSuggest.querySelector("[data-color-original]")?.dataset.colorOriginal);
  const keepPromptFocus = (event: any) => event.preventDefault();
  const updateDraftState = (value: any) => {
    const normalized = normalizeHexColor(value);
    const isDirty = Boolean(originalColor && normalized && normalized !== originalColor);
    valueControl?.classList.toggle("is-dirty", isDirty);
    insert?.classList.toggle("is-dirty", isDirty);
    if (insert && originalColor) insert.disabled = !isDirty;
    hint?.classList.toggle("hidden", !isDirty);
    if (swatchPreview && normalized) swatchPreview.style.setProperty("--active-color", normalized);
  };
  const syncColor = (value: any) => {
    const normalized = normalizeHexColor(value);
    if (!normalized) return;
    state.selectedColorCode = normalized;
    if (picker) picker.value = normalized;
    if (input) input.value = normalized;
    updateDraftState(normalized);
  };
  updateDraftState(input?.value || state.selectedColorCode);
  picker?.addEventListener("input", () => syncColor(picker.value));
  input?.addEventListener("input", () => {
    const normalized = normalizeHexColor(input.value);
    updateDraftState(input.value);
    if (!normalized) return;
    state.selectedColorCode = normalized;
    if (picker) picker.value = normalized;
    if (swatchPreview) swatchPreview.style.setProperty("--active-color", normalized);
  });
  input?.addEventListener("keydown", (event: any) => {
    if (event.key === "Enter") {
      event.preventDefault();
      if (!insert?.disabled) insertColorCode(input.value);
    }
    if (event.key === "Escape") {
      event.preventDefault();
      hideColorSuggest();
      els.promptEditor?.focus();
    }
  });
  insert?.addEventListener("pointerdown", keepPromptFocus);
  insert?.addEventListener("mousedown", keepPromptFocus);
  insert?.addEventListener("click", () => {
    if (insert.disabled) return;
    insertColorCode(input?.value || state.selectedColorCode);
  });
  const saveFavorite = els.colorSuggest.querySelector("[data-save-favorite-color]");
  saveFavorite?.addEventListener("pointerdown", keepPromptFocus);
  saveFavorite?.addEventListener("mousedown", keepPromptFocus);
  saveFavorite?.addEventListener("click", (event: any) => {
    event.stopPropagation();
    saveFavoriteColor();
  });
  const manageFavorite = els.colorSuggest.querySelector("[data-color-palette-manage]");
  manageFavorite?.addEventListener("pointerdown", keepPromptFocus);
  manageFavorite?.addEventListener("mousedown", keepPromptFocus);
  manageFavorite?.addEventListener("click", (event: any) => {
    event.stopPropagation();
    toggleColorPaletteManageMode();
  });
  const importInput = els.colorSuggest.querySelector("[data-color-palette-import-input]");
  importInput?.addEventListener("change", async () => {
    const file = importInput.files?.[0];
    if (!file) return;
    try {
      await importColorPalette(file);
    } catch (error: any) {
      setStatus(error.message || translate("colors.importFailed"), "error");
      console.warn(error.message || translate("colors.importFailed"));
    } finally {
      importInput.value = "";
    }
  });
  els.colorSuggest.querySelectorAll("[data-color-swatch]").forEach((button: any) => {
    button.addEventListener("pointerdown", keepPromptFocus);
    button.addEventListener("mousedown", keepPromptFocus);
    button.addEventListener("click", () => {
      if (state.activeColorChip) {
        syncColor(button.dataset.colorSwatch);
        input?.focus({ preventScroll: true });
        return;
      }
      insertColorCode(button.dataset.colorSwatch);
    });
  });
  els.colorSuggest.querySelectorAll("[data-remove-favorite-color]").forEach((button: any) => {
    button.addEventListener("pointerdown", keepPromptFocus);
    button.addEventListener("mousedown", keepPromptFocus);
    button.addEventListener("click", (event: any) => {
      event.stopPropagation();
      removeFavoriteColor(button.dataset.removeFavoriteColor);
    });
  });
}

function insertColorCode(colorCode: any) {
  const normalized = normalizeHexColor(colorCode) || state.selectedColorCode || DEFAULT_COLOR_CODE;
  if (state.activeColorChip && els.promptEditor?.contains(state.activeColorChip)) {
    const chip = state.activeColorChip;
    updateColorChip(chip, normalized);
    rememberRecentColor(normalized);
    syncPromptAfterChipMutation();
    setCaretAfterNode(chip);
    return;
  }
  let match = activeColorMatch();
  if (!match?.range && state.activeColorRange) {
    match = { query: "", range: state.activeColorRange };
  }
  let trailingSpace = null;
  if (match?.range) {
    match.range.deleteContents();
    const chip = createColorChip(normalized);
    trailingSpace = document.createTextNode(" ");
    match.range.insertNode(chip);
    chip.after(trailingSpace);
  } else {
    const currentText = getPromptText();
    if (currentText && !/\s$/.test(currentText)) {
      appendPromptText(" ");
    }
    els.promptEditor.append(createColorChip(normalized));
    trailingSpace = document.createTextNode(" ");
    els.promptEditor.append(trailingSpace);
  }
  rememberRecentColor(normalized);
  syncPromptFromEditor();
  updatePromptCount();
  updateRequestPreview();
  hideColorSuggest();
  setCaretAfterNode(trailingSpace);
}

function positionColorSuggestAtCaret(match: any) {
  if (!els.colorSuggest || !els.promptEditor || !match?.range) return;
  const host = els.promptEditor.closest(".prompt-editor-wrap") || els.promptEditor;
  const anchorRect = mentionRangeRect(match.range) || els.promptEditor.getBoundingClientRect();
  positionPromptPopoverAtAnchor(
    els.colorSuggest,
    host,
    anchorRect,
    {
      left: "--color-left",
      top: "--color-top",
      width: "--color-width",
      maxHeight: "--prompt-popover-max-height",
    },
    { minWidth: 260, maxWidth: 360, maxHeight: 300, minVisibleHeight: 150 },
  );
}

function openColorChipEditor(chip: any) {
  if (!chip || !els.promptEditor?.contains(chip)) return;
  const normalized = normalizeHexColor(chip.dataset.colorCode) || DEFAULT_COLOR_CODE;
  state.activeColorChip = chip;
  state.activeColorRange = null;
  state.selectedColorCode = normalized;
  renderColorSuggest({ query: normalized.slice(1), range: null });
  positionColorSuggestAtChip(chip);
  els.colorSuggest?.classList.remove("hidden");
}

function positionColorSuggestAtChip(chip: any) {
  if (!els.colorSuggest || !els.promptEditor || !chip) return;
  const host = els.promptEditor.closest(".prompt-editor-wrap") || els.promptEditor;
  const chipRect = chip.getBoundingClientRect();
  positionPromptPopoverAtAnchor(
    els.colorSuggest,
    host,
    chipRect,
    {
      left: "--color-left",
      top: "--color-top",
      width: "--color-width",
      maxHeight: "--prompt-popover-max-height",
    },
    { minWidth: 260, maxWidth: 360, maxHeight: 300, minVisibleHeight: 150 },
  );
}

function createColorChip(colorCode: any) {
  const normalized = normalizeHexColor(colorCode) || DEFAULT_COLOR_CODE;
  const chip = document.createElement("span");
  chip.className = "color-chip";
  chip.contentEditable = "false";
  chip.tabIndex = 0;
  chip.draggable = true;
  chip.dataset.promptChip = "color";
  chip.dataset.colorCode = normalized;
  chip.style.setProperty("--color-code", normalized);
  chip.style.setProperty("--color-text", readableTextColor(normalized));
  const swatch = document.createElement("button");
  swatch.className = "color-chip-swatch";
  swatch.type = "button";
  swatch.setAttribute("data-edit-color-chip", "");
  swatch.setAttribute("aria-label", formatTranslation("colors.modifyValue", { value: normalized }));
  swatch.title = translate("colors.modify");
  const label = document.createElement("span");
  label.className = "color-chip-label";
  label.textContent = normalized;
  const remove = document.createElement("button");
  remove.className = "color-chip-remove";
  remove.type = "button";
  remove.setAttribute("data-remove-color-chip", "");
  remove.setAttribute("aria-label", formatTranslation("colors.removeValue", { value: normalized }));
  remove.textContent = "×";
  chip.append(swatch, label, remove);
  chip.addEventListener("keydown", (event: any) => {
    if (event.key === "Backspace" || event.key === "Delete") {
      event.preventDefault();
      removePromptGalleryChip(chip);
    }
  });
  return chip;
}

function updateColorChip(chip: any, colorCode: any) {
  const normalized = normalizeHexColor(colorCode) || DEFAULT_COLOR_CODE;
  chip.dataset.colorCode = normalized;
  chip.style.setProperty("--color-code", normalized);
  chip.style.setProperty("--color-text", readableTextColor(normalized));
  const label = chip.querySelector(".color-chip-label");
  if (label) label.textContent = normalized;
  const swatch = chip.querySelector("[data-edit-color-chip]");
  if (swatch) {
    swatch.setAttribute("aria-label", formatTranslation("colors.modifyValue", { value: normalized }));
  }
  const remove = chip.querySelector("[data-remove-color-chip]");
  if (remove) {
    remove.setAttribute("aria-label", formatTranslation("colors.removeValue", { value: normalized }));
  }
}

function readableTextColor(colorCode: any) {
  const normalized = normalizeHexColor(colorCode);
  if (!normalized) return "var(--text)";
  const mixedBackground = mixRgbWithWhite(hexToRgb(normalized), 0.22);
  const darkText = hexToRgb("#1f352f");
  const whiteText = hexToRgb("#ffffff");
  return contrastRatio(mixedBackground, darkText) >= contrastRatio(mixedBackground, whiteText)
    ? "#1f352f"
    : "#ffffff";
}

function hexToRgb(colorCode: any) {
  return [
    Number.parseInt(colorCode.slice(1, 3), 16),
    Number.parseInt(colorCode.slice(3, 5), 16),
    Number.parseInt(colorCode.slice(5, 7), 16),
  ];
}

function mixRgbWithWhite(rgb: any, colorWeight: any) {
  return rgb.map((channel: any) => Math.round(channel * colorWeight + 255 * (1 - colorWeight)));
}

function relativeLuminance(rgb: any) {
  const [red, green, blue] = rgb.map((channel: any) => {
    const value = channel / 255;
    return value <= 0.03928 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4;
  });
  return 0.2126 * red + 0.7152 * green + 0.0722 * blue;
}

function contrastRatio(leftRgb: any, rightRgb: any) {
  const left = relativeLuminance(leftRgb);
  const right = relativeLuminance(rightRgb);
  const lighter = Math.max(left, right);
  const darker = Math.min(left, right);
  return (lighter + 0.05) / (darker + 0.05);
}

function hideColorSuggest() {
  if (!els.colorSuggest) return;
  els.colorSuggest.classList.add("hidden");
  els.colorSuggest.innerHTML = "";
  state.activeColorRange = null;
  state.activeColorChip = null;
  state.colorPaletteManageMode = false;
  els.colorSuggest.style.removeProperty("--color-left");
  els.colorSuggest.style.removeProperty("--color-top");
  els.colorSuggest.style.removeProperty("--color-width");
  els.colorSuggest.style.removeProperty("--prompt-popover-max-height");
}

export function initPromptColorsFeature(): void {
  Object.assign(getLegacyBridge().methods, {
    updateColorSuggest,
    activeColorMatch,
    renderColorSuggest,
    bindColorSuggestEvents,
    insertColorCode,
    positionColorSuggestAtCaret,
    openColorChipEditor,
    positionColorSuggestAtChip,
    colorNameForHex,
    colorSwatchButton,
    createColorChip,
    updateColorChip,
    readableTextColor,
    hexToRgb,
    mixRgbWithWhite,
    relativeLuminance,
    contrastRatio,
    hideColorSuggest,
  });
}

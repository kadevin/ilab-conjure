import { LOCALE_CHANGE_EVENT, translate } from "./i18n";
import { getLegacyBridge } from "./state";

const STORAGE_KEY = "codex-image-output-settings-lock-v1";

export interface OutputSettingsSnapshot {
  canonical_model_id: string;
  model_display_name: string;
  parameters: Record<string, unknown>;
  main_model: string;
  model: string;
  size: string;
  ratio: string;
  n: number;
  prompt_fidelity: "original" | "strict" | "off";
  quality: string;
  output_format: string;
  output_compression: number | null;
  moderation: string;
  web_search: boolean;
  resolution: string;
  has_safety_settings: boolean;
  safety_settings: Record<string, unknown>;
  google_search: boolean | null;
}

interface OutputSettingsSummaryContext {
  responses: boolean;
  task: boolean;
  callLabel: string;
}

interface SummaryDetail {
  label: string;
  value: string;
}

interface OutputSettingsSummaryModel {
  contextLabel: string;
  showModel: boolean;
  modelLabel: string;
  modelValue: string;
  hint: string;
  ratio: string;
  pixels: string;
  count: number;
  format: string;
  thirdCard: {
    kind: "format" | "resolution";
    label: string;
    value: string;
    meta: string;
  };
  details: SummaryDetail[];
}

let initialized = false;
let locked = false;
let lockedSnapshot: OutputSettingsSnapshot | null = null;
let taskSnapshot: OutputSettingsSnapshot | null = null;
let taskContext: OutputSettingsSummaryContext | null = null;

function legacyMethod(name: string, ...args: any[]): any {
  const method = getLegacyBridge().methods[name];
  if (typeof method !== "function") {
    throw new Error(`Legacy method ${name} is not initialized`);
  }
  return method(...args);
}

function greatestCommonDivisor(left: number, right: number): number {
  let a = Math.abs(Math.round(left));
  let b = Math.abs(Math.round(right));
  while (b) [a, b] = [b, a % b];
  return a || 1;
}

function normalizedDimensions(value: unknown): [number, number] {
  const match = String(value || "").match(/^(\d+)x(\d+)$/i);
  if (!match) return [1024, 1024];
  const width = Math.max(1, Number(match[1]) || 1024);
  const height = Math.max(1, Number(match[2]) || 1024);
  return [width, height];
}

function record(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value)
    ? { ...(value as Record<string, unknown>) }
    : {};
}

function hasOwn(source: Record<string, unknown>, key: string): boolean {
  return Object.prototype.hasOwnProperty.call(source, key);
}

export function normalizeOutputSettingsSnapshot(params: any): OutputSettingsSnapshot {
  const parameters = record(params?.parameters);
  const sizeValue = parameters["canvas.size"] || params?.size;
  const [width, height] = normalizedDimensions(sizeValue);
  const divisor = greatestCommonDivisor(width, height);
  const fidelity = String(params?.prompt_fidelity || "strict");
  const compression = parameters["gpt.output_compression"] ?? params?.output_compression;
  const canonicalModelId = String(params?.canonical_model_id || "gpt-image-2");
  return {
    canonical_model_id: canonicalModelId,
    model_display_name: String(params?.model_display_name || canonicalModelId),
    parameters,
    main_model: String(params?.main_model || ""),
    model: String(params?.model || "gpt-image-2"),
    size: `${width}x${height}`,
    ratio: String(parameters["canvas.aspect_ratio"] || params?.ratio || `${width / divisor}:${height / divisor}`),
    n: Math.max(1, Math.min(4, Math.round(Number(parameters["output.count"] ?? params?.n) || 1))),
    prompt_fidelity: fidelity === "original" || fidelity === "off" ? fidelity : "strict",
    quality: String(parameters["gpt.quality"] || params?.quality || "auto"),
    output_format: String(parameters["output.format"] || params?.output_format || "png").toLowerCase(),
    output_compression: compression === null || compression === undefined ? null : Number(compression),
    moderation: String(parameters["gpt.moderation"] || params?.moderation || "auto"),
    web_search: Boolean(parameters["gpt.web_search"] ?? params?.web_search),
    resolution: String(parameters["canvas.resolution"] || params?.resolution || ""),
    has_safety_settings: hasOwn(parameters, "gemini.safety_settings"),
    safety_settings: record(parameters["gemini.safety_settings"]),
    google_search: hasOwn(parameters, "gemini.google_search")
      ? Boolean(parameters["gemini.google_search"])
      : null,
  };
}

function promptFidelityLabel(value: OutputSettingsSnapshot["prompt_fidelity"]): string {
  return translate(value === "original" ? "output.modeOriginal" : value === "off" ? "output.modeCreative" : "output.modeStrict");
}

function qualityLabel(value: string): string {
  const key = value === "low"
    ? "output.qualityLow"
    : value === "medium"
      ? "output.qualityMedium"
      : value === "high"
        ? "output.qualityHigh"
        : "output.qualityAuto";
  return translate(key);
}

function geminiSafetyLabel(value: Record<string, unknown>, supported: boolean): string {
  const thresholds = Object.values(value).map(String);
  if (!thresholds.length) return supported ? translate("gemini.safety.threshold.off") : "";
  if (thresholds.every((threshold) => threshold === "OFF")) return translate("gemini.safety.threshold.off");
  if (thresholds.every((threshold) => threshold === "BLOCK_LOW_AND_ABOVE")) {
    return translate("gemini.safety.threshold.blockLowAndAbove");
  }
  return translate("output.lock.custom");
}

export function outputCountCardRatio(value: string): number {
  const [width = 1, height = 1] = String(value || "").split(":").map(Number);
  return width > 0 && height > 0 ? width / height : 1;
}

export function usesWideFourGrid(count: number, ratioValue: string): boolean {
  return count === 4 && outputCountCardRatio(ratioValue) >= 16 / 9;
}

export function buildOutputSettingsSummaryModel(
  snapshot: OutputSettingsSnapshot,
  context: OutputSettingsSummaryContext,
): OutputSettingsSummaryModel {
  const gptImage = snapshot.canonical_model_id === "gpt-image-2";
  const geminiImage = snapshot.canonical_model_id.startsWith("nano-banana");
  const details: SummaryDetail[] = [];
  if (gptImage) {
    details.push(
      { label: translate("output.lock.prompt"), value: promptFidelityLabel(snapshot.prompt_fidelity) },
      { label: translate("output.quality"), value: qualityLabel(snapshot.quality) },
    );
    if (context.responses) {
      details.push({
        label: translate("output.lock.search"),
        value: translate(snapshot.web_search ? "output.lock.enabled" : "output.lock.disabled"),
      });
    } else {
      details.push({ label: translate("output.lock.call"), value: context.callLabel });
    }
    details.push({ label: translate("output.moderation"), value: snapshot.moderation });
  } else {
    const safety = geminiSafetyLabel(snapshot.safety_settings, snapshot.has_safety_settings);
    if (safety) details.push({ label: translate("gemini.safetySettings"), value: safety });
    if (snapshot.google_search !== null) {
      details.push({
        label: translate("gemini.googleSearch"),
        value: translate(snapshot.google_search ? "output.lock.enabled" : "output.lock.disabled"),
      });
    }
  }
  const thirdCard = gptImage
    ? {
        kind: "format" as const,
        label: translate("output.lock.output"),
        value: snapshot.output_format.toUpperCase(),
        meta: translate("output.lock.fileFormat"),
      }
    : {
        kind: "resolution" as const,
        label: translate("canvas.resolution"),
        value: snapshot.resolution || "—",
        meta: "",
      };
  return {
    contextLabel: context.task ? translate("output.lock.task") : "",
    showModel: gptImage ? context.responses : context.task || geminiImage,
    modelLabel: gptImage
      ? translate(context.responses ? "output.mainModel" : "output.lock.imageModel")
      : "",
    modelValue: gptImage
      ? context.responses ? snapshot.main_model || snapshot.model : snapshot.model
      : snapshot.model_display_name || snapshot.canonical_model_id,
    hint: translate(context.task ? "output.lock.taskHint" : "output.lock.lockedHint"),
    ratio: snapshot.ratio,
    pixels: gptImage ? snapshot.size.replace("x", " × ") : "",
    count: snapshot.n,
    format: snapshot.output_format.toUpperCase(),
    thirdCard,
    details,
  };
}

function currentSummaryContext(): OutputSettingsSummaryContext {
  const authSource = String(legacyMethod("currentAuthSource") || "codex");
  const currentCodexMode = authSource === "codex" ? String(legacyMethod("currentCodexMode") || "image") : "";
  const currentApiMode = authSource === "api" ? String(legacyMethod("currentApiMode") || "images") : "";
  const responses = authSource === "api" ? currentApiMode === "responses" : currentCodexMode === "responses";
  const callLabel = authSource === "api" ? "Images API" : "Codex Image";
  return { responses, task: false, callLabel };
}

function taskSummaryContext(task: any): OutputSettingsSummaryContext {
  const params = task?.params || {};
  const request = task?.request || {};
  const responses = params.api_mode === "responses"
    || params.codex_mode === "responses"
    || request.api_mode === "responses"
    || request.codex_mode === "responses"
    || request.endpoint === "/responses"
    || String(task?.backend || "").includes("responses");
  const apiTask = Boolean(params.api_mode || request.api_mode || task?.api_provider_id || task?.api_provider_name);
  return { responses, task: true, callLabel: apiTask ? "Images API" : "Codex Image" };
}

function snapshotFromTask(task: any): OutputSettingsSnapshot {
  const params = task?.params || {};
  const request = task?.request || {};
  const frozen = record(task?.generation_snapshot);
  const canonicalModelId = String(frozen.canonical_model_id || request.canonical_model_id || "gpt-image-2");
  const catalogModel = getLegacyBridge().state.generationCatalog?.models
    .find((item: any) => item.id === canonicalModelId);
  const responses = params.api_mode === "responses"
    || params.codex_mode === "responses"
    || request.api_mode === "responses"
    || request.codex_mode === "responses"
    || request.endpoint === "/responses";
  return normalizeOutputSettingsSnapshot({
    ...params,
    canonical_model_id: canonicalModelId,
    model_display_name: catalogModel?.display_name || canonicalModelId,
    parameters: Object.keys(record(frozen.requested_parameters)).length
      ? record(frozen.requested_parameters)
      : record(request.parameters),
    main_model: params.main_model || request.main_model || (responses ? request.model : ""),
    model: params.model || request.image_model || request.model,
    size: params.size || request.size,
    n: params.n || request.n,
  });
}

function snapshotFromCurrentSelection(): OutputSettingsSnapshot {
  const bridge = getLegacyBridge();
  const legacy = legacyMethod("currentTaskParams");
  const model = bridge.state.generationCatalog?.models.find((item: any) => item.id === bridge.state.selectedModelId);
    const parameters = model && model.id !== "gpt-image-2" && typeof bridge.methods.activeParameterValues === "function"
    ? bridge.methods.activeParameterValues(model)
    : typeof bridge.methods.currentCanonicalParameters === "function"
      ? bridge.methods.currentCanonicalParameters()
      : {};
  return normalizeOutputSettingsSnapshot({
    ...legacy,
    canonical_model_id: model?.id || "gpt-image-2",
    model_display_name: model?.display_name || "GPT Image 2",
    parameters,
  });
}

function createElement<K extends keyof HTMLElementTagNameMap>(
  tag: K,
  className: string,
  text = "",
): HTMLElementTagNameMap[K] {
  const element = document.createElement(tag);
  element.className = className;
  if (text) element.textContent = text;
  return element;
}

function createSummaryCard(label: string): HTMLDivElement {
  const card = createElement("div", "output-settings-summary-card");
  card.append(createElement("span", "output-settings-summary-card-label", label));
  return card;
}

function renderRatioCard(model: OutputSettingsSummaryModel): HTMLDivElement {
  const card = createSummaryCard(translate("output.lock.frame"));
  const visual = createElement("div", "output-settings-ratio-visual");
  const ratio = outputCountCardRatio(model.ratio);
  const frame = createElement("div", "output-settings-ratio-frame");
  frame.style.setProperty("--output-settings-ratio", String(ratio));
  frame.classList.toggle("is-portrait", ratio < 1);
  frame.append(createElement("strong", "output-settings-ratio-value", model.ratio));
  visual.append(frame);
  card.append(visual);
  if (model.pixels) card.append(createElement("span", "output-settings-card-meta", model.pixels));
  return card;
}

function renderCountCard(model: OutputSettingsSummaryModel): HTMLDivElement {
  const card = createSummaryCard(translate("output.lock.outputCount"));
  const visual = createElement("div", "output-settings-count-visual");
  const ratio = outputCountCardRatio(model.ratio);
  const wideFour = usesWideFourGrid(model.count, model.ratio);
  visual.classList.toggle("is-wide-four", wideFour);
  visual.style.setProperty("--output-settings-count-ratio", String(ratio));
  visual.style.setProperty("--output-settings-count-card-max-width", `${wideFour ? 46 : Math.min(38, 58 * ratio)}px`);
  for (let index = 0; index < model.count; index += 1) {
    const thumbnail = createElement("span", "output-settings-count-card");
    thumbnail.append(createElement("span", "output-settings-count-card-sun"), createElement("span", "output-settings-count-card-land"));
    visual.append(thumbnail);
  }
  card.append(visual, createElement("span", "output-settings-card-meta", `${model.count} ${translate("output.lock.sheets")}`));
  return card;
}

function renderThirdCard(model: OutputSettingsSummaryModel): HTMLDivElement {
  const card = createSummaryCard(model.thirdCard.label);
  const visual = createElement("div", `output-settings-${model.thirdCard.kind}-visual`, model.thirdCard.value);
  card.append(visual);
  if (model.thirdCard.meta) card.append(createElement("span", "output-settings-card-meta", model.thirdCard.meta));
  return card;
}

function renderSummary(snapshot: OutputSettingsSnapshot, context: OutputSettingsSummaryContext): void {
  const els = getLegacyBridge().els;
  const root = els.outputSettingsSummaryContent;
  if (!root) return;
  const model = buildOutputSettingsSummaryModel(snapshot, context);
  root.replaceChildren();
  els.outputSettingsLockedSummary?.classList.toggle("is-task-context", context.task);

  const intro = createElement("div", "output-settings-summary-intro");
  if (model.contextLabel) {
    intro.append(createElement("span", "output-settings-summary-context", model.contextLabel));
  }
  if (model.showModel) {
    const modelLine = createElement("div", "output-settings-summary-model-line");
    if (model.modelLabel) {
      modelLine.append(createElement("span", "output-settings-summary-model-label", model.modelLabel));
    }
    modelLine.append(createElement("strong", "output-settings-summary-model", model.modelValue));
    intro.append(modelLine);
  }

  const cards = createElement("div", "output-settings-summary-cards");
  cards.append(renderRatioCard(model), renderCountCard(model), renderThirdCard(model));

  const details = createElement("div", "output-settings-summary-details");
  model.details.forEach((detail) => {
    const item = createElement("div", "output-settings-summary-detail");
    item.append(
      createElement("span", "output-settings-summary-detail-label", detail.label),
      createElement("strong", "output-settings-summary-detail-value", detail.value),
    );
    details.append(item);
  });
  details.classList.toggle("hidden", model.details.length === 0);

  const main = createElement("div", "output-settings-summary-main");
  if (intro.childElementCount) main.append(intro);
  main.append(cards, details);

  const footer = createElement("div", "output-settings-summary-footer");
  const hint = createElement("p", "output-settings-summary-hint", model.hint);
  footer.append(hint);
  if (els.outputSettingsTaskAction) {
    els.outputSettingsTaskAction.classList.toggle("hidden", !context.task);
    footer.append(els.outputSettingsTaskAction);
  }
  root.append(main, footer);
}

function updateLockButton(): void {
  const button = getLegacyBridge().els.outputSettingsLockButton;
  if (!button) return;
  const label = translate(locked ? "output.lock.unlock" : "output.lock.lock");
  button.classList.toggle("is-locked", locked);
  button.setAttribute("aria-pressed", locked ? "true" : "false");
  button.setAttribute("aria-label", label);
  button.title = label;
}

function setLockedViewVisible(visible: boolean): void {
  const els = getLegacyBridge().els;
  const panel = els.outputSettingsHeader?.closest(".output-panel");
  panel?.classList.toggle("is-locked-view", visible);
  els.settingsGrid?.toggleAttribute("inert", visible);
  els.settingsGrid?.setAttribute("aria-hidden", visible ? "true" : "false");
  els.outputSettingsLockedSummary?.classList.toggle("hidden", !visible);
  els.outputSettingsLockedSummary?.setAttribute("aria-hidden", visible ? "false" : "true");
}

function persistLockState(): void {
  try {
    if (!locked || !lockedSnapshot) {
      localStorage.removeItem(STORAGE_KEY);
      return;
    }
    localStorage.setItem(STORAGE_KEY, JSON.stringify({ locked: true, snapshot: lockedSnapshot }));
  } catch {
    // Persistence is a convenience; the in-memory lock remains usable.
  }
}

function readPersistedLockState(): OutputSettingsSnapshot | null {
  try {
    const value = JSON.parse(localStorage.getItem(STORAGE_KEY) || "null");
    return value?.locked && value?.snapshot ? normalizeOutputSettingsSnapshot(value.snapshot) : null;
  } catch {
    return null;
  }
}

function applySnapshot(snapshot: OutputSettingsSnapshot): void {
  legacyMethod("applyTaskOutputParams", { params: snapshot });
}

export function isOutputSettingsLocked(): boolean {
  return locked;
}

export function showLockedOutputSettings(): void {
  if (!locked) return;
  taskSnapshot = null;
  taskContext = null;
  lockedSnapshot = snapshotFromCurrentSelection();
  persistLockState();
  renderSummary(lockedSnapshot, currentSummaryContext());
  setLockedViewVisible(true);
  updateLockButton();
}

export function showTaskOutputSettings(task: any): void {
  if (!locked) return;
  taskSnapshot = snapshotFromTask(task);
  taskContext = taskSummaryContext(task);
  renderSummary(taskSnapshot, taskContext);
  setLockedViewVisible(true);
  updateLockButton();
}

export function refreshOutputSettingsLock(): void {
  if (!locked) return;
  if (taskSnapshot && taskContext) {
    renderSummary(taskSnapshot, taskContext);
    return;
  }
  showLockedOutputSettings();
}

export function adoptTaskOutputSettings(): void {
  if (!locked || !taskSnapshot) return;
  const state = getLegacyBridge().state;
  const task = state.tasks.find((item: any) => String(item.task_id) === String(state.selectedTaskId));
  if (task) legacyMethod("adoptTaskParameters", task);
  applySnapshot(taskSnapshot);
  lockedSnapshot = snapshotFromCurrentSelection();
  taskSnapshot = null;
  taskContext = null;
  persistLockState();
  renderSummary(lockedSnapshot, currentSummaryContext());
  getLegacyBridge().els.outputSettingsTaskAction?.classList.add("hidden");
}

function lockOutputSettings(): void {
  lockedSnapshot = snapshotFromCurrentSelection();
  locked = true;
  taskSnapshot = null;
  taskContext = null;
  persistLockState();
  renderSummary(lockedSnapshot, currentSummaryContext());
  setLockedViewVisible(true);
  updateLockButton();
}

function unlockOutputSettings(): void {
  if (lockedSnapshot) applySnapshot(lockedSnapshot);
  locked = false;
  lockedSnapshot = null;
  taskSnapshot = null;
  taskContext = null;
  persistLockState();
  setLockedViewVisible(false);
  updateLockButton();
}

function toggleOutputSettingsLock(): void {
  if (locked) unlockOutputSettings();
  else lockOutputSettings();
}

export function restoreOutputSettingsLock(): void {
  const snapshot = readPersistedLockState();
  if (!snapshot) {
    locked = false;
    setLockedViewVisible(false);
    updateLockButton();
    return;
  }
  applySnapshot(snapshot);
  lockedSnapshot = snapshotFromCurrentSelection();
  locked = true;
  renderSummary(lockedSnapshot, currentSummaryContext());
  setLockedViewVisible(true);
  updateLockButton();
}

export function initOutputSettingsLockFeature(): void {
  if (initialized) return;
  initialized = true;
  Object.assign(getLegacyBridge().methods, {
    isOutputSettingsLocked,
    restoreOutputSettingsLock,
    refreshOutputSettingsLock,
    showLockedOutputSettings,
    showTaskOutputSettings,
    adoptTaskOutputSettings,
  });
  getLegacyBridge().els.outputSettingsLockButton?.addEventListener("click", toggleOutputSettingsLock);
  getLegacyBridge().els.adoptTaskOutputSettingsButton?.addEventListener("click", adoptTaskOutputSettings);
  document.addEventListener(LOCALE_CHANGE_EVENT, refreshOutputSettingsLock);
}

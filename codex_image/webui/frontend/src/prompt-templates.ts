import { getLegacyBridge } from "./state";
import { formatTranslation, LOCALE_CHANGE_EVENT, translate } from "./i18n";

const PROMPT_TEMPLATES_ENDPOINT = "/api/prompt-templates";
const PROMPT_TEMPLATE_CATEGORIES_ENDPOINT = "/api/prompt-template-categories";
const PROMPT_TEMPLATE_IMPORT_ENDPOINT = "/api/prompt-templates/import";
const PROMPT_TEMPLATE_EXPORT_ENDPOINT = "/api/prompt-templates/export.json";
const PROMPT_TEMPLATE_CATEGORY_COMMON = "\u5e38\u7528";
const PROMPT_TEMPLATE_CATEGORY_PORTRAIT = "\u4eba\u50cf";
const PROMPT_TEMPLATE_CATEGORY_PRODUCT = "\u4ea7\u54c1";
const PROMPT_TEMPLATE_CATEGORY_REPAIR = "\u4fee\u590d";
const PROMPT_TEMPLATE_CATEGORY_POSTER = "\u6d77\u62a5";
const PROMPT_TEMPLATE_CATEGORY_ECOMMERCE = "\u7535\u5546";
const DEFAULT_PROMPT_TEMPLATE_CATEGORIES = [
  PROMPT_TEMPLATE_CATEGORY_COMMON,
  PROMPT_TEMPLATE_CATEGORY_PORTRAIT,
  PROMPT_TEMPLATE_CATEGORY_PRODUCT,
  PROMPT_TEMPLATE_CATEGORY_REPAIR,
  PROMPT_TEMPLATE_CATEGORY_POSTER,
  PROMPT_TEMPLATE_CATEGORY_ECOMMERCE,
];
const DEFAULT_PROMPT_TEMPLATE_CATEGORY_I18N_KEYS: Record<string, string> = {
  [PROMPT_TEMPLATE_CATEGORY_COMMON]: "templates.categoryCommon",
  [PROMPT_TEMPLATE_CATEGORY_PORTRAIT]: "templates.categoryPortrait",
  [PROMPT_TEMPLATE_CATEGORY_PRODUCT]: "templates.categoryProduct",
  [PROMPT_TEMPLATE_CATEGORY_REPAIR]: "templates.categoryRepair",
  [PROMPT_TEMPLATE_CATEGORY_POSTER]: "templates.categoryPoster",
  [PROMPT_TEMPLATE_CATEGORY_ECOMMERCE]: "templates.categoryEcommerce",
};

const bridge = getLegacyBridge();
const state = bridge.state;
const els = bridge.els;
let promptTemplateSearchAcceptManualInput = false;
let lastPromptTemplateTrigger: HTMLElement | null = null;

function legacyMethod(name: string, ...args: any[]): any {
  const method = getLegacyBridge().methods[name];
  if (typeof method !== "function") {
    throw new Error("Legacy method " + name + " is not initialized");
  }
  return method(...args);
}

function escapeHtml(value: any): string { return legacyMethod("escapeHtml", value); }
function setStatus(message: any, type?: any): void { legacyMethod("setStatus", message, type); }
function getPromptText(): string { return legacyMethod("getPromptText"); }
function appendPromptText(text: any): void { legacyMethod("appendPromptText", text); }
function setPromptText(text: any): void { legacyMethod("setPromptText", text); }
function syncPromptFromEditor(): void { legacyMethod("syncPromptFromEditor"); }
function updatePromptCount(): void { legacyMethod("updatePromptCount"); }
function updateRequestPreview(): void { legacyMethod("updateRequestPreview"); }

function normalizePromptTemplate(value: any) {
  if (!value || typeof value !== "object") return null;
  const title = String(value.title || "").trim();
  const content = String(value.content || "").trim();
  if (!title || !content) return null;
  const tags = Array.isArray(value.tags) ? value.tags.map((tag: any) => String(tag || "").trim()).filter(Boolean) : [];
  const usageCount = Number.isFinite(Number(value.usage_count)) ? Number.parseInt(value.usage_count, 10) : 0;
  return {
    id: String(value.id || title).trim() || title,
    title,
    short_title: String(value.short_title || title).trim().slice(0, 12) || title.slice(0, 12),
    content,
    category: String(value.category || PROMPT_TEMPLATE_CATEGORY_COMMON).trim() || PROMPT_TEMPLATE_CATEGORY_COMMON,
    tags,
    mode: String(value.mode || "any"),
    model_hint: String(value.model_hint || "gpt-image-2"),
    notes: String(value.notes || ""),
    thumbnail_url: String(value.thumbnail_url || "").trim(),
    favorite: Boolean(value.favorite),
    variables: Array.isArray(value.variables) ? value.variables.map((item: any) => String(item || "").trim()).filter(Boolean) : [],
    usage_count: Math.max(0, usageCount),
    created_at: value.created_at || "",
    updated_at: value.updated_at || "",
    last_used_at: value.last_used_at || "",
  };
}

function normalizePromptTemplateCategory(value: any, index = 0) {
  const rawName = typeof value === "string" ? value : value?.name || value?.id;
  const name = String(rawName || "").trim().slice(0, 32);
  if (!name) return null;
  const orderValue = Number.parseInt(value?.order ?? "", 10);
  return {
    id: name,
    name,
    order: Number.isFinite(orderValue) ? Math.max(0, orderValue) : (index + 1) * 10,
  };
}

function normalizePromptTemplateList(items: any) {
  return (Array.isArray(items) ? items : [])
    .map(normalizePromptTemplate)
    .filter(Boolean)
    .sort((left: any, right: any) => (
      Number(right.favorite) - Number(left.favorite)
      || Number(Boolean(right.last_used_at)) - Number(Boolean(left.last_used_at))
      || right.usage_count - left.usage_count
      || left.title.localeCompare(right.title, "zh-Hans-CN")
    ));
}

function normalizePromptTemplateCategoryList(items: any) {
  const seen = new Set<string>();
  const categories = (Array.isArray(items) && items.length ? items : DEFAULT_PROMPT_TEMPLATE_CATEGORIES)
    .map((item: any, index: number) => normalizePromptTemplateCategory(item, index))
    .filter(Boolean)
    .filter((category: any) => {
      const key = category.id.toLowerCase();
      if (seen.has(key)) return false;
      seen.add(key);
      return true;
    })
    .sort((left: any, right: any) => left.order - right.order || left.name.localeCompare(right.name, "zh-Hans-CN"));
  if (!categories.some((category: any) => category.id === PROMPT_TEMPLATE_CATEGORY_COMMON)) {
    categories.unshift({ id: PROMPT_TEMPLATE_CATEGORY_COMMON, name: PROMPT_TEMPLATE_CATEGORY_COMMON, order: 10 });
  }
  return categories;
}

function applyPromptTemplateSettingsResponse(data: any) {
  state.promptTemplates = normalizePromptTemplateList(data?.templates);
  state.promptTemplateCategories = normalizePromptTemplateCategoryList(data?.categories);
  if (state.promptTemplateCategory && !state.promptTemplateCategories.some((category: any) => category.id === state.promptTemplateCategory)) {
    state.promptTemplateCategory = "";
  }
  renderPromptTemplateCategories();
  renderPromptTemplateCategoryPanel();
  renderPromptTemplateRecentDock();
  renderPromptTemplateList();
}

async function refreshPromptTemplates() {
  try {
    const response = await fetch(PROMPT_TEMPLATES_ENDPOINT);
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || translate("templates.loadFailed"));
    applyPromptTemplateSettingsResponse(data);
  } catch (error: any) {
    console.warn(error.message || translate("templates.loadFailed"));
    state.promptTemplates = [];
    state.promptTemplateCategories = normalizePromptTemplateCategoryList([]);
    renderPromptTemplateCategories();
    renderPromptTemplateRecentDock();
    renderPromptTemplateList();
  }
}

function syncPromptTemplateSearchInput() {
  const input = els.promptTemplateSearch as HTMLInputElement | null;
  if (!input) return;
  const nextValue = String(state.promptTemplateQuery || "");
  if (input.value !== nextValue) input.value = nextValue;
}

function setPromptTemplateSearchLocked(locked: boolean) {
  const input = els.promptTemplateSearch as HTMLInputElement | null;
  if (!input) return;
  input.readOnly = locked;
  if (locked) {
    input.setAttribute("readonly", "");
  } else {
    input.removeAttribute("readonly");
  }
}

function guardPromptTemplateSearchInput(delays = [0, 120, 360, 900]) {
  delays.forEach((delay) => {
    window.setTimeout(() => {
      if (!els.promptTemplateDrawer?.classList.contains("open")) return;
      syncPromptTemplateSearchInput();
    }, delay);
  });
}

function openPromptTemplateDrawer() {
  legacyMethod("closeGallery", { restoreFocus: false });
  lastPromptTemplateTrigger = document.activeElement instanceof HTMLElement ? document.activeElement : (els.promptTemplateButton as HTMLElement | null);
  els.promptTemplateDrawer?.classList.add("open");
  els.promptTemplateDrawer?.setAttribute("aria-hidden", "false");
  els.promptTemplateDrawerBackdrop?.classList.remove("hidden");
  els.promptTemplateButton?.setAttribute("aria-expanded", "true");
  promptTemplateSearchAcceptManualInput = false;
  setPromptTemplateSearchLocked(true);
  renderPromptTemplateCategories();
  renderPromptTemplateList();
  syncPromptTemplateSearchInput();
  guardPromptTemplateSearchInput();
  window.setTimeout(() => {
    syncPromptTemplateSearchInput();
    els.promptTemplateDrawerClose?.focus({ preventScroll: true });
  }, 0);
}

function closePromptTemplateDrawer(options: any = {}) {
  const restoreFocus = options?.restoreFocus !== false;
  els.promptTemplateDrawer?.classList.remove("open");
  els.promptTemplateDrawer?.setAttribute("aria-hidden", "true");
  els.promptTemplateDrawerBackdrop?.classList.add("hidden");
  els.promptTemplateButton?.setAttribute("aria-expanded", "false");
  promptTemplateSearchAcceptManualInput = false;
  setPromptTemplateSearchLocked(true);
  hidePromptTemplateDetail();
  hidePromptTemplateForm();
  hidePromptTemplateCategoryPanel();
  if (restoreFocus) {
    const focusTarget = lastPromptTemplateTrigger || (els.promptTemplateButton as HTMLElement | null);
    focusTarget?.focus?.({ preventScroll: true });
  }
}

function renderPromptTemplateCategories() {
  if (!els.promptTemplateCategoryList) return;
  const categories = normalizePromptTemplateCategoryList(state.promptTemplateCategories);
  state.promptTemplateCategories = categories;
  els.promptTemplateCategoryList.innerHTML = [
    `<button class="prompt-template-category ${state.promptTemplateCategory ? "" : "active"}" data-prompt-template-category="" type="button">${translate("templates.all")}</button>`,
    ...categories.map((category: any) => `
      <button class="prompt-template-category ${state.promptTemplateCategory === category.id ? "active" : ""}" data-prompt-template-category="${escapeHtml(category.id)}" type="button">
        ${escapeHtml(promptTemplateCategoryLabel(category.name))}
      </button>
    `),
  ].join("");
}

function promptTemplateCategoryLabel(category: any) {
  const name = String(category || "").trim();
  const key = DEFAULT_PROMPT_TEMPLATE_CATEGORY_I18N_KEYS[name];
  return key ? translate(key) : name;
}

function renderPromptTemplateCategoryPanel() {
  if (!els.promptTemplateCategoryPanel) return;
  const categories = normalizePromptTemplateCategoryList(state.promptTemplateCategories);
  els.promptTemplateCategoryPanel.innerHTML = `
    <div class="prompt-template-category-create">
      <input class="control" type="text" maxlength="32" placeholder="${escapeHtml(translate("templates.newCategory"))}" data-prompt-template-category-new>
      <button class="ghost-button text-sm" type="button" data-prompt-template-category-create>${escapeHtml(translate("action.add"))}</button>
    </div>
    <div class="prompt-template-category-manage-list">
      ${categories.map((category: any) => `
        <div class="prompt-template-category-manage-row" data-prompt-template-category-row="${escapeHtml(category.id)}">
          <input class="control" type="text" maxlength="32" value="${escapeHtml(category.name)}" data-prompt-template-category-name>
          <button class="ghost-button text-sm" type="button" data-prompt-template-category-rename>${escapeHtml(translate("action.save"))}</button>
          <button class="ghost-button text-sm quiet-danger-button" type="button" data-prompt-template-category-delete ${category.id === PROMPT_TEMPLATE_CATEGORY_COMMON ? "disabled" : ""}>${escapeHtml(translate("action.delete"))}</button>
        </div>
      `).join("")}
    </div>
  `;
}

function togglePromptTemplateCategoryPanel() {
  if (!els.promptTemplateCategoryPanel) return;
  const isHidden = els.promptTemplateCategoryPanel.classList.contains("hidden");
  if (isHidden) {
    renderPromptTemplateCategoryPanel();
    els.promptTemplateCategoryPanel.classList.remove("hidden");
    els.promptTemplateCategoryManageButton?.setAttribute("aria-expanded", "true");
  } else {
    hidePromptTemplateCategoryPanel();
  }
}

function hidePromptTemplateCategoryPanel() {
  els.promptTemplateCategoryPanel?.classList.add("hidden");
  els.promptTemplateCategoryManageButton?.setAttribute("aria-expanded", "false");
}

function promptTemplatesForDisplay() {
  const query = String(state.promptTemplateQuery || "").trim().toLowerCase();
  return (state.promptTemplates || []).filter((template: any) => {
    if (state.promptTemplateFilter === "favorite" && !template.favorite) return false;
    if (state.promptTemplateFilter === "recent" && !template.last_used_at) return false;
    if (state.promptTemplateCategory && template.category !== state.promptTemplateCategory) return false;
    if (!query) return true;
    return [
      template.title,
      template.short_title,
      template.content,
      template.category,
      template.notes,
      template.model_hint,
      ...(template.tags || []),
    ].join(" ").toLowerCase().includes(query);
  });
}

function renderPromptTemplateList() {
  if (!els.promptTemplateList) return;
  const templates = promptTemplatesForDisplay();
  if (els.promptTemplateSummary) {
    els.promptTemplateSummary.className = "prompt-template-summary";
    els.promptTemplateSummary.textContent = templates.length
      ? formatTranslation("templates.availableCount", { count: templates.length })
      : translate("templates.noMatch");
  }
  if (!templates.length) {
    els.promptTemplateList.innerHTML = `<div class="prompt-template-empty">${translate("templates.empty")}</div>`;
    return;
  }
  els.promptTemplateList.innerHTML = templates.map((template: any) => `
    <button class="prompt-template-card" type="button" data-prompt-template-id="${escapeHtml(template.id)}">
      ${template.thumbnail_url ? `<span class="prompt-template-card-thumb"><img src="${escapeHtml(template.thumbnail_url)}" alt=""></span>` : ""}
      <span class="prompt-template-card-title">${escapeHtml(template.short_title)}</span>
      <span class="prompt-template-card-subtitle">${escapeHtml(template.title)}</span>
      <span class="prompt-template-card-preview">${escapeHtml(promptTemplatePreview(template.content, 64))}</span>
      <span class="prompt-template-card-meta">
        <span>${escapeHtml(promptTemplateCategoryLabel(template.category))}</span>
        <span>${template.favorite ? translate("templates.favoriteBadge") : formatTranslation("templates.usageCount", { count: template.usage_count || 0 })}</span>
      </span>
    </button>
  `).join("");
}

function renderPromptTemplateRecentDock() {
  if (!els.promptTemplateRecentDock) return;
  const recent = (state.promptTemplates || [])
    .filter((template: any) => template.last_used_at || template.favorite)
    .slice(0, 4);
  if (!recent.length) {
    els.promptTemplateRecentDock.classList.add("hidden");
    els.promptTemplateRecentDock.innerHTML = "";
    return;
  }
  els.promptTemplateRecentDock.innerHTML = recent.map((template: any) => `
    <button class="prompt-template-recent-chip" type="button" data-prompt-template-insert="${escapeHtml(template.id)}">
      ${escapeHtml(template.short_title)}
    </button>
  `).join("");
  els.promptTemplateRecentDock.classList.remove("hidden");
}

function selectPromptTemplate(templateId: any) {
  const template = findPromptTemplateById(templateId);
  if (!template || !els.promptTemplateDetail) return;
  state.selectedPromptTemplateId = template.id;
  hidePromptTemplateForm();
  els.promptTemplateDetail.innerHTML = `
    <div class="prompt-template-detail-header">
      <button class="ghost-button text-sm" type="button" data-prompt-template-back>${translate("templates.back")}</button>
      <button class="ghost-button text-sm" type="button" data-prompt-template-edit="${escapeHtml(template.id)}">${translate("templates.edit")}</button>
    </div>
    ${template.thumbnail_url ? `<img class="prompt-template-detail-thumb" src="${escapeHtml(template.thumbnail_url)}" alt="">` : ""}
    <h3>${escapeHtml(template.title)}</h3>
    <div class="prompt-template-detail-meta">
      <span>${escapeHtml(promptTemplateCategoryLabel(template.category))}</span>
      <span>${escapeHtml(template.model_hint)}</span>
      ${template.favorite ? `<span>${translate("templates.favoriteBadge")}</span>` : ""}
    </div>
    <div class="prompt-template-detail-content">${escapeHtml(template.content)}</div>
    ${template.notes ? `<p class="prompt-template-detail-notes">${escapeHtml(template.notes)}</p>` : ""}
    <div class="prompt-template-detail-actions">
      <button class="ghost-button text-sm" type="button" data-prompt-template-copy="${escapeHtml(template.id)}">${translate("templates.copy")}</button>
      <button class="ghost-button text-sm" type="button" data-prompt-template-insert="${escapeHtml(template.id)}">${translate("templates.insert")}</button>
      <button class="run-button" type="button" data-prompt-template-replace="${escapeHtml(template.id)}">${translate("action.replace")}</button>
    </div>
  `;
  els.promptTemplateList?.classList.add("hidden");
  els.promptTemplateDetail.classList.remove("hidden");
}

async function applyPromptTemplate(template: any, mode: any) {
  if (!template) return;
  const content = String(template.content || "").trim();
  if (!content) return;
  if (mode === "replace") {
    setPromptText(content);
  } else {
    const current = getPromptText();
    if (current && !/\s$/.test(current)) appendPromptText("\n\n");
    appendPromptText(content);
    syncPromptFromEditor();
  }
  updatePromptCount();
  updateRequestPreview();
  await afterPromptTemplateApplied(template);
  closePromptTemplateDrawer();
}

async function afterPromptTemplateApplied(template: any) {
  try {
    const response = await fetch(`${PROMPT_TEMPLATES_ENDPOINT}/${encodeURIComponent(template.id)}/use`, { method: "POST" });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || translate("templates.useStateUpdateFailed"));
    applyPromptTemplateSettingsResponse(data);
  } catch (error: any) {
    console.warn(error.message || translate("templates.useStateUpdateFailed"));
  }
}

async function copyPromptTemplateContent(template: any) {
  if (!template) return;
  try {
    await navigator.clipboard.writeText(template.content);
    setStatus(translate("templates.copied"), "ok");
  } catch {
    setStatus(translate("templates.copyFailed"), "error");
  }
}

function renderPromptTemplateForm(template: any = null) {
  if (!els.promptTemplateForm) return;
  const value = template || {
    id: "",
    title: "",
    short_title: "",
    content: getPromptText(),
    category: PROMPT_TEMPLATE_CATEGORY_COMMON,
    tags: [],
    notes: "",
    thumbnail_url: "",
    favorite: false,
  };
  hidePromptTemplateDetail();
  els.promptTemplateList?.classList.add("hidden");
  const categories = promptTemplateCategoriesForSelect(value.category);
  els.promptTemplateForm.innerHTML = `
    <form class="prompt-template-form" data-prompt-template-form-id="${escapeHtml(value.id || "")}">
      <div class="prompt-template-form-header">
        <button class="ghost-button text-sm" type="button" data-prompt-template-back>${escapeHtml(translate("templates.back"))}</button>
        ${value.id ? `<button class="ghost-button text-sm danger-button" type="button" data-prompt-template-delete="${escapeHtml(value.id)}">${escapeHtml(translate("action.delete"))}</button>` : ""}
      </div>
      <label class="prompt-template-field">
        <span>${escapeHtml(translate("templates.formTitle"))}</span>
        <input class="control" type="text" maxlength="80" value="${escapeHtml(value.title || "")}" data-prompt-template-title>
      </label>
      <label class="prompt-template-field">
        <span>${escapeHtml(translate("templates.formShortTitle"))}</span>
        <input class="control" type="text" maxlength="12" value="${escapeHtml(value.short_title || "")}" data-prompt-template-short-title>
      </label>
      <label class="prompt-template-field">
        <span>${escapeHtml(translate("templates.formCategory"))}</span>
        <select class="control" data-prompt-template-category-input>
          ${categories.map((category: any) => `<option value="${escapeHtml(category.id)}" ${category.id === value.category ? "selected" : ""}>${escapeHtml(promptTemplateCategoryLabel(category.name))}</option>`).join("")}
        </select>
      </label>
      <label class="prompt-template-field prompt-template-field-full">
        <span>${escapeHtml(translate("templates.formTags"))}</span>
        <input class="control" type="text" value="${escapeHtml((value.tags || []).join("，"))}" data-prompt-template-tags>
      </label>
      <div class="prompt-template-field prompt-template-field-full prompt-template-thumbnail-field">
        <span>${escapeHtml(translate("templates.formThumbnail"))}</span>
        <input type="hidden" value="${escapeHtml(value.thumbnail_url || "")}" data-prompt-template-thumbnail-url>
        <div class="prompt-template-thumbnail-row">
          <div class="prompt-template-thumbnail-preview" data-prompt-template-thumbnail-preview></div>
          <button class="ghost-button text-sm" type="button" data-prompt-template-thumbnail-clear>${escapeHtml(translate("templates.thumbnailClear"))}</button>
        </div>
        <div class="prompt-template-thumbnail-picker" data-prompt-template-thumbnail-picker></div>
      </div>
      <label class="prompt-template-field prompt-template-field-full">
        <span>${escapeHtml(translate("templates.formContent"))}</span>
        <textarea class="control prompt-template-textarea" maxlength="8000" data-prompt-template-content>${escapeHtml(value.content || "")}</textarea>
      </label>
      <label class="prompt-template-field prompt-template-field-full">
        <span>${escapeHtml(translate("templates.formNotes"))}</span>
        <textarea class="control prompt-template-notes" maxlength="500" data-prompt-template-notes>${escapeHtml(value.notes || "")}</textarea>
      </label>
      <label class="prompt-template-check">
        <input type="checkbox" ${value.favorite ? "checked" : ""} data-prompt-template-favorite>
        <span>${escapeHtml(translate("templates.formFavorite"))}</span>
      </label>
      <button class="run-button prompt-template-save" type="submit">${escapeHtml(translate("action.save"))}</button>
    </form>
  `;
  els.promptTemplateForm.classList.remove("hidden");
  renderPromptTemplateThumbnailPicker(value.thumbnail_url || "");
}

function promptTemplateCategoriesForSelect(selectedCategory: any) {
  const categories = normalizePromptTemplateCategoryList(state.promptTemplateCategories);
  const selected = String(selectedCategory || "").trim();
  if (selected && !categories.some((category: any) => category.id === selected)) {
    categories.push({ id: selected, name: selected, order: categories.length * 10 + 10 });
  }
  return categories;
}

function historyTemplateThumbnails() {
  const seen = new Set<string>();
  const items: Array<{ url: string; label: string }> = [];
  (state.tasks || []).forEach((task: any) => {
    const urls: string[] = [];
    if (Array.isArray(task?.outputs)) {
      task.outputs.forEach((output: any) => {
        if (output?.status === "completed" && output?.url) urls.push(String(output.url));
      });
    }
    if (Array.isArray(task?.output_urls)) urls.push(...task.output_urls.map((url: any) => String(url || "")).filter(Boolean));
    if (task?.output_url) urls.push(String(task.output_url));
    urls.forEach((url, index) => {
      if (!url || seen.has(url)) return;
      seen.add(url);
      items.push({
        url,
        label: `${promptTemplatePreview(task?.prompt || task?.prompt_for_model || task?.task_id || translate("templates.history"), 18)} ${index + 1}`,
      });
    });
  });
  return items.slice(0, 16);
}

function renderPromptTemplateThumbnailPicker(selectedUrl = "") {
  const form = els.promptTemplateForm?.querySelector(".prompt-template-form") as HTMLElement | null;
  if (!form) return;
  const picker = form.querySelector("[data-prompt-template-thumbnail-picker]") as HTMLElement | null;
  const preview = form.querySelector("[data-prompt-template-thumbnail-preview]") as HTMLElement | null;
  const input = form.querySelector("[data-prompt-template-thumbnail-url]") as HTMLInputElement | null;
  if (input) input.value = selectedUrl;
  if (preview) {
    preview.innerHTML = selectedUrl
      ? `<img src="${escapeHtml(selectedUrl)}" alt=""><span>${escapeHtml(promptTemplatePreview(selectedUrl, 30))}</span>`
      : `<span>${escapeHtml(translate("templates.thumbnailNone"))}</span>`;
  }
  if (!picker) return;
  const thumbnails = historyTemplateThumbnails();
  if (!thumbnails.length) {
    picker.innerHTML = `<div class="prompt-template-thumbnail-empty">${escapeHtml(translate("templates.thumbnailEmpty"))}</div>`;
    return;
  }
  picker.innerHTML = thumbnails.map((item) => `
    <button class="prompt-template-thumbnail-option ${item.url === selectedUrl ? "active" : ""}" type="button" data-prompt-template-thumbnail-select="${escapeHtml(item.url)}" title="${escapeHtml(item.label)}">
      <img src="${escapeHtml(item.url)}" alt="">
    </button>
  `).join("");
}

function setPromptTemplateThumbnailUrl(url: any) {
  renderPromptTemplateThumbnailPicker(String(url || "").trim());
}

function setPromptTemplateSummary(message: string, type = "") {
  if (!els.promptTemplateSummary) return;
  els.promptTemplateSummary.textContent = message;
  els.promptTemplateSummary.className = ["prompt-template-summary", type].filter(Boolean).join(" ");
}

async function savePromptTemplateFromDrawer() {
  const form = els.promptTemplateForm?.querySelector(".prompt-template-form") as HTMLFormElement | null;
  if (!form) return;
  const templateId = form.dataset.promptTemplateFormId || "";
  const payload = {
    title: (form.querySelector("[data-prompt-template-title]") as HTMLInputElement | null)?.value || "",
    short_title: (form.querySelector("[data-prompt-template-short-title]") as HTMLInputElement | null)?.value || "",
    category: (form.querySelector("[data-prompt-template-category-input]") as HTMLSelectElement | null)?.value || PROMPT_TEMPLATE_CATEGORY_COMMON,
    tags: ((form.querySelector("[data-prompt-template-tags]") as HTMLInputElement | null)?.value || "").split(/[，,]/).map((tag) => tag.trim()).filter(Boolean),
    content: (form.querySelector("[data-prompt-template-content]") as HTMLTextAreaElement | null)?.value || "",
    notes: (form.querySelector("[data-prompt-template-notes]") as HTMLTextAreaElement | null)?.value || "",
    thumbnail_url: (form.querySelector("[data-prompt-template-thumbnail-url]") as HTMLInputElement | null)?.value || "",
    favorite: Boolean((form.querySelector("[data-prompt-template-favorite]") as HTMLInputElement | null)?.checked),
    model_hint: "gpt-image-2",
  };
  try {
    const response = await fetch(templateId ? `${PROMPT_TEMPLATES_ENDPOINT}/${encodeURIComponent(templateId)}` : PROMPT_TEMPLATES_ENDPOINT, {
      method: templateId ? "PATCH" : "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || translate("templates.saveFailed"));
    applyPromptTemplateSettingsResponse(data);
    hidePromptTemplateForm();
    setStatus(translate("templates.saved"), "ok");
  } catch (error: any) {
    setStatus(error.message || translate("templates.saveFailed"), "error");
  }
}

async function deletePromptTemplate(template: any) {
  if (!template) return;
  try {
    const response = await fetch(`${PROMPT_TEMPLATES_ENDPOINT}/${encodeURIComponent(template.id)}`, { method: "DELETE" });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || translate("templates.deleteFailed"));
    applyPromptTemplateSettingsResponse(data);
    hidePromptTemplateForm();
    hidePromptTemplateDetail();
    setStatus(translate("templates.deleted"), "ok");
  } catch (error: any) {
    setStatus(error.message || translate("templates.deleteFailed"), "error");
  }
}

async function createPromptTemplateCategory(name: any) {
  const clean = String(name || "").trim();
  if (!clean) return;
  try {
    const response = await fetch(PROMPT_TEMPLATE_CATEGORIES_ENDPOINT, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name: clean }),
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || translate("templates.categoryAddFailed"));
    applyPromptTemplateSettingsResponse(data);
    renderPromptTemplateCategoryPanel();
    setStatus(translate("templates.categoryAdded"), "ok");
  } catch (error: any) {
    setStatus(error.message || translate("templates.categoryAddFailed"), "error");
  }
}

async function updatePromptTemplateCategory(categoryId: any, name: any) {
  const clean = String(name || "").trim();
  if (!categoryId || !clean) return;
  try {
    const response = await fetch(`${PROMPT_TEMPLATE_CATEGORIES_ENDPOINT}/${encodeURIComponent(String(categoryId))}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name: clean }),
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || translate("templates.categorySaveFailed"));
    applyPromptTemplateSettingsResponse(data);
    renderPromptTemplateCategoryPanel();
    setStatus(translate("templates.categorySaved"), "ok");
  } catch (error: any) {
    setStatus(error.message || translate("templates.categorySaveFailed"), "error");
  }
}

async function deletePromptTemplateCategory(categoryId: any) {
  if (!categoryId) return;
  try {
    const response = await fetch(`${PROMPT_TEMPLATE_CATEGORIES_ENDPOINT}/${encodeURIComponent(String(categoryId))}`, { method: "DELETE" });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || translate("templates.categoryDeleteFailed"));
    applyPromptTemplateSettingsResponse(data);
    renderPromptTemplateCategoryPanel();
    setStatus(translate("templates.categoryDeleted"), "ok");
  } catch (error: any) {
    setStatus(error.message || translate("templates.categoryDeleteFailed"), "error");
  }
}

async function importPromptTemplatePack(file: File | null | undefined) {
  if (!file) return;
  const formData = new FormData();
  formData.append("file", file);
  try {
    const response = await fetch(PROMPT_TEMPLATE_IMPORT_ENDPOINT, { method: "POST", body: formData });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || translate("templates.importFailed"));
    applyPromptTemplateSettingsResponse(data);
    const message = formatTranslation("templates.importedCount", { count: data.imported || 0 });
    setPromptTemplateSummary(message, "ok");
    setStatus(message, "ok");
  } catch (error: any) {
    const message = error.message || translate("templates.importFailed");
    setPromptTemplateSummary(message, "error");
    setStatus(message, "error");
  }
}

async function exportPromptTemplatePack() {
  const button = els.promptTemplateExportButton as HTMLButtonElement | null;
  if (button) button.disabled = true;
  try {
    const response = await fetch(PROMPT_TEMPLATE_EXPORT_ENDPOINT, {
      headers: { Accept: "application/json" },
    });
    const text = await response.text();
    if (!response.ok) {
      let message = translate("templates.exportFailed");
      try {
        const data = JSON.parse(text);
        message = data?.detail || message;
      } catch {
        // Keep the fallback message when the server returns non-JSON text.
      }
      throw new Error(message);
    }
    const blob = new Blob([text], { type: "application/json;charset=utf-8" });
    const objectUrl = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = objectUrl;
    link.download = "webui-prompt-templates.json";
    link.style.display = "none";
    document.body.appendChild(link);
    link.click();
    window.setTimeout(() => {
      URL.revokeObjectURL(objectUrl);
      link.remove();
    }, 0);
    setPromptTemplateSummary(translate("templates.exported"), "ok");
    setStatus(translate("templates.exported"), "ok");
  } catch (error: any) {
    const message = error.message || translate("templates.exportFailed");
    setPromptTemplateSummary(message, "error");
    setStatus(message, "error");
  } finally {
    if (button) button.disabled = false;
  }
}

function hidePromptTemplateDetail() {
  if (!els.promptTemplateDetail) return;
  els.promptTemplateDetail.classList.add("hidden");
  els.promptTemplateDetail.innerHTML = "";
  els.promptTemplateList?.classList.remove("hidden");
}

function hidePromptTemplateForm() {
  if (!els.promptTemplateForm) return;
  els.promptTemplateForm.classList.add("hidden");
  els.promptTemplateForm.innerHTML = "";
  els.promptTemplateList?.classList.remove("hidden");
}

function findPromptTemplateById(id: any) {
  return (state.promptTemplates || []).find((template: any) => template.id === id) || null;
}

function promptTemplatePreview(text: any, length = 80) {
  const clean = String(text || "").replace(/\s+/g, " ").trim();
  return clean.length > length ? `${clean.slice(0, length)}...` : clean;
}

function bindPromptTemplateEvents() {
  els.promptTemplateButton?.addEventListener("click", openPromptTemplateDrawer);
  els.promptTemplateDrawerClose?.addEventListener("click", closePromptTemplateDrawer);
  els.promptTemplateDrawerBackdrop?.addEventListener("click", closePromptTemplateDrawer);
  els.promptTemplateCreateButton?.addEventListener("click", () => renderPromptTemplateForm());
  els.promptTemplateCategoryManageButton?.addEventListener("click", togglePromptTemplateCategoryPanel);
  els.promptTemplateImportButton?.addEventListener("click", () => (els.promptTemplateImportInput as HTMLInputElement | null)?.click());
  els.promptTemplateExportButton?.addEventListener("click", () => {
    void exportPromptTemplatePack();
  });
  els.promptTemplateImportInput?.addEventListener("change", () => {
    const input = els.promptTemplateImportInput as HTMLInputElement | null;
    const file = input?.files?.[0];
    void importPromptTemplatePack(file);
    if (input) input.value = "";
  });
  els.promptTemplateSearch?.addEventListener("pointerdown", (event: Event) => {
    const input = els.promptTemplateSearch as HTMLInputElement | null;
    if (!input?.readOnly) return;
    event.preventDefault();
    setPromptTemplateSearchLocked(false);
    syncPromptTemplateSearchInput();
    input.focus({ preventScroll: true });
  });
  els.promptTemplateSearch?.addEventListener("keydown", (event: KeyboardEvent) => {
    const input = els.promptTemplateSearch as HTMLInputElement | null;
    if (input?.readOnly && !event.metaKey && !event.ctrlKey && !event.altKey) {
      const key = event.key || "";
      const isPrintable = key.length === 1;
      const isClearKey = key === "Backspace" || key === "Delete";
      if (isPrintable || isClearKey) {
        event.preventDefault();
        setPromptTemplateSearchLocked(false);
        promptTemplateSearchAcceptManualInput = true;
        const nextValue = isClearKey ? "" : key;
        input.value = nextValue;
        state.promptTemplateQuery = nextValue;
        renderPromptTemplateList();
      }
      return;
    }
    promptTemplateSearchAcceptManualInput = true;
  });
  els.promptTemplateSearch?.addEventListener("paste", () => {
    promptTemplateSearchAcceptManualInput = true;
  });
  els.promptTemplateSearch?.addEventListener("drop", () => {
    promptTemplateSearchAcceptManualInput = true;
  });
  els.promptTemplateSearch?.addEventListener("blur", () => {
    promptTemplateSearchAcceptManualInput = false;
    setPromptTemplateSearchLocked(true);
  });
  els.promptTemplateSearch?.addEventListener("input", () => {
    if (!promptTemplateSearchAcceptManualInput) {
      syncPromptTemplateSearchInput();
      guardPromptTemplateSearchInput([120, 360, 900]);
      return;
    }
    state.promptTemplateQuery = els.promptTemplateSearch?.value || "";
    renderPromptTemplateList();
  });
  els.promptTemplateSearch?.addEventListener("focus", () => {
    promptTemplateSearchAcceptManualInput = false;
    guardPromptTemplateSearchInput();
  });
  els.promptTemplateDrawer?.addEventListener("click", (event: Event) => {
    const target = event.target as HTMLElement | null;
    const filter = target?.closest("[data-prompt-template-filter]") as HTMLElement | null;
    const category = target?.closest("[data-prompt-template-category]") as HTMLElement | null;
    const categoryCreate = target?.closest("[data-prompt-template-category-create]") as HTMLElement | null;
    const categoryRename = target?.closest("[data-prompt-template-category-rename]") as HTMLElement | null;
    const categoryDelete = target?.closest("[data-prompt-template-category-delete]") as HTMLElement | null;
    const thumbnailSelect = target?.closest("[data-prompt-template-thumbnail-select]") as HTMLElement | null;
    const thumbnailClear = target?.closest("[data-prompt-template-thumbnail-clear]") as HTMLElement | null;
    const card = target?.closest("[data-prompt-template-id]") as HTMLElement | null;
    const insert = target?.closest("[data-prompt-template-insert]") as HTMLElement | null;
    const replace = target?.closest("[data-prompt-template-replace]") as HTMLElement | null;
    const copy = target?.closest("[data-prompt-template-copy]") as HTMLElement | null;
    const edit = target?.closest("[data-prompt-template-edit]") as HTMLElement | null;
    const remove = target?.closest("[data-prompt-template-delete]") as HTMLElement | null;
    const back = target?.closest("[data-prompt-template-back]");
    if (filter) {
      state.promptTemplateFilter = filter.dataset.promptTemplateFilter || "all";
      els.promptTemplateDrawer?.querySelectorAll("[data-prompt-template-filter]").forEach((button: any) => {
        button.classList.toggle("active", button === filter);
      });
      renderPromptTemplateList();
      return;
    }
    if (category) {
      state.promptTemplateCategory = category.dataset.promptTemplateCategory || "";
      renderPromptTemplateCategories();
      renderPromptTemplateList();
      return;
    }
    if (categoryCreate) {
      const input = els.promptTemplateCategoryPanel?.querySelector("[data-prompt-template-category-new]") as HTMLInputElement | null;
      void createPromptTemplateCategory(input?.value || "");
      return;
    }
    if (categoryRename || categoryDelete) {
      const row = target?.closest("[data-prompt-template-category-row]") as HTMLElement | null;
      const categoryId = row?.dataset.promptTemplateCategoryRow || "";
      if (categoryRename) {
        const input = row?.querySelector("[data-prompt-template-category-name]") as HTMLInputElement | null;
        void updatePromptTemplateCategory(categoryId, input?.value || "");
      } else {
        void deletePromptTemplateCategory(categoryId);
      }
      return;
    }
    if (thumbnailSelect) {
      setPromptTemplateThumbnailUrl(thumbnailSelect.dataset.promptTemplateThumbnailSelect || "");
      return;
    }
    if (thumbnailClear) {
      setPromptTemplateThumbnailUrl("");
      return;
    }
    if (back) {
      hidePromptTemplateDetail();
      hidePromptTemplateForm();
      return;
    }
    if (insert) {
      const template = findPromptTemplateById(insert.dataset.promptTemplateInsert);
      void applyPromptTemplate(template, "insert");
    } else if (replace) {
      const template = findPromptTemplateById(replace.dataset.promptTemplateReplace);
      void applyPromptTemplate(template, "replace");
    } else if (copy) {
      void copyPromptTemplateContent(findPromptTemplateById(copy.dataset.promptTemplateCopy));
    } else if (edit) {
      renderPromptTemplateForm(findPromptTemplateById(edit.dataset.promptTemplateEdit));
    } else if (remove) {
      void deletePromptTemplate(findPromptTemplateById(remove.dataset.promptTemplateDelete));
    } else if (card) {
      selectPromptTemplate(card.dataset.promptTemplateId);
    }
  });
  els.promptTemplateForm?.addEventListener("submit", (event: Event) => {
    event.preventDefault();
    void savePromptTemplateFromDrawer();
  });
  els.promptTemplateRecentDock?.addEventListener("click", (event: Event) => {
    const button = (event.target as HTMLElement | null)?.closest("[data-prompt-template-insert]") as HTMLElement | null;
    if (!button) return;
    const template = findPromptTemplateById(button.dataset.promptTemplateInsert);
    void applyPromptTemplate(template, "insert");
  });
}

export function initPromptTemplatesFeature(): void {
  document.addEventListener(LOCALE_CHANGE_EVENT, () => {
    renderPromptTemplateCategories();
    renderPromptTemplateList();
    if (state.selectedPromptTemplateId && !els.promptTemplateDetail?.classList.contains("hidden")) {
      selectPromptTemplate(state.selectedPromptTemplateId);
    }
  });
  Object.assign(getLegacyBridge().methods, {
    normalizePromptTemplate,
    normalizePromptTemplateCategory,
    normalizePromptTemplateList,
    normalizePromptTemplateCategoryList,
    refreshPromptTemplates,
    openPromptTemplateDrawer,
    closePromptTemplateDrawer,
    renderPromptTemplateCategories,
    promptTemplateCategoryLabel,
    renderPromptTemplateCategoryPanel,
    togglePromptTemplateCategoryPanel,
    promptTemplatesForDisplay,
    renderPromptTemplateList,
    renderPromptTemplateRecentDock,
    selectPromptTemplate,
    applyPromptTemplate,
    afterPromptTemplateApplied,
    copyPromptTemplateContent,
    renderPromptTemplateForm,
    historyTemplateThumbnails,
    renderPromptTemplateThumbnailPicker,
    importPromptTemplatePack,
    exportPromptTemplatePack,
    savePromptTemplateFromDrawer,
    deletePromptTemplate,
    createPromptTemplateCategory,
    updatePromptTemplateCategory,
    deletePromptTemplateCategory,
    hidePromptTemplateDetail,
    hidePromptTemplateForm,
    findPromptTemplateById,
    promptTemplatePreview,
  });
  bindPromptTemplateEvents();
}

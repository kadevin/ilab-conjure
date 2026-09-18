import { clearHistoryActiveFilters, collectHistoryActiveFilters, removeHistoryActiveFilter, type HistoryActiveFilterItem, type HistoryActiveFilterSnapshot } from "./history-active-filters";
import { type HistoryBackupFilters } from "./history-backup";
import { createHistoryTag, deleteHistoryTag, HistoryOrganizationRequestError, historyOrganizationSummarySupported, readHistoryOrganizationFilters, renameHistoryTag, withHistoryTagFilter, withHistoryUntaggedFilter, writeHistoryOrganizationFilters, type HistoryOrganization, type HistoryOrganizationFilters, type HistoryTag } from "./history-organization";
import { historyTaskPageQuery, type HistoryPageQueryInput } from "./history-position-runtime";
import { errorMessage, escapeHtml, facetDisplayValue, historyFilterAttribute, setText } from "./history-presentation";
import { HISTORY_FILTER_QUERY_KEYS, historySnapshotQuery, saveHistoryLocationSnapshot, type HistoryLoadOptions, type HistoryLoadResult } from "./history-scroll-memory";
import type { HistoryTask } from "./history-types";
import { type HistoryFacet, type HistoryFilterKey, type HistorySummary, type HistoryViewMode } from "./history-types";
import { type HistoryScrollAnchor, type HistoryWindowDirection } from "./history-window";
import { formatTranslation, translate } from "./i18n";

export function createHistoryFiltersController(options: {
  selectedTaskId(): string;
  selectLocationTask(id: string): void;
  resetSelection(): void;
  clearDeleteConfirmation(): void;
  loadTasks(options: HistoryLoadOptions): Promise<HistoryLoadResult>;
  scheduleLayout(): void;
  loadedTasks(): HistoryTask[];
  applyOrganizations(organizations: Record<string, HistoryOrganization>): void
}) {
  const els = {
    mobileFiltersButton: document.querySelector<HTMLButtonElement>("#historyMobileFiltersButton"),
    mobileFilterCount: document.querySelector<HTMLElement>("#historyMobileFilterCount"),
    total: document.querySelector<HTMLElement>("#historyTotal"),
    search: document.querySelector<HTMLInputElement>("#historySearch"),
    searchClear: document.querySelector<HTMLButtonElement>("#historySearchClear"),
    favoriteList: document.querySelector<HTMLElement>("#historyFavoriteList"),
    tagFilterList: document.querySelector<HTMLElement>("#historyTagFilterList"),
    tagManageToggle: document.querySelector<HTMLButtonElement>("#historyTagManageToggle"),
    tagManager: document.querySelector<HTMLElement>("#historyTagManager"),
    tagManagerList: document.querySelector<HTMLElement>("#historyTagManagerList"),
    tagManagerStatus: document.querySelector<HTMLElement>("#historyTagManagerStatus"),
    tagNameInput: document.querySelector<HTMLInputElement>("#historyTagNameInput"),
    modeList: document.querySelector<HTMLElement>("#historyModeList"),
    monthList: document.querySelector<HTMLElement>("#historyMonthList"),
    promptModeList: document.querySelector<HTMLElement>("#historyPromptModeList"),
    qualityList: document.querySelector<HTMLElement>("#historyQualityList"),
    ratioList: document.querySelector<HTMLElement>("#historyRatioList"),
    orientationList: document.querySelector<HTMLElement>("#historyOrientationList"),
    backendList: document.querySelector<HTMLElement>("#historyBackendList"),
    providerList: document.querySelector<HTMLElement>("#historyProviderList"),
    sortToggle: document.querySelector<HTMLElement>("#historySortToggle"),
    viewToggle: document.querySelector<HTMLElement>("#historyViewToggle"),
    resultSummary: document.querySelector<HTMLElement>("#historyResultSummary"),
    activeFilters: document.querySelector<HTMLElement>("#historyActiveFilters"),
    activeFiltersLabel: document.querySelector<HTMLElement>("#historyActiveFiltersLabel"),
    activeFilterList: document.querySelector<HTMLElement>("#historyActiveFilterList"),
    clearAllFilters: document.querySelector<HTMLButtonElement>("#historyClearAllFilters"),
    taskList: document.querySelector<HTMLElement>("#historyTaskList"),
  };

  const historyState = {
    q: "",
    mode: "",
    month: "",
    prompt_mode: "",
    quality: "",
    ratio: "",
    orientation: "",
    backend: "",
    provider: "",
    archived: "",
    sort: "newest",
    view: "grid" as HistoryViewMode,
  };
  let historyTags: HistoryTag[] = [];

  let historySummary: HistorySummary | null = null;

  let historyOrganizationFilters: HistoryOrganizationFilters = {
    favorite: false,
    tagIds: [],
    untagged: false,
  };

  let historyTagDeleteConfirmId = "";

  let historyTagManagerCreatePending = false;

  let historyOrganizationApiSupported: boolean | null = null;
  function currentHistoryBackupFilters(): HistoryBackupFilters {
    return {
      q: historyState.q,
      month: historyState.month,
      mode: historyState.mode,
      status: "",
      prompt_mode: historyState.prompt_mode,
      size: "",
      quality: historyState.quality,
      ratio: historyState.ratio,
      orientation: historyState.orientation,
      backend: historyState.backend,
      provider: historyState.provider,
      archived: historyState.archived === "true" ? true : historyState.archived === "false" ? false : null,
      favorite: historyOrganizationFilters.favorite ? true : null,
      tag_ids: [...historyOrganizationFilters.tagIds],
      untagged: historyOrganizationFilters.untagged,
      sort: historyState.sort === "oldest" ? "oldest" : "newest",
    };
  }

  function currentHistoryActiveFilterSnapshot(): HistoryActiveFilterSnapshot {
    const filters: HistoryActiveFilterSnapshot["filters"] = {};
    for (const key of HISTORY_FILTER_QUERY_KEYS) {
      filters[key] = historyState[key];
    }
    return {
      q: historyState.q,
      filters,
      organization: {
        favorite: historyOrganizationFilters.favorite,
        tagIds: [...historyOrganizationFilters.tagIds],
        untagged: historyOrganizationFilters.untagged,
      },
    };
  }

  function historyActiveFilterTitle(key: HistoryFilterKey): string {
    const translationKeys: Record<HistoryFilterKey, string> = {
      mode: "history.type",
      month: "history.month",
      prompt_mode: "history.promptMode",
      quality: "history.quality",
      ratio: "history.ratio",
      orientation: "history.orientation",
      backend: "history.backend",
      provider: "history.provider",
      archived: "history.archived",
    };
    return translate(translationKeys[key]);
  }

  function historyActiveFilterLabel(
    item: HistoryActiveFilterItem,
  ): string {
    if (item.kind === "q") {
      return `${translate("history.search")} · ${item.value}`;
    }
    if (item.kind === "favorite") {
      return translate("history.onlyFavorites");
    }
    if (item.kind === "untagged") {
      return translate("history.untagged");
    }
    if (item.kind === "tag") {
      const name = historyTags.find(
        (tag) => tag.tag_id === item.value,
      )?.name || item.value;
      return `${translate("history.tags")} · ${name}`;
    }
    const value = item.key === "archived"
      ? item.value === "true"
        ? translate("history.archivedOnly")
        : translate("history.unarchived")
      : facetDisplayValue(item.key, item.value);
    return `${historyActiveFilterTitle(item.key)} · ${value}`;
  }

  function renderHistoryActiveFilters(): void {
    const items = collectHistoryActiveFilters(
      currentHistoryActiveFilterSnapshot(),
    );
    const count = items.length;
    const hidden = count === 0;
    els.activeFilters?.classList.toggle("hidden", hidden);
    els.activeFilters?.toggleAttribute("hidden", hidden);
    els.activeFilters?.setAttribute(
      "aria-label",
      hidden
        ? translate("sidebar.filters")
        : formatTranslation("history.activeFilterCount", { count }),
    );
    setText(
      els.activeFiltersLabel,
      hidden
        ? ""
        : formatTranslation("history.activeFilterCount", { count }),
    );
    setText(els.clearAllFilters, translate("history.clearAllFilters"));
    if (els.activeFilterList) {
      els.activeFilterList.innerHTML = items.map((item) => {
        const label = historyActiveFilterLabel(item);
        const removeLabel = formatTranslation(
          "history.removeFilter",
          { label },
        );
        return `
        <span class="history-active-filter-item" role="listitem">
          <button
            class="history-active-filter-chip"
            type="button"
            data-history-remove-active-filter="${escapeHtml(item.id)}"
            aria-label="${escapeHtml(removeLabel)}"
            title="${escapeHtml(removeLabel)}"
          >
            <span class="history-active-filter-chip-label">${escapeHtml(label)}</span>
            <svg class="history-active-filter-chip-icon" viewBox="0 0 16 16" aria-hidden="true" focusable="false"><path d="m4 4 8 8m0-8-8 8" /></svg>
          </button>
        </span>
      `;
      }).join("");
    }
    els.mobileFilterCount?.classList.toggle("hidden", hidden);
    els.mobileFilterCount?.toggleAttribute("hidden", hidden);
    setText(els.mobileFilterCount, hidden ? "" : String(count));
    els.mobileFiltersButton?.classList.toggle(
      "has-active-filters",
      !hidden,
    );
    els.mobileFiltersButton?.setAttribute(
      "aria-label",
      hidden
        ? translate("sidebar.filters")
        : formatTranslation("history.filtersActive", { count }),
    );
  }

  function syncHistoryFilterButtonsFromState(): void {
    for (const key of HISTORY_FILTER_QUERY_KEYS) {
      const attr = historyFilterAttribute(key);
      document
        .querySelectorAll<HTMLElement>(`[data-history-${attr}]`)
        .forEach((button) => {
          button.classList.toggle(
            "active",
            button.getAttribute(`data-history-${attr}`) ===
            historyState[key],
          );
        });
    }
  }

  function applyHistoryActiveFilterSnapshot(
    snapshot: HistoryActiveFilterSnapshot,
  ): void {
    historyState.q = snapshot.q;
    for (const key of HISTORY_FILTER_QUERY_KEYS) {
      historyState[key] = String(snapshot.filters[key] || "");
    }
    historyOrganizationFilters = {
      favorite: snapshot.organization.favorite,
      tagIds: [...snapshot.organization.tagIds],
      untagged: snapshot.organization.untagged,
    };
    options.resetSelection();
    options.clearDeleteConfirmation();
    if (els.search) els.search.value = historyState.q;
    syncHistorySearchClear();
    syncHistoryFilterButtonsFromState();
    renderHistoryOrganizationFilters();
    renderHistoryActiveFilters();
    updateHistoryUrl();
    void options.loadTasks({ reset: true });
  }

  function removeHistoryActiveFilterById(id: string): void {
    const snapshot = currentHistoryActiveFilterSnapshot();
    const item = collectHistoryActiveFilters(snapshot).find(
      (candidate) => candidate.id === id,
    );
    if (!item) return;
    applyHistoryActiveFilterSnapshot(
      removeHistoryActiveFilter(snapshot, item),
    );
  }

  function clearAllHistoryActiveFilters(): void {
    applyHistoryActiveFilterSnapshot(
      clearHistoryActiveFilters(
        currentHistoryActiveFilterSnapshot(),
      ),
    );
  }

  function historyOrientationIconHtml(value: string): string {
    if (value === "portrait") {
      return `<svg class="history-filter-icon history-filter-icon-portrait" viewBox="0 0 20 20" aria-hidden="true" focusable="false">
        <rect x="6.5" y="3" width="7" height="14" rx="2"></rect>
      </svg>`;
    }
    if (value === "landscape") {
      return `<svg class="history-filter-icon history-filter-icon-landscape" viewBox="0 0 20 20" aria-hidden="true" focusable="false">
        <rect x="3" y="6.5" width="14" height="7" rx="2"></rect>
      </svg>`;
    }
    if (value === "square") {
      return `<svg class="history-filter-icon history-filter-icon-square" viewBox="0 0 20 20" aria-hidden="true" focusable="false">
        <rect x="5" y="5" width="10" height="10" rx="2"></rect>
      </svg>`;
    }
    return `<svg class="history-filter-icon history-filter-icon-all" viewBox="0 0 20 20" aria-hidden="true" focusable="false">
      <rect x="3.5" y="4" width="5" height="8" rx="1.5"></rect>
      <rect x="10.5" y="5" width="6" height="4.5" rx="1.4"></rect>
      <rect x="10.5" y="11.5" width="5" height="5" rx="1.4"></rect>
    </svg>`;
  }

  function historyFilterButtonLabelHtml(key: HistoryFilterKey, label: string, value = ""): string {
    if (key !== "orientation") return escapeHtml(label);
    return `${historyOrientationIconHtml(value)}<span class="history-filter-label">${escapeHtml(label)}</span>`;
  }

  function syncStateFromUrl(): void {
    const params = new URLSearchParams(window.location.search);
    historyOrganizationFilters =
      readHistoryOrganizationFilters(params);
    historyState.q = params.get("q") || "";
    historyState.sort = params.get("sort") === "oldest" ? "oldest" : "newest";
    historyState.view = params.get("view") === "list" ? "list" : "grid";
    for (const key of HISTORY_FILTER_QUERY_KEYS) {
      historyState[key] = params.get(key) || "";
    }
    for (const key of ["backend", "provider"] as const) {
      const section = document.querySelector<HTMLDetailsElement>(`[data-history-filter-section="${key}"]`);
      if (section && historyState[key]) section.open = true;
    }
    options.selectLocationTask(params.get("task") || "");
    if (els.search) els.search.value = historyState.q;
    syncHistorySearchClear();
    syncHistorySortMode();
    syncHistoryViewMode();
    renderHistoryActiveFilters();
  }

  function syncHistorySearchClear(): void {
    const hasQuery = Boolean(els.search?.value.trim());
    els.searchClear?.classList.toggle("hidden", !hasQuery);
    els.searchClear?.toggleAttribute("hidden", !hasQuery);
  }

  function updateHistoryUrl(): void {
    const params = new URLSearchParams();
    if (historyState.q) params.set("q", historyState.q);
    if (historyState.sort !== "newest") params.set("sort", historyState.sort);
    if (historyState.view !== "grid") params.set("view", historyState.view);
    for (const key of HISTORY_FILTER_QUERY_KEYS) {
      if (historyState[key]) params.set(key, historyState[key]);
    }
    writeHistoryOrganizationFilters(
      params,
      historyOrganizationFilters,
    );
    if (options.selectedTaskId()) params.set("task", options.selectedTaskId());
    const query = params.toString();
    const nextUrl = query ? `${window.location.pathname}?${query}` : window.location.pathname;
    window.history.replaceState(null, "", nextUrl);
  }

  function saveCurrentHistoryLocation(
    anchor: NonNullable<HistoryScrollAnchor>,
  ): void {
    updateHistoryUrl();
    saveHistoryLocationSnapshot({
      version: 1,
      query: historySnapshotQuery(
        new URLSearchParams(window.location.search),
      ),
      anchor,
      savedAt: Date.now(),
    });
  }

  async function loadSummary(options: { throwOnError?: boolean } = {}): Promise<void> {
    try {
      const response = await fetch("/api/task-history/summary");
      const summary = await response.json() as HistorySummary;
      if (!response.ok) throw new Error((summary as any).detail || translate("history.summaryFailed"));
      if (!historyOrganizationSummarySupported(summary)) {
        historyOrganizationApiSupported = false;
        throw new Error(
          translate("history.backendRestartRequired"),
        );
      }
      historyOrganizationApiSupported = true;
      historySummary = summary;
      historyTags = Array.isArray(summary.tags) ? summary.tags : [];
      setText(els.total, formatTranslation("history.total", { total: summary.total, archived: summary.archived_total }));
      renderHistoryOrganizationFilters(summary);
      renderHistoryTagManager();
      renderFacetButtons(els.modeList, "mode", summary.modes || [], translate("history.allTypes"));
      renderFacetButtons(els.monthList, "month", summary.months.map((item) => ({ value: item.month, count: item.count })), translate("history.allMonths"));
      renderFacetButtons(els.promptModeList, "prompt_mode", summary.prompt_modes || [], translate("history.allPromptModes"));
      renderFacetButtons(els.qualityList, "quality", summary.qualities || [], translate("history.allQualities"));
      renderFacetButtons(els.ratioList, "ratio", summary.ratios, translate("history.allRatios"));
      renderFacetButtons(els.orientationList, "orientation", summary.orientations || [], translate("history.allOrientations"));
      renderFacetButtons(els.backendList, "backend", summary.backends || [], translate("history.allBackends"));
      renderFacetButtons(els.providerList, "provider", summary.providers || [], translate("history.allProviders"));
      syncArchiveButtons();
      renderHistoryActiveFilters();
    } catch (error) {
      const message = errorMessage(
        error,
        translate("history.summaryFailed"),
      );
      setText(els.total, message);
      if (historyOrganizationApiSupported === false) {
        setText(els.resultSummary, message);
      }
      if (options.throwOnError) throw error;
    }
  }

  function renderHistoryOrganizationFilters(
    summary?: Partial<HistorySummary>,
  ): void {
    const counts = summary || historySummary || {};
    if (els.favoriteList) {
      const active = historyOrganizationFilters.favorite;
      els.favoriteList.innerHTML = `
      <button
        class="history-filter-button${active ? " active" : ""}"
        type="button"
        data-history-favorite-filter
        aria-pressed="${active ? "true" : "false"}"
      >
        <span>${escapeHtml(translate("history.onlyFavorites"))}</span>
        <span class="history-filter-count">${Number(counts.favorite_total || 0)}</span>
      </button>
    `;
    }
    if (!els.tagFilterList) return;
    const selected = new Set(historyOrganizationFilters.tagIds);
    const untaggedActive = historyOrganizationFilters.untagged;
    els.tagFilterList.innerHTML = [
      `
      <button
        class="history-filter-button${untaggedActive ? " active" : ""}"
        type="button"
        data-history-untagged-filter
        aria-pressed="${untaggedActive ? "true" : "false"}"
      >
        <span>${escapeHtml(translate("history.untagged"))}</span>
        <span class="history-filter-count">${Number(counts.untagged_total || 0)}</span>
      </button>
    `,
      ...historyTags.map((tag) => {
        const active = selected.has(tag.tag_id);
        return `
        <button
          class="history-filter-button${active ? " active" : ""}"
          type="button"
          data-history-tag-filter="${escapeHtml(tag.tag_id)}"
          aria-pressed="${active ? "true" : "false"}"
        >
          <span>${escapeHtml(tag.name)}</span>
          <span class="history-filter-count">${Number(tag.count || 0)}</span>
        </button>
      `;
      }),
    ].join("");
  }

  function renderHistoryTagManager(): void {
    if (!els.tagManagerList) return;
    if (!historyTags.length) {
      els.tagManagerList.innerHTML = `
      <div class="history-tag-manager-empty">
        ${escapeHtml(translate("history.noTags"))}
      </div>
    `;
      return;
    }
    els.tagManagerList.innerHTML = historyTags
      .map((tag) => {
        const confirming =
          historyTagDeleteConfirmId === tag.tag_id;
        const affectedDeleteLabel = formatTranslation(
          "history.deleteTagAffected",
          {
            count: Number(tag.count || 0),
          },
        );
        const deleteLabel = confirming
          ? translate("history.confirmDelete")
          : translate("history.deleteTag");
        const deleteAriaLabel = confirming
          ? affectedDeleteLabel
          : deleteLabel;
        return `
        <div class="history-tag-manager-row" data-history-tag-row="${escapeHtml(tag.tag_id)}">
          <div class="history-tag-manager-row-field">
            <input
              class="control"
              type="text"
              maxlength="40"
              value="${escapeHtml(tag.name)}"
              data-history-tag-name="${escapeHtml(tag.tag_id)}"
              aria-label="${escapeHtml(translate("history.renameTag"))}"
            />
            <span class="history-filter-count">${Number(tag.count || 0)}</span>
          </div>
          <div class="history-tag-manager-row-actions">
            <button
              class="ghost-button text-sm"
              type="button"
              data-history-rename-tag="${escapeHtml(tag.tag_id)}"
            >${escapeHtml(translate("history.renameTag"))}</button>
            <button
              class="ghost-button text-sm${confirming ? " danger-button" : ""}"
              type="button"
              data-history-delete-tag="${escapeHtml(tag.tag_id)}"
              aria-label="${escapeHtml(deleteAriaLabel)}"
              title="${escapeHtml(deleteAriaLabel)}"
            >${escapeHtml(deleteLabel)}</button>
          </div>
        </div>
      `;
      })
      .join("");
  }

  function applyHistoryOrganizationFilterChange(
    filters: HistoryOrganizationFilters,
  ): void {
    if (historyOrganizationApiSupported === false) {
      setText(
        els.resultSummary,
        translate("history.backendRestartRequired"),
      );
      return;
    }
    historyOrganizationFilters = filters;
    options.resetSelection();
    options.clearDeleteConfirmation();
    renderHistoryOrganizationFilters();
    renderHistoryActiveFilters();
    updateHistoryUrl();
    void options.loadTasks({ reset: true });
  }

  function historyTagMutationErrorMessage(
    error: unknown,
  ): string {
    if (
      error instanceof HistoryOrganizationRequestError &&
      error.status === 409
    ) {
      return translate("history.tagNameConflict");
    }
    return errorMessage(
      error,
      translate("history.organizationFailed"),
    );
  }

  function historyTagCreateErrorMessage(
    error: unknown,
  ): string {
    if (
      error instanceof HistoryOrganizationRequestError &&
      error.status === 404
    ) {
      return translate("history.backendRestartRequired");
    }
    return historyTagMutationErrorMessage(error);
  }

  async function createHistoryTagFromManager(): Promise<void> {
    if (historyTagManagerCreatePending) return;
    const name = els.tagNameInput?.value.trim() || "";
    if (!name) {
      els.tagNameInput?.focus();
      return;
    }
    const form = els.tagManager?.querySelector<HTMLFormElement>(
      "[data-history-tag-create]",
    );
    const controls = form?.querySelectorAll<
      HTMLInputElement | HTMLButtonElement
    >("input, button");
    historyTagManagerCreatePending = true;
    controls?.forEach((control) => {
      control.disabled = true;
    });
    setText(els.tagManagerStatus, "");
    try {
      const tag = await createHistoryTag(name);
      if (els.tagNameInput) els.tagNameInput.value = "";
      await loadSummary();
      setText(
        els.tagManagerStatus,
        `${translate("history.createTag")}：${tag.name}`,
      );
    } catch (error) {
      const message = historyTagCreateErrorMessage(error);
      setText(els.tagManagerStatus, message);
      setText(
        els.resultSummary,
        message,
      );
    } finally {
      historyTagManagerCreatePending = false;
      controls?.forEach((control) => {
        control.disabled = false;
      });
    }
  }

  async function renameHistoryTagFromManager(
    tagId: string,
  ): Promise<void> {
    const input = els.tagManagerList?.querySelector<HTMLInputElement>(
      `[data-history-tag-name="${CSS.escape(tagId)}"]`,
    );
    const name = input?.value.trim() || "";
    if (!name) return;
    try {
      const tag = await renameHistoryTag(tagId, name);
      const organizations: Record<string, HistoryOrganization> = {};
      for (const task of options.loadedTasks()) {
        const taskId = task.task_id;
        if (!task.tags.some((item) => item.tag_id === tagId)) {
          continue;
        }
        organizations[taskId] = {
          favorite: task.favorite,
          tags: task.tags.map((item) =>
            item.tag_id === tagId
              ? { ...item, name: tag.name }
              : item
          ),
        };
      }
      options.applyOrganizations(organizations);
      await loadSummary();
    } catch (error) {
      setText(
        els.resultSummary,
        historyTagMutationErrorMessage(error),
      );
    }
  }

  async function deleteHistoryTagFromManager(
    tagId: string,
  ): Promise<void> {
    if (historyTagDeleteConfirmId !== tagId) {
      historyTagDeleteConfirmId = tagId;
      renderHistoryTagManager();
      return;
    }
    try {
      await deleteHistoryTag(tagId);
      historyTagDeleteConfirmId = "";
      historyOrganizationFilters = {
        ...historyOrganizationFilters,
        tagIds: historyOrganizationFilters.tagIds.filter(
          (value) => value !== tagId,
        ),
      };
      const organizations: Record<string, HistoryOrganization> = {};
      for (const task of options.loadedTasks()) {
        const taskId = task.task_id;
        organizations[taskId] = {
          favorite: task.favorite,
          tags: task.tags.filter(
            (item) => item.tag_id !== tagId,
          ),
        };
      }
      options.applyOrganizations(organizations);
      updateHistoryUrl();
      await loadSummary();
    } catch (error) {
      setText(
        els.resultSummary,
        errorMessage(
          error,
          translate("history.organizationFailed"),
        ),
      );
    }
  }

  function renderFacetButtons(root: HTMLElement | null, key: HistoryFilterKey, items: HistoryFacet[], allLabel: string): void {
    if (!root) return;
    const current = String(historyState[key] || "");
    const attr = historyFilterAttribute(key);
    root.innerHTML = [
      `<button class="history-filter-button ${current ? "" : "active"}" type="button" data-history-filter-key="${key}" data-history-${attr}="">${historyFilterButtonLabelHtml(key, allLabel)}</button>`,
      ...items.map((item) => {
        const active = current === item.value ? " active" : "";
        return `<button class="history-filter-button${active}" type="button" data-history-filter-key="${key}" data-history-${attr}="${escapeHtml(item.value)}">${historyFilterButtonLabelHtml(key, facetDisplayValue(key, item.value), item.value)}<span class="history-filter-count">${item.count}</span></button>`;
      }),
    ].join("");
  }

  function syncArchiveButtons(): void {
    document.querySelectorAll<HTMLElement>("[data-history-archived]").forEach((button) => {
      button.classList.toggle("active", button.getAttribute("data-history-archived") === historyState.archived);
    });
  }

  function syncHistorySortMode(): void {
    const sort = historyState.sort === "oldest" ? "oldest" : "newest";
    historyState.sort = sort;
    els.sortToggle?.querySelectorAll<HTMLElement>("[data-history-sort]").forEach((button) => {
      const active = button.dataset.historySort === sort;
      button.classList.toggle("active", active);
      button.setAttribute("aria-pressed", active ? "true" : "false");
    });
  }

  function applyHistorySort(sort: string): void {
    const nextSort = sort === "oldest" ? "oldest" : "newest";
    if (historyState.sort === nextSort) return;
    historyState.sort = nextSort;
    options.resetSelection();
    syncHistorySortMode();
    updateHistoryUrl();
    void options.loadTasks({ reset: true });
  }

  function historyPageQueryInput(
    cursor?: string | null,
    direction: HistoryWindowDirection = "next",
    anchorTaskId = "",
  ): HistoryPageQueryInput {
    const filters: HistoryPageQueryInput["filters"] = {};
    for (const key of HISTORY_FILTER_QUERY_KEYS) {
      if (historyState[key]) filters[key] = historyState[key];
    }
    return {
      limit: 50,
      sort: historyState.sort,
      cursor,
      direction,
      anchorTaskId,
      q: historyState.q,
      filters,
      organization: { ...historyOrganizationFilters, tagIds: [...historyOrganizationFilters.tagIds] },
    };
  }

  function queryParams(
    cursor?: string | null,
    direction: HistoryWindowDirection = "next",
    anchorTaskId = "",
  ): string {
    return historyTaskPageQuery(
      historyPageQueryInput(cursor, direction, anchorTaskId),
    );
  }

  function syncHistoryViewMode(): void {
    const view = historyState.view === "list" ? "list" : "grid";
    historyState.view = view;
    els.taskList?.classList.toggle("history-view-grid", view === "grid");
    els.taskList?.classList.toggle("history-view-list", view === "list");
    els.viewToggle?.querySelectorAll<HTMLElement>("[data-history-view]").forEach((button) => {
      const active = button.dataset.historyView === view;
      button.classList.toggle("active", active);
      button.setAttribute("aria-pressed", active ? "true" : "false");
    });
    if (view === "grid") options.scheduleLayout();
  }

  function setHistoryViewMode(view: string): void {
    historyState.view = view === "list" ? "list" : "grid";
    syncHistoryViewMode();
    updateHistoryUrl();
  }

  function applyFilter(key: HistoryFilterKey, value: string): void {
    historyState[key] = value;
    options.resetSelection();
    options.clearDeleteConfirmation();
    const attr = historyFilterAttribute(key);
    document.querySelectorAll(`[data-history-${attr}]`).forEach((node) => {
      node.classList.toggle("active", (node as HTMLElement).getAttribute(`data-history-${attr}`) === value);
    });
    renderHistoryActiveFilters();
    updateHistoryUrl();
    void options.loadTasks({ reset: true });
  }
  let searchTimer = 0;
  let bound = false;
  const lifetime = new AbortController();
  function bind(): void {
    if (bound) return; bound = true;
    els.tagManager?.querySelector<HTMLFormElement>(
      "[data-history-tag-create]",
    )?.addEventListener("submit", (event) => {
      event.preventDefault();
      void createHistoryTagFromManager();
    }, { signal: lifetime.signal });

    els.search?.addEventListener("input", () => {
      syncHistorySearchClear();
      window.clearTimeout(searchTimer);
      searchTimer = window.setTimeout(() => {
        historyState.q = els.search?.value.trim() || "";
        options.resetSelection();
        renderHistoryActiveFilters();
        updateHistoryUrl();
        void options.loadTasks({ reset: true });
      }, 180);
    }, { signal: lifetime.signal });
    els.searchClear?.addEventListener("click", () => {
      if (els.search) els.search.value = "";
      syncHistorySearchClear();
      els.search?.focus();
      historyState.q = "";
      options.resetSelection();
      renderHistoryActiveFilters();
      updateHistoryUrl();
      void options.loadTasks({ reset: true });
    }, { signal: lifetime.signal });
    els.sortToggle?.addEventListener("click", (event) => {
      const target = event.target as HTMLElement | null;
      const button = target?.closest<HTMLElement>("[data-history-sort]");
      if (!button || !els.sortToggle?.contains(button)) return;
      applyHistorySort(button.dataset.historySort || "newest");
    }, { signal: lifetime.signal });
  }
  function handleClick(target: HTMLElement | null): boolean {
    const removeActiveFilter = target?.closest<HTMLElement>(
      "[data-history-remove-active-filter]",
    );
    if (removeActiveFilter) {
      removeHistoryActiveFilterById(
        removeActiveFilter.dataset.historyRemoveActiveFilter || "",
      );
      return true;
    }
    if (target?.closest("[data-history-clear-all-filters]")) {
      clearAllHistoryActiveFilters();
      return true;
    }
    const tagManageToggle = target?.closest<HTMLElement>(
      "#historyTagManageToggle",
    );
    if (tagManageToggle) {
      const opening = Boolean(els.tagManager?.hidden);
      if (els.tagManager) {
        els.tagManager.hidden = !opening;
        els.tagManager.classList.toggle("hidden", !opening);
      }
      els.tagManageToggle?.setAttribute(
        "aria-expanded",
        opening ? "true" : "false",
      );
      if (opening) els.tagNameInput?.focus();
      return true;
    }
    const renameTagButton = target?.closest<HTMLElement>(
      "[data-history-rename-tag]",
    );
    if (renameTagButton) {
      void renameHistoryTagFromManager(
        renameTagButton.dataset.historyRenameTag || "",
      );
      return true;
    }
    const deleteTagButton = target?.closest<HTMLElement>(
      "[data-history-delete-tag]",
    );
    if (deleteTagButton) {
      void deleteHistoryTagFromManager(
        deleteTagButton.dataset.historyDeleteTag || "",
      );
      return true;
    }
    if (target?.closest("[data-history-favorite-filter]")) {
      applyHistoryOrganizationFilterChange({
        ...historyOrganizationFilters,
        favorite: !historyOrganizationFilters.favorite,
      });
      return true;
    }
    if (target?.closest("[data-history-untagged-filter]")) {
      applyHistoryOrganizationFilterChange(
        withHistoryUntaggedFilter(
          historyOrganizationFilters,
          !historyOrganizationFilters.untagged,
        ),
      );
      return true;
    }
    const tagFilterButton = target?.closest<HTMLElement>(
      "[data-history-tag-filter]",
    );
    if (tagFilterButton) {
      const tagId =
        tagFilterButton.dataset.historyTagFilter || "";
      applyHistoryOrganizationFilterChange(
        withHistoryTagFilter(
          historyOrganizationFilters,
          tagId,
          !historyOrganizationFilters.tagIds.includes(tagId),
        ),
      );
      return true;
    }
    for (const key of HISTORY_FILTER_QUERY_KEYS) {
      const attr = historyFilterAttribute(key);
      const button = target?.closest<HTMLElement>(`[data-history-${attr}]`);
      if (button) {
        applyFilter(key, button.getAttribute(`data-history-${attr}`) || "");
        return true;
      }
    }
    return false;
  }

  return {
    currentHistoryBackupFilters,
    renderHistoryActiveFilters,
    syncStateFromUrl,
    updateHistoryUrl,
    saveCurrentHistoryLocation,
    loadSummary,
    renderHistoryOrganizationFilters,
    renderHistoryTagManager,
    historyTagCreateErrorMessage,
    syncArchiveButtons,
    historyPageQueryInput,
    queryParams,
    syncHistoryViewMode,
    setHistoryViewMode,
    bind,
    handleClick,
    snapshot: () => ({ ...historyState }),
    organization: () => ({ ...historyOrganizationFilters, tagIds: [...historyOrganizationFilters.tagIds] }),
    tags: () => historyTags.map(tag => ({ ...tag })),
    supported: () => historyOrganizationApiSupported,
    markUnsupported() { historyOrganizationApiSupported = false; },
    dispose() { lifetime.abort(); window.clearTimeout(searchTimer); },
  };
}

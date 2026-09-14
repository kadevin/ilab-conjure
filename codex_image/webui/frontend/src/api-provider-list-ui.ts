export const API_PROVIDER_SEARCH_THRESHOLD = 10;

function providerChoiceGrid(): HTMLElement | null {
  return document.querySelector<HTMLElement>(".api-provider-choice-grid");
}

function providerSearchField(): HTMLElement | null {
  return document.querySelector<HTMLElement>("#apiProviderSearchField");
}

function providerSearchInput(): HTMLInputElement | null {
  return document.querySelector<HTMLInputElement>("#apiProviderSearch");
}

export function updateApiProviderListPresentation(providerCount: number, sorting: boolean): string {
  const longList = providerCount > API_PROVIDER_SEARCH_THRESHOLD;
  const searchVisible = longList && !sorting;
  providerChoiceGrid()?.classList.toggle("is-long-list", longList);
  providerSearchField()?.classList.toggle("hidden", !searchVisible);
  const input = providerSearchInput();
  if (!input) return "";
  if (!searchVisible && input.value) input.value = "";
  return searchVisible ? input.value.trim().toLocaleLowerCase() : "";
}

export function apiProviderMatchesSearch(provider: any, query: string): boolean {
  if (!query) return true;
  return [provider?.name, provider?.id]
    .some((value) => String(value || "").toLocaleLowerCase().includes(query));
}

export function scrollActiveApiProviderCardIntoView(providerId: string, align: "center" | "nearest" = "center"): void {
  window.requestAnimationFrame(() => {
    const grid = providerChoiceGrid();
    const panel = grid?.closest<HTMLElement>(".system-settings-section");
    if (!grid || !panel || panel.clientHeight === 0) return;
    const escapedId = CSS.escape(providerId);
    const card = grid.querySelector<HTMLElement>(`.api-provider-choice[data-api-provider-id="${escapedId}"]`);
    if (!card) return;
    const panelRect = panel.getBoundingClientRect();
    const cardRect = card.getBoundingClientRect();
    const cardTop = panel.scrollTop + cardRect.top - panelRect.top;
    const targetTop = align === "center"
      ? cardTop - Math.max(0, (panel.clientHeight - card.offsetHeight) / 2)
      : Math.min(cardTop, Math.max(panel.scrollTop, cardTop + card.offsetHeight - panel.clientHeight));
    panel.scrollTo({ top: Math.max(0, targetTop), behavior: "auto" });
  });
}

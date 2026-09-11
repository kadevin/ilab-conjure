type HistoryMobileFiltersOptions = {
  page: HTMLElement | null;
  sidebar: HTMLElement | null;
  trigger: HTMLButtonElement | null;
  backdrop: HTMLButtonElement | null;
};

export function initializeHistoryMobileFilters({
  page,
  sidebar,
  trigger,
  backdrop,
}: HistoryMobileFiltersOptions): void {
  if (!page || !sidebar || !trigger || !backdrop) return;

  const mobileQuery = window.matchMedia("(max-width: 760px), (max-width: 950px) and (max-height: 500px) and (pointer: coarse)");

  const sync = () => {
    const open = mobileQuery.matches && page.classList.contains("history-filters-open");
    trigger.setAttribute("aria-expanded", String(open));
    backdrop.hidden = !open;
    sidebar.toggleAttribute("inert", mobileQuery.matches && !open);
    if (mobileQuery.matches) {
      sidebar.setAttribute("aria-hidden", String(!open));
    } else {
      page.classList.remove("history-filters-open");
      sidebar.removeAttribute("aria-hidden");
    }
  };

  const setOpen = (open: boolean, restoreFocus = false) => {
    page.classList.toggle("history-filters-open", mobileQuery.matches && open);
    sync();
    if (restoreFocus) trigger.focus({ preventScroll: true });
  };

  trigger.addEventListener("click", () => {
    setOpen(!page.classList.contains("history-filters-open"));
  });
  backdrop.addEventListener("click", () => setOpen(false, true));
  sidebar.querySelector(".history-filters-close")?.addEventListener("click", () => setOpen(false, true));
  window.addEventListener("keydown", (event) => {
    if (event.key !== "Escape" || !page.classList.contains("history-filters-open")) return;
    event.preventDefault();
    event.stopImmediatePropagation();
    setOpen(false, true);
  });
  mobileQuery.addEventListener("change", sync);
  sync();
}

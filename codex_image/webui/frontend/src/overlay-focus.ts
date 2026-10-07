/** Shared keyboard lifecycle for the existing modal and side-sheet components. */
const layerSelector = ".modal-overlay, .resource-sheet, .confirm-popover, .history-lightbox, .history-export-picker, .history-tag-picker, .history-organize-picker, .task-context-menu, .mobile-sheet, #compactTaskDrawer, #historyDetail";
const focusSelector = 'button:not(:disabled), a[href], input:not(:disabled), select:not(:disabled), textarea:not(:disabled), [tabindex]:not([tabindex="-1"]), [contenteditable="true"]';
export function initOverlayFocus(): void {
  const stack: HTMLElement[] = [];
  let previousFocus = document.activeElement as HTMLElement;
  let syncing = false;
  const triggers = new WeakMap<HTMLElement, HTMLElement>();
  const narrowHistory = window.matchMedia("(max-width: 1100px)");
  const historyBackground = new Map<HTMLElement, boolean>();
  const visible = (element: HTMLElement) => element.id === "historyDetail"
    ? narrowHistory.matches && Boolean(element.closest(".history-detail-open"))
    : !element.classList.contains("hidden") && !element.hidden
    && (!element.matches(".resource-sheet") || element.classList.contains("open"));
  const ownedPopovers = (root: HTMLElement) => Array.from(root.querySelectorAll<HTMLElement>('[aria-controls][aria-expanded="true"]'))
    .flatMap(trigger => (trigger.getAttribute("aria-controls") || "").split(/\s+/).map(id => document.getElementById(id)))
    .filter((popover): popover is HTMLElement => Boolean(popover && !root.contains(popover) && visible(popover) && popover.getClientRects().length));
  const containsFocus = (root: HTMLElement, target: Node | null) => root.contains(target) || ownedPopovers(root).some(popover => popover.contains(target));
  const focusables = (root: HTMLElement) => [root, ...ownedPopovers(root)].flatMap(layer => Array.from(layer.querySelectorAll<HTMLElement>(focusSelector)))
    .filter(item => !item.closest('[inert], [hidden], .hidden, [aria-hidden="true"]') && item.getClientRects().length > 0);
  const focusFirst = (root: HTMLElement) => { root.tabIndex = -1; (focusables(root)[0] || root).focus({ preventScroll: true }); };
  const sync = () => {
    if (syncing) return;
    syncing = true;
    document.querySelectorAll<HTMLElement>(layerSelector).forEach(layer => {
      const open = visible(layer);
      if (layer.id === "historyDetail" && !narrowHistory.matches) {
        layer.inert = false;
        layer.removeAttribute("role");
        layer.removeAttribute("aria-modal");
        return;
      }
      layer.inert = !open;
      if (open && !stack.includes(layer)) {
        if (document.activeElement instanceof HTMLElement) triggers.set(layer, layer.contains(document.activeElement) ? previousFocus : document.activeElement);
        stack.push(layer);
        if (!layer.matches(".task-context-menu")) layer.setAttribute("aria-modal", "true");
        if (!layer.hasAttribute("role")) layer.setAttribute("role", "dialog");
        if (!layer.contains(document.activeElement)) focusFirst(layer);
      }
    });
    const topVisible = [...stack].reverse().find(layer => layer.isConnected && visible(layer));
    document.querySelectorAll<HTMLElement>(".layout-container, .history-page").forEach(root => { root.inert = Boolean(topVisible && !root.contains(topVisible)); });
    const history = document.getElementById("historyDetail");
    if (history && visible(history)) {
      Array.from(history.parentElement?.children || []).forEach(sibling => {
        if (!(sibling instanceof HTMLElement) || sibling === history) return;
        if (!historyBackground.has(sibling)) {
          // Responsive drawers own their existing inert state; do not restore a
          // stale mobile value after their desktop breakpoint has changed.
          if (sibling.inert) return;
          historyBackground.set(sibling, false);
        }
        sibling.inert = true;
      });
      const heading = history.querySelector<HTMLElement>(".history-detail-title");
      if (heading) {
        heading.id = "historyDetailHeading";
        history.setAttribute("aria-labelledby", heading.id);
      }
    } else {
      historyBackground.forEach((inert, sibling) => { sibling.inert = inert; });
      historyBackground.clear();
    }
    for (let index = stack.length - 1; index >= 0; index--) {
      const layer = stack[index]!;
      if (layer.isConnected && visible(layer)) continue;
      const wasTop = index === stack.length - 1;
      stack.splice(index, 1);
      if (wasTop) {
        const trigger = triggers.get(layer);
        if (trigger?.isConnected && !trigger.closest('[inert], .hidden, [hidden]')) trigger.focus({ preventScroll: true });
        else if (stack.length) focusFirst(stack[stack.length - 1]!);
      }
    }
    // Async detail rendering may replace the focused loading-shell control.
    if (topVisible?.id === "historyDetail" && !containsFocus(topVisible, document.activeElement)) focusFirst(topVisible);
    syncing = false;
  };
  new MutationObserver(sync).observe(document.body, { childList: true, subtree: true, attributes: true, attributeFilter: ["class", "hidden"] });
  narrowHistory.addEventListener("change", sync);
  sync();
  document.addEventListener("focusin", event => {
    sync();
    const top = stack[stack.length - 1];
    if (top && visible(top) && !containsFocus(top, event.target as Node)) focusFirst(top);
    previousFocus = document.activeElement as HTMLElement;
  });
  document.addEventListener("keydown", event => {
    const top = stack[stack.length - 1];
    if (!top || !visible(top)) return;
    if (event.key === "Tab") {
      const items = focusables(top);
      const current = items.indexOf(document.activeElement as HTMLElement);
      if (!items.length || (event.shiftKey ? current <= 0 : current === items.length - 1 || current < 0)) {
        event.preventDefault(); (items[event.shiftKey ? items.length - 1 : 0] || top).focus();
      }
    }
    if (event.key === "Escape") {
      // A local suggestion or nested editor gets the first chance to consume Escape.
      const local = top.querySelector<HTMLElement>('.mention-suggest:not(.hidden), .prompt-snippet-popover:not(.hidden), .themed-select-menu:not(.hidden), #taskFilterPopover:not([hidden])');
      if (local || ownedPopovers(top).length) return;
      const close = Array.from(top.querySelectorAll<HTMLButtonElement>('[data-confirm-popover-cancel], .drawer-close-button, [id$="Close"], [data-compact-task-close], [data-history-lightbox-close]')).find(button => button.getClientRects().length && !button.closest('.hidden, [hidden], [inert]'));
      if (close) { event.preventDefault(); event.stopImmediatePropagation(); close.click(); }
    }
  }, true);
}

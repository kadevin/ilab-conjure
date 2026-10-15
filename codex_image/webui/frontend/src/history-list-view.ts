import { escapeHtml } from "./history-presentation";
import { historyTaskCards, type HistoryScrollAnchor } from "./history-window";

/** DOM operations only; the list controller owns cursors and the commit/anchor transaction. */
export function createHistoryListView(taskList: HTMLElement | null, sentinel: HTMLElement | null) {
  const els = { taskList, sentinel };
  function historyTaskCardElement(taskId: string): HTMLElement | null {
    if (!taskId || !els.taskList) return null;
    return historyTaskCards(els.taskList).find((card) => card.dataset.historyTaskCardId === taskId) || null;
  }

  function setLoadMoreState(label: string, options: { hidden?: boolean; busy?: boolean } = {}): void {
    if (!els.sentinel) return;
    els.sentinel.textContent = label;
    els.sentinel.hidden = Boolean(options.hidden);
    els.sentinel.toggleAttribute("aria-busy", Boolean(options.busy));
  }

  function captureHistoryScrollAnchorSkipping(taskIds: Set<string>): HistoryScrollAnchor {
    if (!els.taskList) return null;
    const rootTop = els.taskList.getBoundingClientRect().top;
    for (const card of historyTaskCards(els.taskList)) {
      const taskId = String(card.dataset.historyTaskCardId || "");
      if (!taskId || taskIds.has(taskId)) continue;
      const rect = card.getBoundingClientRect();
      if (rect.bottom < rootTop) continue;
      return { taskId, offset: rect.top - rootTop };
    }
    return null;
  }

  function renderTaskListMessage(className: string, message: string): void {
    if (!els.taskList) return;
    els.taskList.innerHTML = `<div class="${className}">${escapeHtml(message)}</div>`;
  }

  function captureFocus(): { taskId: string; selector: string } | null {
    const active = document.activeElement;
    if (!active || !els.taskList?.contains(active)) return null;
    const taskId = active.closest<HTMLElement>("[data-history-task-card-id]")?.dataset.historyTaskCardId;
    const selector = ["[data-history-task-id]", "[data-history-favorite-task]"].find(value => active.matches(value));
    return taskId && selector ? { taskId, selector } : null;
  }

  function restoreFocus(focus: ReturnType<typeof captureFocus>): void {
    if (focus) historyTaskCardElement(focus.taskId)?.querySelector<HTMLElement>(focus.selector)?.focus({ preventScroll: true });
  }

  function replaceCard(card: HTMLElement, html: string): void {
    const focusSelector = card.contains(document.activeElement)
      ? ["[data-history-task-id]", "[data-history-favorite-task]"].find(selector => document.activeElement?.matches(selector))
      : undefined;
    const template = document.createElement("template");
    template.innerHTML = html.trim();
    const replacement = template.content.firstElementChild;
    if (replacement) {
      card.replaceWith(replacement);
      if (focusSelector) replacement.querySelector<HTMLElement>(focusSelector)?.focus({ preventScroll: true });
    }
  }
  return { historyTaskCardElement, setLoadMoreState, captureHistoryScrollAnchorSkipping, renderTaskListMessage, replaceCard, captureFocus, restoreFocus };
}

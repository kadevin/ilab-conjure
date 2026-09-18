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

  function replaceCard(card: HTMLElement, html: string): void {
    const template = document.createElement("template");
    template.innerHTML = html.trim();
    const replacement = template.content.firstElementChild;
    if (replacement) card.replaceWith(replacement);
  }
  return { historyTaskCardElement, setLoadMoreState, captureHistoryScrollAnchorSkipping, renderTaskListMessage, replaceCard };
}

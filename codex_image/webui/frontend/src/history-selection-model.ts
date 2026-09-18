export type HistorySelectionState = {
  selectedTaskIds: ReadonlySet<string>;
  selectedTaskId: string;
  selectionAnchorTaskId: string;
  selectionMode: boolean;
};

export type HistorySelectionAction =
  | { type: "replace"; ids: readonly string[]; anchor: string; primary: string }
  | { type: "toggle"; id: string; anchor: boolean }
  | { type: "drop"; id: string; clearAnchor?: boolean }
  | { type: "location"; id: string }
  | { type: "detail"; id: string }
  | { type: "failed"; ids: readonly string[] }
  | { type: "context-delete"; ids: readonly string[] }
  | { type: "reset" }
  | { type: "reload" }
  | { type: "enter-touch" };

export function emptyHistorySelection(): HistorySelectionState {
  return { selectedTaskIds: new Set(), selectedTaskId: "", selectionAnchorTaskId: "", selectionMode: false };
}

/** Selection is independent of the mounted page window. */
export function reduceHistorySelection(state: HistorySelectionState, action: HistorySelectionAction): HistorySelectionState {
  if (action.type === "reset") return emptyHistorySelection();
  if (action.type === "enter-touch") return { ...state, selectionMode: true };
  if (action.type === "location" || action.type === "reload") {
    const id = action.type === "location" ? action.id : state.selectedTaskId;
    return { selectedTaskIds: new Set(id ? [id] : []), selectedTaskId: id, selectionAnchorTaskId: id, selectionMode: false };
  }
  if (action.type === "detail") {
    if (state.selectedTaskIds.size === 1 && state.selectedTaskIds.has(action.id)) {
      return { ...state, selectedTaskId: action.id };
    }
    return { selectedTaskIds: new Set([action.id]), selectedTaskId: action.id, selectionAnchorTaskId: action.id, selectionMode: false };
  }
  if (action.type === "context-delete") return { ...state, selectedTaskIds: new Set(action.ids) };
  if (action.type === "failed") {
    return { selectedTaskIds: new Set(action.ids), selectedTaskId: action.ids[0] || "", selectionAnchorTaskId: action.ids[0] || "", selectionMode: action.ids.length ? state.selectionMode : false };
  }
  if (action.type === "replace") {
    const ids = new Set(action.ids.filter(Boolean));
    const first = [...ids][0] || "";
    return { selectedTaskIds: ids, selectedTaskId: ids.has(action.primary) ? action.primary : first, selectionAnchorTaskId: ids.has(action.anchor) ? action.anchor : first, selectionMode: ids.size ? state.selectionMode : false };
  }
  const ids = new Set(state.selectedTaskIds);
  if (action.type === "drop") {
    ids.delete(action.id);
    return { ...state, selectedTaskIds: ids, selectionAnchorTaskId: action.clearAnchor && state.selectionAnchorTaskId === action.id ? "" : state.selectionAnchorTaskId };
  }
  if (ids.has(action.id)) ids.delete(action.id); else ids.add(action.id);
  return { ...state, selectedTaskIds: ids, selectedTaskId: ids.has(action.id) ? action.id : [...ids][0] || "", selectionAnchorTaskId: action.anchor ? action.id : state.selectionAnchorTaskId };
}

export function createHistorySelectionModel() {
  let state = emptyHistorySelection();
  return {
    snapshot: (): Readonly<HistorySelectionState> => ({ ...state, selectedTaskIds: new Set(state.selectedTaskIds) }),
    dispatch(action: HistorySelectionAction): void { state = reduceHistorySelection(state, action); },
  };
}

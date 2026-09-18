/** Owns undo/redo ordering; canvas capture and restoration stay with the scene. */
export function createImageEditorHistory<T>(options: {
  capture: () => T | null;
  restore: (snapshot: T | null) => void;
  changed: () => void;
  resources?: (snapshot: T) => HTMLCanvasElement[];
  byteBudget?: number;
}) {
  const IMAGE_EDITOR_HISTORY_LIMIT = 30;
  let history: T[] = [];
  let historyIndex = -1;
  const resources = new Map<HTMLCanvasElement, number>();
  let retainedBytes = 0;
  const byteBudget = options.byteBudget ?? 512 * 1024 * 1024;

  function retain(snapshot: T) {
    for (const canvas of new Set(options.resources?.(snapshot) || [])) {
      const count = resources.get(canvas) || 0;
      if (!count) retainedBytes += canvas.width * canvas.height * 4;
      resources.set(canvas, count + 1);
    }
  }

  function release(snapshot: T) {
    for (const canvas of new Set(options.resources?.(snapshot) || [])) {
      const count = (resources.get(canvas) || 1) - 1;
      if (count) resources.set(canvas, count);
      else {
        retainedBytes -= canvas.width * canvas.height * 4;
        resources.delete(canvas);
        canvas.width = canvas.height = 0;
      }
    }
  }

  function pushImageEditorHistory(): void {
    const snapshot = options.capture();
    if (!snapshot) return;
    retain(snapshot);
    history.splice(historyIndex + 1).forEach(release);
    history.push(snapshot);
    historyIndex = history.length - 1;
    // Keep the current state and one undo even when a single scene exceeds the
    // budget. Otherwise bound retained unique pixels, not repeated references.
    while (history.length > IMAGE_EDITOR_HISTORY_LIMIT || (retainedBytes > byteBudget && history.length > 2)) {
      release(history.shift()!);
      historyIndex -= 1;
    }
    options.changed();
  }

  function undoImageEdit(): void {
    if (historyIndex <= 0) return;
    historyIndex -= 1;
    options.restore(history[historyIndex] || null);
  }

  function redoImageEdit(): void {
    if (historyIndex >= history.length - 1) return;
    historyIndex += 1;
    options.restore(history[historyIndex] || null);
  }

  function reset(): void {
    history.forEach(release);
    history = [];
    historyIndex = -1;
  }

  return {
    pushImageEditorHistory, undoImageEdit, redoImageEdit, reset,
    canUndo: () => historyIndex > 0,
    canRedo: () => historyIndex >= 0 && historyIndex < history.length - 1,
    retainedBytes: () => retainedBytes,
  };
}

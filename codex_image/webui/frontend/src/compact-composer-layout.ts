/** Move the existing metadata controls so their state and handlers stay intact. */
export function initCompactComposerLayout(onDensityChange: () => void): void {
  const workspace = document.querySelector<HTMLElement>(".main-wrapper");
  const controls = document.querySelector<HTMLElement>(".controls-col");
  const summarySlot = document.getElementById("compactExecutionSummary");
  const footer = document.getElementById("compactPromptMeta");
  const summary = document.getElementById("executionSummary");
  const count = document.getElementById("charCount");
  const restore = document.getElementById("restoreComposerDraft");
  if (!workspace || !controls || !summarySlot || !footer || !summary || !count || !restore) return;

  const origins = [summary, count, restore].map(element => {
    const marker = document.createComment("compact-composer-origin");
    element.before(marker);
    return { element, marker };
  });
  let compact = false;
  const isCompact = () => getComputedStyle(controls).getPropertyValue("--compact-composer").trim() === "1";
  let restoreLostFocusDuringResize = false;
  restore.addEventListener("blur", () => {
    // A media query can hide the old slot before ResizeObserver moves its button.
    restoreLostFocusDuringResize = isCompact() !== compact;
  });
  const sync = () => {
    const focused = document.activeElement;
    // CSS owns both viewport density and the remaining workspace width.
    const next = isCompact();
    if (next === compact) return;
    const movingFocus = focused instanceof HTMLElement && origins.some(({ element }) => element.contains(focused));
    const restoreFocus = restoreLostFocusDuringResize && focused === document.body;
    restoreLostFocusDuringResize = false;
    compact = next;
    if (compact) {
      summarySlot.append(summary);
      footer.append(count, restore);
    } else {
      origins.forEach(({ element, marker }) => marker.after(element));
    }
    controls.toggleAttribute("data-compact-composer", compact);
    onDensityChange();
    if (movingFocus) focused.focus({ preventScroll: true });
    else if (restoreFocus) restore.focus({ preventScroll: true });
  };
  let pending = 0;
  const schedule = () => {
    cancelAnimationFrame(pending);
    pending = requestAnimationFrame(sync);
  };
  new ResizeObserver(schedule).observe(workspace);
  window.addEventListener("resize", schedule);
  window.matchMedia("(pointer: fine)").addEventListener("change", schedule);
  sync();
}

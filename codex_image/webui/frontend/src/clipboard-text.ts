import { createMobileSheet } from "./mobile-shell";
import { translate } from "./i18n";

let manualSheet: ReturnType<typeof createMobileSheet> | null = null;

/** LAN HTTP and denied clipboard permissions still leave a usable copy path. */
export async function copyTextToClipboard(text: string): Promise<boolean> {
  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(text);
      return true;
    }
  } catch { /* Continue with a selection based copy. */ }
  const field = document.createElement("textarea");
  field.value = text;
  field.readOnly = true;
  field.style.cssText = "position:fixed;top:0;left:0;opacity:0;font-size:16px";
  const previous = document.activeElement as HTMLElement | null;
  (previous?.closest('[role="dialog"]') || document.body).append(field);
  field.select();
  let copied = false;
  try { copied = Boolean(document.execCommand?.("copy")); } catch { /* Manual fallback below. */ }
  field.remove(); previous?.focus({ preventScroll: true });
  if (copied) return true;
  manualSheet ||= createMobileSheet("manualClipboard", "mobile.manualCopy");
  const hint = document.createElement("p");
  hint.textContent = translate("mobile.copyHint");
  const selectable = document.createElement("textarea");
  selectable.readOnly = true; selectable.value = text;
  selectable.className = "control manual-copy-text";
  selectable.setAttribute("aria-label", translate("mobile.manualCopy"));
  manualSheet.content.replaceChildren(hint, selectable);
  manualSheet.open(previous || undefined);
  requestAnimationFrame(() => { selectable.focus(); selectable.select(); });
  return false;
}

import { LOCALE_CHANGE_EVENT, translate } from "./i18n";

export const MOBILE_WORKSPACE_QUERY = "(max-width: 600px), (max-width: 950px) and (max-height: 500px) and (pointer: coarse)";

export function mobileKeyboardInset(mobile: boolean, layoutHeight: number, viewport: { height: number; offsetTop: number; scale: number } | null): number {
  if (!mobile || !viewport || Math.abs(viewport.scale - 1) > 0.05 || layoutHeight - viewport.height <= 120) return 0;
  return Math.max(0, layoutHeight - viewport.height - viewport.offsetTop);
}

export function createMobileSheet(id: string, titleKey: string) {
  const root = document.createElement("div");
  root.id = id;
  root.className = "mobile-sheet hidden";
  root.setAttribute("role", "dialog");
  root.setAttribute("aria-modal", "true");
  const frame = document.createElement("section");
  frame.className = "mobile-sheet-frame";
  const header = document.createElement("header");
  header.className = "mobile-sheet-heading";
  const title = document.createElement("strong");
  title.id = `${id}Title`;
  root.setAttribute("aria-labelledby", title.id);
  const closeButton = document.createElement("button");
  closeButton.type = "button";
  closeButton.className = "ghost-button drawer-close-button";
  const content = document.createElement("div");
  content.className = "mobile-sheet-content";
  const label = () => {
    title.textContent = translate(titleKey);
    closeButton.textContent = translate("action.close");
  };
  label();
  document.addEventListener(LOCALE_CHANGE_EVENT, label);
  header.append(title, closeButton);
  frame.append(header, content);
  root.append(frame);
  document.body.append(root);
  let trigger: HTMLElement | null = null;
  const close = () => {
    root.classList.add("hidden");
    trigger?.setAttribute("aria-expanded", "false");
  };
  const open = (source?: HTMLElement) => {
    trigger = source || null;
    root.classList.remove("hidden");
    trigger?.setAttribute("aria-expanded", "true");
  };
  closeButton.addEventListener("click", close);
  root.addEventListener("click", event => { if (event.target === root) close(); });
  return { root, content, open, close };
}

/** Move the existing controls so their listeners and selected values stay intact. */
export function initMobileShell(): void {
  const nav = document.querySelector<HTMLElement>(".nav-actions");
  if (!nav) return;
  const query = window.matchMedia(MOBILE_WORKSPACE_QUERY);
  const sheet = createMobileSheet("mobileMore", "mobile.more");
  const more = document.createElement("button");
  more.type = "button";
  more.className = "ghost-button mobile-more-button";
  more.textContent = "···";
  more.setAttribute("aria-controls", sheet.root.id);
  more.setAttribute("aria-expanded", "false");
  const label = () => more.setAttribute("aria-label", translate("mobile.more"));
  label(); document.addEventListener(LOCALE_CHANGE_EVENT, label);
  nav.append(more);
  more.addEventListener("click", () => sheet.open(more));
  const origins = new Map<HTMLElement, Comment>();
  const move = (id: string, target: HTMLElement) => {
    const node = document.getElementById(id);
    if (!node) return;
    const marker = document.createComment(`mobile-${id}`);
    node.before(marker); origins.set(node, marker); target.append(node);
  };
  const sync = () => {
    sheet.close();
    origins.forEach((marker, node) => marker.replaceWith(node)); origins.clear();
    document.body.classList.toggle("mobile-ui", query.matches);
    if (!query.matches) return;
    move("compactTasksButton", nav);
    move("newTaskButton", nav);
    ["historyToolbarUtilities", "modelFamilyOptions", "queueButton", "taskNotificationButton", "taskNotificationCenter", "generationProviderSettingsButton", "themeSwitcher", "githubLink"].forEach(id => move(id, sheet.content));
  };
  // Close before opening a different overlay; theme/family and notifications stay usable here.
  sheet.content.addEventListener("click", event => {
    if ((event.target as Element).closest("#generationProviderSettingsButton, #queueButton, #historyManagementButton, #historyRefreshButton")) sheet.close();
  }, true);
  query.addEventListener("change", sync); sync();

  let frame = 0;
  const updateViewport = () => {
    cancelAnimationFrame(frame);
    frame = requestAnimationFrame(() => {
      const viewport = window.visualViewport;
      const bottom = mobileKeyboardInset(query.matches, window.innerHeight, viewport);
      const keyboard = bottom > 0;
      document.body.classList.toggle("mobile-keyboard-open", keyboard);
      document.documentElement.style.setProperty("--mobile-keyboard-inset", `${bottom}px`);
      document.documentElement.style.setProperty("--mobile-visible-height", keyboard && viewport ? `${viewport.height}px` : "100dvh");
    });
  };
  window.visualViewport?.addEventListener("resize", updateViewport);
  window.visualViewport?.addEventListener("scroll", updateViewport);
  window.addEventListener("resize", updateViewport);
  updateViewport();
}

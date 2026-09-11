import { translate, LOCALE_CHANGE_EVENT } from "./i18n";
import { getLegacyBridge } from "./state";
export function initCompactWorkspace(): void {
  const sidebar = document.getElementById("sidebar");
  const trigger = document.getElementById("compactTasksButton");
  if (!sidebar || !trigger) return;
  const drawer = document.createElement("div");
  drawer.id = "compactTaskDrawer"; drawer.className = "compact-task-drawer hidden";
  drawer.setAttribute("aria-label", translate("ux.tasks"));
  const close = document.createElement("button");
  close.className = "ghost-button"; close.type = "button"; close.dataset.compactTaskClose = "";
  const label = () => { close.textContent = translate("action.close"); trigger.textContent = translate("ux.tasks"); };
  label(); document.addEventListener(LOCALE_CHANGE_EVENT, label);
  drawer.append(close); document.body.append(drawer);
  const origins = new Map<HTMLElement, Comment>();
  const hide = () => {
    const wasOpen = !drawer.classList.contains("hidden");
    origins.forEach((placeholder, element) => { placeholder.replaceWith(element); }); origins.clear();
    drawer.classList.add("hidden"); trigger.setAttribute("aria-expanded", "false");
    return wasOpen;
  };
  const open = () => {
    if (!window.matchMedia("(max-width: 1180px)").matches) return;
    if (!drawer.classList.contains("hidden")) return;
    sidebar.querySelectorAll<HTMLElement>(".sidebar-search, .task-history-shell, .sidebar-footer").forEach(element => {
      if (element.parentElement?.closest(".task-history-shell")) return;
      const placeholder = document.createComment("task-drawer-origin"); element.before(placeholder); origins.set(element, placeholder); drawer.append(element);
    });
    drawer.classList.remove("hidden"); trigger.setAttribute("aria-expanded", "true");
  };
  trigger.addEventListener("click", open); close.addEventListener("click", hide);
  window.matchMedia("(max-width: 1180px)").addEventListener("change", event => { if (!event.matches) hide(); });
  getLegacyBridge().methods.openCompactTasks = open;
  getLegacyBridge().methods.closeCompactTasks = hide;
  const preview = document.querySelector<HTMLElement>(".preview-panel");
  const prompt = document.querySelector<HTMLElement>(".prompt-panel");
  if (preview && prompt) {
    const jump = document.createElement("button");
    jump.type = "button"; jump.className = "ghost-button compact-preview-jump";
    const labelJump = () => { jump.textContent = translate("ux.viewPreview"); };
    labelJump(); document.addEventListener(LOCALE_CHANGE_EVENT, labelJump);
    preview.tabIndex = -1;
    jump.addEventListener("click", () => {
      preview.scrollIntoView({ block: "start" });
      preview.focus({ preventScroll: true });
    });
    prompt.after(jump);
  }
  // Empty references are optional: keep all upload and library capabilities one click away.
  const panel = document.querySelector<HTMLElement>(".image-panel");
  const toggle = document.getElementById("compactReferencesButton");
  const workspace = panel?.querySelector<HTMLElement>(".image-input-workspace");
  if (!panel || !toggle || !workspace) return;
  workspace.id = "referenceWorkspace";
  toggle.setAttribute("aria-controls", workspace.id);
  let expanded = false;
  const sync = () => {
    const { state } = getLegacyBridge();
    toggle.hidden = Boolean(state.images.length || (state.referenceFiles || []).length);
    const collapsed = window.matchMedia("(max-width: 600px), (max-height: 500px)").matches && !expanded && !state.images.length && !(state.referenceFiles || []).length;
    panel.classList.toggle("references-collapsed", collapsed);
    toggle.setAttribute("aria-expanded", String(!collapsed));
    toggle.textContent = translate(collapsed ? "ux.addReference" : "ux.collapseReference");
  };
  toggle.addEventListener("click", () => { expanded = !expanded; sync(); });
  new MutationObserver(sync).observe(document.getElementById("imageThumbItems")!, { childList: true });
  new MutationObserver(sync).observe(document.getElementById("referenceFileSelection")!, { childList: true });
  window.matchMedia("(max-width: 600px), (max-height: 500px)").addEventListener("change", sync); sync();
}

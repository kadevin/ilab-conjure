/** Radio behavior for both built-in and catalog-rendered output parameters. */
export function syncOutputRadioGroup(group: HTMLElement): HTMLButtonElement[] {
  const buttons = Array.from(group.querySelectorAll<HTMLButtonElement>(".radio-btn"));
  const enabled = buttons.filter(button => !button.disabled);
  const selected = enabled.find(button => button.classList.contains("active")) || enabled[0];
  group.setAttribute("role", "radiogroup");
  buttons.forEach(button => {
    button.setAttribute("role", "radio");
    button.setAttribute("aria-checked", String(button.classList.contains("active")));
    button.removeAttribute("aria-pressed");
    button.tabIndex = button === selected ? 0 : -1;
  });
  return enabled;
}

export function initOutputParameterKeyboard(): void {
  const root = document.getElementById("settingsGrid");
  if (!root) return;
  const sync = () => root.querySelectorAll<HTMLElement>(".radio-group").forEach(syncOutputRadioGroup);
  root.addEventListener("keydown", event => {
    const button = (event.target as Element).closest<HTMLButtonElement>(".radio-btn");
    const group = button?.closest<HTMLElement>(".radio-group");
    if (!button || !group || !root.contains(group)) return;
    const direction = ["ArrowRight", "ArrowDown"].includes(event.key) ? 1
      : ["ArrowLeft", "ArrowUp"].includes(event.key) ? -1 : 0;
    if (!direction) return;
    const buttons = syncOutputRadioGroup(group);
    if (!buttons.length) return;
    event.preventDefault();
    const next = buttons[(buttons.indexOf(button) + direction + buttons.length) % buttons.length]!;
    next.focus();
    next.click();
    syncOutputRadioGroup(group);
  });
  new MutationObserver(sync).observe(root, {
    subtree: true, childList: true, attributes: true, attributeFilter: ["class", "disabled"],
  });
  sync();
}

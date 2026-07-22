const DEFAULT_SELECT_IDS = ["languageSelect", "generationProviderSelect"] as const;

interface ThemedSelectInstance {
  id: number;
  select: HTMLSelectElement;
  host: HTMLDivElement;
  trigger: HTMLButtonElement;
  value: HTMLSpanElement;
  menu: HTMLDivElement;
  activeIndex: number;
  observer: MutationObserver;
  originalTabIndex: number;
  originalAriaHidden: string | null;
}

const instances = new WeakMap<HTMLSelectElement, ThemedSelectInstance>();
const openInstances = new Set<ThemedSelectInstance>();
let nextInstanceId = 1;
let documentPointerListenerBound = false;
let documentPositionListenersBound = false;

const MENU_EDGE_GUTTER = 12;
const MENU_GAP = 5;
const MENU_MAX_HEIGHT = 280;
const MENU_PREFERRED_BELOW_HEIGHT = 160;

function optionText(option: HTMLOptionElement | undefined): string {
  return option?.textContent?.trim() || option?.label || option?.value || "";
}

function appendOptionContent(target: HTMLElement, option: HTMLOptionElement | undefined): void {
  target.replaceChildren();
  const icon = option?.dataset.optionIcon?.trim();
  const kind = option?.dataset.optionIconKind === "image" ? "image" : "emoji";
  if (icon) {
    const iconElement = document.createElement("span");
    iconElement.className = `themed-select-option-icon ${kind}`;
    iconElement.setAttribute("aria-hidden", "true");
    if (kind === "image") {
      const image = document.createElement("img");
      image.src = icon;
      image.alt = "";
      image.decoding = "async";
      iconElement.append(image);
    } else {
      iconElement.textContent = icon;
    }
    target.append(iconElement);
  }
  const label = document.createElement("span");
  label.className = "themed-select-option-label";
  label.textContent = optionText(option);
  target.append(label);
}

function selectableOptionIndexes(instance: ThemedSelectInstance): number[] {
  return Array.from(instance.select.options)
    .map((option, index) => ({ option, index }))
    .filter(({ option }) => !option.disabled && !option.hidden)
    .map(({ index }) => index);
}

function nearestSelectableIndex(instance: ThemedSelectInstance, preferredIndex: number): number {
  const indexes = selectableOptionIndexes(instance);
  if (!indexes.length) return -1;
  return indexes.includes(preferredIndex) ? preferredIndex : indexes[0] ?? -1;
}

function moveSelectableIndex(instance: ThemedSelectInstance, direction: 1 | -1): number {
  const indexes = selectableOptionIndexes(instance);
  if (!indexes.length) return -1;
  const current = indexes.indexOf(nearestSelectableIndex(instance, instance.activeIndex));
  return indexes[(current + direction + indexes.length) % indexes.length] ?? -1;
}

function copyAriaAttributes(instance: ThemedSelectInstance): void {
  const attributes = ["aria-label", "aria-labelledby", "aria-describedby"] as const;
  attributes.forEach((attribute) => {
    const value = instance.select.getAttribute(attribute);
    if (value) instance.trigger.setAttribute(attribute, value);
    else instance.trigger.removeAttribute(attribute);
  });
}

function syncTrigger(instance: ThemedSelectInstance): void {
  const selected = instance.select.selectedOptions[0];
  appendOptionContent(instance.value, selected);
  instance.trigger.disabled = instance.select.disabled;
  instance.trigger.title = instance.select.title || optionText(selected);
  copyAriaAttributes(instance);
  if (instance.select.disabled) closeThemedSelect(instance);
}

function optionButtonId(instance: ThemedSelectInstance, index: number): string {
  return `themed-select-${instance.id}-option-${index}`;
}

function focusOption(instance: ThemedSelectInstance, index: number): void {
  const nextIndex = nearestSelectableIndex(instance, index);
  if (nextIndex < 0) return;
  instance.activeIndex = nextIndex;
  renderOptions(instance);
  instance.menu.querySelector<HTMLButtonElement>(`#${optionButtonId(instance, nextIndex)}`)?.focus();
}

function selectOption(instance: ThemedSelectInstance, index: number): void {
  const option = instance.select.options[index];
  if (!option || option.disabled) return;
  instance.select.selectedIndex = index;
  instance.select.dispatchEvent(new Event("input", { bubbles: true }));
  instance.select.dispatchEvent(new Event("change", { bubbles: true }));
  syncThemedSelect(instance.select);
  closeThemedSelect(instance, true);
}

function handleOptionKeydown(instance: ThemedSelectInstance, event: KeyboardEvent, index: number): void {
  if (event.key === "ArrowDown") {
    event.preventDefault();
    event.stopPropagation();
    focusOption(instance, moveSelectableIndex(instance, 1));
  } else if (event.key === "ArrowUp") {
    event.preventDefault();
    event.stopPropagation();
    focusOption(instance, moveSelectableIndex(instance, -1));
  } else if (event.key === "Home") {
    event.preventDefault();
    event.stopPropagation();
    focusOption(instance, selectableOptionIndexes(instance)[0] ?? -1);
  } else if (event.key === "End") {
    event.preventDefault();
    event.stopPropagation();
    const indexes = selectableOptionIndexes(instance);
    focusOption(instance, indexes[indexes.length - 1] ?? -1);
  } else if (event.key === "Enter" || event.key === " " || event.key === "Spacebar") {
    event.preventDefault();
    event.stopPropagation();
    selectOption(instance, index);
  } else if (event.key === "Escape") {
    event.preventDefault();
    event.stopPropagation();
    closeThemedSelect(instance, true);
  } else if (event.key === "Tab") {
    closeThemedSelect(instance);
  }
}

function renderOptions(instance: ThemedSelectInstance): void {
  const selectedIndex = instance.select.selectedIndex;
  const options = Array.from(instance.select.options);
  if (!options.length) {
    const empty = document.createElement("span");
    empty.className = "themed-select-empty";
    empty.textContent = "-";
    instance.menu.replaceChildren(empty);
    return;
  }

  const buttons = options.map((option, index) => {
    const button = document.createElement("button");
    button.id = optionButtonId(instance, index);
    button.type = "button";
    button.className = "themed-select-option";
    button.setAttribute("role", "option");
    button.setAttribute("aria-selected", index === selectedIndex ? "true" : "false");
    button.disabled = option.disabled;
    button.hidden = option.hidden;
    appendOptionContent(button, option);
    if (index === selectedIndex) button.classList.add("selected");
    if (index === instance.activeIndex) button.classList.add("active");
    button.addEventListener("click", () => selectOption(instance, index));
    button.addEventListener("keydown", (event) => handleOptionKeydown(instance, event, index));
    return button;
  });
  instance.menu.replaceChildren(...buttons);
}

function handleTriggerKeydown(instance: ThemedSelectInstance, event: KeyboardEvent): void {
  if (event.key === "Escape") {
    if (!openInstances.has(instance)) return;
    event.preventDefault();
    event.stopPropagation();
    closeThemedSelect(instance);
    return;
  }
  if (event.key !== "ArrowDown" && event.key !== "ArrowUp" && event.key !== "Enter" && event.key !== " " && event.key !== "Spacebar") {
    return;
  }
  event.preventDefault();
  event.stopPropagation();
  if (!openInstances.has(instance)) openThemedSelect(instance);
  const indexes = selectableOptionIndexes(instance);
  const initialIndex = event.key === "ArrowUp"
    ? indexes[indexes.length - 1] ?? -1
    : nearestSelectableIndex(instance, instance.select.selectedIndex);
  focusOption(instance, initialIndex);
}

function resetThemedSelectMenuPosition(instance: ThemedSelectInstance): void {
  instance.menu.classList.remove("is-portal", "opens-upward");
  ["top", "left", "width", "max-height"].forEach((property) => {
    instance.menu.style.removeProperty(property);
  });
}

function restoreThemedSelectMenu(instance: ThemedSelectInstance): void {
  resetThemedSelectMenuPosition(instance);
  if (instance.menu.parentElement !== instance.host) instance.host.append(instance.menu);
}

function positionThemedSelectMenu(instance: ThemedSelectInstance): void {
  const rect = instance.trigger.getBoundingClientRect();
  const viewportWidth = window.innerWidth;
  const viewportHeight = window.innerHeight;
  const availableBelow = Math.max(0, viewportHeight - rect.bottom - MENU_GAP - MENU_EDGE_GUTTER);
  const availableAbove = Math.max(0, rect.top - MENU_GAP - MENU_EDGE_GUTTER);
  const opensUpward = availableBelow < MENU_PREFERRED_BELOW_HEIGHT && availableAbove > availableBelow;
  const availableHeight = opensUpward ? availableAbove : availableBelow;
  const maxHeight = Math.max(80, Math.min(MENU_MAX_HEIGHT, availableHeight));
  const visibleHeight = Math.min(instance.menu.scrollHeight || maxHeight, maxHeight);
  const width = Math.min(rect.width, Math.max(0, viewportWidth - MENU_EDGE_GUTTER * 2));
  const maximumLeft = Math.max(MENU_EDGE_GUTTER, viewportWidth - MENU_EDGE_GUTTER - width);
  const left = Math.min(Math.max(MENU_EDGE_GUTTER, rect.left), maximumLeft);
  const top = opensUpward
    ? Math.max(MENU_EDGE_GUTTER, rect.top - MENU_GAP - visibleHeight)
    : rect.bottom + MENU_GAP;

  instance.menu.classList.toggle("opens-upward", opensUpward);
  instance.menu.style.top = `${top}px`;
  instance.menu.style.left = `${left}px`;
  instance.menu.style.width = `${width}px`;
  instance.menu.style.maxHeight = `${maxHeight}px`;
}

function positionOpenThemedSelectMenus(): void {
  openInstances.forEach((instance) => positionThemedSelectMenu(instance));
}

function closeThemedSelect(instance: ThemedSelectInstance, restoreFocus = false): void {
  if (!openInstances.delete(instance)) return;
  instance.menu.classList.add("hidden");
  restoreThemedSelectMenu(instance);
  instance.trigger.setAttribute("aria-expanded", "false");
  if (restoreFocus) instance.trigger.focus({ preventScroll: true });
}

function openThemedSelect(instance: ThemedSelectInstance): void {
  if (instance.trigger.disabled) return;
  openInstances.forEach((openInstance) => {
    if (openInstance !== instance) closeThemedSelect(openInstance);
  });
  instance.activeIndex = nearestSelectableIndex(instance, instance.select.selectedIndex);
  syncTrigger(instance);
  renderOptions(instance);
  document.body.append(instance.menu);
  instance.menu.classList.add("is-portal");
  instance.menu.classList.remove("hidden");
  positionThemedSelectMenu(instance);
  instance.trigger.setAttribute("aria-expanded", "true");
  openInstances.add(instance);
}

function bindDocumentPointerListener(): void {
  if (documentPointerListenerBound) return;
  documentPointerListenerBound = true;
  document.addEventListener("pointerdown", (event) => {
    openInstances.forEach((instance) => {
      const target = event.target as Node;
      if (!instance.host.contains(target) && !instance.menu.contains(target)) closeThemedSelect(instance);
    });
  });
}

function bindDocumentPositionListeners(): void {
  if (documentPositionListenersBound) return;
  documentPositionListenersBound = true;
  window.addEventListener("resize", positionOpenThemedSelectMenus);
  document.addEventListener("scroll", positionOpenThemedSelectMenus, true);
}

export function mountThemedSelect(select: HTMLSelectElement | null): void {
  if (!select || select.multiple || instances.has(select)) {
    if (select) syncThemedSelect(select);
    return;
  }
  const parent = select.parentElement;
  if (!parent) return;

  const host = document.createElement("div");
  host.className = "themed-select";
  host.dataset.themedSelect = "";
  const trigger = document.createElement("button");
  trigger.type = "button";
  trigger.className = "themed-select-trigger";
  trigger.setAttribute("aria-haspopup", "listbox");
  trigger.setAttribute("aria-expanded", "false");
  const value = document.createElement("span");
  value.className = "themed-select-value";
  const caret = document.createElement("span");
  caret.className = "themed-select-caret";
  caret.setAttribute("aria-hidden", "true");
  trigger.append(value, caret);
  const menu = document.createElement("div");
  menu.className = "themed-select-menu hidden";
  menu.setAttribute("role", "listbox");

  const id = nextInstanceId++;
  menu.id = `themed-select-${id}-options`;
  trigger.setAttribute("aria-controls", menu.id);
  parent.insertBefore(host, select);
  host.append(select, trigger, menu);
  const instance: ThemedSelectInstance = {
    id,
    select,
    host,
    trigger,
    value,
    menu,
    activeIndex: select.selectedIndex,
    observer: new MutationObserver(() => syncThemedSelect(select)),
    originalTabIndex: select.tabIndex,
    originalAriaHidden: select.getAttribute("aria-hidden"),
  };
  instances.set(select, instance);
  select.classList.add("themed-select-native");
  select.tabIndex = -1;
  select.setAttribute("aria-hidden", "true");
  select.addEventListener("change", () => syncThemedSelect(select));
  select.addEventListener("input", () => syncThemedSelect(select));
  trigger.addEventListener("click", () => {
    if (openInstances.has(instance)) closeThemedSelect(instance);
    else openThemedSelect(instance);
  });
  trigger.addEventListener("keydown", (event) => handleTriggerKeydown(instance, event));
  instance.observer.observe(select, {
    attributes: true,
    attributeFilter: ["aria-describedby", "aria-label", "aria-labelledby", "disabled", "title"],
    characterData: true,
    childList: true,
    subtree: true,
  });
  bindDocumentPointerListener();
  bindDocumentPositionListeners();
  syncThemedSelect(select);
}

export function syncThemedSelect(select: HTMLSelectElement | null): void {
  if (!select) return;
  const instance = instances.get(select);
  if (!instance) return;
  syncTrigger(instance);
  if (openInstances.has(instance)) renderOptions(instance);
}

export function destroyThemedSelects(container: ParentNode | null): void {
  if (!container) return;
  container.querySelectorAll<HTMLSelectElement>("select.themed-select-native").forEach((select) => {
    const instance = instances.get(select);
    if (!instance) return;
    closeThemedSelect(instance);
    restoreThemedSelectMenu(instance);
    instance.observer.disconnect();
    select.classList.remove("themed-select-native");
    select.tabIndex = instance.originalTabIndex;
    if (instance.originalAriaHidden === null) select.removeAttribute("aria-hidden");
    else select.setAttribute("aria-hidden", instance.originalAriaHidden);
    instance.menu.remove();
    instance.host.replaceWith(select);
    instances.delete(select);
  });
}

export function initThemedSelectFeature(): void {
  DEFAULT_SELECT_IDS.forEach((id) => {
    mountThemedSelect(document.getElementById(id) as HTMLSelectElement | null);
  });
}

/** Real application controls, synthetic fixture storage; never contacts a model provider. */
import { loadAcceptanceFrame, prepareFixtureOrigin } from "./browser_acceptance";
import { checkBackupBoundaries } from "./backup_boundaries.browser";
import { checkBackupNavigation } from "./backup_navigation.browser";
import { DICTIONARIES, LOCALES } from "../../codex_image/webui/frontend/src/i18n/dictionaries";

const frame = document.querySelector<HTMLIFrameElement>("#historyFrame")!;
const output = document.querySelector<HTMLElement>("#results")!;
const errors: string[] = [];
const failures: Array<{ name: string; detail?: unknown }> = [];
const measurements: unknown[] = [];
let assertions = 0;
const pause = (ms = 50) => new Promise(resolve => setTimeout(resolve, ms));
function check(name: string, condition: boolean, detail?: unknown) {
  assertions++;
  if (!condition) failures.push({ name, detail });
}
async function until(condition: () => boolean, description: string) {
  const end = Date.now() + 15000;
  while (!condition()) {
    if (Date.now() > end) throw new Error(`Timed out: ${description}`);
    await pause();
  }
}

async function run() {
  await prepareFixtureOrigin();
  localStorage.clear();
  if (new URLSearchParams(location.search).has("backup-navigation-only")) sessionStorage.clear();
  localStorage.setItem("codex-image-locale-preference", "zh-CN");
  if (new URLSearchParams(location.search).has("backup-boundaries-only")) return checkBackupBoundaries(frame, errors);
  await loadAcceptanceFrame(frame, "/qa-app", errors);
  const w = frame.contentWindow!, d = frame.contentDocument!;
  await until(() => !!w.__codexImageWebUI?.state.generationCatalog, "catalog ready");
  const { state, methods } = w.__codexImageWebUI;
  const find = <T extends HTMLElement = HTMLElement>(selector: string) => d.querySelector<T>(selector)!;
  const cards = () => [...d.querySelectorAll<HTMLDetailsElement>("details[data-binding-id]")];
  const input = (selector: string, value: string) => {
    const field = find<HTMLInputElement | HTMLSelectElement>(selector);
    field.value = value;
    field.dispatchEvent(new w.Event("input", { bubbles: true }));
    field.dispatchEvent(new w.Event("change", { bubbles: true }));
  };
  const resize = async (width: number, height: number) => {
    frame.style.width = `${width}px`; frame.style.height = `${height}px`;
    await pause(250);
  };
  if (new URLSearchParams(location.search).has("backup-navigation-only")) return checkBackupNavigation(frame, errors);
  if (new URLSearchParams(location.search).has("translations-only")) {
    find("#outputSettingsLockButton").click();
    methods.openApiSettingsModal!();
    find("#systemSettingsNetworkTab").click();
    await until(() => !find<HTMLInputElement>("#networkEgressFakeIpDnsFallback").disabled, "network settings ready");
    for (const locale of LOCALES) {
      w.__codexImageI18n.setLocale(locale);
      await pause();
      for (const theme of ["light", "dark"]) {
        find(`[data-theme-option="${theme}"]`).click();
        for (const [width, height] of [[1512, 699], [390, 844]]) {
          await resize(width, height);
          const name = `${locale} ${theme} ${width}`;
          for (const selector of ['#moderationGroup [data-i18n]', '#systemSettingsNetworkPanel [data-i18n]:not(#networkEgressCurrentRoute):not(#lanAccessStatus)']) {
            for (const element of d.querySelectorAll<HTMLElement>(selector)) {
              const key = element.dataset.i18n!;
              check(`${name}: ${key} uses the selected locale`, element.textContent?.trim() === DICTIONARIES[locale][key], {actual: element.textContent, expected: DICTIONARIES[locale][key]});
            }
          }
          check(`${name}: LAN status uses its loaded state and current language`, find('#lanAccessStatus').textContent === DICTIONARIES[locale]['lanAccess.localOnly']);
          check(`${name}: current network route is translated`, find('#networkEgressCurrentRoute').textContent === DICTIONARIES[locale]['networkEgress.currentRoute'].replace('{route}', DICTIONARIES[locale]['networkEgress.system']));
          const moderationDetail = [...d.querySelectorAll<HTMLElement>('.output-settings-summary-detail')].find(el => el.querySelector('.output-settings-summary-detail-label')?.textContent === DICTIONARIES[locale]['output.moderation']);
          check(`${name}: locked moderation value is translated`, moderationDetail?.querySelector('.output-settings-summary-detail-value')?.textContent === DICTIONARIES[locale]['ux.moderationAuto']);
          const panel = find('#systemSettingsNetworkPanel');
          check(`${name}: network content has no horizontal overflow`, panel.scrollWidth <= panel.clientWidth + 1);
        }
      }
    }
    w.__codexImageI18n.setLocale("zh-CN");
    find('#systemSettingsModalClose').click();
    check('settings close remains available', find('#systemSettingsModal').getAttribute('aria-hidden') === 'true');
    return {passed: failures.length === 0 && errors.length === 0, assertions, failures, errors};
  }
  const viewports = [[1920, 1080], [1366, 768], [1280, 600], [1024, 768], [390, 844], [360, 740]];
  if (new URLSearchParams(location.search).has("lan-only")) {
    const originalFetch = w.fetch.bind(w);
    let addresses = ["http://198.18.0.1:8787/", "http://192.168.1.10:8787/"];
    w.fetch = ((request: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof request === "string" ? request : request instanceof w.Request ? request.url : String(request);
      if (new URL(url, w.location.href).pathname === "/api/lan-access") {
        return Promise.resolve(new w.Response(JSON.stringify({ enabled: true, active: true,
          restart_required: false, host_override: false, addresses }), { headers: { "Content-Type": "application/json" } }));
      }
      return originalFetch(request, init);
    }) as typeof w.fetch;
    methods.openApiSettingsModal!();
    find("#systemSettingsNetworkTab").click();
    await until(() => !!find("#lanAccessAddresses input"), "LAN address ready");
    for (const theme of ["light", "dark"]) {
      find(`[data-theme-option="${theme}"]`).click();
      for (const [width, height] of [[1366, 768], [390, 844]]) {
        await resize(width, height);
        const container = find("#lanAccessAddresses"), fields = container.querySelectorAll<HTMLInputElement>("input");
        check(`${theme} ${width}: only actual LAN address is displayed`, fields.length === 1 && fields[0].value === "http://192.168.1.10:8787/");
        check(`${theme} ${width}: address row stays inside panel`, container.scrollWidth <= container.clientWidth);
        const copy = container.querySelector<HTMLButtonElement>("button")!;
        copy.focus({ preventScroll: true });
        check(`${theme} ${width}: copy remains keyboard accessible`, d.activeElement === copy && !copy.disabled);
      }
    }
    addresses = ["http://198.19.1.1:8787/"];
    await methods.refreshLanAccess!();
    check("virtual-only state does not offer an unusable address", !find("#lanAccessAddresses input") && !!find("#lanAccessAddresses p"));
    w.fetch = originalFetch;
    return { passed: failures.length === 0 && errors.length === 0, assertions, failures, errors, measurements };
  }
  const visibleScroll = (panel: HTMLElement) => [...panel.querySelectorAll<HTMLElement>(".system-settings-scroll")].find(item => item.getBoundingClientRect().height > 0)!;
  const checkFooter = async (name: string, panel: HTMLElement, selector: string) => {
    const footer = find(selector);
    const scroll = visibleScroll(panel);
    scroll.scrollTop = 0; await pause();
    const before = footer.getBoundingClientRect();
    const bounds = panel.getBoundingClientRect();
    check(`${name}: footer visible before scrolling`, before.top >= bounds.top && before.bottom <= bounds.bottom + 1);
    visibleScroll(panel).scrollTop = visibleScroll(panel).scrollHeight; await pause();
    const after = footer.getBoundingClientRect();
    check(`${name}: footer stays fixed during scroll`, Math.abs(before.top - after.top) <= 1);
    const buttons = [...footer.querySelectorAll<HTMLButtonElement>("button")].filter(button => button.getBoundingClientRect().height);
    const left = buttons[0].getBoundingClientRect(), right = buttons[buttons.length - 1].getBoundingClientRect();
    check(`${name}: actions centered as a group`, Math.abs((left.left + right.right) / 2 - (bounds.left + bounds.right) / 2) <= 2);
    const controlRight = Math.max(...[...panel.querySelectorAll<HTMLElement>(".control, .themed-select-trigger, .provider-binding-card")]
      .filter(control => control.getBoundingClientRect().width > 1).map(control => control.getBoundingClientRect().right));
    check(`${name}: controls clear the scrollbar`, controlRight <= bounds.right - 8);
    check(`${name}: no horizontal overflow`, scroll.scrollWidth <= scroll.clientWidth + 1);
    check(`${name}: scrollbar stops above footer`, scroll.getBoundingClientRect().bottom <= after.top);
    check(`${name}: parallel buttons share radius and height`, buttons.every(button =>
      w.getComputedStyle(button).borderRadius === w.getComputedStyle(buttons[0]).borderRadius
      && Math.abs(button.getBoundingClientRect().height - left.height) < 1));
  };
  await resize(1280, 720);
  methods.openApiSettingsModal!();
  await until(() => !!state.apiSettings?.providers?.length, "settings ready");
  check("only the last provider is protected from deletion", find<HTMLButtonElement>("#deleteApiProviderButton").disabled === (state.apiSettings.providers.length === 1));
  find("#addApiProviderButton").click();
  await until(() => cards().length === 1 && !find("#apiProviderEditor").classList.contains("hidden"), "new draft");
  input("#apiProviderName", "QA-settings");
  input("#apiKey", "qa-settings-synthetic-only");
  let card = cards()[0];
  check("single new binding expanded", card.open);
  let advanced = card.querySelector<HTMLDetailsElement>(".provider-binding-advanced")!;
  check("advanced defaults collapsed", !advanced.open);
  advanced.querySelector<HTMLElement>("summary")!.click();
  await pause();
  if (new URLSearchParams(location.search).has("editor-inspect")) {
    const extraBindings = new URLSearchParams(location.search).has("long-editor") ? 10 : 0;
    for (let index = 0; index < extraBindings; index++) find("#addProviderBindingButton").click();
    cards()[cards().length - 1].querySelector<HTMLDetailsElement>(".provider-binding-advanced")!.open = true;
    await resize(1512, 773);
    const scroll = find(".api-provider-editor-scroll"), modal = find("#systemSettingsModal");
    const panel = find(".system-settings-modal-panel"), footer = find(".api-provider-editor-actions");
    scroll.scrollTop = 0;
    await pause(400);
    const stats = {events:0, frames:0, mutations:0, modalTop:[Infinity,-Infinity], modalHeight:[Infinity,-Infinity],
      footerTop:[Infinity,-Infinity], outerScroll:[Infinity,-Infinity], innerScroll:[Infinity,-Infinity]};
    const sample = () => {
      const box=panel.getBoundingClientRect();
      for (const [range,value] of [[stats.modalTop,box.top],[stats.modalHeight,box.height],
        [stats.footerTop,footer.getBoundingClientRect().top],[stats.outerScroll,modal.scrollTop],[stats.innerScroll,scroll.scrollTop]] as const) {
        range[0]=Math.min(range[0],value); range[1]=Math.max(range[1],value);
      }
      stats.frames++;
      output.textContent=JSON.stringify(stats);
    };
    new MutationObserver(records => { stats.mutations+=records.length; }).observe(find("#apiProviderEditor"),{subtree:true,childList:true,attributes:true});
    let pending=0, remaining=0;
    const tick=()=>{sample();if(--remaining>0)pending=w.requestAnimationFrame(tick);else pending=0;};
    scroll.addEventListener("scroll",()=>{stats.events++;remaining=8;if(!pending)pending=w.requestAnimationFrame(tick);});
    sample();
    await new Promise<void>(()=>{});
  }
  await resize(1280, 600);
  const editorScroll = find(".api-provider-editor-scroll");
  editorScroll.scrollTop = 0; await pause();
  const modelTrigger = card.querySelector<HTMLButtonElement>("[data-binding-model] + .themed-select-trigger")!;
  modelTrigger.click();
  const modelMenu = find(`#${modelTrigger.getAttribute("aria-controls")}`);
  modelMenu.scrollTop = modelMenu.scrollHeight;
  await pause();
  check("scrolling model options preserves the open menu", modelTrigger.getAttribute("aria-expanded") === "true");
  const valueBeforeScroll = card.querySelector<HTMLSelectElement>("[data-binding-model]")!.value;
  editorScroll.scrollTop = editorScroll.scrollHeight; await pause();
  check("scrolling editor closes the detached menu", editorScroll.scrollTop > 0
    && modelTrigger.getAttribute("aria-expanded") === "false" && modelMenu.classList.contains("hidden"));
  check("scroll dismissal preserves the selected model", card.querySelector<HTMLSelectElement>("[data-binding-model]")!.value === valueBeforeScroll);
  modelTrigger.focus({ preventScroll: true });
  modelTrigger.dispatchEvent(new w.KeyboardEvent("keydown", { key: "ArrowDown", bubbles: true }));
  check("dismissed menu can reopen from the keyboard", modelTrigger.getAttribute("aria-expanded") === "true");
  editorScroll.scrollTop = 0; await pause();
  check("scroll dismissal returns option focus without jumping the editor", d.activeElement === modelTrigger
    && modelTrigger.getAttribute("aria-expanded") === "false" && editorScroll.scrollTop === 0);
  await resize(1280, 720);
  const compatibility = card.querySelector<HTMLSelectElement>("[data-binding-compatibility]")!;
  const nonDefault = [...compatibility.options].find(option => option.value !== "standard");
  check("compatibility retains the standard option", [...compatibility.options].some(option => option.value === "standard"));
  if (nonDefault) input("[data-binding-compatibility]", nonDefault.value);
  input("[data-binding-transparency]", "prompt");
  card.querySelector<HTMLInputElement>("[data-binding-ratio-prompt]")!.click();
  await pause();
  const expectedSummary = card.querySelector(".provider-binding-advanced-state")!.textContent!;
  check("advanced summary lists non-default values", expectedSummary.length > 0
    && expectedSummary === card.querySelector(".provider-binding-summary-state")!.textContent);
  const settingsValues = () => ({
    compatibility: cards()[0].querySelector<HTMLSelectElement>("[data-binding-compatibility]")!.value,
    transparency: cards()[0].querySelector<HTMLSelectElement>("[data-binding-transparency]")!.value,
    ratio: cards()[0].querySelector<HTMLInputElement>("[data-binding-ratio-prompt]")!.checked,
  });
  const before = settingsValues();
  advanced.querySelector<HTMLElement>("summary")!.click();
  await pause();
  check("collapsing advanced preserves values", JSON.stringify(settingsValues()) === JSON.stringify(before));

  // Only discovery is stubbed; settings persistence below uses the real isolated backend.
  const originalFetch = w.fetch.bind(w);
  let discoveryCalls = 0;
  w.fetch = ((request: RequestInfo | URL, init?: RequestInit) => {
    const url = typeof request === "string" ? request : request instanceof w.Request ? request.url : String(request);
    if (new URL(url, w.location.href).pathname === "/api/api-settings/models") {
      discoveryCalls++;
      return Promise.resolve(new w.Response(JSON.stringify({ models: [{ id: "qa/vendor-model" }] }), {
        status: 200, headers: { "Content-Type": "application/json" },
      }));
    }
    return originalFetch(request, init);
  }) as typeof w.fetch;
  const canonical = card.querySelector<HTMLSelectElement>("[data-binding-model]")!.value;
  const protocol = card.querySelector<HTMLSelectElement>("[data-binding-protocol]")!.value;
  card.querySelector<HTMLElement>("[data-fetch-provider-models]")!.click();
  await until(() => !!card.querySelector<HTMLSelectElement>("[data-provider-models-select]")?.querySelector('option[value="qa/vendor-model"]'), "synthetic discovery candidate");
  input("[data-provider-models-select]", "qa/vendor-model");
  check("explicit candidate only changes remote name", card.querySelector<HTMLInputElement>("[data-binding-remote-model]")!.value === "qa/vendor-model"
    && card.querySelector<HTMLSelectElement>("[data-binding-model]")!.value === canonical
    && card.querySelector<HTMLSelectElement>("[data-binding-protocol]")!.value === protocol && discoveryCalls === 1);
  w.fetch = originalFetch;

  find("#addProviderBindingButton").click(); await pause();
  check("adding binding opens only the new card", cards().length === 2 && cards().filter(item => item.open).length === 1 && cards()[1].open);
  check("redraw preserves advanced values", JSON.stringify(settingsValues()) === JSON.stringify(before));
  input("[data-binding-remote-model]", "");
  await methods.saveApiProviderEdit!();
  check("invalid collapsed binding opens and receives focus", cards()[0].open && !cards()[1].open
    && d.activeElement === cards()[0].querySelector("[data-binding-remote-model]"));
  input("[data-binding-remote-model]", "qa/vendor-model");
  cards()[1].querySelector<HTMLElement>(".provider-binding-summary")!.click(); await pause();
  const gemini = state.generationCatalog!.models.find(model => model.id.startsWith("nano-banana"));
  if (gemini) {
    const secondModel = cards()[1].querySelector<HTMLSelectElement>("[data-binding-model]")!;
    secondModel.value = gemini.id;
    secondModel.dispatchEvent(new w.Event("change", { bubbles: true }));
    await pause();
    const secondCompatibility = cards()[1].querySelector<HTMLSelectElement>("[data-binding-compatibility]")!;
    const alternative = [...secondCompatibility.options].find(option => option.value !== "standard")!;
    secondCompatibility.value = alternative.value;
    secondCompatibility.dispatchEvent(new w.Event("change", { bubbles: true }));
    await pause();
    check("compatibility change appears in both summaries", cards()[1].querySelector(".provider-binding-advanced-state")!.textContent!.includes(alternative.text)
      && cards()[1].querySelector(".provider-binding-summary-state")!.textContent!.includes(alternative.text));
  }
  cards()[0].querySelector<HTMLElement>(".provider-binding-summary")!.click(); await pause();
  check("summary click switches the single expanded card", cards()[0].open && !cards()[1].open);
  cards()[1].querySelector<HTMLElement>(".provider-binding-summary")!.click(); await pause();
  cards()[1].querySelector<HTMLElement>("[data-remove-provider-binding]")!.click(); await pause();
  check("binding deletion leaves the other binding", cards().length === 1);
  cards()[0].querySelector<HTMLElement>("[data-remove-provider-binding]")!.click(); await pause();
  check("last binding cannot be removed", cards().length === 1);
  input("#apiBaseUrl", "https://api.openai.com/v1");
  await methods.saveApiProviderEdit!();
  await until(() => find("#apiProviderEditor").classList.contains("hidden"), "save completes");
  find("#editApiProviderButton").click(); await pause();
  check("saved advanced settings survive reopening", JSON.stringify(settingsValues()) === JSON.stringify(before));
  check("saved key is not returned to input", find<HTMLInputElement>("#apiKey").value === "");
  advanced = cards()[0].querySelector<HTMLDetailsElement>(".provider-binding-advanced")!;
  advanced.querySelector<HTMLElement>("summary")!.click(); await pause();
  cards()[0].querySelector<HTMLInputElement>("[data-binding-ratio-prompt]")!.click();
  find("#cancelApiProviderEditButton").click(); find("#editApiProviderButton").click(); await pause();
  check("cancel discards advanced edits", JSON.stringify(settingsValues()) === JSON.stringify(before));

  for (const locale of ["zh-CN", "en"]) {
    w.__codexImageI18n.setLocale(locale);
    for (const theme of ["light", "dark"]) {
      find(`[data-theme-option="${theme}"]`).click();
      for (const [width, height] of viewports) {
        await resize(width, height);
        const panel = find("#systemSettingsApiPanel");
        const advancedDetails = cards()[0].querySelector<HTMLDetailsElement>(".provider-binding-advanced")!;
        advancedDetails.open = true; cards()[0].open = true;
        await pause();
        const name = `${locale} ${theme} ${width}x${height}`;
        await checkFooter(`${name} API`, panel, ".api-provider-editor-actions");
        const labels = [...panel.querySelectorAll<HTMLElement>(".field > span, .provider-binding-toggle span, .api-provider-icon-input > span")]
          .filter(label => label.getBoundingClientRect().height > 0);
        const clipped = labels.filter(label => label.scrollWidth > label.clientWidth + 1);
        check(`${name}: labels not clipped`, clipped.length === 0, clipped.map(label => label.textContent));
        check(`${name}: panel has no horizontal overflow`, panel.scrollWidth <= panel.clientWidth + 1);
        const url = find("#apiBaseUrl").getBoundingClientRect(), key = find(".api-key-input-wrap").getBoundingClientRect();
        check(`${name}: URL and key share input axis`, Math.abs(url.left - key.left) <= 1 && Math.abs(url.width - key.width) <= 1);
        const inlineFields = [...panel.querySelectorAll<HTMLElement>(".compact-api-settings-grid > .field, .provider-binding-card[open] .field:not(.provider-binding-remote-model)")];
        for (const field of inlineFields) {
          const label = field.querySelector<HTMLElement>(":scope > span")!;
          const control = field.querySelector<HTMLElement>(":scope > .control, :scope > .themed-select, :scope > .api-key-input-wrap, :scope > .api-provider-name-inputs")!;
          const a = label.getBoundingClientRect(), b = control.getBoundingClientRect();
          check(`${name}: ${label.textContent} label shares control row`, a.right <= b.left && a.top < b.bottom && a.bottom > b.top);
        }
        const remote = cards()[0].querySelector<HTMLInputElement>("[data-binding-remote-model]")!.getBoundingClientRect();
        check(`${name}: remote model retains usable width`, remote.width >= (width > 620 ? 200 : 190));
        check(`${name}: scroll stays inside settings`, w.getComputedStyle(visibleScroll(panel)).overscrollBehaviorY === "contain");
        visibleScroll(panel).scrollTop = visibleScroll(panel).scrollHeight; await pause();
        const save = find("#saveApiProviderEditButton").getBoundingClientRect(), viewport = panel.getBoundingClientRect();
        check(`${name}: sticky save remains accessible`, save.top >= viewport.top - 1 && save.bottom <= viewport.bottom + 1);
        const footer = find(".provider-binding-footer").getBoundingClientRect();
        check(`${name}: final binding controls reachable`, footer.top >= viewport.top - 1 && footer.bottom <= save.top + 1);
        measurements.push({ name, width: panel.clientWidth, content: panel.scrollHeight, viewport: panel.clientHeight, clipped: clipped.length });
        if (locale === "zh-CN" && theme === "dark" && width === 1280) {
          const modal = find(".system-settings-modal-panel"), overlay = find("#systemSettingsModal"), scroll = visibleScroll(panel);
          const baseline = modal.getBoundingClientRect(), footerTop = find(".api-provider-editor-actions").getBoundingClientRect().top;
          let mutations = 0, stable = true;
          const observer = new w.MutationObserver(records => { mutations += records.length; });
          observer.observe(find("#apiProviderEditor"), { subtree: true, childList: true, attributes: true });
          for (let index = 0; index < 24; index++) {
            scroll.scrollTop = index % 2 ? 0 : scroll.scrollHeight;
            await new Promise<void>(resolve => w.requestAnimationFrame(() => resolve()));
            const box = modal.getBoundingClientRect();
            stable &&= Math.abs(box.top - baseline.top) < 1 && Math.abs(box.height - baseline.height) < 1
              && Math.abs(find(".api-provider-editor-actions").getBoundingClientRect().top - footerTop) < 1 && overlay.scrollTop === 0;
          }
          observer.disconnect();
          check("rapid editor scrolling does not re-render fields or move modal/footer", stable && mutations === 0, { stable, mutations });
        }
      }
    }
  }
  find("#cancelApiProviderEditButton").click();
  find("#copyApiProviderButton").click(); await pause();
  check("copy creates an unsaved draft", !!state.apiProviderDraftIsNew);
  check("copy preserves key without displaying it", find<HTMLInputElement>("#apiKey").value === "" && !!state.apiProviderDraft?.api_key_set);
  input("#apiProviderName", "QA-settings-copy");
  await methods.saveApiProviderEdit!();
  await until(() => find("#apiProviderEditor").classList.contains("hidden"), "copy saved with retained key");
  check("copy save retains synthetic credential", state.apiSettings.providers.some((provider: { name: string; api_key_set?: boolean }) => provider.name === "QA-settings-copy" && provider.api_key_set));
  // Populate only the isolated fixture store, so selection and sorting exercise real persistence.
  const savedProviders = state.apiSettings.providers;
  const sourceProvider = savedProviders[0];
  const syntheticProviders = Array.from({ length: 30 - savedProviders.length }, (_, index) => ({
    ...sourceProvider, id: `qa-layout-${index}`, name: `QA Supplier ${String(index).padStart(2, "0")}`,
    base_url: `https://supplier-${index}.example.test/${"long-path/".repeat(12)}`,
    api_key: "qa-layout-synthetic-only", api_key_set: true, concurrency: index % 8 + 1,
    bindings: sourceProvider.bindings.map((binding: any, bindingIndex: number) => ({ ...binding, id: `qa-${index}-${bindingIndex}` })),
  }));
  const seedResponse = await originalFetch("/api/api-settings", {
    method: "PATCH", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ...state.apiSettings, providers: [
      ...savedProviders.map(({ api_key, ...provider }: any) => provider), ...syntheticProviders,
    ] }),
  });
  if (!seedResponse.ok) throw new Error(`Fixture seeding failed: ${seedResponse.status}`);
  state.apiSettings = (await seedResponse.json()).settings;
  methods.populateApiSettingsForm!();
  await pause();
  check("thirty providers available for long-list acceptance", find("#apiProviderList").children.length === 30);
  const modal = find(".system-settings-modal-panel");
  for (const locale of ["zh-CN", "en"]) {
    w.__codexImageI18n.setLocale(locale);
    for (const theme of ["light", "dark"]) {
      find(`[data-theme-option="${theme}"]`).click();
      for (const [width, height] of viewports) {
        await resize(width, height);
        const name = `${locale} ${theme} ${width}x${height} browse`;
        const section = find("#apiProviderSection"), scroll = visibleScroll(section);
        const header = find(".api-provider-section-header"), detail = find("#apiProviderDetail");
        scroll.scrollTop = 0; await pause();
        const headerBefore = header.getBoundingClientRect(), detailBefore = detail.getBoundingClientRect();
        scroll.scrollTop = scroll.scrollHeight; await pause();
        const headerAfter = header.getBoundingClientRect(), detailAfter = detail.getBoundingClientRect();
        const box = modal.getBoundingClientRect(), listBox = scroll.getBoundingClientRect();
        check(`${name}: list really scrolls`, scroll.scrollTop > 0 && scroll.clientHeight >= 64);
        check(`${name}: header and detail stay fixed`, Math.abs(headerBefore.top - headerAfter.top) <= 1 && Math.abs(detailBefore.top - detailAfter.top) <= 1);
        check(`${name}: scrollbar contained between search and detail`, listBox.top >= find("#apiProviderSearchField").getBoundingClientRect().bottom && listBox.bottom <= detailAfter.top);
        check(`${name}: detail and new action visible inside viewport`, detailAfter.bottom <= box.bottom && box.bottom <= height && headerAfter.top >= box.top);
        check(`${name}: no outer or horizontal overflow`, section.scrollHeight <= section.clientHeight + 1 && scroll.scrollWidth <= scroll.clientWidth + 1 && modal.scrollWidth <= modal.clientWidth + 1);
        const buttons = [...detail.querySelectorAll<HTMLButtonElement>("button")];
        const first = buttons[0].getBoundingClientRect(), last = buttons[2].getBoundingClientRect();
        check(`${name}: detail actions centered with equal height and corners`, Math.abs((first.left + last.right) / 2 - (detailAfter.left + detailAfter.right) / 2) <= 1 && buttons.every(button => button.getBoundingClientRect().height === first.height && w.getComputedStyle(button).borderRadius === "8px"));
        const add = find("#addApiProviderButton"), sort = find("#sortApiProvidersButton");
        check(`${name}: top actions align`, add.getBoundingClientRect().height === sort.getBoundingClientRect().height && w.getComputedStyle(add).borderRadius === w.getComputedStyle(sort).borderRadius);
        check(`${name}: new action has distinct solid fill and filled icon`, w.getComputedStyle(add).backgroundColor !== w.getComputedStyle(sort).backgroundColor && w.getComputedStyle(add.querySelector("svg")!).stroke === "none" && !!add.querySelector("svg path"));
        check(`${name}: footer identifies the selected provider`, find("#apiProviderDetailName").textContent === state.apiSettings.providers.find((provider: any) => provider.id === state.apiSettings.active_provider_id)?.name);
      }
    }
  }
  const lastProvider = state.apiSettings.providers.at(-1)!;
  find<HTMLButtonElement>(`[data-api-provider-id="${lastProvider.id}"]`).click(); await pause(500);
  check("selection updates fixed details", find("#apiProviderDetailName").textContent === lastProvider.name
    && find("#apiProviderDetailBaseUrl").textContent === lastProvider.base_url
    && find("#apiProviderDetailConcurrency").textContent === String(lastProvider.concurrency));
  input("#apiProviderSearch", "no-provider-matches-this"); await pause();
  check("empty search retains current details and new action", !!find(".api-provider-search-empty") && find("#apiProviderDetail").getBoundingClientRect().height > 0 && !find("#addApiProviderButton").classList.contains("hidden"));
  input("#apiProviderSearch", lastProvider.name); await pause();
  check("search isolates requested supplier", find("#apiProviderList").children.length === 1);
  input("#apiProviderSearch", ""); await pause();
  find("#sortApiProvidersButton").click(); await pause();
  const sortScroll = visibleScroll(find("#apiProviderSection"));
  sortScroll.scrollTop = sortScroll.scrollHeight; await pause();
  const handle = find<HTMLElement>(`[data-api-provider-id="${lastProvider.id}"] .api-provider-sort-handle`);
  handle.focus(); handle.dispatchEvent(new w.KeyboardEvent("keydown", { key: "Home", bubbles: true }));
  await until(() => state.apiSettings.providers[0].id === lastProvider.id, "keyboard sort moves last supplier to first");
  await pause(400);
  check("sorting remains within the list scroller", sortScroll.getBoundingClientRect().bottom <= find("#apiProviderDetail").getBoundingClientRect().top);
  find("#sortApiProvidersButton").click(); await pause();
  find("#addApiProviderButton").focus();
  check("new action is keyboard focusable", d.activeElement === find("#addApiProviderButton"));
  find("#addApiProviderButton").click(); await pause();
  check("editing hides the entire browsing shell", find("#apiProviderSection").getBoundingClientRect().height === 0 && find("#apiProviderSection").hasAttribute("inert") && find("#apiProviderDetail").getBoundingClientRect().height === 0);
  await checkFooter("new provider from a long list", find("#systemSettingsApiPanel"), ".api-provider-editor-actions");
  find("#cancelApiProviderEditButton").click(); await pause();
  const selectedCard = find<HTMLElement>(`.api-provider-choice[data-api-provider-id="${lastProvider.id}"]`).getBoundingClientRect();
  const restoredList = visibleScroll(find("#apiProviderSection")).getBoundingClientRect();
  check("cancel restores selected card within list viewport", selectedCard.top >= restoredList.top && selectedCard.bottom <= restoredList.bottom);
  for (const theme of ["light", "dark"]) {
    find(`[data-theme-option="${theme}"]`).click();
    for (const [width, height] of viewports) {
      await resize(width, height);
      find("#systemSettingsNetworkTab").click(); await pause(350);
      find('[data-network-egress-mode="custom"]').click(); await pause();
      await checkFooter(`${theme} ${width}x${height} Network`, find("#systemSettingsNetworkPanel"), ".network-egress-actions");
      const indicator = w.getComputedStyle(find(".network-egress-mode-selector .segmented-indicator"));
      check(`${theme}: network uses solid selected fill`, indicator.borderTopWidth === "0px"
        && indicator.backgroundColor === w.getComputedStyle(find("#quantityGroup .segmented-indicator")).backgroundColor);
      input("#networkEgressCustomProxy", "http://127.0.0.1:9");
      input("#networkEgressTimeoutMinutes", "0");
      find("#saveNetworkEgressButton").click(); await pause();
      check(`${theme}: invalid network value keeps error visible`, !find("#networkEgressTimeoutError").hidden);
      await checkFooter(`${theme} ${width}x${height} Network error`, find("#systemSettingsNetworkPanel"), ".network-egress-actions");
      input("#networkEgressTimeoutMinutes", "10");
      find("#systemSettingsStorageTab").click(); await pause(350);
      await checkFooter(`${theme} ${width}x${height} Storage`, find("#systemSettingsStoragePanel"), "#systemSettingsStoragePanel .settings-save-actions");
    }
  }
  for (const status of ["running", "queued"]) {
    const task = {task_id: "qa-preview-timer", mode: "generate", status, params: {size: "auto", n: 2},
      total_count: 2, generated_count: 0, started_at: new Date().toISOString(), created_at: new Date().toISOString(), output_urls: []};
    state.previewRenderKey = null;
    methods.renderPreview!(task);
    const preview = find("#previewGrid");
    check(`${status}: automatic size is omitted`, !preview.querySelector(".elapsed-meta"));
    check(`${status}: elapsed line contains only the live timer`, preview.querySelector(".elapsed-line")?.textContent === preview.querySelector(".elapsed-timer")?.textContent);
    state.previewRenderKey = null;
    methods.renderPreview!({...task, params: {size: "1024x1024", n: 2}});
    check(`${status}: explicit size is retained`, preview.querySelector(".elapsed-meta")?.textContent === "1024x1024");
  }
  check("no application errors", errors.length === 0, errors);
  return { passed: failures.length === 0 && errors.length === 0, assertions, failures, errors, measurements };
}

void run().catch(error => ({ passed: false, assertions, failures, errors: [...errors, String(error)], measurements }))
  .then(async report => {
    output.textContent = JSON.stringify(report);
    await fetch("/qa-results", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(report) });
  });

/** Geometry acceptance on the isolated fixture's actual generation page. */
import { loadAcceptanceFrame, prepareFixtureOrigin } from "./browser_acceptance";
import { LOCALES } from "../../codex_image/webui/frontend/src/i18n/dictionaries";

const frame = document.querySelector<HTMLIFrameElement>("#historyFrame")!;
const output = document.querySelector<HTMLElement>("#results")!;
const errors: string[] = [];
const failures: Array<{ name: string; detail?: unknown }> = [];
const measurements: unknown[] = [];
let assertions = 0;
const pause = (ms = 250) => new Promise(resolve => setTimeout(resolve, ms));
function check(name: string, condition: boolean, detail?: unknown) {
  assertions++;
  if (!condition) failures.push({ name, detail });
}

async function run() {
  await prepareFixtureOrigin();
  localStorage.clear(); // This origin contains only synthetic acceptance data.
  localStorage.setItem("codex-image-locale-preference", "zh-CN");
  await loadAcceptanceFrame(frame, "/qa-app", errors);
  const w = frame.contentWindow!, d = frame.contentDocument!;
  const find = (selector: string) => d.querySelector<HTMLElement>(selector)!;
  const deadline = Date.now() + 15000;
  while (!w.__codexImageWebUI?.state.generationCatalog) {
    if (Date.now() > deadline) throw new Error("Catalog did not load");
    await pause(50);
  }
  const { state, methods } = w.__codexImageWebUI;
  w.__codexImageI18n.setLocale("zh-CN");
  const gptModel = state.selectedModelId;
  const gallery = (count: number) => {
    state.galleryItems = Array.from({ length: count }, (_, index) => ({
      id: `qa-gallery-${index}`, name: `素材 ${index + 1}`, category: state.activeGalleryCategory,
      image_url: "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='16' height='16'/%3E",
    }));
    methods.renderQuickGalleryDock!();
  };
  gallery(5);
  const rect = (selector: string) => find(selector).getBoundingClientRect();
  const size = async (width: number, height: number, sidebar = 347) => {
    frame.style.width = `${width}px`;
    frame.style.height = `${height}px`;
    find("#sidebar").style.setProperty("--sidebar-width", `${sidebar}px`);
    await pause();
    find(".dashboard").scrollTop = 0;
  };
  const editorVisibility = (name: string) => {
    const editor = find("#promptEditor"), bounds = editor.getBoundingClientRect();
    let top = bounds.top, bottom = bounds.bottom;
    // Dashboard scrolling is intentional; clipping inside the composer is not.
    for (let ancestor = editor.parentElement; ancestor && !ancestor.classList.contains("dashboard");
      ancestor = ancestor.parentElement) {
      if (!["hidden", "clip", "auto", "scroll"].includes(w.getComputedStyle(ancestor).overflowY)) continue;
      const box = ancestor.getBoundingClientRect();
      top = Math.max(top, box.top + ancestor.clientTop);
      bottom = Math.min(bottom, box.top + ancestor.clientTop + ancestor.clientHeight);
    }
    const visibleHeight = Math.max(0, bottom - top);
    check(`${name}: ancestors do not clip editor`, visibleHeight >= bounds.height - 1,
      { editor: bounds.height, visible: visibleHeight, compose: rect(".prompt-compose").height,
        wrapper: rect(".prompt-editor-wrap").height });
    check(`${name}: prompt tools stay below editor`, rect(".prompt-template-row").top >= bounds.bottom - 1);
  };
  const geometry = (name: string, fit = false) => {
    const dash = find(".dashboard"), root = d.documentElement;
    const workspace = rect(".main-wrapper").width;
    const stacked = workspace < 900;
    const controls = rect(".controls-col"), preview = rect(".preview-col");
    check(`${name}: no page horizontal overflow`, root.scrollWidth <= root.clientWidth + 1
      && dash.scrollWidth <= dash.clientWidth + 1);
    check(`${name}: dashboard owns page scrolling`, root.scrollHeight <= root.clientHeight + 1
      && !["auto", "scroll"].includes(w.getComputedStyle(find(".controls-col")).overflowY));
    const editor = find("#promptEditor"), editorStyle = w.getComputedStyle(editor);
    const textHeight = editor.clientHeight - parseFloat(editorStyle.paddingTop) - parseFloat(editorStyle.paddingBottom);
    check(`${name}: editor shows at least three text lines`, textHeight >= 3 * parseFloat(editorStyle.lineHeight) - 1);
    editorVisibility(name);
    check(`${name}: workspace determines columns`, stacked ? preview.top >= controls.bottom - 1
      : Math.abs(preview.bottom - controls.bottom) <= 1);
    if (!d.body.classList.contains("mobile-ui")) {
      check(`${name}: upload and gallery share a track`, Math.abs(rect(".image-input-main").height
        - rect("#quickGalleryDock").height) <= 1,
      [".image-input-main", ".image-input-left", ".image-input-footer", ".image-gallery-column", "#quickGalleryDock"].map(selector => ({selector,
        height: rect(selector).height, cssHeight: w.getComputedStyle(find(selector)).height,
        minHeight: w.getComputedStyle(find(selector)).minHeight, rows: w.getComputedStyle(find(selector)).gridTemplateRows})));
      if (!stacked && w.innerHeight <= 1390) {
        const workspaceBottom = rect(".image-input-workspace").bottom;
        check(`${name}: reference actions fill the allocated panel height`,
          [".image-input-footer", ".gallery-manage-panel"].every(selector =>
            Math.abs(rect(selector).bottom - workspaceBottom) <= 1),
          { workspaceBottom, uploadBottom: rect(".image-input-footer").bottom,
            galleryBottom: rect(".gallery-manage-panel").bottom });
        check(`${name}: gallery lists fill the available track`,
          ["#quickGalleryList", ".quick-gallery-rail"].every(selector =>
            Math.abs(rect(selector).height - rect("#quickGalleryDock").height) <= 1));
      }
      const buttons = [...d.querySelectorAll<HTMLElement>(
        ".output-panel :is(.orientation-field, .resolution-field, .quality-field, .quantity-field, #promptFidelityField, .custom-size-control) .radio-btn")]
        .filter(button => button.getBoundingClientRect().height > 0 && !button.closest('[aria-hidden="true"]'));
      check(`${name}: field options are not clipped`, buttons.every(button => button.scrollWidth <= button.clientWidth + 1),
        buttons.filter(button => button.scrollWidth > button.clientWidth + 1).map(button => button.textContent?.trim()));
    }
    const compactComposer = w.getComputedStyle(find(".controls-col")).getPropertyValue("--compact-composer").trim() === "1";
    if (!d.body.classList.contains("mobile-ui")) {
      check(`${name}: output title stays visible`, rect(".output-panel h2").height > 0);
      for (const selector of [".image-panel h2", ".prompt-panel h2"]) {
        check(`${name}: ${selector} follows density`, compactComposer ? rect(selector).height === 0 : rect(selector).height > 0);
      }
      const summary = find("#executionSummary"), count = find("#charCount"), restore = find("#restoreComposerDraft");
      check(`${name}: metadata follows density without duplication`, d.querySelectorAll("#executionSummary").length === 1
        && summary.parentElement === find(compactComposer ? "#compactExecutionSummary" : ".prompt-heading-actions")
        && count.parentElement === find(compactComposer ? "#compactPromptMeta" : ".prompt-heading-main")
        && restore.parentElement === find(compactComposer ? "#compactPromptMeta" : ".prompt-heading-actions"));
      if (compactComposer) {
        const summaryBounds = summary.getBoundingClientRect();
        check(`${name}: execution summary stays between title and lock`, summaryBounds.left >= rect(".output-panel h2").right
          && summaryBounds.right <= rect("#outputSettingsLockButton").left
          && summaryBounds.top >= rect("#outputSettingsHeader").top
          && summaryBounds.bottom <= rect("#outputSettingsHeader").bottom);
        check(`${name}: compact reference panel does not crowd the prompt`,
          rect(".prompt-panel").height >= rect(".image-panel").height - 1);
        if (!find(".image-panel").classList.contains("references-collapsed")) {
          check(`${name}: reference content uses its allocated panel height`,
            rect(".image-panel").bottom - rect(".image-input-workspace").bottom <= 8);
        }
        const maxPromptLines = w.innerHeight <= 800 ? 5 : 8;
        check(`${name}: compact prompt grows with available height without taking over the column`, textHeight <= maxPromptLines * parseFloat(editorStyle.lineHeight) + 1,
          { textHeight, lineHeight: editorStyle.lineHeight });
        check(`${name}: compact output and preview finish at the same content height`,
          Math.abs(rect(".output-panel").bottom - preview.bottom) <= 1);
        const dashboardStyle = w.getComputedStyle(dash);
        const availableBottom = dash.getBoundingClientRect().bottom - parseFloat(dashboardStyle.paddingBottom);
        check(`${name}: compact columns use the entire available workspace`,
          controls.bottom >= availableBottom - 1 && preview.bottom >= availableBottom - 1);
        check(`${name}: compact parameter groups use spacing without separators`,
          parseFloat(w.getComputedStyle(find(".mode-settings-slot")).borderBottomWidth) === 0
          && parseFloat(w.getComputedStyle(find(".output-file-settings")).borderTopWidth) === 0
          && parseFloat(w.getComputedStyle(find(".mode-settings-slot")).paddingBottom) === 0
          && parseFloat(w.getComputedStyle(find(".output-file-settings")).paddingTop) === 0);
        const modeBounds = rect(".mode-settings-slot"), sizeBounds = rect(".output-size-settings"), fileBounds = rect(".output-file-settings");
        if (modeBounds.height > 0 && sizeBounds.height > 0 && fileBounds.height > 0) {
          const gap = parseFloat(w.getComputedStyle(find(".settings-grid")).rowGap);
          check(`${name}: compact group spacing is balanced`,
            Math.abs((sizeBounds.top - modeBounds.bottom) - (fileBounds.top - sizeBounds.bottom)) <= 1);
          check(`${name}: compact group spacing does not absorb unused height`,
            gap >= 8 && gap <= 16
            && Math.abs(sizeBounds.top - modeBounds.bottom - gap) <= 1
            && Math.abs(fileBounds.top - sizeBounds.bottom - gap) <= 1,
            {gap, first: sizeBounds.top - modeBounds.bottom, second: fileBounds.top - sizeBounds.bottom});
          check(`${name}: unused height is not moved below the last parameter`,
            rect(".output-panel").bottom - fileBounds.bottom <= parseFloat(w.getComputedStyle(find(".output-panel")).paddingBottom) + 2);
        }
        const choices = [...d.querySelectorAll<HTMLElement>(".output-panel .radio-btn")]
          .filter(button => button.getBoundingClientRect().height > 0 && !button.closest('[aria-hidden="true"]'));
        check(`${name}: parameter buttons have roomier targets`, choices.every(button => button.getBoundingClientRect().height >= 28));
      }
    }
    if (fit) check(`${name}: default panels fit viewport`, dash.scrollHeight <= dash.clientHeight + 1,
      { available: dash.clientHeight, content: dash.scrollHeight });
    return { name, width: w.innerWidth, height: w.innerHeight, workspace: Math.round(workspace),
      overflow: dash.scrollHeight - dash.clientHeight, output: Math.round(rect(".output-panel").height) };
  };
  if (new URLSearchParams(location.search).has("duration-spacing-only")) {
    const end = new Date().toISOString();
    const start = new Date(Date.now() - 143000).toISOString();
    state.tasks = ['completed', 'failed', 'running'].map((status, index) => ({
      task_id: `qa-duration-${index}`, status, mode: 'generate', prompt: `QA duration ${index}`,
      created_at: start, started_at: start, completed_at: status === 'running' ? null : end,
      params: {model: 'gpt-image-2', size: '1024x1024', n: 1}, output_urls: [],
    }));
    state.taskSidebarGroupCounts = {};
    const heights = new Map<string, number[]>();
    for (const theme of ['light', 'dark']) {
      find(`[data-theme-option="${theme}"]`).click();
      for (const locale of LOCALES) {
        w.__codexImageI18n.setLocale(locale);
        methods.renderTasks!();
        for (const [width, height, sidebar] of [[1920, 1080, 347], [1512, 699, 280]]) {
          await size(width, height, sidebar);
          const name = `${theme} ${locale} ${width}`;
          const cards = [...d.querySelectorAll<HTMLElement>('#sidebar .task-card')];
          const runtime = [...d.querySelectorAll<HTMLElement>('#sidebar .task-runtime')];
          check(`${name}: terminal durations retain a word boundary before the clock`, runtime.length === 2 && runtime.every(el => /\s\d{2}:\d{2}/.test(el.textContent || '')));
          const timers = [...d.querySelectorAll<HTMLElement>('#sidebar .task-card-running-timer')];
          check(`${name}: active timer keeps a visible label gap`, timers.length === 1 && parseFloat(w.getComputedStyle(timers[0]).gap) >= 5);
          check(`${name}: duration words have breathing room`, [...runtime, ...timers].every(el => parseFloat(w.getComputedStyle(el).wordSpacing) >= 1));
          check(`${name}: clock animation keeps natural tracking`, timers.every(el => w.getComputedStyle(el.querySelector('.elapsed-timer')!).letterSpacing === 'normal'));
          if (locale === 'hi') check(`${name}: Devanagari retains natural shaping`, [...runtime, ...timers].every(el => w.getComputedStyle(el).letterSpacing === 'normal'));
          check(`${name}: task rows do not overflow horizontally`, cards.length === 3 && cards.every(el => el.scrollWidth <= el.clientWidth + 1));
          const key = `${theme} ${width}`, current = cards.map(el => el.getBoundingClientRect().height);
          if (!heights.has(key)) heights.set(key, current);
          check(`${name}: translating duration does not change card height`, current.every((h, i) => Math.abs(h - heights.get(key)![i]) < 1));
        }
      }
    }
    w.__codexImageI18n.setLocale('zh-TW'); methods.renderTasks!();
    return {passed: failures.length === 0 && errors.length === 0, assertions, failures, errors};
  }
  const comfortOnly = new URLSearchParams(location.search).has("comfort-only");
  if (new URLSearchParams(location.search).has("density-only") || comfortOnly) {
    const selectors = ["#promptFidelityGroup .radio-btn", "#sizeModeGroup .radio-btn",
      "#orientationGroup .radio-btn", "#resolutionGroup .radio-btn", "#ratioGroup .radio-btn[data-val='4:5']",
      "#qualityGroup .radio-btn", "#quantityGroup .radio-btn", "#outputFormatGroup .radio-btn", "#moderationGroup .radio-btn"];
    const bindings = methods.eligibleProviderBindings!(state.generationCatalog, state.selectedModelId, state.mode);
    for (const theme of ["dark", "light"]) {
      find(`[data-theme-option="${theme}"]`).click();
      for (const {binding, selectionKey} of bindings) {
        methods.selectGenerationProvider!(selectionKey); await pause();
        find('#outputFormatGroup [data-val="webp"]').click();
        await size(2560, 1323, 280);
        const regular = selectors.map(selector => rect(selector).height);
        geometry(`${theme} ${binding.id} regular density`, true);
        for (const [width, height] of [[1512,773], [1512,699], [1440,900], [1280,720]]) {
          await size(width, height, 280);
          const compact = selectors.map(selector => rect(selector).height);
          check(`${theme} ${binding.id} ${width}x${height}: compact targets never exceed regular targets`,
            compact.every((height, index) => height <= regular[index] + 0.1), {regular, compact});
          measurements.push(geometry(`${theme} ${binding.id} ${width}x${height} density`, true));
          if (comfortOnly) {
            const name = `${theme} ${binding.id} ${width}x${height}`;
            for (const selector of ['.quick-gallery-list', '.quick-gallery-rail']) {
              check(`${name}: ${selector} buttons have vertical breathing room`, parseFloat(w.getComputedStyle(find(selector)).rowGap) >= 4);
            }
            const rail = find('.quick-gallery-rail');
            check(`${name}: three gallery categories fit without clipping`, rail.children.length === 3 && rail.scrollHeight <= rail.clientHeight + 1);
            const panelStyle = w.getComputedStyle(find('.output-panel'));
            check(`${name}: output content has consistent edge space`, ['paddingTop','paddingBottom','paddingLeft','paddingRight'].every(key => parseFloat(panelStyle[key]) >= 12));
            check(`${name}: composer footer actions have comfortable equal heights`, ['#clearImagesButton','#pasteClipboardButton','#galleryManageButton','#clearPromptButton','#promptFindButton','#promptTemplateButton'].every(selector => Math.abs(rect(selector).height-32)<1));
            const before = rect('.output-panel');
            find('#outputSettingsLockButton').click(); await pause();
            const cards = [...d.querySelectorAll<HTMLElement>('.output-settings-summary-card')];
            check(`${name}: locked cards keep content away from edges`, cards.length===3 && cards.every(card => { const box=card.getBoundingClientRect(), label=card.querySelector('.output-settings-summary-card-label')!.getBoundingClientRect(), meta=card.querySelector('.output-settings-card-meta')?.getBoundingClientRect(); return label.top-box.top>=12 && (!meta || box.bottom-meta.bottom>=12); }));
            check(`${name}: locked detail row is separated from cards`, rect('.output-settings-summary-details').top-rect('.output-settings-summary-cards').bottom>=12);
            check(`${name}: locked summary remains visible without overflow`, ['#outputSettingsLockedSummary','.output-settings-summary-content'].every(selector => {const el=find(selector);return el.scrollWidth<=el.clientWidth+1 && el.scrollHeight<=el.clientHeight+1;}));
            check(`${name}: locking keeps panel geometry`, Math.abs(rect('.output-panel').height-before.height)<1 && Math.abs(rect('.output-panel').bottom-before.bottom)<1);
            find('#outputSettingsLockButton').click(); await pause();
          }
        }
      }
    }
    await size(1512,773,280);
    return {passed:failures.length===0&&errors.length===0,assertions,failures,measurements,errors};
  }
  if (new URLSearchParams(location.search).has("preview-size-only")) {
    for (const theme of ["dark", "light"]) {
      find(`[data-theme-option="${theme}"]`).click();
      for (const [width, height] of [[1512,773], [1280,720]]) {
        await size(width,height,280);
        for (const count of [1, 4]) {
          const urls = Array.from({length:count}, (_, index) =>
            `data:image/svg+xml,${encodeURIComponent(`<svg xmlns="http://www.w3.org/2000/svg" width="120" height="240"><rect width="120" height="240" fill="hsl(${index * 60} 20% 70%)"/></svg>`)}`);
          methods.renderPreview!({task_id:`qa-preview-${theme}-${width}-${count}`,status:"completed",
            params:{model:"gpt-image-2",size:"1024x2048",n:count},output_urls:urls});
          await pause(400);
          const cards = [...d.querySelectorAll<HTMLElement>("#previewGrid [data-preview-card-key]")];
          check(`${theme} ${width} ${count} outputs: every image remains available`, cards.length === count
            && cards.every(card => { const img = card.querySelector("img"); return img?.complete && img.naturalWidth > 0; }));
          geometry(`${theme} ${width} ${count} outputs`, true);
          check(`${theme} ${width} ${count} outputs: preview stays inside its panel`,
            rect("#previewGrid").bottom <= rect(".preview-panel").bottom
            && find("#previewGrid").scrollWidth <= find("#previewGrid").clientWidth + 1);
        }
      }
    }
    return {passed:failures.length===0&&errors.length===0,assertions,failures,errors};
  }
  if (new URLSearchParams(location.search).has("task-press")) {
    await size(1512, 767, 280);
    const createdAt = new Date().toISOString();
    state.tasks = Array.from({length:3}, (_, index) => ({task_id:`qa-pressed-card-${index}`, status:"completed",
      mode:"generate", prompt:`QA task ${index + 1}`, created_at:createdAt, completed_at:createdAt,
      params:{model:"gpt-image-2",size:"1024x1024",n:1}, output_urls:[state.galleryItems[0].image_url],
      thumbnail_urls:[state.galleryItems[0].image_url]}));
    state.taskSidebarGroupCounts = {};
    methods.renderTasks!(); await pause();
    const cards = [...d.querySelectorAll<HTMLElement>("#taskList .task-card")];
    check("reported three-card sidebar is reproduced", cards.length === 3);
    const card = cards[cards.length - 1], surface = card.querySelector<HTMLElement>(".task-card-swipe-surface")!;
    card.classList.add("active");
    // Keep this acceptance on the synthetic list instead of loading a task.
    card.addEventListener("click", event => { event.preventDefault(); event.stopPropagation(); }, true);
    for (const theme of ["dark", "light"]) {
      find(`[data-theme-option="${theme}"]`).click();
      output.textContent = `Hold the last task card (${theme})`;
      await new Promise<void>(resolve => {
        card.addEventListener("pointerdown", () => {
          w.setTimeout(() => {
            const bounds = card.getBoundingClientRect(), paint = surface.getBoundingClientRect();
            const hit = d.elementFromPoint(paint.x + paint.width / 2, paint.bottom - 0.25);
            check(`${theme}: actual pointer hold activates the pressed surface`, surface.matches(":active"));
            check(`${theme}: pressed border stays inside its card`, paint.top >= bounds.top - 0.1
              && paint.bottom <= bounds.bottom + 0.1 && paint.left >= bounds.left - 0.1 && paint.right <= bounds.right + 0.1,
              {cardTop: bounds.top, cardBottom: bounds.bottom, surfaceTop: paint.top, surfaceBottom: paint.bottom});
            check(`${theme}: bottom border is not clipped by an ancestor`, Boolean(hit && card.contains(hit)));
          }, 150);
          card.addEventListener("pointerup", () => { w.setTimeout(resolve, 100); }, {once:true});
        }, {once:true});
      });
    }
    return {passed:failures.length===0&&errors.length===0,assertions,failures,errors};
  }
  const referenceAcceptance = async () => {
    for (const theme of ["light", "dark"]) {
      find(`[data-theme-option="${theme}"]`).click();
      let shortOutputHeight = 0;
      let shortParameterGap = 0;
      for (const [width, height, sidebar] of [[1512,699,280],[1512,767,280],
        [1440,900,347],[1280,720,347],[1024,768,347],[1920,1080,347]]) {
        await size(width, height, sidebar);
        state.images = [];
        methods.renderImageStrip!();
        gallery(1); await pause();
        const panelHeight = rect(".image-panel").height;
        measurements.push(geometry(`${theme} empty reference ${width}x${height}`, true));
        if (width === 1512 && height === 699) {
          shortOutputHeight = rect(".output-panel").height;
          shortParameterGap = parseFloat(w.getComputedStyle(find(".preset-size-fields")).rowGap);
        }
        if (width === 1512 && height === 767) {
          check(`${theme}: extra height eases parameter density`, rect(".output-panel").height > shortOutputHeight,
            { shortOutputHeight, tallerOutputHeight: rect(".output-panel").height });
          const gap = parseFloat(w.getComputedStyle(find(".preset-size-fields")).rowGap);
          check(`${theme}: extra height increases actual parameter spacing`, gap >= shortParameterGap + 4,
            { shortParameterGap, tallerParameterGap: gap });
        }
        gallery(30); await pause();
        check(`${theme} ${width}x${height}: gallery count preserves reference height`,
          Math.abs(rect(".image-panel").height - panelHeight) <= 1);
        const list = find("#quickGalleryList");
        list.scrollTop = list.scrollHeight;
        check(`${theme} ${width}x${height}: last gallery item remains reachable`,
          list.scrollTop > 0 && list.lastElementChild!.getBoundingClientRect().bottom
            <= list.getBoundingClientRect().bottom + 1);
        state.images = state.galleryItems.slice(0, 2).map((item: object) => ({ ...item, kind: "gallery" }));
        methods.renderImageStrip!(); await pause();
        measurements.push(geometry(`${theme} populated reference ${width}x${height}`, true));
      }
    }
    state.images = [];
    methods.renderImageStrip!();
    gallery(5);
  };
  if (new URLSearchParams(location.search).has("reference-only")) {
    await referenceAcceptance();
    return {passed:failures.length===0&&errors.length===0,assertions,failures,measurements,errors};
  }
  const compactAcceptance = async () => {
    const bindings = methods.eligibleProviderBindings!(state.generationCatalog, state.selectedModelId, state.mode);
    state.images = state.galleryItems.slice(0, 2).map((item: object) => ({...item,kind:'gallery'}));
    methods.renderImageStrip!();
    state.recentAssets = [{id:'qa-compact-recent',filename:'QA preview',image_url:state.galleryItems[0].image_url}];
    methods.renderRecentAssets!();
    for (const locale of ['zh-CN','en']) {
      w.__codexImageI18n.setLocale(locale);
      for (const theme of ['light','dark']) {
        find(`[data-theme-option="${theme}"]`).click();
        for (const {binding,selectionKey} of bindings) {
          methods.selectGenerationProvider!(selectionKey); await pause();
          for (const [width, height, sidebar] of [[1512,699,280],[1512,699,347],[1440,900,347],[1536,864,347],[1366,768,347],[1280,720,347],[1024,768,347],[1920,1080,347]]) {
            await size(width,height,sidebar);
            const name=`${locale} ${theme} ${binding.id} ${width}x${height} sidebar ${sidebar}`;
            measurements.push({...geometry(name,locale==='zh-CN'||height>=900),panels:['.image-panel','.prompt-panel','#promptEditor','.output-panel'].map(selector=>({selector,height:rect(selector).height}))});
            const thumbBounds=rect('.image-thumb-list');
            check(`${name}: reference thumbnails are not vertically clipped`,[...d.querySelectorAll<HTMLElement>('#imageThumbItems .thumb')].every(thumb=>{const r=thumb.getBoundingClientRect();return r.top>=thumbBounds.top-1&&r.bottom<=thumbBounds.bottom+1;}));
            const recentBounds=rect('#recentAssetDock'),footerBounds=rect('.image-input-footer');
            check(`${name}: recent uploads fit their footer`,recentBounds.top>=footerBounds.top-1&&recentBounds.bottom<=footerBounds.bottom+1);
            if (rect('#mainModel').height>0) check(`${name}: main model and prompt processing align`,Math.abs(rect('#mainModel').top-rect('#promptFidelityGroup').top)<1&&Math.abs(rect('#mainModel').height-rect('#promptFidelityGroup').height)<1);
            check(`${name}: redundant size-mode label is absent`, !d.querySelector('.custom-size-control > .field-label'));
            for (const format of ['png','jpeg']) {
              find(`#outputFormatGroup [data-val="${format}"]`).click(); await pause();
              check(`${name} ${format}: file options fit`,['#outputFormatField','.moderation-field'].every(selector=>find(selector).scrollWidth<=find(selector).clientWidth+1));
            }
            find('[data-custom-size-mode="custom"]').click();await pause();
            const card=find('#customSize'),firstImage=find('#customRatioFromImageButton') as HTMLButtonElement;
            check(`${name}: custom inputs fit`,card.scrollWidth<=card.clientWidth+1&&card.scrollHeight<=card.clientHeight+1,{height:card.clientHeight,content:card.scrollHeight});
            firstImage.disabled=false;await pause();
            check(`${name}: first-image action fits`,card.scrollWidth<=card.clientWidth+1&&card.scrollHeight<=card.clientHeight+1,{height:card.clientHeight,content:card.scrollHeight});
            firstImage.disabled=true;
            find('[data-custom-size-mode="preset"]').click();await pause();
          }
        }
      }
    }
    w.__codexImageI18n.setLocale('zh-CN');
    methods.selectGenerationProvider!(bindings[0].selectionKey);
    find('#outputFormatGroup [data-val="png"]').click();
    state.images=Array.from({length:6},(_,index)=>({...state.galleryItems[index%state.galleryItems.length],id:`qa-reference-${index}`,kind:'gallery'}));
    methods.renderImageStrip!();
    for (const [width,height] of [[1512,699],[1280,720]]) {
      await size(width,height,280);
      geometry(`many references ${width}x${height}`,true);
      const source=rect('#imageUploadSource'),track=rect('.image-thumb-list');
      check(`many references ${width}: upload entry remains usable`,source.width>=24&&source.height>=24&&source.bottom<=rect('.image-input-main').bottom+1);
      check(`many references ${width}: thumbnails stay inside their track`,[...d.querySelectorAll<HTMLElement>('#imageThumbItems .thumb')].every(thumb=>{const r=thumb.getBoundingClientRect();return r.top>=track.top-1&&r.bottom<=track.bottom+1;}));
    }
    state.images=[];methods.renderImageStrip!();
  };
  if (new URLSearchParams(location.search).has("compact-only")) {
    await compactAcceptance();
    return {passed:failures.length===0&&errors.length===0,assertions,failures,measurements,errors};
  }
  // A real draft survives moving its action, and focus survives the breakpoint.
  await size(1512, 767, 280);
  methods.setPromptText!("QA compact draft");
  find("#clearPromptButton").click(); await pause();
  const restoreDraft = find("#restoreComposerDraft");
  check("compact restore action is accessible in the footer", !restoreDraft.hidden
    && restoreDraft.parentElement === find("#compactPromptMeta") && rect("#restoreComposerDraft").height >= 24);
  restoreDraft.focus();
  check("restore action accepts keyboard focus before resizing", d.activeElement === restoreDraft);
  await size(1512, 901, 280);
  check("restore action retains keyboard focus when returning to regular layout", d.activeElement === restoreDraft);
  await size(1512, 767, 280);
  check("restore action retains keyboard focus when entering compact layout", d.activeElement === restoreDraft);
  restoreDraft.click(); await pause();
  check("moved restore action retains its original handler", methods.getPromptText!() === "QA compact draft");
  methods.setPromptText!(""); methods.updatePromptCount!();
  if (new URLSearchParams(location.search).has("headings-only")) {
    geometry("compact headings", true);
    await size(1512, 901, 280); geometry("regular headings");
    await size(1512, 767, 280); geometry("compact headings restored", true);
    const editorHeight = rect("#promptEditor").height;
    methods.setPromptText!(Array.from({length:10}, (_, index) => `${index + 1}`).join("\n"));
    await pause();
    check("ten-line prompt does not enlarge the compact editor", Math.abs(rect("#promptEditor").height - editorHeight) <= 1);
    check("ten-line prompt scrolls inside its allocated editor", find("#promptEditor").scrollHeight > find("#promptEditor").clientHeight);
    geometry("ten-line compact prompt", true);
    methods.setPromptText!("");
    return {passed:failures.length===0&&errors.length===0,assertions,failures,measurements,errors};
  }
  for (const theme of ["light", "dark"]) {
    find(`[data-theme-option="${theme}"]`).click();
    check(`${theme} theme applied`, find(`[data-theme-option="${theme}"]`).getAttribute("aria-pressed") === "true");
    for (const [width, height] of [[2560, 1440], [2560, 1159], [1920, 1080], [1920, 900],
      [1680, 1050], [1600, 900], [1536, 864], [1440, 900], [1366, 768], [1280, 720], [1024, 768], [820, 1180], [390, 844]]) {
      await size(width, height);
      measurements.push(geometry(`${theme} ${width}x${height}`, width >= 1920 && height >= 1080));
    }
  }
  await size(1280, 600);
  const editor = find("#promptEditor"), compactEditorHeight = rect("#promptEditor").height;
  const editorStyle = w.getComputedStyle(editor);
  const threeLinesHeight = 3 * parseFloat(editorStyle.lineHeight) + parseFloat(editorStyle.paddingTop)
    + parseFloat(editorStyle.paddingBottom) + parseFloat(editorStyle.borderTopWidth) + parseFloat(editorStyle.borderBottomWidth);
  check("short viewport uses the three-line minimum", Math.abs(compactEditorHeight - threeLinesHeight) <= 1,
    { actual: compactEditorHeight, expected: threeLinesHeight });
  methods.setPromptText!("第一行\n第二行\n第三行");
  await pause();
  check("three text lines fit without editor scrolling", editor.scrollHeight <= editor.clientHeight + 1);
  const beforeLongPrompt = find(".dashboard").scrollHeight;
  methods.setPromptText!(Array.from({ length: 20 }, (_, index) => `提示词第 ${index + 1} 行`).join("\n"));
  editor.focus();
  await pause();
  check("compact editor remains focusable", d.activeElement === editor);
  check("long prompt scrolls inside editor", editor.scrollHeight > editor.clientHeight);
  check("long prompt preserves page height", Math.abs(find(".dashboard").scrollHeight - beforeLongPrompt) <= 1);
  editor.scrollTop = editor.scrollHeight;
  check("last prompt line remains reachable", editor.scrollTop > 0
    && editor.scrollTop + editor.clientHeight >= editor.scrollHeight - 1);
  methods.setPromptText!("");
  for (const [width, height] of [[1920, 900], [1280, 720], [1024, 768]]) {
    await size(width, height);
    methods.setPromptText!("第一行\n第二行\n第三行"); await pause();
    editorVisibility(`${width} desktop, find closed`);
    find("#promptFindButton").click(); await pause();
    editorVisibility(`${width} desktop, find expanded`);
    check(`${width} desktop three lines remain visible with find`, editor.scrollHeight <= editor.clientHeight + 1);
    find("#promptFindClose").click();
  }
  methods.setPromptText!("");
  await size(2560, 1440);
  check("tall viewport expands editor beyond the minimum", rect("#promptEditor").height > compactEditorHeight + 1);
  // Content count must not set the reference panel's intrinsic height.
  for (const [width, height] of [[2560, 1159], [1920, 1080], [1440, 900], [1024, 768]]) {
    await size(width, height);
    gallery(1); await pause();
    const before = rect(".image-panel").height;
    gallery(30); await pause();
    const list = find("#quickGalleryList");
    check(`${width}x${height}: gallery count preserves panel height`, Math.abs(rect(".image-panel").height - before) <= 1);
    check(`${width}x${height}: long gallery scrolls locally`, list.scrollHeight > list.clientHeight);
    list.scrollTop = list.scrollHeight;
    check(`${width}x${height}: last gallery item reachable`, list.scrollTop > 0
      && list.lastElementChild!.getBoundingClientRect().bottom <= list.getBoundingClientRect().bottom + 1);
  }
  gallery(5);
  for (const [width, height] of [[1560, 900], [1561, 900], [1920, 1390], [1920, 1391]]) {
    await size(width, height);
    geometry(`density boundary ${width}x${height}`, height >= 1080);
  }
  // Sidebars and widths immediately around the layout boundaries.
  for (const sidebar of [280, 347, 520]) {
    for (const workspace of [899, 900, 1100, 1101]) {
      await size(sidebar + workspace, 900, sidebar);
      geometry(`sidebar ${sidebar}, workspace ${workspace}`);
    }
  }
  await size(1920, 1080);
  const originalHeight = rect(".output-panel").height;
  find('[data-custom-size-mode="custom"]').click(); await pause();
  check("custom size preserves panel height", Math.abs(rect(".output-panel").height - originalHeight) <= 1);
  check("custom size fields remain accessible", rect("#customWidth").width > 0
    && !find("#customWidth").closest("[inert]"));
  check("custom dimensions fit their editor", find("#customSize").scrollWidth <= find("#customSize").clientWidth + 1);
  find("#outputSettingsLockButton").click(); await pause();
  check("locking preserves panel height", Math.abs(rect(".output-panel").height - originalHeight) <= 1);
  find("#outputSettingsLockButton").click(); await pause();
  find('[data-custom-size-mode="preset"]').click(); await pause();
  find("#promptFidelityHelpButton").focus();
  check("help remains keyboard focusable", d.activeElement === find("#promptFidelityHelpButton"));
  find("#promptFindButton").click(); await pause();
  geometry("expanded prompt tools");
  find("#promptFindClose").click();
  const gemini = state.generationCatalog!.models.filter(model => model.family_id !== state.selectedFamilyId);
  for (const model of gemini) {
    methods.selectConcreteModel!(model.id); await pause();
    geometry(model.id, true);
    await size(1024, 768); geometry(`${model.id} compact`);
    await size(1920, 1080);
  }
  methods.selectConcreteModel!(gptModel); await pause();
  geometry("restored GPT", true);
  const bindings = methods.eligibleProviderBindings!(state.generationCatalog, state.selectedModelId, state.mode);
  check("built-in bindings available for acceptance", bindings.length >= 2);
  for (const { provider, binding, selectionKey } of bindings) {
    methods.selectGenerationProvider!(selectionKey); await pause();
    check(`${binding.id}: binding selected`, state.selectedProviderBindingId === binding.id);
    geometry(`${provider.id} ${binding.id}`, true);
  }
  for (const locale of ["en", "zh-CN"]) {
    w.__codexImageI18n.setLocale(locale);
    for (const [width, height] of [[1920, 1080], [1680, 1050], [1600, 900], [1580, 900], [1536, 864], [1440, 900], [1366, 768], [1280, 720]]) {
      await size(width, height); geometry(`${locale} ${width}x${height}`, width === 1920);
    }
  }
  for (const locale of ["en", "zh-CN"]) {
    w.__codexImageI18n.setLocale(locale);
    await size(390, 844);
    find(".mobile-parameters-button").click(); await pause();
    check(`${locale}: mobile parameter sheet opens`, rect("#mobileParameters .output-panel").height > 0);
    check(`${locale}: mobile parameter sheet has no horizontal overflow`, find("#mobileParameters").scrollWidth
      <= find("#mobileParameters").clientWidth + 1);
    check(`${locale}: mobile parameter controls retain touch targets`, [...d.querySelectorAll<HTMLElement>("#mobileParameters .radio-btn")]
      .filter(button => button.getBoundingClientRect().height > 0 && !button.closest('[aria-hidden="true"]'))
      .every(button => button.getBoundingClientRect().height >= 44));
    await size(1920, 1080);
  }
  await size(1920, 1080);
  geometry("desktop restored after mobile parameters", true);
  // Exercise coarse-pointer CSS on the desktop acceptance host. This changes
  // stylesheet conditions only; native touch events and matchMedia are unchanged.
  const pointerRules: Array<{ rule: CSSMediaRule; condition: string }> = [];
  const enableTouchStyles = (rules: CSSRuleList) => {
    for (const rule of rules) {
      if (rule.type === CSSRule.MEDIA_RULE) {
        const mediaRule = rule as CSSMediaRule;
        const condition = mediaRule.conditionText;
        if (/\(pointer:\s*(?:coarse|fine)\)/.test(condition)) {
          pointerRules.push({ rule: mediaRule, condition });
          mediaRule.media.mediaText = condition.replace(/\(pointer:\s*coarse\)/g, "(min-width: 0px)")
            .replace(/\(pointer:\s*fine\)/g, "(max-width: 0px)");
        }
      }
      const children = (rule as CSSGroupingRule).cssRules;
      if (children) enableTouchStyles(children);
    }
  };
  try {
    for (const sheet of d.styleSheets) enableTouchStyles(sheet.cssRules);
    check("coarse-pointer stylesheet branch activated", pointerRules.length > 0);
    for (const theme of ["light", "dark"]) {
      find(`[data-theme-option="${theme}"]`).click();
      for (const [width, height] of [[1024, 768], [1280, 720], [1920, 900]]) {
        await size(width, height);
        methods.setPromptText!("第一行\n第二行\n第三行"); await pause();
        const style = w.getComputedStyle(editor);
        check(`${theme} ${width} touch editor uses 16px text`, parseFloat(style.fontSize) === 16);
        const minimum = 3 * parseFloat(style.lineHeight) + parseFloat(style.paddingTop)
          + parseFloat(style.paddingBottom) + parseFloat(style.borderTopWidth) + parseFloat(style.borderBottomWidth);
        for (const expanded of [false, true]) {
          if (expanded) { find("#promptFindButton").click(); await pause(); }
          editorVisibility(`${theme} ${width} touch, find=${expanded}`);
          check(`${theme} ${width} touch editor retains three lines, find=${expanded}`,
            rect("#promptEditor").height >= minimum - 1 && editor.scrollHeight <= editor.clientHeight + 1,
            { height: rect("#promptEditor").height, minimum, scroll: editor.scrollHeight, client: editor.clientHeight });
        }
        find("#promptFindClose").click(); await pause();
        const pageHeight = find(".dashboard").scrollHeight;
        methods.setPromptText!(Array.from({ length: 20 }, (_, index) => `触屏提示词第 ${index + 1} 行`).join("\n"));
        editor.focus(); await pause();
        editor.scrollTop = editor.scrollHeight;
        check(`${theme} ${width} touch long prompt stays locally scrollable`, d.activeElement === editor
          && editor.scrollTop > 0 && editor.scrollTop + editor.clientHeight >= editor.scrollHeight - 1
          && Math.abs(find(".dashboard").scrollHeight - pageHeight) <= 1);
      }
    }
  } finally {
    for (const { rule, condition } of pointerRules) rule.media.mediaText = condition;
    methods.setPromptText!("");
  }
  await size(1920, 1080);
  geometry("desktop restored after touch stylesheet branch", true);
  await referenceAcceptance();
  await compactAcceptance();
  check("no application or resource errors", errors.length === 0, errors);
  return { passed: failures.length === 0, assertions, failures, measurements, errors };
}

void run().catch(error => ({ passed: false, fatal: error instanceof Error ? error.stack : String(error), failures, measurements, errors }))
  .then(async report => {
    output.textContent = JSON.stringify(report);
    await fetch("/qa-results", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(report) });
  });

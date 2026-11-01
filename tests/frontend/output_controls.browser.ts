/** Real output controls, isolated data, no generation requests. */
import { loadAcceptanceFrame, prepareFixtureOrigin } from "./browser_acceptance";
const frame = document.querySelector<HTMLIFrameElement>("#historyFrame")!;
const output = document.querySelector<HTMLElement>("#results")!;
const customOnly = new URLSearchParams(location.search).has("custom-only");
const errors: string[] = [], failures: Array<{ name: string; detail?: unknown }> = [];
let assertions = 0;
const pause = (ms = 100) => new Promise(resolve => setTimeout(resolve, ms));
function check(name: string, pass: boolean, detail?: unknown) { assertions++; if (!pass) failures.push({ name, detail }); }
async function run() {
  await prepareFixtureOrigin();
  localStorage.clear();
  await loadAcceptanceFrame(frame, "/qa-app", errors);
  const w = frame.contentWindow!, d = frame.contentDocument!;
  const find = <T extends HTMLElement = HTMLElement>(selector: string) => d.querySelector<T>(selector)!;
  const until = async (predicate: () => boolean) => { const end = Date.now() + 15000; while (!predicate()) { if (Date.now() > end) throw new Error("initialization timed out"); await pause(); } };
  await until(() => !!w.__codexImageWebUI?.state.generationCatalog);
  const { methods } = w.__codexImageWebUI;
  const popup = find("#compressionPopover"), button = find("#outputCompressionButton"), range = find<HTMLInputElement>("#compression");
  const input = (selector: string, value: string) => { const e = find<HTMLInputElement>(selector);e.value=value;e.dispatchEvent(new w.Event("input", {bubbles:true}));e.dispatchEvent(new w.Event("change", {bubbles:true})); };
  const visible = () => !popup.classList.contains("hidden");
  const geometry = (name: string) => {
    const r = popup.getBoundingClientRect();
    check(`${name}: open within viewport`, visible() && r.left >= 0 && r.top >= 0 && r.right <= w.innerWidth && r.bottom <= w.innerHeight, { x:r.x,y:r.y,w:r.width,h:r.height });
    check(`${name}: no inner horizontal overflow`, popup.scrollWidth <= popup.clientWidth + 1 && range.getBoundingClientRect().right <= r.right);
    const panel=find('.output-panel'), panelBounds=panel.getBoundingClientRect(), panelStyle=w.getComputedStyle(panel);
    check(`${name}: compact popup stays inside the output panel`,r.width<=240.5&&r.left>=panelBounds.left+parseFloat(panelStyle.paddingLeft)-1&&r.right<=panelBounds.right-parseFloat(panelStyle.paddingRight)+1);
    check(`${name}: compression uses precise 50–100 percent steps`,range.min==='50'&&range.max==='100'&&range.step==='1');
    const hit = d.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2);
    check(`${name}: popup is not clipped or covered`, !!hit && popup.contains(hit));
    const b=button.getBoundingClientRect(), t=find("#transparentBackgroundField").getBoundingClientRect();
    if (popup.classList.contains("output-extra-options")) {
      check(`${name}: extra options share the popup`, popup.contains(find("#transparentBackgroundField")) && popup.contains(range));
    } else {
      check(`${name}: compression and transparency stay side by side`, button.parentElement === find("#transparentBackgroundField").parentElement && Math.abs((b.top+b.bottom)-(t.top+t.bottom)) < 2 && b.right <= t.left);
    }
    check(`${name}: entry group does not overflow`, button.parentElement!.scrollWidth <= button.parentElement!.clientWidth + 1);
    check(`${name}: filled icon and explicit label`, !!button.querySelector("span")?.textContent && w.getComputedStyle(button.querySelector("svg")!).stroke === "none");
    if (!d.body.classList.contains("mobile-ui")) {
      const format=find("#outputFormatGroup").getBoundingClientRect(), moderation=find(".moderation-field .radio-group").getBoundingClientRect();
      check(`${name}: format and moderation share top and bottom`, Math.abs(format.top-moderation.top)<1 && Math.abs(format.bottom-moderation.bottom)<1, {formatTop:format.top,moderationTop:moderation.top,formatBottom:format.bottom,moderationBottom:moderation.bottom});
      check(`${name}: compression fits the existing header height`, find(".output-field-heading").getBoundingClientRect().height<=24);
    }
    check(`${name}: no duplicate pixel row`, !d.querySelector("#pixelPreview"));
    check(`${name}: summary uses multiplication sign`, /\d+ × \d+/.test(find("#executionSummary").textContent || "") && !/\d+x\d+/.test(find("#executionSummary").textContent || ""));
    check(`${name}: protocol size remains unchanged`, /\d+x\d+/.test(JSON.parse(find("#executionSummary").dataset.parameters!)["canvas.size"]));
  };
  if (new URLSearchParams(location.search).has("extras-only")) {
    w.__codexImageI18n.setLocale("zh-CN");
    const transparent = find<HTMLInputElement>("#transparentBackground");
    const resize = async (width: number, height: number) => { frame.style.width = `${width}px`; frame.style.height = `${height}px`; await pause(250); };
    const selectFormat = async (format: string) => { find(`#outputFormatGroup [data-val="${format}"]`).click(); await pause(); };
    for (const theme of ["light", "dark"]) {
      find(`[data-theme-option="${theme}"]`).click();
      for (const [width, height] of [[1512,773], [1280,699]]) {
        await resize(width, height);
        await selectFormat("webp"); input("#compression", "67");
        button.click(); await pause();
        const name = `${theme} ${width}x${height}`;
        geometry(name);
        check(`${name}: icon-only extra-options entry retains accessible name`, w.getComputedStyle(button.querySelector("span")!).display === "none" && button.getAttribute("aria-label") === "额外选项" && button.title === "额外选项");
        const formatBox = find("#outputFormatGroup").getBoundingClientRect(), moderationBox = find("#moderationGroup").getBoundingClientRect();
        const qualityBox = find("#qualityGroup").getBoundingClientRect(), extraBox = button.getBoundingClientRect();
        check(`${name}: format and extra-options together align with quality`, Math.abs(formatBox.left-qualityBox.left)<1 && Math.abs(extraBox.right-qualityBox.right)<1 && Math.abs(extraBox.left-formatBox.right-6)<1 && moderationBox.width>=140, {format:formatBox.width,quality:qualityBox.width,extraRight:extraBox.right,qualityRight:qualityBox.right});
        const quantityBox = find("#quantityGroup").getBoundingClientRect();
        check(`${name}: moderation aligns with quantity`, Math.abs(moderationBox.left-quantityBox.left)<1 && Math.abs(moderationBox.right-quantityBox.right)<1 && Math.abs(find(".moderation-field > span").getBoundingClientRect().left-find(".quantity-field > span").getBoundingClientRect().left)<1);
        check(`${name}: left labels stay close to options without overlap`, [".orientation-field", ".ratio-field", ".quality-field"].every(selector => {const field=find(selector), label=field.querySelector("span")!.getBoundingClientRect(), group=field.querySelector(".radio-group")!.getBoundingClientRect();return group.left-label.right<=6.5 && group.left-label.right>=0;}));
        check(`${name}: popup focuses transparency first`, d.activeElement === transparent);
        if (!transparent.checked) transparent.click();
        check(`${name}: transparency still updates request value`, find<HTMLInputElement>("#background").value === "transparent");
        transparent.focus();
        transparent.dispatchEvent(new w.KeyboardEvent("keydown", {key:"Tab",bubbles:true}));
        check(`${name}: internal Tab keeps both options accessible`, visible());
        range.focus(); range.dispatchEvent(new w.KeyboardEvent("keydown", {key:"Escape",bubbles:true}));
        check(`${name}: Escape restores trigger focus`, !visible() && d.activeElement === button);
        await selectFormat("png"); button.click(); await pause();
        check(`${name}: PNG opens transparency without compression`, visible() && popup.contains(transparent) && range.disabled && find("#compressionField").classList.contains("hidden"));
        await selectFormat("jpeg");
        check(`${name}: JPEG keeps compression and disables transparency`, visible() && !range.disabled && transparent.disabled && !transparent.checked && find<HTMLInputElement>("#background").value !== "transparent");
        await selectFormat("webp");
        check(`${name}: format roundtrip preserves both preferences`, transparent.checked && !transparent.disabled && range.value === "67");
        find("#promptEditor").click();
        check(`${name}: outside click dismisses options`, !visible());
        await selectFormat("png"); button.click(); await pause();
        await resize(1920,1080);
        check(`${name}: resize restores original controls without duplicates`, !visible() && !popup.contains(transparent) && transparent === find("#transparentBackground") && d.querySelectorAll("#transparentBackground").length === 1);
        check(`${name}: PNG resize retains checkbox focus and values`, d.activeElement === transparent && transparent.checked && range.value === "67" && button.classList.contains("hidden"));
        await selectFormat("webp"); button.click(); await pause();
        check(`${name}: normal layout keeps compression-only entry`, visible() && button.textContent?.trim() === "压缩率" && !popup.contains(transparent) && d.activeElement === range);
        range.dispatchEvent(new w.KeyboardEvent("keydown", {key:"Escape",bubbles:true}));
      }
    }
    return {passed:!failures.length&&!errors.length,assertions,failures,errors};
  }
  for (const locale of ["zh-CN", "en"]) {
    w.__codexImageI18n.setLocale(locale);
    for (const theme of ["light", "dark"]) {
      find(`[data-theme-option="${theme}"]`).click();
      for (const [width,height] of [[1920,1080],[1536,864],[1440,900],[1366,768],[1280,600],[1180,768],[1024,768],[390,844],[360,640]]) {
        frame.style.width=`${width}px`;frame.style.height=`${height}px`;await pause(250);
        if (d.body.classList.contains("mobile-ui")) find(".mobile-parameters-button").click();
        for (const format of customOnly ? [] : ["jpeg","webp"]) {
          find(`#outputFormatGroup [data-val="${format}"]`).click();
          button.scrollIntoView({block:"center"});await pause();button.click();await pause();
          const name=`${locale} ${theme} ${width}x${height} ${format}`;
          geometry(name);
          check(`${name}: first available option receives focus`, d.activeElement === (popup.classList.contains("output-extra-options") && format !== "jpeg" ? find("#transparentBackground") : range));
          check(`${name}: transparency behavior retained`, find<HTMLInputElement>("#transparentBackground").disabled === (format==="jpeg"));
          input("#compression", "67");
          check(`${name}: slider updates value`, find("#compressionValue").textContent==="67%");
          input('#compression','49');
          check(`${name}: values below the UI range become 50 percent`,range.value==='50'&&find('#compressionValue').textContent==='50%'&&JSON.parse(find('#executionSummary').dataset.parameters!)['gpt.output_compression']===50);
          input('#compression','100');
          check(`${name}: upper bound is available`,range.value==='100'&&range.style.getPropertyValue('--range-progress')==='100%');
          range.dispatchEvent(new w.KeyboardEvent("keydown", {key:"Escape",bubbles:true}));
          check(`${name}: Escape closes and restores focus`, !visible() && d.activeElement===button);
          find(`#outputFormatGroup [data-val="${format}"]`).dispatchEvent(new w.MouseEvent("dblclick",{bubbles:true}));await pause();
          check(`${name}: double-click entry retained`, visible());
          find('#outputFormatGroup [data-val="png"]').click();await pause();
          if (popup.classList.contains("output-extra-options")) {
            check(`${name}: PNG retains transparency access`, visible() && !button.classList.contains("hidden") && range.disabled && find("#compressionField").classList.contains("hidden"));
            button.click();
          } else check(`${name}: PNG hides entry and closes popup`, !visible() && button.classList.contains("hidden") && range.disabled);
        }
        find('[data-custom-size-mode="custom"]').click();input('#customWidth','3504');input('#customHeight','2336');await pause();
        const customName=`${locale} ${theme} ${width}x${height} custom size`;
        const card=find('#customSize'), pixelRow=find('.custom-size-row'), ratioRow=find('.custom-ratio-control');
        check(`${customName}: fields fit without clipping`,[card,pixelRow,ratioRow].every(element=>element.scrollWidth<=element.clientWidth+1)&&card.scrollHeight<=card.clientHeight+1);
        const panel=find('.output-panel'),style=w.getComputedStyle(panel),contentWidth=panel.clientWidth-parseFloat(style.paddingLeft)-parseFloat(style.paddingRight);
        const pixelInputs=['#customWidth','#customHeight'].map(selector=>find(selector).getBoundingClientRect());
        const ratioInputs=['#customRatioWidth','#customRatioHeight'].map(selector=>find(selector).getBoundingClientRect());
        check(`${customName}: pixel inputs keep a compact equal width`,pixelInputs.every(rect=>rect.width>=80&&rect.width<=100)&&Math.abs(pixelInputs[0].width-pixelInputs[1].width)<1);
        check(`${customName}: ratio inputs are smaller numeric boxes`,ratioInputs.every(rect=>rect.width>=40&&rect.width<=48));
        const mainGroup=find('.custom-size-main').getBoundingClientRect(),ratioGroup=find('.custom-ratio-field').getBoundingClientRect();
        if(contentWidth>=560)check(`${customName}: wide groups align headings and inputs`,Math.abs(mainGroup.top-ratioGroup.top)<1&&Math.abs(pixelInputs[0].top-ratioInputs[0].top)<1,{contentWidth,mainTop:mainGroup.top,ratioTop:ratioGroup.top,pixelTop:pixelInputs[0].top,ratioInputTop:ratioInputs[0].top});
        if(contentWidth<=480)check(`${customName}: narrow groups stack with a shared left edge`,ratioGroup.top>=mainGroup.bottom&&Math.abs(mainGroup.left-ratioGroup.left)<1);
        check(`${customName}: ratio inputs retain accessible names`,['#customRatioWidth','#customRatioHeight'].every(selector=>!!find(selector).getAttribute('aria-label')));
        const firstImage=find<HTMLButtonElement>('#customRatioFromImageButton'),wasDisabled=firstImage.disabled;
        firstImage.disabled=false;await pause();
        check(`${customName}: first-image action fits when available`,ratioRow.scrollWidth<=ratioRow.clientWidth+1&&firstImage.getBoundingClientRect().right<=card.getBoundingClientRect().right&&card.scrollHeight<=card.clientHeight+1,{cardWidth:card.clientWidth,cardHeight:card.clientHeight,contentHeight:card.scrollHeight,mainWidth:find('.custom-size-main').clientWidth,ratioWidth:ratioRow.clientWidth,ratioContentWidth:ratioRow.scrollWidth});
        firstImage.disabled=wasDisabled;
        find('#swapCustomSizeButton').click();
        check(`${customName}: swapping dimensions still works`,find<HTMLInputElement>('#customWidth').value==='2336'&&find<HTMLInputElement>('#customHeight').value==='3504');
        input('#customWidth','17');await pause();
        const suggestion=find<HTMLButtonElement>('#customSizeSuggestion');
        suggestion.scrollIntoView({block:'center'});await pause();
        const suggestionBounds=suggestion.getBoundingClientRect(),suggestionHit=d.elementFromPoint(suggestionBounds.left+suggestionBounds.width/2,suggestionBounds.top+suggestionBounds.height/2);
        check(`${customName}: validation correction remains reachable`,!suggestion.hidden&&!!suggestionHit&&suggestion.contains(suggestionHit));
        suggestion.click();
        check(`${customName}: correction restores valid dimensions`,find('#customWidth').getAttribute('aria-invalid')==='false'&&suggestion.hidden);
        input('#customWidth','3504');input('#customHeight','2336');
        find('[data-custom-size-mode="preset"]').click();await pause();
        if (d.body.classList.contains("mobile-ui")) find("#mobileParameters .drawer-close-button").click();
      }
    }
  }
  if (!customOnly) {
  frame.style.width="1280px";frame.style.height="720px";await pause(250);
  find('#outputFormatGroup [data-val="webp"]').click();button.scrollIntoView({block:"center"});await pause();button.click();await pause();
  const dashboard=find(".dashboard"); dashboard.scrollTop=Math.max(0,dashboard.scrollTop-20);await pause();
  if (visible()) geometry("after dashboard scroll");
  frame.style.width="1024px";frame.style.height="768px";await pause(250);
  if (visible()) geometry("after viewport resize");
  button.scrollIntoView({block:"center"});await pause();if (!visible()) button.click();
  find("#promptEditor").click();await pause();check("outside click dismisses popup", !visible());
  button.scrollIntoView({block:"center"});await pause();button.click();range.dispatchEvent(new w.KeyboardEvent("keydown",{key:"Tab",bubbles:true}));
  check("Tab returns to local control order", !visible() && d.activeElement===button);
  }
  find('[data-custom-size-mode="custom"]').click(); input("#customWidth","17");
  check("custom size error retained next to input", find("#customWidth").getAttribute("aria-invalid")==="true" && !!find("#customSizeHint").textContent && !find<HTMLButtonElement>("#customSizeSuggestion").hidden);
  input("#customWidth","1024");input("#customHeight","1024");
  check("valid custom dimensions clear error and update summary", find("#customWidth").getAttribute("aria-invalid")==="false" && find("#executionSummary").textContent!.includes("1024 × 1024"));
  methods.updateRequestPreview!();
  const seedRecent=async()=>{
    const view=frame.contentWindow!,doc=frame.contentDocument!;
    await until(()=>!!view.__codexImageWebUI?.state.generationCatalog&&!doc.querySelector('#recentAssetList')?.hasAttribute('aria-busy'));
    view.__codexImageWebUI!.state.recentAssets=[{id:'qa-visibility',filename:'QA preview',image_url:"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='16' height='16'/%3E"}];
    view.__codexImageWebUI!.methods.renderRecentAssets!();
    return doc;
  };
  const isRecentHidden=(doc:Document)=>doc.querySelector('#recentAssetDock')!.classList.contains('previews-hidden')&&doc.querySelector('#recentAssetList')!.getAttribute('aria-hidden')==='true'&&doc.querySelector('#recentAssetList')!.hasAttribute('inert');
  let recentDoc=await seedRecent();
  (recentDoc.querySelector('#recentAssetVisibilityToggle') as HTMLButtonElement).click();
  check('recent previews can be hidden',isRecentHidden(recentDoc));
  await loadAcceptanceFrame(frame,'/qa-app?recent-previews=hidden',errors);recentDoc=await seedRecent();
  check('hidden recent previews survive a real reload',isRecentHidden(recentDoc)&&recentDoc.querySelector('#recentAssetVisibilityToggle')!.getAttribute('aria-expanded')==='false');
  (recentDoc.querySelector('#recentAssetVisibilityToggle') as HTMLButtonElement).click();
  await loadAcceptanceFrame(frame,'/qa-app?recent-previews=shown',errors);recentDoc=await seedRecent();
  check('shown recent previews survive a real reload',!isRecentHidden(recentDoc)&&recentDoc.querySelector('#recentAssetVisibilityToggle')!.getAttribute('aria-expanded')==='true');
  check("no runtime errors", errors.length===0,errors);
  return {passed:failures.length===0&&errors.length===0,assertions,failures,errors};
}
void run().catch(error=>({passed:false,assertions,failures,errors:[...errors,String(error)]})).then(async report=>{output.textContent=JSON.stringify(report);await fetch("/qa-results",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(report)});});

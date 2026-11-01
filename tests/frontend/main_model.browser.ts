/** Main-model selection and channel layout on the isolated application fixture. */
import { loadAcceptanceFrame, prepareFixtureOrigin } from "./browser_acceptance";
const frame = document.querySelector<HTMLIFrameElement>("#historyFrame")!;
const output = document.querySelector<HTMLElement>("#results")!;
const errors: string[] = [], failures: Array<{name:string;detail?:unknown}> = [];
let assertions = 0;
const pause = (ms=100) => new Promise(resolve=>setTimeout(resolve,ms));
function check(name:string,condition:boolean,detail?:unknown) {assertions++;if(!condition)failures.push({name,detail});}
async function run() {
  await prepareFixtureOrigin();localStorage.clear();
  localStorage.setItem("codex-image-locale-preference","zh-CN");
  await loadAcceptanceFrame(frame,"/qa-app",errors);
  const w=frame.contentWindow!,d=frame.contentDocument!;
  const find=<T extends HTMLElement=HTMLElement>(selector:string)=>d.querySelector<T>(selector)!;
  const until=async(predicate:()=>boolean)=>{const end=Date.now()+15000;while(!predicate()){if(Date.now()>end)throw new Error("State did not become ready");await pause();}};
  await until(()=>!!w.__codexImageWebUI?.state.generationCatalog);
  const {state,methods}=w.__codexImageWebUI;
  const input=(selector:string,value:string)=>{const field=find<HTMLInputElement|HTMLSelectElement>(selector);field.value=value;field.dispatchEvent(new w.Event("input",{bubbles:true}));field.dispatchEvent(new w.Event("change",{bubbles:true}));};
  methods.openApiSettingsModal!();await until(()=>!!state.apiSettings?.providers.length);
  for (const [name,protocol] of [["QA Images Relay","openai_images"],["QA Responses Relay","openai_responses"]]) {
    find("#addApiProviderButton").click();await pause();
    input("#apiProviderName",name);input("#apiBaseUrl","https://main-models.example.test/v1");input("#apiKey","sk-QA-main-model-only");
    input("[data-binding-protocol]",protocol);await pause();
    input("[data-binding-remote-model]","gpt-image-2");
    await methods.saveApiProviderEdit!();await until(()=>find("#apiProviderEditor").classList.contains("hidden"));
  }
  find("#systemSettingsModalClose").click();await pause();
  const choose=async(label:string)=>{
    const select=find<HTMLSelectElement>("#generationProviderSelect");
    const option=[...select.options].find(option=>option.textContent?.includes(label));
    if(!option)throw new Error(`Missing route: ${label}`);
    input("#generationProviderSelect",option.value);await pause();
  };
  await choose("Codex Responses");
  find("#mainModelToggle").click();await pause();
  check("Terra appears in candidate list",!!d.querySelector('[data-main-model-option="gpt-6.1-terra"]'));
  find('[data-main-model-option="gpt-6.1-terra"]').click();
  check("Terra is selected and persisted",find<HTMLInputElement>("#mainModel").value==="gpt-6.1-terra"&&w.localStorage.getItem("codex-image-main-model")==="gpt-6.1-terra");
  const routes=[['Codex Image',false],['QA Images Relay',false],['Codex Responses',true],['QA Responses Relay',true]] as const;
  if (new URLSearchParams(location.search).has("reference-hints-only")) {
    for (const locale of ["zh-CN", "en"]) {
      w.__codexImageI18n.setLocale(locale);
      for (const [route, responses] of routes) {
        await choose(route);
        const upload = find("#imageUploadSource");
        const subtitle = upload.querySelector<HTMLElement>(".upload-subtitle")!;
        const title = upload.querySelector<HTMLElement>(".upload-title-full")!;
        const expected = locale === "zh-CN"
          ? (responses ? "点击、拖入或粘贴图片与文件" : "点击、拖入或粘贴图片")
          : (responses ? "Click, drop, or paste images and files" : "Click, drop, or paste images");
        check(`${locale} ${route}: file support hint follows protocol`,
          (w.getComputedStyle(subtitle).display !== "none") === responses);
        check(`${locale} ${route}: upload title follows protocol`, title.textContent === expected);
        check(`${locale} ${route}: accessible upload name follows protocol`, upload.getAttribute("aria-label") === expected);
      }
    }
    return {passed: failures.length === 0 && errors.length === 0, assertions, failures, errors};
  }
  for(const locale of ['zh-CN','en']) {
    w.__codexImageI18n.setLocale(locale);
    for(const theme of ['light','dark']) {
      find(`[data-theme-option="${theme}"]`).click();
      for(const [width,height] of [[2560,1440],[1920,1080],[1536,864],[1366,768],[1280,600],[1024,768],[390,844],[360,640]]) {
        frame.style.width=`${width}px`;frame.style.height=`${height}px`;await pause(250);
        if(d.body.classList.contains('mobile-ui'))find('.mobile-parameters-button').click();
        for(const [route,responses] of routes) {
          await choose(route);
          const name=`${locale} ${theme} ${width}x${height} ${route}`;
          const main=find('#mainModelField'),fidelity=find('#promptFidelityField'),group=find('#promptFidelityGroup'),mode=find('#modeSpecificSettings');
          const panel=find('.output-panel'), panelStyle=w.getComputedStyle(panel);
          const panelWidth=panel.clientWidth-parseFloat(panelStyle.paddingLeft)-parseFloat(panelStyle.paddingRight);
          const controls=['#sizeModeGroup','#orientationGroup','#resolutionGroup','#qualityGroup','#quantityGroup'].map(selector=>find(selector));
          check(`${name}: parameter controls and text stay within their bounds`,controls.every(control=>control.scrollWidth<=control.clientWidth+1&&[...control.querySelectorAll<HTMLElement>('button')].every(button=>button.scrollWidth<=button.clientWidth+1)));
          const [size,orientation,resolution,quality,quantity]=controls.map(control=>control.getBoundingClientRect());
          check(`${name}: stacked fields share their left control axis`,Math.abs(size.left-orientation.left)<1&&Math.abs(size.left-quality.left)<1,{panelWidth,size:size.left,orientation:orientation.left,quality:quality.left});
          check(`${name}: right paired controls share their axis`,Math.abs(resolution.left-quantity.left)<1&&Math.abs(resolution.right-quantity.right)<1);
          check(`${name}: paired rows reflow together`,(Math.abs(orientation.top-resolution.top)<1)===(Math.abs(quality.top-quantity.top)<1));
          for(const control of controls) {
            const label=control.parentElement!.querySelector(':scope > span')!;
            const a=label.getBoundingClientRect(),b=control.getBoundingClientRect();
            check(`${name}: ${control.id} label sits directly above its control`,a.bottom<=b.top&&b.top-a.bottom<=9&&Math.abs(a.left-b.left)<=2);
          }
          const ratio=find('#ratioGroup').getBoundingClientRect(),sizeRow=find('.custom-size-control').getBoundingClientRect();
          check(`${name}: ratio grid keeps the full panel width`,Math.abs(ratio.left-sizeRow.left)<1&&Math.abs(ratio.right-size.right)<1);
          check(`${name}: paired fields use the available width without an empty column`,Math.abs(resolution.right-ratio.right)<1&&Math.abs(quantity.right-ratio.right)<1);
          if(width>=1920&&height>=1080) {
            const dashboard=find('.dashboard');
            check(`${name}: wide desktop gains no page scroll`,d.documentElement.scrollHeight<=d.documentElement.clientHeight+1&&dashboard.scrollHeight<=dashboard.clientHeight+1);
          }
          check(`${name}: main model follows Responses protocol`,main.classList.contains('hidden')===!responses&&main.getAttribute('aria-hidden')===String(!responses));
          check(`${name}: no unused-model placeholder`,!d.querySelector('#apiDirectSettingsNotice')&&!mode.textContent!.includes('直接使用所选图像模型生成'));
          check(`${name}: prompt processing remains reachable`,!fidelity.classList.contains('hidden')&&group.querySelectorAll('button').length===3);
          check(`${name}: no horizontal overflow`,mode.scrollWidth<=mode.clientWidth+1);
          check(`${name}: selected model survives route changes`,find<HTMLInputElement>('#mainModel').value==='gpt-6.1-terra');
          if(!responses) {
            const a=mode.getBoundingClientRect(),b=group.getBoundingClientRect(),label=find('.prompt-fidelity-label').getBoundingClientRect();
            check(`${name}: label and options share one row`,Math.abs((label.top+label.bottom)-(b.top+b.bottom))<2&&label.right<=b.left,{labelTop:label.top,labelBottom:label.bottom,groupTop:b.top,groupBottom:b.bottom});
            check(`${name}: options fill the remaining row width`,Math.abs(a.left-label.left)<1&&Math.abs(a.right-b.right)<1);
            check(`${name}: option text stays within its controls`,[...group.querySelectorAll<HTMLElement>('button')].every(button=>button.scrollWidth<=button.clientWidth+1));
            check(`${name}: empty model wrapper takes no space`,find('.model-tool-row').getBoundingClientRect().height===0);
            check(`${name}: hidden model menu is closed`,find('#mainModelOptions').classList.contains('hidden'));
          } else {
            check(`${name}: Responses search capability remains enabled`,!find<HTMLInputElement>('#webSearch').disabled);
            const promptLabel=find('.prompt-fidelity-label').getBoundingClientRect(),mainLabel=main.querySelector('.output-field-heading')!.getBoundingClientRect(),modelInput=find('#mainModel').getBoundingClientRect(),options=group.getBoundingClientRect();
            check(`${name}: both groups put labels above controls`,promptLabel.bottom<=options.top&&mainLabel.bottom<=modelInput.top);
            if(Math.abs(main.getBoundingClientRect().top-fidelity.getBoundingClientRect().top)<1)check(`${name}: parallel control rows align`,Math.abs(modelInput.top-options.top)<1&&Math.abs(modelInput.bottom-options.bottom)<1);
          }
          find('#promptFidelityGroup [data-val="strict"]').click();
          check(`${name}: full-width prompt setting still updates`,find<HTMLSelectElement>('#promptFidelity').value==='strict');
        }
        if(d.body.classList.contains('mobile-ui'))find('#mobileParameters .drawer-close-button').click();
      }
    }
  }
  check('no runtime errors',errors.length===0,errors);
  return {passed:failures.length===0&&errors.length===0,assertions,failures,errors};
}
void run().catch(error=>({passed:false,assertions,failures,errors:[...errors,String(error)]})).then(async report=>{output.textContent=JSON.stringify(report);await fetch('/qa-results',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(report)});});

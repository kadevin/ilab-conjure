/** Controlled latency against synthetic storage; no production service or provider calls. */
import { loadAcceptanceFrame } from './browser_acceptance';
import { DICTIONARIES, LOCALES } from '../../codex_image/webui/frontend/src/i18n/dictionaries';

export async function checkBackupBoundaries(frame: HTMLIFrameElement, errors: string[]) {
  const failures: Array<{name:string;detail?:unknown}>=[];
  let assertions=0;
  const pause=(ms=60)=>new Promise(resolve=>setTimeout(resolve,ms));
  const check=(name:string,condition:boolean,detail?:unknown)=>{assertions++;if(!condition)failures.push({name,detail});};
  const until=async(fn:()=>boolean,name:string)=>{const end=Date.now()+15000;while(!fn()){if(Date.now()>end)throw Error(name);await pause();}};
  let delay: 'backup'|'upload'|'session'|'restore'|null=null, pending=false;
  let release:(()=>void)|undefined, jobId='', sessionId='', postCount=0, chunkCount=0, rejectDelete=false;
  const deletes:string[]=[];
  (window as any).__qaTransferFetch=async(request:RequestInfo|URL,init:RequestInit|undefined,native:typeof fetch)=>{
    const path=new URL(typeof request==='string'?request:request instanceof URL?request.href:request.url,location.href).pathname;
    if (init?.method==='DELETE' && path.startsWith('/api/user-config-')) {
      deletes.push(path);
      if(rejectDelete){rejectDelete=false;return new Response(JSON.stringify({detail:'user_config_transfer_network_error'}),{status:503,headers:{'Content-Type':'application/json'}});}
    }
    if(path==='/api/user-config-backups' && init?.method==='POST') {
      postCount++;
      const response=await native(request,init);jobId=(await response.clone().json()).job.job_id;
      if(delay==='backup'){pending=true;await new Promise<void>(resolve=>release=resolve);}
      return response;
    }
    if(path==='/api/user-config-restores' && init?.method==='POST') {
      const response=await native(request,init);sessionId=(await response.clone().json()).session.session_id;
      if(delay==='session'){pending=true;await new Promise<void>(resolve=>release=resolve);}
      return response;
    }
    if(path.endsWith('/chunks')) {
      chunkCount++;
      if(delay==='upload') {
        pending=true;
        return new Promise<Response>((resolve,reject)=>init?.signal?.addEventListener('abort',()=>reject(new DOMException('Aborted','AbortError')),{once:true}));
      }
    }
    if(delay==='restore' && path.endsWith('/restore') && init?.method==='POST') {
      pending=true;await new Promise<void>(resolve=>release=resolve);
    }
    return native(request,init);
  };
  sessionStorage.clear();
  await loadAcceptanceFrame(frame,'/qa-app?qa-transfer-boundaries=1',errors);
  const w=frame.contentWindow! as Window & typeof globalThis,d=frame.contentDocument!;
  await until(()=>!!w.__codexImageWebUI?.state.generationCatalog,'catalog ready');
  const methods=w.__codexImageWebUI!.methods;
  const find=<T extends HTMLElement=HTMLElement>(s:string)=>d.querySelector<T>(s)!;
  const click=(s:string)=>find(s).click();
  const visible=(s:string)=>!!find(s)?.getBoundingClientRect().height;
  const change=(el:HTMLInputElement)=>{el.dispatchEvent(new w.Event('input',{bubbles:true}));el.dispatchEvent(new w.Event('change',{bubbles:true}));};
  const input=(s:string,value:string)=>{const el=find<HTMLInputElement>(s);el.value=value;change(el);};
  const open=async()=>{methods.openSystemSettingsModal!('storage');await pause(350);click('#openUserConfigBackupButton');await pause(350);};
  const stored=()=>JSON.parse(w.sessionStorage.getItem('ilab-user-config-transfer')||'{}');
  const closeFromNetwork=async()=>{click('#systemSettingsNetworkTab');click('#systemSettingsModalClose');await pause();};
  const chooseFile=(blob:Blob)=>{const transfer=new w.DataTransfer();transfer.items.add(new w.File([blob],'boundary-fixture.zip',{type:'application/zip'}));const file=find<HTMLInputElement>('#userConfigRestoreFile');file.files=transfer.files;change(file);};
  const checkReadyActions = async () => {
    // Check localized action meanings and long labels in the existing narrow popover.
    frame.style.width='390px';frame.style.height='844px';await pause(350);
    for(const locale of LOCALES){
      click('[data-confirm-popover-cancel]');w.__codexImageI18n.setLocale(locale);click('#systemSettingsModalClose');
      await pause();
      const popover=find('.confirm-popover');
      check(`${locale}: close labels stay inside narrow popover`,popover.scrollWidth<=popover.clientWidth+1 && [...popover.querySelectorAll<HTMLElement>('button')].every(button=>button.scrollWidth<=button.clientWidth+1 && button.scrollHeight<=button.clientHeight+1));
      check(`${locale}: localized close actions differ`,find('[data-confirm-popover-cancel]').textContent===DICTIONARIES[locale]['userConfigBackup.keepWorking'] && find('[data-confirm-popover-confirm]').textContent===DICTIONARIES[locale]['userConfigBackup.discardAndClose']);
    }
    click('[data-confirm-popover-cancel]');w.__codexImageI18n.setLocale('zh-CN');
    frame.style.width='1440px';frame.style.height='900px';await pause(350);
  };
  try {
    await open();
    for(const field of d.querySelectorAll<HTMLInputElement>('input[name=userConfigBackupSection]')){field.checked=field.value==='settings';change(field);}
    if (new URLSearchParams(location.search).has('confirm-copy-only')) {
      click('#createUserConfigBackupButton');await until(()=>visible('#downloadUserConfigBackupButton'),'copy check archive');
      click('#systemSettingsModalClose');
      await checkReadyActions();
      click('#systemSettingsModalClose');click('[data-confirm-popover-confirm]');await until(()=>!visible('#systemSettingsModal'),'copy check cleanup');
      return {passed:failures.length===0 && errors.length===0,assertions,failures,errors};
    }
    delay='backup';pending=false;
    click('#createUserConfigBackupButton');click('#createUserConfigBackupButton');
    await until(()=>pending,'delayed create');
    check('pending create disables duplicate submissions',postCount===1 && find<HTMLButtonElement>('#createUserConfigBackupButton').disabled);
    check('restore cannot replace a pending backup request',find<HTMLInputElement>('#userConfigRestoreFile').disabled);
    await closeFromNetwork();
    check('pending create is guarded from another tab',visible('.confirm-popover') && visible('#systemSettingsModal'));
    check('active close uses distinct actions',find('[data-confirm-popover-cancel]').textContent==='继续操作' && find('[data-confirm-popover-confirm]').textContent==='取消任务并关闭');
    click('[data-confirm-popover-cancel]');
    check('keep working preserves request',visible('#systemSettingsModal') && deletes.length===0);
    click('#systemSettingsModalClose');rejectDelete=true;click('[data-confirm-popover-confirm]');await pause();
    check('confirmed close waits for the server job ID',visible('#systemSettingsModal') && deletes.length===0);
    release!();await until(()=>deletes.length===1,'first cleanup');await pause(150);
    check('failed cleanup keeps the job reachable',visible('#systemSettingsModal') && stored().backupJobId===jobId);
    click('#systemSettingsModalClose');click('[data-confirm-popover-confirm]');await until(()=>!visible('#systemSettingsModal'),'retry cleanup closes');
    check('cleanup retry removes exactly the delayed job',deletes.length===2 && deletes.every(path=>path.endsWith(jobId)) && stored().backupJobId===null);
    delay=null;await open();click('#createUserConfigBackupButton');await until(()=>visible('#downloadUserConfigBackupButton'),'archive ready');
    const job=(await (await w.fetch(`/api/user-config-backups/${stored().backupJobId}`)).json()).job;
    const archive=await (await w.fetch(job.download_url)).blob();
    click('#systemSettingsModalClose');await pause();
    check('ready backup explicitly warns of deletion',find('[data-confirm-popover-confirm]').textContent==='删除临时备份并关闭');
    await checkReadyActions();
    click('[data-user-config-view-mode=restore]');delay='upload';pending=false;chooseFile(archive);
    await until(()=>pending,'chunk upload');
    await closeFromNetwork();click('[data-confirm-popover-confirm]');await until(()=>!visible('#systemSettingsModal'),'cancel upload');
    check('cancelled upload has no unhandled errors',errors.length===0,errors);
    check('cancelled upload clears both tracked IDs',stored().restoreSessionId===null && stored().backupJobId===null);
    check('cancelled upload removes its server session',deletes.some(path=>path.endsWith(sessionId)));
    await open();click('[data-user-config-view-mode=restore]');
    check('cancelled upload resets progress and enables file selection',!visible('#userConfigRestoreProgress') && !find<HTMLInputElement>('#userConfigRestoreFile').disabled && !find<HTMLInputElement>('#userConfigRestoreFile').value);
    // Cancellation before the restore-session response must also clean up its late ID.
    delay='session';pending=false;const oldChunks=chunkCount;chooseFile(archive);await until(()=>pending,'session pending');
    await closeFromNetwork();click('[data-confirm-popover-confirm]');await pause();
    check('session creation waits for safe cleanup',visible('#systemSettingsModal'));
    release!();await until(()=>!visible('#systemSettingsModal'),'late session cancelled');
    check('late session is cancelled without uploading data',chunkCount===oldChunks && stored().restoreSessionId===null && deletes.some(path=>path.endsWith(sessionId)));
    delay=null;await open();click('[data-user-config-view-mode=restore]');chooseFile(archive);
    await until(()=>visible('#userConfigRestorePreview'),'restore preview');
    delay='restore';pending=false;click('#startUserConfigRestoreButton');await until(()=>pending,'restore held');
    click('#systemSettingsNetworkTab');await until(()=>!find<HTMLInputElement>('#networkEgressFakeIpDnsFallback').disabled,'network form');await pause(100);
    click('[data-network-egress-mode=custom]');input('#networkEgressCustomProxy','http://127.0.0.1:17999');input('#networkEgressTimeoutMinutes','13');
    click('#systemSettingsStorageTab');click('#userConfigBackupBackButton');input('#settingsOutputRoot','/fixture/unsaved-output');
    click('#systemSettingsApiTab');click('#addApiProviderButton');input('#apiProviderName','Unsaved fixture provider');
    const apiName=find<HTMLInputElement>('#apiProviderName');
    click('#systemSettingsNetworkTab');await pause(100);release!();
    await until(()=>find('#userConfigRestoreResult').textContent?.includes('恢复')===true,'restore complete');await pause(350);
    check('restore preserves the network draft',find<HTMLInputElement>('#networkEgressCustomProxy').value==='http://127.0.0.1:17999' && find<HTMLInputElement>('#networkEgressMode').value==='custom' && find<HTMLInputElement>('#networkEgressTimeoutMinutes').value==='13');
    check('restore preserves storage draft',find<HTMLInputElement>('#settingsOutputRoot').value==='/fixture/unsaved-output');
    check('restore preserves provider editor DOM and draft',apiName===find('#apiProviderName') && apiName.value==='Unsaved fixture provider');
    for(const id of ['networkEgressStatus','settingsStatus','apiSettingsStatus']) check(`${id}: explains preserved edits`,find(`#${id}`).textContent?.includes('未保存')===true,find(`#${id}`).textContent);
    click('#systemSettingsStorageTab');await pause(100);check('storage draft survives a later tab refresh',find<HTMLInputElement>('#settingsOutputRoot').value==='/fixture/unsaved-output');
    click('#systemSettingsApiTab');check('provider draft notice survives switching back',find('#apiSettingsStatus').textContent?.includes('未保存')===true);
    click('#systemSettingsNetworkTab');await pause(100);check('network draft survives a later tab refresh',find<HTMLInputElement>('#networkEgressCustomProxy').value==='http://127.0.0.1:17999');
    // User save is still authoritative; test only a harmless timeout edit on fixture settings.
    click('[data-network-egress-mode=system]');input('#networkEgressCustomProxy','');click('#saveNetworkEgressButton');
    await until(()=>find('#networkEgressStatus').classList.contains('ok'),'explicit network save');
    check('explicit save applies the kept draft',find<HTMLInputElement>('#networkEgressTimeoutMinutes').value==='13' && !find('#networkEgressStatus').textContent?.includes('未保存'));
    click('#systemSettingsModalClose');
    check('no runtime errors',errors.length===0,errors);
  } catch(error) { failures.push({name:'boundary suite completed',detail:String(error)}); }
  return {passed:failures.length===0 && errors.length===0,assertions,failures,errors};
}

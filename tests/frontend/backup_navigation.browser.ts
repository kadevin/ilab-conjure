/** Navigation never cancels transfers; all archives and restores use the isolated fixture. */
export async function checkBackupNavigation(frame: HTMLIFrameElement, errors: string[]) {
  const w = frame.contentWindow! as Window & typeof globalThis;
  const d = frame.contentDocument!;
  const methods = w.__codexImageWebUI!.methods;
  const failures: Array<{name: string; detail?: unknown}> = [];
  let assertions = 0;
  const pause = (ms = 60) => new Promise(resolve => setTimeout(resolve, ms));
  const check = (name: string, condition: boolean, detail?: unknown) => {
    assertions++; if (!condition) failures.push({name, detail});
  };
  const find = <T extends HTMLElement = HTMLElement>(selector: string) => d.querySelector<T>(selector)!;
  const visible = (selector: string) => !!find(selector)?.getBoundingClientRect().height;
  const until = async (condition: () => boolean, name: string) => {
    const end = Date.now() + 15000;
    while (!condition()) { if (Date.now() > end) throw new Error(`Timed out: ${name}`); await pause(); }
  };
  const click = (selector: string) => find(selector).click();
  const change = (field: HTMLInputElement) => field.dispatchEvent(new w.Event('change', {bubbles:true}));
  let opened = 0, disposed = 0, deletions = 0;
  const openController = methods.openUserConfigBackupController!;
  const closeController = methods.closeUserConfigBackupController!;
  methods.openUserConfigBackupController = () => { opened++; return openController(); };
  methods.closeUserConfigBackupController = () => { disposed++; return closeController(); };
  const originalFetch = w.fetch.bind(w);
  let releaseUpload: (() => void) | undefined, releaseRestore: (() => void) | undefined;
  let uploadWaiting = false, restoreWaiting = false, uploadAborted = false;
  w.fetch = (async (request: RequestInfo | URL, init?: RequestInit) => {
    const path = new URL(typeof request === 'string' ? request : request instanceof w.Request ? request.url : String(request), w.location.href).pathname;
    if (/\/api\/user-config-(backups|restores)\//.test(path) && init?.method === 'DELETE') deletions++;
    if (path.endsWith('/chunks')) {
      uploadWaiting = true;
      init?.signal?.addEventListener('abort', () => { uploadAborted = true; });
      await new Promise<void>(resolve => { releaseUpload = resolve; });
    }
    if (path.endsWith('/restore') && init?.method === 'POST') {
      restoreWaiting = true;
      await new Promise<void>(resolve => { releaseRestore = resolve; });
    }
    return originalFetch(request, init);
  }) as typeof w.fetch;
  methods.openSystemSettingsModal!('storage');
  await pause(350);
  const storageScroll = find('#systemSettingsStoragePanel > .system-settings-scroll');
  storageScroll.scrollTop = storageScroll.scrollHeight;
  const oldScroll = storageScroll.scrollTop;
  click('#openUserConfigBackupButton');
  await pause(350);
  check('backup is nested in storage tab panel', find('#userConfigBackupView').parentElement === find('#systemSettingsStoragePanel'));
  check('settings title stays stable', find('#systemSettingsTitle').textContent === '系统设置');
  check('back button belongs to content heading', !!find('#userConfigBackupBackButton').closest('.user-config-child-heading'));
  check('back receives initial keyboard focus', d.activeElement === find('#userConfigBackupBackButton'));
  const gallery = find<HTMLInputElement>('input[name=userConfigBackupSection][value=gallery]');
  gallery.checked = false; change(gallery);
  const switchTabs = async (name: string) => {
    for (const tab of ['api', 'network', 'language', 'storage']) {
      const button = find(`[data-system-settings-tab=${tab}]`);
      check(`${name}: ${tab} tab remains available`, visible(`#${button.id}`) && !button.closest('[inert]'));
      button.click(); await pause(80);
      check(`${name}: ${tab} tab opens directly`, button.getAttribute('aria-selected') === 'true' && visible(`#${button.getAttribute('aria-controls')}`));
      check(`${name}: backup visibility follows storage`, visible('#userConfigBackupView') === (tab === 'storage'));
    }
    check(`${name}: controller is neither restarted nor disposed`, opened === 1 && disposed === 0, {opened,disposed});
    check(`${name}: no cancellation requests`, deletions === 0);
  };
  await switchTabs('idle');
  find('#systemSettingsStorageTab').focus();
  find('#systemSettingsStorageTab').dispatchEvent(new w.KeyboardEvent('keydown',{key:'ArrowLeft',bubbles:true}));
  check('arrow key moves tab selection and focus', d.activeElement === find('#systemSettingsLanguageTab') && visible('#systemSettingsLanguagePanel'));
  find('#systemSettingsLanguageTab').dispatchEvent(new w.KeyboardEvent('keydown',{key:'End',bubbles:true}));
  check('End returns to storage child', d.activeElement === find('#systemSettingsStorageTab') && visible('#userConfigBackupView'));
  check('backup selection survives tab switches', !gallery.checked);
  click('#userConfigBackupBackButton');
  check('back restores storage overview and focus', visible('#openUserConfigBackupButton') && d.activeElement === find('#openUserConfigBackupButton'));
  check('storage overview restores scroll', Math.abs(storageScroll.scrollTop - oldScroll) <= 1);
  click('#openUserConfigBackupButton');
  check('reopening from overview preserves selection without restarting controller', !gallery.checked && opened === 1);
  // Create a real fixture backup. Selecting only settings avoids model/task data.
  for (const field of d.querySelectorAll<HTMLInputElement>('input[name=userConfigBackupSection]')) {
    field.checked = field.value === 'settings'; change(field);
  }
  click('#createUserConfigBackupButton');
  await switchTabs('creating backup');
  await until(() => visible('#downloadUserConfigBackupButton'), 'backup ready after switching tabs');
  check('backup polling reaches ready after navigation', visible('#downloadUserConfigBackupButton'));
  const stored = JSON.parse(w.sessionStorage.getItem('ilab-user-config-transfer')!);
  const jobResponse = await originalFetch(`/api/user-config-backups/${stored.backupJobId}`);
  const jobPayload = await jobResponse.json();
  const job = jobPayload.job ?? jobPayload;
  const blob = await (await originalFetch(job.download_url)).blob();
  check('fixture archive was downloaded', blob.size > 0);
  click('#systemSettingsNetworkTab');
  click('#systemSettingsModalClose');
  await pause();
  check('closing from a different tab guards a ready backup', visible('#systemSettingsModal') && visible('.confirm-popover'));
  click('[data-confirm-popover-cancel]');
  click('#systemSettingsStorageTab');
  click('[data-user-config-view-mode=restore]');
  const file = find<HTMLInputElement>('#userConfigRestoreFile');
  const transfer = new w.DataTransfer();
  transfer.items.add(new w.File([blob], 'fixture-config.zip', {type:'application/zip'}));
  file.files = transfer.files; change(file);
  await until(() => uploadWaiting, 'upload started');
  await switchTabs('uploading');
  click('#systemSettingsNetworkTab'); click('#systemSettingsModalClose'); await pause();
  check('active upload remains guarded when closing from another tab', visible('.confirm-popover') && !uploadAborted);
  click('[data-confirm-popover-cancel]'); click('#systemSettingsStorageTab');
  click('#userConfigBackupBackButton');
  check('back during upload only navigates', visible('#openUserConfigBackupButton') && !visible('.confirm-popover') && !uploadAborted);
  click('#openUserConfigBackupButton');
  check('selected archive survives back and tabs', file.files?.[0]?.name === 'fixture-config.zip');
  releaseUpload!();
  await until(() => visible('#userConfigRestorePreview'), 'restore preview');
  const preview = find('#userConfigRestorePreview').textContent;
  click('[data-user-config-restore-mode=replace]');
  click('#startUserConfigRestoreButton');
  await until(() => visible('#userConfigReplaceConfirmation'), 'replacement confirmation');
  const ack = find<HTMLInputElement>('#userConfigReplaceAcknowledge');
  ack.checked = true; change(ack);
  await switchTabs('confirmation');
  check('replacement choice and acknowledgement survive navigation', ack.checked && visible('#userConfigReplaceConfirmation') && !find<HTMLButtonElement>('#confirmUserConfigReplaceButton').disabled);
  click('#backToUserConfigPreviewButton');
  click('[data-user-config-restore-mode=incremental]');
  check('preview still available', find('#userConfigRestorePreview').textContent === preview);
  click('#startUserConfigRestoreButton');
  await until(() => restoreWaiting, 'restore request pending');
  await switchTabs('restoring');
  check('restore progress remains active after navigation', visible('#userConfigRestoreProgress'));
  releaseRestore!();
  await until(() => visible('#userConfigRestoreResult'), 'fixture restore completed');
  check('restore result appears after returning', !!find('#userConfigRestoreResult').textContent?.trim());
  for (const theme of ['light','dark']) {
    click(`[data-theme-option=${theme}]`);
    for (const [width,height] of [[1512,699],[390,844]]) {
      frame.style.width=`${width}px`; frame.style.height=`${height}px`; await pause(350);
      const panel=find('.system-settings-modal-panel'), tabs=find('#systemSettingsTabs'), view=find('#userConfigBackupView');
      view.scrollTop=view.scrollHeight; await pause();
      const name=`${theme} ${width}`;
      check(`${name}: navigation stays above scrolling content`, tabs.getBoundingClientRect().bottom <= view.getBoundingClientRect().top + 1);
      check(`${name}: modal stays inside viewport`, panel.getBoundingClientRect().bottom <= height && panel.getBoundingClientRect().top >= 0);
      check(`${name}: content has no horizontal overflow`, view.scrollWidth <= view.clientWidth+1);
      const saved=view.scrollTop;
      click('#systemSettingsLanguageTab'); click('#systemSettingsStorageTab'); await pause(350);
      check(`${name}: child scroll survives switching`, Math.abs(view.scrollTop-saved)<=1);
    }
  }
  d.dispatchEvent(new w.KeyboardEvent('keydown',{key:'Escape',bubbles:true}));
  check('Escape returns to overview without closing settings', visible('#systemSettingsModal') && visible('#openUserConfigBackupButton'));
  check('navigation did not cancel or dispose any transfer', deletions===0 && disposed===0 && !uploadAborted);
  click('#systemSettingsNetworkTab'); click('#systemSettingsModalClose'); await pause();
  check('close still guards backup after returning to overview', visible('.confirm-popover'));
  click('[data-confirm-popover-confirm]');
  await until(()=>!visible('#systemSettingsModal'),'confirmed close');
  check('explicit close disposes once', disposed===1);
  w.fetch=originalFetch;
  methods.openUserConfigBackupController=openController;
  methods.closeUserConfigBackupController=closeController;
  return {passed:failures.length===0 && errors.length===0, assertions, failures, errors};
}

import { getLegacyBridge } from "./state";
import { formatTranslation, translate } from "./i18n";
import {
  buildUserConfigBackupRequest,
  buildUserConfigRestoreRequest,
  cancelUserConfigBackup,
  cancelUserConfigRestore,
  createReplacementConfirmation,
  createUserConfigRestore,
  createUserConfigTransferController,
  directDownloadUserConfigBackup,
  emptyUserConfigReplacementGroups,
  readUserConfigSummary,
  startUserConfigRestore,
  updateReplacementConfirmation,
  uploadUserConfigRestore,
  userConfigBackupActionPriority,
  userConfigBackupStatusMessageKey,
  validateUserConfigRestore,
  type ReplacementConfirmationState,
  type UserConfigBackupJob,
  type UserConfigRestoreMode,
  type UserConfigRestoreGroup,
  type UserConfigRestorePreview,
  type UserConfigRestoreResult,
  type UserConfigSection,
} from "./user-config-backup-api";
import {
  applyUserConfigClientPreferences,
  readUserConfigClientPreferences,
} from "./task-notifications";

const ACTIVE_BACKUP_STATUSES = new Set(["queued", "planning", "packing"]);
const SECTION_KEYS: Record<UserConfigSection, string> = {
  chips: "userConfigBackup.sectionChips",
  gallery: "userConfigBackup.sectionGallery",
  templates: "userConfigBackup.sectionTemplates",
  settings: "userConfigBackup.sectionSettings",
};
const GROUP_KEYS: Record<UserConfigRestoreGroup, string> = {
  colors: "userConfigBackup.groupColors",
  prompt_snippets: "userConfigBackup.groupPromptSnippets",
  gallery_items: "userConfigBackup.groupGalleryItems",
  prompt_templates: "userConfigBackup.groupPromptTemplates",
  settings: "userConfigBackup.groupSettings",
};

let initialized = false;
let currentBackupJob: UserConfigBackupJob | null = null;
let currentRestoreSessionId: string | null = null;
let currentPreview: UserConfigRestorePreview | null = null;
let confirmation: ReplacementConfirmationState | null = null;
let restoreMode: UserConfigRestoreMode = "incremental";
let activeUpload: AbortController | null = null;
let restoreApplying = false;

function bridgeElement(name: string): HTMLElement | null {
  const value = getLegacyBridge().els[name];
  return value instanceof HTMLElement ? value : null;
}

function inputElement(name: string): HTMLInputElement | null {
  const value = getLegacyBridge().els[name];
  return value instanceof HTMLInputElement ? value : null;
}

function setHidden(element: HTMLElement | null, hidden: boolean): void {
  if (!element) return;
  element.classList.toggle("hidden", hidden);
  element.hidden = hidden;
  element.setAttribute("aria-hidden", hidden ? "true" : "false");
}

function setStatus(name: string, message: string, state = ""): void {
  const element = bridgeElement(name);
  if (!element) return;
  element.textContent = message;
  element.classList.toggle("ok", state === "ok");
  element.classList.toggle("error", state === "error");
  element.classList.toggle("running", state === "running");
}

function setProgress(name: string, value: number | null): void {
  const element = bridgeElement(name);
  if (!element) return;
  const visible = value !== null;
  element.classList.toggle("hidden", !visible);
  element.classList.toggle("is-indeterminate", value === -1);
  if (!visible) return;
  const percent = value === -1 ? 0 : Math.max(0, Math.min(100, Math.round(value)));
  element.style.setProperty("--user-config-progress", `${percent}%`);
  element.setAttribute("aria-valuenow", String(percent));
  element.setAttribute("aria-busy", value === -1 ? "true" : "false");
}

function setActionPriority(
  button: HTMLElement | null,
  priority: "primary" | "secondary",
): void {
  if (!button) return;
  button.classList.toggle("run-button", priority === "primary");
  button.classList.toggle("ghost-button", priority === "secondary");
}

function syncBackupActionPriority(status: UserConfigBackupJob["status"] | null): void {
  const priority = userConfigBackupActionPriority(status);
  setActionPriority(bridgeElement("createUserConfigBackupButton"), priority.create);
  setActionPriority(bridgeElement("downloadUserConfigBackupButton"), priority.download);
}

function selectedBackupSections(): UserConfigSection[] {
  return Array.from(document.querySelectorAll<HTMLInputElement>(
    '#userConfigBackupSectionList input[name="userConfigBackupSection"]:checked',
  )).map((input) => input.value as UserConfigSection);
}

function selectedRestoreSections(): UserConfigSection[] {
  return Array.from(document.querySelectorAll<HTMLInputElement>(
    '#userConfigRestoreSectionList input[name="userConfigRestoreSection"]:checked',
  )).map((input) => input.value as UserConfigSection);
}

function formatBytes(value: number): string {
  if (!Number.isFinite(value) || value <= 0) return "0 B";
  const units = ["B", "KB", "MB", "GB"];
  const index = Math.min(units.length - 1, Math.floor(Math.log(value) / Math.log(1024)));
  const amount = value / 1024 ** index;
  return `${amount >= 10 || index === 0 ? amount.toFixed(0) : amount.toFixed(1)} ${units[index]}`;
}

function syncBackupSelection(): void {
  const sections = selectedBackupSections();
  const settingsSelected = sections.includes("settings");
  const sensitiveRow = bridgeElement("userConfigIncludeApiKeysRow");
  if (sensitiveRow) sensitiveRow.hidden = !settingsSelected;
  if (!settingsSelected) {
    const includeKeys = inputElement("userConfigIncludeApiKeys");
    if (includeKeys) includeKeys.checked = false;
  }
  const createButton = bridgeElement("createUserConfigBackupButton") as HTMLButtonElement | null;
  if (createButton) createButton.disabled = sections.length === 0 || Boolean(currentBackupJob && ACTIVE_BACKUP_STATUSES.has(currentBackupJob.status));
}

async function loadBackupSummary(): Promise<void> {
  setStatus("userConfigBackupStatus", translate("userConfigBackup.summaryLoading"), "running");
  try {
    const summaries = await readUserConfigSummary();
    for (const summary of summaries) {
      const target = document.querySelector<HTMLElement>(`[data-user-config-summary="${summary.section}"]`);
      if (!target) continue;
      const warningSuffix = summary.warnings.length
        ? ` · ${formatTranslation("userConfigBackup.warningCount", { count: summary.warnings.length })}`
        : "";
      target.textContent = `${formatTranslation("userConfigBackup.itemCount", { count: summary.item_count })} · ${formatBytes(summary.size_bytes)}${warningSuffix}`;
    }
    setStatus("userConfigBackupStatus", "");
  } catch {
    setStatus("userConfigBackupStatus", translate("userConfigBackup.summaryFailed"), "error");
  }
}

function renderBackupJob(job: UserConfigBackupJob): void {
  currentBackupJob = job;
  const active = ACTIVE_BACKUP_STATUSES.has(job.status);
  const ready = job.status === "ready";
  const createButton = bridgeElement("createUserConfigBackupButton") as HTMLButtonElement | null;
  if (createButton) createButton.disabled = active;
  syncBackupActionPriority(job.status);
  setHidden(bridgeElement("cancelUserConfigBackupButton"), !active && !ready);
  setHidden(bridgeElement("downloadUserConfigBackupButton"), !ready);
  if (job.status === "packing") {
    const progress = job.total_bytes > 0 ? job.completed_bytes * 100 / job.total_bytes : -1;
    setProgress("userConfigBackupProgress", progress);
  } else if (active) {
    setProgress("userConfigBackupProgress", -1);
  } else {
    setProgress("userConfigBackupProgress", null);
  }
  const key = userConfigBackupStatusMessageKey(job);
  setStatus("userConfigBackupStatus", translate(key), active ? "running" : ready ? "ok" : "error");
  syncBackupSelection();
}

function openWebConfirm(
  anchor: HTMLElement | null,
  options: {
    title: string;
    message: string;
    confirmText: string;
    danger?: boolean;
    onConfirm: () => void | Promise<void>;
  },
): void {
  const open = getLegacyBridge().methods.openConfirmPopover;
  if (typeof open === "function" && anchor) open(anchor, options);
}

const transferController = createUserConfigTransferController({
  onBackupStatus: renderBackupJob,
  onRestoreStatus: (snapshot) => {
    currentRestoreSessionId = snapshot.session.session_id;
    if (snapshot.result) {
      transferController.clearRestore();
      renderRestoreResult(snapshot.result);
      refreshRestoredSections(snapshot.result);
      return;
    }
    if (snapshot.preview && !currentPreview) renderRestorePreview(snapshot.preview);
  },
  onError: (error) => {
    setStatus("userConfigBackupStatus", translate(error.code), "error");
    setStatus("userConfigRestoreStatus", translate(error.code), "error");
  },
});

async function createBackup(): Promise<void> {
  const sections = selectedBackupSections();
  if (!sections.length) {
    setStatus("userConfigBackupStatus", translate("userConfigBackup.selectAtLeastOne"), "error");
    return;
  }
  const includeApiKeys = inputElement("userConfigIncludeApiKeys")?.checked === true;
  if (includeApiKeys) {
    openWebConfirm(bridgeElement("createUserConfigBackupButton"), {
      title: translate("userConfigBackup.includeApiKeys"),
      message: translate("userConfigBackup.apiKeyConfirm"),
      confirmText: translate("userConfigBackup.create"),
      danger: false,
      onConfirm: () => performCreateBackup(sections, includeApiKeys),
    });
    return;
  }
  await performCreateBackup(sections, includeApiKeys);
}

async function performCreateBackup(
  sections: UserConfigSection[],
  includeApiKeys: boolean,
): Promise<void> {
  try {
    const request = buildUserConfigBackupRequest(
      sections,
      includeApiKeys,
      readUserConfigClientPreferences(localStorage),
    );
    await transferController.startBackup(request);
  } catch (error) {
    const code = error instanceof Error ? error.message : "user_config_backup_failed";
    setStatus("userConfigBackupStatus", translate(code), "error");
  }
}

async function cancelBackup(): Promise<void> {
  if (!currentBackupJob) return;
  try {
    await cancelUserConfigBackup(currentBackupJob.job_id);
  } catch {
    // The next summary refresh remains safe if cleanup raced expiry.
  }
  transferController.clearBackup();
  currentBackupJob = null;
  syncBackupActionPriority(null);
  setProgress("userConfigBackupProgress", null);
  setHidden(bridgeElement("cancelUserConfigBackupButton"), true);
  setHidden(bridgeElement("downloadUserConfigBackupButton"), true);
  setStatus("userConfigBackupStatus", translate("userConfigBackup.cancelled"));
  syncBackupSelection();
}

function downloadBackup(): void {
  if (!currentBackupJob?.download_url) return;
  directDownloadUserConfigBackup(currentBackupJob.download_url);
  syncBackupActionPriority("ready");
  setHidden(bridgeElement("downloadUserConfigBackupButton"), false);
  setHidden(bridgeElement("cancelUserConfigBackupButton"), false);
  setStatus("userConfigBackupStatus", translate("userConfigBackup.downloaded"), "ok");
  syncBackupSelection();
}

function setTransferView(mode: "backup" | "restore"): void {
  bridgeElement("userConfigTransferMode")?.querySelectorAll<HTMLElement>("[data-user-config-view-mode]").forEach((button) => {
    const active = button.dataset.userConfigViewMode === mode;
    button.classList.toggle("active", active);
    button.setAttribute("aria-pressed", active ? "true" : "false");
  });
  const backupPane = bridgeElement("userConfigBackupPane");
  const restorePane = bridgeElement("userConfigRestorePane");
  if (backupPane) {
    backupPane.hidden = mode !== "backup";
    backupPane.setAttribute("aria-hidden", mode === "backup" ? "false" : "true");
  }
  if (restorePane) {
    restorePane.hidden = mode !== "restore";
    restorePane.setAttribute("aria-hidden", mode === "restore" ? "false" : "true");
  }
}

function renderRestorePreview(preview: UserConfigRestorePreview): void {
  currentPreview = preview;
  restoreMode = "incremental";
  confirmation = createReplacementConfirmation(
    preview.archive_sha256,
    preview.sections.map((section) => section.section),
    restoreMode,
  );
  const list = bridgeElement("userConfigRestoreSectionList");
  list?.replaceChildren();
  for (const section of preview.sections) {
    const label = document.createElement("label");
    label.className = "user-config-section-row";
    const input = document.createElement("input");
    input.type = "checkbox";
    input.name = "userConfigRestoreSection";
    input.value = section.section;
    input.checked = true;
    const copy = document.createElement("span");
    const title = document.createElement("strong");
    title.textContent = translate(SECTION_KEYS[section.section]);
    const detail = document.createElement("small");
    detail.textContent = formatTranslation("userConfigBackup.previewSectionCounts", {
      archive: section.archive_count,
      current: section.replace_existing_count,
    });
    const groups = document.createElement("small");
    groups.className = "user-config-group-counts";
    groups.textContent = section.groups.map((group) => formatTranslation(
      "userConfigBackup.previewGroupCounts",
      {
        group: translate(GROUP_KEYS[group.group]),
        archive: group.archive_count,
        current: group.current_count,
      },
    )).join(" · ");
    const blocked = section.groups.filter(
      (group) => group.archive_count === 0 && group.current_count > 0,
    );
    copy.append(title, detail, groups);
    if (blocked.length) {
      const warning = document.createElement("small");
      warning.className = "user-config-empty-replace-warning";
      warning.textContent = blocked.map((group) => formatTranslation(
        "userConfigBackup.emptyReplaceGroup",
        {
          group: translate(GROUP_KEYS[group.group]),
          current: group.current_count,
        },
      )).join(" · ");
      copy.append(warning);
    }
    label.append(input, copy);
    list?.append(label);
  }
  const meta = bridgeElement("userConfigRestoreArchiveMeta");
  if (meta) meta.textContent = formatTranslation("userConfigBackup.archiveMeta", {
    count: preview.sections.length,
    version: preview.format_version,
  });
  setRestoreMode("incremental");
  setHidden(bridgeElement("userConfigRestorePreview"), false);
  setHidden(bridgeElement("userConfigReplaceConfirmation"), true);
  setHidden(bridgeElement("userConfigRestoreResult"), true);
  setStatus("userConfigRestoreStatus", preview.restorable
    ? translate("userConfigBackup.validationReady")
    : translate("userConfigBackup.versionUnsupported"), preview.restorable ? "ok" : "error");
  const start = bridgeElement("startUserConfigRestoreButton") as HTMLButtonElement | null;
  if (start) start.disabled = !preview.restorable;
}

async function chooseRestoreFile(event: Event): Promise<void> {
  const input = event.currentTarget;
  if (!(input instanceof HTMLInputElement) || !input.files?.[0]) return;
  const file = input.files[0];
  await transferController.resume();
  if (currentRestoreSessionId) {
    await cancelUserConfigRestore(currentRestoreSessionId).catch(() => false);
    transferController.clearRestore();
    currentRestoreSessionId = null;
  }
  activeUpload?.abort();
  activeUpload = new AbortController();
  currentPreview = null;
  setHidden(bridgeElement("userConfigRestorePreview"), true);
  setHidden(bridgeElement("userConfigReplaceConfirmation"), true);
  setHidden(bridgeElement("userConfigRestoreResult"), true);
  try {
    setStatus("userConfigRestoreStatus", translate("userConfigBackup.creatingSession"), "running");
    const created = await createUserConfigRestore(file, { signal: activeUpload.signal });
    currentRestoreSessionId = created.session.session_id;
    transferController.trackRestore(created.session.session_id);
    setProgress("userConfigRestoreProgress", 0);
    setStatus("userConfigRestoreStatus", translate("userConfigBackup.uploading"), "running");
    await uploadUserConfigRestore(file, {
      session_id: created.session.session_id,
      upload_chunk_bytes: created.upload_chunk_bytes,
    }, {
      signal: activeUpload.signal,
      onProgress: (uploaded, total) => setProgress("userConfigRestoreProgress", total > 0 ? uploaded * 100 / total : 0),
    });
    setProgress("userConfigRestoreProgress", -1);
    setStatus("userConfigRestoreStatus", translate("userConfigBackup.validating"), "running");
    renderRestorePreview(await validateUserConfigRestore(created.session.session_id, { signal: activeUpload.signal }));
    setProgress("userConfigRestoreProgress", null);
  } catch (error) {
    if (activeUpload.signal.aborted) return;
    const code = error instanceof Error ? error.message : "user_config_restore_failed";
    setStatus("userConfigRestoreStatus", translate(code), "error");
    setProgress("userConfigRestoreProgress", null);
  } finally {
    activeUpload = null;
  }
}

function setRestoreMode(mode: UserConfigRestoreMode): void {
  restoreMode = mode;
  bridgeElement("userConfigRestoreMode")?.querySelectorAll<HTMLElement>("[data-user-config-restore-mode]").forEach((button) => {
    const active = button.dataset.userConfigRestoreMode === mode;
    button.classList.toggle("active", active);
    button.setAttribute("aria-pressed", active ? "true" : "false");
  });
  const copy = bridgeElement("userConfigRestoreModeCopy");
  if (copy) {
    const key = mode === "replace" ? "userConfigBackup.replaceCopy" : "userConfigBackup.incrementalCopy";
    copy.dataset.i18n = key;
    copy.textContent = translate(key);
  }
  if (confirmation) confirmation = updateReplacementConfirmation(confirmation, { mode });
  setHidden(bridgeElement("userConfigReplaceConfirmation"), true);
  setHidden(bridgeElement("userConfigRestorePreview"), false);
  updateRestoreSelection();
}

function updateRestoreSelection(): void {
  if (!confirmation || !currentPreview) return;
  const sections = selectedRestoreSections();
  if (sections.length) confirmation = updateReplacementConfirmation(confirmation, { sections });
  const blocked = restoreMode === "replace"
    ? emptyUserConfigReplacementGroups(currentPreview, sections)
    : [];
  const button = bridgeElement("startUserConfigRestoreButton") as HTMLButtonElement | null;
  if (button) button.disabled = !sections.length || !currentPreview.restorable || blocked.length > 0;
  if (blocked.length) {
    const labels = blocked.map((item) => translate(GROUP_KEYS[item.group])).join("、");
    setStatus("userConfigRestoreStatus", formatTranslation(
      "userConfigBackup.emptyReplaceBlocked",
      { groups: labels },
    ), "error");
  } else {
    setStatus("userConfigRestoreStatus", currentPreview.restorable
      ? translate("userConfigBackup.validationReady")
      : translate("userConfigBackup.versionUnsupported"), currentPreview.restorable ? "ok" : "error");
  }
}

function renderReplaceConfirmation(): void {
  if (!currentPreview || !confirmation) return;
  const sections = selectedRestoreSections();
  if (!sections.length) return;
  const blocked = emptyUserConfigReplacementGroups(currentPreview, sections);
  if (blocked.length) {
    updateRestoreSelection();
    return;
  }
  confirmation = updateReplacementConfirmation(confirmation, { sections, mode: "replace", acknowledged: false });
  const list = bridgeElement("userConfigReplaceImpactList");
  list?.replaceChildren();
  for (const section of currentPreview.sections.filter((item) => sections.includes(item.section))) {
    for (const group of section.groups) {
      const item = document.createElement("li");
      const subject = section.groups.length > 1
        ? `${translate(SECTION_KEYS[section.section])} · ${translate(GROUP_KEYS[group.group])}`
        : translate(SECTION_KEYS[section.section]);
      item.textContent = formatTranslation("userConfigBackup.replaceImpact", {
        section: subject,
        current: group.current_count,
        archive: group.archive_count,
      });
      list?.append(item);
    }
  }
  if (currentPreview.gallery_history_reference_impact > 0) {
    const item = document.createElement("li");
    item.textContent = formatTranslation("userConfigBackup.galleryReferenceImpact", {
      count: currentPreview.gallery_history_reference_impact,
    });
    list?.append(item);
  }
  if (currentPreview.keyed_provider_retention_count > 0) {
    const item = document.createElement("li");
    item.textContent = formatTranslation("userConfigBackup.providerRetention", {
      count: currentPreview.keyed_provider_retention_count,
    });
    list?.append(item);
  }
  const acknowledge = inputElement("userConfigReplaceAcknowledge");
  if (acknowledge) acknowledge.checked = false;
  const confirmButton = bridgeElement("confirmUserConfigReplaceButton") as HTMLButtonElement | null;
  if (confirmButton) confirmButton.disabled = true;
  setHidden(bridgeElement("userConfigRestorePreview"), true);
  setHidden(bridgeElement("userConfigReplaceConfirmation"), false);
  acknowledge?.focus({ preventScroll: true });
}

async function startRestore(): Promise<void> {
  if (!currentPreview || !currentRestoreSessionId) return;
  if (restoreMode === "replace") {
    renderReplaceConfirmation();
    return;
  }
  await applyRestore();
}

async function applyRestore(): Promise<void> {
  if (!currentPreview || !currentRestoreSessionId || !confirmation) return;
  const request = buildUserConfigRestoreRequest(confirmation, currentPreview.preview_revision);
  if (!request) return;
  restoreApplying = true;
  transferController.trackRestore(currentRestoreSessionId);
  setProgress("userConfigRestoreProgress", -1);
  setStatus("userConfigRestoreStatus", translate("userConfigBackup.restoring"), "running");
  setHidden(bridgeElement("userConfigRestorePreview"), true);
  setHidden(bridgeElement("userConfigReplaceConfirmation"), true);
  try {
    const result = await startUserConfigRestore(currentRestoreSessionId, request);
    transferController.clearRestore();
    renderRestoreResult(result);
    refreshRestoredSections(result);
  } catch (error) {
    const code = error instanceof Error ? error.message : "user_config_restore_failed";
    setStatus("userConfigRestoreStatus", translate(code), "error");
    setHidden(bridgeElement("userConfigRestorePreview"), false);
  } finally {
    restoreApplying = false;
    setProgress("userConfigRestoreProgress", null);
  }
}

function renderRestoreResult(result: UserConfigRestoreResult): void {
  const root = bridgeElement("userConfigRestoreResult");
  root?.replaceChildren();
  const title = document.createElement("strong");
  title.textContent = translate("userConfigBackup.restoreComplete");
  root?.append(title);
  for (const section of result.sections) {
    const stats = result.section_stats[section];
    if (!stats) continue;
    const row = document.createElement("p");
    row.textContent = formatTranslation("userConfigBackup.resultCounts", {
      section: translate(SECTION_KEYS[section]),
      added: stats.added,
      replaced: stats.replaced,
      skipped: stats.skipped,
      copies: stats.recovery_copies,
    });
    root?.append(row);
  }
  if (result.restart_required) {
    const restart = document.createElement("p");
    restart.textContent = translate("userConfigBackup.restartRequired");
    root?.append(restart);
  }
  if (result.client_preferences) {
    const applied = applyUserConfigClientPreferences(result.client_preferences, result.mode);
    const bridge = getLegacyBridge();
    bridge.state.taskNotificationSettings = {
      inApp: applied.applied.notifications.in_app,
      system: applied.applied.notifications.system,
    };
    const inApp = bridge.els.taskNotificationInApp as HTMLInputElement | null;
    const system = bridge.els.taskNotificationSystem as HTMLInputElement | null;
    if (inApp) inApp.checked = applied.applied.notifications.in_app;
    if (system) system.checked = applied.applied.notifications.system;
    for (const warning of applied.warnings) {
      const copy = document.createElement("p");
      copy.textContent = translate(warning);
      root?.append(copy);
    }
  }
  setStatus("userConfigRestoreStatus", translate("userConfigBackup.restoreComplete"), "ok");
  setHidden(root, false);
  currentPreview = null;
  confirmation = null;
}

function refreshRestoredSections(result: UserConfigRestoreResult): void {
  const methods = getLegacyBridge().methods;
  const call = (name: string) => {
    const method = methods[name];
    if (typeof method === "function") void method();
  };
  if (result.sections.includes("chips")) {
    call("refreshColorPalette");
    call("refreshPromptSnippets");
  }
  if (result.sections.includes("gallery")) call("refreshGallery");
  if (result.sections.includes("templates")) call("refreshPromptTemplates");
  if (result.sections.includes("settings")) {
    call("refreshSettings");
    call("refreshNetworkEgress");
    call("populateApiSettingsForm");
  }
}

export function openUserConfigBackupController(): void {
  void transferController.resume();
  void loadBackupSummary();
  syncBackupSelection();
}

export function guardUserConfigBackupClose(closeModal = false): boolean {
  if (restoreApplying) {
    window.alert(translate("userConfigBackup.restoreContinues"));
    return true;
  }
  if (activeUpload || (currentBackupJob && ACTIVE_BACKUP_STATUSES.has(currentBackupJob.status))) {
    openWebConfirm(
      closeModal ? bridgeElement("systemSettingsModalClose") : bridgeElement("userConfigBackupBackButton"),
      {
        title: translate("action.confirmQuestion"),
        message: translate("userConfigBackup.closeActiveConfirm"),
        confirmText: translate("action.cancel"),
        onConfirm: async () => {
          activeUpload?.abort();
          activeUpload = null;
          if (currentRestoreSessionId) await cancelUserConfigRestore(currentRestoreSessionId).catch(() => false);
          if (currentBackupJob) await cancelBackup();
          const methods = getLegacyBridge().methods;
          if (closeModal) methods.closeSystemSettingsModal?.({ force: true });
          else methods.closeUserConfigBackupView?.({ force: true });
        },
      },
    );
    return false;
  }
  if (currentBackupJob?.status === "ready") {
    openWebConfirm(
      closeModal ? bridgeElement("systemSettingsModalClose") : bridgeElement("userConfigBackupBackButton"),
      {
        title: translate("action.confirmQuestion"),
        message: translate("userConfigBackup.discardReadyConfirm"),
        confirmText: translate("action.cancel"),
        onConfirm: async () => {
          await cancelBackup();
          const methods = getLegacyBridge().methods;
          if (closeModal) methods.closeSystemSettingsModal?.({ force: true });
          else methods.closeUserConfigBackupView?.({ force: true });
        },
      },
    );
    return false;
  }
  return true;
}

export function closeUserConfigBackupController(): void {
  if (!restoreApplying) transferController.dispose();
}

function bindEvents(): void {
  const els = getLegacyBridge().els;
  els.userConfigTransferMode?.addEventListener("click", (event: Event) => {
    const target = event.target as Element | null;
    const button = target?.closest<HTMLElement>("[data-user-config-view-mode]");
    const mode = button?.dataset.userConfigViewMode;
    if (mode === "backup" || mode === "restore") setTransferView(mode);
  });
  els.userConfigBackupSectionList?.addEventListener("change", syncBackupSelection);
  els.createUserConfigBackupButton?.addEventListener("click", () => void createBackup());
  els.cancelUserConfigBackupButton?.addEventListener("click", () => void cancelBackup());
  els.downloadUserConfigBackupButton?.addEventListener("click", downloadBackup);
  els.userConfigRestoreFile?.addEventListener("change", (event: Event) => void chooseRestoreFile(event));
  els.userConfigRestoreMode?.addEventListener("click", (event: Event) => {
    const target = event.target as Element | null;
    const button = target?.closest<HTMLElement>("[data-user-config-restore-mode]");
    const mode = button?.dataset.userConfigRestoreMode;
    if (mode === "incremental" || mode === "replace") setRestoreMode(mode);
  });
  els.userConfigRestoreSectionList?.addEventListener("change", updateRestoreSelection);
  els.startUserConfigRestoreButton?.addEventListener("click", () => void startRestore());
  els.backToUserConfigPreviewButton?.addEventListener("click", () => {
    if (confirmation) confirmation = updateReplacementConfirmation(confirmation, { acknowledged: false });
    const acknowledge = inputElement("userConfigReplaceAcknowledge");
    if (acknowledge) acknowledge.checked = false;
    const confirmButton = bridgeElement("confirmUserConfigReplaceButton") as HTMLButtonElement | null;
    if (confirmButton) confirmButton.disabled = true;
    setHidden(bridgeElement("userConfigReplaceConfirmation"), true);
    setHidden(bridgeElement("userConfigRestorePreview"), false);
  });
  els.userConfigReplaceAcknowledge?.addEventListener("change", () => {
    const checked = inputElement("userConfigReplaceAcknowledge")?.checked === true;
    if (confirmation) confirmation = updateReplacementConfirmation(confirmation, { acknowledged: checked });
    const button = bridgeElement("confirmUserConfigReplaceButton") as HTMLButtonElement | null;
    if (button) button.disabled = !checked;
  });
  els.confirmUserConfigReplaceButton?.addEventListener("click", () => void applyRestore());
}

export function initUserConfigBackupFeature(): void {
  if (initialized) return;
  initialized = true;
  bindEvents();
  Object.assign(getLegacyBridge().methods, {
    openUserConfigBackupController,
    closeUserConfigBackupController,
    guardUserConfigBackupClose,
  });
}

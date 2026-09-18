import { createHistoryBackupController, estimateHistoryBackup, historyBackupViewState, type HistoryBackupEstimate, type HistoryBackupFilters, type HistoryBackupJob, type HistoryBackupScope } from "./history-backup";
import { createHistoryImportController, type HistoryImportPhase, type HistoryImportPreview, type HistoryImportResult, type HistoryImportSession, type HistoryImportTaskResult } from "./history-import";
import { escapeHtml, setText } from "./history-presentation";
import { formatTranslation, translate } from "./i18n";

export interface HistoryTransferOptions {
  backupFilters(): HistoryBackupFilters;
  selectedTaskIds(): string[];
  refreshAfterImport(): Promise<void>;
  beforeOpenBackup(): void;
}

export function createHistoryTransferUi(options: HistoryTransferOptions) {
  const els = {
    page: document.querySelector<HTMLElement>(".history-page"),
    backupDialog: document.querySelector<HTMLElement>("#historyBackupDialog"),
    backupTitle: document.querySelector<HTMLElement>("#historyBackupTitle"),
    backupScopeHelp: document.querySelector<HTMLElement>("#historyBackupScopeHelp"),
    backupScopeFieldset: document.querySelector<HTMLFieldSetElement>("#historyBackupScopeFieldset"),
    backupScopeEstimate: document.querySelector<HTMLElement>("#historyBackupScopeEstimate"),
    backupScopeState: document.querySelector<HTMLElement>("#historyBackupScopeState"),
    backupSelectedScope: document.querySelector<HTMLInputElement>("#historyBackupScopeSelected"),
    backupProgressRegion: document.querySelector<HTMLElement>("#historyBackupProgressRegion"),
    backupProgressSummary: document.querySelector<HTMLElement>("#historyBackupProgressSummary"),
    backupProgress: document.querySelector<HTMLProgressElement>("#historyBackupProgress"),
    backupStats: document.querySelector<HTMLElement>("#historyBackupStats"),
    backupLive: document.querySelector<HTMLElement>("#historyBackupLive"),
    backupWarning: document.querySelector<HTMLElement>("#historyBackupWarning"),
    backupComplete: document.querySelector<HTMLElement>("#historyBackupComplete"),
    backupStart: document.querySelector<HTMLButtonElement>("#historyBackupStart"),
    backupCancel: document.querySelector<HTMLButtonElement>("#historyBackupCancel"),
    backupDownload: document.querySelector<HTMLButtonElement>("#historyBackupDownload"),
    backupDismiss: document.querySelector<HTMLButtonElement>("#historyBackupDismiss"),
    importDialog: document.querySelector<HTMLElement>("#historyImportDialog"),
    importTitle: document.querySelector<HTMLElement>("#historyImportTitle"),
    importFile: document.querySelector<HTMLInputElement>("#historyImportFile"),
    importProgress: document.querySelector<HTMLProgressElement>("#historyImportProgress"),
    importLive: document.querySelector<HTMLElement>("#historyImportLive"),
    importPreview: document.querySelector<HTMLElement>("#historyImportPreview"),
    importResult: document.querySelector<HTMLElement>("#historyImportResult"),
    importConfirm: document.querySelector<HTMLButtonElement>("#historyImportConfirm"),
    importCancel: document.querySelector<HTMLButtonElement>("#historyImportCancel"),
  };

  let historyBackupReturnFocus: HTMLElement | null = null;

  let historyImportReturnFocus: HTMLElement | null = null;

  let selectedTaskIdsSnapshot: string[] = [];

  let currentBackupJob: HistoryBackupJob | null = null;

  let currentImportPreview: HistoryImportPreview | null = null;

  let currentImportResult: HistoryImportResult | null = null;

  let currentImportPhase: HistoryImportPhase = "idle";

  let resumableImportSession: HistoryImportSession | null = null;

  let historyImportResumePending = false;

  let lastBackupAnnouncement = "";

  let historyBackupDownloaded = false;

  let historyBackupEstimateGeneration = 0;

  const historyBackupEstimates = new Map<HistoryBackupScope["kind"], HistoryBackupEstimate>();

  const historyBackupEstimateStates = new Map<HistoryBackupScope["kind"], "idle" | "loading" | "ready" | "unavailable">();

  function setHistoryTransferHidden(element: HTMLElement | null, hidden: boolean): void {
    if (!element) return;
    element.hidden = hidden;
    element.classList.toggle("hidden", hidden);
  }

  function historyBackupScope(): HistoryBackupScope {
    const selected = els.backupDialog?.querySelector<HTMLInputElement>('input[name="history-backup-scope"]:checked')?.value;
    if (selected === "selected") {
      return { kind: "selected", taskIds: [...selectedTaskIdsSnapshot] };
    }
    if (selected === "all") return { kind: "all" };
    return { kind: "filtered", filters: options.backupFilters() };
  }

  function renderHistoryBackupScopeEstimates(): void {
    if (historyBackupDownloaded) {
      setHistoryTransferHidden(els.backupScopeEstimate, true);
      return;
    }
    for (const kind of ["selected", "filtered", "all"] as const) {
      const target = els.backupDialog?.querySelector<HTMLElement>(
        `[data-history-backup-scope-count="${kind}"]`,
      ) || null;
      const estimate = historyBackupEstimates.get(kind);
      const state = historyBackupEstimateStates.get(kind) || "idle";
      const text = estimate
        ? formatTranslation("historyBackup.scopeCount", {
          eligible: estimate.eligible_tasks,
          total: estimate.total_tasks,
        })
        : state === "loading"
          ? translate("historyBackup.scopeCounting")
          : state === "unavailable"
            ? translate("historyBackup.scopeCountUnavailable")
            : kind === "selected" && selectedTaskIdsSnapshot.length === 0
              ? translate("historyBackup.scopeNoneSelected")
              : "";
      setText(target, text);
    }

    const locked = historyBackupViewState(currentBackupJob).scopeLocked;
    setHistoryTransferHidden(els.backupScopeEstimate, locked);
    if (locked) {
      setText(els.backupScopeEstimate, "");
      return;
    }
    const kind = historyBackupScope().kind;
    const estimate = historyBackupEstimates.get(kind);
    const state = historyBackupEstimateStates.get(kind) || "idle";
    if (estimate) {
      setText(els.backupScopeEstimate, formatTranslation("historyBackup.willBackup", {
        eligible: estimate.eligible_tasks,
        excluded: estimate.excluded_nonterminal,
      }));
    } else if (kind === "selected" && selectedTaskIdsSnapshot.length === 0) {
      setText(els.backupScopeEstimate, translate("historyBackup.selectTasksFirst"));
    } else if (state === "unavailable") {
      setText(els.backupScopeEstimate, translate("historyBackup.scopeCountUnavailable"));
    } else {
      setText(els.backupScopeEstimate, translate("historyBackup.scopeCounting"));
    }
  }

  async function loadHistoryBackupScopeEstimates(): Promise<void> {
    const generation = ++historyBackupEstimateGeneration;
    historyBackupEstimates.clear();
    historyBackupEstimateStates.clear();
    const scopes: HistoryBackupScope[] = [
      { kind: "filtered", filters: options.backupFilters() },
      { kind: "all" },
    ];
    if (selectedTaskIdsSnapshot.length) {
      scopes.unshift({ kind: "selected", taskIds: [...selectedTaskIdsSnapshot] });
    } else {
      historyBackupEstimateStates.set("selected", "idle");
    }
    for (const scope of scopes) historyBackupEstimateStates.set(scope.kind, "loading");
    renderHistoryBackupScopeEstimates();
    await Promise.all(scopes.map(async (scope) => {
      try {
        const estimate = await estimateHistoryBackup(scope);
        if (generation !== historyBackupEstimateGeneration) return;
        historyBackupEstimates.set(scope.kind, estimate);
        historyBackupEstimateStates.set(scope.kind, "ready");
      } catch {
        if (generation !== historyBackupEstimateGeneration) return;
        historyBackupEstimateStates.set(scope.kind, "unavailable");
      }
      if (generation === historyBackupEstimateGeneration) renderHistoryBackupScopeEstimates();
    }));
  }

  function formatHistoryBytes(value: number | undefined): string {
    const bytes = Number(value || 0);
    if (!Number.isFinite(bytes) || bytes <= 0) return "0 B";
    const units = ["B", "KiB", "MiB", "GiB", "TiB"];
    const index = Math.min(units.length - 1, Math.floor(Math.log(bytes) / Math.log(1024)));
    return `${(bytes / (1024 ** index)).toFixed(index ? 1 : 0)} ${units[index]}`;
  }

  function historyBackupStatusText(job: HistoryBackupJob): string {
    const key = `historyBackup.${job.status}`;
    return translate(key);
  }

  function historyBackupErrorText(code: string): string {
    if (code.includes("space") || code.includes("disk")) return translate("historyBackup.errorDisk");
    if (code.includes("source") || code.includes("changed")) return translate("historyBackup.errorSourceChanged");
    if (code.includes("empty") || code.includes("eligible")) return translate("historyBackup.errorEmpty");
    return translate("historyBackup.errorIo");
  }

  function focusHistoryTransferError(kind: "backup" | "import", message: string): void {
    const summary = kind === "backup" ? els.backupLive : els.importLive;
    setText(summary, message);
    if (summary && !(kind === "backup" ? els.backupDialog : els.importDialog)?.hidden) {
      summary.focus();
    }
  }

  function isTransientHistoryBackupError(status: number): boolean {
    return status === 0 || status === 408 || status === 429 || status >= 500;
  }

  function historyBackupScopeText(kind: HistoryBackupScope["kind"] | undefined): string {
    if (kind === "selected") return translate("historyBackup.scopeSelected");
    if (kind === "filtered") return translate("historyBackup.scopeFiltered");
    if (kind === "all") return translate("historyBackup.scopeAll");
    return translate("historyBackup.scopeLockedUnknown");
  }

  function renderHistoryBackupLockedScope(job: HistoryBackupJob | null): void {
    const locked = historyBackupViewState(job).scopeLocked;
    setHistoryTransferHidden(els.backupScopeState, !locked);
    if (!job || !locked) {
      setText(els.backupScopeState, "");
      return;
    }
    const countsKnown = Number(job.total_tasks || 0) > 0
      || !["queued", "planning"].includes(job.status);
    setText(els.backupScopeState, formatTranslation(
      countsKnown ? "historyBackup.scopeLocked" : "historyBackup.scopeLockedPending",
      {
        scope: historyBackupScopeText(job.scope_kind),
        eligible: Number(job.eligible_tasks || 0),
      },
    ));
  }

  function renderHistoryBackupJob(job: HistoryBackupJob | null): void {
    currentBackupJob = job;
    if (historyBackupDownloaded) {
      setHistoryTransferHidden(els.backupScopeFieldset, true);
      setHistoryTransferHidden(els.backupScopeHelp, true);
      setHistoryTransferHidden(els.backupScopeEstimate, true);
      setHistoryTransferHidden(els.backupScopeState, true);
      setHistoryTransferHidden(els.backupProgressSummary, true);
      setHistoryTransferHidden(els.backupWarning, true);
      setHistoryTransferHidden(els.backupComplete, false);
      setHistoryTransferHidden(els.backupStart, true);
      setHistoryTransferHidden(els.backupCancel, true);
      setHistoryTransferHidden(els.backupDownload, true);
      setHistoryTransferHidden(els.backupDismiss, false);
      els.backupDismiss?.classList.remove("ghost-button");
      els.backupDismiss?.classList.add("run-button");
      if (els.backupDismiss) els.backupDismiss.dataset.i18n = "historyBackup.closePanel";
      setText(els.backupDismiss, translate("historyBackup.closePanel"));
      return;
    }
    setHistoryTransferHidden(els.backupScopeFieldset, false);
    setHistoryTransferHidden(els.backupScopeHelp, false);
    setHistoryTransferHidden(els.backupProgressSummary, false);
    setHistoryTransferHidden(els.backupComplete, true);
    els.backupDismiss?.classList.remove("run-button");
    els.backupDismiss?.classList.add("ghost-button");
    const view = historyBackupViewState(job);
    const missingInputWarning = job && Number(job.missing_input_files || 0) > 0
      ? formatTranslation("historyBackup.missingInputsWarning", {
        tasks: Number(job.tasks_with_missing_inputs || 0),
        files: Number(job.missing_input_files || 0),
      })
      : "";
    setHistoryTransferHidden(els.backupWarning, !missingInputWarning);
    setText(els.backupWarning, missingInputWarning);
    setHistoryTransferHidden(els.backupStart, view.active || view.ready);
    setHistoryTransferHidden(els.backupCancel, !view.active);
    setHistoryTransferHidden(els.backupDownload, !view.ready);
    setHistoryTransferHidden(els.backupDismiss, !view.dismissible);
    const dismissKey = view.ready ? "historyBackup.discard" : "historyBackup.dismiss";
    if (els.backupDismiss) els.backupDismiss.dataset.i18n = dismissKey;
    setText(els.backupDismiss, translate(dismissKey));
    if (els.backupScopeFieldset) els.backupScopeFieldset.disabled = view.scopeLocked;
    renderHistoryBackupLockedScope(job);
    renderHistoryBackupScopeEstimates();
    setHistoryTransferHidden(els.backupProgressRegion, view.progressMode === "hidden");
    if (els.backupProgress) {
      if (view.progressMode === "indeterminate") {
        els.backupProgress.removeAttribute("value");
      } else {
        els.backupProgress.value = view.progressValue;
      }
    }
    if (!job) {
      setText(els.backupStats, "");
      setText(els.backupLive, translate("historyBackup.idle"));
      return;
    }
    const totalBytes = Number(job.total_bytes || 0);
    const completedBytes = Number(job.completed_bytes || 0);
    setText(els.backupStats, formatTranslation("historyBackup.stats", {
      total: job.total_tasks || 0,
      eligible: job.eligible_tasks || 0,
      excluded: job.excluded_nonterminal || 0,
      bytes: `${formatHistoryBytes(completedBytes)} / ${formatHistoryBytes(totalBytes)}`,
    }));
    const statusAnnouncement = job.status === "failed"
      ? historyBackupErrorText(String(job.error_code || ""))
      : job.status === "ready"
        ? translate("historyBackup.readyDetail")
        : historyBackupStatusText(job);
    const announcement = missingInputWarning
      ? `${statusAnnouncement} ${missingInputWarning}`
      : statusAnnouncement;
    if (announcement !== lastBackupAnnouncement) {
      setText(els.backupLive, announcement);
      lastBackupAnnouncement = announcement;
    }
  }

  function renderHistoryBackupDownloaded(): void {
    historyBackupDownloaded = true;
    currentBackupJob = null;
    renderHistoryBackupJob(null);
    lastBackupAnnouncement = translate("historyBackup.downloaded");
    els.backupComplete?.focus();
  }

  function restoreHistoryDialogFocus(kind: "backup" | "import"): void {
    const target = kind === "backup" ? historyBackupReturnFocus : historyImportReturnFocus;
    target?.focus();
    if (kind === "backup") historyBackupReturnFocus = null;
    else historyImportReturnFocus = null;
  }

  function syncHistoryTransferModalState(): void {
    const backupOpen = Boolean(els.backupDialog && !els.backupDialog.hidden);
    const importOpen = Boolean(els.importDialog && !els.importDialog.hidden);
    if (els.page) els.page.inert = backupOpen || importOpen;
  }

  function activeHistoryTransferDialog(): HTMLElement | null {
    if (els.backupDialog && !els.backupDialog.hidden) return els.backupDialog;
    if (els.importDialog && !els.importDialog.hidden) return els.importDialog;
    return null;
  }

  function trapHistoryTransferFocus(event: KeyboardEvent): boolean {
    if (event.key !== "Tab") return false;
    const dialog = activeHistoryTransferDialog();
    if (!dialog) return false;
    const panel = dialog.querySelector<HTMLElement>(".history-transfer-panel[tabindex]");
    const focusable = [...dialog.querySelectorAll<HTMLElement>(
      'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])',
    )].filter((element) => !element.hidden && !element.closest("[hidden]") && element.getAttribute("aria-hidden") !== "true");
    if (!focusable.length) {
      event.preventDefault();
      panel?.focus();
      return true;
    }
    const first = focusable[0]!;
    const last = focusable[focusable.length - 1]!;
    const active = document.activeElement;
    if (event.shiftKey && (active === first || !dialog.contains(active))) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && (active === last || !dialog.contains(active))) {
      event.preventDefault();
      first.focus();
    }
    return true;
  }

  function closeHistoryBackupDialog(options: { restoreFocus?: boolean } = {}): void {
    if (!els.backupDialog) return;
    historyBackupDownloaded = false;
    historyBackupEstimateGeneration += 1;
    setHistoryTransferHidden(els.backupDialog, true);
    els.backupDialog.setAttribute("aria-hidden", "true");
    syncHistoryTransferModalState();
    if (options.restoreFocus !== false) restoreHistoryDialogFocus("backup");
  }

  function openHistoryBackupDialog(trigger: HTMLElement, taskIds: readonly string[], preferSelected = false): void {
    if (els.importDialog && !els.importDialog.hidden) closeHistoryImportDialog({ restoreFocus: false });
    historyBackupReturnFocus = trigger;
    selectedTaskIdsSnapshot = [...taskIds];
    const selectedCount = selectedTaskIdsSnapshot.length;
    if (els.backupSelectedScope) {
      els.backupSelectedScope.disabled = selectedCount === 0;
      els.backupSelectedScope.checked = preferSelected && selectedCount > 0;
    }
    if (!els.backupSelectedScope?.checked) {
      const filtered = els.backupDialog?.querySelector<HTMLInputElement>('input[name="history-backup-scope"][value="filtered"]');
      if (filtered) filtered.checked = true;
    }
    setHistoryTransferHidden(els.backupDialog, false);
    els.backupDialog?.setAttribute("aria-hidden", "false");
    syncHistoryTransferModalState();
    renderHistoryBackupJob(currentBackupJob);
    if (historyBackupViewState(currentBackupJob).scopeLocked) {
      historyBackupEstimateGeneration += 1;
      historyBackupEstimates.clear();
      historyBackupEstimateStates.clear();
      renderHistoryBackupScopeEstimates();
    } else {
      void loadHistoryBackupScopeEstimates();
    }
    els.backupTitle?.focus();
  }

  function importGroupItems(preview: HistoryImportPreview, group: string): HistoryImportTaskResult[] {
    if (group === "restorable") return preview.restorable || [];
    if (group === "duplicate") return preview.duplicate || [];
    if (group === "conflict") return preview.conflict || [];
    return preview.invalid || [];
  }

  const HISTORY_IMPORT_SENSITIVE_REASONS = new Set([
    "backup_import_metadata_contains_sensitive_fields",
    "backup_import_request_contains_sensitive_fields",
  ]);

  const HISTORY_IMPORT_MISMATCH_REASONS = new Set([
    "backup_import_task_fingerprint_mismatch",
    "backup_import_task_id_mismatch",
  ]);

  const HISTORY_IMPORT_INVALID_REASONS = new Set([
    "backup_import_local_task_invalid", "backup_import_raster_invalid",
    "backup_import_reference_file_invalid", "backup_import_task_fingerprint_invalid",
    "backup_import_task_json_invalid", "backup_import_task_json_too_large",
    "backup_import_task_metadata_invalid", "backup_import_task_not_terminal",
    "backup_import_task_organization_invalid", "backup_import_task_required_json_invalid",
    "backup_import_task_required_json_missing",
  ]);

  function historyImportReasonText(reason: string | null | undefined): string {
    if (reason && HISTORY_IMPORT_SENSITIVE_REASONS.has(reason)) return translate("historyImport.reasonSensitive");
    if (reason && HISTORY_IMPORT_MISMATCH_REASONS.has(reason)) return translate("historyImport.reasonMismatch");
    if (reason && HISTORY_IMPORT_INVALID_REASONS.has(reason)) return translate("historyImport.reasonInvalid");
    return translate("historyImport.reasonInvalid");
  }

  function renderHistoryImportPreview(preview: HistoryImportPreview | null): void {
    currentImportPreview = preview;
    setHistoryTransferHidden(els.importPreview, !preview);
    if (!preview || !els.importPreview) {
      if (els.importConfirm) els.importConfirm.disabled = true;
      setHistoryTransferHidden(els.importConfirm, true);
      return;
    }
    for (const group of ["restorable", "duplicate", "conflict", "invalid"]) {
      const details = els.importPreview.querySelector<HTMLElement>(`[data-history-import-group="${group}"]`);
      const items = importGroupItems(preview, group);
      const summary = details?.querySelector<HTMLElement>("summary");
      if (summary) summary.textContent = `${translate(`historyImport.${group}`)} · ${items.length}`;
      const list = details?.querySelector<HTMLOListElement>("ol");
      if (list) list.innerHTML = items.map((item) => `<li><code>${escapeHtml(item.task_id)}</code>${item.reason ? ` <span class="history-import-reason">${escapeHtml(historyImportReasonText(item.reason))}</span>` : ""}</li>`).join("");
    }
    const canRestore = preview.restorable.length > 0;
    if (els.importConfirm) els.importConfirm.disabled = !canRestore;
    setHistoryTransferHidden(els.importConfirm, false);
    setHistoryTransferHidden(els.importCancel, false);
  }

  function renderHistoryImportResult(result: HistoryImportResult | null): void {
    currentImportResult = result;
    setHistoryTransferHidden(els.importResult, !result);
    if (!result || !els.importResult) return;
    const values: Record<string, HistoryImportTaskResult[] | undefined> = {
      restored: result.restored, duplicates: result.duplicates, conflicts: result.conflicts,
      invalid: result.invalid, failed: result.failed, thumbnail_warnings: result.thumbnail_warnings,
      cleanup_warnings: result.cleanup_warnings,
    };
    for (const [key, items] of Object.entries(values)) {
      setText(els.importResult.querySelector<HTMLElement>(`[data-history-import-result="${key}"] dd`), String(items?.length || 0));
    }
  }

  function historyImportPhaseText(phase: HistoryImportPhase): string {
    const key = phase === "idle"
      ? "historyBackup.idle"
      : phase === "creating"
        ? "historyImport.uploading"
        : `historyImport.${phase}`;
    return translate(key);
  }

  function renderHistoryImportPhase(phase: HistoryImportPhase): void {
    currentImportPhase = phase;
    setText(els.importLive, historyImportPhaseText(phase));
    const restoring = phase === "restoring";
    const cancellable = ["creating", "uploading", "validating", "validated"].includes(phase);
    setHistoryTransferHidden(els.importCancel, !cancellable || restoring);
    if (els.importFile) els.importFile.disabled = restoring;
  }

  function closeHistoryImportDialog(options: { restoreFocus?: boolean } = {}): void {
    if (!els.importDialog) return;
    setHistoryTransferHidden(els.importDialog, true);
    els.importDialog.setAttribute("aria-hidden", "true");
    syncHistoryTransferModalState();
    if (options.restoreFocus !== false) restoreHistoryDialogFocus("import");
  }

  function openHistoryImportDialog(trigger: HTMLElement): void {
    if (els.backupDialog && !els.backupDialog.hidden) closeHistoryBackupDialog({ restoreFocus: false });
    historyImportReturnFocus = trigger;
    setHistoryTransferHidden(els.importDialog, false);
    els.importDialog?.setAttribute("aria-hidden", "false");
    syncHistoryTransferModalState();
    renderHistoryImportPhase(currentImportPhase);
    renderHistoryImportPreview(currentImportPreview);
    renderHistoryImportResult(currentImportResult);
    els.importTitle?.focus();
  }

  const backupController = createHistoryBackupController({
    onStatus: (job) => renderHistoryBackupJob(job),
    onError: (error) => {
      const message = historyBackupErrorText(error.code);
      if (!isTransientHistoryBackupError(error.status)) {
        currentBackupJob = null;
        renderHistoryBackupJob(null);
      }
      focusHistoryTransferError("backup", message);
    },
  });

  const importController = createHistoryImportController({
    onPhase: (phase) => renderHistoryImportPhase(phase),
    onProgress: (uploaded, total) => {
      if (els.importProgress) els.importProgress.value = total > 0 ? Math.min(100, Math.round(uploaded * 100 / total)) : 0;
    },
  });

  async function startHistoryBackup(): Promise<void> {
    const scope = historyBackupScope();
    if (scope.kind === "selected" && !scope.taskIds.length) return;
    historyBackupDownloaded = false;
    try {
      await backupController.start(scope);
    } catch (error) {
      if (!(error instanceof DOMException && error.name === "AbortError")) {
        focusHistoryTransferError("backup", historyBackupErrorText(String((error as { code?: string })?.code || "")));
      }
    }
  }

  async function cancelActiveHistoryBackup(): Promise<void> {
    try {
      await backupController.cancel();
    } catch (error) {
      focusHistoryTransferError("backup", historyBackupErrorText(String((error as { code?: string })?.code || "")));
    }
  }

  async function dismissHistoryBackupResult(): Promise<void> {
    const job = currentBackupJob;
    if (!job || !els.backupDismiss) return;
    els.backupDismiss.disabled = true;
    try {
      if (await backupController.dismiss(job.job_id)) {
        currentBackupJob = null;
        closeHistoryBackupDialog();
      }
    } catch (error) {
      focusHistoryTransferError("backup", historyBackupErrorText(String((error as { code?: string })?.code || "")));
    } finally {
      els.backupDismiss.disabled = false;
    }
  }

  function clearHistoryImportUI(): void {
    resumableImportSession = null;
    historyImportResumePending = false;
    currentImportPreview = null;
    currentImportResult = null;
    renderHistoryImportPreview(null);
    renderHistoryImportResult(null);
    if (els.importConfirm) els.importConfirm.disabled = true;
    setHistoryTransferHidden(els.importConfirm, true);
    if (els.importFile) {
      els.importFile.value = "";
      els.importFile.disabled = false;
    }
    if (els.importProgress) els.importProgress.value = 0;
  }

  async function cancelActiveHistoryImport(): Promise<boolean> {
    try {
      await importController.cancel();
      clearHistoryImportUI();
      renderHistoryImportPhase("cancelled");
      return true;
    } catch {
      focusHistoryTransferError("import", translate("historyImport.failed"));
      return false;
    }
  }

  async function chooseHistoryImport(file: File): Promise<void> {
    const resumePending = historyImportResumePending;
    currentImportPreview = null;
    currentImportResult = null;
    renderHistoryImportPreview(null);
    renderHistoryImportResult(null);
    try {
      let preview: HistoryImportPreview | null;
      if (historyImportResumePending) {
        preview = await importController.resumeUpload(file, file.name);
      } else {
        if (importController.activeSessionId() && !await cancelActiveHistoryImport()) return;
        preview = await importController.start(file, file.name);
      }
      if (!preview) return;
      historyImportResumePending = false;
      renderHistoryImportPreview(preview);
    } catch (error) {
      if (!(error instanceof DOMException && error.name === "AbortError")) {
        const activeSessionId = importController.activeSessionId();
        historyImportResumePending = Boolean(activeSessionId);
        if (activeSessionId && !resumePending) {
          resumableImportSession = {
            session_id: activeSessionId,
            filename: file.name,
            size_bytes: file.size,
            uploaded_bytes: 0,
            status: "uploading",
          };
        }
        focusHistoryTransferError("import", translate("historyImport.reselect"));
        if (els.importFile) els.importFile.disabled = false;
      }
    }
  }

  async function restoreHistoryImportSelection(): Promise<void> {
    if (!currentImportPreview?.restorable.length) return;
    setHistoryTransferHidden(els.importCancel, true);
    const terminalSessionId = importController.activeSessionId();
    try {
      const result = await importController.restore();
      if (!result) return;
      resumableImportSession = null;
      historyImportResumePending = false;
      renderHistoryImportResult(result);
      renderHistoryImportPreview(null);
      if (terminalSessionId) {
        await importController.acknowledgeTerminalAfterRefresh(
          terminalSessionId,
          options.refreshAfterImport,
        );
      } else {
        await options.refreshAfterImport();
      }
    } catch {
      renderHistoryImportPhase("failed");
      focusHistoryTransferError("import", translate("historyImport.failed"));
    }
  }

  async function resumeHistoryTransfers(): Promise<void> {
    try { await backupController.resume(); } catch { /* retained state remains available */ }
    try {
      const session = await importController.resume();
      if (!session) return;
      resumableImportSession = session;
      if ((session.status === "restored" || session.status === "failed") && session.result) {
        renderHistoryImportResult(session.result);
        renderHistoryImportPreview(null);
        renderHistoryImportPhase(session.status === "failed" ? "failed" : "restored");
        const acknowledged = await importController.acknowledgeTerminalAfterRefresh(
          session.session_id,
          options.refreshAfterImport,
        );
        if (acknowledged) resumableImportSession = null;
      } else if (session.status === "uploaded" || session.status === "validated") {
        const preview = await importController.resumeValidate();
        if (preview) renderHistoryImportPreview(preview);
      } else if (session.status === "uploading") {
        historyImportResumePending = true;
        renderHistoryImportPhase("uploading");
        setText(els.importLive, translate("historyImport.reselect"));
      } else if (session.status === "restored") {
        renderHistoryImportPhase("restored");
      } else {
        renderHistoryImportPhase(session.status === "interrupted" ? "interrupted" : "failed");
      }
    } catch {
      setText(els.importLive, translate("historyImport.failed"));
    }
  }
  function handleClick(target: HTMLElement | null): boolean {
    if (target?.closest("[data-history-close-backup]")) {
      closeHistoryBackupDialog();
      return true;
    }
    if (target?.closest("[data-history-close-import]")) {
      closeHistoryImportDialog();
      return true;
    }
    const openBackup = target?.closest<HTMLElement>("[data-history-open-backup]");
    if (openBackup) {
      const preferSelected = openBackup.dataset.historyOpenBackup === "selected";
      options.beforeOpenBackup();
      openHistoryBackupDialog(openBackup, options.selectedTaskIds(), preferSelected);
      return true;
    }
    const openImport = target?.closest<HTMLElement>("[data-history-open-import]");
    if (openImport) {
      openHistoryImportDialog(openImport);
      return true;
    }
    if (target?.closest("[data-history-start-backup]")) {
      void startHistoryBackup();
      return true;
    }
    if (target?.closest("[data-history-cancel-backup]")) {
      void cancelActiveHistoryBackup();
      return true;
    }
    if (target?.closest("[data-history-download-backup]")) {
      const job = currentBackupJob;
      if (job) {
        try {
          backupController.download(job);
          renderHistoryBackupDownloaded();
        } catch (error) {
          focusHistoryTransferError("backup", historyBackupErrorText(String((error as { code?: string })?.code || "")));
        }
      }
      return true;
    }
    if (target?.closest("[data-history-dismiss-backup]")) {
      if (historyBackupDownloaded) {
        closeHistoryBackupDialog();
        return true;
      }
      void dismissHistoryBackupResult();
      return true;
    }
    if (target?.closest("[data-history-cancel-import]")) {
      if (currentImportPhase !== "restoring") void cancelActiveHistoryImport();
      return true;
    }
    if (target?.closest("[data-history-confirm-import]")) {
      void restoreHistoryImportSelection();
      return true;
    }

    return false;
  }
  function handleChange(target: HTMLElement | null): boolean {
    const backupScopeInput = target?.closest<HTMLInputElement>(
      'input[name="history-backup-scope"]',
    );
    if (backupScopeInput && els.backupDialog?.contains(backupScopeInput)) {
      renderHistoryBackupScopeEstimates();
      return true;
    }
    if (target === els.importFile) {
      const file = els.importFile?.files?.[0];
      if (els.importFile) els.importFile.value = "";
      if (file) void chooseHistoryImport(file);
      return true;
    }

    return false;
  }
  function handleEscape(): boolean {
    if (els.backupDialog && !els.backupDialog.hidden) {
      closeHistoryBackupDialog();
      return true;
    }
    if (els.importDialog && !els.importDialog.hidden) {
      closeHistoryImportDialog();
      return true;
    }

    return false;
  }
  function renderLocale(): void {
    renderHistoryBackupJob(currentBackupJob);
    renderHistoryBackupScopeEstimates();
    renderHistoryImportPhase(currentImportPhase);
    renderHistoryImportPreview(currentImportPreview);
    renderHistoryImportResult(currentImportResult);
  }

  return {
    handleClick,
    handleChange,
    handleEscape,
    renderLocale,
    trapFocus: trapHistoryTransferFocus,
    resume: resumeHistoryTransfers,
    dispose() { backupController.dispose(); importController.dispose(); },
  };
}

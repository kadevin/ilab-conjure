from __future__ import annotations

import unittest
from pathlib import Path
import re
import shutil
import subprocess
import textwrap


def _typescript_function_body(source: str, name: str) -> str:
    marker = f"function {name}"
    start = source.index(marker)
    brace = source.index("{", start)
    depth = 0
    for index in range(brace, len(source)):
        char = source[index]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return source[brace:index + 1]
    raise AssertionError(f"Function body not found: {name}")


class WebUIStaticHistoryTests(unittest.TestCase):
    def test_history_position_restore_uses_guarded_anchor_load_and_throttled_save(self) -> None:
        source = Path("codex_image/webui/frontend/src/history.ts").read_text(
            encoding="utf-8"
        )

        for marker in (
            'from "./history-scroll-memory"',
            'from "./history-position-runtime"',
            "readHistoryLocationSnapshot()",
            "runHistoryPositionBoot({",
            "loadHistoryAnchorPage({",
            "clearHistoryLocationSnapshot",
            "createHistoryPositionSaveController({",
        ):
            self.assertIn(marker, source)

        boot_body = _typescript_function_body(source, "bootHistoryPage")
        self.assertIn("runHistoryPositionBoot({", boot_body)
        self.assertIn("replaceLocation: (url) => window.history.replaceState", boot_body)
        self.assertIn("syncLocation: () =>", boot_body)
        self.assertIn("loadPage: async (options) =>", boot_body)
        self.assertIn("clearSnapshot: clearHistoryLocationSnapshot", boot_body)

        query_body = _typescript_function_body(source, "queryParams")
        self.assertIn("historyTaskPageQuery(", query_body)
        self.assertIn("historyPageQueryInput(cursor, direction, anchorTaskId)", query_body)

        load_start = source.index("async function loadTasks")
        load_end = source.index("\nfunction taskWindowCursor", load_start)
        load_body = source[load_start:load_end]
        self.assertIn(
            "): Promise<HistoryLoadResult> {",
            load_body,
        )
        for marker in (
            "historyState.loading && !reset",
            "loadHistoryAnchorPage({",
            "query: historyPageQueryInput(cursor, direction, anchorTaskId)",
            "request: requestPage",
            "isCurrent: () => requestId === historyState.requestId",
            "render: (tasks) => renderTasks(tasks, { position: \"replace\" })",
            "applyCursors:",
            "requestFrame:",
            "restore:",
            "enableSave:",
        ):
            self.assertIn(marker, load_body)

        save_body = _typescript_function_body(source, "saveCurrentHistoryLocation")
        self.assertLess(
            save_body.index("updateHistoryUrl()"),
            save_body.index("historySnapshotQuery("),
        )
        self.assertIn("saveHistoryLocationSnapshot({", save_body)
        self.assertNotIn("renderTasks", save_body)

        bind_body = _typescript_function_body(source, "bindEvents")
        scroll_start = bind_body.index('els.taskList?.addEventListener("scroll"')
        scroll_end = bind_body.index("}, { passive: true });", scroll_start)
        scroll_body = bind_body[scroll_start:scroll_end]
        self.assertIn("closeHistoryContextMenu()", scroll_body)
        self.assertIn("maybeLoadMoreFromScroll()", scroll_body)
        self.assertIn("historyPositionSaveController.schedule()", scroll_body)
        self.assertNotIn("renderTasks", scroll_body)

        pagehide_start = source.index('window.addEventListener("pagehide"')
        pagehide_end = source.index("}, { once: true });", pagehide_start)
        pagehide_body = source[pagehide_start:pagehide_end]
        self.assertIn("historyPositionSaveController.flush()", pagehide_body)

    def test_history_backup_restore_ui_contracts(self) -> None:
        html = Path("codex_image/webui/static/history.html").read_text(encoding="utf-8")
        source = Path("codex_image/webui/frontend/src/history.ts").read_text(encoding="utf-8")
        action_panel = Path("codex_image/webui/frontend/src/history-action-panel.ts").read_text(encoding="utf-8")
        styles = Path("codex_image/webui/static/styles/90-history.css").read_text(encoding="utf-8")

        for marker in (
            'id="historyBackupDialog"',
            'id="historyImportDialog"',
            'name="history-backup-scope"',
            'value="selected"',
            'value="filtered"',
            'value="all"',
            'id="historyBackupProgress"',
            'id="historyBackupScopeFieldset"',
            'id="historyBackupScopeEstimate"',
            'id="historyBackupProgressRegion"',
            'id="historyBackupComplete"',
            'data-i18n="historyBackup.downloadStartedTitle"',
            'aria-label="备份进度"',
            'id="historyBackupLive"',
            'id="historyBackupWarning"',
            'id="historyBackupLive" class="history-transfer-live" role="status" aria-live="polite" tabindex="-1"',
            'aria-live="polite"',
            'id="historyImportFile"',
            'accept=".zip,application/zip"',
            'id="historyImportPreview"',
            'id="historyImportResult"',
            'id="historyImportLive" class="history-transfer-live" role="status" aria-live="polite" tabindex="-1"',
        ):
            self.assertIn(marker, html)
        self.assertIn('data-history-open-backup', action_panel)
        self.assertIn('data-history-open-import', action_panel)
        for mode in ("images_only", "images_with_prompts"):
            self.assertIn(f'data-history-export-mode="{mode}"', source)
        self.assertNotIn('data-history-export-mode="task_backup"', source)
        self.assertNotIn("data-history-import-overwrite", html.lower())
        self.assertNotRegex(html.lower(), r'<input[^>]+name="[^"]*overwrite')
        self.assertNotIn("覆盖现有", html)

        filters_body = _typescript_function_body(source, "currentHistoryBackupFilters")
        for marker in (
            "q: historyState.q", "month: historyState.month", "mode: historyState.mode",
            'status: ""', "prompt_mode: historyState.prompt_mode", 'size: ""',
            "quality: historyState.quality", "ratio: historyState.ratio",
            "orientation: historyState.orientation", "backend: historyState.backend",
            "provider: historyState.provider", "archived:", "favorite:",
            "tag_ids: [...historyOrganizationFilters.tagIds]", "untagged:",
            "sort: historyState.sort",
        ):
            self.assertIn(marker, filters_body)
        self.assertNotIn("loadedTaskIds", filters_body)
        self.assertIn("MAX_MOUNTED_TASK_CARDS = 300", source)
        for marker in (
            'from "./history-backup"', 'from "./history-import"',
            "createHistoryBackupController", "createHistoryImportController",
            "backupController.resume()", "importController.resume()",
            "backupController.download(job)",
            "await backupController.dismiss",
            "await loadSummary();", "await loadTasks({ reset: true });",
            'event.key !== "Escape"', "restoreHistoryDialogFocus",
        ):
            self.assertIn(marker, source)

        for marker in (
            ".history-backup-dialog", ".history-import-dialog",
            '.history-import-file-field input[type="file"]',
            ".history-import-file-field input[type=\"file\"]::file-selector-button",
            "overflow-wrap: anywhere", "grid-template-columns: 1fr",
            ":focus-visible", "var(--focus-ring)",
            ".history-backup-scopes label:has(input:checked)",
            ".history-backup-scopes[disabled] label",
            ".history-backup-complete",
            "::-webkit-progress-bar", "::-webkit-progress-value", "::-moz-progress-bar",
            "var(--primary-light)",
            "@media (max-width: 520px)",
            "@media (max-width: 440px)",
            "@media (prefers-reduced-motion: reduce)",
        ):
            self.assertIn(marker, styles)

        render_body = _typescript_function_body(source, "renderHistoryBackupJob")
        for marker in (
            "historyBackupViewState(job)",
            "els.backupScopeFieldset.disabled = view.scopeLocked",
            "els.backupProgress.removeAttribute(\"value\")",
            "renderHistoryBackupLockedScope(job)",
            "historyBackup.readyDetail",
            "historyBackup.missingInputsWarning",
        ):
            self.assertIn(marker, render_body)

        downloaded_body = _typescript_function_body(source, "renderHistoryBackupDownloaded")
        self.assertIn("historyBackupDownloaded = true", downloaded_body)
        self.assertIn("renderHistoryBackupJob(null)", downloaded_body)
        bind_body = _typescript_function_body(source, "bindEvents")
        download_branch = bind_body[
            bind_body.index('if (target?.closest("[data-history-download-backup]"))'):
            bind_body.index('if (target?.closest("[data-history-dismiss-backup]"))')
        ]
        self.assertIn("renderHistoryBackupDownloaded()", download_branch)
        self.assertNotIn("closeHistoryBackupDialog()", download_branch)
        dismiss_branch = bind_body[
            bind_body.index('if (target?.closest("[data-history-dismiss-backup]"))'):
            bind_body.index('if (target?.closest("[data-history-cancel-import]"))')
        ]
        self.assertIn("closeHistoryBackupDialog()", dismiss_branch)

    def test_history_backup_filters_never_enumerate_mounted_cards(self) -> None:
        source = Path("codex_image/webui/frontend/src/history.ts").read_text(encoding="utf-8")
        body = _typescript_function_body(source, "historyBackupScope")
        self.assertIn("selectedTaskIdsSnapshot", body)
        self.assertNotIn("historyState.selectedTaskIds", body)
        self.assertIn("currentHistoryBackupFilters()", body)
        self.assertNotIn("loadedTaskIds", body)

    def test_history_backup_selection_is_frozen_without_mutating_live_selection(self) -> None:
        source = Path("codex_image/webui/frontend/src/history.ts").read_text(encoding="utf-8")
        action_panel = Path("codex_image/webui/frontend/src/history-action-panel.ts").read_text(encoding="utf-8")
        open_body = _typescript_function_body(source, "openHistoryBackupDialog")
        bind_body = _typescript_function_body(source, "bindEvents")

        self.assertIn("selectedTaskIdsSnapshot = [...taskIds]", open_body)
        self.assertIn('data-history-open-backup="selected"', action_panel)
        self.assertIn('const preferSelected = openBackup.dataset.historyOpenBackup === "selected"', bind_body)
        self.assertIn("openHistoryBackupDialog(openBackup, [...historyState.selectedTaskIds], preferSelected)", bind_body)
        self.assertNotIn('historyExportMode === "task_backup"', bind_body)
        self.assertNotIn("historyState.selectedTaskIds =", bind_body)

        scope_body = _typescript_function_body(source, "historyBackupScope").replace(
            "querySelector<HTMLInputElement>", "querySelector"
        )
        harness = textwrap.dedent(f"""
            let selectedTaskIdsSnapshot = ["detail-a", "detail-b"];
            const historyState = {{ selectedTaskIds: new Set(["detail-a", "detail-b", "other"]) }};
            const els = {{ backupDialog: {{ querySelector: () => ({{ value: "selected" }}) }} }};
            const currentHistoryBackupFilters = () => ({{}});
            function historyBackupScope() {scope_body}
            historyState.selectedTaskIds.delete("detail-a");
            historyState.selectedTaskIds.clear();
            process.stdout.write(JSON.stringify({{ scope: historyBackupScope(), live: [...historyState.selectedTaskIds] }}));
        """)
        completed = subprocess.run(
            ["node", "--input-type=module", "--eval", harness],
            check=True,
            capture_output=True,
            text=True,
        )
        self.assertEqual(
            completed.stdout,
            '{"scope":{"kind":"selected","taskIds":["detail-a","detail-b"]},"live":[]}',
        )

    def test_history_transfer_cancel_file_reset_and_modal_accessibility_contracts(self) -> None:
        html = Path("codex_image/webui/static/history.html").read_text(encoding="utf-8")
        source = Path("codex_image/webui/frontend/src/history.ts").read_text(encoding="utf-8")

        choose_body = _typescript_function_body(source, "chooseHistoryImport")
        cancel_import_body = _typescript_function_body(source, "cancelActiveHistoryImport")
        cancel_backup_body = _typescript_function_body(source, "cancelActiveHistoryBackup")
        clear_import_body = _typescript_function_body(source, "clearHistoryImportUI")
        modal_body = _typescript_function_body(source, "syncHistoryTransferModalState")
        trap_body = _typescript_function_body(source, "trapHistoryTransferFocus")
        phase_text_body = " ".join(
            _typescript_function_body(source, "historyImportPhaseText").split()
        )
        preview_body = _typescript_function_body(source, "renderHistoryImportPreview")
        reason_body = _typescript_function_body(source, "historyImportReasonText")
        restore_body = _typescript_function_body(source, "restoreHistoryImportSelection")
        resume_body = _typescript_function_body(source, "resumeHistoryTransfers")
        refresh_body = _typescript_function_body(source, "refreshHistoryAfterImport")

        self.assertIn('els.importFile.value = ""', bind_body := _typescript_function_body(source, "bindEvents"))
        self.assertIn('phase === "idle" ? "historyBackup.idle"', phase_text_body)
        self.assertIn('phase === "creating" ? "historyImport.uploading"', phase_text_body)
        self.assertLess(bind_body.index('const file = els.importFile?.files?.[0]'), bind_body.index('els.importFile.value = ""'))
        self.assertIn("await importController.cancel()", cancel_import_body)
        self.assertIn("clearHistoryImportUI()", cancel_import_body)
        self.assertIn("renderHistoryImportPreview(null)", clear_import_body)
        self.assertIn("renderHistoryImportResult(null)", clear_import_body)
        self.assertIn("els.importConfirm.disabled = true", clear_import_body)
        self.assertIn("await backupController.cancel()", cancel_backup_body)
        self.assertIn("focusHistoryTransferError", cancel_import_body + cancel_backup_body + choose_body)
        self.assertIn("historyImportReasonText(item.reason)", preview_body)
        self.assertNotIn("escapeHtml(item.reason)", preview_body)
        self.assertIn('"historyImport.reasonInvalid"', reason_body)
        self.assertIn('"historyImport.reasonSensitive"', reason_body)
        self.assertIn('"historyImport.reasonMismatch"', reason_body)
        self.assertIn('focusHistoryTransferError("import", translate("historyImport.failed"))', restore_body)
        self.assertIn("await refreshHistoryAfterImport", restore_body)
        self.assertIn("await importController.acknowledgeTerminalAfterRefresh", resume_body)
        self.assertIn("await loadSummary({ throwOnError: true })", refresh_body)
        self.assertIn("await loadTasks({ reset: true, throwOnError: true })", refresh_body)
        self.assertIn("if (!isTransientHistoryBackupError(error.status))", source)
        self.assertIn("currentBackupJob = null", source)
        self.assertIn("els.page.inert =", modal_body)
        self.assertIn("backupOpen || importOpen", modal_body)
        self.assertIn("event.shiftKey", trap_body)
        self.assertIn("event.preventDefault()", trap_body)
        self.assertIn('event.key !== "Tab"', trap_body)
        self.assertIn('.history-transfer-panel[tabindex]', trap_body)
        self.assertIn("panel?.focus()", trap_body)
        self.assertNotIn("dialog.focus()", trap_body)
        self.assertIn("syncHistoryTransferModalState()", source)
        self.assertNotIn("data-history-import-overwrite", html)

    def test_history_backup_format_uses_canonical_organization_path_and_size_field(self) -> None:
        source = Path("codex_image/webui/history_backup_format.py").read_text(encoding="utf-8")
        self.assertIn('"organization": "organization.json"', source)
        self.assertIn('"organization": "source"', source)
        self.assertIn('file_data.get("size_bytes")', source)
        self.assertNotIn('file_data.get("bytes")', source)

    def test_history_resume_pending_chooser_never_replaces_the_server_session(self) -> None:
        source = Path("codex_image/webui/frontend/src/history.ts").read_text(encoding="utf-8")
        choose_body = _typescript_function_body(source, "chooseHistoryImport")
        self.assertIn("if (historyImportResumePending)", choose_body)
        self.assertIn("importController.resumeUpload(file, file.name)", choose_body)
        resume_branch = choose_body[
            choose_body.index("if (historyImportResumePending)"):
            choose_body.index("} else {", choose_body.index("if (historyImportResumePending)"))
        ]
        self.assertNotIn("cancelActiveHistoryImport", resume_branch)
        self.assertNotIn("importController.start", resume_branch)

        harness = textwrap.dedent(f"""
            let currentImportPreview = null;
            let currentImportResult = null;
            let historyImportResumePending = true;
            let resumableImportSession = {{
              session_id: "a".repeat(32), filename: "right.zip", size_bytes: 4,
              uploaded_bytes: 2, status: "uploading",
            }};
            const calls = [];
            const renderHistoryImportPreview = () => undefined;
            const renderHistoryImportResult = () => undefined;
            const focusHistoryTransferError = () => undefined;
            const translate = (key) => key;
            const els = {{ importFile: {{ disabled: false }} }};
            const cancelActiveHistoryImport = async () => {{ calls.push("cancel"); return true; }};
            const importController = {{
              activeSessionId: () => "a".repeat(32),
              cancel: async () => calls.push("cancel-controller"),
              start: async (file) => {{ calls.push(`start:${{file.name}}:${{file.size}}`); return {{ restorable: [] }}; }},
              resumeUpload: async (file, filename) => {{
                calls.push(`resume:${{filename}}:${{file.size}}`);
                if (filename !== "right.zip" || file.size !== 4) throw new Error("mismatch");
                return {{ session_id: "a".repeat(32), restorable: [] }};
              }},
            }};
            async function chooseHistoryImport(file: File) {choose_body}
            (async () => {{
              await chooseHistoryImport({{ name: "wrong.zip", size: 4 }} as File);
              const afterWrongName = historyImportResumePending;
              await chooseHistoryImport({{ name: "right.zip", size: 3 }} as File);
              const afterWrongSize = historyImportResumePending;
              await chooseHistoryImport({{ name: "right.zip", size: 4 }} as File);
              process.stdout.write(JSON.stringify({{ calls, afterWrongName, afterWrongSize, finalPending: historyImportResumePending }}));
            }})();
        """)
        esbuild = Path("node_modules/.bin/esbuild")
        compiled = subprocess.run(
            [str(esbuild), "--loader=ts", "--format=esm", "--target=es2020"],
            input=harness,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(compiled.returncode, 0, compiled.stderr)
        completed = subprocess.run(
            ["node", "--input-type=module", "--eval", compiled.stdout],
            check=True,
            capture_output=True,
            text=True,
        )
        self.assertEqual(
            completed.stdout,
            '{"calls":["resume:wrong.zip:4","resume:right.zip:3","resume:right.zip:4"],"afterWrongName":true,"afterWrongSize":true,"finalPending":false}',
        )

    def test_history_realtime_terminal_update_does_not_reset_a_scrolled_window(self) -> None:
        source = Path(
            "codex_image/webui/frontend/src/history.ts"
        ).read_text(encoding="utf-8")
        shell_source = Path(
            "codex_image/webui/frontend/src/history-shell.ts"
        ).read_text(encoding="utf-8")

        boot_body = _typescript_function_body(source, "bootHistoryPage")
        callback_match = re.search(
            r"refreshHistoryTasks:\s*async\s*\((?P<args>[^)]*)\)\s*=>\s*\{(?P<body>[\s\S]*?)\n\s*\},",
            boot_body,
        )
        self.assertIsNotNone(callback_match)
        self.assertIn("task", callback_match.group("args"))
        self.assertIn("refreshHistoryForRealtimeTask", callback_match.group("body"))
        self.assertIn(
            "reloadNewestWindow: async () => {",
            callback_match.group("body"),
        )
        self.assertIn(
            "await loadTasks({ reset: true });",
            callback_match.group("body"),
        )
        self.assertIn("refreshHistoryTasks?.(task)", shell_source)

    def test_history_shell_uses_shared_top_nav_and_compact_sidebar(self) -> None:
        html = Path(
            "codex_image/webui/static/history.html"
        ).read_text(encoding="utf-8")
        source = Path(
            "codex_image/webui/frontend/src/history.ts"
        ).read_text(encoding="utf-8")
        shell_source = Path(
            "codex_image/webui/frontend/src/history-shell.ts"
        ).read_text(encoding="utf-8")
        styles = Path(
            "codex_image/webui/static/styles/90-history.css"
        ).read_text(encoding="utf-8")

        stylesheet_index = html.index(
            '<link rel="stylesheet"'
        )
        theme_script_index = html.index(
            '"codex-image-theme-preference"'
        )
        self.assertLess(theme_script_index, stylesheet_index)
        bootstrap = html[:stylesheet_index]
        for marker in (
            '"system"',
            '"light"',
            '"dark"',
            "localStorage.getItem",
            "window.matchMedia?.",
            "dataset.theme",
            "dataset.themePreference",
        ):
            self.assertIn(marker, bootstrap)
        self.assertIn(
            'class="history-program-brand"',
            html,
        )
        self.assertIn(
            'data-i18n-attr="aria-label:history.homeAria"',
            html,
        )
        self.assertIn('class="brand-rabbit-logo"', html)
        self.assertIn('d="M18.9 5.2v2.4M17.7 6.4h2.4"', html)
        self.assertNotIn('class="history-program-name"', html)
        self.assertIn('class="history-back-link"', html)
        self.assertIn('data-i18n="history.backToGenerator"', html)
        self.assertRegex(
            styles,
            r"\.history-back-link\s*\{[^}]*width:\s*100%[^}]*min-height:\s*44px[^}]*justify-content:\s*center",
        )
        self.assertRegex(
            styles,
            r"\.history-back-link\s*\{[^}]*background:\s*var\(--surface-soft\)[^}]*font-size:\s*13px",
        )
        self.assertRegex(
            styles,
            r"\.history-back-link:focus-visible\s*\{[^}]*outline:\s*2px\s+solid\s+var\(--focus-ring\)",
        )
        self.assertIn('data-i18n="history.title"', html)
        self.assertIn('id="historyTotal"', html)
        for marker in (
            'class="top-nav history-top-nav"',
            'id="queueButton"',
            'id="taskNotificationButton"',
            'id="taskNotificationCenter"',
            'id="themeSwitcher"',
            'id="githubLink"',
            'id="generationProviderSelect"',
            'id="generationProviderSettingsButton"',
            'id="systemSettingsModal"',
            'id="systemSettingsApiTab"',
            'id="systemSettingsNetworkTab"',
            'id="systemSettingsLanguageTab"',
            'id="systemSettingsStorageTab"',
        ):
            self.assertIn(marker, html)
        self.assertNotIn('id="historyThemeSwitcher"', html)
        for value in ("system", "light", "dark"):
            self.assertIn(
                f'data-theme-option="{value}"',
                html,
            )
        self.assertEqual(
            html.count('data-theme-option="'),
            3,
        )
        toolbar = html[
            html.index('<header class="history-toolbar">'):
            html.index("</header>", html.index('<header class="history-toolbar">'))
        ]
        self.assertNotIn("themeSwitcher", toolbar)
        self.assertNotIn("historyThemeSwitcher", toolbar)
        self.assertIn('class="history-search-field"', html)
        self.assertIn(
            'id="historySearchClear" class="history-search-clear hidden"',
            html,
        )
        self.assertIn('class="history-favorite-filter"', html)
        self.assertNotIn(
            'data-history-filter-section="favorite"',
            html,
        )

        for marker in (
            'from "./history-shell"',
            "initializeHistoryShell({",
            "selectHistoryTask: loadTaskDetail",
        ):
            self.assertIn(marker, source)
        for marker in (
            'import "../legacy-app.js";',
            "initTaskNotificationsFeature",
            "initializeQueueFeature",
            "initProviderSelectionFeature",
            "initSystemSettingsFeature",
            "syncReferenceFileAvailability: () => {}",
            "handlePromptDocumentClick: noOp",
            "handleGalleryDocumentClick: noOp",
            "handleImageEditorHistoryShortcut: () => false",
            "closePromptTemplateDrawer: noOp",
            "selectHistoryTask",
            "startRealtimeUpdates",
        ):
            self.assertIn(marker, shell_source)
        self.assertRegex(
            styles,
            r"\.history-program-brand\s*\{[^}]*display:\s*flex",
        )
        self.assertRegex(
            styles,
            r"\.history-program-brand \.brand-mark\s*\{[^}]*width:\s*38px[^}]*height:\s*38px",
        )
        self.assertRegex(
            styles,
            r"\.history-results\s*\{[^}]*--history-toolbar-control-height:\s*36px",
        )
        self.assertNotIn(".history-theme-switcher", styles)

        language_paths = [
            path
            for path in Path(
                "codex_image/webui/frontend/src/i18n"
            ).glob("*.ts")
            if path.name
            not in {"dictionaries.ts", "types.ts"}
        ]
        self.assertEqual(len(language_paths), 14)
        for path in language_paths:
            self.assertIn(
                '"history.homeAria"',
                path.read_text(encoding="utf-8"),
                f"{path.name} misses history.homeAria",
            )
            self.assertIn(
                '"history.backToGenerator"',
                path.read_text(encoding="utf-8"),
                f"{path.name} misses history.backToGenerator",
            )

    def test_history_export_module_uses_server_download_without_blob(
        self,
    ) -> None:
        node = shutil.which("node")
        if node is None:
            self.skipTest(
                "node is required for frontend behavior checks"
            )
        module_path = Path(
            "codex_image/webui/frontend/src/history-export.ts"
        )
        self.assertTrue(module_path.is_file())
        source = module_path.read_text(encoding="utf-8")
        self.assertNotIn(".blob()", source)
        self.assertNotIn("URL.createObjectURL", source)
        harness = textwrap.dedent(
            f"""
            const fs = require("fs");
            const ts = require("typescript");
            const vm = require("vm");
            const source = fs.readFileSync(
              {str(module_path)!r},
              "utf8",
            );
            const code = ts.transpileModule(source, {{
              compilerOptions: {{
                module: ts.ModuleKind.CommonJS,
                target: ts.ScriptTarget.ES2020,
              }},
            }}).outputText;
            let fetchCount = 0;
            let requestBody = null;
            const anchor = {{
              href: "",
              download: "",
              hidden: false,
              clicked: false,
              removed: false,
              click() {{ this.clicked = true; }},
              remove() {{ this.removed = true; }},
            }};
            const document = {{
              createElement(name) {{
                if (name !== "a") throw new Error("not an anchor");
                return anchor;
              }},
              body: {{ append(node) {{
                if (node !== anchor) throw new Error("wrong node");
              }} }},
            }};
            const fetch = async (_url, init) => {{
              fetchCount += 1;
              requestBody = JSON.parse(init.body);
              return {{
                ok: true,
                status: 200,
                async json() {{
                  return {{
                    download_url: "/download/once",
                    filename: "export.zip",
                    task_count: 2,
                    image_count: 3,
                  }};
                }},
              }};
            }};
            const module = {{ exports: {{}} }};
            vm.runInNewContext(code, {{
              module,
              exports: module.exports,
              fetch,
              document,
              JSON,
              String,
              Error,
              Promise,
            }});
            (async () => {{
              const result = await module.exports.createHistoryExport(
                ["a", "b"],
                "images_with_prompts",
              );
              module.exports.triggerHistoryExportDownload(result);
              if (fetchCount !== 1) throw new Error("wrong request count");
              if (
                requestBody.mode !== "images_with_prompts"
                || requestBody.task_ids.join(",") !== "a,b"
              ) throw new Error("wrong request payload");
              if (
                anchor.href !== "/download/once"
                || anchor.download !== "export.zip"
                || !anchor.clicked
                || !anchor.removed
              ) throw new Error("ordinary download was not triggered");
            }})().catch((error) => {{
              process.stderr.write(String(error.stack || error));
              process.exitCode = 1;
            }});
            """
        )
        result = subprocess.run(
            [node, "-e", harness],
            cwd=Path.cwd(),
            check=False,
            text=True,
            capture_output=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_history_export_picker_and_i18n_contract(self) -> None:
        html = Path(
            "codex_image/webui/static/history.html"
        ).read_text(encoding="utf-8")
        source = Path(
            "codex_image/webui/frontend/src/history.ts"
        ).read_text(encoding="utf-8")
        styles = Path(
            "codex_image/webui/static/styles/90-history.css"
        ).read_text(encoding="utf-8")
        module = Path(
            "codex_image/webui/frontend/src/history-export.ts"
        ).read_text(encoding="utf-8")
        action_panel = Path(
            "codex_image/webui/frontend/src/history-action-panel.ts"
        ).read_text(encoding="utf-8")

        self.assertIn('data-history-toggle-action-section="export"', action_panel)
        self.assertNotIn('data-history-export-mode="task_backup"', source)
        for marker in (
            'from "./history-export"',
            'data-history-open-export',
            "historyExportPending",
            "createHistoryExport(",
            "triggerHistoryExportDownload(",
            "historyExportTrigger?.focus()",
            "historyState.selectedTaskIds",
            "historyState.detailTask",
            "outputs.zip",
        ):
            self.assertIn(marker, source)
        self.assertIn('data-history-export-mode="images_only"', action_panel)
        self.assertIn('data-history-export-mode="images_with_prompts"', action_panel)
        self.assertEqual(
            _typescript_function_body(
                source,
                "runHistoryExport",
            ).count("createHistoryExport("),
            1,
        )
        self.assertNotIn(".blob()", module)
        self.assertNotIn("URL.createObjectURL", module)
        self.assertRegex(
            styles,
            r"\.history-export-picker,\s*\.history-organize-picker\s*\{[^}]*position:\s*fixed",
        )

        export_keys = (
            "history.export",
            "history.exportImagesOnly",
            "history.exportImagesWithPrompts",
            "history.exportPreparing",
            "history.exportStarted",
            "history.exportSummary",
            "history.exportFailed",
            "history.closeExport",
        )
        language_paths = [
            path
            for path in Path(
                "codex_image/webui/frontend/src/i18n"
            ).glob("*.ts")
            if path.name
            not in {"dictionaries.ts", "types.ts"}
        ]
        self.assertEqual(len(language_paths), 14)
        for path in language_paths:
            dictionary = path.read_text(encoding="utf-8")
            for key in export_keys:
                self.assertIn(
                    f'"{key}"',
                    dictionary,
                    f"{path.name} misses {key}",
                )

    def test_history_bulk_action_architecture_and_close_controls(self) -> None:
        html = Path("codex_image/webui/static/history.html").read_text(encoding="utf-8")
        source = Path("codex_image/webui/frontend/src/history.ts").read_text(encoding="utf-8")
        action_panel = Path("codex_image/webui/frontend/src/history-action-panel.ts").read_text(encoding="utf-8")
        styles = Path("codex_image/webui/static/styles/90-history.css").read_text(encoding="utf-8")

        for marker in (
            'data-history-open-backup="selected"',
            'data-history-bulk-clear',
            'data-history-toggle-action-section="organize"',
            'data-history-toggle-action-section="export"',
            'data-history-bulk-delete',
        ):
            self.assertIn(marker, action_panel)

        selection_body = _typescript_function_body(source, "renderSelectionDetail")
        self.assertNotIn("history-selection-actions", selection_body)
        self.assertIn("historySelectionPanelHtml", selection_body)

        organize_body = _typescript_function_body(source, "openHistoryOrganizePicker")
        for marker in (
            'data-history-bulk-favorite',
            'data-history-bulk-unfavorite',
            'data-history-open-tag-picker="add"',
            'data-history-open-tag-picker="remove"',
            'data-history-bulk-archive',
            'data-history-bulk-restore',
        ):
            self.assertIn(marker, organize_body)

        self.assertNotRegex(source, r'class="drawer-close-button[^"\n]*"[^>]*>\s*×\s*</button>')
        self.assertNotRegex(html, r'class="drawer-close-button[^"\n]*"[^>]*>\s*×\s*</button>')
        self.assertGreaterEqual(source.count('class="ghost-button drawer-close-button'), 2)
        self.assertGreaterEqual(html.count('class="ghost-button drawer-close-button'), 3)
        self.assertIn(".history-action-icon", styles)
        self.assertRegex(
            styles,
            r"@media \(max-width: 1100px\)[\s\S]*\.history-selection-dock\s*\{[^}]*display:\s*flex",
        )

    def test_history_toolbar_separates_browse_and_data_safety_actions(self) -> None:
        html = Path("codex_image/webui/static/history.html").read_text(encoding="utf-8")
        styles = Path("codex_image/webui/static/styles/90-history.css").read_text(encoding="utf-8")

        for marker in (
            'class="history-browse-controls"',
            'class="history-toolbar-utilities"',
            'id="historyManagementButton"',
            'id="historyRefreshButton" class="ghost-button history-toolbar-icon-button"',
            'data-i18n-attr="aria-label:history.refresh;title:history.refresh"',
            'class="history-toolbar-button-icon"',
        ):
            self.assertIn(marker, html)

        self.assertRegex(
            styles,
            r"\.history-toolbar-utilities\s*\{[^}]*border-left:\s*1px solid var\(--line\)",
        )
        self.assertRegex(
            styles,
            r"\.history-toolbar-icon-button\s*\{[^}]*width:\s*var\(--history-toolbar-control-height\)",
        )
        self.assertRegex(
            styles,
            r"\.history-toolbar\s*>\s*div:first-child\s*\{[^}]*min-width:\s*max-content",
        )
        self.assertRegex(
            styles,
            r"@media \(max-width: 760px\)[\s\S]*\.history-toolbar-utilities\s*\{[^}]*justify-content:\s*end",
        )

    def test_history_active_filters_are_visible_and_clearable(self) -> None:
        html = Path("codex_image/webui/static/history.html").read_text(encoding="utf-8")
        source = Path("codex_image/webui/frontend/src/history.ts").read_text(encoding="utf-8")
        styles = Path("codex_image/webui/static/styles/90-history.css").read_text(encoding="utf-8")

        for marker in (
            'id="historyActiveFilters"',
            'id="historyActiveFilterList"',
            'id="historyClearAllFilters"',
            'id="historyMobileFilterCount"',
        ):
            self.assertIn(marker, html)
        for marker in (
            'from "./history-active-filters"',
            "collectHistoryActiveFilters(",
            "removeHistoryActiveFilter(",
            "clearHistoryActiveFilters(",
            "renderHistoryActiveFilters()",
        ):
            self.assertIn(marker, source)
        self.assertRegex(
            styles,
            r"\.history-results\s*\{[^}]*grid-template-rows:\s*auto\s+auto\s+minmax\(0,\s*1fr\)",
        )
        self.assertRegex(
            styles,
            r"\.history-active-filter-list\s*\{[^}]*flex-wrap:\s*wrap",
        )
        self.assertRegex(
            styles,
            r"\.history-active-filters\s*\{[^}]*align-items:\s*center",
        )
        self.assertRegex(
            styles,
            r"\.history-active-filters-label\s*\{[^}]*align-self:\s*center",
        )
        self.assertRegex(
            styles,
            r"\.history-active-filter-list\s*\{[^}]*align-content:\s*center",
        )
        self.assertNotRegex(
            styles,
            r"\.history-active-filter-list\s*\{[^}]*overflow-x:\s*auto",
        )
        self.assertRegex(
            styles,
            r"@media \(max-width: 760px\)[\s\S]*\.history-active-filters\s*\{[^}]*grid-template-areas:\s*\"label clear\"\s*\"filters filters\"",
        )
        locale_paths = sorted(Path("codex_image/webui/frontend/src/i18n").glob("*.ts"))
        dictionary_paths = [path for path in locale_paths if path.name not in {"dictionaries.ts", "types.ts"}]
        for path in dictionary_paths:
            localized = path.read_text(encoding="utf-8")
            with self.subTest(locale=path.stem):
                self.assertIn('"history.activeFilterCount"', localized)
                self.assertIn('"history.clearAllFilters"', localized)
                self.assertIn('"history.removeFilter"', localized)
                self.assertIn('"history.filtersActive"', localized)

    def test_history_organization_controls_and_local_update_contract(
        self,
    ) -> None:
        html = Path(
            "codex_image/webui/static/history.html"
        ).read_text(encoding="utf-8")
        source = Path(
            "codex_image/webui/frontend/src/history.ts"
        ).read_text(encoding="utf-8")
        action_panel = Path(
            "codex_image/webui/frontend/src/history-action-panel.ts"
        ).read_text(encoding="utf-8")
        organization_source = Path(
            "codex_image/webui/frontend/src/history-organization.ts"
        ).read_text(encoding="utf-8")
        styles = Path(
            "codex_image/webui/static/styles/90-history.css"
        ).read_text(encoding="utf-8")

        self.assertLess(
            html.index("historySearch"),
            html.index("historyFavoriteList"),
        )
        self.assertLess(
            html.index("historyFavoriteList"),
            html.index('data-history-filter-section="mode"'),
        )
        for marker in (
            'id="historyTagFilterList"',
            'id="historyTagManageToggle"',
            'id="historyTagManager"',
            'id="historyTagManagerStatus"',
        ):
            self.assertIn(marker, html)
        for marker in (
            'data-history-bulk-favorite',
            'data-history-bulk-unfavorite',
            'data-history-open-tag-picker="add"',
            'data-history-open-tag-picker="remove"',
            'data-history-bulk-archive',
            'data-history-bulk-restore',
        ):
            self.assertIn(marker, action_panel)
        for old_id in (
            'historyBulkFavoriteButton',
            'historyBulkUnfavoriteButton',
            'historyBulkAddTagButton',
            'historyBulkRemoveTagButton',
            'historyBulkArchiveButton',
            'historyBulkRestoreButton',
        ):
            self.assertNotIn(f'id="{old_id}"', html)
        self.assertNotIn("history-tag-manager-modal", html)

        for marker in (
            'from "./history-organization"',
            "readHistoryOrganizationFilters",
            "writeHistoryOrganizationFilters",
            "historyTaskPageQuery",
            "taskMatchesHistoryOrganizationFilters",
            "historyFavoriteButtonHtml",
            "historyCardTagsHtml",
            "organizeHistoryTasks",
            "function applyHistoryOrganizations",
            "function removeHistoryTaskCardPreservingAnchor",
            'data-history-favorite-task',
            'data-history-open-tag-picker',
            "historyTagMutationErrorMessage",
            "historyOrganizationSummarySupported",
            "historyTaskRowsSupportOrganization",
            "historyTagPickerCreateHtml",
            "createHistoryTagForTasks",
            "data-history-tag-create-inline",
            "history.backendRestartRequired",
        ):
            self.assertIn(marker, source)
        self.assertIn(
            "class HistoryOrganizationRequestError",
            organization_source,
        )
        self.assertIn(
            "error.status === 409",
            _typescript_function_body(
                source,
                "historyTagMutationErrorMessage",
            ),
        )
        card_body = _typescript_function_body(
            source,
            "taskCardHtml",
        )
        self.assertIn("historyFavoriteButtonHtml", card_body)
        self.assertIn("historyCardTagsHtml", card_body)
        self.assertLess(
            card_body.index("historyFavoriteButtonHtml"),
            card_body.index(
                '<button class="history-task-open"'
            ),
        )
        organize_body = _typescript_function_body(
            source,
            "organizeHistoryTaskIds",
        )
        self.assertEqual(
            organize_body.count("organizeHistoryTasks("),
            1,
        )
        self.assertIn(
            "taskMatchesHistoryOrganizationFilters",
            _typescript_function_body(
                source,
                "applyHistoryOrganizations",
            ),
        )
        self.assertIn("event.key !== \"Escape\"", source)
        self.assertIn("historyTagPickerTrigger?.focus()", source)
        self.assertRegex(
            styles,
            r"\.history-tag-picker\s*\{[^}]*position:\s*fixed",
        )
        self.assertIn(".history-tag-picker-create-form", styles)
        self.assertIn(".history-tag-manager-status", styles)
        self.assertRegex(
            styles,
            r"\.history-card-tags\s*\{[^}]*overflow:\s*hidden",
        )
        self.assertNotRegex(
            styles,
            r"\.history-card-tags\s*\{[^}]*position:\s*absolute",
        )
        favorite_button_body = _typescript_function_body(
            organization_source,
            "historyFavoriteButtonHtml",
        )
        self.assertIn('class="history-favorite-icon"', favorite_button_body)
        self.assertIn('<path d="M12 3.7', favorite_button_body)
        self.assertNotIn(">★</button>", favorite_button_body)
        self.assertNotIn(
            ".history-task-card.active .history-favorite-button",
            styles,
        )
        self.assertNotIn(
            ".history-task-card.selected .history-favorite-button",
            styles,
        )
        self.assertRegex(
            styles,
            r"\.history-page\.history-bulk-selecting \.history-favorite-button:not\(\.active\),\s*"
            r"\.history-page\.history-selection-mode \.history-favorite-button:not\(\.active\)\s*"
            r"\{[^}]*opacity:\s*0[^}]*visibility:\s*hidden[^}]*pointer-events:\s*none",
        )

    def test_history_organization_i18n_keys_exist_in_all_languages(
        self,
    ) -> None:
        keys = (
            "history.favorites",
            "history.onlyFavorites",
            "history.favoriteTask",
            "history.unfavoriteTask",
            "history.tags",
            "history.untagged",
            "history.manageTags",
            "history.createTag",
            "history.renameTag",
            "history.deleteTag",
            "history.deleteTagAffected",
            "history.addTag",
            "history.removeTag",
            "history.favoriteSelected",
            "history.unfavoriteSelected",
            "history.organizationFailed",
            "history.tagNameConflict",
            "history.noTags",
            "history.backendRestartRequired",
        )
        paths = sorted(
            Path(
                "codex_image/webui/frontend/src/i18n"
            ).glob("*.ts")
        )
        language_paths = [
            path
            for path in paths
            if path.name
            not in {"dictionaries.ts", "types.ts"}
        ]
        self.assertEqual(len(language_paths), 14)
        for path in language_paths:
            source = path.read_text(encoding="utf-8")
            for key in keys:
                self.assertIn(
                    f'"{key}"',
                    source,
                    f"{path.name} misses {key}",
                )

    def test_history_search_and_tag_manager_keep_actions_compact(
        self,
    ) -> None:
        html = Path(
            "codex_image/webui/static/history.html"
        ).read_text(encoding="utf-8")
        source = Path(
            "codex_image/webui/frontend/src/history.ts"
        ).read_text(encoding="utf-8")
        styles = Path(
            "codex_image/webui/static/styles/90-history.css"
        ).read_text(encoding="utf-8")

        self.assertIn(
            ".history-search-field input[type=\"search\"]::-webkit-search-cancel-button",
            styles,
        )
        self.assertIn(
            'id="historySearchClear"',
            html,
        )
        self.assertIn(
            'data-i18n="action.add">添加</button>',
            html,
        )
        self.assertIn(
            'class="history-tag-manager-row-field"',
            source,
        )
        self.assertIn(
            'class="history-tag-manager-row-actions"',
            source,
        )
        self.assertIn(
            'translate("history.confirmDelete")',
            source,
        )
        self.assertIn(
            'aria-label="${escapeHtml(deleteAriaLabel)}"',
            source,
        )
        self.assertIn(
            ".history-tag-manager-row-actions",
            styles,
        )
        self.assertNotIn(
            ".history-tag-manager-row > .control",
            styles,
        )

    def test_history_organization_filter_runtime_contract(self) -> None:
        node = shutil.which("node")
        if node is None:
            self.skipTest(
                "node is required for frontend behavior checks"
            )
        module_path = Path(
            "codex_image/webui/frontend/src/"
            "history-organization.ts"
        )
        self.assertTrue(module_path.is_file())
        harness = textwrap.dedent(
            f"""
            const fs = require("fs");
            const ts = require("typescript");
            const vm = require("vm");
            const source = fs.readFileSync(
              {str(module_path)!r},
              "utf8",
            );
            const code = ts.transpileModule(source, {{
              compilerOptions: {{
                module: ts.ModuleKind.CommonJS,
                target: ts.ScriptTarget.ES2020,
              }},
            }}).outputText;
            const module = {{ exports: {{}} }};
            vm.runInNewContext(code, {{
              module,
              exports: module.exports,
              URLSearchParams,
              fetch: () => {{
                throw new Error("unexpected fetch");
              }},
              Set,
              Array,
              Object,
              String,
              Promise,
            }});
            const m = module.exports;
            const check = (condition, message) => {{
              if (!condition) throw new Error(message);
            }};
            const restored = m.readHistoryOrganizationFilters(
              new URLSearchParams(
                "q=red&favorite=true&tag=a&tag=a&tag=b"
              ),
            );
            check(restored.favorite === true, "favorite lost");
            check(
              JSON.stringify(restored.tagIds)
                === JSON.stringify(["a", "b"]),
              "repeated tags were not restored and deduplicated",
            );
            const params = new URLSearchParams(
              "q=red&sort=oldest&tag=old&untagged=true"
            );
            m.writeHistoryOrganizationFilters(params, restored);
            check(params.get("q") === "red", "search changed");
            check(params.get("sort") === "oldest", "sort changed");
            check(
              JSON.stringify(params.getAll("tag"))
                === JSON.stringify(["a", "b"]),
              "tags were not written as repeated parameters",
            );
            check(!params.has("untagged"), "untagged was retained");
            const untagged = m.withHistoryUntaggedFilter(
              restored,
              true,
            );
            check(
              untagged.untagged && untagged.tagIds.length === 0,
              "untagged did not clear tags",
            );
            const tagged = m.withHistoryTagFilter(
              untagged,
              "a",
              true,
            );
            check(
              !tagged.untagged
                && JSON.stringify(tagged.tagIds)
                  === JSON.stringify(["a"]),
              "tag did not clear untagged",
            );
            check(
              m.taskMatchesHistoryOrganizationFilters(
                {{ favorite: true, tags: [
                  {{ tag_id: "a", name: "A" }},
                  {{ tag_id: "b", name: "B" }},
                ] }},
                restored,
              ),
              "AND match rejected a complete task",
            );
            check(
              !m.taskMatchesHistoryOrganizationFilters(
                {{ favorite: true, tags: [
                  {{ tag_id: "a", name: "A" }},
                ] }},
                restored,
              ),
              "AND match accepted a missing tag",
            );
            check(
              !m.taskMatchesHistoryOrganizationFilters(
                {{ favorite: false, tags: [] }},
                {{ favorite: true, tagIds: [], untagged: false }},
              ),
              "favorite filter accepted an unstarred task",
            );
            check(
              !m.historyOrganizationSummarySupported({{
                total: 10,
              }}),
              "legacy summary was accepted",
            );
            check(
              m.historyOrganizationSummarySupported({{
                favorite_total: 0,
                untagged_total: 10,
                tags: [],
              }}),
              "current summary was rejected",
            );
            check(
              !m.historyTaskRowsSupportOrganization([
                {{ task_id: "old-task" }},
              ]),
              "legacy task rows were accepted",
            );
            check(
              m.historyTaskRowsSupportOrganization([
                {{
                  task_id: "current-task",
                  favorite: false,
                  tags: [],
                }},
              ]),
              "current task rows were rejected",
            );
            const escaped = (value) => String(value)
              .replaceAll("<", "&lt;")
              .replaceAll('"', "&quot;");
            const createHtml = m.historyTagPickerCreateHtml(
              escaped,
              {{
                placeholder: '名称"<',
                submitLabel: '创建"<',
              }},
            );
            check(
              createHtml.includes("data-history-tag-create-inline"),
              "picker create form is missing",
            );
            check(
              createHtml.includes("data-history-tag-create-status"),
              "picker create status is missing",
            );
            check(
              !createHtml.includes('名称"<')
                && !createHtml.includes('创建"<'),
              "picker create labels were not escaped",
            );
            const html = m.historyCardTagsHtml(
              [
                {{ tag_id: 'id"<', name: 'name"<'}}
              ],
              escaped,
            );
            check(!html.includes('name"<'), "text was not escaped");
            check(!html.includes('id"<'), "attribute was not escaped");
            """
        )
        result = subprocess.run(
            [node, "-e", harness],
            cwd=Path.cwd(),
            check=False,
            text=True,
            capture_output=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_history_tag_picker_creates_and_assigns_tag_to_tasks(
        self,
    ) -> None:
        node = shutil.which("node")
        if node is None:
            self.skipTest(
                "node is required for frontend behavior checks"
            )
        module_path = Path(
            "codex_image/webui/frontend/src/"
            "history-organization.ts"
        )
        harness = textwrap.dedent(
            f"""
            const fs = require("fs");
            const ts = require("typescript");
            const vm = require("vm");
            const source = fs.readFileSync(
              {str(module_path)!r},
              "utf8",
            );
            const code = ts.transpileModule(source, {{
              compilerOptions: {{
                module: ts.ModuleKind.CommonJS,
                target: ts.ScriptTarget.ES2020,
              }},
            }}).outputText;
            const requests = [];
            const responses = [
              {{
                tag: {{
                  tag_id: "tag-new",
                  name: "人像",
                  count: 0,
                }},
              }},
              {{
                organizations: {{
                  "task-a": {{
                    favorite: false,
                    tags: [{{
                      tag_id: "tag-new",
                      name: "人像",
                    }}],
                  }},
                  "task-b": {{
                    favorite: true,
                    tags: [{{
                      tag_id: "tag-new",
                      name: "人像",
                    }}],
                  }},
                }},
              }},
            ];
            const fetch = async (url, init = {{}}) => {{
              requests.push({{ url, init }});
              const payload = responses.shift();
              return {{
                ok: true,
                status: 200,
                async json() {{ return payload; }},
              }};
            }};
            const module = {{ exports: {{}} }};
            vm.runInNewContext(code, {{
              module,
              exports: module.exports,
              fetch,
              URLSearchParams,
              Set,
              Array,
              Object,
              String,
              Promise,
              JSON,
            }});
            const check = (condition, message) => {{
              if (!condition) throw new Error(message);
            }};
            (async () => {{
              const result =
                await module.exports.createHistoryTagForTasks(
                  "人像",
                  ["task-a", "task-a", "task-b"],
                );
              check(
                result.tag.tag_id === "tag-new",
                "created tag was not returned",
              );
              check(
                result.organizations["task-a"].tags[0].tag_id
                  === "tag-new",
                "created tag was not assigned",
              );
              check(requests.length === 2, "wrong request count");
              check(
                requests[0].url === "/api/task-history/tags",
                "wrong create endpoint",
              );
              check(
                requests[1].url === "/api/task-history/organize",
                "wrong organize endpoint",
              );
              const organizeBody = JSON.parse(
                requests[1].init.body,
              );
              check(
                JSON.stringify(organizeBody.task_ids)
                  === JSON.stringify(["task-a", "task-b"]),
                "task ids were not deduplicated",
              );
              check(
                JSON.stringify(organizeBody.add_tag_ids)
                  === JSON.stringify(["tag-new"]),
                "new tag was not sent for assignment",
              );
            }})().catch((error) => {{
              console.error(error);
              process.exitCode = 1;
            }});
            """
        )
        result = subprocess.run(
            [node, "-e", harness],
            cwd=Path.cwd(),
            check=False,
            text=True,
            capture_output=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_history_lightbox_uses_non_looping_three_slot_peek_carousel(self) -> None:
        source = Path("codex_image/webui/frontend/src/history-lightbox.ts").read_text(encoding="utf-8")
        styles = Path("codex_image/webui/static/styles/90-history.css").read_text(encoding="utf-8")

        for marker in (
            'class="history-lightbox-track"',
            'data-history-lightbox-slot="previous"',
            'data-history-lightbox-slot="current"',
            'data-history-lightbox-slot="next"',
            "historyLightboxState.isTransitioning",
            "function historyLightboxSlotIndexes",
            "function transitionHistoryLightboxTo",
            "bindHistoryLightboxSlots",
        ):
            self.assertIn(marker, source)
        self.assertNotIn("((index % count) + count) % count", source)
        self.assertNotIn("data-history-lightbox-prev", source)
        self.assertNotIn("data-history-lightbox-next", source)
        self.assertNotIn("history-lightbox-nav", source)
        self.assertIn("function historyLightboxEdgeRect", source)
        self.assertIn("function animateHistoryLightboxSwap", source)
        self.assertIn("history-lightbox-transition-ghost", source)
        self.assertNotIn("data-history-lightbox-incoming-image", source)
        self.assertNotIn("is-focus-switching", source)
        self.assertNotIn("history-lightbox-card-back", source)
        self.assertNotIn("is-card-retiring", source)
        self.assertNotIn("is-card-revealing", source)
        self.assertRegex(styles, r"\.history-lightbox-peek\s*\{[^}]*position:\s*fixed")
        self.assertRegex(styles, r"\.history-lightbox-peek\s*\{[^}]*width:\s*clamp\(44px,\s*4\.5vw,\s*88px\)")
        self.assertIn(".history-lightbox-transition-layer", styles)
        self.assertNotIn("transform: translate(12px, -50%)", styles)
        self.assertNotIn("transform: translate(-12px, -50%)", styles)
        self.assertNotIn(".history-lightbox-card-back", styles)
        self.assertIn(".history-lightbox.is-zoomed .history-lightbox-peek", styles)
        self.assertIn("@media (prefers-reduced-motion: reduce)", styles)

    def test_history_lightbox_restores_edge_images_at_or_below_fitted_zoom(self) -> None:
        source = Path("codex_image/webui/frontend/src/history-lightbox.ts").read_text(encoding="utf-8")

        self.assertIn('from "./lightbox-controls"', source)
        self.assertIn("lightboxScaleFromWheel", source)
        self.assertIn("isLightboxAtOrBelowFitScale", source)
        self.assertIn("shouldCloseLightboxFromClick(event.target, historyLightboxEl!)", source)
        self.assertIn("lightboxZoomChromeHtml", source)
        self.assertIn("showLightboxShortcutHint", source)
        self.assertIn("const wasActive = isHistoryLightboxActive();", source)
        self.assertRegex(source, r"if \(!wasActive\) \{\s*showLightboxShortcutHint")
        self.assertNotIn("historyLightboxState.scale !== 1", source)
        self.assertNotIn("event.target === historyLightboxEl", source)

    def test_history_lightbox_peek_carousel_runtime_contract(self) -> None:
        node = shutil.which("node")
        if node is None:
            self.skipTest("node is required for frontend behavior checks")
        module_path = Path("codex_image/webui/frontend/src/history-lightbox.ts")
        harness = textwrap.dedent(
            f"""
            const fs = require("fs");
            const ts = require("typescript");
            const vm = require("vm");
            const source = fs.readFileSync({str(module_path)!r}, "utf8")
              + "\\nexport {{ historyLightboxSlotIndexes as __slots, clampedHistoryLightboxIndex as __clamp }};\\n";
            const code = ts.transpileModule(source, {{
              compilerOptions: {{ module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 }},
            }}).outputText;
            const module = {{ exports: {{}} }};
            vm.runInNewContext(code, {{
              module, exports: module.exports, console, Promise, Set, Map, Array,
              require(name) {{
                if (name === "./i18n") return {{ translate: (key) => key }};
                if (name === "./lightbox-controls") return {{}};
                if (name === "./webui-utils") return {{ escapeHtml: (value) => String(value) }};
                throw new Error(`unexpected require: ${{name}}`);
              }},
            }});
            const check = (condition, message) => {{ if (!condition) throw new Error(message); }};
            check(JSON.stringify(module.exports.__slots(0, 3)) === JSON.stringify({{ previous: null, current: 0, next: 1 }}), "first slots wrap");
            check(JSON.stringify(module.exports.__slots(1, 3)) === JSON.stringify({{ previous: 0, current: 1, next: 2 }}), "middle slots wrong");
            check(JSON.stringify(module.exports.__slots(2, 3)) === JSON.stringify({{ previous: 1, current: 2, next: null }}), "last slots wrap");
            check(module.exports.__clamp(-1, 3) === 0, "negative index wrapped");
            check(module.exports.__clamp(3, 3) === 2, "overflow index wrapped");
            """
        )
        result = subprocess.run([node, "-e", harness], cwd=Path.cwd(), check=False, text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_history_lightbox_swap_hands_off_before_removing_transition_layer(self) -> None:
        source = Path("codex_image/webui/frontend/src/history-lightbox.ts").read_text(encoding="utf-8")
        transition = _typescript_function_body(source, "transitionHistoryLightboxTo")
        animate_swap = _typescript_function_body(source, "animateHistoryLightboxSwap")

        self.assertIn("await preloadHistoryLightboxSlotImages(targetIndex)", transition)
        self.assertIn("const transitionLayer = await animateHistoryLightboxSwap", transition)
        self.assertIn("await settleHistoryLightboxSwap(transitionLayer)", transition)
        self.assertLess(
            transition.index("historyLightboxState.index = targetIndex"),
            transition.index("await settleHistoryLightboxSwap(transitionLayer)"),
        )
        self.assertIn("return layer", animate_swap)
        self.assertNotIn("layer.remove()", animate_swap)

    def test_history_lightbox_swap_uses_bound_image_geometry_for_handoff(self) -> None:
        source = Path("codex_image/webui/frontend/src/history-lightbox.ts").read_text(encoding="utf-8")
        animate_swap = _typescript_function_body(source, "animateHistoryLightboxSwap")

        self.assertIn("const centerRect = currentImage.getBoundingClientRect()", animate_swap)
        bind_slots = animate_swap.index("bindHistoryLightboxSlots(targetIndex)")
        decode_slots = animate_swap.index("await decodeHistoryLightboxBoundSlots()")
        measure_center = animate_swap.index("const centerRect = currentImage.getBoundingClientRect()")
        create_incoming = animate_swap.index("const incomingGhost = historyLightboxTransitionGhost")
        start_animation = animate_swap.index("outgoingGhost.animate")

        self.assertLess(bind_slots, decode_slots)
        self.assertLess(decode_slots, measure_center)
        self.assertLess(measure_center, create_incoming)
        self.assertLess(create_incoming, start_animation)
        self.assertNotIn("currentFrame.getBoundingClientRect()", animate_swap)

    def test_history_lightbox_incoming_ghost_finishes_with_an_unscaled_shadow(self) -> None:
        source = Path("codex_image/webui/frontend/src/history-lightbox.ts").read_text(encoding="utf-8")
        animate_swap = _typescript_function_body(source, "animateHistoryLightboxSwap")

        self.assertRegex(
            animate_swap,
            r"const incomingGhost = historyLightboxTransitionGhost\(\s*"
            r"targetImage\.currentSrc \|\| targetImage\.src,\s*centerRect,",
        )
        self.assertIn("historyLightboxIncomingGhostKeyframes", animate_swap)

    def test_history_lightbox_settling_keeps_only_one_center_shadow(self) -> None:
        styles = Path("codex_image/webui/static/styles/90-history.css").read_text(encoding="utf-8")

        self.assertRegex(
            styles,
            r"\.history-lightbox\.is-shared-switching\.is-shared-settling\s+"
            r"\.history-lightbox-current-image\s*\{[^}]*box-shadow:\s*none",
        )

    def test_history_lightbox_swap_keeps_prepared_edge_slots_visible(self) -> None:
        source = Path("codex_image/webui/frontend/src/history-lightbox.ts").read_text(encoding="utf-8")
        styles = Path("codex_image/webui/static/styles/90-history.css").read_text(encoding="utf-8")
        animate_swap = _typescript_function_body(source, "animateHistoryLightboxSwap")
        transition_ghost = _typescript_function_body(source, "historyLightboxTransitionGhost")

        self.assertIn("bindHistoryLightboxSlots(targetIndex)", animate_swap)
        self.assertIn("await decodeHistoryLightboxBoundSlots()", animate_swap)
        self.assertLess(
            animate_swap.index("bindHistoryLightboxSlots(targetIndex)"),
            animate_swap.index("outgoingGhost.animate"),
        )
        self.assertIn("incomingStartOpacity", animate_swap)
        self.assertNotIn("outgoingEndOpacity", animate_swap)
        self.assertNotIn("getComputedStyle(outgoingPeek).opacity", animate_swap)
        self.assertRegex(
            styles,
            r"\.history-lightbox\s*\{[^}]*--history-lightbox-peek-opacity:\s*0\.48",
        )
        self.assertRegex(
            animate_swap,
            r"historyLightboxGhostKeyframes\(\s*currentRect,[\s\S]*?outgoingEdgeRect,[\s\S]*?1,\s*0,\s*\)",
        )
        self.assertRegex(
            animate_swap,
            r"historyLightboxTransitionGhost\([\s\S]*?reduceMotion\s*\?\s*0\s*:\s*incomingStartOpacity,?\s*\)",
        )
        self.assertIn("opacity: `${opacity}`", transition_ghost)
        self.assertNotRegex(
            styles,
            r"\.history-lightbox\.is-shared-switching\s+\.history-lightbox-peek\s*\{[^}]*opacity:\s*0",
        )
        self.assertNotRegex(
            styles,
            r"\.history-lightbox\.is-shared-switching\s+\.history-lightbox-peek\s*\{[^}]*pointer-events:\s*none",
        )

    def test_history_reference_files_reuse_shared_format_svg_icons(self) -> None:
        source = Path("codex_image/webui/frontend/src/history-detail-media.ts").read_text(encoding="utf-8")
        styles = Path("codex_image/webui/static/styles/90-history.css").read_text(encoding="utf-8")

        self.assertIn('import { referenceFileIconSvgMarkup } from "./reference-file-icons";', source)
        self.assertIn("referenceFileIconSvgMarkup(record.filename)", source)
        self.assertNotIn("const iconText =", source)
        self.assertRegex(
            styles,
            r"\.history-reference-file-icon \.reference-file-format-icon\s*\{[^}]*width:\s*28px[^}]*height:\s*28px",
        )

    def test_history_reference_file_handoff_resolves_current_task_by_safe_id(self) -> None:
        source = Path("codex_image/webui/frontend/src/history.ts").read_text(encoding="utf-8")
        handoff = _typescript_function_body(source, "handoffReferenceFileToMain")
        self.assertIn('/^[0-9a-f]{64}$/.test(assetId)', handoff)
        self.assertIn("historyState.detailTask", handoff)
        self.assertIn("task.reference_files.find", handoff)
        self.assertIn("reference_file_id: assetId", handoff)
        self.assertNotIn("dataset.historyReferenceFileName", source)
        self.assertNotIn("data-history-reference-file-lightbox", source)

    def test_history_reference_file_handoff_serializes_only_current_task_metadata(self) -> None:
        node = shutil.which("node")
        if node is None:
            self.skipTest("node is required for frontend behavior checks")
        source = Path("codex_image/webui/frontend/src/history.ts").read_text(encoding="utf-8")
        function_source = (
            "function handoffReferenceFileToMain(assetId: string): void "
            + _typescript_function_body(source, "handoffReferenceFileToMain")
        )
        harness = textwrap.dedent(
            f"""
            const ts = require("typescript");
            const vm = require("vm");
            const a = "a".repeat(64);
            const b = "b".repeat(64);
            const writes = [];
            const historyState = {{ detailTask: {{
              requested_backend: "openai_responses", api_provider_id: "provider-current",
              reference_files: [{{ id: a, filename: "current.pdf", mime_type: "application/pdf", size_bytes: 42, family: "pdf" }}],
            }} }};
            const localStorage = {{ setItem(key, value) {{ writes.push([key, value]); }} }};
            const window = {{ location: {{ href: "/history" }} }};
            const HISTORY_REFERENCE_HANDOFF_KEY = "handoff";
            const code = ts.transpileModule({function_source!r}, {{
              compilerOptions: {{ target: ts.ScriptTarget.ES2020 }},
            }}).outputText;
            const context = {{ historyState, localStorage, window, HISTORY_REFERENCE_HANDOFF_KEY, JSON, String, Number }};
            vm.createContext(context);
            vm.runInContext(code, context);
            const handoff = context.handoffReferenceFileToMain;
            handoff(a);
            if (writes.length !== 1) throw new Error("valid current-task file was not handed off");
            const item = JSON.parse(writes[0][1])[0];
            if (item.reference_file_id !== a || item.filename !== "current.pdf" || item.api_provider_id !== "provider-current") {{
              throw new Error(`handoff did not use current task metadata: ${{JSON.stringify(item)}}`);
            }}
            writes.length = 0;
            historyState.detailTask = {{
              requested_backend: "codex_responses",
              reference_files: [{{ id: b, filename: "new.md", mime_type: "text/markdown", size_bytes: 3, family: "text" }}],
            }};
            handoff(a);
            handoff("not-a-sha");
            if (writes.length !== 0) throw new Error("stale or invalid ID supplied metadata");
            """
        )
        result = subprocess.run([node, "-e", harness], check=False, text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_history_type_filter_is_translated_for_every_locale(self) -> None:
        locale_paths = sorted(Path("codex_image/webui/frontend/src/i18n").glob("*.ts"))
        dictionary_paths = [path for path in locale_paths if path.name not in {"dictionaries.ts", "types.ts"}]
        self.assertEqual(len(dictionary_paths), 14)
        for path in dictionary_paths:
            source = path.read_text(encoding="utf-8")
            with self.subTest(locale=path.stem):
                self.assertIn('"history.type"', source)
                self.assertIn('"history.allTypes"', source)
                self.assertIn('"history.type.textToImage"', source)
                self.assertIn('"history.type.imageToImage"', source)

    def test_history_page_uses_viewport_workbench_layout(self) -> None:
        html = Path("codex_image/webui/static/history.html").read_text(encoding="utf-8")
        styles = Path("codex_image/webui/static/styles/90-history.css").read_text(encoding="utf-8")
        source = Path("codex_image/webui/frontend/src/history.ts").read_text(encoding="utf-8")

        self.assertIn('class="history-page"', html)
        self.assertIn('data-history-detail-close', Path("codex_image/webui/frontend/src/history-action-panel.ts").read_text(encoding="utf-8"))
        self.assertIn("shouldClearHistoryTaskFromBlankSurface", source)
        self.assertIn("isTaskListBlankSurface: target === els.taskList", source)
        self.assertIn('data-history-resizer="left"', html)
        self.assertIn('data-history-resizer="right"', html)
        self.assertIn('role="separator"', html)
        self.assertIn('class="history-filter-heading history-filter-heading-orientation"', html)
        self.assertIn('class="history-filter-heading-icon"', html)
        self.assertIn('data-i18n-attr="aria-label:history.resizeFilters"', html)
        self.assertIn('data-i18n-attr="aria-label:history.resizeDetail"', html)
        self.assertIn('/static/styles.css?v=runtime-785', html)
        self.assertIn('/static/history.js?v=history-113', html)
        self.assertRegex(styles, r"\.history-page\s*\{[^}]*height:\s*100dvh")
        self.assertRegex(styles, r"\.history-page\s*\{[^}]*overflow:\s*hidden")
        self.assertRegex(styles, r"\.history-page\s*\{[^}]*--history-sidebar-width:\s*280px")
        self.assertRegex(styles, r"\.history-page\s*\{[^}]*--history-detail-width:\s*380px")
        self.assertRegex(styles, r"\.history-page\s*\{[^}]*grid-template-rows:\s*var\(--header-height\)\s+minmax\(0,\s*1fr\)")
        self.assertRegex(styles, r"\.history-top-nav\s*\{[^}]*grid-column:\s*2\s*/\s*-1")
        self.assertRegex(styles, r"\.history-top-nav\s*\{[^}]*grid-row:\s*1")
        self.assertNotIn("--history-resizer-width", styles)
        self.assertNotIn("resizerWidth", source)
        self.assertNotIn(".history-resizer", styles)
        self.assertNotIn(".history-resize-hit-area::before", styles)
        self.assertNotIn(".history-resize-hit-area::after", styles)
        self.assertRegex(styles, r"\.history-page\s*\{[^}]*grid-template-columns:[^}]*clamp\(220px,\s*var\(--history-sidebar-width\),\s*420px\)[^}]*minmax\(360px,\s*1fr\)[^}]*clamp\(300px,\s*var\(--history-detail-width\),\s*620px\)")
        self.assertRegex(styles, r"\.history-resize-hit-area\s*\{[^}]*position:\s*absolute")
        self.assertRegex(styles, r"\.history-resize-hit-area\s*\{[^}]*width:\s*12px")
        self.assertRegex(styles, r"\.history-resize-hit-area\s*\{[^}]*background:\s*transparent")
        self.assertRegex(styles, r"\.history-resize-hit-area\s*\{[^}]*cursor:\s*col-resize")
        self.assertRegex(styles, r"\.history-resize-hit-area-left\s*\{[^}]*left:\s*clamp\(220px,\s*var\(--history-sidebar-width\),\s*420px\)")
        self.assertRegex(styles, r"\.history-resize-hit-area-right\s*\{[^}]*right:\s*clamp\(300px,\s*var\(--history-detail-width\),\s*620px\)")
        self.assertRegex(styles, r"\.history-results\s*\{[^}]*position:\s*relative")
        self.assertRegex(styles, r"\.history-results\s*\{[^}]*grid-template-rows:\s*auto\s+auto\s+minmax\(0,\s*1fr\)")
        self.assertRegex(styles, r"\.history-results\s*\{[^}]*padding:\s*18px\s+12px\s+0")
        self.assertNotRegex(styles, r"\.history-results\s*\{[^}]*grid-template-rows:\s*auto\s+auto\s+minmax\(0,\s*1fr\)\s+auto")
        self.assertRegex(styles, r"\.history-task-list\s*\{[^}]*overflow:\s*auto")
        self.assertRegex(styles, r"\.history-task-list\s*\{[^}]*margin-right:\s*-12px")
        self.assertRegex(styles, r"\.history-task-list\s*\{[^}]*padding:\s*0\s+15px\s+env\(safe-area-inset-bottom,\s*0px\)\s+4px")
        self.assertRegex(styles, r"\.history-task-list\s*\{[^}]*scrollbar-gutter:\s*stable")
        self.assertRegex(styles, r"\.history-task-list\.history-view-grid\s*\{[^}]*--history-task-thumb-row-height:\s*clamp")
        self.assertRegex(styles, r"\.history-task-list\.history-view-grid\s*\{[^}]*display:\s*flex")
        self.assertRegex(styles, r"\.history-task-list\.history-view-grid\s*\{[^}]*flex-wrap:\s*wrap")
        self.assertRegex(styles, r"\.history-task-list\.history-view-grid\s*\{[^}]*align-items:\s*flex-start")
        self.assertRegex(styles, r"\.history-task-list\.history-view-grid\s*\{[^}]*padding:\s*6px\s+15px\s+calc\(6px\s+\+\s+env\(safe-area-inset-bottom,\s*0px\)\)\s+4px")
        self.assertNotRegex(styles, r"\.history-task-list\.history-view-grid\s*\{[^}]*grid-template-columns:\s*repeat\(auto-fill")
        self.assertNotRegex(styles, r"\.history-task-list\.history-view-grid\s*\{[^}]*grid-auto-rows:")
        self.assertRegex(styles, r"\.history-task-list\.history-view-list\s*\{[^}]*grid-template-columns:\s*minmax\(0,\s*1fr\)")
        self.assertRegex(styles, r"\.history-task-list\.history-view-list \.history-task-card\s*\{[^}]*grid-template-columns:\s*minmax\(0,\s*1fr\)")
        self.assertNotIn(".history-task-select", styles)
        self.assertRegex(styles, r"\.history-task-list\.history-view-grid \.history-task-card\s*\{[^}]*flex-basis:\s*var\(--history-task-card-width")
        self.assertRegex(styles, r"\.history-task-list\.history-view-grid \.history-task-card\s*\{[^}]*width:\s*var\(--history-task-card-width")
        self.assertNotRegex(styles, r"\.history-task-list\.history-view-grid\s*\{[^}]*justify-content:\s*space-between")
        self.assertRegex(styles, r"\.history-sidebar,\s*\.history-task-list,\s*\.history-detail,\s*\.history-detail-prompt\s*\{[^}]*scrollbar-color:\s*var\(--scrollbar-thumb\)\s+transparent")
        self.assertRegex(styles, r"\.history-sidebar::-webkit-scrollbar-track,[\s\S]*\.history-detail-prompt::-webkit-scrollbar-track\s*\{[^}]*background:\s*transparent")
        self.assertIn(".history-task-list::-webkit-scrollbar-thumb:hover", styles)
        self.assertRegex(styles, r"\.history-task-list\.history-view-grid \.history-task-thumb\s*\{[^}]*aspect-ratio:\s*var\(--history-task-thumb-ratio,\s*1\s*/\s*1\)")
        self.assertRegex(styles, r"\.history-task-list\.history-view-grid \.history-task-thumb\s*\{[^}]*height:\s*var\(--history-task-row-height,\s*var\(--history-task-thumb-row-height\)\)")
        self.assertNotRegex(
            styles,
            r"\.history-task-list\.history-view-grid \.history-task-thumb\s*\{[^}]*content-visibility:",
        )
        self.assertRegex(styles, r"\.history-task-thumb img\s*\{[^}]*object-fit:\s*cover")
        self.assertRegex(styles, r"\.history-task-thumb img\s*\{[^}]*border-radius:\s*inherit")
        self.assertRegex(
            styles,
            r"\.history-task-list\.history-view-grid \.history-task-card\.active \.history-task-thumb,\s*"
            r"\.history-task-list\.history-view-grid \.history-task-card\.selected \.history-task-thumb\s*\{[^}]*"
            r"border-radius:\s*var\(--radius\)[^}]*background:\s*var\(--surface-soft\)",
        )
        self.assertRegex(styles, r"\.history-task-thumb img\s*\{[^}]*user-select:\s*none")
        self.assertRegex(styles, r"\.history-task-thumb img\s*\{[^}]*-webkit-user-drag:\s*none")
        self.assertNotRegex(styles, r"\.history-task-list\.history-view-grid\s+\.history-task-open\s*\{[^}]*min-height:\s*100%")
        self.assertRegex(styles, r"\.history-detail\s*\{[^}]*display:\s*flex")
        self.assertRegex(styles, r"\.history-detail\s*\{[^}]*flex-direction:\s*column")
        self.assertRegex(styles, r"\.history-detail\s*\{[^}]*overflow:\s*auto")
        self.assertNotRegex(styles, r"\.history-detail\s*\{[^}]*grid-template-rows:")
        self.assertRegex(
            styles,
            r"@media \(max-width:\s*1100px\)\s*\{[\s\S]*\.history-page\s*\{[^}]*grid-template-columns:\s*240px\s+minmax\(0,\s*1fr\)",
        )
        self.assertRegex(
            styles,
            r"@media \(max-width:\s*1100px\)\s*\{[\s\S]*\.history-resize-hit-area\s*\{[^}]*display:\s*none",
        )
        self.assertRegex(
            styles,
            r"@media \(max-width:\s*1100px\)\s*\{[\s\S]*\.history-detail\s*\{[^}]*position:\s*fixed",
        )
        self.assertRegex(styles, r"\.history-detail-title\s*\{[^}]*text-overflow:\s*ellipsis")
        self.assertRegex(styles, r"\.history-detail-title\s*\{[^}]*white-space:\s*nowrap")
        self.assertNotRegex(styles, r"\.history-detail-title\s*\{[^}]*-webkit-line-clamp")
        self.assertRegex(styles, r"\.history-filter-summary\s*\{[^}]*cursor:\s*pointer")
        self.assertRegex(styles, r"\.history-filter-summary::after\s*\{[^}]*transform:\s*rotate\(-45deg\)")
        self.assertRegex(styles, r"\.history-filter-block\[open\] > \.history-filter-summary::after\s*\{[^}]*transform:\s*rotate\(45deg\)")
        self.assertRegex(styles, r"\.history-filter-block:not\(\[open\]\) > \.history-filter-list\s*\{[^}]*display:\s*none")
        self.assertRegex(styles, r"\.history-filter-button\s*\{[^}]*min-height:\s*36px")
        self.assertRegex(styles, r"\.history-filter-button \.history-filter-count\s*\{[^}]*border-inline-start:\s*1px solid")
        self.assertRegex(styles, r"\.history-filter-button \.history-filter-count\s*\{[^}]*background:\s*transparent")
        self.assertNotRegex(styles, r"\.history-filter-button \.history-filter-count\s*\{[^}]*border-radius:")
        self.assertRegex(styles, r"\.history-filter-heading-icon,\s*\.history-filter-icon\s*\{[^}]*stroke:\s*currentColor")
        self.assertRegex(styles, r"\.history-filter-button\[data-history-filter-key=\"orientation\"\]\s*\{[^}]*padding-left:\s*10px")
        self.assertRegex(
            styles,
            r"\.history-task-list\.history-view-grid \.history-task-card\.active \.history-task-thumb,\s*"
            r"\.history-task-list\.history-view-grid \.history-task-card\.selected \.history-task-thumb\s*\{[^}]*"
            r"border-radius:\s*var\(--radius\)[^}]*background:\s*var\(--surface-soft\)",
        )
        self.assertNotRegex(styles, r"\.history-task-card\.selected \.history-task-thumb\s*\{[^}]*border-radius:\s*var\(--radius\) var\(--radius\) 0 0")

    def test_history_grid_cards_use_solid_album_stacks(self) -> None:
        source = Path("codex_image/webui/frontend/src/history.ts").read_text(encoding="utf-8")
        styles = Path("codex_image/webui/static/styles/90-history.css").read_text(encoding="utf-8")

        card_body = _typescript_function_body(source, "taskCardHtml")
        self.assertIn("const imageCount = historyTaskGeneratedCount(task);", card_body)
        self.assertIn("const stackDepth = historyTaskStackDepth(imageCount);", card_body)
        self.assertIn('data-history-image-count="${String(imageCount)}"', card_body)
        self.assertIn('data-history-stack-depth="${String(stackDepth)}"', card_body)
        self.assertIn("historyTaskStackLayers(stackDepth)", card_body)
        self.assertNotIn('history-task-image-count', card_body)
        self.assertNotIn('history-task-active-badge', card_body)
        self.assertNotIn('translate("history.viewing")', card_body)
        self.assertEqual(card_body.count("<img "), 1)

        stack_depth_body = _typescript_function_body(source, "historyTaskStackDepth")
        self.assertIn("return Math.min(3, imageCount - 1);", stack_depth_body)

        stack_layers_body = _typescript_function_body(source, "historyTaskStackLayers")
        self.assertIn("Array.from({ length: stackDepth }", stack_layers_body)
        self.assertIn('class="history-task-stack-layer"', stack_layers_body)
        self.assertNotIn("<img", stack_layers_body)

        self.assertRegex(styles, r"\.history-task-thumb-frame\s*\{[^}]*border-radius:\s*var\(--radius\)")
        self.assertRegex(styles, r"\.history-task-thumb-frame\s*\{[^}]*width:\s*100%")
        self.assertRegex(styles, r"\.history-task-thumb-frame\s*\{[^}]*height:\s*100%")
        self.assertRegex(styles, r"\.history-task-thumb-frame\s*\{[^}]*box-shadow:\s*[^}]*inset 0 0 0 1px")
        self.assertRegex(styles, r"\.history-task-list\.history-view-grid \.history-task-card:not\(\[data-history-stack-depth=\"0\"\]\) \.history-task-thumb-frame\s*\{[^}]*width:\s*calc\(100%\s*-\s*var\(--history-task-stack-offset,\s*0px\)\)")
        self.assertRegex(styles, r"\.history-task-list\.history-view-grid \.history-task-card:not\(\[data-history-stack-depth=\"0\"\]\) \.history-task-thumb-frame\s*\{[^}]*height:\s*calc\(100%\s*-\s*var\(--history-task-stack-offset,\s*0px\)\)")
        self.assertNotRegex(styles, r"\.history-task-list\.history-view-grid \.history-task-card:not\(\[data-history-stack-depth=\"0\"\]\) \.history-task-thumb-frame\s*\{[^}]*border:")
        self.assertRegex(
            styles,
            r"\.history-task-list\.history-view-grid\s+"
            r"\.history-task-card\[data-history-stack-depth\]:not\(\[data-history-stack-depth=\"0\"\]\):not\(\.active\):not\(\.selected\)\s+"
            r"\.history-task-thumb\s*\{[^}]*background:\s*transparent",
        )
        self.assertRegex(styles, r"\.history-task-stack-layer\s*\{[^}]*position:\s*absolute")
        self.assertRegex(styles, r"\.history-task-stack-layer\s*\{[^}]*inset:\s*0 auto auto 0")
        self.assertRegex(styles, r"\.history-task-stack-layer\s*\{[^}]*width:\s*calc\(100%\s*-\s*var\(--history-task-stack-offset,\s*0px\)\)")
        self.assertRegex(styles, r"\.history-task-stack-layer\s*\{[^}]*height:\s*calc\(100%\s*-\s*var\(--history-task-stack-offset,\s*0px\)\)")
        self.assertRegex(styles, r"\.history-task-stack-layer\s*\{[^}]*border:\s*0")
        self.assertRegex(styles, r"\.history-task-stack-layer\s*\{[^}]*border-radius:\s*var\(--radius\)")
        self.assertRegex(styles, r"\.history-task-stack-layer\s*\{[^}]*background:\s*var\(--history-task-stack-layer-surface\)")
        self.assertRegex(styles, r"\.history-task-stack-layer\s*\{[^}]*box-shadow:")
        self.assertRegex(styles, r"\.history-task-stack-layer\s*\{[^}]*pointer-events:\s*none")
        self.assertNotRegex(styles, r"\.history-task-stack-layer\s*\{[^}]*clip-path")
        self.assertNotIn(".history-task-stack-layer::before", styles)
        self.assertRegex(styles, r"\.history-task-list\.history-view-grid \.history-task-card\[data-history-stack-depth=\"1\"\] \.history-task-stack-layer\[data-history-stack-layer=\"1\"\]")
        self.assertRegex(styles, r"\.history-task-list\.history-view-grid \.history-task-card\[data-history-stack-depth=\"2\"\] \.history-task-stack-layer\[data-history-stack-layer=\"2\"\]")
        self.assertRegex(styles, r"\.history-task-list\.history-view-grid \.history-task-card\[data-history-stack-depth=\"3\"\] \.history-task-stack-layer\[data-history-stack-layer=\"3\"\]")
        self.assertIn("--history-task-stack-offset: 6px", styles)
        self.assertIn("--history-task-stack-offset: 12px", styles)
        self.assertIn("--history-task-stack-offset: 18px", styles)
        self.assertIn("--history-task-stack-layer-offset: 6px", styles)
        self.assertIn("--history-task-stack-layer-offset: 12px", styles)
        self.assertIn("--history-task-stack-layer-offset: 18px", styles)
        self.assertIn("--history-task-stack-layer-surface: var(--history-stack-layer-1)", styles)
        self.assertIn("--history-task-stack-layer-surface: var(--history-stack-layer-2)", styles)
        self.assertIn("--history-task-stack-layer-surface: var(--history-stack-layer-3)", styles)
        self.assertRegex(styles, r"\.history-task-list\.history-view-grid \.history-task-card\[data-history-stack-depth=\"1\"\] \.history-task-stack-layer\[data-history-stack-layer=\"1\"\],[^}]*border:\s*1px solid color-mix")
        self.assertRegex(styles, r"transform:\s*translate\(var\(--history-task-stack-layer-offset\),\s*var\(--history-task-stack-layer-offset\)\)")
        self.assertRegex(styles, r"\.history-task-list\.history-view-list \.history-task-stack-layer\s*\{[^}]*display:\s*none")
        self.assertNotIn(".history-task-image-count", styles)
        self.assertNotIn(".history-task-active-badge", styles)
        self.assertNotIn(':root[data-theme="dark"] .history-task-card.selected', styles)

    def test_history_page_feature_contracts_are_complete(self) -> None:
        html = Path("codex_image/webui/static/history.html").read_text(encoding="utf-8")
        source = Path("codex_image/webui/frontend/src/history.ts").read_text(encoding="utf-8")
        detail_media_source = Path("codex_image/webui/frontend/src/history-detail-media.ts").read_text(encoding="utf-8")
        window_source = Path("codex_image/webui/frontend/src/history-window.ts").read_text(encoding="utf-8")
        position_runtime_source = Path("codex_image/webui/frontend/src/history-position-runtime.ts").read_text(encoding="utf-8")
        lightbox_source = Path("codex_image/webui/frontend/src/history-lightbox.ts").read_text(encoding="utf-8")

        for marker in [
            'id="historyModeList"',
            'id="historyOrientationList"',
            'id="historyBackendList"',
            'id="historyProviderList"',
            'id="historyPromptModeList"',
            'id="historyQualityList"',
            'id="historyRatioList"',
            'id="historySortToggle"',
            'data-history-sort="newest"',
            'data-history-sort="oldest"',
            'id="historyViewToggle"',
            'data-history-view="grid"',
            'data-history-view="list"',
            'class="history-task-list history-view-grid"',
            'id="historyManagementButton"',
            'id="historySelectionDock"',
            'id="historySelectionDockCount"',
            'id="historySearchClear"',
            'data-history-resizer="left"',
            'data-history-resizer="right"',
        ]:
            self.assertIn(marker, html)
        self.assertRegex(html, r'<details class="history-filter-block" data-history-filter-section="mode" open>')
        self.assertRegex(html, r'<details class="history-filter-block" data-history-filter-section="month" open>')
        self.assertRegex(html, r'<details class="history-filter-block history-filter-block-secondary" data-history-filter-section="backend">')
        self.assertRegex(html, r'<details class="history-filter-block history-filter-block-secondary" data-history-filter-section="provider">')
        self.assertIn('data-i18n="history.type"', html)
        self.assertNotIn('<select id="historySort"', html)
        self.assertNotIn('id="historyStatusList"', html)
        self.assertNotIn('id="historySizeList"', html)

        for marker in [
            "selectedTaskIds: new Set<string>()",
            'selectionAnchorTaskId: ""',
            "pendingDeleteTaskIds: [] as string[]",
            "exhausted: false",
            "newerExhausted: true",
            "syncStateFromUrl()",
            "updateHistoryUrl()",
            'view: "grid"',
            'mode: ""',
            "HISTORY_FILTER_QUERY_KEYS,",
            'from "./history-scroll-memory";',
            "type HistoryFilterKey = (typeof HISTORY_FILTER_QUERY_KEYS)[number];",
            'renderFacetButtons(els.modeList, "mode", summary.modes || [], translate("history.allTypes"))',
            'translate("history.type.textToImage")',
            'translate("history.type.imageToImage")',
            '["backend", "provider"] as const',
            "syncHistorySortMode()",
            "syncHistoryViewMode()",
            "applyHistorySort(",
            "layoutJustifiedHistoryGrid",
            "scheduleHistoryGridLayout",
            "historyGridLayoutSettings",
            "HISTORY_LAYOUT_STORAGE_KEY",
            "HISTORY_LAYOUT_DEFAULTS",
            "HISTORY_LAYOUT_LIMITS",
            "restoreHistoryLayoutPreference()",
            "bindHistoryResizerEvents()",
            'from "./history-lightbox"',
            'type HistoryLightboxTaskDirection',
            'type HistoryLightboxTaskNavigationContext',
            "initializeHistoryShell({",
            "historyDetailImagesLayoutClass",
            "startHistoryResize",
            "updateHistoryResize",
            "endHistoryResize",
            "preserveActiveTask",
            "activeHistoryTaskVisible",
            "ensureHistoryTaskCardVisible",
            'scrollIntoView({ block: "nearest", inline: "nearest" })',
            "resizeHistoryLayoutByKeyboard",
            "localStorage.setItem(HISTORY_LAYOUT_STORAGE_KEY",
            "setPointerCapture",
            "history-resizing",
            "applyHistoryGridRowLayout",
            "--history-task-card-width",
            "--history-task-row-height",
            'window.addEventListener("resize", () =>',
            "closeHistoryContextMenu();",
            "scheduleHistoryGridLayout();",
            "data-history-view",
            "history-view-grid",
            "history-view-list",
            "renderBulkToolbar()",
            "clearHistoryDeleteConfirmation",
            "renderSelectionDetail",
            "syncHistorySelectionDetail",
            'dataset.historyDetailMode = "selection"',
            "history-bulk-selecting",
            'els.page?.classList.toggle("history-bulk-selecting", count > 1 || historyState.selectionMode)',
            "archiveSelectedTasks",
            "deleteSelectedTasks",
            "trimMountedTaskCards(position === \"prepend\" ? \"bottom\" : \"top\")",
            "trimMountedTaskCards(edge: HistoryWindowEdge)",
            "historyState.loadedTaskIds.delete(taskId)",
            "taskWindowCursor",
            "historyWindowEdgeCursor",
            "captureHistoryScrollAnchor",
            "restoreHistoryScrollAnchor",
            "historyTaskCards",
            "direction: \"previous\"",
            "historyTaskPageQuery(",
            'loadTasks({ direction: "previous" })',
            'loadTasks({ direction: "next" })',
            'data-history-created-at',
            "historyState.exhausted",
            "historyState.newerExhausted",
            "historyState.selectedTaskIds",
            "visibleHistoryTaskIds",
            "applyHistoryTaskSelection",
            "clearHistoryTaskSelection",
            "toggleHistoryTaskSelection",
            "selectHistoryTaskRange",
            "handleHistoryTaskShortcutSelection",
            "shouldDeleteCurrentHistorySelection",
            "event.shiftKey",
            "event.metaKey",
            "event.ctrlKey",
            "data-history-enter-selection-mode",
            "historyState.selectionMode",
            'draggable="false"',
            "HISTORY_THUMBNAIL_CACHE_VERSION",
            "historyThumbnailUrl",
            "versionHistoryThumbnailUrl",
            "historyThumbnailRatioStyle",
            "formatHistorySizeLabel",
            "parseAspectRatioParts",
            "--history-task-thumb-ratio",
            "--history-task-card-ratio",
            "data-history-meta-kind",
            'parseAspectRatioParts(task.size, "x")',
            'parseAspectRatioParts(task.ratio, ":")',
            'url.includes("/outputs/thumbnails/")',
            'const separator = url.includes("?") ? "&" : "?";',
            "thumb-768-fit",
            "v=${HISTORY_THUMBNAIL_CACHE_VERSION}",
            'els.taskList?.addEventListener("dragstart"',
            "event.preventDefault()",
            "aria-current",
            "role=\"listitem\"",
            "history-detail-title",
            "history-detail-actions-result",
            "history-detail-actions-management",
            "const hasSelectedOutputs = selectedCount > 0",
            'translate("history.downloadImage")',
            "history-prompt-compare",
            "outputs.zip",
            "HISTORY_REFERENCE_HANDOFF_KEY",
            "data-history-reference-handoff-url",
            "data-history-input-lightbox-index",
            "openHistoryInputLightbox",
            "openHistoryDetailLightbox",
            "openHistoryTaskLightbox",
            "openHistoryTaskLightboxByDirection",
            "historyAdjacentTaskId",
            'openHistoryLightbox(urls, index, {',
            'taskId: historyState.selectedTaskId',
            "onTaskNavigate: openHistoryTaskLightboxByDirection",
            'addEventListener("dblclick"',
            "try {",
            "catch (error)",
        ]:
            self.assertIn(marker, source)
        for function_name in (
            "syncStateFromUrl",
            "updateHistoryUrl",
            "bindEvents",
        ):
            self.assertIn(
                "for (const key of HISTORY_FILTER_QUERY_KEYS)",
                _typescript_function_body(source, function_name),
            )
        self.assertIn(
            "for (const key of HISTORY_FILTER_QUERY_KEYS)",
            _typescript_function_body(source, "historyPageQueryInput"),
        )
        self.assertIn('params.set("direction", input.direction)', position_runtime_source)
        update_resize_body = _typescript_function_body(source, "updateHistoryResize")
        apply_pending_resize_body = _typescript_function_body(source, "applyPendingHistoryResize")
        start_resize_body = _typescript_function_body(source, "startHistoryResize")
        end_resize_body = _typescript_function_body(source, "endHistoryResize")
        self.assertIn("if (historyGridLayoutFrame) return;", source)
        self.assertNotIn("window.cancelAnimationFrame(historyGridLayoutFrame)", source)
        self.assertIn("scheduleHistoryGridLayout({ keepTaskId });", source)
        self.assertIn("activeHistoryResizer.latestX = event.clientX;", update_resize_body)
        self.assertIn("if (historyResizeFrame) return;", update_resize_body)
        self.assertIn("window.requestAnimationFrame(() => applyPendingHistoryResize())", update_resize_body)
        self.assertNotIn("getBoundingClientRect", update_resize_body)
        self.assertNotIn("applyHistoryLayoutWidths", update_resize_body)
        self.assertIn("maxCombinedWidth: historyLayoutMaxCombinedWidth()", start_resize_body)
        self.assertIn("resize.maxCombinedWidth", apply_pending_resize_body)
        self.assertNotIn("layoutJustifiedHistoryGrid", apply_pending_resize_body)
        self.assertNotIn("persist: true", update_resize_body)
        self.assertIn("localStorage.setItem(HISTORY_LAYOUT_STORAGE_KEY", end_resize_body)
        self.assertIn("applyPendingHistoryResize(resize);", end_resize_body)
        self.assertIn("layoutHistoryGridAfterResize(resize);", end_resize_body)

        for marker in [
            "export function taskOutputRecords",
            "export function taskInputRecords",
            "export function historyDetailImagesLayoutClass",
            "function parseSizeParts",
            "function outputOrientation",
            "history-detail-images-multi",
            "history-detail-images-count-${Math.min(records.length, 4)}",
            "history-detail-images-${orientation}",
            "history-detail-images-stack",
            "export function historyDetailImagesHtml",
            "export function historyInputReferencesHtml",
            "export function historyLightboxUrlsFromTask",
            "export function historyInputLightboxUrlsFromTask",
            "class=\"history-detail-image history-detail-output-card",
            "class=\"history-detail-image-media\"",
            "class=\"history-detail-image-actions\"",
            "function outputRevisedPromptHtml",
            "class=\"history-detail-output-prompt\"",
            "class=\"history-detail-output-prompt-text\"",
            'data-history-copy-output-prompt-index="${record.index}"',
            "record.revisedPrompt",
            "class=\"history-detail-overlay-button primary\"",
            "data-history-lightbox-index",
            "data-history-output-selected-task-id",
            "data-history-reference-handoff-url",
            "class=\"history-detail-inputs\"",
            "class=\"history-detail-input-thumb\"",
            "data-history-input-lightbox-index",
            "input_sources",
            "input_thumbnail_urls",
        ]:
            self.assertIn(marker, detail_media_source)

        for marker in [
            "export function openHistoryLightbox",
            "export function closeHistoryLightbox",
            "export function isHistoryLightboxOpen",
            "function showPreviousHistoryLightboxImage",
            "function showNextHistoryLightboxImage",
            "lightboxScaleFromWheel",
            'addEventListener("wheel"',
            "{ passive: false }",
            'addEventListener("mousedown"',
            'window.addEventListener("mousemove"',
            'event.key === "ArrowLeft"',
            'event.key === "ArrowRight"',
            'event.key === "ArrowUp"',
            'event.key === "ArrowDown"',
            'event.key === "PageUp"',
            'event.key === "PageDown"',
            "onTaskNavigate",
            "taskId",
            "showPreviousHistoryTask",
            "showNextHistoryTask",
            "history-lightbox-counter",
            "data-history-lightbox-image",
            'class="drawer-close-icon"',
            '<path d="M6 6l12 12M18 6L6 18"></path>',
        ]:
            self.assertIn(marker, lightbox_source)
        self.assertNotIn('data-history-lightbox-close aria-label="${escapeHtml(translate("history.closePreview"))}">×</button>', lightbox_source)

        self.assertRegex(
            source,
            r"if \(taskButton\) \{[\s\S]*handleHistoryTaskShortcutSelection\(taskButton\.dataset\.historyTaskId \|\| \"\", event\)[\s\S]*historyState\.selectionMode[\s\S]*toggleHistoryTaskSelection\(taskId\)[\s\S]*applyHistoryTaskSelection\(\[taskId\], taskId, taskId\)",
        )
        self.assertIn("function handleHistoryTaskArrowNavigation", source)
        self.assertIn("isHistoryTaskArrowKey(event.key)", source)
        self.assertIn("historyTaskArrowTargetCard(els.taskList, taskId, event.key, historyState.view)", source)
        self.assertIn('historyState.view === "list" && (event.key === "ArrowLeft" || event.key === "ArrowRight")', source)
        self.assertIn('event.preventDefault();\n  event.stopPropagation();', source)
        self.assertIn('focusHistoryTaskButton(nextTaskId);', source)
        self.assertIn('applyHistoryTaskSelection([nextTaskId], nextTaskId, nextTaskId);', source)
        self.assertIn('if (handleHistoryTaskArrowNavigation(event)) return;', source)

        for marker in [
            "export const HISTORY_TASK_ARROW_KEYS",
            '["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown"]',
            "export function isHistoryTaskArrowKey",
            "function historyGridVerticalArrowTargetCard",
            "candidate.x - current.x",
            "primaryDistance * 10000 + dx",
            "export function historyTaskArrowTargetCard",
            'view: "grid" | "list"',
            'if (key === "ArrowLeft") return cards[currentIndex - 1] ?? null;',
            'if (key === "ArrowRight") return cards[currentIndex + 1] ?? null;',
            "export type HistoryWindowDirection",
            "export type HistoryWindowEdge",
            "export function historyTaskCards",
            "export function encodeHistoryCursor",
            "new TextEncoder().encode(raw)",
            "return btoa(binary)",
            "historyWindowEdgeCursor",
            "captureHistoryScrollAnchor",
            "restoreHistoryScrollAnchor",
            "root.scrollTop +=",
        ]:
            self.assertIn(marker, window_source)
        self.assertNotIn("CSS.escape", window_source)

        self.assertIn("backend", source)
        self.assertIn("provider", source)
        self.assertIn("function historyTaskSourceLabel", source)
        self.assertIn("function historyBackendDisplayLabel", source)
        self.assertIn("const source = historyTaskSourceLabel(task)", source)
        self.assertIn("task.provider", source)
        self.assertLess(source.index("task.provider"), source.index("task.backend"))
        self.assertIn('if (value === "codex_images") return "Codex Image";', source)
        self.assertIn('if (value === "codex_responses") return "Codex Responses";', source)
        self.assertIn('if (value === "openai_images") return "API Image";', source)
        self.assertIn('if (value === "openai_responses") return "API Responses";', source)
        self.assertIn("function historyBackendChannelLabel", source)
        self.assertIn('if (value === "openai_responses") return "Responses";', source)
        self.assertIn('<span>${escapeHtml(historyTaskSourceLabel(task))}</span>', source)
        self.assertIn("orientation", source)
        self.assertIn("prompt_mode", source)
        self.assertIn("quality", source)
        self.assertIn("HISTORY_RATIO_OTHER_VALUE", source)
        self.assertIn('translate("history.ratioOther")', source)
        self.assertIn('if (key === "orientation")', source)
        self.assertIn('translate("output.portrait")', source)
        self.assertIn('translate("output.landscape")', source)
        self.assertIn('translate("output.square")', source)
        self.assertIn("historyOrientationIconHtml", source)
        self.assertIn("historyFilterButtonLabelHtml", source)
        self.assertIn("history-filter-icon", source)
        self.assertIn("history-filter-icon-portrait", source)
        self.assertIn("history-filter-icon-landscape", source)
        self.assertIn("history-filter-icon-square", source)
        self.assertIn('data-history-filter-key="${key}"', source)
        self.assertNotIn('formatTranslation("history.windowNotice"', source)
        self.assertNotIn('notice.className = "history-window-notice"', source)
        self.assertNotIn("statusList", source)
        self.assertNotIn("sizeList", source)
        self.assertIn("sort", source)

    def test_history_resize_reuses_initial_grid_measurement(self) -> None:
        source = Path(
            "codex_image/webui/frontend/src/history.ts"
        ).read_text(encoding="utf-8")

        self.assertIn(
            "function captureHistoryGridLayoutSnapshot",
            source,
        )
        capture_body = _typescript_function_body(
            source,
            "captureHistoryGridLayoutSnapshot",
        )
        start_body = _typescript_function_body(
            source,
            "startHistoryResize",
        )
        apply_body = _typescript_function_body(
            source,
            "applyPendingHistoryResize",
        )
        end_body = _typescript_function_body(
            source,
            "endHistoryResize",
        )
        layout_body = _typescript_function_body(
            source,
            "layoutJustifiedHistoryGrid",
        )

        self.assertIn("root.clientWidth", capture_body)
        self.assertIn("window.getComputedStyle(root)", capture_body)
        self.assertIn(
            "gridLayoutSnapshot: captureHistoryGridLayoutSnapshot()",
            start_body,
        )
        self.assertNotIn("layoutJustifiedHistoryGrid", apply_body)
        self.assertIn("layoutHistoryGridAfterResize(resize);", end_body)
        self.assertIn(
            "resize.startLeft + resize.startRight",
            source,
        )
        self.assertNotIn("root.clientWidth", apply_body)
        self.assertNotIn("window.getComputedStyle", apply_body)
        self.assertIn(
            "options.snapshot === undefined",
            layout_body,
        )
        self.assertIn(
            ": options.snapshot",
            layout_body,
        )
        self.assertIn("bindHistoryGridResizeObserver()", source)
        self.assertIn('resizer.addEventListener("lostpointercapture"', source)
        self.assertIn('window.addEventListener("blur", endHistoryResize)', source)
        self.assertIn('document.addEventListener("visibilitychange"', source)

    def test_history_reference_handoff_is_consumed_by_main_page(self) -> None:
        history_source = Path("codex_image/webui/frontend/src/history.ts").read_text(encoding="utf-8")
        input_source = Path("codex_image/webui/frontend/src/input-sources.ts").read_text(encoding="utf-8")
        boot_source = Path("codex_image/webui/frontend/src/boot.ts").read_text(encoding="utf-8")

        self.assertIn('localStorage.setItem(HISTORY_REFERENCE_HANDOFF_KEY', history_source)
        self.assertIn('window.location.href = "/"', history_source)
        self.assertIn("function restoreHistoryReferenceHandoff()", input_source)
        self.assertIn("localStorage.removeItem(HISTORY_REFERENCE_HANDOFF_KEY)", input_source)
        self.assertIn("imageFileFromUrl(item.url", input_source)
        self.assertIn('restoreHistoryReferenceHandoff,', input_source)
        self.assertIn('call(methods, "restoreHistoryReferenceHandoff")', boot_source)

    def test_history_lightbox_keyboard_is_isolated_from_task_grid_navigation(self) -> None:
        source = Path("codex_image/webui/frontend/src/history.ts").read_text(encoding="utf-8")
        lightbox_source = Path("codex_image/webui/frontend/src/history-lightbox.ts").read_text(encoding="utf-8")

        self.assertIn("function handleHistoryTaskArrowNavigation", source)
        self.assertIn("if (isHistoryLightboxOpen()) return false;", source)
        self.assertLess(
            source.index("if (isHistoryLightboxOpen()) return false;"),
            source.index("if (!isHistoryTaskArrowKey(event.key)) return false;"),
        )
        self.assertIn("historyLightboxEl.tabIndex = -1;", lightbox_source)
        self.assertIn("lightbox.focus({ preventScroll: true });", lightbox_source)
        self.assertIn("const action = lightboxActionForKey(event.key);", lightbox_source)
        self.assertRegex(
            lightbox_source,
            r'event\.key === "ArrowLeft" && action === "previous-image"[\s\S]*?'
            r"event\.preventDefault\(\);\s*event\.stopPropagation\(\);[\s\S]*?"
            r"showPreviousHistoryLightboxImage\(\);",
        )
        self.assertRegex(
            lightbox_source,
            r'event\.key === "ArrowUp" && action === "previous-task"[\s\S]*?'
            r"event\.preventDefault\(\);\s*event\.stopPropagation\(\);[\s\S]*?"
            r"showPreviousHistoryTask\(\);",
        )

    def test_history_lightbox_task_navigation_skips_tasks_without_preview_images(self) -> None:
        source = Path("codex_image/webui/frontend/src/history.ts").read_text(encoding="utf-8")

        self.assertIn("async function historyTaskLightboxDetail", source)
        self.assertIn("const urls = historyLightboxUrlsFromTask(detail);", source)
        self.assertRegex(
            source,
            r"async function openHistoryTaskLightboxByDirection\([\s\S]*const visitedTaskIds = new Set<string>\(\[currentTaskId\]\);[\s\S]*for \(;;\) \{",
        )
        self.assertIn("if (visitedTaskIds.has(nextTaskId))", source)
        self.assertIn("visitedTaskIds.add(nextTaskId);", source)
        self.assertIn("if (!urls.length) {", source)
        self.assertIn("cursorTaskId = nextTaskId;", source)
        self.assertIn("continue;", source)
        self.assertIn('setText(els.resultSummary, translate("history.noMore"));', source)

    def test_history_task_mutations_preserve_scroll_window(self) -> None:
        source = Path("codex_image/webui/frontend/src/history.ts").read_text(encoding="utf-8")

        for marker in [
            "removeHistoryTaskIdsFromWindow",
            "upsertHistoryTaskSummaryCard",
            "refreshHistoryWindowAfterMutation",
            "captureHistoryScrollAnchor(els.taskList)",
            "restoreHistoryScrollAnchor(els.taskList, anchor)",
        ]:
            self.assertIn(marker, source)

        for function_name in [
            "archiveHistoryTaskIds",
            "archiveSingleTask",
            "deleteSelectedTasks",
            "deleteSingleHistoryTask",
            "deleteUnselectedOutputs",
        ]:
            with self.subTest(function_name=function_name):
                body = _typescript_function_body(source, function_name)
                self.assertNotIn("loadTasks({ reset: true })", body)

        delete_body = _typescript_function_body(source, "deleteSelectedTasks")
        self.assertIn("historyState.pendingDeleteTaskIds", delete_body)
        self.assertIn("Promise.allSettled", delete_body)
        self.assertIn("historyState.selectedTaskIds = new Set(failedIds)", delete_body)
        self.assertNotIn("for (const taskId of ids)", delete_body)

        context_body = _typescript_function_body(source, "handleHistoryContextMenuAction")
        self.assertIn("shouldDeleteCurrentHistorySelection(taskId)", context_body)
        self.assertIn("deleteHistoryContextSelectedTasks([...historyState.selectedTaskIds])", context_body)

        guard_body = _typescript_function_body(source, "shouldDeleteCurrentHistorySelection")
        self.assertIn("historyState.selectedTaskIds.size > 1", guard_body)
        self.assertIn("historyState.selectedTaskIds.has(taskId)", guard_body)

        selection_visuals_body = _typescript_function_body(source, "updateTaskSelectionVisuals")
        self.assertIn("historyState.selectedTaskIds.size === 1", selection_visuals_body)
        self.assertIn("historyState.selectedTaskIds.has(cardTaskId)", selection_visuals_body)
        self.assertIn('setAttribute("aria-pressed", selected ? "true" : "false")', selection_visuals_body)

    def test_history_page_polish_i18n_and_detail_actions_contracts(self) -> None:
        html = Path("codex_image/webui/static/history.html").read_text(encoding="utf-8")
        source = Path("codex_image/webui/frontend/src/history.ts").read_text(encoding="utf-8")
        styles = Path("codex_image/webui/static/styles/90-history.css").read_text(encoding="utf-8")
        i18n_source = "\n".join(
            [
                Path("codex_image/webui/frontend/src/i18n/zh-cn.ts").read_text(encoding="utf-8"),
                Path("codex_image/webui/frontend/src/i18n/en.ts").read_text(encoding="utf-8"),
            ]
        )

        for marker in [
            'class="history-program-brand"',
            'data-i18n-attr="aria-label:history.homeAria"',
            'data-i18n="history.backToGenerator"',
            'data-i18n="history.title"',
            'data-i18n-attr="placeholder:history.searchPlaceholder"',
            'data-i18n="history.promptMode"',
            'data-i18n="history.quality"',
            'data-i18n="history.ratio"',
            'data-i18n="history.grid"',
            'data-i18n="history.list"',
            '<div id="historyLoadSentinel"',
            'data-history-load-more',
            'role="status"',
        ]:
            self.assertIn(marker, html)
        self.assertNotIn('data-i18n="history.status"', html)
        self.assertNotIn('data-i18n="history.size"', html)
        self.assertNotIn('<button id="historyLoadSentinel"', html)
        self.assertNotIn('class="brand-mark"', html)
        self.assertNotIn("⌘", html)

        for marker in [
            'import { LOCALE_CHANGE_EVENT, formatTranslation, translate } from "./i18n";',
            'from "./history-shell";',
            "initializeHistoryShell({",
            'document.addEventListener(LOCALE_CHANGE_EVENT',
            'HISTORY_TASK_REUSE_HANDOFF_KEY',
            'data-history-reuse-task',
            'data-history-archive-task',
            'data-history-delete-task',
            'data-history-copy-prompt-kind',
            'data-history-copy-prompt-kind="${escapeHtml(kind)}"',
            'copyPromptToClipboard',
            'copyOutputPromptToClipboard',
            'promptTextForKind',
            'outputPromptTextForIndex',
            'revisedPromptText',
            'outputRevisedPromptTexts',
            'hasDistinctOutputRevisedPrompts',
            'uniquePromptTexts',
            'normalizePromptForCompare',
            'const hasRevisedPanel = hasDistinctOutputPrompts ? false : addPanel("revised"',
            'translate("history.outputRevisedPromptNotice")',
            'history-prompt-panel-header',
            'data-history-copy-output-prompt-index',
            'reuseHistoryTask',
            'data-history-lightbox-url',
            'openHistoryLightbox',
            'closeHistoryLightbox',
            'data-history-load-more',
            'setLoadMoreState',
            'function maybeLoadMoreFromScroll(',
            'els.taskList?.addEventListener("scroll"',
            'function openHistoryContextMenu',
            'historyState.selectedTaskIds.has(clickedTaskId)',
            'applyHistoryTaskSelection([clickedTaskId], clickedTaskId, clickedTaskId)',
            'updateTaskSelectionVisuals()',
            'historySingleContextMenuHtml',
            'historyMultiContextMenuHtml',
            'data-history-context-action="${escapeHtml(action)}"',
            'els.taskList?.addEventListener("contextmenu"',
            'event.key !== "ContextMenu"',
            'event.shiftKey && event.key === "F10"',
            'historyContextButton("reuse", translate("history.reuseTask"))',
            'historyContextButton("download-selected", translate("history.downloadSelectedTasks"))',
            'historyContextButton("archive-selected", translate("action.archive"))',
            'historyContextButton("restore-selected", translate("archive.restore"))',
            'historyContextButton("delete-selected", confirmingDelete ? translate("history.confirmDeleteSelected")',
            'data-history-bulk-archive',
            'data-history-bulk-restore',
            'data-history-bulk-delete',
            'data-history-bulk-clear',
            'deleteSingleHistoryTask(taskId, { confirmInMenu: true })',
            'downloadHistoryTasks(taskIds)',
        ]:
            self.assertIn(marker, source)
        self.assertNotIn('historyContextButton("copy-prompts"', source)
        self.assertNotIn('historyContextButton("copy-ids"', source)
        self.assertNotIn('els.sentinel?.addEventListener("click"', source)
        write_clipboard_body = _typescript_function_body(source, "writeClipboardText")
        self.assertIn("await navigator.clipboard.writeText(text)", write_clipboard_body)
        self.assertIn("} catch {", write_clipboard_body)
        self.assertIn('document.execCommand("copy")', write_clipboard_body)

        for marker in [
            '"history.homeAria": "返回 iLab CONJURE 生成页"',
            '"history.homeAria": "Back to iLab CONJURE generator"',
            '"history.searchPlaceholder": "搜索提示词或任务 ID"',
            '"history.searchPlaceholder": "Search prompts or task ID"',
            '"history.copyPrompt": "复制提示词"',
            '"history.copyPrompt": "Copy prompt"',
            '"history.copyPromptShort": "复制"',
            '"history.copyPromptShort": "Copy"',
            '"history.copyOutputPromptPanel": "复制图 {index} 优化提示词"',
            '"history.copyOutputPromptPanel": "Copy image {index} revised prompt"',
            '"history.outputRevisedPromptTitle": "图 {index} 优化提示词"',
            '"history.outputRevisedPromptTitle": "Image {index} revised prompt"',
            '"history.outputRevisedPromptNotice": "每张图的优化提示词不同，见对应图片下方。"',
            '"history.outputRevisedPromptNotice": "Each image has its own revised prompt below the image."',
            '"history.promptSubmitted": "优化提示词"',
            '"history.promptSubmitted": "Optimized prompt"',
            '"history.viewing": "查看中"',
            '"history.viewing": "Viewing"',
            '"history.reuseTask": "生成页查看"',
            '"history.reuseTask": "View in generator"',
            '"history.downloadImage": "下载图片"',
            '"history.downloadImage": "Download image"',
            '"status.reusedTask": "已在生成页打开任务 {taskId}"',
            '"status.reusedTask": "Opened task {taskId} in generator"',
            '"history.outputActions": "结果图操作"',
            '"history.outputActions": "Result image actions"',
            '"history.inputReferences": "输入参考图"',
            '"history.inputReferences": "Input references"',
            '"history.inputReferenceIndex": "输入参考图 {index}"',
            '"history.inputReferenceIndex": "Input reference {index}"',
            '"history.downloadSelectedTasks": "批量下载"',
            '"history.downloadSelectedTasks": "Batch download"',
            '"history.contextMenuLabel": "历史任务右键菜单"',
            '"history.contextMenuLabel": "History task context menu"',
            '"history.confirmDeleteSelected": "确认删除已选"',
            '"history.confirmDeleteSelected": "Confirm selected delete"',
        ]:
            self.assertIn(marker, i18n_source)

        self.assertRegex(styles, r"\.history-task-card\.active,\s*\.history-task-card\.selected\s*\{[^}]*border-color:\s*transparent")
        self.assertRegex(styles, r"\.history-task-card\.active,\s*\.history-task-card\.selected\s*\{[^}]*background:\s*var\(--primary\)")
        self.assertRegex(styles, r"\.history-task-card\.active,\s*\.history-task-card\.selected\s*\{[^}]*box-shadow:\s*none")
        self.assertNotIn(".history-task-card.active::before", styles)
        self.assertNotIn(".history-task-card.selected::after", styles)
        self.assertRegex(
            styles,
            r"\.history-task-list\.history-view-grid \.history-task-card\.active,\s*"
            r"\.history-task-list\.history-view-grid \.history-task-card\.selected"
            r"\s*\{[^}]*background:\s*var\(--primary\)",
        )
        self.assertNotRegex(
            styles,
            r"\.history-task-list\.history-view-grid \.history-task-card\.active,\s*"
            r"\.history-task-list\.history-view-grid \.history-task-card\.selected"
            r"\s*\{[^}]*0 0 0 2px var\(--primary\)",
        )
        self.assertRegex(styles, r"\.history-task-list\.history-view-grid \.history-task-card\.active \.history-task-thumb,\s*\.history-task-list\.history-view-grid \.history-task-card\.selected \.history-task-thumb\s*\{[^}]*border-radius:\s*var\(--radius\)")
        self.assertRegex(styles, r"\.history-task-list\.history-view-grid \.history-task-card\.active \.history-task-thumb,\s*\.history-task-list\.history-view-grid \.history-task-card\.selected \.history-task-thumb\s*\{[^}]*background:\s*var\(--surface-soft\)")
        self.assertRegex(styles, r"\.history-task-list\.history-view-grid \.history-task-card\.active \.history-task-copy,\s*\.history-task-list\.history-view-grid \.history-task-card\.selected \.history-task-copy\s*\{[^}]*background:\s*transparent")
        self.assertRegex(styles, r"\.history-task-list\.history-view-grid \.history-task-card\.active \.history-task-title,\s*\.history-task-list\.history-view-grid \.history-task-card\.selected \.history-task-title")
        self.assertNotIn(".history-task-active-badge", styles)
        self.assertNotIn(".history-task-image-count", styles)
        self.assertRegex(styles, r"\.history-program-brand\s*\{[^}]*display:\s*flex")
        self.assertRegex(styles, r"\.history-program-brand \.brand-mark\s*\{[^}]*width:")
        self.assertNotIn(".history-program-name", styles)
        self.assertNotRegex(styles, r"\.history-task-card\.selected\s*\{[^}]*outline:")
        self.assertRegex(styles, r"\.history-task-card\.selected \.history-task-copy\s*\{[^}]*background:")
        self.assertRegex(styles, r"\.history-task-list\.history-view-grid \.history-task-copy\s*\{[^}]*min-height:\s*0")
        self.assertRegex(styles, r"\.history-task-list\.history-view-grid \.history-task-title\s*\{[^}]*white-space:\s*nowrap")
        self.assertNotRegex(styles, r"\.history-task-list\.history-view-grid \.history-task-title\s*\{[^}]*-webkit-line-clamp:\s*2")
        self.assertIn("isHistorySelectAllTasksShortcut", source)
        self.assertIn("historySelectAllTaskIds(visibleHistoryTaskIds())", source)
        self.assertIn("handleHistorySelectAllShortcut(event)", source)
        self.assertIn("window.getSelection()?.removeAllRanges()", source)
        self.assertRegex(styles, r"\.history-task-list\.history-view-grid \.history-task-open\s*\{[^}]*gap:\s*0")
        self.assertNotIn(".history-task-select", styles)
        self.assertRegex(styles, r"\.history-detail-image-preview\s*\{[^}]*place-items:\s*center")
        self.assertRegex(styles, r"\.history-detail-image-preview\s*\{[^}]*justify-items:\s*center")
        self.assertRegex(styles, r"\.history-detail-image-preview img\s*\{[^}]*margin:\s*0 auto")
        self.assertRegex(styles, r"\.history-detail-image\s*\{[^}]*position:\s*relative")
        self.assertRegex(styles, r"\.history-detail-image\s*\{[^}]*overflow:\s*hidden")
        self.assertRegex(styles, r"\.history-detail-output-index\s*\{[^}]*position:\s*absolute")
        self.assertRegex(styles, r"\.history-detail-images\s*\{[^}]*grid-template-columns:\s*minmax\(0,\s*1fr\)")
        self.assertRegex(styles, r"\.history-detail-images\s*\{[^}]*justify-items:\s*center")
        self.assertRegex(styles, r"\.history-detail-images\s*\{[^}]*width:\s*100%")
        self.assertRegex(styles, r"\.history-detail-images-multi\s*\{[^}]*grid-template-columns:\s*repeat\(auto-fit,\s*minmax\(min\(180px,\s*100%\),\s*1fr\)\)")
        self.assertRegex(styles, r"\.history-detail-images-multi\s*\{[^}]*justify-items:\s*stretch")
        self.assertRegex(styles, r"\.history-detail-images-multi\.history-detail-images-count-2\s*\{[^}]*grid-template-columns:\s*repeat\(auto-fit,\s*minmax\(min\(180px,\s*100%\),\s*1fr\)\)")
        self.assertRegex(styles, r"\.history-detail-images-multi\.history-detail-images-count-4\s*\{[^}]*grid-template-columns:\s*repeat\(auto-fit,\s*minmax\(min\(220px,\s*100%\),\s*1fr\)\)")
        self.assertRegex(styles, r"\.history-detail-images-multi\.history-detail-images-stack\s*\{[^}]*grid-template-columns:\s*minmax\(0,\s*1fr\)")
        self.assertRegex(styles, r"\.history-detail-images-multi\.history-detail-images-stack\s*\{[^}]*justify-items:\s*center")
        self.assertRegex(styles, r"\.history-detail-images-multi \.history-detail-image\s*\{[^}]*max-width:\s*none")
        self.assertRegex(styles, r"\.history-detail-images-stack \.history-detail-image\s*\{[^}]*width:\s*min\(100%,\s*760px\)")
        self.assertRegex(styles, r"\.history-detail-images-multi \.history-detail-image-preview\s*\{[^}]*min-height:\s*clamp")
        self.assertRegex(styles, r"\.history-detail-images-multi \.history-detail-image-preview img\s*\{[^}]*max-height:\s*clamp")
        self.assertRegex(styles, r"\.history-detail-images-stack \.history-detail-image-preview img\s*\{[^}]*width:\s*100%")
        self.assertRegex(styles, r"\.history-detail-images-stack \.history-detail-image-preview img\s*\{[^}]*max-height:\s*none")
        self.assertRegex(styles, r"\.history-detail-actions\s*\{[^}]*justify-content:\s*space-between")
        self.assertRegex(styles, r"\.history-detail-actions\s*\{[^}]*width:\s*100%")
        self.assertRegex(styles, r"\.history-detail-actions\s*\{[^}]*flex:\s*0\s+0\s+auto")
        self.assertRegex(styles, r"\.history-detail-actions-result\s*>\s*\*,\s*\.history-detail-actions-management\s*>\s*\*\s*\{[^}]*white-space:\s*nowrap")
        self.assertRegex(styles, r"\.history-detail-actions-management\s*\{[^}]*margin-left:\s*auto")
        self.assertRegex(styles, r"\.history-detail\s*\{[^}]*container-name:\s*history-detail")
        self.assertRegex(styles, r"\.history-detail\s*\{[^}]*container-type:\s*inline-size")
        self.assertRegex(
            styles,
            r"@container history-detail \(max-width:\s*340px\)\s*\{[\s\S]*?"
            r"\.history-detail-actions\s*\{[^}]*display:\s*grid[^}]*grid-template-columns:\s*minmax\(0,\s*1fr\)",
        )
        self.assertRegex(
            styles,
            r"@container history-detail \(max-width:\s*340px\)\s*\{[\s\S]*?"
            r"\.history-detail-actions-result\s*\{[^}]*grid-template-columns:\s*repeat\(2,\s*minmax\(0,\s*1fr\)\)",
        )
        self.assertRegex(
            styles,
            r"@container history-detail \(max-width:\s*340px\)\s*\{[\s\S]*?"
            r"\.history-detail-actions-management\s*\{[^}]*grid-template-columns:\s*repeat\(3,\s*minmax\(0,\s*1fr\)\)",
        )
        self.assertRegex(
            styles,
            r"@container history-detail \(max-width:\s*340px\)\s*\{[\s\S]*?"
            r"\.history-detail-actions-result\s*>\s*\*,\s*\.history-detail-actions-management\s*>\s*\*\s*\{[^}]*width:\s*100%",
        )
        self.assertLess(source.index('class="history-detail-actions-result"'), source.index('class="history-detail-actions-management"'))
        self.assertNotIn("history-detail-actions-primary", source)
        self.assertNotIn("history-detail-actions-output", source)
        self.assertNotIn("history-detail-output-selection-actions", styles)
        self.assertNotIn('class="history-detail-output-selection-actions"', source)
        self.assertIn('selectedCount > 1', source)
        self.assertIn('translate("history.downloadSelected")', source)
        self.assertIn('canDeleteUnselected && !deleteBlocked', source)
        self.assertIn('historyState.deleteUnselectedConfirmTaskId = ""', _typescript_function_body(source, "updateOutputSelection"))
        self.assertRegex(styles, r"\.history-detail-actions a\s*\{[^}]*text-decoration:\s*none")
        self.assertRegex(styles, r"\.history-detail-image-media\s*\{[^}]*position:\s*relative")
        self.assertRegex(styles, r"\.history-detail-image-media\s*\{[^}]*overflow:\s*hidden")
        self.assertRegex(styles, r"\.history-detail-image-actions\s*\{[^}]*position:\s*absolute")
        self.assertRegex(styles, r"\.history-detail-image-actions\s*\{[^}]*opacity:\s*0")
        self.assertRegex(styles, r"\.history-detail-image-actions\s*\{[^}]*pointer-events:\s*none")
        self.assertRegex(styles, r"\.history-detail-image-media:hover \.history-detail-image-actions,\s*\.history-detail-image-media:focus-within \.history-detail-image-actions\s*\{[^}]*opacity:\s*1")
        self.assertRegex(styles, r"\.history-detail-image-actions\s*\{[^}]*justify-content:\s*safe center")
        self.assertRegex(styles, r"\.history-detail-image-actions\s*\{[^}]*width:\s*100%")
        self.assertRegex(styles, r"\.history-detail-image-actions\s*>\s*\*\s*\{[^}]*white-space:\s*nowrap")
        self.assertRegex(styles, r"\.history-detail-overlay-button\s*\{[^}]*border-radius:\s*999px")
        self.assertRegex(styles, r"\.history-detail-overlay-button\.primary,\s*\.history-detail-overlay-button\[aria-pressed=\"true\"\]\s*\{[^}]*background:\s*var\(--primary\)")
        self.assertRegex(styles, r"\.history-detail-output-prompt\s*\{[^}]*border-top:\s*1px solid var\(--panel-border\)")
        self.assertRegex(styles, r"\.history-detail-output-prompt-header\s*\{[^}]*grid-template-columns:\s*minmax\(0,\s*1fr\)\s*auto")
        self.assertRegex(styles, r"\.history-detail-output-prompt-text\s*\{[^}]*white-space:\s*pre-wrap")
        self.assertRegex(styles, r"\.history-detail-output-prompt-text\s*\{[^}]*max-height:")
        self.assertRegex(styles, r"\.history-detail-output-prompt-text\s*\{[^}]*scrollbar-color:\s*var\(--scrollbar-thumb\)\s+var\(--scrollbar-track\)")
        self.assertRegex(styles, r"\.history-detail\s*\{[^}]*--history-prompt-font-size:\s*13px")
        self.assertRegex(styles, r"\.history-detail\s*\{[^}]*--history-prompt-line-height:\s*1\.6")
        self.assertRegex(styles, r"\.history-detail-output-prompt-header\s*\{[^}]*font-size:\s*var\(--history-prompt-font-size\)")
        self.assertRegex(styles, r"\.history-detail-output-prompt-text\s*\{[^}]*font-size:\s*var\(--history-prompt-font-size\)")
        self.assertRegex(styles, r"\.history-prompt-panel h3\s*\{[^}]*font-size:\s*var\(--history-prompt-font-size\)")
        self.assertRegex(styles, r"\.history-detail-prompt\s*\{[^}]*font-size:\s*var\(--history-prompt-font-size\)")
        self.assertRegex(styles, r"\.history-prompt-note\s*\{[^}]*border:\s*1px solid var\(--panel-border\)")
        self.assertRegex(styles, r"\.history-detail-inputs\s*\{[^}]*border-top:\s*1px solid")
        self.assertRegex(styles, r"\.history-detail-inputs-list\s*\{[^}]*display:\s*flex")
        self.assertRegex(styles, r"\.history-detail-input-thumb\s*\{[^}]*width:\s*54px")
        self.assertRegex(styles, r"\.history-detail-input-thumb\s*\{[^}]*opacity:\s*0\.72")
        self.assertRegex(styles, r"\.history-detail-input-thumb img\s*\{[^}]*object-fit:\s*cover")
        self.assertRegex(styles, r"\.history-prompt-panel-header\s*\{[^}]*grid-template-columns:\s*minmax\(0,\s*1fr\)\s*auto")
        self.assertRegex(styles, r"\.history-prompt-copy\.copied\s*\{[^}]*background:\s*var\(--primary-light\)")
        self.assertNotRegex(styles, r"\.history-results\s*\{[^}]*env\(safe-area-inset-bottom")
        self.assertRegex(styles, r"\.history-task-list\s*\{[^}]*env\(safe-area-inset-bottom")
        self.assertRegex(styles, r"\.history-task-list\.history-view-grid\s*\{[^}]*padding:\s*6px\s+15px\s+calc\(6px\s+\+\s+env\(safe-area-inset-bottom,\s*0px\)\)\s+4px")
        self.assertRegex(styles, r"\.history-results\s*\{[^}]*--history-toolbar-control-height:\s*36px")
        self.assertRegex(styles, r"\.history-view-toggle,\s*\.history-sort-toggle\s*\{[^}]*box-sizing:\s*border-box")
        self.assertRegex(styles, r"\.history-view-toggle,\s*\.history-sort-toggle\s*\{[^}]*height:\s*var\(--history-toolbar-control-height\)")
        self.assertRegex(styles, r"\.history-view-toggle,\s*\.history-sort-toggle\s*\{[^}]*--segmented-indicator-radius:\s*999px")
        self.assertRegex(styles, r"\.history-view-toggle,\s*\.history-sort-toggle\s*\{[^}]*border-radius:\s*999px")
        self.assertRegex(styles, r"\.history-view-button,\s*\.history-sort-button\s*\{[^}]*font-size:\s*13px")
        self.assertRegex(styles, r"\.history-view-button,\s*\.history-sort-button\s*\{[^}]*border-radius:\s*999px")
        self.assertRegex(styles, r"\.history-view-toggle \.segmented-indicator,\s*\.history-sort-toggle \.segmented-indicator\s*\{[^}]*border-radius:\s*999px")
        self.assertRegex(styles, r"\.history-sort-toggle\.segmented-indicator-host\s+\.history-sort-button\.active\s*\{[^}]*background:\s*transparent")
        self.assertNotIn(".history-sort-label", styles)
        self.assertRegex(styles, r"\.history-toolbar-actions \.control,\s*\.history-toolbar-actions \.ghost-button\.text-sm\s*\{[^}]*min-height:\s*var\(--history-toolbar-control-height\)")
        self.assertRegex(styles, r"\.history-toolbar-actions \.control,\s*\.history-toolbar-actions \.ghost-button\.text-sm\s*\{[^}]*font-size:\s*13px")
        self.assertRegex(styles, r"\.history-toolbar-actions \.control,\s*\.history-toolbar-actions \.ghost-button\.text-sm\s*\{[^}]*font-weight:\s*600")
        self.assertRegex(styles, r"\.history-load-sentinel\s*\{[^}]*position:\s*absolute")
        self.assertRegex(styles, r"\.history-load-sentinel\s*\{[^}]*bottom:\s*calc\(8px \+ env\(safe-area-inset-bottom")
        self.assertRegex(styles, r"\.history-load-sentinel\s*\{[^}]*width:\s*auto")
        self.assertRegex(styles, r"\.history-load-sentinel\s*\{[^}]*min-height:\s*24px")
        self.assertRegex(styles, r"\.history-load-sentinel\s*\{[^}]*pointer-events:\s*none")
        self.assertNotRegex(styles, r"\.history-load-sentinel\s*\{[^}]*cursor:\s*pointer")
        self.assertRegex(styles, r"\.history-context-menu\s*\{[^}]*position:\s*fixed")
        self.assertRegex(styles, r"\.history-context-menu\s*\{[^}]*z-index:\s*9300")
        self.assertRegex(styles, r"\.history-context-menu-button\s*\{[^}]*min-height:\s*30px")
        self.assertRegex(styles, r"\.history-context-menu-button\.danger\s*\{[^}]*color:\s*var\(--danger\)")
        self.assertNotIn(".history-window-notice", styles)
        self.assertRegex(styles, r"\.history-task-list\.history-view-grid \.history-task-meta span:not\(\[data-history-meta-kind=\"size\"\]\)\s*\{[^}]*display:\s*none")
        self.assertNotRegex(styles, r"\.history-page\.history-bulk-selecting \.history-toolbar-actions\s*\{")
        self.assertRegex(styles, r"\.history-results\s*\{[^}]*--history-toolbar-control-height:\s*36px")
        self.assertRegex(styles, r"\.history-toolbar\s*\{[^}]*grid-column:\s*1")
        self.assertRegex(styles, r"\.history-toolbar\s*\{[^}]*grid-row:\s*1")
        self.assertRegex(styles, r"\.history-action-row\s*\{[^}]*min-height:\s*44px")
        self.assertRegex(styles, r"\.history-action-row-primary\s*\{[^}]*background:\s*var\(--primary-light\)")
        self.assertRegex(styles, r"\.history-action-row-danger\s*\{[^}]*color:\s*var\(--danger\)")
        self.assertRegex(styles, r"@keyframes history-action-options-enter\s*\{")
        self.assertRegex(
            styles,
            r"@media \(prefers-reduced-motion: reduce\)[\s\S]*\.history-action-options\s*\{[^}]*animation:\s*none",
        )
        self.assertIn(".history-lightbox", styles)
        self.assertRegex(styles, r"body\.history-lightbox-open\s*\{[^}]*overflow:\s*hidden")
        self.assertRegex(styles, r"\.history-lightbox\s*\{[^}]*position:\s*fixed")
        self.assertRegex(styles, r"\.history-lightbox\s*\{[^}]*z-index:\s*9999")
        self.assertRegex(styles, r"\.history-lightbox\s*\{[^}]*display:\s*flex")
        self.assertRegex(styles, r"\.history-lightbox\s*\{[^}]*backdrop-filter:\s*blur\(10px\)")
        self.assertRegex(styles, r"\.history-lightbox img\s*\{[^}]*cursor:\s*grab")
        self.assertRegex(styles, r"\.history-lightbox img\s*\{[^}]*user-select:\s*none")
        self.assertRegex(styles, r"\.history-lightbox-close\s*\{[^}]*display:\s*inline-flex")
        self.assertRegex(styles, r"\.history-lightbox-close\s*\{[^}]*align-items:\s*center")
        self.assertNotIn(".history-lightbox-nav", styles)
        self.assertRegex(styles, r"\.history-lightbox-counter\s*\{[^}]*position:\s*absolute")
        self.assertNotIn(':root[data-theme="dark"] .history-task-card.selected', styles)

    def test_history_toolbar_uses_flat_semantic_action_hierarchy(self) -> None:
        html = Path("codex_image/webui/static/history.html").read_text(encoding="utf-8")
        action_panel = Path("codex_image/webui/frontend/src/history-action-panel.ts").read_text(encoding="utf-8")
        styles = Path("codex_image/webui/static/styles/90-history.css").read_text(encoding="utf-8")

        self.assertNotIn('id="historyBulkToolbar"', html)
        self.assertIn('data-history-open-backup', action_panel)
        self.assertIn('data-history-open-backup="selected"', action_panel)
        self.assertLess(
            action_panel.index('data-history-toggle-action-section="organize"'),
            action_panel.index('data-history-toggle-action-section="export"'),
        )
        self.assertLess(
            action_panel.index('data-history-open-backup="selected"'),
            action_panel.index('class="history-action-danger"'),
        )

        self.assertRegex(
            styles,
            r"\.history-view-toggle,\s*\.history-sort-toggle\s*\{[^}]*border:\s*0[^}]*background:\s*var\(--surface-soft\)",
        )
        self.assertRegex(styles, r"\.history-action-row\s*\{[^}]*border:\s*0[^}]*background:\s*var\(--surface-soft\)")
        self.assertRegex(styles, r"\.history-action-row-primary\s*\{[^}]*background:\s*var\(--primary-light\)")
        self.assertRegex(styles, r"\.history-action-row-danger\s*\{[^}]*background:\s*var\(--danger-soft\)")

    def test_history_detail_switch_keeps_existing_preview_until_next_images_are_ready(self) -> None:
        source = Path("codex_image/webui/frontend/src/history.ts").read_text(encoding="utf-8")

        load_body = _typescript_function_body(source, "loadTaskDetail")
        self.assertIn("let historyDetailLoadToken = 0", source)
        self.assertIn("const loadToken = ++historyDetailLoadToken", load_body)
        self.assertIn("const keepCurrentDetail", load_body)
        self.assertRegex(
            load_body,
            r"if \(keepCurrentDetail\) \{[\s\S]*history-detail-pending[\s\S]*\} else \{[\s\S]*renderDetailShell\(translate\(\"history\.loadingDetail\"\)\)",
        )
        self.assertIn('els.detail?.setAttribute("aria-busy", "true")', load_body)
        self.assertIn("await preloadHistoryDetailImages(detail)", load_body)
        self.assertIn("if (!isCurrentHistoryDetailLoad(loadToken, taskId)) return;", load_body)
        self.assertIn('els.detail?.removeAttribute("aria-busy")', load_body)

        current_guard_body = _typescript_function_body(source, "isCurrentHistoryDetailLoad")
        self.assertIn("loadToken === historyDetailLoadToken", current_guard_body)
        self.assertIn("historyState.selectedTaskId === taskId", current_guard_body)

        self.assertRegex(
            source,
            r"async function preloadHistoryDetailImage\(url: string\): Promise<boolean> \{[\s\S]*document\.createElement\(\"img\"\)[\s\S]*image\.decoding = \"async\"[\s\S]*await image\.decode\?\.\(\)",
        )

        shell_body = _typescript_function_body(source, "renderDetailShell")
        self.assertIn("historyState.detailTask = null", shell_body)
        self.assertIn('history-detail-empty-title', shell_body)
        self.assertIn('translate("history.detail")', shell_body)
        self.assertNotIn('translate("history.detailTitle")', shell_body)

    def test_history_task_reuse_handoff_is_consumed_by_main_page(self) -> None:
        history_source = Path("codex_image/webui/frontend/src/history.ts").read_text(encoding="utf-8")
        selection_source = Path("codex_image/webui/frontend/src/task-selection.ts").read_text(encoding="utf-8")
        tasks_source = Path("codex_image/webui/frontend/src/tasks.ts").read_text(encoding="utf-8")
        render_source = Path("codex_image/webui/frontend/src/task-list-render.ts").read_text(encoding="utf-8")
        boot_source = Path("codex_image/webui/frontend/src/boot.ts").read_text(encoding="utf-8")
        handoff_body = _typescript_function_body(selection_source, "restoreHistoryTaskReuseHandoff")

        self.assertIn('localStorage.setItem(HISTORY_TASK_REUSE_HANDOFF_KEY', history_source)
        self.assertIn('window.location.href = "/"', history_source)
        self.assertIn("async function restoreHistoryTaskReuseHandoff()", selection_source)
        self.assertIn("localStorage.removeItem(HISTORY_TASK_REUSE_HANDOFF_KEY)", handoff_body)
        self.assertIn("applyTaskToFormWithOutputLock(task)", handoff_body)
        self.assertNotIn("adoptTaskParameters(task)", handoff_body)
        self.assertNotIn("preserveOutputSettings: false", handoff_body)
        self.assertIn("await restoreTaskInputs(task", handoff_body)
        self.assertIn("await revealHistoryTaskInSidebar(task)", handoff_body)
        self.assertLess(
            handoff_body.index("await revealHistoryTaskInSidebar(task)"),
            handoff_body.index("applyTaskToFormWithOutputLock(task)"),
        )
        self.assertIn("/position/", tasks_source)
        self.assertIn("sidebarTaskRevealPagePlan", tasks_source)
        self.assertIn("scrollHistoryTaskCardIntoView", tasks_source)
        self.assertIn("historyTaskRevealLayoutReady", tasks_source)
        self.assertIn('groupItems.dataset.renderComplete === "true"', tasks_source)
        self.assertIn('groupItems.style.maxHeight === "none"', tasks_source)
        self.assertIn('behavior: "auto"', tasks_source)
        self.assertIn("state.expandedTaskGroupAnimationPending = false", tasks_source)
        self.assertIn('translate("taskGroup.current")', render_source)
        self.assertIn('restoreHistoryTaskReuseHandoff,', selection_source)
        self.assertIn('call(methods, "restoreHistoryTaskReuseHandoff")', boot_source)

    def test_history_contextual_action_panel_replaces_competing_top_toolbars(self) -> None:
        html = Path("codex_image/webui/static/history.html").read_text(encoding="utf-8")
        source = Path("codex_image/webui/frontend/src/history.ts").read_text(encoding="utf-8")
        styles = Path("codex_image/webui/static/styles/90-history.css").read_text(encoding="utf-8")

        self.assertNotIn('id="historyBulkToolbar"', html)
        self.assertNotIn('id="historyBackupButton"', html)
        self.assertNotIn('id="historyImportButton"', html)
        self.assertIn('id="historyManagementButton"', html)
        self.assertIn('id="historySelectionDock"', html)
        self.assertIn('id="historySelectionDockCount"', html)
        self.assertIn('data-history-open-management', html)
        self.assertIn('data-history-open-selection-actions', html)
        self.assertNotIn('data-history-task-select', source)
        self.assertNotIn('class="history-task-select"', source)
        self.assertIn('from "./history-action-panel"', source)
        self.assertIn("historyManagementPanelHtml", source)
        self.assertIn("historySelectionPanelHtml", source)
        self.assertIn("nextHistoryActionPanelSection", source)
        selection_render = _typescript_function_body(source, "renderSelectionDetail")
        selection_sync = _typescript_function_body(source, "syncHistorySelectionDetail")
        current_load = _typescript_function_body(source, "isCurrentHistoryDetailLoad")
        close_detail = _typescript_function_body(source, "closeDetail")
        self.assertNotIn("historyState.detailTask = null", selection_render)
        self.assertIn("historySelectionDetailResolution", selection_sync)
        self.assertIn("void loadTaskDetail(historyState.selectedTaskId)", selection_sync)
        self.assertIn("historyState.selectedTaskIds.size === 1", current_load)
        self.assertIn("historyState.selectedTaskIds.has(taskId)", current_load)
        self.assertIn("historyDetailCloseEffect", close_detail)
        self.assertIn('historyState.selectedTaskId = ""', close_detail)
        self.assertIn("historyState.detailTask = null", close_detail)
        self.assertRegex(
            styles,
            r"\.history-action-row\s*\{[^}]*min-height:\s*44px[^}]*border:\s*0[^}]*border-radius:\s*var\(--radius\)",
        )
        self.assertRegex(
            styles,
            r"@media \(max-width: 1100px\)[\s\S]*\.history-selection-dock\s*\{[^}]*display:\s*flex",
        )
        self.assertRegex(
            styles,
            r"@media \(min-width: 1101px\)[\s\S]*\.history-management-button\s*\{[^}]*display:\s*none",
        )

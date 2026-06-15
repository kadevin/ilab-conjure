from __future__ import annotations

import unittest
from pathlib import Path


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
    def test_history_page_uses_viewport_workbench_layout(self) -> None:
        html = Path("codex_image/webui/static/history.html").read_text(encoding="utf-8")
        styles = Path("codex_image/webui/static/styles/90-history.css").read_text(encoding="utf-8")

        self.assertIn('class="history-page"', html)
        self.assertIn('id="historyDetailClose"', html)
        self.assertIn('data-history-resizer="left"', html)
        self.assertIn('data-history-resizer="right"', html)
        self.assertIn('role="separator"', html)
        self.assertIn('class="history-filter-heading history-filter-heading-orientation"', html)
        self.assertIn('class="history-filter-heading-icon"', html)
        self.assertIn('data-i18n-attr="aria-label:history.resizeFilters"', html)
        self.assertIn('data-i18n-attr="aria-label:history.resizeDetail"', html)
        self.assertRegex(styles, r"\.history-page\s*\{[^}]*height:\s*100dvh")
        self.assertRegex(styles, r"\.history-page\s*\{[^}]*overflow:\s*hidden")
        self.assertRegex(styles, r"\.history-page\s*\{[^}]*--history-sidebar-width:\s*280px")
        self.assertRegex(styles, r"\.history-page\s*\{[^}]*--history-detail-width:\s*380px")
        self.assertRegex(styles, r"\.history-page\s*\{[^}]*grid-template-columns:[^}]*clamp\(220px,\s*var\(--history-sidebar-width\),\s*420px\)[^}]*var\(--history-resizer-width\)[^}]*minmax\(360px,\s*1fr\)[^}]*clamp\(300px,\s*var\(--history-detail-width\),\s*620px\)")
        self.assertRegex(styles, r"\.history-resizer\s*\{[^}]*cursor:\s*col-resize")
        self.assertRegex(styles, r"\.history-resizer\s*\{[^}]*touch-action:\s*none")
        self.assertRegex(styles, r"\.history-resizer::after\s*\{[^}]*background-image:\s*[\s\S]*linear-gradient")
        self.assertRegex(styles, r"\.history-resizer::after\s*\{[^}]*background-position:[\s\S]*calc\(50%\s*-\s*4px\)\s+center[\s\S]*50%\s+center[\s\S]*calc\(50%\s*\+\s*4px\)\s+center")
        self.assertRegex(styles, r"\.history-resizer::after\s*\{[^}]*background-size:[\s\S]*1px\s+34px[\s\S]*1px\s+38px[\s\S]*1px\s+34px")
        self.assertRegex(styles, r"\.history-resizer::after\s*\{[^}]*opacity:\s*0\.72")
        self.assertRegex(styles, r"\.history-resizer:hover::before,\s*\.history-resizer:focus-visible::before,\s*\.history-page\.history-resizing \.history-resizer::before\s*\{[^}]*background:\s*var\(--primary\)")
        self.assertRegex(styles, r"\.history-resizer:hover::after,\s*\.history-resizer:focus-visible::after,\s*\.history-page\.history-resizing \.history-resizer::after\s*\{[^}]*background-color:\s*color-mix")
        self.assertRegex(styles, r"\.history-page\.history-resizing,\s*\.history-page\.history-resizing \*\s*\{[^}]*user-select:\s*none")
        self.assertRegex(styles, r"\.history-results\s*\{[^}]*position:\s*relative")
        self.assertRegex(styles, r"\.history-results\s*\{[^}]*grid-template-rows:\s*auto\s+minmax\(0,\s*1fr\)")
        self.assertRegex(styles, r"\.history-results\s*\{[^}]*padding:\s*18px\s+6px\s+calc\(18px\s+\+\s+env\(safe-area-inset-bottom,\s*0px\)\)\s+18px")
        self.assertNotRegex(styles, r"\.history-results\s*\{[^}]*grid-template-rows:\s*auto\s+minmax\(0,\s*1fr\)\s+auto")
        self.assertRegex(styles, r"\.history-task-list\s*\{[^}]*overflow:\s*auto")
        self.assertRegex(styles, r"\.history-task-list\.history-view-grid\s*\{[^}]*--history-task-thumb-row-height:\s*clamp")
        self.assertRegex(styles, r"\.history-task-list\.history-view-grid\s*\{[^}]*display:\s*flex")
        self.assertRegex(styles, r"\.history-task-list\.history-view-grid\s*\{[^}]*flex-wrap:\s*wrap")
        self.assertRegex(styles, r"\.history-task-list\.history-view-grid\s*\{[^}]*align-items:\s*flex-start")
        self.assertRegex(styles, r"\.history-task-list\.history-view-grid\s*\{[^}]*padding:\s*6px\s+4px\s+6px\s+6px")
        self.assertNotRegex(styles, r"\.history-task-list\.history-view-grid\s*\{[^}]*grid-template-columns:\s*repeat\(auto-fill")
        self.assertNotRegex(styles, r"\.history-task-list\.history-view-grid\s*\{[^}]*grid-auto-rows:")
        self.assertRegex(styles, r"\.history-task-list\.history-view-list\s*\{[^}]*grid-template-columns:\s*minmax\(0,\s*1fr\)")
        self.assertRegex(styles, r"\.history-task-list\.history-view-list \.history-task-card\s*\{[^}]*grid-template-columns:\s*40px\s+minmax\(0,\s*1fr\)")
        self.assertRegex(styles, r"\.history-task-list\.history-view-grid \.history-task-select\s*\{[^}]*width:\s*32px")
        self.assertRegex(styles, r"\.history-task-list\.history-view-grid \.history-task-select\s*\{[^}]*top:\s*0")
        self.assertRegex(styles, r"\.history-task-list\.history-view-grid \.history-task-select\s*\{[^}]*left:\s*0")
        self.assertRegex(styles, r"\.history-task-list\.history-view-grid \.history-task-select\s*\{[^}]*border:\s*0")
        self.assertRegex(styles, r"\.history-task-list\.history-view-grid \.history-task-select\s*\{[^}]*background:\s*transparent")
        self.assertRegex(styles, r"\.history-task-list\.history-view-grid \.history-task-select\s*\{[^}]*box-shadow:\s*none")
        self.assertRegex(styles, r"\.history-task-list\.history-view-grid \.history-task-card\s*\{[^}]*flex-basis:\s*var\(--history-task-card-width")
        self.assertRegex(styles, r"\.history-task-list\.history-view-grid \.history-task-card\s*\{[^}]*width:\s*var\(--history-task-card-width")
        self.assertNotRegex(styles, r"\.history-task-list\.history-view-grid\s*\{[^}]*justify-content:\s*space-between")
        self.assertRegex(styles, r"\.history-sidebar,\s*\.history-task-list,\s*\.history-detail,\s*\.history-detail-prompt\s*\{[^}]*scrollbar-color:\s*var\(--scrollbar-thumb\)\s+var\(--scrollbar-track\)")
        self.assertIn(".history-task-list::-webkit-scrollbar-thumb:hover", styles)
        self.assertRegex(styles, r"\.history-task-list\.history-view-grid \.history-task-thumb\s*\{[^}]*aspect-ratio:\s*var\(--history-task-thumb-ratio,\s*1\s*/\s*1\)")
        self.assertRegex(styles, r"\.history-task-list\.history-view-grid \.history-task-thumb\s*\{[^}]*height:\s*var\(--history-task-row-height,\s*var\(--history-task-thumb-row-height\)\)")
        self.assertRegex(styles, r"\.history-task-thumb img\s*\{[^}]*object-fit:\s*contain")
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
            r"@media \(max-width:\s*1100px\)\s*\{[\s\S]*\.history-resizer\s*\{[^}]*display:\s*none",
        )
        self.assertRegex(
            styles,
            r"@media \(max-width:\s*1100px\)\s*\{[\s\S]*\.history-detail\s*\{[^}]*position:\s*fixed",
        )
        self.assertRegex(styles, r"\.history-detail-title\s*\{[^}]*-webkit-line-clamp:\s*2")
        self.assertRegex(styles, r"\.history-filter-button\s*\{[^}]*min-height:\s*40px")
        self.assertRegex(styles, r"\.history-filter-heading-icon,\s*\.history-filter-icon\s*\{[^}]*stroke:\s*currentColor")
        self.assertRegex(styles, r"\.history-filter-button\[data-history-filter-key=\"orientation\"\]\s*\{[^}]*padding-left:\s*10px")

    def test_history_page_feature_contracts_are_complete(self) -> None:
        html = Path("codex_image/webui/static/history.html").read_text(encoding="utf-8")
        source = Path("codex_image/webui/frontend/src/history.ts").read_text(encoding="utf-8")
        detail_media_source = Path("codex_image/webui/frontend/src/history-detail-media.ts").read_text(encoding="utf-8")
        window_source = Path("codex_image/webui/frontend/src/history-window.ts").read_text(encoding="utf-8")
        lightbox_source = Path("codex_image/webui/frontend/src/history-lightbox.ts").read_text(encoding="utf-8")

        for marker in [
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
            'id="historyBulkToolbar"',
            'id="historyBulkArchiveButton"',
            'id="historyBulkRestoreButton"',
            'id="historyBulkDeleteButton"',
            'id="historySearchClear"',
            'data-history-resizer="left"',
            'data-history-resizer="right"',
        ]:
            self.assertIn(marker, html)
        self.assertNotIn('<select id="historySort"', html)
        self.assertNotIn('id="historyStatusList"', html)
        self.assertNotIn('id="historySizeList"', html)

        for marker in [
            "selectedTaskIds: new Set<string>()",
            'selectionAnchorTaskId: ""',
            "exhausted: false",
            "newerExhausted: true",
            "syncStateFromUrl()",
            "updateHistoryUrl()",
            'view: "grid"',
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
            'import { initSegmentedIndicatorFeature } from "./segmented-indicator"',
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
            "history-bulk-selecting",
            'els.page?.classList.toggle("history-bulk-selecting", count > 0)',
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
            'params.set("direction", direction)',
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
            "event.shiftKey",
            "event.metaKey",
            "event.ctrlKey",
            "data-history-task-select",
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
            "aria-selected",
            "role=\"option\"",
            "history-detail-title",
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
            "historyLightboxState.scale = Math.min(Math.max(0.5",
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
            "data-history-lightbox-prev",
            "data-history-lightbox-next",
            "data-history-lightbox-image",
            'class="drawer-close-icon"',
            '<path d="M6 6l12 12M18 6L6 18"></path>',
        ]:
            self.assertIn(marker, lightbox_source)
        self.assertNotIn('data-history-lightbox-close aria-label="${escapeHtml(translate("history.closePreview"))}">×</button>', lightbox_source)

        self.assertRegex(
            source,
            r"if \(taskButton\) \{[\s\S]*handleHistoryTaskShortcutSelection\(taskButton\.dataset\.historyTaskId \|\| \"\", event\)[\s\S]*clearHistoryTaskSelection\(\{ updateVisuals: false \}\);[\s\S]*loadTaskDetail\(taskButton\.dataset\.historyTaskId \|\| \"\"\)",
        )

        for marker in [
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

    def test_history_page_polish_i18n_and_detail_actions_contracts(self) -> None:
        html = Path("codex_image/webui/static/history.html").read_text(encoding="utf-8")
        source = Path("codex_image/webui/frontend/src/history.ts").read_text(encoding="utf-8")
        styles = Path("codex_image/webui/static/styles/90-history.css").read_text(encoding="utf-8")
        i18n_source = Path("codex_image/webui/frontend/src/i18n.ts").read_text(encoding="utf-8")

        for marker in [
            'data-i18n="history.back"',
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
            'import { LOCALE_CHANGE_EVENT, formatTranslation, restoreLocalePreference, translate } from "./i18n";',
            'const HISTORY_THEME_STORAGE_KEY = "codex-image-theme-preference"',
            'restoreHistoryThemePreference()',
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
            'history-task-active-badge',
            'translate("history.viewing")',
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
            'historyState.selectedTaskIds = new Set([clickedTaskId])',
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
            '"history.back": "返回生成页"',
            '"history.back": "Back to generator"',
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

        self.assertRegex(styles, r"\.history-task-card\.active\s*\{[^}]*box-shadow:")
        self.assertRegex(styles, r"\.history-task-card\.active\s*\{[^}]*inset 0 0 0 2px")
        self.assertIn(".history-task-list.history-view-grid .history-task-card.active::before", styles)
        self.assertRegex(styles, r"\.history-task-list\.history-view-grid \.history-task-card\.active::before\s*\{[^}]*content:\s*none")
        self.assertRegex(styles, r"\.history-task-list\.history-view-grid \.history-task-card\.active,\s*\.history-task-list\.history-view-grid \.history-task-card\.selected\s*\{[^}]*background:\s*var\(--primary\)")
        self.assertRegex(styles, r"\.history-task-list\.history-view-grid \.history-task-card\.active,\s*\.history-task-list\.history-view-grid \.history-task-card\.selected\s*\{[^}]*box-shadow:\s*[\s\S]*0 0 0 2px var\(--primary\)")
        self.assertRegex(styles, r"\.history-task-list\.history-view-grid \.history-task-card\.active \.history-task-thumb,\s*\.history-task-list\.history-view-grid \.history-task-card\.selected \.history-task-thumb\s*\{[^}]*border-radius:\s*var\(--radius\) var\(--radius\) 0 0")
        self.assertRegex(styles, r"\.history-task-list\.history-view-grid \.history-task-card\.active \.history-task-thumb,\s*\.history-task-list\.history-view-grid \.history-task-card\.selected \.history-task-thumb\s*\{[^}]*background:\s*var\(--primary\)")
        self.assertRegex(styles, r"\.history-task-list\.history-view-grid \.history-task-card\.active \.history-task-copy,\s*\.history-task-list\.history-view-grid \.history-task-card\.selected \.history-task-copy\s*\{[^}]*background:\s*var\(--primary\)")
        self.assertRegex(styles, r"\.history-task-list\.history-view-grid \.history-task-card\.active \.history-task-title,\s*\.history-task-list\.history-view-grid \.history-task-card\.selected \.history-task-title")
        self.assertRegex(styles, r"\.history-task-active-badge\s*\{[^}]*position:\s*absolute")
        self.assertRegex(styles, r"\.history-task-active-badge\s*\{[^}]*background:\s*color-mix\(in srgb,\s*var\(--primary-strong\) 92%,\s*transparent\)")
        self.assertRegex(styles, r"\.history-task-card\.active \.history-task-active-badge\s*\{[^}]*opacity:\s*1")
        self.assertRegex(styles, r"\.history-back-link\s*\{[^}]*display:\s*inline-flex")
        self.assertRegex(styles, r"\.history-back-link\s*\{[^}]*border:\s*1px solid")
        self.assertRegex(styles, r"\.history-back-link\s*\{[^}]*background:\s*color-mix")
        self.assertRegex(styles, r"\.history-back-link::before\s*\{[^}]*clip-path:")
        self.assertRegex(styles, r"\.history-back-link:hover,\s*\.history-back-link:focus-visible\s*\{[^}]*background:\s*var\(--primary\)")
        self.assertRegex(styles, r"\.history-task-card\.selected\s*\{[^}]*box-shadow:")
        self.assertRegex(styles, r"\.history-task-card\.selected::after\s*\{[^}]*border:")
        self.assertRegex(styles, r"\.history-task-card\.selected \.history-task-copy\s*\{[^}]*background:")
        self.assertRegex(styles, r"\.history-task-list\.history-view-grid \.history-task-copy\s*\{[^}]*min-height:\s*74px")
        self.assertRegex(styles, r"\.history-task-list\.history-view-grid \.history-task-open\s*\{[^}]*gap:\s*0")
        self.assertRegex(styles, r"\.history-task-select\s*\{[^}]*opacity:\s*0\.")
        self.assertRegex(styles, r"\.history-task-select input\s*\{[^}]*appearance:\s*none")
        self.assertRegex(styles, r"\.history-task-select input:checked\s*\{[^}]*background:\s*var\(--primary\)")
        self.assertRegex(styles, r"\.history-task-select input:checked::before\s*\{[^}]*transform:\s*scale\(1\)")
        self.assertRegex(styles, r"\.history-task-card:hover \.history-task-select")
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
        self.assertRegex(styles, r"\.history-detail-actions\s*\{[^}]*justify-content:\s*safe center")
        self.assertRegex(styles, r"\.history-detail-actions\s*\{[^}]*width:\s*100%")
        self.assertRegex(styles, r"\.history-detail-actions\s*>\s*\*\s*\{[^}]*white-space:\s*nowrap")
        self.assertRegex(styles, r"\.history-detail-image-actions\s*\{[^}]*position:\s*absolute")
        self.assertRegex(styles, r"\.history-detail-image-actions\s*\{[^}]*opacity:\s*0")
        self.assertRegex(styles, r"\.history-detail-image-actions\s*\{[^}]*pointer-events:\s*none")
        self.assertRegex(styles, r"\.history-detail-image:hover \.history-detail-image-actions,\s*\.history-detail-image:focus-within \.history-detail-image-actions\s*\{[^}]*opacity:\s*1")
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
        self.assertRegex(styles, r"\.history-prompt-note\s*\{[^}]*border:\s*1px solid var\(--panel-border\)")
        self.assertRegex(styles, r"\.history-detail-inputs\s*\{[^}]*border-top:\s*1px solid")
        self.assertRegex(styles, r"\.history-detail-inputs-list\s*\{[^}]*display:\s*flex")
        self.assertRegex(styles, r"\.history-detail-input-thumb\s*\{[^}]*width:\s*54px")
        self.assertRegex(styles, r"\.history-detail-input-thumb\s*\{[^}]*opacity:\s*0\.72")
        self.assertRegex(styles, r"\.history-detail-input-thumb img\s*\{[^}]*object-fit:\s*cover")
        self.assertRegex(styles, r"\.history-prompt-panel-header\s*\{[^}]*grid-template-columns:\s*minmax\(0,\s*1fr\)\s*auto")
        self.assertRegex(styles, r"\.history-prompt-copy\.copied\s*\{[^}]*background:\s*var\(--primary-light\)")
        self.assertRegex(styles, r"\.history-results\s*\{[^}]*env\(safe-area-inset-bottom")
        self.assertRegex(styles, r"\.history-toolbar-actions\s*\{[^}]*--history-toolbar-control-height:\s*44px")
        self.assertRegex(styles, r"\.history-view-toggle,\s*\.history-sort-toggle\s*\{[^}]*box-sizing:\s*border-box")
        self.assertRegex(styles, r"\.history-view-toggle,\s*\.history-sort-toggle\s*\{[^}]*height:\s*var\(--history-toolbar-control-height\)")
        self.assertRegex(styles, r"\.history-view-button,\s*\.history-sort-button\s*\{[^}]*font-size:\s*14px")
        self.assertRegex(styles, r"\.history-sort-toggle\.segmented-indicator-host\s+\.history-sort-button\.active\s*\{[^}]*background:\s*transparent")
        self.assertNotIn(".history-sort-label", styles)
        self.assertRegex(styles, r"\.history-toolbar-actions \.control,\s*\.history-toolbar-actions \.ghost-button\.text-sm\s*\{[^}]*min-height:\s*var\(--history-toolbar-control-height\)")
        self.assertRegex(styles, r"\.history-toolbar-actions \.control,\s*\.history-toolbar-actions \.ghost-button\.text-sm\s*\{[^}]*font-size:\s*14px")
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
        self.assertRegex(styles, r"\.history-page\.history-bulk-selecting \.history-toolbar-actions\s*\{[^}]*visibility:\s*hidden")
        self.assertRegex(styles, r"\.history-page\.history-bulk-selecting \.history-toolbar-actions\s*\{[^}]*pointer-events:\s*none")
        self.assertRegex(styles, r"\.history-bulk-toolbar\s*\{[^}]*position:\s*absolute")
        self.assertRegex(styles, r"\.history-bulk-toolbar\s*\{[^}]*top:\s*18px")
        self.assertRegex(styles, r"\.history-bulk-toolbar\s*\{[^}]*right:\s*18px")
        self.assertRegex(styles, r"\.history-bulk-toolbar\s*\{[^}]*justify-content:\s*flex-start")
        self.assertRegex(styles, r"\.history-bulk-toolbar\s*\{[^}]*width:\s*max-content")
        self.assertRegex(styles, r"\.history-bulk-toolbar\s*\{[^}]*box-shadow:\s*var\(--shadow-popover\)")
        self.assertRegex(styles, r"\.history-bulk-toolbar\s*>\s*\.segmented-indicator\s*\{[^}]*display:\s*none")
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
        self.assertRegex(styles, r"\.history-lightbox-nav\s*\{[^}]*position:\s*absolute")
        self.assertRegex(styles, r"\.history-lightbox-counter\s*\{[^}]*position:\s*absolute")
        self.assertIn(':root[data-theme="dark"] .history-task-card.selected', styles)

    def test_history_task_reuse_handoff_is_consumed_by_main_page(self) -> None:
        history_source = Path("codex_image/webui/frontend/src/history.ts").read_text(encoding="utf-8")
        selection_source = Path("codex_image/webui/frontend/src/task-selection.ts").read_text(encoding="utf-8")
        boot_source = Path("codex_image/webui/frontend/src/boot.ts").read_text(encoding="utf-8")

        self.assertIn('localStorage.setItem(HISTORY_TASK_REUSE_HANDOFF_KEY', history_source)
        self.assertIn('window.location.href = "/"', history_source)
        self.assertIn("async function restoreHistoryTaskReuseHandoff()", selection_source)
        self.assertIn("localStorage.removeItem(HISTORY_TASK_REUSE_HANDOFF_KEY)", selection_source)
        self.assertIn("applyTaskToForm(task)", selection_source)
        self.assertIn("await restoreTaskInputs(task", selection_source)
        self.assertIn('restoreHistoryTaskReuseHandoff,', selection_source)
        self.assertIn('call(methods, "restoreHistoryTaskReuseHandoff")', boot_source)

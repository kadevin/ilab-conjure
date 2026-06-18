from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

from tests.webui_helpers import WebUIStaticTestCase


class WebUIStaticTaskTests(WebUIStaticTestCase):
    def test_main_sidebar_uses_recent_tasks_and_links_history_page(self) -> None:
        tasks_source = Path("codex_image/webui/frontend/src/tasks.ts").read_text(encoding="utf-8")
        render_source = self._task_list_render_source()
        html = Path("codex_image/webui/static/index.html").read_text(encoding="utf-8")
        i18n_source = Path("codex_image/webui/frontend/src/i18n.ts").read_text(encoding="utf-8")
        sidebar_styles = Path("codex_image/webui/static/styles/10-sidebar.css").read_text(encoding="utf-8")

        self.assertIn('fetch("/api/tasks/recent?limit=200")', tasks_source)
        self.assertNotIn('fetch("/api/tasks")', tasks_source)
        self.assertNotIn('["older", translate("taskGroup.older")]', render_source)
        self.assertIn("historyLibraryGroup", render_source)
        self.assertIn("renderHistoryLibraryGroup(tasks, query)", render_source)
        self.assertIn("taskHistoryLibrarySlot", render_source)
        self.assertNotIn("olderCount", render_source)
        self.assertIn('href="/history"', render_source)
        self.assertNotIn('id="archiveButton"', html)
        self.assertNotIn('data-i18n="footer.historyLibrary"', html)
        self.assertIn('id="taskHistoryLibrarySlot"', html)
        self.assertIn('"footer.historyLibrary": "历史库"', i18n_source)
        self.assertIn('"historyLibrary.openFull": "打开完整历史库"', i18n_source)
        self.assertRegex(sidebar_styles, r"\.task-history-library-slot\s*\{[^}]*margin-bottom:\s*12px")

    def test_history_page_static_contract_exists(self) -> None:
        history_html = Path("codex_image/webui/static/history.html").read_text(encoding="utf-8")
        history_source = Path("codex_image/webui/frontend/src/history.ts").read_text(encoding="utf-8")

        self.assertIn('<main class="history-page"', history_html)
        self.assertIn('id="historySearch"', history_html)
        self.assertIn('id="historyMonthList"', history_html)
        self.assertIn('id="historyTaskList"', history_html)
        self.assertIn('id="historyDetail"', history_html)
        self.assertIn('/static/history.js?v=history-32', history_html)
        self.assertIn('fetch("/api/task-history/summary")', history_source)
        self.assertIn('new URLSearchParams', history_source)
        self.assertIn('/api/task-history/tasks?', history_source)
        self.assertIn('/api/tasks/${encodeURIComponent(taskId)}', history_source)
        self.assertIn("function maybeLoadMoreFromScroll(", history_source)
        self.assertIn('els.taskList?.addEventListener("scroll"', history_source)
        self.assertIn("historyState.nextCursor", history_source)

    def test_task_list_controls_feature_has_typescript_source_contract(self) -> None:
        task_list_controls_source = self._task_list_controls_source()
        legacy_source = self._bootstrap_source()
        main_source = Path("codex_image/webui/frontend/src/main.ts").read_text(encoding="utf-8")

        self.assertIn('import { initTaskListControlsFeature } from "./task-list-controls"', main_source)
        self.assertIn('import { initTaskListRenderFeature } from "./task-list-render"', main_source)
        self.assertIn('import { initTaskArchiveControlsFeature } from "./task-archive-controls"', main_source)
        self.assertIn('import { initTaskBatchControlsFeature } from "./task-batch-controls"', main_source)
        self.assertIn('import { initTaskActionsFeature } from "./task-actions"', main_source)
        self.assertIn('import { initTaskSubmitFeature } from "./task-submit"', main_source)
        self.assertLess(main_source.index('import { initPromptFeature } from "./prompt"'), main_source.index('import { initTaskListControlsFeature } from "./task-list-controls"'))
        self.assertLess(main_source.index('import { initTaskListControlsFeature } from "./task-list-controls"'), main_source.index('import { initTaskFeature } from "./tasks"'))
        self.assertLess(main_source.index("initPromptFeature()"), main_source.index("initTaskListControlsFeature()"))
        self.assertLess(main_source.index("initTaskListControlsFeature()"), main_source.index("initTaskFeature()"))
        self.assertLess(main_source.index("initTaskListControlsFeature()"), main_source.index("initTaskFeature()"))
        self.assertIn("export function initTaskListControlsFeature", task_list_controls_source)
        self.assertIn("function bindTaskListControlEvents()", task_list_controls_source)
        self.assertIn("function replacementGroupKey(currentKey", task_list_controls_source)
        self.assertIn("function handleTaskListClick(event", task_list_controls_source)
        self.assertIn("Object.assign(getLegacyBridge().methods", task_list_controls_source)
        self.assertIn("selectTask", legacy_source)
        self.assertIn('legacyMethod("setExpandedTaskGroupKey"', task_list_controls_source)
        self.assertIn('legacyMethod("scrollExpandedTaskGroupToTop"', task_list_controls_source)
        self.assertIn('data-task-group-toggle-key', task_list_controls_source)
        self.assertIn('const interactiveRoot = els.taskHistoryShell || els.sidebarContent || els.taskList;', task_list_controls_source)
        self.assertIn('const root = taskHistoryInteractiveRoot();', task_list_controls_source)
        self.assertIn("if (!card || !root?.contains(card)) return;", task_list_controls_source)
        self.assertNotIn("!card || !els.taskList.contains(card)", task_list_controls_source)
        for function_name in [
            "bindTaskListEvents",
            "handleTaskListClick",
        ]:
            self.assertNotRegex(legacy_source, rf"\n(?:async\s+)?function {function_name}\(")
        self.assertIn('bindTaskListControlEvents: proxy("bindTaskListControlEvents")', legacy_source)

        for moved_function_name in [
            "updateBatchMarqueeSelection",
            "applyBatchSelectionPreview",
            "renderArchiveModal",
            "archiveSelectedTasks",
            "deleteSelectedTasks",
            "openTaskDeleteConfirm",
        ]:
            self.assertNotRegex(task_list_controls_source, rf"\n(?:async\s+)?function {moved_function_name}\(")

    def test_task_history_anchor_navigation_feature_has_typescript_source_contract(self) -> None:
        anchor_source = self._task_history_anchors_source()
        render_source = self._task_list_render_source()
        controls_source = self._task_list_controls_source()
        main_source = Path("codex_image/webui/frontend/src/main.ts").read_text(encoding="utf-8")
        boot_source = Path("codex_image/webui/frontend/src/boot.ts").read_text(encoding="utf-8")
        bootstrap_source = self._bootstrap_source()
        elements_source = self._elements_source()
        state_defaults = self._state_defaults_source()
        html = Path("codex_image/webui/static/index.html").read_text(encoding="utf-8")
        styles = Path("codex_image/webui/static/styles.css").read_text(encoding="utf-8")

        self.assertIn('import { initTaskHistoryAnchorsFeature } from "./task-history-anchors"', main_source)
        self.assertIn("initTaskHistoryAnchorsFeature();", main_source)
        self.assertIn('call(methods, "restoreExpandedTaskGroupKey")', boot_source)
        self.assertIn("export function initTaskHistoryAnchorsFeature()", anchor_source)
        self.assertIn("function restoreExpandedTaskGroupKey()", anchor_source)
        self.assertIn("function ensureExpandedTaskGroupKey(", anchor_source)
        self.assertIn("function setExpandedTaskGroupKey(", anchor_source)
        self.assertIn("TASK_HISTORY_ALL_COLLAPSED_SENTINEL", anchor_source)
        self.assertIn("function syncTaskHistoryAnchorInset()", anchor_source)
        self.assertIn("new ResizeObserver(() => syncTaskHistoryAnchorInset())", anchor_source)
        self.assertIn("function scrollExpandedTaskGroupToTop(", anchor_source)
        self.assertIn("function renderTaskHistoryAnchors(", anchor_source)
        self.assertIn("state.expandedTaskGroupAnimationPending = true", anchor_source)
        self.assertIn("prefersReducedMotion", anchor_source)
        self.assertIn("expandedTaskGroupAnimationPending: false", state_defaults)
        self.assertIn("function finalizeExpandedTaskGroupBody(", render_source)
        self.assertIn("const shouldAnimateExpand = state.expandedTaskGroupAnimationPending === true;", render_source)
        self.assertIn("state.expandedTaskGroupAnimationPending = false;", render_source)
        self.assertIn('renderTaskHistoryAnchors: proxy("renderTaskHistoryAnchors")', bootstrap_source)
        self.assertIn('restoreExpandedTaskGroupKey: proxy("restoreExpandedTaskGroupKey")', bootstrap_source)
        self.assertIn('ensureExpandedTaskGroupKey: proxy("ensureExpandedTaskGroupKey")', bootstrap_source)
        self.assertIn('scrollExpandedTaskGroupToTop: proxy("scrollExpandedTaskGroupToTop")', bootstrap_source)
        self.assertIn('setExpandedTaskGroupKey: proxy("setExpandedTaskGroupKey")', bootstrap_source)
        self.assertIn('taskHistoryShell: document.querySelector(".task-history-shell")', elements_source)
        self.assertIn('sidebarContent: document.querySelector(".sidebar-content")', elements_source)
        self.assertIn('taskActiveList: document.querySelector("#taskActiveList")', elements_source)
        self.assertIn('taskHistoryTopAnchors: document.querySelector("#taskHistoryTopAnchors")', elements_source)
        self.assertIn('taskHistoryBottomAnchors: document.querySelector("#taskHistoryBottomAnchors")', elements_source)
        self.assertIn('taskHistoryLibrarySlot: document.querySelector("#taskHistoryLibrarySlot")', elements_source)
        self.assertIn("expandedTaskGroupKey: null", state_defaults)
        self.assertNotIn("taskHistoryAnchorLayoutFrameId", state_defaults)
        self.assertNotIn("taskHistoryTopAnchorHeight", state_defaults)
        self.assertNotIn("taskHistoryBottomAnchorHeight", state_defaults)
        self.assertIn("const activeGroup = activeTaskGroup(tasks, query)", render_source)
        self.assertIn("taskHistoryGroups(tasks, query)", render_source)
        self.assertIn("ensureExpandedTaskGroupKey(groups)", render_source)
        self.assertIn('const activeHtml = activeGroup ? activeTaskGroupHtml(activeGroup) : "";', render_source)
        self.assertIn("renderActiveTaskGroup(activeHtml)", render_source)
        self.assertIn("els.taskList.innerHTML = renderExpandedTaskGroupShellHtml(group)", render_source)
        self.assertNotIn("activeHtml + renderExpandedTaskGroupShellHtml(group)", render_source)
        self.assertIn("renderTaskHistoryAnchors(", render_source)
        self.assertIn("top: groups", render_source)
        self.assertIn("expandedKey: groups[0]?.key || expandedKey || null", render_source)
        self.assertIn("data-task-group-toggle-key", render_source)
        self.assertNotIn('addGroup("active"', render_source)
        self.assertNotIn('id="taskExpandAllButton"', html)
        self.assertNotIn('id="taskCollapseAllButton"', html)
        self.assertIn('class="task-history-shell"', html)
        self.assertRegex(
            html,
            r'id="taskActiveList"[\s\S]*id="taskHistoryTopAnchors"[\s\S]*id="taskList"[\s\S]*id="taskHistoryBottomAnchors"[\s\S]*id="taskHistoryLibrarySlot"',
        )
        self.assertIn('id="taskHistoryTopAnchors"', html)
        self.assertIn('id="taskHistoryBottomAnchors"', html)
        self.assertRegex(styles, r"\.task-active-list\s*\{[^}]*scrollbar-gutter:\s*stable")
        self.assertNotRegex(
            styles,
            r"\.task-active-list\s*\{[^}]*padding-right:\s*var\(--task-history-scrollbar-offset",
        )
        self.assertRegex(styles, r"\.sidebar-content,\s*[\s\S]*\.task-active-list,\s*[\s\S]*\.dashboard,\s*[\s\S]*scrollbar-width:\s*thin")
        self.assertIn("function collapseExpandedTaskGroup(", controls_source)
        self.assertIn("setExpandedTaskGroupKey(null", controls_source)
        self.assertNotIn('const nextKey = String(state.expandedTaskGroupKey) === key ? replacementGroupKey(key) : key;', controls_source)
        self.assertNotIn("setAllTaskGroupsCollapsed", controls_source)

    def test_active_task_group_renders_running_and_waiting_sections(self) -> None:
        render_source = self._task_list_render_source()
        bootstrap_source = self._bootstrap_source()

        self.assertIn("function activeTaskGroupHtml", render_source)
        self.assertIn("function activeTaskGroup(tasks", render_source)
        self.assertIn("function activeTaskSections", render_source)
        self.assertIn("function activeTaskOrderIndex", render_source)
        self.assertIn("function activeQueueTaskListRenderKey", render_source)
        self.assertIn("activeQueue: activeQueueTaskListRenderKey()", render_source)
        self.assertIn("activeGroup: activeGroup", render_source)
        self.assertIn('class="task-active-section task-active-section-running"', render_source)
        self.assertIn('class="task-active-section task-active-section-waiting"', render_source)
        self.assertIn('data-active-task-section="running"', render_source)
        self.assertIn('data-active-task-section="waiting"', render_source)
        self.assertNotIn('data-task-group-toggle-key="${groupKey}"\n        data-task-group-expanded="true"\n        aria-expanded="true"\n        aria-label="收起 ${escapeHtml(group.label)}"', render_source[render_source.index("function activeTaskGroupHtml"):render_source.index("function expandedTaskGroupHtml")])
        self.assertIn("revealActiveTaskGroup", render_source)
        self.assertIn('revealActiveTaskGroup: proxy("revealActiveTaskGroup")', bootstrap_source)
        self.assertIn('isQueueDispatchPending: proxy("isQueueDispatchPending")', bootstrap_source)

    def test_active_task_cards_expose_queue_actions_only_for_queue_states(self) -> None:
        render_source = self._task_list_render_source()

        self.assertIn("function taskQueueSection", render_source)
        self.assertIn("function waitingQueueIndex", render_source)
        self.assertIn("function taskQueueActionStripHtml", render_source)
        self.assertIn("function taskCardActionsHtml", render_source)
        self.assertIn('if (!queueSection) return "";', render_source)
        self.assertIn('if (queueSection) return "";', render_source)
        self.assertIn('data-task-queue-section="${escapeHtml(queueSection)}"', render_source)
        self.assertIn('data-task-queue-cancel-id="${taskId}"', render_source)
        self.assertIn('data-task-queue-drag-handle-id="${taskId}"', render_source)
        self.assertIn('data-task-queue-move-id="${taskId}"', render_source)
        self.assertIn('data-task-queue-direction="up"', render_source)
        self.assertIn('data-task-queue-direction="down"', render_source)
        self.assertIn('data-task-queue-promote-id="${taskId}"', render_source)
        self.assertIn('data-task-queue-delete-id="${taskId}"', render_source)
        self.assertIn('data-queue-task-id="${taskId}"', render_source)
        self.assertIn("${queueActions}", render_source)
        self.assertIn("${taskActions}", render_source)

    def test_task_list_queue_controls_delegate_queue_actions(self) -> None:
        controls_source = self._task_list_queue_controls_source()
        main_source = Path("codex_image/webui/frontend/src/main.ts").read_text(encoding="utf-8")
        queue_source = self._queue_source()

        self.assertIn('import { initTaskListQueueControlsFeature } from "./task-list-queue-controls"', main_source)
        self.assertIn("initTaskListQueueControlsFeature();", main_source)
        self.assertIn("export function initTaskListQueueControlsFeature", controls_source)
        self.assertIn("function bindTaskListQueueControls", controls_source)
        self.assertIn("function taskListQueueControlRoots()", controls_source)
        self.assertIn("els.taskActiveList", controls_source)
        self.assertIn("els.taskList", controls_source)
        self.assertIn('root.addEventListener("click", handleTaskListQueueClick)', controls_source)
        self.assertIn('root.addEventListener("dragstart", handleTaskListQueueDragStart)', controls_source)
        self.assertIn('root.addEventListener("dragover", handleTaskListQueueDragOver)', controls_source)
        self.assertIn('root.addEventListener("drop", handleTaskListQueueDrop)', controls_source)
        self.assertIn('root.addEventListener("dragend", handleTaskListQueueDragEnd)', controls_source)
        self.assertIn('closest("[data-task-queue-cancel-id]")', controls_source)
        self.assertIn('closest("[data-task-queue-drag-handle-id]")', controls_source)
        self.assertIn('closest("[data-active-task-section=\\"waiting\\"]")', controls_source)
        self.assertIn("cancelRunningTask", controls_source)
        self.assertIn("moveQueueTask", controls_source)
        self.assertIn("promoteQueueTask", controls_source)
        self.assertIn("deleteQueuedTask", controls_source)
        self.assertIn("handleQueueDragStart", controls_source)
        self.assertIn("reorderQueue", controls_source)
        self.assertIn("function waitingQueueDomOrder()", controls_source)
        self.assertIn("function moveWaitingQueueDragPlaceholder(", controls_source)
        self.assertIn("function restoreWaitingQueueDomOrder(", controls_source)
        self.assertIn("function animateWaitingQueueReorder(", controls_source)
        self.assertIn("function taskQueueTransparentDragImage()", controls_source)
        self.assertIn("task-queue-transparent-drag-image", controls_source)
        self.assertIn("prefersReducedMotion", controls_source)
        self.assertIn("void reorderQueue(reorderedIds);", controls_source)
        self.assertIn("setDragImage(taskQueueTransparentDragImage(), 0, 0)", controls_source)
        self.assertNotIn("setDragImage(card,", controls_source)
        self.assertIn("export function cancelRunningTask", queue_source)
        self.assertNotIn('item.classList.add("dragging")', queue_source)

    def test_task_split_modules_have_typescript_source_contract(self) -> None:
        render_source = self._task_list_render_source()
        actions_source = self._task_actions_source()
        submit_source = self._task_submit_source()
        batch_source = self._task_batch_controls_source()
        archive_source = self._task_archive_controls_source()

        for source in [render_source, actions_source, submit_source, batch_source, archive_source]:
            self.assertNotIn("@ts-nocheck", source)

        for marker in [
            "export function initTaskListRenderFeature",
            "function renderTasks(options: { preserveScroll?: boolean } = {})",
            "function taskSearchQuery()",
            "function filteredVisibleTasks(",
            "function taskCardHtml(",
            "function taskHistoryGroups(",
            "function taskMetaText(",
        ]:
            self.assertIn(marker, render_source)
        for marker in [
            "export function initTaskActionsFeature",
            "async function archiveTask(",
            "async function deleteTask(",
            "async function deleteTaskById(",
            "function openTaskDeleteConfirm(",
            "async function retryFailedTask(",
            "async function acceptTaskSuccesses(",
            "async function markTaskViewed(",
        ]:
            self.assertIn(marker, actions_source)
        for marker in [
            "export function initTaskSubmitFeature",
            "function applyTaskToForm(",
            "function buildPreviewRequest(",
            "function createPendingTask(",
            "function addQueuedTask(",
            "async function runTask(",
        ]:
            self.assertIn(marker, submit_source)
        for marker in [
            "export function initTaskBatchControlsFeature",
            "function toggleBatchMode(",
            "function toggleBatchTaskSelection(",
            "function renderBatchToolbar()",
            "async function archiveSelectedTasks()",
            "function openBatchDeleteConfirm()",
            "async function deleteSelectedTasks(",
            "function handleTaskListPointerDown(",
            "function finishBatchMarqueeSelection()",
        ]:
            self.assertIn(marker, batch_source)
        for marker in [
            "export function initTaskArchiveControlsFeature",
            "function restoreLegacyArchivedTasks()",
            "function clearLegacyArchivedTasks()",
            "function isTaskArchived(",
            "function firstVisibleTaskId()",
            "function replaceTask(",
            "function cleanupSessionSelections()",
            "async function setTaskArchiveState(",
            "async function migrateLegacyArchivedTasks()",
            "function renderArchiveButton()",
            "async function restoreArchivedTask(",
            "function openArchiveModal()",
            "function closeArchiveModal()",
            "function renderArchiveModal()",
        ]:
            self.assertIn(marker, archive_source)
    def test_task_search_lives_in_sidebar_only(self) -> None:
        html = Path("codex_image/webui/static/index.html").read_text(encoding="utf-8")
        styles = Path("codex_image/webui/static/styles.css").read_text(encoding="utf-8")
        script = self._frontend_script_source()
        self.assertRegex(html, r'<div class="sidebar-search">\s*<input id="taskSearch"')
        self.assertNotIn('class="nav-search"', html)
        self.assertNotIn("搜索对话或输入关键词", html)
        self.assertNotIn(".nav-search", styles)
        self.assertIn("taskSearch: document.querySelector(\"#taskSearch\")", script)
        self.assertIn("els.taskSearch.addEventListener(\"input\", handleTaskSearchInput)", script)
        self.assertIn("function handleTaskSearchInput()", self._task_list_controls_source())
        self.assertIn("syncTaskSearchHistoryResults", self._task_list_controls_source())
        self.assertIn("async function syncTaskSearchHistoryResults", Path("codex_image/webui/frontend/src/tasks.ts").read_text(encoding="utf-8"))
        self.assertIn('fetch(`/api/task-history/tasks?${params.toString()}`)', Path("codex_image/webui/frontend/src/tasks.ts").read_text(encoding="utf-8"))
        self.assertIn('params.set("q", query)', Path("codex_image/webui/frontend/src/tasks.ts").read_text(encoding="utf-8"))
        self.assertIn('params.set("archived", "false")', Path("codex_image/webui/frontend/src/tasks.ts").read_text(encoding="utf-8"))
        self.assertIn("historyTaskSummaryToSidebarTask", Path("codex_image/webui/frontend/src/tasks.ts").read_text(encoding="utf-8"))
        self.assertIn("summary_only: true", Path("codex_image/webui/frontend/src/tasks.ts").read_text(encoding="utf-8"))
        self.assertIn("prompt: String(task.prompt_preview || task.task_id || \"\")", Path("codex_image/webui/frontend/src/tasks.ts").read_text(encoding="utf-8"))
        self.assertIn("thumbnail_urls: task.thumbnail_url ? [String(task.thumbnail_url)] : []", Path("codex_image/webui/frontend/src/tasks.ts").read_text(encoding="utf-8"))
        self.assertIn('"sidebar.searchPlaceholder": "搜索提示词或任务 ID"', script)
        self.assertIn('"sidebar.searchPlaceholder": "Search prompts or task ID"', script)
        self.assertRegex(script, r"const text = `\$\{task\.task_id \|\| \"\"\} \$\{task\.prompt")
    def test_sidebar_new_task_button_is_compact_brand_action(self) -> None:
        html = Path("codex_image/webui/static/index.html").read_text(encoding="utf-8")
        styles = Path("codex_image/webui/static/styles.css").read_text(encoding="utf-8")

        self.assertRegex(
            html,
            r'<div class="brand-actions">\s*<button id="newTaskButton" class="primary-button brand-new-button" type="button" aria-label="新建对话"[^>]*>',
        )
        self.assertRegex(html, r'<span[^>]*>新建</span>')
        self.assertIn('class="brand-new-icon"', html)
        self.assertRegex(
            html,
            r'<button id="newTaskButton" class="primary-button brand-new-button"[^>]*>\s*<svg class="brand-new-icon"[\s\S]*?</svg>\s*<span[^>]*>新建</span>\s*</button>',
        )
        self.assertRegex(styles, r"\.brand\s*\{[^}]*justify-content:\s*space-between")
        self.assertRegex(styles, r"\.brand-new-button\s*\{[^}]*min-width:\s*84px")
        self.assertRegex(styles, r"\.brand-new-button\s*\{[^}]*height:\s*34px")
        self.assertRegex(styles, r"\.brand-new-button\s*\{[^}]*width:\s*auto")
        self.assertRegex(styles, r"\.brand-new-icon\s*\{[^}]*display:\s*block")
        self.assertRegex(styles, r"\.sidebar-search\s*\{[^}]*margin-top:\s*0")
    def test_sidebar_history_groups_by_dates_and_uses_anchor_navigation(self) -> None:
        script = self._frontend_script_source()
        render_source = self._task_list_render_source()
        styles = Path("codex_image/webui/static/styles.css").read_text(encoding="utf-8")

        self.assertIn("TASK_HISTORY_EXPANDED_GROUP_STORAGE_KEY", script)
        self.assertIn("restoreExpandedTaskGroupKey", script)
        self.assertIn("taskHistoryGroups(tasks, query)", script)
        self.assertIn("isAlwaysVisibleTask(task)", script)
        self.assertIn("ensureExpandedTaskGroupKey(groups)", script)
        self.assertIn("renderTaskHistoryAnchors(layout)", script)
        self.assertIn("data-task-group-toggle-key", script)
        self.assertIn('translate("taskGroup.today")', render_source)
        self.assertIn('translate("taskGroup.yesterday")', render_source)
        self.assertIn('translate("taskGroup.last7")', render_source)
        self.assertIn('translate("historyLibrary.openFull")', render_source)
        self.assertNotIn('"recent"', render_source)
        self.assertIn('formatTranslation("taskGroup.expand"', script)
        self.assertIn('formatTranslation("taskGroup.collapse"', render_source)
        self.assertIn('class="task-group-count-separator"', script)
        self.assertRegex(script, r"const tasks = visibleTasks\.filter\(\(task(?:: any)?\) => \{[\s\S]*return text\.includes\(query\);[\s\S]*\}\);")
        self.assertIn('task.task_id || ""', script)
        self.assertRegex(styles, r"\.task-history-anchor-row\s*,[\s\S]*\.task-group-header-split\s*\{[^}]*display:\s*grid")
        self.assertRegex(styles, r"\.task-history-anchor-row\s*,[\s\S]*\.task-group-header-split\s*\{[^}]*background:\s*var\(--surface\)")
        self.assertRegex(styles, r"\.task-group-header-split\s*\{[^}]*grid-template-columns:\s*minmax\(0,\s*1fr\)\s+auto")
        self.assertRegex(styles, r"\.task-group-header\.task-group-header-split\s*\{[^}]*display:\s*grid")
        self.assertRegex(styles, r"\.task-list\s*>\s*\.task-group-expanded\s*>\s*\.task-group-header-split\s*\{[^}]*position:\s*sticky")
        self.assertRegex(styles, r"\.task-list\s*>\s*\.task-group-expanded\s*>\s*\.task-group-header-split\s*\{[^}]*top:\s*0")
        self.assertRegex(styles, r"\.task-group-header\s*\{[^}]*background:\s*var\(--surface\)")
        self.assertRegex(styles, r"\.task-group-header\s*\{[^}]*border:\s*1px\s+solid\s+var\(--panel-border\)")
        self.assertRegex(styles, r"\.task-group-header-split\s*\{[^}]*padding:\s*4px")
        self.assertRegex(styles, r"\.task-group-header-split\s*\{[^}]*border:\s*1px\s+solid\s+var\(--panel-border\)")
        self.assertRegex(styles, r"\.task-group-title\s*\{[^}]*display:\s*inline-flex")
        self.assertRegex(styles, r"\.task-group-count\s*\{[^}]*font-variant-numeric:\s*tabular-nums")
        self.assertRegex(styles, r"\.task-group-toggle\s*\{[^}]*display:\s*inline-flex")
        self.assertRegex(styles, r"\.task-group-toggle-icon\s*\{[^}]*width:\s*12px")
        self.assertRegex(styles, r"\.task-group-header-split\[aria-expanded=\"true\"\]\s+\.task-group-toggle\s*\{[^}]*transform:\s*rotate\(90deg\)")
        self.assertRegex(styles, r"\.task-group-arrow-button\s*\{[^}]*min-width:\s*34px")
        self.assertRegex(styles, r"\.task-history-anchor-label\s*,\s*\.task-group-label-button\s*\{[^}]*padding:\s*0\s+12px\s+0\s+14px")
        self.assertNotRegex(styles, r"\.task-history-anchor-row\.active\s*\{[^}]*background:\s*color-mix")
        self.assertRegex(styles, r"\.task-history-anchor-rail\s*\{[^}]*padding-right:\s*var\(--task-history-scrollbar-offset,\s*0px\)")
        self.assertRegex(styles, r"\.sidebar-content\s*\{[^}]*scrollbar-gutter:\s*stable")
    def test_sidebar_task_filters_remain_and_group_bulk_controls_are_removed(self) -> None:
        html = Path("codex_image/webui/static/index.html").read_text(encoding="utf-8")
        script = self._frontend_script_source()
        render_source = self._task_list_render_source()
        controls_source = self._task_list_controls_source()
        styles = Path("codex_image/webui/static/styles.css").read_text(encoding="utf-8")

        self.assertIn('id="taskRatioFilter"', html)
        self.assertIn('id="taskOrientationFilter"', html)
        self.assertIn('id="taskPromptFidelityFilter"', html)
        self.assertIn('id="taskResolutionFilter"', html)
        self.assertIn('aria-label="按分辨率筛选"', html)
        self.assertRegex(html, r'<option value=""[^>]*>全部分辨率</option>')
        self.assertIn('<option value="standard">1K</option>', html)
        self.assertIn('<option value="2k">2K</option>', html)
        self.assertIn('<option value="4k">4K</option>', html)
        self.assertNotIn('id="taskQuantityFilter"', html)
        self.assertNotIn('全部数量', html)
        self.assertNotIn('id="taskExpandAllButton"', html)
        self.assertNotIn('id="taskCollapseAllButton"', html)
        self.assertIn('id="taskHistoryTopAnchors"', html)
        self.assertIn('id="taskHistoryBottomAnchors"', html)
        self.assertIn("taskRatioFilter: document.querySelector(\"#taskRatioFilter\")", script)
        self.assertIn("taskOrientationFilter: document.querySelector(\"#taskOrientationFilter\")", script)
        self.assertIn("taskPromptFidelityFilter: document.querySelector(\"#taskPromptFidelityFilter\")", script)
        self.assertIn("taskResolutionFilter: document.querySelector(\"#taskResolutionFilter\")", script)
        self.assertNotIn("taskQuantityFilter: document.querySelector(\"#taskQuantityFilter\")", script)
        self.assertIn("sidebarContent: document.querySelector(\".sidebar-content\")", script)
        self.assertIn("taskHistoryTopAnchors: document.querySelector(\"#taskHistoryTopAnchors\")", script)
        self.assertIn("taskHistoryBottomAnchors: document.querySelector(\"#taskHistoryBottomAnchors\")", script)
        self.assertIn("taskFilterValues()", script)
        self.assertIn("taskMatchesFilters(task, filters)", script)
        self.assertIn("taskRatio(task)", script)
        self.assertIn("taskOrientation(task)", script)
        self.assertIn("taskPromptFidelity(task)", script)
        self.assertIn("taskResolution(task)", script)
        self.assertNotIn("taskQuantity(task)", script)
        self.assertIn("commitExpandedTaskGroupKey(key, \"auto\")", script)
        self.assertIn("collapseExpandedTaskGroup(null)", script)
        self.assertIn("renderExpandedTaskGroupShellHtml(group)", render_source)
        self.assertIn("scheduleExpandedTaskGroupItemsRender(group, layout.expandedKey || group?.key || null)", render_source)
        self.assertIn("requestAnimationFrame(renderChunk)", render_source)
        self.assertNotIn("taskHistoryCollapseTimerId", controls_source)
        self.assertNotIn("window.setTimeout", controls_source)
        self.assertRegex(styles, r"\.sidebar-filter-panel\s*\{[^}]*display:\s*grid")
        self.assertRegex(styles, r"\.sidebar-filter-grid\s*\{[^}]*grid-template-columns:\s*repeat\(2,\s*minmax\(0,\s*1fr\)\)")
        self.assertNotIn(".task-group-bulk-actions", styles)
        self.assertNotIn(".task-group-action-icon", styles)
    def test_javascript_has_pending_task_feedback(self) -> None:
        script = self._frontend_script_source()

        self.assertIn("createPendingTask", script)
        self.assertIn("startRunFeedback", script)
        self.assertIn("replacePendingTask", script)
    def test_javascript_parses_running_task_started_at_before_elapsed_math(self) -> None:
        script = self._frontend_script_source()

        self.assertIn("function timestampMs", script)
        self.assertIn("function elapsedSecondsSince", script)
        self.assertIn("const progressStartedAt = taskProgressStartValue(task)", script)
        self.assertIn("elapsedSecondsSince(progressStartedAt)", script)
        self.assertIn("state.runStartedAt = timestampMs(task.started_at || task.created_at) || Date.now()", script)
        self.assertNotIn("Date.now() - task.started_at", script)
        self.assertNotIn("state.runStartedAt = task.started_at || Date.now()", script)
    def test_javascript_displays_failed_task_reason_from_last_error(self) -> None:
        script = self._frontend_script_source()

        self.assertIn("function taskFailureMessage", script)
        self.assertIn("task.error || task.last_error", script)
        self.assertIn('`${formatTaskStatus(task)} · ${failure}`', script)
        self.assertIn('taskFailureMessage(selected) || translate("preview.taskFailed")', script)
    def test_failed_preview_wraps_long_error_messages(self) -> None:
        styles = Path("codex_image/webui/static/styles.css").read_text(encoding="utf-8")

        self.assertRegex(styles, r"\.error-preview\s*\{[^}]*overflow-wrap:\s*anywhere")
        self.assertRegex(styles, r"\.error-preview\s*\{[^}]*word-break:\s*break-word")
        self.assertRegex(styles, r"\.error-preview\s*\{[^}]*white-space:\s*pre-wrap")
        self.assertRegex(styles, r"\.error-preview\s*\{[^}]*padding:\s*24px")
        self.assertRegex(styles, r"\.error-preview\s*\{[^}]*flex-direction:\s*column")
        self.assertRegex(styles, r"\.error-preview\s*\{[^}]*align-items:\s*stretch")
        self.assertRegex(styles, r"\.error-preview\s+p\s*\{[^}]*margin:\s*0")
    def test_failed_history_cards_use_static_failed_thumbnail(self) -> None:
        script = self._frontend_script_source()
        styles = Path("codex_image/webui/static/styles.css").read_text(encoding="utf-8")

        self.assertIn("function taskThumbHtml", script)
        self.assertIn('task.status === "failed"', script)
        self.assertIn("failed-thumb", script)
        self.assertRegex(script, r"function taskThumbHtml\(task(?:: any)?,\s*className(?:: any)? = \"task-thumb\"\)[\s\S]*failed-thumb")
        self.assertRegex(styles, r"\.failed-thumb\s*\{[^}]*display:\s*grid")
        self.assertRegex(styles, r"\.failed-thumb\s+span\s*\{[^}]*animation:\s*none")
        self.assertNotRegex(styles, r"\.failed-thumb\s+span\s*\{[^}]*animation:\s*spin")
    def test_running_history_thumbnail_does_not_flex_as_content(self) -> None:
        styles = Path("codex_image/webui/static/styles.css").read_text(encoding="utf-8")

        self.assertRegex(styles, r"\.task-card\s*>\s*\.task-info\s*\{[^}]*flex:\s*1")
        self.assertNotRegex(styles, r"\.task-card\s*>\s*div\s*\{[^}]*flex:\s*1")
        self.assertRegex(styles, r"\.task-thumb\.running-thumb\s*\{[^}]*width:\s*52px")
        self.assertRegex(styles, r"\.task-thumb\.running-thumb\s*\{[^}]*height:\s*52px")
    def test_image_to_image_history_cards_stack_output_and_reference_thumbnails(self) -> None:
        script = self._frontend_script_source()
        styles = Path("codex_image/webui/static/styles.css").read_text(encoding="utf-8")

        self.assertIn("const outputThumbnailUrl = taskThumbnailUrls(task)[0]", script)
        self.assertIn("const inputPreviewUrl = taskInputPreviewUrls(task)[0]", script)
        self.assertIn("function taskThumbShowsLoading", script)
        self.assertIn('["submitting", "queued", "running"].includes(status)', script)
        self.assertIn('class="${safeClassName} task-thumb-stack"', script)
        self.assertIn('translate("taskCard.imageToImageThumb")', script)
        self.assertIn('class="task-thumb-reference"', script)
        self.assertIn('class="task-thumb-output"', script)
        self.assertIn('class="task-thumb-stack-spinner" aria-hidden="true"', script)
        self.assertIn("${loadingSpinner}", script)
        self.assertIn('translate("taskCard.textToImageThumb")', script)
        self.assertIn('class="${safeClassName} task-thumb-single"', script)
        self.assertIn('class="task-thumb-single-image"', script)
        self.assertIn('translate("taskCard.textBadge")', script)
        self.assertNotIn('class="task-thumb-mode-badge" aria-hidden="true">图</span>', script)
        self.assertRegex(styles, r"\.task-thumb-stack\s*\{[^}]*position:\s*relative")
        self.assertRegex(styles, r"\.task-thumb-stack\s*\{[^}]*background:\s*transparent")
        self.assertNotRegex(styles, r"\.task-thumb-stack\s*\{[^}]*border:")
        self.assertRegex(styles, r"\.task-thumb-stack\s+img\s*\{[^}]*object-fit:\s*cover")
        self.assertRegex(styles, r"\.task-thumb-stack-spinner\s*\{[^}]*left:\s*50%")
        self.assertRegex(styles, r"\.task-thumb-stack-spinner\s*\{[^}]*top:\s*50%")
        self.assertRegex(styles, r"\.task-thumb-stack-spinner\s*\{[^}]*width:\s*24px")
        self.assertRegex(styles, r"\.task-thumb-stack-spinner::before\s*\{[^}]*animation:\s*soft-spin 1\.2s linear infinite")
        self.assertNotIn("width 0.18s ease", styles)
        self.assertNotIn("height 0.18s ease", styles)
        self.assertRegex(styles, r"\.task-thumb-reference\s*\{[^}]*right:\s*0")
        self.assertRegex(styles, r"\.task-thumb-reference\s*\{[^}]*bottom:\s*0")
    def test_history_cards_prefer_cached_thumbnail_urls(self) -> None:
        derived_source = self._task_derived_source()
        render_source = self._task_list_render_source()

        self.assertIn("function taskThumbnailUrls", derived_source)
        self.assertIn("task.thumbnail_urls", derived_source)
        self.assertIn("record.thumbnail_url", derived_source)
        self.assertIn("taskThumbnailRoute(task, index)", derived_source)
        self.assertIn("function taskInputThumbnailUrls", derived_source)
        self.assertIn("task.input_thumbnail_urls", derived_source)
        self.assertIn("source.thumbnail_url || thumbnailUrls[uploadInputIndex]", derived_source)
        self.assertIn("taskThumbnailUrls", render_source)
        self.assertIn("const outputThumbnailUrl = taskThumbnailUrls(task)[0]", render_source)
        self.assertIn("const imageUrl = outputThumbnailUrl || outputUrl || task.preview_url || inputPreviewUrl", render_source)
        self.assertNotIn("const imageUrl = outputUrl || task.preview_url || inputPreviewUrl", render_source)
    def test_history_task_thumbnails_lazy_load_images(self) -> None:
        source = self._task_list_render_source()
        styles = Path("codex_image/webui/static/styles.css").read_text(encoding="utf-8")

        self.assertIn('loading="lazy"', source)
        self.assertIn('decoding="async"', source)
        self.assertRegex(source, r'class="task-thumb-reference"[^>]*loading="lazy"[^>]*decoding="async"')
        self.assertRegex(source, r'class="task-thumb-output"[^>]*loading="lazy"[^>]*decoding="async"')
        self.assertRegex(source, r'class="task-thumb-single-image"[^>]*loading="lazy"[^>]*decoding="async"')
        self.assertRegex(styles, r"\.task-thumb-output\s*\{[^}]*left:\s*0")
        self.assertRegex(styles, r"\.task-thumb-output\s*\{[^}]*top:\s*0")
        self.assertRegex(styles, r"\.task-thumb-single-image\s*\{[^}]*object-fit:\s*contain")
        self.assertRegex(styles, r"\.task-thumb-mode-badge\s*\{[^}]*font-size:\s*10px")
        self.assertRegex(styles, r"\.task-card:hover\s+\.task-thumb-reference\s*,[\s\S]*\.archive-card:hover\s+\.task-thumb-reference\s*\{[^}]*transform:\s*translate\(-2px,\s*-2px\)")
        self.assertRegex(styles, r"\.task-card:hover\s+\.task-thumb-output\s*,[\s\S]*\.archive-card:hover\s+\.task-thumb-output\s*\{[^}]*opacity:\s*0\.24")
    def test_history_cards_show_status_lights_and_image_blocks(self) -> None:
        script = self._frontend_script_source()
        styles = Path("codex_image/webui/static/styles.css").read_text(encoding="utf-8")

        self.assertIn("taskStatusLightHtml(task)", script)
        self.assertIn("taskImageBlocksHtml(task)", script)
        self.assertIn("taskImageSummaryText(task)", script)
        self.assertIn('class="task-status-row"', script)
        self.assertIn("task-image-progress", script)
        self.assertIn('class="task-image-summary"', script)
        self.assertIn('aria-label="${escapeHtml(taskStatusAccessibleLabel(task))}"', script)
        self.assertIn('["failed", "partial_failed"].includes(status)', script)
        self.assertIn('status === "completed"', script)
        self.assertIn('status === "running"', script)
        self.assertIn('status === "queued" || status === "submitting"', script)
        self.assertIn("taskOutputRecordsByIndex(task)", script)
        self.assertIn("taskOutputRecordHasDisplayableImage(record)", script)
        self.assertIn("taskVisibleCompletedCount(task)", script)
        self.assertIn('record?.status === "completed"', script)
        self.assertIn('record?.status === "failed"', script)
        self.assertIn('const visibleCount = Math.min(total, 12)', script)
        self.assertRegex(styles, r"\.task-status-light\s*\{[^}]*border-radius:\s*999px")
        self.assertRegex(styles, r"\.task-status-light\.failed\s*\{[^}]*background:\s*var\(--danger\)")
        self.assertRegex(styles, r"\.task-status-light\.completed\s*\{[^}]*background:\s*var\(--primary\)")
        self.assertRegex(styles, r"\.task-status-light\.running\s*\{[^}]*background:\s*var\(--status-blue\)")
        self.assertRegex(styles, r"\.task-status-light\.queued\s*\{[^}]*background:\s*var\(--accent\)")
        self.assertRegex(styles, r"\.task-image-progress\s*\{[^}]*grid-template-columns:\s*repeat\(var\(--task-block-count\)")
        self.assertRegex(styles, r"\.task-card\.failed\s*,\s*\.task-card\.partial_failed\s*\{")
        self.assertRegex(styles, r"\.task-card\.active\s*\{[^}]*box-shadow")
        self.assertRegex(styles, r"\.task-card\.active::after\s*\{[^}]*content:\s*attr\(data-active-label\)")
        self.assertRegex(styles, r"\.task-card\.active::after\s*\{[^}]*right:\s*40px")
        self.assertRegex(styles, r"\.task-card\.active::after\s*\{[^}]*background:\s*var\(--primary\)")
        self.assertRegex(styles, r"\.task-card\.active\.queue-waiting::after\s*,\s*\.task-card\.active\.queue-running::after\s*,\s*\.task-card\.active\.batch-mode::after\s*\{[^}]*right:\s*8px")
        self.assertRegex(styles, r"\.task-card\.active\.running\s*\{[^}]*var\(--status-blue\)")
        self.assertRegex(styles, r"\.task-card\.active\.failed\s*,\s*\.task-card\.active\.partial_failed\s*\{[^}]*background:\s*var\(--danger-soft\)")
    def test_history_image_summary_counts_explicit_running_slots(self) -> None:
        node = shutil.which("node")
        if node is None:
            self.skipTest("node is required for frontend behavior checks")
        script = self._frontend_script_source()
        harness = "\n".join(
            [
                self._extract_javascript_function(script, "taskOutputUrls"),
                self._extract_javascript_function(script, "taskDeletedOutputIndexes"),
                self._extract_javascript_function(script, "taskSelectedOutputIndexes"),
                self._extract_javascript_function(script, "taskTotalCount"),
                self._extract_javascript_function(script, "positiveInt"),
                self._extract_javascript_function(script, "nonnegativeInt"),
                self._extract_javascript_function(script, "taskOutputRecordIsDeleted"),
                self._extract_javascript_function(script, "taskOutputRecordMatchesUrl"),
                self._extract_javascript_function(script, "taskOutputRecordHasDisplayableImage"),
                self._extract_javascript_function(script, "taskOutputIndexFromUrl"),
                self._extract_javascript_function(script, "taskOutputRecordsByIndex"),
                self._extract_javascript_function(script, "taskOutputSelected"),
                self._extract_javascript_function(script, "taskVisibleCompletedCount"),
                self._extract_javascript_function(script, "taskGeneratedCount"),
                self._extract_javascript_function(script, "nonnegativeInt"),
                self._extract_javascript_function(script, "taskImageBlockStatesFromCounts"),
                self._extract_javascript_function(script, "taskImageBlockStates"),
                self._extract_javascript_function(script, "taskImageStatusCounts"),
                self._extract_javascript_function(script, "taskImageSummaryText"),
                """
                const i18nMessages = {
                  "taskCard.count": "{count} 张",
                  "taskCard.successCount": "成功 {count}",
                  "taskCard.failedCount": "失败 {count}",
                  "taskCard.runningCount": "生成中 {count}",
                  "taskCard.waitingCount": "等待 {count}",
                };
                function formatTranslation(key, values = {}) {
                  return String(i18nMessages[key] || key).replace(/\\{([^}]+)\\}/g, (_, name) => values[name] ?? "");
                }
                const summary = taskImageSummaryText({
                  status: "running",
                  total_count: 4,
                  outputs: [
                    { index: 1, status: "running" },
                    { index: 2, status: "running" },
                  ],
                });
                if (summary !== "4 张 · 成功 0 · 失败 0 · 生成中 2 · 等待 2") {
                  throw new Error(`unexpected summary: ${summary}`);
                }
                const summaryOnlyPartial = {
                  status: "partial_failed",
                  total_count: 2,
                  generated_count: 1,
                  failed_count: 1,
                };
                const summaryOnlyPartialStates = taskImageBlockStates(summaryOnlyPartial).join("|");
                if (summaryOnlyPartialStates !== "completed|failed") {
                  throw new Error(`summary-only partial failure should use count fields, got ${summaryOnlyPartialStates}`);
                }
                const summaryOnlyPartialText = taskImageSummaryText(summaryOnlyPartial);
                if (summaryOnlyPartialText !== "2 张 · 成功 1 · 失败 1") {
                  throw new Error(`summary-only partial failure should count one success and one failure, got ${summaryOnlyPartialText}`);
                }
                const staleProgressTask = {
                  status: "running",
                  total_count: 4,
                  generated_count: 2,
                  output_urls: ["/outputs/task-image-1.png"],
                  outputs: [
                    { index: 1, status: "completed", url: "/outputs/task-image-1.png" },
                    { index: 2, status: "completed" },
                  ],
                };
                const staleSummary = taskImageSummaryText(staleProgressTask);
                if (staleSummary !== "4 张 · 成功 1 · 失败 0 · 生成中 1 · 等待 2") {
                  throw new Error(`unexpected stale progress summary: ${staleSummary}`);
                }
                const generated = taskGeneratedCount(staleProgressTask, 1);
                if (generated !== 1) {
                  throw new Error(`generated count should follow visible outputs, got ${generated}`);
                }
                const mergedRecord = taskOutputRecordsByIndex({
                  output_urls: ["/outputs/legacy-image-1.png"],
                  outputs: [{ index: 1, status: "completed" }],
                }).get(1);
                if (mergedRecord.url !== "/outputs/legacy-image-1.png") {
                  throw new Error(`structured output record should preserve legacy URL, got ${mergedRecord.url}`);
                }
                const retryingSparseTask = {
                  status: "running",
                  total_count: 4,
                  generated_count: 2,
                  output_urls: [
                    "/outputs/2026-05-19/task-image-1.jpg",
                    "/outputs/2026-05-19/task-image-4.jpg",
                  ],
                  outputs: [
                    { index: 1, status: "completed", url: "/outputs/2026-05-19/task-image-1.jpg" },
                    { index: 4, status: "completed", url: "/outputs/2026-05-19/task-image-4.jpg" },
                  ],
                };
                const retryingSummary = taskImageSummaryText(retryingSparseTask);
                if (retryingSummary !== "4 张 · 成功 2 · 失败 0 · 生成中 1 · 等待 1") {
                  throw new Error(`sparse retry progress should not double-count output_urls: ${retryingSummary}`);
                }
                const prunedTask = {
                  status: "completed",
                  total_count: 3,
                  selected_output_indexes: [1, "3"],
                  deleted_output_indexes: [2],
                  output_urls: [
                    "/outputs/task-image-1.png",
                    "/outputs/task-image-2.png",
                    "/outputs/task-image-3.png",
                  ],
                  outputs: [
                    { index: 1, status: "completed", url: "/outputs/task-image-1.png" },
                    { index: 2, status: "completed", deleted: true, url: "/outputs/task-image-2.png" },
                    { index: 3, status: "completed", url: "/outputs/task-image-3.png" },
                  ],
                };
                const visibleUrls = taskOutputUrls(prunedTask).join("|");
                if (visibleUrls !== "/outputs/task-image-1.png|/outputs/task-image-3.png") {
                  throw new Error(`deleted outputs should be hidden, got ${visibleUrls}`);
                }
                if (!taskOutputSelected(prunedTask, 3) || taskOutputSelected(prunedTask, 2)) {
                  throw new Error("selected output indexes should be parsed and ignore deleted slots");
                }
                """,
            ]
        )
        result = subprocess.run([node, "-e", harness], check=False, text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
    def test_queue_items_wrap_long_account_and_channel_text(self) -> None:
        render_source = self._task_list_render_source()
        styles = Path("codex_image/webui/static/styles.css").read_text(encoding="utf-8")

        self.assertIn('class="task-info"', render_source)
        self.assertIn("taskMetaDetailsText(task)", render_source)
        self.assertIn("task-status-meta", render_source)
        self.assertRegex(styles, r"\.task-card\s*>\s*\.task-info\s*\{[^}]*min-width:\s*0")
        self.assertRegex(styles, r"\.task-title\s*\{[^}]*text-overflow:\s*ellipsis")
        self.assertRegex(styles, r"\.task-status-meta\s*\{[^}]*text-overflow:\s*ellipsis")
    def test_queue_items_use_compact_titles_and_visible_reorder_controls(self) -> None:
        queue_source = self._queue_source()
        render_source = self._task_list_render_source()
        styles = Path("codex_image/webui/static/styles.css").read_text(encoding="utf-8")

        self.assertIn("function queueItemTitleText", queue_source)
        self.assertIn("function taskQueueActionStripHtml", render_source)
        self.assertIn("task-queue-drag-handle", render_source)
        self.assertIn("function taskQueueActionIconHtml", render_source)
        self.assertIn('class="task-queue-action-icon"', render_source)
        self.assertIn("data-task-queue-move-id", render_source)
        self.assertIn("data-task-queue-direction", render_source)
        self.assertIn("function moveQueueTask", queue_source)
        self.assertIn('translate("queue.cancelRunningTitle")', render_source)
        self.assertIn('translate("queue.moveUpTitle")', render_source)
        self.assertIn('translate("queue.moveDownTitle")', render_source)
        self.assertIn('translate("queue.promoteTitle")', render_source)
        self.assertIn('translate("queue.deleteWaitingTitle")', render_source)
        self.assertNotIn("const cancelLabel", render_source)
        self.assertNotIn("const moveUpLabel", render_source)
        self.assertNotIn("const moveDownLabel", render_source)
        self.assertNotIn("const promoteLabel", render_source)
        self.assertNotIn('aria-label="上移等待任务"', render_source)
        self.assertNotIn('aria-label="下移等待任务"', render_source)
        self.assertNotIn(">取消</button>", render_source)
        self.assertNotIn(">上</button>", render_source)
        self.assertNotIn(">下</button>", render_source)
        self.assertNotIn(">顶</button>", render_source)
        self.assertNotIn(">删</button>", render_source)
        self.assertNotIn("const title = escapeHtml(task.prompt || task.mode || task.task_id || \"Untitled\")", render_source)
        self.assertRegex(styles, r"\.task-queue-drag-handle\s*\{[^}]*cursor:\s*grab")
        self.assertRegex(styles, r"\.task-queue-action,\s*\.task-queue-drag-handle\s*\{[^}]*width:\s*24px")
        self.assertRegex(styles, r"\.task-queue-action,\s*\.task-queue-drag-handle\s*\{[^}]*padding:\s*0")
        self.assertRegex(styles, r"\.task-queue-action-icon\s*\{[^}]*stroke-linejoin:\s*round")
        self.assertRegex(styles, r"\.task-queue-transparent-drag-image\s*\{[^}]*position:\s*fixed")
        self.assertRegex(styles, r"\.task-queue-transparent-drag-image\s*\{[^}]*pointer-events:\s*none")
        self.assertRegex(styles, r"\.task-queue-actions\s*\{[^}]*right:\s*12px")
        self.assertRegex(styles, r"\.task-queue-actions\s*\{[^}]*box-sizing:\s*border-box")
        self.assertRegex(styles, r"\.task-queue-actions\s*\{[^}]*max-width:\s*calc\(100% - 24px\)")
        self.assertRegex(styles, r"\.task-queue-actions\s*\{[^}]*opacity:\s*0")
        self.assertIn(".task-card.queue-waiting.active .task-queue-actions", styles)
        self.assertNotIn(".task-card.active .task-queue-actions", styles)
    def test_javascript_restores_history_input_files(self) -> None:
        script = self._frontend_script_source()

        self.assertIn("restoreTaskInputs", script)
        self.assertIn("input_urls", script)
        self.assertIn("taskInputRestoreSeq", script)
        self.assertIn("function selectedTaskInputRestoreCurrent", script)
        self.assertIn("function applyTaskInputRestoreSources", script)
        self.assertIn("renderSelectedTask(task, taskId);", script)
        self.assertIn("await restoreTaskInputs(task, { taskId, restoreSeq });", script)
        self.assertLess(
            script.index("renderSelectedTask(task, taskId);"),
            script.index("await restoreTaskInputs(task, { taskId, restoreSeq });"),
        )
        self.assertIn("if (!selectedTaskInputRestoreCurrent(taskId, restoreSeq))", script)
    def test_history_input_restore_falls_back_from_legacy_output_input_urls(self) -> None:
        selection_source = self._task_selection_source()
        derived_source = self._task_derived_source()

        self.assertIn("function isLegacyOutputInputUrl", selection_source)
        self.assertIn("function historyInputCandidateUrls", selection_source)
        self.assertIn("const inputUrls = taskInputUrls(task);", selection_source)
        self.assertIn("let uploadInputIndex = 0;", selection_source)
        self.assertIn("const fallbackUrl = inputUrls[uploadInputIndex];", selection_source)
        self.assertIn("const candidateUrls = historyInputCandidateUrls(source.image_url, fallbackUrl);", selection_source)
        self.assertIn("for (const url of candidateUrls)", selection_source)
        self.assertIn('formatTranslation("status.historyInputLoadFailed", { url: candidateUrls[0] || sourceUrl })', selection_source)
        self.assertIn("function taskInputPreviewUrls", derived_source)
        self.assertIn("let uploadInputIndex = 0;", derived_source)
        self.assertIn("isLegacyOutputInputUrl", derived_source)
    def test_queue_status_chip_replaces_queue_drawer(self) -> None:
        html = Path("codex_image/webui/static/index.html").read_text(encoding="utf-8")
        frontend_source = self._frontend_script_source()
        queue_source = self._queue_source()
        elements_source = self._elements_source()

        self.assertIn('id="queueButton"', html)
        self.assertIn('class="queue-button queue-status-chip"', html)
        self.assertIn('id="queueStatusText"', html)
        self.assertIn('aria-label="队列状态：暂无排队"', html)
        self.assertNotIn('id="queueBadge"', html)
        self.assertNotIn('id="queueDrawer"', html)
        self.assertNotIn('id="queueRunningList"', html)
        self.assertNotIn('id="queueWaitingList"', html)
        self.assertNotIn('id="queueDrawerBackdrop"', html)
        self.assertNotIn('queueDrawer:', elements_source)
        self.assertNotIn('queueDrawerClose:', elements_source)
        self.assertNotIn('queueDrawerBackdrop:', elements_source)
        self.assertNotIn('queueRunningList:', elements_source)
        self.assertNotIn('queueWaitingList:', elements_source)
        self.assertNotIn("openQueueDrawer", queue_source)
        self.assertNotIn("closeQueueDrawer", queue_source)
        self.assertNotIn("#queueDrawer.open", frontend_source)
        self.assertNotIn("closeQueueDrawer", frontend_source)
        self.assertIn("function jumpToActiveTaskGroup", queue_source)
        self.assertIn("renderQueueStatusChip", queue_source)
        self.assertIn('els.queueButton?.addEventListener("click", jumpToActiveTaskGroup)', queue_source)
    def test_queue_frontend_polling_and_controls_exist(self) -> None:
        queue_routes = Path("codex_image/webui/routes/queue.py").read_text(encoding="utf-8")
        events_source = Path("codex_image/webui/events.py").read_text(encoding="utf-8")
        legacy_source = self._bootstrap_source()
        queue_source = self._queue_source()
        task_source = self._task_source()
        dom_source = self._dom_source()
        elements_source = self._elements_source()
        state_defaults_source = self._state_defaults_source()

        self.assertIn("queueButton: document.querySelector(\"#queueButton\")", elements_source)
        self.assertIn("queueStatusText: document.querySelector(\"#queueStatusText\")", elements_source)
        self.assertNotIn("queueBadge: document.querySelector(\"#queueBadge\")", elements_source)
        self.assertNotIn("queueDrawer: document.querySelector(\"#queueDrawer\")", elements_source)
        self.assertIn("export function getEls", dom_source)
        self.assertIn("refreshQueue", queue_source)
        self.assertIn('fetch("/api/queue")', queue_source)
        self.assertIn("renderQueue", queue_source)
        self.assertIn("renderQueueStatusChip", queue_source)
        self.assertIn("function jumpToActiveTaskGroup", queue_source)
        self.assertIn('els.queueButton?.addEventListener("click", jumpToActiveTaskGroup)', queue_source)
        self.assertIn("queueRequestSeq", queue_source)
        self.assertIn("queueDispatchSyncTimerId", queue_source)
        self.assertIn("const QUEUE_DISPATCH_RESYNC_DELAY_MS = 1500", queue_source)
        self.assertIn("tasksRequestSeq", state_defaults_source)
        self.assertIn("realtimeSource: null", state_defaults_source)
        self.assertIn("const REALTIME_EVENTS_URL = \"/api/events?stream=1\"", queue_source)
        self.assertIn("new EventSource(REALTIME_EVENTS_URL)", queue_source)
        self.assertIn("function startRealtimeUpdates", queue_source)
        self.assertIn("function closeRealtimeUpdates", queue_source)
        self.assertIn("function handleRealtimeMessage", queue_source)
        self.assertIn("function handleRealtimePayload", queue_source)
        self.assertIn("applyTasksSnapshot", queue_source)
        self.assertIn("applyQueueTasks(payload.queue)", queue_source)
        self.assertIn("function applyQueueTasks", queue_source)
        self.assertIn("applyTaskUpdate", queue_source)
        self.assertIn("updateTaskInState", queue_source)
        self.assertIn("function renderActiveTaskGroupForQueueChange", queue_source)
        self.assertNotIn('bridge.state.expandedTaskGroupKey || "") !== "active"', queue_source)
        self.assertIn("bridge.methods.renderTasks?.();", queue_source)
        self.assertIn("bridge.methods.renderTasks?.()", queue_source)
        boot_source = Path("codex_image/webui/frontend/src/boot.ts").read_text(encoding="utf-8")
        self.assertIn("const realtimeStarted = window.startRealtimeUpdates?.({ migrateLegacyArchives: true });", boot_source)
        self.assertIn("if (!realtimeStarted) {", boot_source)
        self.assertIn('call(methods, "refreshTasks", { migrateLegacyArchives: true })', boot_source)
        realtime_fallback_block = re.search(
            r"if \(!realtimeStarted\) \{(?P<body>[\s\S]*?)\n  \}",
            boot_source,
        )
        self.assertIsNotNone(realtime_fallback_block)
        self.assertIn('window.refreshQueue?.()', realtime_fallback_block.group("body"))
        self.assertIn('call(methods, "refreshTasks", { migrateLegacyArchives: true })', realtime_fallback_block.group("body"))
        self.assertNotRegex(
            boot_source.replace(realtime_fallback_block.group(0), ""),
            r"refreshTasks\(\s*\{ migrateLegacyArchives: true \}\)",
        )
        self.assertIn("void getLegacyBridge().methods.refreshTasks({ migrateLegacyArchives: shouldMigrateArchives });", queue_source)
        self.assertIn("applyQueueState(payload.queue)", queue_source)
        self.assertIn("function activeTasksNeedQueueReconcile(", queue_source)
        self.assertIn('status === "submitting" || status === "queued" || status === "running"', queue_source)
        self.assertIn("activeTasksNeedQueueReconcile(queueTaskIds)", queue_source)
        self.assertNotIn("function selectedTaskNeedsQueueReconcile(", queue_source)
        self.assertIn("void bridge.methods.refreshTasks();", queue_source)
        self.assertRegex(
            queue_source,
            r"if \(!tasks\.length\) \{[\s\S]*needsTaskReconcile[\s\S]*refreshTasks",
        )
        self.assertRegex(
            queue_source,
            r"if \(!changed\) \{[\s\S]*needsTaskReconcile[\s\S]*refreshTasks",
        )
        self.assertIn("@app.get(\"/api/events\", response_model=None)", queue_routes)
        self.assertIn("stream: bool = False", queue_routes)
        self.assertIn("request.is_disconnected()", queue_routes)
        self.assertIn("EVENT_STREAM_CHECK_INTERVAL_SECONDS", queue_routes)
        self.assertIn('"type": "queue"', queue_routes)
        self.assertIn('"type": "task"', events_source)
        self.assertIn("requestSeq !== state.queueRequestSeq", queue_source)
        self.assertIn("requestSeq !== state.tasksRequestSeq", task_source)
        self.assertIn("normalizeQueueState", queue_source)
        self.assertIn("invalidateQueueRequests", queue_source)
        self.assertIn("applyQueueState", queue_source)
        self.assertIn("invalidateQueueRequests();", queue_source)
        self.assertIn("function isQueueDispatchPending", queue_source)
        self.assertIn("function scheduleQueueDispatchSync", queue_source)
        self.assertIn("function clearQueueDispatchSync", queue_source)
        self.assertIn('formatTranslation("queue.dispatching"', queue_source)
        self.assertIn('formatTranslation("queue.availableChannels"', queue_source)
        self.assertNotIn("window.setInterval(pollQueueAndTasks", queue_source)
        self.assertNotIn("function pollQueueAndTasks", queue_source)
        self.assertNotIn("function shouldRefreshTasksDuringQueuePoll", queue_source)
        self.assertNotIn("openQueueDrawer", queue_source)
        self.assertNotIn("closeQueueDrawer", queue_source)
        self.assertIn("promoteQueueTask", queue_source)
        self.assertIn("deleteQueuedTask", queue_source)
        self.assertIn("export function cancelRunningTask", queue_source)
        self.assertNotIn("handleQueueRunningClick", queue_source)
        self.assertNotIn("handleQueueWaitingClick", queue_source)
        self.assertNotIn("data-cancel-queue-task-id", queue_source)
        self.assertIn("reorderQueue", queue_source)
        self.assertIn("handleQueueDragStart", queue_source)
        self.assertIn("handleQueueDragOver", queue_source)
        self.assertIn("handleQueueDrop", queue_source)
        self.assertIn("getBoundingClientRect", queue_source)
        self.assertIn("clientY", queue_source)
        self.assertIn('dropEffect = "move"', queue_source)
        self.assertIn('/api/queue/${encodeURIComponent(taskId)}/promote', queue_source)
        self.assertIn('/api/queue/${encodeURIComponent(taskId)}', queue_source)
        self.assertIn('/api/queue/reorder', queue_source)
    def test_queue_feature_has_typescript_source_contract(self) -> None:
        queue_source = self._queue_source()
        main_source = Path("codex_image/webui/frontend/src/main.ts").read_text(encoding="utf-8")
        state_source = self._state_source()
        dom_source = self._dom_source()
        legacy_source = self._bootstrap_source()
        legacy_entry_source = Path("codex_image/webui/frontend/legacy-app.js").read_text(encoding="utf-8")
        state_defaults_source = self._state_defaults_source()
        elements_source = self._elements_source()
        runtime_feedback_source = self._runtime_feedback_source()
        utils_source = Path("codex_image/webui/frontend/src/webui-utils.ts").read_text(encoding="utf-8")

        self.assertIn('import "../legacy-app.js"', main_source)
        self.assertIn('import { initInputSourcesFeature } from "./input-sources"', main_source)
        self.assertIn('import { initImageEditorFeature } from "./image-editor"', main_source)
        self.assertIn('import { initImageStripFeature } from "./image-strip"', main_source)
        self.assertIn('import { initGalleryFeature } from "./gallery"', main_source)
        self.assertIn('import { initApiSettingsFeature } from "./api-settings"', main_source)
        self.assertIn('import { initStorageSettingsFeature } from "./storage-settings"', main_source)
        self.assertIn('import { initPromptFeature } from "./prompt"', main_source)
        self.assertIn('import { initTaskListControlsFeature } from "./task-list-controls"', main_source)
        self.assertIn('import { initializeQueueFeature } from "./queue"', main_source)
        self.assertIn('import { initTaskFeature } from "./tasks"', main_source)
        self.assertIn('import { initLightboxFeature } from "./lightbox"', main_source)
        self.assertIn("initInputSourcesFeature()", main_source)
        self.assertIn("initImageEditorFeature()", main_source)
        self.assertIn("initImageStripFeature()", main_source)
        self.assertIn("initGalleryFeature()", main_source)
        self.assertIn("initApiSettingsFeature()", main_source)
        self.assertIn("initStorageSettingsFeature()", main_source)
        self.assertIn("initPromptFeature()", main_source)
        self.assertIn("initTaskListControlsFeature()", main_source)
        self.assertIn("initTaskFeature()", main_source)
        self.assertIn("initLightboxFeature()", main_source)
        self.assertIn("initializeQueueFeature()", main_source)
        self.assertLess(main_source.index('import "../legacy-app.js"'), main_source.index('import { initInputSourcesFeature } from "./input-sources"'))
        self.assertLess(main_source.index('import { initInputSourcesFeature } from "./input-sources"'), main_source.index('import { initImageEditorFeature } from "./image-editor"'))
        self.assertLess(main_source.index('import { initImageEditorFeature } from "./image-editor"'), main_source.index('import { initImageStripFeature } from "./image-strip"'))
        self.assertLess(main_source.index('import { initImageStripFeature } from "./image-strip"'), main_source.index('import { initGalleryFeature } from "./gallery"'))
        self.assertLess(main_source.index('import { initGalleryFeature } from "./gallery"'), main_source.index('import { initApiSettingsFeature } from "./api-settings"'))
        self.assertLess(main_source.index('import { initApiSettingsFeature } from "./api-settings"'), main_source.index('import { initStorageSettingsFeature } from "./storage-settings"'))
        self.assertLess(main_source.index('import { initStorageSettingsFeature } from "./storage-settings"'), main_source.index('import { initPromptFeature } from "./prompt"'))
        self.assertLess(main_source.index('import { initPromptFeature } from "./prompt"'), main_source.index('import { initTaskListControlsFeature } from "./task-list-controls"'))
        self.assertLess(main_source.index('import { initTaskListControlsFeature } from "./task-list-controls"'), main_source.index('import { initTaskFeature } from "./tasks"'))
        self.assertLess(main_source.index("initInputSourcesFeature()"), main_source.index("initImageEditorFeature()"))
        self.assertLess(main_source.index("initImageEditorFeature()"), main_source.index("initImageStripFeature()"))
        self.assertLess(main_source.index("initImageStripFeature()"), main_source.index("initGalleryFeature()"))
        self.assertLess(main_source.index("initGalleryFeature()"), main_source.index("initApiSettingsFeature()"))
        self.assertLess(main_source.index("initApiSettingsFeature()"), main_source.index("initStorageSettingsFeature()"))
        self.assertLess(main_source.index("initStorageSettingsFeature()"), main_source.index("initPromptFeature()"))
        self.assertLess(main_source.index("initPromptFeature()"), main_source.index("initTaskListControlsFeature()"))
        self.assertLess(main_source.index("initTaskListControlsFeature()"), main_source.index("initTaskFeature()"))
        self.assertLess(main_source.index("initTaskFeature()"), main_source.index("initLightboxFeature()"))
        self.assertLess(main_source.index("initLightboxFeature()"), main_source.index("initializeQueueFeature()"))
        self.assertLess(main_source.index("initializeQueueFeature()"), main_source.index("boot()"))
        self.assertIn("export function getState", state_source)
        self.assertIn("window.__codexImageWebUI", state_source)
        self.assertIn("export function getEls", dom_source)
        self.assertIn("getLegacyBridge().els", dom_source)
        self.assertLess(len(legacy_entry_source.splitlines()), 350)
        self.assertIn('import { initializeLegacyBridge } from "./src/bootstrap"', legacy_entry_source)
        self.assertIn("initializeLegacyBridge();", legacy_entry_source)
        self.assertIn("export function createDefaultState", state_defaults_source)
        self.assertIn("DEFAULT_GALLERY_CATEGORIES", state_defaults_source)
        self.assertIn("DEFAULT_API_BASE_URL", state_defaults_source)
        self.assertIn("export function createWebUIElements", elements_source)
        self.assertIn("queueButton: document.querySelector(\"#queueButton\")", elements_source)
        self.assertIn("queueStatusText: document.querySelector(\"#queueStatusText\")", elements_source)
        self.assertIn("export function formatTaskStatus", runtime_feedback_source)
        self.assertIn("export function startRunFeedback", runtime_feedback_source)
        self.assertIn("export function startUiClock", runtime_feedback_source)
        self.assertIn("export function addPendingTask", runtime_feedback_source)
        self.assertIn("export function replacePendingTask", runtime_feedback_source)
        self.assertIn("export function escapeHtml", utils_source)
        self.assertIn("export function initializeQueueFeature", queue_source)
        for function_name in [
            "startRealtimeUpdates",
            "closeRealtimeUpdates",
            "handleRealtimeMessage",
            "handleRealtimePayload",
            "refreshQueue",
            "defaultQueueState",
            "normalizeQueueState",
            "invalidateQueueRequests",
            "applyQueueState",
            "renderQueueStatusChip",
            "jumpToActiveTaskGroup",
            "applyQueueTasks",
            "updateQueueElapsedDisplays",
        ]:
            self.assertIn(f"function {function_name}", queue_source)
        self.assertIn("window.startRealtimeUpdates = startRealtimeUpdates", queue_source)
        self.assertIn("window.closeRealtimeUpdates = closeRealtimeUpdates", queue_source)
        self.assertIn("window.refreshQueue = refreshQueue", queue_source)
        self.assertIn("window.applyQueueState = applyQueueState", queue_source)
        self.assertIn("window.applyQueueTasks = applyQueueTasks", queue_source)
        self.assertNotIn("window.closeQueueDrawer", queue_source)
        self.assertIn("window.updateQueueElapsedDisplays = updateQueueElapsedDisplays", queue_source)
        self.assertIn('els.queueButton?.addEventListener("click", jumpToActiveTaskGroup)', queue_source)
        self.assertNotRegex(legacy_source, r"\nfunction startRealtimeUpdates\(")
        self.assertNotRegex(legacy_source, r"\nasync function refreshQueue\(")
        self.assertNotRegex(legacy_source, r"\nfunction renderQueue\(")
        self.assertNotRegex(legacy_source, r"\nfunction startUiClock\(")
        self.assertNotIn("bindQueueListEvents();", legacy_source)
        self.assertIn("installLegacyBridge", legacy_source)
        self.assertIn("startUiClock,", legacy_source)
        self.assertIn("addPendingTask,", legacy_source)
        self.assertIn("replacePendingTask,", legacy_source)

    def test_task_notifications_feature_has_typescript_source_contract(self) -> None:
        source = self._task_notifications_source()
        queue_source = self._queue_source()
        main_source = Path("codex_image/webui/frontend/src/main.ts").read_text(encoding="utf-8")
        html = Path("codex_image/webui/static/index.html").read_text(encoding="utf-8")
        styles = Path("codex_image/webui/static/styles.css").read_text(encoding="utf-8")
        state_defaults = self._state_defaults_source()
        elements_source = self._elements_source()

        self.assertIn('import { initTaskNotificationsFeature } from "./task-notifications"', main_source)
        self.assertIn("initTaskNotificationsFeature();", main_source)
        self.assertIn("export function initTaskNotificationsFeature", source)
        self.assertIn("function notifyTaskUpdate(previousTask", source)
        self.assertIn("function shouldNotifyTerminalTask(", source)
        self.assertIn("function openTaskNotificationCenter()", source)
        self.assertIn("function renderTaskNotifications()", source)
        self.assertIn("function requestSystemNotificationPermission()", source)
        self.assertIn("TASK_NOTIFICATION_SETTINGS_KEY", source)
        self.assertIn("TASK_NOTIFICATION_SEEN_KEY", source)
        self.assertIn("Notification.requestPermission()", source)
        self.assertIn("Object.assign(getLegacyBridge().methods", source)
        self.assertIn('notifyTaskUpdate: proxy("notifyTaskUpdate")', self._bootstrap_source())
        self.assertIn("bridge.methods.notifyTaskUpdate?.(previousTask, task)", queue_source)
        self.assertIn("taskNotifications: []", state_defaults)
        self.assertIn("taskNotificationButton: document.querySelector(\"#taskNotificationButton\")", elements_source)
        self.assertIn("taskNotificationUnreadSummary: document.querySelector(\"#taskNotificationUnreadSummary\")", elements_source)
        self.assertIn('id="taskNotificationButton"', html)
        self.assertIn('aria-label="任务通知"', html)
        self.assertIn('id="taskNotificationCenter"', html)
        self.assertIn('id="taskNotificationUnreadSummary"', html)
        self.assertIn('id="taskNotificationToastRegion"', html)
        self.assertIn('id="taskNotificationBadge" class="task-notification-dot hidden"', html)
        self.assertNotIn('id="taskNotificationBadge" class="queue-badge', html)
        self.assertIn('formatTranslation("notifications.unread"', source)
        self.assertIn('translate("notifications.title")', source)
        self.assertIn('translate("notifications.taskCompleted")', source)
        self.assertIn('formatTranslation("notifications.successCount"', source)
        self.assertIn("function taskNotificationDisplayTitle", source)
        self.assertIn("function taskNotificationDisplayMessage", source)
        self.assertIn("success_count", source)
        self.assertIn("prompt_snippet", source)
        self.assertNotIn('return "任务已完成"', source)
        self.assertNotIn('"生成失败"', source)
        self.assertIn('els.taskNotificationButton.classList.toggle("has-unread", unreadCount > 0)', source)
        self.assertIn('els.taskNotificationButton.setAttribute("aria-label", unreadLabel)', source)
        self.assertIn('els.taskNotificationButton.title = unreadLabel', source)
        self.assertIn('formatTranslation("notifications.unreadSummary"', source)
        self.assertNotIn('els.taskNotificationBadge.textContent = String(unreadCount)', source)
        self.assertIn(".task-notification-button", styles)
        self.assertIn(".task-notification-button.has-unread", styles)
        self.assertIn(".task-notification-dot", styles)
        self.assertIn(".task-notification-unread-summary", styles)
        self.assertNotIn(".task-notification-button .queue-badge", styles)
        self.assertIn(".task-notification-center", styles)
        self.assertIn(".task-notification-toast-region", styles)
        self.assertIn(".task-notification-thumb", styles)

    def test_task_feature_has_typescript_source_contract(self) -> None:
        task_source = self._task_source()
        legacy_source = self._bootstrap_source()
        main_source = Path("codex_image/webui/frontend/src/main.ts").read_text(encoding="utf-8")

        self.assertNotIn("@ts-nocheck", task_source)
        for marker in [
            "export function initTaskFeature",
            "async function refreshTasks",
            "async function applyTasksSnapshot",
            "async function applyTaskUpdate",
            "async function renderSelectedTaskPreview",
        ]:
            self.assertIn(marker, task_source)
        self.assertIn("ensureSelectedTaskDetail(selectedTask.task_id)", task_source)
        self.assertIn("renderPreview(detailedTask)", task_source)
        self.assertIn("await renderSelectedTaskPreview(requestSeq)", task_source)
        self.assertIn("await renderSelectedTaskPreview()", task_source)

        for function_name in [
            "renderTasks",
            "archiveTask",
            "deleteTask",
            "retryFailedTask",
            "acceptTaskSuccesses",
            "applyTaskToForm",
            "buildPreviewRequest",
            "createPendingTask",
            "addQueuedTask",
            "runTask",
        ]:
            self.assertNotRegex(task_source, rf"\n(?:async\s+)?function {function_name}\(")
        for function_name in [
            "refreshTasks",
            "applyTasksSnapshot",
            "applyTaskUpdate",
            "renderTasks",
            "retryFailedTask",
            "acceptTaskSuccesses",
            "taskRetryStateText",
            "runTask",
        ]:
            self.assertNotRegex(legacy_source, rf"\n(?:async\s+)?function {function_name}\(")
            self._assert_bootstrap_proxy(legacy_source, function_name)

        self.assertLess(main_source.index('import "../legacy-app.js"'), main_source.index('import { initInputSourcesFeature } from "./input-sources"'))
        self.assertLess(main_source.index("initInputSourcesFeature()"), main_source.index("initImageEditorFeature()"))
        self.assertLess(main_source.index("initImageEditorFeature()"), main_source.index("initPromptFeature()"))
        self.assertLess(main_source.index("initPromptFeature()"), main_source.index("initTaskListControlsFeature()"))
        self.assertLess(main_source.index("initTaskListControlsFeature()"), main_source.index("initTaskFeature()"))
        self.assertLess(main_source.index("initTaskFeature()"), main_source.index("initializeQueueFeature()"))
        self.assertLess(main_source.index("initializeQueueFeature()"), main_source.index("boot()"))
    def test_task_preview_feature_has_typescript_source_contract(self) -> None:
        source = self._task_preview_source()
        task_source = self._task_source()
        main_source = Path("codex_image/webui/frontend/src/main.ts").read_text(encoding="utf-8")

        self.assertNotIn("@ts-nocheck", source)
        self.assertIn('import { initTaskPreviewFeature } from "./task-preview"', main_source)
        self.assertLess(main_source.index("initTaskPreviewFeature()"), main_source.index("initTaskFeature()"))
        for function_name in [
            "renderPreview",
            "previewStructureKey",
            "previewPromptKey",
            "renderOutputPreview",
            "bindPreviewRetryButtons",
            "updatePreviewDownloadActions",
            "taskOutputZipUrl",
            "outputDownloadFilename",
            "promptPopoverData",
            "runningProgressCard",
            "waitingProgressCard",
            "failureSummaryCard",
            "renderRunningPreview",
            "renderWaitingPreview",
        ]:
            self.assertRegex(source, rf"\nfunction {function_name}\(")
            self.assertNotRegex(task_source, rf"\nfunction {function_name}\(")
        self.assertIn("Object.assign(getLegacyBridge().methods", source)
    def test_task_derived_feature_has_typescript_source_contract(self) -> None:
        source = self._task_derived_source()
        task_source = self._task_source()
        main_source = Path("codex_image/webui/frontend/src/main.ts").read_text(encoding="utf-8")

        self.assertNotIn("@ts-nocheck", source)
        self.assertIn('import { initTaskDerivedFeature } from "./task-derived"', main_source)
        self.assertLess(main_source.index("initTaskDerivedFeature()"), main_source.index("initTaskFeature()"))
        self.assertIn("export function initTaskDerivedFeature", source)
        self.assertIn("const GPT_IMAGE_2_SIZE_PRESETS", source)
        for function_name in [
            "taskThumbnailUrls",
            "taskOutputUrls",
            "taskOutputRecordsByIndex",
            "taskImageBlockStates",
            "taskGeneratedCount",
            "taskTotalCount",
            "taskRatio",
            "taskOrientation",
            "taskPromptFidelity",
            "taskResolution",
            "taskRuntimeText",
            "formatDuration",
        ]:
            self.assertRegex(source, rf"\nfunction {function_name}\(")
            self.assertNotRegex(task_source, rf"\nfunction {function_name}\(")
        self.assertIn("Object.assign(getLegacyBridge().methods", source)
    def test_task_selection_feature_has_typescript_source_contract(self) -> None:
        task_selection_source = self._task_selection_source()
        legacy_source = self._bootstrap_source()
        main_source = Path("codex_image/webui/frontend/src/main.ts").read_text(encoding="utf-8")

        self.assertIn('import { initTaskSelectionFeature } from "./task-selection"', main_source)
        self.assertLess(main_source.index('import { initTaskFeature } from "./tasks"'), main_source.index('import { initTaskSelectionFeature } from "./task-selection"'))
        self.assertLess(main_source.index('import { initTaskSelectionFeature } from "./task-selection"'), main_source.index('import { initLightboxFeature } from "./lightbox"'))
        self.assertLess(main_source.index("initTaskFeature()"), main_source.index("initTaskSelectionFeature()"))
        self.assertLess(main_source.index("initTaskSelectionFeature()"), main_source.index("initLightboxFeature()"))
        self.assertIn("export function initTaskSelectionFeature", task_selection_source)
        for function_name in [
            "selectedTaskInputRestoreCurrent",
            "applySelectedTaskRequestPreview",
            "applyTaskInputRestoreSources",
            "renderSelectedTask",
            "ensureSelectedTaskDetail",
            "restoreTaskInputs",
            "selectTask",
        ]:
            self.assertRegex(task_selection_source, rf"\n(?:async\s+)?function {function_name}\(")
            self.assertNotRegex(legacy_source, rf"\n(?:async\s+)?function {function_name}\(")
        self.assertIn("Object.assign(getLegacyBridge().methods", task_selection_source)
        self.assertIn('ensureSelectedTaskDetail: proxy("ensureSelectedTaskDetail")', legacy_source)
        self.assertIn('selectTask: proxy("selectTask")', legacy_source)
        self.assertIn("task.summary_only", task_selection_source)
        self.assertIn("/api/tasks/${encodeURIComponent(taskId)}", task_selection_source)
        self.assertIn("replaceSelectedTaskDetail", task_selection_source)
    def test_run_task_treats_submit_response_as_queued(self) -> None:
        script = self._frontend_script_source()
        submit_source = self._task_submit_source()

        self.assertIn("addQueuedTask", submit_source)
        self.assertIn("startRealtimeUpdates", script)
        self.assertIn('translate("taskSubmit.queued")', submit_source)
        self.assertNotIn("任务完成", submit_source)
    def test_cmd_enter_shortcut_uses_run_task_flow(self) -> None:
        event_source = Path("codex_image/webui/frontend/src/event-bindings.ts").read_text(encoding="utf-8")
        script = self._frontend_script_source()

        for source in (event_source, script):
            self.assertIn("function isRunTaskShortcut", source)
            self.assertIn('event.key === "Enter"', source)
            self.assertIn("event.metaKey", source)
            self.assertIn("!event.ctrlKey", source)
            self.assertIn("!event.altKey", source)
            self.assertIn("!event.shiftKey", source)
            self.assertIn("!event.repeat", source)
            self.assertIn("!event.isComposing", source)
            self.assertIn("function hasOpenShortcutBlockingLayer", source)
            self.assertIn("#promptTemplateDrawer.open", source)
            self.assertIn(".modal-overlay:not(.hidden)", source)
            self.assertIn("function handleRunTaskShortcut", source)
            self.assertIn("els.runButton.disabled", source)
            self.assertIn("event.preventDefault()", source)
            self.assertIn('call(methods, "runTask")', source)
            self.assertIn('document.addEventListener("keydown", (event) => handleRunTaskShortcut(event, els, methods));', source)
    def test_submit_and_queued_tasks_show_waiting_preview(self) -> None:
        source = self._task_preview_source()
        script = self._frontend_script_source()

        self.assertIn('status: "submitting"', script)
        self.assertIn('if (task.status === "submitting") return translate("taskStatus.submitting");', script)
        self.assertIn('if (status === "submitting" || status === "queued")', source)
        self.assertIn("renderWaitingPreview(selected)", source)
        self.assertIn('startRunFeedback(pendingTask, translate("taskStatus.submitting"))', script)
        self.assertIn("function renderWaitingPreview", script)
        self.assertIn('translate("preview.submittingTitle")', script)
        self.assertIn('translate("preview.queuedTitle")', script)
        self.assertNotIn('els.runButton.textContent = "提交中...";', script)
    def test_preview_uses_queue_membership_for_running_state(self) -> None:
        source = self._task_preview_source()

        self.assertIn("function taskPreviewStatus(", source)
        self.assertIn("state.queue.running", source)
        self.assertIn("state.queue.waiting", source)
        self.assertIn("const status = taskPreviewStatus(selected)", source)
        self.assertIn("const status = taskPreviewStatus(task)", source)
        self.assertIn('if (status === "running")', source)
        self.assertIn('if (status === "submitting" || status === "queued")', source)
    def test_submit_task_has_timeout_instead_of_infinite_submitting_state(self) -> None:
        script = self._frontend_script_source()

        self.assertIn("SUBMIT_TASK_TIMEOUT_MS", script)
        self.assertIn("new AbortController()", script)
        self.assertIn("window.setTimeout(() => controller.abort(), SUBMIT_TASK_TIMEOUT_MS)", script)
        self.assertIn("signal: controller.signal", script)
        self.assertIn('error.name === "AbortError"', script)
        self.assertIn("提交任务超时", script)
        self.assertIn("window.clearTimeout(submitTimeoutId)", script)
    def test_gallery_input_sources_do_not_upload_as_task_files(self) -> None:
        script = self._frontend_script_source()

        self.assertIn('kind: "upload"', script)
        self.assertIn('kind: "gallery"', script)
        self.assertIn('getState().images.filter((image) => image.kind === "upload")', script)
        self.assertIn('getState().images.filter((image) => image.kind === "gallery")', script)
    def test_restored_task_quantity_syncs_button_group(self) -> None:
        node = shutil.which("node")
        if node is None:
            self.skipTest("node is required for frontend behavior checks")
        script = self._task_submit_source()
        output_source = Path("codex_image/webui/frontend/src/output-controls.ts").read_text(encoding="utf-8")
        harness = "\n".join(
            [
                """
                function Event(type) { this.type = type; }
                const quantityButtons = ["1", "2", "3", "4"].map((value) => ({
                  value,
                  active: value === "1",
                  classList: {
                    toggle(className, active) {
                      if (className === "active") this.owner.active = active;
                    },
                  },
                }));
                quantityButtons.forEach((button) => { button.classList.owner = button; });
                function syncQuantityButtons(value) {
                  quantityButtons.forEach((button) => {
                    button.classList.toggle("active", button.value === value);
                  });
                }
                const els = {
                  nInput: {
                    value: "1",
                    matches() { return false; },
                    dispatchEvent(event) { syncQuantityButtons(this.value); return true; },
                  },
                  nValue: null,
                  promptFidelity: { value: "strict", dispatchEvent() {} },
                  mainModel: { value: "" },
                  model: { value: "gpt-image-2" },
                  quality: { value: "low", dispatchEvent() {} },
                  outputFormat: { value: "png", dispatchEvent() {} },
                  moderation: { value: "auto", dispatchEvent() {} },
                  compression: { value: "80" },
                };
                function setMode() {}
                function setPromptWithGalleryRefs() {}
                function persistMainModel() {}
                function normalizeApiSettings(settings) { return settings || { providers: [] }; }
                const state = { apiSettings: { providers: [] } };
                function persistApiSettings() {}
                function populateApiSettingsForm() {}
                function syncSizeControlsFromSize() {}
                function updatePromptCount() {}
                function updateCompression() {}
                function updateCustomSize() {}
                function updateRequestPreview() {}
                function updateRangeProgress() {}
                """,
                self._extract_javascript_function(output_source, "currentQuantity"),
                self._extract_javascript_function(output_source, "updateRangeProgress"),
                self._extract_javascript_function(output_source, "updateQuantity"),
                self._extract_javascript_function(output_source, "syncRadioButtons"),
                self._extract_javascript_function(script, "applyTaskToForm"),
                """
                applyTaskToForm({ mode: "generate", prompt: "history", params: { n: 4 } });
                const activeValue = quantityButtons.find((button) => button.active)?.value || "";
                if (els.nInput.value !== "4") {
                  throw new Error(`expected hidden quantity 4, got ${els.nInput.value}`);
                }
                if (activeValue !== "4") {
                  throw new Error(`expected restored quantity button 4, got ${activeValue || "none"}`);
                }
                """,
            ]
        )
        result = subprocess.run([node, "-e", harness], check=False, text=True, capture_output=True)

        self.assertEqual(result.returncode, 0, result.stderr)
    def test_history_cards_are_fixed_height_and_deletable(self) -> None:
        script = self._frontend_script_source()
        styles = Path("codex_image/webui/static/styles.css").read_text(encoding="utf-8")

        self.assertIn("deleteTask", script)
        self.assertIn("data-delete-task-id", script)
        self.assertIn('class="task-card-actions"', script)
        self.assertIn('translate("taskActions.group")', script)
        self.assertIn('translate("taskContext.archive")', script)
        self.assertIn('translate("taskContext.delete")', script)
        self.assertIn('translate("taskActions.deleteTitle")', script)
        self.assertIn('translate("taskActions.deleteMessage")', script)
        self.assertIn('translate("taskActions.runningCannotDelete")', script)
        self.assertIn("task-action-icon", script)
        self.assertIn("task-delete-icon", script)
        self.assertIn('<svg class="task-action-icon task-delete-icon"', script)
        self.assertIn('method: "DELETE"', script)
        self.assertRegex(styles, r"\.task-card\s*\{[^}]*height:\s*82px")
        self.assertRegex(styles, r"\.task-card\s*\{[^}]*padding-right:\s*34px")
        self.assertRegex(styles, r"\.task-thumb\s*\{[^}]*height:\s*52px")
        self.assertRegex(styles, r"\.task-card-actions\s*\{[^}]*right:\s*8px")
        self.assertRegex(styles, r"\.task-card-actions\s*\{[^}]*top:\s*50%")
        self.assertRegex(styles, r"\.task-card-actions\s*\{[^}]*display:\s*inline-flex")
        self.assertRegex(styles, r"\.task-card-actions\s*\{[^}]*flex-direction:\s*column")
        self.assertRegex(styles, r"\.task-card-actions\s*\{[^}]*gap:\s*6px")
        self.assertRegex(styles, r"\.task-card-actions\s*\{[^}]*transform:\s*translateY\(-50%\)")
        self.assertRegex(styles, r"\.task-card-actions\s*\{[^}]*opacity:\s*0")
        self.assertRegex(styles, r"\.task-archive-button\s*,\s*\.task-delete-button\s*\{[^}]*display:\s*grid")
        self.assertRegex(styles, r"\.task-archive-button\s*,\s*\.task-delete-button\s*\{[^}]*place-items:\s*center")
        self.assertRegex(styles, r"\.task-archive-button\s*,\s*\.task-delete-button\s*\{[^}]*width:\s*26px")
        self.assertRegex(styles, r"\.task-delete-button\s*\{[^}]*background:\s*var\(--surface-soft\)")
        self.assertRegex(styles, r"\.task-delete-button\s*\{[^}]*color:\s*var\(--text-secondary\)")
        self.assertRegex(styles, r"\.task-action-icon\s*\{[^}]*display:\s*block")
        self.assertRegex(styles, r"\.task-action-icon\s*\{[^}]*stroke-linecap:\s*round")
        self.assertRegex(styles, r"\.task-card:hover\s+\.task-card-actions\s*,\s*\.task-card:focus-within\s+\.task-card-actions")
        self.assertRegex(styles, r"\.task-delete-button:hover\s*,\s*\.task-delete-button:focus-visible\s*\{[^}]*color:\s*var\(--danger\)")
    def test_history_cards_show_completed_or_failed_runtime(self) -> None:
        script = self._frontend_script_source()
        styles = Path("codex_image/webui/static/styles.css").read_text(encoding="utf-8")

        self.assertIn("function taskRuntimeText", script)
        self.assertIn("function taskCompletionTimestampText", script)
        self.assertIn("function taskCompletionTimestampTitle", script)
        self.assertIn('["completed", "failed", "partial_failed"].includes(task.status)', script)
        self.assertIn("task.started_at || task.created_at", script)
        self.assertIn("task.completed_at || task.updated_at", script)
        self.assertIn('formatTranslation("taskStatus.runtimeCompleted"', script)
        self.assertIn('formatTranslation("taskStatus.runtime"', script)
        self.assertIn('class="task-runtime"', script)
        self.assertIn('data-task-completed-at-id="${taskId}"', script)
        self.assertIn('title="${escapeHtml(completionTitle)}"', script)
        self.assertRegex(styles, r"\.task-card\s*\{[^}]*height:\s*82px")
        self.assertRegex(styles, r"\.task-runtime\s*\{[^}]*font-size:\s*11px")
        self.assertRegex(styles, r"\.task-runtime\s*\{[^}]*white-space:\s*nowrap")

    def test_task_cards_have_scoped_context_menu_actions(self) -> None:
        script = self._frontend_script_source()
        context_source = Path("codex_image/webui/frontend/src/task-context-menu.ts").read_text(encoding="utf-8")
        styles = Path("codex_image/webui/static/styles.css").read_text(encoding="utf-8")

        self.assertIn("function openTaskContextMenu", script)
        self.assertIn('els.taskList.addEventListener("contextmenu", handleTaskListContextMenu)', script)
        self.assertIn('event.key !== "ContextMenu"', script)
        self.assertIn('event.shiftKey && event.key === "F10"', script)
        self.assertIn('taskContextButton("view", translate("taskContext.view"))', script)
        self.assertNotIn('taskContextButton("restore"', script)
        self.assertIn('taskContextButton("copy-id", translate("taskContext.copyId"))', script)
        self.assertIn('taskContextButton("copy-prompt", translate("taskContext.copyPrompt")', script)
        self.assertIn('taskContextButton("reveal-output", translate("taskContext.revealOutput")', script)
        self.assertIn('taskContextButton("archive", translate("taskContext.archive"))', script)
        self.assertIn('taskContextButton("delete", translate("taskContext.delete")', script)
        self.assertIn('data-task-context-action="${action}"', script)
        self.assertIn('fetch(`/api/tasks/${encodeURIComponent(taskId)}/reveal-output`', script)
        self.assertIn('"X-Requested-With": "codex-image-webui"', script)
        self.assertIn("closeTaskContextMenu", script)
        self.assertIn("async function ensureTaskContextTaskDetail", context_source)
        self.assertIn("await ensureTaskContextTaskDetail(taskId, task)", context_source)
        self.assertIn('fetch(`/api/tasks/${encodeURIComponent(taskId)}`)', context_source)
        self.assertIn("replaceTaskInState(taskId, fullTask)", context_source)
        self.assertNotIn('await copyText(taskPromptText(task));', context_source)
        self.assertRegex(styles, r"\.task-context-menu\s*\{[^}]*position:\s*fixed")
        self.assertRegex(styles, r"\.task-context-menu\s*\{[^}]*z-index:\s*9300")
        self.assertRegex(styles, r"\.task-context-menu-button\s*\{[^}]*min-height:\s*30px")
        self.assertRegex(styles, r"\.task-context-menu-button\.danger\s*\{[^}]*color:\s*var\(--danger\)")
    def test_failed_tasks_can_retry_failed_outputs_from_preview(self) -> None:
        task_routes = Path("codex_image/webui/routes/tasks.py").read_text(encoding="utf-8")
        script = self._frontend_script_source()
        task_actions = self._task_actions_source()
        styles = Path("codex_image/webui/static/styles.css").read_text(encoding="utf-8")

        self.assertIn('@app.post("/api/tasks/{task_id}/retry-failed")', task_routes)
        self.assertIn("retry_failed_slots", task_routes)
        self.assertIn("function retryFailedTask", script)
        self.assertNotIn("data-retry-failed-task-id", script)
        self.assertNotIn("task-retry-button", script)
        self.assertIn("data-preview-retry-failed-task-id", script)
        self.assertIn("canRetryFailedTask(task)", script)
        self.assertIn('fetch(`/api/tasks/${encodeURIComponent(taskId)}/retry-failed`', script)
        self.assertIn("class TaskActionHttpError", task_actions)
        self.assertIn("function refreshTaskAfterActionConflict", task_actions)
        self.assertIn('fetch(`/api/tasks/${encodeURIComponent(normalizedTaskId)}`', task_actions)
        self.assertIn("if (await refreshTaskAfterActionConflict(taskId)) return;", task_actions)
        self.assertIn("isTaskActionConflict(error) && await refreshTaskAfterActionConflict(taskId)", task_actions)
        self.assertIn("retryFailureSummaryButton", script)
        self.assertNotIn(".task-retry-button", styles)
        self.assertRegex(styles, r"\.failure-summary-actions\s*\{[^}]*display:\s*flex")
        self.assertRegex(styles, r"\.failure-summary-actions\s*\{[^}]*flex-wrap:\s*wrap")
        self.assertRegex(styles, r"\.failure-summary-actions\s+\.ghost-button\s*\{[^}]*white-space:\s*nowrap")
        self.assertRegex(styles, r"\.failure-summary-actions\s+\.ghost-button\s*\{[^}]*flex:\s*0 0 auto")
    def test_partial_failed_tasks_can_accept_successes_from_preview(self) -> None:
        task_routes = Path("codex_image/webui/routes/tasks.py").read_text(encoding="utf-8")
        script = self._frontend_script_source()
        task_actions = self._task_actions_source()

        self.assertIn('@app.post("/api/tasks/{task_id}/accept-successes")', task_routes)
        self.assertIn("function acceptTaskSuccesses", script)
        self.assertIn("data-preview-accept-successes-task-id", script)
        self.assertIn("canAcceptTaskSuccesses(task)", script)
        self.assertIn('["failed", "partial_failed"].includes(task.status)', script)
        self.assertIn('fetch(`/api/tasks/${encodeURIComponent(taskId)}/accept-successes`', script)
        self.assertIn("updateTaskInState(updatedTask)", task_actions)
        self.assertIn("renderTasks({ preserveScroll: true })", task_actions)
        self.assertIn("isTaskActionConflict(error) && await refreshTaskAfterActionConflict(taskId)", task_actions)
        self.assertIn('translate("preview.acceptSuccesses")', script)

    def test_task_list_rerender_can_preserve_scroll_position(self) -> None:
        render_source = self._task_list_render_source()
        task_actions = self._task_actions_source()

        self.assertIn("function renderTasks(options: { preserveScroll?: boolean } = {})", render_source)
        self.assertIn("function captureTaskListScrollAnchor()", render_source)
        self.assertIn("function restoreTaskListScrollAnchor(anchor", render_source)
        self.assertIn("function taskListScrollContainer()", render_source)
        self.assertIn("requestAnimationFrame(restore)", render_source)
        self.assertIn('".task-card[data-task-id]"', render_source)
        self.assertIn("renderTasks({ preserveScroll: true })", task_actions)
    def test_retry_attempt_state_is_visible_in_cards_queue_and_preview(self) -> None:
        script = self._frontend_script_source()
        render_source = self._task_list_render_source()

        self.assertIn("function taskRetryStateText", script)
        self.assertIn("function taskRetryReasonText", script)
        self.assertIn('formatTranslation("taskStatus.waitingRetry"', script)
        self.assertIn('formatTranslation("taskStatus.manualRetryAvailable"', script)
        self.assertIn("taskRetryStateText(task)", render_source)
        self.assertIn("retryText", render_source)
        self.assertIn("retryState", script)
        self.assertIn("data-task-retry-id", script)
        self.assertIn("data-preview-retry-state", script)
        self.assertNotIn("data-queue-meta-id", self._queue_source())
    def test_first_running_attempt_is_not_labeled_as_retry(self) -> None:
        node = shutil.which("node")
        if node is None:
            self.skipTest("node is required for frontend behavior checks")
        script = self._frontend_script_source()
        harness = "\n".join(
            [
                self._extract_javascript_function(script, "positiveInt"),
                self._extract_javascript_function(script, "nonnegativeInt"),
                self._extract_javascript_function(script, "taskOutputRecordIsDeleted"),
                self._extract_javascript_function(script, "taskOutputRecordMatchesUrl"),
                self._extract_javascript_function(script, "taskOutputIndexFromUrl"),
                self._extract_javascript_function(script, "taskDeletedOutputIndexes"),
                self._extract_javascript_function(script, "taskOutputUrls"),
                self._extract_javascript_function(script, "taskOutputRecordHasDisplayableImage"),
                self._extract_javascript_function(script, "taskOutputRecordsByIndex"),
                self._extract_javascript_function(script, "taskVisibleCompletedCount"),
                self._extract_javascript_function(script, "taskHasNonRetryableError"),
                self._extract_javascript_function(script, "taskRetrySuccessfulCount"),
                self._extract_javascript_function(script, "taskPartialFailureCanRetryGenericInvalidRequest"),
                self._extract_javascript_function(script, "taskRetryReasonText"),
                self._extract_javascript_function(script, "taskRetryStateText"),
                """
                const i18nMessages = {
                  "taskDerived.usageLimited": "额度限制",
                  "taskStatus.connectionInterrupted": "连接中断",
                  "taskStatus.lastFailed": "上次失败",
                  "taskStatus.waitingRetry": "{reason}，等待重试（第 {attempt}/{max} 次尝试）",
                  "taskStatus.retrying": "{reason}，重试中（第 {attempt}/{max} 次尝试）",
                  "taskStatus.nonRetryableAttempt": "第 {attempt}/{max} 次，不可重试",
                  "taskStatus.manualRetryAvailable": "已停止，可手动重试失败图片",
                };
                function translate(key) {
                  return String(i18nMessages[key] || key);
                }
                function formatTranslation(key, values = {}) {
                  return String(i18nMessages[key] || key).replace(/\\{([^}]+)\\}/g, (_, name) => values[name] ?? "");
                }
                const firstRun = taskRetryStateText({ status: "running", attempts: 1, max_attempts: 2 });
                const firstRunWithPartialFailure = taskRetryStateText({
                  status: "running",
                  attempts: 1,
                  max_attempts: 2,
                  last_error: "1 of 2 images failed: IncompleteRead(4099 bytes read)"
                });
                const runningAutoRetry = taskRetryStateText({ status: "running", attempts: 2, max_attempts: 2, last_error: "temporary network timeout" });
                const runningManualRetry = taskRetryStateText({
                  status: "running",
                  attempts: 1,
                  max_attempts: 2,
                  last_error: "temporary network timeout",
                  retry_requested_at: "2026-05-22T13:30:00Z"
                });
                const queuedRetry = taskRetryStateText({ status: "queued", attempts: 1, max_attempts: 2, last_error: "temporary server failure" });
                const usageLimitFailure = taskRetryStateText({ status: "failed", attempts: 1, max_attempts: 2, last_error: "Codex usage limit reached" });
                const failedManualRetry = taskRetryStateText({ status: "failed", attempts: 1, max_attempts: 2, last_error: "temporary server failure" });
                const partialGenericInvalidRequest = taskRetryStateText({
                  status: "partial_failed",
                  attempts: 1,
                  max_attempts: 2,
                  generated_count: 1,
                  failed_count: 1,
                  total_count: 2,
                  outputs: [
                    { index: 1, status: "completed", url: "/outputs/task-image-1.png" },
                    { index: 2, status: "failed", error: "OpenAI-compatible images request failed: HTTP 400: {\\\"error\\\":{\\\"message\\\":\\\"err\\\",\\\"type\\\":\\\"invalid_request_error\\\",\\\"param\\\":\\\"\\\",\\\"code\\\":\\\"ERR-99E8C62955\\\"}}" },
                  ],
                  last_error: "1 of 2 images failed: OpenAI-compatible images request failed: HTTP 400: {\\\"error\\\":{\\\"message\\\":\\\"err\\\",\\\"type\\\":\\\"invalid_request_error\\\",\\\"param\\\":\\\"\\\",\\\"code\\\":\\\"ERR-99E8C62955\\\"}}"
                });
                const lightweightPartialGenericInvalidRequest = taskRetryStateText({
                  status: "partial_failed",
                  attempts: 1,
                  max_attempts: 2,
                  generated_count: 1,
                  failed_count: 1,
                  total_count: 2,
                  thumbnail_urls: ["/outputs/task-image-1-thumb.png"],
                  last_error: "1 of 2 images failed: OpenAI-compatible images request failed: HTTP 400: {\\\"error\\\":{\\\"message\\\":\\\"err\\\",\\\"type\\\":\\\"invalid_request_error\\\",\\\"param\\\":\\\"\\\",\\\"code\\\":\\\"ERR-99E8C62955\\\"}}"
                });
                const fullInvalidValueFailure = taskRetryStateText({
                  status: "failed",
                  attempts: 1,
                  max_attempts: 2,
                  last_error: "HTTP 400: {\\\"error\\\":{\\\"type\\\":\\\"invalid_request_error\\\",\\\"code\\\":\\\"invalid_value\\\"}}"
                });
                if (firstRun !== "") {
                  throw new Error(`expected first run to have no retry label, got ${firstRun}`);
                }
                if (firstRunWithPartialFailure !== "") {
                  throw new Error(`expected first run partial failure to have no retry label, got ${firstRunWithPartialFailure}`);
                }
                if (runningAutoRetry !== "连接中断，重试中（第 2/2 次尝试）") {
                  throw new Error(`expected running auto retry label, got ${runningAutoRetry}`);
                }
                if (runningManualRetry !== "连接中断，重试中（第 1/2 次尝试）") {
                  throw new Error(`expected running manual retry label, got ${runningManualRetry}`);
                }
                if (queuedRetry !== "上次失败，等待重试（第 2/2 次尝试）") {
                  throw new Error(`expected queued retry label, got ${queuedRetry}`);
                }
                if (usageLimitFailure !== "第 1/2 次，不可重试") {
                  throw new Error(`expected non-retryable usage limit label, got ${usageLimitFailure}`);
                }
                if (failedManualRetry !== "已停止，可手动重试失败图片") {
                  throw new Error(`expected manual retry label, got ${failedManualRetry}`);
                }
                if (partialGenericInvalidRequest !== "已停止，可手动重试失败图片") {
                  throw new Error(`expected partial generic invalid request to be manually retryable, got ${partialGenericInvalidRequest}`);
                }
                if (lightweightPartialGenericInvalidRequest !== "已停止，可手动重试失败图片") {
                  throw new Error(`expected lightweight partial generic invalid request to be manually retryable, got ${lightweightPartialGenericInvalidRequest}`);
                }
                if (fullInvalidValueFailure !== "第 1/2 次，不可重试") {
                  throw new Error(`expected invalid value failure to remain non-retryable, got ${fullInvalidValueFailure}`);
                }
                """,
            ]
        )
        result = subprocess.run([node, "-e", harness], check=False, text=True, capture_output=True)

        self.assertEqual(result.returncode, 0, result.stderr)
    def test_preview_supports_multiple_output_urls(self) -> None:
        html = Path("codex_image/webui/static/index.html").read_text(encoding="utf-8")
        script = self._frontend_script_source()
        styles = Path("codex_image/webui/static/styles.css").read_text(encoding="utf-8")

        self.assertIn('id="downloadAllButton"', html)
        self.assertIn('id="downloadSelectedButton"', html)
        self.assertIn('id="deleteUnselectedOutputsButton"', html)
        self.assertIn('id="previewSelectionCount"', html)
        self.assertIn("打包下载", html)
        self.assertIn("只下载精选", html)
        self.assertIn("删除未精选", html)
        self.assertIn("taskOutputUrls", script)
        self.assertIn("taskSelectedOutputIndexes", script)
        self.assertIn("taskOutputSelected", script)
        self.assertIn("output_urls", script)
        self.assertIn("multi-output", script)
        self.assertIn("updatePreviewDownloadActions", script)
        self.assertIn("updatePreviewSelectionActions", script)
        self.assertIn("taskOutputZipUrl", script)
        self.assertIn("taskSelectedOutputDownloadUrl", script)
        self.assertIn("deleteUnselectedOutputs", script)
        self.assertIn('fetch(`/api/tasks/${encodeURIComponent(taskId)}/outputs/${encodeURIComponent(String(outputIndex))}/selected`', script)
        self.assertIn('fetch(`/api/tasks/${encodeURIComponent(taskId)}/outputs/delete-unselected`', script)
        self.assertIn("data-preview-select-output-index", script)
        self.assertIn("const selectable = Number(totalCount) > 1;", script)
        self.assertIn("selectButton.hidden = !selectable;", script)
        self.assertIn("selectButton.disabled = !selectable;", script)
        self.assertIn('selectButton.title = selected ? translate("preview.removeFeatured") : translate("preview.addFeatured");', script)
        self.assertIn('translate("preview.selectedFeatured")', script)
        self.assertIn('formatTranslation("preview.selectedCount"', script)
        self.assertIn('translate("preview.selectionAdded")', script)
        self.assertIn('translate("preview.selectionRemoved")', script)
        self.assertIn('translate("preview.selectionUpdateFailed")', script)
        self.assertIn('formatTranslation("preview.deleteUnselectedDetail"', script)
        self.assertIn('card.classList.toggle("can-select-output", selectable);', script)
        self.assertIn("data-download-output-url", script)
        self.assertIn("下载该图片", script)
        self.assertNotIn("新标签页打开", script)
        self.assertRegex(styles, r"\.preview-heading-actions\s*\{[^}]*display:\s*flex")
        self.assertRegex(styles, r"\.preview-heading-actions\s*>\s*\.ghost-button\s*\{[^}]*height:\s*32px")
        self.assertRegex(styles, r"\.preview-heading-actions\s*>\s*\.ghost-button\s*\{[^}]*font-size:\s*13px")
        self.assertRegex(styles, r"\.preview-heading-actions\s*>\s*\.ghost-button\s*\{[^}]*text-decoration:\s*none")
        self.assertRegex(styles, r"\.preview-selection-actions\s*\{[^}]*display:\s*flex")
        self.assertRegex(styles, r"\.preview-select-button\s*\{[^}]*position:\s*absolute")
        self.assertRegex(styles, r"\.preview-select-button\[hidden\]\s*,\s*\.preview-card:not\(\.can-select-output\)\s+\.preview-select-button\s*,\s*\.preview-grid:not\(\.multi-output\)\s+\.preview-select-button\s*\{[^}]*display:\s*none")
        self.assertRegex(styles, r"\.preview-select-button\s*\{[^}]*width:\s*32px")
        self.assertRegex(styles, r"\.preview-index\s*\{[^}]*background:\s*color-mix\(in srgb,\s*var\(--primary-strong\) 84%,\s*transparent\)")
        self.assertRegex(styles, r"\.preview-select-button\s*\{[^}]*background:\s*color-mix\(in srgb,\s*var\(--primary-light\) 78%,\s*var\(--surface\) 22%\)")
        self.assertRegex(styles, r"\.preview-select-button\s*\{[^}]*color:\s*var\(--primary-strong\)")
        self.assertRegex(styles, r"\.preview-select-button\s*\{[^}]*opacity:\s*0\.92")
        self.assertRegex(styles, r"\.preview-card\.is-selected\s*\{[^}]*border-color:\s*var\(--primary\)")
        self.assertRegex(styles, r"\.preview-select-button\[aria-pressed=\"true\"\]\s*\{[^}]*background:\s*var\(--primary\)")
        self.assertRegex(styles, r"\.preview-select-button\[aria-pressed=\"true\"\]\s*\{[^}]*opacity:\s*1")
        self.assertRegex(styles, r"\.preview-overlay\s*\{[^}]*background:\s*linear-gradient")
        self.assertNotRegex(styles, r"\.preview-overlay\s*\{[^}]*rgba\(0,\s*0,\s*0,\s*0\.78\)")
        self.assertRegex(styles, r"\.preview-select-label\s*\{[^}]*display:\s*none")
        self.assertRegex(styles, r"\.preview-select-button:hover\s+\.preview-select-label\s*,\s*\.preview-select-button:focus-visible\s+\.preview-select-label\s*,\s*\.preview-select-button\[aria-pressed=\"true\"\]\s+\.preview-select-label\s*\{[^}]*display:\s*inline")
        self.assertRegex(styles, r"\.add-to-input-btn\s*,\s*\.collect-input-btn\s*,\s*\.prompt-popover-button\s*,\s*\.preview-download-link\s*\{[^}]*min-height:\s*32px")
        self.assertRegex(styles, r"\.preview-grid\.multi-output\s*\{[^}]*grid-template-columns:\s*repeat")
        self.assertRegex(styles, r"\.preview-grid\.multi-output\s*\{[^}]*overflow:\s*hidden")
        self.assertNotRegex(styles, r"\.preview-grid\.multi-output\s*\{[^}]*overflow:\s*auto")
    def test_preview_grid_adapts_to_count_and_image_orientation(self) -> None:
        script = self._frontend_script_source()
        styles = Path("codex_image/webui/static/styles.css").read_text(encoding="utf-8")

        self.assertIn("applyPreviewGridLayout", script)
        self.assertIn("syncPreviewImageOrientation", script)
        self.assertIn('`preview-count-${outputCount}`', script)
        self.assertIn('"preview-orientation-portrait"', script)
        self.assertIn('"preview-orientation-landscape"', script)
        self.assertIn('"preview-orientation-square"', script)
        self.assertRegex(styles, r"\.preview-grid\.preview-count-4\.preview-orientation-portrait\s*\{[^}]*grid-template-columns:\s*repeat\(2")
        self.assertRegex(styles, r"\.preview-grid\.preview-count-4\.preview-orientation-square\s*\{[^}]*grid-template-columns:\s*repeat\(2")
        self.assertRegex(styles, r"\.preview-grid\.preview-count-4\.preview-orientation-square\s*\{[^}]*grid-template-rows:\s*repeat\(2")
        self.assertRegex(styles, r"\.preview-grid\.preview-count-3\.preview-orientation-landscape\s*\{[^}]*grid-template-columns:\s*minmax\(0,\s*1fr\)")
        self.assertRegex(styles, r"\.preview-grid\.preview-count-3\.preview-orientation-landscape\s*\{[^}]*grid-template-rows:\s*repeat\(3")
        self.assertRegex(styles, r"\.preview-grid\.preview-count-2\.preview-orientation-square\s*\{[^}]*grid-template-columns:\s*minmax\(0,\s*1fr\)")
        self.assertRegex(styles, r"\.preview-grid\.preview-count-2\.preview-orientation-square\s*\{[^}]*grid-template-rows:\s*repeat\(2")
        self.assertRegex(styles, r"\.preview-grid\.preview-count-2\.preview-orientation-landscape\s*\{[^}]*grid-template-columns:\s*minmax\(0,\s*1fr\)")
        self.assertRegex(styles, r"\.preview-grid\.preview-count-2\.preview-orientation-landscape\s*\{[^}]*grid-template-rows:\s*repeat\(2")
        self.assertRegex(styles, r"\.preview-grid\.multi-output\.preview-orientation-landscape\s*\{[^}]*grid-auto-rows:\s*minmax\(0,\s*1fr\)")
        self.assertNotRegex(styles, r"\.preview-grid\.preview-orientation-landscape\s+\.preview-card\s+img\s*\{[^}]*height:\s*auto")
        self.assertIn("applyPreviewGridLayout(totalCount, itemCount)", script)
    def test_preview_switching_reuses_output_cards_instead_of_rebuilding_grid(self) -> None:
        source = self._task_preview_source()
        styles = Path("codex_image/webui/static/styles.css").read_text(encoding="utf-8")

        self.assertIn("function reconcilePreviewOutputCards(", source)
        self.assertIn("function ensurePreviewOutputCard(", source)
        self.assertIn("function updatePreviewOutputCard(", source)
        self.assertIn("function bindPreviewGridEvents(", source)
        self.assertIn("data-preview-card-key", source)
        self.assertIn("data-preview-output-url", source)
        self.assertIn("image.decode?.()", source)
        self.assertIn("let pendingPreviewRenderToken = 0", source)
        self.assertIn("const previousOutputCount = currentPreviewOutputCardCount()", source)
        self.assertIn("const preservePreviousImages = previousOutputCount === outputUrls.length", source)
        self.assertIn("const shouldDeferLayoutSwitch = !preservePreviousImages && outputUrls.length > 0", source)
        self.assertIn("scheduleDeferredPreviewRender(task, { running, failure, waiting, outputUrls, totalCount, itemCount })", source)
        self.assertIn("function scheduleDeferredPreviewRender(", source)
        self.assertIn("function commitOutputPreviewRender(", source)
        self.assertIn("const allImagesLoaded = await preloadPreviewImages(outputUrls)", source)
        self.assertIn("function preloadPreviewImages(", source)
        self.assertIn("imageAlreadyLoaded: allImagesLoaded", source)
        self.assertIn("preservePreviousImages: false", source)
        self.assertIn("reconcilePreviewOutputCards(task, outputUrls, totalCount, { preservePreviousImages, imageAlreadyLoaded })", source)
        self.assertIn("if (imageAlreadyLoaded) {", source)
        self.assertLess(source.index("const allImagesLoaded = await preloadPreviewImages(outputUrls)"), source.index("commitOutputPreviewRender(task, {"))
        self.assertIn("function clearPreviewImageBeforeLoad(", source)
        self.assertIn("visibleImage.hidden = true", source)
        self.assertIn("visibleImage.hidden = false", source)
        self.assertIn('visibleImage.removeAttribute("src")', source)
        self.assertIn("function waitForPreviewImageLoad(", source)
        self.assertIn("if (!loaded) {", source)
        self.assertIn("const loaded = image.complete && image.naturalWidth > 0 ? true : await loadedPromise", source)
        self.assertNotIn("image.complete ? image.naturalWidth > 0 : await loadedPromise", source)
        self.assertNotIn("if (image.complete) return Promise.resolve(image.naturalWidth > 0);", source)
        self.assertIn("function currentPreviewOrientationClass(", source)
        self.assertIn("const previousOrientationClass = currentPreviewOrientationClass()", source)
        self.assertIn('previousOrientationClass || "preview-orientation-unknown"', source)
        self.assertNotIn("Promise.race", source)
        self.assertNotIn("timeoutPreviewImageDecode", source)
        self.assertNotIn("state.previewRenderKey = nextPreviewKey;\n  clearPreviewGridLayout();", source)
        self.assertNotIn("els.previewGrid.innerHTML = outputUrls.map", source)
        self.assertIn('els.previewGrid.addEventListener("click", handlePreviewGridClick)', source)
        self.assertRegex(styles, r"\.preview-card\.is-loading-next\s*\{[^}]*background:\s*var\(--surface-soft\)")
        self.assertNotRegex(styles, r"\.preview-card\.is-loading-next\s+img\s*\{[^}]*opacity:\s*0\.")
    def test_running_preview_shows_partial_outputs(self) -> None:
        script = self._frontend_script_source()
        source = self._task_preview_source()
        styles = Path("codex_image/webui/static/styles.css").read_text(encoding="utf-8")

        self.assertIn("renderOutputPreview(selected, { running: true })", script)
        self.assertIn("taskGeneratedCount", script)
        self.assertIn("running-progress-card", script)
        self.assertIn('translate("preview.continueGenerating")', script)
        self.assertNotIn("Codex 生成没有真实百分比进度", script)
        self.assertNotIn("请不要重复点击", script)
        self.assertRegex(styles, r"\.running-progress-card\s*\{[^}]*display:\s*flex")
        self.assertIn("function taskProgressStartValue", script)
        self.assertIn('task.status === "running" && taskRetryStateText(task)', script)
        self.assertIn("task?.attempt_started_at || task?.updated_at || task?.retry_requested_at", script)
        self.assertIn("elapsedTimerSpan(\"running\", taskProgressStartValue(task))", script)
        self.assertIn("function previewElapsedLineHtml", source)
        self.assertIn('previewElapsedLineHtml("preview.progressLine"', source)
        self.assertIn('previewElapsedLineHtml("preview.elapsedLine"', source)
        self.assertNotIn('escapeHtml(formatTranslation("preview.progressLine", { generated, total, elapsed }))', source)
        self.assertNotIn('escapeHtml(formatTranslation("preview.elapsedLine", { elapsed }))', source)
        self.assertIn("elapsedTimerMarkup(totalMilliseconds)", script)
        self.assertIn("elapsedWheelMarkup(char)", script)
        self.assertIn("elapsedPartMarkup(elapsed.clock)", script)
        self.assertIn("updateElapsedPartElement(main, elapsed.clock)", script)
        self.assertIn('class="elapsed-main"', script)
        self.assertIn('class="elapsed-ms"', script)
        self.assertIn('class="elapsed-wheel"', script)
        self.assertIn('class="elapsed-wheel-strip"', script)
        self.assertIn('class="elapsed-meta"', script)
        self.assertRegex(styles, r"\.elapsed-timer\s*\{[^}]*font-size:\s*30px")
        self.assertRegex(styles, r"\.elapsed-line\s*\{[^}]*flex-wrap:\s*wrap")
        self.assertRegex(styles, r"\.elapsed-line\s*\{[^}]*white-space:\s*normal")
        self.assertRegex(styles, r"\.elapsed-timer\s*\{[^}]*max-width:\s*100%")
        self.assertRegex(styles, r"\.elapsed-timer\s*\{[^}]*width:\s*max-content")
        self.assertRegex(styles, r"\.elapsed-main\s*\{[^}]*min-width:\s*5ch")
        self.assertRegex(styles, r"\.elapsed-ms\s*\{[^}]*opacity:\s*0\.62")
        self.assertRegex(styles, r"\.elapsed-ms\s*\{[^}]*min-width:\s*2ch")
        self.assertRegex(styles, r"\.elapsed-wheel\s*\{[^}]*overflow:\s*hidden")
        self.assertRegex(styles, r"\.elapsed-wheel-strip\s*\{[^}]*transition:\s*transform")
        self.assertRegex(styles, r"\.elapsed-wheel-strip\s*\{[^}]*var\(--motion-fast\)")
        self.assertRegex(styles, r"var\(--digit-offset,\s*0\)")
        self.assertNotRegex(styles, r"\.elapsed-wheel-strip\s*\{[^}]*--digit-offset:\s*0")
        self.assertRegex(styles, r"\.waiting-preview\s+\.elapsed-timer\s*\{[^}]*font-size:\s*40px")
        self.assertRegex(styles, r"\.waiting-spinner\s*\{[^}]*width:\s*42px")
        self.assertRegex(styles, r"\.waiting-spinner\s*\{[^}]*height:\s*42px")
        self.assertRegex(styles, r"\.waiting-spinner::before\s*\{[^}]*border-right-color:\s*var\(--primary\)")
        self.assertNotRegex(styles, r"\.waiting-spinner::before\s*\{[^}]*conic-gradient")
        self.assertRegex(styles, r"\.waiting-spinner\s*\{[^}]*spinner-breathe")
        self.assertNotIn(".waiting-spinner::after", styles)
        self.assertNotIn("spinner-core", styles)
        self.assertRegex(styles, r"\.run-button\.running::before\s*\{[^}]*width:\s*20px")
        self.assertRegex(styles, r"\.run-button\.running::before\s*\{[^}]*conic-gradient")
    def test_running_preview_shows_failed_slot_reason(self) -> None:
        source = self._task_preview_source()
        script = self._frontend_script_source()
        styles = Path("codex_image/webui/static/styles.css").read_text(encoding="utf-8")

        self.assertIn("function taskRunningFailureKey(", source)
        self.assertIn("function runningFailureNotice(", source)
        self.assertIn('record.status !== "failed"', source)
        self.assertIn("task?.outputs", source)
        self.assertIn("taskRunningFailureKey(task)", source)
        self.assertIn("runningFailureNotice(task)", source)
        self.assertIn("data-preview-running-failure", script)
        self.assertIn('formatTranslation("preview.failedOutput"', script)
        self.assertRegex(
            source,
            r'if \(status === "running"\) \{[\s\S]*taskRunningFailureKey\(task\)',
        )
        self.assertRegex(styles, r"\.running-failure-notice\s*\{[^}]*border:\s*1px solid")
        self.assertRegex(styles, r"\.running-failure-notice\s*\{[^}]*max-height:\s*120px")
        self.assertRegex(styles, r"\.running-failure-notice\s+p\s*\{[^}]*overflow-wrap:\s*anywhere")
    def test_queued_preview_shows_partial_outputs(self) -> None:
        script = self._frontend_script_source()

        self.assertIn("renderOutputPreview(selected, { waiting: true })", script)
        self.assertIn("waitingProgressCard", script)
        self.assertIn('translate("preview.waitingContinue")', script)
        self.assertIn('["waiting", taskId, status, outputUrls', script)
    def test_progress_cards_wrap_long_retry_errors(self) -> None:
        styles = Path("codex_image/webui/static/styles.css").read_text(encoding="utf-8")

        self.assertRegex(styles, r"\.running-progress-card\s*\{[^}]*overflow:\s*hidden")
        self.assertRegex(styles, r"\.running-progress-card\s+p\s*\{[^}]*max-width:\s*100%")
        self.assertRegex(styles, r"\.running-progress-card\s+p\s*\{[^}]*overflow-wrap:\s*anywhere")
        self.assertRegex(styles, r"\.running-progress-card\s+p\s*\{[^}]*word-break:\s*break-word")
    def test_failed_preview_shows_existing_outputs(self) -> None:
        script = self._frontend_script_source()

        self.assertIn('selected?.status === "failed" || selected?.status === "partial_failed"', script)
        self.assertIn('renderOutputPreview(selected, { failure: true })', script)
        self.assertIn('if (task.status === "partial_failed") return translate("taskStatus.partialFailed");', script)
    def test_elapsed_labels_tick_in_tenths_without_rebuilding_preview_images(self) -> None:
        script = self._frontend_script_source()

        self.assertIn("uiClockTimerId", script)
        self.assertIn("startUiClock()", script)
        self.assertIn("window.setInterval(updateElapsedDisplays, 100)", script)
        self.assertIn("window.setInterval(updateRunFeedback, 100)", script)
        self.assertIn("function updateElapsedDisplays", script)
        self.assertIn("function elapsedMillisecondsSince", script)
        self.assertIn("function formatDurationTenths", script)
        self.assertIn("function formatDurationParts", script)
        self.assertIn("const deciseconds = Math.floor((safeMilliseconds % 1000) / 100)", script)
        self.assertIn('const fraction = `.${deciseconds}`', script)
        self.assertNotIn("String(milliseconds).padStart(3", script)
        self.assertIn("function updateElapsedTimerElement", script)
        self.assertIn("updateElapsedTimerElement(element, elapsedMillisecondsSince(element.dataset.previewStart))", script)
        self.assertIn("formatDurationTenths(elapsedMillisecondsSince(state.runStartedAt))", script)
        self.assertIn("updatePreviewElapsedDisplay()", script)
        self.assertIn("updateTaskElapsedDisplays()", script)
        queue_source = self._queue_source()
        self.assertIn("updateQueueElapsedDisplays()", queue_source)
        self.assertNotIn("window.updateQueueElapsedDisplays?.()", script)
        self.assertIn("previewStructureKey(selected)", script)
        self.assertIn("state.previewRenderKey === nextPreviewKey", script)
        self.assertIn("return updatePreviewElapsedDisplay()", script)
        self.assertIn('data-preview-elapsed="${escapeHtml(kind)}"', script)
        self.assertIn('data-task-status-id="${taskId}"', script)
        runtime_feedback_source = self._runtime_feedback_source()
        self.assertIn('import { cssEscape } from "./webui-utils";', runtime_feedback_source)
        self.assertIn("function activeElapsedTaskCards(", runtime_feedback_source)
        self.assertIn("const roots = [els.taskActiveList, els.taskList]", runtime_feedback_source)
        self.assertIn('root.querySelectorAll(`.task-card[data-task-id="${cssEscape(taskId)}"]`)', runtime_feedback_source)
        self.assertIn("function updateTaskElapsedCard(", runtime_feedback_source)
        self.assertNotIn("const root = els.taskHistoryShell || els.taskList", runtime_feedback_source)
        self.assertNotIn('root.querySelectorAll("[data-task-status-id]")', runtime_feedback_source)
        self.assertIn('statusRow.setAttribute("aria-label", accessibleLabel)', runtime_feedback_source)
        self.assertIn("function taskNeedsElapsedTick(", runtime_feedback_source)
        self.assertIn("if (!activeTasks.length) return;", runtime_feedback_source)
        self.assertIn("function setTextIfChanged(", runtime_feedback_source)
        self.assertIn("if (element.textContent !== text) element.textContent = text;", runtime_feedback_source)
        self.assertIn('document.addEventListener("visibilitychange", handleUiClockVisibilityChange)', runtime_feedback_source)
        self.assertIn("if (state.uiClockTimerId || document.hidden) return;", runtime_feedback_source)
        self.assertIn("getLegacyBridge().methods.updateTaskElapsedDisplays?.()", queue_source)
        self.assertNotIn('data-queue-meta-id="${taskId}"', queue_source)
    def test_history_list_skips_unchanged_renders_and_uses_delegated_events(self) -> None:
        script = self._frontend_script_source()
        render_source = self._task_list_render_source()
        selection_source = self._task_selection_source()
        actions_source = self._task_actions_source()

        self.assertIn("tasksRenderKey", script)
        self.assertIn("function taskListRenderKey", render_source)
        self.assertIn("if (state.tasksRenderKey === nextRenderKey)", script)
        self.assertNotIn("selectedTaskId: state.selectedTaskId", render_source)
        self.assertIn("function updateTaskSelectionVisuals", render_source)
        self.assertIn("function taskCardRoot()", render_source)
        self.assertIn("taskCardElement(taskId)", render_source)
        self.assertIn("const root = taskCardRoot();", render_source)
        self.assertIn('root.querySelectorAll(".task-card.active")', render_source)
        self.assertIn("updateTaskSelectionVisuals(taskId)", selection_source)
        self.assertIn("updateTaskSelectionVisuals(taskId)", actions_source)
        self.assertIn('data-active-label="${activeLabel}"', render_source)
        self.assertIn('selectedCard.setAttribute("aria-current", "true")', render_source)
        self.assertIn('card.removeAttribute("aria-current")', render_source)
        self.assertIn("function bindTaskListEvents", script)
        self.assertIn("const interactiveRoot = els.taskHistoryShell || els.sidebarContent || els.taskList;", script)
        self.assertIn("interactiveRoot?.addEventListener(\"click\", handleTaskListClick)", script)
        self.assertIn("interactiveRoot?.addEventListener(\"keydown\", handleTaskListKeydown)", script)
        self.assertNotIn('els.taskList.querySelectorAll(".task-card[data-task-id]").forEach((card)', script)
        self.assertNotIn('els.taskList.querySelectorAll("[data-delete-task-id]").forEach((button)', script)
    def test_queue_list_skips_unchanged_renders_and_uses_delegated_events(self) -> None:
        script = self._queue_source()

        self.assertIn("queueRenderKey", script)
        self.assertIn("function queueListRenderKey", script)
        self.assertIn("if (state.queueRenderKey === nextRenderKey)", script)
        self.assertNotIn("function bindQueueListEvents", script)
        self.assertNotIn("els.queueWaitingList", script)
        self.assertNotIn("function handleQueueWaitingClick", script)
        self.assertIn("function handleQueueDragStart", script)
        self.assertNotIn('els.queueWaitingList.querySelectorAll("[data-promote-queue-task-id]").forEach((button)', script)
    def test_task_unread_state_and_document_title_updates_exist(self) -> None:
        script = self._frontend_script_source()
        styles = Path("codex_image/webui/static/styles.css").read_text(encoding="utf-8")

        self.assertIn("const DEFAULT_DOCUMENT_TITLE", script)
        self.assertIn("function updateDocumentTitle", script)
        self.assertIn("document.title =", script)
        self.assertIn("function taskHasUnreadUpdate", script)
        self.assertIn("function markTaskViewed", script)
        self.assertIn('/api/tasks/${encodeURIComponent(taskId)}/viewed', script)
        self.assertIn("data-task-unread", script)
        self.assertIn("task-unread-dot", script)
        self.assertIn('"taskList.viewing": "查看中"', script)
        self.assertIn('"taskList.viewing": "Viewing"', script)
        self.assertRegex(styles, r"\.task-card\.unread\s*\{[^}]*border-color:")
        self.assertRegex(styles, r"\.task-unread-dot\s*\{[^}]*border-radius:\s*999px")
    def test_preview_outputs_can_be_collected_into_floating_reference_bar(self) -> None:
        html = Path("codex_image/webui/static/index.html").read_text(encoding="utf-8")
        script = self._frontend_script_source()
        styles = Path("codex_image/webui/static/styles.css").read_text(encoding="utf-8")

        self.assertRegex(html, r'id="imageStrip"[\s\S]*id="imageThumbList"[\s\S]*id="imageUploadSource"[\s\S]*id="referenceCollector"')
        self.assertIn("collectedReferences: []", script)
        self.assertIn('data-collect-input-url=""', script)
        self.assertIn("collectButton.dataset.collectInputUrl = outputUrl", script)
        self.assertIn("collectButton.dataset.collectOutputName = downloadName", script)
        self.assertIn('translate("preview.addReference")', script)
        self.assertIn('data-i18n="preview.addReference"', script)
        self.assertIn('translate("preview.stage")', script)
        self.assertIn('data-i18n="preview.stage"', script)
        self.assertIn('data-i18n-attr="aria-label:preview.stageReference;title:preview.stageReference"', script)
        self.assertIn("function collectReferenceOutput", script)
        self.assertIn("function renderReferenceCollector()", script)
        self.assertIn("function removeCollectedReference", script)
        self.assertIn("function clearCollectedReferences", script)
        self.assertIn("async function addCollectedReferencesToInput()", script)
        self.assertIn("state.collectedReferences.some((item) => item.url === url)", script)
        self.assertIn("state.collectedReferences.push({", script)
        self.assertIn('setStatus(translate("referenceCollector.alreadyStaged"), "ok")', script)
        self.assertIn('formatTranslation("referenceCollector.staged"', script)
        self.assertIn('formatTranslation("referenceCollector.title"', script)
        self.assertIn('translate("referenceCollector.addAll")', script)
        self.assertIn('translate("action.clear")', script)
        self.assertIn('translate("referenceCollector.itemFallback")', script)
        self.assertIn('formatTranslation("referenceCollector.remove"', script)
        self.assertIn('setStatus(translate("referenceCollector.cleared"), "ok")', script)
        self.assertIn('formatTranslation("referenceCollector.added"', script)
        self.assertIn('translate("referenceCollector.addFailed")', script)
        self.assertIn('const collectButton = target.closest("[data-collect-input-url]")', script)
        self.assertIn("collectReferenceOutput(collectButton.dataset.collectInputUrl, {", script)
        self.assertIn('sourceTaskId: state.previewTask?.task_id || ""', script)
        self.assertIn("outputIndex: positiveInt(collectButton.dataset.collectOutputIndex) || null", script)
        self.assertIn("data-reference-collector-add-all", script)
        self.assertIn("data-reference-collector-clear", script)
        self.assertIn("data-reference-collector-remove", script)
        self.assertRegex(styles, r"\.image-uploader-grid\s*\{[^}]*position:\s*relative")
        self.assertRegex(styles, r"\.reference-collector\s*\{[^}]*position:\s*absolute")
        self.assertRegex(styles, r"\.reference-collector\s*\{[^}]*top:\s*8px")
        self.assertRegex(styles, r"\.reference-collector\s*\{[^}]*left:\s*8px")
        self.assertRegex(styles, r"\.reference-collector\.hidden\s*\{[^}]*display:\s*none")
        self.assertRegex(styles, r"\.reference-collector-list\s*\{[^}]*display:\s*flex")
        self.assertRegex(styles, r"\.add-to-input-btn\s*,\s*\.collect-input-btn\s*,\s*\.prompt-popover-button\s*,\s*\.preview-download-link\s*\{[^}]*min-height:\s*32px")
        self.assertRegex(styles, r"\.collect-input-btn\s*\{[^}]*color:\s*var\(--text-secondary\)")
    def test_sidebar_archive_and_batch_session_controls_exist(self) -> None:
        html = Path("codex_image/webui/static/index.html").read_text(encoding="utf-8")
        script = self._frontend_script_source()
        styles = Path("codex_image/webui/static/styles.css").read_text(encoding="utf-8")

        self.assertNotIn('id="archiveButton"', html)
        self.assertIn('id="batchManageButton"', html)
        self.assertIn('id="archiveModal"', html)
        self.assertIn('id="archiveList"', html)
        self.assertIn('id="batchToolbar"', html)
        self.assertIn('id="batchArchiveButton"', html)
        self.assertIn('id="batchDeleteButton"', html)
        self.assertIn("ARCHIVED_TASKS_STORAGE_KEY", script)
        self.assertIn("localStorage.getItem(ARCHIVED_TASKS_STORAGE_KEY)", script)
        self.assertIn("localStorage.removeItem(ARCHIVED_TASKS_STORAGE_KEY)", script)
        self.assertNotIn("localStorage.setItem(ARCHIVED_TASKS_STORAGE_KEY", script)
        self.assertIn('fetch(`/api/tasks/${encodeURIComponent(taskId)}/archive`', script)
        self.assertIn("JSON.stringify({ archived })", script)
        self.assertIn("migrateLegacyArchivedTasks", script)
        self.assertIn("Boolean(task?.archived_at)", script)
        self.assertIn("batchManageButton: document.querySelector(\"#batchManageButton\")", script)
        self.assertIn("openArchiveModal", script)
        self.assertIn("archiveTask", script)
        self.assertIn("restoreArchivedTask", script)
        self.assertIn("toggleBatchMode", script)
        self.assertIn("archiveSelectedTasks", script)
        self.assertIn("deleteSelectedTasks", script)
        self.assertIn("batchSelectionAnchorTaskId", script)
        self.assertIn("handleBatchTaskShortcutSelection", script)
        self.assertIn("selectBatchTaskRange", script)
        self.assertIn("visibleBatchTaskIds", script)
        self.assertIn("event.shiftKey", script)
        self.assertIn("event.metaKey", script)
        self.assertIn("event.ctrlKey", script)
        self.assertIn("data-archive-task-id", script)
        self.assertIn("data-batch-select-task-id", script)
        self.assertIn("state.tasks.filter((task) => !isTaskArchived(task.task_id))", script)
        self.assertRegex(styles, r"\.task-card-actions\s*\{[^}]*z-index:\s*2")
        self.assertRegex(styles, r"\.task-archive-button\s*,\s*\.task-delete-button\s*\{[^}]*height:\s*26px")
        self.assertRegex(styles, r"\.task-card:hover\s+\.task-card-actions\s*,\s*\.task-card:focus-within\s+\.task-card-actions")
        self.assertRegex(styles, r"\.batch-toolbar\s*\{[^}]*display:\s*grid")
        self.assertRegex(styles, r"\.archive-modal-panel\s*\{[^}]*width:\s*min\(520px,\s*94vw\)")
    def test_batch_mode_supports_drag_marquee_selection(self) -> None:
        script = self._frontend_script_source()
        styles = Path("codex_image/webui/static/styles.css").read_text(encoding="utf-8")

        self.assertIn("batchSelectionDrag: null", script)
        self.assertIn('els.taskList?.addEventListener("pointerdown", handleTaskListPointerDown)', script)
        self.assertIn('window.addEventListener("pointermove", handleTaskListPointerMove)', script)
        self.assertIn('window.addEventListener("pointerup", handleTaskListPointerUp)', script)
        self.assertIn("function handleTaskListPointerDown", script)
        self.assertIn("function updateBatchMarqueeSelection", script)
        self.assertIn("function applyBatchSelectionPreview", script)
        self.assertIn("batch-selection-marquee", script)
        self.assertIn('els.taskList?.classList.toggle("batch-marquee-enabled", state.batchMode)', script)
        self.assertIn("card.getBoundingClientRect()", script)
        self.assertIn("rectsIntersect(selectionRect, cardRect)", script)
        self.assertRegex(styles, r"\.batch-selection-marquee\s*\{[^}]*position:\s*fixed")
        self.assertRegex(styles, r"\.batch-selection-marquee\s*\{[^}]*pointer-events:\s*none")
        self.assertRegex(styles, r"\.task-list\.batch-marquee-enabled\s+\.task-card\.batch-mode\s*\{[^}]*cursor:\s*crosshair")

from __future__ import annotations

import re
from pathlib import Path

from tests.webui_helpers import WebUIStaticTestCase


class WebUIStaticI18nTests(WebUIStaticTestCase):
    def test_language_bootstrap_and_switcher_exist_before_github(self) -> None:
        html = Path("codex_image/webui/static/index.html").read_text(encoding="utf-8")

        self.assertIn('const LOCALE_STORAGE_KEY = "codex-image-locale-preference";', html)
        self.assertRegex(html, r"document\.documentElement\.lang = locale;")
        self.assertRegex(html, r"document\.documentElement\.dataset\.locale = locale;")
        self.assertIn('id="languageSwitcher"', html)
        self.assertLess(html.index('id="languageSwitcher"'), html.index('id="githubLink"'))
        self.assertIn('data-language-option="zh-CN"', html)
        self.assertIn('data-language-option="en"', html)
        self.assertIn('aria-label="语言 / Language"', html)

    def test_i18n_source_exposes_locales_and_dom_translation(self) -> None:
        source_path = Path("codex_image/webui/frontend/src/i18n.ts")
        self.assertTrue(source_path.exists(), "i18n feature module should exist")

        source = source_path.read_text(encoding="utf-8")
        main_source = Path("codex_image/webui/frontend/src/main.ts").read_text(encoding="utf-8")
        elements_source = Path("codex_image/webui/frontend/src/elements.ts").read_text(encoding="utf-8")
        indicator_source = Path("codex_image/webui/frontend/src/segmented-indicator.ts").read_text(encoding="utf-8")

        self.assertIn('export type Locale = "zh-CN" | "en";', source)
        self.assertIn('const LOCALE_STORAGE_KEY = "codex-image-locale-preference";', source)
        self.assertIn("const DICTIONARIES", source)
        self.assertIn('"app.newTask": "新建"', source)
        self.assertIn('"app.newTask": "New"', source)
        self.assertIn('"outputSettings.title": "输出设置"', source)
        self.assertIn('"outputSettings.title": "Output"', source)
        self.assertIn('document.querySelectorAll<HTMLElement>("[data-i18n]")', source)
        self.assertIn('querySelectorAll<HTMLElement>("[data-i18n-attr]")', source)
        self.assertIn("window.__codexImageI18n", source)
        self.assertIn('import { initI18nFeature } from "./i18n";', main_source)
        self.assertIn("initI18nFeature();", main_source)
        self.assertIn('languageSwitcher: document.querySelector("#languageSwitcher")', elements_source)
        self.assertIn('"#languageSwitcher"', indicator_source)

    def test_static_markup_uses_translation_keys_for_primary_shell(self) -> None:
        html = Path("codex_image/webui/static/index.html").read_text(encoding="utf-8")

        for key in (
            "app.newTask",
            "queue.empty",
            "theme.system",
            "imageInput.title",
            "prompt.title",
            "prompt.run",
            "outputSettings.title",
            "preview.title",
            "settings.title",
            "apiSettings.title",
            "gallery.title",
        ):
            self.assertIn(f'data-i18n="{key}"', html)
        self.assertIn('data-i18n-attr="placeholder:sidebar.searchPlaceholder"', html)
        self.assertIn('data-i18n-attr="aria-label:prompt.editorLabel;data-placeholder:prompt.placeholder"', html)

    def test_language_switcher_styles_match_top_nav_controls(self) -> None:
        styles = Path("codex_image/webui/static/styles.css").read_text(encoding="utf-8")

        self.assertRegex(styles, r"\.language-switcher\s*\{[^}]*display:\s*inline-flex")
        self.assertRegex(styles, r"\.language-switcher\s*\{[^}]*height:\s*var\(--top-nav-control-height\)")
        self.assertRegex(styles, r"\.language-switcher\s*\{[^}]*border-radius:\s*var\(--top-nav-control-radius\)")
        self.assertRegex(styles, r"\.language-option\s*\{[^}]*height:\s*var\(--top-nav-segment-height\)")
        self.assertRegex(styles, r"\.language-option\.active\s*\{[^}]*background:\s*var\(--primary\)")

    def test_runtime_rendered_surfaces_use_i18n_keys(self) -> None:
        i18n_source = Path("codex_image/webui/frontend/src/i18n.ts").read_text(encoding="utf-8")
        runtime_sources = {
            "queue": Path("codex_image/webui/frontend/src/queue.ts").read_text(encoding="utf-8"),
            "notifications": Path("codex_image/webui/frontend/src/task-notifications.ts").read_text(encoding="utf-8"),
            "archive": Path("codex_image/webui/frontend/src/task-archive-controls.ts").read_text(encoding="utf-8"),
            "task_groups": Path("codex_image/webui/frontend/src/task-list-render.ts").read_text(encoding="utf-8"),
            "templates": Path("codex_image/webui/frontend/src/prompt-templates.ts").read_text(encoding="utf-8"),
            "gallery": Path("codex_image/webui/frontend/src/gallery-grid.ts").read_text(encoding="utf-8"),
            "gallery_categories": Path("codex_image/webui/frontend/src/gallery-categories.ts").read_text(encoding="utf-8"),
            "preview": Path("codex_image/webui/frontend/src/task-preview.ts").read_text(encoding="utf-8"),
            "api_settings": Path("codex_image/webui/frontend/src/api-provider-settings.ts").read_text(encoding="utf-8"),
            "storage": Path("codex_image/webui/frontend/src/storage-settings.ts").read_text(encoding="utf-8"),
            "image_strip": Path("codex_image/webui/frontend/src/image-strip.ts").read_text(encoding="utf-8"),
            "custom_size": Path("codex_image/webui/frontend/src/custom-size-controls.ts").read_text(encoding="utf-8"),
            "batch": Path("codex_image/webui/frontend/src/task-batch-controls.ts").read_text(encoding="utf-8"),
            "form": Path("codex_image/webui/frontend/src/form-controls.ts").read_text(encoding="utf-8"),
            "recent_assets": Path("codex_image/webui/frontend/src/recent-assets.ts").read_text(encoding="utf-8"),
            "input_sources": Path("codex_image/webui/frontend/src/input-sources.ts").read_text(encoding="utf-8"),
            "task_submit": Path("codex_image/webui/frontend/src/task-submit.ts").read_text(encoding="utf-8"),
            "task_selection": Path("codex_image/webui/frontend/src/task-selection.ts").read_text(encoding="utf-8"),
            "task_preview": Path("codex_image/webui/frontend/src/task-preview.ts").read_text(encoding="utf-8"),
            "overlay_popovers": Path("codex_image/webui/frontend/src/overlay-popovers.ts").read_text(encoding="utf-8"),
            "task_context_menu": Path("codex_image/webui/frontend/src/task-context-menu.ts").read_text(encoding="utf-8"),
            "prompt_templates": Path("codex_image/webui/frontend/src/prompt-templates.ts").read_text(encoding="utf-8"),
        }

        self.assertIn("export function formatTranslation", i18n_source)
        self.assertIn("new CustomEvent(LOCALE_CHANGE_EVENT", i18n_source)
        for key in (
            "taskGroup.today",
            "taskGroup.yesterday",
            "taskGroup.last7",
            "taskGroup.older",
            "queue.runningWaiting",
            "notifications.empty",
            "footer.archiveCount",
            "templates.availableCount",
            "gallery.drawerSubtitle",
            "gallery.dragSort",
            "preview.addReference",
            "apiSettings.modeImagesShort",
            "imageInput.uploadBadge",
            "imageInput.addToGalleryShort",
            "imageInput.editedBadge",
            "output.pixelPreviewValue",
            "batch.selectedCount",
            "prompt.runEdit",
            "recentAssets.deleteMessage",
            "recentAssets.deleted",
            "inputSource.uploadFallback",
            "status.missingRecentReference",
            "status.emptyPrompt",
            "status.loadedTask",
            "status.loadingHistoryInputs",
            "status.historyInputLoadFailed",
            "referenceCollector.title",
            "referenceCollector.addAll",
            "referenceCollector.added",
            "preview.selectedCount",
            "preview.selectedFeatured",
            "preview.removeFeatured",
            "preview.selectionAdded",
            "preview.deleteUnselectedDetail",
            "promptPopover.title",
            "promptPopover.original",
            "promptPopover.optimized",
            "promptPopover.copyOptimized",
            "taskContext.view",
            "taskContext.restore",
            "taskContext.delete",
            "templates.formTitle",
            "templates.formContent",
            "templates.formFavorite",
            "notifications.taskFailed",
            "notifications.taskPartial",
            "notifications.taskCompleted",
            "notifications.generationFailed",
            "notifications.successCount",
            "notifications.resultAvailable",
            "notifications.failedCount",
            "notifications.systemUnsupported",
            "notifications.systemBlocked",
            "notifications.systemDenied",
            "notifications.systemEnabled",
            "notifications.taskMissing",
            "queue.cancelRunningConfirm",
            "queue.cancelRunningFailed",
            "queue.cancelRunningMessage",
            "queue.cancelRunningTitleConfirm",
            "queue.deleteQueuedFailed",
            "queue.deleteWaitingMessage",
            "queue.deleteWaitingTitleConfirm",
            "queue.promoteFailed",
            "queue.queuedDeleted",
            "queue.reorderFailed",
            "queue.runningCancelled",
        ):
            self.assertIn(f'"{key}"', i18n_source)

        self.assertIn('formatTranslation("queue.runningWaiting"', runtime_sources["queue"])
        self.assertIn('translate("queue.empty")', runtime_sources["queue"])
        self.assertIn('translate("queue.promoteFailed")', runtime_sources["queue"])
        self.assertIn('translate("queue.deleteWaitingTitleConfirm")', runtime_sources["queue"])
        self.assertIn('translate("queue.deleteQueuedFailed")', runtime_sources["queue"])
        self.assertIn('translate("queue.cancelRunningTitleConfirm")', runtime_sources["queue"])
        self.assertIn('translate("queue.cancelRunningFailed")', runtime_sources["queue"])
        self.assertIn('translate("queue.reorderFailed")', runtime_sources["queue"])
        self.assertIn('formatTranslation("notifications.unread"', runtime_sources["notifications"])
        self.assertIn('translate("notifications.empty")', runtime_sources["notifications"])
        self.assertIn('translate("notifications.taskCompleted")', runtime_sources["notifications"])
        self.assertIn('formatTranslation("notifications.successCount"', runtime_sources["notifications"])
        self.assertIn('formatTranslation("footer.archiveCount"', runtime_sources["archive"])
        self.assertIn('translate("footer.archive")', runtime_sources["archive"])
        self.assertIn('translate("taskGroup.today")', runtime_sources["task_groups"])
        self.assertIn('translate("taskGroup.last7")', runtime_sources["task_groups"])
        self.assertIn('formatTranslation("templates.availableCount"', runtime_sources["templates"])
        self.assertIn('translate("templates.noMatch")', runtime_sources["templates"])
        self.assertIn('formatTranslation("gallery.drawerSubtitle"', runtime_sources["gallery"])
        self.assertIn('translate("gallery.use")', runtime_sources["gallery"])
        self.assertIn('defaultGalleryCategoryLabel', runtime_sources["gallery_categories"])
        self.assertIn('translate("preview.addReference")', runtime_sources["preview"])
        self.assertIn('translate("preview.stage")', runtime_sources["preview"])
        self.assertIn('translate("apiSettings.modeImagesShort")', runtime_sources["api_settings"])
        self.assertIn('translate("settings.status")', runtime_sources["storage"])
        self.assertIn('translate("imageInput.uploadBadge")', runtime_sources["image_strip"])
        self.assertIn('translate("imageInput.addToGalleryShort")', runtime_sources["image_strip"])
        self.assertIn('formatTranslation("output.pixelPreviewValue"', runtime_sources["custom_size"])
        self.assertIn('formatTranslation("batch.selectedCount"', runtime_sources["batch"])
        self.assertIn('translate(mode === "edit" ? "prompt.runEdit" : "prompt.run")', runtime_sources["form"])
        self.assertIn('formatTranslation("recentAssets.use"', runtime_sources["recent_assets"])
        self.assertIn('translate("recentAssets.deleteMessage")', runtime_sources["recent_assets"])
        self.assertIn('document.addEventListener(LOCALE_CHANGE_EVENT, renderRecentAssets);', runtime_sources["recent_assets"])
        self.assertIn('translate("inputSource.uploadFallback")', runtime_sources["input_sources"])
        self.assertIn('translate("status.missingRecentReference")', runtime_sources["task_submit"])
        self.assertIn('translate("status.emptyPrompt")', runtime_sources["task_submit"])
        self.assertIn('formatTranslation("status.loadedTask"', runtime_sources["task_selection"])
        self.assertIn('translate("status.loadingHistoryInputs")', runtime_sources["task_selection"])
        self.assertIn('formatTranslation("status.historyInputLoadFailed"', runtime_sources["task_selection"])
        self.assertIn('formatTranslation("referenceCollector.title"', runtime_sources["input_sources"])
        self.assertIn('translate("referenceCollector.addAll")', runtime_sources["input_sources"])
        self.assertIn('formatTranslation("referenceCollector.added"', runtime_sources["input_sources"])
        self.assertIn('formatTranslation("preview.selectedCount"', runtime_sources["task_preview"])
        self.assertIn('translate("preview.selectedFeatured")', runtime_sources["task_preview"])
        self.assertIn('translate("preview.removeFeatured")', runtime_sources["task_preview"])
        self.assertIn('formatTranslation("preview.deleteUnselectedDetail"', runtime_sources["task_preview"])
        self.assertIn('translate("promptPopover.title")', runtime_sources["overlay_popovers"])
        self.assertIn('translate("promptPopover.copyOptimized")', runtime_sources["overlay_popovers"])
        self.assertIn('taskContextButton("view", translate("taskContext.view"))', runtime_sources["task_context_menu"])
        self.assertIn('taskContextButton("delete", translate("taskContext.delete")', runtime_sources["task_context_menu"])
        self.assertIn('translate("templates.formTitle")', runtime_sources["prompt_templates"])
        self.assertIn('translate("templates.formContent")', runtime_sources["prompt_templates"])
        self.assertIn('translate("templates.formFavorite")', runtime_sources["prompt_templates"])

    def test_core_runtime_modules_do_not_keep_hardcoded_chinese_ui_copy(self) -> None:
        frontend_root = Path("codex_image/webui/frontend/src")
        core_runtime_files = (
            "api-provider-settings.ts",
            "auth-source.ts",
            "color-palette.ts",
            "custom-size-controls.ts",
            "gallery.ts",
            "gallery-categories.ts",
            "gallery-grid.ts",
            "gallery-item-actions.ts",
            "image-editor.ts",
            "input-sources.ts",
            "lightbox.ts",
            "main-model-combobox.ts",
            "prompt-colors.ts",
            "prompt-find-replace.ts",
            "prompt-gallery-chips.ts",
            "prompt-snippets.ts",
            "prompt-templates.ts",
            "quick-gallery.ts",
            "queue.ts",
            "runtime-feedback.ts",
            "shell-ui.ts",
            "size-presets.ts",
            "storage-settings.ts",
            "task-actions.ts",
            "task-archive-controls.ts",
            "task-batch-controls.ts",
            "task-derived.ts",
            "task-history-anchors.ts",
            "task-list-render.ts",
            "task-notifications.ts",
            "task-selection.ts",
            "task-submit.ts",
        )

        offenders: list[str] = []
        for filename in core_runtime_files:
            source = (frontend_root / filename).read_text(encoding="utf-8")
            for line_number, line in enumerate(source.splitlines(), 1):
                if re.search(r"[\u4e00-\u9fff]", line):
                    offenders.append(f"{filename}:{line_number}: {line.strip()}")

        self.assertEqual([], offenders)

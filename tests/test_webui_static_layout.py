from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

from tests.webui_helpers import WebUIStaticTestCase


class WebUIStaticLayoutTests(WebUIStaticTestCase):
    def _extract_css_at_rule(self, styles: str, marker: str) -> str:
        start = styles.index(marker)
        return self._extract_css_at_rule_from(styles, marker, start)

    def _extract_last_css_at_rule(self, styles: str, marker: str) -> str:
        start = styles.rindex(marker)
        return self._extract_css_at_rule_from(styles, marker, start)

    def _extract_css_at_rule_from(self, styles: str, marker: str, start: int) -> str:
        brace_start = styles.index("{", start)
        depth = 0
        for index in range(brace_start, len(styles)):
            char = styles[index]
            if char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    return styles[start:index + 1]
        raise AssertionError(f"Could not extract CSS at-rule {marker}")

    def test_selected_reference_files_do_not_expand_or_reflow_footer(self) -> None:
        module = Path("codex_image/webui/frontend/src/reference-file-inputs.ts").read_text(encoding="utf-8")
        styles = Path("codex_image/webui/static/styles/50-image-input-gallery.css").read_text(encoding="utf-8")
        self.assertNotIn("syncReferenceFileWorkspaceClass", module)
        self.assertNotIn("recentReferenceFiles", module)
        self.assertNotRegex(styles, r"\.image-input-footer[^{]*\{[^}]*reference-file-selection")

    def test_reference_file_tiles_share_image_rail_without_recent_file_product_surface(self) -> None:
        module = Path("codex_image/webui/frontend/src/reference-file-inputs.ts").read_text(encoding="utf-8")
        styles = Path("codex_image/webui/static/styles/50-image-input-gallery.css").read_text(encoding="utf-8")
        responsive = Path("codex_image/webui/static/styles/80-utilities-responsive.css").read_text(encoding="utf-8")
        self.assertIn(".reference-file-selection.hidden", styles)
        self.assertNotIn("recent-reference-file", styles)
        self.assertNotIn("has-reference-files", styles)
        self.assertNotRegex(styles, r"\.reference-file-selection\s*\{[^}]*position:\s*absolute")
        self.assertNotRegex(styles, r"\.reference-file-selection\s*\{[^}]*overflow-x:\s*auto")
        self.assertRegex(styles, r"\.image-thumb-items\s*,\s*\.reference-file-selection\s*\{[^}]*display:\s*contents")
        self.assertIn("tile.append(icon, name, remove)", module)
        self.assertRegex(
            styles,
            r"\.reference-file-thumb \.reference-file-format-icon\s*\{[^}]*width:\s*44px[^}]*height:\s*50px",
        )
        self.assertNotIn(".reference-file-row", styles)
        self.assertNotRegex(responsive, r"\.reference-file-selection\s*\{[^}]*overflow-y:\s*auto")

    def test_task_notification_settings_are_in_system_settings_storage_tab(self) -> None:
        html = Path("codex_image/webui/static/index.html").read_text(encoding="utf-8")
        source = self._task_notifications_source()
        styles = Path("codex_image/webui/static/styles.css").read_text(encoding="utf-8")

        self.assertIn('id="taskNotificationInApp"', html)
        self.assertIn('id="taskNotificationSystem"', html)
        self.assertIn("站内通知", html)
        self.assertIn("系统通知", html)
        self.assertIn("inApp: true", source)
        self.assertIn("system: false", source)
        self.assertIn("Notification.permission", source)
        self.assertRegex(styles, r"\.notification-options-panel\s*\{[^}]*display:\s*grid")
        self.assertRegex(styles, r"\.notification-option-row\s*\{[^}]*display:\s*flex")

    def test_task_history_anchor_navigation_layout_contract(self) -> None:
        html = Path("codex_image/webui/static/index.html").read_text(encoding="utf-8")
        styles = Path("codex_image/webui/static/styles.css").read_text(encoding="utf-8")

        self.assertIn('class="task-history-shell"', html)
        self.assertIn('id="taskHistoryTopAnchors"', html)
        self.assertIn('id="taskHistoryBottomAnchors"', html)
        self.assertRegex(styles, r"\.task-history-shell\s*\{[^}]*display:\s*flex")
        self.assertRegex(styles, r"\.task-history-shell\s*\{[^}]*flex-direction:\s*column")
        self.assertRegex(styles, r"\.task-history-shell\s*\{[^}]*min-height:\s*0")
        self.assertRegex(styles, r"\.task-history-shell\s*\{[^}]*gap:\s*6px")
        self.assertRegex(styles, r"\.task-history-anchor-rail\s*\{[^}]*display:\s*grid")
        self.assertRegex(styles, r"\.task-history-anchor-rail\s*\{[^}]*padding-right:\s*var\(--task-history-scrollbar-offset,\s*0px\)")
        self.assertRegex(styles, r"\.task-history-anchor-rail-top\s*\{[^}]*padding-top:\s*0")
        self.assertRegex(styles, r"\.task-history-anchor-row\s*,[\s\S]*\.task-group-header-split\s*\{[^}]*border:\s*1px\s+solid\s+var\(--panel-border\)")
        self.assertRegex(styles, r"\.task-group-header-split\s*\{[^}]*background:\s*var\(--surface\)")
        self.assertRegex(styles, r"\.sidebar-content\s*\{[^}]*flex:\s*1")
        self.assertRegex(styles, r"\.sidebar-content\s*\{[^}]*min-height:\s*0")
        self.assertNotIn(".task-history-anchor-overlay", styles)
        self.assertNotIn("--task-history-top-anchor-height", styles)
        self.assertNotIn("--task-history-bottom-anchor-height", styles)
        self.assertRegex(
            styles,
            r"\.task-history-anchor-row\s*,[\s\S]*\.task-group-header-split\s*\{[^}]*transition:",
        )
        self.assertRegex(styles, r"\.task-group-items\s*\{[^}]*transition:")
        self.assertRegex(
            styles,
            r"@media \(prefers-reduced-motion:\s*reduce\)\s*\{[\s\S]*\.task-history-anchor-row\s*,[\s\S]*\.task-group-header-split\s*,[\s\S]*\.task-group-items\s*,[\s\S]*\.task-card\s*,[\s\S]*\.task-queue-actions\s*,[\s\S]*\.task-thumb-stack img\s*,[\s\S]*\.task-group-toggle\s*,[\s\S]*transition:\s*none",
        )

    def test_motion_tokens_are_defined_and_sidebar_avoids_transition_all(self) -> None:
        tokens = Path("codex_image/webui/static/styles/00-tokens.css").read_text(encoding="utf-8")
        sidebar = Path("codex_image/webui/static/styles/10-sidebar.css").read_text(encoding="utf-8")
        tasks = Path("codex_image/webui/static/styles/20-tasks.css").read_text(encoding="utf-8")
        styles = Path("codex_image/webui/static/styles.css").read_text(encoding="utf-8")

        self.assertIn("--motion-fast: 140ms ease;", tokens)
        self.assertIn("--motion-base: 180ms ease;", tokens)
        self.assertIn("--motion-height: 220ms ease;", tokens)
        self.assertIn("--motion-base: 180ms ease;", styles)
        self.assertNotRegex(sidebar, r"transition:\s*all")
        self.assertNotRegex(tasks, r"transition:\s*all")
        self.assertNotIn("will-change", tasks)
        self.assertRegex(styles, r"\.task-card\s*\{[^}]*background var\(--motion-base\)")
        self.assertRegex(styles, r"\.task-card:focus-visible\s*\{[^}]*outline:\s*2px solid var\(--primary\)")
        self.assertRegex(styles, r"\.task-card\.active:focus-visible,\s*\.task-card\.batch-selected:focus-visible\s*\{[^}]*outline:\s*none")
        self.assertRegex(
            styles,
            r"\.sidebar-resize-handle:hover::before[\s\S]*color-mix\(in srgb, var\(--primary\) 34%, transparent\)",
        )
        self.assertNotRegex(tasks, r"rgba\(69,\s*123,\s*102")
        self.assertNotRegex(tasks, r"rgba\(166,\s*70,\s*61")
        self.assertNotRegex(tasks, r"rgba\(47,\s*111,\s*228")
        self.assertNotRegex(tasks, r"rgba\(155,\s*127,\s*79")
        self.assertNotRegex(tasks, r"rgba\(136,\s*157,\s*149")

    def test_main_surface_motion_uses_tokens_and_reduced_motion(self) -> None:
        source_paths = [
            Path("codex_image/webui/static/styles/30-layout-top-nav-panels.css"),
            Path("codex_image/webui/static/styles/40-controls.css"),
            Path("codex_image/webui/static/styles/50-image-input-gallery.css"),
            Path("codex_image/webui/static/styles/60-prompt.css"),
            Path("codex_image/webui/static/styles/70-output-settings.css"),
            Path("codex_image/webui/static/styles/71-preview-results.css"),
            Path("codex_image/webui/static/styles/72-queue-modals.css"),
            Path("codex_image/webui/static/styles/73-gallery-drawer.css"),
            Path("codex_image/webui/static/styles/74-api-system-settings.css"),
            Path("codex_image/webui/static/styles/75-gallery-card-image-editor.css"),
        ]
        source = "\n".join(path.read_text(encoding="utf-8") for path in source_paths)
        styles = Path("codex_image/webui/static/styles.css").read_text(encoding="utf-8")

        self.assertNotRegex(source, r"transition:\s*all")
        self.assertNotRegex(source, r"\b0\.(?:18|2)s\b")
        self.assertNotRegex(source, r"\b(?:140|160|180|220)ms ease\b")
        self.assertNotRegex(source, r"rgba\(69,\s*123,\s*102")
        self.assertNotRegex(source, r"rgba\(166,\s*70,\s*61")
        self.assertNotRegex(source, r"rgba\(155,\s*127,\s*79")
        self.assertRegex(styles, r"\.primary-button\s*\{[^}]*transition:\s*background var\(--motion-base\)")
        self.assertRegex(styles, r"\.ghost-button\s*\{[^}]*background var\(--motion-base\)")
        self.assertRegex(styles, r"\.segmented-indicator\s*\{[^}]*transform var\(--motion-base\)")
        self.assertRegex(styles, r"\.segmented-indicator\s*\{[^}]*opacity var\(--motion-fast\)")
        self.assertRegex(styles, r"\.image-input-main\s*\{[^}]*border-color var\(--motion-base\)")
        self.assertRegex(styles, r"\.quick-gallery-item\s*\{[^}]*opacity var\(--motion-base\)")
        self.assertRegex(styles, r"\.resource-sheet\s*\{[^}]*transform var\(--motion-fast\)")
        self.assertRegex(styles, r"\.settings-grid\s*\{[^}]*transition:\s*height var\(--motion-height\)")
        self.assertRegex(styles, r"\.custom-size\s*\{[^}]*max-height var\(--motion-height\)")
        self.assertRegex(styles, r"\.gallery-grid\s*\{[^}]*transition:\s*height var\(--motion-height\)")
        self.assertRegex(styles, r"\.preview-overlay\s*\{[^}]*transition:\s*opacity var\(--motion-base\)")
        self.assertRegex(
            styles,
            r"@media \(prefers-reduced-motion:\s*reduce\)\s*\{[\s\S]*\.primary-button[\s\S]*\.upload-tile[\s\S]*\.quick-gallery-item[\s\S]*\.resource-sheet[\s\S]*transition:\s*none",
        )
        self.assertRegex(
            styles,
            r"@media \(prefers-reduced-motion:\s*reduce\)\s*\{[\s\S]*input\[type=range\]\.slider::-webkit-slider-thumb[\s\S]*\.preview-overlay[\s\S]*\.add-upload-to-gallery[\s\S]*transition:\s*none",
        )

    def test_closed_right_edge_drawers_do_not_cast_page_edge_shadow(self) -> None:
        styles = Path("codex_image/webui/static/styles.css").read_text(encoding="utf-8")
        resource_sheet_block = self._extract_css_block(styles, ".resource-sheet")
        resource_sheet_open_block = self._extract_css_block(styles, ".resource-sheet.open")
        queue_drawer_block = self._extract_css_block(styles, ".queue-drawer")
        queue_drawer_open_block = self._extract_css_block(styles, ".queue-drawer.open")

        self.assertIn("box-shadow: none", resource_sheet_block)
        self.assertIn("box-shadow: -18px 0 44px rgba(29, 52, 46, 0.16)", resource_sheet_open_block)
        self.assertIn("box-shadow: none", queue_drawer_block)
        self.assertIn("box-shadow: -18px 0 60px rgba(24, 45, 39, 0.18)", queue_drawer_open_block)

    def test_recent_reference_assets_are_rendered_and_submitted(self) -> None:
        html = Path("codex_image/webui/static/index.html").read_text(encoding="utf-8")
        script = self._frontend_script_source()
        styles = Path("codex_image/webui/static/styles.css").read_text(encoding="utf-8")

        self.assertIn('/static/app.js?v=runtime-568', html)
        self.assertIn('/static/styles.css?v=runtime-568', html)
        self.assertIn('id="recentAssetDock"', html)
        self.assertRegex(html, r'class="image-input-footer"[\s\S]*id="recentAssetDock"[\s\S]*id="recentAssetList"')
        self.assertRegex(html, r'id="recentAssetDock"[\s\S]*id="quickGalleryDock"[\s\S]*id="galleryManagePanel"')
        self.assertIn("recentAssets: []", script)
        self.assertIn("recentAssetDock: document.querySelector(\"#recentAssetDock\")", script)
        self.assertIn("recentAssetList: document.querySelector(\"#recentAssetList\")", script)
        self.assertIn("refreshRecentAssets();", script)
        self.assertIn("function refreshRecentAssets()", script)
        self.assertIn("function renderRecentAssets()", script)
        self.assertIn("function assetSource(item)", script)
        self.assertIn("function referenceAssetInputs()", script)
        self.assertIn("function addReferenceAssetInput(item)", script)
        self.assertIn("function canAddSourceToGallery(source)", script)
        self.assertIn("function galleryImageFileForSource(source)", script)
        self.assertIn("const referenceOffset = uploadInputs().length + referenceAssetInputs().length", script)
        self.assertIn("galleryReferenceInstruction(source, referenceOffset + index + 1)", script)
        self.assertIn('source.kind === "asset"', script)
        self.assertRegex(script, r"function canAddSourceToGallery\(source\)\s*\{[\s\S]*source\.kind === \"asset\"[\s\S]*sourcePreviewUrl\(source\)")
        self.assertRegex(script, r"async function saveUploadToGallery\(\)\s*\{[\s\S]*await galleryImageFileForSource\(source\)[\s\S]*form\.append\(\"image\", imageFile\)")
        self.assertIn('form.append("reference_asset_ids", source.id)', script)
        self.assertIn('fetch("/api/reference-assets/recent?limit=50")', script)
        self.assertIn("reference_asset_ids: assets.map((source) => source.id)", script)
        self.assertIn("data-reference-asset-delete", script)
        self.assertIn("function deleteRecentAsset", script)
        self.assertIn('fetch(`/api/reference-assets/${encodeURIComponent(assetId)}`', script)
        self.assertIn('method: "DELETE"', script)
        self.assertIn("function handleRecentAssetWheel", script)
        self.assertIn('els.recentAssetList?.addEventListener("wheel", handleRecentAssetWheel, { passive: false });', script)
        self.assertIn("const nextScrollLeft = Math.min(maxScrollLeft, Math.max(0, list.scrollLeft + wheelDelta));", script)
        self.assertIn("openConfirmPopover(button", script)
        self.assertIn('event.stopPropagation();', script)
        self.assertIn('message: translate("recentAssets.deleteMessage")', script)
        self.assertIn('document.addEventListener(LOCALE_CHANGE_EVENT, renderRecentAssets);', script)
        self.assertNotIn("不会影响公用图库或历史任务。", script)
        self.assertNotIn("已加入图像输入的同一图片也会移除", script)
        self.assertIn('translate("imageInput.recentBadge")', script)
        self.assertIn('translate("imageInput.uploadBadge")', script)
        self.assertIn('wrapper.className = `thumb ${source.kind === "gallery" ? "gallery-thumb" : source.kind === "asset" ? "asset-thumb" : "upload-thumb"}${source.missing ? " missing-thumb" : ""}`', script)
        self.assertIn("restoredSources.push(assetSource(source));", script)
        self.assertRegex(styles, r"\.recent-asset-list\s*\{[^}]*display:\s*flex")
        self.assertRegex(styles, r"\.recent-asset-list\s*\{[^}]*scrollbar-width:\s*none")
        self.assertRegex(styles, r"\.recent-asset-list\s*\{[^}]*-ms-overflow-style:\s*none")
        self.assertRegex(styles, r"\.recent-asset-list::\-webkit-scrollbar\s*\{[^}]*display:\s*none")
        self.assertRegex(styles, r"\.recent-asset-button\s*\{[^}]*width:\s*var\(--recent-asset-size\)")
        self.assertRegex(styles, r"\.recent-asset-button\s*\{[^}]*position:\s*relative")
        self.assertRegex(styles, r"\.recent-asset-button\s+img\s*\{[^}]*object-fit:\s*cover")
        self.assertRegex(styles, r"\.recent-asset-delete\s*\{[^}]*position:\s*absolute")
        self.assertRegex(styles, r"\.recent-asset-delete\s*\{[^}]*right:\s*-4px")
        self.assertRegex(styles, r"\.recent-asset-delete\s*\{[^}]*opacity:\s*0")
        self.assertRegex(styles, r"\.recent-asset-button:hover\s+\.recent-asset-delete\s*,\s*\.recent-asset-button:focus-within\s+\.recent-asset-delete\s*\{[^}]*opacity:\s*1")
        self.assertRegex(styles, r"\.asset-thumb\s*\{[^}]*border-color:")
    def test_input_sources_feature_has_typescript_source_contract(self) -> None:
        input_source = self._input_sources_source()
        legacy_source = self._bootstrap_source()

        self.assertIn("export function initInputSourcesFeature", input_source)
        self.assertIn("function addImageFiles", input_source)
        self.assertIn("function handleImagePaste", input_source)
        self.assertIn("function handleImageDrop", input_source)
        self.assertIn("function pasteClipboardImages", input_source)
        self.assertIn("function collectReferenceOutput", input_source)
        self.assertIn("Object.assign(getLegacyBridge().methods", input_source)
        for function_name in [
            "uploadSource",
            "gallerySource",
            "assetSource",
            "sourcePreviewUrl",
            "addImageFiles",
            "collectReferenceOutput",
            "imageFileFromUrl",
        ]:
            self._assert_bootstrap_proxy(legacy_source, function_name)
    def test_image_strip_feature_has_typescript_source_contract(self) -> None:
        image_strip_source = self._image_strip_source()
        legacy_source = self._bootstrap_source()
        main_source = Path("codex_image/webui/frontend/src/main.ts").read_text(encoding="utf-8")

        self.assertIn('import { initImageStripFeature } from "./image-strip"', main_source)
        self.assertLess(main_source.index('import { initImageEditorFeature } from "./image-editor"'), main_source.index('import { initImageStripFeature } from "./image-strip"'))
        self.assertLess(main_source.index("initImageEditorFeature()"), main_source.index("initImageStripFeature()"))
        self.assertLess(main_source.index("initImageStripFeature()"), main_source.index("initPromptFeature()"))
        self.assertIn("export function initImageStripFeature", image_strip_source)
        self.assertIn("function renderImageStrip", image_strip_source)
        self.assertIn("function clearImages", image_strip_source)
        self.assertIn("function addImages", image_strip_source)
        self.assertIn("function updateImageStripDensity", image_strip_source)
        self.assertIn('legacyMethod("updateCustomRatioReferenceButtonState")', image_strip_source)
        self.assertIn("Object.assign(getLegacyBridge().methods", image_strip_source)
        for function_name in [
            "renderImageStrip",
            "clearImages",
            "updateImageStripDensity",
        ]:
            self._assert_bootstrap_proxy(legacy_source, function_name)
    def test_gallery_feature_has_typescript_source_contract(self) -> None:
        gallery_source = self._gallery_source()
        legacy_source = self._bootstrap_source()
        event_source = Path("codex_image/webui/frontend/src/event-bindings.ts").read_text(encoding="utf-8")
        main_source = Path("codex_image/webui/frontend/src/main.ts").read_text(encoding="utf-8")

        self.assertIn('import { initGalleryFeature } from "./gallery"', main_source)
        self.assertLess(main_source.index('import { initImageStripFeature } from "./image-strip"'), main_source.index('import { initGalleryCategoriesFeature } from "./gallery-categories"'))
        self.assertLess(main_source.index("initGalleryItemActionsFeature()"), main_source.index("initGalleryFeature()"))
        self.assertLess(main_source.index("initGalleryFeature()"), main_source.index("initApiSettingsFeature()"))
        self.assertIn("export function initGalleryFeature", gallery_source)
        self.assertNotIn("@ts-nocheck", gallery_source)
        self.assertIn("function sortGalleryItems(items", gallery_source)
        self.assertIn("function filterGalleryItems(category", gallery_source)
        self.assertIn("async function refreshGallery()", gallery_source)
        self.assertIn("async function openGallery(category", gallery_source)
        self.assertIn("function closeGallery(options: any = {})", gallery_source)
        self.assertIn("function findGalleryItem(itemId", gallery_source)
        self.assertIn("function applyGalleryItemOrder(category", gallery_source)
        self.assertIn("async function persistGalleryItemOrder(category", gallery_source)
        self.assertIn("function handleGalleryManageButtonClick()", gallery_source)
        self.assertIn('els.galleryManageButton?.addEventListener("click", handleGalleryManageButtonClick)', gallery_source)
        self.assertNotIn('els.galleryManageButton?.addEventListener("click", () => call(methods, "openGallery"', event_source)
        self.assertIn("Object.assign(getLegacyBridge().methods", gallery_source)
        for function_name in [
            "refreshRecentAssets",
            "renderQuickGalleryDock",
            "renderGalleryGridWithHeightTransition",
            "openGalleryEditPopover",
            "saveUploadToGallery",
        ]:
            self.assertNotRegex(gallery_source, rf"\n(?:async\s+)?function {function_name}\(")
        self.assertNotRegex(legacy_source, r"\n(?:async\s+)?function refreshGallery\(")
        self.assertIn('refreshGallery: proxy("refreshGallery")', legacy_source)
    def test_gallery_categories_feature_has_typescript_source_contract(self) -> None:
        source = self._gallery_categories_source()
        gallery_source = self._gallery_source()
        main_source = Path("codex_image/webui/frontend/src/main.ts").read_text(encoding="utf-8")

        self.assertNotIn("@ts-nocheck", source)
        self.assertIn('import { initGalleryCategoriesFeature } from "./gallery-categories"', main_source)
        self.assertLess(main_source.index("initGalleryCategoriesFeature()"), main_source.index("initGalleryFeature()"))
        self.assertIn("export function initGalleryCategoriesFeature", source)
        self.assertIn("const DEFAULT_GALLERY_CATEGORY_LEGACY_LABELS", source)
        self.assertIn("const DEFAULT_GALLERY_CATEGORY_I18N_KEYS", source)
        self.assertIn("const DEFAULT_GALLERY_CATEGORY_ROLE_I18N_KEYS", source)
        for function_name in [
            "defaultGalleryCategories",
            "normalizeGalleryCategory",
            "normalizeGalleryCategories",
            "handleQuickGalleryCategoryEvent",
            "ensureActiveGalleryCategory",
            "renderGalleryCategoryControls",
            "renderGalleryDrawerCategoryTabs",
            "renderGalleryCategoryManager",
            "handleGalleryDrawerCategoryTabClick",
            "handleGalleryCategoryListClick",
            "toggleGalleryCategoryManager",
            "refreshGalleryCategories",
            "createGalleryCategory",
            "updateGalleryCategory",
            "deleteGalleryCategory",
            "performDeleteGalleryCategory",
            "setQuickGalleryCategory",
            "setGalleryDrawerCategory",
            "findGalleryCategory",
            "categoryLabel",
            "categoryPromptRole",
            "applyGalleryCategoryOrder",
            "persistGalleryCategoryOrder",
            "handleGalleryCategoryDragStart",
            "handleGalleryCategoryDragOver",
            "handleGalleryCategoryDrop",
            "handleGalleryCategoryDragEnd",
        ]:
            self.assertRegex(source, rf"\n(?:async\s+)?function {function_name}\(")
            self.assertNotRegex(gallery_source, rf"\n(?:async\s+)?function {function_name}\(")
        self.assertIn('els.galleryCategoryList?.addEventListener("click", handleGalleryCategoryListClick)', source)
        self.assertIn("Object.assign(getLegacyBridge().methods", source)
    def test_recent_assets_feature_has_typescript_source_contract(self) -> None:
        source = self._recent_assets_source()
        gallery_source = self._gallery_source()
        main_source = Path("codex_image/webui/frontend/src/main.ts").read_text(encoding="utf-8")

        self.assertNotIn("@ts-nocheck", source)
        self.assertIn('import { initRecentAssetsFeature } from "./recent-assets"', main_source)
        self.assertLess(main_source.index("initRecentAssetsFeature()"), main_source.index("initGalleryFeature()"))
        for function_name in [
            "refreshRecentAssets",
            "renderRecentAssets",
            "deleteRecentAsset",
        ]:
            self.assertRegex(source, rf"\n(?:async\s+)?function {function_name}\(")
            self.assertNotRegex(gallery_source, rf"\n(?:async\s+)?function {function_name}\(")
        self.assertIn('fetch("/api/reference-assets/recent?limit=50")', source)
        self.assertIn("addReferenceAssetInput(item)", source)
        self.assertIn("Object.assign(getLegacyBridge().methods", source)
    def test_quick_gallery_feature_has_typescript_source_contract(self) -> None:
        source = self._quick_gallery_source()
        gallery_source = self._gallery_source()
        main_source = Path("codex_image/webui/frontend/src/main.ts").read_text(encoding="utf-8")

        self.assertNotIn("@ts-nocheck", source)
        self.assertIn('import { prefersReducedMotion } from "./webui-utils";', source)
        self.assertIn('import { initQuickGalleryFeature } from "./quick-gallery"', main_source)
        self.assertLess(main_source.index("initQuickGalleryFeature()"), main_source.index("initGalleryFeature()"))
        self.assertIn("const QUICK_GALLERY_WHEEL_COOLDOWN_MS", source)
        for function_name in [
            "renderQuickGalleryDock",
            "renderQuickGalleryList",
            "ensureQuickGalleryFocusItem",
            "previewQuickGalleryItem",
            "hideQuickGalleryPreview",
            "scheduleQuickGalleryFocusUpdate",
            "updateQuickGalleryFocus",
            "handleQuickGalleryBoundaryWheel",
            "triggerQuickGalleryBounce",
            "currentQuickGalleryFocusIndex",
            "focusQuickGalleryItem",
            "scrollQuickGalleryItemToFocus",
            "animateGalleryItemToInput",
        ]:
            self.assertRegex(source, rf"\n(?:async\s+)?function {function_name}\(")
            self.assertNotRegex(gallery_source, rf"\n(?:async\s+)?function {function_name}\(")
        self.assertIn("data-quick-gallery-use", source)
        self.assertIn("gallery-fly-clone", source)
        self.assertIn('behavior: prefersReducedMotion() ? "auto" : behavior', source)
        self.assertIn("if (prefersReducedMotion()) return;", source)
        self.assertIn("Object.assign(getLegacyBridge().methods", source)
    def test_gallery_grid_feature_has_typescript_source_contract(self) -> None:
        source = self._gallery_grid_source()
        gallery_source = self._gallery_source()
        main_source = Path("codex_image/webui/frontend/src/main.ts").read_text(encoding="utf-8")

        self.assertNotIn("@ts-nocheck", source)
        self.assertIn('import { initGalleryGridFeature } from "./gallery-grid"', main_source)
        self.assertLess(main_source.index("initGalleryGridFeature()"), main_source.index("initGalleryFeature()"))
        self.assertIn("const GALLERY_GRID_TRANSITION_MS = 220", source)
        for function_name in [
            "renderGalleryGrid",
            "renderGalleryGridWithHeightTransition",
            "shouldAnimateGalleryGridHeight",
            "resetGalleryGridTransition",
            "renderGalleryGridContent",
            "activeGalleryGridItems",
            "activeGalleryGridLayer",
            "galleryGridLayerHtml",
            "galleryGridContentHtml",
            "bindGalleryGridActions",
            "handleGalleryGridClick",
        ]:
            self.assertRegex(source, rf"\n(?:async\s+)?function {function_name}\(")
            self.assertNotRegex(gallery_source, rf"\n(?:async\s+)?function {function_name}\(")
        self.assertIn('els.galleryGrid?.addEventListener("click", handleGalleryGridClick)', source)
        self.assertIn('nextLayer.className = "gallery-grid-layer mode-transition mode-collapsed"', source)
        self.assertIn("Object.assign(getLegacyBridge().methods", source)
    def test_gallery_item_actions_feature_has_typescript_source_contract(self) -> None:
        source = self._gallery_item_actions_source()
        gallery_source = self._gallery_source()
        main_source = Path("codex_image/webui/frontend/src/main.ts").read_text(encoding="utf-8")

        self.assertNotIn("@ts-nocheck", source)
        self.assertIn('import { initGalleryItemActionsFeature } from "./gallery-item-actions"', main_source)
        self.assertLess(main_source.index("initGalleryItemActionsFeature()"), main_source.index("initGalleryFeature()"))
        for function_name in [
            "openAddToGallery",
            "closeAddToGallery",
            "canAddSourceToGallery",
            "galleryImageFileForSource",
            "saveUploadToGallery",
            "renameGalleryItem",
            "moveGalleryItem",
            "editGalleryPromptNote",
            "patchGalleryItem",
            "selectGalleryReplacementFile",
            "replaceGalleryItemImage",
            "deleteGalleryItem",
            "performDeleteGalleryItem",
            "ensureGalleryEditPopover",
            "openGalleryEditPopover",
            "galleryEditFieldHtml",
            "closeGalleryEditPopover",
            "positionGalleryEditPopover",
            "handleGalleryDocumentClick",
        ]:
            self.assertRegex(source, rf"\n(?:async\s+)?function {function_name}\(")
            self.assertNotRegex(gallery_source, rf"\n(?:async\s+)?function {function_name}\(")
        self.assertIn("data-gallery-edit-save", source)
        self.assertIn("data-gallery-edit-cancel", source)
        self.assertIn('fetch(`/api/gallery/${encodeURIComponent(itemId)}/image`', source)
        self.assertIn("Object.assign(getLegacyBridge().methods", source)
    def test_api_settings_feature_has_typescript_source_contract(self) -> None:
        api_settings_source = self._api_settings_source()
        auth_source = Path("codex_image/webui/frontend/src/auth-source.ts").read_text(encoding="utf-8")
        provider_source = Path("codex_image/webui/frontend/src/api-provider-settings.ts").read_text(encoding="utf-8")
        mode_source = Path("codex_image/webui/frontend/src/api-mode-settings.ts").read_text(encoding="utf-8")
        legacy_source = self._bootstrap_source()
        main_source = Path("codex_image/webui/frontend/src/main.ts").read_text(encoding="utf-8")

        for source in [api_settings_source, auth_source, provider_source, mode_source]:
            self.assertNotIn("@ts-nocheck", source)
        self.assertIn('import { initApiSettingsFeature } from "./api-settings"', main_source)
        self.assertLess(main_source.index('import { initGalleryFeature } from "./gallery"'), main_source.index('import { initApiSettingsFeature } from "./api-settings"'))
        self.assertLess(main_source.index('import { initApiSettingsFeature } from "./api-settings"'), main_source.index('import { initPromptFeature } from "./prompt"'))
        self.assertLess(main_source.index("initGalleryFeature()"), main_source.index("initApiSettingsFeature()"))
        self.assertLess(main_source.index("initApiSettingsFeature()"), main_source.index("initPromptFeature()"))
        self.assertIn("export function initApiSettingsFeature", api_settings_source)
        self.assertIn("Object.assign(getLegacyBridge().methods", api_settings_source)
        self.assertIn("export async function refreshHealth()", auth_source)
        self.assertIn("export async function setAuthSource(source", auth_source)
        self.assertIn("export function renderAuthSource(auth", auth_source)
        self.assertIn("export function currentAuthSource()", auth_source)
        self.assertIn("export function updateModeSpecificSettings(authSource", mode_source)
        self.assertIn("export function normalizeApiSettings(settings", provider_source)
        self.assertIn("export function openApiSettingsModal()", provider_source)
        self.assertIn("export function backendForAuthSource(authSource", provider_source)
        self.assertIn("Object.assign(getLegacyBridge().methods", api_settings_source)
        for function_name in [
            "refreshHealth",
            "setAuthSource",
            "renderAuthSource",
            "normalizeApiSettings",
            "openApiSettingsModal",
            "backendForAuthSource",
            "updateModeSpecificSettings",
        ]:
            self.assertNotRegex(api_settings_source, rf"\n(?:async\s+)?function {function_name}\(")
        for function_name in [
            "refreshHealth",
            "normalizeApiSettings",
            "openApiSettingsModal",
            "renderAuthSource",
        ]:
            self._assert_bootstrap_proxy(legacy_source, function_name)

    def test_api_settings_refresh_updates_top_auth_source_summary(self) -> None:
        provider_source = Path("codex_image/webui/frontend/src/api-provider-settings.ts").read_text(encoding="utf-8")
        refresh_body = provider_source[
            provider_source.index("export async function refreshApiSettings"):
            provider_source.index("export function populateApiSettingsForm")
        ]

        self.assertIn("state.apiSettings = mergeApiProviderKeys(data.settings || {})", refresh_body)
        self.assertIn("populateApiSettingsForm();", refresh_body)
        self.assertIn("renderAuthSourceAfterProviderChange();", refresh_body)

    def test_account_quota_feature_is_removed_from_typescript_contract(self) -> None:
        legacy_source = self._bootstrap_source()
        main_source = Path("codex_image/webui/frontend/src/main.ts").read_text(encoding="utf-8")
        event_source = Path("codex_image/webui/frontend/src/event-bindings.ts").read_text(encoding="utf-8")

        self.assertFalse(Path("codex_image/webui/frontend/src/account-quota.ts").exists())
        self.assertNotIn('import { initAccountQuotaFeature } from "./account-quota"', main_source)
        self.assertNotIn("initAccountQuotaFeature()", main_source)
        self.assertNotIn("refreshAccountQuota", legacy_source)
        self.assertNotIn("openAccountQuotaDrawer", legacy_source)
        self.assertNotIn("closeAccountQuotaDrawer", legacy_source)
        self.assertNotIn("accountQuota", event_source)
    def test_storage_settings_feature_has_typescript_source_contract(self) -> None:
        storage_settings_source = self._storage_settings_source()
        legacy_source = self._bootstrap_source()
        main_source = Path("codex_image/webui/frontend/src/main.ts").read_text(encoding="utf-8")

        self.assertIn('import { initStorageSettingsFeature } from "./storage-settings"', main_source)
        self.assertLess(main_source.index('import { initStorageSettingsFeature } from "./storage-settings"'), main_source.index('import { initPromptFeature } from "./prompt"'))
        self.assertLess(main_source.index("initStorageSettingsFeature()"), main_source.index("initPromptFeature()"))
        self.assertIn("export function initStorageSettingsFeature", storage_settings_source)
        self.assertIn("async function refreshSettings()", storage_settings_source)
        self.assertIn("function populateSettingsForm(settings", storage_settings_source)
        self.assertIn("function openSettingsModal()", storage_settings_source)
        self.assertIn("function closeSettingsModal()", storage_settings_source)
        self.assertIn("async function saveSettings()", storage_settings_source)
        self.assertIn("Object.assign(getLegacyBridge().methods", storage_settings_source)
        for function_name in [
            "refreshSettings",
            "populateSettingsForm",
            "openSettingsModal",
            "saveSettings",
        ]:
            self._assert_bootstrap_proxy(legacy_source, function_name)
    def test_form_controls_feature_has_typescript_source_contract(self) -> None:
        form_controls_source = self._form_controls_source()
        size_source = Path("codex_image/webui/frontend/src/size-presets.ts").read_text(encoding="utf-8")
        task_submit_source = Path("codex_image/webui/frontend/src/task-submit.ts").read_text(encoding="utf-8")
        generation_route_source = Path("codex_image/webui/routes/generation.py").read_text(encoding="utf-8")
        main_model_source = Path("codex_image/webui/frontend/src/main-model-combobox.ts").read_text(encoding="utf-8")
        custom_size_source = Path("codex_image/webui/frontend/src/custom-size-controls.ts").read_text(encoding="utf-8")
        output_source = Path("codex_image/webui/frontend/src/output-controls.ts").read_text(encoding="utf-8")
        legacy_source = self._bootstrap_source()
        main_source = Path("codex_image/webui/frontend/src/main.ts").read_text(encoding="utf-8")

        for source in [form_controls_source, size_source, main_model_source, custom_size_source, output_source]:
            self.assertNotIn("@ts-nocheck", source)
        self.assertIn('import { initFormControlsFeature } from "./form-controls"', main_source)
        self.assertLess(main_source.index('import { initPromptFeature } from "./prompt"'), main_source.index('import { initFormControlsFeature } from "./form-controls"'))
        self.assertLess(main_source.index('import { initFormControlsFeature } from "./form-controls"'), main_source.index('import { initTaskListControlsFeature } from "./task-list-controls"'))
        self.assertLess(main_source.index("initPromptFeature()"), main_source.index("initFormControlsFeature()"))
        self.assertLess(main_source.index("initFormControlsFeature()"), main_source.index("initTaskListControlsFeature()"))
        self.assertIn("export function initFormControlsFeature", form_controls_source)
        self.assertIn("function bindFormControlEvents()", form_controls_source)
        self.assertIn("function setMode(mode", form_controls_source)
        self.assertIn("export function updateSizeFromPreset(event", custom_size_source)
        self.assertIn("export function syncSizeControlsFromSize(size", custom_size_source)
        self.assertIn("export function customSizeValidationMessage(width", size_source)
        self.assertIn("export function currentTaskParams()", size_source)
        self.assertIn("const presetMatch = findPresetForSize(params.size)", size_source)
        self.assertIn("params.resolution = presetMatch.resolution", size_source)
        self.assertIn("params.ratio = presetMatch.ratio", size_source)
        self.assertIn("params.orientation = presetMatch.orientation", size_source)
        self.assertIn("const customRatio = currentCustomRatio()", size_source)
        self.assertIn("params.ratio = customRatio", size_source)
        self.assertIn('form.append("resolution", params.resolution)', task_submit_source)
        self.assertIn('form.append("ratio", params.ratio)', task_submit_source)
        self.assertIn('form.append("orientation", params.orientation)', task_submit_source)
        self.assertIn("resolution: str | None = Form(None)", generation_route_source)
        self.assertIn("ratio: str | None = Form(None)", generation_route_source)
        self.assertIn("orientation: str | None = Form(None)", generation_route_source)
        self.assertIn("export function restoreMainModel()", main_model_source)
        self.assertIn("export function updateCompression()", output_source)
        self.assertIn("Object.assign(getLegacyBridge().methods", form_controls_source)
        self.assertIn("updateSizeFromPreset,", form_controls_source)
        for function_name in [
            "updateQuantity",
            "updateCompression",
            "handleOutputFormatDoubleClick",
            "updateSizeFromPreset",
            "syncSizeControlsFromSize",
            "customSizeValidationMessage",
            "updateCustomSize",
            "mainModelOptionsForQuery",
            "restoreMainModel",
            "persistMainModel",
            "currentTaskParams",
            "updateRequestPreview",
        ]:
            self.assertNotRegex(form_controls_source, rf"\nfunction {function_name}\(")
            self.assertNotRegex(legacy_source, rf"\nfunction {function_name}\(")
        self.assertIn('updateSizeFromPreset: proxy("updateSizeFromPreset")', legacy_source)
    def test_overlay_popovers_feature_has_typescript_source_contract(self) -> None:
        overlay_source = self._overlay_popovers_source()
        legacy_source = self._bootstrap_source()
        main_source = Path("codex_image/webui/frontend/src/main.ts").read_text(encoding="utf-8")

        self.assertIn('import { initOverlayPopoversFeature } from "./overlay-popovers"', main_source)
        self.assertLess(main_source.index("initTaskSelectionFeature()"), main_source.index("initOverlayPopoversFeature()"))
        self.assertLess(main_source.index("initOverlayPopoversFeature()"), main_source.index("initShellUiFeature()"))
        self.assertIn("export function initOverlayPopoversFeature", overlay_source)
        self.assertIn("function bindOverlayPopoverEvents()", overlay_source)
        self.assertIn("function openConfirmPopover(anchor, options = {})", overlay_source)
        self.assertIn("function openPromptPopover(anchor, data)", overlay_source)
        self.assertIn("function handleDocumentKeydown(event)", overlay_source)
        self.assertIn("Object.assign(getLegacyBridge().methods", overlay_source)
        for function_name in [
            "ensureConfirmPopover",
            "openConfirmPopover",
            "closeConfirmPopover",
            "positionConfirmPopover",
            "openPromptPopover",
            "positionPromptPopover",
            "clampPopoverPosition",
            "closePromptPopover",
            "copyOptimizedPrompt",
            "handleDocumentClick",
            "handleDocumentKeydown",
        ]:
            if function_name in {"ensureConfirmPopover", "positionConfirmPopover", "clampPopoverPosition", "copyOptimizedPrompt", "handleDocumentClick", "handleDocumentKeydown"}:
                self.assertNotRegex(legacy_source, rf"\n(?:async\s+)?function {function_name}\(")
            else:
                self._assert_bootstrap_proxy(legacy_source, function_name)
    def test_shell_ui_feature_has_typescript_source_contract(self) -> None:
        shell_source = self._shell_ui_source()
        legacy_source = self._bootstrap_source()
        main_source = Path("codex_image/webui/frontend/src/main.ts").read_text(encoding="utf-8")

        self.assertIn('import { initShellUiFeature } from "./shell-ui"', main_source)
        self.assertLess(main_source.index("initOverlayPopoversFeature()"), main_source.index("initShellUiFeature()"))
        self.assertLess(main_source.index("initShellUiFeature()"), main_source.index("initLightboxFeature()"))
        self.assertIn("export function initShellUiFeature", shell_source)
        self.assertIn("function bindShellUiEvents()", shell_source)
        self.assertIn("function restoreThemePreference()", shell_source)
        self.assertIn("function restoreSidebarWidth()", shell_source)
        self.assertNotIn("setupPreviewPanelHeightSync", shell_source)
        self.assertNotIn("syncPreviewPanelHeight", shell_source)
        self.assertNotIn("ResizeObserver", shell_source)
        self.assertIn("function resetForm()", shell_source)
        self.assertIn("function setStatus(message, type)", shell_source)
        self.assertIn("Object.assign(getLegacyBridge().methods", shell_source)
        for function_name in [
            "restoreThemePreference",
            "applyThemePreference",
            "restoreSidebarWidth",
            "startSidebarResize",
            "updateDocumentTitle",
            "setStatus",
            "resetForm",
            "copyJson",
        ]:
            self.assertNotRegex(legacy_source, rf"\n(?:async\s+)?function {function_name}\(")
        self.assertIn('restoreThemePreference: proxy("restoreThemePreference")', legacy_source)
        self.assertNotIn("setupPreviewPanelHeightSync", legacy_source)
    def test_account_quota_drawer_is_removed(self) -> None:
        html = Path("codex_image/webui/static/index.html").read_text(encoding="utf-8")
        script = self._frontend_script_source()
        styles = Path("codex_image/webui/static/styles.css").read_text(encoding="utf-8")
        removed_ids = {
            "button": "account" + "QuotaButton",
            "drawer": "account" + "QuotaDrawer",
            "list": "account" + "QuotaList",
            "close": "account" + "QuotaDrawerClose",
        }

        self.assertNotIn(f'id="{removed_ids["button"]}"', html)
        self.assertNotIn(f'id="{removed_ids["drawer"]}"', html)
        self.assertNotIn(f'id="{removed_ids["list"]}"', html)
        self.assertNotIn(f'id="{removed_ids["close"]}"', html)
        self.assertNotIn("accountQuota", script)
        self.assertNotIn("/api/accounts", script)
        self.assertNotIn("参与轮询", script)
        self.assertNotIn("账号额度", html)
        self.assertNotIn(".account-quota-", styles)
        self.assertRegex(styles, r"\.drawer-close-button\s*\{[^}]*min-width:\s*44px")
        self.assertRegex(styles, r"\.drawer-close-button\s*\{[^}]*align-items:\s*center")
        self.assertRegex(styles, r"\.drawer-close-icon\s*\{[^}]*stroke:\s*currentColor")
    def test_sidebar_brand_uses_ilab_conjure_identity(self) -> None:
        html = Path("codex_image/webui/static/index.html").read_text(encoding="utf-8")
        styles = Path("codex_image/webui/static/styles.css").read_text(encoding="utf-8")

        self.assertIn("<title>iLab GPT CONJURE</title>", html)
        self.assertIn('<link rel="icon" type="image/svg+xml" href="/static/brand/favicon.svg" />', html)
        self.assertNotIn('<link rel="icon" href="data:," />', html)
        self.assertIn('<div class="brand-lockup">', html)
        self.assertIn('class="brand-mark brand-mark-rabbit"', html)
        self.assertIn('class="brand-rabbit-logo"', html)
        self.assertIn('class="brand-rabbit-fill"', html)
        self.assertIn('class="brand-rabbit-cutout"', html)
        self.assertIn('class="brand-rabbit-spark"', html)
        self.assertIn('<div class="brand-name">iLab GPT</div>', html)
        self.assertIn('<div class="brand-subtitle">CONJURE</div>', html)
        self.assertIn('aria-label="iLab GPT CONJURE"', html)
        self.assertNotIn("GPT-image-2 Studio", html)
        favicon_path = Path("codex_image/webui/static/brand/favicon.svg")
        self.assertTrue(favicon_path.exists())
        favicon_source = favicon_path.read_text(encoding="utf-8")
        self.assertIn('viewBox="0 0 128 128"', favicon_source)
        self.assertIn('fill="#457B66"', favicon_source)
        self.assertIn('fill="#FFFFFF"', favicon_source)
        self.assertNotIn("currentColor", favicon_source)
        self.assertNotIn("sodipodi:", Path("codex_image/webui/static/brand/rabbit-logo.svg").read_text(encoding="utf-8"))
        self.assertNotIn("inkscape:", Path("codex_image/webui/static/brand/rabbit-logo.svg").read_text(encoding="utf-8"))

        self.assertRegex(styles, r"\.brand-mark\s*\{[^}]*width:\s*42px")
        self.assertRegex(styles, r"\.brand-mark\s*\{[^}]*height:\s*42px")
        self.assertRegex(styles, r"\.brand-mark\s*\{[^}]*border-radius:\s*15px")
        self.assertRegex(styles, r"\.brand-rabbit-logo\s*\{[^}]*fill:\s*currentColor")
        self.assertRegex(styles, r"\.brand-rabbit-logo\s*\{[^}]*color:\s*#ffffff")
        self.assertRegex(styles, r"\.brand-rabbit-cutout\s*\{[^}]*fill:\s*#457b66")
        self.assertRegex(styles, r"\.brand-rabbit-spark\s*\{[^}]*stroke-width:\s*1\.55")
        self.assertRegex(styles, r"\.brand-name\s*\{[^}]*font-size:\s*17px")
        self.assertRegex(styles, r"\.brand-subtitle\s*\{[^}]*font-weight:\s*700")
        self.assertRegex(styles, r"\.brand-subtitle\s*\{[^}]*letter-spacing:\s*0\.12em")
        self.assertRegex(styles, r"\.brand-subtitle\s*\{[^}]*text-transform:\s*uppercase")
    def test_sidebar_footer_utilities_are_centered(self) -> None:
        html = Path("codex_image/webui/static/index.html").read_text(encoding="utf-8")
        styles = Path("codex_image/webui/static/styles.css").read_text(encoding="utf-8")

        self.assertNotIn('id="settingsButton"', html)
        self.assertNotIn("存储设置</button>", html)
        self.assertRegex(html, r'<div class="task-history-tools">\s*<div id="statusText" class="status-text"')
        self.assertRegex(html, r'<div class="task-history-tools">[\s\S]*id="batchManageButton"')
        self.assertRegex(html, r'<div id="batchToolbar" class="batch-toolbar hidden"')
        self.assertRegex(html, r'<div class="sidebar-footer">\s*<div class="sidebar-api-status-holder"')
        self.assertNotIn('class="footer-actions"', html)
        self.assertNotIn('class="api-status-bar"', html)
        self.assertRegex(styles, r"\.sidebar-footer\s*\{[^}]*align-items:\s*center")
        self.assertRegex(styles, r"\.sidebar-footer\s*\{[^}]*text-align:\s*center")
        self.assertRegex(styles, r"\.task-history-tools\s*\{[^}]*grid-template-columns:\s*minmax\(0,\s*1fr\)\s+auto")
        self.assertRegex(styles, r"\.task-history-batch-button\s*\{[^}]*min-height:\s*30px")
        self.assertRegex(styles, r"\.status-text\s*\{[^}]*width:\s*100%")
        self.assertRegex(styles, r"\.status-text\s*\{[^}]*max-width:\s*100%")
        self.assertRegex(styles, r"\.status-text\s*\{[^}]*overflow-wrap:\s*anywhere")
        self.assertRegex(styles, r"\.status-text\s*\{[^}]*word-break:\s*break-word")
        self.assertRegex(styles, r"\.status-text\s*\{[^}]*display:\s*-webkit-box")
        self.assertRegex(styles, r"\.status-text\s*\{[^}]*-webkit-line-clamp:\s*3")
        self.assertRegex(styles, r"\.status-text\s*\{[^}]*max-height:\s*4\.5em")
        self.assertRegex(styles, r"\.task-history-tools\s+\.status-text\s*\{[^}]*-webkit-line-clamp:\s*1")
        self.assertRegex(styles, r"\.sidebar-api-status-holder\s*\{[^}]*display:\s*none")
        self.assertNotIn(".footer-actions", styles)
        self.assertNotIn(".api-status-bar", styles)
        self.assertRegex(styles, r"\.version-info\s*\{[^}]*text-align:\s*center")
        self.assertRegex(styles, r"\.version-info\s*\{[^}]*font-size:\s*11px")
        self.assertIn('id="versionInfo"', html)
        self.assertIn('id="versionUpdateBadge"', html)
        self.assertIn('id="versionModal"', html)
        self.assertRegex(styles, r"\.version-info\.has-update\s*\{[^}]*color:\s*var\(--primary\)")
        self.assertRegex(styles, r"\.version-update-badge\s*\{[^}]*background:\s*var\(--accent\)")
        self.assertRegex(styles, r"\.version-modal-panel\s*\{[^}]*width:\s*min\(520px,\s*94vw\)")
        self.assertRegex(styles, r"\.version-onboarding\s*\{[^}]*background:\s*var\(--primary-light\)")
        self.assertRegex(styles, r"\.batch-toolbar\s*\{[^}]*align-self:\s*stretch")
        self.assertRegex(styles, r"\.batch-toolbar\s*\{[^}]*gap:\s*7px")
        self.assertRegex(styles, r"\.batch-toolbar\s*\{[^}]*padding:\s*8px\s+10px")

    def test_app_version_status_uses_api_and_updater_action(self) -> None:
        html = Path("codex_image/webui/static/index.html").read_text(encoding="utf-8")
        script = Path("codex_image/webui/static/app.js").read_text(encoding="utf-8")

        self.assertIn('id="versionLabel"', html)
        self.assertIn('data-i18n-attr="aria-label:footer.versionInfo;title:footer.versionInfo"', html)
        self.assertIn('id="versionUpdateButton"', html)
        self.assertIn('id="versionOnboardingNotice"', html)
        self.assertIn('id="versionStandardDownloadLink"', html)
        self.assertIn('id="versionContinuePortableButton"', html)
        self.assertIn('id="versionDismissOnboardingButton"', html)
        self.assertIn("/api/app-version", script)
        self.assertIn("/api/app-version/open-updater", script)
        self.assertIn("/api/app-version/dismiss-onboarding", script)
        self.assertIn("post_update_onboarding", script)
        self.assertIn("footer.version", script)
        self.assertIn("version.updaterStarted", script)
        self.assertIn("version.onboardingStatus", script)
        self.assertIn("version.standardDownload", script)
        self.assertIn("document.addEventListener(LOCALE_CHANGE_EVENT", script)

    def test_workspace_profiles_use_available_container_width(self) -> None:
        base = Path("codex_image/webui/static/styles/01-base.css").read_text(encoding="utf-8")
        layout = Path("codex_image/webui/static/styles/30-layout-top-nav-panels.css").read_text(encoding="utf-8")
        responsive = Path("codex_image/webui/static/styles/80-utilities-responsive.css").read_text(encoding="utf-8")

        main_wrapper = self._extract_css_block(layout, ".main-wrapper")
        dashboard = self._extract_css_block(layout, ".dashboard")
        self.assertIn(
            "container-type: inline-size",
            main_wrapper,
            "the remaining workspace width must drive its own layout profile",
        )
        self.assertIn("container-name: workspace", main_wrapper)
        self.assertIn("min-height: 0", main_wrapper)
        self.assertRegex(
            self._extract_css_block(base, ".layout-container"),
            r"height:\s*100dvh",
        )
        self.assertIn("width: min(100%, 1760px)", dashboard)
        self.assertIn("padding: 24px", dashboard)
        self.assertIn("gap: 24px", dashboard)

        compact = self._extract_last_css_at_rule(responsive, "@container workspace (max-width: 1100px)")
        self.assertRegex(
            compact,
            r"\.dashboard\s*\{[^}]*grid-template-columns:\s*minmax\(0,\s*1\.1fr\)\s+minmax\(320px,\s*0?\.9fr\)",
        )
        stacked = self._extract_css_at_rule(responsive, "@container workspace (max-width: 899px)")
        self.assertRegex(stacked, r"\.dashboard\s*\{[^}]*grid-template-columns:\s*minmax\(0,\s*1fr\)")

    def test_compact_shell_and_workspace_profiles_have_separate_authority(self) -> None:
        responsive = Path("codex_image/webui/static/styles/80-utilities-responsive.css").read_text(encoding="utf-8")

        self.assertNotRegex(
            responsive,
            r"\(min-width:\s*1024px\)",
            "the old desktop width authority must not overlap the compact shell",
        )
        self.assertNotRegex(
            responsive,
            r"@media\s*\(max-width:\s*1024px\)",
            "workspace stacking belongs to the workspace container, not the viewport",
        )
        shell = self._extract_css_at_rule(responsive, "@media (max-width: 1180px)")
        self.assertRegex(shell, r"\.layout-container\s*\{[^}]*flex-direction:\s*column")
        self.assertRegex(shell, r"\.sidebar\s*\{[^}]*width:\s*100%")
        self.assertIn(".sidebar-search", shell)
        self.assertNotRegex(shell, r"\.dashboard\s*\{[^}]*grid-template-columns")
        self.assertNotRegex(shell, r"\.preview-col\s*\{[^}]*height:")
        self.assertIn("@container workspace (max-width: 1100px)", responsive)
        self.assertIn("@container workspace (max-width: 899px)", responsive)

    def test_compact_navigation_scroll_does_not_clip_notification_center(self) -> None:
        responsive = Path("codex_image/webui/static/styles/80-utilities-responsive.css").read_text(encoding="utf-8")

        shell = self._extract_css_at_rule(responsive, "@media (max-width: 1180px)")
        self.assertNotRegex(shell, r"\.top-nav\s*\{[^}]*(?:overflow|overflow-x):\s*auto")
        self.assertRegex(shell, r"\.nav-actions\s*\{[^}]*overflow-x:\s*auto")
        self.assertRegex(shell, r"\.auth-source-detail\s*\{[^}]*display:\s*none")

    def test_responsive_scroll_owners_are_explicit(self) -> None:
        html = Path("codex_image/webui/static/index.html").read_text(encoding="utf-8")
        layout = Path("codex_image/webui/static/styles/30-layout-top-nav-panels.css").read_text(encoding="utf-8")
        output = Path("codex_image/webui/static/styles/70-output-settings.css").read_text(encoding="utf-8")
        prompt = Path("codex_image/webui/static/styles/60-prompt.css").read_text(encoding="utf-8")
        responsive = Path("codex_image/webui/static/styles/80-utilities-responsive.css").read_text(encoding="utf-8")
        shell = Path("codex_image/webui/frontend/src/shell-ui.ts").read_text(encoding="utf-8")

        self.assertNotIn(
            "--controls-col-height",
            shell,
            "CSS grid must be the only preview-height authority",
        )
        self.assertNotIn("setupPreviewPanelHeightSync", shell)
        self.assertNotIn("syncPreviewPanelHeight", shell)
        self.assertNotIn("ResizeObserver", shell)

        dashboard = self._extract_css_block(layout, ".dashboard")
        controls = self._extract_css_block(layout, ".controls-col")
        preview = self._extract_css_block(layout, ".preview-col")
        self.assertIn("min-height: 0", dashboard)
        self.assertIn("overflow-y: auto", dashboard)
        self.assertNotIn("grid-template-rows", dashboard)
        self.assertNotIn("overflow-y", controls)
        self.assertNotIn("height: 100%", controls)
        self.assertRegex(preview, r"height:\s*auto")
        self.assertRegex(preview, r"overflow:\s*hidden")

        stacked = self._extract_css_at_rule(responsive, "@container workspace (max-width: 899px)")
        self.assertRegex(stacked, r"\.dashboard\s*\{[^}]*grid-template-columns:\s*minmax\(0,\s*1fr\)[^}]*align-content:\s*start")
        self.assertRegex(
            stacked,
            r"\.controls-col\s*\{[^}]*max-width:\s*none[^}]*height:\s*auto[^}]*min-height:\s*auto[^}]*overflow:\s*visible",
        )
        self.assertRegex(stacked, r"\.preview-col\s*\{[^}]*height:\s*auto[^}]*min-height:\s*260px[^}]*overflow:\s*visible")
        self.assertRegex(stacked, r"\.preview-panel\s*\{[^}]*min-height:\s*260px")

        for title in ("参考输入（可选）", "提示词", "输出设置"):
            self.assertIn(title, html)
        self.assertIn("justify-content: space-between", self._extract_css_block(layout, ".panel-heading"))
        self.assertIn("justify-content: space-between", self._extract_css_block(prompt, ".prompt-heading-main"))
        self.assertIn("position: relative", self._extract_css_block(output, ".output-settings-header"))
        self.assertNotIn("@media (max-height: 860px)", responsive)
        self.assertNotRegex(
            responsive,
            r"\.controls-col\s+\.output-settings-header\s+h2\s*\{[^}]*position:\s*absolute[^}]*width:\s*1px",
        )

    def test_short_desktop_layout_compacts_sidebar_footer_and_workbench(self) -> None:
        responsive = Path(
            "codex_image/webui/static/styles/80-utilities-responsive.css"
        ).read_text(encoding="utf-8")
        compact = self._extract_css_at_rule(
            responsive,
            "@media (max-height: 1390px) and (min-width: 900px)",
        )

        self.assertRegex(compact, r"\.sidebar-footer\s*\{[^}]*padding:\s*8px\s+12px")
        self.assertRegex(compact, r"\.version-info\s*\{[^}]*display:\s*inline-flex")
        self.assertRegex(
            compact,
            r"\.dashboard\s*\{[^}]*--compact-dashboard-padding:\s*clamp\("
            r"[^}]*padding:\s*var\(--compact-dashboard-padding\)",
        )
        self.assertRegex(
            compact,
            r"\.preview-col\s*\{[^}]*height:\s*calc\("
            r"[\s\S]*var\(--compact-dashboard-padding\)",
        )
        self.assertRegex(
            compact,
            r"\.controls-col\s*\{[^}]*--compact-image-panel-height:\s*clamp\("
            r"[\s\S]*--compact-prompt-panel-height:\s*clamp\("
            r"[\s\S]*justify-content:\s*flex-start",
        )
        self.assertRegex(
            compact,
            r"\.controls-col\s+\.image-panel\s*\{[^}]*"
            r"flex:\s*1\s+1\s+var\(--compact-image-panel-height\)",
        )
        self.assertRegex(
            compact,
            r"\.controls-col\s+\.prompt-panel\s*\{[^}]*"
            r"flex:\s*1\.15\s+1\s+var\(--compact-prompt-panel-height\)",
        )
        self.assertRegex(
            compact,
            r"\.controls-col\s+\.output-panel\s*\{[^}]*flex:\s*0\s+0\s+auto",
        )
        self.assertRegex(compact, r"\.panel\s*\{[^}]*padding:\s*clamp\(")
        self.assertNotIn("align-content: space-between", compact)
        self.assertNotIn("@media (max-height: 860px)", responsive)
        self.assertNotRegex(
            responsive,
            r"\.controls-col\s+\.panel-heading\s+h2,[\s\S]*"
            r"\.controls-col\s+\.output-settings-header\s+h2\s*\{[^}]*clip:",
        )
        self.assertIn(
            ".controls-col .image-input-workspace {\n    flex: 1 1 auto;",
            compact,
        )
        self.assertIn(
            ".controls-col .prompt-compose {\n    flex: 1 1 0;\n    min-height: 0;",
            compact,
        )
    def test_sidebar_width_can_be_resized_and_persisted(self) -> None:
        html = Path("codex_image/webui/static/index.html").read_text(encoding="utf-8")
        styles = Path("codex_image/webui/static/styles.css").read_text(encoding="utf-8")
        script = self._frontend_script_source()

        self.assertIn('<aside id="sidebar" class="sidebar">', html)
        self.assertIn('id="sidebarResizeHandle"', html)
        self.assertIn('id="sidebarResizeShield"', html)
        self.assertIn('class="sidebar-resize-shield"', html)
        self.assertIn('role="separator"', html)
        self.assertIn('aria-label="调整侧栏宽度"', html)
        self.assertIn("sidebar: document.querySelector(\"#sidebar\")", script)
        self.assertIn("sidebarResizeHandle: document.querySelector(\"#sidebarResizeHandle\")", script)
        self.assertIn("sidebarResizeShield: document.querySelector(\"#sidebarResizeShield\")", script)
        self.assertIn("SIDEBAR_WIDTH_STORAGE_KEY", script)
        self.assertIn("restoreSidebarWidth", script)
        self.assertIn("function sidebarWidthFromCss()", script)
        self.assertIn("function currentSidebarWidth()", script)
        self.assertIn("startSidebarResize", script)
        self.assertIn("scheduleSidebarResizeWidth", script)
        self.assertIn("flushSidebarResizeWidth", script)
        self.assertIn("window.requestAnimationFrame(() =>", script)
        self.assertIn("applySidebarWidth(nextWidth, { persist: false });", script)
        self.assertIn("const currentWidth = currentSidebarWidth();", script)
        self.assertIn('(els.sidebar || document.documentElement).style.setProperty("--sidebar-width"', script)
        self.assertNotIn('document.documentElement.style.setProperty("--sidebar-width"', script)
        self.assertIn("const widthOwner = els.sidebar || document.documentElement;", script)
        self.assertIn("els.sidebarResizeShield.hidden = false;", script)
        self.assertIn("els.sidebarResizeShield.hidden = true;", script)
        self.assertNotIn('document.body.classList.add("sidebar-resizing")', script)
        self.assertNotIn('document.body.classList.remove("sidebar-resizing")', script)
        self.assertNotIn("getBoundingClientRect", self._shell_ui_source())
        self.assertNotIn("ResizeObserver", self._shell_ui_source())
        self.assertNotIn("--controls-col-height", self._shell_ui_source())
        self.assertLess(
            script.index("state.sidebarResize = null;", script.index("function finishSidebarResize")),
            script.index("flushSidebarResizeWidth(nextWidth);", script.index("function finishSidebarResize")),
        )
        self.assertIn("localStorage.setItem(SIDEBAR_WIDTH_STORAGE_KEY", script)
        self.assertRegex(styles, r":root\s*\{[^}]*--sidebar-min-width:\s*280px")
        self.assertRegex(styles, r":root\s*\{[^}]*--sidebar-max-width:\s*520px")
        self.assertRegex(styles, r"\.sidebar\s*\{[^}]*position:\s*relative")
        self.assertRegex(styles, r"\.sidebar-resize-handle\s*\{[^}]*cursor:\s*col-resize")
        self.assertRegex(styles, r"\.sidebar-resize-shield\s*\{[^}]*position:\s*fixed")
        self.assertRegex(styles, r"\.sidebar-resize-shield\s*\{[^}]*cursor:\s*col-resize")
    def test_webui_brand_name_is_consistent_across_launch_surfaces(self) -> None:
        app_source = Path("codex_image/webui/app.py").read_text(encoding="utf-8")
        launcher_sources = [
            Path("Start WebUI.command").read_text(encoding="utf-8"),
            Path("Start WebUI Debug.command").read_text(encoding="utf-8"),
            Path("Start WebUI.bat").read_text(encoding="utf-8"),
        ]

        self.assertIn('FastAPI(title="iLab GPT CONJURE"', app_source)
        self.assertIn("<title>iLab GPT CONJURE</title><h1>iLab GPT CONJURE</h1>", app_source)
        self.assertNotIn("GPT-image-2 Studio", app_source)
        for source in launcher_sources:
            self.assertIn("iLab GPT CONJURE", source)
            self.assertNotIn("GPT-image-2 Studio", source)
    def test_output_size_controls_match_gpt_image_2_ratios(self) -> None:
        html = Path("codex_image/webui/static/index.html").read_text(encoding="utf-8")
        script = self._frontend_script_source()

        expected_ratios = ("1:1", "4:5", "5:4", "3:4", "4:3", "2:3", "3:2", "9:16", "16:9", "9:21", "21:9")
        for value in expected_ratios:
            self.assertIn(f'data-val="{value}"', html)
            self.assertIn(f'<option value="{value}"', html)

        ratio_controls = re.search(r'id="ratioGroup"[\s\S]*?<select id="ratio" class="hidden">[\s\S]*?</select>', html)
        self.assertIsNotNone(ratio_controls)
        self.assertIn('id="orientation"', html)
        self.assertNotIn('data-val="auto"', ratio_controls.group(0))
        self.assertNotIn('<option value="auto"', ratio_controls.group(0))
        ratio_markup = ratio_controls.group(0)
        last_index = -1
        for value in expected_ratios:
            index = ratio_markup.index(f'data-val="{value}"')
            self.assertGreater(index, last_index)
            last_index = index
        self.assertIn('"4:5": [1024, 1280]', script)
        self.assertIn('"5:4": [1280, 1024]', script)
        self.assertIn('"4:5": [1600, 2000]', script)
        self.assertIn('"5:4": [2000, 1600]', script)
        self.assertIn('"4:5": [2560, 3200]', script)
        self.assertIn('"5:4": [3200, 2560]', script)
        self.assertIn('"21:9": [1568, 672]', script)
        self.assertIn('"9:21": [672, 1568]', script)
        self.assertIn("RATIO_COUNTERPARTS", script)
    def test_image_input_source_selector_and_hints_are_removed(self) -> None:
        html = Path("codex_image/webui/static/index.html").read_text(encoding="utf-8")
        script = self._frontend_script_source()

        self.assertNotIn("来源选择", html)
        self.assertNotIn("最多支持 16 张图片", html)
        self.assertNotIn("最多支持多张参考图；编辑模式至少需要 1 张图片。", script)
    def test_mask_input_is_removed_from_webui(self) -> None:
        html = Path("codex_image/webui/static/index.html").read_text(encoding="utf-8")
        script = self._frontend_script_source()

        self.assertNotIn("maskBlock", html)
        self.assertNotIn("maskInput", html)
        self.assertNotIn("maskName", html)
        self.assertNotIn(">Mask<", html)
        self.assertNotIn("maskBlock", script)
        self.assertNotIn("maskInput", script)
        self.assertNotIn("maskName", script)
        self.assertNotIn("setMask", script)
        self.assertNotIn('form.append("mask"', script)
    def test_image_input_uses_quick_gallery_dock(self) -> None:
        html = Path("codex_image/webui/static/index.html").read_text(encoding="utf-8")
        script = self._frontend_script_source()
        styles = Path("codex_image/webui/static/styles.css").read_text(encoding="utf-8")

        self.assertIn('class="image-input-workspace"', html)
        self.assertIn('class="image-input-left"', html)
        self.assertIn('class="image-input-footer"', html)
        self.assertIn('class="image-input-actions"', html)
        self.assertIn('class="image-gallery-column"', html)
        self.assertIn('id="imageThumbList"', html)
        image_thumb_list = html[html.index('id="imageThumbList"'):html.index('id="imageUploadSource"')]
        self.assertLess(image_thumb_list.index('id="imageThumbItems"'), image_thumb_list.index('id="referenceFileSelection"'))
        self.assertIn('id="imageUploadSource"', html)
        self.assertIn('id="quickGalleryDock"', html)
        self.assertIn('id="quickGalleryPreview"', html)
        self.assertIn('id="quickGalleryList"', html)
        self.assertIn('id="quickGalleryRail"', html)
        self.assertIn('id="galleryManagePanel"', html)
        self.assertIn('id="galleryManageButton"', html)
        self.assertNotIn('id="galleryManageSummary"', html)
        self.assertNotIn("查看全部", html)
        self.assertIn('class="ghost-button text-sm icon-text-button resource-manage-button gallery-manage-button"', html)
        self.assertRegex(html, r'id="galleryManageButton"[\s\S]*<svg class="button-icon"[\s\S]*<span[^>]*>管理公用库</span>')
        self.assertIn('data-quick-gallery-category="portrait"', html)
        self.assertIn('data-quick-gallery-category="character"', html)
        self.assertIn('data-quick-gallery-category="product"', html)
        self.assertNotIn('id="imageSourceTabs"', html)
        self.assertNotIn('id="inlineGalleryPicker"', html)
        self.assertNotIn('id="inlineGalleryGrid"', html)
        self.assertNotIn('id="gallerySearch"', html)
        self.assertNotIn('id="galleryButtons"', html)
        self.assertNotIn("gallery-picker-row", html)
        self.assertRegex(html, r'<div class="panel-heading">\s*<h2[^>]*>参考输入（可选）</h2>\s*</div>')
        self.assertRegex(html, r'<div class="image-input-footer">[\s\S]*<div class="image-input-actions">[\s\S]*<button id="clearImagesButton"')
        self.assertRegex(html, r'<div class="image-input-footer">[\s\S]*id="recentAssetDock"[\s\S]*id="recentAssetList"')
        self.assertRegex(html, r'<div class="image-gallery-column">[\s\S]*id="quickGalleryDock"[\s\S]*id="galleryManagePanel"')
        self.assertNotRegex(html, r'<div class="image-gallery-column">[\s\S]*id="recentAssetDock"')
        self.assertIn('id="addToGalleryModal"', html)
        self.assertIn("imageUploadSource: document.querySelector(\"#imageUploadSource\")", script)
        self.assertIn("imageThumbList: document.querySelector(\"#imageThumbList\")", script)
        self.assertIn("imageThumbItems: document.querySelector(\"#imageThumbItems\")", script)
        self.assertIn("imageUploaderGrid: document.querySelector(\".image-uploader-grid\")", script)
        self.assertIn("quickGalleryDock: document.querySelector(\"#quickGalleryDock\")", script)
        self.assertIn("quickGalleryPreview: document.querySelector(\"#quickGalleryPreview\")", script)
        self.assertIn("quickGalleryList: document.querySelector(\"#quickGalleryList\")", script)
        self.assertIn("quickGalleryRail: document.querySelector(\"#quickGalleryRail\")", script)
        self.assertIn("galleryManagePanel: document.querySelector(\"#galleryManagePanel\")", script)
        self.assertIn("galleryManageButton: document.querySelector(\"#galleryManageButton\")", script)
        self.assertIn("renderQuickGalleryDock", script)
        self.assertIn("sortGalleryItems", script)
        self.assertIn('localeCompare(rightName, "zh-CN", { numeric: true, sensitivity: "base" })', script)
        self.assertRegex(script, r"function filterGalleryItems\(category = state\.activeGalleryCategory\)\s*\{[\s\S]*sortGalleryItems")
        self.assertNotIn("galleryManageSummary", script)
        self.assertNotIn("renderGalleryManagePanel", script)
        self.assertIn("setQuickGalleryCategory", script)
        self.assertIn("previewQuickGalleryItem", script)
        self.assertIn("hideQuickGalleryPreview", script)
        self.assertIn("scheduleQuickGalleryFocusUpdate", script)
        self.assertIn("updateQuickGalleryFocus", script)
        self.assertIn('quickGalleryList?.addEventListener("scroll", () => call(methods, "scheduleQuickGalleryFocusUpdate"))', script)
        self.assertIn("handleQuickGalleryBoundaryWheel", script)
        self.assertIn("triggerQuickGalleryBounce", script)
        self.assertIn("QUICK_GALLERY_WHEEL_COOLDOWN_MS", script)
        self.assertIn("const QUICK_GALLERY_WHEEL_COOLDOWN_MS = 220;", script)
        self.assertIn('import { prefersReducedMotion } from "./webui-utils";', script)
        self.assertIn("quickGalleryFocusItemId", script)
        self.assertIn("ensureQuickGalleryFocusItem(items)", script)
        self.assertIn("scrollQuickGalleryItemToFocus", script)
        self.assertIn("focusQuickGalleryItem", script)
        self.assertNotIn("scrollQuickGalleryItemToCenter", script)
        self.assertNotIn("centerQuickGalleryItem", script)
        self.assertIn('button.addEventListener("mouseenter", () => previewQuickGalleryItem(button.dataset.quickGalleryUse));', script)
        self.assertIn("focusQuickGalleryItem(button.dataset.quickGalleryUse)", script)
        self.assertNotRegex(
            script,
            r"function previewQuickGalleryItem\(itemId\)\s*\{[\s\S]*focusQuickGalleryItem\(itemId\)[\s\S]*function hideQuickGalleryPreview",
        )
        self.assertIn("const hoveredButton = state.hoveredGalleryItemId", script)
        self.assertIn("const focusButton = hoveredButton || focusedButton || buttons[0];", script)
        self.assertIn("Math.abs(buttons.indexOf(button) - focusIndex)", script)
        self.assertIn("quickGalleryWheelLockTimerId", script)
        self.assertIn('quickGalleryList?.addEventListener("wheel", (event) => call(methods, "handleQuickGalleryBoundaryWheel", event)', script)
        self.assertIn('classList.add("visible")', script)
        self.assertIn('classList.remove("visible")', script)
        self.assertIn("animateGalleryItemToInput", script)
        self.assertIn('behavior: prefersReducedMotion() ? "auto" : behavior', script)
        self.assertIn("if (prefersReducedMotion()) return;", script)
        self.assertIn("filterGalleryItems", script)
        self.assertIn("data-quick-gallery-use", script)
        self.assertIn("addGalleryInput(item)", script)
        self.assertIn("function handleGalleryManageButtonClick()", script)
        self.assertIn('els.galleryManageButton?.addEventListener("click", handleGalleryManageButtonClick)', script)
        self.assertNotIn("imageSourceTabs: document.querySelector", script)
        self.assertNotIn("inlineGalleryPicker: document.querySelector", script)
        self.assertNotIn("setImageSource", script)
        self.assertNotIn("state.gallerySearchQuery", script)
        self.assertNotIn("previewQuickGalleryItem(previewItem?.id || null)", script)
        self.assertIn("add-upload-to-gallery", script)
        self.assertIn("/api/gallery", script)
        self.assertRegex(styles, r"\.image-panel\s*\{[^}]*container-type:\s*inline-size")
        self.assertRegex(styles, r"\.image-input-left\s*\{[^}]*container-type:\s*inline-size")
        self.assertRegex(styles, r"\.image-input-workspace\s*\{[^}]*position:\s*relative")
        self.assertRegex(styles, r":root\s*\{[^}]*--workspace-side-action-width:\s*164px")
        self.assertRegex(styles, r"\.image-input-workspace\s*\{[^}]*--quick-gallery-column-width:\s*var\(--workspace-side-action-width\)")
        self.assertRegex(styles, r"\.image-input-workspace\s*\{[^}]*grid-template-columns:\s*minmax\(0,\s*1fr\)\s+var\(--quick-gallery-column-width\)")
        self.assertRegex(styles, r"\.image-input-workspace\s*\{[^}]*--image-input-action-height:\s*40px")
        self.assertRegex(styles, r"\.image-input-workspace\s*\{[^}]*--image-input-thumb-size:\s*116px")
        self.assertRegex(styles, r"\.image-input-workspace\s*\{[^}]*--quick-gallery-height:\s*var\(--image-input-main-height\)")
        self.assertRegex(styles, r"@container\s+workspace\s*\(max-width:\s*520px\)\s*\{[\s\S]*\.image-input-workspace[\s\S]*grid-template-columns:\s*minmax\(0,\s*1fr\)")
        self.assertNotIn("@container (max-width: 620px)", styles)
        self.assertRegex(styles, r"\.image-input-main\s*\{[^}]*border:\s*1px dashed color-mix\(in srgb, var\(--text-secondary\) 36%, var\(--line\)\)")
        self.assertRegex(styles, r"\.image-input-main\s*\{[^}]*height:\s*var\(--image-input-main-height\)")
        self.assertRegex(styles, r"\.image-input-left\s*\{[^}]*display:\s*flex")
        self.assertRegex(styles, r"\.image-input-left\s*\{[^}]*flex-direction:\s*column")
        self.assertRegex(styles, r"\.image-input-left\s*\{[^}]*height:\s*var\(--image-input-total-height\)")
        self.assertRegex(styles, r"\.image-input-footer\s*\{[^}]*grid-template-columns:\s*auto minmax\(0,\s*1fr\)")
        self.assertRegex(styles, r"\.image-input-footer\s*\{[^}]*height:\s*var\(--image-input-action-height\)")
        self.assertRegex(styles, r"\.image-input-actions\s*\{[^}]*justify-content:\s*flex-start")
        self.assertRegex(styles, r"\.image-input-actions\s*\{[^}]*height:\s*var\(--image-input-action-height\)")
        self.assertRegex(styles, r"\.image-input-actions\s*\{[^}]*flex-wrap:\s*nowrap")
        self.assertRegex(styles, r"\.image-input-actions\s+\.ghost-button\s*,\s*\.gallery-manage-panel\s+\.resource-manage-button\s*\{[^}]*height:\s*var\(--image-input-action-height\)")
        self.assertRegex(styles, r"\.image-gallery-column\s*\{[^}]*display:\s*grid")
        self.assertRegex(styles, r"\.image-gallery-column\s*\{[^}]*grid-template-rows:\s*var\(--quick-gallery-height\)\s+var\(--image-input-action-height\)")
        self.assertRegex(styles, r"\.image-uploader-grid\s*\{[^}]*width:\s*100%")
        self.assertRegex(styles, r"\.image-uploader-grid\s*\{[^}]*height:\s*100%")
        self.assertRegex(styles, r"\.image-uploader-grid\s*\{[^}]*overflow:\s*hidden")
        self.assertRegex(styles, r"\.image-strip\s*\{[^}]*display:\s*grid")
        self.assertRegex(styles, r"\.image-strip\s*\{[^}]*grid-template-columns:\s*minmax\(0,\s*1fr\)")
        self.assertRegex(styles, r"\.image-uploader-grid\.has-inputs\s+\.image-strip\s*\{[^}]*grid-template-columns:\s*minmax\(0,\s*1fr\)\s+var\(--image-upload-source-compact-width\)")
        self.assertRegex(styles, r"\.image-thumb-list\s*\{[^}]*display:\s*none")
        self.assertRegex(styles, r"\.image-uploader-grid\.has-inputs\s+\.image-thumb-list\s*\{[^}]*display:\s*flex")
        self.assertRegex(styles, r"\.image-thumb-list\s*\{[^}]*overflow-x:\s*auto")
        self.assertRegex(styles, r"\.image-upload-source\s*\{[^}]*height:\s*100%")
        self.assertRegex(styles, r"\.thumb\s*\{[^}]*width:\s*var\(--image-input-thumb-size\)")
        self.assertRegex(styles, r"\.thumb\s*\{[^}]*height:\s*var\(--image-input-thumb-size\)")
        self.assertNotRegex(styles, r"\.image-upload-source\s*\{[^}]*flex:\s*1 0 220px")
        self.assertRegex(styles, r"\.image-uploader-grid\.compact-grid\s+\.image-strip\s*\{[^}]*grid-template-rows:\s*var\(--image-input-compact-thumb-size\)")
        self.assertNotRegex(styles, r"\.image-uploader-grid\.compact-grid\s+\.image-strip\s*\{[^}]*grid-template-rows:\s*repeat\(2,")
        self.assertRegex(styles, r"\.image-uploader-grid\.compact-grid\s+\.image-strip\s*\{[^}]*grid-template-columns:\s*minmax\(0,\s*1fr\)\s+var\(--image-input-compact-thumb-size\)")
        self.assertRegex(styles, r"\.image-uploader-grid\.compact-grid\s+\.image-strip\s*\{[^}]*gap:\s*6px")
        self.assertRegex(styles, r"\.image-uploader-grid\.compact-grid\s+\.image-strip\s*\{[^}]*overflow:\s*hidden")
        self.assertNotRegex(styles, r"\.image-uploader-grid\.compact-grid\s+\.image-strip\s*\{[^}]*overflow-x:\s*auto")
        self.assertRegex(styles, r"\.image-uploader-grid\.compact-grid\s*\{[^}]*padding:\s*8px")
        self.assertRegex(styles, r"\.image-uploader-grid\.compact-grid\s+\.image-thumb-list\s*\{[^}]*display:\s*flex")
        self.assertRegex(styles, r"\.image-uploader-grid\.compact-grid\s+\.thumb\s*,\s*\.image-uploader-grid\.compact-grid\s+\.image-upload-source\s*\{[^}]*width:\s*var\(--image-input-compact-thumb-size\)")
        self.assertRegex(styles, r"\.image-uploader-grid\.compact-grid\s+\.thumb-badge\s*\{[^}]*display:\s*none")
        self.assertRegex(styles, r"\.image-uploader-grid\.compact-grid\s+\.thumb\s+\.thumb-remove\s*\{[^}]*width:\s*16px")
        self.assertRegex(styles, r"\.image-uploader-grid\.compact-grid\s+\.add-upload-to-gallery\s*\{[^}]*width:\s*20px")
        self.assertRegex(styles, r"\.image-uploader-grid\.compact-grid\s+\.add-upload-to-gallery\s+\.thumb-add-icon\s*\{[^}]*width:\s*12px")
        self.assertNotIn("@container (max-width: 540px)", styles)
        self.assertRegex(styles, r"\.upload-title-compact\s*\{[^}]*display:\s*none")
        self.assertRegex(styles, r"\.image-uploader-grid\.has-inputs\s+\.upload-title-full\s*\{[^}]*display:\s*none")
        self.assertRegex(styles, r"\.image-uploader-grid\.has-inputs\s+\.upload-title-compact\s*\{[^}]*display:\s*inline")
        self.assertIn("const compactGrid = imageStripNeedsCompactGrid();", script)
        self.assertIn("const thumbCount = state.images.length + state.referenceFiles.length;", script)
        self.assertIn("const thumbItems = els.imageThumbItems;", script)
        self.assertNotIn("els.imageThumbItems || els.imageThumbList", script)
        self.assertNotIn('els.imageThumbList.innerHTML = ""', script)
        self.assertIn("function handleImageStripWheel", script)
        self.assertIn('els.imageStrip?.addEventListener("wheel", handleImageStripWheel, { passive: false })', script)
        self.assertIn("const nextScrollLeft = Math.min(maxScrollLeft, Math.max(0, scrollTarget.scrollLeft + wheelDelta));", script)
        self.assertIn("event.preventDefault();", script)
        self.assertNotIn("state.images.length >= 4 || imageStripNeedsCompactGrid()", script)
        self.assertRegex(script, r"els\.imageUploaderGrid\?\.classList\.toggle\(\"has-images\",\s*hasImages\)")
        self.assertRegex(script, r"els\.imageUploaderGrid\?\.classList\.toggle\(\"has-inputs\",\s*hasInputs\)")
        self.assertRegex(script, r"els\.imageUploaderGrid\?\.classList\.toggle\(\"compact-grid\",\s*compactGrid\)")
        self.assertRegex(styles, r"\.upload-tile\s*\{[^}]*height:\s*100%")
        self.assertRegex(styles, r"\.upload-tile\s*\{[^}]*border:\s*none")
        self.assertRegex(styles, r"\.quick-gallery-dock\s*\{[^}]*position:\s*relative")
        self.assertRegex(styles, r"\.quick-gallery-dock\s*\{[^}]*height:\s*var\(--quick-gallery-height\)")
        self.assertRegex(styles, r"\.quick-gallery-picker\s*\{[^}]*grid-template-columns:\s*minmax\(0,\s*1fr\)\s+52px")
        self.assertRegex(styles, r"\.quick-gallery-rail\s*\{[^}]*height:\s*var\(--quick-gallery-height\)")
        self.assertRegex(styles, r"\.quick-gallery-rail\s*\{[^}]*display:\s*flex")
        self.assertRegex(styles, r"\.quick-gallery-rail\s*\{[^}]*flex-direction:\s*column")
        self.assertRegex(styles, r"\.quick-gallery-rail\s*\{[^}]*overflow-y:\s*auto")
        self.assertRegex(styles, r"\.quick-gallery-rail\s*\{[^}]*scroll-snap-type:\s*y proximity")
        self.assertRegex(styles, r"\.quick-gallery-rail\s*\{[^}]*scrollbar-width:\s*none")
        self.assertRegex(styles, r"\.quick-gallery-rail::\-webkit-scrollbar\s*\{[^}]*display:\s*none")
        self.assertNotRegex(styles, r"\.quick-gallery-rail\s*\{[^}]*grid-template-rows:\s*repeat\(3,\s*1fr\)")
        self.assertRegex(styles, r"\.quick-gallery-category\s*\{[^}]*flex:\s*0 0 30px")
        self.assertRegex(styles, r"\.quick-gallery-category\s*\{[^}]*height:\s*30px")
        self.assertRegex(styles, r"\.quick-gallery-category\s*\{[^}]*overflow:\s*hidden")
        self.assertRegex(styles, r"\.quick-gallery-category\s*\{[^}]*text-overflow:\s*ellipsis")
        self.assertRegex(styles, r"\.quick-gallery-category\s*\{[^}]*white-space:\s*nowrap")
        self.assertRegex(styles, r"\.quick-gallery-category\s*\{[^}]*scroll-snap-align:\s*start")
        self.assertRegex(styles, r"\.quick-gallery-preview\s*\{[^}]*position:\s*absolute")
        self.assertRegex(styles, r"\.quick-gallery-preview\s*\{[^}]*top:\s*50%")
        self.assertRegex(styles, r"\.quick-gallery-preview\s*\{[^}]*pointer-events:\s*none")
        self.assertRegex(styles, r"\.quick-gallery-preview\s*\{[^}]*opacity:\s*0")
        self.assertRegex(styles, r"\.quick-gallery-preview\.visible\s*\{[^}]*opacity:\s*1")
        self.assertRegex(styles, r"\.quick-gallery-list\s*\{[^}]*overflow-y:\s*auto")
        self.assertRegex(styles, r"\.quick-gallery-list\s*\{[^}]*--quick-gallery-item-height:\s*30px")
        self.assertNotIn("--quick-gallery-center-pad", styles)
        self.assertRegex(styles, r"\.quick-gallery-list\s*\{[^}]*padding:\s*0\s+4px\s+0\s+0")
        self.assertRegex(styles, r"\.quick-gallery-list\s*\{[^}]*scroll-snap-type:\s*y proximity")
        self.assertNotRegex(styles, r"\.quick-gallery-list\s*\{[^}]*scroll-padding-block:")
        self.assertRegex(styles, r"\.quick-gallery-list\s*\{[^}]*scrollbar-width:\s*none")
        self.assertRegex(styles, r"\.quick-gallery-list::\-webkit-scrollbar\s*\{[^}]*display:\s*none")
        self.assertRegex(styles, r"\.quick-gallery-item\s*\{[^}]*text-align:\s*center")
        self.assertRegex(styles, r"\.quick-gallery-item\s*\{[^}]*cursor:\s*pointer")
        self.assertRegex(styles, r"\.quick-gallery-item\s*\{[^}]*scroll-snap-align:\s*start")
        self.assertRegex(styles, r"\.quick-gallery-item\.near\s*\{[^}]*opacity:")
        self.assertRegex(styles, r"\.quick-gallery-item\.center\s*\{[^}]*box-shadow:")
        self.assertRegex(styles, r"\.quick-gallery-item\.center\.active\s*\{[^}]*box-shadow:")
        self.assertRegex(styles, r"\.quick-gallery-list\.bounce-top\s*\{[^}]*animation:\s*quickGalleryBounceTop")
        self.assertRegex(styles, r"\.quick-gallery-list\.bounce-bottom\s*\{[^}]*animation:\s*quickGalleryBounceBottom")
        self.assertIn("@keyframes quickGalleryBounceTop", styles)
        self.assertIn("@keyframes quickGalleryBounceBottom", styles)
        self.assertIn("@media (prefers-reduced-motion: reduce)", styles)
        self.assertRegex(styles, r"\.gallery-fly-clone\s*\{[^}]*position:\s*fixed")
        self.assertRegex(styles, r"\.gallery-manage-panel\s*\{[^}]*display:\s*flex")
        self.assertRegex(styles, r"\.gallery-manage-panel\s*\{[^}]*width:\s*100%")
        self.assertRegex(styles, r"\.gallery-manage-panel\s*\{[^}]*justify-content:\s*flex-end")
        self.assertNotRegex(styles, r"\.gallery-manage-panel\s*\{[^}]*border:")
        self.assertRegex(styles, r"\.gallery-manage-panel\s+\.resource-manage-button\s*\{[^}]*flex:\s*1 1 auto")
        resource_button_styles = self._extract_css_block(styles, ".resource-manage-button")
        self.assertIn("width: 100%", resource_button_styles)
        self.assertIn("background: var(--primary)", resource_button_styles)
        self.assertIn("border-color: var(--primary)", resource_button_styles)
        self.assertIn("color: var(--primary-foreground)", resource_button_styles)
        self.assertNotIn("thumb-label", script)
        self.assertNotIn(".thumb-label", styles)
    def test_short_desktop_layout_reduces_input_prompt_and_output_settings_height(self) -> None:
        responsive = Path(
            "codex_image/webui/static/styles/80-utilities-responsive.css"
        ).read_text(encoding="utf-8")
        compact = self._extract_css_at_rule(
            responsive,
            "@media (max-height: 1390px) and (min-width: 900px)",
        )
        narrow_height_marker = "@media (max-height: 1100px) and (min-width: 900px)"
        narrow_marker = "@container workspace (max-width: 1180px)"
        top_level = compact
        narrow_height = self._extract_css_at_rule(responsive, narrow_height_marker)
        narrow = self._extract_css_at_rule(narrow_height, narrow_marker)

        self.assertRegex(
            compact,
            r"\.image-input-workspace\s*\{[^}]*--image-input-main-height:\s*clamp\("
            r"[\s\S]*60px,[\s\S]*150px",
        )
        self.assertRegex(
            compact,
            r"\.image-input-workspace\s*\{[^}]*--image-input-action-height:\s*clamp\("
            r"[\s\S]*28px,[\s\S]*40px",
        )
        self.assertRegex(
            compact,
            r"\.image-input-workspace\s*\{[^}]*--image-input-thumb-size:\s*clamp\("
            r"[\s\S]*104px,[\s\S]*116px",
        )
        self.assertIn("--recent-asset-size: 32px", compact)
        self.assertRegex(compact, r"\.image-uploader-grid\s*\{[^}]*padding:\s*clamp\(")
        self.assertRegex(
            compact,
            r"\.controls-col\s+\.image-panel\s+\.panel-heading\s*\{[^}]*"
            r"margin-bottom:\s*clamp\(4px,[^}]*16px\)",
        )
        self.assertRegex(
            compact,
            r"\.controls-col\s+\.prompt-box\s*\{[^}]*min-height:\s*0"
            r"[^}]*height:\s*100%[^}]*max-height:\s*100%[^}]*overflow-y:\s*auto",
        )
        self.assertRegex(
            compact,
            r"\.controls-col\s+\.prompt-compose\s+\.run-button\s*\{[^}]*"
            r"min-height:\s*0[^}]*height:\s*100%",
        )
        self.assertRegex(
            compact,
            r"\.settings-grid\s*\{[^}]*--compact-settings-control-height:\s*clamp\("
            r"[\s\S]*--compact-settings-segment-height:\s*clamp\("
            r"[\s\S]*gap:\s*var\(--compact-settings-gap\)",
        )
        self.assertRegex(
            compact,
            r"\.controls-col\s+\.output-settings-header\s*\{[^}]*min-height:\s*18px"
            r"[^}]*margin-bottom:\s*clamp\(",
        )
        self.assertRegex(
            compact,
            r"\.ratio-group\s*\{[^}]*grid-template-columns:\s*repeat\(6,\s*minmax\(0,\s*1fr\)\)"
            r"[^}]*grid-template-rows:\s*repeat\(2,\s*var\(--compact-settings-segment-height\)\)",
        )
        self.assertRegex(
            top_level,
            r"\.mode-settings-slot\s*\{[^}]*--mode-settings-stable-height:\s*clamp\("
            r"[\s\S]*77px,[\s\S]*144px",
        )
        self.assertNotRegex(
            top_level,
            r"\.(?:orientation|resolution|ratio|quantity|quality|moderation)-field\s*\{[^}]*grid-row",
        )
        self.assertNotRegex(
            top_level,
            r"#(?:promptFidelityField|pixelPreview|outputFormatField)\s*\{[^}]*grid-row",
        )
        self.assertNotRegex(
            top_level,
            r"\.quantity-quality-row\s*\{[^}]*display:\s*contents",
        )
        self.assertRegex(
            narrow,
            r"\.mode-specific-settings\s*\{[^}]*grid-template-columns:\s*"
            r"minmax\(0,\s*1fr\)\s+minmax\(0,\s*1fr\)",
        )
        self.assertRegex(
            narrow,
            r"\.settings-grid\.custom-size-mode\s*\{[^}]*"
            r"--custom-size-mode-card-height:\s*clamp\(\s*105px",
        )
        self.assertRegex(
            narrow,
            r"--custom-size-mode-card-height:\s*clamp\(\s*105px,\s*calc\(14\.76dvh\s*-\s*8\.4px\),\s*154px",
        )
        self.assertRegex(
            narrow,
            r"--mode-settings-stable-height:\s*clamp\(\s*48px,\s*calc\(15\.96dvh\s*-\s*74\.6px\),\s*102px",
        )
        self.assertRegex(
            compact,
            r"#pixelPreview\s*\{[^}]*min-height:\s*clamp\("
            r"[^}]*white-space:\s*nowrap",
        )
        self.assertRegex(
            compact,
            r"\.settings-grid\.custom-size-mode\s*\{[^}]*"
            r"--custom-size-mode-card-height:\s*clamp\(130px",
        )
        self.assertRegex(compact, r"\.custom-ratio-hint\s*\{[^}]*display:\s*none")
        self.assertNotIn(".api-direct-settings-grid", responsive)
    def test_very_short_desktop_uses_continuous_summary_height(self) -> None:
        responsive = Path("codex_image/webui/static/styles/80-utilities-responsive.css").read_text(encoding="utf-8")
        output = Path("codex_image/webui/static/styles/70-output-settings.css").read_text(encoding="utf-8")
        lock_source = Path("codex_image/webui/frontend/src/output-settings-lock.ts").read_text(encoding="utf-8")

        self.assertNotIn("@media (max-height: 820px)", responsive)
        self.assertNotIn("@media (max-height: 860px)", responsive)
        self.assertRegex(
            responsive,
            r"\.controls-col\s+\.image-panel\s*\{[^}]*"
            r"flex:\s*1\s+1\s+var\(--compact-image-panel-height\)",
        )
        self.assertRegex(output, r"\.output-settings-locked-summary\s*\{[^}]*position:\s*absolute[^}]*inset:\s*0")
        self.assertNotIn("--output-settings-editor-height", responsive + output + lock_source)
        self.assertNotIn("getBoundingClientRect", lock_source)

    def test_mid_width_short_desktop_keeps_input_gallery_side_rail_aligned(self) -> None:
        responsive = Path("codex_image/webui/static/styles/80-utilities-responsive.css").read_text(encoding="utf-8")
        compact = self._extract_last_css_at_rule(responsive, "@container workspace (max-width: 1100px)")

        self.assertRegex(compact, r"\.dashboard\s*\{[^}]*grid-template-columns:\s*minmax\(0,\s*1\.1fr\)\s+minmax\(320px,\s*0\.9fr\)")
        self.assertRegex(compact, r"\.controls-col\s+\.image-input-workspace\s*\{[^}]*--quick-gallery-column-width:\s*132px")
        self.assertRegex(compact, r"\.controls-col\s+\.image-input-workspace\s*\{[^}]*grid-template-columns:\s*minmax\(0,\s*1fr\)\s+var\(--quick-gallery-column-width\)")
        self.assertRegex(compact, r"\.controls-col\s+\.image-input-left,\s*\.controls-col\s+\.image-gallery-column\s*\{[^}]*height:\s*var\(--image-input-total-height\)")
        self.assertRegex(compact, r"\.controls-col\s+\.prompt-panel\s*\{[^}]*--prompt-action-column-width:\s*132px")
    def test_gallery_categories_are_managed_from_server_in_management_sheet(self) -> None:
        html = Path("codex_image/webui/static/index.html").read_text(encoding="utf-8")
        script = self._frontend_script_source()
        styles = Path("codex_image/webui/static/styles.css").read_text(encoding="utf-8")

        self.assertIn('id="galleryDrawer"', html)
        self.assertIn('id="galleryDrawerBackdrop"', html)
        self.assertNotIn('id="galleryModal"', html)
        self.assertIn('class="resource-sheet resource-sheet-wide gallery-drawer"', html)
        self.assertIn('id="galleryDrawerCategoryTabs"', html)
        self.assertIn('id="galleryCategoryManageToggle"', html)
        self.assertIn('id="galleryCategoryManagePanel"', html)
        self.assertIn('id="galleryCategoryList"', html)
        self.assertIn('id="addGalleryCategoryButton"', html)
        self.assertNotIn('id="galleryModalCategoryRail"', html)
        self.assertNotIn('class="gallery-category-view-row"', html)
        self.assertNotIn("查看分类</span>", html)
        self.assertIn("galleryCategories: defaultGalleryCategories()", script)
        self.assertIn("galleryDrawer: document.querySelector", script)
        self.assertIn("galleryDrawerBackdrop: document.querySelector", script)
        self.assertIn("galleryDrawerCategoryTabs: document.querySelector", script)
        self.assertIn("galleryCategoryManageToggle: document.querySelector", script)
        self.assertIn("galleryCategoryManagePanel: document.querySelector", script)
        self.assertNotIn("galleryModalCategoryRail: document.querySelector", script)
        self.assertIn("galleryCategoryList: document.querySelector", script)
        self.assertIn("addGalleryCategoryButton: document.querySelector", script)
        self.assertIn('fetch("/api/gallery/categories"', script)
        self.assertIn("function renderGalleryCategoryControls()", script)
        self.assertIn("function renderGalleryDrawerCategoryTabs()", script)
        self.assertIn("function handleGalleryDrawerCategoryTabClick(event)", script)
        self.assertIn("function toggleGalleryCategoryManager()", script)
        self.assertNotIn("function handleGalleryModalCategoryEvent(event)", script)
        self.assertIn("function setGalleryDrawerCategory(category)", script)
        self.assertIn("function handleGalleryCategoryListClick(event)", script)
        self.assertIn('els.galleryCategoryList?.addEventListener("click", handleGalleryCategoryListClick)', script)
        self.assertIn('els.galleryDrawerCategoryTabs?.addEventListener("click", handleGalleryDrawerCategoryTabClick)', script)
        self.assertIn('event.target.closest?.("[data-gallery-category-save],[data-gallery-category-delete]")', script)
        self.assertIn("updateGalleryCategory(button.dataset.galleryCategorySave)", script)
        self.assertIn("deleteGalleryCategory(button, button.dataset.galleryCategoryDelete)", script)
        self.assertIn('fetch("/api/gallery/categories/reorder"', script)
        self.assertIn("handleGalleryCategoryDragStart", script)
        self.assertIn("handleGalleryCategoryDragOver", script)
        self.assertIn("handleGalleryCategoryDrop", script)
        self.assertIn("handleGalleryCategoryDragEnd", script)
        self.assertIn("function createGalleryDragPreview", script)
        self.assertIn("function createGalleryElementDragPreview", script)
        self.assertIn("function setGalleryDragPreview", script)
        self.assertIn('els.galleryCategoryList?.addEventListener("dragstart", handleGalleryCategoryDragStart)', script)
        self.assertIn('els.galleryCategoryList?.addEventListener("dragover", handleGalleryCategoryDragOver)', script)
        self.assertIn('els.galleryCategoryList?.addEventListener("drop", handleGalleryCategoryDrop)', script)
        self.assertIn('data-gallery-category-drag-handle', script)
        self.assertIn("function renderGalleryGridWithHeightTransition()", script)
        self.assertIn("function shouldAnimateGalleryGridHeight()", script)
        self.assertIn("function resetGalleryGridTransition", script)
        self.assertIn("function activeGalleryGridLayer()", script)
        self.assertIn("function galleryGridLayerHtml(items)", script)
        self.assertIn("function bindGalleryGridActions", script)
        self.assertIn('fetch("/api/gallery/reorder"', script)
        self.assertIn("handleGalleryGridDragStart", script)
        self.assertIn("handleGalleryGridDragOver", script)
        self.assertIn("handleGalleryGridDrop", script)
        self.assertIn("handleGalleryGridDragEnd", script)
        self.assertIn("dataTransfer.setDragImage", script)
        self.assertIn("sourceElement: card", script)
        self.assertIn("sourceElement: categoryRow(categoryId)", script)
        self.assertIn("function galleryGridDomOrder()", script)
        self.assertIn("function moveGalleryGridDragPlaceholder", script)
        self.assertIn("moveGalleryGridDragPlaceholder(targetCard, placement)", script)
        self.assertIn("function categoryDomOrder()", script)
        self.assertIn("function moveGalleryCategoryDragPlaceholder", script)
        self.assertIn("moveGalleryCategoryDragPlaceholder(targetRow, placement)", script)
        self.assertIn("gallery-drag-preview", script)
        self.assertIn('els.galleryGrid?.addEventListener("dragstart", handleGalleryGridDragStart)', script)
        self.assertIn('els.galleryGrid?.addEventListener("dragover", handleGalleryGridDragOver)', script)
        self.assertIn('els.galleryGrid?.addEventListener("drop", handleGalleryGridDrop)', script)
        self.assertIn("data-gallery-order-handle", script)
        self.assertIn('nextLayer.className = "gallery-grid-layer mode-transition mode-collapsed"', script)
        self.assertIn('currentLayer.classList.add("mode-collapsed")', script)
        self.assertIn('nextLayer.classList.remove("mode-collapsed")', script)
        self.assertIn("renderGalleryGrid({ animateHeight: true })", script)
        self.assertIn("function renderGalleryCategoryManager()", script)
        self.assertIn("function createGalleryCategory()", script)
        self.assertIn("function updateGalleryCategory", script)
        self.assertIn("function deleteGalleryCategory", script)
        self.assertIn("function categoryPromptRole(category)", script)
        self.assertIn('legacyMethod("closePromptTemplateDrawer", { restoreFocus: false })', script)
        self.assertIn("data-gallery-category-name", script)
        self.assertIn("data-gallery-category-prompt-role", script)
        self.assertIn("data-gallery-category-delete", script)
        self.assertIn("data-gallery-category-drag-handle", script)
        self.assertNotIn("data-gallery-category-view", script)
        self.assertNotIn("data-gallery-category-order", script)
        self.assertNotIn('querySelectorAll("[data-gallery-category-view]").forEach', script)
        self.assertNotIn("data-gallery-modal-category", script)
        self.assertNotIn("GALLERY_CATEGORY_LABEL_STORAGE_KEY", script)
        self.assertNotIn("localStorage.setItem(GALLERY_CATEGORY_LABEL_STORAGE_KEY", script)
        self.assertRegex(styles, r"\.resource-sheet\s*\{[^}]*position:\s*fixed")
        self.assertRegex(styles, r"\.resource-sheet-wide\s*\{[^}]*width:\s*min\(760px,\s*52vw\)")
        self.assertIn(".gallery-drawer-top", styles)
        self.assertIn(".gallery-drawer-category-tabs", styles)
        self.assertRegex(styles, r"\.gallery-drawer-body\s*\{[^}]*grid-template-columns:\s*1fr[^}]*grid-template-rows:\s*auto\s+minmax\(0,\s*1fr\)")
        self.assertRegex(styles, r"\.gallery-drawer-category-tabs\s+\.quick-gallery-category\s*\{[^}]*width:\s*auto")
        self.assertRegex(styles, r"\.gallery-drawer-category-tabs\s+\.quick-gallery-category\s*\{[^}]*flex:\s*0\s+0\s+auto")
        self.assertRegex(styles, r"\.gallery-category-manage-panel\s*\{[^}]*display:\s*grid")
        self.assertRegex(styles, r"\.gallery-category-manage-panel\s*\{[^}]*width:\s*100%")
        self.assertNotIn(".gallery-category-order", styles)
        self.assertNotRegex(styles, r"\.gallery-category-view-row\s*\{")
        self.assertNotRegex(styles, r"\.gallery-modal-category-rail\s*\{")
        self.assertNotRegex(styles, r"\.gallery-modal-category\.active\s*\{")
        self.assertIn(".gallery-drag-handle", styles)
        self.assertRegex(styles, r"\.gallery-drag-handle\s*\{[^}]*cursor:\s*grab")
        self.assertIn(".gallery-drag-preview", styles)
        self.assertIn(".gallery-drag-preview-clone", styles)
        self.assertNotIn("gallery-category-current-badge", script)
        self.assertNotIn("gallery-category-current-placeholder", script)
        self.assertIn("aria-current=", script)
        self.assertIn("gallery-card-drag-strip", script)
        self.assertRegex(styles, r"\.gallery-category-create-row\s*\{[^}]*grid-template-columns:\s*34px\s+minmax\(160px,\s*1fr\)\s+minmax\(220px,\s*1\.5fr\)\s+auto")
        self.assertRegex(styles, r"\.gallery-category-row\s*\{[^}]*grid-template-columns:\s*34px\s+minmax\(160px,\s*1fr\)\s+minmax\(220px,\s*1\.5fr\)\s+auto")
        self.assertRegex(styles, r"\.gallery-category-row-toolbar\s*\{[^}]*width:\s*34px")
        self.assertIn(".gallery-category-row.is-current", styles)
        self.assertRegex(styles, r"\.gallery-card\s*\{[^}]*grid-template-rows:\s*auto\s+auto\s+auto\s+auto")
        self.assertRegex(styles, r"\.gallery-card-drag-strip\s*\{[^}]*width:\s*100%")
        self.assertRegex(styles, r"\.gallery-card-drag-strip\s*\{[^}]*cursor:\s*grab")
        self.assertIn(".gallery-card-heading", styles)
        self.assertNotRegex(styles, r"\.gallery-card-drag-handle\s*\{[^}]*position:\s*absolute")
        self.assertIn(".gallery-category-row.drop-target", styles)
        self.assertIn(".gallery-card.drop-target", styles)
        self.assertRegex(styles, r"\.gallery-category-row\.is-dragging,\s*\.gallery-card\.is-dragging\s*\{[^}]*opacity:\s*0\.42[^}]*\}")
        self.assertRegex(styles, r"\.gallery-grid\s*\{[^}]*transition:\s*height var\(--motion-height\)")
        self.assertRegex(styles, r"\.gallery-grid\.is-transitioning\s*\{[^}]*will-change:\s*height")
        self.assertRegex(styles, r"\.gallery-grid\s*>\s*\.gallery-grid-layer\s*\{[^}]*grid-area:\s*1\s*/\s*1")
        self.assertRegex(styles, r"\.gallery-grid-layer\s*\{[^}]*display:\s*grid")
        self.assertRegex(styles, r"\.gallery-grid-layer\s*\{[^}]*grid-template-columns:\s*repeat\(auto-fill,\s*minmax\(min\(100%,\s*220px\),\s*1fr\)\)")
        self.assertRegex(styles, r"\.gallery-card\s*\{[^}]*container-type:\s*inline-size")
        self.assertRegex(styles, r"\.gallery-card\s*\{[^}]*min-width:\s*0")
        self.assertRegex(styles, r"\.gallery-card\s*\{[^}]*max-width:\s*100%")
        self.assertRegex(styles, r"\.gallery-card-body\s*\{[^}]*min-width:\s*0")
        self.assertRegex(styles, r"\.gallery-card-heading\s*\{[^}]*min-width:\s*0")
        self.assertRegex(styles, r"\.gallery-card-heading strong\s*\{[^}]*display:\s*block[^}]*min-width:\s*0")
        self.assertRegex(styles, r"\.gallery-card-body span\s*\{[^}]*min-width:\s*0[^}]*overflow:\s*hidden[^}]*text-overflow:\s*ellipsis[^}]*white-space:\s*nowrap")
        self.assertRegex(styles, r"\.gallery-card-actions\s*\{[^}]*grid-template-columns:\s*repeat\(2,\s*minmax\(0,\s*1fr\)\)")
        self.assertRegex(styles, r"\.gallery-card-actions\s*\{[^}]*min-width:\s*0")
        self.assertRegex(styles, r"\.gallery-card-actions \.ghost-button\s*\{[^}]*min-width:\s*0[^}]*overflow:\s*hidden[^}]*text-overflow:\s*ellipsis[^}]*white-space:\s*nowrap")
        self.assertRegex(styles, r"@container \(max-width:\s*219px\)\s*\{[\s\S]*\.gallery-card-actions\s*\{[\s\S]*grid-template-columns:\s*1fr")
        self.assertNotIn("@keyframes galleryGridItemFadeIn", styles)
        self.assertRegex(styles, r"@media \(prefers-reduced-motion: reduce\)\s*\{[\s\S]*\.gallery-grid\s*\{[\s\S]*transition:\s*none")
        self.assertRegex(styles, r"\.gallery-category-list\s*\{[^}]*display:\s*grid")
        self.assertRegex(styles, r"\.gallery-category-row\s*\{[^}]*display:\s*grid")
        self.assertIn(".gallery-category-row-toolbar", styles)
        self.assertIn(".gallery-category-row-actions", styles)
        self.assertRegex(styles, r"@media \(max-width:\s*640px\)\s*\{[\s\S]*\.gallery-category-manage-panel\s*\{[\s\S]*grid-template-columns:\s*1fr")
        self.assertRegex(styles, r"@media \(max-width:\s*640px\)\s*\{[\s\S]*\.gallery-category-create-row\s*\{[\s\S]*grid-template-columns:\s*1fr")
        self.assertRegex(styles, r"@media \(max-width:\s*640px\)\s*\{[\s\S]*\.gallery-category-row\s*\{[\s\S]*grid-template-areas:")
    def test_gallery_item_edits_use_inline_popover(self) -> None:
        script = self._frontend_script_source()
        styles = Path("codex_image/webui/static/styles.css").read_text(encoding="utf-8")

        self.assertNotIn("window.prompt", script)
        self.assertIn("function openGalleryEditPopover", script)
        self.assertIn("function closeGalleryEditPopover", script)
        self.assertIn("closeConfirmPopover,", script)
        self.assertIn("positionGalleryEditPopover(anchor, popover)", script)
        self.assertIn("renameGalleryItem(button", script)
        self.assertIn("moveGalleryItem(button", script)
        self.assertIn("function handleGalleryGridClick(event)", script)
        self.assertIn('els.galleryGrid?.addEventListener("click", handleGalleryGridClick)', script)
        self.assertIn('event.target.closest?.("[data-gallery-use],[data-gallery-rename],[data-gallery-replace],[data-gallery-move],[data-gallery-note],[data-gallery-delete]")', script)
        self.assertIn("data-gallery-edit-save", script)
        self.assertIn("data-gallery-edit-cancel", script)
        self.assertIn("data-gallery-edit-name", script)
        self.assertIn("data-gallery-edit-category", script)
        self.assertIn("data-gallery-replace", script)
        self.assertRegex(script, r'data-gallery-use="\$\{escapeHtml\(item\.id\)\}">\$\{translate\("gallery\.use"\)\}</button>')
        self.assertRegex(script, r'data-gallery-replace="\$\{escapeHtml\(item\.id\)\}">\$\{translate\("gallery\.replace"\)\}</button>')
        self.assertNotIn(">替换图像</button>", script)
        self.assertIn("function replaceGalleryItemImage", script)
        self.assertIn('fetch(`/api/gallery/${encodeURIComponent(itemId)}/image`', script)
        self.assertNotIn('querySelectorAll("[data-gallery-rename]").forEach', script)
        self.assertRegex(styles, r"\.gallery-edit-popover\s*\{[^}]*position:\s*fixed")
        self.assertRegex(styles, r"\.gallery-edit-field\s*\{[^}]*display:\s*grid")
        self.assertRegex(styles, r"\.gallery-edit-actions\s*\{[^}]*display:\s*flex")
        self.assertRegex(styles, r"\.gallery-card-actions\s*\{[^}]*grid-template-columns")
        self.assertNotRegex(styles, r"\.gallery-card-actions\s+\[data-gallery-replace\]\s*\{[^}]*grid-column")
    def test_auth_source_switcher_is_available_in_top_nav(self) -> None:
        html = Path("codex_image/webui/static/index.html").read_text(encoding="utf-8")
        script = self._frontend_script_source()
        auth_source = Path("codex_image/webui/frontend/src/auth-source.ts").read_text(encoding="utf-8")
        styles = Path("codex_image/webui/static/styles.css").read_text(encoding="utf-8")

        self.assertIn('id="authSourceGroup"', html)
        self.assertIn('data-auth-source="codex"', html)
        self.assertIn('data-auth-source="api"', html)
        for removed_source in ("auto", "cock" + "pit"):
            self.assertNotIn(f'data-auth-source="{removed_source}"', html)
        self.assertIn('id="authSourceDetail"', html)
        self.assertLess(html.index('id="authSourceDetail"'), html.index('id="authSourceGroup"'))
        removed_quota_button_id = "account" + "QuotaButton"
        self.assertNotIn(f'id="{removed_quota_button_id}"', html)
        self.assertNotIn('id="authPill"', html)
        self.assertNotIn('authPill:', script)
        self.assertNotIn("authPillText", script)
        self.assertNotIn(".auth-pill", styles)
        self.assertIn("/api/auth", script)
        self.assertIn("setAuthSource", script)
        self.assertIn("renderAuthSource", script)
        self.assertNotIn('onclick="setAuthSource', html)
        self.assertIn('authSourceGroup?.addEventListener("click", (event) => call(methods, "handleAuthSourceClick", event))', script)
        self.assertIn('button.setAttribute("aria-pressed", active ? "true" : "false")', script)
        self.assertIn("function handleAuthSourceClick(event)", script)
        self.assertIn('event.target.closest?.("[data-auth-source]")', script)
        self.assertNotIn('if (source === "api" && currentAuthSource() === "api")', script)
        self.assertIn('apiSourceSettingsButton?.addEventListener("click", () => call(methods, "openApiSettingsModal"))', script)
        self.assertIn("void setAuthSource(source, button)", auth_source)
        self.assertIn('class="auth-source-button auth-source-api-button"', html)
        self.assertIn('id="apiSourceSettingsButton"', html)
        self.assertIn('aria-label="系统设置"', html)
        self.assertIn('title="系统设置"', html)
        self.assertNotIn("双击打开 API 设置", html)
        self.assertIn('id="githubLink"', html)
        self.assertIn('href="https://github.com/kadevin/ilab-gpt-conjure"', html)
        self.assertIn('aria-label="GitHub"', html)
        self.assertIn('target="_blank"', html)
        self.assertIn('rel="noreferrer"', html)
        nav_actions = html[html.index('<div class="nav-actions">'):html.index('<div id="taskNotificationCenter"')]
        self.assertNotIn('id="languageSwitcher"', nav_actions)
        self.assertRegex(styles, r"\.nav-actions\s*\{[^}]*--top-nav-control-height:\s*36px")
        self.assertRegex(styles, r"\.nav-actions\s*\{[^}]*--top-nav-control-radius:\s*999px")
        self.assertRegex(styles, r"\.nav-actions\s*\{[^}]*--top-nav-segment-height:\s*30px")
        self.assertRegex(styles, r"\.queue-button\s*\{[^}]*height:\s*var\(--top-nav-control-height\)")
        self.assertRegex(styles, r"\.queue-button\s*\{[^}]*min-height:\s*var\(--top-nav-control-height\)")
        self.assertRegex(styles, r"\.queue-button\s*\{[^}]*border-radius:\s*var\(--top-nav-control-radius\)")
        self.assertRegex(styles, r"\.queue-badge\s*\{[^}]*height:\s*22px")
        self.assertRegex(styles, r"\.queue-badge\s*\{[^}]*border-radius:\s*var\(--top-nav-control-radius\)")
        self.assertRegex(styles, r"\.task-notification-button\s*\{[^}]*position:\s*relative")
        self.assertRegex(styles, r"\.task-notification-button\.has-unread\s*\{[^}]*background:")
        self.assertRegex(styles, r"\.task-notification-dot\s*\{[^}]*top:\s*8px")
        self.assertRegex(styles, r"\.task-notification-dot\s*\{[^}]*right:\s*8px")
        self.assertRegex(styles, r"\.task-notification-dot\s*\{[^}]*width:\s*7px")
        self.assertNotRegex(styles, r"\.task-notification-button \.queue-badge\s*\{")
        self.assertRegex(styles, r"\.auth-source-switcher\s*\{[^}]*display:\s*flex")
        self.assertRegex(styles, r"\.auth-source-switcher\s*\{[^}]*flex-direction:\s*row")
        self.assertRegex(styles, r"\.auth-source-switcher\s*\{[^}]*align-items:\s*center")
        self.assertRegex(styles, r"\.auth-source-switcher\s*\{[^}]*position:\s*relative")
        self.assertNotRegex(styles, r"\.auth-source-switcher\s*\{[^}]*flex-direction:\s*column")
        self.assertRegex(styles, r"\.auth-source-group\s*\{[^}]*display:\s*inline-flex")
        self.assertRegex(styles, r"\.auth-source-group\s*\{[^}]*height:\s*var\(--top-nav-control-height\)")
        self.assertRegex(styles, r"\.auth-source-group\s*\{[^}]*border-radius:\s*var\(--top-nav-control-radius\)")
        self.assertRegex(styles, r"\.auth-source-button\s*\{[^}]*height:\s*var\(--top-nav-segment-height\)")
        self.assertRegex(styles, r"\.auth-source-button\s*\{[^}]*border-radius:\s*var\(--top-nav-control-radius\)")
        self.assertNotIn(removed_quota_button_id, script)
        self.assertIn('els.apiProviderQuick?.classList.add("hidden")', script)
        self.assertNotIn('els.apiProviderQuick?.classList.toggle("hidden", selected !== "api")', script)
        self.assertNotRegex(styles, r"\.account-quota-button\s*\{")
        self.assertRegex(styles, r"\.auth-source-api-button\s*\{[^}]*gap:\s*4px")
        self.assertRegex(styles, r"\.auth-source-settings-button\s*\{[^}]*width:\s*var\(--top-nav-control-height\)")
        self.assertRegex(styles, r"\.github-link\s*\{[^}]*width:\s*var\(--top-nav-control-height\)")
        self.assertNotRegex(styles, r"\.language-switcher\s*\{[^}]*height:\s*var\(--top-nav-control-height\)")
        self.assertNotRegex(styles, r"\.language-option\s*\{")
        self.assertNotRegex(styles, r"\.api-provider-quick\s*\{[^}]*position:\s*absolute")
        self.assertRegex(styles, r"\.api-provider-quick\s*\{[^}]*height:\s*var\(--top-nav-control-height\)")
        self.assertRegex(styles, r"\.api-provider-quick\s*\{[^}]*border-radius:\s*var\(--top-nav-control-radius\)")
        self.assertRegex(styles, r"\.auth-source-detail\s*\{[^}]*width:\s*150px")
        self.assertRegex(styles, r"\.auth-source-detail\s*\{[^}]*overflow:\s*hidden")
        self.assertRegex(styles, r"\.auth-source-detail\s*\{[^}]*text-overflow:\s*ellipsis")
        self.assertNotRegex(styles, r"\.auth-source-detail\s*\{[^}]*width:\s*128px")
        self.assertIn("els.authSourceDetail.title = text", script)
        self.assertIn('function currentApiProviderLabel(): string { return legacyMethod("currentApiProviderLabel"); }', auth_source)
        self.assertNotIn("自动 →", auth_source)
        self.assertIn('return `API · ${provider} · ${mode}`;', auth_source)
        self.assertIn('return "Codex";', auth_source)
        self.assertIn('formatTranslation("auth.sourceUnavailable", { source: selected })', auth_source)
        self.assertNotIn('return `${effective} · ${mode} · ${imageModel}`', auth_source)
        self.assertRegex(styles, r"\.auth-source-button\.active\s*\{[^}]*background:\s*var\(--primary\)")
        self.assertNotIn("文档中心", html)
        self.assertNotIn("user-profile", html)
    def test_output_and_auth_switchers_use_sliding_segmented_indicator(self) -> None:
        styles = Path("codex_image/webui/static/styles.css").read_text(encoding="utf-8")
        main_source = Path("codex_image/webui/frontend/src/main.ts").read_text(encoding="utf-8")
        indicator_source = Path("codex_image/webui/frontend/src/segmented-indicator.ts").read_text(encoding="utf-8")

        self.assertIn('import { initSegmentedIndicatorFeature } from "./segmented-indicator";', main_source)
        self.assertLess(main_source.index("initSegmentedIndicatorFeature();"), main_source.index("window.__codexImageWebUI?.boot();"))
        self.assertIn('".radio-group:not(.ratio-group)"', indicator_source)
        self.assertIn('"#authSourceGroup"', indicator_source)
        self.assertIn('"#systemSettingsTabs"', indicator_source)
        self.assertIn(".system-settings-tab", indicator_source)
        self.assertIn("refreshSegmentedIndicators", indicator_source)
        self.assertIn("getBoundingClientRect()", indicator_source)
        self.assertIn("window.getComputedStyle(host)", indicator_source)
        self.assertIn("borderLeftWidth", indicator_source)
        self.assertIn("borderTopWidth", indicator_source)
        self.assertIn("activeRect.left - hostRect.left - borderLeft", indicator_source)
        self.assertIn("activeRect.top - hostRect.top - borderTop", indicator_source)
        self.assertIn("--segmented-indicator-x", indicator_source)
        self.assertIn("--segmented-indicator-width", indicator_source)
        self.assertIn("MutationObserver", indicator_source)
        self.assertIn("ResizeObserver", indicator_source)

        self.assertRegex(styles, r"\.segmented-indicator-host\s*\{[^}]*position:\s*relative")
        self.assertRegex(styles, r"\.segmented-indicator-host\s*\{[^}]*isolation:\s*isolate")
        self.assertRegex(styles, r"\.radio-group\s*\{[^}]*--segmented-control-padding:\s*3px")
        self.assertRegex(styles, r"\.radio-group\s*\{[^}]*--segmented-control-height:\s*30px")
        self.assertRegex(styles, r"\.radio-group\s*\{[^}]*align-items:\s*stretch")
        self.assertRegex(styles, r"\.radio-group\s*\{[^}]*padding:\s*var\(--segmented-control-padding\)")
        self.assertRegex(styles, r"\.radio-btn\s*\{[^}]*display:\s*inline-flex")
        self.assertRegex(styles, r"\.radio-btn\s*\{[^}]*align-items:\s*center")
        self.assertRegex(styles, r"\.radio-btn\s*\{[^}]*height:\s*var\(--segmented-control-height\)")
        self.assertRegex(styles, r"\.radio-btn\s*\{[^}]*border-radius:\s*var\(--segmented-indicator-radius\)")
        self.assertRegex(styles, r"\.ratio-group\s+\.radio-btn\s*\{[^}]*height:\s*100%")
        self.assertRegex(styles, r"\.segmented-indicator\s*\{[^}]*position:\s*absolute")
        self.assertRegex(styles, r"\.segmented-indicator\s*\{[^}]*border-radius:\s*var\(--segmented-indicator-radius\)")
        self.assertRegex(styles, r"\.segmented-indicator\s*\{[^}]*background:\s*var\(--primary\)")
        self.assertRegex(styles, r"\.segmented-indicator\s*\{[^}]*transform:\s*translate3d\(var\(--segmented-indicator-x")
        self.assertRegex(styles, r"\.segmented-indicator\s*\{[^}]*transition:\s*transform var\(--motion-base\)")
        self.assertRegex(styles, r"\.segmented-indicator\s*\{[^}]*width var\(--motion-base\)")
        self.assertRegex(styles, r"\.radio-group\.segmented-indicator-host\s+\.radio-btn\.active\s*\{[^}]*background:\s*transparent")
        self.assertRegex(styles, r"\.auth-source-group\.segmented-indicator-host\s+\.auth-source-button\.active\s*\{[^}]*background:\s*transparent")
        self.assertRegex(styles, r"\.system-settings-tabs\.segmented-indicator-host\s+\.system-settings-tab\.active\s*\{[^}]*background:\s*transparent")
        self.assertRegex(styles, r"\.system-settings-tabs\.segmented-indicator-host\s+\.system-settings-tab\.active\s*\{[^}]*color:\s*var\(--primary-foreground\)")
        self.assertRegex(styles, r"@media \(prefers-reduced-motion:\s*reduce\)\s*\{[\s\S]*\.segmented-indicator\s*\{[^}]*transition:\s*none")
    def test_api_source_switcher_and_system_settings_modal_exist(self) -> None:
        html = Path("codex_image/webui/static/index.html").read_text(encoding="utf-8")
        script = self._frontend_script_source()
        event_source = Path("codex_image/webui/frontend/src/event-bindings.ts").read_text(encoding="utf-8")
        advanced_source = Path("codex_image/webui/frontend/src/api-advanced-settings.ts").read_text(encoding="utf-8")
        provider_list_source = Path("codex_image/webui/frontend/src/api-provider-list-ui.ts").read_text(encoding="utf-8")
        provider_source = Path("codex_image/webui/frontend/src/api-provider-settings.ts").read_text(encoding="utf-8")
        main_source = Path("codex_image/webui/frontend/src/main.ts").read_text(encoding="utf-8")
        styles = Path("codex_image/webui/static/styles.css").read_text(encoding="utf-8")

        self.assertIn('data-auth-source="api"', html)
        self.assertNotIn('onclick="setAuthSource', html)
        self.assertIn('id="systemSettingsModal"', html)
        self.assertIn('id="systemSettingsTabs"', html)
        self.assertNotIn('data-i18n="systemSettings.subtitle"', html)
        self.assertNotIn('data-i18n="apiSettings.title"', html)
        self.assertNotIn('data-i18n="codexSettings.title"', html)
        self.assertNotIn('data-i18n="settings.title"', html)
        self.assertNotIn('class="system-settings-section-heading"', html)
        self.assertIn('id="systemSettingsApiTab"', html)
        self.assertIn('id="systemSettingsCodexTab"', html)
        self.assertIn('id="systemSettingsLanguageTab"', html)
        self.assertIn('id="systemSettingsStorageTab"', html)
        self.assertIn('id="systemSettingsApiPanel"', html)
        self.assertIn('id="systemSettingsCodexPanel"', html)
        self.assertIn('id="systemSettingsLanguagePanel"', html)
        self.assertIn('id="systemSettingsStoragePanel"', html)
        self.assertIn('id="languageSelect"', html)
        self.assertIn('id="apiSettingsStatus"', html)
        self.assertIn('id="codexSettingsStatus"', html)
        self.assertIn('id="languageSettingsStatus"', html)
        self.assertIn('id="settingsStatus"', html)
        self.assertIn('class="api-settings-feedback settings-action-status"', html)
        self.assertIn('class="settings-action-status" data-i18n="settings.status"', html)
        self.assertIn('class="settings-action-status language-settings-status" data-i18n="languageSettings.instantStatus"', html)
        self.assertNotIn('id="apiSettingsStatus" class="api-settings-feedback" data-i18n="apiSettings.status"', html)
        self.assertNotIn('id="codexSettingsStatus" class="api-settings-feedback" data-i18n="codexSettings.status"', html)
        self.assertIn("let systemSettingsBackdropPointerDown = false", event_source)
        self.assertIn('systemSettingsModal?.addEventListener("pointerdown"', event_source)
        self.assertIn("systemSettingsBackdropPointerDown = event.target === els.systemSettingsModal", event_source)
        self.assertIn("if (event.target === els.systemSettingsModal && systemSettingsBackdropPointerDown)", event_source)
        self.assertNotIn('if (event.target === els.systemSettingsModal) call(methods, "closeSystemSettingsModal")', event_source)
        self.assertLess(html.index('id="systemSettingsApiTab"'), html.index('id="systemSettingsCodexTab"'))
        self.assertLess(html.index('id="systemSettingsCodexTab"'), html.index('id="systemSettingsLanguageTab"'))
        self.assertLess(html.index('id="systemSettingsLanguageTab"'), html.index('id="systemSettingsStorageTab"'))
        self.assertLess(html.index('id="systemSettingsApiPanel"'), html.index('id="systemSettingsCodexPanel"'))
        self.assertLess(html.index('id="systemSettingsCodexPanel"'), html.index('id="systemSettingsLanguagePanel"'))
        self.assertLess(html.index('id="systemSettingsLanguagePanel"'), html.index('id="systemSettingsStoragePanel"'))
        self.assertIn('aria-selected="true"', html)
        self.assertIn('data-system-settings-tab="api"', html)
        self.assertIn('data-system-settings-tab="codex"', html)
        self.assertIn('data-system-settings-tab="language"', html)
        self.assertIn('data-system-settings-tab="storage"', html)
        self.assertIn('id="apiBaseUrl"', html)
        self.assertIn('id="apiRequestEndpointPreview"', html)
        self.assertIn('data-i18n="apiSettings.actualRequest"', html)
        provider_name_field_start = html.index('class="field api-provider-name-field"')
        base_url_field_start = html.index('class="field api-base-url-field"')
        api_key_field_start = html.index('class="field api-key-field"')
        api_mode_field_start = html.index('class="field api-mode-field"')
        endpoint_preview_start = html.index('class="api-request-endpoint-preview"')
        advanced_settings_start = html.index('id="apiAdvancedSettings"')
        image_model_field_start = html.index('class="field api-image-model-field"')
        concurrency_field_start = html.index('class="field api-concurrency-field"')
        self.assertLess(provider_name_field_start, base_url_field_start)
        self.assertLess(base_url_field_start, api_key_field_start)
        self.assertLess(api_key_field_start, api_mode_field_start)
        self.assertLess(api_mode_field_start, endpoint_preview_start)
        self.assertLess(endpoint_preview_start, advanced_settings_start)
        self.assertLess(advanced_settings_start, image_model_field_start)
        self.assertLess(image_model_field_start, concurrency_field_start)
        self.assertIn('id="apiKey"', html)
        self.assertIn('id="apiImageModel"', html)
        self.assertIn('data-i18n="apiSettings.imageModel">图像生成模型</span>', html)
        self.assertIn('<details id="apiAdvancedSettings" class="api-advanced-settings">', html)
        self.assertIn('data-i18n="apiSettings.advancedSettings">高级设置</strong>', html)
        self.assertIn('id="apiAdvancedImageModelSummary"', html)
        self.assertIn('id="apiAdvancedConcurrencySummary"', html)
        self.assertNotIn('<details id="apiAdvancedSettings" class="api-advanced-settings" open', html)
        api_mode_field = html[html.index('class="field api-mode-field"'):html.index('id="apiMode" class="hidden"')]
        self.assertNotIn('data-i18n="apiSettings.mode">调用方式</span>', api_mode_field)
        self.assertIn('id="apiModeGroup" role="group" aria-label="调用方式"', api_mode_field)
        self.assertIn('data-i18n-attr="aria-label:apiSettings.mode"', api_mode_field)
        self.assertIn('id="apiImagesConcurrency"', html)
        self.assertIn('max="32"', html)
        self.assertIn('data-i18n="apiSettings.concurrency">并发上限</span>', html)
        self.assertIn('imageModelInput()?.addEventListener("input", syncApiAdvancedSettingsSummary)', advanced_source)
        self.assertIn('concurrencyInput()?.addEventListener("input", syncApiAdvancedSettingsSummary)', advanced_source)
        self.assertIn("if (details) details.open = false", advanced_source)
        self.assertIn("resetApiAdvancedSettings();", provider_source)
        self.assertIn('import { initApiAdvancedSettingsFeature } from "./api-advanced-settings";', main_source)
        self.assertLess(main_source.index("initApiAdvancedSettingsFeature();"), main_source.index("window.__codexImageWebUI?.boot();"))
        self.assertIn('id="codexModeGroup"', html)
        self.assertIn('id="codexMode"', html)
        self.assertIn('data-codex-mode-note="images"', html)
        self.assertIn('data-codex-mode-note="responses"', html)
        self.assertIn('aria-current="true"', html)
        self.assertIn('data-i18n="codexSettings.current"', html)
        self.assertIn("Codex 通道", html)
        self.assertRegex(html, r'id="codexModeGroup"[\s\S]*data-val="images"[\s\S]*data-val="responses"')
        self.assertLess(html.index('id="apiProvider"'), html.index('id="systemSettingsCodexPanel"'))
        self.assertLess(html.index('id="systemSettingsCodexPanel"'), html.index('id="codexModeGroup"'))
        self.assertNotIn('id="saveApiSettingsButton"', html)
        self.assertNotIn('id="saveCodexSettingsButton"', html)
        self.assertIn('class="settings-modal-actions settings-status-only"', html)
        self.assertIn('id="apiMode"', html)
        self.assertIn('id="apiProviderQuick"', html)
        self.assertIn('id="apiDirectSettingsButton"', html)
        self.assertIn('class="model-tool-row"', html)
        self.assertIn('id="webSearchField"', html)
        self.assertIn('id="webSearch"', html)
        self.assertIn('id="apiProvider"', html)
        self.assertIn('id="apiProviderCount"', html)
        self.assertIn('id="apiProviderSearchField"', html)
        self.assertIn('id="apiProviderSearch"', html)
        self.assertIn('data-i18n-attr="placeholder:apiSettings.searchProviders;aria-label:apiSettings.searchProviders"', html)
        self.assertIn('id="apiProviderList"', html)
        self.assertIn('id="apiProviderSection"', html)
        self.assertIn('id="apiProviderDetail"', html)
        self.assertNotIn('id="apiProviderDetailName"', html)
        self.assertNotIn('id="apiProviderDetailMeta"', html)
        self.assertIn('id="apiProviderDetailBaseUrl"', html)
        self.assertIn('id="apiProviderDetailKey"', html)
        self.assertIn('id="apiProviderEditor"', html)
        self.assertIn('id="apiProviderName"', html)
        self.assertIn('class="api-key-input-wrap"', html)
        self.assertIn('id="apiKeyRevealButton"', html)
        self.assertIn('aria-pressed="false"', html)
        self.assertIn('data-i18n-attr="aria-label:apiSettings.showApiKey;title:apiSettings.showApiKey"', html)
        self.assertIn('id="editApiProviderButton"', html)
        self.assertIn('id="copyApiProviderButton"', html)
        self.assertIn('id="addApiProviderButton"', html)
        self.assertIn('id="sortApiProvidersButton"', html)
        self.assertIn('class="api-provider-choice-grid"', html)
        self.assertIn('class="api-provider-add-card"', html)
        self.assertIn('data-i18n="apiSettings.newProviderAction"', html)
        self.assertIn('data-i18n="apiSettings.copyProvider"', html)
        self.assertIn('data-i18n="apiSettings.sortProviders"', html)
        self.assertIn('id="deleteApiProviderButton"', html)
        self.assertIn('id="cancelApiProviderEditButton"', html)
        self.assertIn('id="saveApiProviderEditButton"', html)
        self.assertIn('id="apiSettingsActions"', html)
        self.assertLess(html.index('id="apiSettingsActions"'), html.index('id="apiSettingsStatus"'))
        self.assertLess(html.index('class="codex-channel-notes"'), html.index('id="codexSettingsStatus"'))
        self.assertLess(html.index('id="languageSelect"'), html.index('id="languageSettingsStatus"'))
        self.assertLess(html.index('id="settingsStatus"'), html.index('id="saveSettingsButton"'))
        self.assertLess(html.index('id="apiProviderList"'), html.index('id="addApiProviderButton"'))
        self.assertLess(html.index('id="apiProviderDetailConcurrency"'), html.index('id="editApiProviderButton"'))
        self.assertLess(html.index('id="editApiProviderButton"'), html.index('id="copyApiProviderButton"'))
        self.assertLess(html.index('id="copyApiProviderButton"'), html.index('id="deleteApiProviderButton"'))
        self.assertLess(html.index('id="apiProviderCount"'), html.index('id="sortApiProvidersButton"'))
        self.assertLess(html.index('id="sortApiProvidersButton"'), html.index('id="apiProviderSearchField"'))
        self.assertLess(html.index('id="apiProviderSearchField"'), html.index('class="api-provider-choice-grid"'))
        self.assertLess(html.index('id="apiProviderList"'), html.index('id="apiProviderDetail"'))
        self.assertLess(html.index('id="apiProviderDetail"'), html.index('id="apiProviderEditor"'))
        self.assertIn('api-settings-feedback settings-action-status', html)
        self.assertIn('data-val="images"', html)
        self.assertIn('data-val="responses"', html)
        self.assertEqual(html.count('id="mainModel"'), 1)
        self.assertNotIn('id="apiMainModel"', html)
        self.assertIn("API_SETTINGS_STORAGE_KEY", script)
        self.assertIn("systemSettingsModal: document.querySelector", script)
        self.assertIn("systemSettingsTabs: document.querySelector", script)
        self.assertIn("systemSettingsCodexPanel: document.querySelector", script)
        self.assertIn("systemSettingsLanguagePanel: document.querySelector", script)
        self.assertIn("languageSelect: document.querySelector", script)
        self.assertIn("function openSystemSettingsModal", script)
        self.assertIn("function setSystemSettingsTab", script)
        self.assertIn("function openSystemSettingsFromUrl", script)
        self.assertIn("new URLSearchParams(window.location.search)", script)
        self.assertIn('params.get("settings")', script)
        self.assertIn('openSystemSettingsModal(settingsTab || "api")', script)
        self.assertIn("window.history.replaceState", script)
        self.assertIn("apiBaseUrl: document.querySelector", script)
        self.assertIn("apiRequestEndpointPreview: document.querySelector", script)
        self.assertIn("apiKey: document.querySelector", script)
        self.assertIn("apiKeyRevealButton: document.querySelector", script)
        self.assertIn("apiImageModel: document.querySelector", script)
        self.assertIn("apiImagesConcurrency: document.querySelector", script)
        self.assertIn("codexMode: document.querySelector", script)
        self.assertIn("codexModeGroup: document.querySelector", script)
        self.assertIn('codexModeNotes: document.querySelectorAll("[data-codex-mode-note]")', script)
        self.assertNotIn("saveApiSettingsButton: document.querySelector", script)
        self.assertNotIn("saveCodexSettingsButton: document.querySelector", script)
        self.assertNotIn('saveApiSettingsButton?.addEventListener("click"', script)
        self.assertNotIn('saveCodexSettingsButton?.addEventListener("click"', script)
        self.assertIn('codexModeNotes?.forEach', script)
        self.assertIn('call(methods, "selectCodexMode", note.dataset.codexModeNote)', script)
        self.assertIn('call(methods, "queueApiSettingsAutosave")', script)
        self.assertIn("apiMode: document.querySelector", script)
        self.assertIn("apiProvider: document.querySelector", script)
        self.assertIn("apiProviderQuick: document.querySelector", script)
        self.assertIn("apiDirectSettingsButton: document.querySelector", script)
        self.assertIn("webSearch: document.querySelector", script)
        self.assertIn("webSearchField: document.querySelector", script)
        self.assertIn('apiDirectSettingsButton?.addEventListener("click", () => call(methods, "openApiSettingsModal"))', script)
        self.assertIn("apiProviderName: document.querySelector", script)
        self.assertIn("apiProviderSection: document.querySelector", script)
        self.assertIn("apiProviderSearch: document.querySelector", script)
        self.assertIn("apiProviderList: document.querySelector", script)
        self.assertIn("apiProviderDetail: document.querySelector", script)
        self.assertIn("apiProviderEditor: document.querySelector", script)
        self.assertIn("editApiProviderButton: document.querySelector", script)
        self.assertIn("copyApiProviderButton: document.querySelector", script)
        self.assertIn("sortApiProvidersButton: document.querySelector", script)
        self.assertIn("cancelApiProviderEditButton: document.querySelector", script)
        self.assertIn("saveApiProviderEditButton: document.querySelector", script)
        self.assertIn("apiSettingsActions: document.querySelector", script)
        self.assertIn("function activeApiProvider", script)
        self.assertIn("function selectApiProvider", script)
        self.assertIn("function editApiProvider", script)
        self.assertIn("function copyApiProvider", script)
        self.assertIn("function toggleApiProviderSortMode", script)
        self.assertIn("function moveApiProvider", script)
        self.assertIn("api_key_source_provider_id", script)
        self.assertIn("const copiesSavedKey = providerHasApiKey(provider)", script)
        self.assertIn('api_key_source_provider_id: copiesSavedKey ? provider.id : ""', script)
        self.assertIn("if (!provider.api_key && provider.api_key_source_provider_id)", script)
        self.assertIn("function confirmDeleteApiProvider", script)
        self.assertIn("function cancelApiProviderEdit", script)
        self.assertIn("function saveApiProviderEdit", script)
        self.assertIn("function renderApiProviderList", script)
        self.assertIn("export const API_PROVIDER_SEARCH_THRESHOLD = 10", provider_list_source)
        self.assertIn('classList.toggle("is-long-list", longList)', provider_list_source)
        self.assertIn('classList.toggle("hidden", !searchVisible)', provider_list_source)
        self.assertIn("apiProviderMatchesSearch", provider_list_source)
        self.assertIn("scrollActiveApiProviderCardIntoView", provider_list_source)
        self.assertIn("grid.scrollTo", provider_list_source)
        self.assertIn("Math.floor(maxScrollTop / rowStep) * rowStep", provider_list_source)
        self.assertNotIn("scrollIntoView", provider_list_source)
        self.assertIn("apiProviderMatchesSearch(provider, searchQuery)", provider_source)
        self.assertIn('translate("apiSettings.noProviderSearchResults")', provider_source)
        self.assertIn('if (!searchQuery) scrollActiveApiProviderCardIntoView(settings.active_provider_id, "center")', provider_source)
        self.assertIn('scrollActiveApiProviderCardIntoView(activeApiProvider().id, "center")', provider_source)
        self.assertIn("function renderApiProviderDetail", script)
        self.assertIn("function renderApiProviderEditor", script)
        self.assertIn('apiProviderSection?.setAttribute("aria-hidden", visible ? "true" : "false")', script)
        self.assertIn('apiProviderSection?.setAttribute("inert", "")', script)
        self.assertIn('apiProviderSection?.removeAttribute("inert")', script)
        self.assertIn("function updateApiRequestEndpointPreview", script)
        self.assertIn('mode === "responses"', script)
        self.assertIn('? "/responses"', script)
        self.assertIn('state.mode === "edit" ? "/images/edits" : "/images/generations"', script)
        self.assertIn(".split(/[?#]/, 1)[0]", script)
        self.assertIn("function setApiKeyRevealVisible", script)
        self.assertIn("function updateApiKeyRevealButton", script)
        self.assertIn("function revealApiKeyWhilePressed", script)
        self.assertIn("function hideApiKeyReveal", script)
        self.assertIn("function addApiProvider", script)
        self.assertIn("function deleteApiProvider", script)
        self.assertIn("apiProviderDraft", script)
        self.assertIn("apiProviderDraftIsNew", script)
        self.assertIn("options.applyProviderDraft", script)
        self.assertIn("readApiSettingsForm({ applyProviderDraft: !autoSave })", script)
        self.assertIn("localStorage.getItem(API_SETTINGS_STORAGE_KEY)", script)
        self.assertIn("localStorage.setItem(API_SETTINGS_STORAGE_KEY", script)
        self.assertIn("active_provider_id: state.apiSettings.active_provider_id", script)
        self.assertIn("providers: state.apiSettings.providers", script)
        self.assertIn("codex_mode: state.apiSettings.codex_mode", script)
        self.assertIn("function currentCodexMode", script)
        self.assertIn('return mode === "responses" ? "Codex Responses" : "Codex Image"', script)
        self.assertIn("function syncCodexModeNotes", script)
        self.assertIn('note.dataset.codexModeNote === mode', script)
        self.assertIn('note.setAttribute("aria-current", active ? "true" : "false")', script)
        self.assertIn("function selectCodexMode", script)
        self.assertIn("function queueApiSettingsAutosave", script)
        self.assertRegex(provider_source, r"function deleteApiProvider\(\)[\s\S]*queueApiSettingsAutosave\(\);[\s\S]*function confirmDeleteApiProvider")
        self.assertRegex(provider_source, r"function selectApiProvider\(providerId[^)]*\)[\s\S]*queueApiSettingsAutosave\(\);[\s\S]*function editApiProvider")
        self.assertRegex(provider_source, r"function moveApiProvider\(providerId[^,]*, direction[^)]*\)[\s\S]*queueApiSettingsAutosave\(\);[\s\S]*async function saveApiProviderEdit")
        self.assertIn('void saveApiSettings({ auto: true })', script)
        self.assertIn('translate("apiSettings.autoSaving")', script)
        self.assertIn('translate("apiSettings.autoSaved")', script)
        self.assertIn("codexModeLabel(currentCodexMode())", script)
        self.assertIn("function setApiSettingsFeedback", script)
        self.assertIn("function setSaveButtonText", script)
        self.assertIn('saving: translate("apiSettings.saving")', script)
        self.assertIn('saved: translate("apiSettings.savedShort")', script)
        self.assertIn('default: translate("apiSettings.saveProvider")', script)
        self.assertNotRegex(script, r"saveApiSettingsButton\)[^\n]*saveApiSettingsButton\.textContent")
        self.assertRegex(script, r"saveApiProviderEditButton\)[^\n]*saveApiProviderEditButton\.textContent = providerText")
        self.assertNotRegex(script, r"saveCodexSettingsButton\)[^\n]*saveCodexSettingsButton\.textContent")
        self.assertIn('setSaveButtonText("saving")', script)
        self.assertIn('setSaveButtonText("saved")', script)
        self.assertIn('formatTranslation("apiSettings.savedSummary"', script)
        self.assertIn('fetch("/api/api-settings"', script)
        self.assertIn("openApiSettingsModal", script)
        self.assertNotIn("handleAuthSourceDoubleClick", script)
        self.assertNotIn('authSourceGroup?.addEventListener("dblclick"', script)
        self.assertIn('apiSourceSettingsButton?.addEventListener("click", () => call(methods, "openApiSettingsModal"))', script)
        self.assertIn('apiProviderList?.addEventListener("click"', script)
        self.assertIn('apiProviderSearch?.addEventListener("input", () => call(methods, "renderApiProviderList"))', script)
        self.assertIn('closest?.("[data-api-provider-sort]")', script)
        self.assertIn('call(methods, "moveApiProvider"', script)
        self.assertIn('call(methods, "selectApiProvider"', script)
        self.assertIn('editApiProviderButton?.addEventListener("click", () => call(methods, "editApiProvider"))', script)
        self.assertIn('copyApiProviderButton?.addEventListener("click", () => call(methods, "copyApiProvider"))', script)
        self.assertIn('sortApiProvidersButton?.addEventListener("click", () => call(methods, "toggleApiProviderSortMode"))', script)
        self.assertIn('deleteApiProviderButton?.addEventListener("click", () => call(methods, "confirmDeleteApiProvider", els.deleteApiProviderButton))', script)
        self.assertIn('cancelApiProviderEditButton?.addEventListener("click", () => call(methods, "cancelApiProviderEdit"))', script)
        self.assertIn('saveApiProviderEditButton?.addEventListener("click", () => call(methods, "saveApiProviderEdit"))', script)
        self.assertIn('apiKeyRevealButton?.addEventListener("pointerdown"', script)
        self.assertIn('apiKeyRevealButton?.addEventListener("pointerup"', script)
        self.assertIn('apiKeyRevealButton?.addEventListener("pointerleave"', script)
        self.assertIn('apiKeyRevealButton?.addEventListener("keydown"', script)
        self.assertIn('apiKeyRevealButton?.addEventListener("keyup"', script)
        self.assertIn('apiKey?.addEventListener("input"', script)
        self.assertIn('apiBaseUrl?.addEventListener("input"', script)
        self.assertIn('apiMode?.addEventListener("change"', script)
        self.assertNotIn("[els.codexMode, els.apiProviderName, els.apiBaseUrl, els.apiKey, els.apiMode, els.apiImageModel, els.apiImagesConcurrency]", script)
        self.assertIn("auth_source: authSource", script)
        self.assertIn("function backendForAuthSource", script)
        self.assertIn('return codexMode === "responses" ? "codex_responses" : "codex_images"', script)
        self.assertIn("requested_backend: requestedBackend", script)
        self.assertIn("function taskBackendValue", script)
        self.assertIn("function taskApiProviderLabel", script)
        self.assertIn("function taskBackendLabel", script)
        self.assertIn("const backend = taskBackendValue(task)", script)
        self.assertIn("const provider = taskApiProviderLabel(task)", script)
        self.assertIn("|| task?.provider_id", script)
        self.assertIn("|| task?.provider", script)
        self.assertNotIn('if (!providerId) return "";', script)
        self.assertIn('if (backend === "codex_responses") return "Codex Responses"', script)
        self.assertIn('if (backend === "openai_responses") return "API Responses"', script)
        self.assertIn('return [backendLabel, provider].filter(Boolean).join(" · ")', script)
        self.assertIn('payload.endpoint = action === "edit" ? "/images/edits" : "/images/generations"', script)
        self.assertIn('payload.endpoint = "/responses"', script)
        self.assertIn("payload.main_model = params.main_model", script)
        self.assertIn('payload.codex_mode = codexMode', script)
        self.assertIn('form.append("codex_mode", currentCodexMode())', script)
        self.assertIn('form.append("api_mode", currentApiMode())', script)
        self.assertIn('form.append("api_provider_id", currentApiProviderId())', script)
        self.assertIn('form.append("web_search", "true")', script)
        self.assertIn("params.web_search = true", script)
        self.assertIn("payload.api_provider_name = currentApiProviderLabel()", script)
        self.assertIn("webui_api_provider_name", script)
        self.assertIn("api_provider_name: request.api_provider_name", script)
        self.assertIn("images_concurrency: normalizeApiImagesConcurrency(provider.images_concurrency)", script)
        self.assertIn("images_concurrency: normalizeApiImagesConcurrency(els.apiImagesConcurrency?.value)", script)
        self.assertIn("return Math.min(32, Math.max(1, parsed));", script)
        self.assertIn("params.api_images_concurrency = currentApiImagesConcurrency()", script)
        self.assertIn("item.images_concurrency = provider.images_concurrency", script)
        self.assertNotIn("api_image_model: currentApiImageModel()", script)
        self.assertNotIn("api_key: currentApiKey()", script)
        self.assertNotIn("api_key: activeApiProvider", script)
        self.assertIn(".api-provider-list", styles)
        self.assertIn(".api-provider-choice-grid", styles)
        self.assertIn(".api-provider-search", styles)
        self.assertIn(".api-provider-choice", styles)
        self.assertIn(".api-provider-add-card", styles)
        self.assertIn(".api-provider-detail-panel", styles)
        self.assertIn(".api-provider-detail-grid", styles)
        self.assertIn(".api-provider-detail-actions", styles)
        self.assertIn(".api-provider-section-title", styles)
        self.assertIn(".api-provider-editor", styles)
        self.assertIn(".api-request-endpoint-preview", styles)
        self.assertIn(".compact-api-settings-grid", styles)
        self.assertRegex(styles, r"\.api-provider-section-header\s*\{[^}]*justify-content:\s*space-between")
        self.assertRegex(styles, r"\.api-provider-editor-heading\s*\{[^}]*justify-content:\s*flex-start")
        self.assertRegex(styles, r"\.api-provider-detail-actions,\s*\.api-provider-editor-actions\s*\{[^}]*justify-content:\s*center")
        self.assertNotRegex(styles, r"\.api-provider-editor-actions\s*\{[^}]*justify-content:\s*flex-end")
        self.assertRegex(styles, r"\.api-provider-detail-actions \.ghost-button,\s*\.api-provider-detail-actions \.danger-button,[\s\S]*height:\s*40px")
        self.assertRegex(styles, r"\.api-provider-editor-actions \.ghost-button,\s*\.api-provider-editor-actions \.run-button\s*\{[^}]*border-radius:\s*8px")
        self.assertRegex(styles, r"\.api-provider-choice-grid\s*\{[^}]*grid-template-columns:\s*repeat\(2,\s*minmax\(0,\s*1fr\)\)")
        self.assertNotRegex(styles, r"\.api-provider-choice-grid\s*\{[^}]*max-height:")
        self.assertRegex(styles, r"\.api-provider-choice-grid\.is-long-list\s*\{[^}]*max-height:\s*min\(320px,\s*38vh\)")
        self.assertRegex(styles, r"\.api-provider-choice-grid\.is-long-list\s*\{[^}]*overflow-y:\s*auto")
        self.assertRegex(styles, r"\.api-provider-choice-grid\.is-long-list\s*\{[^}]*overflow-x:\s*hidden")
        self.assertRegex(styles, r"\.api-provider-choice-grid\.is-long-list\s*\{[^}]*overscroll-behavior:\s*contain")
        self.assertRegex(styles, r"\.api-provider-search-empty\s*\{[^}]*grid-column:\s*1\s*/\s*-1")
        self.assertRegex(styles, r"\.api-provider-section\.editing\s*\{[^}]*display:\s*none")
        self.assertRegex(styles, r"\.api-provider-editor\s+\.api-provider-name-field\s*\{[^}]*grid-column:\s*1\s*/\s*-1")
        self.assertRegex(styles, r"\.api-request-endpoint-preview\s*\{[^}]*grid-column:\s*1\s*/\s*-1")
        self.assertRegex(styles, r"\.api-settings-grid\s*\{[^}]*align-items:\s*start")
        self.assertRegex(styles, r"\.api-mode-field\s*\{[^}]*grid-template-columns:\s*minmax\(280px,\s*320px\)")
        self.assertRegex(styles, r"\.api-mode-field\s*\{[^}]*justify-content:\s*center")
        self.assertRegex(styles, r"\.api-mode-field \.radio-group\s*\{[^}]*--segmented-control-height:\s*28px")
        self.assertRegex(styles, r"\.api-mode-field \.radio-group\s*\{[^}]*justify-self:\s*center")
        self.assertRegex(styles, r"\.api-mode-field \.segmented-indicator\s*\{[^}]*box-shadow:\s*none")
        self.assertRegex(styles, r"\.api-mode-field \.radio-group\.segmented-indicator-host \.radio-btn\.active\s*\{[^}]*color:\s*var\(--primary-strong\)")
        self.assertRegex(styles, r"\.api-provider-list\s*\{[^}]*display:\s*contents")
        self.assertNotRegex(styles, r"\.api-provider-list\s*\{[^}]*overflow-x:\s*auto")
        self.assertRegex(styles, r"\.api-provider-choice\.active\s*\{[^}]*background:\s*var\(--primary\)")
        self.assertRegex(styles, r"\.api-provider-choice\.active\s*\{[^}]*color:\s*var\(--primary-foreground\)")
        self.assertRegex(styles, r"\.api-provider-choice\.active span\s*\{[^}]*color:\s*color-mix\(in srgb,\s*var\(--primary-foreground\)\s*82%,\s*transparent\)")
        self.assertRegex(styles, r"\.api-provider-detail-grid\s*\{[^}]*grid-template-columns:\s*repeat\(2,\s*minmax\(0,\s*1fr\)\)")
        self.assertRegex(styles, r"\.api-provider-editor\.hidden\s*,\s*\.api-provider-detail-panel\.hidden\s*\{[^}]*display:\s*none")
        self.assertIn("const MIN_SYSTEM_SETTINGS_MODAL_EDGE = 30", script)
        self.assertIn("function positionSystemSettingsModal", script)
        self.assertIn("function animateSystemSettingsPanelHeight", script)
        self.assertIn("function systemSettingsTargetHeight", script)
        self.assertIn("window.innerHeight", script)
        self.assertIn("--system-settings-modal-top", script)
        self.assertIn("style.removeProperty(\"--system-settings-modal-top\")", script)
        self.assertIn("const wasHidden = els.systemSettingsModal?.classList.contains(\"hidden\") ?? true", script)
        self.assertIn("panel.scrollHeight", script)
        self.assertIn("(prefers-reduced-motion: reduce)", script)
        self.assertRegex(styles, r"\.api-settings-grid\s*\{[^}]*grid-template-columns:\s*minmax\(0,\s*1fr\)")
        self.assertRegex(styles, r"\.compact-api-settings-grid > \.api-provider-name-field,[\s\S]*?\.compact-api-settings-grid > \.api-key-field\s*\{[^}]*display:\s*grid")
        self.assertRegex(styles, r"\.compact-api-settings-grid > \.api-provider-name-field,[\s\S]*?\.compact-api-settings-grid > \.api-key-field\s*\{[^}]*grid-template-columns:\s*86px\s+minmax\(0,\s*1fr\)")
        self.assertRegex(styles, r"\.api-advanced-settings\s*\{[^}]*grid-column:\s*1\s*/\s*-1")
        self.assertRegex(styles, r"\.api-advanced-settings > summary\s*\{[^}]*display:\s*flex")
        self.assertRegex(styles, r"\.api-advanced-settings-summary\s*\{[^}]*margin-left:\s*auto")
        self.assertRegex(styles, r"\.api-advanced-settings-body\s*\{[^}]*grid-template-columns:\s*repeat\(2,\s*minmax\(0,\s*1fr\)\)")
        self.assertRegex(styles, r"\.api-advanced-settings\[open\] \.api-advanced-settings-chevron\s*\{[^}]*transform:")
        self.assertRegex(styles, r"@media\s*\(max-width:\s*620px\)\s*\{[\s\S]*?\.api-settings-grid\s*\{[^}]*grid-template-columns:\s*minmax\(0,\s*1fr\)")
        self.assertRegex(styles, r"@media\s*\(max-width:\s*620px\)\s*\{[\s\S]*?\.api-advanced-settings-body\s*\{[^}]*grid-template-columns:\s*minmax\(0,\s*1fr\)")
        self.assertRegex(styles, r"\.api-key-input-wrap\s*\{[^}]*position:\s*relative")
        self.assertRegex(styles, r"\.api-key-input-wrap \.control\s*\{[^}]*padding-right:\s*40px")
        self.assertRegex(styles, r"\.api-key-reveal-button\s*\{[^}]*position:\s*absolute")
        self.assertRegex(styles, r"\.api-key-reveal-button\s*\{[^}]*right:\s*6px")
        self.assertRegex(styles, r"#apiImagesConcurrency\s*\{[^}]*appearance:\s*textfield")
        self.assertRegex(styles, r"#apiImagesConcurrency::-webkit-outer-spin-button,\s*#apiImagesConcurrency::-webkit-inner-spin-button\s*\{[^}]*-webkit-appearance:\s*none")
        self.assertRegex(styles, r"#systemSettingsModal\s*\{[^}]*--system-settings-modal-top:\s*30px")
        self.assertRegex(styles, r"#systemSettingsModal\s*\{[^}]*align-items:\s*flex-start")
        self.assertRegex(styles, r"#systemSettingsModal\s*\{[^}]*overflow:\s*auto")
        self.assertRegex(styles, r"#systemSettingsModal\s*\{[^}]*padding-block:\s*var\(--system-settings-modal-top,\s*30px\)\s+30px")
        self.assertRegex(styles, r"\.system-settings-modal-panel\s*\{[^}]*padding:\s*22px\s+28px\s+24px")
        self.assertRegex(styles, r"\.system-settings-modal-panel\s*>\s*\.modal-heading\s*\{[^}]*position:\s*relative")
        self.assertRegex(styles, r"\.system-settings-modal-panel\s*>\s*\.modal-heading\s*\{[^}]*justify-content:\s*center")
        self.assertRegex(styles, r"\.system-settings-modal-panel\s*>\s*\.modal-heading\s*\{[^}]*min-height:\s*44px")
        self.assertRegex(styles, r"\.system-settings-modal-panel\s*>\s*\.modal-heading\s*\{[^}]*margin-bottom:\s*16px")
        self.assertRegex(styles, r"\.system-settings-modal-panel\s*>\s*\.modal-heading\s*\{[^}]*text-align:\s*center")
        self.assertRegex(styles, r"\.system-settings-modal-panel\s*>\s*\.modal-heading\s+\.drawer-close-button\s*\{[^}]*position:\s*absolute")
        self.assertRegex(styles, r"\.system-settings-section\s*\{[^}]*padding-right:\s*0")
        self.assertNotIn(".system-settings-section-heading", styles)
        self.assertRegex(styles, r"\.system-settings-tabs\s*\{[^}]*grid-template-columns:\s*repeat\(5,\s*minmax\(0,\s*1fr\)\)")
        self.assertRegex(styles, r"\.system-settings-tabs\s*\{[^}]*--segmented-indicator-radius:\s*999px")
        self.assertRegex(styles, r"\.system-settings-tab\.active\s*\{[^}]*color:\s*var\(--primary-foreground\)")
        self.assertRegex(styles, r"\.system-settings-tabs\s+\.segmented-indicator\s*\{[^}]*border-radius:\s*999px")
        self.assertIn(".codex-channel-notes", styles)
        self.assertIn(".codex-channel-note.active", styles)
        self.assertIn(".codex-channel-current", styles)
        self.assertRegex(styles, r"\.api-provider-section-header\s*\{[^}]*justify-content:\s*space-between")
        self.assertRegex(styles, r"\.api-provider-sort-toggle\s*\{[^}]*min-width:\s*72px")
        self.assertRegex(styles, r"\.api-provider-list\.is-sorting\s*\{[^}]*display:\s*grid")
        self.assertRegex(styles, r"\.api-provider-sort-row\s*\{[^}]*grid-template-columns:\s*minmax\(0,\s*1fr\)\s+auto")
        self.assertRegex(styles, r"\.api-provider-sort-button\s*\{[^}]*min-width:\s*48px")
        self.assertRegex(styles, r"\.model-tool-row\s*\{[^}]*grid-template-columns:\s*minmax\(0,\s*1fr\)\s+minmax\(104px,\s*max-content\)")
        self.assertIn(".web-search-toggle", styles)
        self.assertIn(".web-search-field.is-disabled", styles)
        self.assertIn(".api-settings-feedback.ok", styles)
        self.assertIn(".api-settings-feedback.error", styles)
        self.assertIn(".api-settings-feedback.running", styles)
        self.assertRegex(styles, r"\.api-settings-feedback:empty\s*\{[^}]*display:\s*none")
        self.assertRegex(styles, r"\.settings-action-status\s*\{[^}]*flex:\s*1 1 auto")
        self.assertRegex(styles, r"\.settings-action-status\s*\{[^}]*white-space:\s*nowrap")
        self.assertRegex(styles, r"\.settings-action-status:empty\s*\{[^}]*display:\s*none")
        self.assertRegex(styles, r"\.settings-modal-actions\s+\.run-button\s*\{[^}]*justify-content:\s*center")
        self.assertRegex(styles, r"\.settings-modal-actions\s+\.run-button\s*\{[^}]*text-align:\s*center")
    def test_primary_panel_close_buttons_use_consistent_x_button(self) -> None:
        html = Path("codex_image/webui/static/index.html").read_text(encoding="utf-8")
        styles = Path("codex_image/webui/static/styles.css").read_text(encoding="utf-8")

        expected_buttons = {
            "archiveModalClose": "关闭会话归档面板",
            "systemSettingsModalClose": "关闭系统设置面板",
            "imageEditorClose": "关闭编辑输入图片面板",
            "galleryDrawerClose": "关闭公用图库面板",
            "addToGalleryClose": "关闭添加到图库面板",
        }
        for button_id, aria_label in expected_buttons.items():
            with self.subTest(button_id=button_id):
                self.assertCloseButtonUsesConsistentX(html, button_id, aria_label)

        self.assertNotIn('class="ghost-button text-sm" type="button">关闭</button>', html)
        self.assertRegex(styles, r"\.drawer-close-button\s*\{[^}]*flex:\s*0 0 44px")
        self.assertRegex(styles, r"\.drawer-close-button\s*\{[^}]*min-width:\s*44px")
    def test_output_quantity_uses_button_group_limited_to_four(self) -> None:
        html = Path("codex_image/webui/static/index.html").read_text(encoding="utf-8")
        script = self._frontend_script_source()

        self.assertIn('id="quantityGroup"', html)
        self.assertNotIn("<span>数量 n</span>", html)
        self.assertNotRegex(html, r'id="nInput"[^>]*type="range"')
        self.assertRegex(html, r'id="quantityGroup"[\s\S]*data-val="1"[^>]*>1')
        self.assertRegex(html, r'id="quantityGroup"[\s\S]*data-val="4"[^>]*>4')
        self.assertRegex(html, r'<select id="nInput" class="hidden">[\s\S]*<option value="1" selected>1</option>')
        self.assertIn('form.append("n"', script)
        self.assertNotIn("nDecrease", html)
        self.assertNotIn("nIncrease", html)
    def test_output_sliders_match_theme(self) -> None:
        html = Path("codex_image/webui/static/index.html").read_text(encoding="utf-8")
        script = self._frontend_script_source()
        styles = Path("codex_image/webui/static/styles.css").read_text(encoding="utf-8")

        self.assertNotIn("range-control quantity-range", html)
        self.assertNotIn('id="nInput" class="slider"', html)
        self.assertIn('id="outputFormatGroup"', html)
        self.assertIn('id="compressionPopover"', html)
        self.assertIn('class="compression-popover hidden"', html)
        self.assertIn('role="dialog"', html)
        self.assertIn('id="compressionField"', html)
        self.assertIn("range-control compression-range", html)
        self.assertIn("range-value", html)
        self.assertIn("updateRangeProgress", script)
        self.assertIn("--range-progress", script)
        self.assertIn("compressionEnabled", script)
        self.assertIn("openCompressionPopover", script)
        self.assertIn("closeCompressionPopover", script)
        self.assertIn("handleOutputFormatDoubleClick", script)
        self.assertIn('addEventListener("dblclick", handleOutputFormatDoubleClick)', script)
        self.assertIn('event.key === "Escape"', script)
        self.assertIn('els.compressionPopover.classList.add("hidden")', script)
        self.assertNotIn('els.compressionField.classList.toggle("hidden"', script)
        self.assertNotIn("format-hidden", html)
        self.assertNotIn("format-hidden", script)
        self.assertNotIn("PNG 不适用", script)
        self.assertRegex(styles, r"\.range-control\s*\{[^}]*--range-fill:\s*var\(--primary\)")
        self.assertRegex(styles, r"\.output-format-field\s*\{[^}]*position:\s*relative")
        self.assertRegex(styles, r"\.compression-popover\s*\{[^}]*position:\s*absolute")
        self.assertNotRegex(styles, r"\.compression-range\.format-hidden")
        self.assertRegex(styles, r"\.compression-range\s*\{[^}]*display:\s*grid")
        self.assertRegex(styles, r"\.compression-range\s*\{[^}]*grid-template-columns:\s*auto minmax\(160px,\s*1fr\) auto")
        self.assertRegex(styles, r"\.range-value\s*\{[^}]*border-radius:\s*999px")
        self.assertRegex(styles, r"input\[type=range\]\.slider::-webkit-slider-thumb\s*\{[^}]*border:\s*5px solid var\(--range-fill\)")
    def test_output_ratio_layout_is_full_width_and_pairs_portrait_landscape(self) -> None:
        html = Path("codex_image/webui/static/index.html").read_text(encoding="utf-8")
        styles = Path("codex_image/webui/static/styles.css").read_text(encoding="utf-8")

        self.assertRegex(html, r'<div class="field full-width ratio-field">[\s\S]*id="ratioGroup"')
        self.assertRegex(styles, r"\.ratio-group\s*\{[^}]*grid-template-columns:\s*repeat\(6,\s*minmax\(0,\s*1fr\)\)")
        self.assertRegex(styles, r"\.ratio-group\s*\{[^}]*grid-template-rows:\s*repeat\(2,\s*30px\)")
        self.assertRegex(styles, r"\.ratio-group\s+\.radio-btn\s*\{[^}]*transform:\s*scale\(0\.985\)")
        self.assertRegex(styles, r"\.ratio-group\s+\.radio-btn\.active\s*\{[^}]*transform:\s*scale\(1\)")
        self.assertRegex(styles, r"\.radio-btn\s*\{[^}]*transition:\s*[\s\S]*background-color var\(--motion-base\)")
        self.assertRegex(styles, r"@media \(prefers-reduced-motion:\s*reduce\)\s*\{[\s\S]*\.ratio-group\s+\.radio-btn\s*\{[^}]*transform:\s*none")
        self.assertRegex(styles, r"\.ratio-group\s+\.radio-btn\[data-val=\"1:1\"\]\s*\{[^}]*grid-row:\s*1\s*/\s*3")
        for value, column, row in (
            ("4:5", 2, 1),
            ("5:4", 2, 2),
            ("3:4", 3, 1),
            ("4:3", 3, 2),
            ("2:3", 4, 1),
            ("3:2", 4, 2),
            ("9:16", 5, 1),
            ("16:9", 5, 2),
            ("9:21", 6, 1),
            ("21:9", 6, 2),
        ):
            self.assertRegex(styles, rf"\.ratio-group\s+\.radio-btn\[data-val=\"{value}\"\]\s*\{{[^}}]*grid-column:\s*{column}")
            self.assertRegex(styles, rf"\.ratio-group\s+\.radio-btn\[data-val=\"{value}\"\]\s*\{{[^}}]*grid-row:\s*{row}")
    def test_size_controls_keep_mode_specific_rows_above_ratio(self) -> None:
        html = Path("codex_image/webui/static/index.html").read_text(encoding="utf-8")

        self.assertRegex(
            html,
            r'<div class="field orientation-field">[\s\S]*id="orientationGroup"[\s\S]*</div>\s*'
            r'<div class="field resolution-field">[\s\S]*id="resolutionGroup"[\s\S]*</div>\s*'
            r'<div id="customSize" class="custom-size hidden"[\s\S]*id="customWidth"[\s\S]*id="customHeight"[\s\S]*</div>\s*'
            r'<div class="field full-width ratio-field">[\s\S]*id="ratioGroup"',
        )
        self.assertRegex(
            html,
            r'<div class="field-pair full-width quantity-quality-row">[\s\S]*'
            r'<div class="field quality-field">[\s\S]*id="quality"[\s\S]*</div>\s*'
            r'<div class="field quantity-field">[\s\S]*id="quantityGroup"',
        )
    def test_button_radio_groups_are_not_wrapped_by_labels(self) -> None:
        html = Path("codex_image/webui/static/index.html").read_text(encoding="utf-8")

        for label_html in re.findall(r"<label\b[\s\S]*?</label>", html):
            self.assertNotIn('class="radio-group"', label_html)
            self.assertNotIn('class="radio-btn"', label_html)
    def test_resolution_and_orientation_use_button_groups(self) -> None:
        html = Path("codex_image/webui/static/index.html").read_text(encoding="utf-8")
        script = self._frontend_script_source()
        styles = Path("codex_image/webui/static/styles.css").read_text(encoding="utf-8")

        self.assertIn('id="resolutionGroup"', html)
        self.assertRegex(html, r'id="resolutionGroup"[\s\S]*data-val="standard"[^>]*>1K')
        self.assertRegex(html, r'<select id="resolution" class="hidden">[\s\S]*<option value="standard" selected>1K</option>')
        resolution_controls = re.search(r'id="resolutionGroup"[\s\S]*?<select id="resolution" class="hidden">[\s\S]*?</select>', html)
        self.assertIsNotNone(resolution_controls)
        self.assertNotIn('data-val="auto"', resolution_controls.group(0))
        self.assertNotIn('<option value="auto"', resolution_controls.group(0))
        self.assertIn('data-val="standard"', html)
        self.assertIn('data-val="2k"', html)
        self.assertIn('data-val="4k"', html)
        self.assertRegex(html, r'<select id="resolution" class="hidden">')
        self.assertRegex(html, r'id="orientationGroup"[\s\S]*data-val="square"[\s\S]*orientation-option-icon-square[\s\S]*data-i18n="output\.square"[\s\S]*方形')
        self.assertRegex(html, r'id="orientationGroup"[\s\S]*data-val="portrait"[\s\S]*orientation-option-icon-portrait[\s\S]*data-i18n="output\.portrait"[\s\S]*竖图')
        self.assertRegex(html, r'id="orientationGroup"[\s\S]*data-val="landscape"[\s\S]*orientation-option-icon-landscape[\s\S]*data-i18n="output\.landscape"[\s\S]*横图')
        self.assertIn('class="orientation-option-icon orientation-option-icon-square"', html)
        orientation_controls = re.search(r'id="orientationGroup"[\s\S]*?<select id="orientation" class="hidden">[\s\S]*?</select>', html)
        self.assertIsNotNone(orientation_controls)
        self.assertNotIn('data-val="auto"', orientation_controls.group(0))
        self.assertNotIn('<option value="auto"', orientation_controls.group(0))
        self.assertRegex(styles, r"#orientationGroup \.radio-btn\s*\{[^}]*gap:\s*4px")
        self.assertRegex(styles, r"\.orientation-option-icon\s*\{[^}]*width:\s*12px")
        self.assertRegex(styles, r"\.orientation-option-icon\s*\{[^}]*stroke:\s*currentColor")
        self.assertIn('DEFAULT_RESOLUTION = "standard"', script)
        self.assertIn('DEFAULT_RATIO = "1:1"', script)
        self.assertIn('DEFAULT_ORIENTATION = "square"', script)
        self.assertIn("syncRatioAndOrientation", script)
    def test_background_control_is_removed_and_quantity_sits_with_quality(self) -> None:
        html = Path("codex_image/webui/static/index.html").read_text(encoding="utf-8")
        script = self._frontend_script_source()
        styles = Path("codex_image/webui/static/styles.css").read_text(encoding="utf-8")

        self.assertNotIn('id="background"', html)
        self.assertNotIn("<span>背景</span>", html)
        self.assertNotIn("els.background", script)
        self.assertNotIn('form.append("background"', script)
        self.assertRegex(html, r'class="field-pair full-width quantity-quality-row"[\s\S]*id="quality"[\s\S]*id="quantityGroup"')
        self.assertRegex(styles, r"\.field-pair\s*\{[^}]*grid-template-columns:\s*minmax\(0,\s*1fr\) minmax\(0,\s*1fr\)")
    def test_custom_size_panel_is_inline_mode_with_validation(self) -> None:
        html = Path("codex_image/webui/static/index.html").read_text(encoding="utf-8")
        script = self._frontend_script_source()
        styles = Path("codex_image/webui/static/styles.css").read_text(encoding="utf-8")

        self.assertIn('id="settingsGrid"', html)
        self.assertRegex(html, r'class="field-group full-width custom-size-control"[\s\S]*id="sizeModeGroup"[\s\S]*data-custom-size-mode="preset"[\s\S]*data-custom-size-mode="custom"')
        self.assertRegex(
            html,
            r'class="field-group full-width custom-size-control"[\s\S]*id="customSizeToggle"[\s\S]*</div>\s*'
            r'<div class="field orientation-field">[\s\S]*id="orientationGroup"[\s\S]*</div>\s*'
            r'<div class="field resolution-field">[\s\S]*id="resolutionGroup"[\s\S]*</div>\s*'
            r'<div id="customSize" class="custom-size hidden"[\s\S]*class="custom-size-main"[\s\S]*class="field custom-ratio-field"',
        )
        self.assertRegex(html, r'id="customSizeToggle" class="hidden"')
        custom_ratio_markup = re.search(r'<div class="field custom-ratio-field">[\s\S]*?<p id="customRatioHint"[^>]*>[^<]*</p>\s*</div>', html)
        self.assertIsNotNone(custom_ratio_markup)
        self.assertRegex(custom_ratio_markup.group(0), r'<span[^>]*>比例锁定（可选）</span>[\s\S]*class="custom-measure-row custom-ratio-control"')
        self.assertRegex(custom_ratio_markup.group(0), r'<label class="custom-measure-label" for="customRatioWidth"[^>]*>宽</label>[\s\S]*id="customRatioWidth"')
        self.assertRegex(custom_ratio_markup.group(0), r'id="customRatioWidth"[\s\S]*class="control custom-ratio-digit"')
        self.assertRegex(custom_ratio_markup.group(0), r'id="customRatioWidth"[^>]*type="text"[^>]*inputmode="numeric"[^>]*maxlength="1"[^>]*pattern="\[1-9\]"')
        self.assertRegex(custom_ratio_markup.group(0), r'<span class="custom-ratio-separator"[^>]*>:</span>')
        self.assertRegex(custom_ratio_markup.group(0), r'<label class="custom-measure-label" for="customRatioHeight"[^>]*>高</label>[\s\S]*id="customRatioHeight"')
        self.assertRegex(custom_ratio_markup.group(0), r'id="customRatioHeight"[\s\S]*class="control custom-ratio-digit"')
        self.assertRegex(custom_ratio_markup.group(0), r'id="customRatioHeight"[^>]*type="text"[^>]*inputmode="numeric"[^>]*maxlength="1"[^>]*pattern="\[1-9\]"')
        self.assertIn('aria-label="自定义宽高比宽度"', custom_ratio_markup.group(0))
        self.assertIn('aria-label="自定义宽高比高度"', custom_ratio_markup.group(0))
        self.assertNotIn('placeholder="宽"', custom_ratio_markup.group(0))
        self.assertNotIn('placeholder="高"', custom_ratio_markup.group(0))
        self.assertRegex(custom_ratio_markup.group(0), r'id="customRatioHint" class="custom-ratio-hint"[\s\S]*留空则自由宽高 · 填满后同步')
        custom_size_markup = re.search(r'<div id="customSize" class="custom-size hidden"[\s\S]*?</div>\s*<div class="field full-width ratio-field">', html)
        self.assertIsNotNone(custom_size_markup)
        self.assertRegex(custom_size_markup.group(0), r'class="custom-size-main"[\s\S]*class="custom-size-header"[\s\S]*<span[^>]*>像素尺寸</span>')
        self.assertRegex(custom_size_markup.group(0), r'class="custom-measure-row custom-size-row"')
        self.assertRegex(custom_size_markup.group(0), r'<label class="custom-measure-label" for="customWidth"[^>]*>宽度</label>[\s\S]*id="customWidth"')
        self.assertRegex(custom_size_markup.group(0), r'id="customWidth"[\s\S]*id="swapCustomSizeButton"[\s\S]*<label class="custom-measure-label" for="customHeight"[^>]*>高度</label>[\s\S]*id="customHeight"[\s\S]*id="customSizeHint"')
        self.assertRegex(custom_size_markup.group(0), r'class="field custom-ratio-field"[\s\S]*id="customRatioWidth"[\s\S]*id="customRatioHeight"')
        self.assertNotIn('id="lockCustomRatioButton"', custom_size_markup.group(0))
        self.assertNotIn("<span>px</span>", custom_size_markup.group(0))
        self.assertIn("单位 px · 16-3840 · 16倍数 · ≤3:1", custom_size_markup.group(0))
        self.assertNotIn('id="lockCustomRatioButton"', html)
        self.assertIn('aria-label="交换宽高"', html)
        self.assertNotIn('class="switch"', html)
        self.assertNotIn('class="slider round"', html)
        self.assertIn("settingsGrid: document.querySelector", script)
        self.assertIn("sizeModeGroup: document.querySelector", script)
        self.assertIn("customRatioWidth: document.querySelector", script)
        self.assertIn("customRatioHeight: document.querySelector", script)
        self.assertIn("customRatioFromImageButton: document.querySelector", script)
        self.assertIn("swapCustomSizeButton: document.querySelector", script)
        self.assertIn("customSizeHint: document.querySelector", script)
        self.assertIn("function setCustomSizeMode", script)
        self.assertIn("function handleSizeModeEvent", script)
        self.assertIn("function handleCustomRatioInput", script)
        self.assertIn("async function applyFirstReferenceImageAspectRatio", script)
        self.assertIn("function updateCustomRatioReferenceButtonState", script)
        self.assertIn("function singleDigitAspectRatioForDimensions", script)
        self.assertIn("function customAspectRatioFromManualInputs", script)
        self.assertIn("function sanitizeCustomRatioInput", script)
        self.assertIn("function handleCustomDimensionInput", script)
        self.assertIn("function updateCustomRatioFieldState", script)
        self.assertIn("function swapCustomSizeDimensions", script)
        self.assertIn("function populateCustomSizeFromCurrentPreset", script)
        self.assertIn("function customSizeValidationMessage", script)
        self.assertIn("const CUSTOM_SIZE_TRANSITION_MS = 220", script)
        self.assertIn("const CUSTOM_SIZE_HEIGHT_SNAP_TOLERANCE = 4", script)
        self.assertIn("const customSizeTransitionTimers = new WeakMap", script)
        self.assertIn("customSizeTransitionSeq: 0", script)
        self.assertIn("customSizeMode: null", script)
        self.assertIn("customAspectRatioLocked: false", script)
        self.assertIn("customAspectRatioValue: null", script)
        self.assertIn('customAspectRatioSource: "manual"', script)
        self.assertIn("function setCustomSizeModeLayout", script)
        self.assertIn("function measureCustomSizeModeHeight", script)
        self.assertIn("function transitionCustomSizeMode", script)
        self.assertIn("transitionCustomSizeMode(isCustom)", script)
        self.assertIn("Math.abs(targetHeight - fromHeight) <= CUSTOM_SIZE_HEIGHT_SNAP_TOLERANCE", script)
        self.assertIn("setStatus(customSizeError", script)
        self.assertRegex(styles, r"\.custom-size-control\s*\{[^}]*display:\s*grid")
        self.assertRegex(styles, r"\.settings-grid\s*\{[^}]*transition:\s*height var\(--motion-height\)")
        self.assertRegex(styles, r"\.settings-grid\.is-size-transitioning\s*\{[^}]*overflow:\s*hidden")
        self.assertRegex(styles, r"\.settings-grid\.is-size-transitioning\s*\{[^}]*will-change:\s*height")
        self.assertNotRegex(styles, r"\.custom-size\s*\{[^}]*position:\s*absolute")
        self.assertNotRegex(styles, r"\.custom-size::before\s*\{")
        self.assertRegex(styles, r"\.settings-grid\s*\{[^}]*--custom-size-mode-card-height:\s*175px")
        self.assertRegex(styles, r"\.custom-ratio-field\s*\{[^}]*display:\s*none")
        self.assertRegex(styles, r"\.custom-ratio-field\s*\{[^}]*grid-template-columns:\s*minmax\(0,\s*1fr\)")
        self.assertRegex(styles, r"\.custom-ratio-field\s*\{[^}]*align-content:\s*center")
        self.assertRegex(styles, r"\.custom-ratio-field\s*\{[^}]*gap:\s*8px")
        self.assertRegex(styles, r"\.custom-ratio-field\s*\{[^}]*padding-left:\s*20px")
        self.assertRegex(styles, r"\.custom-ratio-field\s*\{[^}]*border-left:\s*1px solid")
        self.assertNotRegex(styles, r"\.custom-ratio-field\s*\{[^}]*min-height:\s*var\(--custom-size-mode-card-height\)")
        self.assertNotRegex(styles, r"\.custom-ratio-field\s*\{[^}]*border:\s*1px solid var\(--line\)")
        self.assertNotRegex(styles, r"\.custom-ratio-field\s*\{[^}]*background:\s*var\(--surface-soft\)")
        self.assertRegex(styles, r"\.custom-measure-row\s*\{[^}]*display:\s*grid")
        self.assertRegex(styles, r"\.custom-measure-row\s*\{[^}]*--measure-label-width:\s*36px")
        self.assertRegex(styles, r"\.custom-measure-row\s*\{[^}]*--measure-input-width:\s*96px")
        self.assertRegex(styles, r"\.custom-measure-row\s*\{[^}]*grid-template-columns:[^}]*var\(--measure-label-width\)")
        self.assertRegex(styles, r"\.custom-measure-row\s*\{[^}]*justify-content:\s*start")
        self.assertRegex(styles, r"\.custom-measure-row\s*\{[^}]*width:\s*auto")
        self.assertRegex(styles, r"\.custom-measure-label\s*\{[^}]*justify-self:\s*end")
        self.assertRegex(styles, r"\.custom-measure-label\s*\{[^}]*font-size:\s*13px")
        self.assertRegex(styles, r"\.custom-measure-row\s*>\s*\.custom-measure-label:first-child\s*\{[^}]*justify-self:\s*start")
        self.assertNotRegex(styles, r"\.custom-ratio-control\s*\{[^}]*padding:")
        self.assertNotRegex(styles, r"\.custom-ratio-control\s*\{[^}]*border:")
        self.assertNotRegex(styles, r"\.custom-ratio-control\s*\{[^}]*background:")
        self.assertRegex(styles, r"\.custom-ratio-control\s*\{[^}]*--measure-input-width:\s*44px")
        self.assertRegex(styles, r"\.custom-ratio-control\s*\{[^}]*--measure-mid-width:\s*18px")
        self.assertRegex(styles, r"\.custom-ratio-digit\s*\{[^}]*width:\s*var\(--measure-input-width\)")
        self.assertRegex(styles, r"\.custom-ratio-header\s*\{[^}]*display:\s*flex")
        self.assertRegex(styles, r"\.custom-ratio-header\s*\{[^}]*min-height:\s*26px")
        self.assertRegex(styles, r"\.custom-ratio-header\s*>\s*span\s*\{[^}]*font-size:\s*12px")
        self.assertRegex(styles, r"\.custom-size-main\s*\{[^}]*display:\s*grid")
        self.assertRegex(styles, r"\.custom-size-main\s*\{[^}]*align-content:\s*center")
        self.assertRegex(styles, r"\.custom-size-header\s*\{[^}]*display:\s*flex")
        self.assertRegex(styles, r"\.custom-size-header\s*\{[^}]*min-height:\s*22px")
        self.assertRegex(styles, r"\.custom-size-header\s*>\s*span\s*\{[^}]*font-size:\s*14px")
        self.assertRegex(styles, r"\.custom-size-header\s*>\s*span\s*\{[^}]*font-weight:\s*600")
        self.assertRegex(styles, r"\.custom-ratio-hint\s*,\s*\.custom-size-hint\s*\{[^}]*font-size:\s*12px")
        self.assertRegex(styles, r"\.custom-ratio-image-button:disabled\s*\{[^}]*display:\s*none")
        self.assertRegex(styles, r"\.settings-grid\.custom-size-mode\s+\.custom-ratio-field\s*\{[^}]*display:\s*grid")
        self.assertRegex(styles, r"\.custom-size\s*\{[^}]*grid-template-columns:\s*minmax\(0,\s*1\.08fr\)\s+minmax\(242px,\s*0\.92fr\)")
        self.assertRegex(styles, r"\.custom-size\s*\{[^}]*align-items:\s*center")
        self.assertRegex(styles, r"\.custom-size\s*\{[^}]*min-height:\s*var\(--custom-size-mode-card-height\)")
        self.assertRegex(styles, r"\.custom-size\s*\{[^}]*max-height:\s*var\(--custom-size-mode-card-height\)")
        self.assertRegex(styles, r"\.custom-size\s*\{[^}]*padding:\s*18px 20px")
        self.assertRegex(styles, r"\.custom-size\s*\{[^}]*transition:[^}]*max-height var\(--motion-height\)")
        self.assertRegex(styles, r"\.custom-size\.custom-size-collapsed\s*\{[^}]*max-height:\s*0")
        self.assertRegex(styles, r"\.custom-size\.custom-size-collapsed\s*\{[^}]*opacity:\s*0")
        self.assertNotIn(".custom-size-field", styles)
        self.assertRegex(styles, r"\.custom-size-row\s*\{[^}]*--measure-input-width:\s*96px")
        self.assertRegex(styles, r"\.custom-size-icon-button\s*\{[^}]*width:\s*30px")
        self.assertRegex(styles, r"\.custom-size-icon-button\s*\{[^}]*justify-self:\s*center")
        self.assertNotRegex(styles, r"\.custom-size-actions\s*\{")
        self.assertRegex(styles, r"\.custom-ratio-field\.active\s*\{[^}]*border-left-color:")
        self.assertNotRegex(styles, r"\.custom-ratio-field\.active\s*\{[^}]*background:\s*var\(--primary-light\)")
        self.assertNotRegex(styles, r"\.custom-ratio-field\.active\s+\.custom-ratio-control")
        self.assertRegex(styles, r"\.custom-size-input\s*\{[^}]*width:\s*var\(--measure-input-width\)")
        self.assertRegex(styles, r"\.custom-size-input\s*\{[^}]*text-align:\s*center")
        self.assertRegex(styles, r"\.custom-size-input\s*\{[^}]*font-variant-numeric:\s*tabular-nums")
        self.assertRegex(styles, r"\.settings-grid\.custom-size-mode\s+\.resolution-field\s*,\s*\.settings-grid\.custom-size-mode\s+\.ratio-field\s*,\s*\.settings-grid\.custom-size-mode\s+\.orientation-field\s*\{[^}]*display:\s*none")
        self.assertRegex(styles, r"\.settings-grid\.custom-size-mode\s+\.custom-size\s*\{[^}]*grid-column:\s*1\s*/\s*-1")
        self.assertNotRegex(styles, r"\.settings-grid\.custom-size-mode\s+\.quantity-field\s*\{[^}]*grid-column:\s*1\s*/\s*-1")
        self.assertRegex(styles, r"@media \(prefers-reduced-motion:\s*reduce\)\s*\{[\s\S]*\.settings-grid\s*,\s*[\s\S]*\.custom-size\s*\{[\s\S]*transition:\s*none")
        self.assertRegex(styles, r"@media \(max-width:\s*640px\)\s*\{[\s\S]*\.custom-size\s*\{[^}]*grid-template-columns:\s*minmax\(0,\s*1fr\)")
    def test_custom_size_ratio_and_quantity_rows_are_balanced_halves(self) -> None:
        html = Path("codex_image/webui/static/index.html").read_text(encoding="utf-8")
        styles = Path("codex_image/webui/static/styles.css").read_text(encoding="utf-8")

        custom_ratio_markup = re.search(r'<div class="field custom-ratio-field">[\s\S]*?<p id="customRatioHint"[^>]*>[^<]*</p>\s*</div>', html)
        self.assertIsNotNone(custom_ratio_markup)
        self.assertRegex(custom_ratio_markup.group(0), r'class="custom-ratio-header">\s*<span[^>]*>比例锁定（可选）</span>\s*</div>')
        self.assertRegex(custom_ratio_markup.group(0), r'class="custom-measure-row custom-ratio-control"[\s\S]*id="customRatioFromImageButton"')
        self.assertRegex(custom_ratio_markup.group(0), r'id="customRatioFromImageButton"[^>]*disabled[^>]*aria-label="获取第一张参考图宽高比"')
        self.assertRegex(custom_ratio_markup.group(0), r"<span[^>]*>取首图</span>")
        self.assertIn("留空则自由宽高 · 填满后同步", custom_ratio_markup.group(0))

        self.assertRegex(styles, r"\.field-pair\s*\{[^}]*grid-template-columns:\s*minmax\(0,\s*1fr\) minmax\(0,\s*1fr\)")
        self.assertNotRegex(styles, r"\.quantity-quality-row\s*\{[^}]*1\.25fr")
        self.assertNotRegex(styles, r"\.quantity-quality-row\s*\{[^}]*0\.75fr")
        self.assertRegex(styles, r"\.custom-measure-row\s*\{[^}]*justify-content:\s*start")
        self.assertRegex(styles, r"\.custom-size\s*\{[^}]*grid-template-columns:\s*minmax\(0,\s*1\.08fr\)\s+minmax\(242px,\s*0\.92fr\)")
        self.assertRegex(styles, r"\.custom-ratio-control\s*\{[^}]*--measure-input-width:\s*44px")
        self.assertRegex(styles, r"\.custom-ratio-control\s*\{[^}]*grid-template-columns:\s*22px 44px 18px 22px 44px auto")
        self.assertRegex(styles, r"\.custom-ratio-image-button\s*\{[^}]*align-self:\s*center")
        self.assertRegex(styles, r"\.custom-size-row\s*\{[^}]*--measure-input-width:\s*96px")
        self.assertNotIn(".custom-size-field", styles)
    def test_custom_size_swap_button_exchanges_dimensions(self) -> None:
        node = shutil.which("node")
        if node is None:
            self.skipTest("node is required for frontend behavior checks")
        script = self._frontend_script_source()
        harness = "\n".join(
            [
                """
                const els = {
                  customWidth: { value: "768" },
                  customHeight: { value: "1280" },
                };
                let customSizeUpdated = 0;
                let pixelPreviewArg = "";
                let requestPreviewUpdated = 0;
                function updateCustomSize() { customSizeUpdated += 1; }
                function updatePixelPreview(size) { pixelPreviewArg = size; }
                function updateRequestPreview() { requestPreviewUpdated += 1; }
                """,
                self._extract_javascript_function(script, "swapCustomSizeDimensions"),
                """
                let prevented = false;
                swapCustomSizeDimensions({ preventDefault() { prevented = true; } });
                if (!prevented) throw new Error("expected swap click to prevent default");
                if (els.customWidth.value !== "1280" || els.customHeight.value !== "768") {
                  throw new Error(`expected swapped dimensions, got ${els.customWidth.value}x${els.customHeight.value}`);
                }
                if (customSizeUpdated !== 1) throw new Error("expected custom size state update");
                if (pixelPreviewArg !== "custom") throw new Error(`expected custom preview update, got ${pixelPreviewArg}`);
                if (requestPreviewUpdated !== 1) throw new Error("expected request preview update");
                """,
            ]
        )
        result = subprocess.run([node, "-e", harness], check=False, text=True, capture_output=True)

        self.assertEqual(result.returncode, 0, result.stderr)
    def test_custom_size_can_use_first_reference_image_ratio(self) -> None:
        node = shutil.which("node")
        if node is None:
            self.skipTest("node is required for frontend behavior checks")
        script = self._frontend_script_source()
        harness = "\n".join(
            [
                """
                const state = {
                  images: [],
                  customAspectRatioLocked: false,
                  customAspectRatioValue: null,
                  customAspectRatioSource: "manual",
                };
                const customRatioFieldClassList = new Set();
                const els = {
                  customRatioField: {
                    classList: {
                      toggle(name, active) {
                        if (active) customRatioFieldClassList.add(name);
                        else customRatioFieldClassList.delete(name);
                      },
                    },
                  },
                  customRatioFromImageButton: {
                    disabled: false,
                    setAttribute(name, value) { this[name] = value; },
                    removeAttribute(name) { delete this[name]; },
                  },
                  customWidth: { value: "1024" },
                  customHeight: { value: "1024" },
                  customRatioWidth: { value: "" },
                  customRatioHeight: { value: "" },
                  pixelPreview: { textContent: "" },
                };
                const statusMessages = [];
                function setStatus(message, type) { statusMessages.push([message, type]); }
                function customDimensionValue(input) {
                  const value = Number.parseInt(input?.value || "", 10);
                  return Number.isInteger(value) ? value : null;
                }
                const GPT_IMAGE_2_MIN_PIXELS = 655360;
                const GPT_IMAGE_2_MAX_PIXELS = 8294400;
                const GPT_IMAGE_2_MAX_LONG_SHORT_RATIO = 3;
                function customSizeValidationMessage(width = customDimensionValue(els.customWidth), height = customDimensionValue(els.customHeight)) {
                  if (width === null || height === null) return "请输入宽度和高度";
                  if (width < 16 || width > 3840 || height < 16 || height > 3840) return "宽高需在 16-3840 px 之间";
                  if (width % 16 !== 0 || height % 16 !== 0) return "宽高需为 16 的倍数";
                  if (Math.max(width, height) / Math.min(width, height) > GPT_IMAGE_2_MAX_LONG_SHORT_RATIO) return "长短边比例不能超过 3:1";
                  const totalPixels = width * height;
                  if (totalPixels < GPT_IMAGE_2_MIN_PIXELS || totalPixels > GPT_IMAGE_2_MAX_PIXELS) return "总像素需在 655,360-8,294,400 之间";
                  return "";
                }
                function updateCustomSize() {}
                function updatePixelPreview() {}
                function updateRequestPreview() { requestPreviewUpdated += 1; }
                let requestPreviewUpdated = 0;
                function sourcePreviewUrl(source) { return source.previewUrl || source.image_url || ""; }
                global.Image = class {
                  set src(value) {
                    this.naturalWidth = value.includes("wide") || value.includes("four-three") ? 1600 : 1024;
                    this.naturalHeight = value.includes("wide") ? 900 : value.includes("four-three") ? 1200 : 1536;
                    setTimeout(() => this.onload && this.onload(), 0);
                  }
                };
                """,
                self._extract_javascript_function(script, "sanitizeCustomRatioInput"),
                self._extract_javascript_function(script, "customRatioDigitValue"),
                self._extract_javascript_function(script, "customAspectRatioFromManualInputs"),
                self._extract_javascript_function(script, "normalizeAspectDimension"),
                self._extract_javascript_function(script, "updateCustomRatioFieldState"),
                self._extract_javascript_function(script, "setCustomAspectRatioFromManualInputs"),
                self._extract_javascript_function(script, "applyCustomAspectRatioFromWidth"),
                self._extract_javascript_function(script, "singleDigitAspectRatioForDimensions"),
                self._extract_javascript_function(script, "firstReferenceImageSource"),
                self._extract_javascript_function(script, "updateCustomRatioReferenceButtonState"),
                self._extract_javascript_function(script, "sourceUrlForAspectRatio"),
                self._extract_javascript_function(script, "loadImageDimensions"),
                self._extract_javascript_function(script, "applyCustomAspectRatioDigits"),
                self._extract_javascript_function(script, "applyFirstReferenceImageAspectRatio"),
                """
                updateCustomRatioReferenceButtonState();
                if (!els.customRatioFromImageButton.disabled) throw new Error("ratio image button should be disabled without images");
                state.images.push({ kind: "upload", previewUrl: "blob:tall" });
                updateCustomRatioReferenceButtonState();
                if (els.customRatioFromImageButton.disabled) throw new Error("ratio image button should enable with an image");
                applyFirstReferenceImageAspectRatio().then(() => {
                  if (els.customRatioWidth.value !== "2" || els.customRatioHeight.value !== "3") {
                    throw new Error(`expected 2:3 from first image, got ${els.customRatioWidth.value}:${els.customRatioHeight.value}`);
                  }
                  if (els.customHeight.value !== "1536") throw new Error(`expected derived height 1536, got ${els.customHeight.value}`);
                  if (!customRatioFieldClassList.has("active")) throw new Error("expected active custom ratio after taking image ratio");
                  if (requestPreviewUpdated !== 1) throw new Error("expected request preview update");
                  state.images = [{ kind: "asset", image_url: "/assets/wide.png" }];
                  return applyFirstReferenceImageAspectRatio();
                }).then(() => {
                  if (els.customRatioWidth.value !== "9" || els.customRatioHeight.value !== "5") {
                    throw new Error(`expected nearest single digit ratio 9:5, got ${els.customRatioWidth.value}:${els.customRatioHeight.value}`);
                  }
                  if (customSizeValidationMessage() !== "") {
                    throw new Error(`expected first-image ratio to keep custom size valid, got ${els.customWidth.value}x${els.customHeight.value}: ${customSizeValidationMessage()}`);
                  }
                  if (els.customWidth.value !== "1152" || els.customHeight.value !== "640") {
                    throw new Error(`expected nearest valid 9:5 dimensions 1152x640, got ${els.customWidth.value}x${els.customHeight.value}`);
                  }
                  els.customWidth.value = "240";
                  els.customHeight.value = "240";
                  state.images = [{ kind: "upload", previewUrl: "blob:four-three" }];
                  return applyFirstReferenceImageAspectRatio();
                }).then(() => {
                  if (els.customRatioWidth.value !== "4" || els.customRatioHeight.value !== "3") {
                    throw new Error(`expected 4:3 from first image, got ${els.customRatioWidth.value}:${els.customRatioHeight.value}`);
                  }
                  if (customSizeValidationMessage() !== "") {
                    throw new Error(`expected small custom size to be raised into valid range, got ${els.customWidth.value}x${els.customHeight.value}: ${customSizeValidationMessage()}`);
                  }
                  if (els.customWidth.value !== "960" || els.customHeight.value !== "720") {
                    throw new Error(`expected nearest valid 4:3 dimensions 960x720, got ${els.customWidth.value}x${els.customHeight.value}`);
                  }
                }).catch((error) => {
                  console.error(error);
                  process.exit(1);
                });
                """,
            ]
        )
        result = subprocess.run([node, "-e", harness], check=False, text=True, capture_output=True)

        self.assertEqual(result.returncode, 0, result.stderr)
    def test_custom_size_manual_ratio_preserves_aspect_ratio_when_dimensions_change(self) -> None:
        node = shutil.which("node")
        if node is None:
            self.skipTest("node is required for frontend behavior checks")
        script = self._frontend_script_source()
        harness = "\n".join(
            [
                """
                const state = { customAspectRatioLocked: false, customAspectRatioValue: null, customAspectRatioSource: "manual" };
                const customRatioFieldClassList = new Set();
                const els = {
                  customRatioField: {
                    classList: {
                      toggle(name, active) {
                        if (active) customRatioFieldClassList.add(name);
                        else customRatioFieldClassList.delete(name);
                      },
                      contains(name) { return customRatioFieldClassList.has(name); },
                    },
                  },
                  customWidth: { value: "1024" },
                  customHeight: { value: "1024" },
                  customRatioWidth: { value: "2x" },
                  customRatioHeight: { value: "3" },
                };
                function customDimensionValue(input) {
                  const value = Number.parseInt(input?.value || "", 10);
                  return Number.isInteger(value) ? value : null;
                }
                """,
                self._extract_javascript_function(script, "sanitizeCustomRatioInput"),
                self._extract_javascript_function(script, "customRatioDigitValue"),
                self._extract_javascript_function(script, "customAspectRatioFromManualInputs"),
                self._extract_javascript_function(script, "normalizeAspectDimension"),
                self._extract_javascript_function(script, "updateCustomRatioFieldState"),
                self._extract_javascript_function(script, "setCustomAspectRatioFromManualInputs"),
                self._extract_javascript_function(script, "applyCustomAspectRatioFromWidth"),
                self._extract_javascript_function(script, "handleCustomRatioInput"),
                self._extract_javascript_function(script, "handleCustomDimensionInput"),
                """
                handleCustomRatioInput(els.customRatioWidth);
                if (els.customRatioWidth.value !== "2") throw new Error(`expected single digit ratio width, got ${els.customRatioWidth.value}`);
                if (els.customRatioHeight.value !== "3") throw new Error(`expected ratio height 3, got ${els.customRatioHeight.value}`);
                if (!state.customAspectRatioLocked) throw new Error("expected manual ratio enabled");
                if (state.customAspectRatioValue !== 2 / 3) throw new Error(`unexpected ratio ${state.customAspectRatioValue}`);
                if (!customRatioFieldClassList.has("active")) throw new Error("expected active ratio field class");
                if (els.customHeight.value !== "1536") {
                  throw new Error(`expected ratio to derive height 1536, got ${els.customHeight.value}`);
                }
                els.customWidth.value = "2048";
                handleCustomDimensionInput(els.customWidth);
                if (els.customHeight.value !== "3072") {
                  throw new Error(`expected manual ratio height 3072, got ${els.customHeight.value}`);
                }
                els.customHeight.value = "1536";
                handleCustomDimensionInput(els.customHeight);
                if (els.customWidth.value !== "1024") {
                  throw new Error(`expected manual ratio width 1024, got ${els.customWidth.value}`);
                }
                els.customRatioHeight.value = "";
                handleCustomRatioInput(els.customRatioHeight);
                if (state.customAspectRatioLocked) throw new Error("clearing a ratio digit should disable manual ratio");
                if (customRatioFieldClassList.has("active")) throw new Error("expected inactive ratio field after clearing digit");
                els.customWidth.value = "1280";
                handleCustomDimensionInput(els.customWidth);
                if (els.customHeight.value !== "1536") throw new Error("unlocked ratio should not mutate height");
                """,
            ]
        )
        result = subprocess.run([node, "-e", harness], check=False, text=True, capture_output=True)

        self.assertEqual(result.returncode, 0, result.stderr)
    def test_custom_size_mode_prefills_current_preset_dimensions(self) -> None:
        node = shutil.which("node")
        if node is None:
            self.skipTest("node is required for frontend behavior checks")
        custom_size_source = Path("codex_image/webui/frontend/src/custom-size-controls.ts").read_text(encoding="utf-8")
        size_source = Path("codex_image/webui/frontend/src/size-presets.ts").read_text(encoding="utf-8")
        harness = "\n".join(
            [
                """
                const DEFAULT_RESOLUTION = "standard";
                const DEFAULT_RATIO = "1:1";
                const DEFAULT_ORIENTATION = "square";
                const RATIO_ORIENTATION = { "1:1": "square", "2:3": "portrait", "3:2": "landscape" };
                const RATIO_COUNTERPARTS = { "1:1": "1:1", "2:3": "3:2", "3:2": "2:3" };
                const ORIENTATION_DEFAULT_RATIOS = { square: "1:1", portrait: "2:3", landscape: "3:2" };
                const GPT_IMAGE_2_SIZE_PRESETS = {
                  standard: { "1:1": [1024, 1024], "2:3": [1024, 1536], "3:2": [1536, 1024] },
                  "2k": { "1:1": [2048, 2048], "2:3": [1344, 2016], "3:2": [2016, 1344] },
                  "4k": { "1:1": [2880, 2880], "2:3": [2336, 3504], "3:2": [3504, 2336] },
                };
                function Event(type) { this.type = type; }
                const els = {
                  customSizeToggle: { checked: false },
                  size: { value: "1344x2016" },
                  resolution: { value: "2k", dispatchEvent() {} },
                  ratio: { value: "2:3", dispatchEvent() {} },
                  orientation: { value: "portrait", dispatchEvent() {} },
                  customWidth: { value: "1024" },
                  customHeight: { value: "1024" },
                };
                let customSizeUpdated = 0;
                let pixelPreviewArg = "";
                let requestPreviewUpdated = 0;
                function updateCustomSize() { customSizeUpdated += 1; }
                function updatePixelPreview(size) { pixelPreviewArg = size; }
                function updateRequestPreview() { requestPreviewUpdated += 1; }
                """,
                self._extract_javascript_function(custom_size_source, "setCustomSizeMode"),
                self._extract_javascript_function(custom_size_source, "updateSizeFromPreset"),
                self._extract_javascript_function(custom_size_source, "populateCustomSizeFromCurrentPreset"),
                self._extract_javascript_function(custom_size_source, "sizeControlName"),
                self._extract_javascript_function(custom_size_source, "syncRatioAndOrientation"),
                self._extract_javascript_function(custom_size_source, "syncOrientationFromRatio"),
                self._extract_javascript_function(custom_size_source, "syncRatioFromOrientation"),
                self._extract_javascript_function(custom_size_source, "setSizeControlValue"),
                self._extract_javascript_function(size_source, "sizeForPreset"),
                self._extract_javascript_function(size_source, "presetDimensions"),
                """
                setCustomSizeMode(true);
                if (els.size.value !== "custom") {
                  throw new Error(`expected custom size mode, got ${els.size.value}`);
                }
                if (els.customWidth.value !== "1344" || els.customHeight.value !== "2016") {
                  throw new Error(`expected 2k portrait preset dimensions, got ${els.customWidth.value}x${els.customHeight.value}`);
                }
                if (customSizeUpdated !== 1) throw new Error("expected one custom size update");
                if (pixelPreviewArg !== "custom") throw new Error(`expected custom pixel preview, got ${pixelPreviewArg}`);
                if (requestPreviewUpdated !== 1) throw new Error("expected request preview update");
                els.customWidth.value = "1408";
                els.customHeight.value = "2048";
                updateSizeFromPreset();
                if (els.customWidth.value !== "1408" || els.customHeight.value !== "2048") {
                  throw new Error(`custom dimensions should not be overwritten while custom mode is active, got ${els.customWidth.value}x${els.customHeight.value}`);
                }
                """,
            ]
        )
        result = subprocess.run([node, "-e", harness], check=False, text=True, capture_output=True)

        self.assertEqual(result.returncode, 0, result.stderr)
    def test_custom_size_validation_rejects_invalid_dimensions(self) -> None:
        node = shutil.which("node")
        if node is None:
            self.skipTest("node is required for frontend behavior checks")
        script = Path("codex_image/webui/frontend/src/size-presets.ts").read_text(encoding="utf-8")
        harness = "\n".join(
            [
                """
                const els = {
                  customWidth: { value: "1024" },
                  customHeight: { value: "1024" },
                };
                const GPT_IMAGE_2_MIN_PIXELS = 655360;
                const GPT_IMAGE_2_MAX_PIXELS = 8294400;
                const GPT_IMAGE_2_MAX_LONG_SHORT_RATIO = 3;
                const translations = {
                  "output.customSizeRequired": "请输入宽度和高度",
                  "output.customSizeBounds": "宽高需在 16-3840 px 之间",
                  "output.customSizeMultiple": "宽高需为 16 的倍数",
                  "output.customSizeRatio": "长短边比例不能超过 3:1",
                  "output.customSizePixels": "总像素需在 655,360-8,294,400 之间",
                };
                function translate(key) { return translations[key] || key; }
                """,
                self._extract_javascript_function(script, "normalizeCustomDimension"),
                self._extract_javascript_function(script, "customDimensionValue"),
                self._extract_javascript_function(script, "customSizeValidationMessage"),
                """
                if (customSizeValidationMessage() !== "") {
                  throw new Error("expected default custom size to be valid");
                }
                els.customWidth.value = "";
                if (customSizeValidationMessage() !== "请输入宽度和高度") {
                  throw new Error(`expected empty value error, got ${customSizeValidationMessage()}`);
                }
                els.customWidth.value = "15";
                els.customHeight.value = "1024";
                if (customSizeValidationMessage() !== "宽高需在 16-3840 px 之间") {
                  throw new Error(`expected range error, got ${customSizeValidationMessage()}`);
                }
                els.customWidth.value = "1025";
                if (customSizeValidationMessage() !== "宽高需为 16 的倍数") {
                  throw new Error(`expected step error, got ${customSizeValidationMessage()}`);
                }
                els.customWidth.value = "3840";
                els.customHeight.value = "1024";
                if (customSizeValidationMessage() !== "长短边比例不能超过 3:1") {
                  throw new Error(`expected aspect ratio error, got ${customSizeValidationMessage()}`);
                }
                els.customWidth.value = "768";
                els.customHeight.value = "768";
                if (customSizeValidationMessage() !== "总像素需在 655,360-8,294,400 之间") {
                  throw new Error(`expected minimum pixel error, got ${customSizeValidationMessage()}`);
                }
                els.customWidth.value = "3840";
                els.customHeight.value = "3840";
                if (customSizeValidationMessage() !== "总像素需在 655,360-8,294,400 之间") {
                  throw new Error(`expected maximum pixel error, got ${customSizeValidationMessage()}`);
                }
                """,
            ]
        )
        result = subprocess.run([node, "-e", harness], check=False, text=True, capture_output=True)

        self.assertEqual(result.returncode, 0, result.stderr)
    def test_right_column_size_reference_panels_are_removed(self) -> None:
        html = Path("codex_image/webui/static/index.html").read_text(encoding="utf-8")

        self.assertNotIn("尺寸约束", html)
        self.assertNotIn("常用尺寸", html)
        self.assertNotIn('data-size=', html)
        self.assertNotIn("size-panels-container", html)
    def test_lightbox_is_fixed_overlay(self) -> None:
        styles = Path("codex_image/webui/static/styles.css").read_text(encoding="utf-8")

        self.assertRegex(styles, r"\.lightbox\s*\{[^}]*position:\s*fixed", "lightbox should float over the viewport")
        self.assertRegex(styles, r"\.lightbox\s*\{[^}]*display:\s*none", "lightbox should be hidden when inactive")
        self.assertRegex(styles, r"\.lightbox\.active\s*\{[^}]*display:\s*flex", "active lightbox should be visible")
        self.assertRegex(styles, r"\.lightbox-close\s*\{[^}]*position:\s*absolute", "close button should stay inside the overlay")
        self.assertRegex(styles, r"\.lightbox-close\s*\{[^}]*display:\s*inline-flex", "close icon should not rely on glyph line-height")
        self.assertRegex(styles, r"\.lightbox-close\s*\{[^}]*align-items:\s*center", "close icon should be vertically centered")
        self.assertRegex(styles, r"\.lightbox-close\s*\{[^}]*justify-content:\s*center", "close icon should be horizontally centered")

    def test_lightbox_can_close_with_button_and_escape(self) -> None:
        script = self._frontend_script_source()
        lightbox_source = self._lightbox_source()

        self.assertIn("lightboxClose", script)
        self.assertIn("addEventListener(\"click\", closeLightbox)", script)
        self.assertIn("addEventListener(\"keydown\"", script)
        self.assertIn('event.key === "Escape"', script)
        self.assertIn('class="drawer-close-icon"', lightbox_source)
        self.assertIn('<path d="M6 6l12 12M18 6L6 18"></path>', lightbox_source)
        self.assertNotIn('aria-label="${translate("lightbox.close")}">×</button>', lightbox_source)

    def test_lightbox_can_navigate_multiple_outputs(self) -> None:
        script = self._frontend_script_source()
        styles = Path("codex_image/webui/static/styles.css").read_text(encoding="utf-8")

        self.assertIn('const images = [...els.previewGrid.querySelectorAll("[data-lightbox-url]")]', script)
        self.assertIn("window.openLightbox?.(currentUrl, urls, Math.max(0, images.indexOf(image)))", script)
        self.assertIn("urls: []", script)
        self.assertIn("showPreviousLightboxImage", script)
        self.assertIn("showNextLightboxImage", script)
        self.assertIn('event.key === "ArrowLeft"', script)
        self.assertIn('event.key === "ArrowRight"', script)
        self.assertIn('class="lightbox-nav lightbox-prev"', script)
        self.assertIn('class="lightbox-nav lightbox-next"', script)
        self.assertIn("lightbox-counter", script)
        self.assertRegex(styles, r"\.lightbox-nav\s*\{[^}]*position:\s*absolute")
        self.assertRegex(styles, r"\.lightbox-counter\s*\{[^}]*position:\s*absolute")
    def test_lightbox_controls_stay_above_zoomed_image(self) -> None:
        styles = Path("codex_image/webui/static/styles.css").read_text(encoding="utf-8")

        self.assertRegex(styles, r"\.lightbox\s+img\s*\{[^}]*z-index:\s*1")
        self.assertRegex(styles, r"\.lightbox-close\s*\{[^}]*z-index:\s*2")
        self.assertRegex(styles, r"\.lightbox-nav\s*\{[^}]*z-index:\s*2")
        self.assertRegex(styles, r"\.lightbox-counter\s*\{[^}]*z-index:\s*2")
    def test_lightbox_right_click_does_not_leave_image_panning(self) -> None:
        script = self._frontend_script_source()

        self.assertIn("function stopLightboxPanning", script)
        self.assertIn("if (event.button !== 0)", script)
        self.assertIn("img?.addEventListener(\"contextmenu\", stopLightboxPanning)", script)
        self.assertIn("window.addEventListener(\"mouseup\", stopLightboxPanning)", script)
        self.assertIn("window.addEventListener(\"blur\", stopLightboxPanning)", script)
        self.assertIn("event.buttons !== undefined && (event.buttons & 1) !== 1", script)
    def test_lightbox_feature_has_typescript_source_contract(self) -> None:
        lightbox_source = self._lightbox_source()
        legacy_source = self._bootstrap_source()

        self.assertIn("export function initLightboxFeature", lightbox_source)
        self.assertIn("function openLightbox", lightbox_source)
        self.assertIn("function closeLightbox", lightbox_source)
        self.assertIn("function syncActiveLightboxUrls", lightbox_source)
        self.assertIn("window.openLightbox = openLightbox", lightbox_source)
        self.assertIn("window.addToInput = addToInput", lightbox_source)
        self.assertIn("Object.assign(getLegacyBridge().methods", lightbox_source)
        for function_name in [
            "isLightboxActive",
            "setLightboxTransform",
            "openLightbox",
            "closeLightbox",
        ]:
            self.assertNotRegex(legacy_source, rf"\n(?:async\s+)?function {function_name}\(")
        self.assertIn("function syncActiveLightboxUrls(): void", legacy_source)
    def test_simplified_workspace_removes_unneeded_panels(self) -> None:
        html = Path("codex_image/webui/static/index.html").read_text(encoding="utf-8")

        self.assertNotIn("基础设置", html)
        self.assertNotIn("接口模式", html)
        self.assertNotIn("任务类型", html)
        self.assertNotIn("状态</h2>", html)
        self.assertNotIn("接口请求预览", html)
        self.assertNotIn("copyJsonButton", html)
        self.assertIn('id="model"', html)
        self.assertIn('type="hidden"', html)
    def test_dashboard_uses_two_column_workspace(self) -> None:
        html = Path("codex_image/webui/static/index.html").read_text(encoding="utf-8")
        script = self._frontend_script_source()
        shell = self._shell_ui_source()
        styles = Path("codex_image/webui/static/styles.css").read_text(encoding="utf-8")

        self.assertIn("controls-col", html)
        self.assertIn("preview-col", html)
        self.assertIn("controlsCol: document.querySelector", script)
        self.assertIn("previewCol: document.querySelector", script)
        self.assertIn("previewPanel: document.querySelector", script)
        self.assertNotIn("setupPreviewPanelHeightSync", shell)
        self.assertNotIn("syncPreviewPanelHeight", shell)
        self.assertNotIn("--controls-col-height", shell)
        self.assertNotIn('class="settings-panel"', html)
        self.assertNotIn('class="status-panel"', html)
        self.assertNotIn('class="json-panel"', html)
        self.assertRegex(styles, r"\.dashboard\s*\{[^}]*width:\s*min\(100%,\s*1760px\)")
        self.assertRegex(styles, r"\.dashboard\s*\{[^}]*margin-inline:\s*auto")
        self.assertRegex(styles, r"\.dashboard\s*\{[^}]*grid-template-columns:\s*minmax\(520px,\s*760px\)\s+minmax\(520px,\s*1fr\)")
        self.assertRegex(styles, r"\.dashboard\s*\{[^}]*min-height:\s*0")
        self.assertNotRegex(styles, r"\.dashboard\s*\{[^}]*grid-template-rows:")
        self.assertRegex(styles, r"\.dashboard\s*\{[^}]*align-content:\s*safe center")
        self.assertRegex(styles, r"\.dashboard\s*\{[^}]*align-items:\s*stretch")
        self.assertRegex(styles, r"\.controls-col\s*\{[^}]*max-width:\s*760px")
        self.assertRegex(styles, r"\.controls-col\s*\{[^}]*width:\s*100%")
        controls_block = self._extract_css_block(styles, ".controls-col")
        self.assertNotIn("height:", controls_block)
        self.assertNotIn("overflow-y:", controls_block)
        self.assertNotRegex(styles, r"\.controls-col\s*>\s*\.output-panel\s*\{[^}]*flex:\s*1\s+1\s+auto")
        self.assertNotRegex(styles, r"\.preview-col\s*\{[^}]*position:\s*sticky")
        self.assertRegex(styles, r"\.preview-col\s*\{[^}]*position:\s*relative")
        self.assertRegex(styles, r"\.preview-col\s*\{[^}]*height:\s*auto")
        self.assertRegex(styles, r"\.preview-col\s*\{[^}]*overflow:\s*hidden")
        self.assertRegex(styles, r"\.preview-panel\s*\{[^}]*height:\s*100%")
        self.assertRegex(styles, r"\.preview-panel\s*\{[^}]*max-height:\s*none")
        self.assertRegex(styles, r"\.preview-panel\s*\{[^}]*display:\s*flex")
        self.assertRegex(styles, r"\.preview-grid\s*\{[^}]*flex:\s*1")
        self.assertRegex(styles, r"\.preview-grid\s*\{[^}]*min-height:\s*0")
        self.assertRegex(styles, r"\.preview-grid\s*\{[^}]*place-items:\s*center")
        self.assertRegex(styles, r"\.preview-grid\s*\{[^}]*overflow:\s*hidden")
        self.assertRegex(styles, r"\.preview-grid:not\(\.multi-output\)\s+\.preview-card\s*\{[^}]*height:\s*100%")
        self.assertRegex(styles, r"\.preview-grid:not\(\.multi-output\)\s+\.preview-card\s*\{[^}]*border-color:\s*transparent")
        self.assertRegex(styles, r"\.preview-grid:not\(\.multi-output\)\s+\.preview-card\s*\{[^}]*background:\s*transparent")
        self.assertRegex(styles, r"\.preview-grid:not\(\.multi-output\)\s+\.preview-card img\s*\{[^}]*position:\s*absolute")
        self.assertRegex(styles, r"\.preview-grid:not\(\.multi-output\)\s+\.preview-card img\s*\{[^}]*inset:\s*0")
        self.assertRegex(styles, r"\.preview-grid:not\(\.multi-output\)\s+\.preview-card img\s*\{[^}]*width:\s*100%")
        self.assertRegex(styles, r"\.preview-grid:not\(\.multi-output\)\s+\.preview-card img\s*\{[^}]*height:\s*100%")
        self.assertRegex(styles, r"\.preview-card\s*\{[^}]*max-height:\s*100%")
        self.assertRegex(styles, r"\.preview-card\s*\{[^}]*border:\s*1px solid transparent")
        self.assertRegex(styles, r"\.preview-card img\s*\{[^}]*max-width:\s*100%")
        self.assertRegex(styles, r"\.preview-card img\s*\{[^}]*max-height:\s*100%")
        self.assertNotIn(".preview-col > .panel:last-child", styles)
    def test_main_workspace_uses_theme_background_texture_only(self) -> None:
        styles = Path("codex_image/webui/static/styles.css").read_text(encoding="utf-8")
        dashboard_block = self._extract_css_block(styles, ".dashboard")

        self.assertRegex(styles, r":root\s*\{[\s\S]*--workspace-texture:\s*radial-gradient")
        self.assertRegex(styles, r":root\[data-theme=\"dark\"\]\s*\{[\s\S]*--workspace-texture:\s*radial-gradient")
        self.assertRegex(styles, r"\.main-wrapper\s*\{[^}]*background-image:\s*var\(--workspace-texture\)")
        self.assertRegex(styles, r"\.main-wrapper\s*\{[^}]*background-size:\s*22px 22px,\s*100% 100%")
        self.assertNotIn("background-image: var(--workspace-texture)", dashboard_block)
        self.assertNotIn("--preview-panel-texture", styles)
        self.assertNotIn(".preview-col > .panel.preview-panel", styles)
    def test_destructive_actions_use_anchored_web_confirm_popover(self) -> None:
        script = self._frontend_script_source()
        styles = Path("codex_image/webui/static/styles.css").read_text(encoding="utf-8")

        self.assertNotIn("window.confirm", script)
        self.assertIn("function openConfirmPopover", script)
        self.assertIn("function closeConfirmPopover", script)
        self.assertIn("positionConfirmPopover(anchor, popover)", script)
        self.assertIn('data-confirm-popover-confirm', script)
        self.assertIn('data-confirm-popover-cancel', script)
        self.assertIn("openConfirmPopover(deleteButton", script)
        self.assertIn("openConfirmPopover(els.batchDeleteButton", script)
        self.assertIn("openConfirmPopover(button", script)
        self.assertRegex(styles, r"\.confirm-popover\s*\{[^}]*position:\s*fixed")
        self.assertRegex(styles, r"\.confirm-popover\s*\{[^}]*z-index:\s*9300")
        self.assertRegex(styles, r"\.confirm-popover-actions\s*\{[^}]*display:\s*flex")
        self.assertRegex(styles, r"\.confirm-popover-confirm\.danger-button\s*\{[^}]*background:")
    def test_system_settings_storage_tab_can_manage_storage_paths(self) -> None:
        html = Path("codex_image/webui/static/index.html").read_text(encoding="utf-8")
        script = self._frontend_script_source()
        styles = Path("codex_image/webui/static/styles.css").read_text(encoding="utf-8")

        self.assertNotIn('id="settingsButton"', html)
        self.assertIn('id="systemSettingsModal"', html)
        self.assertIn('id="systemSettingsStoragePanel"', html)
        self.assertIn('id="settingsInputRoot"', html)
        self.assertIn('id="settingsOutputRoot"', html)
        self.assertIn('id="settingsGalleryRoot"', html)
        self.assertIn('id="settingsSourceDataRoot"', html)
        self.assertIn('id="saveSettingsButton"', html)
        self.assertIn('openSystemSettingsModal("storage")', script)
        self.assertIn('fetch("/api/settings")', script)
        self.assertIn('fetch("/api/settings", {', script)
        self.assertIn("restart_required", script)
        self.assertIn("重启 WebUI 后生效", script)
        self.assertRegex(styles, r"\.system-settings-modal-panel\s*\{[^}]*width:\s*min\(624px,\s*calc\(100vw - 60px\)\)")
        self.assertRegex(styles, r"\.system-settings-modal-panel\s*\{[^}]*max-height:\s*min\(760px,\s*calc\(100vh - var\(--system-settings-modal-top,\s*30px\) - 30px\)\)")
        self.assertRegex(styles, r"\.system-settings-modal-panel\s*\{[^}]*overflow:\s*auto")
        self.assertRegex(styles, r"\.system-settings-modal-panel\s*\{[^}]*padding:\s*22px\s+28px\s+24px")
        self.assertRegex(styles, r"\.system-settings-modal-panel\s*\{[^}]*transition:\s*height var\(--motion-height\)")
        self.assertRegex(styles, r"\.system-settings-modal-panel\.is-height-animating\s*\{[^}]*overflow:\s*hidden")
        self.assertRegex(styles, r"\.system-settings-modal-panel\s*>\s*\.modal-heading\s*\{[^}]*align-items:\s*center")
        self.assertRegex(styles, r"\.system-settings-modal-panel\s*>\s*\.modal-heading\s*\{[^}]*justify-content:\s*center")
        self.assertRegex(styles, r"\.system-settings-modal-panel\s*>\s*\.modal-heading\s*\{[^}]*margin-bottom:\s*16px")
        self.assertRegex(styles, r"\.system-settings-modal-panel\s*>\s*\.modal-heading\s+h2\s*\{[^}]*margin:\s*0")
        self.assertIn(".system-settings-tabs", styles)
        self.assertIn(".system-settings-section[hidden]", styles)
        self.assertRegex(styles, r"\.system-settings-section\s*\{[^}]*flex:\s*0 1 auto")
        self.assertRegex(styles, r"\.system-settings-section\s*\{[^}]*max-height:\s*calc\(100vh - 190px\)")
        self.assertRegex(styles, r"\.system-settings-section\s*\{[^}]*overflow-x:\s*hidden")
        self.assertRegex(styles, r"\.system-settings-section\s*\{[^}]*overflow-y:\s*auto")
        self.assertRegex(styles, r"\.system-settings-section\s*\{[^}]*padding-right:\s*0")
        self.assertRegex(styles, r"\.settings-modal-actions\s*\{[^}]*margin-top:\s*16px")
        self.assertRegex(styles, r"\.settings-path-grid\s*\{[^}]*display:\s*grid")
    def test_image_input_accepts_clipboard_images(self) -> None:
        html = Path("codex_image/webui/static/index.html").read_text(encoding="utf-8")
        script = self._frontend_script_source()
        styles = Path("codex_image/webui/static/styles.css").read_text(encoding="utf-8")

        self.assertIn('/static/app.js?v=runtime-568', html)
        self.assertIn('/static/styles.css?v=runtime-568', html)
        self.assertIn('id="pasteClipboardButton"', html)
        self.assertIn('id="statusText"', html)
        self.assertRegex(
            html,
            r'<div class="task-history-tools">\s*<div id="statusText" class="status-text" aria-live="polite" data-i18n="status\.waiting">等待任务</div>',
        )
        self.assertRegex(
            html,
            r'<div class="image-input-actions">\s*<button id="clearImagesButton" class="ghost-button icon-text-button text-sm quiet-danger-button"[\s\S]*<svg[\s\S]*<span[^>]*>清空</span>[\s\S]*?</button>\s*<button id="pasteClipboardButton" class="ghost-button icon-text-button text-sm"[\s\S]*<svg[\s\S]*<span[^>]*>粘贴</span>',
        )
        self.assertNotIn("粘贴剪贴板", html)
        self.assertIn("点击、拖入或粘贴图片", html)
        self.assertIn("pasteClipboardButton: document.querySelector(\"#pasteClipboardButton\")", script)
        self.assertIn('els.pasteClipboardButton?.addEventListener("click", pasteClipboardImages)', script)
        self.assertIn('document.addEventListener("paste", handleImagePaste)', script)
        self.assertIn('els.imageUploaderGrid?.addEventListener("dragenter", handleImageDragEnter)', script)
        self.assertIn('els.imageUploaderGrid?.addEventListener("dragover", handleImageDragOver)', script)
        self.assertIn('els.imageUploaderGrid?.addEventListener("dragleave", handleImageDragLeave)', script)
        self.assertIn('els.imageUploaderGrid?.addEventListener("drop", handleImageDrop)', script)
        self.assertIn("function isImageFile(file)", script)
        self.assertIn("function addImageFiles(files, options = {})", script)
        self.assertIn("function handleImagePaste(event)", script)
        self.assertIn("event.clipboardData?.items", script)
        self.assertIn("function imageFilesFromDataTransfer(dataTransfer)", script)
        self.assertIn("function dataTransferHasFile(dataTransfer)", script)
        self.assertRegex(script, r"function handleImageDragOver\(event(?:: DragEvent)?\)")
        self.assertIn("event.preventDefault()", script)
        self.assertIn('event.dataTransfer.dropEffect = "copy"', script)
        self.assertNotIn('event.dataTransfer.dropEffect = acceptsImage ? "copy" : "none"', script)
        self.assertRegex(script, r"function handleImageDrop\(event(?:: DragEvent)?\)")
        self.assertIn("event.dataTransfer", script)
        self.assertIn("inputSource.droppedCount", script)
        self.assertIn("inputSource.dropImagesOnly", script)
        self.assertIn("function pasteClipboardImages()", script)
        self.assertIn("navigator.clipboard?.read", script)
        self.assertIn("readClipboardImageFiles", script)
        self.assertIn("function focusImagePasteTarget()", script)
        self.assertIn("els.imageUploadSource?.focus({ preventScroll: true })", script)
        self.assertIn("clipboardPasteShortcutLabel", script)
        self.assertIn("图片输入区已聚焦，请按", script)
        self.assertIn("clipboardImageFilename", script)
        self.assertRegex(styles, r"\.image-uploader-grid\.drag-over\s+\.upload-tile\s*\{[^}]*background:")
    def test_image_thumbnails_keep_natural_aspect_ratio(self) -> None:
        styles = Path("codex_image/webui/static/styles.css").read_text(encoding="utf-8")

        self.assertNotRegex(styles, r"\.task-thumb\s*\{[^}]*height:\s*44px")
        self.assertNotRegex(styles, r"\.preview-card\s*\{[^}]*aspect-ratio:\s*1")
        self.assertRegex(styles, r"\.task-thumb\s*\{[^}]*object-fit:\s*contain")
        self.assertRegex(styles, r"\.preview-card img\s*\{[^}]*height:\s*auto")
    def test_javascript_tolerates_removed_status_and_json_panels(self) -> None:
        script = self._frontend_script_source()

        self.assertIn("if (!els.statusText) return", script)
        self.assertIn("if (!els.requestJson) return", script)
        self.assertIn("if (els.copyJsonButton)", script)
        self.assertIn('setMode("generate")', script)
    def test_input_image_editor_modal_markup_and_styles_exist(self) -> None:
        html = Path("codex_image/webui/static/index.html").read_text(encoding="utf-8")
        styles = Path("codex_image/webui/static/styles.css").read_text(encoding="utf-8")

        self.assertIn('id="imageEditorModal"', html)
        self.assertIn('aria-label="编辑输入图片"', html)
        self.assertIn('id="imageEditorCanvas"', html)
        self.assertIn('id="imageEditorCanvasWrap"', html)
        self.assertIn('id="imageEditorToolBrush"', html)
        self.assertIn('id="imageEditorToolArrow"', html)
        self.assertIn('id="imageEditorToolCrop"', html)
        self.assertIn('id="imageEditorToolFill"', html)
        self.assertRegex(html, r'id="imageEditorToolBrush" class="ghost-button text-sm image-editor-tool"')
        self.assertRegex(html, r'id="imageEditorToolCrop" class="ghost-button text-sm image-editor-tool active"')
        self.assertIn('data-tool-icon="brush"', html)
        self.assertIn('data-tool-icon="arrow"', html)
        self.assertIn('data-tool-icon="crop"', html)
        self.assertIn('data-tool-icon="fill"', html)
        self.assertIn('data-image-editor-tool="fill"', html)
        self.assertIn('aria-label="油漆桶填充"', html)
        self.assertIn("油漆桶", html)
        self.assertIn('id="imageEditorColor"', html)
        self.assertIn('id="imageEditorStroke"', html)
        self.assertIn('id="imageEditorStroke" class="slider" type="range" min="2" max="96" step="1" value="8"', html)
        self.assertIn('id="imageEditorUndo"', html)
        self.assertIn('id="imageEditorRedo"', html)
        self.assertIn('id="imageEditorReset"', html)
        self.assertIn('id="imageEditorSave"', html)
        self.assertIn('id="imageEditorCancel"', html)
        self.assertIn('data-image-editor-canvas-scope="base"', html)
        self.assertIn('data-image-editor-canvas-scope="fit"', html)
        self.assertIn('data-i18n="imageEditor.canvasScope"', html)
        self.assertRegex(styles, r"\.image-editor-panel\s*\{[^}]*width:\s*min\(1040px,\s*94vw\)")
        self.assertRegex(styles, r"\.image-editor-toolbar\s*\{[^}]*display:\s*flex")
        self.assertRegex(styles, r"\.image-editor-stage\s*\{[^}]*min-height:\s*360px")
        self.assertRegex(styles, r"\.image-editor-canvas-wrap\s*\{[^}]*touch-action:\s*none")
        self.assertRegex(styles, r"\.image-editor-canvas\s*\{[^}]*max-width:\s*100%")
        self.assertRegex(styles, r"\.image-editor-tool\.active\s*\{[^}]*background:\s*var\(--primary\)")
        self.assertRegex(styles, r"\.image-editor-tool\s*\{[^}]*min-height:\s*44px")
        self.assertRegex(styles, r"\.image-editor-tool\s*\{[^}]*display:\s*inline-flex")
        self.assertRegex(styles, r"\.image-editor-tool-icon\s+svg\s*\{[^}]*width:\s*18px")
        self.assertRegex(styles, r"\.image-editor-canvas-scope-control\s*\{[^}]*grid-template-columns:\s*1fr 1fr")
        self.assertRegex(styles, r"\.image-editor-canvas-scope-control \.ghost-button\.active\s*\{[^}]*background:\s*var\(--primary\)")
        self.assertRegex(styles, r"\.image-editor-actions \.ghost-button,\s*\.image-editor-actions \.primary-button\s*\{[^}]*width:\s*72px")
        self.assertRegex(styles, r"\.image-editor-actions \.ghost-button,\s*\.image-editor-actions \.primary-button\s*\{[^}]*height:\s*44px")
        self.assertRegex(styles, r"\.thumb-edited-badge\s*\{[^}]*background:\s*color-mix\(in srgb, var\(--primary\) 86%, transparent\)")
        self.assertRegex(styles, r"\.thumb-edited-badge\s*\{[^}]*right:\s*5px")
        self.assertRegex(styles, r"\.thumb-edited-badge\s*\{[^}]*bottom:\s*5px")
        self.assertNotRegex(styles, r"\.thumb-edited-badge\s*\{[^}]*left:\s*5px")
        self.assertNotRegex(styles, r"\.thumb-edited-badge\s*\{[^}]*bottom:\s*31px")
    def test_input_image_thumbnail_primary_click_opens_editor_and_gallery_action_is_secondary(self) -> None:
        script = self._frontend_script_source()
        image_strip_source = self._image_strip_source()
        styles = Path("codex_image/webui/static/styles.css").read_text(encoding="utf-8")

        self.assertIn("createThumbAddIcon", image_strip_source)
        self.assertIn("function createThumbRemoveIcon()", image_strip_source)
        self.assertIn("thumb-add-icon", image_strip_source)
        self.assertIn("thumb-remove-icon", image_strip_source)
        self.assertIn("stroke-linecap", image_strip_source)
        self.assertIn('remove.append(createThumbRemoveIcon())', image_strip_source)
        self.assertIn('remove.setAttribute("aria-label", translate("imageInput.removeImage"))', image_strip_source)
        self.assertNotIn('remove.textContent = "×"', image_strip_source)
        self.assertNotIn("createThumbActionIcon", script)
        self.assertNotIn('createThumbActionIcon("gallery")', script)
        self.assertNotIn('createThumbActionIcon("edit")', script)
        self.assertNotIn('className = "thumb-edit"', script)
        self.assertIn('wrapper.classList.add("editable-thumb")', script)
        self.assertIn('wrapper.tabIndex = 0', script)
        self.assertIn('wrapper.setAttribute("role", "button")', script)
        self.assertRegex(script, r"wrapper\.addEventListener\(\"click\", \(event\) => \{[\s\S]*event\.target\.closest\(\"button\"\)[\s\S]*legacyMethod\(\"openImageEditor\", index\)")
        self.assertRegex(script, r"wrapper\.addEventListener\(\"keydown\", \(event\) => \{[\s\S]*event\.key === \"Enter\"[\s\S]*legacyMethod\(\"openImageEditor\", index\)")
        self.assertIn('addToGallery.append(createThumbAddIcon(), document.createTextNode(translate("imageInput.addToGalleryShort")))', script)
        self.assertIn('translate("imageInput.addToGallery")', script)
        self.assertNotIn('document.createTextNode("+ 图库")', script)
        self.assertNotIn('document.createTextNode("加入图库")', script)
        self.assertRegex(styles, r"\.add-upload-to-gallery\s*\{[^}]*height:\s*32px")
        self.assertRegex(styles, r"\.add-upload-to-gallery\s*\{[^}]*min-width:\s*54px")
        self.assertRegex(styles, r"\.add-upload-to-gallery\s*\{[^}]*display:\s*inline-flex")
        self.assertRegex(styles, r"\.add-upload-to-gallery\s*\{[^}]*opacity:\s*0\.9")
        self.assertRegex(styles, r"\.add-upload-to-gallery\s*\{[^}]*pointer-events:\s*auto")
        self.assertNotRegex(styles, r"\.add-upload-to-gallery\s*\{[^}]*opacity:\s*0(?:;|$)")
        self.assertRegex(styles, r"\.add-upload-to-gallery\s*\{[^}]*bottom:\s*6px")
        self.assertRegex(styles, r"\.add-upload-to-gallery\s*\{[^}]*right:\s*auto")
        self.assertNotRegex(styles, r"\.add-upload-to-gallery\s*\{[^}]*top:\s*6px")
        self.assertRegex(styles, r"\.thumb:hover\s+\.add-upload-to-gallery,\s*\.thumb:focus-within\s+\.add-upload-to-gallery,\s*\.add-upload-to-gallery:focus-visible\s*\{[^}]*opacity:\s*1")
        self.assertRegex(styles, r"\.thumb \.thumb-remove\s*\{[^}]*z-index:\s*3")
        self.assertRegex(styles, r"\.thumb \.thumb-remove\s*\{[^}]*background:\s*color-mix\(in srgb, var\(--danger\) 78%, var\(--surface\)\)")
        self.assertRegex(styles, r"\.thumb \.thumb-remove\s*\{[^}]*color:\s*var\(--primary-foreground\)")
        self.assertNotRegex(styles, r"\.thumb \.thumb-remove\s*\{[^}]*background:\s*rgba\(0,\s*0,\s*0,\s*0\.5\)")
        self.assertRegex(styles, r"\.thumb-remove-icon,\s*\.thumb-remove-icon svg\s*\{[^}]*width:\s*12px")
        self.assertRegex(styles, r"\.thumb-badge\s*\{[^}]*background:\s*color-mix\(in srgb, var\(--primary\) 88%, transparent\)")
        self.assertRegex(styles, r"\.thumb-badge\s*\{[^}]*color:\s*var\(--primary-foreground\)")
        self.assertNotRegex(styles, r"\.thumb-badge\s*\{[^}]*background:\s*rgba\(31,\s*53,\s*47")
        self.assertRegex(styles, r"\.thumb-add-icon\s+svg\s*\{[^}]*width:\s*14px")
        self.assertRegex(styles, r"\.upload-tile\s+\.icon\s+svg\s*\{[^}]*width:\s*18px")
        self.assertRegex(styles, r"\.upload-tile\s+\.icon\s+svg\s*\{[^}]*height:\s*18px")
        self.assertNotIn(".thumb-action-icon", styles)
        self.assertRegex(styles, r"\.editable-thumb\s*\{[^}]*cursor:\s*pointer")
        self.assertRegex(styles, r"\.editable-thumb:hover\s*\{[^}]*transform:\s*translateY\(-1px\)")
        self.assertNotRegex(styles, r"\.thumb-edit\s*[,{\n]")
        self.assertNotRegex(styles, r"\.add-upload-to-gallery\s*\{[^}]*height:\s*22px")
    def test_input_image_editor_javascript_contract_exists(self) -> None:
        script = self._frontend_script_source()
        image_editor_source = self._image_editor_source()
        legacy_source = self._bootstrap_source()

        self.assertIn("IMAGE_EDITOR_PROMPT_HINT", script)
        self.assertIn("IMAGE_EDITOR_MAX_EXPORT_EDGE", script)
        self.assertIn("export function initImageEditorFeature", image_editor_source)
        self.assertIn("Object.assign(getLegacyBridge().methods", image_editor_source)
        self.assertIn("isEditableImageSource,", image_editor_source)
        for function_name in [
            "openImageEditor",
            "closeImageEditor",
            "setImageEditorTool",
            "renderImageEditor",
            "pushImageEditorHistory",
            "saveImageEdit",
            "resetImageEdit",
        ]:
            self.assertNotRegex(legacy_source, rf"\n(?:async\s+)?function {function_name}\(")
        self.assertIn('isEditableImageSource: proxy("isEditableImageSource")', legacy_source)
        self.assertNotIn("IMAGE_EDITOR_BUCKET_FILL_TOLERANCE", script)
        self.assertIn("const imageEditorState = {", script)
        self.assertIn("brushBoundaryCanvas: null", script)
        self.assertIn("brushOverlayCanvas: null", script)
        self.assertIn('tool: "crop"', script)
        self.assertIn('canvasScope: "base"', script)
        self.assertNotIn('tool: "brush"', script)
        self.assertIn("hasInstructionMarks: false", script)
        self.assertIn("imageEditorModal: document.querySelector(\"#imageEditorModal\")", script)
        self.assertIn("imageEditorCanvas: document.querySelector(\"#imageEditorCanvas\")", script)
        self.assertIn("imageEditorToolBrush: document.querySelector(\"#imageEditorToolBrush\")", script)
        self.assertIn("imageEditorToolArrow: document.querySelector(\"#imageEditorToolArrow\")", script)
        self.assertIn("imageEditorToolCrop: document.querySelector(\"#imageEditorToolCrop\")", script)
        self.assertIn("imageEditorToolFill: document.querySelector(\"#imageEditorToolFill\")", script)
        self.assertIn("originalFile: file", script)
        self.assertIn("edited: false", script)
        self.assertIn("function openImageEditor(index)", script)
        self.assertIn("function closeImageEditor()", script)
        self.assertIn("function setImageEditorTool(tool)", script)
        self.assertIn("function renderImageEditor()", script)
        self.assertIn("function pushImageEditorHistory()", script)
        self.assertIn("function undoImageEdit()", script)
        self.assertIn("function redoImageEdit()", script)
        self.assertIn("function resetImageEdit()", script)
        self.assertIn("function saveImageEdit()", script)
        self.assertIn("function paintBucketFillRegion(point)", script)
        self.assertIn("function imageEditorBucketFillColor()", script)
        self.assertIn("function imageEditorBrushBoundaryContext()", script)
        self.assertIn("function imageEditorBrushOverlayContext()", script)
        self.assertIn("function drawEditorBrushBoundarySegment(from, to)", script)
        self.assertIn("function drawEditorBrushOverlaySegment(from, to)", script)
        self.assertIn("function redrawImageEditorBrushOverlay(ctx)", script)
        self.assertIn("function imageEditorBoundaryPixelBlocks(data, index)", script)
        self.assertIn("function imageEditorBoundaryHasPixels(data)", script)
        self.assertIn("function imageEditorPixelTouchesCanvasEdge(index, width, height)", script)
        self.assertNotIn("function imageEditorPixelMatches(data, offset, target, tolerance)", script)
        self.assertNotIn("target = [", script)
        self.assertIn("function handleImageEditorHistoryShortcut(event)", script)
        self.assertIn("function isImageEditorModalOpen()", script)
        self.assertIn('if (!["select", "brush", "arrow", "crop", "fill", "eraser"].includes(tool)) return;', script)
        self.assertIn("function ensureImageEditorPromptHint()", script)
        self.assertIn("function imageEditorExportBlob(canvas)", script)
        self.assertIn("function editedUploadFilename(name)", script)
        self.assertIn("function isEditableImageSource(source)", script)
        self.assertIn("async function imageEditorSourceFile(source)", script)
        self.assertIn("async function remoteImageSourceFile(source)", script)
        self.assertIn('kind: "upload",', script)
        self.assertIn('legacyMethod("syncPromptGalleryMentionsFromInputs")', script)
        self.assertIn("if (imageEditorState.hasInstructionMarks) ensureImageEditorPromptHint();", script)
        self.assertIn("if (!source || !isEditableImageSource(source))", script)
        self.assertIn("hasInstructionMarks: imageEditorState.hasInstructionMarks", script)
        self.assertIn("canvasScope: imageEditorState.canvasScope", script)
        self.assertIn("imageEditorState.canvasScope = snapshot.canvasScope || \"base\";", script)
        self.assertIn("imageEditorState.hasInstructionMarks = Boolean(snapshot.hasInstructionMarks);", script)
        self.assertIn("imageEditorState.hasInstructionMarks = true;", script)
        self.assertIn('imageEditorState.tool = "crop";', script)
        self.assertNotIn('imageEditorState.tool = "brush";', script)
        self.assertIn('configureImageEditorStroke(ctx, { lineCap: "butt", lineJoin: "miter" })', script)
        self.assertIn("function imageEditorArrowGeometry(start, end)", script)
        self.assertIn("const headWidth = Math.max(18, strokeWidth * 2.2);", script)
        self.assertIn("ctx.lineTo(geometry.shaftEnd.x, geometry.shaftEnd.y);", script)
        self.assertRegex(
            script,
            r"function drawEditorArrowOnContext\(ctx, start, end\)[\s\S]*ctx\.lineTo\(geometry\.shaftEnd\.x, geometry\.shaftEnd\.y\);[\s\S]*ctx\.stroke\(\);",
        )
        self.assertIn('els.imageEditorClose?.addEventListener("click", closeImageEditor)', script)
        self.assertIn('els.imageEditorCancel?.addEventListener("click", closeImageEditor)', script)
        self.assertIn('els.imageEditorSave?.addEventListener("click", saveImageEdit)', script)
        self.assertIn('els.imageEditorUndo?.addEventListener("click", undoImageEdit)', script)
        self.assertIn('els.imageEditorRedo?.addEventListener("click", redoImageEdit)', script)
        self.assertIn('els.imageEditorReset?.addEventListener("click", resetImageEdit)', script)
        self.assertIn('document.querySelectorAll<HTMLElement>("[data-image-editor-tool]")', script)
        self.assertIn('button.addEventListener("click", () => setImageEditorTool(button.dataset.imageEditorTool))', script)
        self.assertIn('document.querySelectorAll<HTMLElement>("[data-image-editor-color]")', script)
        self.assertIn('document.querySelectorAll<HTMLElement>("[data-image-editor-canvas-scope]")', script)
        self.assertIn("function setImageEditorCanvasScope(scope)", script)
        self.assertIn("fitImageEditorCanvasToLayers({ preserveCurrent: false, pushHistory: true, status: true });", script)
        self.assertIn("resetImageEditorCanvasToBase({ pushHistory: true, status: true });", script)
        self.assertIn('els.imageEditorColor?.addEventListener("input"', script)
        self.assertIn('els.imageEditorStroke?.addEventListener("input"', script)
        self.assertIn("addEventListener(\"pointerdown\", handleImageEditorPointerDown)", script)
        self.assertIn("addEventListener(\"pointermove\", handleImageEditorPointerMove)", script)
        self.assertIn("addEventListener(\"pointerup\", handleImageEditorPointerUp)", script)
        self.assertIn("addEventListener(\"pointercancel\", handleImageEditorPointerCancel)", script)
        self.assertIn('imageEditorState.tool === "fill"', script)
        self.assertIn("drawEditorBrushBoundarySegment(from, to);", script)
        self.assertIn("drawEditorBrushOverlaySegment(from, to);", script)
        self.assertIn("redrawImageEditorBrushOverlay(ctx);", script)
        self.assertIn("imageEditorState.brushBoundaryCanvas", script)
        self.assertIn("imageEditorState.brushOverlayCanvas", script)
        self.assertIn("ctx.lineWidth = imageEditorState.strokeWidth;", script)
        self.assertNotIn("imageEditorState.strokeWidth + 2", script)
        self.assertIn("if (!imageEditorBoundaryHasPixels(boundaryData)) return false;", script)
        self.assertIn("if (imageEditorPixelTouchesCanvasEdge(index, width, height)) return false;", script)
        self.assertIn('setImageEditorStatus(translate("imageEditor.closedRegionRequired"), "error");', script)
        self.assertIn("pushImageEditorHistory();", script)
        self.assertIn("event.metaKey || event.ctrlKey", script)
        self.assertIn('event.key.toLowerCase() === "z"', script)
        self.assertIn('event.key.toLowerCase() === "y"', script)
        self.assertIn("handleImageEditorHistoryShortcut(event)", script)
        self.assertRegex(script, r"function handleDocumentKeydown\(event\)\s*\{[\s\S]*event\.key === \"Escape\"[\s\S]*closeImageEditor\(\)")

    def test_input_image_editor_supports_layered_compositing(self) -> None:
        html = Path("codex_image/webui/static/index.html").read_text(encoding="utf-8")
        styles = Path("codex_image/webui/static/styles.css").read_text(encoding="utf-8")
        script = self._frontend_script_source()
        image_editor_source = self._image_editor_source()

        self.assertIn('"konva"', Path("package.json").read_text(encoding="utf-8"))
        self.assertIn('id="imageEditorKonvaMount"', html)
        self.assertIn('id="imageEditorInsertList"', html)
        self.assertIn('id="imageEditorLayerList"', html)
        self.assertIn('id="imageEditorToolSelect"', html)
        self.assertIn('id="imageEditorToolEraser"', html)
        self.assertIn('id="imageEditorLayerUp"', html)
        self.assertIn('id="imageEditorLayerDown"', html)
        self.assertIn('id="imageEditorLayerDelete"', html)
        self.assertIn('class="image-editor-side-section image-editor-canvas-scope-section"', html)
        self.assertIn('data-image-editor-tool="select"', html)
        self.assertIn('data-image-editor-tool="eraser"', html)

        self.assertRegex(styles, r"\.image-editor-workspace\s*\{[^}]*grid-template-columns:\s*minmax\(0,\s*1fr\)\s+220px")
        self.assertRegex(styles, r"\.image-editor-side-panel\s*\{[^}]*display:\s*flex")
        self.assertRegex(styles, r"\.image-editor-konva-mount\s*\{[^}]*width:\s*var\(--image-editor-stage-width")
        self.assertRegex(styles, r"\.image-editor-konva-mount\s*\{[^}]*height:\s*var\(--image-editor-stage-height")
        self.assertRegex(
            styles,
            r"\.image-editor-konva-mount \.konvajs-content\s*\{[^}]*width:\s*var\(--image-editor-stage-raw-width",
        )
        self.assertRegex(
            styles,
            r"\.image-editor-konva-mount \.konvajs-content\s*\{[^}]*height:\s*var\(--image-editor-stage-raw-height",
        )
        self.assertRegex(styles, r"\.image-editor-konva-mount \.konvajs-content\s*\{[^}]*transform:\s*scale\(var\(--image-editor-stage-scale")
        self.assertRegex(styles, r"\.image-editor-konva-mount canvas\s*\{[^}]*width:\s*var\(--image-editor-stage-raw-width")
        self.assertRegex(styles, r"\.image-editor-konva-mount canvas\s*\{[^}]*height:\s*var\(--image-editor-stage-raw-height")
        self.assertNotRegex(styles, r"\.image-editor-konva-mount canvas\s*\{[^}]*width:\s*auto\s*!important")
        self.assertNotRegex(styles, r"\.image-editor-konva-mount canvas\s*\{[^}]*height:\s*auto\s*!important")
        self.assertRegex(styles, r"\.image-editor-layer-thumb img\s*\{[^}]*object-fit:\s*cover")

        self.assertIn("import Konva from \"konva\";", image_editor_source)
        self.assertIn("konvaStage: null", image_editor_source)
        self.assertIn("konvaLayer: null", image_editor_source)
        self.assertIn("konvaTransformer: null", image_editor_source)
        self.assertIn("previewNode: null", image_editor_source)
        self.assertIn("layers: []", image_editor_source)
        self.assertIn("selectedLayerId: null", image_editor_source)
        self.assertIn('tool: "crop"', image_editor_source)
        self.assertIn("function renderImageEditorInsertList()", image_editor_source)
        self.assertIn("function renderImageEditorLayerList()", image_editor_source)
        self.assertIn("function imageEditorLayerThumbnailUrl(layer: ImageEditorLayer)", image_editor_source)
        self.assertIn("const thumbnailUrl = imageEditorLayerThumbnailUrl(layer);", image_editor_source)
        self.assertIn("thumbnail.src = thumbnailUrl;", image_editor_source)
        self.assertIn("thumb.append(thumbnail);", image_editor_source)
        self.assertRegex(
            image_editor_source,
            r"if \(thumbnailUrl\) \{[\s\S]*thumb\.append\(thumbnail\);[\s\S]*\} else \{[\s\S]*thumb\.textContent = String\(imageEditorState\.layers\.indexOf\(layer\) \+ 1\);",
        )
        self.assertRegex(image_editor_source, r"async function insertImageEditorLayerFromSource\(source(?::\s*any)?\)")
        self.assertRegex(image_editor_source, r"function selectImageEditorLayer\(layerId(?::\s*[^,)]+)?")
        self.assertRegex(
            image_editor_source,
            r"node\.on\(\"click tap\", \(event: any\) => \{[\s\S]*const point = imageEditorPoint\(event\.evt \|\| event\);[\s\S]*const hitLayer = imageEditorLayerAtPoint\(point\) \|\| layer;[\s\S]*selectImageEditorLayer\(hitLayer\.id, \{ updateTool: false \}\);",
        )
        self.assertRegex(
            image_editor_source,
            r"node\.on\(\"dragstart\", \(event: any\) => \{[\s\S]*const hitLayer = imageEditorLayerAtPoint\(point\) \|\| layer;[\s\S]*selectImageEditorLayer\(hitLayer\.id, \{ updateTool: false \}\);",
        )
        self.assertIn("function imageEditorLayerFromNode(node: any)", image_editor_source)
        self.assertIn("function isImageEditorTransformerTarget(node: any)", image_editor_source)
        self.assertIn("current === imageEditorState.konvaTransformer", image_editor_source)
        self.assertIn("function imageEditorLayerAtPoint(point: any)", image_editor_source)
        self.assertIn("for (let index = imageEditorState.layers.length - 1; index >= 0; index -= 1)", image_editor_source)
        self.assertIn("function fitImageEditorCanvasToLayers", image_editor_source)
        self.assertIn("function resetImageEditorCanvasToBase", image_editor_source)
        self.assertIn("function resizeImageEditorCanvas", image_editor_source)
        self.assertIn("resizeImageEditorBackingCanvas(imageEditorState.workCanvas", image_editor_source)
        self.assertIn("if (imageEditorState.canvasScope === \"fit\")", image_editor_source)
        self.assertIn("fitImageEditorCanvasToLayers({ preserveCurrent: true });", image_editor_source)
        self.assertIn("const rect = layer.node.getClientRect?.({ skipShadow: true, skipStroke: true }) || layer.node.getClientRect?.() || null;", image_editor_source)
        self.assertRegex(image_editor_source, r"function moveImageEditorLayer\(direction(?::\s*any)?\)")
        self.assertIn("function deleteSelectedImageEditorLayer()", image_editor_source)
        self.assertIn("function imageEditorCompositeCanvas()", image_editor_source)
        self.assertRegex(image_editor_source, r"function applyImageEditorLayerEraseStroke\(layer(?::\s*[^,]+)?, points(?::\s*any\[\])?\)")
        self.assertIn("function applyImageEditorLayerEraseSegment(layer: ImageEditorLayer, from: any, to: any)", image_editor_source)
        self.assertIn("function applyImageEditorLayerEraseDot(layer: ImageEditorLayer, point: any)", image_editor_source)
        self.assertIn("function imageEditorLayerCanvasPoint(layer: ImageEditorLayer, point: any)", image_editor_source)
        self.assertIn("layer.canvas.width / Math.max(1, layer.node.width())", image_editor_source)
        self.assertIn("layer.canvas.height / Math.max(1, layer.node.height())", image_editor_source)
        self.assertIn("imageEditorLayerCanvasStrokeWidth(layer)", image_editor_source)
        self.assertIn("drawing.changed = applyImageEditorLayerEraseSegment(layer, drawing.last, point) || drawing.changed;", image_editor_source)
        self.assertIn("const changed = applyImageEditorLayerEraseDot(layer, point);", image_editor_source)
        self.assertIn("new Konva.Arrow", image_editor_source)
        self.assertIn('name: "image-editor-preview-arrow"', image_editor_source)
        self.assertIn("function imageEditorArrowGeometry(start: any, end: any)", image_editor_source)
        self.assertIn("const headWidth = Math.max(18, strokeWidth * 2.2);", image_editor_source)
        self.assertIn("ctx.lineTo(geometry.shaftEnd.x, geometry.shaftEnd.y);", image_editor_source)
        self.assertRegex(
            image_editor_source,
            r"function drawEditorArrowOnContext\(ctx: any, start: any, end: any\)[\s\S]*ctx\.lineTo\(geometry\.shaftEnd\.x, geometry\.shaftEnd\.y\);[\s\S]*ctx\.stroke\(\);",
        )
        self.assertIn("function clearImageEditorPreview()", image_editor_source)
        self.assertIn("function updateImageEditorDisplayScale()", image_editor_source)
        self.assertIn("function updateImageEditorTransformerAffordance(displayScale: number)", image_editor_source)
        self.assertIn("transformer.anchorSize?.(Math.max(14, Math.round(14 / safeScale)))", image_editor_source)
        self.assertIn("transformer.rotateAnchorOffset?.(Math.max(28, Math.round(28 / safeScale)))", image_editor_source)
        self.assertIn("updateImageEditorTransformerAffordance(displayScale);", image_editor_source)
        self.assertIn('mount.style.setProperty("--image-editor-stage-width"', image_editor_source)
        self.assertIn('mount.style.setProperty("--image-editor-stage-height"', image_editor_source)
        self.assertIn('mount.style.setProperty("--image-editor-stage-raw-width"', image_editor_source)
        self.assertIn('mount.style.setProperty("--image-editor-stage-raw-height"', image_editor_source)
        self.assertIn('mount.style.setProperty("--image-editor-stage-scale"', image_editor_source)
        self.assertIn('"PointerEvent" in window', image_editor_source)
        self.assertIn('const downEvents = hasPointerEvents ? "pointerdown" : "mousedown touchstart";', image_editor_source)
        self.assertIn('const moveEvents = hasPointerEvents ? "pointermove" : "mousemove touchmove";', image_editor_source)
        self.assertIn('const upEvents = hasPointerEvents ? "pointerup pointercancel" : "mouseup touchend";', image_editor_source)
        self.assertIn("stage.setPointersPositions?.(event);", image_editor_source)
        self.assertIn('const target = mount?.querySelector(".konvajs-content") || mount || canvas;', image_editor_source)
        self.assertIn("const scaleX = stageWidth / Math.max(1, rect.width);", image_editor_source)
        self.assertIn("const scaleY = stageHeight / Math.max(1, rect.height);", image_editor_source)
        self.assertIn("Math.min(stageWidth, (event.clientX - rect.left) * scaleX)", image_editor_source)
        self.assertIn("captureImageEditorPointer(event)", image_editor_source)
        self.assertRegex(
            image_editor_source,
            r"if \(imageEditorState\.tool === \"select\"\) \{[\s\S]*if \(isImageEditorTransformerTarget\(event\.target\)\) return;[\s\S]*if \(event\.target === stage\) selectImageEditorLayer\(null, \{ updateTool: false \}\);[\s\S]*return;",
        )
        self.assertIn("new Konva.Transformer", image_editor_source)
        self.assertIn("keepRatio: true", image_editor_source)
        self.assertIn('shiftBehavior: "inverted"', image_editor_source)
        self.assertIn("anchorSize: 14", image_editor_source)
        self.assertIn('anchorStroke: "#2F6FE4"', image_editor_source)
        self.assertIn('anchorFill: "#FFFFFF"', image_editor_source)
        self.assertIn('borderStroke: "#2F6FE4"', image_editor_source)
        self.assertIn("rotateAnchorOffset: 28", image_editor_source)
        self.assertIn("imageEditorState.konvaTransformer?.moveToTop?.();", image_editor_source)
        self.assertIn("new Konva.Image", image_editor_source)
        self.assertIn("globalCompositeOperation = \"destination-out\"", image_editor_source)
        self.assertIn('if (!["select", "brush", "arrow", "crop", "fill", "eraser"].includes(tool)) return;', script)
        self.assertRegex(script, r"function resetForm\(\)\s*\{[\s\S]*closeGallery\(\);[\s\S]*closeImageEditor\(\);")
        self.assertIn("openImageEditor(index)", script)
        self.assertIn("editable-thumb", script)
        self.assertNotIn('className = "thumb-edit"', script)
        self.assertIn("thumb-edited-badge", script)
        self.assertNotRegex(
            script,
            r'if \(source\.kind === "upload"\) \{[\s\S]*const edit = document\.createElement\("button"\)',
        )
        self.assertIn('form.append("reference_images", source.file)', script)
        self.assertIn('form.append("images", source.file)', script)
    def test_theme_mode_markup_and_bootstrap_exist(self) -> None:
        html = Path("codex_image/webui/static/index.html").read_text(encoding="utf-8")

        self.assertRegex(html, r"<script>\s*\(\(\) => \{[\s\S]*THEME_STORAGE_KEY")
        self.assertRegex(html, r"document\.documentElement\.dataset\.theme =")
        self.assertRegex(html, r"<script>[\s\S]*</script>\s*<link rel=\"stylesheet\"")
        self.assertIn('id="themeSwitcher"', html)
        self.assertIn('data-theme-option="system"', html)
        self.assertIn('data-theme-option="light"', html)
        self.assertIn('data-theme-option="dark"', html)
        self.assertIn('aria-label="主题模式"', html)
    def test_theme_mode_javascript_and_styles_exist(self) -> None:
        html = Path("codex_image/webui/static/index.html").read_text(encoding="utf-8")
        script = self._frontend_script_source()
        styles = Path("codex_image/webui/static/styles.css").read_text(encoding="utf-8")

        self.assertIn("/static/app.js?v=runtime-568", html)
        self.assertIn("/static/styles.css?v=runtime-568", html)
        self.assertIn('const THEME_STORAGE_KEY = "codex-image-theme-preference";', script)
        self.assertIn('themePreference: "system"', script)
        self.assertIn('call(methods, "restoreThemePreference")', script)
        self.assertIn("function resolveEffectiveTheme", script)
        self.assertIn("function applyThemePreference", script)
        self.assertIn("let themeTransitionLockFrameId", script)
        self.assertIn("function lockThemeTransitions", script)
        self.assertIn('document.documentElement.classList.add("theme-transition-lock")', script)
        self.assertIn('document.documentElement.classList.remove("theme-transition-lock")', script)
        self.assertRegex(script, r"function applyThemePreference\(preference,[\s\S]*lockThemeTransitions\(\)")
        self.assertIn("function updateThemeSwitcher", script)
        self.assertIn("function handleThemeSystemChange", script)
        self.assertIn('localStorage.getItem(THEME_STORAGE_KEY)', script)
        self.assertIn('localStorage.setItem(THEME_STORAGE_KEY', script)
        self.assertRegex(styles, r":root\[data-theme=\"dark\"\]\s*\{[\s\S]*--bg:")
        self.assertIn("--success-soft:", styles)
        self.assertIn("--danger-soft:", styles)
        self.assertLess(styles.index("--danger-soft:"), styles.index("var(--danger-soft)"))
        self.assertRegex(styles, r"\.theme-switcher\s*\{[^}]*display:\s*inline-flex")
        self.assertRegex(styles, r"\.theme-switcher\s*\{[^}]*height:\s*var\(--top-nav-control-height\)")
        self.assertRegex(styles, r"\.theme-switcher\s*\{[^}]*border-radius:\s*var\(--top-nav-control-radius\)")
        self.assertRegex(styles, r"\.theme-option\s*\{[^}]*height:\s*var\(--top-nav-segment-height\)")
        self.assertRegex(styles, r"\.theme-option\s*\{[^}]*border-radius:\s*var\(--top-nav-control-radius\)")
        self.assertRegex(styles, r"\.theme-option\.active\s*\{[^}]*background:\s*var\(--primary\)")
        self.assertRegex(
            styles,
            r":root\.theme-transition-lock \*,\s*:root\.theme-transition-lock \*::before,\s*:root\.theme-transition-lock \*::after\s*\{[^}]*transition:\s*none !important",
        )
    def test_dark_theme_primary_controls_use_contrast_foreground(self) -> None:
        styles = Path("codex_image/webui/static/styles.css").read_text(encoding="utf-8")

        self.assertIn("--primary-foreground:", styles)
        self.assertRegex(styles, r":root\[data-theme=\"dark\"\]\s*\{[\s\S]*--primary-foreground:\s*#10201b;")
        for selector in (
            ".primary-button",
            ".run-button",
            ".theme-option.active",
            ".auth-source-button.active",
            ".system-settings-tab.active",
            ".system-settings-tabs.segmented-indicator-host .system-settings-tab.active",
            ".api-provider-choice.active",
            ".codex-channel-current",
            ".segment.active",
            ".radio-btn.active",
            ".quick-gallery-category.active",
            ".resource-manage-button",
            ".prompt-copy-button",
            ".image-editor-tool.active",
        ):
            with self.subTest(selector=selector):
                self.assertRegex(
                    styles,
                    rf"{re.escape(selector)}\s*\{{[^}}]*color:\s*var\(--primary-foreground\)",
                )

        for selector in (
            ".primary-button",
            ".run-button",
            ".segment.active",
            ".radio-btn.active",
            ".auth-source-button.active",
            ".system-settings-tab.active",
            ".system-settings-tabs.segmented-indicator-host .system-settings-tab.active",
            ".api-provider-choice.active",
            ".codex-channel-current",
        ):
            with self.subTest(selector=selector):
                self.assertNotRegex(
                    styles,
                    rf"{re.escape(selector)}\s*\{{[^}}]*color:\s*(white|#fff)",
                )
    def test_dark_theme_image_input_and_gallery_use_theme_surfaces(self) -> None:
        styles = Path("codex_image/webui/static/styles.css").read_text(encoding="utf-8")
        image_input_block = self._extract_css_block(styles, ".image-input-main")
        quick_center_block = self._extract_css_block(styles, ".quick-gallery-item.center")
        quick_hover_block = self._extract_css_block(styles, ".quick-gallery-item:hover,\n.quick-gallery-item.active")

        self.assertIn("color-mix(in srgb, var(--surface-soft)", image_input_block)
        self.assertNotIn("rgba(255,255,255", image_input_block)
        self.assertNotIn("rgba(237, 246, 242", image_input_block)
        self.assertIn("var(--primary-light)", quick_center_block)
        self.assertIn("var(--primary-light)", quick_hover_block)
        self.assertNotIn("rgba(231, 242, 237", quick_center_block)
        self.assertNotIn("rgba(248, 251, 249", quick_hover_block)
    def test_dark_theme_panels_and_titles_use_soft_visual_hierarchy(self) -> None:
        styles = Path("codex_image/webui/static/styles.css").read_text(encoding="utf-8")
        panel_block = self._extract_css_block(styles, ".panel")
        panel_heading_block = self._extract_css_block(styles, ".panel h2")
        task_title_block = self._extract_css_block(styles, ".task-title")

        self.assertIn("--panel-border:", styles)
        self.assertIn("--section-heading:", styles)
        self.assertIn("--task-title:", styles)
        self.assertRegex(styles, r":root\[data-theme=\"dark\"\]\s*\{[\s\S]*--panel-border:\s*color-mix\(in srgb, var\(--line\) 58%, transparent\);")
        self.assertRegex(styles, r":root\[data-theme=\"dark\"\]\s*\{[\s\S]*--section-heading:\s*color-mix\(in srgb, var\(--text\) 58%, var\(--text-secondary\)\);")
        self.assertRegex(styles, r":root\[data-theme=\"dark\"\]\s*\{[\s\S]*--task-title:\s*color-mix\(in srgb, var\(--text\) 36%, var\(--text-secondary\)\);")
        self.assertIn("border: 1px solid var(--panel-border)", panel_block)
        self.assertRegex(styles, r"\.modal-panel\s*\{[^}]*width:\s*min\(920px,\s*94vw\)[^}]*border:\s*1px solid var\(--panel-border\)")
        self.assertRegex(styles, r"\.queue-drawer\s*\{[^}]*border-left:\s*1px solid var\(--panel-border\)")
        self.assertIn("color: var(--section-heading)", panel_heading_block)
        self.assertIn("color: var(--task-title)", task_title_block)
        self.assertNotIn("rgba(226, 232, 229", panel_block)
        self.assertNotRegex(styles, r"\.modal-panel\s*\{[^}]*width:\s*min\(920px,\s*94vw\)[^}]*rgba\(226, 232, 229")
        self.assertNotIn("rgba(226, 232, 229", styles)

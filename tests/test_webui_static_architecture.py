"""Module boundaries, registration and bootstrap order for the frontend."""

from pathlib import Path

from tests.webui_helpers import WebUIStaticTestCase


class FrontendArchitectureTests(WebUIStaticTestCase):
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
        self.assertIn('fetch("/api/reference-assets/recent?limit=50", { signal })', source)
        self.assertIn("const RECENT_ASSET_RENDER_BATCH_SIZE = 12", source)
        self.assertIn('loading="lazy" decoding="async"', source)
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
        self.assertIn("export function normalizeApiSettings(settings", Path("codex_image/webui/frontend/src/api-provider-model.ts").read_text(encoding="utf-8"))
        self.assertIn("export function openApiSettingsModal()", provider_source)
        self.assertIn("export function openGenerationProviderSettings()", provider_source)
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

    def test_storage_settings_feature_has_typescript_source_contract(self) -> None:
        storage_settings_source = self._storage_settings_source()
        legacy_source = self._bootstrap_source()
        main_source = Path("codex_image/webui/frontend/src/main.ts").read_text(encoding="utf-8")

        self.assertIn('import { initStorageSettingsFeature } from "./storage-settings"', main_source)
        self.assertLess(main_source.index('import { initStorageSettingsFeature } from "./storage-settings"'), main_source.index('import { initPromptFeature } from "./prompt"'))
        self.assertLess(main_source.index("initStorageSettingsFeature()"), main_source.index("initPromptFeature()"))
        self.assertIn("export function initStorageSettingsFeature", storage_settings_source)
        self.assertIn("async function refreshSettings(options: { afterRestore?: boolean } = {})", storage_settings_source)
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
        generation_request_source = Path("codex_image/webui/frontend/src/generation-request.ts").read_text(encoding="utf-8")
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
        self.assertNotIn('form.append("resolution"', task_submit_source)
        self.assertNotIn('form.append("ratio"', task_submit_source)
        self.assertNotIn('form.append("orientation"', task_submit_source)
        self.assertIn("appendCanonicalGenerationFields(form, currentGenerationSelection())", task_submit_source)
        self.assertIn('form.append("canonical_model_id", selection.canonicalModelId)', generation_request_source)
        self.assertIn('form.append("provider_id", selection.providerId)', generation_request_source)
        self.assertIn('form.append("parameters_json", JSON.stringify(sortedRecord(selection.parameters)))', generation_request_source)
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

    def test_lightbox_feature_has_typescript_source_contract(self) -> None:
        lightbox_source = self._lightbox_source()
        legacy_source = self._bootstrap_source()

        self.assertIn("export function initLightboxFeature", lightbox_source)
        self.assertIn("function openLightbox", lightbox_source)
        self.assertIn("function syncActiveLightboxUrls", lightbox_source)
        self.assertIn("openHistoryLightbox", lightbox_source)
        self.assertIn("closeHistoryLightbox", lightbox_source)
        self.assertIn("syncHistoryLightboxUrls", lightbox_source)
        self.assertIn("window.openLightbox = openLightbox", lightbox_source)
        self.assertIn("window.addToInput = addToInput", lightbox_source)
        self.assertIn("Object.assign(getLegacyBridge().methods", lightbox_source)
        self.assertNotIn("function ensureLightboxElement", lightbox_source)
        self.assertNotIn('class="lightbox-nav', lightbox_source)
        for function_name in [
            "isLightboxActive",
            "setLightboxTransform",
            "openLightbox",
            "closeLightbox",
        ]:
            self.assertNotRegex(legacy_source, rf"\n(?:async\s+)?function {function_name}\(")
        self.assertIn("function syncActiveLightboxUrls(): void", legacy_source)

    def test_color_palette_feature_has_typescript_source_contract(self) -> None:
        color_palette_source = self._color_palette_source()
        legacy_source = self._bootstrap_source()
        main_source = Path("codex_image/webui/frontend/src/main.ts").read_text(encoding="utf-8")

        self.assertIn('import { initColorPaletteFeature } from "./color-palette"', main_source)
        self.assertLess(main_source.index("initStorageSettingsFeature()"), main_source.index("initColorPaletteFeature()"))
        self.assertLess(main_source.index("initColorPaletteFeature()"), main_source.index("initPromptFeature()"))
        self.assertIn("export function initColorPaletteFeature", color_palette_source)
        self.assertIn("const DEFAULT_COLOR_SWATCHES", color_palette_source)
        self.assertIn("const COLOR_PALETTE_ENDPOINT", color_palette_source)
        self.assertIn("function defaultColorPalette()", color_palette_source)
        self.assertIn("async function refreshColorPalette()", color_palette_source)
        self.assertIn("function normalizeHexColor(value)", color_palette_source)
        self.assertIn("Object.assign(getLegacyBridge().methods", color_palette_source)
        for function_name in [
            "defaultColorPalette",
            "normalizeColorPalette",
            "refreshColorPalette",
            "persistColorPalette",
            "importColorPalette",
            "toggleColorPaletteManageMode",
            "favoriteColorsForDisplay",
            "recentColorsForDisplay",
            "rememberRecentColor",
            "saveFavoriteColor",
            "removeFavoriteColor",
            "normalizeHexColor",
        ]:
            self.assertNotRegex(legacy_source, rf"\n(?:async\s+)?function {function_name}\(")
        for function_name in [
            "refreshColorPalette",
            "importColorPalette",
            "toggleColorPaletteManageMode",
            "favoriteColorsForDisplay",
            "recentColorsForDisplay",
            "rememberRecentColor",
            "saveFavoriteColor",
            "removeFavoriteColor",
            "normalizeHexColor",
        ]:
            self._assert_bootstrap_proxy(legacy_source, function_name)

    def test_prompt_chip_logic_has_typescript_source_contract(self) -> None:
        prompt_source = self._prompt_source()
        core_source = "\n".join(
            [
                prompt_source,
                self._prompt_serialization_source(),
                self._prompt_gallery_chips_source(),
                self._prompt_editor_events_source(),
                self._prompt_model_source(),
            ]
        )
        legacy_source = self._bootstrap_source()
        main_source = Path("codex_image/webui/frontend/src/main.ts").read_text(encoding="utf-8")

        self.assertNotIn("@ts-nocheck", prompt_source)
        self.assertIn('from "./prompt-serialization"', prompt_source)
        self.assertIn('from "./prompt-gallery-chips"', prompt_source)
        self.assertIn('from "./prompt-editor-events"', prompt_source)
        self.assertIn('from "./prompt-model"', prompt_source)
        for marker in [
            "export function initPromptFeature",
            "function createGalleryChip",
            "function buildPromptForModel",
            "function galleryPrompt",
            "function syncPromptGalleryMentionsFromInputs",
            "function handlePromptChipDrop",
            "function getPromptText",
            "function normalizePromptEditorText",
            "function createPromptTextFragment",
            "function setPromptWithGalleryRefs",
            "function currentPromptFidelity",
        ]:
            self.assertIn(marker, core_source)
        self.assertIn('return String(value || "").replace(/\\r\\n?/g, "\\n");', core_source)
        self.assertIn('document.createElement("br")', core_source)
        self.assertIn("document.createDocumentFragment()", core_source)
        self.assertRegex(
            core_source,
            r"function setPromptText\(text: any\): void\s*\{[\s\S]*normalizePromptEditorText\(text\)[\s\S]*createPromptTextFragment\(normalized\)",
        )
        self.assertRegex(
            core_source,
            r"function setPromptWithGalleryRefs\(text: any,\s*refs: any, mentions\?: ImageMentionContext, sources: any\[\] = \[\]\): void\s*\{[\s\S]*const promptText = normalizePromptEditorText\(text\)",
        )

        for function_name in [
            "getPromptText",
            "setPromptWithGalleryRefs",
            "syncPromptFromEditor",
            "createGalleryChip",
            "createPromptSnippetChip",
            "buildPromptForModel",
            "currentPromptForModel",
            "currentPromptFidelity",
            "syncGalleryInputsFromPrompt",
            "syncPromptGalleryMentionsFromInputs",
        ]:
            self._assert_bootstrap_proxy(legacy_source, function_name)

        self.assertIn("Object.assign(getLegacyBridge().methods", core_source)
        self.assertIn('addEventListener("copy", handlePromptEditorCopy)', core_source)
        self.assertIn('addEventListener("dragstart", handlePromptChipDragStart)', core_source)
        self.assertLess(main_source.index('import "../legacy-app.js"'), main_source.index('import { initInputSourcesFeature } from "./input-sources"'))
        self.assertLess(main_source.index("initInputSourcesFeature()"), main_source.index("initImageEditorFeature()"))
        self.assertLess(main_source.index("initImageEditorFeature()"), main_source.index("initPromptFeature()"))
        self.assertLess(main_source.index("initPromptFeature()"), main_source.index("initTaskListControlsFeature()"))
        self.assertLess(main_source.index("initTaskListControlsFeature()"), main_source.index("initTaskFeature()"))
        self.assertLess(main_source.index("initTaskFeature()"), main_source.index("initializeQueueFeature()"))

    def test_prompt_colors_feature_has_typescript_source_contract(self) -> None:
        source = self._prompt_colors_source()
        prompt_source = self._prompt_source()
        main_source = Path("codex_image/webui/frontend/src/main.ts").read_text(encoding="utf-8")

        self.assertNotIn("@ts-nocheck", source)
        self.assertIn('import { initPromptColorsFeature } from "./prompt-colors"', main_source)
        self.assertLess(main_source.index("initPromptColorsFeature()"), main_source.index("initPromptFeature()"))
        for marker in [
            "DEFAULT_COLOR_CODE",
            "COLOR_PALETTE_EXPORT_CSS_ENDPOINT",
            "export function initPromptColorsFeature",
            "function activeColorMatch",
            "function renderColorSuggest",
            "function insertColorCode",
            "function createColorChip",
            "function readableTextColor",
            "function hideColorSuggest",
        ]:
            self.assertIn(marker, source)
        for function_name in [
            "updateColorSuggest",
            "activeColorMatch",
            "renderColorSuggest",
            "bindColorSuggestEvents",
            "insertColorCode",
            "positionColorSuggestAtCaret",
            "openColorChipEditor",
            "positionColorSuggestAtChip",
            "colorNameForHex",
            "colorSwatchButton",
            "createColorChip",
            "updateColorChip",
            "readableTextColor",
            "hexToRgb",
            "mixRgbWithWhite",
            "relativeLuminance",
            "contrastRatio",
            "hideColorSuggest",
        ]:
            self.assertRegex(source, rf"\nfunction {function_name}\(")
            self.assertNotRegex(prompt_source, rf"\nfunction {function_name}\(")
        self.assertIn("Object.assign(getLegacyBridge().methods", source)

    def test_prompt_snippets_feature_has_typescript_source_contract(self) -> None:
        source = self._prompt_snippets_source()
        prompt_source = self._prompt_source()
        main_source = Path("codex_image/webui/frontend/src/main.ts").read_text(encoding="utf-8")

        self.assertNotIn("@ts-nocheck", source)
        self.assertIn('import { initPromptSnippetsFeature } from "./prompt-snippets"', main_source)
        self.assertLess(main_source.index("initPromptSnippetsFeature()"), main_source.index("initPromptFeature()"))
        for marker in [
            "PROMPT_SNIPPETS_ENDPOINT",
            "PROMPT_SNIPPET_TRIGGER_PATTERN",
            "export function initPromptSnippetsFeature",
            "function createPromptSnippetChip",
            "function expandPromptSnippets",
            "function updatePromptSnippetSuggest",
            "function getPromptSelectionForSnippet",
            "function openPromptSnippetSavePopover",
            "function closePromptSnippetPopover",
        ]:
            self.assertIn(marker, source)
        self.assertIn('candidate.length === 1 && PROMPT_SNIPPET_TRIGGER_CHARS.includes(candidate)', source)
        for function_name in [
            "normalizePromptSnippet",
            "refreshPromptSnippets",
            "activePromptSnippetMatch",
            "insertPromptSnippet",
            "createPromptSnippetChip",
            "findPromptSnippetRefAt",
            "findPromptSnippetById",
            "findPromptSnippetByTag",
            "expandPromptSnippets",
            "updatePromptSnippetSelectionButton",
            "showPromptSnippetSelectionButton",
            "openPromptSnippetSavePopover",
            "openPromptSnippetChipPopover",
            "savePromptSnippetFromPopover",
            "closePromptSnippetPopover",
            "hidePromptSnippetSuggest",
        ]:
            self.assertRegex(source, rf"\n(?:async\s+)?function {function_name}\(")
            self.assertNotRegex(prompt_source, rf"\n(?:async\s+)?function {function_name}\(")
        self.assertIn("Object.assign(getLegacyBridge().methods", source)

    def test_prompt_templates_feature_has_typescript_source_contract(self) -> None:
        source = self._prompt_templates_source()
        prompt_source = self._prompt_source()
        main_source = Path("codex_image/webui/frontend/src/main.ts").read_text(encoding="utf-8")
        boot_source = Path("codex_image/webui/frontend/src/boot.ts").read_text(encoding="utf-8")
        bootstrap_source = self._bootstrap_source()

        self.assertNotIn("@ts-nocheck", source)
        self.assertIn('import { initPromptTemplatesFeature } from "./prompt-templates"', main_source)
        self.assertLess(main_source.index("initPromptSnippetsFeature()"), main_source.index("initPromptTemplatesFeature()"))
        self.assertLess(main_source.index("initPromptTemplatesFeature()"), main_source.index("initPromptFeature()"))
        self.assertIn('call(methods, "refreshPromptTemplates")', boot_source)
        self._assert_bootstrap_proxy(bootstrap_source, "refreshPromptTemplates")
        for marker in [
            "PROMPT_TEMPLATES_ENDPOINT",
            "PROMPT_TEMPLATE_CATEGORIES_ENDPOINT",
            "export function initPromptTemplatesFeature",
            "function normalizePromptTemplate",
            "function normalizePromptTemplateCategory",
            "function refreshPromptTemplates",
            "function syncPromptTemplateSearchInput",
            "function setPromptTemplateSearchLocked",
            "function guardPromptTemplateSearchInput",
            "function openPromptTemplateDrawer",
            "function renderPromptTemplateCategories",
            "function renderPromptTemplateList",
            "function historyTemplateThumbnails",
            "function renderPromptTemplateThumbnailPicker",
            "function applyPromptTemplate",
            "function importPromptTemplatePack",
            "function exportPromptTemplatePack",
            "function setPromptTemplateSummary",
            "function savePromptTemplateFromDrawer",
        ]:
            self.assertIn(marker, source)
        for function_name in [
            "normalizePromptTemplate",
            "normalizePromptTemplateCategory",
            "refreshPromptTemplates",
            "openPromptTemplateDrawer",
            "closePromptTemplateDrawer",
            "renderPromptTemplateCategories",
            "renderPromptTemplateList",
            "renderPromptTemplateRecentDock",
            "selectPromptTemplate",
            "applyPromptTemplate",
            "copyPromptTemplateContent",
            "historyTemplateThumbnails",
            "renderPromptTemplateThumbnailPicker",
            "importPromptTemplatePack",
            "exportPromptTemplatePack",
            "setPromptTemplateSummary",
            "createPromptTemplateCategory",
            "updatePromptTemplateCategory",
            "deletePromptTemplateCategory",
            "renderPromptTemplateForm",
            "savePromptTemplateFromDrawer",
            "deletePromptTemplate",
        ]:
            self.assertRegex(source, rf"\n(?:async\s+)?function {function_name}\(")
            self.assertNotRegex(prompt_source, rf"\n(?:async\s+)?function {function_name}\(")
        self.assertIn("Object.assign(getLegacyBridge().methods", source)
        overlay_source = Path("codex_image/webui/frontend/src/overlay-popovers.ts").read_text(encoding="utf-8")
        self.assertIn("function closePromptTemplateDrawer()", overlay_source)
        self.assertIn("closePromptTemplateDrawer();", overlay_source)
        self.assertIn('legacyMethod("closeGallery", { restoreFocus: false })', source)

    def test_prompt_editor_core_modules_have_typescript_source_contract(self) -> None:
        prompt_source = self._prompt_source()
        serialization_source = self._prompt_serialization_source()
        gallery_chips_source = self._prompt_gallery_chips_source()
        editor_events_source = self._prompt_editor_events_source()
        model_source = self._prompt_model_source()

        for source in (
            serialization_source,
            gallery_chips_source,
            editor_events_source,
            model_source,
        ):
            self.assertNotIn("@ts-nocheck", source)
            self.assertIn('import { getLegacyBridge } from "./state"', source)
            self.assertIn("Object.assign(getLegacyBridge().methods", source)

        for symbol in (
            "getPromptText",
            "promptTextFromNode",
            "promptSelectionText",
            "promptTextFromRange",
            "rangeIntersectsNode",
            "selectPromptEditorContents",
        ):
            self.assertIn(f"export function {symbol}", serialization_source)
            self.assertIn(symbol, prompt_source)

        for symbol in (
            "createGalleryChip",
            "findGalleryRefMentionAt",
            "syncGalleryInputsFromPrompt",
            "syncPromptGalleryMentionsFromInputs",
            "insertGalleryMention",
            "hideMentionSuggest",
        ):
            self.assertIn(f"export function {symbol}", gallery_chips_source)
            self.assertIn(symbol, prompt_source)

        for symbol in (
            "handlePromptEditorCopy",
            "updatePromptChipSelectionState",
            "handlePromptEditorDrop",
            "bindPromptEditorEvents",
            "syncPromptFromEditor",
        ):
            self.assertIn(f"export function {symbol}", editor_events_source)
            self.assertIn(symbol, prompt_source)

        for symbol in (
            "currentPromptForModel",
            "promptTokenReplacement",
            "galleryPrompt",
        ):
            self.assertIn(f"export function {symbol}", model_source)
            self.assertIn(symbol, prompt_source)

        self.assertIn('from "./prompt-serialization"', prompt_source)
        self.assertIn('from "./prompt-gallery-chips"', prompt_source)
        self.assertIn('from "./prompt-editor-events"', prompt_source)
        self.assertIn('from "./prompt-model"', prompt_source)
        self.assertLessEqual(len(prompt_source.splitlines()), 220)

    def test_task_list_controls_feature_has_typescript_source_contract(self) -> None:
        task_list_controls_source = self._task_list_controls_source()
        legacy_source = self._bootstrap_source()
        main_source = Path("codex_image/webui/frontend/src/main.ts").read_text(encoding="utf-8")

        self.assertIn('import { initTaskListControlsFeature } from "./task-list-controls"', main_source)
        self.assertIn('import { initTaskListRenderFeature } from "./task-list-render"', main_source)
        self.assertIn('import { initTaskArchiveControlsFeature } from "./task-archive-controls"', main_source)
        self.assertIn('import { initTaskBatchControlsFeature } from "./task-batch-controls"', main_source)
        self.assertIn('import { initTaskActionsFeature } from "./task-actions"', main_source)
        self.assertIn('import { initTaskCardSwipeFeature } from "./task-card-swipe"', main_source)
        self.assertIn('import { initTaskSubmitFeature } from "./task-submit"', main_source)
        self.assertLess(main_source.index('import { initPromptFeature } from "./prompt"'), main_source.index('import { initTaskListControlsFeature } from "./task-list-controls"'))
        self.assertLess(main_source.index('import { initTaskListControlsFeature } from "./task-list-controls"'), main_source.index('import { initTaskFeature } from "./tasks"'))
        self.assertLess(main_source.index("initPromptFeature()"), main_source.index("initTaskListControlsFeature()"))
        self.assertLess(main_source.index("initTaskListControlsFeature()"), main_source.index("initTaskCardSwipeFeature()"))
        self.assertLess(main_source.index("initTaskCardSwipeFeature()"), main_source.index("initTaskFeature()"))
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
        self.assertIn("function handleTaskCardArrowNavigation", task_list_controls_source)
        self.assertIn('event.key !== "ArrowUp" && event.key !== "ArrowDown"', task_list_controls_source)
        self.assertIn("function isTaskListKeyboardInputTarget", task_list_controls_source)
        self.assertIn('target.closest("button, input, select, textarea, a, [contenteditable=\'true\'], [role=\'textbox\']")', task_list_controls_source)
        self.assertIn("if (isTaskListKeyboardInputTarget(event.target)) return;", task_list_controls_source)
        self.assertIn("isTaskListKeyboardInputTarget(event.target)", task_list_controls_source)
        self.assertIn('event.preventDefault();\n  event.stopPropagation();', task_list_controls_source)
        self.assertIn('void legacyMethod("selectTask", nextCard.dataset.taskId)', task_list_controls_source)
        self.assertIn('card.scrollIntoView({ block: "nearest", inline: "nearest" })', task_list_controls_source)
        self.assertIn("if (handleTaskCardArrowNavigation(card, event)) return;", task_list_controls_source)
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
        card_source = Path("codex_image/webui/frontend/src/task-card-view.ts").read_text(encoding="utf-8")
        model_source = Path("codex_image/webui/frontend/src/task-list-model.ts").read_text(encoding="utf-8")
        viewport_source = Path("codex_image/webui/frontend/src/task-list-viewport.ts").read_text(encoding="utf-8")
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
        self.assertNotIn("syncTaskHistoryAnchorInset", anchor_source)
        self.assertNotIn("taskHistoryAnchorInsetObserver", anchor_source)
        self.assertIn("scheduleLatestTaskNavigationRefresh();", anchor_source)
        self.assertIn("function scrollExpandedTaskGroupToTop(", anchor_source)
        self.assertIn("function renderTaskHistoryAnchors(", anchor_source)
        self.assertIn("state.expandedTaskGroupAnimationPending = true", anchor_source)
        self.assertIn("prefersReducedMotion", anchor_source)
        self.assertIn("expandedTaskGroupAnimationPending: false", state_defaults)
        self.assertIn("function finalizeExpandedTaskGroupBody(", viewport_source)
        self.assertIn("const shouldAnimateExpand = !preserveExisting && animationPending;", viewport_source)
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
        self.assertIn('taskHistoryCurrentAnchor: document.querySelector("#taskHistoryCurrentAnchor")', elements_source)
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
        self.assertIn("renderExpandedTaskGroupHeader(group, {", render_source)
        self.assertIn("startExpanded: !shouldAnimateExpandedGroup", render_source)
        self.assertIn("els.taskList.innerHTML = renderExpandedTaskGroupBodyShellHtml(group)", render_source)
        self.assertIn("renderTaskHistoryAnchors(", render_source)
        self.assertIn("top: groups", model_source)
        self.assertIn("expandedKey: groups[0]?.key || expandedKey || null", model_source)
        self.assertIn("data-task-group-toggle-key", card_source)
        self.assertNotIn('addGroup("active"', render_source)
        self.assertNotIn('id="taskExpandAllButton"', html)
        self.assertNotIn('id="taskCollapseAllButton"', html)
        self.assertIn('class="task-history-shell"', html)
        self.assertRegex(
            html,
            r'id="taskActiveList"[\s\S]*id="taskHistoryTopAnchors"[\s\S]*id="taskHistoryCurrentAnchor"[\s\S]*id="taskList"[\s\S]*id="taskHistoryBottomAnchors"[\s\S]*id="taskHistoryLibrarySlot"',
        )
        self.assertIn('id="taskHistoryTopAnchors"', html)
        self.assertIn('id="taskHistoryBottomAnchors"', html)
        self.assertRegex(styles, r"\.task-active-list\s*\{[^}]*scrollbar-gutter:\s*stable")
        self.assertRegex(styles, r"\.task-active-list\s*\{[^}]*overflow-x:\s*hidden")
        self.assertNotRegex(
            styles,
            r"\.task-active-list\s*\{[^}]*padding-right:\s*var\(--task-history-scrollbar-offset",
        )
        self.assertRegex(styles, r"\.sidebar-content,\s*[\s\S]*\.task-active-list,\s*[\s\S]*\.dashboard,\s*[\s\S]*scrollbar-width:\s*thin")
        self.assertIn("function collapseExpandedTaskGroup(", controls_source)
        self.assertIn("setExpandedTaskGroupKey(null", controls_source)
        self.assertNotIn('const nextKey = String(state.expandedTaskGroupKey) === key ? replacementGroupKey(key) : key;', controls_source)
        self.assertNotIn("setAllTaskGroupsCollapsed", controls_source)

    def test_task_split_modules_have_typescript_source_contract(self) -> None:
        card_source = Path("codex_image/webui/frontend/src/task-card-view.ts").read_text(encoding="utf-8")
        model_source = Path("codex_image/webui/frontend/src/task-list-model.ts").read_text(encoding="utf-8")
        render_source = self._task_list_render_source()
        actions_source = self._task_actions_source()
        submit_source = self._task_submit_source()
        batch_source = self._task_batch_controls_source()
        archive_source = self._task_archive_controls_source()

        for source in [render_source, actions_source, submit_source, batch_source, archive_source]:
            self.assertNotIn("@ts-nocheck", source)

        for marker in [
            "export function initTaskListRenderFeature",
            "function renderTasks(options: { preserveScroll?: boolean; appendGroupKey?: string } = {})",
            "function taskSearchQuery()",
            "function filteredVisibleTasks(",
        ]:
            self.assertIn(marker, render_source)
        self.assertIn("function taskCardHtml(", card_source)
        self.assertIn("function taskHistoryGroups(", model_source)
        self.assertIn("function taskMetaText(", card_source)
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
            "function syncBatchTaskSelectionVisuals(",
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
            "function migrateLegacyArchivedTasks()",
            "function renderArchiveButton()",
            "async function restoreArchivedTask(",
            "function openArchiveModal()",
            "function closeArchiveModal()",
            "function renderArchiveModal()",
        ]:
            self.assertIn(marker, archive_source)

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
        self.assertIn("if (taskWasCancelled(nextTask)) return;", source)
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
        self.assertIn("ensureSelectedTaskDetail(selectedTask.task_id, { signal })", task_source)
        self.assertIn("renderPreview(detailedTask)", task_source)
        self.assertIn("await renderSelectedTaskPreview(requestSeq, signal)", task_source)
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
        self.assertIn("function taskRequestedSize(task: any)", source)
        self.assertIn("function taskOutputSize(task: any)", source)
        self.assertIn("function parseTaskSizeDimensions(size: any)", source)
        self.assertIn("return parseTaskSizeDimensions(taskRequestedSize(task)) || parseTaskSizeDimensions(taskOutputSize(task));", source)
        self.assertNotIn('String(task?.output_size || task?.params?.size || task?.request?.size || "")', source)
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
            "taskDurationText",
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

from __future__ import annotations

from pathlib import Path
import unittest


class WebUIStaticStartupPerformanceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.recent_assets = Path("codex_image/webui/frontend/src/recent-assets.ts").read_text(encoding="utf-8")
        self.gallery = Path("codex_image/webui/frontend/src/gallery.ts").read_text(encoding="utf-8")
        self.gallery_grid = Path("codex_image/webui/frontend/src/gallery-grid.ts").read_text(encoding="utf-8")
        self.gallery_categories = Path("codex_image/webui/frontend/src/gallery-categories.ts").read_text(encoding="utf-8")
        self.templates = Path("codex_image/webui/frontend/src/prompt-templates.ts").read_text(encoding="utf-8")

    def test_recent_assets_render_in_small_lazy_batches(self) -> None:
        self.assertIn("const RECENT_ASSET_RENDER_BATCH_SIZE = 12", self.recent_assets)
        self.assertIn("items.slice(0, recentAssetRenderLimit)", self.recent_assets)
        self.assertIn('loading="lazy" decoding="async"', self.recent_assets)
        self.assertIn('addEventListener("scroll", handleRecentAssetScroll', self.recent_assets)
        self.assertIn('addEventListener("click", handleRecentAssetClick)', self.recent_assets)
        self.assertNotIn('querySelectorAll("[data-reference-asset-id]").forEach', self.recent_assets)

    def test_hidden_media_drawers_do_not_render_their_grids_at_boot(self) -> None:
        self.assertRegex(
            self.gallery,
            r'if \(els\.galleryDrawer\?\.classList\.contains\("open"\)\)\s+renderGalleryGrid\(\)',
        )
        self.assertRegex(
            self.templates,
            r'if \(promptTemplateDrawerIsOpen\(\)\)\s*\{[^}]*renderPromptTemplateList\(\)',
        )
        self.assertRegex(
            self.gallery_grid,
            r'LOCALE_CHANGE_EVENT[\s\S]*if \(els\.galleryDrawer\?\.classList\.contains\("open"\)\) renderGalleryGrid\(\)',
        )
        self.assertRegex(
            self.gallery_categories,
            r'LOCALE_CHANGE_EVENT[\s\S]*if \(els\.galleryDrawer\?\.classList\.contains\("open"\)\) renderGalleryGrid\(\)',
        )
        self.assertRegex(
            self.templates,
            r'LOCALE_CHANGE_EVENT[\s\S]*if \(promptTemplateDrawerIsOpen\(\)\)\s*\{[^}]*renderPromptTemplateList\(\)',
        )
        self.assertIn('loading="lazy" decoding="async"', self.gallery_grid)
        self.assertIn('loading="lazy" decoding="async"', self.templates)



if __name__ == "__main__":
    unittest.main()

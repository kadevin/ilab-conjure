from __future__ import annotations

from tests.frontend_runner import frontend_test

import shutil
import subprocess
from pathlib import Path

from tests.webui_helpers import WebUIStaticTestCase


class WebUIOutputControlsTests(WebUIStaticTestCase):
    def run_node(self, harness: str) -> None:
        node = shutil.which("node")
        if node is None:
            self.skipTest("node is required for frontend behavior checks")
        result = subprocess.run([node, "-e", harness], text=True, capture_output=True, check=False)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    @frontend_test
    def test_recent_preview_preference_handles_storage_failure(self) -> None:
        script = self._frontend_script_source()
        self.run_node("\n".join([
            """
            const assert = require('node:assert/strict');
            const RECENT_ASSET_PREVIEW_VISIBILITY_KEY = 'codex-image-recent-asset-previews-hidden';
            let recentAssetPreviewsHidden = false, stored = null, renders = 0;
            let localStorage = { getItem: () => stored, setItem: (key, value) => { stored = value; } };
            const syncRecentAssetPreviewVisibility = () => renders++;
            """,
            self._extract_javascript_function(script, "readRecentAssetPreviewsHidden"),
            self._extract_javascript_function(script, "toggleRecentAssetPreviews"),
            """
            assert.equal(readRecentAssetPreviewsHidden(), false);
            stored = 'unexpected';
            assert.equal(readRecentAssetPreviewsHidden(), false);
            toggleRecentAssetPreviews();
            assert.equal(readRecentAssetPreviewsHidden(), true);
            toggleRecentAssetPreviews();
            assert.equal(readRecentAssetPreviewsHidden(), false);
            localStorage = {
              getItem() { throw new Error('blocked'); },
              setItem() { throw new Error('quota'); },
            };
            assert.equal(readRecentAssetPreviewsHidden(), false);
            toggleRecentAssetPreviews();
            assert.equal(recentAssetPreviewsHidden, true);
            assert.equal(renders, 3, 'storage failure does not block the visible toggle');
            """,
        ]))

    @frontend_test
    def test_output_radio_keyboard_skips_disabled_and_wraps(self) -> None:
        script = self._frontend_script_source()
        self.run_node("\n".join([
            """
            const assert = require('node:assert/strict');
            const handlers = {};
            let observer;
            let focused;
            const buttons = [0, 1, 2].map(index => ({
              disabled: index === 1, active: index === 0, attrs: {},
              classList: { contains: name => name === 'active' && buttons[index].active },
              setAttribute(name, value) { this.attrs[name] = value; },
              removeAttribute(name) { delete this.attrs[name]; },
              closest: selector => selector === '.radio-btn' ? buttons[index] : group,
              focus() { focused = this; },
              click() { buttons.forEach(button => button.active = button === this); },
            }));
            const group = { querySelectorAll: () => buttons, setAttribute() {} };
            const root = {
              querySelectorAll: () => [group], contains: candidate => candidate === group,
              addEventListener: (name, handler) => handlers[name] = handler,
            };
            const document = { getElementById: () => root };
            class MutationObserver { constructor(callback) { observer = callback; } observe() {} }
            """,
            self._extract_javascript_function(script, "syncOutputRadioGroup"),
            self._extract_javascript_function(script, "initOutputParameterKeyboard"),
            """
            initOutputParameterKeyboard();
            assert.deepEqual(buttons.map(b => b.tabIndex), [0, -1, -1]);
            let prevented = 0;
            const press = key => handlers.keydown({ target: focused || buttons[0], key, preventDefault: () => prevented++ });
            press('ArrowRight');
            assert.equal(focused, buttons[2]);
            assert.equal(buttons[2].attrs['aria-checked'], 'true');
            assert.deepEqual(buttons.map(b => b.tabIndex), [-1, -1, 0]);
            press('ArrowDown');
            assert.equal(focused, buttons[0], 'wrap at the end');
            press('ArrowLeft');
            assert.equal(focused, buttons[2], 'wrap at the beginning');
            press('Tab');
            assert.equal(prevented, 3, 'leave normal Tab navigation to the browser');
            buttons[1].disabled = false;
            observer();
            press('ArrowUp');
            assert.equal(focused, buttons[1], 'catalog updates can enable a choice');
            assert.equal(buttons.filter(b => b.tabIndex === 0).length, 1);
            """,
        ]))

    def test_gallery_minimum_height_and_no_duplicate_pixel_row(self) -> None:
        responsive = Path("codex_image/webui/static/styles/80-utilities-responsive.css").read_text(encoding="utf-8")
        gallery = Path("codex_image/webui/static/styles/50-image-input-gallery.css").read_text(encoding="utf-8")
        output = Path("codex_image/webui/static/styles/70-output-settings.css").read_text(encoding="utf-8")
        self.assertRegex(responsive, r"--image-input-main-height:\s*clamp\(\s*102px")
        self.assertRegex(responsive, r"\.controls-col \.image-input-workspace\s*\{[^}]*min-height:\s*var\(--image-input-total-height\)")
        self.assertRegex(gallery, r"\.quick-gallery-empty\s*\{[^}]*min-height:\s*min\(110px, var\(--quick-gallery-height\)\)")
        self.assertNotIn(".pixel-preview", output)

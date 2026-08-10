from __future__ import annotations

import re
import unittest
from pathlib import Path


def _relative_luminance(hex_color: str) -> float:
    channels = [
        int(hex_color[index:index + 2], 16) / 255
        for index in (1, 3, 5)
    ]
    linear = [
        channel / 12.92
        if channel <= 0.04045
        else ((channel + 0.055) / 1.055) ** 2.4
        for channel in channels
    ]
    return (
        0.2126 * linear[0]
        + 0.7152 * linear[1]
        + 0.0722 * linear[2]
    )


def _contrast_ratio(first: str, second: str) -> float:
    first_luminance = _relative_luminance(first)
    second_luminance = _relative_luminance(second)
    lighter = max(first_luminance, second_luminance)
    darker = min(first_luminance, second_luminance)
    return (lighter + 0.05) / (darker + 0.05)


def _hex_token(source: str, name: str) -> str:
    match = re.search(
        rf"{re.escape(name)}:\s*(#[0-9a-fA-F]{{6}})\s*;",
        source,
    )
    if match is None:
        raise AssertionError(f"Missing hex token: {name}")
    return match.group(1)


class WebUIStaticAccessibilityTests(unittest.TestCase):
    def test_small_secondary_text_tokens_meet_wcag_aa_in_both_themes(
        self,
    ) -> None:
        tokens = Path(
            "codex_image/webui/static/styles/00-tokens.css"
        ).read_text(encoding="utf-8")
        light, dark = tokens.split(':root[data-theme="dark"]', 1)

        light_muted = _hex_token(light, "--text-muted")
        dark_muted = _hex_token(dark, "--text-muted")
        self.assertGreaterEqual(
            _contrast_ratio(light_muted, "#f8faf9"),
            4.5,
        )
        self.assertGreaterEqual(
            _contrast_ratio(dark_muted, "#1e2b26"),
            4.5,
        )

        component_styles = "\n".join(
            path.read_text(encoding="utf-8")
            for path in Path(
                "codex_image/webui/static/styles"
            ).glob("*.css")
        )
        self.assertNotIn("color: var(--muted);", component_styles)

        html = Path(
            "codex_image/webui/static/index.html"
        ).read_text(encoding="utf-8")
        pixel_preview = html[
            html.index('id="pixelPreview"'):
            html.index('id="size"', html.index('id="pixelPreview"'))
        ]
        self.assertIn("color: var(--primary-strong)", pixel_preview)

    def test_static_segmented_controls_announce_group_and_pressed_state(
        self,
    ) -> None:
        html = Path(
            "codex_image/webui/static/index.html"
        ).read_text(encoding="utf-8")
        for group_id in (
            "promptFidelityGroup",
            "orientationGroup",
            "resolutionGroup",
            "ratioGroup",
            "qualityGroup",
            "quantityGroup",
            "outputFormatGroup",
            "moderationGroup",
        ):
            tag = re.search(
                rf"<div\b[^>]*\bid=\"{group_id}\"[^>]*>",
                html,
            )
            self.assertIsNotNone(tag, group_id)
            self.assertIn('role="group"', tag.group(0))
            self.assertRegex(
                tag.group(0),
                r'aria-(?:label|labelledby)="[^"]+"',
            )

        inline_script = html[html.index("document.querySelectorAll"):
                             html.index("</script>", html.index("document.querySelectorAll"))]
        self.assertIn(
            'button.setAttribute("aria-pressed", String(active))',
            inline_script,
        )

    def test_compact_controls_balance_mouse_precision_and_touch_targets(
        self,
    ) -> None:
        responsive = Path(
            "codex_image/webui/static/styles/80-utilities-responsive.css"
        ).read_text(encoding="utf-8")
        image_input = Path(
            "codex_image/webui/static/styles/50-image-input-gallery.css"
        ).read_text(encoding="utf-8")

        self.assertRegex(
            responsive,
            r"--compact-settings-control-height:\s*clamp\(\s*24px,",
        )
        self.assertRegex(
            responsive,
            r"--compact-settings-segment-height:\s*clamp\(\s*24px,",
        )
        delete_button = re.search(
            r"\.recent-asset-delete\s*\{(?P<body>[^}]*)\}",
            image_input,
        )
        self.assertIsNotNone(delete_button)
        self.assertRegex(delete_button.group("body"), r"width:\s*18px")
        self.assertRegex(delete_button.group("body"), r"height:\s*18px")
        asset_size = re.search(
            r"--recent-asset-size:\s*(\d+)px",
            image_input,
        )
        delete_width = re.search(
            r"width:\s*(\d+)px",
            delete_button.group("body"),
        )
        self.assertIsNotNone(asset_size)
        self.assertIsNotNone(delete_width)
        self.assertLessEqual(
            int(delete_width.group(1)) / int(asset_size.group(1)),
            0.6,
            "mouse delete action must not dominate the thumbnail selection target",
        )
        self.assertRegex(
            image_input,
            r"@media \(hover: none\), \(pointer: coarse\)\s*\{\s*"
            r"\.recent-asset-list\s*\{[^}]*padding:\s*4px 4px 0 0[^}]*\}\s*"
            r"\.recent-asset-delete\s*\{[^}]*top:\s*-4px"
            r"[^}]*width:\s*24px[^}]*height:\s*24px",
        )

        recent_list = re.search(
            r"\.recent-asset-list\s*\{(?P<body>[^}]*)\}",
            image_input,
        )
        self.assertIsNotNone(recent_list)
        padding_top = re.search(
            r"padding:\s*(-?\d+)px",
            recent_list.group("body"),
        )
        delete_top = re.search(
            r"top:\s*(-?\d+)px",
            delete_button.group("body"),
        )
        self.assertIsNotNone(padding_top)
        self.assertIsNotNone(delete_top)
        self.assertGreaterEqual(
            int(padding_top.group(1)) + int(delete_top.group(1)),
            0,
            "recent asset action must stay inside the scrollport clip boundary",
        )

    def test_recent_asset_loading_keeps_thumbnail_rail_on_existing_grid_track(
        self,
    ) -> None:
        image_input = Path(
            "codex_image/webui/static/styles/50-image-input-gallery.css"
        ).read_text(encoding="utf-8")
        recent_assets = Path(
            "codex_image/webui/frontend/src/recent-assets.ts"
        ).read_text(encoding="utf-8")

        self.assertRegex(
            image_input,
            r"\.recent-asset-list\s*\{[^}]*grid-row:\s*1",
        )
        self.assertRegex(
            image_input,
            r"\.recent-asset-status\.is-loading\s*\{[^}]*position:\s*absolute",
        )
        self.assertRegex(
            image_input,
            r"\.recent-asset-dock\.is-loading\s+\.recent-asset-visibility-toggle::after",
        )
        self.assertIn(
            'classList.toggle("is-loading", recentAssetLoadState === "loading")',
            recent_assets,
        )

    def test_auxiliary_resource_failures_remain_visible_and_retryable(
        self,
    ) -> None:
        html = Path(
            "codex_image/webui/static/index.html"
        ).read_text(encoding="utf-8")
        recent_assets = Path(
            "codex_image/webui/frontend/src/recent-assets.ts"
        ).read_text(encoding="utf-8")
        prompt_templates = Path(
            "codex_image/webui/frontend/src/prompt-templates.ts"
        ).read_text(encoding="utf-8")

        self.assertIn('id="recentAssetStatus"', html)
        self.assertIn('role="status"', html)
        self.assertIn("data-recent-assets-retry", recent_assets)
        self.assertIn("data-prompt-template-retry", prompt_templates)
        self.assertIn('setAttribute("aria-busy"', recent_assets)
        self.assertIn('setAttribute("aria-busy"', prompt_templates)
        self.assertNotRegex(
            recent_assets,
            r"catch\s*\{[\s\S]{0,160}state\.recentAssets\s*=\s*\[\]",
        )
        self.assertNotRegex(
            prompt_templates,
            r"catch\s*\([^)]*\)\s*\{[\s\S]{0,240}state\.promptTemplates\s*=\s*\[\]",
        )

    def test_generation_page_has_a_page_level_heading(self) -> None:
        html = Path(
            "codex_image/webui/static/index.html"
        ).read_text(encoding="utf-8")
        self.assertRegex(
            html,
            r"<main\b[^>]*>[\s\S]*?<h1\b[^>]*class=\"sr-only\"",
        )

    def test_history_cards_keep_nested_actions_out_of_listbox_semantics(
        self,
    ) -> None:
        html = Path(
            "codex_image/webui/static/history.html"
        ).read_text(encoding="utf-8")
        source = Path(
            "codex_image/webui/frontend/src/history.ts"
        ).read_text(encoding="utf-8")

        self.assertRegex(
            html,
            r'id="historyTaskList"[^>]*role="list"',
        )
        self.assertNotIn(
            'id="historyTaskList" class="history-task-list history-view-grid" role="listbox"',
            html,
        )
        card_start = source.index('<article')
        card_end = source.index("</article>", card_start)
        card_markup = source[card_start:card_end]
        self.assertIn('role="listitem"', card_markup)
        self.assertIn('aria-current="${active ? "true" : "false"}"', card_markup)
        self.assertNotIn('role="option"', card_markup)
        self.assertNotIn("aria-selected", card_markup)
        self.assertIn('aria-label="${escapeHtml(accessibleLabel)}"', card_markup)
        self.assertIn(
            "const accessibleLabel = historyTaskAccessibleLabel(task);",
            source,
        )

    def test_focus_and_history_stack_colors_are_theme_tokens(self) -> None:
        tokens = Path(
            "codex_image/webui/static/styles/00-tokens.css"
        ).read_text(encoding="utf-8")
        history = Path(
            "codex_image/webui/static/styles/90-history.css"
        ).read_text(encoding="utf-8")
        light, dark = tokens.split(':root[data-theme="dark"]', 1)

        for token in (
            "--focus-ring:",
            "--history-stack-layer-1:",
            "--history-stack-layer-2:",
            "--history-stack-layer-3:",
        ):
            self.assertIn(token, light)
            self.assertIn(token, dark)
        for color in (
            "#e3e8e5",
            "#cbd3cf",
            "#b2bdb7",
            "#4a5550",
            "#3a4641",
            "#2d3833",
        ):
            self.assertNotIn(color, history.lower())

    def test_mobile_navigation_exposes_overflow_and_history_uses_filter_drawer(
        self,
    ) -> None:
        responsive = Path(
            "codex_image/webui/static/styles/80-utilities-responsive.css"
        ).read_text(encoding="utf-8")
        history_styles = Path(
            "codex_image/webui/static/styles/90-history.css"
        ).read_text(encoding="utf-8")
        history_html = Path(
            "codex_image/webui/static/history.html"
        ).read_text(encoding="utf-8")
        history_source = Path(
            "codex_image/webui/frontend/src/history.ts"
        ).read_text(encoding="utf-8")
        mobile_filters_source = Path(
            "codex_image/webui/frontend/src/history-mobile-filters.ts"
        ).read_text(encoding="utf-8")

        shell = responsive[responsive.index("@media (max-width: 1180px)"):]
        nav_scrollbar = re.search(
            r"\.nav-actions::?-webkit-scrollbar\s*\{(?P<body>[^}]*)\}",
            shell,
        )
        self.assertIsNotNone(nav_scrollbar)
        self.assertNotIn("display: none", nav_scrollbar.group("body"))
        self.assertRegex(shell, r"\.nav-actions\s*\{[^}]*scrollbar-width:\s*thin")

        mobile = history_styles[
            history_styles.index("@media (max-width: 760px)"):]
        self.assertNotIn("42dvh", mobile)
        self.assertIn(".history-mobile-filter-button", mobile)
        self.assertIn(".history-filters-backdrop", mobile)
        self.assertIn('id="historyMobileFiltersButton"', history_html)
        self.assertIn('id="historyFiltersBackdrop"', history_html)
        self.assertIn(
            "initializeHistoryMobileFilters",
            history_source,
        )
        self.assertIn(
            'classList.toggle("history-filters-open"',
            mobile_filters_source,
        )


if __name__ == "__main__":
    unittest.main()

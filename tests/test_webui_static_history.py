from __future__ import annotations

import unittest
from pathlib import Path
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
        self.assertEqual(len(dictionary_paths), 13)
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
        self.assertIn('id="historyDetailClose"', html)
        self.assertIn('data-history-resizer="left"', html)
        self.assertIn('data-history-resizer="right"', html)
        self.assertIn('role="separator"', html)
        self.assertIn('class="history-filter-heading history-filter-heading-orientation"', html)
        self.assertIn('class="history-filter-heading-icon"', html)
        self.assertIn('data-i18n-attr="aria-label:history.resizeFilters"', html)
        self.assertIn('data-i18n-attr="aria-label:history.resizeDetail"', html)
        self.assertIn('/static/styles.css?v=runtime-640', html)
        self.assertRegex(styles, r"\.history-page\s*\{[^}]*height:\s*100dvh")
        self.assertRegex(styles, r"\.history-page\s*\{[^}]*overflow:\s*hidden")
        self.assertRegex(styles, r"\.history-page\s*\{[^}]*--history-sidebar-width:\s*280px")
        self.assertRegex(styles, r"\.history-page\s*\{[^}]*--history-detail-width:\s*380px")
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
        self.assertRegex(styles, r"\.history-results\s*\{[^}]*grid-template-rows:\s*auto\s+minmax\(0,\s*1fr\)")
        self.assertRegex(styles, r"\.history-results\s*\{[^}]*padding:\s*18px\s+12px\s+0")
        self.assertNotRegex(styles, r"\.history-results\s*\{[^}]*grid-template-rows:\s*auto\s+minmax\(0,\s*1fr\)\s+auto")
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
        self.assertRegex(styles, r"\.history-task-list\.history-view-list \.history-task-card\s*\{[^}]*grid-template-columns:\s*40px\s+minmax\(0,\s*1fr\)")
        self.assertRegex(styles, r"\.history-task-list\.history-view-grid \.history-task-select\s*\{[^}]*width:\s*32px")
        self.assertRegex(styles, r"\.history-task-list\.history-view-grid \.history-task-select\s*\{[^}]*top:\s*0")
        self.assertRegex(styles, r"\.history-task-list\.history-view-grid \.history-task-select\s*\{[^}]*left:\s*0")
        self.assertRegex(styles, r"\.history-task-list\.history-view-grid \.history-task-select\s*\{[^}]*border:\s*0")
        self.assertRegex(styles, r"\.history-task-list\.history-view-grid \.history-task-select\s*\{[^}]*background:\s*transparent")
        self.assertRegex(styles, r"\.history-task-list\.history-view-grid \.history-task-select\s*\{[^}]*box-shadow:\s*none")
        self.assertRegex(styles, r":root\[data-theme=\"dark\"\] \.history-task-list\.history-view-list \.history-task-select\s*\{[^}]*opacity:\s*0\.72")
        self.assertRegex(styles, r":root\[data-theme=\"dark\"\] \.history-task-list\.history-view-grid \.history-task-select\s*\{[^}]*background:\s*transparent")
        self.assertRegex(styles, r":root\[data-theme=\"dark\"\] \.history-task-list\.history-view-grid \.history-task-select\s*\{[^}]*box-shadow:\s*none")
        self.assertRegex(styles, r":root\[data-theme=\"dark\"\] \.history-task-select input\s*\{[^}]*opacity:\s*1")
        self.assertRegex(styles, r"\.history-task-list\.history-view-grid \.history-task-card\s*\{[^}]*flex-basis:\s*var\(--history-task-card-width")
        self.assertRegex(styles, r"\.history-task-list\.history-view-grid \.history-task-card\s*\{[^}]*width:\s*var\(--history-task-card-width")
        self.assertNotRegex(styles, r"\.history-task-list\.history-view-grid\s*\{[^}]*justify-content:\s*space-between")
        self.assertRegex(styles, r"\.history-sidebar,\s*\.history-task-list,\s*\.history-detail,\s*\.history-detail-prompt\s*\{[^}]*scrollbar-color:\s*var\(--scrollbar-thumb\)\s+transparent")
        self.assertRegex(styles, r"\.history-sidebar::-webkit-scrollbar-track,[\s\S]*\.history-detail-prompt::-webkit-scrollbar-track\s*\{[^}]*background:\s*transparent")
        self.assertIn(".history-task-list::-webkit-scrollbar-thumb:hover", styles)
        self.assertRegex(styles, r"\.history-task-list\.history-view-grid \.history-task-thumb\s*\{[^}]*aspect-ratio:\s*var\(--history-task-thumb-ratio,\s*1\s*/\s*1\)")
        self.assertRegex(styles, r"\.history-task-list\.history-view-grid \.history-task-thumb\s*\{[^}]*height:\s*var\(--history-task-row-height,\s*var\(--history-task-thumb-row-height\)\)")
        self.assertRegex(styles, r"\.history-task-thumb img\s*\{[^}]*object-fit:\s*cover")
        self.assertRegex(styles, r"\.history-task-thumb img\s*\{[^}]*border-radius:\s*inherit")
        self.assertRegex(
            styles,
            r"\.history-task-list\.history-view-grid \.history-task-card\.active \.history-task-thumb,\s*"
            r"\.history-task-list\.history-view-grid \.history-task-card\.selected \.history-task-thumb\s*\{[^}]*"
            r"border-radius:\s*var\(--radius\)[^}]*background:\s*var\(--primary\)",
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
        self.assertRegex(styles, r"\.history-filter-button\s*\{[^}]*min-height:\s*40px")
        self.assertRegex(styles, r"\.history-filter-button \.history-filter-count\s*\{[^}]*font-size:\s*10px")
        self.assertRegex(styles, r"\.history-filter-button \.history-filter-count\s*\{[^}]*background:\s*color-mix")
        self.assertRegex(styles, r"\.history-filter-heading-icon,\s*\.history-filter-icon\s*\{[^}]*stroke:\s*currentColor")
        self.assertRegex(styles, r"\.history-filter-button\[data-history-filter-key=\"orientation\"\]\s*\{[^}]*padding-left:\s*10px")
        self.assertRegex(
            styles,
            r"\.history-task-list\.history-view-grid \.history-task-card\.active \.history-task-thumb,\s*"
            r"\.history-task-list\.history-view-grid \.history-task-card\.selected \.history-task-thumb\s*\{[^}]*"
            r"border-radius:\s*var\(--radius\)[^}]*background:\s*var\(--primary\)",
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
        self.assertIn("--history-task-stack-layer-surface: #e3e8e5", styles)
        self.assertIn("--history-task-stack-layer-surface: #cbd3cf", styles)
        self.assertIn("--history-task-stack-layer-surface: #b2bdb7", styles)
        self.assertIn("--history-task-stack-layer-surface: #4a5550", styles)
        self.assertIn("--history-task-stack-layer-surface: #3a4641", styles)
        self.assertIn("--history-task-stack-layer-surface: #2d3833", styles)
        self.assertRegex(styles, r"\.history-task-list\.history-view-grid \.history-task-card\[data-history-stack-depth=\"1\"\] \.history-task-stack-layer\[data-history-stack-layer=\"1\"\],[^}]*border:\s*1px solid color-mix")
        self.assertRegex(styles, r"transform:\s*translate\(var\(--history-task-stack-layer-offset\),\s*var\(--history-task-stack-layer-offset\)\)")
        self.assertRegex(styles, r"\.history-task-list\.history-view-list \.history-task-stack-layer\s*\{[^}]*display:\s*none")
        self.assertNotIn(".history-task-image-count", styles)
        self.assertNotIn(".history-task-active-badge", styles)
        self.assertRegex(styles, r":root\[data-theme=\"dark\"\] \.history-task-list\.history-view-grid \.history-task-card\.active \.history-task-thumb,\s*:root\[data-theme=\"dark\"\] \.history-task-list\.history-view-grid \.history-task-card\.selected \.history-task-thumb\s*\{[^}]*background:\s*var\(--primary-strong\)")

    def test_history_page_feature_contracts_are_complete(self) -> None:
        html = Path("codex_image/webui/static/history.html").read_text(encoding="utf-8")
        source = Path("codex_image/webui/frontend/src/history.ts").read_text(encoding="utf-8")
        detail_media_source = Path("codex_image/webui/frontend/src/history-detail-media.ts").read_text(encoding="utf-8")
        window_source = Path("codex_image/webui/frontend/src/history-window.ts").read_text(encoding="utf-8")
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
            'id="historyBulkToolbar"',
            'id="historyBulkArchiveButton"',
            'id="historyBulkRestoreButton"',
            'id="historyBulkDeleteButton"',
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
            '"mode", "month", "prompt_mode"',
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
            "clearHistoryDeleteConfirmation",
            "renderSelectionDetail",
            "syncHistorySelectionDetail",
            'dataset.historyDetailMode = "selection"',
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
            "shouldDeleteCurrentHistorySelection",
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
            "history-detail-actions-primary",
            "history-detail-actions-output",
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
        update_resize_body = _typescript_function_body(source, "updateHistoryResize")
        apply_pending_resize_body = _typescript_function_body(source, "applyPendingHistoryResize")
        start_resize_body = _typescript_function_body(source, "startHistoryResize")
        end_resize_body = _typescript_function_body(source, "endHistoryResize")
        self.assertIn("if (historyGridLayoutFrame) return;", source)
        self.assertNotIn("window.cancelAnimationFrame(historyGridLayoutFrame)", source)
        self.assertIn("scheduleHistoryGridLayout({ keepTaskId });", source)
        self.assertIn("activeHistoryResizer.latestX = event.clientX;", update_resize_body)
        self.assertIn("if (historyResizeFrame) return;", update_resize_body)
        self.assertIn("window.requestAnimationFrame(applyPendingHistoryResize)", update_resize_body)
        self.assertNotIn("getBoundingClientRect", update_resize_body)
        self.assertNotIn("applyHistoryLayoutWidths", update_resize_body)
        self.assertIn("maxCombinedWidth: historyLayoutMaxCombinedWidth()", start_resize_body)
        self.assertIn("resize.maxCombinedWidth", apply_pending_resize_body)
        self.assertIn("layoutJustifiedHistoryGrid();", apply_pending_resize_body)
        self.assertNotIn("persist: true", update_resize_body)
        self.assertIn("localStorage.setItem(HISTORY_LAYOUT_STORAGE_KEY", end_resize_body)
        self.assertIn("applyPendingHistoryResize();", end_resize_body)

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
        self.assertIn("function handleHistoryTaskArrowNavigation", source)
        self.assertIn("isHistoryTaskArrowKey(event.key)", source)
        self.assertIn("historyTaskArrowTargetCard(els.taskList, taskId, event.key, historyState.view)", source)
        self.assertIn('historyState.view === "list" && (event.key === "ArrowLeft" || event.key === "ArrowRight")', source)
        self.assertIn('event.preventDefault();\n  event.stopPropagation();', source)
        self.assertIn('focusHistoryTaskButton(nextTaskId);', source)
        self.assertIn('void loadTaskDetail(nextTaskId);', source)
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
        self.assertRegex(
            lightbox_source,
            r'if \(event\.key === "ArrowLeft"\) \{[\s\S]*event\.preventDefault\(\);\s*event\.stopPropagation\(\);[\s\S]*showPreviousHistoryLightboxImage\(\);',
        )
        self.assertRegex(
            lightbox_source,
            r'if \(event\.key === "ArrowUp"\) \{[\s\S]*event\.preventDefault\(\);\s*event\.stopPropagation\(\);[\s\S]*showPreviousHistoryTask\(\);',
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
        self.assertIn("const batchSelecting = historyState.selectedTaskIds.size > 0", selection_visuals_body)
        self.assertIn("!batchSelecting && taskId && cardTaskId === taskId", selection_visuals_body)

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

        self.assertRegex(styles, r"\.history-task-card\.active\s*\{[^}]*box-shadow:")
        self.assertRegex(styles, r"\.history-task-card\.active\s*\{[^}]*inset 0 0 0 2px")
        self.assertIn(".history-task-list.history-view-grid .history-task-card.active::before", styles)
        self.assertRegex(styles, r"\.history-task-list\.history-view-grid \.history-task-card\.active::before\s*\{[^}]*content:\s*none")
        self.assertRegex(styles, r"\.history-task-list\.history-view-grid \.history-task-card\.active,\s*\.history-task-list\.history-view-grid \.history-task-card\.selected\s*\{[^}]*background:\s*var\(--primary\)")
        self.assertRegex(styles, r"\.history-task-list\.history-view-grid \.history-task-card\.active,\s*\.history-task-list\.history-view-grid \.history-task-card\.selected\s*\{[^}]*box-shadow:\s*[\s\S]*0 0 0 2px var\(--primary\)")
        self.assertRegex(styles, r"\.history-task-list\.history-view-grid \.history-task-card\.active \.history-task-thumb,\s*\.history-task-list\.history-view-grid \.history-task-card\.selected \.history-task-thumb\s*\{[^}]*border-radius:\s*var\(--radius\)")
        self.assertRegex(styles, r"\.history-task-list\.history-view-grid \.history-task-card\.active \.history-task-thumb,\s*\.history-task-list\.history-view-grid \.history-task-card\.selected \.history-task-thumb\s*\{[^}]*background:\s*var\(--primary\)")
        self.assertRegex(styles, r"\.history-task-list\.history-view-grid \.history-task-card\.active \.history-task-copy,\s*\.history-task-list\.history-view-grid \.history-task-card\.selected \.history-task-copy\s*\{[^}]*background:\s*var\(--primary\)")
        self.assertRegex(styles, r"\.history-task-list\.history-view-grid \.history-task-card\.active \.history-task-title,\s*\.history-task-list\.history-view-grid \.history-task-card\.selected \.history-task-title")
        self.assertNotIn(".history-task-active-badge", styles)
        self.assertNotIn(".history-task-image-count", styles)
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
        self.assertRegex(styles, r"\.history-task-list\.history-view-grid \.history-task-select\s*\{[^}]*opacity:\s*0")
        self.assertRegex(styles, r"\.history-task-list\.history-view-grid \.history-task-select\s*\{[^}]*pointer-events:\s*none")
        self.assertRegex(styles, r"\.history-task-select input\s*\{[^}]*appearance:\s*none")
        self.assertRegex(styles, r"\.history-task-select input:checked\s*\{[^}]*background:\s*var\(--primary\)")
        self.assertRegex(styles, r"\.history-task-select input:checked::before\s*\{[^}]*transform:\s*scale\(1\)")
        self.assertRegex(styles, r"\.history-task-list\.history-view-grid \.history-task-card:has\(\.history-task-thumb:hover\) \.history-task-select")
        self.assertRegex(styles, r"\.history-task-list\.history-view-grid \.history-task-card\.selected \.history-task-select\s*\{[^}]*opacity:\s*1")
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
        self.assertRegex(styles, r"\.history-detail-actions-primary\s*>\s*\*,\s*\.history-detail-actions-output\s*>\s*\*\s*\{[^}]*white-space:\s*nowrap")
        self.assertRegex(styles, r"\.history-detail-actions-output\s*\{[^}]*margin-left:\s*auto")
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
        self.assertRegex(styles, r"\.history-toolbar-actions\s*\{[^}]*--history-toolbar-control-height:\s*44px")
        self.assertRegex(styles, r"\.history-view-toggle,\s*\.history-sort-toggle\s*\{[^}]*box-sizing:\s*border-box")
        self.assertRegex(styles, r"\.history-view-toggle,\s*\.history-sort-toggle\s*\{[^}]*height:\s*var\(--history-toolbar-control-height\)")
        self.assertRegex(styles, r"\.history-view-toggle,\s*\.history-sort-toggle\s*\{[^}]*--segmented-indicator-radius:\s*999px")
        self.assertRegex(styles, r"\.history-view-toggle,\s*\.history-sort-toggle\s*\{[^}]*border-radius:\s*999px")
        self.assertRegex(styles, r"\.history-view-button,\s*\.history-sort-button\s*\{[^}]*font-size:\s*14px")
        self.assertRegex(styles, r"\.history-view-button,\s*\.history-sort-button\s*\{[^}]*border-radius:\s*999px")
        self.assertRegex(styles, r"\.history-view-toggle \.segmented-indicator,\s*\.history-sort-toggle \.segmented-indicator\s*\{[^}]*border-radius:\s*999px")
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
        self.assertNotIn(".history-lightbox-nav", styles)
        self.assertRegex(styles, r"\.history-lightbox-counter\s*\{[^}]*position:\s*absolute")
        self.assertIn(':root[data-theme="dark"] .history-task-card.selected', styles)

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
        self.assertIn('restoreHistoryTaskReuseHandoff,', selection_source)
        self.assertIn('call(methods, "restoreHistoryTaskReuseHandoff")', boot_source)

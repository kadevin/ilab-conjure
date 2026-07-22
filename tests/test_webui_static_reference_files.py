from __future__ import annotations

import json
import re
import unittest
from pathlib import Path
import shutil
import subprocess
import textwrap


ROOT = Path(__file__).resolve().parents[1]


class ReferenceFileFrontendContractTests(unittest.TestCase):
    def test_selected_reference_files_share_the_image_thumbnail_rail(self) -> None:
        html = (ROOT / "codex_image/webui/static/index.html").read_text(encoding="utf-8")
        image_thumb_list = html[
            html.index('<div id="imageThumbList"') : html.index('<div id="imageUploadSource"')
        ]
        styles = (ROOT / "codex_image/webui/static/styles/50-image-input-gallery.css").read_text(encoding="utf-8")

        self.assertIn('id="imageThumbItems"', image_thumb_list)
        self.assertIn('id="referenceFileSelection"', image_thumb_list)
        self.assertLess(image_thumb_list.index('id="imageThumbItems"'), image_thumb_list.index('id="referenceFileSelection"'))
        self.assertNotRegex(styles, r"\.reference-file-selection\s*\{[^}]*position:\s*absolute")
        self.assertRegex(styles, r"\.image-thumb-items\s*,\s*\.reference-file-selection\s*\{[^}]*display:\s*contents")

    def test_generation_file_renderers_reuse_shared_svg_icons(self) -> None:
        module = (ROOT / "codex_image/webui/frontend/src/reference-file-inputs.ts").read_text(encoding="utf-8")
        self.assertIn('import { referenceFileIconSvgMarkup } from "./reference-file-icons";', module)
        self.assertIn("function renderFormatIcon", module)
        self.assertEqual(module.count("renderFormatIcon(icon, source.filename)"), 1)
        self.assertNotIn('icon.textContent = source.family === "pdf"', module)

    def test_selected_file_tiles_reuse_image_thumb_geometry_and_controls(self) -> None:
        module = (ROOT / "codex_image/webui/frontend/src/reference-file-inputs.ts").read_text(encoding="utf-8")
        styles = (ROOT / "codex_image/webui/static/styles/50-image-input-gallery.css").read_text(encoding="utf-8")
        render_block = module[
            module.index("export function renderReferenceFiles") : module.index("export function syncReferenceFileAvailability")
        ]

        self.assertIn("className = `reference-file-thumb thumb", module)
        self.assertIn('className = "reference-file-name"', render_block)
        self.assertIn("name.textContent = source.filename", render_block)
        self.assertNotIn('className = "reference-file-meta"', render_block)
        self.assertIn("tile.title = source.filename", render_block)
        self.assertIn('className = "thumb-remove reference-file-remove"', render_block)
        self.assertRegex(
            styles,
            r"\.reference-file-thumb \.reference-file-format-icon\s*\{[^}]*width:\s*44px[^}]*height:\s*50px",
        )
        self.assertRegex(
            styles,
            r"\.reference-file-name\s*\{[^}]*display:\s*-webkit-box[\s\S]*?"
            r"word-break:\s*break-all[\s\S]*?-webkit-line-clamp:\s*2",
        )
        self.assertRegex(
            styles,
            r"\.image-uploader-grid\.compact-grid\s+\.reference-file-name\s*\{[^}]*display:\s*none",
        )
        self.assertRegex(styles, r"\.reference-file-thumb \.reference-file-remove\s*\{[^}]*opacity:\s*0[^}]*pointer-events:\s*none")
        self.assertRegex(
            styles,
            r"@media\s*\(hover:\s*none\),\s*\(pointer:\s*coarse\)\s*\{[\s\S]*?"
            r"\.reference-file-thumb \.reference-file-remove\s*\{[^}]*opacity:\s*1[^}]*pointer-events:\s*auto",
        )
        self.assertRegex(styles, r"\.reference-file-requirement\s*\{[^}]*position:\s*absolute")
        self.assertNotIn(".reference-file-row", styles)

    def test_selected_docx_renders_icon_filename_summary_and_accessible_tile(self) -> None:
        node = shutil.which("node")
        if node is None:
            self.skipTest("node is required for frontend behavior checks")
        module_path = ROOT / "codex_image/webui/frontend/src/reference-file-inputs.ts"
        filename = "quarterly-planning-notes-with-a-very-long-accessible-filename.docx"
        harness = textwrap.dedent(
            f"""
            const fs = require("fs");
            const ts = require("typescript");
            const vm = require("vm");
            const code = ts.transpileModule(fs.readFileSync({str(module_path)!r}, "utf8"), {{
              compilerOptions: {{ module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 }},
            }}).outputText;
            class ClassList {{
              constructor() {{ this.values = new Set(); }}
              add(...values) {{ values.forEach((value) => this.values.add(value)); }}
              remove(...values) {{ values.forEach((value) => this.values.delete(value)); }}
              toggle(value, force) {{ force ? this.add(value) : this.remove(value); }}
            }}
            class Element {{
              constructor(tag) {{
                this.tagName = tag.toUpperCase(); this.children = []; this.attributes = {{}};
                this.classList = new ClassList(); this.className = ""; this.title = ""; this.tabIndex = -1;
                this.innerHTML = ""; this.workspace = null;
              }}
              append(...children) {{ this.children.push(...children); }}
              replaceChildren(...children) {{ this.children = [...children]; }}
              setAttribute(name, value) {{ this.attributes[name] = String(value); }}
              addEventListener() {{}}
              closest(selector) {{ return selector === ".image-input-workspace" ? this.workspace : null; }}
            }}
            const workspace = new Element("div");
            const container = new Element("div"); container.workspace = workspace;
            const state = {{
              referenceFiles: [{{ kind: "upload", filename: {filename!r}, mime_type: "application/vnd.openxmlformats-officedocument.wordprocessingml.document", size_bytes: 1234, family: "document" }}],
              recentReferenceFiles: [],
            }};
            const bridge = {{ state, els: {{ referenceFileSelection: container }}, methods: {{}} }};
            const module = {{ exports: {{}} }};
            vm.runInNewContext(code, {{
              module, exports: module.exports, console, Set, Map, Array,
              document: {{ createElement: (tag) => new Element(tag) }},
              require(name) {{
                if (name === "./dom") return {{ getEls: () => bridge.els }};
                if (name === "./state") return {{ getLegacyBridge: () => bridge, getState: () => state }};
                if (name === "./i18n") return {{
                  LOCALE_CHANGE_EVENT: "locale-change", translate: (key) => key,
                  formatTranslation: (_key, values) => `Remove ${{values.filename}}`,
                }};
                if (name === "./reference-file-icons") return {{
                  referenceFileIconSvgMarkup: (name) => `<svg data-filename="${{name}}"></svg>`,
                }};
                throw new Error(`unexpected require: ${{name}}`);
              }},
            }});
            module.exports.renderReferenceFiles();
            if (container.children.length !== 1) throw new Error(`expected one tile, got ${{container.children.length}}`);
            const tile = container.children[0];
            if (!tile.className.includes("reference-file-thumb thumb")) throw new Error(`wrong tile class: ${{tile.className}}`);
            if (tile.title !== {filename!r} || tile.attributes["aria-label"] !== {filename!r} || tile.tabIndex !== 0) {{
              throw new Error("full filename is not keyboard/title accessible");
            }}
            const classes = tile.children.map((child) => child.className);
            if (classes.includes("reference-file-meta")) throw new Error("visible metadata leaked into tile");
            const icons = tile.children.filter((child) => child.className === "reference-file-icon" && child.innerHTML.includes("<svg"));
            if (icons.length !== 1) throw new Error(`expected one SVG icon, got ${{icons.length}}`);
            const names = tile.children.filter((child) => child.className === "reference-file-name" && child.textContent === {filename!r});
            if (names.length !== 1) throw new Error(`expected one filename summary, got ${{names.length}}`);
            const remove = tile.children.find((child) => child.className === "thumb-remove reference-file-remove");
            if (!remove || !remove.attributes["aria-label"].includes({filename!r})) throw new Error("accessible remove label missing filename");
            """
        )
        result = subprocess.run([node, "-e", harness], cwd=ROOT, check=False, text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_recent_file_product_surface_and_help_are_removed(self) -> None:
        html = (ROOT / "codex_image/webui/static/index.html").read_text(encoding="utf-8")
        module = (ROOT / "codex_image/webui/frontend/src/reference-file-inputs.ts").read_text(encoding="utf-8")
        elements = (ROOT / "codex_image/webui/frontend/src/elements.ts").read_text(encoding="utf-8")
        defaults = (ROOT / "codex_image/webui/frontend/src/state-defaults.ts").read_text(encoding="utf-8")
        state = (ROOT / "codex_image/webui/frontend/src/state.ts").read_text(encoding="utf-8")
        boot = (ROOT / "codex_image/webui/frontend/src/boot.ts").read_text(encoding="utf-8")
        submit = (ROOT / "codex_image/webui/frontend/src/task-submit.ts").read_text(encoding="utf-8")
        styles = (ROOT / "codex_image/webui/static/styles/50-image-input-gallery.css").read_text(encoding="utf-8")
        responsive_styles = (ROOT / "codex_image/webui/static/styles/80-utilities-responsive.css").read_text(encoding="utf-8")
        generated_styles = (ROOT / "codex_image/webui/static/styles.css").read_text(encoding="utf-8")

        for obsolete_id in (
            "referenceFileInfo",
            "referenceFileVisualLimitTooltip",
            "recentReferenceFileDock",
            "recentReferenceFileList",
        ):
            self.assertNotIn(obsolete_id, html)
            self.assertNotIn(obsolete_id, elements)
        for source in (module, defaults, state, boot, submit):
            self.assertNotIn("recentReferenceFiles", source)
            self.assertNotIn("refreshRecentReferenceFiles", source)
        self.assertNotIn("/api/reference-files/recent", module)
        self.assertNotIn("visualLimitTooltipPinned", module)
        self.assertNotIn("renderRecentReferenceFiles", module)
        self.assertNotIn("bindVisualLimitTooltip", module)
        self.assertNotIn("syncReferenceFileWorkspaceClass", module)
        self.assertNotIn("recent-reference-file", styles)
        self.assertNotIn("recent-reference-file", responsive_styles)
        self.assertNotIn("recent-reference-file", generated_styles)
        self.assertNotIn("reference-file-visual-limit-tooltip", styles)
        self.assertNotIn("#referenceFileInfo", styles)

    def test_every_supported_extension_has_a_unique_svg_icon_spec(self) -> None:
        from codex_image.webui.reference_file_policy import REFERENCE_FILE_TYPES

        family_extensions = {
            "pdf": ["pdf"],
            "spreadsheet": ["xla", "xlb", "xlc", "xlm", "xls", "xlt", "xlw", "xlsx", "csv", "tsv", "iif"],
            "document": ["doc", "docx", "dot", "odt", "rtf", "wiz"],
            "presentation": ["pot", "ppa", "pps", "ppt", "pwz", "pptx"],
            "code": ["asm", "bat", "c", "cc", "conf", "cpp", "css", "cxx", "def", "h", "hh", "in", "js", "mjs", "pl", "py", "s", "sql"],
            "data": ["dic", "htm", "html", "json", "ksh", "list", "log", "markdown", "md", "mht", "mhtml", "mime", "nws", "rst", "srt", "text", "txt", "vtt", "xml"],
            "mail": ["eml", "ics", "ifb", "vcf"],
        }
        family_colors = {
            "pdf": "#d37a70", "spreadsheet": "#64a982", "document": "#6e9cc7",
            "presentation": "#c79862", "code": "#9385c9", "data": "#6fa4a2", "mail": "#879993",
        }
        label_overrides = {"markdown": "MKDN", "mhtml": "MHTL"}
        expected_specs = {}
        for family, extensions in family_extensions.items():
            for extension in extensions:
                label = label_overrides.get(extension, extension.upper())
                color = family_colors[family]
                font_size = 4.5 if len(label) > 3 else 5.3
                expected_specs[extension] = {
                    "extension": extension,
                    "label": label,
                    "family": family,
                    "color": color,
                    "svg": (
                        '<svg class="reference-file-format-icon" viewBox="0 0 24 28" aria-hidden="true" '
                        f'focusable="false" style="color:{color}">\n'
                        '    <rect x="3" y="2" width="18" height="24" rx="4" fill="currentColor" '
                        'fill-opacity=".14" stroke="currentColor" stroke-opacity=".62"></rect>\n'
                        '    <path d="M3 6a4 4 0 0 1 4-4h10a4 4 0 0 1 4 4" fill="currentColor"></path>\n'
                        f'    <text x="12" y="17" text-anchor="middle" fill="currentColor" font-size="{font_size}" '
                        f'font-weight="800" font-family="Arial, sans-serif">{label}</text>\n'
                        "  </svg>"
                    ),
                }

        icon_module = (ROOT / "codex_image/webui/frontend/src/reference-file-icons.ts").read_text(encoding="utf-8")
        self.assertNotIn("<circle", icon_module)
        self.assertNotIn("markerX", icon_module)

        node = shutil.which("node")
        if node is None:
            self.skipTest("node is required for frontend behavior checks")
        module_path = ROOT / "codex_image/webui/frontend/src/reference-file-icons.ts"
        harness = textwrap.dedent(
            f"""
            const fs = require("fs");
            const ts = require("typescript");
            const vm = require("vm");
            const code = ts.transpileModule(fs.readFileSync({str(module_path)!r}, "utf8"), {{
              compilerOptions: {{ module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 }},
            }}).outputText;
            const module = {{ exports: {{}} }};
            vm.runInNewContext(code, {{ module, exports: module.exports }});
            const api = module.exports;
            const extensions = [...api.REFERENCE_FILE_ICON_EXTENSIONS].sort();
            const signatures = extensions.map((ext) => api.referenceFileIconSpec(`file.${{ext}}`).label);
            if (new Set(signatures).size !== signatures.length) throw new Error("format signatures are not unique");
            const specs = Object.fromEntries(extensions.map((ext) => {{
              const spec = api.referenceFileIconSpec(`file.${{ext}}`);
              return [ext, {{ ...spec, svg: api.referenceFileIconSvgMarkup(`file.${{ext}}`) }}];
            }}));
            for (const special of ['__proto__', 'constructor', 'toString']) {{
              const spec = api.referenceFileIconSpec(`file.${{special}}`);
              const svg = api.referenceFileIconSvgMarkup(`file.${{special}}`);
              if (spec.extension !== '' || spec.label !== 'FILE' || spec.family !== 'mail'
                  || spec.color !== '#879993' || !svg.includes('>FILE<')) {{
                throw new Error(`prototype key did not use fallback: ${{special}}`);
              }}
            }}
            const doc = specs.doc.svg;
            const docx = specs.docx.svg;
            const malicious = api.referenceFileIconSvgMarkup('bad"><img src=x>.unknown');
            if (!doc.includes('>DOC<') || !docx.includes('>DOCX<')) throw new Error('dedicated labels missing');
            if (doc === docx) throw new Error('doc and docx icons are not dedicated');
            if (!malicious.includes('>FILE<') || malicious.includes('<img')) throw new Error('fallback is unsafe');
            const mutable = api.referenceFileIconSpec('proposal.doc');
            const originalDoc = api.referenceFileIconSvgMarkup('proposal.doc');
            try {{ mutable.label = '<script>'; mutable.color = '<img src=x>'; }} catch (error) {{}}
            const afterMutation = api.referenceFileIconSvgMarkup('proposal.doc');
            if (!Object.isFrozen(mutable) || afterMutation !== originalDoc
                || afterMutation.includes('<script>') || afterMutation.includes('<img')) {{
              throw new Error('exported spec mutation changed constant SVG markup');
            }}
            process.stdout.write(JSON.stringify({{ extensions, signatures, specs }}));
            """
        )
        result = subprocess.run([node, "-e", harness], cwd=ROOT, check=False, text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["extensions"], sorted(suffix.removeprefix(".") for suffix in REFERENCE_FILE_TYPES))
        self.assertEqual(payload["specs"], expected_specs)

    def test_history_renders_files_outside_image_lightbox(self) -> None:
        media = (ROOT / "codex_image/webui/frontend/src/history-detail-media.ts").read_text(encoding="utf-8")
        history = (ROOT / "codex_image/webui/frontend/src/history.ts").read_text(encoding="utf-8")
        self.assertIn("historyReferenceFilesHtml", media)
        self.assertIn("task.reference_files", media)
        self.assertIn("data-history-reference-file-id", media)
        self.assertIn('if (!files.length) return ""', media)
        self.assertNotIn("data-history-reference-file-lightbox", media)
        self.assertIn("historyReferenceFilesHtml(task)", history)

    def test_history_reference_file_renderer_escapes_copy_and_derives_safe_downloads(self) -> None:
        node = shutil.which("node")
        if node is None:
            self.skipTest("node is required for frontend behavior checks")
        module_path = ROOT / "codex_image/webui/frontend/src/history-detail-media.ts"
        utils_path = ROOT / "codex_image/webui/frontend/src/webui-utils.ts"
        harness = textwrap.dedent(
            f"""
            const fs = require("fs");
            const ts = require("typescript");
            const vm = require("vm");
            const transpile = (path) => ts.transpileModule(fs.readFileSync(path, "utf8"), {{
              compilerOptions: {{ module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 }},
            }}).outputText;
            const evaluate = (code, requireFn, globals = {{}}) => {{
              const module = {{ exports: {{}} }};
              vm.runInNewContext(code, {{ module, exports: module.exports, require: requireFn, console, ...globals }});
              return module.exports;
            }};
            const utils = evaluate(transpile({str(utils_path)!r}), () => {{}}, {{ window: {{}} }});
            const icons = evaluate(
              transpile({str(ROOT / "codex_image/webui/frontend/src/reference-file-icons.ts")!r}),
              () => {{}},
            );
            const media = evaluate(transpile({str(module_path)!r}), (name) => {{
              if (name === "./i18n") return {{ translate: (key) => key, formatTranslation: (key) => key }};
              if (name === "./reference-file-icons") return icons;
              if (name === "./webui-utils") return utils;
              throw new Error(`unexpected require: ${{name}}`);
            }});
            const validId = "a".repeat(64);
            const malicious = `brief\"><img src=x onerror=alert(1)>.pdf`;
            const html = media.historyReferenceFilesHtml({{
              task_id: "task/one",
              reference_files: [
                {{
                  id: validId, filename: malicious, mime_type: "application/pdf",
                  family: "pdf", size_bytes: 2048,
                  download_url: "https://evil.example/steal",
                }},
                {{ id: "c".repeat(64), filename: "proposal.doc", family: "document", size_bytes: 8 }},
                {{ id: "d".repeat(64), filename: "budget.xlsx", family: "spreadsheet", size_bytes: 16 }},
                {{ id: "b".repeat(64), filename: "missing.md", family: "text", size_bytes: 1, missing: true }},
                {{ id: "not-a-sha", filename: "invalid.md", family: "text", size_bytes: 1 }},
              ],
            }});
            if (html.includes(malicious) || html.includes("<img src=x")) throw new Error("filename was not escaped");
            if (!html.includes("brief&quot;&gt;&lt;img")) throw new Error("escaped filename missing");
            if (!html.includes('class="reference-file-format-icon"')) throw new Error("history SVG icon missing");
            if (!html.includes(">DOC<")) throw new Error("DOC signature missing");
            if (!html.includes(">XLSX<")) throw new Error("XLSX signature missing");
            if (!html.includes(`data-history-reference-file-id="${{validId}}"`)) throw new Error("valid re-add action missing");
            if (!html.includes('href="/api/tasks/task%2Fone/reference-files/1/download"')) throw new Error("safe task download missing");
            if (html.includes("evil.example")) throw new Error("untrusted download_url reached markup");
            if ((html.match(/data-history-reference-file-id=/g) || []).length !== 3) throw new Error("valid actions or missing suppression changed");
            if ((html.match(/<a /g) || []).length !== 3) throw new Error("valid downloads or missing suppression changed");
            if (html.includes("data-history-reference-file-lightbox") || html.includes("data-history-input-lightbox")) throw new Error("file row entered lightbox semantics");
            """
        )
        result = subprocess.run([node, "-e", harness], cwd=ROOT, check=False, text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_cache_versions_are_bumped_once(self) -> None:
        index = (ROOT / "codex_image/webui/static/index.html").read_text(encoding="utf-8")
        history = (ROOT / "codex_image/webui/static/history.html").read_text(encoding="utf-8")
        worker = (ROOT / "codex_image/webui/static/service-worker.js").read_text(encoding="utf-8")
        self.assertIn("runtime-568", index)
        self.assertIn("runtime-568", history)
        self.assertIn("history-69", history)
        self.assertIn('ilab-gpt-conjure-shell-v52', worker)

    def test_design_system_documents_shared_input_rail_and_filename_summary_tiles(self) -> None:
        design_path = ROOT / "DESIGN.md"
        if not design_path.exists():
            self.skipTest("private design contract is not exported")
        design = design_path.read_text(encoding="utf-8")
        self.assertIn("已选图片与文件共用同一条缩略图轨道", design)
        self.assertIn("生成页不提供最近参考文件列表", design)
        self.assertNotIn("已选文件覆盖在上传区底部", design)
        self.assertIn("紧凑格式图标 + 两行文件名摘要", design)
        self.assertIn("触发 `compact-grid` 缩略模式时隐藏文件名", design)
        self.assertIn("必须同时清空图片和文件", design)
        self.assertIn("不使用无语义的右上角识别点", design)
        self.assertIn("每个受支持扩展名保留唯一签名", design)

    def test_reference_files_have_separate_state_and_submit_fields(self) -> None:
        defaults = (ROOT / "codex_image/webui/frontend/src/state-defaults.ts").read_text(encoding="utf-8")
        module = (ROOT / "codex_image/webui/frontend/src/reference-file-inputs.ts").read_text(encoding="utf-8")
        submit = (ROOT / "codex_image/webui/frontend/src/task-submit.ts").read_text(encoding="utf-8")
        self.assertIn("referenceFiles: []", defaults)
        self.assertNotIn("recentReferenceFiles", defaults)
        self.assertIn("state.referenceFiles", module)
        self.assertNotIn("state.images.push", module)
        self.assertIn("partitionReferenceDropFiles", module)
        self.assertIn(
            "partitionReferenceDropFiles",
            (ROOT / "codex_image/webui/frontend/src/input-sources.ts").read_text(encoding="utf-8"),
        )
        self.assertIn('form.append("reference_files"', submit)
        self.assertIn('form.append("reference_file_ids"', submit)

    def test_one_input_accepts_and_partitions_images_and_reference_files(self) -> None:
        from codex_image.webui.reference_file_policy import REFERENCE_FILE_TYPES

        html = (ROOT / "codex_image/webui/static/index.html").read_text(encoding="utf-8")
        input_tag_match = re.search(r'<input\b[^>]*\bid="imageInput"[^>]*>', html)
        self.assertIsNotNone(input_tag_match)
        input_tag = input_tag_match.group(0)
        accept_match = re.search(r'\baccept="([^"]*)"', input_tag)
        self.assertIsNotNone(accept_match)
        accept_tokens = {token.strip() for token in accept_match.group(1).split(",") if token.strip()}
        self.assertIn("image/*", accept_tokens)
        self.assertEqual(accept_tokens - {"image/*"}, set(REFERENCE_FILE_TYPES))
        self.assertRegex(input_tag, r"\bmultiple\b")
        self.assertNotIn('id="referenceFileInput"', html)
        self.assertNotIn('id="referenceFileButton"', html)
        self.assertIn('id="referenceFileSelection"', html)
        self.assertNotIn('id="recentReferenceFileDock"', html)
        self.assertIn('data-i18n="imageInput.referenceTitle"', html)
        self.assertNotIn(".ods", html)
        self.assertNotIn(".odp", html)

    def test_generated_bundle_routes_picker_and_drop_through_mixed_ingestion(self) -> None:
        script = (ROOT / "codex_image/webui/static/app.js").read_text(encoding="utf-8")
        self.assertIn("function addMixedInputFiles(", script)
        self.assertRegex(script, r'function addImages\(event\)\s*\{\s*legacyMethod\d*\("addMixedInputFiles", event\.target\.files \|\| \[\]\)')
        self.assertRegex(script, r'function handleImageDrop\(event\)[\s\S]*addMixedInputFiles\(files, \{')

    def test_reference_file_module_enforces_separate_file_workflow(self) -> None:
        module = (ROOT / "codex_image/webui/frontend/src/reference-file-inputs.ts").read_text(encoding="utf-8")
        self.assertIn('kind: "upload" | "asset"', module)
        self.assertIn('family: "pdf" | "spreadsheet" | "document" | "text"', module)
        self.assertNotIn('/api/reference-files/recent', module)
        self.assertIn("referenceFiles.requiresResponses", module)
        self.assertIn('legacyMethod("selectCodexMode", "responses")', module)
        self.assertIn('legacyMethod("openApiSettingsModal")', module)
        self.assertNotIn("handlePickerClick", module)
        self.assertNotIn("handlePickerChange", module)
        self.assertIn(".referenceFiles.filter", module)
        self.assertNotIn("URL.createObjectURL", module)
        self.assertNotIn('legacyMethod("setMode"', module)

    def test_submission_keeps_file_metadata_out_of_image_action(self) -> None:
        submit = (ROOT / "codex_image/webui/frontend/src/task-submit.ts").read_text(encoding="utf-8")
        self.assertIn("referenceFileUploads()", submit)
        self.assertIn("storedReferenceFileInputs()", submit)
        self.assertIn("missingReferenceFileInputs()", submit)
        self.assertIn("local_reference_files", submit)
        self.assertIn("reference_files:", submit)
        self.assertNotIn("refreshRecentReferenceFiles", submit)
        for code in (
            "reference_file_empty",
            "reference_file_type_unsupported",
            "reference_file_type_mismatch",
            "reference_file_invalid",
            "reference_file_too_large",
            "reference_files_total_too_large",
            "reference_file_missing",
            "reference_files_require_responses",
            "provider_reference_files_unsupported",
        ):
            self.assertIn(code, submit)

    def test_availability_uses_unified_auth_provider_mode_update_path(self) -> None:
        mode = (ROOT / "codex_image/webui/frontend/src/api-mode-settings.ts").read_text(encoding="utf-8")
        module = (ROOT / "codex_image/webui/frontend/src/reference-file-inputs.ts").read_text(encoding="utf-8")
        self.assertRegex(
            mode,
            r"function updateModeSpecificSettings[\s\S]*legacyMethod\(\"syncReferenceFileAvailability\"\)",
        )
        self.assertRegex(
            module,
            r"function syncReferenceFileAvailability[\s\S]*responsesEnabled\(\)[\s\S]*requirementActionVisible = false[\s\S]*renderReferenceFiles\(\)",
        )

    def test_form_reset_clears_selection_without_recent_file_state(self) -> None:
        shell = (ROOT / "codex_image/webui/frontend/src/shell-ui.ts").read_text(encoding="utf-8")
        module = (ROOT / "codex_image/webui/frontend/src/reference-file-inputs.ts").read_text(encoding="utf-8")
        reset = shell[shell.index("function resetForm()") : shell.index("async function copyJson()")]
        self.assertIn('legacyMethod("clearReferenceFiles", { silent: true })', reset)
        self.assertNotIn("recentReferenceFiles", reset)
        self.assertNotIn('els.clearImagesButton?.addEventListener("click", clearReferenceFiles)', module)

    def test_visual_limit_tooltip_product_surface_is_absent(self) -> None:
        html = (ROOT / "codex_image/webui/static/index.html").read_text(encoding="utf-8")
        module = (ROOT / "codex_image/webui/frontend/src/reference-file-inputs.ts").read_text(encoding="utf-8")
        self.assertNotIn('id="referenceFileInfo"', html)
        self.assertNotIn('id="referenceFileVisualLimitTooltip"', html)
        self.assertNotIn('aria-describedby="referenceFileVisualLimitTooltip"', html)
        self.assertNotIn("bindVisualLimitTooltip", module)

    def test_channel_and_provider_switches_preserve_files_without_warning(self) -> None:
        auth = (ROOT / "codex_image/webui/frontend/src/auth-source.ts").read_text(encoding="utf-8")
        providers = (ROOT / "codex_image/webui/frontend/src/api-provider-settings.ts").read_text(encoding="utf-8")
        selection = (ROOT / "codex_image/webui/frontend/src/task-selection.ts").read_text(encoding="utf-8")
        self.assertNotIn("guardReferenceFilesBeforePathSwitch", auth)
        self.assertNotIn("guardReferenceFilesBeforePathSwitch", providers)
        self.assertNotIn("clearReferenceFiles", auth)
        self.assertNotIn("clearReferenceFiles", providers)
        self.assertIn("restoreTaskReferenceFiles", selection)
        self.assertIn("task.reference_files", selection)

    def test_reference_file_module_does_not_expose_channel_switch_warning(self) -> None:
        module = (ROOT / "codex_image/webui/frontend/src/reference-file-inputs.ts").read_text(encoding="utf-8")
        self.assertNotIn("guardReferenceFilesBeforePathSwitch", module)
        self.assertNotIn("referenceFiles.switchTitle", module)
        self.assertNotIn("referenceFiles.removeAndSwitch", module)

    def test_images_submission_failure_is_rendered_in_preview(self) -> None:
        submit = (ROOT / "codex_image/webui/frontend/src/task-submit.ts").read_text(encoding="utf-8")
        runtime = (ROOT / "codex_image/webui/frontend/src/runtime-feedback.ts").read_text(encoding="utf-8")
        self.assertIn('reference_files_require_responses: "referenceFiles.requiresResponses"', submit)
        catch_block = submit[submit.index("} catch (error) {") : submit.index("} finally {")]
        self.assertIn("markPendingTaskFailed(pendingTask.task_id, message)", catch_block)
        failed = runtime[runtime.index("export function markPendingTaskFailed") : runtime.index("export function startRunFeedback")]
        self.assertIn('task.status = "failed"', failed)
        self.assertIn("renderPreview(task)", failed)

    def test_task_restore_and_history_handoff_keep_files_out_of_image_restore(self) -> None:
        selection = (ROOT / "codex_image/webui/frontend/src/task-selection.ts").read_text(encoding="utf-8")
        inputs = (ROOT / "codex_image/webui/frontend/src/input-sources.ts").read_text(encoding="utf-8")
        self.assertIn("function restoreTaskReferenceFiles", selection)
        restore = selection[
            selection.index("function restoreTaskReferenceFiles") : selection.index("async function fetchHistoryInputBlob")
        ]
        self.assertIn("state.referenceFiles", restore)
        self.assertNotIn("fetch(", restore)
        self.assertNotIn("state.images", restore)
        self.assertIn("restoreTaskReferenceFiles(task,", selection)
        self.assertIn("reference_file_id", inputs)
        self.assertIn("requested_backend", inputs)
        self.assertIn("addReferenceFileInput", inputs)
        handoff = inputs[inputs.index("async function restoreHistoryReferenceHandoff") : inputs.index("function bindInputSourceEvents")]
        self.assertEqual(handoff.count("localStorage.removeItem(HISTORY_REFERENCE_HANDOFF_KEY)"), 1)

    def test_task_reference_restore_is_guarded_by_restore_sequence(self) -> None:
        selection = (ROOT / "codex_image/webui/frontend/src/task-selection.ts").read_text(encoding="utf-8")
        self.assertEqual(selection.count("restoreTaskReferenceFiles(task, { taskId, restoreSeq })"), 2)
        normal_select = selection[selection.index("async function selectTask") : selection.index("async function restoreHistoryTaskReuseHandoff")]
        history_reuse = selection[selection.index("async function restoreHistoryTaskReuseHandoff") : selection.index("export function initTaskSelectionFeature")]
        self.assertIn("restoreTaskReferenceFiles(task, { taskId, restoreSeq })", normal_select)
        self.assertIn("restoreTaskReferenceFiles(task, { taskId, restoreSeq })", history_reuse)
        restore = selection[
            selection.index("function restoreTaskReferenceFiles") : selection.index("async function fetchHistoryInputBlob")
        ]
        self.assertIn("selectedTaskInputRestoreCurrent(taskId, restoreSeq)", restore)
        self.assertEqual(restore.count("selectedTaskInputRestoreCurrent(taskId, restoreSeq)"), 1)
        self.assertNotIn('legacyMethod("currentAuthSource")', restore)
        self.assertNotIn('legacyMethod("currentApiMode")', restore)
        self.assertNotIn('legacyMethod("currentCodexMode")', restore)
        self.assertNotIn('legacyMethod("setAuthSource"', restore)
        self.assertNotIn('legacyMethod("selectCodexMode"', restore)

    def test_same_task_a_b_a_stale_reference_restore_cannot_write(self) -> None:
        node = shutil.which("node")
        if node is None:
            self.skipTest("node is required for frontend behavior checks")
        module_path = ROOT / "codex_image/webui/frontend/src/task-selection.ts"
        harness = textwrap.dedent(
            f"""
            const fs = require("fs");
            const ts = require("typescript");
            const vm = require("vm");
            const source = fs.readFileSync({str(module_path)!r}, "utf8")
              + "\\nexport {{ restoreTaskReferenceFiles as __restoreTaskReferenceFiles }};\\n";
            const code = ts.transpileModule(source, {{
              compilerOptions: {{ module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 }},
            }}).outputText;
            const state = {{
              selectedTaskId: "task-a", taskInputRestoreSeq: 1, referenceFiles: [],
              apiSettings: {{ providers: [] }},
            }};
            const bridge = {{ state, els: {{}}, methods: {{
              renderReferenceFiles() {{}}, updateRequestPreview() {{}}, setStatus() {{}},
              currentAuthSource() {{ return "api"; }},
              currentApiMode() {{ return "responses"; }},
              currentCodexMode() {{ return "responses"; }},
            }} }};
            const module = {{ exports: {{}} }};
            vm.runInNewContext(code, {{
              module, exports: module.exports, console, Promise, Set, Map, Array,
              require(name) {{
                if (name === "./i18n") return {{ formatTranslation: (key) => key, translate: (key) => key }};
                if (name === "./state") return {{ getLegacyBridge: () => bridge }};
                throw new Error(`unexpected require: ${{name}}`);
              }},
            }});
            const restore = module.exports.__restoreTaskReferenceFiles;
            const task = (taskId, fileId) => ({{
              task_id: taskId, requested_backend: "codex_responses",
              reference_files: [{{ id: fileId, filename: `${{fileId}}.pdf`, mime_type: "application/pdf", size_bytes: 1, family: "pdf" }}],
            }});
            (async () => {{
              state.selectedTaskId = "task-b"; state.taskInputRestoreSeq = 2;
              await restore(task("task-a", "a-old"), {{ taskId: "task-a", restoreSeq: 1 }});
              await restore(task("task-b", "b"), {{ taskId: "task-b", restoreSeq: 2 }});
              state.selectedTaskId = "task-a"; state.taskInputRestoreSeq = 3;
              await restore(task("task-a", "a-new"), {{ taskId: "task-a", restoreSeq: 3 }});
              if (state.referenceFiles.length !== 1 || state.referenceFiles[0].id !== "a-new") {{
                throw new Error(`stale restore overwrote current files: ${{JSON.stringify(state.referenceFiles)}}`);
              }}
            }})().catch((error) => {{ console.error(error); process.exit(1); }});
            """
        )
        result = subprocess.run([node, "-e", harness], cwd=ROOT, check=False, text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_task_restore_displays_files_on_current_api_images_channel(self) -> None:
        node = shutil.which("node")
        if node is None:
            self.skipTest("node is required for frontend behavior checks")
        module_path = ROOT / "codex_image/webui/frontend/src/task-selection.ts"
        harness = textwrap.dedent(
            f"""
            const fs = require("fs");
            const ts = require("typescript");
            const vm = require("vm");
            const source = fs.readFileSync({str(module_path)!r}, "utf8")
              + "\\nexport {{ restoreTaskReferenceFiles as __restoreTaskReferenceFiles }};\\n";
            const code = ts.transpileModule(source, {{
              compilerOptions: {{ module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 }},
            }}).outputText;
            let authSwitches = 0;
            let codexModeSwitches = 0;
            const state = {{
              selectedTaskId: "task-a", taskInputRestoreSeq: 1,
              referenceFiles: [], apiSettings: {{ providers: [] }},
            }};
            const bridge = {{ state, els: {{}}, methods: {{
              renderReferenceFiles() {{}}, updateRequestPreview() {{}}, setStatus() {{}},
              currentAuthSource() {{ return "api"; }},
              currentApiMode() {{ return "images"; }},
              currentCodexMode() {{ return "responses"; }},
              selectCodexMode() {{ codexModeSwitches += 1; return Promise.resolve(true); }},
              setAuthSource() {{ authSwitches += 1; return Promise.resolve(true); }},
            }} }};
            const module = {{ exports: {{}} }};
            vm.runInNewContext(code, {{
              module, exports: module.exports, console, Promise, Set, Map, Array,
              require(name) {{
                if (name === "./i18n") return {{ formatTranslation: (key) => key, translate: (key) => key }};
                if (name === "./state") return {{ getLegacyBridge: () => bridge }};
                throw new Error(`unexpected require: ${{name}}`);
              }},
            }});
            (async () => {{
              const restored = await module.exports.__restoreTaskReferenceFiles({{
                task_id: "task-a", requested_backend: "codex_responses",
                reference_files: [{{ id: "a".repeat(64), filename: "new.md", mime_type: "text/markdown", size_bytes: 1, family: "text" }}],
              }}, {{ taskId: "task-a", restoreSeq: 1 }});
              if (restored !== true) throw new Error("reference files were not restored");
              if (state.referenceFiles.length !== 1) throw new Error("reference file restore failed");
              if (authSwitches !== 0) throw new Error(`task selection switched auth source ${{authSwitches}} time(s)`);
              if (codexModeSwitches !== 0) throw new Error(`task selection switched Codex mode ${{codexModeSwitches}} time(s)`);
            }})().catch((error) => {{ console.error(error); process.exit(1); }});
            """
        )
        result = subprocess.run([node, "-e", harness], cwd=ROOT, check=False, text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_history_file_handoff_aborts_when_auth_patch_fails(self) -> None:
        node = shutil.which("node")
        if node is None:
            self.skipTest("node is required for frontend behavior checks")
        module_path = ROOT / "codex_image/webui/frontend/src/input-sources.ts"
        handoff = [{
            "reference_file_id": "a" * 64,
            "filename": "brief.md",
            "mime_type": "text/markdown",
            "size_bytes": 10,
            "family": "text",
            "requested_backend": "codex_responses",
            "api_provider_id": "",
        }]
        harness = textwrap.dedent(
            f"""
            const fs = require("fs");
            const ts = require("typescript");
            const vm = require("vm");
            const source = fs.readFileSync({str(module_path)!r}, "utf8")
              + "\\nexport {{ restoreHistoryReferenceHandoff as __restoreHistoryReferenceHandoff }};\\n";
            const code = ts.transpileModule(source, {{
              compilerOptions: {{ module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 }},
            }}).outputText;
            const state = {{ images: [], tasks: [], referenceFiles: [], apiSettings: {{ providers: [] }} }};
            const added = [];
            let stored = {json.dumps(json.dumps(handoff))};
            const localStorage = {{
              getItem() {{ return stored; }},
              removeItem() {{ stored = ""; }},
            }};
            const bridge = {{ state, els: {{}}, methods: {{
              selectCodexMode() {{ return Promise.resolve(true); }},
              setAuthSource() {{ return Promise.resolve(false); }},
              setStatus() {{}},
            }} }};
            const module = {{ exports: {{}} }};
            vm.runInNewContext(code, {{
              module, exports: module.exports, console, Promise, Set, Map, Array, localStorage,
              URL: {{ createObjectURL() {{ return "blob:test"; }}, revokeObjectURL() {{}} }},
              File: class File {{}}, document: {{ addEventListener() {{}} }},
              require(name) {{
                if (name === "./dom") return {{ getEls: () => ({{}}) }};
                if (name === "./i18n") return {{ formatTranslation: (key) => key, LOCALE_CHANGE_EVENT: "locale", translate: (key) => key }};
                if (name === "./state") return {{ getLegacyBridge: () => bridge, getState: () => state }};
                if (name === "./reference-file-inputs") return {{
                  addReferenceFileInput: (item) => added.push(item), partitionReferenceDropFiles: () => ({{ images: [], referenceFiles: [], unsupported: [] }}),
                }};
                throw new Error(`unexpected require: ${{name}}`);
              }},
            }});
            (async () => {{
              await module.exports.__restoreHistoryReferenceHandoff();
              if (added.length || state.referenceFiles.length) throw new Error("handoff retained files after failed auth switch");
              if (stored !== "") throw new Error("handoff key was not consumed");
            }})().catch((error) => {{ console.error(error); process.exit(1); }});
            """
        )
        result = subprocess.run([node, "-e", harness], cwd=ROOT, check=False, text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_provider_switch_has_no_reference_file_snapshot_transaction(self) -> None:
        module = (ROOT / "codex_image/webui/frontend/src/api-provider-settings.ts").read_text(encoding="utf-8")
        self.assertNotIn("guardReferenceFilesBeforePathSwitch", module)
        self.assertNotIn("referenceFileSnapshot", module)
        return
        node = shutil.which("node")
        if node is None:
            self.skipTest("node is required for frontend behavior checks")
        module_path = ROOT / "codex_image/webui/frontend/src/reference-file-inputs.ts"
        harness = textwrap.dedent(
            f"""
            const fs = require("fs");
            const ts = require("typescript");
            const vm = require("vm");
            const source = fs.readFileSync({str(module_path)!r}, "utf8");
            const code = ts.transpileModule(source, {{
              compilerOptions: {{ module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 }},
            }}).outputText;
            const original = {{ id: "file-1", filename: "one.pdf" }};
            const state = {{ referenceFiles: [original], recentReferenceFiles: [] }};
            let confirmOptions = null;
            let renderCount = 0;
            let previewCount = 0;
            let focusCount = 0;
            const bridge = {{ methods: {{
              openConfirmPopover(_anchor, options) {{ confirmOptions = options; }},
              updateRequestPreview() {{ previewCount += 1; }},
            }} }};
            const sandbox = {{
              module: {{ exports: {{}} }}, exports: {{}}, console,
              require(name) {{
                if (name === "./dom") return {{ getEls: () => ({{}}) }};
                if (name === "./i18n") return {{
                  formatTranslation: (key) => key,
                  LOCALE_CHANGE_EVENT: "locale-change",
                  translate: (key) => key,
                }};
                if (name === "./state") return {{ getLegacyBridge: () => bridge, getState: () => state }};
                if (name === "./reference-file-icons") return {{ referenceFileIconSvgMarkup: () => "<svg></svg>" }};
                throw new Error(`unexpected require: ${{name}}`);
              }},
              document: {{ body: {{ focus() {{ focusCount += 1; }} }} }},
              File: class File {{}}, Set, Map, Array, Promise,
            }};
            sandbox.exports = sandbox.module.exports;
            vm.runInNewContext(code, sandbox);
            const api = sandbox.module.exports;
            api.renderReferenceFiles = () => {{ renderCount += 1; }};
            const anchor = {{ focus() {{ focusCount += 1; }} }};
            (async () => {{
              const continued = api.guardReferenceFilesBeforePathSwitch(false, anchor, async () => false);
              if (continued !== false || !confirmOptions) throw new Error("guard did not open confirmation");
              await confirmOptions.onConfirm();
              if (state.referenceFiles.length !== 1 || state.referenceFiles[0] !== original) {{
                throw new Error("failed switch did not restore reference-file snapshot");
              }}
              if (focusCount !== 1) throw new Error(`focus count ${{focusCount}}`);
              if (previewCount < 2) throw new Error(`preview count ${{previewCount}}`);
            }})().catch((error) => {{ console.error(error); process.exit(1); }});
            """
        )
        result = subprocess.run([node, "-e", harness], cwd=ROOT, check=False, text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_failed_provider_patch_does_not_mutate_reference_files(self) -> None:
        module = (ROOT / "codex_image/webui/frontend/src/api-provider-settings.ts").read_text(encoding="utf-8")
        save = module[module.index("export async function saveApiSettings") :]
        self.assertIn("const previousSettings = normalizeApiSettings(state.apiSettings)", save)
        self.assertIn("state.apiSettings = previousSettings", save)
        self.assertNotIn("clearReferenceFiles", module)
        self.assertNotIn("referenceFileSnapshot", module)
        return
        node = shutil.which("node")
        if node is None:
            self.skipTest("node is required for frontend behavior checks")
        reference_path = ROOT / "codex_image/webui/frontend/src/reference-file-inputs.ts"
        provider_path = ROOT / "codex_image/webui/frontend/src/api-provider-settings.ts"
        harness = textwrap.dedent(
            f"""
            const fs = require("fs");
            const ts = require("typescript");
            const vm = require("vm");
            const transpile = (path) => ts.transpileModule(fs.readFileSync(path, "utf8"), {{
              compilerOptions: {{ module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 }},
            }}).outputText;
            const originalFile = {{ id: "file-1", filename: "one.pdf" }};
            const originalDraft = {{
              id: "provider-a", name: "Provider A", base_url: "https://example.test/v1",
              api_key: "", image_model: "gpt-image-1", api_mode: "responses",
              images_concurrency: 1, api_key_set: true, api_key_masked: "***",
              api_key_source_provider_id: "",
            }};
            const state = {{
              referenceFiles: [originalFile], recentReferenceFiles: [], mode: "generate",
              apiSettings: {{ codex_mode: "responses", active_provider_id: "provider-a", providers: [{{ ...originalDraft }}] }},
              apiProviderEditingId: "provider-a", apiProviderDraft: {{ ...originalDraft }},
              apiProviderDraftIsNew: false, apiProviderSortMode: false, apiSettingsSaveTimerId: null,
            }};
            const field = (value = "") => ({{ value, dispatchEvent() {{}}, classList: {{ toggle() {{}} }}, setAttribute() {{}}, removeAttribute() {{}} }});
            const els = {{
              apiProviderName: field("Provider A"), apiBaseUrl: field("https://example.test/v1"),
              apiKey: field(""), apiMode: field("images"), apiImageModel: field("gpt-image-1"),
              apiImagesConcurrency: field("1"), saveApiProviderEditButton: field(""),
            }};
            let confirmOptions = null;
            let focusCount = 0;
            let patch = null;
            const persisted = [];
            const bridge = {{ state, els, methods: {{
              openConfirmPopover(_anchor, options) {{ confirmOptions = options; }},
              updateRequestPreview() {{}}, setStatus() {{}}, renderAuthSource() {{}}, closePromptPopover() {{}},
            }} }};
            const localStorage = {{
              setItem(key, value) {{ persisted.push([key, value]); }}, getItem() {{ return null; }},
            }};
            const shared = {{
              console, localStorage,
              document: {{ body: {{ focus() {{ focusCount += 1; }} }}, activeElement: null }},
              window: {{ setTimeout: () => 1, clearTimeout() {{}} }},
              Event: class Event {{ constructor(type) {{ this.type = type; }} }},
              HTMLElement: class HTMLElement {{}}, File: class File {{}}, Set, Map, Array, Promise,
              fetch: async (_url, options) => {{ patch = options; return {{ ok: false, json: async () => ({{ detail: "save failed" }}) }}; }},
            }};
            const i18n = {{ formatTranslation: (key) => key, LOCALE_CHANGE_EVENT: "locale-change", translate: (key) => key }};
            const dom = {{ getEls: () => els }};
            const stateModule = {{ getLegacyBridge: () => bridge, getState: () => state }};
            const evaluate = (code, requireFn) => {{
              const module = {{ exports: {{}} }};
              vm.runInNewContext(code, {{ ...shared, module, exports: module.exports, require: requireFn }});
              return module.exports;
            }};
            const referenceApi = evaluate(transpile({str(reference_path)!r}), (name) => {{
              if (name === "./dom") return dom;
              if (name === "./i18n") return i18n;
              if (name === "./state") return stateModule;
              if (name === "./reference-file-icons") return {{ referenceFileIconSvgMarkup: () => "<svg></svg>" }};
              throw new Error(`unexpected reference require: ${{name}}`);
            }});
            const providerApi = evaluate(transpile({str(provider_path)!r}), (name) => {{
              if (name === "./state") return stateModule;
              if (name === "./state-defaults") return {{
                API_SETTINGS_STORAGE_KEY: "api-settings", DEFAULT_API_BASE_URL: "https://api.openai.com/v1",
                DEFAULT_API_IMAGE_MODEL: "gpt-image-1", DEFAULT_API_IMAGES_CONCURRENCY: 1,
                DEFAULT_API_MODE: "images", DEFAULT_CODEX_MODE: "images",
              }};
              if (name === "./auth-source") return {{ refreshHealth: async () => {{}} }};
              if (name === "./api-mode-settings") return {{ updateModeSpecificSettings() {{}} }};
              if (name === "./i18n") return i18n;
              if (name === "./system-settings") return {{ closeSystemSettingsModal() {{}}, openSystemSettingsModal() {{}} }};
              if (name === "./api-advanced-settings") return {{ resetApiAdvancedSettings() {{}} }};
              if (name === "./api-provider-list-ui") return {{
                apiProviderMatchesSearch: () => true, scrollActiveApiProviderCardIntoView() {{}},
                updateApiProviderListPresentation: () => "",
              }};
              if (name === "./reference-file-inputs") return referenceApi;
              throw new Error(`unexpected provider require: ${{name}}`);
            }});
            const anchor = {{ focus() {{ focusCount += 1; }} }};
            (async () => {{
              referenceApi.guardReferenceFilesBeforePathSwitch(false, anchor, () => providerApi.saveApiSettings());
              if (!confirmOptions) throw new Error("missing confirmation");
              await confirmOptions.onConfirm();
              const active = state.apiSettings.providers.find((item) => item.id === state.apiSettings.active_provider_id);
              if (patch?.method !== "PATCH") throw new Error("provider PATCH was not attempted");
              if (active?.id !== "provider-a" || active?.api_mode !== "responses") throw new Error("active path was not rolled back");
              if (state.apiProviderEditingId !== "provider-a" || state.apiProviderDraft?.api_mode !== "responses") throw new Error("draft was not restored");
              if (state.referenceFiles.length !== 1 || state.referenceFiles[0] !== originalFile) throw new Error("files were not restored");
              const saved = JSON.parse(persisted[persisted.length - 1][1]);
              if (saved.active_provider_id !== "provider-a" || saved.providers[0].api_mode !== "responses") throw new Error("persisted path was not rolled back");
              if (focusCount !== 1) throw new Error(`focus count ${{focusCount}}`);
            }})().catch((error) => {{ console.error(error); process.exit(1); }});
            """
        )
        result = subprocess.run([node, "-e", harness], cwd=ROOT, check=False, text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_mode_and_provider_save_do_not_use_reference_file_guards(self) -> None:
        auth = (ROOT / "codex_image/webui/frontend/src/auth-source.ts").read_text(encoding="utf-8")
        providers = (ROOT / "codex_image/webui/frontend/src/api-provider-settings.ts").read_text(encoding="utf-8")
        auth_switch = auth[auth.index("export async function setAuthSource") : auth.index("export function handleAuthSourceClick")]
        provider_select = providers[providers.index("export function selectApiProvider") : providers.index("export function editApiProvider")]
        save = providers[providers.index("export async function saveApiProviderEdit") : providers.index("function renderAuthSourceAfterProviderChange")]
        codex = providers[providers.index("export function selectCodexMode") : providers.index("export function queueApiSettingsAutosave")]
        self.assertNotIn("normalized === currentAuthSource()", auth_switch)
        self.assertNotRegex(auth_switch, r"if \(!switchAnchor\)[\s\S]*continueSwitch")
        self.assertNotRegex(provider_select, r"!switchAnchor\s*\|\|")
        self.assertNotRegex(save, r"if \(!anchor\)[\s\S]*continueSwitch")
        self.assertNotRegex(codex, r"if \(!switchAnchor\)[\s\S]*continueSwitch")
        save_settings = providers[providers.index("export async function saveApiSettings") :]
        self.assertIn("const previousSettings = normalizeApiSettings(state.apiSettings)", save_settings)
        self.assertIn("state.apiSettings = previousSettings", save_settings)
        self.assertIn("return false", save_settings)
        module = (ROOT / "codex_image/webui/frontend/src/reference-file-inputs.ts").read_text(encoding="utf-8")
        self.assertNotIn("guardReferenceFilesBeforePathSwitch", module)


class ReferenceFileFrontendBehaviorTests(unittest.TestCase):
    def test_composed_image_file_rail_runtime_contract(self) -> None:
        node = shutil.which("node")
        if node is None:
            self.skipTest("node is required for frontend behavior checks")
        image_strip_path = ROOT / "codex_image/webui/frontend/src/image-strip.ts"
        reference_path = ROOT / "codex_image/webui/frontend/src/reference-file-inputs.ts"
        harness = textwrap.dedent(
            f"""
            const fs = require("fs");
            const ts = require("typescript");
            const vm = require("vm");
            const transpile = (path) => ts.transpileModule(fs.readFileSync(path, "utf8"), {{
              compilerOptions: {{ module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 }},
            }}).outputText;
            class File {{
              constructor(name, type) {{ this.name = name; this.type = type; this.size = 12; }}
            }}
            class FakeClassList {{
              constructor(owner) {{ this.owner = owner; this.values = new Set(); }}
              add(...values) {{ values.forEach((value) => this.values.add(value)); }}
              remove(...values) {{ values.forEach((value) => this.values.delete(value)); }}
              toggle(value, force) {{
                if (force === undefined) force = !this.values.has(value);
                force ? this.values.add(value) : this.values.delete(value);
                return force;
              }}
              contains(value) {{ return this.values.has(value); }}
            }}
            class FakeElement {{
              constructor(tag = "div") {{
                this.tagName = tag.toUpperCase(); this.children = []; this.parentElement = null;
                this.attributes = {{}}; this.listeners = {{}}; this.className = "";
                this.classList = new FakeClassList(this); this.title = ""; this.tabIndex = -1;
                this.textContent = ""; this.value = ""; this.clientWidth = 0;
                this.scrollWidth = 0; this.scrollLeft = 0;
                this._innerHTML = "";
              }}
              set innerHTML(value) {{ this._innerHTML = String(value); this.replaceChildren(); }}
              get innerHTML() {{ return this._innerHTML; }}
              append(...children) {{ children.forEach((child) => {{ child.parentElement = this; this.children.push(child); }}); }}
              remove() {{
                if (!this.parentElement) return;
                this.parentElement.children = this.parentElement.children.filter((child) => child !== this);
                this.parentElement = null;
              }}
              replaceChildren(...children) {{
                this.children.forEach((child) => {{ child.parentElement = null; }}); this.children = [];
                this.append(...children);
              }}
              setAttribute(name, value) {{ this.attributes[name] = String(value); }}
              getAttribute(name) {{ return this.attributes[name] ?? null; }}
              addEventListener(name, handler) {{ (this.listeners[name] ||= []).push(handler); }}
              click() {{ (this.listeners.click || []).forEach((handler) => handler({{ target: this, stopPropagation() {{}} }})); }}
              press(key) {{ if (this.tagName === "BUTTON" && (key === "Enter" || key === " ")) this.click(); }}
              focus() {{ document.activeElement = this; }}
              contains(target) {{ return target === this || this.children.some((child) => child.contains?.(target)); }}
              closest(selector) {{
                let current = this;
                while (current) {{
                  if (selector.startsWith(".") && (current.classList.contains(selector.slice(1)) || current.className.split(/\\s+/).includes(selector.slice(1)))) return current;
                  current = current.parentElement;
                }}
                return null;
              }}
            }}
            const document = {{
              activeElement: null, body: new FakeElement("body"),
              createElement: (tag) => new FakeElement(tag), createTextNode: (text) => Object.assign(new FakeElement("#text"), {{ textContent: text }}),
              addEventListener() {{}}, querySelector() {{ return null; }},
            }};
            const window = {{ addEventListener() {{}}, location: {{ origin: "http://127.0.0.1" }} }};
            const workspace = new FakeElement(); workspace.classList.add("image-input-workspace");
            const imageUploaderGrid = new FakeElement(); imageUploaderGrid.classList.add("image-uploader-grid"); imageUploaderGrid.clientWidth = 400;
            const imageStrip = new FakeElement();
            const imageThumbList = new FakeElement(); imageThumbList.clientWidth = 260; imageThumbList.scrollWidth = 260;
            const imageThumbItems = new FakeElement();
            const referenceFileSelection = new FakeElement(); referenceFileSelection.classList.add("hidden");
            const imageUploadSource = new FakeElement();
            imageThumbList.append(imageThumbItems, referenceFileSelection);
            imageStrip.append(imageThumbList, imageUploadSource);
            imageUploaderGrid.append(imageStrip); workspace.append(imageUploaderGrid);
            const els = {{
              imageInput: new FakeElement("input"), clearImagesButton: new FakeElement("button"),
              imageStrip, imageThumbList, imageThumbItems, referenceFileSelection,
              imageUploaderGrid, imageUploadSource, statusText: new FakeElement(),
            }};
            const state = {{ images: [], referenceFiles: [], recentReferenceFiles: [], tasks: [], mode: "generate" }};
            let codexMode = "responses";
            const bridge = {{ state, els, methods: {{
              currentAuthSource: () => "codex", currentCodexMode: () => codexMode,
              selectCodexMode(mode) {{ codexMode = mode; }}, setStatus(message) {{ els.statusText.textContent = message; }},
              updateRequestPreview() {{}}, updateCustomRatioReferenceButtonState() {{}}, syncPromptGalleryMentionsFromInputs() {{}},
              setMode() {{}}, sourcePreviewUrl: () => "blob:image", sourceName: (source) => source.file?.name || source.name || "image",
              isEditableImageSource: () => false, categoryLabel: () => "category", canAddSourceToGallery: () => false,
              revokeUploadPreviewUrl() {{}}, revokeUploadPreviewUrls() {{}},
            }} }};
            const shared = {{
              console, File, Set, Map, Array, Promise, document, window,
              HTMLElement: FakeElement, WheelEvent: {{ DOM_DELTA_LINE: 1, DOM_DELTA_PAGE: 2 }},
            }};
            const i18n = {{
              formatTranslation: (_key, values) => `Remove ${{values.filename}}`,
              LOCALE_CHANGE_EVENT: "locale-change", translate: (key) => key,
            }};
            const dom = {{ getEls: () => els }};
            const stateModule = {{ getLegacyBridge: () => bridge, getState: () => state }};
            const evaluate = (code, requireFn) => {{
              const module = {{ exports: {{}} }};
              vm.runInNewContext(code, {{ ...shared, module, exports: module.exports, require: requireFn }});
              return module.exports;
            }};
            const referenceApi = evaluate(transpile({str(reference_path)!r}), (name) => {{
              if (name === "./dom") return dom;
              if (name === "./i18n") return i18n;
              if (name === "./state") return stateModule;
              if (name === "./reference-file-icons") return {{ referenceFileIconSvgMarkup: (name) => `<svg data-file="${{name}}"></svg>` }};
              throw new Error(`unexpected reference require: ${{name}}`);
            }});
            const imageApi = evaluate(transpile({str(image_strip_path)!r}), (name) => {{
              if (name === "./dom") return dom;
              if (name === "./i18n") return i18n;
              if (name === "./state") return stateModule;
              throw new Error(`unexpected image require: ${{name}}`);
            }});
            imageApi.initImageStripFeature();
            const errors = [];
            const check = (condition, message) => {{ if (!condition) errors.push(message); }};

            const docx = new File("full-accessible-plan.docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document");
            referenceApi.addReferenceFileInput(docx);
            check(imageUploaderGrid.classList.contains("has-inputs"), "file-only state did not set has-inputs");
            check(!imageUploaderGrid.classList.contains("has-images"), "file-only state set has-images");
            check(referenceFileSelection.children.length === 1 && imageThumbItems.children.length === 0, "file-only rail composition mismatch");
            const originalFileTile = referenceFileSelection.children[0];

            state.images = [{{ kind: "upload", file: new File("one.png", "image/png") }}];
            bridge.methods.renderImageStrip();
            check(imageThumbItems.children.length === 1 && referenceFileSelection.children[0] === originalFileTile, "mixed rail did not preserve separate siblings");
            check(imageUploaderGrid.classList.contains("has-images") && imageUploaderGrid.classList.contains("has-inputs"), "mixed state classes mismatch");
            state.images = [{{ kind: "upload", file: new File("two.png", "image/png") }}];
            bridge.methods.renderImageStrip();
            check(referenceFileSelection.children[0] === originalFileTile, "image rerender replaced file tile");

            imageUploaderGrid.clientWidth = 350;
            bridge.methods.updateImageStripDensity();
            check(imageUploaderGrid.classList.contains("compact-grid"), "combined image/file count did not cross compact threshold");

            const remove = referenceFileSelection.children[0]?.children.find((child) => child.className === "thumb-remove reference-file-remove");
            check(remove?.tagName === "BUTTON" && remove.getAttribute("aria-label")?.includes(docx.name), "remove button is not keyboard accessible by filename");
            remove?.press("Enter");
            check(state.referenceFiles.length === 0, "keyboard activation did not remove the selected file");

            referenceApi.addReferenceFileInput(docx);
            const stableChildren = imageThumbList.children.slice();
            els.imageThumbItems = null;
            bridge.methods.renderImageStrip();
            check(imageThumbList.children.length === stableChildren.length && imageThumbList.children.every((child, index) => child === stableChildren[index]), "missing imageThumbItems cleared the parent rail");
            els.imageThumbItems = imageThumbItems;

            state.images = []; state.referenceFiles = []; codexMode = "images";
            referenceApi.clearReferenceFiles();
            referenceApi.addReferenceFileInput(new File("guarded.docx", docx.type));
            const requirement = imageUploaderGrid.children.find((child) => child.className === "reference-file-requirement");
            check(Boolean(requirement) && requirement?.parentElement === imageUploaderGrid, "zero-input requirement CTA was not rendered outside the thumbnail flex tree");
            check(imageUploaderGrid.classList.contains("has-inputs"), "zero-input requirement CTA was not made visible");
            const action = requirement?.children.find((child) => child.tagName === "BUTTON");
            check(Boolean(action), "zero-input requirement CTA was not clickable");
            action?.click();
            check(codexMode === "responses", "requirement CTA did not switch to Responses");
            check(referenceFileSelection.classList.contains("hidden") && !imageUploaderGrid.classList.contains("has-inputs"), "requirement CTA did not clear its visible state");

            if (errors.length) throw new Error(errors.join("\\n"));
            """
        )
        result = subprocess.run([node, "-e", harness], cwd=ROOT, check=False, text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_mixed_picker_partitions_images_files_and_unsupported_inputs(self) -> None:
        node = shutil.which("node")
        if node is None:
            self.skipTest("node is required for frontend behavior checks")
        input_sources_path = ROOT / "codex_image/webui/frontend/src/input-sources.ts"
        image_strip_path = ROOT / "codex_image/webui/frontend/src/image-strip.ts"
        reference_path = ROOT / "codex_image/webui/frontend/src/reference-file-inputs.ts"
        harness = textwrap.dedent(
            f"""
            const fs = require("fs");
            const ts = require("typescript");
            const vm = require("vm");
            const transpile = (path) => ts.transpileModule(fs.readFileSync(path, "utf8"), {{
              compilerOptions: {{ module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 }},
            }}).outputText;
            class File {{
              constructor(name, type) {{ this.name = name; this.type = type; this.size = 1; }}
            }}
            class FakeElement {{
              constructor() {{
                this.children = []; this.listeners = {{}}; this.textContent = ""; this.value = "";
                this.classList = {{ add() {{}}, remove() {{}}, toggle() {{}}, contains() {{ return false; }} }};
              }}
              addEventListener(name, handler) {{ this.listeners[name] = handler; }}
              replaceChildren(...children) {{ this.children = children; this.renderCount = (this.renderCount || 0) + 1; }}
              append(...children) {{ this.children.push(...children); }}
              remove() {{}}
              setAttribute() {{}}
              removeAttribute() {{}}
              closest() {{ return null; }}
              contains() {{ return false; }}
              focus() {{}}
            }}
            const imageInput = new FakeElement();
            const clearImagesButton = new FakeElement();
            const referenceFileSelection = new FakeElement();
            const statusText = new FakeElement();
            const imageUploaderGrid = new FakeElement();
            const els = {{ imageInput, clearImagesButton, referenceFileSelection, statusText, imageUploaderGrid }};
            const state = {{ images: [], tasks: [], mode: "generate", referenceFiles: [], recentReferenceFiles: [] }};
            let codexMode = "images";
            const statuses = [];
            const bridge = {{ methods: {{
              updateRequestPreview() {{}},
              setMode() {{}},
              currentAuthSource() {{ return "codex"; }},
              currentCodexMode() {{ return codexMode; }},
              setStatus(message, type) {{ statuses.push([message, type]); statusText.textContent = message; }},
            }}, state, els }};
            const document = {{
              body: new FakeElement(),
              createElement() {{ return new FakeElement(); }},
              addEventListener() {{}},
            }};
            const window = {{ addEventListener() {{}}, location: {{ origin: "http://127.0.0.1" }} }};
            const shared = {{
              console, File, Set, Map, Array, Promise, document, window,
              URL: {{ createObjectURL: () => "blob:test", revokeObjectURL() {{}} }},
              Event: class Event {{}}, HTMLElement: FakeElement,
            }};
            const i18n = {{
              formatTranslation: (key) => key,
              LOCALE_CHANGE_EVENT: "locale-change",
              translate: (key) => key,
            }};
            const dom = {{ getEls: () => els }};
            const stateModule = {{ getLegacyBridge: () => bridge, getState: () => state }};
            const evaluate = (code, requireFn) => {{
              const module = {{ exports: {{}} }};
              vm.runInNewContext(code, {{ ...shared, module, exports: module.exports, require: requireFn }});
              return module.exports;
            }};
            const referenceApi = evaluate(transpile({str(reference_path)!r}), (name) => {{
              if (name === "./dom") return dom;
              if (name === "./i18n") return i18n;
              if (name === "./state") return stateModule;
              if (name === "./reference-file-icons") return {{ referenceFileIconSvgMarkup: () => "<svg></svg>" }};
              throw new Error(`unexpected reference require: ${{name}}`);
            }});
            const inputApi = evaluate(transpile({str(input_sources_path)!r}), (name) => {{
              if (name === "./dom") return dom;
              if (name === "./i18n") return i18n;
              if (name === "./state") return stateModule;
              if (name === "./reference-file-inputs") return referenceApi;
              throw new Error(`unexpected input require: ${{name}}`);
            }});
            const imageStripApi = evaluate(transpile({str(image_strip_path)!r}), (name) => {{
              if (name === "./dom") return dom;
              if (name === "./i18n") return i18n;
              if (name === "./state") return stateModule;
              throw new Error(`unexpected strip require: ${{name}}`);
            }});
            referenceApi.initReferenceFileInputsFeature();
            inputApi.initInputSourcesFeature();
            imageStripApi.initImageStripFeature();
            if (typeof imageInput.listeners.change !== "function") throw new Error("picker handler was not bound");

            const pick = (files) => {{
              imageInput.files = files;
              imageInput.value = "chosen";
              imageInput.listeners.change({{ target: imageInput }});
              if (imageInput.value !== "") throw new Error("picker value was not cleared");
            }};
            const files = (suffix) => [
              new File(`image-${{suffix}}.png`, "image/png"),
              new File(`brief-${{suffix}}.docx`, "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
              new File(`payload-${{suffix}}.bin`, "application/octet-stream"),
            ];

            const imagesFiles = files("images");
            pick(imagesFiles);
            if (state.images.length !== 1 || state.images[0].file !== imagesFiles[0]) throw new Error("Images mode did not add PNG exactly once");
            if (state.referenceFiles.length !== 0) throw new Error("Images mode accepted DOCX");
            if (!statuses.some(([message]) => message === "referenceFiles.requiresResponses")) throw new Error("Images mode did not guard DOCX");
            if (statuses[statuses.length - 1][0] !== "referenceFiles.errorUnsupported") throw new Error("unsupported was not final picker error");

            statuses.length = 0;
            pick([new File("guarded.docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document")]);
            if (statusText.textContent !== "referenceFiles.requiresResponses") throw new Error("missing stale requirement setup");
            const rendersBeforeSwitch = referenceFileSelection.renderCount || 0;
            codexMode = "responses";
            referenceApi.syncReferenceFileAvailability();
            if (statusText.textContent !== "status.waiting") throw new Error("Responses switch did not clear requirement status");
            if ((referenceFileSelection.renderCount || 0) <= rendersBeforeSwitch) throw new Error("Responses switch did not rerender requirement UI");

            state.images = [];
            state.referenceFiles = [];
            statuses.length = 0;
            const responsesFiles = files("responses");
            pick(responsesFiles);
            if (state.images.length !== 1 || state.images[0].file !== responsesFiles[0]) throw new Error("Responses picker PNG mismatch");
            if (state.referenceFiles.length !== 1 || state.referenceFiles[0].file !== responsesFiles[1]) throw new Error("Responses picker DOCX mismatch");
            if (statuses[statuses.length - 1][0] !== "referenceFiles.errorUnsupported") throw new Error("unsupported was not final Responses error");

            let dragActive = false;
            imageUploaderGrid.classList = {{
              add() {{}}, remove() {{}}, contains() {{ return false; }},
              toggle(name, active) {{ if (name === "drag-over") dragActive = Boolean(active); }},
            }};
            const protectedTransfer = {{
              files: [],
              items: [{{ kind: "file", type: "application/pdf", getAsFile() {{ return null; }} }}],
              types: ["Files"],
              dropEffect: "none",
            }};
            let dragOverPrevented = false;
            imageUploaderGrid.listeners.dragenter({{
              dataTransfer: protectedTransfer,
              preventDefault() {{}}, stopPropagation() {{}},
            }});
            if (!dragActive) throw new Error("protected reference drag did not activate the unified drop zone");
            imageUploaderGrid.listeners.dragover({{
              dataTransfer: protectedTransfer,
              preventDefault() {{ dragOverPrevented = true; }}, stopPropagation() {{}},
            }});
            if (!dragOverPrevented || protectedTransfer.dropEffect !== "copy") {{
              throw new Error(`protected reference drag was rejected: prevented=${{dragOverPrevented}} effect=${{protectedTransfer.dropEffect}}`);
            }}

            const dropFiles = files("drop");
            bridge.methods.handleImageDrop({{
              dataTransfer: {{ files: dropFiles, items: [], types: ["Files"] }},
              preventDefault() {{}}, stopPropagation() {{}},
            }});
            if (state.images.length !== 2 || state.images[1].file !== dropFiles[0]) throw new Error("drop PNG mismatch");
            if (state.referenceFiles.length !== 2 || state.referenceFiles[1].file !== dropFiles[1]) throw new Error("drop DOCX mismatch");
            if (statuses[statuses.length - 1][0] !== "referenceFiles.errorUnsupported") throw new Error("unsupported was not final drop error");

            clearImagesButton.listeners.click({{ target: clearImagesButton }});
            if (state.images.length !== 0 || state.referenceFiles.length !== 0) {{
              throw new Error(`clear button left inputs behind: images=${{state.images.length}}, files=${{state.referenceFiles.length}}`);
            }}
            """
        )
        result = subprocess.run([node, "-e", harness], cwd=ROOT, check=False, text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)

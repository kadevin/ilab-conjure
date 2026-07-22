from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient


class WebUIPWATests(unittest.TestCase):
    def test_static_pages_expose_pwa_manifest_and_service_worker_registration(self) -> None:
        index_html = Path("codex_image/webui/static/index.html").read_text(encoding="utf-8")
        history_html = Path("codex_image/webui/static/history.html").read_text(encoding="utf-8")
        pwa_script_path = Path("codex_image/webui/static/pwa.js")

        manifest_link = '<link rel="manifest" href="/manifest.webmanifest" />'
        theme_meta = '<meta name="theme-color" content="#457B66" />'
        pwa_script = '<script src="/static/pwa.js?v=pwa-1" defer></script>'

        self.assertIn(manifest_link, index_html)
        self.assertIn(manifest_link, history_html)
        self.assertIn(theme_meta, index_html)
        self.assertIn(theme_meta, history_html)
        self.assertIn(pwa_script, index_html)
        self.assertIn(pwa_script, history_html)
        self.assertTrue(pwa_script_path.exists())

        pwa_script_source = pwa_script_path.read_text(encoding="utf-8")
        self.assertIn('"serviceWorker" in navigator', pwa_script_source)
        self.assertIn("window.isSecureContext", pwa_script_source)
        self.assertIn('navigator.serviceWorker.register("/service-worker.js", { scope: "/" })', pwa_script_source)

    def test_web_app_manifest_uses_rabbit_brand_identity_and_installable_metadata(self) -> None:
        manifest_path = Path("codex_image/webui/static/manifest.webmanifest")
        self.assertTrue(manifest_path.exists())
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

        self.assertEqual(manifest["id"], "/")
        self.assertEqual(manifest["name"], "iLab CONJ Web")
        self.assertEqual(manifest["short_name"], "iLab CONJ Web")
        self.assertEqual(manifest["start_url"], "/")
        self.assertEqual(manifest["scope"], "/")
        self.assertEqual(manifest["display"], "standalone")
        self.assertEqual(manifest["theme_color"], "#457B66")
        self.assertEqual(manifest["background_color"], "#F6F8F5")

        icons = manifest.get("icons")
        self.assertIsInstance(icons, list)
        self.assertNotIn("/static/brand/favicon.svg", {icon.get("src") for icon in icons if isinstance(icon, dict)})
        self.assertIn(
            {"src": "/static/brand/pwa-icon-192.png", "sizes": "192x192", "type": "image/png", "purpose": "any maskable"},
            icons,
        )
        self.assertIn(
            {"src": "/static/brand/pwa-icon-512.png", "sizes": "512x512", "type": "image/png", "purpose": "any maskable"},
            icons,
        )

        for icon_path in (
            Path("codex_image/webui/static/brand/pwa-icon-192.png"),
            Path("codex_image/webui/static/brand/pwa-icon-512.png"),
        ):
            self.assertTrue(icon_path.exists(), str(icon_path))

    def test_pwa_document_title_omits_duplicate_brand_in_standalone_window(self) -> None:
        title_path = Path("codex_image/webui/frontend/src/web-app-title.ts")
        self.assertTrue(title_path.exists())
        title_source = title_path.read_text(encoding="utf-8")
        shell_source = Path("codex_image/webui/frontend/src/shell-ui.ts").read_text(encoding="utf-8")
        history_source = Path("codex_image/webui/frontend/src/history.ts").read_text(encoding="utf-8")

        self.assertIn('window.matchMedia?.("(display-mode: standalone)")?.matches', title_source)
        self.assertIn("navigator as Navigator & { standalone?: boolean }", title_source)
        self.assertIn("return isStandaloneWebApp() ? standaloneTitle : fullTitle;", title_source)
        self.assertIn('import { webAppDocumentTitle } from "./web-app-title"', shell_source)
        self.assertIn("const fullTitle = status ? `${status} · ${defaultTitle}` : defaultTitle;", shell_source)
        self.assertIn("document.title = webAppDocumentTitle(status, fullTitle);", shell_source)
        self.assertIn('import { webAppDocumentTitle } from "./web-app-title"', history_source)
        self.assertIn("function historyDocumentTitle()", history_source)
        self.assertIn('return webAppDocumentTitle(translate("history.title"), translate("history.documentTitle"));', history_source)
        self.assertIn("document.title = historyDocumentTitle();", history_source)

    def test_service_worker_caches_only_application_shell_not_user_data_or_api_streams(self) -> None:
        worker_path = Path("codex_image/webui/static/service-worker.js")
        self.assertTrue(worker_path.exists())
        source = worker_path.read_text(encoding="utf-8")

        self.assertIn('const CACHE_NAME = "ilab-gpt-conjure-shell-v52";', source)
        self.assertIn('"/"', source)
        self.assertIn('"/history"', source)
        self.assertIn('"/manifest.webmanifest"', source)
        self.assertIn('"/static/app.js"', source)
        self.assertIn('"/static/history.js"', source)
        self.assertIn('"/static/styles.css"', source)
        self.assertIn("request.mode === \"navigate\"", source)
        self.assertIn("caches.match(request).then", source)
        self.assertIn("catch(() => caches.match(request, { ignoreSearch: true }))", source)
        self.assertNotIn('"/api/', source)
        self.assertNotIn('"/events', source)
        self.assertNotIn('"/inputs', source)
        self.assertNotIn('"/outputs', source)

    def test_pwa_root_assets_are_served_from_webui_app(self) -> None:
        from codex_image.webui.app import create_app

        with tempfile.TemporaryDirectory() as tmp:
            app = create_app(output_root=Path(tmp), auth_checker=lambda: True, auto_start_queue=False)
            client = TestClient(app)

            manifest_response = client.get("/manifest.webmanifest")
            self.assertEqual(manifest_response.status_code, 200)
            self.assertEqual(manifest_response.headers["content-type"].split(";")[0], "application/manifest+json")
            self.assertEqual(manifest_response.json()["name"], "iLab CONJ Web")
            self.assertEqual(manifest_response.headers["cache-control"], "no-store")
            self.assertEqual(client.head("/manifest.webmanifest").status_code, 200)

            worker_response = client.get("/service-worker.js")
            self.assertEqual(worker_response.status_code, 200)
            self.assertEqual(worker_response.headers["content-type"].split(";")[0], "text/javascript")
            self.assertIn("Service-Worker-Allowed", worker_response.headers)
            self.assertEqual(worker_response.headers["Service-Worker-Allowed"], "/")
            self.assertEqual(worker_response.headers["cache-control"], "no-store")
            self.assertEqual(client.head("/service-worker.js").status_code, 200)

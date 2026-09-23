from __future__ import annotations

import mimetypes
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient


class WebUIStaticServingTests(unittest.TestCase):
    def setUp(self) -> None:
        from codex_image.webui.app import create_app

        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        app = create_app(
            output_root=root / "output",
            auth_settings_path=root / "auth-settings.json",
            webui_settings_path=root / "webui-settings.json",
            auth_checker=lambda: True,
            auto_start_queue=False,
        )
        self.client = TestClient(app)
        self.addCleanup(self.client.close)
        self.static_root = Path(__file__).resolve().parents[1] / "codex_image/webui/static"
        mimetypes.guess_type("icon.svg")  # Initialize the platform MIME table before patching it.

    def test_svg_assets_ignore_system_mime_types(self) -> None:
        assets = ("brand/model-marks/openai.svg", "brand/model-marks/gemini.svg", "brand/favicon.svg")
        for system_type in ("text/plain", "application/octet-stream", "image/svg+xml"):
            with patch.dict(mimetypes.types_map, {".svg": system_type}):
                self.assertEqual(mimetypes.guess_type("icon.svg")[0], system_type)
                for asset in assets:
                    expected = (self.static_root / asset).read_bytes()
                    for method in ("GET", "HEAD"):
                        with self.subTest(system_type=system_type, asset=asset, method=method):
                            response = self.client.request(method, f"/static/{asset}?v=mime-test")
                            self.assertEqual(response.status_code, 200)
                            self.assertEqual(response.headers["content-type"], "image/svg+xml")
                            self.assertEqual(response.headers["cache-control"], "no-store")
                            self.assertEqual(int(response.headers["content-length"]), len(expected))
                            self.assertEqual(response.content, expected if method == "GET" else b"")

    def test_svg_conditional_and_range_requests_keep_http_semantics(self) -> None:
        asset = "brand/model-marks/openai.svg"
        with patch.dict(mimetypes.types_map, {".svg": "text/plain"}):
            original = self.client.get(f"/static/{asset}")
            conditional = self.client.get(
                f"/static/{asset}", headers={"If-None-Match": original.headers["etag"]}
            )
            partial = self.client.get(f"/static/{asset}", headers={"Range": "bytes=0-31"})

        self.assertEqual(conditional.status_code, 304)
        self.assertEqual(conditional.content, b"")
        self.assertEqual(conditional.headers["cache-control"], "no-store")
        self.assertEqual(partial.status_code, 206)
        self.assertEqual(partial.headers["content-type"], "image/svg+xml")
        self.assertEqual(partial.headers["cache-control"], "no-store")
        self.assertEqual(partial.content, (self.static_root / asset).read_bytes()[:32])

    def test_non_svg_and_missing_assets_keep_their_response_types(self) -> None:
        with patch.dict(mimetypes.types_map, {".svg": "text/plain"}):
            png = self.client.get("/static/brand/pwa-icon-192.png")
            missing = self.client.get("/static/brand/model-marks/missing.svg")
            unsupported = self.client.post("/static/brand/model-marks/openai.svg")

        self.assertEqual(png.status_code, 200)
        self.assertEqual(png.headers["content-type"], "image/png")
        self.assertEqual(png.headers["cache-control"], "no-store")
        self.assertEqual(png.content, (self.static_root / "brand/pwa-icon-192.png").read_bytes())
        self.assertEqual(missing.status_code, 404)
        self.assertEqual(missing.headers["content-type"], "application/json")
        self.assertEqual(unsupported.status_code, 405)

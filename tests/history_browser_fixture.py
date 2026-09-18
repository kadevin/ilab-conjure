"""Isolated fixture for tests/frontend/history_page.browser.ts.

Run: python -m tests.history_browser_fixture
Open http://127.0.0.1:18792/qa?variant=current in the in-app browser.
Optionally pass --baseline-bundle /path/to/previous/history.js for comparison.
The service binds only loopback, uses synthetic tasks and removes its temporary data
on normal shutdown. It never reads the user's task directories or settings.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import io
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
from tempfile import TemporaryDirectory

from fastapi import Request
from fastapi.responses import FileResponse, HTMLResponse
from PIL import Image
import uvicorn

from codex_image.webui.app import create_app

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "codex_image/webui/static"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=18792)
    parser.add_argument("--baseline-bundle", type=Path)
    args = parser.parse_args()
    baseline = args.baseline_bundle.resolve() if args.baseline_bundle else None
    initial_directory = Path.cwd()
    with TemporaryDirectory(prefix="conjure-history-acceptance-") as temporary:
        work = Path(temporary)
        try:
            # Storage's legacy relative roots must also resolve inside the fixture.
            os.chdir(work)
            paths = {
                name: work / name
                for name in (
                    "input_root", "output_root", "gallery_root", "reference_asset_root",
                    "reference_file_root", "prompt_template_asset_root", "source_data_root",
                    "auth_settings_path", "api_settings_path", "network_egress_settings_path",
                    "color_settings_path", "prompt_snippets_path", "prompt_templates_path",
                    "webui_settings_path", "queue_path", "history_export_temp_root",
                    "history_backup_temp_root", "user_config_backup_temp_root",
                )
            }
            app = create_app(
                **paths, auth_checker=lambda: True, auto_start_queue=False,
                static_dir=STATIC,
            )
            storage = app.state.storage
            image = io.BytesIO()
            Image.new("RGB", (96, 64), (92, 108, 196)).save(image, format="PNG")
            for number in range(675):
                task_id = f"qa-history-{number:04d}"
                timestamp = (datetime(2026, 8, 1, tzinfo=timezone.utc) + timedelta(minutes=number)).isoformat()
                path = storage.output_file(storage.write_output(task_id, image.getvalue(), "png", index=1))
                storage.write_metadata(task_id, {
                    "task_id": task_id, "mode": "generate", "status": "completed",
                    "created_at": timestamp, "updated_at": timestamp,
                    "completed_at": timestamp, "terminal_at": timestamp,
                    "prompt": f"Synthetic QA history {number:04d}",
                    "params": {"size": "1024x1024", "quality": "high", "ratio": "1:1"},
                    "backend": "openai_images", "generated_count": 1, "total_count": 1,
                    "output_files": [path],
                    "outputs": [{"index": 1, "status": "completed", "file": path}],
                })
            subprocess.run([
                str(ROOT / "node_modules/.bin/esbuild"),
                str(ROOT / "tests/frontend/history_page.browser.ts"),
                "--bundle", "--format=iife", "--target=es2022",
                f"--outfile={work / 'qa.js'}", "--log-level=warning",
            ], check=True)
            if baseline:
                shutil.copyfile(baseline, work / "baseline.js")

            @app.get("/qa")
            def acceptance_page():
                return HTMLResponse(
                    '<!doctype html><html><body><h1>History acceptance</h1>'
                    '<pre id="results">Running</pre>'
                    '<iframe id="historyFrame" style="width:1440px;height:900px;border:0"></iframe>'
                    '<script src="/qa.js"></script></body></html>'
                )

            @app.get("/qa.js")
            def acceptance_script():
                return FileResponse(work / "qa.js", media_type="text/javascript")

            @app.get("/qa-baseline")
            def baseline_page():
                return HTMLResponse(re.sub(
                    r"/static/history.js\?v=history-\d+", "/qa-baseline.js",
                    (STATIC / "history.html").read_text(encoding="utf-8"),
                ))

            @app.get("/qa-baseline.js")
            def baseline_script():
                return FileResponse(work / "baseline.js", media_type="text/javascript")

            @app.post("/qa-results")
            async def acceptance_results(request: Request):
                report = await request.json()
                print(json.dumps(report, ensure_ascii=False), flush=True)
                return {"ok": True}

            @app.middleware("http")
            async def acceptance_frame(request: Request, call_next):
                response = await call_next(request)
                # Same-origin embedding only, exclusively in this synthetic fixture.
                if request.url.path in ("/history", "/qa-baseline"):
                    response.headers["x-frame-options"] = "SAMEORIGIN"
                    response.headers["content-security-policy"] = response.headers.get(
                        "content-security-policy", "",
                    ).replace("frame-ancestors 'none'", "frame-ancestors 'self'")
                return response

            print(f"History acceptance: http://127.0.0.1:{args.port}/qa?variant=current", flush=True)
            uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="warning")
        finally:
            os.chdir(initial_directory)


if __name__ == "__main__":
    main()

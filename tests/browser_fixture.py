"""Isolated host for the three real-browser frontend acceptance suites.

Run: python -m tests.browser_fixture
Open http://127.0.0.1:18792/qa in the in-app browser and choose a suite.
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

from fastapi import HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, Response
from PIL import Image
import uvicorn

from codex_image.webui.app import create_app

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "codex_image/webui/static"
BROWSER_SUITES = {
    "history": "history_page.browser",
    "image-mentions": "image_mentions.browser",
    "prompt-paste": "prompt_paste.browser",
}


def acceptance_html(filename: str) -> str:
    html = (STATIC / filename).read_text(encoding="utf-8")
    # Browser behavior suites must execute today's assets, not a previous PWA shell.
    html = re.sub(r'<script\b[^>]*\bsrc="/static/pwa\.js[^\"]*"[^>]*>\s*</script>', "", html)
    capture = """<script>
      (() => {
        const report = message => parent.postMessage({type: "qa-runtime-error", message}, location.origin);
        addEventListener("error", event => {
          const target = event.target;
          report(event.message || "Resource failed: " + (target.src || target.href || target.tagName));
        }, true);
        addEventListener("unhandledrejection", event => report(String(event.reason)));
        document.documentElement.dataset.qaErrorCapture = "ready";
      })();
    </script>"""
    return html.replace("<head>", "<head>" + capture, 1)


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
                *(str(ROOT / "tests/frontend" / f"{name}.ts") for name in BROWSER_SUITES.values()),
                str(ROOT / "tests/frontend/browser_harness.ts"),
                "--bundle", "--format=iife", "--target=es2022",
                f"--outdir={work}", "--log-level=warning",
            ], check=True)
            if baseline:
                shutil.copyfile(baseline, work / "baseline.js")

            unexpected_requests: list[str] = []

            @app.get("/qa")
            def suite_index():
                links = "".join(f'<li><a href="/qa/{name}">{name}</a></li>' for name in BROWSER_SUITES)
                return HTMLResponse(f"<!doctype html><html><body><h1>Browser acceptance</h1><ul>{links}</ul></body></html>")

            @app.get("/qa/{suite}")
            def acceptance_page(suite: str):
                if suite not in BROWSER_SUITES:
                    raise HTTPException(404)
                script = "history_page.browser" if suite == "history" else "browser_harness"
                return HTMLResponse(
                    f'<!doctype html><html><body><h1>{suite} acceptance</h1>'
                    '<pre id="results">Running</pre>'
                    '<iframe id="historyFrame" style="width:1440px;height:900px;border:0"></iframe>'
                    f'<script src="/qa-script/{script}.js"></script></body></html>'
                )

            @app.get("/qa-script/{name}.js")
            def acceptance_script(name: str):
                if name not in (*BROWSER_SUITES.values(), "browser_harness"):
                    raise HTTPException(404)
                return FileResponse(work / f"{name}.js", media_type="text/javascript")

            @app.get("/qa-app")
            def application_page():
                return HTMLResponse(acceptance_html("index.html"))

            @app.get("/qa-history")
            def history_page():
                return HTMLResponse(acceptance_html("history.html"))

            @app.get("/qa-unexpected-requests")
            def network_report():
                return {"requests": unexpected_requests}

            @app.get("/qa-baseline")
            def baseline_page():
                return HTMLResponse(re.sub(
                    r"/static/history.js\?v=history-\d+", "/qa-baseline.js",
                    acceptance_html("history.html"),
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
                if request.url.path.startswith("/unexpected-"):
                    unexpected_requests.append(request.url.path)
                    return Response(status_code=204)
                response = await call_next(request)
                # Same-origin embedding only, exclusively in this synthetic fixture.
                if request.url.path in ("/qa-history", "/qa-baseline", "/qa-app"):
                    response.headers["x-frame-options"] = "SAMEORIGIN"
                    response.headers["content-security-policy"] = response.headers.get(
                        "content-security-policy", "",
                    ).replace("frame-ancestors 'none'", "frame-ancestors 'self'")
                if request.url.path.startswith("/qa"):
                    response.headers["cache-control"] = "no-store"
                return response

            print(f"Browser acceptance: http://127.0.0.1:{args.port}/qa", flush=True)
            uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="warning")
        finally:
            os.chdir(initial_directory)


if __name__ == "__main__":
    main()

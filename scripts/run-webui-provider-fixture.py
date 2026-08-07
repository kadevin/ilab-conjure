#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import json
import sys
import tempfile
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import uvicorn
from fastapi import Request
from fastapi.responses import JSONResponse, Response

from codex_image.webui.app import create_app


PNG_B64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAIAAACQd1PeAAAADUlEQVR42mNk+M/wHwAEAQH/69ZkWQAAAABJRU5ErkJggg=="
)
PNG_BYTES = base64.b64decode(PNG_B64)
LONG_RELAY_NAME = "Fixture Multi-Model Relay — GPT Image 2 + Nano Banana Pro/2/Lite"


def _binding(
    binding_id: str,
    canonical_model_id: str,
    remote_model_id: str,
    protocol_profile: str,
    parameter_codec: str,
) -> dict[str, Any]:
    return {
        "id": binding_id,
        "canonical_model_id": canonical_model_id,
        "remote_model_id": remote_model_id,
        "protocol_profile": protocol_profile,
        "parameter_codec": parameter_codec,
        "operations": ["generate", "edit"],
    }


def fixture_settings(base_url: str) -> dict[str, Any]:
    openai_base = f"{base_url}/mock/openai/v1"
    gemini_base = f"{base_url}/mock/gemini/v1beta"
    multi_bindings = [
        _binding(
            "mega-gpt",
            "gpt-image-2",
            "relay/custom-gpt-image-2-with-a-very-long-model-name",
            "openai_images",
            "gpt_openai_images",
        ),
        *[
            _binding(
                f"mega-{model_id}",
                model_id,
                f"relay/custom-{model_id}-with-a-very-long-model-name",
                "openai_images",
                "gemini_openai_images",
            )
            for model_id in ("nano-banana-pro", "nano-banana-2", "nano-banana-2-lite")
        ],
    ]
    native_gemini_bindings = [
        _binding(
            f"google-{model_id}",
            model_id,
            f"fixture/{model_id}",
            "gemini_generate_content",
            "gemini_generate_content_image",
        )
        for model_id in ("nano-banana-pro", "nano-banana-2", "nano-banana-2-lite")
    ]
    openai_gemini_bindings = [
        _binding(
            f"gemini-openai-{model_id}",
            model_id,
            f"fixture-openai/{model_id}",
            "openai_images",
            "gemini_openai_images",
        )
        for model_id in ("nano-banana-pro", "nano-banana-2", "nano-banana-2-lite")
    ]
    providers = [
        {
            "id": "mega-relay",
            "name": LONG_RELAY_NAME,
            "base_url": openai_base,
            "api_key": "fixture-mega-key-not-valid",
            "concurrency": 3,
            "bindings": multi_bindings,
        },
        {
            "id": "google-native",
            "name": "Google generateContent Fixture",
            "base_url": gemini_base,
            "api_key": "fixture-google-key-not-valid",
            "concurrency": 2,
            "bindings": native_gemini_bindings,
        },
        {
            "id": "gemini-openai",
            "name": "Gemini OpenAI-Compatible Fixture",
            "base_url": openai_base,
            "api_key": "fixture-gemini-openai-key-not-valid",
            "concurrency": 2,
            "bindings": openai_gemini_bindings,
        },
        {
            "id": "gpt-only",
            "name": "GPT-Only Supplier (filter fixture)",
            "base_url": openai_base,
            "api_key": "fixture-gpt-only-key-not-valid",
            "concurrency": 1,
            "bindings": [
                _binding(
                    "gpt-only-binding",
                    "gpt-image-2",
                    "fixture/gpt-only",
                    "openai_images",
                    "gpt_openai_images",
                )
            ],
        },
    ]
    return {
        "schema_version": 2,
        "codex_mode": "images",
        "active_provider_id": "mega-relay",
        "default_provider_by_model": {
            model_id: "mega-relay"
            for model_id in (
                "gpt-image-2",
                "nano-banana-pro",
                "nano-banana-2",
                "nano-banana-2-lite",
            )
        },
        "providers": providers,
    }


def _snapshot(
    *,
    family_id: str,
    model_id: str,
    provider_id: str,
    provider_name: str,
    remote_model_id: str,
    protocol_profile: str,
    parameter_codec: str,
    requested_parameters: dict[str, Any],
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "family_id": family_id,
        "canonical_model_id": model_id,
        "model_manifest_version": 1,
        "provider_id": provider_id,
        "provider_name": provider_name,
        "provider_base_url": "http://fixture.invalid/v1",
        "provider_concurrency": 2,
        "binding_id": f"fixture-{model_id}",
        "remote_model_id": remote_model_id,
        "protocol_profile": protocol_profile,
        "parameter_codec": parameter_codec,
        "binding_operations": ["edit", "generate"],
        "requested_parameters": requested_parameters,
        "mapped_request": {
            "method": "POST",
            "path": "/fixture/redacted",
            "content_type": "application/json",
            "json_body": {"prompt": "<redacted prompt>"},
            "form_fields": {},
            "files": [],
            "repeat_count": 1,
        },
    }


def _seed_task(
    app,
    *,
    task_id: str,
    prompt: str,
    snapshot: dict[str, Any] | None,
    provider_id: str,
    provider_name: str,
    tool_usage: dict[str, Any] | None = None,
) -> None:
    storage = app.state.storage
    output_path = storage.write_output(task_id, PNG_BYTES, "png", index=1)
    output_file = storage.output_file(output_path)
    output_url = f"/outputs/{output_file}"
    metadata: dict[str, Any] = {
        "task_id": task_id,
        "created_at": "2026-07-15T08:00:00+00:00",
        "updated_at": "2026-07-15T08:00:01+00:00",
        "completed_at": "2026-07-15T08:00:01+00:00",
        "status": "completed",
        "mode": "generate",
        "prompt": prompt,
        "params": {"n": 1},
        "backend": snapshot.get("protocol_profile") if snapshot else "codex_images",
        "api_provider_id": provider_id,
        "api_provider_name": provider_name,
        "generated_count": 1,
        "failed_count": 0,
        "total_count": 1,
        "output_file": output_file,
        "output_url": output_url,
        "output_files": [output_file],
        "output_urls": [output_url],
        "outputs": [
            {
                "index": 1,
                "status": "completed",
                "file": output_file,
                "url": output_url,
                "format": "png",
                "size": "1x1",
                "tool_usage": tool_usage or {},
            }
        ],
    }
    if snapshot:
        metadata["generation_snapshot"] = snapshot
    if tool_usage:
        metadata["tool_usage"] = tool_usage
    storage.write_metadata(task_id, metadata)


def seed_fixture_tasks(app) -> None:
    grounding = {
        "provider_metadata": {
            "grounding": [
                {
                    "rendered_content": (
                        '<a href="https://www.google.com/search?q=fixture">Fixture search</a>'
                    ),
                    "sources": [
                        {
                            "page_uri": "https://example.com/fixture-rabbits",
                            "image_uri": "https://example.com/fixture-rabbit.png",
                            "title": "Fixture rabbit source",
                        }
                    ],
                }
            ]
        }
    }
    _seed_task(
        app,
        task_id="20260715080000-a1b2c3d4",
        prompt="Fixture Gemini history task",
        snapshot=_snapshot(
            family_id="gemini-image",
            model_id="nano-banana-2",
            provider_id="google-native",
            provider_name="Google generateContent Fixture (historical name)",
            remote_model_id="fixture/historical-nano-banana-2",
            protocol_profile="gemini_generate_content",
            parameter_codec="gemini_generate_content_image",
            requested_parameters={
                "canvas.aspect_ratio": "16:9",
                "canvas.resolution": "4K",
                "output.modalities": "TEXT + IMAGE",
                "gemini.safety_settings": {},
                "gemini.google_search": True,
                "gemini.google_image_search": True,
                "output.count": 1,
                "fixture.removed_parameter": "migration-demo",
            },
        ),
        provider_id="google-native",
        provider_name="Google generateContent Fixture (historical name)",
        tool_usage=grounding,
    )
    _seed_task(
        app,
        task_id="20260715075900-b2c3d4e5",
        prompt="Fixture GPT Image history task",
        snapshot=_snapshot(
            family_id="gpt-image",
            model_id="gpt-image-2",
            provider_id="mega-relay",
            provider_name=LONG_RELAY_NAME,
            remote_model_id="fixture/historical-gpt-image-2",
            protocol_profile="openai_images",
            parameter_codec="gpt_openai_images",
            requested_parameters={
                "canvas.aspect_ratio": "3:2",
                "canvas.resolution": "1536x1024",
                "output.quality": "high",
                "output.count": 1,
            },
        ),
        provider_id="mega-relay",
        provider_name=LONG_RELAY_NAME,
    )
    _seed_task(
        app,
        task_id="20260715075800-c3d4e5f6",
        prompt="Fixture legacy Codex task",
        snapshot=None,
        provider_id="codex",
        provider_name="Codex",
    )


def _safe_request_record(request: Request, payload: dict[str, Any], status: int) -> dict[str, Any]:
    return {
        "method": request.method,
        "path": request.url.path,
        "content_type": request.headers.get("content-type", "").split(";", 1)[0],
        "json_keys": sorted(str(key) for key in payload),
        "status": status,
    }


def build_fixture_app(root: Path, *, host: str, port: int, auto_start_queue: bool = True):
    browser_host = "127.0.0.1" if host in {"0.0.0.0", "::"} else host
    base_url = f"http://{browser_host}:{port}"
    root.mkdir(parents=True, exist_ok=True)
    (root / "api-settings.json").write_text(
        json.dumps(fixture_settings(base_url), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    (root / "auth-settings.json").write_text(
        json.dumps({"source": "codex"}, indent=2),
        encoding="utf-8",
    )
    (root / "webui-settings.json").write_text(
        json.dumps({"locale": "zh-CN"}, indent=2),
        encoding="utf-8",
    )
    app = create_app(
        input_root=root / "inputs",
        output_root=root / "outputs",
        gallery_root=root / "gallery",
        source_data_root=root / "source-data",
        auth_settings_path=root / "auth-settings.json",
        api_settings_path=root / "api-settings.json",
        network_egress_settings_path=root / "network-egress-settings.json",
        webui_settings_path=root / "webui-settings.json",
        queue_path=root / "source-data" / "fixture-queue.json",
        auth_checker=lambda: False,
        auto_start_queue=auto_start_queue,
        auto_retry=False,
    )
    app.state.fixture_request_records = []

    async def json_payload(request: Request) -> dict[str, Any]:
        try:
            payload = await request.json()
        except Exception:
            return {}
        return payload if isinstance(payload, dict) else {}

    def record(request: Request, payload: dict[str, Any], status: int) -> None:
        app.state.fixture_request_records.append(_safe_request_record(request, payload, status))

    @app.get("/fixture/requests")
    def fixture_requests() -> dict[str, Any]:
        return {"requests": list(app.state.fixture_request_records)}

    @app.get("/mock/assets/fixture.png")
    def fixture_asset() -> Response:
        return Response(PNG_BYTES, media_type="image/png")

    @app.post("/mock/openai/v1/images/generations")
    async def openai_generate(request: Request):
        payload = await json_payload(request)
        status = 400 if "[fixture:400]" in str(payload.get("prompt") or "") else 200
        record(request, payload, status)
        if status == 400:
            return JSONResponse({"error": {"message": "fixture invalid parameters"}}, status_code=400)
        count = max(1, min(10, int(payload.get("n") or 1)))
        if payload.get("response_format") == "url":
            data = [
                {"url": f"{base_url}/mock/assets/fixture.png", "mime_type": "image/png"}
                for _ in range(count)
            ]
        else:
            data = [
                {"b64_json": PNG_B64, "mime_type": "image/png", "revised_prompt": "fixture"}
                for _ in range(count)
            ]
        return {
            "model": f"{payload.get('model') or 'fixture-model'}-actual",
            "data": data,
            "usage": {"fixture_images": count},
        }

    @app.post("/mock/openai/v1/images/edits")
    async def openai_edit(request: Request):
        body = await request.body()
        payload = {"multipart_bytes": len(body)}
        record(request, payload, 200)
        return {
            "model": "fixture-edit-actual",
            "data": [{"b64_json": PNG_B64, "mime_type": "image/png"}],
            "usage": {"fixture_images": 1},
        }

    @app.post("/mock/gemini/v1beta/models/{model_path:path}")
    async def gemini_generate_content(model_path: str, request: Request):
        payload = await json_payload(request)
        status = 400 if "[fixture:400]" in json.dumps(payload, ensure_ascii=False) else 200
        record(request, payload, status)
        if status == 400:
            return JSONResponse({"error": {"message": "fixture invalid parameters"}}, status_code=400)
        count = max(1, min(4, int((payload.get("generationConfig") or {}).get("candidateCount") or 1)))
        candidates = []
        for index in range(count):
            candidates.append(
                {
                    "content": {
                        "parts": [
                            {
                                "thought": True,
                                "inlineData": {"mimeType": "image/png", "data": PNG_B64},
                            },
                            {"text": f"Fixture Gemini text {index + 1}"},
                            {"inlineData": {"mimeType": "image/png", "data": PNG_B64}},
                        ]
                    },
                    "groundingMetadata": {
                        "searchEntryPoint": {
                            "renderedContent": (
                                '<a href="https://www.google.com/search?q=fixture">Fixture search</a>'
                            )
                        },
                        "groundingChunks": [
                            {
                                "image": {
                                    "uri": "https://example.com/fixture-rabbits",
                                    "imageUri": "https://example.com/fixture-rabbit.png",
                                    "title": "Fixture rabbit source",
                                }
                            }
                        ],
                    },
                }
            )
        return {
            "candidates": candidates,
            "usageMetadata": {"totalTokenCount": 1},
            "modelVersion": model_path.removesuffix(":generateContent"),
        }

    seed_fixture_tasks(app)
    return app, base_url


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run an isolated multi-provider WebUI fixture.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=8787, type=int)
    parser.add_argument(
        "--check",
        action="store_true",
        help="Build the fixture, verify its catalog, then exit without listening.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not 1 <= args.port <= 65535:
        raise SystemExit("--port must be between 1 and 65535")
    with tempfile.TemporaryDirectory(prefix="imagegen-provider-fixture-") as temporary:
        app, base_url = build_fixture_app(
            Path(temporary),
            host=args.host,
            port=args.port,
            auto_start_queue=not args.check,
        )
        print(f"Fixture WebUI: {base_url}", flush=True)
        if args.check:
            from fastapi.testclient import TestClient

            with TestClient(app) as client:
                response = client.get("/api/generation-catalog")
                if response.status_code != 200:
                    raise SystemExit("fixture catalog check failed")
                print(
                    f"Fixture catalog: {len(response.json().get('providers') or [])} providers",
                    flush=True,
                )
            return 0
        try:
            uvicorn.run(app, host=args.host, port=args.port, access_log=False)
        finally:
            print("Fixture data cleaned up.", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

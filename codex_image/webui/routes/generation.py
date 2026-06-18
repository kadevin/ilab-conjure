from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, Form, HTTPException, UploadFile

from codex_image.client import DEFAULT_MAIN_MODEL, image_model_supports_input_fidelity
from codex_image.webui.context import WebUIContext
from codex_image.webui.executor import (
    _file_to_data_url,
    _instructions_for_transport,
    _normalize_compression,
    _normalize_prompt_fidelity,
    _prompt_for_transport,
    _resolve_gallery_refs,
    _resolve_reference_assets,
)
from codex_image.webui.prompt_ratio import append_ratio_prompt_instruction
from codex_image.webui.storage import utc_now
from codex_image.webui.task_metadata import _dedupe_preserve_order, _params, _with_file_urls, _write_queued_metadata

DEFAULT_PROMPT_FIDELITY = "strict"


def register_generation_routes(app: FastAPI, ctx: WebUIContext) -> None:
    h = ctx.route_helpers

    @app.post("/api/generate")
    async def generate(
        prompt: str = Form(...),
        main_model: str = Form(DEFAULT_MAIN_MODEL),
        model: str = Form("gpt-image-2"),
        size: str = Form("auto"),
        resolution: str | None = Form(None),
        ratio: str | None = Form(None),
        orientation: str | None = Form(None),
        quality: str = Form("low"),
        background: str | None = Form(None),
        output_format: str = Form("png"),
        moderation: str | None = Form(None),
        output_compression: str | None = Form(None),
        n: int = Form(1, ge=1, le=4),
        web_search: bool = Form(False),
        codex_mode: str | None = Form(None),
        api_mode: str | None = Form(None),
        api_provider_id: str | None = Form(None),
        prompt_for_model: str | None = Form(None),
        prompt_fidelity: str = Form(DEFAULT_PROMPT_FIDELITY),
        gallery_image_ids: list[str] | None = Form(None),
        reference_asset_ids: list[str] | None = Form(None),
        reference_images: list[UploadFile] | None = File(None),
    ) -> dict[str, Any]:
        if not ctx.auth_checker():
            raise HTTPException(status_code=401, detail="Codex auth is not available")

        gallery_refs, gallery_data_urls = _resolve_gallery_refs(ctx.gallery_storage, gallery_image_ids or [])
        uploaded_assets = await h["save_reference_assets"](reference_images or [])
        selected_assets, _ = _resolve_reference_assets(ctx.reference_asset_storage, reference_asset_ids or [])
        reference_assets = h["dedupe_reference_assets"](uploaded_assets + selected_assets)
        task = ctx.storage.create_task("generate")
        created_at = utc_now()
        input_files: list[Path] = []
        reference_data_urls = [
            _file_to_data_url(ctx.reference_asset_storage.image_path(str(item["id"])), mime_type=str(item.get("mime_type") or ""))
            for item in reference_assets
        ]
        all_reference_data_urls = reference_data_urls + gallery_data_urls
        compression = _normalize_compression(output_format, output_compression)
        fidelity = _normalize_prompt_fidelity(prompt_fidelity)
        model_prompt = append_ratio_prompt_instruction(h["model_prompt_for_fidelity"](prompt, prompt_for_model, fidelity), ratio)
        prompt_constraints, guard_instructions = h["prompt_guard_context"](prompt, fidelity)
        auth_source = ctx.auth_settings.read_source() if not h["client_factory_overridden"] else "codex"
        effective_api_provider_id = h["request_api_provider_id"](auth_source, api_provider_id)
        effective_api_provider_name = h["request_api_provider_name"](auth_source, effective_api_provider_id)
        effective_api_mode = h["request_api_mode"](auth_source, api_mode, effective_api_provider_id)
        effective_codex_mode = h["request_codex_mode"](auth_source, codex_mode)
        effective_api_images_concurrency = h["request_api_images_concurrency"](auth_source, effective_api_provider_id)
        requested_backend = h["backend_for_submit"](auth_source, effective_api_mode, effective_codex_mode)
        transport_mode = effective_api_mode or effective_codex_mode
        web_search_enabled = bool(web_search) and requested_backend.endswith("_responses")
        request_model_prompt = _prompt_for_transport(
            model_prompt,
            auth_source=auth_source,
            api_mode=transport_mode,
            prompt_fidelity=fidelity,
            instructions=guard_instructions,
        )
        request_instructions = _instructions_for_transport(
            auth_source=auth_source,
            api_mode=transport_mode,
            instructions=guard_instructions,
        )

        request_kwargs: dict[str, Any] = dict(
            auth_source=auth_source,
            api_mode=effective_api_mode,
            codex_mode=effective_codex_mode,
            prompt=request_model_prompt,
            main_model=main_model,
            model=model,
            input_images=all_reference_data_urls,
            size=size,
            quality=quality,
            background=background,
            output_format=output_format,
            moderation=moderation,
            output_compression=compression,
        )
        if request_instructions:
            request_kwargs["instructions"] = request_instructions
        if web_search_enabled:
            request_kwargs["web_search"] = True
        request_payload = h["build_image_request_payload"](**request_kwargs)
        stored_request_payload = h["slim_request_payload"](
            request_payload,
            input_files=[path.name for path in input_files],
            gallery_refs=gallery_refs,
            reference_assets=reference_assets,
        )
        stored_request_payload["webui_requested_backend"] = requested_backend
        if effective_api_provider_id is not None:
            stored_request_payload["webui_api_provider_id"] = effective_api_provider_id
        if effective_api_provider_name:
            stored_request_payload["webui_api_provider_name"] = effective_api_provider_name
        if auth_source == "api" and effective_api_mode == "images":
            stored_request_payload["webui_api_images_concurrency"] = effective_api_images_concurrency
        ctx.storage.write_request(task.task_id, stored_request_payload)
        params = _params(main_model, model, size, quality, background, output_format, moderation, compression, n)
        if resolution:
            params["resolution"] = resolution
        if ratio:
            params["ratio"] = ratio
        if orientation:
            params["orientation"] = orientation
        params["prompt_fidelity"] = fidelity
        if web_search_enabled:
            params["web_search"] = True
        if effective_codex_mode is not None:
            params["codex_mode"] = effective_codex_mode
        if effective_api_mode is not None:
            params["api_mode"] = effective_api_mode
        if effective_api_provider_id is not None:
            params["api_provider_id"] = effective_api_provider_id
        if effective_api_provider_name:
            params["api_provider_name"] = effective_api_provider_name
        if auth_source == "api" and effective_api_mode == "images":
            params["api_images_concurrency"] = effective_api_images_concurrency
        metadata = _write_queued_metadata(
            ctx.storage,
            task.task_id,
            created_at=created_at,
            mode="generate",
            prompt=prompt,
            prompt_for_model=model_prompt,
            params=params,
            input_files=[path.name for path in input_files],
            mask_file=None,
            gallery_refs=gallery_refs,
            reference_assets=reference_assets,
            prompt_constraints=prompt_constraints,
            requested_backend=requested_backend,
            max_attempts=ctx.queue_manager.max_attempts if ctx.queue_manager is not None else 1,
        )
        ctx.queue_storage.enqueue(task.task_id)
        h["ensure_queue_worker_running"]()
        return {
            "task": _with_file_urls(metadata, ctx.active_task_ids, ctx.gallery_storage, ctx.reference_asset_storage),
            "request": stored_request_payload,
        }

    @app.post("/api/edit")
    async def edit(
        prompt: str = Form(...),
        main_model: str = Form(DEFAULT_MAIN_MODEL),
        model: str = Form("gpt-image-2"),
        size: str = Form("auto"),
        resolution: str | None = Form(None),
        ratio: str | None = Form(None),
        orientation: str | None = Form(None),
        quality: str = Form("low"),
        background: str | None = Form(None),
        output_format: str = Form("png"),
        input_fidelity: str | None = Form(None),
        moderation: str | None = Form(None),
        output_compression: str | None = Form(None),
        n: int = Form(1, ge=1, le=4),
        web_search: bool = Form(False),
        codex_mode: str | None = Form(None),
        api_mode: str | None = Form(None),
        api_provider_id: str | None = Form(None),
        prompt_for_model: str | None = Form(None),
        prompt_fidelity: str = Form(DEFAULT_PROMPT_FIDELITY),
        gallery_image_ids: list[str] | None = Form(None),
        reference_asset_ids: list[str] | None = Form(None),
        images: list[UploadFile] | None = File(None),
        mask: UploadFile | None = File(None),
    ) -> dict[str, Any]:
        if not ctx.auth_checker():
            raise HTTPException(status_code=401, detail="Codex auth is not available")

        if not images and not _dedupe_preserve_order(gallery_image_ids or []) and not _dedupe_preserve_order(reference_asset_ids or []):
            raise HTTPException(status_code=400, detail="At least one image is required")
        gallery_refs, gallery_data_urls = _resolve_gallery_refs(ctx.gallery_storage, gallery_image_ids or [])
        uploaded_assets = await h["save_reference_assets"](images or [])
        selected_assets, _ = _resolve_reference_assets(ctx.reference_asset_storage, reference_asset_ids or [])
        reference_assets = h["dedupe_reference_assets"](uploaded_assets + selected_assets)
        task = ctx.storage.create_task("edit")
        created_at = utc_now()
        input_files: list[Path] = []
        if not reference_assets and not gallery_data_urls:
            raise HTTPException(status_code=400, detail="At least one image is required")
        mask_files = await h["save_uploads"](task.task_id, [mask] if mask is not None else [], kind="mask")
        image_data_urls = [
            _file_to_data_url(ctx.reference_asset_storage.image_path(str(item["id"])), mime_type=str(item.get("mime_type") or ""))
            for item in reference_assets
        ]
        all_image_data_urls = image_data_urls + gallery_data_urls
        mask_data_url = _file_to_data_url(mask_files[0]) if mask_files else None
        compression = _normalize_compression(output_format, output_compression)
        fidelity = _normalize_prompt_fidelity(prompt_fidelity)
        model_prompt = append_ratio_prompt_instruction(h["model_prompt_for_fidelity"](prompt, prompt_for_model, fidelity), ratio)
        prompt_constraints, guard_instructions = h["prompt_guard_context"](prompt, fidelity)
        effective_input_fidelity = input_fidelity if image_model_supports_input_fidelity(model) else None
        auth_source = ctx.auth_settings.read_source() if not h["client_factory_overridden"] else "codex"
        effective_api_provider_id = h["request_api_provider_id"](auth_source, api_provider_id)
        effective_api_provider_name = h["request_api_provider_name"](auth_source, effective_api_provider_id)
        effective_api_mode = h["request_api_mode"](auth_source, api_mode, effective_api_provider_id)
        effective_codex_mode = h["request_codex_mode"](auth_source, codex_mode)
        effective_api_images_concurrency = h["request_api_images_concurrency"](auth_source, effective_api_provider_id)
        requested_backend = h["backend_for_submit"](auth_source, effective_api_mode, effective_codex_mode)
        transport_mode = effective_api_mode or effective_codex_mode
        web_search_enabled = bool(web_search) and requested_backend.endswith("_responses")
        request_model_prompt = _prompt_for_transport(
            model_prompt,
            auth_source=auth_source,
            api_mode=transport_mode,
            prompt_fidelity=fidelity,
            instructions=guard_instructions,
        )
        request_instructions = _instructions_for_transport(
            auth_source=auth_source,
            api_mode=transport_mode,
            instructions=guard_instructions,
        )

        request_kwargs = dict(
            auth_source=auth_source,
            api_mode=effective_api_mode,
            codex_mode=effective_codex_mode,
            prompt=request_model_prompt,
            action="edit",
            main_model=main_model,
            model=model,
            input_images=all_image_data_urls,
            mask_image=mask_data_url,
            size=size,
            quality=quality,
            background=background,
            output_format=output_format,
            input_fidelity=effective_input_fidelity,
            moderation=moderation,
            output_compression=compression,
        )
        if request_instructions:
            request_kwargs["instructions"] = request_instructions
        if web_search_enabled:
            request_kwargs["web_search"] = True
        request_payload = h["build_image_request_payload"](**request_kwargs)
        image_input_names = [path.name for path in input_files]
        mask_file = mask_files[0].name if mask_files else None
        stored_request_payload = h["slim_request_payload"](
            request_payload,
            input_files=image_input_names,
            gallery_refs=gallery_refs,
            reference_assets=reference_assets,
            mask_file=mask_file,
        )
        stored_request_payload["webui_requested_backend"] = requested_backend
        if effective_api_provider_id is not None:
            stored_request_payload["webui_api_provider_id"] = effective_api_provider_id
        if effective_api_provider_name:
            stored_request_payload["webui_api_provider_name"] = effective_api_provider_name
        if auth_source == "api" and effective_api_mode == "images":
            stored_request_payload["webui_api_images_concurrency"] = effective_api_images_concurrency
        ctx.storage.write_request(task.task_id, stored_request_payload)
        params = _params(main_model, model, size, quality, background, output_format, moderation, compression, n)
        if resolution:
            params["resolution"] = resolution
        if ratio:
            params["ratio"] = ratio
        if orientation:
            params["orientation"] = orientation
        params["prompt_fidelity"] = fidelity
        if effective_input_fidelity:
            params["input_fidelity"] = effective_input_fidelity
        if web_search_enabled:
            params["web_search"] = True
        if effective_codex_mode is not None:
            params["codex_mode"] = effective_codex_mode
        if effective_api_mode is not None:
            params["api_mode"] = effective_api_mode
        if effective_api_provider_id is not None:
            params["api_provider_id"] = effective_api_provider_id
        if effective_api_provider_name:
            params["api_provider_name"] = effective_api_provider_name
        if auth_source == "api" and effective_api_mode == "images":
            params["api_images_concurrency"] = effective_api_images_concurrency
        metadata = _write_queued_metadata(
            ctx.storage,
            task.task_id,
            created_at=created_at,
            mode="edit",
            prompt=prompt,
            prompt_for_model=model_prompt,
            params=params,
            input_files=image_input_names,
            mask_file=mask_file,
            gallery_refs=gallery_refs,
            reference_assets=reference_assets,
            prompt_constraints=prompt_constraints,
            requested_backend=requested_backend,
            max_attempts=ctx.queue_manager.max_attempts if ctx.queue_manager is not None else 1,
        )
        ctx.queue_storage.enqueue(task.task_id)
        h["ensure_queue_worker_running"]()
        return {
            "task": _with_file_urls(metadata, ctx.active_task_ids, ctx.gallery_storage, ctx.reference_asset_storage),
            "request": stored_request_payload,
        }

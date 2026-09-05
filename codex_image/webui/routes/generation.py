from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile

from codex_image.client import DEFAULT_MAIN_MODEL, image_model_supports_input_fidelity
from codex_image.generation.snapshot import generation_snapshot
from codex_image.generation.service import redacted_protocol_request
from codex_image.client_types import ResponsesInputFile
from codex_image.generation.types import ImageInput
from codex_image.webui.context import WebUIContext
from codex_image.webui.generation_request import (
    generation_command_from_form,
    parse_parameters_json,
    preview_generation_command,
)
from codex_image.webui.image_uploads import (
    InvalidRasterImage,
    ValidatedRasterImage,
    read_validated_raster_uploads,
)
from codex_image.webui.resource_limits import (
    MAX_TASK_IMAGE_BYTES,
    TaskImageLimitError,
    TaskImageResource,
    validate_task_image_total,
)
from codex_image.webui.executor import (
    _file_to_data_url,
    _instructions_for_transport,
    _normalize_compression,
    _normalize_prompt_fidelity,
    _prompt_for_transport,
    _resolve_gallery_refs,
    _resolve_reference_assets,
)
from codex_image.webui.executor_inputs import (
    _bytes_to_data_url,
    _reference_file_to_responses_input,
    _resolve_reference_files,
)
from codex_image.webui.prompt_ratio import (
    append_ratio_prompt_instruction,
    normalize_prompt_ratio,
    orientation_from_ratio,
    ratio_from_size,
)
from codex_image.webui.reference_file_capabilities import (
    effective_reference_file_main_model,
    reference_file_capability_key_for_backend,
)
from codex_image.webui.reference_files import (
    ReferenceFileStorage,
    ValidatedReferenceFile,
    dedupe_reference_file_records,
    read_reference_file_uploads,
    reference_file_task_record,
    resolve_reference_file_ids,
    validate_reference_file_total,
)
from codex_image.webui.storage import utc_now
from codex_image.webui.task_metadata import _dedupe_preserve_order, _params, _with_file_urls, _write_queued_metadata

DEFAULT_PROMPT_FIDELITY = "off"

REFERENCE_FILE_ERROR_MESSAGES = {
    "reference_file_empty": "Reference files cannot be empty.",
    "reference_file_type_unsupported": "This reference file type is not supported.",
    "reference_file_type_mismatch": "The reference file type does not match its filename.",
    "reference_file_invalid": "The reference file is invalid.",
    "reference_file_too_large": "The reference file is too large.",
    "reference_files_total_too_large": "The combined reference files are too large.",
}
REFERENCE_FILE_MISSING_DETAIL = {
    "code": "reference_file_missing",
    "message": "A referenced file is no longer available.",
}
PROVIDER_REFERENCE_FILES_UNSUPPORTED_DETAIL = {
    "code": "provider_reference_files_unsupported",
    "message": "This provider does not support reference files for the selected Responses model.",
}
TASK_IMAGES_TOTAL_TOO_LARGE_DETAIL = {
    "code": "task_images_total_too_large",
    "message": "The combined task images are too large.",
}

_CODEX_BINDING_MODES = {
    "codex-gpt-image-2-images": "images",
    "codex-gpt-image-2-responses": "responses",
}
_CODEX_GPT_BACKENDS = frozenset({"codex_images", "codex_responses"})


@dataclass(frozen=True)
class PreparedReferenceFiles:
    uploads: tuple[ValidatedReferenceFile, ...]
    selected_asset_ids: tuple[str, ...]
    records: tuple[dict[str, Any], ...]
    response_inputs: tuple[ResponsesInputFile, ...]


@dataclass(frozen=True)
class PreparedGenerationSubmission:
    plan: Any
    request_payload: dict[str, Any]
    model_prompt: str
    prompt_constraints: Any
    params: dict[str, Any]
    prompt_locale: str


def _request_auth_source(ctx: WebUIContext, provider_id: str | None) -> str:
    explicit = str(provider_id or "").strip()
    if explicit:
        return "codex" if explicit == "codex" else "api"
    if ctx.route_helpers["client_factory_overridden"]:
        return "codex"
    return ctx.auth_settings.read_source()


def _codex_mode_for_binding(
    provider_id: str | None,
    binding_id: str | None,
    fallback: str | None,
) -> str | None:
    if str(provider_id or "").strip() != "codex":
        return fallback
    return _CODEX_BINDING_MODES.get(str(binding_id or "").strip(), fallback)


def _api_binding_appends_aspect_ratio_prompt(
    ctx: WebUIContext,
    *,
    provider_id: str | None,
    binding_id: str | None,
    canonical_model_id: str | None,
    operation: str,
) -> bool:
    selected_provider_id = str(provider_id or "").strip()
    selected_binding_id = str(binding_id or "").strip()
    selected_model_id = str(canonical_model_id or "").strip()
    for connection in ctx.api_settings.read_connections():
        if connection.id != selected_provider_id:
            continue
        candidates = [
            binding
            for binding in connection.bindings
            if (
                (selected_binding_id and binding.id == selected_binding_id)
                or (
                    not selected_binding_id
                    and binding.canonical_model_id == selected_model_id
                    and operation in binding.operations
                )
            )
        ]
        return len(candidates) == 1 and candidates[0].append_aspect_ratio_prompt
    return False


def _generation_request_error(exc: ValueError) -> HTTPException:
    message = str(exc)
    if "does not support model" in message:
        code = "provider_model_binding_missing"
        safe_message = "The selected provider does not support this model."
    elif "does not support operation" in message:
        code = "operation_unsupported"
        safe_message = "The selected provider does not support this operation."
    elif "Unknown provider" in message:
        code = "provider_not_found"
        safe_message = "The selected provider is not configured."
    elif "Unknown image model" in message:
        code = "model_not_found"
        safe_message = "The selected image model is not available."
    else:
        code = "generation_request_invalid"
        safe_message = "The generation request is invalid."
    return HTTPException(status_code=400, detail={"code": code, "message": safe_message})


def _preview_form_generation(
    ctx: WebUIContext,
    *,
    operation: str,
    canonical_model_id: str | None,
    provider_id: str | None,
    binding_id: str | None,
    parameters_json: str | None,
    prompt: str,
    model_prompt: str,
    main_model: str,
    instructions: str | None,
    image_data_urls: list[str],
    mask_data_url: str | None,
    reference_file_inputs: list[ResponsesInputFile],
    legacy_fields: dict[str, Any],
    explicit_form_fields: frozenset[str],
    codex_mode: str | None,
):
    try:
        command = generation_command_from_form(
            operation=operation,  # type: ignore[arg-type]
            canonical_model_id=canonical_model_id,
            provider_id=provider_id,
            binding_id=binding_id,
            parameters_json=parameters_json,
            prompt=model_prompt,
            image_inputs=tuple(ImageInput(item) for item in image_data_urls),
            reference_files=tuple(reference_file_inputs),
            mask_image=mask_data_url,
            main_model=main_model,
            instructions=instructions,
            legacy_fields=legacy_fields,
            explicit_form_fields=explicit_form_fields,
        )
        return preview_generation_command(
            command,
            codex_mode=str(codex_mode or "images"),
            provider_connections=ctx.api_settings.read_connections(),
        )
    except ValueError as exc:
        raise _generation_request_error(exc) from exc


def _enqueue_generation(
    ctx: WebUIContext,
    *,
    task_id: str,
    metadata: dict[str, Any],
    plan: Any,
    auth_source: str,
) -> None:
    metadata["generation_snapshot"] = generation_snapshot(plan)
    ctx.storage.write_metadata(task_id, metadata)
    ctx.queue_storage.enqueue(task_id)
    if ctx.queue_manager is not None:
        channels = ctx.route_helpers["queue_channels_for_source"](auth_source)
        ctx.queue_manager.channels = channels
        ctx.queue_manager.max_attempts = ctx.route_helpers["queue_max_attempts_for_channels"](channels)
    ctx.route_helpers["wake_queue_worker"]()


def _prepare_generation_submission(
    ctx: WebUIContext,
    *,
    operation: str,
    prompt: str,
    prompt_for_model: str | None,
    ui_language: str,
    prompt_fidelity: str,
    main_model: str,
    model: str,
    size: str,
    resolution: str | None,
    ratio: str | None,
    orientation: str | None,
    quality: str,
    background: str | None,
    output_format: str,
    input_fidelity: str | None,
    moderation: str | None,
    output_compression: str | None,
    n: int,
    web_search: bool,
    auth_source: str,
    effective_api_mode: str | None,
    effective_codex_mode: str | None,
    effective_api_provider_id: str | None,
    effective_api_provider_name: str | None,
    effective_api_images_concurrency: int,
    requested_backend: str,
    canonical_model_id: str | None,
    provider_id: str | None,
    binding_id: str | None,
    parameters_json: str | None,
    explicit_form_fields: frozenset[str],
    image_data_urls: list[str],
    mask_data_url: str | None,
    reference_file_inputs: list[ResponsesInputFile],
) -> PreparedGenerationSubmission:
    h = ctx.route_helpers
    compression = _normalize_compression(output_format, output_compression)
    uses_gpt_prompt_processing = canonical_model_id in {None, "gpt-image-2"}
    effective_main_model = main_model if uses_gpt_prompt_processing else ""
    fidelity = _normalize_prompt_fidelity(prompt_fidelity) if uses_gpt_prompt_processing else "off"
    effective_size = size
    effective_ratio = ratio
    effective_orientation = orientation
    canonical_parameters: dict[str, Any] | None = None
    if parameters_json is not None:
        try:
            canonical_parameters = parse_parameters_json(parameters_json)
        except ValueError as exc:
            raise _generation_request_error(exc) from exc
    if (
        auth_source == "codex"
        and canonical_model_id == "gpt-image-2"
        and requested_backend in _CODEX_GPT_BACKENDS
        and canonical_parameters is not None
    ):
        canonical_size = str(canonical_parameters.get("canvas.size") or "").strip()
        if canonical_size:
            effective_size = canonical_size
        if not effective_ratio:
            effective_ratio = ratio_from_size(effective_size) or None
        if not effective_orientation:
            effective_orientation = orientation_from_ratio(effective_ratio) or None
    base_model_prompt = h["model_prompt_for_fidelity"](prompt, prompt_for_model, fidelity)
    if fidelity == "original":
        model_prompt = base_model_prompt
    elif auth_source == "api" and canonical_model_id:
        model_prompt = base_model_prompt
        if canonical_parameters is not None and _api_binding_appends_aspect_ratio_prompt(
            ctx,
            provider_id=effective_api_provider_id,
            binding_id=binding_id,
            canonical_model_id=canonical_model_id,
            operation=operation,
        ):
            prompt_ratio = normalize_prompt_ratio(
                canonical_parameters.get("canvas.aspect_ratio")
            ) or ratio_from_size(canonical_parameters.get("canvas.size"))
            model_prompt = append_ratio_prompt_instruction(
                model_prompt,
                prompt_ratio,
                locale=ui_language,
            )
    else:
        model_prompt = append_ratio_prompt_instruction(
            base_model_prompt,
            effective_ratio,
            locale=ui_language,
        )
    prompt_constraints, guard_instructions = h["prompt_guard_context"](
        prompt,
        fidelity,
        ui_language,
    )
    transport_mode = effective_api_mode or effective_codex_mode
    web_search_enabled = bool(web_search) and requested_backend.endswith("_responses")
    request_model_prompt = _prompt_for_transport(
        model_prompt,
        auth_source=auth_source,
        api_mode=transport_mode,
        prompt_fidelity=fidelity,
        instructions=guard_instructions,
        locale=ui_language,
    )
    request_instructions = _instructions_for_transport(
        auth_source=auth_source,
        api_mode=transport_mode,
        instructions=guard_instructions,
    )
    resolved_provider_id = effective_api_provider_id if auth_source == "api" else "codex"
    plan = _preview_form_generation(
        ctx,
        operation=operation,
        canonical_model_id=canonical_model_id,
        provider_id=provider_id,
        binding_id=binding_id,
        parameters_json=parameters_json,
        prompt=prompt,
        model_prompt=request_model_prompt,
        main_model=effective_main_model,
        instructions=request_instructions,
        image_data_urls=image_data_urls,
        mask_data_url=mask_data_url,
        reference_file_inputs=reference_file_inputs,
        legacy_fields={
            "model": model,
            "resolved_provider_id": resolved_provider_id,
            "size": effective_size,
            "quality": quality,
            "background": background,
            "output_format": output_format,
            "moderation": moderation,
            "output_compression": compression,
            "input_fidelity": input_fidelity,
            "web_search": web_search_enabled,
            "n": n,
        },
        explicit_form_fields=explicit_form_fields,
        codex_mode=effective_codex_mode,
    )
    effective_n = int(plan.command.parameters.get("output.count") or n)
    request_kwargs: dict[str, Any] = {
        "auth_source": auth_source,
        "api_mode": effective_api_mode,
        "codex_mode": effective_codex_mode,
        "prompt": request_model_prompt,
        "main_model": effective_main_model,
        "model": model,
        "input_images": image_data_urls,
        "size": effective_size,
        "quality": quality,
        "background": background,
        "output_format": output_format,
        "moderation": moderation,
        "output_compression": compression,
    }
    if operation == "edit":
        request_kwargs.update(
            action="edit",
            mask_image=mask_data_url,
            input_fidelity=input_fidelity,
        )
    if request_instructions:
        request_kwargs["instructions"] = request_instructions
    if web_search_enabled:
        request_kwargs["web_search"] = True
    if canonical_model_id is not None:
        protocol_preview = redacted_protocol_request(plan)
        request_payload = dict(protocol_preview.json_body or protocol_preview.form_fields)
    else:
        request_payload = h["build_image_request_payload"](**request_kwargs)
    params = _params(
        effective_main_model, model, effective_size, quality, background, output_format,
        moderation, compression, effective_n,
    )
    if not uses_gpt_prompt_processing:
        params.pop("main_model", None)
    for key, value in (
        ("resolution", resolution),
        ("ratio", effective_ratio),
        ("orientation", effective_orientation),
    ):
        if value:
            params[key] = value
    if uses_gpt_prompt_processing:
        params["prompt_fidelity"] = fidelity
    if input_fidelity:
        params["input_fidelity"] = input_fidelity
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
    if auth_source == "api":
        params["api_images_concurrency"] = effective_api_images_concurrency
    return PreparedGenerationSubmission(
        plan=plan,
        request_payload=request_payload,
        model_prompt=model_prompt,
        prompt_constraints=prompt_constraints,
        params=params,
        prompt_locale=str(ui_language or "zh-CN"),
    )


def _persist_generation_submission(
    ctx: WebUIContext,
    *,
    prepared: PreparedGenerationSubmission,
    operation: str,
    task_id: str,
    created_at: str,
    prompt: str,
    requested_backend: str,
    auth_source: str,
    effective_api_provider_id: str | None,
    effective_api_provider_name: str | None,
    effective_api_images_concurrency: int,
    input_files: list[Path],
    mask_file: str | None,
    gallery_refs: list[dict[str, Any]],
    reference_assets: list[dict[str, Any]],
    file_references: list[dict[str, Any]],
) -> dict[str, Any]:
    h = ctx.route_helpers
    stored_request_payload = h["slim_request_payload"](
        prepared.request_payload,
        input_files=[path.name for path in input_files],
        gallery_refs=gallery_refs,
        reference_assets=reference_assets,
        reference_files=file_references,
        mask_file=mask_file,
    )
    stored_request_payload["webui_requested_backend"] = requested_backend
    if effective_api_provider_id is not None:
        stored_request_payload["webui_api_provider_id"] = effective_api_provider_id
    if effective_api_provider_name:
        stored_request_payload["webui_api_provider_name"] = effective_api_provider_name
    if auth_source == "api":
        stored_request_payload["webui_api_images_concurrency"] = (
            effective_api_images_concurrency
        )
    ctx.storage.write_request(task_id, stored_request_payload)

    metadata = _write_queued_metadata(
        ctx.storage,
        task_id,
        created_at=created_at,
        mode=operation,
        prompt=prompt,
        prompt_for_model=prepared.model_prompt,
        execution_model_prompt=prepared.model_prompt,
        execution_prompt=str(prepared.plan.command.prompt),
        execution_instructions=prepared.plan.command.instructions,
        prompt_locale=prepared.prompt_locale,
        params=prepared.params,
        input_files=[path.name for path in input_files],
        mask_file=mask_file,
        gallery_refs=gallery_refs,
        reference_assets=reference_assets,
        reference_files=file_references,
        prompt_constraints=prepared.prompt_constraints,
        requested_backend=requested_backend,
        max_attempts=ctx.queue_manager.max_attempts if ctx.queue_manager is not None else 1,
    )
    _enqueue_generation(
        ctx,
        task_id=task_id,
        metadata=metadata,
        plan=prepared.plan,
        auth_source=auth_source,
    )
    return {
        "task": _with_file_urls(
            metadata,
            ctx.active_task_ids,
            ctx.gallery_storage,
            ctx.reference_asset_storage,
            ctx.reference_file_storage,
        ),
        "request": stored_request_payload,
    }


def _reject_cached_unsupported_reference_files(
    ctx: WebUIContext,
    *,
    has_reference_files: bool,
    requested_backend: str,
    provider_id: str | None,
    main_model: str,
) -> None:
    if not has_reference_files:
        return
    key = reference_file_capability_key_for_backend(
        requested_backend=requested_backend,
        provider_id=str(provider_id or ""),
        main_model=main_model,
        api_settings=ctx.api_settings,
    )
    if key in ctx.responses_file_unsupported_keys:
        raise HTTPException(status_code=400, detail=PROVIDER_REFERENCE_FILES_UNSUPPORTED_DETAIL)


async def _prepare_reference_files(
    storage: ReferenceFileStorage,
    uploads: list[UploadFile],
    asset_ids: list[str],
) -> PreparedReferenceFiles:
    try:
        validated_uploads = await read_reference_file_uploads(uploads)
    except ValueError as exc:
        code = str(exc)
        raise HTTPException(
            status_code=400,
            detail={"code": code, "message": REFERENCE_FILE_ERROR_MESSAGES.get(code, "The reference file is invalid.")},
        ) from exc
    try:
        selected_records = resolve_reference_file_ids(storage, asset_ids, touch=False)
    except (FileNotFoundError, OSError, ValueError) as exc:
        raise HTTPException(status_code=404, detail=REFERENCE_FILE_MISSING_DETAIL) from exc
    verified_selected_records, selected_inputs = _resolve_reference_files(
        storage,
        selected_records,
    )

    predicted_records = dedupe_reference_file_records(
        [reference_file_task_record(upload) for upload in validated_uploads]
        + verified_selected_records
    )
    try:
        validate_reference_file_total(predicted_records)
    except ValueError as exc:
        code = str(exc)
        raise HTTPException(
            status_code=400,
            detail={"code": code, "message": REFERENCE_FILE_ERROR_MESSAGES.get(code, "The reference file is invalid.")},
        ) from exc

    uploads_by_id = {
        upload.asset_id: upload
        for upload in validated_uploads
    }
    selected_inputs_by_id = {
        str(record["id"]): response_input
        for record, response_input in zip(
            verified_selected_records,
            selected_inputs,
            strict=True,
        )
    }
    response_inputs: list[ResponsesInputFile] = []
    for record in predicted_records:
        asset_id = str(record["id"])
        upload = uploads_by_id.get(asset_id)
        if upload is not None:
            response_inputs.append(
                _reference_file_to_responses_input(
                    Path(upload.filename),
                    record,
                    data=upload.data,
                )
            )
        else:
            response_inputs.append(selected_inputs_by_id[asset_id])
    return PreparedReferenceFiles(
        uploads=tuple(validated_uploads),
        selected_asset_ids=tuple(
            dict.fromkeys(str(value or "").strip() for value in asset_ids)
        ),
        records=tuple(predicted_records),
        response_inputs=tuple(response_inputs),
    )


def _commit_reference_files(
    storage: ReferenceFileStorage,
    prepared: PreparedReferenceFiles,
) -> list[dict[str, Any]]:
    try:
        return storage.commit_batch(
            prepared.uploads,
            prepared.selected_asset_ids,
        )
    except ValueError as exc:
        code = str(exc)
        if code == "reference_file_missing":
            raise HTTPException(status_code=404, detail=REFERENCE_FILE_MISSING_DETAIL) from exc
        stable_code = code if code in REFERENCE_FILE_ERROR_MESSAGES else "reference_file_invalid"
        raise HTTPException(
            status_code=400,
            detail={
                "code": stable_code,
                "message": REFERENCE_FILE_ERROR_MESSAGES[stable_code],
            },
        ) from exc


async def _prepare_raster_uploads(
    uploads: list[UploadFile],
) -> list[ValidatedRasterImage]:
    try:
        return await read_validated_raster_uploads(uploads)
    except InvalidRasterImage as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _prepared_reference_asset(image: ValidatedRasterImage) -> dict[str, Any]:
    return {
        "id": image.sha256,
        "sha256": image.sha256,
        "filename": image.filename,
        "mime_type": image.mime_type,
        "size_bytes": len(image.data),
    }


def _commit_reference_assets(
    ctx: WebUIContext,
    *,
    uploads: list[ValidatedRasterImage],
    predicted_assets: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    uploads_by_id = {image.sha256: image for image in uploads}
    committed: list[dict[str, Any]] = []
    for predicted in predicted_assets:
        asset_id = str(predicted.get("id") or "")
        upload = uploads_by_id.get(asset_id)
        try:
            if upload is not None:
                item = ctx.reference_asset_storage.create_or_touch(
                    upload.filename,
                    upload.data,
                    upload.mime_type,
                )
            else:
                item = ctx.reference_asset_storage.touch(asset_id)
        except (FileNotFoundError, OSError, ValueError) as exc:
            raise HTTPException(
                status_code=404,
                detail=f"Reference asset not found: {asset_id}",
            ) from exc
        committed.append(item)
    return committed


def _predicted_reference_data_urls(
    ctx: WebUIContext,
    *,
    uploads: list[ValidatedRasterImage],
    predicted_assets: list[dict[str, Any]],
) -> list[str]:
    uploads_by_id = {image.sha256: image for image in uploads}
    data_urls: list[str] = []
    for item in predicted_assets:
        asset_id = str(item["id"])
        upload = uploads_by_id.get(asset_id)
        if upload is not None:
            data_urls.append(
                _bytes_to_data_url(
                    upload.data,
                    filename=upload.filename,
                    mime_type=upload.mime_type,
                )
            )
        else:
            data_urls.append(
                _file_to_data_url(
                    ctx.reference_asset_storage.image_path(asset_id),
                    mime_type=str(item.get("mime_type") or ""),
                )
            )
    return data_urls


def _validate_task_image_resources(
    *,
    reference_assets: list[dict[str, Any]],
    gallery_refs: list[dict[str, Any]],
    mask: ValidatedRasterImage | None = None,
) -> None:
    resources: list[TaskImageResource] = []
    for item in [*reference_assets, *gallery_refs]:
        digest = str(item.get("sha256") or item.get("id") or "").strip()
        resources.append(
            TaskImageResource(
                key=f"content:{digest}",
                size_bytes=int(item.get("size_bytes") or 0),
            )
        )
    if mask is not None:
        resources.append(
            TaskImageResource(
                key=f"content:{mask.sha256}",
                size_bytes=len(mask.data),
            )
        )
    try:
        validate_task_image_total(
            resources,
            max_total_bytes=MAX_TASK_IMAGE_BYTES,
        )
    except TaskImageLimitError as exc:
        raise HTTPException(
            status_code=413,
            detail=TASK_IMAGES_TOTAL_TOO_LARGE_DETAIL,
        ) from exc


def _gallery_data_urls(
    ctx: WebUIContext,
    gallery_refs: list[dict[str, Any]],
) -> list[str]:
    return [
        _file_to_data_url(
            ctx.gallery_storage.image_path(str(item["id"])),
            mime_type="",
        )
        for item in gallery_refs
    ]


def register_generation_routes(app: FastAPI, ctx: WebUIContext) -> None:
    h = ctx.route_helpers

    @app.post("/api/generate")
    async def generate(
        request: Request,
        prompt: str = Form(...),
        ui_language: str = Form("zh-CN"),
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
        canonical_model_id: str | None = Form(None),
        provider_id: str | None = Form(None),
        binding_id: str | None = Form(None),
        parameters_json: str | None = Form(None),
        prompt_for_model: str | None = Form(None),
        prompt_fidelity: str = Form(DEFAULT_PROMPT_FIDELITY),
        gallery_image_ids: list[str] | None = Form(None),
        reference_asset_ids: list[str] | None = Form(None),
        reference_file_ids: list[str] | None = Form(None),
        reference_images: list[UploadFile] | None = File(None),
        reference_files: list[UploadFile] | None = File(None),
    ) -> dict[str, Any]:
        explicit_form_fields = frozenset(str(key) for key in (await request.form()).keys())
        auth_source = _request_auth_source(ctx, provider_id)
        if auth_source == "codex" and not ctx.route_helpers["codex_auth_checker"]():
            raise HTTPException(status_code=401, detail="Codex auth is not available")
        main_model = effective_reference_file_main_model(main_model)

        provider_hint = provider_id if auth_source == "api" and provider_id else api_provider_id
        effective_api_provider_id = h["request_api_provider_id"](auth_source, provider_hint)
        effective_api_provider_name = h["request_api_provider_name"](auth_source, effective_api_provider_id)
        effective_api_mode = h["request_api_mode"](auth_source, api_mode, effective_api_provider_id)
        effective_codex_mode = _codex_mode_for_binding(
            provider_id,
            binding_id,
            h["request_codex_mode"](auth_source, codex_mode),
        )
        effective_api_images_concurrency = h["request_api_images_concurrency"](auth_source, effective_api_provider_id)
        requested_backend = h["backend_for_submit"](auth_source, effective_api_mode, effective_codex_mode)
        if (reference_files or reference_file_ids) and not requested_backend.endswith("_responses"):
            raise HTTPException(
                status_code=400,
                detail={
                    "code": "reference_files_require_responses",
                    "message": "Reference files require a Responses backend.",
                },
            )
        _reject_cached_unsupported_reference_files(
            ctx,
            has_reference_files=bool(reference_files or reference_file_ids),
            requested_backend=requested_backend,
            provider_id=effective_api_provider_id,
            main_model=main_model,
        )

        gallery_refs, _ = _resolve_gallery_refs(
            ctx.gallery_storage,
            gallery_image_ids or [],
            include_data_urls=False,
        )
        uploaded_images = await _prepare_raster_uploads(reference_images or [])
        predicted_uploaded_assets = [
            _prepared_reference_asset(image)
            for image in uploaded_images
        ]
        selected_assets, _ = _resolve_reference_assets(
            ctx.reference_asset_storage,
            reference_asset_ids or [],
            touch=False,
            include_data_urls=False,
        )
        predicted_assets = h["dedupe_reference_assets"](
            predicted_uploaded_assets + selected_assets
        )
        _validate_task_image_resources(
            reference_assets=predicted_assets,
            gallery_refs=gallery_refs,
        )
        prepared_reference_files = await _prepare_reference_files(
            ctx.reference_file_storage,
            reference_files or [],
            reference_file_ids or [],
        )
        reference_data_urls = _predicted_reference_data_urls(
            ctx,
            uploads=uploaded_images,
            predicted_assets=predicted_assets,
        )
        gallery_data_urls = _gallery_data_urls(ctx, gallery_refs)
        all_reference_data_urls = reference_data_urls + gallery_data_urls
        prepared_submission = _prepare_generation_submission(
            ctx,
            operation="generate",
            prompt=prompt,
            prompt_for_model=prompt_for_model,
            ui_language=ui_language,
            prompt_fidelity=prompt_fidelity,
            main_model=main_model,
            model=model,
            size=size,
            resolution=resolution,
            ratio=ratio,
            orientation=orientation,
            quality=quality,
            background=background,
            output_format=output_format,
            input_fidelity=None,
            moderation=moderation,
            output_compression=output_compression,
            n=n,
            web_search=web_search,
            auth_source=auth_source,
            effective_api_mode=effective_api_mode,
            effective_codex_mode=effective_codex_mode,
            effective_api_provider_id=effective_api_provider_id,
            effective_api_provider_name=effective_api_provider_name,
            effective_api_images_concurrency=effective_api_images_concurrency,
            requested_backend=requested_backend,
            canonical_model_id=canonical_model_id,
            provider_id=provider_id,
            binding_id=binding_id,
            parameters_json=parameters_json,
            explicit_form_fields=explicit_form_fields,
            image_data_urls=all_reference_data_urls,
            mask_data_url=None,
            reference_file_inputs=list(prepared_reference_files.response_inputs),
        )

        reference_assets = _commit_reference_assets(
            ctx,
            uploads=uploaded_images,
            predicted_assets=predicted_assets,
        )
        file_references = _commit_reference_files(
            ctx.reference_file_storage,
            prepared_reference_files,
        )
        task = ctx.storage.create_task("generate")
        return _persist_generation_submission(
            ctx,
            prepared=prepared_submission,
            operation="generate",
            task_id=task.task_id,
            created_at=utc_now(),
            prompt=prompt,
            requested_backend=requested_backend,
            auth_source=auth_source,
            effective_api_provider_id=effective_api_provider_id,
            effective_api_provider_name=effective_api_provider_name,
            effective_api_images_concurrency=effective_api_images_concurrency,
            input_files=[],
            mask_file=None,
            gallery_refs=gallery_refs,
            reference_assets=reference_assets,
            file_references=file_references,
        )

    @app.post("/api/edit")
    async def edit(
        request: Request,
        prompt: str = Form(...),
        ui_language: str = Form("zh-CN"),
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
        canonical_model_id: str | None = Form(None),
        provider_id: str | None = Form(None),
        binding_id: str | None = Form(None),
        parameters_json: str | None = Form(None),
        prompt_for_model: str | None = Form(None),
        prompt_fidelity: str = Form(DEFAULT_PROMPT_FIDELITY),
        gallery_image_ids: list[str] | None = Form(None),
        reference_asset_ids: list[str] | None = Form(None),
        reference_file_ids: list[str] | None = Form(None),
        images: list[UploadFile] | None = File(None),
        mask: UploadFile | None = File(None),
        reference_files: list[UploadFile] | None = File(None),
    ) -> dict[str, Any]:
        explicit_form_fields = frozenset(str(key) for key in (await request.form()).keys())
        auth_source = _request_auth_source(ctx, provider_id)
        if auth_source == "codex" and not ctx.route_helpers["codex_auth_checker"]():
            raise HTTPException(status_code=401, detail="Codex auth is not available")
        main_model = effective_reference_file_main_model(main_model)

        provider_hint = provider_id if auth_source == "api" and provider_id else api_provider_id
        effective_api_provider_id = h["request_api_provider_id"](auth_source, provider_hint)
        effective_api_provider_name = h["request_api_provider_name"](auth_source, effective_api_provider_id)
        effective_api_mode = h["request_api_mode"](auth_source, api_mode, effective_api_provider_id)
        effective_codex_mode = _codex_mode_for_binding(
            provider_id,
            binding_id,
            h["request_codex_mode"](auth_source, codex_mode),
        )
        effective_api_images_concurrency = h["request_api_images_concurrency"](auth_source, effective_api_provider_id)
        requested_backend = h["backend_for_submit"](auth_source, effective_api_mode, effective_codex_mode)
        if (reference_files or reference_file_ids) and not requested_backend.endswith("_responses"):
            raise HTTPException(
                status_code=400,
                detail={
                    "code": "reference_files_require_responses",
                    "message": "Reference files require a Responses backend.",
                },
            )
        _reject_cached_unsupported_reference_files(
            ctx,
            has_reference_files=bool(reference_files or reference_file_ids),
            requested_backend=requested_backend,
            provider_id=effective_api_provider_id,
            main_model=main_model,
        )

        gallery_refs, _ = _resolve_gallery_refs(
            ctx.gallery_storage,
            gallery_image_ids or [],
            include_data_urls=False,
        )
        uploaded_images = await _prepare_raster_uploads(images or [])
        prepared_masks = await _prepare_raster_uploads(
            [mask] if mask is not None else []
        )
        prepared_mask = prepared_masks[0] if prepared_masks else None
        predicted_uploaded_assets = [
            _prepared_reference_asset(image)
            for image in uploaded_images
        ]
        selected_assets, _ = _resolve_reference_assets(
            ctx.reference_asset_storage,
            reference_asset_ids or [],
            touch=False,
            include_data_urls=False,
        )
        predicted_assets = h["dedupe_reference_assets"](
            predicted_uploaded_assets + selected_assets
        )
        if not predicted_assets and not gallery_refs:
            raise HTTPException(status_code=400, detail="At least one image is required")
        _validate_task_image_resources(
            reference_assets=predicted_assets,
            gallery_refs=gallery_refs,
            mask=prepared_mask,
        )
        prepared_reference_files = await _prepare_reference_files(
            ctx.reference_file_storage,
            reference_files or [],
            reference_file_ids or [],
        )
        image_data_urls = _predicted_reference_data_urls(
            ctx,
            uploads=uploaded_images,
            predicted_assets=predicted_assets,
        )
        gallery_data_urls = _gallery_data_urls(ctx, gallery_refs)
        all_image_data_urls = image_data_urls + gallery_data_urls
        mask_data_url = (
            _bytes_to_data_url(
                prepared_mask.data,
                filename=prepared_mask.filename,
                mime_type=prepared_mask.mime_type,
            )
            if prepared_mask is not None
            else None
        )
        effective_input_fidelity = input_fidelity if image_model_supports_input_fidelity(model) else None
        prepared_submission = _prepare_generation_submission(
            ctx,
            operation="edit",
            prompt=prompt,
            prompt_for_model=prompt_for_model,
            ui_language=ui_language,
            prompt_fidelity=prompt_fidelity,
            main_model=main_model,
            model=model,
            size=size,
            resolution=resolution,
            ratio=ratio,
            orientation=orientation,
            quality=quality,
            background=background,
            output_format=output_format,
            input_fidelity=effective_input_fidelity,
            moderation=moderation,
            output_compression=output_compression,
            n=n,
            web_search=web_search,
            auth_source=auth_source,
            effective_api_mode=effective_api_mode,
            effective_codex_mode=effective_codex_mode,
            effective_api_provider_id=effective_api_provider_id,
            effective_api_provider_name=effective_api_provider_name,
            effective_api_images_concurrency=effective_api_images_concurrency,
            requested_backend=requested_backend,
            canonical_model_id=canonical_model_id,
            provider_id=provider_id,
            binding_id=binding_id,
            parameters_json=parameters_json,
            explicit_form_fields=explicit_form_fields,
            image_data_urls=all_image_data_urls,
            mask_data_url=mask_data_url,
            reference_file_inputs=list(prepared_reference_files.response_inputs),
        )

        reference_assets = _commit_reference_assets(
            ctx,
            uploads=uploaded_images,
            predicted_assets=predicted_assets,
        )
        file_references = _commit_reference_files(
            ctx.reference_file_storage,
            prepared_reference_files,
        )
        task = ctx.storage.create_task("edit")
        mask_files = (
            [
                ctx.storage.write_input(
                    task.task_id,
                    prepared_mask.filename,
                    prepared_mask.data,
                    kind="mask",
                    index=1,
                )
            ]
            if prepared_mask is not None
            else []
        )
        mask_file = mask_files[0].name if mask_files else None
        return _persist_generation_submission(
            ctx,
            prepared=prepared_submission,
            operation="edit",
            task_id=task.task_id,
            created_at=utc_now(),
            prompt=prompt,
            requested_backend=requested_backend,
            auth_source=auth_source,
            effective_api_provider_id=effective_api_provider_id,
            effective_api_provider_name=effective_api_provider_name,
            effective_api_images_concurrency=effective_api_images_concurrency,
            input_files=[],
            mask_file=mask_file,
            gallery_refs=gallery_refs,
            reference_assets=reference_assets,
            file_references=file_references,
        )

from __future__ import annotations

from typing import Any, Literal, TypedDict

from .task_enrichment import (
    _dedupe_preserve_order,
    _enrich_gallery_refs,
    _enrich_reference_files,
    _enrich_reference_assets,
    _gallery_category_response,
    _gallery_item_response,
    _gallery_ref_response,
    _infer_gallery_refs_from_prompt,
    _input_sources,
    _input_urls,
    _params,
    _reference_asset_response,
    _with_file_urls,
)
from .task_outputs import (
    _accept_partial_task_successes,
    _api_images_concurrency_metadata_value,
    _append_output_record_state,
    _apply_api_images_concurrency_metadata,
    _apply_api_provider_metadata,
    _complete_task,
    _completed_output_records_for_accept,
    _delete_unselected_task_outputs,
    _downloadable_output_paths,
    _fail_task,
    _finalize_generated_task,
    _is_non_retryable_error,
    _normalize_api_images_concurrency_for_metadata,
    _ordered_output_progress,
    _output_file_from_url,
    _output_record_filename,
    _output_thumbnail_fields,
    _output_url,
    _partial_failure_message,
    _positive_int,
    _retryable_failed_output_indexes,
    _safe_output_path,
    _safe_nonnegative_int,
    _set_task_output_selected,
    _visible_completed_output_records,
    _write_progress_metadata,
    _write_queued_metadata,
    _write_running_metadata,
)


OutputStatus = Literal["running", "completed", "failed", "deleted"]


class TaskOutputRecord(TypedDict, total=False):
    index: int
    status: OutputStatus
    deleted: bool
    file: str
    url: str
    thumbnail_file: str
    thumbnail_url: str
    size: str
    format: str
    quality: str
    background: str
    revised_prompt: str
    usage: dict[str, Any]
    tool_usage: dict[str, Any]
    error: str
    attempts: int


class TaskMetadata(TypedDict, total=False):
    task_id: str
    created_at: str
    updated_at: str
    viewed_at: str
    queued_at: str
    started_at: str
    mode: str
    status: str
    prompt: str
    prompt_for_model: str
    params: dict[str, Any]
    generation_snapshot: dict[str, Any]
    generation_error: dict[str, Any]
    tool_usage: dict[str, Any]
    tool_usages: list[dict[str, Any]]
    input_files: list[str]
    mask_file: str | None
    input_urls: list[str]
    input_thumbnail_urls: list[str]
    gallery_refs: list[dict[str, Any]]
    reference_assets: list[dict[str, Any]]
    reference_files: list[dict[str, Any]]
    reference_file_count: int
    input_sources: list[dict[str, Any]]
    generated_count: int
    failed_count: int
    total_count: int
    output_files: list[str]
    output_urls: list[str]
    outputs: list[TaskOutputRecord]
    selected_output_indexes: list[int]
    deleted_output_indexes: list[int]
    last_error: str

from __future__ import annotations
from pathlib import PureWindowsPath
from typing import Any
from urllib.parse import urlparse


def _record_at(records: list[object], source_index: int | None) -> dict[str, Any]:
    index = int(source_index or 1) - 1
    if 0 <= index < len(records) and isinstance(records[index], dict):
        return dict(records[index])
    return {}


def _safe_asset_task_record(record: dict[str, Any]) -> dict[str, Any]:
    return {
        key: record[key]
        for key in ("id", "filename", "mime_type", "size_bytes", "sha256")
        if key in record
    }


def _safe_gallery_task_record(record: dict[str, Any]) -> dict[str, Any]:
    return {
        key: record[key]
        for key in ("id", "name", "category", "filename", "mime_type", "size_bytes", "sha256", "prompt_note")
        if key in record
    }


def _rewrite_restored_metadata(
    raw: dict[str, Any],
    task_id: str,
    input_names: list[str],
    mask_name: str | None,
    output_names: list[str],
    reference_assets: list[dict[str, Any]],
    gallery_refs: list[dict[str, Any]],
    reference_files: list[dict[str, Any]],
) -> dict[str, Any]:
    metadata = _drop_untrusted_local_paths(raw)
    metadata["task_id"] = task_id
    metadata["input_files"] = list(input_names)
    if mask_name is None:
        metadata.pop("mask_file", None)
    else:
        metadata["mask_file"] = mask_name
    metadata["output_files"] = list(output_names)
    if output_names:
        metadata["output_file"] = output_names[0]
    else:
        metadata.pop("output_file", None)
    raw_outputs = raw.get("outputs") if isinstance(raw.get("outputs"), list) else []
    outputs: list[dict[str, Any]] = []
    for index, filename in enumerate(output_names, start=1):
        source = raw_outputs[index - 1] if index <= len(raw_outputs) and isinstance(raw_outputs[index - 1], dict) else {}
        record = _drop_untrusted_local_paths(source)
        record.update(index=index, file=filename)
        record.pop("thumbnail_file", None)
        record.pop("thumbnail_url", None)
        outputs.append(record)
    metadata["outputs"] = outputs
    metadata["reference_assets"] = reference_assets
    metadata["gallery_refs"] = gallery_refs
    metadata["reference_files"] = reference_files
    metadata.pop("input_urls", None)
    metadata.pop("input_thumbnail_urls", None)
    return metadata


def _rewrite_restored_request(
    raw: dict[str, Any],
    input_names: list[str],
    mask_name: str | None,
    reference_assets: list[dict[str, Any]],
    gallery_refs: list[dict[str, Any]],
    reference_files: list[dict[str, Any]],
) -> dict[str, Any]:
    request = _drop_untrusted_local_paths(raw)
    if "input_files" in raw or input_names:
        request["input_files"] = list(input_names)
    if mask_name is not None:
        request["mask_file"] = mask_name
    image_refs: dict[str, Any] = {
        "input_files": list(input_names),
        "gallery_refs": gallery_refs,
        "reference_assets": reference_assets,
    }
    if mask_name is not None:
        image_refs["mask_file"] = mask_name
    request["webui_image_refs"] = image_refs
    request["webui_file_refs"] = {"reference_files": reference_files}
    return request


def _drop_untrusted_local_paths(value: Any, key: str = "") -> Any:
    if isinstance(value, dict):
        cleaned: dict[str, Any] = {}
        for child_key, child_value in value.items():
            name = str(child_key)
            if name in {
                "input_files", "mask_file", "output_file", "output_files", "file",
                "thumbnail_file", "thumbnail_url", "input_urls", "input_thumbnail_urls",
                "url", "output_url", "output_urls", "input_sources",
            }:
                continue
            if name.endswith("_path") or name.endswith("_paths"):
                continue
            cleaned_value = _drop_untrusted_local_paths(child_value, name)
            if cleaned_value is not _UNSAFE_LOCAL_VALUE:
                cleaned[name] = cleaned_value
        return cleaned
    if isinstance(value, list):
        cleaned_items = [_drop_untrusted_local_paths(item, key) for item in value]
        return [item for item in cleaned_items if item is not _UNSAFE_LOCAL_VALUE]
    # These schema fields are display/model text, never resource locators.
    # Preserve their exact contents, including leading slashes and whitespace.
    if isinstance(value, str) and key not in _RESTORED_TEXT_FIELDS and _is_untrusted_local_value(value):
        return _UNSAFE_LOCAL_VALUE
    return value


def _is_untrusted_local_value(value: str) -> bool:
    text = value.strip()
    if not text:
        return False
    if text.startswith("/") or PureWindowsPath(text).is_absolute():
        return True
    parsed = urlparse(text)
    if parsed.scheme.casefold() == "file":
        return True
    if parsed.scheme.casefold() in {"http", "https"}:
        host = (parsed.hostname or "").casefold()
        if host in {"localhost", "127.0.0.1", "::1"}:
            return True
    return False

_RESTORED_TEXT_FIELDS = frozenset({
    "prompt", "prompt_for_model", "revised_prompt", "negative_prompt",
    "text", "content", "instructions", "description", "name", "title",
    "prompt_note", "error", "last_error", "message",
})

_UNSAFE_LOCAL_VALUE = object()

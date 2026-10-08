from __future__ import annotations

import json
from typing import Any

from fastapi import HTTPException


def normalize_reference_image_order(
    raw: str | None,
    uploads: list[dict[str, Any]],
    assets: list[dict[str, Any]],
    galleries: list[dict[str, Any]],
) -> list[dict[str, str]] | None:
    """Resolve multipart upload positions to durable asset identities before deduping."""
    if raw is None:
        return None
    available = {
        **{("upload", index): ("asset", str(item["id"])) for index, item in enumerate(uploads)},
        **{("asset", str(item["id"])): ("asset", str(item["id"])) for item in assets},
        **{("gallery", str(item["id"])): ("gallery", str(item["id"])) for item in galleries},
    }
    try:
        entries = json.loads(raw)
        if not isinstance(entries, list):
            raise ValueError("Expected a list")
        seen_inputs: set[tuple[str, Any]] = set()
        seen_images: set[tuple[str, str]] = set()
        result = []
        for entry in entries:
            if not isinstance(entry, dict):
                raise ValueError("Expected an image reference")
            kind = entry.get("kind")
            identity = entry.get("index") if kind == "upload" else entry.get("id")
            if kind == "upload":
                if type(identity) is not int:
                    raise ValueError("Invalid upload index")
            elif kind not in {"asset", "gallery"} or not isinstance(identity, str):
                raise ValueError("Invalid image reference")
            key = (kind, identity)
            resolved = available[key]
            seen_inputs.add(key)
            if resolved not in seen_images:
                seen_images.add(resolved)
                result.append({"kind": resolved[0], "id": resolved[1]})
        if seen_inputs != available.keys():
            raise ValueError("Image order must cover every submitted image")
        return result
    except (ValueError, KeyError, TypeError) as exc:
        raise HTTPException(status_code=400, detail={
            "code": "reference_image_order_invalid",
            "message": "Reference image order does not match the submitted images.",
        }) from exc


def order_reference_sources(
    sources: list[dict[str, Any]], order: Any,
) -> list[dict[str, Any]]:
    """Order known sources without discarding missing-image placeholders or legacy inputs."""
    if not isinstance(order, list):
        return sources
    positions: dict[tuple[str, str], int] = {}
    for entry in order:
        if (
            isinstance(entry, dict)
            and isinstance(entry.get("kind"), str)
            and entry["kind"] in {"asset", "gallery"}
            and isinstance(entry.get("id"), str)
        ):
            positions.setdefault((entry["kind"], entry["id"]), len(positions))
    # Legacy task-local files have no durable ID and execute before stored references.
    return sorted(sources, key=lambda source: -1 if source.get("kind") == "upload" else positions.get(
        (str(source.get("kind")), str(source.get("id"))), len(positions)
    ))


def remap_reference_image_order(order: Any, identities: dict[tuple[str, str], str]) -> list[dict[str, str]] | None:
    """Keep restored references in order while translating archive-local identities."""
    if not isinstance(order, list):
        return None
    remapped = []
    seen = set()
    for entry in order:
        if not isinstance(entry, dict):
            continue
        kind, identity = entry.get("kind"), entry.get("id")
        if not isinstance(kind, str) or not isinstance(identity, str):
            continue
        restored_id = identities.get((kind, identity))
        if restored_id is not None and (kind, restored_id) not in seen:
            seen.add((kind, restored_id))
            remapped.append({"kind": kind, "id": restored_id})
    return remapped


def ordered_reference_data_urls(
    assets: list[dict[str, Any]], asset_urls: list[str],
    galleries: list[dict[str, Any]], gallery_urls: list[str], order: Any,
) -> list[str]:
    sources = [
        {"kind": kind, "id": item["id"], "value": value}
        for kind, items, values in (("asset", assets, asset_urls), ("gallery", galleries, gallery_urls))
        for item, value in zip(items, values, strict=True)
    ]
    return [source["value"] for source in order_reference_sources(sources, order)]

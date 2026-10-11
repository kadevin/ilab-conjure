"""Bind explicit prompt chips to images, independently of names and upload order."""
from __future__ import annotations

import json
from typing import Any

from fastapi import HTTPException


def resolve_prompt_image_mentions(
    raw: str | None, prompt: str, model_prompt: str,
    uploads: list[dict[str, Any]], order: list[dict[str, str]] | None,
) -> tuple[str, str, dict[str, Any] | None]:
    if raw is None:
        return prompt, model_prompt, None
    try:
        context = json.loads(raw)
        if not isinstance(context, dict) or context.get("version") != 1 or order is None:
            raise ValueError("Invalid image mentions")
        template = context.get("template")
        if not isinstance(template, str) or len(template) > 100 or "{number}" not in template:
            raise ValueError("Invalid reference label")
        positions = {(entry["kind"], entry["id"]): number for number, entry in enumerate(order, 1)}

        def resolve(parts: Any, expected: str) -> tuple[str, list[Any], list[Any]]:
            if not isinstance(parts, list) or len(parts) > 10000:
                raise ValueError("Invalid prompt parts")
            visible, compiled, normalized, references = [], [], [], []
            for part in parts:
                if isinstance(part, str):
                    visible.append(part)
                    compiled.append(part)
                    normalized.append(part)
                    continue
                if not isinstance(part, dict) or not isinstance(part.get("text"), str):
                    raise ValueError("Invalid mention")
                source = part.get("source")
                if not isinstance(source, dict) or source.get("missing"):
                    raise ValueError("Invalid reference")
                kind = source.get("kind")
                if kind == "upload":
                    index = source.get("index")
                    if type(index) is not int or not 0 <= index < len(uploads):
                        raise ValueError("Invalid upload")
                    identity = ("asset", str(uploads[index]["id"]))
                elif kind in {"asset", "gallery"} and isinstance(source.get("id"), str):
                    identity = (kind, source["id"])
                else:
                    raise ValueError("Invalid source")
                number = positions[identity]
                mention = {"text": part["text"], "source": {"kind": identity[0], "id": identity[1]}}
                visible.append(part["text"])
                compiled.append(template.replace("{number}", str(number)))
                normalized.append(mention)
                references.append(mention)
            if "".join(visible) != expected:
                raise ValueError("Prompt does not match mentions")
            return "".join(compiled), normalized, references

        original, parts, references = resolve(context.get("parts"), prompt)
        compiled, _, model_references = resolve(context.get("model_parts"), model_prompt)
        if references != model_references:
            raise ValueError("Model references do not match original prompt")
        return original, compiled, {"version": 1, "parts": parts}
    except (ValueError, KeyError, TypeError) as exc:
        raise HTTPException(status_code=400, detail={
            "code": "prompt_image_mentions_invalid",
            "message": "Image mentions do not match the prompt and selected reference images.",
        }) from exc


def remap_prompt_image_mentions(context: Any, identities: dict[tuple[str, str], str]) -> Any:
    """Keep missing references explicit; never bind them to a different restored image."""
    invalid = {"version": 1, "parts": []}
    if not isinstance(context, dict) or context.get("version") != 1 or not isinstance(context.get("parts"), list):
        return invalid
    parts = []
    for part in context["parts"]:
        if isinstance(part, str):
            parts.append(part)
            continue
        if not isinstance(part, dict) or not isinstance(part.get("text"), str) or not isinstance(part.get("source"), dict):
            return invalid
        source = part["source"]
        kind, source_id = source.get("kind"), source.get("id")
        if kind not in ("asset", "gallery") or not isinstance(source_id, str):
            return invalid
        identity = None if source.get("missing") else identities.get((kind, source_id))
        parts.append({"text": part["text"], "source": {
            "kind": kind, "id": identity or source_id, "missing": identity is None,
        }})
    return {"version": 1, "parts": parts}

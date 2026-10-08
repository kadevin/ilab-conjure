from __future__ import annotations

import json
import re
from typing import Any

from fastapi import HTTPException


def resolve_gallery_prompt(prompt: str, raw: str | None, order: list[dict[str, str]] | None) -> str:
    """Render localized gallery guidance against the same deduplicated order as image inputs."""
    if raw is None:
        return prompt
    try:
        context = json.loads(raw)
        if not isinstance(context, dict) or order is None:
            raise ValueError("Gallery instructions require an explicit image order")
        header, template, references = context["header"], context["template"], context["references"]
        if not isinstance(header, str) or not isinstance(template, str) or "{number}" not in template:
            raise ValueError("Invalid gallery instruction template")
        if not isinstance(references, list):
            raise ValueError("Invalid gallery references")
        by_id: dict[str, dict[str, Any]] = {}
        for reference in references:
            if not isinstance(reference, dict) or any(
                not isinstance(reference.get(key), str) for key in ("id", "name", "role", "note")
            ):
                raise ValueError("Invalid gallery reference")
            identity = reference["id"]
            if identity in by_id:
                raise ValueError("Duplicate gallery instruction")
            by_id[identity] = reference
        if set(by_id) != {entry["id"] for entry in order if entry["kind"] == "gallery"}:
            raise ValueError("Gallery instructions must match the selected images")
        lines = []
        for number, entry in enumerate(order, start=1):
            if entry["kind"] != "gallery":
                continue
            values = {**by_id[entry["id"]], "number": str(number)}
            # Substitute the template once; user-authored values are never parsed as placeholders.
            lines.append(re.sub(r"\{(number|name|role|note)\}", lambda match: values[match[1]], template))
        return f"{prompt}\n\n{header}\n" + "\n".join(lines) if lines else prompt
    except (ValueError, KeyError, TypeError) as exc:
        raise HTTPException(status_code=400, detail={
            "code": "gallery_prompt_invalid",
            "message": "Gallery instructions do not match the submitted images.",
        }) from exc

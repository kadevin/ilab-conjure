from __future__ import annotations

import json
import re
import uuid
from pathlib import Path
from typing import Any

from .storage_utils import utc_now


MAX_PROMPT_SNIPPETS = 200
MAX_PROMPT_SNIPPET_TAG_LENGTH = 24
MAX_PROMPT_SNIPPET_TITLE_LENGTH = 80
MAX_PROMPT_SNIPPET_CATEGORY_LENGTH = 32
MAX_PROMPT_SNIPPET_CONTENT_LENGTH = 4000
PROMPT_SNIPPET_TRIGGER_CHARS = "~～〜∼˜"
PROMPT_SNIPPET_BOUNDARY_CHARS = "，。,.；;：:！？!?、（）()[]【】\"'“”‘’"
_PROMPT_SNIPPET_TOKEN_PATTERN = re.compile(
    rf"([{re.escape(PROMPT_SNIPPET_TRIGGER_CHARS)}]+)"
    rf"([^\s{re.escape(PROMPT_SNIPPET_TRIGGER_CHARS + '@#' + PROMPT_SNIPPET_BOUNDARY_CHARS)}]+)"
)


class PromptSnippetSettings:
    def __init__(self, path: Path) -> None:
        self.path = path

    def read(self) -> dict[str, Any]:
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return self.default_settings()
        if not isinstance(payload, dict):
            return self.default_settings()
        try:
            return _normalize_prompt_snippets_payload(payload, default_when_missing=True)
        except ValueError:
            return self.default_settings()

    def list(self) -> list[dict[str, Any]]:
        return self.read()["snippets"]

    def create(self, payload: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(payload, dict):
            raise ValueError("Prompt snippet payload must be an object")
        current = self.read()
        snippets = current["snippets"]
        if len(snippets) >= MAX_PROMPT_SNIPPETS:
            raise ValueError("Too many prompt snippets")
        snippet = _normalize_prompt_snippet_payload(
            {
                "id": str(uuid.uuid4()),
                "tag": payload.get("tag"),
                "title": payload.get("title"),
                "content": payload.get("content"),
                "category": payload.get("category"),
                "order": payload.get("order", (len(snippets) + 1) * 10),
                "created_at": utc_now(),
                "updated_at": utc_now(),
            }
        )
        _ensure_unique_prompt_snippet_tag(snippets, snippet["tag"])
        self.write({**current, "snippets": [*snippets, snippet]})
        return snippet

    def update(self, snippet_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(payload, dict):
            raise ValueError("Prompt snippet payload must be an object")
        current = self.read()
        snippets = current["snippets"]
        for index, existing in enumerate(snippets):
            if existing["id"] != snippet_id:
                continue
            merged = {
                **existing,
                "tag": payload.get("tag", existing["tag"]),
                "title": payload.get("title", existing["title"]),
                "content": payload.get("content", existing["content"]),
                "category": payload.get("category", existing["category"]),
                "order": payload.get("order", existing["order"]),
                "updated_at": utc_now(),
            }
            snippet = _normalize_prompt_snippet_payload(merged)
            _ensure_unique_prompt_snippet_tag(snippets, snippet["tag"], exclude_id=snippet_id)
            updated = [*snippets]
            updated[index] = snippet
            self.write({**current, "snippets": updated})
            return snippet
        raise ValueError("Prompt snippet not found")

    def delete(self, snippet_id: str) -> None:
        current = self.read()
        snippets = current["snippets"]
        updated = [snippet for snippet in snippets if snippet["id"] != snippet_id]
        if len(updated) == len(snippets):
            raise ValueError("Prompt snippet not found")
        self.write({**current, "snippets": updated})

    def write(self, payload: dict[str, Any]) -> dict[str, Any]:
        settings = _normalize_prompt_snippets_payload(payload, default_when_missing=False)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(settings, indent=2, ensure_ascii=False), encoding="utf-8")
        return settings

    @staticmethod
    def default_settings() -> dict[str, Any]:
        return {"version": 1, "snippets": []}


def expand_prompt_snippets(prompt: Any, snippets: list[dict[str, Any]]) -> str:
    text = str(prompt or "")
    content_by_tag = {
        str(snippet.get("tag") or "").lower(): str(snippet.get("content") or "")
        for snippet in snippets
        if isinstance(snippet, dict) and snippet.get("tag") and snippet.get("content")
    }
    previous_snippet_end = -1

    def replace(match: re.Match[str]) -> str:
        nonlocal previous_snippet_end
        previous = text[match.start() - 1] if match.start() > 0 else ""
        follows_snippet = match.start() == previous_snippet_end
        if previous and not previous.isspace() and previous not in PROMPT_SNIPPET_BOUNDARY_CHARS and not follows_snippet:
            previous_snippet_end = -1
            return match.group(0)
        content = content_by_tag.get(match.group(2).lower())
        if not content:
            previous_snippet_end = -1
            return match.group(0)
        previous_snippet_end = match.end()
        return content

    return _PROMPT_SNIPPET_TOKEN_PATTERN.sub(replace, text)


def _normalize_prompt_snippets_payload(payload: dict[str, Any], *, default_when_missing: bool) -> dict[str, Any]:
    snippets_value = payload.get("snippets")
    if snippets_value is None and default_when_missing:
        snippets_value = []
    if not isinstance(snippets_value or [], list):
        raise ValueError("Prompt snippets must be an array")
    snippets: list[dict[str, Any]] = []
    seen_tags: set[str] = set()
    for item in (snippets_value or [])[:MAX_PROMPT_SNIPPETS]:
        snippet = _normalize_prompt_snippet_payload(item)
        tag_key = snippet["tag"].casefold()
        if tag_key in seen_tags:
            continue
        seen_tags.add(tag_key)
        snippets.append(snippet)
    snippets.sort(key=lambda item: (item.get("order", 0), item.get("updated_at", ""), item.get("tag", "")))
    return {"version": 1, "snippets": snippets}


def _normalize_prompt_snippet_payload(item: Any) -> dict[str, Any]:
    if not isinstance(item, dict):
        raise ValueError("Prompt snippet must be an object")
    snippet_id = _clean_prompt_snippet_id(item.get("id"))
    tag = _clean_prompt_snippet_tag(item.get("tag"))
    content = _clean_prompt_snippet_content(item.get("content"))
    title = _clean_prompt_snippet_title(item.get("title"), fallback=tag)
    category = _clean_prompt_snippet_category(item.get("category"))
    order = _clean_prompt_snippet_order(item.get("order"))
    created_at = str(item.get("created_at") or utc_now())
    updated_at = str(item.get("updated_at") or created_at)
    return {
        "id": snippet_id,
        "tag": tag,
        "title": title,
        "content": content,
        "category": category,
        "order": order,
        "created_at": created_at,
        "updated_at": updated_at,
    }


def _ensure_unique_prompt_snippet_tag(
    snippets: list[dict[str, Any]],
    tag: str,
    *,
    exclude_id: str | None = None,
) -> None:
    tag_key = tag.casefold()
    for snippet in snippets:
        if exclude_id and snippet.get("id") == exclude_id:
            continue
        if str(snippet.get("tag", "")).casefold() == tag_key:
            raise ValueError("Duplicate prompt snippet tag")


def _clean_prompt_snippet_id(value: Any) -> str:
    text = str(value or "").strip()
    return text[:80] or str(uuid.uuid4())


def _clean_prompt_snippet_tag(value: Any) -> str:
    tag = str(value or "").strip().lstrip("~～〜∼˜").strip()
    if not tag or len(tag) > MAX_PROMPT_SNIPPET_TAG_LENGTH:
        raise ValueError("Invalid prompt snippet tag")
    if re.search(r"[\s~～〜∼˜@#，。,.]", tag):
        raise ValueError("Invalid prompt snippet tag")
    return tag


def _clean_prompt_snippet_title(value: Any, *, fallback: str) -> str:
    title = str(value or "").strip()[:MAX_PROMPT_SNIPPET_TITLE_LENGTH]
    return title or fallback


def _clean_prompt_snippet_category(value: Any) -> str:
    return str(value or "常用").strip()[:MAX_PROMPT_SNIPPET_CATEGORY_LENGTH] or "常用"


def _clean_prompt_snippet_content(value: Any) -> str:
    content = str(value or "").strip()
    if not content or len(content) > MAX_PROMPT_SNIPPET_CONTENT_LENGTH:
        raise ValueError("Invalid prompt snippet content")
    return content


def _clean_prompt_snippet_order(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0

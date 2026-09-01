from __future__ import annotations

import json
import re
import threading
import uuid
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from codex_image.client import DEFAULT_IMAGE_MODEL

from .atomic_files import atomic_write_text
from .store_locks import StoreLockMixin, store_locked
from .storage_utils import utc_now


MAX_PROMPT_TEMPLATES = 200
MAX_PROMPT_TEMPLATE_TITLE_LENGTH = 80
MAX_PROMPT_TEMPLATE_SHORT_TITLE_LENGTH = 12
MAX_PROMPT_TEMPLATE_CATEGORY_LENGTH = 32
MAX_PROMPT_TEMPLATE_TAG_LENGTH = 24
MAX_PROMPT_TEMPLATE_TAGS = 12
MAX_PROMPT_TEMPLATE_CONTENT_LENGTH = 8000
MAX_PROMPT_TEMPLATE_NOTES_LENGTH = 500
MAX_PROMPT_TEMPLATE_THUMBNAIL_URL_LENGTH = 500
MAX_PROMPT_TEMPLATE_IMPORT_BYTES = 1_000_000
SUPPORTED_PROMPT_TEMPLATE_MODEL_HINTS = {DEFAULT_IMAGE_MODEL, "any"}
PROMPT_TEMPLATE_MODES = {"text_to_image", "image_to_image", "edit", "any"}
DEFAULT_PROMPT_TEMPLATE_CATEGORIES = [
    {"id": "常用", "name": "常用", "order": 10},
    {"id": "人像", "name": "人像", "order": 20},
    {"id": "产品", "name": "产品", "order": 30},
    {"id": "修复", "name": "修复", "order": 40},
    {"id": "海报", "name": "海报", "order": 50},
    {"id": "电商", "name": "电商", "order": 60},
]


class PromptTemplateSettings(StoreLockMixin):
    def __init__(self, path: Path) -> None:
        self.path = path
        self._lock = threading.RLock()

    @store_locked
    def read(self) -> dict[str, Any]:
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return self.default_settings()
        if not isinstance(payload, dict):
            return self.default_settings()
        try:
            return _normalize_prompt_templates_payload(payload, default_when_missing=True)
        except ValueError:
            return self.default_settings()

    @store_locked
    def list(self) -> list[dict[str, Any]]:
        return self.read()["templates"]

    @store_locked
    def list_categories(self) -> list[dict[str, Any]]:
        return self.read()["categories"]

    @store_locked
    def create(self, payload: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(payload, dict):
            raise ValueError("Prompt template payload must be an object")
        current = self.read()
        templates = current["templates"]
        if len(templates) >= MAX_PROMPT_TEMPLATES:
            raise ValueError("Too many prompt templates")
        now = utc_now()
        template = _normalize_prompt_template_payload(
            {
                "id": str(uuid.uuid4()),
                "title": payload.get("title"),
                "short_title": payload.get("short_title"),
                "content": payload.get("content"),
                "category": payload.get("category"),
                "tags": payload.get("tags"),
                "mode": payload.get("mode"),
                "model_hint": payload.get("model_hint"),
                "notes": payload.get("notes"),
                "thumbnail_url": payload.get("thumbnail_url"),
                "favorite": payload.get("favorite"),
                "usage_count": 0,
                "created_at": now,
                "updated_at": now,
                "last_used_at": "",
            }
        )
        categories = _ensure_prompt_template_categories(current["categories"], [*templates, template])
        self.write({**current, "templates": [*templates, template], "categories": categories})
        return template

    @store_locked
    def update(self, template_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(payload, dict):
            raise ValueError("Prompt template payload must be an object")
        current = self.read()
        templates = current["templates"]
        for index, existing in enumerate(templates):
            if existing["id"] != template_id:
                continue
            merged = {**existing, **{key: value for key, value in payload.items() if key != "id"}, "updated_at": utc_now()}
            template = _normalize_prompt_template_payload(merged)
            updated = [*templates]
            updated[index] = template
            categories = _ensure_prompt_template_categories(current["categories"], updated)
            self.write({**current, "templates": updated, "categories": categories})
            return template
        raise ValueError("Prompt template not found")

    @store_locked
    def mark_used(self, template_id: str) -> dict[str, Any]:
        current = self.read()
        templates = current["templates"]
        for index, existing in enumerate(templates):
            if existing["id"] != template_id:
                continue
            updated_template = _normalize_prompt_template_payload(
                {
                    **existing,
                    "usage_count": int(existing.get("usage_count") or 0) + 1,
                    "last_used_at": utc_now(),
                    "updated_at": existing.get("updated_at") or utc_now(),
                }
            )
            updated = [*templates]
            updated[index] = updated_template
            self.write({**current, "templates": updated})
            return updated_template
        raise ValueError("Prompt template not found")

    @store_locked
    def delete(self, template_id: str) -> None:
        current = self.read()
        templates = current["templates"]
        updated = [template for template in templates if template["id"] != template_id]
        if len(updated) == len(templates):
            raise ValueError("Prompt template not found")
        self.write({**current, "templates": updated})

    @store_locked
    def create_category(self, payload: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(payload, dict):
            raise ValueError("Prompt template category payload must be an object")
        current = self.read()
        category = _normalize_prompt_template_category_payload(
            {"name": payload.get("name") or payload.get("id"), "order": payload.get("order")},
            fallback_order=_next_prompt_template_category_order(current["categories"]),
        )
        _ensure_prompt_template_category_available(current["categories"], category["id"])
        categories = _normalize_prompt_template_categories_payload([*current["categories"], category])
        self.write({**current, "categories": categories})
        return category

    @store_locked
    def update_category(self, category_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(payload, dict):
            raise ValueError("Prompt template category payload must be an object")
        current = self.read()
        old_id = _clean_prompt_template_category(category_id)
        new_category = _normalize_prompt_template_category_payload(
            {"name": payload.get("name") or payload.get("id") or old_id, "order": payload.get("order")},
            fallback_order=_prompt_template_category_order(current["categories"], old_id),
        )
        if old_id != new_category["id"]:
            _ensure_prompt_template_category_available(current["categories"], new_category["id"])
        found = False
        categories: list[dict[str, Any]] = []
        for category in current["categories"]:
            if category["id"] == old_id:
                categories.append(new_category)
                found = True
            else:
                categories.append(category)
        if not found:
            raise ValueError("Prompt template category not found")
        templates = [
            _normalize_prompt_template_payload({**template, "category": new_category["id"] if template["category"] == old_id else template["category"]})
            for template in current["templates"]
        ]
        self.write({**current, "templates": templates, "categories": categories})
        return new_category

    @store_locked
    def delete_category(self, category_id: str) -> dict[str, Any]:
        current = self.read()
        clean_id = _clean_prompt_template_category(category_id)
        if clean_id == "常用":
            raise ValueError("Default prompt template category cannot be deleted")
        categories = [category for category in current["categories"] if category["id"] != clean_id]
        if len(categories) == len(current["categories"]):
            raise ValueError("Prompt template category not found")
        templates = [
            _normalize_prompt_template_payload({**template, "category": "常用" if template["category"] == clean_id else template["category"]})
            for template in current["templates"]
        ]
        settings = self.write({**current, "templates": templates, "categories": categories})
        return settings

    @store_locked
    def export_pack(self) -> dict[str, Any]:
        settings = self.read()
        return {
            "version": 1,
            "format": "webui-prompt-template-pack",
            "model_hint": DEFAULT_IMAGE_MODEL,
            "exported_at": utc_now(),
            "categories": settings["categories"],
            "templates": settings["templates"],
        }

    @store_locked
    def import_pack(self, filename: str, payload: bytes, content_type: str | None = None) -> tuple[dict[str, Any], int, int]:
        imported_categories, template_payloads = _parse_prompt_template_import(filename, payload, content_type)
        current = self.read()
        categories = _normalize_prompt_template_categories_payload([*current["categories"], *imported_categories])
        templates = [*current["templates"]]
        existing_keys = {(template["title"].casefold(), template["content"]) for template in templates}
        imported = 0
        skipped = 0
        now = utc_now()
        for item in template_payloads:
            if len(templates) >= MAX_PROMPT_TEMPLATES:
                skipped += 1
                continue
            candidate = _normalize_prompt_template_payload(
                {
                    **item,
                    "id": str(uuid.uuid4()),
                    "model_hint": DEFAULT_IMAGE_MODEL,
                    "usage_count": 0,
                    "created_at": now,
                    "updated_at": now,
                    "last_used_at": "",
                }
            )
            key = (candidate["title"].casefold(), candidate["content"])
            if key in existing_keys:
                skipped += 1
                continue
            existing_keys.add(key)
            templates.append(candidate)
            categories = _ensure_prompt_template_categories(categories, [candidate])
            imported += 1
        settings = self.write({**current, "templates": templates, "categories": categories})
        return settings, imported, skipped

    @store_locked
    def write(self, payload: dict[str, Any]) -> dict[str, Any]:
        settings = _normalize_prompt_templates_payload(payload, default_when_missing=False)
        atomic_write_text(
            self.path,
            json.dumps(settings, indent=2, ensure_ascii=False),
            mode=0o600,
        )
        return settings

    @staticmethod
    def default_settings() -> dict[str, Any]:
        return {"version": 1, "templates": [], "categories": [*DEFAULT_PROMPT_TEMPLATE_CATEGORIES]}


def _normalize_prompt_templates_payload(payload: dict[str, Any], *, default_when_missing: bool) -> dict[str, Any]:
    templates_value = payload.get("templates")
    if templates_value is None and default_when_missing:
        templates_value = []
    if not isinstance(templates_value or [], list):
        raise ValueError("Prompt templates must be an array")
    templates = [_normalize_prompt_template_payload(item) for item in (templates_value or [])[:MAX_PROMPT_TEMPLATES]]
    templates.sort(key=lambda item: (0 if item["favorite"] else 1, -(item["usage_count"]), item.get("updated_at", ""), item.get("title", "")))
    categories_value = payload.get("categories")
    if categories_value is None:
        categories_value = DEFAULT_PROMPT_TEMPLATE_CATEGORIES if default_when_missing else []
    categories = _normalize_prompt_template_categories_payload(categories_value)
    categories = _ensure_prompt_template_categories(categories, templates)
    return {"version": 1, "templates": templates, "categories": categories}


def _normalize_prompt_template_payload(item: Any) -> dict[str, Any]:
    if not isinstance(item, dict):
        raise ValueError("Prompt template must be an object")
    template_id = _clean_prompt_template_id(item.get("id"))
    title = _clean_prompt_template_title(item.get("title"))
    short_title = _clean_prompt_template_short_title(item.get("short_title"), fallback=title)
    content = _clean_prompt_template_content(item.get("content"))
    category = _clean_prompt_template_category(item.get("category"))
    tags = _clean_prompt_template_tags(item.get("tags"))
    mode = _clean_prompt_template_mode(item.get("mode"))
    model_hint = _clean_prompt_template_model_hint(item.get("model_hint"))
    notes = _clean_prompt_template_notes(item.get("notes"))
    thumbnail_url = _clean_prompt_template_thumbnail_url(item.get("thumbnail_url") or item.get("thumbnail"))
    created_at = str(item.get("created_at") or utc_now())
    updated_at = str(item.get("updated_at") or created_at)
    last_used_at = str(item.get("last_used_at") or "")
    return {
        "id": template_id,
        "title": title,
        "short_title": short_title,
        "content": content,
        "category": category,
        "tags": tags,
        "mode": mode,
        "model_hint": model_hint,
        "notes": notes,
        "thumbnail_url": thumbnail_url,
        "favorite": bool(item.get("favorite")),
        "variables": _extract_prompt_template_variables(content),
        "usage_count": _clean_prompt_template_usage_count(item.get("usage_count")),
        "created_at": created_at,
        "updated_at": updated_at,
        "last_used_at": last_used_at,
    }


def _clean_prompt_template_id(value: Any) -> str:
    text = str(value or "").strip()
    return text[:80] or str(uuid.uuid4())


def _clean_prompt_template_title(value: Any) -> str:
    title = str(value or "").strip()[:MAX_PROMPT_TEMPLATE_TITLE_LENGTH]
    if not title:
        raise ValueError("Invalid prompt template title")
    return title


def _clean_prompt_template_short_title(value: Any, *, fallback: str) -> str:
    title = str(value or "").strip()[:MAX_PROMPT_TEMPLATE_SHORT_TITLE_LENGTH]
    return title or fallback[:MAX_PROMPT_TEMPLATE_SHORT_TITLE_LENGTH]


def _clean_prompt_template_content(value: Any) -> str:
    content = str(value or "").strip()
    if not content or len(content) > MAX_PROMPT_TEMPLATE_CONTENT_LENGTH:
        raise ValueError("Invalid prompt template content")
    return content


def _clean_prompt_template_category(value: Any) -> str:
    return str(value or "常用").strip()[:MAX_PROMPT_TEMPLATE_CATEGORY_LENGTH] or "常用"


def _normalize_prompt_template_categories_payload(value: Any) -> list[dict[str, Any]]:
    if value is None:
        value = []
    if not isinstance(value, list):
        raise ValueError("Prompt template categories must be an array")
    categories: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, raw in enumerate(value):
        category = _normalize_prompt_template_category_payload(raw, fallback_order=(index + 1) * 10)
        key = category["id"].casefold()
        if key in seen:
            continue
        seen.add(key)
        categories.append(category)
    if not any(category["id"] == "常用" for category in categories):
        categories.insert(0, {"id": "常用", "name": "常用", "order": 10})
    categories.sort(key=lambda item: (item["order"], item["name"]))
    return categories


def _normalize_prompt_template_category_payload(value: Any, *, fallback_order: int = 10) -> dict[str, Any]:
    if isinstance(value, str):
        name = _clean_prompt_template_category(value)
        order = fallback_order
    elif isinstance(value, dict):
        name = _clean_prompt_template_category(value.get("name") or value.get("id"))
        order = _clean_prompt_template_category_order(value.get("order"), fallback_order=fallback_order)
    else:
        raise ValueError("Prompt template category must be a string or object")
    return {"id": name, "name": name, "order": order}


def _clean_prompt_template_category_order(value: Any, *, fallback_order: int) -> int:
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return fallback_order


def _ensure_prompt_template_categories(categories: list[dict[str, Any]], templates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result = _normalize_prompt_template_categories_payload(categories)
    known = {category["id"].casefold() for category in result}
    next_order = _next_prompt_template_category_order(result)
    for template in templates:
        category_id = _clean_prompt_template_category(template.get("category"))
        key = category_id.casefold()
        if key in known:
            continue
        result.append({"id": category_id, "name": category_id, "order": next_order})
        known.add(key)
        next_order += 10
    result.sort(key=lambda item: (item["order"], item["name"]))
    return result


def _ensure_prompt_template_category_available(categories: list[dict[str, Any]], category_id: str) -> None:
    key = _clean_prompt_template_category(category_id).casefold()
    if any(category["id"].casefold() == key for category in categories):
        raise ValueError("Prompt template category already exists")


def _next_prompt_template_category_order(categories: list[dict[str, Any]]) -> int:
    if not categories:
        return 10
    return max(int(category.get("order") or 0) for category in categories) + 10


def _prompt_template_category_order(categories: list[dict[str, Any]], category_id: str) -> int:
    clean_id = _clean_prompt_template_category(category_id)
    for category in categories:
        if category["id"] == clean_id:
            return int(category.get("order") or 10)
    return _next_prompt_template_category_order(categories)


def _clean_prompt_template_tags(value: Any) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError("Prompt template tags must be an array")
    tags: list[str] = []
    seen: set[str] = set()
    for raw in value[:MAX_PROMPT_TEMPLATE_TAGS]:
        tag = str(raw or "").strip()[:MAX_PROMPT_TEMPLATE_TAG_LENGTH]
        key = tag.casefold()
        if tag and key not in seen:
            seen.add(key)
            tags.append(tag)
    return tags


def _clean_prompt_template_mode(value: Any) -> str:
    mode = str(value or "any").strip()
    if mode not in PROMPT_TEMPLATE_MODES:
        raise ValueError("Unsupported prompt template mode")
    return mode


def _clean_prompt_template_model_hint(value: Any) -> str:
    model_hint = str(value or DEFAULT_IMAGE_MODEL).strip()
    if model_hint not in SUPPORTED_PROMPT_TEMPLATE_MODEL_HINTS:
        raise ValueError("Unsupported prompt template model hint")
    return model_hint


def _clean_prompt_template_notes(value: Any) -> str:
    return str(value or "").strip()[:MAX_PROMPT_TEMPLATE_NOTES_LENGTH]


def _clean_prompt_template_thumbnail_url(value: Any) -> str:
    text = str(value or "").strip()[:MAX_PROMPT_TEMPLATE_THUMBNAIL_URL_LENGTH]
    if not text:
        return ""
    parsed = urlsplit(text)
    if parsed.scheme and parsed.scheme not in {"http", "https"}:
        raise ValueError("Unsupported prompt template thumbnail URL")
    if text.lower().startswith(("javascript:", "data:")):
        raise ValueError("Unsupported prompt template thumbnail URL")
    return text


def _clean_prompt_template_usage_count(value: Any) -> int:
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return 0


def _extract_prompt_template_variables(content: str) -> list[str]:
    variables: list[str] = []
    seen: set[str] = set()
    for match in re.finditer(r"\{\{\s*([^{}\s][^{}]{0,40}?)\s*\}\}", content):
        name = match.group(1).strip()
        key = name.casefold()
        if name and key not in seen:
            seen.add(key)
            variables.append(name)
    return variables


def _parse_prompt_template_import(filename: str, payload: bytes, content_type: str | None = None) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if len(payload) > MAX_PROMPT_TEMPLATE_IMPORT_BYTES:
        raise ValueError("Prompt template pack is too large")
    text = payload.decode("utf-8-sig", errors="replace")
    suffix = Path(filename or "").suffix.lower()
    content_type = (content_type or "").lower()
    if suffix in {".md", ".markdown"} or "markdown" in content_type:
        return _parse_prompt_template_markdown_import(filename, text)
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return _parse_prompt_template_markdown_import(filename, text)
    return _parse_prompt_template_json_import(filename, parsed)


def _parse_prompt_template_json_import(filename: str, payload: Any) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    raw_categories: list[Any] = []
    raw_records: Any
    if isinstance(payload, list):
        raw_records = payload
    elif isinstance(payload, dict):
        raw_categories = payload.get("categories") if isinstance(payload.get("categories"), list) else []
        raw_records = (
            payload.get("templates")
            or payload.get("prompts")
            or payload.get("items")
            or payload.get("data")
            or []
        )
    else:
        raise ValueError("Prompt template pack must be JSON object, JSON array, or Markdown")
    if not isinstance(raw_records, list):
        raise ValueError("Prompt template pack records must be an array")
    categories = _normalize_prompt_template_categories_payload(raw_categories)
    templates = [
        item
        for item in (_prompt_template_payload_from_community_record(record, filename=filename) for record in raw_records)
        if item is not None
    ]
    return categories, templates


def _prompt_template_payload_from_community_record(record: Any, *, filename: str) -> dict[str, Any] | None:
    if isinstance(record, str):
        content = record.strip()
        if not content:
            return None
        return {
            "title": _prompt_template_title_from_content(filename, content),
            "short_title": _prompt_template_title_from_content(filename, content)[:MAX_PROMPT_TEMPLATE_SHORT_TITLE_LENGTH],
            "content": content,
            "category": "常用",
            "tags": [],
            "mode": "any",
            "model_hint": DEFAULT_IMAGE_MODEL,
            "notes": "",
            "thumbnail_url": "",
            "favorite": False,
        }
    if not isinstance(record, dict):
        return None
    content = _first_prompt_template_text(
        record,
        ["content", "prompt", "text", "template", "positive_prompt", "positive", "body"],
    )
    if not content:
        return None
    title = _first_prompt_template_text(record, ["title", "name", "label", "short_title", "shortTitle"]) or _prompt_template_title_from_content(filename, content)
    category = _first_prompt_template_text(record, ["category", "group", "folder", "type"]) or "常用"
    return {
        "title": title,
        "short_title": _first_prompt_template_text(record, ["short_title", "shortTitle", "alias"]) or title[:MAX_PROMPT_TEMPLATE_SHORT_TITLE_LENGTH],
        "content": content,
        "category": category,
        "tags": _prompt_template_tags_from_import(record.get("tags") or record.get("keywords")),
        "mode": _prompt_template_mode_from_import(record.get("mode") or record.get("workflow")),
        "model_hint": DEFAULT_IMAGE_MODEL,
        "notes": _first_prompt_template_text(record, ["notes", "description", "desc", "comment"]),
        "thumbnail_url": _first_prompt_template_text(record, ["thumbnail_url", "thumbnail", "preview_url", "preview", "cover", "image"]),
        "favorite": bool(record.get("favorite")),
    }


def _parse_prompt_template_markdown_import(filename: str, text: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    headings = list(re.finditer(r"(?m)^(#{1,3})\s+(.+?)\s*$", text))
    if not headings:
        content = text.strip()
        if not content:
            return _normalize_prompt_template_categories_payload([]), []
        return _normalize_prompt_template_categories_payload([]), [
            {
                "title": _prompt_template_title_from_content(filename, content),
                "content": _markdown_prompt_content(content),
                "category": "常用",
                "tags": [],
                "mode": "any",
                "model_hint": DEFAULT_IMAGE_MODEL,
                "notes": "",
                "thumbnail_url": "",
                "favorite": False,
            }
        ]
    templates: list[dict[str, Any]] = []
    categories: list[dict[str, Any]] = []
    for index, heading in enumerate(headings):
        title = heading.group(2).strip()
        body_start = heading.end()
        body_end = headings[index + 1].start() if index + 1 < len(headings) else len(text)
        body = text[body_start:body_end].strip()
        metadata, content_source = _markdown_prompt_template_metadata(body)
        content = _markdown_prompt_content(content_source)
        if not content:
            continue
        category = metadata.get("category") or "常用"
        categories.append({"id": category, "name": category, "order": (len(categories) + 1) * 10})
        templates.append(
            {
                "title": title,
                "short_title": metadata.get("short") or title[:MAX_PROMPT_TEMPLATE_SHORT_TITLE_LENGTH],
                "content": content,
                "category": category,
                "tags": _prompt_template_tags_from_import(metadata.get("tags", "")),
                "mode": "any",
                "model_hint": DEFAULT_IMAGE_MODEL,
                "notes": metadata.get("notes", ""),
                "thumbnail_url": metadata.get("thumbnail", ""),
                "favorite": False,
            }
        )
    return _normalize_prompt_template_categories_payload(categories), templates


def _markdown_prompt_template_metadata(body: str) -> tuple[dict[str, str], str]:
    metadata: dict[str, str] = {}
    content_lines: list[str] = []
    metadata_keys = {
        "category": "category",
        "分类": "category",
        "tags": "tags",
        "tag": "tags",
        "标签": "tags",
        "thumbnail": "thumbnail",
        "thumbnail_url": "thumbnail",
        "preview": "thumbnail",
        "notes": "notes",
        "备注": "notes",
        "short": "short",
        "short_title": "short",
    }
    for line in body.splitlines():
        match = re.match(r"^\s*([A-Za-z_\-\u4e00-\u9fff]+)\s*[:：]\s*(.+?)\s*$", line)
        if match and match.group(1).strip().lower() in metadata_keys and not content_lines:
            metadata[metadata_keys[match.group(1).strip().lower()]] = match.group(2).strip()
            continue
        content_lines.append(line)
    return metadata, "\n".join(content_lines).strip()


def _markdown_prompt_content(text: str) -> str:
    blocks = re.findall(r"```(?:prompt|text|txt)?\s*\n([\s\S]*?)```", text, flags=re.IGNORECASE)
    if blocks:
        return "\n\n".join(block.strip() for block in blocks if block.strip()).strip()
    return text.strip()


def _first_prompt_template_text(record: dict[str, Any], keys: list[str]) -> str:
    for key in keys:
        value = record.get(key)
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return ""


def _prompt_template_title_from_content(filename: str, content: str) -> str:
    stem = Path(filename or "").stem.strip()
    if stem and stem not in {"pack", "prompts", "community-pack"}:
        return stem[:MAX_PROMPT_TEMPLATE_TITLE_LENGTH]
    first_line = re.sub(r"\s+", " ", content).strip()
    return (first_line[:MAX_PROMPT_TEMPLATE_TITLE_LENGTH] or "导入模板").strip()


def _prompt_template_tags_from_import(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        raw_tags = value
    else:
        raw_tags = re.split(r"[,，#\n]+", str(value))
    return _clean_prompt_template_tags([str(tag).strip() for tag in raw_tags if str(tag).strip()])


def _prompt_template_mode_from_import(value: Any) -> str:
    mode = str(value or "any").strip()
    return mode if mode in PROMPT_TEMPLATE_MODES else "any"

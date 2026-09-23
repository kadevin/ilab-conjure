from __future__ import annotations

from typing import Any

from fastapi import Body, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response

from codex_image.webui.context import WebUIContext
from codex_image.webui.image_uploads import (
    InvalidRasterImage,
    SUPPORTED_RASTER_MIME_TYPES,
    read_validated_raster_upload,
)
from codex_image.webui.reference_assets import (
    ReferenceAssetInUseError,
    ReferenceAssetProtectionUnavailableError,
)
from codex_image.webui.storage import _guess_mime_type
from codex_image.webui.task_metadata import _gallery_category_response, _gallery_item_response, _reference_asset_response


def register_gallery_routes(app: FastAPI, ctx: WebUIContext) -> None:
    @app.get("/api/gallery")
    def list_gallery(category: str | None = None) -> dict[str, Any]:
        try:
            items = ctx.gallery_storage.list_items(category=category)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {
            "items": [_gallery_item_response(item) for item in items],
            "categories": [_gallery_category_response(category) for category in ctx.gallery_storage.list_categories()],
        }

    @app.get("/api/gallery/categories")
    def list_gallery_categories() -> dict[str, Any]:
        return {"categories": [_gallery_category_response(category) for category in ctx.gallery_storage.list_categories()]}

    @app.post("/api/gallery/categories")
    def create_gallery_category(payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
        try:
            category = ctx.gallery_storage.create_category(
                name=str(payload["name"]),
                prompt_role=str(payload["prompt_role"]) if "prompt_role" in payload else None,
                order=int(payload["order"]) if "order" in payload and payload["order"] is not None else None,
            )
        except (KeyError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"category": _gallery_category_response(category)}

    @app.patch("/api/gallery/categories/reorder")
    def reorder_gallery_categories(payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
        try:
            categories = ctx.gallery_storage.reorder_categories(list(payload["category_ids"]))
        except (KeyError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"categories": [_gallery_category_response(category) for category in categories]}

    @app.patch("/api/gallery/categories/{category_id}")
    def update_gallery_category(category_id: str, payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
        try:
            category = ctx.gallery_storage.update_category(
                category_id,
                name=str(payload["name"]) if "name" in payload else None,
                prompt_role=str(payload["prompt_role"]) if "prompt_role" in payload else None,
                order=int(payload["order"]) if "order" in payload and payload["order"] is not None else None,
            )
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail="Gallery category not found") from exc
        except (KeyError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"category": _gallery_category_response(category)}

    @app.delete("/api/gallery/categories/{category_id}")
    def delete_gallery_category(category_id: str, move_to: str | None = None) -> dict[str, Any]:
        try:
            ctx.gallery_storage.delete_category(category_id, move_to=move_to)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail="Gallery category not found") from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"ok": True, "id": category_id}

    @app.post("/api/gallery")
    async def create_gallery_item(
        name: str = Form(...),
        category: str = Form(...),
        prompt_note: str | None = Form(None),
        image: UploadFile = File(...),
    ) -> dict[str, Any]:
        try:
            validated = await read_validated_raster_upload(image)
        except InvalidRasterImage as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        try:
            item = ctx.gallery_storage.create_item(
                name=name,
                category=category,
                filename=validated.filename,
                data=validated.data,
                content_type=validated.mime_type,
                prompt_note=prompt_note,
            )
        except FileExistsError as exc:
            raise HTTPException(status_code=409, detail="Gallery name already exists") from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"item": _gallery_item_response(item)}

    @app.patch("/api/gallery/reorder")
    def reorder_gallery_items(payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
        try:
            items = ctx.gallery_storage.reorder_items(str(payload["category"]), list(payload["item_ids"]))
        except (KeyError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"items": [_gallery_item_response(item) for item in items]}

    @app.patch("/api/gallery/{item_id}")
    def update_gallery_item(item_id: str, payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
        try:
            item = ctx.gallery_storage.update_item(
                item_id,
                name=str(payload["name"]) if "name" in payload else None,
                category=str(payload["category"]) if "category" in payload else None,
                prompt_note=str(payload["prompt_note"]) if "prompt_note" in payload else None,
                order=int(payload["order"]) if "order" in payload and payload["order"] is not None else None,
            )
        except FileExistsError as exc:
            raise HTTPException(status_code=409, detail="Gallery name already exists") from exc
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail="Gallery item not found") from exc
        except (KeyError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"item": _gallery_item_response(item)}

    @app.put("/api/gallery/{item_id}/image")
    async def replace_gallery_item_image(item_id: str, image: UploadFile = File(...)) -> dict[str, Any]:
        try:
            validated = await read_validated_raster_upload(image)
        except InvalidRasterImage as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        try:
            item = ctx.gallery_storage.replace_item_image(
                item_id,
                filename=validated.filename,
                data=validated.data,
                content_type=validated.mime_type,
            )
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail="Gallery item not found") from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"item": _gallery_item_response(item)}

    @app.delete("/api/gallery/{item_id}")
    def delete_gallery_item(item_id: str) -> dict[str, Any]:
        try:
            ctx.gallery_storage.delete_item(item_id)
        except (FileNotFoundError, ValueError) as exc:
            raise HTTPException(status_code=404, detail="Gallery item not found") from exc
        return {"ok": True, "id": item_id}

    @app.get("/api/gallery/{item_id}/image")
    def get_gallery_image(item_id: str) -> Response:
        try:
            item = ctx.gallery_storage.read_item(item_id)
            path = ctx.gallery_storage.image_path(item_id)
        except (FileNotFoundError, ValueError) as exc:
            raise HTTPException(status_code=404, detail="Gallery item not found") from exc
        mime_type = str(item.get("mime_type") or _guess_mime_type(path.name)).split(";", 1)[0].strip().lower()
        if mime_type not in SUPPORTED_RASTER_MIME_TYPES:
            raise HTTPException(status_code=415, detail="Unsupported media type")
        return FileResponse(
            path,
            media_type=mime_type,
            headers={"Cache-Control": "no-store"},
        )

    @app.get("/api/reference-assets/recent")
    def list_reference_assets(limit: int = 20) -> dict[str, Any]:
        clean_limit = max(0, min(int(limit), 50))
        try:
            reference_counts = ctx.reference_asset_storage.reference_counts()
        except Exception as exc:
            raise HTTPException(
                status_code=503,
                detail={
                    "code": "reference_asset_protection_unavailable",
                    "message": "Reference asset usage could not be checked.",
                },
            ) from exc
        items: list[dict[str, Any]] = []
        for item in ctx.reference_asset_storage.list_recent(limit=clean_limit):
            response = _reference_asset_response(item)
            reference_count = reference_counts.get(str(item.get("id") or ""), 0)
            response["reference_count"] = reference_count
            response["deletable"] = reference_count == 0
            items.append(response)
        return {"items": items}

    @app.post("/api/reference-assets/{asset_id}/hide")
    def hide_reference_asset(asset_id: str) -> dict[str, bool]:
        try:
            ctx.reference_asset_storage.hide_item(asset_id)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="Invalid reference asset id") from exc
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=f"Reference asset not found: {asset_id}") from exc
        return {"ok": True}

    @app.delete("/api/reference-assets/{asset_id}")
    def delete_reference_asset(asset_id: str) -> dict[str, bool]:
        try:
            ctx.reference_asset_storage.delete_item(asset_id)
        except ReferenceAssetInUseError as exc:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "reference_asset_in_use",
                    "message": "This reference asset is used by existing tasks.",
                    "reference_count": exc.reference_count,
                },
            ) from exc
        except ReferenceAssetProtectionUnavailableError as exc:
            raise HTTPException(
                status_code=503,
                detail={
                    "code": "reference_asset_protection_unavailable",
                    "message": "Reference asset usage could not be checked.",
                },
            ) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="Invalid reference asset id") from exc
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=f"Reference asset not found: {asset_id}") from exc
        return {"ok": True}

    @app.get("/api/reference-assets/{asset_id}/image")
    def get_reference_asset_image(asset_id: str) -> Response:
        try:
            item = ctx.reference_asset_storage.read_item(asset_id)
            path = ctx.reference_asset_storage.image_path(asset_id)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="Invalid reference asset id") from exc
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=f"Reference asset not found: {asset_id}") from exc
        mime_type = str(item.get("mime_type") or _guess_mime_type(path.name)).split(";", 1)[0].strip().lower()
        if mime_type not in SUPPORTED_RASTER_MIME_TYPES:
            raise HTTPException(status_code=415, detail="Unsupported media type")
        return FileResponse(path, media_type=mime_type)

    @app.get("/api/reference-assets/{asset_id}/thumbnail")
    def get_reference_asset_thumbnail(asset_id: str) -> Response:
        try:
            path = ctx.reference_asset_storage.thumbnail_path(asset_id)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="Invalid reference asset thumbnail") from exc
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=f"Reference asset not found: {asset_id}") from exc
        return FileResponse(path, media_type="image/webp", headers={"Cache-Control": "no-store"})

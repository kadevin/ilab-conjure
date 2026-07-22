from __future__ import annotations

from collections import deque
from threading import Condition
from typing import Any

from codex_image.client import ImageResult
from codex_image.generation.service import GenerationService
from codex_image.generation.types import GeneratedAsset, GenerationResult
from codex_image.providers.contracts import ExecutionPlan
from codex_image.providers.registry import ProviderRegistry, default_registry


class _LegacyClientAdapter:
    def __init__(self, client: Any) -> None:
        self.client = client

    def execute(self, plan: ExecutionPlan) -> GenerationResult:
        command = plan.command
        params = {**command.parameters, **command.legacy_compat_parameters}
        common: dict[str, Any] = {
            "prompt": command.prompt,
            "main_model": command.main_model,
            "model": plan.binding.remote_model_id,
            "size": params.get("canvas.size"),
            "quality": params.get("gpt.quality"),
            "background": params.get("gpt.background"),
            "output_format": params.get("output.format", "png"),
            "moderation": params.get("gpt.moderation"),
            "output_compression": params.get("gpt.output_compression"),
        }
        ephemeral_reference_files: list[Any] = []
        if plan.binding.protocol_profile.endswith("responses"):
            common["instructions"] = command.instructions
            common["web_search"] = bool(params.get("gpt.web_search"))
            ephemeral_reference_files = list(command.reference_files)
            common["reference_files"] = ephemeral_reference_files
        try:
            if command.operation == "edit":
                result = self.client.edit_image(
                    **common,
                    images=[image.data_url for image in command.image_inputs],
                    mask_image=command.mask_image,
                    input_fidelity=params.get("gpt.input_fidelity"),
                )
            else:
                result = self.client.generate_image(
                    **common,
                    reference_images=[image.data_url for image in command.image_inputs],
                )
        finally:
            ephemeral_reference_files.clear()
        return GenerationResult(
            assets=(GeneratedAsset(
                image_bytes=result.image_bytes,
                mime_type=f"image/{result.output_format or 'png'}",
                revised_prompt=result.revised_prompt,
                metadata={
                    "size": result.size,
                    "background": result.background,
                    "quality": result.quality,
                    "tool_usage": result.tool_usage,
                },
            ),),
            usage=dict(result.usage),
        )


class ExecutionPlanImageClient:
    """Compatibility-shaped executor backed by the reviewed GenerationService path."""

    def __init__(
        self,
        plan: ExecutionPlan,
        client: Any,
        *,
        registry: ProviderRegistry | None = None,
    ) -> None:
        self._plan = plan
        self._uses_legacy_client_adapter = plan.binding.parameter_codec.startswith("gpt_")
        if registry is None:
            base_registry = default_registry()
            protocol = (
                _LegacyClientAdapter(client)
                if self._uses_legacy_client_adapter
                else base_registry.protocol(plan.binding.protocol_profile)
            )
            registry = ProviderRegistry(
                protocols={plan.binding.protocol_profile: protocol},
                codecs={
                    plan.binding.parameter_codec: base_registry.codec(
                        plan.binding.parameter_codec
                    )
                },
            )
        self._registry = registry
        self._service = GenerationService(None, registry)  # resolver is not used for a frozen plan
        self._condition = Condition()
        self._pending_results: deque[ImageResult] = deque()
        self._request_in_flight = False
        self._failure: Exception | None = None
        self._failure_remaining = 0
        try:
            self._expected_outputs = max(
                1, int(plan.command.parameters.get("output.count") or 1)
            )
        except (TypeError, ValueError):
            self._expected_outputs = 1
        self.direct_images_concurrent = (
            plan.provider.id != "codex"
            or plan.binding.protocol_profile.endswith("images")
        )

    def generate_image(self, **kwargs: Any) -> ImageResult:
        return self._execute("generate", kwargs)

    def edit_image(self, **kwargs: Any) -> ImageResult:
        return self._execute("edit", kwargs)

    def _execute(self, operation: str, kwargs: dict[str, Any]) -> ImageResult:
        if operation != self._plan.command.operation:
            raise RuntimeError("Execution operation differs from the frozen generation plan.")
        if self._uses_legacy_client_adapter:
            result = self._service.execute_plan_once(self._plan)
            if not result.assets:
                raise RuntimeError("The provider returned no image asset.")
            return self._image_result(result, result.assets[0], kwargs)
        # The executor kwargs are legacy compatibility plumbing. The restored
        # snapshot plan is authoritative for all request choices and inputs.
        while True:
            with self._condition:
                if self._pending_results:
                    return self._pending_results.popleft()
                if self._failure is not None and self._failure_remaining > 0:
                    failure = self._failure
                    self._failure_remaining -= 1
                    if self._failure_remaining == 0:
                        self._failure = None
                    raise failure
                if not self._request_in_flight:
                    self._request_in_flight = True
                    break
                self._condition.wait()

        try:
            result = self._service.execute_plan_once(self._plan)
            if not result.assets:
                raise RuntimeError("The provider returned no image asset.")
            converted = [
                self._image_result(result, asset, kwargs) for asset in result.assets
            ]
        except Exception as exc:
            with self._condition:
                self._request_in_flight = False
                self._failure = exc
                self._failure_remaining = max(0, self._expected_outputs - 1)
                self._condition.notify_all()
            raise

        with self._condition:
            self._pending_results.extend(converted)
            self._request_in_flight = False
            image_result = self._pending_results.popleft()
            self._condition.notify_all()
            return image_result

    @staticmethod
    def _image_result(
        result: GenerationResult,
        asset: GeneratedAsset,
        kwargs: dict[str, Any],
    ) -> ImageResult:
        metadata = dict(asset.metadata)
        mime_type = str(asset.mime_type or "").split(";", 1)[0].strip().lower()
        asset_format = mime_type.split("/", 1)[1] if mime_type.startswith("image/") else ""
        if asset_format == "jpg":
            asset_format = "jpeg"
        output_format = str(
            asset_format
            or metadata.get("output_format")
            or metadata.get("format")
            or kwargs.get("output_format")
            or "png"
        )
        size = str(metadata.get("size") or kwargs.get("size") or "")
        if not size and asset.width is not None and asset.height is not None:
            size = f"{asset.width}x{asset.height}"
        tool_usage = dict(metadata.get("tool_usage") or {})
        if result.text_parts:
            tool_usage["text_parts"] = list(result.text_parts)
        if result.provider_metadata:
            tool_usage["provider_metadata"] = dict(result.provider_metadata)
        return ImageResult(
            asset.image_bytes,
            asset.revised_prompt,
            output_format,
            size,
            str(metadata.get("background") or kwargs.get("background") or "auto"),
            str(metadata.get("quality") or kwargs.get("quality") or "auto"),
            dict(result.usage),
            tool_usage,
        )


__all__ = ("ExecutionPlanImageClient",)

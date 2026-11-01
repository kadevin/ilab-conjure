from __future__ import annotations

import asyncio
from collections import deque
from dataclasses import replace
from threading import Condition
from typing import Any, Awaitable, Callable

from codex_image.client import ImageResult
from codex_image.generation.service import GenerationService
from codex_image.generation.types import GeneratedAsset, GenerationResult
from codex_image.generation.errors import GenerationTimeoutError
from codex_image.providers.contracts import ExecutionPlan
from codex_image.providers.registry import ProviderRegistry, default_registry
from codex_image.providers.result_assets import asset_load_failure
from codex_image.providers.transparency import transparency_request


class _LegacyClientAdapter:
    def __init__(self, client: Any) -> None:
        self.client = client

    def execute(self, plan: ExecutionPlan) -> GenerationResult:
        command = plan.command
        params = {**command.parameters, **command.legacy_compat_parameters}
        transparency = transparency_request(command, plan.binding)
        common: dict[str, Any] = {
            "prompt": transparency.prompt,
            "main_model": command.main_model,
            "model": plan.binding.remote_model_id,
            "size": params.get("canvas.size"),
            "quality": params.get("gpt.quality"),
            "background": transparency.background,
            "output_format": params.get("output.format", "png"),
            "moderation": params.get("gpt.moderation"),
            "output_compression": params.get("gpt.output_compression"),
        }
        ephemeral_reference_files: list[Any] = []
        if plan.binding.protocol_profile.endswith("responses"):
            common["instructions"] = transparency.instructions
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
        if self._uses_legacy_client_adapter:
            base_registry = registry or default_registry()
            registry = ProviderRegistry(
                protocols={
                    plan.binding.protocol_profile: _LegacyClientAdapter(client)
                },
                codecs={
                    plan.binding.parameter_codec: base_registry.codec(
                        plan.binding.parameter_codec
                    )
                },
            )
        elif registry is None:
            registry = default_registry()
        self._registry = registry
        self._service = GenerationService(None, registry)  # resolver is not used for a frozen plan
        self._condition = Condition()
        self._pending_results: deque[ImageResult | Exception] = deque()
        self._request_in_flight = False
        self._batch_lock = asyncio.Lock()
        self._batch_failure: BaseException | None = None
        self._delivered_outputs = 0
        self._output_slots: tuple[int, ...] = ()
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

    def prepare_output_count(self, count: int) -> None:
        """Set the pending slots before execution without changing the snapshot."""
        self._expected_outputs = count

    def prepare_output_slots(self, slots: list[int]) -> None:
        self.prepare_output_count(len(slots))
        self._output_slots = tuple(slots)
        if self._plan.progress is not None:
            self._plan.progress.output_slots = tuple(slots)

    def _take_pending_result(self) -> ImageResult:
        item = self._pending_results.popleft()
        self._delivered_outputs += 1
        if isinstance(item, Exception):
            raise item
        return item

    async def call_output(self, request: Callable[[], Awaitable[ImageResult]]) -> ImageResult:
        if self._uses_legacy_client_adapter:
            return await request()
        # Apply transport retries to the batch before distributing its outcome.
        # A cached terminal failure must not enter each slot's retry loop.
        async with self._batch_lock:
            with self._condition:
                if self._pending_results:
                    return self._take_pending_result()
            if self._batch_failure is not None:
                raise self._batch_failure
            try:
                result = await request()
            except BaseException as exc:
                self._batch_failure = exc
                if isinstance(exc, GenerationTimeoutError) and exc.partial_result is not None:
                    partial = exc.partial_result
                    with self._condition:
                        self._pending_results.clear()
                        self._pending_results.extend(
                            item if isinstance(item, Exception) else self._image_result(partial, item, {})
                            for item in partial.asset_outcomes
                        )
                        return self._take_pending_result()
                if asset_load_failure(exc) is None:
                    # A timed-out/cancelled batch may finish while its worker
                    # drains. Those late results must not reach waiting slots.
                    with self._condition:
                        self._pending_results.clear()
                raise
            attempts = getattr(result, "_image_request_attempts", 1)
            with self._condition:
                for pending in self._pending_results:
                    setattr(pending, "_image_request_attempts", attempts)
            return result

    def _plan_for_remaining_outputs(self) -> ExecutionPlan:
        if self._plan.progress is not None:
            self._plan.progress.output_slots = self._output_slots[self._delivered_outputs:]
        count = max(1, self._expected_outputs - self._delivered_outputs)
        if self._plan.command.parameters.get("output.count") == count:
            return self._plan
        command = replace(self._plan.command, parameters={
            **self._plan.command.parameters, "output.count": count,
        })
        request = self._registry.codec(self._plan.binding.parameter_codec).encode(
            command, self._plan.model, self._plan.binding,
        )
        return replace(self._plan, command=command, protocol_request=request)

    def _execute(self, operation: str, kwargs: dict[str, Any]) -> ImageResult:
        if operation != self._plan.command.operation:
            raise RuntimeError("Execution operation differs from the frozen generation plan.")
        if self._uses_legacy_client_adapter:
            result = self._service.execute_plan_once(self._plan)
            if not result.assets:
                raise RuntimeError("The provider returned no image asset.")
            return self._image_result(result, result.assets[0], kwargs)
        # The executor kwargs are legacy compatibility plumbing. The restored
        # snapshot plan keeps request choices and inputs; batch size is reduced
        # to the slots still needed by this execution.
        while True:
            with self._condition:
                if self._pending_results:
                    return self._take_pending_result()
                if self._batch_failure is not None:
                    raise self._batch_failure
                if not self._request_in_flight:
                    self._request_in_flight = True
                    break
                self._condition.wait()

        try:
            result = self._service.execute_plan_once(self._plan_for_remaining_outputs())
            if not result.assets and not result.asset_outcomes:
                raise RuntimeError("The provider returned no image asset.")
            converted = [
                item if isinstance(item, Exception) else self._image_result(result, item, kwargs)
                for item in (result.asset_outcomes or result.assets)
            ]
        except BaseException:
            with self._condition:
                self._request_in_flight = False
                self._condition.notify_all()
            raise

        with self._condition:
            self._pending_results.extend(converted)
            self._batch_failure = next((item for item in converted if isinstance(item, Exception)), None)
            self._request_in_flight = False
            self._condition.notify_all()
            return self._take_pending_result()

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

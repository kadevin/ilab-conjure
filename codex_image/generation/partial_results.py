"""Validated batch outcomes recovered while a timed-out request drains."""
from __future__ import annotations

from dataclasses import replace

from codex_image.http_connection import exception_chain
from .types import GeneratedAsset, GenerationResult


class PartialGenerationError(RuntimeError):
    def __init__(self, result: GenerationResult, completed_at: tuple[float, ...]) -> None:
        super().__init__("Batch interrupted after receiving partial image results")
        self.result = result
        self.completed_at = completed_at


def results_completed_before(exc: BaseException, deadline: float) -> GenerationResult | None:
    partial = next((item for item in exception_chain(exc) if isinstance(item, PartialGenerationError)), None)
    if partial is None:
        return None
    outcomes = tuple(item for item, finished in zip(partial.result.asset_outcomes, partial.completed_at)
                     if finished <= deadline)
    assets = tuple(item for item in outcomes if isinstance(item, GeneratedAsset))
    return replace(partial.result, assets=assets, asset_outcomes=outcomes) if assets else None

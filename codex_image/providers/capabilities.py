from __future__ import annotations

from dataclasses import dataclass

from .codecs.gpt_image import GPT_PARAMETER_IDS
from .codecs.gemini_image import GEMINI_PARAMETER_IDS


@dataclass(frozen=True)
class CodecCapability:
    codec_id: str
    protocol_profiles: frozenset[str]
    mapped_parameter_ids: frozenset[str]


_GEMINI_PARAMETERS = GEMINI_PARAMETER_IDS

CODEC_CAPABILITIES = {
    capability.codec_id: capability
    for capability in (
        CodecCapability("gpt_codex_images", frozenset({"codex_images"}), GPT_PARAMETER_IDS),
        CodecCapability("gpt_codex_responses", frozenset({"codex_responses"}), GPT_PARAMETER_IDS),
        CodecCapability("gpt_openai_images", frozenset({"openai_images"}), GPT_PARAMETER_IDS),
        CodecCapability("gpt_openai_responses", frozenset({"openai_responses"}), GPT_PARAMETER_IDS),
        CodecCapability(
            "gemini_interactions_image", frozenset({"gemini_interactions"}), _GEMINI_PARAMETERS
        ),
        CodecCapability(
            "gemini_generate_content_image",
            frozenset({"gemini_generate_content"}),
            _GEMINI_PARAMETERS,
        ),
        CodecCapability(
            "gemini_generate_content_image_config",
            frozenset({"gemini_generate_content", "gemini_change2pro_generate_content"}),
            _GEMINI_PARAMETERS,
        ),
        CodecCapability("gemini_openai_images", frozenset({"openai_images"}), _GEMINI_PARAMETERS),
        CodecCapability("gemini_t8_images", frozenset({"t8_images"}), _GEMINI_PARAMETERS),
        CodecCapability(
            "gemini_openrouter_images",
            frozenset({"openrouter_images"}),
            _GEMINI_PARAMETERS,
        ),
    )
}


def codec_capability(codec_id: str) -> CodecCapability:
    try:
        return CODEC_CAPABILITIES[codec_id]
    except KeyError as exc:
        raise ValueError(f"Unknown parameter codec: {codec_id}") from exc


def protocol_codec_pairs() -> frozenset[tuple[str, str]]:
    return frozenset(
        (profile, capability.codec_id)
        for capability in CODEC_CAPABILITIES.values()
        for profile in capability.protocol_profiles
    )


__all__ = ("CODEC_CAPABILITIES", "CodecCapability", "codec_capability", "protocol_codec_pairs")

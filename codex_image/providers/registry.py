from __future__ import annotations

from typing import Mapping

from .contracts import ParameterCodec, ProtocolAdapter


class ProviderRegistry:
    def __init__(
        self,
        *,
        protocols: Mapping[str, ProtocolAdapter],
        codecs: Mapping[str, ParameterCodec],
    ) -> None:
        self._protocols = dict(protocols)
        self._codecs = dict(codecs)

    def protocol(self, profile: str) -> ProtocolAdapter:
        try:
            return self._protocols[profile]
        except KeyError as exc:
            raise ValueError(f"Unknown protocol profile: {profile}") from exc

    def codec(self, codec_id: str) -> ParameterCodec:
        try:
            return self._codecs[codec_id]
        except KeyError as exc:
            raise ValueError(f"Unknown parameter codec: {codec_id}") from exc


def default_registry(
    *,
    codex_auth_state=None,
    codex_auth_provider=None,
    transport=None,
) -> ProviderRegistry:
    from .codex import CodexImagesAdapter, CodexResponsesAdapter
    from .codecs import (
        GeminiGenerateContentImageCodec,
        GeminiGenerateContentImageConfigCodec,
        GeminiOpenAIImagesCodec,
        GeminiOpenRouterImagesCodec,
        GeminiT8ImagesCodec,
        GptCodexImagesCodec,
        GptCodexResponsesCodec,
        GptOpenAIImagesCodec,
        GptOpenAIResponsesCodec,
    )
    from .gemini import Change2ProGeminiAdapter, GeminiGenerateContentAdapter
    from .openai import OpenAIImagesAdapter, OpenAIResponsesAdapter
    from .t8 import T8ImagesAdapter

    return ProviderRegistry(
        protocols={
            "codex_images": CodexImagesAdapter(
                auth_state=codex_auth_state,
                auth_provider=codex_auth_provider,
                transport=transport,
            ),
            "codex_responses": CodexResponsesAdapter(
                auth_state=codex_auth_state,
                auth_provider=codex_auth_provider,
                transport=transport,
            ),
            "openai_images": OpenAIImagesAdapter(transport=transport),
            "openai_responses": OpenAIResponsesAdapter(transport=transport),
            "gemini_generate_content": GeminiGenerateContentAdapter(transport=transport),
            "gemini_change2pro_generate_content": Change2ProGeminiAdapter(transport=transport),
            "t8_images": T8ImagesAdapter(transport=transport),
            "openrouter_images": OpenAIImagesAdapter(transport=transport),
        },
        codecs={
            "gpt_codex_images": GptCodexImagesCodec(),
            "gpt_codex_responses": GptCodexResponsesCodec(),
            "gpt_openai_images": GptOpenAIImagesCodec(),
            "gpt_openai_responses": GptOpenAIResponsesCodec(),
            "gemini_generate_content_image": GeminiGenerateContentImageCodec(),
            "gemini_generate_content_image_config": GeminiGenerateContentImageConfigCodec(),
            "gemini_openai_images": GeminiOpenAIImagesCodec(),
            "gemini_t8_images": GeminiT8ImagesCodec(),
            "gemini_openrouter_images": GeminiOpenRouterImagesCodec(),
        },
    )


__all__ = ("ProviderRegistry", "default_registry")

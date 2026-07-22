from __future__ import annotations

import base64
import json
import socket
import tempfile
import unittest
import urllib.error
from pathlib import Path
from typing import Any

from tests.helpers import FakeResponse, FakeTransport, make_sse_completed_event, write_auth_file


def _auth_state(*, access_token: str, account_id: str, refresh_token: str = "refresh-token"):
    from codex_image.auth import AuthState

    return AuthState(
        path=Path("/tmp/auth.json"),
        access_token=access_token,
        refresh_token=refresh_token,
        id_token="header.payload.sig",
        account_id=account_id,
        last_refresh=None,
        raw={},
    )


class FakeAuthProvider:
    def __init__(self, states: list[Any]) -> None:
        self.states = list(states)
        self.cursor = 0

    def has_auth(self) -> bool:
        return bool(self.states)

    def available_count(self) -> int:
        return len(self.states)

    def next_auth_state(self):
        state = self.states[self.cursor % len(self.states)]
        self.cursor += 1
        return state

    def next_auth_state_after_unauthorized(self, current_state):
        for _ in range(len(self.states)):
            candidate = self.next_auth_state()
            if candidate.account_id != current_state.account_id or candidate.access_token != current_state.access_token:
                return candidate
        return None


class ClientTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmpdir.cleanup)
        self.auth_path = Path(self.tmpdir.name) / "auth.json"

    def test_openai_base_url_preserves_explicit_root_and_known_paths(self) -> None:
        from codex_image.client_types import DEFAULT_OPENAI_API_BASE_URL, normalize_openai_base_url

        self.assertEqual(normalize_openai_base_url("https://api.example.com"), "https://api.example.com")
        self.assertEqual(normalize_openai_base_url("https://api.example.com/"), "https://api.example.com")
        self.assertEqual(normalize_openai_base_url("https://api.example.com/v1"), "https://api.example.com/v1")
        self.assertEqual(
            normalize_openai_base_url("https://api.example.com/v1/responses"),
            "https://api.example.com/v1",
        )
        self.assertEqual(normalize_openai_base_url(""), DEFAULT_OPENAI_API_BASE_URL)

    def test_urllib_transport_uses_configured_timeout(self) -> None:
        from unittest.mock import patch

        from codex_image.http import UrllibTransport

        captured: dict[str, object] = {}

        class FakeUrlopenResponse:
            status = 200

            @staticmethod
            def getcode() -> int:
                return 200

            @property
            def headers(self) -> dict[str, str]:
                return {"content-type": "text/plain"}

            def read(self) -> bytes:
                return b"ok"

            def __enter__(self) -> "FakeUrlopenResponse":
                return self

            def __exit__(self, *args: object) -> None:
                return None

        def fake_urlopen(
            request: object,
            timeout: float | None = None,
            context: object | None = None,
        ) -> FakeUrlopenResponse:
            captured["timeout"] = timeout
            captured["context"] = context
            return FakeUrlopenResponse()

        with patch("codex_image.http.request.urlopen", fake_urlopen):
            response = UrllibTransport(timeout=12.5).request(
                method="POST",
                url="https://example.test/responses",
                headers={},
                body=b"{}",
            )

        self.assertEqual(response.status, 200)
        self.assertEqual(response.body, b"ok")
        self.assertEqual(captured["timeout"], 12.5)
        self.assertIsNotNone(captured["context"])

    def test_urllib_transport_converts_socket_timeout_to_timeout_error(self) -> None:
        from unittest.mock import patch

        from codex_image.http import UrllibTransport

        def fake_urlopen(
            request: object,
            timeout: float | None = None,
            context: object | None = None,
        ) -> object:
            raise socket.timeout("timed out")

        with patch("codex_image.http.request.urlopen", fake_urlopen):
            with self.assertRaisesRegex(TimeoutError, r"timed out after [0-9.]+s \(timeout limit 1.5s\)"):
                UrllibTransport(timeout=1.5).request(
                    method="POST",
                    url="https://example.test/responses",
                    headers={},
                    body=b"{}",
                )

    def test_urllib_transport_converts_url_timeout_to_timeout_error(self) -> None:
        from unittest.mock import patch

        from codex_image.http import UrllibTransport

        def fake_urlopen(
            request: object,
            timeout: float | None = None,
            context: object | None = None,
        ) -> object:
            raise urllib.error.URLError(socket.timeout("read timed out"))

        with patch("codex_image.http.request.urlopen", fake_urlopen):
            with self.assertRaisesRegex(TimeoutError, r"timed out after [0-9.]+s \(timeout limit 2s\): read timed out"):
                UrllibTransport(timeout=2.0).request(
                    method="GET",
                    url="https://example.test/image.png",
                    headers={},
                    body=b"",
                )

    def test_generate_image_passes_size_and_decodes_image(self) -> None:
        write_auth_file(self.auth_path, access_token="token-1", account_id="acct-1")
        image_bytes = b"fake-png-data"
        transport = FakeTransport(
            [
                FakeResponse(
                    status=200,
                    body=make_sse_completed_event(
                        image_b64=base64.b64encode(image_bytes).decode("ascii"),
                        size="3840x2160",
                        quality="high",
                    ),
                    headers={"Content-Type": "text/event-stream"},
                )
            ]
        )

        from codex_image.auth import load_auth_state
        from codex_image.client import CodexImageClient

        client = CodexImageClient(load_auth_state(self.auth_path), transport=transport)
        result = client.generate_image(
            prompt="draw a mug",
            size="3840x2160",
            quality="high",
            output_format="png",
        )

        self.assertEqual(result.image_bytes, image_bytes)
        self.assertEqual(result.size, "3840x2160")
        self.assertEqual(result.output_format, "png")
        self.assertEqual(result.usage["total_tokens"], 3)

        request = transport.requests[0]
        payload = json.loads(request["body"].decode("utf-8"))
        self.assertEqual(payload["tools"][0]["type"], "image_generation")
        self.assertEqual(payload["tools"][0]["size"], "3840x2160")
        self.assertEqual(payload["tools"][0]["quality"], "high")
        self.assertEqual(request["headers"]["Authorization"], "Bearer token-1")
        self.assertEqual(request["headers"]["Chatgpt-Account-Id"], "acct-1")

    def test_codex_responses_payload_accepts_prompt_guard_instructions(self) -> None:
        write_auth_file(self.auth_path, access_token="token-guard", account_id="acct-guard")
        transport = FakeTransport(
            [
                FakeResponse(
                    status=200,
                    body=make_sse_completed_event(
                        image_b64=base64.b64encode(b"image").decode("ascii"),
                    ),
                    headers={"Content-Type": "text/event-stream"},
                )
            ]
        )

        from codex_image.auth import load_auth_state
        from codex_image.client import CodexImageClient

        client = CodexImageClient(load_auth_state(self.auth_path), transport=transport)
        client.generate_image(
            prompt="draw a mug",
            instructions="保留原意，不得删除硬性约束",
            size="1024x1024",
            quality="low",
        )

        payload = json.loads(transport.requests[0]["body"].decode("utf-8"))
        self.assertEqual(payload["instructions"], "保留原意，不得删除硬性约束")

    def test_codex_responses_payload_can_enable_web_search_before_image_generation(self) -> None:
        write_auth_file(self.auth_path, access_token="token-search", account_id="acct-search")
        transport = FakeTransport(
            [
                FakeResponse(
                    status=200,
                    body=make_sse_completed_event(
                        image_b64=base64.b64encode(b"image").decode("ascii"),
                        tool_usage={
                            "image_gen": {"input_tokens": 4, "output_tokens": 5, "total_tokens": 9},
                            "web_search": {"num_requests": 1},
                        },
                    ),
                    headers={"Content-Type": "text/event-stream"},
                )
            ]
        )

        from codex_image.auth import load_auth_state
        from codex_image.client import CodexImageClient

        client = CodexImageClient(load_auth_state(self.auth_path), transport=transport)
        result = client.generate_image(
            prompt="draw with current facts",
            instructions="原始提示词模式：\n调用图像生成工具时，必须逐字使用用户原始提示词。",
            size="1536x864",
            quality="low",
            web_search=True,
        )

        payload = json.loads(transport.requests[0]["body"].decode("utf-8"))
        self.assertEqual([tool["type"] for tool in payload["tools"]], ["web_search", "image_generation"])
        self.assertEqual(payload["tools"][0]["search_context_size"], "low")
        self.assertEqual(payload["tools"][1]["quality"], "low")
        self.assertEqual(payload["tool_choice"], "required")
        self.assertFalse(payload["parallel_tool_calls"])
        self.assertIn("必须逐字使用用户原始提示词", payload["instructions"])
        self.assertIn("First call web_search", payload["instructions"])
        self.assertIn("explicit exception to original or strict prompt-fidelity rules", payload["instructions"])
        self.assertIn("official or commonly used English title", payload["instructions"])
        self.assertEqual(result.usage, {"input_tokens": 4, "output_tokens": 5, "total_tokens": 9})
        self.assertEqual(result.tool_usage["web_search"], {"num_requests": 1})

    def test_codex_images_generations_posts_json_to_codex_images_endpoint(self) -> None:
        image_bytes = b"codex-image"
        transport = FakeTransport(
            [
                FakeResponse(
                    status=200,
                    body=json.dumps(
                        {
                            "data": [
                                {
                                    "b64_json": base64.b64encode(image_bytes).decode("ascii"),
                                    "size": "1024x1024",
                                    "quality": "low",
                                    "output_format": "png",
                                }
                            ],
                            "usage": {"total_tokens": 7},
                        }
                    ).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                )
            ]
        )

        from codex_image.client import CodexImagesImageClient

        client = CodexImagesImageClient(_auth_state(access_token="token-images", account_id="acct-images"), transport=transport)
        result = client.generate_image(
            prompt="draw a mug",
            size="1024x1024",
            quality="low",
            output_format="png",
        )

        self.assertEqual(result.image_bytes, image_bytes)
        self.assertEqual(result.size, "1024x1024")
        self.assertEqual(result.usage, {"total_tokens": 7})
        request = transport.requests[0]
        self.assertEqual(request["method"], "POST")
        self.assertEqual(request["url"], "https://chatgpt.com/backend-api/codex/images/generations")
        self.assertEqual(request["headers"]["Accept"], "application/json")
        self.assertEqual(request["headers"]["Content-Type"], "application/json")
        self.assertEqual(request["headers"]["Authorization"], "Bearer token-images")
        self.assertEqual(request["headers"]["Chatgpt-Account-Id"], "acct-images")
        payload = json.loads(request["body"].decode("utf-8"))
        self.assertEqual(payload["model"], "gpt-image-2")
        self.assertEqual(payload["prompt"], "draw a mug")
        self.assertEqual(payload["size"], "1024x1024")
        self.assertEqual(payload["quality"], "low")
        self.assertNotIn("endpoint", payload)
        self.assertNotIn("tools", payload)

    def test_codex_images_edits_posts_json_images_array_not_multipart(self) -> None:
        image_bytes = b"codex-edited"
        input_data_url = "data:image/png;base64," + base64.b64encode(b"input").decode("ascii")
        transport = FakeTransport(
            [
                FakeResponse(
                    status=200,
                    body=json.dumps(
                        {
                            "data": [
                                {
                                    "b64_json": base64.b64encode(image_bytes).decode("ascii"),
                                    "size": "1152x2048",
                                    "quality": "high",
                                    "output_format": "png",
                                }
                            ]
                        }
                    ).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                )
            ]
        )

        from codex_image.client import CodexImagesImageClient

        client = CodexImagesImageClient(_auth_state(access_token="token-edit", account_id="acct-edit"), transport=transport)
        result = client.edit_image(
            prompt="edit the image",
            images=[input_data_url],
            size="1152x2048",
            quality="high",
            output_format="png",
        )

        self.assertEqual(result.image_bytes, image_bytes)
        request = transport.requests[0]
        self.assertEqual(request["url"], "https://chatgpt.com/backend-api/codex/images/edits")
        self.assertEqual(request["headers"]["Content-Type"], "application/json")
        self.assertNotIn("multipart/form-data", request["headers"]["Content-Type"])
        payload = json.loads(request["body"].decode("utf-8"))
        self.assertEqual(payload["images"], [{"image_url": input_data_url}])
        self.assertEqual(payload["prompt"], "edit the image")
        self.assertEqual(payload["size"], "1152x2048")
        self.assertNotIn("endpoint", payload)

    def test_openai_images_client_posts_direct_image_generation_request(self) -> None:
        image_bytes = b"api-image-data"
        image_b64 = base64.b64encode(image_bytes).decode("ascii")
        transport = FakeTransport(
            [
                FakeResponse(
                    status=200,
                    body=json.dumps(
                        {
                            "data": [
                                {
                                    "b64_json": image_b64,
                                    "revised_prompt": "api revised prompt",
                                }
                            ],
                            "usage": {"total_tokens": 7},
                        }
                    ).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                )
            ]
        )

        from codex_image.client import OPENAI_COMPATIBLE_USER_AGENT, OpenAIImagesImageClient

        self.assertTrue(OPENAI_COMPATIBLE_USER_AGENT.startswith("iLab-CONJURE/"))

        client = OpenAIImagesImageClient(
            api_key="test-api-key-test-secret",
            base_url="https://api.example.com/v1",
            image_model="gpt-image-2",
            transport=transport,
        )
        result = client.generate_image(
            prompt="draw a mug",
            main_model="gpt-5.5",
            size="1024x1536",
            quality="low",
            background="opaque",
            output_format="webp",
            moderation="auto",
            output_compression=80,
        )

        self.assertEqual(result.image_bytes, image_bytes)
        self.assertEqual(result.revised_prompt, "api revised prompt")
        self.assertEqual(result.output_format, "webp")
        self.assertEqual(result.size, "1024x1536")
        self.assertEqual(result.quality, "low")
        self.assertEqual(result.background, "opaque")
        self.assertEqual(result.usage["total_tokens"], 7)

        request = transport.requests[0]
        payload = json.loads(request["body"].decode("utf-8"))
        self.assertEqual(request["url"], "https://api.example.com/v1/images/generations")
        self.assertEqual(request["headers"]["Authorization"], "Bearer test-api-key-test-secret")
        self.assertEqual(request["headers"]["User-Agent"], OPENAI_COMPATIBLE_USER_AGENT)
        self.assertEqual(payload["model"], "gpt-image-2")
        self.assertNotIn("main_model", payload)
        self.assertNotIn("stream", payload)
        self.assertEqual(payload["prompt"], "draw a mug")
        self.assertEqual(payload["size"], "1024x1536")
        self.assertEqual(payload["quality"], "low")
        self.assertEqual(payload["background"], "opaque")
        self.assertEqual(payload["output_format"], "webp")
        self.assertEqual(payload["output_compression"], 80)

    def test_openai_images_client_ignores_numeric_response_size_and_uses_image_dimensions(self) -> None:
        image_bytes = base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAIAAAADCAIAAAA2iEnWAAAAFElEQVR4nGNkZGJmYGBgYgADKAUAAMQADPiqQJgAAAAASUVORK5CYII="
        )
        body = json.dumps(
            {
                "data": [
                    {
                        "b64_json": base64.b64encode(image_bytes).decode("ascii"),
                        "size": str(len(image_bytes)),
                    }
                ]
            }
        ).encode("utf-8")

        from codex_image.client import OpenAIImagesImageClient

        result = OpenAIImagesImageClient.parse_response_json(
            body,
            request_payload={"size": "1024x1536", "output_format": "png"},
        )

        self.assertEqual(result.size, "2x3")

    def test_openai_images_client_can_request_and_parse_multiple_generated_images(self) -> None:
        first_b64 = base64.b64encode(b"api-image-1").decode("ascii")
        second_b64 = base64.b64encode(b"api-image-2").decode("ascii")
        transport = FakeTransport(
            [
                FakeResponse(
                    status=200,
                    body=json.dumps(
                        {
                            "data": [
                                {"b64_json": first_b64, "revised_prompt": "first prompt"},
                                {"b64_json": second_b64, "revised_prompt": "second prompt"},
                            ],
                            "usage": {"total_tokens": 14},
                        }
                    ).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                )
            ]
        )

        from codex_image.client import OpenAIImagesImageClient

        client = OpenAIImagesImageClient(
            api_key="test-api-key-test-secret",
            base_url="https://api.example.com/v1",
            image_model="gpt-image-2",
            transport=transport,
        )
        results = client.generate_images(
            prompt="draw two mugs",
            size="1024x1024",
            quality="low",
            output_format="png",
            n=2,
        )

        self.assertEqual([result.image_bytes for result in results], [b"api-image-1", b"api-image-2"])
        self.assertEqual([result.revised_prompt for result in results], ["first prompt", "second prompt"])
        self.assertEqual([result.usage for result in results], [{"total_tokens": 14}, {"total_tokens": 14}])

        payload = json.loads(transport.requests[0]["body"].decode("utf-8"))
        self.assertEqual(payload["n"], 2)

    def test_openai_responses_client_posts_api_key_responses_request_without_codex_headers(self) -> None:
        image_bytes = b"responses-image-data"
        image_b64 = base64.b64encode(image_bytes).decode("ascii")
        transport = FakeTransport(
            [
                FakeResponse(
                    status=200,
                    body=make_sse_completed_event(
                        image_b64=image_b64,
                        revised_prompt="responses revised prompt",
                        size="1024x1536",
                        quality="low",
                    ),
                    headers={"Content-Type": "text/event-stream"},
                )
            ]
        )

        from codex_image.client import OPENAI_COMPATIBLE_USER_AGENT, OpenAIResponsesImageClient

        client = OpenAIResponsesImageClient(
            api_key="test-api-key-responses-secret",
            base_url="https://api.example.com/v1",
            image_model="gpt-image-2",
            transport=transport,
        )
        result = client.generate_image(
            prompt="draw a mug through responses",
            main_model="gpt-5.5",
            size="1024x1536",
            quality="low",
            output_format="webp",
            moderation="auto",
            output_compression=80,
        )

        self.assertEqual(result.image_bytes, image_bytes)
        self.assertEqual(result.revised_prompt, "responses revised prompt")
        self.assertEqual(result.output_format, "png")
        self.assertEqual(result.size, "1024x1536")
        self.assertEqual(result.usage["total_tokens"], 3)

        request = transport.requests[0]
        payload = json.loads(request["body"].decode("utf-8"))
        self.assertEqual(request["url"], "https://api.example.com/v1/responses")
        self.assertEqual(request["headers"]["Authorization"], "Bearer test-api-key-responses-secret")
        self.assertEqual(request["headers"]["Accept"], "text/event-stream")
        self.assertEqual(request["headers"]["User-Agent"], OPENAI_COMPATIBLE_USER_AGENT)
        self.assertNotIn("Originator", request["headers"])
        self.assertNotIn("Chatgpt-Account-Id", request["headers"])
        self.assertNotIn("Session_id", request["headers"])
        self.assertNotIn("X-Client-Request-Id", request["headers"])
        self.assertNotIn("endpoint", payload)

    def test_openai_responses_payload_accepts_prompt_guard_instructions(self) -> None:
        transport = FakeTransport(
            [
                FakeResponse(
                    status=200,
                    body=make_sse_completed_event(image_b64=base64.b64encode(b"image").decode("ascii")),
                    headers={"Content-Type": "text/event-stream"},
                )
            ]
        )

        from codex_image.client import OpenAIResponsesImageClient

        client = OpenAIResponsesImageClient(
            api_key="test-api-key-responses-secret",
            base_url="https://api.example.com/v1",
            image_model="gpt-image-2",
            transport=transport,
        )
        client.generate_image(
            prompt="draw with guard",
            instructions="保留原意，不得删除硬性约束",
            size="1024x1024",
            quality="low",
        )

        payload = json.loads(transport.requests[0]["body"].decode("utf-8"))
        self.assertEqual(payload["instructions"], "保留原意，不得删除硬性约束")

    def test_openai_responses_client_uses_main_model_and_image_tool_model(self) -> None:
        transport = FakeTransport(
            [
                FakeResponse(
                    status=200,
                    body=make_sse_completed_event(image_b64=base64.b64encode(b"image").decode("ascii")),
                    headers={"Content-Type": "text/event-stream"},
                )
            ]
        )

        from codex_image.client import OpenAIResponsesImageClient

        client = OpenAIResponsesImageClient(
            api_key="test-api-key-responses-secret",
            base_url="https://api.example.com/v1",
            image_model="gpt-image-2",
            transport=transport,
        )
        client.generate_image(
            prompt="draw with main model",
            main_model="gpt-5.5",
            model="gpt-image-2",
            size="auto",
            quality="auto",
            output_format="png",
        )

        payload = json.loads(transport.requests[0]["body"].decode("utf-8"))
        self.assertEqual(payload["model"], "gpt-5.5")
        self.assertEqual(payload["tools"][0]["type"], "image_generation")
        self.assertEqual(payload["tools"][0]["model"], "gpt-image-2")
        self.assertEqual(payload["tools"][0]["action"], "generate")
        self.assertEqual(payload["tool_choice"], {"type": "image_generation"})

    def test_openai_responses_client_can_enable_web_search_tool(self) -> None:
        transport = FakeTransport(
            [
                FakeResponse(
                    status=200,
                    body=make_sse_completed_event(image_b64=base64.b64encode(b"image").decode("ascii")),
                    headers={"Content-Type": "text/event-stream"},
                )
            ]
        )

        from codex_image.client import OpenAIResponsesImageClient

        client = OpenAIResponsesImageClient(
            api_key="test-api-key-responses-secret",
            base_url="https://api.example.com/v1",
            image_model="gpt-image-2",
            transport=transport,
        )
        client.generate_image(
            prompt="draw with web context",
            main_model="gpt-5.5",
            model="gpt-image-2",
            size="1536x864",
            quality="low",
            output_format="png",
            web_search=True,
        )

        payload = json.loads(transport.requests[0]["body"].decode("utf-8"))
        self.assertEqual([tool["type"] for tool in payload["tools"]], ["web_search", "image_generation"])
        self.assertEqual(payload["tools"][1]["quality"], "low")
        self.assertEqual(payload["tool_choice"], "required")
        self.assertFalse(payload["parallel_tool_calls"])
        self.assertIn("First call web_search", payload["instructions"])
        self.assertIn("explicit exception to original or strict prompt-fidelity rules", payload["instructions"])

    def test_openai_responses_client_surfaces_missing_image_call_error(self) -> None:
        missing_image_event = {
            "type": "response.completed",
            "response": {
                "output": [
                    {
                        "type": "message",
                        "content": [{"type": "output_text", "text": "image tool did not return an image"}],
                    }
                ]
            },
        }
        transport = FakeTransport(
            [
                FakeResponse(
                    status=200,
                    body=f"data: {json.dumps(missing_image_event)}\n\n".encode("utf-8"),
                    headers={"Content-Type": "text/event-stream"},
                )
            ]
        )

        from codex_image.client import OpenAIResponsesImageClient

        client = OpenAIResponsesImageClient(
            api_key="test-api-key-responses-secret",
            base_url="https://api.example.com/v1",
            image_model="gpt-image-2",
            transport=transport,
        )
        with self.assertRaisesRegex(RuntimeError, "OpenAI-compatible responses image generation failed: image tool did not return an image"):
            client.generate_image(prompt="draw missing image", size="1024x1024", quality="low")

    def test_openai_responses_client_posts_edit_request_with_images_and_mask(self) -> None:
        image_b64 = base64.b64encode(b"responses-edited-image").decode("ascii")
        transport = FakeTransport(
            [
                FakeResponse(
                    status=200,
                    body=make_sse_completed_event(image_b64=image_b64, revised_prompt="responses edit revised"),
                    headers={"Content-Type": "text/event-stream"},
                )
            ]
        )

        from codex_image.client import OpenAIResponsesImageClient

        client = OpenAIResponsesImageClient(
            api_key="test-api-key-responses-edit-secret",
            base_url="https://api.example.com",
            image_model="gpt-image-2",
            transport=transport,
        )
        result = client.edit_image(
            prompt="edit through responses",
            images=["data:image/png;base64,aW1hZ2U="],
            mask_image="data:image/png;base64,bWFzaw==",
            main_model="gpt-5.4-mini",
            size="auto",
            quality="auto",
        )

        self.assertEqual(result.image_bytes, b"responses-edited-image")
        self.assertEqual(result.revised_prompt, "responses edit revised")

        payload = json.loads(transport.requests[0]["body"].decode("utf-8"))
        self.assertEqual(transport.requests[0]["url"], "https://api.example.com/responses")
        self.assertEqual(payload["model"], "gpt-5.4-mini")
        self.assertEqual(payload["tools"][0]["action"], "edit")
        self.assertEqual(payload["tools"][0]["input_image_mask"], {"image_url": "data:image/png;base64,bWFzaw=="})
        self.assertEqual(payload["input"][0]["content"][1], {"type": "input_image", "image_url": "data:image/png;base64,aW1hZ2U="})

    def test_openai_images_client_posts_direct_edit_request_with_input_images(self) -> None:
        image_b64 = base64.b64encode(b"edited-api-image").decode("ascii")
        transport = FakeTransport(
            [
                FakeResponse(
                    status=200,
                    body=json.dumps({"data": [{"b64_json": image_b64}]}).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                )
            ]
        )

        from codex_image.client import OpenAIImagesImageClient

        client = OpenAIImagesImageClient(
            api_key="test-api-key-edit-secret",
            base_url="https://api.example.com",
            image_model="gpt-image-2",
            transport=transport,
        )
        client.edit_image(
            prompt="edit the first image",
            images=["data:image/png;base64,aW1hZ2U="],
            main_model="gpt-5.4-mini",
            size="auto",
            quality="auto",
        )

        request = transport.requests[0]
        self.assertEqual(request["url"], "https://api.example.com/images/edits")
        self.assertIn("multipart/form-data", request["headers"]["Content-Type"])
        self.assertNotIn("gpt-5.4-mini", request["body"].decode("utf-8", errors="replace"))
        self.assertIn('name="model"', request["body"].decode("utf-8", errors="replace"))
        self.assertIn("gpt-image-2", request["body"].decode("utf-8", errors="replace"))
        self.assertIn('name="prompt"', request["body"].decode("utf-8", errors="replace"))
        self.assertIn("edit the first image", request["body"].decode("utf-8", errors="replace"))
        self.assertIn('name="image"; filename="image-1.png"', request["body"].decode("utf-8", errors="replace"))
        self.assertIn(b"image", request["body"])

    def test_openai_images_client_downloads_url_image_output(self) -> None:
        jpeg_bytes = b"\xff\xd8\xffdownloaded-jpeg"
        transport = FakeTransport(
            [
                FakeResponse(
                    status=200,
                    body=json.dumps(
                        {
                            "data": [
                                {
                                    "url": "https://cdn.example.com/generated.jpg",
                                    "revised_prompt": "url revised prompt",
                                }
                            ],
                            "usage": {"total_tokens": 9},
                        }
                    ).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                ),
                FakeResponse(
                    status=200,
                    body=jpeg_bytes,
                    headers={"Content-Type": "image/jpeg"},
                ),
            ]
        )

        from codex_image.client import OpenAIImagesImageClient

        client = OpenAIImagesImageClient(
            api_key="test-api-key-url-secret",
            base_url="https://api.example.com/v1",
            transport=transport,
        )
        result = client.generate_image(
            prompt="draw url output",
            size="1024x1536",
            quality="auto",
            output_format="jpeg",
        )

        self.assertEqual(result.image_bytes, jpeg_bytes)
        self.assertEqual(result.revised_prompt, "url revised prompt")
        self.assertEqual(result.output_format, "jpeg")
        self.assertEqual(result.usage["total_tokens"], 9)
        self.assertEqual(transport.requests[1]["method"], "GET")
        self.assertEqual(transport.requests[1]["url"], "https://cdn.example.com/generated.jpg")
        self.assertNotIn("Authorization", transport.requests[1]["headers"])

    def test_openai_images_client_retries_url_download_with_api_key_after_forbidden(self) -> None:
        jpeg_bytes = b"\xff\xd8\xffauthorized-jpeg"
        transport = FakeTransport(
            [
                FakeResponse(
                    status=200,
                    body=json.dumps({"data": [{"url": "https://api.example.com/file/generated.jpg"}]}).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                ),
                FakeResponse(status=403, body=b"forbidden", headers={"Content-Type": "text/plain"}),
                FakeResponse(status=200, body=jpeg_bytes, headers={"Content-Type": "image/jpeg"}),
            ]
        )

        from codex_image.client import OpenAIImagesImageClient

        client = OpenAIImagesImageClient(
            api_key="test-api-key-url-retry-secret",
            base_url="https://api.example.com/v1",
            transport=transport,
        )
        result = client.generate_image(prompt="draw authorized url", output_format="jpeg")

        self.assertEqual(result.image_bytes, jpeg_bytes)
        self.assertNotIn("Authorization", transport.requests[1]["headers"])
        self.assertEqual(transport.requests[2]["headers"]["Authorization"], "Bearer test-api-key-url-retry-secret")

    def test_openai_images_client_does_not_send_api_key_to_cross_origin_asset(self) -> None:
        transport = FakeTransport(
            [
                FakeResponse(
                    status=200,
                    body=json.dumps(
                        {"data": [{"url": "https://cdn.example.com/private/generated.jpg"}]}
                    ).encode("utf-8"),
                ),
                FakeResponse(status=403, body=b"forbidden", headers={"Content-Type": "text/plain"}),
            ]
        )

        from codex_image.client import OpenAIImagesImageClient

        client = OpenAIImagesImageClient(
            api_key="must-not-leak",
            base_url="https://api.example.com/v1",
            transport=transport,
        )
        with self.assertRaisesRegex(RuntimeError, "invalid image URL asset"):
            client.generate_image(prompt="draw private url")
        self.assertEqual(len(transport.requests), 2)
        self.assertNotIn("Authorization", transport.requests[1]["headers"])

    def test_openai_images_client_decodes_data_url_output(self) -> None:
        png_bytes = base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Y9Zya4AAAAASUVORK5CYII="
        )
        body = json.dumps(
            {
                "data": [
                    {
                        "url": "data:image/png;base64," + base64.b64encode(png_bytes).decode("ascii")
                    }
                ]
            }
        ).encode("utf-8")

        from codex_image.client import OpenAIImagesImageClient

        result = OpenAIImagesImageClient.parse_response_json(body)
        self.assertEqual(result.image_bytes, png_bytes)

    def test_openai_images_client_surfaces_http_and_missing_image_errors(self) -> None:
        from codex_image.client import OpenAIImagesImageClient

        failing = OpenAIImagesImageClient(
            api_key="test-api-key-fail",
            base_url="https://api.example.com/v1",
            transport=FakeTransport([FakeResponse(status=400, body=b'{"error":{"message":"bad request"}}')]),
        )
        with self.assertRaisesRegex(RuntimeError, "OpenAI-compatible images request failed: HTTP 400"):
            failing.generate_image(prompt="fail")

        missing_image = OpenAIImagesImageClient(
            api_key="test-api-key-missing",
            base_url="https://api.example.com/v1",
            transport=FakeTransport([FakeResponse(status=200, body=b'{"data": []}')]),
        )
        with self.assertRaisesRegex(RuntimeError, "completed without image data"):
            missing_image.generate_image(prompt="missing image")

    def test_generate_image_surfaces_sse_error_event(self) -> None:
        write_auth_file(self.auth_path, access_token="token-error", account_id="acct-error")
        error_event = {
            "type": "error",
            "error": {
                "type": "server_error",
                "code": "server_error",
                "message": "An error occurred while processing your request. Please include the request ID req-123.",
            },
        }
        transport = FakeTransport(
            [
                FakeResponse(
                    status=200,
                    body=f"data: {json.dumps(error_event)}\n\n".encode("utf-8"),
                    headers={"Content-Type": "text/event-stream"},
                )
            ]
        )

        from codex_image.auth import load_auth_state
        from codex_image.client import CodexImageClient

        client = CodexImageClient(load_auth_state(self.auth_path), transport=transport)
        with self.assertRaisesRegex(RuntimeError, "server_error.*request ID req-123"):
            client.generate_image(prompt="draw a failing image")

    def test_generate_image_writes_redacted_sse_debug_log(self) -> None:
        write_auth_file(self.auth_path, access_token="token-debug", account_id="acct-debug")
        image_b64 = base64.b64encode(b"debug-image").decode("ascii")
        transport = FakeTransport(
            [
                FakeResponse(
                    status=200,
                    body=make_sse_completed_event(
                        image_b64=image_b64,
                        revised_prompt="debug revised prompt",
                        size="2160x3840",
                    ),
                    headers={"Content-Type": "text/event-stream"},
                )
            ]
        )

        from codex_image.auth import load_auth_state
        from codex_image.client import CodexImageClient

        debug_path = Path(self.tmpdir.name) / "debug-sse.jsonl"
        client = CodexImageClient(load_auth_state(self.auth_path), transport=transport)
        client.generate_image(
            prompt="draw with debug",
            reference_images=["data:image/png;base64,input-image"],
            debug_sse_path=debug_path,
        )

        records = [json.loads(line) for line in debug_path.read_text(encoding="utf-8").splitlines()]
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["event"]["type"], "response.completed")
        image_call = records[0]["event"]["response"]["output"][0]
        self.assertEqual(image_call["revised_prompt"], "debug revised prompt")
        self.assertEqual(image_call["result"], f"<redacted image base64, {len(image_b64)} chars>")

        log_text = debug_path.read_text(encoding="utf-8")
        self.assertNotIn(image_b64, log_text)
        self.assertNotIn("input-image", log_text)

    def test_generate_image_writes_sse_debug_log_before_error(self) -> None:
        write_auth_file(self.auth_path, access_token="token-debug-error", account_id="acct-debug-error")
        error_event = {
            "type": "error",
            "error": {
                "type": "server_error",
                "code": "server_error",
                "message": "request failed. Please include the request ID debug-req.",
            },
        }
        transport = FakeTransport(
            [
                FakeResponse(
                    status=200,
                    body=f"data: {json.dumps(error_event)}\n\n".encode("utf-8"),
                    headers={"Content-Type": "text/event-stream"},
                )
            ]
        )

        from codex_image.auth import load_auth_state
        from codex_image.client import CodexImageClient

        debug_path = Path(self.tmpdir.name) / "debug-error-sse.jsonl"
        client = CodexImageClient(load_auth_state(self.auth_path), transport=transport)
        with self.assertRaisesRegex(RuntimeError, "debug-req"):
            client.generate_image(prompt="draw failing debug", debug_sse_path=debug_path)

        records = [json.loads(line) for line in debug_path.read_text(encoding="utf-8").splitlines()]
        self.assertEqual(records[0]["event"], error_event)

    def test_generate_image_surfaces_failed_image_call_message_text(self) -> None:
        write_auth_file(self.auth_path, access_token="token-refusal", account_id="acct-refusal")
        refusal = "抱歉，这个图像请求无法生成，因为其中包含可能被判定为性化呈现的姿态与人物参考组合。"
        events = [
            {
                "type": "response.output_item.done",
                "output_index": 0,
                "item": {
                    "id": "ig_test",
                    "type": "image_generation_call",
                    "status": "failed",
                },
            },
            {
                "type": "response.output_item.done",
                "output_index": 1,
                "item": {
                    "id": "msg_test",
                    "type": "message",
                    "role": "assistant",
                    "status": "completed",
                    "content": [
                        {
                            "type": "output_text",
                            "text": refusal,
                        }
                    ],
                },
            },
            {
                "type": "response.completed",
                "response": {
                    "status": "completed",
                    "output": [],
                },
            },
        ]
        body = "".join(f"data: {json.dumps(event, ensure_ascii=False)}\n\n" for event in events).encode("utf-8")
        transport = FakeTransport([FakeResponse(status=200, body=body, headers={"Content-Type": "text/event-stream"})])

        from codex_image.auth import load_auth_state
        from codex_image.client import CodexImageClient

        client = CodexImageClient(load_auth_state(self.auth_path), transport=transport)
        with self.assertRaises(RuntimeError) as raised:
            client.generate_image(prompt="draw a refused image")

        message = str(raised.exception)
        self.assertIn(refusal, message)
        self.assertNotIn("Codex completed without image_generation_call output", message)

    def test_generate_image_redacts_partial_image_debug_events(self) -> None:
        write_auth_file(self.auth_path, access_token="token-debug-partial", account_id="acct-debug-partial")
        partial_b64 = base64.b64encode(b"partial-image").decode("ascii")
        final_b64 = base64.b64encode(b"final-image").decode("ascii")
        partial_event = {
            "type": "response.image_generation_call.partial_image",
            "partial_image_b64": partial_b64,
        }
        body = f"data: {json.dumps(partial_event)}\n\n".encode("utf-8") + make_sse_completed_event(image_b64=final_b64)
        transport = FakeTransport([FakeResponse(status=200, body=body, headers={"Content-Type": "text/event-stream"})])

        from codex_image.auth import load_auth_state
        from codex_image.client import CodexImageClient

        debug_path = Path(self.tmpdir.name) / "debug-partial-sse.jsonl"
        client = CodexImageClient(load_auth_state(self.auth_path), transport=transport)
        client.generate_image(prompt="draw with partial debug", debug_sse_path=debug_path)

        records = [json.loads(line) for line in debug_path.read_text(encoding="utf-8").splitlines()]
        self.assertEqual(records[0]["event"]["partial_image_b64"], f"<redacted image base64, {len(partial_b64)} chars>")
        self.assertNotIn(partial_b64, debug_path.read_text(encoding="utf-8"))

    def test_sse_debug_log_redacts_unknown_long_base64_fields(self) -> None:
        from codex_image.client import CodexImageClient

        long_b64 = base64.b64encode(b"x" * 512).decode("ascii")
        redacted = CodexImageClient._redact_debug_value({"new_image_field": long_b64})

        self.assertEqual(redacted["new_image_field"], f"<redacted probable base64, {len(long_b64)} chars>")

    def test_generate_image_refreshes_token_after_401(self) -> None:
        write_auth_file(self.auth_path, access_token="expired-token", refresh_token="refresh-me", account_id="acct-old")
        refreshed_token_response = json.dumps(
            {
                "access_token": "fresh-token",
                "refresh_token": "fresh-refresh",
                "id_token": "header.eyJodHRwczovL2FwaS5vcGVuYWkuY29tL2F1dGgiOnsiY2hhdGdwdF9hY2NvdW50X2lkIjoiYWNjdC1uZXcifX0.sig",
                "expires_in": 3600,
                "token_type": "Bearer",
            }
        ).encode("utf-8")
        final_image = base64.b64encode(b"ok-image").decode("ascii")
        transport = FakeTransport(
            [
                FakeResponse(status=401, body=b'{"error":"expired"}', headers={"Content-Type": "application/json"}),
                FakeResponse(status=200, body=refreshed_token_response, headers={"Content-Type": "application/json"}),
                FakeResponse(status=200, body=make_sse_completed_event(image_b64=final_image), headers={"Content-Type": "text/event-stream"}),
            ]
        )

        from codex_image.auth import load_auth_state
        from codex_image.client import CodexImageClient

        client = CodexImageClient(load_auth_state(self.auth_path), transport=transport)
        result = client.generate_image(prompt="draw after refresh")

        self.assertEqual(result.image_bytes, b"ok-image")
        self.assertEqual(len(transport.requests), 3)
        self.assertTrue(transport.requests[1]["url"].endswith("/oauth/token"))
        self.assertEqual(transport.requests[2]["headers"]["Authorization"], "Bearer fresh-token")

    def test_generate_image_with_auth_provider_rotates_after_401_without_oauth_refresh(self) -> None:
        final_image = base64.b64encode(b"provider-ok").decode("ascii")
        transport = FakeTransport(
            [
                FakeResponse(status=401, body=b'{"error":"expired"}', headers={"Content-Type": "application/json"}),
                FakeResponse(status=200, body=make_sse_completed_event(image_b64=final_image), headers={"Content-Type": "text/event-stream"}),
            ]
        )

        from codex_image.client import CodexImageClient

        provider = FakeAuthProvider(
            [
                _auth_state(access_token="expired-access", account_id="acct-old", refresh_token="must-not-refresh"),
                _auth_state(access_token="fresh-access", account_id="acct-new", refresh_token="must-not-refresh"),
            ]
        )
        client = CodexImageClient(auth_provider=provider, transport=transport)
        result = client.generate_image(prompt="draw with provider")

        self.assertEqual(result.image_bytes, b"provider-ok")
        self.assertEqual(len(transport.requests), 2)
        self.assertEqual(transport.requests[0]["headers"]["Authorization"], "Bearer expired-access")
        self.assertEqual(transport.requests[0]["headers"]["Chatgpt-Account-Id"], "acct-old")
        self.assertEqual(transport.requests[1]["headers"]["Authorization"], "Bearer fresh-access")
        self.assertEqual(transport.requests[1]["headers"]["Chatgpt-Account-Id"], "acct-new")
        self.assertFalse(any(request["url"].endswith("/oauth/token") for request in transport.requests))

    def test_generate_image_with_auth_provider_rotates_after_usage_limit(self) -> None:
        final_image = base64.b64encode(b"provider-quota-ok").decode("ascii")
        usage_limit = {
            "error": {
                "type": "usage_limit_reached",
                "message": "The usage limit has been reached",
                "plan_type": "plus",
                "resets_in_seconds": 32593,
            }
        }
        transport = FakeTransport(
            [
                FakeResponse(status=429, body=json.dumps(usage_limit).encode("utf-8"), headers={"Content-Type": "application/json"}),
                FakeResponse(status=200, body=make_sse_completed_event(image_b64=final_image), headers={"Content-Type": "text/event-stream"}),
            ]
        )

        from codex_image.client import CodexImageClient

        provider = FakeAuthProvider(
            [
                _auth_state(access_token="limited-access", account_id="acct-limited", refresh_token="must-not-refresh"),
                _auth_state(access_token="available-access", account_id="acct-available", refresh_token="must-not-refresh"),
            ]
        )
        client = CodexImageClient(auth_provider=provider, transport=transport)
        result = client.generate_image(prompt="draw after quota")

        self.assertEqual(result.image_bytes, b"provider-quota-ok")
        self.assertEqual(len(transport.requests), 2)
        self.assertEqual(transport.requests[0]["headers"]["Authorization"], "Bearer limited-access")
        self.assertEqual(transport.requests[0]["headers"]["Chatgpt-Account-Id"], "acct-limited")
        self.assertEqual(transport.requests[1]["headers"]["Authorization"], "Bearer available-access")
        self.assertEqual(transport.requests[1]["headers"]["Chatgpt-Account-Id"], "acct-available")

    def test_generate_image_formats_usage_limit_without_raw_json(self) -> None:
        write_auth_file(self.auth_path, access_token="limited-token", account_id="acct-limited")
        usage_limit = {
            "error": {
                "type": "usage_limit_reached",
                "message": "The usage limit has been reached",
                "resets_in_seconds": 32593,
            }
        }
        transport = FakeTransport(
            [
                FakeResponse(status=429, body=json.dumps(usage_limit).encode("utf-8"), headers={"Content-Type": "application/json"}),
            ]
        )

        from codex_image.auth import load_auth_state
        from codex_image.client import CodexImageClient

        client = CodexImageClient(load_auth_state(self.auth_path), transport=transport)
        with self.assertRaises(RuntimeError) as caught:
            client.generate_image(prompt="draw limited")
        message = str(caught.exception)
        self.assertRegex(message, r"Codex usage limit reached: The usage limit has been reached")
        self.assertNotIn('{"error"', message)
        self.assertIn("resets in", message)

    def test_generate_image_with_reference_images_includes_input_images(self) -> None:
        write_auth_file(self.auth_path, access_token="token-ref", account_id="acct-ref")
        transport = FakeTransport(
            [
                FakeResponse(
                    status=200,
                    body=make_sse_completed_event(image_b64=base64.b64encode(b"ref-image").decode("ascii")),
                    headers={"Content-Type": "text/event-stream"},
                )
            ]
        )

        from codex_image.auth import load_auth_state
        from codex_image.client import CodexImageClient

        client = CodexImageClient(load_auth_state(self.auth_path), transport=transport)
        result = client.generate_image(
            prompt="use references",
            reference_images=["data:image/png;base64,aaa", "data:image/png;base64,bbb"],
        )

        self.assertEqual(result.image_bytes, b"ref-image")
        payload = json.loads(transport.requests[0]["body"].decode("utf-8"))
        content = payload["input"][0]["content"]
        self.assertEqual(content[1]["type"], "input_image")
        self.assertEqual(content[1]["image_url"], "data:image/png;base64,aaa")
        self.assertEqual(content[2]["image_url"], "data:image/png;base64,bbb")

    def test_generate_image_can_override_main_model(self) -> None:
        write_auth_file(self.auth_path, access_token="token-main-model", account_id="acct-main-model")
        transport = FakeTransport(
            [
                FakeResponse(
                    status=200,
                    body=make_sse_completed_event(image_b64=base64.b64encode(b"main-model-image").decode("ascii")),
                    headers={"Content-Type": "text/event-stream"},
                )
            ]
        )

        from codex_image.auth import load_auth_state
        from codex_image.client import CodexImageClient

        client = CodexImageClient(load_auth_state(self.auth_path), transport=transport)
        client.generate_image(prompt="draw with custom main model", main_model="gpt-5.4")

        payload = json.loads(transport.requests[0]["body"].decode("utf-8"))
        self.assertEqual(payload["model"], "gpt-5.4")
        self.assertEqual(payload["tools"][0]["model"], "gpt-image-2")

    def test_edit_image_uses_edit_action_and_mask_without_gpt_image_2_input_fidelity(self) -> None:
        write_auth_file(self.auth_path, access_token="token-edit", account_id="acct-edit")
        transport = FakeTransport(
            [
                FakeResponse(
                    status=200,
                    body=make_sse_completed_event(image_b64=base64.b64encode(b"edited-image").decode("ascii")),
                    headers={"Content-Type": "text/event-stream"},
                )
            ]
        )

        from codex_image.auth import load_auth_state
        from codex_image.client import CodexImageClient

        client = CodexImageClient(load_auth_state(self.auth_path), transport=transport)
        result = client.edit_image(
            prompt="change only background",
            images=["data:image/png;base64,input1"],
            mask_image="data:image/png;base64,mask1",
            size="1536x1024",
            input_fidelity="high",
        )

        self.assertEqual(result.image_bytes, b"edited-image")
        payload = json.loads(transport.requests[0]["body"].decode("utf-8"))
        self.assertEqual(payload["tools"][0]["action"], "edit")
        self.assertEqual(payload["tools"][0]["input_image_mask"]["image_url"], "data:image/png;base64,mask1")
        self.assertNotIn("input_fidelity", payload["tools"][0])
        self.assertEqual(payload["input"][0]["content"][1]["image_url"], "data:image/png;base64,input1")

    def test_edit_image_passes_input_fidelity_for_models_that_support_it(self) -> None:
        write_auth_file(self.auth_path, access_token="token-edit-fidelity", account_id="acct-edit-fidelity")
        transport = FakeTransport(
            [
                FakeResponse(
                    status=200,
                    body=make_sse_completed_event(image_b64=base64.b64encode(b"edited-image").decode("ascii")),
                    headers={"Content-Type": "text/event-stream"},
                )
            ]
        )

        from codex_image.auth import load_auth_state
        from codex_image.client import CodexImageClient

        client = CodexImageClient(load_auth_state(self.auth_path), transport=transport)
        client.edit_image(
            prompt="change only background",
            images=["data:image/png;base64,input1"],
            model="gpt-image-1.5",
            input_fidelity="high",
        )

        payload = json.loads(transport.requests[0]["body"].decode("utf-8"))
        self.assertEqual(payload["tools"][0]["model"], "gpt-image-1.5")
        self.assertEqual(payload["tools"][0]["input_fidelity"], "high")


if __name__ == "__main__":
    unittest.main()

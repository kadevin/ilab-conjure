from __future__ import annotations

import base64
from io import BytesIO
import unittest
from unittest.mock import Mock, patch

from PIL import Image


class ResultAssetTests(unittest.TestCase):
    @staticmethod
    def _image_bytes(
        image_format: str = "PNG",
        *,
        size: tuple[int, int] = (4, 3),
    ) -> bytes:
        buffer = BytesIO()
        Image.new("RGB", size, "white").save(buffer, format=image_format)
        return buffer.getvalue()

    @staticmethod
    def _gif_bytes(*, frames: int) -> bytes:
        images = [
            Image.new("RGB", (2, 2), (index % 255, 20, 40))
            for index in range(frames)
        ]
        buffer = BytesIO()
        images[0].save(
            buffer,
            format="GIF",
            save_all=True,
            append_images=images[1:],
            duration=10,
            loop=0,
        )
        return buffer.getvalue()

    def test_base64_and_data_url_results_use_decoded_raster_mime_and_dimensions(self) -> None:
        from codex_image.providers.result_assets import load_response_asset

        png = self._image_bytes()
        encoded = base64.b64encode(png).decode("ascii")

        bare = load_response_asset({"b64_json": encoded})
        data_url = load_response_asset(
            {"url": f"data:image/png;base64,{encoded}"}
        )

        self.assertEqual(bare.image_bytes, png)
        self.assertEqual(bare.mime_type, "image/png")
        self.assertEqual((bare.width, bare.height), (4, 3))
        self.assertEqual(data_url, bare)

    def test_result_rejects_declared_or_data_url_mime_that_contradicts_bytes(self) -> None:
        from codex_image.providers.result_assets import (
            AssetLoadError,
            load_response_asset,
        )

        encoded = base64.b64encode(self._image_bytes()).decode("ascii")

        with self.assertRaisesRegex(AssetLoadError, "content type"):
            load_response_asset(
                {"b64_json": encoded, "mime_type": "image/jpeg"}
            )
        with self.assertRaisesRegex(AssetLoadError, "content type"):
            load_response_asset(
                {"url": f"data:image/jpeg;base64,{encoded}"}
            )

    def test_result_rejects_fake_images_and_excessive_animation_frames(self) -> None:
        from codex_image.providers.result_assets import (
            AssetLoadError,
            load_response_asset,
        )

        fake = base64.b64encode(b"\x89PNG\r\n\x1a\nnot-a-real-png").decode("ascii")
        animated = base64.b64encode(self._gif_bytes(frames=101)).decode("ascii")

        with self.assertRaisesRegex(AssetLoadError, "valid raster"):
            load_response_asset({"b64_json": fake})
        with self.assertRaisesRegex(AssetLoadError, "frame limit"):
            load_response_asset({"b64_json": animated})

    def test_url_loader_results_are_revalidated_and_use_a_bounded_download(self) -> None:
        from codex_image.http import HTTPResponse
        from codex_image.providers.result_assets import (
            AssetLoadError,
            LoadedAsset,
            MAX_ASSET_BYTES,
            download_asset_url,
            load_response_asset,
        )

        png = self._image_bytes()

        class BoundedTransport:
            def __init__(self) -> None:
                self.limit: int | None = None

            def request_bounded(self, **kwargs):
                self.limit = int(kwargs["max_response_bytes"])
                return HTTPResponse(
                    status=200,
                    body=png,
                    headers={"Content-Type": "image/png"},
                )

        transport = BoundedTransport()
        downloaded = download_asset_url(
            "https://cdn.example/image.png",
            transport=transport,  # type: ignore[arg-type]
            provider_base_url="https://api.example/v1",
            authorization=None,
        )

        self.assertEqual(downloaded.image_bytes, png)
        self.assertEqual(transport.limit, MAX_ASSET_BYTES)
        with self.assertRaisesRegex(AssetLoadError, "valid raster"):
            load_response_asset(
                {"url": "https://cdn.example/fake.png"},
                url_loader=lambda _url: LoadedAsset(
                    b"\x89PNG\r\n\x1a\nfake",
                    "image/png",
                    1,
                    1,
                ),
            )

    def test_base64_size_is_checked_before_decoding(self) -> None:
        from codex_image.providers.result_assets import (
            AssetLoadError,
            load_response_asset,
        )

        with patch("codex_image.providers.result_assets.MAX_ASSET_BYTES", 3):
            with patch(
                "codex_image.providers.result_assets.base64.b64decode"
            ) as decode:
                with self.assertRaisesRegex(AssetLoadError, "50 MiB limit"):
                    load_response_asset({"b64_json": "A" * 8})
        decode.assert_not_called()

    def test_download_uses_decoded_format_when_raster_content_type_is_wrong(self) -> None:
        from codex_image.http import HTTPResponse
        from codex_image.providers.result_assets import download_asset_url

        for image_format, mime in (('WEBP', 'image/webp'), ('JPEG', 'image/jpeg'),
                                   ('PNG', 'image/png'), ('GIF', 'image/gif')):
            data = self._image_bytes(image_format)
            for header in ('image/png', 'image/jpeg', 'image/webp', 'image/gif'):
                with self.subTest(image_format=image_format, header=header):
                    transport = Mock()
                    transport.request_asset_bounded.return_value = HTTPResponse(
                        status=200, body=data, headers={'Content-Type': header},
                    )
                    asset = download_asset_url('https://cdn.example/wrong.png', transport=transport,
                                               provider_base_url='https://api.example/v1', authorization=None)
                    self.assertEqual(asset.image_bytes, data)
                    self.assertEqual(asset.mime_type, mime)
                    self.assertEqual((asset.width, asset.height), (4, 3))
                    transport.request_asset_bounded.assert_called_once()

    def test_download_still_rejects_invalid_images_and_non_raster_content_types(self) -> None:
        from codex_image.http import HTTPResponse
        from codex_image.providers.result_assets import AssetLoadError, download_asset_url

        cases = [(b'<html>error</html>', 'image/png'), (b'RIFFinvalidWEBP', 'image/png'),
                 (self._image_bytes('WEBP'), 'text/html'), (self._image_bytes('WEBP'), 'image/svg+xml')]
        for data, header in cases:
            with self.subTest(header=header, size=len(data)):
                transport = Mock()
                transport.request_asset_bounded.return_value = HTTPResponse(
                    status=200, body=data, headers={'Content-Type': header},
                )
                with self.assertRaises(AssetLoadError):
                    download_asset_url('https://cdn.example/wrong.png', transport=transport,
                                       provider_base_url='https://api.example/v1', authorization=None)


if __name__ == "__main__":
    unittest.main()

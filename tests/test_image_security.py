from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from PIL import Image

from codex_image.raster_validation import RasterValidationError, inspect_raster_image
from codex_image.webui.thumbnails import create_image_thumbnail, create_sidebar_thumbnail


class ImageSecurityTests(TestCase):
    def test_supported_formats_still_decode_and_thumbnail(self):
        for fmt in ("PNG", "JPEG", "GIF", "WEBP"):
            with self.subTest(format=fmt), TemporaryDirectory() as directory:
                data = BytesIO()
                Image.new("RGB", (24, 16), "red").save(data, format=fmt)
                self.assertEqual(inspect_raster_image(data.getvalue()).image_format, fmt)
                root = Path(directory)
                source = root / "source.bin"
                source.write_bytes(data.getvalue())
                self.assertEqual(create_image_thumbnail(source, root / "thumb.jpg"), root / "thumb.jpg")
                self.assertEqual(create_sidebar_thumbnail(source, root / "side.webp"), root / "side.webp")

    def test_rejected_format_parser_is_not_invoked(self):
        data = BytesIO()
        Image.new("RGB", (8, 8)).save(data, "TIFF")
        Image.init()
        _, accept = Image.OPEN["TIFF"]
        with patch.dict(Image.OPEN, {"TIFF": (lambda *args: self.fail("TIFF parser invoked"), accept)}):
            with self.assertRaises(RasterValidationError):
                inspect_raster_image(data.getvalue())

    def test_png_exif_orientation_is_preserved_in_thumbnails(self):
        # Small valid EXIF fixture, not an exhaustion payload.
        exif = Image.Exif()
        exif[274] = 6
        with TemporaryDirectory() as directory:
            root = Path(directory)
            Image.new("RGB", (24, 16), "red").save(root / "source.png", exif=exif)
            for target, create in ((root / "thumb.jpg", create_image_thumbnail),
                                   (root / "side.webp", create_sidebar_thumbnail)):
                self.assertEqual(create(root / "source.png", target), target)
                with Image.open(target) as image:
                    self.assertEqual(image.size, (16, 24))

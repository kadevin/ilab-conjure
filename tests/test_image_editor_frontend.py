import unittest

from tests.frontend_runner import run_frontend


class ImageEditorFrontendTests(unittest.TestCase):
    def test_image_editor_modules(self) -> None:
        run_frontend(self, "image_editor_modules.test.ts")

from __future__ import annotations

import unittest


class ProtocolAuthTests(unittest.TestCase):
    def test_auth_scheme_is_derived_from_protocol_profile(self) -> None:
        from codex_image.providers.auth import auth_scheme_for_protocol

        self.assertEqual(
            auth_scheme_for_protocol("gemini_generate_content"),
            "x-goog-api-key",
        )
        self.assertEqual(auth_scheme_for_protocol("openai_images"), "bearer")
        self.assertEqual(auth_scheme_for_protocol("openai_responses"), "bearer")
        self.assertEqual(auth_scheme_for_protocol("codex_images"), "codex_login")
        self.assertEqual(auth_scheme_for_protocol("codex_responses"), "codex_login")

    def test_unknown_protocol_has_no_implicit_auth_fallback(self) -> None:
        from codex_image.providers.auth import auth_scheme_for_protocol

        with self.assertRaisesRegex(ValueError, "unknown_protocol_auth_scheme"):
            auth_scheme_for_protocol("unknown")


if __name__ == "__main__":
    unittest.main()

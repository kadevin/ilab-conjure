from __future__ import annotations

import hashlib
import json
import unittest

from codex_image.webui.resource_limits import (
    HISTORY_BACKUP_FREE_RATIO,
    HISTORY_BACKUP_MIN_FREE_BYTES,
    HISTORY_BACKUP_UPLOAD_CHUNK_BYTES,
    MAX_HISTORY_BACKUP_COMPRESSION_RATIO,
    MAX_HISTORY_BACKUP_ENTRIES,
    MAX_HISTORY_BACKUP_EXPANDED_BYTES,
    MAX_HISTORY_BACKUP_MANIFEST_BYTES,
    MAX_HISTORY_BACKUP_MEMBER_BYTES,
    MAX_HISTORY_BACKUP_UPLOAD_BYTES,
    MAX_USER_CONFIG_BACKUP_COMPRESSION_RATIO,
    MAX_USER_CONFIG_BACKUP_ENTRIES,
    MAX_USER_CONFIG_BACKUP_EXPANDED_BYTES,
    MAX_USER_CONFIG_BACKUP_MANIFEST_BYTES,
    MAX_USER_CONFIG_BACKUP_MEMBER_BYTES,
    MAX_USER_CONFIG_BACKUP_UPLOAD_BYTES,
    USER_CONFIG_BACKUP_FREE_RATIO,
    USER_CONFIG_BACKUP_MIN_FREE_BYTES,
    USER_CONFIG_BACKUP_UPLOAD_CHUNK_BYTES,
)
from codex_image.webui.user_config_backup_format import (
    USER_CONFIG_BACKUP_FORMAT,
    USER_CONFIG_BACKUP_FORMAT_VERSION,
    UserConfigBackupManifest,
    UserConfigBackupMember,
    parse_user_config_manifest,
    safe_user_config_member_path,
    serialize_user_config_manifest,
)


def _digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _manifest() -> UserConfigBackupManifest:
    return UserConfigBackupManifest(
        format=USER_CONFIG_BACKUP_FORMAT,
        format_version=USER_CONFIG_BACKUP_FORMAT_VERSION,
        app_version="0.8.3",
        created_at="2026-08-21T12:00:00+00:00",
        sections=("chips", "gallery", "templates", "settings"),
        contains_secrets=False,
        members=(
            UserConfigBackupMember("chips", "chips/colors.json", 2, _digest(b"{}")),
            UserConfigBackupMember("gallery", "gallery/categories.json", 2, _digest(b"[]")),
            UserConfigBackupMember(
                "templates",
                "templates/prompt-templates.json",
                2,
                _digest(b"{}"),
            ),
            UserConfigBackupMember("settings", "settings/webui.json", 2, _digest(b"{}")),
        ),
    )


def _payload() -> dict[str, object]:
    return json.loads(serialize_user_config_manifest(_manifest()))


class UserConfigBackupFormatTests(unittest.TestCase):
    def test_user_config_archives_reuse_the_hardened_history_limits(self) -> None:
        self.assertEqual(
            (
                MAX_USER_CONFIG_BACKUP_UPLOAD_BYTES,
                MAX_USER_CONFIG_BACKUP_EXPANDED_BYTES,
                MAX_USER_CONFIG_BACKUP_MEMBER_BYTES,
                MAX_USER_CONFIG_BACKUP_MANIFEST_BYTES,
                MAX_USER_CONFIG_BACKUP_ENTRIES,
                MAX_USER_CONFIG_BACKUP_COMPRESSION_RATIO,
                USER_CONFIG_BACKUP_UPLOAD_CHUNK_BYTES,
                USER_CONFIG_BACKUP_MIN_FREE_BYTES,
                USER_CONFIG_BACKUP_FREE_RATIO,
            ),
            (
                MAX_HISTORY_BACKUP_UPLOAD_BYTES,
                MAX_HISTORY_BACKUP_EXPANDED_BYTES,
                MAX_HISTORY_BACKUP_MEMBER_BYTES,
                MAX_HISTORY_BACKUP_MANIFEST_BYTES,
                MAX_HISTORY_BACKUP_ENTRIES,
                MAX_HISTORY_BACKUP_COMPRESSION_RATIO,
                HISTORY_BACKUP_UPLOAD_CHUNK_BYTES,
                HISTORY_BACKUP_MIN_FREE_BYTES,
                HISTORY_BACKUP_FREE_RATIO,
            ),
        )

    def test_manifest_round_trip_preserves_all_selected_sections(self) -> None:
        manifest = _manifest()

        first = serialize_user_config_manifest(manifest)
        second = serialize_user_config_manifest(manifest)

        self.assertEqual(first, second)
        self.assertEqual(parse_user_config_manifest(first), manifest)
        self.assertEqual(
            json.loads(first)["sections"],
            ["chips", "gallery", "templates", "settings"],
        )

    def test_safe_member_path_accepts_only_declared_v1_layouts(self) -> None:
        cases = (
            ("chips", ("colors.json",), "chips/colors.json"),
            ("chips", ("prompt-snippets.json",), "chips/prompt-snippets.json"),
            ("gallery", ("categories.json",), "gallery/categories.json"),
            (
                "gallery",
                ("items", "20260821120000-a1b2c3d4", "metadata.json"),
                "gallery/items/20260821120000-a1b2c3d4/metadata.json",
            ),
            (
                "gallery",
                ("items", "20260821120000-a1b2c3d4", "产品 图.png"),
                "gallery/items/20260821120000-a1b2c3d4/产品 图.png",
            ),
            ("templates", ("prompt-templates.json",), "templates/prompt-templates.json"),
            (
                "templates",
                ("thumbnails", f"{_digest(b'image')}.webp"),
                f"templates/thumbnails/{_digest(b'image')}.webp",
            ),
            ("settings", ("client-preferences.json",), "settings/client-preferences.json"),
        )
        for section, parts, expected in cases:
            with self.subTest(section=section, parts=parts):
                self.assertEqual(safe_user_config_member_path(section, *parts), expected)

        rejected = (
            ("chips", ("unknown.json",)),
            ("gallery", ("items", "bad/id", "metadata.json")),
            ("gallery", ("items", "item-1", "nested/image.png")),
            ("templates", ("thumbnails", "not-a-digest.png")),
            ("templates", ("thumbnails", f"{_digest(b'image')}.svg")),
            ("settings", ("oauth.json",)),
        )
        for section, parts in rejected:
            with self.subTest(section=section, parts=parts):
                with self.assertRaisesRegex(ValueError, "user_config_member_path_invalid"):
                    safe_user_config_member_path(section, *parts)

    def test_parser_rejects_paths_that_can_escape_or_change_after_nfkc(self) -> None:
        unsafe_paths = (
            "/chips/colors.json",
            "C:/chips/colors.json",
            "chips/../settings/webui.json",
            "chips\\colors.json",
            "chips//colors.json",
            "chips/./colors.json",
            "chips/．．/colors.json",
            "chips/colors.json\x00",
        )
        for path in unsafe_paths:
            with self.subTest(path=path):
                payload = _payload()
                payload["members"][0]["path"] = path  # type: ignore[index]
                with self.assertRaisesRegex(ValueError, "user_config_manifest_member_path_invalid"):
                    parse_user_config_manifest(json.dumps(payload).encode("utf-8"))

    def test_parser_rejects_duplicate_or_mismatched_sections_and_members(self) -> None:
        cases: list[dict[str, object]] = []

        duplicate_member = _payload()
        duplicate_member["members"].append(dict(duplicate_member["members"][0]))  # type: ignore[union-attr,index]
        cases.append(duplicate_member)

        duplicate_section = _payload()
        duplicate_section["sections"] = ["chips", "chips", "gallery", "templates", "settings"]
        cases.append(duplicate_section)

        missing_section_member = _payload()
        missing_section_member["members"] = missing_section_member["members"][:-1]  # type: ignore[index]
        cases.append(missing_section_member)

        wrong_root = _payload()
        wrong_root["members"][0]["section"] = "settings"  # type: ignore[index]
        cases.append(wrong_root)

        unknown_section = _payload()
        unknown_section["sections"] = ["chips", "gallery", "templates", "unknown"]
        cases.append(unknown_section)

        for payload in cases:
            with self.subTest(payload=payload):
                with self.assertRaises(ValueError):
                    parse_user_config_manifest(json.dumps(payload).encode("utf-8"))

    def test_parser_is_strict_about_schema_numbers_booleans_and_digests(self) -> None:
        mutations = (
            ("format_version", True),
            ("format_version", "1"),
            ("contains_secrets", 0),
            ("members.0.size_bytes", True),
            ("members.0.size_bytes", -1),
            ("members.0.sha256", "A" * 64),
            ("members.0.sha256", "a" * 63),
        )
        for field, value in mutations:
            with self.subTest(field=field):
                payload = _payload()
                if field.startswith("members.0."):
                    payload["members"][0][field.rsplit(".", 1)[-1]] = value  # type: ignore[index]
                else:
                    payload[field] = value
                with self.assertRaises(ValueError):
                    parse_user_config_manifest(json.dumps(payload).encode("utf-8"))

    def test_format_and_version_errors_remain_distinguishable(self) -> None:
        payload = _payload()
        payload["format"] = "other-format"
        with self.assertRaisesRegex(ValueError, "user_config_manifest_format_unsupported"):
            parse_user_config_manifest(json.dumps(payload).encode("utf-8"))

        payload = _payload()
        payload["format_version"] = 2
        with self.assertRaisesRegex(ValueError, "user_config_manifest_version_unsupported"):
            parse_user_config_manifest(json.dumps(payload).encode("utf-8"))

    def test_serializer_rejects_invalid_in_memory_manifest(self) -> None:
        invalid = UserConfigBackupManifest(
            **{
                **_manifest().__dict__,
                "members": (
                    UserConfigBackupMember("chips", "chips/colors.json", 2, "A" * 64),
                ),
                "sections": ("chips",),
            }
        )

        with self.assertRaises(ValueError):
            serialize_user_config_manifest(invalid)


if __name__ == "__main__":
    unittest.main()

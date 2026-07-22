from __future__ import annotations

from pathlib import Path
import unittest


class TrayLauncherStaticTests(unittest.TestCase):
    def test_rust_tray_launcher_declares_core_behavior_and_assets(self) -> None:
        launcher_root = Path("launcher")
        manifest = launcher_root / "Cargo.toml"
        main_source = launcher_root / "src" / "main.rs"
        lib_source = launcher_root / "src" / "lib.rs"
        standard_update_source = launcher_root / "src" / "standard_update.rs"
        standard_updater_main = launcher_root / "src" / "bin" / "standard_updater.rs"
        build_script = launcher_root / "build.rs"
        readme = launcher_root / "README.md"
        icon_svg = launcher_root / "assets" / "rabbit-logo.svg"
        icon_ico = launcher_root / "assets" / "rabbit-logo.ico"

        for path in (
            manifest,
            main_source,
            lib_source,
            standard_update_source,
            standard_updater_main,
            build_script,
            readme,
            icon_svg,
            icon_ico,
        ):
            self.assertTrue(path.exists(), f"{path} should exist")

        manifest_text = manifest.read_text(encoding="utf-8")
        self.assertIn('name = "ilab-conjure-launcher"', manifest_text)
        self.assertIn("tray-icon", manifest_text)
        self.assertIn("winit", manifest_text)
        self.assertIn("open", manifest_text)
        self.assertIn("[target.'cfg(windows)'.build-dependencies]", manifest_text)
        self.assertIn("winresource", manifest_text)

        source = main_source.read_text(encoding="utf-8")
        build_source = build_script.read_text(encoding="utf-8")
        combined_source = "\n".join(
            (
                source,
                lib_source.read_text(encoding="utf-8"),
                standard_update_source.read_text(encoding="utf-8"),
                standard_updater_main.read_text(encoding="utf-8"),
            )
        )
        self.assertIn('#![cfg_attr(target_os = "windows", windows_subsystem = "windows")]', source)
        self.assertIn("assets/rabbit-logo.ico", build_source)
        self.assertIn("winresource::WindowsResource::new", build_source)
        self.assertIn('resource.set_icon("assets/rabbit-logo.ico")', build_source)
        self.assertIn('resource.set("FileDescription", "iLab CONJURE")', build_source)
        self.assertIn('resource.set("ProductName", "iLab CONJURE")', build_source)
        self.assertIn('"iLab GPT CONJURE.exe"', build_source)
        self.assertIn('pub const APP_NAME: &str = "iLab CONJURE";', combined_source)
        self.assertIn(
            'pub const LEGACY_DATA_DIR_NAME: &str = "iLab GPT CONJURE";',
            combined_source,
        )
        self.assertIn("http://127.0.0.1:8787/", combined_source)
        self.assertIn("create_tray_state(&config)", source)
        self.assertIn("sync_locale", source)
        self.assertIn(".set_text(", source)
        self.assertIn("MENU_OPEN_SETTINGS", source)
        self.assertIn("MENU_OPEN_HISTORY", source)
        self.assertIn("settings_item", source)
        self.assertIn("history_item", source)
        self.assertIn("service.open_settings", source)
        self.assertIn("service.open_history", source)
        self.assertLess(source.index("MENU_OPEN_WEBUI"), source.index("MENU_OPEN_SETTINGS"))
        self.assertLess(source.index("MENU_OPEN_SETTINGS"), source.index("MENU_OPEN_HISTORY"))
        self.assertIn("service.show_about", source)
        self.assertIn("read_locale_preference", combined_source)
        self.assertIn("detect_system_locale", combined_source)
        self.assertIn("AppleLanguages", combined_source)
        self.assertIn("CurrentUICulture", combined_source)
        self.assertIn("AboutAction::CheckUpdates", combined_source)
        self.assertIn("UpdateAvailability::UpdateAvailable", combined_source)
        self.assertIn("show_platform_update_window", combined_source)
        self.assertIn("LATEST_UPDATE_MANIFEST_URL", combined_source)
        self.assertIn("parse_update_manifest_payload", combined_source)
        self.assertIn("verify_update_manifest_signature", combined_source)
        self.assertIn("update-signing-public-key.b64", combined_source)
        self.assertIn("--verify-update-manifest", combined_source)
        self.assertIn("ed25519", manifest_text)
        self.assertIn("base64", manifest_text)
        self.assertIn("current_update_platform_key", combined_source)
        self.assertIn('"platforms"', combined_source)
        self.assertIn('"standard_platforms"', combined_source)
        self.assertIn("standard_signature", combined_source)
        self.assertIn('"sha256"', combined_source)
        self.assertIn('"signature"', combined_source)
        self.assertIn("User-Agent", combined_source)
        self.assertIn(
            "https://github.com/kadevin/ilab-conjure/releases/latest/download/latest.json",
            combined_source,
        )
        self.assertIn("show_platform_about_window", combined_source)
        self.assertIn("portable-version.txt", combined_source)
        self.assertIn("APP_VERSION", combined_source)
        self.assertIn("开源地址", combined_source)
        self.assertIn("打开开源地址", combined_source)
        self.assertIn("发现新版本", combined_source)
        self.assertIn("安装更新", combined_source)
        self.assertIn("下载新版", combined_source)
        self.assertIn("Download Update", combined_source)
        self.assertIn("UpdateOutcome::LaunchedUpdater", combined_source)
        self.assertIn("portable_updater_path", combined_source)
        self.assertIn("launch_portable_updater", combined_source)
        self.assertIn("StandardMacUpdater", combined_source)
        self.assertIn("standard_update_helper_path", combined_source)
        self.assertIn("launch_standard_updater", combined_source)
        self.assertIn("run_standard_updater", combined_source)
        self.assertIn("--expected-sha256", combined_source)
        self.assertIn("--expected-version", combined_source)
        self.assertIn("--locale", combined_source)
        self.assertIn("verify_sha256_file", combined_source)
        self.assertIn("hdiutil", combined_source)
        self.assertIn("/usr/bin/codesign", combined_source)
        self.assertIn("/usr/bin/lipo", combined_source)
        self.assertIn("com.ilab.gpt-conjure", combined_source)
        self.assertIn("replace_staged_app_transaction", combined_source)
        self.assertIn("with administrator privileges", combined_source)
        self.assertIn('open\").arg("-n"', combined_source)
        self.assertIn("ILAB_CONJURE_APP_DIR", combined_source)
        self.assertIn("--auto", combined_source)
        self.assertIn("--restart-launcher", combined_source)
        self.assertNotIn("failed to open update download", combined_source)
        self.assertNotIn(
            'open::that(RELEASES_URL).context("failed to open GitHub Releases")',
            combined_source,
        )
        self.assertIn("打开 WebUI", combined_source)
        self.assertIn("打开设置", combined_source)
        self.assertIn("历史库", combined_source)
        self.assertIn("检查更新", combined_source)
        self.assertIn("关于 iLab CONJURE", combined_source)
        self.assertIn("重启 WebUI 服务", combined_source)
        self.assertIn("退出", combined_source)
        self.assertIn("Open WebUI", combined_source)
        self.assertIn("Open Settings", combined_source)
        self.assertIn("History Library", combined_source)
        self.assertIn("Check for Updates", combined_source)
        self.assertIn("About iLab CONJURE", combined_source)
        self.assertIn("Restart WebUI Service", combined_source)
        self.assertIn("Quit", combined_source)
        self.assertIn("codex_image.webui.startup_auth", combined_source)
        self.assertIn("uvicorn", combined_source)
        self.assertIn("webui-server.log", combined_source)

        icon_text = icon_svg.read_text(encoding="utf-8")
        self.assertIn("<svg", icon_text)
        self.assertIn("rabbit", icon_text.lower())
        self.assertIn("#457B66", icon_text)
        self.assertIn('fill="#FFFFFF"', icon_text)
        self.assertIn('stroke="#D3B776"', icon_text)
        self.assertNotIn('stroke="#FFFFFF"', icon_text)
        icon_bytes = icon_ico.read_bytes()
        self.assertGreater(len(icon_bytes), 1024)
        self.assertEqual(icon_bytes[:4], b"\x00\x00\x01\x00")
        self.assertGreaterEqual(int.from_bytes(icon_bytes[4:6], "little"), 5)

        readme_text = readme.read_text(encoding="utf-8")
        self.assertIn("system tray", readme_text.lower())
        self.assertIn("menu bar", readme_text.lower())
        self.assertIn("does not replace the Python WebUI backend", readme_text)
        self.assertIn("rabbit-logo.ico", readme_text)
        self.assertIn("File Explorer", readme_text)
        self.assertIn("signed `latest.json` manifest", readme_text)
        self.assertIn("Install Update", readme_text)
        self.assertIn("updater handoff", readme_text)
        self.assertIn("standard macOS app", readme_text)
        self.assertIn("rollback", readme_text.lower())

use super::*;

#[test]
fn launcher_urls_match_fixed_local_webui_port() {
    let config =
        LauncherConfig::from_dirs(PathBuf::from("/app"), PathBuf::from("/data"), DEFAULT_PORT)
            .unwrap();

    assert_eq!(config.url(), WEBUI_URL);
    assert_eq!(config.health_url(), "http://127.0.0.1:8787/api/health");
    assert_eq!(config.settings_url(), "http://127.0.0.1:8787/?settings=1");
    assert_eq!(config.history_url(), "http://127.0.0.1:8787/history");
    assert_eq!(
        config.log_path,
        PathBuf::from("/data/webui-outputs/webui-server.log")
    );
}

#[test]
fn rabbit_icon_has_rgba_pixels_and_visible_shape() {
    let (rgba, width, height) = rabbit_icon_rgba(32);

    assert_eq!((width, height), (32, 32));
    assert_eq!(rgba.len(), 32 * 32 * 4);
    assert!(rgba.chunks_exact(4).any(|pixel| pixel[3] == 0xFF));
    assert!(rgba.chunks_exact(4).any(|pixel| pixel[3] == 0x00));
    assert!(rgba
        .chunks_exact(4)
        .filter(|pixel| pixel[3] == 0xFF)
        .all(|pixel| pixel == [0xFF, 0xFF, 0xFF, 0xFF]));
}

#[test]
fn rabbit_icon_fills_menu_bar_template_canvas() {
    let (rgba, width, height) = rabbit_icon_rgba(32);
    let mut min_x = width;
    let mut min_y = height;
    let mut max_x = 0;
    let mut max_y = 0;

    for y in 0..height {
        for x in 0..width {
            let alpha = rgba[((y * width + x) * 4 + 3) as usize];
            if alpha == 0 {
                continue;
            }
            min_x = min_x.min(x);
            min_y = min_y.min(y);
            max_x = max_x.max(x);
            max_y = max_y.max(y);
        }
    }

    assert!(max_x >= min_x);
    assert!(max_y >= min_y);
    assert!(max_x - min_x + 1 >= 24);
    assert!(max_y - min_y + 1 >= 25);
    assert!(min_y >= 2);
    assert!(height - max_y - 1 <= 3);
}

#[test]
fn locale_from_language_tag_matches_webui_locale_rules() {
    assert_eq!(
        AppLocale::from_language_tag("zh-Hans-CN"),
        Some(AppLocale::ZhCn)
    );
    assert_eq!(AppLocale::from_language_tag("zh"), Some(AppLocale::ZhCn));
    assert_eq!(
        AppLocale::from_language_tag("zh-Hant-TW"),
        Some(AppLocale::ZhTw)
    );
    assert_eq!(AppLocale::from_language_tag("zh-HK"), Some(AppLocale::ZhHk));
    assert_eq!(AppLocale::from_language_tag("ja-JP"), Some(AppLocale::Ja));
    assert_eq!(AppLocale::from_language_tag("ko-KR"), Some(AppLocale::Ko));
    assert_eq!(AppLocale::from_language_tag("de-DE"), Some(AppLocale::De));
    assert_eq!(AppLocale::from_language_tag("xx-YY"), None);
}

#[test]
fn localized_menu_labels_cover_simplified_chinese_and_english() {
    let zh = localized_menu_labels(AppLocale::ZhCn);
    assert_eq!(zh.open_webui, "打开 WebUI");
    assert_eq!(zh.open_settings, "打开设置");
    assert_eq!(zh.open_history, "历史库");
    assert_eq!(zh.check_updates, "检查更新");
    assert_eq!(zh.about, "关于 iLab CONJURE");
    assert_eq!(zh.restart, "重启 WebUI 服务");
    assert_eq!(zh.quit, "退出");

    let en = localized_menu_labels(AppLocale::En);
    assert_eq!(en.open_webui, "Open WebUI");
    assert_eq!(en.open_settings, "Open Settings");
    assert_eq!(en.open_history, "History Library");
    assert_eq!(en.check_updates, "Check for Updates");
    assert_eq!(en.about, "About iLab CONJURE");
    assert_eq!(en.restart, "Restart WebUI Service");
    assert_eq!(en.quit, "Quit");
}

#[test]
fn localized_about_labels_cover_simplified_chinese_and_english() {
    let zh = localized_about_labels(AppLocale::ZhCn);
    assert_eq!(zh.title, "关于 iLab CONJURE");
    assert_eq!(zh.version, "版本");
    assert_eq!(zh.open_source, "开源地址");
    assert_eq!(zh.check_updates, "检查更新");
    assert_eq!(zh.open_project, "打开开源地址");
    assert_eq!(zh.close, "关闭");

    let en = localized_about_labels(AppLocale::En);
    assert_eq!(en.title, "About iLab CONJURE");
    assert_eq!(en.version, "Version");
    assert_eq!(en.open_source, "Open source");
    assert_eq!(en.check_updates, "Check for Updates");
    assert_eq!(en.open_project, "Open Source");
    assert_eq!(en.close, "Close");
}

#[test]
fn launcher_version_label_prefers_portable_version_file() {
    let root = env::temp_dir().join(format!(
        "ilab-conjure-launcher-version-test-{}-portable",
        std::process::id()
    ));
    let app_dir = root.join("app");
    fs::create_dir_all(&app_dir).unwrap();
    fs::write(root.join("portable-version.txt"), "local-build-1\n").unwrap();

    assert_eq!(launcher_version_label(&app_dir), "local-build-1");

    let _ = fs::remove_dir_all(root);
}

#[test]
fn launcher_version_label_reads_source_version_py() {
    let root = env::temp_dir().join(format!(
        "ilab-conjure-launcher-version-test-{}-source",
        std::process::id()
    ));
    let version_dir = root.join("codex_image");
    fs::create_dir_all(&version_dir).unwrap();
    fs::write(version_dir.join("version.py"), "APP_VERSION = \"1.2.3\"\n").unwrap();

    assert_eq!(launcher_version_label(&root), "v1.2.3");

    let _ = fs::remove_dir_all(root);
}

#[test]
fn about_info_contains_version_and_project_urls() {
    let root = env::temp_dir().join(format!(
        "ilab-conjure-launcher-about-test-{}",
        std::process::id()
    ));
    let app_dir = root.join("app");
    fs::create_dir_all(&app_dir).unwrap();
    fs::write(root.join("portable-version.txt"), "0.5.4\n").unwrap();
    let config = LauncherConfig::from_dirs(app_dir, root.join("data"), DEFAULT_PORT).unwrap();

    let about = config.about_info();

    assert_eq!(about.version_label, "v0.5.4");
    assert_eq!(about.project_url, PROJECT_URL);
    assert_eq!(about.releases_url, RELEASES_URL);

    let _ = fs::remove_dir_all(root);
}

#[test]
fn update_manifest_payload_parses_version_release_url_notes_and_platforms() {
    let manifest = parse_update_manifest_payload(
            r#"{
                "schema_version": 1,
                "version": "0.6.0",
                "release_url": "https://github.com/kadevin/ilab-conjure/releases/tag/v0.6.0",
                "notes": "更新说明",
                "signature": {
                    "algorithm": "ed25519",
                    "value": "KgkUvdx3azdMzIFWAX2wR5tNrYZWH+k2pfu/sckT/TiNNrlTKL8NYqXJ1vbG5Ko+js92ygATeCZD4PXplAZGCg=="
                },
                "platforms": {
                    "darwin-aarch64": {
                        "asset": "ilab-gpt-conjure_macos_portable_arm64_0.6.0.zip",
                        "url": "https://example.test/arm64.zip",
                        "sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
                        "package": "portable-zip"
                    },
                    "windows-x86_64": {
                        "asset": "ilab-gpt-conjure_windows_portable_x64_0.6.0.zip",
                        "url": "https://example.test/windows.zip",
                        "sha256": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
                        "package": "portable-zip"
                    }
                },
                "standard_platforms": {
                    "darwin-aarch64": {
                        "asset": "iLab-GPT-CONJURE-macos-arm64-0.6.0.dmg",
                        "url": "https://example.test/arm64.dmg",
                        "sha256": "cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc",
                        "package": "standard-dmg"
                    }
                }
            }"#,
        )
        .unwrap();

    assert_eq!(manifest.version, "0.6.0");
    assert_eq!(
        manifest.release_url,
        "https://github.com/kadevin/ilab-conjure/releases/tag/v0.6.0"
    );
    assert_eq!(manifest.notes, "更新说明");
    assert_eq!(manifest.platforms.len(), 2);
    assert_eq!(manifest.standard_platforms.len(), 1);
    assert_eq!(
        manifest.platforms["darwin-aarch64"].url,
        "https://example.test/arm64.zip"
    );
    assert_eq!(
        manifest.standard_platforms["darwin-aarch64"].url,
        "https://example.test/arm64.dmg"
    );
    assert_eq!(
        manifest.platforms["darwin-aarch64"].sha256,
        "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    );
    assert_eq!(
        manifest.signature.unwrap().value,
        "KgkUvdx3azdMzIFWAX2wR5tNrYZWH+k2pfu/sckT/TiNNrlTKL8NYqXJ1vbG5Ko+js92ygATeCZD4PXplAZGCg=="
    );
}

#[test]
fn update_manifest_signature_verifies_ed25519_payload_and_rejects_tampering() {
    let public_key = "A6EHv/POEL4dcN0Y50vAmWfk1jCbpQ1fHdyGZBJVMbg=";
    let mut manifest = UpdateManifest {
            schema_version: 1,
            version: "0.6.0".to_string(),
            release_url: "https://example.test/release".to_string(),
            notes: String::new(),
            signature: Some(UpdateSignature {
                algorithm: "ed25519".to_string(),
                value: "KgkUvdx3azdMzIFWAX2wR5tNrYZWH+k2pfu/sckT/TiNNrlTKL8NYqXJ1vbG5Ko+js92ygATeCZD4PXplAZGCg==".to_string(),
            }),
            standard_signature: None,
            platforms: [(
                "darwin-aarch64".to_string(),
                UpdatePlatform {
                    asset: "current.zip".to_string(),
                    url: "https://example.test/current.zip".to_string(),
                    sha256: "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
                        .to_string(),
                    package: "portable-zip".to_string(),
                },
            )]
            .into(),
            standard_platforms: Default::default(),
        };

    verify_update_manifest_signature_with_key(&manifest, public_key).unwrap();

    manifest.platforms.get_mut("darwin-aarch64").unwrap().sha256 =
        "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa".to_string();

    assert!(verify_update_manifest_signature_with_key(&manifest, public_key).is_err());
}

#[test]
fn update_check_selects_matching_manifest_platform_entry() {
    let key = current_update_platform_key();
    let manifest = UpdateManifest {
        schema_version: 1,
        version: "0.6.0".to_string(),
        release_url: "https://example.test/release".to_string(),
        notes: String::new(),
        signature: None,
        standard_signature: None,
        platforms: [
            (
                "unsupported-platform".to_string(),
                UpdatePlatform {
                    asset: "other.zip".to_string(),
                    url: "https://example.test/other.zip".to_string(),
                    sha256: "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
                        .to_string(),
                    package: "portable-zip".to_string(),
                },
            ),
            (
                key.to_string(),
                UpdatePlatform {
                    asset: "current.zip".to_string(),
                    url: "https://example.test/current.zip".to_string(),
                    sha256: "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
                        .to_string(),
                    package: "portable-zip".to_string(),
                },
            ),
        ]
        .into(),
        standard_platforms: [(
            key.to_string(),
            UpdatePlatform {
                asset: "current.dmg".to_string(),
                url: "https://example.test/current.dmg".to_string(),
                sha256: "cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc"
                    .to_string(),
                package: "standard-dmg".to_string(),
            },
        )]
        .into(),
    };

    let check = update_check_from_manifest("v0.5.0", &manifest, UpdatePackageKind::Portable);
    let standard_check =
        update_check_from_manifest("v0.5.0", &manifest, UpdatePackageKind::Standard);

    assert_eq!(check.availability, UpdateAvailability::UpdateAvailable);
    assert_eq!(check.current_version, "v0.5.0");
    assert_eq!(check.latest_version, "v0.6.0");
    assert_eq!(check.release_url, "https://example.test/release");
    assert_eq!(
        check.download_url,
        Some("https://example.test/current.zip".to_string())
    );
    assert_eq!(
        check.download_sha256,
        Some("bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb".to_string())
    );
    assert_eq!(check.package, Some("portable-zip".to_string()));
    assert_eq!(
        standard_check.download_url,
        Some("https://example.test/current.dmg".to_string())
    );
    assert_eq!(standard_check.package, Some("standard-dmg".to_string()));
}

#[test]
fn update_check_compares_semver_labels_and_handles_local_builds() {
    assert_eq!(
        compare_version_labels("v0.5.9", "v0.6.0"),
        Some(std::cmp::Ordering::Less)
    );
    assert_eq!(
        compare_version_labels("0.6.0", "v0.6.0"),
        Some(std::cmp::Ordering::Equal)
    );
    assert_eq!(
        compare_version_labels("v0.7.0", "v0.6.0"),
        Some(std::cmp::Ordering::Greater)
    );
    assert_eq!(compare_version_labels("local-build", "v0.6.0"), None);

    let manifest = UpdateManifest {
        schema_version: 1,
        version: "0.6.0".to_string(),
        release_url: "https://example.test/release".to_string(),
        notes: String::new(),
        signature: None,
        standard_signature: None,
        platforms: Default::default(),
        standard_platforms: Default::default(),
    };

    assert_eq!(
        update_check_from_manifest("v0.6.0", &manifest, UpdatePackageKind::Portable).availability,
        UpdateAvailability::UpToDate
    );
    assert_eq!(
        update_check_from_manifest("local-build", &manifest, UpdatePackageKind::Portable)
            .availability,
        UpdateAvailability::UnknownCurrentVersion
    );
}

#[test]
fn update_check_offers_install_for_local_build_when_manifest_platform_matches() {
    let manifest = UpdateManifest {
        schema_version: 1,
        version: "0.6.0".to_string(),
        release_url: "https://example.test/release".to_string(),
        notes: String::new(),
        signature: None,
        standard_signature: None,
        platforms: [(
            current_update_platform_key().to_string(),
            UpdatePlatform {
                asset: "current.zip".to_string(),
                url: "https://example.test/current.zip".to_string(),
                sha256: "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
                    .to_string(),
                package: "portable-zip".to_string(),
            },
        )]
        .into(),
        standard_platforms: Default::default(),
    };

    let local_build_check =
        update_check_from_manifest("local-build", &manifest, UpdatePackageKind::Portable);
    let up_to_date_check =
        update_check_from_manifest("v0.6.0", &manifest, UpdatePackageKind::Portable);

    assert_eq!(
        local_build_check.availability,
        UpdateAvailability::UnknownCurrentVersion
    );
    assert!(update_check_has_install_action(
        &local_build_check,
        UpdateInstallAction::PortableUpdater
    ));
    assert!(!update_check_has_install_action(
        &up_to_date_check,
        UpdateInstallAction::PortableUpdater
    ));
}

#[test]
fn update_install_action_requires_bundled_updater() {
    let check = UpdateCheck {
        current_version: "v0.5.0".to_string(),
        latest_version: "v0.6.0".to_string(),
        release_url: "https://example.test/release".to_string(),
        download_url: Some("https://example.test/current.zip".to_string()),
        download_sha256: Some(
            "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb".to_string(),
        ),
        package: Some("portable-zip".to_string()),
        availability: UpdateAvailability::UpdateAvailable,
    };

    assert!(!update_check_has_install_action(
        &check,
        UpdateInstallAction::None
    ));
    assert!(update_check_has_install_action(
        &check,
        UpdateInstallAction::PortableUpdater
    ));
    assert!(update_check_has_install_action(
        &check,
        UpdateInstallAction::StandardMacUpdater
    ));
    assert!(update_check_has_install_action(
        &check,
        UpdateInstallAction::DownloadPackage
    ));
}

#[test]
fn portable_updater_path_resolves_from_bundle_root() {
    let root = env::temp_dir().join(format!(
        "ilab-conjure-launcher-updater-test-{}",
        std::process::id()
    ));
    let app_dir = root.join("app");
    fs::create_dir_all(&app_dir).unwrap();
    let config = LauncherConfig::from_dirs(app_dir, root.join("data"), DEFAULT_PORT).unwrap();

    #[cfg(target_os = "macos")]
    {
        let updater = root.join("Update WebUI Portable.command");
        fs::write(&updater, "#!/bin/zsh\n").unwrap();
        assert_eq!(portable_updater_path(&config), Some(updater));
    }

    #[cfg(target_os = "windows")]
    {
        let updater = root.join("Update WebUI Portable.bat");
        fs::write(&updater, "@echo off\n").unwrap();
        assert_eq!(portable_updater_path(&config), Some(updater));
    }

    #[cfg(not(any(target_os = "macos", target_os = "windows")))]
    {
        assert_eq!(portable_updater_path(&config), None);
    }

    let _ = fs::remove_dir_all(root);
}

#[test]
fn standard_app_uses_standard_webui_shim_and_no_portable_updater() {
    let root = env::temp_dir().join(format!(
        "ilab-conjure-launcher-standard-test-{}",
        std::process::id()
    ));
    let app_dir = root
        .join("iLab GPT CONJURE.app")
        .join("Contents")
        .join("Resources")
        .join("app");
    fs::create_dir_all(&app_dir).unwrap();
    fs::write(app_dir.join("standard_webui_app.py"), "app = object()\n").unwrap();
    fs::write(root.join("Update WebUI Portable.command"), "#!/bin/zsh\n").unwrap();
    let config = LauncherConfig::from_dirs(app_dir, root.join("data"), DEFAULT_PORT).unwrap();

    assert_eq!(config.uvicorn_app(), "standard_webui_app:app");
    assert_eq!(portable_updater_path(&config), None);

    let check = UpdateCheck {
        current_version: "v0.6.1".to_string(),
        latest_version: "v0.6.2".to_string(),
        release_url: "https://example.test/release".to_string(),
        download_url: Some("https://example.test/update.dmg".to_string()),
        download_sha256: Some("a".repeat(64)),
        package: Some("standard-dmg".to_string()),
        availability: UpdateAvailability::UpdateAvailable,
    };
    assert_eq!(
        update_install_action_for_config(&config, &check),
        UpdateInstallAction::DownloadPackage
    );

    let helper = root
        .join("iLab GPT CONJURE.app")
        .join("Contents")
        .join("Helpers")
        .join(standard_update::STANDARD_UPDATER_EXECUTABLE);
    fs::create_dir_all(helper.parent().unwrap()).unwrap();
    fs::write(&helper, "helper").unwrap();
    #[cfg(target_os = "macos")]
    assert_eq!(
        update_install_action_for_config(&config, &check),
        UpdateInstallAction::StandardMacUpdater
    );
    #[cfg(not(target_os = "macos"))]
    assert_eq!(
        update_install_action_for_config(&config, &check),
        UpdateInstallAction::DownloadPackage
    );

    let _ = fs::remove_dir_all(root);
}

#[test]
fn reads_locale_preference_from_webui_settings_json() {
    let path = env::temp_dir().join(format!(
        "ilab-conjure-launcher-locale-test-{}-{}.json",
        std::process::id(),
        "zh-tw"
    ));
    fs::write(&path, r#"{"locale":"zh-TW"}"#).unwrap();

    assert_eq!(read_locale_preference(&path), Some(AppLocale::ZhTw));

    fs::write(&path, r#"{"locale":"xx"}"#).unwrap();
    assert_eq!(read_locale_preference(&path), None);

    let _ = fs::remove_file(path);
}

#[test]
fn portable_app_dir_defaults_to_bundle_data_directory() {
    let app_dir = PathBuf::from("/bundle/app");

    assert_eq!(
        default_data_dir_for_app(&app_dir),
        PathBuf::from("/bundle/data")
    );
}

#[test]
fn app_bundle_executable_can_find_portable_app_directory() {
    let mut candidates = Vec::new();
    push_app_dir_candidates(
        &mut candidates,
        Path::new("/bundle/Start iLab GPT CONJURE.app/Contents/MacOS"),
    );

    assert!(candidates.contains(&PathBuf::from("/bundle/app")));
}

#[test]
fn standard_app_executable_can_find_embedded_resources_app_directory() {
    let mut mac_candidates = Vec::new();
    push_app_dir_candidates(
        &mut mac_candidates,
        Path::new("/Applications/iLab GPT CONJURE.app/Contents/MacOS"),
    );
    assert!(mac_candidates.contains(&PathBuf::from(
        "/Applications/iLab GPT CONJURE.app/Contents/Resources/app"
    )));

    let mut windows_candidates = Vec::new();
    push_app_dir_candidates(
        &mut windows_candidates,
        Path::new("C:/Tools/iLab GPT CONJURE"),
    );
    assert!(windows_candidates.contains(&PathBuf::from("C:/Tools/iLab GPT CONJURE/resources/app")));
}

#[test]
fn standard_app_uses_platform_user_data_directory_instead_of_embedded_resources() {
    let app_dir = PathBuf::from("/Applications/iLab GPT CONJURE.app/Contents/Resources/app");
    let data_dir = default_data_dir_for_app(&app_dir);

    assert!(data_dir.ends_with(Path::new("iLab GPT CONJURE")));
    assert!(!data_dir.starts_with("/Applications/iLab GPT CONJURE.app"));
    assert_ne!(data_dir, app_dir.join("output"));
}

#[test]
fn display_brand_is_decoupled_from_legacy_storage_identity() {
    assert_eq!(APP_NAME, "iLab CONJURE");
    assert_eq!(LEGACY_DATA_DIR_NAME, "iLab GPT CONJURE");
    assert!(standard_app_data_dir().ends_with(LEGACY_DATA_DIR_NAME));
}

#[test]
fn migration_copies_legacy_portable_data_without_moving_or_overwriting() {
    let root = env::temp_dir().join(format!(
        "ilab-conjure-migration-test-{}",
        std::process::id()
    ));
    let _ = fs::remove_dir_all(&root);
    let legacy = root.join("old").join("data");
    let target = root.join("new-data");
    fs::create_dir_all(legacy.join("webui-inputs").join("gallery")).unwrap();
    fs::write(legacy.join("webui-api-settings.json"), "{}\n").unwrap();
    fs::write(
        legacy
            .join("webui-inputs")
            .join("gallery")
            .join("asset.txt"),
        "asset\n",
    )
    .unwrap();

    migrate_legacy_portable_data(&legacy, &target).unwrap();

    assert!(legacy.join("webui-api-settings.json").exists());
    assert!(target.join("webui-api-settings.json").exists());
    assert!(target
        .join("webui-inputs")
        .join("gallery")
        .join("asset.txt")
        .exists());
    assert!(migration_marker_path(&target).exists());

    fs::write(target.join("webui-settings.json"), "{}\n").unwrap();
    let result = migrate_legacy_portable_data(&legacy, &target);
    assert!(result.is_err());

    let _ = fs::remove_dir_all(&root);
}

#[test]
fn migration_prompt_plan_allows_manual_choice_when_no_data_was_detected() {
    let zh = migration_prompt_plan(None, AppLocale::ZhCn);
    assert_eq!(zh.title, "迁移旧版数据");
    assert_eq!(zh.skip_button, "跳过");
    assert_eq!(zh.choose_button, "选择旧版本目录");
    assert_eq!(zh.detected_button, None);
    assert!(zh.message.contains("没有自动检测到旧 portable data/"));
    assert!(zh.message.contains("0.5.4 或更早版本"));

    let detected = Path::new("/tmp/iLab GPT CONJURE/data");
    let en = migration_prompt_plan(Some(detected), AppLocale::En);
    assert_eq!(en.title, "Migrate Portable Data");
    assert_eq!(en.choose_button, "Choose Old Folder");
    assert_eq!(en.detected_button, Some("Copy Detected Data"));
    assert!(en.message.contains("/tmp/iLab GPT CONJURE/data"));
    assert!(en.message.contains("will not be moved or deleted"));
}

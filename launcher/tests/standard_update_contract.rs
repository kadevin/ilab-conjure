use ilab_conjure_launcher::standard_update::{
    build_privileged_replace_command, parse_standard_update_args, replace_staged_app_transaction,
    standard_app_bundle_path, validate_mounted_standard_app, verify_sha256_file,
};
use std::fs;
use std::path::{Path, PathBuf};
use std::time::{SystemTime, UNIX_EPOCH};

fn temp_root(label: &str) -> PathBuf {
    let stamp = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap()
        .as_nanos();
    std::env::temp_dir().join(format!(
        "ilab-standard-update-{label}-{}-{stamp}",
        std::process::id()
    ))
}

fn valid_args(target: &Path, log_path: &Path) -> Vec<String> {
    vec![
        "--url".to_string(),
        "https://github.com/kadevin/ilab-conjure/releases/download/v0.6.2/iLab-GPT-CONJURE-macos-arm64-0.6.2.dmg".to_string(),
        "--expected-sha256".to_string(),
        "a".repeat(64),
        "--expected-version".to_string(),
        "0.6.2".to_string(),
        "--target-app".to_string(),
        target.display().to_string(),
        "--parent-pid".to_string(),
        "42".to_string(),
        "--log-path".to_string(),
        log_path.display().to_string(),
        "--locale".to_string(),
        "zh-CN".to_string(),
    ]
}

#[test]
fn parses_only_safe_standard_update_arguments() {
    let root = temp_root("args");
    let target = root.join("iLab GPT CONJURE.app");
    let log_path = root.join("update.log");
    let request = parse_standard_update_args(valid_args(&target, &log_path)).unwrap();

    assert_eq!(request.expected_version, "0.6.2");
    assert_eq!(request.expected_sha256, "a".repeat(64));
    assert_eq!(request.target_app, target);
    assert_eq!(request.parent_pid, 42);
    assert_eq!(request.locale, "zh-CN");

    let mut insecure = valid_args(&request.target_app, &log_path);
    insecure[1] = "http://example.test/update.dmg".to_string();
    assert!(parse_standard_update_args(insecure).is_err());

    let mut bad_hash = valid_args(&request.target_app, &log_path);
    bad_hash[3] = "not-a-sha256".to_string();
    assert!(parse_standard_update_args(bad_hash).is_err());
}

#[test]
fn resolves_installed_bundle_from_embedded_standard_app_dir() {
    let app_dir = Path::new("/Applications/iLab GPT CONJURE.app/Contents/Resources/app");
    assert_eq!(
        standard_app_bundle_path(app_dir),
        Some(PathBuf::from("/Applications/iLab GPT CONJURE.app"))
    );
    assert_eq!(standard_app_bundle_path(Path::new("/tmp/source")), None);
}

#[test]
fn verifies_download_sha256_and_rejects_tampering() {
    let root = temp_root("sha");
    fs::create_dir_all(&root).unwrap();
    let package = root.join("update.dmg");
    fs::write(&package, b"abc").unwrap();

    verify_sha256_file(
        &package,
        "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad",
    )
    .unwrap();
    fs::write(&package, b"tampered").unwrap();
    assert!(verify_sha256_file(
        &package,
        "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad",
    )
    .is_err());

    let _ = fs::remove_dir_all(root);
}

#[test]
fn replacement_transaction_swaps_only_the_app_bundle() {
    let root = temp_root("replace");
    let target = root.join("iLab GPT CONJURE.app");
    let staged = root.join(".iLab GPT CONJURE.update.app");
    let user_data = root.join("Application Support").join("task.json");
    fs::create_dir_all(&target).unwrap();
    fs::create_dir_all(&staged).unwrap();
    fs::create_dir_all(user_data.parent().unwrap()).unwrap();
    fs::write(target.join("version.txt"), "old").unwrap();
    fs::write(staged.join("version.txt"), "new").unwrap();
    fs::write(&user_data, "keep").unwrap();

    replace_staged_app_transaction(&target, &staged).unwrap();

    assert_eq!(
        fs::read_to_string(target.join("version.txt")).unwrap(),
        "new"
    );
    assert_eq!(fs::read_to_string(&user_data).unwrap(), "keep");
    assert!(!staged.exists());
    assert!(!root.join(".iLab GPT CONJURE.backup.app").exists());

    let _ = fs::remove_dir_all(root);
}

#[test]
fn privileged_replace_command_quotes_paths_and_contains_rollback() {
    let source = Path::new("/tmp/new user's app.app");
    let target = Path::new("/Applications/iLab GPT CONJURE.app");
    let command = build_privileged_replace_command(source, target).unwrap();

    assert!(command.contains("user'\"'\"'s app.app"));
    assert!(command.contains("/usr/bin/ditto"));
    assert!(command.contains("/bin/mv"));
    assert!(command.contains("restore_status"));
    assert!(!command.contains("curl"));
    assert!(!command.contains("http"));
}

#[cfg(target_os = "macos")]
#[test]
fn validates_mounted_app_identity_version_and_required_helpers() {
    let root = temp_root("bundle");
    let app = root.join("iLab GPT CONJURE.app");
    let contents = app.join("Contents");
    let macos = contents.join("MacOS");
    let helpers = contents.join("Helpers");
    fs::create_dir_all(&macos).unwrap();
    fs::create_dir_all(&helpers).unwrap();
    fs::write(
        contents.join("Info.plist"),
        r#"<?xml version="1.0" encoding="UTF-8"?>
<plist version="1.0"><dict>
<key>CFBundleIdentifier</key><string>com.ilab.gpt-conjure</string>
<key>CFBundleShortVersionString</key><string>0.6.2</string>
</dict></plist>"#,
    )
    .unwrap();
    fs::write(macos.join("ilab-conjure-launcher"), "launcher").unwrap();
    fs::write(helpers.join("ilab-conjure-standard-updater"), "updater").unwrap();

    validate_mounted_standard_app(&app, "v0.6.2").unwrap();
    assert!(validate_mounted_standard_app(&app, "0.6.3").is_err());
    fs::remove_file(helpers.join("ilab-conjure-standard-updater")).unwrap();
    assert!(validate_mounted_standard_app(&app, "0.6.2").is_err());

    let _ = fs::remove_dir_all(root);
}

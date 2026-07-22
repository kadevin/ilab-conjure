use anyhow::{anyhow, bail, Context, Result};
use sha2::{Digest, Sha256};
use std::collections::BTreeMap;
use std::fs::{self, File, OpenOptions};
use std::io::{Read, Write};
use std::path::{Path, PathBuf};
use std::process::{Command, Stdio};
use std::thread;
use std::time::{Duration, SystemTime, UNIX_EPOCH};

pub const STANDARD_APP_BUNDLE_NAME: &str = "iLab GPT CONJURE.app";
pub const STANDARD_APP_BUNDLE_ID: &str = "com.ilab.gpt-conjure";
pub const STANDARD_UPDATER_EXECUTABLE: &str = "ilab-conjure-standard-updater";
const STANDARD_LAUNCHER_EXECUTABLE: &str = "ilab-conjure-launcher";
const HANDOFF_PREFIX: &str = "ilab-gpt-conjure-standard-update-handoff-";
const WORKSPACE_PREFIX: &str = "ilab-gpt-conjure-standard-update-work-";
const PARENT_EXIT_TIMEOUT: Duration = Duration::from_secs(60);

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct StandardUpdateRequest {
    pub url: String,
    pub expected_sha256: String,
    pub expected_version: String,
    pub target_app: PathBuf,
    pub parent_pid: u32,
    pub log_path: PathBuf,
    pub locale: String,
}

pub fn parse_standard_update_args<I, S>(args: I) -> Result<StandardUpdateRequest>
where
    I: IntoIterator<Item = S>,
    S: Into<String>,
{
    let mut values = BTreeMap::new();
    let mut args = args.into_iter().map(Into::into);
    while let Some(flag) = args.next() {
        if !matches!(
            flag.as_str(),
            "--url"
                | "--expected-sha256"
                | "--expected-version"
                | "--target-app"
                | "--parent-pid"
                | "--log-path"
                | "--locale"
        ) {
            bail!("unknown standard updater argument {flag}");
        }
        let value = args
            .next()
            .ok_or_else(|| anyhow!("{flag} requires a value"))?;
        if values.insert(flag.clone(), value).is_some() {
            bail!("duplicate standard updater argument {flag}");
        }
    }

    let take = |name: &str| -> Result<String> {
        values
            .get(name)
            .cloned()
            .ok_or_else(|| anyhow!("missing standard updater argument {name}"))
    };
    let url = take("--url")?;
    if !url.starts_with("https://") || url.chars().any(char::is_whitespace) {
        bail!("standard update URL must use HTTPS and contain no whitespace");
    }
    let expected_sha256 = take("--expected-sha256")?.to_ascii_lowercase();
    if !is_sha256_hex(&expected_sha256) {
        bail!("standard update SHA256 must be 64 hexadecimal characters");
    }
    let expected_version = normalize_release_version(&take("--expected-version")?)?;
    let target_app = PathBuf::from(take("--target-app")?);
    if target_app.file_name().and_then(|name| name.to_str()) != Some(STANDARD_APP_BUNDLE_NAME) {
        bail!("standard update target must be {STANDARD_APP_BUNDLE_NAME}");
    }
    if target_app.starts_with("/Volumes") {
        bail!("standard App must be copied out of the DMG before it can update itself");
    }
    let parent_pid = take("--parent-pid")?
        .parse::<u32>()
        .context("standard updater parent PID is invalid")?;
    if parent_pid == 0 {
        bail!("standard updater parent PID must be positive");
    }
    let log_path = PathBuf::from(take("--log-path")?);
    let locale = normalize_update_locale(&take("--locale")?);

    Ok(StandardUpdateRequest {
        url,
        expected_sha256,
        expected_version,
        target_app,
        parent_pid,
        log_path,
        locale,
    })
}

pub fn standard_app_bundle_path(app_dir: &Path) -> Option<PathBuf> {
    if app_dir.file_name().and_then(|name| name.to_str()) != Some("app") {
        return None;
    }
    let resources = app_dir.parent()?;
    if resources.file_name().and_then(|name| name.to_str()) != Some("Resources") {
        return None;
    }
    let contents = resources.parent()?;
    if contents.file_name().and_then(|name| name.to_str()) != Some("Contents") {
        return None;
    }
    let bundle = contents.parent()?;
    (bundle.file_name().and_then(|name| name.to_str()) == Some(STANDARD_APP_BUNDLE_NAME))
        .then(|| bundle.to_path_buf())
}

pub fn standard_update_helper_path(app_dir: &Path) -> Option<PathBuf> {
    let bundle = standard_app_bundle_path(app_dir)?;
    if bundle.starts_with("/Volumes") {
        return None;
    }
    let helper = bundle
        .join("Contents")
        .join("Helpers")
        .join(STANDARD_UPDATER_EXECUTABLE);
    helper.is_file().then_some(helper)
}

pub fn launch_standard_updater(helper: &Path, request: &StandardUpdateRequest) -> Result<()> {
    if !helper.is_file() {
        bail!(
            "standard updater helper was not found at {}",
            helper.display()
        );
    }
    let handoff_dir = create_private_temp_dir(HANDOFF_PREFIX)?;
    let handoff_helper = handoff_dir.join(STANDARD_UPDATER_EXECUTABLE);
    fs::copy(helper, &handoff_helper).with_context(|| {
        format!(
            "failed to copy standard updater helper from {}",
            helper.display()
        )
    })?;
    set_executable_permissions(&handoff_helper)?;

    let spawn_result = Command::new(&handoff_helper)
        .args(standard_update_handoff_args(request))
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .spawn()
        .context("failed to start standard updater helper");
    if spawn_result.is_err() {
        let _ = fs::remove_dir_all(&handoff_dir);
    }
    spawn_result.map(|_| ())
}

fn standard_update_handoff_args(request: &StandardUpdateRequest) -> Vec<String> {
    vec![
        "--url".to_string(),
        request.url.clone(),
        "--expected-sha256".to_string(),
        request.expected_sha256.clone(),
        "--expected-version".to_string(),
        request.expected_version.clone(),
        "--target-app".to_string(),
        request.target_app.display().to_string(),
        "--parent-pid".to_string(),
        request.parent_pid.to_string(),
        "--log-path".to_string(),
        request.log_path.display().to_string(),
        "--locale".to_string(),
        request.locale.clone(),
    ]
}

pub fn run_standard_updater<I, S>(args: I) -> Result<()>
where
    I: IntoIterator<Item = S>,
    S: Into<String>,
{
    let request = parse_standard_update_args(args)?;
    append_update_log(&request.log_path, "standard update started")?;
    let result = run_standard_update_request(&request);
    if let Err(error) = &result {
        let _ = append_update_log(&request.log_path, &format!("update failed: {error:#}"));
        if !process_is_alive(request.parent_pid) && request.target_app.is_dir() {
            let _ = relaunch_standard_app(&request.target_app);
        }
    }
    result
}

fn run_standard_update_request(request: &StandardUpdateRequest) -> Result<()> {
    #[cfg(not(target_os = "macos"))]
    {
        let _ = request;
        bail!("standard DMG updates are only supported on macOS");
    }

    #[cfg(target_os = "macos")]
    {
        let messages = updater_messages(&request.locale);
        show_standard_update_notification(messages.start);
        wait_for_process_exit(request.parent_pid, PARENT_EXIT_TIMEOUT)
            .context("launcher did not exit before the update timeout")?;
        let workspace = create_private_temp_dir(WORKSPACE_PREFIX)?;
        let _workspace_cleanup = RemoveDirOnDrop(workspace.clone());
        let dmg_path = workspace.join("update.dmg");
        download_update(&request.url, &dmg_path, &request.log_path)?;
        verify_sha256_file(&dmg_path, &request.expected_sha256)?;
        append_update_log(&request.log_path, "download SHA256 verified")?;

        let mountpoint = workspace.join("mounted");
        fs::create_dir_all(&mountpoint)?;
        {
            let _mount = mount_dmg(&dmg_path, &mountpoint)?;
            let source_app = mountpoint.join(STANDARD_APP_BUNDLE_NAME);
            validate_mounted_standard_app(&source_app, &request.expected_version)?;
            verify_mounted_app_signature_and_architecture(&source_app)?;
            install_standard_app(&source_app, &request.target_app, &request.log_path)?;
        }

        relaunch_standard_app(&request.target_app)?;
        append_update_log(
            &request.log_path,
            &format!("updated successfully to {}", request.expected_version),
        )?;
        show_standard_update_notification(messages.success);
        Ok(())
    }
}

pub fn verify_sha256_file(path: &Path, expected_sha256: &str) -> Result<()> {
    if !is_sha256_hex(expected_sha256) {
        bail!("expected SHA256 is invalid");
    }
    let mut file = File::open(path)
        .with_context(|| format!("failed to open update package {}", path.display()))?;
    let mut hasher = Sha256::new();
    let mut buffer = [0_u8; 64 * 1024];
    loop {
        let count = file.read(&mut buffer)?;
        if count == 0 {
            break;
        }
        hasher.update(&buffer[..count]);
    }
    let actual = format!("{:x}", hasher.finalize());
    if !actual.eq_ignore_ascii_case(expected_sha256) {
        bail!("update package SHA256 mismatch: expected {expected_sha256}, got {actual}");
    }
    Ok(())
}

pub fn replace_staged_app_transaction(target: &Path, staged: &Path) -> Result<()> {
    validate_target_and_staging(target, staged)?;
    if !target.is_dir() {
        bail!("installed App was not found at {}", target.display());
    }
    if !staged.is_dir() {
        bail!("staged App was not found at {}", staged.display());
    }
    let backup = backup_path_for_target(target)?;
    remove_path_if_exists(&backup)?;
    fs::rename(target, &backup).with_context(|| {
        format!(
            "failed to move installed App {} to backup",
            target.display()
        )
    })?;
    if let Err(error) = fs::rename(staged, target) {
        let restore = fs::rename(&backup, target);
        return match restore {
            Ok(()) => Err(error).context("failed to move staged App into place; old App restored"),
            Err(restore_error) => Err(anyhow!(
                "failed to install staged App ({error}); rollback also failed ({restore_error})"
            )),
        };
    }
    let _ = remove_path_if_exists(&backup);
    Ok(())
}

pub fn build_privileged_replace_command(source: &Path, target: &Path) -> Result<String> {
    if source == target
        || target.file_name().and_then(|name| name.to_str()) != Some(STANDARD_APP_BUNDLE_NAME)
    {
        bail!("refusing unsafe standard App replacement paths");
    }
    let staging = staging_path_for_target(target)?;
    let backup = backup_path_for_target(target)?;
    Ok(format!(
        "set -e; /bin/rm -rf {staging} {backup}; /usr/bin/ditto {source} {staging}; /bin/mv {target} {backup}; restore_status=0; /bin/mv {staging} {target} || restore_status=$?; if [ \"$restore_status\" -ne 0 ]; then /bin/mv {backup} {target}; exit \"$restore_status\"; fi; /bin/rm -rf {backup} || true",
        source = shell_quote(source.as_os_str().to_string_lossy().as_ref()),
        target = shell_quote(target.as_os_str().to_string_lossy().as_ref()),
        staging = shell_quote(staging.as_os_str().to_string_lossy().as_ref()),
        backup = shell_quote(backup.as_os_str().to_string_lossy().as_ref()),
    ))
}

pub fn standard_update_locale_hint(args: &[String]) -> &str {
    args.windows(2)
        .find(|pair| pair[0] == "--locale")
        .map(|pair| pair[1].as_str())
        .unwrap_or("en")
}

pub fn show_standard_update_error(message: &str, locale: &str) {
    #[cfg(target_os = "macos")]
    {
        let script = format!(
            "display dialog {} with title {} buttons {{\"OK\"}} default button \"OK\" with icon stop",
            apple_script_string(message),
            apple_script_string(updater_messages(locale).error_title),
        );
        let _ = Command::new("/usr/bin/osascript")
            .args(["-e", &script])
            .status();
    }
    #[cfg(not(target_os = "macos"))]
    eprintln!("iLab CONJURE update failed: {message}");
}

pub fn cleanup_standard_updater_handoff() {
    let Ok(executable) = std::env::current_exe() else {
        return;
    };
    let Some(parent) = executable.parent() else {
        return;
    };
    let Some(name) = parent.file_name().and_then(|name| name.to_str()) else {
        return;
    };
    if name.starts_with(HANDOFF_PREFIX) {
        let _ = fs::remove_dir_all(parent);
    }
}

fn install_standard_app(source_app: &Path, target_app: &Path, log_path: &Path) -> Result<()> {
    let parent = target_app
        .parent()
        .ok_or_else(|| anyhow!("standard App target has no parent directory"))?;
    if directory_is_writable(parent) {
        let staging = staging_path_for_target(target_app)?;
        remove_path_if_exists(&staging)?;
        run_command(
            Command::new("/usr/bin/ditto").arg(source_app).arg(&staging),
            "failed to stage updated App",
        )?;
        replace_staged_app_transaction(target_app, &staging)?;
        append_update_log(
            log_path,
            "installed update without administrator authorization",
        )?;
        return Ok(());
    }

    let command = build_privileged_replace_command(source_app, target_app)?;
    let script = format!(
        "do shell script {} with administrator privileges",
        apple_script_string(&command)
    );
    run_command(
        Command::new("/usr/bin/osascript").args(["-e", &script]),
        "administrator-authorized App replacement failed",
    )?;
    append_update_log(
        log_path,
        "installed update with administrator authorization",
    )?;
    Ok(())
}

pub fn validate_mounted_standard_app(app: &Path, expected_version: &str) -> Result<()> {
    if !app.is_dir() {
        bail!("verified DMG does not contain {STANDARD_APP_BUNDLE_NAME}");
    }
    let plist = app.join("Contents").join("Info.plist");
    let bundle_id = plist_string(&plist, "CFBundleIdentifier")?;
    if bundle_id != STANDARD_APP_BUNDLE_ID {
        bail!("update App bundle identifier mismatch: {bundle_id}");
    }
    let version = normalize_release_version(&plist_string(&plist, "CFBundleShortVersionString")?)?;
    if version != normalize_release_version(expected_version)? {
        bail!("update App version mismatch: expected {expected_version}, got {version}");
    }
    let launcher = app
        .join("Contents")
        .join("MacOS")
        .join(STANDARD_LAUNCHER_EXECUTABLE);
    let updater = app
        .join("Contents")
        .join("Helpers")
        .join(STANDARD_UPDATER_EXECUTABLE);
    if !launcher.is_file() || !updater.is_file() {
        bail!("update App is missing its launcher or standard updater helper");
    }
    Ok(())
}

fn verify_mounted_app_signature_and_architecture(app: &Path) -> Result<()> {
    run_command(
        Command::new("/usr/bin/codesign")
            .args(["--verify", "--deep", "--strict"])
            .arg(app),
        "update App code signature verification failed",
    )?;
    let launcher = app
        .join("Contents")
        .join("MacOS")
        .join(STANDARD_LAUNCHER_EXECUTABLE);
    let updater = app
        .join("Contents")
        .join("Helpers")
        .join(STANDARD_UPDATER_EXECUTABLE);
    let expected_arch = if cfg!(target_arch = "aarch64") {
        "arm64"
    } else if cfg!(target_arch = "x86_64") {
        "x86_64"
    } else {
        bail!(
            "unsupported updater architecture {}",
            std::env::consts::ARCH
        );
    };

    for (label, executable) in [
        ("launcher", launcher.as_path()),
        ("standard updater helper", updater.as_path()),
    ] {
        let output = Command::new("/usr/bin/lipo")
            .arg("-archs")
            .arg(executable)
            .output()
            .with_context(|| format!("failed to inspect update App {label} architecture"))?;
        if !output.status.success() {
            bail!(
                "failed to inspect update App {label} architecture: {}",
                String::from_utf8_lossy(&output.stderr).trim()
            );
        }
        let architectures = String::from_utf8(output.stdout)?;
        if !architectures
            .split_whitespace()
            .any(|arch| arch == expected_arch)
        {
            bail!(
                "update App {label} architecture mismatch: expected {expected_arch}, got {}",
                architectures.trim()
            );
        }
    }
    Ok(())
}

fn plist_string(plist: &Path, key: &str) -> Result<String> {
    let output = Command::new("/usr/bin/plutil")
        .args(["-extract", key, "raw", "-o", "-"])
        .arg(plist)
        .output()
        .with_context(|| format!("failed to read {key} from {}", plist.display()))?;
    if !output.status.success() {
        bail!(
            "failed to read {} from {}: {}",
            key,
            plist.display(),
            String::from_utf8_lossy(&output.stderr).trim()
        );
    }
    Ok(String::from_utf8(output.stdout)?.trim().to_string())
}

fn download_update(url: &str, destination: &Path, log_path: &Path) -> Result<()> {
    append_update_log(log_path, &format!("downloading {url}"))?;
    run_command(
        Command::new("/usr/bin/curl")
            .args(["--fail", "--location", "--show-error", "--output"])
            .arg(destination)
            .arg(url),
        "failed to download standard update DMG",
    )
}

struct MountedDmg {
    mountpoint: PathBuf,
}

impl Drop for MountedDmg {
    fn drop(&mut self) {
        let _ = Command::new("/usr/bin/hdiutil")
            .arg("detach")
            .arg(&self.mountpoint)
            .arg("-force")
            .stdout(Stdio::null())
            .stderr(Stdio::null())
            .status();
    }
}

fn mount_dmg(dmg: &Path, mountpoint: &Path) -> Result<MountedDmg> {
    run_command(
        Command::new("/usr/bin/hdiutil")
            .args(["attach", "-readonly", "-nobrowse", "-mountpoint"])
            .arg(mountpoint)
            .arg(dmg),
        "failed to mount standard update DMG",
    )?;
    Ok(MountedDmg {
        mountpoint: mountpoint.to_path_buf(),
    })
}

fn relaunch_standard_app(target: &Path) -> Result<()> {
    run_command(
        Command::new("/usr/bin/open").arg("-n").arg(target),
        "failed to restart updated App",
    )
}

fn wait_for_process_exit(pid: u32, timeout: Duration) -> Result<()> {
    let started = SystemTime::now();
    loop {
        if !process_is_alive(pid) {
            return Ok(());
        }
        if started.elapsed().unwrap_or_default() >= timeout {
            bail!("process {pid} is still running");
        }
        thread::sleep(Duration::from_millis(200));
    }
}

fn process_is_alive(pid: u32) -> bool {
    Command::new("/bin/kill")
        .args(["-0", &pid.to_string()])
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .status()
        .map(|status| status.success())
        .unwrap_or(false)
}

fn directory_is_writable(directory: &Path) -> bool {
    let probe = directory.join(format!(
        ".ilab-conjure-update-write-test-{}",
        std::process::id()
    ));
    match OpenOptions::new().write(true).create_new(true).open(&probe) {
        Ok(_) => {
            let _ = fs::remove_file(probe);
            true
        }
        Err(_) => false,
    }
}

fn validate_target_and_staging(target: &Path, staged: &Path) -> Result<()> {
    if target == staged || target.parent() != staged.parent() {
        bail!("target and staged App must be distinct siblings");
    }
    if target.file_name().and_then(|name| name.to_str()) != Some(STANDARD_APP_BUNDLE_NAME) {
        bail!("refusing to replace unexpected App target");
    }
    Ok(())
}

fn staging_path_for_target(target: &Path) -> Result<PathBuf> {
    Ok(target
        .parent()
        .ok_or_else(|| anyhow!("standard App target has no parent directory"))?
        .join(".iLab GPT CONJURE.update.app"))
}

fn backup_path_for_target(target: &Path) -> Result<PathBuf> {
    Ok(target
        .parent()
        .ok_or_else(|| anyhow!("standard App target has no parent directory"))?
        .join(".iLab GPT CONJURE.backup.app"))
}

fn remove_path_if_exists(path: &Path) -> Result<()> {
    if !path.exists() {
        return Ok(());
    }
    let metadata = fs::symlink_metadata(path)?;
    if metadata.is_dir() {
        fs::remove_dir_all(path)?;
    } else {
        fs::remove_file(path)?;
    }
    Ok(())
}

fn create_private_temp_dir(prefix: &str) -> Result<PathBuf> {
    let stamp = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default()
        .as_nanos();
    let path = std::env::temp_dir().join(format!("{prefix}{}-{stamp}", std::process::id()));
    fs::create_dir(&path).with_context(|| {
        format!(
            "failed to create private update directory {}",
            path.display()
        )
    })?;
    set_private_directory_permissions(&path)?;
    Ok(path)
}

#[cfg(unix)]
fn set_private_directory_permissions(path: &Path) -> Result<()> {
    use std::os::unix::fs::PermissionsExt;
    fs::set_permissions(path, fs::Permissions::from_mode(0o700))?;
    Ok(())
}

#[cfg(not(unix))]
fn set_private_directory_permissions(_path: &Path) -> Result<()> {
    Ok(())
}

#[cfg(unix)]
fn set_executable_permissions(path: &Path) -> Result<()> {
    use std::os::unix::fs::PermissionsExt;
    fs::set_permissions(path, fs::Permissions::from_mode(0o700))?;
    Ok(())
}

#[cfg(not(unix))]
fn set_executable_permissions(_path: &Path) -> Result<()> {
    Ok(())
}

fn run_command(command: &mut Command, context: &str) -> Result<()> {
    let output = command.output().with_context(|| context.to_string())?;
    if !output.status.success() {
        bail!(
            "{}: {}",
            context,
            String::from_utf8_lossy(&output.stderr).trim()
        );
    }
    Ok(())
}

fn append_update_log(path: &Path, message: &str) -> Result<()> {
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent)?;
    }
    let timestamp = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default()
        .as_secs();
    let mut log = OpenOptions::new().create(true).append(true).open(path)?;
    writeln!(log, "[{timestamp}] {message}")?;
    Ok(())
}

fn normalize_release_version(value: &str) -> Result<String> {
    let clean = value.trim().trim_start_matches('v').trim_start_matches('V');
    let parts = clean.split('.').collect::<Vec<_>>();
    if parts.len() != 3
        || parts
            .iter()
            .any(|part| part.is_empty() || !part.chars().all(|ch| ch.is_ascii_digit()))
    {
        bail!("standard update version must be a three-part semantic version");
    }
    Ok(clean.to_string())
}

fn normalize_update_locale(value: &str) -> String {
    let clean = value.trim().replace('_', "-").to_ascii_lowercase();
    if clean.starts_with("zh-cn") || clean.starts_with("zh-hans") || clean == "zh" {
        "zh-CN".to_string()
    } else if clean.starts_with("zh-tw") || clean.starts_with("zh-hant") {
        "zh-TW".to_string()
    } else if clean.starts_with("zh-hk") || clean.starts_with("zh-mo") {
        "zh-HK".to_string()
    } else {
        "en".to_string()
    }
}

struct UpdaterMessages {
    start: &'static str,
    success: &'static str,
    error_title: &'static str,
}

fn updater_messages(locale: &str) -> UpdaterMessages {
    match normalize_update_locale(locale).as_str() {
        "zh-CN" => UpdaterMessages {
            start: "正在下载并安装新版，应用将在完成后重新启动。",
            success: "更新完成，已重新启动 iLab CONJURE。",
            error_title: "iLab CONJURE 更新失败",
        },
        "zh-TW" | "zh-HK" => UpdaterMessages {
            start: "正在下載並安裝新版，應用程式將在完成後重新啟動。",
            success: "更新完成，已重新啟動 iLab CONJURE。",
            error_title: "iLab CONJURE 更新失敗",
        },
        _ => UpdaterMessages {
            start: "Downloading and installing the update. The app will relaunch when finished.",
            success: "Update complete. iLab CONJURE has been relaunched.",
            error_title: "iLab CONJURE Update Failed",
        },
    }
}

fn is_sha256_hex(value: &str) -> bool {
    value.len() == 64 && value.chars().all(|ch| ch.is_ascii_hexdigit())
}

fn shell_quote(value: &str) -> String {
    format!("'{}'", value.replace('\'', "'\"'\"'"))
}

fn apple_script_string(value: &str) -> String {
    let mut result = String::from("\"");
    for ch in value.chars() {
        match ch {
            '\"' => result.push_str("\\\""),
            '\\' => result.push_str("\\\\"),
            '\n' => result.push_str("\" & return & \""),
            '\r' => {}
            _ => result.push(ch),
        }
    }
    result.push('\"');
    result
}

fn show_standard_update_notification(message: &str) {
    let script = format!(
        "display notification {} with title {}",
        apple_script_string(message),
        apple_script_string("iLab CONJURE"),
    );
    let _ = Command::new("/usr/bin/osascript")
        .args(["-e", &script])
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .status();
}

struct RemoveDirOnDrop(PathBuf);

impl Drop for RemoveDirOnDrop {
    fn drop(&mut self) {
        let _ = fs::remove_dir_all(&self.0);
    }
}

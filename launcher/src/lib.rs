use anyhow::{anyhow, Context, Result};
use std::{
    env,
    fs::{self, File, OpenOptions},
    io::{Read, Write},
    net::TcpStream,
    path::{Path, PathBuf},
    process::{Child, Command, Stdio},
    thread,
    time::{Duration, Instant, SystemTime, UNIX_EPOCH},
};

mod locale;
pub mod standard_update;
pub use locale::{
    detect_system_locale, localized_about_labels, localized_menu_labels, localized_update_labels,
    read_locale_preference, resolve_launcher_locale, AboutLabels, AppLocale, MenuLabels,
    UpdateLabels,
};
mod update_manifest;
pub use update_manifest::verify_update_manifest_file;
use update_manifest::version_label_from_raw;
#[cfg(test)]
use update_manifest::{
    compare_version_labels, current_update_platform_key, verify_update_manifest_signature_with_key,
    UpdatePlatform, UpdateSignature,
};
use update_manifest::{
    parse_update_manifest_payload, update_check_from_manifest, verify_update_manifest_signature,
    UpdateAvailability, UpdateCheck, UpdateManifest, UpdatePackageKind,
};

pub const APP_NAME: &str = "iLab CONJURE";
pub const LEGACY_DATA_DIR_NAME: &str = "iLab GPT CONJURE";
pub const DEFAULT_PORT: u16 = 8787;
pub const WEBUI_URL: &str = "http://127.0.0.1:8787/";
pub const HEALTH_PATH: &str = "/api/health";
pub const LOG_FILE_NAME: &str = "webui-server.log";
pub const PROJECT_URL: &str = "https://github.com/kadevin/ilab-conjure";
pub const RELEASES_URL: &str = "https://github.com/kadevin/ilab-conjure/releases/latest";
pub const LATEST_UPDATE_MANIFEST_URL: &str =
    "https://github.com/kadevin/ilab-conjure/releases/latest/download/latest.json";
pub const UPDATE_SIGNING_PUBLIC_KEY_B64: &str =
    include_str!("../assets/update-signing-public-key.b64");
pub const DEFAULT_LOCALE_TAG: &str = "zh-CN";

const WAIT_TIMEOUT: Duration = Duration::from_secs(30);
const HEALTH_POLL_INTERVAL: Duration = Duration::from_millis(500);

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct AboutInfo {
    pub version_label: String,
    pub project_url: &'static str,
    pub releases_url: &'static str,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum AboutAction {
    Close,
    OpenProject,
    CheckUpdates,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum UpdateInstallAction {
    None,
    PortableUpdater,
    StandardMacUpdater,
    DownloadPackage,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum UpdateDialogAction {
    Close,
    OpenRelease,
    InstallUpdate,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum UpdateOutcome {
    Continue,
    LaunchedUpdater,
}

#[derive(Debug, Clone)]
pub struct LauncherConfig {
    pub app_dir: PathBuf,
    pub data_dir: PathBuf,
    pub input_root: PathBuf,
    pub output_root: PathBuf,
    pub source_data_root: PathBuf,
    pub log_path: PathBuf,
    pub port: u16,
}

impl LauncherConfig {
    pub fn detect() -> Result<Self> {
        let app_dir = detect_app_dir()?;
        let data_dir = env::var_os("ILAB_CONJURE_DATA_DIR")
            .map(PathBuf::from)
            .unwrap_or_else(|| default_data_dir_for_app(&app_dir));
        Self::from_dirs(app_dir, data_dir, DEFAULT_PORT)
    }

    pub fn from_dirs(app_dir: PathBuf, data_dir: PathBuf, port: u16) -> Result<Self> {
        let data_dir = data_dir.canonicalize().unwrap_or_else(|_| data_dir.clone());
        let output_root = data_dir.join("webui-outputs");
        Ok(Self {
            app_dir,
            input_root: data_dir.join("webui-inputs"),
            source_data_root: output_root.join("source-data"),
            log_path: output_root.join(LOG_FILE_NAME),
            output_root,
            data_dir,
            port,
        })
    }

    pub fn url(&self) -> String {
        format!("http://127.0.0.1:{}/", self.port)
    }

    pub fn health_url(&self) -> String {
        format!("{}api/health", self.url())
    }

    pub fn settings_url(&self) -> String {
        format!("{}?settings=1", self.url())
    }

    pub fn history_url(&self) -> String {
        format!("{}history", self.url())
    }

    pub fn auth_settings_path(&self) -> PathBuf {
        self.data_dir.join("webui-auth-settings.json")
    }

    pub fn api_settings_path(&self) -> PathBuf {
        self.data_dir.join("webui-api-settings.json")
    }

    pub fn webui_settings_path(&self) -> PathBuf {
        self.data_dir.join("webui-settings.json")
    }

    pub fn about_info(&self) -> AboutInfo {
        AboutInfo {
            version_label: launcher_version_label(&self.app_dir),
            project_url: PROJECT_URL,
            releases_url: RELEASES_URL,
        }
    }

    pub fn uvicorn_app(&self) -> &'static str {
        if self.app_dir.join("standard_webui_app.py").exists() {
            "standard_webui_app:app"
        } else if self.app_dir.join("portable_webui_app.py").exists() {
            "portable_webui_app:app"
        } else {
            "codex_image.webui.app:app"
        }
    }
}

pub fn launcher_version_label(app_dir: &Path) -> String {
    read_portable_version(app_dir)
        .or_else(|| read_source_version(app_dir))
        .map(|version| version_label_from_raw(&version))
        .unwrap_or_else(|| version_label_from_raw(env!("CARGO_PKG_VERSION")))
}

fn read_portable_version(app_dir: &Path) -> Option<String> {
    let version_path = app_dir.parent()?.join("portable-version.txt");
    first_nonempty_line(&version_path)
}

fn read_source_version(app_dir: &Path) -> Option<String> {
    let text = fs::read_to_string(app_dir.join("codex_image").join("version.py")).ok()?;
    text.lines().find_map(|line| {
        let trimmed = line.trim();
        if !trimmed.starts_with("APP_VERSION") {
            return None;
        }
        let (_, value) = trimmed.split_once('=')?;
        quoted_python_string(value.trim())
    })
}

fn first_nonempty_line(path: &Path) -> Option<String> {
    fs::read_to_string(path)
        .ok()?
        .lines()
        .map(str::trim)
        .find(|line| !line.is_empty())
        .map(str::to_string)
}

fn quoted_python_string(value: &str) -> Option<String> {
    let mut chars = value.chars();
    let quote = chars.next()?;
    if quote != '"' && quote != '\'' {
        return None;
    }
    let tail = chars.as_str();
    let end = tail.find(quote)?;
    Some(tail[..end].to_string())
}

fn update_check_has_install_action(
    check: &UpdateCheck,
    install_action: UpdateInstallAction,
) -> bool {
    check.availability != UpdateAvailability::UpToDate
        && check.download_url.is_some()
        && install_action != UpdateInstallAction::None
}

fn update_install_button_label(
    labels: &UpdateLabels,
    install_action: UpdateInstallAction,
) -> &'static str {
    match install_action {
        UpdateInstallAction::PortableUpdater | UpdateInstallAction::StandardMacUpdater => {
            labels.install_update
        }
        UpdateInstallAction::DownloadPackage => labels.download_update,
        UpdateInstallAction::None => labels.install_update,
    }
}

fn update_install_note(labels: &UpdateLabels, install_action: UpdateInstallAction) -> &'static str {
    match install_action {
        UpdateInstallAction::PortableUpdater => labels.install_note,
        UpdateInstallAction::StandardMacUpdater => labels.standard_install_note,
        UpdateInstallAction::DownloadPackage => labels.download_note,
        UpdateInstallAction::None => labels.install_note,
    }
}

fn portable_updater_path(config: &LauncherConfig) -> Option<PathBuf> {
    if is_standard_app_dir(&config.app_dir) {
        return None;
    }
    let bundle_dir = config.app_dir.parent()?;
    let candidate = if cfg!(target_os = "macos") {
        bundle_dir.join("Update WebUI Portable.command")
    } else if cfg!(target_os = "windows") {
        bundle_dir.join("Update WebUI Portable.bat")
    } else {
        return None;
    };
    candidate.exists().then_some(candidate)
}

#[cfg(target_os = "macos")]
fn spawn_portable_updater(updater: &Path) -> Result<()> {
    let mut command = command_with_no_window(Path::new("zsh"));
    command.arg(updater).arg("--auto").arg("--restart-launcher");
    if let Some(bundle_dir) = updater.parent() {
        command.current_dir(bundle_dir);
    }
    command
        .spawn()
        .context("failed to start portable updater")?;
    Ok(())
}

#[cfg(target_os = "windows")]
fn spawn_portable_updater(updater: &Path) -> Result<()> {
    let updater_helper = updater.with_extension("ps1");
    if !updater_helper.exists() {
        return Err(anyhow!(
            "portable updater helper was not found at {}",
            updater_helper.display()
        ));
    }
    let mut command = command_with_no_window(Path::new("powershell"));
    command
        .args(["-NoProfile", "-File"])
        .arg(&updater_helper)
        .args(["-AutoInstall", "-RestartLauncher"]);
    if let Some(bundle_dir) = updater.parent() {
        command.current_dir(bundle_dir);
    }
    command
        .spawn()
        .context("failed to start portable updater")?;
    Ok(())
}

#[cfg(not(any(target_os = "macos", target_os = "windows")))]
fn spawn_portable_updater(_updater: &Path) -> Result<()> {
    Err(anyhow!(
        "portable updater is only available on macOS and Windows"
    ))
}

fn show_platform_about_window(info: &AboutInfo, labels: &AboutLabels) -> Result<AboutAction> {
    #[cfg(target_os = "macos")]
    {
        show_macos_about_window(info, labels)
    }
    #[cfg(target_os = "windows")]
    {
        show_windows_about_window(info, labels)
    }
    #[cfg(not(any(target_os = "macos", target_os = "windows")))]
    {
        eprintln!(
            "{}\n{}: {}\n{}: {}",
            labels.title, labels.version, info.version_label, labels.open_source, info.project_url
        );
        Ok(AboutAction::Close)
    }
}

#[cfg(target_os = "macos")]
fn show_macos_about_window(info: &AboutInfo, labels: &AboutLabels) -> Result<AboutAction> {
    let message = format!(
        "{}: {}\n{}: {}",
        labels.version, info.version_label, labels.open_source, info.project_url
    );
    let script = format!(
        "set dialogResult to display dialog {} with title {} buttons {{{}, {}, {}}} default button {}\nbutton returned of dialogResult",
        apple_script_string(&message),
        apple_script_string(labels.title),
        apple_script_string(labels.close),
        apple_script_string(labels.open_project),
        apple_script_string(labels.check_updates),
        apple_script_string(labels.check_updates),
    );
    let output = Command::new("osascript")
        .arg("-e")
        .arg(script)
        .output()
        .context("failed to show About window")?;
    if !output.status.success() {
        return Err(anyhow!("About window failed with status {}", output.status));
    }
    let button = String::from_utf8_lossy(&output.stdout).trim().to_string();
    Ok(about_action_from_button(&button, labels))
}

#[cfg(target_os = "macos")]
fn apple_script_string(value: &str) -> String {
    let mut result = String::from("\"");
    for ch in value.chars() {
        match ch {
            '"' => result.push_str("\\\""),
            '\\' => result.push_str("\\\\"),
            '\n' => result.push_str("\" & return & \""),
            '\r' => {}
            _ => result.push(ch),
        }
    }
    result.push('"');
    result
}

#[cfg(target_os = "windows")]
fn show_windows_about_window(info: &AboutInfo, labels: &AboutLabels) -> Result<AboutAction> {
    let script = format!(
        r#"
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
$form = New-Object System.Windows.Forms.Form
$form.Text = {title}
$form.Width = 520
$form.Height = 220
$form.StartPosition = 'CenterScreen'
$form.FormBorderStyle = 'FixedDialog'
$form.MaximizeBox = $false
$form.MinimizeBox = $false
$form.Tag = 'close'
$name = New-Object System.Windows.Forms.Label
$name.Text = {app_name}
$name.Font = New-Object System.Drawing.Font('Segoe UI', 12, [System.Drawing.FontStyle]::Bold)
$name.AutoSize = $true
$name.Left = 20
$name.Top = 18
$version = New-Object System.Windows.Forms.Label
$version.Text = {version_line}
$version.AutoSize = $true
$version.Left = 20
$version.Top = 54
$source = New-Object System.Windows.Forms.Label
$source.Text = {source_label}
$source.AutoSize = $true
$source.Left = 20
$source.Top = 84
$link = New-Object System.Windows.Forms.LinkLabel
$link.Text = {project_url}
$link.AutoSize = $true
$link.Left = 100
$link.Top = 84
$link.Add_Click({{ $form.Tag = 'open-project'; $form.Close() }})
$check = New-Object System.Windows.Forms.Button
$check.Text = {check_updates}
$check.Width = 125
$check.Height = 32
$check.Left = 210
$check.Top = 135
$check.Add_Click({{ $form.Tag = 'check-updates'; $form.Close() }})
$open = New-Object System.Windows.Forms.Button
$open.Text = {open_project}
$open.Width = 125
$open.Height = 32
$open.Left = 75
$open.Top = 135
$open.Add_Click({{ $form.Tag = 'open-project'; $form.Close() }})
$close = New-Object System.Windows.Forms.Button
$close.Text = {close}
$close.Width = 90
$close.Height = 32
$close.Left = 345
$close.Top = 135
$close.Add_Click({{ $form.Tag = 'close'; $form.Close() }})
$form.Controls.AddRange(@($name, $version, $source, $link, $open, $check, $close))
[void]$form.ShowDialog()
Write-Output $form.Tag
"#,
        title = powershell_string(labels.title),
        app_name = powershell_string(APP_NAME),
        version_line = powershell_string(&format!("{}: {}", labels.version, info.version_label)),
        source_label = powershell_string(&format!("{}:", labels.open_source)),
        project_url = powershell_string(info.project_url),
        check_updates = powershell_string(labels.check_updates),
        open_project = powershell_string(labels.open_project),
        close = powershell_string(labels.close),
    );
    let output = command_with_no_window(Path::new("powershell"))
        .args(["-NoProfile", "-Command", &script])
        .output()
        .context("failed to show About window")?;
    if !output.status.success() {
        return Err(anyhow!("About window failed with status {}", output.status));
    }
    let action = String::from_utf8_lossy(&output.stdout).trim().to_string();
    Ok(match action.as_str() {
        "check-updates" => AboutAction::CheckUpdates,
        "open-project" => AboutAction::OpenProject,
        _ => AboutAction::Close,
    })
}

#[cfg(target_os = "windows")]
fn powershell_string(value: &str) -> String {
    format!("'{}'", value.replace('\'', "''"))
}

#[cfg(target_os = "macos")]
fn about_action_from_button(button: &str, labels: &AboutLabels) -> AboutAction {
    if button == labels.check_updates {
        AboutAction::CheckUpdates
    } else if button == labels.open_project {
        AboutAction::OpenProject
    } else {
        AboutAction::Close
    }
}

fn fetch_update_manifest() -> Result<UpdateManifest> {
    let payload = fetch_update_manifest_payload()?;
    let manifest = parse_update_manifest_payload(&payload)?;
    verify_update_manifest_signature(&manifest)?;
    Ok(manifest)
}

fn fetch_update_manifest_payload() -> Result<String> {
    let mut command = command_with_no_window(Path::new(curl_program()));
    command
        .arg("-fsSL")
        .arg("--connect-timeout")
        .arg("8")
        .arg("--max-time")
        .arg("15")
        .arg("-H")
        .arg("Accept: application/json")
        .arg("-H")
        .arg(format!("User-Agent: {APP_NAME}"))
        .arg(LATEST_UPDATE_MANIFEST_URL);
    let output = command
        .output()
        .context("failed to run update manifest request")?;
    if !output.status.success() {
        let stderr = String::from_utf8_lossy(&output.stderr).trim().to_string();
        return Err(anyhow!(
            "update manifest request failed with status {}{}",
            output.status,
            if stderr.is_empty() {
                String::new()
            } else {
                format!(": {stderr}")
            }
        ));
    }
    String::from_utf8(output.stdout).context("update manifest response was not valid UTF-8")
}

fn curl_program() -> &'static str {
    if cfg!(windows) {
        "curl.exe"
    } else {
        "curl"
    }
}

fn show_platform_update_window(
    check: &UpdateCheck,
    labels: &UpdateLabels,
    install_action: UpdateInstallAction,
) -> Result<UpdateDialogAction> {
    #[cfg(target_os = "macos")]
    {
        show_macos_update_window(check, labels, install_action)
    }
    #[cfg(target_os = "windows")]
    {
        show_windows_update_window(check, labels, install_action)
    }
    #[cfg(not(any(target_os = "macos", target_os = "windows")))]
    {
        eprintln!("{}", update_message(check, labels, install_action));
        Ok(UpdateDialogAction::Close)
    }
}

fn update_message(
    check: &UpdateCheck,
    labels: &UpdateLabels,
    install_action: UpdateInstallAction,
) -> String {
    let status = match check.availability {
        UpdateAvailability::UpToDate => labels.up_to_date,
        UpdateAvailability::UpdateAvailable => labels.update_available,
        UpdateAvailability::UnknownCurrentVersion => labels.unknown_current_version,
    };
    let mut message = format!(
        "{}: {}\n{}: {}\n{}",
        labels.current_version,
        check.current_version,
        labels.latest_version,
        check.latest_version,
        status
    );
    if update_check_has_install_action(check, install_action) {
        message.push_str("\n\n");
        message.push_str(update_install_note(labels, install_action));
    }
    message
}

#[cfg(target_os = "macos")]
fn show_macos_update_window(
    check: &UpdateCheck,
    labels: &UpdateLabels,
    install_action: UpdateInstallAction,
) -> Result<UpdateDialogAction> {
    let has_install = update_check_has_install_action(check, install_action);
    let install_label = update_install_button_label(labels, install_action);
    let mut buttons = vec![labels.close, labels.open_release];
    if has_install {
        buttons.push(install_label);
    }
    let buttons_script = buttons
        .iter()
        .map(|button| apple_script_string(button))
        .collect::<Vec<_>>()
        .join(", ");
    let default_button = if has_install {
        install_label
    } else {
        labels.open_release
    };
    let script = format!(
        "set dialogResult to display dialog {} with title {} buttons {{{}}} default button {}\nbutton returned of dialogResult",
        apple_script_string(&update_message(check, labels, install_action)),
        apple_script_string(labels.title),
        buttons_script,
        apple_script_string(default_button),
    );
    let output = Command::new("osascript")
        .arg("-e")
        .arg(script)
        .output()
        .context("failed to show update window")?;
    if !output.status.success() {
        return Err(anyhow!(
            "update window failed with status {}",
            output.status
        ));
    }
    let button = String::from_utf8_lossy(&output.stdout).trim().to_string();
    Ok(update_action_from_button(&button, labels))
}

#[cfg(target_os = "windows")]
fn show_windows_update_window(
    check: &UpdateCheck,
    labels: &UpdateLabels,
    install_action: UpdateInstallAction,
) -> Result<UpdateDialogAction> {
    let install_button = if update_check_has_install_action(check, install_action) {
        format!(
            r#"
$install = New-Object System.Windows.Forms.Button
$install.Text = {install_update}
$install.Width = 125
$install.Height = 32
$install.Left = 265
$install.Top = 145
$install.Add_Click({{ $form.Tag = 'install-update'; $form.Close() }})
$form.Controls.Add($install)
"#,
            install_update = powershell_string(update_install_button_label(labels, install_action))
        )
    } else {
        String::new()
    };
    let script = format!(
        r#"
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
$form = New-Object System.Windows.Forms.Form
$form.Text = {title}
$form.Width = 540
$form.Height = 240
$form.StartPosition = 'CenterScreen'
$form.FormBorderStyle = 'FixedDialog'
$form.MaximizeBox = $false
$form.MinimizeBox = $false
$form.Tag = 'close'
$message = New-Object System.Windows.Forms.Label
$message.Text = {message}
$message.AutoSize = $false
$message.Width = 480
$message.Height = 95
$message.Left = 24
$message.Top = 22
$message.Font = New-Object System.Drawing.Font('Segoe UI', 10)
$release = New-Object System.Windows.Forms.Button
$release.Text = {open_release}
$release.Width = 125
$release.Height = 32
$release.Left = 130
$release.Top = 145
$release.Add_Click({{ $form.Tag = 'open-release'; $form.Close() }})
$close = New-Object System.Windows.Forms.Button
$close.Text = {close}
$close.Width = 90
$close.Height = 32
$close.Left = 400
$close.Top = 145
$close.Add_Click({{ $form.Tag = 'close'; $form.Close() }})
$form.Controls.AddRange(@($message, $release, $close))
{download_button}
[void]$form.ShowDialog()
Write-Output $form.Tag
"#,
        title = powershell_string(labels.title),
        message = powershell_string(&update_message(check, labels, install_action)),
        open_release = powershell_string(labels.open_release),
        close = powershell_string(labels.close),
        download_button = install_button,
    );
    let output = command_with_no_window(Path::new("powershell"))
        .args(["-NoProfile", "-Command", &script])
        .output()
        .context("failed to show update window")?;
    if !output.status.success() {
        return Err(anyhow!(
            "update window failed with status {}",
            output.status
        ));
    }
    let action = String::from_utf8_lossy(&output.stdout).trim().to_string();
    Ok(match action.as_str() {
        "install-update" => UpdateDialogAction::InstallUpdate,
        "open-release" => UpdateDialogAction::OpenRelease,
        _ => UpdateDialogAction::Close,
    })
}

#[cfg(target_os = "macos")]
fn update_action_from_button(button: &str, labels: &UpdateLabels) -> UpdateDialogAction {
    if button == labels.install_update || button == labels.download_update {
        UpdateDialogAction::InstallUpdate
    } else if button == labels.open_release {
        UpdateDialogAction::OpenRelease
    } else {
        UpdateDialogAction::Close
    }
}

fn update_package_kind_for_app(app_dir: &Path) -> UpdatePackageKind {
    if is_standard_app_dir(app_dir) {
        UpdatePackageKind::Standard
    } else if app_dir.file_name().and_then(|name| name.to_str()) == Some("app") {
        UpdatePackageKind::Portable
    } else {
        UpdatePackageKind::Source
    }
}

fn update_install_action_for_config(
    config: &LauncherConfig,
    check: &UpdateCheck,
) -> UpdateInstallAction {
    if check.download_url.is_none() || check.availability == UpdateAvailability::UpToDate {
        return UpdateInstallAction::None;
    }
    if portable_updater_path(config).is_some() {
        return UpdateInstallAction::PortableUpdater;
    }
    if is_standard_app_dir(&config.app_dir) {
        if cfg!(target_os = "macos")
            && check.package.as_deref() == Some("standard-dmg")
            && check.download_sha256.is_some()
            && standard_update::standard_update_helper_path(&config.app_dir).is_some()
        {
            return UpdateInstallAction::StandardMacUpdater;
        }
        return UpdateInstallAction::DownloadPackage;
    }
    UpdateInstallAction::None
}

fn update_notice_path(config: &LauncherConfig) -> PathBuf {
    config.data_dir.join("update-notice.json")
}

fn sync_update_notice(config: &LauncherConfig, check: &UpdateCheck) -> Result<()> {
    if check.availability != UpdateAvailability::UpdateAvailable {
        clear_update_notice(config);
        return Ok(());
    }
    fs::create_dir_all(&config.data_dir)?;
    let mut payload = serde_json::json!({
        "current_version": check.current_version.trim_start_matches('v').trim_start_matches('V'),
        "latest_version": check.latest_version.trim_start_matches('v').trim_start_matches('V'),
        "checked_at": SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap_or_default()
            .as_secs()
            .to_string(),
        "release_url": check.release_url.clone(),
    });
    if let Some(download_url) = &check.download_url {
        payload["download_url"] = serde_json::Value::String(download_url.clone());
        if is_standard_app_dir(&config.app_dir) {
            payload["standard_download_url"] = serde_json::Value::String(download_url.clone());
        }
    }
    fs::write(
        update_notice_path(config),
        serde_json::to_string_pretty(&payload)? + "\n",
    )?;
    Ok(())
}

fn clear_update_notice(config: &LauncherConfig) {
    let path = update_notice_path(config);
    if path.exists() {
        let _ = fs::remove_file(path);
    }
}

pub struct WebUiService {
    pub config: LauncherConfig,
    child: Option<Child>,
}

impl WebUiService {
    pub fn new(config: LauncherConfig) -> Self {
        Self {
            config,
            child: None,
        }
    }

    pub fn ensure_running(&mut self) -> Result<()> {
        fs::create_dir_all(&self.config.output_root)?;
        fs::create_dir_all(&self.config.input_root)?;
        fs::create_dir_all(&self.config.source_data_root)?;

        if is_webui_ready(self.config.port) {
            self.log_line("WebUI is already running; leaving existing service untouched.")?;
            return Ok(());
        }

        let python = self.ensure_python_runtime()?;
        self.initialize_auth_settings(&python)?;
        self.spawn_uvicorn(&python)?;
        self.wait_until_ready()
    }

    pub fn open_webui(&self) -> Result<()> {
        open::that(self.config.url()).context("failed to open WebUI in the default browser")
    }

    pub fn open_settings(&self) -> Result<()> {
        open::that(self.config.settings_url())
            .context("failed to open WebUI settings in the default browser")
    }

    pub fn open_history(&self) -> Result<()> {
        open::that(self.config.history_url())
            .context("failed to open history library in the default browser")
    }

    pub fn check_for_updates(&self, locale: AppLocale) -> Result<UpdateOutcome> {
        let labels = localized_update_labels(locale);
        let current_version = self.config.about_info().version_label;
        let manifest = fetch_update_manifest()
            .with_context(|| format!("{}: {}", labels.check_failed, LATEST_UPDATE_MANIFEST_URL))?;
        let package_kind = update_package_kind_for_app(&self.config.app_dir);
        let check = update_check_from_manifest(&current_version, &manifest, package_kind);
        sync_update_notice(&self.config, &check)?;
        let install_action = update_install_action_for_config(&self.config, &check);
        match show_platform_update_window(&check, &labels, install_action)? {
            UpdateDialogAction::Close => Ok(UpdateOutcome::Continue),
            UpdateDialogAction::OpenRelease => {
                open::that(&check.release_url).context("failed to open GitHub release page")?;
                Ok(UpdateOutcome::Continue)
            }
            UpdateDialogAction::InstallUpdate => match install_action {
                UpdateInstallAction::PortableUpdater => {
                    self.launch_portable_updater()?;
                    Ok(UpdateOutcome::LaunchedUpdater)
                }
                UpdateInstallAction::StandardMacUpdater => {
                    self.launch_standard_updater(&check, locale)?;
                    Ok(UpdateOutcome::LaunchedUpdater)
                }
                UpdateInstallAction::DownloadPackage => {
                    let url = check
                        .download_url
                        .as_ref()
                        .ok_or_else(|| anyhow!("standard package download URL is not available"))?;
                    open::that(url).context("failed to open update package download")?;
                    Ok(UpdateOutcome::Continue)
                }
                UpdateInstallAction::None => Ok(UpdateOutcome::Continue),
            },
        }
    }

    pub fn show_about(&self, locale: AppLocale) -> Result<UpdateOutcome> {
        let labels = localized_about_labels(locale);
        let info = self.config.about_info();
        match show_platform_about_window(&info, &labels)? {
            AboutAction::Close => Ok(UpdateOutcome::Continue),
            AboutAction::OpenProject => {
                open::that(PROJECT_URL).context("failed to open open-source project page")?;
                Ok(UpdateOutcome::Continue)
            }
            AboutAction::CheckUpdates => self.check_for_updates(locale),
        }
    }

    pub fn restart_owned_service(&mut self) -> Result<()> {
        self.stop_owned_service();
        self.ensure_running()?;
        self.open_webui()
    }

    pub fn stop_owned_service(&mut self) {
        if let Some(mut child) = self.child.take() {
            let _ = child.kill();
            let _ = child.wait();
        }
    }

    fn launch_portable_updater(&self) -> Result<()> {
        let updater = portable_updater_path(&self.config)
            .ok_or_else(|| anyhow!("portable updater script is not available"))?;
        self.log_line(&format!(
            "Launching portable updater: {}",
            updater.display()
        ))?;
        spawn_portable_updater(&updater)
    }

    fn launch_standard_updater(&self, check: &UpdateCheck, locale: AppLocale) -> Result<()> {
        let helper = standard_update::standard_update_helper_path(&self.config.app_dir)
            .ok_or_else(|| anyhow!("standard updater helper is not available"))?;
        let target_app = standard_update::standard_app_bundle_path(&self.config.app_dir)
            .ok_or_else(|| anyhow!("standard App bundle path could not be resolved"))?;
        let request = standard_update::StandardUpdateRequest {
            url: check
                .download_url
                .clone()
                .ok_or_else(|| anyhow!("standard update download URL is not available"))?,
            expected_sha256: check
                .download_sha256
                .clone()
                .ok_or_else(|| anyhow!("standard update SHA256 is not available"))?,
            expected_version: check.latest_version.clone(),
            target_app,
            parent_pid: std::process::id(),
            log_path: self.config.data_dir.join("standard-update.log"),
            locale: locale.tag().to_string(),
        };
        standard_update::launch_standard_updater(&helper, &request)
    }

    pub fn log_line(&self, message: &str) -> Result<()> {
        let mut log = open_log_file(&self.config.log_path)?;
        writeln!(log, "[launcher] {message}")?;
        Ok(())
    }

    fn ensure_python_runtime(&self) -> Result<PathBuf> {
        if let Some(python) = bundled_or_venv_python(&self.config.app_dir) {
            if dependency_probe(&python, &self.config.app_dir)? {
                return Ok(python);
            }
        }

        let python = bundled_or_venv_python(&self.config.app_dir)
            .unwrap_or_else(|| venv_python_path(&self.config.app_dir));
        if !python.exists() {
            let system_python = find_system_python()?;
            self.run_logged_command(
                command_with_no_window(&system_python)
                    .args(["-m", "venv"])
                    .arg(self.config.app_dir.join(".venv")),
                "create Python virtual environment",
            )?;
        }

        if !dependency_probe(&python, &self.config.app_dir)? {
            self.run_logged_command(
                command_with_no_window(&python)
                    .args(["-m", "pip", "install", "--require-hashes", "-r"])
                    .arg(self.config.app_dir.join("requirements-webui.txt")),
                "install WebUI dependencies",
            )?;
            if !dependency_probe(&python, &self.config.app_dir)? {
                return Err(anyhow!(
                    "WebUI dependency verification failed after installation"
                ));
            }
        }

        Ok(python)
    }

    fn initialize_auth_settings(&self, python: &Path) -> Result<()> {
        self.run_logged_command(
            command_with_no_window(python)
                .args(["-m", "codex_image.webui.startup_auth", "--settings-path"])
                .arg(self.config.auth_settings_path())
                .current_dir(&self.config.app_dir),
            "initialize auth settings",
        )
    }

    fn spawn_uvicorn(&mut self, python: &Path) -> Result<()> {
        let log = open_log_file(&self.config.log_path)?;
        let err_log = log.try_clone()?;
        let mut command = command_with_no_window(python);
        command
            .args([
                "-m",
                "codex_image.webui.server",
                self.config.uvicorn_app(),
                "--port",
                &self.config.port.to_string(),
                "--no-access-log",
                "--timeout-graceful-shutdown",
                "5",
            ])
            .current_dir(&self.config.app_dir)
            .env("ILAB_CONJURE_DATA_DIR", &self.config.data_dir)
            .env("ILAB_CONJURE_APP_DIR", &self.config.app_dir)
            .env(
                "APP_LAUNCHER_MODE",
                launcher_mode_for_app(&self.config.app_dir),
            )
            .env("PYTHONPATH", python_path_for_app(&self.config.app_dir))
            .stdout(Stdio::from(log))
            .stderr(Stdio::from(err_log));

        let child = command.spawn().context("failed to start WebUI service")?;
        self.child = Some(child);
        Ok(())
    }

    fn wait_until_ready(&self) -> Result<()> {
        let started_at = Instant::now();
        while started_at.elapsed() < WAIT_TIMEOUT {
            if is_webui_ready(self.config.port) {
                return Ok(());
            }
            thread::sleep(HEALTH_POLL_INTERVAL);
        }
        Err(anyhow!(
            "WebUI did not become ready within {} seconds. Check {}.",
            WAIT_TIMEOUT.as_secs(),
            self.config.log_path.display()
        ))
    }

    fn run_logged_command(&self, command: &mut Command, action: &str) -> Result<()> {
        let log = open_log_file(&self.config.log_path)?;
        let err_log = log.try_clone()?;
        let status = command
            .current_dir(&self.config.app_dir)
            .stdout(Stdio::from(log))
            .stderr(Stdio::from(err_log))
            .status()
            .with_context(|| format!("failed to {action}"))?;
        if status.success() {
            Ok(())
        } else {
            Err(anyhow!("{action} failed with status {status}"))
        }
    }
}

impl Drop for WebUiService {
    fn drop(&mut self) {
        self.stop_owned_service();
    }
}

pub fn detect_app_dir() -> Result<PathBuf> {
    if let Some(path) = env::var_os("ILAB_CONJURE_APP_DIR") {
        let path = PathBuf::from(path);
        if is_app_dir(&path) {
            return Ok(path);
        }
    }

    let mut candidates: Vec<PathBuf> = Vec::new();
    if let Ok(exe) = env::current_exe() {
        if let Some(parent) = exe.parent() {
            push_app_dir_candidates(&mut candidates, parent);
        }
    }
    if let Ok(cwd) = env::current_dir() {
        push_app_dir_candidates(&mut candidates, &cwd);
        if cwd.file_name().and_then(|name| name.to_str()) == Some("launcher") {
            if let Some(parent) = cwd.parent() {
                candidates.push(parent.to_path_buf());
            }
        }
    }
    candidates.push(PathBuf::from(env!("CARGO_MANIFEST_DIR")).join(".."));

    candidates
        .into_iter()
        .find(|candidate| is_app_dir(candidate))
        .map(|candidate| candidate.canonicalize().unwrap_or(candidate))
        .ok_or_else(|| anyhow!("could not locate app directory containing codex_image"))
}

fn push_app_dir_candidates(candidates: &mut Vec<PathBuf>, anchor: &Path) {
    for ancestor in anchor.ancestors() {
        candidates.push(ancestor.to_path_buf());
        candidates.push(ancestor.join("app"));
        candidates.push(ancestor.join("resources").join("app"));
        candidates.push(ancestor.join("Contents").join("Resources").join("app"));
        if ancestor.file_name().and_then(|name| name.to_str()) == Some("MacOS") {
            if let Some(contents_dir) = ancestor.parent() {
                candidates.push(contents_dir.join("Resources").join("app"));
            }
        }
    }
}

pub fn is_app_dir(path: &Path) -> bool {
    path.join("codex_image").is_dir() && path.join("requirements-webui.txt").is_file()
}

pub fn is_webui_ready(port: u16) -> bool {
    let Ok(mut stream) = TcpStream::connect_timeout(
        &format!("127.0.0.1:{port}")
            .parse()
            .expect("valid loopback address"),
        Duration::from_millis(600),
    ) else {
        return false;
    };
    let _ = stream.set_read_timeout(Some(Duration::from_millis(800)));
    let _ = stream.set_write_timeout(Some(Duration::from_millis(800)));
    let request = format!(
        "GET {HEALTH_PATH} HTTP/1.1\r\nHost: 127.0.0.1:{port}\r\nConnection: close\r\n\r\n"
    );
    if stream.write_all(request.as_bytes()).is_err() {
        return false;
    }
    let mut response = String::new();
    stream.read_to_string(&mut response).is_ok() && response.starts_with("HTTP/1.1 200")
}

pub fn rabbit_icon_rgba(size: u32) -> (Vec<u8>, u32, u32) {
    let mut rgba = vec![0; (size * size * 4) as usize];
    let white = [0xFF, 0xFF, 0xFF, 0xFF];
    let transparent = [0x00, 0x00, 0x00, 0x00];

    fill_rotated_ellipse(&mut rgba, size, (8.3, 6.3), (1.45, 4.15), -9.0, white);
    fill_rotated_ellipse(&mut rgba, size, (12.7, 6.6), (1.35, 4.25), 36.0, white);
    fill_ellipse(&mut rgba, size, 14.4, 15.6, 6.3, 4.8, white);
    fill_ellipse(&mut rgba, size, 8.9, 12.4, 4.6, 4.25, white);
    fill_ellipse(&mut rgba, size, 19.3, 13.9, 1.85, 1.95, white);
    fill_ellipse(&mut rgba, size, 9.4, 19.1, 2.7, 1.15, white);
    fill_ellipse(&mut rgba, size, 15.3, 19.2, 3.2, 1.15, white);
    fill_rotated_ellipse(&mut rgba, size, (8.2, 5.9), (0.52, 2.25), -9.0, transparent);
    fill_rotated_ellipse(
        &mut rgba,
        size,
        (12.45, 6.0),
        (0.48, 2.15),
        36.0,
        transparent,
    );
    fill_ellipse(&mut rgba, size, 7.45, 11.7, 0.72, 0.72, transparent);

    (rgba, size, size)
}

const RABBIT_ICON_SOURCE_VIEWBOX: f32 = 22.0;
const RABBIT_ICON_MENU_BAR_X_OFFSET: f32 = -1.0;
const RABBIT_ICON_MENU_BAR_Y_OFFSET: f32 = 0.5;

fn fill_ellipse(rgba: &mut [u8], size: u32, cx: f32, cy: f32, rx: f32, ry: f32, color: [u8; 4]) {
    let scale = size as f32 / RABBIT_ICON_SOURCE_VIEWBOX;
    let cx = (cx + RABBIT_ICON_MENU_BAR_X_OFFSET) * scale;
    let cy = (cy + RABBIT_ICON_MENU_BAR_Y_OFFSET) * scale;
    let rx = rx * scale;
    let ry = ry * scale;
    for y in 0..size {
        for x in 0..size {
            let dx = (x as f32 + 0.5 - cx) / rx;
            let dy = (y as f32 + 0.5 - cy) / ry;
            if dx * dx + dy * dy <= 1.0 {
                let index = ((y * size + x) * 4) as usize;
                rgba[index..index + 4].copy_from_slice(&color);
            }
        }
    }
}

fn fill_rotated_ellipse(
    rgba: &mut [u8],
    size: u32,
    center: (f32, f32),
    radii: (f32, f32),
    angle_degrees: f32,
    color: [u8; 4],
) {
    let scale = size as f32 / RABBIT_ICON_SOURCE_VIEWBOX;
    let (cx, cy) = center;
    let (rx, ry) = radii;
    let cx = (cx + RABBIT_ICON_MENU_BAR_X_OFFSET) * scale;
    let cy = (cy + RABBIT_ICON_MENU_BAR_Y_OFFSET) * scale;
    let rx = rx * scale;
    let ry = ry * scale;
    let angle = angle_degrees.to_radians();
    let cos = angle.cos();
    let sin = angle.sin();
    for y in 0..size {
        for x in 0..size {
            let px = x as f32 + 0.5 - cx;
            let py = y as f32 + 0.5 - cy;
            let dx = (px * cos + py * sin) / rx;
            let dy = (-px * sin + py * cos) / ry;
            if dx * dx + dy * dy <= 1.0 {
                let index = ((y * size + x) * 4) as usize;
                rgba[index..index + 4].copy_from_slice(&color);
            }
        }
    }
}

fn dependency_probe(python: &Path, app_dir: &Path) -> Result<bool> {
    let status = command_with_no_window(python)
        .args(["-m", "codex_image.dependency_check", "--requirements"])
        .arg(app_dir.join("requirements-webui.txt"))
        .current_dir(app_dir)
        .env("PYTHONPATH", python_path_for_app(app_dir))
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .status()?;
    Ok(status.success())
}

fn find_system_python() -> Result<PathBuf> {
    let candidates: &[&str] = if cfg!(windows) {
        &["py", "python"]
    } else {
        &["python3", "python"]
    };
    candidates
        .iter()
        .find_map(|name| {
            command_with_no_window(Path::new(name))
                .arg("--version")
                .stdout(Stdio::null())
                .stderr(Stdio::null())
                .status()
                .ok()
                .filter(|status| status.success())
                .map(|_| PathBuf::from(name))
        })
        .ok_or_else(|| anyhow!("Python 3 was not found. Install Python 3 first."))
}

fn bundled_or_venv_python(app_dir: &Path) -> Option<PathBuf> {
    for candidate in bundled_python_candidates(app_dir) {
        if candidate.exists() {
            return Some(candidate);
        }
    }
    let venv_python = venv_python_path(app_dir);
    venv_python.exists().then_some(venv_python)
}

fn default_data_dir_for_app(app_dir: &Path) -> PathBuf {
    if is_standard_app_dir(app_dir) {
        return standard_app_data_dir();
    }
    if app_dir.file_name().and_then(|name| name.to_str()) == Some("app") {
        if let Some(data_dir) = app_dir.parent().map(|parent| parent.join("data")) {
            return data_dir;
        }
    }
    app_dir.join("output")
}

fn bundled_python_candidates(app_dir: &Path) -> Vec<PathBuf> {
    let mut candidates = Vec::new();
    if cfg!(windows) {
        if let Some(resources_dir) = app_dir.parent() {
            candidates.push(resources_dir.join("python").join("python.exe"));
        }
        if let Some(bundle_dir) = app_dir.parent() {
            candidates.push(bundle_dir.join("python").join("python.exe"));
        }
    } else {
        if let Some(resources_dir) = app_dir.parent() {
            candidates.push(
                resources_dir
                    .join("python")
                    .join("Python.framework")
                    .join("Versions")
                    .join("3.11")
                    .join("bin")
                    .join("python3"),
            );
        }
        if let Some(bundle_dir) = app_dir.parent() {
            candidates.push(
                bundle_dir
                    .join("python")
                    .join("Python.framework")
                    .join("Versions")
                    .join("3.11")
                    .join("bin")
                    .join("python3"),
            );
        }
    }
    candidates
}

fn is_standard_app_dir(app_dir: &Path) -> bool {
    if app_dir.file_name().and_then(|name| name.to_str()) != Some("app") {
        return false;
    }
    let Some(resources_dir) = app_dir.parent() else {
        return false;
    };
    if resources_dir.file_name().and_then(|name| name.to_str()) == Some("resources") {
        return true;
    }
    if resources_dir.file_name().and_then(|name| name.to_str()) != Some("Resources") {
        return false;
    }
    let Some(contents_dir) = resources_dir.parent() else {
        return false;
    };
    if contents_dir.file_name().and_then(|name| name.to_str()) != Some("Contents") {
        return false;
    }
    contents_dir
        .parent()
        .and_then(|bundle| bundle.extension())
        .and_then(|extension| extension.to_str())
        == Some("app")
}

fn standard_app_data_dir() -> PathBuf {
    if cfg!(target_os = "macos") {
        home_dir()
            .unwrap_or_else(|| PathBuf::from("."))
            .join("Library")
            .join("Application Support")
            .join(LEGACY_DATA_DIR_NAME)
    } else if cfg!(windows) {
        env::var_os("APPDATA")
            .map(PathBuf::from)
            .or_else(|| home_dir().map(|home| home.join("AppData").join("Roaming")))
            .unwrap_or_else(|| PathBuf::from("."))
            .join(LEGACY_DATA_DIR_NAME)
    } else {
        env::var_os("XDG_DATA_HOME")
            .map(PathBuf::from)
            .or_else(|| home_dir().map(|home| home.join(".local").join("share")))
            .unwrap_or_else(|| PathBuf::from("."))
            .join(LEGACY_DATA_DIR_NAME)
    }
}

fn home_dir() -> Option<PathBuf> {
    env::var_os("HOME")
        .map(PathBuf::from)
        .or_else(|| env::var_os("USERPROFILE").map(PathBuf::from))
}

fn launcher_mode_for_app(app_dir: &Path) -> &'static str {
    if is_standard_app_dir(app_dir) {
        "standard"
    } else if app_dir.file_name().and_then(|name| name.to_str()) == Some("app") {
        "portable"
    } else {
        "source"
    }
}

pub fn maybe_offer_legacy_portable_migration(
    config: &LauncherConfig,
    locale: AppLocale,
) -> Result<()> {
    if !is_standard_app_dir(&config.app_dir) {
        return Ok(());
    }
    if migration_marker_path(&config.data_dir).exists() || target_has_webui_data(&config.data_dir) {
        return Ok(());
    }
    let detected = legacy_portable_data_candidates(&config.app_dir)
        .into_iter()
        .find(|candidate| looks_like_legacy_portable_data(candidate));
    let Some(source) = prompt_legacy_migration_source(detected.as_deref(), locale)? else {
        return Ok(());
    };
    let source = normalize_legacy_data_dir(&source);
    if !looks_like_legacy_portable_data(&source) {
        return Err(anyhow!(
            "selected legacy data directory does not contain WebUI data: {}",
            source.display()
        ));
    }
    migrate_legacy_portable_data(&source, &config.data_dir)
}

fn legacy_portable_data_candidates(app_dir: &Path) -> Vec<PathBuf> {
    let mut candidates = Vec::new();
    if let Some(root) = standard_package_root(app_dir) {
        candidates.push(root.join("data"));
    }
    if let Some(app_bundle) = macos_app_bundle_root(app_dir) {
        if let Some(parent) = app_bundle.parent() {
            candidates.push(parent.join("data"));
        }
    }
    candidates
}

fn standard_package_root(app_dir: &Path) -> Option<PathBuf> {
    let resources_dir = app_dir.parent()?;
    if resources_dir.file_name().and_then(|name| name.to_str()) == Some("resources") {
        return resources_dir.parent().map(Path::to_path_buf);
    }
    macos_app_bundle_root(app_dir).and_then(|bundle| bundle.parent().map(Path::to_path_buf))
}

fn macos_app_bundle_root(app_dir: &Path) -> Option<PathBuf> {
    let resources_dir = app_dir.parent()?;
    if resources_dir.file_name().and_then(|name| name.to_str()) != Some("Resources") {
        return None;
    }
    let contents_dir = resources_dir.parent()?;
    if contents_dir.file_name().and_then(|name| name.to_str()) != Some("Contents") {
        return None;
    }
    contents_dir.parent().map(Path::to_path_buf)
}

fn normalize_legacy_data_dir(path: &Path) -> PathBuf {
    let data_child = path.join("data");
    if looks_like_legacy_portable_data(&data_child) {
        data_child
    } else {
        path.to_path_buf()
    }
}

fn looks_like_legacy_portable_data(path: &Path) -> bool {
    path.is_dir()
        && [
            "webui-settings.json",
            "webui-auth-settings.json",
            "webui-api-settings.json",
            "webui-network-egress-settings.json",
            "webui-color-settings.json",
            "webui-prompt-snippets.json",
            "webui-prompt-templates.json",
            "webui-inputs",
            "webui-outputs",
        ]
        .iter()
        .any(|name| path.join(name).exists())
}

fn target_has_webui_data(path: &Path) -> bool {
    looks_like_legacy_portable_data(path)
}

fn migration_marker_path(data_dir: &Path) -> PathBuf {
    data_dir
        .join(".migration")
        .join("portable-data-copied-v1.json")
}

fn migrate_legacy_portable_data(source_data_dir: &Path, target_data_dir: &Path) -> Result<()> {
    if !looks_like_legacy_portable_data(source_data_dir) {
        return Err(anyhow!(
            "legacy portable data was not found at {}",
            source_data_dir.display()
        ));
    }
    if target_has_webui_data(target_data_dir) {
        return Err(anyhow!(
            "target data directory already contains WebUI data: {}",
            target_data_dir.display()
        ));
    }
    copy_dir_recursive(source_data_dir, target_data_dir)?;
    let marker_path = migration_marker_path(target_data_dir);
    if let Some(parent) = marker_path.parent() {
        fs::create_dir_all(parent)?;
    }
    let migrated_at = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default()
        .as_secs();
    let marker = serde_json::json!({
        "schema_version": 1,
        "source": source_data_dir.display().to_string(),
        "migrated_at_unix": migrated_at,
        "mode": "copy"
    });
    fs::write(&marker_path, serde_json::to_string_pretty(&marker)?)
        .with_context(|| format!("failed to write migration marker {}", marker_path.display()))?;
    Ok(())
}

fn copy_dir_recursive(source: &Path, target: &Path) -> Result<()> {
    fs::create_dir_all(target)?;
    for entry in fs::read_dir(source)
        .with_context(|| format!("failed to read directory {}", source.display()))?
    {
        let entry = entry?;
        let source_path = entry.path();
        let target_path = target.join(entry.file_name());
        let metadata = fs::symlink_metadata(&source_path)?;
        if metadata.file_type().is_symlink() {
            continue;
        }
        if metadata.is_dir() {
            copy_dir_recursive(&source_path, &target_path)?;
        } else if metadata.is_file() {
            if let Some(parent) = target_path.parent() {
                fs::create_dir_all(parent)?;
            }
            fs::copy(&source_path, &target_path).with_context(|| {
                format!(
                    "failed to copy {} to {}",
                    source_path.display(),
                    target_path.display()
                )
            })?;
        }
    }
    Ok(())
}

#[derive(Debug, Clone, PartialEq, Eq)]
struct MigrationPromptPlan {
    title: &'static str,
    message: String,
    skip_button: &'static str,
    choose_button: &'static str,
    detected_button: Option<&'static str>,
}

fn migration_prompt_plan(
    detected_data_dir: Option<&Path>,
    locale: AppLocale,
) -> MigrationPromptPlan {
    match locale {
        AppLocale::ZhCn | AppLocale::ZhTw | AppLocale::ZhHk => {
            let message = if let Some(path) = detected_data_dir {
                format!(
                    "检测到旧 portable 数据目录：\n{}\n\n可以复制到标准 App 数据目录；也可以选择其他旧版本目录。旧数据不会被移动或删除。",
                    path.display()
                )
            } else {
                "没有自动检测到旧 portable data/。\n\n如果你从 0.5.4 或更早版本迁移，可以选择旧版本目录或其中的 data 目录；也可以跳过。旧数据不会被移动或删除。"
                    .to_string()
            };
            MigrationPromptPlan {
                title: "迁移旧版数据",
                message,
                skip_button: "跳过",
                choose_button: "选择旧版本目录",
                detected_button: detected_data_dir.map(|_| "复制检测到的数据"),
            }
        }
        _ => {
            let message = if let Some(path) = detected_data_dir {
                format!(
                    "Found legacy portable data:\n{}\n\nCopy it into the standard app data directory, or choose another old portable folder. The old data will not be moved or deleted.",
                    path.display()
                )
            } else {
                "No legacy portable data/ folder was detected automatically.\n\nIf you are migrating from 0.5.4 or earlier, choose the old portable folder or its data folder. You can also skip this step. The old data will not be moved or deleted."
                    .to_string()
            };
            MigrationPromptPlan {
                title: "Migrate Portable Data",
                message,
                skip_button: "Skip",
                choose_button: "Choose Old Folder",
                detected_button: detected_data_dir.map(|_| "Copy Detected Data"),
            }
        }
    }
}

#[cfg(target_os = "macos")]
fn prompt_legacy_migration_source(
    detected_data_dir: Option<&Path>,
    locale: AppLocale,
) -> Result<Option<PathBuf>> {
    let plan = migration_prompt_plan(detected_data_dir, locale);
    let script = if let Some(detected_button) = plan.detected_button {
        format!(
            "set dialogResult to display dialog {} with title {} buttons {{{}, {}, {}}} default button {}\nbutton returned of dialogResult",
            apple_script_string(&plan.message),
            apple_script_string(plan.title),
            apple_script_string(plan.skip_button),
            apple_script_string(plan.choose_button),
            apple_script_string(detected_button),
            apple_script_string(detected_button),
        )
    } else {
        format!(
            "set dialogResult to display dialog {} with title {} buttons {{{}, {}}} default button {}\nbutton returned of dialogResult",
            apple_script_string(&plan.message),
            apple_script_string(plan.title),
            apple_script_string(plan.skip_button),
            apple_script_string(plan.choose_button),
            apple_script_string(plan.choose_button),
        )
    };
    let output = Command::new("osascript")
        .arg("-e")
        .arg(script)
        .output()
        .context("failed to show migration prompt")?;
    if !output.status.success() {
        return Ok(None);
    }
    let button = String::from_utf8_lossy(&output.stdout).trim().to_string();
    if plan.detected_button.is_some_and(|label| button == label) {
        let Some(detected_data_dir) = detected_data_dir else {
            return Ok(None);
        };
        return Ok(Some(detected_data_dir.to_path_buf()));
    }
    if button == plan.choose_button {
        return choose_legacy_data_dir(locale);
    }
    Ok(None)
}

#[cfg(target_os = "macos")]
fn choose_legacy_data_dir(locale: AppLocale) -> Result<Option<PathBuf>> {
    let prompt = match locale {
        AppLocale::ZhCn | AppLocale::ZhTw | AppLocale::ZhHk => "选择旧版本目录或其中的 data 目录",
        _ => "Choose the old portable folder or its data folder",
    };
    let script = format!(
        "POSIX path of (choose folder with prompt {})",
        apple_script_string(prompt)
    );
    let output = Command::new("osascript")
        .arg("-e")
        .arg(script)
        .output()
        .context("failed to show folder chooser")?;
    if !output.status.success() {
        return Ok(None);
    }
    let value = String::from_utf8_lossy(&output.stdout).trim().to_string();
    if value.is_empty() {
        Ok(None)
    } else {
        Ok(Some(PathBuf::from(value)))
    }
}

#[cfg(target_os = "windows")]
fn prompt_legacy_migration_source(
    detected_data_dir: Option<&Path>,
    locale: AppLocale,
) -> Result<Option<PathBuf>> {
    let plan = migration_prompt_plan(detected_data_dir, locale);
    let buttons = if detected_data_dir.is_some() {
        "YesNoCancel"
    } else {
        "OKCancel"
    };
    let script = format!(
        r#"
Add-Type -AssemblyName System.Windows.Forms
$result = [System.Windows.Forms.MessageBox]::Show({message}, {title}, '{buttons}', 'Question')
Write-Output $result
"#,
        message = powershell_string(&plan.message),
        title = powershell_string(plan.title),
        buttons = buttons,
    );
    let output = command_with_no_window(Path::new("powershell"))
        .args(["-NoProfile", "-Command", &script])
        .output()
        .context("failed to show migration prompt")?;
    if !output.status.success() {
        return Ok(None);
    }
    match String::from_utf8_lossy(&output.stdout).trim() {
        "Yes" => Ok(detected_data_dir.map(Path::to_path_buf)),
        "No" | "OK" => choose_legacy_data_dir(locale),
        _ => Ok(None),
    }
}

#[cfg(target_os = "windows")]
fn choose_legacy_data_dir(locale: AppLocale) -> Result<Option<PathBuf>> {
    let description = match locale {
        AppLocale::ZhCn | AppLocale::ZhTw | AppLocale::ZhHk => "选择旧版本目录或其中的 data 目录",
        _ => "Choose the old portable folder or its data folder",
    };
    let script = format!(
        r#"
Add-Type -AssemblyName System.Windows.Forms
$dialog = New-Object System.Windows.Forms.FolderBrowserDialog
$dialog.Description = {description}
if ($dialog.ShowDialog() -eq 'OK') {{
  Write-Output $dialog.SelectedPath
}}
"#,
        description = powershell_string(description),
    );
    let output = command_with_no_window(Path::new("powershell"))
        .args(["-NoProfile", "-Command", &script])
        .output()
        .context("failed to show folder chooser")?;
    if !output.status.success() {
        return Ok(None);
    }
    let value = String::from_utf8_lossy(&output.stdout).trim().to_string();
    if value.is_empty() {
        Ok(None)
    } else {
        Ok(Some(PathBuf::from(value)))
    }
}

#[cfg(not(any(target_os = "macos", target_os = "windows")))]
fn prompt_legacy_migration_source(
    _detected_data_dir: Option<&Path>,
    _locale: AppLocale,
) -> Result<Option<PathBuf>> {
    Ok(None)
}

fn venv_python_path(app_dir: &Path) -> PathBuf {
    if cfg!(windows) {
        app_dir.join(".venv").join("Scripts").join("python.exe")
    } else {
        app_dir.join(".venv").join("bin").join("python")
    }
}

fn python_path_for_app(app_dir: &Path) -> String {
    let deps = app_dir.join(".deps");
    if deps.exists() {
        format!(
            "{}{}{}",
            app_dir.display(),
            env_path_separator(),
            deps.display()
        )
    } else {
        app_dir.display().to_string()
    }
}

fn env_path_separator() -> &'static str {
    if cfg!(windows) {
        ";"
    } else {
        ":"
    }
}

fn open_log_file(path: &Path) -> Result<File> {
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent)?;
    }
    OpenOptions::new()
        .create(true)
        .append(true)
        .open(path)
        .with_context(|| format!("failed to open log file {}", path.display()))
}

fn command_with_no_window(program: &Path) -> Command {
    let mut command = Command::new(program);
    configure_no_window(&mut command);
    command
}

#[cfg(windows)]
fn configure_no_window(command: &mut Command) {
    use std::os::windows::process::CommandExt;
    command.creation_flags(0x08000000);
}

#[cfg(not(windows))]
fn configure_no_window(_command: &mut Command) {}

#[cfg(test)]
mod tests;

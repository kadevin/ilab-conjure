use anyhow::{anyhow, Context, Result};
use base64::{engine::general_purpose, Engine as _};
use ed25519_dalek::{Signature, Verifier, VerifyingKey};
use std::{
    cmp::Ordering,
    collections::BTreeMap,
    env,
    fs::{self, File, OpenOptions},
    io::{Read, Write},
    net::TcpStream,
    path::{Path, PathBuf},
    process::{Child, Command, Stdio},
    thread,
    time::{Duration, Instant, SystemTime, UNIX_EPOCH},
};

pub mod standard_update;

pub const APP_NAME: &str = "iLab GPT CONJURE";
pub const DEFAULT_PORT: u16 = 8787;
pub const WEBUI_URL: &str = "http://127.0.0.1:8787/";
pub const HEALTH_PATH: &str = "/api/health";
pub const LOG_FILE_NAME: &str = "webui-server.log";
pub const PROJECT_URL: &str = "https://github.com/kadevin/ilab-gpt-conjure";
pub const RELEASES_URL: &str = "https://github.com/kadevin/ilab-gpt-conjure/releases/latest";
pub const LATEST_UPDATE_MANIFEST_URL: &str =
    "https://github.com/kadevin/ilab-gpt-conjure/releases/latest/download/latest.json";
pub const UPDATE_SIGNING_PUBLIC_KEY_B64: &str =
    include_str!("../assets/update-signing-public-key.b64");
pub const DEFAULT_LOCALE_TAG: &str = "zh-CN";

const WAIT_TIMEOUT: Duration = Duration::from_secs(30);
const HEALTH_POLL_INTERVAL: Duration = Duration::from_millis(500);

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum AppLocale {
    ZhCn,
    ZhTw,
    ZhHk,
    Ja,
    Ko,
    En,
    Es,
    Pt,
    Fr,
    De,
    Ru,
    It,
    Hi,
}

impl AppLocale {
    pub fn from_language_tag(value: &str) -> Option<Self> {
        let language = normalize_language_tag(value)?;
        match language.as_str() {
            "zh-cn" => return Some(Self::ZhCn),
            "zh-tw" => return Some(Self::ZhTw),
            "zh-hk" => return Some(Self::ZhHk),
            "ja" => return Some(Self::Ja),
            "ko" => return Some(Self::Ko),
            "en" => return Some(Self::En),
            "es" => return Some(Self::Es),
            "pt" => return Some(Self::Pt),
            "fr" => return Some(Self::Fr),
            "de" => return Some(Self::De),
            "ru" => return Some(Self::Ru),
            "it" => return Some(Self::It),
            "hi" => return Some(Self::Hi),
            _ => {}
        }
        if language.starts_with("zh-hk") || language.starts_with("zh-mo") {
            return Some(Self::ZhHk);
        }
        if language.starts_with("zh-tw") || language.starts_with("zh-hant") {
            return Some(Self::ZhTw);
        }
        if language.starts_with("zh-cn")
            || language.starts_with("zh-sg")
            || language.starts_with("zh-hans")
            || language == "zh"
        {
            return Some(Self::ZhCn);
        }
        if language.starts_with("ja") {
            return Some(Self::Ja);
        }
        if language.starts_with("ko") {
            return Some(Self::Ko);
        }
        if language.starts_with("en") {
            return Some(Self::En);
        }
        if language.starts_with("es") {
            return Some(Self::Es);
        }
        if language.starts_with("pt") {
            return Some(Self::Pt);
        }
        if language.starts_with("fr") {
            return Some(Self::Fr);
        }
        if language.starts_with("de") {
            return Some(Self::De);
        }
        if language.starts_with("ru") {
            return Some(Self::Ru);
        }
        if language.starts_with("it") {
            return Some(Self::It);
        }
        if language.starts_with("hi") {
            return Some(Self::Hi);
        }
        None
    }

    pub fn tag(self) -> &'static str {
        match self {
            Self::ZhCn => "zh-CN",
            Self::ZhTw => "zh-TW",
            Self::ZhHk => "zh-HK",
            Self::Ja => "ja",
            Self::Ko => "ko",
            Self::En => "en",
            Self::Es => "es",
            Self::Pt => "pt",
            Self::Fr => "fr",
            Self::De => "de",
            Self::Ru => "ru",
            Self::It => "it",
            Self::Hi => "hi",
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct MenuLabels {
    pub open_webui: &'static str,
    pub open_settings: &'static str,
    pub open_history: &'static str,
    pub check_updates: &'static str,
    pub about: &'static str,
    pub restart: &'static str,
    pub quit: &'static str,
}

pub fn localized_menu_labels(locale: AppLocale) -> MenuLabels {
    match locale {
        AppLocale::ZhCn => MenuLabels {
            open_webui: "打开 WebUI",
            open_settings: "打开设置",
            open_history: "历史库",
            check_updates: "检查更新",
            about: "关于 iLab GPT CONJURE",
            restart: "重启 WebUI 服务",
            quit: "退出",
        },
        AppLocale::ZhTw => MenuLabels {
            open_webui: "開啟 WebUI",
            open_settings: "開啟設定",
            open_history: "歷史庫",
            check_updates: "檢查更新",
            about: "關於 iLab GPT CONJURE",
            restart: "重新啟動 WebUI 服務",
            quit: "結束",
        },
        AppLocale::ZhHk => MenuLabels {
            open_webui: "開啟 WebUI",
            open_settings: "開啟設定",
            open_history: "歷史庫",
            check_updates: "檢查更新",
            about: "關於 iLab GPT CONJURE",
            restart: "重新啟動 WebUI 服務",
            quit: "結束",
        },
        AppLocale::Ja => MenuLabels {
            open_webui: "WebUI を開く",
            open_settings: "設定を開く",
            open_history: "履歴ライブラリ",
            check_updates: "アップデートを確認",
            about: "iLab GPT CONJURE について",
            restart: "WebUI サービスを再起動",
            quit: "終了",
        },
        AppLocale::Ko => MenuLabels {
            open_webui: "WebUI 열기",
            open_settings: "설정 열기",
            open_history: "기록 라이브러리",
            check_updates: "업데이트 확인",
            about: "iLab GPT CONJURE 정보",
            restart: "WebUI 서비스 다시 시작",
            quit: "종료",
        },
        AppLocale::En => MenuLabels {
            open_webui: "Open WebUI",
            open_settings: "Open Settings",
            open_history: "History Library",
            check_updates: "Check for Updates",
            about: "About iLab GPT CONJURE",
            restart: "Restart WebUI Service",
            quit: "Quit",
        },
        AppLocale::Es => MenuLabels {
            open_webui: "Abrir WebUI",
            open_settings: "Abrir ajustes",
            open_history: "Historial",
            check_updates: "Buscar actualizaciones",
            about: "Acerca de iLab GPT CONJURE",
            restart: "Reiniciar servicio WebUI",
            quit: "Salir",
        },
        AppLocale::Pt => MenuLabels {
            open_webui: "Abrir WebUI",
            open_settings: "Abrir configurações",
            open_history: "Histórico",
            check_updates: "Verificar atualizações",
            about: "Sobre iLab GPT CONJURE",
            restart: "Reiniciar serviço WebUI",
            quit: "Sair",
        },
        AppLocale::Fr => MenuLabels {
            open_webui: "Ouvrir WebUI",
            open_settings: "Ouvrir les réglages",
            open_history: "Historique",
            check_updates: "Rechercher des mises à jour",
            about: "À propos de iLab GPT CONJURE",
            restart: "Redémarrer le service WebUI",
            quit: "Quitter",
        },
        AppLocale::De => MenuLabels {
            open_webui: "WebUI öffnen",
            open_settings: "Einstellungen öffnen",
            open_history: "Verlauf",
            check_updates: "Nach Updates suchen",
            about: "Über iLab GPT CONJURE",
            restart: "WebUI-Dienst neu starten",
            quit: "Beenden",
        },
        AppLocale::Ru => MenuLabels {
            open_webui: "Открыть WebUI",
            open_settings: "Открыть настройки",
            open_history: "История",
            check_updates: "Проверить обновления",
            about: "О iLab GPT CONJURE",
            restart: "Перезапустить службу WebUI",
            quit: "Выйти",
        },
        AppLocale::It => MenuLabels {
            open_webui: "Apri WebUI",
            open_settings: "Apri impostazioni",
            open_history: "Cronologia",
            check_updates: "Controlla aggiornamenti",
            about: "Informazioni su iLab GPT CONJURE",
            restart: "Riavvia servizio WebUI",
            quit: "Esci",
        },
        AppLocale::Hi => MenuLabels {
            open_webui: "WebUI खोलें",
            open_settings: "सेटिंग्स खोलें",
            open_history: "इतिहास लाइब्रेरी",
            check_updates: "अपडेट जांचें",
            about: "iLab GPT CONJURE के बारे में",
            restart: "WebUI सेवा पुनः शुरू करें",
            quit: "बाहर निकलें",
        },
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct AboutLabels {
    pub title: &'static str,
    pub version: &'static str,
    pub open_source: &'static str,
    pub check_updates: &'static str,
    pub open_project: &'static str,
    pub close: &'static str,
}

pub fn localized_about_labels(locale: AppLocale) -> AboutLabels {
    match locale {
        AppLocale::ZhCn => AboutLabels {
            title: "关于 iLab GPT CONJURE",
            version: "版本",
            open_source: "开源地址",
            check_updates: "检查更新",
            open_project: "打开开源地址",
            close: "关闭",
        },
        AppLocale::ZhTw | AppLocale::ZhHk => AboutLabels {
            title: "關於 iLab GPT CONJURE",
            version: "版本",
            open_source: "開源地址",
            check_updates: "檢查更新",
            open_project: "開啟開源地址",
            close: "關閉",
        },
        _ => AboutLabels {
            title: "About iLab GPT CONJURE",
            version: "Version",
            open_source: "Open source",
            check_updates: "Check for Updates",
            open_project: "Open Source",
            close: "Close",
        },
    }
}

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
pub struct UpdateLabels {
    pub title: &'static str,
    pub current_version: &'static str,
    pub latest_version: &'static str,
    pub up_to_date: &'static str,
    pub update_available: &'static str,
    pub unknown_current_version: &'static str,
    pub check_failed: &'static str,
    pub install_update: &'static str,
    pub install_note: &'static str,
    pub standard_install_note: &'static str,
    pub download_update: &'static str,
    pub download_note: &'static str,
    pub open_release: &'static str,
    pub close: &'static str,
}

pub fn localized_update_labels(locale: AppLocale) -> UpdateLabels {
    match locale {
        AppLocale::ZhCn => UpdateLabels {
            title: "检查更新",
            current_version: "当前版本",
            latest_version: "最新版本",
            up_to_date: "已经是最新版本。",
            update_available: "发现新版本。",
            unknown_current_version: "当前版本不是正式版本，无法自动判断是否需要更新。",
            check_failed: "无法检查更新",
            install_update: "安装更新",
            install_note: "点击“安装更新”会退出启动器，由更新器替换程序文件并保留 data/。",
            standard_install_note: "点击“安装更新”会退出当前 App，自动覆盖安装新版并重新启动；任务、图片和设置保持不变。",
            download_update: "下载新版",
            download_note: "点击“下载新版”会打开标准安装包下载。下载完成后退出当前 App，再用新版包覆盖安装。",
            open_release: "打开发行页",
            close: "关闭",
        },
        AppLocale::ZhTw | AppLocale::ZhHk => UpdateLabels {
            title: "檢查更新",
            current_version: "目前版本",
            latest_version: "最新版本",
            up_to_date: "已經是最新版本。",
            update_available: "發現新版本。",
            unknown_current_version: "目前版本不是正式版本，無法自動判斷是否需要更新。",
            check_failed: "無法檢查更新",
            install_update: "安裝更新",
            install_note: "點擊「安裝更新」會結束啟動器，由更新器替換程式檔案並保留 data/。",
            standard_install_note: "點擊「安裝更新」會結束目前 App，自動覆蓋安裝新版並重新啟動；任務、圖片和設定保持不變。",
            download_update: "下載新版",
            download_note: "點擊「下載新版」會開啟標準安裝包下載。下載完成後結束目前 App，再用新版包覆蓋安裝。",
            open_release: "開啟發行頁",
            close: "關閉",
        },
        _ => UpdateLabels {
            title: "Check for Updates",
            current_version: "Current version",
            latest_version: "Latest version",
            up_to_date: "You are using the latest version.",
            update_available: "A new version is available.",
            unknown_current_version:
                "The current version is not a formal release, so it cannot be compared automatically.",
            check_failed: "Could not check for updates",
            install_update: "Install Update",
            install_note:
                "Install Update will quit the launcher, replace app files, and preserve data/.",
            standard_install_note: "Install Update will quit this app, replace it with the verified update, and relaunch it. Tasks, images, and settings are preserved.",
            download_update: "Download Update",
            download_note:
                "Download Update opens the standard app package. After it downloads, quit this app and install the new package over the old one.",
            open_release: "Open Release",
            close: "Close",
        },
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
struct UpdatePlatform {
    asset: String,
    url: String,
    sha256: String,
    package: String,
}

#[derive(Debug, Clone, PartialEq, Eq)]
struct UpdateSignature {
    algorithm: String,
    value: String,
}

#[derive(Debug, Clone, PartialEq, Eq)]
struct UpdateManifest {
    schema_version: u64,
    version: String,
    release_url: String,
    notes: String,
    signature: Option<UpdateSignature>,
    standard_signature: Option<UpdateSignature>,
    platforms: BTreeMap<String, UpdatePlatform>,
    standard_platforms: BTreeMap<String, UpdatePlatform>,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum UpdateAvailability {
    UpToDate,
    UpdateAvailable,
    UnknownCurrentVersion,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum UpdatePackageKind {
    Portable,
    Standard,
    Source,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum UpdateInstallAction {
    None,
    PortableUpdater,
    StandardMacUpdater,
    DownloadPackage,
}

#[derive(Debug, Clone, PartialEq, Eq)]
struct UpdateCheck {
    current_version: String,
    latest_version: String,
    release_url: String,
    download_url: Option<String>,
    download_sha256: Option<String>,
    package: Option<String>,
    availability: UpdateAvailability,
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

pub fn resolve_launcher_locale(settings_path: &Path) -> AppLocale {
    read_locale_preference(settings_path)
        .or_else(detect_system_locale)
        .unwrap_or(AppLocale::ZhCn)
}

pub fn read_locale_preference(settings_path: &Path) -> Option<AppLocale> {
    let payload: serde_json::Value =
        serde_json::from_str(&fs::read_to_string(settings_path).ok()?).ok()?;
    payload
        .get("locale")
        .and_then(|value| value.as_str())
        .and_then(AppLocale::from_language_tag)
}

pub fn detect_system_locale() -> Option<AppLocale> {
    system_language_candidates()
        .into_iter()
        .find_map(|candidate| AppLocale::from_language_tag(&candidate))
}

fn system_language_candidates() -> Vec<String> {
    let mut candidates = Vec::new();
    candidates.extend(platform_language_candidates());
    for key in ["LC_ALL", "LC_MESSAGES", "LANG", "LANGUAGE"] {
        if let Ok(value) = env::var(key) {
            candidates.extend(
                value
                    .split(':')
                    .map(str::trim)
                    .filter(|candidate| !candidate.is_empty())
                    .map(str::to_string),
            );
        }
    }
    candidates
}

#[cfg(target_os = "macos")]
fn platform_language_candidates() -> Vec<String> {
    let Ok(output) = Command::new("defaults")
        .args(["read", "-g", "AppleLanguages"])
        .output()
    else {
        return Vec::new();
    };
    if !output.status.success() {
        return Vec::new();
    }
    String::from_utf8_lossy(&output.stdout)
        .lines()
        .map(|line| {
            line.trim()
                .trim_matches(|c| matches!(c, '"' | ',' | '(' | ')' | ' ' | '\t'))
                .to_string()
        })
        .filter(|candidate| !candidate.is_empty())
        .collect()
}

#[cfg(target_os = "windows")]
fn platform_language_candidates() -> Vec<String> {
    let Ok(output) = command_with_no_window(Path::new("powershell"))
        .args([
            "-NoProfile",
            "-Command",
            "[System.Globalization.CultureInfo]::CurrentUICulture.Name",
        ])
        .output()
    else {
        return Vec::new();
    };
    if !output.status.success() {
        return Vec::new();
    }
    String::from_utf8_lossy(&output.stdout)
        .lines()
        .map(str::trim)
        .filter(|candidate| !candidate.is_empty())
        .map(str::to_string)
        .collect()
}

#[cfg(not(any(target_os = "macos", target_os = "windows")))]
fn platform_language_candidates() -> Vec<String> {
    Vec::new()
}

fn normalize_language_tag(value: &str) -> Option<String> {
    let language = value
        .trim()
        .split('.')
        .next()
        .unwrap_or("")
        .replace('_', "-")
        .to_lowercase();
    (!language.is_empty()).then_some(language)
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

fn version_label_from_raw(value: &str) -> String {
    let clean = value.trim().trim_start_matches('v').trim_start_matches('V');
    if is_semver_like(clean) {
        format!("v{clean}")
    } else if value.trim().is_empty() {
        version_label_from_raw(env!("CARGO_PKG_VERSION"))
    } else {
        value.trim().to_string()
    }
}

fn is_semver_like(value: &str) -> bool {
    let mut parts = value.split('.');
    let Some(major) = parts.next() else {
        return false;
    };
    let Some(minor) = parts.next() else {
        return false;
    };
    let Some(patch) = parts.next() else {
        return false;
    };
    [major, minor, patch]
        .iter()
        .all(|part| !part.is_empty() && part.chars().all(|ch| ch.is_ascii_digit()))
}

fn parse_update_manifest_payload(payload: &str) -> Result<UpdateManifest> {
    let value: serde_json::Value =
        serde_json::from_str(payload).context("failed to parse update manifest")?;
    let schema_version = value
        .get("schema_version")
        .and_then(|field| field.as_u64())
        .unwrap_or(1);
    if schema_version != 1 {
        return Err(anyhow!(
            "unsupported update manifest schema_version {schema_version}"
        ));
    }
    let version = value
        .get("version")
        .and_then(|field| field.as_str())
        .map(str::trim)
        .filter(|field| !field.is_empty())
        .ok_or_else(|| anyhow!("update manifest did not include version"))?
        .to_string();
    let release_url = value
        .get("release_url")
        .and_then(|field| field.as_str())
        .map(str::trim)
        .filter(|field| !field.is_empty())
        .unwrap_or(RELEASES_URL)
        .to_string();
    let notes = value
        .get("notes")
        .and_then(|field| field.as_str())
        .unwrap_or("")
        .trim()
        .to_string();
    let signature = parse_update_signature(value.get("signature"));
    let standard_signature = parse_update_signature(value.get("standard_signature"));
    let platforms = parse_update_platforms(value.get("platforms"), "platforms")?;
    let standard_platforms =
        parse_optional_update_platforms(value.get("standard_platforms"), "standard_platforms")?;
    if platforms.is_empty() {
        return Err(anyhow!(
            "update manifest did not include any usable platform entries"
        ));
    }

    Ok(UpdateManifest {
        schema_version,
        version,
        release_url,
        notes,
        signature,
        standard_signature,
        platforms,
        standard_platforms,
    })
}

fn parse_update_signature(value: Option<&serde_json::Value>) -> Option<UpdateSignature> {
    let object = value?.as_object()?;
    let algorithm = object
        .get("algorithm")
        .and_then(|field| field.as_str())
        .map(str::trim)
        .filter(|field| !field.is_empty())?;
    let value = object
        .get("value")
        .and_then(|field| field.as_str())
        .map(str::trim)
        .filter(|field| !field.is_empty())?;
    Some(UpdateSignature {
        algorithm: algorithm.to_string(),
        value: value.to_string(),
    })
}

fn parse_optional_update_platforms(
    value: Option<&serde_json::Value>,
    field_name: &str,
) -> Result<BTreeMap<String, UpdatePlatform>> {
    match value {
        Some(_) => parse_update_platforms(value, field_name),
        None => Ok(BTreeMap::new()),
    }
}

fn parse_update_platforms(
    value: Option<&serde_json::Value>,
    field_name: &str,
) -> Result<BTreeMap<String, UpdatePlatform>> {
    let mut platforms = BTreeMap::new();
    let platform_values = value
        .and_then(|field| field.as_object())
        .ok_or_else(|| anyhow!("update manifest did not include {field_name}"))?;
    for (key, platform) in platform_values {
        let Some(url) = platform
            .get("url")
            .and_then(|field| field.as_str())
            .map(str::trim)
            .filter(|field| !field.is_empty())
        else {
            continue;
        };
        let Some(sha256) = platform
            .get("sha256")
            .and_then(|field| field.as_str())
            .map(str::trim)
            .filter(|field| is_sha256_hex(field))
        else {
            continue;
        };
        let asset = platform
            .get("asset")
            .and_then(|field| field.as_str())
            .map(str::trim)
            .filter(|field| !field.is_empty())
            .map(str::to_string)
            .unwrap_or_else(|| {
                url.rsplit('/')
                    .next()
                    .filter(|name| !name.is_empty())
                    .unwrap_or("update.zip")
                    .to_string()
            });
        let package = platform
            .get("package")
            .and_then(|field| field.as_str())
            .map(str::trim)
            .filter(|field| !field.is_empty())
            .unwrap_or("portable-zip")
            .to_string();
        platforms.insert(
            key.to_string(),
            UpdatePlatform {
                asset,
                url: url.to_string(),
                sha256: sha256.to_ascii_lowercase(),
                package,
            },
        );
    }
    Ok(platforms)
}

fn is_sha256_hex(value: &str) -> bool {
    value.len() == 64 && value.chars().all(|ch| ch.is_ascii_hexdigit())
}

fn update_check_from_manifest(
    current_version: &str,
    manifest: &UpdateManifest,
    package_kind: UpdatePackageKind,
) -> UpdateCheck {
    let latest_version = version_label_from_raw(&manifest.version);
    let availability = match compare_version_labels(current_version, &latest_version) {
        Some(Ordering::Less) => UpdateAvailability::UpdateAvailable,
        Some(Ordering::Equal | Ordering::Greater) => UpdateAvailability::UpToDate,
        None => UpdateAvailability::UnknownCurrentVersion,
    };
    let platform_map = match package_kind {
        UpdatePackageKind::Portable => &manifest.platforms,
        UpdatePackageKind::Standard => &manifest.standard_platforms,
        UpdatePackageKind::Source => &manifest.platforms,
    };
    let platform = platform_map.get(current_update_platform_key());
    UpdateCheck {
        current_version: current_version.to_string(),
        latest_version,
        release_url: manifest.release_url.clone(),
        download_url: platform.map(|entry| entry.url.clone()),
        download_sha256: platform.map(|entry| entry.sha256.clone()),
        package: platform.map(|entry| entry.package.clone()),
        availability,
    }
}

pub fn verify_update_manifest_file(path: &Path) -> Result<()> {
    let payload = fs::read_to_string(path)
        .with_context(|| format!("failed to read update manifest {}", path.display()))?;
    let manifest = parse_update_manifest_payload(&payload)?;
    verify_update_manifest_signature(&manifest)
}

fn verify_update_manifest_signature(manifest: &UpdateManifest) -> Result<()> {
    verify_update_manifest_signature_with_key(manifest, UPDATE_SIGNING_PUBLIC_KEY_B64)
}

fn verify_update_manifest_signature_with_key(
    manifest: &UpdateManifest,
    public_key_b64: &str,
) -> Result<()> {
    verify_signature_with_key(
        manifest
            .signature
            .as_ref()
            .ok_or_else(|| anyhow!("update manifest is missing signature"))?,
        update_manifest_signing_payload(manifest).as_bytes(),
        public_key_b64,
    )?;
    if !manifest.standard_platforms.is_empty() {
        verify_signature_with_key(
            manifest
                .standard_signature
                .as_ref()
                .ok_or_else(|| anyhow!("update manifest is missing standard_signature"))?,
            standard_update_manifest_signing_payload(manifest).as_bytes(),
            public_key_b64,
        )?;
    }
    Ok(())
}

fn verify_signature_with_key(
    signature: &UpdateSignature,
    payload: &[u8],
    public_key_b64: &str,
) -> Result<()> {
    if !signature.algorithm.eq_ignore_ascii_case("ed25519") {
        return Err(anyhow!(
            "unsupported update manifest signature algorithm {}",
            signature.algorithm
        ));
    }
    let public_bytes = general_purpose::STANDARD
        .decode(public_key_b64.trim())
        .context("failed to decode update signing public key")?;
    let public_key_bytes: [u8; 32] = public_bytes
        .as_slice()
        .try_into()
        .map_err(|_| anyhow!("update signing public key must be 32 bytes"))?;
    let verifying_key = VerifyingKey::from_bytes(&public_key_bytes)
        .context("failed to load update signing public key")?;
    let signature_bytes = general_purpose::STANDARD
        .decode(signature.value.trim())
        .context("failed to decode update manifest signature")?;
    let signature_bytes: [u8; 64] = signature_bytes
        .as_slice()
        .try_into()
        .map_err(|_| anyhow!("update manifest signature must be 64 bytes"))?;
    let signature = Signature::from_bytes(&signature_bytes);
    verifying_key
        .verify(payload, &signature)
        .context("update manifest signature verification failed")
}

fn update_manifest_signing_payload(manifest: &UpdateManifest) -> String {
    let mut lines = vec!["ilab-gpt-conjure-update-manifest-v1".to_string()];
    push_signing_field(
        &mut lines,
        "schema_version",
        &manifest.schema_version.to_string(),
    );
    push_signing_field(&mut lines, "version", &manifest.version);
    push_signing_field(&mut lines, "release_url", &manifest.release_url);
    for (platform_key, platform) in &manifest.platforms {
        push_signing_field(&mut lines, "platform", platform_key);
        push_signing_field(&mut lines, "asset", &platform.asset);
        push_signing_field(&mut lines, "url", &platform.url);
        push_signing_field(&mut lines, "sha256", &platform.sha256);
        push_signing_field(&mut lines, "package", &platform.package);
    }
    let mut payload = lines.join("\n");
    payload.push('\n');
    payload
}

fn standard_update_manifest_signing_payload(manifest: &UpdateManifest) -> String {
    let mut lines = vec!["ilab-gpt-conjure-standard-update-manifest-v1".to_string()];
    push_signing_field(
        &mut lines,
        "schema_version",
        &manifest.schema_version.to_string(),
    );
    push_signing_field(&mut lines, "version", &manifest.version);
    push_signing_field(&mut lines, "release_url", &manifest.release_url);
    for (platform_key, platform) in &manifest.standard_platforms {
        push_signing_field(&mut lines, "standard_platform", platform_key);
        push_signing_field(&mut lines, "asset", &platform.asset);
        push_signing_field(&mut lines, "url", &platform.url);
        push_signing_field(&mut lines, "sha256", &platform.sha256);
        push_signing_field(&mut lines, "package", &platform.package);
    }
    let mut payload = lines.join("\n");
    payload.push('\n');
    payload
}

fn push_signing_field(lines: &mut Vec<String>, name: &str, value: &str) {
    lines.push(format!("{name}:{}:{value}", value.len()));
}

fn current_update_platform_key() -> &'static str {
    #[cfg(all(target_os = "macos", target_arch = "aarch64"))]
    {
        "darwin-aarch64"
    }
    #[cfg(all(target_os = "macos", target_arch = "x86_64"))]
    {
        "darwin-x86_64"
    }
    #[cfg(all(target_os = "windows", target_arch = "x86_64"))]
    {
        "windows-x86_64"
    }
    #[cfg(not(any(
        all(target_os = "macos", target_arch = "aarch64"),
        all(target_os = "macos", target_arch = "x86_64"),
        all(target_os = "windows", target_arch = "x86_64")
    )))]
    {
        "unsupported-platform"
    }
}

fn compare_version_labels(current: &str, latest: &str) -> Option<Ordering> {
    Some(parse_semver_label(current)?.cmp(&parse_semver_label(latest)?))
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

fn parse_semver_label(value: &str) -> Option<(u64, u64, u64)> {
    let clean = value
        .trim()
        .trim_start_matches('v')
        .trim_start_matches('V')
        .split(['-', '+'])
        .next()?;
    let mut parts = clean.split('.');
    let major = parts.next()?.parse().ok()?;
    let minor = parts.next()?.parse().ok()?;
    let patch = parts.next()?.parse().ok()?;
    Some((major, minor, patch))
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
                    .args(["-m", "pip", "install", "-r"])
                    .arg(self.config.app_dir.join("requirements-webui.txt")),
                "install WebUI dependencies",
            )?;
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
                "uvicorn",
                self.config.uvicorn_app(),
                "--host",
                "127.0.0.1",
                "--port",
                &self.config.port.to_string(),
                "--no-access-log",
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

        let child = command
            .spawn()
            .context("failed to start Uvicorn WebUI service")?;
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

    fill_rotated_ellipse(&mut rgba, size, 8.3, 6.3, 1.45, 4.15, -9.0, white);
    fill_rotated_ellipse(&mut rgba, size, 12.7, 6.6, 1.35, 4.25, 36.0, white);
    fill_ellipse(&mut rgba, size, 14.4, 15.6, 6.3, 4.8, white);
    fill_ellipse(&mut rgba, size, 8.9, 12.4, 4.6, 4.25, white);
    fill_ellipse(&mut rgba, size, 19.3, 13.9, 1.85, 1.95, white);
    fill_ellipse(&mut rgba, size, 9.4, 19.1, 2.7, 1.15, white);
    fill_ellipse(&mut rgba, size, 15.3, 19.2, 3.2, 1.15, white);
    fill_rotated_ellipse(&mut rgba, size, 8.2, 5.9, 0.52, 2.25, -9.0, transparent);
    fill_rotated_ellipse(&mut rgba, size, 12.45, 6.0, 0.48, 2.15, 36.0, transparent);
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
    cx: f32,
    cy: f32,
    rx: f32,
    ry: f32,
    angle_degrees: f32,
    color: [u8; 4],
) {
    let scale = size as f32 / RABBIT_ICON_SOURCE_VIEWBOX;
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
        .arg("-c")
        .arg("import fastapi, uvicorn, multipart, httpx, PIL")
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
            .join(APP_NAME)
    } else if cfg!(windows) {
        env::var_os("APPDATA")
            .map(PathBuf::from)
            .or_else(|| home_dir().map(|home| home.join("AppData").join("Roaming")))
            .unwrap_or_else(|| PathBuf::from("."))
            .join(APP_NAME)
    } else {
        env::var_os("XDG_DATA_HOME")
            .map(PathBuf::from)
            .or_else(|| home_dir().map(|home| home.join(".local").join("share")))
            .unwrap_or_else(|| PathBuf::from("."))
            .join(APP_NAME)
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
mod tests {
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
        assert_eq!(zh.about, "关于 iLab GPT CONJURE");
        assert_eq!(zh.restart, "重启 WebUI 服务");
        assert_eq!(zh.quit, "退出");

        let en = localized_menu_labels(AppLocale::En);
        assert_eq!(en.open_webui, "Open WebUI");
        assert_eq!(en.open_settings, "Open Settings");
        assert_eq!(en.open_history, "History Library");
        assert_eq!(en.check_updates, "Check for Updates");
        assert_eq!(en.about, "About iLab GPT CONJURE");
        assert_eq!(en.restart, "Restart WebUI Service");
        assert_eq!(en.quit, "Quit");
    }

    #[test]
    fn localized_about_labels_cover_simplified_chinese_and_english() {
        let zh = localized_about_labels(AppLocale::ZhCn);
        assert_eq!(zh.title, "关于 iLab GPT CONJURE");
        assert_eq!(zh.version, "版本");
        assert_eq!(zh.open_source, "开源地址");
        assert_eq!(zh.check_updates, "检查更新");
        assert_eq!(zh.open_project, "打开开源地址");
        assert_eq!(zh.close, "关闭");

        let en = localized_about_labels(AppLocale::En);
        assert_eq!(en.title, "About iLab GPT CONJURE");
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
                "release_url": "https://github.com/kadevin/ilab-gpt-conjure/releases/tag/v0.6.0",
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
            "https://github.com/kadevin/ilab-gpt-conjure/releases/tag/v0.6.0"
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
            update_check_from_manifest("v0.6.0", &manifest, UpdatePackageKind::Portable)
                .availability,
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
        assert!(
            windows_candidates.contains(&PathBuf::from("C:/Tools/iLab GPT CONJURE/resources/app"))
        );
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
}

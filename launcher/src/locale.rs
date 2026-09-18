#[cfg(target_os = "windows")]
use crate::command_with_no_window;
#[cfg(target_os = "macos")]
use std::process::Command;
use std::{env, fs, path::Path};

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
            about: "关于 iLab CONJURE",
            restart: "重启 WebUI 服务",
            quit: "退出",
        },
        AppLocale::ZhTw => MenuLabels {
            open_webui: "開啟 WebUI",
            open_settings: "開啟設定",
            open_history: "歷史庫",
            check_updates: "檢查更新",
            about: "關於 iLab CONJURE",
            restart: "重新啟動 WebUI 服務",
            quit: "結束",
        },
        AppLocale::ZhHk => MenuLabels {
            open_webui: "開啟 WebUI",
            open_settings: "開啟設定",
            open_history: "歷史庫",
            check_updates: "檢查更新",
            about: "關於 iLab CONJURE",
            restart: "重新啟動 WebUI 服務",
            quit: "結束",
        },
        AppLocale::Ja => MenuLabels {
            open_webui: "WebUI を開く",
            open_settings: "設定を開く",
            open_history: "履歴ライブラリ",
            check_updates: "アップデートを確認",
            about: "iLab CONJURE について",
            restart: "WebUI サービスを再起動",
            quit: "終了",
        },
        AppLocale::Ko => MenuLabels {
            open_webui: "WebUI 열기",
            open_settings: "설정 열기",
            open_history: "기록 라이브러리",
            check_updates: "업데이트 확인",
            about: "iLab CONJURE 정보",
            restart: "WebUI 서비스 다시 시작",
            quit: "종료",
        },
        AppLocale::En => MenuLabels {
            open_webui: "Open WebUI",
            open_settings: "Open Settings",
            open_history: "History Library",
            check_updates: "Check for Updates",
            about: "About iLab CONJURE",
            restart: "Restart WebUI Service",
            quit: "Quit",
        },
        AppLocale::Es => MenuLabels {
            open_webui: "Abrir WebUI",
            open_settings: "Abrir ajustes",
            open_history: "Historial",
            check_updates: "Buscar actualizaciones",
            about: "Acerca de iLab CONJURE",
            restart: "Reiniciar servicio WebUI",
            quit: "Salir",
        },
        AppLocale::Pt => MenuLabels {
            open_webui: "Abrir WebUI",
            open_settings: "Abrir configurações",
            open_history: "Histórico",
            check_updates: "Verificar atualizações",
            about: "Sobre iLab CONJURE",
            restart: "Reiniciar serviço WebUI",
            quit: "Sair",
        },
        AppLocale::Fr => MenuLabels {
            open_webui: "Ouvrir WebUI",
            open_settings: "Ouvrir les réglages",
            open_history: "Historique",
            check_updates: "Rechercher des mises à jour",
            about: "À propos de iLab CONJURE",
            restart: "Redémarrer le service WebUI",
            quit: "Quitter",
        },
        AppLocale::De => MenuLabels {
            open_webui: "WebUI öffnen",
            open_settings: "Einstellungen öffnen",
            open_history: "Verlauf",
            check_updates: "Nach Updates suchen",
            about: "Über iLab CONJURE",
            restart: "WebUI-Dienst neu starten",
            quit: "Beenden",
        },
        AppLocale::Ru => MenuLabels {
            open_webui: "Открыть WebUI",
            open_settings: "Открыть настройки",
            open_history: "История",
            check_updates: "Проверить обновления",
            about: "О iLab CONJURE",
            restart: "Перезапустить службу WebUI",
            quit: "Выйти",
        },
        AppLocale::It => MenuLabels {
            open_webui: "Apri WebUI",
            open_settings: "Apri impostazioni",
            open_history: "Cronologia",
            check_updates: "Controlla aggiornamenti",
            about: "Informazioni su iLab CONJURE",
            restart: "Riavvia servizio WebUI",
            quit: "Esci",
        },
        AppLocale::Hi => MenuLabels {
            open_webui: "WebUI खोलें",
            open_settings: "सेटिंग्स खोलें",
            open_history: "इतिहास लाइब्रेरी",
            check_updates: "अपडेट जांचें",
            about: "iLab CONJURE के बारे में",
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
            title: "关于 iLab CONJURE",
            version: "版本",
            open_source: "开源地址",
            check_updates: "检查更新",
            open_project: "打开开源地址",
            close: "关闭",
        },
        AppLocale::ZhTw | AppLocale::ZhHk => AboutLabels {
            title: "關於 iLab CONJURE",
            version: "版本",
            open_source: "開源地址",
            check_updates: "檢查更新",
            open_project: "開啟開源地址",
            close: "關閉",
        },
        _ => AboutLabels {
            title: "About iLab CONJURE",
            version: "Version",
            open_source: "Open source",
            check_updates: "Check for Updates",
            open_project: "Open Source",
            close: "Close",
        },
    }
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

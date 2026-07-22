from __future__ import annotations

import re
from pathlib import Path

from tests.webui_helpers import WebUIStaticTestCase


class WebUIStaticI18nTests(WebUIStaticTestCase):
    def test_history_document_title_uses_multimodel_product_brand_in_every_locale(self) -> None:
        locale_paths = sorted(Path("codex_image/webui/frontend/src/i18n").glob("*.ts"))
        locale_paths = [path for path in locale_paths if path.name not in {"types.ts", "dictionaries.ts"}]

        self.assertEqual(13, len(locale_paths))
        for path in locale_paths:
            source = path.read_text(encoding="utf-8")
            self.assertRegex(source, r'"history\.documentTitle": "[^"]*iLab CONJURE"')
            self.assertNotIn("iLab GPT CONJURE", source)
            self.assertNotIn("iLabGPTCONJURE", source)

    def test_model_provider_selection_copy_exists_in_every_locale(self) -> None:
        required_keys = (
            "modelSelection.family",
            "modelSelection.concreteModel",
            "modelSelection.provider",
            "modelSelection.providerUnavailable",
            "modelSelection.openSettings",
            "modelSelection.codexUnavailable",
            "modelSelection.catalogUnavailable",
        )
        locale_paths = sorted(Path("codex_image/webui/frontend/src/i18n").glob("*.ts"))
        locale_paths = [path for path in locale_paths if path.name not in {"types.ts", "dictionaries.ts"}]
        self.assertEqual(13, len(locale_paths))
        for path in locale_paths:
            source = path.read_text(encoding="utf-8")
            for key in required_keys:
                self.assertIn(f'"{key}"', source, f"{path.name} is missing {key}")

    def test_api_binding_ratio_prompt_copy_exists_in_every_locale(self) -> None:
        required_keys = (
            "apiSettings.appendRatioPrompt",
            "apiSettings.defaultProviderForModel",
            "apiSettings.removeBinding",
            "apiSettings.providerIcon",
        )
        locale_paths = sorted(Path("codex_image/webui/frontend/src/i18n").glob("*.ts"))
        locale_paths = [path for path in locale_paths if path.name not in {"types.ts", "dictionaries.ts"}]
        self.assertEqual(13, len(locale_paths))
        for path in locale_paths:
            source = path.read_text(encoding="utf-8")
            for key in required_keys:
                self.assertIn(f'"{key}"', source, f"{path.name} is missing {key}")

        submit_source = Path("codex_image/webui/frontend/src/task-submit.ts").read_text(encoding="utf-8")
        self.assertIn('form.append("ui_language", currentLocaleCode())', submit_source)
        simplified_default_labels = {
            "zh-cn.ts": "设为默认供应商",
            "zh-tw.ts": "設為預設供應商",
            "zh-hk.ts": "設為預設供應商",
            "en.ts": "Default provider",
        }
        for filename, label in simplified_default_labels.items():
            source = (Path("codex_image/webui/frontend/src/i18n") / filename).read_text(encoding="utf-8")
            self.assertIn(f'"apiSettings.defaultProviderForModel": "{label}"', source)

        provider_icon_labels = {
            "zh-cn.ts": "Emoji 图标",
            "zh-tw.ts": "Emoji 圖示",
            "zh-hk.ts": "Emoji 圖示",
            "en.ts": "Emoji",
        }
        for filename, label in provider_icon_labels.items():
            source = (Path("codex_image/webui/frontend/src/i18n") / filename).read_text(encoding="utf-8")
            self.assertIn(f'"apiSettings.providerIcon": "{label}"', source)

    def test_mixed_upload_copy_is_localized_in_every_locale(self) -> None:
        expected = {
            "zh-cn.ts": ("点击、拖入或粘贴图片与文件", "点击、拖入或粘贴图片与文件", "添加输入", "支持图片与 Responses 参考文件"),
            "zh-tw.ts": ("點選、拖曳或貼上圖片與檔案", "點選、拖曳或貼上圖片與檔案", "新增輸入", "支援圖片與 Responses 參考檔案"),
            "zh-hk.ts": ("點選、拖曳或貼上圖片與檔案", "點選、拖曳或貼上圖片與檔案", "新增輸入", "支援圖片與 Responses 參考檔案"),
            "ja.ts": ("画像とファイルをクリック、ドロップ、または貼り付け", "画像とファイルをクリック、ドロップ、または貼り付け", "入力を追加", "画像と Responses の参照ファイルに対応"),
            "ko.ts": ("이미지와 파일을 클릭, 드롭 또는 붙여넣기", "이미지와 파일을 클릭, 드롭 또는 붙여넣기", "입력 추가", "이미지 및 Responses 참조 파일 지원"),
            "en.ts": ("Click, drop, or paste images and files", "Click, drop, or paste images and files", "Add input", "Supports images and Responses reference files"),
            "es.ts": ("Haz clic, suelta o pega imágenes y archivos", "Haz clic, suelta o pega imágenes y archivos", "Añadir entrada", "Admite imágenes y archivos de referencia de Responses"),
            "pt.ts": ("Clique, solte ou cole imagens e arquivos", "Clique, solte ou cole imagens e arquivos", "Adicionar entrada", "Compatível com imagens e arquivos de referência do Responses"),
            "fr.ts": ("Cliquez, déposez ou collez des images et des fichiers", "Cliquez, déposez ou collez des images et des fichiers", "Ajouter une entrée", "Images et fichiers de référence pour Responses"),
            "de.ts": ("Bilder und Dateien anklicken, ablegen oder einfügen", "Bilder und Dateien anklicken, ablegen oder einfügen", "Eingabe hinzufügen", "Unterstützt Bilder und Responses-Referenzdateien"),
            "ru.ts": ("Нажмите, перетащите или вставьте изображения и файлы", "Нажмите, перетащите или вставьте изображения и файлы", "Добавить источник", "Изображения и файлы-источники для Responses"),
            "it.ts": ("Fai clic, rilascia o incolla immagini e file", "Fai clic, rilascia o incolla immagini e file", "Aggiungi input", "Immagini e file di riferimento per Responses"),
            "hi.ts": ("चित्र और फ़ाइलें जोड़ने के लिए क्लिक करें, ड्रॉप करें या पेस्ट करें", "चित्र और फ़ाइलें जोड़ने के लिए क्लिक करें, ड्रॉप करें या पेस्ट करें", "इनपुट जोड़ें", "चित्र और Responses संदर्भ फ़ाइलें समर्थित हैं"),
        }
        keys = ("uploadAria", "uploadFull", "uploadCompact", "uploadSubtitle")
        locale_dir = Path("codex_image/webui/frontend/src/i18n")
        self.assertEqual(13, len(expected))
        for filename, values in expected.items():
            source = (locale_dir / filename).read_text(encoding="utf-8")
            for key, value in zip(keys, values):
                self.assertIn(f'"imageInput.{key}": "{value}"', source)

    def test_reference_file_copy_exists_in_every_locale(self) -> None:
        required_keys = (
            "imageInput.referenceTitle",
            "referenceFiles.add",
            "referenceFiles.selected",
            "referenceFiles.recent",
            "referenceFiles.familyPdf",
            "referenceFiles.familySpreadsheet",
            "referenceFiles.familyDocument",
            "referenceFiles.familyText",
            "referenceFiles.visualLimit",
            "referenceFiles.remove",
            "referenceFiles.switchTitle",
            "referenceFiles.switchMessage",
            "referenceFiles.removeAndSwitch",
            "referenceFiles.requiresResponses",
            "referenceFiles.switchToResponses",
            "referenceFiles.openApiSettings",
            "referenceFiles.providerMissing",
            "referenceFiles.missing",
            "referenceFiles.loadFailed",
            "referenceFiles.errorEmpty",
            "referenceFiles.errorUnsupported",
            "referenceFiles.errorMismatch",
            "referenceFiles.errorInvalid",
            "referenceFiles.errorTooLarge",
            "referenceFiles.errorTotalTooLarge",
            "referenceFiles.errorMissing",
            "referenceFiles.errorProviderUnsupported",
            "referenceFiles.responsesEnabled",
            "referenceFiles.historyPathMismatch",
            "history.referenceFiles",
            "history.downloadReferenceFile",
            "history.readdReferenceFile",
        )
        locale_paths = sorted(Path("codex_image/webui/frontend/src/i18n").glob("*.ts"))
        locale_paths = [path for path in locale_paths if path.name not in {"types.ts", "dictionaries.ts"}]
        self.assertEqual(13, len(locale_paths))
        for path in locale_paths:
            source = path.read_text(encoding="utf-8")
            for key in required_keys:
                self.assertIn(f'"{key}"', source, f"{path.name} is missing {key}")

    def test_reference_file_document_family_translation_is_specific_in_every_locale(self) -> None:
        expected = {
            "de.ts": "Dokument",
            "en.ts": "Document",
            "es.ts": "Documento",
            "fr.ts": "Document",
            "hi.ts": "दस्तावेज़",
            "it.ts": "Documento",
            "ja.ts": "ドキュメント",
            "ko.ts": "문서",
            "pt.ts": "Documento",
            "ru.ts": "Документ",
            "zh-cn.ts": "文档",
            "zh-hk.ts": "文件",
            "zh-tw.ts": "文件",
        }
        locale_dir = Path("codex_image/webui/frontend/src/i18n")
        for filename, translation in expected.items():
            source = (locale_dir / filename).read_text(encoding="utf-8")
            self.assertIn(f'"referenceFiles.familyDocument": "{translation}"', source)

    def test_language_bootstrap_detects_browser_language_and_settings_select_replaces_top_nav(self) -> None:
        html = Path("codex_image/webui/static/index.html").read_text(encoding="utf-8")
        nav_actions = html[html.index('<div class="nav-actions">'):html.index('<div id="taskNotificationCenter"')]
        language_panel = html[html.index('<section id="systemSettingsLanguagePanel"'):html.index('</section>', html.index('<section id="systemSettingsLanguagePanel"'))]

        self.assertIn('const LOCALE_STORAGE_KEY = "codex-image-locale-preference";', html)
        self.assertIn("function detectPreferredLocale", html)
        self.assertIn("async function readStoredLocalePreference", html)
        self.assertIn("function persistLocalePreference", html)
        self.assertIn('fetch("/api/settings")', html)
        self.assertIn('body: JSON.stringify({ locale: currentLocale })', html)
        self.assertIn("navigator.languages", html)
        self.assertIn('const valid = new Set(["zh-CN", "zh-TW", "zh-HK", "ja", "ko", "en", "es", "pt", "fr", "de", "ru", "it", "hi"]);', html)
        self.assertRegex(html, r"document\.documentElement\.lang = currentLocale;")
        self.assertRegex(html, r"document\.documentElement\.dataset\.locale = currentLocale;")
        self.assertNotIn('id="languageSwitcher"', html)
        self.assertNotIn('id="languageSelect"', nav_actions)
        self.assertLess(nav_actions.index('id="themeSwitcher"'), nav_actions.index('id="githubLink"'))
        self.assertIn('id="systemSettingsLanguageTab"', html)
        self.assertIn('data-i18n="systemSettings.languageTab"', html)
        self.assertIn('id="languageSelect"', language_panel)
        self.assertIn('<option value="zh-TW">正體中文</option>', language_panel)
        self.assertIn('<option value="zh-HK">繁体中文</option>', language_panel)
        self.assertIn('<option value="es">Español</option>', language_panel)
        self.assertIn('<option value="pt">Português</option>', language_panel)
        self.assertIn('<option value="fr">Français</option>', language_panel)
        self.assertIn('<option value="de">Deutsch</option>', language_panel)
        self.assertIn('<option value="ru">Русский</option>', language_panel)
        self.assertIn('<option value="it">Italiano</option>', language_panel)
        self.assertIn('<option value="hi">हिन्दी</option>', language_panel)
        self.assertIn('language.startsWith("ru")', html)
        self.assertIn('language.startsWith("it")', html)
        self.assertIn('language.startsWith("hi")', html)
        self.assertNotIn("繁體中文（台灣）", language_panel)
        self.assertNotIn("繁體中文（香港）", language_panel)
        self.assertIn('data-i18n="settings.language"', language_panel)
        self.assertIn('data-i18n="settings.languageCopy"', language_panel)
        self.assertIn('data-i18n="languageSettings.instantStatus"', language_panel)
        for locale in ("zh-CN", "zh-TW", "zh-HK", "ja", "ko", "en", "es", "pt", "fr", "de", "ru", "it", "hi"):
            self.assertIn(f'<option value="{locale}"', language_panel)
        self.assertNotIn("settings.status", language_panel)

    def test_i18n_source_exposes_locales_and_dom_translation(self) -> None:
        source_path = Path("codex_image/webui/frontend/src/i18n.ts")
        self.assertTrue(source_path.exists(), "i18n feature module should exist")
        types_path = Path("codex_image/webui/frontend/src/i18n/types.ts")
        dictionaries_path = Path("codex_image/webui/frontend/src/i18n/dictionaries.ts")
        zh_dictionary_path = Path("codex_image/webui/frontend/src/i18n/zh-cn.ts")
        zh_tw_dictionary_path = Path("codex_image/webui/frontend/src/i18n/zh-tw.ts")
        zh_hk_dictionary_path = Path("codex_image/webui/frontend/src/i18n/zh-hk.ts")
        ja_dictionary_path = Path("codex_image/webui/frontend/src/i18n/ja.ts")
        ko_dictionary_path = Path("codex_image/webui/frontend/src/i18n/ko.ts")
        en_dictionary_path = Path("codex_image/webui/frontend/src/i18n/en.ts")
        es_dictionary_path = Path("codex_image/webui/frontend/src/i18n/es.ts")
        pt_dictionary_path = Path("codex_image/webui/frontend/src/i18n/pt.ts")
        fr_dictionary_path = Path("codex_image/webui/frontend/src/i18n/fr.ts")
        de_dictionary_path = Path("codex_image/webui/frontend/src/i18n/de.ts")
        ru_dictionary_path = Path("codex_image/webui/frontend/src/i18n/ru.ts")
        it_dictionary_path = Path("codex_image/webui/frontend/src/i18n/it.ts")
        hi_dictionary_path = Path("codex_image/webui/frontend/src/i18n/hi.ts")
        self.assertTrue(types_path.exists(), "i18n types should be isolated from runtime code")
        self.assertTrue(dictionaries_path.exists(), "i18n dictionary registry should be isolated from runtime code")
        self.assertTrue(zh_dictionary_path.exists(), "zh-CN dictionary should live in its own file")
        self.assertTrue(zh_tw_dictionary_path.exists(), "zh-TW dictionary should live in its own file")
        self.assertTrue(zh_hk_dictionary_path.exists(), "zh-HK dictionary should live in its own file")
        self.assertTrue(ja_dictionary_path.exists(), "Japanese dictionary should live in its own file")
        self.assertTrue(ko_dictionary_path.exists(), "Korean dictionary should live in its own file")
        self.assertTrue(en_dictionary_path.exists(), "English dictionary should live in its own file")
        self.assertTrue(es_dictionary_path.exists(), "Spanish dictionary should live in its own file")
        self.assertTrue(pt_dictionary_path.exists(), "Portuguese dictionary should live in its own file")
        self.assertTrue(fr_dictionary_path.exists(), "French dictionary should live in its own file")
        self.assertTrue(de_dictionary_path.exists(), "German dictionary should live in its own file")
        self.assertTrue(ru_dictionary_path.exists(), "Russian dictionary should live in its own file")
        self.assertTrue(it_dictionary_path.exists(), "Italian dictionary should live in its own file")
        self.assertTrue(hi_dictionary_path.exists(), "Hindi dictionary should live in its own file")

        source = source_path.read_text(encoding="utf-8")
        types_source = types_path.read_text(encoding="utf-8")
        dictionaries_source = dictionaries_path.read_text(encoding="utf-8")
        zh_dictionary_source = zh_dictionary_path.read_text(encoding="utf-8")
        zh_tw_dictionary_source = zh_tw_dictionary_path.read_text(encoding="utf-8")
        zh_hk_dictionary_source = zh_hk_dictionary_path.read_text(encoding="utf-8")
        ja_dictionary_source = ja_dictionary_path.read_text(encoding="utf-8")
        ko_dictionary_source = ko_dictionary_path.read_text(encoding="utf-8")
        en_dictionary_source = en_dictionary_path.read_text(encoding="utf-8")
        es_dictionary_source = es_dictionary_path.read_text(encoding="utf-8")
        pt_dictionary_source = pt_dictionary_path.read_text(encoding="utf-8")
        fr_dictionary_source = fr_dictionary_path.read_text(encoding="utf-8")
        de_dictionary_source = de_dictionary_path.read_text(encoding="utf-8")
        ru_dictionary_source = ru_dictionary_path.read_text(encoding="utf-8")
        it_dictionary_source = it_dictionary_path.read_text(encoding="utf-8")
        hi_dictionary_source = hi_dictionary_path.read_text(encoding="utf-8")
        main_source = Path("codex_image/webui/frontend/src/main.ts").read_text(encoding="utf-8")
        elements_source = Path("codex_image/webui/frontend/src/elements.ts").read_text(encoding="utf-8")

        self.assertIn('export type Locale = "zh-CN" | "zh-TW" | "zh-HK" | "ja" | "ko" | "en" | "es" | "pt" | "fr" | "de" | "ru" | "it" | "hi";', types_source)
        self.assertIn("export type TranslationDictionary", types_source)
        self.assertIn('const LOCALE_STORAGE_KEY = "codex-image-locale-preference";', source)
        self.assertIn('import { DEFAULT_LOCALE, DICTIONARIES, LOCALES } from "./i18n/dictionaries";', source)
        self.assertIn("export function detectPreferredLocale", source)
        self.assertIn("async function readStoredLocalePreference", source)
        self.assertIn("function persistLocalePreference", source)
        self.assertIn('fetch("/api/settings")', source)
        self.assertIn('body: JSON.stringify({ locale: currentLocale })', source)
        self.assertIn("navigator.languages", source)
        self.assertIn('language.startsWith("zh-hk")', source)
        self.assertIn('language.startsWith("ja")', source)
        self.assertIn('language.startsWith("ko")', source)
        self.assertIn('language.startsWith("es")', source)
        self.assertIn('language.startsWith("pt")', source)
        self.assertIn('language.startsWith("fr")', source)
        self.assertIn('language.startsWith("de")', source)
        self.assertIn('language.startsWith("ru")', source)
        self.assertIn('language.startsWith("it")', source)
        self.assertIn('language.startsWith("hi")', source)
        self.assertNotIn("const DICTIONARIES", source)
        self.assertIn("export const DEFAULT_LOCALE", dictionaries_source)
        self.assertIn("export const LOCALES", dictionaries_source)
        self.assertIn("export const DICTIONARIES", dictionaries_source)
        self.assertIn('"zh-CN": ZH_CN_DICTIONARY', dictionaries_source)
        self.assertIn('"zh-TW": ZH_TW_DICTIONARY', dictionaries_source)
        self.assertIn('"zh-HK": ZH_HK_DICTIONARY', dictionaries_source)
        self.assertIn('"ja": JA_DICTIONARY', dictionaries_source)
        self.assertIn('"ko": KO_DICTIONARY', dictionaries_source)
        self.assertIn('"en": EN_DICTIONARY', dictionaries_source)
        self.assertIn('"es": ES_DICTIONARY', dictionaries_source)
        self.assertIn('"pt": PT_DICTIONARY', dictionaries_source)
        self.assertIn('"fr": FR_DICTIONARY', dictionaries_source)
        self.assertIn('"de": DE_DICTIONARY', dictionaries_source)
        self.assertIn('"ru": RU_DICTIONARY', dictionaries_source)
        self.assertIn('"it": IT_DICTIONARY', dictionaries_source)
        self.assertIn('"hi": HI_DICTIONARY', dictionaries_source)
        self.assertIn("export const ZH_CN_DICTIONARY", zh_dictionary_source)
        self.assertIn("export const ZH_TW_DICTIONARY", zh_tw_dictionary_source)
        self.assertIn("export const ZH_HK_DICTIONARY", zh_hk_dictionary_source)
        self.assertIn("export const JA_DICTIONARY", ja_dictionary_source)
        self.assertIn("export const KO_DICTIONARY", ko_dictionary_source)
        self.assertIn("export const EN_DICTIONARY", en_dictionary_source)
        self.assertIn("export const ES_DICTIONARY", es_dictionary_source)
        self.assertIn("export const PT_DICTIONARY", pt_dictionary_source)
        self.assertIn("export const FR_DICTIONARY", fr_dictionary_source)
        self.assertIn("export const DE_DICTIONARY", de_dictionary_source)
        self.assertIn("export const RU_DICTIONARY", ru_dictionary_source)
        self.assertIn("export const IT_DICTIONARY", it_dictionary_source)
        self.assertIn("export const HI_DICTIONARY", hi_dictionary_source)
        self.assertIn('"app.newTask": "新建"', zh_dictionary_source)
        self.assertIn('"app.newTask": "新增"', zh_tw_dictionary_source)
        self.assertIn('"app.newTask": "新增"', zh_hk_dictionary_source)
        self.assertIn('"app.newTask": "新規"', ja_dictionary_source)
        self.assertIn('"app.newTask": "새로 만들기"', ko_dictionary_source)
        self.assertIn('"app.newTask": "New"', en_dictionary_source)
        self.assertIn('"app.newTask": "Nuevo"', es_dictionary_source)
        self.assertIn('"app.newTask": "Novo"', pt_dictionary_source)
        self.assertIn('"app.newTask": "Nouveau"', fr_dictionary_source)
        self.assertIn('"app.newTask": "Neu"', de_dictionary_source)
        self.assertIn('"app.newTask": "Новый"', ru_dictionary_source)
        self.assertIn('"app.newTask": "Nuovo"', it_dictionary_source)
        self.assertIn('"app.newTask": "नया"', hi_dictionary_source)
        self.assertIn('"outputSettings.title": "输出设置"', zh_dictionary_source)
        self.assertIn('"outputSettings.title": "輸出設定"', zh_tw_dictionary_source)
        self.assertIn('"outputSettings.title": "輸出設定"', zh_hk_dictionary_source)
        self.assertIn('"outputSettings.title": "出力設定"', ja_dictionary_source)
        self.assertIn('"outputSettings.title": "출력 설정"', ko_dictionary_source)
        self.assertIn('"outputSettings.title": "Output"', en_dictionary_source)
        self.assertIn('"language.es": "Español"', es_dictionary_source)
        self.assertIn('"language.pt": "Português"', pt_dictionary_source)
        self.assertIn('"language.fr": "Français"', fr_dictionary_source)
        self.assertIn('"language.de": "Deutsch"', de_dictionary_source)
        self.assertIn('"language.ru": "Русский"', ru_dictionary_source)
        self.assertIn('"language.it": "Italiano"', it_dictionary_source)
        self.assertIn('"language.hi": "हिन्दी"', hi_dictionary_source)
        self.assertIn('document.querySelectorAll<HTMLElement>("[data-i18n]")', source)
        self.assertIn('querySelectorAll<HTMLElement>("[data-i18n-attr]")', source)
        self.assertIn("window.__codexImageI18n", source)
        self.assertIn('import { initI18nFeature } from "./i18n";', main_source)
        self.assertIn("initI18nFeature();", main_source)
        self.assertIn('languageSelect: document.querySelector("#languageSelect")', elements_source)

    def test_static_markup_uses_translation_keys_for_primary_shell(self) -> None:
        html = Path("codex_image/webui/static/index.html").read_text(encoding="utf-8")

        for key in (
            "app.newTask",
            "queue.empty",
            "theme.system",
            "imageInput.referenceTitle",
            "prompt.title",
            "prompt.run",
            "outputSettings.title",
            "preview.title",
            "systemSettings.title",
            "systemSettings.languageTab",
            "settings.status",
            "settings.language",
            "apiSettings.providers",
            "apiSettings.copyProvider",
            "apiSettings.sortProviders",
            "apiSettings.editProvider",
            "gallery.title",
        ):
            self.assertIn(f'data-i18n="{key}"', html)
        self.assertIn('data-i18n-attr="placeholder:sidebar.searchPlaceholder"', html)
        self.assertIn('data-i18n-attr="aria-label:prompt.editorLabel;data-placeholder:prompt.placeholder"', html)

    def test_language_select_styles_match_settings_panel_controls(self) -> None:
        styles = Path("codex_image/webui/static/styles.css").read_text(encoding="utf-8")

        self.assertRegex(styles, r"\.language-settings-panel\s*\{[^}]*display:\s*grid")
        self.assertRegex(styles, r"\.language-settings-panel\s*\{[^}]*max-width:\s*640px")
        self.assertRegex(styles, r"\.language-select-field\s*\{[^}]*max-width:\s*420px")
        self.assertNotRegex(styles, r"\.language-switcher\s*\{")
        self.assertNotRegex(styles, r"\.language-option\s*\{")

    def test_runtime_rendered_surfaces_use_i18n_keys(self) -> None:
        i18n_source = Path("codex_image/webui/frontend/src/i18n.ts").read_text(encoding="utf-8")
        dictionary_source = "\n".join(
            [
                Path("codex_image/webui/frontend/src/i18n/zh-cn.ts").read_text(encoding="utf-8"),
                Path("codex_image/webui/frontend/src/i18n/zh-tw.ts").read_text(encoding="utf-8"),
                Path("codex_image/webui/frontend/src/i18n/zh-hk.ts").read_text(encoding="utf-8"),
                Path("codex_image/webui/frontend/src/i18n/ja.ts").read_text(encoding="utf-8"),
                Path("codex_image/webui/frontend/src/i18n/ko.ts").read_text(encoding="utf-8"),
                Path("codex_image/webui/frontend/src/i18n/en.ts").read_text(encoding="utf-8"),
            ]
        )
        runtime_sources = {
            "queue": Path("codex_image/webui/frontend/src/queue.ts").read_text(encoding="utf-8"),
            "notifications": Path("codex_image/webui/frontend/src/task-notifications.ts").read_text(encoding="utf-8"),
            "archive": Path("codex_image/webui/frontend/src/task-archive-controls.ts").read_text(encoding="utf-8"),
            "task_groups": Path("codex_image/webui/frontend/src/task-list-render.ts").read_text(encoding="utf-8"),
            "templates": Path("codex_image/webui/frontend/src/prompt-templates.ts").read_text(encoding="utf-8"),
            "gallery": Path("codex_image/webui/frontend/src/gallery-grid.ts").read_text(encoding="utf-8"),
            "gallery_categories": Path("codex_image/webui/frontend/src/gallery-categories.ts").read_text(encoding="utf-8"),
            "preview": Path("codex_image/webui/frontend/src/task-preview.ts").read_text(encoding="utf-8"),
            "api_settings": Path("codex_image/webui/frontend/src/api-provider-settings.ts").read_text(encoding="utf-8"),
            "storage": Path("codex_image/webui/frontend/src/storage-settings.ts").read_text(encoding="utf-8"),
            "image_strip": Path("codex_image/webui/frontend/src/image-strip.ts").read_text(encoding="utf-8"),
            "custom_size": Path("codex_image/webui/frontend/src/custom-size-controls.ts").read_text(encoding="utf-8"),
            "batch": Path("codex_image/webui/frontend/src/task-batch-controls.ts").read_text(encoding="utf-8"),
            "form": Path("codex_image/webui/frontend/src/form-controls.ts").read_text(encoding="utf-8"),
            "recent_assets": Path("codex_image/webui/frontend/src/recent-assets.ts").read_text(encoding="utf-8"),
            "input_sources": Path("codex_image/webui/frontend/src/input-sources.ts").read_text(encoding="utf-8"),
            "task_submit": Path("codex_image/webui/frontend/src/task-submit.ts").read_text(encoding="utf-8"),
            "task_selection": Path("codex_image/webui/frontend/src/task-selection.ts").read_text(encoding="utf-8"),
            "task_preview": Path("codex_image/webui/frontend/src/task-preview.ts").read_text(encoding="utf-8"),
            "overlay_popovers": Path("codex_image/webui/frontend/src/overlay-popovers.ts").read_text(encoding="utf-8"),
            "task_context_menu": Path("codex_image/webui/frontend/src/task-context-menu.ts").read_text(encoding="utf-8"),
            "prompt_templates": Path("codex_image/webui/frontend/src/prompt-templates.ts").read_text(encoding="utf-8"),
        }

        self.assertIn("export function formatTranslation", i18n_source)
        self.assertIn("new CustomEvent(LOCALE_CHANGE_EVENT", i18n_source)
        for key in (
            "taskGroup.today",
            "taskGroup.yesterday",
            "taskGroup.last7",
            "taskGroup.older",
            "queue.runningWaiting",
            "notifications.empty",
            "footer.archiveCount",
            "templates.availableCount",
            "gallery.drawerSubtitle",
            "gallery.dragSort",
            "preview.addReference",
            "apiSettings.modeImagesShort",
            "apiSettings.actualRequest",
            "apiSettings.newProviderAction",
            "apiSettings.copyProvider",
            "apiSettings.copyProviderStatus",
            "apiSettings.copyProviderWithoutKeyStatus",
            "apiSettings.sortProviders",
            "apiSettings.sortProviderStatus",
            "apiSettings.saveProvider",
            "apiSettings.autoSaving",
            "apiSettings.autoSaved",
            "apiSettings.cancelEdit",
            "apiSettings.deleteProviderTitle",
            "apiSettings.deleteProviderMessage",
            "apiSettings.deleteProviderStatus",
            "imageInput.uploadBadge",
            "imageInput.addToGalleryShort",
            "imageInput.removeImage",
            "imageInput.editedBadge",
            "output.pixelPreviewValue",
            "batch.selectedCount",
            "prompt.runEdit",
            "recentAssets.deleteMessage",
            "recentAssets.deleted",
            "inputSource.uploadFallback",
            "status.missingRecentReference",
            "status.emptyPrompt",
            "status.loadedTask",
            "status.loadingHistoryInputs",
            "status.historyInputLoadFailed",
            "taskList.viewing",
            "referenceCollector.title",
            "referenceCollector.addAll",
            "referenceCollector.added",
            "preview.selectedCount",
            "preview.selectedFeatured",
            "preview.removeFeatured",
            "preview.selectionAdded",
            "preview.deleteUnselectedDetail",
            "promptPopover.title",
            "promptPopover.original",
            "promptPopover.optimized",
            "promptPopover.copyOptimized",
            "taskContext.view",
            "taskContext.delete",
            "templates.formTitle",
            "templates.formContent",
            "templates.formFavorite",
            "notifications.taskFailed",
            "notifications.taskPartial",
            "notifications.taskCompleted",
            "notifications.generationFailed",
            "notifications.successCount",
            "notifications.resultAvailable",
            "notifications.failedCount",
            "notifications.systemUnsupported",
            "notifications.systemBlocked",
            "notifications.systemDenied",
            "notifications.systemEnabled",
            "notifications.taskMissing",
            "queue.cancelRunningConfirm",
            "queue.cancelRunningFailed",
            "queue.cancelRunningMessage",
            "queue.cancelRunningTitleConfirm",
            "queue.deleteQueuedFailed",
            "queue.deleteWaitingMessage",
            "queue.deleteWaitingTitleConfirm",
            "queue.promoteFailed",
            "queue.queuedDeleted",
            "queue.reorderFailed",
            "queue.runningCancelled",
            "colors.hexValue",
            "colors.pendingUpdate",
        ):
            self.assertIn(f'"{key}"', dictionary_source)

        self.assertIn('formatTranslation("queue.runningWaiting"', runtime_sources["queue"])
        self.assertIn('translate("queue.empty")', runtime_sources["queue"])
        self.assertIn('translate("queue.promoteFailed")', runtime_sources["queue"])
        self.assertIn('translate("queue.deleteWaitingTitleConfirm")', runtime_sources["queue"])
        self.assertIn('translate("queue.deleteQueuedFailed")', runtime_sources["queue"])
        self.assertIn('translate("queue.cancelRunningTitleConfirm")', runtime_sources["queue"])
        self.assertIn('translate("queue.cancelRunningFailed")', runtime_sources["queue"])
        self.assertIn('translate("queue.reorderFailed")', runtime_sources["queue"])
        self.assertIn('formatTranslation("notifications.unread"', runtime_sources["notifications"])
        self.assertIn('translate("notifications.empty")', runtime_sources["notifications"])
        self.assertIn('translate("notifications.taskCompleted")', runtime_sources["notifications"])
        self.assertIn('formatTranslation("notifications.successCount"', runtime_sources["notifications"])
        self.assertIn('translate("footer.historyLibrary")', runtime_sources["archive"])
        self.assertIn('translate("taskGroup.today")', runtime_sources["task_groups"])
        self.assertIn('translate("taskGroup.last7")', runtime_sources["task_groups"])
        self.assertIn('formatTranslation("templates.availableCount"', runtime_sources["templates"])
        self.assertIn('translate("templates.noMatch")', runtime_sources["templates"])
        self.assertIn('formatTranslation("gallery.drawerSubtitle"', runtime_sources["gallery"])
        self.assertIn('translate("gallery.use")', runtime_sources["gallery"])
        self.assertIn('defaultGalleryCategoryLabel', runtime_sources["gallery_categories"])
        self.assertIn('translate("preview.addReference")', runtime_sources["preview"])
        self.assertIn('translate("preview.stage")', runtime_sources["preview"])
        self.assertIn('translate("apiSettings.modeImagesShort")', runtime_sources["api_settings"])
        self.assertIn('translate("apiSettings.saveProvider")', runtime_sources["api_settings"])
        self.assertIn('translate("apiSettings.autoSaving")', runtime_sources["api_settings"])
        self.assertIn('translate("apiSettings.autoSaved")', runtime_sources["api_settings"])
        self.assertIn('translate("apiSettings.deleteProviderTitle")', runtime_sources["api_settings"])
        self.assertIn('formatTranslation("apiSettings.deleteProviderMessage"', runtime_sources["api_settings"])
        self.assertIn('translate("settings.status")', runtime_sources["storage"])
        self.assertIn('translate("imageInput.uploadBadge")', runtime_sources["image_strip"])
        self.assertIn('translate("imageInput.addToGalleryShort")', runtime_sources["image_strip"])
        self.assertIn('translate("imageInput.removeImage")', runtime_sources["image_strip"])
        self.assertIn('formatTranslation("output.pixelPreviewValue"', runtime_sources["custom_size"])
        self.assertIn('formatTranslation("batch.selectedCount"', runtime_sources["batch"])
        self.assertIn('translate(mode === "edit" ? "prompt.runEdit" : "prompt.run")', runtime_sources["form"])
        self.assertIn('formatTranslation("recentAssets.use"', runtime_sources["recent_assets"])
        self.assertIn('translate("recentAssets.deleteMessage")', runtime_sources["recent_assets"])
        self.assertIn('document.addEventListener(LOCALE_CHANGE_EVENT, renderRecentAssets);', runtime_sources["recent_assets"])
        self.assertIn('translate("inputSource.uploadFallback")', runtime_sources["input_sources"])
        self.assertIn('translate("status.missingRecentReference")', runtime_sources["task_submit"])
        self.assertIn('translate("status.emptyPrompt")', runtime_sources["task_submit"])
        self.assertIn('formatTranslation("status.loadedTask"', runtime_sources["task_selection"])
        self.assertIn('translate("status.loadingHistoryInputs")', runtime_sources["task_selection"])
        self.assertIn('formatTranslation("status.historyInputLoadFailed"', runtime_sources["task_selection"])
        self.assertIn('formatTranslation("referenceCollector.title"', runtime_sources["input_sources"])
        self.assertIn('translate("referenceCollector.addAll")', runtime_sources["input_sources"])
        self.assertIn('formatTranslation("referenceCollector.added"', runtime_sources["input_sources"])
        self.assertIn('formatTranslation("preview.selectedCount"', runtime_sources["task_preview"])
        self.assertIn('translate("preview.selectedFeatured")', runtime_sources["task_preview"])
        self.assertIn('translate("preview.removeFeatured")', runtime_sources["task_preview"])
        self.assertIn('formatTranslation("preview.deleteUnselectedDetail"', runtime_sources["task_preview"])
        self.assertIn('translate("promptPopover.title")', runtime_sources["overlay_popovers"])
        self.assertIn('translate("promptPopover.copyOptimized")', runtime_sources["overlay_popovers"])
        self.assertIn('taskContextButton("view", translate("taskContext.view"))', runtime_sources["task_context_menu"])
        self.assertIn('taskContextButton("delete", translate("taskContext.delete")', runtime_sources["task_context_menu"])
        self.assertIn('translate("templates.formTitle")', runtime_sources["prompt_templates"])
        self.assertIn('translate("templates.formContent")', runtime_sources["prompt_templates"])
        self.assertIn('translate("templates.formFavorite")', runtime_sources["prompt_templates"])

    def test_core_runtime_modules_do_not_keep_hardcoded_chinese_ui_copy(self) -> None:
        frontend_root = Path("codex_image/webui/frontend/src")
        core_runtime_files = (
            "api-provider-settings.ts",
            "auth-source.ts",
            "color-palette.ts",
            "custom-size-controls.ts",
            "gallery.ts",
            "gallery-categories.ts",
            "gallery-grid.ts",
            "gallery-item-actions.ts",
            "image-editor.ts",
            "input-sources.ts",
            "lightbox.ts",
            "main-model-combobox.ts",
            "prompt-colors.ts",
            "prompt-find-replace.ts",
            "prompt-gallery-chips.ts",
            "prompt-snippets.ts",
            "prompt-templates.ts",
            "quick-gallery.ts",
            "queue.ts",
            "runtime-feedback.ts",
            "shell-ui.ts",
            "size-presets.ts",
            "storage-settings.ts",
            "task-actions.ts",
            "task-archive-controls.ts",
            "task-batch-controls.ts",
            "task-derived.ts",
            "task-history-anchors.ts",
            "task-list-render.ts",
            "task-notifications.ts",
            "task-selection.ts",
            "task-submit.ts",
        )

        offenders: list[str] = []
        for filename in core_runtime_files:
            source = (frontend_root / filename).read_text(encoding="utf-8")
            for line_number, line in enumerate(source.splitlines(), 1):
                if re.search(r"[\u4e00-\u9fff]", line):
                    offenders.append(f"{filename}:{line_number}: {line.strip()}")

        self.assertEqual([], offenders)

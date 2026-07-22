export type Locale = "zh-CN" | "zh-TW" | "zh-HK" | "ja" | "ko" | "en" | "es" | "pt" | "fr" | "de" | "ru" | "it" | "hi";
export type TranslationDictionary = Record<string, string>;
export type TranslationValues = Record<string, string | number>;
export type ModelSelectionTranslationKey =
  | "modelSelection.family"
  | "modelSelection.concreteModel"
  | "modelSelection.provider"
  | "modelSelection.providerUnavailable"
  | "modelSelection.openSettings"
  | "modelSelection.codexUnavailable"
  | "modelSelection.catalogUnavailable";

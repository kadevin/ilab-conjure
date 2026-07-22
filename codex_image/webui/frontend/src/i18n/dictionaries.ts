import { EN_DICTIONARY } from "./en";
import { DE_DICTIONARY } from "./de";
import { ES_DICTIONARY } from "./es";
import { FR_DICTIONARY } from "./fr";
import { JA_DICTIONARY } from "./ja";
import { KO_DICTIONARY } from "./ko";
import { PT_DICTIONARY } from "./pt";
import { RU_DICTIONARY } from "./ru";
import { IT_DICTIONARY } from "./it";
import { HI_DICTIONARY } from "./hi";
import type { Locale, ModelSelectionTranslationKey, TranslationDictionary } from "./types";
import { ZH_CN_DICTIONARY } from "./zh-cn";
import { ZH_HK_DICTIONARY } from "./zh-hk";
import { ZH_TW_DICTIONARY } from "./zh-tw";

export const DEFAULT_LOCALE: Locale = "zh-CN";
export const LOCALES: readonly Locale[] = ["zh-CN", "zh-TW", "zh-HK", "ja", "ko", "en", "es", "pt", "fr", "de", "ru", "it", "hi"];
export const MODEL_SELECTION_TRANSLATION_KEYS: readonly ModelSelectionTranslationKey[] = [
  "modelSelection.family",
  "modelSelection.concreteModel",
  "modelSelection.provider",
  "modelSelection.providerUnavailable",
  "modelSelection.openSettings",
  "modelSelection.codexUnavailable",
  "modelSelection.catalogUnavailable",
];

export const DICTIONARIES: Record<Locale, TranslationDictionary> = {
  "zh-CN": ZH_CN_DICTIONARY,
  "zh-TW": ZH_TW_DICTIONARY,
  "zh-HK": ZH_HK_DICTIONARY,
  "ja": JA_DICTIONARY,
  "ko": KO_DICTIONARY,
  "en": EN_DICTIONARY,
  "es": ES_DICTIONARY,
  "pt": PT_DICTIONARY,
  "fr": FR_DICTIONARY,
  "de": DE_DICTIONARY,
  "ru": RU_DICTIONARY,
  "it": IT_DICTIONARY,
  "hi": HI_DICTIONARY
};

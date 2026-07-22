from __future__ import annotations

import re
from math import gcd
from typing import Any


_RATIO_RE = re.compile(r"^\s*([1-9]\d{0,2})\s*:\s*([1-9]\d{0,2})\s*$")
_SIZE_RE = re.compile(r"^\s*([1-9]\d*)\s*x\s*([1-9]\d*)\s*$", re.IGNORECASE)

_RATIO_INSTRUCTION_TEMPLATES = {
    "zh-CN": "将宽高比设为 {ratio}",
    "zh-TW": "將寬高比設為 {ratio}",
    "zh-HK": "將寬高比設為 {ratio}",
    "ja": "アスペクト比を {ratio} に設定してください。",
    "ko": "화면 비율을 {ratio}로 설정하세요.",
    "en": "Set the aspect ratio to {ratio}.",
    "es": "Establece la relación de aspecto en {ratio}.",
    "pt": "Defina a proporção da imagem como {ratio}.",
    "fr": "Réglez le rapport largeur/hauteur sur {ratio}.",
    "de": "Stelle das Seitenverhältnis auf {ratio} ein.",
    "ru": "Установите соотношение сторон {ratio}.",
    "it": "Imposta le proporzioni su {ratio}.",
    "hi": "पक्षानुपात को {ratio} पर सेट करें।",
}


def _normalize_prompt_locale(value: Any) -> str:
    language = str(value or "zh-CN").strip().lower()
    exact = next(
        (locale for locale in _RATIO_INSTRUCTION_TEMPLATES if locale.lower() == language),
        None,
    )
    if exact:
        return exact
    if language.startswith(("zh-hk", "zh-mo")):
        return "zh-HK"
    if language.startswith(("zh-tw", "zh-hant")):
        return "zh-TW"
    if language.startswith(("zh-cn", "zh-sg", "zh-hans")) or language == "zh":
        return "zh-CN"
    for locale in ("ja", "ko", "en", "es", "pt", "fr", "de", "ru", "it", "hi"):
        if language.startswith(locale):
            return locale
    return "zh-CN"


def normalize_prompt_ratio(value: Any) -> str:
    match = _RATIO_RE.match(str(value or ""))
    if not match:
        return ""
    return f"{int(match.group(1))}:{int(match.group(2))}"


def ratio_from_size(value: Any) -> str:
    match = _SIZE_RE.match(str(value or ""))
    if not match:
        return ""
    width = int(match.group(1))
    height = int(match.group(2))
    divisor = gcd(width, height)
    return f"{width // divisor}:{height // divisor}"


def orientation_from_ratio(value: Any) -> str:
    ratio = normalize_prompt_ratio(value)
    if not ratio:
        return ""
    width, height = (int(part) for part in ratio.split(":"))
    if width == height:
        return "square"
    return "landscape" if width > height else "portrait"


def ratio_prompt_instruction(value: Any, *, locale: Any = None) -> str:
    ratio = normalize_prompt_ratio(value)
    if not ratio:
        return ""
    template = _RATIO_INSTRUCTION_TEMPLATES[_normalize_prompt_locale(locale)]
    return template.format(ratio=ratio)


def append_ratio_prompt_instruction(prompt: str, ratio: Any, *, locale: Any = None) -> str:
    instruction = ratio_prompt_instruction(ratio, locale=locale)
    if not instruction:
        return prompt
    prompt_text = str(prompt or "").rstrip()
    if instruction in prompt_text:
        return prompt_text
    if not prompt_text:
        return instruction
    return f"{prompt_text}\n\n{instruction}"

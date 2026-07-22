type ModelFamilyBrandMark = {
  asset: string;
  className: string;
};

const BRAND_MARKS: Record<string, ModelFamilyBrandMark> = {
  "gpt-image": {
    asset: "/static/brand/model-marks/openai.svg",
    className: "openai",
  },
  "gemini-image": {
    asset: "/static/brand/model-marks/gemini.svg",
    className: "gemini",
  },
};

function fallbackMarkHtml(className: string): string {
  return `
    <svg class="${className} model-family-brand-mark-fallback" viewBox="0 0 24 24" aria-hidden="true" focusable="false">
      <path d="m12 4 8 8-8 8-8-8Z" />
    </svg>`;
}

export function modelFamilyBrandMarkHtml(familyId: string, className: string): string {
  const mark = BRAND_MARKS[familyId];
  if (!mark) return fallbackMarkHtml(className);
  return `<img class="${className} model-family-brand-mark-${mark.className}" src="${mark.asset}" alt="" aria-hidden="true" decoding="async" />`;
}

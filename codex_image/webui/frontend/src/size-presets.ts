import { getLegacyBridge } from "./state";
import { currentAuthSource } from "./auth-source";
import { currentApiImageModel, currentApiImagesConcurrency, currentApiMode, currentApiProviderId } from "./api-provider-settings";
import { currentMainModel } from "./main-model-combobox";
import { currentQuantity } from "./output-controls";
import { translate } from "./i18n";

export const DEFAULT_RESOLUTION = "standard";
export const DEFAULT_RATIO = "1:1";
export const DEFAULT_ORIENTATION = "square";

export const RATIO_ORIENTATION: Record<string, string> = {
  "1:1": "square",
  "4:5": "portrait",
  "5:4": "landscape",
  "3:4": "portrait",
  "4:3": "landscape",
  "2:3": "portrait",
  "3:2": "landscape",
  "9:16": "portrait",
  "16:9": "landscape",
  "9:21": "portrait",
  "21:9": "landscape",
};

export const RATIO_COUNTERPARTS: Record<string, string> = {
  "1:1": "1:1",
  "4:5": "5:4",
  "5:4": "4:5",
  "3:4": "4:3",
  "4:3": "3:4",
  "2:3": "3:2",
  "3:2": "2:3",
  "9:16": "16:9",
  "16:9": "9:16",
  "9:21": "21:9",
  "21:9": "9:21",
};

export const ORIENTATION_DEFAULT_RATIOS: Record<string, string> = {
  square: "1:1",
  portrait: "2:3",
  landscape: "3:2",
};

export const GPT_IMAGE_2_SIZE_PRESETS: Record<string, Record<string, [number, number]>> = {
  standard: {
    "1:1": [1024, 1024],
    "4:5": [1024, 1280],
    "5:4": [1280, 1024],
    "3:4": [1152, 1536],
    "4:3": [1536, 1152],
    "2:3": [1024, 1536],
    "3:2": [1536, 1024],
    "9:16": [864, 1536],
    "16:9": [1536, 864],
    "9:21": [672, 1568],
    "21:9": [1568, 672],
  },
  "2k": {
    "1:1": [2048, 2048],
    "4:5": [1600, 2000],
    "5:4": [2000, 1600],
    "3:4": [1536, 2048],
    "4:3": [2048, 1536],
    "2:3": [1344, 2016],
    "3:2": [2016, 1344],
    "9:16": [1152, 2048],
    "16:9": [2048, 1152],
    "9:21": [1152, 2688],
    "21:9": [2688, 1152],
  },
  "4k": {
    "1:1": [2880, 2880],
    "4:5": [2560, 3200],
    "5:4": [3200, 2560],
    "3:4": [2448, 3264],
    "4:3": [3264, 2448],
    "2:3": [2336, 3504],
    "3:2": [3504, 2336],
    "9:16": [2160, 3840],
    "16:9": [3840, 2160],
    "9:21": [1632, 3808],
    "21:9": [3808, 1632],
  },
};

export const GPT_IMAGE_2_POPULAR_SIZE_EXAMPLES = ["1024x1024", "1024x1280", "1280x1024", "1024x1536", "1536x1024", "2048x1152", "3840x2160", "2160x3840", "1568x672"];

export const GPT_IMAGE_2_MIN_PIXELS = 655360;
export const GPT_IMAGE_2_MAX_PIXELS = 8294400;
export const GPT_IMAGE_2_MAX_LONG_SHORT_RATIO = 3;

const { els } = getLegacyBridge();

function legacyMethod(name: string, ...args: any[]): any {
  const method = getLegacyBridge().methods[name];
  if (typeof method !== "function") {
    throw new Error("Legacy method " + name + " is not initialized");
  }
  return method(...args);
}

function currentPromptFidelity(): string { return legacyMethod("currentPromptFidelity"); }

export function presetDimensions(resolution: any, ratio: any): [number, number] {
  const defaultPreset = GPT_IMAGE_2_SIZE_PRESETS[DEFAULT_RESOLUTION] as Record<string, [number, number]>;
  const preset = GPT_IMAGE_2_SIZE_PRESETS[resolution] || defaultPreset;
  const dimensions = preset[ratio] || preset[DEFAULT_RATIO] || defaultPreset[DEFAULT_RATIO] || [1024, 1024];
  return dimensions;
}

export function sizeForPreset(resolution: any, ratio: any): string {
  const [width, height] = presetDimensions(resolution, ratio);
  return `${width}x${height}`;
}

export function orientationForRatio(ratio: any): string {
  return RATIO_ORIENTATION[ratio] || DEFAULT_ORIENTATION;
}

export function orientationForDimensions(width: any, height: any): string {
  const numericWidth = Number(width);
  const numericHeight = Number(height);
  if (numericWidth === numericHeight) return "square";
  return numericWidth > numericHeight ? "landscape" : "portrait";
}

export function normalizeCustomDimension(value: any): number | null {
  const rawValue = String(value ?? "").trim();
  if (!rawValue) return null;
  const numericValue = Number(rawValue);
  if (!Number.isInteger(numericValue)) return null;
  return numericValue;
}

export function customDimensionValue(input: any): number | null {
  return normalizeCustomDimension(input?.value);
}

export function customSizeValidationMessage(width: any = customDimensionValue(els.customWidth), height: any = customDimensionValue(els.customHeight)): string {
  if (width === null || height === null) return translate("output.customSizeRequired");
  if (width < 16 || width > 3840 || height < 16 || height > 3840) return translate("output.customSizeBounds");
  if (width % 16 !== 0 || height % 16 !== 0) return translate("output.customSizeMultiple");
  if (Math.max(width, height) / Math.min(width, height) > GPT_IMAGE_2_MAX_LONG_SHORT_RATIO) return translate("output.customSizeRatio");
  const totalPixels = width * height;
  if (totalPixels < GPT_IMAGE_2_MIN_PIXELS || totalPixels > GPT_IMAGE_2_MAX_PIXELS) return translate("output.customSizePixels");
  return "";
}

export function findPresetForSize(size: any): any {
  for (const [resolution, ratios] of Object.entries(GPT_IMAGE_2_SIZE_PRESETS)) {
    for (const [ratio, dimensions] of Object.entries(ratios)) {
      if (`${dimensions[0]}x${dimensions[1]}` === size) {
        return { resolution, ratio, orientation: RATIO_ORIENTATION[ratio] || orientationForDimensions(dimensions[0], dimensions[1]) };
      }
    }
  }
  return null;
}

export function currentSize(): string {
  if (els.size.value !== "custom") return els.size.value;
  return `${els.customWidth.value}x${els.customHeight.value}`;
}

export function currentImageToolModel(): string {
  return currentAuthSource() === "api" ? currentApiImageModel() : els.model.value;
}

export function currentTaskParams(): any {
  const params: any = {
    main_model: currentMainModel(),
    model: currentImageToolModel(),
    size: currentSize(),
    n: currentQuantity(),
    prompt_fidelity: currentPromptFidelity(),
    quality: els.quality.value,
    output_format: els.outputFormat.value,
    moderation: els.moderation.value,
    output_compression: els.outputFormat.value === "png" ? null : Number(els.compression.value),
  };
  if (currentAuthSource() === "api") {
    params.api_provider_id = currentApiProviderId();
    params.api_mode = currentApiMode();
    params.api_images_concurrency = currentApiImagesConcurrency();
  }
  return params;
}

import type { GenerationCatalog } from "./types";

function record(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value)
    ? value as Record<string, unknown>
    : {};
}

function explicitCanonicalModelId(task: unknown): string {
  const source = record(task);
  const snapshot = record(source.generation_snapshot);
  const request = record(source.request);
  return String(snapshot.canonical_model_id || request.canonical_model_id || "").trim();
}

export function taskCanonicalModelId(task: unknown): string {
  return explicitCanonicalModelId(task) || "gpt-image-2";
}

export type TaskOutputSettingsView = "locked-summary" | "parameter-inspector" | "editor";

export function taskOutputSettingsView(
  task: unknown,
  selectedModelId: string,
  outputSettingsLocked: boolean,
): TaskOutputSettingsView {
  if (outputSettingsLocked) return "locked-summary";
  return taskCanonicalModelId(task) === selectedModelId ? "editor" : "parameter-inspector";
}

export function taskRequestedParameters(task: unknown): Record<string, unknown> {
  const source = record(task);
  const snapshot = record(source.generation_snapshot);
  const frozen = record(snapshot.requested_parameters);
  if (Object.keys(frozen).length) return { ...frozen };
  return { ...record(record(source.request).parameters) };
}

function preferredParameter(
  parameters: Record<string, unknown>,
  parameterId: string,
  ...fallbacks: unknown[]
): unknown {
  if (parameters[parameterId] !== undefined && parameters[parameterId] !== null) {
    return parameters[parameterId];
  }
  return fallbacks.find((value) => value !== undefined && value !== null);
}

export function taskOutputControlValues(task: unknown): Record<string, unknown> {
  const source = record(task);
  const params = record(source.params);
  const request = record(source.request);
  const parameters = taskRequestedParameters(task);
  const values = {
    size: preferredParameter(parameters, "canvas.size", params.size, request.size),
    ratio: preferredParameter(parameters, "canvas.aspect_ratio", params.ratio, request.ratio),
    resolution: preferredParameter(parameters, "canvas.resolution", params.resolution, request.resolution),
    quality: preferredParameter(parameters, "gpt.quality", params.quality, request.quality),
    background: preferredParameter(parameters, "gpt.background", params.background, request.background),
    moderation: preferredParameter(parameters, "gpt.moderation", params.moderation, request.moderation),
    web_search: preferredParameter(parameters, "gpt.web_search", params.web_search, request.web_search),
    n: preferredParameter(parameters, "output.count", params.n, request.n),
    output_format: preferredParameter(parameters, "output.format", params.output_format, request.output_format),
    output_compression: preferredParameter(
      parameters,
      "gpt.output_compression",
      params.output_compression,
      request.output_compression,
    ),
  };
  return Object.fromEntries(Object.entries(values).filter(([, value]) => value !== undefined && value !== null));
}

export function taskModelDisplayName(task: unknown, catalog: GenerationCatalog | null | undefined): string {
  const modelId = taskCanonicalModelId(task);
  return catalog?.models.find((model) => model.id === modelId)?.display_name || modelId;
}

export function taskModelFamilyId(
  task: unknown,
  catalog: GenerationCatalog | null | undefined,
): "gpt-image" | "gemini-image" | "unknown" {
  const modelId = taskCanonicalModelId(task);
  const familyId = catalog?.models.find((model) => model.id === modelId)?.family_id;
  if (familyId === "gpt-image" || familyId === "gemini-image") return familyId;
  if (modelId === "gpt-image-2") return "gpt-image";
  if (modelId.startsWith("nano-banana")) return "gemini-image";
  return "unknown";
}

function greatestCommonDivisor(left: number, right: number): number {
  let a = Math.abs(Math.round(left));
  let b = Math.abs(Math.round(right));
  while (b) [a, b] = [b, a % b];
  return a || 1;
}

function dimensions(value: unknown): [number, number] | null {
  const match = String(value || "").trim().match(/^(\d+)\s*[x×]\s*(\d+)$/i);
  if (!match) return null;
  const width = Number(match[1]);
  const height = Number(match[2]);
  return width > 0 && height > 0 ? [width, height] : null;
}

function compactDimensions(value: [number, number] | null): string {
  return value ? `${value[0]}×${value[1]}` : "";
}

function normalizedGptResolution(value: string): string {
  const normalized = value.trim().toLowerCase();
  if (normalized === "standard" || normalized === "1k") return "1K";
  if (normalized === "2k") return "2K";
  if (normalized === "4k") return "4K";
  return value.trim();
}

export function taskCanvasSummaryParts(task: unknown): string[] {
  const source = record(task);
  const params = record(source.params);
  const request = record(source.request);
  const parameters = taskRequestedParameters(task);
  const size = dimensions(
    parameters["canvas.size"] || source.output_size || params.size || request.size,
  );
  const explicitRatio = String(parameters["canvas.aspect_ratio"] || params.ratio || "").trim();
  const ratio = explicitRatio || (size
    ? `${size[0] / greatestCommonDivisor(size[0], size[1])}:${size[1] / greatestCommonDivisor(size[0], size[1])}`
    : "");
  const explicitResolution = String(parameters["canvas.resolution"] || params.resolution || "").trim();
  const resolution = taskCanonicalModelId(task) === "gpt-image-2"
    ? normalizedGptResolution(explicitResolution)
    : explicitResolution;
  const honestResolution = resolution && resolution.toLowerCase() !== "custom"
    ? resolution
    : compactDimensions(size);
  return [ratio, honestResolution].filter(Boolean);
}

function channelLabelForProtocolProfile(value: unknown): string {
  const profile = String(value || "").trim();
  if (profile === "openai_responses") return "Responses";
  if (["openai_images", "t8_images", "openrouter_images", "gemini_openai_images"].includes(profile)) {
    return "Image";
  }
  if (["gemini_generate_content", "gemini_change2pro_generate_content"].includes(profile)) {
    return "Gemini";
  }
  return "";
}

export function taskChannelLabel(task: unknown): string {
  const source = record(task);
  const snapshot = record(source.generation_snapshot);
  for (const profile of [source.backend, snapshot.protocol_profile, source.requested_backend]) {
    const label = channelLabelForProtocolProfile(profile);
    if (label) return label;
  }
  return "";
}

export function taskUsesCanonicalModelSummary(task: unknown): boolean {
  const modelId = explicitCanonicalModelId(task);
  return Boolean(modelId && modelId !== "gpt-image-2");
}

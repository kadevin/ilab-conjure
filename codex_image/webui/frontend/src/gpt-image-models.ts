/** Versions sharing the GPT Image controls; Codex bindings remain Image 2 only. */
export function isGptImageModel(modelId: unknown): boolean {
  return ["gpt-image-2", "gpt-image-2.5-flare", "gpt-image-2.5-sunburst"].includes(String(modelId || ""));
}

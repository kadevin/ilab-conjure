import { readFileSync } from "node:fs";

import { canonicalControlValues, canonicalParametersForSubmission } from "../../codex_image/webui/frontend/src/model-parameter-drafts";

const fixturePath = process.env.GENERATION_CATALOG_FIXTURE;
if (!fixturePath) throw new Error("GENERATION_CATALOG_FIXTURE is required");
const catalog = JSON.parse(readFileSync(fixturePath, "utf8"));
const fixedGptControls = canonicalControlValues({
  resolution: "1K",
  ratio: "1:1",
  output_format: "png",
  quality: "auto",
  moderation: "auto",
  n: 1,
}, "openai_images");
const result: Record<string, Record<string, unknown>> = {};
for (const modelId of ["nano-banana-pro"]) {
  const model = catalog.models.find((item: any) => item.id === modelId);
  result[modelId] = canonicalParametersForSubmission(model, "generate", {}, fixedGptControls);
}
process.stdout.write(JSON.stringify(result));

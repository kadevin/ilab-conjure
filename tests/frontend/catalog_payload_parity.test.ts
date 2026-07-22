import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import { isGenerationCatalog } from "../../codex_image/webui/frontend/src/model-catalog";

test("real backend generation catalog payload passes the frontend validator", () => {
  const fixturePath = process.env.GENERATION_CATALOG_FIXTURE;
  assert.ok(fixturePath, "GENERATION_CATALOG_FIXTURE is required");
  const payload = JSON.parse(readFileSync(fixturePath, "utf8"));
  assert.deepEqual(
    payload.families.map((family: any) => family.id),
    ["gpt-image", "gemini-image"],
  );
  assert.equal(isGenerationCatalog(payload), true);
});

import assert from "node:assert/strict";
import test from "node:test";

import {
  clearProviderApiKeyInputs,
  evaluateProviderCredentialSave,
  isConfirmedProviderOriginChange,
} from "../../codex_image/webui/frontend/src/api-provider-credentials";

const savedProvider = {
  id: "relay",
  base_url: "https://relay.example/v1",
  api_key: "",
  api_key_set: true,
};

test("allows a hidden saved key when the URL origin is unchanged", () => {
  assert.deepEqual(
    evaluateProviderCredentialSave(
      { ...savedProvider, base_url: "https://relay.example/v2" },
      [savedProvider],
    ),
    { kind: "allow" },
  );
});

test("requires confirmation before retaining a hidden key for a different origin", () => {
  assert.deepEqual(
    evaluateProviderCredentialSave(
      { ...savedProvider, base_url: "https://other.example/v1" },
      [savedProvider],
    ),
    {
      kind: "confirm_origin_change",
      providerId: "relay",
      previousOrigin: "https://relay.example",
      nextOrigin: "https://other.example",
    },
  );
});

test("accepts a newly entered key when the URL origin changes", () => {
  assert.deepEqual(
    evaluateProviderCredentialSave(
      { ...savedProvider, base_url: "https://other.example/v1", api_key: "new-secret" },
      [savedProvider],
    ),
    { kind: "allow" },
  );
});

test("rejects a new or historically keyless provider without a key", () => {
  assert.deepEqual(
    evaluateProviderCredentialSave(
      { id: "new", base_url: "https://new.example/v1", api_key: "", api_key_set: false },
      [savedProvider],
    ),
    { kind: "key_required" },
  );
  assert.deepEqual(
    evaluateProviderCredentialSave(
      { id: "keyless", base_url: "https://keyless.example/v1", api_key: "", api_key_set: false },
      [{ id: "keyless", base_url: "https://keyless.example/v1", api_key_set: false }],
    ),
    { kind: "key_required" },
  );
});

test("allows only same-origin key reuse when copying a provider", () => {
  const draft = {
    id: "relay-copy",
    base_url: "https://relay.example/v2",
    api_key: "",
    api_key_source_provider_id: "relay",
  };
  assert.deepEqual(evaluateProviderCredentialSave(draft, [savedProvider]), { kind: "allow" });
  assert.deepEqual(
    evaluateProviderCredentialSave(
      { ...draft, base_url: "https://other.example/v1" },
      [savedProvider],
    ),
    { kind: "key_required" },
  );
});

test("accepts only a confirmation for the exact provider and origin change", () => {
  const decision = evaluateProviderCredentialSave(
    { ...savedProvider, base_url: "https://other.example/v1" },
    [savedProvider],
  );
  assert.equal(
    isConfirmedProviderOriginChange(decision, {
      providerId: "relay",
      previousOrigin: "https://relay.example",
      nextOrigin: "https://other.example",
    }),
    true,
  );
  assert.equal(
    isConfirmedProviderOriginChange(decision, {
      providerId: "relay",
      previousOrigin: "https://relay.example",
      nextOrigin: "https://typo.example",
    }),
    false,
  );
});

test("drops plaintext keys from client state after the backend accepts a save", () => {
  const settings = clearProviderApiKeyInputs({
    active_provider_id: "relay",
    providers: [
      { ...savedProvider, api_key: "just-entered-secret", api_key_set: true },
    ],
  });

  assert.equal(settings.providers[0].api_key, "");
  assert.equal(settings.providers[0].api_key_set, true);
  assert.equal(settings.active_provider_id, "relay");
});

import assert from "node:assert/strict";
import test from "node:test";

test("failed deletion preserves settings, caches and routing; pending deletion excludes overlapping writes", async () => {
  const state: any = {};
  const storage = new Map<string, string>();
  const savedGlobals = { window: globalThis.window, document: globalThis.document, fetch: globalThis.fetch, localStorage: globalThis.localStorage };
  Object.assign(globalThis, {
    document: { title: "Provider deletion test", querySelector: () => null },
    window: { setTimeout: () => 1, clearTimeout() {}, __codexImageWebUI: { state, els: {}, methods: {
      setStatus() {}, syncReferenceFileAvailability() {}, currentAuthSource: () => "api", currentApiMode: () => "images",
      renderAuthSource() {}, renderProviderSelection() {}, updateRequestPreview() {},
    } } },
    localStorage: { setItem: (key: string, value: string) => storage.set(key, value) },
  });
  try {
    const { normalizeApiSettings } = await import("../../codex_image/webui/frontend/src/api-provider-model");
    const { deleteApiProvider, selectApiProvider, addApiProvider, persistApiSettings, saveApiSettings } = await import("../../codex_image/webui/frontend/src/api-provider-settings");
    for (const failure of ["server_rejected", "offline"]) {
      state.apiSettings = normalizeApiSettings({ providers: [{ id: "a", api_key_set: true }, { id: "b", api_key_set: true }],
        active_provider_id: "a", default_provider_by_model: { "gpt-image-2": "a" } });
      state.selectedProviderId = "a";
      state.selectedProviderBindingId = "a-gpt-image-2";
      state.lastProviderByModel = { "gpt-image-2": "a" };
      state.lastProviderSelectionByModel = { "gpt-image-2": "a::a-gpt-image-2" };
      persistApiSettings();
      const before = JSON.stringify(state.apiSettings);
      const beforeCache = storage.get("codex-image-api-settings");
      let writes = 0;
      let release!: () => void;
      globalThis.fetch = (async (_url: unknown, init: RequestInit) => {
        writes++;
        const payload = JSON.parse(String(init.body));
        assert.deepEqual(payload.providers.map((p: any) => p.id), ["b"]);
        assert.deepEqual(payload.default_provider_by_model, { "gpt-image-2": "b" });
        assert.equal("api_key" in payload.providers[0], false);
        await new Promise<void>(resolve => { release = resolve; });
        if (failure === "offline") throw new TypeError("Synthetic network failure");
        return new Response(JSON.stringify({ detail: "default_provider_mapping_missing" }), { status: 400 });
      }) as typeof fetch;
      const deletion = deleteApiProvider();
      assert.equal(JSON.stringify(state.apiSettings), before, "card remains until server confirmation");
      await deleteApiProvider();
      selectApiProvider("b");
      addApiProvider();
      assert.equal(await saveApiSettings({ auto: true }), false);
      assert.equal(writes, 1);
      release();
      await deletion;
      assert.equal(JSON.stringify(state.apiSettings), before);
      assert.equal(storage.get("codex-image-api-settings"), beforeCache);
      assert.equal(state.selectedProviderId, "a");
      assert.equal(state.selectedProviderBindingId, "a-gpt-image-2");
      assert.deepEqual(state.lastProviderByModel, { "gpt-image-2": "a" });
      assert.deepEqual(state.lastProviderSelectionByModel, { "gpt-image-2": "a::a-gpt-image-2" });
      assert.ok(!state.apiProviderEditingId);
    }
  } finally {
    Object.assign(globalThis, savedGlobals);
  }
});

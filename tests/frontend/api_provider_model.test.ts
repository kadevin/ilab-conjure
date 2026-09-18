import assert from 'node:assert/strict';
import test from 'node:test';
// State defaults also carry the browser document title; no live DOM is needed here.
Object.assign(globalThis, { document: { title: 'Provider tests' } });
const { applyProviderDraft, normalizeApiProvider, normalizeApiSettings } = await import('../../codex_image/webui/frontend/src/api-provider-model');
const { apiSettingsSavePayload, patchApiSettings } = await import('../../codex_image/webui/frontend/src/api-provider-save');

test('normalization preserves provider order, deduplicates ids and clamps concurrency', () => {
  const settings = normalizeApiSettings({ providers: [
    { id: 'B', concurrency: 99 }, { id: 'a', concurrency: -1 }, { id: 'b' },
  ], active_provider_id: 'missing' });
  assert.deepEqual(settings.providers.map((p: any) => [p.id, p.concurrency]), [['b', 32], ['a', 1]]);
  assert.equal(settings.active_provider_id, 'b');
});

test('draft default opt-out chooses another supporter without changing input', () => {
  const settings = normalizeApiSettings({ providers: [{ id: 'a' }, { id: 'b' }], default_provider_by_model: { 'gpt-image-2': 'a' } });
  const before = JSON.stringify(settings);
  const next = applyProviderDraft(settings, normalizeApiProvider({ ...settings.providers[0], default_model_ids: [] }));
  assert.equal(next.default_provider_by_model['gpt-image-2'], 'b');
  assert.equal(JSON.stringify(settings), before);
});

test('save payload omits stored secrets, preserves explicit replacement and scoped origin confirmation', () => {
  const settings = normalizeApiSettings({ providers: [
    { id: 'stored', api_key_set: true, api_key_masked: 'masked' },
    { id: 'new', api_key: 'synthetic-test-key' },
    { id: 'copy', api_key_set: true, api_key_source_provider_id: 'stored' },
  ] });
  const payload = apiSettingsSavePayload(settings, { providerId: 'stored', previousOrigin: 'https://a.example', nextOrigin: 'https://b.example' });
  assert.equal('api_key' in payload.providers[0], false);
  assert.equal('api_key_masked' in payload.providers[0], false);
  assert.equal(payload.providers[0].preserve_api_key_on_origin_change, true);
  assert.equal(payload.providers[1].api_key, 'synthetic-test-key');
  assert.equal('preserve_api_key_on_origin_change' in payload.providers[1], false);
  assert.equal(payload.providers[2].api_key_source_provider_id, 'stored');
});

test('transport sends one PATCH and returns server settings without modifying payload', async () => {
  const payload = { schema_version: 2, providers: [] };
  let calls = 0;
  const request = (async (url: string, init: RequestInit) => {
    calls++;
    assert.equal(url, '/api/api-settings');
    assert.equal(init.method, 'PATCH');
    assert.deepEqual(JSON.parse(String(init.body)), payload);
    return new Response(JSON.stringify({ settings: { providers: [] } }), { status: 200 });
  }) as typeof fetch;
  assert.deepEqual(await patchApiSettings(payload, request), { settings: { providers: [] } });
  assert.equal(calls, 1);
});

test('transport rejection remains a failure for the coordinator rollback', async () => {
  const request = (async () => new Response(JSON.stringify({ detail: 'synthetic_failure' }), { status: 400 })) as typeof fetch;
  await assert.rejects(patchApiSettings({}, request), /synthetic_failure/);
});

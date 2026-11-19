import assert from "node:assert/strict";
import test from "node:test";
import { readFileSync } from "node:fs";
import { runInNewContext } from "node:vm";
import { DEFAULT_APPEARANCE, APPEARANCE_STORAGE_KEY, normalizeAppearance, appearanceTokens, colorContrast, readAppearance, persistAppearance } from "../../codex_image/webui/frontend/src/appearance";
import { applyUserConfigClientPreferences, readUserConfigClientPreferences } from "../../codex_image/webui/frontend/src/task-notifications";

test("original appearance leaves all existing CSS values intact", () => {
  assert.deepEqual(appearanceTokens(DEFAULT_APPEARANCE, false), {});
  assert.deepEqual(appearanceTokens(DEFAULT_APPEARANCE, true), {});
  for (const bad of [null, {}, { ...DEFAULT_APPEARANCE, version: 2 }, { ...DEFAULT_APPEARANCE, primary: 'red;display:none' }]) {
    assert.deepEqual(normalizeAppearance(bad), DEFAULT_APPEARANCE);
  }
  assert.deepEqual(readAppearance({ getItem() { throw Error(); } }), DEFAULT_APPEARANCE);
  assert.equal(persistAppearance(DEFAULT_APPEARANCE, { setItem() { throw Error(); } }), false);
});

test("generated palettes keep text and focus readable across RGB extremes and tones", () => {
  for (const r of [0, 64, 128, 192, 255]) for (const g of [0, 64, 128, 192, 255]) for (const b of [0, 64, 128, 192, 255]) {
    const primary = '#' + [r, g, b].map(v => v.toString(16).padStart(2, '0')).join('');
    for (const background of ['neutral', 'warm', 'cool', 'tinted'] as const) for (const dark of [false, true]) {
      const t = appearanceTokens({ version: 1, preset: 'custom', primary, background }, dark);
      for (const surface of ['bg', 'surface', 'surface-soft', 'primary-light', 'secondary-action-hover', 'secondary-action-pressed']) {
        for (const text of ['text', 'text-secondary', 'text-muted']) {
          assert.ok(colorContrast(t[text], t[surface]) >= 4.5, `${primary}/${background}/${dark}: ${text} on ${surface}`);
        }
      }
      for (const fill of ['primary', 'primary-strong', 'task-card-surface-selected-hover', 'task-card-surface-selected-pressed']) {
        assert.ok(colorContrast(t['primary-foreground'], t[fill]) >= 4.5, `${primary}: ${fill}`);
      }
      assert.ok(colorContrast(t['focus-ring'], t.surface) >= 3);
      assert.ok(colorContrast(t['control-border'], t.surface) >= 3);
      assert.ok(colorContrast(t['scrollbar-thumb'], t['scrollbar-track']) >= 3, `${primary}/${dark}: scrollbar contrast`);
      for (const surface of ['viewer-surface', 'viewer-hover']) {
        for (const text of ['viewer-foreground', 'viewer-muted']) assert.ok(colorContrast(t[text], t[surface]) >= 4.5);
      }
      assert.ok(colorContrast(t['viewer-accent-foreground'], t['viewer-accent']) >= 4.5);
    }
  }
});

test("neutral backgrounds retain the chosen scrollbar hue", () => {
  for (const dark of [false, true]) {
    const tokens = ['#386FC4', '#8057B0'].map(primary => appearanceTokens({ ...DEFAULT_APPEARANCE, preset: 'custom', primary, background: 'neutral' }, dark));
    assert.equal(tokens[0].bg, tokens[1].bg);
    assert.notEqual(tokens[0]['scrollbar-thumb'], tokens[1]['scrollbar-thumb']);
  }
});

test("personalized manifests use the network with a base-only offline fallback", async () => {
  const handlers = new Map<string, (event: unknown) => void>();
  const cacheReads: unknown[] = [];
  const base = new Response("base manifest");
  const custom = new Response("custom manifest");
  const invalid = new Response("invalid colors", { status: 422 });
  let network: Response | undefined = custom;
  let cached: Response | undefined = base;
  runInNewContext(readFileSync("codex_image/webui/static/service-worker.js", "utf8"), {
    URL, Response,
    fetch: async () => {
      if (!network) throw new Error("offline");
      return network;
    },
    self: { location: { origin: "https://fixture.test" }, addEventListener: (name: string, handler: (event: unknown) => void) => handlers.set(name, handler) },
    caches: { match: async (request: unknown) => { cacheReads.push(request); return cached; } },
  });
  const dispatch = () => {
    let response: Promise<Response> | undefined;
    handlers.get("fetch")!({
      request: { method: "GET", mode: "cors", url: "https://fixture.test/manifest.webmanifest?theme_color=%238057B0" },
      respondWith: (value: Promise<Response>) => { response = value; },
    });
    return response;
  };
  assert.equal(await dispatch(), custom);
  network = invalid;
  assert.equal(await dispatch(), invalid);
  assert.deepEqual(cacheReads, []);
  network = undefined;
  assert.equal(await dispatch(), base);
  assert.deepEqual(cacheReads, ["/manifest.webmanifest"]);
  cached = undefined;
  assert.equal((await dispatch())?.type, "error");
});

test("appearance backup restore preserves existing incremental preferences and accepts old backups", () => {
  const values = new Map<string, string>();
  const storage = { getItem: (k: string) => values.get(k) ?? null, setItem: (k: string, v: string) => { values.set(k, v); } };
  const blue = { ...DEFAULT_APPEARANCE, preset: 'custom' as const, primary: '#386FC4' };
  const purple = { ...blue, primary: '#8057B0' };
  persistAppearance(blue, storage);
  assert.deepEqual(readUserConfigClientPreferences(storage).appearance, blue);
  const environment = { storage, notificationPermission: 'denied' as const, applyTheme: () => {} };
  const old = { theme: 'dark' as const, notifications: { in_app: true, system: false } };
  applyUserConfigClientPreferences({ ...old, appearance: purple }, 'incremental', environment);
  assert.deepEqual(readAppearance(storage), blue);
  applyUserConfigClientPreferences({ theme: 'dark', notifications_in_app: true, notifications_system: false, appearance: purple }, 'replace', environment);
  assert.deepEqual(readAppearance(storage), purple);
  applyUserConfigClientPreferences(old, 'replace', environment);
  assert.deepEqual(readAppearance(storage), purple);
  values.delete(APPEARANCE_STORAGE_KEY);
  applyUserConfigClientPreferences({ ...old, appearance: blue }, 'incremental', environment);
  assert.deepEqual(readAppearance(storage), blue);
});

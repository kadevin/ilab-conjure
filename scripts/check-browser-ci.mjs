// Execute the existing synthetic browser suites, never a user-supplied origin.
import { spawn } from 'node:child_process';
import { createServer } from 'node:net';
import { setTimeout as pause } from 'node:timers/promises';
import { fileURLToPath } from 'node:url';
import { chromium } from 'playwright';

const root = fileURLToPath(new URL('../', import.meta.url));
const suites = ['workbench-layout?compact-only', 'api-provider-delete',
  'api-settings?backup-navigation-only', 'api-settings?backup-boundaries-only'];
const selected = process.argv.slice(2);
if (selected.some(suite => !suites.includes(suite))) throw new Error('Unknown browser suite');
const probe = createServer();
await new Promise(resolve => probe.listen(0, '127.0.0.1', resolve));
const port = probe.address().port;
await new Promise(resolve => probe.close(resolve));
const origin = `http://127.0.0.1:${port}`;
const fixture = spawn(process.env.QA_PYTHON || 'python', ['-m', 'tests.browser_fixture', '--port', String(port)], {
  cwd: root, env: { ...process.env, PYTHONUNBUFFERED: '1' }, stdio: ['ignore', 'pipe', 'pipe'],
});
let log = '', spawnError, browser;
fixture.on('error', error => { spawnError = error; });
for (const stream of [fixture.stdout, fixture.stderr]) stream.on('data', data => { log = (log + data).slice(-6000); });
async function cleanup() {
  await browser?.close();
  if (fixture.exitCode === null && fixture.signalCode === null && !spawnError) {
    fixture.kill('SIGTERM');
    for (let i = 0; i < 100 && fixture.exitCode === null && fixture.signalCode === null; i++) await pause(100);
    if (fixture.exitCode === null && fixture.signalCode === null) fixture.kill('SIGKILL');
  }
}
for (const signal of ['SIGINT', 'SIGTERM']) process.once(signal, () => { cleanup().finally(() => process.exit(1)); });
try {
  const deadline = Date.now() + 90000;
  while (true) {
    if (spawnError || fixture.exitCode !== null) throw spawnError || new Error(`Fixture exited: ${log}`);
    if (Date.now() > deadline) throw new Error(`Fixture startup timeout: ${log}`);
    if (log.includes(`Browser acceptance: ${origin}/qa`)) {
      try { if ((await fetch(`${origin}/qa`, { signal: AbortSignal.timeout(1000) })).ok) break; } catch { /* starting */ }
    }
    await pause(200);
  }
  browser = await chromium.launch({ headless: true });
  const failed = [];
  for (const suite of selected.length ? selected : suites) {
    const context = await browser.newContext({ viewport: { width: 1600, height: 1000 } });
    const errors = [];
    await context.route('**/*', route => {
      const url = new URL(route.request().url());
      if (url.origin === origin) return route.continue();
      errors.push(`Unexpected external request: ${url.origin}`);
      return route.abort();
    });
    const page = await context.newPage();
    page.on('pageerror', error => errors.push(error.message));
    try {
      await page.goto(`${origin}/qa/${suite}`);
      await page.waitForFunction(() => {
        try { return typeof JSON.parse(document.querySelector('#results').textContent).passed === 'boolean'; }
        catch { return false; }
      }, null, { timeout: 300000 });
      const report = JSON.parse(await page.locator('#results').textContent());
      if (!report.passed || !(report.assertions > 0) || report.errors?.length || errors.length) {
        throw new Error(JSON.stringify({ suite, fatal: report.fatal, failures: report.failures,
          errors: [...errors, ...(report.errors || [])] }));
      }
      console.log(`${suite}: ${report.assertions} assertions passed`);
    } catch (error) {
      failed.push(suite);
      console.error(String(error));
    } finally { await context.close(); }
  }
  if (failed.length) throw new Error(`Browser regressions failed: ${failed.join(', ')}`);
} finally { await cleanup(); }
